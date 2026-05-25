"""Phase 6 S1-02 — AC-10: JSON round-trip + byte-determinism + umbrella discriminator.

For each of the seven variants and for :class:`TransitionEvent`:

* ``Model.model_validate_json(m.model_dump_json()) == m`` round-trip.
* ``m.model_dump_json()`` is byte-deterministic across two independent
  dumps (sorted keys; future Pydantic config flip dies here, not in
  Phase-6.5 / Phase-9).

For the :data:`VulnLedgerState` umbrella, ``TypeAdapter(VulnLedgerState)
.validate_python(adapter.dump_python(v))`` round-trips to the same
variant. A payload with an unknown ``kind`` raises a
discriminator-not-matched error rather than silently coercing.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from codegenie.workflows.vuln_ledger import (
    AwaitingHumanReview,
    Completed,
    FailedUnrecoverable,
    GateFailedRetryable,
    NeedsPlan,
    PatchApplied,
    PlanReady,
    TransitionEvent,
    VulnLedgerState,
)

_VARIANTS: list[BaseModel] = [
    NeedsPlan(),
    PlanReady(plan_summary="bump foo"),
    PatchApplied(patch_digest="a" * 64),  # type: ignore[arg-type]
    GateFailedRetryable(
        failing_signals=("build_failed",),  # type: ignore[arg-type]
        attempt_number=1,  # type: ignore[arg-type]
    ),
    AwaitingHumanReview(review_reason="no_concrete_match"),
    Completed(),
    FailedUnrecoverable(reason="checkpoint_integrity"),
]


@pytest.mark.parametrize("inst", _VARIANTS)
def test_ac10_variant_round_trip(inst: BaseModel) -> None:
    encoded = inst.model_dump_json()
    decoded = type(inst).model_validate_json(encoded)
    assert decoded == inst


@pytest.mark.parametrize("inst", _VARIANTS)
def test_ac10_variant_byte_determinism(inst: BaseModel) -> None:
    a = inst.model_dump_json()
    b = inst.model_dump_json()
    assert a == b, (
        f"AC-10: {type(inst).__name__} JSON dump must be byte-deterministic. "
        "A future Pydantic config flip that broke this would silently desync "
        "the Phase-9 byte-equality assertion across substrates."
    )


def test_ac10_transition_event_round_trip() -> None:
    ev = TransitionEvent(
        transition_id="01HXX0TRANSITION0000000000",  # type: ignore[arg-type]
        prior_state_id="needs_plan",
        next_state_id="plan_ready",
        triggering_outcome={"kind": "applied", "transform_id": "a" * 64},
        evidence_digest="b" * 64,  # type: ignore[arg-type]
        chain_head="c" * 64,  # type: ignore[arg-type]
        workflow_id="01HXX0WORKFLOW00000000000Z",  # type: ignore[arg-type]
    )
    encoded = ev.model_dump_json()
    decoded = TransitionEvent.model_validate_json(encoded)
    assert decoded == ev


def test_ac10_transition_event_byte_determinism() -> None:
    ev = TransitionEvent(
        transition_id="01HXX0TRANSITION0000000000",  # type: ignore[arg-type]
        prior_state_id="needs_plan",
        next_state_id="plan_ready",
        triggering_outcome={"kind": "applied"},
        evidence_digest="b" * 64,  # type: ignore[arg-type]
        chain_head="c" * 64,  # type: ignore[arg-type]
        workflow_id="01HXX0WORKFLOW00000000000Z",  # type: ignore[arg-type]
    )
    assert ev.model_dump_json() == ev.model_dump_json()


@pytest.mark.parametrize("inst", _VARIANTS)
def test_ac10_umbrella_round_trip_preserves_variant_class(inst: BaseModel) -> None:
    adapter = TypeAdapter(VulnLedgerState)
    dumped = adapter.dump_python(inst)
    decoded = adapter.validate_python(dumped)
    assert type(decoded) is type(inst)
    assert decoded == inst


def test_ac10_umbrella_rejects_unknown_kind_in_json() -> None:
    adapter = TypeAdapter(VulnLedgerState)
    with pytest.raises(ValidationError):
        adapter.validate_json('{"kind": "cancelled"}')
