# Validation report: S5-02 — `GateRunner.run` three-retry loop + all four branches

**Validated:** 2026-05-25
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Validator agent run:** automated (story-validation-corrector scheduled task)

## Summary

S5-02 is the load-bearing "do the retry loop exactly once" story the entire phase exists to ship — the four-branch dispatch (passed / escalate / failed_unrecoverable / replan-and-continue) plus the ADR-0007 pre-execute marker ordering invariant. The draft's goal, four-branch decomposition, and step-by-step outline were structurally sound. But every block-tier finding traced back to a single root cause: **the draft was written before S1-04, S2-02, S4-05, and S5-01 reached HARDENED on 2026-05-22..2026-05-25.** As a consequence the draft asserted a synchronous `ReplanHook`, stored a sum-type `RecipeOutcome` into a `str` field, called `with_prior_attempt(outcome)` against the widened `(outcome, *, sandbox_run_id)` signature, asserted on a non-existent `RecipeApplication.transform_output` attribute, used a `MagicMock` where an `AsyncMock` is required, and leaked JSON-escape `\"` literals into the TDD plan that would have produced syntax errors before any test ran.

| Draft assumption | Reality on `master` (or HARDENED upstream story) |
|---|---|
| `ReplanHook.__call__` is sync; `replan_hook(ctx)` returns a `RecipeApplication` | S5-01 HARDENED locked `async def __call__(self, ctx: GateContext) -> RecipeOutcome`. `RecipeApplication` does not exist. Sync invocation binds a coroutine; `AttributeError` on attribute access. |
| `recipe_app.transform_output` and `recipe_app.diff` are valid | `RecipeOutcome = Applied | Skipped | NotApplicable | Failed`. `Applied` carries `transform_id`, `plugin_id`, `recipe_id`. No `.transform_output`, no `.diff`. |
| `ctx.with_prior_attempt(outcome)` | S1-04 HARDENED #5 widened the signature to `with_prior_attempt(self, outcome, *, sandbox_run_id: RunId) -> "GateContext"`. Draft's positional call `TypeError`s at runtime — `sandbox_run_id` is required keyword-only. |
| `gate.evaluate(...)` may return `GateOutcome(state="failed_unrecoverable")` | S4-05 HARDENED locked `Gate.evaluate` to `state ∈ {passed, failed_retryable, escalate}`. `failed_unrecoverable` is **runner-derived** — the runner must `model_copy(update={"state": "failed_unrecoverable"})` on the third attempt before recording. The draft AC asserted the third recorded attempt's state without specifying HOW the runner produces it. |
| `fake_ledger.attempts()` is the canonical reader | S2-02 HARDENED locked `entries() -> list[LedgerEntry]` (`PreExecuteMarker | Attempt` union). `attempts()` exists as a fake-only convenience; the production surface is `entries()`. |
| `SandboxBackendError` counts toward `max_attempts` | True, but the draft did NOT specify that the synthetic `Attempt` MUST be `record(...)`-ed BEFORE the next iteration's `record_pre_execute(...)`. S2-02 AC-OO-3 / AC-RR-5 require `_marker_pending is False` at the next marker write; without the synthetic record, iteration 2's `record_pre_execute` raises `LedgerAttemptOutOfOrder(context="record_pre_execute")` and the loop aborts at attempt 2 — never reaching `max_attempts=3`. |
| `MagicMock` is acceptable for the replan hook | `AsyncMock(spec=ReplanHook)` is required. A `MagicMock` returns a sync `MagicMock` (not a coroutine); `await self.replan_hook(ctx)` raises `TypeError: object MagicMock can't be used in 'await' expression`. |
| The TDD plan's Python code is valid as-written | Multiple test bodies contain `[\"tests\"]`, `\"r1\"`, `\"pre_execute\"` — JSON-escaped quotes leaked into the markdown. `\"` is not a valid Python escape; an executor copying verbatim would land syntax errors. |
| Same-failing-signals detector fires when `len(deque) == max_attempts` | Phase arch §Edge cases #17 says "3×". For `max_attempts=5`, the draft's check diverges from arch — should be a sliding window of size 3, regardless of `max_attempts`. |

The validator's response: **narrow every AC against the four HARDENED upstream surfaces, promote the async loop + sum-type dispatch + synthetic-marker-close to first-class ACs, rewrite the entire TDD plan with valid Python literals + AsyncMock + sum-type `match` arms + `assert_marker_ordering` ordering helper used across every branch, and pin the functional-core / imperative-shell discipline (mirroring S4-05's `_classify_retry` and S2-02's `_parse_ledger_row` precedents) as ACs rather than Refactor afterthoughts.**

