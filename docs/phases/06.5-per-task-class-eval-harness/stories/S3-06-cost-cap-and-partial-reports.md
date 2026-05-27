# Story S3-06 — Cost-cap path + partial reports

**Step:** Step 3 — Implement the runner: asyncio fan-out, subprocess rubric, aggregator with BCa bootstrap
**Status:** Ready (HARDENED 2026-05-27)
**Effort:** M
**Depends on:** S3-02 (aggregator + cancellation surface — HARDENED), S3-04 (failure-mode mapping + ADR-0004 amendment removing `sut.cancelled` — HARDENED)
**ADRs honored:** phase-arch §Gap 4 (`complete: bool` field on `BenchRunReport` + gate refuses partial — S4-04's `IncompleteReportForPromotion`), ADR-0009 (humans-always-merge — partial runs feed advisory verdicts), ADR-0010 (`isolation_class` is emitted on partial reports unchanged)

## Validation notes

Hardened 2026-05-27 by the `phase-story-validator` skill. 24 critic findings (7 blocks, 13 hardens, 4 nits) applied. Highlights:

- **F-CON-1 / F-DP-1 (block).** The synthesized `FailureMode(code="sut.cancelled", ...)` for every cancelled case was removed. It collided head-on with three HARDENED contracts: (a) S3-04 makes an ADR-0004 §Consequences amendment to **drop** `sut.cancelled` from the seed taxonomy in favor of `sut.timeout`; (b) S3-04 AC-4a forbids synthesizing any `FailureMode` for cases during the cost-cap path; (c) S3-04 AC-7 reserved-namespace defense would rewrite any post-amendment `sut.cancelled` to `rubric.unknown_failure_mode`, destroying the discriminator. The replacement design: workers cooperatively check a shared `cost_cap_event`; the aggregator enqueues an `_Aborted(case_id)` tagged-union marker for each uncompleted case (the queue widening S3-02 HARDENED already prescribed in its Notes-for-implementer block, line 900); the aggregator translates `_Aborted` markers into placeholder `BenchScore(passed=False, score=0.0, breakdown={}, failure_modes=(), cost_usd=0.0, wall_clock_ms=0)` entries at finalize time — `failure_modes=()` (empty), not a synthetic FailureMode. The placeholder reports the *fact* ("this case was cancelled before dispatch") without fabricating a per-case SUT event that never occurred (CLAUDE.md "Facts, not judgments").
- **F-CON-2 (block).** `max_cost_usd: float | None = 5.0` reverted to `max_cost_usd: float = 5.0` (the arch + final-design contract). Operators who want effectively-unlimited pass a large float. Surfacing the conflict, not averaging it (Rule 7).
- **F-CON-3 (block).** `BenchRunReport.original_run_id: str | None` dropped — S1-02 is HARDENED and frozen; a wire-contract field cannot land as an S3-06 refactor. Forensic chain-walking uses `run_id.removeprefix("partial:")` (the `partial:` prefix already encodes the source run id).
- **F-CON-4 (block).** The CLI exit-code discriminator switched from "`complete=False` AND any `sut.cancelled` failure mode" to **`complete is False` alone**. The `complete` boolean is the contract; no FailureMode-based conjunction. (Future partial-reasons — Phase 13 cost-prediction abort, Phase 16 microVM OOM — should add a `partial_reason: Literal["cost_cap"] | None = None` discriminated field on `BenchRunReport`; surfaced as Notes-for-implementer with the rule-of-three trigger, not as an AC today.)
- **F-CON-5 (block).** Cross-process `flock` on `<bench_root>/.<task_class>.runlock` (final-design line 324) is **explicitly deferred to a follow-up story** in Out-of-scope — silent omission would close the critic's `[P]` concurrent-cost-leak attack without evidence. Phase 6.5 ships single-process cost-cap; live-mode cross-host protection is a separate story.
- **F-CON-6 (harden).** ADR attribution corrected: ADR-0002 is the lower_bound_95/BCa contract, NOT the "gate refuses partial" contract. The partial-rejection semantic is owned by phase-arch §Gap 4 + S4-04's `IncompleteReportForPromotion`. Updated in front-matter.
- **F-DP-2 (block).** Aggregator's audit append removed from `Runner.execute(...)`. S3-02 AC-13 pins `execute` as audit-write-free; S3-06 introduces `Runner.run_eval(plan, *, …, out_dir) -> BenchRunReport` as the composition root that owns `audit.write_run_record`. Regression test mirrors S3-02 AC-13's `monkeypatch.setattr("codegenie.eval.audit.write_run_record", lambda *a, **kw: pytest.fail(...))` from inside `execute`.
- **F-DP-3 (harden).** Cancellation choreography pinned: workers respect `cost_cap_event.is_set()` cooperatively at safe-points (top of `_run_case`; before semaphore acquire; after `wait_for(system_under_test, …)`). The aggregator drives the cap detection and `_Aborted`-marker emission. External `task.cancel()` is reserved for S3-04 AC-4a's external-cancel path and is **not** how cost-cap fires. The conflation in the prior draft would have caused workers to raise `CancelledError` (propagating per S3-02 AC-12), bypassing the aggregator's synthesis path.
- **F-DP-4 (harden).** Two named-seam extractions promoted from refactor-note to AC (mirroring S3-02 F-DP-6's precedent of promoting `_run_case`/`_aggregate` from refactor to AC):
  - `_finalize_partial_report(welford, completed_buf, plan, remaining_case_ids, started_at) -> BenchRunReport` — pure.
  - `_next_cap_phase(phase, running_total, cap) -> CostCapPhase` — pure predicate; `CostCapPhase` is a `StrEnum` (`RUNNING | APPROACHING | BREACHED`). Eliminates the flag-pair anti-pattern (two booleans `warned_at_80` + implicit "breached") and forbids the impossible state (warn-after-breach re-fire).
- **F-DP-5 (harden).** Structured-logging contract pinned: events emitted via `structlog.get_logger("codegenie.eval.runner")`; event names `cost_cap_approaching` (WARNING) and `cost_cap_exceeded` (ERROR); tests use `structlog.testing.capture_logs()` (NOT stdlib `caplog`).
- **F-COV-1 (harden).** Edge cases pinned: cap fires on case 1 (immediate breach); boundary `running_total == max_cost_usd` does NOT fire (`>`, not `>=`); `max_cost_usd <= 0.0` raises `ValueError` at entry; exact cancelled cardinality (not `>= 2`).
- **F-COV-2 (harden).** ERROR-log test, single-fire WARNING test, and `cost_cap_approaching` NOT-fired-when-disabled test added. Negative tests catch the early-fire mutation.
- **F-COV-3 (harden).** Audit-chain test asserts both cardinality (`+1` file) AND chain integrity (`audit.verify(out_dir).ok is True`, `latest.prev_hash` matches the previously-written record's identity).
- **F-TQ-1 (block).** Test 1's unreadable nested set-comprehension replaced with a clean `for cid, score in cancelled: assert all of …`. The replacement asserts every field of the placeholder score (`passed=False, score=0.0, breakdown={}, failure_modes=(), cost_usd=0.0, wall_clock_ms=0`).
- **F-TQ-2 (block).** `caplog` calls replaced with `structlog.testing.capture_logs()` everywhere — the codebase uses structlog (`tests/smoke/test_cli_end_to_end.py` precedent); `caplog` would silently miss structlog records.
- **F-TQ-3 (harden).** Deterministic-completion-order tests use a `GatedCostingSUT` (per-case `asyncio.Event` release) so the test asserts `cancelled_ids == {"d", "e"}` and `completed_ids == {"a", "b", "c"}` exactly — not fuzzy `>= 2`.
- **F-TQ-4 (harden).** Property test added: `report.complete is False ⇔ sum(c.cost for c in completed) > max_cost_usd`, and `report.total_cost_usd <= max_cost_usd + max_single_case_cost` (bounded over-shoot). Catches double-counting and off-by-one on the boundary.
- **F-TQ-5 (harden).** Mutation guards on the `complete=True` happy-path test: assert NO `_Aborted` marker leaked into per_case; assert NO `cost_cap_approaching` / `cost_cap_exceeded` log records emitted.
- **F-TQ-6 (nit).** Tempdir-cleanup test pins the `CostingStubSUT.tempdir_observer` contract explicitly in §Implementation outline (otherwise the assertion is vacuous when the SUT never creates tempdirs).
- **F-DP-6 (notes only — Rule 2).** `CostCap` smart-constructor value object deferred until a third threshold-check site lands (Phase 13 cost-prediction). 80% threshold list deferred similarly.
- **F-DP-7 (notes only — Rule 2).** `partial_reason: Literal["cost_cap"] | None = None` field on `BenchRunReport` deferred until Phase 13 / Phase 16 introduce a second partial-reason consumer. `complete=False` is the single discriminator today.

Full audit trail: `_validation/S3-06-cost-cap-and-partial-reports.md`.

## Context

When the operator (or CI) sets `--max-cost-usd`, the aggregator monitors `running_total_cost_usd` after each `BenchScore` lands. If the cap is breached, a shared `cost_cap_event` is set; workers respect it cooperatively at safe-points; the aggregator drains its queue and emits `_Aborted(case_id)` markers for every case that did not produce a real `BenchScore`. At finalize time, `_finalize_partial_report` translates each `_Aborted` marker into a placeholder `BenchScore` with empty `failure_modes` (the *fact* is recorded; no fabricated SUT event). The partial report is tagged `complete=False` and `run_id = f"partial:{plan.run_id}"` (arch §Gap 4); the audit chain **still records the partial run**. The promotion gate (S4-04) refuses `evidence_sufficient=True` on any report with `complete=False` — so the cost cap becomes a structural reason for a verdict-refusal, not a silent truncation.

This is the operationalization of CLAUDE.md "Fail loud": a half-finished run leaves evidence in the chain that it was half-finished. Phase 13's outcome ledger and cost-analysis surfaces can see "we tried, the cap fired" instead of seeing nothing. The CLI surfaces this with exit code `2` (cost-cap exceeded — S4-01 owns the mapping; the discriminator is `complete is False` alone).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Failure modes` row 2 ("Cost-cap breached") — semantics.
  - `../phase-arch-design.md §Process view` cost-cap branch — sequence-diagram view of cancellation.
  - `../phase-arch-design.md §Control flow → Decision points #2` — `total_cost_usd > max_cost_usd` → cancel + partial.
  - `../phase-arch-design.md §Components → runner.py` step 5 — cost-cap is phase 5 of the six-phase pipeline; `max_cost_usd: float = 5.0` (no `None` — the contract is plain `float`).
  - `../phase-arch-design.md §Gap analysis Gap 4` — three contractual additions: `complete: bool` (S1-02 HARDENED ships this), gate rejects (S4-04 owns `IncompleteReportForPromotion`), verify breakdown (this story's audit-still-records AC).
  - `../phase-arch-design.md §Logging strategy` — `WARNING` at >80% of cap; `ERROR` at breach.
- **Phase ADRs:**
  - `../ADRs/0004-per-task-class-failure-modes-taxonomy.md` — **post-S3-04 amendment**: `sut.cancelled` removed from the seed taxonomy; this story does NOT emit it.
  - `../ADRs/0009-automatic-demotion-as-recommendation-shift.md` — humans-always-merge applies symmetrically to demotion-suggesting evidence.
  - `../ADRs/0010-isolation-class-annotation-on-bench-run-report.md` — `isolation_class` is still emitted on partial reports (Phase 16 may want to see "we hit the cap on subprocess isolation").
- **Sibling stories (HARDENED — the contracts THIS story consumes):**
  - `S1-02-wire-models-frozen-extra-forbid.md` — `BenchRunReport.complete: bool = True` is the contract; this story does NOT add fields.
  - `S3-02-asyncio-fan-out-and-aggregator.md` — `Runner.execute` shape; `_Sentinel` discipline; Notes-for-implementer line 900 explicitly prescribes the `_Aborted` queue widening that S3-06 must adopt; AC-13 pins `execute` as audit-write-free.
  - `S3-04-six-per-case-failure-paths.md` — ADR-0004 amendment removing `sut.cancelled`; AC-4a forbids `FailureMode` synthesis on the external-cancel path. This story's `cost_cap_event`-driven cooperative cancellation produces NO `FailureMode`s.
- **Source design:** `../final-design.md §Components → runner.py` step 5 (cost-cap path); `../final-design.md §Failure modes & recovery` row "Cost cap exceeded".

## Goal

Implement cooperative cost-cap enforcement in the aggregator: when `running_total_cost_usd > max_cost_usd`, set the shared `cost_cap_event`; workers honor it at safe-points and exit early; the aggregator emits an `_Aborted(case_id)` marker for every uncompleted case; `_finalize_partial_report` translates each marker into a placeholder `BenchScore` with empty `failure_modes`; the returned `BenchRunReport` is tagged `complete=False`, `run_id=f"partial:{plan.run_id}"`. A separate composition surface `Runner.run_eval(...)` calls `audit.write_run_record` regardless of `complete` so the audit chain records the partial run. `Runner.execute(...)` itself does NOT write to the audit chain (S3-02 AC-13 stays green).

## Acceptance criteria

### Public surface

- [ ] **AC-1.** `Runner.execute(plan, *, system_under_test, rubric_runner, cache_dir, timeout_per_case_seconds, concurrency=None, on_score=None, max_cost_usd: float = 5.0) -> BenchRunReport` — `max_cost_usd` is added as a kwarg to the HARDENED S3-02 signature; type is plain `float` (no `None`; matches arch + final-design). `max_cost_usd <= 0.0` raises `ValueError(f"max_cost_usd must be > 0.0, got {max_cost_usd}")` at entry, before any worker is scheduled.

- [ ] **AC-2.** `Runner.run_eval(plan, *, system_under_test, rubric_runner, cache_dir, timeout_per_case_seconds, concurrency=None, on_score=None, max_cost_usd: float = 5.0, out_dir: Path) -> BenchRunReport` — new public composition surface. Body is a 4-line composition: `report = await self.execute(...)`; (S3-05's `bootstrap` step is a future fold-in, no-op today); `path, head = audit.write_run_record(report, out_dir)`; `return report.model_copy(update={"chain_head": head})`. The audit write is **unconditional on `report.complete`** — partial runs land in the chain.

### Queue widening (S3-02 hand-off)

- [ ] **AC-3.** `_Aborted` is a `@dataclass(frozen=True)` carrying `case_id: str`, declared in `src/codegenie/eval/runner.py`. The worker→aggregator queue type widens from `tuple[str, BenchScore] | _Sentinel` (HARDENED S3-02) to `tuple[str, BenchScore] | _Sentinel | _Aborted`. The aggregator branches via `isinstance(item, _Aborted)` (NOT via `FailureMode` inspection). The queue-type widening is an additive change to the S3-02 contract (`_Sentinel` is still the run-end marker; `_Aborted` is the per-case cancellation marker).

### Cost-cap state machine

- [ ] **AC-4.** `CostCapPhase` is a `StrEnum` in `src/codegenie/eval/runner.py`: `RUNNING | APPROACHING | BREACHED`. The aggregator carries a single `phase: CostCapPhase` variable; transitions are monotonic (`RUNNING → APPROACHING → BREACHED`; never backward; `RUNNING → BREACHED` is allowed when the first score already exceeds the cap). A pure helper `_next_cap_phase(phase: CostCapPhase, running_total: float, cap: float) -> CostCapPhase` lives at module level; unit-tested in `tests/unit/test_runner_cost_cap_helpers.py` for all transition paths (including idempotent re-call: `_next_cap_phase(BREACHED, running_total=anything, cap=anything) == BREACHED`).

- [ ] **AC-5.** After each non-marker queue item is consumed, the aggregator updates `running_total += score.cost_usd` and calls `phase = _next_cap_phase(phase, running_total, cap)`. On transition `RUNNING → APPROACHING` or `RUNNING/APPROACHING → BREACHED`, the corresponding log fires (AC-9, AC-10).

### Cooperative cancellation (no external task.cancel for cost-cap)

- [ ] **AC-6.** `cost_cap_event: asyncio.Event` is shared between aggregator and workers. The aggregator calls `cost_cap_event.set()` on transition to `BREACHED`. Workers check `cost_cap_event.is_set()` at TWO safe-points in `_run_case`: (i) before `async with sem:` (skip if already breached), (ii) after `await asyncio.wait_for(system_under_test(case), …)` returns (do not invoke rubric on a breached run). On either check returning True, the worker `return`s without enqueuing anything for that case. **External `task.cancel()` is NOT used by the cost-cap path** — that is reserved for S3-04 AC-4a's external-cancel path. (Mutation guard: a wrong impl that calls `for t in worker_tasks: t.cancel()` causes `CancelledError` to propagate per S3-02 AC-12, bypassing the aggregator's synthesis path. Red test pins that NO `CancelledError` reaches `execute()`'s caller on a cost-cap fire.)

### Aggregator drains + emits `_Aborted` markers

- [ ] **AC-7.** When the aggregator transitions to `BREACHED`, it: (i) records the set of case_ids that have already produced a `(case_id, score)` item; (ii) drains the queue without blocking (pulls all items already enqueued); (iii) computes `remaining_case_ids = {c.case_id for c in plan.cases} - completed_case_ids - already_aborted_case_ids`; (iv) enqueues `_Aborted(case_id=cid)` for every `cid` in `remaining_case_ids` (in lexicographic order for determinism); (v) continues the consume loop until `_SENTINEL`. Workers that bypass at the cooperative check (AC-6) never reach the queue; the aggregator's `_Aborted`-emission is what guarantees `len(report.per_case) == len(plan.cases)`.

### Placeholder score synthesis (NO synthetic `FailureMode`)

- [ ] **AC-8.** `_finalize_partial_report(welford, completed_buf, aborted_case_ids, plan, started_at) -> BenchRunReport` is a pure module-level helper. For each `case_id` in `aborted_case_ids`, it emits a placeholder `BenchScore(passed=False, score=0.0, breakdown={}, failure_modes=(), cost_usd=0.0, wall_clock_ms=0)`. **Critically, `failure_modes=()` is empty — NO `FailureMode` with `code="sut.cancelled"` is synthesized.** S3-04's ADR-0004 amendment removes `sut.cancelled` from the seed taxonomy; emitting it would resolve via S3-04 AC-7's reserved-namespace defense to `rubric.unknown_failure_mode`, destroying the discriminator. Per-case fact: cancelled-before-dispatch records are placeholder `BenchScore`s, not fabricated SUT events.

- [ ] **AC-9.** The returned `BenchRunReport` has, on a cap-fired run:
  - `complete = False`
  - `run_id = f"partial:{plan.run_id}"`
  - `per_case` contains exactly `len(plan.cases)` entries (every case_id from the plan is present), sorted lexicographically by `case_id`
  - `total_cost_usd = sum(s.cost_usd for cid, s in per_case)` — placeholder scores contribute `0.0`
  - `block_severity_failure_modes` reflects ONLY real rubric-emitted block-severity codes from the completed cases (placeholder scores contribute none, by AC-8)
  - `isolation_class = "subprocess"` (per ADR-0010, unconditional on partial)
  - On a non-cap-fired run: `complete = True`, `run_id = plan.run_id` (no `partial:` prefix), and NO `_Aborted` marker reaches `per_case`.

### Logging contract

- [ ] **AC-10.** WARNING fires at the `RUNNING → APPROACHING` transition (i.e., `running_total >= 0.8 * max_cost_usd` and `< max_cost_usd`). Emitted via `structlog.get_logger("codegenie.eval.runner").warning(event="cost_cap_approaching", running_total=<float>, max_cost_usd=<float>, n_completed=<int>)` where `n_completed` is the count of non-placeholder `BenchScore`s consumed at the moment of emission. The WARNING fires **exactly once per run** — the `RUNNING → APPROACHING` transition is monotonic (AC-4), so re-firing is structurally impossible.

- [ ] **AC-11.** ERROR fires at the `* → BREACHED` transition. Emitted via `structlog.get_logger("codegenie.eval.runner").error(event="cost_cap_exceeded", running_total=<float>, max_cost_usd=<float>, n_completed=<int>, n_remaining=<int>)` where `n_remaining = len(plan.cases) - n_completed`.

- [ ] **AC-12.** Neither `cost_cap_approaching` nor `cost_cap_exceeded` is emitted on a run that does not transition past `RUNNING` (i.e., `sum_of_costs < 0.8 * max_cost_usd`). Negative-fire mutation test pins this.

### Boundary semantics

- [ ] **AC-13.** Boundary `running_total == max_cost_usd` exactly does NOT fire BREACHED — the predicate is `>`, not `>=`. Test pins: `cost_each=2.5, n=2, cap=5.0` → `complete is True`, no `_Aborted` markers in `per_case`.

- [ ] **AC-14.** Cap fires on case 1 when the first completed score alone exceeds the cap. Test: `cost_each=10.0, cap=5.0, n=3` with deterministic completion via a gated SUT (case `a` releases first) → exactly 1 case completed (`a`), exactly 2 cancelled (`b`, `c`); `report.per_case` has 3 entries.

### Audit chain integrity (run_eval-owned)

- [ ] **AC-15.** `Runner.run_eval(...)` calls `audit.write_run_record(report, out_dir)` regardless of `report.complete`. The chain grows by exactly 1 record. Test asserts: (i) `len(list(out_dir.glob("*.json"))) == 0` before; (ii) `== 1` after; (iii) `audit.verify(out_dir).ok is True` (chain integrity); (iv) `audit.read_latest(out_dir).complete is False` and `audit.read_latest(out_dir).run_id.startswith("partial:")` (the persisted record matches the in-memory report). The pre-test directory is fresh-mkdir'd (no prior records).

- [ ] **AC-16.** `Runner.execute(...)` does NOT call `audit.write_run_record` even when the cap fires — S3-02 AC-13 stays green. Regression test mirrors S3-02 AC-13: `monkeypatch.setattr("codegenie.eval.audit.write_run_record", lambda *a, **kw: pytest.fail("execute() must not write to audit chain — that's run_eval's job"))`; assert the cap-fired `execute()` returns a partial report without raising.

### CLI exit-code discriminator (single field)

- [ ] **AC-17.** The unambiguous "cost-cap fired" signal is **`report.complete is False`** alone — no FailureMode-based conjunction. S4-01 maps `complete is False` to exit code `2`. (Future partial reasons — Phase 13 / Phase 16 — extend additively via a `partial_reason` field; surfaced in Notes-for-implementer, deferred today.)

### Tooling

- [ ] **AC-18.** `mypy --strict`, `ruff format --check`, `ruff check` clean on touched files.

- [ ] **AC-19.** All red tests in §TDD plan exist, were committed at the red marker, and are now green.

## Implementation outline

1. **Widen the queue type** in `src/codegenie/eval/runner.py`:
   ```python
   @dataclass(frozen=True)
   class _Aborted:
       case_id: str
   ```
   Queue type becomes `asyncio.Queue[tuple[str, BenchScore] | _Sentinel | _Aborted]`. Aggregator's `isinstance` chain: `_Sentinel` (break loop), `_Aborted` (record case_id in `aborted_case_ids`), else (record completed score).

2. **Cost-cap state machine** at module level:
   ```python
   class CostCapPhase(StrEnum):
       RUNNING = "running"
       APPROACHING = "approaching"
       BREACHED = "breached"

   _APPROACH_RATIO: Final[float] = 0.8

   def _next_cap_phase(phase: CostCapPhase, running_total: float, cap: float) -> CostCapPhase:
       if phase is CostCapPhase.BREACHED:
           return phase                       # monotonic
       if running_total > cap:
           return CostCapPhase.BREACHED
       if phase is CostCapPhase.RUNNING and running_total >= _APPROACH_RATIO * cap:
           return CostCapPhase.APPROACHING
       return phase
   ```

3. **Add `max_cost_usd` to `Runner.execute(...)`** with the validation:
   ```python
   if max_cost_usd <= 0.0:
       raise ValueError(f"max_cost_usd must be > 0.0, got {max_cost_usd}")
   ```
   Thread `max_cost_usd` and `cost_cap_event` into `_aggregate`.

4. **Aggregator extension** — inside `_aggregate(queue, plan, on_score, started_at, max_cost_usd, cost_cap_event)`:
   - Track `phase: CostCapPhase = CostCapPhase.RUNNING`, `running_total: float = 0.0`, `completed_buf: list[tuple[str, BenchScore]] = []`, `aborted_case_ids: set[str] = set()`.
   - On a `(case_id, score)` item: `running_total += score.cost_usd`; append to `completed_buf`; await `on_score(...)` (if provided — S3-02 AC-11 contract); compute `new_phase = _next_cap_phase(phase, running_total, max_cost_usd)`; on `RUNNING → APPROACHING` log WARNING (AC-10); on `* → BREACHED` log ERROR (AC-11), set `cost_cap_event.set()`, then drain remaining queue items (use `queue.get_nowait()` until `QueueEmpty` to capture in-flight items), then compute `remaining = {c.case_id for c in plan.cases} - {cid for cid, _ in completed_buf} - aborted_case_ids` and enqueue `_Aborted(cid)` for each (sorted) — these enqueues are picked up in subsequent loop iterations before `_SENTINEL`.
   - On an `_Aborted(case_id)` item: `aborted_case_ids.add(case_id)`.
   - On `_SENTINEL`: break loop; finalize.

5. **Worker cooperation** in `_run_case` (the S3-02-defined seam):
   ```python
   async def _run_case(case, plan, sem, queue, *, cost_cap_event, …):
       if cost_cap_event.is_set():           # AC-6 (i)
           return
       async with sem:
           if cost_cap_event.is_set():       # AC-6 (i, after acquire)
               return
           # ... cache probe, SUT, rubric ...
           if cost_cap_event.is_set():       # AC-6 (ii)
               return
           await queue.put((case.case_id, score))
   ```

6. **`Runner.run_eval(...)`** — the new composition surface, body shape:
   ```python
   async def run_eval(self, plan, *, out_dir, **kwargs) -> BenchRunReport:
       report = await self.execute(plan, **kwargs)
       # S3-05's bootstrap fold-in is a future composition step; no-op today
       path, head = audit.write_run_record(report, out_dir)
       return report.model_copy(update={"chain_head": head})
   ```

7. **`_finalize_partial_report(welford, completed_buf, aborted_case_ids, plan, started_at) -> BenchRunReport`** (pure, module-level):
   - Build placeholder `BenchScore`s for `aborted_case_ids` (AC-8: `failure_modes=()`).
   - Merge with `completed_buf`; sort by `case_id`.
   - If `aborted_case_ids` is empty: `run_id=plan.run_id`, `complete=True`. Else: `run_id=f"partial:{plan.run_id}"`, `complete=False`.
   - All other fields populated per S3-02 AC-7 (plan-bound + aggregated).

## TDD plan — red / green / refactor

### Red — write failing tests first

`tests/unit/test_runner_cost_cap.py`:

```python
import pytest
import asyncio
from pathlib import Path
from structlog.testing import capture_logs
from codegenie.eval.runner import Runner, _Aborted, CostCapPhase, _next_cap_phase
from codegenie.eval import audit
from tests.helpers.bench import make_plan_with_costs
from tests.helpers.suts import GatedCostingSUT, CostingStubSUT
from tests.helpers.rubrics import InProcessStubRubric


@pytest.mark.asyncio
async def test_cap_fires_partial_prefix_and_complete_false_exact_cardinality(tmp_path):
    """Mutation-resistant: exact completed/cancelled cardinality via gated SUT."""
    plan = make_plan_with_costs(case_ids=["a", "b", "c", "d", "e"], cost_each=2.0)
    sut = GatedCostingSUT(cost_each=2.0, release_order=["a", "b", "c", "d", "e"])
    rubric = InProcessStubRubric()

    report = await Runner().execute(
        plan, system_under_test=sut, rubric_runner=rubric,
        cache_dir=tmp_path / "cache", timeout_per_case_seconds=5.0,
        max_cost_usd=5.0,
    )

    # AC-9: shape
    assert report.complete is False
    assert report.run_id == f"partial:{plan.run_id}"
    assert {cid for cid, _ in report.per_case} == {"a", "b", "c", "d", "e"}
    assert len(report.per_case) == 5

    # AC-7 / AC-8: exact cardinality via deterministic gated completion
    completed_ids = {cid for cid, s in report.per_case if s.cost_usd > 0.0}
    cancelled_ids = {cid for cid, s in report.per_case if s.cost_usd == 0.0}
    assert completed_ids == {"a", "b", "c"}        # 3 cases at $2 = $6 > cap $5
    assert cancelled_ids == {"d", "e"}

    # AC-8: placeholder score field-by-field
    for cid, score in report.per_case:
        if cid in cancelled_ids:
            assert score.passed is False
            assert score.score == 0.0
            assert score.breakdown == {}
            assert score.failure_modes == ()        # NO synthetic FailureMode
            assert score.cost_usd == 0.0
            assert score.wall_clock_ms == 0

    # AC-9: total cost from real cases only
    assert report.total_cost_usd == 6.0


@pytest.mark.asyncio
async def test_cap_fires_on_case_1_immediately(tmp_path):
    """AC-14: a single case whose cost alone exceeds the cap still produces a partial report."""
    plan = make_plan_with_costs(case_ids=["a", "b", "c"], cost_each=10.0)
    sut = GatedCostingSUT(cost_each=10.0, release_order=["a", "b", "c"])

    report = await Runner().execute(
        plan, system_under_test=sut, rubric_runner=InProcessStubRubric(),
        cache_dir=tmp_path / "cache", timeout_per_case_seconds=5.0,
        max_cost_usd=5.0,
    )

    assert report.complete is False
    completed = {cid for cid, s in report.per_case if s.cost_usd > 0.0}
    cancelled = {cid for cid, s in report.per_case if s.cost_usd == 0.0}
    assert completed == {"a"}
    assert cancelled == {"b", "c"}


@pytest.mark.asyncio
async def test_complete_true_no_aborted_markers_no_logs(tmp_path):
    """AC-9 happy path. Mutation guards: no _Aborted leaked into per_case; no cap logs."""
    plan = make_plan_with_costs(case_ids=["a", "b"], cost_each=0.5)
    sut = CostingStubSUT(cost_each=0.5)

    with capture_logs() as logs:
        report = await Runner().execute(
            plan, system_under_test=sut, rubric_runner=InProcessStubRubric(),
            cache_dir=tmp_path / "cache", timeout_per_case_seconds=5.0,
            max_cost_usd=5.0,
        )

    assert report.complete is True
    assert report.run_id == plan.run_id                # no partial: prefix
    # Mutation guards
    assert not any(s.failure_modes for cid, s in report.per_case)  # no synthesized FMs
    assert not any(e.get("event") in {"cost_cap_approaching", "cost_cap_exceeded"} for e in logs)


@pytest.mark.asyncio
async def test_boundary_equality_does_not_fire(tmp_path):
    """AC-13: running_total == max_cost_usd does NOT breach (predicate is `>`, not `>=`)."""
    plan = make_plan_with_costs(case_ids=["a", "b"], cost_each=2.5)
    report = await Runner().execute(
        plan, system_under_test=CostingStubSUT(cost_each=2.5),
        rubric_runner=InProcessStubRubric(),
        cache_dir=tmp_path / "cache", timeout_per_case_seconds=5.0,
        max_cost_usd=5.0,
    )
    assert report.complete is True


@pytest.mark.asyncio
async def test_partial_run_appended_to_audit_chain_with_verify(tmp_path):
    """AC-15: run_eval writes regardless of complete; chain verify passes."""
    out_dir = tmp_path / "runs"
    out_dir.mkdir(parents=True)
    assert len(list(out_dir.glob("*.json"))) == 0      # fresh

    plan = make_plan_with_costs(["a", "b", "c"], cost_each=10.0)
    report = await Runner().run_eval(
        plan,
        system_under_test=GatedCostingSUT(cost_each=10.0, release_order=["a", "b", "c"]),
        rubric_runner=InProcessStubRubric(),
        cache_dir=tmp_path / "cache", timeout_per_case_seconds=5.0,
        max_cost_usd=5.0, out_dir=out_dir,
    )

    files = list(out_dir.glob("*.json"))
    assert len(files) == 1                              # AC-15 (i)/(ii)
    assert audit.verify(out_dir).ok is True             # AC-15 (iii) — chain integrity
    latest = audit.read_latest(out_dir)
    assert latest.complete is False                     # AC-15 (iv)
    assert latest.run_id.startswith("partial:")
    assert report.chain_head != ""                      # run_eval populated it


@pytest.mark.asyncio
async def test_execute_does_not_write_audit_chain_on_cap_fire(tmp_path, monkeypatch):
    """AC-16: regression of S3-02 AC-13 under the cap-fire path."""
    monkeypatch.setattr(
        "codegenie.eval.audit.write_run_record",
        lambda *a, **kw: pytest.fail("execute() must not write to audit chain"),
    )
    plan = make_plan_with_costs(["a", "b", "c"], cost_each=10.0)
    report = await Runner().execute(
        plan, system_under_test=GatedCostingSUT(cost_each=10.0, release_order=["a", "b", "c"]),
        rubric_runner=InProcessStubRubric(),
        cache_dir=tmp_path / "cache", timeout_per_case_seconds=5.0,
        max_cost_usd=5.0,
    )
    assert report.complete is False
    assert report.chain_head == ""                      # untouched by execute


@pytest.mark.asyncio
async def test_warning_at_80_percent_fires_exactly_once(tmp_path):
    """AC-10 + single-fire (structural via monotonic CostCapPhase)."""
    plan = make_plan_with_costs(["a", "b", "c", "d", "e"], cost_each=1.0)
    with capture_logs() as logs:
        await Runner().execute(
            plan, system_under_test=CostingStubSUT(cost_each=1.0),
            rubric_runner=InProcessStubRubric(),
            cache_dir=tmp_path / "cache", timeout_per_case_seconds=5.0,
            max_cost_usd=5.0,                          # 80% = 4.0 → fires after 4 cases
        )
    warnings = [e for e in logs if e.get("event") == "cost_cap_approaching"]
    assert len(warnings) == 1
    assert warnings[0]["max_cost_usd"] == 5.0
    assert warnings[0]["running_total"] >= 4.0
    assert "n_completed" in warnings[0]


@pytest.mark.asyncio
async def test_error_log_at_breach(tmp_path):
    """AC-11: ERROR fires once at breach."""
    plan = make_plan_with_costs(["a", "b", "c"], cost_each=3.0)
    with capture_logs() as logs:
        await Runner().execute(
            plan, system_under_test=GatedCostingSUT(cost_each=3.0, release_order=["a", "b", "c"]),
            rubric_runner=InProcessStubRubric(),
            cache_dir=tmp_path / "cache", timeout_per_case_seconds=5.0,
            max_cost_usd=5.0,
        )
    errors = [e for e in logs if e.get("event") == "cost_cap_exceeded"]
    assert len(errors) == 1
    assert errors[0]["n_remaining"] >= 1
    assert "n_completed" in errors[0]


@pytest.mark.asyncio
async def test_no_warning_when_under_80_percent(tmp_path):
    """AC-12: catches the early-fire mutation."""
    plan = make_plan_with_costs(["a", "b"], cost_each=1.0)        # total=2.0, cap=5.0 → 40%
    with capture_logs() as logs:
        await Runner().execute(
            plan, system_under_test=CostingStubSUT(cost_each=1.0),
            rubric_runner=InProcessStubRubric(),
            cache_dir=tmp_path / "cache", timeout_per_case_seconds=5.0,
            max_cost_usd=5.0,
        )
    assert not any(e.get("event") in {"cost_cap_approaching", "cost_cap_exceeded"} for e in logs)


@pytest.mark.asyncio
async def test_max_cost_usd_zero_or_negative_raises(tmp_path):
    """AC-1: ValueError at entry; no workers scheduled."""
    plan = make_plan_with_costs(["a"], cost_each=1.0)
    for bad in (0.0, -1.0, -0.001):
        with pytest.raises(ValueError, match="max_cost_usd must be > 0.0"):
            await Runner().execute(
                plan, system_under_test=CostingStubSUT(cost_each=1.0),
                rubric_runner=InProcessStubRubric(),
                cache_dir=tmp_path / "cache", timeout_per_case_seconds=5.0,
                max_cost_usd=bad,
            )


@pytest.mark.asyncio
async def test_no_stranded_subprocess_after_cap_fires(tmp_path):
    """AC-6 cooperative cancellation: tempdir cleanup robust under early-return."""
    plan = make_plan_with_costs(["a", "b", "c", "d"], cost_each=3.0)
    sut = CostingStubSUT(cost_each=3.0, tempdir_observer=tmp_path)
    await Runner().execute(
        plan, system_under_test=sut, rubric_runner=InProcessStubRubric(),
        cache_dir=tmp_path / "cache", timeout_per_case_seconds=5.0,
        max_cost_usd=3.5,
    )
    leftover = list(tmp_path.glob("rubric-tempdir-*"))
    assert leftover == [], f"stranded tempdirs: {leftover}"


@pytest.mark.asyncio
async def test_no_cancellederror_propagates_on_cap_fire(tmp_path):
    """AC-6: cost-cap uses cooperative cancellation, not external task.cancel.
    A wrong impl that calls task.cancel() would let CancelledError escape per S3-02 AC-12."""
    plan = make_plan_with_costs(["a", "b", "c"], cost_each=10.0)
    # Must not raise CancelledError
    report = await Runner().execute(
        plan, system_under_test=GatedCostingSUT(cost_each=10.0, release_order=["a", "b", "c"]),
        rubric_runner=InProcessStubRubric(),
        cache_dir=tmp_path / "cache", timeout_per_case_seconds=5.0,
        max_cost_usd=5.0,
    )
    assert report.complete is False
```

`tests/unit/test_runner_cost_cap_helpers.py` — direct unit tests for `_next_cap_phase`:

```python
import pytest
from codegenie.eval.runner import CostCapPhase, _next_cap_phase

def test_running_stays_running_below_80pct():
    assert _next_cap_phase(CostCapPhase.RUNNING, running_total=3.9, cap=5.0) is CostCapPhase.RUNNING

def test_running_to_approaching_at_exact_80pct():
    assert _next_cap_phase(CostCapPhase.RUNNING, running_total=4.0, cap=5.0) is CostCapPhase.APPROACHING

def test_approaching_stays_approaching_below_breach():
    assert _next_cap_phase(CostCapPhase.APPROACHING, running_total=4.9, cap=5.0) is CostCapPhase.APPROACHING

def test_running_to_breached_skips_approaching_when_first_score_exceeds():
    assert _next_cap_phase(CostCapPhase.RUNNING, running_total=10.0, cap=5.0) is CostCapPhase.BREACHED

def test_boundary_equality_is_not_breached():
    """AC-13: > not >=."""
    assert _next_cap_phase(CostCapPhase.APPROACHING, running_total=5.0, cap=5.0) is CostCapPhase.APPROACHING

def test_breached_is_terminal_idempotent():
    assert _next_cap_phase(CostCapPhase.BREACHED, running_total=0.0, cap=5.0) is CostCapPhase.BREACHED
    assert _next_cap_phase(CostCapPhase.BREACHED, running_total=999.0, cap=5.0) is CostCapPhase.BREACHED
```

`tests/property/test_runner_cost_cap_properties.py`:

```python
from hypothesis import given, strategies as st, settings
import pytest
from codegenie.eval.runner import Runner
from tests.helpers.bench import make_plan_with_costs
from tests.helpers.suts import GatedCostingSUT
from tests.helpers.rubrics import InProcessStubRubric


@settings(max_examples=30, deadline=5000)
@given(
    n=st.integers(min_value=1, max_value=8),
    cost_each=st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False),
    cap=st.floats(min_value=0.5, max_value=20.0, allow_nan=False, allow_infinity=False),
)
@pytest.mark.asyncio
async def test_cap_fires_iff_total_exceeds(n, cost_each, cap, tmp_path):
    """AC-13 + AC-9 invariant: complete is False ⇔ n * cost_each > cap."""
    case_ids = [f"c{i:02d}" for i in range(n)]
    plan = make_plan_with_costs(case_ids=case_ids, cost_each=cost_each)
    sut = GatedCostingSUT(cost_each=cost_each, release_order=case_ids)
    report = await Runner().execute(
        plan, system_under_test=sut, rubric_runner=InProcessStubRubric(),
        cache_dir=tmp_path / f"cache_{n}_{cost_each}_{cap}",
        timeout_per_case_seconds=5.0, max_cost_usd=cap,
    )
    expected_partial = (n * cost_each) > cap
    assert (report.complete is False) == expected_partial
    # No-silent-drops accounting (AC-9)
    assert {cid for cid, _ in report.per_case} == set(case_ids)
    # Bounded over-shoot
    assert report.total_cost_usd <= cap + cost_each + 1e-9
```

Run all tests; confirm failures. Commit as the red marker.

### Green — make them pass

Implement per §Implementation outline: `_Aborted` dataclass, `CostCapPhase` StrEnum, `_next_cap_phase` pure helper, `cost_cap_event` plumbing, cooperative `_run_case` checks, aggregator drain + `_Aborted` emission, `_finalize_partial_report` pure helper, `Runner.run_eval` composition.

### Refactor — clean up

- Module docstring on `runner.py` documents Gap #4 ("partial reports are first-class audit records; the gate refuses promotion on them; Phase 13's outcome ledger can still see them") and references S3-04's ADR-0004 amendment removing `sut.cancelled`.
- Single `_format_partial_run_id(run_id: str) -> str` (`f"partial:{run_id}"`) for symmetry with `_finalize_partial_report`.
- Verify no stdlib `logging` calls leaked in (everything via `structlog.get_logger`).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/runner.py` | `_Aborted` dataclass, `CostCapPhase` StrEnum, `_next_cap_phase` helper, cooperative `_run_case` checks, aggregator drain + `_Aborted` emission, `_finalize_partial_report`, `Runner.run_eval` composition, `max_cost_usd` kwarg on `execute` |
| `tests/unit/test_runner_cost_cap.py` | New: all integration tests for the cap-fires path |
| `tests/unit/test_runner_cost_cap_helpers.py` | New: pure-helper unit tests for `_next_cap_phase` (functional core) |
| `tests/property/test_runner_cost_cap_properties.py` | New: Hypothesis property for "complete is False ⇔ total > cap" + bounded over-shoot |
| `tests/helpers/suts.py` | Add `CostingStubSUT` (per-case cost emission, optional tempdir-observer hook) and `GatedCostingSUT` (deterministic release-order via per-case `asyncio.Event`) |

Note: `src/codegenie/eval/models.py` is **NOT** touched. S1-02 ships `complete: bool` already; no new field is added by this story (the `original_run_id` field has been dropped — see Validation notes F-CON-3).

## Out of scope

- The exit-code mapping at CLI (S4-01 — exit code 2 for `complete=False`).
- Promotion gate's refusal on `complete=False` (S4-04 — `IncompleteReportForPromotion`).
- Live-LLM cost tracking source (`SandboxCostEntry.cost_usd` — already wired in Phase 5, consumed via S2-06).
- Per-case cost prediction / forecasting (deferred to Phase 13).
- `--allow-isolation-mix` override flag for ADR-0010 (deferred to Phase 16).
- **Cross-process cost-cap protection via `flock` on `<bench_root>/.<task_class>.runlock`** (final-design line 324). Phase 6.5 ships single-process cooperative cancellation. The cross-host / cross-process protection is a separate story (proposed `S3-06b — Cross-process cost-cap runlock`) once a real live-mode operator workflow exists; today's CI cassette runs do not cross processes. Deferring is explicit, not silent (Validation notes F-CON-5).
- **`BenchRunReport.partial_reason: Literal["cost_cap"] | None = None` field** as the open/closed discriminator for future partial-reason consumers (Phase 13 cost-prediction abort, Phase 16 microVM OOM). Today `complete is False` is the sole discriminator (AC-17); when a second partial-reason lands, the field amendment is the rule-of-three threshold (Notes-for-implementer).

## Notes for the implementer

- **The partial run is a real audit record, not a degraded one.** The whole point of Gap #4 is that the chain captures evidence of "we tried, the cap fired, here's what we got." Promotion is the next decision, not the audit's.
- **Cooperative cancellation matters.** Do NOT `task.cancel()` worker tasks for the cost-cap path — that propagates `CancelledError` through `asyncio.gather` per S3-02 AC-12, bypassing the aggregator's `_Aborted`-emission. External `task.cancel()` is reserved for S3-04 AC-4a's external-cancel CLI path (operator hits Ctrl-C). Cost-cap uses `cost_cap_event` cooperative checks at safe-points in `_run_case`.
- **Do NOT raise on cost cap.** Raising would skip the audit append in `run_eval` and lose the evidence. Returning the partial report is the contract.
- **`failure_modes=()` on placeholder scores is intentional.** Do not synthesize a `FailureMode(code="sut.cancelled", …)` — S3-04's ADR-0004 amendment removed `sut.cancelled` from the seed taxonomy; emitting it would resolve via S3-04 AC-7's reserved-namespace defense to `rubric.unknown_failure_mode`, silently destroying the discriminator. The placeholder records the *fact* (the case was cancelled before dispatch) without fabricating a SUT event.
- **The 80%-of-cap WARNING is a curator-UX nicety.** The structural single-fire guarantee comes from `CostCapPhase`'s monotonicity (`RUNNING → APPROACHING` happens at most once per run — re-fire is impossible because `_next_cap_phase` never returns to `RUNNING`). Tested directly in `test_runner_cost_cap_helpers.py`.
- **`_finalize_partial_report` is pure** — no I/O, no clock reads beyond the `started_at` argument. This is what makes the partial-run synthesis re-testable in isolation and what lets a future Phase 13 cost-predictor build "what would the report have looked like" simulations without spinning up a runner.
- **Future extension: `partial_reason` field.** When Phase 13 cost-prediction-abort or Phase 16 microVM-OOM partial lands as the second partial-reason, add `BenchRunReport.partial_reason: Literal["cost_cap", "<next>"] | None = None`. S4-01's CLI dispatch and S4-04's gate refusal then read one discriminated field. Today (1 producer), `complete is False` is sufficient and avoids a wire-contract change to a HARDENED S1-02 model.
- **Future extension: `CostCap` value object.** If a third threshold-check site lands (e.g., Phase 13 introduces a "soft warn at 50%" threshold), promote `max_cost_usd: float` to `CostCap(limit_usd: float, warn_ratio: float = 0.8)` or `cost_warning_thresholds: tuple[float, ...]`. Today (2 sites — warn at 80%, breach at 100%), the bare kwarg is fine (Rule 2: three similar lines is better than premature abstraction).
- **`_Aborted` queue marker honors the precedent S3-02 set.** The aggregator's `isinstance(item, _Aborted)` branch is the structural seam — a future "partial because of OOM" path would add `class _OOMAborted(_Aborted): ...` (or an adjacent variant) without rewriting the aggregator.
