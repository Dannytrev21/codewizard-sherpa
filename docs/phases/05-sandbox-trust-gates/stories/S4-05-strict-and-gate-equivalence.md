# Story S4-05 — `StrictAndGate` adapter + Phase 3 equivalence property test

**Step:** Step 4 — Six signal collectors + StrictAndGate adapter
**Status:** Ready
**Effort:** M
**Depends on:** S4-01 (build + install collectors), S4-02 (test collector), S4-03 (trace + policy + cve_delta collectors), S4-04 (Phase 3 TrustScorer signal-kind widening)
**ADRs honored:** ADR-0003, ADR-0014

## Context

`StrictAndGate` is the thin adapter (~40 LOC) that translates a populated `ObjectiveSignals` to a `list[TrustSignal]` and delegates to Phase 3's `TrustScorer.score(...)`. Per ADR-0003, Phase 5 does not ship a second scorer — Phase 3's strict-AND is the canonical evaluator. The load-bearing test here is the **equivalence property**: for every populated combination of the six sub-models, `StrictAndGate.evaluate(os, ctx).passed` MUST equal `Phase3TrustScorer.score(materialized).passed`. If Phase 3's scoring semantics ever drift from strict-AND, this test breaks loudly and forces a contract conversation rather than silent divergence.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Component design — `Gate` (ABC) + `StrictAndGate`` — public interface, ~40 LOC budget, `GateMissingRequiredSignal` raise behavior.
- **Architecture:** `../phase-arch-design.md §Testing strategy — Strict-AND equivalence with Phase 3 scorer` — "For every combination of `{passed, failed} × 6 signals`, `StrictAndGate.evaluate(os, ctx)` returns a `GateOutcome` whose `passed` field equals `all(signal.passed for signal in populated_signals)` — **and** equals what Phase 3's `TrustScorer.score(...)` returns on the materialized `TrustSignal` list."
- **Phase ADRs:** `../ADRs/0003-trustscorer-extension-via-signal-kind-registry.md` — ADR-0003 — adapter is the only translation surface; property test enforces equivalence; "If Phase 3 ever drops strict-AND for weighted scoring, this adapter and its test loudly break".
- **Phase ADRs:** `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — ADR-0014 — `ObjectiveSignals` is `extra="forbid", frozen=True`; static introspection invariant remains in force.
- **High-level impl:** `../High-level-impl.md §Step 4` — done criterion: "For every combination of {passed, failed} × 6 signals" and "Hypothesis-driven test asserts `StrictAndGate.evaluate(os, ctx).passed == Phase3TrustScorer.score(materialized_signals).passed` for any populated combination".
- **Existing code:** `src/codegenie/gates/contract.py` (S1-04) — `Gate` ABC, `GateContext`, `GateOutcome`, `RetryPolicy`.
- **Existing code:** `src/codegenie/sandbox/signals/models.py` (S1-03) — `ObjectiveSignals`, six sub-models.
- **Existing code:** `src/codegenie/trust/scorer.py` (Phase 3 + S4-04) — `TrustScorer.score(signals)`.

## Goal

Ship `src/codegenie/gates/strict_and.py` — a ~40 LOC `StrictAndGate(Gate)` whose `evaluate(os, ctx)` materializes a `list[TrustSignal]` from populated `ObjectiveSignals` sub-models, delegates to `Phase3TrustScorer.score(...)`, and is proved equivalent to Phase 3 via a hypothesis property test over every populated combination.

## Acceptance criteria

- [ ] `src/codegenie/gates/strict_and.py` defines `class StrictAndGate(Gate)` with `evaluate(self, os: ObjectiveSignals, ctx: GateContext) -> GateOutcome`. **≤ 60 LOC including imports** (≤ 40 LOC for the body — architect's number).
- [ ] `StrictAndGate.evaluate` materializes a `list[TrustSignal]` ONLY from populated (non-`None`) sub-models on `os`. Empty `ObjectiveSignals` (all `None`) → `GateMissingRequiredSignal` raised (never silently passes).
- [ ] When any signal kind in `ctx.gate.required_signals` is `None` on `os`, `GateMissingRequiredSignal` is raised with the missing kind names in the message.
- [ ] `GateOutcome.passed == Phase3TrustScorer.score(materialized).passed` — for every populated combination. Asserted by hypothesis property test below.
- [ ] `GateOutcome.failing_signals` lists every kind whose sub-model has `passed=False` (sorted, deterministic).
- [ ] `GateOutcome.retryable` is `True` IFF all failing kinds are in `ctx.gate.retry_policy.retryable_failures` AND none are in `non_retryable_failures`.
- [ ] `GateOutcome.state` ∈ `{"passed", "failed_retryable", "escalate"}`. (`"failed_unrecoverable"` is set by `GateRunner` based on attempt history, not by the adapter — out of scope.)
- [ ] **Hypothesis property test:** for every subset `S ⊆ {build, install, tests, trace, policy, cve_delta}` and every passed/failed assignment over `S`, `StrictAndGate.evaluate(os, ctx).passed == Phase3TrustScorer.score(materialized).passed`. ≥ 200 examples.
- [ ] **Enumerative test:** every one of the `2^6 = 64` cartesian-product `{passed, failed}` combinations across all six populated kinds yields `StrictAndGate.evaluate(os, ctx).passed == all(s.passed for s in populated_signals)`.
- [ ] **Mutation check:** flipping `TrustSignal.passed=True` on a sub-model whose underlying `ObjectiveSignals` sub-model has `passed=False` (i.e., asserting the adapter doesn't lose `passed` in translation) makes the test fail — proves the adapter faithfully copies `passed`.
- [ ] No banned substring (`confidence`, `llm`, `self_reported`, `model_says`) anywhere in adapter code or test fixtures; `tests/schema/test_objective_signals_static.py` green.
- [ ] No `subprocess` import in `gates/strict_and.py`; no `anthropic` / LLM import in `gates/**` (fence CI green).
- [ ] TDD plan's red test exists, is committed, and is green.
- [ ] `ruff`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Adapter body shape:
   ```python
   class StrictAndGate(Gate):
       def __init__(self, gate_id: TransitionId, retry_policy: RetryPolicy, required_signals: list[str]) -> None: ...

       def evaluate(self, os: ObjectiveSignals, ctx: GateContext) -> GateOutcome:
           populated = self._populated(os)            # list[tuple[kind, _SignalBase]]
           missing = self._missing_required(populated)
           if missing:
               raise GateMissingRequiredSignal(missing)
           trust_signals = [TrustSignal(kind=k, passed=s.passed, details=s.details) for k, s in populated]
           score = Phase3TrustScorer().score(trust_signals)
           failing = sorted(k for k, s in populated if not s.passed)
           retryable = bool(failing) and all(k in self._retry_policy.retryable_failures for k in failing) \
                       and not any(k in self._retry_policy.non_retryable_failures for k in failing)
           state = "passed" if score.passed else ("failed_retryable" if retryable else "escalate")
           return GateOutcome(passed=score.passed, attempt=ctx.attempt, failing_signals=failing,
                              retryable=retryable, state=state, summary=..., signals=os)
   ```
2. Add `GateMissingRequiredSignal` to `gates/errors.py` if S1-04 hasn't already.
3. Construct a hypothesis strategy `signals_strategy()` that yields a populated `ObjectiveSignals` with each kind independently present-or-`None`, and for each present kind a synthetic sub-model with random `passed: bool`. Skip the all-`None` case (raises by contract).
4. Write the enumerative `64-case` parametrized test and the hypothesis property test side by side.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/gates/test_strict_and.py`

```python
# tests/gates/test_strict_and.py
import itertools
from datetime import UTC, datetime

import pytest
from hypothesis import given, settings, strategies as st

import codegenie.sandbox.signals.trust_registration  # noqa: F401  (fires kind registration)
from codegenie.gates.contract import GateContext, RetryPolicy, TransitionId
from codegenie.gates.errors import GateMissingRequiredSignal
from codegenie.gates.strict_and import StrictAndGate
from codegenie.sandbox.signals.models import (
    BuildSignal, CveDeltaSignal, InstallSignal, ObjectiveSignals,
    PolicySignal, SignalProvenance, TestSignal, TraceSignal,
)
from codegenie.trust.scorer import TrustScorer, TrustSignal


KINDS = ("build", "install", "tests", "trace", "policy", "cve_delta")
_SUB = {
    "build": BuildSignal, "install": InstallSignal, "tests": TestSignal,
    "trace": TraceSignal, "policy": PolicySignal, "cve_delta": CveDeltaSignal,
}


def _prov(kind: str) -> SignalProvenance:
    return SignalProvenance(signal_kind=kind, collector_module=f"x.{kind}",
                            collector_version="1", inputs_blake3="00" * 16)


def _sub(kind: str, passed: bool):
    return _SUB[kind](passed=passed, details={}, provenance=_prov(kind), at=datetime.now(UTC))


def _os(populated: dict[str, bool]) -> ObjectiveSignals:
    kw = {k: _sub(k, p) for k, p in populated.items()}
    return ObjectiveSignals(**kw)


def _gate(required: list[str], non_retryable: list[str] | None = None) -> StrictAndGate:
    rp = RetryPolicy(
        max_attempts=3,
        retryable_failures=[k for k in KINDS if k not in (non_retryable or [])],
        non_retryable_failures=non_retryable or [],
        timeout_retryable=False,
    )
    return StrictAndGate(gate_id=TransitionId.STAGE6_VALIDATE, retry_policy=rp, required_signals=required)


def _ctx(attempt: int = 1) -> GateContext:
    return GateContext.model_construct(attempt=attempt, prior_attempts=[],
                                       workflow_id="wf", run_id="r")


@pytest.mark.parametrize("combo", list(itertools.product([True, False], repeat=6)))
def test_enumerative_64_cases_all_six_populated(combo):
    # WHY: brute-force coverage — for every passed/failed combination across
    #      all six sub-models, adapter agrees with naive all().
    populated = dict(zip(KINDS, combo))
    os_ = _os(populated)
    gate = _gate(required=list(KINDS))
    outcome = gate.evaluate(os_, _ctx())
    assert outcome.passed == all(populated.values())


@pytest.mark.parametrize("combo", list(itertools.product([True, False], repeat=6)))
def test_equivalence_with_phase3_trustscorer(combo):
    # WHY: ADR-0003 load-bearing — StrictAndGate is a thin adapter; if Phase 3
    #      ever drifts from strict-AND, this test fails LOUDLY rather than letting
    #      Phase 5 and Phase 3 silently disagree.
    populated = dict(zip(KINDS, combo))
    os_ = _os(populated)
    gate = _gate(required=list(KINDS))
    outcome = gate.evaluate(os_, _ctx())
    materialized = [TrustSignal(kind=k, passed=p, details={}) for k, p in populated.items()]
    phase3 = TrustScorer().score(materialized)
    assert outcome.passed == phase3.passed


@given(st.lists(st.sampled_from(KINDS), min_size=1, max_size=6, unique=True),
       st.lists(st.booleans(), min_size=1, max_size=6))
@settings(max_examples=200)
def test_equivalence_property_over_arbitrary_populated_subsets(present, passes):
    # WHY: extension-by-addition — adapter must remain equivalent to Phase 3
    #      across every populated combination, including partial population
    #      (e.g., only build + tests).
    n = min(len(present), len(passes))
    populated = {k: passes[i] for i, k in enumerate(present[:n])}
    os_ = _os(populated)
    gate = _gate(required=present[:n])
    outcome = gate.evaluate(os_, _ctx())
    materialized = [TrustSignal(kind=k, passed=p, details={}) for k, p in populated.items()]
    phase3 = TrustScorer().score(materialized)
    assert outcome.passed == phase3.passed


def test_missing_required_signal_raises():
    # WHY: arch §Failure behavior — adapter never silently passes; required-but-None raises.
    os_ = _os({"build": True, "install": True})  # missing tests, trace, policy, cve_delta
    gate = _gate(required=list(KINDS))
    with pytest.raises(GateMissingRequiredSignal) as exc:
        gate.evaluate(os_, _ctx())
    assert "tests" in str(exc.value)


def test_failing_signals_sorted_and_deterministic():
    populated = {"build": True, "install": False, "tests": False, "trace": True,
                 "policy": False, "cve_delta": True}
    os_ = _os(populated)
    gate = _gate(required=list(KINDS))
    outcome = gate.evaluate(os_, _ctx())
    assert outcome.failing_signals == sorted(["install", "tests", "policy"])


def test_non_retryable_failure_state_is_escalate():
    # WHY: trace failures are non-retryable per YAML; outcome.state must be "escalate".
    populated = {"build": True, "install": True, "tests": True, "trace": False,
                 "policy": True, "cve_delta": True}
    os_ = _os(populated)
    gate = _gate(required=list(KINDS), non_retryable=["trace"])
    outcome = gate.evaluate(os_, _ctx())
    assert outcome.passed is False
    assert outcome.state == "escalate"
    assert outcome.retryable is False


def test_retryable_failure_state_is_failed_retryable():
    populated = {"build": True, "install": True, "tests": False, "trace": True,
                 "policy": True, "cve_delta": True}
    os_ = _os(populated)
    gate = _gate(required=list(KINDS), non_retryable=["trace"])
    outcome = gate.evaluate(os_, _ctx())
    assert outcome.passed is False
    assert outcome.state == "failed_retryable"
    assert outcome.retryable is True


def test_adapter_faithfully_copies_passed_mutation_check():
    # WHY: mutation defense — if the adapter ever drops/inverts `passed` during
    #      translation, the equivalence test still passes by coincidence on
    #      all-True / all-False cases. This test pins one-off mismatch.
    populated = {"build": True, "install": False, "tests": True, "trace": True,
                 "policy": True, "cve_delta": True}
    os_ = _os(populated)
    gate = _gate(required=list(KINDS))
    outcome = gate.evaluate(os_, _ctx())
    assert outcome.passed is False
    assert "install" in outcome.failing_signals
```

### Green — make it pass

- Write `gates/strict_and.py` per the outline; keep the body ≤ 40 LOC.
- Wire `GateMissingRequiredSignal` if absent.

### Refactor — clean up

- Inline anything that's used once. The adapter's whole virtue is being a translation surface — extra helpers blur ADR-0003's "thin adapter" stance.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/gates/strict_and.py` | The ~40 LOC adapter. |
| `src/codegenie/gates/errors.py` | Add `GateMissingRequiredSignal` if not present. |
| `src/codegenie/gates/__init__.py` | Re-export `StrictAndGate`. |
| `tests/gates/test_strict_and.py` | 64-case enumerative + hypothesis property + mutation check. |

## Out of scope

- The three-retry loop, retry-1/retry-2 timing — `GateRunner` (S5-02).
- `failed_unrecoverable` 3× detection — `GateRunner`.
- `ReplanHook` invocation — `GateRunner` + S5-01.
- YAML catalog loading into `StrictAndGate.from_yaml(...)` — that's S5-02's `from_yaml` factory.

## Notes for the implementer

1. The adapter is intentionally boring. If you find yourself adding logic beyond "translate, delegate, build outcome", you're in the wrong place. ADR-0003 §Tradeoffs row 1: "Single source of truth for strict-AND scoring — Phase 3's logic is reused untouched."
2. The equivalence test is the load-bearing artifact, not the adapter LOC count. If Phase 3's `TrustScorer.score(...)` changes to weighted scoring, this test fails loudly. That's the design.
3. `failing_signals` is sorted alphabetically — determinism matters for ledger replay (`attempts.jsonl` chain).
4. The mutation check (`test_adapter_faithfully_copies_passed_mutation_check`) defends against the adapter losing `passed` in translation; without it, equivalence-on-all-true and equivalence-on-all-false hide a one-off bug.
5. Don't compute `state="failed_unrecoverable"` here — that's `GateRunner`'s job (depends on history across attempts). The adapter only knows about one evaluation.
6. The `64-case` enumeration uses `itertools.product([True, False], repeat=6)` — exhaustive. Don't replace it with hypothesis "for speed"; the brute-force list is the spec.
