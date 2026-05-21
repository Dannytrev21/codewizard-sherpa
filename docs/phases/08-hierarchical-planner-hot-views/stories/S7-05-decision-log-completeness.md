# Story S7-05 — Add the decision-log completeness adversarial test and RouteDescended wiring

**Step:** Step 7 — Close the exit criteria: latency, decision-log completeness, and adversarial gates
**Status:** Ready
**Effort:** M
**Depends on:** S6-04
**ADRs honored:** ADR-0007, ADR-0008

## Context
Exit criterion 1 — "the chosen path is logged on every workflow" — is true *by construction* (S5-06 makes the `RouteDecided` append a precondition of the routing transition; S6-05 proves it statically). This story adds the *empirical* proof: run N fixture workflows across recipe / RAG / LLM routes and assert exactly N `RouteDecided` events land in the workflow-internal stream — no workflow silently skips its log. It also wires `RouteDescended` emission where Phase 4's `FallbackTier` descends a route (edge case 8), so route-misprediction stops being a hidden number and becomes a measured one. This is the final exit-criteria closeout for the routing half of Phase 8.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Testing strategy / Adversarial tests` — "**Decision-log completeness** — run N fixture workflows across recipe/LLM routes; assert exactly N `RouteDecided` events, the shipped chain verifies end-to-end, and a deliberately-introduced chain gap is caught by the shipped `ChainTamperDetected` path."
  - `../phase-arch-design.md §Edge cases` — edge case 8: "`route()` mispredicts (recipe stale) … `FallbackTier` descends recipe→RAG→LLM (Phase 4 unchanged); `RouteDescended` appended; the misprediction rate becomes a measured number."
  - `../phase-arch-design.md §C7 — Routing/resolution event emission` — the `RouteDescended` model shape (`from_route`, `to_route`, `reason`).
  - `../phase-arch-design.md §Integration with Phase 9` — Gap-4 note: routing events are workflow-scoped; the completeness test asserts on the internal stream.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0007-routing-events-into-existing-event-log.md` — ADR-0007 §Consequences — "A decision-log completeness adversarial test runs N fixture workflows and asserts exactly N `RouteDecided` events." Routing events emit into the existing `EventLog`, no new store.
  - `../ADRs/0008-route-events-in-the-workflow-internal-stream.md` — ADR-0008 §Consequences — "The decision-log completeness adversarial test asserts *N `RouteDecided` events in the internal stream* for N workflows; it uses the *spanning* stream's `ChainTamperDetected` path only for events that actually ride the chain." `RouteDecided` / `RouteDescended` are *not* chained — do not assert a hash chain over them.
- **Existing code (if any):**
  - `src/codegenie/plugins/events.py` — `RouteDecided` / `RouteDescended` variants (added S3-04), `_INTERNAL_CLASSES`, `emit_internal`, `replay`.
  - `src/codegenie/planner/routing.py` — `PlannerNode.route` emits `RouteDecided` (S5-06).
  - Phase 4's `FallbackTier` descent code — search `src/codegenie/transforms/` or the Phase-4 plugin code for where a route descends recipe→RAG→LLM; that is the call site `RouteDescended` emission hooks into.
  - `tests/integration/test_event_replay.py` — the `EventLog.replay` + `InMemorySink` pattern.

## Goal
Add an adversarial test asserting exactly N `RouteDecided` events for N fixture workflows, and wire `RouteDescended` emission at Phase 4's `FallbackTier` descent so route misprediction is a measured number.

## Acceptance criteria
- [ ] An adversarial test runs N (N ≥ 3) fixture workflows spanning recipe-hit, RAG-hit, and LLM-fallthrough routes through the full Supervisor path, then asserts via `EventLog.replay` over the **workflow-internal** stream that exactly N `RouteDecided` events are present — one per workflow, none missing, none duplicated.
- [ ] The test asserts each `RouteDecided` event's `workflow_id` maps to a distinct fixture workflow (the count is N *distinct* workflows, not N events for one workflow).
- [ ] `RouteDescended` is emitted via `emit_internal` at the point where Phase 4's `FallbackTier` descends a route (recipe→RAG or RAG→LLM), carrying `from_route`, `to_route`, and a `reason`.
- [ ] A test exercises a misprediction fixture (a stale-recipe route that descends) and asserts a `RouteDescended` event with the correct `from_route` / `to_route` lands in the internal stream.
- [ ] The completeness test does **not** assert a BLAKE3 chain over `RouteDecided` / `RouteDescended` — they are unchained `WorkflowInternalEvent`s (ADR-0008); any chain assertion belongs only to genuinely spanning events.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Build (or reuse) N fixture workflows — at minimum one per route tier (recipe-eligible Node/npm, no-recipe Node/npm for LLM fallthrough, a RAG-hit fixture via a fake `SolvedExampleRagPort`).
2. Run each through `run_supervisor` against one shared `InMemorySink`-backed `EventLog`.
3. Replay the internal stream, filter for `RouteDecided`, assert `len == N` and the `workflow_id`s are the N distinct fixtures.
4. Locate Phase 4's `FallbackTier` descent call site; add a `RouteDescended` `emit_internal` call there with `from_route` / `to_route` / `reason` populated from the descent.
5. Write a misprediction-fixture test driving a route descent and asserting the `RouteDescended` event.
6. Confirm the new emission edge is covered by the S6-05 static AST test scope, or extend that test if `RouteDescended` introduces a new transition edge.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/adv/phase08/test_decision_log_completeness.py`

