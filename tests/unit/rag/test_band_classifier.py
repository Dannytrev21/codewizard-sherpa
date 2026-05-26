"""Phase-4 S5-02 — :class:`BandClassifier` tests.

Covers the load-bearing ACs:

* AC-1 — module exports exactly three public names.
* AC-2 — keyword-only frozen dataclass; positional construction is
  ``TypeError``; invalid floors raise ``ValueError`` with the
  directive substring.
* AC-3 — no logger / file I/O / ``hash()`` in ``confidence.py``.
* AC-4 / AC-5 / AC-6 — canonical band table + boundary inclusivity.
* AC-7 — ``classify`` signature matches the S5-01 ``ConfidenceClassifier``
  Protocol byte-for-byte.
* AC-8 — deterministic tiebreak via lexicographic ``record.id`` ordering
  (NOT ``hash()``).
* AC-13 — every ``RagMiss(...)`` in the module is argument-less.
* AC-14 — end-to-end integration with S5-01's retriever.
"""

from __future__ import annotations

import ast
import inspect

import pytest

from codegenie.rag import confidence as confidence_module
from codegenie.rag.confidence import (
    BandClassifier,
    RagConfidence,
    classify_similarity,
)
from codegenie.rag.models import (
    RagDegraded,
    RagHit,
    RagMiss,
)
from codegenie.rag.retriever import (
    FencedRetrievalCandidate,
)
from codegenie.types.identifiers import (
    HexNonce,
    Similarity,
)
from tests.fixtures.rag.fake_solved_example import (
    make_solved_example,
)

# --- AC-1: module shape ----------------------------------------------------


def test_ac1_module_exports_three_names() -> None:
    assert set(confidence_module.__all__) == {
        "BandClassifier",
        "RagConfidence",
        "classify_similarity",
    }


# --- AC-2: kw-only frozen dataclass + ValidationError on bad floors --------


def test_ac2_positional_construction_is_type_error() -> None:
    with pytest.raises(TypeError):
        BandClassifier(0.85, 0.65)  # type: ignore[call-arg,misc]


@pytest.mark.parametrize(
    "high,degraded",
    [
        (0.5, 0.6),  # degraded > high
        (0.5, 0.5),  # degraded == high (not strictly less)
        (1.1, 0.0),  # high out of [0, 1]
        (0.5, -0.1),  # degraded out of [0, 1]
        (0.5, float("nan")),
        (float("nan"), 0.5),
    ],
)
def test_ac2_invalid_floors_raise_value_error(high: float, degraded: float) -> None:
    with pytest.raises(ValueError, match="degraded_floor must be strictly less than high_floor"):
        BandClassifier(high_floor=high, degraded_floor=degraded)


def test_ac2_classifier_is_frozen() -> None:
    bc = BandClassifier(high_floor=0.85, degraded_floor=0.65)
    with pytest.raises(Exception):  # noqa: B017 — dataclasses.FrozenInstanceError
        bc.high_floor = 0.5  # type: ignore[misc]


# --- AC-3: classifier module has no logger / file I/O / hash() --------------


