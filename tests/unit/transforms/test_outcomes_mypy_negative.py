"""Subprocess-mypy fence — S1-03 AC-9a.

This is the *type-time* enforcement that makes the type-system catch silent
``Union`` widening: write a temp module that ``match``-es over
``RecipeOutcome`` with one arm intentionally missing, then assert
``mypy --strict`` flags ``assert_never(unexpected)`` because mypy cannot
narrow ``unexpected`` to ``Never``. Without this guard, a contributor who
adds a fifth ``RecipeOutcome`` variant without updating every consumer's
``match`` would silently pass CI.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

FIXTURE = textwrap.dedent(
    """
    from typing import assert_never
    from codegenie.transforms.outcomes import (
        RecipeOutcome, Applied, Skipped, RecipeNotApplicable,
    )
    # Intentionally missing the ``RecipeFailed`` arm:
    def describe(o: RecipeOutcome) -> str:
        match o:
            case Applied():
                return "a"
            case Skipped():
                return "s"
            case RecipeNotApplicable():
                return "n"
            case _ as unexpected:
                assert_never(unexpected)  # mypy must flag — RecipeFailed unaccounted-for
        return ""
    """
)


def test_assert_never_catches_missing_arm(tmp_path: Path) -> None:
    """``mypy --strict`` rejects the deliberately-incomplete match."""
    f = tmp_path / "negative.py"
    f.write_text(FIXTURE)
    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(f)],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        check=False,
    )
    assert result.returncode != 0, (
        f"mypy unexpectedly accepted an incomplete match.\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "assert_never" in combined, (
        f"expected 'assert_never' error in mypy output; got:\n{combined}"
    )
