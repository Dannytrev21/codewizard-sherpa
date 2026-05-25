"""Phase 6 S1-02 — AC-4 + AC-5: TransitionEvent seven-field shape + legal-edge enforcement.

* AC-4 — field set is byte-equal to the seven-field shape (the five named by
  ``final-design.md §"State model"`` plus ``transition_id`` and
  ``workflow_id``). A missing or extra field fails.
* AC-5 — the ``model_validator(mode='after')`` rejects ``(prior, next) ∉
  _LEGAL_TRANSITIONS``. The error message contains the ADR-0003 directive
  substring so a buggy validator that returns ``self`` unconditionally is
  caught.
"""

from __future__ import annotations

import itertools
from typing import get_args

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from codegenie.workflows.vuln_ledger import (
    _LEGAL_TRANSITIONS,
    LedgerStateKind,
    TransitionEvent,
)

_EXPECTED_FIELDS = {
    "transition_id",
    "prior_state_id",
    "next_state_id",
    "triggering_outcome",
    "evidence_digest",
    "chain_head",
    "workflow_id",
}


def _valid_event(
    *,
    prior: str = "needs_plan",
    nxt: str = "plan_ready",
    triggering_outcome: object | None = None,
) -> TransitionEvent:
    return TransitionEvent(
        transition_id="01HXX0TRANSITION0000000000",  # type: ignore[arg-type]
        prior_state_id=prior,  # type: ignore[arg-type]
        next_state_id=nxt,  # type: ignore[arg-type]
        triggering_outcome=triggering_outcome
        if triggering_outcome is not None
        else {"kind": "applied", "transform_id": "a" * 64},
        evidence_digest="b" * 64,  # type: ignore[arg-type]
        chain_head="c" * 64,  # type: ignore[arg-type]
        workflow_id="01HXX0WORKFLOW00000000000Z",  # type: ignore[arg-type]
    )


def test_ac4_field_set_is_exact_seven() -> None:
    fields = set(TransitionEvent.model_fields)
    assert fields == _EXPECTED_FIELDS, (
        f"AC-4: TransitionEvent field set drifted. Got {fields}, want {_EXPECTED_FIELDS}. "
        "final-design.md §'State model' mandates five (prior, next, triggering, evidence, "
        "chain_head); transition_id + workflow_id are the two cross-cutting identifiers. "
        "Dropping chain_head would make replay verification (ADR-0003) impossible."
    )


def test_ac4_event_is_frozen_and_forbids_extra() -> None:
    cfg = TransitionEvent.model_config
    assert cfg.get("frozen") and cfg.get("extra") == "forbid"


def test_ac4_event_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        TransitionEvent(  # type: ignore[call-arg]
            transition_id="01HXX0TRANSITION0000000000",  # type: ignore[arg-type]
            prior_state_id="needs_plan",  # type: ignore[arg-type]
            next_state_id="plan_ready",  # type: ignore[arg-type]
            triggering_outcome={},
            evidence_digest="a" * 64,  # type: ignore[arg-type]
            chain_head="b" * 64,  # type: ignore[arg-type]
            workflow_id="01HXX0WORKFLOW00000000000Z",  # type: ignore[arg-type]
            surprise="not allowed",
        )


# ---------------------------------------------------------------------------
# AC-5 — legal transitions table enforcement.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("pair", sorted(_LEGAL_TRANSITIONS))
def test_ac5_every_legal_pair_constructs(pair: tuple[str, str]) -> None:
    prior, nxt = pair
    inst = _valid_event(prior=prior, nxt=nxt)
    assert inst.prior_state_id == prior
    assert inst.next_state_id == nxt


def _illegal_pairs() -> list[tuple[str, str]]:
    universe = list(get_args(LedgerStateKind))
    all_pairs = set(itertools.product(universe, repeat=2))
    return sorted(all_pairs - _LEGAL_TRANSITIONS)


@pytest.mark.parametrize("pair", _illegal_pairs())
def test_ac5_illegal_pairs_rejected_with_directive(pair: tuple[str, str]) -> None:
    prior, nxt = pair
    with pytest.raises(ValidationError) as ei:
        _valid_event(prior=prior, nxt=nxt)
    msg = str(ei.value)
    assert "ADR-0003" in msg, (
        f"AC-5: illegal transition {pair!r} must surface ADR-0003 directive in the "
        f"error message so the implementer is pointed at the legal-edge inventory. "
        f"Got: {msg!r}"
    )


@st.composite
def _ledger_kind_pair(draw: st.DrawFn) -> tuple[str, str]:
    universe = get_args(LedgerStateKind)
    prior = draw(st.sampled_from(universe))
    nxt = draw(st.sampled_from(universe))
    return (prior, nxt)


@given(_ledger_kind_pair())
def test_ac5_property_only_legal_pairs_construct(pair: tuple[str, str]) -> None:
    prior, nxt = pair
    if pair in _LEGAL_TRANSITIONS:
        _valid_event(prior=prior, nxt=nxt)
    else:
        with pytest.raises(ValidationError):
            _valid_event(prior=prior, nxt=nxt)


def test_ac5_operationally_terminal_states_have_zero_outgoing_edges() -> None:
    """AC-5 §3 — 'operationally terminal' = zero outgoing edges.

    The story distinguishes the *class-level* terminal partition
    (``{completed, awaiting_human_review, failed_unrecoverable}`` —
    membership of S1-01's :data:`TerminalState`) from the *operational*
    definition (zero outgoing edges = ``{completed, failed_unrecoverable}``).
    ``awaiting_human_review`` is resumable (human approves ⇒ ``plan_ready``);
    its class-level terminality is a *contract* declaration to the harness,
    not a graph-level absorbing-state claim.

    The two states with zero outgoing edges are the absorbing states.
    """
    operationally_terminal = {"completed", "failed_unrecoverable"}
    for terminal in operationally_terminal:
        for nxt in get_args(LedgerStateKind):
            assert (terminal, nxt) not in _LEGAL_TRANSITIONS, (
                f"AC-5: operationally-terminal kind {terminal!r} must have zero "
                f"outgoing edges; found ({terminal!r}, {nxt!r}) ∈ _LEGAL_TRANSITIONS "
                f"— a 'completed' re-run shortcut would soft-lock replay determinism."
            )


def test_ac5_non_absorbing_states_have_at_least_one_outgoing_edge() -> None:
    """AC-5 §4 — non-terminal-liveness: every state that is NOT
    operationally terminal must have at least one outgoing legal edge.

    ``awaiting_human_review`` IS class-level terminal but is operationally
    *resumable* — it has outgoing edges (``→ plan_ready``, ``→ completed``,
    ``→ failed_unrecoverable``). Excluded from the dead-state check.
    """
    operationally_terminal = {"completed", "failed_unrecoverable"}
    live = set(get_args(LedgerStateKind)) - operationally_terminal
    for s in live:
        out_edges = [pair for pair in _LEGAL_TRANSITIONS if pair[0] == s]
        assert out_edges, (
            f"AC-5: non-absorbing kind {s!r} has zero outgoing edges — a state "
            "with no exit is a soft-lock bug."
        )
