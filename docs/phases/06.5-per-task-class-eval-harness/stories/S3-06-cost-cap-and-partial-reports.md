# Story S3-06 — Cost-cap path + partial reports

**Step:** Step 3 — Implement the runner: asyncio fan-out, subprocess rubric, aggregator with BCa bootstrap
**Status:** Ready
**Effort:** M
**Depends on:** S3-02 (aggregator + cancellation surface)
**ADRs honored:** ADR-0002 (lower_bound_95 — `complete=False` means gate refuses), ADR-0009 (humans-always-merge — partial runs feed advisory verdicts), Gap #4 (partial-report tagging — `complete: bool` field on `BenchRunReport`)

## Context

When the operator (or CI) sets `--max-cost-usd`, the aggregator monitors `total_cost_usd` after each `BenchScore` lands. If the cap is breached, outstanding worker tasks are cancelled cooperatively, the partial report is tagged `complete=False` and `run_id = f"partial:{...}"` (Gap #4), and the audit chain **still records the partial run**. The promotion gate (S4-04) refuses `evidence_sufficient=True` on any report with `complete=False` — so the cost cap becomes a structural reason for a verdict-refusal, not a silent truncation.

This is the operationalization of CLAUDE.md "Fail loud": a half-finished run leaves evidence in the chain that it was half-finished. Phase 13's outcome ledger and cost-analysis surfaces can see "we tried, the cap fired" instead of seeing nothing. The CLI surfaces this with exit code `2` (cost-cap exceeded — S4-01 owns the mapping; this story exposes the discriminator).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Failure modes` row 2 ("Cost-cap breached") — semantics.
  - `../phase-arch-design.md §Process view` cost-cap branch — sequence-diagram view of cancellation.
  - `../phase-arch-design.md §Control flow → Decision points #2` — `total_cost_usd > max_cost_usd` → cancel + partial.
  - `../phase-arch-design.md §Components → runner.py` step 5 — cost-cap is phase 5 of the six-phase pipeline.
  - `../phase-arch-design.md §Gap analysis Gap 4` — three contractual additions: `complete: bool`, gate rejects, verify breakdown.
  - `../phase-arch-design.md §Logging strategy` — `WARNING` at >80% of cap (curator UX); `ERROR` at breach.
- **Phase ADRs:**
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md` — partial reports have `lower_bound_95` over truncated case sets; the gate must refuse them.
  - `../ADRs/0009-automatic-demotion-as-recommendation-shift.md` — humans-always-merge applies symmetrically to demotion-suggesting evidence.
  - `../ADRs/0010-isolation-class-annotation-on-bench-run-report.md` — `isolation_class` is still emitted on partial reports (Phase 16 may want to see "we hit the cap on subprocess isolation").
- **Source design:** `../final-design.md §Gap analysis Gap 4` (the three contractual additions), `§Components → runner.py` step 5 (cost-cap path).

## Goal

Implement cost-cap enforcement in the aggregator: when `running_total_cost_usd > max_cost_usd`, cancel outstanding tasks, prefix the `run_id` with `partial:`, set `complete=False`, ensure the audit chain still records the partial run, and emit a `sut.cancelled` synthetic `BenchScore` for every uncompleted case so `len(per_case)` reflects the full plan.

## Acceptance criteria

- [ ] `Runner.execute(...)` accepts `max_cost_usd: float | None = 5.0`; `None` disables the cap.
- [ ] After each `BenchScore` is consumed by the aggregator, `running_total_cost_usd += score.cost_usd`; on `running_total_cost_usd > max_cost_usd`, the aggregator cancels every outstanding worker task.
- [ ] Cancelled workers emit a synthetic `BenchScore(passed=False, score=0.0, breakdown={}, failure_modes=(FailureMode(code="sut.cancelled", severity="block", detail="cost-cap exceeded"),), cost_usd=0.0, wall_clock_ms=0)` for their case so the `per_case` count still reflects every case in the plan (no silent drops). Assertion: `set(case_id for case_id, _ in report.per_case) == set(plan.cases keys)`.
- [ ] `BenchRunReport.run_id == f"partial:{plan.run_id}"` when the cap fired; `BenchRunReport.original_run_id == plan.run_id`; on complete runs, `original_run_id is None`.
- [ ] `BenchRunReport.complete is False` when the cap fired; `True` otherwise.
- [ ] The audit chain **still records the partial run**: `audit.write_run_record(report, out_dir)` is called regardless of the cap; chain length grows by exactly 1 after the cap fires.
- [ ] A `WARNING` log fires at `>= 80%` of the cap with `{running_total, max_cost_usd, n_completed}`; an `ERROR` log at the breach.
- [ ] CLI exit-code discriminator: a `BenchRunReport` with `complete=False` AND any `sut.cancelled` failure mode is the unambiguous "cost-cap fired" signal; S4-01 maps this to exit code `2`.
- [ ] Cooperative cancellation: workers respect `asyncio.CancelledError`, finalize their tempdir cleanup, and the run does not leave stranded subprocesses (the test suite's `tmp_path` directory contains no rubric-tempdir leftovers after the cap-fires test).
- [ ] `mypy --strict`, `ruff format --check`, `ruff check` clean.
- [ ] All red tests in §TDD plan exist, were committed at the red marker, and are now green.

## Implementation outline

1. Add `max_cost_usd: float | None = 5.0` to `Runner.execute(...)`; thread through from CLI (S4-01 wires the flag).
2. Aggregator maintains `running_total: float = 0.0`; after `score = await queue.get()` (non-sentinel), `running_total += score.cost_usd`.
3. Add a `cost_cap_event = asyncio.Event()` shared across workers + aggregator.
4. When `running_total >= 0.8 * max_cost_usd` and not yet warned: log `WARNING "cost_cap_approaching"` with `{running_total, max_cost_usd, n_completed}`.
5. When `running_total > max_cost_usd`:
   - Log `ERROR "cost_cap_exceeded"` with `{running_total, max_cost_usd, n_completed, n_remaining}`.
   - `cost_cap_event.set()`.
   - Identify uncompleted cases: `remaining_case_ids = set(plan.cases keys) - set(completed_case_ids)`.
   - Cancel outstanding worker tasks: iterate the worker `task` set and call `task.cancel()`.
   - For each `remaining_case_id`, build and emit a synthetic `BenchScore(..., failure_modes=(FailureMode(code="sut.cancelled", severity="block", detail="cost-cap exceeded"),))` to the queue.
6. After draining: build the report with `run_id=f"partial:{plan.run_id}"`, `original_run_id=plan.run_id`, `complete=False`.
7. Call `audit.write_run_record(report, out_dir)` (same code path as the complete-run case).
8. Confirm `BenchRunReport` has `complete: bool = True` (S1-02 lands this) and `original_run_id: str | None = None` (add here if not in S1-02 yet).

## TDD plan — red / green / refactor

### Red — write failing tests first

`tests/unit/test_runner_cost_cap.py`:

```python
import pytest
from codegenie.eval.runner import Runner
from codegenie.eval import audit
from tests.helpers.bench import make_plan_with_costs
from tests.helpers.suts import CostingStubSUT
from tests.helpers.rubrics import in_process_stub_rubric


@pytest.mark.asyncio
async def test_cap_fires_partial_prefix_and_complete_false(tmp_path):
    # 5 cases, each emits cost_usd=2.0; cap at 5.0 → cap fires around case 3.
    plan = make_plan_with_costs(case_ids=["a","b","c","d","e"], cost_each=2.0)
    sut = CostingStubSUT(cost_each=2.0)

    report = await Runner().execute(
        plan, system_under_test=sut, rubric_runner=in_process_stub_rubric,
        max_cost_usd=5.0,
    )

    assert report.complete is False
    assert report.run_id.startswith("partial:")
    assert report.original_run_id == plan.run_id
    assert {cid for cid, _ in report.per_case} == {"a", "b", "c", "d", "e"}
    cancelled = [s for cid, s in report.per_case
                 if any(fm.code == "sut.cancelled" for fm in s.failure_modes)]
    assert len(cancelled) >= 2  # at least 2 cases cancelled
    assert all(s.score == 0.0 for _, s in [(c, sc) for c, sc in report.per_case if c in {cid for cid, sc in report.per_case if any(fm.code == "sut.cancelled" for fm in sc.failure_modes)}])


@pytest.mark.asyncio
async def test_complete_true_when_cap_not_breached(tmp_path):
    plan = make_plan_with_costs(case_ids=["a","b"], cost_each=0.5)
    sut = CostingStubSUT(cost_each=0.5)
    report = await Runner().execute(
        plan, system_under_test=sut, rubric_runner=in_process_stub_rubric,
        max_cost_usd=5.0,
    )
    assert report.complete is True
    assert report.run_id == plan.run_id  # no partial: prefix
    assert report.original_run_id is None


@pytest.mark.asyncio
async def test_partial_run_appended_to_audit_chain(tmp_path):
    out_dir = tmp_path / ".codegenie" / "eval"
    out_dir.mkdir(parents=True)
    chain_len_before = len(list(out_dir.glob("*.json")))
    plan = make_plan_with_costs(["a","b","c"], cost_each=10.0)

    await Runner().run_eval(
        plan, system_under_test=CostingStubSUT(cost_each=10.0),
        rubric_runner=in_process_stub_rubric,
        max_cost_usd=5.0, out_dir=out_dir,
    )

    chain_len_after = len(list(out_dir.glob("*.json")))
    assert chain_len_after == chain_len_before + 1
    # The latest record is a partial:
    latest = audit.read_latest(out_dir)
    assert latest.complete is False
    assert latest.run_id.startswith("partial:")


@pytest.mark.asyncio
async def test_warning_at_80_percent_of_cap(caplog):
    plan = make_plan_with_costs(["a","b","c","d","e"], cost_each=1.0)
    sut = CostingStubSUT(cost_each=1.0)
    await Runner().execute(plan, system_under_test=sut, rubric_runner=in_process_stub_rubric, max_cost_usd=5.0)
    warnings = [r for r in caplog.records if "cost_cap_approaching" in r.message]
    assert warnings, "expected cost_cap_approaching WARNING at >=80% of cap"


@pytest.mark.asyncio
async def test_max_cost_usd_none_disables_cap():
    plan = make_plan_with_costs(["a","b"], cost_each=999.0)
    sut = CostingStubSUT(cost_each=999.0)
    report = await Runner().execute(
        plan, system_under_test=sut, rubric_runner=in_process_stub_rubric,
        max_cost_usd=None,
    )
    assert report.complete is True


@pytest.mark.asyncio
async def test_no_stranded_subprocess_after_cap_fires(tmp_path):
    """Tempdir cleanup robust under cooperative cancellation."""
    plan = make_plan_with_costs(["a","b","c","d"], cost_each=3.0)
    sut = CostingStubSUT(cost_each=3.0, tempdir_observer=tmp_path)
    await Runner().execute(plan, system_under_test=sut, rubric_runner=in_process_stub_rubric, max_cost_usd=3.5)
    leftover = list(tmp_path.glob("rubric-tempdir-*"))
    assert leftover == [], f"stranded tempdirs: {leftover}"
```

Run all six; confirm failures. Commit as the red marker.

### Green — make them pass

Add `max_cost_usd` to `Runner.execute`; running-sum check in aggregator; `asyncio.Event` cancellation signal; synthetic-cancelled-score emitter; partial-tagged report; unconditional audit append. Confirm `BenchRunReport.complete` and `original_run_id` fields exist (S1-02 should land `complete`; add `original_run_id` here if not).

### Refactor — clean up

- Extract `_emit_cancelled_scores(remaining_case_ids, queue)` helper.
- `_format_partial_run_id(run_id) -> str` for the one-liner.
- Structured logging at 80% (`WARNING`) and breach (`ERROR`); single-fire guard on the 80% warning (don't log twice).
- Explicit docstring on `Runner.execute` documenting Gap #4 ("partial reports are first-class audit records; the gate refuses promotion on them; Phase 13's outcome ledger can still see them").
- Add `BenchRunReport.original_run_id: str | None = None` to `models.py` if S1-02 didn't include it; update `__all__` if relevant.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/runner.py` | Cost-cap branch + cancellation + synthetic-cancelled emitter + unconditional audit append |
| `src/codegenie/eval/models.py` | Confirm `complete: bool = True` + add `original_run_id: str | None = None` on `BenchRunReport` if missing |
| `tests/unit/test_runner_cost_cap.py` | New: cap-fires, complete-true, audit-chain-still-appends, 80% warning, `max_cost_usd=None`, no stranded tempdirs |
| `tests/helpers/suts.py` | Add `CostingStubSUT` (per-case cost emission, optional tempdir-observer hook) |

## Out of scope

- The exit-code mapping at CLI (S4-01 — exit code 2 for `complete=False` due to cap).
- Promotion gate's refusal on `complete=False` (S4-04 — `IncompleteReportForPromotion`).
- Live-LLM cost tracking source (`SandboxCostEntry.cost_usd` — already wired in Phase 5, consumed via S2-06).
- Per-case cost prediction / forecasting (deferred to Phase 13).
- `--allow-isolation-mix` override flag for ADR-0010 (deferred to Phase 16).

## Notes for the implementer

- **The partial run is a real audit record, not a degraded one.** The whole point of Gap #4 is that the chain captures evidence of "we tried, the cap fired, here's what we got." Promotion is the next decision, not the audit's.
- Cooperative cancellation matters: workers must `await proc.wait()` after `proc.kill()` on cancellation, or the test suite leaks zombie subprocesses on macOS (a known annoying failure mode). The "no stranded tempdirs" test is the structural guard.
- Do **not** raise on cost cap. Raising would skip the audit append and lose the evidence. Returning the partial report is the contract.
- The `sut.cancelled` code is part of the taxonomy (arch §Failure modes table + ADR-0004 §Consequences list). Ensure `bench/vuln-remediation/failure_modes.yaml` and `bench/migration-chainguard-distroless/failure_modes.yaml` declare it with `severity: block` — flag this for S5-01 / S6-01 if missing.
- The 80%-of-cap warning is a curator-UX nicety. Don't skip it — the alternative is operators getting bitten by a silent cap-firing on case 9 of 10. Use a single-fire guard (`if not warned_at_80 and running_total >= 0.8 * max_cost_usd:`).
- `original_run_id` is for forensic chain-walking ("which complete run did this partial run shadow?"). Setting it `None` on complete runs keeps the field's presence informative.
- The "no silent drops" guarantee (`len(per_case) == n_cases`) is what makes the audit chain useful for Phase 13: a partial run with three cases finished and two cancelled tells a different story from a complete run with three cases. Without the synthetic cancelled scores, the chain would look like a complete-3-case run.
