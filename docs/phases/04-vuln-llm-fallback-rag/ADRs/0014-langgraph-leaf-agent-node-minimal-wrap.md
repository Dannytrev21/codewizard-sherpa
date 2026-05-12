# ADR-0014: `LangGraph` imported minimally as `LeafAgentNode` one-node `StateGraph`; Phase 6 replaces the node, not the leaf

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** langgraph · phase-6-handoff · roadmap-fit · synthesizer-departure
**Related:** [ADR-0004](0004-leaf-llm-agent-protocol-os-tiered.md), [production ADR-0002](../../../production/adrs/0002-langgraph-as-runtime-sherpa-as-discipline.md)

## Context

The Phase 4 roadmap entry says verbatim: "`langgraph` imported minimally — just enough to wrap the leaf agent invocation." Three lens designs read this three ways. Performance honored it (one-node `StateGraph` wrap). Security did not import `langgraph` at all. Best-practices explicitly refused (`final-design.md §"Synthesis ledger"` row "LangGraph footprint"; `critique.md §best-practices.2`). The critic argued that *honoring the roadmap line* matters: Phase 6 inherits a clean wrapping target if the minimal import lands now; otherwise Phase 6 invents the wrapping shape from scratch and must prove it composes with the engine.

The synthesizer adopts the performance-lens minimal wrap *but* with a tight scope: a `LeafAgentNode` class whose `build_graph()` returns a one-node `StateGraph`, and a Pydantic `LeafState(request, response)` schema. The leaf — `LeafLlmAgent.invoke` — is a plain function; the wrapper is the swap point.

## Options considered

- **No LangGraph import.** Best-practices + security. Cleanest until Phase 6, when the wrapping shape must be invented mid-rewrite.
- **One-node `StateGraph` wrap (synth).** Minimal import: `langgraph` in `pyproject.toml` pinned to a minor; `LeafAgentNode.build_graph` returns a one-node graph that wraps `LeafLlmAgent.invoke`. Phase 6 replaces the node with the full SHERPA subgraph.
- **Full SHERPA subgraph now.** Phase 6's scope dragged into Phase 4. Inverts the phase order.
- **`langgraph.func` only (the lower-level API).** Doesn't compose with Phase 6's anticipated `interrupt()` + checkpointer pattern.

## Decision

`LeafAgentNode` wraps `LeafLlmAgent.invoke` in a one-node `langgraph.graph.StateGraph`. The state is a Pydantic `LeafState(request: LlmRequest, response: LlmResponse | None)`. `langgraph` is pinned to a minor in `pyproject.toml`. The wrap is theatre-grade in Phase 4 (no `interrupt()`, no checkpointer, no branching) — its sole purpose is to make Phase 6's migration a node swap, not a rewrite.

Phase 6 replaces `LeafAgentNode` with the full SHERPA subgraph (`Recipe_Matcher → Solved_Example_RAG_Retriever → LLM_Planner → Step_Emitter` per [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md)); `LeafLlmAgent.invoke` (the leaf function) is unchanged.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 6's LangGraph migration is a node swap — the leaf signature is preserved across phases | One extra abstraction layer in Phase 4; the wrap does nothing functional |
| `langgraph` shows up in `pyproject.toml` now — the dep graph is "honest" about what's coming | Engineer surprise at "why is LangGraph imported if it doesn't do anything?" — the answer lives in this ADR |
| `LeafState` Pydantic schema is what Phase 6's state ledger will consume verbatim | One more typed model to maintain |
| The literal reading of the roadmap line is honored — Phase 6 doesn't inherit a "you said one-node but did none" surprise | Best-practices' "no theatre" critique is real; surfaced as a deliberate roadmap-fit decision |
| Phase 5's microVM swap (in `JailedLeafLlmAgent` → `MicroVmLeafLlmAgent`) doesn't touch the wrap — the wrap and the leaf are independent | If Phase 6 picks a fundamentally different state-machine framework (vs LangGraph), the Phase 4 wrap is dead code; mitigated by [production ADR-0002](../../../production/adrs/0002-langgraph-as-runtime-sherpa-as-discipline.md) committing to LangGraph |

## Consequences

- `langgraph` is pinned to a minor in `pyproject.toml`. SDK shape drift on LangGraph minor bumps lands as a fence-CI test failure.
- `LeafAgentNode` lives in `src/codegenie/llm/node.py`. `LeafState` Pydantic schema lives there too.
- `LeafAgentNode.build_graph()` is unit-tested for "one node, named correctly, invokes the leaf once." No semantic tests beyond that — the wrap doesn't do anything.
- Phase 6's SHERPA subgraph replaces `LeafAgentNode` with multiple nodes; `LeafLlmAgent.invoke` is wrapped *inside* one of those nodes. The leaf signature (`LlmRequest → LlmResponse`) is preserved.
- The wrap and the engine (`RagLlmEngine`) are independent — the engine calls `LeafLlmAgent` directly; the wrap exists for Phase 6's swap target, not for current-phase routing.

## Reversibility

**High.** Removing the wrap is deleting one file (`node.py`), removing `langgraph` from `pyproject.toml`, and dropping the unit test. Phase 6's migration then becomes a wrap-invention rather than a node-swap — exactly the cost this ADR avoids paying.

## Evidence / sources

- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row "LangGraph footprint"
- `../final-design.md §"Components"` #3 — `LeafAgentNode` design
- `../phase-arch-design.md §"Non-goals"` NG2 — no LangGraph runtime
- `../phase-arch-design.md §"Component design"` #2 — `LeafAgentNode` interface
- `../critique.md §best-practices.2` — roadmap line "imported minimally"
- Roadmap §Phase 4 tooling — "`langgraph` imported minimally"
- Production [ADR-0002](../../../production/adrs/0002-langgraph-as-runtime-sherpa-as-discipline.md) — LangGraph as runtime
