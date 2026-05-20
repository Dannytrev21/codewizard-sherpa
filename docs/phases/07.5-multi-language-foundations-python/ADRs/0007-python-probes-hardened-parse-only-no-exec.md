# ADR-0007: Python manifest/lockfile probes are parse-only, byte/depth/timeout-capped; `setup.py` is never executed

**Status:** Accepted
**Date:** 2026-05-20
**Tags:** Functional core, imperative shell · hard-caps · no-exec · honest-confidence · security
**Related:** [ADR-0008](0008-python-depgraph-pure-parsing-no-resolution.md), [ADR-0009](0009-requirements-txt-directive-language-parsing-contract.md), [ADR-0004](0004-python-detection-as-base-tier-probe-not-prepass.md), [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)

_Note: the dep-graph purity decision is [ADR-0008](0008-python-depgraph-pure-parsing-no-resolution.md) and the `requirements.txt` directive contract is [ADR-0009](0009-requirements-txt-directive-language-parsing-contract.md); this ADR governs the Python manifest/build-system probes._

## Context

Python is the first non-Node target language, and its manifest surface crosses the untrusted-repo trust boundary (TB-2 in [final-design.md §Data flow](../final-design.md#data-flow)). Python manifests are *not* benign data:

- **`setup.py` is arbitrary executable Python** — RCE-on-execution. A hostile repo whose only manifest is a `setup.py` calling `os.system(...)` is a real, common shape. The performance lens design omitted `setup.py` entirely; the critic caught it ([critique.md §Things this design missed that a different lens caught](../critique.md)).
- **Lockfiles can be weaponized** — a 200 MB `poetry.lock` or a billion-laughs TOML/JSON bomb can OOM or hang the gather process if parsed naively.

The codebase already ships the right machinery: the Phase 1 `SizeCapExceeded` / `DepthCapExceeded` / `SymlinkRefusedError` cap classes that `LanguageDetectionProbe` already raises. The question was whether the Python probes reuse that machinery and parse structurally, or take the easy path the performance benchmark implicitly assumed (already-resolved lockfiles, no `setup.py`). The security lens supplied the parse-only / byte-capped / no-exec discipline; the synthesis folds it in verbatim (CONFLICT CR-4).

## Options considered

- **Option A — execute `setup.py` to read its metadata** (the conventional pip approach). **Pattern:** none — it is RCE on a hostile repo; categorically rejected.
- **Option B — parse manifests naively, no caps.** Read `pyproject.toml` / lockfiles with no byte or depth limit. **Pattern:** none — a 200 MB lockfile OOMs the gather process.
- **Option C — parse-only, structural, with hard caps before parse.** `setup.py`/`setup.cfg` read as text and parsed structurally (tree-sitter / INI); every parser enforces a byte cap, a depth/entry cap, and a per-probe timeout *before* parsing, reusing the Phase 1 cap machinery; a probe at a cap returns a partial fact with `confidence="low"` and a `_WARNING_IDS` entry. **Pattern:** Functional core, imperative shell + honest-confidence.

## Decision

Every Python manifest/build-system probe (`PythonProjectProbe`, `PythonBuildSystemProbe`, `PythonManifestProbe`, `PythonImportGraphProbe`) is **parse-only**. `setup.py` / `setup.cfg` are **read as text and parsed structurally** — tree-sitter for `setup.py`, INI for `setup.cfg` — and **never executed**. Every parser enforces a **byte cap, a parse-depth/entry cap, and a per-probe timeout *before* parsing**, reusing the Phase 1 `SizeCapExceeded` / `DepthCapExceeded` / `SymlinkRefusedError` machinery. A probe at a cap returns a **partial fact with `confidence="low"`** and a `_WARNING_IDS` entry (`python.manifest_oversized`, `python.lockfile_truncated`, `python.setup_py_not_static`). A repo whose only manifest is a hostile `setup.py` yields a `confidence="low"` "not statically analyzable" fact. The probes are **functional core / imperative shell** — pure parsing helpers, `run()` the only impure surface, and it only *reads*. An AST test forbids `exec` / `eval` / `importlib`-of-a-repo-file anywhere in the Python probe code. The unverified `1.15×`-parity numeric gate from the performance lens is **dropped** — a guessed ceiling against a non-existent baseline with no test that would catch a breach.

## Tradeoffs

| Gain | Cost |
|---|---|
| `setup.py` RCE is structurally impossible — it is read as text, never executed; an AST test proves the probe code contains no `exec`/`eval`/`importlib`-of-repo-file | A `setup.py`-only repo yields only a `confidence="low"` "not statically analyzable" fact — Python metadata that lives *only* in dynamic `setup.py` code is not recovered |
| A 200 MB or billion-laughs lockfile is rejected *before parse* — no OOM, no hang — reusing proven Phase 1 cap machinery | Caps are pre-parse, so a legitimately-large manifest is also rejected at the cap — the cap value is a tuning choice that may need revisiting |
| A probe at a cap returns an honest partial fact with `confidence="low"` — honest-confidence over completeness (commitment 3) | Completeness on adversarial inputs is explicitly sacrificed — a capped probe under-reports, by design |
| Reuses the Phase 1 cap machinery — no new cap framework, the Python probes inherit a tested boundary | The Python probes must correctly *wire* the existing caps before parse — a probe that parses first and caps second defeats the protection |
| Dropping the `1.15×` gate removes a chronically-flaky CI gate against a baseline that does not exist | There is no hard numeric ceiling on Python gather cost — replaced by a `sys.modules` fence + "within `make check`'s envelope" |

## Pattern fit

The toolkit's **functional core, imperative shell** is the load-bearing discipline: the parsing logic is pure helper functions (testable with no I/O), and `run()` is the only impure surface — and it only *reads*, never writes or executes. This is what makes "never executes `setup.py`" a structural property rather than a hope: a pure parser *cannot* execute the file it parses; the AST test that forbids `exec`/`eval`/`importlib`-of-repo-file is the fence that keeps the core pure. The hard-caps-before-parse discipline is the security lens's contribution and it is not a "pattern" so much as a boundary invariant — the cap is checked at the trust boundary (TB-2) before any attacker-controlled bytes reach a parser. The honest-confidence behavior (a capped probe returns `confidence="low"`, not a crash or a silent omission) is production commitment 3 — "silent staleness is the worst failure mode" — applied at the probe level.

## Consequences

- A hostile `setup.py` (`os.system`, `subprocess`, `__import__`) is read as text; the dynamic call is observed *as a fact* ("not statically resolvable", `confidence="low"`) — never executed (edge case #5, [phase-arch-design.md §Edge cases](../phase-arch-design.md#edge-cases)).
- An oversized or billion-laughs lockfile is rejected before parse with a structured `_WARNING_IDS` entry — no OOM, no hang (edge case #4).
- The `forbidden-patterns` pre-commit hook plus a probe-specific AST test enforce no `exec`/`eval`/`importlib`-of-repo-file in the Python probe code — a CI-blocking structural proof.
- Python probe `declared_inputs` are tight globs (`pyproject.toml`, `requirements*.txt`, `Pipfile*`, `*.lock`, `**/*.py`) so the content-addressed cache invalidates surgically — editing a Python file leaves every Node probe's cache valid.
- The performance regression surface is two *checkable* claims (a `sys.modules` fence; "within `make check`"), not a guessed `1.15×` gate — no chronically-flaky CI gate is introduced.
- Adversarial fixtures (hostile `requirements.txt`, oversized lockfile, hostile `setup.py`) are first-class conformance cases — "fails closed" is part of *passing* ([ADR-0010](0010-conformance-tier-parameterized-over-live-registry.md)).

## Reversibility

**Low.** The no-exec discipline is non-negotiable — executing `setup.py` is RCE on a hostile repo, and reversing it is not a design option, it is a vulnerability. The cap *values* are tunable (Medium reversibility on the numbers), but caps-before-parse as a discipline is a fixed trust-boundary invariant. The structural choice (parse-only, functional core) is durable because it is what makes the security property provable; reverting to execution-based metadata extraction would require a fundamentally different, sandboxed architecture and is out of scope for every foreseeable phase.

## Evidence / sources

- [final-design.md §Components — Python Layer A/B probes](../final-design.md#components), §Synthesis ledger CR-4, §Failure modes & recovery, §Test plan (adversarial)
- [phase-arch-design.md §Component design — Python Layer A/B probes](../phase-arch-design.md#component-design), §Edge cases #4 and #5, §Agentic best practices (tool-use safety)
- [critique.md §Things this design missed that a different lens caught](../critique.md) — `setup.py` as arbitrary executable code; §Synthesis CR-4 (1.15× gate dropped)
- [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md) — deterministic gather; [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) — the probe contract reused
- Phase 1 `SizeCapExceeded` / `DepthCapExceeded` / `SymlinkRefusedError` cap machinery
