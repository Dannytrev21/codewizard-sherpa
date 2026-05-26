"""Phase-4 S5-02 AC-14 — end-to-end integration with S5-01's retriever.

The :class:`BandClassifier` plugs into :class:`SolvedExampleRetriever`
via the constructor-injected ``confidence_classifier``. Three input
scores (0.90 / 0.75 / 0.40) yield ``RagHit`` / ``RagDegraded`` /
``RagMiss`` respectively. The retriever's reason-bearing
``RagMissEvent(reason="top1_below_floor")`` is emitted only on the
0.40 case.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from codegenie.plugins.events import EventLog
from codegenie.rag.confidence import BandClassifier
from codegenie.rag.models import (
    RagDegraded,
    RagHit,
    RagMiss,
    ScoredSolvedExample,
)
from codegenie.rag.retriever import SolvedExampleRetriever
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
    def __init__(self) -> None:
        self._head = _DEFAULT_SPAN_HEAD

    def contains_chain_head(self, head: ChainHead) -> bool:
        del head
        return True

    def head(self) -> ChainHead:
        return self._head


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


async def _run_with_score(tmp_path: Path, score: float) -> tuple[Any, list[str]]:
    example = make_solved_example(id_=f"ex-score-{int(score * 100):02d}")
    q = make_query_matching(example)

    def qb(advisory: Any, repo_ctx: Any) -> Any:
        del advisory, repo_ctx
        return q

    def qtb(_q: Any) -> str:
        return "query text"

    embedder = MagicMock()
    embedder.embed = lambda _t: example.embedding_vector

    store = MagicMock()

    async def _qc(_q: Any, *, embedding: Any, top_k: int) -> Any:
        del embedding, top_k
        return [ScoredSolvedExample(record=example, score=Similarity(score))]

    store.query_candidates = _qc

    def _verify(_r: Any, _log: Any) -> bool:
        return True

    fw = _build_fence_stub()

    classifier = BandClassifier(high_floor=0.85, degraded_floor=0.65)
    event_log = EventLog(
        root=tmp_path,
        workflow_id=WorkflowId("01HRETRIEVER0BANDCLASS0WX"),
    )
    retriever = SolvedExampleRetriever(
        store=store,
        embedder=embedder,
        spanning_log=_StubSpanningChainLog(),
        record_verifier=_verify,
        fence_wrapper=fw,
        query_builder=qb,
        query_text_builder=qtb,
        confidence_classifier=classifier,
        event_log=event_log,
    )
    outcome = await retriever.query(object(), object())
    event_log.flush()  # type: ignore[attr-defined]
    event_types = [type(e).__name__ for e in event_log.replay()]  # type: ignore[attr-defined]
    return outcome, event_types


@pytest.mark.asyncio
async def test_ac14_high_score_yields_rag_hit(tmp_path: Path) -> None:
    outcome, _ = await _run_with_score(tmp_path / "hit", 0.90)
    assert isinstance(outcome, RagHit)
    assert outcome.score == 0.90


@pytest.mark.asyncio
async def test_ac14_medium_score_yields_rag_degraded(tmp_path: Path) -> None:
    outcome, _ = await _run_with_score(tmp_path / "deg", 0.75)
    assert isinstance(outcome, RagDegraded)
    assert outcome.score == 0.75


@pytest.mark.asyncio
async def test_ac14_low_score_yields_bare_rag_miss_with_top1_below_floor_event(
    tmp_path: Path,
) -> None:
    outcome, event_types = await _run_with_score(tmp_path / "miss", 0.40)
    assert isinstance(outcome, RagMiss)
    # The retriever's classifier-result arm emits RagMissEvent(reason="top1_below_floor").
    assert "RagMissEvent" in event_types
    # No selected event for a miss.
    assert "RagCandidateSelectedEvent" not in event_types
