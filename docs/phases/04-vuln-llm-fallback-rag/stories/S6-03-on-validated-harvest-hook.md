# Story S6-03 — `FallbackTier.on_validated` harvest hook with confidence gate

**Step:** Step 6 — Compose FallbackTier + register typecheck.typescript SignalKind + integration
**Status:** HARDENED
**Effort:** M
**Depends on:** S6-01 (FallbackTier shell + ctor-injected `confidence_gate`), S4-06 HARDENED (`ingest_solved_example` keyword-only, `_phase4_local_capability_mint` in `codegenie.rag._capability_mint`, `SolvedExampleHarvested` event registered)
**ADRs honored:** ADR-0009 (inline auto-harvest gated by `TrustOutcome.passed AND confidence == "high"`; Module Boundary not Capability), ADR-0004 (`PlanOutcome` wraps `RecipeOutcome` — never widened)

## Validation notes

Validated: 2026-05-22
Verdict: **HARDENED**
Findings addressed: 23 (8 block, 11 harden, 4 nit) across Coverage / Test-Quality / Consistency / Design-Patterns critics.

Material changes applied (full audit log in `_validation/S6-03-on-validated-harvest-hook.md`):

- **Shipped `TrustOutcome.confidence` is `Literal["high", "degraded"]`, not `["high", "medium", "low"]` (block).** Verified directly against `src/codegenie/transforms/outcomes.py:403`. ADR-04-0009 / phase-arch §Edge-case 18 talk about `"medium"`/`"low"` — that's design-doc drift. Tests now parametrize over the shipped `["high", "degraded"]` set; the gate is `passed AND confidence == "high"`; `"degraded"` maps to `HarvestSkipped(reason="low_confidence")`. Surfaced as Rule-7 conflict in Notes-for-implementer with a one-line ADR-04-0009 amendment item.
- **Mint module is `codegenie.rag._capability_mint`, not `codegenie.rag.ingest` (block).** S4-06 HARDENED (AC-5/AC-6/AC-7) put the mint in a private module with a strict import-linter contract: only `codegenie.rag.ingest` may import it. S6-03 must extend `[tool.importlinter]` `ignore_imports` with one new edge `codegenie.fallback.tier -> codegenie.rag._capability_mint`; test scaffolding patches the symbol at its real location.
- **`ingest_solved_example` is keyword-only and takes `ValidatedPlanOutcome` (block).** S4-06 AC-2 pins `(*, outcome: ValidatedPlanOutcome, store, embedder, capability) -> SolvedExampleId`. The original story called it positionally with a `PlanOutcome`. `on_validated` now explicitly projects `(PlanOutcome.AppliedFromLlm, PostValidationContext) -> ValidatedPlanOutcome` via a pure helper before the call.
- **`SolvedExampleHarvestedDeduped` is a phantom event (block).** S4-06 ships `ingest_solved_example -> SolvedExampleId` (no sum return). Replaced with deterministic-ID pre-check using S4-06's `_solved_example_id_for(...)` + `store.contains(id)` — caller-side idempotence detection emitting `HarvestSkipped(reason="already_harvested")`.
- **`HarvestSkipped` event registration was missing (block).** S4-06's Out-of-scope explicitly defers registration to S6-03. AC-13 now lands it in `src/codegenie/plugins/events.py` as a `WorkflowInternalEvent` variant with `event_type: Literal["harvest_skipped"]` and `reason: Literal[...]` closed set.
- **`on_validated` signature cannot reach `ValidatedPlanOutcome` from `(outcome, trust)` alone (block).** Eight fields needed by `ValidatedPlanOutcome` are not on `PlanOutcome.AppliedFromLlm`. Signature widened additively to `on_validated(outcome, trust, *, context: PostValidationContext)`. `FallbackTier` stays stateless (S6-01 invariant); the orchestrator stamps `PostValidationContext` per validated run.
- **Event discriminator field is `event_type` with snake-case literal values (block).** Confirmed against `src/codegenie/plugins/events.py:166–465`. Tests now use `e.event_type == "solved_example_harvested"` and `"harvest_skipped"`; `e.kind` was the wrong field.
- **`ConfidenceGate` is ctor-injected per S6-01 AC-5 (harden).** Story no longer "introduces" the gate inside `on_validated`. AC-3 pins `self._confidence_gate.passes(trust)` as the call site; the *named-clauses* observability (`_TrustPassed`, `_HighConfidence`) survives as a Specification-pattern AC against ADR-04-0009 §Tradeoffs row 6.
- **Pure `harvest_eligibility(outcome) -> HarvestEligibility` projection (harden).** Mirrors S6-01's `transform_from_plan` precedent — functional core / imperative shell. Rule-of-three met (four `PlanOutcome` variants + `assert_never`). Exhaustive variant test runs without standing up `FallbackTier`.
- **TDD plan made mutation-resistant.** Fixed: (a) `e.kind` → `e.event_type`; (b) added `assert_awaited_once_with(...)` payload-identity assertions; (c) added `mint_spy.assert_not_called()` to gate-blocks tests; (d) added timeout wrapper to the contention integration test; (e) added the mutual-exclusion-and-totality property test; (f) removed the broken `Deduped`-variant idempotence test.
- **Skip-reason set pinned as `Literal[...]` (harden).** Closed set `{"low_confidence", "trust_failed", "outcome_not_harvestable", "already_harvested"}`. ADR-04-0009 §Consequences amendment item recorded in Notes.

Cross-phase conflicts surfaced (Global Rule 7 — do not silently blend):

1. **`TrustOutcome.confidence` literal set:** shipped `["high", "degraded"]` vs ADR-04-0009 / phase-arch text `["high", "medium", "low"]`. Resolution adopted here: keep shipped. Amend ADR-04-0009 §Consequences + phase-arch Edge-case 18 with a one-line correction in the same PR.
2. **`on_validated` signature widening:** arch line 813 says `on_validated(outcome, trust)`. We widen additively with a keyword-only `context: PostValidationContext`. S6-01's stub (which only asserts `NotImplementedError`) admits the widening; verify before committing.
3. **`PlanOutcome.AppliedFromLlm.plan_proposal`:** the LLM-emitted plan must be reachable for harvesting. We carry `plan_proposal` on `PostValidationContext` rather than amending S1-03's `AppliedFromLlm` variant. If a later phase wants `plan_proposal` on the variant itself, that's an additive S1-03 amendment, not an S6-03 concern.

## Context

Roadmap exit criterion #2 — "Re-running the same case hits RAG, not LLM, and produces an equivalent fix at lower cost" — requires that the solved-example store **contains** the harvested outcome by the time the second workflow runs. The critic surfaced (`critique.md §"[B] §4"`) that operator-CLI-only harvest meets the criterion only by test scaffolding; unconditional inline harvest poisons the corpus.

