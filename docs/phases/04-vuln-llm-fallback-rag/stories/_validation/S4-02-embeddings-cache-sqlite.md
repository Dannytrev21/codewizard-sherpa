# Validation report: S4-02 — Embeddings cache.sqlite

**Validated:** 2026-05-22 01:21 EDT
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S4-02 ships the `CachedEmbedder` decorator over S4-01's `Embedder` Protocol: BLAKE3(text)-keyed sqlite cache-aside with model-digest invalidation and rebuild-on-corruption. The goal traces cleanly to Phase-4 arch Component 8, High-level-impl Step 4, ADR-0007, final-design's cache-aside pattern, and edge case #13. The story was sound but had three executor-blocking defects: the schema contradicted model-digest invalidation, vector serialization contradicted S4-01's tuple-backed `EmbeddingVector`, and the concurrency outline mixed incompatible sqlite-connection strategies. All blockers were fixable in place, so the verdict is HARDENED.

## Findings by critic

### Coverage critic

**F1 (block) — AC-2 cannot satisfy AC-5.** AC-2 originally keyed the table by `text_blake3` alone, while AC-5 required preserving an old-model row and inserting a new-model row for the same input text. Proposed fix: make `(text_blake3, model_digest)` the composite primary key and assert duplicate same-text/different-model rows survive.

**F2 (harden) — lazy-open did not cover missing parent directories.** The story said the db is lazy-opened but did not require `.codegenie/rag/` creation. Proposed fix: AC-1 now pins lazy parent creation and tests no filesystem work occurs before the first non-empty call.

**F3 (harden) — file corruption cleanup missed WAL sidecars.** WAL mode creates `-wal`/`-shm`; deleting only the main db can leave stale sqlite sidecars behind. Proposed fix: AC-7 requires deleting the db plus sidecars before one retry.

**F4 (harden) — batch edge cases were underspecified.** `embed_batch([])` and all-cache-hit batches could still open sqlite or delegate. Proposed fix: AC-6 now pins empty-batch no-open behavior and all-hit no-delegation behavior through follow-on tests.

### Test-Quality critic

**F5 (harden) — batch dedupe order was weak.** AC-6 allowed either `["a", "b"]` or `["b", "a"]`, weakening deterministic behavior. Proposed fix: require first-seen order for missing texts.

**F6 (harden) — digest examples were semantically invalid.** The test spy used `BlobDigest("spy-digest-v1")`, even though `BlobDigest` is a 64-hex semantic type. Proposed fix: examples now use `BlobDigest("1" * 64)` and AC-5 uses `"0" * 64`/`"1" * 64`.

**F7 (harden) — row-corruption test could accept a leaking internal exception.** AC-8 said corruption raises `EmbeddingsCacheCorrupted` but `embed()` returns a fresh vector. Proposed fix: AC-8 now makes the exception internal: `_decode_row` raises it, public `embed()` catches, deletes exactly that row, logs, re-embeds, and returns.

**F8 (harden) — property test needed stronger mutation resistance.** The optional property test only checked bit-identical vectors. Proposed fix: it also asserts row count exactly one for the `(text_blake3, model_digest)` pair and spy call count remains one on the second call, killing always-miss and constant-key mutants.

### Consistency critic

**F9 (block) — AC-8 contradicted S4-01's hardened `EmbeddingVector` contract.** S4-01 fixes `EmbeddingVector = NewType("EmbeddingVector", tuple)` and prevents numpy from crossing the `Embedder` boundary. The S4-02 draft still described returning arrays from `np.frombuffer`. Proposed fix: serialize via `np.asarray(tuple(vector), dtype=np.float32)` internally and return `EmbeddingVector(tuple(float(x) for x in decoded))`.

**F10 (harden) — `pyproject.toml` was listed as a likely edit despite current deps already satisfying the story.** `blake3` is already in runtime dependencies and `hypothesis` is already in dev extras. Proposed fix: make dependency handling verify-only and remove `pyproject.toml` from Files to touch.

**F11 (nit) — logging shape needed the existing no-raw-text commitment.** Arch logging strategy forbids raw prompts/completions and this cache may handle advisory-derived query text. Proposed fix: AC-7 and Notes §5 explicitly prohibit logging raw embedded text.

### Design-Patterns critic

**F12 (block) — hidden mutable sqlite connection was not protected.** The implementation outline stored `_conn` on the wrapper while AC-10 claimed per-call connection safety. A shared connection across `asyncio.to_thread` calls without a lock would be an easy locked-db or corruption footgun. Proposed fix: keep the lazy connection but guard all sqlite operations with a process-local `threading.RLock`; explicitly state single-flight embedding is out of scope.

**F13 (harden) — composite key should make illegal states unrepresentable.** The model-digest invalidation invariant should live in the table constraint, not just in query discipline. Proposed fix: add Notes §8 and an AC-level schema test for the composite primary key.

**F14 (harden) — functional core needed named pure helpers.** Serialization, deserialization, and key derivation are pure logic and should be independently testable. Proposed fix: implementation outline names `_blake3_hex`, `_decode_vector_bytes`, and tuple-backed serialization helpers.

**F15 (nit) — concurrency target should not imply a single-flight service.** A per-key in-flight map is a separate feature with deadlock risk. Proposed fix: Notes §10 states idempotence is the target; duplicate same-text miss work is allowed.

## Research briefs

No `NEEDS RESEARCH` findings. All issues were resolved from in-repo sources: S4-01's validation report, Phase-4 arch Component 8 and edge case #13, ADR-0007 Consequences, `pyproject.toml`, and the repo's strict typing / extension-by-addition commitments in `CLAUDE.md`.

## Conflict resolutions

No critic conflict required external choice. The only design tradeoff was sqlite connection strategy: Design-Patterns flagged the unguarded shared connection, while Coverage only needed observable "no locked db error." The hardened story resolves this with a small `threading.RLock` and keeps single-flight out of scope per Rule 2.

## Edits applied

1. Header status changed from `Ready` to `HARDENED`; validation notes inserted.
2. AC-1 now requires lazy parent directory creation and no filesystem work at construction time.
3. AC-2 schema now uses `PRIMARY KEY (text_blake3, model_digest)` plus `busy_timeout=5000`.
4. AC-5 now uses valid `BlobDigest` examples and asserts old/new model rows coexist.
5. AC-6 now pins first-seen batch dedupe, empty-batch no-open, and all-hit no-delegation tests.
6. AC-7 now deletes WAL sidecars and forbids logging raw embedded text.
7. AC-8 now aligns with tuple-backed `EmbeddingVector` and makes row-corruption recovery internal.
8. AC-10 now pins a process-local sqlite lock and explicitly scopes out single-flight embedding.
9. Implementation outline updated for verify-only deps, composite schema, lazy parent creation, typed BLAKE3 helper, pure vector decode/encode, and row/file corruption split.
10. TDD sample fixed to return tuple-backed vectors with valid 64-hex digest.
11. Follow-on tests expanded for composite key, partial-hit batch, empty batch, row corruption, and same-text concurrency.
12. Files-to-touch narrowed; `pyproject.toml` removed as expected no-op.
13. Notes added for composite key, tuple-backed vectors, and idempotence-not-single-flight.

## Verdict rationale

HARDENED. The story's goal and phase fit are correct; no scope rewrite was needed. The blockers were real but local: a schema key contradiction, a type-boundary contradiction with S4-01, and an unsafe/contradictory concurrency prescription. The edited story now gives the executor observable ACs, mutation-resistant tests, and a small maintainable implementation shape.

## Recommended next step

Run `phase-story-executor` on S4-02.
