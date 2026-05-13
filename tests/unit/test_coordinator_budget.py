"""S3-05 Section H — resource budget (Gap 3): raw_artifact_mb + advisory RSS."""

from __future__ import annotations

import pytest
import structlog

from codegenie.coordinator.budget import (
    BudgetingContext,
    ProbeBudgetExceeded,
    ResourceBudget,
)
from codegenie.coordinator.coordinator import Ran, gather
from codegenie.probes.base import ProbeOutput
from tests.unit._coordinator_fixtures import FakeProbe, make_snapshot, make_task

# ─────────────── Unit-level BudgetingContext contract ──────────────────────


def test_budgeting_context_blocks_overrun(tmp_path):
    """AC-20 — direct unit test of the callback contract."""
    bc = BudgetingContext(workspace=tmp_path, raw_artifact_mb=1)
    bc.report_bytes(512 * 1024)
    bc.report_bytes(512 * 1024)  # cumulative 1.0 MB — at limit, ok (>= boundary)
    with pytest.raises(ProbeBudgetExceeded):
        bc.report_bytes(1)


def test_budgeting_context_workspace_stays_path(tmp_path):
    """AC-20 — ProbeContext.workspace MUST remain a plain pathlib.Path (ADR-0007 freeze)."""
    bc = BudgetingContext(workspace=tmp_path, raw_artifact_mb=1)
    assert isinstance(bc.workspace, type(tmp_path))


def test_resource_budget_defaults():
    """AC-20 — ResourceBudget default values pinned by the story."""
    rb = ResourceBudget()
    assert rb.rss_mb == 200
    assert rb.raw_artifact_mb == 10
    assert rb.wall_clock_s == 30


# ─────────────── Coordinator-level enforcement ─────────────────────────────


@pytest.mark.parametrize(
    "mb_written,should_error",
    [(0.5, False), (1.0, False), (1.5, True)],
)
async def test_raw_artifact_budget_boundaries(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config, mb_written, should_error
):
    """AC-21 — boundary parametrization kills always-error and >/>= mutants."""

    async def write_n(_snap, ctx):
        ctx.report_bytes(int(mb_written * 1024 * 1024))
        return ProbeOutput({"ok": True}, [], "high", 1, [], [])

    probe = FakeProbe(name="bg", _run=write_n)
    probe.declared_resource_budget = ResourceBudget(rss_mb=200, raw_artifact_mb=1, wall_clock_s=30)
    snap, task = make_snapshot(tmp_path), make_task()

    result = await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    has_budget_err = any("raw_artifact_mb" in e for e in result.outputs["bg"].errors)
    assert has_budget_err == should_error
    if should_error:
        assert result.outputs["bg"].confidence == "low"


async def test_rss_warning_is_advisory_not_fatal(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config, monkeypatch
):
    """AC-22 — probe.rss.warn emits, gather considers probe successful."""
    monkeypatch.setattr(
        "codegenie.coordinator.coordinator._sample_rss_mb",
        lambda: 999,
    )

    probe = FakeProbe(name="rssy")
    snap, task = make_snapshot(tmp_path), make_task()

    with structlog.testing.capture_logs() as captured:
        result = await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    warns = [e for e in captured if e["event"] == "probe.rss.warn"]
    assert warns and warns[0]["probe"] == "rssy"
    assert warns[0]["peak_rss_mb"] >= 200
    assert isinstance(result.executions["rssy"], Ran)
    assert result.outputs["rssy"].errors == []
    assert result.outputs["rssy"].confidence == "high"
