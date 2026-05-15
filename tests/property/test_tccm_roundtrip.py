"""Hypothesis property test for ``codegenie.tccm.DerivedQuery``.

AC-11 of story 02 S1-04: round-trip identity over all five variants ×
random ASCII payloads. Closes the mutation that AC-6's fixed five examples
would not catch (e.g., a payload-encoding bug that activates only for
non-trivial strings).
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
from pydantic import TypeAdapter

from codegenie.tccm import (
    ConsumersOf,
    DerivedQuery,
    ProducersOf,
    RefsTo,
    ReverseLookup,
)

# Alias on import — `TestsExercising` collides with pytest's `Test*` collector.
from codegenie.tccm import TestsExercising as ExerciseTestsQuery

_payload_text = st.text(
    min_size=1,
    max_size=32,
    alphabet=st.characters(min_codepoint=33, max_codepoint=126),
)

_variant_strategy: st.SearchStrategy[DerivedQuery] = st.one_of(
    st.builds(ConsumersOf, pkg=_payload_text),
    st.builds(ProducersOf, pkg=_payload_text),
    st.builds(ReverseLookup, module=_payload_text),
    st.builds(RefsTo, symbol=_payload_text),
    st.builds(ExerciseTestsQuery, symbol=_payload_text),
)


@given(_variant_strategy)
def test_derived_query_roundtrip_property(q: DerivedQuery) -> None:
    adapter: TypeAdapter[DerivedQuery] = TypeAdapter(DerivedQuery)
    decoded = adapter.validate_json(adapter.dump_json(q))
    assert decoded == q
    assert type(decoded) is type(q)
