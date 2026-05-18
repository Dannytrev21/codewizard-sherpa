"""S8-03 AC-10c — ``bench-nightly.yml`` typed-model assertions.

Nightly hosted-runner bench (Gap 2 closer). Pinned runner image,
``CODEGENIE_FORCE_CPU_COUNT=2`` at the job level, ``pull-requests: write``
permission, ``workflow_dispatch``-able for ad-hoc reruns, cron string
exactly ``"0 4 * * *"`` (UTC).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.unit.ci._workflow_model import WorkflowFile

_REPO_ROOT = Path(__file__).resolve().parents[3]
_NIGHTLY_YML = _REPO_ROOT / ".github" / "workflows" / "bench-nightly.yml"


@pytest.fixture
def wf() -> WorkflowFile:
    return WorkflowFile.from_path(_NIGHTLY_YML)


def test_workflow_file_exists() -> None:
    assert _NIGHTLY_YML.exists(), f"AC-10c: {_NIGHTLY_YML} must exist"


def test_cron_schedule_is_utc_four_am(wf: WorkflowFile) -> None:
    schedule: Any = wf.triggers.get("schedule")
    assert isinstance(schedule, list) and schedule, (
        "AC-10c: nightly workflow must declare on.schedule with at least one entry"
    )
    crons = [item.get("cron") for item in schedule if isinstance(item, dict)]
    assert "0 4 * * *" in crons, (
        f"AC-10c: cron schedule must be exactly '0 4 * * *' (UTC); got {crons}"
    )


def test_workflow_is_workflow_dispatch_able(wf: WorkflowFile) -> None:
    assert "workflow_dispatch" in wf.triggers, (
        "AC-10c: nightly workflow must accept workflow_dispatch for operator-triggered reruns"
    )


def test_hosted_runner_image_pinned_not_latest(wf: WorkflowFile) -> None:
    """A floating ``ubuntu-latest`` could cause ≥ 100% drift on its own."""
    jobs = wf.jobs
    assert jobs, "nightly workflow must declare at least one job"
    for name, job in jobs.items():
        runs_on = job.runs_on
        assert runs_on == "ubuntu-24.04", (
            f"AC-10c: job {name!r} must pin runs-on to 'ubuntu-24.04'; got {runs_on!r}"
        )


def test_force_cpu_count_two_set_at_job_level(wf: WorkflowFile) -> None:
    for name, job in wf.jobs.items():
        env = job.env or {}
        assert env.get("CODEGENIE_FORCE_CPU_COUNT") == "2", (
            f"AC-10c: job {name!r} must set CODEGENIE_FORCE_CPU_COUNT=2 at the job level; "
            f"got env={env}"
        )


def test_pull_requests_write_granted_on_bench_job(wf: WorkflowFile) -> None:
    for name, job in wf.jobs.items():
        perms = job.permissions or {}
        assert perms.get("pull-requests") == "write", (
            f"AC-10c: job {name!r} must grant pull-requests: write for `gh pr comment`; got {perms}"
        )
        # Contents must stay read-only — never widen.
        assert perms.get("contents", "read") == "read"


def test_runs_only_hosted_runner_bench_script(wf: WorkflowFile) -> None:
    """The nightly workflow must invoke ONLY the hosted-runner bench script."""
    run_text = "\n".join(s.run or "" for j in wf.jobs.values() for s in j.steps)
    assert "bench_portfolio_walltime_hosted_runner.py" in run_text
    # Sanity: the per-PR bench scripts MUST NOT run nightly (different baselines).
    assert "bench_portfolio_walltime.py\n" not in run_text or (
        run_text.count("bench_portfolio_walltime.py")
        == run_text.count("bench_portfolio_walltime_hosted_runner.py")
    ), (
        "AC-10c: nightly workflow runs the hosted-runner bench only; "
        "the dev-laptop bench scripts must not be invoked here"
    )
