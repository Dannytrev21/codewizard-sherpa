# Validation report — S1-04 `gates/contract.py` — Gate ABC + 5 frozen Pydantic models + TransitionId + ReplanHook

**Story:** [`../S1-04-gates-contract-abc-models.md`](../S1-04-gates-contract-abc-models.md)
**Validated:** 2026-05-22
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S1-04 ships the third load-bearing surface of Phase 5 — the `Gate` ABC, the `TransitionId` enum, the `ReplanHook` Protocol, and the five frozen Pydantic models (`RetryPolicy`, `AttemptSummary`, `GateContext`, `GateOutcome`, `Attempt`) that the gate seam exchanges with the runner, the orchestrator, and Phase 4. The draft was structurally correct — the goal traced cleanly to ADR-0006 / ADR-0002 / ADR-0014 / ADR-0008, the field set matched `phase-arch-design.md §Data model` (lines 721–776), and Out-of-scope was disciplined (S1-05 registry, S4-05 StrictAndGate, S5-02 GateRunner, S5-01 ReplanHook contract test, S2-01 ledger persistence).

But it had **18 weaknesses** spanning all four critic lenses, including **three block-tier findings**. Most consequentially:

1. **(consistency — block) `SignalKind` redefinition contradicts S1-03's chokepoint.** Implementation outline §2 said "Define `SignalKind = str`" (arch line 721 placeholder). But S1-03 promoted `SignalKind = NewType("SignalKind", str)` to [`src/codegenie/types/identifiers.py:96`](../../../../src/codegenie/types/identifiers.py:96), and S1-03 AC-4c is an AST source-scan chokepoint test that **forbids any `NewType("SignalKind", …)` redefinition under `src/codegenie/gates/`**. An executor following the draft literally would have failed S1-03's chokepoint. Resolved by importing `SignalKind` from `codegenie.types.identifiers`; new AC-S asserts `is`-equality against the canonical declaration site; new AST source-scan AC catches future regressions.
2. **(coverage / tests — block) `GateOutcome` cross-field invariants unenforced.** The draft permitted `GateOutcome(passed=True, state="failed_retryable", retryable=True, failing_signals=["tests"])` — a structurally nonsense outcome that Phase 6's LangGraph reducer would treat as authoritative and that `RetryLedger` would chain into the audit. Mirrors S1-02 AC-7b/c/d block-tier finding. Resolved with a `@model_validator(mode="after")` enforcing the four state↔(passed, retryable, failing_signals) cross-field invariants (positive + 2+ negative paths per state).
3. **(coverage / tests — block) Literal positive set unpinned.** The draft's `test_outcome_state_literal_rejects_unknown` checked only that `"weird_state"` is rejected. An executor shipping `Literal["pass", "fail_r", "fail_u", "esc"]` (shorter aliases) would pass every test — but Phase 6's `Command(goto=...)/interrupt()` dispatch keys on the byte-exact strings. Mirrors S1-02 M-6/M-7. Resolved with `typing.get_args(...)` byte-equal AC + parametrized positive construction across all four states.
4. **(tests — harden) `extra="forbid", frozen=True` parametrized over all 5 Pydantic models.** Draft tested only `RetryPolicy` directly (one `test_models_are_frozen_and_extra_forbid` against `RetryPolicy`). The other four Pydantic models could have silently shipped `extra="ignore"` or `frozen=False`. Mirrors S1-02 M-2 and S1-03 same gap. Resolved with parametrized assertion `Cls.model_config["extra"] == "forbid"` AND `Cls.model_config["frozen"] is True` for each.
5. **(consistency — harden) `with_prior_attempt` signature unrealizable from arch alone.** Arch line 749 sketches `with_prior_attempt(self, outcome: GateOutcome) -> "GateContext"` — but `AttemptSummary.sandbox_run_id` cannot be derived from `outcome` (neither `GateOutcome` nor `SignalProvenance` carry it; `Attempt.sandbox_run_id` is downstream, populated by the runner). Per arch §Component design — GateRunner step 6, the runner has `run.run_id` at the callsite. Resolved by widening signature to `(self, outcome: GateOutcome, *, sandbox_run_id: RunId)` — surfaced as "Open ambiguity (resolved)" with the rationale.
6. **(consistency / patterns — harden) `ReplanHook` return type references nonexistent `RecipeApplication`.** Draft annotated `__call__(self, ctx: GateContext) -> RecipeApplication`. `grep -rn "class RecipeApplication" src/` returns zero matches; the actual Phase-3 transform-outcome type that ships GREEN is `codegenie.transforms.outcomes.RecipeOutcome` (the `Applied | Skipped | NotApplicable | Failed` sum). An executor following the draft would mint a phantom type that contradicts S5-01's integration test. Resolved by string forward-ref to `"RecipeOutcome"` with TYPE_CHECKING-only import.
7. **(coverage / tests — harden) `with_prior_attempt` semantics under-specified.** Draft AC ("length increases by 1; original untouched") fails to catch (a) a "prepend" mutation that satisfies the length check; (b) a "return self with side-effect on prior_attempts" mutation; (c) accumulation drift after 3 successive calls. Split into AC-G-4 (positional append), AC-G-5 (list-identity / immutability), AC-G-6 (3-call accumulation in correct order).
8. **(patterns — harden) `AttemptNumber` newtype adopted from `types/identifiers.py:102`.** The identifier was created explicitly for *this story* per the docstring `"Bounded retry counter (1..1024); S1-04 AttemptSummary.attempt."` Rule-of-three already cleared (`AttemptSummary.attempt_id`, `Attempt.attempt_id`, `GateOutcome.attempt`, `RetryPolicy.max_attempts`). New ACs adopt it.
9. **(patterns / coverage — harden) `prev_hash`/`chain_hash` lowercase-hex.** Draft AC was "32-char hex"; uppercase `"A"*32` would pass `int(v, 16)`. ADR-0005 (Phase 4 chain-head compatibility) requires lowercase canonical hex; uppercase mismatches on replay verification. Tightened to regex `^[0-9a-f]{32}$` + parametrized rejection of uppercase, mixed-case, non-hex, short, long.
10. **(coverage — harden) `TransitionId` member-set cardinality unpinned.** Draft asserted values but not the *member set*; an executor adding a third member would pass every test. Promoted to AC-3a (set-equality) + AC-3 (mixin discipline: `str, Enum` so YAML/JSON round-trip yields the value).
11. **(coverage — harden) `RetryPolicy.retryable_failures ⊥ non_retryable_failures` cross-field invariant.** A signal in both lists is undefined dispatch for `StrictAndGate.evaluate` (S4-05). Added `@model_validator` enforcing disjoint sets.
12. **(coverage — harden) `Attempt.ended_at >= Attempt.started_at`.** Mirrors S1-02 AC-7c (parallel cross-field invariant on `SandboxRun`).
13. **(coverage / consistency — harden) ADR-0014 inheritance: hard AC, not a Refactor "confirm".** Draft Refactor said "confirm" but it's not testable as an AC. Promoted to AC-INH: reuse S1-03's `iter_nested_field_names` walker (now public per S1-03 hardening) and assert no field name (transitively) on `Attempt`/`GateOutcome`/`GateContext`/`AttemptSummary`/`RetryPolicy` contains the four banned substrings.
14. **(consistency — harden) Module purity + `__future__ annotations` + `__all__` discipline.** No AC in the draft. Mirrors S1-02 AC-9/9a/9b precedent exactly. Added the parallel test file `tests/gates/test_contract_purity.py` with TYPE_CHECKING-aware import walker.
15. **(consistency — harden) Coverage floor wording bug** ("≥ 95% branch" vs README "95 line / 90 branch"). Same conflation S1-02 and S1-03 fixed; consistency is its own dimension.
16. **(coverage — harden) `evidence_paths` annotation pinning.** Draft used `{"stdout": Path("/tmp/o")}` in a fixture but no AC asserted the field shape. An executor could ship `dict[str, str]` or `Mapping[str, Path]`. Added AC-H-1 with `get_type_hints`.
17. **(coverage — harden) `prior_failure_summary` byte cap, not char cap.** Arch §Harness engineering says 4 KiB. Draft AC was character-count. Tightened to UTF-8 byte count with parametrized boundary tests (ASCII, multibyte two-byte, multibyte three-byte at the boundary).
18. **(patterns — nit, surfaced as Note) Forward-seam for `GateOutcome.state` closed Literal.** Phase 6's LangGraph maps the 4 states to `Command(goto=...)/interrupt()`. Adding a 5th state requires an ADR amendment AND a Phase 6 reducer change — *not* a silent widening to `str`. Mirrors S1-02's "closed Literal of an open registry" pattern.

