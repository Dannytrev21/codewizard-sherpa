"""S3-03 — ``SemverVersion`` newtype + ``parse_semver`` smart constructor.

The CVE-feed ingest boundary (S3-03) routes every ``AffectedRange.introduced
/ fixed / last_affected`` value through :func:`parse_semver`. Grammar is
canonical semver-2.0.0 (https://semver.org/#spec-item-2). Production
ADR-0033 §1 names version strings as a "review-blocker" primitive-obsession
site; this newtype + smart constructor closes that gap.
"""

from __future__ import annotations

import pytest

from codegenie.result import Err, Ok
from codegenie.types.identifiers import SemverVersion, _NEWTYPE_REGISTRY
from codegenie.types.parsers import parse_semver


# AC-S6 — registry citation.
def test_newtype_registry_cites_adr_0033_for_semver_version() -> None:
    entry = _NEWTYPE_REGISTRY["SemverVersion"]
    assert "ADR-0033" in entry


# AC-S6 — __all__ membership.
def test_semver_version_in_identifiers_all() -> None:
    from codegenie.types import identifiers as ids

    assert "SemverVersion" in ids.__all__


def test_parse_semver_in_parsers_all() -> None:
    from codegenie.types import parsers as p

    assert "parse_semver" in p.__all__


# AC-S8 — happy-path corpus.
@pytest.mark.parametrize(
    "raw",
    [
        "1.0.0",
        "0.1.2",
        "1.2.3-alpha.1",
        "1.2.3+build.42",
        "1.2.3-rc.1+build.5",
        "0.0.0",
        "10.20.30",
        "1.0.0-0",
        "1.0.0-alpha",
        "1.0.0-alpha+001",
        "1.0.0-beta.11",
    ],
)
def test_parse_semver_accepts_canonical(raw: str) -> None:
    result = parse_semver(raw)
    assert isinstance(result, Ok)
    assert result.value == SemverVersion(raw)


# AC-S8 — rejection corpus.
@pytest.mark.parametrize(
    "raw",
    [
        "",
        "1",
        "1.2",
        "01.2.3",
        "1.02.3",
        "1.2.03",
        "1.2.3-",
        "1.2.3+",
        "v1.2.3",
        "1.2.3 ",
        " 1.2.3",
        "1.2.3.4",
        "1.2.3-01",  # numeric pre-release with leading zero
        "1.2.3-α",  # non-ASCII
    ],
)
def test_parse_semver_rejects_malformed(raw: str) -> None:
    result = parse_semver(raw)
    assert isinstance(result, Err)
    assert "SemverVersion" in result.error.message


def test_parse_semver_round_trip_identity() -> None:
    """Round-trip — the Ok value MUST equal the input byte-for-byte."""
    for raw in ("1.2.3", "1.2.3-rc.1+build.5"):
        result = parse_semver(raw)
        assert isinstance(result, Ok)
        assert result.value == raw
