# Phase 6 — SHERPA-style state machine for the vuln loop

This folder contains the design of record for Phase 6 of the codewizard-sherpa roadmap, plus the artifacts that produced it. The design was synthesized via the multi-agent workflow defined in the `roadmap-phase-designer` skill: three competing single-lens designs, a devil's-advocate critique, and a Graph-of-Thought synthesis.

**Phase scope:** see [`../../roadmap.md`](../../roadmap.md) §"Phase 6 — SHERPA-style state machine for the vuln loop".

## Reading order

1. **[final-design.md](final-design.md)** — the **design of record**. Start here if you are implementing this phase. Includes the full synthesis ledger (vertex counts, edge classifications, conflict-resolution scores, provenance annotations).
2. **[critique.md](critique.md)** — the devil's-advocate critique against the three single-lens designs.
3. **[design-performance.md](design-performance.md)** — performance-first design (lens [P]).
4. **[design-security.md](design-security.md)** — security-first design (lens [S]).
5. **[design-best-practices.md](design-best-practices.md)** — best-practices design (lens [B]).

When other documents link to *this phase's design*, link to [final-design.md](final-design.md), not the per-lens drafts.

## Provenance

- **Roadmap:** [`docs/roadmap.md`](../../roadmap.md)
- **Production design reference:** [`docs/production/design.md`](../../production/design.md)
- **Prior phases:**
  - [`../00-bullet-tracer-foundations/final-design.md`](../00-bullet-tracer-foundations/final-design.md)
  - [`../01-context-gather-layer-a-node/final-design.md`](../01-context-gather-layer-a-node/final-design.md)
  - [`../02-context-gather-layers-b-g/final-design.md`](../02-context-gather-layers-b-g/final-design.md)
  - [`../03-vuln-deterministic-recipe/final-design.md`](../03-vuln-deterministic-recipe/final-design.md)
  - [`../04-vuln-llm-fallback-rag/final-design.md`](../04-vuln-llm-fallback-rag/final-design.md)
  - [`../05-sandbox-trust-gates/final-design.md`](../05-sandbox-trust-gates/final-design.md)
- **Skill that produced these artifacts:** `roadmap-phase-designer`
- **Date generated:** 2026-05-12
