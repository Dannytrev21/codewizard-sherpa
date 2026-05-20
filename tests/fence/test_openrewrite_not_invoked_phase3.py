"""AC-Tool-4 fence — the OpenRewrite engine is never invoked by a Phase-3
npm workflow.

S5-03 ships ``OpenRewriteRecipeEngine`` as a *scaffold* (ADR-0009): it is
Protocol-conformant and structurally complete, but no Phase-3 npm
remediation routes through it. The only sanctioned importer under
``src/codegenie/`` is ``transforms/__init__.py`` (the additive re-export).
A grep that finds the engine imported anywhere else in ``src/`` or
``plugins/`` is a Phase-3 invocation leak. Phase 7's distroless plugin is the
first legitimate consumer.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_IMPORT_NEEDLE = "from codegenie.transforms.engines.openrewrite"
_ALLOWED_SUFFIXES = ("transforms/__init__.py",)


def test_openrewrite_engine_not_imported_from_phase3_code() -> None:
    """AC-Tool-4 — no ``src/`` or ``plugins/`` module imports the engine
    except the ``transforms/__init__.py`` re-export."""
    search_roots = [
        str(p) for p in (_REPO_ROOT / "src" / "codegenie", _REPO_ROOT / "plugins") if p.exists()
    ]
    result = subprocess.run(
        ["git", "grep", "-l", _IMPORT_NEEDLE, "--", *search_roots],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_REPO_ROOT),
    )
    # `git grep -l` exits 1 with empty stdout when there are zero matches.
    leaks = [
        line for line in result.stdout.splitlines() if line and not line.endswith(_ALLOWED_SUFFIXES)
    ]
    assert leaks == [], f"Phase-3 OpenRewrite invocation leak: {leaks}"
