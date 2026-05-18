"""S8-03 AC-1/2/4/7 — typed-model workflow assertions for ``ci.yml``.

Uses :class:`tests.unit.ci._workflow_model.WorkflowFile` instead of raw
``yaml.safe_load`` so a malformed YAML fails the parse step (not a
downstream ``KeyError``), and so step access is type-checked.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.unit.ci._workflow_model import WorkflowFile

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CI_YML = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

_PHASE2_REQUIRED_SUBSET = {
    "fence",
    "contract-freeze",
    "unit",
    "integration",
    "portfolio",
    "adv-phase02",
    "mypy",
    "bench",
}
_LEGACY_SUBSET = {"lint", "typecheck", "test", "security"}

_XDIST_RE = re.compile(r"(?<!\w)(-n[\s\d]|--numprocesses\b|--dist\b|pytest-xdist|tox\s+-p\b)")


@pytest.fixture
def wf() -> WorkflowFile:
    return WorkflowFile.from_path(_CI_YML)


def test_workflow_parses(wf: WorkflowFile) -> None:
    """Smoke: malformed YAML or missing required fields would raise here."""
    assert wf.jobs, "ci.yml must declare at least one job"


def test_required_subset_present(wf: WorkflowFile) -> None:
    """AC-1(a) — Phase-2 named lanes are a *subset* of the job set."""
    job_names = set(wf.jobs)
    missing = _PHASE2_REQUIRED_SUBSET - job_names
    assert not missing, (
        f"AC-1: missing Phase-2 named lanes {sorted(missing)} (present: {sorted(job_names)})"
    )


def test_legacy_jobs_preserved(wf: WorkflowFile) -> None:
    """AC-1(b) — no silent deletion of Phase-0/1 jobs."""
    job_names = set(wf.jobs)
    missing = _LEGACY_SUBSET - job_names
    assert not missing, f"AC-1(b): legacy jobs deleted: {sorted(missing)} (this story is additive)"


@pytest.mark.parametrize(
    "lane",
    sorted(_PHASE2_REQUIRED_SUBSET - {"fence"}),  # fence already runs on 3.11 only
)
def test_phase2_lane_runs_on_python_311_and_312(wf: WorkflowFile, lane: str) -> None:
    """AC-1(c) — every NEW Phase-2 lane runs on the matrix 3.11 + 3.12."""
    job = wf.jobs[lane]
    matrix = job.strategy.matrix if job.strategy else None
    assert matrix is not None, f"{lane}: must declare a strategy.matrix"
    pythons = set(matrix.get("python", []))
    assert {"3.11", "3.12"}.issubset(pythons), (
        f"{lane}: python matrix must include 3.11 and 3.12; got {pythons}"
    )


def test_unit_lane_serial_and_no_cov(wf: WorkflowFile) -> None:
    """AC-2 — unit lane runs serial (no xdist) with --no-cov."""
    unit = wf.jobs["unit"]
    run_text = "\n".join(s.run or "" for s in unit.steps)
    assert "pytest tests/unit/" in run_text, "unit lane must invoke pytest tests/unit/"
    assert "--no-cov" in run_text, "unit lane must pass --no-cov"
    assert not _XDIST_RE.search(run_text), (
        f"unit lane uses xdist-style parallel flags: {_XDIST_RE.search(run_text).group()!r}"  # type: ignore[union-attr]
    )


def test_portfolio_serial_budget(wf: WorkflowFile) -> None:
    """AC-4 — portfolio lane has timeout-minutes ≤ 7 and no xdist."""
    portfolio = wf.jobs["portfolio"]
    assert portfolio.timeout_minutes is not None and portfolio.timeout_minutes <= 7, (
        f"portfolio lane must have timeout-minutes ≤ 7; got {portfolio.timeout_minutes}"
    )
    run_text = "\n".join(s.run or "" for s in portfolio.steps)
    assert "pytest tests/integration/portfolio/" in run_text
    assert not _XDIST_RE.search(run_text)


def test_bench_advisory(wf: WorkflowFile) -> None:
    """AC-7 — bench lane's pytest step is continue-on-error: true."""
    bench = wf.jobs["bench"]
    advisory_steps = [s for s in bench.steps if s.continue_on_error is True]
    assert advisory_steps, (
        "AC-7: bench lane must have at least one continue-on-error: true step "
        "(variance-prone; never blocks merge)"
    )


def test_bench_lane_runs_new_bench_scripts(wf: WorkflowFile) -> None:
    """AC-7 — bench lane invokes the two new (non-`-m bench`) scripts."""
    bench = wf.jobs["bench"]
    run_text = "\n".join(s.run or "" for s in bench.steps)
    assert "bench_portfolio_walltime.py" in run_text
    assert "bench_index_health_overhead.py" in run_text
    # Hosted-runner bench MUST NOT run per-PR.
    assert "bench_portfolio_walltime_hosted_runner.py" not in run_text, (
        "AC-7: hosted-runner bench is nightly-only; do not invoke per-PR"
    )


def test_bench_lane_grants_pr_write(wf: WorkflowFile) -> None:
    """AC-7 — bench lane has pull-requests: write so `gh pr comment` works."""
    bench = wf.jobs["bench"]
    perms = bench.permissions or {}
    assert perms.get("pull-requests") == "write", (
        f"AC-7: bench lane must grant pull-requests: write; got {perms}"
    )
    # Contents must remain read-only.
    assert perms.get("contents", "read") == "read"


def test_adv_phase02_is_not_continue_on_error(wf: WorkflowFile) -> None:
    """AC-5 — adversarial lane fails the build on any failure."""
    adv = wf.jobs["adv-phase02"]
    for step in adv.steps:
        assert step.continue_on_error is not True, (
            f"AC-5: adv-phase02 step {step.name!r} sets continue-on-error: true; "
            "LOAD-BEARING gate must fail red"
        )


def test_all_new_phase2_lanes_depend_on_fence(wf: WorkflowFile) -> None:
    """A closure-fence violation should short-circuit the workflow."""
    for lane in _PHASE2_REQUIRED_SUBSET - {"fence"}:
        needs = wf.jobs[lane].needs
        needs_list = [needs] if isinstance(needs, str) else (needs or [])
        assert "fence" in needs_list, (
            f"{lane}: must declare `needs: [fence]` so a fence violation "
            "short-circuits the workflow"
        )


def test_workflow_top_level_permissions_remain_read_only(wf: WorkflowFile) -> None:
    """Phase-0 contract preserved (test_ci_workflow.py asserts this too)."""
    assert wf.permissions == {"contents": "read"}
