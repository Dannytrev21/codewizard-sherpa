"""S8-03 AC-13 — *no* pytest-xdist anywhere.

ADR-0009 vetoes ``pytest-xdist`` (and friends ``-n``/``--numprocesses``/
``--dist``/``tox -p``) across both workflow YAML and ``pyproject.toml``'s
``addopts``. The test parses every workflow via the typed model so a
mistyped ``-n4`` (no space) cannot smuggle in unnoticed, and metamorphic-
mutates a copy to prove the assertion has bite.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from tests.unit.ci._workflow_model import WorkflowFile

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

# Match xdist-flavored parallelism flags. Whitespace OR digit follows ``-n``;
# ``tox -p`` matches; ``pytest-xdist`` package name; ``--numprocesses``;
# ``--dist``. The negative-lookahead suffix prevents matching when the
# pattern lands inside a longer identifier.
_XDIST_RE = re.compile(r"(?<!\w)(-n[\s\d]|--numprocesses\b|--dist\b|pytest-xdist|tox\s+-p\b)")


def _workflow_files() -> list[Path]:
    return sorted(_WORKFLOWS_DIR.glob("*.yml"))


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_no_xdist_in_workflow(path: Path) -> None:
    wf = WorkflowFile.from_path(path)
    for job_name, step_label, run in wf.step_run_strings():
        match = _XDIST_RE.search(run)
        assert match is None, (
            f"AC-13: xdist-style flag {match.group()!r} in {path.name} "  # type: ignore[union-attr]
            f"job={job_name!r} step={step_label!r}"
        )


def test_no_xdist_in_pyproject_addopts() -> None:
    cfg = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    pytest_cfg = cfg.get("tool", {}).get("pytest", {}).get("ini_options", {})
    addopts = pytest_cfg.get("addopts", "")
    if isinstance(addopts, list):
        addopts = " ".join(addopts)
    match = _XDIST_RE.search(addopts)
    assert match is None, (
        f"AC-13: pyproject.toml [tool.pytest.ini_options].addopts contains "
        f"xdist-style flag {match.group()!r}"  # type: ignore[union-attr]
    )


def test_metamorphic_injecting_xdist_fires_assertion() -> None:
    """AC-13 — mutate a parsed workflow copy to confirm the regex has bite.

    Loads a real workflow, injects ``-n 4`` into a step's run string, re-runs
    the regex. Expect a match — proves the scan would catch a real edit.
    """
    wf = WorkflowFile.from_path(_REPO_ROOT / ".github" / "workflows" / "ci.yml")
    # Pick the first job with a run step.
    sample_run = None
    for _, _, run in wf.step_run_strings():
        sample_run = run
        break
    assert sample_run is not None, "metamorphic precondition: ci.yml has at least one run step"
    mutated = sample_run + "\npytest -n 4 tests/\n"
    assert _XDIST_RE.search(mutated) is not None, (
        "metamorphic: injected `-n 4` MUST match the regex; "
        "regex has no bite and would silently let xdist slip in"
    )
