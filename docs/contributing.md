# Contributing

Welcome. This page is the onboarding guide for contributors picking up the
codewizard-sherpa repo cold. It is intentionally short: the *why* lives in
[docs/production/design.md](production/design.md) and the per-phase
architecture under `docs/phases/<phase>/phase-arch-design.md`. This page
tells you what to type.

## Bootstrap

The repo standardizes on **Python 3.11+** and uses `uv` when available,
falling back to `python -m pip`. From a clean clone:

```sh
make bootstrap
```

This is the only command you should ever run by hand to get a usable
environment. It resolves all `[project.optional-dependencies]` extras
required for the dev loop. The Makefile shells out to either `uv pip install
-e ".[dev]"` or `python -m pip install -e ".[dev]"`; never mutate the
environment by editing `setup.py` (there isn't one) or pip-installing into
`site-packages` directly.

Phase 0 ships four extras (ADR-0006):

- `gather` — the deterministic probe pipeline (runtime). No LLM SDKs here.
- `dev` — the local quality loop (`ruff`, `mypy`, `pytest`, `pip-audit`,
  `import-linter`, `mkdocs`).
- `service` — Temporal worker + service-facing tooling. Empty in Phase 0;
  populated by Phases 3+.
- `agents` — **the LLM-SDK landing zone.** When Phase 4 introduces the
  LLM fallback, packages like `anthropic` (and any other LLM SDK) land in
  `[agents]` and NEVER in `[project.dependencies]`. The `fence` CI job
  enforces this: anything LLM-shaped in `dependencies` fails the build.

Run `make check` once after bootstrap to confirm the loop:

```sh
make check
```

This runs `lint → typecheck → test → fence` in order.

## Running the harness

The probe pipeline is exposed as a single CLI entry point:

```sh
codegenie gather /path/to/some/repo
```

This writes `.codegenie/context/repo-context.yaml` (human-facing) and
`.codegenie/context/raw/*.json` (raw probe outputs) inside the analyzed
repo. Cache lives under `.codegenie/cache/`. The CLI offers to add
`.codegenie/` to the analyzed repo's `.gitignore` on first run.

Useful sub-commands:

- `codegenie gather --no-cache PATH` — force every probe to re-run
- `codegenie audit verify PATH` — re-validate the audit chain (S3-06)
- `codegenie gather --help` — global flag inventory

If any of the external tools listed in `docs/localv2.md §6` are missing
from `$PATH`, the CLI prints an actionable error and exits non-zero. Do not
try to monkey-patch the probe to "tolerate" a missing tool — fail loudly
(global rule 12).

The portfolio golden tests (`tests/golden/test_goldens_match.py`,
`tests/integration/portfolio/test_portfolio_sweep.py`) assert SCIP index
freshness, so they need `scip-typescript@0.4.0` on `$PATH`
(`npm install -g @sourcegraph/scip-typescript@0.4.0`). Without it they skip
loudly (`SKIPPED LOUD`) rather than fail; CI installs the pinned tool
itself.

## Adding a probe

The "extension by addition" rule is load-bearing: adding a probe is never
"edit existing code." It is "register one new class." The
`LanguageDetectionProbe` shipped in S4-01 (Phase 0) is the worked example
to copy.

Numbered recipe:

1. **File the issue first** — use the `New probe` template at
   `.github/ISSUE_TEMPLATE/new-probe.md`. Name the Planner decision your
   evidence supports; if you can't, the probe is premature.
2. **Write the failing tests first.** Create `tests/unit/test_<probe>.py`
   with a happy path, a failure mode, and a confidence-reporting assertion.
   The probe contract demands honest confidence.
3. **Declare the output schema** under
   `src/codegenie/schema/probes/<probe_name>.py`. Probe schemas use Pydantic
   v2 models. The output is **facts, not judgments** — no `safe_to_*`
   booleans, no `recommended_action` strings.
4. **Implement the probe class** under `src/codegenie/probes/<probe_name>.py`.
   Inherit from the ABC in `src/codegenie/probes/base.py`. Populate:
   - `declared_inputs` — file globs the probe reads (drives cache keys)
   - `applies_to_languages` — list, or `["*"]`
   - `applies_to_tasks` — list, or `["*"]`
5. **Register the probe.** Add `@register_probe` above the class.
   `src/codegenie/probes/__init__.py` imports register-side-effects;
   adding a probe never requires editing a central list.
6. **Validate the snapshot.** Run `pytest tests/unit/test_probe_contract.py`.
   If the probe widens the contract surface, that test fails — STOP. File
   an ADR amendment (template:
   `.github/ISSUE_TEMPLATE/adr-amendment.md`) before regenerating the
   snapshot. Per ADR-0007, drift is resolved by changing code, never by
   editing the spec.
7. **Round-trip a fixture.** Add a synthetic repo under `tests/fixtures/`
   that exercises the probe end-to-end via `codegenie gather`.

### Probe version bumps

(Resolves open question Q2 from
`phases/00-bullet-tracer-foundations/phase-arch-design.md`.)

Each probe class carries a `version: str` class attribute. The convention:

- **Patch bump** (`1.0.0 → 1.0.1`) — internal refactor, no output schema
  change, no cache-invalidation needed.
- **Minor bump** (`1.0.x → 1.1.0`) — output schema gains an OPTIONAL field.
  Old cache entries are still readable.
- **Major bump** (`1.x.y → 2.0.0`) — output schema breaks (renamed field,
  removed field, type change). Cache entries from the prior major version
  are invalidated at read time; an ADR is required.

Cache keys include the probe version. **Never** silently re-use the same
version after changing the output shape — stale `repo-context.yaml` files
in the wild will mis-merge.

### Adding a Layer B/C/D/E/G probe (Phase 2 additions)

Phase 2 (Layers B–G) introduces five additions on top of the Phase 0/1 recipe
above; the seven-step recipe still applies — these are *additions*, not
replacements. Use the named Phase 2 probes as canonical examples to copy.

1. **Heaviness annotation.** Pass `heaviness=` and `runs_last=` to
   `@register_probe(...)` (see Phase 2 ADR-0003). The coordinator sorts the
   non-prelude wave by heaviness; `runs_last=True` is for probes that must
   observe a fully-prepared workspace. Example: `IndexHealthProbe` (Layer B2,
   `src/codegenie/probes/layer_b/index_health.py`).

2. **`run_external_cli` vs `run_allowlisted`.** Layer B/G probes that shell
   out to an external CLI route through `codegenie.exec.run_external_cli` —
   the Layer B/G wrapper that adds timing + structured-event emission on top
   of Phase 0's `run_allowlisted`. Layer C probes (e.g. `RuntimeTraceProbe`,
   `src/codegenie/probes/layer_c/runtime_trace.py`) call `run_allowlisted`
   directly because they pass explicit hardening flags (capability drops,
   read-only roots) the wrapper does not model. Adding a binary to either
   path requires an ADR amendment to 02-ADR-0001. Example wrapped:
   `SemgrepProbe` (Layer G, `src/codegenie/probes/layer_g/semgrep.py`).

