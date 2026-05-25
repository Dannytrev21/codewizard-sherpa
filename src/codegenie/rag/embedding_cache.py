"""Phase-4 S4-02 — :class:`CachedEmbedder` BLAKE3(text)-keyed SQLite cache-aside.

Decorator over any :class:`codegenie.rag.embedder.Embedder` that adds a
content-addressed cache-aside layer at
``.codegenie/rag/embeddings.cache.sqlite``. Cache key is the BLAKE3 hex
digest of the **input text**, and each row also carries the inner
embedder's :meth:`Embedder.model_digest` so a model upgrade automatically
invalidates cached vectors without dropping the old rows (ADR-0007
§Consequences).

Design notes (anchored in story S4-02 §Notes for the implementer):

- **Cache key is the input text, never the vector.** ONNX float drift at
  the 5th decimal (ADR-0007 §Tradeoffs) means two embeds of the same
  text on different CPU architectures produce slightly different vectors;
  hashing the vector would silently mass-invalidate when a developer
  runs on arm64 and CI runs on x86_64. The model digest column captures
  embedder identity, not vector identity.

- **Composite primary key ``(text_blake3, model_digest)`` is load-bearing.**
  A model upgrade must preserve the old row and insert a new row for the
  same text under the new digest — AC-5 of S4-02 pins this. Drop-and-
  insert-on-conflict against ``text_blake3`` alone would collapse the
  two rows and erase the old cached vector.

- **Lazy-open with rebuild-on-corruption (edge case #13).** The SQLite
  file is not opened in ``__init__``; the first non-empty ``embed`` /
  ``embed_batch`` call creates the parent directory, opens the file,
  applies PRAGMAs, and executes the schema. If any of that raises
  :class:`sqlite3.DatabaseError`, the wrapper closes the handle, deletes
  the file plus ``-wal`` / ``-shm`` sidecars, re-creates the schema, and
  treats the triggering call as a miss.

- **Row-level corruption recovers in-band.** If the stored vector blob is
  not exactly ``_VECTOR_BYTES`` bytes of ``np.float32``, ``_decode_row``
  raises :class:`EmbeddingsCacheCorrupted`. The shell catches it, deletes
  only that ``(text_blake3, model_digest)`` row, logs
  ``embedding_cache_row_corrupted``, re-embeds, and writes the
  replacement.

- **Concurrency target is idempotence, not single-flight.** The
  shared sqlite connection (``check_same_thread=False``) is guarded by a
  process-local ``threading.RLock``. Two concurrent same-text misses MAY
  both call the inner embedder; the writes are idempotent (``INSERT OR
  REPLACE``) and the table ends with one row per
  ``(text_blake3, model_digest)``. AC-10 pins this.

- **numpy stays inside the cache adapter.** S4-01 hardened
  :data:`EmbeddingVector` to a tuple-backed newtype so numpy never leaks
  through the public ``Embedder`` boundary. ``_encode_vector`` /
  ``_decode_row`` use numpy internally; ``embed()`` / ``embed_batch()``
  return ``EmbeddingVector(tuple(...))``.

- **No ``clear()`` method.** The model-digest column already isolates
  upgrade scenarios; the operational recovery is "delete the file, the
  cache lazy-rebuilds on next access." If a future story needs cache
  clear, an ADR amendment is the bar (S4-02 §7).
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

import blake3
import numpy as np
import structlog

from codegenie.rag.errors import EmbeddingsCacheCorrupted
from codegenie.types.identifiers import BlobDigest, EmbeddingVector

if TYPE_CHECKING:  # pragma: no cover — typing-only import
    from codegenie.rag.embedder import Embedder


# ---------------------------------------------------------------------------
# Schema + serialization constants
# ---------------------------------------------------------------------------


_VECTOR_DIM: Final[int] = 384
"""Bare-metal embedding dim for BGE-small (S4-01). The cache schema itself
is dim-agnostic (BLOB storage); the **validator** in ``_decode_row`` is
pinned to 384. A future second adapter that changes dim will need either
an `embedding_dim` Protocol extension (extension-by-addition) or a
parametric validator — not a speculative knob today (S4-02 §4)."""

_VECTOR_BYTES: Final[int] = 4 * _VECTOR_DIM
"""``np.float32`` is 4 bytes per scalar; ``_VECTOR_DIM`` scalars per row."""

_VECTOR_DTYPE: Final = np.dtype("float32")

_SCHEMA: Final[str] = """
CREATE TABLE IF NOT EXISTS embeddings (
    text_blake3 TEXT NOT NULL,
    model_digest TEXT NOT NULL,
    vector BLOB NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (text_blake3, model_digest)
);
CREATE INDEX IF NOT EXISTS idx_model ON embeddings(model_digest);
"""

_PRAGMAS: Final[tuple[str, ...]] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA busy_timeout=5000",
)

_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Pure helpers (functional core)
# ---------------------------------------------------------------------------


def _blake3_hex(text: str) -> BlobDigest:
    """Unprefixed 64-hex BLAKE3 digest of ``text`` encoded as UTF-8.

    Pure. The unprefixed form matches AC-4's ``blake3.blake3(b"hello").hexdigest()``
    comparison and the existing :data:`BlobDigest` Phase-3 convention.
    """
    return BlobDigest(blake3.blake3(text.encode("utf-8")).hexdigest())


def _encode_vector(vector: EmbeddingVector) -> bytes:
    """Serialize a tuple-backed :data:`EmbeddingVector` to ``np.float32`` bytes.

    The cache adapter is the only sanctioned numpy-cross-boundary site —
    callers hand us a ``EmbeddingVector(tuple(...))``, we hand back
    ``len == _VECTOR_BYTES`` bytes that round-trip via
    :func:`_decode_row` on read.
    """
    return np.asarray(tuple(vector), dtype=_VECTOR_DTYPE).tobytes()


def _decode_row(text_blake3: str, model_digest: str, blob: bytes) -> EmbeddingVector:
    """Validate + decode a stored vector blob; raise on row-level corruption.

    Raises
    ------
    EmbeddingsCacheCorrupted
        If ``len(blob) != _VECTOR_BYTES`` or the decoded ``np.frombuffer``
        view does not have shape ``(_VECTOR_DIM,)``. Caller's contract is
        to delete only the offending ``(text_blake3, model_digest)`` row
        and re-embed (AC-8).
    """
    if len(blob) != _VECTOR_BYTES:
        raise EmbeddingsCacheCorrupted(
            text_blake3=text_blake3,
            model_digest=model_digest,
            byte_len=len(blob),
        )
    decoded = np.frombuffer(blob, dtype=_VECTOR_DTYPE)
    if decoded.shape != (_VECTOR_DIM,):
        raise EmbeddingsCacheCorrupted(
            text_blake3=text_blake3,
            model_digest=model_digest,
            byte_len=len(blob),
        )
    # ``np.frombuffer`` returns a read-only view; cast to tuple of plain
    # ``float`` so callers see no numpy types (S4-02 §3 / §9).
    return EmbeddingVector(tuple(float(x) for x in decoded))


def _iso_now() -> str:
    """ISO-8601 UTC timestamp; informational ``created_at`` column only."""
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    """First-seen-order dedupe — used to assemble AC-6's ``missing_unique``."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


