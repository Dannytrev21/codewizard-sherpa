# Story S9-03 — Bench harness + 7-day rolling baseline

**Step:** Step 9 — CI gates, import-linter contracts, performance baselines, bench backfill hook
**Status:** Ready
**Effort:** M
**Depends on:** S9-01
**ADRs honored:** ADR-0008 (`BundleBuilder` deterministic serial fallback + `vuln_index.digest` cache key — `bench_bundle_builder_{warm,cold}` measure the very property that ADR commits to), ADR-0005 (two-stream event log — `bench_event_appender_throughput` measures the spanning-stream write path under load), ADR-0002 (`PluginRegistry` kernel — `bench_plugin_registry_build` measures the kernel construction cost), ADR-0009 (`RecipeEngine` Protocol — `bench_recipe_match` measures the plugin-local `RecipeRegistry` iteration cost)

## Context

Phase 3 commits to seven specific performance budgets (`phase-arch-design.md §Testing strategy / Performance regression budgets`). They are not aspirational; each names a load-bearing component and a budget the component must meet on `ubuntu-24.04` × Python 3.11 / 3.12. The seven:

| Bench | Budget |
|---|---|
| `bench_plugin_registry_build` | < 500 ms for 3 plugins |
| `bench_bundle_builder_warm` | < 5 ms |
| `bench_bundle_builder_cold` | < 300 ms |
| `bench_vuln_index_lookup` | < 10 ms p99 over 100 lookups |
| `bench_recipe_match` | < 60 ms p95 |
| `bench_event_appender_throughput` | > 30,000 events/sec |
| `bench_workflow_e2e_warm` | < 20 s p50, < 35 s p95 |

Absolute thresholds catch the catastrophic regressions but miss the slow creep. The relative-budget assertion is the complementary gate: a benchmark that runs in `0.8 × budget` today and `0.79 × budget` tomorrow does not trip the absolute, but a 30% slowdown still indicates a regression worth investigating. Phase 3 ships the **7-day rolling mean baseline + 25%-regression assertion**: every CI green run appends its measurement to `tests/bench/.baseline.json` keyed by `(bench_name, python_version)`; a new run computes the mean over the last 7 days' worth of entries and fails the bench job if the new measurement exceeds `1.25 × mean`. First-ever run seeds the baseline (no assertion); subsequent runs assert.

Phase 2's existing `tests/bench/` has three bench files (`test_cache_hit_dispatch.py`, `test_cli_cold_start.py`, `test_coordinator_overhead.py`) gated by the `bench` pytest marker and run advisorily via `pytest tests/bench/ -m bench` (see `.github/workflows/ci.yml § test step "bench (advisory)"`). The current `bench-collection-guard` step asserts exactly 3 bench tests collected — Phase 3 needs to relax this to 10 (3 Phase 2 + 7 Phase 3) and update the guard accordingly. **The Phase 3 bench job is gating, not advisory:** `phase-arch-design.md §Testing strategy / Performance regression budgets` names this as a CI gate (`> 25% regression vs. 7-day rolling mean fails`). The Phase 2 `continue-on-error: true` shape does not carry forward; the new bench job blocks merge on regression. (Variance on shared GitHub runners is the known risk; mitigation is the `pytest-benchmark`-style multi-round sampling described in the Implementation outline.)

S9-01 wired the CI matrix and `make check`. This story lands the seven bench files, the baseline-recording harness, the relative-regression assertion, and the CI job that gates on the result.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy / Performance regression budgets` — the seven verbatim budgets above; relative-budget rule "> 25% regression vs. 7-day rolling mean fails."
  - `../phase-arch-design.md §Open questions deferred to implementation` ("CI runner concurrency tuning ... record the rolling-7-day baseline at first CI green") — this story owns the answer.
  - `../phase-arch-design.md §Implementation-level risks #1` (`bwrap` availability) — bench tests that depend on the jail (`bench_bundle_builder_cold`, `bench_workflow_e2e_warm`) fail if S9-01's `apt-get install -y bubblewrap` step is missing.
  - `../High-level-impl.md §Step 9 — Bench harness` — itemizes the seven bench files by exact path under `tests/bench/`.
