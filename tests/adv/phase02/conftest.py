"""Per-test fixtures for the Phase 2 adversarial corpus (S4-02).

Registers only the ``fixture_path`` helper — the ``phase02_adv`` pytest
marker is registered in ``pyproject.toml`` (the existing Phase 0/1
convention), not here, to avoid double-registration drift (S4-02 AC-7).

Also installs a session-scoped autouse fixture that ensures the
`stale-scip` fixture is materialized (`regenerate.sh` invoked once per
session) before any test in this directory runs. This makes the
adversarial self-bootstrapping on CI (where no human runs
`regenerate.sh` first) while preserving the loud-fail diagnostics
inside the test for genuine environment bugs (missing `git`, `bash`).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "portfolio" / "stale-scip"
_SLICE_PATH = _FIXTURE / ".codegenie" / "context" / "raw" / "scip.json"


@pytest.fixture(autouse=True, scope="session")
def _materialize_stale_scip_fixture() -> None:
    """Run `regenerate.sh` once per test session if the artifacts are missing.

    The fixture's `.git/` and `.codegenie/` are gitignored runtime state by
    design (S4-02 §"Files to touch" — DP2 seed-vs-runtime split). On CI
    nothing pre-materializes them, so the conftest does it.

    `pytest.fail`s loudly if `git`/`bash` are missing or `regenerate.sh`
    exits non-zero — those are real developer-environment bugs (Rule 12).
    """
    if _SLICE_PATH.exists() and (_FIXTURE / ".git").exists():
        return
    if shutil.which("bash") is None:
        pytest.fail("`bash` is required to materialize the stale-scip fixture; not on $PATH.")
    if shutil.which("git") is None:
        pytest.fail("`git` is required to materialize the stale-scip fixture; not on $PATH.")
    result = subprocess.run(  # noqa: S603 — fixture script, path-controlled.
        ["./regenerate.sh"],
        cwd=_FIXTURE,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"regenerate.sh failed (exit {result.returncode}); "
            f"stdout={result.stdout!r}; stderr={result.stderr!r}"
        )


@pytest.fixture
def fixture_path() -> Path:
    """Resolve to ``tests/fixtures/portfolio/stale-scip/``.

    Walks up from this conftest to the ``tests/`` root, then into the
    portfolio fixture directory. Future Phase-2 adversarials will share
    this helper (rule-of-three trigger to lift it into a `_helpers.py`).
    """
    return Path(__file__).parent.parent.parent / "fixtures" / "portfolio" / "stale-scip"
