# Story S1-04 — ADR-P4-001 — `Recipe.engine` Literal extension to `"rag_llm"`

**Step:** Step 1 — Plant the contracts, the two ADR-gated Phase-3 edits, and the fence-CI rules every Phase 4 component consumes
**Status:** Ready
**Effort:** S
**Depends on:** S1-02, S1-03
**ADRs honored:** ADR-P4-001

## Context

Cross-cutting and load-bearing. This story is the **first of exactly two** in-place Phase-3 edits Phase 4 makes (G15). Phase 3 froze `Recipe.engine: Literal["ncu","openrewrite"]`; Phase 4 adds `"rag_llm"` so the third `RecipeEngine` (built in Step 5) can register through the existing selector chain. The edit is single-line in the production source but updates the Phase-3 snapshot test (`tests/contracts/test_recipe_engine_literal_snapshot.py`) and ships a new unit test confirming every Phase-3 fixture still parses. PR must carry the `phase-3-contract-bumped` label so review concentration finds it.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Architectural context"` — "two ADR-gated additive edits" caption.
  - `../phase-arch-design.md §"Component design"` #1 — `RagLlmEngine` is the new sibling that consumes the extended Literal.
  - `../phase-arch-design.md §"Development view"` — engine registry pattern shipped in Phase 3.
- **Phase ADRs:**
  - `../ADRs/0001-recipe-engine-literal-extends-with-rag-llm.md` — ADR-P4-001 — the decision; this story IS its implementation.
