"""Phase-4 S4-01 — ``FastembedEmbedder`` refuse-start + Protocol behavior.

ACs covered here (no real ``fastembed`` weight download):
  - AC-2: refuse-start branches (missing lock, corrupt lock, weights absent,
    model_name mismatch, sha256 mismatch).
  - AC-5: ``model_digest()`` stability.
  - AC-7 (behavioral): runtime ``__init__`` never downloads weights when
    the lock is verified against an already-populated cache.
  - AC-8: typed errors carry ``kind`` discriminator + diagnostic strings.

ACs requiring real BGE-small weights are marked ``@pytest.mark.fastembed``
and live in :mod:`test_embedder_fastembed_marked` (separate module so the
unmarked unit-test file stays fast).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path
from unittest.mock import patch

import pytest

from codegenie.rag.errors import (
    EmbeddingModelMismatch,
    EmbeddingsBootstrapRequired,
)
from codegenie.types.identifiers import ModelId


def _digest_dir(root: Path) -> str:
    """Recompute the directory digest the same way the implementation does.

    The algorithm is part of the AC-6 contract: sorted relative-path
    traversal of every regular file under ``root``; sha256 fold of
    ``(rel_path_bytes, file_bytes)`` pairs. Tests recompute it
    independently to catch silent algorithm drift in the implementation.
    """
    hasher = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix().encode("utf-8")
        hasher.update(rel)
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def _seed_synthetic_cache(cache_dir: Path) -> str:
    """Populate ``cache_dir`` with a synthetic, multi-file 'model' tree
    so that AC-6's directory digest is exercised (a single-file fixture
    would silently let a single-file sha256 implementation pass).
    Returns the expected digest for that tree.
    """
    model_dir = cache_dir / "BAAI__bge-small-en-v1.5"
    model_dir.mkdir(parents=True)
    (model_dir / "model.onnx").write_bytes(b"weights-bytes-v1")
    (model_dir / "tokenizer.json").write_bytes(b'{"version":"1.0"}')
    (model_dir / "config.json").write_bytes(b'{"hidden_size":384}')
    return _digest_dir(cache_dir)


def _write_lock(lock_path: Path, *, model_name: str, sha256: str) -> None:
    import yaml  # local import keeps test file deps explicit

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # Use yaml.safe_dump so an all-numeric sha256 (e.g., "0" * 64) is
    # round-tripped as a string and not silently coerced to int. This
    # mirrors how the bootstrap CLI writes the file.
    lock_path.write_text(
        yaml.safe_dump(
            {"model_name": model_name, "sha256": sha256},
            sort_keys=True,
        )
    )


# ---------------------------------------------------------------------------
# AC-2 — refuse-start branches
# ---------------------------------------------------------------------------


def test_refuses_to_start_when_lock_missing(tmp_path: Path) -> None:
    """ADR-0007 §Decision — runtime refuses-start on bootstrap absence.

    Catches the 'silent-fallback-to-untracked-weights' failure mode.
    """
    from codegenie.rag.embedder import FastembedEmbedder

    with pytest.raises(EmbeddingsBootstrapRequired) as exc_info:
        FastembedEmbedder(
            lock_path=tmp_path / "embeddings_model.lock",
            cache_dir=tmp_path / "fastembed-cache",
        )

    assert "codegenie embeddings bootstrap" in str(exc_info.value)
    assert exc_info.value.runbook_url == "docs/operations/embeddings.md"


def test_refuses_to_start_on_corrupt_lock_yaml(tmp_path: Path) -> None:
    """A present-but-unparseable lock raises ``EmbeddingsBootstrapRequired``
    with a 'lock corrupt' diagnostic — not a raw ``yaml.YAMLError``
    (Rule 12: fail loud *and* typed; adapter-pattern boundary)."""
    from codegenie.rag.embedder import FastembedEmbedder

    lock = tmp_path / "embeddings_model.lock"
    lock.write_text(":\n  - this is not a mapping: [unclosed")

    with pytest.raises(EmbeddingsBootstrapRequired) as exc_info:
        FastembedEmbedder(
            lock_path=lock,
            cache_dir=tmp_path / "fastembed-cache",
        )
    assert "corrupt" in str(exc_info.value).lower()
    assert "codegenie embeddings bootstrap" in str(exc_info.value)


def test_refuses_to_start_on_corrupt_lock_unknown_key(tmp_path: Path) -> None:
    """``_EmbeddingsModelLock`` is ``extra='forbid'``; an unknown key is
    treated as a corrupt lock (not a ``pydantic.ValidationError`` escape)."""
    from codegenie.rag.embedder import FastembedEmbedder

    lock = tmp_path / "embeddings_model.lock"
    lock.write_text(
        "model_name: BAAI/bge-small-en-v1.5\nsha256: " + "0" * 64 + "\nunexpected: junk\n"
    )

    with pytest.raises(EmbeddingsBootstrapRequired) as exc_info:
        FastembedEmbedder(
            lock_path=lock,
            cache_dir=tmp_path / "fastembed-cache",
        )
    assert "corrupt" in str(exc_info.value).lower()


def test_refuses_when_weights_absent(tmp_path: Path) -> None:
    """Lock present, but the on-disk weights cache is empty / missing —
    distinct from missing-lock case; same remedy
    (``codegenie embeddings bootstrap``). Raises
    ``EmbeddingsBootstrapRequired``, NOT ``EmbeddingModelMismatch``."""
    from codegenie.rag.embedder import FastembedEmbedder

    lock = tmp_path / "embeddings_model.lock"
    _write_lock(lock, model_name="BAAI/bge-small-en-v1.5", sha256="0" * 64)

    with pytest.raises(EmbeddingsBootstrapRequired) as exc_info:
        FastembedEmbedder(
            lock_path=lock,
            cache_dir=tmp_path / "fastembed-cache",  # absent dir
        )
    assert "codegenie embeddings bootstrap" in str(exc_info.value)


def test_refuses_when_weights_dir_present_but_empty(tmp_path: Path) -> None:
    """Lock present, cache dir present but with no files at all — also
    weights-absent. Implementation must walk the tree, not just check
    ``cache_dir.exists()``."""
    from codegenie.rag.embedder import FastembedEmbedder

    cache_dir = tmp_path / "fastembed-cache"
    cache_dir.mkdir()
    lock = tmp_path / "embeddings_model.lock"
    _write_lock(lock, model_name="BAAI/bge-small-en-v1.5", sha256="0" * 64)

    with pytest.raises(EmbeddingsBootstrapRequired):
        FastembedEmbedder(lock_path=lock, cache_dir=cache_dir)


def test_refuses_on_model_name_mismatch(tmp_path: Path) -> None:
    """Lock's ``model_name`` != ctor ``model_name``:
    ``EmbeddingModelMismatch(kind='model_name', expected=ctor, found=lock)``.

    The ``kind`` discriminator distinguishes this raise-site from the
    sha256-drift one (AC-8 — without it, ``expected``/``found`` are
    indistinguishable: both are strings)."""
    from codegenie.rag.embedder import FastembedEmbedder

    cache_dir = tmp_path / "fastembed-cache"
    _seed_synthetic_cache(cache_dir)
    lock = tmp_path / "embeddings_model.lock"
    _write_lock(lock, model_name="BAAI/bge-small-en-v1.5", sha256="0" * 64)

    with pytest.raises(EmbeddingModelMismatch) as exc_info:
        FastembedEmbedder(
            model_name=ModelId("BAAI/bge-large-en-v1.5"),  # differs
            lock_path=lock,
            cache_dir=cache_dir,
        )
    assert exc_info.value.kind == "model_name"
    assert exc_info.value.expected == "BAAI/bge-large-en-v1.5"
    assert exc_info.value.found == "BAAI/bge-small-en-v1.5"


def test_refuses_on_sha256_drift(tmp_path: Path) -> None:
    """ADR-0007 + edge case #3 — sha256-drift refuse-start branch.
    Weights present, lock present, but digest mismatches: a fat-fingered
    model upgrade halts the worker rather than silently embedding into a
    different vector space."""
    from codegenie.rag.embedder import FastembedEmbedder

    cache_dir = tmp_path / "fastembed-cache"
    _seed_synthetic_cache(cache_dir)
    lock = tmp_path / "embeddings_model.lock"
    expected_digest = "0" * 64  # deliberately wrong
    _write_lock(lock, model_name="BAAI/bge-small-en-v1.5", sha256=expected_digest)

    with pytest.raises(EmbeddingModelMismatch) as exc_info:
        FastembedEmbedder(lock_path=lock, cache_dir=cache_dir)
    assert exc_info.value.kind == "sha256"
    assert exc_info.value.expected == expected_digest
    assert exc_info.value.found != expected_digest
    # The diagnostic also names the runbook so an operator can recover.
    assert "docs/operations/embeddings.md" in str(exc_info.value)


# ---------------------------------------------------------------------------
# AC-5 — model_digest stability
# ---------------------------------------------------------------------------


class _SpyTextEmbedding:
    """Stand-in for ``fastembed.TextEmbedding`` so unit tests can construct
    a ``FastembedEmbedder`` without downloading real weights. The runtime
    construct path goes via :func:`importlib.import_module` so we patch the
    attribute on the live ``fastembed`` module."""

    instances: list[_SpyTextEmbedding] = []  # noqa: RUF012 — class-level spy registry

    def __init__(self, model_name: str, **kwargs: object) -> None:
        self.model_name = model_name
        self.kwargs = kwargs
        _SpyTextEmbedding.instances.append(self)

    def embed(self, texts: Iterable[str], **_: object) -> Iterable[object]:
        raise NotImplementedError("Spy never embeds — only construction is observed.")


@pytest.fixture(autouse=True)
def _reset_spy() -> None:
    _SpyTextEmbedding.instances.clear()


def test_model_digest_returns_lock_sha256_verbatim(tmp_path: Path) -> None:
    """AC-5 — ``model_digest()`` returns ``BlobDigest(lock.sha256)`` verbatim,
    same string on every call, same string across instances."""
    from codegenie.rag.embedder import FastembedEmbedder

    cache_dir = tmp_path / "fastembed-cache"
    expected_digest = _seed_synthetic_cache(cache_dir)
    lock = tmp_path / "embeddings_model.lock"
    _write_lock(lock, model_name="BAAI/bge-small-en-v1.5", sha256=expected_digest)

    with patch("fastembed.TextEmbedding", _SpyTextEmbedding):
        emb_a = FastembedEmbedder(lock_path=lock, cache_dir=cache_dir)
        emb_b = FastembedEmbedder(lock_path=lock, cache_dir=cache_dir)

    assert emb_a.model_digest() == expected_digest
    assert emb_a.model_digest() == emb_a.model_digest()
    assert emb_a.model_digest() == emb_b.model_digest()


# ---------------------------------------------------------------------------
# AC-7 (behavioral) — runtime __init__ never downloads
# ---------------------------------------------------------------------------


def test_runtime_init_never_downloads(tmp_path: Path) -> None:
    """AC-7 behavioral — when the lock + cache are pre-populated, the
    ``TextEmbedding`` constructor is only reached *after* verification
    passed. Structurally proves the offline-only posture: a cache-miss
    would have raised ``EmbeddingsBootstrapRequired`` before construction.
    """
    from codegenie.rag.embedder import FastembedEmbedder

    cache_dir = tmp_path / "fastembed-cache"
    expected_digest = _seed_synthetic_cache(cache_dir)
    lock = tmp_path / "embeddings_model.lock"
    _write_lock(lock, model_name="BAAI/bge-small-en-v1.5", sha256=expected_digest)

    with patch("fastembed.TextEmbedding", _SpyTextEmbedding):
        FastembedEmbedder(lock_path=lock, cache_dir=cache_dir)

    assert len(_SpyTextEmbedding.instances) == 1
    assert _SpyTextEmbedding.instances[0].model_name == "BAAI/bge-small-en-v1.5"


def test_runtime_init_does_not_construct_session_on_missing_lock(
    tmp_path: Path,
) -> None:
    """AC-7 behavioral — refuse-start branches must not even reach
    ``TextEmbedding(...)``. If they did, fastembed could download
    on a malformed-cache repair attempt — exactly the silent-bootstrap
    failure mode ADR-0007 §Decision forbids."""
    from codegenie.rag.embedder import FastembedEmbedder

    with patch("fastembed.TextEmbedding", _SpyTextEmbedding):
        with pytest.raises(EmbeddingsBootstrapRequired):
            FastembedEmbedder(
                lock_path=tmp_path / "embeddings_model.lock",
                cache_dir=tmp_path / "fastembed-cache",
            )
    assert _SpyTextEmbedding.instances == []


# ---------------------------------------------------------------------------
# AC-8 — typed-error string + attribute coverage
# ---------------------------------------------------------------------------


def test_embedding_model_mismatch_str_includes_kind_both_values_and_runbook(
    tmp_path: Path,
) -> None:
    """AC-8 — ``EmbeddingModelMismatch.__str__`` includes the ``kind``
    discriminator, both ``expected`` and ``found`` values verbatim, and
    the runbook pointer. Tests must read ``exc.kind`` directly so a
    silent fallthrough on the ``kind`` field is caught."""
    err = EmbeddingModelMismatch(kind="sha256", expected="abc123", found="def456")
    message = str(err)
    assert err.kind == "sha256"
    assert err.expected == "abc123"
    assert err.found == "def456"
    assert "sha256" in message
    assert "abc123" in message
    assert "def456" in message
    assert "docs/operations/embeddings.md" in message


def test_embeddings_bootstrap_required_str_names_runbook() -> None:
    """AC-8 — ``EmbeddingsBootstrapRequired`` carries a typed
    ``runbook_url`` attribute and its ``__str__`` contains the literal
    CLI command operators are meant to run."""
    err = EmbeddingsBootstrapRequired(reason="lock file missing")
    message = str(err)
    assert err.runbook_url == "docs/operations/embeddings.md"
    assert "codegenie embeddings bootstrap" in message
    assert "lock file missing" in message


# ---------------------------------------------------------------------------
# AC-9 prep — Protocol is runtime-checkable
# ---------------------------------------------------------------------------


def test_protocol_runtime_checkable_against_fastembed_embedder(
    tmp_path: Path,
) -> None:
    """The Protocol is ``@runtime_checkable``; a concrete adapter
    satisfies ``isinstance(..., Embedder)``."""
    from codegenie.rag.embedder import Embedder, FastembedEmbedder

    cache_dir = tmp_path / "fastembed-cache"
    expected_digest = _seed_synthetic_cache(cache_dir)
    lock = tmp_path / "embeddings_model.lock"
    _write_lock(lock, model_name="BAAI/bge-small-en-v1.5", sha256=expected_digest)

    with patch("fastembed.TextEmbedding", _SpyTextEmbedding):
        emb = FastembedEmbedder(lock_path=lock, cache_dir=cache_dir)
    assert isinstance(emb, Embedder)
