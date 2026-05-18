# Story S4-02 — Embeddings cache.sqlite (BLAKE3(text)-keyed cache-aside; lazy-open; rebuild-on-corruption)

**Step:** Step 4 — Ship RAG substrate kernel: Embedder + SolvedExampleStore + record provenance
**Status:** Ready
**Effort:** S
**Depends on:** S4-01 (`Embedder` Protocol + `FastembedEmbedder` + `model_digest()`)
**ADRs honored:** ADR-0007 (cache keyed on BLAKE3 of input text + model_digest column; edge case #13 — corruption rebuild)

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

- [ ] **AC-1 — `CachedEmbedder(inner: Embedder, db_path: Path)` shape.** Constructor takes an inner `Embedder` (any conforming impl, including `FastembedEmbedder`) and a db path; the db is **lazy-opened** on first `embed`/`embed_batch` call, not on `__init__`. The wrapper itself conforms to the `Embedder` Protocol (`isinstance(CachedEmbedder(...), Embedder) is True`).
- [ ] **AC-2 — Cache schema.** First lazy-open creates the schema if absent:
    ```sql
    CREATE TABLE IF NOT EXISTS embeddings (
        text_blake3 TEXT PRIMARY KEY,    -- BLAKE3(text.encode("utf-8")) hex
        model_digest TEXT NOT NULL,       -- inner.model_digest()
        vector BLOB NOT NULL,             -- np.float32 384-dim bytes
        created_at TEXT NOT NULL          -- ISO-8601 UTC; informational only
    );
    CREATE INDEX IF NOT EXISTS idx_model ON embeddings(model_digest);
    ```
    PRAGMA: `journal_mode=WAL`, `synchronous=NORMAL` (durability is fine for a cache; we re-embed on miss).
- [ ] **AC-3 — Cache hit avoids second embed.** Given `wrapper = CachedEmbedder(spy_embedder, db_path=tmp)`, `wrapper.embed("hello")` then `wrapper.embed("hello")`: `spy_embedder.embed` is called **exactly once**. Catches the "cache writes never happen" / "every call re-embeds" mutants.
- [ ] **AC-4 — Cache key is BLAKE3 of input text (not of vector).** Manually compute `blake3.blake3(b"hello").hexdigest()` and assert the row's `text_blake3` column matches verbatim. Catches the "use sha256" / "use truncated digest" mutants.
- [ ] **AC-5 — Model-digest mismatch on read = cache miss.** With the db pre-populated against `model_digest="old-digest"`, wrapping a new inner embedder whose `model_digest() == "new-digest"`, `wrapper.embed(same_text)` calls the inner embedder (cache treated as miss); the row for `(text_blake3, model_digest="old-digest")` is left untouched (no cascading delete); a new row for `model_digest="new-digest"` is inserted. The lookup is `SELECT vector FROM embeddings WHERE text_blake3=? AND model_digest=?` — both columns in the predicate.
- [ ] **AC-6 — `embed_batch` is cache-aware.** `wrapper.embed_batch(["a", "b", "a"])` calls `inner.embed_batch` with the **deduplicated, cache-missing** subset `["a", "b"]` (or `["b", "a"]` — order-irrelevant; deterministic dedup is preferred), then assembles the return list in input order. Returned vectors for index 0 and 2 are bit-identical (same row).
- [ ] **AC-7 — Corruption rebuild on `sqlite3.DatabaseError`.** When `sqlite3.connect(db_path).execute("SELECT 1 FROM embeddings LIMIT 1")` raises `DatabaseError` (simulate via a corrupt 1-byte file), the wrapper:
    - Deletes the db file.
    - Re-creates the schema.
    - Returns the embedded vector from the inner embedder (treating the corruption-recovery call as a cache miss).
    - Emits a structured log at WARN level: `cache_rebuilt_on_corruption` with `db_path` field. No workflow exception is raised.
- [ ] **AC-8 — Vector serialization is `np.float32` + length-checked.** Stored bytes are exactly `vector.astype(np.float32).tobytes()`; read-back validates `len(bytes) == 4 * 384 = 1536` and `np.frombuffer(bytes, dtype=np.float32).shape == (384,)`. Mismatch on read raises `EmbeddingsCacheCorrupted(row_id)` and the row is deleted + re-embedded; the surrounding `embed()` returns the freshly computed vector.
- [ ] **AC-9 — `model_digest()` passthrough.** `wrapper.model_digest() == inner.model_digest()`. The wrapper does not invent a new digest; the cache key already disambiguates per-model.
- [ ] **AC-10 — Wrapper is concurrency-safe within a single asyncio loop.** Two `embed()` calls awaited under `asyncio.gather` (wrap with `asyncio.to_thread`) on the same `CachedEmbedder` instance do not corrupt the db; the second cache write either no-ops (if the first won) or overwrites with the bit-identical bytes (idempotent). No `sqlite3.OperationalError: database is locked` escapes — WAL mode + `connect(check_same_thread=False)` + per-call connection covers it.
- [ ] **AC-11 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean on `src/codegenie/rag/embedding_cache.py` + tests.

## Implementation outline

1. **Add `blake3` to runtime deps** if not already present (Phase 0/2 may have added it; check `pyproject.toml` first — Rule 8). If absent, this is the ADR-amendment trigger; surface per Rule 7 before adding. (Likely already there for content-addressed cache keys in `src/codegenie/cache/keys.py`.)
2. **Schema constants** in `src/codegenie/rag/embedding_cache.py`: `_SCHEMA: Final[str]` with `CREATE TABLE IF NOT EXISTS embeddings ...`; `_VECTOR_DIM: Final[int] = 384`; `_VECTOR_DTYPE: Final[type] = np.float32`.
3. **`CachedEmbedder`** class:
   - `__init__(self, inner: Embedder, db_path: Path) -> None`: stores both; `_conn: sqlite3.Connection | None = None` (lazy).
   - `_lazy_open(self) -> sqlite3.Connection`: if `_conn is None`, open with `sqlite3.connect(db_path, check_same_thread=False)`, set pragmas, execute schema. Wrap in try/except `sqlite3.DatabaseError` → `db_path.unlink(missing_ok=True)` + retry once; if retry fails, raise.
   - `_blake3_hex(text: str) -> str`: pure helper.
   - `embed(self, text: str) -> EmbeddingVector`:
     - `key = self._blake3_hex(text)`; `digest = self.inner.model_digest()`.
     - `row = conn.execute("SELECT vector FROM embeddings WHERE text_blake3=? AND model_digest=?", (key, digest)).fetchone()`.
     - Hit: `vec = np.frombuffer(row[0], dtype=np.float32)`; validate shape; return `EmbeddingVector(vec)`.
     - Miss: `vec = self.inner.embed(text)`; `conn.execute("INSERT OR REPLACE INTO embeddings VALUES (?, ?, ?, ?)", (key, digest, np.asarray(vec, dtype=np.float32).tobytes(), datetime.now(timezone.utc).isoformat()))`; `conn.commit()`; return.
   - `embed_batch(self, texts: list[str]) -> list[EmbeddingVector]`:
     - Compute keys, query missing-set in one `SELECT … WHERE text_blake3 IN (...) AND model_digest=?`, deduplicate `missing_unique`, call `self.inner.embed_batch(missing_unique)`, insert results, then assemble output list in input order.
   - `model_digest(self) -> BlobDigest`: delegate to `self.inner`.
4. **Corruption-recovery code path** (AC-7): isolated in `_lazy_open` so any malformed-db state on first read triggers rebuild; subsequent reads succeed from the now-empty schema.
5. **Tests** under `tests/unit/rag/test_embedding_cache.py`:
   - Spy embedder: a `_SpyEmbedder` class implementing `Embedder` with a `calls` counter; deterministic vectors (e.g., `np.arange(384, dtype=np.float32) / 384` for text "a"; permutation for "b").
   - AC-3 (cache hit avoids second embed), AC-4 (BLAKE3 key), AC-5 (model-digest mismatch is miss), AC-6 (batch dedup), AC-7 (corruption rebuild), AC-8 (vector roundtrip + corrupt-row recovery), AC-9 (digest passthrough), AC-10 (concurrent gather).
6. **Property test** under `tests/property/test_embedding_cache_roundtrip.py` (optional but cheap):
   - Hypothesis: for any UTF-8 text (excluding control chars to keep sqlite param-binding simple), `wrapper.embed(text)` → second call returns bit-identical bytes via `wrapper.embed(text)`; cache row count grows by exactly 1.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/unit/rag/test_embedding_cache.py`

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from codegenie.types.identifiers import BlobDigest, EmbeddingVector


class _SpyEmbedder:
    """Counts inner-call invocations to prove cache hits do not delegate."""

    def __init__(self) -> None:
        self.embed_calls = 0
        self._digest = BlobDigest("spy-digest-v1")

    def embed(self, text: str) -> EmbeddingVector:
        self.embed_calls += 1
        # Deterministic vector per text — repeatable across calls
        seed = sum(text.encode("utf-8")) % 7
        vec = np.full(384, seed / 7.0, dtype=np.float32)
        return EmbeddingVector(vec)

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
- `test_model_digest_mismatch_treated_as_miss` (AC-5) — pre-populate row with old digest; new inner digest causes inner.embed call.
- `test_embed_batch_dedups_and_preserves_order` (AC-6) — input `["a", "b", "a"]`; inner.embed_batch receives at most 2 elements; output[0] == output[2].
- `test_corruption_rebuilds_cache_silently` (AC-7) — write `b"\x00"` to db path before first call; first `embed()` succeeds and returns a fresh vector; db file is now valid; log captured at WARN.
- `test_corrupt_row_vector_bytes_recovered` (AC-8) — directly insert a row with `vector = b"short"`; calling `embed(same_text)` re-embeds + replaces.
- `test_model_digest_passthrough` (AC-9).
- `test_concurrent_embed_calls_do_not_corrupt_db` (AC-10) — `asyncio.gather(asyncio.to_thread(wrapper.embed, "a"), asyncio.to_thread(wrapper.embed, "b"))`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/embedding_cache.py` | `CachedEmbedder` wrapper + schema + lazy-open + corruption rebuild. |
| `src/codegenie/rag/errors.py` | Add `EmbeddingsCacheCorrupted` (extend existing module from S4-01). |
| `tests/unit/rag/test_embedding_cache.py` | Red test + AC follow-ons. |
| `tests/property/test_embedding_cache_roundtrip.py` | Hypothesis cache roundtrip (optional but cheap). |
| `pyproject.toml` | Add `blake3` to runtime deps **only** if not already present (verify first). |

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

The view returned by `np.frombuffer(row_bytes, dtype=np.float32)` is read-only. The retriever / property tests should not mutate the returned vector; if a caller needs to mutate, they `.copy()` themselves. Document this in the module docstring so a future contributor doesn't waste an hour on "why can't I modify this?"

### §4 — Vector dim 384 is BGE-small-specific

`_VECTOR_DIM = 384` is a `Final[int]` constant local to this module — it matches the BGE-small model S4-01 ships. A future Voyage adapter would have its own dim (1024); the cache schema is dim-agnostic (`BLOB` storage), but the **validator** that asserts `len(bytes) == 4 * 384` would need to be parameterized by `inner.embedding_dim` or similar. **Do not** add `embedding_dim` to the `Embedder` Protocol speculatively — when the second adapter lands, the Protocol can extend by addition. For now, the dim assertion is pinned to BGE-small explicitly.

### §5 — Logging shape

Use `structlog` (Phase 0 convention) — `log = structlog.get_logger(__name__)` at module top; `log.warning("cache_rebuilt_on_corruption", db_path=str(db_path))`. Never log the embedded text itself (PII / advisory content). The text's BLAKE3 hash is fine to log if needed for triage.

### §6 — Compose at call-site, not in the Protocol

`CachedEmbedder` is a decorator over `Embedder`; it does **not** modify the `Embedder` Protocol (which AC-9 of S4-01 froze at three methods). The composition `CachedEmbedder(FastembedEmbedder(...), db_path=...)` happens in the retriever wiring (S5-01) — not in `FastembedEmbedder.__init__`. This keeps each layer responsible for one thing: bootstrap-discipline vs. cache-aside.

### §7 — Don't add a `clear()` method

Tempting to add `def clear(self) -> None: self._conn.execute("DELETE FROM embeddings")`. **Don't.** The model-digest column already isolates upgrade scenarios; the operational recovery is "delete the file, the cache lazy-rebuilds on next access." If a future story needs cache clear, an ADR amendment is the bar — surface per Rule 7.
