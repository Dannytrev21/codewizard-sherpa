"""Phase-4 S6-03 AC-6 + AC-9 — pure harvest-helper tests.

Covers the three pure helpers landed in S6-03 prep:

* :func:`harvest_eligibility` — exhaustive ``match`` over the
  four-variant :data:`PlanOutcome` union; only ``AppliedFromLlm`` is
  eligible.
* :func:`skip_reason_for` — projection of a failing :class:`TrustOutcome`
  into the closed-set ``HarvestSkipped.reason`` Literal.
* :func:`_validated_outcome_from` — pure ``(AppliedFromLlm, PostValidationContext)
  → ValidatedPlanOutcome`` projection; ``mypy --strict`` rejects any
  other :data:`PlanOutcome` variant at the callsite.
"""

from __future__ import annotations

from codegenie.fallback.plan_outcome import (
    AppliedFromLlm,
    AppliedFromRecipe,
    RagOnlyApplicable,
    Refused,
)
from codegenie.fallback.plan_proposal import PlanProposalDepBump
from codegenie.fallback.post_validation_context import PostValidationContext
from codegenie.fallback.tier import (
    HarvestEligibility,
    _validated_outcome_from,
    harvest_eligibility,
    skip_reason_for,
)
from codegenie.transforms.outcomes import TrustOutcome
from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    CveId,
    Language,
    LeafResponseId,
    PackageId,
    SemverVersion,
    SignalKind,
    SolvedExampleId,
    TaskClassId,
    WorkflowId,
)

# --- AC-6: harvest_eligibility exhaustiveness ------------------------------


def test_ac6_applied_from_llm_is_eligible() -> None:
    outcome = AppliedFromLlm(
        recipe_outcome_digest=BlobDigest("0" * 64),
        few_shot_ref=None,
        response_id=LeafResponseId("resp-001"),
    )
    assert harvest_eligibility(outcome) == HarvestEligibility(eligible=True)


def test_ac6_applied_from_recipe_is_not_eligible() -> None:
    outcome = AppliedFromRecipe(recipe_outcome_digest=BlobDigest("0" * 64))
    assert harvest_eligibility(outcome) == HarvestEligibility(eligible=False)


def test_ac6_rag_only_applicable_is_not_eligible() -> None:
    outcome = RagOnlyApplicable(few_shot_ref=SolvedExampleId("ex-001"))
    assert harvest_eligibility(outcome) == HarvestEligibility(eligible=False)


def test_ac6_refused_is_not_eligible() -> None:
    outcome = Refused(reason="LEAF_REFUSED")
    assert harvest_eligibility(outcome) == HarvestEligibility(eligible=False)


# --- skip_reason_for projection -------------------------------------------


def _trust(*, passed: bool, confidence: str) -> TrustOutcome:
    failing: tuple[SignalKind, ...] = () if passed else (SignalKind("test.failure"),)
    return TrustOutcome(
        passed=passed,
        confidence=confidence,  # type: ignore[arg-type]
        signals=(),
        failing=failing,
    )


def test_skip_reason_trust_failed_takes_precedence() -> None:
    """Both clauses failed → ``trust_failed`` wins (more fundamental)."""
    assert skip_reason_for(_trust(passed=False, confidence="degraded")) == "trust_failed"


def test_skip_reason_passed_with_degraded_confidence() -> None:
    """Clause 1 OK, clause 2 failed → ``low_confidence``."""
    assert skip_reason_for(_trust(passed=True, confidence="degraded")) == "low_confidence"


def test_skip_reason_passed_high_is_a_caller_bug() -> None:
    """Caller invariant: only invoke ``skip_reason_for`` when the gate
    rejected. If both clauses pass we fall through to ``low_confidence``
    by the default branch — documents the caller-contract precondition.
    """
    # Both clauses pass — this code path isn't reached at runtime, but
    # the helper still returns a valid Literal so mypy --strict stays
    # clean on the return-type.
    assert skip_reason_for(_trust(passed=True, confidence="high")) == "low_confidence"


# --- _validated_outcome_from projection -----------------------------------


def _ctx() -> PostValidationContext:
    plan = PlanProposalDepBump(
        manifest_path="package.json",
        package=PackageId("a@1.0.0"),
        target_version=SemverVersion("1.0.1"),
        rationale="patch",
    )
    return PostValidationContext(
        workflow_id=WorkflowId("wf-validated-001"),
        chain_head=ChainHead("a" * 64),
        advisory_digest=BlobDigest("1" * 64),
        cve_id=CveId("CVE-2026-9999"),
        task_class=TaskClassId("vuln_remediation"),
        language=Language("typescript"),
        build_system="npm",
        transform_digest=BlobDigest("2" * 64),
        trust_outcome_digest=BlobDigest("3" * 64),
        query_text="fix the cve",
        plan_proposal=plan,
    )


def test_ac9_validated_outcome_from_projects_every_field() -> None:
    """Every required ``ValidatedPlanOutcome`` field is populated from
    the context + the outcome's response_id."""
    outcome = AppliedFromLlm(
        recipe_outcome_digest=BlobDigest("0" * 64),
        few_shot_ref=None,
        response_id=LeafResponseId("resp-projection"),
    )
    context = _ctx()
    validated = _validated_outcome_from(outcome=outcome, context=context)
    assert validated.query_text == context.query_text
    assert validated.cve_id == context.cve_id
    assert validated.transform_digest == context.transform_digest
    assert validated.trust_outcome_digest == context.trust_outcome_digest
    assert validated.task_class == context.task_class
    assert validated.language == context.language
    assert validated.build_system == context.build_system
    assert validated.advisory_digest == context.advisory_digest
    assert validated.chain_head == context.chain_head
    assert validated.plan_proposal == context.plan_proposal
    assert validated.response_id == "resp-projection"
