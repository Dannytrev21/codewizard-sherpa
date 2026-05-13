# Story S9-03 — Concurrent-workflow throughput scaling test (Gap 3)

**Step:** Step 9 — Performance canary (G6) + SQLite throughput watchdog (G9) + ADR-P6-006 escalation hook
**Status:** Ready
**Effort:** S
**Depends on:** S9-02
**ADRs honored:** ADR-0006, ADR-0011, ADR-P6-006

## Context
S9-02's serial throughput watchdog measures the *wrong* workload for Phase 9's production target. Phase 9 will run N workflows in parallel, each against its own per-workflow `.sqlite3` file (ADR-0006); per-workflow files are supposed to eliminate write contention. But the assumption is *untested*: if the bottleneck is OS-level inode contention, per-process `aiosqlite` event-loop overhead, or the shared `chain_lock` ADR-0007 introduces, a serial test passes while production hits a wall the moment concurrency rises. The synthesizer flagged this as **Gap 3** in the arch design (`phase-arch-design.md §Gap analysis Gap 3`) and committed to a multi-workflow concurrent test as the closer. This story ships it: N=10 `asyncio.Task`s each driving a separate `AuditedSqliteSaver(<workflow_N>.sqlite3)` through 100 serial checkpoints; aggregate throughput must scale to at least 10× the single-workflow baseline that S9-02 recorded — otherwise per-workflow-file isolation isn't actually isolating, and ADR-P6-006 escalates with a *distinct* trigger condition pointing at concurrency contention rather than disk fsync.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Gap analysis Gap 3` (lines 1331–1336) — the gap statement, the test specification (N=10 tasks × 100 checkpoints), the ≥ 10× scaling threshold, and the consequence (ADR-P6-006 escalates).
  - `../phase-arch-design.md §Performance regression tests` (lines 1208–1212).
  - `../phase-arch-design.md §Persistence view` — per-workflow file layout under `.codegenie/loop/checkpoints/<workflow_id>.sqlite3`.
  - `../phase-arch-design.md §Tradeoffs table` row 10 — same escalation row as serial throughput; the *trigger condition* differs (concurrency vs serial).
- **Phase ADRs:**
  - `../ADRs/0006-audited-sqlite-saver-per-workflow-fsync.md` — the per-workflow-file premise being stress-tested.
  - `../ADRs/0011-sqlite-throughput-watch-and-postgres-escalation.md` §"complementary multi-workflow concurrent test" (line 30) — defines `tests/perf/test_checkpoint_concurrent_throughput.py` and the post-baseline threshold rule.
  - `../ADRs/0007-blake3-chain-extension-and-tamper-evidence.md` — the shared `chain_lock` that may be the bottleneck if per-workflow files aren't enough.
  - `../ADRs/P6-006-sqlite-throughput-insufficient.md` (shipped by S9-02) — this story's failure path adds a *concurrent* trigger row to the ADR's Numeric thresholds table.
- **Source design:**
  - `../final-design.md §Synthesis ledger shared blind spot #1` — measurement-not-assumption commitment.
  - `../final-design.md §Risk 3` — the escalation procedure.
- **High-level-impl:** `../High-level-impl.md §Step 9 — Features delivered bullet 3` — the explicit N=10 × 100 spec.
- **Existing code:**
  - `src/codegenie/graph/checkpointer.py` — `make_checkpointer(workflow_id, *, base)` is the factory; each task instantiates its own via a distinct `workflow_id`.
  - `tests/perf/test_checkpoint_throughput.py` (from S9-02) — reuse `_measure_serial_throughput` if the helper was extracted in S9-02's refactor step.
  - `tests/perf/baseline.json` — must contain `"checkpoint_throughput"` from S9-02 to derive the 10× target; if missing, the test skips with a clear instruction (not a silent pass).

## Goal
Ship `tests/perf/test_checkpoint_concurrent_throughput.py` such that N=10 `asyncio.Task`s, each driving a separate `AuditedSqliteSaver(workflow_id=…)` through 100 serial checkpoints, complete with aggregate throughput **≥ 10× the single-workflow `writes_per_second`** recorded in `tests/perf/baseline.json` by S9-02; on failure the test fails with an explicit `"ADR-P6-006 escalation: concurrent-throughput scaling below 10× single-workflow baseline"` message and records the per-task and aggregate numbers to `baseline.json` for diagnostics.

