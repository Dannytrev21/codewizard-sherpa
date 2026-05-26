"""Phase 6 S2-01 — in-memory ``CheckpointStore`` adapter for tests.

Single-process test substrate; the ``lock()`` context manager is a
no-op (cross-process safety is exercised against the SQLite adapter).
Mirrors the Phase-3 ``InMemorySink`` (events.py) shape — the per-event
record carries only what ``read_all_for_workflow`` + ``tail_chain_head``
need (no ``written_at`` audit column; that lives only in the SQLite
adapter's row schema).

Anti-refactor (story §"Anti-refactor #1"): this class does **not**
inherit from anything; the Protocol is the contract. Shared logic
(boundary check, canonical event bytes) is composed in via free
functions in :mod:`codegenie.workflows.checkpoints`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from codegenie.output.sanitizer import sanitize_for_persistence
from codegenie.types.identifiers import ChainHead, WorkflowId
from codegenie.workflows._chain import _compute_chain_head
from codegenie.workflows.checkpoints import (
    _GENESIS_CHAIN_HEAD,
    _MAX_EVENT_BYTES,
    _PAYLOAD_TOO_LARGE_DIRECTIVE,
    _assert_boundary,
    _canonical_event_bytes,
)
from codegenie.workflows.errors import CheckpointPayloadTooLargeError
from codegenie.workflows.vuln_ledger import TransitionEvent

__all__ = [
    "InMemoryCheckpointStore",
]


class InMemoryCheckpointStore:
    """Dict-of-lists implementation of :class:`CheckpointStore` for tests.

    Internal shape: ``dict[WorkflowId, list[tuple[TransitionEvent, ChainHead]]]``.
    Append-order is the list-append order; ``tail_chain_head`` reads the
    last entry's second tuple element (NOT recomputed — AC-11
    detection-substrate-only contract).
    """

    __slots__ = ("_root", "_log")

    def __init__(self, root: object | None = None) -> None:
        """Construct an empty in-memory store.

        ``root`` is accepted (and ignored) so the test parity fixture can
        construct ``InMemoryCheckpointStore(tmp_path)`` and
        ``SqliteCheckpointStore(tmp_path)`` with the same call.
        """
        self._root = root
        # Each row is (next_head, sanitized_event_bytes) — mirrors the
        # SQLite row shape so read-back parsing is byte-identical
        # across adapters (AC-6 parity contract).
        self._log: dict[WorkflowId, list[tuple[ChainHead, bytes]]] = {}

    def append(self, event: TransitionEvent) -> ChainHead:
        _assert_boundary(event)
        payload = _canonical_event_bytes(event)
        if len(payload) > _MAX_EVENT_BYTES:
            raise CheckpointPayloadTooLargeError(_PAYLOAD_TOO_LARGE_DIRECTIVE)
        # AC-12 — canonical sanitizer is the ONLY redaction path. Both
        # adapters route through this; forking re into either file
        # trips the AST fence at
        # tests/fence/test_checkpoint_sanitizer_imports.py.
        stored = sanitize_for_persistence(payload)
        prior = self.tail_chain_head(event.workflow_id)
        # Phase-6 S2-02 AC-3 sanitization-aware chain discipline: chain
        # head protects the BYTES ON DISK so the verifier can reproduce
        # the rolling head from the persisted (possibly redacted)
        # payload. For non-secret-shaped events the reconstructed event
        # is byte-equal to the live event (sanitize is a no-op).
        chain_input_event = TransitionEvent.model_validate_json(stored)
        next_head = _compute_chain_head(prior, chain_input_event)
        self._log.setdefault(event.workflow_id, []).append((next_head, stored))
        return next_head

    def read_all_for_workflow(self, workflow_id: WorkflowId) -> Iterator[TransitionEvent]:
        for _head, stored in self._log.get(workflow_id, []):
            yield TransitionEvent.model_validate_json(stored)

    def iter_persisted_chain(
        self, workflow_id: WorkflowId
    ) -> Iterator[tuple[TransitionEvent, ChainHead]]:
        for head, stored in self._log.get(workflow_id, []):
            yield TransitionEvent.model_validate_json(stored), head

    def tail_chain_head(self, workflow_id: WorkflowId) -> ChainHead:
        rows = self._log.get(workflow_id)
        if not rows:
            return _GENESIS_CHAIN_HEAD
        return rows[-1][0]

    @contextmanager
    def lock(self, workflow_id: WorkflowId) -> Iterator[None]:
        # Single-process tests need no real lock — cross-process safety
        # is exercised against the SQLite store. Mirrors the Phase-3
        # ``InMemorySink.lock`` no-op pattern.
        del workflow_id
        yield

    def close(self) -> None:
        self._log.clear()
