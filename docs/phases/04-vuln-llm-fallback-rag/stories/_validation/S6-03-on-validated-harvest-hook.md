# Validation report — S6-03 — `FallbackTier.on_validated` harvest hook

**Validated:** 2026-05-22
**Verdict:** **HARDENED**
**Story:** `docs/phases/04-vuln-llm-fallback-rag/stories/S6-03-on-validated-harvest-hook.md`

## Context brief

- **Goal:** Implement `FallbackTier.on_validated(outcome, trust, *, context)` — the inline-harvest hook called by the orchestrator after Stage 6 validates a workflow. On `trust.passed AND trust.confidence == "high"` and an LLM-emitted outcome, mint capability via the Phase-4-local shim, project to `ValidatedPlanOutcome`, call S4-06's silent keyword-only writer, emit `SolvedExampleHarvested`. Otherwise emit exactly one `HarvestSkipped(reason)` from a closed-set `Literal[...]`.
- **Phase exit criteria touched:** Roadmap exit #2 ("Re-running the same case hits RAG, not LLM, at lower cost") depends entirely on this hook firing in production behavior (not test scaffolding). High-level-impl Step 6 Features delivered (`on_validated` bullet).
- **Authoritative ADRs:** ADR-04-0009 (inline auto-harvest + confidence gate; Module Boundary not GoF Capability), ADR-04-0004 (`PlanOutcome` wraps `RecipeOutcome` — never widened), production ADR-0008 (`TrustOutcome.confidence` shape), production ADR-0034 (event-sourcing).
- **Live HARDENED preconditions (read carefully — pre-validation draft did not):**
  - S6-01 HARDENED: `FallbackTier.__init__(...)` already keyword-only accepts `confidence_gate: ConfidenceGate`. The tier is stateless ("no state of its own").
  - S4-06 HARDENED (2026-05-22 13:45 EDT): `ingest_solved_example(*, outcome: ValidatedPlanOutcome, store, embedder, capability) -> SolvedExampleId` — keyword-only, returns plain `SolvedExampleId`, silent. `_phase4_local_capability_mint(*, workflow_id, chain_head)` at `src/codegenie/rag/_capability_mint.py`. `pyproject.toml [tool.importlinter]` contract `"ADR-0016: phase4 solved-example mint module is scoped"` admits only `codegenie.rag.ingest -> codegenie.rag._capability_mint`. `SolvedExampleHarvested` registered as `WorkflowInternalEvent` with discriminator `event_type` and snake_case literal `"solved_example_harvested"`. Deterministic-id helper `_solved_example_id_for(*, outcome, embedding_model)` exists.
- **Shipped Phase-3 runtime types (verified during validation):**
  - `src/codegenie/transforms/outcomes.py:403` — **`TrustOutcome.confidence: Literal["high", "degraded"]`** (NOT `["high","medium","low"]`).
  - `src/codegenie/plugins/events.py:166–465` — every internal-event variant uses `event_type: Literal["snake_case"]`; `_INTERNAL_CLASSES` tuple + `__all__` are the registration surface.
  - `src/codegenie/types/identifiers.py:54–92` — `WorkflowId`, `ChainHead`, `BlobDigest`, `CveId`, `TaskClassId`, `Language` newtypes; `PackageManager` `Literal`.
- **Out-of-scope (deferred):** E2E (S7-07); Phase 5 capability-mint supersession; Phase 11 webhook second ingestion path; operator quarantine (Phase 6.5 / 11); amending `TrustOutcome.confidence` literal set.

## Critic reports

### Coverage critic — verdict: block

