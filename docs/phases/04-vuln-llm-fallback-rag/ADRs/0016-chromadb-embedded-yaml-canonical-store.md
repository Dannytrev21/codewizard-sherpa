# ADR-0016: chromadb PersistentClient embedded mode; YAML records as canonical source; sqlite derived

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** ports-and-adapters · content-addressed-storage · single-writer · operational-recovery
**Related:** ADR-0007 (this phase) · [production ADR-0017](../../../production/adrs/0017-knowledge-graph-backend.md)

## Context

Phase 4 needs a local vector store for solved examples. All three design lenses agreed on `chromadb` (performance for cold-start, security for embedded-mode-no-network-listener, best-practices for no-docker-compose contributor friction). The disagreement was around schema durability, write concurrency, and operational recovery.

The critic surfaced three load-bearing concerns (`critique.md §"Where do all three quietly agree"` + `[P] §5`):

1. **chromadb schema migrations are not stable** — a chromadb upgrade can require a rebuild that loses examples.
2. **Single-writer limit** — chromadb's HNSW writer is single-threaded; 24-worker portfolio scans + per-workflow ingest = lock contention or silent dropped writes.
3. **chromadb sqlite is not git-attributable** — binary blobs don't diff; fixture portability claims are broken.

[Production ADR-0017](../../../production/adrs/0017-knowledge-graph-backend.md) defers the knowledge-graph-backend choice (qdrant / pgvector / Neo4j) for the production service. Phase 4 (local POC) doesn't need to anticipate the resolution; it needs to ship a Protocol that pgvector can slot behind in Phase 11.

The honest framing: chromadb is a *derived* store; canonical truth lives in human-reviewable YAML records that can rebuild chromadb at any time. The single-writer constraint is declared in the Protocol docstring + enforced by `asyncio.Lock`; Phase 11's pgvector adapter swap is the resolution at portfolio scale.

## Options considered

- **chromadb sqlite as canonical store, no YAML mirror** (default approach). Single source; chromadb owns durability. **Pattern:** Single-store. Loses git-attributability; chromadb schema migrations are migration cliffs.
- **YAML records as canonical, chromadb derived** (synthesis). `.codegenie/rag/records/<id>.yaml` is the canonical artifact (git-attributable, human-reviewable, diffable); chromadb sqlite is derived (rebuildable via `codegenie rag rebuild`). **Pattern:** Source-of-truth split — canonical + derived index.
- **qdrant** (security lens rejected, best-practices rejected). HTTP listener surface; docker-compose contributor friction. **Pattern:** External vector store. Rejected for Phase 4; resolution defers to Phase 11 + [ADR-0017](../../../production/adrs/0017-knowledge-graph-backend.md).
- **pgvector embedded** (Phase 11 candidate). Postgres + pgvector extension; multi-writer; mature schema migrations. **Pattern:** Relational + vector. Out of scope for Phase 4 (local POC); Phase 11's adapter swap behind the same `SolvedExampleStore` Protocol.

## Decision

`SolvedExampleStore` Protocol with one in-tree adapter: `ChromaPersistentStore` wrapping `chromadb.PersistentClient` in embedded mode against `.codegenie/rag/chroma/`. **Canonical source:** YAML files at `.codegenie/rag/records/<id>.yaml` (one example per file; human-reviewable; git-attributable). **Derived index:** chromadb sqlite + parquet; rebuildable via `codegenie rag rebuild` from canonical YAML — *without re-embedding* (records carry their embedding model digest + vector). **Single-writer:** declared in the Protocol docstring + enforced by process-local `asyncio.Lock` around `add()`. **Per-`(task_class, language, build_system)` collection:** smaller HNSW indexes; O(1) filter selection at query time.

**Pattern:** Ports and Adapters (one Protocol, one adapter today; pgvector adapter via [ADR-0017](../../../production/adrs/0017-knowledge-graph-backend.md) in Phase 11) + Source-of-truth split (canonical YAML + derived sqlite).

## Tradeoffs

