"""S3-02 — VulnIndex lookup / affecting_range / digest / lifecycle tests.

Covers AC-A1..A3, AC-E3..E6, AC-F1..F5, AC-G1..G2, AC-H1..H4, AC-J1.
"""

from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import TypeAdapter

from codegenie.result import Ok
from codegenie.types.identifiers import CveId, PackageName
from codegenie.types.parsers import parse_blob_digest
from codegenie.vuln_index import (
    AffectedRange,
    VulnerabilityRecord,
    VulnIndex,
    VulnIndexException,
)

# ---- Shared fixtures -------------------------------------------------------


@pytest.fixture
def fresh_index(tmp_path: Path, alembic_upgrade) -> Iterator[VulnIndex]:  # type: ignore[no-untyped-def]
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    idx = VulnIndex(db)
    yield idx
    idx.close()


@pytest.fixture
def multi_seeded_index(tmp_path: Path, alembic_upgrade) -> Iterator[VulnIndex]:  # type: ignore[no-untyped-def]
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    idx = VulnIndex(db)
    base_ts = datetime(2024, 3, 1, tzinfo=UTC)
    seeds = [
        ("CVE-2024-21501", "npm", "express", "4.19.2"),
        ("CVE-2023-26136", "npm", "lodash", "4.17.21"),
        ("CVE-2024-11111", "pypi", "express", "0.0.2"),
    ]
    for cve, eco, pkg, fixed in seeds:
        idx._raw_insert(
            VulnerabilityRecord(
                cve_id=CveId(cve),
                ecosystem=eco,  # type: ignore[arg-type]
                package=PackageName(pkg),
                affected_range=AffectedRange(introduced="0.0.0", fixed=fixed),
                severity="high",
                published_at=base_ts,
                source="nvd",
            )
        )
    yield idx
    idx.close()


# ---- AC-A2/A3 — package surface + test seam typing -------------------------


def test_all_excludes_test_seams() -> None:
    """AC-A2 — _raw_insert / _raw_set_meta NOT in __all__.

    S3-03 extends the public surface additively with the feed-registry kernel
    (``Feed`` protocol, ``FeedRegistry``, decorator) + ingest pipeline
    (``IngestStats``, ``ingest_records``) + the parse-error model
    (``VulnParseError`` / ``VulnParseException``). The invariant this test
    guards is still ``_raw_*`` test seams stay OUT of ``__all__`` — checked
    as a subset assertion rather than an equality so the surface can grow
    additively per the "Extension by addition" commitment in CLAUDE.md.
    """
    import codegenie.vuln_index as pkg

    public = set(pkg.__all__)
    assert public >= {
        "AffectedRange",
        "VulnIndex",
        "VulnIndexConfigError",
        "VulnIndexException",
        "VulnIndexLookupError",
        "VulnerabilityRecord",
    }
    # S3-02 invariant — internal seams remain private.
    assert "_raw_insert" not in public
    assert "_raw_set_meta" not in public


def test_raw_insert_rejects_non_record(fresh_index: VulnIndex) -> None:
    """AC-A3 — _raw_insert typed at the boundary."""
    with pytest.raises(TypeError):
        fresh_index._raw_insert({"cve_id": "CVE-2024-21501"})  # type: ignore[arg-type]


def test_raw_set_meta_rejects_non_str(fresh_index: VulnIndex) -> None:
    """AC-A3 — _raw_set_meta typed at the boundary."""
    with pytest.raises(TypeError):
        fresh_index._raw_set_meta("schema_version", 1)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        fresh_index._raw_set_meta(b"x", "y")  # type: ignore[arg-type]


# ---- AC-B4 — published_at tz round-trips through sqlite TEXT ---------------


def test_published_at_tz_round_trips_through_storage(fresh_index: VulnIndex) -> None:
    when = datetime(2024, 3, 1, 12, 0, 0, tzinfo=UTC)
    fresh_index._raw_insert(
        VulnerabilityRecord(
            cve_id=CveId("CVE-2024-21501"),
            ecosystem="npm",
            package=PackageName("express"),
            affected_range=AffectedRange(introduced="0.0.0", fixed="4.19.2"),
            severity="high",
            published_at=when,
            source="nvd",
        )
    )
    out = fresh_index.lookup(PackageName("express"), "npm")[0]
    assert out.published_at == when
    assert out.published_at.tzinfo is not None


