"""Phase-4 S4-02 — Hypothesis property: cache hits never re-embed.

For any UTF-8-encodable text, calling ``wrapper.embed(text)`` twice on the
same :class:`CachedEmbedder` instance must:

1. Return bit-identical tuple-backed :data:`EmbeddingVector` values.
2. Increment the inner embedder's call counter by exactly 1 (the second
   call is served from the cache).
3. Leave exactly one row in the ``embeddings`` table for that
   ``(text_blake3, model_digest)`` pair.

The spy embedder is deterministic per-text so the byte-identity check
holds without depending on a real fastembed session. ``Cs`` (lone
surrogate) characters are excluded because UTF-8 encoding rejects them
and the cache key would never be computed in practice — that is a
boundary the smart-constructor would have caught at the Query layer.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import blake3
import numpy as np
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from codegenie.rag.embedding_cache import _VECTOR_DIM, CachedEmbedder
from codegenie.types.identifiers import BlobDigest, EmbeddingVector


class _Spy:
    """Tuple-backed deterministic spy — mirrors the unit-test fixture so
    the property suite is self-contained."""

    def __init__(self) -> None:
        self.calls = 0
        self._digest = BlobDigest("9" * 64)

    def embed(self, text: str) -> EmbeddingVector:
        self.calls += 1
        seed = (sum(text.encode("utf-8")) % 7) / 7.0
        vec = np.full(_VECTOR_DIM, seed, dtype=np.float32)
        return EmbeddingVector(tuple(float(x) for x in vec))

    def embed_batch(self, texts: list[str]) -> list[EmbeddingVector]:
        # Independent path; do NOT call self.embed, so the call counter
        # stays clean for the property assertion.
        seeds = [(sum(t.encode("utf-8")) % 7) / 7.0 for t in texts]
        return [
            EmbeddingVector(tuple(float(x) for x in np.full(_VECTOR_DIM, s, dtype=np.float32)))
            for s in seeds
        ]

    def model_digest(self) -> BlobDigest:
        return self._digest


_UTF8_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=["Cs"]),
    min_size=1,
    max_size=64,
)


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
@given(text=_UTF8_TEXT)
def test_cache_hit_is_idempotent_and_does_not_re_embed(tmp_path: Path, text: str) -> None:
    """For any UTF-8 text: second embed returns the same tuple and does
    not call inner; exactly one row exists for that (text, digest)."""
    db_path = tmp_path / "embeddings.cache.sqlite"
    spy = _Spy()
    wrapper = CachedEmbedder(inner=spy, db_path=db_path)

    first = wrapper.embed(text)
    calls_after_first = spy.calls
    second = wrapper.embed(text)
    calls_after_second = spy.calls

    assert first == second
    assert calls_after_first == 1
    assert calls_after_second == 1

    expected_key = blake3.blake3(text.encode("utf-8")).hexdigest()
    conn = sqlite3.connect(db_path)
    try:
        rows = list(
            conn.execute(
                "SELECT COUNT(*) FROM embeddings WHERE text_blake3=?",
                (expected_key,),
            )
        )
    finally:
        conn.close()
    assert rows == [(1,)]
