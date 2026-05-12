# Story S3-06 — `recipes/selector.py` + `selector.yaml` decision table + `RecipeSelection` totality

**Step:** Step 3 — Ship the `NcuRecipeEngine` vertical: `tools/npm` + `tools/ncu` wrappers, `LockfileResolver`, `LockfileCanonicalizer`, recipe catalog + selector
**Status:** Ready
**Effort:** L
**Depends on:** S3-05, S2-06
**ADRs honored:** ADR-0004, ADR-0001, ADR-0002

## Context

The `RecipeSelector` is the closed-enum decision point between the deterministic Phase-3 path and Phase-4's RAG/LLM fallback. ADR-0004 commits the selector to returning a structured `RecipeSelection(recipe, reason, diagnostics)` triple — never `Optional[Recipe]` — so Phase 4 can read *why* the deterministic path missed without expanding the Phase-3 surface. The `reason` enum is **closed in code** (`Literal["matched","no_engine","range_break","peer_dep_conflict","unsupported_dialect","catalog_miss"]`); new reasons require code + schema + tests in the same PR.

The selector consumes `RepoContextView` (S5-02 lands; this story uses a stub view in tests), `CveEntry` (from S2-01), `SkillSlice` (Phase-2 + S1-08's `applies_to.cve_patterns` extension), and the registry (S3-04). It loads `selector.yaml` as a flat decision table and dispatches via Python `match/case`. The `Hypothesis` totality property test is load-bearing: the selector must **never raise** on routine no-match cases (`final-design.md §"Component design" #3` failure section).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #3 (Recipe, RecipeSelector, catalog)` — internal-design five-filter pipeline.
  - `../phase-arch-design.md §"Goals" #3` — `RecipeSelection` triple.
  - `../phase-arch-design.md §"Goals" #12` — no DSL for `selector.yaml`; flat data + closed `reason` enum.
- **Phase ADRs:**
  - `../ADRs/0004-recipe-selection-structured-triple-not-optional.md` — primary contract.
  - `../ADRs/0001-transform-recipe-engine-two-abc-contract.md` — engine availability is part of the match.
- **Source design:**
  - `../final-design.md §Goals #5` — selector triple lineage.
  - `../final-design.md §"Open questions" — diagnostics dict keys` (minimum keys defined).
- **Existing code:**
  - `src/codegenie/recipes/registry.py` (S3-04) — `RecipeRegistry.load`.
  - `src/codegenie/recipes/models.py` (S3-05) — `Recipe`, `ApplyConstraints`.
  - `src/codegenie/recipes/contract.py` (S1-03) — `RecipeEngine` ABC.
  - `src/codegenie/transforms/cve/models.py` (S2-01) — `CveEntry`.
  - `src/codegenie/skills/models.py` (post-S1-08 with `applies_to.cve_patterns`).

## Goal

Ship `src/codegenie/recipes/selector.py` (with `RecipeSelector.select(view, advisory, skills) -> RecipeSelection`) and `src/codegenie/recipes/selector.yaml` (flat decision table). Selector applies the five filters in order, returns `RecipeSelection` for every routine no-match case (Hypothesis-tested totality), and raises only on ambiguity (`priority` tie). At minimum 14 unit tests pin the per-reason × matched/unmatched matrix.

## Acceptance criteria

- [ ] `src/codegenie/recipes/selector.py` exports `RecipeSelection(BaseModel)` with `{recipe: Recipe | None, reason: Literal["matched","no_engine","range_break","peer_dep_conflict","unsupported_dialect","catalog_miss"], diagnostics: dict[str, Any]}`. `extra="forbid"`, `frozen=True`.
- [ ] `RecipeSelector.select(view, advisory, skills, *, engine_availability: dict[str, bool]) -> RecipeSelection`:
  1. Filter by `recipe.applies_to.ecosystem == advisory.ecosystem` → unmatched falls through to `catalog_miss`.
  2. Filter by `applies_to.cve_patterns` matching `advisory.cve_id` (default `["*"]` matches all).
  3. Evaluate `applies_to.semver_range_predicate` against the existing range; falsey → `RecipeSelection(reason="range_break")`.
  4. Check `engine_availability[recipe.engine] is True` → false → `RecipeSelection(reason="no_engine", diagnostics={"engine": recipe.engine, "available": False})`.
  5. Check Phase-2 depgraph peer-dep compatibility (consults `view`) → conflict → `RecipeSelection(reason="peer_dep_conflict", diagnostics={...})`.
  6. If `view.dialect not in {"npm"}` (pnpm-workspace, yarn-classic) → `RecipeSelection(reason="unsupported_dialect", diagnostics={"dialect": view.dialect})`.
- [ ] Among multiple matches, sort by `recipe.priority` ascending; **tie at the same priority → raise `RecipeSelectorAmbiguous`** (loud).
- [ ] `src/codegenie/recipes/selector.yaml` — flat decision table; documented schema; consumed by `match/case` dispatch. The YAML is *data*; the enum is closed in code.
- [ ] Diagnostics dict includes the minimum keys defined by the arch: `{engine, available, why_excluded, candidate_count}` whenever applicable.
- [ ] `tests/unit/recipes/test_selector.py` ships ≥ 14 tests — one per `reason` enum × matched/unmatched paths + the ambiguity-on-priority-tie raise.
- [ ] `tests/unit/recipes/test_selector_is_total.py` — Hypothesis property: for any synthetic `(advisory, view, skills)` permutation, `select` returns a `RecipeSelection` and **does not raise** (except for the ambiguity-tie path, which is excluded by construction).
- [ ] The selector never imports anything under `codegenie.cli` or `codegenie.transforms.coordinator` (one-way dependency).
- [ ] `ruff check`, `mypy --strict`, `pytest` pass.

## Implementation outline

1. Land `tests/unit/recipes/test_selector.py` (with all 14 reason cases as separate functions) + `tests/unit/recipes/test_selector_is_total.py` (Hypothesis) first (red).
2. Implement `src/codegenie/recipes/selector.py`:
   - `class RecipeSelection(BaseModel)` as above.
   - `class RecipeSelectorAmbiguous(RuntimeError)` — typed error.
   - `_load_decision_table(yaml_path) -> DecisionTable`.
   - `_eval_semver_range_predicate(predicate: str, ctx: dict) -> bool` — a tiny pure-function dispatcher; the only supported predicate name in v0.3 is `supports_patched_version` (referenced by S3-05's recipe), implemented as `advisory.first_patched_version is not None and semver_intersects(existing_range, advisory.first_patched_version)`. Future predicates require code + test PR.
   - `class RecipeSelector` with `__init__(self, registry: RecipeRegistry, decision_table_path: Path)`.
   - `select(view, advisory, skills, *, engine_availability)` — runs the five filters; collects candidates; on multiple → sort by `priority`; tie → raise.
3. Land `src/codegenie/recipes/selector.yaml` — minimal content for v0.3 (e.g., dialect allow-list, predicate-name allow-list). Document its schema in the YAML's header comment.
4. Run the Hypothesis property test until the totality invariant holds on ≥ 100 random examples.

## TDD plan — red / green / refactor

### Red
Path: `tests/unit/recipes/test_selector_is_total.py`
```python
import hypothesis.strategies as st
from hypothesis import given, settings

from codegenie.recipes.selector import RecipeSelector, RecipeSelection


@settings(max_examples=200, deadline=None)
@given(
    advisory_ecosystem=st.sampled_from(["npm", "pypi", "maven"]),
    advisory_cve=st.text(min_size=1, max_size=20),
    dialect=st.sampled_from(["npm", "pnpm-workspace", "yarn-classic"]),
    engine_avail=st.dictionaries(
        keys=st.sampled_from(["ncu", "openrewrite"]),
        values=st.booleans(),
    ),
)
def test_selector_never_raises_on_routine_no_match(
    advisory_ecosystem, advisory_cve, dialect, engine_avail,
    selector_under_test, fake_view_factory, fake_advisory_factory, fake_skills,
):
    view = fake_view_factory(dialect=dialect)
    advisory = fake_advisory_factory(ecosystem=advisory_ecosystem, cve_id=advisory_cve)
    result = selector_under_test.select(
        view=view, advisory=advisory, skills=fake_skills,
        engine_availability=engine_avail,
    )
    assert isinstance(result, RecipeSelection)
    assert result.reason in (
        "matched", "no_engine", "range_break",
        "peer_dep_conflict", "unsupported_dialect", "catalog_miss",
    )
```

Path: `tests/unit/recipes/test_selector.py`
```python
import pytest

from codegenie.recipes.selector import RecipeSelectorAmbiguous, RecipeSelection


def test_select_matched_happy_path(selector_under_test, npm_view, cve_express_dos, skills):
    sel = selector_under_test.select(
        view=npm_view, advisory=cve_express_dos, skills=skills,
        engine_availability={"ncu": True, "openrewrite": False},
    )
    assert sel.reason == "matched"
    assert sel.recipe.id == "npm-upgrade-patched-v1"


def test_select_no_engine_when_ncu_unavailable(selector_under_test, npm_view, cve_express_dos, skills):
    sel = selector_under_test.select(
        view=npm_view, advisory=cve_express_dos, skills=skills,
        engine_availability={"ncu": False, "openrewrite": False},
    )
    assert sel.reason == "no_engine"
    assert sel.recipe is None
    assert sel.diagnostics["engine"] == "ncu"
    assert sel.diagnostics["available"] is False


# ... 12 more tests covering range_break, peer_dep_conflict,
#     unsupported_dialect, catalog_miss × matched/unmatched permutations
#     + the ambiguity-tie raise
def test_priority_tie_raises_ambiguous(selector_under_test_with_tied_recipes, npm_view, cve_express_dos, skills):
    with pytest.raises(RecipeSelectorAmbiguous):
        selector_under_test_with_tied_recipes.select(
            view=npm_view, advisory=cve_express_dos, skills=skills,
            engine_availability={"ncu": True, "openrewrite": False},
        )
```

### Green
Implement the five filters in order; the dispatch is a small `for recipe in candidates: ...` loop with explicit early-returns per filter.

### Refactor
- Once S4 onward consumes diagnostics keys, freeze the diagnostics-key contract in a sibling `RecipeSelectionDiagnostics` Pydantic model. Defer for now.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/recipes/selector.py` | New — `RecipeSelector` + `RecipeSelection` |
| `src/codegenie/recipes/selector.yaml` | New — flat decision table (data) |
| `tests/unit/recipes/test_selector.py` | New — ≥ 14 tests |
| `tests/unit/recipes/test_selector_is_total.py` | New — Hypothesis totality |
| `tests/unit/recipes/conftest.py` | New — `selector_under_test`, `npm_view`, `fake_advisory_factory`, etc. |

## Out of scope

- **Engine availability snapshot construction** — handled by S3-07 (where the snapshot is built); this story consumes the dict.
- **`RepoContextView`** — handled by S5-02; this story uses test stubs.
- **Phase-2 depgraph peer-dep query** — `view.peer_dep_conflict_check(...)` is the seam this story uses; the underlying query consumes Phase-2 outputs already present.
- **Phase 4 RAG/LLM wrapping** — handled by Phase 4; this story commits to the `reason` enum that Phase 4 reads.

## Notes for the implementer
- The `reason` enum is **closed in code** — a new value requires editing the `Literal[...]` plus adding a unit test in the same PR (mirror Phase-2's `detect.type` discipline; ADR-0008 of Phase 2).
- The five filters apply **in order**: ecosystem first (cheapest), engine availability fourth (already-computed snapshot lookup), peer-dep conflict fifth (the expensive depgraph traversal). Reorder only with an ADR amendment.
- Hypothesis totality is the single most important invariant in this story. If the property test ever fails with a `RuntimeError`, the selector is buggy — do not catch the exception in the selector to make the test pass.
- `selector.yaml` is **data**, not a DSL. Putting a `match/case` mini-DSL in YAML invites the "templated YAML" antipattern that bit Phase 2's policy authoring. Stay flat.
- The `_eval_semver_range_predicate` dispatcher is a closed allow-list. v0.3 ships exactly one predicate name (`supports_patched_version`). Phase 4 may add `supports_minor_bump`, etc., but each new predicate name must land with its own unit test.
- `peer_dep_conflict_check` should consult `view.build_graph.resolved_edges` if `view.index_health.cve_confidence >= "medium"`; otherwise fall back to `view.build_graph.declared_edges` and downgrade `confidence: medium` in `diagnostics` per the Step 3 risk note in `High-level-impl.md §Step 3 Risks`.
- Per Rule 12: when `reason="no_engine"`, the diagnostics dict must say *which* engine — operators triage from CI logs and need the recipe→engine mapping.
- This selector is **CPU-bounded** (in-memory dispatch). No I/O, no subprocess. Hot-path latency ≤ 5 ms.
