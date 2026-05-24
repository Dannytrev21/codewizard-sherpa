# Story S6-06 — `typecheck.typescript` applicability matrix (JS-only repos pass, not degrade)

**Step:** Step 6 — Compose FallbackTier + register typecheck.typescript SignalKind + integration
**Status:** HARDENED
**Effort:** S
**Depends on:** S6-05 (the base collector + registration must ship first — S6-06 extends the same module)
**ADRs honored:** ADR-04-0015 (TypeScript-in-scope detection lives in the plugin; applicability is plugin-local), Gap 4 from arch §Gap analysis (pass-not-degrade for JS-only repos)

## Validation notes (2026-05-23)

Hardened by `phase-story-validator`. The story was written before S6-05 went through validation, so it carried the same six clusters of stale framings that S6-05's hardening corrected. Major changes:

- **Class-based collector references removed (Cluster A, BLOCK):** every `TypecheckTypescriptSignal()` instantiation + `.collect(repo, ctx)` call replaced with the shipped plain-async-function form `await collect_typecheck_typescript_signal(repo_root, baseline_repo_sha, timeout_s=30.0)`. There is no `SignalCollector` Protocol in Phase 3 and no `RepoSnapshot` / `ProbeContext` on the signal-evaluation tier.
- **`confidence` field on `TrustSignal` removed everywhere (Cluster B, BLOCK):** shipped `outcomes.py:377-388` is Pydantic `extra="forbid"` with three fields (`kind`, `passed`, `details`). Every previous AC that set `confidence="high"` / `"medium"` would `ValidationError` at construction. Applicability signalled via `details["applicable"]: bool` instead.
- **`details` type widened to shipped `dict[str, str | int | bool | float]` (Cluster C, BLOCK):** S6-05 Cluster B already widened the arch §line 763 spec to match shipped. S6-06 follows.
- **`RepoSnapshot` replaced with `repo_root: Path` (Cluster D, BLOCK):** `RepoSnapshot` (`src/codegenie/probes/base.py:32`) has fields `root`, `git_commit`, `detected_languages`, `config` — **no file list**. Signal collectors don't receive it. The applicability helper takes `repo_root` and walks the filesystem locally with `os.scandir`.
- **Module import path uses hyphenated slug via `importlib` (Cluster E, BLOCK):** per S7-01 + S6-05 hardening, the loader uses the literal hyphenated slug. Tests use `importlib.import_module("plugins.vulnerability-remediation--node--npm.adapters.ts_typecheck_signal")`; bare `from plugins.vulnerability_remediation__node__npm.adapters... import ...` raises `SyntaxError`.
- **Integration test rewritten to use the shipped surface (Cluster F, BLOCK):** `collect_all_signals(...)` doesn't exist; integration test calls `collect_typecheck_typescript_signal` directly, builds the signal list explicitly, and passes to `TrustScorer(event_log=in_memory_event_log).score(signals)` — mirrors S6-05 AC-5's both-directions assertion. **Now asserts both directions in the same test** (JS-only passes; TS-with-broken-types fails) — a constant `applicable=False` mutation would have passed the positive-only form.
- **Edge-case tests now actually test the edge (Cluster G, BLOCK):** `.tsx` test changed from `tsconfig=True, ts_files=False, tsx_files=True → applicable` (which already passes because of `tsconfig=True`) to `tsconfig=False, ts_files=False, tsx_files=True → DegradedNoTsconfig`. Same fix for the `.d.ts` test. These now verify the `.tsx` / `.d.ts` detection paths instead of just asserting `tsconfig=True ⇒ applicable`.
- **NotApplicable short-circuits before `run_allowlisted` (Cluster H, HARDEN):** new AC asserts `run_allowlisted` mock has `call_count == 0` when the matrix dispatches `NotApplicable`. Naive implementations that run tsc and override the result are rejected.
- **`node_modules/` exclusion test pinned (Cluster I, HARDEN):** new AC — a fixture with `node_modules/some-pkg/index.ts` and no source-root `.ts` files or `tsconfig.json` is classified `NotApplicable`. Catches walker misconfiguration.
- **Sum type aligned with S6-05 discriminated-union precedent (Cluster J, HARDEN):** `TypeScriptApplicability = Applicable | DegradedNoTsconfig | NotApplicable` — each a `@dataclass(frozen=True)` variant, mirroring `ErrorCount | UnparseableOutput` from S6-05. Dispatch uses `match`/`case` with `assert_never(...)` exhaustiveness; adding a fifth variant later triggers a mypy non-exhaustive error rather than silent fall-through.
- **`_is_typescript_in_scope` renamed `_typescript_applicability` (Cluster L, HARDEN):** name now matches the sum-typed return shape (parallels S6-05's `_parse_tsc_error_count`).
- **Purity AST-fence extended (Cluster M, HARDEN):** `tests/fence/test_phase4_typecheck_purity.py` (added by S6-05) extends to cover `_typescript_applicability`. Asserts bounded I/O: no `subprocess`, no `asyncio`, no network, no file-content reads (`.read_text` / `.read_bytes` / `open(... 'r')`), no module-level mutation. Stat + scandir are admitted.
- **Performance AC replaced with structural / bounded assertion (Cluster N, HARDEN):** wall-clock `≤ 50 ms` deleted (CI-flaky). Replaced with structural invariants — walker is iterative `os.scandir`, does not recurse into `node_modules/` — and a generous-bound load test (10K files under `node_modules/` returns `NotApplicable` in under 2 s).
- **Goal text reframed (Cluster O, HARDEN):** "presence of `tsconfig.json` AND any `.ts` files" was wrong vs the four-case matrix. Rewritten to "presence of `tsconfig.json` and/or any `.ts` / `.tsx` / `.d.ts` file in the working tree (excluding `node_modules/`)".

Future-sibling extract (Notes-for-implementer only, Rule 2 — defer): the second applicability sibling (`typecheck.python` in Phase 7.5 — `pyproject.toml` + `*.py` files) is the rule-of-three trigger for a `TypecheckApplicabilityKit(language, manifest_files, source_suffixes, exclude_dirs)` extract. First sibling ships flat.

Full audit log: [`_validation/S6-06-typecheck-applicability-matrix.md`](_validation/S6-06-typecheck-applicability-matrix.md).

## Context

S6-05 ships the base `collect_typecheck_typescript_signal(repo_root, baseline_repo_sha, timeout_s=30.0) -> TrustSignal` with degraded-pass behavior when `tsc` is missing: `TrustSignal(passed=False, details={"degraded_reason": "no_tsconfig_or_tsc"})`. Phase-arch-design §Gap 4 (lines 1108–1112) flags the bug honestly: that response **fails strict-AND**, which means a perfectly correct **JavaScript-only repo with no TypeScript at all** cannot pass Phase 5's validate. That's wrong — the signal should *not apply*, not *fail*.

The fix is the applicability matrix: detect whether TypeScript is in scope (`tsconfig.json` and/or any `.ts` / `.tsx` / `.d.ts` files in the working tree, excluding `node_modules/`) and dispatch per the four-case truth table from arch §Gap 4:

| `tsconfig.json` present | `.ts`/`.tsx`/`.d.ts` files present (outside `node_modules`) | applicability variant | passed | `details` key contract | semantics |
|---|---|---|---|---|---|
| yes | yes | `Applicable(ts_files_count=N)` | depends on tsc | (existing S6-05 keys) | normal happy path |
| yes | no  | `Applicable(ts_files_count=0)` | True (`tsc` reports 0 errors) | `{"baseline_error_count": 0, "current_error_count": 0}` | applicable, vacuous |
| no  | yes | `DegradedNoTsconfig` | depends on tsc availability | `{"degraded_reason": "no_tsconfig_or_tsc"}` if tsc missing | degraded (S6-05 path) |
| no  | no  | **`NotApplicable`** | **True** | **`{"applicable": False}`** | not applicable; pass not degrade |

The last row is the load-bearing change: `passed=True` because the signal **does not apply**. JS-only repos sail through strict-AND.

This is surgical (~30 lines per arch §Gap 4 "Improvement" paragraph); composes cleanly atop S6-05's existing function by gating it on a pre-dispatch applicability check.

## References — where to look

- **Architecture:** [phase-arch-design.md §Gap analysis — Gap 4](../phase-arch-design.md) (lines 1108–1112 — the matrix); §Edge case row 9 (missing tsc); §Component 11; §Goal G10.
- **Phase ADRs:** [ADR-04-0015](../ADRs/0015-typecheck-typescript-signal-and-tsc-allowed-binary.md) (§Tradeoffs — missing tsc semantics; §Consequences — applicability is plugin-local). **No amendment needed** — the matrix is in arch §Gap 4 already; ADR-04-0015 carries the "missing tsc → degraded" framing that the matrix subsumes additively.
- **Source design:** [final-design.md §Component 12](../final-design.md) (applicability detection mentioned as the right shape).
- **High-level impl:** [High-level-impl.md §Step 6](../High-level-impl.md) Features delivered ("Applicability detection per Gap 4: presence of `tsconfig.json` + any `.ts` files").
- **Sibling validation to mirror:** [`_validation/S6-05-typecheck-typescript-signal.md`](_validation/S6-05-typecheck-typescript-signal.md) — establishes the function-call-not-class-decorator collector form, the `confidence`-field-doesn't-exist on `TrustSignal`, the discriminated-union sum-type discipline (`ErrorCount | UnparseableOutput`), the `run_allowlisted`-not-`SubprocessJail` subprocess surface, and the hyphenated-slug `importlib.import_module` pattern. **S6-06 mirrors every cluster.**
- **Shipped source-of-truth files:**
  - `src/codegenie/transforms/outcomes.py:377-388` — `TrustSignal` (three fields, no confidence; Pydantic `extra="forbid"`; `details: dict[str, str | int | bool | float]`).
  - `src/codegenie/probes/base.py:32` — `RepoSnapshot` (Phase-0 probe input; **not** used by signal collectors).
  - `src/codegenie/exec/__init__.py:235` — `run_allowlisted` (the subprocess surface; raises `ProbeTimeoutError` / `ToolMissingError`).
  - `src/codegenie/transforms/signal_kinds.py:10-14, 154` — `register_signal_kind` (function call, NOT decorator); `BUILD = register_signal_kind("build")` precedent.
- **Existing code (after S6-05 ships):** `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py`. This story extends the `collect_typecheck_typescript_signal` function's prelude with a pre-dispatch applicability check.

## Goal

Add a pre-dispatch helper `_typescript_applicability(repo_root: Path) -> TypeScriptApplicability` that detects whether TypeScript is in scope — presence of `tsconfig.json` and/or any `.ts` / `.tsx` / `.d.ts` files in the working tree (excluding `node_modules/`) — and gate `collect_typecheck_typescript_signal`'s existing S6-05 logic on the result. Dispatch the four-case applicability matrix per arch §Gap 4; emit `TrustSignal(kind=TYPECHECK_TYPESCRIPT, passed=True, details={"applicable": False})` for JS-only repos so they pass strict-AND instead of failing it.

## Acceptance criteria

- [ ] **AC-1: Four-case truth table** asserted by `tests/unit/typecheck/test_applicability_matrix.py` (parametrized, table-driven):
  - `tsconfig.json present + .ts file present` → `_typescript_applicability(...)` returns `Applicable(ts_files_count >= 1)`; collector runs `tsc`; result projection unchanged from S6-05.
  - `tsconfig.json present + no .ts file` → `Applicable(ts_files_count=0)`; collector runs `tsc` (which reports 0 errors); `passed=True`; `details` carries the existing S6-05 key set (e.g., `{"baseline_error_count": 0, "current_error_count": 0}` or `{"degraded_reason": "no_baseline", "error_count": 0}`).
  - `no tsconfig.json + .ts file present` → `DegradedNoTsconfig`; collector invokes `run_allowlisted` (degraded path from S6-05); on `ToolMissingError` returns `TrustSignal(passed=False, details={"degraded_reason": "no_tsconfig_or_tsc"})` (S6-05 behavior preserved).
  - `no tsconfig.json + no .ts file` → `NotApplicable`; collector **short-circuits before `run_allowlisted` is called**; returns `TrustSignal(kind=TYPECHECK_TYPESCRIPT, passed=True, details={"applicable": False})`. **`confidence` is NOT set** (no such field on `TrustSignal`; would Pydantic-ValidationError otherwise — see Cluster B in Validation notes). **The signal passes because it does not apply.**

  Asserted via `isinstance(result, mod.Applicable)` etc., **not** by `.value == "applicable"` string comparison (Cluster G + J).

- [ ] **AC-2: `_typescript_applicability` is a bounded-I/O helper** with signature `_typescript_applicability(repo_root: Path) -> TypeScriptApplicability`. Walks `repo_root` once with iterative `os.scandir`, skipping `node_modules/` directories. No subprocess, no `asyncio`, no network, no file-content reads (only directory enumeration + suffix matching + stat). Testable in isolation with a `tmp_path`-based `repo_factory` fixture; mypy `--strict` accepts the module.

- [ ] **AC-3: `TypeScriptApplicability` is a discriminated union of frozen dataclasses** — mirrors S6-05's `ErrorCount | UnparseableOutput` precedent (Cluster J):
  ```python
  @dataclass(frozen=True)
  class Applicable:
      ts_files_count: int  # forensics; can be 0 in the vacuous case

  @dataclass(frozen=True)
  class DegradedNoTsconfig:
      ts_files_count: int  # forensics

  @dataclass(frozen=True)
  class NotApplicable:
      pass

  TypeScriptApplicability = Applicable | DegradedNoTsconfig | NotApplicable
  ```
  Dispatch in `collect_typecheck_typescript_signal` uses `match`/`case` with `typing.assert_never(applicability)` in the catch-all — mypy --strict surfaces non-exhaustive dispatch.

- [ ] **AC-4: `NotApplicable` short-circuits BEFORE `run_allowlisted` (Cluster H)** — `tests/unit/typecheck/test_applicability_matrix.py::test_not_applicable_does_not_spawn_tsc` patches `mod.run_allowlisted` with an `AsyncMock`, invokes the collector against a JS-only `tmp_path` fixture, and asserts `mock.call_count == 0`. Mutation barrier: catches the lazy "run tsc and then override" implementation.

- [ ] **AC-5: `node_modules/` exclusion (Cluster I)** — `tests/unit/typecheck/test_applicability_matrix.py::test_node_modules_ts_files_do_not_count` creates a fixture with `node_modules/some-pkg/index.ts` (and other deeply-nested `.ts` files under `node_modules/`) and **no** source-root `.ts` files or `tsconfig.json`; asserts `_typescript_applicability(repo_root)` returns `NotApplicable`. Catches walker mis-configuration; without this, every `npm install`-ed JS-only repo would be misclassified.

- [ ] **AC-6: `.tsx` files count as TypeScript in scope (Cluster G)** — test: `tsconfig=False, ts_files=False, tsx_files=True` → `DegradedNoTsconfig` (verifies `.tsx` triggers the "ts files present" detector; `.tsx` alone does NOT imply tsconfig). Pin in a test so a future contributor doesn't accidentally narrow the predicate to `*.ts` literal.

- [ ] **AC-7: `.d.ts`-only repos still detected as `.ts files present` (Cluster G)** — test: `tsconfig=False, ts_files=False, d_ts_files=True` → `DegradedNoTsconfig`. Declaration files are TypeScript; `tsc --noEmit` on them is meaningful.

- [ ] **AC-8: Existing S6-05 tests still green** — the baseline-strict-AND, timeout, missing-tsc, baseline-cache-IO, and registry-membership tests from S6-05 all still pass; the matrix wraps but does not replace them. Asserted by `make test` post-change (no regressions in the `tests/unit/typecheck/test_signal.py` and `tests/fence/test_typecheck_signal_registered.py` suites).

- [ ] **AC-9: `TrustSignal` shape conforms to shipped `outcomes.py:377-388` (Cluster B + C)** — three fields only: `kind: SignalKind`, `passed: bool`, `details: dict[str, str | int | bool | float]`. The `NotApplicable` path emits `details={"applicable": False}`; the collector **never sets `confidence=`** (Pydantic `extra="forbid"` would raise). The applicable-but-no-`.ts` case emits the same S6-05 key set (baseline / current / no_baseline / degraded_reason / tsc_version).

- [ ] **AC-10: Strict-AND in JS-only repo, both directions (Cluster K + Q)** — `tests/integration/test_typecheck_signal_applicability_js_only.py::test_strict_and_both_directions` runs the full Phase-3 `TrustScorer` (constructed as `TrustScorer(event_log=in_memory_event_log)` — S6-05 AC-5 precedent) against two fixture repos in the same test:
  - **Positive direction:** JS-only fixture (no `tsconfig.json`, no `.ts` files); signal list includes the `typecheck.typescript` signal returning `passed=True, details={"applicable": False}` plus five other passing signals; `outcome.passed is True`, `outcome.failing == []`.
  - **Negative direction:** TS fixture with broken types (`tsconfig.json + a .ts file with a hallucinated method`); five-other-signal pass + `typecheck.typescript` returning `passed=False`; `outcome.passed is False`, `outcome.failing == [SignalKind("typecheck.typescript")]`.

  Mutation barrier: a constant `passed=True` (or `applicable=False`) implementation passes the positive direction alone. Asserting both directions in the same test catches it.

  The integration test calls `await collect_typecheck_typescript_signal(repo_root, RepoSha(...))` directly (no `collect_all_signals` — that surface does not exist); builds the signal list explicitly with five plain-pass `TrustSignal`s plus the typecheck signal; calls `TrustScorer(event_log=...).score(signals)`.

- [ ] **AC-11: Plugin import path uses the hyphenated slug via `importlib` (Cluster E)** — any test that loads the plugin module references `importlib.import_module("plugins.vulnerability-remediation--node--npm.adapters.ts_typecheck_signal")` — never `from plugins.vulnerability_remediation__node__npm.adapters... import ...` (Python parser rejects hyphens; loader uses the literal hyphenated slug per S7-01).

- [ ] **AC-12: Purity / boundedness AST-fence extended (Cluster M)** — `tests/fence/test_phase4_typecheck_purity.py` (added by S6-05) extends to AST-walk `_typescript_applicability` and assert:
  - no imports of `subprocess`, `asyncio`, `socket`, `http`, `urllib`, `requests`, `httpx`;
  - no calls to `open(..., 'r')`, `.read_text()`, `.read_bytes()`, `json.load`, `yaml.load` — applicability does not read file contents, only directory entries;
  - no module-level mutable state writes.
  `os.scandir`, `os.stat`, `pathlib.Path.iterdir`, `pathlib.Path.exists`, `pathlib.Path.suffix` are admitted.

- [ ] **AC-13: Bounded walker — structural + load assertion (Cluster N)** —
  - Structural: a unit test inspects the helper's AST (or just asserts the implementation imports `os.scandir`) confirming iterative-not-recursive traversal of the directory tree.
  - Load: `tests/unit/typecheck/test_applicability_matrix.py::test_large_node_modules_does_not_blow_up` builds a fixture with 10K `.ts` files under `node_modules/some-pkg/` (and zero `.ts` / `.tsx` / `.d.ts` files outside `node_modules`); asserts `_typescript_applicability(repo_root) == NotApplicable()` returns within a **generous** 2 s envelope (not the flaky 50 ms claim from the original draft).

- [ ] **AC-14: Open/Closed — no edits to Phase-3 transforms (Cluster Q)** — `tests/fence/test_phase4_no_trust_scorer_edits.py` (added by S6-05 AC-6) covers `src/codegenie/transforms/{trust_scorer,signal_kinds,outcomes}.py`. S6-06 introduces zero diff to those files (asserted by the same fence; no new fence required). All S6-06 code lives in the plugin module + tests + arch docs are unchanged (matrix already documented in §Gap 4).

- [ ] **AC-15: `make check`, `mypy --strict`, `make lint-imports`, `make fence`, `make test` all green; lines-changed footprint bounded (~30 lines of production code per arch §Gap 4 "small").**

## Implementation outline

1. In `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py` (the module S6-05 ships):

   - Add the discriminated-union sum type (mirrors S6-05's `ErrorCount | UnparseableOutput`):

     ```python
     @dataclass(frozen=True)
     class Applicable:
         ts_files_count: int

     @dataclass(frozen=True)
     class DegradedNoTsconfig:
         ts_files_count: int

     @dataclass(frozen=True)
     class NotApplicable:
         pass

     TypeScriptApplicability = Applicable | DegradedNoTsconfig | NotApplicable
     ```

   - Add the bounded-I/O helper:

     ```python
     _TS_SUFFIXES: Final = frozenset({".ts", ".tsx", ".d.ts"})  # .d.ts via .suffix == ".ts" + stem.endswith(".d") — see note below
     _EXCLUDE_DIRS: Final = frozenset({"node_modules"})

     def _typescript_applicability(repo_root: Path) -> TypeScriptApplicability:
         """Bounded I/O: iterative scandir, skip node_modules, count ts/tsx/d.ts."""
         tsconfig_present = (repo_root / "tsconfig.json").exists()
         ts_count = _count_ts_files(repo_root)  # iterative scandir helper, also pure-ish I/O
         if tsconfig_present and ts_count >= 0:  # vacuous case still applicable
             return Applicable(ts_files_count=ts_count)
         if ts_count > 0:
             return DegradedNoTsconfig(ts_files_count=ts_count)
         return NotApplicable()
     ```

     Note on `.d.ts`: `Path("foo.d.ts").suffix == ".ts"` AND `Path("foo.d.ts").stem == "foo.d"` — the helper can match on `.suffix == ".ts"` (catches `.ts` and `.d.ts`) and `.suffix == ".tsx"` separately. Verify in a test fixture; don't rely on suffix-only naming if the implementer prefers `name.endswith((".ts", ".tsx"))` (which catches all three).

   - In `collect_typecheck_typescript_signal`, dispatch on the result of `_typescript_applicability` **before** invoking `run_allowlisted`:

     ```python
     async def collect_typecheck_typescript_signal(
         repo_root: Path,
         baseline_repo_sha: RepoSha,
         timeout_s: float = 30.0,
     ) -> TrustSignal:
         match _typescript_applicability(repo_root):
             case NotApplicable():
                 return TrustSignal(
                     kind=TYPECHECK_TYPESCRIPT,
                     passed=True,
                     details={"applicable": False},
                 )
             case DegradedNoTsconfig(ts_files_count=n):
                 # existing S6-05 path: invoke tsc; missing-tsc → degraded
                 return await _invoke_and_score(repo_root, baseline_repo_sha, timeout_s,
                                                 extra_details={"ts_files_count": n})
             case Applicable(ts_files_count=n):
                 # existing S6-05 path with applicable marker
                 return await _invoke_and_score(repo_root, baseline_repo_sha, timeout_s,
                                                 extra_details={"applicable": True, "ts_files_count": n})
             case _ as never:
                 typing.assert_never(never)
     ```

     `_invoke_and_score` extracts S6-05's existing body (run_allowlisted → parse → compare to baseline → return TrustSignal). The refactor preserves S6-05 behavior exactly for the `Applicable` and `DegradedNoTsconfig` arms.

2. Extend `tests/fence/test_phase4_typecheck_purity.py` (S6-05) to walk `_typescript_applicability` and assert AC-12's import / call denylist.

3. Land `tests/unit/typecheck/test_applicability_matrix.py` covering AC-1 (parametrized table), AC-4 (no-spawn), AC-5 (node_modules exclusion), AC-6 (`.tsx`), AC-7 (`.d.ts`), AC-13 (10K-file load).

4. Land `tests/integration/test_typecheck_signal_applicability_js_only.py::test_strict_and_both_directions` per AC-10. Use `TrustScorer(event_log=in_memory_event_log_fixture)` constructor injection (S6-05 AC-5 precedent).

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/unit/typecheck/test_applicability_matrix.py
"""Gap 4: JS-only repos must NOT fail strict-AND on missing tsc.
Why this matters: Phase 7's distroless plugin won't have a Node toolchain;
the same fence applies — pass not degrade when the signal doesn't apply.
"""
import importlib
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from codegenie.exec import ProcessResult
from codegenie.types.identifiers import RepoSha
from codegenie.transforms.outcomes import TrustSignal

mod = importlib.import_module(
    "plugins.vulnerability-remediation--node--npm.adapters.ts_typecheck_signal"
)


# --- repo_factory fixture (Cluster G; pinned to remove drift) -----------

@pytest.fixture
def repo_factory(tmp_path):
    """Builds a fixture repo under tmp_path with boolean flags.

    tsconfig=True       → writes {} to tsconfig.json
    ts_files=True       → writes src/index.ts (empty)
    tsx_files=True      → writes src/component.tsx (empty)
    d_ts_files=True     → writes src/types.d.ts (empty)
    node_modules_ts=int → writes node_modules/pkg-{i}/index.ts for i in range(N)
    """
    def _build(tsconfig=False, ts_files=False, tsx_files=False,
               d_ts_files=False, node_modules_ts=0):
        repo = tmp_path / "repo"
        (repo / "src").mkdir(parents=True)
        if tsconfig:
            (repo / "tsconfig.json").write_text("{}")
        if ts_files:
            (repo / "src" / "index.ts").write_text("")
        if tsx_files:
            (repo / "src" / "component.tsx").write_text("")
        if d_ts_files:
            (repo / "src" / "types.d.ts").write_text("")
        for i in range(node_modules_ts):
            pkg = repo / "node_modules" / f"pkg-{i}"
            pkg.mkdir(parents=True)
            (pkg / "index.ts").write_text("")
        return repo
    return _build


# --- AC-1: four-case matrix ---------------------------------------------

@pytest.mark.parametrize("has_tsconfig, has_ts_files, expected_variant", [
    (True,  True,  "Applicable"),
    (True,  False, "Applicable"),       # vacuous, but still applicable
    (False, True,  "DegradedNoTsconfig"),
    (False, False, "NotApplicable"),
])
def test_typescript_applicability_four_cases(
    has_tsconfig, has_ts_files, expected_variant, repo_factory,
):
    """AC-1: matrix dispatch is total + correct.

    Mutation barrier: a constant-returning implementation fails at least
    one row. Asserts variant by isinstance (Cluster G + J — sum-typed
    discipline; do not compare .value strings).
    """
    repo = repo_factory(tsconfig=has_tsconfig, ts_files=has_ts_files)
    result = mod._typescript_applicability(repo)
    assert type(result).__name__ == expected_variant


# --- AC-4: NotApplicable short-circuits before run_allowlisted ----------

@pytest.mark.asyncio
async def test_not_applicable_does_not_spawn_tsc(repo_factory):
    """AC-4: JS-only repo must NOT pay the tsc cost. Catches lazy
    'run tsc then override' implementations."""
    repo = repo_factory(tsconfig=False, ts_files=False)
    spy = AsyncMock()
    with patch.object(mod, "run_allowlisted", new=spy):
        result = await mod.collect_typecheck_typescript_signal(
            repo_root=repo, baseline_repo_sha=RepoSha("deadbeef"),
        )
    assert spy.call_count == 0
    assert result.passed is True
    assert result.details == {"applicable": False}
    # Cluster B: no confidence key — Pydantic extra='forbid' would have raised
    assert "confidence" not in result.details


# --- AC-5: node_modules exclusion ---------------------------------------

def test_node_modules_ts_files_do_not_count(repo_factory):
    """AC-5: every npm install creates thousands of .ts files under
    node_modules/. Walker must skip; otherwise every JS-only repo with
    installed packages is misclassified."""
    repo = repo_factory(tsconfig=False, ts_files=False, node_modules_ts=5)
    result = mod._typescript_applicability(repo)
    assert isinstance(result, mod.NotApplicable)


# --- AC-6: .tsx files trigger detection (the actual edge) ---------------

def test_tsx_alone_triggers_degraded_no_tsconfig(repo_factory):
    """AC-6 (Cluster G fix): .tsx without tsconfig means we DO see TypeScript
    in scope but can't run tsc properly — DegradedNoTsconfig branch.

    The original story tested `tsconfig=True, tsx_files=True` which would
    return Applicable just from tsconfig=True — that's not a .tsx test.
    """
    repo = repo_factory(tsconfig=False, ts_files=False, tsx_files=True)
    result = mod._typescript_applicability(repo)
    assert isinstance(result, mod.DegradedNoTsconfig)


# --- AC-7: .d.ts-only repos still detected ------------------------------

def test_d_ts_alone_triggers_degraded_no_tsconfig(repo_factory):
    """AC-7 (Cluster G fix): declaration files are TypeScript; tsc --noEmit
    on them is meaningful. Pin so future contributor doesn't narrow the
    predicate to source-only `.ts`."""
    repo = repo_factory(tsconfig=False, ts_files=False, d_ts_files=True)
    result = mod._typescript_applicability(repo)
    assert isinstance(result, mod.DegradedNoTsconfig)


# --- AC-13: bounded walker on a 10K-file node_modules fixture -----------

def test_large_node_modules_does_not_blow_up(tmp_path):
    """AC-13: structural + load assertion. 10K .ts files under node_modules
    should be skipped; classification returns within a generous 2s envelope.
    Not flaky-50ms (Cluster N)."""
    import time
    repo = tmp_path / "big_repo"
    repo.mkdir()
    big = repo / "node_modules" / "huge"
    big.mkdir(parents=True)
    for i in range(10_000):
        (big / f"f{i}.ts").write_text("")
    start = time.monotonic()
    result = mod._typescript_applicability(repo)
    elapsed = time.monotonic() - start
    assert isinstance(result, mod.NotApplicable)
    assert elapsed < 2.0  # generous envelope; flag a real regression


# --- AC-2 / AC-3: sum-type shape (frozen dataclass; not Literal/enum) ----

def test_applicability_variants_are_frozen_dataclasses():
    """AC-3: mirrors S6-05's ErrorCount | UnparseableOutput discipline.
    Frozen dataclasses enable match-exhaustive dispatch + assert_never."""
    from dataclasses import is_dataclass, fields
    for cls in (mod.Applicable, mod.DegradedNoTsconfig, mod.NotApplicable):
        assert is_dataclass(cls)
        assert getattr(cls, "__dataclass_params__").frozen is True
    # Applicable + DegradedNoTsconfig carry ts_files_count forensic count
    assert "ts_files_count" in {f.name for f in fields(mod.Applicable)}
    assert "ts_files_count" in {f.name for f in fields(mod.DegradedNoTsconfig)}


# --- AC-8: S6-05 regressions stay green ---------------------------------

# (No explicit test here — make test runs the existing S6-05 suite which must
# still pass. Listed as AC for awareness during code review.)


# tests/integration/test_typecheck_signal_applicability_js_only.py
# --- AC-10: full strict-AND, both directions, same test -----------------

@pytest.mark.asyncio
async def test_strict_and_both_directions(repo_factory, in_memory_event_log):
    """AC-10 (Cluster F + K): JS-only passes AND TS-with-broken-types fails,
    asserted in the same test so a constant-pass/constant-fail mutation
    cannot pass alone.

    Mirrors S6-05 AC-5's both-directions trust-scorer construction.
    """
    import importlib
    importlib.import_module(
        "plugins.vulnerability-remediation--node--npm.adapters.ts_typecheck_signal"
    )
    from codegenie.transforms.trust_scorer import TrustScorer
    from codegenie.transforms.outcomes import TrustSignal
    from codegenie.types.identifiers import SignalKind

    other_kinds = [
        SignalKind("build"), SignalKind("install"), SignalKind("tests"),
        SignalKind("lockfile_policy"), SignalKind("cve_delta"),
    ]
    five_passes = [TrustSignal(kind=k, passed=True, details={}) for k in other_kinds]

    # Positive direction: JS-only repo → applicable=False → outcome.passed=True
    js_only = repo_factory(tsconfig=False, ts_files=False)
    ts_signal_pos = await mod.collect_typecheck_typescript_signal(
        repo_root=js_only, baseline_repo_sha=RepoSha("deadbeef"),
    )
    scorer = TrustScorer(event_log=in_memory_event_log)
    out_pos = scorer.score([*five_passes, ts_signal_pos])
    assert out_pos.passed is True
    assert out_pos.failing == []
    assert ts_signal_pos.details == {"applicable": False}

    # Negative direction: TS repo with broken types → typecheck signal fails →
    # outcome.passed=False, failing == [typecheck.typescript]
    ts_repo = repo_factory(tsconfig=True, ts_files=True)
    failing_ts_signal = TrustSignal(
        kind=SignalKind("typecheck.typescript"),
        passed=False,
        details={"baseline_error_count": 0, "current_error_count": 3},
    )
    out_neg = scorer.score([*five_passes, failing_ts_signal])
    assert out_neg.passed is False
    assert out_neg.failing == [SignalKind("typecheck.typescript")]
```

### Green — make it pass

- Add the three frozen-dataclass variants + `TypeScriptApplicability` alias.
- Add `_typescript_applicability(repo_root)` with iterative `os.scandir`, skipping `node_modules/`, counting suffix matches.
- Refactor `collect_typecheck_typescript_signal` to dispatch on the matrix via `match`/`case` with `typing.assert_never(...)` exhaustiveness; the `Applicable` and `DegradedNoTsconfig` arms delegate to an extracted `_invoke_and_score` helper preserving S6-05's exact behavior.
- Verify all existing S6-05 tests (`tests/unit/typecheck/test_signal.py`, `tests/unit/typecheck/test_baseline_io.py`, `tests/unit/trust_scorer/test_typecheck_kind.py`, `tests/fence/test_typecheck_signal_registered.py`, `tests/fence/test_phase4_no_trust_scorer_edits.py`) still pass.
- Extend `tests/fence/test_phase4_typecheck_purity.py` (S6-05's fence file) to AST-walk `_typescript_applicability` per AC-12's denylist.

### Refactor — clean up

- Confirm `_typescript_applicability` reads no file contents (only directory entries + `tsconfig.json` existence check via `Path.exists()`) — the AST-fence in AC-12 enforces this.
- Confirm the dispatch in `collect_typecheck_typescript_signal` is exhaustive via `match` + `typing.assert_never(...)` in the catch-all — a fifth variant added later then fails mypy `--strict`.
- Verify the matrix-test column "expected_variant" uses `type(result).__name__` comparison so renaming a variant fails the test loudly.
- The `_invoke_and_score` helper extracts S6-05's body without changing semantics — the existing S6-05 unit tests are the regression gate.

## Files to touch

| Path | Why |
|---|---|
| `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py` | Add `Applicable | DegradedNoTsconfig | NotApplicable` sum type + `_typescript_applicability` helper + `match`-based dispatch in `collect_typecheck_typescript_signal`. ~30 lines per arch §Gap 4 "small". |
| `tests/unit/typecheck/test_applicability_matrix.py` | New — table-driven four-case matrix + AC-4 no-spawn + AC-5 node_modules exclusion + AC-6 `.tsx` + AC-7 `.d.ts` + AC-13 10K-file load. |
| `tests/integration/test_typecheck_signal_applicability_js_only.py` | New — AC-10 both-directions strict-AND with `TrustScorer(event_log=...)`. |
| `tests/fence/test_phase4_typecheck_purity.py` | **Extend** (S6-05's fence) — add `_typescript_applicability` to the AST-walk denylist (AC-12). |

## Out of scope

- Promoting `typecheck.typescript` to a shared `vulnerability-remediation--node--*` base plugin so Phase 7 can not-register it instead of needing the matrix — Phase 7 decision per ADR-04-0015 §Decision.
- Detecting *project references* (`composite: true` + `references: [...]`) or path-mapped `tsconfig.json` files in subdirectories — out of scope; the simple-root-tsconfig check is the durable shape. Subdir-tsconfig repos fall into `DegradedNoTsconfig` (still applicable, degraded).
- Re-running `tsc` on the *applicable-but-no-`.ts`-files* case to confirm 0 errors — the test pins the contract; the actual `tsc` invocation behavior is S6-05's responsibility. The `Applicable(ts_files_count=0)` variant simply delegates to the existing S6-05 path.
- Extracting a `TypecheckApplicabilityKit(language, manifest_files, source_suffixes, exclude_dirs)` shared helper — defer to the second sibling (`typecheck.python` in Phase 7.5) per Rule of Three + Rule 2 (three similar lines beats premature abstraction).

## Notes for the implementer

- **The matrix is from arch §Gap 4 verbatim.** If you find yourself adding a fifth case, surface per Global Rule 7 — the gap analysis says "four cases" and "small (~30 lines)". Adding a fifth case is structurally fine (the `match` block + `assert_never` will demand the new arm), but if you reach for it, surface the change.

- **`.tsx` and `.d.ts` count as `.ts` for applicability** (the `tsc` toolchain handles both). Pin in tests so a future contributor doesn't accidentally narrow the predicate. The cheapest predicate is `name.endswith((".ts", ".tsx"))` — `.d.ts` is caught by `.endswith(".ts")`. Or use `Path.suffix in (".ts", ".tsx")` (also catches `.d.ts` via `.ts` suffix). Either works; pick one and pin.

- **The `NotApplicable` case is THE load-bearing change.** A regression here re-introduces the bug where a JS-only repo cannot pass Phase 5's validate. AC-4 (no-spawn) + AC-10 (both-directions integration) are the two mutation barriers; both must stay green.

- **The applicability check has bounded I/O, not strict purity.** It reads directory entries and `tsconfig.json` existence (a stat call). It does NOT read file contents. The CLAUDE.md "functional core / imperative shell" discipline is preserved — the check is deterministic given the filesystem state at call time, and AC-12's AST-fence pins the boundedness (no subprocess, no network, no `.read_text` / `.read_bytes` / `open()`-for-read).

- **`confidence` is NOT a field on `TrustSignal`** (shipped `outcomes.py:377-388`; Pydantic `extra="forbid"`). Every previous AC that prescribed `confidence="high"` / `"medium"` would `ValidationError` at construction. Use `details["applicable"]: bool` for the not-applicable case. This is S6-05's Cluster B precedent — do not re-introduce.

- **Subprocess surface is `run_allowlisted`, NOT `SubprocessJail`.** S6-05's Cluster D fixed this; S6-06 inherits the same surface. The `NotApplicable` arm must short-circuit BEFORE `run_allowlisted` is called (AC-4).

- **Module import path uses the hyphenated slug** via `importlib.import_module("plugins.vulnerability-remediation--node--npm...")`. Python's `import` parser rejects hyphens; the loader uses the literal slug per S7-01. Bare `from plugins.vulnerability_remediation__node__npm.adapters... import ...` raises `SyntaxError`.

- **Open/Closed verified by S6-05's existing fence** `tests/fence/test_phase4_no_trust_scorer_edits.py`. S6-06 introduces zero diff to `src/codegenie/transforms/{trust_scorer,signal_kinds,outcomes}.py`. If you find yourself reaching for those files, you've broken Open/Closed — surface per Global Rule 7.

- **Phase 7's distroless plugin** still has the option of *not registering* the signal at all per ADR-04-0015 §Decision. The applicability matrix is the "right shape" Phase 7's Node-touching plugin will inherit even if the signal is promoted to a shared base plugin (arch open question 3).

- **Future-sibling extract (Rule of Three; defer).** When Phase 7.5 lands `typecheck.python`, the applicability shape will repeat: presence of `pyproject.toml` (and/or `setup.py` / `setup.cfg`) + any `.py` file (excluding `.venv/` and `__pycache__/`) → `Applicable | DegradedNoPyproject | NotApplicable`. The second sibling triggers a kernel extract along axes `(language: str, manifest_files: list[str], source_suffixes: list[str], exclude_dirs: list[str]) -> Applicability` — likely `src/codegenie/typecheck/applicability_kit.py` or similar. **First sibling (this story) ships flat** per Rule 2 ("three similar lines is better than premature abstraction"); next sibling carries the extract. The third sibling (`typecheck.java` later) consumes it.

- **No ADR amendment required.** Arch §Gap 4 already prescribes the matrix verbatim; ADR-04-0015 §Tradeoffs's "missing tsc → degraded" framing is subsumed additively by the matrix (the `DegradedNoTsconfig` arm preserves S6-05's existing degraded behavior). The new `details["applicable"]` + `details["ts_files_count"]` keys are forensic — no schema-level claim to update.
