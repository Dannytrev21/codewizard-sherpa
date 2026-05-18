"""S8-03 AC-5 — adv-phase02 is LOAD-BEARING.

Three independent assertions:

1. The workflow's ``adv-phase02`` step does NOT set ``continue-on-error: true``
   (would silently swallow Phase-2 exit-criterion regressions).
2. The eight named adversarial-test files exist under ``tests/adv/phase02/``.
3. Each file collects at least one ``def test_…`` function — catches empty
   stubs (a file that exists but holds nothing is worse than a missing file
   because it gives false confidence).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.unit.ci._workflow_model import WorkflowFile

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_ADV_DIR = _REPO_ROOT / "tests" / "adv" / "phase02"

_REQUIRED_ADV_FILES = (
    "test_adversarial_dockerfile.py",
    "test_concurrent_gather_race.py",
    "test_hostile_skills_yaml.py",
    "test_image_digest_drift.py",
    "test_no_inmemory_secret_leak.py",
    "test_phase3_handoff_smoke.py",
    "test_secret_in_source.py",
    "test_stale_scip_fixture.py",
)


def test_adv_phase02_lane_is_not_continue_on_error() -> None:
    wf = WorkflowFile.from_path(_CI_YML)
    adv = wf.jobs["adv-phase02"]
    for step in adv.steps:
        assert step.continue_on_error is not True, (
            f"AC-5: adv-phase02 step {step.name!r} would swallow failures"
        )


@pytest.mark.parametrize("filename", _REQUIRED_ADV_FILES)
def test_each_required_file_exists(filename: str) -> None:
    path = _ADV_DIR / filename
    assert path.exists(), f"AC-5: required adversarial file missing: {path}"


@pytest.mark.parametrize("filename", _REQUIRED_ADV_FILES)
def test_each_required_file_collects_at_least_one_test(filename: str) -> None:
    """A file that exists but defines zero tests is an empty-stub trap.

    ``pytest --collect-only -q tests/adv/phase02/<file>`` returns one line per
    collected test; we count lines containing ``::test_``.
    """
    target = _ADV_DIR / filename
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-cov", str(target)],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        timeout=60,
        check=False,
    )
    collected = [line for line in result.stdout.splitlines() if "::test_" in line]
    assert collected, (
        f"AC-5: {filename} collects zero tests (empty stub).\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_no_extra_unrecognized_test_files_in_adv_dir() -> None:
    """Catch typos / accidental commits — every test_*.py file is on the allowlist."""
    actual = {p.name for p in _ADV_DIR.glob("test_*.py")}
    expected = set(_REQUIRED_ADV_FILES)
    extras = actual - expected
    assert not extras, (
        f"AC-5: unexpected adversarial test files: {sorted(extras)}. "
        "Update _REQUIRED_ADV_FILES (and the story enumeration) when adding new ones."
    )