18 hardening edits applied in place; no `RESCUE`-tier findings (every gap was patchable by adding ACs, tightening tests, importing the right types, and routing through the established kernels — not by re-architecting goal or scope). No Stage-3 research needed — every gap was answerable from the four honored ADRs, arch §Data model + §Component design + §Integration with Phase 6 + §Edge cases, CLAUDE.md (Extension by addition, Newtype identifiers, Functional core / imperative shell, Rule 11), the existing kernel modules (`types/identifiers.py`, `sandbox/contract.py` per S1-02, `sandbox/signals/_introspection.py` per S1-03), and the two prior HARDENED reports (S1-02, S1-03).

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim, hardened):** Ship `src/codegenie/gates/contract.py` exposing the `Gate` ABC, the `TransitionId` enum, the `ReplanHook` Protocol (return type `RecipeOutcome`), and the five frozen `extra="forbid"` Pydantic models (`RetryPolicy`, `AttemptSummary`, `GateContext`, `GateOutcome`, `Attempt`) — with `SignalKind` and `AttemptNumber` IMPORTED from `codegenie.types.identifiers` and `RunId` IMPORTED from `codegenie.sandbox.contract`, never redefined.
- **Non-goals (from Out-of-scope):** `StrictAndGate` (S4-05), `GateRunner.run` (S5-02), `@register_signal_kind` (S1-05), `ReplanHook` integration test (S5-01), `FenceWrapper.compose_prior_attempts` (S5-03), YAML catalog loader (S1-06), `evidence_paths` population (S5-02), Phase-3 typed `Advisory`/`Recipe`/`TransformOutput` (Phase-3 future), promoting `RunId` to identifiers (future cleanup).

