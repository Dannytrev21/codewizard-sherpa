"""Unit tests for ``codegenie.probes._shared.scanner_outcome`` — story 02 S5-01.

Covers AC-1, AC-3 through AC-18 (the scanner-side of the AC matrix); the
scenario-side is mirrored in ``tests/unit/probes/layer_c/test_scenario_result.py``
and the property-test pass lives at ``tests/property/test_sum_types_roundtrip.py``.

The hardening template is S1-01 (``test_freshness.py``): discriminator-string
pinning, JSON-shape pin, nested-type roundtrip, exhaustive ``match`` at every
level of the sum, ``frozen=True`` + ``extra="forbid"`` mutation-resistance,
literal ``__all__`` pin, source-scan against ``model_construct``.
"""

from __future__ import annotations

from pathlib import Path
from typing import assert_never

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.probes._shared.scanner_outcome import (
    STDERR_TAIL_CAP_BYTES,
    Finding,
    ScannerFailed,
    ScannerOutcome,
    ScannerRan,
    ScannerSkipped,
)

# ---------------------------------------------------------------------------
# Test fixtures — one of each variant; ``ScannerRan`` carries one ``Finding``
# so the nested-type-preservation assertion has something to bite on.
# ---------------------------------------------------------------------------

SCANNER_OUTCOMES: list[ScannerOutcome] = [
    ScannerRan(
        findings=[
            Finding(id="rule-1", severity="medium", metadata={"path": "src/foo.py"}),
        ]
    ),
    ScannerSkipped(reason="tool_missing"),
    ScannerFailed(exit_code=2, stderr_tail="boom"),
]


# ---------------------------------------------------------------------------
# AC-5 — round-trip identity + nested-type preservation.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("instance", SCANNER_OUTCOMES)
def test_scanner_outcome_roundtrip_identity(instance: ScannerOutcome) -> None:
    adapter: TypeAdapter[ScannerOutcome] = TypeAdapter(ScannerOutcome)
    encoded = adapter.dump_json(instance)
    decoded = adapter.validate_json(encoded)
    assert decoded == instance
    assert type(decoded) is type(instance)
    if isinstance(instance, ScannerRan):
        assert isinstance(decoded, ScannerRan)
        assert [type(f) for f in decoded.findings] == [type(f) for f in instance.findings]


# ---------------------------------------------------------------------------
# AC-12 — discriminator strings are exactly pinned.
# ---------------------------------------------------------------------------


def test_scanner_outcome_discriminator_strings_are_exactly_pinned() -> None:
    assert ScannerRan().kind == "ran"
    assert ScannerSkipped(reason="tool_missing").kind == "skipped"
    assert ScannerFailed(exit_code=1, stderr_tail="").kind == "failed"


# ---------------------------------------------------------------------------
# AC-13 — JSON shape pinned (catches symmetric ``kind → tag`` rename).
# ---------------------------------------------------------------------------


def test_scanner_skipped_json_shape_pinned() -> None:
    dump = ScannerSkipped(reason="tool_missing").model_dump(mode="json")
    assert dump == {"kind": "skipped", "reason": "tool_missing"}


def test_scanner_failed_json_shape_pinned() -> None:
    """S5-04 extends ScannerFailed with an optional ``reason`` field
    (default ``None``) so the ``failed`` discriminator can distinguish
    invalid-JSON from non-zero-exit failures without changing the
    discriminator key. The baseline (no ``reason``) dump still pins."""
    dump = ScannerFailed(exit_code=2, stderr_tail="err").model_dump(mode="json")
    assert dump == {"kind": "failed", "exit_code": 2, "stderr_tail": "err", "reason": None}
    typed = ScannerFailed(exit_code=2, stderr_tail="err", reason="invalid_json").model_dump(
        mode="json"
    )
    assert typed == {
        "kind": "failed",
        "exit_code": 2,
        "stderr_tail": "err",
        "reason": "invalid_json",
    }


# ---------------------------------------------------------------------------
# AC-14 — unknown discriminator is rejected (top level).
# ---------------------------------------------------------------------------


def test_scanner_outcome_unknown_discriminator_is_rejected() -> None:
    adapter: TypeAdapter[ScannerOutcome] = TypeAdapter(ScannerOutcome)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "bogus_scanner"})


# ---------------------------------------------------------------------------
# AC-6 — exhaustive match over ``ScannerOutcome``.
# ---------------------------------------------------------------------------


def test_scanner_outcome_match_is_exhaustive() -> None:
    seen: set[str] = set()
    for outcome in SCANNER_OUTCOMES:
        match outcome:
            case ScannerRan():
                seen.add("ran")
            case ScannerSkipped():
                seen.add("skipped")
            case ScannerFailed():
                seen.add("failed")
            case _ as unexpected:
                assert_never(unexpected)
    assert seen == {"ran", "skipped", "failed"}


