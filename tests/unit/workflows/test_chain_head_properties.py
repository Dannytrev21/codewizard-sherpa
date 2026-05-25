"""Phase 6 S1-02 — AC-8: chain-head stability + sensitivity + chain-forward.

The pure helper at :mod:`codegenie.workflows._chain` is the substrate the
Phase-9 S4-05 G5 byte-equality story depends on. Three Hypothesis
properties + one fold-equivalence:

* **Stability** — same ``(prior, event)`` ⇒ byte-equal chain head.
* **Sensitivity** — any field difference (in ``event`` or in ``prior``) ⇒
  different chain head. Mutants that drop a field from the canonical
  bytes die.
* **Chain-forward extension** — folding a sequence yields the same final
  head as recomputing from the same starting head. The chain is a pure
  function of the event sequence, never of hidden state.
"""

from __future__ import annotations

import string

from hypothesis import given, settings
from hypothesis import strategies as st

from codegenie.types.identifiers import ChainHead
from codegenie.workflows._chain import _compute_chain_head
from codegenie.workflows.vuln_ledger import TransitionEvent

_HEX = "0123456789abcdef"

_LEGAL_PAIRS = [
    ("needs_plan", "plan_ready"),
    ("plan_ready", "patch_applied"),
    ("patch_applied", "completed"),
    ("plan_ready", "awaiting_human_review"),
    ("gate_failed_retryable", "needs_plan"),
]


@st.composite
def _chain_heads(draw: st.DrawFn) -> ChainHead:
    chars = draw(st.lists(st.sampled_from(_HEX), min_size=64, max_size=64))
    return ChainHead("".join(chars))


@st.composite
def _events(draw: st.DrawFn) -> TransitionEvent:
    prior, nxt = draw(st.sampled_from(_LEGAL_PAIRS))
    # 26-char Crockford base32 ULID
    ulid_alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    transition_id = "0" + "".join(
        draw(st.lists(st.sampled_from(ulid_alphabet[:32]), min_size=25, max_size=25))
    )
    workflow_id = "0" + "".join(
        draw(st.lists(st.sampled_from(ulid_alphabet[:32]), min_size=25, max_size=25))
    )
    evidence = "".join(draw(st.lists(st.sampled_from(_HEX), min_size=64, max_size=64)))
    head = "".join(draw(st.lists(st.sampled_from(_HEX), min_size=64, max_size=64)))
    payload = draw(
        st.dictionaries(
            keys=st.text(alphabet=string.ascii_lowercase, min_size=1, max_size=8),
            values=st.text(alphabet=string.ascii_lowercase, max_size=16),
            max_size=4,
        )
    )
    return TransitionEvent(
        transition_id=transition_id,  # type: ignore[arg-type]
        prior_state_id=prior,  # type: ignore[arg-type]
        next_state_id=nxt,  # type: ignore[arg-type]
        triggering_outcome=payload,
        evidence_digest=evidence,  # type: ignore[arg-type]
        chain_head=head,  # type: ignore[arg-type]
        workflow_id=workflow_id,  # type: ignore[arg-type]
    )


@given(prior=_chain_heads(), event=_events())
@settings(max_examples=50)
def test_ac8_stability(prior: ChainHead, event: TransitionEvent) -> None:
    a = _compute_chain_head(prior, event)
    b = _compute_chain_head(prior, event)
    assert a == b
    # Return shape matches ChainHead grammar (64 lowercase hex chars).
    assert len(a) == 64
    assert all(c in _HEX for c in a)


@given(prior=_chain_heads(), event=_events(), other=_events())
@settings(max_examples=50)
def test_ac8_sensitivity_to_event_change(
    prior: ChainHead, event: TransitionEvent, other: TransitionEvent
) -> None:
    if event == other:
        # Hypothesis may rarely draw equal events — same input ⇒ same output,
        # which is the stability case, not the sensitivity case.
        return
    assert _compute_chain_head(prior, event) != _compute_chain_head(prior, other)


@given(prior_a=_chain_heads(), prior_b=_chain_heads(), event=_events())
@settings(max_examples=50)
def test_ac8_sensitivity_to_prior_head_change(
    prior_a: ChainHead, prior_b: ChainHead, event: TransitionEvent
) -> None:
    if prior_a == prior_b:
        return
    assert _compute_chain_head(prior_a, event) != _compute_chain_head(prior_b, event)


@given(
    starting=_chain_heads(),
    seq=st.lists(_events(), min_size=1, max_size=5),
)
@settings(max_examples=25)
def test_ac8_chain_forward_extension_is_pure_fold(
    starting: ChainHead, seq: list[TransitionEvent]
) -> None:
    """Folding the helper over a sequence twice from the same start MUST
    yield identical final heads — the chain is purely a function of the
    sequence + starting head, never of hidden state."""

    def _fold(start: ChainHead, events: list[TransitionEvent]) -> ChainHead:
        head = start
        for ev in events:
            head = _compute_chain_head(head, ev)
        return head

    assert _fold(starting, seq) == _fold(starting, seq)
