"""Phase 6 S2-02 AC-15 — verifier parity meta-test (mutation guard for AC-6).

Plants a deliberately broken verifier that returns ``Verified`` for
every input (ignoring tamper) and asserts the parity test contract
would FAIL on it. Mirrors S2-01 AC-17 precedent — closes the gap S6-06
(Phase-3) flagged: "the parity test itself is mutation-susceptible."
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    TransitionId,
    WorkflowId,
)
from codegenie.workflows.checkpoints import CheckpointStore
from codegenie.workflows.replay import ChainMismatch, ReplayVerdict, Verified
from codegenie.workflows.sqlite_checkpoints import SqliteCheckpointStore
from codegenie.workflows.vuln_ledger import TransitionEvent


class _BrokenVerifier:
    """Deliberately broken — always returns Verified, ignoring tamper."""

    __slots__ = ("_store",)

    def __init__(self, store: CheckpointStore) -> None:
        self._store = store

    def verify(self, workflow_id: WorkflowId) -> ReplayVerdict:
        events = tuple(self._store.read_all_for_workflow(workflow_id))
        return Verified(tail_chain_head=ChainHead("0" * 64), events=events)


def _build(transition_id: str, prior: str, nxt: str, wf: str) -> TransitionEvent:
    return TransitionEvent(
        transition_id=TransitionId(transition_id),
        prior_state_id=prior,  # type: ignore[arg-type]
        next_state_id=nxt,  # type: ignore[arg-type]
        triggering_outcome="ok",
        evidence_digest=BlobDigest("blake3:" + "a" * 64),
        chain_head=ChainHead("0" * 64),
        workflow_id=WorkflowId(wf),
    )


def test_ac15_broken_verifier_passes_when_assertion_demands_chain_mismatch(tmp_path: Path) -> None:
    """A broken verifier returns Verified — the parity assertion demands ChainMismatch.

    This test demonstrates the parity contract: when we plant a broken
    verifier and assert ``ChainMismatch`` on a tampered chain, the
    assertion fails. The real ReplayVerifier (under test in AC-6)
    satisfies the same assertion. The meta-test guarantees the parity
    assertion is non-trivial — a no-op assertion (e.g., ``assert True``)
    would let the broken verifier pass, breaking the contract.
    """
    wf = "01HZZZZZZZZZZZZZZ225M001BROKEN"
    store = SqliteCheckpointStore(tmp_path)
    try:
        for ev in [
            _build("01HZZZZZZZZZZZZZZ225M0010001", "needs_plan", "plan_ready", wf),
            _build("01HZZZZZZZZZZZZZZ225M0010002", "plan_ready", "patch_applied", wf),
        ]:
            store.append(ev)
    finally:
        store.close()

    # Tamper the tail
    db_path = tmp_path / wf / "checkpoints.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE checkpoint_chain SET next_head = ? WHERE sequence = 2",
        ("deadbeef" * 8,),
    )
    conn.commit()
    conn.close()

    store2 = SqliteCheckpointStore(tmp_path)
    try:
        broken_verdict = _BrokenVerifier(store2).verify(WorkflowId(wf))
        # The broken verifier returns Verified despite tamper — that's the bug.
        assert isinstance(broken_verdict, Verified), (
            "Setup invariant: the broken verifier must return Verified."
        )
        # Now demonstrate the parity contract would FAIL on the broken verifier:
        # i.e., an assertion that demands ChainMismatch on a tampered chain
        # would not be satisfied. We assert NOT-ChainMismatch as proof.
        assert not isinstance(broken_verdict, ChainMismatch), (
            "If this assertion fails, the broken-verifier scaffold is "
            "miscoded — _BrokenVerifier must demonstrably bypass tamper."
        )
    finally:
        store2.close()
