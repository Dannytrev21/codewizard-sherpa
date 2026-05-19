"""Phase 7 S1-02 — `DistroPackage`, enums, exhaustiveness, JSON round-trip.

Covers ACs 2, 3, 4, 6, 7, 8, 12. Story file:
`docs/phases/07-migration-task-class/stories/
S1-02-provenance-enums-and-distro-package.md`.

ADRs honoured: Phase 7 ADR-0004 (primitive home), production ADR-0033
(sum-type discipline — `UnknownReason` is a `Literal` union, not `str`),
production ADR-0038 (vuln-provenance contract names every type here
verbatim).
"""

from __future__ import annotations

import json
from typing import assert_never, get_args

import pytest
from pydantic import ValidationError

from codegenie.primitives.vuln_provenance.types import (
    AdapterConfidence,
    DistroPackage,
    UnknownReason,
)

_ADMITTED_DISTROS: tuple[str, ...] = ("alpine", "debian", "ubuntu", "rhel")

# ---------------------------------------------------------------------------
# DistroPackage — AC-2 + AC-7
# ---------------------------------------------------------------------------


def test_distro_package_happy_path() -> None:
    pkg = DistroPackage(name="openssl", version="3.0.7", distro="alpine")
    assert pkg.name == "openssl"
    assert pkg.version == "3.0.7"
    assert pkg.distro == "alpine"


def test_distro_package_frozen_rejects_mutation() -> None:
    pkg = DistroPackage(name="openssl", version="3.0.7", distro="alpine")
    with pytest.raises(ValidationError):
        pkg.name = "evil"  # type: ignore[misc]


