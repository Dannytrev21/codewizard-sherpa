"""S3-02 — VulnerabilityRecord / AffectedRange / error model shape tests.

Covers AC-B2, AC-B3, AC-B4, AC-C1..C4.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from codegenie.types.identifiers import CveId, PackageName
from codegenie.vuln_index import (
    AffectedRange,
    VulnerabilityRecord,
    VulnIndexConfigError,
    VulnIndexException,
    VulnIndexLookupError,
)

# ---- AffectedRange (AC-B3) -------------------------------------------------


def test_affected_range_minimal_introduced_only() -> None:
    r = AffectedRange(introduced="0.0.0")
    assert r.fixed is None
    assert r.last_affected is None


def test_affected_range_full() -> None:
    r = AffectedRange(introduced="0.0.0", fixed="4.19.2", last_affected="3.99.99")
    assert r.fixed == "4.19.2"
    assert r.last_affected == "3.99.99"


def test_affected_range_frozen() -> None:
    r = AffectedRange(introduced="0.0.0")
    with pytest.raises(ValidationError):
        r.introduced = "1.0.0"  # type: ignore[misc]


def test_affected_range_rejects_empty_introduced() -> None:
    with pytest.raises(ValidationError):
        AffectedRange(introduced="")


def test_affected_range_rejects_empty_fixed() -> None:
    with pytest.raises(ValidationError):
        AffectedRange(introduced="0.0.0", fixed="")


def test_affected_range_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        AffectedRange(introduced="0.0.0", extra_field="boom")  # type: ignore[call-arg]


# ---- VulnerabilityRecord (AC-B2, AC-B4) ------------------------------------


def test_vulnerability_record_round_trips_tz_aware_published_at() -> None:
    when = datetime(2024, 3, 1, 12, 0, 0, tzinfo=UTC)
    rec = VulnerabilityRecord(
        cve_id=CveId("CVE-2024-21501"),
        ecosystem="npm",
        package=PackageName("express"),
        affected_range=AffectedRange(introduced="0.0.0", fixed="4.19.2"),
        severity="high",
        published_at=when,
        source="nvd",
    )
    assert rec.published_at.tzinfo is not None
    assert rec.published_at == when


def test_vulnerability_record_frozen() -> None:
    rec = VulnerabilityRecord(
        cve_id=CveId("CVE-2024-21501"),
        ecosystem="npm",
        package=PackageName("express"),
        affected_range=AffectedRange(introduced="0.0.0"),
        severity="high",
        published_at=datetime.now(UTC),
        source="nvd",
    )
    with pytest.raises(ValidationError):
        rec.severity = "critical"  # type: ignore[misc]


def test_vulnerability_record_rejects_bad_severity() -> None:
    with pytest.raises(ValidationError):
        VulnerabilityRecord(
            cve_id=CveId("CVE-2024-21501"),
            ecosystem="npm",
            package=PackageName("express"),
            affected_range=AffectedRange(introduced="0.0.0"),
            severity="urgent",  # type: ignore[arg-type]
            published_at=datetime.now(UTC),
            source="nvd",
        )


def test_vulnerability_record_rejects_bad_source() -> None:
    with pytest.raises(ValidationError):
        VulnerabilityRecord(
            cve_id=CveId("CVE-2024-21501"),
            ecosystem="npm",
            package=PackageName("express"),
            affected_range=AffectedRange(introduced="0.0.0"),
            severity="high",
            published_at=datetime.now(UTC),
            source="snyk",  # type: ignore[arg-type]
        )


def test_vulnerability_record_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        VulnerabilityRecord(
            cve_id=CveId("CVE-2024-21501"),
            ecosystem="npm",
            package=PackageName("express"),
            affected_range=AffectedRange(introduced="0.0.0"),
            severity="high",
            published_at=datetime.now(UTC),
            source="nvd",
            extra_field="boom",  # type: ignore[call-arg]
        )


# ---- Error models (AC-C1..C4) ----------------------------------------------


def test_lookup_error_typed_reason_ok() -> None:
    err = VulnIndexLookupError(reason="cve_not_found")
    assert err.reason == "cve_not_found"
    assert err.details == {}


def test_lookup_error_with_details() -> None:
    err = VulnIndexLookupError(reason="closed", details={"path": "/tmp/x"})
    assert err.details["path"] == "/tmp/x"


def test_lookup_error_rejects_unknown_reason() -> None:
    with pytest.raises(ValidationError):
        VulnIndexLookupError(reason="typo", details={})  # type: ignore[arg-type]


def test_lookup_error_frozen() -> None:
    err = VulnIndexLookupError(reason="closed")
    with pytest.raises(ValidationError):
        err.reason = "cve_not_found"  # type: ignore[misc]


def test_lookup_error_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        VulnIndexLookupError(reason="closed", extra="boom")  # type: ignore[call-arg]


def test_config_error_typed_reason_ok() -> None:
    err = VulnIndexConfigError(reason="invalid_max_age", details={"value": "7.5"})
    assert err.reason == "invalid_max_age"
    assert err.details["value"] == "7.5"


def test_config_error_rejects_unknown_reason() -> None:
    with pytest.raises(ValidationError):
        VulnIndexConfigError(reason="other", details={})  # type: ignore[arg-type]


def test_exception_wraps_model() -> None:
    """AC-C3 — VulnIndexException exposes the typed model."""
    model = VulnIndexLookupError(reason="cve_not_found", details={"cve_id": "CVE-1"})
    try:
        raise VulnIndexException(model)
    except VulnIndexException as e:
        assert e.model.reason == "cve_not_found"
        assert e.model.details["cve_id"] == "CVE-1"


def test_exception_can_wrap_config_error() -> None:
    model = VulnIndexConfigError(reason="non_positive_max_age", details={"value": "0"})
    try:
        raise VulnIndexException(model)
    except VulnIndexException as e:
        assert isinstance(e.model, VulnIndexConfigError)
        assert e.model.reason == "non_positive_max_age"
