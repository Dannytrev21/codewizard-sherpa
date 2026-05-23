# ADR-0012: Event store topology — Temporal workflow history (workflow-scoped) + Postgres `events.events` (workflow-spanning)

**Status:** Accepted
**Date:** 2026-05-23
**Tags:** event-sourcing · separation-of-concerns · projection · operational
**Related:** [ADR-0003](0003-per-workflow-blake3-prev-hash-chain.md), [ADR-0005](0005-payload-by-reference-blobref-threshold.md), [ADR-0006](0006-critical-event-synchronous-flush-vocabulary.md), [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md)

## Context

[ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md) mandates event sourcing as the canonical primitive — projections fold typed events into the read paths consumers (Phase 11 KG, Phase 13 cost ledger, Phase 13.5 portal) need. Temporal already provides a workflow event log (workflow history) per workflow, which survives worker crashes and cluster restarts. But Temporal's workflow history is *workflow-scoped* (you cannot query across workflows efficiently) and is GC'd by retention policy (~30 days in dev). Projections that fold across workflows (`retry_histogram` over all `TrustGateFailed`, `plugin_telemetry` over all `PluginResolved × MergeOutcome`) need a portfolio-spanning store that survives the retention window.

The performance-first design [P] proposed only Postgres (`events.events`). The best-practices design [B] proposed only Temporal history. The critic showed both single-substrate positions break: Temporal history alone cannot serve cross-workflow projections; Postgres alone duplicates Temporal's workflow-scoped durability and risks divergence ("did this activity result actually commit to Postgres before the workflow accepted the return value?").

## Options considered

- **Single substrate: Temporal history only.** Projections read Temporal history via the SDK; cross-workflow queries are SDK-side iteration. **Pattern:** uniform Temporal-native. Retention-window limit; no cross-workflow query indexes; projection lag tied to SDK iteration speed.
- **Single substrate: Postgres `events.events` only.** Every activity emits to Postgres; Temporal history is the orchestration record only. **Pattern:** uniform Postgres-native. Postgres becomes the durability path; Temporal's already-recorded activity results are redundant; risk of "history says success, Postgres doesn't" divergence.
- **Hybrid: Temporal history for workflow-internal control flow; Postgres `events.events` for workflow-spanning typed projections.** Temporal history is the *workflow's* event store (control flow, signals, activity results). Postgres `events.events` is the *portfolio's* event store (the typed audit + projection substrate). The `emit_event` Activity is the writer; the per-workflow BLAKE3 chain ([ADR-0003](0003-per-workflow-blake3-prev-hash-chain.md)) ensures tamper-evidence. **Pattern:** layered event stores with explicit boundaries.

## Decision

Two event stores, each with a single explicit purpose: **Temporal workflow history** is the workflow-scoped, control-flow store (activity dispatches, signals, query state); **Postgres `events.events`** is the workflow-spanning typed-event store (the 21-variant discriminated union, per-workflow BLAKE3 chain, the substrate projections fold). Activities that take a side-effect in the world also emit a typed event to `events.events` via the `emit_event` Activity. **Pattern: layered event stores with explicit purpose-per-substrate.**

## Tradeoffs

| Gain | Cost |
|---|---|
| Workflow-internal control flow lives where it's natural — in Temporal history, GC'd by retention | Two stores to reason about; the boundary "what goes where" must be documented and held |
| Cross-workflow projections (`retry_histogram`, `plugin_telemetry`) have a real portfolio-wide indexed substrate | The `emit_event` path is an extra activity hop per side-effect — ~10 ms wall-clock |
| `events.events` outlives Temporal's retention — audit-class 365-day retention per ADR-0040 | Postgres becomes a load-bearing piece of the application beyond just checkpointing |
| `WorkflowHistoryFanout` decision: only events the workflow *actually* needs to durably record cross-workflow ride the `emit_event` path | Engineers must remember "this event needs to fan out" — the decision is per-event, encoded in the activity body |
| Per-workflow BLAKE3 chain in `events.events` gives tamper-evidence on the projection substrate ([ADR-0003](0003-per-workflow-blake3-prev-hash-chain.md)) | Temporal history does not have the same tamper-evidence; the trust model for history is "Temporal cluster integrity", not application chain |
| `@critical_event` events ([ADR-0006](0006-critical-event-synchronous-flush-vocabulary.md)) ensure synchronous Postgres durability for audit-critical types — Temporal-only would have to trust retention | Synchronous-flush has its own latency cost (~10 ms per critical event) |

## Pattern fit

Layered event stores with explicit purpose-per-substrate is the canonical pattern when "one store is operationally optimal for one scope but not the other". Temporal's history is hyper-optimized for workflow-scoped replay; Postgres is hyper-optimized for cross-row queries. The toolkit's `design-patterns-toolkit.md §Separation by access pattern` calls out "split the substrate when the access patterns are genuinely orthogonal — workflow-internal replay vs portfolio-wide projection are orthogonal access patterns". The `emit_event` Activity is the integration point — explicit, typed, fenced.

## Consequences

- `events.events` lives in Postgres schema `events`, owned by Phase-9 alembic (see [ADR-0011](0011-checkpointer-backend-postgres.md) and the alembic discipline section).
- `emit_event` is one Activity on the `system` task queue ([ADR-0007](0007-two-task-queue-partitioning-and-expansion-by-addition.md)).
- Per-workflow BLAKE3 chain ([ADR-0003](0003-per-workflow-blake3-prev-hash-chain.md)) operates only on `events.events`, not Temporal history.
- Projections (`audit_trail`, `retry_histogram`, `plugin_telemetry` in Phase 9; cost-ledger in Phase 13; KG-writeback in Phase 11) fold only `events.events`.
- The 21-variant `EventPayload` discriminated union is the contract for what `events.events` accepts; the union grows by addition.
- Workflow history is *not* a projection target — projections that need workflow-internal detail (rare; mostly debugging) call the Temporal SDK directly.
- A `WorkflowHistoryFanout` discipline (which events ride `emit_event` from which Activities) is implicit in the Activity code; documented per-activity in [phase-arch-design.md §C2](../phase-arch-design.md#c2--activity-catalog-codegeniedurableactivities).
- If a future activity needs to emit an event that *doesn't* exist in the union, the contributor adds a new Pydantic variant (one file change) — no schema migration (JSONB payload).

## Reversibility

**Medium.** Collapsing the two stores into Postgres-only would mean re-implementing Temporal's history equivalents — non-trivial. Collapsing into Temporal-only would mean re-implementing projection indexing on top of the SDK iteration — also non-trivial. The two-store shape is durable.

## Evidence / sources

- [`../phase-arch-design.md §Architectural context — Temporal history is workflow-scoped; events.events is workflow-spanning`](../phase-arch-design.md#architectural-context)
- [`../phase-arch-design.md §C5 — Canonical event log`](../phase-arch-design.md#c5--canonical-event-log-codegenievntslog-codegenievntspayloads-codegenievntsblob_refs)
- [`../phase-arch-design.md §Design patterns applied — #7 Event sourcing for agent runs`](../phase-arch-design.md#design-patterns-applied)
- [`../final-design.md §Departures from all three inputs #4`](../final-design.md)
- [`../final-design.md §Synthesis ledger — two-database vs one row`](../final-design.md)
- [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md) — canonical primitive
- [production ADR-0040](../../../production/adrs/0040-data-lifecycle-retention-and-classification.md) — audit-class retention
