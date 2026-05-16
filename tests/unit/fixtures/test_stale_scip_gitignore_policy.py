"""S4-02 AC-12 — seed-vs-runtime split is enforced by `.gitignore`.

Asserts via `git check-ignore`:
- `tests/fixtures/portfolio/stale-scip/.git/` is ignored.
- `tests/fixtures/portfolio/stale-scip/.codegenie/...scip.json` is ignored.
- `tests/fixtures/portfolio/stale-scip/_seed/scip-slice.template.json` is
  tracked (NOT ignored — exit code 1 from `git check-ignore`).

The unit protects the seed-vs-runtime split: if a future contributor
accidentally commits regenerated `.codegenie/` content (or vendors `.git/`),
the assertions catch it before the adversarial reaches CI.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent.parent
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "portfolio" / "stale-scip"


def _check_ignore(path: Path) -> int:
    result = subprocess.run(  # noqa: S603 — local git, path-controlled.
        ["git", "check-ignore", str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode


def test_fixture_gitignore_policy() -> None:
    if shutil.which("git") is None:
        pytest.fail("`git` is required for git check-ignore; not on $PATH.")

    # Tracked (seed material): expected NOT ignored → exit code 1.
    seed = FIXTURE / "_seed" / "scip-slice.template.json"
    assert seed.exists(), f"seed template missing at {seed}"
    assert _check_ignore(seed) == 1, (
        f"Seed template {seed} must be tracked (not gitignored); "
        "the seed-vs-runtime split requires this file in git history."
    )

    # Runtime (`.git/`): expected ignored → exit code 0.
    inner_git = FIXTURE / ".git"
    assert _check_ignore(inner_git) == 0, (
        f"{inner_git} must be gitignored. Fixture-local `.gitignore` should "
        "exclude `.git/`; otherwise `git add -f` could vendor a nested work "
        "tree (which Git would also refuse, but defense-in-depth)."
    )

    # Runtime (`.codegenie/...`): expected ignored → exit code 0.
    runtime_slice = FIXTURE / ".codegenie" / "context" / "raw" / "scip.json"
    assert _check_ignore(runtime_slice) == 0, (
        f"{runtime_slice} must be gitignored (repo-wide `.gitignore` covers "
        "`.codegenie/` everywhere; fixture-local `.gitignore` reinforces it)."
    )