# ---------------------------------------------------------------------------
# AC-17 — frozen + extra="forbid" mutation resistance.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("instance", SCANNER_OUTCOMES)
def test_scanner_outcomes_are_frozen(instance: ScannerOutcome) -> None:
    with pytest.raises(ValidationError):
        instance.kind = "other"  # type: ignore[misc]


def test_scanner_ran_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        ScannerRan.model_validate({"kind": "ran", "findings": [], "extra_field": 1})


def test_scanner_skipped_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        ScannerSkipped.model_validate(
            {"kind": "skipped", "reason": "tool_missing", "extra_field": 1}
        )


def test_scanner_failed_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        ScannerFailed.model_validate(
            {"kind": "failed", "exit_code": 1, "stderr_tail": "x", "extra_field": 1}
        )


# ---------------------------------------------------------------------------
# AC: ScannerFailed.stderr_tail cap (boundary + named constant).
# ---------------------------------------------------------------------------


def test_stderr_tail_cap_bytes_is_named_constant() -> None:
    assert STDERR_TAIL_CAP_BYTES == 4096


@pytest.mark.parametrize(
    "input_length,expected_length",
    [(0, 0), (1, 1), (4095, 4095), (4096, 4096), (4097, 4096), (8192, 4096)],
)
def test_scanner_failed_stderr_tail_truncates_at_cap(
    input_length: int, expected_length: int
) -> None:
    s = "x" * input_length
    outcome = ScannerFailed(exit_code=1, stderr_tail=s)
    assert len(outcome.stderr_tail) == expected_length


# ---------------------------------------------------------------------------
# AC: ScannerSkipped.reason Literal closure.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reason", ["tool_missing", "tool_unhealthy", "upstream_unavailable"])
def test_scanner_skipped_reason_accepts_each_literal(reason: str) -> None:
    inst = ScannerSkipped.model_validate({"kind": "skipped", "reason": reason})
    assert inst.reason == reason


@pytest.mark.parametrize("reason", ["", "ad_hoc", "TOOL_MISSING"])
def test_scanner_skipped_reason_rejects_out_of_set(reason: str) -> None:
    with pytest.raises(ValidationError):
        ScannerSkipped.model_validate({"kind": "skipped", "reason": reason})


# ---------------------------------------------------------------------------
# AC: Finding.severity Literal closure.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("severity", ["info", "low", "medium", "high", "critical"])
def test_finding_severity_accepts_each_literal(severity: str) -> None:
    inst = Finding.model_validate(
        {"kind": "finding", "id": "r", "severity": severity, "metadata": {}}
    )
    assert inst.severity == severity


@pytest.mark.parametrize("severity", ["unknown", "INFO", ""])
def test_finding_severity_rejects_out_of_set(severity: str) -> None:
    with pytest.raises(ValidationError):
        Finding.model_validate({"kind": "finding", "id": "r", "severity": severity, "metadata": {}})


# ---------------------------------------------------------------------------
# AC-16 — Finding.metadata recursive JSONValue round-trip.
# ---------------------------------------------------------------------------


def test_finding_metadata_jsonvalue_roundtrip() -> None:
    deep_metadata = {
        "a": [1, 2.0, "x", True, None, {"nested": [{"deep": [None]}]}],
    }
    inst = ScannerRan(findings=[Finding(id="rule-1", severity="medium", metadata=deep_metadata)])
    adapter: TypeAdapter[ScannerOutcome] = TypeAdapter(ScannerOutcome)
    decoded = adapter.validate_json(adapter.dump_json(inst))
    assert isinstance(decoded, ScannerRan)
    assert decoded.findings[0].metadata == deep_metadata


# ---------------------------------------------------------------------------
# AC-18 — ``__all__`` is pinned literally.
# ---------------------------------------------------------------------------


EXPECTED_SCANNER_NAMES = {
    "Finding",
    "ScannerFailed",
    "ScannerOutcome",
    "ScannerRan",
    "ScannerSkipped",
    "STDERR_TAIL_CAP_BYTES",
}


def test_scanner_outcome_all_exports_are_pinned() -> None:
    import codegenie.probes._shared.scanner_outcome as mod

    assert set(mod.__all__) == EXPECTED_SCANNER_NAMES


# ---------------------------------------------------------------------------
# AC: source-scan against ``model_construct``.
# ---------------------------------------------------------------------------


def test_scanner_outcome_module_has_no_model_construct() -> None:
    """A defense-in-depth scan in addition to the forbidden-patterns hook."""
    import codegenie.probes._shared.scanner_outcome as mod

    source = Path(mod.__file__).read_text()
    assert "model_construct" not in source
