"""S8-03 AC-6 — global ``warn_unreachable = true`` is the exhaustiveness gate.

The mypy lane's enforcement of S8-01's exhaustiveness-ritual is config-driven:
``pyproject.toml § [tool.mypy] warn_unreachable = true`` fires per-module
via mypy's whole-program analysis. The S8-01 attempt log confirmed the
project-wide setting is sufficient — no per-module override block needed.

These tests guard the config against:

* a contributor disabling the global setting,
* an override block carving it off for a production module,
* the CI lane re-introducing the obsolete ``--warn-unreachable`` flag
  (single source of truth is the config).
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

from tests.unit.ci._workflow_model import WorkflowFile

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture
def pyproject() -> dict[str, Any]:
    return tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))


def test_global_warn_unreachable_is_true(pyproject: dict[str, Any]) -> None:
    """AC-6(a) — ``[tool.mypy].warn_unreachable`` MUST be true repo-wide."""
    mypy_cfg = pyproject["tool"]["mypy"]
    assert mypy_cfg.get("warn_unreachable") is True, (
        "AC-6: [tool.mypy].warn_unreachable must remain True; "
        "S8-01's exhaustiveness rituals depend on this global setting"
    )


def test_no_override_disables_warn_unreachable(pyproject: dict[str, Any]) -> None:
    """AC-6(b) — no override block flips it off for any production module."""
    overrides = pyproject["tool"]["mypy"].get("overrides", [])
    for entry in overrides:
        if entry.get("warn_unreachable") is False:
            modules = entry.get("module") or entry.get("modules") or []
            production = [
                m
                for m in (modules if isinstance(modules, list) else [modules])
                if isinstance(m, str) and m.startswith("codegenie")
            ]
            assert not production, (
                f"AC-6: override {entry!r} disables warn_unreachable for production "
                f"module(s) {production}; S8-01 exhaustiveness coverage breaks"
            )


def test_mypy_lane_does_not_pass_warn_unreachable_on_cli() -> None:
    """AC-6(a) — single source of truth is the config, not the CLI flag."""
    wf = WorkflowFile.from_path(_CI_YML)
    mypy = wf.jobs.get("mypy")
    assert mypy is not None, "AC-6: mypy lane must exist"
    for step in mypy.steps:
        run = step.run or ""
        assert "--warn-unreachable" not in run, (
            "AC-6: mypy lane must NOT pass --warn-unreachable on the CLI; "
            "the [tool.mypy] config is the single source of truth"
        )