The remaining slice — what S5-02 actually owns:

1. The concrete `async def run` method on a keyword-only-constructed `GateRunner` dataclass-style class.
2. Two pure module-private helpers (`_dispatch_outcome`, `_is_same_failing_signals_3x`) and a `history: deque[frozenset[SignalKind]]` of `maxlen=3`.
3. Four exit branches (passed / escalate / failed_unrecoverable / replan-and-continue) plus three error sub-cases (`SandboxBackendError` orphan-marker-close, `GateMissingRequiredSignal` structured escalation, `replan_hook` non-`Applied` variant → escalate) plus the exhaustion-with-varying-signals fallthrough → escalate.
4. ADR-0007 marker ordering invariant asserted via a shared `assert_marker_ordering(parent, expected_pairs)` helper used in EVERY branch test (Branch A, B, C, D, and the all-backend-errors path).
5. AC-INV-1 conftest-autoused metamorphic invariant: `marker_count == execute_count == attempt_record_count` at every test teardown.
6. Module purity + cold-start fence row for `codegenie.gates.runner`.
7. Two Hypothesis property tests (n-retryable-then-pass; set-equal-permutation Branch C).
8. `mypy --strict` clean module; no `Any` in the public surface; newtype identifiers (`AttemptNumber`, `RunId`, `SandboxSpecHash`, `SignalKind`) consumed throughout.

That's enough to make the executor's red-green-refactor cycle land deterministically against the four HARDENED upstream contracts.

No `RESCUE`-tier escalation: the goal text needed only minor edits (drop `RecipeApplication` wording; promote `async def`); the acceptance criteria, the implementation outline, and the TDD plan were rewritten in place to bind to the actual upstream surfaces. Every gap was patchable from the four honored ADRs plus the four HARDENED upstream reports plus the existing kernels (`transforms/outcomes.py`, `types/identifiers.py`, `gates/contract.py`, `gates/retry_ledger.py`). **Stage 3 (research) was skipped — every gap was answerable from in-repo precedents and the prior validation reports.**

## Findings by critic

### Coverage critic (15 findings: 6 block, 7 harden, 2 nit)

#### Block-tier

1. **(coverage — block) `ReplanHook` is async; runner written as sync.** Synchronous `replan_hook(ctx)` and `replan.assert_not_called()` against S5-01 HARDENED's async Protocol. **Fix:** AC-ASYNC-1..-3 promote `run` to `async def`; tests use `await runner.run(ctx)` and `AsyncMock(spec=ReplanHook)`. The repo's `asyncio_mode = "auto"` makes `@pytest.mark.asyncio` redundant.

2. **(coverage — block) `RecipeOutcome` sum-type variants are not dispatched.** AC-Branch-D asserted "ctx.transform_output is replaced with the hook's `RecipeApplication`" — type doesn't exist; `Applied` carries `(transform_id, plugin_id, recipe_id)` only. **Fix:** AC-RO-1 / -2 / -3 — `match` on variant; `Skipped|NotApplicable|Failed` → escalate; `Applied` carries forward identity-equal.

3. **(coverage — block) `with_prior_attempt` requires `sandbox_run_id` kwarg.** S1-04 HARDENED #5 widened. **Fix:** AC-WPA-1 / -2 — single atomic composite `ctx.with_prior_attempt(outcome, sandbox_run_id=run.run_id).model_copy(update={...})`.

4. **(coverage — block) `failed_unrecoverable` materialization unspecified.** `StrictAndGate.evaluate` returns 3 states; runner must derive the fourth. **Fix:** AC-DERIVE-1 — runner does `model_copy(update={"state": "failed_unrecoverable", ...})` BEFORE the third `record(...)`.

5. **(coverage — block) Orphan pre-execute marker on `SandboxBackendError` corrupts the ledger.** Without an immediate synthetic `record(...)`, the next iteration's `record_pre_execute` raises `LedgerAttemptOutOfOrder`. **Fix:** AC-BACKEND-CLOSE pins the close-the-marker invariant.

6. **(coverage — block) Synthetic `Attempt.sandbox_run_id` on backend error unspecified.** **Fix:** AC-SYN-1 — `RunId(f"backend-error-{attempt_id:04d}")`.

