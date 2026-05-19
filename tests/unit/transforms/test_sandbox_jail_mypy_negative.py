"""Subprocess-mypy fence for ``JailedSubprocessResult`` — S4-01 AC-9a.

Mirrors the S1-03 ``test_outcomes_mypy_negative.py`` precedent. Write a
temp module that ``match``-es over ``JailedSubprocessResult`` with one
arm intentionally missing, then assert ``mypy --strict`` flags
``assert_never(result)`` because mypy cannot narrow the un-handled variant
to ``Never``. Without this guard, a contributor adding a sixth variant
without updating every consumer's ``match`` would silently pass CI.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

FIXTURE = textwrap.dedent(
    """
    from typing import assert_never
    from codegenie.transforms.sandbox_jail import (
        Completed,
        JailedSubprocessResult,
        NetworkDenied,
        OomKilled,
        TimedOut,
    )

    # ``DiskQuotaExceeded`` arm intentionally omitted — mypy must flag.
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
            case _ as unexpected:
                assert_never(unexpected)
        return ""
    """
)


def test_mypy_strict_catches_missing_arm(tmp_path: Path) -> None:
    """``mypy --strict`` rejects the deliberately-incomplete match."""
    fixture = tmp_path / "negative.py"
    fixture.write_text(FIXTURE)
    repo_root = Path(__file__).resolve().parents[3]
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(fixture)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(repo_root),
    )
    combined = (proc.stdout + proc.stderr).lower()
    assert proc.returncode != 0, (
        "mypy --strict accepted a match with a missing variant arm; "
        f"stdout=\n{proc.stdout}\nstderr=\n{proc.stderr}"
    )
    # Mypy emits a message like 'argument has incompatible type ... expected "Never"'.
    assert "never" in combined or "assert_never" in combined or "argument" in combined, (
        "mypy error did not reference the assert_never narrowing failure: "
        f"stdout=\n{proc.stdout}\nstderr=\n{proc.stderr}"
    )