### Phase 5 exit criteria touched

- Step 1 done-criteria (High-level-impl.md §Step 1): `pytest tests/gates/test_contract*.py tests/gates/test_gate_abc.py` green; `mypy --strict src/codegenie/gates` clean; line ≥ 95% AND branch ≥ 90% on `gates/contract.py`.
- §Goal 3 (arch): "Public surface introduced — one `Gate` ABC." This story is the ABC declaration site.
- §Goal 8 (arch): `ObjectiveSignals` `extra="forbid", frozen=True`; ADR-0014 enforcement transitively extends to `Attempt.signals`/`GateOutcome.signals` (AC-INH).
- §Integration with Phase 6 (arch lines 940-953): `GateOutcome.state` maps to LangGraph; `AttemptSummary` is the state ledger payload; `Gate.evaluate` is a pure function safe to call on resume; `with_prior_attempt` lifts as a Phase 6 reducer.
- ADR-0002 (additive `prior_attempts` kwarg): `AttemptSummary` is the structured payload; `prior_failure_summary` is fence-wrapped (Phase 4 owns the wrapping; this story enforces the byte cap).
- ADR-0006 (Protocol vs ABC): `Gate` is ABC (shared default behavior); `ReplanHook` is Protocol (duck-typed, no shared behavior).
- ADR-0014 (`extra="forbid"` + static introspection): every Pydantic model here carries the config; transitively, `signals: ObjectiveSignals` inherits S1-03's invariant; AC-INH extends the introspection scope to the top-level field names of all 5 gates models.
- ADR-0008 (LLM Judge persona deferred): `AttemptSummary.prior_failure_summary` is the *only* text channel between gate runner and Phase 4; it is fence-wrapped (Phase 4 side) and byte-capped (this story).

