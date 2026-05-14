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

### Pre-commit hooks

`.pre-commit-config.yaml` runs `ruff`, `ruff format`, and `mypy` on
staged files. SHA-pinned for reproducibility. Run `pre-commit install`
once after `make bootstrap`; CI re-runs the same checks via `make check`
so the hook is convenience, not gate.

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
