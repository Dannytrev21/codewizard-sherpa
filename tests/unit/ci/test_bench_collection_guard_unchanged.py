"""S8-03 AC-7b — the existing ``bench-collection-guard`` count stays at 3.

The new bench scripts (`bench_portfolio_walltime.py`,
`bench_index_health_overhead.py`, `bench_portfolio_walltime_hosted_runner.py`)
must NOT carry the ``@pytest.mark.bench`` marker — that would push the
S5-01 ``bench-collection-guard`` step from 3 → 6 and break the guard.

The guard's literal threshold lives in ``.github/workflows/ci.yml`` and is
the source of truth.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
_NEW_BENCH_SCRIPTS = (
    _REPO_ROOT / "tests" / "bench" / "bench_portfolio_walltime.py",
    _REPO_ROOT / "tests" / "bench" / "bench_index_health_overhead.py",
    _REPO_ROOT / "tests" / "bench" / "bench_portfolio_walltime_hosted_runner.py",
)


def test_collection_guard_threshold_is_three() -> None:
    """The literal ``expected exactly 3 bench tests`` string anchors the guard."""
    text = _CI_YML.read_text(encoding="utf-8")
    assert "expected exactly 3 bench tests" in text, (
        "AC-7b: ci.yml must keep the literal 'expected exactly 3 bench tests' "
        "(the S5-01 collection guard); changing the threshold needs an ADR amendment"
    )
    # And the guard's `-ne 3` check must still be present.
    assert re.search(r'\[\s*"\$\{collected\}"\s*-ne\s*3\s*\]', text), (
        'AC-7b: ci.yml\'s `[ "${collected}" -ne 3 ]` collection-count check is gone'
    )


@pytest.mark.parametrize("script", _NEW_BENCH_SCRIPTS, ids=lambda p: p.name)
def test_new_bench_scripts_do_not_carry_bench_marker(script: Path) -> None:
    """AC-7b — new bench scripts MUST NOT be decorated ``@pytest.mark.bench``.

    If a contributor adds the marker, ``pytest --collect-only -m bench`` would
    count to 4+ and the guard fires. The collection guard is the contract;
    the marker veto is the prevention.
    """
    text = script.read_text(encoding="utf-8")
    assert "pytest.mark.bench" not in text, (
        f"AC-7b: {script.name} carries @pytest.mark.bench — would break collection-guard"
    )
    assert "@bench" not in text, (
        f"AC-7b: {script.name} carries @bench — would break collection-guard"
    )
