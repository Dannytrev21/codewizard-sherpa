"""Phase 6 S2-02 AC-3 — sanitization-aware fold round-trip.

The load-bearing invariant the S2-01 attempt log surfaced: the chain
head is computed over the LIVE event (cleartext); the on-disk row is
the SANITIZED bytes. A naive verifier that recomputes by reading the
persisted bytes and re-hashing them WITHOUT round-tripping through
TransitionEvent.model_validate_json would compute a DIFFERENT head than
was persisted IFF sanitization triggered, and would falsely declare
ChainMismatch.

The fix is the round-trip: the verifier reads persisted bytes, parses
them via model_validate_json into a TransitionEvent, then folds via
_compute_chain_head. Because sanitize_for_persistence operates on
canonical-JSON bytes and replaces only secret-shaped substrings with
idempotent <REDACTED:fingerprint=...> sentinels (themselves valid JSON
strings), the reconstructed event produces byte-equal model_dump_json()
output — so the verifier's fold reproduces the write-path BLAKE3 input
by construction.
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
from codegenie.workflows.replay import ReplayVerifier, Verified
from codegenie.workflows.sqlite_checkpoints import SqliteCheckpointStore
from codegenie.workflows.vuln_ledger import TransitionEvent


def _event(payload: object, transition_id: str, workflow_id: str) -> TransitionEvent:
    return TransitionEvent(
        transition_id=TransitionId(transition_id),
        prior_state_id="needs_plan",
        next_state_id="plan_ready",
        triggering_outcome=payload,
        evidence_digest=BlobDigest("blake3:" + "c" * 64),
        chain_head=ChainHead("0" * 64),
        workflow_id=WorkflowId(workflow_id),
    )


def test_ac3_sqlite_secret_shape_does_not_trigger_chain_mismatch(tmp_path: Path) -> None:
    """A secret-shaped payload that triggers sanitization yields Verified, not ChainMismatch."""
    secret = "AKIA" + "X" * 16
    wf = "01HZZZZZZZZZZZZZZ22A0001WF"
    event = _event({"leaked": secret}, "01HZZZZZZZZZZZZZZ22A001001", wf)
    store = SqliteCheckpointStore(tmp_path)
    try:
        store.append(event)
        verdict = ReplayVerifier(store).verify(WorkflowId(wf))
        assert isinstance(verdict, Verified), (
            f"Sanitization triggered on a secret-shaped payload — verifier "
            f"misclassified as {verdict!r}. The fold MUST mirror the "
            f"write path by round-tripping through model_validate_json "
            f"(S2-02 AC-3)."
        )
    finally:
        store.close()


def test_ac3_in_memory_secret_shape_does_not_trigger_chain_mismatch(tmp_path: Path) -> None:
    secret = "AKIA" + "Y" * 16
    wf = "01HZZZZZZZZZZZZZZ22A0002WF"
    event = _event({"another_leak": secret}, "01HZZZZZZZZZZZZZZ22A002001", wf)
    store = InMemoryCheckpointStore(tmp_path)
    try:
        store.append(event)
        verdict = ReplayVerifier(store).verify(WorkflowId(wf))
        assert isinstance(verdict, Verified)
    finally:
        store.close()


def test_ac3_pure_fold_helper_returns_genesis_for_empty_iterable() -> None:
    """The pure helper returns ``genesis`` unchanged for an empty iterable."""
    from codegenie.workflows._replay import _replay_fold
    from codegenie.workflows.checkpoints import _GENESIS_CHAIN_HEAD

    assert _replay_fold([], genesis=_GENESIS_CHAIN_HEAD) == _GENESIS_CHAIN_HEAD


def test_ac3_pure_fold_helper_matches_sequence_application(tmp_path: Path) -> None:
    """The fold over a 3-event sequence equals the chained ``append() -> ChainHead``."""
    from codegenie.workflows._replay import _replay_fold
    from codegenie.workflows.checkpoints import _GENESIS_CHAIN_HEAD

    wf = "01HZZZZZZZZZZZZZZ22A0003WF"
    store = InMemoryCheckpointStore(tmp_path)
    try:
        events: list[TransitionEvent] = []
        head: ChainHead = _GENESIS_CHAIN_HEAD
        edges = [
            ("needs_plan", "plan_ready"),
            ("plan_ready", "patch_applied"),
            ("patch_applied", "completed"),
        ]
        for idx, (prior, nxt) in enumerate(edges):
            e = TransitionEvent(
                transition_id=TransitionId(f"01HZZZZZZZZZZZZZZ22A30100{idx:02d}"),
                prior_state_id=prior,  # type: ignore[arg-type]
                next_state_id=nxt,  # type: ignore[arg-type]
                triggering_outcome="ok",
                evidence_digest=BlobDigest("blake3:" + "d" * 64),
                chain_head=ChainHead("0" * 64),
                workflow_id=WorkflowId(wf),
            )
            events.append(e)
            head = store.append(e)
        folded = _replay_fold(events)
        assert folded == head
    finally:
        store.close()
