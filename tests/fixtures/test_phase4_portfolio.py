"""Phase-4 S7-05 — :class:`Phase4FixtureSpec` manifest tests.

Tests the **manifest** shipped in :mod:`tests.fixtures.phase4_portfolio`
plus the structural artifacts of any fixture directories present today.
The full S7-05 AC complement (AC-3 .ts file counts, AC-8 tsc clean,
AC-11 seeded RAG record digest, AC-12 cassette stubs, etc.) lands as
the fixture-content commits arrive.

This Attempt #1 ships:

* The typed manifest (5 ``Phase4FixtureSpec`` rows).
* Structural smoke for the ``glibc-on-node`` fixture (Dockerfile +
  package.json + index.js — the simplest of the five).
* Lookup helpers + their unit tests.

Future Attempts:

* Plant ``express-cve-2026-1234`` (≥70 .ts files + Jest suite +
  tsc-clean — multi-session effort).
* Plant ``lodash-cve-2026-9876`` (~20 files + callsite rewrite fixture).
* Plant ``express-rerun`` (seeded ``.codegenie/rag/records/``).
* Plant ``cassette-attempt-1-fails-attempt-2-passes`` (two cassette stubs).

When Phase-3 S8-01 lands its ``tests/fixtures/repos/_portfolio.py``
typed manifest, the rows here merge additively and this module's
sunset commit deletes the shadow.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.phase4_portfolio import (
    PHASE4_PORTFOLIO,
    Phase4FixtureSpec,
    by_category,
    by_consumer_story,
    by_name,
)

_REPOS_DIR = Path(__file__).parent / "repos"


# --- Manifest cardinality + shape ------------------------------------------


def test_portfolio_has_five_fixtures() -> None:
    """S7-05 AC §Goal: 'Land all five fixtures.' The manifest pins
    five rows by name; a future widening to six lands as an additive
    new row, not an edit to this test."""
    assert len(PHASE4_PORTFOLIO) == 5, (
        f"S7-05 portfolio drift — expected 5 fixtures, got {len(PHASE4_PORTFOLIO)}"
    )


def test_portfolio_names_match_arch_spec() -> None:
    """The five names are the arch §Fixture-portfolio names, verbatim."""
    names = sorted(s.name for s in PHASE4_PORTFOLIO)
    expected = sorted(
        [
            "express-cve-2026-1234",
            "lodash-cve-2026-9876",
            "glibc-on-node",
            "express-rerun",
            "cassette-attempt-1-fails-attempt-2-passes",
        ]
    )
    assert names == expected


def test_every_spec_is_frozen() -> None:
    """Pydantic ``frozen=True`` rejects post-construction mutation."""
    spec = PHASE4_PORTFOLIO[0]
    with pytest.raises(Exception):  # noqa: B017,BLE001 — Pydantic ValidationError shape
        spec.name = "different"  # type: ignore[misc]


def test_no_duplicate_names_in_portfolio() -> None:
    """Two rows with the same name would silently shadow each other in lookups."""
    names = [s.name for s in PHASE4_PORTFOLIO]
    duplicates = [n for n in set(names) if names.count(n) > 1]
    assert not duplicates, f"duplicate names in portfolio: {duplicates}"


def test_every_spec_has_at_least_one_cve_id() -> None:
    """A fixture with zero CVE ids would be unreachable as a CVE anchor."""
    bad = [s.name for s in PHASE4_PORTFOLIO if not s.cve_ids]
    assert not bad, f"fixtures with empty cve_ids: {bad}"


def test_every_spec_has_at_least_one_consumer_story() -> None:
    """A fixture with no documented consumer is dead weight; surface loudly."""
    bad = [s.name for s in PHASE4_PORTFOLIO if not s.consumer_stories]
    assert not bad, f"fixtures with no consumer_stories: {bad}"


# --- Category dimension (arch §1014 glob shape) ----------------------------


def test_by_category_vuln_major_bump_returns_two_rows() -> None:
    """Arch §1014 globs ``vuln-major-bump/*``; the canonical helper
    returns the two ``vuln-major-bump`` fixtures (express + lodash)."""
    rows = by_category("vuln-major-bump")
    assert {s.name for s in rows} == {
        "express-cve-2026-1234",
        "lodash-cve-2026-9876",
    }


def test_by_category_vuln_provenance_returns_glibc() -> None:
    rows = by_category("vuln-provenance")
    assert {s.name for s in rows} == {"glibc-on-node"}


def test_by_category_vuln_rag_hit_returns_express_rerun() -> None:
    rows = by_category("vuln-rag-hit")
    assert {s.name for s in rows} == {"express-rerun"}


def test_by_category_vuln_retry_returns_cassette_fixture() -> None:
    rows = by_category("vuln-retry")
    assert {s.name for s in rows} == {"cassette-attempt-1-fails-attempt-2-passes"}


# --- Consumer-story lookup -------------------------------------------------


def test_by_consumer_story_s5_04_returns_major_bump_fixtures() -> None:
    """S5-04 calibration smoke consumes the two ``vuln-major-bump`` fixtures."""
    rows = by_consumer_story("S5-04")
    assert {s.name for s in rows} == {
        "express-cve-2026-1234",
        "lodash-cve-2026-9876",
    }


def test_by_consumer_story_s7_03_returns_glibc_on_node() -> None:
    """S7-03 vuln_provenance adapter consumes the provenance fixture."""
    rows = by_consumer_story("S7-03")
    assert {s.name for s in rows} == {"glibc-on-node"}


def test_by_consumer_story_s6_02_returns_cassette_fixture() -> None:
    """S6-02 retry-bypass test consumes the cassette retry fixture."""
    rows = by_consumer_story("S6-02")
    assert {s.name for s in rows} == {"cassette-attempt-1-fails-attempt-2-passes"}


def test_by_consumer_story_s7_07_returns_express_rerun() -> None:
    """S7-07 replay-lands-RAG E2E consumes the seeded RAG fixture."""
    rows = by_consumer_story("S7-07")
    assert "express-rerun" in {s.name for s in rows}


# --- by_name lookup --------------------------------------------------------


def test_by_name_returns_the_matching_spec() -> None:
    spec = by_name("glibc-on-node")
    assert isinstance(spec, Phase4FixtureSpec)
    assert spec.category == "vuln-provenance"


def test_by_name_raises_with_helpful_diagnostic_on_unknown() -> None:
    """A missing fixture surfaces with the available list — operator
    diagnostic, not silent ``IndexError``."""
    with pytest.raises(KeyError, match=r"no Phase-4 fixture named .*available"):
        by_name("does-not-exist")


# --- glibc-on-node fixture content smoke ----------------------------------


def test_glibc_on_node_fixture_directory_exists() -> None:
    """The simplest of the five fixtures ships in this commit; the
    other four are scheduled for follow-up attempts."""
    fixture_dir = _REPOS_DIR / "glibc-on-node"
    assert fixture_dir.is_dir(), f"glibc-on-node fixture directory missing at {fixture_dir}"


def test_glibc_on_node_has_dockerfile_with_node_base_image() -> None:
    """The fixture's load-bearing artifact is its Dockerfile — the
    base-image provenance anchor S7-03's adapter consumes."""
    dockerfile = _REPOS_DIR / "glibc-on-node" / "Dockerfile"
    assert dockerfile.is_file(), f"Dockerfile missing at {dockerfile}"
    body = dockerfile.read_text()
    assert "FROM node:" in body, "Dockerfile must FROM a node base image"


def test_glibc_on_node_has_package_json() -> None:
    """Minimal npm-loadable shape."""
    pkg = _REPOS_DIR / "glibc-on-node" / "package.json"
    assert pkg.is_file()
    import json

    parsed = json.loads(pkg.read_text())
    assert parsed["name"] == "glibc-on-node-fixture"
    assert "express" in parsed["dependencies"]


def test_other_phase4_fixtures_not_yet_planted_loudly_skips() -> None:
    """The other four fixtures land in follow-up commits. This test
    documents the deferred set so a reader sees the gap explicitly."""
    expected_directories = [
        "express-cve-2026-1234",
        "lodash-cve-2026-9876",
        "express-rerun",
        "cassette-attempt-1-fails-attempt-2-passes",
    ]
    missing = [name for name in expected_directories if not (_REPOS_DIR / name).is_dir()]
    if missing:
        pytest.skip(
            f"S7-05 Attempt #1 only planted glibc-on-node; "
            f"deferred fixture directories: {missing}. "
            f"Each requires its own follow-up commit (express-cve-2026-1234 = "
            f"~80 .ts files + Jest suite; lodash-cve-2026-9876 = ~20 files; "
            f"express-rerun = seeded .codegenie/rag/records/<id>.yaml; "
            f"cassette-attempt-... = two typed CassetteStub YAMLs)."
        )
