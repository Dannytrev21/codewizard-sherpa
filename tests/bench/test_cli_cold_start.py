"""Advisory cold-start canary (S5-01).

Runs ``sys.executable -m codegenie --help`` five times, computes the median
wall-clock, and writes the result to ``bench-results.json["cold_start"]``.
Advisory only — never asserts a threshold. The non-gating posture is the
explicit L3 #12 decision (``phase-arch-design.md §Edge cases``); the
structural defense against heavy-import drift lives in ``import-linter``
(S1-05), not here.

Invokes via ``sys.executable -m codegenie`` (NOT a bare ``codegenie`` on
``$PATH``) so a stale globally-installed wheel cannot bias the number —
the interpreter under test is the one that gets timed.
"""

from __future__ import annotations

import statistics
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.bench._helpers import bench_results_path, merge_bench_result


@pytest.mark.bench
def test_cli_cold_start_median(tmp_path: Path) -> None:
    samples: list[float] = []
    for _ in range(5):
        t0 = time.perf_counter()
        result = subprocess.run(
            [sys.executable, "-m", "codegenie", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        elapsed = time.perf_counter() - t0
        assert result.returncode == 0, f"cold-start invocation failed: {result.stderr!r}"
        samples.append(elapsed)

    median = statistics.median(samples)
    out = bench_results_path(tmp_path)
    merge_bench_result(out, "cold_start", {"wall_clock_s_median": median, "samples": samples})

    # The "harness is not silently no-op" assertion.
    re_read = bench_results_path(tmp_path).read_text(encoding="utf-8")
    import json as _json

    parsed = _json.loads(re_read)
    assert "cold_start" in parsed, parsed
    assert parsed["cold_start"]["wall_clock_s_median"] > 0
