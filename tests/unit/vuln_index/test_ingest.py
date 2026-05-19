"""S3-03 — ingest pipeline + deterministic feed digest tests.

Covers AC-D1..D6.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from codegenie.types.identifiers import CveId, PackageName
from codegenie.vuln_index import VulnIndex, ingest_records
from codegenie.vuln_index.ingest import (
    IngestStats,
    _record_to_row,
    _update_feed_digest,
)
from codegenie.vuln_index.models import AffectedRange, VulnerabilityRecord
from codegenie.vuln_index.parsers import _MAX_ERROR_REPORT, VulnParseError


def _record(
    cve: str = "CVE-2024-21501",
    pkg: str = "express",
    fixed: str = "4.19.2",
    severity: str = "high",
    published: datetime | None = None,
) -> VulnerabilityRecord:
    return VulnerabilityRecord(
        cve_id=CveId(cve),
        ecosystem="npm",
        package=PackageName(pkg),
        affected_range=AffectedRange(introduced="0.0.0", fixed=fixed),  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        published_at=published or datetime(2024, 2, 26, 5, 15, 8, tzinfo=UTC),
        source="nvd",
    )


@pytest.fixture
def fresh_index(tmp_path: Path, alembic_upgrade) -> Iterator[VulnIndex]:  # type: ignore[no-untyped-def]
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    idx = VulnIndex(db)
    yield idx
    idx.close()


# AC-D3 — pure mapper
def test_record_to_row_is_pure() -> None:
    r = _record()
    row1 = _record_to_row(r)
    row2 = _record_to_row(r)
    assert row1 == row2
    # Column-count contract — 9 (matches storage schema, excluding raw_payload).
    assert len(row1) == 9


def test_record_to_row_optional_versions_emit_empty_sentinel() -> None:
    r = _record()  # fixed="4.19.2", last_affected=None
    row = _record_to_row(r)
    # column ordering: ..., introduced, fixed, last_affected, ...
    assert row[3] == "0.0.0"
    assert row[4] == "4.19.2"
    assert row[5] == ""  # last_affected is None → empty sentinel


# AC-D1 — stats shape + counting.
def test_ingest_stats_default_shape() -> None:
    s = IngestStats()
    assert s.inserted == 0 and s.skipped == 0
    assert s.errors == [] and s.errors_truncated == 0


def test_ingest_records_inserts_new_rows(fresh_index: VulnIndex) -> None:
    records = [
        _record(cve="CVE-2024-11111", pkg="lodash"),
        _record(cve="CVE-2024-22222", pkg="express"),
    ]
    stats = ingest_records(fresh_index, records)
    assert stats.inserted == 2
    assert stats.skipped == 0
    assert stats.errors == []


# AC-D4 — idempotency
def test_ingest_records_is_idempotent(fresh_index: VulnIndex) -> None:
    records = [_record(cve="CVE-2024-11111", pkg="lodash"), _record()]
    ingest_records(fresh_index, records)
    stats = ingest_records(fresh_index, records)
    assert stats.inserted == 0
    assert stats.skipped == len(records)


# AC-D1 — error report cap (100) + truncation counter
def test_errors_truncated_when_over_cap(fresh_index: VulnIndex) -> None:
    errors: list[VulnParseError | VulnerabilityRecord] = [
        VulnParseError(reason="bad_json", details={"i": i}) for i in range(150)
    ]
    stats = ingest_records(fresh_index, errors)
    assert len(stats.errors) == _MAX_ERROR_REPORT
    assert stats.errors_truncated == 50
    assert stats.inserted == 0


# AC-D2 + AC-D5 — no-op refresh keeps digest byte-identical
def test_no_op_refresh_keeps_digest_byte_identical(fresh_index: VulnIndex) -> None:
    records = [
        _record(cve="CVE-2024-11111", pkg="lodash"),
        _record(cve="CVE-2024-22222", pkg="express"),
        _record(cve="CVE-2024-33333", pkg="axios"),
    ]
    ingest_records(fresh_index, records)
    _update_feed_digest(fresh_index, "nvd", records)
    digest_1 = fresh_index.digest()
    # Re-ingest same content, shuffled order.
    shuffled = list(records)
    random.shuffle(shuffled)
    ingest_records(fresh_index, shuffled)
    _update_feed_digest(fresh_index, "nvd", shuffled)
    digest_2 = fresh_index.digest()
    assert digest_1 == digest_2


# AC-D2 — sort-by-cve_id determinism (direct property)
def test_update_feed_digest_is_order_independent(fresh_index: VulnIndex) -> None:
    rs1 = [
        _record(cve="CVE-2024-AAAAA", pkg="a"),
        _record(cve="CVE-2024-BBBBB", pkg="b"),
        _record(cve="CVE-2024-CCCCC", pkg="c"),
    ]
    rs2 = list(reversed(rs1))
    _update_feed_digest(fresh_index, "nvd", rs1)
    d1 = fresh_index.digest()
    _update_feed_digest(fresh_index, "nvd", rs2)
    d2 = fresh_index.digest()
    assert d1 == d2


# AC-D6 — digest changes under content change
@pytest.mark.parametrize("mutation", ["add", "remove", "mutate_severity", "mutate_range"])
def test_digest_changes_under_content_change(fresh_index: VulnIndex, mutation: str) -> None:
    base = [
        _record(cve="CVE-2024-11111", pkg="lodash"),
        _record(cve="CVE-2024-22222", pkg="express"),
    ]
    _update_feed_digest(fresh_index, "nvd", base)
    before = fresh_index.digest()

    if mutation == "add":
        mutated = [*base, _record(cve="CVE-2024-99999", pkg="axios")]
    elif mutation == "remove":
        mutated = base[:1]
    elif mutation == "mutate_severity":
        mutated = [
            _record(cve="CVE-2024-11111", pkg="lodash", severity="low"),
            _record(cve="CVE-2024-22222", pkg="express"),
        ]
    else:  # mutate_range
        mutated = [
            _record(cve="CVE-2024-11111", pkg="lodash", fixed="5.0.0"),
            _record(cve="CVE-2024-22222", pkg="express"),
        ]
    _update_feed_digest(fresh_index, "nvd", mutated)
    after = fresh_index.digest()
    assert before != after


# Parse errors do NOT contribute to the digest (load-bearing for ADR-0008)
def test_parse_errors_excluded_from_digest(fresh_index: VulnIndex) -> None:
    successes = [_record(cve="CVE-2024-11111", pkg="lodash")]
    errors = [VulnParseError(reason="bad_json", details={})]
    _update_feed_digest(fresh_index, "nvd", successes)
    d1 = fresh_index.digest()
    # Re-ingest with extra parse errors but same successes.
    ingest_records(fresh_index, [*successes, *errors])
    _update_feed_digest(fresh_index, "nvd", successes)
    d2 = fresh_index.digest()
    assert d1 == d2
