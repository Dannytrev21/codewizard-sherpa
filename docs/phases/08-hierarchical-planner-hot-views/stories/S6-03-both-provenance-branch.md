# Story S6-03 — Wire the BothProvenanceTrigger multi-plugin branch

**Step:** Step 6 — Assemble the Supervisor graph and the pure decide() core
**Status:** Ready
**Effort:** M
**Depends on:** S6-01, S6-02
**ADRs honored:** ADR-0002, ADR-0001

## Context
A workflow trigger can carry `Both` provenance — a vulnerability remediation that is also implicated by a distroless-migration task class, for example — and per production ADR-0042 (`Accepted`) "Phase 8 must model parent workflow plus plugin work items". This story wires the `BothProvenanceTrigger` branch of the Supervisor: resolve each implicated task class, build a `Bundle` and a `RouteDecision` per resolution, and emit a `MultiPluginDispatch`. It is downstream integration work — it extends the single-dispatch pipeline (S6-02) and feeds `decide()` (S6-01) the per-resolution tuples without changing either's shape.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Control flow` — decision point D2: "`BothProvenanceTrigger` → resolve each `implicated_task_class`, build a `Bundle` and `RouteDecision` per resolution, emit `MultiPluginDispatch`".
  - `../phase-arch-design.md §Scenario 3 — ADR-0042 multi-plugin Both workflow` — the per-task-class resolve/build sequence diagram.
  - `../phase-arch-design.md §Data model` — `MultiPluginDispatch(parent_workflow_id, work_items)`, `PluginWorkItem(plugin, bundle, route)`.
  - `../phase-arch-design.md §Edge cases` — case 3 (`Both`/multi-plugin trigger), case 14 (a `Both` with one task class fails at construction).
  - `../phase-arch-design.md §Open questions deferred to implementation` — Q3: Phase 8 ships the typed shape, not the deep cross-PR sequencing.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0002-supervisor-decision-three-variant-sum-type.md` — ADR-0002 — `work_items` length ≥ 2, one per resolved task class; `MultiPluginDispatch` is a first-class variant.
  - `../ADRs/0001-supervisor-graph-engine.md` — ADR-0001 — the `Both` branch stays inside the plain async pipeline; no new graph machinery.
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0042-multi-plugin-coordination-for-both-workflows.md` — "Phase 8 must model parent workflow plus plugin work items".
- **Existing code (if any):**
  - `src/codegenie/supervisor/graph.py` — `run_supervisor`, the three nodes from S6-02; extend, do not fork.
  - `src/codegenie/supervisor/decide.py` — `decide()` from S6-01; already handles `BothProvenanceTrigger` given the input tuples.
  - `src/codegenie/supervisor/state.py` — `BothProvenanceTrigger.implicated_task_classes`, `MultiPluginDispatch`, `PluginWorkItem`.

## Goal
`run_supervisor` resolves each `implicated_task_class` of a `BothProvenanceTrigger`, builds a `Bundle` + `RouteDecision` per resolution, and produces a `MultiPluginDispatch` with one `PluginWorkItem` per resolved task class.