### Load-bearing commitments touched

- **CLAUDE.md "Extension by addition"** — new gate kinds register as subclasses of `Gate` ABC; the ABC itself stays Open/Closed.
- **CLAUDE.md "Domain identifiers ... newtype when crossing ≥ 2 modules"** — `SignalKind`, `AttemptNumber`, `RunId` all cross ≥ 5 module boundaries.
- **CLAUDE.md "Functional core / imperative shell"** — `gates/contract.py` is pure (no I/O, no logger, no methods on models beyond validators); `GateRunner` (S5-02) is the imperative shell.
- **CLAUDE.md "Match existing convention"** — `from __future__ import annotations`, alphabetized `__all__`, module docstring naming ADRs, single-declaration-site discipline for NewTypes — all established by Phase 0/1/2 (`result.py`, `adapters/protocols.py`) and reinforced by S1-02 and S1-03 hardening.
- **ADR-0006** — Gate is ABC (shared default state); ReplanHook is Protocol (duck-typed); the bodies of all Protocol methods are `...` (no shared default behavior; AST-asserted, mirrors S1-02 AC-2b).
- **ADR-0002** — `AttemptSummary` is the structured retry-feedback payload; signature shape locked here, byte-cap (4 KiB UTF-8) on `prior_failure_summary` lives here, fence-wrap is Phase 4's responsibility.
- **ADR-0014** — `extra="forbid", frozen=True` plus banned-substring scan extends transitively to this story's models via the S1-03 walker.
- **ADR-0008** — no LLM judgment fields anywhere in the trust graph; enforced by code (the AC-INH substring scan), not prose.
- **Phase 6 lift-unchanged commitment** (arch §Integration with Phase 6) — the 5 Pydantic models + Gate ABC + TransitionId enum + ReplanHook Protocol are the seam Phase 6's LangGraph nodes consume. Illegal-states-representable here = illegal-states-inherited downstream.

### Open ambiguities (resolved before Stage 2)

- **`with_prior_attempt` signature.** The arch line 749 sketch `with_prior_attempt(self, outcome: GateOutcome)` cannot derive `sandbox_run_id` from `outcome`. Resolution: widen to `(self, outcome: GateOutcome, *, sandbox_run_id: RunId)`. `GateRunner` (S5-02 step 6) has `run.run_id` at the callsite. Cleanest cut; documented as Validation note #5 + AC-G-2.
- **`ReplanHook.__call__` return type.** Draft said `RecipeApplication`; the type does not exist. Phase 3 ships `RecipeOutcome` (sum type) at `codegenie.transforms.outcomes.RecipeOutcome`. Resolution: string forward-ref `"RecipeOutcome"` + TYPE_CHECKING-only import. Documented as Validation note #7 + AC-K-3.
- **`Advisory`/`Recipe`/`TransformOutput` types on `GateContext`.** Phase 3 has not shipped them as classes. Resolution: `str` placeholders today; widening is a future story. Documented in Implementation outline + Notes.
- **Whether `RunId` should promote to `types/identifiers.py`.** S1-03 set the precedent by promoting `SignalKind`. Resolution: not in S1-04's scope (Rule 3 — surgical changes). Surfaced as a future cleanup story.

### Phase 1/2/5 prior art consulted

