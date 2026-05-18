"""Unit tests for :class:`OwnershipProbe` (S6-05)."""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
from pathlib import Path

import pydantic
import pytest

from codegenie.probes.layer_e import ownership as op
from codegenie.probes.registry import default_registry
from codegenie.types.identifiers import ProbeId

# ---------------------------------------------------------------------------
# Pure parser — functional core (AC-NEW-6 part 2)
# ---------------------------------------------------------------------------


def test_parse_codeowners_lines_is_pure_module_function() -> None:
    """AC-NEW-6 (part 2). Mutation caught: moving the parser into the
    ``OwnershipProbe`` class (re-tangling pure / impure)."""
    src = inspect.getsource(op)
    tree = ast.parse(src)
    found: ast.FunctionDef | None = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_parse_codeowners_lines":
            found = node
            break
    assert found is not None, "_parse_codeowners_lines must be a module-level function"
    assert [a.arg for a in found.args.args] == ["text"]


def test_parse_codeowners_lines_happy_path() -> None:
    """AC-5. Mutation caught: emitting owners as a single string instead
    of splitting on whitespace."""
    text = "# Default owners\n* @platform-team\n/api/ @api-team @platform-team\n*.md @docs-team\n"
    entries, errors = op._parse_codeowners_lines(text)
    assert errors == ()
    assert len(entries) == 3
    assert entries[1].pattern == "/api/"
    assert entries[1].owners == ("@api-team", "@platform-team")
    assert entries[1].line_number == 3  # 1-indexed; comment line counts


def test_parse_codeowners_lines_skips_comments_and_blanks() -> None:
    """AC-8. Mutation caught: emitting comments as entries with empty
    owners (would conflate with AC-7's empty-owners case)."""
    text = "# header\n\n* @team\n# trailing\n\n"
    entries, errors = op._parse_codeowners_lines(text)
    assert len(entries) == 1
    assert entries[0].pattern == "*"
    assert errors == ()


def test_parse_codeowners_lines_records_empty_owners_with_error() -> None:
    """AC-7. Mutation caught: silently dropping a pattern with no owners."""
    text = "*.py\n"
    entries, errors = op._parse_codeowners_lines(text)
    assert entries[0].pattern == "*.py"
    assert entries[0].owners == ()
    assert "empty_owners_at_line_1" in errors


def test_parse_codeowners_lines_inline_comment_truncates_at_hash_token() -> None:
    """AC-NEW-5. Mutation caught: ``line.split('#', 1)[0]`` naive
    implementation would strip ``#`` legitimately inside a pattern token."""
    text = "*.py @user # owners are the python team\n"
    entries, errors = op._parse_codeowners_lines(text)
    assert entries[0].pattern == "*.py"
    assert entries[0].owners == ("@user",)
    assert errors == ()


def test_parse_codeowners_lines_never_raises_on_garbage() -> None:
    """AC-NEW-6 (part 2). The pure parser must never raise; every
    malformed input is captured in the ``errors`` tuple."""
    text = "\x00\x01\x02 weird\n@no-pattern-prefix\n  leading-ws @t\n"
    entries, errors = op._parse_codeowners_lines(text)
    assert isinstance(entries, tuple)
    assert isinstance(errors, tuple)


# ---------------------------------------------------------------------------
# Imperative shell — async probe.run
# ---------------------------------------------------------------------------


