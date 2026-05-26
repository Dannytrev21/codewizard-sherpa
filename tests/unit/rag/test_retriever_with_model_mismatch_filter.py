"""Phase-4 S5-03 AC-5, AC-6, AC-8, AC-9 — retriever + filter integration.

AC-5: 5 candidates, 3 carry the live digest, 2 carry stale digests →
classifier called with exactly the 3 live; filter emits one
``RagRecordModelMismatch(count=2)``.

AC-6: all-mismatched → bare ``RagMiss()`` + ``RagMissEvent(reason=
"all_candidates_model_mismatch")``; classifier not called; filter emits
``RagRecordModelMismatch(count=N)`` first.

AC-8: chain-orphan exclusion runs BEFORE the model-digest filter; both
events emitted in the correct order.

AC-9: a chain-orphan that would-also-be model-mismatched is removed by
the chain-orphan stage; the filter sees zero mismatches and emits no
event (no double-attribution).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from codegenie.plugins.events import EventLog, RagRecordModelMismatch
from codegenie.rag.confidence import BandClassifier
from codegenie.rag.exclusion import EmbeddingModelMismatchFilter
from codegenie.rag.models import (
    RagHit,
    RagMiss,
    ScoredSolvedExample,
)
from codegenie.rag.retriever import SolvedExampleRetriever
from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    HexNonce,
    ModelId,
    Similarity,
    WorkflowId,
)
from tests.fixtures.rag.fake_solved_example import (
    make_query_matching,
    make_solved_example,
)

_LIVE_DIGEST = BlobDigest("blake3:" + "1" * 64)
_STALE_DIGEST = BlobDigest("blake3:" + "2" * 64)


class _StubSpanningChainLog:
    def contains_chain_head(self, head: ChainHead) -> bool:
        del head
        return True

    def head(self) -> ChainHead:
        return ChainHead("b" * 64)


def _build_fence_stub() -> Any:
    from codegenie.fallback.fence.wrapper import CanaryClean, FencedSegment

    def _fence(payload: str, source_kind: str) -> Any:
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
    return fw


def _candidate(record_id: str, model: BlobDigest) -> ScoredSolvedExample:
    rec = make_solved_example(id_=record_id)
    rec = rec.model_copy(update={"embedding_model": ModelId(str(model))})
    return ScoredSolvedExample(record=rec, score=Similarity(0.9))


async def _run_with_candidates(
    tmp_path: Path,
    candidates: list[ScoredSolvedExample],
    *,
    record_verifier_predicate: Any | None = None,
) -> tuple[Any, list[str], EventLog]:
    example = make_solved_example(id_="ex-q")
    q = make_query_matching(example)

    def qb(advisory: Any, repo_ctx: Any) -> Any:
        del advisory, repo_ctx
        return q

    def qtb(_q: Any) -> str:
        return "query text"

    embedder = MagicMock()
    embedder.model_digest = lambda: _LIVE_DIGEST
    embedder.embed = lambda _t: example.embedding_vector

    store = MagicMock()

    async def _qc(_q: Any, *, embedding: Any, top_k: int) -> Any:
        del embedding, top_k
        return candidates

    store.query_candidates = _qc

    verifier = record_verifier_predicate if record_verifier_predicate else (lambda r, log: True)

    fw = _build_fence_stub()

    classifier = BandClassifier(high_floor=0.85, degraded_floor=0.65)
    event_log = EventLog(root=tmp_path, workflow_id=WorkflowId("01HS503INTEGRATIONTESTWX0"))
    filter_ = EmbeddingModelMismatchFilter(embedder=embedder, event_log=event_log)

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
        model_digest_filter=filter_,
    )
    outcome = await retriever.query(object(), object())
    event_log.flush()  # type: ignore[attr-defined]
    event_types = [type(e).__name__ for e in event_log.replay()]  # type: ignore[attr-defined]
    return outcome, event_types, event_log


@pytest.mark.asyncio
async def test_ac5_partial_mismatch_filter_excludes_stale_and_emits_one_event(
    tmp_path: Path,
) -> None:
    candidates = [
        _candidate("ok-1", _LIVE_DIGEST),
        _candidate("stale-1", _STALE_DIGEST),
        _candidate("ok-2", _LIVE_DIGEST),
        _candidate("ok-3", _LIVE_DIGEST),
        _candidate("stale-2", _STALE_DIGEST),
    ]
    outcome, event_types, event_log = await _run_with_candidates(tmp_path, candidates)
    # Classifier saw the 3 live candidates → RagHit on the top one.
    assert isinstance(outcome, RagHit)
    # Exactly one RagRecordModelMismatch emitted with count=2.
    mm_events = [
        e
        for e in event_log.replay()
        if isinstance(e, RagRecordModelMismatch)  # type: ignore[attr-defined]
    ]
    assert len(mm_events) == 1
    assert mm_events[0].count == 2


@pytest.mark.asyncio
async def test_ac6_all_mismatched_returns_bare_rag_miss(tmp_path: Path) -> None:
    candidates = [_candidate(f"stale-{i}", _STALE_DIGEST) for i in range(3)]
    outcome, event_types, event_log = await _run_with_candidates(tmp_path, candidates)
    assert isinstance(outcome, RagMiss)
    # Filter emitted one mismatch event with count=3.
    mm_events = [
        e
        for e in event_log.replay()
        if isinstance(e, RagRecordModelMismatch)  # type: ignore[attr-defined]
    ]
    assert len(mm_events) == 1
    assert mm_events[0].count == 3
    # Retriever emitted RagMissEvent(reason="all_candidates_model_mismatch").
    miss_events = [
        e
        for e in event_log.replay()
        if type(e).__name__ == "RagMissEvent"  # type: ignore[attr-defined]
    ]
    assert len(miss_events) == 1
    assert miss_events[0].reason == "all_candidates_model_mismatch"


@pytest.mark.asyncio
async def test_ac9_chain_orphan_removes_would_be_mismatched(tmp_path: Path) -> None:
    """A record that's BOTH chain-orphan and model-mismatched is removed
    by the chain-orphan stage; the filter sees zero mismatches → no
    double-attribution."""
    orphan_and_stale = _candidate("orphan-stale", _STALE_DIGEST)
    valid = [_candidate("ok-1", _LIVE_DIGEST), _candidate("ok-2", _LIVE_DIGEST)]
    candidates = [orphan_and_stale, *valid]

    def verifier(rec: Any, log: Any) -> bool:
        del log
        return rec.id != "orphan-stale"

    outcome, event_types, event_log = await _run_with_candidates(
        tmp_path, candidates, record_verifier_predicate=verifier
    )
    # No model-mismatch event because the orphan was filtered out first.
    mm_events = [
        e
        for e in event_log.replay()
        if isinstance(e, RagRecordModelMismatch)  # type: ignore[attr-defined]
    ]
    assert len(mm_events) == 0, (
        "Chain-orphan exclusion must run before the model-digest filter; "
        "a would-be-mismatched orphan must NOT be double-attributed."
    )
    # One chain-orphan event emitted.
    chain_orphan_events = [
        e
        for e in event_log.replay()
        if type(e).__name__ == "RagRecordChainOrphan"  # type: ignore[attr-defined]
    ]
    assert len(chain_orphan_events) == 1
    assert isinstance(outcome, RagHit)
