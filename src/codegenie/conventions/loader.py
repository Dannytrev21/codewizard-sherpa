"""``ConventionsCatalogLoader`` — multi-file partial-success YAML loader.

Reads every ``*.yaml`` / ``*.yml`` file under the supplied ``search_paths``
through the :mod:`codegenie.parsers.safe_yaml` chokepoint, validates each
file as a :class:`~codegenie.conventions.catalog.Catalog`, and returns a
:class:`CatalogLoadOutcome` carrying the merged rule list alongside any
per-file errors. The :class:`FatalLoadError` shape is reserved for the
catastrophic case where every entry in ``search_paths`` is unreadable.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
  §"Component design" #10, §"Failure behavior".
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0007-no-plugin-loader-in-phase-2.md``
  — kernel-side scaffolding only.
- ``docs/production/adrs/0033-domain-modeling-discipline.md`` §1, §3-4 —
  newtype discipline, illegal-states-unrepresentable for the per-file
  error union.
"""

from __future__ import annotations

import errno
import json
import os
from pathlib import Path
from typing import Annotated, Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from codegenie.conventions.catalog import Catalog
from codegenie.conventions.model import ConventionRule
from codegenie.errors import (
    DepthCapExceeded as DepthCapExceededError,
)
from codegenie.errors import (
    MalformedYAMLError,
    SymlinkRefusedError,
)
from codegenie.errors import (
    SizeCapExceeded as SizeCapExceededError,
)
from codegenie.parsers import safe_yaml
from codegenie.result import Err, Ok, Result

__all__ = [
    "CatalogFileUnreadable",
    "CatalogLoadOutcome",
    "ConventionsCatalogLoader",
    "ConventionsError",
    "DepthCapExceeded",
    "FatalLoadError",
    "SchemaError",
    "SizeCapExceeded",
    "SymlinkRefused",
    "UnknownPatternType",
    "UnsafeYaml",
]


# Per-catalog-file cap. ``safe_yaml.load`` enforces a pre-parse size cap; this
# mirrors S2-01 SkillsLoader's frontmatter cap. 1 MiB is large enough for any
# realistic conventions catalog (Phase 2 fixtures cap out at a few KB).
_CATALOG_FILE_MAX_BYTES = 1 << 20

_DEFAULT_USER_TIER = Path("~/.codegenie/conventions/").expanduser()
_DEFAULT_REPO_TIER = Path(".codegenie/conventions/")

_EVENT_LOAD_FAILED = "conventions_catalog_load_failed"

_logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Per-file error variants — Pydantic discriminated union over ``reason``.
# Mirrors S2-01 SkillsLoadError convention (field names ``reason`` + ``path``
# + optional details; same shape so Phase 3 plugins can match uniformly).
# ---------------------------------------------------------------------------