[ADR-04-0009](../ADRs/0009-inline-auto-harvest-confidence-gate.md) threads the needle: inline harvest **wired into `FallbackTier.on_validated(outcome, trust, *, context)`** firing **iff** `trust.passed AND trust.confidence == "high"`. Capability is `SolvedExampleWriteCapability` minted via the private-module factory `_phase4_local_capability_mint(workflow_id, chain_head)` at `src/codegenie/rag/_capability_mint.py` (interim shim — Phase 5 supersedes). The harvest gate is a *named* `ConfidenceGate.passes(trust)` Specification — testable in isolation; future second-knob amendments are additive AND-clauses.

S6-01 stubbed `on_validated` raising `NotImplementedError` and wired `confidence_gate: ConfidenceGate` as a keyword-only ctor collaborator. **S4-06 (HARDENED 2026-05-22) shipped the writer surface and capability boundary** with a stricter shape than the original S6-03 draft assumed: the writer is silent, keyword-only, and consumes a `ValidatedPlanOutcome` bridge type. This story lands the production-behavior hook on top of those preconditions, the `HarvestSkipped` event registration for the gated-out path, the import-linter contract extension that admits `codegenie.fallback.tier` as a permitted importer of `_capability_mint`, and the unit + integration tests pinning the gate / dispatch / idempotence / contention semantics. The roadmap-exit-criterion E2E test (`tests/integration/test_phase4_e2e_replay_lands_rag.py`) is S7-07 and consumes this hook.

## References — where to look

