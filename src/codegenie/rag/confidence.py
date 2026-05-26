"""Phase-4 S5-02 — two-threshold band classifier.

Concrete implementation of the S5-01
:class:`~codegenie.rag.retriever.ConfidenceClassifier` Protocol. The
``(score → band)`` mapping is the simplest specification-pattern shape
(table-driven, three branches, no state).

Band rule (ADR-04-0008 §Decision):

* ``similarity >= high_floor`` → ``"high"`` → :class:`RagHit`
* ``degraded_floor <= similarity < high_floor`` → ``"medium"`` →
  :class:`RagDegraded`
* ``similarity < degraded_floor`` → ``"low"`` → :class:`RagMiss` (bare —
  miss-cause observability lives on the S5-01 ``RagMissEvent``, not on
  the variant)

The two thresholds are injected as ``float`` values from the plugin's
``plugin.yaml`` (S7-04). Tiebreak among equal-top candidates is
**lexicographic on ``record.id``** — never ``hash()`` (which is
``PYTHONHASHSEED``-salted and would make the choice
process-nondeterministic, breaking the S5-01 idempotence invariant).

Discipline:

* No module-level state, no logger, no event emission, no I/O.
* :class:`BandClassifier` is a frozen kw-only dataclass — positional
  construction is a ``TypeError`` and mutation post-construction is a
  ``FrozenInstanceError``.
* ``__post_init__`` validates ``0.0 <= degraded_floor < high_floor <= 1.0``;
  rejects ``NaN`` (which fails every comparison silently).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal, assert_never

from codegenie.rag.models import (
    RagDegraded,
    RagHit,
    RagMiss,
    RetrievalOutcome,
)
from codegenie.rag.retriever import FencedRetrievalCandidate
from codegenie.types.identifiers import Similarity

__all__ = [
    "BandClassifier",
    "RagConfidence",
    "classify_similarity",
]


RagConfidence = Literal["high", "medium", "low"]
"""Closed three-value band label. ``BandClassifier`` folds it into the
:data:`RetrievalOutcome` variant via the ``match`` in :meth:`classify`."""


_INVALID_FLOORS_MSG: Final[str] = (
    "degraded_floor must be strictly less than high_floor and both must "
    "lie in [0.0, 1.0]; got high_floor={high_floor!r}, "
    "degraded_floor={degraded_floor!r}"
)


def classify_similarity(
    score: Similarity,
    *,
    high_floor: float,
    degraded_floor: float,
) -> RagConfidence:
    """Return the ``RagConfidence`` band for ``score`` given the two floors.

    Pure: same inputs ⇒ same output across processes / Python versions.
    No state read, no I/O, no ``hash()`` — the function is a
    three-line specification-pattern dispatch.

    Inclusivity: ``score >= high_floor`` is the high band (ties at the
    high boundary go to ``"high"``, not ``"medium"``);
    ``degraded_floor <= score < high_floor`` is the medium band
    (ties at the degraded boundary go to ``"medium"``, not ``"low"``).
    """
    if score >= high_floor:
        return "high"
    if score >= degraded_floor:
        return "medium"
    return "low"


@dataclass(frozen=True, kw_only=True)
class BandClassifier:
    """Concrete :class:`~codegenie.rag.retriever.ConfidenceClassifier`.

    Constructor is keyword-only — positional ``BandClassifier(0.85, 0.65)``
    fails with ``TypeError`` (kw_only=True). Defaults match
    ADR-04-0008 §Pattern fit (``high_floor=0.85``, ``degraded_floor=0.65``)
    but the plugin.yaml-shipped values from S7-04 override at
    construction time.

    Frozen — ``BandClassifier(...).high_floor = 0.5`` raises
    ``FrozenInstanceError``. The classifier carries no mutable state.
    """

    high_floor: float = 0.85
    degraded_floor: float = 0.65

    def __post_init__(self) -> None:
        hf, df = self.high_floor, self.degraded_floor
        if math.isnan(hf) or math.isnan(df) or not (0.0 <= df < hf <= 1.0):
            raise ValueError(_INVALID_FLOORS_MSG.format(high_floor=hf, degraded_floor=df))

    def classify(
        self,
        candidates: Sequence[FencedRetrievalCandidate],
    ) -> RetrievalOutcome:
        """Classify the top-scored candidate via :func:`classify_similarity`.

        Tiebreak among equal-top candidates is lexicographic on
        ``record.id`` — string ordering, never ``hash()``. Empty input
        returns bare :class:`RagMiss` (the retriever already short-
        circuits the empty path with a reason-bearing event; this is
        a defensive secondary path).
        """
        if not candidates:
            return RagMiss()
        top = max(candidates, key=lambda c: (c.score, _lex_inverse(c.record.id)))
        confidence = classify_similarity(
            Similarity(top.score),
            high_floor=self.high_floor,
            degraded_floor=self.degraded_floor,
        )
        match confidence:
            case "high":
                return RagHit(few_shot=top.record, score=Similarity(top.score))
            case "medium":
                return RagDegraded(near_match=top.record, score=Similarity(top.score))
            case "low":
                return RagMiss()
            case _ as unreachable:
                assert_never(unreachable)


def _lex_inverse(record_id: str) -> tuple[int, ...]:
    """Sort-key inverse so ``max(...)`` prefers the lexicographically-
    smallest ``record_id``.

    ``max(candidates, key=lambda c: (c.score, _lex_inverse(c.record.id)))``
    picks the highest score AND, on ties, the smallest id. The inverse
    is computed by negating each codepoint — a tuple of ints sorts the
    opposite way to the original string, so ``max`` returns the
    desired minimum.
    """
    return tuple(-ord(ch) for ch in record_id)
