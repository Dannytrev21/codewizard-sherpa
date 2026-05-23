# Story S3-07 — Event-log throughput bench baseline

**Step:** Step 3 — Canonical event log, BlobRef store, and activity-boundary sanitizer
**Status:** Ready
**Effort:** S
**Depends on:** S3-04 (read path; bench includes a small read leg for cache-warming realism), S3-06 (sanitizer; bench events flow through `seal` to mirror production-path cost)
**ADRs honored:** ADR-0003 (per-workflow chain — bench validates the per-workflow parallelism that the chain enables), ADR-0006 (sync vs batched flush split — bench measures both p95s), ADR-0012 (Postgres canonical store), production ADR-0034

## Context

The G6 exit criterion is "≥3000 events/sec sustained portfolio-wide from 5 activity workers; p95 commit ≤ 15 ms (sync) / ≤ 50 ms (batched)" (`phase-arch-design.md §C5`). S3-01..S3-06 ship the **machinery**; this story ships the **baseline measurement** plus the ratchet baseline file that future regressions cannot silently cross.

The bench scaffolding: `tests/perf/test_phase09_event_log_append.py` under the existing `bench` pytest marker. Runs nightly in CI (`make bench`), not on every PR. Asserts (a) 10k events across 50 concurrent workflows commit with p95 ≤ 50 ms batched / ≤ 15 ms sync; (b) the recorded p95s ratchet against `tests/bench/baselines/phase09_event_log_append.json`. A regression (> 1.5× the baseline) fails CI; a confirmed improvement (≥ 10% better than baseline over 5 consecutive runs) requires updating the baseline (manual; not auto-ratchet).

S3-07 is NOT the formal G6 exit-criterion test — S8-04 (`tests/perf/test_phase09_throughput.py`) ships the full G6 + token-canary + cold-replay suite. This story is the **per-component bench baseline** for the event-log machinery in isolation, runnable without Temporal / workers / the LangGraph subgraph.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C5 — Performance envelope` ("G6: ≥ 3000 events/sec sustained portfolio-wide from 5 activity workers; p95 commit ≤ 15 ms (sync) or ≤ 50 ms (batched)").
  - `../phase-arch-design.md §Performance regression tests` (the `-m bench` discipline; ratchet-baseline pattern).
  - `../phase-arch-design.md §Implementation-level risks #3` (back-pressure interaction with Temporal retries; bench should include a fault-injection scenario per S8-04).
- **Phase ADRs:**
  - `../ADRs/0003-per-workflow-blake3-prev-hash-chain.md` — the per-workflow chain enables concurrent-workflow parallelism the bench validates (50 concurrent workflows × 200 events each = 10k events).
  - `../ADRs/0006-critical-event-synchronous-flush-vocabulary.md` — the bench measures BOTH paths.
- **Existing code:**
  - `src/codegenie/events/log.py` (S3-01 through S3-04).
  - `pyproject.toml § [tool.pytest.ini_options] markers` — `bench` marker is already declared (CLAUDE.md notes "excluded by default").
  - Sibling bench precedents in the codebase: `tests/perf/` from Phase 2 (probe benchmarks); `tests/bench/baselines/` directory if it exists.
- **External:**
  - `pytest-benchmark` is a possible dep (check `pyproject.toml`); otherwise `time.perf_counter` + `statistics.quantiles` is sufficient.
  - psycopg-pool sizing under burst — `phase-arch-design.md §Implementation-level risks #4`.

## Goal

Ship `tests/perf/test_phase09_event_log_append.py` under the `bench` marker that: (a) drives 10k events across 50 concurrent workflows via `EventBatchWriter`; (b) drives 100 critical-event sync emits sequentially; (c) measures p95 wall-clock commit for both paths; (d) compares against a checked-in `tests/bench/baselines/phase09_event_log_append.json` baseline; (e) emits a structured-JSON results file consumable by the nightly CI baseline-ratchet check. Ship the initial baseline file with conservative numbers; future PRs see ratchet warnings if they drift.

## Acceptance criteria

