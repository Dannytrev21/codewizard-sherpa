# Story S5-06 — Append RouteDecided before the routing transition

**Step:** Step 5 — Implement the HotViewStore, renderer, and PlannerNode routing core
**Status:** Ready
**Effort:** M
**Depends on:** S3-01, S3-03, S3-04, S5-02
**ADRs honored:** ADR-0007, ADR-0008, ADR-0011, ADR-0003

## Context
This story closes the routing half of exit criterion 1 — "the chosen path is logged on every workflow." It wires `PlannerNode.route` to read `HotViewStore.get_all` for context and to append a `RouteDecided` event via `EventLog.emit_internal` **before** returning the `RouteDecision`. The append is a *precondition of the transition*, not a fire-and-forget side effect: no code path reaches a routing transition without first emitting `RouteDecided`. It completes the `PlannerNode` started in S5-05.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C3 — PlannerNode` — `route()` reads the hot views and appends `RouteDecided` *before* returning
  - `../phase-arch-design.md §C7 — Routing/resolution event emission` — the `RouteDecided` append is a precondition of the routing transition; the `RouteDecided` field shape
  - `../phase-arch-design.md §Process view` — "PN->>EVT: emit_internal(RouteDecided) BEFORE transition"
  - `../phase-arch-design.md §Control flow` — step 4: `route` reads `HotViewStore.get_all(repo)` then emits `RouteDecided` via `emit_internal` *before* returning
  - `../phase-arch-design.md §Gap 4` — `RouteDecided` is workflow-scoped → the `WorkflowInternalEvent` stream
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0007-routing-events-into-existing-event-log.md` — ADR-0007 — emit into the existing `codegenie.plugins.events` log; the append is the append-before-transition precondition; no new event store
  - `../ADRs/0008-route-events-in-the-workflow-internal-stream.md` — ADR-0008 — `RouteDecided` rides the `WorkflowInternalEvent` stream, emitted via `emit_internal` (lock-free), never the BLAKE3-chained spanning stream
  - `../ADRs/0011-fixed-three-step-routing-pipeline.md` — ADR-0011 — `route()` runs the fixed three-step selection (S5-05) before emitting
  - `../ADRs/0003-hot-view-integrity-by-gather-id-content-addressing.md` — ADR-0003 — `route()` reads `get_all`, which is `gather_id`-verified and fail-closed
- **Existing code (if any):**
  - `src/codegenie/planner/routing.py` — `PlannerNode` + the pure selection (S5-05) — `route()` is completed here
  - `src/codegenie/plugins/events.py` — `RouteDecided` variant + `emit_internal` (S3-04 added the variant; `emit_internal` ships)
  - `src/codegenie/hotviews/store.py` — `HotViewStore.get_all` (S5-01/S5-02) — the warm-path read `route()` consumes

## Goal
`PlannerNode.route` reads `HotViewStore.get_all`, runs the fixed selection, and appends `RouteDecided` via `emit_internal` before returning the `RouteDecision` — so the append is a precondition of the routing transition.