- **Source design:**
  - `../final-design.md §"Roadmap coherence check"` §"New ADRs implied"` — ADR-P4-001 surfaced.
- **Existing code:**
  - `src/codegenie/recipes/contract.py` — current `Recipe.engine: Literal["ncu","openrewrite"]`.
  - `tests/contracts/test_recipe_engine_literal_snapshot.py` — Phase-3 snapshot the regen targets.
  - `tests/fixtures/recipes/*.yaml` — every Phase-3 recipe fixture must still parse with the extended Literal.

## Goal

Extend `Recipe.engine` from `Literal["ncu","openrewrite"]` to `Literal["ncu","openrewrite","rag_llm"]` and regenerate the Phase-3 snapshot test while proving every Phase-3 fixture still validates.

## Acceptance criteria

- [ ] `src/codegenie/recipes/contract.py` — `Recipe.engine: Literal["ncu","openrewrite","rag_llm"]`. No other field changed.
- [ ] `tests/contracts/test_recipe_engine_literal_snapshot.py` regenerated to include `"rag_llm"`; new snapshot committed; CI re-greens.
- [ ] `tests/unit/recipes/test_recipe_engine_literal_extended.py` — `Recipe(engine="rag_llm", ...)` validates AND every Phase-3 fixture under `tests/fixtures/recipes/*.yaml` parses unchanged (forward compat assertion).
- [ ] `Recipe(engine="garbage")` still raises `ValidationError` (Literal still closed; one new value only).
- [ ] PR labelled `phase-3-contract-bumped` so the review-of-the-edit is conspicuous (per ADR-P4-001).
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` on `src/codegenie/recipes/contract.py` clean.
- [ ] All Phase-0–3 CI jobs (`fence`, `tool_digests_verify`, `recipes_digests_verify`, `determinism_canary`, `adversarial_corpus`) stay green.

## Implementation outline

1. Open `src/codegenie/recipes/contract.py`; change exactly the Literal definition. Touch no other line.
2. Open `tests/contracts/test_recipe_engine_literal_snapshot.py`; regenerate the snapshot (e.g. run a one-off pytest under `UPDATE_SNAPSHOTS=1` or hand-edit the snapshot constant the test compares against — match the Phase-0 snapshot discipline).
3. Add `tests/unit/recipes/test_recipe_engine_literal_extended.py`:
   - `Recipe(engine="rag_llm", ...)` validates;
   - every Phase-3 fixture parses unchanged (parametrize over `tests/fixtures/recipes/*.yaml`);
   - `Recipe(engine="garbage")` still raises.
4. Re-run the Phase-3 test suite to confirm no regression. The `phase-3-contract-bumped` PR label is the operational fence.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/recipes/test_recipe_engine_literal_extended.py`

```python
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from codegenie.recipes.contract import Recipe

FIXTURES = Path(__file__).parents[2] / "fixtures" / "recipes"


def test_recipe_engine_accepts_rag_llm():
    r = Recipe(
        engine="rag_llm",
        # ...whatever minimum field set Phase-3 Recipe needs...
    )
    assert r.engine == "rag_llm"


def test_recipe_engine_still_rejects_unknown():
    with pytest.raises(ValidationError):
        Recipe(engine="garbage")


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.yaml")))
def test_every_phase3_fixture_still_parses(path: Path) -> None:
    Recipe.model_validate(yaml.safe_load(path.read_text()))
```

### Green — make it pass

Change exactly one character region: `Literal["ncu","openrewrite"]` → `Literal["ncu","openrewrite","rag_llm"]`. Regenerate the Phase-3 snapshot.

### Refactor — clean up

- No refactor needed (Rule 3 — surgical changes). The edit is the smallest possible.
- Add an inline comment near the Literal: `# Phase 4 ADR-P4-001 — additive; Phase 7 (Chainguard) will append another value`.
- Confirm `RecipeApplication.engine_used: Literal[...]` mirrors the same triple if it exists in Phase 3 — if so, this story extends that Literal too (still one-line). If it doesn't yet exist, leave it; S6-01 will introduce it.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/recipes/contract.py` | Extend `Recipe.engine` Literal by one value. |
| `tests/contracts/test_recipe_engine_literal_snapshot.py` | Regenerate Phase-3 snapshot. |
| `tests/contracts/_snapshots/recipe_engine.json` (or equivalent) | New snapshot bytes. |
| `tests/unit/recipes/test_recipe_engine_literal_extended.py` | Forward-compat fixture sweep. |

## Out of scope

- **`RagLlmEngine` class definition** — S5-01.
- **Orchestrator writeback branch** — S1-05.
- **`RecipeApplication.tier_evidence`** — S5-02.
- **`RecipeFailureReason` Literal expansion for Phase-7 Chainguard reasons** — Phase 7 ADR amendment.

## Notes for the implementer

- This is one of **exactly two** Phase-3 in-place edits in all of Phase 4 (G15; ADR-P4-001 / ADR-P4-002). Resist the temptation to "improve" anything else in `src/codegenie/recipes/contract.py` (Rule 3 — surgical changes). Phase-3 regression hard-gate (S7-05) catches any drift.
- Snapshot regen mechanics: Phase 0's snapshot-test discipline either (a) uses an `UPDATE_SNAPSHOTS` env var to rewrite the snapshot file, or (b) inlines the expected JSON literal in the test. Match the existing pattern (Rule 11).
- If you find an exhaustive `match` statement on `recipe.engine` anywhere in `src/codegenie/transforms/` or `src/codegenie/recipes/`, do **not** add a `case "rag_llm"` here — that's S1-05's job (the orchestrator writeback stub branch) or Step 5's job (the engine itself). Mypy `assert_never` will catch missed cases at type-check time on those PRs.
- The `phase-3-contract-bumped` label is operational; configure or check the PR template if needed. The label exists to draw reviewer attention to the contract edit. Document it in the PR description with a one-liner: "ADR-P4-001 — additive Literal extension, snapshot regenerated, every Phase-3 fixture re-validated".
- If `RecipeApplication.engine_used` is already a separate Literal field in Phase 3, surface (Rule 12 — fail loud) and extend it in the same PR — the writeback branch in S1-05 reads `engine_used == "rag_llm"`, so they must agree. If the field is currently `str`, leave it — S6-01 / S5-02 will tighten it as part of writeback wiring.
