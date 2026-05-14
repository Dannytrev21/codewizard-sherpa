# Phase 2 — Context gathering: Layers B–G

This folder contains the design of record for Phase 2 of the codewizard-sherpa roadmap, plus the artifacts that produced it. The design was synthesized via the multi-agent workflow defined in the `roadmap-phase-designer` skill: three competing single-lens designs, a devil's-advocate critique, and a Graph-of-Thought synthesis.

**Phase scope:** see [`../../roadmap.md`](../../roadmap.md) §"Phase 2 — Context gathering — Layers B–G".

## Context for this design run (2026-05-14)

Phase 2 is the first phase whose design pipeline ran *after* production ADRs 0029–0034 (Task-Class Context Manifests, graph-aware queries, plugin architecture, language search adapters, domain modeling discipline, event sourcing) landed. The roadmap explicitly flagged Phase 2 as **pending plugin-architecture redesign** because those ADRs materially changed how Layers B–G ship — the kernel/plugin split, the TCCM loader, the adapter `Protocol` contracts, and the `IndexFreshness` sum type are all consequences of that framing being absorbed into this design.

The synthesis explicitly resolved five tensions the critic surfaced:

1. **Plugin-loader scope** — only kernel-side scaffolding ships in Phase 2 (adapter `Protocol`s, TCCM loader, Skills loader, `IndexFreshness`, registration plumbing). The plugin *loader* itself, the universal `(*, *, *)` fallback, and the first concrete plugin remain Phase 3 deliverables per ADR-0031 §Consequences §1.
2. **Probe contract additions** — Phase 0's frozen ABC is preserved. Heaviness and ordering hints attach as registry-side `@register_probe(...)` kwargs, not new ABC fields.
3. **`IndexFreshness` sum type** — one canonical name, one module (`src/codegenie/indices/freshness.py`), one variant set; competing `IndexConfidence` / `AdapterConfidence` proposals deferred to Phase 3.
4. **Secret-finding redaction** — Phase 2 persists zero secret plaintext. Only fingerprints land in artifacts. Phase 5 microVM remains the named escalation door for any cleartext-required judgment.
5. **`pytest-xdist` veto** — preserved from Phase 0. The Phase 2 portfolio fits serial CI inside the target budget.

## Reading order

1. **[final-design.md](final-design.md)** — the **design of record**. Start here if you are implementing this phase. Includes the full synthesis ledger (vertex counts, edge classifications, conflict-resolution scores, provenance annotations).
2. **[critique.md](critique.md)** — the devil's-advocate critique against the three single-lens designs. Read after `final-design.md` to understand which wounds the synthesis was forced to address.
3. **[design-performance.md](design-performance.md)** — performance-first design (lens [P]).
4. **[design-security.md](design-security.md)** — security-first design (lens [S]).
5. **[design-best-practices.md](design-best-practices.md)** — best-practices design (lens [B]).

When other documents link to *this phase's design*, link to [final-design.md](final-design.md), not the per-lens drafts. The per-lens drafts and the critique are kept for audit, not for execution.

## Provenance

- **Roadmap:** [`docs/roadmap.md`](../../roadmap.md)
- **Production design reference:** [`docs/production/design.md`](../../production/design.md)
- **Local POC contract:** [`docs/localv2.md`](../../localv2.md)
- **Prior phases:**
  - [`../00-bullet-tracer-foundations/final-design.md`](../00-bullet-tracer-foundations/final-design.md)
  - [`../01-context-gather-layer-a-node/final-design.md`](../01-context-gather-layer-a-node/final-design.md)
- **Key ADRs absorbed:** [0029](../../production/adrs/0029-task-class-context-manifests.md), [0030](../../production/adrs/0030-graph-aware-context-queries.md), [0031](../../production/adrs/0031-plugin-architecture.md), [0032](../../production/adrs/0032-language-search-adapters.md), [0033](../../production/adrs/0033-domain-modeling-discipline.md), [0034](../../production/adrs/0034-event-sourcing-canonical-primitive.md)
- **Skill that produced these artifacts:** `roadmap-phase-designer`
- **Date generated:** 2026-05-14
