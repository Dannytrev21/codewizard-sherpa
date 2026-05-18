# Story S6-06 — `typecheck.typescript` applicability matrix (JS-only repos pass, not degrade)

**Step:** Step 6 — Compose FallbackTier + register typecheck.typescript SignalKind + integration
**Status:** Ready
**Effort:** S
**Depends on:** S6-05 (the base collector + registration)
**ADRs honored:** ADR-04-0015 (TypeScript-in-scope detection), Gap 4 from arch §Gap analysis (pass-not-degrade for JS-only repos)

## Context

S6-05 shipped the base `TypecheckTypescriptSignal` with degraded behavior when `tsc` is missing: `TrustSignal(passed=False, details={"degraded_reason": "no_tsconfig_or_tsc"}, confidence="medium")`. Phase-arch-design §Gap 4 (lines 1108–1112) flags the bug honestly: that response **fails strict-AND**, which means a perfectly correct **JavaScript-only repo with no TypeScript at all** cannot pass Phase 5's validate. That's wrong — the signal should *not apply*, not *fail*.

The fix is the applicability matrix: detect whether TypeScript is in scope (`tsconfig.json` + any `.ts` files) and dispatch per the four-case truth table from arch §Gap 4:

| `tsconfig.json` present | `.ts` files present | applicable | passed | confidence | semantics |
|---|---|---|---|---|---|
| yes | yes | True | run `tsc`, project result | (depends on tsc) | normal happy path |
| yes | no  | True | run `tsc` (will be 0 errors) | True | applicable, vacuous |
| no  | yes | True | degraded — run `tsc` if available | varies | confidence="medium" |
| no  | no  | **False** | **True** | **high** | not applicable; pass not degrade |

The last row is the load-bearing change: `details={"applicable": False}` and `passed=True` — the signal **passes** because it does not apply. JS-only repos sail through strict-AND.

This is surgical (~30 lines per arch §Gap 4 "Improvement" paragraph); composes cleanly with S6-05's existing structure.

## References — where to look

- **Architecture:** [phase-arch-design.md §Gap analysis — Gap 4](../phase-arch-design.md) (lines 1108–1112 — the matrix); §Edge case row 9 (missing tsc); §Component 11; §Goal G10.
- **Phase ADRs:** [ADR-04-0015](../ADRs/0015-typecheck-typescript-signal-and-tsc-allowed-binary.md) (§Tradeoffs — missing tsc semantics; §Consequences — applicability is plugin-local).
- **Source design:** [final-design.md §Component 12](../final-design.md) (applicability detection mentioned as the right shape).
- **High-level impl:** [High-level-impl.md §Step 6](../High-level-impl.md) Features delivered ("Applicability detection per Gap 4: presence of `tsconfig.json` + any `.ts` files").
- **Existing code (after S6-05):** `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py`. This story extends the `collect` method's prelude.

## Goal

Add `TypeScript-in-scope` detection to `TypecheckTypescriptSignal.collect`: presence of `tsconfig.json` AND any `.ts` files in the repo. Dispatch the four-case applicability matrix per arch §Gap 4; emit `TrustSignal(passed=True, details={"applicable": False}, confidence="high")` for JS-only repos so they pass strict-AND instead of failing it.

## Acceptance criteria

- [ ] **Four-case truth table** asserted by `tests/unit/typecheck/test_applicability_matrix.py`:
  - `tsconfig.json + .ts files` → `applicable=True`; run tsc; result projection unchanged from S6-05.
  - `tsconfig.json + no .ts files` → `applicable=True`; run tsc (will report 0 errors); `passed=True`, `confidence="high"`.
  - `no tsconfig.json + .ts files` → `applicable=True` (degraded); run tsc *if available*; `confidence="medium"`. If tsc missing, fall back to S6-05's `degraded_reason="no_tsconfig_or_tsc"` path.
  - `no tsconfig.json + no .ts files` → `applicable=False`; `passed=True`; `details={"applicable": False}`; `confidence="high"`. **The signal passes because it does not apply.**
