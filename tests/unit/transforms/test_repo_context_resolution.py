"""ADR-0015 — repo dependency loading and pure CVE resolution."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from codegenie.result import Err, Ok
from codegenie.transforms.repo_context import (
    CveAffectsMultiple,
    CveAffectsRepo,
    CveNotInRepo,
    InstalledDependency,
    RepoContextMissing,
    RepoContextNoDependencies,
    load_installed_dependencies,
    resolve_cve,
)
from codegenie.types.identifiers import CveId, PackageName
from codegenie.vuln_index import AffectedRange, VulnerabilityRecord


def _record(cve: str, package: str, ecosystem: str = "npm") -> VulnerabilityRecord:
    return VulnerabilityRecord(
        cve_id=CveId(cve),
        ecosystem=ecosystem,  # type: ignore[arg-type]
        package=PackageName(package),
        affected_range=AffectedRange(introduced="0.0.0", fixed="1.0.0"),
        severity="high",
        published_at=datetime(2026, 5, 1, tzinfo=UTC),
        source="nvd",
    )


def _write_context(repo: Path) -> None:
    context_dir = repo / ".codegenie" / "context"
    context_dir.mkdir(parents=True)
    (context_dir / "repo-context.yaml").write_text("probes: {}\n", encoding="utf-8")


def test_load_installed_dependencies_reads_package_json_dependency_names(tmp_path: Path) -> None:
    _write_context(tmp_path)
    (tmp_path / "package.json").write_text(
        '{"dependencies":{"express":"4.18.2"},"devDependencies":{"vitest":"1.0.0"}}',
        encoding="utf-8",
    )

    result = load_installed_dependencies(tmp_path)

    assert isinstance(result, Ok)
    assert result.value == (
        InstalledDependency(package=PackageName("express"), ecosystem="npm"),
        InstalledDependency(package=PackageName("vitest"), ecosystem="npm"),
    )


def test_load_installed_dependencies_requires_context_artifact(tmp_path: Path) -> None:
    result = load_installed_dependencies(tmp_path)

    assert isinstance(result, Err)
    assert isinstance(result.error, RepoContextMissing)


def test_load_installed_dependencies_reports_no_dependencies(tmp_path: Path) -> None:
    _write_context(tmp_path)
    (tmp_path / "package.json").write_text('{"name":"empty"}', encoding="utf-8")

    result = load_installed_dependencies(tmp_path)

    assert isinstance(result, Err)
    assert isinstance(result.error, RepoContextNoDependencies)


def test_resolve_cve_not_in_repo() -> None:
    outcome = resolve_cve(
        [_record("CVE-2024-21501", "lodash")],
        (InstalledDependency(package=PackageName("express"), ecosystem="npm"),),
    )

    assert isinstance(outcome, CveNotInRepo)


def test_resolve_cve_single_match() -> None:
    record = _record("CVE-2024-21501", "express")

    outcome = resolve_cve(
        [record, _record("CVE-2024-21501", "lodash")],
        (InstalledDependency(package=PackageName("express"), ecosystem="npm"),),
    )

    assert isinstance(outcome, CveAffectsRepo)
    assert outcome.record == record


def test_resolve_cve_multiple_matches_escalates() -> None:
    express = _record("CVE-2024-21501", "express")
    body_parser = _record("CVE-2024-21501", "body-parser")

    outcome = resolve_cve(
        [express, body_parser],
        (
            InstalledDependency(package=PackageName("express"), ecosystem="npm"),
            InstalledDependency(package=PackageName("body-parser"), ecosystem="npm"),
        ),
    )

    assert isinstance(outcome, CveAffectsMultiple)
    assert outcome.records == (body_parser, express)