3. **`@register_index_freshness_check` Open/Closed seam.** If your probe
   answers "is this index fresh?", register a check at
   `codegenie.indices.freshness` via the decorator (02-ADR-0006). The
   `IndexHealthProbe` enumerates every registered check via the registry —
   no central edit needed. Example: `SkillsIndexProbe` registers a freshness
   check for `SkillsIndex` (Layer D,
   `src/codegenie/probes/layer_d/skills_index.py`).

4. **Typed `ProbeOutput.schema_slice` via Pydantic.** Output schemas under
   `src/codegenie/schema/probes/<probe>.py` are Pydantic v2 models with
   `model_config = ConfigDict(frozen=True, extra="forbid")`. **Do not call
   `model_construct`** anywhere under `src/codegenie/output/` — the
   `forbidden-patterns` pre-commit hook bans it; validation must always run
   at the writer chokepoint (02-ADR-0010). Example: `ConventionsProbe`
   (Layer D, `src/codegenie/probes/layer_d/conventions.py`).

5. **`declared_inputs` cache keys.** Globs cover most cases; special tokens
   (e.g. `image-digest:` per 02-ADR-0004) ride alongside file globs and are
   resolved by the coordinator's snapshot system. Cache keys derive
   deterministically from `declared_inputs` + probe version. Example with
   special token: `RuntimeTraceProbe`.

6. **Confidence is a fact, not a judgment.** Every `ProbeOutput.confidence`
   is `"high" | "medium" | "low"` based on observed evidence — never an
   editorialized recommendation. The Planner consumes confidence; probes
   never editorialize. `IndexHealthProbe` derives confidence from the
   `IndexFreshness` sum-type variant (Fresh → `"high"`, Stale → `"low"`).

