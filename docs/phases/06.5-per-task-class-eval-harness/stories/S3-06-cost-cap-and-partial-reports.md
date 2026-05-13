# Story S3-06 — Cost-cap path + partial reports

**Step:** Step 3 — Implement the runner: asyncio fan-out, subprocess rubric, aggregator with BCa bootstrap
**Status:** Ready
**Effort:** M
**Depends on:** S3-02 (aggregator + cancellation surface)
**ADRs honored:** ADR-0002 (lower_bound_95 — `complete=False` means gate refuses), ADR-0009 (humans-always-merge — partial runs feed advisory verdicts), Gap #4 (partial-report tagging)

## Context

When the operator (or CI) sets `--max-cost-usd`, the aggregator monitors `total_cost_usd` after each `BenchScore` lands. If the cap is breached, outstanding worker tasks are cancelled cooperatively, the partial report is tagged `complete=False` and `run_id = f"partial:{...}"` (Gap #4), and the audit chain **still records the partial run**. The promotion gate (S4-04) refuses `evidence_sufficient=True` on any report with `complete=False` — so the cost cap becomes a structural reason for a verdict-refusal, not a silent truncation. Exit code is `2` at the CLI layer (S4-01).

## References — where to look

- **Architecture:** `../phase-arch-design.md §Failure modes` row 2 ("Cost-cap breached"), `§Process view` (cost-cap branch), `§Components → runner.py`
- **Phase ADRs:** `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md` (complete=False blocks promotion), `../ADRs/0009-automatic-demotion-as-recommendation-shift.md`
- **Source design:** `../final-design.md §Gap analysis Gap 4` (partial-report tagging), `§Components → runner.py`

## Goal

Implement cost-cap enforcement in the aggregator: when `running_total_cost_usd > max_cost_usd`, cancel outstanding tasks, prefix the `run_id` with `partial:`, set `complete=False`, and ensure the audit chain still records the partial run.

## Acceptance criteria

- [ ] After each `BenchScore` is consumed by the aggregator, the running cost sum is recomputed; on `running_total_cost_usd > max_cost_usd`, the aggregator calls `task.cancel()` on every outstanding worker task.
- [ ] Cancelled workers emit a synthetic `BenchScore` with `FailureMode(code="sut.cancelled", severity="block", detail="cost-cap exceeded")` for their case so the `per_case` count still reflects every case in the plan (no silent drops).
- [ ] `BenchRunReport.run_id` is `f"partial:{plan.run_id}"` when the cap fired; the original `plan.run_id` is preserved in a sidecar field (`BenchRunReport.original_run_id: str | None`) for traceability.
- [ ] `BenchRunReport.complete is False` when the cap fired; `True` otherwise.
- [ ] The audit chain **still records the partial run**: `audit.write_run_record(report, out_dir)` is called regardless of the cap. A `tests/unit/test_runner_cost_cap.py::test_partial_run_appended_to_audit_chain` test asserts the chain length grew by exactly 1 after the cap fires.
- [ ] A `WARNING` log fires at `> 80%` of the cap (per arch §Logging); an `ERROR` log at the breach.
- [ ] CLI exit code is `2` when `complete=False` due to cost cap; mapping lives in S4-01 but this story exposes the discriminator via `BenchRunReport.complete is False and "cost-cap" in <reason field>`.
- [ ] Cooperative cancellation: workers respect `asyncio.CancelledError` and finalize their tempdir cleanup; the run does not leave stranded subprocesses (`pytest` `tmp_path` cleanup is clean).
- [ ] `mypy --strict`, ruff clean; the red test `tests/unit/test_runner_cost_cap.py::test_complete_false_and_partial_prefix` exists and is green.

## Implementation outline

1. Add `max_cost_usd: float | None = 5.0` to `Runner.execute(...)`; thread through from CLI later.
2. Aggregator maintains `running_total = 0.0`; after `score = await queue.get()`, `running_total += score.cost_usd`.
3. When `running_total > max_cost_usd`:
   - Log `ERROR` `"cost_cap_exceeded"` with `{running_total, max_cost_usd, n_completed}`.
   - Signal cancellation: `cost_cap_event.set()` (an `asyncio.Event` the workers check).
   - For each not-yet-completed case, build a synthetic `BenchScore` with `FailureMode("sut.cancelled", "block", "cost-cap exceeded")`, score `0.0`, cost `0.0`, and emit to the queue.
4. After draining: build the report with `run_id = f"partial:{plan.run_id}"`, `original_run_id = plan.run_id`, `complete = False`.
5. Call `audit.write_run_record(report, out_dir)` (same code path as the complete-run case).
6. Add `complete: bool = True` and `original_run_id: str | None = None` to `BenchRunReport` if not already on the model (S1-02 already adds `complete`; verify).

## TDD plan — red / green / refactor

### Red

`tests/unit/test_runner_cost_cap.py`:

```python
@pytest.mark.asyncio
async def test_complete_false_and_partial_prefix(tmp_path):
    # 5 cases, each emits cost_usd=2.0; cap at 5.0 → cap fires after the 3rd case.
    plan = make_plan_with_costs(case_ids=["a","b","c","d","e"], cost_each=2.0)
    sut = StubSUT(cost_each=2.0)

    report = await Runner().execute(plan, system_under_test=sut, max_cost_usd=5.0)

    assert report.complete is False
    assert report.run_id.startswith("partial:")
    assert report.original_run_id == plan.run_id
    assert len(report.per_case) == 5  # all cases accounted for
    cancelled = [s for s in report.per_case
                 if any(fm.code == "sut.cancelled" for fm in s.failure_modes)]
    assert len(cancelled) >= 2  # at least cases d and e


@pytest.mark.asyncio
async def test_partial_run_appended_to_audit_chain(tmp_path):
    out_dir = tmp_path / ".codegenie" / "eval"
    chain_len_before = len(list_chain(out_dir))
    plan = make_plan_with_costs(["a","b","c"], cost_each=10.0)

    await Runner().execute_and_audit(plan, system_under_test=StubSUT(cost_each=10.0),
                                      max_cost_usd=5.0, out_dir=out_dir)

    chain_len_after = len(list_chain(out_dir))
    assert chain_len_after == chain_len_before + 1
    latest = read_latest_record(out_dir)
    assert latest.complete is False
    assert latest.run_id.startswith("partial:")
```

### Green

Add `max_cost_usd` to `Runner.execute`; running-sum check in aggregator; cancellation `asyncio.Event`; synthetic-cancelled-score emitter; partial-tagged report; unconditional audit append.

### Refactor

Extract `_emit_cancelled_scores(remaining_case_ids, queue)` helper; `_format_partial_run_id(run_id) -> str` for one-liner clarity; structured logging at 80% threshold (`WARNING`) and breach (`ERROR`); explicit docstring on `Runner.execute` documenting Gap #4 ("partial reports are first-class audit records; the gate refuses promotion on them").

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/runner.py` | Cost-cap branch + cancellation + synthetic-cancelled emitter |
| `src/codegenie/eval/models.py` | Confirm `complete: bool = True` + `original_run_id: str | None = None` on `BenchRunReport` |
| `tests/unit/test_runner_cost_cap.py` | New: cap-fires, partial-prefix, audit-chain-still-appends |

## Out of scope

- The exit-code mapping at CLI (S4-01 — exit code 2 for `complete=False` due to cap).
- Promotion gate's refusal on `complete=False` (S4-04 — `IncompleteReportForPromotion`).
- Live-LLM cost tracking source (`SandboxCostEntry.cost_usd` — already wired in Phase 5, consumed via S2-06).
- Per-case cost prediction / forecasting (out of scope; deferred to Phase 13).

## Notes for the implementer

- **The partial run is a real audit record, not a degraded one.** The whole point of Gap #4 is that the chain captures evidence of "we tried, the cap fired, here's what we got." Promotion is the next decision, not the audit's.
- Cooperative cancellation matters: workers must `await proc.wait()` after `proc.kill()` on cancellation, or the test suite leaks zombie subprocesses on macOS (a known annoying failure mode).
- Do **not** raise on cost cap. Raising would skip the audit append and lose the evidence. Returning the partial report is the contract.
- The `sut.cancelled` code is part of the taxonomy (per arch §Failure modes table). Ensure `bench/vuln-remediation/failure_modes.yaml` and `bench/migration-chainguard-distroless/failure_modes.yaml` declare it with `severity: block` — flag this for S5-01 / S6-01 if missing.
- The 80%-of-cap warning is a curator-UX nicety. Don't skip it — the alternative is operators getting bitten by a silent cap-firing on case 9 of 10.
- `original_run_id` is for forensic chain-walking ("which complete run did this partial run shadow?"). Setting it `None` on complete runs keeps the field's presence informative.
