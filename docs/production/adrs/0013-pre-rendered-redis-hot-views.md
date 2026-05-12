# ADR-0013: Pre-rendered Redis hot views for agent context

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** latency · ergonomics
**Related:** ADR-0005, ADR-0006

## Context

The Planning agent (Stage 3) reads from the `RepoContext` artifact via MCP many times during one planning pass. Some slices are hit very frequently — `available_skills`, `entrypoint`, `risk_flags`, `confidence_summary` — and serving them via the full MCP-over-Postgres-over-object-store path costs roundtrips that pile up.

If every MCP call is 50ms and the planning pass makes 20 calls, that's a full second of planning latency lost to context retrieval. At portfolio scale across thousands of workflows per day, this latency compounds into real cost and reviewer-attention waste.

## Options considered

- **No pre-rendering — every MCP call hits the full stack.** Simple, slow. Acceptable for v0.1 if cold-start dominates anyway.
- **Pre-render everything.** Render every `RepoContext` slice into Redis. Maximum hit rate, maximum cache invalidation surface area, maximum memory cost.
- **Pre-render only the high-traffic slices.** Render the slices the agent provably hits frequently, leave the rest in cold storage. Best of both — fast for hot paths, simple for cold paths.

## Decision

**Pre-render a small set of high-traffic `RepoContext` slices into Redis** after every successful gather, keyed by repo:

- `available_skills` (the manifest of Skills that apply to this repo)
- `entrypoint` (current Dockerfile entrypoint shape)
- `risk_flags` (custom certs, native modules, blocking shell usage, etc.)
- `confidence_summary` (probe confidence levels and `IndexHealthProbe` output)

These are the slices the agent consults during the recipe-match and RAG-retrieval steps of Stage 3 (ADR-0011). Pre-rendered, single-digit-millisecond Redis reads replace tens-of-millisecond MCP-over-Postgres reads.

Other slices (raw probe outputs, full Dockerfile parse trees, runtime traces) are read from cold storage only when needed.

## Tradeoffs

| Gain | Cost |
|---|---|
| Single-digit-ms latency on the slices the agent actually hits frequently | One more cache to invalidate; staleness bugs surface as wrong planning context |
| Lower MCP server load — most calls answered from Redis | Redis cluster to operate (mitigated: Redis is operationally simple compared to Postgres) |
| Continuous gather + pre-render gives "always-fresh in single-digit ms" property | Memory cost ∝ (watched repos × pre-rendered slice sizes); bounded but real |
| Pre-rendered shape can evolve independently of the source `RepoContext` schema | Schema-evolution drift between Redis views and the underlying artifact must be policed |

## Consequences

- The pre-render task fires as the **final step of every gather** (ADR-0006). It is part of the gather pipeline, not a separate cron — no time window where the gather is fresh but the views are stale.
- Pre-rendered views are versioned: when the slice shape changes, the version bumps and stale entries are evicted on read.
- TTL is *not* set — invalidation is gather-driven, not time-driven. Every gather either updates or evicts.
- The MCP "Context" server (per `../design.md §8.4` Physical view) reads Redis first, falls through to Postgres + object store on miss.
- The list of pre-rendered slices is intentionally **short and curated**. Adding a new slice to the pre-render list requires a deliberate ADR amendment — easy to add, easier to keep small.

## Reversibility

**Low cost.** The Redis layer is an optimization on top of the MCP/Postgres baseline. Turning off pre-rendering reverts to slower-but-correct behavior. Adding more pre-rendered slices is additive.

## Evidence / sources

- `../design.md §3.2` (continuous gather — pre-rendered agent views subsection)
- `../../context.md §"Caching, freshness, and incremental gathers"` — pre-rendered "agent views" in Redis for hot paths
- `../design.md §8.1`, `§8.4` — MCP servers and Redis in the logical and physical views
