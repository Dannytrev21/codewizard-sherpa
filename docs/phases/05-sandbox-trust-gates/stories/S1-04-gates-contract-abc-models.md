# Story S1-04 — `gates/contract.py` — `Gate` ABC, `GateContext`, `GateOutcome`, `RetryPolicy`, `AttemptSummary`, `TransitionId`

**Step:** Step 1 — Scaffold packages, contracts, and CI fences
**Status:** Ready
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0006, ADR-0002, ADR-0014, ADR-0008

## Context

`Gate` is one of the three load-bearing public abstractions in Phase 5 — the strict-AND scoring surface. Per ADR-0006, `Gate` is declared as an ABC (subclasses share `gate_id`/`required_signals`/`retry_policy` defaults) whereas `SandboxClient` is a Protocol. This story ships the abstract base plus the four frozen Pydantic models the gate seam exchanges with the runner, the orchestrator, and Phase 4 — `GateContext` (orchestrator → runner), `GateOutcome` (gate → runner / orchestrator), `RetryPolicy` (YAML → gate), `AttemptSummary` (runner → Phase 4 via `prior_attempts`), plus the `TransitionId` enum and the internal `Attempt` model the ledger writes.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Gate (ABC) + StrictAndGate` — exact `Gate` signature with `gate_id`, `required_signals: tuple[SignalKind, ...]`, `retry_policy`, `evaluate` abstract method.
  - `../phase-arch-design.md §Data model — gates/contract.py` — pseudo-code for `RetryPolicy`, `AttemptSummary`, `GateContext`, `GateOutcome`, `TransitionId`, `Attempt`.
  - `../phase-arch-design.md §Component design — GateRunner` — confirms `GateContext.with_prior_attempt(outcome) -> GateContext`.
  - `../phase-arch-design.md §Edge case 17` + `§Control flow` — `state` ∈ `{"passed", "failed_retryable", "failed_unrecoverable", "escalate"}` semantics.
  - `../phase-arch-design.md §Integration with Phase 6` — `GateOutcome.state` maps to LangGraph `Command(goto=...) / interrupt()`.
- **Phase ADRs (rules this story honors):**
  - `../ADRs/0006-protocol-vs-abc-convention.md` — ADR-0006 — `Gate` is `abc.ABC`.
  - `../ADRs/0002-additive-prior-attempts-kwarg.md` — ADR-0002 — `AttemptSummary` is the structured retry-feedback payload; Phase 4's kwarg landing site.
  - `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — ADR-0014 — `Attempt.signals: ObjectiveSignals` and `GateOutcome.signals: ObjectiveSignals` inherit the static invariant; no new banned-substring fields here.
  - `../ADRs/0008-llm-judge-persona-deferral.md` — ADR-0008 — `AttemptSummary.prior_failure_summary` is fence-wrapped text, not LLM-generated trust input.
- **Source design:**
  - `../final-design.md §Component-3` (Gate) and `§Component-6` (AttemptSummary contract).
- **High-level impl:**
  - `../High-level-impl.md §Step 1 — Features delivered` bullet 4.

## Goal

Ship `src/codegenie/gates/contract.py` exposing the `Gate` ABC, the `TransitionId` enum, the `ReplanHook` Protocol placeholder, and the six frozen `extra="forbid"` Pydantic models (`RetryPolicy`, `AttemptSummary`, `GateContext`, `GateOutcome`, `Attempt`).

## Acceptance criteria

- [ ] `from codegenie.gates.contract import Gate, GateContext, GateOutcome, RetryPolicy, AttemptSummary, TransitionId, Attempt, ReplanHook, SignalKind` all succeed.
- [ ] `Gate` is an `abc.ABC` subclass; instantiating `Gate(...)` directly raises `TypeError`; a concrete subclass that omits `evaluate` raises `TypeError`; one with `evaluate` instantiates.
- [ ] `TransitionId` is an `Enum(str, Enum)` with members `STAGE6_VALIDATE = "stage6_validate"` and `STAGE6_VALIDATE_LOOSE = "stage6_validate_loose"` and rejects unknown values.
- [ ] `GateOutcome.state` is `Literal["passed", "failed_retryable", "failed_unrecoverable", "escalate"]`; constructing with any other value raises `ValidationError`.
- [ ] `GateContext.prior_attempts` defaults to `[]`; `GateContext.with_prior_attempt(outcome)` returns a new `GateContext` (frozen) with `prior_attempts` appended (length increases by 1; original untouched).
- [ ] `AttemptSummary` rejects `prior_failure_summary` strings > 4096 characters (the 4 KB cap from arch §Data model and §Harness engineering).
- [ ] `Attempt.prev_hash` and `Attempt.chain_hash` are 32-char hex strings (BLAKE3-128); shorter strings raise `ValidationError`.
- [ ] All seven models carry `model_config = ConfigDict(extra="forbid", frozen=True)`; every model rejects unknown fields and mutation.
- [ ] `ReplanHook` is `@runtime_checkable Protocol` with one method `__call__(self, ctx: GateContext) -> RecipeApplication` (forward-ref to Phase 3 type; story S5-01 supplies the full integration test).
- [ ] TDD plan's red tests exist, are committed, and are green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/gates/contract.py`, `pytest tests/gates/test_contract_models.py tests/gates/test_gate_abc.py` all pass.
- [ ] Branch coverage on `gates/contract.py` ≥ 95% (95/90 floor from `stories/README.md`).

