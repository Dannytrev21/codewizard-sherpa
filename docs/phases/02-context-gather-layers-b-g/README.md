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

## Phase 2 ADRs

The nine Step-1 ADRs (0001–0009) ship with the Step-1 code in story S1-11; each is **Accepted** and frozen. 02-ADR-0010 is pre-drafted in this directory but its enforcement code (the `RedactedSlice` smart constructor) lands in S3-02 (Step 3) — it is listed under a separate sub-bullet so a casual reader does not assume it is Step-1-active.

**Step-1 (land with S1-11):**

- [0001 — Add docker + security CLIs to ALLOWED_BINARIES](ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md) — Accepted
- [0002 — Tree-sitter grammars Phase 2 amendment](ADRs/0002-tree-sitter-grammars-phase-2-amendment.md) — Accepted
- [0003 — Coordinator heaviness sort + annotation](ADRs/0003-coordinator-heaviness-sort-annotation.md) — Accepted
- [0004 — Image digest as declared-input token](ADRs/0004-image-digest-as-declared-input-token.md) — Accepted
- [0005 — Secret findings: no plaintext persistence](ADRs/0005-secret-findings-no-plaintext-persistence.md) — Accepted
- [0006 — IndexFreshness sum-type location](ADRs/0006-index-freshness-sum-type-location.md) — Accepted
- [0007 — No plugin loader in Phase 2](ADRs/0007-no-plugin-loader-in-phase-2.md) — Accepted
- [0008 — No event stream in Phase 2](ADRs/0008-no-event-stream-in-phase-2.md) — Accepted
- [0009 — pytest-xdist veto preserved](ADRs/0009-pytest-xdist-veto-preserved.md) — Accepted

**Pre-drafted; enforcement code lands in S3-02 (Step 3):**

- [0010 — RedactedSlice smart constructor at the writer boundary](ADRs/0010-redacted-slice-smart-constructor-at-writer-boundary.md) — Accepted (file present; the runtime `RedactedSlice` ships in story S3-02)

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

## Phase 2 exit-criteria — closed

**Canonical mapping table:** see [stories/README.md §Exit-criteria coverage](stories/README.md#exit-criteria-coverage). The high-level G1–G10 sign-off below is a Step-8 summary, not a duplicate of the canonical table.

- [x] **G1.** Every language-agnostic Layer B–G probe ships with golden-file coverage against the 5-repo portfolio (S4-01..S4-06, S5-02..S5-04, S6-01..S6-08, S7-01..S7-05).
- [x] **G2.** `IndexHealthProbe` (B2) surfaces a real staleness case in CI against `stale-scip` (S4-01 + S4-02 + S7-02; gated by `adv-phase02` in S8-03).
- [x] **G3.** Phase 0/1 frozen surfaces unchanged — contract-freeze snapshot still passes (S1-09 ADR-0004 amendment + S8-03 `contract-freeze` CI job).
- [x] **G4.** `IndexFreshness = Fresh | Stale(reason)` at `src/codegenie/indices/freshness.py`; `confidence_section.py` consumes with exhaustive `match` + `assert_never` (S1-01 + S8-01 + S8-03 `mypy --warn-unreachable`).
- [x] **G5.** Secret findings redacted at the writer chokepoint; plaintext in zero persisted files (S3-01 + S3-02 + S3-03 + S6-07 + S7-04).
- [x] **G6.** One subprocess port for Layer B/G external CLIs (`run_external_cli`); Layer C uses `run_allowlisted` directly (S1-07 + S5-02 + S6-06..S6-08).
- [x] **G7.** Cost target $0/run, tokens-per-gather = 0 — `fence` CI job stays green (S1-11 + S8-03).
- [x] **G8.** Wall-clock advisory targets covered by three bench canaries including the hosted-runner emulation (S8-03 `bench` lane + nightly).
- [x] **G9.** Kernel scaffolding ships — adapter `Protocol`s + `TCCMLoader` + `SkillsLoader` + `IndexFreshness`; NO Plugin Loader, NO `plugin.yaml` parser, NO `plugins/` directory (deferred to Phase 3 per 02-ADR-0007 + production ADR-0031).
- [x] **G10.** Nine new ADRs land in `ADRs/` alongside the code (S1-11; 0001–0009 + 0010 pre-drafted enforced in S3-02).

**Sign-off:** Phase 2 Step 8 closed by stories S8-01 (Confidence section renderer + `mypy --warn-unreachable`), S8-02 (CLI Phase-2 stdout summary block), S8-03 (eight CI lanes + three advisory bench canaries + hosted-runner nightly), and S8-04 (Phase-3 handoff issues + `docs/contributing.md` Layer B–G addendum + this exit-criteria sign-off).
