"""Phase 4 S1-03 — ``assert_never`` exhaustiveness over ``PlanOutcome`` via mypy.

Subprocesses ``mypy --strict`` against a temp file whose ``match`` deliberately
omits one variant. ``assert_never`` in the default arm forces an exhaustiveness
diagnostic; we assert both (a) non-zero exit, and (b) a marker substring in
stdout proving the failure was an exhaustiveness diagnostic, not an unrelated
mypy error (import resolution, missing stubs). F5.

Mirrors the HARDENED S1-02 ``test_plan_proposal_match_exhaustive.py``.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("mypy")  # F5 — missing mypy => skip, not a false pass/fail.

OMITTED = ["AppliedFromRecipe", "AppliedFromLlm", "RagOnlyApplicable", "Refused"]

# Substrings proving the failure is the EXHAUSTIVENESS diagnostic — F5.
# ``assert_never``'s arg is typed ``Never``; an unhandled variant makes mypy
# flag the ``assert_never`` call site, surfacing as one of:
#   * "argument 1 to ..." referencing ``assert_never``;
#   * an "unreachable" diagnostic on the default arm;
#   * "Missing" in some mypy versions.
_EXHAUSTIVENESS_MARKERS = ("assert_never", "unreachable", "missing")


def _src(omit: str) -> str:
    arms = "\n".join(
        f"                case {v}():\n                    pass" for v in OMITTED if v != omit
    )
    return textwrap.dedent(
        f"""
        from typing import assert_never
        from codegenie.fallback.plan_outcome import (
            PlanOutcome, AppliedFromRecipe, AppliedFromLlm,
            RagOnlyApplicable, Refused,
        )

        def consume(p: PlanOutcome) -> None:
            match p:
{arms}
                case _ as never:
                    assert_never(never)
        """
    )


@pytest.mark.parametrize("omit", OMITTED)
def test_mypy_strict_rejects_incomplete_plan_outcome_match(tmp_path: Path, omit: str) -> None:
    tmp = tmp_path / "match.py"
    tmp.write_text(_src(omit))
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(tmp)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, (
        f"mypy --strict accepted incomplete PlanOutcome match (missing {omit}); "
        f"stdout:\n{result.stdout}"
    )
    out = result.stdout.lower()
    assert any(m in out for m in _EXHAUSTIVENESS_MARKERS), (
        f"mypy failed but not for an exhaustiveness reason (missing {omit}); "
        f"stdout:\n{result.stdout}"
    )


def test_mypy_strict_accepts_complete_plan_outcome_match(tmp_path: Path) -> None:
    full = textwrap.dedent(
        """
        from typing import assert_never
        from codegenie.fallback.plan_outcome import (
            PlanOutcome, AppliedFromRecipe, AppliedFromLlm,
            RagOnlyApplicable, Refused,
        )

        def consume(p: PlanOutcome) -> None:
            match p:
                case AppliedFromRecipe():
                    pass
                case AppliedFromLlm():
                    pass
                case RagOnlyApplicable():
                    pass
                case Refused():
                    pass
                case _ as never:
                    assert_never(never)
        """
    )
    tmp = tmp_path / "full.py"
    tmp.write_text(full)
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(tmp)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"mypy --strict rejected complete match: {result.stdout}"
    assert "error:" not in result.stdout.lower(), result.stdout
