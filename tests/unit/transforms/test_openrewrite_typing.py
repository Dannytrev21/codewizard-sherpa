"""AC-Surface-2(b) — subprocess-mypy positive fence.

``OpenRewriteRecipeEngine`` must structurally satisfy the S5-01
``RecipeEngine`` Protocol under ``mypy --strict``: the ADR-0014 ``apply``
signature returns a bare ``RecipeOutcome``, so a ``RecipeEngine``-typed
binding is assignable. ``mypy --strict`` on the fixture must exit 0. Mirrors
``test_npm_lockfile_typing.py``.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

_FIXTURE = textwrap.dedent(
    """
    from codegenie.transforms.engines.openrewrite import OpenRewriteRecipeEngine
    from codegenie.transforms.recipe_engine import RecipeEngine
    from codegenie.transforms.sandbox_jail import SubprocessJail
    from codegenie.transforms.transform_registry import TransformRegistry


    def check_protocol_conformance(
        jail: SubprocessJail, registry: TransformRegistry
    ) -> RecipeEngine:
        # AC-Surface-2(b): apply's -> RecipeOutcome return matches the Protocol
        # exactly, so the engine is assignable to a RecipeEngine binding.
        engine: RecipeEngine = OpenRewriteRecipeEngine(jail=jail, transform_registry=registry)
        return engine
    """
)


def test_mypy_strict_accepts_protocol_conformance(tmp_path: Path) -> None:
    """AC-Surface-2(b) — ``mypy --strict`` exits 0 on the conformance fixture."""
    fixture = tmp_path / "positive.py"
    fixture.write_text(_FIXTURE)
    repo_root = Path(__file__).resolve().parents[3]
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(fixture)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(repo_root),
    )
    assert proc.returncode == 0, (
        "mypy --strict rejected the OpenRewriteRecipeEngine conformance fixture; "
        f"stdout=\n{proc.stdout}\nstderr=\n{proc.stderr}"
    )
