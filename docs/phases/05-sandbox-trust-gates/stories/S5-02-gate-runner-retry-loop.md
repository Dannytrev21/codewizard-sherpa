# Story S5-02 — `GateRunner.run` three-retry loop + all four branches

**Step:** Step 5 — GateRunner three-retry loop + Phase 4 replan_hook integration
**Status:** Ready (HARDENED 2026-05-25)
**Effort:** L
**Depends on:** S1-04 (`Gate` ABC + `GateContext.with_prior_attempt(outcome, *, sandbox_run_id: RunId)` + `GateOutcome` + `AttemptNumber` + `ReplanHook` Protocol + frozen `Attempt`), S2-02 (`record_pre_execute` + `_marker_pending` recovery + `entries() -> list[LedgerEntry]`), S4-05 (`StrictAndGate.evaluate` returns `state ∈ {passed, failed_retryable, escalate}` — `failed_unrecoverable` is **runner-derived**), S5-01 (`ReplanHook` is **`async def`** returning `RecipeOutcome` sum type via `make_orchestrator_replan_hook` factory)
**ADRs honored:** ADR-0001, ADR-0007, ADR-0014 (phase) ; production ADR-0014 (three-retry default)

## Validation notes — what changed during hardening (2026-05-25)

Four-critic pass (coverage / test-quality / consistency / design-patterns). Verdict: **HARDENED**. The draft's goal + scope + 4-branch decomposition were sound, but every block-tier finding traced to a single root cause: the draft was written **before** S1-04, S2-02, S4-05, and S5-01 reached HARDENED on 2026-05-22..2026-05-25. As a consequence the draft asserted a synchronous Protocol against the now-async `ReplanHook`, stored a sum-type `RecipeOutcome` into a `str` field, called `with_prior_attempt(outcome)` against the widened `(outcome, *, sandbox_run_id)` signature, and emitted invalid Python in the TDD plan via leaked JSON escapes. Headline edits — every one would have caught a structurally-wrong implementation that the executor's validator would have missed:

