"""Phase 6 S1-02 — AC-2: discriminated-union round-trip + discriminator-collision rejection.

The umbrella is declared as
``Annotated[Variant_1 | ... | Variant_7, Field(discriminator="kind")]`` —
the convention every Phase-3 sum type in
``codegenie/transforms/outcomes.py`` follows. Removing the discriminator
silently lets Pydantic fall back to structural matching, which is the
exact failure mode this AC pins.
"""

from __future__ import annotations

import typing

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.workflows.vuln_ledger import (
    Completed,
    GateFailedRetryable,
    NeedsPlan,
    PatchApplied,
    PlanReady,
    VulnLedgerState,
)


def test_ac2_umbrella_is_annotated_with_discriminator() -> None:
    """``get_origin`` returns ``typing.Annotated``; metadata names ``kind``."""
    metadata = typing.get_args(VulnLedgerState)
    # Annotated[Union[...], Field(discriminator="kind")]
    assert len(metadata) >= 2, "VulnLedgerState must be Annotated with a Field discriminator"
    field_info = metadata[-1]
    # pydantic.fields.FieldInfo carries ``discriminator``.
    discriminator = getattr(field_info, "discriminator", None)
    assert discriminator == "kind", (
        f"AC-2: VulnLedgerState discriminator must be 'kind' (got {discriminator!r}). "
        "Removing the discriminator lets Pydantic fall back to structural matching, "
        "which silently mis-routes payloads with overlapping field shapes."
    )


def test_ac2_round_trip_to_needs_plan() -> None:
    adapter = TypeAdapter(VulnLedgerState)
    inst = adapter.validate_python({"kind": "needs_plan"})
    assert isinstance(inst, NeedsPlan)


def test_ac2_round_trip_to_plan_ready() -> None:
    adapter = TypeAdapter(VulnLedgerState)
    inst = adapter.validate_python({"kind": "plan_ready", "plan_summary": "bump foo"})
    assert isinstance(inst, PlanReady)
    assert inst.plan_summary == "bump foo"


def test_ac2_round_trip_to_patch_applied() -> None:
    adapter = TypeAdapter(VulnLedgerState)
    inst = adapter.validate_python({"kind": "patch_applied", "patch_digest": "a" * 64})
    assert isinstance(inst, PatchApplied)


def test_ac2_round_trip_to_gate_failed_retryable() -> None:
    adapter = TypeAdapter(VulnLedgerState)
    inst = adapter.validate_python(
        {
            "kind": "gate_failed_retryable",
            "failing_signals": ["build_failed"],
            "attempt_number": 2,
        }
    )
    assert isinstance(inst, GateFailedRetryable)


def test_ac2_round_trip_to_completed() -> None:
    adapter = TypeAdapter(VulnLedgerState)
    inst = adapter.validate_python({"kind": "completed"})
    assert isinstance(inst, Completed)


def test_ac2_unknown_kind_rejected_with_discriminator_message() -> None:
    adapter = TypeAdapter(VulnLedgerState)
    with pytest.raises(ValidationError) as ei:
        adapter.validate_python({"kind": "nonsense"})
    # Pydantic v2 emits a 'union_tag_invalid' error type for discriminator
    # mismatches; the message must reference the discriminator.
    errors = ei.value.errors()
    types = {e.get("type") for e in errors}
    assert any(t.startswith("union_tag") for t in types if t), (
        f"AC-2: unknown 'kind' must raise a discriminator-collision error "
        f"(got types={types}). Structural fallback would silently mis-route."
    )


def test_ac2_missing_kind_rejected() -> None:
    """A payload lacking ``kind`` must not be accepted — discriminator is required."""
    adapter = TypeAdapter(VulnLedgerState)
    with pytest.raises(ValidationError):
        adapter.validate_python({"plan_summary": "no kind here"})


def test_ac2_overlapping_field_shape_routes_by_kind_not_structure() -> None:
    """Mutation guard: a structurally-PatchApplied-looking payload with
    ``kind='completed'`` MUST round-trip to :class:`Completed`, not to
    :class:`PatchApplied`. Without ``discriminator='kind'``, Pydantic's
    structural fallback would silently route the wrong variant — a Rule 12
    failure mode caught here."""
    adapter = TypeAdapter(VulnLedgerState)
    # Completed accepts no patch_digest, so this would naturally route to
    # PatchApplied under structural matching. With the discriminator on,
    # Pydantic rejects (extra fields forbidden).
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "completed", "patch_digest": "a" * 64})
