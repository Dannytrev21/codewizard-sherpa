# Story S6-02 — Build the plain-async Supervisor graph and three nodes

**Step:** Step 6 — Assemble the Supervisor graph and the pure decide() core
**Status:** Ready
**Effort:** M
**Depends on:** S4-03, S5-06
**ADRs honored:** ADR-0001, ADR-0009

## Context
The Supervisor is the per-workflow tollbooth: resolve the plugin, build the Context Bundle, route the work. The synthesis assumed `langgraph` was a runtime dependency and built the Supervisor as a `StateGraph` — but `langgraph` is not in `pyproject.toml`, not in `uv.lock`, and is `import-linter`-forbidden everywhere (Gap 1). This story implements the Supervisor as a **plain async pipeline of three functions** sharing a frozen `SupervisorState` — Option B of ADR-0001 — keeping the new-dependency count at exactly two and preserving each `async def` as the Phase-9 Temporal-Activity seam. It is the integration choke point that joins the C2 adapter (Step 4) and the `PlannerNode` (Step 5).

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C1 — Supervisor` — `build_supervisor_graph` / `run_supervisor` signatures; "three nodes wired in a linear graph"; "SupervisorGraph is a thin type alias".
  - `../phase-arch-design.md §Control flow` — the happy-path node order: `resolve_node` → `build_bundle_node` → `route_node`; events emitted at each node.
  - `../phase-arch-design.md §Process view` — the sequential `resolve → build_bundle → route` flow; "It never loops".
  - `../phase-arch-design.md §Scenario 1` — the warm-path recipe-route walkthrough every node participates in.
  - `../phase-arch-design.md §Gap 1` — why a plain async pipeline, not LangGraph.
  - `../phase-arch-design.md §Harness engineering` — `structlog` logging; state advanced by `model_copy(update=...)`, never mutated.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0001-supervisor-graph-engine.md` — ADR-0001 — plain async pipeline; `SupervisorGraph` is a type alias; no `langgraph` dep; no fence amendment.
  - `../ADRs/0009-concrete-resolution-to-bundle-resolution-adapter.md` — ADR-0009 — `build_bundle_node` calls `to_bundle_resolution` then the shipped `BundleBuilder.build`.
- **Existing code (if any):**
  - `src/codegenie/supervisor/state.py` — `SupervisorState` (frozen, `extra="forbid"`), the `SupervisorDecision` union — import, do not redeclare.
  - `src/codegenie/supervisor/bundle_resolution.py` — `to_bundle_resolution` + `ResolverTccmPlaceholder` shipped by S4-02/S4-03.
  - `src/codegenie/plugins/resolver.py` — `resolve(registry, scope)`; `src/codegenie/plugins/bundle.py` — `BundleBuilder.build`.
  - `src/codegenie/plugins/events.py` — `EventLog.emit_internal`, `PluginResolved`, `BundleBuilt`, `InMemorySink` (use for tests).
  - `src/codegenie/plugins/subgraph.py` — `SubgraphState` advanced by `model_copy(update={...})` — the frozen-state discipline to mirror.

## Goal
`build_supervisor_graph` and `run_supervisor` exist in `codegenie/supervisor/graph.py`, running `resolve_node` → `build_bundle_node` → `route_node` as a plain async pipeline that advances a frozen `SupervisorState` and returns a `SupervisorDecision` — with no `langgraph` import.

