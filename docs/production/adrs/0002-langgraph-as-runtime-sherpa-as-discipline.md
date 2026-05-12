# ADR-0002: LangGraph as runtime, SHERPA as discipline — composition over alternatives

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** orchestration · runtime
**Related:** ADR-0001, ADR-0014, ADR-0022

## Context

Industry comparisons typically treat LangGraph and the SHERPA pattern (arXiv 2509.00272) as alternative orchestration choices — pick one. In practice they operate at different layers: LangGraph provides runtime primitives (`StateGraph`, `conditional_edge`, checkpointer, `interrupt()`) while SHERPA describes an architectural discipline (hierarchical state machines, state-as-contract, nodes-never-call-nodes, domain-best-practices-as-topology).

Treating them as alternatives forces a choice between "real framework with weak discipline" and "rigorous discipline with no runtime tooling." Both losses are avoidable.

## Options considered

- **LangGraph only**, treating SHERPA as inspiration but not as enforced discipline. The framework permits ad-hoc node-to-node calls, untyped state dicts, and unconstrained agent paths. Determinism erodes; reviewer debugging gets harder.
- **SHERPA-only HSM**, hand-rolled. Total control, but reinvents checkpointing, interrupts, state history, audit trail, and visualization tooling.
- **Compose**: use LangGraph as the runtime engine and enforce SHERPA discipline as a project convention — backed by code review, lint rules, and Pydantic-typed state.

## Decision

**LangGraph is the runtime engine; SHERPA is the architectural discipline applied to how graphs are constructed.** They are not alternatives — they sit at different layers and compose cleanly.

Concrete commitments imposed by this composition:

- All state ledgers are **typed Pydantic models** — no `dict[str, Any]`.
- **Nodes never call other nodes** directly. They mutate state and return; LangGraph's `conditional_edge` logic decides what runs next based on state contents.
- Subgraphs are **first-class architectural primitives**, used aggressively for hierarchical decomposition.
- Branching reflects **domain best-practices encoded as topology**, not ad-hoc agent choice.
- Human-in-the-loop is implemented via `interrupt()` at low-trust transitions, not only at end-of-flow.
- The agent has freedom only **inside leaf node implementations**, never at orchestration time.

## Tradeoffs

| Gain | Cost |
|---|---|
| Replayability of agent decisions | Engineers must internalize the discipline; PRs that violate it need rejection |
| LangGraph's mature tooling (state inspector, checkpointer, `interrupt()`) for free | Lint rules / code review must enforce "nodes never call nodes" — runtime doesn't enforce it |
| Domain best-practices become structural, not promptual | Adding a new node is more thought-intensive than appending a tool call |
| `interrupt()` makes multi-day human pauses cheap | Pydantic state models must evolve with care; schema drift is a real risk |

## Consequences

- The "SHERPA-disciplined LangGraph" implementation pattern is the project's distinct contribution. Other LangGraph implementations elsewhere routinely violate the discipline; ours does not.
- Pre-commit hooks or AST-based lints can enforce the "nodes never call nodes" rule and "state must be a Pydantic model" rule.
- The probe contract (ADR-0007) and the Step File format become the natural boundaries where SHERPA-disciplined code interfaces with the rest of the system.

## Reversibility

**Medium.** Replacing LangGraph with another HSM runtime is feasible if the runtime supports typed state and conditional edges. Replacing the SHERPA discipline (e.g., allowing nodes to call nodes) would require a substantial code rewrite because subgraph code assumes the state-as-contract invariant; the freedom would also undo the determinism guarantees the Trust-Aware layer depends on.

## Evidence / sources

- `../design.md §4.1` (Layer 2 description)
- `../design.md §4.2` (explicit "runtime vs discipline" framing with comparison table)
- `../design.md §8.8` (worker subgraph state machine diagram showing the discipline rendered as topology)
- arXiv 2509.00272 — SHERPA: "A Model-Driven Framework for Large Language Model Execution," Chen et al. — hierarchical state machines encoding domain best practices
- LangChain blog and docs — `interrupt()`, checkpointer, `StateGraph` primitives
