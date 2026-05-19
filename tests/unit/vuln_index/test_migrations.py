"""S3-02 — Alembic upgrade + sqlite schema shape tests.

Covers AC-D1, AC-D2, AC-D3, AC-D4, AC-D5, AC-D6, AC-D7, AC-E2.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from codegenie.types.identifiers import CveId, PackageName
from codegenie.vuln_index import (
    AffectedRange,
    VulnerabilityRecord,
    VulnIndex,
)


def _make_record(cve: str = "CVE-2024-21501") -> VulnerabilityRecord:
    return VulnerabilityRecord(
        cve_id=CveId(cve),
        ecosystem="npm",
        package=PackageName("express"),
        affected_range=AffectedRange(introduced="0.0.0", fixed="4.19.2"),
        severity="high",
        published_at=datetime(2024, 3, 1, tzinfo=UTC),
        source="nvd",
    )


def test_alembic_upgrade_creates_tables(tmp_path: Path, alembic_upgrade) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"vulnerabilities", "meta", "alembic_version"} <= tables


def test_vulnerabilities_columns_pinned(tmp_path: Path, alembic_upgrade) -> None:  # type: ignore[no-untyped-def]
    """AC-D1 — column set + nullability matches the contract."""
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    conn = sqlite3.connect(db)
    cols = list(conn.execute("PRAGMA table_info('vulnerabilities')"))
    conn.close()
    by_name = {row[1]: row for row in cols}
    expected = {
        "id",
        "cve_id",
        "ecosystem",
        "package",
        "introduced",
        "fixed",
        "last_affected",
        "severity",
        "published_at",
        "source",
        "raw_payload",
    }
    assert set(by_name.keys()) == expected
    # notnull semantics: 3rd field (index 3) is the notnull flag in PRAGMA.
    assert by_name["cve_id"][3] == 1
    assert by_name["ecosystem"][3] == 1
    assert by_name["package"][3] == 1
    assert by_name["introduced"][3] == 1
    assert by_name["severity"][3] == 1
    assert by_name["published_at"][3] == 1
    assert by_name["source"][3] == 1
    assert by_name["raw_payload"][3] == 1
    # Nullable fields.
    assert by_name["fixed"][3] == 0
    assert by_name["last_affected"][3] == 0


def test_composite_index_columns_in_order(tmp_path: Path, alembic_upgrade) -> None:  # type: ignore[no-untyped-def]
    """AC-D2 — pinned (ecosystem, package) column order on idx_vuln_pkg_eco."""
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    conn = sqlite3.connect(db)
    cols = [(r[0], r[2]) for r in conn.execute("PRAGMA index_info('idx_vuln_pkg_eco')")]
    conn.close()
    assert cols == [(0, "ecosystem"), (1, "package")]


def test_explain_query_plan_uses_composite_index(tmp_path: Path, alembic_upgrade) -> None:  # type: ignore[no-untyped-def]
    """AC-D7 — the WHERE eco=? AND package=? plan hits idx_vuln_pkg_eco."""
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    conn = sqlite3.connect(db)
    plan = conn.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM vulnerabilities WHERE ecosystem=? AND package=?",
        ("npm", "express"),
    ).fetchall()
    conn.close()
    assert any("idx_vuln_pkg_eco" in str(r) for r in plan), f"plan: {plan}"


def test_unique_constraint_covers_full_range(tmp_path: Path, alembic_upgrade) -> None:  # type: ignore[no-untyped-def]
    """AC-D3 — (cve, eco, pkg, introduced, fixed, last_affected) uniqueness.

    Sqlite materialises the ``UniqueConstraint`` as an auto-index whose
    column order matches the constraint declaration order. We assert the
    auto-index column set + order is the full ``AffectedRange`` shape.
    """
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    conn = sqlite3.connect(db)
    auto_indexes = [
        row[1]
        for row in conn.execute("PRAGMA index_list('vulnerabilities')")
        if row[3] == "u"  # 'u' = unique constraint backing index
    ]
    assert len(auto_indexes) == 1, f"expected one unique auto-index, got {auto_indexes}"
    cols = [row[2] for row in conn.execute(f"PRAGMA index_info('{auto_indexes[0]}')")]
    conn.close()
    assert cols == [
        "cve_id",
        "ecosystem",
        "package",
        "introduced",
        "fixed",
        "last_affected",
    ]


def test_insert_or_ignore_idempotent(tmp_path: Path, alembic_upgrade) -> None:  # type: ignore[no-untyped-def]
    """AC-D4 — re-inserting an identical record is a no-op."""
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    rec = _make_record()
    with VulnIndex(db) as idx:
        idx._raw_insert(rec)
        idx._raw_insert(rec)
    conn = sqlite3.connect(db)
    count = conn.execute("SELECT COUNT(*) FROM vulnerabilities").fetchone()[0]
    conn.close()
    assert count == 1


def test_unique_constraint_allows_distinct_ranges(tmp_path: Path, alembic_upgrade) -> None:  # type: ignore[no-untyped-def]
    """AC-D3 — multiple non-overlapping ranges for the same CVE+package permitted."""
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    base = _make_record()
    other = VulnerabilityRecord(
        cve_id=base.cve_id,
        ecosystem=base.ecosystem,
        package=base.package,
        affected_range=AffectedRange(introduced="5.0.0", fixed="5.1.2"),
        severity=base.severity,
        published_at=base.published_at,
        source=base.source,
    )
    with VulnIndex(db) as idx:
        idx._raw_insert(base)
        idx._raw_insert(other)
    conn = sqlite3.connect(db)
    count = conn.execute("SELECT COUNT(*) FROM vulnerabilities").fetchone()[0]
    conn.close()
    assert count == 2


def test_meta_table_shape(tmp_path: Path, alembic_upgrade) -> None:  # type: ignore[no-untyped-def]
    """AC-D5 — meta table is (key TEXT PRIMARY KEY, value TEXT NOT NULL)."""
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    conn = sqlite3.connect(db)
    cols = list(conn.execute("PRAGMA table_info('meta')"))
    conn.close()
    by_name = {row[1]: row for row in cols}
    assert set(by_name.keys()) == {"key", "value"}
    # PK flag at index 5.
    assert by_name["key"][5] == 1
    assert by_name["value"][3] == 1  # NOT NULL


def test_double_upgrade_is_idempotent(tmp_path: Path, alembic_upgrade) -> None:  # type: ignore[no-untyped-def]
    """AC-D6 — running alembic upgrade head twice doesn't error."""
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    alembic_upgrade(db)
    conn = sqlite3.connect(db)
    revs = list(conn.execute("SELECT version_num FROM alembic_version"))
    conn.close()
    assert len(revs) == 1
