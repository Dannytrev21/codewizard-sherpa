"""Tests for ``RedactedSlice`` — S3-02.

Covers all 26 ACs after phase-story-validator hardening: model surface, field
validators, frozen / extra-forbid invariants, JSON round-trip, JSON byte-stability,
field-declaration order, ``model_construct`` ban via S1-11 forbidden-patterns,
and the cross-story integration with S3-01 (``redact_secrets``).
"""

from __future__ import annotations

import copy
import inspect
import json
import re
import string
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

import codegenie.output.redacted_slice as redacted_slice_module
from codegenie.output.redacted_slice import RedactedSlice
from codegenie.types.identifiers import ProbeId

_FP_REGEX = re.compile(r"^[0-9a-f]{8}$")


# ----------------------------------------------------------------------------
# AC-1 / AC-2 — module surface + docstring
# ----------------------------------------------------------------------------


def test_ac1_module_exists_with_docstring() -> None:
    assert redacted_slice_module.__doc__ is not None
    assert "RedactedSlice" in redacted_slice_module.__doc__


def test_ac2_module_docstring_references_required_anchors() -> None:
    doc = inspect.getdoc(redacted_slice_module) or ""
    # Required substrings from S3-02 AC-2 (case-insensitive for the ladder
    # framing).
    assert "Gap 4" in doc
    assert "02-ADR-0010" in doc
    assert "02-ADR-0005" in doc
    lower = doc.lower()
    assert "three rungs" in lower or "three-rung" in lower


def test_ac3_redacted_slice_has_exactly_three_fields() -> None:
    assert set(RedactedSlice.model_fields.keys()) == {
        "slice",
        "findings_count",
        "fingerprints",
    }


# ----------------------------------------------------------------------------
# AC-4 / AC-5 / AC-6 — frozen + extra-forbid
# ----------------------------------------------------------------------------


def test_ac4_frozen_and_extra_forbid_config() -> None:
    cfg = RedactedSlice.model_config
    assert cfg.get("frozen") is True
    assert cfg.get("extra") == "forbid"


def test_ac5_mutation_raises_validation_error() -> None:
    instance = RedactedSlice(slice={}, findings_count=0, fingerprints=[])
    with pytest.raises(ValidationError):
        instance.findings_count = 99  # type: ignore[misc]


def test_ac6_unknown_field_raises() -> None:
    with pytest.raises(ValidationError) as ei:
        RedactedSlice(
            slice={},
            findings_count=0,
            fingerprints=[],
            extra_field="x",  # type: ignore[call-arg]
        )
    assert "extra_forbidden" in str(ei.value)


# ----------------------------------------------------------------------------
# AC-7 — fingerprints field validator scalar cases
# ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fp",
    [
        "1234567",  # len 7
        "123456789",  # len 9
        "ABCDEF12",  # uppercase
        "",  # empty
        "abcdef12 ",  # trailing whitespace
        " abcdef12",  # leading whitespace
        "aBcDeF12",  # mixed case
        "abcdef1g",  # non-hex char 'g'
        "abcdef1ñ",  # non-ASCII (ñ)
    ],
)
def test_ac7_invalid_fingerprints_rejected(fp: str) -> None:
    with pytest.raises(ValidationError):
        RedactedSlice(slice={}, findings_count=1, fingerprints=[fp])


@pytest.mark.parametrize("fp", ["12345678", "abcdef12", "00000000", "ffffffff"])
def test_ac7_valid_fingerprints_accepted(fp: str) -> None:
    inst = RedactedSlice(slice={}, findings_count=1, fingerprints=[fp])
    assert inst.fingerprints == [fp]


def test_ac7_non_string_element_rejected() -> None:
    with pytest.raises(ValidationError):
        RedactedSlice(
            slice={},
            findings_count=1,
            fingerprints=[12345678],  # type: ignore[list-item]
        )


# ----------------------------------------------------------------------------
# AC-7b — property-based mutation resistance
# ----------------------------------------------------------------------------


@given(st.text(alphabet="0123456789abcdef", min_size=8, max_size=8))
def test_ac7b_property_any_8hex_accepted(fp: str) -> None:
    # Singleton list
    inst = RedactedSlice(slice={}, findings_count=1, fingerprints=[fp])
    assert inst.fingerprints == [fp]


@given(
    st.lists(
        st.text(alphabet="0123456789abcdef", min_size=8, max_size=8),
        min_size=1,
        max_size=10,
    )
)
def test_ac7b_property_list_of_8hex_accepted(fps: list[str]) -> None:
    inst = RedactedSlice(slice={}, findings_count=max(len(fps), len(set(fps))), fingerprints=fps)
    assert inst.fingerprints == fps


@given(
    st.text(alphabet=string.printable, min_size=0, max_size=20).filter(
        lambda s: _FP_REGEX.fullmatch(s) is None
    )
)
def test_ac7b_property_non_fingerprints_rejected(s: str) -> None:
    with pytest.raises(ValidationError):
        RedactedSlice(slice={}, findings_count=1, fingerprints=[s])


# ----------------------------------------------------------------------------
# AC-8 / AC-8b — findings_count >= len(fingerprints) invariant
# ----------------------------------------------------------------------------


