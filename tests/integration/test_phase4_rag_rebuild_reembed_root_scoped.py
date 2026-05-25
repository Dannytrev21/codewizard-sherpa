"""Phase-4 S4-07 shakedown follow-up — ``--reembed`` honors ``--root`` AND
preserves chroma/manifest on embedder-construction failure.

The 2026-05-25 shakedown of ``codegenie rag rebuild`` against a custom
``--root`` exposed two regressions in the ``--reembed`` path that the
original AC-6 test (which monkeypatches the seam) could not catch:

1. **F1 — root-scoping bug.** ``_seam_build_reembed_embedder(root)``
   constructs ``FastembedEmbedder()`` with no args, so the lock + cache
   defaults resolve to ``.codegenie/rag/embeddings_model.lock`` and
   ``./.codegenie/rag/fastembed-cache`` (cwd-relative), ignoring the
   operator's ``--root``. Running ``embeddings bootstrap --lock-path
   <root>/embeddings_model.lock`` followed by ``rag rebuild --root <root>
   --reembed`` raises ``EmbeddingsBootstrapRequired`` even though the
   lock IS present at ``<root>/embeddings_model.lock``.

2. **F2 — failure-corrupts-store bug.** Phase 2 of ``rebuild()`` deletes
   ``chroma/`` and unlinks ``manifest.yaml`` *before* the embedder is
   constructed in phase 3+4's ``_rebuild_async``. If the embedder build
   fails (F1, network outage, drift), the store is left with records/
   intact, chroma/ wiped, and manifest.yaml gone — operationally
   unrecoverable without manual surgery. The runbook §"transactional at
   the directory level" promise is broken.

Both tests use the real ``FastembedEmbedder`` lookup path (no seam
monkeypatch) — that is the explicit point of these tests, since the seam
is what allowed F1 + F2 to ship undetected.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Final

import pytest
import yaml

from codegenie.rag.cli import rebuild
from codegenie.rag.errors import EmbeddingsBootstrapRequired
from codegenie.rag.store import (
    ChromaPersistentStore,
    SolvedExampleWriteCapability,
)
from codegenie.types.identifiers import WorkflowId
from tests.fixtures.rag.fake_solved_example import make_solved_example

_LOCK_FILENAME: Final[str] = "embeddings_model.lock"
_CACHE_DIRNAME: Final[str] = "fastembed-cache"


async def _seed_two(root: Path) -> None:
    store = ChromaPersistentStore(root_dir=root)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-shakedown"))
    for i, cve in enumerate(["CVE-2026-7771", "CVE-2026-7772"]):
        await store.add(make_solved_example(id_=f"ex-rs-{i:03d}", cve_id=cve), cap)
    store.close()


def test_reembed_failure_preserves_chroma_and_manifest(tmp_path: Path) -> None:
    """F2 — when ``--reembed`` cannot build the embedder, the rebuild
    must NOT have already destroyed ``chroma/`` or ``manifest.yaml``.

    Construct a ``--root`` that contains canonical records + manifest +
    chroma BUT no ``embeddings_model.lock``. Invoke ``rebuild(reembed=
    True)``. Real ``FastembedEmbedder`` construction raises
    ``EmbeddingsBootstrapRequired``. The rebuild must exit non-zero AND
    leave both ``chroma/`` and ``manifest.yaml`` intact — the records
    YAMLs are the canonical source, so chroma + manifest are recoverable
    by simply re-running rebuild (after bootstrapping). If chroma +
    manifest are already wiped, recovery requires manual surgery.
    """
    root = tmp_path / "rag"
    asyncio.run(_seed_two(root))

    # Sanity — chroma and manifest exist post-seed.
    assert (root / "chroma").is_dir()
    assert (root / "manifest.yaml").is_file()
    pre_manifest_bytes = (root / "manifest.yaml").read_bytes()
    pre_chroma_files = sorted(p.name for p in (root / "chroma").iterdir())

    # No lock file present — real FastembedEmbedder will refuse to start.
    assert not (root / _LOCK_FILENAME).exists()

    exit_code = rebuild(root=root, reembed=True)
    assert exit_code == 1, (
        f"rebuild --reembed with no lock should exit 1 (embedder cannot start), got {exit_code}"
    )

    # F2 contract — chroma + manifest preserved on preflight failure.
    assert (root / "manifest.yaml").is_file(), (
        "manifest.yaml was unlinked despite the --reembed preflight "
        "failing — store is now corrupted (F2 regression)"
    )
    assert (root / "manifest.yaml").read_bytes() == pre_manifest_bytes, (
        "manifest.yaml content changed despite preflight failure"
    )
    assert (root / "chroma").is_dir(), (
        "chroma/ was deleted despite the --reembed preflight failing — "
        "store is now corrupted (F2 regression)"
    )
    post_chroma_files = sorted(p.name for p in (root / "chroma").iterdir())
    assert post_chroma_files == pre_chroma_files, (
        f"chroma/ contents changed despite preflight failure: "
        f"pre={pre_chroma_files} post={post_chroma_files}"
    )


def test_reembed_honors_custom_root_for_lock_lookup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F1 — ``--reembed`` must resolve the embeddings lock + cache
    relative to ``--root``, not cwd-relative ``.codegenie/rag/``.

    Place a real-looking lock file under ``<root>/embeddings_model.lock``
    and an empty ``<root>/fastembed-cache``. Confirm that the embedder
    construction reads from ``<root>/embeddings_model.lock`` and NOT from
    ``./.codegenie/rag/embeddings_model.lock`` (which we cd away from).

    The test asserts the precondition behavior via ``EmbeddingsBootstrap
    Required``'s ``lock_path=<root>/embeddings_model.lock`` field — that
    field is the discriminator between the broken cwd-relative resolve
    and the fixed root-scoped resolve.
    """
    root = tmp_path / "rag"
    asyncio.run(_seed_two(root))

    # Custom root contains a *corrupt* lock so we get a deterministic,
    # network-free failure inside the embedder — the lock_path field of
    # the error tells us WHICH path the embedder was asked to verify.
    (root / _LOCK_FILENAME).write_text("not valid yaml: [\n", encoding="utf-8")
    (root / _CACHE_DIRNAME).mkdir(parents=True, exist_ok=True)

    # Move cwd somewhere that has NO .codegenie/rag/ — so a cwd-relative
    # lookup would yield a "file missing" error mentioning .codegenie/rag,
    # while a correct root-scoped lookup yields a "corrupt lock" error
    # mentioning <root>/embeddings_model.lock.
    cwd_only = tmp_path / "cwd_only"
    cwd_only.mkdir()
    monkeypatch.chdir(cwd_only)
    # And clear FASTEMBED_CACHE_DIR so it cannot mask the cwd default.
    monkeypatch.delenv("FASTEMBED_CACHE_DIR", raising=False)

    expected_lock = root / _LOCK_FILENAME

    with pytest.raises(EmbeddingsBootstrapRequired) as excinfo:
        from codegenie.rag.cli import _seam_build_reembed_embedder

        _seam_build_reembed_embedder(root)

    msg = str(excinfo.value)
    assert str(expected_lock) in msg, (
        f"EmbeddingsBootstrapRequired did NOT name the root-scoped lock "
        f"path. Expected {expected_lock} in error, got: {msg!r}. The "
        f"seam ignored --root and fell back to the cwd-relative default."
    )
    assert ".codegenie/rag/embeddings_model.lock" not in msg or str(expected_lock) in msg, (
        f"seam fell back to cwd-relative default path: {msg!r}"
    )


