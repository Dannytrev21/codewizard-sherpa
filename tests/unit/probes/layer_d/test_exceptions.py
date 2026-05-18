"""Unit tests for ``ExceptionProbe`` (S6-03)."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

from codegenie.probes.layer_d import exceptions as exc

from .conftest import _make_context, _make_repo


def _entry(
    repo_glob: str = "*",
    task: str = "vuln",
    expires: date = date(2030, 1, 1),
) -> exc.ExceptionEntry:
    return exc.ExceptionEntry(
        repo_glob=repo_glob, task=task, reason="r", expires=expires, approver="@team"
    )


def test_partition_by_expiry_inclusive_boundary() -> None:
    """AC-9 / AC-15. Mutation caught: ``expires > now`` (strict) instead of
    ``expires >= now`` — same-day-as-expiry entries are still active."""
    today = _entry(expires=date(2026, 5, 17))
    yesterday = _entry(expires=date(2026, 5, 16))
    active, expired = exc._partition_by_expiry([today, yesterday], now=date(2026, 5, 17))
    assert today in active
    assert yesterday in expired


def test_match_repo_glob_case_sensitive() -> None:
    """AC-9. Mutation caught: using ``fnmatch.fnmatch`` (case-insensitive on
    Windows) — only ``fnmatchcase`` guarantees cross-platform determinism."""
    assert exc._match_repo_glob("myservice", "myservice*") is True
    assert exc._match_repo_glob("myservice", "MyService*") is False


def test_exceptions_bare_list_rejected_low_confidence(tmp_path: Path) -> None:
    """AC-22. Mutation caught: admitting top-level YAML lists would silently
    bypass the chokepoint mapping discipline."""
    repo = _make_repo(tmp_path)
    bare = repo.root / ".codegenie" / "exceptions.yaml"
    bare.parent.mkdir(parents=True)
    bare.write_text(
        "- repo_glob: '*'\n  task: vuln\n  reason: r\n  expires: 2026-09-01\n  approver: '@team'\n"
    )
    ctx = _make_context(tmp_path)
    output = asyncio.run(exc.ExceptionProbe().run(repo, ctx))
    assert output.confidence == "low"
    slice_ = exc.ExceptionsSlice.model_validate(output.schema_slice)
    assert "exceptions_yaml_not_mapping" in slice_.per_file_errors


def test_exceptions_mapping_shape_happy_path(tmp_path: Path) -> None:
    """AC-22. Pinned format."""
    repo = _make_repo(tmp_path)
    ex = repo.root / ".codegenie" / "exceptions.yaml"
    ex.parent.mkdir(parents=True)
    ex.write_text(
        "exceptions:\n"
        "  - repo_glob: 'myrepo*'\n    task: vuln_remediation\n    reason: 'r'\n"
        "    expires: 2030-01-01\n    approver: '@team'\n"
    )
    ctx = _make_context(tmp_path)
    output = asyncio.run(exc.ExceptionProbe().run(repo, ctx))
    assert output.confidence == "high"
    slice_ = exc.ExceptionsSlice.model_validate(output.schema_slice)
    assert len(slice_.active) == 1


def test_exceptions_repo_glob_filters_unmatched(tmp_path: Path) -> None:
    """AC-9. Mutation caught: dropping the glob filter would emit
    cross-repo exceptions in every gather."""
    repo = _make_repo(tmp_path, name="alpha")
    ex = repo.root / ".codegenie" / "exceptions.yaml"
    ex.parent.mkdir(parents=True)
    ex.write_text(
        "exceptions:\n"
        "  - repo_glob: 'alpha*'\n    task: v\n    reason: r\n"
        "    expires: 2030-01-01\n    approver: '@t'\n"
        "  - repo_glob: 'beta*'\n    task: v\n    reason: r\n"
        "    expires: 2030-01-01\n    approver: '@t'\n"
    )
    ctx = _make_context(tmp_path)
    output = asyncio.run(exc.ExceptionProbe().run(repo, ctx))
    slice_ = exc.ExceptionsSlice.model_validate(output.schema_slice)
    matched = list(slice_.active) + list(slice_.expired)
    assert [e.repo_glob for e in matched] == ["alpha*"]


def test_exceptions_files_absent_low(tmp_path: Path) -> None:
    """AC-10."""
    repo = _make_repo(tmp_path)
    ctx = _make_context(
        tmp_path,
        config_overrides={"exceptions.user_home": str(tmp_path / "empty_home")},
    )
    output = asyncio.run(exc.ExceptionProbe().run(repo, ctx))
    assert output.confidence == "low"
    slice_ = exc.ExceptionsSlice.model_validate(output.schema_slice)
    assert "exceptions_files_absent" in slice_.per_file_errors
    assert slice_.active == () and slice_.expired == ()


def test_exceptions_active_expired_disjoint(tmp_path: Path) -> None:
    """AC-9 smart-constructor invariant. Mutation caught: leaking an entry
    into both partitions would break the disjoint guarantee."""
    repo = _make_repo(tmp_path)
    ex = repo.root / ".codegenie" / "exceptions.yaml"
    ex.parent.mkdir(parents=True)
    ex.write_text(
        "exceptions:\n"
        "  - repo_glob: 'myrepo*'\n    task: a\n    reason: r\n"
        "    expires: 2099-01-01\n    approver: '@t'\n"
        "  - repo_glob: 'myrepo*'\n    task: b\n    reason: r\n"
        "    expires: 2000-01-01\n    approver: '@t'\n"
    )
    ctx = _make_context(tmp_path)
    output = asyncio.run(exc.ExceptionProbe().run(repo, ctx))
    slice_ = exc.ExceptionsSlice.model_validate(output.schema_slice)
    active_ids = {(e.repo_glob, e.task, e.expires) for e in slice_.active}
    expired_ids = {(e.repo_glob, e.task, e.expires) for e in slice_.expired}
    assert active_ids.isdisjoint(expired_ids)


def test_exceptions_two_runs_byte_identical(tmp_path: Path) -> None:
    """AC-15."""
    repo = _make_repo(tmp_path)
    ex = repo.root / ".codegenie" / "exceptions.yaml"
    ex.parent.mkdir(parents=True)
    ex.write_text(
        "exceptions:\n"
        "  - repo_glob: 'myrepo*'\n    task: z\n    reason: r\n"
        "    expires: 2099-01-01\n    approver: '@t'\n"
        "  - repo_glob: 'myrepo*'\n    task: a\n    reason: r\n"
        "    expires: 2099-01-01\n    approver: '@t'\n"
    )
    ctx = _make_context(tmp_path)
    s1 = exc.ExceptionsSlice.model_validate(
        asyncio.run(exc.ExceptionProbe().run(repo, ctx)).schema_slice
    )
    s2 = exc.ExceptionsSlice.model_validate(
        asyncio.run(exc.ExceptionProbe().run(repo, ctx)).schema_slice
    )
    assert s1.model_dump_json() == s2.model_dump_json()
    assert [e.task for e in s1.active] == ["a", "z"]


def test_exceptions_exception_entry_not_named_exception() -> None:
    """Implementer note 11. Mutation caught: rebinding the builtin
    ``Exception`` name would break every ``except Exception`` block in the
    module — assert the slice class is ``ExceptionEntry``."""
    assert hasattr(exc, "ExceptionEntry")
    assert exc.ExceptionEntry is not Exception
