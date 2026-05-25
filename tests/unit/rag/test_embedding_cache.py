"""Phase-4 S4-02 — ``CachedEmbedder`` BLAKE3-keyed SQLite cache-aside.

Every test below pins a specific acceptance criterion (or rejects a
specific mutant) for the cache wrapper described in
``docs/phases/04-vuln-llm-fallback-rag/stories/S4-02-embeddings-cache-sqlite.md``.

The spy embedder is deliberately tuple-backed (no numpy past the
public ``Embedder`` boundary) so we don't accidentally regress S4-01's
``EmbeddingVector`` discipline (S1-01 AC-2).
"""

from __future__ import annotations

import asyncio
import sqlite3
import struct
from pathlib import Path

import blake3
import numpy as np
import pytest
from structlog.testing import capture_logs

from codegenie.rag.embedding_cache import (
    _VECTOR_BYTES,
    _VECTOR_DIM,
    CachedEmbedder,
    EmbeddingsCacheCorrupted,
)
from codegenie.types.identifiers import BlobDigest, EmbeddingVector

# ---------------------------------------------------------------------------
# Test doubles — spy embedder; tuple-backed vectors only (S4-01 AC-9)
# ---------------------------------------------------------------------------


class _SpyEmbedder:
    """Counts inner-call invocations; deterministic per-text vectors.

    Returns ``EmbeddingVector(tuple(...))`` of length ``_VECTOR_DIM`` so the
    public boundary stays tuple-backed (S4-01 AC-9).
    """

    def __init__(self, digest: BlobDigest | None = None) -> None:
        self.embed_calls = 0
        self.embed_batch_calls = 0
        self.last_batch: list[str] = []
        self._digest = digest if digest is not None else BlobDigest("1" * 64)

    def embed(self, text: str) -> EmbeddingVector:
        self.embed_calls += 1
        # Deterministic vector per text — repeatable across calls.
        seed = (sum(text.encode("utf-8")) % 7) / 7.0
        vec = np.full(_VECTOR_DIM, seed, dtype=np.float32)
        return EmbeddingVector(tuple(float(x) for x in vec))

    def embed_batch(self, texts: list[str]) -> list[EmbeddingVector]:
        self.embed_batch_calls += 1
        self.last_batch = list(texts)
        return [self._embed_unchecked(t) for t in texts]

    def _embed_unchecked(self, text: str) -> EmbeddingVector:
        """Vector compute used by both ``embed`` and ``embed_batch`` without
        bumping the single-shot ``embed_calls`` counter — keeps AC-6's
        "embed_batch routes to the batch API" assertion clean."""
        seed = (sum(text.encode("utf-8")) % 7) / 7.0
        vec = np.full(_VECTOR_DIM, seed, dtype=np.float32)
        return EmbeddingVector(tuple(float(x) for x in vec))

    def model_digest(self) -> BlobDigest:
        return self._digest


# ---------------------------------------------------------------------------
# AC-3 — cache hit avoids second inner embed call (RED ↔ GREEN root)
# ---------------------------------------------------------------------------


def test_cache_hit_avoids_second_inner_embed_call(tmp_path: Path) -> None:
    """AC-3 — ADR-0007 §Consequences: cache must short-circuit on hit.

    If this regresses, every retriever query re-embeds — Phase 4's p99
    budget busted. Catches "always-miss" and "never-write" mutants.
    """
    spy = _SpyEmbedder()
    wrapper = CachedEmbedder(inner=spy, db_path=tmp_path / "embeddings.cache.sqlite")

    v1 = wrapper.embed("hello")
    v2 = wrapper.embed("hello")

    assert spy.embed_calls == 1, "cache must short-circuit second call"
    assert v1 == v2, "cached vector must be bit-identical"


# ---------------------------------------------------------------------------
# AC-1 — wrapper shape, lazy-open, Protocol conformance
# ---------------------------------------------------------------------------


def test_init_is_lazy_no_dir_or_db_created(tmp_path: Path) -> None:
    """AC-1 — neither the missing parent dir nor the db file exist until
    the first non-empty call. Catches an eager-open mutant."""
    spy = _SpyEmbedder()
    db_path = tmp_path / "missing" / "embeddings.cache.sqlite"
    wrapper = CachedEmbedder(inner=spy, db_path=db_path)

    assert not db_path.parent.exists()
    assert not db_path.exists()
    # Spy untouched and wrapper untouched -- exists for use-after-construct.
    assert wrapper is not None


