"""S6-08 fence — keep ``AttemptAnchor.plan_proposal_kind`` synced with
the discriminator tags of :data:`PlanProposal`'s discriminated union.

Without this fence, adding a 5th variant to :data:`PlanProposal` in a
later phase (e.g., Phase 7 distroless) silently drifts the anchor — the
JSONL projection would carry the new kind as a string but the anchor's
``Literal[...]`` would reject it at load time. This fence makes the
extension machine-enforced (add the variant ⇒ this test fails until the
anchor's literal is widened).
"""

from __future__ import annotations

from typing import get_args

from codegenie.fallback.attempt_anchor import AttemptAnchor
from codegenie.fallback.plan_proposal import (
    PlanProposalCallsiteRewrite,
    PlanProposalDepBump,
    PlanProposalOverride,
    PlanProposalRefuse,
)


def test_plan_proposal_kind_literal_equals_plan_proposal_union_tags() -> None:
    """The set of ``Literal`` members on ``plan_proposal_kind`` MUST equal
    the set of discriminator tags on :data:`PlanProposal`'s union."""
    anchor_tags = set(get_args(AttemptAnchor.model_fields["plan_proposal_kind"].annotation))
    proposal_tags = {
        get_args(PlanProposalDepBump.model_fields["kind"].annotation)[0],
        get_args(PlanProposalOverride.model_fields["kind"].annotation)[0],
        get_args(PlanProposalCallsiteRewrite.model_fields["kind"].annotation)[0],
        get_args(PlanProposalRefuse.model_fields["kind"].annotation)[0],
    }
    assert anchor_tags == proposal_tags, (
        f"AttemptAnchor.plan_proposal_kind {anchor_tags!r} != "
        f"PlanProposal union tags {proposal_tags!r}; "
        f"widen the Literal or add the missing variant."
    )
