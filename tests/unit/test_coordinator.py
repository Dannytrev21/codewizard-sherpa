"""S3-05 coordinator — surface, concurrency, isolation, chain, cache-hit, lifecycle, metamorphic.

Sections A/B/C/D/E/G/I/J from the story TDD plan. Section F lives in
:mod:`tests.unit.test_coordinator_prelude` and section H in
:mod:`tests.unit.test_coordinator_budget`.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import asdict
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import structlog

from codegenie.coordinator.coordinator import (
    CacheHit,
    GatherResult,
    Ran,
    Skipped,
    gather,
)
from codegenie.output.sanitizer import SanitizedProbeOutput
from codegenie.probes.base import ProbeOutput
from tests.unit._coordinator_fixtures import (
    FakeProbe,
    make_snapshot,
    make_task,
)

# ───────────────────────── Section A — surface ─────────────────────────────


async def test_single_probe_dispatch_returns_ran(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config
):
    """AC-2, AC-3 — happy path lands a SanitizedProbeOutput inside Ran."""
    probe = FakeProbe(name="p1")
    snap, task = make_snapshot(tmp_path), make_task()

    result = await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    assert isinstance(result, GatherResult)
    assert isinstance(result.executions["p1"], Ran)
    assert isinstance(result.outputs["p1"], SanitizedProbeOutput)
    assert result.outputs["p1"].schema_slice == {"p1": True}


async def test_outputs_dict_omits_skipped_probes(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config
):
    """AC-4, AC-19 — Skipped probes populate executions, NOT outputs."""
    yes, no = FakeProbe(name="y"), FakeProbe(name="n", _applies=False)
    snap, task = make_snapshot(tmp_path), make_task()

    result = await gather(snap, task, [yes, no], fresh_config, fresh_cache, fresh_sanitizer)

    assert set(result.executions.keys()) == {"y", "n"}
    assert isinstance(result.executions["n"], Skipped)
    assert "applies()" in result.executions["n"].reason
    assert set(result.outputs.keys()) == {"y"}


# ───────────────── Section B — bounded concurrency ────────────────────────


async def test_concurrency_peak_equals_semaphore_value(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config
):
    """AC-5, AC-6 — deterministic peak-equality via asyncio.Event."""
    fresh_config.max_concurrent_probes = 2
    release = asyncio.Event()
    state = {"in_flight": 0, "peak": 0}

    async def slow_run(_snap, _ctx):
        state["in_flight"] += 1
        state["peak"] = max(state["peak"], state["in_flight"])
        await release.wait()
        state["in_flight"] -= 1
        return ProbeOutput({"ok": True}, [], "high", 1, [], [])

    probes = [FakeProbe(name=f"p{i}", _run=slow_run) for i in range(4)]
    snap, task = make_snapshot(tmp_path), make_task()

    gather_task = asyncio.create_task(
        gather(snap, task, probes, fresh_config, fresh_cache, fresh_sanitizer)
    )
    await asyncio.sleep(0.05)
    release.set()
    await gather_task

    assert state["peak"] == 2, f"expected peak==2 with Semaphore(2), got {state['peak']}"


async def test_concurrency_peak_with_max_one(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-5, AC-6 — second parametrization pinning peak == 1 with Semaphore(1)."""
    fresh_config.max_concurrent_probes = 1
    release = asyncio.Event()
    state = {"in_flight": 0, "peak": 0}

    async def slow_run(_snap, _ctx):
        state["in_flight"] += 1
        state["peak"] = max(state["peak"], state["in_flight"])
        await release.wait()
        state["in_flight"] -= 1
        return ProbeOutput({"ok": True}, [], "high", 1, [], [])

    probes = [FakeProbe(name=f"p{i}", _run=slow_run) for i in range(3)]
    snap, task = make_snapshot(tmp_path), make_task()

    gather_task = asyncio.create_task(
        gather(snap, task, probes, fresh_config, fresh_cache, fresh_sanitizer)
    )
    await asyncio.sleep(0.05)
    release.set()
    await gather_task

    assert state["peak"] == 1


