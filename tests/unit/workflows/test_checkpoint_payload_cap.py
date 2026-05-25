"""Phase 6 S2-01 AC-10 — per-event canonical-JSON byte cap.

The 64 KiB cap lives at the *store* layer (AC-10 Mutation thinking)
so the forensic ``EventLog`` (Phase-3 S6-01) can still carry full
evidence. The cap is the surface that catches accidental evidence
inlining (a node storing a full RAG cassette as ``triggering_outcome``
rather than a ``BlobDigest`` reference).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    TransitionId,
    WorkflowId,
)
from codegenie.workflows.checkpoints import _MAX_EVENT_BYTES
from codegenie.workflows.errors import CheckpointPayloadTooLargeError
from codegenie.workflows.in_memory_checkpoints import InMemoryCheckpointStore
from codegenie.workflows.sqlite_checkpoints import SqliteCheckpointStore
from codegenie.workflows.vuln_ledger import TransitionEvent


def _oversize_event() -> TransitionEvent:
    """Build a ``TransitionEvent`` whose canonical-JSON bytes exceed the cap."""
    blob = "x" * (_MAX_EVENT_BYTES + 1024)
    return TransitionEvent(
        transition_id=TransitionId("01HZZZZZZZZZZZZZZAC010A001"),
        prior_state_id="needs_plan",
        next_state_id="plan_ready",
        triggering_outcome={"blob": blob},
        evidence_digest=BlobDigest("blake3:" + "a" * 64),
        chain_head=ChainHead("0" * 64),
        workflow_id=WorkflowId("01HZZZZZZZZZZZZZZAC010WF01"),
    )


def test_ac10_sqlite_rejects_oversize_payload(tmp_path: Path) -> None:
    store = SqliteCheckpointStore(tmp_path)
    try:
        with pytest.raises(CheckpointPayloadTooLargeError) as exc_info:
            store.append(_oversize_event())
        msg = str(exc_info.value)
        assert "64 KiB" in msg
        assert "ADR-0003" in msg
        assert "blob digest" in msg.lower() or "blobdigest" in msg.lower()
    finally:
        store.close()


def test_ac10_in_memory_rejects_oversize_payload(tmp_path: Path) -> None:
    store = InMemoryCheckpointStore(tmp_path)
    try:
        with pytest.raises(CheckpointPayloadTooLargeError):
            store.append(_oversize_event())
    finally:
        store.close()


def test_ac10_typed_exception_error_id_grammar() -> None:
    """The ``error_id`` matches the Phase-1 ADR-0007 dotted-snake-case grammar."""
    import re

    err_id = CheckpointPayloadTooLargeError.error_id
    assert re.fullmatch(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$", err_id), err_id
    assert err_id == "workflows.checkpoint_payload_too_large"


def test_ac10_cap_lives_at_store_layer_not_model_layer() -> None:
    """``TransitionEvent`` itself does not cap size — the forensic log uses it raw."""
    big = "x" * (_MAX_EVENT_BYTES + 1024)
    # Model accepts the oversized payload (validates fields, not byte size).
    event = TransitionEvent(
        transition_id=TransitionId("01HZZZZZZZZZZZZZZAC010A002"),
        prior_state_id="needs_plan",
        next_state_id="plan_ready",
        triggering_outcome={"blob": big},
        evidence_digest=BlobDigest("blake3:" + "a" * 64),
        chain_head=ChainHead("0" * 64),
        workflow_id=WorkflowId("01HZZZZZZZZZZZZZZAC010WF02"),
    )
    # The bytes really are over the cap.
    assert len(event.model_dump_json().encode()) > _MAX_EVENT_BYTES
