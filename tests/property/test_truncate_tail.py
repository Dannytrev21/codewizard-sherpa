"""Hypothesis property tests for ``_truncate_tail`` (S1-07 / AC-13).

Three invariants pin the contract:

1. Length-bound: ``len(_truncate_tail(buf, cap)) <= max(cap, MARKER_LEN)`` and
   exactly ``cap`` when truncation actually occurred.
2. Identity-under-cap: ``len(buf) <= cap`` ⇒ ``_truncate_tail(buf, cap) is buf``
   (the *same object*, not just equal — guards against unneeded copies).
3. Marker + tail discipline: ``len(buf) > cap`` ⇒ result starts with
   ``_TRUNC_MARKER`` AND ends with the original buffer's last
   ``cap - MARKER_LEN`` bytes AND has length exactly ``cap``.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from codegenie.exec import _TRUNC_MARKER, _truncate_tail

MARKER_LEN = len(_TRUNC_MARKER)


@given(
    buf=st.binary(min_size=0, max_size=2048),
    cap=st.integers(min_value=MARKER_LEN + 1, max_value=4096),
)
def test_truncate_tail_length_bound(buf: bytes, cap: int) -> None:
    result = _truncate_tail(buf, cap)
    assert len(result) <= max(cap, MARKER_LEN)


@given(
    buf=st.binary(min_size=0, max_size=2048),
    cap=st.integers(min_value=MARKER_LEN + 1, max_value=4096),
)
def test_truncate_tail_identity_when_under_cap(buf: bytes, cap: int) -> None:
    if len(buf) <= cap:
        assert _truncate_tail(buf, cap) is buf


@given(
    buf=st.binary(min_size=0, max_size=2048),
    cap=st.integers(min_value=MARKER_LEN + 1, max_value=4096),
)
def test_truncate_tail_preserves_marker_prefix_and_tail(
    buf: bytes,
    cap: int,
) -> None:
    if len(buf) > cap:
        result = _truncate_tail(buf, cap)
        assert result.startswith(_TRUNC_MARKER)
        assert result.endswith(buf[-(cap - MARKER_LEN) :])
        assert len(result) == cap
