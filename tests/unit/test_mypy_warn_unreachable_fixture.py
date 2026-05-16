"""S1-11 — automated mypy ``warn_unreachable`` fixture test (AC-5).

Replaces the original draft's manual ``delete-an-arm`` procedure. With
``warn_unreachable = true`` repo-wide (Phase 0 S1-02), mypy must reject a
deliberately-incomplete ``match: IndexFreshness`` ending in
``assert_never(value)``. If this test ever passes mypy clean, the repo-wide
setting has silently broken — exactly the failure mode 02-ADR-0006
§Consequences names.

Sources:

- ``docs/phases/02-context-gather-layers-b-g/stories/S1-11-forbidden-patterns-mypy-adrs.md``
  §AC-5.
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0006-index-freshness-sum-type-location.md``
  §Consequences.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "mypy_warn_unreachable"
    / "incomplete_match.py"
)


def test_incomplete_match_fails_mypy_strict() -> None:
    """AC-5 — automates the ``delete-an-arm`` procedure.

    The fixture is a deliberately-incomplete ``match: IndexFreshness`` ending
    in ``assert_never(value)``. With ``warn_unreachable = true`` enabled
    repo-wide, mypy must reject this fixture under ``--strict``.
    """
    assert FIXTURE.exists(), f"fixture missing: {FIXTURE}"
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(FIXTURE)],
        capture_output=True,
        text=True,
        check=False,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        "mypy --strict must reject the incomplete match (warn_unreachable invariant); "
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
