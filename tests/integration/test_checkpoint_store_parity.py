"""Phase 6 S2-01 AC-6 — adapter parity contract.

Both adapters must satisfy the :class:`CheckpointStore` Protocol such
that, given byte-equal inputs, they produce byte-equal outputs:

* identical ``append() -> ChainHead`` return values;
* identical ``tail_chain_head(wf)`` results;
* identical ``read_all_for_workflow(wf)`` sequences.

The parametrize-over-factory shape lets Phase 9 add a Postgres adapter
without editing this file — just join the factory list.

The companion AC-17 meta-test
(``tests/integration/test_checkpoint_store_parity_meta.py``) plants a
deliberately broken adapter and asserts these tests FAIL on it,
guarding against future ``==``→``!=`` mutation in the equality
assertions.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    TransitionId,
    WorkflowId,
)
from codegenie.workflows.checkpoints import _GENESIS_CHAIN_HEAD, CheckpointStore
from codegenie.workflows.in_memory_checkpoints import InMemoryCheckpointStore
from codegenie.workflows.sqlite_checkpoints import SqliteCheckpointStore
from codegenie.workflows.vuln_ledger import TransitionEvent

ADAPTER_FACTORIES: list[Callable[[Path], CheckpointStore]] = [
    InMemoryCheckpointStore,
    SqliteCheckpointStore,
]
ADAPTER_FACTORY_IDS = ["in_memory", "sqlite"]


def _build_event(
    *,
    transition_id: str,
    prior: str,
    nxt: str,
    workflow_id: str,
    payload: dict | str = "ok",
) -> TransitionEvent:
    return TransitionEvent(
        transition_id=TransitionId(transition_id),
        prior_state_id=prior,  # type: ignore[arg-type]
        next_state_id=nxt,  # type: ignore[arg-type]
        triggering_outcome=payload,
        evidence_digest=BlobDigest("blake3:" + "a" * 64),
        chain_head=ChainHead("0" * 64),
        workflow_id=WorkflowId(workflow_id),
    )


_CLEAN_SEQUENCE: list[tuple[str, str, str]] = [
    # (transition_id, prior_state_id, next_state_id)
    ("01HZZZZZZZZZZZZZZZZZZZZ001", "needs_plan", "plan_ready"),
    ("01HZZZZZZZZZZZZZZZZZZZZ002", "plan_ready", "patch_applied"),
    ("01HZZZZZZZZZZZZZZZZZZZZ003", "patch_applied", "completed"),
]


def _run_sequence(
    store: CheckpointStore, workflow_id: str
) -> tuple[ChainHead, list[TransitionEvent]]:
    """Append the clean-completion sequence; return final head + read-back list."""
    head: ChainHead = ChainHead("0" * 64)
    for transition_id, prior, nxt in _CLEAN_SEQUENCE:
        event = _build_event(
            transition_id=transition_id,
            prior=prior,
            nxt=nxt,
            workflow_id=workflow_id,
        )
        head = store.append(event)
    read_back = list(store.read_all_for_workflow(WorkflowId(workflow_id)))
    return head, read_back


@pytest.mark.parametrize("store_factory", ADAPTER_FACTORIES, ids=ADAPTER_FACTORY_IDS)
def test_ac6_genesis_tail_is_identical_across_adapters(
    store_factory: Callable[[Path], CheckpointStore], tmp_path: Path
) -> None:
    """Empty workflow tail must equal the genesis constant."""
    store = store_factory(tmp_path)
    try:
        wf = WorkflowId("01HZZZZZZZZZZZZZZZZZZZZZAA")
        assert store.tail_chain_head(wf) == _GENESIS_CHAIN_HEAD
    finally:
        store.close()


def test_ac6_clean_completion_byte_equal_between_adapters(tmp_path: Path) -> None:
    """SAME inputs ⇒ SAME ``append()`` chain head, SAME read-back sequence.

    The single canonical assertion that the Protocol *is* the contract:
    a buggy adapter that uses ``hash()`` instead of ``_compute_chain_head``
    fails byte-loud here.
    """
    mem_root = tmp_path / "mem"
    sql_root = tmp_path / "sql"
    mem_root.mkdir()
    sql_root.mkdir()
    mem = InMemoryCheckpointStore(mem_root)
    sql = SqliteCheckpointStore(sql_root)
    try:
        wf = "01HZZZZZZZZZZZZZZZZZZZZZBB"
        mem_head, mem_reads = _run_sequence(mem, wf)
        sql_head, sql_reads = _run_sequence(sql, wf)
        # Final chain heads must match byte-for-byte.
        assert mem_head == sql_head, (
            f"Adapter parity violation: mem={mem_head!r} sql={sql_head!r}. "
            "The Protocol IS the contract — adapters must agree."
        )
        # Tail reads must agree.
        assert mem.tail_chain_head(WorkflowId(wf)) == sql.tail_chain_head(WorkflowId(wf))
        # Read-back sequences must be byte-identical.
        assert mem_reads == sql_reads
        assert len(mem_reads) == 3
    finally:
        mem.close()
        sql.close()
