"""Unit tests for ``RepoConfigProbe`` (S6-03)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from codegenie.probes.layer_d import repo_config as rc

from .conftest import _make_context, _make_repo


def test_extract_frontmatter_block_returns_bytes_and_offset() -> None:
    """AC-7. Pure helper. Mutation caught: returning the body region as text would
    decode the body — the helper returns bytes and a byte offset only."""
    data = b"---\nfoo: 1\nbar: baz\n---\nbody starts here\nmore body\n"
    fm, body_off = rc._extract_frontmatter_block(data)
    assert fm == b"foo: 1\nbar: baz\n"
    assert body_off > 0
    assert data[body_off:].startswith(b"body starts here")


def test_extract_frontmatter_block_returns_none_when_no_block() -> None:
    """AC-7. Mutation caught: synthesizing a frontmatter from a single ``---``
    line would invent structure that isn't there."""
    fm, off = rc._extract_frontmatter_block(b"# Heading\nbody only\n")
    assert fm is None
    assert off == 0


def test_extract_frontmatter_block_handles_crlf() -> None:
    """AC-7. Mutation caught: silently failing on CRLF newlines."""
    data = b"---\r\nfoo: 1\r\n---\r\nbody\r\n"
    fm, off = rc._extract_frontmatter_block(data)
    assert fm is not None
    assert b"foo: 1" in fm
    assert off > 0


def test_repo_config_happy_path(tmp_path: Path) -> None:
    """AC-7. Mutation caught: not reading the three canonical markers."""
    repo = _make_repo(tmp_path)
    (repo.root / "AGENTS.md").write_text("---\nfoo: 1\n---\nbody bytes here\n")
    (repo.root / "CLAUDE.md").write_text("no frontmatter just body\n")
    gh = repo.root / ".github"
    gh.mkdir()
    (gh / "copilot-instructions.md").write_text("---\nkey: val\n---\nb\n")
    ctx = _make_context(tmp_path)
    output = asyncio.run(rc.RepoConfigProbe().run(repo, ctx))
    assert output.confidence == "high"
    slice_ = rc.RepoConfigSlice.model_validate(output.schema_slice)
    paths = [f.path for f in slice_.files]
    assert paths == [".github/copilot-instructions.md", "AGENTS.md", "CLAUDE.md"]
    by_path = {f.path: f for f in slice_.files}
    assert by_path["AGENTS.md"].frontmatter_keys == ("foo",)
    assert by_path["CLAUDE.md"].frontmatter_keys == ()
    assert by_path["CLAUDE.md"].has_body is True


def test_repo_config_markers_absent_low(tmp_path: Path) -> None:
    """AC-10. Mutation caught: any raise on missing config markers."""
    repo = _make_repo(tmp_path)
    ctx = _make_context(tmp_path)
    output = asyncio.run(rc.RepoConfigProbe().run(repo, ctx))
    assert output.confidence == "low"
    slice_ = rc.RepoConfigSlice.model_validate(output.schema_slice)
    assert slice_.files == ()
    assert slice_.per_file_errors == ("repo_config_markers_absent",)


def test_repo_config_malformed_frontmatter_yields_medium(tmp_path: Path) -> None:
    """AC-16 / AC-17. Mutation caught: collapsing partial-failure to low —
    a malformed-frontmatter marker should still surface as medium when a
    sibling parses cleanly."""
    repo = _make_repo(tmp_path)
    (repo.root / "AGENTS.md").write_text("---\nfoo: 1\n---\nbody\n")
    (repo.root / "CLAUDE.md").write_text("---\n: : : bad : yaml\n---\nbody\n")
    ctx = _make_context(tmp_path)
    output = asyncio.run(rc.RepoConfigProbe().run(repo, ctx))
    assert output.confidence == "medium"
    slice_ = rc.RepoConfigSlice.model_validate(output.schema_slice)
    assert "frontmatter_malformed" in slice_.per_file_errors


def test_repo_config_oversize_file_recorded(tmp_path: Path) -> None:
    """AC-7. Mutation caught: silently truncating an oversize config marker
    would discard the breach signal."""
    repo = _make_repo(tmp_path)
    (repo.root / "AGENTS.md").write_text("x" * (70 * 1024))
    ctx = _make_context(tmp_path, config_overrides={"repo_config.max_bytes": 1024})
    output = asyncio.run(rc.RepoConfigProbe().run(repo, ctx))
    slice_ = rc.RepoConfigSlice.model_validate(output.schema_slice)
    assert "file_exceeds_cap" in slice_.per_file_errors


def test_repo_config_two_runs_byte_identical(tmp_path: Path) -> None:
    """AC-15. Determinism on the sorted file list."""
    repo = _make_repo(tmp_path)
    (repo.root / "AGENTS.md").write_text("body\n")
    (repo.root / "CLAUDE.md").write_text("body\n")
    ctx = _make_context(tmp_path)
    s1 = rc.RepoConfigSlice.model_validate(
        asyncio.run(rc.RepoConfigProbe().run(repo, ctx)).schema_slice
    )
    s2 = rc.RepoConfigSlice.model_validate(
        asyncio.run(rc.RepoConfigProbe().run(repo, ctx)).schema_slice
    )
    assert s1.model_dump_json() == s2.model_dump_json()
