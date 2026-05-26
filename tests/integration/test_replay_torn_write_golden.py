"""Phase 6 S2-02 AC-10 — torn-write integration golden tests.

Unparseable event_bytes via raw SQLite UPDATE to truncated JSON. The
verifier classifies as TornWrite(reason="unparseable_event"); the
``hydrate_or_fail`` gate maps to FailedUnrecoverable with the typed
integrity error_id.
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


def _seed_one_row(tmp_path: Path, wf: str) -> Path:
    store = SqliteCheckpointStore(tmp_path)
    try:
        store.append(
            TransitionEvent(
                transition_id=TransitionId("01HZZZZZZZZZZZZZZ22A00100A001"),
                prior_state_id="needs_plan",
                next_state_id="plan_ready",
                triggering_outcome="ok",
                evidence_digest=BlobDigest("blake3:" + "a" * 64),
                chain_head=ChainHead("0" * 64),
                workflow_id=WorkflowId(wf),
            )
        )
    finally:
        store.close()
    return tmp_path / wf / "checkpoints.sqlite"


def test_ac10_truncated_event_bytes_yields_failed_unrecoverable(tmp_path: Path) -> None:
    wf = "01HZZZZZZZZZZZZZZ22A001UNPARS"
    db_path = _seed_one_row(tmp_path, wf)
    conn = sqlite3.connect(str(db_path))
    conn.execute("UPDATE checkpoint_chain SET event_bytes = ? WHERE sequence = 1", (b'{"trunc',))
    conn.commit()
    conn.close()

    store = SqliteCheckpointStore(tmp_path)
    try:
        result = hydrate_or_fail(store, WorkflowId(wf))
    finally:
        store.close()

    assert isinstance(result, FailedUnrecoverable)
    assert result.reason == "checkpoint_integrity"
    assert result.error is not None
    assert str(result.error.error_id) == str(_INTEGRITY_ERROR_ID)
    assert "torn_write" in result.error.message
    assert "unparseable_event" in result.error.message


def test_ac10_schema_incompatible_payload_yields_failed_unrecoverable(tmp_path: Path) -> None:
    """A valid JSON object that isn't a TransitionEvent shape also classifies as unparseable."""
    wf = "01HZZZZZZZZZZZZZZ22A002NOTEVT"
    db_path = _seed_one_row(tmp_path, wf)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE checkpoint_chain SET event_bytes = ? WHERE sequence = 1",
        (b'{"not": "a transition event"}',),
    )
    conn.commit()
    conn.close()

    store = SqliteCheckpointStore(tmp_path)
    try:
        result = hydrate_or_fail(store, WorkflowId(wf))
    finally:
        store.close()

    assert isinstance(result, FailedUnrecoverable)
    assert result.reason == "checkpoint_integrity"
    assert result.error is not None
    assert "unparseable_event" in result.error.message
