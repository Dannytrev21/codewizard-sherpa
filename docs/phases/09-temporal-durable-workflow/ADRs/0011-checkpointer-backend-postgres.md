# ADR-0011: Postgres as the Phase-9 LangGraph checkpointer backend

**Status:** Accepted
**Date:** 2026-05-23
**Tags:** Adapter · checkpointer · durability · resolves-production-ADR-0016
**Related:** [ADR-0001](0001-phase-6-sqlite-checkpointer-cutover-policy.md), [ADR-0010](0010-activity-granularity-asymmetric.md), [production ADR-0016](../../../production/adrs/0016-checkpointer-backend.md)

## Context

Production ADR-0016 (checkpointer backend) was deferred at the production-design stage with the note "default to SQLite for local dev; Postgres for production; revisit when a production phase exercises it". Phase 9 is that phase. The Phase-6 SHERPA subgraph runs inside the fat `run_vuln_subgraph` Activity ([ADR-0010](0010-activity-granularity-asymmetric.md)); if the activity worker is SIGKILLed mid-subgraph, the activity must resume on a fresh worker at the same LangGraph node. SQLite cannot serve this — its checkpoint file lives on one host; the fresh worker is on a different host.

The available LangGraph checkpointer backends are: in-memory (no durability), SQLite (single-host durability, current Phase-6 default), and `langgraph-checkpoint-postgres` (multi-host durability via a shared Postgres). The decision is also load-bearing for the Phase-8 hash-chained log forward-emit story (the activity's idempotency-on-attempt-id requires a shared store readable from any worker).

## Options considered

- **Stay on SQLite for Phase 9.** Run the activity worker with a network-attached SQLite file (NFS, EFS). **Pattern:** shared-file SQLite. Subject to NFS file-locking quirks; checkpoint corruption risk on concurrent writes.
- **Build a new bespoke checkpointer.** Roll Phase-9 own, optimized for the Phase-6 case. **Pattern:** custom adapter. NIH; reinvents `langgraph-checkpoint-postgres`.
- **Adopt `langgraph-checkpoint-postgres` via `PostgresCheckpointerAdapter`.** Wrap upstream's `PostgresSaver` in a thin Adapter that adds `health() -> CheckpointerHealth` translation. **Pattern:** genuine Adapter (translates, does not forward), upstream Saver does the work.

## Decision

Phase 9 adopts `langgraph-checkpoint-postgres` via the `PostgresCheckpointerAdapter` Adapter. The adapter wraps upstream's `PostgresSaver`, exposes the `LangGraphCheckpointerPort` Protocol, and adds `health() -> CheckpointerHealth(pool_in_use, pool_idle, last_write_age_seconds)` translation that the upstream class does not expose. This resolves [production ADR-0016](../../../production/adrs/0016-checkpointer-backend.md) from Deferred → Accepted. **Pattern: genuine Adapter (translation, not forwarder).**

## Tradeoffs

| Gain | Cost |
|---|---|
| Activity worker SIGKILL → resume on any worker — required for G1 exit criterion | Postgres becomes a durability dependency for *every* in-flight Phase-9 workflow; cluster outage halts the system |
| Upstream-maintained checkpoint schema — no Phase-9 schema work | Upstream version pin matters; bumps may require checkpoint format migrations |
| The Adapter adds `health()` translation — earns the "Adapter" pattern name (per critic-3 on [B]'s "forwarder Adapter" attack) | One extra Pydantic model (`CheckpointerHealth`) for what is fundamentally a metric tuple |
| Schema ownership is clean: `langgraph_checkpoints` owned by upstream's `setup()`, not by Phase-9 alembic ([ADR-0011 §Internal structure](#consequences) below) | Three Postgres schemas in one database (`temporal`, `langgraph_checkpoints`, `events`); ownership boundary CI-asserted |
| Resolves production-ADR-0016 from Deferred → Accepted with real evidence | Future "Postgres is too heavy for local dev" pushback is countered only by "Docker is already required for Temporal anyway" |
| One `psycopg_pool.AsyncConnectionPool` per worker — shared with `emit_event` writer | Pool sizing is a tuning surface (`minsize=2, maxsize=20`); over-sized wastes Postgres connections, under-sized causes `PoolTimeoutError` under burst |

## Pattern fit

Genuine Adapter (toolkit `design-patterns-toolkit.md §Adapter — Adapter vs Forwarder`) is the right shape when "the upstream class does the work but exposes an interface that doesn't match the application's Port". `PostgresSaver` exposes checkpoint save/load; the application needs a Port that *also* exposes `health()` for operator portals. Wrapping it with a thin translation layer makes the Adapter genuine — it adds value beyond `def saver(self): return self._inner`. The critic correctly attacked single-implementation Adapters that are forwarders; this one isn't.

## Consequences

- `codegenie.durable.checkpointer.PostgresCheckpointerAdapter` wraps `langgraph_checkpoint_postgres.PostgresSaver`.
- `langgraph_checkpoints` schema is owned by upstream's `setup()` call — Phase-9 alembic does *not* migrate it. Ownership boundary asserted by `tests/fence/test_alembic_owns_only_events_schema.py`.
- The Adapter takes one `psycopg_pool.AsyncConnectionPool`; the same pool is shared with `EventBatchWriter` for `emit_event`.
- Upstream version pin in `pyproject.toml`; CI's pinned-version test catches schema bumps before merge.
- Pool exhaustion → `psycopg.PoolTimeoutError` → activity retries per `RetryPolicy` (5 s timeout, retry 3×).
- The Phase-6 `SqliteSaver` is unchanged; per [ADR-0001](0001-phase-6-sqlite-checkpointer-cutover-policy.md), existing Phase-6 workflows drain on SQLite while new ones start on Postgres.
- Production ADR-0016 is promoted from Deferred → Accepted with the Phase-9 evidence section appended (`docs/production/adrs/0016-checkpointer-backend.md` evidence row update).
- Phase 16 production deployment uses the same adapter against a production-grade Postgres cluster (potentially with read replicas for projection scaling).

## Reversibility

**Medium.** Switching to a different checkpointer backend later (e.g., a hypothetical Redis-backed saver) requires implementing a new Adapter and a one-shot data migration of in-flight workflow checkpoints — non-trivial but the `LangGraphCheckpointerPort` Protocol keeps the application code stable.

## Evidence / sources

- [`../phase-arch-design.md §C4 — Postgres checkpointer adapter`](../phase-arch-design.md#c4--postgres-checkpointer-adapter-codegeniedurablecheckpointer)
- [`../phase-arch-design.md §Path to production end state — Deferred ADRs`](../phase-arch-design.md#path-to-production-end-state)
- [`../final-design.md §4 — Postgres checkpointer adapter`](../final-design.md)
- [`../critique.md §Attacks on the best-practices design — forwarder Adapter`](../critique.md)
- [production ADR-0016](../../../production/adrs/0016-checkpointer-backend.md) — this ADR resolves it
- Upstream: `langgraph-checkpoint-postgres` — `https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-postgres`
