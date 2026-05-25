"""Phase-4 S4-01 — fastembed-marked tests for ``FastembedEmbedder``.

These tests require real BGE-small ONNX weights. They are marked
``@pytest.mark.fastembed`` so the default test suite (which has no
bootstrapped cache) skips them; CI runs ``codegenie embeddings
bootstrap`` once and then opts these in with ``-m fastembed`` (or runs
them alongside the default suite, since fastembed is a registered
marker rather than a default-deselected one).

ACs covered:
  - AC-3: ``embed`` returns a ``len=384`` tuple of Python floats,
    L2-normalized to within 1e-3.
  - AC-4: ``embed_batch`` is semantically equivalent to repeated
    ``embed`` within tolerance (``cos ≥ 1 - 1e-6`` AND per-component
    ``abs ≤ 1e-5``); ``embed_batch([]) == []``.
  - AC-12: ``embed`` is bit-identical run-to-run on a single instance
    — the load-bearing precondition for S4-02's text-keyed cache.
  - AC-2 (positive): the full happy path (lock present + weights
    present + digest matches) constructs the embedder without raising.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from codegenie.types.identifiers import ModelId

pytestmark = pytest.mark.fastembed

_REPO_ROOT: Path = Path(__file__).resolve().parents[3]
_LIVE_CACHE: Path = _REPO_ROOT / ".codegenie" / "rag" / "fastembed-cache"
_LIVE_LOCK: Path = _REPO_ROOT / ".codegenie" / "rag" / "embeddings_model.lock"


def _require_bootstrapped() -> None:
    if not _LIVE_LOCK.is_file() or not _LIVE_CACHE.is_dir():
        pytest.skip(
            "live BGE-small cache not bootstrapped; run "
            "`python -m codegenie embeddings bootstrap`",
        )


@pytest.fixture
def live_embedder() -> object:
    _require_bootstrapped()
    from codegenie.rag.embedder import FastembedEmbedder

    return FastembedEmbedder(
        model_name=ModelId("BAAI/bge-small-en-v1.5"),
        lock_path=_LIVE_LOCK,
        cache_dir=_LIVE_CACHE,
    )


# ---------------------------------------------------------------------------
# AC-3 — embed shape, dtype, normalization
# ---------------------------------------------------------------------------


def test_embed_returns_normalized_384_tuple(live_embedder: object) -> None:
    """AC-3 — ``len == 384``, every element a Python ``float``,
    L2-norm within 1e-3 of 1.0. NOT an ``np.ndarray`` / dtype
    assertion — ``EmbeddingVector`` is a ``tuple`` newtype (S1-01 AC-2)."""
    vec = live_embedder.embed("hello world")  # type: ignore[attr-defined]
    assert isinstance(vec, tuple)
    assert len(vec) == 384
    for x in vec:
        assert isinstance(x, float)
    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-3


# ---------------------------------------------------------------------------
# AC-12 — embed determinism on a single instance
# ---------------------------------------------------------------------------


def test_embed_is_bit_identical_run_to_run(live_embedder: object) -> None:
    """AC-12 — ``embed(t) == embed(t)`` exactly. A non-deterministic
    ``embed`` would silently poison S4-02's text-keyed cache (the same
    text would store two different vectors, the cache lookup would
    cache-miss-loop). The strong invariant pins singleton-ONNX
    determinism."""
    a = live_embedder.embed("the quick brown fox")  # type: ignore[attr-defined]
    b = live_embedder.embed("the quick brown fox")  # type: ignore[attr-defined]
    assert a == b


# ---------------------------------------------------------------------------
# AC-4 — embed_batch semantic equivalence within tolerance
# ---------------------------------------------------------------------------


def _cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    num = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return num / (na * nb)


def test_embed_batch_within_tolerance_of_repeated_embed(
    live_embedder: object,
) -> None:
    """AC-4 — ``embed_batch([t0, t1, t2])[i]`` matches ``embed(ti)``
    within ``cos ≥ 1 - 1e-6`` AND per-component ``abs ≤ 1e-5``. Bit-
    equality is NOT required: ONNX batch kernels can differ from
    singleton kernels at the 5th decimal. ADR-0008's two-threshold band
    is what absorbs this; the load-bearing property here is that batch
    is a perf optimization, never a semantic change."""
    texts = ["alpha bravo", "charlie delta", "echo foxtrot"]
    batch = live_embedder.embed_batch(texts)  # type: ignore[attr-defined]
    singles = [live_embedder.embed(t) for t in texts]  # type: ignore[attr-defined]
    assert len(batch) == len(texts)
    for i, (b_vec, s_vec) in enumerate(zip(batch, singles, strict=True)):
        cos = _cosine(b_vec, s_vec)
        assert cos >= 1 - 1e-6, f"cosine drift at i={i}: cos={cos}"
        for j, (bx, sx) in enumerate(zip(b_vec, s_vec, strict=True)):
            assert abs(bx - sx) <= 1e-5, (
                f"per-component drift at i={i} j={j}: |Δ|={abs(bx - sx)}"
            )


def test_embed_batch_empty_returns_empty(live_embedder: object) -> None:
    """AC-4 — ``embed_batch([]) == []`` (not a crash, not a one-element
    list with an empty vector)."""
    assert live_embedder.embed_batch([]) == []  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# AC-2 (positive happy path)
# ---------------------------------------------------------------------------


def test_full_happy_path_construct_then_embed() -> None:
    """End-to-end positive control: a freshly-constructed embedder
    against the real bootstrapped cache embeds without raising and
    ``model_digest()`` matches the on-disk lock contents byte-for-byte.
    """
    _require_bootstrapped()
    from codegenie.rag.embedder import FastembedEmbedder

    emb = FastembedEmbedder(
        model_name=ModelId("BAAI/bge-small-en-v1.5"),
        lock_path=_LIVE_LOCK,
        cache_dir=_LIVE_CACHE,
    )
    vec = emb.embed("end-to-end smoke")
    assert len(vec) == 384

    import yaml

    payload = yaml.safe_load(_LIVE_LOCK.read_text())
    assert emb.model_digest() == payload["sha256"]
