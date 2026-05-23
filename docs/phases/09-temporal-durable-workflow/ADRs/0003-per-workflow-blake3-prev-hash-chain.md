# ADR-0003: Per-workflow BLAKE3 prev-hash chain (not global)

**Status:** Accepted
**Date:** 2026-05-23
**Tags:** event-sourcing · integrity · concurrency · failure-mode
**Related:** [ADR-0002](0002-phase-8-plugin-events-log-cutover-to-canonical-event-log.md), [ADR-0012](0012-event-store-topology-temporal-history-plus-postgres-events.md), [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)

## Context

The canonical event log appends typed events with a BLAKE3 `prev_hash` chain so a tamper attempt produces a verifiable break at read time. The security-first design [S] proposed a **global** chain (every event's `prev_hash` references the previous event written portfolio-wide). The critic's destruction of [S] showed two problems: (1) a global chain forces all event writes to serialize through one chain-head — kills concurrent-workflow throughput dead because COPY-binary appends cannot parallelize; (2) one workflow's tamper invalidates *every* later event in the entire portfolio, blast-radius-amplifying a single compromise.

Phase 9 needs the tamper-evidence property of a hash chain without the serial-bottleneck and blast-radius costs of the global version.

## Options considered

- **Global chain (single chain-head for the whole portfolio).** Maximum entanglement; every append must read the last `row_hash`. **Pattern:** classical append-only Merkle log. Throughput ≈ 1/RTT (one writer at a time). Blast radius: portfolio-wide.
- **No chain — rely on Postgres trigger + role-scoped grants.** Append-only enforced; mutation refused. **Pattern:** authorization-only integrity. No tamper-evidence if `application_role` itself is compromised.
- **Per-workflow chain (one chain-head per `workflow_id`).** Each workflow's events form their own hash chain; chain-verify is per-workflow at read time. **Pattern:** partitioned hash chain. Throughput: parallel across workflows. Blast radius: one workflow.

## Decision

Append `prev_hash = BLAKE3(prev_row.row_hash || canonical_payload)` per `workflow_id`; the first event for each workflow has `prev_hash = NULL`; chain-verify runs at projection read time per workflow. **Pattern: partitioned hash chain.**

## Tradeoffs

| Gain | Cost |
|---|---|
| Concurrent workflows append in parallel — G6's ≥ 3k events/sec is achievable | Same-workflow events must still serialize through one chain-head (per-workflow cache) |
| Tamper blast radius is **one workflow**, not the portfolio | Cannot detect a cross-workflow ordering attack (re-ordering rows across workflows is not chain-visible) |
| Chain-verify cost scales with workflow size (~12 events typical), not portfolio size | Portfolio events (`workflow_id = NULL`) need a separate chain or no chain; design picks "no chain" for portfolio rows |
| Per-workflow chain-head cache fits in 200-workflow LRU at the worker — bounded memory | Restart re-reads chain-tail from Postgres lazily on first append per workflow |
| Compromise of `application_role` corrupting a workflow halts only that workflow's projections | `ChainTamperDetected` must surface; otherwise silent corruption survives across workflows that never re-read the affected one |

## Pattern fit

Partitioned append-only hash chains are the standard relaxation when concurrent multi-writer throughput matters and per-partition isolation is the actual security boundary. The toolkit's `design-patterns-toolkit.md §Partitioning` calls out "partition by the natural unit of authorship — concurrent partitions write in parallel, integrity is per-partition". Workflow IDs are the natural authorship unit for this system: every event has exactly one workflow (or is portfolio-scoped); cross-workflow re-ordering attacks do not match the threat model (the attacker model is "compromised activity worker with `application_role` INSERT permission", which can write *only* into its own task-queue's allowlist of event kinds and is per-workflow scoped).

## Consequences

- `EventBatchWriter` keeps an LRU per-workflow chain-head cache (bounded by 200 in-flight workflows). Cold-restart re-reads the chain tail from Postgres on first append for each workflow.
- `events.events` schema carries `prev_hash BYTEA NULL` and `row_hash BYTEA NOT NULL` and a `wf_seq BIGINT NULL` per-workflow monotonic counter (the UNIQUE INDEX `events_wf_seq_uniq ON (workflow_id, wf_seq)` is what detects double-recording).
- Projections verify the chain as they fold. A break emits `ChainTamperDetected` (a `@critical_event` variant in [ADR-0006](0006-critical-event-synchronous-flush-vocabulary.md)) and halts the projection for that workflow.
- Portfolio events (`workflow_id = NULL`) are *not* chained — they are rare (config bootstrap, system-wide budgets) and the cross-workflow-ordering attack is out of scope.
- Phase-9 throughput target (G6: ≥ 3k events/sec) is achievable; would not have been with a global chain.
- A future ADR may add a global chain back as a *secondary* index if a portfolio-wide tamper-detection requirement materializes — additive.

## Reversibility

**Medium.** Switching to a global chain would require a schema migration (add a `global_seq` column with backfill), a data backfill that re-computes chain heads across the existing data, and an `EventBatchWriter` rewrite to single-writer mode. Doable but non-trivial. Switching to no-chain is trivial (set `prev_hash = NULL` always) but loses tamper-evidence.

## Evidence / sources

- [`../final-design.md §Lens summary — BLAKE3 chain is per-workflow not global`](../final-design.md)
- [`../final-design.md §Synthesis ledger — BLAKE3 chain scope row`](../final-design.md)
- [`../phase-arch-design.md §C5 — Canonical event log`](../phase-arch-design.md#c5--canonical-event-log-codegenievntslog-codegenievntspayloads-codegenievntsblob_refs)
- [`../phase-arch-design.md §Edge case 8`](../phase-arch-design.md#edge-cases)
- [`../critique.md §Attacks on the security-first design`](../critique.md)
- [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)
- BLAKE3 spec — `https://github.com/BLAKE3-team/BLAKE3-specs`
