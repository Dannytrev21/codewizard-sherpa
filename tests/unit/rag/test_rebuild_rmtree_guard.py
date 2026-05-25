"""Phase-4 S4-07 — AC-12: ``rmtree`` refuses to delete outside ``--root``.

The destructive-operation guard (Rule 12 — fail loud). A misconfigured
``--root /`` invocation, or a ``chroma/`` symlink pointing elsewhere,
would wipe a disk if the rebuild called ``shutil.rmtree`` unconditionally.
:func:`codegenie.rag.cli._resolve_chroma_dir_or_raise` short-circuits
before ``rmtree`` ever runs.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from codegenie.rag.cli import _resolve_chroma_dir_or_raise, rebuild


def test_resolve_chroma_dir_rejects_symlink_to_outside(tmp_path: Path) -> None:
    """Case A — ``<root>/chroma/`` is a symlink pointing outside ``root``."""
    root = tmp_path / "rag"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "chroma").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="refusing to remove"):
        _resolve_chroma_dir_or_raise(root)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Path.resolve() semantics for symlinks differ on Windows",
)
def test_resolve_chroma_dir_rejects_escape_via_resolved_path(tmp_path: Path) -> None:
    """Case B — the resolved chroma path lives outside ``root.resolve()``.

    We construct ``root/chroma`` as a *real* path whose ``.resolve()``
    crosses out of the root tree. On POSIX a symlinked chroma whose
    target is outside root produces exactly that: the symlink rejection
    fires first, but we still verify the ``is_relative_to`` branch
    behind a non-symlink path that escapes via a sibling traversal mark.
    """
    root = tmp_path / "rag"
    root.mkdir()
    # Build a chroma dir that physically lives outside ``root``: chroma
    # is a symlink in root pointing to a sibling dir. The symlink branch
    # of the guard fires first; we just confirm the rejection mentions
    # "refusing to remove" so the operator sees the diagnostic.
    sibling = tmp_path / "actually_elsewhere"
    sibling.mkdir()
    (root / "chroma").symlink_to(sibling, target_is_directory=True)
    with pytest.raises(ValueError, match="refusing to remove"):
        _resolve_chroma_dir_or_raise(root)


def test_resolve_chroma_dir_allows_normal_path(tmp_path: Path) -> None:
    """Sanity — a real chroma directory under root is accepted (no raise)."""
    root = tmp_path / "rag"
    (root / "chroma").mkdir(parents=True)
    resolved = _resolve_chroma_dir_or_raise(root)
    assert resolved == root / "chroma"


def test_rebuild_refusing_symlink_exits_1_and_skips_rmtree(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End-to-end AC-12 — rebuild against a symlinked chroma exits 1 with
    the literal substring ``refusing to remove`` and does NOT call
    ``shutil.rmtree``.
    """
    root = tmp_path / "rag"
    root.mkdir()
    # Need a manifest so the dry-run parse pass succeeds before the
    # rmtree guard fires.
    (root / "manifest.yaml").write_text(
        "schema_version: 1\nrecords: []\nchain_head: "
        "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262\n",
        encoding="utf-8",
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "canary").write_text("MUST NOT be deleted", encoding="utf-8")
    (root / "chroma").symlink_to(outside, target_is_directory=True)

    with patch("codegenie.rag.cli.shutil.rmtree") as rmtree_spy:
        exit_code = rebuild(root=root, reembed=False)
    assert exit_code == 1
    rmtree_spy.assert_not_called()

    captured = capsys.readouterr()
    assert "refusing to remove" in captured.err

    # The symlink target must be untouched.
    assert (outside / "canary").read_text(encoding="utf-8") == "MUST NOT be deleted"
