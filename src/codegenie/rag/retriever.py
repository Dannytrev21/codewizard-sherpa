"""Phase-4 S5-01 — ``SolvedExampleRetriever.query`` composition.

The read-side RAG composition layer. Calls collaborators in this exact
order (every step emits a workflow-internal audit event):

1. ``query_builder(advisory, repo_ctx) -> Query`` (injected callable).
2. ``query_text_builder(q) -> str`` (injected callable; canonical
   embedding-text rendering — never f-strings or string concatenation
   in this module).
3. ``embedder.embed(text) -> EmbeddingVector`` (S4-01).
4. ``store.query_candidates(q, *, embedding, top_k) ->
   Sequence[ScoredSolvedExample]`` (S4-03 candidate-read amendment).
5. **Chain-verify** every candidate via
   ``record_verifier(record, spanning_log) -> bool`` (S4-05). Excluded
   records emit ``RagRecordChainOrphan``.
6. **Model-mismatch filter** via the optional
   ``model_digest_filter`` hook (S5-03 supplies the concrete; default
   ``None`` = passthrough). Exclusions emit ``RagRecordModelMismatch``.
7. **Fence** every surviving record's canonical YAML bytes as
   ``source_kind="rag_retrieved"`` (ADR-04-0013 trust boundary). The
   classifier sees ``Sequence[FencedRetrievalCandidate]``, never raw
   record content.
8. ``confidence_classifier.classify(candidates) -> RetrievalOutcome``
   (S5-02 supplies the concrete ``BandClassifier``; this module ships
   only the Protocol). Emits one of
   ``RagHitEvent`` / ``RagDegradedEvent`` / ``RagMissEvent``, plus
   ``RagCandidateSelectedEvent`` on hit/degraded for S6-01's
   prompt-assembly handoff.

Discipline:

* All collaborators are Protocols or injected callables — no concrete
  imports of ``chromadb``, ``fastembed``, or ``onnxruntime``.
* The :class:`SolvedExampleRetriever` is a frozen dataclass; no
  mutable state across ``query()`` invocations.
* Return shape is the closed ``RagHit | RagDegraded | RagMiss`` union
  via the band classifier; ``RagMiss`` stays **bare** (miss causes
  live in :class:`RagMissEvent.reason`, not in a widening of the
  variant).
* ADR-04-0011 — retry-bypass discipline lives at ``FallbackTier``.
  ``query()`` has no ``prior_attempts`` parameter.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, assert_never, runtime_checkable

from codegenie.fallback.fence.wrapper import FencedSegment, FenceWrapper
from codegenie.hashing import content_hash_bytes
from codegenie.plugins.events import (
    EventLog,
    QueryBuiltEvent,
    QueryRenderedEvent,
    RagCandidateSelectedEvent,
    RagDegradedEvent,
    RagHitEvent,
    RagMissEvent,
    RagRecordChainOrphan,
    RecordsChainVerifiedEvent,
    RecordsEmbeddedEvent,
    RecordsFencedEvent,
    StoreQueriedEvent,
)
from codegenie.rag.embedder import Embedder
from codegenie.rag.models import (
    Query,
    RagDegraded,
    RagHit,
    RagMiss,
    RetrievalOutcome,
    ScoredSolvedExample,
    SolvedExample,
)
from codegenie.rag.provenance import SpanningChainLog
from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    EventId,
    SolvedExampleId,
)

__all__ = [
    "CandidateSolvedExampleStore",
    "ConfidenceClassifier",
    "FencedRetrievalCandidate",
    "SolvedExampleRetriever",
]


# ---------------------------------------------------------------------------
# Read-side Protocol surfaces (Open/Closed at the file boundary)
# ---------------------------------------------------------------------------


@runtime_checkable
class CandidateSolvedExampleStore(Protocol):
    """Narrow read-side Protocol the retriever depends on.

    A pure subset of :class:`SolvedExampleStore` exposing only the
    candidate-returning read surface. The retriever does NOT need
    ``add`` / ``digest`` / ``close`` / ``query`` — those are
    write/projection methods that live behind the wider Protocol.
    """

    async def query_candidates(
        self,
        q: Query,
        *,
        embedding: Sequence[float],
        top_k: int = 5,
    ) -> Sequence[ScoredSolvedExample]: ...


@runtime_checkable
class ConfidenceClassifier(Protocol):
    """Band-classifier seam (S5-02 supplies the concrete ``BandClassifier``).

    Single method by design: a classifier takes the *fenced* candidates
    (so injection bytes have already passed through ``FenceWrapper``
    by the time the classifier sees them — ADR-04-0013 trust boundary)
    and returns the closed :data:`RetrievalOutcome` union. Pre-fencing
    + pre-filtering is the retriever's responsibility, never the
    classifier's.
    """

    def classify(self, candidates: Sequence[FencedRetrievalCandidate]) -> RetrievalOutcome: ...


# ---------------------------------------------------------------------------
# Fenced-candidate DTO (S5-01 AC-1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FencedRetrievalCandidate:
    """A fenced, scored solved-example candidate ready for classification.

    Carries both ``fenced`` (the ``FencedSegment`` whose ``.content``
    contains escaped-injection bytes) and ``record`` (the original
    :class:`SolvedExample` whose YAML was fenced). The classifier
    consumes ``fenced.content`` for prompt-assembly bytes and ``record``
    for the ``RagHit.few_shot`` / ``RagDegraded.near_match`` payload.

    ``score`` is the raw cosine similarity from the store. The
    classifier folds ``(score → band)`` per ADR-04-0008.
    """

    fenced: FencedSegment
    record: SolvedExample
    score: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_event_id() -> EventId:
    """Mint a deterministic-shape ``EventId`` for one retriever emission."""
    return EventId("01HRRG" + uuid.uuid4().hex[:20].upper())


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _canonical_yaml_text(record: SolvedExample) -> str:
    """Return the canonical-YAML representation of ``record`` for fencing.

    The :class:`FenceWrapper` accepts ``str``; the canonical YAML bytes
    are produced via the same ``model_dump_json`` shape that drives
    the store's chain head. UTF-8 round-trip is loss-less for the
    JSON-serialisable record fields.
    """
    return record.model_dump_json()


def _digest_fenced(seg: FencedSegment) -> BlobDigest:
    """Audit-anchor digest for a fenced segment."""
    return BlobDigest(content_hash_bytes(seg.content.encode("utf-8")))


# ---------------------------------------------------------------------------
# SolvedExampleRetriever
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SolvedExampleRetriever:
    """The read-side RAG composition: build → embed → store → verify →
    filter → fence → classify, with a typed audit event per step.

    Every collaborator is injected via the keyword-only constructor.
    No concrete imports of ``chromadb``, ``fastembed``, or ``onnxruntime``
    appear in this module (AST-walk test enforces).
    """

    store: CandidateSolvedExampleStore
    embedder: Embedder
    spanning_log: SpanningChainLog
    record_verifier: Callable[[SolvedExample, SpanningChainLog], bool]
    fence_wrapper: FenceWrapper
    query_builder: Callable[..., Query]
    query_text_builder: Callable[[Query], str]
    confidence_classifier: ConfidenceClassifier
    event_log: EventLog
    model_digest_filter: (
        Callable[
            [Sequence[ScoredSolvedExample]],
            tuple[list[ScoredSolvedExample], int],
        ]
        | None
    ) = field(default=None)
    top_k: int = 5

    async def query(self, advisory: object, repo_ctx: object) -> RetrievalOutcome:
        """Run the read-side dispatch and return a typed :data:`RetrievalOutcome`.

        ``advisory`` and ``repo_ctx`` are typed-Erased at this seam (the
        concrete types are the plugin-owned :class:`CveAdvisory` /
        :class:`RepoContext` from S7-02; this Protocol stays
        constraint-light so the kernel does not depend on plugin types).
        """
        wf_id = self.event_log.workflow_id

        # 1. build_query
        q = self.query_builder(advisory, repo_ctx)
        self.event_log.emit_internal(
            QueryBuiltEvent(
                event_id=_new_event_id(),
                workflow_id=wf_id,
                timestamp=_now_utc(),
            )
        )

        # 2. render_query_text
        query_text = self.query_text_builder(q)
        self.event_log.emit_internal(
            QueryRenderedEvent(
                event_id=_new_event_id(),
                workflow_id=wf_id,
                timestamp=_now_utc(),
            )
        )

        # 3. embed
        embedding = self.embedder.embed(query_text)
        self.event_log.emit_internal(
            RecordsEmbeddedEvent(
                event_id=_new_event_id(),
                workflow_id=wf_id,
                timestamp=_now_utc(),
            )
        )

        # 4. store_query_candidates
        raw = await self.store.query_candidates(q, embedding=embedding, top_k=self.top_k)
        self.event_log.emit_internal(
            StoreQueriedEvent(
                event_id=_new_event_id(),
                workflow_id=wf_id,
                timestamp=_now_utc(),
                count=len(raw),
            )
        )

        if not raw:
            self.event_log.emit_internal(
                RagMissEvent(
                    event_id=_new_event_id(),
                    workflow_id=wf_id,
                    timestamp=_now_utc(),
                    reason="empty_store",
                )
            )
            return RagMiss()

        # 5. per_record_chain_verify
        verified = self._chain_verify(raw, wf_id)
        self.event_log.emit_internal(
            RecordsChainVerifiedEvent(
                event_id=_new_event_id(),
                workflow_id=wf_id,
                timestamp=_now_utc(),
                surviving_count=len(verified),
                excluded_count=len(raw) - len(verified),
            )
        )
        if not verified:
            self.event_log.emit_internal(
                RagMissEvent(
                    event_id=_new_event_id(),
                    workflow_id=wf_id,
                    timestamp=_now_utc(),
                    reason="all_candidates_chain_orphan",
                )
            )
            return RagMiss()

        # 6. model_digest_filter (optional — S5-03 supplies the concrete).
        # The filter owns its own ``RagRecordModelMismatch`` event emission
        # (it knows the model digests; the retriever does not).
        if self.model_digest_filter is not None:
            verified, _excluded = self.model_digest_filter(verified)
            if not verified:
                self.event_log.emit_internal(
                    RagMissEvent(
                        event_id=_new_event_id(),
                        workflow_id=wf_id,
                        timestamp=_now_utc(),
                        reason="all_candidates_model_mismatch",
                    )
                )
                return RagMiss()

        # 7. fence_record_content (TRUST BOUNDARY — ADR-04-0013)
        candidates = self._fence_candidates(verified)
        self.event_log.emit_internal(
            RecordsFencedEvent(
                event_id=_new_event_id(),
                workflow_id=wf_id,
                timestamp=_now_utc(),
                count=len(candidates),
            )
        )

        # 8. classify
        outcome = self.confidence_classifier.classify(candidates)
        self._emit_outcome_events(outcome, candidates, wf_id)
        return outcome

    # ---- helpers (composition over inheritance) --------------------------

    def _chain_verify(
        self, raw: Sequence[ScoredSolvedExample], wf_id: object
    ) -> list[ScoredSolvedExample]:
        """Return the candidates passing
        :func:`codegenie.rag.provenance.verify`; emit one
        :class:`RagRecordChainOrphan` per excluded record."""
        verified: list[ScoredSolvedExample] = []
        span_head: ChainHead = self.spanning_log.head()
        for cand in raw:
            if self.record_verifier(cand.record, self.spanning_log):
                verified.append(cand)
                continue
            self.event_log.emit_internal(
                RagRecordChainOrphan(
                    event_id=_new_event_id(),
                    workflow_id=self.event_log.workflow_id,
                    timestamp=_now_utc(),
                    record_id=cand.record.id,
                    record_event_chain_head=cand.record.provenance.event_chain_head,
                    spanning_log_head=span_head,
                )
            )
        return verified

    def _fence_candidates(
        self, verified: Sequence[ScoredSolvedExample]
    ) -> list[FencedRetrievalCandidate]:
        """Fence every surviving record's canonical YAML as
        ``source_kind="rag_retrieved"``."""
        out: list[FencedRetrievalCandidate] = []
        for cand in verified:
            fenced = self.fence_wrapper.fence(
                _canonical_yaml_text(cand.record),
                source_kind="rag_retrieved",
            )
            out.append(
                FencedRetrievalCandidate(
                    fenced=fenced,
                    record=cand.record,
                    score=cand.score,
                )
            )
        return out

    def _emit_outcome_events(
        self,
        outcome: RetrievalOutcome,
        candidates: Sequence[FencedRetrievalCandidate],
        wf_id: object,
    ) -> None:
        """Emit outcome + selected-candidate events.

        Exhaustive ``match`` over the closed three-variant union; a
        deliberate-failure test plants a synthetic fourth variant that
        the ``assert_never`` arm rejects.
        """
        match outcome:
            case RagHit(few_shot=record, score=_):
                self.event_log.emit_internal(
                    RagHitEvent(
                        event_id=_new_event_id(),
                        workflow_id=self.event_log.workflow_id,
                        timestamp=_now_utc(),
                        record_id=record.id,
                    )
                )
                self._emit_selected(record.id, candidates)
            case RagDegraded(near_match=record, score=_):
                self.event_log.emit_internal(
                    RagDegradedEvent(
                        event_id=_new_event_id(),
                        workflow_id=self.event_log.workflow_id,
                        timestamp=_now_utc(),
                        record_id=record.id,
                    )
                )
                self._emit_selected(record.id, candidates)
            case RagMiss():
                self.event_log.emit_internal(
                    RagMissEvent(
                        event_id=_new_event_id(),
                        workflow_id=self.event_log.workflow_id,
                        timestamp=_now_utc(),
                        reason="top1_below_floor",
                    )
                )
            case _ as unreachable:
                assert_never(unreachable)

    def _emit_selected(
        self,
        record_id: SolvedExampleId,
        candidates: Sequence[FencedRetrievalCandidate],
    ) -> None:
        """Emit :class:`RagCandidateSelectedEvent` for the chosen candidate
        — the audit anchor S6-01's prompt-assembly handoff reads."""
        for cand in candidates:
            if cand.record.id == record_id:
                self.event_log.emit_internal(
                    RagCandidateSelectedEvent(
                        event_id=_new_event_id(),
                        workflow_id=self.event_log.workflow_id,
                        timestamp=_now_utc(),
                        record_id=record_id,
                        fenced_digest=_digest_fenced(cand.fenced),
                    )
                )
                return


# Note on Protocol relationship: any adapter satisfying the full
# :class:`SolvedExampleStore` Protocol also structurally satisfies the
# narrow :class:`CandidateSolvedExampleStore` (it has the same
# ``query_candidates`` shape). The relationship is enforced at runtime
# by structural typing, not asserted via a static `type[]` annotation
# (mypy rejects abstract-Protocol assignments).
