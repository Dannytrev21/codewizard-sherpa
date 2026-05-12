# ADR-0001: Layered Hybrid orchestration — three layers, not one framework

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** orchestration · architecture
**Related:** ADR-0002, ADR-0003

## Context

The production system must execute long-running, multi-stage code modifications across thousands of repos. The choice of orchestration model is the most consequential architectural decision in the project. It determines whether agents can be constrained against the "Safer Builders, Risky Maintainers" failure mode, whether workflows can pause for days awaiting human review, whether decisions are replayable for audit, and whether new task types can be added without rewriting existing code.

No single agent-framework satisfies all of those properties simultaneously. Framework comparisons routinely treat LangGraph / CrewAI / Agents SDK as alternatives to each other, and the project's earlier docs (`auto-agent-design.md`, `gemini-auto-agent-design.md`) implicitly assumed a single-framework choice was forthcoming.

## Options considered

- **LangGraph alone.** Strong state-machine primitives, `interrupt()` + checkpointer, but the framework permits ad-hoc node-to-node calls and untyped state dicts. Without architectural discipline on top, determinism erodes.
- **CrewAI alone.** Role-based, emergent multi-agent coordination. Excellent for prototypes; the architectural opposite of state-as-contract. Agents debate and improvise — the failure mode the Safer Builders / Risky Maintainers data warns against (`gemini-auto-agent-design.md §"Empirical Realities"`).
- **Anthropic / OpenAI Agents SDK alone.** Minimal tool-use loop. No orchestration primitives, no hierarchical decomposition, no checkpointing. Would require building LangGraph by hand to get anywhere.
- **Hand-rolled SHERPA-style HSM (no LangGraph runtime).** Possible but reinvents checkpointing, interrupts, state-history visualization, and runtime tooling that LangGraph already provides.
- **Layered Hybrid.** Compose Temporal (durable substrate) + LangGraph (runtime) + SHERPA discipline (architectural rule) + Trust-Aware gates (safety layer) + minimal Agents SDK (leaf LLM calls). Each layer is replaceable in principle; the composition is the load-bearing choice.

## Decision

Adopt the **Layered Hybrid Architecture**:

1. **Temporal** as the outer durable-execution envelope, owning per-repo workflows across hours to days.
2. **LangGraph Supervisor (Hierarchical Planner)** as Layer 1 — reads intent, routes into task-specific subgraphs.
3. **SHERPA-disciplined worker subgraphs** as Layer 2 — strictly typed Pydantic state ledger, nodes never call other nodes, transitions driven by state contents.
4. **Trust-Aware gates** as Layer 3 — `conditional_edge` between every node, running objective sandbox checks and the policy engine before allowing transitions.
5. **Leaf LLM calls** only at designated nodes, via a minimal Agents SDK.

## Tradeoffs

| Gain | Cost |
|---|---|
| Replayable agent decisions (state ledger + Temporal checkpoint) | More moving parts than a single-framework approach |
| Hierarchical decomposition matches task structure | Engineers must internalize the layer model before contributing |
| Multi-day pauses for human review are first-class (`interrupt()`) | Coordinated upgrades across layers require migration discipline |
| New task types are additive (new subgraph, no edits) | Cross-layer debugging requires tracing through 2–3 abstractions |
| Trust gates uniform across all subgraphs — invest once | Cannot adopt off-the-shelf vendor agent products that assume a single-framework world |

## Consequences

- The Supervisor becomes the single most important component — it dispatches to every subgraph, so failures cascade. Heavily tested.
- Trust gate logic is shared infrastructure; one investment serves every subgraph.
- Cross-layer concerns (token-budget caps, identity scoping, observability) get implemented at the layer best suited (Temporal for cost ceilings; LangGraph for state visibility; gates for policy hooks).
- The probe contract (ADR-0007) is unaffected by this choice — gather is upstream of orchestration.

## Reversibility

**Medium-high.** Individual layers are replaceable behind interface contracts (LangGraph could be swapped for another HSM runtime if the step-file format and gate-verdict format hold). Swapping the layer model itself — dropping SHERPA discipline, going emergent CrewAI-style — is high cost because subgraph code assumes state-as-contract. Plan for the layer model to be permanent; plan for individual runtimes to be replaceable.

## Evidence / sources

- `../design.md §4.1` (the three layers + outer envelope)
- `../design.md §4.3` (12×5 comparison matrix)
- `../design.md §4.7` (one-paragraph rejection per alternative)
- `../../gemini-auto-agent-design.md §"Empirical Realities"` — "Safer Builders, Risky Maintainers" data
- `../../auto-agent-design.md §6` — Temporal as the production substrate (OpenAI Codex, Replit precedent)
- arXiv 2509.00272 — SHERPA paper
