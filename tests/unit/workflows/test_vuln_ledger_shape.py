"""Phase 6 S1-02 — AC-1 + AC-3: seven-variant shape + frozen-extra-forbid payloads.

Covers:

* AC-1 — exactly seven ``BaseModel`` subclasses in ``vuln_ledger.py``;
  multiset of ``kind`` literals byte-equal to ``LedgerStateKind``
  membership.
* AC-3 — per-variant payload fields named in the story; ``model_config
  = _FROZEN_FORBID`` on every variant; payload values are typed via
  existing newtypes / closed literals (never raw ``str``).

The AST ``_FROZEN_FORBID`` import-fence lives at
``tests/fence/test_workflows_frozen_forbid.py`` (AC-12).
"""

from __future__ import annotations

import inspect
from typing import get_args

import pytest
from pydantic import BaseModel, ValidationError

import codegenie.workflows.vuln_ledger as ledger
from codegenie.workflows.vuln_ledger import (
    AwaitingHumanReview,
    Completed,
    FailedUnrecoverable,
    GateFailedRetryable,
    LedgerStateKind,
    NeedsPlan,
    PatchApplied,
    PlanReady,
)

_EXPECTED_VARIANT_NAMES = {
    "NeedsPlan",
    "PlanReady",
    "PatchApplied",
    "GateFailedRetryable",
    "AwaitingHumanReview",
    "Completed",
    "FailedUnrecoverable",
}

_EXPECTED_KINDS = {
    "needs_plan",
    "plan_ready",
    "patch_applied",
    "gate_failed_retryable",
    "awaiting_human_review",
    "completed",
    "failed_unrecoverable",
}


def _ledger_variant_classes() -> set[type[BaseModel]]:
    """Return the seven variant classes declared in ``vuln_ledger.py``.

    Inspects the module for ``BaseModel`` subclasses whose ``kind`` field
    is a ``Literal[...]`` taxonomy member (excludes :class:`TransitionEvent`
    + any other helper models).
    """
    found: set[type[BaseModel]] = set()
    for _name, obj in inspect.getmembers(ledger, inspect.isclass):
        if not issubclass(obj, BaseModel):
            continue
        if obj.__module__ != ledger.__name__:
            continue
        # A variant carries a ``kind`` Literal whose only allowed value is
        # in ``LedgerStateKind``. ``TransitionEvent`` has no such field.
        kind_field = obj.model_fields.get("kind")
        if kind_field is None:
            continue
        ann_args = get_args(kind_field.annotation)
        if not ann_args:
            continue
        if any(a in _EXPECTED_KINDS for a in ann_args):
            found.add(obj)
    return found


def test_ac1_seven_variant_classes_present() -> None:
    classes = _ledger_variant_classes()
    names = {c.__name__ for c in classes}
    assert names == _EXPECTED_VARIANT_NAMES, (
        f"AC-1: expected seven variants {_EXPECTED_VARIANT_NAMES}, got {names}. "
        "Adding an eighth variant requires amending ADR-0001 + ADR-0003 + "
        "S1-01's TerminalState Literal first."
    )
    assert len(classes) == 7


def test_ac1_kind_multiset_byte_equal_to_ledger_state_kind_membership() -> None:
    classes = _ledger_variant_classes()
    kinds: list[str] = []
    for c in classes:
        ann = c.model_fields["kind"].annotation
        # Literal[...] — get_args returns the single literal value tuple.
        args = get_args(ann)
        assert len(args) == 1, f"variant {c.__name__} kind literal must have arity 1"
        kinds.append(args[0])
    assert sorted(kinds) == sorted(_EXPECTED_KINDS), (
        f"AC-1: variant kinds {sorted(kinds)} drifted from LedgerStateKind "
        f"membership {sorted(_EXPECTED_KINDS)}."
    )
    # Cross-check with the public alias's ``get_args``.
    assert set(get_args(LedgerStateKind)) == _EXPECTED_KINDS


# ---------------------------------------------------------------------------
# AC-3 — per-variant payload fields + frozen + extra="forbid".
# ---------------------------------------------------------------------------


def _is_frozen_and_forbid(cls: type[BaseModel]) -> bool:
    cfg = cls.model_config
    return bool(cfg.get("frozen")) and cfg.get("extra") == "forbid"