# ---- AC-F (lookup behavior) ------------------------------------------------


def test_lookup_selectivity_excludes_other_packages_and_ecosystems(
    multi_seeded_index: VulnIndex,
) -> None:
    """AC-F2 — filter applies to BOTH (name, ecosystem)."""
    results = multi_seeded_index.lookup(PackageName("express"), "npm")
    assert {str(r.cve_id) for r in results} == {"CVE-2024-21501"}


def test_lookup_missing_package_returns_empty_list(multi_seeded_index: VulnIndex) -> None:
    """AC-F3 — missing → [] (not raises)."""
    assert multi_seeded_index.lookup(PackageName("nonexistent"), "npm") == []


def test_lookup_filter_by_ecosystem_only_fails_selectivity(
    multi_seeded_index: VulnIndex,
) -> None:
    """AC-F2 mutation guard — verify the package filter actually filters."""
    pypi_only = multi_seeded_index.lookup(PackageName("express"), "pypi")
    assert {str(r.cve_id) for r in pypi_only} == {"CVE-2024-11111"}
    npm_only = multi_seeded_index.lookup(PackageName("express"), "npm")
    assert {str(r.cve_id) for r in npm_only} == {"CVE-2024-21501"}
    assert pypi_only != npm_only


def test_lookup_sorts_severity_desc_published_desc_cveid_asc(fresh_index: VulnIndex) -> None:
    """AC-F4 — full deterministic sort with severity + time + cve_id tiebreak."""
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 2, 1, tzinfo=UTC)
    seeds = [
        ("CVE-2026-0001", "high", t0),
        ("CVE-2026-0002", "critical", t0),
        ("CVE-2026-0003", "high", t1),
        ("CVE-2026-0004", "medium", t1),
        ("CVE-2026-0005", "critical", t0),  # collision with 0002 → cve_id ASC
    ]
    for cve, sev, ts in seeds:
        fresh_index._raw_insert(
            VulnerabilityRecord(
                cve_id=CveId(cve),
                ecosystem="npm",
                package=PackageName("x"),
                affected_range=AffectedRange(introduced="0.0.0"),
                severity=sev,  # type: ignore[arg-type]
                published_at=ts,
                source="nvd",
            )
        )
    cves = [str(r.cve_id) for r in fresh_index.lookup(PackageName("x"), "npm")]
    assert cves == [
        "CVE-2026-0002",
        "CVE-2026-0005",
        "CVE-2026-0003",
        "CVE-2026-0001",
        "CVE-2026-0004",
    ]


def test_lookup_round_trip_property(tmp_path: Path, alembic_upgrade) -> None:  # type: ignore[no-untyped-def]
    """AC-F5 — Hypothesis-style round-trip over a manual portfolio."""
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    idx = VulnIndex(db)
    portfolio: list[tuple[str, str, str]] = [
        ("CVE-2024-A001", "npm", "express"),
        ("CVE-2024-A002", "npm", "express"),
        ("CVE-2024-A003", "npm", "lodash"),
        ("CVE-2024-A004", "pypi", "requests"),
    ]
    base = datetime(2026, 1, 1, tzinfo=UTC)
    inserted: dict[tuple[str, str], set[str]] = {}
    for cve, eco, pkg in portfolio:
        idx._raw_insert(
            VulnerabilityRecord(
                cve_id=CveId(cve),
                ecosystem=eco,  # type: ignore[arg-type]
                package=PackageName(pkg),
                affected_range=AffectedRange(introduced="0.0.0"),
                severity="high",
                published_at=base,
                source="nvd",
            )
        )
        inserted.setdefault((eco, pkg), set()).add(cve)
    for (eco, pkg), cves in inserted.items():
        got = idx.lookup(PackageName(pkg), eco)  # type: ignore[arg-type]
        assert {str(r.cve_id) for r in got} == cves
    idx.close()


