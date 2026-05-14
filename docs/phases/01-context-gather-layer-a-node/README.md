# Phase 1 — Context gathering: Layer A (Node.js)

This folder contains the design of record for Phase 1 of the codewizard-sherpa roadmap, plus the artifacts that produced it. The design was synthesized via the multi-agent workflow defined in the `roadmap-phase-designer` skill: three competing single-lens designs, a devil's-advocate critique, and a Graph-of-Thought synthesis.

**Phase scope:** see [`../../roadmap.md`](../../roadmap.md) §"Phase 1 — Context gathering — Layer A (Node.js)".

## Status update (2026-05-13)

Production ADRs 0029–0034 (Task-Class Context Manifests, graph-aware queries, plugin architecture, language search adapters, domain modeling discipline, event sourcing) landed *after* Phase 1's design pipeline ran. Phase 1's design itself is mostly unaffected (the gather layer is plugin-agnostic), but two refinements layer on top:

- **Yarn variant detection (story `S2-02a` + Phase 1 [ADR-0013](ADRs/0013-yarn-variants-as-distinct-package-managers.md)).** The shipped `NodeBuildSystemProbe` collapses Yarn Classic and Yarn Berry into `"yarn"`. Production ADR-0031 (plugin scope tuple) treats them as distinct plugin scopes. The gather-layer fix lives in `stories/S2-02a-yarn-variant-detection.md`. Blocks `S3-03` (parser must branch on variant: Berry's `yarn.lock` is YAML).
- **Domain modeling discipline (production [ADR-0033](../../production/adrs/0033-domain-modeling-discipline.md)).** Applies forward from its date for all new Phase 1 code: newtype-per-identifier (`ProbeId`, `RepoId`, `SkillId`, etc.), smart constructors for parseable values, tagged unions for state machines, illegal-states-unrepresentable. Already-shipped Phase 1 code (raw `str` identifiers; `Optional[X]` / `bool` state) retrofits opportunistically as files are touched — tracked as a backlog item, not a phase blocker.

Phase 1's outputs feed downstream plugin dispatch: `RepoContext.node_build_system.build_system.package_manager` and `RepoContext.node_build_system.build_system.bundler` are load-bearing for Phase 8's Supervisor when it resolves which plugin handles a given workflow. Schema stability for those fields just gained a new consumer.

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
- **Prior phase:** [`../00-bullet-tracer-foundations/final-design.md`](../00-bullet-tracer-foundations/final-design.md)
- **Skill that produced these artifacts:** `roadmap-phase-designer`
- **Date generated:** 2026-05-12
