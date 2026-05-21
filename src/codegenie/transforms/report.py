"""S5-05 remediation report contract and atomic YAML writer.

``remediation-report.yaml`` is the human-facing Phase-3 artifact that Phase 5
reads to decide retry/escalation. The schema is intentionally rigid:
``extra="forbid"`` on every Pydantic model, newtyped identifiers on every
domain-id field, and module-local tagged unions for load/write failures.

The writer uses a functional-core / imperative-shell split:
``_serialize()`` is deterministic and pure, while ``_write_bytes`` owns the
tmp+fsync+``os.replace`` boundary. The schema version is pinned at
``Literal[1]``; top-level field additions are contract amendments.
"""

from __future__ import annotations

import errno
import os
import secrets
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Annotated, Final, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from codegenie.result import Err, Ok, Result
from codegenie.transforms._forward import SandboxedPath
from codegenie.transforms.outcomes import (
    RemediationFailed,
    RemediationNotApplicable,
    RemediationOutcome,
    RequiresHumanReview,
    TrustOutcome,
    Validated,
)
from codegenie.transforms.policy.lockfile_policy import PolicyViolation
from codegenie.types.identifiers import (
    BlobDigest,
    BranchName,
    CveId,
    PluginId,
    RecipeId,
    SemverVersion,
    TransformId,
    TransformKind,
    WorkflowId,
)

__all__ = [
    "PluginSnapshot",
    "RemediationReport",
    "ReportDiskFull",
    "ReportFileMissing",
    "ReportFilesystemRace",
    "ReportIoError",
    "ReportLoadError",
    "ReportMetadata",
    "ReportOtherIoError",
    "ReportPermissionDenied",
    "ReportSchemaViolation",
    "ReportSizeCapExceeded",
    "ReportSymlinkRefused",
    "ReportUnknownSchemaVersion",
    "ReportWriteSymlinkRefused",
    "ReportYamlSyntax",
    "TransformSnapshot",
]

_SUPPORTED_SCHEMA_VERSIONS: Final[tuple[int, ...]] = (1,)
_MAX_REPORT_BYTES: Final[int] = 1 << 20


class ReportFileMissing(BaseModel):
    """Report path does not exist or is not a regular file."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["file_missing"] = "file_missing"
    path: str


class ReportYamlSyntax(BaseModel):
    """Report file is not well-formed YAML."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["yaml_syntax"] = "yaml_syntax"
    path: str
    message: str


class ReportSchemaViolation(BaseModel):
    """Report YAML parsed but failed the Pydantic contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["schema_violation"] = "schema_violation"
    path: str
    field_errors: tuple[str, ...]


class ReportUnknownSchemaVersion(BaseModel):
    """Report schema version is not supported by Phase 3."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["unknown_schema_version"] = "unknown_schema_version"
    path: str
    found_version: int
    supported_versions: tuple[int, ...]


class ReportSizeCapExceeded(BaseModel):
    """Report input is larger than the 1 MiB smart-constructor cap."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["size_cap_exceeded"] = "size_cap_exceeded"
    path: str
    actual_bytes: int
    cap: int


class ReportSymlinkRefused(BaseModel):
    """Report load refused a symlink before opening the target."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["symlink_refused"] = "symlink_refused"
    path: str


ReportLoadError = Annotated[
    ReportFileMissing
    | ReportYamlSyntax
    | ReportSchemaViolation
    | ReportUnknownSchemaVersion
    | ReportSizeCapExceeded
    | ReportSymlinkRefused,
    Field(discriminator="kind"),
]


