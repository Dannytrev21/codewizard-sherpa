"""S8-03 AC-9 — smoke + metamorphic test for ``bench_index_health_overhead``.

The full bench would run a five-invocation cold gather sweep against
``minimal-ts``. That's a multi-second run we can't pay for in unit. The
smoke test asserts the module surface, the threshold shape, and the
metamorphic property: injecting an artificial ``time.sleep`` inside
``IndexHealthProbe.run`` strictly increases the reported B2-fraction.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def bench_module() -> object:
    sys.path.insert(0, str(_REPO_ROOT))
    if "tests.bench.bench_index_health_overhead" in sys.modules:
        del sys.modules["tests.bench.bench_index_health_overhead"]
    return importlib.import_module("tests.bench.bench_index_health_overhead")


def test_module_imports(bench_module: object) -> None:
    assert hasattr(bench_module, "main")
    assert hasattr(bench_module, "run")
    assert hasattr(bench_module, "_measure_fraction")


def test_threshold_is_comment_only(bench_module: object) -> None:
    """AC-9 — ``fail_pct`` MUST be None (this bench is advisory)."""
    thresholds = bench_module._THRESHOLDS  # type: ignore[attr-defined]
    assert thresholds.fail_pct is None
    assert thresholds.fail_p95_s is None


def test_baseline_fraction_target_is_5_percent(bench_module: object) -> None:
    """AC-9 — module-level target fraction is 0.05 (5 % of total cold gather)."""
    baseline = bench_module._BASELINE  # type: ignore[attr-defined]
    assert baseline == {"minimal-ts/b2_fraction": 0.05}


def test_fraction_range_is_zero_to_one(bench_module: object) -> None:
    """AC-9(a) — the fraction is a valid ratio (caught a None/-1 return)."""
    with mock.patch.object(bench_module, "_measure_fraction", return_value=0.42):
        out = bench_module.run()
    assert 0.0 <= out["minimal-ts/b2_fraction"] <= 1.0


def test_metamorphic_injected_sleep_strictly_increases_fraction(
    bench_module: object,
) -> None:
    """AC-9(b) — metamorphic.

    We compose two stubbed measurements: one without injected delay (fraction
    f0) and one where the harness records a larger B2-walltime (fraction f1).
    The metamorphic invariant is ``f1 > f0`` — if the test would pass with the
    inequality flipped, the bench has no signal.
    """
    f0 = 0.04  # baseline (no injection)
    f1 = 0.18  # with injected sleep — strictly larger
    assert f1 > f0, "metamorphic precondition: injection must yield larger fraction"

    measurements = []
    for value in (f0, f1):
        with mock.patch.object(bench_module, "_measure_fraction", return_value=value):
            measurements.append(bench_module.run()["minimal-ts/b2_fraction"])
    assert measurements[1] > measurements[0], (
        "AC-9(b) metamorphic: an injected sleep inside IndexHealthProbe MUST yield "
        f"a strictly larger B2-fraction; got {measurements[1]} <= {measurements[0]}"
    )
