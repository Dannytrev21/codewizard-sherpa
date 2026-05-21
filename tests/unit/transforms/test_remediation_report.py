"""S5-05 — RemediationReport schema + YAML writer."""

from __future__ import annotations

import errno
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from codegenie.result import Err, Ok
from codegenie.transforms._forward import SandboxedPath
from codegenie.transforms.outcomes import (
    RemediationError,
    RemediationFailed,
    RemediationNotApplicable,
    RequiresHumanReview,
    TrustOutcome,
    TrustSignal,
    Validated,
)
from codegenie.transforms.report import (
    PluginSnapshot,
    RemediationReport,
    ReportDiskFull,
    ReportFileMissing,
    ReportFilesystemRace,
    ReportLoadError,
    ReportMetadata,
    ReportOtherIoError,
    ReportPermissionDenied,
    ReportSchemaViolation,
    ReportSizeCapExceeded,
    ReportSymlinkRefused,
    ReportUnknownSchemaVersion,
    ReportWriteSymlinkRefused,
    ReportYamlSyntax,
    TransformSnapshot,
)
from codegenie.types.identifiers import (
    BlobDigest,
    BranchName,
    CveId,
    ErrorId,
    PluginId,
    RecipeId,
    SemverVersion,
    SignalKind,
    TransformId,
    TransformKind,
    WorkflowId,
)


def _sandboxed(path: Path) -> SandboxedPath:
    return SandboxedPath(absolute=path)


def _meta(**overrides: object) -> ReportMetadata:
    base: dict[str, object] = {
        "workflow_id": WorkflowId("01HX0000000000000000000000"),
        "cve": CveId("CVE-2024-21501"),
        "repo_path": "/tmp/fixture",
        "started_at": datetime(2026, 5, 17, 12, 0, tzinfo=UTC),
        "completed_at": datetime(2026, 5, 17, 12, 0, 30, tzinfo=UTC),
        "codegenie_version": "0.3.0",
    }
    base.update(overrides)
    return ReportMetadata(**base)


def _plugin(*, recipe: bool = True) -> PluginSnapshot:
    if recipe:
        return PluginSnapshot(
            plugin_id=PluginId("vulnerability-remediation--node--npm"),
            plugin_version=SemverVersion("0.1.0"),
            recipe_id=RecipeId("npm-lockfile-semver-bump"),
            recipe_version=SemverVersion("0.1.0"),
        )
    return PluginSnapshot(
        plugin_id=PluginId("vulnerability-remediation--node--npm"),
        plugin_version=SemverVersion("0.1.0"),
        recipe_id=None,
        recipe_version=None,
    )


def _transform() -> TransformSnapshot:
    return TransformSnapshot(
        transform_id=TransformId("blake3:abc123"),
        transform_kind=TransformKind("npm-lockfile-semver-bump"),
        files_changed=("package.json", "package-lock.json"),
        diff_bytes_sha256=BlobDigest("a" * 64),
    )


def _trust_passed() -> TrustOutcome:
    return TrustOutcome(
        passed=True,
        failing=[],
        signals=(
            TrustSignal(
                kind=SignalKind("tests"),
                passed=True,
                details={"total": 12},
            ),
        ),
        confidence="high",
    )


@pytest.fixture
def validated_report() -> RemediationReport:
    branch = BranchName("codegenie/cve-2024-21501-abc12")
    return RemediationReport(
        schema_version=1,
        metadata=_meta(),
        plugin=_plugin(),
        transform=_transform(),
        outcome=Validated(
            branch=branch,
            report_path="/tmp/r.yaml",
            passed=True,
            failing=[],
        ),
        trust_outcome=_trust_passed(),
        branch=branch,
        event_log_internal_path="events/internal/01HX.jsonl.zst",
        event_log_spanning_path="events/spanning/append.jsonl.zst",
        spanning_chain_head=BlobDigest("b" * 64),
        lockfile_policy_violations=(),
    )


def _write_and_load(tmp_path: Path, report: RemediationReport) -> RemediationReport:
    path = _sandboxed(tmp_path / "r.yaml")
    write_result = report.write(path)
    assert isinstance(write_result, Ok)
    loaded = RemediationReport.from_yaml(path)
    assert isinstance(loaded, Ok)
    return loaded.unwrap()


def test_report_surface_symbols_exported() -> None:
    assert ReportLoadError is not None
    assert RemediationReport.__name__ == "RemediationReport"


def test_round_trip_validated(tmp_path: Path, validated_report: RemediationReport) -> None:
    assert _write_and_load(tmp_path, validated_report) == validated_report


