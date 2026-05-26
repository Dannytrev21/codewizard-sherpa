"""Phase 6 S2-02 AC-9 — Scenario #4 tamper integration golden.

Runs the clean-completion sequence, tampers the second row's next_head
via raw SQLite, calls hydrate_or_fail, asserts FailedUnrecoverable with
the right reason / error_id / message substrings. Embodies
phase-arch-design.md §"Scenarios" #4 verbatim.
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
from codegenie.workflows.replay import (
    _INTEGRITY_ERROR_ID,
    hydrate_or_fail,
)
from codegenie.workflows.sqlite_checkpoints import SqliteCheckpointStore
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


def test_ac9_middle_row_tamper_yields_typed_integrity_failure(tmp_path: Path) -> None:
    wf = "01HZZZZZZZZZZZZZZ229A001TAMPMID"
    events = [
        _e("01HZZZZZZZZZZZZZZ22900100001", "needs_plan", "plan_ready", wf),
        _e("01HZZZZZZZZZZZZZZ22900100002", "plan_ready", "patch_applied", wf),
        _e("01HZZZZZZZZZZZZZZ22900100003", "patch_applied", "completed", wf),
    ]
    store = SqliteCheckpointStore(tmp_path)
    try:
        for ev in events:
            store.append(ev)
    finally:
        store.close()

    # Raw-SQLite tamper of the middle row (sequence=2).
    db_path = tmp_path / wf / "checkpoints.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE checkpoint_chain SET next_head = ? WHERE sequence = ?",
        ("deadbeef" * 8, 2),
    )
    conn.commit()
    conn.close()

    store2 = SqliteCheckpointStore(tmp_path)
    try:
        result = hydrate_or_fail(store2, WorkflowId(wf))
    finally:
        store2.close()

    assert isinstance(result, FailedUnrecoverable)
    assert result.reason == "checkpoint_integrity"
    assert result.error is not None
    assert str(result.error.error_id) == str(_INTEGRITY_ERROR_ID)
    # The message names the middle-tamper index AND the offending transition id.
    assert "divergence_index=1" in result.error.message, (
        f"AC-9: expected middle-tamper to surface divergence_index=1; got "
        f"message={result.error.message!r}. A back-to-front verifier would "
        f"report index 2 (the tail) instead."
    )
    assert events[1].transition_id in result.error.message
