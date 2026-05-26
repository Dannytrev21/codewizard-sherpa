"""Phase-4 S5-03 — embedding-model-mismatch filter.

Concrete implementation of S5-01's ``model_digest_filter`` hook
(``Callable[[Sequence[ScoredSolvedExample]],
tuple[list[ScoredSolvedExample], int]]``). Excludes any candidate whose
``record.embedding_model`` does not match the live embedder's
``model_digest()`` — a model bump invalidates prior vectors (ADR-04-0007),
so comparing a fresh query embedding against a stale-model record
produces silently-wrong similarity scores.

Discipline:

* Frozen dataclass; constructor-injected ``Embedder`` + ``EventLog``.
* ``__post_init__`` caches the live model digest once (ADR-04-0007 pins
  the digest for the embedder lifetime — caching is correct and matches
  the S5-01 idempotence invariant).
* The filter emits its own ``RagRecordModelMismatch`` event with the
  live ``current_model`` and a representative ``sample_stale_model``;
  the retriever no longer emits this event.
* ``count == 0`` paths are silent (no event noise on zero exclusions).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from codegenie.plugins.events import EventLog, RagRecordModelMismatch
from codegenie.rag.embedder import Embedder
from codegenie.rag.models import ScoredSolvedExample
from codegenie.types.identifiers import BlobDigest, EventId

__all__ = ["EmbeddingModelMismatchFilter"]


def _new_event_id() -> EventId:
    return EventId("01HRMM" + uuid.uuid4().hex[:20].upper())


@dataclass(frozen=True)
class EmbeddingModelMismatchFilter:
    """Frozen-dataclass filter implementing S5-01's
    ``model_digest_filter`` hook.

    Cached lookup of ``embedder.model_digest()`` happens in
    ``__post_init__`` via the frozen-dataclass lazy-cache idiom
    (``object.__setattr__`` on the frozen instance — ADR-04-0007 pins
    the digest for the embedder lifetime).
    """

    embedder: Embedder
    event_log: EventLog
    _current_model_digest: BlobDigest = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_current_model_digest",
            self.embedder.model_digest(),
        )

    def __call__(
        self, candidates: Sequence[ScoredSolvedExample]
    ) -> tuple[list[ScoredSolvedExample], int]:
        """Return ``(surviving, excluded_count)``.

        Surviving = exactly those candidates whose
        ``record.embedding_model`` equals the cached
        ``_current_model_digest``. Order is preserved (the partition is
        deterministic).

        Side effect (only on ``excluded_count > 0``): emits exactly one
        :class:`RagRecordModelMismatch` event naming the live model and
        a representative stale model.
        """
        current = self._current_model_digest
        current_str = str(current)
        surviving: list[ScoredSolvedExample] = []
        sample_stale: BlobDigest | None = None
        excluded_count = 0
        for c in candidates:
            # ``record.embedding_model`` is a ``ModelId`` (NewType[str]);
            # ``current`` is a ``BlobDigest`` (NewType[str]). Both wrap
            # ``str`` and the production convention is that the record's
            # embedding-model field carries the BLAKE3 digest hex (S4-04
            # canonical YAML records are written that way). Compare via
            # the underlying string so mypy's NewType-aware ``==`` does
            # not flag the otherwise-correct comparison.
            if str(c.record.embedding_model) == current_str:
                surviving.append(c)
            else:
                excluded_count += 1
                if sample_stale is None:
                    sample_stale = BlobDigest(str(c.record.embedding_model))
        if excluded_count > 0 and sample_stale is not None:
            self.event_log.emit_internal(
                RagRecordModelMismatch(
                    event_id=_new_event_id(),
                    workflow_id=self.event_log.workflow_id,
                    timestamp=datetime.now(UTC),
                    count=excluded_count,
                    current_model=current,
                    sample_stale_model=sample_stale,
                )
            )
        return surviving, excluded_count
