"""Hosted-runner portfolio walltime bench (S8-03 AC-10b — Gap 2 closer).

GATING. Unlike the dev-laptop sibling (``bench_portfolio_walltime.py``),
this bench fails the build on ``>= 100 %`` regression OR ``> 360 s`` p95
walltime. Runs nightly via ``.github/workflows/bench-nightly.yml``; sets
``CODEGENIE_FORCE_CPU_COUNT=2`` BEFORE importing any coordinator module so
``effective_cpu_count()`` returns 2 on the first call regardless of the
runner's actual CPU count.

Invocation:

    CODEGENIE_FORCE_CPU_COUNT=2 python tests/bench/bench_portfolio_walltime_hosted_runner.py

NOT marked ``-m bench`` (S8-03 AC-7b — collection-guard stays at 3).
"""

from __future__ import annotations

import os

# Pin the emulated CPU count BEFORE the coordinator import resolves
# ``effective_cpu_count`` — the function reads the env-var on each call but
# we set it here defensively so a developer running this script locally
# gets the hosted-runner shape without having to set the env-var manually.
os.environ.setdefault("CODEGENIE_FORCE_CPU_COUNT", "2")

# ruff: noqa: E402  — imports below intentionally follow the env-var pin.

import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Final

from tests.bench._bench_kernel import (
    Threshold,
    compare_to_baseline,
    exit_with_verdict,
    load_baseline,
    post_comment_if,
)

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_FIXTURES_ROOT: Final[Path] = _REPO_ROOT / "tests" / "fixtures" / "portfolio"
_BASELINE: Final[Path] = (
    _REPO_ROOT / "tests" / "bench" / "baselines" / "portfolio_walltime_hosted_runner.json"
)
_RUNS_PER_MODE: Final[int] = 5
_RESULTS_OUT: Final[Path] = _REPO_ROOT / "bench-results.json"

# Gap 2 closer thresholds (arch §"Gap analysis"):
#   * comment on ≥ 50 % regression
#   * fail build on ≥ 100 % regression OR p95 > 360 s
_THRESHOLDS: Final[Threshold] = Threshold(
    comment_pct=50.0,
    fail_pct=100.0,
    fail_p95_s=360.0,
)


def _gather_once(workdir: Path, cache_dir: Path, *, fresh_cache: bool) -> float:
    if fresh_cache and cache_dir.exists():
        shutil.rmtree(cache_dir)
    start = time.perf_counter()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "codegenie",
            "gather",
            str(workdir),
            "--cache-dir",
            str(cache_dir),
        ],
        check=False,
        capture_output=True,
        timeout=360,
    )
    return time.perf_counter() - start


def _measure_fixture(name: str, fixture_root: Path) -> tuple[list[float], list[float]]:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        workdir = tmp_path / name
        shutil.copytree(fixture_root, workdir)
        cache_dir = tmp_path / ".cache"
        cold: list[float] = []
        warm: list[float] = []
        for _ in range(_RUNS_PER_MODE):
            cold.append(_gather_once(workdir, cache_dir, fresh_cache=True))
            warm.append(_gather_once(workdir, cache_dir, fresh_cache=False))
        return cold, warm


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = int(round(0.95 * (len(sorted_v) - 1)))
    return sorted_v[idx]


def run() -> tuple[dict[str, float], float]:
    """Return ``(measurements, p95_of_all_cold_runs)``."""
    fixtures = sorted(p for p in _FIXTURES_ROOT.iterdir() if p.is_dir())
    measurements: dict[str, float] = {}
    all_cold: list[float] = []
    for fixture in fixtures:
        cold, warm = _measure_fixture(fixture.name, fixture)
        measurements[f"{fixture.name}/cold_p50_s"] = statistics.median(cold)
        measurements[f"{fixture.name}/warm_p50_s"] = statistics.median(warm)
        all_cold.extend(cold)
    return measurements, _p95(all_cold)


def main() -> int:
    measurements, p95 = run()
    baseline = load_baseline(_BASELINE)
    verdict = compare_to_baseline(measurements, baseline, _THRESHOLDS, p95_seconds=p95)
    _RESULTS_OUT.write_text(
        json.dumps(
            {
                "bench": "portfolio_walltime_hosted_runner",
                "measurements": measurements,
                "p95_cold_s": p95,
                "verdict": type(verdict).__name__,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    post_comment_if(verdict)
    return exit_with_verdict(verdict)


if __name__ == "__main__":
    raise SystemExit(main())
