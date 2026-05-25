"""Phase-4 S4-01 — ``codegenie embeddings bootstrap`` CLI behavior.

The CLI body lives in :mod:`codegenie.rag.cli`; tests invoke
:func:`codegenie.rag.cli.bootstrap` directly so the assertions can read
the integer exit code without ``sys.exit`` interaction. The
``fastembed.TextEmbedding`` constructor is patched with a spy that
populates a synthetic cache directory — this exercises the lock-write /
no-op / drift / upgrade branches without downloading real weights.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from codegenie.rag.embedder import _compute_dir_digest
from codegenie.types.identifiers import ModelId


def _digest_dir(root: Path) -> str:
    """Mirror of the AC-6 algorithm — duplicated so a silent change in
    the implementation's algorithm is caught by these tests independently."""
    hasher = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix().encode("utf-8")
        hasher.update(rel)
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


class _SpyTextEmbedding:
    """Test double for ``fastembed.TextEmbedding`` that lays down a
    synthetic, multi-file model directory under ``cache_dir`` so the
    directory-digest algorithm has something realistic to hash.

    Tests can adjust :attr:`payload_factory` to simulate model-upgrade
    drift (different bytes per model_name) or corruption (different
    bytes on the same model_name)."""

    payload_factory: Callable[[str], dict[str, bytes]] = staticmethod(
        lambda model_name: {
            "model.onnx": f"weights-for-{model_name}".encode(),
            "tokenizer.json": b'{"version":"1.0"}',
            "config.json": f'{{"name":"{model_name}"}}'.encode(),
        }
    )

    instances: list[_SpyTextEmbedding] = []  # noqa: RUF012

    def __init__(self, model_name: str, cache_dir: str | None = None, **_: object) -> None:
        self.model_name = model_name
        cache_path = Path(cache_dir) if cache_dir else Path.cwd()
        cache_path.mkdir(parents=True, exist_ok=True)
        # Lay down the per-model subdirectory so the digest covers
        # rel-paths that differ across model_names — a model upgrade
        # therefore drifts the digest deterministically.
        safe = model_name.replace("/", "__")
        model_dir = cache_path / safe
        model_dir.mkdir(parents=True, exist_ok=True)
        for fname, body in type(self).payload_factory(model_name).items():
            (model_dir / fname).write_bytes(body)
        _SpyTextEmbedding.instances.append(self)

    def embed(self, texts: Iterable[str], **_: object) -> Iterable[object]:
        raise NotImplementedError


@pytest.fixture(autouse=True)
def _reset_spy() -> None:
    _SpyTextEmbedding.instances.clear()
    # Reset payload_factory if a previous test rebound it.
    _SpyTextEmbedding.payload_factory = staticmethod(
        lambda model_name: {
            "model.onnx": f"weights-for-{model_name}".encode(),
            "tokenizer.json": b'{"version":"1.0"}',
            "config.json": f'{{"name":"{model_name}"}}'.encode(),
        }
    )


def _load_lock(lock_path: Path) -> dict[str, str]:
    return yaml.safe_load(lock_path.read_text())


# ---------------------------------------------------------------------------
# First write + idempotent re-run
# ---------------------------------------------------------------------------


def test_first_invocation_writes_lock_with_sorted_yaml(tmp_path: Path) -> None:
    """First write emits a sorted-key YAML lock with a trailing newline.
    The on-disk shape is part of the AC-6 contract."""
    from codegenie.rag.cli import bootstrap

    cache = tmp_path / "fastembed-cache"
    lock = tmp_path / "embeddings_model.lock"

    with patch("fastembed.TextEmbedding", _SpyTextEmbedding):
        code = bootstrap(
            model_name=ModelId("BAAI/bge-small-en-v1.5"),
            lock_path=lock,
            cache_dir=cache,
        )
    assert code == 0
    assert lock.is_file()
    text = lock.read_text()
    # sorted keys → model_name appears before sha256.
    assert text.index("model_name") < text.index("sha256")
    assert text.endswith("\n")
    payload = _load_lock(lock)
    assert payload["model_name"] == "BAAI/bge-small-en-v1.5"
    assert payload["sha256"] == _digest_dir(cache)


def test_idempotent_rerun_does_not_rewrite_lock(tmp_path: Path) -> None:
    """AC-6 — same model + same on-disk digest = no-op. The lock-write
    seam is NOT invoked; the file bytes are byte-identical before/after
    (mtime is too coarse to be a reliable no-op signal — Rule 12)."""
    import codegenie.rag.cli as rag_cli

    cache = tmp_path / "fastembed-cache"
    lock = tmp_path / "embeddings_model.lock"

    with patch("fastembed.TextEmbedding", _SpyTextEmbedding):
        rag_cli.bootstrap(
            model_name=ModelId("BAAI/bge-small-en-v1.5"),
            lock_path=lock,
            cache_dir=cache,
        )
        first_bytes = lock.read_bytes()
        with patch.object(rag_cli, "_seam_write_lock") as spy_write:
            code = rag_cli.bootstrap(
                model_name=ModelId("BAAI/bge-small-en-v1.5"),
                lock_path=lock,
                cache_dir=cache,
            )
        assert code == 0
        spy_write.assert_not_called()
    assert lock.read_bytes() == first_bytes


