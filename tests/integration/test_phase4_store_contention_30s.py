"""Phase-4 S4-03 AC-8 — short contention test.

The full ``asyncio.gather`` two-coroutine + monotonic-chain-head test is
S4-08; this story ships the shorter pin that catches the simplest
regression: someone removes the ``try/finally`` from
:meth:`ChromaPersistentStore.add` and the lock leaks; the ``locked()``
assertion below catches it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.rag.errors import StoreWriteContention
from codegenie.rag.store import (
    ChromaPersistentStore,
    SolvedExampleWriteCapability,
)
from codegenie.types.identifiers import WorkflowId
from tests.fixtures.rag.fake_solved_example import make_solved_example


async def test_store_write_contention_30s_short_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Single-knob squeeze: ``_ADD_LOCK_TIMEOUT_SECONDS`` → 0.05s.

    Confirms the timeout path raises :class:`StoreWriteContention` with
    the right ``workflow_id`` and that the timed-out ``add`` did not
    leak ownership of the lock.
    """
    monkeypatch.setattr("codegenie.rag.store._ADD_LOCK_TIMEOUT_SECONDS", 0.05)
    store = ChromaPersistentStore(root_dir=tmp_path)
    # AC-2-test-only-direct-construction — S4-06 ships the mint.
    cap = SolvedExampleWriteCapability(workflow_id=WorkflowId("wf-contention"))
    example = make_solved_example(id_="ex-contention")

    await store._add_lock.acquire()
    try:
        with pytest.raises(StoreWriteContention) as exc_info:
            await store.add(example, cap)
        assert exc_info.value.workflow_id == WorkflowId("wf-contention")
    finally:
        store._add_lock.release()
    assert store._add_lock.locked() is False
    store.close()
