"""Phase 6 S2-01 AC-11 — partial-write detection-substrate contract.

The most insidious failure mode for this substrate is an executor
"helpfully" adding chain recomputation inside ``tail_chain_head``. This
collapses the detection/policy separation ADR-0003 depends on — the
S2-02 replay verifier is the SOLE site of integrity decision; this
story is the SOLE site of substrate fidelity.

Property: after tampering with the SQLite ``next_head`` column on the
last row, ``tail_chain_head`` returns the *tampered* (wrong) value —
NOT a recomputed one. ``read_all_for_workflow`` yields the events
faithfully — integrity policing is the S2-02 verifier's job.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    TransitionId,
    WorkflowId,
)
from codegenie.workflows.sqlite_checkpoints import SqliteCheckpointStore
from codegenie.workflows.vuln_ledger import TransitionEvent


def _build(*, transition_id: str, prior: str, nxt: str, workflow_id: str) -> TransitionEvent:
    return TransitionEvent(
        transition_id=TransitionId(transition_id),
        prior_state_id=prior,  # type: ignore[arg-type]
        next_state_id=nxt,  # type: ignore[arg-type]
        triggering_outcome="ok",
        evidence_digest=BlobDigest("blake3:" + "a" * 64),
        chain_head=ChainHead("0" * 64),
        workflow_id=WorkflowId(workflow_id),
    )


_WF = "01HZZZZZZZZZZZZZZZZZZAC011"


def test_ac11_tail_chain_head_does_not_recompute(tmp_path: Path) -> None:
    """``tail_chain_head`` returns the persisted bytes, not a fresh fold."""
    store = SqliteCheckpointStore(tmp_path)
    try:
        # Append three legitimate events
        for tid, prior, nxt in [
            ("01HZZZZZZZZZZZZZZAC011A001", "needs_plan", "plan_ready"),
            ("01HZZZZZZZZZZZZZZAC011A002", "plan_ready", "patch_applied"),
            ("01HZZZZZZZZZZZZZZAC011A003", "patch_applied", "completed"),
        ]:
            store.append(_build(transition_id=tid, prior=prior, nxt=nxt, workflow_id=_WF))

        # Tamper with the last row's next_head directly via raw SQLite
        # (simulating a partial / torn write or a malicious edit).
        wf_dir = tmp_path / _WF
        conn = sqlite3.connect(str(wf_dir / "checkpoints.sqlite"))
        tampered_head = "deadbeef" * 8  # 64 hex chars but wrong
        conn.execute(
            "UPDATE checkpoint_chain SET next_head = ? "
            "WHERE sequence = (SELECT MAX(sequence) FROM checkpoint_chain)",
            (tampered_head,),
        )
        conn.commit()
        conn.close()

        # Re-open store (force fresh connection so the SELECT sees the
        # tampered row).
        store.close()
        store2 = SqliteCheckpointStore(tmp_path)
        try:
            head = store2.tail_chain_head(WorkflowId(_WF))
            # AC-11 contract: tail_chain_head returns whatever the substrate
            # persisted. NOT a recomputation.
            assert head == tampered_head, (
                "tail_chain_head must return the persisted value, not a "
                "recomputed one. Integrity policing belongs to S2-02; "
                "this store is detection-substrate-only."
            )
            # And read_all yields all four rows faithfully — integrity
            # policing is the verifier's, not the reader's.
            events = list(store2.read_all_for_workflow(WorkflowId(_WF)))
            assert len(events) == 3
        finally:
            store2.close()
    finally:
        store.close()


def test_ac11_null_event_bytes_surfaces_integrity_error(tmp_path: Path) -> None:
    """Raw NULL inserts must raise SQLite IntegrityError, not silently skip."""
    store = SqliteCheckpointStore(tmp_path)
    try:
        # Seed an empty per-workflow file via a single legitimate append.
        wf = "01HZZZZZZZZZZZZZZAC011B000"
        store.append(
            _build(
                transition_id="01HZZZZZZZZZZZZZZAC011B001",
                prior="needs_plan",
                nxt="plan_ready",
                workflow_id=wf,
            )
        )
        wf_dir = tmp_path / wf
        conn = sqlite3.connect(str(wf_dir / "checkpoints.sqlite"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO checkpoint_chain "
                "(transition_id, prior_head, next_head, event_bytes, written_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    "01HZZZZZZZZZZZZZZAC011B002",
                    "0" * 64,
                    "1" * 64,
                    None,
                    "2026-01-01T00:00:00+00:00",
                ),
            )
        conn.close()
    finally:
        store.close()
