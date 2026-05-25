"""Phase-4 S4-07 — AC-8: corrupt YAML aborts BEFORE chromadb is touched.

The dry-run-parse-first pass (Implementation Outline §2) is what makes
the default-mode rebuild transactional at the directory level. This test
seeds a sentinel under ``<root>/chroma/`` before invoking rebuild on a
deliberately corrupted record; the sentinel must still be present after
the exit-1 abort. A rebuild that deletes chroma first and parses second
would lose the sentinel — the assertion catches that mutant.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Final

import pytest

from codegenie.rag.cli import rebuild
from codegenie.rag.store import (
    ChromaPersistentStore,
    SolvedExampleWriteCapability,
)
from codegenie.types.identifiers import WorkflowId
from tests.fixtures.rag.fake_solved_example import make_solved_example

_PRE_REBUILD_SENTINEL: Final[str] = "_pre_rebuild_sentinel"


async def _seed_three(root: Path) -> None:
    store = ChromaPersistentStore(root_dir=root)
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-corrupt"))
    for i, cve in enumerate(["CVE-2026-1", "CVE-2026-2", "CVE-2026-3"]):
        await store.add(make_solved_example(id_=f"ex-{i:03d}", cve_id=cve), cap)
    store.close()


def test_rag_rebuild_corrupt_yaml_aborts_before_chromadb_touch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """AC-8 — corrupt one record YAML; rebuild exits 1, stderr names the
    offending path, and the pre-rebuild ``chroma/`` sentinel still exists."""
    root = tmp_path / "rag"
    asyncio.run(_seed_three(root))

    # Corrupt one record file with non-UTF-8 garbage.
    target_yaml = root / "records" / "ex-001.yaml"
    target_yaml.write_bytes(b"\xff\xff malformed not even yaml")

    # Seed the chroma/ sentinel.
    sentinel = root / "chroma" / _PRE_REBUILD_SENTINEL
    sentinel.write_text("pre-rebuild sentinel", encoding="utf-8")

    exit_code = rebuild(root=root, reembed=False)
    assert exit_code == 1

    captured = capsys.readouterr()
    assert "ex-001.yaml" in captured.err, (
        f"stderr did not name the offending YAML path verbatim: {captured.err!r}"
    )

    # Sentinel must still exist — the dry-run pass aborted BEFORE rmtree.
    assert sentinel.exists(), (
        "shutil.rmtree ran before the dry-run parse — pre-rebuild sentinel "
        "was destroyed; AC-8 transactional contract broken"
    )
