"""Unit tests for ``RepoNotesProbe`` (S6-03)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from codegenie.probes.layer_d import repo_notes as rn

from .conftest import _make_context, _make_repo


def test_collect_headings_extracts_h1_h2_h3_only() -> None:
    """AC-6. Mutation caught: matching arbitrary ``#`` prefixes (e.g.,
    inside code fences) would corrupt the heading index — pure helper
    is unit-testable from bytes only."""
    lines = iter([b"# Top\n", b"body\n", b"## Sub\n", b"### Deeper\n", b"plain\n"])
    headings = rn._collect_headings(lines)
    assert headings == ("# Top", "## Sub", "### Deeper")


def test_collect_headings_skips_lines_over_cap_and_continues() -> None:
    """AC-6. Mutation caught: dropping the per-line cap would admit
    pathological notes; the helper must continue past a too-long line."""
    big = b"#" + b" x" * 3000 + b"\n"
    lines = iter([b"# Real\n", big, b"## After\n"])
    headings = rn._collect_headings(lines)
    assert headings == ("# Real", "## After")


def test_repo_notes_happy_path(tmp_path: Path) -> None:
    """AC-6. Mutation caught: not iterating the notes directory."""
    repo = _make_repo(tmp_path)
    notes_dir = repo.root / ".codegenie" / "notes"
    notes_dir.mkdir(parents=True)
    (notes_dir / "alpha.md").write_text("# Alpha\n## A1\n")
    (notes_dir / "beta.md").write_text("# Beta\n")
    ctx = _make_context(tmp_path)
    output = asyncio.run(rn.RepoNotesProbe().run(repo, ctx))
    assert output.confidence == "high"
    slice_ = rn.RepoNotesSlice.model_validate(output.schema_slice)
    assert slice_.notes_dir == ".codegenie/notes"
    paths = [f.path for f in slice_.files]
    assert paths == [".codegenie/notes/alpha.md", ".codegenie/notes/beta.md"]
    assert slice_.files[0].headings == ("# Alpha", "## A1")
    assert slice_.files[0].byte_count > 0
    assert slice_.per_file_errors == ()


def test_repo_notes_marker_absent_low_confidence(tmp_path: Path) -> None:
    """AC-10. Mutation caught: any raise on missing notes dir."""
    repo = _make_repo(tmp_path)
    ctx = _make_context(tmp_path)
    output = asyncio.run(rn.RepoNotesProbe().run(repo, ctx))
    assert output.confidence == "low"
    slice_ = rn.RepoNotesSlice.model_validate(output.schema_slice)
    assert slice_.notes_dir is None
    assert slice_.files == ()
    assert slice_.per_file_errors == ("repo_notes_dir_absent",)


def test_repo_notes_two_runs_byte_identical(tmp_path: Path) -> None:
    """AC-15. Mutation caught: any iteration order from ``os.listdir``."""
    repo = _make_repo(tmp_path)
    notes_dir = repo.root / ".codegenie" / "notes"
    notes_dir.mkdir(parents=True)
    for n in ("c.md", "a.md", "b.md"):
        (notes_dir / n).write_text(f"# {n}\n")
    ctx = _make_context(tmp_path)
    s1 = rn.RepoNotesSlice.model_validate(
        asyncio.run(rn.RepoNotesProbe().run(repo, ctx)).schema_slice
    )
    s2 = rn.RepoNotesSlice.model_validate(
        asyncio.run(rn.RepoNotesProbe().run(repo, ctx)).schema_slice
    )
    assert s1.model_dump_json() == s2.model_dump_json()
    assert [f.path for f in s1.files] == [
        ".codegenie/notes/a.md",
        ".codegenie/notes/b.md",
        ".codegenie/notes/c.md",
    ]


def test_repo_notes_partial_failure_records_cap_breach(tmp_path: Path) -> None:
    """AC-16. Mutation caught: collapsing line-cap breach to low when
    other notes parse cleanly."""
    repo = _make_repo(tmp_path)
    notes_dir = repo.root / ".codegenie" / "notes"
    notes_dir.mkdir(parents=True)
    (notes_dir / "good.md").write_text("# Good\n")
    long_line = "#" + (" x" * 3000) + "\n"
    (notes_dir / "long.md").write_text(long_line + "## After\n")
    ctx = _make_context(tmp_path)
    output = asyncio.run(rn.RepoNotesProbe().run(repo, ctx))
    assert output.confidence == "medium"
    slice_ = rn.RepoNotesSlice.model_validate(output.schema_slice)
    assert "note_line_exceeds_cap" in slice_.per_file_errors
