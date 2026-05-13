# Story S3-02 — Asyncio fan-out + bounded semaphore + Welford aggregator

**Step:** Step 3 — Implement the runner: asyncio fan-out, subprocess rubric, aggregator with BCa bootstrap
**Status:** Ready
**Effort:** M
**Depends on:** S3-01 (plan phase), S2-03 (content-addressed cache)
**ADRs honored:** ADR-0001 (subprocess invocation is per-worker), ADR-0002 (deterministic per-case order at report time), ADR-0010 (`isolation_class` on emitted report)

## Context

Given the `RunPlan` from S3-01, this story executes the per-case work. Each worker probes the cache, then on a miss awaits the SUT (Phase 6's `build_vuln_loop`, injected as a callable), then invokes the rubric (S3-03 wires the real subprocess; this story uses an **in-process stub rubric** so the fan-out shape is independently testable). A single aggregator `asyncio.Task` consumes a queue, rolling Welford mean/stddev, and at report time orders entries deterministically by `case_id`.

The architectural invariant (arch §Determinism row "runner scheduling") is: **completion order is non-deterministic; report order is not.** Two runs of the same plan with random jitter in SUT completion times must produce byte-identical `per_case` tuples when serialized. This is what makes the audit chain reproducible.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Process view` — the asyncio sequence diagram (per-case worker → queue → aggregator → audit).
  - `../phase-arch-design.md §Determinism vs probabilism` row "runner scheduling" — non-deterministic completion order; deterministic report order via `case_id` sort at emit time.
  - `../phase-arch-design.md §Components → runner.py` — six-phase pipeline; this story owns phases 2 (cache probe), 3 (execute), 4 (aggregate).
  - `../phase-arch-design.md §Concurrency` paragraph — bounded by `asyncio.Semaphore(N=min(os.cpu_count(), 4))`, overridable via `--concurrency`.
  - `../phase-arch-design.md §Edge cases #16` (corrupt cache → treated as miss) and `#17` (concurrent run conflict).
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md` — the rubric runs across a process boundary per worker; this story leaves the seam open via an injected `rubric_runner: Callable` (S3-03 substitutes the real subprocess invocation).
  - `../ADRs/0010-isolation-class-annotation-on-bench-run-report.md` — `BenchRunReport.isolation_class = "subprocess"` is set unconditionally by this story; flip is Phase 16's job.
- **Source design:** `../final-design.md §Components → runner.py` ("async def; the harness is async-shaped from Phase 6.5 because Phase 6's SUT is async (LangGraph ainvoke)").
- **Open question:** OQ #1 — `min(cpu_count(), 4)` floor; document the override flag in the docstring; **do not** raise the floor in this story.

## Goal

Implement `Runner.execute(plan, *, system_under_test, rubric_runner, concurrency=None, on_score=None) -> BenchRunReport` that fans out per-case workers under `asyncio.Semaphore(min(cpu_count(), 4))` (overridable), aggregates via Welford, and produces a `BenchRunReport` with `per_case` sorted by `case_id`, `complete=True`, and `isolation_class="subprocess"`.

## Acceptance criteria

- [ ] `Runner.execute(plan, *, system_under_test, rubric_runner, concurrency=None, on_score=None) -> BenchRunReport` is the sole new public symbol.
- [ ] Default concurrency = `min(os.cpu_count() or 1, 4)`; explicit `concurrency=N` overrides; `concurrency <= 0` raises `ValueError`.
- [ ] The aggregator is a single `asyncio.Task` consuming an `asyncio.Queue[BenchScore | _Sentinel]`; multiple aggregator tasks would race the Welford state — a static test asserts only one aggregator task is created (`asyncio.all_tasks` count diff).
- [ ] Welford mean/stddev: numerically stable single-pass; correct to `1e-12` on `[0.2, 0.5, 0.8]` returning `mean=0.5`, `stddev=0.3`.
- [ ] On the 3-case stub bench with a deterministic stub SUT and the in-process stub rubric, `Runner.execute(...)` returns a `BenchRunReport` with: `complete=True`, `isolation_class="subprocess"`, three `per_case` entries ordered by `case_id`, `mean_score == sum/3` within `1e-12`, `lower_bound_95 == 0.0` (placeholder — filled by S3-05).
- [ ] **Determinism under completion-order jitter**: a property test runs the same plan three times with `asyncio.sleep` jitter randomized via Hypothesis; all three `per_case` tuples are byte-identical when JSON-serialized.
- [ ] Cache probe happens *inside* the worker before SUT invocation; on hit, the worker emits the cached `BenchScore` directly to the queue and skips both SUT and `rubric_runner` (asserted by a stub SUT that fails loudly if called when a cache hit is expected).
- [ ] `on_score` callback, if provided, is awaited once per case as soon as the score lands on the queue (before sort) — this is the JSONL streaming hook S4-02 uses.
- [ ] `mypy --strict`, `ruff format --check`, `ruff check` clean.
- [ ] Worker exceptions other than the six typed failure modes (S3-04) propagate; `KeyboardInterrupt` and `asyncio.CancelledError` are **not** swallowed (a test patches the worker to raise `KeyboardInterrupt` and asserts the run does not finalize).
- [ ] All red tests in §TDD plan exist, were committed at the red marker, and are now green.

## Implementation outline

1. Add `Runner.execute(plan, *, system_under_test, rubric_runner, concurrency=None, on_score=None) -> BenchRunReport`.
2. `concurrency = concurrency or min(os.cpu_count() or 1, 4)`; reject `<= 0`.
3. Create `queue: asyncio.Queue[BenchScore | _Sentinel] = asyncio.Queue()`, `sem = asyncio.Semaphore(concurrency)`, and `aggregator_task = asyncio.create_task(_aggregate(queue, plan, on_score))`.
4. Spawn one `asyncio.Task` per case: `async with sem: score = await _run_case(plan, case, system_under_test, rubric_runner)`; `await queue.put(score)`.
5. Worker body `_run_case`:
   1. `cached = cache.get(plan.cache_keys[case.case_id], cache_dir)`; on hit, return the cached `BenchScore` (no SUT, no rubric).
   2. On miss, `harness_output = await asyncio.wait_for(system_under_test(case), timeout=plan.timeout_per_case_seconds)` (S3-04 wraps the typed failure paths; this story keeps the `try/except` placeholder narrow).
   3. `score = await rubric_runner(case, harness_output)` (S3-03 injects the subprocess implementation; this story's tests inject an in-process stub).
   4. `cache.put(plan.cache_keys[case.case_id], score, cache_dir)`.
   5. Return `score`.
6. `await asyncio.gather(*tasks)`; `await queue.put(_SENTINEL)`; `await aggregator_task`; return the aggregator's `BenchRunReport`.
7. Aggregator body `_aggregate`:
   - Pull from queue; on `_SENTINEL`, finalize.
   - Update a `WelfordAccumulator` (`update(score) → mean / variance`).
   - Buffer `(case_id, BenchScore)` pairs in a list.
   - On finalize: sort by `case_id`, build the `BenchRunReport` with `complete=True`, `isolation_class="subprocess"`, `lower_bound_95=0.0` placeholder.
   - Compute `block_severity_failure_modes` as the deduplicated set of `fm.code for fm in score.failure_modes if fm.severity == "block"`.
8. Extract `WelfordAccumulator` to a sibling helper module (or private class) — must have its own unit tests in `tests/unit/test_welford.py`.
9. Bind `structlog` context inside the worker: `log.bind(case_id=case.case_id, run_id=plan.run_id)`.

## TDD plan — red / green / refactor

### Red — write failing tests first

Test file: `tests/unit/test_runner_execute.py`

```python
import asyncio
import json
import pytest
from hypothesis import given, strategies as st, settings
from codegenie.eval.models import BenchScore, FailureMode
from codegenie.eval.runner import Runner
from tests.helpers.bench import make_stub_plan
from tests.helpers.suts import JitteredStubSUT, FailingStubSUT
from tests.helpers.rubrics import in_process_stub_rubric


@pytest.mark.asyncio
async def test_per_case_ordered_by_case_id_regardless_of_completion():
    """Determinism invariant: completion order varies; report order does not."""
    plan = make_stub_plan(case_ids=["c", "a", "b"])
    # Stub SUT sleeps longest for case "a", shortest for "c" → completion is c, b, a.
    sut = JitteredStubSUT({"a": 0.03, "b": 0.02, "c": 0.01})

    report = await Runner().execute(
        plan, system_under_test=sut, rubric_runner=in_process_stub_rubric,
    )

    assert [cid for cid, _ in report.per_case] == ["a", "b", "c"]
    assert report.complete is True
    assert report.isolation_class == "subprocess"


@pytest.mark.asyncio
async def test_welford_mean_exact_on_known_inputs():
    plan = make_stub_plan(scores={"a": 0.2, "b": 0.5, "c": 0.8})
    report = await Runner().execute(
        plan, system_under_test=JitteredStubSUT.zero(),
        rubric_runner=in_process_stub_rubric,
    )
    assert abs(report.mean_score - 0.5) < 1e-12
    assert abs(report.score_stddev - 0.3) < 1e-12  # population stddev


@given(jitter_ms=st.lists(st.integers(min_value=0, max_value=20), min_size=3, max_size=3))
@settings(max_examples=20, deadline=None)
def test_report_byte_identical_across_completion_orderings(jitter_ms):
    plan = make_stub_plan(case_ids=["a", "b", "c"], scores={"a": 0.7, "b": 0.4, "c": 0.9})
    sut = JitteredStubSUT(dict(zip(["a","b","c"], (j/1000 for j in jitter_ms))))
    report = asyncio.run(Runner().execute(
        plan, system_under_test=sut, rubric_runner=in_process_stub_rubric,
    ))
    canonical = json.dumps([(cid, s.model_dump()) for cid, s in report.per_case], sort_keys=True)
    # Compare to a baseline run with zero jitter
    baseline_sut = JitteredStubSUT.zero()
    baseline = asyncio.run(Runner().execute(
        plan, system_under_test=baseline_sut, rubric_runner=in_process_stub_rubric,
    ))
    baseline_canonical = json.dumps([(cid, s.model_dump()) for cid, s in baseline.per_case], sort_keys=True)
    assert canonical == baseline_canonical


@pytest.mark.asyncio
async def test_cache_hit_skips_sut_and_rubric(tmp_path):
    plan = make_stub_plan(case_ids=["a"], cache_dir=tmp_path / "cache")
    # Pre-seed the cache with a known score.
    from codegenie.eval.cache import put as cache_put
    pre = BenchScore(passed=True, score=0.99, breakdown={}, failure_modes=(), cost_usd=0.0, wall_clock_ms=1)
    cache_put(plan.cache_keys["a"], pre, plan.cache_dir)

    sut = FailingStubSUT()  # fails loudly if called
    report = await Runner().execute(
        plan, system_under_test=sut, rubric_runner=in_process_stub_rubric,
    )
    assert report.per_case[0][1].score == 0.99
    assert sut.call_count == 0


@pytest.mark.asyncio
async def test_concurrency_default_caps_at_four(monkeypatch):
    monkeypatch.setattr("os.cpu_count", lambda: 16)
    plan = make_stub_plan(case_ids=[f"c{i}" for i in range(8)])
    sut = JitteredStubSUT.with_observer()
    report = await Runner().execute(
        plan, system_under_test=sut, rubric_runner=in_process_stub_rubric,
    )
    assert sut.observer.max_inflight == 4


@pytest.mark.asyncio
async def test_keyboard_interrupt_propagates_not_swallowed():
    """CancelledError and KeyboardInterrupt must not be coerced into FailureMode."""
    plan = make_stub_plan(case_ids=["a"])
    async def boom(case):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        await Runner().execute(plan, system_under_test=boom, rubric_runner=in_process_stub_rubric)


@pytest.mark.asyncio
async def test_only_one_aggregator_task_created():
    """Multiple aggregators race Welford state. Static-ish guard."""
    plan = make_stub_plan(case_ids=["a", "b"])
    sut = JitteredStubSUT.zero()
    before = {t for t in asyncio.all_tasks() if not t.done()}
    await Runner().execute(plan, system_under_test=sut, rubric_runner=in_process_stub_rubric)
    after = {t for t in asyncio.all_tasks() if not t.done()}
    assert (after - before) == set()  # no leaked tasks
```

Run all seven; confirm import/attribute failures. Commit as the red marker.

### Green — make them pass

`asyncio.Semaphore`, `asyncio.Queue`, one aggregator task, Welford in-place. Stub the rubric in-process via the `rubric_runner` parameter (S3-03 swaps in the real subprocess call). Cache probe inside the worker via `cache.get` (S2-03 already exists). `lower_bound_95 = 0.0` placeholder.

### Refactor — clean up

- Pull aggregator into `_aggregate(queue, plan, on_score) -> BenchRunReport`; add `WelfordAccumulator` with `update(x) / mean / variance` and `tests/unit/test_welford.py`.
- Structured logging at worker start/end with `case_id` bound; document the determinism invariant in the docstring; explicit type alias `OnScoreCallback = Callable[[str, BenchScore], Awaitable[None]] | None`.
- Pull the worker into `_run_case(plan, case, system_under_test, rubric_runner) -> BenchScore` so S3-04 has a clean seam for typed failure mapping.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/runner.py` | Add `Runner.execute` + `_aggregate` + `_run_case` |
| `src/codegenie/eval/_welford.py` | New helper module: `WelfordAccumulator` |
| `tests/unit/test_runner_execute.py` | New: stub-bench happy path, ordering invariant, Welford correctness, cache-skip, concurrency cap |
| `tests/unit/test_welford.py` | New: Welford correctness over hand-computed sequences |
| `tests/helpers/suts.py` | New: `JitteredStubSUT`, `FailingStubSUT` |
| `tests/helpers/rubrics.py` | New: `in_process_stub_rubric` callable |

## Out of scope

- Real subprocess rubric — S3-03 (this story uses an injected in-process stub).
- The six typed failure-mode mappings (`sut.exception`, `sut.timeout`, `rubric.*`) — S3-04.
- BCa bootstrap on `lower_bound_95` — S3-05 (set to `0.0` placeholder here).
- Cost-cap cancellation and partial reports — S3-06.
- Audit chain append — S3-06 (this story's `Runner.execute` produces the `BenchRunReport` value; the audit write is the final step of `run_eval`, which composes plan + execute + bootstrap + cost-cap + audit).

## Notes for the implementer

- **Don't conflate "concurrency floor" with "concurrency override."** The default `min(cpu_count(), 4)` is documented in OQ #1 — leave a `# TODO: revisit if portfolio scale forces higher (OQ #1)` comment, don't expand it now.
- Welford is preferred over `statistics.stdev` because the aggregator processes scores as they stream in — two-pass would force buffering and lose the streaming property the JSONL CLI mode (S4-02) needs.
- The aggregator **must** be a single task. Multiple aggregator tasks lose the determinism property because their internal accumulator state races. The "no leaked tasks" test is the structural guard.
- The `_SENTINEL` pattern is intentional. Don't reach for `asyncio.Queue.join()` here — the sentinel makes "all workers done" an explicit signal the aggregator can branch on.
- Resist threading the rubric subprocess call into the worker now. S3-03 owns that contract; this story injects `rubric_runner` so S3-03 can substitute the subprocess implementation without re-shaping the worker.
- The cache probe in the worker is **after** `async with sem:` — it's cheap (~1 ms) but it still occupies the semaphore. This is fine; alternative orderings (probe before semaphore acquire) require careful thought about cancellation safety. Defer until OQ #1 surfaces.
- `lower_bound_95=0.0` is a deliberate placeholder; S3-05 fills it. A test in S3-05 will assert the real bootstrap replaces the placeholder; do **not** raise an exception here for "not implemented" — that would block S3-05's TDD.
- `CancelledError` from `asyncio.CancelledError` (cost-cap path, S3-06) is **not** the same as `KeyboardInterrupt`. S3-06 will wrap the cost-cap cancellation; this story must propagate `KeyboardInterrupt` cleanly so users can ctrl-C a stuck run.