# ---------------------------------------------------------------------------
# CachedEmbedder — imperative shell
# ---------------------------------------------------------------------------


class CachedEmbedder:
    """Decorator that adds a BLAKE3(text)-keyed SQLite cache-aside to any
    :class:`codegenie.rag.embedder.Embedder`.

    The wrapper itself satisfies the ``Embedder`` Protocol — ``isinstance``
    against :class:`Embedder` returns True (AC-1). It is composed at
    call-site (e.g., the S5-01 retriever wiring), not inside
    ``FastembedEmbedder.__init__``; each layer has one responsibility
    (S4-02 §6).
    """

    __slots__ = ("_conn", "_db_path", "_inner", "_lock")

    _inner: Embedder
    _db_path: Path
    _conn: sqlite3.Connection | None
    _lock: threading.RLock

    def __init__(self, inner: Embedder, db_path: Path) -> None:
        self._inner = inner
        self._db_path = db_path
        self._conn = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ open

    def _lazy_open(self) -> sqlite3.Connection:
        """Open the cache db on first call; create parent dir + schema.

        Rebuild-on-corruption: a :class:`sqlite3.DatabaseError` raised
        either by ``sqlite3.connect`` (file-shaped but not a valid DB) or
        by the schema / pragma probe (header sentinel mismatch, etc.)
        triggers one rebuild attempt — close, unlink the file plus its
        WAL / SHM sidecars, recreate. A second failure propagates (AC-7).
        """
        with self._lock:
            if self._conn is not None:
                return self._conn
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                self._conn = self._connect_and_init(self._db_path)
            except sqlite3.DatabaseError as exc:
                _log.warning(
                    "cache_rebuilt_on_corruption",
                    db_path=str(self._db_path),
                    reason=exc.__class__.__name__,
                )
                self._discard_corrupt_db()
                self._conn = self._connect_and_init(self._db_path)
            return self._conn

    @staticmethod
    def _connect_and_init(db_path: Path) -> sqlite3.Connection:
        """Connect, apply PRAGMAs, install schema; raise on probe failure.

        Probed by ``SELECT 1`` so a file that ``sqlite3.connect`` accepts
        but the schema engine rejects (corrupt header past offset 0) still
        falls into the rebuild path (AC-7).
        """
        conn = sqlite3.connect(db_path, check_same_thread=False)
        try:
            for pragma in _PRAGMAS:
                conn.execute(pragma)
            conn.executescript(_SCHEMA)
            conn.execute("SELECT 1 FROM embeddings LIMIT 1")
            conn.commit()
        except sqlite3.DatabaseError:
            conn.close()
            raise
        return conn

    def _discard_corrupt_db(self) -> None:
        """Close + unlink the cache db plus its WAL/SHM sidecars."""
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:  # pragma: no cover — best-effort close
                pass
            self._conn = None
        for path in (
            self._db_path,
            self._db_path.with_name(self._db_path.name + "-wal"),
            self._db_path.with_name(self._db_path.name + "-shm"),
        ):
            if path.exists():
                path.unlink()

    # ------------------------------------------------------------------ embed

    def embed(self, text: str) -> EmbeddingVector:
        """Cache-aside ``embed``: lookup → return on hit; else delegate +
        write-back. Row-level corruption is recovered in-band (AC-8)."""
        key = _blake3_hex(text)
        digest = self._inner.model_digest()
        conn = self._lazy_open()
        cached = self._lookup_one(conn, key, digest)
        if cached is not None:
            return cached
        # Miss: compute outside the sqlite transaction so the inner call's
        # latency doesn't hold the RLock through the (potentially) long
        # embedding compute.
        vector = self._inner.embed(text)
        self._write_one(conn, key, digest, vector)
        return vector

    def embed_batch(self, texts: list[str]) -> list[EmbeddingVector]:
        """Cache-aside ``embed_batch``: dedupe in first-seen order, delegate
        only misses, assemble in input order (AC-6).

        ``embed_batch([])`` returns ``[]`` and MUST NOT open the SQLite
        file — the lazy-open invariant catches a "cache db materialized
        on empty call" mutant.
        """
        if not texts:
            return []
        conn = self._lazy_open()
        digest = self._inner.model_digest()
        keys = [_blake3_hex(t) for t in texts]

        # Build hit/miss split. Row-level corruption per key is recovered
        # individually (the row is deleted, the key falls back to miss).
        text_to_vector: dict[str, EmbeddingVector] = {}
        for text, key in zip(texts, keys, strict=True):
            if text in text_to_vector:
                continue
            cached = self._lookup_one(conn, key, digest)
            if cached is not None:
                text_to_vector[text] = cached

        missing = [t for t in _dedupe_preserve_order(texts) if t not in text_to_vector]
        if missing:
            fresh = self._inner.embed_batch(missing)
            if len(fresh) != len(missing):
                raise RuntimeError(
                    f"inner embed_batch returned {len(fresh)} vectors for {len(missing)} inputs"
                )
            for missed_text, vector in zip(missing, fresh, strict=True):
                missed_key = _blake3_hex(missed_text)
                self._write_one(conn, missed_key, digest, vector)
                text_to_vector[missed_text] = vector

        return [text_to_vector[t] for t in texts]

    def model_digest(self) -> BlobDigest:
        """Passthrough — the inner digest IS the cache-discriminator (AC-9)."""
        return self._inner.model_digest()

    # ------------------------------------------------------------------ helpers

    def _lookup_one(
        self,
        conn: sqlite3.Connection,
        key: BlobDigest,
        digest: BlobDigest,
    ) -> EmbeddingVector | None:
        """Single-row lookup; recovers from row-level corruption in-band.

        Returns ``None`` on miss OR on recovered row-level corruption
        (so the caller re-embeds). Never raises
        :class:`EmbeddingsCacheCorrupted` past this boundary (AC-8).
        """
        with self._lock:
            cursor = conn.execute(
                "SELECT vector FROM embeddings WHERE text_blake3=? AND model_digest=?",
                (str(key), str(digest)),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        try:
            return _decode_row(str(key), str(digest), row[0])
        except EmbeddingsCacheCorrupted:
            _log.warning(
                "embedding_cache_row_corrupted",
                text_blake3=str(key),
                model_digest=str(digest),
                byte_len=len(row[0]) if row[0] is not None else 0,
            )
            self._delete_row(conn, key, digest)
            return None

    def _delete_row(
        self,
        conn: sqlite3.Connection,
        key: BlobDigest,
        digest: BlobDigest,
    ) -> None:
        with self._lock:
            conn.execute(
                "DELETE FROM embeddings WHERE text_blake3=? AND model_digest=?",
                (str(key), str(digest)),
            )
            conn.commit()

    def _write_one(
        self,
        conn: sqlite3.Connection,
        key: BlobDigest,
        digest: BlobDigest,
        vector: EmbeddingVector,
    ) -> None:
        """Idempotent upsert. ``INSERT OR REPLACE`` keeps the concurrent
        double-miss case (AC-10) producing byte-identical bytes overwriting
        byte-identical bytes — a no-op in practice (S4-02 §2)."""
        blob = _encode_vector(vector)
        with self._lock:
            conn.execute(
                "INSERT OR REPLACE INTO embeddings "
                "(text_blake3, model_digest, vector, created_at) "
                "VALUES (?, ?, ?, ?)",
                (str(key), str(digest), blob, _iso_now()),
            )
            conn.commit()


__all__ = (
    "CachedEmbedder",
    "EmbeddingsCacheCorrupted",
    "_VECTOR_BYTES",
    "_VECTOR_DIM",
    "_blake3_hex",
    "_decode_row",
    "_encode_vector",
)
