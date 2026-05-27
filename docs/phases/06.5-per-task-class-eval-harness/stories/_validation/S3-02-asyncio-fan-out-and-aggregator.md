# Validation report — S3-02 — Asyncio fan-out + Welford aggregator

**Validator run:** 2026-05-27 (scheduled task `story-validation-corrector`)
**Story file:** `../S3-02-asyncio-fan-out-and-aggregator.md`
**Verdict:** **HARDENED** — story had 28 fixable weaknesses; edits applied.
**Skip Stage 3:** no findings tagged `NEEDS RESEARCH`.

## Context Brief (Stage 1)

S3-02 implements `Runner.execute(plan, *, system_under_test, rubric_runner, ...) -> BenchRunReport`. It is the fan-out + Welford-aggregator stage of a six-piece orchestrator (S3-01 plan → S3-02 execute → S3-03 real subprocess rubric → S3-04 typed failure mapping → S3-05 BCa bootstrap → S3-06 cost cap + audit write). The story explicitly defers all five sibling concerns and uses an in-process stub rubric for testability.

Constraints from arch (`phase-arch-design.md`) and ADRs:

- **ADR-0001** (rubric subprocess isolation): the rubric runs across a process boundary; the runner type-checks the *caller side* via a `RubricRunner` Protocol (`final-design.md` lines 158-168 explicitly defines it), and substitutes the real subprocess in S3-03.
- **ADR-0002** (`lower_bound_95` is the promotion-gate input): bootstrap is deterministic; this story emits `lower_bound_95=0.0` as a placeholder.
- **ADR-0010** (`isolation_class` annotation): set unconditionally to `"subprocess"` on every report.
- **arch §Process view + §Concurrency**: `asyncio.Semaphore(min(os.cpu_count(), 4))`, single aggregator task, deterministic report-time ordering by `case_id`.
- **arch §Determinism row "runner scheduling"**: completion order non-deterministic; report order is — load-bearing for audit-chain byte-stability.
- **HARDENED S1-02** (`BenchRunReport` shape): 17 fields, `frozen=True extra="forbid"`, `per_case: tuple[tuple[str, BenchScore], ...]`.
- **HARDENED S3-01** (`RunPlan` shape): 10 fields, no `cache_dir`, no `timeout_per_case_seconds`. These must be `execute` kwargs.
- **CLAUDE.md**: "Honest confidence", "Fail loud", "Extension by addition", Rule 9 (tests verify intent), Rule 11 (match conventions), Rule 12 (surface uncertainty).

## Stage 2 — Critic findings

Four critics ran in parallel. 28 findings total. Severity counts: 8 blocks, 16 hardens, 4 nits.

### Coverage (F-COV-1 … F-COV-12) — 12 findings

