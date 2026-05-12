# ADR-0005: `chromadb` PersistentClient in-process with single-writer flock + stale-lock detection

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** vector-store · concurrency · phase-9-handoff · synthesizer-departure
**Related:** [ADR-0002](0002-two-tier-writeback-pending-promoted.md), [ADR-0006](0006-bge-small-en-embedding-model-sha-pinned.md)

## Context

Phase 4 needs a vector store. The corpus starts empty and grows monotonically; Phase 4 ships expecting ≤ 1k examples for the first 6 months, scaling to ~5k before a swap becomes worthwhile. All three lens designs reached the same first answer (`chromadb` embedded) and disagreed on isolation: in-process (performance, best-practices) or in a read-only subprocess (security). The architect picked in-process and the critic (`critique.md §performance hidden assumption #3`) attacked it on GIL-contention grounds for the 8-parallel-worker profile.

`phase-arch-design.md §"Gap analysis" §"Gap 3"` raises a separate, sharper problem: `flock` is advisory on Linux but the lock file's inode survives a SIGKILL'd writer holding it; the writer's SQLite WAL is mid-write; every subsequent reader on the same host blocks indefinitely. The synthesis treated this as fully handled by single-writer discipline; the gap analysis says it isn't.

## Options considered

- **`qdrant` local Docker.** Production-grade vector store. Adds a Docker dep to Phase 4 (currently zero external services). Defers the GIL contention question by network-isolating queries. Picked as the documented Phase 9+ swap target ([ADR-0003](#) referenced in `final-design.md §"Roadmap coherence check"` ADR-P4-003).
- **`pgvector` on Postgres.** Better for portfolio-scale querying. Heavier dep; Phase 4's single-host single-process posture doesn't need it.
- **`chromadb` PersistentClient in-process under exclusive `flock`.** Synthesis pick. Zero external services. GIL contention bounded by single-writer + read-mostly workload + ≤ 5k examples.
- **`chromadb` in a read-only subprocess.** Security-lens position. Adds ~30ms per query (subprocess UDS). Mitigates GIL contention at the cost of process management.

## Decision

Use `chromadb.PersistentClient(is_persistent=True, allow_reset=False)` in the orchestrator process with telemetry disabled at import time. Two collections: `vuln_solved_examples_promoted` and `vuln_solved_examples_pending`. Bodies live as canonical JSON at `.codegenie/rag/bodies/<id>.json`; chromadb stores `(id, embedding, small metadata)` only.

Concurrency: `SolvedExampleStore.read()` acquires a shared `flock` on `.codegenie/rag/.lock`; `write()` acquires exclusive. **Stale-lock detection:** `write()` writes its `(pid, hostname, timestamp)` to `.codegenie/rag/.lock.holder` atomically; a reader that's been waiting > 60s checks if the holder PID is alive (`os.kill(pid, 0)`) and breaks the lock if not. The dead-worker case is self-healing within a minute; Phase 9's Temporal Activity wrapping makes it moot.

The swap path to `qdrant` for portfolio scale (~5k+ examples) is documented; the engine and writer code don't import `chromadb` directly outside `src/codegenie/rag/store.py`.

## Tradeoffs

| Gain | Cost |
|---|---|
| Zero external services in Phase 4 — no Docker, no Postgres, no Redis | Scales to ~5k examples before HNSW perf cliff; swap path is documented but unproven |
| `chromadb` queries are p50 ≤ 12ms, p95 ≤ 30ms on 100 examples — well under the selector-chain 250ms budget | GIL contention at 8 concurrent workers is real; mitigated by single-writer + read-mostly workload, not eliminated |
| Single-writer discipline + atomic `os.replace` on body JSON + content-addressed `example_id` means race-on-same-id is idempotent, not corrupting | A SIGKILL'd writer holding the exclusive lock blocks every other worker until stale-lock detection kicks in (60s) |
| Stale-lock detection is local-POC-grade ergonomics; Phase 9's Temporal Activity heartbeating makes it production-grade without code change | Adds `~60s` worst-case latency on the rare worker-crash-mid-writeback path; surfaced as known concession |
| `chromadb` encapsulated in `src/codegenie/rag/store.py` — fence-CI forbids `import chromadb` elsewhere; swap to qdrant is one file's worth of work | Telemetry must be disabled at import time, not at first use (env var or monkey-patch); easy to forget |
| Two collections (pending/promoted) reuse the same store machinery — split is a schema concern, not a deployment concern | Cross-collection queries require two `query()` calls; trivial cost |

## Consequences

- `SolvedExampleStore` is the only module importing `chromadb`. Fence-CI test (`tests/fence/test_fence_phase4.py`) enforces.
- SQLite-backed chromadb uses WAL mode. Corruption (SQLite checksum failure) is detected by `opens_cleanly()` at startup; the orchestrator quarantines `<dir>.corrupt-<ts>`, rebuilds empty, forces `--no-rag` for the run with a loud warning.
- `.codegenie/rag/solved-examples/` holds `chroma.sqlite3` + parquet shards. ~25 MB at 100 examples; ~250 MB at 1k.
- The stale-lock detector is process-aware on Linux (`os.kill(pid, 0)` returns 0 if alive, raises `OSError` if dead); macOS works the same. Two-host scenarios (Phase 9+) need a different mechanism (Temporal heartbeats handle it).
- `test_store_breaks_stale_lock_after_60s.py` uses a process-kill fixture to verify the recovery path. Without this test, the gap-fix is just a comment.
- Phase 9's Temporal Activity wraps `writeback_solved_example`; Activities are heartbeated and Temporal handles the dead-worker case structurally. The flock + stale-detector is the local-POC compromise.

## Reversibility

**Medium.** Swapping to `qdrant` is a single-file refactor (`store.py`); the rest of Phase 4 sees `SolvedExampleStore`'s typed Protocol. The swap *trigger* is observable (HNSW p95 latency creeping above 50ms on warm queries), so the decision rolls forward, not back. Reverting the *stale-lock detector* alone would mean accepting the deadlock risk; reverting *in-process* to subprocess-isolated would require a wire format and ~30ms/query latency hit.

## Evidence / sources

- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row "Vector store"
- `../final-design.md §"Components"` #7 — `SolvedExampleStore` design
- `../phase-arch-design.md §"Component design"` #4 — `SolvedExampleStore`
- `../phase-arch-design.md §"Gap analysis" §"Gap 3"` — stale-lock detection requirement
- `../critique.md §performance hidden assumption #3` — GIL contention at 8 workers
- `../critique.md §best-practices §security "Things this design missed"` — chromadb supply-chain isolation
