"""S2-03 AC-13 — coverage ratchet for the ``DerivedQuery`` dispatcher.

Production ADR-0030 §Consequences ratchet: a sixth ``DerivedQuery`` variant
cannot land green without a corresponding ``case`` arm in every consumer's
``match``. Repo-wide ``warn_unreachable = true`` (Phase 0 ``pyproject.toml``)
turns the missing arm into a mypy build failure — same shape S1-11 already
uses for ``IndexFreshness``.

The fixture
``tests/fixtures/mypy_warn_unreachable/incomplete_derived_query_dispatch.py``
deliberately omits four of five ``case`` arms; ``mypy --strict`` must reject
it. If this test ever passes mypy clean, the repo-wide setting has silently
broken.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "mypy_warn_unreachable"
    / "incomplete_derived_query_dispatch.py"
)


def test_dispatcher_match_arms_are_under_mypy_warn_unreachable_ratchet() -> None:
    assert FIXTURE.exists(), f"fixture missing: {FIXTURE}"
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(FIXTURE)],
        capture_output=True,
        text=True,
        check=False,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        "mypy --strict must reject the incomplete DerivedQuery match "
        "(warn_unreachable invariant); "
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
