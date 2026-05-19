"""Phase 3 S3-02 — ``PackageName`` + ``Ecosystem`` additive extension to the
S1-01 newtype catalog.

S1-01's ``PackageId`` grammar (``<name>@<pinned-semver>``) does not fit
vulnerability-lookup semantics (per-name across versions); S3-02 lands the
two missing kernel-tier names additively here. ``PackageName`` is a
``NewType[str]`` (npm scoped + unscoped, no version) and ``Ecosystem`` is a
closed ``Literal[...]`` (shape parity with the ``severity`` and ``source``
literals on ``VulnerabilityRecord``).

ADRs honored: production ADR-0033 (newtype every domain identifier),
phase-3 ADR-0010 (smart-constructor boundary + closed-set Literal).
"""

from __future__ import annotations

import pytest

from codegenie.result import Err, Ok
from codegenie.types.identifiers import PackageName
from codegenie.types.parsers import parse_ecosystem, parse_package_name

# ---------------------------------------------------------------------------
# AC-B1 — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "good",
    [
        "express",
        "lodash",
        "@scope/pkg",
        "@a/b",
        "a",
        "left-pad",
        "left_pad",
        "foo.bar",
    ],
)
def test_parse_package_name_happy(good: str) -> None:
    r = parse_package_name(good)
    assert isinstance(r, Ok)
    assert r.value == PackageName(good)


@pytest.mark.parametrize("good", ["npm", "pypi", "maven", "rubygems", "gomod"])
def test_parse_ecosystem_happy(good: str) -> None:
    r = parse_ecosystem(good)
    assert isinstance(r, Ok)
    assert r.value == good


# ---------------------------------------------------------------------------
# AC-B1 — rejection corpus
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "EXPRESS",  # uppercase
        "express@4.19.2",  # @version disallowed
        "express ",  # trailing space
        " express",  # leading space
        "@scope",  # scope only, no name
        "@/pkg",  # empty scope
        "scope/pkg",  # missing leading @
        "../etc/passwd",  # path traversal
        "@scope/PKG",  # uppercase name in scope
        "express/sub",  # slash in unscoped
    ],
)
def test_parse_package_name_rejects(bad: str) -> None:
    r = parse_package_name(bad)
    assert isinstance(r, Err)
    assert r.error.value == bad


@pytest.mark.parametrize(
    "bad",
    [
        "NPM",  # uppercase
        "rust",  # not in closed set
        "",
        " npm ",  # whitespace
        "npm ",
        "pip",  # synonym not allowed
    ],
)
def test_parse_ecosystem_rejects(bad: str) -> None:
    r = parse_ecosystem(bad)
    assert isinstance(r, Err)
    assert r.error.value == bad


# ---------------------------------------------------------------------------
# AC-B1 — exports + registry
# ---------------------------------------------------------------------------


def test_package_name_and_ecosystem_in_all() -> None:
    from codegenie.types import identifiers as ids

    assert "PackageName" in ids.__all__
    assert "Ecosystem" in ids.__all__


def test_package_name_registry_entry_cites_adr_0033() -> None:
    """AC-B1 — PackageName carries an ADR-0033 citation in its registry doc."""
    from codegenie.types.identifiers import _NEWTYPE_REGISTRY

    assert "PackageName" in _NEWTYPE_REGISTRY
    assert "ADR-0033" in _NEWTYPE_REGISTRY["PackageName"]


def test_ecosystem_registry_entry_present() -> None:
    from codegenie.types.identifiers import _NEWTYPE_REGISTRY

    assert "Ecosystem" in _NEWTYPE_REGISTRY
    assert "ADR-0010" in _NEWTYPE_REGISTRY["Ecosystem"]