- [ ] **TypeScript-in-scope detection is a pure function**: `is_typescript_in_scope(repo: RepoSnapshot) -> TypeScriptApplicability` where `TypeScriptApplicability` is a small sum type (`Applicable | DegradedNoTsconfig | NotApplicable`). Testable in isolation. Pure: no I/O outside the repo snapshot.
- [ ] **`.ts` file detection is bounded**: walks the repo respecting `.gitignore` semantics (re-use Phase-0/1 file walker); does not recurse into `node_modules/`; does not blow up on a 10K-file repo. Performance: `is_typescript_in_scope` ≤ 50 ms on the fixture repo.
- [ ] **No false positives from `.d.ts`-only repos**: a repo with only declaration files (`*.d.ts`) but no `.ts` source files is still detected as `.ts files present` (declaration files are TypeScript and `tsc --noEmit` on them is meaningful). Test pinned.
- [ ] **Existing S6-05 tests still green**: the baseline-strict-AND, timeout, and `tsc`-missing paths from S6-05 still pass; the matrix wraps but does not replace them.
- [ ] **TrustSignal shape preserved**: `details: dict[str, str|int|bool]` shape from arch §Type contracts (line 763) unchanged; the new keys `{"applicable": False}` or `{"applicable": True, "ts_files_count": int}` fit the existing dict shape (no widening).
- [ ] **Strict-AND in JS-only repo**: `tests/integration/test_typecheck_signal_applicability_js_only.py` runs the full Phase-3 `TrustScorer` against a JS-only fixture repo with no `tsconfig.json` and no `.ts` files; `TrustOutcome.passed` is True; the typecheck signal contributes `passed=True, applicable=False` to the strict-AND.
- [ ] **Strict-AND in TS-in-scope-but-no-.ts-files**: a repo with `tsconfig.json` but only `.tsx` and `.js` files — apply rule "any `.ts` or `.tsx` file in scope". Decide and pin: `.tsx` counts as `.ts` for applicability purposes (the `tsc` toolchain handles both). Tests pin both directions.
- [ ] `make check`, `mypy --strict`, `make lint-imports` all green; lines-changed footprint bounded (~30 lines of production code per arch §Gap 4 "small").

## Implementation outline

1. In `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py`:
   - Add a small sum type `TypeScriptApplicability` (e.g., enum or `Literal["applicable", "degraded_no_tsconfig", "not_applicable"]` — match the existing Phase-3 convention).
   - Add `_is_typescript_in_scope(repo: RepoSnapshot) -> TypeScriptApplicability` pure helper.
   - In `collect`, dispatch on the result of `_is_typescript_in_scope`:
     - `Applicable` ⇒ existing S6-05 path.
     - `DegradedNoTsconfig` ⇒ run tsc if available; `confidence="medium"`; else degraded path from S6-05.
     - `NotApplicable` ⇒ early-return `TrustSignal(kind="typecheck.typescript", passed=True, details={"applicable": False}, confidence="high")`.
2. The `.ts`/`.tsx` walker can use Phase-0's existing repo-snapshot file enumeration (don't re-walk the filesystem; the snapshot already has the file list).
3. Land `tests/unit/typecheck/test_applicability_matrix.py` covering the four cases plus the `.tsx`-only and `.d.ts`-only edge cases.
4. Land `tests/integration/test_typecheck_signal_applicability_js_only.py` — JS-only repo through the full strict-AND.

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/typecheck/test_applicability_matrix.py
import pytest
from plugins.vulnerability_remediation__node__npm.adapters.ts_typecheck_signal import (
    TypecheckTypescriptSignal, _is_typescript_in_scope,
)

@pytest.mark.parametrize("has_tsconfig, has_ts_files, expected", [
    (True,  True,  "applicable"),
    (True,  False, "applicable"),  # vacuous, but still applicable
    (False, True,  "degraded_no_tsconfig"),
    (False, False, "not_applicable"),
])
def test_is_typescript_in_scope_four_cases(has_tsconfig, has_ts_files, expected, repo_factory):
    """Gap 4: JS-only repos must NOT fail strict-AND on missing tsc.
    Why this matters: Phase 7's distroless plugin won't have a Node toolchain;
    the same fence applies — pass not degrade when the signal doesn't apply."""
    repo = repo_factory(tsconfig=has_tsconfig, ts_files=has_ts_files)
    assert _is_typescript_in_scope(repo).value == expected


@pytest.mark.asyncio
async def test_js_only_repo_passes_with_applicable_false(repo_factory):
    """Gap 4 load-bearing assertion: pass not degrade."""
    repo = repo_factory(tsconfig=False, ts_files=False)
    sig = TypecheckTypescriptSignal()
    result = await sig.collect(repo, ctx)
    assert result.passed is True
    assert result.details == {"applicable": False}
    assert result.confidence == "high"