7. **(coverage — block) Same-signature detector window vs hard floor.** Diverges for `max_attempts != 3`. **Fix:** AC-SLIDE-1 — sliding window of size 3 regardless of `max_attempts`.

8. **(coverage — block) TDD-plan code contains escaped quotes.** **Fix:** AC-PLAIN-PY-1 asserts `ast.parse(...)` on the test file; TDD plan rewritten with proper Python literals.

#### Harden-tier

9. **(coverage — harden) `GateMissingRequiredSignal` synthetic-outcome `signals` payload unpinned.** **Fix:** AC-MR-1 — `signals=ObjectiveSignals()` (or collected-so-far); assert on structured `outcome.failing_signals`, not substring.

10. **(coverage — harden) `max_attempts > 1024` not rejected.** `AttemptNumber` bound is 1..1024. **Fix:** AC-CON-1 parametrizes the upper bound + non-int rejection.

11. **(coverage — harden) Exhaustion + varying signals branch implicit.** **Fix:** AC-EX-1 — explicit `escalate` return when no Branch C and `max_attempts` reached.

12. **(coverage — harden) `structlog` event field set unpinned.** **Fix:** AC-OBS-1 — per-event field-set assertion via `structlog.testing.capture_logs()`.

13. **(coverage — harden) Pre-execute ordering only tested on Branch D.** **Fix:** AC-PEM-2 — `assert_marker_ordering(parent, expected_pairs)` invoked in Branch A, C, D, AND all-backend-errors.

#### Nit

14. **(coverage — nit) `fake_ledger.count_attempts()` / `attempts()` interfaces not pinned.** **Fix:** Notes-for-implementer + AC-LE-1 — fakes mirror production `entries()`; convenience helpers documented.

15. **(coverage — nit) `AttemptNumber` vs raw int `attempt`.** **Fix:** AC-AT-STAMP-1 covers the stamp; AC-NT-1 covers the newtype consumption.

### Test Quality critic (16 findings: 9 block, 6 harden, 1 nit)

#### Block-tier

1. **(test-quality — block) TDD-plan code is invalid Python.** Escaped quotes throughout. **Fix:** rewrite + AC-PLAIN-PY-1.

2. **(test-quality — block) `replan_hook=MagicMock()` for an async hook.** **Fix:** AC-AM-1 — `AsyncMock(spec=ReplanHook)` everywhere; assertions use `await_count`, `await_args.kwargs`.

3. **(test-quality — block) `_fake_recipe_app()` / `new_recipe.transform_output` invented.** **Fix:** AC-RO-1 — replace with `_applied()` factory; test asserts identity on the `Applied` instance carried through `fake_spec_builder.for_gate.call_args_list[1]`.

4. **(test-quality — block) Branch C `failing_signals` order-sensitivity untested.** **Fix:** AC-SET-1 — parametrize across set-equal permutations.

5. **(test-quality — block) `count_attempts()` / `attempts()` are invented helpers.** **Fix:** AC-LE-1 — fakes mirror real `entries()`; tests filter `isinstance(e, Attempt)`.

6. **(test-quality — block) Pre-execute ordering not asserted across all paths.** **Fix:** AC-PEM-2 — shared helper used by every test.

7. **(test-quality — block) Branch D `attempt=2` baked into the fake.** **Fix:** AC-AT-STAMP-1 — runner stamps; fake records `last_eval_attempts: list[int]`.

8. **(test-quality — block) No replan call-count assertion in Branch C.** Catches the `attempt <= max_attempts` off-by-one. **Fix:** AC-RC-1 — `replan.await_count == 2` in Branch C.

9. **(test-quality — block) `outcome.summary.startswith("missing_required_signal")` substring assertion.** **Fix:** AC-MR-1 — structured `outcome.failing_signals` assertion.

#### Harden-tier

10. **(test-quality — harden) No property-based test over retryable-then-pass.** **Fix:** AC-PROP-1.

11. **(test-quality — harden) Missing metamorphic invariant.** **Fix:** AC-INV-1 — conftest-autoused.

12. **(test-quality — harden) `max_attempts < 1` parametrization too narrow.** **Fix:** AC-CON-1 / -2 parametrize upper bound + non-int.

13. **(test-quality — harden) No test for `Failed` `RecipeOutcome`.** **Fix:** AC-RF-1.

14. **(test-quality — harden) `gates.runner.exit` field set unpinned.** **Fix:** AC-OBS-1.

