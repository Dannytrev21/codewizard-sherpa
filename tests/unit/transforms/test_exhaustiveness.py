"""Per-umbrella exhaustiveness — story 03 S1-03 AC-9.

Five named tests, one per discriminated union; each ``match``-es over every
current variant and reaches ``assert_never(unexpected)`` in the wildcard
arm. Runtime confirms full coverage today; the *real* protection against
silent ``Union`` widening is mypy's narrowing-based check on
``assert_never``, fenced by the subprocess-mypy meta-test in
``test_outcomes_mypy_negative.py`` (AC-9a).
"""

from __future__ import annotations

from typing import assert_never

from codegenie.transforms.outcomes import (
    AdapterConfidence,
    Advance,
    Applicability,
    ApplicationPlan,
    Applied,
    Applies,
    Degraded,
    Escalate,
    NodeTransition,
    NotApplies,
    RecipeError,
    RecipeFailed,
    RecipeNotApplicable,
    RecipeOutcome,
    RemediationError,
    RemediationFailed,
    RemediationNotApplicable,
    RemediationOutcome,
    RequiresHumanReview,
    ShortCircuit,
    Skipped,
    Trusted,
    Unavailable,
    Validated,
)
from codegenie.types.identifiers import (
    BranchName,
    ErrorId,
    PluginId,
    RecipeId,
    TransformId,
)


def test_exhaustiveness_recipe_outcome() -> None:
    """AC-9 — every ``RecipeOutcome`` variant has a ``match`` arm + the
    wildcard reaches ``assert_never``."""
    instances: list[RecipeOutcome] = [
        Applied(
            transform_id=TransformId("a" * 64),
            plugin_id=PluginId("p"),
            recipe_id=RecipeId("r"),
        ),
        Skipped(reason="plugin_disabled", plugin_id=PluginId("p")),
        RecipeNotApplicable(reason="PEER_DEP_CONFLICT"),
        RecipeFailed(error=RecipeError(error_id=ErrorId("e.1"), message="x")),
    ]
    seen: set[str] = set()
    for o in instances:
        match o:
            case Applied():
                seen.add("applied")
            case Skipped():
                seen.add("skipped")
            case RecipeNotApplicable():
                seen.add("not_applicable")
            case RecipeFailed():
                seen.add("failed")
            case _ as unexpected:
                assert_never(unexpected)
    assert seen == {"applied", "skipped", "not_applicable", "failed"}


def test_exhaustiveness_remediation_outcome() -> None:
    """AC-9 — every ``RemediationOutcome`` variant has a ``match`` arm."""
    instances: list[RemediationOutcome] = [
        Validated(branch=BranchName("b"), report_path="/p", passed=True, failing=[]),
        RequiresHumanReview(reason="no_concrete_match"),
        RemediationNotApplicable(reason="PEER_DEP_CONFLICT"),
        RemediationFailed(
            error=RemediationError(error_id=ErrorId("e.1"), message="x"),
        ),
    ]
    seen: set[str] = set()
    for o in instances:
        match o:
            case Validated():
                seen.add("validated")
            case RequiresHumanReview():
                seen.add("requires_human_review")
            case RemediationNotApplicable():
                seen.add("not_applicable")
            case RemediationFailed():
                seen.add("failed")
            case _ as unexpected:
                assert_never(unexpected)
    assert seen == {"validated", "requires_human_review", "not_applicable", "failed"}


def test_exhaustiveness_node_transition() -> None:
    """AC-9 — every ``NodeTransition`` variant has a ``match`` arm."""
    instances: list[NodeTransition] = [
        Advance(state={}),
        ShortCircuit(outcome=RemediationNotApplicable(reason="PEER_DEP_CONFLICT")),
        Escalate(reason="capability_missing"),
    ]
    seen: set[str] = set()
    for t in instances:
        match t:
            case Advance():
                seen.add("advance")
            case ShortCircuit():
                seen.add("short_circuit")
            case Escalate():
                seen.add("escalate")
            case _ as unexpected:
                assert_never(unexpected)
    assert seen == {"advance", "short_circuit", "escalate"}


def test_exhaustiveness_adapter_confidence() -> None:
    """AC-9 — every ``AdapterConfidence`` variant has a ``match`` arm."""
    instances: list[AdapterConfidence] = [
        Trusted(),
        Degraded(reason="timeout"),
        Unavailable(reason="binary_missing"),
    ]
    seen: set[str] = set()
    for c in instances:
        match c:
            case Trusted():
                seen.add("trusted")
            case Degraded():
                seen.add("degraded")
            case Unavailable():
                seen.add("unavailable")
            case _ as unexpected:
                assert_never(unexpected)
    assert seen == {"trusted", "degraded", "unavailable"}


def test_exhaustiveness_applicability() -> None:
    """AC-9 — every ``Applicability`` variant has a ``match`` arm."""
    instances: list[Applicability] = [
        Applies(plan=ApplicationPlan(summary="x")),
        NotApplies(reason="PEER_DEP_CONFLICT"),
    ]
    seen: set[str] = set()
    for a in instances:
        match a:
            case Applies():
                seen.add("applies")
            case NotApplies():
                seen.add("not_applies")
            case _ as unexpected:
                assert_never(unexpected)
    assert seen == {"applies", "not_applies"}