- [`src/codegenie/types/identifiers.py`](../../../../src/codegenie/types/identifiers.py) — `SignalKind` (line 96, S1-03 promotion), `AttemptNumber` (line 102, created for this story), `RecipeId`, `WorkflowId`, `CveId`, `EventId`.
- [`src/codegenie/sandbox/contract.py`](../../../../src/codegenie/sandbox/contract.py) — S1-02's `RunId` declaration site; established the `from __future__ import annotations` + `__all__` + module-purity invariant + AST chokepoint for NewType-redefinition.
- [`src/codegenie/sandbox/signals/_introspection.py`](../../../../src/codegenie/sandbox/signals/_introspection.py) — S1-03's `iter_nested_field_names` public function; AC-INH reuses it without re-implementation.
- [`src/codegenie/transforms/outcomes.py`](../../../../src/codegenie/transforms/outcomes.py) — Phase 3's `RecipeOutcome` sum type (`Applied | Skipped | NotApplicable | Failed`). The forward-ref target.
- [`src/codegenie/adapters/protocols.py`](../../../../src/codegenie/adapters/protocols.py) — Phase 2's `runtime_checkable` Protocol precedents; the `TestId = NewType("TestId", str)` pattern at line 41.
- S1-02 HARDENED report (`_validation/S1-02-sandbox-contract-protocol-models.md`) — the template for "model_config introspection on every model" + "Literal byte-exact positive + negative" + "cross-field invariants" + "module-purity test".
- S1-03 HARDENED report (`_validation/S1-03-objective-signals-models.md`) — the template for "promote shared identifier to `types/identifiers.py`" + AST chokepoint + `iter_nested_field_names` walker.

## Stage 2 — critic reports

### 2A · Coverage critic (verdict: COVERAGE-RESCUE → patched to HARDEN)

The Coverage critic flagged **two block-tier findings** and 7 harden-tier findings.