## Acceptance criteria
- [ ] `run_supervisor` over a `BothProvenanceTrigger` fixture with N (≥ 2) implicated task classes returns a `MultiPluginDispatch` whose `work_items` has length N.
- [ ] Each `PluginWorkItem` carries the `Bundle` and `RouteDecision` produced for *its* resolved task class — verified by asserting distinct `plugin` / `route` values across the work items.
- [ ] `MultiPluginDispatch.parent_workflow_id` equals the triggering `SupervisorState.workflow_id`.
- [ ] `PluginResolved` and `BundleBuilt` are emitted once per resolved task class — N of each in the `InMemorySink` stream for an N-class `Both` trigger.
- [ ] The single-dispatch path (S6-02) still returns `Dispatched` — no regression; its test stays green unchanged.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. In `run_supervisor`, branch on `state.provenance`: `SingleTaskTrigger` keeps the S6-02 single path; `BothProvenanceTrigger` enters the multi path.
2. For the multi path, iterate `provenance.implicated_task_classes` — for each, run `resolve_node` then `build_bundle_node` (reuse the S6-02 nodes; scope each resolve to that task class), collecting `resolutions`, `bundles`, and per-resolution `RouteDecision`s into tuples.
3. Route each resolution through `route_node` so a `RouteDecided` is appended per work item (S6-05's AST test asserts no routing edge skips the append — the `Both` branch must route through the same `route_node`, not a side path).
4. Call `decide(provenance=both, resolutions=..., bundles=..., routes=..., parent_workflow_id=state.workflow_id)` (S6-01) — `decide()` zips the tuples into `MultiPluginDispatch`.
5. Keep cross-PR sequencing (ordering, shared evidence, status rollup) OUT — Phase 8 ships the typed shape only (Open Question 3); record that scoping call in the attempt log.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/integration/supervisor/test_supervisor_both_branch.py`
First red test — the multi-plugin dispatch shape:
```python
async def test_run_supervisor_both_provenance_yields_multi_plugin_dispatch() -> None:
    # arrange: a SupervisorState with BothProvenanceTrigger(implicated_task_classes=(t_vuln, t_distroless)),
    #          a registry resolving each task class to a distinct ConcreteResolution,
    #          an EventLog over an InMemorySink
    # act: decision = await run_supervisor(graph, state)
    # assert: isinstance(decision, MultiPluginDispatch)
    #         and len(decision.work_items) == 2
    #         and decision.parent_workflow_id == state.workflow_id
    #         and {wi.plugin for wi in decision.work_items} == {plugin_vuln, plugin_distroless}
    ...
```
Second red test — event emission count:
```python
async def test_both_branch_emits_resolved_and_built_per_task_class() -> None:
    # act: await run_supervisor(graph, state)  # 2 implicated task classes
    # assert: sum(e.event_type == "plugin_resolved" for e in event_log.replay()) == 2
    #         and sum(e.event_type == "bundle_built" for e in event_log.replay()) == 2
    ...
```
### Green — make it pass
Add the `match`/branch in `run_supervisor` on `provenance.kind`. Loop the existing `resolve_node`/`build_bundle_node`/`route_node` per task class, accumulate the tuples, hand them to `decide()`. The smallest change — no new node, no new module.
### Refactor — clean up
Docstring the multi-path branch. Confirm edge case 14 is already covered by the model validator (a one-class `Both` cannot be constructed — assert this in a small unit test if not already covered by S2-03). Confirm a `UniversalFallbackResolution` among the implicated classes still escalates correctly (decide()'s fallback-first match). Logging per `§Harness engineering`. Cyclomatic complexity ≤ 8.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/supervisor/graph.py` | Extend `run_supervisor` with the `BothProvenanceTrigger` branch. |
| `tests/integration/supervisor/test_supervisor_both_branch.py` | New — the multi-plugin dispatch integration tests. |

## Out of scope
- Deep cross-PR sequencing — ordering, shared evidence, status rollup — deferred to Phase 10 (Open Question 3). Phase 8 ships only the typed `MultiPluginDispatch` shape.
- The `Dispatched`-payload-into-subgraph handoff — S6-04.
- The static append-before-transition AST test — S6-05.
- A real `Both`-producing trigger source — Phase 10 is the first real producer; Phase 8 uses fixtures.

## Notes for the implementer
- Route each `Both` resolution through the *same* `route_node` — if you build a shortcut path, S6-05's AST test will (correctly) flag a routing edge that skips the `RouteDecided` append.
- `work_items` length ≥ 2 is enforced by the `MultiPluginDispatch` model validator (ADR-0002) — a one-class `Both` is already rejected at trigger construction by the `BothProvenanceTrigger` validator (edge case 14); the two guards are independent.
- `parent_workflow_id` is the stable Phase-9 extension point — Temporal's parent/child workflow model maps directly onto it; do not invent a separate parent identifier.
- Resolve N task classes sequentially — Phase 8 adds no concurrency; the Supervisor is the fast tollbooth, and parallel resolution is Phase 9 substrate work.
- This is purely additive — the `SingleTaskTrigger` path from S6-02 must not change shape; run its test unchanged to confirm.
