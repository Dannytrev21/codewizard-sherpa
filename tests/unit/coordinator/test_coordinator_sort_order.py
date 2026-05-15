"""S1-08 — coordinator honors registry-declared dispatch order under the single
``Semaphore(min(cpu_count(), 8))`` budget, hoists ``runs_last=True`` probes
out of the prelude/Wave-2 partition, and emits a per-wave
``coordinator.dispatch.order`` structlog event.

Pins:
- AC-6b — single semaphore (no per-tier).
- AC-9 — registry-declared order survives the semaphore.
- AC-10 — ``coordinator.dispatch.order`` once per wave.
- AC-13 — cross-wave ``runs_last`` invariant.

Mutation resistance: tests would fail if ``sorted_for_dispatch`` were stubbed
to return its input unchanged OR if the coordinator/seam ignored
``runs_last`` for ``tier="base"`` probes.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import structlog
from structlog.testing import LogCapture

from codegenie.coordinator.coordinator import gather
from codegenie.probes.base import Probe, ProbeOutput, RepoSnapshot, Task
from tests.unit._coordinator_fixtures import make_snapshot, make_task


@pytest.fixture()
def log_output() -> LogCapture:
    """Re-installable structlog capture so each test gets a clean log buffer."""
    cap = LogCapture()
    structlog.configure(processors=[cap])
    yield cap
    structlog.reset_defaults()


@dataclass
class _RecorderProbe(Probe):
    """A synthetic probe that records ``(name, perf_counter_ns)`` on entry to
    ``run`` and returns a trivial slice. The per-probe ``timeline`` shared
    list reveals the actual dispatch order after ``gather()`` returns.

    NOT registered into ``default_registry`` — instantiated inline in tests.
    """

    name: str = "recorder"
    version: str = "0.1.0"
    layer: str = "B"
    tier: str = "task_specific"
    applies_to_tasks: list[str] = field(default_factory=lambda: ["*"])
    applies_to_languages: list[str] = field(default_factory=lambda: ["*"])
    requires: list[str] = field(default_factory=list)
    declared_inputs: list[str] = field(default_factory=list)
    timeout_seconds: int = 5
    cache_strategy: str = "none"

    timeline: list[tuple[str, int]] = field(default_factory=list)
    sleep_s: float = 0.005

    def applies(self, repo: RepoSnapshot, task: Task) -> bool:
        return True

    def cache_key(self, repo: RepoSnapshot, task: Task) -> str:
        return f"sha256:{self.name}"

    async def run(self, repo: RepoSnapshot, ctx: Any) -> ProbeOutput:
        self.timeline.append((self.name, time.perf_counter_ns()))
        await asyncio.sleep(self.sleep_s)
        return ProbeOutput(
            schema_slice={self.name: True},
            raw_artifacts=[],
            confidence="high",
            duration_ms=1,
            warnings=[],
            errors=[],
        )


# ---------------------------------------------------------------------------
# AC-9 + AC-13 — registry order survives the semaphore; runs_last is strictly
# last; tier="base" + runs_last=True is hoisted out of the prelude.
# ---------------------------------------------------------------------------


async def test_dispatch_order_under_single_semaphore_with_runs_last_hoist(
    tmp_path: Path,
    fresh_cache: Any,
    fresh_sanitizer: Any,
    fresh_config: Any,
    log_output: LogCapture,
) -> None:
    timeline: list[tuple[str, int]] = []

    # Build probes in the order the registry's sorted_for_dispatch() would emit:
    # heavy (Wave 2), medium (Wave 2), light (Wave 2), base prelude (Wave 1),
    # then base + runs_last (must land at the tail of Wave 2).
    a_light = _RecorderProbe(name="a_light", tier="task_specific", timeline=timeline)
    b_medium = _RecorderProbe(name="b_medium", tier="task_specific", timeline=timeline)
    c_heavy = _RecorderProbe(name="c_heavy", tier="task_specific", timeline=timeline)
    e_base_prelude = _RecorderProbe(name="e_base_prelude", tier="base", timeline=timeline)
    d_index_health = _RecorderProbe(name="d_index_health", tier="base", timeline=timeline)

    runs_last_names = frozenset({"d_index_health"})

    await gather(
        make_snapshot(tmp_path),
        make_task(),
        [c_heavy, b_medium, a_light, e_base_prelude, d_index_health],
        fresh_config,
        fresh_cache,
        fresh_sanitizer,
        runs_last_names=runs_last_names,
    )

    order = [name for name, _ in timeline]

    # AC-13 — d_index_health (runs_last=True, tier="base") is strictly last
    # despite its declared base tier.
    assert order[-1] == "d_index_health", order

    # The non-runs_last base probe ran in the prelude wave (before any
    # non-base Wave-2 probe).
    assert order.index("e_base_prelude") < order.index("a_light"), order
    assert order.index("e_base_prelude") < order.index("b_medium"), order
    assert order.index("e_base_prelude") < order.index("c_heavy"), order


# ---------------------------------------------------------------------------
# AC-10 — coordinator.dispatch.order emitted once per wave; runs_last only
# appears at the tail of the rest wave.
# ---------------------------------------------------------------------------


async def test_coordinator_dispatch_order_log_emitted_per_wave(
    tmp_path: Path,
    fresh_cache: Any,
    fresh_sanitizer: Any,
    fresh_config: Any,
    log_output: LogCapture,
) -> None:
    timeline: list[tuple[str, int]] = []
    base_a = _RecorderProbe(name="base_a", tier="base", timeline=timeline)
    rest_a = _RecorderProbe(name="rest_a", tier="task_specific", timeline=timeline)
    runs_last_x = _RecorderProbe(name="runs_last_x", tier="base", timeline=timeline)

    await gather(
        make_snapshot(tmp_path),
        make_task(),
        [rest_a, base_a, runs_last_x],
        fresh_config,
        fresh_cache,
        fresh_sanitizer,
        runs_last_names=frozenset({"runs_last_x"}),
    )

    events = [r for r in log_output.entries if r.get("event") == "coordinator.dispatch.order"]
    waves = {e["wave"]: e["probe_order"] for e in events}
    assert set(waves.keys()) == {"prelude", "rest"}, waves

    # runs_last hoisted out of prelude.
    assert "runs_last_x" not in waves["prelude"], waves["prelude"]
    # runs_last lands at the tail of the rest wave.
    assert waves["rest"][-1] == "runs_last_x", waves["rest"]
    # base_a ran in the prelude.
    assert "base_a" in waves["prelude"], waves["prelude"]


# ---------------------------------------------------------------------------
# AC-6b — single Semaphore preserved (no per-tier semaphore)
# ---------------------------------------------------------------------------


async def test_single_semaphore_bounds_total_concurrency(
    tmp_path: Path,
    fresh_cache: Any,
    fresh_sanitizer: Any,
    fresh_config: Any,
    log_output: LogCapture,
) -> None:
    """``config.max_concurrent_probes = 2`` plus a deliberate stall in every
    probe must result in at most two probes running concurrently — across
    BOTH waves. A per-tier semaphore would let prelude + rest each run with
    a full budget.

    Mutation: an implementation that introduced per-tier semaphores would
    raise the observed concurrency past 2.
    """
    fresh_config.max_concurrent_probes = 2

    concurrent = 0
    peak = 0
    lock = asyncio.Lock()

    @dataclass
    class _PeakRecorder(_RecorderProbe):
        async def run(self, repo: RepoSnapshot, ctx: Any) -> ProbeOutput:  # type: ignore[override]
            nonlocal concurrent, peak
            async with lock:
                concurrent += 1
                peak = max(peak, concurrent)
            await asyncio.sleep(0.02)
            async with lock:
                concurrent -= 1
            return ProbeOutput(
                schema_slice={self.name: True},
                raw_artifacts=[],
                confidence="high",
                duration_ms=1,
                warnings=[],
                errors=[],
            )

    probes = [
        _PeakRecorder(name=f"p{i}", tier=("base" if i < 2 else "task_specific")) for i in range(6)
    ]
    await gather(
        make_snapshot(tmp_path),
        make_task(),
        probes,
        fresh_config,
        fresh_cache,
        fresh_sanitizer,
    )
    assert peak <= 2, peak


# ---------------------------------------------------------------------------
# Defensive — no runs_last names means coordinator behaves as Phase 0/1.
# ---------------------------------------------------------------------------


async def test_runs_last_names_default_empty_preserves_phase01_behavior(
    tmp_path: Path,
    fresh_cache: Any,
    fresh_sanitizer: Any,
    fresh_config: Any,
    log_output: LogCapture,
) -> None:
    """When no probe is marked ``runs_last``, the coordinator's partition is
    indistinguishable from Phase 0/1: ``tier == "base"`` runs in the prelude,
    everything else runs in the rest wave, and the per-wave log emits in
    that order."""
    timeline: list[tuple[str, int]] = []
    p_base = _RecorderProbe(name="p_base", tier="base", timeline=timeline)
    p_rest = _RecorderProbe(name="p_rest", tier="task_specific", timeline=timeline)

    await gather(
        make_snapshot(tmp_path),
        make_task(),
        [p_rest, p_base],
        fresh_config,
        fresh_cache,
        fresh_sanitizer,
    )
    order = [name for name, _ in timeline]
    assert order.index("p_base") < order.index("p_rest")

    events = [r for r in log_output.entries if r.get("event") == "coordinator.dispatch.order"]
    waves = {e["wave"]: e["probe_order"] for e in events}
    assert waves["prelude"] == ["p_base"]
    assert waves["rest"] == ["p_rest"]