## Acceptance criteria
- [ ] `from codegenie.supervisor.graph import build_supervisor_graph, run_supervisor` succeeds; signatures match `§C1` (keyword-only DI: `plugin_registry`, `bundle_builder`, `planner_node`, `event_log`).
- [ ] `SupervisorGraph` is a thin type alias (e.g. over a callable / a small frozen holder of the three nodes) — not a class importing any graph framework; `import langgraph` appears nowhere in `codegenie/supervisor/`.
- [ ] `resolve_node` emits `PluginResolved`, `build_bundle_node` emits `BundleBuilt` via `event_log.emit_internal`; each node returns a new `SupervisorState` via `model_copy(update=...)` — no in-place mutation.
- [ ] `run_supervisor(graph, state)` over a `ConcreteResolution`-producing fixture returns a `Dispatched`; over a `UniversalFallbackResolution` fixture (e.g. a `cobol` repo) returns an `EscalatedToHITL` — verified against an `InMemorySink` `EventLog`.
- [ ] `make lint-imports` is green — `codegenie.supervisor` stays LLM-SDK-fenced.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Create `src/codegenie/supervisor/graph.py`. Define `SupervisorGraph` as a thin type alias / frozen holder of `(resolve_node, build_bundle_node, route_node)` plus the injected collaborators — no framework type.
2. Write the three `async def` nodes, each `(state: SupervisorState, ...) -> SupervisorState`: `resolve_node` calls `plugins.resolver.resolve`, emits `PluginResolved`, returns `state.model_copy(update={"resolution": ...})`; `build_bundle_node` calls `to_bundle_resolution` then `bundle_builder.build`, emits `BundleBuilt`, returns `model_copy(update={"bundle": ...})`; `route_node` calls `planner_node.route(...)` (which itself appends `RouteDecided` — S5-06).
3. Write `build_supervisor_graph(*, plugin_registry, bundle_builder, planner_node, event_log) -> SupervisorGraph` — pure assembly, no I/O.
4. Write `run_supervisor(graph, state) -> SupervisorDecision`: run the three nodes in sequence on the `SingleTaskTrigger` path; on a `UniversalFallbackResolution` short-circuit after `resolve_node` to `EscalatedToHITL`; call `decide()` (S6-01) to produce the final value.
5. Add `structlog` logging at node boundaries with regex-valid `_WARNING_IDS`; export `build_supervisor_graph` / `run_supervisor` via `supervisor/__init__.py` `__all__`.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/integration/supervisor/test_supervisor_graph.py`
First red test — the happy single-dispatch path:
```python
async def test_run_supervisor_concrete_resolution_yields_dispatched() -> None:
    # arrange: a fixture PluginRegistry resolving to a ConcreteResolution, a real BundleBuilder,
    #          a PlannerNode with fake ports, an EventLog over an InMemorySink
    # act: graph = build_supervisor_graph(...); decision = await run_supervisor(graph, state)
    # assert: isinstance(decision, Dispatched)
    #         and {e.event_type for e in event_log.replay()} >= {"plugin_resolved", "bundle_built"}
    ...
```
Second red test — the escalation path:
```python
async def test_run_supervisor_universal_fallback_yields_escalated_to_hitl() -> None:
    # arrange: a registry that resolves a cobol repo to UniversalFallbackResolution
    # act: decision = await run_supervisor(graph, state)
    # assert: isinstance(decision, EscalatedToHITL) and "no concrete" in decision.reason.lower()
    ...
```
Add a third red test asserting each node returns a *new* `SupervisorState` object (`state is not next_state`) — frozen-state discipline.
### Green — make it pass
Implement the three nodes and `run_supervisor` as described. Keep `build_supervisor_graph` a pure assembly function. Use `decide()` from S6-01 for the terminal mapping — do not re-derive the decision in the graph.
### Refactor — clean up
Type hints on every node and the alias; docstrings on `build_supervisor_graph` / `run_supervisor`. Edge case 4 (`resolve_node` produces `UniversalFallbackResolution`) routes to `EscalatedToHITL` without touching `build_bundle_node`. Logging per `§Harness engineering`. Confirm cyclomatic complexity ≤ 8 per function; confirm `make lint-imports` stays green.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/supervisor/graph.py` | New — `SupervisorGraph` alias, the three nodes, `build_supervisor_graph`, `run_supervisor`. |
| `src/codegenie/supervisor/__init__.py` | Export `build_supervisor_graph` / `run_supervisor`. |
| `tests/integration/supervisor/test_supervisor_graph.py` | New — graph end-to-end against `InMemorySink`. |

## Out of scope
- The `BothProvenanceTrigger` multi-resolve branch — S6-03 extends `run_supervisor`/`build_bundle_node` to loop per task class.
- The `Dispatched`-payload-into-SHERPA-subgraph handoff — S6-04.
- The static append-before-transition AST test — S6-05.
- The `< 5 ms` warm-path bench — S7-01.
- A real Redis-backed integration run — S6-03's integration test and S7 carry that; this story may use an in-memory / fake `HotViewStore`.

## Notes for the implementer
- `SupervisorGraph` is **deliberately** a type alias, not a class — ADR-0001 makes the Phase-9 rebind to `StateGraph` a small, loud edit. Do not add `langgraph` "to be ready"; that is the exact premature-pluggability the ADR rejects.
- Never mutate `SupervisorState` — always `model_copy(update=...)`. Mirror `SubgraphState` discipline in `plugins/subgraph.py`.
- Emit `PluginResolved` / `BundleBuilt` via `emit_internal` (workflow-internal stream) — not `emit_spanning`. `PluginResolved` is already an internal event; follow that placement (Gap 4).
- The `build_bundle_node` calls `to_bundle_resolution` first — if S4-03's `ResolverTccmPlaceholder` fires, let it propagate; do not catch and build an empty Bundle.
- The three-node *discipline* is enforced by convention + tests, not a graph type — keep each node a single-purpose `async def` so S6-05's AST test can reason about `route_node` in isolation.
- Bounded public surface: `build_supervisor_graph` + `run_supervisor` + `SupervisorGraph` are 3 of the ≤24 names — keep the three nodes package-internal.