1. **(consistency / coverage — block) `ReplanHook` is `async def`.** S5-01 HARDENED locked `ReplanHook.__call__` as `async def __call__(self, ctx: GateContext) -> RecipeOutcome`. Draft outline step 7 calls `self.replan_hook(ctx)` synchronously, which binds a coroutine and `AttributeError`s on attribute access. Fix: `GateRunner.run` promoted to `async def`; the loop `await`s the hook; tests use `AsyncMock(spec=ReplanHook)` not `MagicMock`. The repo's `asyncio_mode = "auto"` makes `@pytest.mark.asyncio` redundant. AC-ASYNC-1..-3 pin the surface.
2. **(consistency / coverage — block) `RecipeOutcome` is a sum type — `Applied | Skipped | NotApplicable | Failed`.** Draft tested `new_recipe.transform_output` and `recipe_app.diff`, neither of which exist on any variant. `Applied` has `transform_id`, `plugin_id`, `recipe_id`. Fix: AC-RO-1 (`match` on variant — CLAUDE.md "tagged union > anaemic dict"); AC-RO-2 (`Skipped | NotApplicable | Failed` from `replan_hook` → runner escalates without further retries); AC-RO-3 (replan-applied path carries the `Applied` instance forward unchanged — runner does NOT unpack into a `str` field).
3. **(consistency — block) `with_prior_attempt` requires `sandbox_run_id: RunId` keyword-only kwarg.** S1-04 HARDENED #5 / AC-G-2 widened the signature. Draft called `ctx.with_prior_attempt(outcome)` — `TypeError` at runtime. Fix: AC-WPA-1 pins `ctx = ctx.with_prior_attempt(outcome, sandbox_run_id=run.run_id)`; AC-WPA-2 the new `ctx.prior_attempts[-1].sandbox_run_id == run.run_id` (identity carries through `AttemptSummary`).
4. **(consistency / coverage — block) `failed_unrecoverable` is runner-derived; gate.evaluate only returns 3 states.** S4-05 HARDENED locked `GateOutcome.state ∈ {passed, failed_retryable, escalate}`. Draft AC asserted "third Attempt.outcome.state is also `failed_unrecoverable`" but the gate would have written `failed_retryable`. Fix: AC-DERIVE-1 — on same-failing-signals-3× detection, runner does `outcome = outcome.model_copy(update={"state": "failed_unrecoverable", "retryable": False})` BEFORE the third `ledger.record(...)`; the recorded `Attempt.outcome.state` matches the returned outcome.
5. **(consistency / coverage — block) `SandboxBackendError` orphans `_marker_pending` → next iteration crashes.** S2-02 AC-OO-3 / AC-RR-5 require `_marker_pending is False` before `record_pre_execute`. Draft said the synthetic attempt counts toward `max_attempts` but didn't pin that the synthetic `ledger.record(...)` MUST close the marker BEFORE the next iteration. Without it, iteration 2's `record_pre_execute` raises `LedgerAttemptOutOfOrder(context="record_pre_execute")` and the loop aborts at attempt 2. Fix: AC-BACKEND-CLOSE pins the close-the-marker invariant; metamorphic AC-INV-1 asserts `count(pre_execute) == count(execute calls) == count(attempt records)` across every test, including all-backend-errors.
6. **(coverage — block) Synthetic `Attempt.sandbox_run_id` for backend errors unspecified.** `Attempt.sandbox_run_id: RunId` is required (S1-04 Frozen Pydantic). No `SandboxRun` exists on `SandboxBackendError`. Fix: AC-SYN-1 pins `RunId(f"backend-error-{attempt_id:04d}")` as the synthetic value; stable per attempt; round-trips through `entries()`.
7. **(consistency — block) Ledger reader is `entries() -> list[LedgerEntry]`, NOT `attempts()`.** S2-02 HARDENED AC-DR-1 locked the typed union reader. Draft tests called `fake_ledger.attempts()[-1].outcome.state`. Fix: AC-LE-1 — fakes mirror the production `entries()` surface; tests filter with `[e for e in entries() if isinstance(e, Attempt)]`. Convenience helpers `count_attempts()` / `count_pre_executes()` ALLOWED on the fake but must be documented as views over `entries()`.
8. **(test-quality / coverage — block) TDD-plan code is invalid Python (escaped quotes).** Lines 130, 137-138, 144, 150-156, 164-166, 173-176, 187-188, 192, 204-210, 216-217, 221-223, 230, 234 use `\"...\"` instead of `"..."` — looks like JSON escape leaked into markdown. Fix: AC-PLAIN-PY-1 asserts the rewritten test file passes `python -c 'import ast; ast.parse(open(path).read())'`; the TDD plan section is rewritten with proper Python literals.
9. **(test-quality — block) Branch C `failing_signals` order-sensitivity untested.** Draft used three identical `["tests"]` lists. Mutation `tuple(...)` over `frozenset(...)` passes silently. Fix: AC-SET-1 parametrizes Branch C over `[["tests","lint"], ["lint","tests"], ["tests","lint"]]` — set-equal, list-unequal — and asserts `failed_unrecoverable`. AC-SORT-1 also pins that EVERY `Attempt.outcome.failing_signals` written by the runner is sorted (S4-05 AC-FS-1 on-disk stability).
10. **(test-quality — block) Branch D `attempt=2` baked into fake outcome.** Draft `_passed_outcome(attempt=2)` lets the runner pass `attempt=99` to the gate without test failure. Fix: AC-AT-STAMP-1 — fake outcomes carry NO `attempt` arg; runner is contractually responsible for `outcome = outcome.model_copy(update={"attempt": AttemptNumber(current_loop_attempt)})`; tests assert both `out.attempt == 2` AND `fake_gate.last_eval_attempt == 2`.
11. **(test-quality — block) No replan call-count assertion in Branch C.** Mutation `if replan_hook and attempt <= max_attempts:` (off-by-one) fires a 3rd replan. Draft's `MagicMock(...)` masks it. Fix: AC-RC-1 — Branch C asserts `replan.await_count == 2` (replan fires between attempts 1→2 and 2→3, NOT after attempt 3).
12. **(test-quality / coverage — block) Pre-execute ordering only tested on Branch D.** ADR-0007 says "marker BEFORE every execute." A regression that writes marker AFTER execute on attempt 1 passes Branch A. Fix: AC-PEM-2 — the `parent.attach_mock` ordering trick is hoisted to a `assert_marker_ordering(parent, expected_count)` helper used by Branch A, Branch C, Branch D, AND the backend-error test.
13. **(test-quality — block) `GateMissingRequiredSignal` test asserts `summary.startswith("missing_required_signal")`.** Substring fragility — S2-02 HARDENED #9 explicitly killed substring assertions. Also: `Attempt.outcome.signals: ObjectiveSignals` is REQUIRED non-None — synthetic outcome must carry an `ObjectiveSignals()`. Fix: AC-MR-1 asserts on structured `outcome.failing_signals == ["missing_required_signal"]` (sorted) AND `outcome.signals` is a valid `ObjectiveSignals` instance (may have signals collected pre-evaluate).
14. **(coverage — harden) `max_attempts > 1024` not rejected.** `AttemptNumber` is bounded `1..1024` per S1-04 (`Annotated[int, Field(ge=1, le=1024)]`). Draft only rejected `< 1`. Fix: AC-CON-1 parametrizes `[0, -1, 1025, 3.0, "3", None]` all raise `ValueError`/`TypeError`.
15. **(coverage — harden) Loop-exhaustion + varying signals branch implicit.** When all `max_attempts` attempts fail retryably with NON-identical `failing_signals` (signals vary), Branch C does not fire and the loop falls through. Fix: AC-EX-1 pins the explicit `escalate` return + ledger has `max_attempts` entries.
16. **(coverage / test-quality — harden) Same-signature detector is a sliding window of size 3, NOT `max_attempts`-floor.** Phase arch §Edge case 17 says "3×". Draft outline step 4 said "if `len(deque) == max_attempts`" — diverges for `max_attempts=5`. Fix: AC-SLIDE-1 — detector triggers when the last 3 attempts have set-equal `failing_signals` AND `attempt >= 3`, regardless of `max_attempts`. Test: `max_attempts=5` with three identical retryable failures returns `failed_unrecoverable` at attempt 3, ledger has 3 attempts.
17. **(test-quality — harden) `Failed` `RecipeOutcome` from replan_hook untested.** What if the LLM fallback itself returns `Failed(reason=...)`? Fix: AC-RF-1 — `replan_hook` returns `Failed(reason="llm_timeout")` on attempt 1 → runner returns `escalate`; ledger has 1 attempt (the original failure) + structured log event `gates.runner.replan_failed`.
18. **(coverage — harden) `structlog` event field set unpinned.** Draft listed event names. Fix: AC-OBS-1 pins fields per event — `gates.runner.attempt_started` carries `{attempt, gate_id, transition_id, sandbox_spec_hash}`; `gates.runner.attempt_recorded` carries `{attempt, state, failing_signals, sandbox_run_id}`; `gates.runner.replan_invoked` carries `{attempt, prior_attempts_count}`; `gates.runner.replan_failed` carries `{attempt, variant}`; `gates.runner.exit` carries `{final_state, attempt, total_duration_ms}`. Test uses `structlog.testing.capture_logs()`.
19. **(consistency / design — harden) Module purity + fence rows.** New submodule `src/codegenie/gates/runner.py` needs cold-start fence rows + import-allowlist test (CLAUDE.md "Structural defenses live under `tests/fence/`"). Fix: AC-PURITY-1 — `runner.py`'s import closure ∩ `{codegenie.fallback, codegenie.rag, codegenie.cli, codegenie.orchestrator}` is empty (composition-root discipline); AC-PURITY-2 — no `subprocess`, `os.system`, `anthropic`, `openai`, `pickle` imports; AC-FENCE-1 — corresponding row exists in `tests/fence/` cold-start matrix.
20. **(design — harden) Functional core / imperative shell split pinned as ACs (S4-05 / S2-02 precedent).** Refactor named `_dispatch_outcome`; promoted to AC-PH-1 (pure, takes data, returns `Literal[...]`). Added AC-PH-2 — `_is_same_failing_signals_3x(history: Sequence[frozenset[SignalKind]], attempt: int) -> bool` is a separate pure module-level helper, unit-tested with empty / `len<3` / mixed-order / true-positive cases. AC-PH-3 — `history: collections.deque[frozenset[SignalKind]]` with `maxlen=3` (NOT `maxlen=max_attempts` per finding #16); element type is typecheck-visible. AC-PH-4 — `structlog` emit calls live in `run()` ONLY (helpers stay pure).
21. **(design — harden) Primitive obsession on identifiers.** Fix: AC-NT-1 — `runner.py` consumes `AttemptNumber`, `SandboxSpecHash`, `RunId`, `SignalKind` newtypes; bare `int`/`str` for domain concepts is a `mypy --strict` violation against the module's public signature.
22. **(design — harden) Constructor bound + keyword-only.** Fix: AC-CTOR-1 — `__init__` is keyword-only (`*, client, gate, ...`); AC-CON-1 above covers the bound; AC-CTOR-2 — six dependencies all injected (Hexagonal — `GateRunner` is the inbound port; `SandboxClient`, `Gate`, `RetryLedger`, `SandboxSpecBuilder`, `ReplanHook` are five outbound ports).
23. **(design — harden) Atomic `ctx` swap.** Notes pin one-line composition: `ctx = ctx.with_prior_attempt(outcome, sandbox_run_id=run.run_id).model_copy(update={"transform_output": applied_or_unchanged})` — single statement; never the two-copy form that leaves a transient ctx visible to observers.
24. **(test-quality — harden) `last_ctx` invented helper replaced.** Drop the bespoke recorder. Use `fake_spec_builder.for_gate.call_args_list[i].kwargs["ctx"]` (or positional equivalent) to assert against the spec-builder Port. Fakes do not invent inspection surface absent from the production Protocol.
25. **(test-quality — harden) Hypothesis property + metamorphic invariant.** AC-PROP-1: for `n ∈ [1, max_attempts-1]` retryable outcomes + 1 pass, runner returns `(state="passed", attempt=n+1)`. AC-INV-1: across every test, `len([e for e in entries() if isinstance(e, PreExecuteMarker)]) == fake_client.execute.call_count == len([e for e in entries() if isinstance(e, Attempt)])` (metamorphic — single guard catches whole marker/attempt drift classes).
26. **(consistency — nit) `S1-04` added to `Depends on:` line** — transitive but load-bearing (`with_prior_attempt` widened kwarg, `AttemptNumber` bound, `Attempt`/`GateOutcome` shapes).
27. **(consistency — note) `ctx.transform_output` Phase-3 widening.** Until Phase 3 widens `GateContext.transform_output` from `str` placeholder to a typed model, Branch D carries forward the `Applied` *as-is* into the field. The runner does NOT coerce (per S5-01 HARDENED AC-FWD-1). Notes-for-implementer pins this; an Out-of-scope row defers the typed widening.
28. **(design — note) `_synthetic_error_outcome` rule-of-two.** Two synthetic-outcome construction sites (backend error + missing signal). Per Rule 2, inline both. If a third site lands (S5-05 cassette retry / S6 Firecracker timeout), extract `_synthetic_error_outcome(error_kind, attempt, signals) -> GateOutcome` at that point.
29. **(design — note) `_run_one_attempt` extraction option.** Surface as a Notes refactor: extract `_run_one_attempt(ctx, attempt, started_at) -> tuple[Attempt, GateOutcome]` so the marker-before-execute ordering becomes lexically enforced inside one function. Don't AC it — surface as one-time future option.

No `RESCUE`-tier findings — every gap was patchable from S1-04 / S2-02 / S4-05 / S5-01 HARDENED reports + arch + ADRs + CLAUDE.md. No Stage-3 research needed: every gap was answerable from in-repo precedents and prior HARDENED stories. Full audit log: [`_validation/S5-02-gate-runner-retry-loop.md`](_validation/S5-02-gate-runner-retry-loop.md).

## Context

`GateRunner` is the *exactly-once* implementation of the three-retry loop the entire phase exists to ship (per `phase-arch-design.md §Component design — GateRunner` and production ADR-0014). It composes everything S1-S4 landed: `SandboxSpecBuilder.for_gate`, `SandboxClient.execute`, the six signal collectors, `StrictAndGate.evaluate`, and `RetryLedger.record_pre_execute` / `record` / `entries`. The loop has four mutually exclusive exit branches (`passed`, `escalate`, `failed_unrecoverable`, replan-and-continue); each must be tested independently and the union must reach ≥ 90% branch coverage. The pre-execute marker (Gap 1, ADR-0007) must be written **before** `client.execute()` runs, not after — this story enforces that ordering for every attempt (including those that raise `SandboxBackendError`).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — GateRunner` — public interface, internal structure (the six-step loop body), performance envelope, failure behavior.
  - `../phase-arch-design.md §Process view §Scenario 1 (happy)` — first-attempt-passes sequence.
  - `../phase-arch-design.md §Process view §Scenario 2 (retry recovers)` — the central scenario this loop implements.
  - `../phase-arch-design.md §Process view §Scenario 3 (test removed)` — `failed_unrecoverable` on same `failing_signals` 3×.
  - `../phase-arch-design.md §Process view §Scenario 4 (docker daemon dies)` — `SandboxBackendError` counts as a failing attempt.
  - `../phase-arch-design.md §Edge cases §17` — same-signature 3× → `failed_unrecoverable` (exit 12), distinct from `escalate` (exit 11).
  - `../phase-arch-design.md §Concurrency` (line ~236) — single-threaded by design; `SandboxClient.execute` is sync; the only `await` site in the runner is the `replan_hook`.
- **Phase ADRs:**
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — `GateRunner` is the only consumer of `SandboxClient`; Stage 6's previous direct `validation.*` call routes through it.
  - `../ADRs/0007-pre-execute-marker-for-resume-safety.md` — `record_pre_execute(attempt_id, sandbox_spec_hash, started_at)` is called **before** `client.execute`; the marker write is BLAKE3-chained.
  - `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — `ObjectiveSignals` is the only signal carrier; this story consumes it but does not extend it.
- **Production ADRs:**
  - `../../../production/adrs/0014-three-retry-default-per-gate.md` — `max_attempts: int = 3` default; override path requires `--operator-ack`.
- **Source design:**
  - `../final-design.md §Synthesis ledger — Three-retry loop + replan_hook row`.
- **Prior-story validation (read first):**
  - `_validation/S1-04-gates-contract-abc-models.md` — `with_prior_attempt(outcome, *, sandbox_run_id: RunId)` widened kwarg; `AttemptNumber` 1..1024 bound; `ReplanHook` Protocol shape.
  - `_validation/S2-02-pre-execute-marker-gap-1.md` — `_marker_pending` recovery; `entries()` reader; `LedgerAttemptOutOfOrder(context=...)` discriminator.
  - `_validation/S4-05-strict-and-gate-equivalence.md` — `Gate.evaluate` returns only 3 states (`passed | failed_retryable | escalate`); `failed_unrecoverable` is runner-derived.
  - `_validation/S5-01-replan-hook-protocol-contract-test.md` — `ReplanHook` is `async`; returns `RecipeOutcome` sum type; factory composition-root pattern.
- **Existing code:**
  - `src/codegenie/gates/contract.py` (S1-04, S5-01) — `Gate`, `GateContext`, `GateOutcome`, `RetryPolicy`, `AttemptSummary`, `ReplanHook`, `Attempt`.
  - `src/codegenie/gates/retry_ledger.py` (S2-01, S2-02) — `record_pre_execute`, `record`, `head`, `entries`.
  - `src/codegenie/gates/errors.py` — `GateMissingRequiredSignal`, `LedgerAttemptOutOfOrder`.
  - `src/codegenie/sandbox/contract.py` — `SandboxClient`, `SandboxSpec`, `SandboxRun`, `SandboxBackendError`.
  - `src/codegenie/sandbox/spec_builder.py` (S3-01) — `SandboxSpecBuilder.for_gate`.
  - `src/codegenie/sandbox/signals/registry.py` (S1-05, S4-01..S4-04) — signal-kind registry.
  - `src/codegenie/gates/strict_and.py` (S4-05) — `StrictAndGate.evaluate`.
  - `src/codegenie/transforms/outcomes.py` — `RecipeOutcome = Applied | Skipped | NotApplicable | Failed`.
  - `src/codegenie/types/identifiers.py` — `AttemptNumber`, `RunId`, `SandboxSpecHash`, `SignalKind` newtypes.

## Goal

Implement `GateRunner.run(ctx) -> GateOutcome` as an **`async def`** method (Phase-5's single `await` site is the `replan_hook`) wrapping a `for attempt in 1..max_attempts` loop that writes the pre-execute marker before every `client.execute`, records every attempt, dispatches via a pure `_dispatch_outcome` helper to the four mutually exclusive exit branches (`passed` / `escalate` / `failed_unrecoverable` — runner-derived / replan-and-continue), and closes the `_marker_pending` state on every error path; ≥ 90% branch / ≥ 95% line coverage on `runner.py`.

## Acceptance criteria

### A. Constructor + signature

- [ ] **AC-CTOR-1 — Keyword-only constructor:** `GateRunner(*, client: SandboxClient, gate: Gate, ledger: RetryLedger, spec_builder: SandboxSpecBuilder, max_attempts: int = 3, replan_hook: ReplanHook | None = None)` per `../phase-arch-design.md §Component design`. Asserted via `inspect.signature(GateRunner.__init__)` — every parameter except `self` is `KEYWORD_ONLY`.
- [ ] **AC-CON-1 — `max_attempts` bound:** constructor rejects `max_attempts` outside `[1, 1024]` (the `AttemptNumber` envelope from `types/identifiers.py:102`) with `ValueError`. Parametrized: `pytest.mark.parametrize("bad", [0, -1, 1025, 10_000])`.
- [ ] **AC-CON-2 — Type discipline at the constructor boundary:** non-int `max_attempts` (`3.0`, `"3"`, `None`) raise `TypeError` (or `ValueError` if Pydantic-coerced). The default `3` is `int`, asserted via `typing.get_type_hints(GateRunner.__init__)`.
- [ ] **AC-ASYNC-1 — `run` is `async def`:** `inspect.iscoroutinefunction(GateRunner.run) is True`; test files use `await runner.run(ctx)`. The repo's `asyncio_mode = "auto"` makes `@pytest.mark.asyncio` markers redundant; tests do NOT add the marker (lint-equivalent: no marker added by this story).

### B. Pre-execute marker — ordering invariant (ADR-0007)

- [ ] **AC-PEM-1 — Marker before execute:** for every attempt (including those that raise `SandboxBackendError`), `ledger.record_pre_execute(attempt_id, spec.sandbox_spec_hash, started_at=started_at)` is called **before** `client.execute(spec)`. Verified by a `parent = MagicMock(); parent.attach_mock(...)` ordering trick exposed as a shared `assert_marker_ordering(parent, expected_pairs)` helper. The helper asserts `parent.mock_calls`' name list is `["pre_execute", "execute"] * expected_pairs`.
- [ ] **AC-PEM-2 — Ordering asserted across ALL branches:** `assert_marker_ordering(parent, expected_pairs)` is invoked in Branch A (`expected_pairs=1`), Branch C (`=3`), Branch D (`=2`), AND the all-backend-errors test (`=3`). A regression that moves the marker write after `client.execute` fails ≥ 4 tests.
- [ ] **AC-INV-1 — Marker / execute / attempt-record metamorphic invariant:** for every test that drives the runner end-to-end, `len([e for e in ledger.entries() if isinstance(e, PreExecuteMarker)]) == fake_client.execute.call_count == len([e for e in ledger.entries() if isinstance(e, Attempt)])` at test teardown. Conftest fixture autouses this assertion. A regression that skips the marker on `replan_hook=None`'s exhausting attempt fails the invariant.

### C. The four exit branches

- [ ] **AC-BRANCH-A — Happy (first attempt passes):** when `gate.evaluate(...)` returns `GateOutcome(state="passed")` on attempt 1, `await runner.run(ctx)` returns it without awaiting `replan_hook`; `entries()` contains exactly one `PreExecuteMarker(attempt_id=1)` followed by one `Attempt(attempt_id=1, outcome.state="passed")`.
- [ ] **AC-BRANCH-B — Non-retryable escalate (gate.state=="escalate"):** when `gate.evaluate(...)` returns `GateOutcome(state="escalate")` (e.g., `trace` failure per the YAML's `non_retryable_failures`), `run` returns it immediately; `replan_hook.await_count == 0`; `entries()` has exactly one `PreExecuteMarker` + one `Attempt`.
- [ ] **AC-BRANCH-C — `failed_unrecoverable` (same failing signals 3×, sliding window):** when three consecutive attempts produce **set-equal** `failing_signals` (order-insensitive), `run` returns `GateOutcome(state="failed_unrecoverable", retryable=False, attempt=AttemptNumber(3))`. The third `Attempt.outcome.state` written to the ledger ALSO equals `"failed_unrecoverable"` (runner derives via `outcome.model_copy(update={"state": "failed_unrecoverable", "retryable": False})` BEFORE the third `record(...)`).
- [ ] **AC-SET-1 — Set-equality, not list-equality, on `failing_signals`:** Branch C is parametrized across `[["tests","lint"], ["lint","tests"], ["tests","lint"]]` (set-equal, list-unequal across attempts). The detector fires; `failed_unrecoverable` is returned. A regression using `tuple(failing_signals)` for the comparison fails this row.
- [ ] **AC-SLIDE-1 — Sliding window of size 3, NOT `max_attempts`-floor:** with `max_attempts=5` and three identical retryable failures on attempts 1-3, runner returns `failed_unrecoverable` at attempt 3, ledger has 3 attempts, `replan_hook.await_count == 2`.
- [ ] **AC-BRANCH-D — Replan-and-continue → eventual pass:** when attempt 1 fails retryably and attempt 2 passes, `await run(ctx)` returns `GateOutcome(state="passed", attempt=AttemptNumber(2))`; `replan_hook.await_count == 1`; the awaited `ctx` carries `len(ctx.prior_attempts) == 1`; the recipe outcome is propagated forward (see AC-RO).
- [ ] **AC-EX-1 — Exhaustion + varying signals → escalate:** when all `max_attempts` attempts fail retryably with NON-set-equal `failing_signals` (e.g., `["tests"], ["lint"], ["tests","lint"]`), Branch C does NOT fire; runner returns `GateOutcome(state="escalate", attempt=AttemptNumber(max_attempts))`; ledger has `max_attempts` entries.

### D. `ReplanHook` async surface + `RecipeOutcome` sum-type dispatch

- [ ] **AC-RH-1 — Hook is awaited:** the runner does `recipe_outcome = await self.replan_hook(ctx_with_prior)` at exactly one place in `run()`. AST scan asserts the body of `run()` contains exactly one `await` expression whose callee is `self.replan_hook`.
- [ ] **AC-RC-1 — Replan call-count is `attempt - 1` after retries, never `attempt`:** Branch C with `max_attempts=3` and three retryable outcomes → `replan.await_count == 2` (fires between attempts 1→2 and 2→3, NOT after attempt 3). Catches the `attempt <= max_attempts` off-by-one mutation.
- [ ] **AC-RO-1 — `match` on `RecipeOutcome` variant (CLAUDE.md "tagged union > anaemic dict"):** the runner dispatches via `match recipe_outcome: case Applied(): ...; case Skipped() | NotApplicable() | Failed(): ...`. AST scan asserts at least one `Match` node in `run()`. No `.kind == "applied"` string comparison.
- [ ] **AC-RO-2 — `Skipped` / `NotApplicable` / `Failed` from replan → escalate without further retries:** when `replan_hook` returns any non-`Applied` variant, runner returns `GateOutcome(state="escalate", ...)`; ledger has the originating failed attempt; `gates.runner.replan_failed` structured event is emitted with `{attempt, variant: "skipped"|"not_applicable"|"failed"}`.
- [ ] **AC-RO-3 — `Applied` carries forward unchanged:** the `Applied` instance returned by `replan_hook` is stored into the next iteration's `ctx.transform_output` via `model_copy(update={"transform_output": applied})` WITHOUT type coercion (per S5-01 HARDENED AC-FWD-1). The spec builder receives the `Applied` instance unchanged on attempt 2's `for_gate(...)` call; identity-equal: `fake_spec_builder.for_gate.call_args_list[1].kwargs["ctx"].transform_output is applied`.
- [ ] **AC-RF-1 — `Failed` replan_hook test:** when `replan_hook` returns `Failed(reason="llm_timeout")` after attempt 1's retryable failure, runner returns `GateOutcome(state="escalate")`; ledger has exactly 1 `Attempt` (the original failure); `gates.runner.replan_failed` event emitted.

### E. `with_prior_attempt` + ctx threading

- [ ] **AC-WPA-1 — `sandbox_run_id` kwarg supplied:** `ctx = ctx.with_prior_attempt(outcome, sandbox_run_id=run.run_id).model_copy(update={"transform_output": applied})` is the **single** atomic statement that produces the next iteration's ctx (no two-copy form leaving a transient ctx visible). AST scan on `run()` asserts at most one `with_prior_attempt` callsite and at most one ctx-reassignment per loop iteration.
- [ ] **AC-WPA-2 — `prior_attempts[-1].sandbox_run_id` carries identity:** after Branch D, `replan_hook.await_args.args[0].prior_attempts[-1].sandbox_run_id == run1.run_id` (the just-completed attempt's run id). Identity carries through `AttemptSummary` per S1-04 AC-G-4.
- [ ] **AC-WPA-3 — Three-attempt accumulation:** in a Branch C / sliding-window test with three attempts, the third `replan_hook` (if it were called — it ISN'T per AC-RC-1) would observe `len(ctx.prior_attempts) == 2`; we instead assert via the second hook call that `len(ctx.prior_attempts) == 1`.

### F. Synthetic outcomes for error paths

- [ ] **AC-SYN-1 — `SandboxBackendError` synthetic Attempt:** when `client.execute` raises `SandboxBackendError(...)`, runner constructs `GateOutcome(passed=False, attempt=AttemptNumber(attempt), failing_signals=["sandbox_backend"], retryable=True, state="failed_retryable", summary="sandbox_backend_error", signals=ObjectiveSignals())` and a paired `Attempt` with `sandbox_run_id=RunId(f"backend-error-{attempt:04d}")`. `ObjectiveSignals()` (all sub-models `None`) is the empty signals payload.
- [ ] **AC-BACKEND-CLOSE — Synthetic attempt closes `_marker_pending` BEFORE next iteration:** after `SandboxBackendError`, runner immediately calls `ledger.record(synthetic_attempt)` to clear `_marker_pending`; the next iteration's `record_pre_execute(attempt+1, ...)` succeeds without `LedgerAttemptOutOfOrder`. Test: three consecutive `SandboxBackendError` → `count_pre_executes() == count_attempts() == 3`; final outcome is `escalate` (Scenario 4).
- [ ] **AC-MR-1 — `GateMissingRequiredSignal` synthetic outcome:** runner constructs `GateOutcome(state="escalate", retryable=False, failing_signals=["missing_required_signal"], signals=<collected signals so far, or ObjectiveSignals()>, summary=f"missing_required_signal:{exc.missing}")`; records exactly one attempt; returns immediately. Assertion: `outcome.failing_signals == ["missing_required_signal"]` (NOT `summary.startswith(...)`).
- [ ] **AC-NONE-1 — `replan_hook is None` + retryable failure → escalate:** when `replan_hook` is `None` and attempt 1 returns `failed_retryable`, runner returns `escalate` immediately (no way to produce a different patch); ledger has exactly 1 attempt.

### G. Outcome derivation discipline (frozen models, sum types)

- [ ] **AC-DERIVE-1 — `failed_unrecoverable` derived via `model_copy`:** runner does `outcome = outcome.model_copy(update={"state": "failed_unrecoverable", "retryable": False, "passed": False})` BEFORE the third `record(...)`. Never constructs `GateOutcome(...)` from scratch in this path (would drop `failing_signals`, `summary`, `signals`).
- [ ] **AC-AT-STAMP-1 — Runner stamps `attempt` on every outcome:** before recording, runner does `outcome = outcome.model_copy(update={"attempt": AttemptNumber(current_loop_attempt)})`. Tests assert both `out.attempt == n` AND that the fake gate's `last_eval_attempt == n` (proves the runner passed the right counter to gate.evaluate AND stamped the returned outcome). Catches the "runner returns gate's outcome verbatim" mutation.
- [ ] **AC-SORT-1 — `failing_signals` recorded sorted:** every `Attempt.outcome.failing_signals` written by the runner is sorted (`list == sorted(list)`). Applies to derived `failed_unrecoverable`, synthetic backend-error (`["sandbox_backend"]` already sorted), and missing-signal (`["missing_required_signal"]` already sorted).

### H. Functional core / imperative shell

- [ ] **AC-PH-1 — `_dispatch_outcome(outcome, attempt, max_attempts, has_replan_hook, history) -> Literal["return", "escalate", "failed_unrecoverable", "continue"]`:** module-private; PURE (no `ledger.*`, `client.*`, `await`, `structlog.*` calls in body); inputs are only data; returns a closed-sum dispatch tag. AST-walk conformance test (mirrors S4-05 AC-PURITY-1).
- [ ] **AC-PH-2 — `_is_same_failing_signals_3x(history: Sequence[frozenset[SignalKind]], attempt: int) -> bool`:** separate module-private pure helper; unit-tested with `[]` (False), `[{a},{a}]` (False — only 2), `[{a},{b},{a}]` (False — not all equal), `[{a,b},{b,a},{a,b}]` (True — set-equal across permutations), `[{a},{a},{a},{a}]` (True only at attempt >= 3 — slide).
- [ ] **AC-PH-3 — `history: collections.deque[frozenset[SignalKind]]` with `maxlen=3`:** typecheck-visible element type. `runner.py` builds `frozenset(outcome.failing_signals)` and `history.append(...)` at the bottom of each iteration BEFORE dispatch.
- [ ] **AC-PH-4 — `structlog` emit lives in `run()` only:** AST scan asserts `_dispatch_outcome` / `_is_same_failing_signals_3x` / any other module-private helper has no `structlog` import or call in its body. Side-effects live exclusively in the impure shell.

### I. Module purity + fence rows

- [ ] **AC-PURITY-1 — Composition-root isolation:** AST scan on `src/codegenie/gates/runner.py` asserts its import closure ∩ `{codegenie.fallback, codegenie.rag, codegenie.cli, codegenie.orchestrator}` is empty. The runner depends only on `codegenie.gates.*`, `codegenie.sandbox.*` (contract surfaces), `codegenie.transforms.outcomes`, `codegenie.types.identifiers`, and stdlib.
- [ ] **AC-PURITY-2 — No forbidden runtime imports:** AST scan asserts no `import subprocess`, `import os.system`, `import anthropic`, `import openai`, `import pickle` in `runner.py`. The fence `tests/schema/test_no_subprocess_outside_build_chokepoint.py` remains green.
- [ ] **AC-FENCE-1 — Cold-start fence row for `codegenie.gates.runner`:** the corresponding row in `tests/fence/` cold-start matrix exists and is green. If a row doesn't exist for `gates/runner.py`, this story adds it.
- [ ] **AC-NT-1 — Newtypes consumed, not redefined:** `runner.py` IMPORTS `AttemptNumber`, `SandboxSpecHash`, `RunId`, `SignalKind` from `codegenie.types.identifiers`. AST scan forbids `NewType(...)` calls in `runner.py`.

### J. Observability

- [ ] **AC-OBS-1 — Structured `structlog` events with pinned field sets:**
  - `gates.runner.attempt_started`: `{attempt, gate_id, transition_id, sandbox_spec_hash}`
  - `gates.runner.attempt_recorded`: `{attempt, state, failing_signals, sandbox_run_id}`
  - `gates.runner.replan_invoked`: `{attempt, prior_attempts_count}`
  - `gates.runner.replan_failed`: `{attempt, variant}` (`variant ∈ {"skipped", "not_applicable", "failed"}`)
  - `gates.runner.exit`: `{final_state, attempt, total_duration_ms}`
  Tests capture via `structlog.testing.capture_logs()` and assert field sets per event are EXACT subsets of the captured payload.

### K. Property-based + coverage

- [ ] **AC-PROP-1 — Hypothesis property: `n` retryable then pass:** `@given(n=integers(min_value=1, max_value=2))` (max_attempts-1=2 when max=3); for `n` retryable outcomes (varying signals to avoid Branch C) followed by 1 pass, runner returns `(state="passed", attempt=n+1)`. Catches hardcoded `attempt=2`.
- [ ] **AC-PROP-2 — Hypothesis property: set-equal shuffle preserves Branch C:** `@given(perms=...)` over a non-empty `frozenset[SignalKind]`; three attempts whose `failing_signals` are permutations of the same set → runner returns `failed_unrecoverable`. Catches `tuple(...)` order-sensitive comparison.
- [ ] **AC-COV-1 — `tests/gates/test_runner_branches.py`** covers all four branches plus `EX-1`, `SYN-1`/`BACKEND-CLOSE`, `MR-1`, `NONE-1`, `RF-1`, `SLIDE-1`; `pytest --cov=src/codegenie/gates/runner --cov-branch` reports ≥ 90% branch and ≥ 95% line.
- [ ] **AC-PLAIN-PY-1 — TDD file parses:** `python -c 'import ast; ast.parse(open("tests/gates/test_runner_branches.py").read())'` exits 0. (Defends against an executor copying escaped-quote sample text verbatim.)
- [ ] **AC-LEDGER-PROBE-1 — `tests/gates/test_pre_execute_marker.py`** (the test S2-02 stubbed) is upgraded to assert ordering against the live `GateRunner` (not just `RetryLedger` in isolation). Uses `assert_marker_ordering` helper.
- [ ] **AC-MYPY-1 — `mypy --strict src/codegenie/gates/runner.py`** passes; no `Any` in the public signature; constructor + `run` + private helpers fully typed.
- [ ] **AC-CHAIN-1 — `Attempt` chain fields populated by ledger, not runner:** runner builds `Attempt` WITHOUT supplying `prev_hash`/`chain_hash` (S2-01/S2-02 lock chain derivation inside `RetryLedger.record`). `ended_at = datetime.now(UTC)` is set by the runner AFTER `gate.evaluate` returns (so `ended_at >= started_at` per S1-04 C-7).
- [ ] **AC-QG-1 — Quality gates:** `ruff`, `ruff format --check`, `mypy --strict`, `pytest tests/gates/test_runner_branches.py tests/gates/test_pre_execute_marker.py tests/gates/test_runner_purity.py` all pass.

## Implementation outline

1. Create `src/codegenie/gates/runner.py`. Module docstring cites ADR-0001 (Stage 6 chokepoint), ADR-0007 (pre-execute marker), production ADR-0014 (three-retry), and ADR-0006 (Protocol-vs-ABC) by name.
2. Define module-private pure helpers:
   - `_dispatch_outcome(outcome, attempt, max_attempts, has_replan_hook, history) -> Literal["return", "escalate", "failed_unrecoverable", "continue"]` — closed-sum dispatch tag.
   - `_is_same_failing_signals_3x(history: Sequence[frozenset[SignalKind]], attempt: int) -> bool` — sliding-window detector; only returns True when `attempt >= 3 AND len(history) >= 3 AND len(set(history[-3:])) == 1`.
3. Define `class GateRunner` with the keyword-only `__init__` (AC-CTOR-1); constructor validates `max_attempts ∈ [1, 1024]` (AC-CON-1).
4. Define private helper `_collect_signals(run: SandboxRun, ctx: GateContext) -> ObjectiveSignals` — iterates `self.gate.required_signals` and dispatches via `sandbox.signals.registry`. Pure relative to its inputs.
5. Define `async def run(self, ctx: GateContext) -> GateOutcome`:
   - Initialize `started_run_at = datetime.now(UTC)`; `history: deque[frozenset[SignalKind]] = deque(maxlen=3)`.
   - Loop `for attempt_int in range(1, self.max_attempts + 1):`
     - `attempt = AttemptNumber(attempt_int)`; `started_at = datetime.now(UTC)`.
     - `spec = self.spec_builder.for_gate(self.gate, attempt, ctx)`.
     - `self.ledger.record_pre_execute(attempt, spec.sandbox_spec_hash, started_at=started_at)` — **before any execute**.
     - Emit `gates.runner.attempt_started`.
     - `try: run_obj = self.client.execute(spec); except SandboxBackendError as e:` → synthesize `Attempt(...)` with `sandbox_run_id=RunId(f"backend-error-{attempt_int:04d}")` and `outcome=GateOutcome(state="failed_retryable", failing_signals=["sandbox_backend"], signals=ObjectiveSignals(), retryable=True, attempt=attempt, summary="sandbox_backend_error")`; record it (closes `_marker_pending`); emit `gates.runner.attempt_recorded`; `history.append(frozenset(["sandbox_backend"]))`; dispatch via `_dispatch_outcome(...)`; if `"escalate"` or `"failed_unrecoverable"` return; else if attempt == max_attempts return escalate; else continue (no replan — no signals to act on).
     - `try: signals = self._collect_signals(run_obj, ctx); outcome = self.gate.evaluate(signals, ctx); except GateMissingRequiredSignal as e:` → synthesize escalate outcome (AC-MR-1); record; return.
     - Stamp `outcome = outcome.model_copy(update={"attempt": attempt})` (AC-AT-STAMP-1); ensure `outcome.failing_signals` sorted.
     - `history.append(frozenset(outcome.failing_signals))`.
     - **Pre-record derivation:** if `_is_same_failing_signals_3x(history, attempt_int)`, derive `outcome = outcome.model_copy(update={"state": "failed_unrecoverable", "retryable": False, "passed": False})` (AC-DERIVE-1).
     - Build `attempt_record = Attempt(attempt_id=attempt, sandbox_run_id=run_obj.run_id, signals=signals, outcome=outcome, started_at=started_at, ended_at=datetime.now(UTC))` (chain fields supplied by `ledger.record`).
     - `self.ledger.record(attempt_record)`; emit `gates.runner.attempt_recorded`.
     - `tag = _dispatch_outcome(outcome, attempt_int, self.max_attempts, self.replan_hook is not None, history)`.
     - `match tag:`
       - `case "return":` emit `gates.runner.exit`; `return outcome`.
       - `case "escalate":` `outcome = outcome.model_copy(update={"state": "escalate"})` if needed; emit exit; return.
       - `case "failed_unrecoverable":` emit exit; return (outcome already derived above).
       - `case "continue":` (only when `replan_hook` set AND attempt < max_attempts AND state is failed_retryable):
         - Emit `gates.runner.replan_invoked` with `{attempt, prior_attempts_count: len(ctx.prior_attempts)}`.
         - `ctx_with_prior = ctx.with_prior_attempt(outcome, sandbox_run_id=run_obj.run_id)`.
         - `recipe_outcome = await self.replan_hook(ctx_with_prior)`.
         - `match recipe_outcome:`
           - `case Applied():` `ctx = ctx_with_prior.model_copy(update={"transform_output": recipe_outcome})`; continue loop.
           - `case Skipped() | NotApplicable() | Failed():` emit `gates.runner.replan_failed` with `{attempt, variant}`; return `GateOutcome(state="escalate", ...)`.
6. Loop exhaustion without pass → return `GateOutcome(state="escalate", attempt=AttemptNumber(self.max_attempts), ...)` (AC-EX-1); emit `gates.runner.exit`.
7. `src/codegenie/gates/__init__.py` re-exports `GateRunner`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/gates/test_runner_branches.py`

```python
from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, strategies as st

from codegenie.gates.contract import (
    Attempt,
    GateContext,
    GateOutcome,
    PreExecuteMarker,
    ReplanHook,
)
from codegenie.gates.errors import (
    GateMissingRequiredSignal,
    LedgerAttemptOutOfOrder,
)
from codegenie.gates.runner import GateRunner, _dispatch_outcome, _is_same_failing_signals_3x
from codegenie.sandbox.contract import SandboxBackendError
from codegenie.sandbox.signals.models import ObjectiveSignals
from codegenie.transforms.outcomes import Applied, Failed, NotApplicable, Skipped
from codegenie.types.identifiers import AttemptNumber, RunId, SignalKind


def assert_marker_ordering(parent: MagicMock, expected_pairs: int) -> None:
    """Marker MUST precede execute for every attempt (ADR-0007)."""
    names = [c[0] for c in parent.mock_calls]
    assert names == ["pre_execute", "execute"] * expected_pairs, (
        f"expected {expected_pairs} pre_execute→execute pairs; got {names!r}"
    )


@pytest.fixture
def make_runner(fake_ledger, fake_spec_builder, fake_client, strict_and_gate):
    def _make(*, max_attempts: int = 3, replan_hook: ReplanHook | None = None):
        return GateRunner(
            client=fake_client,
            gate=strict_and_gate,
            ledger=fake_ledger,
            spec_builder=fake_spec_builder,
            max_attempts=max_attempts,
            replan_hook=replan_hook,
        )
    return _make


@pytest.fixture(autouse=True)
def _enforce_marker_attempt_execute_invariant(request, fake_ledger, fake_client):
    """AC-INV-1: marker count == execute count == attempt-record count at teardown."""
    yield
    if not getattr(fake_ledger, "_used", False):
        return
    entries = fake_ledger.entries()
    markers = [e for e in entries if isinstance(e, PreExecuteMarker)]
    attempts = [e for e in entries if isinstance(e, Attempt)]
    assert len(markers) == fake_client.execute.call_count == len(attempts), (
        f"marker/execute/attempt drift: "
        f"markers={len(markers)}, execs={fake_client.execute.call_count}, attempts={len(attempts)}"
    )


# ---------- Branch A — happy path ----------

@pytest.mark.asyncio  # redundant under asyncio_mode=auto, included for explicitness
async def test_branch_A_first_attempt_passes_returns_passed_no_replan(
    make_runner, fake_client, fake_ledger, strict_and_gate, gate_ctx, ordering_parent
):
    fake_client.set_run_sequence([_run("r1", exit_code=0)])
    strict_and_gate.set_outcomes([_passed()])
    replan = AsyncMock(spec=ReplanHook)

    out = await make_runner(replan_hook=replan).run(gate_ctx)

    assert out.state == "passed"
    assert out.attempt == AttemptNumber(1)
    replan.assert_not_awaited()
    assert fake_ledger.count_attempts() == 1
    assert_marker_ordering(ordering_parent, expected_pairs=1)


# ---------- AC-PEM ordering across all branches ----------

async def test_marker_ordering_branch_D(
    make_runner, fake_client, fake_ledger, strict_and_gate, gate_ctx, ordering_parent
):
    fake_client.set_run_sequence([_run("r1", 1), _run("r2", 0)])
    strict_and_gate.set_outcomes([_failed_retryable(["tests"]), _passed()])
    applied = _applied()
    replan = AsyncMock(spec=ReplanHook, return_value=applied)

    await make_runner(replan_hook=replan).run(gate_ctx)

    assert_marker_ordering(ordering_parent, expected_pairs=2)


# ---------- Branch B — non-retryable escalate ----------

async def test_branch_B_gate_escalate_returns_immediately_no_replan(
    make_runner, fake_client, strict_and_gate, fake_ledger, gate_ctx, ordering_parent
):
    fake_client.set_run_sequence([_run("r1", 1)])
    strict_and_gate.set_outcomes([_gate_escalate(["trace"])])
    replan = AsyncMock(spec=ReplanHook)

    out = await make_runner(replan_hook=replan).run(gate_ctx)

    assert out.state == "escalate"
    replan.assert_not_awaited()
    assert fake_ledger.count_attempts() == 1
    assert_marker_ordering(ordering_parent, expected_pairs=1)


# ---------- Branch C — same failing signals 3× (sliding window, set-equality) ----------

@pytest.mark.parametrize(
    "signal_lists",
    [
        [["tests"], ["tests"], ["tests"]],                       # identical
        [["tests", "lint"], ["lint", "tests"], ["tests", "lint"]],  # set-equal, list-unequal
    ],
    ids=["identical", "set_equal_permutations"],
)
async def test_branch_C_same_failing_signals_three_times_returns_failed_unrecoverable(
    make_runner, fake_client, strict_and_gate, fake_ledger, gate_ctx, signal_lists
):
    fake_client.set_run_sequence([_run(f"r{i}", 1) for i in range(3)])
    strict_and_gate.set_outcomes([_failed_retryable(s) for s in signal_lists])
    applied = _applied()
    replan = AsyncMock(spec=ReplanHook, return_value=applied)

    out = await make_runner(replan_hook=replan).run(gate_ctx)

    assert out.state == "failed_unrecoverable"
    assert out.retryable is False
    assert fake_ledger.count_attempts() == 3
    attempts = [e for e in fake_ledger.entries() if isinstance(e, Attempt)]
    assert attempts[-1].outcome.state == "failed_unrecoverable"  # runner-derived
    assert attempts[-1].outcome.failing_signals == sorted(attempts[-1].outcome.failing_signals)
    # AC-RC-1: replan fired exactly 2 times (between 1→2 and 2→3, NOT after 3)
    assert replan.await_count == 2


# ---------- AC-SLIDE-1: sliding window with max_attempts=5 ----------

async def test_sliding_window_fires_at_attempt_3_even_with_max_5(
    make_runner, fake_client, strict_and_gate, fake_ledger, gate_ctx
):
    fake_client.set_run_sequence([_run(f"r{i}", 1) for i in range(3)])
    strict_and_gate.set_outcomes([_failed_retryable(["tests"]) for _ in range(3)])
    replan = AsyncMock(spec=ReplanHook, return_value=_applied())

    out = await make_runner(max_attempts=5, replan_hook=replan).run(gate_ctx)

    assert out.state == "failed_unrecoverable"
    assert fake_ledger.count_attempts() == 3
    assert replan.await_count == 2


# ---------- Branch D — replan recovers, identity-faithful carry-forward ----------

async def test_branch_D_retry_recovers_invokes_replan_once(
    make_runner, fake_client, fake_spec_builder, strict_and_gate, fake_ledger, gate_ctx
):
    fake_client.set_run_sequence([_run("r1", 1), _run("r2", 0)])
    strict_and_gate.set_outcomes([_failed_retryable(["tests"]), _passed()])
    applied = _applied(transform_id="tid-2")
    replan = AsyncMock(spec=ReplanHook, return_value=applied)

    out = await make_runner(replan_hook=replan).run(gate_ctx)

    assert out.state == "passed"
    assert out.attempt == AttemptNumber(2)
    assert replan.await_count == 1
    invoked_ctx = replan.await_args.args[0]
    assert len(invoked_ctx.prior_attempts) == 1
    assert invoked_ctx.prior_attempts[-1].sandbox_run_id == "r1"  # AC-WPA-2
    # AC-RO-3: attempt 2's ctx carries the Applied identity-equal
    second_call_ctx = fake_spec_builder.for_gate.call_args_list[1].kwargs.get(
        "ctx", fake_spec_builder.for_gate.call_args_list[1].args[2]
    )
    assert second_call_ctx.transform_output is applied


# ---------- AC-RO-2 / AC-RF-1 — replan returns non-Applied → escalate ----------

@pytest.mark.parametrize(
    "outcome,variant",
    [
        (Skipped(reason="no_recipe"), "skipped"),
        (NotApplicable(reason="no_match"), "not_applicable"),
        (Failed(reason="llm_timeout"), "failed"),
    ],
)
async def test_replan_non_applied_variant_escalates(
    make_runner, fake_client, strict_and_gate, fake_ledger, gate_ctx, outcome, variant, captured_logs
):
    fake_client.set_run_sequence([_run("r1", 1)])
    strict_and_gate.set_outcomes([_failed_retryable(["tests"])])
    replan = AsyncMock(spec=ReplanHook, return_value=outcome)

    out = await make_runner(replan_hook=replan).run(gate_ctx)

    assert out.state == "escalate"
    assert fake_ledger.count_attempts() == 1
    assert any(
        e["event"] == "gates.runner.replan_failed" and e["variant"] == variant
        for e in captured_logs
    )


# ---------- AC-SYN-1 + AC-BACKEND-CLOSE — backend error closes marker ----------

async def test_sandbox_backend_error_synthetic_attempt_closes_marker_and_eventually_escalates(
    make_runner, fake_client, fake_ledger, strict_and_gate, gate_ctx, ordering_parent
):
    fake_client.execute = MagicMock(side_effect=SandboxBackendError("daemon EOF"))
    replan = AsyncMock(spec=ReplanHook, return_value=_applied())

    out = await make_runner(replan_hook=replan).run(gate_ctx)

    assert out.state == "escalate"
    assert fake_ledger.count_attempts() == 3
    assert_marker_ordering(ordering_parent, expected_pairs=3)
    attempts = [e for e in fake_ledger.entries() if isinstance(e, Attempt)]
    for a in attempts:
        assert "sandbox_backend" in a.outcome.failing_signals
        assert a.sandbox_run_id.startswith("backend-error-")


# ---------- AC-MR-1 — missing required signal ----------

async def test_missing_required_signal_escalates_immediately(
    make_runner, fake_client, strict_and_gate, fake_ledger, gate_ctx
):
    fake_client.set_run_sequence([_run("r1", 0)])
    strict_and_gate.evaluate = MagicMock(side_effect=GateMissingRequiredSignal("tests"))
    replan = AsyncMock(spec=ReplanHook)

    out = await make_runner(replan_hook=replan).run(gate_ctx)

    assert out.state == "escalate"
    assert out.failing_signals == ["missing_required_signal"]  # structured, NOT substring
    assert fake_ledger.count_attempts() == 1
    replan.assert_not_awaited()


# ---------- AC-NONE-1 — no replan hook + retryable ----------

async def test_replan_hook_none_with_retryable_failure_escalates(
    make_runner, fake_client, strict_and_gate, fake_ledger, gate_ctx
):
    fake_client.set_run_sequence([_run("r1", 1)])
    strict_and_gate.set_outcomes([_failed_retryable(["tests"])])

    out = await make_runner(replan_hook=None).run(gate_ctx)

    assert out.state == "escalate"
    assert fake_ledger.count_attempts() == 1


# ---------- AC-EX-1 — exhaustion with varying signals → escalate ----------

async def test_exhaustion_with_varying_failing_signals_escalates(
    make_runner, fake_client, strict_and_gate, fake_ledger, gate_ctx
):
    fake_client.set_run_sequence([_run(f"r{i}", 1) for i in range(3)])
    strict_and_gate.set_outcomes([
        _failed_retryable(["tests"]),
        _failed_retryable(["lint"]),
        _failed_retryable(["tests", "lint"]),
    ])
    replan = AsyncMock(spec=ReplanHook, return_value=_applied())

    out = await make_runner(replan_hook=replan).run(gate_ctx)

    assert out.state == "escalate"
    assert fake_ledger.count_attempts() == 3


# ---------- AC-CON-1 / AC-CON-2 — constructor bounds ----------

@pytest.mark.parametrize("bad", [0, -1, 1025, 10_000])
def test_max_attempts_out_of_bounds_rejected(
    fake_client, fake_ledger, fake_spec_builder, strict_and_gate, bad
):
    with pytest.raises(ValueError):
        GateRunner(
            client=fake_client, gate=strict_and_gate, ledger=fake_ledger,
            spec_builder=fake_spec_builder, max_attempts=bad,
        )


# ---------- AC-AT-STAMP-1 — runner stamps attempt on outcome ----------

async def test_runner_stamps_attempt_number_on_returned_outcome(
    make_runner, fake_client, strict_and_gate, gate_ctx
):
    fake_client.set_run_sequence([_run("r1", 1), _run("r2", 0)])
    # Fake outcomes carry NO attempt arg — runner stamps it
    strict_and_gate.set_outcomes([_failed_retryable(["tests"]), _passed()])
    replan = AsyncMock(spec=ReplanHook, return_value=_applied())

    out = await make_runner(replan_hook=replan).run(gate_ctx)

    assert out.attempt == AttemptNumber(2)
    # Fake gate recorded the attempt counter it was invoked with
    assert strict_and_gate.last_eval_attempts == [1, 2]


# ---------- AC-OBS-1 — structured events ----------

async def test_structlog_events_carry_pinned_fields(
    make_runner, fake_client, strict_and_gate, gate_ctx, captured_logs
):
    fake_client.set_run_sequence([_run("r1", 0)])
    strict_and_gate.set_outcomes([_passed()])

    await make_runner(replan_hook=None).run(gate_ctx)

    started = next(e for e in captured_logs if e["event"] == "gates.runner.attempt_started")
    assert {"attempt", "gate_id", "transition_id", "sandbox_spec_hash"} <= started.keys()
    exit_ev = next(e for e in captured_logs if e["event"] == "gates.runner.exit")
    assert {"final_state", "attempt", "total_duration_ms"} <= exit_ev.keys()
    assert exit_ev["final_state"] == "passed"


# ---------- AC-PH-1..PH-3 — pure helpers unit-tested ----------

def test_is_same_failing_signals_3x_empty_returns_false():
    assert not _is_same_failing_signals_3x(deque(maxlen=3), attempt=1)


def test_is_same_failing_signals_3x_two_identical_returns_false():
    h = deque([frozenset({SignalKind("a")}), frozenset({SignalKind("a")})], maxlen=3)
    assert not _is_same_failing_signals_3x(h, attempt=2)


def test_is_same_failing_signals_3x_set_equal_permutations_returns_true_at_3():
    h = deque(
        [
            frozenset({SignalKind("a"), SignalKind("b")}),
            frozenset({SignalKind("b"), SignalKind("a")}),
            frozenset({SignalKind("a"), SignalKind("b")}),
        ],
        maxlen=3,
    )
    assert _is_same_failing_signals_3x(h, attempt=3)


def test_is_same_failing_signals_3x_mixed_returns_false():
    h = deque(
        [
            frozenset({SignalKind("a")}),
            frozenset({SignalKind("b")}),
            frozenset({SignalKind("a")}),
        ],
        maxlen=3,
    )
    assert not _is_same_failing_signals_3x(h, attempt=3)


def test_dispatch_outcome_purity():
    """AC-PH-1: helper takes only data, returns a tag. No I/O imports needed."""
    history = deque([frozenset({SignalKind("a")})], maxlen=3)
    tag = _dispatch_outcome(
        outcome=_passed(),
        attempt=1,
        max_attempts=3,
        has_replan_hook=True,
        history=history,
    )
    assert tag == "return"


# ---------- AC-PROP-1 — Hypothesis property ----------

@given(n=st.integers(min_value=1, max_value=2))
async def test_property_n_retryable_then_pass_returns_attempt_n_plus_1(
    n, make_runner, fake_client, fake_ledger, strict_and_gate, gate_ctx
):
    # Vary signals across attempts to avoid Branch C tripping
    varying = [[f"signal_{i}"] for i in range(n)]
    fake_client.set_run_sequence([_run(f"r{i}", 1) for i in range(n)] + [_run("rOK", 0)])
    strict_and_gate.set_outcomes([_failed_retryable(v) for v in varying] + [_passed()])
    replan = AsyncMock(spec=ReplanHook, return_value=_applied())

    out = await make_runner(max_attempts=n + 1, replan_hook=replan).run(gate_ctx)

    assert out.state == "passed"
    assert out.attempt == AttemptNumber(n + 1)
```

(Helper factories `_run`, `_passed`, `_failed_retryable`, `_gate_escalate`, `_applied` live in `tests/gates/conftest.py`; fakes for `fake_client`, `fake_ledger`, `fake_spec_builder`, `strict_and_gate`, `gate_ctx`, the `ordering_parent` MagicMock with `attach_mock` pre-wired, and the `captured_logs` fixture wrapping `structlog.testing.capture_logs` also live there.)

A separate test file `tests/gates/test_runner_purity.py` houses the AST-walk fences (AC-PURITY-1, AC-PURITY-2, AC-NT-1, AC-PH-1 / AC-PH-4 purity, AC-RH-1 single-await-callee, AC-RO-1 match-node-present).

### Green — make it pass

Smallest implementation: `async def run` with the loop body in §Implementation outline §5. Use `try/except SandboxBackendError` around `client.execute`; `try/except GateMissingRequiredSignal` around `gate.evaluate`. Maintain `history: deque[frozenset[SignalKind]]` with `maxlen=3`. Use `match` on the `RecipeOutcome` variant for the replan dispatch. Construct `outcome.model_copy(update=...)` for every state derivation (never construct fresh `GateOutcome` mid-loop — would drop fields).

### Refactor — clean up

- The `_dispatch_outcome` + `_is_same_failing_signals_3x` extractions land in Green (they're pinned ACs, not refactor luxuries).
- Add module docstrings citing ADR-0001, ADR-0007, production ADR-0014, ADR-0006.
- Optional (not an AC): extract `_run_one_attempt(ctx, attempt, started_at) -> tuple[Attempt, GateOutcome]` if `run()` exceeds ~120 LOC. Marker-before-execute ordering becomes lexical inside the helper.
- Coverage: run `pytest --cov-branch --cov=src/codegenie/gates/runner` and add cases until ≥ 90% branch / ≥ 95% line.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/gates/runner.py` | New module — `GateRunner` class + `_dispatch_outcome` + `_is_same_failing_signals_3x`. |
| `src/codegenie/gates/__init__.py` | Re-export `GateRunner`. |
| `src/codegenie/gates/errors.py` | Confirm `GateMissingRequiredSignal` exists (from S1-04 / S4-05); add the `.missing` typed attribute if not already present. |
| `tests/gates/test_runner_branches.py` | The four-branch + sliding-window + error sub-cases + property tests. |
| `tests/gates/test_pre_execute_marker.py` | Upgrade S2-02's stub to assert ordering against the live runner via `assert_marker_ordering` helper. |
| `tests/gates/test_runner_purity.py` | AST-walk fences: AC-PURITY-1/2, AC-NT-1, AC-PH-1/4, AC-RH-1, AC-RO-1. |
| `tests/gates/conftest.py` | Fakes for `SandboxClient`, `Gate`, `RetryLedger` (with `count_attempts()` / `count_pre_executes()` as documented views over `entries()`), `SandboxSpecBuilder` (with `MagicMock(wraps=...)` for `for_gate` so `call_args_list[i]` works); factory helpers `_run`, `_passed`, `_failed_retryable`, `_gate_escalate`, `_applied`; `ordering_parent` and `captured_logs` fixtures. |
| `tests/fence/test_runner_cold_start.py` | Cold-start fence row for `codegenie.gates.runner` (AC-FENCE-1). |

## Out of scope

- Phase 4 `prior_attempts` kwarg + `FenceWrapper.compose_prior_attempts` — S5-03.
- Stage 6 chokepoint AST test promotion — S5-04.
- VCR-cassette integration against real Phase 4 — S5-05.
- `CostEmitter.emit` wired post-attempt — S7-03 (the hook point is here but the schema lives later).
- Concurrent-remediate flock — S7-04.
- `--max-attempts-override` CLI flag — S8-02.
- Phase-3 typed widening of `GateContext.transform_output` (currently `str` placeholder per S1-04 HARDENED) — until then, Branch D's `model_copy(update={"transform_output": applied})` writes the `Applied` instance into a placeholder-typed field; the runner does NOT coerce (S5-01 HARDENED AC-FWD-1).

## Notes for the implementer

- The pre-execute marker is the single most load-bearing assertion in this story. Use `parent.attach_mock` (or `unittest.mock.Mock.assert_has_calls(any_order=False)`) — do **not** use timestamps; tests must not race.
- `ctx.with_prior_attempt(outcome, sandbox_run_id=run.run_id)` is the **only** legal mutation (per S1-04 HARDENED widening). The composite `ctx = ctx.with_prior_attempt(...).model_copy(update={"transform_output": applied})` is a SINGLE atomic statement — never two separate assignments that leave a transient ctx with new `prior_attempts` and old `transform_output` visible.
- `ReplanHook` is `async`. The only `await` site in `run()` is `await self.replan_hook(ctx)`. Every other call (`client.execute`, `ledger.record`, `gate.evaluate`, `spec_builder.for_gate`) is sync. The async/sync boundary is sharp and intentional — Phase 5's probabilistic surface is exactly one node (per arch §Determinism).
- `RecipeOutcome` is `Applied | Skipped | NotApplicable | Failed`. Dispatch via `match recipe_outcome: case Applied(): ...; case Skipped() | NotApplicable() | Failed(): ...` — NEVER `recipe_outcome.kind == "applied"` (CLAUDE.md "tagged union > anaemic dict"). `Applied` exposes `transform_id`, `plugin_id`, `recipe_id` — no `.diff`, no `.transform_output`.
- `GateOutcome` is frozen. Every state derivation (`failed_unrecoverable`, `escalate`, attempt-stamp) MUST use `outcome.model_copy(update=...)`. Constructing a fresh `GateOutcome(...)` drops `failing_signals`, `summary`, `signals` and the next replay will diverge.
- `SandboxBackendError` synthetic attempts MUST carry an `ObjectiveSignals()` (all sub-models `None`) so the JSONL line conforms to `Attempt.outcome.signals`'s required-not-null shape.
- Same-signature detection compares `frozenset(failing_signals)` (set-equal, order-insensitive). The deque is `maxlen=3` regardless of `max_attempts` — the detector is a sliding window, not a hard floor (`max_attempts=5` with three identical failures still triggers at attempt 3).
- The synthetic-error-outcome path occurs at exactly TWO call sites (backend error + missing signal). Per Rule 2, INLINE both. If a third site lands in S5-05 / S6+ (Firecracker timeout, cassette retry exhaustion), extract `_synthetic_error_outcome(error_kind, attempt, signals) -> GateOutcome` at that point — not before.
- Resist adding cost emission, metrics emission, or trace span management here — `CostEmitter` lands in S7-03 with a clean hook point; tracing per `phase-arch-design.md §Observability` is a separate concern. Keep this module ≤ 250 LOC (allowing for the pure helpers and the four `match` branches).
- The static fence test `tests/schema/test_no_subprocess_outside_build_chokepoint.py` must remain green — `runner.py` must not import `subprocess`. AC-PURITY-2 + AC-FENCE-1 enforce this structurally.
- `GateRunner` is the inbound port; its five constructor deps (`SandboxClient`, `Gate`, `RetryLedger`, `SandboxSpecBuilder`, `ReplanHook`) are outbound ports. Every adapter swap (Firecracker `SandboxClient` in S6-01, alternative gate from S4-06+, alternative replan strategy for Phase 6's LangGraph) is a composition-root change — NEVER an edit to `runner.py`. Kernel-extract (`@register_runner` / `@register_retry_strategy`) is deferred until N=3 concrete consumers exist.
- The `_dispatch_outcome` helper returns a `Literal["return", "escalate", "failed_unrecoverable", "continue"]` closed sum. `run()` matches on it. If a future story adds a fifth branch (e.g., "human-in-the-loop pause"), the Literal widens AND `run()` adds one `case` arm — Open/Closed at the dispatch boundary.
