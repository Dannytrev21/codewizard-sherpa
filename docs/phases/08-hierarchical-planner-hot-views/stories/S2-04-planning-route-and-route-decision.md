# Story S2-04 — Declare the PlanningRoute enum and RouteDecision model

**Step:** Step 2 — Declare the hot-view data model and the Supervisor/routing sum types
**Status:** Ready
**Effort:** S
**Depends on:** S2-01
**ADRs honored:** ADR-0011

## Context
The planner's job is to decide whether a workflow enters at the recipe tier, the RAG tier, or the LLM tier — and to log that decision on every workflow (exit criterion 1). This story lands the two pure declarations behind that decision: `PlanningRoute`, the closed three-member `StrEnum` of routing tiers, and `RouteDecision`, the frozen record the planner returns and the `RouteDecided` event carries. It is foundational, contracts-first work: `PlannerNode.route` (S5-05) returns a `RouteDecision`, `PluginWorkItem`/`Dispatched` (S2-01) carry one, and the `RouteDecided` event variant (S3-04) embeds the `route` field — none of those can be typed until this story lands.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Data model` — the `[contract] routing decision` block: `PlanningRoute(StrEnum)` with `RECIPE/RAG/LLM`, `RouteDecision` (`route`, `reason`, `confidence: Literal["high","medium","low"]`, `candidates_considered: tuple[str, ...]`).
  - `../phase-arch-design.md §C3 — PlannerNode` — the `PlanningRoute` / `RouteDecision` public-interface block; `route()` returns a `RouteDecision`.
  - `../phase-arch-design.md §Agentic best practices` — "Confidence handling": a recipe-index hit is `high`, a RAG hit carries the retrieval-score band, an LLM fallthrough is `low`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0011-fixed-three-step-routing-pipeline.md` — ADR-0011 — exactly three routing tiers (recipe → RAG → LLM), fixed by production ADR-0011; no fourth without an ADR amendment.
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` — the fixed three-tier order recipe-first → RAG → LLM-fallback.
- **Existing code (if any):**
  - `src/codegenie/types/identifiers.py` — the codebase's `StrEnum` / `Literal` discipline; `Confidence` is the `Literal["high","medium","low"]` band used elsewhere (reuse the existing band, do not re-declare).
  - `src/codegenie/probes/base.py` — `confidence: Literal["high", "medium", "low"]` — the canonical honest-confidence band the whole codebase uses.
  - `src/codegenie/plugins/subgraph.py:65` — the frozen-model `ConfigDict` convention.

## Goal
Declare the `PlanningRoute` `StrEnum` (`RECIPE`/`RAG`/`LLM`) and the frozen `RouteDecision` model in `codegenie/planner/model.py`, so the planner, the Supervisor decision variants, and the routing event variants all have a typed routing-tier contract.

## Acceptance criteria
- [ ] `codegenie/planner/model.py` declares `PlanningRoute(StrEnum)` with exactly three members: `RECIPE = "recipe"`, `RAG = "rag"`, `LLM = "llm"`.
- [ ] `RouteDecision` is a frozen model (`model_config = ConfigDict(frozen=True, extra="forbid")`) with `route: PlanningRoute`, `reason: str`, `confidence: Literal["high", "medium", "low"]`, `candidates_considered: tuple[str, ...]`.
- [ ] `PlanningRoute("recipe")` resolves to `PlanningRoute.RECIPE` and `PlanningRoute.RECIPE == "recipe"` (it is a `StrEnum` — string-comparable).
- [ ] A `match` over a `PlanningRoute` value covering the three members and ending in `assert_never` type-checks under `mypy --strict`.
- [ ] The two new public names are listed in `codegenie/planner/__init__.py.__all__`; the running ≤ 24 public-surface count is noted in the attempt log.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Create `codegenie/planner/` with `__init__.py` and `model.py`.
2. Declare `PlanningRoute(StrEnum)` with the three members.
3. Declare `RouteDecision` frozen, with the four fields. Reuse the existing `Confidence` `Literal["high","medium","low"]` band if one is already importable (`probes/base.py` uses it inline); otherwise an inline `Literal` is acceptable — do not invent a new confidence enum.
4. Export `PlanningRoute` and `RouteDecision` via `__init__.py.__all__`.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/planner/test_route_decision.py`

```python
def test_planning_route_has_exactly_three_members() -> None:
    # WHY: ADR-0011 fixes exactly three routing tiers; a fourth member would
    # need an ADR amendment — this test calcifies the closed set.
    assert {r.value for r in PlanningRoute} == {"recipe", "rag", "llm"}