- **Phase ADRs:**
  - `../ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md` — what `bench_bundle_builder_{warm,cold}` measure: warm hits the cache (key includes `vuln_index.digest`); cold misses and rebuilds.
  - `../ADRs/0005-two-stream-event-log-per-adr-0034.md` — the `fcntl.flock`-protected BLAKE3-chained spanning stream is what `bench_event_appender_throughput` measures under contention.
  - `../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md` — the kernel `bench_plugin_registry_build` measures: filesystem walk → `importlib.import_module` × N → integrity check.
- **Existing code:**
  - `tests/bench/test_cache_hit_dispatch.py`, `test_cli_cold_start.py`, `test_coordinator_overhead.py` — Phase 2 bench pattern (`@pytest.mark.bench`, `pytest-benchmark`-style timing, JSON output). Mirror the shape.
  - `.github/workflows/ci.yml § test job — "bench-collection-guard" and "bench (advisory)"` — the existing CI bench steps; this story relaxes the guard to 10 and adds a gating `bench` job (separate from the advisory one OR by removing `continue-on-error: true` — pick whichever preserves the Phase 2 canary signal).
  - `pyproject.toml § [tool.pytest.ini_options].markers` — `bench` marker already declared; no new marker needed.

## Goal

Land seven bench files under `tests/bench/` measuring the seven Phase 3 components against the verbatim budgets; ship a 7-day rolling baseline harness that records measurements per `(bench, python_version)` to `tests/bench/.baseline.json` and fails the CI bench job on > 25% regression vs. the rolling mean. The bench job is gating, not advisory, for the seven Phase 3 benchmarks (the three Phase 2 canaries remain advisory).

## Acceptance criteria

- [ ] `tests/bench/bench_plugin_registry_build.py` (NEW) constructs a fresh `PluginRegistry` and loads three plugins (vuln-node-npm + universal + `example--noop--*`). Asserts wall-clock < 500 ms. Marker `@pytest.mark.bench`.
- [ ] `tests/bench/bench_bundle_builder_warm.py` (NEW) pre-populates `.codegenie/cache/bundles/` (cache hit), then measures `BundleBuilder.build(...)`. Asserts < 5 ms.
- [ ] `tests/bench/bench_bundle_builder_cold.py` (NEW) clears the cache, runs `BundleBuilder.build(...)`. Asserts < 300 ms.
- [ ] `tests/bench/bench_vuln_index_lookup.py` (NEW) runs 100 `VulnIndex.lookup(...)` calls; asserts p99 < 10 ms.
- [ ] `tests/bench/bench_recipe_match.py` (NEW) iterates a plugin's `RecipeRegistry` against a synthetic `Plan`; asserts p95 < 60 ms (over ≥ 20 samples).
- [ ] `tests/bench/bench_event_appender_throughput.py` (NEW) emits ≥ 100k events in a tight loop to the spanning stream (single-process; `fcntl.flock` round-trip per emit per ADR-0005); asserts throughput > 30,000 events/sec.
- [ ] `tests/bench/bench_workflow_e2e_warm.py` (NEW) runs `codegenie remediate` against the `express-cve-2024-21501/` fixture with caches pre-warmed (vuln-index, bundle, npm `--prefer-offline`); asserts p50 < 20 s and p95 < 35 s over ≥ 5 samples.
- [ ] `tests/bench/_baseline.py` (NEW) — helper module exposing `record_and_assert(bench_name, measurement, *, python_version=sys.version_info[:2], baseline_path=...)`. Behavior: load `tests/bench/.baseline.json` (empty if missing); compute mean over entries within the last 7 days for `(bench_name, python_version)`; if entry count < 1, append and skip assertion ("baseline seed run"); else assert `measurement <= 1.25 * mean` with a diagnostic naming the regression %.
- [ ] `tests/bench/.baseline.json` (NEW, gitignored) is created on first CI green; subsequent runs append. Schema documented in `tests/bench/_baseline.py` docstring (entries: `{bench_name, python_version, measurement_value, units, recorded_at_iso_utc}`).
- [ ] Each of the seven bench files calls `record_and_assert(...)` after asserting its absolute budget — both gates must pass.
- [ ] `.github/workflows/ci.yml § test job — bench-collection-guard` is updated from `-ne 3` to `-ne 10` (3 Phase 2 + 7 Phase 3). The Phase 3 seven bench files are wired into a **gating** bench step (`continue-on-error: false`, separate from the existing advisory step OR by promoting the advisory step for the Phase 3 names only — pick whichever keeps Phase 2 canaries advisory and Phase 3 benches gating, surfacing the decision in `test_ci_workflow.py`).
- [ ] CI uploads `tests/bench/.baseline.json` as a workflow artifact (mirrors the existing `bench-results` upload pattern) so historical baselines persist across runner instantiations. Restoring the artifact at job start is part of the baseline-rolling story — document the choice (cache action vs. artifact-download — actions/cache@v4 with a `bench-baseline-v1` key is the recommended shape).
- [ ] `test_ci_workflow.py` (existing) asserts the bench-collection-guard count is 10 and that the gating bench step is wired with `continue-on-error: false` for the Phase 3 names.
- [ ] `mypy --strict` clean; `ruff check`, `ruff format --check` clean on touched files.
- [ ] TDD plan's red test exists, committed, green.

