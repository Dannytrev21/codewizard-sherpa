"""Phase-4 S4-07 — AC-5/AC-6 golden idempotence tests for ``codegenie rag rebuild``.

The load-bearing contract: ``store.digest() == manifest.chain_head`` is
byte-identical across a rebuild cycle (ADR-0016 content-addressed
derived-index). Catches the "rebuild reshuffles records" and "rebuild
drops records" mutants — both would change the rolling BLAKE3 hex.

AC-5 covers the default-mode happy path with a sentinel-resistant
``rmtree`` check; AC-6 covers ``--reembed`` with a "different" model
digest, assertions over *what changed* (not just that something changed),
and an idempotent second-run check.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Final

import pytest
import yaml

from codegenie.rag.cli import rebuild
from codegenie.rag.store import ChromaPersistentStore
from codegenie.types.identifiers import (
    BlobDigest,
    EmbeddingVector,
    WorkflowId,
)
from tests.fixtures.rag.fake_solved_example import make_solved_example

_PRE_REBUILD_SENTINEL: Final[str] = "_pre_rebuild_sentinel"


async def _seed_three_records_async(root: Path) -> tuple[str, str]:
    """Helper — seed three records and return (pre_digest, pre_chain_head)."""
    from codegenie.rag.store import SolvedExampleWriteCapability

    store = ChromaPersistentStore(root_dir=root)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-rebuild"))
    for i, cve in enumerate(["CVE-2026-1111", "CVE-2026-2222", "CVE-2026-3333"]):
        await store.add(
            make_solved_example(id_=f"ex-{i:03d}", cve_id=cve),
            cap,
        )
    pre_digest = str(store.digest())
    manifest = yaml.safe_load((root / "manifest.yaml").read_text(encoding="utf-8"))
    pre_chain_head = str(manifest["chain_head"])
    store.close()
    assert pre_digest == pre_chain_head, "S4-04 contract: digest equals chain_head"
    return pre_digest, pre_chain_head


def test_rag_rebuild_reproduces_byte_identical_digest(tmp_path: Path) -> None:
    """AC-5 — Default-mode rebuild reproduces the chain head byte-identically.

    The sentinel under ``<root>/chroma/`` proves the ``rmtree`` actually
    ran — a rebuild that silently re-adds on top of the existing chromadb
    would leave the sentinel behind and fail this assertion.

    Sync test function: ``rebuild()`` owns an ``asyncio.run`` boundary
    internally; calling it from an outer event loop raises
    ``RuntimeError: asyncio.run() cannot be called from a running event
    loop``. Per Notes §2, tests own the sync/async boundary themselves.
    """
    root = tmp_path / "rag"
    pre_digest, pre_chain_head = asyncio.run(_seed_three_records_async(root))

    # AC-5 sentinel: prove rmtree ran. Write under chroma/ AFTER seeding
    # but before invoking rebuild — store.close() above released chromadb's
    # handle so we can drop a file alongside the sqlite.
    sentinel = root / "chroma" / _PRE_REBUILD_SENTINEL
    sentinel.write_text("pre-rebuild sentinel", encoding="utf-8")

    exit_code = rebuild(root=root, reembed=False)
    assert exit_code == 0

    # Sentinel must be gone — rmtree wiped the directory wholesale (AC-4).
    assert not sentinel.exists(), (
        "shutil.rmtree was skipped — the pre-rebuild sentinel survived; "
        "the corruption-recovery contract (AC-4) is broken"
    )
    assert (root / "chroma").exists(), "chroma/ must be recreated after rebuild"
    chroma_contents = list((root / "chroma").rglob("*"))
    assert chroma_contents, "rebuilt chroma/ must be non-empty"

    reopened = ChromaPersistentStore(root_dir=root)
    try:
        post_digest = str(reopened.digest())
    finally:
        reopened.close()
    manifest = yaml.safe_load((root / "manifest.yaml").read_text(encoding="utf-8"))
    post_chain_head = str(manifest["chain_head"])

    assert post_digest == pre_digest, (
        "rebuild MUST reproduce the chain head byte-identically "
        f"(pre={pre_digest!r}, post={post_digest!r})"
    )
    assert post_chain_head == pre_chain_head


def test_rag_rebuild_reembed_updates_model_and_vectors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-6 — ``--reembed`` updates every record's ``embedding_model`` to the
    new digest, vectors stay length-384, and the second ``--reembed`` run
    is idempotent (chain head unchanged on the second pass).

    Asserts *what changed*, not just *that* it changed (validator
    hardening — a bare ``v2 != v1`` would also pass on a record reorder
    or a dropped field; the per-record post-conditions catch those).
    """
    root = tmp_path / "rag"
    _, pre_chain_head_v1 = asyncio.run(_seed_three_records_async(root))

    # Inject a deterministic fake embedder via the module-level seam.
    new_digest = BlobDigest("d" * 64)
    fixed_vector = EmbeddingVector(tuple(0.25 for _ in range(384)))

    class _FakeEmbedder:
        def embed(self, _text: str) -> EmbeddingVector:
            return fixed_vector

        def embed_batch(self, texts: list[str]) -> list[EmbeddingVector]:
            return [fixed_vector for _ in texts]

        def model_digest(self) -> BlobDigest:
            return new_digest

    monkeypatch.setattr(
        "codegenie.rag.cli._seam_build_reembed_embedder",
        lambda _root: _FakeEmbedder(),
    )

    # First reembed run.
    code1 = rebuild(root=root, reembed=True)
    assert code1 == 0

    manifest_v2 = yaml.safe_load((root / "manifest.yaml").read_text(encoding="utf-8"))
    chain_head_v2 = str(manifest_v2["chain_head"])
    assert chain_head_v2 != pre_chain_head_v1, (
        "reembed changed canonical YAML bytes — chain head MUST move"
    )

    # Per-record post-conditions — every YAML now carries the new model
    # digest and the new fixed vector length.
    record_files = sorted((root / "records").glob("*.yaml"))
    assert len(record_files) == 3
    for rf in record_files:
        body = yaml.safe_load(rf.read_text(encoding="utf-8"))
        assert body["embedding_model"] == str(new_digest), (
            f"record {rf.name} did not adopt the new embedding_model digest"
        )
        assert len(body["embedding_vector"]) == 384, (
            f"record {rf.name} embedding_vector lost the 384-element shape"
        )

    # Second reembed run — idempotent: same text + same embedder → same vectors.
    code2 = rebuild(root=root, reembed=True)
    assert code2 == 0
    manifest_v3 = yaml.safe_load((root / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest_v3["chain_head"] == chain_head_v2, (
        "second --reembed run was not idempotent — chain head moved a second time"
    )
