"""Phase 4 S1-02 — ``assert_never`` exhaustiveness over ``PlanProposal`` via mypy.

Subprocesses ``mypy --strict`` against a temp file whose ``match`` deliberately
omits one variant. ``assert_never`` in the default arm forces an exhaustiveness
diagnostic; we assert both (a) non-zero exit, and (b) a marker substring in
stdout proving the failure was an exhaustiveness diagnostic, not an unrelated
mypy error (import resolution, missing stubs). F4 / F18.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("mypy")  # F18 — missing mypy => skip, not a false pass/fail.

OMITTED = [
    "PlanProposalDepBump",
    "PlanProposalOverride",
    "PlanProposalCallsiteRewrite",
    "PlanProposalRefuse",
]

# Substrings proving the failure is the EXHAUSTIVENESS diagnostic — F4. mypy
# reports the unhandled variant by typing ``never`` (the last-arm capture)
# against ``assert_never``'s ``Never`` parameter, which surfaces as one of:
#   * "argument 1 to ..." referencing ``assert_never``;
#   * an "unreachable" diagnostic on the default arm;
#   * "Missing" in some mypy versions.
_EXHAUSTIVENESS_MARKERS = ("assert_never", "unreachable", "missing")


def _src(omit: str) -> str:
    # Arms render at column 16 (8 leading spaces of dedent + 8 to match the
    # ``case _ as never:`` indent under ``match p:`` after dedent strips 8).
    arms = "\n".join(
        f"                case {v}():\n                    pass" for v in OMITTED if v != omit
    )
    return textwrap.dedent(
        f"""
        from typing import assert_never
        from codegenie.fallback.plan_proposal import (
            PlanProposal, PlanProposalDepBump, PlanProposalOverride,
            PlanProposalCallsiteRewrite, PlanProposalRefuse,
        )

        def consume(p: PlanProposal) -> None:
            match p:
{arms}
                case _ as never:
                    assert_never(never)
        """
    )


@pytest.mark.parametrize("omit", OMITTED)
def test_mypy_strict_rejects_incomplete_match(tmp_path: Path, omit: str) -> None:
    src = _src(omit)
    tmp = tmp_path / "match.py"
    tmp.write_text(src)
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(tmp)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, (
        f"mypy --strict accepted match block missing {omit}; stdout:\n{result.stdout}"
    )
    out = result.stdout.lower()
    assert any(m in out for m in _EXHAUSTIVENESS_MARKERS), (
        f"mypy failed but not for an exhaustiveness reason (missing {omit}); "
        f"stdout:\n{result.stdout}"
    )


def test_mypy_strict_accepts_complete_match(tmp_path: Path) -> None:
    full = textwrap.dedent(
        """
        from typing import assert_never
        from codegenie.fallback.plan_proposal import (
            PlanProposal, PlanProposalDepBump, PlanProposalOverride,
            PlanProposalCallsiteRewrite, PlanProposalRefuse,
        )

        def consume(p: PlanProposal) -> None:
            match p:
                case PlanProposalDepBump():
                    pass
                case PlanProposalOverride():
                    pass
                case PlanProposalCallsiteRewrite():
                    pass
                case PlanProposalRefuse():
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
