"""ADR-0015 — CVE-keyed lookup for orchestrator resolution."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from codegenie.types.identifiers import CveId, PackageName
from codegenie.vuln_index import AffectedRange, VulnerabilityRecord, VulnIndex


@pytest.fixture
def seeded_index(tmp_path: Path, alembic_upgrade) -> Iterator[VulnIndex]:  # type: ignore[no-untyped-def]
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    idx = VulnIndex(db)
    ts = datetime(2026, 5, 1, tzinfo=UTC)
    for package, severity in (("express", "high"), ("body-parser", "critical")):
        idx._raw_insert(
            VulnerabilityRecord(
                cve_id=CveId("CVE-2024-21501"),
                ecosystem="npm",
                package=PackageName(package),
                affected_range=AffectedRange(introduced="0.0.0", fixed="4.19.2"),
                severity=severity,  # type: ignore[arg-type]
                published_at=ts,
                source="nvd",
            )
        )
    idx._raw_insert(
        VulnerabilityRecord(
            cve_id=CveId("CVE-2026-0001"),
            ecosystem="pypi",
            package=PackageName("express"),
            affected_range=AffectedRange(introduced="0.0.0", fixed="1.0.0"),
            severity="medium",
            published_at=ts,
            source="osv",
        )
    )
    yield idx
    idx.close()


def test_find_by_cve_returns_all_matching_records_sorted(seeded_index: VulnIndex) -> None:
    records = seeded_index.find_by_cve(CveId("CVE-2024-21501"))

    assert [(r.ecosystem, str(r.package), r.severity) for r in records] == [
        ("npm", "body-parser", "critical"),
        ("npm", "express", "high"),
    ]


def test_find_by_cve_missing_returns_empty(seeded_index: VulnIndex) -> None:
    assert seeded_index.find_by_cve(CveId("CVE-1999-0001")) == []
