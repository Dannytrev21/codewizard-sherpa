"""S7-03 AC-28 / AC-30 — golden-file harness.

Invokes ``scripts/regen_golden.py --check --portfolio`` and asserts exit
code 0. On mismatch, the failure message surfaces the path + the
unified-diff stderr output.

The portfolio ``index_health`` goldens assert SCIP freshness
(``scip: fresh``), so this test requires ``scip-typescript`` on PATH —
``@requires_tool`` skips it loudly otherwise. CI installs the pinned tool
(``.github/workflows/ci.yml``); a developer box without it gets a
``SKIPPED LOUD`` reason instead of a confusing golden mismatch.
"""

from __future__ import annotations

import subprocess  # noqa: S404 — tests/ scope; subprocess ban applies under src/
import sys
from pathlib import Path

from tests._ci_support.requires_tool import requires_tool

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REGEN_SCRIPT = _REPO_ROOT / "scripts" / "regen_golden.py"


@requires_tool("scip-typescript")
def test_goldens_match_live_output() -> None:
    """Run ``regen_golden.py --check --portfolio`` and assert zero diffs."""
    result = subprocess.run(
        [sys.executable, str(_REGEN_SCRIPT), "--check", "--portfolio"],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, (
        "Golden mismatch — run "
        "`python scripts/regen_golden.py --update --portfolio` after "
        "investigating each diff. stderr follows:\n"
        f"{result.stderr}"
    )
