# Validation report: S4-02 — Embeddings cache.sqlite

**Validated:** 2026-05-22 05:15Z
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S4-02 adds `CachedEmbedder`, a BLAKE3(text)-keyed sqlite cache-aside decorator over S4-01's `Embedder` Protocol. The story's goal is sound and traces to phase arch §Component 8, ADR-0007 §Consequences, and edge case #13. The validator found 15 issues: 3 block-tier contradictions and 12 fixable harden/nit issues. All were patched in place, so this is HARDENED, not RESCUE.

The biggest fix is the sqlite key shape. The draft schema used `text_blake3 TEXT PRIMARY KEY`, but AC-5 required preserving an old-model row and inserting a new-model row for the same text under a different `model_digest`. The story now requires `PRIMARY KEY (text_blake3, model_digest)`. The other load-bearing fixes align vector serialization with S4-01's tuple-backed `EmbeddingVector` contract and replace the contradictory concurrency design with one lazy sqlite connection guarded by a process-local `threading.RLock`.

## Context brief

- **Goal:** ship `CachedEmbedder` at `src/codegenie/rag/embedding_cache.py`, keyed by `BLAKE3(text)` and `model_digest`, with lazy-open sqlite, cache hit/miss behavior, row/file corruption recovery, and batch support.
- **Phase constraints:** Phase 4 keeps LLM/RAG code under `src/codegenie/rag/`; no edits to `src/codegenie/{probes,coordinator,cache,output,schema}/`. ADR-0007 requires BLAKE3(input text) plus `model_digest()` column so model upgrades invalidate without hashing vectors.
- **Dependency lineage:** S4-01 hardened `EmbeddingVector` as a tuple-backed newtype and froze `Embedder` at `embed`, `embed_batch`, `model_digest`.
- **Open ambiguities:** none after synthesis.

## Findings by critic

### Coverage critic

**F1 (block) — Schema makes AC-5 impossible.** The draft had `text_blake3 TEXT PRIMARY KEY`, but AC-5 says an old `model_digest` row must remain while a new `model_digest` row for the same text is inserted. A sole text key cannot represent both rows. Fix: schema now uses `PRIMARY KEY (text_blake3, model_digest)`, and tests must prove duplicate text across models is allowed.

**F2 (harden) — Batch partial-hit and empty-input cases were underspecified.** The draft covered `["a", "b", "a"]` on a cold cache but not mixed hit/miss batches or `[]`. Fix: AC-6 now adds a partial-hit test and requires `embed_batch([]) == []` without opening the db.

**F3 (harden) — File-level corruption recovery missed connection cleanup.** Deleting a corrupt sqlite file while holding a stale connection can leave a broken handle. Fix: AC-7 now requires close/discard before unlink and retry.

**F4 (harden) — Row-level corruption behavior was self-contradictory.** The draft said a bad vector row "raises `EmbeddingsCacheCorrupted`" and also that public `embed()` returns freshly computed output. Fix: AC-8 makes the typed exception internal to `_decode_row`; `embed()` catches it, deletes only the composite-key row, logs, and returns fresh output.

### Test-Quality critic

**F5 (harden) — TDD spy returned the wrong public type.** The sample `_SpyEmbedder.embed` returned an `np.ndarray` inside `EmbeddingVector`, contradicting S4-01's tuple-backed contract. Fix: sample now returns `EmbeddingVector(tuple(float(x) for x in vec))`.

**F6 (harden) — TDD sample had unused imports.** `Any` and `pytest` were imported but unused; strict lint would fail the red test scaffold. Fix: removed both.

**F7 (harden) — Missing mutation-killer for composite schema.** Without a schema-level test, an executor could leave `text_blake3` as the sole key and still pass most behavior tests until AC-5. Fix: required `test_schema_uses_text_and_model_digest_composite_key`.

**F8 (harden) — Concurrency test risked asserting the wrong property.** A same-text concurrent miss may compute twice and still be correct. Fix: test guidance now forbids asserting `inner.embed_calls == 1`; it asserts db validity, one final row, equal results, and no locked-db escape.