1. **[block] Mint-import location wrong.** Story AC line 36 said "Test imports `_phase4_local_capability_mint` from `codegenie.rag.ingest`" — S4-06 HARDENED puts the symbol in the private module `codegenie.rag._capability_mint` and AC-7 fences any import path from `ingest.py`.
2. **[block] `ingest_solved_example` signature mismatch.** Draft called positionally with `outcome: PlanOutcome`; S4-06 AC-2 pins keyword-only with `outcome: ValidatedPlanOutcome`. The 11-field bridge type carries data not on `PlanOutcome.AppliedFromLlm` — the story silently elided the projection step.
3. **[block] `Deduped` return variant doesn't exist.** Idempotence AC line 43 + outline §4 referenced a `Deduped` variant from `ingest_solved_example`; S4-06 returns plain `SolvedExampleId`. Test as written is unimplementable.
4. **[block] `HarvestSkipped` not registered.** Per S4-06 Out-of-scope, S6-03 owns the registration. No AC pinned it. Without registration the first emit raises a Pydantic discriminator error.
5. **[block] ADR vs story skip-reason set drift.** ADR-04-0009 enumerates only `low_confidence`; story expanded to `{low_confidence, trust_failed, outcome_not_harvestable}`. Acceptable as additive, but unpinned + must be amendable from a closed `Literal`.
6. **[harden] Emission-before-ingest escape hatch.** "Exactly once when ingest succeeds" was order-blind; a buggy impl could emit then have ingest raise.
7. **[harden] No-op-when-gate-fails AC didn't bind mint ordering.** Tests pinned `ingest_spy.assert_not_awaited()` but not `mint_spy.assert_not_called()`. Eager-mint mutation passes silently.
8. **[harden] Lock-contention test allows silent drop.** "Chain head advances monotonically" + "both return" can be satisfied by an impl that swallows one ingest.
9. **[harden] `workflow_id` + `chain_head` source hand-waved.** Outline §5 left "kwargs or `__init__` extension" undecided — three executor attempts will resolve three different ways.
10. **[harden] `ConfidenceGate` named-clauses AC unobservable.** Only truth table was tested; a one-line `def passes()` lambda passes while violating Specification-pattern intent.
11. **[nit] `Refused` reaching `on_validated`.** `Refused` outcomes aren't validated — orchestrator shouldn't call. AC should pin defensive behavior.
12. **[nit] `e.kind` vs `event_type`.** Test snippets used `e.kind`; shipped events use `event_type`.

### Test-Quality critic — verdict: block

1. **[block] `e.kind` is the wrong attribute.** Every event-presence filter in the snippets returns `[]`; `skipped[0]` raises `IndexError`. Implementer's first-pass "fix" likely flips assertions and the suite passes vacuously.
2. **[block] `harvester_spy.ingest_solved_example.assert_awaited_once()` does not pin payload.** No `_with(...)` kwargs assertion. Mutations: pass `outcome=None`; mint capability A but pass capability B; sign-flip the keyword/positional contract — all survive.
3. **[block] `Deduped` variant not in S4-06.** Idempotence test cannot be written against the actual writer surface; if the executor invents the variant, that's a silent extension of S4-06.
4. **[block] `test_confidence_gate` only exercises composition.** Truth-table parametrize does not prove gate has named clauses; a free-function lambda passes.
5. **[harden] `SolvedExampleHarvested` payload identity never asserted.** The emitted `solved_example_id` must equal `ingest_solved_example`'s return; the snippet only checks event-type presence.
6. **[harden] `capturing_event_log` fixture unspecified.** A `recorded: list = []` stub that never wires to the tier passes negative assertions; positive ones get "fixed" by deletion.
7. **[harden] Redundant `side_effect = AssertionError(...)` + `assert_not_awaited`.** Either alone is correct; both confuse and hide swallow-bugs.
8. **[harden] `asyncio.gather` test has no timeout and no observable for "chain-head monotonic".** Deadlock → CI hang, not test failure.
9. **[recommended property]** Mutual-exclusion + totality of terminal events under the closed cross-product `(4 outcomes × 2 confidence × 2 passed)` — Hypothesis-driven; catches double-emit and no-emit mutations the parametrize misses.
10. **Python correctness in snippets.** `from codegenie.gates.trust import TrustOutcome` placeholder; `AppliedFromRecipe(...)` / `RagOnlyApplicable(...)` with bare `Ellipsis` fields; `Refused(reason="PROVENANCE_NOT_APP_LAYER")` unverified literal value.

### Consistency critic — verdict: block

A. **[block] `ingest_solved_example` call shape contradicts S4-06.** Positional `outcome`, wrong type (`PlanOutcome` vs `ValidatedPlanOutcome`). S4-06 wins (more recently hardened).