async def test_cpu_count_none_falls_back_to_one(
    tmp_path, monkeypatch, fresh_cache, fresh_sanitizer, fresh_config
):
    """AC-5 — ``os.cpu_count() or 1`` branch under cgroup-constrained envs."""
    monkeypatch.setattr(os, "cpu_count", lambda: None)
    fresh_config.max_concurrent_probes = 8
    probe = FakeProbe(name="p")
    snap, task = make_snapshot(tmp_path), make_task()

    result = await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    assert isinstance(result.executions["p"], Ran)


# ─────────────── Section C — failure isolation + cancellation ──────────────


@pytest.mark.parametrize("exc_cls", [ValueError, PermissionError, RuntimeError, KeyError, OSError])
async def test_failure_isolation_over_exception_types(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config, exc_cls
):
    """AC-7, AC-8 — every Exception subclass is isolated into ProbeOutput.errors."""

    async def boom(_snap, _ctx):
        raise exc_cls("synthetic")

    raising = FakeProbe(name="bad", _run=boom)
    healthy = FakeProbe(name="ok")
    snap, task = make_snapshot(tmp_path), make_task()

    result = await gather(
        snap, task, [raising, healthy], fresh_config, fresh_cache, fresh_sanitizer
    )

    assert isinstance(result.executions["bad"], Ran)
    assert result.outputs["bad"].confidence == "low"
    assert any(exc_cls.__name__ in e for e in result.outputs["bad"].errors)
    assert isinstance(result.executions["ok"], Ran)
    assert result.outputs["ok"].errors == []


class _BaseExcCarveOut(BaseException):
    """Custom ``BaseException`` for the AC-8 negative test.

    Pytest's runner intercepts ``KeyboardInterrupt`` regardless of in-test
    ``try`` / ``pytest.raises`` context (pytest treats Ctrl-C specially);
    using a project-local ``BaseException`` subclass exercises the SAME
    failure-isolation carve-out the story names (``except Exception`` MUST
    NOT trap a true ``BaseException``) without colliding with pytest's
    abort path. The behavior under test is identical: if the coordinator
    were to catch ``BaseException`` instead of ``Exception``, this would
    land in ``Ran(errors=...)`` rather than propagate.
    """


async def test_base_exception_subclass_propagates(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config
):
    """AC-8 — a ``BaseException`` subclass MUST propagate out of gather()."""

    async def kaboom(_snap, _ctx):
        raise _BaseExcCarveOut()

    probe = FakeProbe(name="boom", _run=kaboom)
    snap, task = make_snapshot(tmp_path), make_task()

    raised = False
    try:
        await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)
    except _BaseExcCarveOut:
        raised = True
    assert raised, "BaseException subclass was swallowed by the coordinator"


async def test_timeout_uses_min_of_timeout_and_wall_clock_budget(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config
):
    """AC-9 — tighter of probe.timeout_seconds vs declared_resource_budget.wall_clock_s wins."""
    import time

    from codegenie.coordinator.budget import ResourceBudget

    async def slow(_snap, _ctx):
        await asyncio.sleep(10)
        return ProbeOutput({}, [], "high", 0, [], [])

    probe = FakeProbe(name="slow", _run=slow, timeout_seconds=300)
    probe.declared_resource_budget = ResourceBudget(rss_mb=200, raw_artifact_mb=10, wall_clock_s=1)
    snap, task = make_snapshot(tmp_path), make_task()

    t0 = time.monotonic()
    result = await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)
    elapsed = time.monotonic() - t0

    assert 0.95 < elapsed < 2.0, f"expected ~1s + grace, got {elapsed:.2f}"
    assert any("timeout" in e for e in result.outputs["slow"].errors)
    assert result.outputs["slow"].confidence == "low"


