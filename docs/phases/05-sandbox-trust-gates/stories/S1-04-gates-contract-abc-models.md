# Story S1-04 — `gates/contract.py` — `Gate` ABC, `GateContext`, `GateOutcome`, `RetryPolicy`, `AttemptSummary`, `TransitionId`

**Step:** Step 1 — Scaffold packages, contracts, and CI fences
**Status:** Ready (Hardened 2026-05-22)
**Effort:** M
**Depends on:** S1-01, S1-02 (`RunId` newtype), S1-03 (`SignalKind` newtype + `ObjectiveSignals` + `iter_nested_field_names`)
**ADRs honored:** ADR-0006, ADR-0002, ADR-0014, ADR-0008

## Validation notes (2026-05-22)

Hardened via `phase-story-validator` (verdict: HARDENED). Source-of-truth contradictions resolved against [`../phase-arch-design.md §Data model`](../phase-arch-design.md), [ADR-0006](../ADRs/0006-protocol-vs-abc-convention.md), [ADR-0002](../ADRs/0002-additive-prior-attempts-kwarg.md), [ADR-0014](../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md), [ADR-0008](../ADRs/0008-llm-judge-persona-deferral.md), and codebase precedents ([`src/codegenie/types/identifiers.py`](../../../../src/codegenie/types/identifiers.py), [`src/codegenie/adapters/protocols.py`](../../../../src/codegenie/adapters/protocols.py), [`src/codegenie/result.py`](../../../../src/codegenie/result.py)), plus the just-hardened S1-02 and S1-03 reports. Full report: [`_validation/S1-04-gates-contract-abc-models.md`](_validation/S1-04-gates-contract-abc-models.md).

