"""S8-03 AC-10b — boundary-parametrized tests for ``compare_to_baseline``.

The hosted-runner bench (``bench_portfolio_walltime_hosted_runner.py``) is the
single Phase-2 bench script that gates the build. Two independent thresholds
fire ``Verdict.Fail``: ``>= 100%`` regression OR ``> 360s`` p95 walltime
(arch §"Gap 2"). A wrong implementation that swaps either inclusivity
(``>`` vs ``>=``) at the boundary silently flips the gate. These parametrize
the boundaries explicitly.
"""

from __future__ import annotations

import pytest

from tests.bench._bench_kernel import (
    CommentOnly,
    Fail,
    Ok,
    Threshold,
    Verdict,
    compare_to_baseline,
)

# Default Phase-2 hosted-runner thresholds (arch §"Gap 2").
_T = Threshold(comment_pct=50.0, fail_pct=100.0, fail_p95_s=360.0)


def _verdict_kind(v: Verdict) -> type[Ok | CommentOnly | Fail]:
    return type(v)


@pytest.mark.parametrize(
    "pct,expected",
    [
        (-10.0, Ok),  # improvement → Ok
        (0.0, Ok),  # parity → Ok
        (49.9, Ok),  # below comment threshold
        (50.0, CommentOnly),  # comment boundary (inclusive)
        (99.0, CommentOnly),  # comment range, below fail
        (99.999, CommentOnly),
        (100.0, Fail),  # fail boundary (inclusive)
        (101.0, Fail),  # over fail
        (500.0, Fail),  # catastrophic
    ],
)
def test_regression_pct_boundary_classification(pct: float, expected: type) -> None:
    baseline = {"only_fixture": 100.0}
    measurements = {"only_fixture": 100.0 * (1.0 + pct / 100.0)}
    verdict = compare_to_baseline(measurements, baseline, _T, p95_seconds=0.0)
    assert _verdict_kind(verdict) is expected, (
        f"regression {pct}% must classify as {expected.__name__}; got {verdict}"
    )


@pytest.mark.parametrize(
    "p95,expected",
    [
        (0.0, Ok),
        (359.0, Ok),
        (360.0, Ok),  # ``>`` is strict — 360 exactly is still Ok
        (360.001, Fail),  # strictly above triggers Fail
        (361.0, Fail),
        (1000.0, Fail),
    ],
)
def test_p95_threshold_boundary_classification(p95: float, expected: type) -> None:
    baseline = {"only_fixture": 100.0}
    # measurement at parity so the only failing axis is p95.
    measurements = {"only_fixture": 100.0}
    verdict = compare_to_baseline(measurements, baseline, _T, p95_seconds=p95)
    assert _verdict_kind(verdict) is expected, (
        f"p95={p95}s must classify as {expected.__name__}; got {verdict}"
    )


def test_either_threshold_triggers_fail_independently() -> None:
    """AC-10b — the two thresholds are independent (boolean OR, arch §Gap 2)."""
    baseline = {"x": 100.0}
    # Regression below fail AND p95 below ceiling → Ok or CommentOnly.
    v_neither = compare_to_baseline({"x": 150.0}, baseline, _T, p95_seconds=100.0)
    assert isinstance(v_neither, CommentOnly)
    # Regression at fail boundary alone → Fail.
    v_regression_only = compare_to_baseline({"x": 200.0}, baseline, _T, p95_seconds=100.0)
    assert isinstance(v_regression_only, Fail)
    # p95 alone → Fail.
    v_p95_only = compare_to_baseline({"x": 100.0}, baseline, _T, p95_seconds=400.0)
    assert isinstance(v_p95_only, Fail)


def test_comment_only_threshold_alone_does_not_fail() -> None:
    """Without ``fail_pct`` or ``fail_p95_s``, the kernel never returns Fail."""
    advisory = Threshold(comment_pct=10.0)
    v = compare_to_baseline({"x": 1000.0}, {"x": 100.0}, advisory, p95_seconds=100000.0)
    assert isinstance(v, CommentOnly)


def test_missing_baseline_key_is_silently_skipped() -> None:
    """A new fixture absent from baseline is not a Fail — it's the refresh ritual."""
    v = compare_to_baseline(
        {"new_fixture": 999.0, "known": 100.0},
        {"known": 100.0},
        _T,
        p95_seconds=0.0,
    )
    assert isinstance(v, Ok), "new fixture must NOT trigger a regression"


def test_zero_baseline_does_not_divide_by_zero() -> None:
    """Defensive: zero baseline yields 0% regression, not ZeroDivisionError."""
    v = compare_to_baseline({"x": 5.0}, {"x": 0.0}, _T, p95_seconds=0.0)
    assert isinstance(v, Ok)
