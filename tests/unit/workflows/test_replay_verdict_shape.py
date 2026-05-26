"""Phase 6 S2-02 AC-1 — ReplayVerdict + HydrationResult discriminated-union shape."""

from __future__ import annotations

from typing import Annotated, Literal, get_args, get_origin

import pytest
from pydantic import ValidationError

from codegenie.types.identifiers import ChainHead, TransitionId
from codegenie.workflows._frozen import _FROZEN_FORBID
from codegenie.workflows.replay import (
    ChainMismatch,
    EmptyWorkflow,
    Hydrated,
    HydrationResult,
    ReplayVerdict,
    TornWrite,
    Verified,
)
from codegenie.workflows.vuln_ledger import FailedUnrecoverable

# All four verdict variants + Hydrated must use the canonical _FROZEN_FORBID config.
_VARIANTS = (Verified, ChainMismatch, TornWrite, EmptyWorkflow, Hydrated)


def test_ac1_all_variants_use_canonical_frozen_forbid_config() -> None:
    for variant in _VARIANTS:
        cfg = variant.model_config
        assert bool(cfg.get("frozen")) and cfg.get("extra") == "forbid", (
            f"{variant.__name__}.model_config must equal _FROZEN_FORBID "
            f"(frozen=True, extra='forbid'). Inlined ConfigDict drift is forbidden."
        )
    # Mirrors the canonical S1-02 fence — _FROZEN_FORBID is referenced by name in
    # the source (the workflows-frozen-forbid AST fence enforces import discipline).
    _ = _FROZEN_FORBID


def test_ac1_kind_literals_are_byte_equal() -> None:
    """The four verdict variants + Hydrated have byte-equal ``kind`` slugs."""
    assert Verified.model_fields["kind"].default == "verified"
    assert ChainMismatch.model_fields["kind"].default == "chain_mismatch"
    assert TornWrite.model_fields["kind"].default == "torn_write"
    assert EmptyWorkflow.model_fields["kind"].default == "empty_workflow"
    assert Hydrated.model_fields["kind"].default == "hydrated"


def test_ac1_replay_verdict_union_has_exactly_four_members() -> None:
    """``ReplayVerdict`` is exactly four variants — no silent fifth."""
    # ReplayVerdict is Annotated[Verified | ChainMismatch | TornWrite | EmptyWorkflow, ...]
    assert get_origin(ReplayVerdict) is Annotated
    union_type = get_args(ReplayVerdict)[0]
    members = set(get_args(union_type))
    assert members == {Verified, ChainMismatch, TornWrite, EmptyWorkflow}, (
        f"ReplayVerdict drift — got {members!r}, want the closed four-variant set. "
        f"Adding a fifth variant is an ADR-0003 amendment."
    )


def test_ac1_hydration_result_union_is_hydrated_or_failed_unrecoverable() -> None:
    assert get_origin(HydrationResult) is Annotated
    union_type = get_args(HydrationResult)[0]
    members = set(get_args(union_type))
    assert members == {Hydrated, FailedUnrecoverable}


def test_ac1_chain_mismatch_divergence_index_validated_non_negative() -> None:
    with pytest.raises(ValidationError):
        ChainMismatch(
            persisted_tail=ChainHead("a" * 64),
            recomputed_tail=ChainHead("b" * 64),
            divergence_index=-1,
            offending_transition_id=TransitionId("01HZZZZZZZZZZZZZZAC0DIVID01"),
        )


def test_ac1_torn_write_reason_is_closed_three_element_literal() -> None:
    """``TornWrite.reason`` is exactly the three closed slugs."""
    reason_annotation = TornWrite.model_fields["reason"].annotation
    assert get_origin(reason_annotation) is Literal
    members = set(get_args(reason_annotation))
    assert members == {"unparseable_event", "null_event_bytes", "duplicate_chain_link"}


def test_ac1_torn_write_offending_sequence_validated_non_negative() -> None:
    with pytest.raises(ValidationError):
        TornWrite(reason="unparseable_event", offending_sequence=-1)


def test_ac1_variants_are_frozen() -> None:
    """Every variant is immutable — assigning a field after construction raises."""
    v = EmptyWorkflow(genesis_chain_head=ChainHead("0" * 64))
    with pytest.raises(ValidationError):
        v.genesis_chain_head = ChainHead("1" * 64)  # type: ignore[misc]
