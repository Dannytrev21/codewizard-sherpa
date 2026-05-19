"""OSV (Open Source Vulnerability) feed parser + fetcher.

Cassette schema (``tests/fixtures/cve-feeds/osv/express-min.json``):

```json
{
  "id": "GHSA-rv95-896h-c2vc",
  "aliases": ["CVE-2024-21501"],
  "published": "2024-02-26T05:15:08Z",
  "database_specific": {"severity": "HIGH"},
  "affected": [
    {
      "package": {"ecosystem": "npm", "name": "express"},
      "ranges": [
        {"type": "SEMVER", "events": [{"introduced": "0.0.0"}, {"fixed": "4.19.2"}]}
      ]
    }
  ]
}
```

OSV ``events`` are a chronological list of state transitions; we collapse
the first ``introduced``/``fixed``/``last_affected`` triple into one
:class:`AffectedRange`.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import datetime
from typing import Any, ClassVar, Final

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

__all__ = ["OsvFeed"]

_FEED_URLS: Final[Mapping[str, str]] = {
    "osv": "https://osv-vulnerabilities.storage.googleapis.com/all.zip",
}

_SEVERITY_TO_LITERAL: Final[Mapping[str, str]] = {
    "LOW": "low",
    "MEDIUM": "medium",
    "MODERATE": "medium",
    "HIGH": "high",
    "CRITICAL": "critical",
}


@register_vuln_feed("osv")
class OsvFeed:
    """OSV (osv.dev) feed implementation."""

    source: ClassVar[str] = "osv"

    def parse_one(self, raw: bytes) -> Result[VulnerabilityRecord, VulnParseError]:
        env = parse_record_envelope(raw)
        if isinstance(env, Err):
            return env
        record = env.value
        if not isinstance(record, dict):
            return Err(
                error=VulnParseError(reason="missing_required_field", details={"field": "record"})
            )
        return _parse_osv_record(record)

    def fetch(
        self,
        *,
        since: datetime | None = None,
        timeout_s: float = 30.0,
    ) -> Iterator[bytes]:
        from urllib.error import URLError  # noqa: PLC0415
        from urllib.request import urlopen  # noqa: PLC0415

        url = _FEED_URLS["osv"]
        try:
            with urlopen(url, timeout=timeout_s) as response:  # noqa: S310 — allowlist
                yield response.read()
        except URLError as exc:
            raise VulnFeedFetchError(f"osv: {exc}") from exc


def _parse_osv_record(
    record: dict[str, Any],
) -> Result[VulnerabilityRecord, VulnParseError]:
    # CVE alias wins over OSV id (matches GHSA's behavior; downstream
    # consumers prefer the cross-ecosystem CVE identifier when available).
    aliases = record.get("aliases")
    cve_alias: str | None = None
    if isinstance(aliases, list):
        for a in aliases:
            if isinstance(a, str) and a.startswith("CVE-"):
                cve_alias = a
                break
    if cve_alias is not None:
        cve_result = smart_construct_cve_id(cve_alias)
        if isinstance(cve_result, Err):
            return cve_result
        cve_id = cve_result.value
    else:
        osv_id = record.get("id")
        if not isinstance(osv_id, str) or not osv_id:
            return Err(
                error=VulnParseError(reason="missing_required_field", details={"field": "id"})
            )
        cve_id = osv_id
    published_result = extract_published_at(record.get("published"))
    if isinstance(published_result, Err):
        return published_result
    db_specific = record.get("database_specific")
    sev_raw: object = None
    if isinstance(db_specific, dict):
        sev_raw = db_specific.get("severity")
    if not isinstance(sev_raw, str) or sev_raw.upper() not in _SEVERITY_TO_LITERAL:
        return Err(
            error=VulnParseError(
                reason="missing_required_field",
                details={"field": "database_specific.severity"},
            )
        )
    severity = _SEVERITY_TO_LITERAL[sev_raw.upper()]
    affected = record.get("affected")
    if not isinstance(affected, list) or not affected:
        return Err(
            error=VulnParseError(reason="missing_required_field", details={"field": "affected"})
        )
    head = affected[0]
    if not isinstance(head, dict):
        return Err(
            error=VulnParseError(reason="missing_required_field", details={"field": "affected[0]"})
        )
    pkg_obj = head.get("package")
    if not isinstance(pkg_obj, dict):
        return Err(
            error=VulnParseError(
                reason="missing_required_field", details={"field": "affected[0].package"}
            )
        )
    eco_raw = pkg_obj.get("ecosystem")
    if not isinstance(eco_raw, str):
        return Err(
            error=VulnParseError(
                reason="missing_required_field",
                details={"field": "affected[0].package.ecosystem"},
            )
        )
    eco_result = assert_ecosystem_registered(eco_raw)
    if isinstance(eco_result, Err):
        return eco_result
    pkg_name_result = smart_construct_package_name(pkg_obj.get("name"))
    if isinstance(pkg_name_result, Err):
        return pkg_name_result
    range_result = _collapse_osv_events(head.get("ranges"))
    if isinstance(range_result, Err):
        return range_result
    introduced, fixed, last_affected = range_result.value
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
                    "introduced": introduced,
                    "fixed": fixed,
                    "last_affected": last_affected,
                }
            ),
            severity=severity,  # type: ignore[arg-type]
            published_at=published_result.value,
            source="osv",
        )
    except ValueError as exc:  # pragma: no cover
        return Err(
            error=VulnParseError(
                reason="bad_semver", details={"value": str(exc), "field": "affected_range"}
            )
        )
    return Ok(value=rec)


def _collapse_osv_events(
    ranges: Any,
) -> Result[tuple[str, str | None, str | None], VulnParseError]:
    if not isinstance(ranges, list) or not ranges:
        return Err(
            error=VulnParseError(reason="missing_required_field", details={"field": "ranges"})
        )
    head = ranges[0]
    if not isinstance(head, dict):
        return Err(
            error=VulnParseError(reason="missing_required_field", details={"field": "ranges[0]"})
        )
    events = head.get("events")
    if not isinstance(events, list) or not events:
        return Err(
            error=VulnParseError(
                reason="missing_required_field", details={"field": "ranges[0].events"}
            )
        )
    introduced: str | None = None
    fixed: str | None = None
    last: str | None = None
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if "introduced" in ev and introduced is None:
            r = smart_construct_semver(ev["introduced"], field="introduced")
            if isinstance(r, Err):
                return r
            introduced = str(r.value)
        elif "fixed" in ev and fixed is None:
            r2 = smart_construct_semver(ev["fixed"], field="fixed")
            if isinstance(r2, Err):
                return r2
            fixed = str(r2.value)
        elif "last_affected" in ev and last is None:
            r3 = smart_construct_semver(ev["last_affected"], field="last_affected")
            if isinstance(r3, Err):
                return r3
            last = str(r3.value)
    if introduced is None:
        introduced = "0.0.0"
    return Ok(value=(introduced, fixed, last))