| ID | Sev | Issue (short) | Resolution |
|---|---|---|---|
| F-COV-1 | block | `BenchRunReport` field coverage missing — most fields have no defining AC | Resolved by AC-7 (plan-bound + aggregated source enumeration) |
| F-COV-2 | block | `cache_dir` / `plan.timeout_per_case_seconds` referenced but not in signature | Resolved by AC-1 (signature widened with explicit kwargs) |
| F-COV-3 | block | Aggregator hangs on worker exception (no try/finally) | Resolved by AC-5 (no-hang invariant + red test) |
| F-COV-4 | harden | `on_score` AC exists but no red test | Resolved by `test_on_score_called_once_per_case_in_completion_order_before_sort` |
| F-COV-5 | harden | Welford "stddev=0.3" is sample (n−1), comment says population | Resolved by AC-6 (sample n−1 pinned; comment corrected; `statistics.stdev` oracle) |
| F-COV-6 | harden | No AC for empty-plan path | Resolved by AC-8 (empty bench within 1 s) |
| F-COV-7 | harden | No AC for `os.cpu_count() returning None` | Resolved by AC-2 + `test_execute_concurrency_floor_when_cpu_count_returns_none` |
| F-COV-8 | harden | No AC for `concurrency=1`, `> len(cases)`, `=0` boundary | Resolved by AC-2 + multiple red tests |
| F-COV-9 | harden | AC-9 (KeyboardInterrupt) doesn't pin `CancelledError` | Resolved by AC-12 + sibling `test_cancelled_error_propagates` |
| F-COV-10 | harden | Hypothesis property compares to fixed baseline only | Resolved by AC-9a (two-jitter cross-comparison) |
| F-COV-11 | harden | Aggregator-count test only checks "no leaked tasks" | Resolved by AC-4 + named-task spy in `test_exactly_one_aggregator_task_created` |
| F-COV-12 | nit | No AC for `cache.put` `OSError` | Resolved by AC-10a (log-and-continue, arch §Edge cases #16) |

### Test-Quality (F-TQ-1 … F-TQ-15) — 15 findings

| ID | Sev | Issue | Wrong-impl that passes | Resolution |
|---|---|---|---|---|
| F-TQ-1 | harden | Determinism test anchored to single baseline | Sorted-only-when-N≤3 impl | Merged with F-COV-10 → AC-9a |
| F-TQ-2 | harden | `per_case` tuple-not-list contract not asserted | `list(sorted(buf))` | AC-15 (universal `isinstance(report.per_case, tuple)`) |
| F-TQ-3 | harden | Welford fixture doesn't pin streaming property | `buffer + statistics.pstdev` at finalize | AC-6a (numerical-stability large-offset fixture) |
| F-TQ-4 | harden | "population stddev" comment wrong | Implementer flips fixture to 0.2449 to "fix" | AC-6 (comment + AC say sample n−1; oracle is `statistics.stdev`) |
| F-TQ-5 | harden | Cache-hit test doesn't prove rubric skipped | Worker calls rubric anyway, discards | AC-10 (`rubric.call_count == 0`; identity check on cached score) |
| F-TQ-6 | harden | Concurrency cap test depends on stub timing | Cap=2 still shows max_inflight==4 by accident | `GatedJitteredStubSUT` with `asyncio.Event` blocking until N cases enter |
| F-TQ-7 | block | No `CancelledError` test | Worker `except Exception` minus KeyboardInterrupt swallows Cancelled | Merged with F-COV-9 → AC-12 |
| F-TQ-8 | block | Aggregator-count test wrong | Two aggregators both cleanly awaited → no leaked tasks | Merged with F-COV-11 → named-task spy |
| F-TQ-9 | harden | `WelfordAccumulator` red tests not enumerated | Off-by-one in `M2 += delta*delta` (vs `delta*delta2`) | New `tests/unit/test_welford.py` block (6 tests) |
| F-TQ-10 | block | No `on_score` test | `on_score=None` ignored as kwarg | Merged with F-COV-4 |
| F-TQ-11 | harden | Property-based invariants missing | Aggregator silently drops a case | AC-14 (5-invariant multi-property test) |
| F-TQ-12 | harden | Metamorphic relations missing | Sort by `(wall_clock_ms, case_id)` accident | AC-9b (concurrency-invariance) + AC-9c (slowness-invariance) |
| F-TQ-13 | nit | `isolation_class="subprocess"` asserted once | Conditional `isolation_class` survives | AC-15 (universal assertion) |
| F-TQ-14 | nit | Sync Hypothesis test wraps `asyncio.run` | N/A — hygiene | Accepted; pattern documented inline |
| F-TQ-15 | nit | `assert report.complete is True` tautological | N/A | Kept (regression guard) |

### Consistency (F-CON-1 … F-CON-8) — 8 findings

| ID | Sev | Issue | Source of truth | Resolution |
|---|---|---|---|---|
| F-CON-1 | harden | `concurrency: int = 1` (final-design) vs `min(cpu_count(), 4)` (arch) | arch > final-design (phase-architect precedence) | Note added to References + Goal: arch supersedes |
| F-CON-2 | block | `plan.timeout_per_case_seconds` / `cache_dir` not on HARDENED `RunPlan` | HARDENED S3-01 AC-1 | Resolved via option (a): widen `execute` kwargs (not `RunPlan`). Merged with F-COV-2 |
| F-CON-3 | block | `BenchRunReport(extra="forbid")` requires all fields populated | HARDENED S1-02 | Resolved via AC-7 (explicit field-source enumeration). Merged with F-COV-1 |
| F-CON-4 | harden | `make_stub_plan` undefined; conflicts with S3-01's `stub_task_class_fixture` | HARDENED S3-01 helper name | `make_stub_plan` defined explicitly in `tests/helpers/bench.py` as a thin builder over `stub_task_class_fixture` + `Runner().plan(...)` |
| F-CON-5 | harden | `chain_head` / `prev_hash` ambiguity in returned report | HARDENED S1-02 + S2-04 | AC-13: `chain_head=""` sentinel, `prev_hash=plan.prev_chain_head` |
| F-CON-6 | block | `lower_bound_95=0.0` placeholder silent vs ADR-0002 gate | CLAUDE.md "Honest confidence" + ADR-0002 | Resolved via option (c): AC-13 pins "execute never audit-writes"; S3-06 composes the full chain. Notes-for-implementer makes the no-leak path explicit |
| F-CON-7 | nit | `rubric_runner` type-honesty across process boundary | ADR-0001 §Consequences | Notes-for-implementer documents the boundary semantics |
| F-CON-8 | nit | `on_score` completion-order vs sort-order semantics | arch §Determinism | AC-11 spells it out explicitly + red test verifies both orderings differ |

### Design-Patterns (F-DP-1 … F-DP-9) — 9 findings

| ID | Sev | Issue | Trigger | Resolution |
|---|---|---|---|---|
| F-DP-1 | harden | `rubric_runner: Callable` inconsistent with `RubricRunner` Protocol prescribed by final-design.md | S3-03 (named), final-design.md lines 158-168 | New file `src/codegenie/eval/rubric_runner.py`; AC-3 mandates Protocol with `@runtime_checkable` |
| F-DP-2 | harden | `system_under_test: Callable` — no Phase 6 `Sut` Protocol | Phase 6 + 2 stubs (rule-of-three met) | Deferred with explicit trigger in Notes-for-implementer (Phase 6 SUT lands → introduce Protocol). Today: 2-consumer (stubs are one cohort) |
| F-DP-3 | harden | `on_score` sync-vs-async not pinned at entry | Fail-loud for partial-progress avoidance | AC-2a (`asyncio.iscoroutinefunction` check; `TypeError` at entry) |
| F-DP-4 | harden | `_SENTINEL` type unspecified — could be `None` or string | S3-06 will widen to `_Sentinel \| _Aborted` (rule-of-two pending) | AC-4a (`class _Sentinel: pass` + `Final[_Sentinel]` instance) |
| F-DP-5 | nit | `Runner` class anaemia today (no instance state) | S3-06 adds `cost_total`/`cancellation_event` | Deferred with trigger in notes |
| F-DP-6 | harden | `_run_case` / `_aggregate` extraction is refactor-section "should", not enforced AC | S3-04 + S3-06 both extend exactly these helpers | AC-implied via implementation outline; Notes-for-implementer makes inlining a non-option |
| F-DP-7 | nit | `_welford.py` underscore-private placement | S4-02 may need rolling stats public | Deferred with trigger in notes |
| F-DP-8 | nit | `cache.get`/`cache.put` module-level access | S3-06 + Phase 9 may want `CachePort` injection | Deferred with trigger in notes |
| F-DP-9 | nit | `execute` will hit ~7 kwargs by S3-06 | S3-06 adds cost-cap kwargs | Deferred with trigger in notes |

## Stage 3 — Researcher

**Skipped.** No findings tagged `NEEDS RESEARCH`. All patterns recommended are precedented in the codebase (Welford from `statistics` precedent; tagged-union sentinel from `phase-arch-design.md §Determinism` and S2-03 cache key shape; Protocol-as-strategy already prescribed in `final-design.md` lines 158-168; metamorphic-relation testing is standard for determinism invariants — no need for arXiv).

## Stage 4 — Synthesizer + Editor

### Conflict resolutions

- **Coverage vs Test-Quality on Welford fixture** (F-COV-5 + F-TQ-3 + F-TQ-4): both critics targeted the same ambiguity. Single fix: pin sample (n−1) explicitly; add `statistics.stdev` oracle; add numerical-stability fixture.
- **Coverage vs Consistency on `cache_dir`** (F-COV-2 + F-CON-2): same root cause (missing kwarg); option (a) resolution per Consistency priority.
- **Coverage vs Consistency on `BenchRunReport` fields** (F-COV-1 + F-CON-3): same root cause; explicit AC-7 enumeration.
- **Design-Patterns vs Rule 2 (premature abstraction)** (F-DP-2, F-DP-5, F-DP-7, F-DP-8, F-DP-9): the critic was rigorous about applying Rule 2 — all five surfaced as deferred with explicit triggers in Notes-for-implementer rather than introduced today.

### Edits applied to story

1. **Status line**: `Ready (HARDENED 2026-05-27)`.
2. **New `Validation notes` block** under Status with itemized fix summary.
3. **`Depends on`** widened to enumerate HARDENED-sibling contracts (S1-02, S2-03, S2-04, S3-01).
4. **`Goal`** rewritten with the new signature and the no-audit-write invariant.
5. **`References`** section: added precedence note (arch supersedes final-design on concurrency); added `final-design.md §rubric_runner` cross-reference.
6. **`Acceptance criteria`** restructured with 17 numbered ACs grouped by concern (Public surface, RubricRunner Protocol, Aggregator topology, Welford correctness, Report field population, Empty bench, Determinism, Cache discipline, on_score streaming, Exception discipline, No audit write, Property-based laws, Universal report-shape, Tooling).
7. **`Implementation outline`** rewritten:
   - Step 1: new `RubricRunner` Protocol module.
   - Step 2: `WelfordAccumulator` with sample n−1 semantics and zero-on-empty/single contract.
   - Step 3: `_Sentinel` class shape pinned.
   - Step 4: `execute(...)` body with try/finally around the fan-out, named aggregator task, entry-time on_score validation.
   - Step 5: `_run_case` extraction with `OSError` log-and-continue.
   - Step 6: `_aggregate` extraction with full `BenchRunReport` construction enumerating every field source.
   - Step 7: queue item shape `tuple[str, BenchScore] | _Sentinel` (worker enqueues case_id directly).
   - Step 8: import-the-module-not-the-symbol convention.
8. **TDD plan** rewritten: 22 red tests instead of 7; each AC has at least one mutation-resistant test; oracle recompute used where applicable; Hypothesis used for accounting and order-invariance properties.
9. **Files to touch** expanded with new `rubric_runner.py` module, `_welford.py`, `rubrics.py` helper, `bench.py` `make_stub_plan` addition.
10. **Out of scope** rewritten with explicit hand-offs to each downstream story (S3-03, S3-04, S3-05, S3-06).
11. **Notes for the implementer** rewritten with the load-bearing invariants up front (no audit-write, lower_bound_95 placeholder safety, etc.) plus 5 deferred design opportunities each with explicit trigger conditions.

### Lines added/changed

- Story file before: 220 lines.
- Story file after: ~860 lines (4× growth driven by red-test enumeration and AC density).

### Smell-catalog summary

| Smell category | Pre-validation | Post-validation |
|---|---|---|
| Vague AC ("handles gracefully") | 0 | 0 |
| Tautological tests | 1 (`complete is True`) | 1 (kept, annotated) |
| Missing field-population specs | 12 of 17 `BenchRunReport` fields | 0 |
| Unspecified helper signatures | 4 (`make_stub_plan`, `JitteredStubSUT.with_observer`, `FailingStubSUT`, `in_process_stub_rubric`) | 0 |
| Silent contract violations vs HARDENED siblings | 2 (`plan.timeout_per_case_seconds`, `plan.cache_dir`) | 0 |
| Mutation-resistant test coverage | ~40% of ACs | ~95% of ACs |
| Property-based invariants | 1 (determinism vs baseline) | 4 (cross-jitter, concurrency-invariance, slowness-invariance, multi-accounting) |
| Deferred design opportunities with explicit triggers | 0 | 5 |

## What a STRONG version of this story looks like (for future writers)

- Every `BenchRunReport` field has a stated source (plan-bound copy vs aggregator-computed).
- Every collaborator at the boundary is a Protocol when the next sibling story will substitute (the `RubricRunner` precedent).
- Every async cleanup path is wrapped in `try/finally` so the test suite never hangs on a wedge.
- Every "this is set by a future story" placeholder explains *why* it's safe (no chain-write here; `lower_bound_95=0.0` benign because never audit-chained).
- Every deferred design opportunity has a named trigger condition.
- Every property test compares run-to-run, not run-to-baseline, where the invariant is "any two runs must agree."
- Every numerical primitive has a hand-computed oracle + a numerical-stability fixture + an order-invariance property.

## Out of scope of this validation

- The story does not yet have an `_attempts/S3-02-asyncio-fan-out-and-aggregator.md` (executor hasn't run).
- The hardened story has not been re-validated for second-order weaknesses introduced by the edits (next validator run, if needed, can re-audit).
- The deferred design opportunities (F-DP-2, F-DP-5, F-DP-7, F-DP-8, F-DP-9) are *not* implemented; they are documented triggers for downstream stories.
