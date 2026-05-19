"""S2-03 AC-11 — binary-mode reads + ``__pycache__`` / ``*.pyc`` skip.

These witnesses pin the loader's cross-platform invariance. A maintainer
who flips the file read to text mode (silently CRLF→LF on Windows) breaks
``test_digest_is_bytes_mode``; a maintainer who removes the
``__pycache__`` filter breaks the pyc-skip tests.
"""

from __future__ import annotations

from pathlib import Path

from codegenie.plugins.loader import compute_plugin_tree_digest


def test_digest_is_bytes_mode(tmp_path: Path) -> None:
    """LF vs CRLF byte content produces DIFFERENT digests.

    The opposite mutant — text-mode read normalizing CRLF→LF — would make
    the two digests equal and fail this test loudly.
    """
    lf_dir = tmp_path / "lf"
    crlf_dir = tmp_path / "crlf"
    lf_dir.mkdir()
    crlf_dir.mkdir()
    (lf_dir / "f.txt").write_bytes(b"line1\nline2\n")
    (crlf_dir / "f.txt").write_bytes(b"line1\r\nline2\r\n")
    lf_digest = compute_plugin_tree_digest(lf_dir).unwrap()
    crlf_digest = compute_plugin_tree_digest(crlf_dir).unwrap()
    assert lf_digest != crlf_digest


def test_digest_skips_pycache_directory(tmp_path: Path) -> None:
    """Populating ``__pycache__/foo.cpython-311.pyc`` does NOT change the digest."""
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "real.py").write_text("# real content\n", encoding="utf-8")
    before = compute_plugin_tree_digest(plugin_dir).unwrap()

    cache_dir = plugin_dir / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "foo.cpython-311.pyc").write_bytes(b"bytecode")
    after = compute_plugin_tree_digest(plugin_dir).unwrap()
    assert before == after


def test_digest_skips_top_level_pyc_files(tmp_path: Path) -> None:
    """Top-level ``leaked.pyc`` does NOT change the digest."""
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    (plugin_dir / "real.py").write_text("# real content\n", encoding="utf-8")
    before = compute_plugin_tree_digest(plugin_dir).unwrap()

    (plugin_dir / "leaked.pyc").write_bytes(b"leaked bytecode")
    after = compute_plugin_tree_digest(plugin_dir).unwrap()
    assert before == after
