"""Phase-4 S5-01 — :class:`SolvedExampleRetriever` outcome paths.

Covers the load-bearing return-shape ACs:

* AC-4 — empty store returns bare ``RagMiss()`` + ``RagMissEvent(reason="empty_store")``
  and never invokes the classifier.
* AC-5, AC-6, AC-7 — chain-orphan exclusion: ``record_verifier`` returning
  ``False`` excludes the record + emits ``RagRecordChainOrphan``; all-orphan
  returns bare ``RagMiss`` + ``RagMissEvent(reason="all_candidates_chain_orphan")``.
* AC-8, AC-9 — fence is called once per surviving candidate with
  ``source_kind="rag_retrieved"``.
* AC-13 — return type is the closed three-variant union; ``RagMiss`` stays
  bare (the test would fail if a ``reason`` field were added).
* AC-17 — ``model_digest_filter`` hook: ``None`` is passthrough; excluding
  all records returns bare ``RagMiss`` + ``RagMissEvent(reason="all_candidates_model_mismatch")``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from codegenie.plugins.events import EventLog
from codegenie.rag.models import (
    RagDegraded,
    RagHit,
    RagMiss,
    ScoredSolvedExample,
)
from codegenie.rag.retriever import (
    FencedRetrievalCandidate,
    SolvedExampleRetriever,
)
from codegenie.types.identifiers import (
    ChainHead,
    HexNonce,
    Similarity,
    WorkflowId,
)
from tests.fixtures.rag.fake_solved_example import (
    make_query_matching,
    make_solved_example,
)

_DEFAULT_SPAN_HEAD: ChainHead = ChainHead("b" * 64)


class _StubSpanningChainLog:
    def __init__(self, head: ChainHead | None = None) -> None:
        self._head = head if head is not None else _DEFAULT_SPAN_HEAD

    def contains_chain_head(self, head: ChainHead) -> bool:
        del head
        return True

    def head(self) -> ChainHead:
        return self._head


def _build_fence_stub() -> tuple[Any, list[str]]:
    """Build a FenceWrapper-shaped stub that records source_kind per call."""
    from codegenie.fallback.fence.wrapper import CanaryClean, FencedSegment

    source_kinds: list[str] = []

    def _fence(payload: str, source_kind: str) -> Any:
        source_kinds.append(source_kind)
        return FencedSegment(
            nonce=HexNonce("0" * 16),
            source_kind=source_kind,  # type: ignore[arg-type]
            content=f"<UNTRUSTED_INPUT id=01H>{payload}</UNTRUSTED_INPUT id=01H>",
            truncated=False,
            original_byte_length=len(payload.encode("utf-8")),
            canary=CanaryClean(),
        )

    fw = MagicMock()
    fw.fence = _fence
    return fw, source_kinds


async def _build_retriever(
    tmp_path: Path,
    *,
    store_candidates: list[ScoredSolvedExample],
    verifier_decision: Any,
    classifier_pyfunc: Any | None = None,
    model_digest_filter: Any | None = None,
) -> tuple[
    SolvedExampleRetriever,
    Any,  # classifier mock
    list[str],  # source_kinds
    list[Any],  # emitted events
    EventLog,
]:
    """Construct a retriever with stub collaborators that capture call args."""
    example_for_qb = store_candidates[0].record if store_candidates else make_solved_example()
    q = make_query_matching(example_for_qb)

    def qb(advisory: Any, repo_ctx: Any) -> Any:
        del advisory, repo_ctx
        return q

    def qtb(_q: Any) -> str:
        return "query text"

    embedder = MagicMock()
    embedder.embed = lambda text: example_for_qb.embedding_vector

    store = MagicMock()

    async def _qc(_q: Any, *, embedding: Any, top_k: int) -> Any:
        del embedding, top_k
        return store_candidates

    store.query_candidates = _qc

    if callable(verifier_decision):
        verifier = verifier_decision
    else:
        verifier = lambda r, log: bool(verifier_decision)  # noqa: E731

    fw, source_kinds = _build_fence_stub()

    classifier = MagicMock()
    if classifier_pyfunc is None:

        def _default_classify(candidates: Any) -> Any:
            cand: FencedRetrievalCandidate = candidates[0]
            return RagHit(few_shot=cand.record, score=Similarity(cand.score))

        classifier.classify = _default_classify
    else:
        classifier.classify = classifier_pyfunc

    # Capture the events emitted to the in-memory log via replay() below.
    event_log = EventLog(
        root=tmp_path,
        workflow_id=WorkflowId("01HRETRIEVER0OUTCOMETESTWX"),
    )

    retriever = SolvedExampleRetriever(
        store=store,
        embedder=embedder,
        spanning_log=_StubSpanningChainLog(),
        record_verifier=verifier,
        fence_wrapper=fw,
        query_builder=qb,
        query_text_builder=qtb,
        confidence_classifier=classifier,
        event_log=event_log,
        model_digest_filter=model_digest_filter,
    )
    return retriever, classifier, source_kinds, [], event_log


def _emitted_event_types(event_log: EventLog, tmp_path: Path) -> list[str]:
    """Read back the workflow-internal events written by the test run."""
    event_log.flush()  # type: ignore[attr-defined]
    # The internal sink writes one record per emit; replay reconstructs them.
    return [type(e).__name__ for e in event_log.replay()]  # type: ignore[attr-defined]


# AC-4 — Empty store returns bare RagMiss + reason event, never calls classifier.


@pytest.mark.asyncio
async def test_ac4_empty_store_returns_bare_rag_miss(tmp_path: Path) -> None:
    classifier_called = [False]

    def _never(candidates: Any) -> Any:
        classifier_called[0] = True
        return RagMiss()

    retriever, _, source_kinds, _, event_log = await _build_retriever(
        tmp_path,
        store_candidates=[],
        verifier_decision=True,
        classifier_pyfunc=_never,
    )
    outcome = await retriever.query(object(), object())
    assert isinstance(outcome, RagMiss)
    assert not classifier_called[0], "classifier must not be called on empty store"
    assert source_kinds == [], "fence must not be called on empty store"
    names = _emitted_event_types(event_log, tmp_path)
    # Must include exactly one RagMissEvent with the empty_store reason.
    assert "RagMissEvent" in names
    miss_events = [
        e
        for e in event_log.replay()
        if type(e).__name__ == "RagMissEvent"  # type: ignore[attr-defined]
    ]
    assert len(miss_events) == 1
    assert miss_events[0].reason == "empty_store"


# AC-5, AC-6, AC-7 — chain-orphan exclusion + all-orphan returns RagMiss.


@pytest.mark.asyncio
async def test_ac7_all_orphan_returns_bare_rag_miss(tmp_path: Path) -> None:
    classifier_called = [False]

    def _never(candidates: Any) -> Any:
        classifier_called[0] = True
        return RagMiss()

    orphans = [
        ScoredSolvedExample(
            record=make_solved_example(id_=f"orphan-{i}"),
            score=Similarity(0.9),
        )
        for i in range(3)
    ]
    retriever, _, source_kinds, _, event_log = await _build_retriever(
        tmp_path,
        store_candidates=orphans,
        verifier_decision=False,  # every record an orphan
        classifier_pyfunc=_never,
    )
    outcome = await retriever.query(object(), object())
    assert isinstance(outcome, RagMiss)
    assert not classifier_called[0]
    assert source_kinds == [], "no fence on all-orphan path"
    names = _emitted_event_types(event_log, tmp_path)
    # Three RagRecordChainOrphan + one RagMissEvent(reason="all_candidates_chain_orphan").
    assert names.count("RagRecordChainOrphan") == 3
    miss_events = [
        e
        for e in event_log.replay()
        if type(e).__name__ == "RagMissEvent"  # type: ignore[attr-defined]
    ]
    assert len(miss_events) == 1
    assert miss_events[0].reason == "all_candidates_chain_orphan"


# AC-8, AC-9 — fence is invoked once per surviving record with source_kind=rag_retrieved.


@pytest.mark.asyncio
async def test_ac9_fence_called_once_per_surviving_candidate(tmp_path: Path) -> None:
    survivors = [
        ScoredSolvedExample(
            record=make_solved_example(id_=f"ok-{i}"),
            score=Similarity(0.9),
        )
        for i in range(3)
    ]
    retriever, _, source_kinds, _, event_log = await _build_retriever(
        tmp_path,
        store_candidates=survivors,
        verifier_decision=True,
    )
    outcome = await retriever.query(object(), object())
    assert isinstance(outcome, RagHit)
    # Fence called once per surviving record with source_kind="rag_retrieved".
    assert source_kinds == ["rag_retrieved", "rag_retrieved", "rag_retrieved"]


# AC-13 — RagMiss stays bare (no `reason` field on the model).


def test_ac13_rag_miss_is_bare() -> None:
    """RagMiss has no `reason` field — miss causes live in RagMissEvent."""
    RagMiss()  # constructs successfully without a `reason` keyword
    # Pydantic v2: ``model_fields`` lists declared fields; only ``kind`` is present.
    fields = set(RagMiss.model_fields.keys())
    assert fields == {"kind"}, f"RagMiss must stay bare (only `kind` field). Found: {fields}"
    # And constructing with a `reason` keyword is rejected (extra="forbid").
    with pytest.raises(Exception):  # noqa: B017 — ValidationError from pydantic
        RagMiss(reason="empty_store")  # type: ignore[call-arg]


# AC-17 — model_digest_filter excludes records; all-excluded returns RagMiss.


@pytest.mark.asyncio
async def test_ac17_all_model_mismatch_returns_bare_rag_miss(tmp_path: Path) -> None:
    classifier_called = [False]

    def _never(candidates: Any) -> Any:
        classifier_called[0] = True
        return RagMiss()

    candidates = [
        ScoredSolvedExample(
            record=make_solved_example(id_=f"mm-{i}"),
            score=Similarity(0.9),
        )
        for i in range(2)
    ]

    def _filter_excludes_all(
        verified: Any,
    ) -> Any:
        return ([], len(verified))

    retriever, _, source_kinds, _, event_log = await _build_retriever(
        tmp_path,
        store_candidates=candidates,
        verifier_decision=True,
        classifier_pyfunc=_never,
        model_digest_filter=_filter_excludes_all,
    )
    outcome = await retriever.query(object(), object())
    assert isinstance(outcome, RagMiss)
    assert not classifier_called[0]
    assert source_kinds == []
    names = _emitted_event_types(event_log, tmp_path)
    assert "RagRecordModelMismatch" in names
    miss_events = [
        e
        for e in event_log.replay()
        if type(e).__name__ == "RagMissEvent"  # type: ignore[attr-defined]
    ]
    assert len(miss_events) == 1
    assert miss_events[0].reason == "all_candidates_model_mismatch"


# Hit-path: classifier returns RagHit → RagHitEvent + RagCandidateSelectedEvent emitted.


@pytest.mark.asyncio
async def test_hit_path_emits_outcome_and_selected_events(tmp_path: Path) -> None:
    survivor = ScoredSolvedExample(
        record=make_solved_example(id_="hit-001"),
        score=Similarity(0.95),
    )

    def _hit(candidates: Any) -> Any:
        cand: FencedRetrievalCandidate = candidates[0]
        return RagHit(few_shot=cand.record, score=Similarity(cand.score))

    retriever, _, _, _, event_log = await _build_retriever(
        tmp_path,
        store_candidates=[survivor],
        verifier_decision=True,
        classifier_pyfunc=_hit,
    )
    outcome = await retriever.query(object(), object())
    assert isinstance(outcome, RagHit)
    names = _emitted_event_types(event_log, tmp_path)
    assert "RagHitEvent" in names
    assert "RagCandidateSelectedEvent" in names


# Degraded-path: classifier returns RagDegraded → RagDegradedEvent + RagCandidateSelectedEvent.


@pytest.mark.asyncio
async def test_degraded_path_emits_outcome_and_selected_events(tmp_path: Path) -> None:
    survivor = ScoredSolvedExample(
        record=make_solved_example(id_="degraded-001"),
        score=Similarity(0.72),
    )

    def _degraded(candidates: Any) -> Any:
        cand: FencedRetrievalCandidate = candidates[0]
        return RagDegraded(near_match=cand.record, score=Similarity(cand.score))

    retriever, _, _, _, event_log = await _build_retriever(
        tmp_path,
        store_candidates=[survivor],
        verifier_decision=True,
        classifier_pyfunc=_degraded,
    )
    outcome = await retriever.query(object(), object())
    assert isinstance(outcome, RagDegraded)
    names = _emitted_event_types(event_log, tmp_path)
    assert "RagDegradedEvent" in names
    assert "RagCandidateSelectedEvent" in names