def test_round_trip_not_applicable(tmp_path: Path) -> None:
    report = RemediationReport(
        schema_version=1,
        metadata=_meta(),
        plugin=_plugin(recipe=False),
        transform=None,
        outcome=RemediationNotApplicable(reason="PEER_DEP_CONFLICT"),
        trust_outcome=None,
        branch=None,
        event_log_internal_path="events/internal/not-applicable.jsonl.zst",
        event_log_spanning_path="events/spanning/append.jsonl.zst",
        spanning_chain_head=BlobDigest("c" * 64),
    )

    assert _write_and_load(tmp_path, report) == report


def test_round_trip_failed_partial_report(tmp_path: Path) -> None:
    report = RemediationReport(
        schema_version=1,
        metadata=_meta(),
        plugin=_plugin(recipe=False),
        transform=None,
        outcome=RemediationFailed(
            error=RemediationError(
                error_id=ErrorId("io.lockfile_v1_unsupported"),
                message="lockfile schema v1 not supported",
            ),
            partial_report_path=None,
        ),
        trust_outcome=None,
        branch=None,
        event_log_internal_path="events/internal/partial.jsonl.zst",
        event_log_spanning_path="events/spanning/append.jsonl.zst",
        spanning_chain_head=BlobDigest("d" * 64),
    )

    assert _write_and_load(tmp_path, report) == report


def test_round_trip_requires_human_review(tmp_path: Path) -> None:
    report = RemediationReport(
        schema_version=1,
        metadata=_meta(),
        plugin=_plugin(recipe=False),
        transform=None,
        outcome=RequiresHumanReview(reason="no_concrete_match", handoff_path=None),
        trust_outcome=None,
        branch=None,
        event_log_internal_path="events/internal/hr.jsonl.zst",
        event_log_spanning_path="events/spanning/append.jsonl.zst",
        spanning_chain_head=BlobDigest("e" * 64),
    )

    assert _write_and_load(tmp_path, report) == report


def test_yaml_byte_identical_on_repeated_write(
    tmp_path: Path, validated_report: RemediationReport
) -> None:
    path_a = _sandboxed(tmp_path / "a.yaml")
    path_b = _sandboxed(tmp_path / "b.yaml")
    assert isinstance(validated_report.write(path_a), Ok)
    assert isinstance(validated_report.write(path_b), Ok)
    assert path_a.absolute.read_bytes() == path_b.absolute.read_bytes()


def test_serialize_is_pure_and_byte_stable(validated_report: RemediationReport) -> None:
    assert validated_report._serialize() == validated_report._serialize()


def test_no_python_tags_in_serialized_output(validated_report: RemediationReport) -> None:
    assert b"!!python" not in validated_report._serialize()


def test_write_read_write_byte_identical(
    tmp_path: Path, validated_report: RemediationReport
) -> None:
    first = _sandboxed(tmp_path / "first.yaml")
    second = _sandboxed(tmp_path / "second.yaml")

    assert isinstance(validated_report.write(first), Ok)
    loaded = RemediationReport.from_yaml(first)
    assert isinstance(loaded, Ok)
    assert isinstance(loaded.unwrap().write(second), Ok)

    assert first.absolute.read_bytes() == second.absolute.read_bytes()


def test_file_missing(tmp_path: Path) -> None:
    result = RemediationReport.from_yaml(_sandboxed(tmp_path / "missing.yaml"))

    assert isinstance(result, Err)
    assert isinstance(result.unwrap_err(), ReportFileMissing)


def test_directory_rejected_as_file_missing(tmp_path: Path) -> None:
    result = RemediationReport.from_yaml(_sandboxed(tmp_path))

    assert isinstance(result, Err)
    assert isinstance(result.unwrap_err(), ReportFileMissing)


def test_yaml_syntax_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("schema_version: 1\nmetadata: {workflow_id:", encoding="utf-8")

    result = RemediationReport.from_yaml(_sandboxed(path))

    assert isinstance(result, Err)
    assert isinstance(result.unwrap_err(), ReportYamlSyntax)


def test_open_eloop_is_symlink_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "race.yaml"

    def boom(path_arg: str, flags: int) -> int:
        raise OSError(errno.ELOOP, "too many symbolic links")

    monkeypatch.setattr("codegenie.transforms.report.os.open", boom)
    result = RemediationReport.from_yaml(_sandboxed(path))

    assert isinstance(result, Err)
    assert isinstance(result.unwrap_err(), ReportSymlinkRefused)


