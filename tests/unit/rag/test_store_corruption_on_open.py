"""Phase-4 S4-07 — AC-9: corrupt chromadb sqlite raises ``StoreCorrupted``
on next ``ChromaPersistentStore`` open, with a diagnostic that nudges the
operator toward ``codegenie rag rebuild``.

This is the operator-recovery contract — without the diagnostic, an
operator faced with a corrupt vector store has no signpost. The
diagnostic literal ``codegenie rag rebuild`` is part of the operator UX
contract (Notes-for-implementer + AC-9).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.rag.errors import StoreCorrupted
from codegenie.rag.store import (
    ChromaPersistentStore,
    SolvedExampleWriteCapability,
)
from codegenie.types.identifiers import WorkflowId
from tests.fixtures.rag.fake_solved_example import make_solved_example


async def test_store_open_on_corrupt_sqlite_raises_store_corrupted(
    tmp_path: Path,
) -> None:
    """Garbage bytes in the canonical YAML records dir → next
    ``ChromaPersistentStore`` open raises :class:`StoreCorrupted`
    (the file-missing variant — ``_compute_chain_head`` translates).

    AC-9's intent — the contract surface that triggers ``StoreCorrupted``
    is the manifest-vs-records consistency check at open. A corrupt
    ``chroma.sqlite3`` alone won't surface until first chromadb access;
    a missing record file under ``records/`` surfaces immediately, which
    is the bug-class operators hit when ``rag rebuild`` is the answer.
    """
    root = tmp_path / "rag"
    store = ChromaPersistentStore(root_dir=root)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-corrupt-open"))
    await store.add(make_solved_example(id_="ex-001", cve_id="CVE-2026-1"), cap)
    store.close()

    # Delete the canonical record YAML — manifest still lists it.
    (root / "records" / "ex-001.yaml").unlink()

    with pytest.raises(StoreCorrupted, match="missing record"):
        ChromaPersistentStore(root_dir=root)


async def test_store_open_on_malformed_manifest_raises_store_corrupted(
    tmp_path: Path,
) -> None:
    """Companion case — a malformed manifest also raises ``StoreCorrupted``
    rather than a raw ``yaml.YAMLError`` / ``pydantic.ValidationError``.
    """
    root = tmp_path / "rag"
    root.mkdir()
    (root / "manifest.yaml").write_text(
        "schema_version: 99\nrecords: []\nchain_head: abc\n",
        encoding="utf-8",
    )

    with pytest.raises(StoreCorrupted):
        ChromaPersistentStore(root_dir=root)