15. **(test-quality — harden) No AST-fence test for `runner.py`.** **Fix:** AC-PURITY-1 / -2, AC-NT-1, AC-FENCE-1 — new file `tests/gates/test_runner_purity.py`.

#### Nit

16. **(test-quality — nit) `last_ctx` invented helper.** **Fix:** Notes-for-implementer + AC-RO-3 — assert via `MagicMock.call_args_list` against the spec-builder Port.

### Consistency critic (14 findings: 5 block, 7 harden, 2 nit)

#### Block-tier

1. **(consistency — block) `replan_hook` invocation synchronous; S5-01 HARDENED locks async.** **Fix:** AC-ASYNC-1..-3.

2. **(consistency — block) `RecipeOutcome` stored into `str`-typed `transform_output` field.** **Fix:** AC-RO-3 — runner does NOT coerce; field carries the `Applied` instance until Phase 3 widens the type (Out-of-scope row added).

3. **(consistency — block) `with_prior_attempt(outcome)` omits required `sandbox_run_id` kwarg.** **Fix:** AC-WPA-1.

4. **(consistency — block) `SandboxBackendError` orphans `_marker_pending` flag.** **Fix:** AC-BACKEND-CLOSE.

5. **(consistency — block) Tests use `fake_ledger.attempts()` but S2-02 locked `entries()`.** **Fix:** AC-LE-1 — fakes mirror `entries()`; convenience helpers documented as filters.

#### Harden-tier

6. **(consistency — harden) `failed_unrecoverable` runner-derived, not gate-returned.** **Fix:** AC-DERIVE-1.

7. **(consistency — harden) `failing_signals` recorded order must be sorted.** **Fix:** AC-SORT-1.

8. **(consistency — harden) `ctx.transform_output` Phase 3 widening dependency.** **Fix:** Notes-for-implementer + Out-of-scope row.

9. **(consistency — harden) `Depends on` omits S1-04.** **Fix:** Added S1-04 explicitly to dependency list.

10. **(consistency — harden) New submodule `gates/runner.py` needs fence row.** **Fix:** AC-FENCE-1.

11. **(consistency — harden) `Attempt` chain fields populated by ledger, not runner.** **Fix:** AC-CHAIN-1 — runner builds without `prev_hash`/`chain_hash`; `ledger.record` finalizes.

12. **(consistency — harden) `with_prior_attempt` + `model_copy` atomic.** **Fix:** AC-WPA-1 — single statement.

#### Nit

13. **(consistency — nit) Production ADR-0014 reference verified to exist.** No edit.

14. **(consistency — nit) `started_at` kwarg form preference.** Notes — pin kwarg for timezone-awareness intent at the call site.

### Design Patterns critic (15 findings: 0 block, 11 harden, 3 note, 1 nit)

#### Harden-tier

1. **(design — harden) `_dispatch_outcome` purity pinned as AC.** **Fix:** AC-PH-1.

2. **(design — harden) `_is_same_failing_signals_3x` extracted as separate pure helper.** **Fix:** AC-PH-2.

3. **(design — harden) `history` deque element type pinned.** **Fix:** AC-PH-3 — `deque[frozenset[SignalKind]]` with `maxlen=3`.

4. **(design — harden) Async surface declaration.** **Fix:** AC-ASYNC-1 + Notes — only `await` site in runner.

5. **(design — harden) Keyword-only constructor + max_attempts bound.** **Fix:** AC-CTOR-1 + AC-CON-1.

6. **(design — harden) `RecipeOutcome` sum-type dispatch via `match`.** **Fix:** AC-RO-1 — AST scan asserts `Match` node present.

7. **(design — harden) Module purity invariant.** **Fix:** AC-PURITY-1 — composition-root isolation.

8. **(design — harden) Primitive obsession on identifiers.** **Fix:** AC-NT-1 — newtypes consumed.

9. **(design — harden) `GateOutcome.state` rewrite via `model_copy`.** **Fix:** AC-DERIVE-1 + Notes — never construct fresh `GateOutcome` mid-loop.

10. **(design — harden) `structlog` emit purity.** **Fix:** AC-PH-4 — emits live in `run()` only.

11. **(design — harden) Test invents `fake_spec_builder.last_ctx`.** **Fix:** AC-RO-3 — assert via `call_args_list` on the Port.

#### Note-only

12. **(design — note) `_synthetic_error_outcome` rule-of-two — inline both call sites.** **Fix:** Notes-for-implementer.

