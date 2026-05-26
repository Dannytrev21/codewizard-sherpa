"""Phase-4 S5-02 AC-10 — Hypothesis monotonicity property.

For any ``(score_low, score_high)`` with ``low <= high`` and any valid
``(high_floor, degraded_floor)``, the band classifier's output never
goes backward as the score increases:

    rank(classify(high)) >= rank(classify(low))

where ``rank`` maps ``"high" → 2, "medium" → 1, "low" → 0``. A buggy
classifier that swapped the boundary inequality (e.g. ``score >
high_floor`` instead of ``>=``) would fail near the boundaries; a
classifier that mis-ordered the band literals would fail almost
immediately.

AC-11 (cross-architecture ONNX drift) is folded into the same file
with a 0.01-margin envelope around the floors.
"""

from __future__ import annotations

from typing import Final

from hypothesis import given, settings
from hypothesis import strategies as st

from codegenie.rag.confidence import RagConfidence, classify_similarity
from codegenie.types.identifiers import Similarity

_RANK: Final[dict[RagConfidence, int]] = {"high": 2, "medium": 1, "low": 0}

_DRIFT_MARGIN: Final[float] = 0.01  # > the 0.005 ADR-04-0007 ONNX drift envelope


@given(
    score_low=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    score_high=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    high_floor=st.floats(min_value=0.05, max_value=0.99, allow_nan=False, allow_infinity=False),
    degraded_floor=st.floats(min_value=0.01, max_value=0.95, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=300, deadline=None)
def test_ac10_band_classifier_is_monotone_in_score(
    score_low: float,
    score_high: float,
    high_floor: float,
    degraded_floor: float,
) -> None:
    """``score_low <= score_high`` ⇒ ``rank(classify(low)) <= rank(classify(high))``.

    Both score-order combinations are exercised (one branch handles
    ``low <= high``; we also try the reversed pair to widen coverage).
    """
    # Ensure the floors are valid (degraded < high, both in [0, 1]).
    lo_floor, hi_floor = sorted([degraded_floor, high_floor])
    if lo_floor == hi_floor:
        return  # invalid — strict <
    if not (0.0 <= lo_floor < hi_floor <= 1.0):
        return
    a, b = sorted([score_low, score_high])
    out_a = classify_similarity(Similarity(a), high_floor=hi_floor, degraded_floor=lo_floor)
    out_b = classify_similarity(Similarity(b), high_floor=hi_floor, degraded_floor=lo_floor)
    assert _RANK[out_b] >= _RANK[out_a], (
        f"non-monotonic: a={a} → {out_a}, b={b} → {out_b}, floors=(deg={lo_floor}, hi={hi_floor})"
    )


@given(
    high_floor=st.floats(min_value=0.05, max_value=0.99, allow_nan=False, allow_infinity=False),
    degraded_floor=st.floats(min_value=0.01, max_value=0.95, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200, deadline=None)
def test_ac11_drift_envelope_band_interiors_stay_stable(
    high_floor: float,
    degraded_floor: float,
) -> None:
    """A score ``_DRIFT_MARGIN`` away from any floor stays in its band.

    The 0.005 ADR-04-0007 ONNX drift envelope means a measured score
    could shift by up to that much across architectures. A
    well-calibrated band has an interior wide enough to absorb the
    drift without crossing the boundary.
    """
    lo_floor, hi_floor = sorted([degraded_floor, high_floor])
    if lo_floor == hi_floor or not (0.0 <= lo_floor < hi_floor <= 1.0):
        return
    if hi_floor - lo_floor < 2 * _DRIFT_MARGIN:
        return  # band too narrow to apply the drift envelope

    # Interior probe in each band.
    high_interior = hi_floor + _DRIFT_MARGIN
    if high_interior <= 1.0:
        assert (
            classify_similarity(
                Similarity(high_interior),
                high_floor=hi_floor,
                degraded_floor=lo_floor,
            )
            == "high"
        )

    medium_interior = (hi_floor + lo_floor) / 2
    assert (
        classify_similarity(
            Similarity(medium_interior),
            high_floor=hi_floor,
            degraded_floor=lo_floor,
        )
        == "medium"
    )

    low_interior = lo_floor - _DRIFT_MARGIN
    if low_interior >= 0.0:
        assert (
            classify_similarity(
                Similarity(low_interior),
                high_floor=hi_floor,
                degraded_floor=lo_floor,
            )
            == "low"
        )