def test_ac8_count_less_than_fingerprints_rejected() -> None:
    with pytest.raises(ValidationError):
        RedactedSlice(
            slice={},
            findings_count=2,
            fingerprints=["abcdef12", "12345678", "fedcba98"],
        )


_ACCEPT_CASES = [
    (0, []),
    (1, ["abcdef12"]),
    (3, ["abcdef12"]),
    (3, ["abcdef12", "12345678", "fedcba98"]),
]
_REJECT_CASES = [
    (0, ["abcdef12"]),
    (1, ["abcdef12", "12345678"]),
]


@pytest.mark.parametrize(("count", "fps"), _ACCEPT_CASES)
def test_ac8b_boundary_accept(count: int, fps: list[str]) -> None:
    inst = RedactedSlice(slice={}, findings_count=count, fingerprints=fps)
    assert inst.findings_count == count
    assert inst.fingerprints == fps


@pytest.mark.parametrize(("count", "fps"), _REJECT_CASES)
def test_ac8b_boundary_reject(count: int, fps: list[str]) -> None:
    with pytest.raises(ValidationError):
        RedactedSlice(slice={}, findings_count=count, fingerprints=fps)


def test_ac8b_negative_count_with_empty_fps_rejected() -> None:
    with pytest.raises(ValidationError):
        RedactedSlice(slice={}, findings_count=-1, fingerprints=[])


# ----------------------------------------------------------------------------
# AC-9 — findings_count >= 0
# ----------------------------------------------------------------------------


def test_ac9_negative_count_rejected() -> None:
    with pytest.raises(ValidationError):
        RedactedSlice(slice={}, findings_count=-1, fingerprints=[])


# ----------------------------------------------------------------------------
# AC-10 / AC-10b / AC-10c — JSON round-trip identity + byte-stability + nesting
# ----------------------------------------------------------------------------


def _nested_fixture_slice() -> dict[str, Any]:
    return {
        "node_version": "20.11.1",
        "envelope": {
            "secrets": [
                "<REDACTED:fingerprint=abcdef12>",
                None,
                {
                    "inner": [
                        1,
                        "<REDACTED:fingerprint=12345678>",
                        {"deep": "<REDACTED:fingerprint=fedcba98>"},
                    ],
                    "count": 3,
                },
            ],
            "extras": [None, "plain-string", 42, 1.5, True, False],
        },
    }


def test_ac10_round_trip_pydantic_equality() -> None:
    original = RedactedSlice(
        slice=_nested_fixture_slice(),
        findings_count=3,
        fingerprints=["abcdef12", "12345678", "fedcba98"],
    )
    reloaded = RedactedSlice.model_validate_json(original.model_dump_json())
    assert reloaded == original
    assert reloaded.slice == original.slice


def test_ac10b_json_byte_stability() -> None:
    original = RedactedSlice(
        slice=_nested_fixture_slice(),
        findings_count=3,
        fingerprints=["abcdef12", "12345678", "fedcba98"],
    )
    a = original.model_dump_json()
    b = original.model_dump_json()
    assert a == b


def test_ac10c_nested_recursion_deep_equality() -> None:
    src = _nested_fixture_slice()
    original = RedactedSlice(
        slice=src,
        findings_count=3,
        fingerprints=["abcdef12", "12345678", "fedcba98"],
    )
    reloaded = RedactedSlice.model_validate_json(original.model_dump_json())
    assert reloaded.slice == src
    # At least three nesting levels exercised (dict -> list -> dict -> list).
    assert isinstance(reloaded.slice["envelope"], dict)
    sec = reloaded.slice["envelope"]["secrets"]  # type: ignore[index]
    assert isinstance(sec, list)
    inner = sec[2]
    assert isinstance(inner, dict)
    assert isinstance(inner["inner"], list)
    assert isinstance(inner["inner"][2], dict)


# ----------------------------------------------------------------------------
# AC-11 / AC-11b — model_dump keys + declaration order
# ----------------------------------------------------------------------------


def test_ac11_model_dump_keys() -> None:
    dumped = RedactedSlice(slice={}, findings_count=0, fingerprints=[]).model_dump()
    assert set(dumped.keys()) == {"slice", "findings_count", "fingerprints"}


def test_ac11b_field_declaration_order_preserved() -> None:
    inst = RedactedSlice(slice={}, findings_count=0, fingerprints=[])
    assert list(inst.model_dump().keys()) == [
        "slice",
        "findings_count",
        "fingerprints",
    ]
    assert list(json.loads(inst.model_dump_json()).keys()) == [
        "slice",
        "findings_count",
        "fingerprints",
    ]


# ----------------------------------------------------------------------------
# AC-12 / AC-12b / AC-13 / AC-14 — model_construct ban via S1-11
# ----------------------------------------------------------------------------


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "check_forbidden_patterns.py"

_OFFENDING_BODY = "RedactedSlice.model_construct(slice={}, findings_count=0, fingerprints=[])\n"


