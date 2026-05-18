# Phase 3 — Vuln remediation: deterministic recipe path

**Status:** Design pipeline complete (designer → critic → synthesizer → architect → ADR-extractor → impl-planner → story-writer). Ready for `phase-story-validator` + `phase-story-executor`.

This phase ships the first end-to-end deterministic transform in the system — given a Node.js repo with a known npm CVE, produce a working patch diff on a local branch with no LLM in the loop. It also lands the **first plugin** (`plugins/vulnerability-remediation--node--npm/`) and the **universal `(*,*,*)` HITL fallback**, exercising the plugin architecture ([ADR-0031](../../production/adrs/0031-plugin-architecture.md)) for the first time.

Phase 3 was previously designed and removed pending plugin-architecture redesign. This redesign absorbs ADRs 0029 (TCCMs), 0030 (graph-aware queries), 0031 (plugin architecture), 0032 (language search adapters), 0033 (domain modeling discipline), and 0034 (event sourcing canonical primitive).

## Reading order

| # | File | Purpose |
|---|---|---|
| 1 | [`final-design.md`](final-design.md) | **Design of record.** Synthesizes the three competing designs plus the critique into the architecture implementers will build. Read this first; everything else is audit. |
| 2 | [`critique.md`](critique.md) | Devil's-advocate critique of all three competing designs. Surfaces the conflicts the synthesizer had to resolve. |
| 3 | [`design-performance.md`](design-performance.md) | Performance-first competing design (round 1). Workflows-per-hour, token economy, cache locality. |
| 4 | [`design-security.md`](design-security.md) | Security-first competing design (round 1). Isolation, least privilege, audit, supply chain. |
| 5 | [`design-best-practices.md`](design-best-practices.md) | Best-practices competing design (round 1). Idiomatic Python, plugin contract shape, conventions. |

When other documents link to "the Phase 3 design," they link to [`final-design.md`](final-design.md). The competing designs and critique are kept for audit.

## What ships in this phase

- First plugin: `plugins/vulnerability-remediation--node--npm/` with TCCM, language adapters, deterministic recipe engine, Skills, and subgraph nodes.
- Universal HITL fallback plugin: `plugins/universal--*--*/` — never silently fail; always escalate.
- `RemediationOrchestrator`, `TrustScorer`, `Transform` ABC, `ApplyContext` — the Phase 5 contract surface.
- Synthetic third test plugin (`tests/fixtures/plugins/example--noop--*/`) — proves the plugin Protocol takes >1 implementation before Phase 7 lands.
- Typed event-sourcing emission (per ADR-0034) — `workflow-internal` (→ Temporal in Phase 9) and `workflow-spanning` (→ Postgres side-channel in Phase 9) streams, same Pydantic types.
- Working end-to-end demo: given a Node.js repo with a known npm CVE, produce a patch diff that installs cleanly and passes the repo's own tests inside the interim sandbox.

## Next steps in the design pipeline

1. ~~**`phase-architect`** — produces `phase-arch-design.md` (4+1 views), per-phase ADRs in `ADRs/`, and `High-level-impl.md`.~~ ✅ done — see [`phase-arch-design.md`](phase-arch-design.md), [`ADRs/`](ADRs/), [`High-level-impl.md`](High-level-impl.md).
2. ~~**`phase-story-writer`** — decomposes `High-level-impl.md` into autonomous-implementer stories under `stories/`.~~ ✅ done — 42 stories under [`stories/`](stories/) (see [`stories/README.md`](stories/README.md) for the manifest).
3. **`phase-story-validator`** — hardens each story before `phase-story-executor` runs it.
4. **`phase-story-executor`** — implements each story via TDD red-green-refactor.