## Acceptance criteria
- [ ] `tests/perf/test_checkpoint_concurrent_throughput.py` exists. It reads `tests/perf/baseline.json`'s `checkpoint_throughput.writes_per_second` as the single-workflow baseline; if absent, the test fails (not skips) with the message `"Concurrent test requires S9-02 baseline; run test_checkpoint_throughput.py first"`.
- [ ] The test spawns **N=10** `asyncio.Task`s via `asyncio.gather(*tasks)`. Each task: (1) calls `make_checkpointer(workflow_id=f"perftest_concurrent_{i}", base=tmp_path)` with a distinct workflow_id (i ∈ 0..9, producing 10 distinct `.sqlite3` files in `tmp_path`); (2) issues a 5-call warmup; (3) issues exactly **100 serial timed `put()` calls** with a mutated `VulnLedger` per call (same mutation pattern as S9-02 — increment a counter / append to `prior_attempts`); (4) returns its own `(writes_per_second_for_this_task, elapsed_s_for_this_task)`.
- [ ] Aggregate throughput is computed as `total_writes / wall_clock_elapsed_s` where `total_writes = 10 * 100 = 1000` and `wall_clock_elapsed_s` is the wall-clock from "all tasks started" to "all tasks completed" (measured around the `asyncio.gather`, **not** the sum of per-task elapsed which would double-count serialization).
- [ ] The test asserts `aggregate_writes_per_second >= 10.0 * single_workflow_baseline_wps`. On failure, the assertion message contains: (1) the literal `"ADR-P6-006 escalation: concurrent-throughput scaling below 10× single-workflow baseline"`; (2) the single-workflow baseline; (3) the measured aggregate; (4) the scaling factor (`aggregate / baseline`, rounded to 2 decimal places); (5) the per-task throughputs (10 numbers) so an operator can see whether one task lagged or all 10 lagged uniformly — the failure mode tells you whether it's contention or per-process overhead.
- [ ] On both pass and failure, the test merges `{"concurrent_throughput": {"aggregate_writes_per_second": <float>, "single_workflow_baseline_wps": <float>, "scaling_factor": <float>, "n_tasks": 10, "iterations_per_task": 100, "per_task_wps": [<10 floats>], "wall_clock_s": <float>, "recorded_at": "<ISO-8601-UTC>"}}` into `tests/perf/baseline.json` — failures still record for diagnostic value (ADR-0011's "first run records the baseline" rule explicitly applies to this test).
- [ ] Each task's `put()` calls are **serial within the task** (await one before issuing the next); concurrency exists only *across* tasks. This is the production access pattern — one workflow is single-writer; N workflows write in parallel.
- [ ] The 10 `.sqlite3` files are confirmed distinct on disk (assert `len(list(tmp_path.glob("*.sqlite3"))) == 10` after the run); this guards against an accidental shared-DB bug where all tasks point at the same file.
- [ ] No `chain_lock` reach-around — the test calls the public `make_checkpointer` factory and the public `put()` path only; if the ADR-0007 shared `chain_lock` is the bottleneck, the test must surface it via *measured* contention, not by inspecting internals.
- [ ] The test is marked `@pytest.mark.asyncio` and `@pytest.mark.slow`; it runs only on the merge-queue nightly cron.
- [ ] A meta-test `test_concurrent_failure_message_format` (not `@pytest.mark.slow`) verifies the failure-message string contract: it constructs the message via the formatter helper with synthetic numbers and asserts the canonical literal plus all five components are present.
- [ ] A meta-test `test_concurrent_baseline_missing_fails_loudly` (not `@pytest.mark.slow`) constructs an empty `baseline.json` in `tmp_path` and asserts the canonical "requires S9-02 baseline" message — guards Rule §12 ("Fail loud") against a future refactor that silently skips.
- [ ] ADR-P6-006's `Numeric thresholds` table is **updated** (this PR edits the ADR file shipped by S9-02) to add a second row: `concurrent_aggregate_scaling_floor=10.0× single-workflow baseline`, with a separate `Trigger condition` row for the concurrent test. The escalation procedure is unchanged.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/perf/test_checkpoint_concurrent_throughput.py -m slow` all pass.

## Implementation outline
1. Read `tests/perf/test_checkpoint_throughput.py` (S9-02). If `_measure_serial_throughput(checkpointer, *, iterations, warmup)` was extracted, reuse it inside each task; otherwise inline the loop. Do not re-implement S9-02's mutation pattern — match it exactly so the only variable is concurrency.
2. Read `src/codegenie/graph/checkpointer.py` to confirm `make_checkpointer` accepts a per-call `base` override (per S2-01). If it does not, surface that as a blocker for this story — do not silently work around it by mutating `cwd`.
3. Create `tests/perf/test_checkpoint_concurrent_throughput.py` with:
   - Module-level constant `N_CONCURRENT_TASKS = 10` and `ITERATIONS_PER_TASK = 100`.
   - Module-level constant `CONCURRENT_SCALING_FLOOR = 10.0`.
   - `_format_concurrent_failure_message(...)` helper (mirrors S9-02's pattern).
   - `_load_single_workflow_baseline_wps(baseline_path: Path) -> float` — reads `baseline.json`, returns `checkpoint_throughput.writes_per_second`, raises with the canonical missing-baseline message on KeyError or FileNotFoundError.
   - `async def _run_one_task(task_index, base, iterations) -> tuple[float, float]` — opens its own checkpointer, runs warmup + timed loop, returns `(wps, elapsed_s)`.
   - The main `test_concurrent_throughput_scales_to_10x_single_baseline` async body assembles 10 tasks via `asyncio.gather`, times wall-clock, computes aggregate, asserts, records.
4. Edit `docs/phases/06-sherpa-state-machine/ADRs/P6-006-sqlite-throughput-insufficient.md` to add the concurrent row to the `Numeric thresholds` table and a second bullet under `Trigger condition`. Cross-link from `Evidence / sources` to this story.
5. Update `tests/perf/README.md`: add a paragraph distinguishing the serial floor (S9-02) from the concurrent scaling floor (S9-03), noting they are *independent* gates with *one* escalation ADR (ADR-P6-006).
6. Confirm `mypy --strict`; `asyncio.gather` typing on heterogeneous return shapes can require an explicit `tuple[float, float]` annotation on `_run_one_task`.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/perf/test_checkpoint_concurrent_throughput.py` (the meta-tests are the red sources — they assert the message-format contracts before the production code exists).

```python
# tests/perf/test_checkpoint_concurrent_throughput.py
import json
import pytest
from pathlib import Path

from tests.perf.test_checkpoint_concurrent_throughput import (
    CONCURRENT_SCALING_FLOOR,
    N_CONCURRENT_TASKS,
    ITERATIONS_PER_TASK,
    _format_concurrent_failure_message,
    _load_single_workflow_baseline_wps,
)


def test_concurrent_scaling_floor_is_ten_x() -> None:
    # Guards ADR-0011: any change requires amending the ADR.
    assert CONCURRENT_SCALING_FLOOR == 10.0


def test_concurrent_task_count_is_ten() -> None:
    # Gap 3 in arch design specifies N=10 explicitly.
    assert N_CONCURRENT_TASKS == 10
    assert ITERATIONS_PER_TASK == 100


def test_concurrent_failure_message_format(tmp_path: Path) -> None:
    msg = _format_concurrent_failure_message(
        single_baseline_wps=150.0,
        aggregate_wps=900.0,
        scaling_factor=6.0,
        per_task_wps=[120.0, 95.0, 88.0, 110.0, 105.0, 92.0, 99.0, 102.0, 97.0, 90.0],
    )
    assert "ADR-P6-006 escalation: concurrent-throughput scaling below 10× single-workflow baseline" in msg
    assert "150.0" in msg or "150.00" in msg  # baseline
    assert "900.0" in msg or "900.00" in msg  # aggregate
    assert "6.0" in msg or "6.00" in msg  # scaling factor
    # Per-task numbers must all appear (at least the first and last as a smoke check)
    assert "120.0" in msg or "120.00" in msg
    assert "90.0" in msg or "90.00" in msg


def test_concurrent_baseline_missing_fails_loudly(tmp_path: Path) -> None:
    empty_baseline = tmp_path / "baseline.json"
    empty_baseline.write_text("{}")
    with pytest.raises(AssertionError) as exc:
        _load_single_workflow_baseline_wps(empty_baseline)
    assert "requires S9-02 baseline" in str(exc.value)
    assert "test_checkpoint_throughput.py" in str(exc.value)


def test_concurrent_baseline_uses_s9_02_record(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"checkpoint_throughput": {"writes_per_second": 137.5}}))
    assert _load_single_workflow_baseline_wps(baseline) == 137.5
