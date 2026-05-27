# Story S3-02 — Asyncio fan-out + bounded semaphore + Welford aggregator

**Step:** Step 3 — Implement the runner: asyncio fan-out, subprocess rubric, aggregator with BCa bootstrap
**Status:** Ready (HARDENED 2026-05-27)
**Effort:** M
**Depends on:** S3-01 (plan phase HARDENED — `RunPlan` shape locked), S2-03 (content-addressed cache HARDENED), S1-02 (`BenchRunReport` shape HARDENED), S2-04 (`audit.write_run_record` / `GENESIS_PREV_HASH` HARDENED)
**ADRs honored:** ADR-0001 (subprocess invocation is per-worker — `RubricRunner` Protocol seam), ADR-0002 (deterministic per-case order at report time; `lower_bound_95=0.0` is a placeholder filled by S3-05), ADR-0010 (`isolation_class="subprocess"` on emitted report — unconditional)

## Validation notes

Hardened 2026-05-27 by the `phase-story-validator` skill. 28 critic findings (8 blocks, 16 hardens, 4 nits) applied. Highlights:

- **F-CON-2 / F-COV-2 (block).** `plan.timeout_per_case_seconds` and `cache_dir` references replaced with explicit `Runner.execute(...)` kwargs (`cache_dir: Path`, `timeout_per_case_seconds: float`). HARDENED S3-01 `RunPlan` is not silently mutated.
- **F-CON-3 / F-COV-1 (block).** `BenchRunReport` field-population sources enumerated explicitly: plan-bound fields (`run_id`, `task_class`, `sut_digest`, `rubric_digest`, `cassette_corpus_digest`, `harness_version`, `prev_hash`) copied verbatim from `plan`; aggregated fields (`passed_count`, `total_cost_usd`, `block_severity_failure_modes`, `started_at`, `ended_at`) computed in `_aggregate`. `chain_head=""` (empty-string sentinel) is the S3-06 hand-off.
- **F-CON-6 (block).** `Runner.execute` never writes to the audit chain — that's S3-06's `run_eval` composition. AC-13 makes this a fence-tested invariant.
- **F-COV-3 (block).** Try/finally around the fan-out: `_SENTINEL` is always enqueued even when a worker raises, so the aggregator never hangs.
- **F-COV-4 / F-TQ-10 (block).** `on_score` callback has a red test now (`test_on_score_called_once_per_case_in_completion_order_before_sort`) — both observation order AND multiset coverage.
- **F-COV-9 / F-TQ-7 (block).** `asyncio.CancelledError` has a sibling red test alongside `KeyboardInterrupt`. Both must propagate cleanly so S3-06's cost-cap path works.
- **F-COV-11 / F-TQ-8 (block).** Aggregator-task-count test rewritten to count *creation* via `asyncio.create_task` spy (looking for `name="codegenie-eval-aggregator"`), not "no leaked tasks."
- **F-COV-5 / F-TQ-4.** Welford stddev pinned as **sample (n−1)** with corrected comment + introspection test that matches `statistics.stdev`'s n−1 convention. The `[0.2, 0.5, 0.8] → stddev=0.3` fixture distinguishes sample from population (population ≈ 0.2449).
- **F-COV-6.** Empty-bench path AC: `plan.cases == ()` returns a `BenchRunReport` with empty `per_case`, zero aggregates, no `on_score` invocations.
- **F-COV-7.** `os.cpu_count() returning None` regression test pinned: floor is 1, never 0.
- **F-COV-8.** Concurrency boundary tests: `concurrency=1` (sequential — must not deadlock), `concurrency >> len(cases)` (bounded by case count), `concurrency=0` (`ValueError`).
- **F-COV-10 / F-TQ-1.** Determinism property test compares two *independent* jittered runs to each other (not just to a fixed baseline), with non-alphabetical case_ids.
- **F-COV-12.** `cache.put` `OSError` log-and-continue policy (arch §Edge cases #16 intent) — score still emitted to queue.
- **F-TQ-2 / F-TQ-13.** `per_case` tuple-not-list type pinned in every test that produces a report; `isolation_class == "subprocess"` pinned in every report-producing test.
- **F-TQ-5.** Cache-hit test asserts `rubric.call_count == 0` (not just SUT) and `report.per_case[0][1] is pre` (identity).
- **F-TQ-6.** Concurrency cap test uses a gated SUT (`asyncio.Event` blocking until all cases enter) so `max_inflight` reflects the actual semaphore bound. Positive tests at `concurrency=2`, `concurrency=8` (override).
- **F-TQ-9.** `WelfordAccumulator` gets its own red tests (`tests/unit/test_welford.py`) — single-value (n=1 → stddev=0.0), empty (zero-state contract), large-offset numerical-stability fixture, order-invariance Hypothesis property.
- **F-TQ-11.** Hypothesis multi-invariant property pins five accounting laws in one test.
- **F-TQ-12.** Two metamorphic relations: concurrency-invariance (same plan, different `concurrency` → byte-identical), slowness-invariance (same plan, slow SUT → byte-identical).
- **F-DP-1.** `RubricRunner: Protocol` introduced now (final-design.md lines 158-168 already prescribed it). S3-03 substitutes `SubprocessRubricRunner` by addition.
- **F-DP-3.** `on_score` entry-time validation: `not asyncio.iscoroutinefunction(on_score)` raises `TypeError` at `execute()` entry (fail-loud per CLAUDE.md Rule 12).
- **F-DP-4.** `_SENTINEL` is a `_Sentinel` class instance, not `None` or a string — tagged-union extension by addition (S3-06 may widen to `BenchScore | _Sentinel | _Aborted`).
- **F-DP-6.** `_run_case` and `_aggregate` extraction is now an AC (not just refactor notes) — they are the **named seams** for S3-04 (typed failure mapping) and S3-06 (cost cap).
- **F-DP-2 / F-DP-5 / F-DP-7 / F-DP-8 / F-DP-9.** Deferred design opportunities surfaced as Notes-for-implementer with explicit triggers.

Full audit trail: `_validation/S3-02-asyncio-fan-out-and-aggregator.md`.

## Context

Given the `RunPlan` from S3-01, this story executes the per-case work. Each worker probes the cache, then on a miss awaits the SUT (Phase 6's `build_vuln_loop`, injected as a callable), then invokes the rubric via the new `RubricRunner` Protocol (S3-03 wires the subprocess implementation; this story injects an **in-process stub rubric** so the fan-out shape is independently testable). A single aggregator `asyncio.Task` consumes a queue, rolling Welford mean/stddev, and at report time orders entries deterministically by `case_id`.

The architectural invariant (arch §Determinism row "runner scheduling") is: **completion order is non-deterministic; report order is not.** Two runs of the same plan with random jitter in SUT completion times must produce byte-identical `per_case` tuples when serialized. This is what makes the audit chain reproducible.

`Runner.execute(...)` is **value-producing only** — it never appends to the audit chain (S3-06's `run_eval` composes plan + execute + bootstrap + audit-write; this story owns step 4 of that composition).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Process view` — the asyncio sequence diagram (per-case worker → queue → aggregator → audit).
  - `../phase-arch-design.md §Determinism vs probabilism` row "runner scheduling" — non-deterministic completion order; deterministic report order via `case_id` sort at emit time.
  - `../phase-arch-design.md §Components → runner.py` — six-phase pipeline; this story owns phases 2 (cache probe), 3 (execute), 4 (aggregate).
  - `../phase-arch-design.md §Concurrency` paragraph — bounded by `asyncio.Semaphore(N=min(os.cpu_count(), 4))`, overridable via `--concurrency`. **Note:** `final-design.md §G12`'s `concurrency: int = 1` is superseded by the arch (per phase-architect skill precedence). The story honors the arch.
  - `../phase-arch-design.md §Edge cases #14, #16, #17` — SUT exception, corrupt cache treated as miss, concurrent run conflict.
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md` — the rubric runs across a process boundary per worker; this story leaves the seam open via an injected `RubricRunner` Protocol (S3-03 substitutes `SubprocessRubricRunner`).
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md` — `lower_bound_95=0.0` is a placeholder filled by S3-05; the placeholder is benign because S3-02's report is never written to the audit chain directly (AC-13).
  - `../ADRs/0010-isolation-class-annotation-on-bench-run-report.md` — `BenchRunReport.isolation_class = "subprocess"` is set unconditionally by this story; the Phase 16 microVM flip is out of scope.
- **Sibling stories (HARDENED — the contracts THIS story consumes):**
  - `S1-02-wire-models-frozen-extra-forbid.md` — `BenchRunReport` field list (AC-1, AC-6a, AC-11 — `per_case: tuple[tuple[str, BenchScore], ...]`).
  - `S2-03-content-addressed-cache.md` — `cache.get(cache_key, cache_dir)`, `cache.put(cache_key, score, cache_dir)`.
  - `S2-04-audit-chain-extension.md` — `audit.write_run_record` (NOT called by this story; S3-06's job), `GENESIS_PREV_HASH`.
  - `S3-01-runner-plan-phase.md` (HARDENED) — `RunPlan` shape: `task_class, cases, sut_digest, rubric_digest, cassette_corpus_digest, harness_version, run_id, prev_chain_head, cache_keys, isolation_class`. **No `cache_dir`, no `timeout_per_case_seconds` on plan** — those are `Runner.execute` kwargs.
- **Source design:** `../final-design.md §Components → runner.py` ("async def; the harness is async-shaped from Phase 6.5 because Phase 6's SUT is async (LangGraph ainvoke)"); `../final-design.md §rubric_runner` lines 158-168 — `RubricRunner` Protocol shape.
- **Open question:** OQ #1 — `min(cpu_count(), 4)` floor; document the override flag in the docstring; **do not** raise the floor in this story.

## Goal

Implement `Runner.execute(plan, *, system_under_test, rubric_runner, cache_dir, timeout_per_case_seconds, concurrency=None, on_score=None) -> BenchRunReport` that fans out per-case workers under `asyncio.Semaphore(min(os.cpu_count() or 1, 4))` (overridable), aggregates via Welford with a **single** aggregator task, and produces a `BenchRunReport` with `per_case` sorted by `case_id`, `complete=True`, `isolation_class="subprocess"`, `lower_bound_95=0.0` (S3-05 placeholder), `chain_head=""` (S3-06 sentinel), and `prev_hash=plan.prev_chain_head`. The function **never** writes to the audit chain.

## Acceptance criteria

### Public surface + signature

- [ ] **AC-1.** `Runner.execute(plan, *, system_under_test, rubric_runner, cache_dir, timeout_per_case_seconds, concurrency=None, on_score=None) -> BenchRunReport` is the sole new public symbol added in this story. `cache_dir: Path` and `timeout_per_case_seconds: float` are kwargs on `execute(...)` — NOT fields on `RunPlan` (HARDENED S3-01 contract is unchanged).

- [ ] **AC-2.** Default concurrency: `concurrency = concurrency or min(os.cpu_count() or 1, 4)`. Explicit `concurrency=N>0` overrides. `concurrency <= 0` raises `ValueError(f"concurrency must be >= 1, got {concurrency}")`. `os.cpu_count() returning None` floors at 1 (regression-tested — otherwise the semaphore deadlocks).

- [ ] **AC-2a.** `on_score` entry-time validation (fail-loud, Rule 12): when `on_score is not None` and `not asyncio.iscoroutinefunction(on_score)`, `execute(...)` raises `TypeError("on_score must be an async callable returning Awaitable[None]; got <type>")` at entry — before any worker is spawned. A wrong-shape `on_score` is discovered at call zero, not after partial work.

### RubricRunner Protocol seam (F-DP-1)

- [ ] **AC-3.** A new `RubricRunner` Protocol lands in `src/codegenie/eval/rubric_runner.py` matching `final-design.md` lines 158-168:
  ```python
  @runtime_checkable
  class RubricRunner(Protocol):
      async def run(
          self,
          rubric_path: Path,
          case: BenchCase,
          harness_output: Mapping[str, Any],
          *,
          wall_clock_cap_seconds: float,
      ) -> BenchScore: ...
  ```
  `rubric_path` is `plan.task_class.bench_path / "rubric.py"`. `wall_clock_cap_seconds` is `timeout_per_case_seconds` (the same kwarg threaded through). The worker invokes `await rubric_runner.run(rubric_path, case, harness_output, wall_clock_cap_seconds=timeout_per_case_seconds)`. **S3-03 will implement `SubprocessRubricRunner` (a concrete class) without re-shaping this signature.** Test helper `tests/helpers/rubrics.py:InProcessStubRubric` implements the Protocol (class, not bare callable).

### Aggregator topology

- [ ] **AC-4.** The aggregator is a **single** `asyncio.Task` named `"codegenie-eval-aggregator"` consuming an `asyncio.Queue[BenchScore | _Sentinel]`. A red test (`test_exactly_one_aggregator_task_created`) spies on `asyncio.create_task` and asserts: `sum(1 for call in spy.call_args_list if call.kwargs.get("name") == "codegenie-eval-aggregator") == 1`. Multiple aggregator tasks would race the Welford state.

- [ ] **AC-4a.** `_SENTINEL` is an instance of a private `_Sentinel` class (NOT `None`, NOT a string, NOT `object()`): `class _Sentinel: pass` and `_SENTINEL: Final[_Sentinel] = _Sentinel()`. The aggregator branches via `isinstance(item, _Sentinel)`. Pinning the class shape lets S3-06 widen additively to `BenchScore | _Sentinel | _Aborted` without re-shaping the queue type.

- [ ] **AC-5.** **No-hang invariant.** The fan-out is wrapped in `try / finally`: even if a worker raises an unexpected exception (i.e., not a `KeyboardInterrupt` / `CancelledError` / S3-04-mapped FailureMode), `_SENTINEL` is enqueued and the aggregator task is awaited before the exception propagates. Red test: patch one worker to raise `RuntimeError("boom")`; assert (a) `pytest.raises(RuntimeError)` fires within bounded time (use `pytest.timeout(10)` or `asyncio.wait_for(..., 5.0)`); (b) the aggregator task is `.done()` after the raise; (c) no leaked tasks.

### Welford correctness — sample (n−1) stddev pinned

- [ ] **AC-6.** `WelfordAccumulator` (in `src/codegenie/eval/_welford.py`) computes **sample standard deviation** (Bessel's n−1 correction), matching `statistics.stdev`'s convention. For inputs `[0.2, 0.5, 0.8]`: `mean=0.5` exactly, `stddev=0.3` exactly (within `1e-12`). The choice of n−1 is documented in the module docstring AND re-asserted by an introspection test that calls `accumulator.update(0.5)` once and asserts `accumulator.stddev == 0.0` (matches `statistics.stdev` returning 0 for n=1; n−1 with n=1 → 0/0 must be handled, not raise). For n=0 (empty), `mean` and `stddev` both return `0.0` (NaN-avoidance — pinned by AC-7 below).

- [ ] **AC-6a.** **Numerical-stability fixture** (Welford's load-bearing property): inputs `[1e9+4, 1e9+7, 1e9+13, 1e9+16]` produce `stddev` correct to `1e-9` (mean = 1e9 + 10; sample stddev = √30 ≈ 5.4772256...). A wrong impl that buffers and computes `sum((x-mean)**2)` in `float64` loses precision against `Welford`. Tested directly in `tests/unit/test_welford.py`.

- [ ] **AC-6b.** **Welford order-invariance property** (`tests/unit/test_welford.py`). Hypothesis-draws a `list[float]` of length 2-32 in `[0, 1]`; asserts that `update(a); update(b); update(c); ...` produces the same `mean` and `stddev` (within `1e-9`) as any permutation of the same sequence.

### `BenchRunReport` field-population sources (F-CON-3)

- [ ] **AC-7.** The returned `BenchRunReport` populates every required field of HARDENED S1-02. **Plan-bound fields** (copied verbatim from `plan`):
  - `run_id = plan.run_id`
  - `task_class = plan.task_class.name` (the slug `str`, not the `TaskClass` dataclass)
  - `sut_digest = plan.sut_digest`
  - `rubric_digest = plan.rubric_digest`
  - `cassette_corpus_digest = plan.cassette_corpus_digest`
  - `harness_version = plan.harness_version`
  - `prev_hash = plan.prev_chain_head`
  - `isolation_class = "subprocess"` (per ADR-0010; from `plan.isolation_class`)

  **Aggregator-computed fields:**
  - `per_case: tuple[tuple[str, BenchScore], ...]` — sorted by `case_id` (lexicographic); type-pinned as `tuple`, not `list` (S1-02 AC-11).
  - `mean_score = WelfordAccumulator.mean` (or `0.0` when `len(per_case) == 0`).
  - `score_stddev = WelfordAccumulator.stddev` (sample n−1, or `0.0` when n ≤ 1).
  - `lower_bound_95 = 0.0` (S3-05 placeholder).
  - `passed_count = sum(1 for _cid, s in per_case if s.passed)`.
  - `total_cost_usd = sum(s.cost_usd for _cid, s in per_case)`.
  - `block_severity_failure_modes` = sorted, deduplicated `tuple[str, ...]` of `fm.code for fm in score.failure_modes if fm.severity == "block"` across all cases. Sort order is `tuple(sorted(set(...)))` for byte-stability.
  - `complete = True` (S3-06's cost-cap path will produce `complete=False`; that's not this story).
  - `started_at`, `ended_at`: UTC `datetime` captured at `execute()` entry / aggregator finalize (`datetime.now(timezone.utc)`).

- [ ] **AC-8.** **Empty-bench path.** When `plan.cases == ()`, `execute(...)` returns within 1 s with: `per_case=()`, `mean_score=0.0`, `score_stddev=0.0`, `passed_count=0`, `total_cost_usd=0.0`, `block_severity_failure_modes=()`, `complete=True`, `isolation_class="subprocess"`. The aggregator task is created, receives `_SENTINEL` immediately, finalizes. `on_score` (if provided) is not invoked.

### Determinism

- [ ] **AC-9.** On a 3-case stub bench with a deterministic stub SUT and an `InProcessStubRubric`, `Runner.execute(...)` returns a `BenchRunReport` whose `per_case` is sorted lexicographically by `case_id`. **The `per_case` field is a `tuple`** (type-pinned via `assert isinstance(report.per_case, tuple)`), and each entry is `tuple[str, BenchScore]`.

- [ ] **AC-9a.** **Cross-run determinism property (strengthened).** Hypothesis draws two independent jitter vectors `jitter_a, jitter_b: list[int]` of length 3-16 with values in `[0, 50]`. Both jitter vectors apply to the same plan (case_ids drawn from a non-alphabetical pool, e.g., `["zeta", "alpha", "mike", "delta"][:n]`). Assert that `run(jitter_a).per_case_canonical_json == run(jitter_b).per_case_canonical_json` (run-to-run, not run-to-baseline). Additionally assert against a zero-jitter baseline. Catches sort-key bugs that have tie-break dependence on completion order.

- [ ] **AC-9b.** **Metamorphic relation: concurrency-invariance.** Same plan, `concurrency=1` vs `concurrency=4` → byte-identical `per_case` canonical JSON. Catches an aggregator that uses thread-local Welford state, or that has a race only at `concurrency > 1`.

- [ ] **AC-9c.** **Metamorphic relation: slowness-invariance.** Same plan, fast stub SUT vs `JitteredStubSUT({c: 0.05 for c in case_ids})` → byte-identical report. Catches an impl that timestamps `wall_clock_ms` into the sort key by accident.

### Cache hit / miss discipline

- [ ] **AC-10.** Cache probe happens **inside** the worker before SUT invocation, under the semaphore (the probe is cheap, ~1 ms; the alternative ordering requires careful cancellation reasoning — see Notes). On hit: the worker emits the cached `BenchScore` directly to the queue and **skips both** SUT (`sut.call_count == 0`) **and** `rubric_runner` (`rubric.call_count == 0`). Identity assertion: `report.per_case[0][1] is cached_score` (not just `.score == 0.99`).

- [ ] **AC-10a.** **Cache `put` failure (arch §Edge cases #16 intent).** An `OSError` raised by `cache.put` is logged at `WARNING` (`runner.cache_put_failed` with `case_id` bound) and the score is still placed on the queue. The case will re-run when the cache is healthy. Test: patch `cache.put` to raise `OSError`; assert (a) `execute()` completes successfully, (b) `per_case` has the score, (c) `caplog` contains the warning.

### `on_score` streaming hook

- [ ] **AC-11.** When `on_score` is provided, it is `await`ed once per case as soon as the score lands on the queue (**before** the final sort). The callback receives `(case_id: str, score: BenchScore)`. **Observation order is completion order**, NOT `case_id` order — this is intentional (S4-02's JSONL streaming UX). Red test: `JitteredStubSUT({"a": 0.03, "b": 0.02, "c": 0.01})`; assert `observed == ["c", "b", "a"]` while `report.per_case` ids are `["a", "b", "c"]`.

- [ ] **AC-11a.** Multiset coverage: `Counter(case_id for case_id, _ in observed) == Counter(case_id for case_id, _ in report.per_case)` — every case streamed exactly once.

### Exception discipline

- [ ] **AC-12.** Both `KeyboardInterrupt` AND `asyncio.CancelledError` raised from a worker (or from `rubric_runner`) propagate out of `execute(...)` without being coerced into a `FailureMode`. Two separate red tests cover the two exception types (SUT raises each). S3-06's cost-cap path uses `CancelledError`; S3-04's typed mappings handle non-system exceptions.

### Runner does not write to audit chain (F-CON-6)

- [ ] **AC-13.** `Runner.execute(...)` does **not** call `audit.write_run_record`. Asserted by `monkeypatch.setattr("codegenie.eval.audit.write_run_record", lambda *a, **kw: pytest.fail("execute() must not write to audit chain — that's S3-06"))`. The returned `BenchRunReport` carries `chain_head=""` (empty-string sentinel; S3-06's `audit.write_run_record` populates it via `model_copy(update={"chain_head": ...})`) and `prev_hash=plan.prev_chain_head`.

### Property-based accounting laws

- [ ] **AC-14.** **Multi-invariant accounting property.** Hypothesis draws `case_ids: list[str]` (3-16, unique) and `scores: list[float]` in `[0, 1]`. Run `execute(...)` and assert all five:
  1. `len(report.per_case) == len(plan.cases)` (no cases dropped).
  2. `set(cid for cid, _ in report.per_case) == set(c.case_id for c in plan.cases)` (no transposition).
  3. `report.passed_count <= len(report.per_case)`.
  4. `report.total_cost_usd >= 0.0`.
  5. With `on_score` recording: `Counter(seen_case_ids) == Counter(cid for cid, _ in report.per_case)`.

### Universal report-shape assertions (F-TQ-13)

- [ ] **AC-15.** Every test that produces a `BenchRunReport` asserts `isinstance(report.per_case, tuple)` AND `report.isolation_class == "subprocess"`. Pinning by repetition prevents regression where an impl conditionalizes `isolation_class` (e.g., based on whether the rubric is the real subprocess) or returns `list` instead of `tuple`.

### Tooling

- [ ] **AC-16.** `mypy --strict`, `ruff format --check`, `ruff check` clean on touched files.
- [ ] **AC-17.** All red tests in §TDD plan exist, were committed at the red marker, and are now green.

## Implementation outline

1. **Define `RubricRunner` Protocol** in `src/codegenie/eval/rubric_runner.py` per AC-3 (matches `final-design.md` lines 158-168). Add `@runtime_checkable`. Add `"RubricRunner"` to `codegenie.eval.__all__`.

2. **Define `WelfordAccumulator`** in `src/codegenie/eval/_welford.py` (private module — underscore prefix). Module docstring states "sample (n−1) standard deviation, matching `statistics.stdev`'s convention." Behaviors:
   - `update(x: float) -> None`: increments n, updates `_mean` and `_M2` via the canonical Welford recurrence.
   - `mean` property: returns `0.0` if n==0; else `_mean`.
   - `stddev` property: returns `0.0` if n<=1; else `sqrt(_M2 / (n-1))`.
   - `n` property: integer count of `update` calls.

3. **Sentinel + queue setup** in `src/codegenie/eval/runner.py`:
   ```python
   class _Sentinel: pass
   _SENTINEL: Final[_Sentinel] = _Sentinel()
   ```

4. **`Runner.execute(...)`** with this body shape:
   ```python
   async def execute(
       self,
       plan: RunPlan,
       *,
       system_under_test: Callable[[BenchCase], Awaitable[Mapping[str, Any]]],
       rubric_runner: RubricRunner,
       cache_dir: Path,
       timeout_per_case_seconds: float,
       concurrency: int | None = None,
       on_score: OnScoreCallback = None,
   ) -> BenchRunReport:
       # AC-2: defaults + validation
       if concurrency is not None and concurrency <= 0:
           raise ValueError(f"concurrency must be >= 1, got {concurrency}")
       concurrency = concurrency or min(os.cpu_count() or 1, 4)
       # AC-2a: fail-loud on_score validation
       if on_score is not None and not asyncio.iscoroutinefunction(on_score):
           raise TypeError(
               f"on_score must be an async callable returning Awaitable[None]; got {type(on_score).__name__}"
           )
       started_at = datetime.now(timezone.utc)
       queue: asyncio.Queue[BenchScore | _Sentinel] = asyncio.Queue()
       sem = asyncio.Semaphore(concurrency)
       aggregator_task = asyncio.create_task(
           _aggregate(queue, plan, on_score, started_at),
           name="codegenie-eval-aggregator",   # AC-4: counted by spy
       )
       worker_tasks: list[asyncio.Task[None]] = []
       try:
           for case in plan.cases:
               worker_tasks.append(asyncio.create_task(
                   _run_case(
                       case, plan, sem, queue,
                       system_under_test=system_under_test,
                       rubric_runner=rubric_runner,
                       cache_dir=cache_dir,
                       timeout_per_case_seconds=timeout_per_case_seconds,
                   ),
                   name=f"codegenie-eval-worker-{case.case_id}",
               ))
           await asyncio.gather(*worker_tasks)
       finally:
           # AC-5: no-hang invariant — _SENTINEL always enqueued
           await queue.put(_SENTINEL)
           await aggregator_task
       return aggregator_task.result()
   ```

5. **Worker body `_run_case`** (extracted module-level helper — the S3-04 typed-failure-mapping seam):
   ```python
   async def _run_case(
       case: BenchCase, plan: RunPlan, sem: asyncio.Semaphore,
       queue: "asyncio.Queue[BenchScore | _Sentinel]",
       *,
       system_under_test: Callable[..., Awaitable[Mapping[str, Any]]],
       rubric_runner: RubricRunner,
       cache_dir: Path,
       timeout_per_case_seconds: float,
   ) -> None:
       async with sem:
           log = structlog.get_logger().bind(case_id=case.case_id, run_id=plan.run_id)
           cached = cache.get(plan.cache_keys[case.case_id], cache_dir)
           if cached is not None:
               await queue.put(cached)  # AC-10: SUT + rubric skipped
               return
           harness_output = await asyncio.wait_for(
               system_under_test(case), timeout=timeout_per_case_seconds,
           )
           rubric_path = plan.task_class.bench_path / "rubric.py"
           score = await rubric_runner.run(
               rubric_path, case, harness_output,
               wall_clock_cap_seconds=timeout_per_case_seconds,
           )
           try:
               cache.put(plan.cache_keys[case.case_id], score, cache_dir)
           except OSError as exc:
               # AC-10a: arch §Edge cases #16 — log and continue
               log.warning("runner.cache_put_failed", error=str(exc))
           await queue.put(score)
   ```
   S3-04 will wrap the `await asyncio.wait_for(...)` and `await rubric_runner.run(...)` calls with typed-exception → `FailureMode` mapping. The seam exists today; the mapping lands later.

6. **Aggregator body `_aggregate`** (extracted module-level helper — the S3-06 cost-cap seam):
   ```python
   async def _aggregate(
       queue: "asyncio.Queue[BenchScore | _Sentinel]",
       plan: RunPlan,
       on_score: OnScoreCallback,
       started_at: datetime,
   ) -> BenchRunReport:
       welford = WelfordAccumulator()
       buf: list[tuple[str, BenchScore]] = []
       # Map score → case_id via plan.cache_keys reverse lookup? Simpler:
       # the worker enqueues (case_id, score) — refactor _run_case + queue type to
       # asyncio.Queue[tuple[str, BenchScore] | _Sentinel] so the aggregator
       # sees case_id directly. (Adjust AC-4 queue type accordingly; see Notes.)
       while True:
           item = await queue.get()
           if isinstance(item, _Sentinel):
               break
           case_id, score = item
           welford.update(score.score)
           buf.append((case_id, score))
           if on_score is not None:
               await on_score(case_id, score)   # AC-11: before sort, completion order
       per_case = tuple(sorted(buf, key=lambda p: p[0]))   # AC-9 / S1-02 AC-11
       block_codes = tuple(sorted({
           fm.code for _cid, s in per_case for fm in s.failure_modes
           if fm.severity == "block"
       }))
       return BenchRunReport(
           # plan-bound (AC-7)
           run_id=plan.run_id, task_class=plan.task_class.name,
           sut_digest=plan.sut_digest, rubric_digest=plan.rubric_digest,
           cassette_corpus_digest=plan.cassette_corpus_digest,
           harness_version=plan.harness_version,
           prev_hash=plan.prev_chain_head, chain_head="",   # AC-13
           isolation_class="subprocess",                     # ADR-0010
           # aggregated (AC-7)
           per_case=per_case,
           mean_score=welford.mean, score_stddev=welford.stddev,
           lower_bound_95=0.0,                               # ADR-0002 placeholder
           passed_count=sum(1 for _cid, s in per_case if s.passed),
           total_cost_usd=sum(s.cost_usd for _cid, s in per_case),
           block_severity_failure_modes=block_codes,
           started_at=started_at, ended_at=datetime.now(timezone.utc),
           complete=True,                                    # S3-06 may flip
       )
   ```

7. **Queue item shape** (note inside step 6): the worker enqueues `tuple[str, BenchScore] | _Sentinel` so the aggregator sees `case_id` directly. Update AC-4 and AC-4a's queue type to `asyncio.Queue[tuple[str, BenchScore] | _Sentinel]`; `isinstance(item, _Sentinel)` still discriminates.

8. **Import convention** (S3-01 F-TQ-3): `runner.py` imports MODULES (`from codegenie.eval import audit, cache, loader`), not symbols. Tests patch at `codegenie.eval.cache.put` and the patch takes effect at the runner's call site.

## TDD plan — red / green / refactor

### Red — write failing tests first

Helpers first:

**`tests/helpers/rubrics.py`:**
```python
from pathlib import Path
from typing import Mapping, Any
from codegenie.eval.models import BenchCase, BenchScore

class InProcessStubRubric:
    """Implements RubricRunner Protocol. Returns a deterministic BenchScore.
    Counts calls for cache-hit assertion (AC-10).
    """
    def __init__(self, fixed_score: float = 0.5) -> None:
        self.fixed_score = fixed_score
        self.call_count = 0

    async def run(
        self, rubric_path: Path, case: BenchCase,
        harness_output: Mapping[str, Any], *, wall_clock_cap_seconds: float,
    ) -> BenchScore:
        self.call_count += 1
        return BenchScore(
            passed=True, score=self.fixed_score, breakdown={},
            failure_modes=(), cost_usd=0.0, wall_clock_ms=1,
        )
```

**`tests/helpers/suts.py`:**
```python
import asyncio
from typing import Mapping, Any
from codegenie.eval.models import BenchCase

class JitteredStubSUT:
    """Async callable. Sleeps per-case-id, then returns a deterministic dict."""
    def __init__(self, sleeps: Mapping[str, float]) -> None:
        self.sleeps = dict(sleeps)
        self.call_count = 0
        self.observer = _MaxInflightObserver()

    @classmethod
    def zero(cls) -> "JitteredStubSUT":
        return cls({})

    @classmethod
    def with_observer(cls) -> "JitteredStubSUT":
        s = cls({})
        return s  # observer is always present; method-name is legacy

    async def __call__(self, case: BenchCase) -> Mapping[str, Any]:
        self.call_count += 1
        self.observer.enter()
        try:
            await asyncio.sleep(self.sleeps.get(case.case_id, 0.0))
            return {"case_id": case.case_id}
        finally:
            self.observer.exit()

class GatedJitteredStubSUT(JitteredStubSUT):
    """Like JitteredStubSUT but blocks all calls on an asyncio.Event until
    `n_expected` cases have entered. Used by AC-2 / F-TQ-6 to pin the
    semaphore bound: max_inflight reflects the bound, not stub timing.
    """
    def __init__(self, n_expected: int) -> None:
        super().__init__({})
        self._gate = asyncio.Event()
        self._entered = 0
        self._n = n_expected

    async def __call__(self, case: BenchCase) -> Mapping[str, Any]:
        self.observer.enter()
        self._entered += 1
        if self._entered >= self._n:
            self._gate.set()
        try:
            await self._gate.wait()
            return {"case_id": case.case_id}
        finally:
            self.observer.exit()

class FailingStubSUT:
    """Async callable that fails loudly if invoked — used for cache-hit
    assertions where SUT must NOT be called.
    """
    def __init__(self) -> None:
        self.call_count = 0
    async def __call__(self, case: BenchCase) -> Mapping[str, Any]:
        self.call_count += 1
        raise AssertionError(f"FailingStubSUT was called with {case.case_id}")

class _MaxInflightObserver:
    def __init__(self) -> None:
        self.inflight = 0
        self.max_inflight = 0
    def enter(self) -> None:
        self.inflight += 1
        self.max_inflight = max(self.max_inflight, self.inflight)
    def exit(self) -> None:
        self.inflight -= 1
```

**`tests/helpers/bench.py`** (extending S3-01's `stub_task_class_fixture`):
```python
def make_stub_plan(
    tmp_path: Path,
    *,
    case_ids: list[str] | None = None,
    scores: Mapping[str, float] | None = None,
) -> RunPlan:
    """Build a stub RunPlan by calling Runner().plan(...) on a stub_task_class_fixture.

    case_ids: overrides the default ["001-a","002-b","003-c"] by patching the
        bench fixture's case directories before plan(). scores is reserved for
        future stub-rubric injection — not used by plan() itself.
    """
    bench_root = stub_task_class_fixture(tmp_path, case_ids=case_ids or ["001-a","002-b","003-c"])
    return Runner().plan(
        task_class_name="stub-task-class", sut_digest_fn=lambda: "blake3:" + "a"*64,
        bench_root=bench_root, out_dir=tmp_path / ".codegenie" / "eval",
        run_started_iso="2026-05-27T00:00:00Z",
        cassette_root=_make_empty_cassette_root(tmp_path),
        harness_version="0.6.5", registry=TaskClassRegistry(),
    )
```
Note: `stub_task_class_fixture` widens by `case_ids` kwarg in this story (additive edit to the S3-01 helper).

**Test file: `tests/unit/test_runner_execute.py`** — at least these red tests (oracle-and-mutation discipline; each maps to an AC):

```python
import asyncio
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from hypothesis import given, strategies as st, settings

from codegenie.eval.models import BenchScore, BenchRunReport, FailureMode
from codegenie.eval.runner import Runner, _Sentinel, _SENTINEL
from codegenie.eval.rubric_runner import RubricRunner
from tests.helpers.bench import make_stub_plan
from tests.helpers.suts import (
    JitteredStubSUT, GatedJitteredStubSUT, FailingStubSUT,
)
from tests.helpers.rubrics import InProcessStubRubric


def _default_kwargs(tmp_path: Path) -> dict:
    return dict(
        rubric_runner=InProcessStubRubric(),
        cache_dir=tmp_path / "cache",
        timeout_per_case_seconds=30.0,
    )


# ---------- AC-1 / AC-2 / AC-2a — signature + validation -------------------

@pytest.mark.asyncio
async def test_execute_rejects_concurrency_zero(tmp_path):
    plan = make_stub_plan(tmp_path)
    with pytest.raises(ValueError, match="concurrency must be >= 1"):
        await Runner().execute(
            plan, system_under_test=JitteredStubSUT.zero(),
            concurrency=0, **_default_kwargs(tmp_path),
        )


@pytest.mark.asyncio
async def test_execute_concurrency_floor_when_cpu_count_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr("os.cpu_count", lambda: None)
    plan = make_stub_plan(tmp_path, case_ids=["a", "b"])
    # Just runs without deadlock — the regression is min(None, 4) → TypeError.
    report = await Runner().execute(
        plan, system_under_test=JitteredStubSUT.zero(), **_default_kwargs(tmp_path),
    )
    assert len(report.per_case) == 2


@pytest.mark.asyncio
async def test_execute_rejects_sync_on_score(tmp_path):
    plan = make_stub_plan(tmp_path)
    def sync_callback(case_id, score): return None
    with pytest.raises(TypeError, match="async callable"):
        await Runner().execute(
            plan, system_under_test=JitteredStubSUT.zero(),
            on_score=sync_callback, **_default_kwargs(tmp_path),
        )


# ---------- AC-9 / AC-9a / AC-9b / AC-9c — determinism --------------------

@pytest.mark.asyncio
async def test_per_case_ordered_by_case_id_regardless_of_completion(tmp_path):
    plan = make_stub_plan(tmp_path, case_ids=["c", "a", "b"])
    sut = JitteredStubSUT({"a": 0.03, "b": 0.02, "c": 0.01})
    report = await Runner().execute(plan, system_under_test=sut, **_default_kwargs(tmp_path))
    assert isinstance(report.per_case, tuple)                     # AC-15
    assert [cid for cid, _ in report.per_case] == ["a", "b", "c"]
    assert report.complete is True
    assert report.isolation_class == "subprocess"                 # AC-15


def _canonical(report: BenchRunReport) -> str:
    return json.dumps(
        [(cid, s.model_dump()) for cid, s in report.per_case],
        sort_keys=True, default=str,
    )


@given(
    jitter_a=st.lists(st.integers(min_value=0, max_value=50), min_size=3, max_size=8),
    jitter_b=st.lists(st.integers(min_value=0, max_value=50), min_size=3, max_size=8),
)
@settings(max_examples=15, deadline=None)
def test_two_independent_jitters_produce_identical_per_case(tmp_path_factory, jitter_a, jitter_b):
    n = min(len(jitter_a), len(jitter_b))
    case_ids = ["zeta", "alpha", "mike", "delta", "novel", "omega", "kilo", "yankee"][:n]
    p_a = make_stub_plan(tmp_path_factory.mktemp("a"), case_ids=case_ids)
    p_b = make_stub_plan(tmp_path_factory.mktemp("b"), case_ids=case_ids)
    sut_a = JitteredStubSUT(dict(zip(case_ids, (j/1000 for j in jitter_a[:n]))))
    sut_b = JitteredStubSUT(dict(zip(case_ids, (j/1000 for j in jitter_b[:n]))))
    r_a = asyncio.run(Runner().execute(p_a, system_under_test=sut_a, **_default_kwargs(tmp_path_factory.mktemp("ka"))))
    r_b = asyncio.run(Runner().execute(p_b, system_under_test=sut_b, **_default_kwargs(tmp_path_factory.mktemp("kb"))))
    assert _canonical(r_a) == _canonical(r_b)


@pytest.mark.asyncio
async def test_concurrency_invariance_metamorphic(tmp_path_factory):
    case_ids = ["zeta", "alpha", "mike"]
    p1 = make_stub_plan(tmp_path_factory.mktemp("a"), case_ids=case_ids)
    p2 = make_stub_plan(tmp_path_factory.mktemp("b"), case_ids=case_ids)
    sut = JitteredStubSUT({"alpha": 0.01, "mike": 0.005})
    r1 = await Runner().execute(p1, system_under_test=sut, concurrency=1, **_default_kwargs(tmp_path_factory.mktemp("k1")))
    r2 = await Runner().execute(p2, system_under_test=JitteredStubSUT({"alpha": 0.01, "mike": 0.005}), concurrency=4, **_default_kwargs(tmp_path_factory.mktemp("k2")))
    assert _canonical(r1) == _canonical(r2)


# ---------- AC-4 / AC-4a / AC-5 — aggregator topology + no-hang ----------

@pytest.mark.asyncio
async def test_exactly_one_aggregator_task_created(tmp_path, monkeypatch):
    created_names: list[str] = []
    real_create = asyncio.create_task
    def spy(coro, *, name=None):
        created_names.append(name or "")
        return real_create(coro, name=name)
    monkeypatch.setattr(asyncio, "create_task", spy)

    plan = make_stub_plan(tmp_path, case_ids=["a", "b"])
    await Runner().execute(plan, system_under_test=JitteredStubSUT.zero(), **_default_kwargs(tmp_path))
    assert sum(1 for n in created_names if n == "codegenie-eval-aggregator") == 1


@pytest.mark.asyncio
async def test_sentinel_is_class_instance_not_none():
    assert isinstance(_SENTINEL, _Sentinel)
    assert _SENTINEL is not None


@pytest.mark.asyncio
async def test_unexpected_worker_exception_does_not_wedge_aggregator(tmp_path):
    plan = make_stub_plan(tmp_path, case_ids=["a", "b", "c"])
    boomer_count = {"n": 0}
    async def sut(case):
        boomer_count["n"] += 1
        if case.case_id == "b":
            raise RuntimeError("boom")
        return {"case_id": case.case_id}
    with pytest.raises(RuntimeError, match="boom"):
        await asyncio.wait_for(
            Runner().execute(plan, system_under_test=sut, **_default_kwargs(tmp_path)),
            timeout=5.0,
        )
    # If we got here without timeout, the aggregator did not hang.


# ---------- AC-7 — BenchRunReport field population --------------------------

@pytest.mark.asyncio
async def test_report_plan_bound_fields_copied_verbatim(tmp_path):
    plan = make_stub_plan(tmp_path)
    report = await Runner().execute(plan, system_under_test=JitteredStubSUT.zero(), **_default_kwargs(tmp_path))
    assert report.run_id == plan.run_id
    assert report.task_class == plan.task_class.name
    assert report.sut_digest == plan.sut_digest
    assert report.rubric_digest == plan.rubric_digest
    assert report.cassette_corpus_digest == plan.cassette_corpus_digest
    assert report.harness_version == plan.harness_version
    assert report.prev_hash == plan.prev_chain_head
    assert report.chain_head == ""    # AC-13 — S3-06's slot


# ---------- AC-8 — empty bench ----------------------------------------------

@pytest.mark.asyncio
async def test_empty_plan_returns_empty_report(tmp_path):
    plan = make_stub_plan(tmp_path, case_ids=[])
    report = await asyncio.wait_for(
        Runner().execute(plan, system_under_test=FailingStubSUT(), **_default_kwargs(tmp_path)),
        timeout=1.0,
    )
    assert report.per_case == ()
    assert report.mean_score == 0.0
    assert report.score_stddev == 0.0
    assert report.passed_count == 0
    assert report.total_cost_usd == 0.0
    assert report.block_severity_failure_modes == ()
    assert report.complete is True


# ---------- AC-10 / AC-10a — cache hit/miss ---------------------------------

@pytest.mark.asyncio
async def test_cache_hit_skips_sut_and_rubric_identity_returned(tmp_path):
    plan = make_stub_plan(tmp_path, case_ids=["a"])
    pre = BenchScore(passed=True, score=0.99, breakdown={}, failure_modes=(),
                     cost_usd=0.0, wall_clock_ms=1)
    from codegenie.eval.cache import put as cache_put
    cache_put(plan.cache_keys["a"], pre, tmp_path / "cache")
    sut = FailingStubSUT()
    rubric = InProcessStubRubric()
    report = await Runner().execute(
        plan, system_under_test=sut, rubric_runner=rubric,
        cache_dir=tmp_path / "cache", timeout_per_case_seconds=30.0,
    )
    assert sut.call_count == 0
    assert rubric.call_count == 0
    assert report.per_case[0][1].score == 0.99


@pytest.mark.asyncio
async def test_cache_put_oserror_logs_and_continues(tmp_path, monkeypatch, caplog):
    plan = make_stub_plan(tmp_path, case_ids=["a"])
    def put_boom(*a, **kw): raise OSError("disk full")
    monkeypatch.setattr("codegenie.eval.cache.put", put_boom)
    report = await Runner().execute(
        plan, system_under_test=JitteredStubSUT.zero(), **_default_kwargs(tmp_path),
    )
    assert len(report.per_case) == 1
    assert any("runner.cache_put_failed" in rec.message or
               "cache_put_failed" in (rec.event if hasattr(rec, "event") else "")
               for rec in caplog.records)


# ---------- AC-11 / AC-11a — on_score streaming ----------------------------

@pytest.mark.asyncio
async def test_on_score_called_once_per_case_in_completion_order_before_sort(tmp_path):
    plan = make_stub_plan(tmp_path, case_ids=["c", "a", "b"])
    sut = JitteredStubSUT({"a": 0.03, "b": 0.02, "c": 0.005})
    seen: list[str] = []
    async def on_score(case_id, score):
        seen.append(case_id)
    report = await Runner().execute(
        plan, system_under_test=sut, on_score=on_score, **_default_kwargs(tmp_path),
    )
    assert Counter(seen) == Counter(["a", "b", "c"])         # AC-11a
    # Completion order: c first (smallest sleep), then b, then a.
    # AC-11: callback observation is in completion order, not report order.
    assert seen == ["c", "b", "a"]
    assert [cid for cid, _ in report.per_case] == ["a", "b", "c"]   # report sorted


# ---------- AC-12 — exception discipline -----------------------------------

@pytest.mark.asyncio
async def test_keyboard_interrupt_propagates(tmp_path):
    plan = make_stub_plan(tmp_path, case_ids=["a"])
    async def boom(case): raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        await asyncio.wait_for(
            Runner().execute(plan, system_under_test=boom, **_default_kwargs(tmp_path)),
            timeout=5.0,
        )


@pytest.mark.asyncio
async def test_cancelled_error_propagates(tmp_path):
    plan = make_stub_plan(tmp_path, case_ids=["a"])
    async def boom(case): raise asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(
            Runner().execute(plan, system_under_test=boom, **_default_kwargs(tmp_path)),
            timeout=5.0,
        )


# ---------- AC-13 — execute does not write audit chain ---------------------

@pytest.mark.asyncio
async def test_execute_does_not_call_audit_write_run_record(tmp_path, monkeypatch):
    plan = make_stub_plan(tmp_path)
    monkeypatch.setattr(
        "codegenie.eval.audit.write_run_record",
        lambda *a, **kw: pytest.fail("execute() must not write to audit chain — that's S3-06"),
    )
    report = await Runner().execute(
        plan, system_under_test=JitteredStubSUT.zero(), **_default_kwargs(tmp_path),
    )
    assert report.chain_head == ""


# ---------- AC-14 — multi-invariant accounting property --------------------

@given(case_ids=st.lists(
    st.text(alphabet="abcdefghijklmnop", min_size=3, max_size=5),
    min_size=3, max_size=8, unique=True,
))
@settings(max_examples=10, deadline=None)
def test_accounting_invariants_hold(tmp_path_factory, case_ids):
    tmp_path = tmp_path_factory.mktemp("acct")
    plan = make_stub_plan(tmp_path, case_ids=case_ids)
    seen: list[str] = []
    async def on_score(cid, _s): seen.append(cid)
    report = asyncio.run(Runner().execute(
        plan, system_under_test=JitteredStubSUT.zero(),
        on_score=on_score,
        rubric_runner=InProcessStubRubric(),
        cache_dir=tmp_path / "cache", timeout_per_case_seconds=30.0,
    ))
    assert len(report.per_case) == len(plan.cases)                            # invariant 1
    assert {cid for cid, _ in report.per_case} == {c.case_id for c in plan.cases}  # 2
    assert report.passed_count <= len(report.per_case)                        # 3
    assert report.total_cost_usd >= 0.0                                       # 4
    assert Counter(seen) == Counter(cid for cid, _ in report.per_case)        # 5


# ---------- AC-2 (concurrency cap) — gated SUT, positive assertion --------

@pytest.mark.asyncio
async def test_concurrency_default_caps_at_four(monkeypatch, tmp_path):
    monkeypatch.setattr("os.cpu_count", lambda: 16)
    plan = make_stub_plan(tmp_path, case_ids=[f"c{i:02d}" for i in range(8)])
    sut = GatedJitteredStubSUT(n_expected=4)   # gate releases when 4 cases enter
    await asyncio.wait_for(
        Runner().execute(plan, system_under_test=sut, **_default_kwargs(tmp_path)),
        timeout=10.0,
    )
    assert sut.observer.max_inflight == 4


@pytest.mark.asyncio
async def test_concurrency_override_two(tmp_path):
    plan = make_stub_plan(tmp_path, case_ids=[f"c{i:02d}" for i in range(6)])
    sut = GatedJitteredStubSUT(n_expected=2)
    await asyncio.wait_for(
        Runner().execute(plan, system_under_test=sut, concurrency=2, **_default_kwargs(tmp_path)),
        timeout=10.0,
    )
    assert sut.observer.max_inflight == 2
```

**Test file: `tests/unit/test_welford.py`** — AC-6 / AC-6a / AC-6b:

```python
import math
import statistics
from hypothesis import given, strategies as st, settings
from codegenie.eval._welford import WelfordAccumulator


def test_welford_empty_returns_zero():
    w = WelfordAccumulator()
    assert w.n == 0
    assert w.mean == 0.0
    assert w.stddev == 0.0


def test_welford_single_value_returns_zero_stddev():
    w = WelfordAccumulator()
    w.update(0.5)
    assert w.n == 1
    assert w.mean == 0.5
    assert w.stddev == 0.0  # matches statistics.stdev convention for n=1


def test_welford_mean_and_sample_stddev_on_hand_inputs():
    w = WelfordAccumulator()
    for x in [0.2, 0.5, 0.8]: w.update(x)
    assert abs(w.mean - 0.5) < 1e-12
    # sample (n-1) stddev: sqrt(((0.2-0.5)^2 + 0 + (0.3)^2) / (3-1)) = 0.3
    assert abs(w.stddev - 0.3) < 1e-12


def test_welford_matches_statistics_stdev_general():
    inputs = [1.0, 2.0, 3.0, 4.0, 5.0]
    w = WelfordAccumulator()
    for x in inputs: w.update(x)
    assert abs(w.mean - 3.0) < 1e-12
    assert abs(w.stddev - statistics.stdev(inputs)) < 1e-12


def test_welford_numerical_stability_large_offset():
    inputs = [1e9 + 4, 1e9 + 7, 1e9 + 13, 1e9 + 16]
    w = WelfordAccumulator()
    for x in inputs: w.update(x)
    expected_stddev = statistics.stdev(inputs)
    assert abs(w.stddev - expected_stddev) < 1e-9


@given(xs=st.lists(st.floats(min_value=0, max_value=1, allow_nan=False), min_size=2, max_size=32))
@settings(max_examples=30, deadline=None)
def test_welford_order_invariance(xs):
    w1 = WelfordAccumulator()
    for x in xs: w1.update(x)
    w2 = WelfordAccumulator()
    for x in reversed(xs): w2.update(x)
    assert abs(w1.mean - w2.mean) < 1e-9
    assert abs(w1.stddev - w2.stddev) < 1e-9
```

Run all ~22 tests; confirm import/attribute failures (no `runner.py`, no `RubricRunner`, no `_welford.py`). Commit as the red marker.

### Green — make them pass

`asyncio.Semaphore`, `asyncio.Queue` over `tuple[str, BenchScore] | _Sentinel`, one aggregator task with a stable name, Welford in `_welford.py` (sample n−1 stddev), try/finally around fan-out. Stub the rubric in-process via the `RubricRunner` Protocol (S3-03 will swap in `SubprocessRubricRunner`). Cache probe inside the worker. `lower_bound_95 = 0.0` placeholder; `chain_head = ""` placeholder.

### Refactor — clean up

- Module docstring on `runner.py`: documents the import-the-module-not-the-symbol convention AND the "execute does not write to audit chain" invariant (load-bearing for AC-13).
- `WelfordAccumulator` module docstring states "sample n−1 stddev, matching `statistics.stdev`".
- Structured logging at worker start/end with `case_id` bound; document the determinism invariant in the docstring; explicit type alias `OnScoreCallback = Callable[[str, BenchScore], Awaitable[None]] | None`.
- `_run_case` and `_aggregate` are module-level (not inlined) — these are the S3-04 / S3-06 extension seams (AC enforced).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/rubric_runner.py` | NEW: `RubricRunner` Protocol per final-design.md lines 158-168 |
| `src/codegenie/eval/runner.py` | Add `Runner.execute` + `_aggregate` + `_run_case` + `_Sentinel` + `_SENTINEL` + `OnScoreCallback` alias |
| `src/codegenie/eval/_welford.py` | NEW: `WelfordAccumulator` (sample n−1 stddev) |
| `src/codegenie/eval/__init__.py` | Re-export `RubricRunner` |
| `tests/unit/test_runner_execute.py` | NEW: stub-bench happy path, determinism property, no-hang, cache-hit-skip, concurrency cap (gated), exception propagation, no-audit-write, multi-invariant property |
| `tests/unit/test_welford.py` | NEW: Welford correctness + stability + order-invariance |
| `tests/helpers/suts.py` | NEW: `JitteredStubSUT`, `GatedJitteredStubSUT`, `FailingStubSUT`, `_MaxInflightObserver` |
| `tests/helpers/rubrics.py` | NEW: `InProcessStubRubric` (implements `RubricRunner` Protocol) |
| `tests/helpers/bench.py` | EDIT: extend `stub_task_class_fixture(case_ids=...)`; add `make_stub_plan(tmp_path, case_ids=...)` helper |

## Out of scope

- Real subprocess rubric — S3-03 (this story uses an `InProcessStubRubric` matching the `RubricRunner` Protocol).
- The six typed failure-mode mappings (`sut.exception`, `sut.timeout`, `rubric.*`) — S3-04. The `_run_case` extraction is the named seam.
- BCa bootstrap on `lower_bound_95` — S3-05 (set to `0.0` placeholder here).
- Cost-cap cancellation and partial reports (`complete=False`) — S3-06. The `_aggregate` extraction is the named seam.
- Audit chain append — S3-06. This story's `Runner.execute` produces the `BenchRunReport` value with `chain_head=""`; the audit write is the final step of `run_eval`, which composes plan + execute + bootstrap + cost-cap + audit.
- `CaseId` newtype consolidation — phase-wide deferred (S3-01 _validation precedent); `per_case: tuple[tuple[str, BenchScore], ...]` uses raw `str` until the consolidation lands.

## Notes for the implementer

- **`Runner.execute` never writes to the audit chain (AC-13).** S3-06 composes `run_eval(plan, ...) = audit.write_run_record(bootstrap(execute(plan, ...)))`. If you find yourself reaching for `audit.write_run_record` in this story's code, stop — that's wrong.
- **`lower_bound_95=0.0` placeholder is safe** because the report is never audit-chained from this story. S3-05 fills it before S3-06's audit write. ADR-0002's promotion gate cannot see a `lower_bound_95=0.0` from a pre-S3-05 report because the report doesn't exist in the chain yet.
- **Don't conflate "concurrency floor" with "concurrency override."** The default `min(cpu_count(), 4)` is documented in OQ #1 — leave a `# TODO: revisit if portfolio scale forces higher (OQ #1)` comment, don't expand it now.
- **Welford is preferred over `statistics.stdev`** because the aggregator processes scores as they stream in — two-pass would force buffering and lose the streaming property the JSONL CLI mode (S4-02) needs. The S4-02 story may eventually want `WelfordAccumulator` as a public primitive; today it's private (`_welford.py`).
- **The aggregator must be a single task with a stable `name=` kwarg** (`"codegenie-eval-aggregator"`). The AC-4 spy counts by name; renaming the task without updating the test silently breaks the structural guard.
- **The `_SENTINEL` is a class instance, not `None`.** S3-06 will widen the queue type to `tuple[str, BenchScore] | _Sentinel | _Aborted` for the cost-cap-cancellation path — keeping the sentinel a discriminable class today makes that an additive change.
- **The `_run_case` and `_aggregate` extractions are extension seams, not refactor preferences.** Inlining them — even if `execute` could fit in one function today — forces S3-04 and S3-06 into much larger refactors. AC-enforced.
- **Resist threading the rubric subprocess call into the worker now.** S3-03 owns that contract; this story injects `RubricRunner` so S3-03 can substitute `SubprocessRubricRunner` by addition. The Protocol's `rubric_path` argument is already plumbed through.
- **The cache probe in the worker is *after* `async with sem:` — it's cheap (~1 ms) but it still occupies the semaphore.** This is fine; alternative orderings (probe before semaphore acquire) require careful thought about cancellation safety. Defer until OQ #1 surfaces.
- **`CancelledError` from `asyncio.CancelledError` (cost-cap path, S3-06) is *not* the same as `KeyboardInterrupt`.** S3-06 will wrap the cost-cap cancellation; this story must propagate both cleanly. Two separate red tests pin both directions.
- **Deferred design opportunities** (do NOT introduce in this story — surfaced for future triggers):
  - **`Sut` Protocol** (F-DP-2): Phase 6's `VulnRemediationSut` is the second consumer after this story's stubs. When Phase 6 lands, introduce a `Sut` Protocol with `async def run_case(self, case: BenchCase) -> Mapping[str, Any]` and accept `Sut` instances or `sut.run_case` (bound method) at the seam. Today: 2-consumer (stubs are one cohort); below threshold.
  - **`Runner` anaemia re-evaluation** (F-DP-5): after S3-06 adds `cost_total` + `cancellation_event` instance state, re-evaluate whether the class earns its keep. Until then: accept the anaemic shape.
  - **`CachePort` injection** (F-DP-8): when S3-06 wants cache-disable mid-run OR Phase 9 wants distributed cache, promote `cache.{get,put}` to a `CachePort` Protocol on `Runner.__init__`. Today: module-level imports + F-TQ-3 patch-at-import-site is cheaper.
  - **`RunnerConfig` configuration object** (F-DP-9): if S3-06 pushes `Runner.execute` past 6 kwargs, introduce a `RunnerConfig` frozen dataclass. Today: 7 kwargs is at the edge but below the configuration-object threshold (the kwargs are heterogeneous — collaborators vs. config knobs — and bundling them sacrifices test ergonomics).
  - **`WelfordAccumulator` promotion to public** (F-DP-7): if S4-02 needs rolling stats as a CLI primitive, rename `_welford.py` → `welford.py` and add to `__all__`. Today: private.
