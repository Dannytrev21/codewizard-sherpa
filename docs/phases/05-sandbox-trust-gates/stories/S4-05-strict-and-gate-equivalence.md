# Story S4-05 — `StrictAndGate` adapter + Phase 3 equivalence property test

**Step:** Step 4 — Six signal collectors + StrictAndGate adapter
**Status:** Ready (HARDENED 2026-05-25)
**Effort:** M
**Depends on:** S1-03 (`ObjectiveSignals` + six sub-models + `SignalKind` newtype + `iter_nested_field_names`), S1-04 (`Gate` ABC + `GateContext` + `GateOutcome` + `RetryPolicy` + `AttemptNumber` + `TransitionId`), S1-05 (`@register_signal_kind` delegation chain), S4-01 (`collect_build_signal` / `collect_install_signal`), S4-02 (`collect_test_signal`), S4-03 (`collect_trace_signal` / `collect_policy_signal` / `collect_cve_delta_signal`), S4-04 (`trace` + `policy` net-new kind registrations + 7-kind registry membership)
**ADRs honored:** ADR-0003, ADR-0014

## Validation notes (2026-05-25 — phase-story-validator)

Four-critic pass. Verdict: **HARDENED**. The draft was structurally sound on goal + scope, but every block-tier finding traced back to one root cause: the draft was written **before** S4-04's HARDENED report locked in the actual Phase-3 surfaces (`TrustScorer(event_log=...)` constructor injection, `transforms/trust_scorer` import path, `TrustOutcome.failing` caller-order, no `trust_registration.py` sidecar). Headline edits, with severity tags — every one would have caught a structurally-wrong implementation that the executor's validator would have missed:

