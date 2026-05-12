# Story S5-02 — `GateRunner.run` three-retry loop + all four branches

**Step:** Step 5 — GateRunner three-retry loop + Phase 4 replan_hook integration
**Status:** Ready
**Effort:** L
**Depends on:** S2-02, S4-05, S5-01
**ADRs honored:** ADR-0001, ADR-0007, ADR-0014 (phase) ; production ADR-0014 (three-retry default)

## Context

`GateRunner` is the *exactly-once* implementation of the three-retry loop the entire phase exists to ship (per `phase-arch-design.md §Component design — GateRunner` and production ADR-0014). It composes everything S1-S4 landed: `SandboxSpecBuilder.for_gate`, `SandboxClient.execute`, the six signal collectors, `StrictAndGate.evaluate`, and `RetryLedger.record_pre_execute`/`record`. The loop has four mutually exclusive exit branches (`passed`, `escalate`, `failed_unrecoverable`, replan-and-continue); each must be tested independently and the union must reach ≥ 90% branch coverage. The pre-execute marker (Gap 1, ADR-0007) must be written **before** `client.execute()` runs, not after — this story enforces that ordering.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — GateRunner` — public interface, internal structure (the six-step loop body), performance envelope, failure behavior.
  - `../phase-arch-design.md §Process view §Scenario 1 (happy)` — first-attempt-passes sequence.
  - `../phase-arch-design.md §Process view §Scenario 2 (retry recovers)` — the central scenario this loop implements.
  - `../phase-arch-design.md §Process view §Scenario 3 (test removed)` — `failed_unrecoverable` on same `failing_signals` 3×.
  - `../phase-arch-design.md §Process view §Scenario 4 (docker daemon dies)` — `SandboxBackendError` counts as a failing attempt.
  - `../phase-arch-design.md §Edge cases §17` — same-signature 3× → `failed_unrecoverable` (exit 12), distinct from `escalate` (exit 11).
- **Phase ADRs:**
  - `../ADRs/0001-two-chokepoint-sandbox-seam.md` — `GateRunner` is the only consumer of `SandboxClient`; Stage 6's previous direct `validation.*` call routes through it.
  - `../ADRs/0007-pre-execute-marker-for-resume-safety.md` — `record_pre_execute(attempt_id, sandbox_spec_hash, started_at)` is called **before** `client.execute`; the marker write is BLAKE3-chained.
  - `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — `ObjectiveSignals` is the only signal carrier; this story consumes it but does not extend it.
- **Production ADRs:**
  - `../../../production/adrs/0014-three-retry-default-per-gate.md` — `max_attempts: int = 3` default; override path requires `--operator-ack`.
- **Source design:**
  - `../final-design.md §Synthesis ledger — Three-retry loop + replan_hook row`.
- **Existing code:**
  - `src/codegenie/gates/contract.py` (S1-04, S5-01) — `Gate`, `GateContext`, `GateOutcome`, `RetryPolicy`, `AttemptSummary`, `ReplanHook`.
  - `src/codegenie/gates/retry_ledger.py` (S2-01, S2-02) — `record_pre_execute`, `record`, `head`.
  - `src/codegenie/sandbox/contract.py` — `SandboxClient`, `SandboxSpec`, `SandboxRun`.
  - `src/codegenie/sandbox/spec_builder.py` (S3-01) — `SandboxSpecBuilder.for_gate`.
  - `src/codegenie/sandbox/signals/registry.py` (S1-05, S4-01..S4-04) — signal-kind registry.
  - `src/codegenie/gates/strict_and.py` (S4-05) — `StrictAndGate.evaluate`.

## Goal

Implement `GateRunner.run(ctx) -> GateOutcome` with a plain `for attempt in 1..max_attempts` loop that writes the pre-execute marker before every `client.execute`, records every attempt, and dispatches to the four mutually exclusive exit branches; ≥ 90% branch coverage on `runner.py`.

## Acceptance criteria