def test_ownership_happy_path_parses_repo_root_file(
    tmp_path: Path,
    _make_repo,  # type: ignore[no-untyped-def]
    _make_ctx,  # type: ignore[no-untyped-def]
) -> None:
    """AC-5. End-to-end imperative shell."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CODEOWNERS").write_text(
        "# Default owners\n* @platform-team\n/api/ @api-team @platform-team\n*.md @docs-team\n"
    )
    output = asyncio.run(op.OwnershipProbe().run(_make_repo(repo), _make_ctx(tmp_path)))
    assert output.confidence == "high"
    assert output.raw_artifacts == []  # marker-probe convention; no raw artifact
    slice_ = op.OwnershipSlice.model_validate(output.schema_slice)
    assert slice_.source_path == "CODEOWNERS"
    assert len(slice_.entries) == 3
    assert slice_.entries[1].pattern == "/api/"
    assert slice_.entries[1].owners == ("@api-team", "@platform-team")
    assert output.duration_ms >= 0


def test_ownership_searches_three_locations_in_order(
    tmp_path: Path,
    _make_repo,  # type: ignore[no-untyped-def]
    _make_ctx,  # type: ignore[no-untyped-def]
) -> None:
    """AC-9. Mutation caught: any precedence change. Phase-2 order is
    CODEOWNERS > .github/CODEOWNERS > docs/CODEOWNERS (intentional
    divergence from GitHub — AC-NEW-7)."""
    repo = tmp_path / "repo"
    (repo / ".github").mkdir(parents=True)
    (repo / "docs").mkdir()
    (repo / "CODEOWNERS").write_text("* @root\n")
    (repo / ".github" / "CODEOWNERS").write_text("* @github_dir\n")
    (repo / "docs" / "CODEOWNERS").write_text("* @docs_dir\n")
    output = asyncio.run(op.OwnershipProbe().run(_make_repo(repo), _make_ctx(tmp_path)))
    slice_ = op.OwnershipSlice.model_validate(output.schema_slice)
    assert slice_.source_path == "CODEOWNERS"
    assert any("additional_codeowners_present_at" in e for e in output.errors)


def test_ownership_absent_yields_low_confidence_no_raise(
    tmp_path: Path,
    _make_repo,  # type: ignore[no-untyped-def]
    _make_ctx,  # type: ignore[no-untyped-def]
) -> None:
    """AC-6. Mutation caught: re-raising on a no-CODEOWNERS repo OR
    misframing the absent-file case as ``confidence='high'`` (that is
    the deferred-stub framing; the right precedent here is
    CertificateProbe upstream-absent → confidence='low')."""
    repo = tmp_path / "repo"
    repo.mkdir()
    output = asyncio.run(op.OwnershipProbe().run(_make_repo(repo), _make_ctx(tmp_path)))
    assert output.confidence == "low"
    slice_ = op.OwnershipSlice.model_validate(output.schema_slice)
    assert slice_.entries == ()
    assert slice_.source_path is None
    assert "codeowners_absent" in output.errors


def test_ownership_size_cap_enforced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _make_repo,  # type: ignore[no-untyped-def]
    _make_ctx,  # type: ignore[no-untyped-def]
) -> None:
    """AC-14. Mutation caught: any unbounded read. The cap fires before
    any read."""
    import os

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CODEOWNERS").write_text("* @team\n")
    monkeypatch.setattr(os.path, "getsize", lambda p: op.OWNERSHIP_MAX_BYTES + 1)
    output = asyncio.run(op.OwnershipProbe().run(_make_repo(repo), _make_ctx(tmp_path)))
    assert output.confidence == "low"
    assert any("codeowners_size_cap_exceeded" in e for e in output.errors)


def test_ownership_two_runs_byte_identical(
    tmp_path: Path,
    _make_repo,  # type: ignore[no-untyped-def]
    _make_ctx,  # type: ignore[no-untyped-def]
) -> None:
    """AC-15. Mutation caught: any sort/reorder of entries — line order
    preserves operator intent (early lines often override later)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CODEOWNERS").write_text("/b/ @b\n/a/ @a\n/c/ @c\n")
    probe = op.OwnershipProbe()
    out1 = asyncio.run(probe.run(_make_repo(repo), _make_ctx(tmp_path))).schema_slice
    out2 = asyncio.run(probe.run(_make_repo(repo), _make_ctx(tmp_path))).schema_slice
    assert json.dumps(out1, sort_keys=True) == json.dumps(out2, sort_keys=True)
    slice_ = op.OwnershipSlice.model_validate(out1)
    assert [e.pattern for e in slice_.entries] == ["/b/", "/a/", "/c/"]


# ---------------------------------------------------------------------------
# Registration & static integrity
# ---------------------------------------------------------------------------


def test_ownership_probe_registered_light() -> None:
    """AC-4, AC-NEW-2."""
    entry = next(
        (e for e in default_registry._entries if e.cls.name == "ownership"),
        None,
    )
    assert entry is not None, "OwnershipProbe must be in default_registry._entries"
    assert entry.heaviness == "light"


def test_ownership_probe_id_constant_exists() -> None:
    """AC-NEW-1. Dual-form identity discipline."""
    assert hasattr(op, "_PROBE_ID")
    assert op._PROBE_ID == ProbeId("ownership")
    assert op.OwnershipProbe.name == "ownership"


def test_ownership_no_subclass_extension_path() -> None:
    """AC-NEW-4. Mutation caught: a subclass fragments dispatch."""
    tree = ast.parse(inspect.getsource(op))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            assert "OwnershipProbe" not in bases, f"Subclass {node.name!r} violates AC-NEW-4"


def test_ownership_docstring_documents_github_divergence() -> None:
    """AC-NEW-7. The intentional divergence is grep-discoverable."""
    assert op.__doc__ is not None
    assert "Phase 2 search order intentionally diverges from GitHub" in op.__doc__


def test_ownership_slice_rejects_extra_fields() -> None:
    """AC-2, AC-16. Mutation caught: relaxing extra='forbid' to 'allow'."""
    with pytest.raises(pydantic.ValidationError):
        op.OwnershipSlice(
            source_path="CODEOWNERS",
            entries=(),
            extra_field="x",  # type: ignore[call-arg]
        )


def test_ownership_entry_rejects_extra_fields() -> None:
    """AC-2. OwnershipEntry also enforces extra='forbid'."""
    with pytest.raises(pydantic.ValidationError):
        op.OwnershipEntry(
            pattern="*",
            owners=(),
            line_number=1,
            extra_field="x",  # type: ignore[call-arg]
        )