- [ ] **AC-1 — Bench file under `bench` marker.** `tests/perf/test_phase09_event_log_append.py` is decorated `@pytest.mark.bench`. Default `make test` skips it. `make bench` (or `pytest -m bench`) runs it. The bench requires testcontainers Postgres (the `pg_pool` fixture from S3-01); CI's nightly bench job runs against a fresh container.
- [ ] **AC-2 — Batched-path bench: 10k events across 50 concurrent workflows.** The bench launches 50 `asyncio.gather`-d tasks; each task is one workflow emitting 200 events via `EventBatchWriter.enqueue` (non-critical kinds, so all ride the batched path). Total: 10k events. Measure wall-clock from first `enqueue` to last `await writer.flush()`. Assert p95 commit per event ≤ 50 ms (per `High-level-impl.md §Step 3 done-criteria`). The throughput target ≥3k events/sec is `10_000 / total_wall_clock_seconds ≥ 3000` ⇒ `total_wall_clock_seconds ≤ 3.33s`.
- [ ] **AC-3 — Sync-path bench: 100 critical-event emits sequentially.** Sequential (not concurrent — the sync path is per-emit RTT bound). 100 `MergeOutcome` emits one at a time; measure p95 wall-clock per emit. Assert p95 ≤ 15 ms.
- [ ] **AC-4 — Baseline file format.** `tests/bench/baselines/phase09_event_log_append.json` carries:
    ```json
    {
      "version": 1,
      "metric_units": "ms",
      "results": {
        "batched_p95_ms_per_event": 45.0,
        "sync_p95_ms_per_event": 14.0,
        "total_batched_wallclock_s": 3.0,
        "throughput_events_per_sec": 3333.0
      },
      "tolerance_factor": 1.5,
      "recorded_against": "psycopg 3.x, postgres 16-alpine, testcontainers shared-runner",
      "recorded_at": "2026-05-23T00:00:00Z"
    }
    ```
    Numbers are starting estimates; first GREEN run of the bench records the actual measured values back into this file (manual update — not auto-ratchet).
- [ ] **AC-5 — Ratchet logic.** If `measured_p95 > baseline.results.batched_p95_ms_per_event * baseline.tolerance_factor`, the test fails with a message naming the regression delta and the offending PR. The default `tolerance_factor=1.5` allows 50% drift over the baseline (catches actual regressions; tolerates CI noise). If `measured_p95 < baseline * 0.9` over 5 consecutive nightly runs (improvement evidence), CI emits a structured-log notice "Bench improvement persists; consider updating baseline"; **no auto-update**.
- [ ] **AC-6 — Bench result emission.** The bench writes a structured JSON to `tests/bench/results/phase09_event_log_append_${TIMESTAMP}.json` capturing the full distribution (p50, p95, p99, max, count). The nightly CI workflow archives this as a build artifact (S8-06 wires the CI plumbing — this story ships the file emission).
- [ ] **AC-7 — Chain integrity in bench results.** After the 10k batched events land, the bench runs `EventLog.read_workflow` against 3 random workflows and asserts each chain verifies (per S3-04). This catches a perf "win" that's actually a chain-corruption bug. Failure of chain-verify fails the bench loud.
- [ ] **AC-8 — Sanitizer in the bench path.** The bench events are constructed via `RedactedActivityResult.seal` (S3-06) for realism — the sanitizer's ~10-50 µs overhead is part of the measured cost. (The activities in Step 4 always go through `seal`; the bench should mirror.)
- [ ] **AC-9 — Bench is not flaky.** Run the bench 5 consecutive times locally; each run's p95 falls within the tolerance band. If variance is too high (run-over-run p95 differs by > 2×), document the source (likely shared CI runner noise) and adjust `tolerance_factor`. The bench MUST NOT be marked `@pytest.mark.flaky`.
- [ ] **AC-10 — Bench runs in < 60 s wall-clock.** Including testcontainer startup. CI's nightly bench job has a 60-s budget; if the bench exceeds it, narrow the workload (e.g., 5k events instead of 10k) and update the baseline.
- [ ] **AC-11 — `make bench` Makefile target.** `make bench` runs `pytest -m bench tests/perf/`. Documented in `docs/development.md` (Step 8 closeout — this story just wires the target).
- [ ] **AC-12 — Bench uses the same `EventBatchWriter` defaults as production.** `batch_size=256`, `flush_interval_ms=20`, `chain_lru_max=200` — all defaults from `DurableSettings` (S2-02). The bench MUST NOT cherry-pick favorable settings; the measurement is of the production-default configuration.

## Implementation outline

1. **Verify `bench` marker is registered** in `pyproject.toml § [tool.pytest.ini_options] markers`. Sibling Phase-2 benches confirm; CLAUDE.md notes the marker exists.
2. **Construct the bench scaffolding.**
    ```python
    @pytest.mark.bench
    @pytest.mark.asyncio
    async def test_event_log_batched_p95_under_50ms(pg_pool, fresh_events_schema):
        """G6 sanity floor — batched-path commit p95 ≤ 50 ms.
        10k events across 50 concurrent workflows."""
        log = EventLog(pool=pg_pool)
        writer = EventBatchWriter(log=log)
        await writer.start()
        cap = _full_capability_for("system")

        async def one_workflow(wf_id: int):
            wf = WorkflowId(f"bench-wf-{wf_id:03d}")
            for i in range(200):
                event = _make_bench_event(wf=wf, seq=i)  # routes through seal
                await writer.enqueue(event, capability=cap)
            await writer.flush()

        start = time.perf_counter()
        await asyncio.gather(*[one_workflow(i) for i in range(50)])
        await writer.stop()
        elapsed = time.perf_counter() - start

        # ... gather per-event timing via writer's internal hooks or per-batch log
        results = _summarize_bench_results(elapsed, total_events=10_000)
        _emit_results_json("phase09_event_log_append", results)
        _assert_against_baseline("phase09_event_log_append", results)
    ```