def test_planning_route_is_string_comparable() -> None:
    # WHY: PlanningRoute is a StrEnum so it round-trips cleanly through the
    # RouteDecided event's JSON and equals its string value.
    assert PlanningRoute.RECIPE == "recipe"
    assert PlanningRoute("llm") is PlanningRoute.LLM

def test_route_decision_is_frozen_and_forbids_extra() -> None:
    # WHY: a RouteDecision is an immutable logged record — mutation would
    # desync the RouteDecided event from the dispatched payload; an unexpected
    # field must be a loud ValidationError, not a silently-absorbed key.
    d = RouteDecision(route=PlanningRoute.RECIPE, reason="recipe lodash-bump matched",
                      confidence="high", candidates_considered=("lodash-bump",))
    with pytest.raises(ValidationError):
        d.reason = "changed"
    with pytest.raises(ValidationError):
        RouteDecision(route=PlanningRoute.RAG, reason="x", confidence="high",
                      candidates_considered=(), unexpected="y")
```

### Green — make it pass
Declare `PlanningRoute(StrEnum)` and the frozen `RouteDecision`. Smallest shape — no routing logic (S5-05), no event wiring (S3-04).

### Refactor — clean up
Docstrings naming the ADR-0011 lineage and the honest-confidence band (a recipe hit is `high`, a RAG hit carries the score band, an LLM fallthrough is `low`). Confirm the `confidence` field reuses the codebase's canonical `Literal["high","medium","low"]` band rather than a new type. Add a module comment that `PlanningRoute` is closed — a fourth tier is an ADR-0011 amendment, not a free edit.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/planner/__init__.py` | New package; `__all__` exports `PlanningRoute`, `RouteDecision`. |
| `src/codegenie/planner/model.py` | Declares `PlanningRoute` and `RouteDecision`. |
| `tests/unit/planner/test_route_decision.py` | Red tests: closed three-member set, string-comparability, frozen + `extra="forbid"`. |

## Out of scope
- `PlannerNode` and the fixed three-step routing pipeline — S5-05.
- The `RecipeMatchPort` / `SolvedExampleRagPort` / `LeafLlmPort` `Protocol`s — S3-01.
- The `RouteDecided` / `RouteDescended` event variants that carry a `route` field — S3-04.
- The append-before-transition wiring — S5-06.

## Notes for the implementer
- `PlanningRoute` is a `StrEnum`, not a Pydantic discriminated union — it has no `kind` discriminator. It is a closed enum of *labels*, not a sum type of *records*. Do not over-model it.
- ADR-0011 §Reversibility note is partly an anti-decision: a registry (`@register_planning_step`) for these three tiers was deliberately rejected. Do not add registry machinery — three fixed members of a `StrEnum` is the honest shape.
- Reuse the codebase's `Literal["high","medium","low"]` confidence band (`probes/base.py` is the canonical site). The whole codebase reports honest confidence on this exact band — a new enum here would fork it (Rule 11).
- `candidates_considered: tuple[str, ...]` is a tuple, not a list — frozen models carry immutable collections; mirror the codebase's tuple-for-frozen-collections convention.
- This story has no dependency on S2-02/S2-03; it depends only on S2-01 because the manifest sequences the package skeletons. `codegenie/planner/model.py` must not import `codegenie.supervisor` (the supervisor depends on the planner, not the reverse).
