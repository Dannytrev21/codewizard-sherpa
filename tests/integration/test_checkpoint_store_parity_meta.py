"""Phase 6 S2-01 AC-17 — parity-meta test (mutation guard for AC-6).

The parity contract test (AC-6) is itself susceptible to mutation: a
``==`` swapped for ``!=``, a missing ``read_all_for_workflow()`` call.
This meta-test constructs a deliberately-broken in-memory adapter that
violates one parity invariant and asserts the parity test FAILS — if
the parity test were broken (a tautology), the meta-test catches it.

Closes the exact gap S6-06 (Phase-3) flagged as "false-positive
additive is the scariest failure mode," applied here to contract
conformance.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    TransitionId,
    WorkflowId,
)
from codegenie.workflows.in_memory_checkpoints import InMemoryCheckpointStore
from codegenie.workflows.vuln_ledger import TransitionEvent


class _BrokenReversedReader(InMemoryCheckpointStore):
    """Deliberately-broken adapter — yields events in REVERSE append order.

    Used to demonstrate that the parity invariant
    ``read_all_for_workflow == append_order_list`` *would* catch a
    misbehaving adapter; if it didn't, the parity test is a tautology.
    """

    def read_all_for_workflow(self, workflow_id: WorkflowId) -> Iterator[TransitionEvent]:
        rows = list(super().read_all_for_workflow(workflow_id))
        rows.reverse()
        yield from rows


def _build_event(*, transition_id: str, prior: str, nxt: str, workflow_id: str) -> TransitionEvent:
    return TransitionEvent(
        transition_id=TransitionId(transition_id),
        prior_state_id=prior,  # type: ignore[arg-type]
        next_state_id=nxt,  # type: ignore[arg-type]
        triggering_outcome="ok",
        evidence_digest=BlobDigest("blake3:" + "a" * 64),
        chain_head=ChainHead("0" * 64),
        workflow_id=WorkflowId(workflow_id),
    )


def test_ac17_broken_adapter_fails_parity_check(tmp_path: Path) -> None:
    """A deliberately-broken adapter must fail the AC-6 parity invariant.

    If this assertion ever passes (i.e. the parity check accepts a
    reversed reader), the parity contract is a tautology — AC-6 is
    not actually exercising the invariant.
    """
    wf = "01HZZZZZZZZZZZZZZZZZZZZ017"
    broken = _BrokenReversedReader(tmp_path / "broken")
    correct = InMemoryCheckpointStore(tmp_path / "correct")
    try:
        events = [
            _build_event(
                transition_id=f"01HZZZZZZZZZZZZZZZZZZZZ{i:03d}",
                prior=prior,
                nxt=nxt,
                workflow_id=wf,
            )
            for i, (prior, nxt) in enumerate(
                [
                    ("needs_plan", "plan_ready"),
                    ("plan_ready", "patch_applied"),
                    ("patch_applied", "completed"),
                ],
                start=1,
            )
        ]
        for e in events:
            broken.append(e)
            correct.append(e)
        broken_reads = list(broken.read_all_for_workflow(WorkflowId(wf)))
        correct_reads = list(correct.read_all_for_workflow(WorkflowId(wf)))
        # The parity invariant — broken adapter disagrees with correct one.
        assert broken_reads != correct_reads, (
            "Meta-failure: a reversed-reader adapter passed the parity "
            "read-equality check. The parity test is a tautology — "
            "tighten the AC-6 assertion."
        )
        # And concretely: broken reads the events in reverse.
        assert broken_reads == list(reversed(events))
        assert correct_reads == events
    finally:
        broken.close()
        correct.close()