## Implementation outline

1. Create `src/codegenie/gates/contract.py`. Import `abc.ABC`, `abc.abstractmethod`, `enum.Enum`, `typing.Protocol`, `runtime_checkable`, `Literal`, `pydantic.BaseModel`, `ConfigDict`, plus `ObjectiveSignals` from S1-03.
2. Define `SignalKind = str` (open registry per ADR-0003; not a closed Literal).
3. Define `TransitionId(str, Enum)` with the two members.
4. Define `RetryPolicy` (`max_attempts`, `retryable_failures`, `non_retryable_failures`, `timeout_retryable`).
5. Define `AttemptSummary` with a `field_validator` capping `prior_failure_summary` length.
6. Define `GateOutcome` with the `state` Literal and `signals: ObjectiveSignals`.
7. Define `GateContext` with `prior_attempts: list[AttemptSummary] = []` and the `with_prior_attempt` method that returns a new frozen copy (use `model_copy(update={"prior_attempts": [...]})`).
8. Define `Attempt` (internal) per the pseudo-code.
9. Declare the `Gate` ABC with the abstract `evaluate` method and the three class attributes `gate_id`, `required_signals`, `retry_policy`.
10. Declare `ReplanHook` Protocol.
11. Write the two test files.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/gates/test_contract_models.py`, `tests/gates/test_gate_abc.py`.

```python
# tests/gates/test_contract_models.py
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pydantic import ValidationError
from codegenie.gates.contract import (
    GateContext, GateOutcome, RetryPolicy, AttemptSummary,
    TransitionId, Attempt,
)
from codegenie.sandbox.signals.models import ObjectiveSignals

def _attempt_summary(**overrides):
    base = dict(
        attempt_id=1, sandbox_run_id="run-1",
        failing_signals=["tests"],
        prior_failure_summary="failed: jwt.test.ts",
        evidence_paths={"stdout": Path("/tmp/o")},
    )
    base.update(overrides)
    return AttemptSummary(**base)

def test_transition_id_enum_values():
    assert TransitionId.STAGE6_VALIDATE.value == "stage6_validate"
    assert TransitionId.STAGE6_VALIDATE_LOOSE.value == "stage6_validate_loose"

def test_outcome_state_literal_rejects_unknown():
    with pytest.raises(ValidationError):
        GateOutcome(
            passed=False, attempt=1, failing_signals=[], retryable=False,
            state="weird_state", summary="x", signals=ObjectiveSignals(),
        )

def test_attempt_summary_caps_prior_failure_summary_at_4kb():
    with pytest.raises(ValidationError):
        _attempt_summary(prior_failure_summary="x" * 4097)

def test_attempt_summary_accepts_exactly_4096():
    s = _attempt_summary(prior_failure_summary="x" * 4096)
    assert len(s.prior_failure_summary) == 4096

def test_gate_context_prior_attempts_defaults_empty():
    ctx = GateContext(
        worktree=Path("/repo"), advisory="adv-fixture",
        recipe="recipe-fixture", transform_output="to-fixture",
        workflow_id="wf-1", run_id="r-1",
    )
    assert ctx.prior_attempts == []

def test_gate_context_with_prior_attempt_returns_new_immutable_copy():
    ctx = GateContext(
        worktree=Path("/repo"), advisory="adv", recipe="rec",
        transform_output="to", workflow_id="wf", run_id="r",
    )
    outcome = GateOutcome(
        passed=False, attempt=1, failing_signals=["tests"],
        retryable=True, state="failed_retryable",
        summary="tests failed", signals=ObjectiveSignals(),
    )
    new_ctx = ctx.with_prior_attempt(outcome)
    assert new_ctx is not ctx
    assert len(new_ctx.prior_attempts) == 1
    assert len(ctx.prior_attempts) == 0   # original untouched

def test_attempt_prev_hash_must_be_blake3_128_hex():
    with pytest.raises(ValidationError):
        Attempt(
            attempt_id=1, sandbox_run_id="r1",
            signals=ObjectiveSignals(),
            outcome=GateOutcome(
                passed=True, attempt=1, failing_signals=[], retryable=False,
                state="passed", summary="ok", signals=ObjectiveSignals(),
            ),
            started_at=datetime.now(timezone.utc),
            ended_at=datetime.now(timezone.utc),
            prev_hash="tooshort",  # must be 32 hex chars
            chain_hash="0" * 32,
        )

def test_models_are_frozen_and_extra_forbid():
    rp = RetryPolicy(max_attempts=3, retryable_failures=["tests"], non_retryable_failures=["trace"])
    with pytest.raises(ValidationError):
        rp.max_attempts = 5
    with pytest.raises(ValidationError):
        RetryPolicy(max_attempts=3, retryable_failures=[], non_retryable_failures=[], extra="boom")