| # | Severity | Finding | Fix applied |
|---|---|---|---|
| **C-1** | **block** | **`GateOutcome` cross-field invariants unenforced (state↔passed↔retryable↔failing_signals)** | New `@model_validator` `_check_state_invariants` + AC-CF-1..AC-CF-4 with positive + negative paths per state |
| **C-2** | **block** | **Literal positive set unpinned (M-6/M-7 pattern)** | New AC-5 (`typing.get_args(...)` byte-equal) + AC-5a (parametrized positive construction across all 4 states) |
| C-3 | harden | `extra="forbid", frozen=True` parametrized over all 5 Pydantic models | New AC-4 + AC-4a + AC-4b parametrized fixture |
| C-4 | harden | `with_prior_attempt` semantics under-specified — prepend, mutate-self, accumulation-drift mutations would pass | New AC-G-3..AC-G-6 (split positional, identity, accumulation) |
| C-5 | harden | `TransitionId` member-set cardinality unpinned | New AC-3a (set-equality) + AC-3 (subclass discipline) + AC-3c (rejection) + AC-3d (str mixin) |
| C-6 | harden | `RetryPolicy` `retryable_failures` ⊥ `non_retryable_failures` invariant missing | New `@model_validator` + AC-I-2 |
| C-7 | harden | `Attempt.ended_at >= started_at` invariant missing | New `@model_validator` + AC-J-2 |
| C-8 | harden | `evidence_paths` annotation pinning missing | New AC-H-1 (`get_type_hints` returns exactly `dict[str, Path]`) |
| C-9 | harden | `prior_failure_summary` cap was character-count; arch is byte-count | Tightened to UTF-8 byte count + multibyte boundary tests (AC-H-2) |
| C-10 | nit | Coverage floor wording ("≥ 95% branch" vs README's "95 line / 90 branch") | Tightened AC-12 to "line ≥ 95% AND branch ≥ 90%" |

The two block-tier findings (C-1, C-2) are patchable — both fix at the AC + TDD-plan level, not at the goal level. Promoted RESCUE → HARDEN.

### 2B · Test-quality critic (verdict: TESTS-HARDEN)

Mutation analysis — 22 plausible wrong implementations evaluated. Headline misses caught in the harden:

| # | Wrong implementation | Caught by draft TDD? | Caught after harden? |
|---|---|---|---|
| M-1 | Drop `extra="forbid"` on `AttemptSummary` | No — only `RetryPolicy` was tested | Yes — parametrized over all 5 models |
| M-2 | Drop `frozen=True` on `GateContext` | No | Yes — same |
| **M-3** | **Ship `Literal["pass", "fail_r", "fail_u", "esc"]`** | **No — negative test on `"weird_state"` still rejects** | **Yes — `typing.get_args` byte-equal + positive-construction parametrized** |
| M-4 | `with_prior_attempt` prepends instead of appends | No — length still increases by 1 | Yes — AC-G-4 positional check |
| M-5 | `with_prior_attempt` mutates `self.prior_attempts.append(...)` and returns `self` | Partial — `new is not ctx` check would pass if a copy is returned, but mutating the SHARED list is undetected | Yes — AC-G-5 identity check on `prior_attempts` list |
| M-6 | `with_prior_attempt` works for the first call but breaks accumulation on second | No | Yes — AC-G-6 three-call test |
| **M-7** | **`GateOutcome(passed=True, state="failed_retryable", retryable=False)` accepted** | **No** | **Yes — AC-CF-2 negative path** |
| **M-8** | **`GateOutcome(passed=False, state="passed", failing_signals=[])` accepted** | **No** | **Yes — AC-CF-1 negative path** |
| M-9 | `prev_hash="A"*32` accepted (uppercase) | No — `int(v, 16)` parses uppercase | Yes — regex `^[0-9a-f]{32}$` |
| M-10 | `prev_hash="0"*64` accepted (wrong length, BLAKE3-256) | No (draft check too lax) | Yes — fullmatch with `{32}` |
| M-11 | `RetryPolicy(retryable_failures=["tests"], non_retryable_failures=["tests"])` accepted | No | Yes — disjoint validator + AC-I-2 |
| M-12 | `TransitionId` adds a third member silently | No | Yes — AC-3a set-equality |
| M-13 | `Attempt(ended_at=earlier_than_started)` accepted | No | Yes — AC-J-2 + validator |
| M-14 | `prior_failure_summary` cap is 4096 *characters*, not bytes | Partial — ASCII tests pass | Yes — multibyte boundary tests + UTF-8 byte length |
| M-15 | `attempt_id` accepts `0` or `1025` | No | Yes — AC-H-3 / AC-J-3 range |
| M-16 | `SignalKind` redefined locally as `NewType("SignalKind", str)` | No — passes import tests | Yes — AC-S `is`-equality + AST scan |
| M-17 | `RunId` redefined locally | No | Yes — AC-R same pattern |
| M-18 | `ReplanHook` adds a `cleanup` method silently | No | Yes — AC-K-2 set-equality |
| M-19 | `ReplanHook.__call__` body provides a default implementation (ADR-0006 violation) | No | Yes — AC-K-4 AST walk |
| **M-20** | **`ReplanHook` returns `RecipeApplication` (phantom)** | **No — passes import but breaks at S5-01 integration** | **Yes — AC-K-3 explicit `RecipeOutcome` forward-ref** |
| M-21 | `evidence_paths` typed as `dict[str, str]` | No — Pydantic coerces Path to str at runtime | Yes — `get_type_hints` source-level check |
| M-22 | `GateContext.with_prior_attempt` signature omits `sandbox_run_id` (forcing S5-02 to thread the value through a hack) | No — the arch sketch is signature-locked at the draft | Yes — AC-G-2 keyword-only kwarg check |

Original tests that survived review:
- `test_gate_cannot_be_instantiated_directly` — kept verbatim (AC-2a).
- `test_subclass_missing_evaluate_cannot_instantiate` — kept (AC-2b).
- `test_concrete_subclass_works` — kept (AC-2c).
- `test_transition_id_enum_values` — kept (AC-3b) and supplemented.

Properties added:
- The four-state cross-field invariants on `GateOutcome` (positive + at least two negative paths per state).
- The 3-call accumulation test on `with_prior_attempt`.
- AST source-scan for NewType-redefinition (AC-S / AC-A / AC-R).
- Module purity walker (TYPE_CHECKING-aware).
- ADR-0014 inheritance scan (re-uses S1-03's walker; AC-INH).

### 2C · Consistency critic (verdict: CONSIST-HARDEN)

| # | Severity | Finding | Fix applied |
|---|---|---|---|
| **#1** | **block** | **Implementation outline §2 contradicts S1-03's AC-4c AST chokepoint (`SignalKind = str` redefinition)** | Updated outline §2 to "Do NOT redefine — import from `codegenie.types.identifiers`"; added AC-S + AST chokepoint mirror |
| #2 | harden | `with_prior_attempt(self, outcome)` signature from arch is unrealizable (cannot derive `sandbox_run_id`) | Resolved via additional `sandbox_run_id: RunId` keyword-only kwarg; documented as "Open ambiguity (resolved)" in Validation note #5 |
| #3 | harden | `ReplanHook` return type `RecipeApplication` is a phantom (no such class in codebase) | Resolved via string forward-ref to existing `RecipeOutcome` + TYPE_CHECKING-only import |
| #4 | harden | Coverage floor wording bug ("≥ 95% branch" vs "95 line / 90 branch") | Same fix S1-02/S1-03 applied; AC-12 tightened |
| #5 | harden | `AttemptNumber` newtype is created in `types/identifiers.py:102` explicitly for this story but unused in the draft | Adopted on `attempt_id`/`max_attempts`/`attempt` fields |
| #6 | harden | `from __future__ import annotations` + `__all__` + module-purity test missing | Added in mirror of S1-02 AC-9/9a/9b precedent |
| #7 | harden | ADR-0014 inheritance scan was a Refactor "confirm" — promote to AC | AC-INH (new test file reusing S1-03 walker) |
| #8 | nit | `Mapping` import source — not applicable here (no Mapping in this file) | — |

No `RESCUE`-tier consistency findings. The block-tier #1 is patchable as an outline + AC edit.

### 2D · Design-patterns critic (verdict: PATTERNS-HARDEN)

| # | Severity | Finding | Fix applied |
|---|---|---|---|
| 1 | harden | Primitive obsession on `attempt_id` / `attempt` / `max_attempts: int` — crosses ≥ 4 modules; `AttemptNumber` already exists in `types/identifiers.py:102` explicitly for this purpose | Adopted `AttemptNumber` on all four fields; range enforcement via `@field_validator` (so `get_type_hints` preserves the NewType) |
| 2 | harden | Primitive obsession on `sandbox_run_id`/`run_id` — `RunId` exists in `sandbox/contract.py` (S1-02) | Adopted `RunId` for `AttemptSummary.sandbox_run_id` (and the new `with_prior_attempt` kwarg); `GateContext.run_id` stays `str` for now (different semantic — workflow run vs sandbox run) |
| 3 | harden | Illegal-states-representable on `GateOutcome` (cross-state inconsistencies) and `RetryPolicy` (overlapping failure lists) and `Attempt` (reversed timestamps) | `@model_validator(mode="after")` on each; ACs in §F, §I, §J |
| 4 | harden | `with_prior_attempt` referential transparency unenforced beyond length-check | AC-G-3 / AC-G-4 / AC-G-5 / AC-G-6 split it into observable invariants |
| 5 | clean | Hexagonal port (ReplanHook Protocol) + ABC (Gate) + plugin-via-registry (sandbox backends through `SandboxClient`) is correctly framed; no opportunity missed | — |
| 6 | nit | Closed Literal mirror on `GateOutcome.state` — forward-seam pattern from S1-02 should be documented | Added forward-seam note (Implementation note #15) |
| 7 | nit | `Attempt` is exported but documented internal — the surface-cardinality vs documentation-intent distinction | Documented in AC-J-4 + docstring |
| 8 | clean | Functional core (pure data + protocol + ABC) without I/O is the right shape | — |

The two newtype findings (`AttemptNumber`, `RunId`) cross the rule-of-three threshold (`AttemptNumber` is at 4 fields here alone; `RunId` is at 6+ modules). Making them imports now prevents post-hoc cleanup stories.

## Conflict resolution (Stage 4 synthesizer)

- **Consistency #1 (SignalKind redefinition) vs Coverage's "all model fields typed":** Consistency wins (source of truth is the S1-03 chokepoint + `types/identifiers.py`). The fields use the imported `SignalKind`. Coverage is satisfied via AC-H-1 / AC-I-1 (`get_type_hints` checks).
- **Consistency #2 (with_prior_attempt signature) vs the arch sketch:** The arch sketch is the goal direction, not the line-by-line contract. The signature widens by a kwarg without changing intent (`with_prior_attempt` still produces a frozen new GateContext with the AttemptSummary appended). Documented as "Open ambiguity (resolved)" rather than "deviation from arch."
- **Design-Patterns #2 (RunId promotion to identifiers.py) vs Rule 3 (surgical changes):** Rule 3 wins. S1-04's scope is gates/contract.py; promoting `RunId` would force edits to S1-02 (already HARDENED + presumably executed). Promotion is a future-cleanup story.
- **Coverage C-8 (`evidence_paths` annotation) vs Out-of-scope (population deferred to S5-02):** Complementary. The *shape* is pinned here (S1-04 AC-H-1); the *population* (filling the dict from `SandboxRun.copy_out_root`) is S5-02. Both apply.
- **Design-Patterns #1 (AttemptNumber) vs Pydantic's `Annotated[int, Field(ge=1, le=1024)]` ergonomic:** The Pydantic-friendly form would erase the NewType from `get_type_hints`. Resolution: keep the field annotation as the bare NewType `attempt_id: AttemptNumber`, enforce the range via `@field_validator("attempt_id")`. Two-level typing (NewType for hints, validator for runtime) is the cleanest fit to AC-H-1 + AC-H-3.

## Edits applied (summary)

1. New `Validation notes` block under the story header with 18 numbered headline edits.
2. **Acceptance criteria** rewritten from 11 ACs to 49+ (grouped A–O): import surface, Gate ABC shape, TransitionId, model_config discipline, GateOutcome Literal byte-exact (positive + negative), four GateOutcome cross-field state-invariants, GateContext + `with_prior_attempt` referential transparency + accumulation, AttemptSummary fields + UTF-8 byte cap + range, RetryPolicy fields + disjoint, Attempt timestamps + hex shape + range, ReplanHook Protocol shape, ADR-0014 inheritance, NewType source-of-truth pinning (SignalKind/AttemptNumber/RunId), module purity (future/imports/docstring), process gates.
3. **Implementation outline** rewritten from 11 numbered steps to 11 with code-level prescriptions, the corrected `SignalKind`/`AttemptNumber`/`RunId` import discipline, the keyword-only `sandbox_run_id` kwarg on `with_prior_attempt`, the explicit `_check_state_invariants` validator, the `_check_retry_classifications_disjoint` validator, the lowercase-hex regex validator, the 4096-UTF-8-byte cap validator.
4. **TDD plan** rewritten from 2 test files (~80 LOC sketch) to 4 test files (~620 LOC sketch) with parametrized fixtures, AST source-scans, set-equality assertions, and TYPE_CHECKING-aware import walker.
5. **Files to touch** updated to add `tests/gates/test_contract_field_names_static.py` and `tests/gates/test_contract_purity.py`.
6. **Out of scope** expanded with explicit deferrals: `Advisory`/`Recipe`/`TransformOutput` (Phase-3 future), `evidence_paths` population (S5-02), `RunId` promotion (future cleanup).
7. **Notes for the implementer** rewritten and ~4× longer: import discipline (the load-bearing rule), cross-field invariant rationale, `with_prior_attempt` ambiguity resolution, forward-seam notes (closed Literal + Phase-3 placeholders), NewType discipline (rule-of-three applied + the two-level typing trick), Pydantic v2 idioms, coverage process, test ordering with S1-03 dependency.

No story restructuring; the goal, scope, dependencies (S1-01 + the newly explicit S1-02/S1-03), and ADR mapping (-0006, -0002, -0014, -0008) are unchanged.

## Final verdict

**HARDENED.** Story ready for `phase-story-executor`. Every AC is individually verifiable; the AC set collectively guarantees the Goal-3 (public surface) + Goal-8 (ADR-0014 inheritance) + Phase-6 lift-unchanged commitments; every test in the TDD plan would fail on at least one named mutation (22 mutations enumerated); CLAUDE.md Rule 11 (codebase convention) is honored (mirrors S1-02 + S1-03 precedents); the design patterns surface (ABC, Protocol, model-validator illegal-states-unrepresentable, NewType, functional core, forward-seam notes) is explicit; the closed-`Literal`-mirroring-Phase-6-dispatch tension is documented as a forward seam, not silently widened.