def test_open_unexpected_oserror_is_load_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "busy.yaml"

    def boom(path_arg: str, flags: int) -> int:
        raise OSError(errno.EBUSY, "busy")

    monkeypatch.setattr("codegenie.transforms.report.os.open", boom)
    result = RemediationReport.from_yaml(_sandboxed(path))

    assert isinstance(result, Err)
    assert isinstance(result.unwrap_err(), ReportYamlSyntax)


def test_extra_field_rejected(tmp_path: Path, validated_report: RemediationReport) -> None:
    path = _sandboxed(tmp_path / "r.yaml")
    validated_report.write(path).unwrap()
    doc = yaml.safe_load(path.absolute.read_bytes())
    doc["magic_field"] = True
    hostile = tmp_path / "hostile.yaml"
    hostile.write_text(yaml.safe_dump(doc), encoding="utf-8")

    result = RemediationReport.from_yaml(_sandboxed(hostile))

    assert isinstance(result, Err)
    err = result.unwrap_err()
    assert isinstance(err, ReportSchemaViolation)
    assert "magic_field" in err.field_errors


def test_non_mapping_document_rejected_at_root(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    result = RemediationReport.from_yaml(_sandboxed(path))

    assert isinstance(result, Err)
    err = result.unwrap_err()
    assert isinstance(err, ReportSchemaViolation)
    assert "<root>" in err.field_errors


def test_unknown_schema_version_pre_pydantic(
    tmp_path: Path, validated_report: RemediationReport
) -> None:
    path = _sandboxed(tmp_path / "r.yaml")
    validated_report.write(path).unwrap()
    doc = yaml.safe_load(path.absolute.read_bytes())
    doc["schema_version"] = 2
    doc["plugin"]["plugin_id"] = ""
    versioned = tmp_path / "v2.yaml"
    versioned.write_text(yaml.safe_dump(doc), encoding="utf-8")

    result = RemediationReport.from_yaml(_sandboxed(versioned))

    assert isinstance(result, Err)
    err = result.unwrap_err()
    assert isinstance(err, ReportUnknownSchemaVersion)
    assert err.found_version == 2
    assert err.supported_versions == (1,)


def test_size_cap_exceeded(tmp_path: Path) -> None:
    path = tmp_path / "big.yaml"
    path.write_bytes(b"schema_version: 1\nfiller: " + b"x" * (1 << 20))

    result = RemediationReport.from_yaml(_sandboxed(path))

    assert isinstance(result, Err)
    err = result.unwrap_err()
    assert isinstance(err, ReportSizeCapExceeded)
    assert err.cap == 1 << 20


def test_symlink_refused(tmp_path: Path, validated_report: RemediationReport) -> None:
    real = _sandboxed(tmp_path / "real.yaml")
    validated_report.write(real).unwrap()
    link = tmp_path / "link.yaml"
    link.symlink_to(real.absolute)

    result = RemediationReport.from_yaml(_sandboxed(link))

    assert isinstance(result, Err)
    assert isinstance(result.unwrap_err(), ReportSymlinkRefused)


def test_outcome_kind_case_sensitive(tmp_path: Path, validated_report: RemediationReport) -> None:
    path = _sandboxed(tmp_path / "r.yaml")
    validated_report.write(path).unwrap()
    doc = yaml.safe_load(path.absolute.read_bytes())
    doc["outcome"]["kind"] = "VALIDATED"
    hostile = tmp_path / "case.yaml"
    hostile.write_text(yaml.safe_dump(doc), encoding="utf-8")

    result = RemediationReport.from_yaml(_sandboxed(hostile))

    assert isinstance(result, Err)
    err = result.unwrap_err()
    assert isinstance(err, ReportSchemaViolation)
    assert "outcome.kind" in err.field_errors


def test_validated_outcome_requires_transform_and_branch() -> None:
    with pytest.raises(ValidationError, match="validated"):
        RemediationReport(
            schema_version=1,
            metadata=_meta(),
            plugin=_plugin(),
            transform=None,
            outcome=Validated(
                branch=BranchName("b"),
                report_path="/x",
                passed=True,
                failing=[],
            ),
            trust_outcome=_trust_passed(),
            branch=BranchName("b"),
            event_log_internal_path="x",
            event_log_spanning_path="y",
            spanning_chain_head=BlobDigest("0" * 64),
        )


def test_failed_outcome_requires_branch_none() -> None:
    with pytest.raises(ValidationError, match="failed"):
        RemediationReport(
            schema_version=1,
            metadata=_meta(),
            plugin=_plugin(recipe=False),
            transform=None,
            outcome=RemediationFailed(
                error=RemediationError(error_id=ErrorId("io.x"), message="m"),
                partial_report_path=None,
            ),
            trust_outcome=None,
            branch=BranchName("should-be-none"),
            event_log_internal_path="x",
            event_log_spanning_path="y",
            spanning_chain_head=BlobDigest("0" * 64),
        )


def test_not_applicable_outcome_requires_branch_none() -> None:
    with pytest.raises(ValidationError, match="not_applicable"):
        RemediationReport(
            schema_version=1,
            metadata=_meta(),
            plugin=_plugin(recipe=False),
            transform=None,
            outcome=RemediationNotApplicable(reason="PEER_DEP_CONFLICT"),
            trust_outcome=None,
            branch=BranchName("should-be-none"),
            event_log_internal_path="x",
            event_log_spanning_path="y",
            spanning_chain_head=BlobDigest("0" * 64),
        )


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        ReportMetadata(
            workflow_id=WorkflowId("01HX0000000000000000000000"),
            cve=CveId("CVE-2024-21501"),
            repo_path="/x",
            started_at=datetime(2026, 5, 17, 12, 0),
            completed_at=datetime(2026, 5, 17, 12, 0, 30, tzinfo=UTC),
            codegenie_version="0.3.0",
        )


def test_write_refuses_destination_symlink(
    tmp_path: Path, validated_report: RemediationReport
) -> None:
    real = tmp_path / "real.yaml"
    link = tmp_path / "link.yaml"
    real.write_text("target\n", encoding="utf-8")
    link.symlink_to(real)

    result = validated_report.write(_sandboxed(link))

    assert isinstance(result, Err)
    assert isinstance(result.unwrap_err(), ReportWriteSymlinkRefused)


def test_atomic_write_no_partial_on_replace_failure(
    tmp_path: Path,
    validated_report: RemediationReport,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _sandboxed(tmp_path / "r.yaml")
    path.absolute.write_text("PREVIOUS_CONTENT\n", encoding="utf-8")

    def boom(src: str, dst: str) -> None:
        raise OSError(errno.EACCES, "synthetic permission denied")

    monkeypatch.setattr("codegenie.transforms.report.os.replace", boom)
    result = validated_report.write(path)

    assert isinstance(result, Err)
    assert isinstance(result.unwrap_err(), ReportPermissionDenied)
    assert path.absolute.read_text(encoding="utf-8") == "PREVIOUS_CONTENT\n"
    assert not any(child.name.endswith(".tmp") for child in tmp_path.iterdir())


def test_disk_full_translation(
    tmp_path: Path,
    validated_report: RemediationReport,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(src: str, dst: str) -> None:
        raise OSError(errno.ENOSPC, "no space")

    monkeypatch.setattr("codegenie.transforms.report.os.replace", boom)
    result = validated_report.write(_sandboxed(tmp_path / "r.yaml"))

    assert isinstance(result, Err)
    assert isinstance(result.unwrap_err(), ReportDiskFull)


def test_filesystem_race_translation(
    tmp_path: Path,
    validated_report: RemediationReport,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(src: str, dst: str) -> None:
        raise OSError(errno.ELOOP, "race")

    monkeypatch.setattr("codegenie.transforms.report.os.replace", boom)
    result = validated_report.write(_sandboxed(tmp_path / "r.yaml"))

    assert isinstance(result, Err)
    assert isinstance(result.unwrap_err(), ReportFilesystemRace)


def test_open_failure_cleans_missing_tmp(
    tmp_path: Path,
    validated_report: RemediationReport,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(path_arg: str, flags: int, mode: int = 0o777) -> int:
        raise OSError(errno.EACCES, "denied")

    monkeypatch.setattr("codegenie.transforms.report.os.open", boom)
    result = validated_report.write(_sandboxed(tmp_path / "r.yaml"))

    assert isinstance(result, Err)
    assert isinstance(result.unwrap_err(), ReportPermissionDenied)


def test_other_io_error_translation(
    tmp_path: Path,
    validated_report: RemediationReport,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(src: str, dst: str) -> None:
        raise OSError(errno.EBUSY, "busy")

    monkeypatch.setattr("codegenie.transforms.report.os.replace", boom)
    result = validated_report.write(_sandboxed(tmp_path / "r.yaml"))

    assert isinstance(result, Err)
    assert isinstance(result.unwrap_err(), ReportOtherIoError)


def test_files_changed_tuple_round_trips(
    tmp_path: Path, validated_report: RemediationReport
) -> None:
    loaded = _write_and_load(tmp_path, validated_report)

    assert loaded.transform is not None
    assert isinstance(loaded.transform.files_changed, tuple)
    assert loaded.transform.files_changed == ("package.json", "package-lock.json")