## Implementation outline

1. **`tests/bench/_baseline.py`.** Pure-Python module: `load_baseline(path) -> dict`, `record(...)`, `compute_rolling_mean(entries, *, days=7) -> float | None`, `record_and_assert(...)`. JSON shape pinned; `datetime.fromisoformat` for the windowing. Keep it tiny (~80 LoC); no third-party deps.
2. **Seven bench files.** Mirror the Phase 2 `test_cache_hit_dispatch.py` shape: one `@pytest.mark.bench` test per file; absolute assertion first; then `record_and_assert(...)` second. Each bench uses `time.perf_counter()` deltas over ≥ N samples (N = 20 for p95-style benches, 100 for `bench_vuln_index_lookup`, 5 for `bench_workflow_e2e_warm`); compute p50 / p95 / p99 with `statistics.quantiles`.
3. **`bench_workflow_e2e_warm.py`'s warmup.** Phase-3-realistic: prime the bundle cache via one `BundleBuilder.build(...)` outside the timed region; prime npm via `--prefer-offline` pre-fetch into a project-local cache committed under `tests/fixtures/npm-cache/` (or constructed in the test fixture). Without warmup the 20 s p50 budget is unmeetable; the **first** run still records the cold baseline elsewhere (the `bench_bundle_builder_cold` file owns cold).
4. **Baseline file lifecycle.** `tests/bench/.baseline.json` in `.gitignore` (the file is per-runner state). CI restores via `actions/cache@v4` keyed `bench-baseline-${{ runner.os }}-${{ matrix.python }}-v1` so 3.11 and 3.12 baselines do not contaminate each other.
5. **CI integration.** In `.github/workflows/ci.yml`, after the existing advisory `bench (advisory)` step (which preserves the Phase 2 canary signal), add a `bench (gating)` step running only the seven Phase 3 files with `continue-on-error: false`. Verify the matrix entries inherited from S9-01 are in effect.
6. **Variance mitigation.** Each bench warms by running the operation once outside the timing region (eliminates first-import / first-syscall cost from the measurement). Each bench takes ≥ 5 samples (≥ 20 for p95, ≥ 100 for p99) and reports the quantile, not the single best run.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/bench/_baseline.py` (helper) + `tests/bench/test_baseline_unit.py`

```python
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.bench._baseline import compute_rolling_mean, record_and_assert


def _entry(bench: str, val: float, days_ago: float, py: tuple[int, int] = (3, 11)) -> dict:
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {
        "bench_name": bench,
        "python_version": list(py),
        "measurement_value": val,
        "units": "ms",
        "recorded_at_iso_utc": ts.isoformat(),
    }


