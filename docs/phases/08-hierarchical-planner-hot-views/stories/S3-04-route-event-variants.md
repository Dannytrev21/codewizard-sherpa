# Story S3-04 — Add the RouteDecided/RouteDescended event variants

**Step:** Step 3 — Declare the planner ports and extend the event union
**Status:** Ready
**Effort:** S
**Depends on:** S1-03, S2-03
**ADRs honored:** ADR-0007, ADR-0008

## Context
Phase 8's exit criterion 1 — "the chosen path is logged on every workflow" — must be true *by construction*. Rather than build a standalone event store (which would front-run Phase 9's canonical log and give Phase 11/13 two sources of truth), Phase 8 adds two `Literal`-tagged Pydantic event variants to the **existing** `codegenie.plugins.events` log. This story is the load-bearing half of exit criterion 1: it lands `RouteDecided` and `RouteDescended` in the correct stream so S5-06 can append `RouteDecided` before every routing transition.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C7 — Routing/resolution event emission` — the exact `RouteDecided` / `RouteDescended` Pydantic field shapes.
  - `../phase-arch-design.md §Gap 4 — the event log is two-stream` — why the variants go in `WorkflowInternalEvent`, not the BLAKE3-chained spanning stream.
  - `../phase-arch-design.md §Integration with Phase 9` — "Note (Gap 4)": `RouteDecided`/`RouteDescended` are workflow-scoped; they belong in the workflow-internal stream Phase 9 ports to Temporal history.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0007-routing-events-into-existing-event-log.md` — ADR-0007 — no standalone event store; two `Literal`-tagged variants added to the existing union; the append is a precondition of the routing transition.
  - `../ADRs/0008-route-events-in-the-workflow-internal-stream.md` — ADR-0008 — the variants go in `WorkflowInternalEvent` / `_INTERNAL_CLASSES` / `__all__`, emitted via `emit_internal`; **not** the BLAKE3-chained spanning stream.
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0034-event-sourcing-canonical-primitive.md` — Phase 9 re-points `codegenie.plugins.events` as a projection of the canonical log; Phase 8 emits in the shape Phase 9 adopts.
- **Existing code (if any):**
  - `src/codegenie/plugins/events.py` — `PluginResolved` (line ~174) and `BundleBuilt` (line ~187) are the precedent variants: same `event_type` `Literal` tag, same frozen-model shape, same placement in `WorkflowInternalEvent` (line ~476) and `_INTERNAL_CLASSES` (line ~512); `emit_internal` is at line ~764, `replay` at ~810.
  - `src/codegenie/planner/model.py` (S2-04) — `PlanningRoute` `StrEnum`, imported by both new events.

## Goal
Add `RouteDecided` and `RouteDescended` as `Literal`-tagged variants of `WorkflowInternalEvent`, wired into `_INTERNAL_CLASSES` and `__all__`, so routing decisions ride the existing workflow-internal event stream.

## Acceptance criteria
- [ ] `RouteDecided` and `RouteDescended` are frozen Pydantic models (`ConfigDict(frozen=True, extra="forbid")`) in `src/codegenie/plugins/events.py`, with `event_type` `Literal` tags `"route_decided"` and `"route_descended"` respectively, matching the §C7 field shapes (`RouteDecided`: `event_id`, `workflow_id`, `timestamp`, `route`, `reason`, `bundle_hash`, `recipe_match`, `rag_top_score`; `RouteDescended`: `event_id`, `workflow_id`, `timestamp`, `from_route`, `to_route`, `reason`).
- [ ] Both variants are added to the `WorkflowInternalEvent` `Annotated[... , Field(discriminator="event_type")]` union, to the `_INTERNAL_CLASSES` tuple, and to the module `__all__` — three reviewable wiring edits.
- [ ] A test confirms `RouteDecided` and `RouteDescended` round-trip through `EventLog.emit_internal` then `EventLog.replay` against an `InMemorySink` — emit, replay, assert byte-equal.
- [ ] A test confirms `RouteDecided` is a member of `WorkflowInternalEvent` and **not** of `WorkflowSpanningEvent` (it pays no `fcntl.flock` per routing decision — ADR-0008).
- [ ] No existing event variant is moved, renamed, or its tag changed.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. In `events.py`, declare `RouteDecided` and `RouteDescended` next to the existing `WorkflowInternalEvent` member classes, mirroring the `PluginResolved` declaration style (frozen, `extra="forbid"`, `event_type` `Literal` default).
2. Import `PlanningRoute` from `codegenie.planner.model` for the `route` / `from_route` / `to_route` fields.
3. Add both classes to the `WorkflowInternalEvent` union, to `_INTERNAL_CLASSES`, and to `__all__`.
4. Confirm `_INTERNAL_ADAPTER`'s `TypeAdapter[WorkflowInternalEvent]` picks the new variants up automatically (it rebuilds from the union).
5. Run `mypy --strict src/` and `make check` — the discriminated-union edit is compiler-policed.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/plugins/test_route_events.py`
Assert the variants round-trip through the internal stream and are not in the spanning stream.
```python
async def test_route_decided_round_trips_through_internal_stream() -> None:
    # arrange: an EventLog over an InMemorySink; build a RouteDecided(...)
    # act:    log.emit_internal(evt); replay the internal stream
    # assert: the replayed event equals the emitted RouteDecided (discriminator resolves it)

def test_route_decided_is_internal_not_spanning() -> None:
    # arrange: import RouteDecided, _INTERNAL_CLASSES, _SPANNING_CLASSES
    # act:    membership checks
    # assert: RouteDecided in _INTERNAL_CLASSES and RouteDecided not in _SPANNING_CLASSES
    #         — ADR-0008: routing events are workflow-scoped, lock-free
```
### Green — make it pass
Declare the two frozen models; wire them into the union, `_INTERNAL_CLASSES`, and `__all__`. No new module — strictly additive edits to `events.py`.
### Refactor — clean up
Docstrings on both classes naming ADR-0007/0008. Confirm `recipe_match: str | None = None` and `rag_top_score: float | None = None` carry defaults (a recipe route has no `rag_top_score`; an LLM route has neither). Verify the existing `events.py` tests still pass — no variant was disturbed. Note in the attempt log that these two names are *not* in the four-new-package `__all__` budget (they live in the shipped `events.py`).

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/plugins/events.py` | Add `RouteDecided` / `RouteDescended` + three wiring edits (union, `_INTERNAL_CLASSES`, `__all__`). |
| `tests/unit/plugins/test_route_events.py` | Red test — internal-stream round-trip + not-spanning membership. |

## Out of scope
- Appending `RouteDecided` from `PlannerNode.route` — S5-06 (the append-before-transition wiring).
- Emitting `RouteDescended` where Phase 4's `FallbackTier` descends — S7-05.
- The static AST test that no routing edge skips the append — S6-05.
- The decision-log completeness adversarial test — S7-05.

## Notes for the implementer
- This is an **additive edit to a shipped file**, not a new module — exactly the loud, compiler-policed `Literal`-variant addition commitment §5 sanctions. The three wiring lines (union member, `_INTERNAL_CLASSES` entry, `__all__` entry) must *all* land — a missing one is a silent bug the discriminated-union test should catch.
- ADR-0008 is the trap to avoid: do **not** add these to `WorkflowSpanningEvent`. The synthesis's `final-design.md` prose calls the log a "hash-chained log" — that conflates the two streams. Routing events are per-workflow, lock-free, and ride `WorkflowInternalEvent`, matching the `PluginResolved` precedent.
- Mirror `PluginResolved`'s exact shape: `event_type` is a `Literal` with a default value, the model is frozen with `extra="forbid"`, and `event_id` / `workflow_id` / `timestamp` are the standard envelope fields.
- The `route` field's type is `PlanningRoute` (the S2-04 `StrEnum`), not a raw `str` — this creates an import edge `codegenie.plugins.events → codegenie.planner.model`; confirm that edge does not violate `import-linter` (model.py is pure declarations, LLM-SDK-free).
- Do not touch the BLAKE3-chain logic — these events do not chain; `ChainTamperDetected` is for spanning-stream events only (ADR-0008 §Consequences).