| Gain | Cost |
|---|---|
| YAML records survive chromadb schema upgrades — rebuild without re-embedding; corruption recovery is "delete chroma/, run rebuild" | Two storage shapes to maintain (YAML + sqlite); ingestion writes both atomically (transactional discipline in `SolvedExampleStore.add`) |
| Git-attributable canonical store — every solved example is a commit; provenance includes the committing PR | Repository size grows linearly with corpus (~6.5 KB per example); 100 PRs/day → ~240 MB/year — acknowledged storage cost |
| Per-`(task_class, language, build_system)` collection means smaller HNSW indexes; query latency stays bounded as corpus grows | Cross-task-class queries (rare in Phase 4) require union over collections; not Phase 4's case |
| Single-writer constraint is *declared* in Protocol + *enforced* by `asyncio.Lock` — the limit is visible, not a hidden race | Concurrent workflows in a single process serialize on `add()`; at portfolio scale (24 workers, Phase 13), this is the trigger to swap to pgvector via Phase 11 — documented |
| The `SolvedExampleStore` Protocol is the seam for Phase 11's pgvector swap — one adapter, no consumer change | Phase 11's swap touches one file (`src/codegenie/rag/store.py` adapter selection); but corpus migration is real work |
| `codegenie rag rebuild` is the operational-recovery command — a load-bearing UX commitment | Operators must know it exists and when to run it (docs/operations/rag.md) |

## Pattern fit

**Ports and Adapters** with intentional single-adapter-today scope: `SolvedExampleStore` is the port; `ChromaPersistentStore` is the only adapter Phase 4 ships. [ADR-0017](../../../production/adrs/0017-knowledge-graph-backend.md) commits the project to a second adapter (pgvector / qdrant / etc.) — meaning the Protocol earns its keep at the architectural level even if today it has one impl.

The **Source-of-truth split** pattern (canonical YAML + derived sqlite) is a textbook content-addressed-storage shape. The toolkit names "Cache-aside + Content-addressed cache (BLAKE3 key)" for the embedding cache (ADR-0007 / final-design §10) — this is the same idea one level up: the canonical store is content-addressed YAML; the chromadb sqlite is a derived index keyed off the canonical records.

## Consequences

- `.codegenie/rag/records/<id>.yaml` — canonical `SolvedExample` (human-reviewable; git-attributable per PR).
- `.codegenie/rag/chroma/` — derived sqlite + parquet; rebuildable.
- `.codegenie/rag/manifest.yaml` — `{records: [...], chain_head: ChainHead}`; BLAKE3-rolled head over records list.
- `codegenie rag rebuild` is the operational-recovery command; reads YAML, re-inserts into chromadb without re-embedding (records carry embedding model digest + vector).
- `SolvedExampleStore.add()` is single-writer (asyncio-lock-guarded inside the adapter); concurrent ingest serializes.
- `SolvedExampleStore.add(example, capability)` requires the `SolvedExampleWriteCapability` (per [ADR-0009](0009-inline-auto-harvest-confidence-gate.md)); read paths (`query`) require no capability.
- Per-collection partition key: `(task_class, language, build_system)`; query routes to the matching collection in O(1).
- Phase 11's merge-webhook ingest path is a *second* writer; with single-writer chromadb, two workflows ingesting near-simultaneously serialize on the lock; portfolio-scale resolution is the pgvector swap behind the same Protocol.
- Storage budget: ~6.5 KB per example (~5 KB YAML + ~1.5 KB derived vector); 100 PRs/day → ~240 MB/year — acknowledged in design.
- `tests/unit/rag/test_store.py` covers open/add/query round-trip; `tests/integration/test_phase4_rag_rebuild_idempotent.py` asserts `rebuild` is byte-identical to fresh ingest.

## Reversibility

**Medium.** Swapping chromadb to a different vector store behind the same `SolvedExampleStore` Protocol is the explicit Phase-11 move via [ADR-0017](../../../production/adrs/0017-knowledge-graph-backend.md) — designed-for path. Removing the YAML-canonical layer (going to chromadb-only) loses git-attributability and the schema-upgrade-resilience story; would require Phase-4 ADR amendment. Switching to qdrant or pgvector *in Phase 4* would add operational complexity (docker-compose, network listener) the contributor-friction argument explicitly rejected.

## Evidence / sources

- `../final-design.md §Component 7 — SolvedExampleStore + ChromaPersistentStore`
- `../final-design.md §Conflict-resolution table` row "Vector store"
- `../phase-arch-design.md §Component 7 — SolvedExampleStore`
- `../phase-arch-design.md §Failure modes` (chromadb sqlite corrupted → rebuild)
- `../critique.md §"[P] §5"` (single-writer + concurrent workers)
- `../critique.md §"Where do all three quietly agree"` (chromadb consensus without analysis)
- [production ADR-0017](../../../production/adrs/0017-knowledge-graph-backend.md) (deferred knowledge-graph-backend choice; Phase 11 resolution)
