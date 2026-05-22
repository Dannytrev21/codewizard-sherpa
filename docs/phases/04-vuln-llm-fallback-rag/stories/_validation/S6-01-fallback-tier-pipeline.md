# Validation report — S6-01 — `FallbackTier` named-sequential pipeline

**Validated:** 2026-05-22
**Verdict:** **HARDENED**
**Story:** `docs/phases/04-vuln-llm-fallback-rag/stories/S6-01-fallback-tier-pipeline.md`

## Context brief

- **Goal:** Ship `src/codegenie/fallback/tier.py` exposing `FallbackTier.run` as a short, named, sequential pipeline of nine per-step events plus a terminal `PlanOutcomeEmitted` (= ten audit events total on happy path), each step emitting exactly one event in a fixed order, producing a typed `RecipeApplication` from a validated `PlanProposal` on the initial-planning (`prior_attempts=[]`) path.
- **Phase exit criteria touched:** High-level-impl Step 6. Phase 5 has already merged the `FallbackTier.run(advisory, repo_ctx, recipe_selection, *, prior_attempts=[]) -> RecipeApplication` call-site (G2 in phase arch); Phase 6 (LangGraph) reads `tests/fixtures/fallback_tier_callable.py` as its lift-contract.
- **Authoritative ADRs:** ADR-0002 (Pipeline, no LangGraph / no Chain-of-Responsibility / no async-generator), ADR-0004 (`PlanOutcome` wraps `RecipeOutcome` — never widens), ADR-0010 (`BudgetToken` capability flows through exactly two frames), ADR-0012 (`ProvenanceGate` runs first; tier-0; event-absence on `LeafInvoked` proves the gate fired), ADR-0013 (`FenceWrapper` scans untruncated then truncates; never log raw completions / prompts).
- **Out-of-scope (deferred):** Retry path (`prior_attempts != []`) → S6-02; `on_validated` body → S6-03; `typecheck.typescript` SignalKind → S6-04..06; determinism under cassette replay → S6-07.

## Critic reports

### Coverage critic — verdict: harden

1. **[block]** "Each step emits one event" is asserted only as an ordered kind-list — duplicate emits would only be caught if the list-length mismatch fires; mutation pressure is weak. Need an explicit `len(recorded) == 10` and `Counter(kinds)` exact-multiplicity assertion.
2. **[block]** `LeafInvoked` and `LeafReturned` are both listed as separate kinds but described as "one event per step" — internal contradiction. Step 6 (leaf-invoke) emits two events per ADR-0010 §Consequences; the story must say so.
3. **[block]** No AC pins the event-list shape for `LEAF_REFUSED` / `LEAF_SCHEMA_VIOLATION` / `BUDGET_EXCEEDED` paths — implementer could emit `TransformBuilt` before refusing and still pass.
4. **[harden]** No AC for `on_validated` stub raising `NotImplementedError("see S6-03")` — only mentioned in outline §7.
5. **[harden]** No AC pins `assert_never(plan)` exhaustiveness on `match plan` — mypy `--strict` only catches it if the file actually uses `match`; an `if/elif` over `.kind` strings would slip through.
6. **[harden]** No AC pins `leaf.invoke.call_count == 1` on happy path.
7. **[harden]** No AC pins happy-path `PlanOutcomeEmitted` variant is `AppliedFromLlm` (not `AppliedFromRecipe`).
8. **[harden]** No AC pins typed-error policy: which exceptions propagate vs convert to `Refused`.
9. **[harden]** No AC pins `tests/fixtures/fallback_tier_callable.py` factory constructs successfully — a typo-broken fixture would pass the export-existence check.

### Test-Quality critic — verdict: harden