@pytest.mark.asyncio
async def test_tsx_files_count_as_typescript_in_scope(repo_factory):
    """tsc handles .tsx; applicability must include it."""
    repo = repo_factory(tsconfig=True, ts_files=False, tsx_files=True)
    result = _is_typescript_in_scope(repo)
    assert result.value == "applicable"


@pytest.mark.asyncio
async def test_d_ts_only_repo_treated_as_in_scope(repo_factory):
    """Declaration-only repo: tsc --noEmit on .d.ts is meaningful."""
    repo = repo_factory(tsconfig=True, ts_files=False, d_ts_files=True)
    result = _is_typescript_in_scope(repo)
    assert result.value == "applicable"


# tests/integration/test_typecheck_signal_applicability_js_only.py
@pytest.mark.asyncio
async def test_full_strict_and_passes_for_js_only_repo(js_only_fixture_repo):
    """Gap 4 + ADR-04-0015: JS-only repo must produce TrustOutcome.passed=True
    on the strict-AND even with typecheck.typescript in the registry.
    Why this matters: regression of this test means we re-introduced the
    'JS-only repo can't pass Phase 5 validate' bug."""
    scorer = TrustScorer()
    signals = await collect_all_signals(js_only_fixture_repo)  # registry-driven
    outcome = scorer.score(signals)
    assert outcome.passed is True
    ts_sig = next(s for s in signals if s.kind == "typecheck.typescript")
    assert ts_sig.details == {"applicable": False}
```

### Green — make it pass

- Land `_is_typescript_in_scope` + `TypeScriptApplicability` enum / sum type.
- Add the four-case dispatch in `collect`.
- Verify the existing S6-05 tests still pass (the `Applicable` path is the existing behavior).

### Refactor — clean up

- The walker should use the existing repo-snapshot file list — don't recurse the filesystem here. Read `src/codegenie/probes/base.py` / `RepoSnapshot` to confirm the file-listing surface (Global Rule 8).
- The four-case test is the documentation; do not duplicate the table in a docstring — point readers to the test from a one-line comment.

## Files to touch

| Path | Why |
|---|---|
| `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py` | Add `_is_typescript_in_scope` + four-case dispatch in `collect`. |
| `tests/unit/typecheck/test_applicability_matrix.py` | New — table-driven four-case + `.tsx` + `.d.ts` pins. |
| `tests/integration/test_typecheck_signal_applicability_js_only.py` | New — full strict-AND on JS-only fixture. |

## Out of scope

- Promoting `typecheck.typescript` to a shared `vulnerability-remediation--node--*` base plugin so Phase 7 can not-register it instead of needing the matrix — Phase 7 decision per ADR-04-0015 §Decision.
- Detecting *project references* (`composite: true` + `references: [...]`) or path-mapped `tsconfig.json` files in subdirectories — out of scope; the simple-root-tsconfig check is the durable shape.
- Re-running tsc on the *applicable-but-no-.ts-files* case to confirm 0 errors — the test pins the contract; the actual `tsc` invocation behavior is S6-05's responsibility.

## Notes for the implementer

- The matrix is from arch §Gap 4 verbatim. If you find yourself adding a fifth case, surface per Global Rule 7 — the gap analysis says "four cases" and "small (~30 lines)".
- `.tsx` counts as `.ts` for applicability (the `tsc` toolchain handles both). Pin this in a test so a future contributor doesn't accidentally narrow the predicate to `*.ts` literal.
- The `not_applicable` case is **the load-bearing change**. A regression here re-introduces the bug where a JS-only repo cannot pass Phase 5's validate. Make the test name self-documenting.
- The applicability check is **pure** — it reads the repo snapshot, returns a sum type, no I/O. The functional-core/imperative-shell discipline from CLAUDE.md applies. AST-walk tests in some Phase-1/2 probes assert this; mirror the convention if the existing tests demand it.
- Phase 7's distroless plugin still has the option of *not registering* the signal at all per ADR-04-0015 §Decision. The applicability matrix is the "right shape" Phase 7's Node-touching plugin will inherit even if the signal is promoted to a shared base plugin (arch open question 3).
