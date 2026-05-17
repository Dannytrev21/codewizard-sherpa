"""S5-05 — Hypothesis purity / totality property test (AC-10).

For every drawn input:
- The function returns exactly one of ``Fresh | Stale`` (totality —
  never raises, never returns ``None``).
- Two calls with the same input return equal values (purity — no hidden
  state).
- Wall-clock between two calls with the same input stays under a soft
  budget — the structural defense against I/O sneaking into the function
  is the AST audit (``test_runtime_trace_freshness_purity.py``), not this
  timing check.
"""

from __future__ import annotations

import time

from hypothesis import given, settings
from hypothesis import strategies as st

from codegenie.indices.freshness import Fresh, Stale
from codegenie.probes.layer_c.runtime_trace import _check_runtime_trace_freshness

# A reasonably broad slice strategy: keys may or may not be present; values
# include ``None``, strings, ints, bools, and lists. Coverage extends across
# the type-validation branch + the digest comparison branches.
_digest_values = st.one_of(
    st.none(),
    st.text(min_size=0, max_size=80),
    st.integers(),
    st.booleans(),
    st.lists(st.text(max_size=8), max_size=3),
)

_timestamp_values = st.one_of(
    st.none(),
    st.text(max_size=60),
    st.integers(),
    st.just("2026-05-17T00:00:00+00:00"),
    st.just("not-a-timestamp"),
)

_confidence_values = st.one_of(
    st.just("high"),
    st.just("medium"),
    st.just("low"),
    st.just("unavailable"),
    st.text(max_size=20),
    st.none(),
)


def _slice_dict() -> st.SearchStrategy[dict[str, object]]:
    return st.fixed_dictionaries(
        {},
        optional={
            "built_image_digest": _digest_values,
            "last_traced_image_digest": _digest_values,
            "last_traced_at": _timestamp_values,
            "trace_coverage_confidence": _confidence_values,
        },
    )


@given(slice_=_slice_dict(), head=st.text(max_size=40))
@settings(max_examples=300, deadline=None)
def test_totality_and_purity(slice_: dict[str, object], head: str) -> None:
    result_a = _check_runtime_trace_freshness(slice_, head)
    result_b = _check_runtime_trace_freshness(slice_, head)
    # Totality: returns exactly one of Fresh | Stale; never None.
    assert isinstance(result_a, (Fresh, Stale))
    # Purity: same input → same output (Pydantic models compare by field).
    assert result_a == result_b


@given(slice_=_slice_dict(), head=st.text(max_size=40))
@settings(max_examples=80, deadline=None)
def test_wall_clock_under_soft_budget(slice_: dict[str, object], head: str) -> None:
    """Soft signal: two consecutive calls share inputs and stay under 50 ms.

    The structural defense (no I/O / no clock) is the AST audit in
    ``test_runtime_trace_freshness_purity.py``. This test is the
    operator-facing canary — a sudden 100x slowdown surfaces here even if
    a contributor sneaks a subprocess shell in another seam.
    """
    t0 = time.perf_counter()
    _check_runtime_trace_freshness(slice_, head)
    _check_runtime_trace_freshness(slice_, head)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 50, f"elapsed_ms={elapsed_ms!r}; soft budget is 50 ms"