1. **[block]** `leaf.invoke` payload identity never asserted — `LeafInvoked` could carry the wrong `prompt_digest_blake3`, `PlanOutcomeEmitted` could carry the wrong variant, and the kind-list test still passes. Need cross-event identity checks (`PromptBuilt.digest == LeafInvoked.digest`; `BudgetPrecharged.token_id == BudgetReconciled.token_id`).
2. **[block]** "Short-circuit after emit" mutations slip through — happy-path test needs `leaf.invoke.assert_awaited_once()`; budget-precheck test (the AC exists but the TDD plan never shows it) needs `leaf.invoke.assert_not_awaited()`.
3. **[block]** `AsyncMock(side_effect=pytest.fail.__wrapped__)` — `pytest.fail` does not expose `__wrapped__`; this constructor raises `AttributeError`. Replace with `AsyncMock(); leaf.invoke.side_effect = AssertionError("...")`.
4. **[harden]** Provenance-refuse test covers only `BaseImage`; parametrize over every non-app-layer variant of `Provenance` enum.
5. **[harden]** No `Counter(kinds)` multiplicity invariant.
6. **[harden]** No prefix-ordering property: aborts must emit a prefix of the happy-path event list plus a terminal event.
7. **[harden]** `capturing_event_log` fixture is unspecified; spec against the `EventLog` Protocol so a renamed `.emit` method doesn't silently make tests vacuously pass.
8. **[nit]** Fence test `tests/fence/test_no_raw_completions_logged.py` should have a positive case asserting it catches an inline violation.

### Consistency critic — verdict: harden

1. **[block]** `RecipeApplication.Applied | RecipeApplication.Refused(reason=...)` shape is what Phase 4 arch §Component 1 (lines 430, 475) and ADR-0012 §Decision authoritatively declare. Phase 5 stories (S5-01, S5-02) speak of `RecipeApplication.diff: bytes` as a single attribute. **These can co-exist if `RecipeApplication` is a tagged union (`Applied(diff=bytes)` + `Refused(reason=Literal[...])`) — but if Phase 5's already-shipped type is a single class, the story silently breaks Phase 5.** Surface to implementer as Global-Rule-7 conflict; Phase 4 arch is the local source of truth and AC stays as `Refused(reason=...)`, but executor must confirm Phase 5's `RecipeApplication` is a discriminated union or amend the contract before shipping.
2. **[block]** Nine-step pipeline vs ten event kinds — internal counting inconsistency. ADR-0004 §Consequences explicitly authorizes the second-event-per-outcome (`PlanOutcomeEmitted` is *in addition to* the per-step events). Story header + AC #4 must say "nine per-step events + one terminal `PlanOutcomeEmitted` = ten total."
3. **[block]** "Extends S2-05's import-linter contract" — S2-05 already pins import scope to `{codegenie.fallback.budget, codegenie.fallback.tier, codegenie.fallback.leaf.anthropic_adapter}` and ships `tests/fence/test_budget_token_scope.py`. S6-01 does not extend; it *exercises*. Drop the invented test file path.
4. **[harden]** No AC for registering the eight new event kinds in `src/codegenie/plugins/events.py` (`WorkflowInternalEvent` union + `_INTERNAL_CLASSES`). Currently no Phase-4 event is registered. The executor must add them or runtime emission will fail Pydantic-discriminator validation.
5. **[harden]** `on_validated` stub is in outline §7 but never in an AC.

### Design-Patterns critic — verdict: harden

**Correct rejections confirmed:** Chain-of-Responsibility Protocol, `_TierStep` for-loop, LangGraph state machine, async-generator `TierChain`, `Strategy` over tier-order, registry-on-`PlanProposal.kind` for Transform-build. All correctly forbidden by ADR-0002 / phase-4 arch §Design patterns applied row 1.

