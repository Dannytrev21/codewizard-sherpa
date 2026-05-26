"""Phase 6 S2-02 AC-8 — ``hydrate_or_fail`` four routing tests.

Per-mapping tests, not parametrize (each verdict has different setup
costs; Notes-for-implementer documents the rationale).
"""

from __future__ import annotations

from pathlib import Path

from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    TransitionId,
    WorkflowId,
)
from codegenie.workflows.in_memory_checkpoints import InMemoryCheckpointStore
from codegenie.workflows.replay import (
    _INTEGRITY_ERROR_ID,
    Hydrated,
    hydrate_or_fail,
)
from codegenie.workflows.vuln_ledger import FailedUnrecoverable, TransitionEvent


def _e(transition_id: str, prior: str, nxt: str, wf: str) -> TransitionEvent:
    return TransitionEvent(
        transition_id=TransitionId(transition_id),
        prior_state_id=prior,  # type: ignore[arg-type]
        next_state_id=nxt,  # type: ignore[arg-type]
        triggering_outcome="ok",
        evidence_digest=BlobDigest("blake3:" + "a" * 64),
        chain_head=ChainHead("0" * 64),
        workflow_id=WorkflowId(wf),
    )


def test_ac8_empty_workflow_routes_to_hydrated_needs_plan(tmp_path: Path) -> None:
    store = InMemoryCheckpointStore(tmp_path)
    try:
        result = hydrate_or_fail(store, WorkflowId("01HZZZZZZZZZZZZZZ228001ROOT0"))
        assert isinstance(result, Hydrated)
        assert result.events == ()
        assert result.latest_state_kind == "needs_plan"
    finally:
        store.close()


def test_ac8_verified_routes_to_hydrated_with_latest_state(tmp_path: Path) -> None:
    store = InMemoryCheckpointStore(tmp_path)
    wf = "01HZZZZZZZZZZZZZZ228002ROOT0"
    try:
        events = [
            _e("01HZZZZZZZZZZZZZZ22800200001", "needs_plan", "plan_ready", wf),
            _e("01HZZZZZZZZZZZZZZ22800200002", "plan_ready", "patch_applied", wf),
            _e("01HZZZZZZZZZZZZZZ22800200003", "patch_applied", "completed", wf),
        ]
        for ev in events:
            store.append(ev)
        result = hydrate_or_fail(store, WorkflowId(wf))
        assert isinstance(result, Hydrated)
        assert result.events == tuple(events)
        assert result.latest_state_kind == "completed"
    finally:
        store.close()


def test_ac8_chain_mismatch_routes_to_failed_unrecoverable(tmp_path: Path) -> None:
    store = InMemoryCheckpointStore(tmp_path)
    wf = "01HZZZZZZZZZZZZZZ228003ROOT0"
    try:
        events = [
            _e("01HZZZZZZZZZZZZZZ22800300001", "needs_plan", "plan_ready", wf),
            _e("01HZZZZZZZZZZZZZZ22800300002", "plan_ready", "patch_applied", wf),
        ]
        for ev in events:
            store.append(ev)
        # Tamper with the last row's head.
        log = store._log[WorkflowId(wf)]
        log[-1] = (ChainHead("deadbeef" * 8), log[-1][1])
        result = hydrate_or_fail(store, WorkflowId(wf))
        assert isinstance(result, FailedUnrecoverable)
        assert result.reason == "checkpoint_integrity"
        assert result.error is not None
        assert str(result.error.error_id) == str(_INTEGRITY_ERROR_ID)
        assert "divergence_index=1" in result.error.message
        assert "chain_mismatch" in result.error.message
    finally:
        store.close()


def test_ac8_torn_write_routes_to_failed_unrecoverable(tmp_path: Path) -> None:
    store = InMemoryCheckpointStore(tmp_path)
    wf = "01HZZZZZZZZZZZZZZ228004ROOT0"
    try:
        for ev in [
            _e("01HZZZZZZZZZZZZZZ22800400001", "needs_plan", "plan_ready", wf),
            _e("01HZZZZZZZZZZZZZZ22800400002", "plan_ready", "patch_applied", wf),
        ]:
            store.append(ev)
        log = store._log[WorkflowId(wf)]
        log[0] = (log[0][0], b'{"truncated')  # unparseable bytes
        result = hydrate_or_fail(store, WorkflowId(wf))
        assert isinstance(result, FailedUnrecoverable)
        assert result.reason == "checkpoint_integrity"
        assert result.error is not None
        assert "torn_write" in result.error.message
        assert "unparseable_event" in result.error.message
    finally:
        store.close()


def test_ac8_integrity_error_id_matches_phase1_grammar() -> None:
    """``error_id`` is dotted_snake_case per Phase-1 ADR-0007."""
    import re

    assert re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*", str(_INTEGRITY_ERROR_ID))


def test_ac8_hydrated_kind_literal_is_hydrated() -> None:
    """``Hydrated.kind`` is a NEW closed tag, NOT reused from ``LedgerStateKind``."""
    assert Hydrated.model_fields["kind"].default == "hydrated"
    # Sanity: "hydrated" is not a LedgerStateKind value.
    from typing import get_args

    from codegenie.workflows.vuln_ledger import LedgerStateKind

    assert "hydrated" not in set(get_args(LedgerStateKind))
