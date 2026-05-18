"""S8-03 AC-8 — smoke test for ``bench_portfolio_walltime``.

The full bench runs a 25-invocation subprocess sweep across five fixtures
(cold + warm × 5 runs × 5 fixtures). That is too slow for a unit run. The
smoke test imports the module, runs ``_measure_fixture`` against
``minimal-ts`` only with ``_RUNS_PER_MODE`` temporarily collapsed to 1, and
asserts the returned dict carries the contractual keys.

Reliability note: this test depends on the ``codegenie gather`` CLI working
end-to-end on ``tests/fixtures/portfolio/minimal-ts``. If the gather CLI
breaks, the `integration` lane is the primary signal — not this smoke. We
catch and skip on subprocess failure to avoid noise here; the gating signal
is held elsewhere.
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
    """Fresh import; clears any cached module state."""
    sys.path.insert(0, str(_REPO_ROOT))
    if "tests.bench.bench_portfolio_walltime" in sys.modules:
        del sys.modules["tests.bench.bench_portfolio_walltime"]
    return importlib.import_module("tests.bench.bench_portfolio_walltime")


def test_module_imports_without_executing_main(bench_module: object) -> None:
    """Importing the module must NOT trigger a 25-invocation bench sweep."""
    assert hasattr(bench_module, "main")
    assert hasattr(bench_module, "run")
    assert hasattr(bench_module, "_measure_fixture")


def test_thresholds_advisory_only(bench_module: object) -> None:
    """AC-8 — this bench is comment-only (advisory). ``fail_pct`` is None."""
    thresholds = bench_module._THRESHOLDS  # type: ignore[attr-defined]
    assert thresholds.fail_pct is None, (
        "bench_portfolio_walltime is advisory; fail_pct must be None "
        "(gating contract lives in bench_portfolio_walltime_hosted_runner)"
    )
    assert thresholds.fail_p95_s is None


def test_runs_returns_contractual_keys_when_subprocess_is_stubbed(
    bench_module: object, tmp_path: Path
) -> None:
    """AC-8 — ``run({fixture})`` shape: every key is ``<fixture>/<mode>_p50_s``.

    We stub ``subprocess.run`` so the test doesn't actually launch the gather
    CLI — that's the `integration` lane's job. The smoke is structural: the
    output dict has the right keys with float values.
    """
    fake_completed = mock.Mock(returncode=0, stdout=b"", stderr=b"")
    with mock.patch.object(bench_module, "subprocess") as fake_sp:
        fake_sp.run.return_value = fake_completed
        # Avoid the 5-run-per-mode loop in the smoke run.
        with mock.patch.object(bench_module, "_RUNS_PER_MODE", 1):
            measurements = bench_module.run(fixture_filter=("minimal-ts",))
    assert set(measurements.keys()) == {"minimal-ts/cold_p50_s", "minimal-ts/warm_p50_s"}, (
        f"unexpected keys: {sorted(measurements.keys())}"
    )
    for key, value in measurements.items():
        assert isinstance(value, float), f"{key}: expected float, got {type(value).__name__}"
        assert value >= 0.0, f"{key}: walltime must be non-negative"