```

### Green — make it pass
Implement the four named module-level objects plus the helpers. Then implement the real `@pytest.mark.slow` async test body using `asyncio.gather` over 10 `_run_one_task(...)` coroutines, each opening its own `make_checkpointer(workflow_id=...)`.

### Refactor — clean up
If S9-02 extracted `_measure_serial_throughput`, call it from `_run_one_task` so the inner loop is identical to S9-02's. Pull `_format_concurrent_failure_message` next to `_format_throughput_failure_message` if both end up in a shared `tests/perf/_helpers.py` — but only if S9-02 has already created that file. Do not preemptively extract.

## Files to touch
| Path | Why |
|---|---|
| `tests/perf/test_checkpoint_concurrent_throughput.py` | The concurrent-scaling test. |
| `docs/phases/06-sherpa-state-machine/ADRs/P6-006-sqlite-throughput-insufficient.md` | Add the concurrent threshold row + trigger condition. |
| `tests/perf/README.md` | Document the serial-vs-concurrent gate distinction. |

## Out of scope
- **Per-node overhead** — S9-01.
- **Serial throughput floor** — S9-02. The 100 writes/s floor is *not* the same gate; this story compares against the *baseline* S9-02 recorded, not the floor.
- **Tuning the 10× scaling factor based on measurement** — the threshold is set *before* the first run per ADR-0011's commitment. If the first CI run shows the per-workflow-file premise is wrong and 10× is unachievable, that is *exactly the signal* the gate is designed to surface; do not pre-tune to make the gate pass.
- **N > 10** — the synthesizer picked 10 (`phase-arch-design.md §Gap 3`). Higher N belongs to Phase 9 stress tests, not Phase 6 CI.
- **Editing ADR-0011** — no policy change; ADR-P6-006 (S9-02's ADR) absorbs the concurrent threshold.

## Notes for the implementer
- The **wall-clock around `asyncio.gather`** is the load-bearing measurement, not the sum of per-task elapsed times. A naive `sum(per_task_elapsed)` divides by `N`, looks like 10× scaling, and silently passes even when tasks ran serially because the event loop got starved. Time the gather, divide total writes by gather-elapsed. Add a comment quoting this rule — it is the single easiest way to break the test.
- The per-task throughputs in the failure message are diagnostic gold. If all 10 are ~equal at, say, 30 wps when serial baseline is 200 wps, the bottleneck is per-process overhead (event loop, aiosqlite). If one task is 200 wps and nine are 5 wps, the bottleneck is contention (shared lock, inode). The same test failure tells two different stories; preserve the per-task list.
- Distinct `.sqlite3` files are the premise of ADR-0006. The `len(...) == 10` assertion after the run is not paranoia — a typo in `workflow_id` (e.g., constant instead of `f"…_{i}"`) would silently collapse all writes into one file, hide the real concurrency cost, and let the test pass for the wrong reason. The post-run file-count assertion catches that bug.
- The `chain_lock` from ADR-0007 is shared across all writers in the same process. If the concurrent test fails, the lock is a prime suspect. The test does *not* probe internals — but the failure message's diagnostic data is what an operator uses to decide between (a) Postgres pull-forward (per ADR-P6-006), (b) lock-granularity refactor, or (c) per-task subprocess isolation. The test is the signal; the response is the ADR's procedure.
- ISO-8601-UTC `recorded_at` matches S9-01 and S9-02's convention — use the same `datetime.now(tz=datetime.UTC).isoformat()` snippet. Consistency across the three records makes `baseline.json` greppable.
- The `iterations_per_task=100` is intentionally smaller than S9-02's 1,000. Why: 10 tasks × 100 iterations = 1,000 total writes (matches S9-02's total), so the *workload* is held constant and the only changed variable is concurrency. Do not raise to 1,000 per task — that would change two variables at once and confound the comparison.
- The `pytest-asyncio` event loop scope matters: use `@pytest.mark.asyncio` with the default function-scope loop; per-task event loops would over-isolate and miss the shared-loop overhead this test exists to surface.
- ADR-P6-006's edit is *additive* — append a row to the table, append a trigger-condition bullet. Do not rewrite the ADR; S9-02 owns the structure. If you find yourself rewriting more than the table row and one bullet, stop and surface — a deeper change belongs in its own ADR amendment.
- If the test fails on the first run, the *correct* response is to commit the failure record to `baseline.json` and open the ADR-P6-006 amendment story per ADR-0011's procedure. Do not "tune" the threshold to make it pass. This is the third gate in Step 9 — its job is to fire when reality disagrees with the design.
- Concurrent tests on CI are flakier than serial. If transient flake appears, the response is the same as S9-01's: investigate, do not skip. The threshold (10×) is calibrated to be achievable when the design's premise (per-workflow files isolate writers) holds; if it doesn't hold, the test is correct to fail.