## Acceptance criteria
- [ ] `route(self, bundle, hot_views, *, workflow_id, repo_id)` calls `hot_views.get_all(repo_id)` for routing context and runs the S5-05 selection.
- [ ] `route` constructs a `RouteDecided` event (`workflow_id`, `route`, `reason`, `bundle_hash`, optional `recipe_match` / `rag_top_score`) and calls `EventLog.emit_internal(route_decided)` **before** the `return route_decision` statement.
- [ ] The `RouteDecided` event is emitted on every routing outcome — recipe, RAG, and LLM-fallthrough — not just the recipe path.
- [ ] A test running `route()` against an `InMemorySink` `EventLog` confirms exactly one `RouteDecided` event is in the workflow-internal stream after the call, and that its `route` matches the returned `RouteDecision.route`.
- [ ] If `emit_internal` raises, `route` does **not** return a `RouteDecision` (the append is a precondition — a failed append fails the transition).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Complete `PlannerNode.route` in `routing.py`: call `hot_views.get_all(repo_id)`, run the S5-05 selection to a `RouteDecision`.
2. Build a `RouteDecided` (the variant added by S3-04) from the `RouteDecision` + `workflow_id` + the bundle hash.
3. Call `self._event_log.emit_internal(route_decided)` — then, only after it succeeds, `return route_decision`.
4. Do not wrap the emit in a `try/except` that swallows — a failed append must propagate so the transition fails (the precondition discipline).
5. Keep the ordering structurally obvious — the `emit_internal` call is the last statement before `return`, so the S6-05 static AST test can prove no path skips it.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/planner/test_route_emits_route_decided.py`
First red test — `RouteDecided` is appended before the return, on every route:
```python
@pytest.mark.parametrize("scenario", ["recipe", "rag", "llm"])
async def test_route_appends_route_decided_for_every_outcome(scenario) -> None:
    # arrange: ports configured for the scenario; an EventLog over an InMemorySink
    # act:    decision = await planner_node.route(bundle, hot_views,
    #             workflow_id=WID, repo_id=RID)
    # assert: exactly one RouteDecided in the internal stream;
    #         that event.route == decision.route
```
A second red test — the append is a precondition (a failed append fails the transition):
```python
async def test_failed_emit_internal_prevents_the_routing_transition() -> None:
    # arrange: an EventLog whose emit_internal raises
    # act/assert: route(...) raises — it does NOT return a RouteDecision
```
A third red test — `route` reads the hot views:
```python
async def test_route_reads_hot_view_store_get_all() -> None:
    # arrange: a recording HotViewStore
    # act:    await planner_node.route(bundle, hot_views, workflow_id=WID, repo_id=RID)
    # assert: hot_views.get_all was called with repo_id=RID
```
### Green — make it pass
Complete `route()`: read `get_all`, select, build `RouteDecided`, `emit_internal`, then `return`. The smallest version puts `emit_internal` immediately before `return`.
### Refactor — clean up
Type hints (`Bundle`, `HotViewStore`, `WorkflowId`, `RepoId`, `RouteDecision`); docstring on `route` stating the append-before-transition precondition and citing ADR-0007/0008; a functional-core purity AST test confirming the *selection* helper stays pure (`route()` itself is the impure shell — the I/O surface). Confirm `RouteDecided` goes to the internal stream via `emit_internal`, never `emit_spanning`.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/planner/routing.py` | Complete `PlannerNode.route` with the hot-view read and the `RouteDecided` append |
| `tests/unit/planner/test_route_emits_route_decided.py` | The red tests for append-before-transition on every outcome |

## Out of scope
- The static AST test asserting no routing edge skips the append — S6-05 (it operates on `route_node` in `codegenie.supervisor`, downstream of this story).
- `RouteDescended` emission where Phase 4's `FallbackTier` descends — S7-05.
- The `phase08_e2e` routing test (`RouteDecided` in the internal stream for a full fixture workflow) — S7-02.
- The Supervisor `route_node` that calls `PlannerNode.route` — S6-02.

## Notes for the implementer
- The append is a *precondition*, not a side effect (ADR-0007). `emit_internal` must succeed before `route` returns — a `try/except` that swallows the emit failure would make "logged on every workflow" false. If the emit fails, the routing transition fails loud (Rule 12).
- Place the `emit_internal` call as the last statement before `return` so S6-05's static AST test can prove structurally that no path reaches the transition without it. A scattered or conditional emit defeats that proof.
- `RouteDecided` rides the `WorkflowInternalEvent` stream via `emit_internal` (ADR-0008) — *not* `emit_spanning`. Putting it on the spanning stream pays an `fcntl.flock` per routing decision for tamper-evidence the completeness guarantee does not need.
- Emit on *every* outcome — recipe, RAG, and LLM. A common bug is emitting only on the "interesting" path; exit criterion 1 is "logged on *every* workflow."
- `route()` reading `get_all` consumes the S5-02 fail-closed read — the planner never sees a `None` slice and never branches on Redis availability; that is the branchless warm path.
