# ADR-0016: Checkpointer backend (Postgres vs Redis)

**Status:** Deferred
**Date:** 2026-05-11
**Tags:** platform · storage
**Related:** ADR-0001, ADR-0003

## Context

LangGraph's checkpointer backs durable state across `interrupt()` calls. When a worker subgraph is paused awaiting human review, the state is serialized to the checkpointer and rehydrated when work resumes — potentially days later (ADR-0009 implies this is the common case).

The checkpointer needs three properties: durable persistence, efficient lookup by workflow ID, and reasonable concurrency. Both Postgres and Redis satisfy all three; the right pick depends on volume and write patterns.

## Options considered

- **`InMemorySaver`** (LangGraph default). Works for development and tests. Lost on process restart. Not viable for production.
- **Postgres.** Single source of truth, ACID, easy queries for "show me all checkpointed workflows for this repo." Higher write latency than Redis. Already in the stack (Temporal uses it).
- **Redis.** Lower latency, simpler ops, in-memory primary. Persistence requires RDB/AOF configuration. Cluster mode adds complexity.
- **SQLite per worker** (LangGraph supports this). Operationally simple but doesn't survive worker rotation.

## Default until decided

**`InMemorySaver`** for development and tests; **Postgres** as the production default unless volume estimates show write throughput problems.

Postgres is the safe default because:
- Already in the stack for Temporal state (ADR-0003)
- ACID guarantees, simple to back up, simple to query
- One database to operate, not two

## Evidence needed to resolve

- **Volume estimate.** Workflows per day × average checkpoint frequency × average state size = write throughput requirement.
- **Interrupt frequency.** If `interrupt()` fires on every gate transition (worst case), checkpointer write throughput must match gate throughput. If `interrupt()` fires only on retry-exhaustion (more typical), throughput is much lower.
- **Query patterns.** If operators need to list "all paused workflows older than 24h" frequently, Postgres queries are easier. If lookups are exclusively by workflow ID, Redis is equally good.
- **Redis ops experience.** Does the team have production Redis ops experience? If not, Postgres reduces the on-call surface area.

## Reversibility (of the eventual choice)

**Medium cost** if migrating Postgres → Redis after the fact: need to migrate in-flight checkpointed state (workflows can be days old). **Low cost** if going Redis → Postgres: state can be drained as workflows complete.

## Evidence / sources

- `../design.md §5` (Checkpointer subsection — explicit deferral)
- `../design.md §7` (Open questions — Checkpointer backend)
- LangGraph docs — `InMemorySaver`, `PostgresSaver`, `SqliteSaver` reference implementations