- **Architecture:** [phase-arch-design.md §Control flow lines 813–818](../phase-arch-design.md) (`on_validated` steps 10–12); §Component 1 internal structure (`on_validated` part); §Component 10 — `SolvedExampleWriter` (capability mint); §Edge case row 18 (harvest gating).
- **Phase ADRs:** [ADR-04-0009](../ADRs/0009-inline-auto-harvest-confidence-gate.md) (the whole story is this ADR's implementation; pattern fit §Specification + Module-Boundary); [ADR-04-0004](../ADRs/0004-plan-outcome-wraps-recipe-outcome.md) (`PlanOutcome` is what `on_validated` matches on).
- **Production ADRs:** [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md) (`TrustOutcome.passed` + `confidence` shape — what the gate reads); [production ADR-0034](../../../production/adrs/0034-event-sourcing-canonical-primitive.md) (`SolvedExampleHarvested` / `HarvestSkipped` audit events).
- **Source design:** [final-design.md §Component 9 — SolvedExampleWriter](../final-design.md); §Departures from all three inputs item 4 (inline + confidence gate); §Goal "Inline auto-harvest gate".
- **High-level impl:** [High-level-impl.md §Step 6](../High-level-impl.md) Features delivered (`on_validated` bullet); §Step 4 risks (chromadb writer contention; `loop.run_in_executor` mitigation).
- **HARDENED sibling stories (live contracts):**
  - `_validation/S6-01-fallback-tier-pipeline.md` — `FallbackTier.__init__(retriever, leaf, budget, fence, canary, provenance, event_log, *, prompt_builder, harvester, confidence_gate)`; `FallbackTier` is stateless.
  - `S4-06-ingest-capability-mint.md` (HARDENED) — `ingest_solved_example(*, outcome: ValidatedPlanOutcome, store, embedder, capability) -> SolvedExampleId` (keyword-only, silent); `_phase4_local_capability_mint(*, workflow_id, chain_head)` at `src/codegenie/rag/_capability_mint.py`; `pyproject.toml [tool.importlinter]` contract `"ADR-0016: phase4 solved-example mint module is scoped"`; `SolvedExampleHarvested` registered with `event_type: Literal["solved_example_harvested"]`; `_solved_example_id_for(*, outcome, embedding_model) -> SolvedExampleId` deterministic-id helper.
- **Shipped runtime types (load-bearing):**
  - `src/codegenie/transforms/outcomes.py:391–403` — `TrustOutcome.confidence: Literal["high", "degraded"]` (NOT `["high","medium","low"]`).
  - `src/codegenie/plugins/events.py:166–465` — every `WorkflowInternalEvent` variant uses `event_type: Literal["snake_case"]` as the discriminator; `_INTERNAL_CLASSES` tuple + `__all__` are the registration surface; `_INTERNAL_ADAPTER` provides round-trip validation.
  - `src/codegenie/types/identifiers.py` — `WorkflowId`, `ChainHead`, `BlobDigest`, `CveId`, `TaskClassId`, `Language` newtypes; `PackageManager` Literal.
- **Existing code (will be created or extended):** `src/codegenie/fallback/tier.py` (S6-01 stub); `src/codegenie/rag/ingest.py` + `src/codegenie/rag/_capability_mint.py` (S4-06); `src/codegenie/fallback/plan_outcome.py` (S1-03).

## Goal

Implement `FallbackTier.on_validated(outcome: PlanOutcome, trust: TrustOutcome, *, context: PostValidationContext) -> None` so that on `trust.passed AND trust.confidence == "high"` and `outcome` being `AppliedFromLlm`, the tier:

1. consults the deterministic-ID idempotence pre-check;
2. mints `SolvedExampleWriteCapability` via `_phase4_local_capability_mint(workflow_id=context.workflow_id, chain_head=context.chain_head)`;
3. projects `(outcome, context) -> ValidatedPlanOutcome` via a pure helper;
4. calls the silent keyword-only `ingest_solved_example(*, outcome=validated, store=self._store, embedder=self._embedder, capability=capability)`;
5. emits `SolvedExampleHarvested(solved_example_id=...)` on success;

otherwise emits exactly one `HarvestSkipped(reason: Literal[...])` event capturing the closed-set reason — and never invokes mint, projection, or ingest.

## Acceptance criteria

### Signature and surface

- [ ] **AC-1 — Widened keyword-only signature.** `src/codegenie/fallback/tier.py` exports:
    ```python
    async def on_validated(
        self,
        outcome: PlanOutcome,
        trust: TrustOutcome,
        *,
        context: PostValidationContext,
    ) -> None
    ```
    `context` is keyword-only. `mypy --strict src/codegenie/fallback/tier.py` clean.

- [ ] **AC-2 — `PostValidationContext` shape pinned.** `src/codegenie/fallback/post_validation_context.py` defines a frozen `BaseModel` (`model_config = ConfigDict(frozen=True, extra="forbid")`) with exactly these typed fields:
    ```python
    workflow_id:           WorkflowId
    chain_head:            ChainHead
    advisory_digest:       BlobDigest
    cve_id:                CveId
    task_class:            TaskClassId
    language:              Language
    build_system:          PackageManager
    transform_digest:      BlobDigest
    trust_outcome_digest:  BlobDigest
    query_text:            str
    plan_proposal:         PlanProposal
    ```
    No `dict[str, Any]`; no untyped escape hatch. The class is exported from `src/codegenie/fallback/__init__.py` so the Phase-3 orchestrator can construct it.

### Specification gate (ctor-injected; named clauses)

- [ ] **AC-3 — `on_validated` reads the ctor-injected `ConfidenceGate`.** The body contains `if not self._confidence_gate.passes(trust): ...` — never constructs `ConfidenceGate` locally and never inlines a `trust.passed and trust.confidence == "high"` ladder. AST-walking test in `tests/unit/fallback/test_on_validated.py` (a) confirms no `BoolOp(And)` over `trust.passed` and `trust.confidence` appears inside `tier.py`'s `on_validated` body, and (b) confirms the body references `self._confidence_gate.passes`.

- [ ] **AC-4 — `ConfidenceGate` exposes named, separable clauses.** `src/codegenie/fallback/confidence_gate.py` defines:
    ```python
    class _TrustPassed:
        def is_satisfied_by(self, trust: TrustOutcome) -> bool: return trust.passed
    class _HighConfidence:
        def is_satisfied_by(self, trust: TrustOutcome) -> bool: return trust.confidence == "high"
    class ConfidenceGate:
        clauses: Final[tuple[_TrustPassed, _HighConfidence]] = (_TrustPassed(), _HighConfidence())
        def passes(self, trust: TrustOutcome) -> bool:
            return all(c.is_satisfied_by(trust) for c in self.clauses)
    ```
    `tests/unit/fallback/test_confidence_gate.py` asserts (a) each clause's truth table in isolation, (b) `ConfidenceGate.clauses` is enumerable and contains exactly the two named instances in order, (c) `passes` ≡ AND-composition: removing `_HighConfidence` from a hand-built `ConfidenceGate` lets `("high"|"degraded")` both pass; removing `_TrustPassed` lets `(False, "high")` pass. Each "removing a clause changes the truth table" assertion is the structural property that an inlined `if` ladder cannot fake.

- [ ] **AC-5 — Gate parametrize uses the shipped `TrustOutcome.confidence` literal set.** Table-driven test exercises every constructible `(passed, confidence)` pair against `src/codegenie/transforms/outcomes.py:403`'s `Literal["high", "degraded"]`:

    | passed | confidence  | `gate.passes` |
    |--------|-------------|---------------|
    | `True` | `"high"`    | `True`        |
    | `True` | `"degraded"`| `False`       |
    | `False`| `"high"`    | `False`       |
    | `False`| `"degraded"`| `False`       |

    The test fails-loud if a future code change widens `TrustOutcome.confidence` beyond `Literal["high","degraded"]` without surfacing here (drives the Rule-7 surface noted above).

### Outcome dispatch via pure helper

- [ ] **AC-6 — Pure `harvest_eligibility(outcome) -> HarvestEligibility` projection.** New module-level function in `src/codegenie/fallback/tier.py` (co-located precedent: S6-01's `transform_from_plan`):
    ```python
    HarvestEligibility = Eligible | NotEligible
    class Eligible(BaseModel):
        kind: Literal["eligible"] = "eligible"
    class NotEligible(BaseModel):
        kind: Literal["not_eligible"] = "not_eligible"
        reason: Literal["outcome_not_harvestable"] = "outcome_not_harvestable"

    def harvest_eligibility(outcome: PlanOutcome) -> HarvestEligibility:
        match outcome:
            case AppliedFromLlm():        return Eligible()
            case AppliedFromRecipe():     return NotEligible()
            case RagOnlyApplicable():     return NotEligible()
            case Refused():               return NotEligible()
            case _ as never:              assert_never(never)
    ```
    `tests/unit/fallback/test_harvest_eligibility.py` exhaustively tests every `PlanOutcome` variant + (via `pytest.raises(TypeError)` against `mypy --strict`) the `assert_never` arm. The pure helper requires no `FallbackTier` instance.

- [ ] **AC-7 — `on_validated` dispatch order: eligibility → gate → idempotence → mint → ingest → emit.** Order is fixed and observable:
    1. `eligibility = harvest_eligibility(outcome)` — if `NotEligible`, emit `HarvestSkipped(reason="outcome_not_harvestable")` and return; no further work.
    2. `if not self._confidence_gate.passes(trust)` — emit `HarvestSkipped(reason=skip_reason_for(trust))` (closed-set projection: `passed=False` → `"trust_failed"`; `confidence != "high"` → `"low_confidence"`) and return; no mint.
    3. Compute deterministic id `sid = _solved_example_id_for(outcome=validated, embedding_model=self._embedder.model_digest())`; if `await self._store.contains(sid)`, emit `HarvestSkipped(reason="already_harvested")` and return; no mint.
    4. Mint `capability = _phase4_local_capability_mint(workflow_id=context.workflow_id, chain_head=context.chain_head)`.
    5. `validated = _validated_outcome_from(outcome=outcome, context=context)` (pure projection — see AC-9).
    6. `actual_sid = await ingest_solved_example(outcome=validated, store=self._store, embedder=self._embedder, capability=capability)` — keyword-only.
    7. Emit `SolvedExampleHarvested(solved_example_id=actual_sid, ...)` **only after** ingest returns successfully.

    A test parametrized across each rejection branch asserts mint and ingest are *not* called for that branch (see AC-12).

### Idempotence (deterministic-ID pre-check; no phantom `Deduped` variant)

- [ ] **AC-8 — Idempotence via caller-side pre-check.** Two `on_validated` calls with identical `(outcome, context)` yield exactly two events: the first is `SolvedExampleHarvested`, the second is `HarvestSkipped(reason="already_harvested")`. `store.add` is invoked exactly once across both calls (asserted by call-count on the store spy). No `SolvedExampleHarvestedDeduped` event is invented; reason set stays at the closed four. `tests/unit/fallback/test_on_validated_idempotent.py` pins this.

### Pure projection helper

- [ ] **AC-9 — Pure `_validated_outcome_from(outcome, context) -> ValidatedPlanOutcome` projection.** Module-level helper in `src/codegenie/fallback/tier.py`:
    ```python
    def _validated_outcome_from(
        *,
        outcome: AppliedFromLlm,
        context: PostValidationContext,
    ) -> ValidatedPlanOutcome
    ```
    Builds `ValidatedPlanOutcome` from `outcome.response_id` + every field on `context`. The function is `mypy --strict` clean and accepts ONLY `AppliedFromLlm` (compile-time guard — callers prove they passed the eligibility filter before invoking). `tests/unit/fallback/test_validated_outcome_projection.py` asserts (a) every required `ValidatedPlanOutcome` field is populated; (b) `mypy --strict` rejects `_validated_outcome_from(outcome=AppliedFromRecipe(...), context=...)` (recorded as a `tests/unit/types/test_phase4_identifiers_mypy_negative.py`-style negative test).

### Capability mint and import boundary

- [ ] **AC-10 — Mint imports from the private module via the linter-admitted edge.** `tier.py` contains `from codegenie.rag._capability_mint import _phase4_local_capability_mint` (the symbol is keyword-only `(*, workflow_id, chain_head)` per S4-06 AC-5). The mint is called keyword-only inside `on_validated`.

- [ ] **AC-11 — Import-linter contract extended.** `pyproject.toml [tool.importlinter.contracts]` row `name = "ADR-0016: phase4 solved-example mint module is scoped"` gains one new `ignore_imports` row:
    ```toml
    ignore_imports = [
      "codegenie.rag.ingest -> codegenie.rag._capability_mint",
      "codegenie.fallback.tier -> codegenie.rag._capability_mint",
    ]
    ```
    `tests/fence/test_phase4_capability_mint_scope.py` (from S4-06 AC-7) is amended in-place: the contract-shape assertion expects the two-row `ignore_imports`; the AST scope test exempts `src/codegenie/fallback/tier.py`. `make lint-imports` green on the production tree. A planted-violation test (the S4-06-style temp file under `src/codegenie/`) still trips the contract by name.

### No-op when blocked

- [ ] **AC-12 — Mint and ingest are NOT called when any precondition fails.** Test fixture: `mint_spy = MagicMock(...)`; `ingest_spy = AsyncMock(...)`. Parametrized over each rejection branch (outcome-not-harvestable, trust-failed, low-confidence, already-harvested):

    ```python
    mint_spy.assert_not_called()
    ingest_spy.assert_not_awaited()
    assert len(events_of(capturing_event_log, "solved_example_harvested")) == 0
    assert len(events_of(capturing_event_log, "harvest_skipped")) == 1
    ```

    `events_of(log, event_type)` filters on `e.event_type == event_type` — the canonical Pydantic discriminator (NOT `e.kind`). Closed-set `reason` field-membership asserted per branch.

### Event registration

- [ ] **AC-13 — `HarvestSkipped` registered as `WorkflowInternalEvent` variant.** `src/codegenie/plugins/events.py` adds:
    ```python
    class HarvestSkipped(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")
        event_type: Literal["harvest_skipped"] = "harvest_skipped"
        event_id: EventId
        workflow_id: WorkflowId
        timestamp: datetime
        reason: Literal["low_confidence", "trust_failed", "outcome_not_harvestable", "already_harvested"]
        plan_outcome_kind: Literal["llm", "recipe", "rag_only", "refused"]
    ```
    Wired into the `WorkflowInternalEvent` discriminated union + `_INTERNAL_CLASSES` tuple + `__all__`. `tests/unit/plugins/test_events.py` asserts (a) the discriminator mapping contains `"harvest_skipped"`, (b) `_INTERNAL_ADAPTER.validate_python({"event_type": "harvest_skipped", ...})` round-trips, (c) Pydantic rejects `reason="anything_else"` at construction time (closed-set enforcement).

- [ ] **AC-14 — `SolvedExampleHarvested.solved_example_id` matches `ingest_solved_example` return.** Test sets `ingest_spy.return_value = SolvedExampleId("pinned-id-abc")` and asserts the emitted `SolvedExampleHarvested.solved_example_id == "pinned-id-abc"` — payload identity, not type-presence.

### Property: mutual exclusion and totality

- [ ] **AC-15 — Exactly one terminal event per `on_validated` call.** Property test in `tests/property/test_on_validated_mutual_exclusion.py` (Hypothesis):
    ```python
    @given(outcome=closed_plan_outcome_strategy(), trust=trust_outcome_strategy())
    @pytest.mark.asyncio
    async def test_exactly_one_terminal_event(outcome, trust, fresh_tier):
        await fresh_tier.on_validated(outcome, trust, context=fresh_context())
        terminal = [e for e in fresh_tier._event_log.recorded
                    if e.event_type in {"solved_example_harvested", "harvest_skipped"}]
        assert len(terminal) == 1
    ```
    Catches double-emit and no-emit mutations the parametrize misses.

### Contention

- [ ] **AC-16 — Store contention under `asyncio.gather` does not deadlock and does not silently drop.** `tests/integration/test_phase4_on_validated_under_lock.py` invokes `on_validated` twice via `asyncio.gather` with `asyncio.wait_for(..., timeout=30.0)` (matching High-level-impl Step 4 §Risks contention budget). Asserts (a) both calls return within timeout; (b) for two distinct `(outcome, context)` pairs, `store.add` was invoked exactly twice and two `solved_example_harvested` events landed with distinct `solved_example_id`; (c) for two identical pairs, exactly one `store.add` invocation, one `solved_example_harvested`, one `harvest_skipped(reason="already_harvested")`. Composes with S4-08 / Gap 3.

### Determinism, lint, type

- [ ] **AC-17 — `make check`, `mypy --strict`, `make lint-imports` all green.** Including the planted-violation test still tripping the renamed two-row contract.

## Implementation outline

1. **Land `PostValidationContext`** at `src/codegenie/fallback/post_validation_context.py` — frozen Pydantic with the 11 typed fields per AC-2. Export from `codegenie.fallback.__init__`.
2. **Land `ConfidenceGate`** at `src/codegenie/fallback/confidence_gate.py` — `_TrustPassed`, `_HighConfidence`, and `ConfidenceGate` with the `clauses` tuple exposed for audit (AC-4). Pure; no event-log dep.
3. **Land `HarvestEligibility`** sum + `harvest_eligibility(outcome)` pure helper as module-level definitions in `src/codegenie/fallback/tier.py` (co-located like S6-01's `transform_from_plan`). Exhaustive `match` with `assert_never` arm.
4. **Land `_validated_outcome_from(*, outcome, context)`** pure helper in `tier.py` — accepts `AppliedFromLlm` only (mypy-strict gate at compile time). Build `ValidatedPlanOutcome` field-by-field from `context` + `outcome.response_id`.
5. **Replace `NotImplementedError` stub** in `FallbackTier.on_validated` with the body. Dispatch order (AC-7): eligibility → gate → idempotence pre-check → mint → projection → ingest → emit. One emit per branch; mint never runs on a blocked branch.
6. **`skip_reason_for(trust)` projection** — pure module-level helper: `passed=False → "trust_failed"`; `confidence != "high" → "low_confidence"`; (these are *closed* — if both fail, `"trust_failed"` wins; pin in AC-7 test).
7. **Idempotence pre-check.** `sid_candidate = _solved_example_id_for(outcome=tentative_validated, embedding_model=self._embedder.model_digest())` — note this requires building `tentative_validated` from `outcome + context` first (use `_validated_outcome_from`). If `await self._store.contains(sid_candidate)`, emit `HarvestSkipped(reason="already_harvested")` and return *before* minting capability. If `SolvedExampleStore.contains` is not on the S4-03 surface, surface as a Rule-7 blocker; do not invent.
8. **`HarvestSkipped` event registration.** Add the Pydantic variant to `src/codegenie/plugins/events.py`; wire `WorkflowInternalEvent` union + `_INTERNAL_CLASSES` + `__all__`. Mirror S4-06 AC-9's `SolvedExampleHarvested` row exactly.
9. **Import-linter contract extension.** One row added to S4-06's `ignore_imports`. Amend `tests/fence/test_phase4_capability_mint_scope.py`'s `_contracts()`-asserted shape from a one-row list to a two-row list; amend the AST scope test's exempt set to include `src/codegenie/fallback/tier.py`. Run `make lint-imports`.
10. **Tests** (see TDD plan): unit, property, integration. Confirm `pytest.mark.asyncio` + `asyncio_mode = "auto"` (Phase-0 default).
11. **Surface Rule-7 conflicts** (ADR-04-0009 + arch text talk about `"medium"`/`"low"`; the shipped type is `["high","degraded"]`). Open a separate one-line PR amending ADR-04-0009 §Consequences and phase-arch Edge-case 18; cross-reference from the story's _attempts log. **Do not** widen `TrustOutcome.confidence` — production-ADR-0008 is the gate; widening has cross-phase blast radius.

## TDD plan — red / green / refactor

### Red — write the failing tests first

#### `tests/unit/fallback/test_confidence_gate.py`

```python
import pytest
from codegenie.fallback.confidence_gate import (
    ConfidenceGate, _TrustPassed, _HighConfidence,
)
from codegenie.transforms.outcomes import TrustOutcome


def _trust(passed: bool, confidence: str) -> TrustOutcome:
    return TrustOutcome(passed=passed, failing=[], signals=[], confidence=confidence)  # type: ignore[arg-type]


@pytest.mark.parametrize("passed, confidence, expected", [
    (True,  "high",     True),
    (True,  "degraded", False),
    (False, "high",     False),
    (False, "degraded", False),
])
def test_gate_truth_table_against_shipped_literal_set(passed, confidence, expected):
    """TrustOutcome.confidence is Literal['high','degraded'] (outcomes.py:403).
    The original ADR-04-0009 / phase-arch text talked about 'medium'/'low' — drift.
    This test pins the shipped reality; a future widening of the Literal must
    update this table loudly (Rule 7)."""
    gate = ConfidenceGate()
    assert gate.passes(_trust(passed, confidence)) is expected


def test_clauses_are_named_and_ordered():
    """ADR-04-0009 §Tradeoffs row 6: composable Specifications must remain
    named and testable; a free-form 'if' ladder violates the pattern."""
    gate = ConfidenceGate()
    assert isinstance(gate.clauses[0], _TrustPassed)
    assert isinstance(gate.clauses[1], _HighConfidence)
    assert len(gate.clauses) == 2


@pytest.mark.parametrize("passed, expected", [(True, True), (False, False)])
def test_trust_passed_clause_in_isolation(passed, expected):
    assert _TrustPassed().is_satisfied_by(_trust(passed, "high")) is expected


@pytest.mark.parametrize("confidence, expected", [("high", True), ("degraded", False)])
def test_high_confidence_clause_in_isolation(confidence, expected):
    assert _HighConfidence().is_satisfied_by(_trust(True, confidence)) is expected


def test_removing_a_clause_changes_truth_table():
    """Structural property an inlined `if` ladder cannot fake: each clause
    is removable, and removing one shifts the truth table on the row that
    clause governs."""
    only_passed = type("OnlyPassed", (ConfidenceGate,), {"clauses": (_TrustPassed(),)})()
    assert only_passed.passes(_trust(True, "degraded")) is True  # without _HighConfidence

    only_confidence = type("OnlyConfidence", (ConfidenceGate,), {"clauses": (_HighConfidence(),)})()
    assert only_confidence.passes(_trust(False, "high")) is True  # without _TrustPassed
```

#### `tests/unit/fallback/test_harvest_eligibility.py`

```python
import pytest
from codegenie.fallback.tier import (
    harvest_eligibility, Eligible, NotEligible,
)
# Variant factories from S1-03 — referenced, not inlined as Ellipsis.
from tests.fixtures.plan_outcome_factories import (
    make_applied_from_llm, make_applied_from_recipe,
    make_rag_only_applicable, make_refused,
)


def test_applied_from_llm_is_eligible():
    """Harvest-eligible outcome — the case the inline-harvest path exists for."""
    eligibility = harvest_eligibility(make_applied_from_llm())
    assert isinstance(eligibility, Eligible)


@pytest.mark.parametrize("outcome_factory", [
    make_applied_from_recipe,        # already in corpus by virtue of the recipe
    make_rag_only_applicable,        # not a new example
    make_refused,                    # never validated, defensive
])
def test_non_llm_outcomes_are_not_eligible(outcome_factory):
    """ADR-04-0004 final-design open question: recipe-applied + RAG-only +
    refused outcomes must not be harvested (corpus-quality invariant)."""
    eligibility = harvest_eligibility(outcome_factory())
    assert isinstance(eligibility, NotEligible)
    assert eligibility.reason == "outcome_not_harvestable"
```

#### `tests/unit/fallback/test_on_validated.py`

```python
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from codegenie.fallback.tier import FallbackTier
from codegenie.transforms.outcomes import TrustOutcome
from tests.fixtures.plan_outcome_factories import (
    make_applied_from_llm, make_applied_from_recipe,
    make_rag_only_applicable, make_refused,
)
from tests.fixtures.post_validation_context_factory import make_context


def _trust(passed=True, confidence="high") -> TrustOutcome:
    return TrustOutcome(passed=passed, failing=[], signals=[], confidence=confidence)  # type: ignore[arg-type]


def _terminal_events(log):
    return [e for e in log.recorded
            if e.event_type in {"solved_example_harvested", "harvest_skipped"}]


@pytest.mark.asyncio
async def test_happy_path_emits_harvested_after_successful_ingest(
    tier_under_test, capturing_event_log, mint_spy, ingest_spy, store_spy,
):
    """ADR-04-0009 production-behavior path. Roadmap exit #2 depends on this.
    Pins payload identity: the emitted SolvedExampleHarvested.solved_example_id
    must equal the id ingest_solved_example returned."""
    ingest_spy.return_value = "pinned-id-abc"
    outcome = make_applied_from_llm()
    context = make_context(workflow_id="wf-1", chain_head="ch-1")

    await tier_under_test.on_validated(outcome, _trust(True, "high"), context=context)

    mint_spy.assert_called_once_with(workflow_id="wf-1", chain_head="ch-1")
    ingest_spy.assert_awaited_once()
    kwargs = ingest_spy.await_args.kwargs
    assert kwargs["store"] is store_spy
    assert kwargs["outcome"].cve_id == context.cve_id
    assert kwargs["outcome"].response_id == outcome.response_id
    assert kwargs["capability"] is mint_spy.return_value
    terminal = _terminal_events(capturing_event_log)
    assert len(terminal) == 1
    assert terminal[0].event_type == "solved_example_harvested"
    assert terminal[0].solved_example_id == "pinned-id-abc"


@pytest.mark.parametrize("trust, expected_reason", [
    (TrustOutcome(passed=True,  failing=[], signals=[], confidence="degraded"),  "low_confidence"),
    (TrustOutcome(passed=False, failing=[], signals=[], confidence="high"),      "trust_failed"),
    (TrustOutcome(passed=False, failing=[], signals=[], confidence="degraded"),  "trust_failed"),
])
@pytest.mark.asyncio
async def test_blocked_gate_skips_with_correct_reason_and_no_mint(
    tier_under_test, capturing_event_log, mint_spy, ingest_spy, trust, expected_reason,
):
    """ADR-04-0009: poisoned-corpus risk bounded — gate must hold AND mint must
    not be called on a blocked branch (gate precedes mint per AC-7)."""
    await tier_under_test.on_validated(
        make_applied_from_llm(), trust, context=make_context(),
    )
    mint_spy.assert_not_called()
    ingest_spy.assert_not_awaited()
    terminal = _terminal_events(capturing_event_log)
    assert len(terminal) == 1
    assert terminal[0].event_type == "harvest_skipped"
    assert terminal[0].reason == expected_reason


@pytest.mark.parametrize("outcome_factory", [
    make_applied_from_recipe,
    make_rag_only_applicable,
    make_refused,
])
@pytest.mark.asyncio
async def test_non_llm_outcomes_skip_before_gate(
    tier_under_test, capturing_event_log, mint_spy, ingest_spy, outcome_factory,
):
    """AC-7 dispatch order: eligibility filter runs BEFORE the gate, so a
    non-LLM outcome with passed=False / confidence='degraded' still receives
    reason='outcome_not_harvestable' (eligibility wins; gate never runs)."""
    await tier_under_test.on_validated(
        outcome_factory(),
        TrustOutcome(passed=False, failing=[], signals=[], confidence="degraded"),  # type: ignore[arg-type]
        context=make_context(),
    )
    mint_spy.assert_not_called()
    ingest_spy.assert_not_awaited()
    terminal = _terminal_events(capturing_event_log)
    assert len(terminal) == 1
    assert terminal[0].reason == "outcome_not_harvestable"


@pytest.mark.asyncio
async def test_no_inline_boolop_in_on_validated_body():
    """AC-3 structural property: `on_validated` reads ctor-injected gate; an
    inline `trust.passed and trust.confidence == "high"` would violate the
    Specification pattern (ADR-04-0009)."""
    import ast, pathlib
    src = pathlib.Path("src/codegenie/fallback/tier.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for fn in ast.walk(tree):
        if isinstance(fn, ast.AsyncFunctionDef) and fn.name == "on_validated":
            for node in ast.walk(fn):
                if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
                    # Forbid `trust.passed and ...` shapes; the gate is `self._confidence_gate.passes(...)`
                    sources = [ast.dump(v) for v in node.values]
                    assert not any("trust" in s and "passed" in s for s in sources), (
                        "on_validated must call self._confidence_gate.passes(trust), "
                        "not inline a BoolOp ladder"
                    )
            return
    raise AssertionError("on_validated not found in tier.py")
```

#### `tests/unit/fallback/test_on_validated_idempotent.py`

```python
import pytest
from tests.fixtures.plan_outcome_factories import make_applied_from_llm
from tests.fixtures.post_validation_context_factory import make_context


@pytest.mark.asyncio
async def test_second_call_skips_with_already_harvested(
    tier_with_real_store, capturing_event_log,
):
    """S4-06 AC-3: _solved_example_id_for is deterministic in identity fields.
    Two calls with the same (outcome, context) hash to the same SolvedExampleId;
    the second consults store.contains and emits HarvestSkipped(already_harvested)
    without calling ingest_solved_example again. NO 'Deduped' return variant —
    that contradicts S4-06's plain-id return."""
    outcome = make_applied_from_llm()
    context = make_context(workflow_id="wf-1", chain_head="ch-1")
    trust = ...  # high+passed; fixture
    store = tier_with_real_store._store

    await tier_with_real_store.on_validated(outcome, trust, context=context)
    await tier_with_real_store.on_validated(outcome, trust, context=context)

    assert store.add.call_count == 1
    types = [e.event_type for e in capturing_event_log.recorded]
    assert types.count("solved_example_harvested") == 1
    skipped = [e for e in capturing_event_log.recorded if e.event_type == "harvest_skipped"]
    assert len(skipped) == 1
    assert skipped[0].reason == "already_harvested"
```

#### `tests/integration/test_phase4_on_validated_under_lock.py`

```python
import asyncio
import pytest


@pytest.mark.asyncio
async def test_concurrent_distinct_calls_both_land_within_budget(tier_with_real_store):
    """High-level-impl Step 4 §Risks: chromadb embedded-mode `add()` may block
    the loop. on_validated wraps it correctly when needed (`loop.run_in_executor`).
    30s budget per-call matches the contention contract."""
    a = tier_with_real_store.on_validated(outcome_a, trust_high, context=ctx_a)
    b = tier_with_real_store.on_validated(outcome_b, trust_high, context=ctx_b)
    await asyncio.wait_for(asyncio.gather(a, b), timeout=30.0)

    store = tier_with_real_store._store
    assert store.add.call_count == 2
    harvested_ids = [
        e.solved_example_id for e in events_of(tier_with_real_store._event_log, "solved_example_harvested")
    ]
    assert len(set(harvested_ids)) == 2


@pytest.mark.asyncio
async def test_concurrent_identical_calls_single_write(tier_with_real_store):
    """Same (outcome, context) twice under gather — exactly one store.add,
    one solved_example_harvested, one harvest_skipped(already_harvested).
    Catches buggy impls that drop one ingest silently (silent-drop mutation)."""
    a = tier_with_real_store.on_validated(outcome, trust_high, context=context)
    b = tier_with_real_store.on_validated(outcome, trust_high, context=context)
    await asyncio.wait_for(asyncio.gather(a, b), timeout=30.0)

    log = tier_with_real_store._event_log
    assert tier_with_real_store._store.add.call_count == 1
    assert len(events_of(log, "solved_example_harvested")) == 1
    skipped = events_of(log, "harvest_skipped")
    assert len(skipped) == 1 and skipped[0].reason == "already_harvested"
```

#### `tests/property/test_on_validated_mutual_exclusion.py`

```python
import pytest
from hypothesis import given, strategies as st
from codegenie.transforms.outcomes import TrustOutcome


_PLAN_OUTCOME_STRATEGY = st.sampled_from([
    make_applied_from_llm, make_applied_from_recipe,
    make_rag_only_applicable, make_refused,
])
_TRUST_STRATEGY = st.builds(
    TrustOutcome,
    passed=st.booleans(), failing=st.just([]), signals=st.just([]),
    confidence=st.sampled_from(["high", "degraded"]),
)


@given(outcome_factory=_PLAN_OUTCOME_STRATEGY, trust=_TRUST_STRATEGY)
@pytest.mark.asyncio
async def test_exactly_one_terminal_event_per_call(outcome_factory, trust, fresh_tier_factory):
    """Mutual exclusion + totality: no double-emit, no missing-emit.
    Closed cross-product is small (4 outcomes × 2 confidence × 2 passed = 16);
    Hypothesis gives near-exhaustive coverage and catches mutations parametrize misses."""
    tier, log = fresh_tier_factory()
    await tier.on_validated(outcome_factory(), trust, context=make_context())
    terminal = [
        e for e in log.recorded
        if e.event_type in {"solved_example_harvested", "harvest_skipped"}
    ]
    assert len(terminal) == 1


@given(outcome_factory=_PLAN_OUTCOME_STRATEGY, trust=_TRUST_STRATEGY)
@pytest.mark.asyncio
async def test_skip_reason_is_always_in_closed_literal_set(outcome_factory, trust, fresh_tier_factory):
    """HarvestSkipped.reason is closed-set; future widening must be explicit
    (Pydantic Literal[...] rejects unknown reasons)."""
    tier, log = fresh_tier_factory()
    await tier.on_validated(outcome_factory(), trust, context=make_context())
    for e in log.recorded:
        if e.event_type == "harvest_skipped":
            assert e.reason in {
                "low_confidence", "trust_failed",
                "outcome_not_harvestable", "already_harvested",
            }
```

#### `tests/unit/plugins/test_events.py` — additions for `HarvestSkipped`

```python
def test_harvest_skipped_round_trips_through_internal_adapter():
    from codegenie.plugins.events import _INTERNAL_ADAPTER, HarvestSkipped
    payload = {
        "event_type": "harvest_skipped",
        "event_id": "evt-1", "workflow_id": "wf-1",
        "timestamp": "2026-05-22T00:00:00Z",
        "reason": "low_confidence",
        "plan_outcome_kind": "llm",
    }
    event = _INTERNAL_ADAPTER.validate_python(payload)
    assert isinstance(event, HarvestSkipped)
    assert event.reason == "low_confidence"


@pytest.mark.parametrize("bad_reason", ["", "weird", "LOW_CONFIDENCE", "anything"])
def test_harvest_skipped_rejects_open_set_reasons(bad_reason):
    from codegenie.plugins.events import _INTERNAL_ADAPTER
    with pytest.raises(Exception):
        _INTERNAL_ADAPTER.validate_python({
            "event_type": "harvest_skipped",
            "event_id": "evt-1", "workflow_id": "wf-1",
            "timestamp": "2026-05-22T00:00:00Z",
            "reason": bad_reason,
            "plan_outcome_kind": "llm",
        })
```

#### `tests/fence/test_phase4_capability_mint_scope.py` — amendment

```python
def test_phase4_mint_contract_shape() -> None:
    contract = _contracts()[CONTRACT]
    assert contract["type"] == "forbidden"
    assert contract["source_modules"] == ["codegenie"]
    assert contract["as_packages"] is True
    assert contract["forbidden_modules"] == ["codegenie.rag._capability_mint"]
    assert contract["ignore_imports"] == [
        "codegenie.rag.ingest -> codegenie.rag._capability_mint",
        "codegenie.fallback.tier -> codegenie.rag._capability_mint",
    ]


# Update _ALLOWED_IMPORTERS set to include fallback/tier.py
_ALLOWED_IMPORTERS: Final[frozenset[str]] = frozenset({
    "src/codegenie/rag/ingest.py",
    "src/codegenie/fallback/tier.py",
})
```

### Green — make it pass

- Land `post_validation_context.py`, `confidence_gate.py`.
- Land `harvest_eligibility(...)`, `_validated_outcome_from(...)`, `skip_reason_for(...)` in `tier.py`.
- Land `HarvestSkipped` in `plugins/events.py` (mirror S4-06's `SolvedExampleHarvested` row exactly).
- Replace `on_validated` stub body per AC-7.
- Extend `pyproject.toml [tool.importlinter]` `ignore_imports`.
- Land variant factories `tests/fixtures/plan_outcome_factories.py` + `tests/fixtures/post_validation_context_factory.py` if S1-03 didn't already.

### Refactor — clean up

- Keep `ConfidenceGate.clauses` separable for future second-knob additions (per-task-class trust gating per ADR-04-0009 Open Question 7) — adding a `_TaskClassAllowed` clause is one-line additive.
- Do **not** extract an `_emit(...)` helper. Two emit sites only; Rule of three not met (S6-01 reconciliation precedent).
- Do **not** inject `capability_minter` as a Strategy. Phase 5 supersession is by import-swap (ADR-04-0009 §Decision); premature pluggability is a Rule-2 anti-pattern.
- `on_validated` body is the short imperative shell over a single pure projection (`harvest_eligibility`) plus a single pure builder (`_validated_outcome_from`). No sub-pipeline extraction.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/tier.py` | Implement `on_validated`; add `harvest_eligibility`, `_validated_outcome_from`, `skip_reason_for` pure helpers; import mint from `codegenie.rag._capability_mint`. |
| `src/codegenie/fallback/confidence_gate.py` | New — named-clause Specification (ADR-0009 §Pattern fit). |
| `src/codegenie/fallback/post_validation_context.py` | New — frozen typed bridge between Stage 6 and `ValidatedPlanOutcome`. |
| `src/codegenie/fallback/__init__.py` | Re-export `PostValidationContext`, `ConfidenceGate` for the orchestrator. |
| `src/codegenie/plugins/events.py` | Register `HarvestSkipped` `WorkflowInternalEvent` variant (mirror S4-06's `SolvedExampleHarvested` row). |
| `pyproject.toml` (`[tool.importlinter]`) | Extend S4-06's contract `ignore_imports` with `codegenie.fallback.tier -> codegenie.rag._capability_mint`. |
| `tests/unit/fallback/test_on_validated.py` | New — dispatch order, payload identity, no-inline-BoolOp AST check. |
| `tests/unit/fallback/test_on_validated_idempotent.py` | New — deterministic-id pre-check; no `Deduped` variant. |
| `tests/unit/fallback/test_confidence_gate.py` | New — clauses, truth table on shipped `Literal["high","degraded"]`, removal-changes-table structural property. |
| `tests/unit/fallback/test_harvest_eligibility.py` | New — exhaustive variant test; pure helper. |
| `tests/unit/fallback/test_validated_outcome_projection.py` | New — field-by-field projection assertions; mypy-negative test for non-LLM outcome. |
| `tests/integration/test_phase4_on_validated_under_lock.py` | New — `asyncio.gather` × 2 with `wait_for(30.0)`; distinct + identical key cases. |
| `tests/property/test_on_validated_mutual_exclusion.py` | New — Hypothesis property: exactly one terminal event; closed-set reason. |
| `tests/unit/plugins/test_events.py` | Extended — `HarvestSkipped` round-trip + closed-set rejection. |
| `tests/fence/test_phase4_capability_mint_scope.py` | Amended — two-row `ignore_imports`; `_ALLOWED_IMPORTERS` includes `fallback/tier.py`. |
| `tests/fixtures/plan_outcome_factories.py` | New (or extended from S1-03) — `make_applied_from_llm/recipe/...` builders. |
| `tests/fixtures/post_validation_context_factory.py` | New — `make_context(**overrides)` builder. |

## Out of scope

- The roadmap-exit-criterion E2E (second-run-hits-RAG) — **S7-07**.
- Phase 5's `GateRunner` swap of `_phase4_local_capability_mint` → `gates._capability_mint` — Phase 5; the shim docstring carries the `# TODO(phase-5)` marker per S4-06 AC-5.
- Phase 11's merge-webhook post-validate harvest — a *second* ingestion path; both call `ingest_solved_example` with different capabilities (Phase 11's concern).
- Operator quarantine path for subtly-wrong harvested examples — Phase 6.5 / Phase 11.
- **Amending `TrustOutcome.confidence` literal set.** The shipped `Literal["high", "degraded"]` is production-ADR-0008's gate; widening would be a cross-phase change.
- **Amending S1-03's `AppliedFromLlm` to carry `plan_proposal`.** Currently `plan_proposal` flows via `PostValidationContext`; if a later phase needs it on the variant, that's an additive S1-03 amendment.

## Notes for the implementer

- The capability is **Module Boundary, not GoF Capability** — Python doesn't have runtime-unforgeable capabilities; `import-linter` is the lint-time backstop. Don't overclaim in docstrings (ADR-0009 §Pattern fit).
- The `ConfidenceGate` must be *named and composed* — a free-form `if trust.passed and trust.confidence == "high"` ladder inside `on_validated` violates the Specification pattern (ADR-0009 §Tradeoffs) AND the AC-3 AST check fails the build.
- The `outcome_not_harvestable` skip for `AppliedFromRecipe`/`RagOnlyApplicable`/`Refused` is intentional: recipes are deterministic and already in the corpus by virtue of the recipe definition; harvesting them creates duplicate near-identical few-shots and degrades retrieval (final-design open question on second-knob refinement). The dispatch order in AC-7 runs eligibility *before* the gate so a non-LLM outcome with a degraded `TrustOutcome` still reports the eligibility reason, never the gate reason.
- `ingest_solved_example` runs under `asyncio.Lock` inside `SolvedExampleStore` (S4-03). `on_validated` does NOT lock externally — that would double-lock and deadlock under `asyncio.gather`.
- If the integration test under `asyncio.gather` hangs, it's likely the chromadb embedded-mode `add()` blocking the event loop — High-level-impl Step 4 §Risks bullet 3 names the mitigation: wrap in `loop.run_in_executor`. Surface per Global Rule 12 if the 30s contention contract can't be met.
- **Rule 7 — surface conflicts, don't blend.** The ADR-04-0009 + phase-arch text references to `TrustOutcome.confidence == "medium"` / `"low"` were written before the shipped Phase-3 type pinned the literal set to `["high", "degraded"]`. The hardened story honors the shipped type. Land a one-line amendment to ADR-04-0009 §Consequences ("`confidence` is `Literal['high', 'degraded']`; gate fires on `'high'` only") and phase-arch Edge-case 18 ("`confidence != 'high'` covers `'degraded'`") in the same PR. **Do not** widen `TrustOutcome.confidence`.
- **Rule 7 — `on_validated` signature widening.** S6-01's stub raises `NotImplementedError`; widening additively to accept `context: PostValidationContext` is safe because the stub test only asserts the raise. If the orchestrator (Phase 3 / Phase 5 callsite) does not yet pass `context`, that's the callsite's amendment to land in the same PR.
- **Rule 8 — read before you write.** Verify `SolvedExampleStore.contains(sid) -> bool` is on the S4-03 surface before relying on it for the idempotence pre-check. If it isn't, surface as a blocking precondition (do NOT silently widen S4-03; that's a separate ADR).
- **Open/Closed seam.** When Phase 6.5 introduces the second-knob (per-task-class trust gating), it appends a `_TaskClassAllowed` clause to `ConfidenceGate.clauses` — one Pydantic-frozen class + one row in the `clauses` tuple. `on_validated` does not change. This is what "extension by addition" looks like for this seam.
- The deterministic-id pre-check is the load-bearing idempotence mechanism. `_solved_example_id_for(...)` is keyed on `(cve_id, advisory_digest, transform_digest, trust_outcome_digest, embedding_model)` per S4-06 AC-3. Two `on_validated` calls with the same `(outcome, context)` hash to the same id; `store.contains(id)` is the cheap check; `HarvestSkipped(reason="already_harvested")` is the audit signal. Chroma's natural upsert is the safety net beneath this — but the audit event is the operator-visible truth.
