"""Pin the ``Makefile`` ``fence:`` target invocation to the full Phase 3 set.

A simple but load-bearing meta-test. If a future cleanup narrows ``make
fence`` back to just the Phase 0 scan, the new Phase 3 fences would no
longer be locally invokable via the canonical command — and the CI gate
documented at ``phase-arch-design.md §Testing strategy §CI gates`` (line
1042) would silently drift.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

_MAKEFILE_PATH: Final[Path] = Path("Makefile")

_REQUIRED_PATHS_IN_FENCE_RECIPE: Final[tuple[str, ...]] = (
    "tests/unit/test_pyproject_fence.py",
    "tests/fence/",
)


def _read_fence_recipe() -> str:
    """Return everything between ``fence:`` and the next non-recipe line."""
    text = _MAKEFILE_PATH.read_text(encoding="utf-8")
    # Recipe lines in Make are tab-indented; everything until the next
    # non-tab-indented non-blank line is part of the recipe.
    lines = text.splitlines()
    out: list[str] = []
    in_recipe = False
    for line in lines:
        if not in_recipe:
            if re.match(r"^fence\s*:", line):
                in_recipe = True
            continue
        if line == "" or line.startswith("\t") or line.startswith("    "):
            out.append(line)
        else:
            break
    assert out, "Could not locate Makefile `fence:` recipe body"
    return "\n".join(out)


def test_fence_recipe_invokes_phase0_scan() -> None:
    recipe = _read_fence_recipe()
    assert "tests/unit/test_pyproject_fence.py" in recipe, (
        f"Makefile `fence:` recipe MUST still run the Phase 0 scan. Found:\n{recipe}"
    )


def test_fence_recipe_invokes_phase3_fence_directory() -> None:
    """AC-3: ``make fence`` covers the new ``tests/fence/`` collection."""
    recipe = _read_fence_recipe()
    assert "tests/fence/" in recipe, (
        f"Makefile `fence:` recipe MUST run `tests/fence/`. Found:\n{recipe}"
    )


def test_fence_recipe_disables_coverage() -> None:
    """The fence subset doesn't satisfy ``--cov-fail-under=85``; `--no-cov`
    keeps `make fence` invocable as a standalone gate (S1-04 attempt log
    documented this exact local-run footgun)."""
    recipe = _read_fence_recipe()
    assert "--no-cov" in recipe, (
        f"Makefile `fence:` recipe MUST pass `--no-cov` so the narrow subset "
        f"doesn't trip pyproject's --cov-fail-under=85 floor. Found:\n{recipe}"
    )