```

```python
# tests/gates/test_gate_abc.py
import pytest
from codegenie.gates.contract import Gate, GateContext, GateOutcome, RetryPolicy
from codegenie.sandbox.signals.models import ObjectiveSignals

def test_gate_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        Gate()

def test_subclass_missing_evaluate_cannot_instantiate():
    class Incomplete(Gate):
        gate_id = "x"
        required_signals = ()
        retry_policy = RetryPolicy(max_attempts=3, retryable_failures=[], non_retryable_failures=[])
    with pytest.raises(TypeError):
        Incomplete()

def test_concrete_subclass_works():
    class Always(Gate):
        gate_id = "always"
        required_signals = ()
        retry_policy = RetryPolicy(max_attempts=3, retryable_failures=[], non_retryable_failures=[])
        def evaluate(self, os, ctx):
            return GateOutcome(
                passed=True, attempt=1, failing_signals=[], retryable=False,
                state="passed", summary="ok", signals=os,
            )
    g = Always()
    out = g.evaluate(ObjectiveSignals(), None)
    assert out.passed is True and out.state == "passed"
```

Run; confirm `ImportError`, commit, then implement.

### Green — make it pass

Implement `contract.py` minimally. For `with_prior_attempt`, use Pydantic's `model_copy(update={"prior_attempts": self.prior_attempts + [AttemptSummary.from_outcome(outcome)]})` — the `from_outcome` classmethod on `AttemptSummary` is a small convenience that pulls `attempt_id`/`failing_signals`/`prior_failure_summary` out of the outcome. (Add this classmethod here; the *prompt builder* helper in S5-03 only operates on lists of `AttemptSummary`.) Validate `prev_hash`/`chain_hash` via a `field_validator(mode="after")` that checks length 32 and `int(v, 16)` parsability.

### Refactor — clean up

- ADR-0014 inheritance: confirm `Attempt.signals: ObjectiveSignals` and `GateOutcome.signals: ObjectiveSignals` continue to enforce the static-introspection invariant transitively. (Re-run `tests/sandbox/test_objective_signals_introspection.py` after this story; field names on `Attempt` and `GateOutcome` themselves should also be scanned — confirm `attempts.jsonl` payload key names contain no banned substring.)
- Add a docstring on `Gate.evaluate` noting "raises `GateMissingRequiredSignal` if a `required_signals` element is None on `os`" — the actual raise happens in `StrictAndGate` (S4-05), but the contract is documented here.
- `ReplanHook` Protocol can take a forward-ref `RecipeApplication` — use `TYPE_CHECKING` guard for the import to avoid a circular dep at runtime; the integration contract test is S5-01.
- Edge case (arch §Edge case 17): `failed_unrecoverable` is a state, not an exception — keep `GateOutcome.state` as the only place this lives.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/gates/contract.py` | New file — Gate ABC + six contract models per ADR-0006/0002/0014 |
| `tests/gates/test_contract_models.py` | New test — model invariants (frozen, extra-forbid, literal, length cap, hex validators) |
| `tests/gates/test_gate_abc.py` | New test — ABC abstract method enforcement |

## Out of scope

- **`StrictAndGate` implementation** — S4-05.
- **`GateRunner.run` retry loop** — S5-02.
- **`@register_signal_kind`** — S1-05.
- **`ReplanHook` integration / VCR contract test** — S5-01.
- **`FenceWrapper.compose_prior_attempts`** — S5-03 (Phase 4 prompt builder consumes `prior_failure_summary`).
- **YAML catalog loader** — S1-06.

## Notes for the implementer

- Choosing **between** `field_validator` and `model_validator(mode="after")` for the BLAKE3 hex check: a per-field `@field_validator("prev_hash", "chain_hash")` is cleaner and reusable. Pattern: assert `len(v) == 32 and set(v) <= set("0123456789abcdef")` — both must hold.
- The `with_prior_attempt` contract returns a new frozen `GateContext`. Pydantic's `model_copy(update=..., deep=False)` is correct here; do not use `deep=True` because `worktree: Path` and other refs are immutable.
- `AttemptSummary.from_outcome(outcome)` — make this a `@classmethod` on `AttemptSummary`. It maps `outcome.attempt → attempt_id`, `outcome.failing_signals → failing_signals`, `outcome.summary → prior_failure_summary` (truncated to 4096 chars; FenceWrapper sanitizes; this story just enforces the length cap), and pulls `sandbox_run_id`/`evidence_paths` from the outcome's `signals` provenance (use sensible defaults if absent).
- `Attempt` is **internal** — listed in arch §Data model with the "Internal" tag. Export it from `contract.py` (the ledger reads/writes it) but do not document it on the public surface.
- Cover the 95/90 floor with parametrized tests on `state` literal (4 valid, 1 invalid) and on each frozen+extra-forbid model (one rejection test apiece).
- Watch the forward-ref to `RecipeApplication` in `ReplanHook`. Use `TYPE_CHECKING` import or a string annotation; do not introduce a runtime cycle to Phase 4.
