"""Phase-4 S4-01 typed errors for the RAG-substrate embedder.

Two error classes carry the failure modes the runtime ``__init__`` raises
when the on-disk ``embeddings_model.lock`` is missing, corrupt, or out of
sync with the on-disk weights cache:

- :class:`EmbeddingsBootstrapRequired` — operator must (re-)run
  ``codegenie embeddings bootstrap``.
- :class:`EmbeddingModelMismatch` — model identity or weight digest
  diverged from what the lock pins. ``kind`` discriminator distinguishes
  the two raise-sites (ADR-0007 §Decision + edge case #3).

Both inherit :class:`Exception` (markers-only — no behaviour beyond
attribute carriage; the CLAUDE.md convention) and stringify via an
explicit ``__str__`` so the diagnostic message is part of the contract
rather than ``args[0]``-folklore.
"""

from __future__ import annotations

from typing import Final, Literal

from codegenie.types.identifiers import WorkflowId

_RUNBOOK_URL: Final[str] = "docs/operations/embeddings.md"
_BOOTSTRAP_CMD: Final[str] = "codegenie embeddings bootstrap"


class EmbeddingsBootstrapRequired(Exception):
    """Raised at runtime when the embeddings substrate has not been
    bootstrapped (lock missing, lock corrupt, or lock present but
    on-disk weights absent). Same remedy for all three: re-run
    ``codegenie embeddings bootstrap``.

    Attributes
    ----------
    runbook_url:
        Pointer to the operator runbook (``docs/operations/embeddings.md``).
    reason:
        Short human-readable phrase naming which sub-branch raised
        (``"lock file missing"`` / ``"lock file corrupt"`` /
        ``"on-disk weights absent"``). Exposed so callers can branch on
        the cause without parsing ``__str__``.
    """

    __slots__ = ("reason", "runbook_url")

    runbook_url: str
    reason: str

    def __init__(self, *, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.runbook_url = _RUNBOOK_URL

    def __str__(self) -> str:
        return (
            f"embeddings substrate not bootstrapped — {self.reason}; "
            f"run `{_BOOTSTRAP_CMD}` (runbook: {self.runbook_url})"
        )


class EmbeddingModelMismatch(Exception):
    """Raised at runtime when the on-disk embeddings state diverges from
    what the lock pins. ADR-0007 §Decision + arch edge case #3 — halts
    the worker rather than silently embedding into a different vector
    space.

    The ``kind`` discriminator is load-bearing: the same exception type
    is raised at two semantically distinct sites (lock ``model_name`` vs
    ctor ``model_name``; on-disk weights digest vs ``lock.sha256``).
    Without ``kind`` an operator or test cannot tell which.

    Attributes
    ----------
    kind:
        ``"model_name"`` or ``"sha256"`` — which invariant was violated.
    expected:
        The lock-pinned value the runtime expected to see. (For
        ``kind="model_name"`` this is the ctor's ``model_name``; for
        ``kind="sha256"`` this is ``lock.sha256``.)
    found:
        The value that was actually observed on disk.
    runbook_url:
        Pointer to the operator runbook.
    """

    __slots__ = ("expected", "found", "kind", "runbook_url")

    kind: Literal["model_name", "sha256"]
    expected: str
    found: str
    runbook_url: str

    def __init__(
        self,
        *,
        kind: Literal["model_name", "sha256"],
        expected: str,
        found: str,
    ) -> None:
        super().__init__(kind, expected, found)
        self.kind = kind
        self.expected = expected
        self.found = found
        self.runbook_url = _RUNBOOK_URL

    def __str__(self) -> str:
        return (
            f"embeddings model drift — kind={self.kind} "
            f"expected={self.expected!r} found={self.found!r}; "
            f"runbook: {self.runbook_url}"
        )


class EmbeddingsCacheCorrupted(Exception):
    """Raised internally by :mod:`codegenie.rag.embedding_cache` when a
    single cached row's vector blob is not a length-checked ``np.float32``
    payload of ``_VECTOR_BYTES`` bytes. Carries the composite-key triple
    (``text_blake3``, ``model_digest``, observed ``byte_len``) so the
    caller can delete *exactly* that row before re-embedding (story S4-02
    AC-8).

    This exception is a private contract between the cache wrapper's
    ``_decode_row`` helper and its ``embed()`` / ``embed_batch()`` shells.
    It MUST NOT escape the public ``Embedder`` boundary — the shells catch
    it, delete the offending row, log ``embedding_cache_row_corrupted``,
    re-embed, and write the replacement (S4-02 §AC-8).
    """

    __slots__ = ("byte_len", "model_digest", "text_blake3")

    text_blake3: str
    model_digest: str
    byte_len: int

    def __init__(self, *, text_blake3: str, model_digest: str, byte_len: int) -> None:
        super().__init__(text_blake3, model_digest, byte_len)
        self.text_blake3 = text_blake3
        self.model_digest = model_digest
        self.byte_len = byte_len

    def __str__(self) -> str:
        return (
            f"embeddings cache row corrupt — text_blake3={self.text_blake3} "
            f"model_digest={self.model_digest} byte_len={self.byte_len}"
        )


class StoreWriteContention(Exception):
    """Raised by :class:`codegenie.rag.store.ChromaPersistentStore.add` when
    the process-local single-writer lock cannot be acquired within
    ``_ADD_LOCK_TIMEOUT_SECONDS`` (default ``30.0``).

    ADR-0016 §Decision + arch §Gap 3 — declared serialization is the
    Phase-4 conformance bar for any future ``SolvedExampleStore`` adapter
    (Phase-11 pgvector). Silent hangs under 24-worker harvest contention
    are the failure mode this exception exists to make loud.

    Attributes
    ----------
    workflow_id:
        ULID of the harvester whose ``add()`` lost the race. Carried
        verbatim from the ``SolvedExampleWriteCapability``; the orchestrator
        emits ``SolvedExampleIngestFailed(reason=write_contention,
        workflow_id=...)`` rather than failing the workflow outright.
    """

    __slots__ = ("workflow_id",)

    workflow_id: WorkflowId

    def __init__(self, *, workflow_id: WorkflowId) -> None:
        super().__init__(workflow_id)
        self.workflow_id = workflow_id

    def __str__(self) -> str:
        return f"SolvedExampleStore.add lock-contention timeout — workflow_id={self.workflow_id!r}"


class StoreClosed(Exception):
    """Raised when a method on :class:`ChromaPersistentStore` is invoked
    after :meth:`close`. ``add`` / ``query`` / ``_query_with_embedding``
    raise this; ``digest`` does **not** (it is a pure projection over the
    in-memory record-id list which ``close`` leaves intact — see story
    S4-03 AC-7).
    """

    __slots__ = ()


class StoreCorrupted(Exception):
    """Family marker for chromadb-side corruption recovery (rebuild-from-
    YAML, later stories S4-04 / S4-07). **Declared in S4-03 for the error
    family**, **not raised by S4-03 code paths**. A story that raises this
    must own the recovery path that consumes it.
    """

    __slots__ = ()


__all__ = (
    "EmbeddingModelMismatch",
    "EmbeddingsBootstrapRequired",
    "EmbeddingsCacheCorrupted",
    "StoreClosed",
    "StoreCorrupted",
    "StoreWriteContention",
)