**F9 (harden) — Property test needed a safe alphabet and a fake embedder.** Hypothesis can generate surrogate codepoints that fail UTF-8 encoding, and real fastembed would make the property slow/flaky. Fix: property plan uses `blacklist_categories=("Cs",)` and the spy embedder.

### Consistency critic

**F10 (block) — AC-8 contradicted S4-01's `EmbeddingVector` contract.** S4-01 hardened `EmbeddingVector = NewType("EmbeddingVector", tuple)`, but S4-02 read-back returned `EmbeddingVector(vec)` where `vec` was an ndarray. Fix: AC-8 now converts decoded `np.float32` bytes back to `tuple(float(...))` before wrapping.

**F11 (harden) — `pyproject.toml` touch row was stale.** The repo already has `blake3` in runtime dependencies and `hypothesis` in dev extras. Fix: Files-to-touch now says `pyproject.toml` should remain unchanged unless local verification proves drift.

**F12 (nit) — `busy_timeout` was absent from the sqlite PRAGMAs.** AC-10 relies on not leaking locked-db errors in a threaded test. Fix: AC-2 now includes `busy_timeout=5000`.

### Design-Patterns critic

**F13 (block) — Concurrency design contradicted itself.** The outline used a singleton `_conn`, while AC-10 said safety came from "per-call connection." That is neither a clear adapter boundary nor a testable concurrency contract. Fix: AC-10 and the outline now use a single lazy connection guarded by `threading.RLock`; duplicate miss work is explicitly out of scope.

**F14 (harden) — Composite key is an illegal-state fix, not just a SQL detail.** The cache state must distinguish same text across model versions. Fix: Notes §8 explains the invariant and AC-2 makes it representable in the schema.

**F15 (nit) — Pattern advice needed to preserve protocol composition.** The draft was already good on composition (`CachedEmbedder(inner)` instead of editing `Embedder`), but the tuple/newtype and concurrency details could invite overreach. Fix: added Notes §9 and §10 to keep numpy internal and avoid speculative single-flight machinery.

## Research briefs

No external research was needed. All findings resolved from in-repo docs, ADR-0007, S4-01's validation report, `CLAUDE.md`, and the local `pyproject.toml`.

## Conflict resolutions

- **Consistency over implementation convenience:** S4-01's tuple-backed `EmbeddingVector` contract wins over the S4-02 draft's ndarray-flavored examples. The cache may use numpy internally but must expose tuple-backed values.
- **Coverage and design jointly on key shape:** Coverage identified that AC-5 was impossible; Design-Patterns framed the fix as "make illegal states unrepresentable." Both resolve to the same composite key.

## Edits applied

1. Header status changed from `Ready` to `HARDENED`; validation notes inserted.
2. AC-2 schema changed from sole `text_blake3` primary key to composite `(text_blake3, model_digest)` and added `busy_timeout=5000`.
3. AC-5 now explicitly requires preserving old-model and new-model rows for the same text.
4. AC-6 now covers partial-hit batches and empty batches that do not open sqlite.
5. AC-7 now closes/discards stale handles before file rebuild and bans raw text in logs.
6. AC-8 now models row-level corruption as an internal typed exception and returns tuple-backed `EmbeddingVector` values.
7. AC-10 now states the `threading.RLock` concurrency contract and explicitly excludes single-flight.
8. Implementation outline updated for dependency no-op, schema constants, lock discipline, row/file corruption split, strict spy embedder, and property-test strategy.
9. TDD code sample fixed to remove unused imports and return tuple-backed vectors.
10. Required tests expanded for schema, partial-hit batch, empty batch, corrupt row, and concurrency.
11. Files-to-touch clarified that `pyproject.toml` should not change under current repo state.
12. Notes §8-§10 added for composite key, tuple-backed `EmbeddingVector`, and idempotent-not-single-flight concurrency.

## Verdict rationale

HARDENED. The story's scope and goal are valid; the blockers were localized contradictions in schema, type boundary, and concurrency wording. Those are now patched without changing the goal or adding adjacent work. The executor can implement the story with clear observable ACs and tests that should catch the likely wrong implementations.

## Recommended next step

Run `phase-story-executor` for S4-02. The executor should focus on the composite key, tuple-backed vector boundary, and row/file corruption split; those are the highest-risk parts of the implementation.
