"""S3-05 Section H — resource budget (Gap 3): raw_artifact_mb + advisory RSS.

Also pins the S1-07 :class:`BudgetingContext` extension (AC-15) — two new
``None``-defaulted fields (``parsed_manifest``, ``input_snapshot``)
mirroring the S1-06 :class:`codegenie.probes.base.ProbeContext` additions.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

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
    """AC-20 — ResourceBudget default values pinned by the story.

    S1-09 AC-1 — ``raw_artifact_truncate_mb`` default is 5 (soft on-disk
    truncation threshold; sibling to the existing hard ceiling
    ``raw_artifact_mb=10``).
    """
    rb = ResourceBudget()
    assert rb.rss_mb == 200
    assert rb.raw_artifact_mb == 10
    assert rb.wall_clock_s == 30
    assert rb.raw_artifact_truncate_mb == 5


def test_resource_budget_field_set_pinned() -> None:
    """S1-09 AC-5 — dataclass field tuple is exactly these four, in this order.

    A fifth future field demands another ADR + a story; this test is the
    trip-wire.
    """
    fields = tuple(f.name for f in dataclasses.fields(ResourceBudget))
    assert fields == (
        "rss_mb",
        "raw_artifact_mb",
        "wall_clock_s",
        "raw_artifact_truncate_mb",
    )


def test_resource_budget_invariant_truncate_le_hard_ceiling() -> None:
    """S1-09 AC-2 — __post_init__ rejects truncate_mb > raw_artifact_mb.

    Kills mutant: __post_init__ omitted (silent acceptance of unreachable
    soft policy because the hard ceiling fires first).
    """
    with pytest.raises(ValueError, match="raw_artifact_truncate_mb"):
        ResourceBudget(raw_artifact_mb=10, raw_artifact_truncate_mb=11)
    # Equality at the limit is allowed.
    rb = ResourceBudget(raw_artifact_mb=10, raw_artifact_truncate_mb=10)
    assert rb.raw_artifact_truncate_mb == 10


# ─────────────── S1-07 BudgetingContext extension (AC-15) ──────────────────


def test_budgeting_context_has_parsed_manifest_and_input_snapshot_fields() -> None:
    """AC-15 — five-field shape pinned in order, both new fields default None.

    The BudgetingContext field tuple is the *runtime ctx contract* every
    probe accessing ``ctx.parsed_manifest`` / ``ctx.input_snapshot`` reads
    against; reordering or renaming would break S2-04 / S1-08 downstream.
    """
    names = tuple(f.name for f in dataclasses.fields(BudgetingContext))
    assert names == (
        "workspace",
        "raw_artifact_mb",
        "bytes_written",
        "parsed_manifest",
        "input_snapshot",
    )
    bc = BudgetingContext(workspace=Path("/tmp"), raw_artifact_mb=10)
    assert bc.parsed_manifest is None
    assert bc.input_snapshot is None


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
    # ``raw_artifact_truncate_mb`` must be <= ``raw_artifact_mb`` (S1-09
    # AC-2 invariant). When this test shrinks the hard ceiling to 1 MB it
    # must also shrink the soft truncation companion to stay legal.
    probe.declared_resource_budget = ResourceBudget(
        rss_mb=200, raw_artifact_mb=1, wall_clock_s=30, raw_artifact_truncate_mb=1
    )
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
