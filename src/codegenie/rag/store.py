"""Phase-4 S4-03 — ``SolvedExampleStore`` Protocol + ``ChromaPersistentStore``.

The RAG substrate's read/write seam. ADR-0016 commits Phase 4 to **one**
Protocol (:class:`SolvedExampleStore`) with **one** in-tree adapter
(:class:`ChromaPersistentStore` over ``chromadb.PersistentClient`` in
embedded mode); a Phase-11 pgvector adapter swap happens behind the same
Protocol. The load-bearing constraints — captured in arch Gap 3, edge
case #5, and ADR-0016 §Decision:

1. **single-writer constraint.** ChromaDB's HNSW writer is single-
   threaded; concurrent ingest from 24 portfolio workers (Phase 11)
   needs *declared* serialization, not silent racing. We enforce inside
   :class:`ChromaPersistentStore` via a process-local
   ``asyncio.Lock``; the docstring of :class:`SolvedExampleStore`
   carries the constraint forward to any future adapter (e.g. Phase-11
   pgvector) so its conformance bar is the same.

2. **30 s lock-contention contract.** ``add()`` ``await``s the lock
   with a ``_ADD_LOCK_TIMEOUT_SECONDS`` (default ``30.0``) timeout; on
   timeout raises :class:`~codegenie.rag.errors.StoreWriteContention`
   carrying the harvester's :class:`WorkflowId`. S4-08 lands the full
   ``asyncio.gather`` two-coroutine pin; this story ships the shorter
   integration test that pins only the timeout itself.

3. **Per-``(task_class, language, build_system)`` collection partition.**
   Smaller HNSW indexes; O(1) collection lookup; future task classes
   (Phase-7 distroless, Phase-15 recipe authoring) land in their own
   collections without touching existing ones.

4. **``add()`` is capability-gated.** :class:`SolvedExampleWriteCapability`
   is required at the type level. The marker is *declared* here; S4-06
   ships the ``_phase4_local_capability_mint`` factory. Tests in this
   story construct it directly inside the test module (boundary lift
   acknowledged inline).

**What this story does NOT ship.** The YAML-canonical write + manifest
layer is S4-04; ``add()`` here writes chromadb only and will be
*extended* (composed under, not edited) by S4-04 to take the
YAML-canonical path. The ``provenance.event_chain_head`` chain-verify is
S4-05. The two-threshold band classifier is S5-02 — this module returns
:class:`RagHit` / :class:`RagMiss` only, never :class:`RagDegraded`.

**Vector boundary.** The store stores pre-computed ``embedding_vector``
values supplied by the caller and searches with a caller-supplied
``query_embedding``. It does not own an embedder; the retriever (S5-01)
does. The Protocol's public ``query`` therefore returns
:class:`RagMiss` until the retriever wires :meth:`_query_with_embedding`
— see :ref:`§Two read methods` in the body of this module.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, final, runtime_checkable

import blake3
import chromadb
import structlog
from chromadb.config import Settings

from codegenie.rag.errors import StoreClosed, StoreWriteContention
from codegenie.rag.models import Query, RagHit, RagMiss, RetrievalOutcome, SolvedExample
from codegenie.types.identifiers import (
    EmbeddingVector,
    Similarity,
    SolvedExampleId,
    StoreDigest,
    WorkflowId,
)

if TYPE_CHECKING:  # pragma: no cover — typing-only import
    from chromadb.api.models.Collection import Collection

_LOG = structlog.get_logger(__name__)

_ADD_LOCK_TIMEOUT_SECONDS: Final[float] = 30.0
"""Process-local single-writer timeout (ADR-0016 §Gap 3). Module-level
constant so AC-8's integration test can squeeze it via
``monkeypatch.setattr(...)`` without patching ``asyncio.wait_for``."""

_COLLECTION_NAME_SEPARATOR: Final[str] = "__"
"""Per-partition collection name separator. Underscores are safe; ``:``
or ``/`` may be rejected by chromadb (varies by version)."""

_HNSW_COSINE_METADATA: Final[dict[str, str]] = {"hnsw:space": "cosine"}
"""Pin chromadb's HNSW distance metric to cosine so
``similarity = 1.0 - distance`` lands in the ``Similarity`` range
``[-1.0, 1.0]`` mandated by :class:`~codegenie.rag.models.RagHit`."""

_CHROMA_SETTINGS: Final[Settings] = Settings(anonymized_telemetry=False)


# ---------------------------------------------------------------------------
# SolvedExampleWriteCapability — the marker S4-06 will mint
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class SolvedExampleWriteCapability:
    """Frozen marker required by :meth:`SolvedExampleStore.add`.

    S4-03 declares the type only; S4-06 ships
    ``_phase4_local_capability_mint`` as the sole public minting surface.
    Tests in this story construct it directly inside the test module
    (boundary lift acknowledged with an ``# AC-2-test-only-direct-
    construction`` inline comment near each construction site).
    """

    workflow_id: WorkflowId


# ---------------------------------------------------------------------------
# SolvedExampleStore Protocol — four members, single-writer constraint
# ---------------------------------------------------------------------------


@runtime_checkable
class SolvedExampleStore(Protocol):
    """RAG persistent-store seam. Four methods, exactly.

    The **single-writer constraint** (ADR-0016 §Decision) is part of the
    contract: any adapter implementing this Protocol MUST serialize
    concurrent :meth:`add` calls at the adapter level and raise
    :class:`~codegenie.rag.errors.StoreWriteContention` rather than block
    indefinitely. Phase-11's pgvector swap inherits the bar.

    The Phase-4 in-tree adapter is :class:`ChromaPersistentStore`. A
    Phase-11 pgvector adapter slots in behind this Protocol without
    touching call sites.

    The arch §Component 7 / final-design §7 illustrative snippet shows
    ``query`` / ``add`` as synchronous ``def``; the resolved contract is
    ``async def`` because the lock and the ``asyncio.to_thread`` wrap
    around the synchronous chromadb client both require an async caller.
    This deviation is acknowledged in the S4-03 story Notes §10 — do not
    "fix" it back to sync.
    """

    async def query(
        self,
        q: Query,
        *,
        top_k: int = 5,
        similarity_floor: float | None = None,
    ) -> RetrievalOutcome: ...

    async def add(
        self,
        example: SolvedExample,
        capability: SolvedExampleWriteCapability,
    ) -> SolvedExampleId: ...

    def digest(self) -> StoreDigest: ...

    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# ChromaPersistentStore — the in-tree adapter
# ---------------------------------------------------------------------------


def _collection_name(task_class: str, language: str, build_system: str) -> str:
    sep = _COLLECTION_NAME_SEPARATOR
    return f"{task_class}{sep}{language}{sep}{build_system}"


def _digest_record_ids(record_ids: list[SolvedExampleId]) -> StoreDigest:
    """Pure: roll BLAKE3 over the record-id list in given order.

    Order-sensitive on purpose (AC-6) — the S4-07 ``rag rebuild`` golden
    test rebuilds from S4-04's manifest in the same insertion order and
    asserts byte-identical digest. Sorting would hide insertion-order
    bugs; do not sort.

    The empty roll equals ``blake3(b"").hexdigest()`` (literal:
    ``af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262``).
    """
    h = blake3.blake3()
    for rid in record_ids:
        h.update(rid.encode("utf-8"))
    return StoreDigest(h.hexdigest())


class ChromaPersistentStore:
    """In-tree :class:`SolvedExampleStore` over
    ``chromadb.PersistentClient`` (embedded mode).

    Spike posture (S4-03 Implementation Outline §1, one-page throwaway):
    chromadb's collection ``add`` / ``query`` are synchronous CPython
    calls; we wrap each via ``await asyncio.to_thread(...)`` so the
    surrounding ``asyncio.Lock`` is meaningful. The lock itself is
    process-local — a second OS process opening the same on-disk client
    has its own lock; only S4-04's YAML-canonical layer makes
    cross-process correctness tractable.
    """

    __slots__ = ("_add_lock", "_client", "_collections", "_record_ids", "_root_dir")

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        chroma_path = root_dir / "chroma"
        chroma_path.mkdir(parents=True, exist_ok=True)
        self._client: chromadb.api.ClientAPI | None = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=_CHROMA_SETTINGS,
        )
        self._collections: dict[str, Collection] = {}
        self._add_lock = asyncio.Lock()
        self._record_ids: list[SolvedExampleId] = []
        self._load_existing_record_ids()

    # ---------------------------- private helpers ---------------------------

    def _check_open(self) -> None:
        if self._client is None:
            raise StoreClosed("ChromaPersistentStore has been closed")

    def _get_collection(self, task_class: str, language: str, build_system: str) -> Collection:
        """Resolve (lazily) the partition collection.

        Caches resolved collections on ``self._collections`` so a single
        client lookup is O(1) on the hot path.
        """
        assert self._client is not None  # _check_open is the caller's job
        name = _collection_name(task_class, language, build_system)
        cached = self._collections.get(name)
        if cached is not None:
            return cached
        collection = self._client.get_or_create_collection(
            name=name, metadata=_HNSW_COSINE_METADATA
        )
        self._collections[name] = collection
        return collection

    def _existing_collection(
        self, task_class: str, language: str, build_system: str
    ) -> Collection | None:
        """Return the partition collection if it already exists.

        Used by read paths so a never-populated partition returns
        :class:`RagMiss` rather than implicitly creating an empty
        collection (AC-5 — "no records ever added for that partition →
        :class:`RagMiss`").
        """
        assert self._client is not None
        name = _collection_name(task_class, language, build_system)
        cached = self._collections.get(name)
        if cached is not None:
            return cached
        try:
            collection = self._client.get_collection(name=name)
        except Exception:
            return None
        self._collections[name] = collection
        return collection

    def _load_existing_record_ids(self) -> None:
        """Populate ``_record_ids`` from any collections already on disk.

        **Insertion-order caveat (S4-03 AC-3 + Notes §11).** chromadb's
        ``collection.get()`` does not guarantee insertion order, and
        there is one collection per partition, so the order this method
        produces is best-effort within-process. Cross-process digest
        determinism arrives with S4-04's ``manifest.yaml`` (the
        canonical insertion-order source); do not pretend otherwise.
        """
        assert self._client is not None
        loaded: list[SolvedExampleId] = []
        try:
            collections = self._client.list_collections()
        except Exception:
            return
        for collection_handle in collections:
            try:
                collection = self._client.get_collection(name=collection_handle.name)
            except Exception:
                continue
            self._collections[collection_handle.name] = collection
            try:
                existing = collection.get(include=[])
            except Exception:
                continue
            ids = existing.get("ids") or []
            for rid in ids:
                loaded.append(SolvedExampleId(rid))
        self._record_ids = loaded

    # ---------------------------- write path --------------------------------

    async def add(
        self,
        example: SolvedExample,
        capability: SolvedExampleWriteCapability,
    ) -> SolvedExampleId:
        """Capability-gated single-writer ``add``.

        Acquires ``self._add_lock`` with ``_ADD_LOCK_TIMEOUT_SECONDS``;
        on timeout raises
        :class:`~codegenie.rag.errors.StoreWriteContention` carrying
        ``capability.workflow_id``. ``capability`` is a marker — the
        type-level gate is the load-bearing detail; its ``workflow_id``
        is *only* read on the timeout branch to make the failure event
        attributable.
        """
        self._check_open()
        acquired = False
        try:
            try:
                await asyncio.wait_for(
                    self._add_lock.acquire(),
                    timeout=_ADD_LOCK_TIMEOUT_SECONDS,
                )
            except TimeoutError as exc:
                _LOG.warning(
                    "store.add.timeout",
                    workflow_id=str(capability.workflow_id),
                )
                raise StoreWriteContention(workflow_id=capability.workflow_id) from exc
            acquired = True
            _LOG.debug("store.add.acquired", example_id=example.id)
            collection = self._get_collection(
                example.task_class, example.language, example.build_system
            )
            metadata = _metadata_from_example(example)
            vector: Sequence[float] = [float(x) for x in example.embedding_vector]
            embeddings: list[Sequence[float] | Sequence[int]] = [vector]
            await asyncio.to_thread(
                collection.add,
                ids=[example.id],
                embeddings=embeddings,
                metadatas=[metadata],
            )
            self._record_ids.append(SolvedExampleId(example.id))
            _LOG.debug("store.add.completed", example_id=example.id)
            return SolvedExampleId(example.id)
        finally:
            if acquired:
                self._add_lock.release()

    # ---------------------------- read paths --------------------------------

    async def query(
        self,
        q: Query,
        *,
        top_k: int = 5,
        similarity_floor: float | None = None,
    ) -> RetrievalOutcome:
        """Protocol-surface read path.

        Resolves the partition collection from ``q`` and returns
        :class:`RagMiss`. The Protocol carries no vector and this store
        ships no embedder; the real read path is
        :meth:`_query_with_embedding`, called by S5-01's retriever once
        it has embedded the query.
        """
        del top_k, similarity_floor  # honored by _query_with_embedding only
        self._check_open()
        _ = self._existing_collection(q.task_class, q.language, q.build_system)
        return RagMiss()

    async def _query_with_embedding(
        self,
        q: Query,
        query_embedding: EmbeddingVector,
        *,
        top_k: int = 5,
        similarity_floor: float | None = None,
    ) -> RetrievalOutcome:
        """In-house read path called by S5-01's retriever.

        Resolves the partition collection from ``q``; if it doesn't
        exist (no records ever added for that triple) returns
        :class:`RagMiss`. Otherwise runs chromadb's similarity search
        with the caller-supplied vector, takes the top result, and
        returns :class:`RagHit` when ``similarity_floor`` is satisfied
        (or unset). Never returns :class:`RagDegraded` — that's S5-02's
        job to layer on.
        """
        self._check_open()
        collection = self._existing_collection(q.task_class, q.language, q.build_system)
        if collection is None:
            return RagMiss()
        query_vector: Sequence[float] = [float(x) for x in query_embedding]
        query_embeddings: list[Sequence[float] | Sequence[int]] = [query_vector]
        result = await asyncio.to_thread(
            collection.query,
            query_embeddings=query_embeddings,
            n_results=top_k,
        )
        ids_pages = result.get("ids") or []
        distances_pages = result.get("distances") or []
        metadatas_pages = result.get("metadatas") or []
        if not ids_pages or not ids_pages[0]:
            return RagMiss()
        top_id = ids_pages[0][0]
        top_distance = distances_pages[0][0] if distances_pages and distances_pages[0] else None
        if top_distance is None:
            return RagMiss()
        top_score = max(-1.0, min(1.0, 1.0 - float(top_distance)))
        if similarity_floor is not None and top_score < similarity_floor:
            return RagMiss()
        metadata = metadatas_pages[0][0] if metadatas_pages and metadatas_pages[0] else None
        record = self._rehydrate_record_or_none(SolvedExampleId(top_id), metadata)
        if record is None:
            return RagMiss()
        return RagHit(few_shot=record, score=Similarity(top_score))

    @staticmethod
    def _rehydrate_record_or_none(
        record_id: SolvedExampleId,
        metadata: object | None,
    ) -> SolvedExample | None:
        """Try to reconstruct a :class:`SolvedExample` from chromadb's
        stored metadata. S4-03 stores the model's full JSON dump as the
        ``example_json`` metadata field (S4-04 will own the canonical
        YAML and feed records from there); if absent or unparseable we
        return ``None`` and the caller folds to :class:`RagMiss`.
        """
        if not isinstance(metadata, dict):
            return None
        payload = metadata.get("example_json")
        if not isinstance(payload, str):
            return None
        try:
            return SolvedExample.model_validate_json(payload)
        except Exception:
            return None

    # ---------------------------- projection --------------------------------

    def digest(self) -> StoreDigest:
        """BLAKE3-rolled digest over the record-id list (insertion order).

        Pure projection over in-memory state; safe after :meth:`close`
        (AC-7) and never raises :class:`StoreClosed`.

        **Within-process scope.** Cross-process (close/reopen)
        determinism is **deferred to S4-04**'s manifest.yaml — chromadb
        does not promise insertion order on ``get()`` and there is one
        collection per partition (Notes §11). Within a single live store
        the contract holds: two stores fed the same records in the same
        order produce identical digests; opposite order produces
        different digests; pinned by ``test_digest_is_insertion_order_sensitive``.
        """
        return _digest_record_ids(self._record_ids)

    def close(self) -> None:
        """Drop the chromadb client reference. Idempotent (AC-7).

        ``digest()`` continues to work after ``close()`` — it is a pure
        in-memory projection. ``add`` / ``query`` /
        ``_query_with_embedding`` raise :class:`StoreClosed`.
        """
        self._client = None
        self._collections.clear()


# ---------------------------------------------------------------------------
# Pure helpers — kept module-local
# ---------------------------------------------------------------------------


def _metadata_from_example(example: SolvedExample) -> dict[str, str | int | float | bool]:
    """Flat ``str | int | float | bool`` dict — chromadb metadata cannot
    nest. The full record is JSON-encoded under ``example_json`` so the
    read path can rehydrate; the partition triple + chain-anchor are
    surfaced as flat fields for future operator-side debugging.
    """
    return {
        "task_class": str(example.task_class),
        "language": str(example.language),
        "build_system": str(example.build_system),
        "embedding_model": str(example.embedding_model),
        "event_chain_head": str(example.provenance.event_chain_head),
        "example_json": example.model_dump_json(),
    }


__all__ = (
    "ChromaPersistentStore",
    "SolvedExampleStore",
    "SolvedExampleWriteCapability",
)
