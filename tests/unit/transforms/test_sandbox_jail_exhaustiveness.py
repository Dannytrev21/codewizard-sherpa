"""Exhaustiveness fence for ``JailedSubprocessResult`` — S4-01 AC-9.

Mirrors the S1-03 ``test_exhaustiveness.py`` precedent. Every variant has a
``match`` arm; the wildcard arm reaches ``assert_never``. Runtime confirms
full coverage today; the subprocess-mypy negative fence at
``test_sandbox_jail_mypy_negative.py`` (AC-9a) is what protects against
silent ``Union`` widening at type-check time.
"""

from __future__ import annotations

from typing import assert_never

from codegenie.transforms.sandbox_jail import (
    Completed,
    DiskQuotaExceeded,
    JailedSubprocessResult,
    NetworkDenied,
    OomKilled,
    TimedOut,
)


def classify(result: JailedSubprocessResult) -> str:
    match result:
        case Completed():
            return "completed"
        case TimedOut():
            return "timed_out"
        case OomKilled():
            return "oom_killed"
        case NetworkDenied():
            return "network_denied"
        case DiskQuotaExceeded():
            return "disk_quota_exceeded"
        case _ as unexpected:
            assert_never(unexpected)


def test_every_variant_classifies() -> None:
    cases: list[tuple[JailedSubprocessResult, str]] = [
        (
            Completed(
                kind="completed",
                exit_code=0,
                stdout_bytes=0,
                stderr_bytes=0,
                wall_time_s=0.0,
            ),
            "completed",
        ),
        (TimedOut(kind="timed_out", budget_s=1.0, elapsed_s=1.0), "timed_out"),
        (OomKilled(kind="oom_killed", peak_rss_mib=1), "oom_killed"),
        (NetworkDenied(kind="network_denied", host="x"), "network_denied"),
        (
            DiskQuotaExceeded(kind="disk_quota_exceeded", quota_bytes=1, bytes_written=2),
            "disk_quota_exceeded",
        ),
    ]
    for variant, expected in cases:
        assert classify(variant) == expected