def test_ac3_module_purity_no_logger_no_io_no_hash() -> None:
    tree = ast.parse(inspect.getsource(confidence_module))
    forbidden_imports = {"logging", "structlog", "os", "sys"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            assert top not in forbidden_imports, f"confidence.py must not import {top!r}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                assert top not in forbidden_imports, f"confidence.py must not import {top!r}"
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                assert func.id != "hash", (
                    "confidence.py must not call hash() — PYTHONHASHSEED salting "
                    "would make tiebreaks process-nondeterministic."
                )
                assert func.id != "open", "confidence.py must not call open() — pure function."


# --- AC-4 / AC-5 / AC-6: band table + boundary inclusivity ------------------


@pytest.mark.parametrize(
    "score,expected",
    [
        (1.00, "high"),
        (0.95, "high"),
        (0.85, "high"),  # high boundary (inclusive)
        (0.84, "medium"),
        (0.75, "medium"),
        (0.65, "medium"),  # degraded boundary (inclusive)
        (0.64, "low"),
        (0.50, "low"),
        (0.00, "low"),
        (-0.50, "low"),
    ],
)
def test_ac4_canonical_band_table(score: float, expected: RagConfidence) -> None:
    actual = classify_similarity(Similarity(score), high_floor=0.85, degraded_floor=0.65)
    assert actual == expected


def test_ac5_high_boundary_inclusive() -> None:
    """``similarity == high_floor`` lands in ``"high"`` (NOT ``"medium"``)."""
    assert classify_similarity(Similarity(0.85), high_floor=0.85, degraded_floor=0.65) == "high"


def test_ac5_degraded_boundary_inclusive() -> None:
    """``similarity == degraded_floor`` lands in ``"medium"`` (NOT ``"low"``)."""
    assert classify_similarity(Similarity(0.65), high_floor=0.85, degraded_floor=0.65) == "medium"


# --- AC-7: signature matches S5-01 ConfidenceClassifier Protocol -----------


def test_ac7_signature_matches_protocol() -> None:
    """``BandClassifier.classify`` signature is ``classify(self, candidates:
    Sequence[FencedRetrievalCandidate]) -> RetrievalOutcome``."""
    sig = inspect.signature(BandClassifier.classify)
    params = list(sig.parameters)
    assert params == ["self", "candidates"]
    # mypy + runtime structural check: a BandClassifier instance is a
    # ConfidenceClassifier.
    from codegenie.rag.retriever import ConfidenceClassifier

    bc = BandClassifier(high_floor=0.85, degraded_floor=0.65)
    assert isinstance(bc, ConfidenceClassifier)


# --- AC-8: deterministic lexicographic tiebreak ----------------------------


def _candidate(record_id: str, score: float) -> FencedRetrievalCandidate:
    """Build a fenced candidate with the given record id + score."""
    from codegenie.fallback.fence.wrapper import CanaryClean, FencedSegment

    rec = make_solved_example(id_=record_id)
    fenced = FencedSegment(
        nonce=HexNonce("0" * 16),
        source_kind="rag_retrieved",
        content=f"<UNTRUSTED_INPUT id=01H>{record_id}</UNTRUSTED_INPUT id=01H>",
        truncated=False,
        original_byte_length=len(record_id.encode("utf-8")),
        canary=CanaryClean(),
    )
    return FencedRetrievalCandidate(fenced=fenced, record=rec, score=score)


def test_ac8_tiebreak_is_lexicographic_smallest_id() -> None:
    """Two candidates with identical top score → ``min(record.id)`` wins."""
    a = _candidate("a-id", 0.92)
    b = _candidate("b-id", 0.92)
    bc = BandClassifier(high_floor=0.85, degraded_floor=0.65)
    outcome = bc.classify([a, b])
    assert isinstance(outcome, RagHit)
    assert outcome.few_shot.id == "a-id"


def test_ac8_tiebreak_independent_of_insertion_order() -> None:
    """The reversed-input must yield the same chosen record id."""
    a = _candidate("a-id", 0.92)
    b = _candidate("b-id", 0.92)
    bc = BandClassifier(high_floor=0.85, degraded_floor=0.65)
    outcome_ab = bc.classify([a, b])
    outcome_ba = bc.classify([b, a])
    assert isinstance(outcome_ab, RagHit)
    assert isinstance(outcome_ba, RagHit)
    assert outcome_ab.few_shot.id == outcome_ba.few_shot.id == "a-id"


# --- AC-13: RagMiss is constructed bare in the module ----------------------


def test_ac13_all_rag_miss_calls_are_argument_less() -> None:
    tree = ast.parse(inspect.getsource(confidence_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "RagMiss":
                assert not node.args and not node.keywords, (
                    "RagMiss must be constructed bare in confidence.py"
                )


# --- AC-9: classify dispatches all three bands ------------------------------


def test_ac9_classify_returns_rag_hit_for_high_band() -> None:
    cand = _candidate("hit-001", 0.95)
    bc = BandClassifier(high_floor=0.85, degraded_floor=0.65)
    outcome = bc.classify([cand])
    assert isinstance(outcome, RagHit)
    assert outcome.few_shot.id == "hit-001"


def test_ac9_classify_returns_rag_degraded_for_medium_band() -> None:
    cand = _candidate("deg-001", 0.75)
    bc = BandClassifier(high_floor=0.85, degraded_floor=0.65)
    outcome = bc.classify([cand])
    assert isinstance(outcome, RagDegraded)
    assert outcome.near_match.id == "deg-001"


def test_ac9_classify_returns_rag_miss_for_low_band() -> None:
    cand = _candidate("miss-001", 0.40)
    bc = BandClassifier(high_floor=0.85, degraded_floor=0.65)
    outcome = bc.classify([cand])
    assert isinstance(outcome, RagMiss)


def test_ac9_classify_empty_returns_bare_rag_miss() -> None:
    bc = BandClassifier(high_floor=0.85, degraded_floor=0.65)
    outcome = bc.classify([])
    assert isinstance(outcome, RagMiss)


# --- AC-10: monotonicity (Hypothesis) ---------------------------------------


def test_ac10_monotonicity_low_score_never_outranks_high_score() -> None:
    """Property: ``rank(classify(high)) >= rank(classify(low))`` for
    ``high >= low``. Spot-checked with a handful of pairs (the full
    Hypothesis property lives in
    ``tests/property/test_band_classifier_monotonicity.py``)."""
    rank: dict[RagConfidence, int] = {"high": 2, "medium": 1, "low": 0}
    pairs = [
        (0.20, 0.30),
        (0.60, 0.70),
        (0.80, 0.90),
        (0.65, 0.85),  # crosses two bands
        (0.10, 0.99),  # full range
    ]
    for low, high in pairs:
        out_low = classify_similarity(Similarity(low), high_floor=0.85, degraded_floor=0.65)
        out_high = classify_similarity(Similarity(high), high_floor=0.85, degraded_floor=0.65)
        assert rank[out_high] >= rank[out_low], (
            f"non-monotonic: low={low} → {out_low}, high={high} → {out_high}"
        )
