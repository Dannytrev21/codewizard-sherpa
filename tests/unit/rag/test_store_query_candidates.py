"""Phase-4 S4-03 candidate-read amendment (S5-01 precondition).

:meth:`ChromaPersistentStore.query_candidates` returns the **raw** scored
candidate set so the retriever (S5-01) can chain-verify,
model-mismatch-filter, and fence *before* the band classifier runs.

These tests pin:

* AC-Q1 — empty partition ⇒ empty sequence (NOT ``RagMiss``).
* AC-Q2 — closed store ⇒ ``StoreClosed`` (mirrors ``_query_with_embedding``).
* AC-Q3 — round-trip: a seeded record comes back as a
  ``ScoredSolvedExample`` with a high score.
* AC-Q4 — the Protocol surface exposes ``query_candidates``.
* AC-Q5 — no pre-classification: the return type is
  ``Sequence[ScoredSolvedExample]``, never ``RetrievalOutcome``.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from codegenie.rag.errors import StoreClosed
from codegenie.rag.models import ScoredSolvedExample
from codegenie.rag.store import (
    ChromaPersistentStore,
    SolvedExampleStore,
    SolvedExampleWriteCapability,
)
from codegenie.types.identifiers import SolvedExampleId, WorkflowId
from tests.fixtures.rag.fake_solved_example import (
    make_query_matching,
    make_solved_example,
)


async def test_q1_empty_partition_returns_empty_sequence(tmp_path: Path) -> None:
    """An empty partition contributes zero candidates, not a ``RagMiss``."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    try:
        # Build a query referencing a partition that has never been written to.
        example = make_solved_example(id_="ex-never")
        q = make_query_matching(example)
        candidates = await store.query_candidates(q, embedding=example.embedding_vector, top_k=5)
        assert candidates == []
        # Empty list is NOT a RagMiss — the retriever folds the empty
        # sequence into RagMiss with an audit event.
        assert isinstance(candidates, list)
    finally:
        store.close()


async def test_q2_closed_store_raises_store_closed(tmp_path: Path) -> None:
    store = ChromaPersistentStore(root_dir=tmp_path)
    store.close()
    example = make_solved_example(id_="ex-001")
    q = make_query_matching(example)
    with pytest.raises(StoreClosed):
        await store.query_candidates(q, embedding=example.embedding_vector)


async def test_q3_round_trip_yields_scored_solved_example(tmp_path: Path) -> None:
    """Load-bearing read-side round-trip: a record added to the store
    comes back as a typed ``ScoredSolvedExample`` whose ``score`` is the
    raw cosine value (NOT a band-classifier verdict)."""
    store = ChromaPersistentStore(root_dir=tmp_path)
    try:
        cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-q3"))
        example = make_solved_example(id_="ex-q3")
        await store.add(example, cap)

        q = make_query_matching(example)
        candidates = await store.query_candidates(q, embedding=example.embedding_vector, top_k=5)
        assert len(candidates) == 1
        scored = candidates[0]
        assert isinstance(scored, ScoredSolvedExample)
        assert scored.record.id == SolvedExampleId("ex-q3")
        # Score is the raw cosine — NOT a Literal band ("hit"/"degraded"/"miss").
        assert isinstance(scored.score, float)
        assert scored.score >= 0.99
        # Sanity: ``Similarity`` is a NewType[float], scored.score satisfies
        # the [-1, 1] bound (the model_validate would have rejected otherwise).
        assert -1.0 <= scored.score <= 1.0
    finally:
        store.close()


def test_q4_protocol_exposes_query_candidates() -> None:
    """The :class:`SolvedExampleStore` Protocol declares
    ``query_candidates`` so a Phase-11 pgvector adapter must implement it."""
    assert hasattr(SolvedExampleStore, "query_candidates")
    sig = inspect.signature(SolvedExampleStore.query_candidates)
    # Keyword-only ``embedding`` + keyword-only ``top_k`` (default 5).
    params = sig.parameters
    assert "q" in params
    assert "embedding" in params
    assert params["embedding"].kind is inspect.Parameter.KEYWORD_ONLY
    assert "top_k" in params
    assert params["top_k"].default == 5


def test_q5_query_candidates_does_not_return_retrieval_outcome() -> None:
    """Pre-classification at the store layer is the failure mode S5-01
    validation §F1 rejected. The annotated return type must be
    ``Sequence[ScoredSolvedExample]``, never ``RetrievalOutcome``.
    """
    sig = inspect.signature(SolvedExampleStore.query_candidates)
    # The string form of the annotation; mypy validates the static type
    # at typecheck time, this is the runtime tripwire.
    annotation = str(sig.return_annotation)
    assert "ScoredSolvedExample" in annotation, (
        "Phase-4 S4-03 amendment: query_candidates must return "
        "Sequence[ScoredSolvedExample]; pre-classification at the store "
        "layer is the failure mode the amendment closes."
    )
    assert "RetrievalOutcome" not in annotation
