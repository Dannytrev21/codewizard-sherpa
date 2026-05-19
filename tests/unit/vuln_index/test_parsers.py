"""S3-03 — error model + size/depth caps + per-feed parse tests.

Covers AC-C1..C4, AC-P1..P3, AC-S1..S5, AC-R1, AC-N2.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

import pytest
from pydantic import ValidationError

from codegenie.result import Err, Ok
from codegenie.types.identifiers import PackageName
from codegenie.vuln_index.parsers import (
    _MAX_JSON_DEPTH,
    _MAX_PAYLOAD_BYTES,
    VulnParseError,
    VulnParseException,
    _check_depth,
    _safe_json_load,
    canonical_raw_payload,
)
from codegenie.vuln_index.registry import default_feed_registry

CASSETTES_DIR: Final[Path] = (
    Path(__file__).resolve().parents[2] / "fixtures" / "cve-feeds"
)


# ---------------------------------------------------------------------------
# AC-C1..C3 — error model shape
# ---------------------------------------------------------------------------


def test_vuln_parse_error_is_frozen() -> None:
    err = VulnParseError(reason="bad_json", details={"message": "bad"})
    with pytest.raises(ValidationError):
        err.reason = "bad_cve_id"  # type: ignore[misc]


def test_vuln_parse_error_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        VulnParseError(reason="bad_json", details={}, extra_field="nope")  # type: ignore[call-arg]


def test_vuln_parse_error_rejects_unknown_reason_at_runtime() -> None:
    with pytest.raises(ValidationError):
        VulnParseError(reason="typo", details={})  # type: ignore[arg-type]


def test_vuln_parse_exception_wraps_model() -> None:
    model = VulnParseError(reason="bad_cve_id", details={"value": "not-a-cve"})
    exc = VulnParseException(model)
    assert exc.model is model
    assert exc.model.reason == "bad_cve_id"


def test_vuln_parse_error_exported_in_module() -> None:
    from codegenie.vuln_index import parsers

    assert "VulnParseError" in parsers.__all__
    assert "VulnParseException" in parsers.__all__


def test_vuln_parse_exception_in_top_level_package() -> None:
    import codegenie.vuln_index as pkg

    assert "VulnParseException" in pkg.__all__
    assert "VulnParseError" in pkg.__all__


# ---------------------------------------------------------------------------
# AC-S1 — caps are module-level Final
# ---------------------------------------------------------------------------


def test_caps_are_module_constants() -> None:
    assert _MAX_PAYLOAD_BYTES == 1_048_576
    assert _MAX_JSON_DEPTH == 16


# ---------------------------------------------------------------------------
# AC-S3 — depth boundary
# ---------------------------------------------------------------------------


def _build_nested(depth: int) -> dict:
    """Build a dict whose deepest leaf sits at the given depth.

    ``depth=1`` is the bare ``{}``; ``depth=2`` is ``{"x": {}}``; etc.
    """
    root: dict = {}
    cur = root
    for _ in range(depth - 1):
        cur["x"] = {}
        cur = cur["x"]
    return root


def test_depth_cap_accepts_exactly_16() -> None:
    _check_depth(_build_nested(16))


def test_depth_cap_rejects_17() -> None:
    with pytest.raises(VulnParseException) as exc_info:
        _check_depth(_build_nested(17))
    assert exc_info.value.model.reason == "json_too_deep"
    assert exc_info.value.model.details["depth"] == 17


# ---------------------------------------------------------------------------
# AC-S4 — size boundary
# ---------------------------------------------------------------------------


def test_size_cap_accepts_exactly_1mib() -> None:
    raw = b"a" * 1_048_576
    result = _safe_json_load(raw)
    # NOT payload_too_large; json parse fails because "aaaa..." isn't valid JSON.
    assert isinstance(result, Err)
    assert result.error.reason == "bad_json"


def test_size_cap_rejects_1mib_plus_one() -> None:
    raw = b"a" * 1_048_577
    result = _safe_json_load(raw)
    assert isinstance(result, Err)
    assert result.error.reason == "payload_too_large"
    assert result.error.details == {"size": 1_048_577, "limit": 1_048_576}


def test_size_cap_valid_small_json_returns_ok() -> None:
    raw = json.dumps({"hello": "world"}).encode("utf-8")
    result = _safe_json_load(raw)
    assert isinstance(result, Ok)
    assert result.value == {"hello": "world"}


# ---------------------------------------------------------------------------
# AC-P1 — bad cve id rejected per-feed
# ---------------------------------------------------------------------------


def _cassette(source: str, name: str) -> bytes:
    return (CASSETTES_DIR / source / name).read_bytes()


@pytest.mark.parametrize("source", ["nvd", "ghsa", "osv"])
def test_parser_rejects_malformed_cve_id(source: str) -> None:
    feed = default_feed_registry.get_feed(source)
    result = feed.parse_one(_cassette(source, "malformed-bad_cve.json"))
    assert isinstance(result, Err)
    assert result.error.reason == "bad_cve_id"


# ---------------------------------------------------------------------------
# AC-P3 — naive datetime rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["nvd", "ghsa", "osv"])
def test_parser_rejects_naive_datetime(source: str) -> None:
    feed = default_feed_registry.get_feed(source)
    result = feed.parse_one(_cassette(source, "malformed-no_tz.json"))
    assert isinstance(result, Err)
    assert result.error.reason == "missing_tz"


# ---------------------------------------------------------------------------
# AC-P2 — unsupported ecosystem rejection parametric over registered set
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["nvd", "ghsa", "osv"])
def test_parser_rejects_unsupported_ecosystem(source: str) -> None:
    feed = default_feed_registry.get_feed(source)
    result = feed.parse_one(_cassette(source, "malformed-wrong_eco.json"))
    assert isinstance(result, Err)
    assert result.error.reason == "unsupported_ecosystem"
    assert "ecosystem" in result.error.details


# ---------------------------------------------------------------------------
# Happy path — per-feed minimal record parses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source,expected_cve",
    [
        ("nvd", "CVE-2024-21501"),
        ("ghsa", "CVE-2024-21501"),
        ("osv", "CVE-2024-21501"),
    ],
)
def test_minimal_record_parses(source: str, expected_cve: str) -> None:
    feed = default_feed_registry.get_feed(source)
    result = feed.parse_one(_cassette(source, "express-min.json"))
    assert isinstance(result, Ok)
    rec = result.value
    assert str(rec.cve_id) == expected_cve
    assert rec.package == PackageName("express")
    assert rec.ecosystem == "npm"
    assert rec.severity == "high"
    assert str(rec.affected_range.fixed) == "4.19.2"


# ---------------------------------------------------------------------------
# Depth cassette routes through the actual parser surface
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source", ["nvd", "ghsa", "osv"])
def test_parser_rejects_depth_17_via_cassette(source: str) -> None:
    feed = default_feed_registry.get_feed(source)
    result = feed.parse_one(_cassette(source, "malformed-depth.json"))
    assert isinstance(result, Err)
    assert result.error.reason == "json_too_deep"


# ---------------------------------------------------------------------------
# AC-S5 — per-record raw_payload cap (256 KiB) — distinct from fetch cap
# ---------------------------------------------------------------------------


def test_per_record_raw_payload_cap_enforced() -> None:
    """A record under the 1 MiB fetch cap but over the 256 KiB per-row cap rejects."""
    big = "x" * 300_000  # 300 KiB filler — exceeds 256 KiB
    payload = {
        "cve": {
            "id": "CVE-2024-21501",
            "published": "2024-02-26T05:15:08+00:00",
            "metrics": {"cvssMetricV31": [{"baseSeverity": "HIGH"}]},
            "padding": big,
        },
        "affected": {
            "package": "express",
            "ecosystem": "npm",
            "ranges": [{"introduced": "0.0.0", "fixed": "4.19.2"}],
        },
    }
    raw = json.dumps(payload).encode("utf-8")
    assert len(raw) < _MAX_PAYLOAD_BYTES  # under 1 MiB fetch cap
    result = default_feed_registry.get_feed("nvd").parse_one(raw)
    assert isinstance(result, Err)
    assert result.error.reason == "payload_too_large"
    assert result.error.details["limit"] == 262_144
    assert result.error.details["size"] > 262_144


# ---------------------------------------------------------------------------
# canonical_raw_payload determinism — sorted keys, no whitespace
# ---------------------------------------------------------------------------


def test_canonical_raw_payload_sorts_keys() -> None:
    p1 = canonical_raw_payload({"b": 2, "a": 1, "c": 3})
    p2 = canonical_raw_payload({"c": 3, "a": 1, "b": 2})
    assert p1 == p2
    assert p1 == b'{"a":1,"b":2,"c":3}'
