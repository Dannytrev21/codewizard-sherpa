# ADR-0001: Supervisor graph engine — plain async pipeline, not LangGraph

**Status:** Accepted
**Date:** 2026-05-21
**Tags:** Functional core / imperative shell · orchestration · dependency management
**Related:** ADR-0002, [production ADR-0002](../../../production/adrs/0002-langgraph-as-runtime-sherpa-as-discipline.md), [production ADR-0003](../../../production/adrs/0003-temporal-as-workflow-substrate.md)

## Context

The Supervisor is a strictly sequential `resolve → build_bundle → route` flow with one branch point (the `PluginResolution` variant) and one trigger-driven branch (`provenance == both`). It never loops. `final-design.md` §Supervisor builds the entire three-node Supervisor on `build_supervisor_graph(): LangGraph resolve→bundle→route` and justifies it with "LangGraph is already a runtime dep since Phase 6" and "the cost is ~30 lines of builder boilerplate."

Both premises are **false against the codebase** — see [phase-arch-design.md §Gap 1](../phase-arch-design.md#gap-1--langgraph-is-not-a-dependency-the-synthesis-assumed-it-shipped-in-phase-6). `pyproject.toml` reserves the LLM-SDK slot but does not include `langgraph`; `uv.lock` has no `langgraph`; there is no `import langgraph` anywhere in `src/`; and `langgraph` appears *only* in `import-linter` `forbidden_modules` lists. The Phase 6 "subgraph" is the Protocol-based `SubgraphNode` + `SubgraphState` in `plugins/subgraph.py` — a typed-contract design, not a LangGraph runtime. Adding `langgraph` would be a *third* new runtime dependency beyond the synthesis's own Goal G7 budget of two (`redis` + `mcp`), and would require a fence amendment to un-forbid it.

## Options considered

- **Option A — Add `langgraph` as a real dependency now.** Amend `forbidden_modules` to admit `langgraph` into `codegenie.supervisor.graph` only; build the Supervisor as a three-node `StateGraph`. **Pattern:** Plugin architecture / graph runtime — but a third runtime dep and a fence amendment for a never-looping three-step flow is *premature pluggability* (toolkit "flag on sight").
- **Option B — Plain async pipeline of three functions sharing `SupervisorState`.** `SupervisorGraph` is a thin type alias; the three nodes are plain `async def`s; `decide()` stays a pure core. **Pattern:** Functional core / imperative shell. Each function boundary *is* the Phase-9 Temporal-Activity seam — Temporal wraps a plain async function exactly as readily as a graph node.
- **Option C — A single async function with inline branches.** No node boundary at all. **Pattern:** none — collapses the Phase-9 Temporal-Activity seam the roadmap (§Phase 9) needs; Phase 9 would have to re-introduce the boundaries it wants to wrap.

## Decision

Phase 8 ships the Supervisor as a **plain async pipeline of three functions** (`resolve_node`, `build_bundle_node`, `route_node`) sharing a frozen `SupervisorState`, with a pure `decide()` core. `SupervisorGraph` is a thin type alias the implementer may later rebind to a real `StateGraph` in Phase 9 if Temporal+LangGraph integration warrants it. This is the **Functional core, imperative shell** pattern: the node boundary is preserved as the Phase-9 seam without importing a graph framework to draw it.

## Tradeoffs

| Gain | Cost |
|---|---|
| New-dependency count stays at exactly two (`redis`, `mcp`) — Goal G7 met | `SupervisorGraph` is a type alias, not a real graph object — a Phase-9 rebind to `StateGraph` is a deliberate (small) edit if it ever happens |
| No `import-linter` fence amendment — `langgraph` stays forbidden everywhere, the simplest fence posture | If a future phase genuinely needs graph features (conditional edges, checkpointed sub-states), the pipeline must be promoted to a real graph then |
| Zero framework overhead on the warm path (~0 ms vs LangGraph's ~1–2 ms) | The three-node *discipline* is a convention, not enforced by a graph type — a contract-snapshot test on `SupervisorDecision` and the purity fence carry the enforcement instead |
| `decide()` is pure either way; the Phase-9 Temporal-Activity seam is each `async def` — Temporal wraps it identically | A reviewer expecting `design.md §1`'s "Supervisor is a graph node" framing must read this ADR to see why Phase 8 defers the literal graph |

## Pattern fit

The toolkit's "premature pluggability" entry is explicit: "We made it pluggable in case… with one implementation. YAGNI." A graph framework for a strictly sequential, never-branching three-step flow is graph machinery for a function. The honest pattern is **Functional core, imperative shell** — three thin `async def` shells around a pure `decide()`. The Phase-9 Temporal seam does not require Phase 8 to pre-shape itself into `StateGraph` nodes; Temporal wraps whatever Phase 8 ships. Building the graph "for the Phase 9 seam" would be speculative generality for a phase away.

## Consequences

- The new-dependency budget holds at two; `pyproject.toml` and `docker-compose.yml` edits stay minimal and fence-enumerated.
- `import-linter` keeps `langgraph` forbidden across all four new packages — no special-case carve-out to maintain.
- Phase 9 wraps each of the three `async def` nodes in a Temporal Activity; `decide()` is Activity-wrappable unchanged. The seam is preserved.
- A future phase that needs real graph features must explicitly promote `SupervisorGraph` from a type alias to a `StateGraph` — a loud, reviewable edit, not a silent drift.
- The three-node *discipline* must be preserved by convention + the `SupervisorDecision` contract test + the functional-core purity fence, since no graph type enforces it.
- `production/design.md §1`'s "Supervisor as a LangGraph node" framing is honored *in spirit* (the node boundary exists) but not *literally* in Phase 8 — this ADR is the record of that gap.

## Reversibility

**High.** `SupervisorGraph` is a thin type alias by construction precisely so a Phase-9 rebind to `langgraph.StateGraph` is a localized change: add the dep, amend the fence, bind the alias, wrap the three functions as nodes. `decide()` stays pure across the rebind; the `SupervisorDecision` contract is unaffected. The decision is deliberately built to be cheap to revisit when Temporal lands.

## Evidence / sources

- ../phase-arch-design.md §Gap 1 — `langgraph` not a dependency
- ../phase-arch-design.md §C1 — Supervisor; "Graph engine is open"
- ../final-design.md §Synthesis ledger — Conflict-resolution row "Supervisor shape"
- ../critique.md §Attacks on the best-practices design, problem 4 — "premature pluggability… speculative generality for a phase away"
- ../../../production/adrs/0002-langgraph-as-runtime-sherpa-as-discipline.md — LangGraph as runtime
- ../../../production/adrs/0003-temporal-as-workflow-substrate.md — the Phase-9 Activity seam
- `design-patterns-toolkit.md` §Anti-patterns — "Premature pluggability"