7. **Canonical probe examples (copy these).** `IndexHealthProbe` (Layer B2,
   the load-bearing probe), `RuntimeTraceProbe` (Layer C, sandboxed
   subprocess + `image_digest_resolver`), `SemgrepProbe` (Layer G, external
   CLI via `run_external_cli`), `SkillsIndexProbe` (Layer D, registers a
   freshness check), `ConventionsProbe` (Layer D, typed slice + Open/Closed
   loader). Each lives under `src/codegenie/probes/layer_<letter>/`.

## Project conventions

### Coverage ratchet (resolves open question Q5)

The repo enforces line / branch coverage thresholds via
`--cov-fail-under` in `pyproject.toml`. The ratchet schedule is:

| Phase    | Line | Branch | Notes |
|----------|-----:|-------:|-------|
| Phase 0  |  85  |   75   | `85/75` — current gate. |
| Phase 1  |  87  |   77   | Bumps to `87/77` when Phase 1's first probe lands. |
| Phase 2  |  90  |   80   | Bumps to `90/80`. Frozen thereafter until Phase 5. |

The `--cov-fail-under=85` line in `pyproject.toml` carries a comment
mirroring this schedule so a contributor editing the gate sees the table.
Do **not** raise the gate ahead of the schedule — coverage is a floor, not
a goal, and ad-hoc bumps create one-PR pain that gets reverted.

### Probe contract is frozen

The probe ABC in `src/codegenie/probes/base.py` and the snapshot
`tests/snapshots/probe_contract.v1.json` are governed by **ADR-0007**.
Drift between the runtime ABC and the snapshot is resolved by **changing
code, never by editing the spec**. If you must widen the contract:

1. File an issue with the `ADR amendment` template.
2. Wait for the amendment text to be approved.
3. Open a PR using the repo's PR template at `templates/adr-amendment.md`.
4. Regenerate the snapshot using `scripts/regen_probe_contract_snapshot.py`.

### Structural defense tests (`tests/fence/`)

Three fences pin invariants of the *composition*, not behaviours of a
single module. They catch classes of bugs that unit tests routinely miss
because unit tests verify one module at a time against its declared
interface, not against what the runtime composition actually wires up.

- **Adding a new submodule under `src/codegenie/`?**
  `tests/fence/test_per_submodule_cold_start.py` spawns a fresh subprocess
  for every importable submodule. A new circular import — even one that
  pytest never trips because its shared interpreter has primed sys.modules
  — fires this fence. If your new module is in the
  `_KNOWN_BROKEN_PRE_FIX` skip set, it's blocked on a tracked fix; do not
  add to that set without an explicit reason.
- **Adding a new attribute to `ProbeContext`?**
  `tests/fence/test_probe_context_conformance.py` asserts the
  coordinator-built ctx (`BudgetingContext`) carries every attribute on
  the frozen `ProbeContext` surface. Forget to thread your new attribute
  through `_make_probe_context` and the fence fires before a probe
  silently `AttributeError`s at runtime.
- **Modifying a probe to read a new ctx attribute or use a new code
  path?** The smoke test `test_no_probe_errors_in_smoke_run_record` runs
  a real gather against the `polyglot` fixture and asserts no probe
  reports `exit_status="error"`. Coordinator failure-isolation otherwise
  hides AttributeError-class drift; this assertion surfaces it.

These three were added 2026-05-19 after a probe-context drift and a
plugins.manifest circular-import surfaced in end-to-end testing. The
discipline: **structural defenses are cheap to add and cheap to run; the
moment a class of bug shows up in production, write the fence that would
have caught it.**

### Extension by addition — what counts as an edit

Extension by addition means **no *silent* edits**, not "no edits"
([ADR-0043](production/adrs/0043-extension-by-addition-means-no-silent-edits.md)).
An edit is a violation only when it changes existing behaviour *silently*.
Edits the compiler or a snapshot test fully polices are the enforcement
mechanism, not violations — these are always safe and need no special
ceremony:

- Adding a member to a closed `Literal` / `Enum`.
- Adding a field to a frozen struct or a new `$ref` to a schema envelope.
- Adding an import line to an explicit-import collection point
  (`probes/__init__.py`, the language registry, etc.).
- Adding a new file (probe, plugin, adapter, `LanguagePack`).

