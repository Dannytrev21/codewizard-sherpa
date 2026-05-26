"""Phase-4 S6-03 AC-4 + AC-5 — :class:`ConfidenceGate` truth table.

Table-driven over the shipped ``TrustOutcome.confidence: Literal["high",
"degraded"]`` × ``passed: bool`` matrix. Asserts the gate fires iff both
clauses pass (named separable Specification-pattern composition).
"""

from __future__ import annotations

import pytest

from codegenie.fallback.confidence_gate import ConfidenceGate
from codegenie.transforms.outcomes import TrustOutcome


def _trust(*, passed: bool, confidence: str) -> TrustOutcome:
    """Build a valid TrustOutcome — the model enforces
    ``passed == (failing == ())`` so when constructing a failing
    outcome we add a placeholder failing signal."""
    from codegenie.types.identifiers import SignalKind

    failing: tuple[SignalKind, ...] = () if passed else (SignalKind("test.failure"),)
    return TrustOutcome(
        passed=passed,
        confidence=confidence,  # type: ignore[arg-type]
        signals=(),
        failing=failing,
    )


@pytest.mark.parametrize(
    ("passed", "confidence", "expected"),
    [
        (True, "high", True),  # both clauses pass
        (True, "degraded", False),  # confidence too low
        (False, "high", False),  # didn't pass
        (False, "degraded", False),  # both clauses fail
    ],
)
def test_ac4_gate_truth_table(passed: bool, confidence: str, expected: bool) -> None:
    """Auto-harvest fires iff trust.passed AND trust.confidence == 'high'."""
    gate = ConfidenceGate()
    trust = _trust(passed=passed, confidence=confidence)
    assert gate.passes(trust) is expected


def test_ac4_gate_is_frozen_dataclass() -> None:
    """The gate is stateless — frozen dataclass with no constructor args."""
    import dataclasses

    assert dataclasses.is_dataclass(ConfidenceGate)
    # No parameters in __init__ — the gate is pure logic.
    gate = ConfidenceGate()
    with pytest.raises(Exception):  # noqa: B017
        gate._x = 1  # type: ignore[attr-defined]


def test_ac4_only_one_public_method_named_passes() -> None:
    """The gate exports exactly one public method — ``passes``."""
    public_methods = {
        name
        for name in dir(ConfidenceGate)
        if not name.startswith("_") and callable(getattr(ConfidenceGate, name))
    }
    assert public_methods == {"passes"}
