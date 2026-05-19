"""``VulnerabilityRecord`` + ``AffectedRange`` — frozen Pydantic value objects.

S3-03 migrates ``AffectedRange.introduced/fixed/last_affected`` from raw
``str`` to :data:`SemverVersion` (closes the primitive-obsession deferred
by S3-02 §Notes). Validation routes through
:func:`codegenie.types.parsers.parse_semver` at the model boundary; the CVE
feed parsers (S3-03) drive valid semver inputs in, so this validator
double-guards the storage shape rather than the parsing shape.

ADRs: phase-3 ADR-0010 (frozen + extra="forbid" value-object discipline),
production ADR-0033 (newtypes for domain identifiers — ``PackageName``,
``CveId``, ``Ecosystem``, ``SemverVersion`` flow in from
:mod:`codegenie.types.identifiers`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from codegenie.result import Ok
from codegenie.types.identifiers import CveId, Ecosystem, PackageName, SemverVersion
from codegenie.types.parsers import parse_semver

__all__ = ["AffectedRange", "VulnerabilityRecord"]


class AffectedRange(BaseModel):
    """Half-open version range describing the vulnerable interval.

    ``fixed`` and ``last_affected`` are **independent** — ``fixed`` is the
    patched-line first-good version; ``last_affected`` is the last-good
    version on an EOL'd minor line that will never receive the patch. Either
    may be ``None``; both ``None`` ⇒ open (unbounded) vulnerability. All
    three are :data:`SemverVersion`-shaped at the construction boundary.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    introduced: SemverVersion
    fixed: SemverVersion | None = None
    last_affected: SemverVersion | None = None

    @field_validator("introduced", mode="before")
    @classmethod
    def _coerce_introduced(cls, v: object) -> SemverVersion:
        if not isinstance(v, str) or not v:
            raise ValueError("AffectedRange.introduced must be a non-empty semver string")
        parsed = parse_semver(v)
        if not isinstance(parsed, Ok):
            raise ValueError(f"AffectedRange.introduced: {parsed.error.message}")
        return parsed.value

    @field_validator("fixed", "last_affected", mode="before")
    @classmethod
    def _coerce_optional(cls, v: object) -> SemverVersion | None:
        if v is None:
            return None
        if not isinstance(v, str) or not v:
            raise ValueError("AffectedRange version strings must be non-empty semver when present")
        parsed = parse_semver(v)
        if not isinstance(parsed, Ok):
            raise ValueError(f"AffectedRange: {parsed.error.message}")
        return parsed.value


class VulnerabilityRecord(BaseModel):
    """One CVE × ecosystem × package × affected-range row in the index."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cve_id: CveId
    ecosystem: Ecosystem
    package: PackageName
    affected_range: AffectedRange
    severity: Literal["low", "medium", "high", "critical"]
    published_at: datetime
    source: Literal["nvd", "ghsa", "osv"]
