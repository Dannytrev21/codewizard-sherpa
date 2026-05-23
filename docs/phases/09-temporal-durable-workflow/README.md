# Phase 09 — Durable workflow envelope: Temporal

This folder holds the design pipeline for **Phase 9 — Durable workflow envelope: Temporal**
(see [`docs/roadmap.md`](../../roadmap.md) for the phase scope and exit criteria).

The state machine from Phase 6 gets wrapped in a Temporal workflow per [ADR-0003](../../production/adrs/0003-temporal-as-workflow-substrate.md); the SQLite checkpointer is replaced by Postgres per [ADR-0016](../../production/adrs/0016-checkpointer-backend.md); and the canonical event log primitive from [ADR-0034](../../production/adrs/0034-event-sourcing-canonical-primitive.md) lands operationally — Temporal's workflow history is the workflow-scoped store, with a typed Postgres side-channel for workflow-spanning concerns that Phases 11 and 13 will project off of.

## Reading order

1. **[`final-design.md`](final-design.md)** — **Design of record.** Read this first. Synthesized from the three competing designs below plus the critique. When other documents reference this phase's design, they reference `final-design.md`.
2. **[`critique.md`](critique.md)** — Devil's-advocate critique of all three competing designs.
3. **[`design-performance.md`](design-performance.md)** — Round-1 design under the performance-first lens.
4. **[`design-security.md`](design-security.md)** — Round-1 design under the security-first lens.
5. **[`design-best-practices.md`](design-best-practices.md)** — Round-1 design under the best-practices lens.

The three Round-1 designs are competing viewpoints, not iterative refinements. They were produced in parallel, then attacked by the critic, then reconciled by the Graph-of-Thought synthesizer. The per-lens designs and the critique are kept for audit; the **synthesized `final-design.md` is what implementation follows.**

## Next steps after this folder

This folder is the input to `phase-architect` (which produces `phase-arch-design.md`, per-phase ADRs under `ADRs/`, and `High-level-impl.md`), which is in turn the input to `phase-story-writer` (which decomposes the impl plan into autonomous-AI-agent-executable stories under `stories/`).
