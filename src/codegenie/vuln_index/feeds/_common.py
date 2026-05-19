"""Shared parser helpers used by every concrete feed.

Lives outside the registry / protocol modules so the protocol's
``parse_one(self, raw: bytes)`` signature stays a thin dispatch surface and
the feeds compose these helpers in their own order. Pure functions only —
no I/O, no logging, no global state. Mirrors the "functional core" half of
S3-03's functional-core / imperative-shell discipline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from codegenie.result import Err, Ok, Result
from codegenie.types.identifiers import Ecosystem, PackageName, SemverVersion
from codegenie.types.parsers import parse_cve_id, parse_package_name, parse_semver
from codegenie.vuln_index.parsers import (
    VulnParseError,
    VulnParseException,
    _check_depth,
    _safe_json_load,
)

__all__ = [
    "ECOSYSTEMS",
    "extract_published_at",
    "parse_record_envelope",
    "smart_construct_cve_id",
    "smart_construct_package_name",
    "smart_construct_semver",
]

# Closed-set membership for the parametric ``unsupported_ecosystem``
# rejection (AC-P2). Same set as :data:`Ecosystem` Literal; identity check
# rather than redefining the Literal.
ECOSYSTEMS: Final[frozenset[str]] = frozenset({"npm", "pypi", "maven", "rubygems", "gomod"})


def parse_record_envelope(raw: bytes) -> Result[object, VulnParseError]:
    """Size-cap + depth-cap + JSON decode in one helper (AC-S2 + AC-S3).

    Returns the parsed ``dict | list`` value on success; otherwise an
    ``Err`` carrying the typed parse error. Per-record raw-payload cap
    (256 KiB) is enforced by callers AFTER they extract the inner record
    object — that cap applies to the persisted BLOB, not the inbound
    chunk.
    """
    loaded = _safe_json_load(raw)
    if isinstance(loaded, Err):
        return loaded
    try:
        _check_depth(loaded.value)
    except VulnParseException as exc:
        return Err(error=exc.model)
    return loaded


def smart_construct_cve_id(value: object) -> Result[str, VulnParseError]:
    """Run the S1-01 ``parse_cve_id`` smart constructor (AC-P1)."""
    if not isinstance(value, str):
        return Err(error=VulnParseError(reason="bad_cve_id", details={"value": repr(value)[:64]}))
    parsed = parse_cve_id(value)
    if isinstance(parsed, Ok):
        return Ok(value=str(parsed.value))
    return Err(error=VulnParseError(reason="bad_cve_id", details={"value": value}))


def smart_construct_package_name(value: object) -> Result[PackageName, VulnParseError]:
    """Wrap the package-name smart constructor (used after CPE / ecosystem map)."""
    if not isinstance(value, str):
        return Err(
            error=VulnParseError(reason="missing_required_field", details={"field": "package"})
        )
    parsed = parse_package_name(value)
    if isinstance(parsed, Ok):
        return Ok(value=parsed.value)
    return Err(error=VulnParseError(reason="missing_required_field", details={"field": "package"}))


def smart_construct_semver(value: object, *, field: str) -> Result[SemverVersion, VulnParseError]:
    if not isinstance(value, str):
        return Err(
            error=VulnParseError(
                reason="bad_semver", details={"value": repr(value)[:64], "field": field}
            )
        )
    parsed = parse_semver(value)
    if isinstance(parsed, Ok):
        return Ok(value=parsed.value)
    return Err(error=VulnParseError(reason="bad_semver", details={"value": value, "field": field}))


def extract_published_at(value: object) -> Result[datetime, VulnParseError]:
    """Parse an ISO 8601 datetime; reject naive (no tzinfo) datetimes (AC-P3).

    Uses ``datetime.fromisoformat`` — Python ≥ 3.11 accepts a trailing ``Z``
    (UTC marker) on the input.
    """
    if not isinstance(value, str):
        return Err(error=VulnParseError(reason="missing_tz", details={"value": repr(value)[:64]}))
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return Err(error=VulnParseError(reason="missing_tz", details={"value": value}))
    if dt.tzinfo is None:
        return Err(error=VulnParseError(reason="missing_tz", details={"value": value}))
    return Ok(value=dt)


def assert_ecosystem_registered(value: str) -> Result[Ecosystem, VulnParseError]:
    """AC-P2 — closed-set membership check, parametric over :data:`ECOSYSTEMS`."""
    if value not in ECOSYSTEMS:
        return Err(
            error=VulnParseError(reason="unsupported_ecosystem", details={"ecosystem": value})
        )
    return Ok(value=value)  # type: ignore[arg-type]