13. **(design — note) `_run_one_attempt` extraction option.** **Fix:** Notes-for-implementer as a future refactor.

14. **(design — note) Hexagonal ports summary.** **Fix:** Notes-for-implementer.

#### Nit

15. **(design — nit) No `@register_runner` premature abstraction. Good — deferred until N=3.** **Fix:** Notes-for-implementer pins the deferral.

## Conflict resolution

- **Coverage wants a `Failed` replan_hook test (AC-RF-1); Test Quality wants the same; Consistency confirms S5-01 HARDENED ships `Failed` as a `RecipeOutcome` variant.** Three critics align. AC-RF-1 added; no conflict.
- **Design Patterns wants `_run_one_attempt` extraction; Coverage / Consistency don't require it.** Rule 2 — `_run_one_attempt` adds one helper for ordering-as-structure. Surfaced in Notes-for-implementer as a future refactor option, NOT promoted to AC. The `assert_marker_ordering` ordering helper covers the test side.
- **Coverage wants `last_ctx` recorder; Test Quality + Design Patterns want `call_args_list`.** Coverage's concern is "the runner threaded the right ctx into the next spec build"; the `call_args_list` approach answers it equivalently without inventing a fake-only attribute. Design Patterns + Test Quality win; Notes-for-implementer explains the rationale.
- **Coverage's `max_attempts > 1024` rejection; Design Patterns' AttemptNumber bound consumption.** Same fix — AC-CON-1 covers both critics.

## Stage 3 — research

**Skipped.** Every gap was answerable from in-repo precedents:

- S1-04 HARDENED (`ReplanHook` Protocol shape, `AttemptNumber` bound, `with_prior_attempt` widening, frozen Pydantic discipline, `Attempt`/`GateOutcome` shapes)
- S2-02 HARDENED (`record_pre_execute` 3-arg signature, `_marker_pending` recovery, `entries()` reader, `LedgerAttemptOutOfOrder(context=...)` discriminator)
- S4-05 HARDENED (3-state `Gate.evaluate` return; `failed_unrecoverable` is runner-derived; `failing_signals` sorted; functional core / imperative shell precedent `_classify_retry`)
- S5-01 HARDENED (async `ReplanHook` returning `RecipeOutcome` sum type; identity-faithful threading via `is`-equality spies; AsyncMock(spec=...) pattern; AST-fence module-isolation pattern)
- S2-01 HARDENED (pure module-level helpers `_canonical_json` / `_compute_chain_hash` / `_recover_chain_state` — the functional-core pattern S5-02 inherits)
- CLAUDE.md "Cassette workflow" (existing cassette infrastructure — explicitly out of scope here, deferred to S5-05)
- CLAUDE.md "tagged union > anaemic dict" (the `match` on `RecipeOutcome` discipline)
- CLAUDE.md "Structural defenses live under `tests/fence/`" (new submodule = new fence row)

No external canonical pattern was needed. The four HARDENED upstream stories + Phase 5 arch + S2-01 / S2-02's pure-helper-extraction precedent + CLAUDE.md's sum-type discipline gave every gap a one-step fix.

## Edits applied to `S5-02-gate-runner-retry-loop.md`

### 1. Status + Depends-on lines
- Before: `**Status:** Ready` / `**Depends on:** S2-02, S4-05, S5-01`
- After: `**Status:** Ready (HARDENED 2026-05-25)` / `**Depends on:** S1-04 (...), S2-02 (...), S4-05 (...), S5-01 (...)` with per-dep note of the specific locked surface this story consumes.

### 2. Validation notes block
Added 29-point Validation notes block under Status / Depends-on / ADRs honored. Every block-tier finding gets its own numbered note with the source HARDENED report cited.

### 3. Goal rewrite
- Before: prose about a "plain `for attempt in 1..max_attempts` loop" with no mention of `async` or `RecipeOutcome` variant dispatch.
- After: explicit `async def run`, single `await` site, `_dispatch_outcome` pure helper, four mutually exclusive branches with `failed_unrecoverable` runner-derived, `_marker_pending` closure on every error path.