def test_wrapper_conforms_to_embedder_protocol(tmp_path: Path) -> None:
    """AC-1 — ``isinstance(CachedEmbedder(...), Embedder) is True``."""
    from codegenie.rag.embedder import Embedder

    wrapper = CachedEmbedder(
        inner=_SpyEmbedder(),
        db_path=tmp_path / "embeddings.cache.sqlite",
    )
    assert isinstance(wrapper, Embedder)


# ---------------------------------------------------------------------------
# AC-2 / AC-5 — schema composite primary key
# ---------------------------------------------------------------------------


def test_schema_uses_text_and_model_digest_composite_key(tmp_path: Path) -> None:
    """AC-2 / AC-5 — PRIMARY KEY is (text_blake3, model_digest).

    A schema test catches a regression where the executor "improves" the
    table to ``text_blake3 TEXT PRIMARY KEY`` (the original validator-
    rejected shape), which would silently break ``test_model_digest_
    mismatch_treated_as_miss``.
    """
    db_path = tmp_path / "embeddings.cache.sqlite"
    wrapper = CachedEmbedder(inner=_SpyEmbedder(), db_path=db_path)
    wrapper.embed("seed")  # trigger lazy-open + schema install

    conn = sqlite3.connect(db_path)
    try:
        cols = list(conn.execute("PRAGMA table_info(embeddings)"))
        # column rows: (cid, name, type, notnull, dflt_value, pk)
        pk_columns = sorted(name for _cid, name, _t, _nn, _d, pk in cols if pk)
        assert pk_columns == ["model_digest", "text_blake3"], pk_columns
        # idx_model index present per AC-2.
        idx_names = {row[1] for row in conn.execute("PRAGMA index_list(embeddings)")}
        assert "idx_model" in idx_names
    finally:
        conn.close()


def test_two_digests_for_same_text_coexist(tmp_path: Path) -> None:
    """AC-5 — both rows survive: ``text_blake3`` alone is NOT unique."""
    db_path = tmp_path / "embeddings.cache.sqlite"
    spy_a = _SpyEmbedder(digest=BlobDigest("a" * 64))
    wrapper_a = CachedEmbedder(inner=spy_a, db_path=db_path)
    wrapper_a.embed("hello")

    spy_b = _SpyEmbedder(digest=BlobDigest("b" * 64))
    wrapper_b = CachedEmbedder(inner=spy_b, db_path=db_path)
    wrapper_b.embed("hello")

    conn = sqlite3.connect(db_path)
    try:
        rows = list(
            conn.execute(
                "SELECT model_digest FROM embeddings WHERE text_blake3=? ORDER BY model_digest",
                (blake3.blake3(b"hello").hexdigest(),),
            )
        )
    finally:
        conn.close()
    assert [r[0] for r in rows] == ["a" * 64, "b" * 64]


# ---------------------------------------------------------------------------
# AC-4 — cache key is BLAKE3(text), not a vector / sha256 / truncated digest
# ---------------------------------------------------------------------------


def test_cache_key_is_blake3_of_input_text(tmp_path: Path) -> None:
    """AC-4 — verbatim ``blake3.blake3(b"hello").hexdigest()`` match.

    Catches "use sha256" / "use truncated digest" / "hash the vector"
    mutants.
    """
    db_path = tmp_path / "embeddings.cache.sqlite"
    wrapper = CachedEmbedder(inner=_SpyEmbedder(), db_path=db_path)
    wrapper.embed("hello")

    expected = blake3.blake3(b"hello").hexdigest()
    conn = sqlite3.connect(db_path)
    try:
        rows = list(conn.execute("SELECT text_blake3 FROM embeddings"))
    finally:
        conn.close()
    assert rows == [(expected,)]
    assert len(expected) == 64


# ---------------------------------------------------------------------------
# AC-5 — model-digest mismatch on read = cache miss; old row untouched
# ---------------------------------------------------------------------------


