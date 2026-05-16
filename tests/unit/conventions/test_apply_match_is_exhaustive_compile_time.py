"""S2-02 AC-9 compile-time half — ``warn_unreachable`` rejects an incomplete
``match: ConventionRule`` that ends in ``assert_never``.

The repo-wide ``warn_unreachable = true`` setting (Phase 0) turns the
load-bearing exhaustiveness check from a runtime catch into a mypy build
failure. This test invokes mypy on a deliberately-incomplete fixture and
asserts mypy returns non-zero with an unreachable diagnostic.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "mypy_warn_unreachable"
    / "incomplete_match_conventions.py"
)


def test_incomplete_conventions_match_fails_mypy_strict() -> None:
    assert FIXTURE.exists(), f"fixture missing: {FIXTURE}"
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(FIXTURE)],
        capture_output=True,
        text=True,
        check=False,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        "mypy --strict must reject the incomplete match; "
        f"got exit 0; output:\n{combined}"
    )
    needles = (
        "unreachable",
        'Argument 1 to "assert_never"',
        "Statement is unreachable",
    )
    assert any(n in combined for n in needles), (
        f"mypy failure must name unreachable/assert_never; got:\n{combined}"
    )
