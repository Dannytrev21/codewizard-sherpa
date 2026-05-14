"""Advisory cache-hit dispatch-ratio canary (S5-01).

Runs the bullet tracer end-to-end against ``tests/fixtures/js_only`` twice
in the same Python process so the second-run state is observable as a
:class:`codegenie.coordinator.coordinator.GatherResult` — the warm run's
``executions["language_detection"]`` MUST be a :class:`CacheHit` (per
ADR-0009). That single assertion is non-advisory: a silent
"cache-never-hits" regression would otherwise produce a small ratio that
looks healthy.

The wall-clock ratio (warm / cold) is advisory and written to
``bench-results.json["cache_hit_dispatch"]``.
"""

from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path

import pytest

# Side-effect import — triggers @register_probe on the default registry.
import codegenie.probes.language_detection  # noqa: F401
from codegenie.cache.store import CacheStore
from codegenie.config.defaults import Config
from codegenie.coordinator.coordinator import CacheHit, gather
from codegenie.coordinator.snapshot import build_snapshot
from codegenie.output.sanitizer import OutputSanitizer
from codegenie.probes.base import Task
from codegenie.probes.registry import default_registry
from tests.bench._helpers import bench_results_path, merge_bench_result

_FIXTURE_SRC = Path(__file__).parent.parent / "fixtures" / "js_only"


@pytest.mark.bench
def test_cache_hit_dispatch_ratio(tmp_path: Path) -> None:
    fixture = tmp_path / "js_only"
    shutil.copytree(_FIXTURE_SRC, fixture)

    cfg = Config()
    sanitizer = OutputSanitizer()
    cache = CacheStore(
        cache_dir=fixture / ".codegenie" / "cache",
        ttl_hours=cfg.cache_ttl_hours,
    )
    probe_classes = default_registry.for_task("__bullet_tracer__", frozenset({"unknown"}))
    probes = [cls() for cls in probe_classes]
    assert probes, "no probes registered for the bullet tracer task"

    snap = build_snapshot(fixture, cfg)
    task = Task(type="__bullet_tracer__", options={})

    # Cold run (writes the cache).
    t0 = time.perf_counter()
    asyncio.run(gather(snap, task, probes, cfg, cache, sanitizer))
    cold_s = time.perf_counter() - t0

    # Warm run (reads the cache). Re-instantiate probes; build_snapshot is
    # idempotent — same key tuple → CacheHit.
    probes_warm = [cls() for cls in probe_classes]
    t0 = time.perf_counter()
    warm_result = asyncio.run(gather(snap, task, probes_warm, cfg, cache, sanitizer))
    warm_s = time.perf_counter() - t0

    # Non-advisory gate (ADR-0009).
    assert isinstance(warm_result.executions["language_detection"], CacheHit), (
        warm_result.executions
    )

    ratio = (warm_s / cold_s) if cold_s > 0 else 0.0
    out = bench_results_path(tmp_path)
    merge_bench_result(
        out,
        "cache_hit_dispatch",
        {"ratio": ratio, "cold_s": cold_s, "warm_s": warm_s},
    )

    import json as _json

    parsed = _json.loads(bench_results_path(tmp_path).read_text(encoding="utf-8"))
    assert "cache_hit_dispatch" in parsed, parsed
    assert parsed["cache_hit_dispatch"]["warm_s"] > 0
    assert parsed["cache_hit_dispatch"]["cold_s"] > 0