def test_model_upgrade_rewrites_lock_and_warns(tmp_path: Path) -> None:
    """AC-6 — operator-initiated model upgrade overwrites the lock with
    the new ``{model_name, sha256}``. This is the arch edge-case #3
    workflow — a CLI that exit-1s on every change makes the documented
    upgrade impossible."""
    import codegenie.rag.cli as rag_cli

    cache = tmp_path / "fastembed-cache"
    lock = tmp_path / "embeddings_model.lock"

    with patch("fastembed.TextEmbedding", _SpyTextEmbedding):
        # Land a lock for model A.
        rag_cli.bootstrap(
            model_name=ModelId("BAAI/bge-small-en-v1.5"),
            lock_path=lock,
            cache_dir=cache,
        )
        small_payload = _load_lock(lock)
        # Upgrade to model B.
        code = rag_cli.bootstrap(
            model_name=ModelId("BAAI/bge-large-en-v1.5"),
            lock_path=lock,
            cache_dir=cache,
        )
        assert code == 0
        upgraded = _load_lock(lock)
    assert upgraded["model_name"] == "BAAI/bge-large-en-v1.5"
    assert upgraded["sha256"] != small_payload["sha256"]
    # New digest covers the post-upgrade cache contents (both models
    # remain on disk — fastembed leaves the old cache intact).
    assert upgraded["sha256"] == _digest_dir(cache)


def test_same_model_drift_exits_1_and_preserves_lock(tmp_path: Path) -> None:
    """AC-6 — same-model digest drift exits 1 and the lock is NOT
    rewritten so the operator can investigate cache tampering."""
    import codegenie.rag.cli as rag_cli

    cache = tmp_path / "fastembed-cache"
    lock = tmp_path / "embeddings_model.lock"

    with patch("fastembed.TextEmbedding", _SpyTextEmbedding):
        rag_cli.bootstrap(
            model_name=ModelId("BAAI/bge-small-en-v1.5"),
            lock_path=lock,
            cache_dir=cache,
        )
    pre_drift = lock.read_bytes()
    # Tamper with a cached file — simulates corruption / supply-chain
    # attack post-bootstrap.
    tampered = cache / "BAAI__bge-small-en-v1.5" / "model.onnx"
    tampered.write_bytes(b"tampered-bytes")

    # Re-run bootstrap with the same model. The spy will OVERWRITE the
    # tampered file back to its expected payload, so to keep the cache
    # tampered we run the bootstrap with a spy that does not re-seed.
    class _NoSeedSpy(_SpyTextEmbedding):
        def __init__(self, model_name: str, cache_dir: str | None = None, **_: object) -> None:
            # Bypass the parent's directory seeding so the tampered
            # bytes survive into the digest computation.
            self.model_name = model_name
            _SpyTextEmbedding.instances.append(self)

    with patch("fastembed.TextEmbedding", _NoSeedSpy):
        code = rag_cli.bootstrap(
            model_name=ModelId("BAAI/bge-small-en-v1.5"),
            lock_path=lock,
            cache_dir=cache,
        )
    assert code == 1
    assert lock.read_bytes() == pre_drift  # lock NOT rewritten


def test_bootstrap_no_weights_exits_1(tmp_path: Path) -> None:
    """Defensive — if the fastembed constructor returns without
    populating the cache (broken install, offline mode), exit 1 rather
    than write a zero-file digest into the lock."""
    import codegenie.rag.cli as rag_cli

    cache = tmp_path / "fastembed-cache"
    lock = tmp_path / "embeddings_model.lock"

    class _NoSeedSpy:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

    with patch("fastembed.TextEmbedding", _NoSeedSpy):
        code = rag_cli.bootstrap(
            model_name=ModelId("BAAI/bge-small-en-v1.5"),
            lock_path=lock,
            cache_dir=cache,
        )
    assert code == 1
    assert not lock.exists()


def test_compute_dir_digest_changes_on_tokenizer_swap(tmp_path: Path) -> None:
    """AC-6 — a directory digest must be sensitive to tokenizer-config
    changes (the precise drift the single-file sha256 algorithm would
    miss). This pins the algorithm's coverage of all files, not just
    ``model.onnx``."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    for root in (a, b):
        root.mkdir()
        (root / "model.onnx").write_bytes(b"same-weights")
        (root / "tokenizer.json").write_bytes(b'{"vocab_size":30522}')
    # Mutate only tokenizer.json in `b`.
    (b / "tokenizer.json").write_bytes(b'{"vocab_size":30523}')
    assert _compute_dir_digest(a) != _compute_dir_digest(b)


def test_compute_dir_digest_changes_on_file_rename(tmp_path: Path) -> None:
    """AC-6 — the algorithm hashes ``rel_path + body``, so renaming
    ``model.onnx`` → ``weights.onnx`` (same bytes) drifts the digest.
    Without that, a rename inside the cache would be invisible."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    for root in (a, b):
        root.mkdir()
    (a / "model.onnx").write_bytes(b"weights")
    (b / "weights.onnx").write_bytes(b"weights")
    assert _compute_dir_digest(a) != _compute_dir_digest(b)