# ---- AC-G (affecting_range) ------------------------------------------------


def test_affecting_range_returns_matching_row(multi_seeded_index: VulnIndex) -> None:
    """AC-G1 — WHERE cve_id = ? filters correctly."""
    rng = multi_seeded_index.affecting_range(CveId("CVE-2023-26136"))
    assert rng.fixed == "4.17.21"


def test_affecting_range_missing_cve_raises_typed(multi_seeded_index: VulnIndex) -> None:
    """AC-G2 — missing CVE raises VulnIndexException(reason='cve_not_found')."""
    with pytest.raises(VulnIndexException) as exc:
        multi_seeded_index.affecting_range(CveId("CVE-9999-9999"))
    assert exc.value.model.reason == "cve_not_found"
    assert exc.value.model.details["cve_id"] == "CVE-9999-9999"


# ---- AC-H (digest) ---------------------------------------------------------


def test_digest_round_trips_through_parse_blob_digest(fresh_index: VulnIndex) -> None:
    """AC-H1 — digest matches the BlobDigest grammar (64-hex, no prefix)."""
    d = fresh_index.digest()
    assert len(d) == 64
    assert ":" not in d
    r = parse_blob_digest(d)
    assert isinstance(r, Ok)


# Empty-DB digest is a deterministic literal — computed once, frozen here as
# the drift sentinel. If the joiner / field order / hash algorithm change,
# this assertion fails loudly (AC-H2). Computed via S3-02 first green run.
EMPTY_DB_DIGEST_LITERAL = "64bb3c9a335ea41562ccc3116bb12f11d0a9f9a6c932a0c39f30d260262f2e8f"


def test_empty_db_digest_is_deterministic_across_invocations(fresh_index: VulnIndex) -> None:
    """AC-H2 — empty DB digest is stable on repeated calls."""
    a = fresh_index.digest()
    b = fresh_index.digest()
    assert a == b


def test_empty_db_digest_is_pinned_literal(fresh_index: VulnIndex) -> None:
    """AC-H2 — drift sentinel. Tightened by `test_empty_db_digest_literal_freeze` below."""
    d = fresh_index.digest()
    # Initial run: this assertion fails and the actual value gets pasted into
    # EMPTY_DB_DIGEST_LITERAL. The constant in the module is the contract.
    if EMPTY_DB_DIGEST_LITERAL:
        assert d == EMPTY_DB_DIGEST_LITERAL, (
            f"Empty-DB digest drifted from frozen literal. "
            f"Expected {EMPTY_DB_DIGEST_LITERAL!r}, got {d!r}."
        )


def test_digest_deterministic_across_processes(tmp_path: Path, alembic_upgrade) -> None:  # type: ignore[no-untyped-def]
    """AC-H3 — digest is byte-identical across two python processes."""
    import subprocess
    import sys

    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    # ``import codegenie.vuln_index`` indirectly triggers probe-catalog log
    # output via the wider ``codegenie`` package init — we print the digest
    # on a dedicated marker line and parse it back out.
    code = (
        "import sys; sys.path.insert(0, 'src')\n"
        "from pathlib import Path\n"
        "from codegenie.vuln_index import VulnIndex\n"
        f"idx = VulnIndex(Path({str(db)!r}))\n"
        "print('DIGEST:' + idx.digest())\n"
        "idx.close()\n"
    )
    a = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    b = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)

    def _extract(out: str) -> str:
        for line in out.splitlines():
            if line.startswith("DIGEST:"):
                return line[len("DIGEST:") :]
        raise AssertionError(f"no DIGEST marker in subprocess output: {out!r}")

    a_digest = _extract(a.stdout)
    b_digest = _extract(b.stdout)
    assert a_digest == b_digest
    assert len(a_digest) == 64