### 4. Acceptance criteria — replaced the 13-AC draft with an 11-section hardened set (~50 ACs)
Headers: **A.** Constructor + signature | **B.** Pre-execute marker ordering invariant | **C.** The four exit branches | **D.** `ReplanHook` async + `RecipeOutcome` sum-type dispatch | **E.** `with_prior_attempt` + ctx threading | **F.** Synthetic outcomes for error paths | **G.** Outcome derivation discipline (frozen models, sum types) | **H.** Functional core / imperative shell | **I.** Module purity + fence rows | **J.** Observability | **K.** Property-based + coverage. Every AC is observable; every observable assertion has a paired test in the rewritten TDD plan.

### 5. Implementation outline rewrite
- Replaced the 6-step prose outline with a numbered 7-step outline that names the `async def run` declaration, the two pure helpers, the `history: deque[frozenset[SignalKind]]` with `maxlen=3`, the `match` on `RecipeOutcome` for replan dispatch, the synthetic-attempt-record-before-next-iteration for `SandboxBackendError`, the `model_copy` derivations for state stamping, and the single atomic `ctx` swap.

### 6. TDD plan rewrite
Replaced the 9-test draft (with escaped-quote leakage) with a 17-test plan in valid Python: Branch A, B, C (parametrized set-equal), C-sliding-window-max-5, D (with identity-check on `call_args_list`), non-Applied-variant (parametrized over Skipped/NotApplicable/Failed), backend-error-closes-marker, missing-required-signal, no-replan-escalates, exhaustion-with-varying-signals, constructor-bounds (parametrized), runner-stamps-attempt, structlog-events, three unit tests for `_is_same_failing_signals_3x` purity, `_dispatch_outcome` purity, and a Hypothesis property test (`AC-PROP-1`). Plus an autouse fixture for `AC-INV-1` metamorphic invariant.

### 7. Files to touch
Added `tests/gates/test_runner_purity.py` (AST-walk fences) and `tests/fence/test_runner_cold_start.py` (AC-FENCE-1) as separate files. Confirmed `gates/errors.py` already houses `GateMissingRequiredSignal` from S1-04 / S4-05.

### 8. Out-of-scope expanded
Added Phase-3 typed widening of `GateContext.transform_output` as an explicit out-of-scope row. Branch D's `model_copy` writes the `Applied` instance into a placeholder-typed field; the runner does NOT coerce per S5-01 HARDENED AC-FWD-1.

### 9. Notes for the implementer rewrite
Eight notes covering: pre-execute marker as the load-bearing assertion; `with_prior_attempt` + `model_copy` atomic composition; async/sync boundary; `RecipeOutcome` `match` discipline; `GateOutcome.model_copy` for all state derivations; `SandboxBackendError` synthetic `ObjectiveSignals()`; sliding-window detector; synthetic-error-outcome rule-of-two deferral; cost/metrics/trace deferral; static fence test; hexagonal ports summary; `_dispatch_outcome` closed-sum dispatch tag and Open/Closed at the dispatch boundary.

## Verdict

**HARDENED.** Story is now ready for `phase-story-executor`.

The four-branch dispatch is preserved with every branch backed by an observable AC. The ADR-0007 pre-execute marker ordering is asserted across every branch via a shared helper, plus a conftest-autoused metamorphic invariant catches whole drift classes silently. The async/sync boundary is sharp (`replan_hook` is the only `await` site). The `RecipeOutcome` sum-type dispatch uses `match` (CLAUDE.md "tagged union > anaemic dict"). The `failed_unrecoverable` derivation is pinned as a `model_copy` operation, not a fresh `GateOutcome` construction. The `_marker_pending` recovery hole on `SandboxBackendError` is closed by an explicit AC. The functional-core / imperative-shell split (two pure helpers + thin impure `run`) mirrors S4-05 and S2-02 precedents. Module purity + cold-start fence rows are structurally enforced.

Executor preconditions:
- S1-04 GREEN (ships `Gate`, `GateContext` with `with_prior_attempt(outcome, *, sandbox_run_id)`, `GateOutcome`, `AttemptNumber`, `Attempt`, `ReplanHook` Protocol returning `RecipeOutcome`)
- S2-02 GREEN (ships `record_pre_execute`, `_marker_pending` recovery, `entries()` reader, `LedgerAttemptOutOfOrder(context=...)`)
- S4-05 GREEN (ships `StrictAndGate.evaluate` returning 3-state `GateOutcome`)
- S5-01 GREEN (ships `make_orchestrator_replan_hook` factory + async-aware contract test)
- `src/codegenie/gates/runner.py` does not yet exist; will be created.
- `tests/fence/test_runner_cold_start.py` row may or may not exist; AC-FENCE-1 covers either.