def test_ac12_model_construct_banned_under_output_package(
    tmp_path: Path,
) -> None:
    target_dir = tmp_path / "src" / "codegenie" / "output"
    target_dir.mkdir(parents=True)
    target = target_dir / "synth.py"
    target.write_text(_OFFENDING_BODY, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(target)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode >= 1, result.stdout + result.stderr
    combined = result.stdout + result.stderr
    assert "02-ADR-0010 §Decision" in combined
    assert "production ADR-0033 §3" in combined
    assert "model_construct" in combined


def test_ac12b_surgical_predicate_negative_path(tmp_path: Path) -> None:
    target_dir = tmp_path / "src" / "codegenie" / "parsers"
    target_dir.mkdir(parents=True)
    target = target_dir / "synth.py"
    target.write_text(_OFFENDING_BODY, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(target)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_ac13_runtime_predicate_surface() -> None:
    from scripts.check_forbidden_patterns import (
        _PHASE2_BANNED_PACKAGES,
        _is_under_phase2_banned_package,
    )

    assert "output" in _PHASE2_BANNED_PACKAGES
    assert _is_under_phase2_banned_package(Path("src/codegenie/output/redacted_slice.py")) is True
    assert _is_under_phase2_banned_package(Path("src/codegenie/output/sanitizer.py")) is True
    assert _is_under_phase2_banned_package(Path("src/codegenie/parsers/safe_json.py")) is False


def test_ac14_no_actual_model_construct_calls_in_output_package() -> None:
    pattern = re.compile(r"\.model_construct\s*\(|\bmodel_construct\s*=")
    output_dir = REPO_ROOT / "src" / "codegenie" / "output"
    for py in output_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert pattern.search(text) is None, (
            f"model_construct call form found in {py}: forbidden by 02-ADR-0010"
        )


# ----------------------------------------------------------------------------
# AC-15 / AC-15b — cross-story integration with S3-01
# ----------------------------------------------------------------------------


_AWS_KEY = "AKIAIOSFODNN7EXAMPLE"
_AWS_KEY_2 = "AKIAJANOTHEREXAMPLE0"
_GH_TOKEN = "ghp_" + "a" * 36


def test_ac15_redact_secrets_returns_redacted_slice() -> None:
    from codegenie.output.sanitizer import redact_secrets

    rs, findings = redact_secrets({}, ProbeId("test"))
    assert isinstance(rs, RedactedSlice)
    assert rs.findings_count == 0
    assert rs.fingerprints == []
    assert findings == []


@pytest.mark.parametrize(
    ("input_slice", "expected_count", "expected_unique_fps"),
    [
        ({"node_version": "20.11.1"}, 0, 0),
        ({"env": _AWS_KEY}, 1, 1),
        (
            {
                "a": _AWS_KEY,
                "b": _AWS_KEY_2,
                "c": f"Authorization: token {_GH_TOKEN}",
            },
            3,
            3,
        ),
        ({"a": _AWS_KEY, "b": _AWS_KEY}, 2, 1),
    ],
)
def test_ac15b_cross_story_integration_with_s3_01(
    input_slice: dict[str, Any],
    expected_count: int,
    expected_unique_fps: int,
) -> None:
    from codegenie.output.sanitizer import redact_secrets

    rs, findings = redact_secrets(input_slice, ProbeId("test"))
    assert isinstance(rs, RedactedSlice)
    assert rs.findings_count == expected_count
    assert len(rs.fingerprints) == expected_unique_fps

    # Round-trip through model_validate(model_dump()) — all three invariants.
    reloaded = RedactedSlice.model_validate(rs.model_dump())
    assert reloaded == rs

    for fp in reloaded.fingerprints:
        assert _FP_REGEX.fullmatch(fp), fp
    assert reloaded.findings_count >= len(reloaded.fingerprints)
    assert reloaded.findings_count >= 0


def test_ac16_public_constructor_accessible() -> None:
    # The smart-constructor pattern accepts that the constructor itself is
    # callable; defense is convention + lint + S7-04 boundary test.
    inst = RedactedSlice(slice={}, findings_count=0, fingerprints=[])
    assert isinstance(inst, RedactedSlice)


# ----------------------------------------------------------------------------
# AC-17 / AC-18 — Phase 0/1 invariants preserved
# ----------------------------------------------------------------------------


def test_ac18_jsonvalue_alias_from_parsers_used_for_slice_field() -> None:
    # The slice field accepts a deeply-nested JSONValue without raising.
    inst = RedactedSlice(
        slice={"a": [1, 1.5, True, None, {"b": "<REDACTED:fingerprint=abcdef12>"}]},
        findings_count=1,
        fingerprints=["abcdef12"],
    )
    assert inst.slice["a"][4]["b"] == "<REDACTED:fingerprint=abcdef12>"  # type: ignore[index]


# ----------------------------------------------------------------------------
# Sanity — deep-copy of input is not mutated by construction
# ----------------------------------------------------------------------------


def test_input_slice_not_mutated_by_construction() -> None:
    src = _nested_fixture_slice()
    src_snapshot = copy.deepcopy(src)
    RedactedSlice(slice=src, findings_count=3, fingerprints=["abcdef12"])
    assert src == src_snapshot
