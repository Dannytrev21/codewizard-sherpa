"""Pure aggregation helpers for :mod:`~codegenie.probes.layer_c.cve` (S5-04).

Extracted from :mod:`cve` so the probe module stays under its 200-source-
line budget. Every function here is a pure transform on
:class:`GrypeJsonSchema` — no IO, no side effects, no randomness.
"""

from __future__ import annotations

from typing import Any, Final

from codegenie.probes.layer_c._cve_models import GrypeJsonSchema

_SEVERITY_ORDER: Final[dict[str, int]] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "negligible": 4,
}
_BUCKETS: Final[tuple[str, ...]] = ("critical", "high", "medium", "low", "negligible")
_TOP_FINDINGS_N: Final[int] = 20


def _normalize_severity(raw: str) -> str:
    s = raw.strip().lower()
    return s if s in _SEVERITY_ORDER else "negligible"


def _by_severity(parsed: GrypeJsonSchema) -> dict[str, int]:
    counts: dict[str, int] = dict.fromkeys(_BUCKETS, 0)
    for m in parsed.matches:
        counts[_normalize_severity(m.vulnerability.severity)] += 1
    return counts


def _by_source(parsed: GrypeJsonSchema) -> dict[str, int]:
    counts: dict[str, int] = {}
    for m in parsed.matches:
        key = m.artifact.type or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _top_findings(parsed: GrypeJsonSchema) -> list[dict[str, Any]]:
    """Deterministic top-N: severity desc → package name asc → CVE id asc.

    Stable across runs and across input permutations.
    """
    rows = [
        {
            "cve_id": m.vulnerability.id,
            "package_name": m.artifact.name,
            "severity": _normalize_severity(m.vulnerability.severity),
            "fix_state": m.vulnerability.fix.state,
        }
        for m in parsed.matches
    ]
    rows.sort(
        key=lambda r: (
            _SEVERITY_ORDER.get(str(r["severity"]), 999),
            str(r["package_name"]),
            str(r["cve_id"]),
        )
    )
    return rows[:_TOP_FINDINGS_N]


def _empty_buckets() -> dict[str, int]:
    return dict.fromkeys(_BUCKETS, 0)


__all__ = [
    "_BUCKETS",
    "_SEVERITY_ORDER",
    "_TOP_FINDINGS_N",
    "_by_severity",
    "_by_source",
    "_empty_buckets",
    "_normalize_severity",
    "_top_findings",
]
