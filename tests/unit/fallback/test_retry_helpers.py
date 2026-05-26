"""S6-02 unit tests for :func:`codegenie.fallback.tier.select_retry_summary`.

The pure functional core of the retry-bypass branch (ADR-04-0011): returns
``prior_attempts[-1]`` with a defense-in-depth non-empty assertion.

The ``[-1]`` selection is the bug-catcher: a regression to ``[0]`` would be
invisible at N=1 but loud at N∈{2,3}. The unreachable-on-empty assertion
guards against a future refactor flipping the ``bool(prior_attempts)``
guard in :meth:`FallbackTier.run`.
"""

from __future__ import annotations

import pytest

from codegenie.fallback.tier import select_retry_summary
from codegenie.transforms.apply_context import AttemptSummary
from codegenie.types.identifiers import AttemptNumber, SignalKind


def _make_summary(*, attempt: int, signal: str, body: str) -> AttemptSummary:
    return AttemptSummary(
        attempt=AttemptNumber(attempt),
        failing_signals=(SignalKind(signal),),
        prior_failure_summary=body,
        evidence_paths=(),
        transform_id=None,
    )


@pytest.mark.parametrize("n", [1, 2, 3])
def test_select_retry_summary_returns_last_attempt(n: int) -> None:
    """For N attempts, ``select_retry_summary`` returns the **last** —
    not the first. The ``[-1]`` selection is the load-bearing semantic.
    """
    summaries = tuple(
        _make_summary(attempt=i + 1, signal=f"sig.{i}", body=f"body-{i}") for i in range(n)
    )
    assert select_retry_summary(summaries) is summaries[-1]


def test_select_retry_summary_returns_only_attempt_for_n_equals_1() -> None:
    """N=1 sanity — last == first when there is only one."""
    only = _make_summary(attempt=42, signal="sig.x", body="solo")
    assert select_retry_summary((only,)) is only


def test_select_retry_summary_empty_tuple_raises() -> None:
    """The unreachable-on-empty assertion: a future refactor that flips
    the ``bool(prior_attempts)`` guard in :meth:`FallbackTier.run` would
    silently :class:`IndexError`. The assert surfaces it loud instead.
    """
    with pytest.raises(AssertionError, match="unreachable"):
        select_retry_summary(())


def test_select_retry_summary_empty_list_raises() -> None:
    """``bool([])`` and ``bool(())`` are both ``False``; the helper must
    refuse both shapes equally."""
    with pytest.raises(AssertionError, match="unreachable"):
        select_retry_summary([])


def test_select_retry_summary_accepts_list_shape() -> None:
    """``Sequence[AttemptSummary]`` is read-covariant — ``list`` works
    same as ``tuple``. Phase 5's retry envelope passes whichever shape
    its serialization produces; the helper must not care."""
    summaries = [
        _make_summary(attempt=1, signal="sig.0", body="b0"),
        _make_summary(attempt=2, signal="sig.1", body="b1"),
    ]
    assert select_retry_summary(summaries) is summaries[-1]
