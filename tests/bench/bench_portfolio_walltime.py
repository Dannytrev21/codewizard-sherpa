"""Dev-laptop portfolio walltime bench (S8-03 AC-8). Advisory; comment-only.

Measures cold + warm p50 walltime for each of the five canonical portfolio
fixtures (``minimal-ts``, ``native-modules``, ``monorepo-pnpm``,
``distroless-target``, ``stale-scip``) and compares against
``tests/bench/baselines/portfolio_walltime.json``. A ≥ 50 % regression on
any fixture posts a PR comment via ``gh pr comment``. No fixture ever fails
the build from this script — that contract is held by
``bench_portfolio_walltime_hosted_runner.py`` only.

Invocation: ``python tests/bench/bench_portfolio_walltime.py``. NOT marked
``-m bench`` so the existing S5-01 ``bench-collection-guard`` count stays
at 3 (S8-03 AC-7b).
"""

from __future__ import annotations

import json
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Final

# Running this file as a script puts the script's own directory on
# ``sys.path[0]``, not the repo root — prepend the repo root so the
# ``tests`` namespace package resolves for the kernel import below.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.bench._bench_kernel import (  # noqa: E402
    Threshold,
    compare_to_baseline,
    exit_with_verdict,
    load_baseline,
    post_comment_if,
)

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_FIXTURES_ROOT: Final[Path] = _REPO_ROOT / "tests" / "fixtures" / "portfolio"
_BASELINE: Final[Path] = _REPO_ROOT / "tests" / "bench" / "baselines" / "portfolio_walltime.json"
_RUNS_PER_MODE: Final[int] = 5  # 5-run median per arch §"Performance regression tests"
_RESULTS_OUT: Final[Path] = _REPO_ROOT / "bench-results.json"

_THRESHOLDS: Final[Threshold] = Threshold(comment_pct=50.0)  # advisory; no fail


def _gather_once(workdir: Path, cache_dir: Path, *, fresh_cache: bool) -> float:
    """Run ``codegenie gather`` once on ``workdir``; return walltime seconds.

    ``fresh_cache=True`` deletes ``cache_dir`` first so the measurement
    captures cold-start walltime. ``fresh_cache=False`` leaves the cache in
    place for the warm measurement.
    """
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
        check=False,  # advisory bench — failures captured by other lanes
        capture_output=True,
        timeout=180,
    )
    return time.perf_counter() - start


def _measure_fixture(name: str, fixture_root: Path) -> tuple[float, float]:
    """Return ``(cold_p50_s, warm_p50_s)`` for the given fixture."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        workdir = tmp_path / name
        shutil.copytree(fixture_root, workdir)
        cache_dir = tmp_path / ".cache"

        cold_runs: list[float] = []
        warm_runs: list[float] = []
        for _ in range(_RUNS_PER_MODE):
            cold_runs.append(_gather_once(workdir, cache_dir, fresh_cache=True))
            warm_runs.append(_gather_once(workdir, cache_dir, fresh_cache=False))
        return statistics.median(cold_runs), statistics.median(warm_runs)


def run(fixture_filter: tuple[str, ...] = ()) -> dict[str, float]:
    """Run the bench across (optionally filtered) fixtures and return measurements.

    Returns a flat ``{<fixture>/cold_p50_s: secs, <fixture>/warm_p50_s: secs, ...}``
    map suitable for ``compare_to_baseline``.
    """
    fixtures = sorted(p for p in _FIXTURES_ROOT.iterdir() if p.is_dir())
    if fixture_filter:
        wanted = set(fixture_filter)
        fixtures = [f for f in fixtures if f.name in wanted]

    out: dict[str, float] = {}
    for fixture in fixtures:
        cold_p50, warm_p50 = _measure_fixture(fixture.name, fixture)
        out[f"{fixture.name}/cold_p50_s"] = cold_p50
        out[f"{fixture.name}/warm_p50_s"] = warm_p50
    return out


def main() -> int:
    measurements = run()
    baseline = load_baseline(_BASELINE)
    verdict = compare_to_baseline(measurements, baseline, _THRESHOLDS)
    _RESULTS_OUT.write_text(
        json.dumps(
            {
                "bench": "portfolio_walltime",
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