- [ ] `GateRunner(*, client: SandboxClient, gate: Gate, ledger: RetryLedger, spec_builder: SandboxSpecBuilder, max_attempts: int = 3, replan_hook: ReplanHook | None = None)` constructor matches the signature in `../phase-arch-design.md §Component design`; `max_attempts` default is `3` (production ADR-0014) and a runtime check rejects `max_attempts < 1`.
- [ ] `GateRunner.run(ctx: GateContext) -> GateOutcome` writes a `record_pre_execute(attempt_id, spec.sandbox_spec_hash, started_at=now())` ledger line **before** `client.execute(spec)` is called; verified by an `unittest.mock` `call_args_list` ordering assertion on a single `MagicMock` (per ADR-0007 — Gap 1).
- [ ] Branch A — happy: when `gate.evaluate(...)` returns `GateOutcome(state="passed")` on attempt 1, `run` returns it without invoking `replan_hook`; ledger has exactly one `attempt` line plus one `pre_execute` line.
- [ ] Branch B — non-retryable: when `gate.evaluate(...)` returns `GateOutcome(retryable=False)` (e.g., `trace` failure per the YAML's `non_retryable_failures`), `run` returns `GateOutcome(state="escalate")` immediately; no `replan_hook` invocation; ledger has exactly one attempt line.
- [ ] Branch C — `failed_unrecoverable`: when three consecutive attempts produce **identical** `failing_signals` lists (set-equal, order-insensitive), `run` returns `GateOutcome(state="failed_unrecoverable")` and the ledger has exactly three attempt lines; the third `Attempt.outcome.state` is also `"failed_unrecoverable"`.
- [ ] Branch D — replan-and-continue → eventual pass: when attempt 1 fails retryably and attempt 2 passes, `run` returns `GateOutcome(state="passed", attempt=2)`; `replan_hook` is invoked exactly once with a `GateContext` whose `prior_attempts` has length 1; `ctx.transform_output` is replaced with the hook's `RecipeApplication` before attempt 2's spec is built.
- [ ] `SandboxBackendError` raised by `client.execute` is caught, recorded as an attempt with `state="failed_retryable"` and `failing_signals=["sandbox_backend"]`, and counts toward `max_attempts`; after `max_attempts` exhausted on backend errors, `run` returns `GateOutcome(state="escalate")` (Scenario 4 — Docker daemon dies).
- [ ] `GateMissingRequiredSignal` raised by `gate.evaluate` is **not** retried — `run` returns `GateOutcome(state="escalate")` immediately and the attempt is recorded with a structured `details["reason"] == "missing_required_signal"`.
- [ ] When `replan_hook is None` and a retry would be needed, `run` returns `GateOutcome(state="escalate")` (no hook = no way to produce a different patch); ledger records the exhausting attempt explicitly.
- [ ] `tests/gates/test_runner_branches.py` covers all four branches plus the two error sub-cases; `pytest --cov=src/codegenie/gates/runner --cov-branch` reports ≥ 90% branch and ≥ 95% line.
- [ ] `tests/gates/test_pre_execute_marker.py` (the test S2-02 stubbed) is upgraded to assert ordering against the live `GateRunner` (not just `RetryLedger` in isolation).
- [ ] Structured `structlog` events emitted: `gates.runner.attempt_started`, `gates.runner.attempt_recorded`, `gates.runner.replan_invoked`, `gates.runner.exit` (with `final_state`). Events match the constants registered in S1-01.
- [ ] `mypy --strict src/codegenie/gates/runner.py` passes; no `Any` in the public signature.
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff`, `mypy --strict`, `pytest tests/gates/test_runner_branches.py tests/gates/test_pre_execute_marker.py` pass.

## Implementation outline

1. Create `src/codegenie/gates/runner.py` with a `class GateRunner` dataclass-style constructor (`__init__` with keyword-only args matching the signature).
2. Implement `_build_attempt(...)` and `_collect_signals(run, ctx)` private helpers — the latter iterates `self.gate.required_signals` and calls registered collectors via the `sandbox.signals.registry`.
3. The loop body (per `phase-arch-design.md §Component design — GateRunner` step list):
   1. `started_at = datetime.now(UTC)`; `spec = self.spec_builder.for_gate(self.gate, attempt, ctx)`.
   2. `self.ledger.record_pre_execute(attempt, spec.sandbox_spec_hash, started_at)` — **before any execute**.
   3. Try `run = self.client.execute(spec)`; on `SandboxBackendError`, jump to the synthetic-backend-failure path (record + continue if retries remain).
   4. `signals = self._collect_signals(run, ctx)`; on `GateMissingRequiredSignal`, record + return `escalate`.
   5. `outcome = self.gate.evaluate(signals, ctx)`.
   6. `self.ledger.record(Attempt(...))`.
   7. Dispatch: `passed → return`; `not retryable → return escalate`; same-failing-signals-3× → return `failed_unrecoverable`; else if `replan_hook` and `attempt < max_attempts`: `ctx = ctx.with_prior_attempt(outcome)`; `ctx.transform_output = self.replan_hook(ctx)`; continue.
4. Same-failing-signals detection: compare `frozenset(outcome.failing_signals)` for the last three attempts; if `len(deduped) == 1 and attempt == max_attempts`, return `failed_unrecoverable`.
5. Emit structlog events at every branch.
6. Loop exhaustion without pass → `GateOutcome(state="escalate")`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/gates/test_runner_branches.py`

```python
# tests/gates/test_runner_branches.py
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from codegenie.gates.contract import GateContext, GateOutcome
from codegenie.gates.errors import GateMissingRequiredSignal, SandboxBackendError
from codegenie.gates.runner import GateRunner


@pytest.fixture
def make_runner(fake_ledger, fake_spec_builder, fake_client, strict_and_gate):
    def _make(*, max_attempts: int = 3, replan_hook=None):
        return GateRunner(
            client=fake_client,
            gate=strict_and_gate,
            ledger=fake_ledger,
            spec_builder=fake_spec_builder,
            max_attempts=max_attempts,
            replan_hook=replan_hook,
        )
    return _make


def test_branch_A_first_attempt_passes_returns_passed_no_replan(
    make_runner, fake_client, fake_ledger, strict_and_gate, gate_ctx
):
    fake_client.set_run_sequence([_run_id("r1", exit_code=0)])
    strict_and_gate.set_outcomes([_passed_outcome(attempt=1)])
    replan = MagicMock()

    out = make_runner(replan_hook=replan).run(gate_ctx)

    assert out.state == "passed"
    assert out.attempt == 1
    replan.assert_not_called()
    assert fake_ledger.count_attempts() == 1
    assert fake_ledger.count_pre_executes() == 1


def test_pre_execute_marker_written_before_execute_for_every_attempt(
    make_runner, fake_client, fake_ledger, strict_and_gate, gate_ctx
):
    fake_client.set_run_sequence([_run_id("r1", 1), _run_id("r2", 0)])
    strict_and_gate.set_outcomes([_failed_retryable_outcome([\"tests\"]), _passed_outcome(attempt=2)])

    spy = MagicMock()
    fake_client.execute = MagicMock(side_effect=fake_client.execute)
    fake_ledger.record_pre_execute = MagicMock(side_effect=fake_ledger.record_pre_execute)
    # Single mock to capture ordering
    parent = MagicMock()
    parent.attach_mock(fake_ledger.record_pre_execute, \"pre_execute\")
    parent.attach_mock(fake_client.execute, \"execute\")

    make_runner(replan_hook=MagicMock(return_value=_fake_recipe_app())).run(gate_ctx)

    names = [c[0] for c in parent.mock_calls]
    # Strict ordering for each attempt: pre_execute, then execute, repeating
    assert names == [\"pre_execute\", \"execute\", \"pre_execute\", \"execute\"]


def test_branch_B_non_retryable_failure_returns_escalate_no_replan(
    make_runner, fake_client, strict_and_gate, fake_ledger, gate_ctx
):
    fake_client.set_run_sequence([_run_id(\"r1\", 1)])
    strict_and_gate.set_outcomes([_failed_non_retryable_outcome([\"trace\"])])
    replan = MagicMock()

    out = make_runner(replan_hook=replan).run(gate_ctx)

    assert out.state == \"escalate\"
    replan.assert_not_called()
    assert fake_ledger.count_attempts() == 1


def test_branch_C_same_failing_signals_three_times_returns_failed_unrecoverable(
    make_runner, fake_client, strict_and_gate, fake_ledger, gate_ctx
):
    fake_client.set_run_sequence([_run_id(f\"r{i}\", 1) for i in range(3)])
    strict_and_gate.set_outcomes(
        [_failed_retryable_outcome([\"tests\"]) for _ in range(3)]
    )

    out = make_runner(
        replan_hook=MagicMock(return_value=_fake_recipe_app())
    ).run(gate_ctx)

    assert out.state == \"failed_unrecoverable\"
    assert fake_ledger.count_attempts() == 3
    # Third recorded attempt's outcome state is also failed_unrecoverable
    assert fake_ledger.attempts()[-1].outcome.state == \"failed_unrecoverable\"


def test_branch_D_retry_recovers_invokes_replan_once_and_replaces_transform_output(
    make_runner, fake_client, strict_and_gate, fake_ledger, gate_ctx
):
    fake_client.set_run_sequence([_run_id(\"r1\", 1), _run_id(\"r2\", 0)])
    strict_and_gate.set_outcomes([
        _failed_retryable_outcome([\"tests\"]),
        _passed_outcome(attempt=2),
    ])
    new_recipe = _fake_recipe_app(diff=b\"+ patched\\n\")
    replan = MagicMock(return_value=new_recipe)

    out = make_runner(replan_hook=replan).run(gate_ctx)

    assert out.state == \"passed\"
    assert out.attempt == 2
    assert replan.call_count == 1
    invoked_ctx: GateContext = replan.call_args.args[0]
    assert len(invoked_ctx.prior_attempts) == 1
    # ctx.transform_output was replaced before attempt 2's spec build
    assert fake_spec_builder.last_ctx.transform_output is new_recipe.transform_output


def test_sandbox_backend_error_counts_as_failing_attempt_and_eventually_escalates(
    make_runner, fake_client, fake_ledger, strict_and_gate, gate_ctx
):
    fake_client.execute = MagicMock(side_effect=SandboxBackendError(\"daemon EOF\"))

    out = make_runner(replan_hook=MagicMock(return_value=_fake_recipe_app())).run(gate_ctx)

    assert out.state == \"escalate\"
    assert fake_ledger.count_attempts() == 3
    assert all(\"sandbox_backend\" in a.outcome.failing_signals for a in fake_ledger.attempts())


def test_missing_required_signal_escalates_immediately(
    make_runner, fake_client, strict_and_gate, fake_ledger, gate_ctx
):
    fake_client.set_run_sequence([_run_id(\"r1\", 0)])
    strict_and_gate.evaluate = MagicMock(side_effect=GateMissingRequiredSignal(\"tests\"))

    out = make_runner(replan_hook=MagicMock()).run(gate_ctx)

    assert out.state == \"escalate\"
    assert fake_ledger.count_attempts() == 1
    assert fake_ledger.attempts()[0].outcome.summary.startswith(\"missing_required_signal\")


def test_replan_hook_none_with_retryable_failure_escalates(
    make_runner, fake_client, strict_and_gate, fake_ledger, gate_ctx
):
    fake_client.set_run_sequence([_run_id(\"r1\", 1)])
    strict_and_gate.set_outcomes([_failed_retryable_outcome([\"tests\"])])

    out = make_runner(replan_hook=None).run(gate_ctx)

    assert out.state == \"escalate\"
    assert fake_ledger.count_attempts() == 1


def test_max_attempts_below_one_rejected_at_construction(
    fake_client, fake_ledger, fake_spec_builder, strict_and_gate
):
    with pytest.raises(ValueError):
        GateRunner(
            client=fake_client, gate=strict_and_gate, ledger=fake_ledger,
            spec_builder=fake_spec_builder, max_attempts=0,
        )
```

(Helper factories `_run_id`, `_passed_outcome`, `_failed_retryable_outcome`, `_failed_non_retryable_outcome`, `_fake_recipe_app` live in `tests/gates/conftest.py`; fakes for `fake_client`, `fake_ledger`, `fake_spec_builder`, `strict_and_gate`, `gate_ctx` also live there.)

### Green — make it pass

Smallest implementation: a single `run` method with the six-step loop body. Use `try/except SandboxBackendError` around `client.execute`; use `try/except GateMissingRequiredSignal` around `gate.evaluate`. Track last three `failing_signals` as `collections.deque(maxlen=3)`; check `frozenset` equality at the end of each iteration when `len(deque) == max_attempts`.

### Refactor — clean up

- Extract `_dispatch_outcome(outcome, attempt, history) -> Literal["return", "escalate", "failed_unrecoverable", "continue"]` so each branch is one line in the loop.
- Replace `MagicMock` ordering trick with `parent.attach_mock` documented in the test.
- Add docstrings citing ADR-0001 (Stage 6 chokepoint), ADR-0007 (pre-execute marker), production ADR-0014 (three-retry).
- Ensure `gates.runner.exit` event includes `final_state`, `attempt`, `total_duration_ms`.
- Coverage: invoke `pytest --cov-branch` and add cases until ≥ 90% branch; the three error sub-cases plus four branches should comfortably exceed.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/gates/runner.py` | New module — `GateRunner` class. |
| `src/codegenie/gates/errors.py` | Add `GateMissingRequiredSignal` if not already present from S1-04. |
| `src/codegenie/gates/__init__.py` | Re-export `GateRunner`. |
| `tests/gates/test_runner_branches.py` | The four-branch + error tests. |
| `tests/gates/test_pre_execute_marker.py` | Upgrade S2-02's stub to assert ordering against live runner. |
| `tests/gates/conftest.py` | Fakes for `SandboxClient`, `Gate`, `RetryLedger`, `SandboxSpecBuilder` and `GateContext` factory. |

## Out of scope

- Phase 4 `prior_attempts` kwarg + `FenceWrapper.compose_prior_attempts` — S5-03.
- Stage 6 chokepoint AST test promotion — S5-04.
- VCR-cassette integration against real Phase 4 — S5-05.
- `CostEmitter.emit` wired post-attempt — S7-03 (the hook point is here but the schema lives later).
- Concurrent-remediate flock — S7-04.
- `--max-attempts-override` CLI flag — S8-02.

## Notes for the implementer

- The pre-execute marker is the single most-load-bearing assertion in this story. Use `parent.attach_mock` (or `unittest.mock.Mock.assert_has_calls(any_order=False)`) — do **not** use timestamps; tests must not race.
- `ctx.with_prior_attempt(outcome)` returns a new frozen `GateContext` (since the model is `frozen=True`); replace the local `ctx` reference, do not try to mutate.
- `ctx.transform_output = replan_hook(ctx)` — since `GateContext` is frozen, this is really a `ctx = ctx.model_copy(update={"transform_output": replan_hook(ctx).transform_output})`. Keep the assignment in one place in the loop body.
- `SandboxBackendError` synthetic attempts must still carry an `ObjectiveSignals` (empty) so the JSONL line conforms to `Attempt`'s schema — see the Scenario 4 sequence.
- The same-signature detector compares **sets**, not lists, so failing-signals order from collectors does not flip the verdict.
- Resist adding cost emission, metrics emission, or trace span management here — `CostEmitter` lands in S7-03 with a clean hook point; tracing per `phase-arch-design.md §Observability` is a separate concern. Keep this module ≤ 200 LOC.
- The static fence test `tests/schema/test_no_subprocess_outside_build_chokepoint.py` must remain green — `runner.py` must not import `subprocess`.