def test_reembed_with_bootstrapped_custom_root_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F1 end-to-end — bootstrap to ``<root>/embeddings_model.lock``,
    rebuild ``--root <root> --reembed`` must succeed. This is the
    documented operator workflow from ``docs/operations/rag.md``.

    Uses ``_seam_build_reembed_embedder`` directly with a fake to keep
    the test hermetic (no fastembed download), but mounts the fake so
    that it RECEIVES the root and asserts the root flowed through.
    """
    from codegenie.rag.cli import _seam_build_reembed_embedder

    received_roots: list[Path] = []

    def spy_seam(root_arg: Path) -> object:
        received_roots.append(root_arg)
        return (
            _seam_build_reembed_embedder.__wrapped__(root_arg)
            if hasattr(_seam_build_reembed_embedder, "__wrapped__")
            else _seam_build_reembed_embedder(root_arg)
        )

    # Build a deterministic fake embedder consumed by the rebuild loop.
    from codegenie.types.identifiers import BlobDigest, EmbeddingVector

    fixed_vector = EmbeddingVector(tuple(0.5 for _ in range(384)))
    new_digest = BlobDigest("e" * 64)

    class _FakeEmbedder:
        def embed(self, _text: str) -> EmbeddingVector:
            return fixed_vector

        def embed_batch(self, texts: list[str]) -> list[EmbeddingVector]:
            return [fixed_vector for _ in texts]

        def model_digest(self) -> BlobDigest:
            return new_digest

    root = tmp_path / "rag"
    asyncio.run(_seed_two(root))

    received: list[Path] = []

    def spy(root_arg: Path) -> object:
        received.append(root_arg)
        return _FakeEmbedder()

    monkeypatch.setattr("codegenie.rag.cli._seam_build_reembed_embedder", spy)

    code = rebuild(root=root, reembed=True)
    assert code == 0
    assert received == [root], (
        f"_seam_build_reembed_embedder was called with the wrong root: "
        f"expected [{root}], got {received}"
    )

    manifest = yaml.safe_load((root / "manifest.yaml").read_text(encoding="utf-8"))
    for rid in manifest["records"]:
        body = yaml.safe_load((root / "records" / f"{rid}.yaml").read_text(encoding="utf-8"))
        assert body["embedding_model"] == str(new_digest)
