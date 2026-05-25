"""Phase-4 S4-07 — AC-7: missing manifest exits 2, no chromadb side effects."""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.rag.cli import rebuild


def test_rag_rebuild_missing_manifest_exits_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Empty ``<root>/`` — exit 2, stderr names the missing manifest and
    points at the operations doc; chromadb directory is NOT created."""
    root = tmp_path / "rag"
    root.mkdir(parents=True, exist_ok=True)

    exit_code = rebuild(root=root, reembed=False)
    assert exit_code == 2

    captured = capsys.readouterr()
    assert "no manifest.yaml found" in captured.err
    assert "docs/operations/rag.md" in captured.err

    # AC-7 — chromadb directory NOT created on missing-manifest abort.
    assert not (root / "chroma").exists(), (
        "rebuild created chroma/ on missing manifest — should be a no-op"
    )
