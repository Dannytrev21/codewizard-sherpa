"""Unit tests for ``codegenie.transforms.outcomes`` — story 03 S1-03.

Covers every acceptance criterion (AC-1 .. AC-13) of
``docs/phases/03-vuln-deterministic-recipe/stories/S1-03-tagged-union-outcomes.md``
that is observable at runtime. Static-type (AC-9a) is enforced by the
subprocess-mypy fence in ``test_outcomes_mypy_negative.py``; module-purity
(AC-10b / AC-10c) is enforced by ``test_outcomes_purity.py``.

Note on naming: the story's example test imports use the bare names
``NotApplicable as RecipeNotApplicable`` / ``Failed as RecipeFailed`` etc.,
which technically aliases a single class twice. Because
``RecipeOutcome.Failed`` and ``RemediationOutcome.Failed`` carry different
field shapes (``RecipeError`` vs ``RemediationError + partial_report_path``)
they MUST be distinct classes. We export them under disambiguated names —
``RecipeFailed`` / ``RemediationFailed`` / ``RecipeNotApplicable`` /
``RemediationNotApplicable`` — and the umbrella discriminated unions
``RecipeOutcome`` / ``RemediationOutcome`` route by ``kind`` as usual.
"""

from __future__ import annotations

import typing

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.transforms.outcomes import (
    AdapterConfidence,
    Advance,
    Applicability,
    ApplicationPlan,
    Applied,
    Applies,
    DegradationReason,
    Degraded,
    Escalate,
    EscalationReason,
    HumanReviewReason,
    NodeTransition,
    NotApplicableReason,
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
    SkipReason,
    Trusted,
    UnavailabilityReason,
    Unavailable,
    Validated,
)
from codegenie.types.identifiers import (
    BranchName,
    ErrorId,
    PluginId,
    RecipeId,
    SignalKind,
    TransformId,
)

ALL_VARIANTS = [
    Applied(
        transform_id=TransformId("a" * 64),
        plugin_id=PluginId("vuln--node--npm"),
        recipe_id=RecipeId("R1"),
    ),
    Skipped(reason="plugin_disabled", plugin_id=PluginId("vuln--node--npm")),
    RecipeNotApplicable(reason="PEER_DEP_CONFLICT"),
    RecipeFailed(error=RecipeError(error_id=ErrorId("recipe.boom"), message="boom")),
    Validated(
        branch=BranchName("fix/cve-1"),
        report_path="/jail/report.yaml",
        passed=True,
        failing=[],
    ),
    RequiresHumanReview(reason="no_concrete_match"),
    RemediationNotApplicable(reason="RECIPE_CATALOG_MISS"),
    RemediationFailed(
        error=RemediationError(error_id=ErrorId("rem.boom"), message="b"),
    ),
    Advance(state={"k": 1}),
    ShortCircuit(outcome=RemediationNotApplicable(reason="PEER_DEP_CONFLICT")),
    Escalate(reason="capability_missing"),
    Trusted(),
    Degraded(reason="timeout"),
    Unavailable(reason="binary_missing"),
    Applies(plan=ApplicationPlan(summary="bump express")),
    NotApplies(reason="MAJOR_BUMP_REFUSE"),
]

UNION_FOR = {
    Applied: RecipeOutcome,
    Skipped: RecipeOutcome,
    RecipeNotApplicable: RecipeOutcome,
    RecipeFailed: RecipeOutcome,
    Validated: RemediationOutcome,
    RequiresHumanReview: RemediationOutcome,
    RemediationNotApplicable: RemediationOutcome,
    RemediationFailed: RemediationOutcome,
    Advance: NodeTransition,
    ShortCircuit: NodeTransition,
    Escalate: NodeTransition,
    Trusted: AdapterConfidence,
    Degraded: AdapterConfidence,
    Unavailable: AdapterConfidence,
    Applies: Applicability,
    NotApplies: Applicability,
}


@pytest.mark.parametrize("inst", ALL_VARIANTS)
def test_construct_and_round_trip(inst):
    """AC-8a — every variant round-trips through its umbrella union."""
    union = UNION_FOR[type(inst)]
    adapter = TypeAdapter(union)
    decoded = adapter.validate_json(adapter.dump_json(inst))
    assert decoded == inst
    assert type(decoded) is type(inst)


def test_nested_discriminator_preserved():
    """AC-8a — ``ShortCircuit(outcome=Validated(...))`` preserves the nested
    concrete type. Guards against accidental loss of the inner discriminator."""
    inner = Validated(
        branch=BranchName("b"),
        report_path="/p",
        passed=True,
        failing=[],
    )
    sc = ShortCircuit(outcome=inner)
    adapter = TypeAdapter(NodeTransition)
    decoded = adapter.validate_json(adapter.dump_json(sc))
    assert isinstance(decoded, ShortCircuit)
    assert isinstance(decoded.outcome, Validated)
    assert decoded.outcome == inner