async def test_timeout_invokes_sigkill_hook(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-10 — on timeout, tracked subprocesses in exec._RUNNING_PROCS are SIGKILL'd."""
    import codegenie.exec as exec_mod

    fake_proc = MagicMock()
    fake_proc.returncode = None

    async def register_then_sleep(_snap, _ctx):
        exec_mod._RUNNING_PROCS[424242] = fake_proc
        await asyncio.sleep(10)
        return ProbeOutput({}, [], "high", 0, [], [])

    probe = FakeProbe(name="tk", _run=register_then_sleep, timeout_seconds=1)
    snap, task = make_snapshot(tmp_path), make_task()

    await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    fake_proc.kill.assert_called()
    exec_mod._RUNNING_PROCS.pop(424242, None)


# ─────────────── Section D — validator → sanitizer chain ───────────────────


async def test_validator_blocks_secret_shaped_field(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config
):
    """AC-11, AC-13 — _ProbeOutputValidator catches secret-shaped keys before scrub."""

    async def emit_secret(_snap, _ctx):
        return ProbeOutput({"api_key": "abc"}, [], "high", 1, [], [])

    probe = FakeProbe(name="leak", _run=emit_secret)
    snap, task = make_snapshot(tmp_path), make_task()

    result = await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    assert isinstance(result.executions["leak"], Ran)
    assert result.outputs["leak"].confidence == "low"
    err = result.outputs["leak"].errors[0]
    assert re.match(r"^SecretLikelyFieldNameError: .+ at \(.+\)$", err), err


async def test_sanitizer_scrubs_absolute_paths_on_happy_path(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config
):
    """AC-12 — sanitizer rewrites <repo>/foo → foo. Kills the omit-sanitizer mutant."""
    snap, task = make_snapshot(tmp_path), make_task()
    abs_path = str(snap.root / "deep" / "thing.json")

    async def emit_path(_snap, _ctx):
        return ProbeOutput({"root_path": abs_path}, [], "high", 1, [], [])

    probe = FakeProbe(name="pathy", _run=emit_path)

    result = await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    out = result.outputs["pathy"]
    assert isinstance(out, SanitizedProbeOutput)
    assert out.schema_slice["root_path"] == "deep/thing.json"
    assert str(snap.root) not in out.schema_slice["root_path"]


def test_no_top_level_pydantic_import_in_coordinator():
    """AC-25 — ``import pydantic`` must not appear at top of coordinator.py."""
    import ast
    import pathlib

    src = pathlib.Path("src/codegenie/coordinator/coordinator.py").read_text()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "pydantic" not in alias.name, f"top-level import of {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            assert node.module is None or "pydantic" not in node.module, node.module


def test_lifecycle_event_names_match_arch():
    """AC-24 — every required lifecycle event string is literally present."""
    import pathlib

    src = pathlib.Path("src/codegenie/coordinator/coordinator.py").read_text()
    for event in (
        "probe.start",
        "probe.success",
        "probe.cache_hit",
        "probe.skip",
        "probe.failure",
        "probe.timeout",
        "probe.rss.warn",
    ):
        assert event in src, f"missing lifecycle event name {event!r}"


# ─────────────── Section E — cache-hit short-circuit (ADR-0009) ────────────


async def test_cache_hit_short_circuits_chain(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-14, AC-15 — on hit, run/validator/sanitizer all skipped."""
    cached = ProbeOutput({"hit": True}, [], "high", 1, [], [])
    probe = FakeProbe(name="warm")
    probe.run = AsyncMock(side_effect=AssertionError("run must not be called"))

    snap, task = make_snapshot(tmp_path), make_task()
    key = fresh_cache.key_for(probe, snap, task)
    fresh_cache.put(key, cached)

    with (
        patch("codegenie.coordinator.validator._ProbeOutputValidator.model_validate") as mv,
        patch.object(fresh_sanitizer, "scrub", wraps=fresh_sanitizer.scrub) as sp,
    ):
        result = await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    assert mv.call_count == 0
    assert sp.call_count == 0
    assert probe.run.await_count == 0
    assert isinstance(result.executions["warm"], CacheHit)
    assert result.executions["warm"].key == key
    assert isinstance(result.outputs["warm"], SanitizedProbeOutput)
    assert result.outputs["warm"].schema_slice == {"hit": True}


# ─────────────── Section G — applies() filter + Skipped ────────────────────


async def test_applies_false_short_circuits_cache_and_run(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config
):
    """AC-19 — applies()-False → Skipped, no cache.get, no run()."""
    probe = FakeProbe(name="n", _applies=False)
    probe.run = AsyncMock(side_effect=AssertionError("run must not be called"))
    fresh_cache.get = MagicMock(side_effect=AssertionError("cache.get must not be called"))

    snap, task = make_snapshot(tmp_path), make_task()

    result = await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    assert isinstance(result.executions["n"], Skipped)
    assert probe.run.await_count == 0
    assert fresh_cache.get.call_count == 0
    assert "n" not in result.outputs


# ─────────────── Section I — lifecycle events + run_id ─────────────────────


async def test_every_lifecycle_event_carries_run_id(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config
):
    """AC-23, AC-24 — run_id is bound once and on every probe.* event."""
    probes = [FakeProbe(name=f"p{i}") for i in range(3)]
    snap, task = make_snapshot(tmp_path), make_task()

    with structlog.testing.capture_logs() as captured:
        await gather(snap, task, probes, fresh_config, fresh_cache, fresh_sanitizer)

    probe_events = [e for e in captured if e["event"].startswith("probe.")]
    assert probe_events, "no probe.* events emitted"
    run_ids = {e.get("run_id") for e in probe_events}
    assert len(run_ids) == 1 and next(iter(run_ids)), f"run_id drift: {run_ids}"


async def test_probe_skip_event_emitted_with_reason(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config
):
    """AC-19, AC-24 — applies()-False → probe.skip event + Skipped execution."""
    probe = FakeProbe(name="n", _applies=False)
    snap, task = make_snapshot(tmp_path), make_task()

    with structlog.testing.capture_logs() as captured:
        await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    skips = [e for e in captured if e["event"] == "probe.skip"]
    assert len(skips) == 1
    assert skips[0]["probe"] == "n"
    assert "applies()" in skips[0]["reason"]


# ─────────────── Section J — metamorphic + invariants ──────────────────────


async def test_gather_is_order_invariant(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-26 — same probe set in different order → same outputs + execution keys."""

    def mk(name: str) -> FakeProbe:
        return FakeProbe(name=name)

    snap, task = make_snapshot(tmp_path), make_task()

    r1 = await gather(
        snap, task, [mk("a"), mk("b"), mk("c")], fresh_config, fresh_cache, fresh_sanitizer
    )
    # Reset cache for a fair from-scratch comparison.
    import shutil

    shutil.rmtree(tmp_path / ".codegenie_cache", ignore_errors=True)
    from codegenie.cache.store import CacheStore

    cache2 = CacheStore(cache_dir=tmp_path / ".codegenie_cache", ttl_hours=24)
    r2 = await gather(
        snap, task, [mk("c"), mk("a"), mk("b")], fresh_config, cache2, fresh_sanitizer
    )

    # ``duration_ms`` is wall-clock noise — exclude it from the
    # order-invariance comparison (the asserted invariant is semantic
    # output equality, not timing parity).
    def _semantic(v: SanitizedProbeOutput) -> dict[str, Any]:
        d = asdict(v)
        d.pop("duration_ms", None)
        return d

    assert {k: _semantic(v) for k, v in r1.outputs.items()} == {
        k: _semantic(v) for k, v in r2.outputs.items()
    }
    assert set(r1.executions.keys()) == set(r2.executions.keys())


async def test_second_gather_is_all_cache_hits(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config
):
    """AC-27 — idempotent re-run lands all CacheHits, outputs field-equal."""
    probes = [FakeProbe(name=f"p{i}") for i in range(2)]
    snap, task = make_snapshot(tmp_path), make_task()

    r1 = await gather(snap, task, probes, fresh_config, fresh_cache, fresh_sanitizer)
    probes2 = [FakeProbe(name=f"p{i}") for i in range(2)]
    r2 = await gather(snap, task, probes2, fresh_config, fresh_cache, fresh_sanitizer)

    assert all(isinstance(e, CacheHit) for e in r2.executions.values())
    assert {k: asdict(v) for k, v in r1.outputs.items()} == {
        k: asdict(v) for k, v in r2.outputs.items()
    }


async def test_empty_probe_list_returns_empty_gather_result(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config
):
    """AC-28 — gather([], ...) returns GatherResult({}, {}) without crashing."""
    snap, task = make_snapshot(tmp_path), make_task()

    with structlog.testing.capture_logs() as captured:
        result = await gather(snap, task, [], fresh_config, fresh_cache, fresh_sanitizer)

    assert result.outputs == {}
    assert result.executions == {}
    assert not any(e["event"].startswith("probe.") for e in captured)


async def test_executions_dict_covers_all_dispatched_probes(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config
):
    """AC-29 — heterogeneous mix: success + failure + timeout + cache-hit."""
    from codegenie.coordinator.budget import ResourceBudget

    async def ok(_s, _c):
        return ProbeOutput({"ok": True}, [], "high", 1, [], [])

    async def bad(_s, _c):
        raise RuntimeError("nope")

    async def slow(_s, _c):
        await asyncio.sleep(10)
        return ProbeOutput({}, [], "high", 0, [], [])

    p_ok = FakeProbe(name="ok", _run=ok)
    p_bad = FakeProbe(name="bad", _run=bad)
    p_to = FakeProbe(name="to", _run=slow, timeout_seconds=1)
    p_to.declared_resource_budget = ResourceBudget(rss_mb=200, raw_artifact_mb=10, wall_clock_s=1)
    p_hit = FakeProbe(name="hit")
    snap, task = make_snapshot(tmp_path), make_task()
    fresh_cache.put(
        fresh_cache.key_for(p_hit, snap, task),
        ProbeOutput({"warm": True}, [], "high", 1, [], []),
    )

    result = await gather(
        snap, task, [p_ok, p_bad, p_to, p_hit], fresh_config, fresh_cache, fresh_sanitizer
    )

    assert set(result.executions.keys()) == {"ok", "bad", "to", "hit"}
    assert set(result.outputs.keys()) == {"ok", "bad", "to", "hit"}
    assert isinstance(result.executions["hit"], CacheHit)
    assert isinstance(result.executions["ok"], Ran)
    assert result.outputs["bad"].confidence == "low"
    assert any("timeout" in e for e in result.outputs["to"].errors)


# ─────────────── Section A — build_snapshot (AC-1) ─────────────────────────


def test_build_snapshot_falls_back_when_not_a_git_repo(tmp_path):
    """AC-1 — git rev-parse failure → git_commit=None, snapshot.root resolved."""
    from codegenie.config.defaults import Config
    from codegenie.coordinator.snapshot import build_snapshot

    snap = build_snapshot(tmp_path, Config())

    assert snap.git_commit is None
    assert snap.root == tmp_path.resolve()
    assert snap.root.is_absolute()
    assert snap.detected_languages == {}


# ─────────── S3-06 amendment — errored Ran is not cached (AC-6) ──────────


async def test_dispatch_does_not_cache_errored_ran(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config
):
    """S3-06 AC-6: errored probe outputs must NOT be persisted to the cache.

    Errored outputs are not replayable — caching them would mean the *next*
    gather quietly returns the failure from disk instead of re-running the
    probe. The coordinator's ``_dispatch_one`` gates ``cache.put`` on
    ``not sanitized.errors``.
    """

    async def boom(_s, _c):
        raise RuntimeError("kaboom")

    probe = FakeProbe(name="bad", _run=boom)
    snap, task = make_snapshot(tmp_path), make_task()

    await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    key = fresh_cache.key_for(probe, snap, task)
    assert fresh_cache.get_index_record(key) is None
    assert fresh_cache.get(key) is None


async def test_ran_carries_cache_key(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """S3-06 AC-5: ``Ran`` carries the cache key the dispatch used.

    The audit writer reads ``Ran.key`` directly — re-deriving via
    ``cache.key_for`` at audit-write time would record what we'd ask for
    *now* rather than what the coordinator actually asked.
    """
    probe = FakeProbe(name="p")
    snap, task = make_snapshot(tmp_path), make_task()

    result = await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    execution = result.executions["p"]
    assert isinstance(execution, Ran)
    expected_key = fresh_cache.key_for(probe, snap, task)
    assert execution.key == expected_key
