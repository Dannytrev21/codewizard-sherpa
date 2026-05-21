"""Subprocess-mypy fence — S6-03 AC-19.

Type-time enforcement that ``assert_never`` catches a silently-widened
``NodeTransition``: write a temp module that ``match``-es over the union
with one variant arm intentionally missing, then assert ``mypy --strict``
flags ``assert_never(unexpected)`` because mypy cannot narrow ``unexpected``
to ``Never``. Mirrors ``tests/unit/transforms/test_outcomes_mypy_negative.py``.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

FIXTURE = textwrap.dedent(
    """
    from typing import assert_never
    from codegenie.plugins.subgraph import (
        NodeTransition, Advance, ShortCircuit,
    )
    # Intentionally missing the ``Escalate`` arm:
    def describe(t: NodeTransition) -> str:
        match t:
            case Advance():
                return "a"
            case ShortCircuit():
                return "s"
            case _ as unexpected:
                assert_never(unexpected)  # mypy must flag — Escalate unaccounted-for
        return ""
    """
)


def test_assert_never_catches_missing_arm_node_transition(tmp_path: Path) -> None:
    """``mypy --strict`` rejects the deliberately-incomplete NodeTransition match."""
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