Headline edits (every weakness the four critics flagged would have let a structurally-wrong implementation slip past the executor's validator):

1. **`SignalKind` is IMPORTED, not redefined.** The draft Implementation outline §2 said "Define `SignalKind = str`" (arch line 721 placeholder). But S1-03 promoted `SignalKind = NewType("SignalKind", str)` to [`src/codegenie/types/identifiers.py:96`](../../../../src/codegenie/types/identifiers.py:96), and S1-03 AC-4c is an AST chokepoint that **forbids any `NewType("SignalKind", ...)` redefinition under `src/codegenie/gates/`**. An executor following the draft literally would have failed S1-03's chokepoint test. Fix: import `SignalKind` from `codegenie.types.identifiers`; new AC-S asserts the source-level annotation pin (`get_type_hints` returns the imported `SignalKind`, not a re-declared one).
2. **Canonical literal spellings pinned positively** (mirrors S1-02 M-6/M-7). Draft asserted only the negative case (`state="weird_state"` rejected). An executor shipping `Literal["pass", "fail_r", "fail_u", "esc"]` would pass every test silently — but Phase 6 LangGraph's `Command(goto=...)/interrupt()` mapping keys on the byte-exact spellings. New AC asserts `typing.get_args(...) == ("passed", "failed_retryable", "failed_unrecoverable", "escalate")` AND parametrized positive construction across all four states.
3. **`GateOutcome` cross-field invariants enforced** (illegal-states-unrepresentable, mirrors S1-02 AC-7b/c/d). The draft permitted `GateOutcome(passed=True, state="failed_retryable", retryable=True, failing_signals=["tests"])` — a structurally nonsense outcome that downstream consumers (Phase 6 reducer, `RetryLedger`, Phase 11 reviewer) would treat as authoritative. Added `@model_validator(mode="after")` enforcing the four cross-state invariants (see AC-CF group).
4. **`extra="forbid", frozen=True` asserted *directly* via `model_config` introspection on every Pydantic model** (mirrors S1-02 M-2 and S1-03's same gap). Draft tested only `RetryPolicy` for frozen+extra (`test_models_are_frozen_and_extra_forbid`). The other five Pydantic models (`AttemptSummary`, `GateContext`, `GateOutcome`, `Attempt`, plus future `RetryPolicy` if Pydantic-validated) could have silently shipped `extra="ignore"`. New parametrized test covers all five.
5. **`with_prior_attempt` signature widened with `sandbox_run_id: RunId` kwarg.** Arch line 749's signature `with_prior_attempt(self, outcome: GateOutcome) -> "GateContext"` is unrealizable: `AttemptSummary.sandbox_run_id` cannot be derived from `outcome` alone (neither `GateOutcome` nor `SignalProvenance` carries it; `Attempt.sandbox_run_id` is where it lives but `GateOutcome` does not). Per arch §Component design — GateRunner step 6, the runner has access to `run.run_id` at the callsite. Resolved by widening the signature to accept a `sandbox_run_id: RunId` kwarg. Documented as "Open ambiguity (resolved)" — surface for S5-02 executor.
6. **`with_prior_attempt` semantics tightened.** Draft asserted "length increases by 1; original untouched." Added positional check (`new.prior_attempts[-1]` is the freshly-appended summary, not prepended), list-identity check (`new.prior_attempts is not ctx.prior_attempts`), and a three-attempt accumulation test (calling three times produces a length-3 list in correct order). Mutation testing this matters: an executor shipping `prior_attempts = [summary] + prior_attempts` (prepend) would pass the original AC.
7. **`ReplanHook.__call__` return type uses the existing `RecipeOutcome` sum type, NOT the draft's nonexistent `RecipeApplication`.** Draft annotated `__call__(self, ctx: GateContext) -> RecipeApplication` — but `RecipeApplication` does not exist anywhere in the codebase; the actual Phase-3 transform-outcome type is `codegenie.transforms.outcomes.RecipeOutcome` (the `Applied | Skipped | NotApplicable | Failed` union shipped GREEN). An executor following the draft would invent a `RecipeApplication` type that contradicts S5-01's integration test. Fix: `__call__` returns `RecipeOutcome` (TYPE_CHECKING import; string annotation `"RecipeOutcome"` to avoid runtime cycle); documented in Notes.
8. **`AttemptNumber` newtype adopted from `types/identifiers.py:102`** (CLAUDE.md "newtype when crossing ≥ 2 modules"; rule-of-three already cleared). The identifier was created explicitly for *this story* — see the docstring `"Bounded retry counter (1..1024); S1-04 AttemptSummary.attempt."` Fields adopting it: `AttemptSummary.attempt_id`, `Attempt.attempt_id`, `GateOutcome.attempt`, `RetryPolicy.max_attempts`. Per the identifier doc the bound is 1..1024 — encoded as `Annotated[int, Field(ge=1, le=1024)]` on the Pydantic field where the NewType is opaque.
9. **`prev_hash`/`chain_hash` validator tightened to LOWERCASE hex** (32 chars, regex `^[0-9a-f]{32}$`). Draft AC said "32-char hex strings" — uppercase `"A"*32` would pass `int(v, 16)`. ADR-0005 (Phase 4 chain-head compatibility) requires lowercase canonical hex; a chain extension producing uppercase would mismatch on replay verification. Negative test: parametrized rejection on uppercase, mixed-case, and non-hex.
10. **`TransitionId` member set + str-enum mixin pinned.** Draft asserted member values but not the *member set* (so an executor adding a third member `STAGE7_BUILD = "stage7_build"` would pass every existing test). Added AC asserting `set(TransitionId.__members__) == {"STAGE6_VALIDATE", "STAGE6_VALIDATE_LOOSE"}` and `issubclass(TransitionId, str)` (so YAML/JSON round-trip yields the value, not `<TransitionId.X: "...">`).
11. **`RetryPolicy.retryable_failures ⊥ non_retryable_failures` cross-field invariant.** A signal listed in both classifications is ambiguous — `StrictAndGate.evaluate` would have undefined dispatch. Added `@model_validator(mode="after")` enforcing disjoint sets + a paired AC. (`StrictAndGate` is S4-05; making the contract reject the contradiction *here* means S4-05 inherits illegal-states-unrepresentable.)
12. **`Attempt.ended_at >= Attempt.started_at`** (mirrors S1-02 AC-7c). Draft permitted reversed timestamps. Added `@model_validator(mode="after")` + paired AC.
13. **ADR-0014 inheritance check is a HARD AC, not a Refactor "confirm."** Promoted to AC-INH: reuse S1-03's `iter_nested_field_names` from `codegenie.sandbox.signals._introspection` and walk `Attempt`, `GateOutcome`, `GateContext`, `AttemptSummary`, `RetryPolicy` field names — no name (transitively) may contain the four banned substrings (`confidence`, `llm`, `self_reported`, `model_says`). New test file `tests/gates/test_contract_field_names_static.py`.
14. **Module purity + `__future__ annotations` + `__all__` discipline** (mirrors S1-02 AC-9 / AC-9a / AC-9b precedent). Module docstring cites all four ADRs (-0006, -0002, -0014, -0008); `from __future__ import annotations` is line 1; `__all__` is alphabetized; imports are restricted to stdlib + pydantic + `codegenie.{errors,types.identifiers,sandbox.contract,sandbox.signals.models}`. New `tests/gates/test_contract_purity.py`.
15. **Coverage floor wording corrected.** Draft AC said "≥ 95%" without specifying line vs branch — README is **95 line / 90 branch**. Same conflation the S1-02 and S1-03 hardening fixed; consistency requires the same wording everywhere.
16. **Forward-seam note** added: `GateOutcome.state` is a *closed mirror* of Phase 6 LangGraph's `Command(goto=...)/interrupt()` dispatch. Adding a 5th state requires ADR amendment (and a paired Phase 6 reducer update) — *not* a silent widening to `str`. Mirrors S1-02's "closed Literal of an open registry" pattern.
17. **`evidence_paths` shape pinned** in AC. Arch line 737 declares `evidence_paths: dict[str, Path]`; draft used it in a fixture but no AC asserted the annotation. Added AC-EP asserting `typing.get_type_hints(AttemptSummary)['evidence_paths']` returns exactly `dict[str, Path]` (not `dict[str, str]`, not `Mapping[str, Path]`).
18. **`prior_failure_summary` cap is 4096 bytes UTF-8 (the 4 KiB cap from arch)**, asserted via `len(v.encode("utf-8")) <= 4096`. Draft was character-count which diverges from arch §Harness engineering byte-budget under multibyte content. Added an AC with a multibyte boundary test.

No `RESCUE`-tier findings — every gap was patchable by adding ACs, tightening the TDD plan, and routing through `types/identifiers.py`. No Stage-3 research needed; every gap was answerable from Phase 5 arch + the four honored ADRs + `types/identifiers.py` + S1-02/S1-03 hardened reports.

## Context

`Gate` is one of the three load-bearing public abstractions in Phase 5 — the strict-AND scoring surface. Per ADR-0006, `Gate` is declared as an ABC (subclasses share `gate_id`/`required_signals`/`retry_policy` defaults) whereas `SandboxClient` is a Protocol. This story ships the abstract base plus the five frozen Pydantic models the gate seam exchanges with the runner, the orchestrator, and Phase 4 — `GateContext` (orchestrator → runner), `GateOutcome` (gate → runner / orchestrator), `RetryPolicy` (YAML → gate), `AttemptSummary` (runner → Phase 4 via `prior_attempts`), plus the `TransitionId` enum, the `ReplanHook` Protocol, and the internal `Attempt` model the ledger writes.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Gate (ABC) + StrictAndGate` — exact `Gate` signature with `gate_id`, `required_signals: tuple[SignalKind, ...]`, `retry_policy`, `evaluate` abstract method.
  - `../phase-arch-design.md §Data model — gates/contract.py` — pseudo-code for `RetryPolicy`, `AttemptSummary`, `GateContext`, `GateOutcome`, `TransitionId`, `Attempt`.
  - `../phase-arch-design.md §Component design — GateRunner` — confirms `GateContext.with_prior_attempt(outcome) -> GateContext` (signature widened by Validation note #5).
  - `../phase-arch-design.md §Edge case 17` + `§Control flow` — `state` ∈ `{"passed", "failed_retryable", "failed_unrecoverable", "escalate"}` semantics.
  - `../phase-arch-design.md §Integration with Phase 6` — `GateOutcome.state` maps to LangGraph `Command(goto=...) / interrupt()`.
- **Phase ADRs (rules this story honors):**
  - `../ADRs/0006-protocol-vs-abc-convention.md` — ADR-0006 — `Gate` is `abc.ABC`.
  - `../ADRs/0002-additive-prior-attempts-kwarg.md` — ADR-0002 — `AttemptSummary` is the structured retry-feedback payload; Phase 4's kwarg landing site.
  - `../ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — ADR-0014 — `Attempt.signals: ObjectiveSignals` and `GateOutcome.signals: ObjectiveSignals` inherit the static invariant; banned-substring scan extends to top-level field names of every model in this file (AC-INH).
  - `../ADRs/0008-llm-judge-persona-deferral.md` — ADR-0008 — `AttemptSummary.prior_failure_summary` is fence-wrapped text, not LLM-generated trust input.
- **Source design:**
  - `../final-design.md §Component-3` (Gate) and `§Component-6` (AttemptSummary contract).
- **High-level impl:**
  - `../High-level-impl.md §Step 1 — Features delivered` bullet 4.
- **Identifiers home (per S1-03):**
  - [`src/codegenie/types/identifiers.py`](../../../../src/codegenie/types/identifiers.py) — `SignalKind` (line 96), `AttemptNumber` (line 102, created explicitly for this story), `WorkflowId` (line 82), `RunId` (in `sandbox/contract.py` per S1-02).

## Goal

Ship `src/codegenie/gates/contract.py` exposing the `Gate` ABC, the `TransitionId` enum, the `ReplanHook` Protocol (return type `RecipeOutcome`), and the five frozen `extra="forbid"` Pydantic models (`RetryPolicy`, `AttemptSummary`, `GateContext`, `GateOutcome`, `Attempt`) — with `SignalKind` and `AttemptNumber` IMPORTED from `codegenie.types.identifiers` and `RunId` IMPORTED from `codegenie.sandbox.contract`, never redefined.

## Acceptance criteria

### A. Import surface and `__all__`

- [ ] **AC-1 — Import:** `from codegenie.gates.contract import Gate, GateContext, GateOutcome, RetryPolicy, AttemptSummary, TransitionId, Attempt, ReplanHook` succeeds with no side effects (idempotent on second import: `id(mod_first) == id(mod_second)`).
- [ ] **AC-1a — `__all__` is the exact public surface:** `set(codegenie.gates.contract.__all__) == {"Attempt", "AttemptSummary", "Gate", "GateContext", "GateOutcome", "ReplanHook", "RetryPolicy", "TransitionId"}`. `SignalKind`, `AttemptNumber`, and `RunId` are NOT re-exported from this module (they live in `types/identifiers` and `sandbox/contract` respectively; re-exporting would dilute the single declaration site).

### B. `Gate` ABC shape (ADR-0006)

- [ ] **AC-2 — `Gate` is an ABC:** `issubclass(Gate, abc.ABC) is True`; `inspect.isabstract(Gate) is True`; `getattr(Gate.evaluate, "__isabstractmethod__", False) is True`.
- [ ] **AC-2a — Cannot instantiate directly:** `with pytest.raises(TypeError): Gate()` (the message contains "abstract method evaluate").
- [ ] **AC-2b — A subclass missing `evaluate` cannot instantiate:**
  ```python
  class Incomplete(Gate):
      gate_id = "x"; required_signals = (); retry_policy = RetryPolicy(...)
  with pytest.raises(TypeError): Incomplete()
  ```
- [ ] **AC-2c — A subclass providing `evaluate` instantiates and works** (positive path, see TDD plan).
- [ ] **AC-2d — Class attributes are declared on the ABC body** (no `__init__` ceremony required by subclasses): `Gate.gate_id`, `Gate.required_signals`, `Gate.retry_policy` exist as class attributes; the ABC carries no `__init__` that would force subclass constructor boilerplate. The ABC documents (via docstring on `evaluate`) "raises `GateMissingRequiredSignal` if a `required_signals` element is None on `os`" — the raise is in `StrictAndGate` (S4-05) but the contract documents it here.

### C. `TransitionId` enum

- [ ] **AC-3 — Enum subclasses `str`:** `issubclass(TransitionId, str)`; `issubclass(TransitionId, Enum)`.
- [ ] **AC-3a — Member set is exactly two values:** `set(TransitionId.__members__) == {"STAGE6_VALIDATE", "STAGE6_VALIDATE_LOOSE"}` (catches the mutation where a third member is silently added — Phase 6 LangGraph routing keys on this set).
- [ ] **AC-3b — Member values byte-exact:** `TransitionId.STAGE6_VALIDATE.value == "stage6_validate"` AND `TransitionId.STAGE6_VALIDATE_LOOSE.value == "stage6_validate_loose"`.
- [ ] **AC-3c — Unknown values rejected:** `with pytest.raises(ValueError): TransitionId("stage7_build")`.
- [ ] **AC-3d — JSON round-trip yields the value (str mixin), not the repr:** `TransitionId.STAGE6_VALIDATE == "stage6_validate"` (string equality holds because of the `str` mixin) — pinned as an assertion.

### D. Pydantic `model_config` discipline (all five Pydantic models)

- [ ] **AC-4 — `extra="forbid", frozen=True` asserted directly via `model_config` introspection on every model:** for `Cls in (RetryPolicy, AttemptSummary, GateContext, GateOutcome, Attempt)`, `Cls.model_config['extra'] == 'forbid'` AND `Cls.model_config['frozen'] is True`. Parametrized test.
- [ ] **AC-4a — Unknown-field rejection on every model:** for each of the five Pydantic models, constructing with a valid kwarg set plus `_bogus="x"` raises `pydantic.ValidationError`.
- [ ] **AC-4b — Mutation rejection on every model:** for each of the five models, constructing a valid instance and attempting `setattr(instance, <some-field>, <new-value>)` raises `pydantic.ValidationError`.

### E. `GateOutcome.state` Literal — positive AND negative byte-exact

- [ ] **AC-5 — Canonical state set byte-exact:** `typing.get_args(GateOutcome.model_fields["state"].annotation) == ("passed", "failed_retryable", "failed_unrecoverable", "escalate")` (positive pin — catches the mutation where an executor ships `Literal["pass", "fail_r", "fail_u", "esc"]` that passes the legacy negative case).
- [ ] **AC-5a — Each canonical state value constructs (parametrized positive path):** for `state in ("passed", "failed_retryable", "failed_unrecoverable", "escalate")`, `GateOutcome(passed=…, state=state, …)` constructs (with the cross-field invariants in §F honored).
- [ ] **AC-5b — Out-of-set state rejected:** `GateOutcome(state="weird_state", …)` raises `ValidationError`.

### F. `GateOutcome` cross-field invariants (illegal-states-unrepresentable)

A `@model_validator(mode="after")` on `GateOutcome` named `_check_state_invariants` enforces:

- [ ] **AC-CF-1 — `state == "passed"` implies `passed is True` and `failing_signals == []` and `retryable is False`:**
  - `GateOutcome(passed=True, state="passed", failing_signals=[], retryable=False, …)` constructs.
  - `GateOutcome(passed=True, state="passed", failing_signals=["tests"], …)` raises.
  - `GateOutcome(passed=False, state="passed", …)` raises.
- [ ] **AC-CF-2 — `state == "failed_retryable"` implies `passed is False` and `retryable is True`:**
  - `GateOutcome(passed=False, state="failed_retryable", retryable=True, failing_signals=["tests"], …)` constructs.
  - `GateOutcome(passed=True, state="failed_retryable", …)` raises.
  - `GateOutcome(passed=False, state="failed_retryable", retryable=False, …)` raises.
- [ ] **AC-CF-3 — `state == "failed_unrecoverable"` implies `passed is False` and `retryable is False`:** same parametrized pattern, positive + two negatives.
- [ ] **AC-CF-4 — `state == "escalate"` implies `passed is False` and `retryable is False`:** same.

### G. `GateContext` and `with_prior_attempt` (referential transparency)

- [ ] **AC-G-1 — Default empty `prior_attempts`:** `GateContext(…)` constructed without `prior_attempts` yields `ctx.prior_attempts == []`.
- [ ] **AC-G-2 — Signature is `with_prior_attempt(self, outcome: GateOutcome, sandbox_run_id: RunId) -> "GateContext"`:** `sandbox_run_id` is a required kwarg (per Validation note #5 — the arch's bare-`outcome` signature cannot derive `sandbox_run_id`). Asserted via `inspect.signature(GateContext.with_prior_attempt)`.
- [ ] **AC-G-3 — Returns a new frozen instance:** `new is not ctx`; `type(new) is GateContext`; `setattr(new, "advisory", "x")` raises.
- [ ] **AC-G-4 — Appends to the END (positional, not prepend):** after `new = ctx.with_prior_attempt(outcome, sandbox_run_id=RunId("run-1"))`, `new.prior_attempts[-1].attempt_id == outcome.attempt` AND `new.prior_attempts[-1].sandbox_run_id == "run-1"` AND `new.prior_attempts[-1].failing_signals == outcome.failing_signals` AND `new.prior_attempts[-1].prior_failure_summary == outcome.summary[:4096]`. (Catches the "prepend" mutation that the original draft AC ("length increases by 1") would have missed.)
- [ ] **AC-G-5 — Original untouched (immutability):** `ctx.prior_attempts == []` AFTER the call; `new.prior_attempts is not ctx.prior_attempts` (list-identity check — catches the mutation where the implementation mutates `self.prior_attempts.append(...)` and returns `self`).
- [ ] **AC-G-6 — Three sequential calls accumulate in order:** chaining `ctx2 = ctx.with_prior_attempt(o1, sandbox_run_id=RunId("r1"))`, `ctx3 = ctx2.with_prior_attempt(o2, sandbox_run_id=RunId("r2"))`, `ctx4 = ctx3.with_prior_attempt(o3, sandbox_run_id=RunId("r3"))` yields `[s1, s2, s3]` (in order, three distinct `sandbox_run_id`s, three distinct `attempt_id`s). Catches every "append at wrong position" mutation.

### H. `AttemptSummary` shape and caps

- [ ] **AC-H-1 — Fields and types:** `typing.get_type_hints(AttemptSummary)` returns exactly `{"attempt_id": AttemptNumber, "sandbox_run_id": RunId, "failing_signals": list[SignalKind], "prior_failure_summary": str, "evidence_paths": dict[str, Path]}`. (`AttemptNumber`/`RunId`/`SignalKind` are NewTypes — `is`-equality against the imports asserts no local redefinition; `evidence_paths` is `dict[str, Path]`, not `Mapping[str, Path]` or `dict[str, str]`.)
- [ ] **AC-H-2 — `prior_failure_summary` byte-cap at 4096 UTF-8 bytes:** the `field_validator` rejects `len(v.encode("utf-8")) > 4096` and accepts exactly 4096. Asserted with parametrized tests over (a) 4096 ASCII chars (accepted), (b) 4097 ASCII chars (rejected), (c) 2049 two-byte chars (4098 bytes — rejected), (d) 4094 ASCII + one 3-byte char (4097 bytes — rejected), (e) 4093 ASCII + one 3-byte char (4096 bytes — accepted).
- [ ] **AC-H-3 — `AttemptSummary.attempt_id` is `AttemptNumber`** and the Pydantic constraint `Annotated[int, Field(ge=1, le=1024)]` is applied: `AttemptSummary(attempt_id=0, …)` and `AttemptSummary(attempt_id=1025, …)` both raise. (Bound from `types/identifiers.py:102` "Bounded retry counter (1..1024)".)

### I. `RetryPolicy` shape + disjoint failure classifications

- [ ] **AC-I-1 — Fields and types:** `typing.get_type_hints(RetryPolicy)` returns `{"max_attempts": AttemptNumber, "retryable_failures": list[SignalKind], "non_retryable_failures": list[SignalKind], "timeout_retryable": bool}`. `max_attempts: Annotated[int, Field(ge=1, le=1024)]`.
- [ ] **AC-I-2 — `retryable_failures` and `non_retryable_failures` are disjoint:** a `@model_validator(mode="after")` named `_check_retry_classifications_disjoint` raises `ValidationError` when the intersection is non-empty. Positive: disjoint sets construct; negative: a signal in both lists is rejected.
- [ ] **AC-I-3 — `timeout_retryable` default is `False`** (arch line 728): `RetryPolicy(max_attempts=3, retryable_failures=[], non_retryable_failures=[]).timeout_retryable is False`.

### J. `Attempt` (internal — ledger row) cross-field invariants and hex shape

- [ ] **AC-J-1 — `prev_hash` and `chain_hash` are 32 LOWERCASE hex chars** (BLAKE3-128). `field_validator(mode="after")` accepts `"0"*32`, `"abcdef0123456789" * 2`; rejects `"A"*32` (uppercase), `"x"*32` (non-hex), `"0"*31` (short), `"0"*33` (long), `""`. Regex `^[0-9a-f]{32}$`.
- [ ] **AC-J-2 — `Attempt.ended_at >= Attempt.started_at`** (mirrors S1-02 AC-7c). `@model_validator(mode="after")` rejects reversed timestamps.
- [ ] **AC-J-3 — `attempt_id` is `AttemptNumber` (1..1024)** — same constraint as `AttemptSummary.attempt_id`.
- [ ] **AC-J-4 — `Attempt` is **exported but documented internal**:** docstring on `Attempt` reads `"Internal — one row written to attempts.jsonl. NOT part of the public surface."` (the `__all__` includes it because the ledger reads/writes it across modules — surface-cardinality vs documentation-intent).

### K. `ReplanHook` Protocol (Gap 2, ADR-0002 integration seam)

- [ ] **AC-K-1 — `@runtime_checkable` present directly** (mirrors S1-02 AC-2): `getattr(ReplanHook, "_is_runtime_protocol", False) is True`.
- [ ] **AC-K-2 — Protocol member set is exactly `{__call__}`:** `set(typing.get_protocol_members(ReplanHook)) == {"__call__"}` (catches a 3rd-method mutation).
- [ ] **AC-K-3 — Return type annotation references the existing `RecipeOutcome`, not the nonexistent `RecipeApplication`:** `ReplanHook.__call__.__annotations__["return"]` is the string `"RecipeOutcome"` (or evaluates to `codegenie.transforms.outcomes.RecipeOutcome` via `typing.get_type_hints` with the localns workaround documented in Notes). Import is inside `if TYPE_CHECKING:` to avoid a runtime cycle to `codegenie.transforms` per Refactor note.
- [ ] **AC-K-4 — `__call__` body is `...` (ADR-0006 "no shared default behavior"):** AST walk asserts `ast.Expr(ast.Constant(Ellipsis))` (mirrors S1-02 AC-2b).

### L. ADR-0014 transitive banned-substring scan (S1-03 inheritance)

- [ ] **AC-INH — Reuse S1-03's `iter_nested_field_names` walker:** `from codegenie.sandbox.signals._introspection import iter_nested_field_names` succeeds; for `Cls in (Attempt, GateOutcome, GateContext, AttemptSummary, RetryPolicy)`, the union of `iter_nested_field_names(Cls)` plus `Cls.model_fields.keys()` contains **no** name (case-insensitive) matching the banned substrings `("confidence", "llm", "self_reported", "model_says")`. New test file `tests/gates/test_contract_field_names_static.py`.

### M. `SignalKind` and `AttemptNumber` source-of-truth pinning

- [ ] **AC-S — `SignalKind` is IMPORTED, not redefined:** `gates.contract.SignalKind is codegenie.types.identifiers.SignalKind` (`is`, not `==` — guarantees the *same NewType object*); `typing.get_type_hints(AttemptSummary)["failing_signals"]` evaluates to `list[SignalKind]` with the imported NewType. AST source-scan on `src/codegenie/gates/contract.py` asserts no `NewType("SignalKind", …)` call anywhere in the file (mirrors S1-03 AC-4c chokepoint — this story is the next victim of that chokepoint if implemented carelessly).
- [ ] **AC-A — `AttemptNumber` is IMPORTED, not redefined:** same chokepoint; `gates.contract.AttemptNumber is codegenie.types.identifiers.AttemptNumber`; no `NewType("AttemptNumber", …)` under `src/codegenie/gates/`.
- [ ] **AC-R — `RunId` is IMPORTED from `codegenie.sandbox.contract`, not redefined:** `gates.contract.RunId is codegenie.sandbox.contract.RunId`; no `NewType("RunId", …)` under `src/codegenie/gates/`.

### N. Module purity + structural discipline (mirrors S1-02 AC-9 family)

- [ ] **AC-9 — `from __future__ import annotations` on line 1 of the docstring-prefaced module** — static check.
- [ ] **AC-9a — Module imports only stdlib + pydantic + sibling kernel modules:** `tests/gates/test_contract_purity.py` walks every `Import`/`ImportFrom` node and asserts membership in the closed set `{"abc", "enum", "typing", "collections", "collections.abc", "datetime", "pathlib", "re", "pydantic", "codegenie.errors", "codegenie.types.identifiers", "codegenie.sandbox.contract", "codegenie.sandbox.signals.models", "codegenie.transforms.outcomes"}` — the last entry only if NOT inside `if TYPE_CHECKING:` (a top-level runtime import of `codegenie.transforms.outcomes` would be a cycle and is forbidden). The TYPE_CHECKING-only import is permitted and exempted by the walker.
- [ ] **AC-9b — Module docstring cites ADR-0006, ADR-0002, ADR-0014, ADR-0008 by name** (substring match on the file source).

### O. Process gates (tooling + coverage)

- [ ] **AC-10 — TDD plan's red tests exist, are committed, and (after Green) are green.**
- [ ] **AC-11 — Tooling clean:** `ruff check src/codegenie/gates/contract.py`, `ruff format --check src/codegenie/gates/contract.py`, `mypy --strict src/codegenie/gates/contract.py`, `pytest tests/gates/test_contract_models.py tests/gates/test_gate_abc.py tests/gates/test_contract_field_names_static.py tests/gates/test_contract_purity.py` all pass.
- [ ] **AC-12 — Coverage on `src/codegenie/gates/contract.py`: line ≥ 95% AND branch ≥ 90%** (the 95/90 floor from [`stories/README.md §Definition of done`](README.md) — line 95, branch 90, NOT "≥ 95% branch" as the draft conflated).
- [ ] **AC-13 — Fence-test non-regression:** `tests/schema/test_no_llm_imports_in_sandbox.py` and any analogous fence under `tests/schema/` covering `gates/` (if present from S1-01/S1-07) remain green. `contract.py` imports no symbol from `anthropic`, `langgraph`, `chromadb`, or `sentence_transformers`.

## Implementation outline

1. Create `src/codegenie/gates/contract.py`. Module preamble:
   - `from __future__ import annotations` (AC-9).
   - Module docstring citing ADR-0006 (Protocol vs ABC), ADR-0002 (additive `prior_attempts` kwarg), ADR-0014 (`extra="forbid"` + static introspection), ADR-0008 (LLM Judge persona deferred) by name (AC-9b); quotes the "no I/O, no logger, no sibling Phase-5 modules" purity invariant (AC-9a, mirrors [`sandbox/contract.py`](../../../../src/codegenie/sandbox/contract.py) S1-02 precedent).
   - Imports (organized by section):
     - stdlib: `abc.{ABC, abstractmethod}`; `enum.Enum`; `typing.{Annotated, Protocol, TYPE_CHECKING, runtime_checkable}`; `typing.Literal`; `datetime.datetime`; `pathlib.Path`.
     - pydantic: `BaseModel, ConfigDict, Field, field_validator, model_validator`.
     - sibling kernel: `from codegenie.types.identifiers import AttemptNumber, SignalKind` (Validation note #1 + #8 + AC-S/A); `from codegenie.sandbox.contract import RunId` (Validation note + AC-R); `from codegenie.sandbox.signals.models import ObjectiveSignals`.
     - TYPE_CHECKING-only: `if TYPE_CHECKING: from codegenie.transforms.outcomes import RecipeOutcome` (AC-K-3 — forward-ref).
   - Declare `__all__` explicitly, alphabetized (AC-1a):
     ```python
     __all__ = [
         "Attempt", "AttemptSummary", "Gate", "GateContext",
         "GateOutcome", "ReplanHook", "RetryPolicy", "TransitionId",
     ]
     ```
     `SignalKind`, `AttemptNumber`, `RunId` are NOT re-exported (AC-1a — single declaration site).

2. **Do NOT redefine `SignalKind` / `AttemptNumber` / `RunId`** — they are imports. (Validation note #1, #8 + S1-03's AC-4c AST chokepoint enforces this.)

3. Define `TransitionId(str, Enum)` (AC-3 family):
   ```python
   class TransitionId(str, Enum):
       """Contract — stage transitions Phase 5 gates wrap. str-mixin so YAML/JSON
       round-trip yields the value, not <TransitionId.X: '...'>."""
       STAGE6_VALIDATE = "stage6_validate"
       STAGE6_VALIDATE_LOOSE = "stage6_validate_loose"
   ```

4. Define `RetryPolicy` (AC-I family):
   ```python
   class RetryPolicy(BaseModel):
       """Contract — per-gate retry config from YAML."""
       max_attempts: Annotated[int, Field(ge=1, le=1024)]
       retryable_failures: list[SignalKind]
       non_retryable_failures: list[SignalKind]
       timeout_retryable: bool = False

       model_config = ConfigDict(extra="forbid", frozen=True)

       @model_validator(mode="after")
       def _check_retry_classifications_disjoint(self) -> "RetryPolicy":
           overlap = set(self.retryable_failures) & set(self.non_retryable_failures)
           if overlap:
               raise ValueError(
                   f"signals classified as both retryable and non-retryable: {sorted(overlap)}"
               )
           return self
   ```

5. Define `AttemptSummary` (AC-H family):
   ```python
   class AttemptSummary(BaseModel):
       """Contract — structured retry context passed to Phase 4 (ADR-0002).
       NO raw log bytes — fence-wrapped, canary-checked summary only."""
       attempt_id: Annotated[int, Field(ge=1, le=1024)]   # AttemptNumber-typed at hint level
       sandbox_run_id: RunId
       failing_signals: list[SignalKind]
       prior_failure_summary: str           # ≤ 4096 UTF-8 bytes (validated)
       evidence_paths: dict[str, Path]

       model_config = ConfigDict(extra="forbid", frozen=True)

       @field_validator("prior_failure_summary", mode="after")
       @classmethod
       def _cap_summary_at_4kib(cls, v: str) -> str:
           if len(v.encode("utf-8")) > 4096:
               raise ValueError("prior_failure_summary exceeds 4096-byte (UTF-8) cap")
           return v
   ```
   Note: the `attempt_id` annotation in `model_fields` resolves to `int` at the Pydantic-shape level but `typing.get_type_hints(AttemptSummary)["attempt_id"]` returns `AttemptNumber` via the explicit annotation (Pydantic v2 preserves NewType in `__annotations__`). Document the precedence in Notes.

   **Type-hint resolution detail.** `Annotated[int, Field(...)]` is the Pydantic-validation shape; the *typing-level* identifier is `AttemptNumber`. To satisfy AC-H-1 / AC-H-3, the field is declared as `attempt_id: AttemptNumber` with the Pydantic constraints applied via a class-level `model_config = ConfigDict(json_schema_extra=...)` or per-field `@field_validator` checking `1 <= v <= 1024`. The simpler shape is to keep the field annotation as `AttemptNumber` (preserved by `get_type_hints`) and add the range validator via `@field_validator("attempt_id")`:
   ```python
   attempt_id: AttemptNumber

   @field_validator("attempt_id", mode="after")
   @classmethod
   def _check_attempt_id_range(cls, v: int) -> int:
       if not (1 <= v <= 1024):
           raise ValueError("attempt_id must satisfy 1 <= n <= 1024")
       return v
   ```
   This keeps `typing.get_type_hints(...)["attempt_id"] is AttemptNumber` (AC-H-1) AND enforces the bound (AC-H-3).

6. Define `GateOutcome` (AC-5 + AC-CF family):
   ```python
   class GateOutcome(BaseModel):
       """Contract — output of Gate.evaluate AND GateRunner.run."""
       passed: bool
       attempt: AttemptNumber                  # 1..1024 via field validator
       failing_signals: list[SignalKind]
       retryable: bool
       state: Literal["passed", "failed_retryable", "failed_unrecoverable", "escalate"]
       summary: str
       signals: ObjectiveSignals

       model_config = ConfigDict(extra="forbid", frozen=True)

       @model_validator(mode="after")
       def _check_state_invariants(self) -> "GateOutcome":
           if self.state == "passed":
               if not self.passed:
                   raise ValueError("state='passed' requires passed=True")
               if self.failing_signals:
                   raise ValueError("state='passed' requires empty failing_signals")
               if self.retryable:
                   raise ValueError("state='passed' requires retryable=False")
           elif self.state == "failed_retryable":
               if self.passed:
                   raise ValueError("state='failed_retryable' requires passed=False")
               if not self.retryable:
                   raise ValueError("state='failed_retryable' requires retryable=True")
           elif self.state == "failed_unrecoverable":
               if self.passed:
                   raise ValueError("state='failed_unrecoverable' requires passed=False")
               if self.retryable:
                   raise ValueError("state='failed_unrecoverable' requires retryable=False")
           elif self.state == "escalate":
               if self.passed:
                   raise ValueError("state='escalate' requires passed=False")
               if self.retryable:
                   raise ValueError("state='escalate' requires retryable=False")
           return self

       @field_validator("attempt", mode="after")
       @classmethod
       def _check_attempt_range(cls, v: int) -> int:
           if not (1 <= v <= 1024):
               raise ValueError("attempt must satisfy 1 <= n <= 1024")
           return v
   ```

7. Define `GateContext` (AC-G family):
   ```python
   class GateContext(BaseModel):
       """Contract — input to GateRunner.run."""
       worktree: Path
       advisory: str                            # forward-ref to Phase 3 Advisory (see Notes)
       recipe: str                              # forward-ref to Phase 3 Recipe (see Notes)
       transform_output: str                    # forward-ref to Phase 3 TransformOutput (see Notes)
       prior_attempts: list[AttemptSummary] = Field(default_factory=list)
       workflow_id: str                         # ULID; WorkflowId (Notes)
       run_id: str

       model_config = ConfigDict(extra="forbid", frozen=True)

       def with_prior_attempt(
           self, outcome: GateOutcome, *, sandbox_run_id: RunId
       ) -> "GateContext":
           """Return a new frozen GateContext with the AttemptSummary appended.
           sandbox_run_id is supplied by the caller (GateRunner has access to
           run.run_id at the callsite); see Validation note #5."""
           summary = AttemptSummary(
               attempt_id=outcome.attempt,
               sandbox_run_id=sandbox_run_id,
               failing_signals=list(outcome.failing_signals),
               prior_failure_summary=outcome.summary[:4096],
               evidence_paths={},  # populated by S5-02 GateRunner from sandbox.copy_out_root
           )
           return self.model_copy(update={"prior_attempts": [*self.prior_attempts, summary]})
   ```
   Forward-refs: `advisory: str`, `recipe: str`, `transform_output: str` use `str` placeholders until Phase 3 ships the typed models. Phase 3's existing types are `CveId` / `RecipeId` (`types/identifiers.py`); Phase 3 has no `Advisory` / `Recipe` / `TransformOutput` class shipped today. Surface in Notes; do not invent phantom types.

8. Define `Attempt` (internal — ledger row; AC-J family):
   ```python
   class Attempt(BaseModel):
       """Internal — one row written to attempts.jsonl. NOT part of the public surface
       (exported because the ledger reads/writes it; do not consume from non-ledger code)."""
       attempt_id: AttemptNumber
       sandbox_run_id: RunId
       signals: ObjectiveSignals
       outcome: GateOutcome
       started_at: datetime
       ended_at: datetime
       prev_hash: str                           # 32 lowercase hex (BLAKE3-128)
       chain_hash: str                          # 32 lowercase hex (BLAKE3-128)

       model_config = ConfigDict(extra="forbid", frozen=True)

       @field_validator("prev_hash", "chain_hash", mode="after")
       @classmethod
       def _check_blake3_128_lowercase_hex(cls, v: str) -> str:
           import re
           if not re.fullmatch(r"[0-9a-f]{32}", v):
               raise ValueError("must be 32 lowercase hex chars (BLAKE3-128)")
           return v

       @field_validator("attempt_id", mode="after")
       @classmethod
       def _check_attempt_id_range(cls, v: int) -> int:
           if not (1 <= v <= 1024):
               raise ValueError("attempt_id must satisfy 1 <= n <= 1024")
           return v

       @model_validator(mode="after")
       def _check_timestamps(self) -> "Attempt":
           if self.ended_at < self.started_at:
               raise ValueError("ended_at must be >= started_at")
           return self
   ```

9. Declare the `Gate` ABC (AC-2 family):
   ```python
   class Gate(ABC):
       """Strict-AND gate kernel. Subclasses share gate_id/required_signals/retry_policy
       defaults (ADR-0006 — ABC because shared default behavior is non-trivial)."""
       gate_id: str
       required_signals: tuple[SignalKind, ...]
       retry_policy: RetryPolicy

       @abstractmethod
       def evaluate(self, os: ObjectiveSignals, ctx: GateContext) -> GateOutcome:
           """Evaluate signals → outcome.

           Raises GateMissingRequiredSignal if any required_signals element is
           None on os; the raise lives in StrictAndGate (S4-05), documented here."""
           ...
   ```

10. Declare `ReplanHook` Protocol (AC-K family):
    ```python
    @runtime_checkable
    class ReplanHook(Protocol):
        """Closure-shaped callable wrapping FallbackTier.run (Gap 2 / ADR-0002).
        S5-01 supplies the integration contract test."""
        def __call__(self, ctx: GateContext) -> "RecipeOutcome": ...
    ```
    The return-type annotation is a string forward-ref to `codegenie.transforms.outcomes.RecipeOutcome` (the existing Phase-3 sum type; the draft's `RecipeApplication` is a phantom and does not exist). TYPE_CHECKING-only import at top of file avoids the runtime cycle.

11. Write the four test files: `tests/gates/test_contract_models.py`, `tests/gates/test_gate_abc.py`, `tests/gates/test_contract_field_names_static.py`, `tests/gates/test_contract_purity.py`.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file paths:
- `tests/gates/test_contract_models.py` — Pydantic config, literal byte-exact, cross-field invariants on `GateOutcome` and `RetryPolicy` and `Attempt`, `AttemptSummary` UTF-8 cap and field-shape, `with_prior_attempt` referential transparency + accumulation.
- `tests/gates/test_gate_abc.py` — ABC abstract method enforcement; `ReplanHook` Protocol shape (decorator, member set, body AST).
- `tests/gates/test_contract_field_names_static.py` — ADR-0014 inheritance scan (S1-03 walker reused).
- `tests/gates/test_contract_purity.py` — `from __future__`, import allowlist, module docstring cites ADRs.

```python
# tests/gates/test_contract_models.py
"""Model behavior — every Pydantic-side AC for S1-04 (hardened)."""
from __future__ import annotations

import inspect
import typing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from codegenie.gates import contract as contract_mod
from codegenie.gates.contract import (
    Attempt, AttemptSummary, Gate, GateContext, GateOutcome,
    ReplanHook, RetryPolicy, TransitionId,
)
from codegenie.sandbox.signals.models import ObjectiveSignals
from codegenie.sandbox.contract import RunId
from codegenie.types.identifiers import AttemptNumber, SignalKind
from codegenie.types import identifiers as ids_mod
from codegenie.sandbox import contract as sandbox_contract_mod


# ----------------- shared fixtures -----------------

_NOW = datetime(2026, 5, 22, 12, 0, 0, tzinfo=timezone.utc)


def _valid_summary(**ov):
    base = dict(
        attempt_id=AttemptNumber(1),
        sandbox_run_id=RunId("run-1"),
        failing_signals=[SignalKind("tests")],
        prior_failure_summary="failed: jwt.test.ts",
        evidence_paths={"stdout": Path("/tmp/o")},
    )
    base.update(ov)
    return AttemptSummary(**base)


def _valid_outcome(**ov):
    base = dict(
        passed=False, attempt=AttemptNumber(1),
        failing_signals=[SignalKind("tests")], retryable=True,
        state="failed_retryable",
        summary="tests failed", signals=ObjectiveSignals(),
    )
    base.update(ov)
    return GateOutcome(**base)


def _valid_ctx(**ov):
    base = dict(
        worktree=Path("/repo"), advisory="adv",
        recipe="rec", transform_output="to",
        workflow_id="01HZ" + "0" * 22, run_id="r-1",
    )
    base.update(ov)
    return GateContext(**base)


# =================================================================
# AC-1, AC-1a — import surface, __all__
# =================================================================

def test_all_is_exact_public_surface():
    assert set(contract_mod.__all__) == {
        "Attempt", "AttemptSummary", "Gate", "GateContext",
        "GateOutcome", "ReplanHook", "RetryPolicy", "TransitionId",
    }


def test_signal_kind_not_re_exported():
    """AC-1a — `SignalKind` lives in types.identifiers; not re-exported here."""
    assert "SignalKind" not in contract_mod.__all__
    assert "AttemptNumber" not in contract_mod.__all__
    assert "RunId" not in contract_mod.__all__


# =================================================================
# AC-S, AC-A, AC-R — SignalKind / AttemptNumber / RunId are IMPORTS
# =================================================================

def test_signal_kind_is_same_newtype_as_identifiers():
    """AC-S — `is`-equality against the canonical NewType in identifiers.py."""
    assert contract_mod.SignalKind is ids_mod.SignalKind


def test_attempt_number_is_same_newtype_as_identifiers():
    """AC-A."""
    assert contract_mod.AttemptNumber is ids_mod.AttemptNumber


def test_run_id_is_same_newtype_as_sandbox_contract():
    """AC-R."""
    assert contract_mod.RunId is sandbox_contract_mod.RunId


def test_no_newtype_redefinition_in_gates_contract_source():
    """AC-S / AC-A / AC-R — AST source-scan chokepoint (S1-03 AC-4c precedent)."""
    import ast
    src = Path(contract_mod.__file__).read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "NewType":
            assert node.args and isinstance(node.args[0], ast.Constant), \
                "expected NewType('Name', ...) — but the first arg isn't a string literal"
            name = node.args[0].value
            assert name not in {"SignalKind", "AttemptNumber", "RunId"}, (
                f"{name} must be imported, not redefined under gates/contract.py "
                "(S1-03 AC-4c chokepoint / Validation note #1)"
            )


# =================================================================
# AC-2 family — Gate ABC
# =================================================================

import abc

def test_gate_is_abstract_base_class():
    """AC-2."""
    assert issubclass(Gate, abc.ABC)
    assert inspect.isabstract(Gate) is True
    assert getattr(Gate.evaluate, "__isabstractmethod__", False) is True


def test_gate_cannot_be_instantiated_directly():
    """AC-2a."""
    with pytest.raises(TypeError):
        Gate()  # type: ignore[abstract]


def test_subclass_missing_evaluate_cannot_instantiate():
    """AC-2b."""
    class Incomplete(Gate):
        gate_id = "x"
        required_signals: tuple[SignalKind, ...] = ()
        retry_policy = RetryPolicy(
            max_attempts=AttemptNumber(3), retryable_failures=[], non_retryable_failures=[],
        )
    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]


def test_concrete_subclass_works():
    """AC-2c."""
    class Always(Gate):
        gate_id = "always"
        required_signals: tuple[SignalKind, ...] = ()
        retry_policy = RetryPolicy(
            max_attempts=AttemptNumber(3), retryable_failures=[], non_retryable_failures=[],
        )
        def evaluate(self, os, ctx):
            return GateOutcome(
                passed=True, attempt=AttemptNumber(1), failing_signals=[],
                retryable=False, state="passed", summary="ok", signals=os,
            )
    g = Always()
    out = g.evaluate(ObjectiveSignals(), _valid_ctx())
    assert out.passed is True and out.state == "passed"


# =================================================================
# AC-3 family — TransitionId
# =================================================================

def test_transition_id_subclasses_str_and_enum():
    """AC-3."""
    from enum import Enum
    assert issubclass(TransitionId, str)
    assert issubclass(TransitionId, Enum)


def test_transition_id_member_set_is_exact():
    """AC-3a — catches a 3rd member silently added."""
    assert set(TransitionId.__members__) == {"STAGE6_VALIDATE", "STAGE6_VALIDATE_LOOSE"}


def test_transition_id_values_byte_exact():
    """AC-3b."""
    assert TransitionId.STAGE6_VALIDATE.value == "stage6_validate"
    assert TransitionId.STAGE6_VALIDATE_LOOSE.value == "stage6_validate_loose"


def test_transition_id_rejects_unknown_value():
    """AC-3c."""
    with pytest.raises(ValueError):
        TransitionId("stage7_build")


def test_transition_id_str_mixin_equality():
    """AC-3d — JSON/YAML round-trip yields the value string, not <TransitionId.X>."""
    assert TransitionId.STAGE6_VALIDATE == "stage6_validate"


# =================================================================
# AC-4 family — model_config introspection, parametrized
# =================================================================

_PYDANTIC_MODELS = [RetryPolicy, AttemptSummary, GateContext, GateOutcome, Attempt]


@pytest.mark.parametrize("cls", _PYDANTIC_MODELS)
def test_each_model_is_frozen_and_extra_forbid(cls):
    """AC-4."""
    assert cls.model_config["extra"] == "forbid"
    assert cls.model_config["frozen"] is True


@pytest.mark.parametrize("cls,kwargs", [
    (RetryPolicy, dict(max_attempts=AttemptNumber(3), retryable_failures=[], non_retryable_failures=[])),
    # (AttemptSummary, GateContext, GateOutcome, Attempt populated via helpers below)
])
def test_retry_policy_rejects_unknown_field(cls, kwargs):
    """AC-4a (RetryPolicy slice; mirrored for the other 4 below)."""
    with pytest.raises(ValidationError):
        cls(**kwargs, _bogus="x")


def test_attempt_summary_rejects_unknown_field():
    with pytest.raises(ValidationError):
        _valid_summary(_bogus="x")


def test_gate_context_rejects_unknown_field():
    with pytest.raises(ValidationError):
        _valid_ctx(_bogus="x")


def test_gate_outcome_rejects_unknown_field():
    with pytest.raises(ValidationError):
        _valid_outcome(_bogus="x")


def test_attempt_rejects_unknown_field():
    with pytest.raises(ValidationError):
        Attempt(
            attempt_id=AttemptNumber(1), sandbox_run_id=RunId("r"),
            signals=ObjectiveSignals(),
            outcome=_valid_outcome(passed=True, state="passed", retryable=False, failing_signals=[]),
            started_at=_NOW, ended_at=_NOW,
            prev_hash="0" * 32, chain_hash="0" * 32,
            _bogus="x",
        )


@pytest.mark.parametrize("cls,instance_factory,field,new", [
    (RetryPolicy, lambda: RetryPolicy(
        max_attempts=AttemptNumber(3), retryable_failures=[], non_retryable_failures=[]
    ), "max_attempts", AttemptNumber(5)),
    (AttemptSummary, _valid_summary, "attempt_id", AttemptNumber(2)),
    (GateContext, _valid_ctx, "run_id", "r-2"),
    (GateOutcome, _valid_outcome, "summary", "mutated"),
])
def test_each_pydantic_model_is_frozen_at_runtime(cls, instance_factory, field, new):
    """AC-4b."""
    inst = instance_factory()
    with pytest.raises(ValidationError):
        setattr(inst, field, new)


# =================================================================
# AC-5 family — Literal byte-exact (positive + negative)
# =================================================================

def test_outcome_state_literal_set_byte_exact():
    """AC-5 — catches the mutation: an executor shipping shorter aliases passes
    every legacy negative test."""
    args = typing.get_args(GateOutcome.model_fields["state"].annotation)
    assert args == ("passed", "failed_retryable", "failed_unrecoverable", "escalate")


@pytest.mark.parametrize("state,passed,retryable,failing", [
    ("passed",                True,  False, []),
    ("failed_retryable",      False, True,  [SignalKind("tests")]),
    ("failed_unrecoverable",  False, False, [SignalKind("tests")]),
    ("escalate",              False, False, [SignalKind("trace")]),
])
def test_outcome_constructs_for_each_canonical_state(state, passed, retryable, failing):
    """AC-5a — positive construction across the full state set."""
    GateOutcome(
        passed=passed, attempt=AttemptNumber(1), failing_signals=failing,
        retryable=retryable, state=state, summary="x", signals=ObjectiveSignals(),
    )


def test_outcome_rejects_out_of_set_state():
    """AC-5b."""
    with pytest.raises(ValidationError):
        _valid_outcome(state="weird_state")


# =================================================================
# AC-CF family — GateOutcome cross-field invariants
# =================================================================

# AC-CF-1: state == "passed"
def test_passed_state_requires_passed_true_and_no_failing_signals_and_no_retryable():
    GateOutcome(passed=True, attempt=AttemptNumber(1), failing_signals=[],
                retryable=False, state="passed", summary="ok", signals=ObjectiveSignals())

    with pytest.raises(ValidationError):
        GateOutcome(passed=True, attempt=AttemptNumber(1),
                    failing_signals=[SignalKind("tests")], retryable=False,
                    state="passed", summary="ok", signals=ObjectiveSignals())

    with pytest.raises(ValidationError):
        GateOutcome(passed=False, attempt=AttemptNumber(1), failing_signals=[],
                    retryable=False, state="passed", summary="x", signals=ObjectiveSignals())

    with pytest.raises(ValidationError):
        GateOutcome(passed=True, attempt=AttemptNumber(1), failing_signals=[],
                    retryable=True, state="passed", summary="x", signals=ObjectiveSignals())


# AC-CF-2: state == "failed_retryable"
def test_failed_retryable_invariants():
    GateOutcome(passed=False, attempt=AttemptNumber(1),
                failing_signals=[SignalKind("tests")], retryable=True,
                state="failed_retryable", summary="x", signals=ObjectiveSignals())

    with pytest.raises(ValidationError):  # passed=True
        GateOutcome(passed=True, attempt=AttemptNumber(1), failing_signals=[],
                    retryable=True, state="failed_retryable",
                    summary="x", signals=ObjectiveSignals())

    with pytest.raises(ValidationError):  # retryable=False
        GateOutcome(passed=False, attempt=AttemptNumber(1),
                    failing_signals=[SignalKind("tests")], retryable=False,
                    state="failed_retryable", summary="x", signals=ObjectiveSignals())


# AC-CF-3: state == "failed_unrecoverable"
def test_failed_unrecoverable_invariants():
    GateOutcome(passed=False, attempt=AttemptNumber(3),
                failing_signals=[SignalKind("tests")], retryable=False,
                state="failed_unrecoverable", summary="stuck", signals=ObjectiveSignals())

    with pytest.raises(ValidationError):
        GateOutcome(passed=True, attempt=AttemptNumber(3), failing_signals=[],
                    retryable=False, state="failed_unrecoverable",
                    summary="x", signals=ObjectiveSignals())

    with pytest.raises(ValidationError):
        GateOutcome(passed=False, attempt=AttemptNumber(3),
                    failing_signals=[SignalKind("tests")], retryable=True,
                    state="failed_unrecoverable", summary="x", signals=ObjectiveSignals())


# AC-CF-4: state == "escalate"
def test_escalate_invariants():
    GateOutcome(passed=False, attempt=AttemptNumber(1),
                failing_signals=[SignalKind("trace")], retryable=False,
                state="escalate", summary="non-retry", signals=ObjectiveSignals())

    with pytest.raises(ValidationError):
        GateOutcome(passed=True, attempt=AttemptNumber(1), failing_signals=[],
                    retryable=False, state="escalate",
                    summary="x", signals=ObjectiveSignals())

    with pytest.raises(ValidationError):
        GateOutcome(passed=False, attempt=AttemptNumber(1),
                    failing_signals=[SignalKind("trace")], retryable=True,
                    state="escalate", summary="x", signals=ObjectiveSignals())


# =================================================================
# AC-G family — GateContext.with_prior_attempt
# =================================================================

def test_gate_context_prior_attempts_defaults_empty():
    """AC-G-1."""
    assert _valid_ctx().prior_attempts == []


def test_with_prior_attempt_signature_requires_sandbox_run_id_kwarg():
    """AC-G-2."""
    sig = inspect.signature(GateContext.with_prior_attempt)
    params = sig.parameters
    assert "outcome" in params
    assert "sandbox_run_id" in params
    assert params["sandbox_run_id"].kind == inspect.Parameter.KEYWORD_ONLY


def test_with_prior_attempt_returns_new_frozen_instance():
    """AC-G-3."""
    ctx = _valid_ctx()
    outcome = _valid_outcome()
    new = ctx.with_prior_attempt(outcome, sandbox_run_id=RunId("run-1"))
    assert new is not ctx
    assert type(new) is GateContext
    with pytest.raises(ValidationError):
        setattr(new, "advisory", "mutated")


def test_with_prior_attempt_appends_to_end():
    """AC-G-4 — catches the prepend mutation."""
    ctx = _valid_ctx()
    outcome = _valid_outcome(attempt=AttemptNumber(7),
                              failing_signals=[SignalKind("policy")],
                              summary="policy violation")
    new = ctx.with_prior_attempt(outcome, sandbox_run_id=RunId("run-1"))
    appended = new.prior_attempts[-1]
    assert appended.attempt_id == 7
    assert appended.sandbox_run_id == "run-1"
    assert appended.failing_signals == ["policy"]
    assert appended.prior_failure_summary == "policy violation"


def test_with_prior_attempt_does_not_mutate_original():
    """AC-G-5."""
    ctx = _valid_ctx()
    new = ctx.with_prior_attempt(_valid_outcome(), sandbox_run_id=RunId("r1"))
    assert ctx.prior_attempts == []
    assert new.prior_attempts is not ctx.prior_attempts


def test_with_prior_attempt_three_call_accumulation():
    """AC-G-6 — catches multi-call accumulation bugs."""
    ctx = _valid_ctx()
    o1 = _valid_outcome(attempt=AttemptNumber(1))
    o2 = _valid_outcome(attempt=AttemptNumber(2))
    o3 = _valid_outcome(attempt=AttemptNumber(3))
    ctx2 = ctx.with_prior_attempt(o1, sandbox_run_id=RunId("r1"))
    ctx3 = ctx2.with_prior_attempt(o2, sandbox_run_id=RunId("r2"))
    ctx4 = ctx3.with_prior_attempt(o3, sandbox_run_id=RunId("r3"))
    assert [a.attempt_id for a in ctx4.prior_attempts] == [1, 2, 3]
    assert [a.sandbox_run_id for a in ctx4.prior_attempts] == ["r1", "r2", "r3"]
    # original untouched
    assert ctx.prior_attempts == []
    assert ctx2.prior_attempts == [ctx2.prior_attempts[0]]  # length 1
    assert len(ctx3.prior_attempts) == 2


# =================================================================
# AC-H family — AttemptSummary
# =================================================================

def test_attempt_summary_type_hints_exact():
    """AC-H-1."""
    hints = typing.get_type_hints(AttemptSummary)
    assert hints["attempt_id"] is AttemptNumber
    assert hints["sandbox_run_id"] is RunId
    assert hints["failing_signals"] == list[SignalKind]
    assert hints["prior_failure_summary"] is str
    assert hints["evidence_paths"] == dict[str, Path]


def test_attempt_summary_caps_prior_failure_summary_at_4096_bytes_ascii():
    """AC-H-2 (a)."""
    with pytest.raises(ValidationError):
        _valid_summary(prior_failure_summary="x" * 4097)


def test_attempt_summary_accepts_exactly_4096_bytes_ascii():
    """AC-H-2 (a)."""
    s = _valid_summary(prior_failure_summary="x" * 4096)
    assert len(s.prior_failure_summary.encode("utf-8")) == 4096


def test_attempt_summary_rejects_multibyte_over_4096_bytes():
    """AC-H-2 (c) — 2049 two-byte chars = 4098 bytes."""
    with pytest.raises(ValidationError):
        _valid_summary(prior_failure_summary="é" * 2049)


def test_attempt_summary_accepts_multibyte_at_boundary():
    """AC-H-2 (e) — 4093 ASCII + one 3-byte char = 4096 bytes."""
    s = _valid_summary(prior_failure_summary="a" * 4093 + "€")
    assert len(s.prior_failure_summary.encode("utf-8")) == 4096


@pytest.mark.parametrize("bad", [0, -1, 1025, 9999])
def test_attempt_summary_attempt_id_range(bad):
    """AC-H-3."""
    with pytest.raises(ValidationError):
        _valid_summary(attempt_id=bad)


# =================================================================
# AC-I family — RetryPolicy
# =================================================================

def test_retry_policy_type_hints_exact():
    """AC-I-1."""
    hints = typing.get_type_hints(RetryPolicy)
    assert hints["max_attempts"] is AttemptNumber
    assert hints["retryable_failures"] == list[SignalKind]
    assert hints["non_retryable_failures"] == list[SignalKind]
    assert hints["timeout_retryable"] is bool


def test_retry_policy_classifications_must_be_disjoint():
    """AC-I-2."""
    with pytest.raises(ValidationError):
        RetryPolicy(
            max_attempts=AttemptNumber(3),
            retryable_failures=[SignalKind("tests")],
            non_retryable_failures=[SignalKind("tests")],  # overlap
        )


def test_retry_policy_timeout_retryable_default():
    """AC-I-3."""
    p = RetryPolicy(max_attempts=AttemptNumber(3), retryable_failures=[], non_retryable_failures=[])
    assert p.timeout_retryable is False


# =================================================================
# AC-J family — Attempt
# =================================================================

def _valid_attempt(**ov):
    base = dict(
        attempt_id=AttemptNumber(1), sandbox_run_id=RunId("r1"),
        signals=ObjectiveSignals(),
        outcome=GateOutcome(
            passed=True, attempt=AttemptNumber(1), failing_signals=[],
            retryable=False, state="passed", summary="ok", signals=ObjectiveSignals(),
        ),
        started_at=_NOW, ended_at=_NOW + timedelta(seconds=1),
        prev_hash="0" * 32, chain_hash="0" * 32,
    )
    base.update(ov)
    return Attempt(**base)


@pytest.mark.parametrize("bad", [
    "A" * 32,            # uppercase rejected
    "g" * 32,            # non-hex rejected
    "0" * 31,            # too short
    "0" * 33,            # too long
    "",                  # empty
    "0123456789abcdef" + "0123456789ABCDEF",  # mixed case
])
def test_attempt_rejects_non_lowercase_hex_for_chain_hashes(bad):
    """AC-J-1."""
    with pytest.raises(ValidationError):
        _valid_attempt(prev_hash=bad)
    with pytest.raises(ValidationError):
        _valid_attempt(chain_hash=bad)


def test_attempt_accepts_canonical_lowercase_hex():
    """AC-J-1 positive."""
    _valid_attempt(prev_hash="abcdef0123456789" * 2, chain_hash="0" * 32)


def test_attempt_rejects_ended_before_started():
    """AC-J-2."""
    with pytest.raises(ValidationError):
        _valid_attempt(started_at=_NOW, ended_at=_NOW - timedelta(seconds=1))


def test_attempt_accepts_ended_equal_started():
    """AC-J-2 boundary."""
    _valid_attempt(started_at=_NOW, ended_at=_NOW)


@pytest.mark.parametrize("bad", [0, -1, 1025])
def test_attempt_rejects_out_of_range_attempt_id(bad):
    """AC-J-3."""
    with pytest.raises(ValidationError):
        _valid_attempt(attempt_id=bad)
```

```python
# tests/gates/test_gate_abc.py
"""Gate ABC + ReplanHook Protocol shape ACs."""
from __future__ import annotations

import ast
import typing
from pathlib import Path

from codegenie.gates import contract as contract_mod
from codegenie.gates.contract import (
    Gate, GateContext, GateOutcome, ReplanHook, RetryPolicy,
)
from codegenie.sandbox.signals.models import ObjectiveSignals
from codegenie.types.identifiers import AttemptNumber


# ----------------- AC-K family — ReplanHook Protocol -----------------

def test_replan_hook_is_runtime_checkable():
    """AC-K-1."""
    assert getattr(ReplanHook, "_is_runtime_protocol", False) is True


def test_replan_hook_member_set_is_only_call():
    """AC-K-2 — catches 3rd-method mutation."""
    members = set(typing.get_protocol_members(ReplanHook))
    assert members == {"__call__"}


def test_replan_hook_return_annotation_references_recipe_outcome():
    """AC-K-3 — string forward-ref to existing Phase-3 RecipeOutcome (not phantom)."""
    ret = ReplanHook.__call__.__annotations__["return"]
    assert ret == "RecipeOutcome" or ret == "'RecipeOutcome'", (
        f"expected string forward-ref to RecipeOutcome, got {ret!r}"
    )


def test_replan_hook_call_body_is_ellipsis_only():
    """AC-K-4 — AST walk; ADR-0006 'no shared default behavior'."""
    src = Path(contract_mod.__file__).read_text()
    tree = ast.parse(src)
    cls = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "ReplanHook"
    )
    fn_defs = [n for n in cls.body if isinstance(n, ast.FunctionDef)]
    assert {fn.name for fn in fn_defs} == {"__call__"}
    body = fn_defs[0].body
    assert len(body) == 1
    stmt = body[0]
    assert isinstance(stmt, ast.Expr)
    assert isinstance(stmt.value, ast.Constant)
    assert stmt.value.value is Ellipsis


# ----------------- AC-2d — Gate ABC class attributes -----------------

def test_gate_documents_required_signal_raise_in_docstring():
    """AC-2d documentation requirement."""
    doc = Gate.evaluate.__doc__ or ""
    assert "GateMissingRequiredSignal" in doc, (
        "Gate.evaluate's docstring must document the raise (contract documented "
        "here even though the actual raise lives in StrictAndGate / S4-05)."
    )
```

```python
# tests/gates/test_contract_field_names_static.py
"""AC-INH — ADR-0014 banned-substring scan extended to gates/contract.py models."""
from __future__ import annotations

from codegenie.gates.contract import (
    Attempt, AttemptSummary, GateContext, GateOutcome, RetryPolicy,
)
from codegenie.sandbox.signals._introspection import iter_nested_field_names

_BANNED = ("confidence", "llm", "self_reported", "model_says")


def test_no_banned_substring_in_any_contract_field_name():
    """AC-INH — reuse the S1-03 walker; gates/contract.py models inherit the invariant."""
    for cls in (Attempt, AttemptSummary, GateContext, GateOutcome, RetryPolicy):
        names = set(iter_nested_field_names(cls)) | set(cls.model_fields.keys())
        for n in names:
            low = n.lower()
            for banned in _BANNED:
                assert banned not in low, (
                    f"{cls.__name__}.<...>{n!r} contains banned substring {banned!r} "
                    "(ADR-0014; LLM self-assessment must not enter trust-graph field names)"
                )
```

```python
# tests/gates/test_contract_purity.py
"""AC-9 / AC-9a / AC-9b — module-purity invariant; mirrors S1-02 precedent."""
from __future__ import annotations

import ast
from pathlib import Path

from codegenie.gates import contract as contract_mod


_ALLOWED_TOPLEVEL_IMPORTS = {
    "abc", "enum", "typing",
    "collections", "collections.abc",
    "datetime", "pathlib", "re",
    "pydantic",
    "codegenie.errors",
    "codegenie.types.identifiers",
    "codegenie.sandbox.contract",
    "codegenie.sandbox.signals.models",
}

# TYPE_CHECKING-only imports are permitted but must not be runtime.
_TYPE_CHECKING_ONLY_ALLOWED = {
    "codegenie.transforms.outcomes",
}


def _runtime_imports(tree: ast.AST) -> set[str]:
    """Walk top-level imports; exclude anything under `if TYPE_CHECKING:` branches."""
    out: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.If):
            test = node.test
            is_tc = (
                (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or
                (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")
            )
            if is_tc:
                continue
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.add(node.module)
    return out


def test_contract_has_future_annotations():
    """AC-9."""
    src = Path(contract_mod.__file__).read_text()
    assert "from __future__ import annotations" in src.splitlines()[:25]


def test_contract_runtime_imports_are_allowlisted():
    """AC-9a."""
    src = Path(contract_mod.__file__).read_text()
    tree = ast.parse(src)
    runtime = _runtime_imports(tree)
    extras = runtime - _ALLOWED_TOPLEVEL_IMPORTS
    assert not extras, (
        f"gates/contract.py imports disallowed modules at runtime: {sorted(extras)}.\n"
        f"Allowed: {sorted(_ALLOWED_TOPLEVEL_IMPORTS)}\n"
        f"TYPE_CHECKING-only allowed: {sorted(_TYPE_CHECKING_ONLY_ALLOWED)}"
    )


def test_contract_module_docstring_cites_all_four_adrs():
    """AC-9b."""
    doc = contract_mod.__doc__ or ""
    for adr in ("ADR-0006", "ADR-0002", "ADR-0014", "ADR-0008"):
        assert adr in doc, f"module docstring must cite {adr}"
```

Run the four test files; confirm `ImportError` on every contract symbol; commit the red tests; then implement.

### Green — make it pass

Implement `contract.py` per the Implementation outline. Notes for the Green pass:

- **Import discipline (Validation note #1).** `SignalKind`, `AttemptNumber` come from `codegenie.types.identifiers`. `RunId` comes from `codegenie.sandbox.contract` (S1-02 shipped it there). Never write `NewType("SignalKind", str)` (or `RunId` / `AttemptNumber`) under `src/codegenie/gates/` — S1-03's AC-4c AST chokepoint AND this story's AC-S/AC-A/AC-R will fail it.
- **`with_prior_attempt` signature** is `(self, outcome: GateOutcome, *, sandbox_run_id: RunId) -> "GateContext"`. The keyword-only `sandbox_run_id` mirrors how `GateRunner` calls it at the seam (S5-02). Per the Validation note resolution: the arch's bare-`outcome` signature cannot derive `sandbox_run_id` because neither `GateOutcome` nor `SignalProvenance` carries it.
- **Cross-field validators** raise `ValueError(<specific message>)`; Pydantic wraps it into `ValidationError` for tests. Method names: `_check_state_invariants` (GateOutcome), `_check_retry_classifications_disjoint` (RetryPolicy), `_check_timestamps` (Attempt). Leading underscore = internal.
- **`AttemptNumber` at the typing level and `Field(ge=1, le=1024)` at the validation level.** Annotation is `attempt_id: AttemptNumber`; range enforcement is via `@field_validator("attempt_id")`. Don't try `Annotated[AttemptNumber, Field(...)]` — Pydantic may or may not preserve the NewType through the annotation tree depending on version; explicit validator keeps `typing.get_type_hints(...)["attempt_id"] is AttemptNumber` (AC-H-1).
- **`prior_failure_summary` byte-cap.** Reject `len(v.encode("utf-8")) > 4096`. Arch §Harness engineering frames this as a 4 KiB cap; ASCII assumption was wrong (multi-byte content exceeds the cap silently).
- **`ReplanHook.__call__` return** is the string `"RecipeOutcome"`. The actual import is inside `if TYPE_CHECKING:` to avoid the runtime cycle `gates → transforms → ...`. Phase 3 already ships `codegenie.transforms.outcomes.RecipeOutcome` as the sum type `Applied | Skipped | NotApplicable | Failed`.
- **`Gate.evaluate` docstring** must mention `GateMissingRequiredSignal` (AC-2d test asserts substring match). The actual `raise` is in `StrictAndGate.evaluate` (S4-05) — this story documents the contract.

### Refactor — clean up

- ADR-0014 inheritance (AC-INH): the S1-03 walker `iter_nested_field_names` is imported in the test; no new infrastructure needed here. If S1-03 has not yet landed when this story executes, the test marks `xfail` with the dependency-name; otherwise it runs.
- Sanity-check that no `Attempt` or `GateOutcome` field name contains a banned substring (`confidence`/`llm`/`self_reported`/`model_says`). Names currently chosen — `attempt_id`, `sandbox_run_id`, `failing_signals`, `prior_failure_summary`, `evidence_paths`, `retry_policy`, `gate_id`, `required_signals`, `state`, `signals`, `prev_hash`, `chain_hash`, `started_at`, `ended_at`, `max_attempts`, `retryable_failures`, `non_retryable_failures`, `timeout_retryable`, `worktree`, `advisory`, `recipe`, `transform_output`, `workflow_id`, `run_id`, `prior_attempts`, `outcome`, `passed`, `attempt`, `retryable`, `summary` — all clean. The CI test still runs as defense-in-depth.
- `ReplanHook` Protocol with the TYPE_CHECKING'd return type: re-read at the end to confirm `mypy --strict` is clean. Pydantic does not validate Protocol shapes; `runtime_checkable` is only for `isinstance()` checks.
- `GateContext` forward-refs (`advisory: str`, `recipe: str`, `transform_output: str`): when Phase 3 ships `Advisory`/`Recipe`/`TransformOutput` Pydantic models or NewTypes, this is an ADR-amendment + widening story for a future executor. For now, `str` is the honest placeholder. Note in the docstring.
- Confirm `__all__` is alphabetized; mirrors S1-02.
- Coverage check on every cross-field branch + every validator's ValueError path.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/gates/contract.py` | New file — Gate ABC + five frozen Pydantic models + TransitionId + ReplanHook per ADR-0006/0002/0014/0008; imports `SignalKind`/`AttemptNumber`/`RunId` (no redefinition) |
| `tests/gates/test_contract_models.py` | New test — `model_config` introspection, literal byte-exact (positive + negative), cross-field invariants on `GateOutcome`/`RetryPolicy`/`Attempt`, `AttemptSummary` UTF-8 cap and field-shape, `with_prior_attempt` referential transparency + accumulation |
| `tests/gates/test_gate_abc.py` | New test — ABC abstract-method enforcement + `ReplanHook` Protocol shape (decorator, member set, AST body, return-annotation forward-ref) |
| `tests/gates/test_contract_field_names_static.py` | New test — AC-INH; reuses S1-03's `iter_nested_field_names` walker; ADR-0014 transitive banned-substring scan across all 5 gates models |
| `tests/gates/test_contract_purity.py` | New test — `from __future__ import annotations`, import allowlist (TYPE_CHECKING-aware), module docstring cites the 4 ADRs |

## Out of scope

- **`StrictAndGate` implementation** — S4-05. This story documents `Gate.evaluate`'s `GateMissingRequiredSignal` raise in the docstring but does not raise it.
- **`GateRunner.run` retry loop** — S5-02. This story ships the `with_prior_attempt` referential-transparency contract; the loop that calls it is S5-02's.
- **`@register_signal_kind`** — S1-05. This story uses `SignalKind` (imported) but does not own the registry.
- **`ReplanHook` integration / VCR contract test** — S5-01. This story ships the Protocol shape; the integration test that invokes a concrete hook is S5-01's.
- **`FenceWrapper.compose_prior_attempts`** — S5-03 (Phase 4 prompt builder consumes `prior_failure_summary`).
- **YAML catalog loader** — S1-06.
- **`AttemptSummary.evidence_paths` population logic** — S5-02 GateRunner pulls evidence file paths from `SandboxRun.copy_out_root` after each attempt; this story declares the shape but constructs empty `{}` inside `with_prior_attempt`.
- **`Advisory`/`Recipe`/`TransformOutput` typed models** — Phase 3 has not shipped these as typed classes; current annotation is `str` placeholder. Widening is a future story when Phase 3 lands the types.
- **Promoting `RunId` to `types/identifiers.py`** — S1-02 declared `RunId` in `sandbox/contract.py`. This story imports it from there. A future cleanup story may promote it (mirroring S1-03's `SignalKind` move); not in S1-04's scope.

## Notes for the implementer

### Imports vs redefinition (the load-bearing discipline)

- **`SignalKind` lives in [`src/codegenie/types/identifiers.py:96`](../../../../src/codegenie/types/identifiers.py:96).** Import it. Don't redefine it. S1-03's AC-4c is an AST chokepoint test under `src/codegenie/gates/` (and `src/codegenie/sandbox/`) that **will fail your PR** if you write `NewType("SignalKind", str)` in this file. Validation note #1 is the trace: the arch's pseudo-code line 721 `SignalKind = str` was a placeholder S1-03 already replaced.
- **`AttemptNumber` lives at [`types/identifiers.py:102`](../../../../src/codegenie/types/identifiers.py:102).** The docstring there literally says `"Bounded retry counter (1..1024); S1-04 AttemptSummary.attempt."` — the identifier was created for *this story*. Use it on `AttemptSummary.attempt_id`, `Attempt.attempt_id`, `GateOutcome.attempt`, `RetryPolicy.max_attempts`. Range enforcement (1..1024) goes via `@field_validator` (not `Annotated[AttemptNumber, Field(...)]`) so `typing.get_type_hints` preserves the NewType.
- **`RunId` lives at [`src/codegenie/sandbox/contract.py`](../../../../src/codegenie/sandbox/contract.py) (S1-02).** Import from there. A future cleanup story may promote it to `types/identifiers.py`; not your problem today.

### Cross-field invariants — illegal states unrepresentable

Pydantic `@model_validator(mode="after")` is the right tool. Each invariant raises `ValueError(<specific message>)`; Pydantic wraps it into `ValidationError`. The invariants this story enforces:

- **`GateOutcome` four-state cross-field invariant** (Validation note #3). One validator, four branches; each branch checks the three companions (`passed`, `retryable`, `failing_signals`). Without this, Phase 6's LangGraph reducer inherits illegal states; Phase 11's reviewer trusts a `state="passed"` outcome that has `failing_signals != []`.
- **`RetryPolicy` disjoint failure classifications** (Validation note #11). A signal in both `retryable_failures` and `non_retryable_failures` is undefined dispatch for `StrictAndGate.evaluate` (S4-05).
- **`Attempt.ended_at >= Attempt.started_at`** (Validation note #12). Mirrors S1-02 AC-7c.

The alternative — pushing these into `GateRunner`/`StrictAndGate` — would let callers construct nonsense intermediaries. The arch says the contract is what Phase 6 lifts unchanged; if the contract permits illegal states, every downstream consumer inherits them.

### `with_prior_attempt` signature (resolved ambiguity)

The arch line 749 sketch — `with_prior_attempt(self, outcome: GateOutcome) -> "GateContext"` — is unrealizable: `AttemptSummary.sandbox_run_id` cannot be derived from `outcome` alone (neither `GateOutcome` nor `SignalProvenance` carry it). Per Validation note #5, the signature widens to `(self, outcome: GateOutcome, *, sandbox_run_id: RunId)`. `GateRunner` (S5-02 step 6 of the loop) already has `run.run_id` at the callsite. This is the cleanest cut: the contract is honest, the runner threads the value once.

### Forward-seam notes — what *doesn't* go in `contract.py`

- **`GateOutcome.state: Literal["passed", "failed_retryable", "failed_unrecoverable", "escalate"]` is a closed Literal today.** That's intentional: Phase 6 LangGraph's `Command(goto=...) / interrupt()` mapping (arch §Integration with Phase 6) keys on these exact strings. Adding a 5th state requires an ADR amendment AND a paired Phase 6 reducer change. Do **not** silently widen to `str`. Mirrors S1-02's "closed Literal of an open registry" forward-seam.
- **`Advisory`/`Recipe`/`TransformOutput`** are typed as `str` placeholders. Phase 3 has not shipped them as classes (`grep -rn "class Advisory" src/` returns nothing). When Phase 3 lands the typed models, widening these annotations is a future-story ADR amendment.
- **`AttemptSummary.evidence_paths` is `dict[str, Path]`**, not `Mapping[str, Path]`. S1-02 used `Mapping` for read-only intent on `SandboxSpec.env`; here, `GateRunner` populates the dict after constructing the summary — a writable shape is the honest one.

### NewType discipline (CLAUDE.md "≥ 2 module boundaries")

| Identifier | Source | Why a NewType |
|---|---|---|
| `SignalKind` | `types/identifiers.py:96` | Crosses `signals/models.py` (S1-03), `gates/contract.py` (here), `gates/strict_and.py` (S4-05), `signals/registry.py` (S1-05), `gates/runner.py` (S5-02), `attempts.jsonl` Phase 11 |
| `AttemptNumber` | `types/identifiers.py:102` | Crosses `gates/contract.py` (here), `gates/runner.py` (S5-02), `gates/retry_ledger.py` (S2-01), `attempts.jsonl` (Phase 11 reviewer) |
| `RunId` | `sandbox/contract.py` (S1-02) | Crosses sandbox/contract (S1-02), gates/contract (here), gates/retry_ledger (S2-01), gates/runner (S5-02), cost/sandbox.jsonl (S7-03), CLI inspect (S8-01) |

Other `str`-shaped fields (`gate_id`, `summary`, `workflow_id`, `run_id` on `GateContext`, `advisory`/`recipe`/`transform_output` Phase-3 placeholders) do NOT get newtypes today — Rule 2 caps premature abstraction. If a future story consumes one as a typed surface, the NewType goes there.

### Pydantic v2 idioms

- **Always** `model_config = ConfigDict(extra="forbid", frozen=True)`. Never the v1 `class Config` style — the project is Python 3.11+ and Pydantic 2.
- **`@model_validator(mode="after")`** raises `ValueError`; Pydantic wraps it. Method name `_check_<invariant>` (leading underscore — internal). Returns `self`.
- **`@field_validator("foo", "bar", mode="after")`** for shared validation across multiple fields (used for `prev_hash` + `chain_hash`).
- **`Field(default_factory=list)`** for `prior_attempts` — never `default=[]` (Python's classic shared-mutable-default trap; Pydantic 2 catches it but `default_factory` is the canonical form).
- **NewType is a type-checker shim.** `RunId("r1")` returns the bare string at runtime; the NewType wrapper is for `mypy --strict` only. Tests use the constructor form as intent documentation.

### Coverage floor

This module sits on the **95% line / 90% branch** floor per [`stories/README.md §Definition of done`](README.md). Cover every cross-field validator branch (positive + each negative), every literal value (positive + at least one negative), every `field_validator` accept/reject, the `with_prior_attempt` 3-call accumulation, the AST scans, and the module-purity test.

### Test ordering

Run the four test files in order: models → ABC → field-names → purity. The field-names test depends on S1-03's `iter_nested_field_names` being importable; if S1-03 is not yet executed, mark `xfail(strict=True)` on the file with the dependency-name; remove the marker once S1-03 ships. Documenting the dependency early prevents a silent "test was skipped" failure mode.
