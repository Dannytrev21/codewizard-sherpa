# Validation report — S3-06 Cost-cap path + partial reports

**Validator:** `phase-story-validator` skill
**Date:** 2026-05-27
**Verdict:** **HARDENED** (story had multiple BLOCK-level collisions with HARDENED sibling stories; significant in-place rewrite applied)

## Summary

Story S3-06 had structural problems beyond cosmetic AC tightening — but not structural enough to warrant RESCUE because the **goal** (cost-cap fires → partial report → audit chain still records) is sound and aligns with phase-arch §Gap 4, ADR-0009, S1-02's `complete: bool` field, and S4-04's `IncompleteReportForPromotion`. What needed surgery was the **implementation mechanics**, which had drifted from contracts that S3-02 and S3-04 hardened *after* S3-06 was written.

**Critic counts:** 8 BLOCKs, 13 HARDENs, 4 NITs across the four critics.

## Context Brief used by critics

- **Goal:** Implement cost-cap enforcement in the aggregator; cancel outstanding tasks; tag report `partial:` + `complete=False`; audit chain still records.
- **Sibling-family lineage:** S3-06 is the 3rd story in the runner-aggregator family (after S3-01 HARDENED runner plan; S3-02 HARDENED fan-out + aggregator; S3-03 subprocess rubric; S3-04 HARDENED typed failure paths; S3-05 deterministic BCa bootstrap). S3-02 explicitly hands off a queue-widening contract to S3-06 ("S3-06 will widen the queue type to `tuple[str, BenchScore] | _Sentinel | _Aborted` for the cost-cap-cancellation path" — line 900 of S3-02). S3-04's ADR-0004 amendment (precondition) removes `sut.cancelled` from the seed taxonomy and forbids `FailureMode` synthesis on the cost-cap path.
- **Phase / arch constraints:** `max_cost_usd: float = 5.0` (plain `float`, not `float | None`); `complete: bool` is the field (final-design's `aborted` is stale wording superseded by phase-arch §Gap 4); audit-chain append is unconditional on `complete`; S3-02 AC-13 pins `Runner.execute` as audit-write-free.

## Critic 1: Coverage

**Verdict: 2 blocks, 9 hardens, 2 nits.**

Key findings applied:
- **F-COV-1 (block)** — signature type contradiction (`float | None` vs arch `float`). Reverted to `float = 5.0` (the source-of-truth contract). Aligned with Consistency F-CON-2.
- **F-COV-2 (block)** — audit-chain test asserted file count only, not chain integrity. New AC-15 asserts both cardinality AND `audit.verify(out_dir).ok is True`, AND `audit.read_latest(out_dir).complete is False`.
- **F-COV-3..9 (hardens)** — boundary `>` vs `>=` test (new AC-13); `0.0` / negative semantics (new AC-1 raises `ValueError`); cap-fires-on-case-1 (new AC-14); exact cancelled count via gated SUT (replaced fuzzy `>= 2`); ERROR-log assertion (new AC-11); single-fire WARNING (structurally pinned via `CostCapPhase` monotonicity); WARNING-NOT-fired when disabled (new AC-12); `severity="block"` on synthetic FailureMode (resolved by removing the FailureMode entirely — see Consistency F-CON-1); chain integrity test.

Coverage's 2 nits (`n_completed` definition; WARNING/ERROR Goal-to-AC trace) folded into AC-10/AC-11 explicit definitions.

## Critic 2: Test-Quality (mutation thinking)

**Verdict: 3 blocks, 5 hardens, 2 nits, plus 4 missing test types and 4 properties.**

Key findings applied:
- **F-TQ-1 (block)** — Test 1's unreadable nested set-comprehension was mutation-tolerant and tautological when the cancelled set is empty. Rewritten with a clean `for cid, score in report.per_case: if score.cost_usd == 0.0: assert score.passed is False and score.score == 0.0 and ...` pattern that asserts every field of the placeholder.
- **F-TQ-2 (block)** — `caplog` is stdlib-only; codebase uses structlog. All log-capture rewritten to `with capture_logs() as logs:` per `structlog.testing`. (Verified the precedent in `tests/smoke/test_cli_end_to_end.py`.)
- **F-TQ-3 (block)** — `Runner.run_eval` vs `Runner.execute` surface ambiguity. Rewrote AC-1 / AC-2 to make the bifurcation explicit: cost-cap state owned by `execute`; audit-write owned by `run_eval`. Aligned with Design-Patterns F-DP-3.
- **F-TQ-4..6 (hardens)** — exact cardinality via `GatedCostingSUT`; structural single-fire WARNING; structural no-warning-when-disabled; tempdir-observer contract pinned in §Implementation outline.
- Added Hypothesis property `test_cap_fires_iff_total_exceeds` over `(n, cost_each, cap)`: asserts `complete is False ⇔ n * cost_each > cap`, set equality on `per_case` case_ids (no silent drops), bounded over-shoot `total_cost_usd <= cap + cost_each` (catches double-counting).

## Critic 3: Consistency

**Verdict: 7 blocks, 2 hardens, 1 nit. The most severe critic.**

Key findings applied:
- **F-CON-1 (block)** — Story emitted `FailureMode(code="sut.cancelled", ...)` synthetic for every cancelled case. This collides head-on with three HARDENED contracts:
  1. S3-04 ADR-0004 amendment (precondition): drops `sut.cancelled` from the seed taxonomy in favor of `sut.timeout`.
  2. S3-04 AC-4a: external-cancel path forbids `FailureMode` synthesis for any case.
  3. S3-04 AC-7 reserved-namespace defense: any rubric-emitted `sut.cancelled` (or runner-emitted, by extension) post-amendment resolves to `rubric.unknown_failure_mode` — silently destroying the discriminator.
  **Resolution:** placeholder scores use `failure_modes=()` (empty); no synthetic FailureMode. The fact ("case was cancelled before dispatch") is recorded; no fabricated SUT event (CLAUDE.md "Facts, not judgments"). Aligned with Design-Patterns F-DP-1.
- **F-CON-2 (block)** — `max_cost_usd: float | None = 5.0` contradicts arch's `float = 5.0`. Reverted to plain `float`. Surfacing the conflict (Rule 7), not averaging.
- **F-CON-3 (block)** — `BenchRunReport.original_run_id: str | None` is a new field on a HARDENED frozen Pydantic model (S1-02 ships `extra="forbid"`). Dropped. Forensic chain-walking uses `run_id.removeprefix("partial:")` (the prefix already encodes the source).
- **F-CON-4 (block)** — CLI exit-code discriminator changed from "complete=False AND any sut.cancelled FailureMode" to **`complete is False` alone**. Consistent with the absence of `sut.cancelled` post-S3-04. Aligned with Design-Patterns F-DP-2.
- **F-CON-5 (block)** — Cross-process `flock` at `<bench_root>/.<task_class>.runlock` (final-design line 324) is now **explicitly deferred** in Out-of-scope with a forward-pointer to a `S3-06b` follow-up story. Silent omission would have closed the critic's `[P]` concurrent-cost-leak attack without evidence.
- **F-CON-6 (harden)** — ADR-0002 attribution corrected; gate-refuses-partial semantic is owned by phase-arch §Gap 4 + S4-04's `IncompleteReportForPromotion`, not ADR-0002 (which is the BCa/lower-bound contract).
- **F-CON-7 (harden)** — `Runner.execute` vs `Runner.run_eval` bifurcation made explicit (AC-1 / AC-2). Regression AC-16 mirrors S3-02 AC-13's `monkeypatch.setattr("codegenie.eval.audit.write_run_record", lambda *a, **kw: pytest.fail(...))` under the cap-fire path.

Note: Consistency also flagged final-design line 293's stale wording (`BenchRunReport.aborted = True` vs the actual field `complete`). Out of scope for this validation; flagged for a separate doc-cleanup commit.

## Critic 4: Design-Patterns

**Verdict: 3 blocks, 4 hardens, 2 nits.**

Key findings applied:
- **F-DP-1 (block)** — Adopt the `_Aborted` tagged-union queue widening that S3-02 explicitly handed off. The new design uses `_Aborted(case_id: str)` as the per-case cancellation marker on the queue; `_finalize_partial_report` translates `_Aborted` markers into placeholder `BenchScore`s at finalize time. The wire-type (`BenchScore`) and the control-signal type (`_Aborted`) are now distinct — no primitive obsession.
- **F-DP-2 (block)** — Discriminator switched to single field `complete is False`. The `partial_reason: Literal["cost_cap"] | None` extension is surfaced in Notes-for-implementer with a rule-of-three trigger (Phase 13 or Phase 16 as the second consumer). Today: 1 partial-reason → 1 field; deferring is Rule 2 conformance.
- **F-DP-3 (block)** — `Runner.run_eval(...)` is the composition root; `Runner.execute(...)` is audit-write-free. AC-2 specifies the 4-line composition. AC-16 is the regression test mirroring S3-02 AC-13.
- **F-DP-4 (harden)** — Two named-seam extractions promoted from refactor-note to AC (S3-02 F-DP-6 precedent):
  - `_finalize_partial_report(welford, completed_buf, aborted_case_ids, plan, started_at) -> BenchRunReport` — pure.
  - `_next_cap_phase(phase, running_total, cap) -> CostCapPhase` — pure predicate.
  Both unit-tested in `tests/unit/test_runner_cost_cap_helpers.py`.
- **F-DP-5 (harden)** — `CostCapPhase` StrEnum (`RUNNING | APPROACHING | BREACHED`) replaces the flag-pair anti-pattern. Monotonic transitions; impossible states forbidden by `_next_cap_phase`'s structure. The single-fire WARNING is structurally pinned by monotonicity — not by a boolean flag.
- **F-DP-6 (harden)** — Structured-logging contract pinned: `structlog.get_logger("codegenie.eval.runner")`; event names `cost_cap_approaching` (WARNING) and `cost_cap_exceeded` (ERROR). Tests assert on `event` field of the structlog record.
- **F-DP-7 (harden)** — Cooperative cancellation choreography pinned in AC-6: workers check `cost_cap_event.is_set()` at TWO safe-points; external `task.cancel()` is reserved for S3-04 AC-4a's external-cancel path and is NOT how cost-cap fires.
- **F-DP-8, F-DP-9 (nits)** — `CostCap` smart-constructor and `cost_warning_thresholds: tuple[float, ...]` deferred to Notes-for-implementer with explicit rule-of-three triggers.

## Conflict resolution

One Coverage finding (F-COV-1 type) and one Consistency finding (F-CON-2 type) both addressed the same `max_cost_usd: float | None` issue. Priority order: **Consistency > Coverage > Test-Quality > Design-Patterns**. Consistency's recommendation (drop `None`, keep `float = 5.0`) wins — it conforms to the source of truth rather than introducing an unauthorized feature. Coverage's downstream recommendation ("test 0.0 / negative semantics") then layered cleanly on top: the new AC-1 raises `ValueError` for `<= 0.0`.

One Design-Patterns finding (F-DP-2: `partial_reason` discriminated field) was demoted from AC to Notes-for-implementer because: (a) it would require a wire-contract amendment to a HARDENED S1-02 model, mirroring the F-CON-3 dropped-field reasoning; (b) the rule-of-three threshold is not yet met (1 partial-reason today); (c) the goal of "single-field discriminator" is met by `complete is False` alone today.

One Consistency finding (F-CON-5: cross-process `flock`) was demoted from "add to scope" to "explicit deferral with forward-pointer." The cassette test environment is single-process; introducing the lock without a real live-mode multi-process workflow risks deadlocks in tests and ADR drift. The follow-up `S3-06b` is named in Out-of-scope so the gap is visible, not silent.

## Final story state

The rewritten story has 19 numbered ACs (vs ~10 prose bullets originally), organized into 8 sections:
- Public surface (AC-1, AC-2)
- Queue widening (AC-3)
- Cost-cap state machine (AC-4, AC-5)
- Cooperative cancellation (AC-6)
- Aggregator drains + emits `_Aborted` markers (AC-7)
- Placeholder score synthesis (AC-8, AC-9)
- Logging contract (AC-10, AC-11, AC-12)
- Boundary semantics (AC-13, AC-14)
- Audit chain integrity (AC-15, AC-16)
- CLI exit-code discriminator (AC-17)
- Tooling (AC-18, AC-19)

The TDD plan now has 12 unit tests + 6 pure-helper tests + 1 Hypothesis property test. All use `structlog.testing.capture_logs()` for structured-log assertions (not stdlib `caplog`). Cardinality checks are exact (not `>= 2`) — using a `GatedCostingSUT` for deterministic completion order. The mutation-resistant `no_cancellederror_propagates` test pins that cost-cap is cooperative, not external `task.cancel()` based.

`src/codegenie/eval/models.py` is **NOT** in Files-to-touch — the story respects S1-02's wire-contract finality.

## Verdict: HARDENED

The story is now executable. Every AC is individually verifiable; the AC set collectively guarantees the goal; the TDD plan would catch the obvious mutations (no FailureMode synthesis, no external cancel, no audit-write in execute, correct boundary `>`, single-fire WARNING via monotonicity); the implementation consumes the kernels S3-02 and S3-04 prescribed (`_Aborted` widening, no `FailureMode` synthesis); a future Phase 13 / Phase 16 partial-reason consumer has a clear rule-of-three trigger to add `partial_reason: Literal[...]`. The cross-process `flock` is explicitly deferred, not silently omitted.
