# Story S3-01 — Declare the planner ports and result models

**Step:** Step 3 — Declare the planner ports and extend the event union
**Status:** Ready
**Effort:** S
**Depends on:** S2-01
**ADRs honored:** ADR-0011

## Context
Phase 8's `PlannerNode` makes the recipe→RAG→LLM routing decision by crossing technology boundaries (a recipe registry, a future Knowledge Graph, an LLM). The hexagonal pattern fixes those boundaries as `Protocol`s **before** either the routing logic (`PlannerNode`, S5-05) or any concrete adapter (`NullRagPort`, S3-03) is written, so the routing core stays LLM-free and `import-linter`-fenceable. This story is foundational: it lands the three Ports and the two small result models every later planner story imports.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C3 — PlannerNode (codegenie.planner)` — the `RecipeMatchPort` / `SolvedExampleRagPort` / `LeafLlmPort` `Protocol` signatures and the `RouteDecision` shape.
  - `../phase-arch-design.md §Development view` — `planner/ports.py` holds the three Ports; `planner/model.py` (S2-04) holds `PlanningRoute`/`RouteDecision`.
  - `../phase-arch-design.md §Design patterns applied` — "Hexagonal / ports & adapters + dependency inversion" row.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0011-fixed-three-step-routing-pipeline.md` — ADR-0011 — each tier is reached through a `Protocol` Port; concrete adapters are injected; the RAG port is a `NullRagPort` in Phase 8.
- **Existing code (if any):**
  - `src/codegenie/plugins/events.py §EventStreamSink` — a shipped `@runtime_checkable Protocol` precedent — mirror its declaration style.
  - `src/codegenie/plugins/bundle.py:227 class Bundle` — the `Bundle` type all three Port methods accept.
  - `src/codegenie/types/identifiers.py` — `RecipeId`, `RepoId` (added by S1-01) — never raw `str` for domain IDs.

## Goal
Declare `RecipeMatchPort`, `SolvedExampleRagPort`, and `LeafLlmPort` as `Protocol`s plus the frozen `RecipeMatch` and `RagHit` result models so the routing pipeline has a fixed hexagonal boundary.

## Acceptance criteria
- [ ] `codegenie/planner/ports.py` exists declaring `RecipeMatchPort`, `SolvedExampleRagPort`, `LeafLlmPort` as `Protocol`s with the signatures `async def match(self, bundle: Bundle) -> RecipeMatch | None`, `async def query(self, bundle: Bundle) -> RagHit | None`, `async def is_available(self) -> bool`.
- [ ] `RecipeMatch` and `RagHit` are frozen Pydantic models (`ConfigDict(frozen=True, extra="forbid")`); `RecipeMatch` carries a `RecipeId` and a `confidence: Literal["high","medium","low"]`; `RagHit` carries a `top_score: float` and an `example_ids: tuple[str, ...]`.
- [ ] All three Ports are `@runtime_checkable` so S3-03's `Protocol`-assignment test can `isinstance`-check an adapter.
- [ ] `codegenie/planner/__init__.py` exists and re-exports only the names other packages need via `__all__`; package-internal names stay unexported.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Create `src/codegenie/planner/__init__.py` and `src/codegenie/planner/ports.py`.
2. In `ports.py`, declare `RecipeMatch` and `RagHit` as frozen Pydantic models with the fields above.
3. Declare the three `@runtime_checkable Protocol`s with the exact async signatures from §C3.
4. Set `__all__` in `ports.py` and re-export the public subset through `planner/__init__.py`'s `__all__` (track against the ≤24-name budget).
5. Run `mypy --strict src/codegenie/planner/` — `Protocol`s with `...` bodies must type-check clean.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/planner/test_ports.py`
Assert the Ports are structurally usable and the result models are frozen.
```python
def test_recipe_match_port_is_runtime_checkable_protocol() -> None:
    # arrange: a trivial object exposing async match(bundle) -> RecipeMatch | None
    # act:    isinstance(fake, RecipeMatchPort)
    # assert: True — the Protocol is @runtime_checkable and structural
    ...

def test_recipe_match_is_frozen() -> None:
    # arrange: build a RecipeMatch(recipe_id=..., confidence="high")
    # act:    attempt m.confidence = "low"
    # assert: pydantic raises ValidationError — frozen=True holds
    ...
```
### Green — make it pass
Create `ports.py` with the two frozen models and the three `@runtime_checkable Protocol`s; create the `planner/__init__.py` package marker. Bodies are `...`.
### Refactor — clean up
Add module + class docstrings naming ADR-0011. Confirm `RagHit.top_score` is a plain `float` (no clamping — that is the adapter's job). Verify no I/O import lands in `ports.py` (pure declarations). Confirm the public-surface count stays within the ≤24-name budget; note the running total in the attempt log.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/planner/__init__.py` | New package marker + bounded `__all__`. |
| `src/codegenie/planner/ports.py` | The three Ports + `RecipeMatch` / `RagHit` result models. |
| `tests/unit/planner/test_ports.py` | Red test — Protocol structural check + frozen-model check. |

## Out of scope
- `PlanningRoute` / `RouteDecision` — S2-04 (`planner/model.py`).
- `NullRagPort` concrete adapter — S3-03.
- `PlannerNode` and the routing pipeline — S5-05.
- `_WARNING_IDS` for the `planner` package — S3-05.

## Notes for the implementer
- Ports are **declarations only** — no logic, no I/O, no concrete class. A `Protocol` with `...` bodies is the entire deliverable for the three Ports.
- Use `Protocol` (structural), not `ABC` (nominal) — `NullRagPort` (S3-03) must satisfy `SolvedExampleRagPort` by shape, never by inheritance.
- All three methods are `async` — they front async-capable adapters even though the Phase-8 `NullRagPort` does no real I/O.
- Do not import any LLM SDK here; `codegenie.planner.routing` is fenced (S1-03), and keeping `ports.py` clean keeps the whole package fence-trivial.
- Track the bounded public surface (≤24 names across the four new packages) from this story onward — surface any pressure in the attempt log, never silently widen `__all__`.
