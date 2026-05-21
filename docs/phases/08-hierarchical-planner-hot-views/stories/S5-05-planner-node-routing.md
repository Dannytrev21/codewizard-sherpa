# Story S5-05 — Implement the PlannerNode three-step routing pipeline

**Step:** Step 5 — Implement the HotViewStore, renderer, and PlannerNode routing core
**Status:** Ready
**Effort:** M
**Depends on:** S2-02
**ADRs honored:** ADR-0011

## Context
`PlannerNode` is the routing core: it decides whether a workflow enters at the recipe tier, the RAG tier, or the LLM tier. ADR-0011 fixes this as a three-step pipeline — an ordered `tuple[(PlanningRoute, port-callable), ...]` iterated in order, first hit wins, fallthrough is `LLM` — never a registry, never a class hierarchy. This story builds `PlannerNode` and the pure selection logic; the hot-view read and the `RouteDecided` append wiring land in S5-06, which makes the selection a complete `route()` method.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C3 — PlannerNode` — the public interface (`__init__`, `route`), the fixed-ordered-tuple internal structure, "the selection logic is pure and 100%-branch-covered"
  - `../phase-arch-design.md §Control flow` — D4: recipe match → `RECIPE`; no recipe, RAG hit → `RAG`; neither → `LLM` (fallthrough)
  - `../phase-arch-design.md §Patterns considered and deliberately rejected` — Strategy registry / `@register_planning_step` and Chain of responsibility both rejected
  - `../phase-arch-design.md §Data model` — `PlanningRoute` `StrEnum`, `RouteDecision` frozen model
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0011-fixed-three-step-routing-pipeline.md` — ADR-0011 — a fixed ordered `tuple`, first hit wins, `LLM` fallthrough; `RecipeMatchPort` / `SolvedExampleRagPort` / `LeafLlmPort` Protocols; no registry, no CoR; 100% branch coverage on the selection
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` — the fixed recipe→RAG→LLM tier order
- **Existing code (if any):**
  - `src/codegenie/planner/model.py` — `PlanningRoute`, `RouteDecision` (S2-04) — `route()` returns a `RouteDecision`
  - `src/codegenie/planner/ports.py` — `RecipeMatchPort`, `SolvedExampleRagPort`, `LeafLlmPort` Protocols + `RecipeMatch` / `RagHit` result models (S3-01) — the injected dependencies
  - `src/codegenie/planner/null_rag.py` — `NullRagPort` (S3-03) — the Phase-8 concrete RAG port for tests
  - `src/codegenie/plugins/bundle.py` — `Bundle` — the input `route` is handed

## Goal
`PlannerNode` exists with a pure first-hit-wins selection over the fixed recipe→RAG→LLM tuple, defaulting to `LLM` when no tier hits.

## Acceptance criteria
- [ ] `PlannerNode.__init__(*, recipe_port, rag_port, llm_port, event_log)` exists; the routing tiers are held as a fixed ordered `tuple[(PlanningRoute, port-callable), ...]` — not a registry, not a class hierarchy.
- [ ] The selection is pure: given a recipe hit it yields `RECIPE`; given no recipe but a RAG hit it yields `RAG`; given neither it yields `LLM` (fallthrough).
- [ ] The selection logic has 100% branch coverage over the three outcomes (recipe-hit / RAG-hit / LLM-fallthrough) — fake ports drive each.
- [ ] The first hit wins: a recipe hit short-circuits before the RAG port is consulted (verified by a fake RAG port asserting it was not called).
- [ ] `RouteDecision.confidence` reflects the tier: a recipe-index hit is `high`, an LLM fallthrough is `low`.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Create `src/codegenie/planner/routing.py`.
2. `PlannerNode.__init__` stores the three injected ports and the `EventLog`; build the fixed ordered tuple of `(PlanningRoute, port-coroutine)` from the recipe and RAG ports.
3. Implement a pure async selection helper: iterate the tuple, `await` each port-callable, return the first `(route, evidence)` whose port hits; if none hits, return `(LLM, fallthrough)`.
4. Map the selection result to a `RouteDecision` (route, reason, confidence band, `candidates_considered`).
5. Keep `route()` itself minimal here — S5-06 adds the hot-view read and the `RouteDecided` append; this story may stub `route()` to call the selection or expose the selection as a separately-testable method.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/planner/test_routing_selection.py`
One red test per outcome. Recipe hit:
```python
async def test_recipe_hit_routes_to_recipe_and_skips_rag() -> None:
    # arrange: recipe_port returns a RecipeMatch; a rag_port that records calls
    # act:    decision = await planner_node._select(bundle)   # the pure selection
    # assert: decision.route is PlanningRoute.RECIPE; rag_port was NOT called;
    #         decision.confidence == "high"
```
RAG hit:
```python
async def test_no_recipe_rag_hit_routes_to_rag() -> None:
    # arrange: recipe_port returns None; rag_port returns a RagHit
    # act/assert: decision.route is PlanningRoute.RAG
```
LLM fallthrough:
```python
async def test_no_recipe_no_rag_falls_through_to_llm() -> None:
    # arrange: recipe_port returns None; rag_port (NullRagPort) returns None
    # act/assert: decision.route is PlanningRoute.LLM; decision.confidence == "low"
```
### Green — make it pass
Implement `PlannerNode` and the pure selection over the fixed tuple. The smallest version iterates the tuple, returns the first hit, falls through to `LLM`.
### Refactor — clean up
Type hints on every signature (`RecipeMatchPort`, `SolvedExampleRagPort`, `LeafLlmPort`, `EventLog`, `Bundle`, `RouteDecision`); docstring on `PlannerNode` and the selection stating the fixed-pipeline / first-hit-wins / `LLM`-fallthrough contract; reference ADR-0011 in the docstring so a future reader sees the fixed shape is deliberate. Confirm `routing.py` imports no LLM SDK (it will be `import-linter`-fenced by S1-03).

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/planner/routing.py` | New module — `PlannerNode` and the pure selection |
| `src/codegenie/planner/__init__.py` | Export `PlannerNode` (counts against the ≤24 surface budget) |
| `tests/unit/planner/test_routing_selection.py` | The red tests for the three outcomes |

## Out of scope
- The hot-view read (`HotViewStore.get_all`) inside `route()` and the `RouteDecided` append-before-transition — S5-06 (extends this same `PlannerNode`).
- The functional-core purity AST test for the selection — fold into S5-06 once `route()` is complete, or add a `tests/.../test_routing_purity.py` here covering the selection helper only.
- The `import-linter` LLM-SDK fence group — S1-03 (this story must just not import an LLM SDK).

## Notes for the implementer
- ADR-0011 is partly an anti-decision: do not introduce a `@register_planning_step` registry or a Chain-of-Responsibility handler hierarchy. Three ADR-0011-fixed steps are an ordered `tuple` iterated — a registry for three known steps is premature pluggability the ADR explicitly forbids.
- First hit wins and short-circuits: a recipe hit must not consult the RAG port. The "skips RAG" test is the guard — a naive implementation that evaluates all three ports then picks would pass the route assertion but fail this one.
- The RAG port in Phase 8 is `NullRagPort` (S3-03) — it always returns `None`, so in practice Phase 8 routes recipe-or-LLM. The RAG branch is structurally present and fake-port-tested; Phase 11 swaps the adapter with zero routing-code change.
- Rule 5: a recipe-existence check is plain code (a key-membership test against the plugin's `RecipeRegistry`), not a judgment call — no LLM in the selection. The LLM is reached only *through* `LeafLlmPort`, never inside `route()`.
- Confidence is honest (CLAUDE.md §Honest confidence): a recipe-index hit is `high`; an LLM fallthrough is `low`; a RAG hit carries the retrieval score's band.