class UnknownPatternType(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: Literal["unknown_pattern_type"] = "unknown_pattern_type"
    path: Path
    offending_kind: str


class SchemaError(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: Literal["schema"] = "schema"
    path: Path
    details: list[dict[str, object]]


class SymlinkRefused(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: Literal["symlink_refused"] = "symlink_refused"
    path: Path


class UnsafeYaml(BaseModel):
    """Umbrella for every ``MalformedYAMLError`` cause.

    A YAML parse failure can be a hostile ``!!python/object`` constructor
    exploit, a syntactic ``ParserError``, a ``ScannerError``, or a
    top-level-non-mapping. ``safe_yaml.load`` fuses all of these into a
    single :class:`MalformedYAMLError`; the operational response is the
    same (inspect the file before re-running), so the umbrella naming
    matches the response (S2-01 convention; story §"Validation notes" B6).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: Literal["unsafe_yaml"] = "unsafe_yaml"
    path: Path


class SizeCapExceeded(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: Literal["size_cap_exceeded"] = "size_cap_exceeded"
    path: Path


class DepthCapExceeded(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: Literal["depth_cap_exceeded"] = "depth_cap_exceeded"
    path: Path


class CatalogFileUnreadable(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    reason: Literal["catalog_file_unreadable"] = "catalog_file_unreadable"
    path: Path
    errno_name: str


ConventionsError = Annotated[
    UnknownPatternType
    | SchemaError
    | SymlinkRefused
    | UnsafeYaml
    | SizeCapExceeded
    | DepthCapExceeded
    | CatalogFileUnreadable,
    Field(discriminator="reason"),
]


# ---------------------------------------------------------------------------
# Outcome shapes.
# ---------------------------------------------------------------------------


class CatalogLoadOutcome(BaseModel):
    """Result-of-``load_all`` payload: merged catalog + per-file errors."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    catalog: Catalog
    per_file_errors: list[ConventionsError]


class FatalLoadError(BaseModel):
    """Catastrophic failure — emitted only when no search path is readable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: Literal["no_search_path_readable"] = "no_search_path_readable"
    paths: list[Path]


# ---------------------------------------------------------------------------
# Pure helper — Pydantic ValidationError classifier.
# ---------------------------------------------------------------------------


def _classify_validation_error(
    exc: ValidationError, path: Path
) -> UnknownPatternType | SchemaError:
    """Split discriminator-tag failures from schema-shape failures.

    Pydantic v2 reports a discriminated-union mismatch as one of
    ``"union_tag_invalid"`` / ``"union_tag_not_found"``. The offending
    ``kind`` lives in the row's ``ctx.tag`` field (the input dict that
    failed to dispatch sits under ``input``). Everything else (extra
    fields, missing required keys, regex-compile failures via the
    ``model_validator``) is a :class:`SchemaError`.

    Returns the first matching :class:`UnknownPatternType` when a tag
    failure is present, otherwise a :class:`SchemaError` carrying every
    row from ``exc.errors()``.
    """
    tag_failure_types = {"union_tag_invalid", "union_tag_not_found"}
    for row in exc.errors():
        if row.get("type") not in tag_failure_types:
            continue
        ctx = row.get("ctx") or {}
        offending = ctx.get("tag")
        if offending is None:
            # Fallback: pull from input dict's ``kind`` key.
            raw_input = row.get("input")
            if isinstance(raw_input, dict):
                offending = raw_input.get("kind")
        if offending is None:
            continue
        return UnknownPatternType(
            path=path,
            offending_kind=str(offending),
        )
    # Use ``ValidationError.json()`` to obtain a JSON-safe representation;
    # the raw ``errors()`` output can carry non-serialisable instances (e.g.,
    # ``ctx.error: ValueError`` from a ``model_validator`` failure).
    details: list[dict[str, object]] = json.loads(exc.json())
    return SchemaError(path=path, details=details)


_YamlFailureClassified = (
    SymlinkRefused | UnsafeYaml | SizeCapExceeded | DepthCapExceeded | CatalogFileUnreadable
)


def _classify_yaml_failure(exc: Exception, path: Path) -> _YamlFailureClassified | None:
    """Map a ``safe_yaml.load`` failure to the per-file error variant.

    Returns ``None`` for unknown exception types (caller re-raises).
    """
    if isinstance(exc, SymlinkRefusedError):
        return SymlinkRefused(path=path)
    if isinstance(exc, SizeCapExceededError):
        return SizeCapExceeded(path=path)
    if isinstance(exc, DepthCapExceededError):
        return DepthCapExceeded(path=path)
    if isinstance(exc, MalformedYAMLError):
        return UnsafeYaml(path=path)
    if isinstance(exc, OSError):
        return CatalogFileUnreadable(
            path=path,
            errno_name=errno.errorcode.get(exc.errno or 0, "EUNKNOWN"),
        )
    return None


# ---------------------------------------------------------------------------
# ConventionsCatalogLoader — pure-data ``__init__``; first I/O on ``load_all``.
# ---------------------------------------------------------------------------


class ConventionsCatalogLoader:
    """Multi-file YAML loader for the org conventions catalog.

    Constructor is pure data. ``load_all()`` is the only I/O entry point;
    it returns a partial-success outcome by default (one malformed catalog
    yields a ``per_file_errors`` entry; other catalogs still load). The
    :class:`FatalLoadError` shape is reserved for the catastrophic case
    where every entry in ``search_paths`` is unreadable.
    """

    def __init__(self, search_paths: list[Path]) -> None:
        self._search_paths: list[Path] = [Path(p) for p in search_paths]

    @classmethod
    def default(cls) -> ConventionsCatalogLoader:
        """Construct with the pinned ``[user, repo]`` ordering.

        ``~/.codegenie/conventions/`` then ``.codegenie/conventions/``.
        Phase 2 ships without an org tier for conventions (the
        merge-precedence story for cross-tier convention rules is
        deferred to Phase 4+).
        """
        return cls(search_paths=[_DEFAULT_USER_TIER, _DEFAULT_REPO_TIER])

    def load_all(self) -> Result[CatalogLoadOutcome, FatalLoadError]:
        """Walk every search path and load every ``*.yaml`` / ``*.yml`` file."""
        if self._search_paths:
            readable = [p for p in self._search_paths if os.access(p, os.R_OK)]
            if not readable:
                return Err(
                    error=FatalLoadError(
                        reason="no_search_path_readable",
                        paths=list(self._search_paths),
                    )
                )

        merged_rules: list[ConventionRule] = []
        per_file_errors: list[ConventionsError] = []

        for search_path in self._search_paths:
            if not search_path.is_dir():
                continue
            catalog_files = sorted(set(search_path.glob("*.yaml")) | set(search_path.glob("*.yml")))
            for catalog_path in catalog_files:
                err = self._load_one_catalog(catalog_path, merged_rules)
                if err is not None:
                    per_file_errors.append(err)
                    _logger.warning(_EVENT_LOAD_FAILED, **err.model_dump(mode="json"))

        return Ok(
            value=CatalogLoadOutcome(
                catalog=Catalog(rules=merged_rules),
                per_file_errors=per_file_errors,
            )
        )

    def _load_one_catalog(
        self, catalog_path: Path, merged_rules: list[ConventionRule]
    ) -> ConventionsError | None:
        """Parse + validate one catalog file. Returns an error or ``None``."""
        try:
            data = safe_yaml.load(catalog_path, max_bytes=_CATALOG_FILE_MAX_BYTES)
        except Exception as exc:
            classified = _classify_yaml_failure(exc, catalog_path)
            if classified is not None:
                return classified
            raise

        try:
            sub_catalog = Catalog.model_validate(dict(data))
        except ValidationError as exc:
            return _classify_validation_error(exc, catalog_path)
        merged_rules.extend(sub_catalog.rules)
        return None
