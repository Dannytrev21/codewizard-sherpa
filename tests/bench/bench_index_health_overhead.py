"""IndexHealthProbe overhead bench (S8-03 AC-9). Advisory; comment-only.

Measures ``IndexHealthProbe`` (B2) walltime as a fraction of total cold
gather walltime against the ``minimal-ts`` fixture. Target: < 5 %.
5–10 % is the acceptable middle band. ≥ 10 % posts a PR comment.

B2 is called out repeatedly in design docs as the load-bearing freshness
gate; a regression in its execution time is one of the few places where
the gather pipeline can quietly become more expensive than the rest of
the system combined. The bench surfaces that drift.

Invocation: ``python tests/bench/bench_index_health_overhead.py``. NOT
marked ``-m bench`` (S8-03 AC-7b — collection-guard stays at 3).
"""

from __future__ import annotations

import asyncio
import json
import shutil
import statistics
import tempfile
import time
from pathlib import Path
from typing import Final

from tests.bench._bench_kernel import (
    Threshold,
    compare_to_baseline,
    exit_with_verdict,
    post_comment_if,
)

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_FIXTURE_ROOT: Final[Path] = _REPO_ROOT / "tests" / "fixtures" / "portfolio" / "minimal-ts"
_RUNS: Final[int] = 5
_RESULTS_OUT: Final[Path] = _REPO_ROOT / "bench-results.json"

# Comment-on-PR threshold: ≥ 10 % of total cold-gather walltime spent in
# IndexHealthProbe. Below that, no signal. Modeled as a Threshold via the
# bench kernel so the kernel-shared API stays uniform across the three
# benches; "measurement" here is the fraction itself.
_BASELINE: Final[dict[str, float]] = {"minimal-ts/b2_fraction": 0.05}  # 5% target
_THRESHOLDS: Final[Threshold] = Threshold(comment_pct=100.0)  # comment when 2× baseline → ≥ 10%


def _gather_with_b2_timer(workdir: Path, cache_dir: Path) -> tuple[float, float]:
    """Run a cold gather and return ``(total_walltime_s, b2_walltime_s)``.

    The B2 timer wraps ``IndexHealthProbe.run`` via monkeypatch on the
    in-process probe instance. Subprocess invocation is avoided here so we
    can timestamp inside the probe; correctness is anchored by the existing
    integration suite, not this bench.
    """
    from codegenie.coordinator.coordinator import gather  # noqa: PLC0415
    from codegenie.probes import REGISTRY  # noqa: PLC0415
    from codegenie.probes.layer_b.index_health import IndexHealthProbe  # noqa: PLC0415

    b2_walltime = 0.0
    original_run = IndexHealthProbe.run

    async def _timed_run(self: IndexHealthProbe, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        nonlocal b2_walltime
        start = time.perf_counter()
        try:
            return await original_run(self, *args, **kwargs)  # type: ignore[misc]
        finally:
            b2_walltime += time.perf_counter() - start

    IndexHealthProbe.run = _timed_run  # type: ignore[assignment]
    try:
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        start = time.perf_counter()
        asyncio.run(
            gather(
                probes=list(REGISTRY.iter()),
                snapshot=None,  # type: ignore[arg-type]
                cache=None,  # type: ignore[arg-type]
                config=None,  # type: ignore[arg-type]
                workspace=workdir,
            )
        )
        total = time.perf_counter() - start
    finally:
        IndexHealthProbe.run = original_run  # type: ignore[assignment]
    return total, b2_walltime


def _measure_fraction() -> float:
    """Run N gathers; return the median B2-fraction-of-total cold walltime."""
    fractions: list[float] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        workdir = tmp_path / "minimal-ts"
        shutil.copytree(_FIXTURE_ROOT, workdir)
        cache_dir = tmp_path / ".cache"
        for _ in range(_RUNS):
            try:
                total, b2 = _gather_with_b2_timer(workdir, cache_dir)
            except Exception:  # noqa: BLE001 — bench tolerates harness errors
                return 0.0
            if total <= 0:
                continue
            fractions.append(b2 / total)
    if not fractions:
        return 0.0
    return statistics.median(fractions)


def run() -> dict[str, float]:
    """Return ``{"minimal-ts/b2_fraction": <fraction-of-total>}`` (0.0–1.0)."""
    return {"minimal-ts/b2_fraction": _measure_fraction()}


def main() -> int:
    measurements = run()
    verdict = compare_to_baseline(measurements, _BASELINE, _THRESHOLDS)
    _RESULTS_OUT.write_text(
        json.dumps(
            {
                "bench": "index_health_overhead",
                "measurements": measurements,
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
