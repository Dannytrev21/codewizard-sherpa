"""Phase-4 S2-05 AC-11 / AC-12 — ``BudgetToken`` import-scope contract.

ADR-0010 commits the project to the Capability pattern for LLM-budget
enforcement: ``LeafLlm.invoke`` requires a ``BudgetToken`` keyword
argument, and the anti-pattern "Capability passed through ten frames" is
load-bearing-avoided by keeping the token's flow to exactly two frames
(``FallbackTier → LeafLlm.invoke``).

The structural guard is the ``[[tool.importlinter.contracts]]`` block
named ``"ADR-0010: BudgetToken is two-frame scoped"`` in ``pyproject.toml``
— this test:

- **AC-12 baseline** asserts the contract evaluates green at story-GREEN
  time (no regressions).
- **AC-12 positive control** plants
  ``tests/fixtures/violators/forged_budget_import.py`` under
  ``src/codegenie/`` as a non-test module, re-runs ``lint-imports``, and
  asserts the contract fires AND names ``budget_token`` in its diagnostic.
  Mirrors the planted-leak mechanic from ``tests/fence/
  test_lint_imports_catches_planted_leak.py``.

Subprocess invocation uses ``python -m importlinter`` via the venv's
``lint-imports`` console script, so the test works regardless of PATH
activation. Fence tests fail loud (Rule 12) — no ``skip``/``xfail``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest

_FALLBACK_DIR: Final[Path] = Path("src/codegenie/fallback")
_PLANTED_MODULE_NAME: Final[str] = "_test_planted_budget_leak"
_PLANTED_PATH: Final[Path] = _FALLBACK_DIR / "fence" / f"{_PLANTED_MODULE_NAME}.py"
_VIOLATOR_FIXTURE: Final[Path] = Path("tests/fixtures/violators/forged_budget_import.py")


def _resolve_lint_imports_binary() -> str:
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


@pytest.fixture(autouse=True)
def _refuse_to_run_if_importlinter_package_missing() -> None:
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


def test_lint_imports_passes_at_baseline() -> None:
    """Baseline: at S2-05 GREEN time the BudgetToken scope contract is green."""
    result = _run_importlinter()
    assert result.returncode == 0, (
        f"`import-linter` failed at baseline (rc={result.returncode}). "
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_violator_fixture_exists() -> None:
    """AC-12 positive-control fixture is on disk.

    The fixture is a *deliberate* import-linter violator that proves the
    contract fires when the planted version of it is moved under
    ``src/codegenie/``. Living under ``tests/fixtures/violators/`` is the
    safe location — ``tests/`` is outside the codegenie package, so the
    file alone does not trip the production lint-imports run.
    """
    assert _VIOLATOR_FIXTURE.is_file(), f"missing violator fixture: {_VIOLATOR_FIXTURE}"
    content = _VIOLATOR_FIXTURE.read_text(encoding="utf-8")
    assert "from codegenie.fallback.budget_token import BudgetToken" in content


def test_lint_imports_catches_planted_budget_token_leak() -> None:
    """AC-12 — a non-test module under ``src/codegenie/`` importing
    ``BudgetToken`` outside the allowed scope MUST fail ``import-linter``
    AND the failure message MUST name the forbidden module.

    The plant is a sibling submodule under ``codegenie.fallback.fence`` —
    a location currently in the contract's ``source_modules`` list and
    *not* in ``ignore_imports``. ``finally`` removes the planted file
    even on assertion failure.
    """
    assert _FALLBACK_DIR.is_dir(), f"Fallback dir missing: {_FALLBACK_DIR}"
    assert not _PLANTED_PATH.exists(), (
        f"Stale planted leak file at {_PLANTED_PATH}; remove before re-running."
    )
    try:
        _PLANTED_PATH.write_text(
            '"""Planted-leak fixture (S2-05 AC-12). DELETE."""\n\n'
            "from codegenie.fallback.budget_token import BudgetToken  # noqa: F401\n",
            encoding="utf-8",
        )
        result = _run_importlinter()
        assert result.returncode != 0, (
            "`import-linter` did NOT fire on planted BudgetToken import. "
            "The Phase-4 capability-scope contract is silently degraded.\n"
            f"stdout:\n{result.stdout}"
        )
        combined = (result.stdout + "\n" + result.stderr).lower()
        assert "budget_token" in combined, (
            "Failure message MUST name `budget_token` so an operator can act.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    finally:
        if _PLANTED_PATH.exists():
            _PLANTED_PATH.unlink()


def test_contract_source_modules_match_codegenie_tree_minus_budget_token() -> None:
    """Shape test — the enumerated ``source_modules`` list is the codegenie
    tree minus ``fallback.budget_token``. Adds to the codegenie tree must
    surface in this test so the scope contract does not silently develop a
    blind spot (Rule 12 — fail loud)."""
    try:
        import tomllib
    except ModuleNotFoundError:  # py 3.10 fallback (project requires 3.11+)
        import tomli as tomllib  # type: ignore[no-redef,import-not-found]
    with open("pyproject.toml", "rb") as fh:
        data = tomllib.load(fh)
    contracts = data["tool"]["importlinter"]["contracts"]
    matching = [
        c for c in contracts if c.get("name") == "ADR-0010: BudgetToken is two-frame scoped"
    ]
    assert len(matching) == 1, "expected exactly one BudgetToken-scope contract"
    sources = set(matching[0]["source_modules"])

    src_codegenie = Path("src/codegenie")
    top_level = {
        p.name for p in src_codegenie.iterdir() if p.is_dir() and not p.name.startswith("__")
    }
    # codegenie.fallback is split into its non-budget-token siblings; every
    # other top-level subpackage is sourced as a whole.
    expected_outside_fallback = {f"codegenie.{name}" for name in top_level - {"fallback"}}
    fallback_dir = src_codegenie / "fallback"
    fallback_siblings = {
        f"codegenie.fallback.{p.stem if p.is_file() else p.name}"
        for p in fallback_dir.iterdir()
        if (
            (p.is_file() and p.suffix == ".py" and not p.name.startswith("__"))
            or (p.is_dir() and not p.name.startswith("__"))
        )
        and p.name not in {"budget_token.py", "__pycache__"}
    }
    expected_sources = expected_outside_fallback | fallback_siblings

    missing = expected_sources - sources
    extra = sources - expected_sources
    assert not missing, (
        f"contract source_modules missing entries (probably a new codegenie "
        f"subpackage that should be scoped): {sorted(missing)}"
    )
    assert not extra, (
        f"contract source_modules has entries no longer in the codegenie tree: {sorted(extra)}"
    )