def test_model_digest_mismatch_treated_as_miss(tmp_path: Path) -> None:
    """AC-5 — pre-populating against an old digest then wrapping a new
    inner embedder forces the cache to treat the read as a miss; the old
    row is left intact (no cascading delete)."""
    db_path = tmp_path / "embeddings.cache.sqlite"
    old_digest = BlobDigest("0" * 64)
    new_digest = BlobDigest("1" * 64)

    # Pre-populate via the wrapper itself using the old-digest inner.
    old_wrapper = CachedEmbedder(inner=_SpyEmbedder(digest=old_digest), db_path=db_path)
    old_wrapper.embed("hello")

    new_inner = _SpyEmbedder(digest=new_digest)
    new_wrapper = CachedEmbedder(inner=new_inner, db_path=db_path)
    new_wrapper.embed("hello")

    # Inner was called once because the cache lookup missed under the new digest.
    assert new_inner.embed_calls == 1

    conn = sqlite3.connect(db_path)
    try:
        rows = sorted(
            r[0]
            for r in conn.execute(
                "SELECT model_digest FROM embeddings WHERE text_blake3=?",
                (blake3.blake3(b"hello").hexdigest(),),
            )
        )
    finally:
        conn.close()
    # Both rows survive (composite PK invariant).
    assert rows == [old_digest, new_digest]


# ---------------------------------------------------------------------------
# AC-6 — embed_batch is cache-aware: dedup + partial-hit + empty short-circuit
# ---------------------------------------------------------------------------


def test_embed_batch_dedups_and_preserves_order(tmp_path: Path) -> None:
    """AC-6 — input ``["a", "b", "a"]``: inner.embed_batch sees ``["a", "b"]``;
    output index 0 == index 2 (same row, byte-identical)."""
    db_path = tmp_path / "embeddings.cache.sqlite"
    spy = _SpyEmbedder()
    wrapper = CachedEmbedder(inner=spy, db_path=db_path)

    out = wrapper.embed_batch(["a", "b", "a"])

    assert spy.last_batch == ["a", "b"], spy.last_batch
    assert spy.embed_batch_calls == 1
    assert out[0] == out[2]
    assert len(out) == 3


def test_embed_batch_partial_hit_only_delegates_misses(tmp_path: Path) -> None:
    """AC-6 — pre-populate ``"a"``; call with ``["a", "b", "a", "c"]``;
    inner sees only ``["b", "c"]`` while output preserves all four positions."""
    db_path = tmp_path / "embeddings.cache.sqlite"
    spy = _SpyEmbedder()
    wrapper = CachedEmbedder(inner=spy, db_path=db_path)
    pre = wrapper.embed("a")  # warm cache row for "a"
    assert spy.embed_calls == 1

    out = wrapper.embed_batch(["a", "b", "a", "c"])

    assert spy.last_batch == ["b", "c"]
    assert spy.embed_batch_calls == 1
    assert out[0] == out[2] == pre
    assert len(out) == 4


def test_embed_batch_empty_returns_empty_without_opening_db(tmp_path: Path) -> None:
    """AC-6 — ``embed_batch([])`` returns ``[]`` and the SQLite file is not
    created. Catches an eager-open mutant inside ``embed_batch``."""
    spy = _SpyEmbedder()
    db_path = tmp_path / "embeddings.cache.sqlite"
    wrapper = CachedEmbedder(inner=spy, db_path=db_path)

    out = wrapper.embed_batch([])

    assert out == []
    assert spy.embed_calls == 0
    assert spy.embed_batch_calls == 0
    assert not db_path.exists()


# ---------------------------------------------------------------------------
# AC-7 — sqlite file corruption is recovered on next call; log emitted
# ---------------------------------------------------------------------------


def test_corruption_rebuilds_cache_silently(tmp_path: Path) -> None:
    """AC-7 — a corrupt sqlite file at ``db_path`` is rebuilt on first
    ``embed`` without surfacing ``sqlite3.DatabaseError`` to the caller.

    Uses a sqlite-shaped-but-malformed file (valid magic header, garbage
    body) so the rebuild path is exercised: a literal 1-byte zero file
    would be silently accepted by ``sqlite3.connect`` + early PRAGMAs
    (sqlite treats a near-empty file as a fresh db). The malformed
    body trips ``file is not a database`` on the first table-touching
    query, which is exactly the runtime failure shape edge case #13
    points at.
    """
    db_path = tmp_path / "embeddings.cache.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"SQLite format 3\x00" + b"\xff" * 200)
    # Also drop fake WAL/SHM sidecars so we can prove they're cleaned up.
    db_path.with_name(db_path.name + "-wal").write_bytes(b"\x00")
    db_path.with_name(db_path.name + "-shm").write_bytes(b"\x00")

    spy = _SpyEmbedder()
    wrapper = CachedEmbedder(inner=spy, db_path=db_path)
    with capture_logs() as logs:
        out = wrapper.embed("hello")

    assert spy.embed_calls == 1
    assert len(out) == _VECTOR_DIM
    # New file is a valid db now; schema query succeeds.
    conn = sqlite3.connect(db_path)
    try:
        rows = list(conn.execute("SELECT COUNT(*) FROM embeddings"))
    finally:
        conn.close()
    assert rows == [(1,)]
    # Warning fired with the expected event name; raw text is NEVER logged.
    rebuild_events = [
        entry for entry in logs if entry.get("event") == "cache_rebuilt_on_corruption"
    ]
    assert rebuild_events, logs
    assert rebuild_events[0]["db_path"] == str(db_path)
    for entry in logs:
        assert "hello" not in str(entry)