def test_rolling_mean_excludes_entries_older_than_7_days() -> None:
    entries = [_entry("b", 100.0, 1), _entry("b", 200.0, 3), _entry("b", 999.0, 10)]
    mean = compute_rolling_mean(entries, bench_name="b", python_version=(3, 11), days=7)
    assert mean == pytest.approx(150.0)  # 999 excluded; (100+200)/2


def test_record_and_assert_seeds_on_empty_baseline(tmp_path: Path) -> None:
    """Why: first ever CI green must seed without failing — no baseline to
    compare against (phase-arch-design.md §Open questions)."""
    bp = tmp_path / "baseline.json"
    bp.write_text("[]")
    record_and_assert("b", 100.0, units="ms", baseline_path=bp)  # must not raise
    data = json.loads(bp.read_text())
    assert len(data) == 1


def test_record_and_assert_fails_on_25_percent_regression(tmp_path: Path) -> None:
    """Why: the cardinal Phase 3 regression rule. 25% above the rolling mean
    is the threshold per phase-arch-design.md §Testing strategy."""
    bp = tmp_path / "baseline.json"
    bp.write_text(json.dumps([_entry("b", 100.0, 1) for _ in range(3)]))
    with pytest.raises(AssertionError, match="regression"):
        record_and_assert("b", 126.0, units="ms", baseline_path=bp)


def test_record_and_assert_accepts_within_25_percent(tmp_path: Path) -> None:
    bp = tmp_path / "baseline.json"
    bp.write_text(json.dumps([_entry("b", 100.0, 1) for _ in range(3)]))
    record_and_assert("b", 124.0, units="ms", baseline_path=bp)  # must not raise


def test_python_versions_do_not_cross_contaminate(tmp_path: Path) -> None:
    """Why: 3.12 measurements must not poison 3.11's baseline (different
    interpreters have systematically different startup cost)."""
    bp = tmp_path / "baseline.json"
    bp.write_text(json.dumps([_entry("b", 50.0, 1, py=(3, 12))]))
    # 3.11 sees empty baseline -> seeds; no regression assertion.
    record_and_assert("b", 1000.0, units="ms", baseline_path=bp, python_version=(3, 11))