@pytest.mark.parametrize("inst", ALL_VARIANTS)
def test_extra_field_rejected(inst):
    """AC-8b — every variant rejects extra fields."""
    payload = {**inst.model_dump(), "_oops": "x"}
    with pytest.raises(ValidationError):
        type(inst).model_validate(payload)


@pytest.mark.parametrize("inst", ALL_VARIANTS)
def test_frozen_after_construction(inst):
    """AC-8c — every variant is frozen (mutation raises)."""
    with pytest.raises(ValidationError):
        inst.kind = "bogus"  # type: ignore[misc]


def test_discriminator_strings_are_exactly_pinned():
    """AC-8d — a symmetric ``Applied.kind ↔ Failed.kind`` swap would still
    round-trip; pin the exact strings against that mutation."""
    expected: dict[type, str] = {
        Applied: "applied",
        Skipped: "skipped",
        RecipeNotApplicable: "not_applicable",
        RecipeFailed: "failed",
        Validated: "validated",
        RequiresHumanReview: "requires_human_review",
        RemediationNotApplicable: "not_applicable",
        RemediationFailed: "failed",
        Advance: "advance",
        ShortCircuit: "short_circuit",
        Escalate: "escalate",
        Trusted: "trusted",
        Degraded: "degraded",
        Unavailable: "unavailable",
        Applies: "applies",
        NotApplies: "not_applies",
    }
    for inst in ALL_VARIANTS:
        assert inst.kind == expected[type(inst)]


@pytest.mark.parametrize("inst", ALL_VARIANTS)
def test_json_shape_pinned(inst):
    """AC-8e — a ``kind`` → ``tag`` rename would still pass round-trip;
    pin the JSON key explicitly."""
    dump = inst.model_dump(mode="json")
    assert "kind" in dump
    assert dump["kind"] == inst.kind


def test_json_shape_keysets_pinned():
    """AC-8e — pin the full ``model_dump(mode='json')`` key-set for one
    variant per umbrella; catches accidental field rename."""
    assert set(
        Applied(
            transform_id=TransformId("a" * 64),
            plugin_id=PluginId("p"),
            recipe_id=RecipeId("r"),
        )
        .model_dump(mode="json")
        .keys()
    ) == {"kind", "transform_id", "plugin_id", "recipe_id"}
    assert set(
        Validated(branch=BranchName("b"), report_path="/p", passed=True, failing=[])
        .model_dump(mode="json")
        .keys()
    ) == {"kind", "branch", "report_path", "passed", "failing"}
    assert set(Trusted().model_dump(mode="json").keys()) == {"kind"}
    assert set(Advance(state={"k": 1}).model_dump(mode="json").keys()) == {"kind", "state"}
    assert set(NotApplies(reason="PEER_DEP_CONFLICT").model_dump(mode="json").keys()) == {
        "kind",
        "reason",
    }


@pytest.mark.parametrize(
    "union",
    [RecipeOutcome, RemediationOutcome, NodeTransition, AdapterConfidence, Applicability],
)
def test_top_level_unknown_kind_rejected(union):
    """AC-8f — bogus discriminator value rejected at the umbrella level."""
    with pytest.raises(ValidationError):
        TypeAdapter(union).validate_python({"kind": "bogus_kind"})


def test_not_applicable_reason_is_single_source_of_truth():
    """AC-8g — the ``NotApplicableReason`` Literal alias is the same object
    on both producers. Identity check (``is``) guards accidental duplication."""
    recipe_anno = RecipeNotApplicable.model_fields["reason"].annotation
    rem_anno = RemediationNotApplicable.model_fields["reason"].annotation
    assert recipe_anno is rem_anno
    assert recipe_anno is NotApplicableReason


def test_validated_passed_failing_invariant():
    """AC-8h — ``passed == (len(failing) == 0)`` (make-illegal-states-unrepresentable)."""
    Validated(branch=BranchName("b"), report_path="/p", passed=True, failing=[])
    Validated(
        branch=BranchName("b"),
        report_path="/p",
        passed=False,
        failing=[SignalKind("tests")],
    )
    with pytest.raises(ValidationError):
        Validated(
            branch=BranchName("b"),
            report_path="/p",
            passed=True,
            failing=[SignalKind("tests")],
        )
    with pytest.raises(ValidationError):
        Validated(branch=BranchName("b"), report_path="/p", passed=False, failing=[])


@pytest.mark.parametrize(
    "bad",
    [{"k": [1, 2]}, {"k": {"nested": 1}}, {"k": None}],
)
def test_advance_state_primitives_only_rejects(bad):
    """AC-8i — ``state`` accepts only ``str | int | bool | float`` values."""
    with pytest.raises(ValidationError):
        Advance(state=bad)


@pytest.mark.parametrize(
    "ok",
    [{"k": "v"}, {"k": 1}, {"k": True}, {"k": 1.5}, {}],
)
def test_advance_state_primitives_only_accepts(ok):
    """AC-8i — primitive values and the empty dict pass validation."""
    Advance(state=ok)


