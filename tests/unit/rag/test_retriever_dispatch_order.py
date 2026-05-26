"""Phase-4 S5-01 — :class:`SolvedExampleRetriever.query` dispatch-order test.

AC-2: the retriever drives its collaborators in this exact named order:
``(build_query, render_query_text, embed, store_query_candidates,
chain_verify, fence, classify)``. Out-of-order dispatch would mean
unfenced bytes pass the trust boundary (ADR-04-0013) or chain-orphan
records reach the classifier (poisoning vector edge case #14).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from codegenie.plugins.events import EventLog
from codegenie.rag.models import RagHit, ScoredSolvedExample
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
    """Minimal :class:`SpanningChainLog` Protocol satisfier for tests."""

    def __init__(self, head: ChainHead | None = None) -> None:
        self._head = head if head is not None else _DEFAULT_SPAN_HEAD

    def contains_chain_head(self, head: ChainHead) -> bool:
        del head
        return True

    def head(self) -> ChainHead:
        return self._head


class _StubFenceWrapper:
    """Minimal :class:`FenceWrapper` shape (call_count + recorded source_kind)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def fence(self, payload: str, source_kind: str) -> Any:
        from codegenie.fallback.fence.wrapper import CanaryClean, FencedSegment

        self.calls.append((payload[:32], source_kind))
        content = f"<UNTRUSTED_INPUT id=01H>{payload}</UNTRUSTED_INPUT id=01H>"
        return FencedSegment(
            nonce=HexNonce("0" * 16),
            source_kind=source_kind,  # type: ignore[arg-type]
            content=content,
            truncated=False,
            original_byte_length=len(payload.encode("utf-8")),
            canary=CanaryClean(),
        )


@pytest.mark.asyncio
async def test_ac2_retriever_calls_collaborators_in_named_order(tmp_path: Path) -> None:
    """SolvedExampleRetriever.query MUST drive collaborators in the named
    sequence. Out-of-order dispatch would mean unfenced bytes pass the
    classifier (trust-boundary breach ADR-04-0013) or chain-orphan records
    reach prompt assembly (poisoning vector edge case #14).
    """
    calls: list[str] = []
    example = make_solved_example(id_="ex-001")
    q = make_query_matching(example)

    def qb(advisory: Any, repo_ctx: Any) -> Any:
        del advisory, repo_ctx
        calls.append("build_query")
        return q

    def qtb(_q: Any) -> str:
        calls.append("render_query_text")
        return "query text"

    embedder = MagicMock()

    def _embed(text: str) -> Any:
        del text
        calls.append("embed")
        return example.embedding_vector

    embedder.embed = _embed

    store = MagicMock()
    candidate = ScoredSolvedExample(record=example, score=Similarity(0.9))

    async def _qc(_q: Any, *, embedding: Any, top_k: int) -> Any:
        del embedding, top_k
        calls.append("store_query_candidates")
        return [candidate]

    store.query_candidates = _qc

    def _verify(_r: Any, _log: Any) -> bool:
        calls.append("chain_verify")
        return True

    fence_wrapper = _StubFenceWrapper()

    def _fence(payload: str, source_kind: str) -> Any:
        calls.append("fence")
        return fence_wrapper.fence(payload, source_kind)

    fw = MagicMock()
    fw.fence = _fence

    classifier = MagicMock()

    def _classify(candidates: Any) -> Any:
        calls.append("classify")
        cand: FencedRetrievalCandidate = candidates[0]
        return RagHit(few_shot=cand.record, score=Similarity(cand.score))

    classifier.classify = _classify

    event_log = EventLog(root=tmp_path, workflow_id=WorkflowId("01HRETRIEVERAC02WORKFLW01"))
    try:
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
        assert isinstance(outcome, RagHit)
    finally:
        event_log.flush()  # type: ignore[attr-defined]

    assert calls == [
        "build_query",
        "render_query_text",
        "embed",
        "store_query_candidates",
        "chain_verify",
        "fence",
        "classify",
    ]
