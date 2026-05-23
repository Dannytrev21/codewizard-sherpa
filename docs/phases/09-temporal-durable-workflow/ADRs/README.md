# Phase 09 — Durable workflow envelope: Temporal: ADRs

Architecture Decision Records for Phase 9, in Nygard format. Each ADR captures one load-bearing decision: context, alternatives, what was chosen, tradeoffs, consequences, and reversibility.

**Phase architecture:** [phase-arch-design.md](../phase-arch-design.md)
**Source design:** [final-design.md](../final-design.md)
**Critique:** [critique.md](../critique.md)
**Production reference:** [docs/production/adrs/](../../../production/adrs/)

## Index

| # | Title | Tags |
|---|---|---|
| [0001](0001-phase-6-sqlite-checkpointer-cutover-policy.md) | Phase-6 SQLite checkpointer drain-don't-cutover policy | Adapter · migration · backward-compatibility |
| [0002](0002-phase-8-plugin-events-log-cutover-to-canonical-event-log.md) | Phase-8 `codegenie.plugins.events` log → canonical event log cutover schedule | strangler-fig · event-sourcing · cutover |
| [0003](0003-per-workflow-blake3-prev-hash-chain.md) | Per-workflow BLAKE3 prev-hash chain (not global) | event-sourcing · integrity · concurrency · failure-mode |
| [0004](0004-workflow-determinism-enforcement-three-layers.md) | Workflow-determinism enforcement via three layers (import-linter + AST fence + Replayer) | determinism · fence · static-analysis · CI-gate |
| [0005](0005-payload-by-reference-blobref-threshold.md) | Payload-by-reference via `BlobRef` for activity payloads > 8 KiB | smart-constructor · content-addressing · history-compactness |
| [0006](0006-critical-event-synchronous-flush-vocabulary.md) | `@critical_event` synchronous-flush vocabulary | Open/Closed · decorator-registry · event-sourcing · durability |
| [0007](0007-two-task-queue-partitioning-and-expansion-by-addition.md) | Two-task-queue partitioning in Phase 9; expansion by addition | isolation · blast-radius · expansion-by-addition · workers |
| [0008](0008-typed-credential-blocklist-not-regex.md) | `RedactedActivityResult.seal()` — typed-credential-class blocklist (not regex; capability is process-level not cryptographic) | smart-constructor · secret-redaction · capability-pattern · type-driven-security |
| [0009](0009-no-pgcrypto-column-encryption.md) | No `pgcrypto` column encryption on `events.payload`; encryption-at-rest delegated to volume layer | anti-decision · threat-modeling · defense-in-depth · YAGNI |
| [0010](0010-activity-granularity-asymmetric.md) | Asymmetric activity granularity — 1:1 for Phase-8 Supervisor; one fat Activity for Phase-6 SHERPA subgraph | activity-decomposition · adapter · SutDigest · backward-compatibility |
| [0011](0011-checkpointer-backend-postgres.md) | Postgres as the Phase-9 LangGraph checkpointer backend | Adapter · checkpointer · durability · resolves-production-ADR-0016 |
| [0012](0012-event-store-topology-temporal-history-plus-postgres-events.md) | Event store topology — Temporal workflow history (workflow-scoped) + Postgres `events.events` (workflow-spanning) | event-sourcing · separation-of-concerns · projection · operational |
| [0013](0013-no-temporal-port-abstraction.md) | No `TemporalPort` / durable-execution abstraction (premature pluggability) | anti-decision · premature-abstraction · YAGNI · pattern-soup |
| [0014](0014-multi-plugin-parent-workflow-as-temporal-shape.md) | `MultiPluginParentWorkflow` as a real Temporal parent/child workflow shape | sum-type · parent-child-workflow · ADR-0042-rendering |
| [0015](0015-temporal-ui-loopback-only.md) | `temporal-ui` bound to `127.0.0.1:8233` only | dev-surface · attack-surface · fence |

## Conventions

- Filenames are `NNNN-kebab-case-title.md`, numbered locally per phase starting at 0001.
- Numbers are immutable; superseded ADRs keep their number and cross-link.
- Cross-references to production ADRs use `../../../production/adrs/NNNN-*.md`; to other phase-9 ADRs, plain relative paths.
- New ADRs are additive — they do not edit existing ones unless explicitly superseding (in which case both are kept and cross-linked).

## Decisions noted but not yet documented

These are surfaced in [phase-arch-design.md §Open questions deferred to implementation](../phase-arch-design.md#open-questions-deferred-to-implementation) and are *not* yet ADR-worthy — they will become ADRs only after evidence accumulates during implementation or in a subsequent phase:

- Continue-as-new for `run_vuln_subgraph` approaching the 20-min cap (Phase 10 may force the decision).
- Whether `@critical_event` events should also write through the EventBatchWriter for redundancy after the sync path commits.
- Postgres connection-pool sizing under burst (`minsize=2, maxsize=20` baseline; tuned by G6 throughput canary).
- Whether `ParentResult.SomeMerged` auto-emits `HumanReviewRequested` for unmerged children (deferred to Phase 10).
- Whether to ship Phase-9 Worker Versioning in dev mode (Phase 16 hardening will land it; Phase 9 dev mode may opt-in earlier).
- Whether the `EventLog` should expose a `read_kind` API for cross-workflow projections.

## Gap-driven future ADRs

These ADRs are anticipated from [phase-arch-design.md §Gap analysis & improvements](../phase-arch-design.md#gap-analysis--improvements) but defer to canary or implementation evidence:

- **Future ADR-0016** — `route` activity overhead canary result (Gap 1: collapse to `[S]`-shape or keep `[P]/[B]`-shape based on `tests/perf/test_phase09_route_activity_overhead.py`).
- **Future ADR-0017** — `MultiPluginDispatch.coordination_policy` field default + sibling-failure semantics (Gap 2; landed when Phase 10 exercises `Both`).
- **Future ADR-0018** — `freshness_window` on recorded routing decisions (Gap 3: handles workflow-resume-weeks-later → GC'd `gather_id`).