# ---------------------------------------------------------------------------
# AC-8 — row-level vector corruption is recovered in-band; no leak
# ---------------------------------------------------------------------------


def test_corrupt_row_vector_bytes_recovered(tmp_path: Path) -> None:
    """AC-8 — a too-short vector blob triggers ``EmbeddingsCacheCorrupted``
    inside ``_decode_row``; ``embed`` catches it, deletes only the
    offending row, re-embeds, replaces. The exception MUST NOT escape."""
    db_path = tmp_path / "embeddings.cache.sqlite"
    spy = _SpyEmbedder()
    wrapper = CachedEmbedder(inner=spy, db_path=db_path)
    wrapper.embed("hello")  # warm
    assert spy.embed_calls == 1

    # Tamper: replace stored vector with 5 bytes of garbage.
    expected_key = blake3.blake3(b"hello").hexdigest()
    digest = spy.model_digest()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE embeddings SET vector=? WHERE text_blake3=? AND model_digest=?",
            (b"short", expected_key, str(digest)),
        )
        conn.commit()
    finally:
        conn.close()

    # Reopen with a fresh wrapper to defeat any in-process caching of a
    # previously-returned vector.
    wrapper2 = CachedEmbedder(inner=spy, db_path=db_path)
    with capture_logs() as logs:
        out = wrapper2.embed("hello")

    # Inner was called again (corruption recovery counted as a miss).
    assert spy.embed_calls == 2
    assert len(out) == _VECTOR_DIM

    conn = sqlite3.connect(db_path)
    try:
        rows = list(
            conn.execute(
                "SELECT LENGTH(vector) FROM embeddings WHERE text_blake3=? AND model_digest=?",
                (expected_key, str(digest)),
            )
        )
    finally:
        conn.close()
    # The replacement row carries a length-checked _VECTOR_BYTES payload.
    assert rows == [(_VECTOR_BYTES,)]
    corruption_events = [
        entry for entry in logs if entry.get("event") == "embedding_cache_row_corrupted"
    ]
    assert corruption_events, logs
    # text_blake3 + model_digest carried for triage; raw text never logged.
    assert corruption_events[0]["text_blake3"] == expected_key
    for entry in logs:
        assert "hello" not in str(entry)


def test_embeddings_cache_corrupted_never_escapes(tmp_path: Path) -> None:
    """AC-8 — the typed exception is private; callers never see it.

    Directly mutate the on-disk row to provoke a corrupt decode and assert
    ``embed`` returns a fresh vector instead of propagating
    ``EmbeddingsCacheCorrupted``.
    """
    db_path = tmp_path / "embeddings.cache.sqlite"
    wrapper = CachedEmbedder(inner=_SpyEmbedder(), db_path=db_path)
    wrapper.embed("hi")
    digest = wrapper.model_digest()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE embeddings SET vector=? WHERE text_blake3=? AND model_digest=?",
            (b"", blake3.blake3(b"hi").hexdigest(), str(digest)),
        )
        conn.commit()
    finally:
        conn.close()

    # No try/except — if EmbeddingsCacheCorrupted leaks, the test fails.
    wrapper2 = CachedEmbedder(inner=_SpyEmbedder(), db_path=db_path)
    out = wrapper2.embed("hi")
    assert len(out) == _VECTOR_DIM


