# Story S1-05 — ADR-P4-002 — orchestrator writeback conditional stub branch

**Step:** Step 1 — Plant the contracts, the two ADR-gated Phase-3 edits, and the fence-CI rules every Phase 4 component consumes
**Status:** Ready
**Effort:** S
**Depends on:** S1-04
**ADRs honored:** ADR-P4-001, ADR-P4-002

## Context

The **second and final** in-place Phase-3 edit Phase 4 makes (G15). Phase 3's `RemediationOrchestrator` is the six-call linear pipeline; Phase 4 needs exactly one new branch after `TrustScorer.passed`: when `recipe_application.engine_used == "rag_llm"`, call `writeback_solved_example(...)`. In Step 1 this branch is a **no-op stub** — annotated with `# Phase 4 ADR-P4-002 conditional` so review can find it. S6-03 promotes the stub to the real call. The stub ships now so the snapshot of "what the orchestrator does" matches the architecture and so Phase 3 paths (`ncu`, `openrewrite`) provably never reach the branch (G15 regression hard-gate in S7-05 depends on this).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Control flow"` step 9 — "Decision point E: `TrustScorer.passed && engine_used == 'rag_llm'` → call `writeback_solved_example` synchronously. This is the ADR-P4-002 conditional branch. Other engines (`ncu`, `openrewrite`) do not trigger writeback — Phase 3's path is untouched."
  - `../phase-arch-design.md §"Component design"` #6 — `writeback_solved_example` strict guard.
- **Phase ADRs:**
  - `../ADRs/0002-two-tier-writeback-pending-promoted.md` — ADR-P4-002 — the writeback shape this branch will later call.
  - `../ADRs/0001-recipe-engine-literal-extends-with-rag-llm.md` — ADR-P4-001 — the Literal extension this branch's `engine_used == "rag_llm"` check relies on.
- **Existing code:**
  - `src/codegenie/transforms/coordinator.py` — the six-call linear `RemediationOrchestrator.run`. Edit-in-place per ADR-P4-002.
  - `src/codegenie/recipes/selector.py` / `src/codegenie/recipes/contract.py` — sources of `RecipeApplication.engine_used`.

## Goal

Add exactly one conditional branch inside `RemediationOrchestrator.run` (or wherever `TrustScorer.passed` lands) that pattern-matches `recipe_application.engine_used == "rag_llm"` and `trust_score.passed`, but performs no action — annotated as the ADR-P4-002 writeback conditional placeholder.

## Acceptance criteria

- [ ] `src/codegenie/transforms/coordinator.py` contains exactly one new conditional block, of the shape `if recipe_application.engine_used == "rag_llm" and trust_score.passed: pass  # Phase 4 ADR-P4-002 conditional`.
- [ ] The block is reachable by direct integration test (a synthetic `RecipeApplication(engine_used="rag_llm")` + passing `TrustScorer` enters the branch).
- [ ] `tests/unit/transforms/test_writeback_stub_unreachable.py` asserts Phase 3 paths (`ncu`, `openrewrite`) **never** execute the branch when fed real Phase-3 fixtures — even if `TrustScorer.passed == True`.
- [ ] `tests/unit/transforms/test_writeback_stub_annotated.py` AST-scans `coordinator.py` for the literal comment `# Phase 4 ADR-P4-002 conditional` and fails if absent — so the annotation cannot drift silently.
- [ ] All Phase-3 integration tests still pass verbatim — the stub is a no-op.
- [ ] PR labelled `phase-3-contract-bumped`.
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on `src/codegenie/transforms/coordinator.py` clean.

## Implementation outline

1. Locate the post-`TrustScorer.score(...)` site in `RemediationOrchestrator.run` (or its delegate).
2. Add the conditional block in the smallest possible footprint:
   ```python
   if recipe_application.engine_used == "rag_llm" and trust_score.passed:
       pass  # Phase 4 ADR-P4-002 conditional — writeback wired in S6-03
   ```
3. Write `tests/unit/transforms/test_writeback_stub_unreachable.py`:
   - Mock `RecipeSelector` to return `engine="ncu"` then `engine="openrewrite"` (use Phase-3 fixtures); stub `TrustScorer.passed=True`;
   - Mock `writeback_solved_example` (it doesn't exist yet — patch any future call site or assert on the branch's `pass` path via a probe like an injected counter); concretely: use a `unittest.mock.patch` that *would* intercept any call to a Phase-4 writeback symbol; assert it was never called for the `ncu` / `openrewrite` engines.
4. Write `tests/unit/transforms/test_writeback_stub_annotated.py`: read `coordinator.py` and assert the marker comment exists.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/transforms/test_writeback_stub_unreachable.py`

```python
from unittest.mock import patch

import pytest

from codegenie.transforms.coordinator import RemediationOrchestrator
# ... import or build Phase-3 fixture helpers ...


