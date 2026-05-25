"""Phase 6 S1-02 — AC-9: ``match`` + ``assert_never`` exhaustiveness.

If a future story adds an eighth variant without updating ``_describe``,
mypy --strict catches the missing ``case`` arm at typecheck time. The
runtime parametrize asserts every variant routes to its expected slug.

Replacing ``assert_never(unreachable)`` with ``return 'unknown'`` would
silently pass at runtime for an unhandled variant but fail
``make typecheck`` — the AC requires both runtime parametrize and
typecheck pass.
"""

from __future__ import annotations

from typing import assert_never

import pytest

from codegenie.workflows.vuln_ledger import (
    AwaitingHumanReview,
    Completed,
    FailedUnrecoverable,
    GateFailedRetryable,
    NeedsPlan,
    PatchApplied,
    PlanReady,
    VulnLedgerState,
)


def _describe(state: VulnLedgerState) -> str:
    match state:
        case NeedsPlan():
            return "needs_plan"
        case PlanReady():
            return "plan_ready"
        case PatchApplied():
            return "patch_applied"
        case GateFailedRetryable():
            return "gate_failed_retryable"
        case AwaitingHumanReview():
            return "awaiting_human_review"
        case Completed():
            return "completed"
        case FailedUnrecoverable():
            return "failed_unrecoverable"
        case _ as unreachable:
            assert_never(unreachable)


@pytest.mark.parametrize(
    "state,expected",
    [
        (NeedsPlan(), "needs_plan"),
        (PlanReady(plan_summary="p"), "plan_ready"),
        (PatchApplied(patch_digest="a" * 64), "patch_applied"),  # type: ignore[arg-type]
        (
            GateFailedRetryable(
                failing_signals=("x",),  # type: ignore[arg-type]
                attempt_number=1,  # type: ignore[arg-type]
            ),
            "gate_failed_retryable",
        ),
        (AwaitingHumanReview(review_reason="no_concrete_match"), "awaiting_human_review"),
        (Completed(), "completed"),
        (FailedUnrecoverable(reason="subgraph_aborted"), "failed_unrecoverable"),
    ],
)
def test_ac9_describe_routes_every_variant(state: VulnLedgerState, expected: str) -> None:
    assert _describe(state) == expected
