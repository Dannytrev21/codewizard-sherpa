"""Phase-4 S6-03 — :class:`ConfidenceGate` harvest predicate.

ADR-04-0009 §Decision: the inline auto-harvest fires iff
``trust.passed AND trust.confidence == "high"``. The gate is a named
Specification-pattern predicate (testable in isolation; future
amendments are additive AND-clauses) so the on_validated body in
``tier.py`` is a single ``self._confidence_gate.passes(trust)`` call —
never an inline ``trust.passed and trust.confidence == "high"`` ladder.

Two clauses, separable + named (AC-4):

* :meth:`_TrustPassed.passes` — the trust outcome itself passed
  (no failing signals).
* :meth:`_HighConfidence.passes` — the trust outcome's confidence
  band is ``"high"`` (NOT ``"degraded"``).

The combined :meth:`ConfidenceGate.passes` evaluates both clauses;
the named clauses are public for unit testing in isolation against
the shipped ``TrustOutcome.confidence: Literal["high", "degraded"]``
type (ADR-04-0009 §Tradeoffs row 6).
"""

from __future__ import annotations

from dataclasses import dataclass

from codegenie.transforms.outcomes import TrustOutcome

__all__ = [
    "ConfidenceGate",
]


@dataclass(frozen=True, slots=True)
class _TrustPassed:
    """Clause 1: the trust outcome passed (no failing signals)."""

    @staticmethod
    def passes(trust: TrustOutcome) -> bool:
        return trust.passed


@dataclass(frozen=True, slots=True)
class _HighConfidence:
    """Clause 2: the trust outcome's confidence band is exactly ``"high"``."""

    @staticmethod
    def passes(trust: TrustOutcome) -> bool:
        return trust.confidence == "high"


@dataclass(frozen=True, slots=True)
class ConfidenceGate:
    """Auto-harvest predicate over a :class:`TrustOutcome`.

    ``ConfidenceGate().passes(trust)`` returns ``True`` iff both
    named clauses pass — ADR-04-0009 §Decision specifies the AND
    composition. A future ADR amendment may add a third clause (e.g.,
    minimum confidence-vector dimensions); the additive-AND shape
    means each clause stays independently testable.
    """

    def passes(self, trust: TrustOutcome) -> bool:
        return _TrustPassed.passes(trust) and _HighConfidence.passes(trust)
