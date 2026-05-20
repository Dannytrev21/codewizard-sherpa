# Phase 7.5 — Multi-language foundations + Python

Design artifacts for roadmap Phase 7.5 — the second target language (Python) introduced
by addition, plus the `LanguagePack` contract, `register_language()`, the `tests/conformance/`
tier, and the ADR-0043 discipline reframe.

Produced by the `roadmap-phase-designer` skill (three competing lens designs → devil's-advocate
critique → Graph-of-Thought synthesis).

## Reading order

1. **[final-design.md](final-design.md)** — **the design of record.** Start here. Synthesized
   from the three competing designs and the critique. When other documents link to Phase 7.5's
   design, they link to this file.
2. **[critique.md](critique.md)** — devil's-advocate critique of all three competing designs.
   Read this to understand which weaknesses the final design had to resolve.
3. **[design-performance.md](design-performance.md)** — Round 1, performance-first lens.
4. **[design-security.md](design-security.md)** — Round 1, security-first lens.
5. **[design-best-practices.md](design-best-practices.md)** — Round 1, best-practices lens.

The three per-lens designs and the critique are kept for audit. Execution follows
`final-design.md` only.

## Next steps

`final-design.md` feeds the `phase-architect` skill, which produces `phase-arch-design.md`,
per-phase `ADRs/`, and `High-level-impl.md`. Those in turn feed `phase-story-writer`, which
decomposes the phase into executable stories under `stories/`.