B. **[block] Mint module location contradicts S4-06 AC-5/6/7.** `_capability_mint` is private; import-linter contract admits only one edge; `tier.py` is not in the allow-list. Resolutions: (1) extend the contract with one row, or (2) route mint through `ingest.py` via a new helper. Story Files-to-touch row 167 anticipates this but doesn't pin the choice.

C. **[block] `on_validated(outcome: PlanOutcome, trust: TrustOutcome)` cannot reach a `ValidatedPlanOutcome` from its two args.** Eight of `ValidatedPlanOutcome`'s 11 fields are not on `PlanOutcome.AppliedFromLlm`. Hand-wavy "extend __init__ if needed" is an under-specification. Arch wins for control-flow contract (`on_validated(outcome, trust)`); S6-01 wins for "stateless tier" invariant. Both can be preserved by a keyword-only `context: PostValidationContext` widening.

D. **[block] `HarvestSkipped` event registration missing.** S4-06 Out-of-scope explicitly defers to S6-03. ADR-04-0009 §Consequences names the event load-bearing.

E. **[block] `TrustOutcome.confidence` literal set drift.** Shipped `src/codegenie/transforms/outcomes.py:403` is `Literal["high", "degraded"]`. ADR-04-0009 + phase-arch §Edge-case 18 reference `"medium"`/`"low"`. The story's test snippets construct `confidence="medium"` and `"low"` — those raise `ValidationError` at fixture construction. The validation critic verified the shipped type directly. Resolution: keep shipped, amend ADR + arch, rewrite tests against `["high","degraded"]`.

F. **[block] `SolvedExampleHarvestedDeduped` is phantom.** Not registered; `ingest_solved_example` returns no sum. Replace with deterministic-id pre-check.

G. **[harden] Skip-reason set wider than ADR.** ADR-04-0009 §Consequences names only `low_confidence`. Story added `trust_failed`, `outcome_not_harvestable`. Additive and correct; pin via `Literal[...]` on the registered event.

H. **[harden] AC line 36 asks tests to import mint from `codegenie.rag.ingest`.** S4-06 AC-7 explicitly bans this — `ingest.py` does not re-export. Test scaffolding must patch the symbol at `codegenie.rag._capability_mint`.

I. **[nit] `_phase4_local_capability_mint` synchronous.** Consistent ✓.

J. **[harden] `AppliedFromRecipe(...)` / `RagOnlyApplicable(...)` test snippet shapes bare-Ellipsis.** Untestable without S1-03 factories.

K. **[nit] `e.kind` shorthand.** S6-01 hardened with the same shorthand; tolerable in prose but the actual code uses `event_type` with snake_case literal values.

### Design-Patterns critic — verdict: harden

1. **[block] Stale mint-import location** — see Coverage 1 / Consistency B.
2. **[block] `AC-6` invents `Deduped` variant** — see Coverage 3 / Consistency F.
3. **[block] `ConfidenceGate` collaborator is double-specified.** S6-01 AC-5 wires `confidence_gate` as a ctor kwarg; the draft said "Introduce `class ConfidenceGate` … Land at confidence_gate.py" without saying "this story lands the *type*; S6-01's ctor already accepts it." Reconcile.
4. **[harden] `HarvestSkipped.reason` should be typed `Literal[...]`** — Open/Closed at the source.
5. **[harden] Outline §5 workflow-context hand-wave** — pick one shape.
6. **[nit] No `_emit` helper.** Rule of three not met for 2 emit sites — explicitly note "don't extract."

**Design-pattern opportunities elevated to ACs:**

