# Story S4-02 — Embeddings cache.sqlite (BLAKE3(text)-keyed cache-aside; lazy-open; rebuild-on-corruption)

**Step:** Step 4 — Ship RAG substrate kernel: Embedder + SolvedExampleStore + record provenance
**Status:** Done — GREEN 2026-05-25 (phase-story-executor; see [`_attempts/S4-02.md`](_attempts/S4-02.md) for the per-AC evidence table + gate log — `CachedEmbedder` BLAKE3(text)-keyed SQLite cache-aside lands at `src/codegenie/rag/embedding_cache.py` (~360 lines: composite-key schema, lazy-open, two-tier corruption recovery, `threading.RLock`-guarded shared connection, tuple-backed `EmbeddingVector` boundary, `INSERT OR REPLACE` idempotence). `EmbeddingsCacheCorrupted` joins the typed errors at `src/codegenie/rag/errors.py` as a private row-corruption marker the public `embed()` path catches and never leaks. 19 unit tests + 1 Hypothesis property (100 examples) cover AC-1..AC-10; AC-11 lint/format/`mypy --strict` clean on touched. Story-scoped gates green: `make fence` 475 passed, `make typecheck` 230 files, `make lint-imports` 11 contracts kept / 0 broken (path-scoped fence under `codegenie.rag` unchanged — no LLM SDK admission needed). Full suite 6921 passed / 42 skipped / 9 xfailed (L-2 macOS `tsconfig_pathological` timing flake + L-4 `lint_imports_canary` PATH issue deselected per attempt-log convention; CI Linux clean). Three new lessons (L-S402-1 sqlite-corruption fixture shape, L-S402-2 structlog capture_logs vs caplog, L-S402-3 float32 round-trip equality) captured.)
**Effort:** S
**Depends on:** S4-01 (`Embedder` Protocol + `FastembedEmbedder` + `model_digest()`)
**ADRs honored:** ADR-0007 (cache keyed on BLAKE3 of input text + model_digest column; edge case #13 — corruption rebuild)

## Validation notes

Validated: 2026-05-22
Verdict: HARDENED
Findings addressed: 15 — 3 block, 10 harden, 2 nit

Changes applied:
- **AC-2 / AC-5 fixed (block)** — the original schema used `text_blake3 TEXT PRIMARY KEY` while AC-5 required preserving old and new `model_digest` rows for the same text; schema now uses `PRIMARY KEY (text_blake3, model_digest)`.
- **AC-8 fixed (block)** — aligned serialization with S4-01's hardened `EmbeddingVector = NewType("EmbeddingVector", tuple)` contract; numpy stays inside the cache adapter and read-back returns a tuple-backed `EmbeddingVector`.
- **AC-10 fixed (block)** — replaced the contradictory "unguarded singleton `_conn` + per-call connection" concurrency story with an explicit process-local lock over sqlite operations; duplicate miss computation is allowed, locked-database errors are not.
- Hardened row-level corruption recovery, sqlite file corruption rebuild, batch partial-hit tests, property-test strategy, strict typing details, and the `pyproject.toml` no-op expectation (`blake3` + `hypothesis` are already present).
- Tightened the TDD sample so it has no unused imports and the spy embedder returns tuple-backed `EmbeddingVector` values, not numpy arrays.
- Post-check refinements: valid 64-hex `BlobDigest` examples, first-seen batch miss order, lazy parent-dir creation, and sqlite WAL sidecar cleanup on corruption rebuild.

Full audit log: docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S4-02-embeddings-cache-sqlite.md

## Context

S4-01 ships the cache-miss embedding path. A naïve retrieval that re-embeds the same `Query.digest()` text on every retry burns ~80 ms / call uncached. The Phase-4 design pins **BLAKE3(input_text)-keyed sqlite cache-aside** at `.codegenie/rag/embeddings.cache.sqlite` (arch §Component 8 + ADR-0007 §Consequences), keyed by text (not by embedded vector — float drift would break the key) with the embedder's `model_digest()` carried as a column so an out-of-band model upgrade auto-invalidates cached vectors.

Edge case #13 names sqlite-corruption as a recoverable failure: lazy-open with rebuild-on-corruption — the next `embed()` call repopulates the cache from scratch; no workflow fails. This is the same posture Phase-2 uses for the input-snapshot cache.

This story decorates `FastembedEmbedder` with a cache-aside layer **without** changing the `Embedder` Protocol shape — `embed()` consults the cache, calls through to the underlying session on miss, writes the result back, returns. The cache is the load-bearing reason `Embedder.model_digest()` exists (S4-01 Notes §2); this story is where that contract earns its keep.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 8 — Embedder + FastembedEmbedder` — embedding cache at `.codegenie/rag/embeddings.cache.sqlite` keyed on BLAKE3 of input text.
  - `../phase-arch-design.md §Edge case #13` — `embeddings.cache.sqlite` corrupted → cache rebuilt on demand; no workflow failure; logged.
  - `../phase-arch-design.md §"On-disk shapes"` — `.codegenie/rag/embeddings.cache.sqlite` — BLAKE3(text) → vector (idempotent reuse).
- **Phase ADRs:**
  - `../ADRs/0007-fastembed-onnx-over-sentence-transformers.md` §Consequences — "cache keys on BLAKE3 of input text and includes the `model_digest()` as a column — model upgrades automatically invalidate cached vectors."
- **Source design:**
  - `../final-design.md §Component 8 — FastembedEmbedder` — content-addressed cache-aside framing.
  - `../final-design.md §"Cache-aside + Content-addressed cache (BLAKE3 key)"` — toolkit pattern name.
- **Existing code (precedent to mirror):**
  - `src/codegenie/cache/` — the Phase-0 content-addressed cache; lazy-open + corruption-handling idioms. Mirror its `pathlib.Path` + `sqlite3` discipline (no SQLAlchemy).
  - `src/codegenie/probes/layer_a/*.py` — `input_snapshot` lazy-open precedent.

## Goal

Ship a `CachedEmbedder` wrapper at `src/codegenie/rag/embedding_cache.py` that decorates any `Embedder` with a BLAKE3-keyed sqlite cache-aside layer; cache miss → delegate + write-back; cache hit → return without invoking the underlying embedder; corrupted sqlite → rebuild on next access; cache key = `BLAKE3(text)` and entries carry the embedder's `model_digest()` column for automatic invalidation.

## Acceptance criteria

- [ ] **AC-1 — `CachedEmbedder(inner: Embedder, db_path: Path)` shape.** Constructor takes an inner `Embedder` (any conforming impl, including `FastembedEmbedder`) and a db path; the db parent directory is created and the db is **lazy-opened** on first non-empty `embed`/`embed_batch` call, not on `__init__`. The wrapper itself conforms to the `Embedder` Protocol (`isinstance(CachedEmbedder(...), Embedder) is True`). A test constructs the wrapper with `db_path=tmp_path / "missing" / "embeddings.cache.sqlite"` and asserts the directory and db file do not exist until the first call.
- [ ] **AC-2 — Cache schema.** First lazy-open creates the schema if absent:
    ```sql
    CREATE TABLE IF NOT EXISTS embeddings (
        text_blake3 TEXT NOT NULL,       -- BLAKE3(text.encode("utf-8")) hex
        model_digest TEXT NOT NULL,       -- inner.model_digest()
        vector BLOB NOT NULL,             -- np.float32 384-dim bytes
        created_at TEXT NOT NULL,         -- ISO-8601 UTC; informational only
        PRIMARY KEY (text_blake3, model_digest)
    );
    CREATE INDEX IF NOT EXISTS idx_model ON embeddings(model_digest);
    ```
    The composite primary key is load-bearing: a model upgrade must preserve the old row and insert a new row for the same `text_blake3` under the new `model_digest` (AC-5). PRAGMA: `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000` (durability is fine for a cache; we re-embed on miss).
- [ ] **AC-3 — Cache hit avoids second embed.** Given `wrapper = CachedEmbedder(spy_embedder, db_path=tmp)`, `wrapper.embed("hello")` then `wrapper.embed("hello")`: `spy_embedder.embed` is called **exactly once**. Catches the "cache writes never happen" / "every call re-embeds" mutants.
- [ ] **AC-4 — Cache key is BLAKE3 of input text (not of vector).** Manually compute `blake3.blake3(b"hello").hexdigest()` and assert the row's `text_blake3` column matches verbatim. Catches the "use sha256" / "use truncated digest" mutants.
- [ ] **AC-5 — Model-digest mismatch on read = cache miss.** With the db pre-populated against `model_digest=BlobDigest("0" * 64)`, wrapping a new inner embedder whose `model_digest() == BlobDigest("1" * 64)`, `wrapper.embed(same_text)` calls the inner embedder (cache treated as miss); the row for `(text_blake3, model_digest=BlobDigest("0" * 64))` is left untouched (no cascading delete); a new row for `(text_blake3, model_digest=BlobDigest("1" * 64))` is inserted. The lookup is `SELECT vector FROM embeddings WHERE text_blake3=? AND model_digest=?` — both columns in the predicate, and a schema test asserts the composite primary key exists. (validator: hardened — original schema made this AC impossible with `text_blake3` as sole primary key; digest examples now use valid 64-hex `BlobDigest` values.)
- [ ] **AC-6 — `embed_batch` is cache-aware.** `wrapper.embed_batch(["a", "b", "a"])` calls `inner.embed_batch` with the **deduplicated, cache-missing** subset in first-seen order (`["a", "b"]`), then assembles the return list in input order. Returned vectors for index 0 and 2 are bit-identical (same row). A separate partial-hit test pre-populates `"a"`, calls `embed_batch(["a", "b", "a", "c"])`, and asserts the inner receives only `["b", "c"]` while all four outputs preserve input order. `embed_batch([])` returns `[]` and must not create or open the sqlite file.
- [ ] **AC-7 — Corruption rebuild on `sqlite3.DatabaseError`.** When lazy-open or the first schema/read probe raises `sqlite3.DatabaseError` (simulate via a corrupt 1-byte file), the wrapper:
    - Closes and discards any open connection handle.
    - Deletes the db file plus sqlite WAL sidecars (`embeddings.cache.sqlite-wal`, `embeddings.cache.sqlite-shm`) if present.
    - Re-creates the schema under the same lazy-open path.
    - Returns the embedded vector from the inner embedder (treating the corruption-recovery call as a cache miss).
    - Emits a structured log at WARN level: `cache_rebuilt_on_corruption` with `db_path` and `reason` fields, but never the raw embedded text. No workflow exception is raised unless the retry-open also raises `DatabaseError`.
- [ ] **AC-8 — Vector serialization is `np.float32` + length-checked while `EmbeddingVector` remains tuple-backed.** Stored bytes are exactly `np.asarray(tuple(vector), dtype=np.float32).tobytes()` where `vector` is S4-01's tuple-backed `EmbeddingVector`; numpy arrays never cross the public `Embedder` boundary. Read-back validates `len(bytes) == 4 * 384 = 1536` and `np.frombuffer(bytes, dtype=np.float32).shape == (384,)`, then returns `EmbeddingVector(tuple(float(x) for x in decoded))`. Mismatch on read is row-level corruption: `_decode_row` raises `EmbeddingsCacheCorrupted(text_blake3, model_digest, byte_len)`, `embed()` catches it, deletes only that composite-key row, logs `embedding_cache_row_corrupted`, re-embeds, writes the replacement, and returns the freshly computed vector. The typed exception must not escape the public `embed()` path.
- [ ] **AC-9 — `model_digest()` passthrough.** `wrapper.model_digest() == inner.model_digest()`. The wrapper does not invent a new digest; the cache key already disambiguates per-model.
- [ ] **AC-10 — Wrapper is concurrency-safe within a single asyncio loop.** Two `embed()` calls awaited under `asyncio.gather` (wrap with `asyncio.to_thread`) on the same `CachedEmbedder` instance do not corrupt the db; the post-run table contains one row per `(text_blake3, model_digest)` and both callers receive bit-identical vectors for the same text. No `sqlite3.OperationalError: database is locked` escapes. The implementation uses one lazy-opened sqlite connection guarded by a process-local `threading.RLock` around schema creation, lookup, row delete, insert, and commit. This story does **not** promise single-flight embedding: two concurrent cache misses may both call the inner embedder, but the writes are idempotent.
- [ ] **AC-11 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean on `src/codegenie/rag/embedding_cache.py` + tests.

## Implementation outline

1. **Dependency check is verify-only.** `blake3` is already in `[project.dependencies]` and `hypothesis` is already in `[project.optional-dependencies].dev` as of this validation run; do not edit `pyproject.toml` for this story unless the executor discovers local drift. If a missing runtime dependency is discovered anyway, surface per Rule 7 before adding it.
2. **Schema constants** in `src/codegenie/rag/embedding_cache.py`: `_SCHEMA: Final[str]` with the composite-key `CREATE TABLE IF NOT EXISTS embeddings ...`; `_VECTOR_DIM: Final[int] = 384`; `_VECTOR_BYTES: Final[int] = 4 * _VECTOR_DIM`; `_VECTOR_DTYPE: Final = np.dtype("float32")`.
3. **`CachedEmbedder`** class:
   - `__init__(self, inner: Embedder, db_path: Path) -> None`: stores both; `_conn: sqlite3.Connection | None = None` (lazy); `_lock = threading.RLock()` for single-process concurrency discipline.
   - `_lazy_open(self) -> sqlite3.Connection`: under `_lock`, if `_conn is None`, ensure `db_path.parent.mkdir(parents=True, exist_ok=True)`, open with `sqlite3.connect(db_path, check_same_thread=False)`, set `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`, execute schema. Wrap open/schema/probe in `sqlite3.DatabaseError` → close/discard any connection, delete `db_path` plus `db_path`'s `-wal`/`-shm` sidecars, log, and retry once; if retry fails, raise.
   - `_blake3_hex(text: str) -> BlobDigest`: pure helper returning unprefixed 64-hex BLAKE3 text digest.
   - `embed(self, text: str) -> EmbeddingVector`:
     - `key = self._blake3_hex(text)`; `digest = self.inner.model_digest()`.
     - Under `_lock`, run `SELECT vector FROM embeddings WHERE text_blake3=? AND model_digest=?`.
     - Hit: decode via `_decode_vector_bytes(key, digest, row[0]) -> EmbeddingVector`. If it raises `EmbeddingsCacheCorrupted`, delete only `(key, digest)`, log `embedding_cache_row_corrupted`, and fall through to miss.
     - Miss: call `self.inner.embed(text)` outside any sqlite write transaction if possible; then under `_lock`, `INSERT OR REPLACE INTO embeddings(text_blake3, model_digest, vector, created_at) VALUES (?, ?, ?, ?)` with `np.asarray(tuple(vec), dtype=np.float32).tobytes()`; `conn.commit()`; return the original tuple-backed `EmbeddingVector`.
   - `embed_batch(self, texts: list[str]) -> list[EmbeddingVector]`:
     - Compute keys, query cache hits in one `SELECT ... WHERE model_digest=? AND text_blake3 IN (...)`, decode valid rows, delete invalid rows, deduplicate only the missing texts, call `self.inner.embed_batch(missing_unique)`, insert replacements, then assemble output list in input order. Empty input returns `[]` and must not open the sqlite file.
   - `model_digest(self) -> BlobDigest`: delegate to `self.inner`.
4. **Corruption-recovery code paths**:
   - File-level sqlite corruption (`sqlite3.DatabaseError` while opening/probing schema) rebuilds the whole db file once, emits `cache_rebuilt_on_corruption`, and treats the call as a miss.
   - Row-level vector corruption (`EmbeddingsCacheCorrupted`) deletes only the composite-key row, emits `embedding_cache_row_corrupted`, and treats the call as a miss.
5. **Tests** under `tests/unit/rag/test_embedding_cache.py`:
   - Spy embedder: a `_SpyEmbedder` class implementing `Embedder` with a `calls` counter and deterministic tuple-backed vectors (e.g., `EmbeddingVector(tuple(float(x) for x in np.full(384, seed, dtype=np.float32)))`). Avoid `Any` in public test helpers; these tests run under `mypy --strict`.
   - AC-2 / AC-5 schema test (`PRAGMA table_info` + `PRAGMA index_list` / duplicate insert) proving the composite `(text_blake3, model_digest)` key.
   - AC-3 (cache hit avoids second embed), AC-4 (BLAKE3 key), AC-5 (model-digest mismatch is miss), AC-6 (batch dedup + partial-hit), AC-7 (file-level corruption rebuild), AC-8 (vector roundtrip + corrupt-row recovery), AC-9 (digest passthrough), AC-10 (concurrent gather).
6. **Property test** under `tests/property/test_embedding_cache_roundtrip.py` (optional but cheap):
   - Hypothesis: for any UTF-8-encodable text (`st.text(alphabet=st.characters(blacklist_categories=("Cs",)))`), `wrapper.embed(text)` → second call returns bit-identical tuples and does not increment the spy's embed-call count; the cache row count for that text/model pair is exactly 1. Use the spy embedder, not real `fastembed`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/unit/rag/test_embedding_cache.py`

```python
from __future__ import annotations

from pathlib import Path

import numpy as np

from codegenie.types.identifiers import BlobDigest, EmbeddingVector


class _SpyEmbedder:
    """Counts inner-call invocations to prove cache hits do not delegate."""

    def __init__(self) -> None:
        self.embed_calls = 0
        self._digest = BlobDigest("1" * 64)

    def embed(self, text: str) -> EmbeddingVector:
        self.embed_calls += 1
        # Deterministic vector per text — repeatable across calls
        seed = sum(text.encode("utf-8")) % 7
        vec = np.full(384, seed / 7.0, dtype=np.float32)
        return EmbeddingVector(tuple(float(x) for x in vec))

    def embed_batch(self, texts: list[str]) -> list[EmbeddingVector]:
        return [self.embed(t) for t in texts]

    def model_digest(self) -> BlobDigest:
        return self._digest


def test_cache_hit_avoids_second_inner_embed_call(tmp_path: Path) -> None:
    """AC-3 — ADR-0007 §Consequences: cache must short-circuit on hit.
    If this test fails, every retriever query re-embeds — Phase 4's p99 budget
    busted. Catches "always-miss" and "never-write" mutants."""
    from codegenie.rag.embedding_cache import CachedEmbedder

    spy = _SpyEmbedder()
    wrapper = CachedEmbedder(inner=spy, db_path=tmp_path / "embeddings.cache.sqlite")

    v1 = wrapper.embed("hello")
    v2 = wrapper.embed("hello")

    assert spy.embed_calls == 1, "cache must short-circuit second call"
    assert np.array_equal(np.asarray(v1), np.asarray(v2)), "cached vector must be bit-identical"
```

Why it fails: `codegenie.rag.embedding_cache` does not yet exist — `ImportError`.

### Green — make it pass

Land `src/codegenie/rag/embedding_cache.py` with the minimum: schema creation, `_blake3_hex`, the SELECT-then-INSERT-on-miss path. Skip batch optimization and corruption recovery for the red-pass; add them in the refactor pass.

### Refactor

- Extract `_lazy_open` + corruption recovery into a small helper.
- Add WAL pragma + `check_same_thread=False`.
- Implement batch dedup.
- Module docstring cites ADR-0007 §Consequences and names the cache invariant.

### Required follow-on tests

- `test_cache_key_is_blake3_of_input_text` (AC-4) — manual digest comparison.
- `test_schema_uses_text_and_model_digest_composite_key` (AC-2 / AC-5) — insert the same `text_blake3` under two `model_digest` values; both rows survive; a same-pair insert replaces only that pair.
- `test_model_digest_mismatch_treated_as_miss` (AC-5) — pre-populate row with old digest; new inner digest causes inner.embed call.
- `test_embed_batch_dedups_and_preserves_order` (AC-6) — input `["a", "b", "a"]`; inner.embed_batch receives exactly `["a", "b"]`; output[0] == output[2].
- `test_embed_batch_partial_hit_only_delegates_misses` (AC-6) — pre-populate `"a"`; `embed_batch(["a", "b", "a", "c"])` delegates only `"b"` and `"c"` and preserves all four output positions.
- `test_embed_batch_empty_returns_empty_without_opening_db` (AC-6) — `embed_batch([]) == []` and `db_path.exists()` is false after the call.
- `test_corruption_rebuilds_cache_silently` (AC-7) — write `b"\x00"` to db path before first call; first `embed()` succeeds and returns a fresh vector; db file is now valid; log captured at WARN.
- `test_corrupt_row_vector_bytes_recovered` (AC-8) — directly insert a row with `vector = b"short"`; calling `embed(same_text)` does not leak `EmbeddingsCacheCorrupted`, deletes only that row, re-embeds, and replaces it.
- `test_model_digest_passthrough` (AC-9).
- `test_concurrent_embed_calls_do_not_corrupt_db` (AC-10) — `asyncio.gather(asyncio.to_thread(wrapper.embed, "a"), asyncio.to_thread(wrapper.embed, "a"))`; assert no locked-db error escapes, both results are equal, and the table has exactly one row for `(BLAKE3("a"), digest)`. Do not assert `inner.embed_calls == 1`; single-flight is explicitly out of scope.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/embedding_cache.py` | `CachedEmbedder` wrapper + schema + lazy-open + corruption rebuild. |
| `src/codegenie/rag/errors.py` | Add `EmbeddingsCacheCorrupted` (extend existing module from S4-01). |
| `tests/unit/rag/test_embedding_cache.py` | Red test + AC follow-ons. |
| `tests/property/test_embedding_cache_roundtrip.py` | Hypothesis cache roundtrip (optional but cheap). |

`pyproject.toml` is expected to remain unchanged for this story: `blake3` is already a runtime dependency and `hypothesis` is already in the dev extras. Touch it only if local verification proves drift.

## Out of scope

- **Cache eviction / TTL** — the cache is content-addressed by text; eviction would require tracking access-time and adds policy that buys nothing for Phase 4. Disk growth is bounded by the corpus size; Phase 11 will reconsider when the corpus is portfolio-scale.
- **Cross-process safety** — single-writer assumption mirrors the chromadb store (S4-03). At portfolio scale (Phase 11), workers each have their own cache db; sharing across processes is not designed-for and not tested.
- **The chromadb store** — S4-03.
- **Async-native embed interface** — the cache stays sync; callers `asyncio.to_thread` if they need to yield.
- **Hot-reload of model swap** — the digest column auto-invalidates on swap; no flush API. Operators run `codegenie rag rebuild --reembed` (S4-07) when a model swap should re-populate.

## Notes for the implementer

### §1 — Why the cache key is text, not vector

ONNX float drift at the 5th decimal (ADR-0007 §Tradeoffs) means two embeds of the same text on different CPU architectures produce slightly different vectors. Hashing the **vector** as the cache key would silently mass-invalidate when a developer runs on arm64 and CI runs on x86_64. Hashing the **input text** is architecture-independent; the model digest column captures the embedder identity. Do not "improve" this by hashing the vector.

### §2 — Why `INSERT OR REPLACE` rather than `INSERT ... ON CONFLICT DO NOTHING`

In the AC-10 concurrent-gather case, two coroutines may both miss and both write the same row. `INSERT OR REPLACE` makes the second write idempotent (same bytes overwrite same bytes). `DO NOTHING` is fine too but `OR REPLACE` is simpler and matches the cache-aside semantics: "the freshest write wins; both produce identical bytes" — a no-op in practice.

### §3 — `np.frombuffer` returns read-only views

The internal view returned by `np.frombuffer(row_bytes, dtype=np.float32)` is read-only. Convert it immediately to `EmbeddingVector(tuple(float(x) for x in decoded))` before returning; do not leak the view or make callers reason about numpy mutability. Document this in the module docstring so a future contributor doesn't reintroduce an ndarray return.

### §4 — Vector dim 384 is BGE-small-specific

`_VECTOR_DIM = 384` is a `Final[int]` constant local to this module — it matches the BGE-small model S4-01 ships. A future Voyage adapter would have its own dim (1024); the cache schema is dim-agnostic (`BLOB` storage), but the **validator** that asserts `len(bytes) == 4 * 384` would need to be parameterized by `inner.embedding_dim` or similar. **Do not** add `embedding_dim` to the `Embedder` Protocol speculatively — when the second adapter lands, the Protocol can extend by addition. For now, the dim assertion is pinned to BGE-small explicitly.

### §5 — Logging shape

Use `structlog` (Phase 0 convention) — `log = structlog.get_logger(__name__)` at module top; `log.warning("cache_rebuilt_on_corruption", db_path=str(db_path))`. Never log the embedded text itself (PII / advisory content). The text's BLAKE3 hash is fine to log if needed for triage.

### §6 — Compose at call-site, not in the Protocol

`CachedEmbedder` is a decorator over `Embedder`; it does **not** modify the `Embedder` Protocol (which AC-9 of S4-01 froze at three methods). The composition `CachedEmbedder(FastembedEmbedder(...), db_path=...)` happens in the retriever wiring (S5-01) — not in `FastembedEmbedder.__init__`. This keeps each layer responsible for one thing: bootstrap-discipline vs. cache-aside.

### §7 — Don't add a `clear()` method

Tempting to add `def clear(self) -> None: self._conn.execute("DELETE FROM embeddings")`. **Don't.** The model-digest column already isolates upgrade scenarios; the operational recovery is "delete the file, the cache lazy-rebuilds on next access." If a future story needs cache clear, an ADR amendment is the bar — surface per Rule 7.

### §8 — Composite key is not optional

`text_blake3` alone is not a valid primary key because ADR-0007's invalidation contract keeps old-model rows cold while inserting new-model rows for the same input text. The cache lookup is `(text_blake3, model_digest)`, the write key is `(text_blake3, model_digest)`, and row-level corruption deletes exactly that pair. A table-level `PRIMARY KEY (text_blake3, model_digest)` is the simplest way to make the invariant representable.

### §9 — `EmbeddingVector` is tuple-backed

S4-01 hardened `EmbeddingVector` to a tuple-backed newtype so numpy never leaks through the `Embedder` Protocol. `embedding_cache.py` may use numpy internally to serialize/deserialize `float32` bytes, but its public inputs and outputs stay `EmbeddingVector(tuple(...))`. Avoid tests that assert `isinstance(vector, np.ndarray)`; that would regress the S4-01 contract.

### §10 — Concurrency target is idempotence, not single-flight

The cache wrapper is a lightweight sqlite cache-aside decorator, not an in-process single-flight service. Concurrent same-text misses may both call `inner.embed`; AC-10 only requires the sqlite file to remain valid, the final row to be correct, and no locked-db exception to escape. If a later benchmark proves duplicate same-text miss work matters, add a per-key in-flight map in a separate story with its own deadlock tests.
