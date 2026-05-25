"""Phase 6 S2-01 AC-9 — golden chain ordering for two scripted scenarios.

Scenario #1 — clean completion: needs_plan → plan_ready → patch_applied → completed.
Scenario #2 — retry-then-recovery: ... → gate_failed_retryable → needs_plan →
    plan_ready → patch_applied → completed.

The golden encodes the full ``(transition_id, prior_head, next_head)``
triple per row; regeneration requires
``PHASE6_CHECKPOINT_GOLDEN_REWRITE=1``. The clock is injected so
``written_at`` is deterministic.

On failure, the directive distinguishes additive (regenerate) from
breaking (ADR-0003 amendment + Phase-9 review).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    TransitionId,
    WorkflowId,
)
from codegenie.workflows.sqlite_checkpoints import SqliteCheckpointStore
from codegenie.workflows.vuln_ledger import TransitionEvent

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_PATH = _REPO_ROOT / "tests" / "golden" / "phase6-checkpoint" / "clean_completion_chain.json"
_REWRITE_FLAG = "PHASE6_CHECKPOINT_GOLDEN_REWRITE"

_FROZEN_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _frozen_clock() -> datetime:
    return _FROZEN_NOW


def _build(*, transition_id: str, prior: str, nxt: str, workflow_id: str) -> TransitionEvent:
    return TransitionEvent(
        transition_id=TransitionId(transition_id),
        prior_state_id=prior,  # type: ignore[arg-type]
        next_state_id=nxt,  # type: ignore[arg-type]
        triggering_outcome={"scenario": "golden"},
        evidence_digest=BlobDigest("blake3:" + "a" * 64),
        chain_head=ChainHead("0" * 64),
        workflow_id=WorkflowId(workflow_id),
    )


# Scenario #1 — clean completion. Four transitions; ``needs_plan`` is
# the initial state (no write) and the three following are all
# boundaries.
_SCENARIO_1_WF = "01HZZZZZZZZZZZZZZZZZZSCN001"
_SCENARIO_1: list[tuple[str, str, str]] = [
    ("01HZZZZZZZZZZZZZSCN001A001", "needs_plan", "plan_ready"),
    ("01HZZZZZZZZZZZZZSCN001A002", "plan_ready", "patch_applied"),
    ("01HZZZZZZZZZZZZZSCN001A003", "patch_applied", "completed"),
]


# Scenario #2 — retry-then-recovery. Six transitions; one
# ``patch_applied → gate_failed_retryable`` arm + one
# ``gate_failed_retryable → needs_plan`` (the only non-boundary
# transition target along this path). The test asserts the store sees
# only the FIVE boundary rows from this 6-transition path.
_SCENARIO_2_WF = "01HZZZZZZZZZZZZZZZZZZSCN002"
_SCENARIO_2_ALL: list[tuple[str, str, str]] = [
    ("01HZZZZZZZZZZZZZSCN002A001", "plan_ready", "patch_applied"),
    ("01HZZZZZZZZZZZZZSCN002A002", "patch_applied", "gate_failed_retryable"),
    # gate_failed_retryable → needs_plan is NOT a boundary write; the
    # orchestrator never invokes append() at this transition (needs_plan
    # is the only non-boundary LedgerStateKind today).
    ("01HZZZZZZZZZZZZZSCN002A003", "gate_failed_retryable", "needs_plan"),
    ("01HZZZZZZZZZZZZZSCN002A004", "needs_plan", "plan_ready"),
    ("01HZZZZZZZZZZZZZSCN002A005", "plan_ready", "patch_applied"),
    ("01HZZZZZZZZZZZZZSCN002A006", "patch_applied", "completed"),
]


def _directive() -> str:
    return (
        "Phase-6 checkpoint ordering drift. If additive (new field on "
        "TransitionEvent with a default, new serialization-affecting "
        "Pydantic config), regenerate the golden under "
        f"`{_REWRITE_FLAG}=1 pytest "
        "tests/integration/test_checkpoint_golden_ordering.py`. If "
        "breaking (re-orderable events, changed canonical-JSON shape, "
        "broken _compute_chain_head byte-stability), this is an ADR-0003 "
        "amendment + Phase-9 review (S5-01 Postgres adapter G5 "
        "byte-equality forward dep)."
    )


def _run_clean_completion(store: SqliteCheckpointStore) -> list[dict[str, Any]]:
    wf = WorkflowId(_SCENARIO_1_WF)
    chain: list[dict[str, Any]] = []
    for transition_id, prior, nxt in _SCENARIO_1:
        prior_head = store.tail_chain_head(wf)
        event = _build(
            transition_id=transition_id,
            prior=prior,
            nxt=nxt,
            workflow_id=_SCENARIO_1_WF,
        )
        next_head = store.append(event)
        chain.append(
            {
                "transition_id": transition_id,
                "prior_head": str(prior_head),
                "next_head": str(next_head),
                "prior_state_id": prior,
                "next_state_id": nxt,
            }
        )
    return chain


def test_ac9_clean_completion_golden(tmp_path: Path) -> None:
    """Scenario #1: clean completion produces a deterministic chain."""
    store = SqliteCheckpointStore(tmp_path, clock=_frozen_clock)
    try:
        actual = _run_clean_completion(store)
    finally:
        store.close()

    actual_payload: dict[str, Any] = {
        "scenario": "clean_completion",
        "workflow_id": _SCENARIO_1_WF,
        "chain": actual,
    }

    if os.environ.get(_REWRITE_FLAG) == "1":
        _GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        _GOLDEN_PATH.write_text(json.dumps(actual_payload, indent=2, sort_keys=True) + "\n")
        return
    assert _GOLDEN_PATH.exists(), _directive() + f" Missing: {_GOLDEN_PATH}"
    expected = json.loads(_GOLDEN_PATH.read_text())
    assert actual_payload == expected, _directive()


def test_ac9_retry_recovery_writes_only_boundaries(tmp_path: Path) -> None:
    """Scenario #2: only the FIVE boundary transitions hit the store.

    The non-boundary transition (gate_failed_retryable → needs_plan)
    must NOT be persisted; the orchestrator only calls ``append()`` on
    boundary edges (AC-4 contract).
    """
    store = SqliteCheckpointStore(tmp_path, clock=_frozen_clock)
    boundary_writes: list[tuple[str, str]] = []
    try:
        wf = WorkflowId(_SCENARIO_2_WF)
        for transition_id, prior, nxt in _SCENARIO_2_ALL:
            event = _build(
                transition_id=transition_id,
                prior=prior,
                nxt=nxt,
                workflow_id=_SCENARIO_2_WF,
            )
            from codegenie.workflows.checkpoints import _SEMANTIC_BOUNDARY_KINDS

            if nxt in _SEMANTIC_BOUNDARY_KINDS:
                store.append(event)
                boundary_writes.append((transition_id, nxt))

        # Five boundary writes, no needs_plan target.
        assert len(boundary_writes) == 5
        assert all(nxt != "needs_plan" for _t, nxt in boundary_writes)
        read_back = list(store.read_all_for_workflow(wf))
        assert len(read_back) == 5
        # Append order preserved.
        assert [e.transition_id for e in read_back] == [t for t, _n in boundary_writes]
    finally:
        store.close()
