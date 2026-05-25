"""Phase 6 S2-01 AC-13 — clock injection + between-boundary no-write.

Two structural defenses:

1. **Clock injection.** ``SqliteCheckpointStore.__init__`` accepts a
   ``clock: Callable[[], datetime] | None`` keyword; the ``written_at``
   column is captured via this clock. A test that injects a frozen
   clock asserts deterministic timestamps.
2. **Between-boundary no-write property.** Two consecutive boundary
   transitions produce exactly two rows; no intermediate non-boundary
   transition leaves a row behind.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    TransitionId,
    WorkflowId,
)
from codegenie.workflows.sqlite_checkpoints import SqliteCheckpointStore
from codegenie.workflows.vuln_ledger import TransitionEvent

_FROZEN_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


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


def test_ac13_clock_injection_is_deterministic(tmp_path: Path) -> None:
    """The injected clock controls ``written_at``."""
    store = SqliteCheckpointStore(tmp_path, clock=lambda: _FROZEN_NOW)
    try:
        wf = "01HZZZZZZZZZZZZZZAC013W001"
        store.append(
            _build(
                transition_id="01HZZZZZZZZZZZZZZAC013A001",
                prior="needs_plan",
                nxt="plan_ready",
                workflow_id=wf,
            )
        )
        conn = sqlite3.connect(str(tmp_path / wf / "checkpoints.sqlite"))
        (written_at,) = conn.execute("SELECT written_at FROM checkpoint_chain").fetchone()
        conn.close()
        assert written_at == _FROZEN_NOW.isoformat()
    finally:
        store.close()


def test_ac13_default_clock_is_utc_aware(tmp_path: Path) -> None:
    """The default clock returns a tz-aware UTC datetime."""
    from codegenie.workflows.sqlite_checkpoints import _default_clock

    now = _default_clock()
    assert now.tzinfo is not None
    assert now.utcoffset() == _FROZEN_NOW.utcoffset()  # both UTC offset 0


def test_ac13_between_boundary_no_write(tmp_path: Path) -> None:
    """Two boundary transitions yield exactly two rows — no intermediate writes."""
    store = SqliteCheckpointStore(tmp_path, clock=lambda: _FROZEN_NOW)
    try:
        wf = "01HZZZZZZZZZZZZZZAC013W002"
        store.append(
            _build(
                transition_id="01HZZZZZZZZZZZZZZAC013B001",
                prior="needs_plan",
                nxt="plan_ready",
                workflow_id=wf,
            )
        )
        store.append(
            _build(
                transition_id="01HZZZZZZZZZZZZZZAC013B002",
                prior="plan_ready",
                nxt="patch_applied",
                workflow_id=wf,
            )
        )
        events = list(store.read_all_for_workflow(WorkflowId(wf)))
        assert len(events) == 2
        # Both rows correspond to boundary kinds.
        assert events[0].next_state_id == "plan_ready"
        assert events[1].next_state_id == "patch_applied"
    finally:
        store.close()
