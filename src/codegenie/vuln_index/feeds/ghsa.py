"""GitHub Security Advisory (GHSA) feed parser + fetcher.

Cassette schema (``tests/fixtures/cve-feeds/ghsa/express-min.json``):

```json
{
  "ghsa_id": "GHSA-rv95-896h-c2vc",
  "cve_id": "CVE-2024-21501",
  "published_at": "2024-02-26T05:15:08Z",
  "severity": "high",
  "package": {"ecosystem": "npm", "name": "express"},
  "vulnerable_version_range": ">= 0.0.0, < 4.19.2",
  "fixed_version": "4.19.2"
}
```

We use the GHSA id as the record's ``cve_id`` when no CVE alias exists
(arch §C11 §"GHSA"); the cassette ``cve_id`` field, when present, takes
precedence.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any, ClassVar, Final, Mapping

from codegenie.errors import VulnFeedFetchError
from codegenie.result import Err, Ok, Result
from codegenie.vuln_index.feeds._common import (
    assert_ecosystem_registered,
    extract_published_at,
    parse_record_envelope,
    smart_construct_cve_id,
    smart_construct_package_name,
    smart_construct_semver,
)
from codegenie.vuln_index.models import AffectedRange, VulnerabilityRecord
from codegenie.vuln_index.parsers import (
    _MAX_RAW_PAYLOAD_BYTES,
    VulnParseError,
    canonical_raw_payload,
)
from codegenie.vuln_index.registry import register_vuln_feed

__all__ = ["GhsaFeed"]

_FEED_URLS: Final[Mapping[str, str]] = {
    "ghsa": "https://api.github.com/advisories",
}

_SEVERITY_TO_LITERAL: Final[Mapping[str, str]] = {
    "low": "low",
    "medium": "medium",
    "moderate": "medium",
    "high": "high",
    "critical": "critical",
}


@register_vuln_feed("ghsa")
class GhsaFeed:
    """GitHub Security Advisory feed implementation."""

    source: ClassVar[str] = "ghsa"

    def parse_one(self, raw: bytes) -> Result[VulnerabilityRecord, VulnParseError]:
        env = parse_record_envelope(raw)
        if isinstance(env, Err):
            return env
        record = env.value
        if not isinstance(record, dict):
            return Err(
                error=VulnParseError(
                    reason="missing_required_field", details={"field": "advisory"}
                )
            )
        return _parse_ghsa_record(record)

    def fetch(
        self,
        *,
        since: datetime | None = None,
        timeout_s: float = 30.0,
    ) -> Iterator[bytes]:
        from urllib.error import URLError  # noqa: PLC0415
        from urllib.request import urlopen  # noqa: PLC0415

        url = _FEED_URLS["ghsa"]
        try:
            with urlopen(url, timeout=timeout_s) as response:  # noqa: S310 — allowlist
                yield response.read()
        except URLError as exc:
            raise VulnFeedFetchError(f"ghsa: {exc}") from exc


def _parse_ghsa_record(
    record: dict[str, Any],
) -> Result[VulnerabilityRecord, VulnParseError]:
    # Use the CVE alias if present, else the GHSA id (acts as the canonical
    # identifier when no CVE has been assigned — common for npm package
    # advisories).
    cve_value = record.get("cve_id") or record.get("ghsa_id")
    if not isinstance(cve_value, str) or not cve_value:
        return Err(
            error=VulnParseError(
                reason="missing_required_field", details={"field": "cve_id"}
            )
        )
    if cve_value.startswith("CVE-"):
        cve_result = smart_construct_cve_id(cve_value)
        if isinstance(cve_result, Err):
            return cve_result
        cve_id = cve_result.value
    elif cve_value.startswith("GHSA-"):
        cve_id = cve_value
    else:
        return Err(
            error=VulnParseError(
                reason="bad_cve_id", details={"value": cve_value}
            )
        )
    published_result = extract_published_at(record.get("published_at"))
    if isinstance(published_result, Err):
        return published_result
    sev_raw = record.get("severity")
    if not isinstance(sev_raw, str) or sev_raw.lower() not in _SEVERITY_TO_LITERAL:
        return Err(
            error=VulnParseError(
                reason="missing_required_field", details={"field": "severity"}
            )
        )
    severity = _SEVERITY_TO_LITERAL[sev_raw.lower()]
    pkg_obj = record.get("package")
    if not isinstance(pkg_obj, dict):
        return Err(
            error=VulnParseError(
                reason="missing_required_field", details={"field": "package"}
            )
        )
    eco_raw = pkg_obj.get("ecosystem")
    if not isinstance(eco_raw, str):
        return Err(
            error=VulnParseError(
                reason="missing_required_field", details={"field": "package.ecosystem"}
            )
        )
    eco_result = assert_ecosystem_registered(eco_raw)
    if isinstance(eco_result, Err):
        return eco_result
    pkg_name_result = smart_construct_package_name(pkg_obj.get("name"))
    if isinstance(pkg_name_result, Err):
        return pkg_name_result
    # GHSA does not always carry a structured introduced version; default
    # to "0.0.0" (open-from-genesis) when fixed_version is the only signal.
    intro_result = smart_construct_semver(
        record.get("introduced", "0.0.0"), field="introduced"
    )
    if isinstance(intro_result, Err):
        return intro_result
    fixed: str | None = None
    last: str | None = None
    if record.get("fixed_version") is not None:
        fixed_result = smart_construct_semver(record["fixed_version"], field="fixed")
        if isinstance(fixed_result, Err):
            return fixed_result
        fixed = str(fixed_result.value)
    if record.get("last_affected") is not None:
        last_result = smart_construct_semver(record["last_affected"], field="last_affected")
        if isinstance(last_result, Err):
            return last_result
        last = str(last_result.value)
    raw_blob = canonical_raw_payload(record)
    if len(raw_blob) > _MAX_RAW_PAYLOAD_BYTES:
        return Err(
            error=VulnParseError(
                reason="payload_too_large",
                details={"size": len(raw_blob), "limit": _MAX_RAW_PAYLOAD_BYTES},
            )
        )
    try:
        rec = VulnerabilityRecord(
            cve_id=cve_id,  # type: ignore[arg-type]
            ecosystem=eco_result.value,
            package=pkg_name_result.value,
            affected_range=AffectedRange.model_validate(
                {
                    "introduced": intro_result.value,
                    "fixed": fixed,
                    "last_affected": last,
                }
            ),
            severity=severity,  # type: ignore[arg-type]
            published_at=published_result.value,
            source="ghsa",
        )
    except ValueError as exc:  # pragma: no cover — defensive
        return Err(
            error=VulnParseError(
                reason="bad_semver", details={"value": str(exc), "field": "affected_range"}
            )
        )
    return Ok(value=rec)
