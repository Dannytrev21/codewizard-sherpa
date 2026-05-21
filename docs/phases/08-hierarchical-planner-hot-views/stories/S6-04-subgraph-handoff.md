# Story S6-04 — Dispatch the Dispatched payload into the SHERPA subgraph

**Step:** Step 6 — Assemble the Supervisor graph and the pure decide() core
**Status:** Ready
**Effort:** S
**Depends on:** S6-03
**ADRs honored:** ADR-0002, ADR-0001

## Context
Once the Supervisor produces a `Dispatched` decision it must hand the work to the per-plugin worker subgraph — the Phase-6 SHERPA loop, which runs `IngestCve → BuildBundle → Recipe → ...` over a frozen `SubgraphState`. This story wires that handoff: the `Dispatched` payload's frozen `Bundle` and `RouteDecision` are loaded into the initial `SubgraphState`'s existing accumulator fields. It is the final integration seam of Step 6 — the point where the planning layer ends and the worker subgraph begins, and the boundary Phase 6's `SubgraphState` already shipped fields for.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Control flow` — step 6: "the Supervisor hands the `Dispatched` payload — the frozen `Bundle` and the `RouteDecision` — to the Phase 6 SHERPA subgraph's initial `SubgraphState` (`SubgraphState.bundle` and `SubgraphState.resolution` are the existing accumulator fields)".
  - `../phase-arch-design.md §C1 — Supervisor` — "the impure surface is … the subgraph handoff".
  - `../phase-arch-design.md §Process view` — `SUP-->>SG: Dispatched(plugin, version, bundle, route)`.
  - `../phase-arch-design.md §Integration with Phase 9` — the three-node graph (including this handoff seam) is the Temporal-Activity boundary.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0002-supervisor-decision-three-variant-sum-type.md` — ADR-0002 — the handoff `match`es on `SupervisorDecision`; `assert_never` over the union.
  - `../ADRs/0001-supervisor-graph-engine.md` — ADR-0001 — the handoff is a plain function at the pipeline tail; it is part of the Phase-9 seam.
- **Existing code (if any):**
  - `src/codegenie/plugins/subgraph.py` — `SubgraphState` (frozen, `extra="forbid"`, `arbitrary_types_allowed=True`): `workflow_id: WorkflowId`, `cve: CveId`, `resolution: PluginResolution | None`, `bundle: Bundle | None`; `SubgraphNode` Protocol. The handoff populates `resolution` and `bundle`.
  - `src/codegenie/supervisor/graph.py` — `run_supervisor`, the `Dispatched` value to hand off.
  - `src/codegenie/supervisor/state.py` — `Dispatched(plugin, version, bundle, route)`.

## Goal
A handoff function maps a `Dispatched` payload into an initial `SubgraphState` with the `bundle` and `resolution` accumulator fields populated, so the Phase-6 SHERPA subgraph can be entered with a typed, validated starting state.

## Acceptance criteria
- [ ] A handoff function (e.g. `to_initial_subgraph_state(decision: Dispatched, *, workflow_id, cve) -> SubgraphState`) exists in `codegenie/supervisor/`.
- [ ] The returned `SubgraphState` has `bundle` set to the `Dispatched.bundle` (same frozen object) and `resolution` populated; `workflow_id` and `cve` are set from the arguments.
- [ ] The function is pure — it constructs a `SubgraphState`, performs no I/O, imports no shell module.
- [ ] The handoff is reachable only for the `Dispatched` variant — a `MultiPluginDispatch` or `EscalatedToHITL` is `match`ed elsewhere; the `match` closes with `assert_never`.
- [ ] An integration test runs `run_supervisor` to a `Dispatched` and feeds the result through the handoff into a `SubgraphState` that round-trips Pydantic validation.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Add `to_initial_subgraph_state` to `codegenie/supervisor/graph.py` (or a small `handoff.py` if `graph.py` is getting large) — a pure function `Dispatched -> SubgraphState`.
2. Construct the `SubgraphState` setting `workflow_id`, `cve`, `bundle=decision.bundle`, and `resolution` (the resolution that produced the dispatch — thread it through from `run_supervisor` or carry it on `SupervisorState`).
3. Confirm `SubgraphState`'s `extra="forbid"` accepts exactly these fields — no extra keys; the other accumulator fields stay `None` for the subgraph to populate.
4. Where `run_supervisor` returns, `match` the `SupervisorDecision`: `Dispatched` → eligible for handoff; `MultiPluginDispatch` / `EscalatedToHITL` → not handed to a single subgraph here; close with `assert_never`.
5. `structlog`-log the handoff with a regex-valid warning/info ID.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/integration/supervisor/test_subgraph_handoff.py`
First red test — the field mapping:
```python
async def test_dispatched_payload_populates_initial_subgraph_state() -> None:
    # arrange: run_supervisor to a Dispatched over a vuln-remediation fixture
    # act: subgraph_state = to_initial_subgraph_state(dispatched, workflow_id=wf, cve=cve)
    # assert: subgraph_state.bundle is dispatched.bundle          # same frozen object
    #         and subgraph_state.resolution is not None
    #         and subgraph_state.workflow_id == wf
    ...
```
Second red test — purity / validation round-trip:
```python
def test_initial_subgraph_state_is_a_valid_frozen_state() -> None:
    # act: state = to_initial_subgraph_state(dispatched_fixture, workflow_id=wf, cve=cve)
    # assert: SubgraphState.model_validate(state.model_dump()) == state   # round-trips, extra="forbid" holds
    ...
```
### Green — make it pass
Implement `to_initial_subgraph_state` as a single `SubgraphState(...)` construction. No subgraph execution — this story only builds the *initial* state.
### Refactor — clean up
Docstring naming the Phase-6 accumulator-field contract. Confirm the function imports only `SubgraphState`, `Dispatched`, and identifier types — no `redis`, no `EventLog`. Confirm the `match` over `SupervisorDecision` at the call site closes with `assert_never`. Logging per `§Harness engineering`.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/supervisor/graph.py` (or new `handoff.py`) | Add `to_initial_subgraph_state`. |
| `src/codegenie/supervisor/__init__.py` | Export `to_initial_subgraph_state` if it is part of the public surface. |
| `tests/integration/supervisor/test_subgraph_handoff.py` | New — the handoff field-mapping + validation tests. |

## Out of scope
- *Running* the Phase-6 SHERPA subgraph — Phase 8 builds the initial state only; the subgraph loop is unchanged Phase-6 code.
- The `MultiPluginDispatch` per-work-item subgraph dispatch — Phase 8 ships the typed shape (S6-03); fanning N work items into N subgraphs is Phase 9/10 work.
- The universal HITL subgraph dispatch for `EscalatedToHITL` — Phase 6 owns that subgraph; Phase 8 only produces the typed variant.
- The `phase08_e2e` workflow test that exercises the full path — S7-02.

## Notes for the implementer
- Use `SubgraphState`'s *existing* `bundle` and `resolution` fields — do not add new fields to `SubgraphState`; that file is Phase-6 shipped code and editing it is not in scope.
- `SubgraphState` has `arbitrary_types_allowed=True` because `transform` is non-Pydantic — your handoff only sets the Pydantic-clean `bundle`/`resolution`/`workflow_id`/`cve`, so this is not your concern, but do not assume every field is plain-serializable.
- The handoff is pure — the *dispatch* of the resulting state into the subgraph is the impure shell, and in Phase 8 that is just constructing the state; Phase 9's Temporal envelope owns actually entering the subgraph.
- `cve: CveId` is required on `SubgraphState` — thread it from the `SupervisorState`/trigger; do not invent a placeholder CVE.
- Keep the `assert_never` at the `SupervisorDecision` `match` — a future fourth variant must be a loud `mypy` failure here too.
