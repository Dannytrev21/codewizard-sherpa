"""Phase 6 S2-01 AC-3 + AC-4 — semantic-boundary catalog + boundary-only append.

AC-3 pins the six-element boundary set byte-equal to final-design.md
§"Decisions of record" item 3 and cross-checks it against S1-02's
:data:`_TERMINAL_LEDGER_KINDS` (terminals are always boundaries).

AC-4 exercises every non-boundary kind (today: only ``needs_plan``) and
asserts :func:`_assert_boundary` rejects it with the policy-violation
directive — the orchestrator must surface the rejection, never silently
skip the write.
"""

from __future__ import annotations

from typing import Final, get_args

import pytest

from codegenie.workflows.checkpoints import (
    _MAX_EVENT_BYTES,
    _SEMANTIC_BOUNDARY_KINDS,
    _assert_boundary,
)
from codegenie.workflows.vuln_ledger import (
    _TERMINAL_LEDGER_KINDS,
    LedgerStateKind,
)

_EXPECTED_BOUNDARY_KINDS: Final[frozenset[LedgerStateKind]] = frozenset(
    {
        "plan_ready",
        "patch_applied",
        "gate_failed_retryable",
        "awaiting_human_review",
        "completed",
        "failed_unrecoverable",
    }
)


def test_ac3_membership_byte_equal_to_final_design() -> None:
    """Byte-equality against the six kinds final-design.md item 3 enumerates."""
    assert _SEMANTIC_BOUNDARY_KINDS == _EXPECTED_BOUNDARY_KINDS, (
        "_SEMANTIC_BOUNDARY_KINDS drift from final-design.md §'Decisions of "
        "record' item 3. Adding a seventh boundary is an ADR-0003 amendment."
    )
    assert len(_SEMANTIC_BOUNDARY_KINDS) == 6


def test_ac3_subset_of_ledger_state_kind() -> None:
    """Every boundary kind must be a valid LedgerStateKind (S1-02 cross-story)."""
    kind_universe = set(get_args(LedgerStateKind))
    assert _SEMANTIC_BOUNDARY_KINDS <= kind_universe, (
        "_SEMANTIC_BOUNDARY_KINDS contains a kind not in LedgerStateKind — "
        "rename drift between vuln_ledger.py and checkpoints.py."
    )


def test_ac3_terminal_kinds_are_boundary_kinds() -> None:
    """Every terminal LedgerStateKind must be a semantic boundary."""
    assert _TERMINAL_LEDGER_KINDS <= _SEMANTIC_BOUNDARY_KINDS, (
        "Terminal partition drift — a workflow that ends MUST have a final "
        "durable checkpoint. ADR-0003 §Consequences."
    )


def test_ac3_needs_plan_is_not_a_boundary() -> None:
    """The one non-boundary kind today is the initial state — no value in persisting."""
    assert "needs_plan" not in _SEMANTIC_BOUNDARY_KINDS, (
        "needs_plan is the initial state; checkpointing it would be a redundant snapshot."
    )


def test_ac3_max_event_bytes_constant() -> None:
    """The 64 KiB cap is module-level Final (not class-level, not derived)."""
    assert _MAX_EVENT_BYTES == 65_536


def _build_event(prior: LedgerStateKind, nxt: LedgerStateKind):
    """Construct a valid ``TransitionEvent`` with the given edge."""
    from codegenie.types.identifiers import (
        BlobDigest,
        ChainHead,
        TransitionId,
        WorkflowId,
    )
    from codegenie.workflows.vuln_ledger import TransitionEvent

    return TransitionEvent(
        transition_id=TransitionId("01ARZ3NDEKTSV4RRFFQ69G5FAV"),
        prior_state_id=prior,
        next_state_id=nxt,
        triggering_outcome={"why": "test"},
        evidence_digest=BlobDigest("blake3:" + "a" * 64),
        chain_head=ChainHead("0" * 64),
        workflow_id=WorkflowId("01HZZZZZZZZZZZZZZZZZZZZZZZ"),
    )


# AC-4 — parametrize over every non-boundary kind reachable via a legal
# edge. Today the only non-boundary kind is ``needs_plan``; only one
# legal edge ends at ``needs_plan`` (``gate_failed_retryable ->
# needs_plan``).
_NON_BOUNDARY_EDGES: Final[list[tuple[LedgerStateKind, LedgerStateKind]]] = [
    ("gate_failed_retryable", "needs_plan"),
]


@pytest.mark.parametrize(("prior", "nxt"), _NON_BOUNDARY_EDGES)
def test_ac4_non_boundary_append_rejected(prior: LedgerStateKind, nxt: LedgerStateKind) -> None:
    """The boundary helper raises with the policy-violation directive."""
    event = _build_event(prior, nxt)
    with pytest.raises(ValueError) as exc_info:
        _assert_boundary(event)
    msg = str(exc_info.value)
    assert "Phase-6 checkpoint policy violation" in msg
    assert "ADR-0003" in msg
    assert repr(nxt) in msg


@pytest.mark.parametrize("kind", sorted(_EXPECTED_BOUNDARY_KINDS))
def test_ac4_boundary_append_accepted(kind: LedgerStateKind) -> None:
    """Every boundary kind passes the policy check.

    We construct a legal edge ending at ``kind`` so the
    ``model_validator`` doesn't reject the event before
    :func:`_assert_boundary` ever runs.
    """
    # Legal in-edges for each boundary kind (any one will do).
    in_edge: dict[LedgerStateKind, LedgerStateKind] = {
        "plan_ready": "needs_plan",
        "patch_applied": "plan_ready",
        "gate_failed_retryable": "patch_applied",
        "awaiting_human_review": "plan_ready",
        "completed": "patch_applied",
        "failed_unrecoverable": "plan_ready",
    }
    event = _build_event(in_edge[kind], kind)
    _assert_boundary(event)  # MUST NOT raise
