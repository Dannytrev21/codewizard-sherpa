"""``VulnerabilityRecord`` + ``AffectedRange`` — frozen Pydantic value objects.

Schema-validation only — semver shape validation for
``introduced``/``fixed``/``last_affected`` is S3-03's ingest concern (this
story accepts non-empty strings only).

ADRs: phase-3 ADR-0010 (frozen + extra="forbid" value-object discipline),
production ADR-0033 (newtypes for domain identifiers — ``PackageName``,
``CveId``, ``Ecosystem`` flow in from :mod:`codegenie.types.identifiers`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from codegenie.types.identifiers import CveId, Ecosystem, PackageName

__all__ = ["AffectedRange", "VulnerabilityRecord"]


class AffectedRange(BaseModel):
    """Half-open version range describing the vulnerable interval.

    ``fixed`` and ``last_affected`` are **independent** — ``fixed`` is the
    patched-line first-good version; ``last_affected`` is the last-good
    version on an EOL'd minor line that will never receive the patch. Either
    may be ``None``; both ``None`` ⇒ open (unbounded) vulnerability.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    introduced: str
    fixed: str | None = None
    last_affected: str | None = None

    @field_validator("introduced")
    @classmethod
    def _introduced_non_empty(cls, v: str) -> str:
        if not v:
            raise ValueError("AffectedRange.introduced must be non-empty")
        return v

    @field_validator("fixed", "last_affected")
    @classmethod
    def _optional_non_empty(cls, v: str | None) -> str | None:
        if v is not None and not v:
            raise ValueError("AffectedRange version strings must be non-empty when present")
        return v


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
