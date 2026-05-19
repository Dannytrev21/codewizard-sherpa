"""NVD JSON 2.0 feed parser + fetcher.

Cassette / test corpus drives the parser shape — the upstream NVD 2.0
``/cves/2.0`` endpoint returns ``{"vulnerabilities": [{"cve": {...}}, ...]}``.
For the per-record parser surface, this module accepts ONE record-shaped
chunk: a JSON object of the form documented in
``tests/fixtures/cve-feeds/README.md``:

```json
{
  "cve": {
    "id": "CVE-2024-21501",
    "published": "2024-02-26T05:15:08Z",
    "metrics": {"cvssMetricV31": [{"baseSeverity": "HIGH"}]}
  },
  "configurations": [
    {"nodes": [{"cpeMatch": [{"criteria": "cpe:2.3:a:expressjs:express:*"}]}]}
  ],
  "affected": {"package": "express", "ecosystem": "npm", "ranges": [
    {"introduced": "0.0.0", "fixed": "4.19.2"}
  ]}
}
```

The cassette schema deliberately collapses the NVD CPE configuration tree
into an explicit ``affected`` block so this Phase-3 implementation can
exercise per-feed parser correctness without needing the full CPE
projection. Phase 4+ widens this when the real-network refresh story lands.

ADRs: phase-3 ADR-0010 (Open/Closed seam — registered via decorator).
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

__all__ = ["NvdFeed"]

# Module-level allowlist (AC-N1). Lazy-resolved at fetch time so a test
# helper can monkeypatch through the module, but production code paths
# only ever read this value.
_FEED_URLS: Final[Mapping[str, str]] = {
    "nvd": "https://services.nvd.nist.gov/rest/json/cves/2.0",
}

_SEVERITY_TO_LITERAL: Final[Mapping[str, str]] = {
    "LOW": "low",
    "MEDIUM": "medium",
    "HIGH": "high",
    "CRITICAL": "critical",
}


@register_vuln_feed("nvd")
class NvdFeed:
    """NVD JSON 2.0 feed implementation. Stateless."""

    source: ClassVar[str] = "nvd"

    def parse_one(self, raw: bytes) -> Result[VulnerabilityRecord, VulnParseError]:
        env = parse_record_envelope(raw)
        if isinstance(env, Err):
            return env
        record = env.value
        if not isinstance(record, dict):
            return Err(
                error=VulnParseError(
                    reason="missing_required_field", details={"field": "cve"}
                )
            )
        return _parse_nvd_record(record)

    def fetch(
        self,
        *,
        since: datetime | None = None,
        timeout_s: float = 30.0,
    ) -> Iterator[bytes]:
        # Lazy-imported per AC-N3 — cold-start fence asserts urllib.request
        # does NOT enter sys.modules at ``import codegenie.vuln_index.parsers``.
        from urllib.error import URLError  # noqa: PLC0415 — cold-start budget
        from urllib.request import urlopen  # noqa: PLC0415

        url = _FEED_URLS["nvd"]
        try:
            with urlopen(url, timeout=timeout_s) as response:  # noqa: S310 — allowlist
                yield response.read()
        except URLError as exc:
            raise VulnFeedFetchError(f"nvd: {exc}") from exc


def _parse_nvd_record(
    record: dict[str, Any],
) -> Result[VulnerabilityRecord, VulnParseError]:
    cve_obj = record.get("cve")
    if not isinstance(cve_obj, dict):
        return Err(
            error=VulnParseError(
                reason="missing_required_field", details={"field": "cve"}
            )
        )
    cve_result = smart_construct_cve_id(cve_obj.get("id"))
    if isinstance(cve_result, Err):
        return cve_result
    published_result = extract_published_at(cve_obj.get("published"))
    if isinstance(published_result, Err):
        return published_result
    severity = _extract_nvd_severity(cve_obj)
    if severity is None:
        return Err(
            error=VulnParseError(
                reason="missing_required_field", details={"field": "metrics.baseSeverity"}
            )
        )
    affected_obj = record.get("affected")
    if not isinstance(affected_obj, dict):
        return Err(
            error=VulnParseError(
                reason="missing_required_field", details={"field": "affected"}
            )
        )
    eco_raw = affected_obj.get("ecosystem")
    if not isinstance(eco_raw, str):
        return Err(
            error=VulnParseError(
                reason="missing_required_field", details={"field": "affected.ecosystem"}
            )
        )
    eco_result = assert_ecosystem_registered(eco_raw)
    if isinstance(eco_result, Err):
        return eco_result
    pkg_result = smart_construct_package_name(affected_obj.get("package"))
    if isinstance(pkg_result, Err):
        return pkg_result
    range_result = _extract_first_range(affected_obj.get("ranges"))
    if isinstance(range_result, Err):
        return range_result
    introduced, fixed, last_affected = range_result.value
    # AC-S5 — per-record raw_payload cap (256 KiB).
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
            cve_id=cve_result.value,  # type: ignore[arg-type]
            ecosystem=eco_result.value,
            package=pkg_result.value,
            affected_range=AffectedRange.model_validate(
                {
                    "introduced": introduced,
                    "fixed": fixed,
                    "last_affected": last_affected,
                }
            ),
            severity=severity,  # type: ignore[arg-type]
            published_at=published_result.value,
            source="nvd",
        )
    except ValueError as exc:  # pragma: no cover — defensive
        return Err(
            error=VulnParseError(
                reason="bad_semver", details={"value": str(exc), "field": "affected_range"}
            )
        )
    return Ok(value=rec)


def _extract_nvd_severity(cve_obj: dict[str, Any]) -> str | None:
    metrics = cve_obj.get("metrics")
    if not isinstance(metrics, dict):
        return None
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        block = metrics.get(key)
        if isinstance(block, list) and block:
            head = block[0]
            if isinstance(head, dict):
                base = head.get("baseSeverity")
                if isinstance(base, str):
                    return _SEVERITY_TO_LITERAL.get(base.upper())
    return None


def _extract_first_range(
    ranges: Any,
) -> Result[tuple[str, str | None, str | None], VulnParseError]:
    if not isinstance(ranges, list) or not ranges:
        return Err(
            error=VulnParseError(
                reason="missing_required_field", details={"field": "affected.ranges"}
            )
        )
    head = ranges[0]
    if not isinstance(head, dict):
        return Err(
            error=VulnParseError(
                reason="missing_required_field", details={"field": "affected.ranges[0]"}
            )
        )
    introduced_raw = head.get("introduced", "0.0.0")
    intro_result = smart_construct_semver(introduced_raw, field="introduced")
    if isinstance(intro_result, Err):
        return intro_result
    fixed_raw = head.get("fixed")
    last_raw = head.get("last_affected")
    fixed: str | None = None
    last: str | None = None
    if fixed_raw is not None:
        fixed_result = smart_construct_semver(fixed_raw, field="fixed")
        if isinstance(fixed_result, Err):
            return fixed_result
        fixed = str(fixed_result.value)
    if last_raw is not None:
        last_result = smart_construct_semver(last_raw, field="last_affected")
        if isinstance(last_result, Err):
            return last_result
        last = str(last_result.value)
    return Ok(value=(str(intro_result.value), fixed, last))