- **Pure `harvest_eligibility(outcome) -> HarvestEligibility` projection** (mirrors S6-01's `transform_from_plan` precedent; functional core / imperative shell; rule-of-three met — 4 variants + assert_never).
- **`ConfidenceGate.clauses` enumerable observable** (Specification pattern's named-clauses requirement per ADR-04-0009 §Tradeoffs row 6) — including the "removing a clause changes the truth table" structural property.
- **Idempotence via deterministic-ID pre-check** using S4-06's `_solved_example_id_for(...)` + `store.contains(id)` — replaces the phantom `Deduped` variant.

**Opportunities deliberately rejected:**

- **Strategy/DI for `capability_minter`** — Phase 5 supersedes by import-swap (ADR-04-0009 §Decision); premature pluggability is itself a Rule-2 anti-pattern.
- **`_emit(...)` helper** — Rule of three not met for two emit sites; S6-01 reconciliation precedent.
- **Sub-pipeline extraction for `on_validated` body** — three steps; Rule of three not met.

**Recommendation on mint-import routing:** extend S4-06's `[tool.importlinter]` `ignore_imports` with one row `codegenie.fallback.tier -> codegenie.rag._capability_mint`. Simpler than introducing a `harvest_solved_example` helper in `ingest.py` for one caller; mirrors S4-06's existing pattern; Phase 5's swap trims this row in the same diff.

**Recommendation on workflow-context shape:** add `PostValidationContext` as a keyword-only `on_validated` argument carrying the 11 needed fields. Keeps `FallbackTier` stateless (S6-01 invariant) and additive-only on the orchestrator's call shape. `plan_proposal` lives on `PostValidationContext` rather than amending S1-03's `AppliedFromLlm` (S1-03 is HARDENED; additive amendment is a separate concern).

## Conflict resolutions (priority: Consistency > Coverage > Test-Quality > Design-Patterns)

- **Consistency E (TrustOutcome.confidence) vs Coverage 5 (skip-reason set):** Shipped code wins. Keep `Literal["high","degraded"]`; rewrite gate parametrize and skip-reason projection (`confidence != "high" → "low_confidence"`). ADR-04-0009 + phase-arch text need a one-line amendment in a separate PR. Surfaced as Rule-7 conflict in Notes-for-implementer.
- **Consistency B (mint location) vs Design-Patterns recommendation (extend contract) vs Coverage 1 (wrong import path):** Extend contract — single-line additive change to S4-06's contract; mirrors the existing pattern; Phase 5's mint-swap removes the row. Alternative routing-through-helper rejected (one caller; Rule 2).
- **Consistency C (signature) vs S6-01 stateless invariant:** Widen `on_validated` signature additively with keyword-only `context: PostValidationContext`. Preserves both arch's two-positional control-flow contract and S6-01's stateless invariant.
- **Coverage 11 (`Refused` reaches `on_validated`?) vs eligibility-first dispatch:** Run `harvest_eligibility` as step 1; `Refused` returns `NotEligible(reason="outcome_not_harvestable")`. Defensive behavior, not an exception. Documented in AC-7.
- **Design-Patterns 3 (`ConfidenceGate` double-specified) vs S6-01:** This story lands the *type definition* at `confidence_gate.py`; S6-01's ctor parameter typed against it; `on_validated` uses `self._confidence_gate.passes(trust)`. Pinned in AC-3.
- **Coverage 5 + Consistency G + Design-Patterns 4 (closed reason set):** Pin `Literal["low_confidence", "trust_failed", "outcome_not_harvestable", "already_harvested"]` on the registered `HarvestSkipped.reason` field. ADR-04-0009 amendment in a separate PR enumerates the set; Pydantic Literal enforces it at construction.

## Edits applied

Full diff in the story file's `Validation notes` block. Summary:

- **ACs strengthened/added — 17 total** covering: signature widening with `PostValidationContext`, `ConfidenceGate` ctor-injected with named clauses observable, gate parametrize against shipped `["high","degraded"]` literal set, pure `harvest_eligibility(outcome) -> HarvestEligibility` projection, dispatch order pinned (eligibility → gate → idempotence → mint → projection → ingest → emit), deterministic-ID idempotence pre-check (no phantom `Deduped`), pure `_validated_outcome_from(outcome, context)` projection helper, mint-import via the linter-admitted edge, import-linter contract extended in `pyproject.toml`, no-op-when-blocked AC pinning both `mint_spy.assert_not_called()` AND `ingest_spy.assert_not_awaited()`, `HarvestSkipped` registered as `WorkflowInternalEvent` with `event_type` discriminator + closed-set `Literal` reasons, `SolvedExampleHarvested.solved_example_id` payload identity, mutual-exclusion-and-totality property, contention test with `asyncio.wait_for(30.0)` and observable per-key store behavior, `make check`/`mypy --strict`/`make lint-imports` green.

- **TDD plan rewritten:** fixed `e.kind` → `e.event_type`; truth-table parametrize uses shipped `["high","degraded"]`; added `_TrustPassed`/`_HighConfidence` isolation tests + "removing a clause changes the truth table" structural property; added AST-walking test forbidding inline `BoolOp(And)` on `trust.passed`/`trust.confidence` inside `on_validated` body; added `harvest_eligibility` exhaustive variant test; rewrote idempotence test against deterministic-id pre-check; integration test wraps `asyncio.gather` in `asyncio.wait_for(30.0)` with distinct + identical key arms; added Hypothesis property for mutual-exclusion + totality + closed-set reason; added `HarvestSkipped` round-trip + closed-set rejection tests in `tests/unit/plugins/test_events.py`; amended `tests/fence/test_phase4_capability_mint_scope.py` for the two-row `ignore_imports` shape + `_ALLOWED_IMPORTERS` extension; replaced bare-Ellipsis `AppliedFromRecipe(...)` with factory-builder references; replaced broken `side_effect = AssertionError(...)` pattern with `mint_spy.assert_not_called()` + `ingest_spy.assert_not_awaited()`.

- **Implementation outline expanded:** explicit dispatch order, `skip_reason_for(trust)` pure helper, deterministic-id pre-check sequencing (build `tentative_validated` → hash → contains check → mint), event registration following S4-06's mirror pattern, contract extension verification, Rule-7 surfacing.

- **Files-to-touch widened:** added `post_validation_context.py`, `confidence_gate.py`, fallback `__init__.py`, two new test fixture modules, the events.py registration, the `pyproject.toml` import-linter row, the amended fence test.

- **Notes-for-implementer expanded:** Module-Boundary-not-Capability reminder; AST-checked gate-pattern enforcement; dispatch-order rationale; `asyncio.Lock` double-lock warning; Rule-7 surfacing for `TrustOutcome.confidence` drift; Rule-7 surfacing for `on_validated` signature widening (S6-01 stub compat); Rule-8 surfacing for `SolvedExampleStore.contains` precondition; Open/Closed second-knob seam; deterministic-id pre-check as load-bearing idempotence mechanism.

## Conflicts surfaced to implementer (Global Rule 7 — do not silently blend)

1. **`TrustOutcome.confidence` literal set:** shipped `["high", "degraded"]` vs ADR-04-0009 / phase-arch text `["high", "medium", "low"]`. Resolution: honor shipped; amend ADR + arch in a separate one-line PR; do NOT widen the type.
2. **`on_validated` signature widening:** arch line 813 says `(outcome, trust)`. We widen additively with keyword-only `context: PostValidationContext`. S6-01's stub admits this (only asserts `NotImplementedError`); verify before committing. Orchestrator callsite needs to construct `PostValidationContext` — that's the same PR.
3. **`SolvedExampleStore.contains(sid) -> bool`** — required for AC-8's idempotence pre-check. If S4-03 didn't ship this surface, surface as a blocking precondition; do NOT silently widen S4-03 from inside S6-03.
4. **`PlanOutcome.AppliedFromLlm.plan_proposal`** — currently absent from the S1-03 variant. We carry `plan_proposal` on `PostValidationContext` to avoid touching S1-03. If a later phase needs `plan_proposal` on the variant, that's an additive S1-03 amendment, not an S6-03 concern.
5. **Import-linter contract extension:** S4-06's contract is extended additively with one row. S4-06 AC-6 explicitly forbade adding future `codegenie.gates.*` ignores prematurely; the new `codegenie.fallback.tier` row is real (not forward-allocated) and lands the moment `tier.py` actually imports the mint.

## Final verdict

**HARDENED.** Story now constrains a correct implementation: every AC is individually verifiable; the dispatch-order AC removes the "emit-before-ingest", "mint-on-blocked-branch", and "silent-drop-under-contention" mutation classes; the named-clauses AC + AST guard removes the "inline `if` ladder" Specification-pattern bypass; the deterministic-id pre-check replaces the phantom `Deduped` variant with a real, S4-06-compatible idempotence mechanism; the property test catches mutual-exclusion / totality / closed-set-reason mutations the parametrize misses. Five cross-phase conflicts surfaced to the implementer rather than silently averaged. The hardened story is consistent with every load-bearing precondition shipped by S6-01 HARDENED, S4-06 HARDENED, and the live Phase-3 runtime types (`TrustOutcome.confidence`, `WorkflowInternalEvent` discriminator shape).
