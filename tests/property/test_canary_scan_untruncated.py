"""Phase-4 S2-03 AC-6 — Hypothesis property: scan fires past truncation cap.

The load-bearing structural fix from ADR-0013: scan **untruncated**, then
truncate. For any payload longer than the largest source-kind cap (16 KB
``source_snippet``), if an injection pattern is hidden past byte ``cap``,
the scan must still fire AND report the exact ``pattern_id``.

Asserting the exact pattern_id (not merely ``isinstance(CanaryCollision)``)
also enforces AC-2's no-substring-shadowing invariant: a shadowed pattern
would cause ``scan_pure`` to return the shadowing id and this property
would fail. That is intended. If this test fails with an id mismatch, the
bug is a shadowed corpus entry (fix INJECTION_PATTERNS); never weaken this
assertion.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from codegenie.fallback.fence.canary import INJECTION_PATTERNS, scan_pure
from codegenie.fallback.fence.wrapper import CanaryCollision


@given(
    prefix_kb=st.integers(min_value=17, max_value=64),
    pattern_idx=st.integers(min_value=0, max_value=len(INJECTION_PATTERNS) - 1),
)
@settings(max_examples=500, deadline=None)
def test_pattern_hidden_past_largest_cap_is_still_detected(
    prefix_kb: int, pattern_idx: int
) -> None:
    """The byte count past the 16 KB source_snippet cap ensures the pattern
    sits in the would-have-been-truncated zone. The b"X" filler contains no
    injection-pattern bytes (AC-2's non-empty + real-corpus invariants keep
    this true for the seed corpus)."""
    pid, pat = INJECTION_PATTERNS[pattern_idx]
    payload_bytes = b"X" * (prefix_kb * 1024) + pat
    payload = payload_bytes.decode("utf-8", errors="ignore")
    result = scan_pure(payload, INJECTION_PATTERNS)
    assert isinstance(result, CanaryCollision)
    assert result.pattern_id == pid