def test_recipe_error_message_max_length_4096():
    """AC-7g — ``RecipeError.message`` capped at 4096 chars."""
    RecipeError(error_id=ErrorId("e.1"), message="x" * 4096)
    with pytest.raises(ValidationError):
        RecipeError(error_id=ErrorId("e.1"), message="x" * 4097)


def test_remediation_error_message_max_length_4096():
    """AC-7g — ``RemediationError.message`` capped at 4096 chars."""
    RemediationError(error_id=ErrorId("r.1"), message="x" * 4096)
    with pytest.raises(ValidationError):
        RemediationError(error_id=ErrorId("r.1"), message="x" * 4097)


def test_partial_report_path_defaults_to_none():
    """AC-4 — ``RemediationFailed.partial_report_path`` defaults to ``None``
    (orchestrator may fail before allocating the report path)."""
    f = RemediationFailed(error=RemediationError(error_id=ErrorId("r.1"), message="x"))
    assert f.partial_report_path is None
    g = RemediationFailed(
        error=RemediationError(error_id=ErrorId("r.1"), message="x"),
        partial_report_path="/jail/partial.yaml",
    )
    assert g.partial_report_path == "/jail/partial.yaml"


def test_handoff_path_defaults_to_none():
    """AC-4 — ``RequiresHumanReview.handoff_path`` defaults to ``None``."""
    rhr = RequiresHumanReview(reason="no_concrete_match")
    assert rhr.handoff_path is None


def test_reason_literal_sets_pinned():
    """AC-7a..AC-7f — every reason Literal has the pinned member set."""

    def members(alias):
        return set(typing.get_args(alias))

    assert members(NotApplicableReason) == {
        "PEER_DEP_CONFLICT",
        "MAJOR_BUMP_REFUSE",
        "OVERRIDES_AMBIGUOUS",
        "RECIPE_CATALOG_MISS",
        "ALL_RECIPES_NOT_APPLICABLE",
        # S5-01 additive — registry walker's "zero recipes" dispatch case.
        "NO_RECIPES_REGISTERED",
    }
    assert members(SkipReason) == {"plugin_disabled", "registry_skipped"}
    assert members(EscalationReason) == {
        "plugin_extends_cycle",
        "manifest_rejected",
        "capability_missing",
    }
    assert members(HumanReviewReason) == {
        "no_concrete_match",
        "trust_outcome_failed",
        "policy_violation_unrecoverable",
    }
    assert members(DegradationReason) == {"timeout", "partial_results", "rate_limited"}
    assert members(UnavailabilityReason) == {
        "binary_missing",
        "io_error",
        "unsupported_version",
    }


EXPECTED_ALL = {
    # Umbrella aliases (5)
    "RecipeOutcome",
    "RemediationOutcome",
    "NodeTransition",
    "AdapterConfidence",
    "Applicability",
    # Variant classes (16 — distinct per umbrella; Failed/NotApplicable
    # disambiguated by recipe-/remediation-prefixed names)
    "Applied",
    "Skipped",
    "RecipeNotApplicable",
    "RecipeFailed",
    "Validated",
    "RequiresHumanReview",
    "RemediationNotApplicable",
    "RemediationFailed",
    "Advance",
    "ShortCircuit",
    "Escalate",
    "Trusted",
    "Degraded",
    "Unavailable",
    "Applies",
    "NotApplies",
    # Reason literals (6)
    "NotApplicableReason",
    "SkipReason",
    "EscalationReason",
    "HumanReviewReason",
    "DegradationReason",
    "UnavailabilityReason",
    # Error models (2)
    "RecipeError",
    "RemediationError",
    # ApplicationPlan (1)
    "ApplicationPlan",
}


def test_all_exports_exact_set():
    """AC-10a — ``__all__`` is the exact 30-name set. (Story header says 31
    by double-counting reused ``NotApplicable``/``Failed`` names; we
    disambiguate to ``RecipeFailed`` / ``RemediationFailed`` /
    ``RecipeNotApplicable`` / ``RemediationNotApplicable`` and produce 30
    unique exports.)"""
    import codegenie.transforms.outcomes as m

    assert set(m.__all__) == EXPECTED_ALL
    assert len(m.__all__) == len(EXPECTED_ALL) == 30


def test_all_names_resolve_in_package_init():
    """AC-1 — every export resolves from ``codegenie.transforms``."""
    import codegenie.transforms as pkg

    for name in EXPECTED_ALL:
        assert hasattr(pkg, name), f"codegenie.transforms missing {name}"


def test_recipe_and_remediation_variants_are_distinct_classes():
    """Recipe + remediation ``NotApplicable`` and ``Failed`` are distinct
    class objects (different shapes — ``RecipeError`` vs ``RemediationError``
    + ``partial_report_path``)."""
    assert RecipeNotApplicable is not RemediationNotApplicable
    assert RecipeFailed is not RemediationFailed
