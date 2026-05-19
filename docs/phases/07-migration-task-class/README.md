# Phase 7 — Add migration task class (Chainguard distroless)

This folder contains the design pipeline for Phase 7 of the codewizard-sherpa roadmap. Phase 7 introduces the second task class — Chainguard distroless container migration — as a test of the project's extension-by-addition invariant.

## Reading order

1. **[final-design.md](final-design.md)** — **The design of record.** Synthesized from the three competing designs + critique via Graph-of-Thought decomposition. Implementers read this first.
2. **[critique.md](critique.md)** — Devil's-advocate critique of all three competing designs. Read second to understand the synthesis context.
3. **[design-performance.md](design-performance.md)** — Round 1 design under the performance-first lens (throughput, latency, token economy).
4. **[design-security.md](design-security.md)** — Round 1 design under the security-first lens (isolation, least privilege, audit, supply chain).
5. **[design-best-practices.md](design-best-practices.md)** — Round 1 design under the best-practices lens (idiomatic, maintainable, conventional, well-tested).

## Status

`final-design.md` is the canonical reference. Per-lens designs and the critique are kept for audit only.

After this design pipeline, the [`phase-architect`](../../../.claude/skills/) skill expands `final-design.md` into:

- `phase-arch-design.md` — 4+1 architectural views, testing strategy, edge cases, gap analysis.
- `ADRs/` — Per-phase Architecture Decision Records in Nygard format.
- `High-level-impl.md` — Ordered step-by-step implementation plan.

The [`phase-story-writer`](../../../.claude/skills/) skill then decomposes those artifacts into autonomous-AI-agent-executable stories under `stories/`.
