"""Phase 6 S2-02 AC-6 — verifier parity contract across both adapters.

The verdict shape (kind, divergence_index, offending_transition_id)
MUST match byte-for-byte across InMemoryCheckpointStore and
SqliteCheckpointStore for the same logical tamper. Adapter-specific
read-path shortcuts would surface here as adapter-divergent verdicts.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    TransitionId,
    WorkflowId,
)
from codegenie.workflows.checkpoints import CheckpointStore
from codegenie.workflows.in_memory_checkpoints import InMemoryCheckpointStore
from codegenie.workflows.replay import (
    ChainMismatch,
    EmptyWorkflow,
    ReplayVerifier,
    Verified,
)
from codegenie.workflows.sqlite_checkpoints import SqliteCheckpointStore
from codegenie.workflows.vuln_ledger import TransitionEvent

ADAPTER_FACTORIES: list[Callable[[Path], CheckpointStore]] = [
    InMemoryCheckpointStore,
    SqliteCheckpointStore,
]
ADAPTER_FACTORY_IDS = ["in_memory", "sqlite"]


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


@pytest.mark.parametrize("store_factory", ADAPTER_FACTORIES, ids=ADAPTER_FACTORY_IDS)
def test_ac6_empty_workflow_verdict_byte_equal(
    store_factory: Callable[[Path], CheckpointStore], tmp_path: Path
) -> None:
    store = store_factory(tmp_path)
    try:
        wf = WorkflowId("01HZZZZZZZZZZZZZZ226A001EMPTY")
        verdict = ReplayVerifier(store).verify(wf)
        assert isinstance(verdict, EmptyWorkflow)
        assert verdict.genesis_chain_head == ChainHead("0" * 64)
    finally:
        store.close()


@pytest.mark.parametrize("store_factory", ADAPTER_FACTORIES, ids=ADAPTER_FACTORY_IDS)
def test_ac6_clean_sequence_verified_across_adapters(
    store_factory: Callable[[Path], CheckpointStore], tmp_path: Path
) -> None:
    store = store_factory(tmp_path)
    wf = "01HZZZZZZZZZZZZZZ226A002CLEAN"
    try:
        events = [
            _e("01HZZZZZZZZZZZZZZ22600200001", "needs_plan", "plan_ready", wf),
            _e("01HZZZZZZZZZZZZZZ22600200002", "plan_ready", "patch_applied", wf),
            _e("01HZZZZZZZZZZZZZZ22600200003", "patch_applied", "completed", wf),
        ]
        for ev in events:
            store.append(ev)
        verdict = ReplayVerifier(store).verify(WorkflowId(wf))
        assert isinstance(verdict, Verified)
        assert verdict.events == tuple(events)
    finally:
        store.close()


def _tamper_in_memory(store: InMemoryCheckpointStore, wf: str, index: int) -> None:
    log = store._log[WorkflowId(wf)]
    log[index] = (ChainHead("deadbeef" * 8), log[index][1])


def _tamper_sqlite(tmp_path: Path, wf: str, sequence: int) -> None:
    db = tmp_path / wf / "checkpoints.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE checkpoint_chain SET next_head = ? WHERE sequence = ?",
        ("deadbeef" * 8, sequence),
    )
    conn.commit()
    conn.close()


def test_ac6_tail_tamper_yields_byte_equal_chain_mismatch(tmp_path: Path) -> None:
    """Both adapters must report ChainMismatch at the same divergence_index."""
    wf = "01HZZZZZZZZZZZZZZ226A003TAMP"
    events = [
        _e("01HZZZZZZZZZZZZZZ22600300001", "needs_plan", "plan_ready", wf),
        _e("01HZZZZZZZZZZZZZZ22600300002", "plan_ready", "patch_applied", wf),
        _e("01HZZZZZZZZZZZZZZ22600300003", "patch_applied", "completed", wf),
    ]
    mem_root = tmp_path / "mem"
    sql_root = tmp_path / "sql"
    mem_root.mkdir()
    sql_root.mkdir()
    mem = InMemoryCheckpointStore(mem_root)
    sql = SqliteCheckpointStore(sql_root)
    try:
        for ev in events:
            mem.append(ev)
            sql.append(ev)
        _tamper_in_memory(mem, wf, index=2)
        # SQLite sequence is 1-indexed (AUTOINCREMENT starts at 1).
        # Tamper the third row (sequence = 3).
        sql.close()
        _tamper_sqlite(sql_root, wf, sequence=3)
        sql = SqliteCheckpointStore(sql_root)

        mem_verdict = ReplayVerifier(mem).verify(WorkflowId(wf))
        sql_verdict = ReplayVerifier(sql).verify(WorkflowId(wf))
        assert isinstance(mem_verdict, ChainMismatch)
        assert isinstance(sql_verdict, ChainMismatch)
        # Same divergence index across adapters.
        assert mem_verdict.divergence_index == sql_verdict.divergence_index == 2
        # Same offending transition id.
        expected_tid = events[2].transition_id
        assert mem_verdict.offending_transition_id == expected_tid
        assert sql_verdict.offending_transition_id == expected_tid
    finally:
        mem.close()
        sql.close()