1. **[harden]** `prior_attempts: list[AttemptSummary] = []` — mutable default. Change to `Sequence[AttemptSummary] = ()`. If Phase 5's pre-merged signature literally types `list[...] = []`, surface as Global-Rule-7 conflict; do not silently blend.
2. **[harden]** Refuse-reason strings appear as raw `str` in ACs — must be `Literal["PROVENANCE_NOT_APP_LAYER","BUDGET_EXCEEDED","LEAF_REFUSED","LEAF_SCHEMA_VIOLATION"]` per ADR-0004 (closed-set discipline, anti-pattern avoided §3 stringly-typed identifiers).
3. **[harden]** `PlanOutcomeEmitted` payload typing not pinned — must carry `outcome: PlanOutcome` (the discriminated union), not `dict`.
4. **[nit]** Outline §5 ("Refactor common metadata into a small `_emit(kind, **fields)` helper") contradicts Refactor section ("Extract … only if duplication exceeds two-line cost"). Reconcile: extract only if ≥ 2 fields are shared across every emit.
5. **[harden]** Pure projection opportunity: `match plan` over `PlanProposal` → `Transform` is pure. Extract as module-level `transform_from_plan(plan: PlanProposal) -> Transform` (functional core); `run()` calls it. Lets a small unit test exercise every variant + `assert_never` arm in isolation.
6. **[nit / Notes]** Rule-of-three reminder: when Phase 13 (cost-aware tier re-rank) adds the *third* tier-shaped extension, revisit `_TierStep` Protocol. Until then the linear body is correct.

## Conflict resolutions (priority: Consistency > Coverage > Test-Quality > Design-Patterns)

- **Consistency #1 vs Coverage #3:** Phase 4 arch authoritatively names `RecipeApplication.Refused(reason=...)`; story keeps that shape. If Phase 5's shipped type is a single class, surface as Global-Rule-7 conflict in Notes-for-implementer — do not silently rewrite either side.
- **Design-Patterns #1 vs Phase-5 contract (G2):** Phase 5 merged `prior_attempts=[]` (a `list`). `Sequence[AttemptSummary] = ()` is read-covariant and accepts callers passing `[]`; the AC adopts `Sequence` (Python-correctness wins over signature-string-exactness because the contract is the *shape Phase 5 passes*, not the type-annotation string). Notes-for-implementer warns to surface if Phase 5's type is invariantly `list`.
- **Coverage #2 (event-per-step) vs arch wording:** ADR-0010 §Audit events explicitly lists `LeafInvoked` + `LeafReturned` as two events from step 6. Story is amended to make this explicit.

## Edits applied

See the story file's `Validation notes` block for the full change list. Summary:

- **ACs strengthened:** 11 ACs added/rewritten — event-list shapes for each refuse path, exact event count, `assert_never` exhaustiveness, `on_validated` stub, `RecipeApplication.Refused.reason` typed `Literal[...]`, `PlanOutcomeEmitted.outcome` typed `PlanOutcome`, factory constructs successfully, leaf-call-count, happy-path `PlanOutcome` variant, typed-error policy, event registration in `WorkflowInternalEvent`.
- **TDD plan fixed:** broken `pytest.fail.__wrapped__` → `AssertionError`-side-effect; payload identity assertions added; parametrized provenance test; budget-precheck refuse test added; prefix-ordering property test added; `Counter(kinds)` multiplicity invariant added; `capturing_event_log` spec'd.
- **Implementation outline updated:** `_emit` helper reconciled (only-if-shared-≥2-fields); pure `transform_from_plan` extraction prescribed.
- **Notes-for-implementer expanded:** mutable-default footgun; Phase 4 vs Phase 5 `RecipeApplication`-shape conflict (Global-Rule-7 surface, do not blend); rule-of-three reminder for `_TierStep`.

## Final verdict

**HARDENED.** Story now constrains a correct implementation: every AC is individually verifiable, the AC set collectively guarantees the goal (no escape hatches for short-circuit-after-emit or duplicate-emit mutations), the TDD plan would fail a wrong implementation (payload identity + multiplicity + prefix-ordering), and the prescribed implementation extends by addition without violating ADR-0002's "the chain order *is* the policy" commitment. Two cross-phase conflicts (`RecipeApplication` shape, `list` vs `Sequence` for `prior_attempts`) surfaced to the implementer rather than silently averaged.