3. **Per-event timing collection** — the simplest accurate approach: bracket `await writer.enqueue` calls with `time.perf_counter()`. The enqueue itself is microsecond-scale (returns before flush); the meaningful unit is `total_wallclock / 10_000` (effective per-event commit cost amortized across the batched path). Document this measurement choice in the test docstring.
4. **Baseline I/O helpers** — small `_load_baseline(name)` and `_emit_results_json(name, results)` functions in a `tests/bench/_helpers.py` module. Shared across S3-07 and future perf stories.
5. **`_make_bench_event` factory** — constructs `RouteDecided` (non-critical, batched) or `MergeOutcome` (critical, sync) per the bench branch; routes through `RedactedRouteDecidedOutput.seal(...)` for realism (S3-06 sanitizer in the path).
6. **Chain-verify post-flush** — after the bench, sample 3 workflows and read them back via `EventLog.read_workflow`; consume the async iterator; if any raises `ChainBrokenError`, the bench fails.
7. **Initial baseline numbers.** First run produces actual measurements; update the JSON in the same PR before merging. Numbers in AC-4 are placeholders that the implementer replaces with first-run reality.

## TDD plan — red / green / refactor

### Red — failing test first

Test file path: `tests/perf/test_phase09_event_log_append.py`

Test intent: The bench harness exists and asserts against a baseline file. The first run produces a `KeyError` or `FileNotFoundError` because the baseline file doesn't exist yet.

```python
# Test outline only.
@pytest.mark.bench
async def test_batched_p95_against_baseline(pg_pool, fresh_events_schema):
    """G6 sanity floor — batched-path commit p95 ≤ baseline × tolerance.
    The first run fails on missing baseline file; commit the baseline,
    then re-run to GREEN."""
    log = EventLog(pool=pg_pool)
    writer = EventBatchWriter(log=log)
    await writer.start()
    # ... drive workload, measure
    results = await _run_batched_bench(writer)
    await writer.stop()

    baseline = _load_baseline("phase09_event_log_append")  # raises FileNotFoundError first run
    _assert_against_baseline(results, baseline)
```

Why it fails: `tests/bench/baselines/phase09_event_log_append.json` doesn't exist.

### Green — minimal pass

- Create the baseline JSON with the placeholder numbers from AC-4.
- Run the bench locally; record the actual measured values; update the baseline file.
- Commit baseline + the new bench file together.
- Re-run; passes.

### Required follow-on tests

- **`test_sync_p95_under_15ms`** (AC-3) — 100 sequential critical emits; assert p95 ≤ 15 ms.
- **`test_chain_integrity_after_bench`** (AC-7) — sample 3 workflows; chain-verify.
- **`test_baseline_ratchet_fails_loud_on_regression`** — synthetic test that forges a "measured" p95 value 2× the baseline and asserts `_assert_against_baseline` raises with the expected diff message. (Tests the harness itself.)
- **`test_baseline_improvement_emits_notice_only`** — synthetic test that forges a "measured" value 0.5× the baseline and asserts NO failure but a structured-log notice.
- **`test_bench_completes_under_60s`** (AC-10) — wraps the main bench in `asyncio.wait_for(..., timeout=60)`.

### Refactor

- The bench helpers (`_load_baseline`, `_emit_results_json`, `_assert_against_baseline`) live in `tests/bench/_helpers.py` for reuse by future perf stories (S8-04 will use the same pattern for the throughput / route-activity / token canary).
- Document the bench discipline in the test file's module docstring: "This bench measures the event-log machinery in isolation. The formal G6 exit-criterion test (Temporal + workers + LangGraph end-to-end) is S8-04."
- Baseline file is human-edited; the README in `tests/bench/baselines/` (S8-06 ships the README) explains when to update.

## Files to touch

| Path | Why |
|---|---|
| `tests/perf/__init__.py` | Test package marker (may exist). |
| `tests/perf/test_phase09_event_log_append.py` | The bench file. |
| `tests/bench/__init__.py` | Empty package marker. |
| `tests/bench/_helpers.py` | `_load_baseline`, `_emit_results_json`, `_assert_against_baseline`. |
| `tests/bench/baselines/__init__.py` | Marker (empty). |
| `tests/bench/baselines/phase09_event_log_append.json` | The ratchet baseline. **Numbers updated after first GREEN run.** |
| `tests/bench/baselines/README.md` | Brief: "when to update; tolerance philosophy". (S8-06 may move this to `docs/` — coordinate.) |
| `Makefile` | `make bench` target — `pytest -m bench`. |

