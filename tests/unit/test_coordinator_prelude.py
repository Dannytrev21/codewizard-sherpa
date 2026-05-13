"""S3-05 Section F — prelude pass (Gap 4) + snapshot isolation."""

from __future__ import annotations

import pytest
import structlog

from codegenie.coordinator.coordinator import gather
from codegenie.probes.base import ProbeOutput
from tests.unit._coordinator_fixtures import FakeProbe, make_snapshot, make_task


@pytest.mark.parametrize(
    "counts",
    [
        {"javascript": 5, "typescript": 2},
        {"python": 3},
        {},
    ],
)
async def test_prelude_pass_enriches_snapshot_for_downstream_probes(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config, counts
):
    """AC-16 — parametrized: prelude output drives enriched_snapshot.detected_languages."""

    async def base_run(_s, _c):
        return ProbeOutput({"language_stack": {"counts": counts}}, [], "high", 1, [], [])

    base = FakeProbe(name="lang", tier="base", _run=base_run)
    downstream = FakeProbe(name="ds", tier="task_specific")
    snap, task = make_snapshot(tmp_path), make_task()

    await gather(snap, task, [base, downstream], fresh_config, fresh_cache, fresh_sanitizer)

    assert downstream._seen_snapshots, "downstream never dispatched"
    assert downstream._seen_snapshots[0].detected_languages == counts


async def test_no_base_tier_means_empty_enriched_languages(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config
):
    """AC-16 — no base-tier probe → downstream sees the original empty dict."""
    downstream = FakeProbe(name="ds", tier="task_specific")
    snap, task = make_snapshot(tmp_path), make_task()

    await gather(snap, task, [downstream], fresh_config, fresh_cache, fresh_sanitizer)

    assert downstream._seen_snapshots[0].detected_languages == {}


@pytest.mark.parametrize(
    "scenario",
    ["prelude_failed", "missing_language_stack_key", "empty_counts"],
)
async def test_prelude_degraded_warns_and_continues_with_empty_languages(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config, scenario
):
    """AC-17 — fail-loud: when prelude can't supply counts, warn + dispatch with {}."""

    async def base_run(_s, _c):
        if scenario == "prelude_failed":
            raise PermissionError("/forbidden")
        if scenario == "missing_language_stack_key":
            return ProbeOutput({}, [], "low", 1, [], [])
        if scenario == "empty_counts":
            return ProbeOutput({"language_stack": {"counts": {}}}, [], "high", 1, [], [])
        raise AssertionError("unreachable")

    base = FakeProbe(name="lang", tier="base", _run=base_run)
    downstream = FakeProbe(name="ds", tier="task_specific")
    snap, task = make_snapshot(tmp_path), make_task()

    with structlog.testing.capture_logs() as captured:
        await gather(snap, task, [base, downstream], fresh_config, fresh_cache, fresh_sanitizer)

    assert downstream._seen_snapshots[0].detected_languages == {}
    if scenario != "empty_counts":
        assert any(e["event"] == "prelude.degraded" for e in captured), captured


async def test_probe_mutation_of_snapshot_does_not_leak(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config
):
    """AC-18 — Probe-A mutating its snapshot.detected_languages cannot affect Probe-B."""

    async def malicious(_snap, _ctx):
        _snap.detected_languages["evil"] = 1
        return ProbeOutput({}, [], "high", 1, [], [])

    a = FakeProbe(name="a", _run=malicious)
    b = FakeProbe(name="b")
    snap, task = (
        make_snapshot(tmp_path, detected_languages={"javascript": 1}),
        make_task(),
    )

    await gather(snap, task, [a, b], fresh_config, fresh_cache, fresh_sanitizer)

    assert "evil" not in b._seen_snapshots[0].detected_languages