class _ReportIoBase(BaseModel):
    """Shared OS-error payload for report write failures."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    path: str
    errno: int
    message: str


class ReportWriteSymlinkRefused(_ReportIoBase):
    """Destination path is a symlink before publish."""

    kind: Literal["write_symlink_refused"] = "write_symlink_refused"


class ReportDiskFull(_ReportIoBase):
    """Filesystem reported ``ENOSPC`` while writing the report."""

    kind: Literal["disk_full"] = "disk_full"


class ReportPermissionDenied(_ReportIoBase):
    """Filesystem reported ``EACCES`` while writing the report."""

    kind: Literal["permission_denied"] = "permission_denied"


class ReportFilesystemRace(_ReportIoBase):
    """Filesystem reported ``ELOOP`` or equivalent TOCTOU race."""

    kind: Literal["filesystem_race"] = "filesystem_race"


class ReportOtherIoError(_ReportIoBase):
    """Fallback for any other ``OSError`` during report write."""

    kind: Literal["other_io_error"] = "other_io_error"


ReportIoError = Annotated[
    ReportWriteSymlinkRefused
    | ReportDiskFull
    | ReportPermissionDenied
    | ReportFilesystemRace
    | ReportOtherIoError,
    Field(discriminator="kind"),
]


class ReportMetadata(BaseModel):
    """Stable report metadata. Datetimes must carry timezone information."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    workflow_id: WorkflowId
    cve: CveId
    repo_path: str
    started_at: datetime
    completed_at: datetime
    codegenie_version: str

    @field_validator("started_at", "completed_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("report datetimes must be timezone-aware")
        return value


class PluginSnapshot(BaseModel):
    """Plugin and optional recipe identity captured in the report."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    plugin_id: PluginId
    plugin_version: SemverVersion
    recipe_id: RecipeId | None = None
    recipe_version: SemverVersion | None = None


class TransformSnapshot(BaseModel):
    """Post-apply transform summary consumed by Phase 5 and humans."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    transform_id: TransformId
    transform_kind: TransformKind
    files_changed: tuple[str, ...]
    diff_bytes_sha256: BlobDigest


class RemediationReport(BaseModel):
    """Frozen schema for ``remediation-report.yaml``.

    Version bump policy: additive variants inside nested discriminated unions do
    not bump ``schema_version``; adding/removing/reordering top-level fields
    does, because Phase 5 reads this field surface by name.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1]
    metadata: ReportMetadata
    plugin: PluginSnapshot
    transform: TransformSnapshot | None
    outcome: RemediationOutcome
    trust_outcome: TrustOutcome | None
    branch: BranchName | None
    event_log_internal_path: str
    event_log_spanning_path: str
    spanning_chain_head: BlobDigest
    lockfile_policy_violations: tuple[PolicyViolation, ...] = ()

    @model_validator(mode="after")
    def _outcome_optional_field_invariants(self) -> RemediationReport:
        if isinstance(self.outcome, Validated):
            if self.transform is None or self.branch is None:
                raise ValueError("validated outcome requires transform and branch")
        elif isinstance(self.outcome, RemediationFailed):
            if self.branch is not None:
                raise ValueError("failed outcome requires branch to be None")
        elif isinstance(self.outcome, RemediationNotApplicable | RequiresHumanReview):
            if self.branch is not None:
                raise ValueError(f"{self.outcome.kind} outcome requires branch to be None")
        return self

    def _serialize(self) -> bytes:
        """Return deterministic YAML bytes without touching the filesystem."""
        return yaml.safe_dump(
            self.model_dump(mode="json"),
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        ).encode("utf-8")

    def write(self, path: SandboxedPath) -> Result[None, ReportIoError]:
        """Atomically publish this report to ``path`` without raising."""
        return _write_bytes(path, self._serialize())

    @classmethod
    def from_yaml(cls, path: SandboxedPath) -> Result[RemediationReport, ReportLoadError]:
        """Load a report from YAML using the pinned validation order."""
        report_path = _as_path(path)
        path_text = str(report_path)
        if report_path.is_symlink():
            return Err(error=ReportSymlinkRefused(path=path_text))
        if report_path.exists() and not report_path.is_file():
            return Err(error=ReportFileMissing(path=path_text))

        try:
            fd = os.open(str(report_path), os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return Err(error=ReportFileMissing(path=path_text))
        except IsADirectoryError:
            return Err(error=ReportFileMissing(path=path_text))
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                return Err(error=ReportSymlinkRefused(path=path_text))
            return Err(
                error=ReportYamlSyntax(
                    path=path_text,
                    message=f"could not open report: {exc.strerror or str(exc)}",
                )
            )

        try:
            stat_result = os.fstat(fd)
            if stat_result.st_size > _MAX_REPORT_BYTES:
                return Err(
                    error=ReportSizeCapExceeded(
                        path=path_text,
                        actual_bytes=stat_result.st_size,
                        cap=_MAX_REPORT_BYTES,
                    )
                )
            with os.fdopen(fd, "rb", closefd=True) as handle:
                fd = -1
                raw = handle.read()
        finally:
            if fd >= 0:
                os.close(fd)

        try:
            data: object = yaml.safe_load(raw.decode("utf-8"))
        except (UnicodeDecodeError, yaml.YAMLError) as exc:
            return Err(error=ReportYamlSyntax(path=path_text, message=str(exc)))

        observed = data.get("schema_version") if isinstance(data, Mapping) else None
        if (
            isinstance(observed, int)
            and not isinstance(observed, bool)
            and observed not in _SUPPORTED_SCHEMA_VERSIONS
        ):
            return Err(
                error=ReportUnknownSchemaVersion(
                    path=path_text,
                    found_version=observed,
                    supported_versions=_SUPPORTED_SCHEMA_VERSIONS,
                )
            )

        try:
            return Ok(value=cls.model_validate(data))
        except ValidationError as exc:
            return Err(
                error=ReportSchemaViolation(
                    path=path_text,
                    field_errors=tuple(_field_error_path(error) for error in exc.errors()),
                )
            )


def _as_path(path: SandboxedPath) -> Path:
    return Path(os.fspath(path))


def _field_error_path(error: Mapping[str, object]) -> str:
    loc = error.get("loc", ())
    if isinstance(loc, tuple | list):
        parts = [str(part) for part in loc]
    else:
        parts = [str(loc)] if loc else []

    ctx = error.get("ctx")
    if isinstance(ctx, Mapping):
        discriminator = ctx.get("discriminator")
        if isinstance(discriminator, str):
            discriminator_name = discriminator.strip("'")
            if parts and parts[-1] != discriminator_name:
                parts.append(discriminator_name)

    return ".".join(parts) if parts else "<root>"


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    written = 0
    while written < len(view):
        written += os.write(fd, view[written:])


def _write_bytes(path: SandboxedPath, payload: bytes) -> Result[None, ReportIoError]:
    dest = _as_path(path)
    dest_text = str(dest)
    if dest.is_symlink():
        return Err(
            error=ReportWriteSymlinkRefused(
                path=dest_text,
                errno=errno.ELOOP,
                message="destination is a symlink",
            )
        )

    tmp = dest.parent / f"{dest.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    try:
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        try:
            _write_all(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(str(tmp), str(dest))
    except OSError as exc:
        _cleanup_tmp(tmp)
        return Err(error=_translate_oserror(dest, exc))
    return Ok(value=None)


def _cleanup_tmp(tmp: Path) -> None:
    try:
        tmp.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def _translate_oserror(path: Path, exc: OSError) -> ReportIoError:
    err_no = exc.errno if exc.errno is not None else 0
    message = exc.strerror or str(exc)
    if err_no == errno.ENOSPC:
        return ReportDiskFull(path=str(path), errno=err_no, message=message)
    if err_no == errno.EACCES:
        return ReportPermissionDenied(path=str(path), errno=err_no, message=message)
    if err_no == errno.ELOOP:
        return ReportFilesystemRace(path=str(path), errno=err_no, message=message)
    return ReportOtherIoError(path=str(path), errno=err_no, message=message)