## Out of scope

- **Full G6 throughput test** — S8-04 (`tests/perf/test_phase09_throughput.py`) — runs the full Temporal-worker-LangGraph stack and asserts ≥3k events/sec from 5 workers. This story is the per-component baseline only.
- **Token canary (G11)** — S8-04. Cassette-replay zero-token assertion.
- **Cold-replay latency bench** (200-event history ≤ 1.5 s p95) — S8-04.
- **Route-activity overhead canary** (Gap-1) — S8-04.
- **Connection-pool sizing tune** — `phase-arch-design.md §Implementation-level risks #4`. This bench may surface evidence that `pool_maxsize=20` is wrong; raise as a follow-up story.
- **Adversarial back-pressure scenario** (Postgres `pg_sleep(2.0)` fault injection) — S8-04. This story's bench runs against healthy Postgres only.
- **Auto-ratchet of baselines on persistent improvement** — explicitly out per AC-5. Manual baseline updates are a code-review signal.

## Notes for the implementer

### §1 — First-run baseline is the implementer's job

The numbers in AC-4 are placeholders. The first time this bench runs locally on the implementer's machine, capture the actual measured p95s and total wall-clock; update the JSON; commit baseline + bench together. CI's nightly bench will then ratchet against those numbers.

If the implementer's machine is significantly faster or slower than CI (e.g., M-series laptop vs shared CI runner), the baseline may need a re-record after first CI run. **Prefer to record on CI** if possible (run the bench in a PR, capture the result from the build artifact, copy into the baseline file, push the update). The PR description should say "First bench run; baseline captured from CI build #X".

### §2 — `total_wallclock / N` is the right per-event metric for batched

Per-event timing in a batched path is misleading — every `enqueue` returns in microseconds (no commit yet). The commit cost is amortized across the batch. The right metric is `total_wallclock_seconds / total_events` averaged across the run.

For the sync path, per-emit timing IS the right metric (each emit commits before returning). Use `time.perf_counter()` around each `await writer.enqueue(critical_event, ...)` and compute p95 from the distribution.

### §3 — `tolerance_factor=1.5` is the starting bet

CI shared runners are noisy. A factor of 1.5 (50% headroom) catches genuine regressions while tolerating noise. After 10 nightly runs, examine the variance:
- If p95 oscillates within ±20%, tighten to 1.3.
- If p95 oscillates within ±50%, keep at 1.5 (the band is the noise floor).
- If p95 oscillates beyond 2×, the bench is flaky — investigate the cause (likely a shared runner with a busy neighbor); do NOT mark `@pytest.mark.flaky` (per AC-9).

The factor is a single number in the baseline JSON; tuning is a one-line edit.

### §4 — The bench MUST NOT skip `seal`

Production activities all return through `RedactedActivityResult.seal` (S3-06). The bench's events must also flow through `seal` to capture the real per-event cost. Skipping `seal` would falsely inflate the measured throughput.

The `_make_bench_event` factory constructs a model AND seals it before returning. If `seal` itself becomes the bottleneck (it shouldn't — ~10-50 µs), that's a signal to investigate, not to remove the seal.

### §5 — Chain-verify in the bench catches "fast but wrong"

A perf "win" that omits the chain-head LRU update is faster but corrupts the chain. AC-7's post-bench chain-verify on 3 sample workflows catches this. The verify cost is negligible (~5 ms per workflow); always include it.

If a future story adds bench scaffolding for other components, mirror this discipline: **after every perf bench, verify the correctness invariant the component is supposed to preserve.**

### §6 — Bench results live alongside the source

`tests/bench/results/` (the per-run JSON files) is NOT in `.gitignore` by default. The CI workflow archives these as artifacts; locally, the directory accumulates files (the implementer can `rm tests/bench/results/*.json` periodically).

If the directory grows unbounded, add it to `.gitignore`. For now, keeping local results visible helps the implementer notice trends without checking CI.

### §7 — Not adopted (YAGNI)

- **`pytest-benchmark` plugin** — not adopted unless the codebase already uses it. Manual `time.perf_counter` + `statistics.quantiles` is sufficient and one fewer dep.
- **Continuous profiling integration** — out of scope for Phase 9. Phase 13+ observability landing OTel can layer profiling.
- **Multi-machine bench (Locust/k6 style)** — out of scope. The bench is a single-process load generator hitting a single testcontainer Postgres. Multi-machine load testing is a Phase 16 hardening concern.
- **Bench-driven autotuning of `batch_size` / `flush_interval_ms`** — explicitly out. The defaults in `DurableSettings` are the contract; bench validates them, doesn't tune them.
