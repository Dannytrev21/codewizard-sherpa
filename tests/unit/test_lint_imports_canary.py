"""Deliberate-negative canary for the ``[tool.importlinter]`` config.

Mirrors S1-02's ``test_ruff_check_rejects_print_in_src_per_phase_arch_logging_strategy``
(``tests/unit/test_toolchain_config.py:132-163``). Without this canary, the
config could ship with ``forbidden_modules: ["nonexistent"]`` and every other
AC still passes. Owned by story S1-05 (AC-10).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLI = PROJECT_ROOT / "src" / "codegenie" / "cli.py"


def _lint_imports_path() -> str:
    # The `import-linter` distribution exposes a `lint-imports` console
    # script — `python -m importlinter` is intentionally NOT supported by
    # the package, so we resolve the binary on PATH (matching the Makefile
    # target and the CI invocation).
    resolved = shutil.which("lint-imports")
    assert resolved is not None, (
        "lint-imports console script must be on PATH; "
        "run `pip install -e .[dev]` (S1-05 adds `import-linter` to [dev])."
    )
    return resolved


def _run_lint_imports() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_lint_imports_path(), "--config", "pyproject.toml", "--no-cache"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_lint_imports_exits_zero_on_current_tree() -> None:
    # AC-10(a): the green half of the canary.
    result = _run_lint_imports()
    assert result.returncode == 0, (
        f"AC-10: lint-imports failed on current tree: "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_lint_imports_actually_blocks_a_planted_heavy_import() -> None:
    # AC-10(b): plant `import yaml` in cli.py, run lint-imports, assert
    # non-zero exit, restore. Mirrors S1-02's ruff `print(` canary
    # (test_toolchain_config.py:132-163).
    original = CLI.read_text() if CLI.exists() else None
    CLI.parent.mkdir(parents=True, exist_ok=True)
    CLI.write_text("import yaml  # planted by S1-05 canary — DO NOT COMMIT\n")
    try:
        result = _run_lint_imports()
        assert result.returncode != 0, (
            f"AC-10: lint-imports failed to catch planted `import yaml` in cli.py — "
            f"the [tool.importlinter] config is misconfigured. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    finally:
        if original is not None:
            CLI.write_text(original)
        else:
            CLI.unlink(missing_ok=True)