@pytest.mark.parametrize(
    "meta_key",
    ["feed_digest_nvd", "feed_digest_ghsa", "feed_digest_osv", "schema_version"],
)
def test_digest_changes_when_any_meta_input_changes(fresh_index: VulnIndex, meta_key: str) -> None:
    """AC-H4 — every meta input contributes to the digest."""
    before = fresh_index.digest()
    fresh_index._raw_set_meta(meta_key, "z" * 64)
    after = fresh_index.digest()
    assert before != after


# ---- AC-I (is_stale + env) -------------------------------------------------


def test_is_stale_pure_strict_boundary() -> None:
    """AC-I5 — exactly at threshold is NOT stale (strict >)."""
    from codegenie.vuln_index.index import _is_stale_pure

    assert _is_stale_pure(now=100.0, mtime=100.0 - 7 * 86400, max_age_seconds=7 * 86400) is False
    assert _is_stale_pure(now=100.0, mtime=100.0 - 7 * 86400 - 1, max_age_seconds=7 * 86400) is True


def test_is_stale_pure_clock_skew_returns_false() -> None:
    """AC-I3 — mtime in the future → False."""
    from codegenie.vuln_index.index import _is_stale_pure

    assert _is_stale_pure(now=100.0, mtime=200.0, max_age_seconds=7 * 86400) is False


def test_is_stale_non_existent_path_is_fresh(tmp_path: Path) -> None:
    """AC-I2 — non-existent path → False."""
    idx = VulnIndex(tmp_path / "nope.sqlite")
    assert idx.is_stale() is False


@pytest.mark.parametrize(
    ("bad_value", "expected_reason"),
    [
        ("not-an-int", "invalid_max_age"),
        ("", "invalid_max_age"),
        ("7.5", "invalid_max_age"),
        ("+7", "invalid_max_age"),
        ("007 garbage", "invalid_max_age"),
        ("0", "non_positive_max_age"),
        ("-1", "non_positive_max_age"),
    ],
)
def test_env_validation_rejection_corpus(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_upgrade,  # type: ignore[no-untyped-def]
    bad_value: str,
    expected_reason: str,
) -> None:
    """AC-I4 — rejection corpus with typed reasons."""
    monkeypatch.setenv("CODEGENIE_VULN_INDEX_MAX_AGE_DAYS", bad_value)
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    idx = VulnIndex(db)
    with pytest.raises(VulnIndexException) as exc:
        idx.is_stale()
    assert exc.value.model.reason == expected_reason
    idx.close()


@pytest.mark.parametrize("good_value", ["7", " 7 ", "7\n", "1"])
def test_env_validation_accepts_clean_int(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_upgrade,  # type: ignore[no-untyped-def]
    good_value: str,
) -> None:
    """AC-I4 — whitespace-stripped ints accept."""
    monkeypatch.setenv("CODEGENIE_VULN_INDEX_MAX_AGE_DAYS", good_value)
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    idx = VulnIndex(db)
    idx.is_stale()  # MUST NOT raise
    idx.close()


def test_default_threshold_is_seven_days(
    tmp_path: Path,
    alembic_upgrade,  # type: ignore[no-untyped-def]
) -> None:
    """AC-I6 — env unset → 7-day default.

    ``VulnIndex.__init__`` opens the sqlite connection + applies WAL pragmas
    which may bump the file's mtime; pin the mtime AFTER instantiation so
    the staleness check sees the value the test wants.
    """
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    idx = VulnIndex(db)
    eight_days_ago = time.time() - 8 * 86400
    os.utime(db, (eight_days_ago, eight_days_ago))
    assert idx.is_stale() is True
    idx.close()

    db2 = tmp_path / "fresh.sqlite"
    alembic_upgrade(db2)
    idx2 = VulnIndex(db2)
    six_days_ago = time.time() - 6 * 86400
    os.utime(db2, (six_days_ago, six_days_ago))
    assert idx2.is_stale() is False
    idx2.close()


@given(
    days=st.integers(min_value=1, max_value=365), age_days=st.integers(min_value=0, max_value=730)
)
@settings(max_examples=40, deadline=None)
def test_is_stale_property(days: int, age_days: int) -> None:
    """AC-I1 — property: is_stale ↔ age strictly greater than threshold."""
    from codegenie.vuln_index.index import _is_stale_pure

    now = 1_000_000.0
    mtime = now - age_days * 86400
    expected = (age_days * 86400) > (days * 86400)
    assert _is_stale_pure(now=now, mtime=mtime, max_age_seconds=days * 86400) is expected