@pytest.mark.parametrize("engine_used", ["ncu", "openrewrite"])
def test_phase3_engines_do_not_enter_writeback_branch(engine_used, phase3_passing_fixture):
    """G15 — the ADR-P4-002 branch must be unreachable from Phase-3 engines."""
    sentinel = []

    # Patch any symbol that the *real* writeback would call once S6-03 lands.
    # If writeback_solved_example doesn't exist yet, assert via a code-path
    # marker counter injected behind a feature flag — keep this purely
    # behavioral so the test still works post-promotion.
    with patch(
        "codegenie.transforms.coordinator._WRITEBACK_BRANCH_VISITED",
        new=sentinel,
        create=True,
    ):
        run_orchestrator_with_engine(
            phase3_passing_fixture, engine_used=engine_used
        )

    assert sentinel == [], (
        f"Phase-3 {engine_used} path entered the rag_llm writeback branch — "
        "ADR-P4-002 boundary violated (G15)."
    )


def test_rag_llm_engine_enters_writeback_branch(rag_llm_passing_fixture):
    sentinel = []
    with patch(
        "codegenie.transforms.coordinator._WRITEBACK_BRANCH_VISITED",
        new=sentinel, create=True,
    ):
        run_orchestrator_with_engine(rag_llm_passing_fixture, engine_used="rag_llm")
    assert sentinel == ["visited"]
```

Test file path: `tests/unit/transforms/test_writeback_stub_annotated.py`

```python
from pathlib import Path

COORDINATOR = Path("src/codegenie/transforms/coordinator.py").resolve()


def test_writeback_branch_carries_adr_marker_comment():
    src = COORDINATOR.read_text()
    assert "# Phase 4 ADR-P4-002 conditional" in src, (
        "ADR-P4-002 marker comment missing — reviewers will lose track "
        "of the second Phase-3 edit."
    )
```

### Green — make it pass

Add the `if` block with the marker comment. To satisfy the `_WRITEBACK_BRANCH_VISITED` sentinel in tests, append inside the branch body:

```python
if recipe_application.engine_used == "rag_llm" and trust_score.passed:
    _WRITEBACK_BRANCH_VISITED.append("visited")  # Phase 4 ADR-P4-002 conditional — writeback wired in S6-03
```

…where `_WRITEBACK_BRANCH_VISITED: list[str] = []` is a module-level test seam. **The seam ships in production** as an empty list with no other writer — it's `pass`-equivalent and entirely free at runtime. S6-03 will replace this with the real `writeback_solved_example(...)` call.

Alternative if the team prefers not to ship a test seam: keep the body as `pass` and have the unreachability test stub-patch the *whole function path* rather than a sentinel; pick whichever matches Phase-0 conventions (Rule 11).

### Refactor — clean up

- The sentinel pattern is unusual; surface (Rule 12) and discuss in PR if reviewers prefer the `pass`+function-patch alternative. Both satisfy ADR-P4-002 unreachability; the sentinel is just less brittle across Step 6 promotion.
- Confirm `mypy --strict` accepts the sentinel; if not, use `Final[list[str]] = []` plus a `# noqa` on the mutation line (the runtime mutation is intentional).
- No other refactor of `coordinator.py`. Surgical changes only.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/coordinator.py` | Add the ADR-P4-002 stub branch. |
| `tests/unit/transforms/test_writeback_stub_unreachable.py` | Prove Phase-3 paths never enter the branch (G15). |
| `tests/unit/transforms/test_writeback_stub_annotated.py` | Keep the ADR marker comment honest. |

## Out of scope

- **Real `writeback_solved_example` call** — promoted in S6-03 after S6-01/S6-02 ship the function and the Gap-4 guard matrix.
- **Strict-AND TrustScorer extension** — S6-02.
- **`plan_source` accounting** — S5-02 / S6-02.
- **`--no-rag` / `--no-llm` CLI semantics** — S6-03.

## Notes for the implementer

- This is the **last** Phase-3 file Phase 4 touches in-place (G15). Phase-3 regression hard-gate (S7-05) re-runs every Phase-3 integration test verbatim; any unrelated edit here will fail S7-05.
- The marker comment `# Phase 4 ADR-P4-002 conditional` is asserted by a test. Do not paraphrase it.
- The `_WRITEBACK_BRANCH_VISITED` sentinel is acceptable in production only because it has no writer outside this branch AND the branch is a no-op. If you prefer not to ship the sentinel, structure the test around a `unittest.mock.patch` of a symbol that will exist in S6-01 (e.g. `codegenie.rag.writeback.writeback_solved_example`) — and skip the test until S6-01 lands. The downside is the unreachability assertion is delayed by 5 stories; the sentinel keeps it on the critical path.
- Verify that `RecipeApplication.engine_used` is already a `Literal["ncu","openrewrite","rag_llm"]` after S1-04 (or that S1-04 left it as `str` because Phase 3 used `str`). If `Literal`, the `engine_used == "rag_llm"` branch is statically reachable; mypy `assert_never` on a `match` would catch a missed case. If `str`, no mypy check applies — the unreachability test is the only line of defence.
- Edge case from `../phase-arch-design.md §"Edge cases"`: row #14 — "Worker crashes between `TrustScorer.pass` and writeback completion → next run with same `qk` re-pays LLM". This story's stub does not write; that's fine for now. S6-01 makes the writeback synchronous so the rare-crash budget is bounded.
- Rule 12 (fail loud): if the orchestrator's post-trust-score site doesn't exist or differs from `../phase-arch-design.md §"Control flow"` step 9, surface (don't infer where to put the branch).
