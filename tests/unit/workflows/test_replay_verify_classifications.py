"""Phase 6 S2-02 AC-5 — verdict-classification matrix (against the in-memory adapter).

Five scenarios covering the four verdict variants. SQLite-specific
torn-write cases (raw-SQLite UPDATE patterns) live in AC-10's
integration test.
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
    ChainMismatch,
    EmptyWorkflow,
    ReplayVerifier,
    TornWrite,
    Verified,
)
from codegenie.workflows.vuln_ledger import TransitionEvent


def _e(transition_id: str, prior: str, nxt: str, workflow_id: str) -> TransitionEvent:
    return TransitionEvent(
        transition_id=TransitionId(transition_id),
        prior_state_id=prior,  # type: ignore[arg-type]
        next_state_id=nxt,  # type: ignore[arg-type]
        triggering_outcome="ok",
        evidence_digest=BlobDigest("blake3:" + "a" * 64),
        chain_head=ChainHead("0" * 64),
        workflow_id=WorkflowId(workflow_id),
    )


_WF = "01HZZZZZZZZZZZZZZ225001VFWF"


def _build_clean(store: InMemoryCheckpointStore) -> list[TransitionEvent]:
    events = [
        _e("01HZZZZZZZZZZZZZZ22500100A1", "needs_plan", "plan_ready", _WF),
        _e("01HZZZZZZZZZZZZZZ22500100A2", "plan_ready", "patch_applied", _WF),
        _e("01HZZZZZZZZZZZZZZ22500100A3", "patch_applied", "completed", _WF),
    ]
    for ev in events:
        store.append(ev)
    return events


def test_ac5_empty_workflow_returns_empty_workflow_verdict(tmp_path: Path) -> None:
    store = InMemoryCheckpointStore(tmp_path)
    try:
        verdict = ReplayVerifier(store).verify(WorkflowId(_WF))
        assert isinstance(verdict, EmptyWorkflow)
        assert verdict.genesis_chain_head == ChainHead("0" * 64)
    finally:
        store.close()


def test_ac5_legitimate_sequence_returns_verified(tmp_path: Path) -> None:
    store = InMemoryCheckpointStore(tmp_path)
    try:
        events = _build_clean(store)
        verdict = ReplayVerifier(store).verify(WorkflowId(_WF))
        assert isinstance(verdict, Verified)
        assert verdict.events == tuple(events)
    finally:
        store.close()


def test_ac5_tail_tamper_returns_chain_mismatch_at_last_index(tmp_path: Path) -> None:
    store = InMemoryCheckpointStore(tmp_path)
    try:
        events = _build_clean(store)
        # Tamper with the last row's persisted head directly in the in-memory log.
        last_head, last_bytes = store._log[WorkflowId(_WF)][-1]
        store._log[WorkflowId(_WF)][-1] = (ChainHead("deadbeef" * 8), last_bytes)
        verdict = ReplayVerifier(store).verify(WorkflowId(_WF))
        assert isinstance(verdict, ChainMismatch)
        assert verdict.divergence_index == len(events) - 1
        assert verdict.offending_transition_id == events[-1].transition_id
        assert verdict.persisted_tail == ChainHead("deadbeef" * 8)
    finally:
        store.close()


def test_ac5_middle_tamper_reports_first_divergence_index(tmp_path: Path) -> None:
    """A buggy verifier that walks back-to-front would report index 2; the test demands 1."""
    store = InMemoryCheckpointStore(tmp_path)
    try:
        events = _build_clean(store)
        log = store._log[WorkflowId(_WF)]
        log[1] = (ChainHead("cafebabe" * 8), log[1][1])
        # Note: the persisted tail is unchanged (we tampered with row 1, not 2).
        verdict = ReplayVerifier(store).verify(WorkflowId(_WF))
        assert isinstance(verdict, ChainMismatch)
        # First divergence is at index 1 — the tampered middle row.
        assert verdict.divergence_index == 1
        assert verdict.offending_transition_id == events[1].transition_id
    finally:
        store.close()


def test_ac5_tampered_event_bytes_returns_chain_mismatch(tmp_path: Path) -> None:
    """Different bytes ⇒ different chain head when folded."""
    store = InMemoryCheckpointStore(tmp_path)
    try:
        _build_clean(store)
        log = store._log[WorkflowId(_WF)]
        # Replace the middle row's bytes with a different but valid event.
        bogus = (
            _e(
                "01HZZZZZZZZZZZZZZ22500100BX",
                "plan_ready",
                "patch_applied",
                _WF,
            )
            .model_dump_json()
            .encode("utf-8")
        )
        log[1] = (log[1][0], bogus)
        verdict = ReplayVerifier(store).verify(WorkflowId(_WF))
        assert isinstance(verdict, ChainMismatch)
        assert verdict.divergence_index == 1
    finally:
        store.close()


def test_ac5_unparseable_event_bytes_returns_torn_write(tmp_path: Path) -> None:
    """Truncated JSON in persisted bytes ⇒ TornWrite(unparseable_event)."""
    store = InMemoryCheckpointStore(tmp_path)
    try:
        _build_clean(store)
        log = store._log[WorkflowId(_WF)]
        log[1] = (log[1][0], b'{"not": "complete')  # truncated JSON
        verdict = ReplayVerifier(store).verify(WorkflowId(_WF))
        assert isinstance(verdict, TornWrite)
        assert verdict.reason == "unparseable_event"
        assert verdict.offending_sequence == 1
    finally:
        store.close()


def test_ac5_verdict_is_one_of_four_kinds(tmp_path: Path) -> None:
    """No matter the input, the verdict's kind is one of the four closed slugs."""
    store = InMemoryCheckpointStore(tmp_path)
    try:
        verdict = ReplayVerifier(store).verify(WorkflowId(_WF))
        assert verdict.kind in {"verified", "chain_mismatch", "torn_write", "empty_workflow"}
    finally:
        store.close()


def test_ac5_verifier_uses_protocol_only(tmp_path: Path) -> None:
    """The verifier dispatches through the Protocol — no substrate shortcut."""
    import inspect

    from codegenie.workflows import replay as replay_module

    src = inspect.getsource(replay_module)
    # No SQLite-specific imports / calls.
    assert "sqlite3" not in src
    assert "fcntl" not in src
    assert "SELECT" not in src
