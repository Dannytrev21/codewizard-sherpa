"""Coverage-of-the-contract test for the Phase 7 ``import-linter`` contract.

Planted-import subprocess test: writes a temp module
``codegenie.primitives.vuln_provenance._test_planted_phase7_leak`` containing
``import torch``, runs ``lint-imports``, asserts non-zero exit AND that
the failure message names both the planted module's containing package and
the forbidden SDK.

ADR-0011 framing: this is **audit + lint** enforcement. A determined PR
that edits this test file alongside the violation defeats the fence —
CODEOWNERS on ``tests/fence/`` is the social anchor. Mirrors the
Phase 3 precedent at ``tests/fence/test_lint_imports_catches_planted_leak.py``.

Phase-4 S1-05 / ADR-0003: the planted SDK is ``torch``, not ``anthropic``.
``anthropic`` is no longer in the Phase-7 contract's ``forbidden_modules``
(it moved to path-scope at the leaf adapter); planting it would pass
vacuously — its mutation guard would be dead. ``torch`` is in the still-
forbidden set, so the test keeps teeth. The test name is preserved for git
blame continuity.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest

_PRIMITIVE_DIR: Final[Path] = Path("src/codegenie/primitives/vuln_provenance")
_PLANTED_MODULE_NAME: Final[str] = "_test_planted_phase7_leak"
_PLANTED_PATH: Final[Path] = _PRIMITIVE_DIR / f"{_PLANTED_MODULE_NAME}.py"
_PLANTED_SDK: Final[str] = "torch"


def _resolve_lint_imports_binary() -> str:
    """Locate the ``lint-imports`` console script.

    Prefers the venv-local entry next to the running interpreter (so
    ``pytest`` invocations inside a venv work without ``PATH`` activation).
    Fails loud (Rule 12) instead of silently skipping.
    """
    candidate = Path(sys.executable).parent / "lint-imports"
    if candidate.exists() and os.access(candidate, os.X_OK):
        return str(candidate)
    on_path = shutil.which("lint-imports")
    if on_path is not None:
        return on_path
    pytest.fail(
        "`lint-imports` not found on PATH or next to the venv's python. "
        'Install dev extras (`pip install -e ".[dev]"`) before running fence tests.'
    )


def _run_importlinter() -> subprocess.CompletedProcess[str]:
    """Run the `import-linter` checker against `pyproject.toml`."""
    return subprocess.run(
        [
            _resolve_lint_imports_binary(),
            "--config",
            "pyproject.toml",
            "--no-cache",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_lint_imports_catches_planted_anthropic_under_primitive() -> None:
    """AC-2: planted ``import {_PLANTED_SDK}`` (currently ``torch``) under
    ``src/codegenie/primitives/vuln_provenance/`` MUST fail ``import-linter``
    AND the failure message MUST name the forbidden module.

    ``finally`` removes the planted file even on assertion failure.

    Phase-4 S1-05 / ADR-0003: ``anthropic`` is no longer in the Phase-7
    contract's ``forbidden_modules``; this test plants ``torch`` (which is)
    to keep the mutation guard alive."""
    assert _PRIMITIVE_DIR.is_dir(), f"Primitive dir missing: {_PRIMITIVE_DIR}"
    assert not _PLANTED_PATH.exists(), (
        f"Stale planted leak file at {_PLANTED_PATH}; remove before re-running."
    )
    try:
        _PLANTED_PATH.write_text(
            f'"""Planted-leak fixture (Phase 7 S1-06 AC-2). DELETE."""\n\n'
            f"import {_PLANTED_SDK}  # noqa: F401\n",
            encoding="utf-8",
        )
        result = _run_importlinter()
        assert result.returncode != 0, (
            f"`import-linter` did NOT fire on planted `{_PLANTED_SDK}` import "
            f"under the Phase 7 primitive. The contract is silently degraded.\n"
            f"stdout:\n{result.stdout}"
        )
        combined = (result.stdout + "\n" + result.stderr).lower()
        assert _PLANTED_SDK in combined, (
            f"Failure message MUST name `{_PLANTED_SDK}` so an operator can act.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        # Also name the phase-7 contract by name so the operator can locate it.
        assert "phase-7" in combined or "vuln_provenance" in combined, (
            "Failure message should reference the Phase 7 contract / primitive "
            f"so an operator can locate the offending contract.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    finally:
        if _PLANTED_PATH.exists():
            _PLANTED_PATH.unlink()


@pytest.fixture(autouse=True)
def _refuse_to_run_if_importlinter_package_missing() -> None:
    """Fail loud (Rule 12) instead of silently skipping if the dev environment
    is missing ``import-linter``."""
    result = subprocess.run(
        [sys.executable, "-c", "import importlinter"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            "import-linter package not installed; install dev extras "
            '(`pip install -e ".[dev]"`) before running tests/fence/.'
        )
