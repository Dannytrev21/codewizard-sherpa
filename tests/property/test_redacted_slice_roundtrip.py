"""S7-05 AC-12 — Hypothesis round-trip property over ``RedactedSlice``.

Every Hypothesis example is obtained via :func:`redact_secrets` (the
**only** legal construction surface per 02-ADR-0010 — the smart
constructor pattern). The test asserts JSON round-trip identity via a
:class:`~pydantic.TypeAdapter`. The S7-04 structural firewall (no
``RedactedSlice(...)`` direct construction outside
``codegenie.output.sanitizer``) is unaffected: this file never
constructs the model directly — it exclusively threads synthetic dicts
through ``redact_secrets`` to obtain instances.

Settings discipline (AC-35): ``database=None`` for CI reproducibility,
``deadline=None`` because round-trip latency is variable on CI,
``max_examples=200`` to match the rest of the Phase-2 property surface.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import TypeAdapter

from codegenie.output.redacted_slice import RedactedSlice
from codegenie.output.sanitizer import redact_secrets
from codegenie.parsers import JSONValue
from codegenie.types.identifiers import ProbeId

# ---------------------------------------------------------------------------
# JSONValue strategy with bounded depth (mirrors test_sum_types_roundtrip).
# ---------------------------------------------------------------------------

_printable_ascii = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    min_size=0,
    max_size=32,
)

_json_value: st.SearchStrategy[JSONValue] = st.recursive(
    st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-(2**31), max_value=2**31 - 1),
        st.floats(allow_nan=False, allow_infinity=False, width=32),
        _printable_ascii,
    ),
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(_printable_ascii, children, max_size=4),
    ),
    max_leaves=8,
)

_slice_payload: st.SearchStrategy[dict[str, JSONValue]] = st.dictionaries(
    _printable_ascii.filter(lambda s: len(s) >= 1),
    _json_value,
    max_size=4,
)

_adapter: TypeAdapter[RedactedSlice] = TypeAdapter(RedactedSlice)
_PROBE_NAME = ProbeId("test.property")


@given(payload=_slice_payload)
@settings(max_examples=200, deadline=None, database=None)
def test_redacted_slice_roundtrips_identity(payload: dict[str, JSONValue]) -> None:
    """Every ``RedactedSlice`` obtained via the smart constructor JSON-round-trips.

    The legal-construction discipline is verified at the test boundary:
    every example transits ``redact_secrets`` before reaching the
    ``TypeAdapter``. A regression in the model invariants
    (fingerprint regex, count-vs-fingerprints ordering, ``frozen``,
    ``extra="forbid"``) would surface as a round-trip identity mismatch
    or a Pydantic ``ValidationError`` on the post-decode revalidation.
    """
    redacted, _ = redact_secrets(payload, probe_name=_PROBE_NAME)

    encoded = _adapter.dump_json(redacted)
    decoded = _adapter.validate_json(encoded)

    # Identity equality + concrete-type preservation.
    assert decoded == redacted
    assert type(decoded) is type(redacted)

    # Structural invariants the model enforces — sanity-check at boundary.
    assert decoded.findings_count >= len(decoded.fingerprints)
    for fp in decoded.fingerprints:
        assert len(fp) == 8
        assert all(c in "0123456789abcdef" for c in fp)