def test_distro_package_extra_forbid() -> None:
    with pytest.raises(ValidationError):
        DistroPackage(
            name="x",
            version="1",
            distro="alpine",
            extra_field="leak",  # type: ignore[call-arg]
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        # `distro` not in the Literal closed set
        {"name": "x", "version": "1", "distro": "centos"},
        # `distro` case-mismatch — Literal is value-exact
        {"name": "x", "version": "1", "distro": "Alpine"},
        {"name": "x", "version": "1", "distro": "ALPINE"},
        # `distro` whitespace contamination
        {"name": "x", "version": "1", "distro": " alpine"},
        {"name": "x", "version": "1", "distro": "alpine "},
        # `distro` empty string
        {"name": "x", "version": "1", "distro": ""},
        # `name` empty / whitespace-only — Field(min_length=1) alone admits " "
        {"name": "", "version": "1", "distro": "alpine"},
        {"name": " ", "version": "1", "distro": "alpine"},
        {"name": "\t", "version": "1", "distro": "alpine"},
        # `version` empty / whitespace-only
        {"name": "x", "version": "", "distro": "alpine"},
        {"name": "x", "version": " ", "distro": "alpine"},
        {"name": "x", "version": "\t", "distro": "alpine"},
    ],
    ids=[
        "distro_centos_not_in_literal",
        "distro_case_mismatch_title",
        "distro_case_mismatch_upper",
        "distro_leading_whitespace",
        "distro_trailing_whitespace",
        "distro_empty",
        "name_empty",
        "name_space_only",
        "name_tab_only",
        "version_empty",
        "version_space_only",
        "version_tab_only",
    ],
)
def test_distro_package_rejects_invalid_input(kwargs: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        DistroPackage(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("distro", _ADMITTED_DISTROS)
def test_distro_package_admits_every_supported_distro(distro: str) -> None:
    pkg = DistroPackage(name="zlib", version="1.2", distro=distro)  # type: ignore[arg-type]
    assert pkg.distro == distro


# ---------------------------------------------------------------------------
# DistroPackage JSON round-trip — AC-12
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("distro", _ADMITTED_DISTROS)
def test_distro_package_json_round_trip(distro: str) -> None:
    """`DistroPackage` will nest inside `BaseImage` → `Both` → `Provenance`
    and serialise into the event log. Pin the JSON shape now so silent
    serialization drift can't slip in before S1-03."""
    pkg = DistroPackage(name="openssl", version="3.0.7", distro=distro)  # type: ignore[arg-type]
    raw = pkg.model_dump_json()
    back = DistroPackage.model_validate_json(raw)
    assert back == pkg


def test_distro_package_json_keys_are_exactly_three() -> None:
    """No extras, no `_kind` markers, no Pydantic internals leak into the
    JSON payload — guards `BaseImage` from accidental schema drift."""
    pkg = DistroPackage(name="openssl", version="3.0.7", distro="alpine")
    payload = json.loads(pkg.model_dump_json())
    assert set(payload.keys()) == {"name", "version", "distro"}
    assert payload == {"name": "openssl", "version": "3.0.7", "distro": "alpine"}


# ---------------------------------------------------------------------------
# AdapterConfidence — AC-3 + AC-8
# ---------------------------------------------------------------------------


def test_adapter_confidence_values_match_arch() -> None:
    assert AdapterConfidence.HIGH.value == "high"
    assert AdapterConfidence.DEGRADED.value == "degraded"
    assert AdapterConfidence.UNAVAILABLE.value == "unavailable"


def test_adapter_confidence_round_trips_from_string() -> None:
    assert AdapterConfidence("high") is AdapterConfidence.HIGH
    assert AdapterConfidence("degraded") is AdapterConfidence.DEGRADED
    assert AdapterConfidence("unavailable") is AdapterConfidence.UNAVAILABLE


def test_adapter_confidence_members_are_distinct() -> None:
    members = list(AdapterConfidence)
    assert len(members) == 3
    for i, a in enumerate(members):
        for b in members[i + 1 :]:
            assert a is not b
            assert a.value != b.value


def test_adapter_confidence_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        AdapterConfidence("medium")


def test_adapter_confidence_is_string_enum() -> None:
    # `StrEnum` members satisfy `isinstance(m, str)` and compare equal to
    # the literal string — the contract that lets adapters dump the value
    # into Provenance JSON without a `.value` lookup.
    assert isinstance(AdapterConfidence.HIGH, str)
    assert AdapterConfidence.HIGH == "high"


# ---------------------------------------------------------------------------
# UnknownReason — AC-4
# ---------------------------------------------------------------------------


_EXPECTED_REASONS: frozenset[str] = frozenset(
    {
        "sbom_layer_attribution_absent",
        "no_adapter_resolved",
        "adapter_error",
        "base_image_already_distroless",
        "build_failed",
        "dockerfile_parse_failed",
    }
)


def test_unknown_reason_literal_args_match_arch() -> None:
    assert set(get_args(UnknownReason)) == _EXPECTED_REASONS


def test_unknown_reason_args_count_is_six() -> None:
    # Mutation guard: dropping a value silently still passes the set check
    # above if a sibling test mutates the expected set. Pin the count too.
    assert len(get_args(UnknownReason)) == 6


# ---------------------------------------------------------------------------
# Exhaustiveness anchor — AC-6
# ---------------------------------------------------------------------------


def _describe(r: UnknownReason) -> str:
    """Match-statement over every `UnknownReason` value with `assert_never`
    as the fallthrough. Adding a new reason without extending this function
    fails `mypy --strict` because `assert_never` would receive a non-`Never`
    argument."""

    match r:
        case "sbom_layer_attribution_absent":
            return "sbom"
        case "no_adapter_resolved":
            return "no_adapter"
        case "adapter_error":
            return "adapter_error"
        case "base_image_already_distroless":
            return "distroless"
        case "build_failed":
            return "build"
        case "dockerfile_parse_failed":
            return "dockerfile"
        case _:  # pragma: no cover — defensive; static-check covers exhaustively
            assert_never(r)


@pytest.mark.parametrize("reason", sorted(_EXPECTED_REASONS))
def test_describe_every_reason(reason: str) -> None:
    described = _describe(reason)  # type: ignore[arg-type]
    assert described, f"_describe({reason!r}) returned empty"


# ---------------------------------------------------------------------------
# Module surface — AC-1
# ---------------------------------------------------------------------------


def test_module_re_exports_supporting_types() -> None:
    """The three supporting types must be importable from the primitive's
    public `__init__.py` so S1-03 / downstream adapters consume the shape
    without reaching into `types.py` directly."""
    from codegenie.primitives.vuln_provenance import (
        AdapterConfidence as PublicConfidence,
    )
    from codegenie.primitives.vuln_provenance import (
        DistroPackage as PublicDistroPackage,
    )
    from codegenie.primitives.vuln_provenance import UnknownReason as PublicReason

    assert PublicConfidence is AdapterConfidence
    assert PublicDistroPackage is DistroPackage
    assert PublicReason is UnknownReason
