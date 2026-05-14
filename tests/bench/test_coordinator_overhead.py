"""Advisory dispatch-overhead canary (S5-01).

Measures the wall-clock cost of one in-test ``NoopProbe`` flowing through
the real :func:`codegenie.coordinator.coordinator.gather` end-to-end —
real :class:`OutputSanitizer`, real ``_ProbeOutputValidator`` lookup,
real :class:`CacheStore` against ``tmp_path``. Writes the duration under
``bench-results.json["coordinator_overhead"]``. Advisory only.

The probe is defined locally (NOT registered on the production
``default_registry``) so this canary does not perturb other tests'
registry state.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from codegenie.cache.store import CacheStore
from codegenie.config.defaults import Config
from codegenie.coordinator.coordinator import gather
from codegenie.coordinator.snapshot import build_snapshot
from codegenie.output.sanitizer import OutputSanitizer
from codegenie.probes.base import Probe, ProbeOutput, RepoSnapshot, Task
from tests.bench._helpers import bench_results_path, merge_bench_result


class _NoopProbe(Probe):
    """Minimal probe — no IO, no real work. Used as a dispatch-overhead probe."""

    name = "_noop_bench"
    version = "0.0.0"
    layer = "A"
    tier = "task_specific"
    applies_to_tasks = ["*"]
    applies_to_languages = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = []
    timeout_seconds = 5
    cache_strategy = "none"

    async def run(self, repo: RepoSnapshot, ctx: object) -> ProbeOutput:
        del repo, ctx
        return ProbeOutput(
            schema_slice={},
            raw_artifacts=[],
            confidence="high",
            duration_ms=0,
            warnings=[],
            errors=[],
        )


@pytest.mark.bench
def test_coordinator_dispatch_overhead(tmp_path: Path) -> None:
    cfg = Config()
    snap = build_snapshot(tmp_path, cfg)
    cache = CacheStore(cache_dir=tmp_path / "cache", ttl_hours=cfg.cache_ttl_hours)
    sanitizer = OutputSanitizer()

    t0 = time.perf_counter()
    result = asyncio.run(
        gather(
            snap,
            Task(type="_bench", options={}),
            [_NoopProbe()],
            cfg,
            cache,
            sanitizer,
        )
    )
    elapsed = time.perf_counter() - t0
    assert "_noop_bench" in result.executions, result.executions

    out = bench_results_path(tmp_path)
    merge_bench_result(out, "coordinator_overhead", {"wall_clock_s": elapsed})

    import json as _json

    parsed = _json.loads(bench_results_path(tmp_path).read_text(encoding="utf-8"))
    assert "coordinator_overhead" in parsed, parsed
    assert parsed["coordinator_overhead"]["wall_clock_s"] > 0
