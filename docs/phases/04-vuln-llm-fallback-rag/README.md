# Phase 04 — Vuln remediation: LLM fallback + solved-example RAG

This folder holds the design artifacts for **Phase 4** of the codewizard-sherpa roadmap. Phase 4 introduces the **first LLM** into the system — but only as a leaf inside the recipe → RAG → LLM-fallback decision chain ([ADR-0011](../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md)). Phase 3 ships the deterministic recipe path; Phase 4 adds the fallback tiers that handle cases recipes cannot reach (transitive vulns requiring peer-dep upgrades, major-version bumps with breaking-change call-site rewrites). Confidence is computed from objective signals only ([ADR-0008](../../production/adrs/0008-objective-signal-trust-score.md)).

This phase was **re-designed** to absorb the plugin framing introduced by [ADR-0029](../../production/adrs/0029-task-class-context-manifests.md) (TCCMs), [ADR-0030](../../production/adrs/0030-graph-aware-context-queries.md) (graph-aware queries), [ADR-0031](../../production/adrs/0031-plugin-architecture.md) (plugin architecture), and [ADR-0032](../../production/adrs/0032-language-search-adapters.md) (language search adapters). All Phase 4 work lands inside `plugins/vulnerability-remediation--node--npm/` (extension by addition). It also lands the first `typecheck.*` `SignalKind` per [ADR-0037](../../production/adrs/0037-layered-analysis-funnel-scip-typechecker-lsp.md) and inherits the provenance refuse-mode shipped in Phase 3 per [ADR-0038](../../production/adrs/0038-vulnerability-provenance-attribution.md).

## Reading order

1. **[final-design.md](final-design.md)** — the **design of record**. Synthesized from three competing lens designs + a devil's-advocate critique. This is what implementers read.
2. **[critique.md](critique.md)** — devil's-advocate attack on all three lens designs. Useful for understanding *why* the final design departs from each lens.
3. **[design-performance.md](design-performance.md)** — performance-first lens (Round 1). Throughput, latency, $/PR, cache hit rate.
4. **[design-security.md](design-security.md)** — security-first lens (Round 1). Isolation, least privilege, audit, supply chain.
5. **[design-best-practices.md](design-best-practices.md)** — best-practices lens (Round 1). Idiomatic, maintainable, conventional, well-tested.

## Provenance

Produced by the `roadmap-phase-designer` skill on 2026-05-18: three parallel design subagents → one devil's-advocate critic → one Graph-of-Thought synthesizer. The per-lens designs and the critique are kept for audit; `final-design.md` is what subsequent phases (`phase-architect`, `phase-story-writer`) read.

## What comes next

- **`phase-architect`** consumes `final-design.md` and produces `phase-arch-design.md` (4+1 views, edge cases, testing strategy), `ADRs/` (Nygard-format per-phase decisions), and `High-level-impl.md` (ordered step-by-step plan).
- **`phase-story-writer`** consumes the architect artifacts and produces `stories/` — autonomous-AI-agent-executable user stories under red-green-refactor TDD.