```

State why it fails: `tests/bench/_baseline.py` does not exist; the seven bench files do not exist; the bench-collection-guard count is 3.

### Green — minimal pass
- Write `tests/bench/_baseline.py` to satisfy the four unit tests.
- Write the seven bench files. Each calls `record_and_assert(bench_name=__name__.rsplit('.', 1)[-1], ...)` after its absolute assertion.
- Update `.github/workflows/ci.yml`: collection-guard count 3 → 10; add gating bench step.
- Update `test_ci_workflow.py` for the new collection-guard count + gating step shape.

### Refactor
- Lift sample-collection + quantile helpers into `tests/bench/_helpers.py` so the seven bench files share `def sample_p95(callable, n=20) -> float`.
- Add a `make bench` Makefile target running `pytest tests/bench/ -m bench --no-cov` for local pre-flight.
- Document the baseline-cache key + invalidation policy in the helper module docstring (key change = baseline reset; runners that hit a new key see "seed" behavior, which is correct).
- Edge cases from §Edge cases that touch this code: variance on shared CI runners (the documented Phase 2 risk). Mitigation: multi-sample + quantile, not single-run min/max. If a bench is chronically flaky on ubuntu-24.04 specifically, surface it (do not weaken the assertion) and pick whether to retry-tactic or budget-amend via an ADR amendment.

## Files to touch

| Path | Why |
|---|---|
| `tests/bench/_baseline.py` | NEW — rolling-baseline helper (load / mean / record / assert). |
| `tests/bench/test_baseline_unit.py` | NEW — unit tests for the helper. |
| `tests/bench/bench_plugin_registry_build.py` | NEW — kernel build < 500 ms. |
| `tests/bench/bench_bundle_builder_warm.py` | NEW — cache-hit < 5 ms. |
| `tests/bench/bench_bundle_builder_cold.py` | NEW — cache-miss < 300 ms. |
| `tests/bench/bench_vuln_index_lookup.py` | NEW — p99 < 10 ms over 100 lookups. |
| `tests/bench/bench_recipe_match.py` | NEW — p95 < 60 ms over ≥ 20 samples. |
| `tests/bench/bench_event_appender_throughput.py` | NEW — > 30k events/sec to spanning stream. |
| `tests/bench/bench_workflow_e2e_warm.py` | NEW — e2e p50 < 20 s, p95 < 35 s. |
| `.gitignore` | Add `tests/bench/.baseline.json` (per-runner state). |
| `.github/workflows/ci.yml` | Bump collection-guard 3 → 10; add gating bench step; wire `actions/cache@v4` for baseline persistence. |
| `tests/unit/test_ci_workflow.py` | Update collection-guard assertion; assert gating step shape. |
| `Makefile` (optional) | Add `bench` convenience target. |

## Out of scope

- **`BenchReplayable` event payload + Phase 6.5 backfill** — owned by S9-04.
- **`docs/operations/phase03-runbook.md`** — owned by S9-04.
- **Macroscopic optimization** — if a bench fails its absolute budget, this story does NOT include a perf investigation; surface the regression and open a follow-up. The baseline assertion catches creep; budget violations are a separate diagnostic loop.
- **Microbenchmark for `TrustScorer.score`** — the seven listed budgets are exhaustive for Phase 3. `TrustScorer.score` is dominated by `npm install` + `npm test` wall-clock (already covered by `bench_workflow_e2e_warm`).
- **Comparing Phase 3 perf to Phase 2** — Phase 2's three bench canaries remain advisory and are separately scoped.
- **Postgres-backed baseline persistence** — Phase 9 may move the rolling baseline into the production-side event store; Phase 3 ships the JSON-file shape.

## Notes for the implementer

- **The seven benchmark names are verbatim.** Do not rename to "more pythonic" forms (e.g., `bench_plugin_registry_build_test.py`). The names appear in `phase-arch-design.md §Testing strategy` and in the rolling-baseline JSON keys — drift between the names and the doc will silently break baseline matching. The file *prefix* is `bench_` (not `test_`) deliberately so the collection guard counts them correctly.
- **`pytest-benchmark` is tempting but not required.** The Phase 2 bench files use `time.perf_counter()` directly; mirror that for consistency. `pytest-benchmark`'s rich output is nice-to-have, not load-bearing for the 25%-regression assertion.
- **The 25% threshold is not configurable.** Hard-coded in `record_and_assert(...)` per `phase-arch-design.md §Testing strategy`. Operators who want to widen it must amend that section (architecture commitment), not tweak a constant.
- **Baseline persistence vs. portability.** `actions/cache@v4` keyed by `bench-baseline-${{ runner.os }}-${{ matrix.python }}-v1` is the production-facing answer. Operators running locally may want a separate baseline; the helper accepts a `baseline_path` override for that reason — keep the signature accommodating both paths.
- **`bench_event_appender_throughput` measures the spanning stream specifically.** The per-workflow `internal` stream does NOT use `fcntl.flock` (per-workflow file; no cross-process contention) and would benchmark differently. The 30k events/sec budget applies to the spanning stream — that is what S6-01's BLAKE3 chain + `fcntl.flock` round-trip has to sustain.
- **`bench_workflow_e2e_warm` budget includes `npm install` + `npm test`.** Those wall-clocks dominate; if the budget feels tight, verify the warmup (pre-warmed bundle cache + `--prefer-offline` npm) is in effect. Without warmup the budget is wildly unmeetable; with warmup it's the floor + a few hundred ms of orchestrator overhead.
- **Variance is the enemy.** Multi-sample + quantile is the right answer for the four benches with p-quantile budgets. For single-shot benches (`bench_plugin_registry_build`, `bench_bundle_builder_{warm,cold}`, `bench_event_appender_throughput`), take 5+ samples and assert against the median (not the minimum, not the maximum) — minimum hides regressions, maximum trips on noise.
- **The collection-guard bump 3 → 10 is the single brittle integration point with S9-01.** If S9-01 already bumped it (or restructured), reconcile against `test_ci_workflow.py` and document which story owns the count.
