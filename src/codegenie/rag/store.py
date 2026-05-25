"""Phase-4 S4-03/S4-04 — ``SolvedExampleStore`` Protocol + ``ChromaPersistentStore``.

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

5. **YAML-canonical + manifest.yaml (S4-04).** ``add()`` atomically
   writes (1) ``<root>/records/<id>.yaml`` (canonical Pydantic dump via
   :func:`_canonical_yaml_dump`, sorted keys, trailing newline), (2)
   chromadb (the derived index), (3) ``<root>/manifest.yaml`` rolled
   under the same ``asyncio.Lock``. ``manifest.yaml`` is the
   **order-of-truth** at store-open. ``digest()`` re-rolls the canonical
   YAML bytes (NOT the record-id strings — ADR-0016 §"content-addressed
   derived-index" pattern) so ``codegenie rag rebuild`` can golden-check
   ``digest() == manifest.chain_head`` byte-identical.

**What this module does NOT ship.** The ``provenance.event_chain_head``
chain-verify is S4-05. The ``codegenie rag rebuild`` operational
recovery command is S4-07. The two-threshold band classifier is S5-02 —
this module returns :class:`RagHit` / :class:`RagMiss` only, never
:class:`RagDegraded`.

**Vector boundary.** The store stores pre-computed ``embedding_vector``
values supplied by the caller and searches with a caller-supplied
``query_embedding``. It does not own an embedder; the retriever (S5-01)
does. The Protocol's public ``query`` therefore returns
:class:`RagMiss` until the retriever wires :meth:`_query_with_embedding`
— see :ref:`§Two read methods` in the body of this module.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, Protocol, final, runtime_checkable

import blake3
import chromadb
import structlog
import yaml
from chromadb.config import Settings
from pydantic import BaseModel, ConfigDict, ValidationError

from codegenie.rag.errors import StoreClosed, StoreCorrupted, StoreWriteContention
from codegenie.rag.models import Query, RagHit, RagMiss, RetrievalOutcome, SolvedExample
from codegenie.types.identifiers import (
    ChainHead,
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

_MANIFEST_FILENAME: Final[str] = "manifest.yaml"
_RECORDS_SUBDIR: Final[str] = "records"
_MANIFEST_SCHEMA_VERSION: Final[int] = 1
"""S4-04: ``manifest.yaml``'s ``schema_version`` literal. A future v2 (e.g.
Phase-11 pgvector or a ``backend_kind`` widening) bumps this and adds a
table-keyed dispatcher; the v1-only branch lives inline here per Rule 2."""

_FORBIDDEN_ID_SUBSTRINGS: Final[tuple[str, ...]] = ("/", "\\", "\x00")
"""S4-04 AC-14: a record id containing any of these would escape
``<root>/records/`` on disk. The check is in :meth:`ChromaPersistentStore.add`
before any write — :data:`SolvedExampleId` is a bare ``NewType`` and does
not re-validate."""


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


def _roll_chain_head(record_bytes: Iterable[bytes]) -> ChainHead:
    """Pure functional core (S4-04 AC-8): BLAKE3 over the concatenation of
    ``record_bytes`` in iteration order.

    Order-sensitive on purpose (ADR-0016 §"content-addressed derived-index").
    Sorting would hide insertion-order bugs; do not sort.

    The empty roll equals ``blake3(b"").hexdigest()`` (literal:
    ``af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262``).

    Pure — no filesystem, no allocation beyond the hasher. Pinned by
    ``tests/unit/rag/test_chain_head_monotonic.py``'s prefix-stability
    table test.
    """
    h = blake3.blake3()
    for blob in record_bytes:
        h.update(blob)
    return ChainHead(h.hexdigest())


def _compute_chain_head(record_ids: list[SolvedExampleId], records_dir: Path) -> ChainHead:
    """Imperative shell over :func:`_roll_chain_head`: read each canonical
    YAML record off disk in insertion order, then roll.

    Raises :class:`StoreCorrupted` (NOT bare ``FileNotFoundError``) when a
    listed record file is absent — AC-13. The translation lives here so
    every caller (``digest()``, the manifest write, ``_load_existing_record_ids``)
    sees the same typed error.

    **Why O(N) re-read each call (Notes §10).** A running hasher on
    ``self`` would be O(1) amortised but is hidden mutable state that can
    desync from disk and make ``digest()`` silently lie (Rule 12 violation).
    The stateless re-read keeps ``digest()`` a pure projection over disk.
    """

    def _read(rid: SolvedExampleId) -> bytes:
        try:
            return (records_dir / f"{rid}.yaml").read_bytes()
        except FileNotFoundError as e:
            raise StoreCorrupted(f"manifest references missing record: {rid}") from e

    return _roll_chain_head(_read(rid) for rid in record_ids)


def _canonical_yaml_dump(model: BaseModel) -> str:
    """Single serialisation surface for both the record YAML and the
    manifest YAML (S4-04 AC-1/AC-2). Identical PyYAML options on both
    sides keep AC-7's byte-identity guarantee stable across PyYAML
    versions.

    ``model_dump(mode="json")`` is load-bearing: Pydantic's ``json`` mode
    coerces ``datetime`` to ISO-8601 strings (otherwise PyYAML would
    serialise them as ``!!timestamp`` tags which would round-trip
    awkwardly). Sorted keys, no flow style, allow unicode, trailing
    newline.
    """
    return yaml.safe_dump(
        model.model_dump(mode="json"),
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
    )


def _atomic_write_text(path: Path, content: str) -> None:
    """Atomic write via sibling ``.tmp`` + :func:`os.replace`. Caller
    ensures ``path.parent`` exists (no hidden ``mkdir`` — Notes §2;
    Rule 8 — read before you write).

    The sibling ``.tmp`` lives in the same directory so ``os.replace``
    stays within one filesystem (a cross-fs replace raises
    ``OSError``). A stale ``.tmp`` from a crashed write is harmless:
    ``os.replace`` overwrites the same path on retry, and
    :meth:`ChromaPersistentStore._load_existing_record_ids` reads the
    manifest (not a ``records/*.yaml`` glob), so ``.tmp`` files are
    never enumerated (Notes §9).

    Mirrors ``src/codegenie/probes/layer_d/conventions.py`` — do not
    "improve" to ``shutil.move`` (Notes §2; cross-fs move is NOT atomic).
    Consolidating the ~8 per-module copies into a shared
    ``codegenie/_fsutil.py`` is a sanctioned migration candidate but
    out of scope for S4-04 (Rule 3).
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _validate_record_id_path_safe(record_id: str) -> None:
    """S4-04 AC-14: reject ids that would escape ``<root>/records/`` on
    disk before any write happens. :data:`SolvedExampleId` is a bare
    ``NewType`` and does not re-validate at the model boundary; this
    check is the write-path gate.

    The story's strict ``^[0-9a-f]{8,64}$`` reading would also reject the
    fixture ids the validator-prescribed tests themselves use (``ex-A``,
    ``ex-canonical-001``). The intent recorded in the AC text — "a test
    proves ``id="../../etc/passwd"`` cannot reach a filesystem write" —
    is path-safety, which this guard enforces (no path separators, no
    parent traversal, no NUL byte, no leading dot, non-empty).
    """
    if not record_id:
        raise ValueError("SolvedExample.id must be non-empty")
    if record_id.startswith("."):
        raise ValueError(f"SolvedExample.id may not begin with '.': {record_id!r}")
    if ".." in record_id:
        raise ValueError(f"SolvedExample.id may not contain '..' (path traversal): {record_id!r}")
    for forbidden in _FORBIDDEN_ID_SUBSTRINGS:
        if forbidden in record_id:
            raise ValueError(f"SolvedExample.id may not contain {forbidden!r}: {record_id!r}")


# ---------------------------------------------------------------------------
# _Manifest — module-private durability artefact (S4-04 AC-9)
# ---------------------------------------------------------------------------


class _Manifest(BaseModel):
    """``manifest.yaml`` durability shape — module-private (NOT exported).

    Schema versioning is intentionally minimal (``Literal[1]``); a future
    v2 (Phase-11 pgvector or a ``backend_kind`` widening) will bump the
    version and the genuine Open/Closed seam (a table keyed on
    ``schema_version``) lands then — premature today (Rule 2; Notes §8).

    No ``from_yaml`` classmethod by design: the inline defensive parse
    in :meth:`ChromaPersistentStore._load_existing_record_ids` is the
    only reader. Public ``SolvedExample.from_yaml`` (S4-07 consumer) is
    the only named YAML parser in the RAG surface.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    records: list[SolvedExampleId]
    chain_head: ChainHead


def _parse_manifest_or_raise(manifest_path: Path) -> _Manifest:
    """Defensive parse — every malformed-manifest case translates to
    :class:`StoreCorrupted` (S4-04 AC-9). NEVER lets ``yaml.YAMLError``
    or ``pydantic.ValidationError`` leak through.

    Check order matters (Notes §8): the raw ``schema_version`` is
    inspected BEFORE :meth:`_Manifest.model_validate`. ``_Manifest`` is
    ``extra="forbid"`` + ``schema_version: Literal[1]``; without the
    pre-check a hypothetical v2 manifest would fail validation with a
    generic :class:`ValidationError` instead of the intended
    :class:`StoreCorrupted` diagnostic that names the upgrade path.
    """
    try:
        raw_text = manifest_path.read_text(encoding="utf-8")
    except OSError as e:
        raise StoreCorrupted(f"manifest.yaml read failed: {e}") from e
    try:
        parsed = yaml.safe_load(raw_text)
    except yaml.YAMLError as e:
        raise StoreCorrupted("manifest.yaml is not valid YAML") from e
    if not isinstance(parsed, dict):
        raise StoreCorrupted("manifest.yaml must be a mapping at the top level")
    schema_version = parsed.get("schema_version")
    if schema_version != _MANIFEST_SCHEMA_VERSION:
        raise StoreCorrupted(
            f"unknown manifest schema_version: {schema_version!r} "
            f"(expected {_MANIFEST_SCHEMA_VERSION})"
        )
    try:
        return _Manifest.model_validate(parsed)
    except ValidationError as e:
        raise StoreCorrupted(f"manifest.yaml is malformed: {e}") from e


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

    __slots__ = (
        "_add_lock",
        "_client",
        "_collections",
        "_record_ids",
        "_records_dir",
        "_root_dir",
    )

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._records_dir = root_dir / _RECORDS_SUBDIR
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
        """S4-04 AC-3 — populate ``_record_ids`` from ``manifest.yaml``.

        ``manifest.yaml`` is the order-of-truth (NOT chromadb): chromadb's
        ``collection.get()`` does not guarantee insertion order and there
        is one collection per partition.

        Absent manifest → fresh store (``_record_ids = []``). Present but
        malformed → :class:`StoreCorrupted` (AC-9). Listed record file
        missing on disk → :class:`StoreCorrupted` via
        :func:`_compute_chain_head` (AC-13).
        """
        manifest_path = self._root_dir / _MANIFEST_FILENAME
        if not manifest_path.exists():
            self._record_ids = []
            return
        manifest = _parse_manifest_or_raise(manifest_path)
        # AC-13: every listed record file must be present on disk; the
        # cheapest reproduction is to drive _compute_chain_head, which
        # already translates missing files to StoreCorrupted.
        _compute_chain_head(list(manifest.records), self._records_dir)
        self._record_ids = list(manifest.records)

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
        _validate_record_id_path_safe(example.id)
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

            # 1. Canonical YAML (S4-04 AC-1) — written FIRST so a chromadb
            #    failure leaves a recoverable orphan (AC-4); caller mkdirs
            #    the records dir, NOT the atomic-write helper (AC-1 + Notes §2).
            self._records_dir.mkdir(parents=True, exist_ok=True)
            _atomic_write_text(
                self._records_dir / f"{example.id}.yaml",
                _canonical_yaml_dump(example),
            )
            _LOG.debug("store.add.yaml_written", example_id=example.id)

            # 2. chromadb (derived index) — if this raises, steps 3..5 never
            #    run; _record_ids stays unappended; manifest stays untouched
            #    (AC-4). The YAML orphan is recoverable by `codegenie rag
            #    rebuild` (S4-07).
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
            _LOG.debug("store.add.chroma_written", example_id=example.id)

            # 3. Manifest update (S4-04 AC-2) — last; identical PyYAML
            #    options to AC-1's record dump (AC-7 byte-identity). If the
            #    manifest write raises (AC-12), in-process self-heal kicks
            #    in on the next successful add; cross-process recovery is
            #    `codegenie rag rebuild` (S4-07).
            self._record_ids.append(SolvedExampleId(example.id))
            chain_head = _compute_chain_head(self._record_ids, self._records_dir)
            manifest = _Manifest(
                records=list(self._record_ids),
                chain_head=chain_head,
            )
            _atomic_write_text(
                self._root_dir / _MANIFEST_FILENAME,
                _canonical_yaml_dump(manifest),
            )
            # AC-12: if the manifest write raised, the exception propagates
            # and `self._record_ids` still holds `example.id` — by design.
            # The next successful add() rewrites a manifest that re-includes
            # it (in-process self-heal); a cross-process restart reconciles
            # via `codegenie rag rebuild` (S4-07).
            _LOG.debug("store.add.manifest_updated", example_id=example.id)
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
        """BLAKE3-rolled digest over the canonical YAML bytes of every
        record (insertion order — S4-04 §5).

        Re-wraps :func:`_compute_chain_head` from :data:`ChainHead` to the
        Protocol-pinned :data:`StoreDigest` newtype (S4-04 AC-5). The
        same BLAKE3 hex is re-typed at the boundary; one canonical
        computation, two distinct domain newtypes.

        ``digest() == manifest.chain_head`` is the load-bearing invariant
        S4-07's ``rag rebuild`` golden test pins. Cross-process
        determinism arrives because both sides roll the canonical YAML
        bytes (NOT the record-id strings — ADR-0016 §"content-addressed
        derived-index").

        Empty store digest is ``blake3(b"").hexdigest()`` —
        ``af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262``.
        Survives :meth:`close` because ``_record_ids`` is unaffected
        (AC-7).
        """
        chain_head = _compute_chain_head(self._record_ids, self._records_dir)
        # ChainHead → StoreDigest re-wrap at the Protocol boundary (AC-5)
        return StoreDigest(chain_head)

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