```python
async def test_n_workflows_yield_exactly_n_route_decided_events(
    route_fixtures, redis_container
) -> None:
    # WHY: exit criterion 1 — "logged on every workflow." A workflow that
    # silently skips its RouteDecided append is the failure this test exists
    # to catch; N workflows must produce exactly N events, no more, no fewer.
    sink = InMemorySink()
    event_log = EventLog(internal_sink=sink, ...)
    for state in route_fixtures:          # recipe, rag, llm — N distinct workflows
        await run_supervisor(graph(event_log), state)

    decided = [e for e in event_log.replay_internal() if isinstance(e, RouteDecided)]
    assert len(decided) == len(route_fixtures)
    assert {e.workflow_id for e in decided} == {s.workflow_id for s in route_fixtures}


async def test_fallback_descent_emits_route_descended(stale_recipe_fixture) -> None:
    # WHY: edge case 8 — a route misprediction must be a MEASURED number.
    # When FallbackTier descends recipe->RAG, a RouteDescended event records it.
    ...
    descended = [e for e in event_log.replay_internal() if isinstance(e, RouteDescended)]
    assert len(descended) == 1
    assert descended[0].from_route == PlanningRoute.RECIPE
    assert descended[0].to_route == PlanningRoute.RAG
```

### Green — make it pass
The completeness test passes without new code (S5-06 already makes the append a precondition). The `RouteDescended` test needs the new emission edge: add one `emit_internal(RouteDescended(...))` call at Phase 4's `FallbackTier` descent point — the smallest edit that records the descent. Do not add retry or fallback *logic* — Phase 4 owns the descent; Phase 8 only logs it.

### Refactor — clean up
Module docstring naming exit criterion 1 and edge case 8; type hints on fixtures; a `replay_internal` helper if the `EventLog` API needs a thin wrapper. Honor §Harness engineering — `RouteDescended` emission logs via `emit_internal` (unchained, ADR-0008), and the descent reason is human-readable.

## Files to touch
| Path | Why |
|---|---|
| `tests/adv/phase08/test_decision_log_completeness.py` | The N-workflows-→-N-events completeness test + the descent test (new file). |
| Phase 4 `FallbackTier` descent module (`src/codegenie/...`) | Add the `RouteDescended` `emit_internal` call at the descent point. |
| `tests/adv/phase08/conftest.py` | Route-tier fixtures + the stale-recipe misprediction fixture, if not reusable. |

## Out of scope
- The `phase08_e2e` single-workflow routing test — that is S7-02 (this story is the *completeness* counterpart over N workflows).
- The Redis-tamper adversarial tests — S7-04.
- Any change to Phase 4's `FallbackTier` descent *logic* — Phase 8 only adds the `RouteDescended` emission; the descent behavior is Phase 4's, unchanged (edge case 8: "Phase 4 unchanged").
- A standalone routing-decision store — ADR-0007 forbids it; routing events ride the existing `EventLog`.

## Notes for the implementer
- ADR-0008: assert N events on the **internal** stream, and do **not** assert a hash chain — `RouteDecided` / `RouteDescended` are unchained. A test that expects `ChainTamperDetected` over them would be wrong by construction.
- "Exactly N" means both directions — N missing events fails *and* N+1 (a duplicate append) fails. Assert the count and the distinct `workflow_id` set, not just `>= N`.
- The `RouteDescended` edit touches Phase 4 code — keep it surgical (Rule 3): one `emit_internal` call at the existing descent point, no refactor of the `FallbackTier`.
- Edge case 8 is explicit that Phase 4 is unchanged — Phase 8 *observes* the descent, it does not cause or alter it. The `RouteDescended` event is a measurement, not a control.
- If `RouteDescended` emission creates a new transition edge in routing code, confirm S6-05's static append-before-transition AST test still holds (or extend it) so the new edge cannot skip its log either.

## ADRs honored
- **ADR-0007** — routing/resolution events emit into the existing `EventLog`; the completeness test asserts against it, no new store.
- **ADR-0008** — the completeness test asserts N events in the workflow-internal stream; `RouteDescended` emits via `emit_internal`, unchained.
