# Phase 6 — Performance-first design

**Question:** how do we introduce a restartable vuln-remediation state machine without turning every step into orchestration overhead?

## Design

- Keep the graph plugin-local: `plugins/vulnerability-remediation--node--npm/subgraph/`.
- Use one async LangGraph graph per workflow, not one graph per retry.
- Persist the Pydantic ledger only at semantic checkpoints: plan accepted, patch applied, gate result recorded, HITL decision recorded.
- Rehydrate from SQLite once on resume, then continue in-memory until the next checkpoint.
- Reuse the existing Phase 3/4/5 services as ports. Phase 6 composes them; it does not fork duplicate implementations.
- Expose a small harness-facing `VulnRemediationSut` contract so Phase 6.5 can invoke the workflow without importing the graph topology.

## Main performance choices

| Choice | Reason |
|---|---|
| Single graph per workflow | Avoid graph-construction churn and duplicate dependency wiring |
| Checkpoint on semantic boundaries | Durable enough for replay, cheaper than writing after every helper call |
| Typed ledger deltas | Smaller checkpoint payloads than repeated opaque snapshots |
| Harness invokes stable SUT adapter | Keeps eval harness cold-start cost bounded and decoupled from graph internals |

## Risks

- SQLite write amplification can still dominate very small fixtures; checkpoints need payload-size tests.
- A contract that is too abstract can hide useful graph observability from evals; expose evidence summaries in the result type.
- Retry loops may accidentally rebuild heavyweight dependencies unless constructors are separated from execution.