**No per-phase allowlists.** Phase 7's byte-edit allowlist (Phase 7
ADR-0009) is the *last* enumerated per-phase list — no future phase adds
one. A surface that must be protected is a **contract with a snapshot
test**, following the probe-ABC pattern (`tests/unit/test_probe_contract.py`
diffs the runtime ABC against `probe_contract.v1.json`): the file stays
freely editable, and the snapshot test fails iff the frozen contract
changed. Files and components are not frozen — contracts are. This is a
forward rule; existing Phase 0–7 surfaces are not retrofitted.

**Freeze discipline.** Freeze only *narrow* contracts — never broad
components. Freeze only when *earned* (a surface that has survived ~3
phases of use unchanged), or state plainly why an early freeze is
necessary. Freeze *provisionally*: a freeze ADR uses `Provisional
Accepted` with a `Review trigger` (see §ADR lifecycle).

**Migrations.** A genuinely cross-cutting change to existing code — a
security fix across every probe, a logging-format change, a new required
field — is a **migration**: a loud, reviewed, all-at-once horizontal
sweep, explicitly labelled as such in the PR. A migration is *not* a
silent edit; it is gated by the conformance suite (`tests/conformance/`)
and golden files, regenerated deliberately, in a single reviewed pass.
Use a migration — or generalise the existing component — rather than
forking a near-duplicate to avoid touching the original.

### ADR lifecycle

Production ADR statuses are `Proposed`, `Accepted`, `Provisional Accepted`, `Deferred`, and `Superseded`.

- Use **`Provisional Accepted`** only when the direction is binding now but a named future evidence point remains. The ADR must include `**Review trigger:**` and say what evidence will promote or retire it.
- When a decision replaces an older one, use reciprocal links: the older ADR becomes `Superseded by ADR-NNNN`, and the successor includes `**Supersedes:** ADR-MMMM`.
- In the issue and PR, state what changed, why the older claim no longer holds, and what evidence supports the new posture.

### Pre-commit hooks

`.pre-commit-config.yaml` runs `ruff`, `ruff format`, and `mypy` on
staged files. SHA-pinned for reproducibility. Run `pre-commit install`
once after `make bootstrap`; CI re-runs the same checks via `make check`
so the hook is convenience, not gate.

### `egress_test_loopback` fixture (Phase-4 S3-03)

The repo-root [`sitecustomize.py`](../sitecustomize.py) installs
`EgressGuard` (`src/codegenie/fallback/leaf/egress_guard.py`) at every
interpreter start — including every `pytest` run. The guard wraps
`socket.create_connection` and rejects any host other than
`api.anthropic.com:443`, **including** loopback (`127.0.0.1`, `::1`,
`localhost`). Per ADR-0006 §Decision: there is no env-var, no boolean
parameter, and no module constant that widens the allowlist.

A test that genuinely needs to dial a loopback listener (binds a
throwaway socket on an ephemeral port and connects to it) must request
the **`egress_test_loopback`** fixture, defined in
[`tests/conftest.py`](../tests/conftest.py):

```python
def test_my_local_listener(egress_test_loopback):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    # socket.create_connection(("127.0.0.1", listener.getsockname()[1])) admitted
```

The fixture sets a thread-scoped `contextvars.ContextVar` to `True` and
resets it on teardown. A `threading.Thread` spawned during the test runs
in an empty `Context`, so the flag is invisible to it — concurrent
workers stay blocked (the AC-8 isolation guarantee, for free). Do **not**
request the fixture for tests that monkeypatch the socket layer or use
mocks; those tests never reach the wrapper.

### Phase-4 adversarial suite (`phase04_adv` marker)

Adversarial tests for Phase 4 (egress guard, prompt-fence, cassette
discipline) live under [`tests/adv/phase04/`](../tests/adv/phase04/) and
carry the `phase04_adv` pytest marker — mirroring the `phase02_adv`
precedent. Both markers are CI-gating; `make test` runs them by default.

### CI matrix

The six required jobs (all must pass on Python 3.11 AND 3.12 before merge):

- `lint` — `ruff check` + `ruff format --check` + `lint-imports`
- `typecheck` — `mypy --strict src/`
- `test` — `pytest` + coverage gate (see ratchet above)
- `security` — `pip-audit`
- `docs` — `mkdocs build --strict` over the curated `nav`
- `fence` — the LLM-in-gather fence (ADR-0002)

## See also

- `docs/roadmap.md` — phased plan from local POC to production
- `docs/localv2.md` — canonical local POC spec
- `docs/production/README.md` — canonical production-target reference
- `docs/phases/00-bullet-tracer-foundations/README.md` — Phase 0 exit criteria and handoff record
