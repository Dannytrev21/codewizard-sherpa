# ADR-0017: Knowledge-graph backend (Qdrant / pgvector / Neo4j)

**Status:** Deferred
**Date:** 2026-05-11
**Tags:** platform · storage
**Related:** ADR-0011

## Context

The knowledge graph stores solved examples from Stage 7 Learning. ADR-0011 commits to retrieving them at Stage 3 Planning as few-shot context for the LLM. The store needs two access patterns:

1. **Similarity search by fingerprint** — "find prior migrations that resemble this `RepoContext` fingerprint." Vector-similarity search.
2. **Optional: graph traversal** — "find prior fixes that touched this file AND that dependency AND succeeded with this base image." Multi-hop relationships.

If only #1, a vector DB suffices. If #2 becomes important, graph traversal is awkward without a graph-native store.

## Options considered

- **Qdrant.** Vector-only. Excellent similarity-search ergonomics, fast, well-maintained. No graph traversal.
- **pgvector (Postgres extension).** Vector similarity inside Postgres. Operationally simpler — one DB engine. Slower vector-similarity than purpose-built stores, but adequate at moderate scale.
- **Neo4j.** Graph-native. Cypher queries make traversal natural. Vector similarity supported via plugins but secondary to the graph model.
- **Hybrid: pgvector + graph metadata in Postgres.** Use pgvector for similarity, model relationships as Postgres tables, do traversal in SQL. Works until the queries get hairy.

## Default until decided

**pgvector** for Phase 1.

Reasoning:
- Postgres already in the stack for Temporal (ADR-0003) and checkpointer (ADR-0016).
- One database engine reduces ops surface area.
- Vector similarity in pgvector is adequate at the volumes Phase 1 will see (thousands of solved examples).
- Graph-traversal queries can be modeled with recursive CTEs if needed.

Upgrade to Qdrant if similarity-search latency becomes a bottleneck. Upgrade to Neo4j if traversal queries become primary access pattern.

## Evidence needed to resolve

- **Query volume.** Vector-similarity queries per second at peak.
- **Query mix.** What fraction of queries are pure similarity vs. multi-hop traversal? If >20% are traversal, Neo4j becomes attractive.
- **Solved-example growth rate.** At org scale, how many new entries per week?
- **Latency tolerance.** Stage 3 RAG retrieval — is 100ms acceptable, or does it need to be 10ms?

## Reversibility (of the eventual choice)

**Medium cost.** Solved examples can be re-indexed in a new backend; the existing data isn't lost. But: if multi-hop traversal queries are written against Cypher and we move to pgvector, those queries become awkward SQL.

## Evidence / sources

- `../design.md §5` (Shared knowledge graph subsection — explicit deferral)
- `../design.md §7` (Open questions — Knowledge-graph backend)
- `../../auto-agent-design.md §2.1` — Konveyor Kai's MCP-backed solution server uses a vector DB