def test_vector_roundtrip_is_byte_identical(tmp_path: Path) -> None:
    """AC-8 — stored bytes == ``np.asarray(tuple(vector), dtype=float32).tobytes()``."""
    db_path = tmp_path / "embeddings.cache.sqlite"
    spy = _SpyEmbedder()
    wrapper = CachedEmbedder(inner=spy, db_path=db_path)
    vector = wrapper.embed("roundtrip")

    expected_bytes = np.asarray(tuple(vector), dtype=np.float32).tobytes()
    conn = sqlite3.connect(db_path)
    try:
        rows = list(conn.execute("SELECT vector FROM embeddings"))
    finally:
        conn.close()
    assert rows[0][0] == expected_bytes
    # And the public boundary is tuple-backed (no numpy leak).
    assert isinstance(vector, tuple)
    assert all(isinstance(x, float) for x in vector)


# ---------------------------------------------------------------------------
# AC-9 — model_digest passthrough
# ---------------------------------------------------------------------------


def test_model_digest_passthrough(tmp_path: Path) -> None:
    """AC-9 — wrapper does NOT invent a new digest."""
    spy = _SpyEmbedder(digest=BlobDigest("d" * 64))
    wrapper = CachedEmbedder(inner=spy, db_path=tmp_path / "embeddings.cache.sqlite")
    assert wrapper.model_digest() == spy.model_digest()


# ---------------------------------------------------------------------------
# AC-10 — concurrency-safe within a single asyncio loop
# ---------------------------------------------------------------------------


def test_concurrent_embed_calls_do_not_corrupt_db(tmp_path: Path) -> None:
    """AC-10 — ``asyncio.gather(asyncio.to_thread(...), ...)``: post-run
    table holds exactly one row for the (text, digest) pair; both callers
    receive bit-identical vectors; no ``database is locked`` escapes."""
    db_path = tmp_path / "embeddings.cache.sqlite"
    spy = _SpyEmbedder()
    wrapper = CachedEmbedder(inner=spy, db_path=db_path)

    async def driver() -> tuple[EmbeddingVector, EmbeddingVector]:
        results = await asyncio.gather(
            asyncio.to_thread(wrapper.embed, "concurrent"),
            asyncio.to_thread(wrapper.embed, "concurrent"),
        )
        return results[0], results[1]

    v1, v2 = asyncio.run(driver())
    assert v1 == v2

    conn = sqlite3.connect(db_path)
    try:
        rows = list(
            conn.execute(
                "SELECT COUNT(*) FROM embeddings WHERE text_blake3=?",
                (blake3.blake3(b"concurrent").hexdigest(),),
            )
        )
    finally:
        conn.close()
    assert rows == [(1,)]


# ---------------------------------------------------------------------------
# Defensive coverage — invalid stored shape (length passes, dtype reshape fails)
# ---------------------------------------------------------------------------


def test_decode_row_rejects_wrong_byte_count() -> None:
    """Direct exercise of the pure helper so the AC-8 invariant is pinned
    even if a future refactor moves call sites around."""
    from codegenie.rag.embedding_cache import _decode_row

    with pytest.raises(EmbeddingsCacheCorrupted) as exc_info:
        _decode_row("a" * 64, "b" * 64, b"\x00" * (_VECTOR_BYTES - 4))
    assert exc_info.value.byte_len == _VECTOR_BYTES - 4


def test_encode_decode_roundtrip() -> None:
    """``_encode_vector`` ↔ ``_decode_row`` is byte-identical.

    Uses fractions with an exact float32 representation (``i / 256.0``,
    a power-of-2 denominator) so the round-trip tuple equality holds
    after float64→float32→float64 widening. The encoder is canonical
    in float32 — verifying values that LOSE precision in float32 would
    test float arithmetic, not the encoder contract.
    """
    from codegenie.rag.embedding_cache import _decode_row, _encode_vector

    original = EmbeddingVector(tuple(float(i) / 256.0 for i in range(_VECTOR_DIM)))
    blob = _encode_vector(original)
    assert len(blob) == _VECTOR_BYTES
    decoded = _decode_row("k", "d", blob)
    assert decoded == original


def test_vector_blob_layout_matches_float32_struct() -> None:
    """Anchor the storage contract via stdlib ``struct`` so a numpy
    refactor cannot silently change the on-disk encoding."""
    from codegenie.rag.embedding_cache import _encode_vector

    sample = EmbeddingVector(tuple([0.5] * _VECTOR_DIM))
    blob = _encode_vector(sample)
    unpacked = struct.unpack(f"<{_VECTOR_DIM}f", blob)
    assert all(abs(x - 0.5) < 1e-7 for x in unpacked)
