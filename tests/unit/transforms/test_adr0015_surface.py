"""ADR-0015 additive surfaces consumed by S6-04."""

from __future__ import annotations

from codegenie.plugins.subgraph import SubgraphState
from codegenie.transforms import (
    HumanReviewReason,
    NotApplicableReason,
    StageOutcome,
    TrustOutcome,
)
from codegenie.types.identifiers import WorkflowId


def test_stage_outcome_aliases_trust_outcome() -> None:
    assert StageOutcome is TrustOutcome


def test_subgraph_state_has_adr0015_slots() -> None:
    state = SubgraphState(workflow_id=WorkflowId("wf-adr0015"), cve="CVE-2024-21501")

    assert state.installed_dependencies == ()
    assert state.vulnerability_record is None
    assert state.application_plan is None
    assert state.apply_context is None


def test_adr0015_reason_literals_are_importable() -> None:
    not_applicable: NotApplicableReason = "CVE_NOT_IN_DEPENDENCY_SET"
    review: HumanReviewReason = "MULTI_PACKAGE_CVE"

    assert not_applicable == "CVE_NOT_IN_DEPENDENCY_SET"
    assert review == "MULTI_PACKAGE_CVE"
