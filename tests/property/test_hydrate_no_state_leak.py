"""Phase 6 S2-02 AC-11 — fail-closed-before-hydrate property.

When verification fails, ``hydrate_or_fail`` returns ``FailedUnrecoverable``
WITHOUT materializing any non-terminal ledger-state variant in memory.
The orchestrator MUST construct the ledger state only after the
``Hydrated`` arm.

This is the load-bearing safety invariant of ADR-0003: "no patch work
resumes" after integrity failure. A verifier that pre-materializes
``NeedsPlan()`` or similar would let the subgraph run against corrupted
state.
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
from codegenie.workflows.replay import hydrate_or_fail
from codegenie.workflows.sqlite_checkpoints import SqliteCheckpointStore
from codegenie.workflows.vuln_ledger import (
    AwaitingHumanReview,
    Completed,
    FailedUnrecoverable,
    GateFailedRetryable,
    NeedsPlan,
    PatchApplied,
    PlanReady,
    TransitionEvent,
)


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


def test_ac11_failure_path_returns_only_failed_unrecoverable(tmp_path: Path) -> None:
    wf = "01HZZZZZZZZZZZZZZ22B001NOLEAK"
    store = SqliteCheckpointStore(tmp_path)
    try:
        store.append(_build("01HZZZZZZZZZZZZZZ22B00100A001", "needs_plan", "plan_ready", wf))
        store.append(_build("01HZZZZZZZZZZZZZZ22B00100A002", "plan_ready", "patch_applied", wf))
    finally:
        store.close()

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
        result = hydrate_or_fail(store2, WorkflowId(wf))
    finally:
        store2.close()
    # The failure-path return is the typed terminal — never a non-terminal variant.
    assert isinstance(result, FailedUnrecoverable)
    forbidden_types = (
        NeedsPlan,
        PlanReady,
        PatchApplied,
        GateFailedRetryable,
        AwaitingHumanReview,
        Completed,
    )
    assert not isinstance(result, forbidden_types)


def test_ac11_replay_module_constructs_no_non_terminal_ledger_states() -> None:
    """AST fence: replay.py constructs no NeedsPlan/PlanReady/... etc.

    The only ledger-state variant allowed is ``FailedUnrecoverable`` on
    the failed path. Hydrated arms return the typed ``Hydrated`` model
    carrying events, NOT a materialized ledger state.
    """
    import ast
    import inspect

    from codegenie.workflows import replay as replay_module

    forbidden_class_names = {
        "NeedsPlan",
        "PlanReady",
        "PatchApplied",
        "GateFailedRetryable",
        "AwaitingHumanReview",
        "Completed",
    }
    tree = ast.parse(inspect.getsource(replay_module))
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in forbidden_class_names:
                bad.append(f"{node.func.id}() @ line {node.lineno}")
    assert not bad, (
        "AC-11: replay.py constructs forbidden non-terminal ledger-state "
        "variants — the orchestrator owns ledger-state construction, not "
        "the verifier:\n  - " + "\n  - ".join(sorted(set(bad)))
    )
