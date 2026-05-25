"""Phase-4 S4-05 AC-8 — Hypothesis membership property for ``verify``.

For arbitrary 64-hex ``record_head`` values and arbitrary sets of 64-hex
``known_heads``, the assertion is:

    verify(record, log) == (record.provenance.event_chain_head in known_heads)

This single equality kills always-True / always-False / inverted-
membership / wrong-field mutants on the verifier in one property.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from codegenie.rag.provenance import SpanningChainLog, verify
from codegenie.types.identifiers import ChainHead
from tests.fixtures.rag.fake_solved_example import make_solved_example

_HEX_64 = st.text(alphabet="0123456789abcdef", min_size=64, max_size=64)


class _FakeSpanningLog:
    """Set-backed ``SpanningChainLog`` with a call counter for AC-8's
    "exactly-once per non-empty head" pin."""

    def __init__(self, known: frozenset[ChainHead]) -> None:
        self._known = known
        self.calls = 0

    def contains_chain_head(self, head: ChainHead) -> bool:
        self.calls += 1
        return head in self._known


@given(record_head=_HEX_64, known_heads=st.sets(_HEX_64, max_size=8))
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_verify_membership_matches_set_containment(record_head: str, known_heads: set[str]) -> None:
    """AC-8 — pure membership equality across 50 cases."""
    head = ChainHead(record_head)
    known: frozenset[ChainHead] = frozenset(ChainHead(h) for h in known_heads)
    record = make_solved_example(id_="prop-" + record_head[:8], event_chain_head=record_head)
    log = _FakeSpanningLog(known)

    expected = head in known
    actual = verify(record, log)

    assert actual is expected
    # The head is guaranteed non-empty (64 hex chars) so contains_chain_head
    # must have been called exactly once.
    assert log.calls == 1
    # The runtime-checkable Protocol pin from S4-05 AC-2 must still recognise
    # the fake — guards against accidental Protocol-surface widening.
    assert isinstance(log, SpanningChainLog)