1. **(coverage / consistency — block) `TrustScorer` constructor takes `event_log: EventLog`.** Draft's `Phase3TrustScorer()` no-arg pseudocode would `TypeError` at first call. **Fix:** AC-CTOR-1 / -2 / -3 pin the keyword-injected `event_log: EventLog`; the TDD plan threads a per-test `_log(tmp_path)` fixture; the class is `TrustScorer` (no `Phase3` prefix in production code).
2. **(consistency — block) Import paths rewritten end-to-end.** Draft's `from codegenie.trust.scorer import TrustScorer, TrustSignal` resolves to neither module nor symbol. **Fix:** `from codegenie.transforms.trust_scorer import TrustScorer`, `from codegenie.transforms.outcomes import TrustSignal, TrustOutcome`, `from codegenie.transforms.signal_kinds import signal_kind_registry`, `from codegenie.plugins.events import EventLog`. AC-IMPORT-1..-3 pin every adapter + test import.
3. **(coverage — block) `failing_signals` ordering is gate-side, NOT a passthrough of `TrustOutcome.failing`.** Phase-3 `TrustOutcome.failing` is deliberately *caller-order* (`trust_scorer.py:99-104` — "never sorted or deduplicated"). A passthrough would contradict the draft AC's "sorted, deterministic". **Fix:** AC-FS-1 derives `failing_signals` from the populated `ObjectiveSignals` (intersected with `required_signals`), sorted; AC-FS-2 mutation-defends with a 3-permutation shuffle of the same populated dict; AC-FS-3 AST scan forbids any `score.failing` reference in `strict_and.py`; AC-FS-4 adversarial — a populated non-required failing kind is *excluded* from `failing_signals`.
4. **(coverage — block) Sidecar `trust_registration.py` import is forbidden.** Draft's `import codegenie.sandbox.signals.trust_registration` contradicts S4-04 AC-ANTIPATTERN-1 (file-existence test forbids the path). **Fix:** all test fixtures use `import codegenie.sandbox.signals  # noqa: F401  (fires kind registration)`; AC-REG-1 forbids any `trust_registration` reference in `gates/**` or the test; AC-REG-2 mirrors S4-04's file-existence forbid.
5. **(coverage — block) `ctx.attempt` does not exist on `GateContext`.** S1-04 `GateContext` has no `attempt` field — the adapter must derive `attempt = AttemptNumber(len(ctx.prior_attempts) + 1)`. **Fix:** AC-ATTEMPT-1..-3, including a 3-call accumulation test and the inherited 1..1024 bound from `AttemptNumber`.
6. **(coverage — block) `ctx.gate.required_signals` is a phantom lookup.** Gate is the instance itself; `GateContext` has no `gate` field. **Fix:** AC-REQ-1 pins `self.required_signals` (the gate's own attribute per S1-04); AC-REQ-2 pins `GateMissingRequiredSignal` raised when a required kind is `None` on `os`.
7. **(coverage — block) Registry pre-population mismatch.** Phase-3 pre-registers `{build, install, tests, lockfile_policy, cve_delta}` — NOT `{build, install, tests, policy, cve_delta}`. `trace` + `policy` are net-new Phase-5 kinds fired by `import codegenie.sandbox.signals` (S4-04 ACs). **Fix:** AC-REG-3 (7-element membership), AC-REG-4 (exact set), AC-REG-5 (`lockfile_policy` is NOT a Phase-5 sub-model).
8. **(coverage — block) `EmptySignals` corner-case uncovered.** `TrustScorer.score([])` raises `EmptySignals` — distinct from `GateMissingRequiredSignal`. **Fix:** AC-EMPTY-1 pins the discipline (gate raises `GateMissingRequiredSignal` BEFORE calling `score()`); AC-EMPTY-2 the `required_signals=()` AND all-`None` corner with a distinct message.
9. **(consistency — block) `GateOutcome.state` set is THREE members for the adapter** (`{passed, failed_retryable, escalate}`), NOT four — `failed_unrecoverable` is set by `GateRunner` based on attempt history (story's prose says it, but no AC pinned it). **Fix:** AC-STATE-1..-3, including AC-STATE-3 explicit `assert outcome.state != "failed_unrecoverable"` in every parametrized row.
10. **(coverage — harden) `TrustOutcome.confidence` propagated to `summary`, NOT dropped.** Phase-3 returns `confidence: Literal["high", "degraded"]`. The adapter must do *something* with it. Per arch §Integration with Phase 6, `state` is the runner-decision input; `confidence` is audit-only. **Fix:** AC-CONF-1 pins `summary` tail substring carries the confidence; AC-CONF-2 mutation-defends — flipping `event_log` from clean to one carrying `AdapterDegraded(workflow_id=...)` flips the substring.
11. **(coverage — harden) `details` round-trip + `TrustSignal` 3-field shape.** `TrustSignal` has exactly `(kind, passed, details)` — no `provenance`, no `at`. **Fix:** AC-DETAILS-1 byte-stable `details` round-trip on a 3-key dict; AC-DETAILS-2 pins that the materialized `TrustSignal` set has exactly the three fields.
12. **(coverage — harden) Property-test strategy bug.** Draft's two paired lists (`present, passes`) truncate via `min(len(...), len(...))` — silently deletes coverage. **Fix:** AC-PROP-1 rewrites to `st.dictionaries(keys=st.sampled_from(KINDS), values=st.booleans(), min_size=1, max_size=6)`; AC-PROP-2 bumps to `max_examples=500`.
13. **(consistency — harden) `gate_id` vs `TransitionId` conflation.** `TransitionId` is a closed Literal of stage transitions, NOT the gate identifier — but the str-mixin enum yields the value so `gate_id = TransitionId.STAGE6_VALIDATE.value` is the convention until S1-06's catalog loader supplies a distinct typed identifier. Documented as Open ambiguity (resolved). Outline + tests rewritten.
14. **(patterns — harden) Functional core / imperative shell split.** Mirrors `trust_scorer.py:96-123`'s two-pure-helper discipline. **Fix:** Implementation outline now names `_materialize(os, required) -> list[TrustSignal]` and `_classify_retry(failing, retry_policy) -> tuple[bool, str]` as module-private pure helpers; `evaluate` is the only impure surface.
15. **(patterns — harden) `AttemptNumber` newtype adopted.** S1-04 minted it explicitly for this consumer. **Fix:** AC-ATTEMPT-1 mints `AttemptNumber(len(ctx.prior_attempts) + 1)`.
16. **(patterns — harden) `SignalKind` newtype at every kind call site.** Pydantic coerces raw `str` but the static surface loses NewType discipline. **Fix:** AC-NEWTYPE-1 every `TrustSignal(kind=...)` and registry-lookup call site uses `SignalKind(name)`; AC-NEWTYPE-2 source-of-truth pin mirrors S1-03 AC-4c chokepoint (no `NewType("SignalKind", ...)` under `src/codegenie/gates/`).
17. **(patterns — harden) Typed `.missing: tuple[SignalKind, ...]` on `GateMissingRequiredSignal`.** Mirrors the `SignalKindAlreadyRegistered.{name, existing, duplicate}` typed-attribute pattern from `transforms/signal_kinds.py:69-75`. **Fix:** AC-EXC-1 / -2.
18. **(patterns — harden) Module purity + import allow-list.** Mirrors S1-04 AC-9a precedent. **Fix:** AC-PURITY-1.
19. **(coverage — harden) LOC budget enforced by test, not prose.** **Fix:** AC-LOC-1 (≤ 60 lines total), AC-LOC-2 (≤ 40 executable lines via AST walk).
20. **(consistency — harden) Coverage floor wording (line ≥ 95% AND branch ≥ 90%).** Mirrors S1-02/S1-03/S1-04 fix. **Fix:** AC-COV-1.
21. **(patterns — note-only forward seam) `@register_gate` registry deferred.** StrictAndGate is N=1 concrete `Gate`. The kernel-extract precedent from `signal_kinds.py` (Final-singleton + per-instance `.fresh()`) is documented in Notes as the path forward for `WeightedScoreGate` / `LooseGate`. Per Rule 2, no abstraction extracted today.
22. **(patterns — note-only forward seam) `from_yaml` factory deferred.** Out-of-scope cleared between S1-06 (catalog schema owner) and S5-02 (runner) — S4-05 ships only the constructor-injected adapter.

No `RESCUE`-tier findings — every gap was patchable by rewriting against the actual upstream surfaces (S1-04 / S4-04 HARDENED) and tightening ACs. No Stage-3 research needed: every gap was answerable from Phase 5 arch + ADRs + the seven prior HARDENED reports (S1-02, S1-03, S1-04, S1-05, S4-01..S4-04) + the existing kernels (`transforms/trust_scorer.py`, `transforms/signal_kinds.py`, `transforms/outcomes.py`, `types/identifiers.py`). Full audit log: [`_validation/S4-05-strict-and-gate-equivalence.md`](_validation/S4-05-strict-and-gate-equivalence.md).

## Context

`StrictAndGate` is the thin adapter (~40 LOC) that translates a populated `ObjectiveSignals` to a `list[TrustSignal]` and delegates to Phase 3's `TrustScorer.score(...)`. Per ADR-0003, Phase 5 does not ship a second scorer — Phase 3's strict-AND is the canonical evaluator; `StrictAndGate` is a textbook adapter / anti-corruption-layer between the Phase-5 sandbox-domain Pydantic and the Phase-3 trust-domain Pydantic. The load-bearing test is the **equivalence property**: for every populated combination of the six Phase-5 sub-models, `StrictAndGate.evaluate(os, ctx).passed` MUST equal `TrustScorer(event_log).score(materialized).passed`. If Phase 3's scoring semantics ever drift from strict-AND, this test breaks loudly and forces a contract conversation rather than silent divergence.

## References — where to look

- **Architecture:** [`../phase-arch-design.md §Component design — Gate (ABC) + StrictAndGate`](../phase-arch-design.md) — public interface, ~40 LOC budget, `GateMissingRequiredSignal` raise behavior.
- **Architecture:** [`../phase-arch-design.md §Testing strategy — Strict-AND equivalence with Phase 3 scorer`](../phase-arch-design.md#strict-and-equivalence-with-phase-3-scorer) — "For every combination of `{passed, failed} × 6 signals`, `StrictAndGate.evaluate(os, ctx)` returns a `GateOutcome` whose `passed` field equals `all(signal.passed for signal in populated_signals)` — **and** equals what Phase 3's `TrustScorer.score(...)` returns on the materialized `TrustSignal` list."
- **Phase ADRs:** [`../ADRs/0003-trustscorer-extension-via-signal-kind-registry.md`](../ADRs/0003-trustscorer-extension-via-signal-kind-registry.md) — adapter is the only translation surface; property test enforces equivalence; "If Phase 3 ever drops strict-AND for weighted scoring, this adapter and its test loudly break".
- **Phase ADRs:** [`../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md`](../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md) — `ObjectiveSignals` is `extra="forbid", frozen=True`; banned-substring scan transitively inherited via S1-03 walker (S1-04 AC-INH covers `GateOutcome.signals`).
- **High-level impl:** [`../High-level-impl.md §Step 4`](../High-level-impl.md) — done criterion: "For every combination of {passed, failed} × 6 signals" and "Hypothesis-driven test asserts `StrictAndGate.evaluate(os, ctx).passed == TrustScorer.score(materialized_signals).passed` for any populated combination".
- **Existing code (kernels this story consumes):**
  - [`src/codegenie/gates/contract.py`](../../../../src/codegenie/gates/contract.py) (S1-04) — `Gate` ABC, `GateContext`, `GateOutcome`, `RetryPolicy`, `AttemptNumber`-derived `attempt`, `TransitionId`.
  - [`src/codegenie/sandbox/signals/models.py`](../../../../src/codegenie/sandbox/signals/models.py) (S1-03) — `ObjectiveSignals`, six sub-models, `SignalProvenance`, `AwareDatetime` enforcement.
  - [`src/codegenie/transforms/trust_scorer.py`](../../../../src/codegenie/transforms/trust_scorer.py) — `TrustScorer(event_log: EventLog)`, `EmptySignals`, `UnregisteredSignalKind`. **`TrustOutcome.failing` is caller-order — never sort-passthrough.**
  - [`src/codegenie/transforms/outcomes.py`](../../../../src/codegenie/transforms/outcomes.py) — `TrustSignal(kind, passed, details)` — no `provenance`, no `at`; `TrustOutcome(passed, failing, signals, confidence)`.
  - [`src/codegenie/transforms/signal_kinds.py`](../../../../src/codegenie/transforms/signal_kinds.py) — `signal_kind_registry` singleton; pre-registers `{build, install, tests, lockfile_policy, cve_delta}`; `trace` + `policy` registered by Phase-5 via `import codegenie.sandbox.signals`.
  - [`src/codegenie/plugins/events.py`](../../../../src/codegenie/plugins/events.py) — `EventLog`, `AdapterDegraded` (for the `confidence` propagation test).
  - [`src/codegenie/types/identifiers.py`](../../../../src/codegenie/types/identifiers.py) — `SignalKind`, `AttemptNumber` NewTypes (single declaration site).
- **Sibling validation reports (pattern lineage):**
  - [`_validation/S1-04-gates-contract-abc-models.md`](_validation/S1-04-gates-contract-abc-models.md) — `AttemptNumber` derivation, cross-field invariants, purity discipline.
  - [`_validation/S4-04-trustscorer-signal-kind-registry.md`](_validation/S4-04-trustscorer-signal-kind-registry.md) — registry layout, no-sidecar discipline, `_log(tmp_path)` fixture, byte-stable kind set.
  - [`_validation/S1-03-objective-signals-models.md`](_validation/S1-03-objective-signals-models.md) — `iter_nested_field_names` walker (ADR-0014 inheritance), `at: AwareDatetime`, NewType chokepoint pattern.

## Goal

Ship `src/codegenie/gates/strict_and.py` — a ~40 LOC `StrictAndGate(Gate)` whose `evaluate(os, ctx)` materializes a `list[TrustSignal]` from populated `ObjectiveSignals` sub-models (using the canonical kind names from `signal_kind_registry`), delegates strict-AND scoring to the canonical `TrustScorer(event_log).score(...)` (NOT a Phase-5 reimplementation), and is proved equivalent to Phase 3 via a hypothesis property test over every populated combination. Two module-private pure helpers (`_materialize`, `_classify_retry`) carry the logic; `evaluate` is the only impure surface (constructs `TrustScorer`, calls `score()`).

## Acceptance criteria

### A. Constructor + import surface

- [ ] **AC-CTOR-1** — `StrictAndGate.__init__(self, *, gate_id: str, required_signals: tuple[SignalKind, ...], retry_policy: RetryPolicy, event_log: EventLog) -> None`. All four kwargs are required keyword-only; `inspect.signature(StrictAndGate.__init__)` asserts the exact parameter names + ordering + `kind=KEYWORD_ONLY`.
- [ ] **AC-CTOR-2** — The `event_log` argument is stored on `self._event_log` and used to construct (or be passed to) a `TrustScorer` at `evaluate` time. The scorer construction is per-call (cheap; the scorer is stateless across `score()` per `trust_scorer.py:135-137`); a stored-scorer alternative is also acceptable iff the same `EventLog` instance is reused.
- [ ] **AC-CTOR-3** — `StrictAndGate.__init__` accepts and stores the four kwargs without side effects: no filesystem writes, no logger emissions, no module-level state mutation.
- [ ] **AC-IMPORT-1** — The adapter module's imports are exactly:
  ```python
  from __future__ import annotations
  from typing import TYPE_CHECKING
  from codegenie.errors import CodegenieError
  from codegenie.gates.contract import Gate, GateContext, GateOutcome, RetryPolicy
  from codegenie.sandbox.signals.models import ObjectiveSignals
  from codegenie.transforms.outcomes import TrustSignal
  from codegenie.transforms.trust_scorer import TrustScorer
  from codegenie.transforms.signal_kinds import signal_kind_registry
  from codegenie.types.identifiers import AttemptNumber, SignalKind
  if TYPE_CHECKING:
      from codegenie.plugins.events import EventLog
  ```
  Asserted via AST walk over `gates/strict_and.py` source. `subprocess`, `os.system`, `pathlib.Path.write_*`, `logging`, `structlog`, `anthropic`, `langgraph` are explicitly forbidden.
- [ ] **AC-IMPORT-2** — `from codegenie.gates.strict_and import StrictAndGate, GateMissingRequiredSignal` succeeds idempotently (second import returns the same module object).
- [ ] **AC-IMPORT-3** — `set(codegenie.gates.strict_and.__all__) == {"GateMissingRequiredSignal", "StrictAndGate"}`. `TrustScorer`, `TrustSignal`, `signal_kind_registry`, `SignalKind`, `AttemptNumber` are NOT re-exported — single-declaration-site discipline (mirrors S1-04 AC-1a).

### B. Gate ABC conformance

- [ ] **AC-ABC-1** — `issubclass(StrictAndGate, Gate) is True`; `inspect.isabstract(StrictAndGate) is False`; `StrictAndGate(...)` constructs without `TypeError`.
- [ ] **AC-ABC-2** — `StrictAndGate.evaluate.__isabstractmethod__` is falsy (concrete override).
- [ ] **AC-ABC-3** — `StrictAndGate.gate_id`, `.required_signals`, `.retry_policy` are accessible as instance attributes after construction, matching the kwargs passed in.

### C. `evaluate` signature + pure-helper split (functional core / imperative shell)

- [ ] **AC-EVAL-1** — `inspect.signature(StrictAndGate.evaluate)` is exactly `(self, os: ObjectiveSignals, ctx: GateContext) -> GateOutcome` (mirrors S1-04 AC-2). No `attempt` kwarg, no `event_log` kwarg.
- [ ] **AC-PURE-1** — Module declares two pure helpers `_materialize(os: ObjectiveSignals, required: tuple[SignalKind, ...]) -> list[TrustSignal]` and `_classify_retry(failing: list[SignalKind], retry_policy: RetryPolicy) -> tuple[bool, str]`. Both are module-private (leading underscore); both are referenced exactly once in `evaluate`; both can be called from tests directly.
- [ ] **AC-PURE-2** — `_materialize` does no I/O (no `TrustScorer` construction inside it); `_classify_retry` does no I/O. Asserted by AST walk over both helper bodies: no `Call(Name="TrustScorer")`, no `Call(Attr(Name=_, attr="open"))`, no `Call(Attr(Name="datetime", attr="now"))`, no `Call(Attr(Name="time", attr=_))`.
- [ ] **AC-PURE-3** — `_materialize` is deterministic: called twice with the same `(os, required)` returns lists whose elements compare equal (`TrustSignal` is frozen Pydantic — `==` is field-wise) AND whose order is byte-identical (sorted by the canonical kind ordering of `required`).

### D. Signal materialization (`_materialize`)

- [ ] **AC-MAT-1** — `_materialize(os=ObjectiveSignals(build=_build(passed=True)), required=(SignalKind("build"),))` returns `[TrustSignal(kind=SignalKind("build"), passed=True, details={})]`. The exact 3-field shape is asserted (`set(ts.model_fields) == {"kind", "passed", "details"}` — mirrors S1-04 / `outcomes.py:377-388`).
- [ ] **AC-MAT-2** — `_materialize` produces only the *populated* sub-models — a `None` sub-model contributes no `TrustSignal`. For a 3-of-6 population, the output list has length 3.
- [ ] **AC-MAT-3** — `_materialize` does NOT include the `provenance` or `at` fields in the materialized `TrustSignal` (TrustSignal has neither). AST walk on `_materialize` asserts the constructor call sites name only `kind`, `passed`, `details`.
- [ ] **AC-MAT-4** — Mutation defense (M-9 — `details` round-trip): for `BuildSignal(passed=False, details={"k": "v", "i": 7, "b": True}, provenance=_prov("build"), at=_now())`, the materialized `TrustSignal.details == {"k": "v", "i": 7, "b": True}` byte-equal AND `type(ts.details["b"]) is bool` AND `type(ts.details["i"]) is int` (no `bool↔int` coercion drift).
- [ ] **AC-MAT-5** — Mutation defense (M-1 — `passed` faithfulness): for every of the 64 cartesian-product `{passed, failed}` combinations across the six sub-models, each materialized `TrustSignal.passed` equals the source sub-model's `passed`.
- [ ] **AC-NEWTYPE-1** — Every `TrustSignal(kind=...)` and `signal_kind_registry.__contains__` call site in `strict_and.py` passes a `SignalKind(...)` instance (NewType-wrapped), not a bare `str`. AST scan over `_materialize` body asserts `Call(Name="SignalKind")` wraps the raw string in every kind-passing position.
- [ ] **AC-NEWTYPE-2** — Source-of-truth pin (mirrors S1-03 AC-4c chokepoint): AST source-scan on `src/codegenie/gates/strict_and.py` forbids `NewType("SignalKind", …)` and `NewType("AttemptNumber", …)` redefinitions; both are imported from `codegenie.types.identifiers`.

### E. `failing_signals` deterministic sort + intersect with `required_signals`

- [ ] **AC-FS-1** — `failing_signals` is derived by `_classify_retry` from the *populated* sub-models on `os` (intersected with `self.required_signals` AND sorted alphabetically by the `SignalKind` string value). It is NOT a passthrough of `TrustOutcome.failing` (Phase-3 caller-order would violate the determinism guarantee).
- [ ] **AC-FS-2** — Mutation defense (M-3 — accidental passthrough): for a populated dict `{trace: False, build: False, tests: True}` with `required=(SignalKind("build"), SignalKind("tests"), SignalKind("trace"))`, three permutations of the source `ObjectiveSignals` field-construction order (Pydantic preserves declaration order) yield the SAME `outcome.failing_signals == sorted([SignalKind("build"), SignalKind("trace")])`. Parametrized over three permutations.
- [ ] **AC-FS-3** — AST chokepoint: source-scan over `src/codegenie/gates/strict_and.py` asserts NO `Attribute(attr="failing")` access on any `TrustOutcome` value (forbids the `score.failing` passthrough mutation entirely).
- [ ] **AC-FS-4** — Adversarial — non-required populated kind: for `required=(SignalKind("build"),)` and `os=ObjectiveSignals(build=_build(passed=True), tests=_tests(passed=False))`, `outcome.failing_signals == []` (the failing `tests` kind is NOT required, so it is excluded). `outcome.passed is True`.

### F. State / retryable cross-field (mirrors S1-04 AC-CF discipline)

- [ ] **AC-STATE-1** — `outcome.state ∈ {"passed", "failed_retryable", "escalate"}` across every test case the adapter produces. `"failed_unrecoverable"` is RUNNER-only (S5-02) — adapter never returns it.
- [ ] **AC-STATE-2** — Parametrized over the 64 cartesian-product + 1 non-retryable-failure + 1 all-pass row: `outcome.state == "passed"` iff `outcome.passed is True`; `outcome.state == "failed_retryable"` iff (`outcome.passed is False` AND `outcome.retryable is True`); `outcome.state == "escalate"` iff (`outcome.passed is False` AND `outcome.retryable is False`).
- [ ] **AC-STATE-3** — Every test row asserts `outcome.state != "failed_unrecoverable"` (positive forbid — defends M-7).
- [ ] **AC-RETRY-1** — Parametrized over retry-policy shapes (all-retryable, some-non-retryable, all-non-retryable): `_classify_retry(failing, retry_policy)` returns `(retryable, state)` where `retryable` is `True` IFF `failing` is non-empty AND every kind in `failing` is in `retry_policy.retryable_failures` AND no kind in `failing` is in `retry_policy.non_retryable_failures`.
- [ ] **AC-RETRY-2** — Empty `failing` (`os` all-passed, populated) yields `(retryable=False, state="passed")`. Non-empty `failing` with all kinds in `retryable_failures` yields `(retryable=True, state="failed_retryable")`. Any kind in `non_retryable_failures` yields `(retryable=False, state="escalate")`.

### G. Phase-3 strict-AND equivalence (load-bearing property)

- [ ] **AC-EQUIV-1** — 64-case enumerative parametrize over `itertools.product([True, False], repeat=6)` for the six populated kinds (`build, install, tests, trace, policy, cve_delta`): `StrictAndGate.evaluate(os, ctx).passed == TrustScorer(event_log=_log(tmp_path)).score(materialized).passed`. The materialized list uses `SignalKind(name)` wrapping at every kind.
- [ ] **AC-EQUIV-2** — Same 64 cases: `outcome.passed == all(populated.values())` (naive `all()` parity — the strict-AND semantics).
- [ ] **AC-PROP-1** — Hypothesis property test: `@given(st.dictionaries(keys=st.sampled_from(KINDS_5_PHASE_5), values=st.booleans(), min_size=1, max_size=6))` — for every dict `d`, `StrictAndGate.evaluate(os, ctx).passed == TrustScorer(event_log=_log(tmp_path)).score(materialized).passed` AND `outcome.passed == all(d.values())`. `KINDS_5_PHASE_5` is the 6-element tuple of Phase-5 sub-model kinds (NOT the 7-element registry, which includes Phase-3-only `lockfile_policy`).
- [ ] **AC-PROP-2** — `@settings(deadline=None, max_examples=500, suppress_health_check=[HealthCheck.too_slow])` — explicit derandomisation + 500-example floor.
- [ ] **AC-PROP-3** — A *second* property test parametrizes from the *live registry* (mirrors S4-04 pattern): `kinds = tuple(KINDS_5_PHASE_5)` is computed once at module-import (after `import codegenie.sandbox.signals`); the hypothesis strategy samples from this live set. If a future Phase-7 widens `ObjectiveSignals` with `baseimage`/`shell_presence`, the test surface auto-extends.

### H. Attempt derivation from `prior_attempts`

- [ ] **AC-ATTEMPT-1** — `outcome.attempt == AttemptNumber(len(ctx.prior_attempts) + 1)`. The result is typed via `AttemptNumber(...)` (NewType-wrapped, NOT bare `int`). `outcome.attempt` field accepts the value via S1-04's `Annotated[int, Field(ge=1, le=1024)]` + `AttemptNumber` annotation.
- [ ] **AC-ATTEMPT-2** — Three-call accumulation (mirrors S1-04 AC-G-6): with `ctx.prior_attempts=[]` → `outcome.attempt == 1`; with one `prior_attempts` element → `outcome.attempt == 2`; with two → `outcome.attempt == 3`. Parametrized.
- [ ] **AC-ATTEMPT-3** — Negative path: `ctx.prior_attempts` constructed with 1024 elements → `outcome.attempt == 1025` triggers the `AttemptNumber` 1..1024 bound rejection at construction (`ValidationError`). The adapter does NOT silently clamp.

### I. Exception shape — `GateMissingRequiredSignal`

- [ ] **AC-EXC-1** — `GateMissingRequiredSignal(CodegenieError)` is declared in `src/codegenie/gates/strict_and.py` (or `src/codegenie/gates/errors.py` if S1-04 has already provisioned it — check before duplicating). Constructor signature: `__init__(self, missing: tuple[SignalKind, ...]) -> None`; the message format is `f"required signals missing on ObjectiveSignals: {sorted(missing)}"`.
- [ ] **AC-EXC-2** — Typed attribute `.missing: tuple[SignalKind, ...]` on the exception instance (mirrors `SignalKindAlreadyRegistered.{name, existing, duplicate}` in `transforms/signal_kinds.py:69-75`). Operator tooling dispatches on the typed field, NOT by parsing the message. Asserted: `exc = pytest.raises(GateMissingRequiredSignal); assert exc.value.missing == (SignalKind("tests"),)`.
- [ ] **AC-REQ-1** — Source of truth: `self.required_signals` (the gate's own instance attribute), NOT `ctx.gate.required_signals` (does not exist). AST walk over `evaluate` body asserts NO `Attribute(value=Name("ctx"), attr="gate")` access.
- [ ] **AC-REQ-2** — `GateMissingRequiredSignal` raised when any kind in `self.required_signals` is `None` on `os`. The exception's `.missing` lists exactly the missing kinds (sorted alphabetically; deterministic). Parametrized over 6 single-missing cases + 1 two-missing case.
- [ ] **AC-EMPTY-1** — `self.required_signals=(SignalKind("build"),)` AND `os=ObjectiveSignals()` (all-`None`) raises `GateMissingRequiredSignal(missing=(SignalKind("build"),))` — `evaluate` does NOT propagate to `TrustScorer.score([])` (which would raise the categorically distinct `EmptySignals`).
- [ ] **AC-EMPTY-2** — Corner case: `self.required_signals=()` AND `os=ObjectiveSignals()` (all-`None`) raises `GateMissingRequiredSignal(missing=())` with a distinct fallback message ("no required signals and no populated signals — gate cannot evaluate"). Never propagates `EmptySignals`.

### J. `summary` field shape

- [ ] **AC-SUMMARY-1** — Format: `f"strict-AND: {n_passed}/{n_populated} signals passed; failing: {failing_csv_or_none}; confidence={trust_outcome.confidence}"` where `failing_csv_or_none = ",".join(sorted(failing_signals)) or "none"` and `trust_outcome.confidence ∈ {"high", "degraded"}`. Byte-stable substring assertions: `"strict-AND: "`, `"; failing:"`, `"; confidence="` always appear; the failing-csv is `"none"` when empty.
- [ ] **AC-SUMMARY-2** — `len(outcome.summary.encode("utf-8")) <= 4096` (matches `AttemptSummary.prior_failure_summary` byte-cap from S1-04 AC-H-2 — forward compatibility for the runner's `AttemptSummary` construction).
- [ ] **AC-CONF-1** — Confidence propagation: when `_log(tmp_path)` is clean, `outcome.summary` contains `"; confidence=high"`; when `_log(tmp_path)` carries `AdapterDegraded(workflow_id=workflow_id_under_test)`, `outcome.summary` contains `"; confidence=degraded"`.
- [ ] **AC-CONF-2** — Mutation defense: flipping the `event_log` between clean and `AdapterDegraded`-emitting flips the substring; otherwise-identical `(os, ctx)` inputs yield otherwise-identical summaries.

### K. Registry + side-effect import discipline

- [ ] **AC-REG-1** — AST source-scan over `src/codegenie/gates/strict_and.py` AND `tests/gates/test_strict_and.py` forbids ANY reference to `trust_registration` (any module, any symbol) — mirrors S4-04 AC-ANTIPATTERN-1.
- [ ] **AC-REG-2** — File-existence test (mirrors S4-04 AC-ANTIPATTERN-1): `Path("src/codegenie/sandbox/signals/trust_registration.py").exists()` is `False`. Reproduced in this story's test suite so the no-sidecar invariant has redundant defenders.
- [ ] **AC-REG-3** — After `import codegenie.sandbox.signals`, `signal_kind_registry` has exactly 7 kinds. Asserted via `len(signal_kind_registry._origins) == 7` or by collecting via the public `__contains__` interface over the canonical 7-tuple.
- [ ] **AC-REG-4** — The exact set is `{SignalKind("build"), SignalKind("install"), SignalKind("tests"), SignalKind("lockfile_policy"), SignalKind("cve_delta"), SignalKind("trace"), SignalKind("policy")}` — byte-exact.
- [ ] **AC-REG-5** — The adapter operates on the SIX Phase-5 sub-model kinds `{build, install, tests, trace, policy, cve_delta}`. `lockfile_policy` is NOT a Phase-5 sub-model on `ObjectiveSignals` — the adapter never materializes a `TrustSignal(kind=SignalKind("lockfile_policy"), ...)`. AST scan / runtime parametrization both confirm.

### L. Module purity + import allow-list (mirrors S1-04 AC-9 family)

- [ ] **AC-PURITY-1** — `tests/gates/test_strict_and_purity.py` walks every `Import`/`ImportFrom` AST node in `src/codegenie/gates/strict_and.py` and asserts membership in the closed set listed in AC-IMPORT-1. `subprocess`, `os.system`, `pathlib.Path.write_*`, `logging`, `structlog`, `anthropic`, `langgraph`, `chromadb`, `sentence_transformers` are explicitly forbidden.
- [ ] **AC-PURITY-2** — `gates/strict_and.py` declares `from __future__ import annotations` on the first non-docstring line. Module docstring cites ADR-0003, ADR-0014 by name (substring match on file source).
- [ ] **AC-FENCE-1** — `tests/schema/test_no_llm_imports_in_sandbox.py` and `tests/schema/test_no_subprocess_outside_build_chokepoint.py` remain green after `gates/strict_and.py` lands (no new violations).
- [ ] **AC-FENCE-2** — ADR-0014 inheritance: `iter_nested_field_names(GateOutcome)` (via S1-04 AC-INH walker) produces the same set after S4-05 lands as it did before — `strict_and.py` does NOT add any new field name (transitively) containing `confidence`, `llm`, `self_reported`, `model_says`.

### M. Process gates

- [ ] **AC-LOC-1** — `len(Path("src/codegenie/gates/strict_and.py").read_text(encoding="utf-8").splitlines()) <= 60` (total file lines including imports, blank lines, comments).
- [ ] **AC-LOC-2** — AST walk on `strict_and.py` counts executable statements (excluding `ast.Module` docstring, top-level `ast.ImportFrom` / `ast.Import`, `ast.Expr` whose value is a bare `ast.Constant` string, blank lines): `<= 40` executable lines across all classes + helpers.
- [ ] **AC-COV-1** — `pytest --cov=codegenie.gates.strict_and` reports `line ≥ 95%` AND `branch ≥ 90%` (the README floor — line 95, branch 90; NOT "branch ≥ 95%" as the draft conflation pattern would suggest).
- [ ] **AC-TOOL-1** — `ruff check src/codegenie/gates/strict_and.py`, `ruff format --check src/codegenie/gates/strict_and.py`, `mypy --strict src/codegenie/gates/strict_and.py` all pass cleanly.
- [ ] **AC-TDD-1** — TDD plan's red tests (`tests/gates/test_strict_and.py` + `tests/gates/test_strict_and_purity.py`) exist, are committed in the same PR, and (after Green) pass.

## Implementation outline

1. **Module preamble (`src/codegenie/gates/strict_and.py`):**
   ```python
   """S4-05 — StrictAndGate adapter.

   Thin adapter (Phase-5 sandbox-domain ObjectiveSignals → Phase-3 trust-domain
   TrustSignal list) delegating strict-AND scoring to the canonical
   :class:`~codegenie.transforms.trust_scorer.TrustScorer`. Per ADR-0003,
   Phase 5 does NOT ship a second scorer — the equivalence property test in
   ``tests/gates/test_strict_and.py`` ensures any future drift from
   strict-AND breaks loudly at this boundary.

   Per ADR-0014, ``GateOutcome.signals: ObjectiveSignals`` inherits the
   ``extra="forbid", frozen=True`` + banned-substring invariant (transitively
   validated by S1-04 AC-INH using
   :func:`~codegenie.sandbox.signals._introspection.iter_nested_field_names`).

   Functional core / imperative shell (mirrors ``trust_scorer.py:96-123``):
   :func:`_materialize` and :func:`_classify_retry` are pure helpers;
   :meth:`StrictAndGate.evaluate` is the only impure surface (constructs
   :class:`TrustScorer`, calls ``score()``).
   """
   from __future__ import annotations
   # ... imports per AC-IMPORT-1 ...
   ```

2. **Define the exception:**
   ```python
   class GateMissingRequiredSignal(CodegenieError):
       missing: tuple[SignalKind, ...]
       def __init__(self, missing: tuple[SignalKind, ...]) -> None:
           self.missing = tuple(sorted(missing))
           if not self.missing:
               super().__init__("no required signals and no populated signals — gate cannot evaluate")
           else:
               super().__init__(f"required signals missing on ObjectiveSignals: {list(self.missing)}")
   ```
   Check S1-04 for an existing `gates/errors.py` provisioning — if present, declare there instead of `strict_and.py` (single declaration site).

3. **Pure helpers:**
   ```python
   _PHASE_5_KIND_FOR_FIELD: Final[dict[str, SignalKind]] = {
       "build": SignalKind("build"),
       "install": SignalKind("install"),
       "tests": SignalKind("tests"),
       "trace": SignalKind("trace"),
       "policy": SignalKind("policy"),
       "cve_delta": SignalKind("cve_delta"),
   }

   def _materialize(os: ObjectiveSignals, required: tuple[SignalKind, ...]) -> list[TrustSignal]:
       """Pure: ObjectiveSignals → list[TrustSignal] in canonical sort order.

       Iterates the six Phase-5 sub-model fields in deterministic sorted-by-kind
       order; emits one TrustSignal per populated (non-None) sub-model; copies
       `passed` and `details` byte-stable. Never propagates `provenance` or
       `at` (TrustSignal has neither field — outcomes.py:377-388).
       """
       materialized: list[TrustSignal] = []
       for field_name in sorted(_PHASE_5_KIND_FOR_FIELD):
           sub = getattr(os, field_name)
           if sub is None:
               continue
           kind = _PHASE_5_KIND_FOR_FIELD[field_name]
           materialized.append(TrustSignal(kind=kind, passed=sub.passed, details=dict(sub.details)))
       return materialized

   def _classify_retry(failing: list[SignalKind], retry_policy: RetryPolicy) -> tuple[bool, str]:
       """Pure: (failing, retry_policy) → (retryable, state)."""
       if not failing:
           return (False, "passed")
       any_non_retryable = any(k in retry_policy.non_retryable_failures for k in failing)
       all_retryable = all(k in retry_policy.retryable_failures for k in failing)
       if any_non_retryable or not all_retryable:
           return (False, "escalate")
       return (True, "failed_retryable")
   ```

4. **Adapter:**
   ```python
   class StrictAndGate(Gate):
       def __init__(
           self,
           *,
           gate_id: str,
           required_signals: tuple[SignalKind, ...],
           retry_policy: RetryPolicy,
           event_log: EventLog,
       ) -> None:
           self.gate_id = gate_id
           self.required_signals = required_signals
           self.retry_policy = retry_policy
           self._event_log = event_log

       def evaluate(self, os: ObjectiveSignals, ctx: GateContext) -> GateOutcome:
           # 1. Validate every required kind is populated; fail-loud if not.
           missing = tuple(k for k in self.required_signals if getattr(os, k, None) is None)
           if missing or (not self.required_signals and not _any_populated(os)):
               raise GateMissingRequiredSignal(missing)

           # 2. Pure translation.
           materialized = _materialize(os, self.required_signals)

           # 3. Delegate scoring to Phase 3 (the impure surface — but stateless
           #    across calls; see trust_scorer.py:135-137).
           trust_outcome = TrustScorer(event_log=self._event_log).score(materialized)

           # 4. Derive gate-side failing_signals (sorted; intersected with required).
           required_set = set(self.required_signals)
           failing = sorted(
               kind for kind in (_PHASE_5_KIND_FOR_FIELD[f] for f in _PHASE_5_KIND_FOR_FIELD
                                 if getattr(os, f) is not None and not getattr(os, f).passed)
               if kind in required_set
           )
           retryable, state = _classify_retry(failing, self.retry_policy)

           # 5. Build summary (carries the confidence; ≤ 4096 UTF-8 bytes).
           n_pop = sum(1 for f in _PHASE_5_KIND_FOR_FIELD if getattr(os, f) is not None)
           n_pass = n_pop - len(failing)
           failing_csv = ",".join(failing) or "none"
           summary = (f"strict-AND: {n_pass}/{n_pop} signals passed; "
                      f"failing: {failing_csv}; confidence={trust_outcome.confidence}")

           # 6. Derive AttemptNumber from prior_attempts (S1-04 AC-G-4 invariant).
           attempt = AttemptNumber(len(ctx.prior_attempts) + 1)

           return GateOutcome(
               passed=trust_outcome.passed,
               attempt=attempt,
               failing_signals=failing,
               retryable=retryable,
               state=state,
               summary=summary,
               signals=os,
           )
   ```

5. **Wire `__all__`:** `__all__ = ["GateMissingRequiredSignal", "StrictAndGate"]`.

6. **Confirm the `gate_id` convention:** the convention used downstream is `gate_id = TransitionId.STAGE6_VALIDATE.value` (a string; the str-mixin enum yields the value). Until S1-06 / S5-02 ships a distinct typed `GateId`, the constructor accepts `gate_id: str` and tests pass `TransitionId.STAGE6_VALIDATE.value`.

## TDD plan — red / green / refactor

### Red — write the failing test first

**Test file path:** `tests/gates/test_strict_and.py` + `tests/gates/test_strict_and_purity.py`.

```python
# tests/gates/test_strict_and.py
"""S4-05 — StrictAndGate adapter equivalence + cross-field tests.

Side-effect import (fires @register_signal_kind on every Phase-5 collector
module — populates `trace` + `policy` in `signal_kind_registry`). MUST NOT
be replaced with a `trust_registration.py` sidecar import (S4-04
AC-ANTIPATTERN-1).
"""
from __future__ import annotations

import ast
import inspect
import itertools
from datetime import datetime, timezone
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

import codegenie.sandbox.signals  # noqa: F401  (fires kind registration)
from codegenie.gates.contract import GateContext, GateOutcome, RetryPolicy, TransitionId
from codegenie.gates.strict_and import (
    GateMissingRequiredSignal,
    StrictAndGate,
    _classify_retry,
    _materialize,
)
from codegenie.plugins.events import EventLog
from codegenie.sandbox.signals.models import (
    BuildSignal,
    CveDeltaSignal,
    InstallSignal,
    ObjectiveSignals,
    PolicySignal,
    SignalProvenance,
    TestSignal,
    TraceSignal,
)
from codegenie.transforms.outcomes import TrustSignal
from codegenie.transforms.signal_kinds import signal_kind_registry
from codegenie.transforms.trust_scorer import TrustScorer
from codegenie.types.identifiers import AttemptNumber, SignalKind, WorkflowId

# --- Constants ---------------------------------------------------------------

KINDS_5_PHASE_5: tuple[str, ...] = ("build", "install", "tests", "trace", "policy", "cve_delta")
_SUB_FOR_KIND = {
    "build": BuildSignal, "install": InstallSignal, "tests": TestSignal,
    "trace": TraceSignal, "policy": PolicySignal, "cve_delta": CveDeltaSignal,
}

# --- Fixtures ----------------------------------------------------------------

def _now() -> datetime:
    # tz-aware (S1-03 AC-6 — naive datetime rejects at construction).
    return datetime.now(timezone.utc)

def _prov(kind: str) -> SignalProvenance:
    return SignalProvenance(
        signal_kind=SignalKind(kind),
        collector_module=f"codegenie.sandbox.signals.{kind}",
        collector_version="1",
        inputs_blake3="0" * 32,
    )

def _sub(kind: str, passed: bool, details: dict | None = None):
    return _SUB_FOR_KIND[kind](
        passed=passed,
        details=dict(details or {}),
        provenance=_prov(kind),
        at=_now(),
    )

def _os(populated: dict[str, bool]) -> ObjectiveSignals:
    return ObjectiveSignals(**{k: _sub(k, p) for k, p in populated.items()})

@pytest.fixture
def _log(tmp_path) -> EventLog:
    return EventLog(workflow_id=WorkflowId("wf-test"), path=tmp_path / "events.jsonl")

def _gate(
    required: tuple[str, ...],
    *,
    non_retryable: tuple[str, ...] = (),
    event_log: EventLog,
) -> StrictAndGate:
    rp = RetryPolicy(
        max_attempts=AttemptNumber(3),
        retryable_failures=[SignalKind(k) for k in KINDS_5_PHASE_5 if k not in non_retryable],
        non_retryable_failures=[SignalKind(k) for k in non_retryable],
        timeout_retryable=False,
    )
    return StrictAndGate(
        gate_id=TransitionId.STAGE6_VALIDATE.value,
        required_signals=tuple(SignalKind(k) for k in required),
        retry_policy=rp,
        event_log=event_log,
    )

def _ctx(*, prior_attempts: tuple = ()) -> GateContext:
    # `attempt` is derived from len(prior_attempts) + 1; no `attempt` field here.
    return GateContext.model_construct(
        worktree=Path("/tmp/wt"), advisory="adv", recipe="rec", transform_output="to",
        prior_attempts=list(prior_attempts),
    )


# --- A. Import surface + constructor ----------------------------------------

def test_imports_are_idempotent():
    import codegenie.gates.strict_and as m1
    import codegenie.gates.strict_and as m2
    assert m1 is m2

def test_all_is_byte_exact():
    import codegenie.gates.strict_and as m
    assert set(m.__all__) == {"GateMissingRequiredSignal", "StrictAndGate"}

def test_constructor_signature_keyword_only(_log):
    sig = inspect.signature(StrictAndGate.__init__)
    params = list(sig.parameters.values())[1:]  # skip self
    names = [p.name for p in params]
    assert names == ["gate_id", "required_signals", "retry_policy", "event_log"]
    assert all(p.kind == inspect.Parameter.KEYWORD_ONLY for p in params)


# --- B. ABC conformance ------------------------------------------------------

def test_strict_and_gate_is_concrete_subclass(_log):
    from codegenie.gates.contract import Gate
    assert issubclass(StrictAndGate, Gate)
    assert not inspect.isabstract(StrictAndGate)
    g = _gate(required=("build",), event_log=_log)
    assert g.gate_id == "stage6_validate"
    assert g.required_signals == (SignalKind("build"),)


# --- C. evaluate signature + pure-helper split -------------------------------

def test_evaluate_signature_exact():
    sig = inspect.signature(StrictAndGate.evaluate)
    params = [(p.name, p.annotation) for p in sig.parameters.values()]
    # self, os: ObjectiveSignals, ctx: GateContext
    assert [p[0] for p in params] == ["self", "os", "ctx"]

def test_pure_helpers_are_module_private():
    import codegenie.gates.strict_and as m
    assert hasattr(m, "_materialize")
    assert hasattr(m, "_classify_retry")
    assert "_materialize" not in m.__all__
    assert "_classify_retry" not in m.__all__


# --- D. _materialize --------------------------------------------------------

def test_materialize_emits_only_populated():
    os_ = _os({"build": True, "tests": False})
    out = _materialize(os_, required=tuple(SignalKind(k) for k in KINDS_5_PHASE_5))
    assert len(out) == 2
    assert all(isinstance(ts, TrustSignal) for ts in out)
    kinds = {ts.kind for ts in out}
    assert kinds == {SignalKind("build"), SignalKind("tests")}

def test_materialize_three_field_shape_only():
    out = _materialize(_os({"build": True}), required=(SignalKind("build"),))
    assert set(out[0].model_fields) == {"kind", "passed", "details"}

@pytest.mark.parametrize("combo", list(itertools.product([True, False], repeat=6)))
def test_materialize_passed_faithfulness_64_cases(combo):
    populated = dict(zip(KINDS_5_PHASE_5, combo))
    out = _materialize(_os(populated), required=tuple(SignalKind(k) for k in KINDS_5_PHASE_5))
    for ts in out:
        # The kind string equals one of our populated keys; passed must match.
        assert ts.passed is populated[ts.kind]

def test_materialize_details_round_trip_byte_exact():
    sub = BuildSignal(
        passed=False,
        details={"k": "v", "i": 7, "b": True},
        provenance=_prov("build"),
        at=_now(),
    )
    os_ = ObjectiveSignals(build=sub)
    [ts] = _materialize(os_, required=(SignalKind("build"),))
    assert ts.details == {"k": "v", "i": 7, "b": True}
    assert type(ts.details["b"]) is bool
    assert type(ts.details["i"]) is int  # no bool↔int coercion


# --- E. failing_signals deterministic + intersect ----------------------------

@pytest.mark.parametrize("perm_order", [
    ("build", "tests", "trace"),
    ("trace", "build", "tests"),
    ("tests", "trace", "build"),
])
def test_failing_signals_is_sorted_regardless_of_source_order(_log, perm_order):
    # All three permutations populate the same three failing kinds; output must
    # be the same sorted list (M-3 mutation defense — passthrough of
    # TrustOutcome.failing would yield caller-order, not sorted).
    populated = {k: False for k in perm_order}
    os_ = _os(populated)
    g = _gate(required=tuple(perm_order), event_log=_log)
    out = g.evaluate(os_, _ctx())
    assert out.failing_signals == sorted([SignalKind(k) for k in perm_order])

def test_failing_signals_excludes_non_required_failing_kinds(_log):
    os_ = _os({"build": True, "tests": False})
    g = _gate(required=("build",), event_log=_log)
    out = g.evaluate(os_, _ctx())
    assert out.failing_signals == []
    assert out.passed is True


# --- F. state / retryable cross-field ---------------------------------------

@pytest.mark.parametrize("combo", list(itertools.product([True, False], repeat=6)))
def test_state_is_three_set_only_never_failed_unrecoverable(_log, combo):
    populated = dict(zip(KINDS_5_PHASE_5, combo))
    os_ = _os(populated)
    g = _gate(required=KINDS_5_PHASE_5, event_log=_log)
    out = g.evaluate(os_, _ctx())
    assert out.state in {"passed", "failed_retryable", "escalate"}
    assert out.state != "failed_unrecoverable"

def test_non_retryable_failure_state_is_escalate(_log):
    populated = {"build": True, "install": True, "tests": True, "trace": False,
                 "policy": True, "cve_delta": True}
    os_ = _os(populated)
    g = _gate(required=KINDS_5_PHASE_5, non_retryable=("trace",), event_log=_log)
    out = g.evaluate(os_, _ctx())
    assert out.passed is False
    assert out.state == "escalate"
    assert out.retryable is False

def test_retryable_failure_state_is_failed_retryable(_log):
    populated = {"build": True, "install": True, "tests": False, "trace": True,
                 "policy": True, "cve_delta": True}
    os_ = _os(populated)
    g = _gate(required=KINDS_5_PHASE_5, non_retryable=("trace",), event_log=_log)
    out = g.evaluate(os_, _ctx())
    assert out.passed is False
    assert out.state == "failed_retryable"
    assert out.retryable is True


# --- G. Phase-3 strict-AND equivalence (LOAD-BEARING) -----------------------

@pytest.mark.parametrize("combo", list(itertools.product([True, False], repeat=6)))
def test_64_case_equivalence_with_phase3(_log, combo):
    """ADR-0003 load-bearing — if Phase 3 drifts from strict-AND, this fails LOUDLY."""
    populated = dict(zip(KINDS_5_PHASE_5, combo))
    os_ = _os(populated)
    g = _gate(required=KINDS_5_PHASE_5, event_log=_log)
    out = g.evaluate(os_, _ctx())
    materialized = [
        TrustSignal(kind=SignalKind(k), passed=p, details={})
        for k, p in populated.items()
    ]
    phase3 = TrustScorer(event_log=_log).score(materialized)
    assert out.passed == phase3.passed
    assert out.passed == all(populated.values())

@given(st.dictionaries(
    keys=st.sampled_from(KINDS_5_PHASE_5),
    values=st.booleans(),
    min_size=1, max_size=6,
))
@settings(deadline=None, max_examples=500, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_equivalence_property_over_arbitrary_subsets(populated):
    # ADR-0003 — equivalence holds across the open subset space.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        log = EventLog(workflow_id=WorkflowId("wf-prop"), path=Path(td) / "events.jsonl")
        os_ = _os(populated)
        present = tuple(populated.keys())
        g = _gate(required=present, event_log=log)
        out = g.evaluate(os_, _ctx())
        materialized = [
            TrustSignal(kind=SignalKind(k), passed=p, details={})
            for k, p in populated.items()
        ]
        phase3 = TrustScorer(event_log=log).score(materialized)
        assert out.passed == phase3.passed


# --- H. AttemptNumber derivation --------------------------------------------

@pytest.mark.parametrize("n_priors,expected", [(0, 1), (1, 2), (2, 3)])
def test_attempt_derived_from_prior_attempts(_log, n_priors, expected):
    os_ = _os({"build": True})
    g = _gate(required=("build",), event_log=_log)
    # Build N synthetic AttemptSummary stand-ins; model_construct skips validation
    # so the test does not depend on AttemptSummary's full shape here.
    ctx = _ctx(prior_attempts=tuple(object() for _ in range(n_priors)))
    out = g.evaluate(os_, ctx)
    assert out.attempt == AttemptNumber(expected)


# --- I. Exception shape ------------------------------------------------------

def test_missing_required_signal_raises_with_typed_missing_attribute(_log):
    os_ = _os({"build": True, "install": True})  # missing tests, trace, policy, cve_delta
    g = _gate(required=KINDS_5_PHASE_5, event_log=_log)
    with pytest.raises(GateMissingRequiredSignal) as exc_info:
        g.evaluate(os_, _ctx())
    exc = exc_info.value
    # Typed attribute — operator tooling dispatches on this, NOT the message.
    assert exc.missing == tuple(sorted(SignalKind(k) for k in
                                       ("tests", "trace", "policy", "cve_delta")))

def test_required_signals_empty_and_os_all_none_raises_with_distinct_message(_log):
    os_ = ObjectiveSignals()  # all None
    g = _gate(required=(), event_log=_log)
    with pytest.raises(GateMissingRequiredSignal) as exc_info:
        g.evaluate(os_, _ctx())
    assert exc_info.value.missing == ()
    assert "no required signals and no populated signals" in str(exc_info.value)

def test_required_signals_non_empty_but_os_all_none_raises_before_phase3(_log):
    # NEVER propagates the categorically-distinct EmptySignals from Phase 3.
    os_ = ObjectiveSignals()
    g = _gate(required=("build",), event_log=_log)
    with pytest.raises(GateMissingRequiredSignal):
        g.evaluate(os_, _ctx())


# --- J. summary field shape + confidence propagation ------------------------

def test_summary_contains_canonical_substrings_when_passing(_log):
    os_ = _os({"build": True, "tests": True})
    g = _gate(required=("build", "tests"), event_log=_log)
    out = g.evaluate(os_, _ctx())
    assert "strict-AND: 2/2 signals passed" in out.summary
    assert "failing: none" in out.summary
    assert "confidence=high" in out.summary

def test_summary_contains_failing_csv_alphabetically_when_failing(_log):
    os_ = _os({"build": False, "tests": False})
    g = _gate(required=("build", "tests"), event_log=_log)
    out = g.evaluate(os_, _ctx())
    assert "failing: build,tests" in out.summary

def test_summary_byte_capped_at_4096_utf8(_log):
    # Largest realistic case: all 6 populated, all failing — summary still small.
    os_ = _os({k: False for k in KINDS_5_PHASE_5})
    g = _gate(required=KINDS_5_PHASE_5, event_log=_log)
    out = g.evaluate(os_, _ctx())
    assert len(out.summary.encode("utf-8")) <= 4096

def test_confidence_propagates_to_summary_when_event_log_carries_adapter_degraded(tmp_path):
    from codegenie.plugins.events import AdapterDegraded
    log = EventLog(workflow_id=WorkflowId("wf-degraded"), path=tmp_path / "events.jsonl")
    log.append(AdapterDegraded(workflow_id=WorkflowId("wf-degraded"), reason="rate_limited"))
    os_ = _os({"build": True})
    g = _gate(required=("build",), event_log=log)
    out = g.evaluate(os_, _ctx())
    assert "confidence=degraded" in out.summary


# --- K. Registry + side-effect import discipline ----------------------------

def test_signal_kind_registry_has_exactly_seven_kinds_after_sandbox_import():
    expected = {SignalKind(k) for k in
                ("build", "install", "tests", "lockfile_policy", "cve_delta", "trace", "policy")}
    for kind in expected:
        assert kind in signal_kind_registry
    # No surprise extras (membership test for any plausible extras):
    for surprise in ("baseimage", "shell_presence", "anything_else"):
        assert SignalKind(surprise) not in signal_kind_registry

def test_no_trust_registration_sidecar_module_exists():
    # Mirrors S4-04 AC-ANTIPATTERN-1 — redundant defender at this story's layer.
    assert not Path("src/codegenie/sandbox/signals/trust_registration.py").exists()

def test_strict_and_source_makes_no_reference_to_trust_registration():
    src = Path("src/codegenie/gates/strict_and.py").read_text(encoding="utf-8")
    assert "trust_registration" not in src

def test_strict_and_source_makes_no_passthrough_of_trust_outcome_failing():
    # AC-FS-3 — AST scan forbids `score.failing` / `.failing` attribute access
    # on any TrustOutcome value (the M-3/M-4 mutation defenders).
    src = Path("src/codegenie/gates/strict_and.py").read_text(encoding="utf-8")
    assert ".failing" not in src  # crude but sufficient for ~40 LOC


# --- M. LOC budget ----------------------------------------------------------

def test_total_loc_under_60():
    src_lines = Path("src/codegenie/gates/strict_and.py").read_text(
        encoding="utf-8").splitlines()
    assert len(src_lines) <= 60

def test_executable_loc_under_40():
    src = Path("src/codegenie/gates/strict_and.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    # Count executable statements (rough but adequate at ~40 LOC scale):
    # excludes module docstring, top-level imports, and bare-string Expr stmts.
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                              ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Return,
                              ast.If, ast.For, ast.While, ast.Try, ast.Raise)):
            count += 1
    assert count <= 40
```

```python
# tests/gates/test_strict_and_purity.py
"""Module-purity walker mirroring S1-04 test_contract_purity.py.

Asserts strict_and.py imports nothing outside the closed allow-list, and
that no forbidden patterns appear in the source.
"""
from __future__ import annotations
import ast
from pathlib import Path

_SRC = Path("src/codegenie/gates/strict_and.py")

_ALLOWED_IMPORTS = frozenset({
    "__future__",
    "typing",
    "codegenie.errors",
    "codegenie.gates.contract",
    "codegenie.sandbox.signals.models",
    "codegenie.transforms.outcomes",
    "codegenie.transforms.trust_scorer",
    "codegenie.transforms.signal_kinds",
    "codegenie.types.identifiers",
    "codegenie.plugins.events",  # TYPE_CHECKING only
})

_FORBIDDEN_SUBSTRINGS = ("subprocess", "os.system", "os.popen", "structlog",
                         "logging", "anthropic", "langgraph", "chromadb",
                         "sentence_transformers")


def test_imports_within_allowlist():
    tree = ast.parse(_SRC.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name in _ALLOWED_IMPORTS, alias.name
        elif isinstance(node, ast.ImportFrom):
            assert node.module in _ALLOWED_IMPORTS, node.module


def test_no_forbidden_substrings_in_source():
    src = _SRC.read_text(encoding="utf-8")
    for needle in _FORBIDDEN_SUBSTRINGS:
        assert needle not in src, needle


def test_module_docstring_cites_adrs():
    src = _SRC.read_text(encoding="utf-8")
    for adr in ("ADR-0003", "ADR-0014"):
        assert adr in src, adr


def test_future_annotations_present():
    src = _SRC.read_text(encoding="utf-8")
    assert "from __future__ import annotations" in src
```

### Green — make it pass

- Write `gates/strict_and.py` per the outline; keep the body ≤ 40 executable lines (~55-60 total file lines incl. docstring + imports + the two pure helpers + the adapter class).
- Wire `GateMissingRequiredSignal` per the typed-attribute pattern; check `gates/errors.py` first for an existing provisioning from S1-04.
- If `lockfile_policy` is not yet pre-populated on `signal_kind_registry` from the production codebase, surface the contradiction to the user before continuing — do NOT silently register it from this story.

### Refactor — clean up

- Inline anything used exactly once OUTSIDE the two named pure helpers (`_materialize`, `_classify_retry`) — those two earn their keep by being independently testable. The adapter's whole virtue is being a thin translation surface; extra helpers blur ADR-0003's "thin adapter" stance.
- Keep the `_PHASE_5_KIND_FOR_FIELD` `Final[dict[...]]` module-level catalog (mirrors the `_GENERATOR_HEADER_MARKERS` / `_REFLECTION_QUERIES` pattern from existing probe modules — iterated, never branched on). Extending to Phase 7 `baseimage`/`shell_presence` is one entry in this dict + the corresponding ObjectiveSignals widening.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/gates/strict_and.py` | The ~40 LOC adapter + two pure helpers + `GateMissingRequiredSignal` (if not already in `gates/errors.py`). |
| `src/codegenie/gates/errors.py` | Add `GateMissingRequiredSignal` IF S1-04 didn't (check first; single declaration site). |
| `src/codegenie/gates/__init__.py` | Re-export `StrictAndGate` AND `GateMissingRequiredSignal` (the public surface this story ships). |
| `tests/gates/test_strict_and.py` | 64-case enumerative + property + adversarial + cross-field + summary + LOC budget. |
| `tests/gates/test_strict_and_purity.py` | Module-purity walker mirroring S1-04 `test_contract_purity.py`. |

## Out of scope

- The three-retry loop, retry-1/retry-2 timing — `GateRunner` (S5-02).
- `failed_unrecoverable` 3× detection — `GateRunner` (S5-02).
- `ReplanHook` invocation — `GateRunner` + S5-01.
- `from_yaml` factory (catalog-loader construction) — owner TBD between S1-06 (catalog schema) and S5-02 (runner instantiation). S4-05 ships only the constructor-injected adapter.
- Widening `GateOutcome` with a first-class `confidence` field — S1-04 contract is frozen; the adapter propagates confidence via the `summary` tail substring only. Future widening requires a paired ADR + S1-04 amendment.
- `@register_gate` registry — N=1 today (forward seam only).
- Phase-7 `baseimage` / `shell_presence` sub-models on `ObjectiveSignals` — out-of-scope here; the adapter's `_PHASE_5_KIND_FOR_FIELD` catalog auto-extends when those land.

## Notes for the implementer

1. **Adapter pattern** — `StrictAndGate` is a textbook anti-corruption-layer / hexagonal-port adapter between the Phase-5 sandbox-domain (`ObjectiveSignals`) and the Phase-3 trust-domain (`list[TrustSignal]`). The 40-LOC budget is the design — if you find yourself adding logic beyond "translate, delegate, build outcome", you're in the wrong place. ADR-0003 §Tradeoffs row 1: "Single source of truth for strict-AND scoring — Phase 3's logic is reused untouched."
2. **The equivalence test is the load-bearing artifact, not the LOC count.** If Phase 3's `TrustScorer.score(...)` changes to weighted scoring, this test fails loudly. That's the design.
3. **`failing_signals` is DELIBERATELY gate-side, NOT a passthrough of `TrustOutcome.failing`.** Phase-3's `TrustOutcome.failing` is caller-order (`trust_scorer.py:99-104` — "never sorted or deduplicated"). Phase-5's `GateOutcome.failing_signals` is sorted alphabetically for ledger-replay determinism (`attempts.jsonl` chain), intersected with `self.required_signals` so non-required populated failures are excluded. The equivalence property test binds only on `passed` — the strict-AND result — and that's the load-bearing contract.
4. **`AttemptNumber` derivation is `len(ctx.prior_attempts) + 1`** — never `ctx.attempt` (does not exist on `GateContext`). Per S1-04 AC-J-3, the resulting `AttemptNumber` is bounded 1..1024; the bound is inherited via the `GateOutcome.attempt` field validator. Do NOT silently clamp.
5. **`TrustScorer` is stateless across `score()` calls** (`trust_scorer.py:135-137`). Constructing per `evaluate()` call is acceptable; constructing once at gate construction and reusing the instance is also acceptable. Both honor the constructor-injected `EventLog` contract.
6. **`confidence` propagation decision** — Phase-3's `TrustOutcome.confidence: Literal["high", "degraded"]` is carried into `GateOutcome.summary` as a tail substring rather than as a first-class field. Widening `GateOutcome` (S1-04-owned, frozen) to carry confidence as a typed field is a future story (paired ADR + amendment). The summary-substring channel is the audit trail today; downstream consumers that need it can parse it (rare — Phase 6's reducer dispatches on `state`, not `confidence`).
7. **Side-effect import for kind registration** — `import codegenie.sandbox.signals` is the canonical trigger (per S4-04 ACs). NEVER introduce a `trust_registration.py` sidecar — S4-04 has an explicit file-existence anti-pattern AC, and this story has a redundant defender (AC-REG-1 / AC-REG-2).
8. **`GateMissingRequiredSignal` typed `.missing` attribute** mirrors the `SignalKindAlreadyRegistered.{name, existing, duplicate}` precedent from `transforms/signal_kinds.py:69-75`. Operator tooling dispatches on the typed field — never parse the message. The fallback empty-`missing` case (`required_signals=()` + `os` all-`None`) has a distinct message ("no required signals and no populated signals — gate cannot evaluate") so the operator can disambiguate even when `.missing` is the empty tuple.
9. **`gate_id` convention** — `TransitionId.STAGE6_VALIDATE.value` is the string; the str-mixin enum yields the value. Until S1-06 / S5-02 provisions a distinct typed `GateId`, the constructor accepts `gate_id: str`. Surface as Open ambiguity (resolved): the gate-id-vs-transition-id distinction will sharpen when the catalog loader lands.
10. **Forward seam — `@register_gate` registry.** StrictAndGate is N=1 concrete `Gate`. The kernel-extract precedent from `signal_kinds.py` (`Final` singleton + per-instance `.fresh()` for tests) is the path forward when a 2nd gate (e.g., `LooseGate`, `WeightedScoreGate`) ships. Today, per Rule 2, no abstraction is extracted; the `from_yaml` catalog-loader path will provide registry-like dispatch when it lands.
11. **`_PHASE_5_KIND_FOR_FIELD: Final[dict[str, SignalKind]]` catalog** — module-level frozen dict mirroring the `_GENERATOR_HEADER_MARKERS` / `_REFLECTION_QUERIES` pattern from probe modules. Iterated, never branched on. Phase 7 widens by adding one entry (and the corresponding `ObjectiveSignals` field) — never edits the iteration logic.
12. **No `subprocess`, no `pathlib.Path.write_*`, no `logging`/`structlog`, no `anthropic`/`langgraph` imports** — the module-purity AC is non-negotiable; this is a pure translation surface. If you find yourself reaching for filesystem or logger, you're conflating the adapter with the runner (S5-02 owns logging emission + filesystem writes).
13. **Test ordering note** — `tests/gates/test_strict_and.py` depends on the Phase-5 sandbox-signals collector modules being importable (so `import codegenie.sandbox.signals` fires the `@register_signal_kind` decorators). If `S4-01..S4-03` haven't shipped yet on `master`, surface this story's runtime dependency to the user before running the test suite. The story is unblocked structurally (S4-01..S4-04 are GREEN per the status snapshot) — surface only if reality has diverged.