@pytest.mark.parametrize(
    "cls",
    [
        NeedsPlan,
        PlanReady,
        PatchApplied,
        GateFailedRetryable,
        AwaitingHumanReview,
        Completed,
        FailedUnrecoverable,
    ],
)
def test_ac3_variant_is_frozen_and_forbids_extra(cls: type[BaseModel]) -> None:
    assert _is_frozen_and_forbid(cls), (
        f"AC-3/AC-12: {cls.__name__} must set model_config = _FROZEN_FORBID. "
        "Inline ConfigDict(...) declarations drift; the AST fence at "
        "tests/fence/test_workflows_frozen_forbid.py pins single-canonical."
    )


def test_ac3_needs_plan_has_only_kind() -> None:
    fields = set(NeedsPlan.model_fields)
    assert fields == {"kind"}, "NeedsPlan: initial state, no evidence payload"


def test_ac3_plan_ready_carries_plan_summary() -> None:
    assert set(PlanReady.model_fields) == {"kind", "plan_summary"}
    PlanReady(plan_summary="bump lodash to 4.17.21")  # constructs


def test_ac3_plan_ready_rejects_overlong_summary() -> None:
    with pytest.raises(ValidationError):
        PlanReady(plan_summary="x" * 4097)


def test_ac3_patch_applied_carries_patch_digest() -> None:
    assert set(PatchApplied.model_fields) == {"kind", "patch_digest"}
    PatchApplied(patch_digest="a" * 64)  # type: ignore[arg-type]


def test_ac3_gate_failed_retryable_uses_tuple_not_list() -> None:
    """The field MUST be ``tuple`` so the variant is hashable / genuinely frozen."""
    fields = GateFailedRetryable.model_fields
    assert set(fields) == {"kind", "failing_signals", "attempt_number"}
    inst = GateFailedRetryable(
        failing_signals=("build_failed",),  # type: ignore[arg-type]
        attempt_number=1,  # type: ignore[arg-type]
    )
    assert isinstance(inst.failing_signals, tuple)


def test_ac3_awaiting_human_review_carries_review_reason() -> None:
    fields = set(AwaitingHumanReview.model_fields)
    assert fields == {"kind", "review_reason", "handoff_path"}
    AwaitingHumanReview(review_reason="no_concrete_match")
    AwaitingHumanReview(review_reason="no_concrete_match", handoff_path="runs/abc.txt")


def test_ac3_completed_carries_optional_report_path() -> None:
    fields = set(Completed.model_fields)
    assert fields == {"kind", "report_path"}
    Completed()  # default report_path=None
    Completed(report_path="runs/report.md")


def test_ac3_failed_unrecoverable_reason_is_closed_set() -> None:
    fields = set(FailedUnrecoverable.model_fields)
    assert fields == {"kind", "reason", "error"}
    # Each allowed reason constructs.
    for reason in (
        "checkpoint_integrity",
        "subgraph_aborted",
        "manifest_rejected",
        "policy_violation",
        "internal_invariant_violated",
    ):
        FailedUnrecoverable(reason=reason)  # type: ignore[arg-type]


def test_ac3_failed_unrecoverable_rejects_unknown_reason() -> None:
    with pytest.raises(ValidationError):
        FailedUnrecoverable(reason="some_new_reason")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "cls,kwargs",
    [
        (NeedsPlan, {}),
        (PlanReady, {"plan_summary": "p"}),
        (PatchApplied, {"patch_digest": "a" * 64}),
        (
            GateFailedRetryable,
            {"failing_signals": ("x",), "attempt_number": 1},
        ),
        (AwaitingHumanReview, {"review_reason": "no_concrete_match"}),
        (Completed, {}),
        (FailedUnrecoverable, {"reason": "subgraph_aborted"}),
    ],
)
def test_ac3_extra_field_rejected(cls: type[BaseModel], kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        cls(**kwargs, surprise=42)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "cls,kwargs",
    [
        (PlanReady, {"plan_summary": "p"}),
        (PatchApplied, {"patch_digest": "a" * 64}),
    ],
)
def test_ac3_frozen_assignment_rejected(cls: type[BaseModel], kwargs: dict[str, object]) -> None:
    inst = cls(**kwargs)
    with pytest.raises(ValidationError):
        # Reassigning to a frozen model raises ValidationError.
        next_field = next(iter(kwargs))
        setattr(inst, next_field, "other")  # type: ignore[arg-type]