# ---- AC-J (stale_payload) --------------------------------------------------


def test_stale_payload_shape_validates_via_type_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    alembic_upgrade,  # type: ignore[no-untyped-def]
) -> None:
    """AC-J1 — payload validates as TypeAdapter[dict[str, str|int|bool|float|list[str]]]."""
    monkeypatch.setenv("CODEGENIE_VULN_INDEX_MAX_AGE_DAYS", "7")
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    idx = VulnIndex(db)
    # Pin mtime AFTER open — VulnIndex.__init__ may touch the file via WAL.
    os.utime(db, (time.time() - 8 * 86400, time.time() - 8 * 86400))
    payload = idx.stale_payload()
    Adapter = TypeAdapter(dict[str, str | int | bool | float | list[str]])
    Adapter.validate_python(payload)
    assert set(payload.keys()) == {"path", "mtime_iso", "age_days", "threshold_days"}
    assert payload["threshold_days"] == 7
    assert payload["age_days"] >= 7.5
    idx.close()


def test_stale_vuln_index_event_type_literal() -> None:
    """AC-J1 — _STALE_VULN_INDEX_EVENT_TYPE constant exposed for S6-04."""
    from codegenie.vuln_index.errors import _STALE_VULN_INDEX_EVENT_TYPE

    assert _STALE_VULN_INDEX_EVENT_TYPE == "stale_vuln_index"


# ---- AC-E (lifecycle) ------------------------------------------------------


def test_close_then_lookup_raises_closed(multi_seeded_index: VulnIndex) -> None:
    """AC-E4 — post-close ops raise typed 'closed' error."""
    idx = multi_seeded_index
    idx.close()
    with pytest.raises(VulnIndexException) as exc:
        idx.lookup(PackageName("express"), "npm")
    assert exc.value.model.reason == "closed"


def test_close_then_affecting_range_raises_closed(multi_seeded_index: VulnIndex) -> None:
    idx = multi_seeded_index
    idx.close()
    with pytest.raises(VulnIndexException) as exc:
        idx.affecting_range(CveId("CVE-2024-21501"))
    assert exc.value.model.reason == "closed"


def test_close_then_digest_raises_closed(multi_seeded_index: VulnIndex) -> None:
    idx = multi_seeded_index
    idx.close()
    with pytest.raises(VulnIndexException) as exc:
        idx.digest()
    assert exc.value.model.reason == "closed"


def test_double_close_is_idempotent(multi_seeded_index: VulnIndex) -> None:
    """AC-E3 — close() is idempotent."""
    multi_seeded_index.close()
    multi_seeded_index.close()  # must NOT raise


def test_context_manager_closes_on_exit(tmp_path: Path, alembic_upgrade) -> None:  # type: ignore[no-untyped-def]
    """AC-E3 — __enter__/__exit__ release the connection."""
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    with VulnIndex(db) as idx:
        _ = idx.digest()
    with pytest.raises(VulnIndexException) as exc:
        idx.digest()
    assert exc.value.model.reason == "closed"


def test_wal_journal_mode_on_open(tmp_path: Path, alembic_upgrade) -> None:  # type: ignore[no-untyped-def]
    """AC-E5 — PRAGMA journal_mode=WAL applied."""
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    with VulnIndex(db) as _:
        pass
    conn = sqlite3.connect(db)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0].lower()
    conn.close()
    assert mode == "wal"


def test_no_fd_leak_over_1024_open_close(tmp_path: Path, alembic_upgrade) -> None:  # type: ignore[no-untyped-def]
    """AC-E6 — 1024 sequential opens do not exhaust fds."""
    db = tmp_path / "vuln-index.sqlite"
    alembic_upgrade(db)
    for _ in range(1024):
        with VulnIndex(db) as idx:
            _ = idx.digest()
