"""Phase-4 S2-05 AC-15 — ``mypy --strict`` proves ``LeafLlm.invoke`` requires
``BudgetToken``.

ADR-0010's load-bearing claim is that calling ``LeafLlm.invoke(...)``
without a ``BudgetToken`` is a type error — not a runtime check, a
type-system property. This test runs ``mypy --strict`` against a
deliberately-failing fixture and asserts the missing-keyword-argument
diagnostic appears.

This AC is **gated on S3-01** landing
``codegenie.fallback.leaf.protocol.LeafLlm`` — the Protocol the fixture
imports. Until S3-01 ships, ``pytest.importorskip`` cleanly skips this
test. When S3-01 GREENs the skip flips to a real assertion. The
``tests/fence/`` convention is "no skip" (Rule 12) but the story
explicitly allows this single ``importorskip`` because the AC's own goal
is "land standalone; S3-01 turns it green" (story Notes for AC-15).

Tests/`tests/fence/` and tests/fixtures/typecheck/ are mypy-excluded for
the project's main typecheck run (see pyproject), so the failing fixture
does not regress ``make typecheck``. This test runs mypy in a subprocess
against a single fixture file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest

_FIXTURE: Final[Path] = Path("tests/fixtures/typecheck/budget_token_missing.py")


def _resolve_mypy_binary() -> str:
    candidate = Path(sys.executable).parent / "mypy"
    if candidate.exists() and os.access(candidate, os.X_OK):
        return str(candidate)
    on_path = shutil.which("mypy")
    if on_path is not None:
        return on_path
    pytest.fail(
        "`mypy` not found on PATH or next to the venv's python. "
        'Install dev extras (`pip install -e ".[dev]"`).'
    )


def test_invoke_without_budget_token_is_mypy_error() -> None:
    """AC-15 — fixture file must mypy-error with a missing-arg diagnostic.

    Skipped cleanly until S3-01 ships ``codegenie.fallback.leaf.protocol``.
    """
    pytest.importorskip(
        "codegenie.fallback.leaf.protocol",
        reason="AC-15 gated on S3-01 LeafLlm Protocol landing.",
    )
    assert _FIXTURE.is_file(), f"fixture missing: {_FIXTURE}"
    result = subprocess.run(
        [_resolve_mypy_binary(), "--strict", str(_FIXTURE)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, (
        f"`mypy --strict` accepted the fixture — the type-system guard is "
        f"broken.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    combined = (result.stdout + "\n" + result.stderr).lower()
    # Match either of the standard mypy diagnostics for a missing keyword arg.
    assert any(needle in combined for needle in ("missing", "argument", "call-arg")), (
        "mypy failed but the diagnostic did not name a missing-argument "
        f"problem.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
