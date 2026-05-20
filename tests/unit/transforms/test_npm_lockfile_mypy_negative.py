"""AC-4g2 — subprocess-mypy fence for the engine's ``JailedSubprocessResult``
mapping.

Write a temp module that ``match``-es over ``JailedSubprocessResult`` with one
arm intentionally missing, then assert ``mypy --strict`` flags
``assert_never`` because it cannot narrow the un-handled variant to ``Never``.
Without this guard a contributor who widens the union (or deletes a variant)
would silently pass the runtime exhaustiveness AC. Mirrors
``test_sandbox_jail_mypy_negative.py``.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

# ``JailSetupFailed`` arm intentionally omitted — mypy --strict must reject.
_FIXTURE = textwrap.dedent(
    """
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
        return ""
    """
)


def test_mypy_strict_catches_missing_jail_result_arm(tmp_path: Path) -> None:
    """AC-4g2 — ``mypy --strict`` rejects a match missing the ``JailSetupFailed``
    arm."""
    fixture = tmp_path / "negative.py"
    fixture.write_text(_FIXTURE)
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
        "mypy --strict accepted a match with a missing JailedSubprocessResult "
        f"arm; stdout=\n{proc.stdout}\nstderr=\n{proc.stderr}"
    )
    assert "never" in combined or "assert_never" in combined or "argument" in combined, (
        f"mypy error did not reference the assert_never narrowing failure: "
        f"stdout=\n{proc.stdout}\nstderr=\n{proc.stderr}"
    )
