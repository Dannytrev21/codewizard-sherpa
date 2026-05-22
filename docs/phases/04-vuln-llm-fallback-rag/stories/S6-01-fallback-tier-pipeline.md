# Story S6-01 — `FallbackTier` named-sequential pipeline

**Step:** Step 6 — Compose FallbackTier + register typecheck.typescript SignalKind + integration
**Status:** HARDENED
**Effort:** L
**Depends on:** S2-01 (ProvenanceGate), S2-05 (LlmInvocationGuard + BudgetToken), S3-02 (AnthropicLeafAdapter), S5-02 (two-threshold band classifier); transitively S2-02..S2-04, S4-*, S5-01
**ADRs honored:** ADR-0002 (named sequential Pipeline — no LangGraph), ADR-0004 (`PlanOutcome` wraps `RecipeOutcome` — no widening), ADR-0010 (`BudgetToken` capability flows only two frames), ADR-0012 (ProvenanceGate as explicit tier-0), ADR-0013 (FenceWrapper / CanaryGuard discipline)

## Validation notes (2026-05-22 — phase-story-validator)

Story HARDENED. Changes:

- **Event count clarified:** "nine per-step events + one terminal `PlanOutcomeEmitted` = ten events total on happy path" (ADR-0004 §Consequences explicitly authorizes the terminal). Step 6 (leaf-invoke) emits two per-step events (`LeafInvoked` + `LeafReturned`) per ADR-0010 §Consequences.
- **ACs strengthened:** exact event count (`len(recorded) == 10`), `Counter(kinds)` multiplicity invariant, explicit event-list shapes for every refuse path, `assert_never(plan)` exhaustiveness, `on_validated` stub, `Refused.reason` is `Literal[...]`, `PlanOutcomeEmitted.outcome` is typed `PlanOutcome`, factory constructs successfully, `leaf.invoke.call_count == 1` on happy path, typed-error policy pinned, eight new event kinds registered in `src/codegenie/plugins/events.py` `WorkflowInternalEvent` union.
- **TDD plan fixed:** broken `pytest.fail.__wrapped__` replaced with `AssertionError` side-effect; cross-event payload identity asserted (`PromptBuilt.digest == LeafInvoked.digest`; `BudgetPrecharged.token_id == BudgetReconciled.token_id`); provenance-refuse parametrized over every non-app-layer variant; budget-precheck refuse test added; prefix-ordering property test added; `capturing_event_log` spec'd against `EventLog` Protocol.
- **Implementation outline:** `_emit` helper extracted only if ≥ 2 fields are shared across every emit (reconciles outline vs Refactor); pure `transform_from_plan(plan: PlanProposal) -> Transform` extracted as functional core (testable in isolation).
- **Cross-phase conflicts surfaced (Global Rule 7, do not silently average):**
  - `RecipeApplication` shape — Phase 4 arch (§Component 1 lines 430/475) authoritatively declares it a tagged union (`Applied` / `Refused`). If Phase 5's shipped type is a single Pydantic class with `.diff: bytes`, surface and amend the contract before shipping. Do NOT silently coerce.
  - `prior_attempts` type — Phase 5 G2 contract reads `list[AttemptSummary] = []`. Story adopts `Sequence[AttemptSummary] = ()` (read-covariant, accepts list callers, no mutable-default footgun). If Phase 5 typed `list` invariantly, surface and amend.

See `_validation/S6-01-fallback-tier-pipeline.md` for the full critic reports and conflict-resolution log.

## Context

Phase 4's recipe → RAG → LLM dispatch order is fixed by production ADR-0011. ADR-04-0002 records the structural choice: `FallbackTier` is a **single `async def run(...)` composed as a short, named, sequential pipeline** — no LangGraph (Phase 6 owns that), no async generator, no `Chain-of-Responsibility` Protocol. The order *is* the policy.

Phase 5 has already merged the callsite `FallbackTier.run(advisory, repo_ctx, recipe_selection, *, prior_attempts=[]) -> RecipeApplication` (arch §Goals G2). Phase 4 must produce that exact signature so Phase 5's `GateRunner` retry path works the day Phase 4 merges.

The pipeline composes nine named steps (arch §Control flow happy-path 1–9): provenance.classify → budget.running_total precheck → retrieval (or retry-bypass — covered by S6-02) → prompt-build → budget.precharge → leaf.invoke → budget.reconcile → build Transform → return `RecipeApplication`. Each step emits one audit event in order, with step 6 (leaf-invoke) emitting two events (`LeafInvoked` + `LeafReturned` per ADR-0010 §Consequences). On success the pipeline also emits a terminal `PlanOutcomeEmitted` carrying the Phase-4-local `PlanOutcome` variant (ADR-0004 §Consequences), bringing the happy-path total to **ten audit events**. Failure surfaces as `RecipeApplication.Refused(reason=…)` and a `PlanOutcomeEmitted(Refused(reason=…))` event; the typed exceptions that survive (`EgressViolation`) propagate to the Phase-3 plugin wrapper.

This story lands the dispatch shell + happy-path; S6-02 lands retry-bypass; S6-03 lands `on_validated`; S6-07 pins determinism under cassette replay.

## References — where to look

- **Architecture:** [phase-arch-design.md §Component 1 — FallbackTier](../phase-arch-design.md) (lines 438–475); §Control flow (lines 799–819); §Design patterns applied row 1 (Pipeline); §Anti-patterns avoided (capability-through-two-frames).
- **Phase ADRs:** [ADR-0002](../ADRs/0002-fallback-tier-pipeline-no-langgraph.md) (the structural choice); [ADR-0004](../ADRs/0004-plan-outcome-wraps-recipe-outcome.md) (`PlanOutcome` wraps not widens); [ADR-0010](../ADRs/0010-llm-invocation-guard-budget-token-capability.md) (`BudgetToken` capability scope); [ADR-0012](../ADRs/0012-provenance-gate-explicit-tier-zero.md) (gate runs first); [ADR-0013](../ADRs/0013-fence-wrapper-canary-scan-before-truncation.md).
- **Production ADRs:** [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) (chain order); [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md) (TrustOutcome shape `on_validated` consumes).
- **Source design:** [final-design.md §Component 1 — FallbackTier](../final-design.md); §"Three load-bearing structural lines" item 1.
- **High-level impl:** [High-level-impl.md §Step 6](../High-level-impl.md) (Features delivered list).
- **Existing code:** `src/codegenie/fallback/{plan_outcome.py,plan_proposal.py,types.py,provenance_gate.py,budget.py,fence/}`, `src/codegenie/fallback/leaf/{port.py,anthropic_adapter.py}`, `src/codegenie/rag/retriever.py` — every collaborator already exists at Step-6 start.

## Goal

Ship `src/codegenie/fallback/tier.py` exposing `FallbackTier.__init__(...)` and `async run(advisory, repo_ctx, recipe_selection, *, prior_attempts: Sequence[AttemptSummary] = ()) -> RecipeApplication` as a named sequential pipeline of nine steps, emitting exactly ten audit events on happy path (one per step, with step 6 emitting `LeafInvoked` + `LeafReturned`, plus a terminal `PlanOutcomeEmitted` per ADR-0004), with happy-path (initial planning, `prior_attempts=()`) producing a typed `RecipeApplication.Applied` from a validated `PlanProposal`.

## Acceptance criteria

### Signature + types

- [ ] `FallbackTier.__init__` matches arch §Component 1 signature exactly (positional `retriever, leaf, budget, fence, canary, provenance, event_log` + keyword-only `prompt_builder, harvester, confidence_gate`).
- [ ] `async def run(advisory, repo_ctx, recipe_selection, *, prior_attempts: Sequence[AttemptSummary] = ()) -> RecipeApplication` — keyword-only `prior_attempts` defaulting to an **immutable empty tuple** (no mutable-default footgun); `Sequence` is read-covariant so callers passing `list[...]` still typecheck. If Phase 5's shipped signature insists on `list[AttemptSummary] = []`, surface as a Global-Rule-7 conflict (see Notes). `mypy --strict` clean — no `Any`, no untyped functions.
- [ ] `FallbackTier.on_validated(self, outcome: PlanOutcome, trust: TrustOutcome) -> None` exists as a stub that `raise NotImplementedError("see S6-03")` — signature is mypy `--strict` clean; tested in `test_fallback_tier.py::test_on_validated_stub_raises`. (Phase 5 / Phase 3 orchestrator callsites can import the method symbol from Step 6 onward; S6-03 fills the body.)
- [ ] `RecipeApplication.Refused.reason` is typed `Literal["PROVENANCE_NOT_APP_LAYER", "BUDGET_EXCEEDED", "LEAF_REFUSED", "LEAF_SCHEMA_VIOLATION"]` (the closed set ADR-0004 §Decision authorizes); `mypy --strict` rejects unknown literals at any call site.

### Dispatch order + event tape

- [ ] Dispatch order is **provenance.classify → budget.running_total (precheck) → retrieval (this story: always called when `prior_attempts == ()`; S6-02 adds the bypass) → prompt_builder.build → budget.precharge → leaf.invoke → budget.reconcile → transform-build → return** — asserted by `tests/unit/fallback/test_fallback_tier.py` mocking every collaborator and recording call order via a single chronological tape.
- [ ] **Happy-path event tape is exactly ten events in order:** `ProvenanceClassified(kind)`, `BudgetPrechecked(running, requested)`, one of `RagHit|RagDegraded|RagMiss`, `PromptBuilt(prompt_digest_blake3)`, `BudgetPrecharged(token_id, precharged)`, `LeafInvoked(prompt_digest_blake3)`, `LeafReturned(response_digest_blake3, tokens_in, tokens_out)`, `BudgetReconciled(token_id, actual_in, actual_out)`, `TransformBuilt(plan_kind)`, `PlanOutcomeEmitted(outcome)`. Asserted by **both** list-equality (`kinds == [...]`) **and** `Counter(kinds) == Counter([...])` (multiplicity invariant — duplicate emits fail; missing emits fail). Step 6 emits two events (`LeafInvoked` + `LeafReturned` per ADR-0010 §Consequences); every other step emits exactly one.
- [ ] **Happy-path leaf call**: `leaf.invoke.call_count == 1` and `leaf.invoke.assert_awaited_once()`. A "short-circuit-after-emit" mutation (emit `LeafInvoked` then return without awaiting `leaf.invoke`) fails this AC.
- [ ] **Happy-path `PlanOutcome` variant** is `AppliedFromLlm` (not `AppliedFromRecipe`, not `RagOnlyApplicable`) — asserted by `events_by_kind["PlanOutcomeEmitted"].outcome` `isinstance(AppliedFromLlm)`. Initial planning with `prior_attempts == ()` always reaches the leaf, so `AppliedFromLlm` is the only correct variant.
- [ ] **Cross-event payload identity** (catches "emit-the-right-kind-but-wrong-payload" mutations): `PromptBuilt.prompt_digest_blake3 == LeafInvoked.prompt_digest_blake3`; `BudgetPrecharged.token_id == BudgetReconciled.token_id`; `LeafReturned.response_digest_blake3` is the BLAKE3 of the (validated, redacted) `LeafResponse`.
- [ ] **`PlanOutcomeEmitted.outcome` is typed `PlanOutcome`** (the Phase-4-local discriminated union, not `dict[str, Any]`); JSON-serialization preserves the discriminator tag. Asserted by `test_plan_outcome_emitted_payload_is_typed`.

### Refuse paths — event-list shape pinned for each

- [ ] **Provenance refuse (tier-0):** `Provenance` not in `{AppDirect, AppTransitive, AppVendored, Both}` ⇒ method returns `RecipeApplication.Refused(reason="PROVENANCE_NOT_APP_LAYER")`. Event tape is exactly `["ProvenanceClassified", "PlanOutcomeEmitted"]` — **`LeafInvoked` MUST NOT appear**, and `BudgetPrechecked` MUST NOT appear (the gate runs before the precheck). `leaf.invoke.assert_not_awaited()`. Honors ADR-0012 + arch §Edge case row 1. Parametrized over **every** non-app-layer variant of the `Provenance` enum (not just `BaseImage`).
- [ ] **Budget precheck refuse:** `running_total + per_call_max_tokens > max_tokens_per_workflow` ⇒ `Refused(reason="BUDGET_EXCEEDED")`. Event tape is exactly `["ProvenanceClassified", "BudgetPrechecked", "PlanOutcomeEmitted"]` — `PromptBuilt`, `BudgetPrecharged`, `LeafInvoked` MUST NOT appear; `leaf.invoke.assert_not_awaited()`.
- [ ] **Leaf refuses** (`LeafResponse.plan` is `PlanProposal.refuse`): `Refused(reason="LEAF_REFUSED")`. Event tape is exactly `["ProvenanceClassified", "BudgetPrechecked", <RagHit|RagDegraded|RagMiss>, "PromptBuilt", "BudgetPrecharged", "LeafInvoked", "LeafReturned", "BudgetReconciled", "PlanOutcomeEmitted"]` — **`TransformBuilt` MUST NOT appear**.
- [ ] **Leaf schema violation** (`PlanProposal` validator failure inside adapter): `Refused(reason="LEAF_SCHEMA_VIOLATION")`. Event tape matches the leaf-refuses shape; `TransformBuilt` MUST NOT appear.
- [ ] **Prefix-ordering invariant:** for every abort path, the emitted event sequence (minus the terminal `PlanOutcomeEmitted`) is a strict prefix of the happy-path event sequence. Asserted by `test_event_emission_is_prefix_of_happy_path` parametrized over the four refuse paths.
- [ ] **Typed-error policy pinned:** `EgressViolation` from the adapter **propagates** (raised out of `run`) — Phase 3 plugin wrapper catches. `LeafProtocolViolation` from schema validation is **caught and converted** to `Refused(LEAF_SCHEMA_VIOLATION)`. `BudgetExceeded` from `precharge` is **caught and converted** to `Refused(BUDGET_EXCEEDED)`. Only `EgressViolation` raises out of `run`. Asserted by `test_typed_error_policy` exercising each.

### Pattern + scope discipline

- [ ] **BudgetToken flows through exactly two frames**: `FallbackTier.run` (mint via `budget.precharge`) → `LeafLlm.invoke` (consume) — per ADR-0010 and arch §Anti-patterns avoided. S2-05's import-linter contract (`tests/fence/test_budget_token_scope.py`) already pins this scope to `{codegenie.fallback.budget, codegenie.fallback.tier, codegenie.fallback.leaf.anthropic_adapter}`; this story **exercises** that contract by introducing `tier.py` as one of the permitted importers — `make lint-imports` stays green; no new import-linter test is required.
- [ ] **`PlanOutcome` wraps, never widens:** the `PlanOutcomeEmitted` event carries the Phase-4-local `PlanOutcome` variant (`AppliedFromRecipe | AppliedFromLlm | RagOnlyApplicable | Refused`) — Phase 3 `RecipeOutcome` is unchanged. ADR-0004 fence test (`tests/property/test_plan_outcome_no_recipe_outcome_widening.py` from S1-03) stays green after this story lands.
- [ ] **`match plan` exhaustiveness:** `tests/fence/test_fallback_tier_assert_never.py` AST-walks `src/codegenie/fallback/tier.py` and asserts that the Transform-build site uses a `match plan:` block with a `case _: assert_never(plan)` arm — `if/elif` over `.kind` strings is rejected. `mypy --strict` catches missing arms.
- [ ] **Eight new event kinds registered** in `src/codegenie/plugins/events.py`: `ProvenanceClassified`, `BudgetPrechecked`, `RagHit`, `RagDegraded`, `RagMiss`, `PromptBuilt`, `BudgetPrecharged`, `LeafInvoked`, `LeafReturned`, `BudgetReconciled`, `TransformBuilt`, `PlanOutcomeEmitted` (skipping any already shipped by S2-01 / S2-04 / S4-01). Each appears in `WorkflowInternalEvent` discriminated union AND in `_INTERNAL_CLASSES`; round-trip tested in `tests/unit/plugins/test_events.py` via `_INTERNAL_ADAPTER`. Missing registration = Pydantic-discriminator failure at first emission.

### Hygiene + harness

- [ ] **Never logs raw LLM completions or raw prompts** — only BLAKE3 digests. AST-walking test `tests/fence/test_no_raw_completions_logged.py` (lands in this story) includes a *positive case*: parses an inline source string containing `log.info(..., response.content, ...)` and asserts the walker flags it; the codebase-clean assertion is the negative case.
- [ ] `tests/fixtures/fallback_tier_callable.py` exports `make_fallback_tier_for_fixtures(...)` returning a constructed-from-fakes `FallbackTier` instance — published as the contract Phase 6 (LangGraph migration) reads. ADR-0002 §Reversibility commits to this fixture. **The fixture is exercised:** `tests/fixtures/test_fallback_tier_callable.py::test_factory_constructs` calls `make_fallback_tier_for_fixtures()` and asserts `isinstance(tier, FallbackTier)` — a typo-broken fixture fails loudly.
- [ ] `mypy --strict` clean on `src/codegenie/fallback/tier.py`; `make lint`, `make lint-imports`, `make typecheck`, `make test` all green.

## Implementation outline

1. New module `src/codegenie/fallback/tier.py`. Imports: Phase-3 `RecipeApplication`, `RecipeSelection`, `CveAdvisory`, `RepoContext`, `AttemptSummary` (from Phase-3 / Phase-5 contract types); Phase-4 collaborators (`SolvedExampleRetriever`, `LeafLlm`, `LlmInvocationGuard`, `BudgetToken`, `FenceWrapper`, `CanaryGuard`, `ProvenanceGate`, `PromptBuilder`, `SolvedExampleWriter`, `ConfidenceGate`); event log; `PlanProposal` + `PlanOutcome`.
2. `class FallbackTier`: store collaborators in `__init__`; **no state of its own** (arch §State: None).
3. `async def run`: stepwise method calls; **never** an explicit `match` ladder over collaborator return types beyond what's strictly necessary for dispatch — keep each step three to ten lines. Catch `BudgetExceeded` / `LeafProtocolViolation` at the tier-level and project to `Refused(reason=...)`; let `EgressViolation` propagate.
4. **Pure functional core for plan → Transform:** extract `def transform_from_plan(plan: PlanProposal) -> Transform` as a **module-level pure function** (no I/O, no event emission). Use `match plan` over `PlanProposal` variants with `case _: assert_never(plan)` exhaustiveness. `run()` calls it. The pure split lets `tests/unit/fallback/test_transform_builder.py` exercise every variant + the `assert_never` arm without standing up the whole `FallbackTier`. Resist extracting more — the rest of `run()` is genuinely I/O-driven imperative shell (functional core / imperative shell, arch §Design patterns applied row 5).
5. Emit one event per step via `self._event_log.emit(...)` (step 6 emits two — `LeafInvoked` then `LeafReturned`). Inline the calls. Extract a `_emit(kind, **fields)` helper **only if** ≥ 2 fields are shared verbatim across every call (e.g., `workflow_id`, `advisory.cve_id`) — otherwise leave inline (Rule 2: three similar lines beats premature abstraction; ADR-0002 commits to the linear-body shape).
6. **No retry logic.** Three transport retries live inside `AnthropicLeafAdapter` (S3-02); Phase 5's `GateRunner` owns gate-level retry. `FallbackTier` is a single-shot dispatch.
7. `on_validated(self, outcome: PlanOutcome, trust: TrustOutcome) -> None`: stub raising `NotImplementedError("see S6-03")`. Method exists with the correct signature so Phase 5 / Phase 3 orchestrator callsites can import it from Step 6 onward; S6-03 fills the body.
8. **Register event kinds** in `src/codegenie/plugins/events.py`: add `ProvenanceClassified`, `BudgetPrechecked`, `RagHit`, `RagDegraded`, `RagMiss`, `PromptBuilt`, `BudgetPrecharged`, `LeafInvoked`, `LeafReturned`, `BudgetReconciled`, `TransformBuilt`, `PlanOutcomeEmitted` as frozen Pydantic models with `event_type: Literal[...]` discriminators; wire each into `WorkflowInternalEvent` union and `_INTERNAL_CLASSES`. Skip any already shipped by S2-01 / S2-04 / S4-01 (re-check at impl time).
9. Publish `tests/fixtures/fallback_tier_callable.py` exporting `make_fallback_tier_for_fixtures(...)` returning a constructed-from-fakes instance — read by Phase 6 (LangGraph) and by the determinism property test (S6-07). Cover with a small `test_factory_constructs` so a typo-broken fixture fails loudly.

## TDD plan — red / green / refactor

### Red — write the failing tests first

`capturing_event_log` is spec'd against the `EventLog` Protocol (`MagicMock(spec=EventLog)`-style) so a renamed `.emit` method cannot silently make tests vacuously pass. The fixture exposes `recorded: list[Event]` in chronological order; the only mutation point is via `.emit(...)`.

```python
# tests/unit/fallback/test_fallback_tier.py
from collections import Counter
import pytest
from unittest.mock import AsyncMock, MagicMock
from codegenie.fallback.tier import FallbackTier
from codegenie.fallback.plan_proposal import PlanProposal, CallsiteRewrite
from codegenie.fallback.plan_outcome import AppliedFromLlm, Refused as POutcomeRefused
from codegenie.fallback.provenance_gate import Provenance
from codegenie.rag.models import RagHit
# ...other Phase-4 imports...

HAPPY_PATH_KINDS = [
    "ProvenanceClassified", "BudgetPrechecked", "RagHit",
    "PromptBuilt", "BudgetPrecharged", "LeafInvoked",
    "LeafReturned", "BudgetReconciled", "TransformBuilt",
    "PlanOutcomeEmitted",
]


@pytest.mark.asyncio
async def test_run_happy_path_emits_ten_events_in_order(
    advisory_fix, repo_ctx_fix, recipe_selection_fix, capturing_event_log,
    fence_fix, canary_fix, prompt_builder_fix, harvester_fix, confidence_gate_fix,
):
    """Happy path: dispatch order is the policy (ADR-0002).
    Why this matters: re-ordering steps silently breaks the trust boundary
    (e.g., leaf invoked before provenance classify spends tokens on
    non-app-layer CVEs — ADR-0012). Step 6 emits TWO events
    (LeafInvoked + LeafReturned) per ADR-0010 §Consequences; the terminal
    PlanOutcomeEmitted is in addition to the nine per-step events per
    ADR-0004 §Consequences."""
    retriever = AsyncMock(); retriever.query.return_value = RagHit(...)
    leaf = AsyncMock(); leaf.invoke.return_value = LeafResponse(plan=CallsiteRewrite(...), ...)
    budget = MagicMock()
    budget.running_total.return_value = BudgetSnapshot(consumed_tokens=0, ...)
    budget.precharge.return_value = BudgetToken(...)
    provenance = MagicMock(); provenance.classify.return_value = Provenance.AppDirect
    tier = FallbackTier(
        retriever=retriever, leaf=leaf, budget=budget,
        fence=fence_fix, canary=canary_fix, provenance=provenance,
        event_log=capturing_event_log,
        prompt_builder=prompt_builder_fix,
        harvester=harvester_fix,
        confidence_gate=confidence_gate_fix,
    )

    result = await tier.run(advisory_fix, repo_ctx_fix, recipe_selection_fix)

    # Ordering AND exact multiplicity — duplicate emits or missing emits fail.
    recorded = capturing_event_log.recorded
    kinds = [e.kind for e in recorded]
    assert kinds == HAPPY_PATH_KINDS
    assert Counter(kinds) == Counter(HAPPY_PATH_KINDS)
    assert len(recorded) == 10

    # Leaf actually invoked (not short-circuited after emit).
    leaf.invoke.assert_awaited_once()
    assert leaf.invoke.call_count == 1

    # Cross-event payload identity — wrong-payload mutations fail.
    events_by_kind = {e.kind: e for e in recorded}
    assert events_by_kind["PromptBuilt"].prompt_digest_blake3 == \
        events_by_kind["LeafInvoked"].prompt_digest_blake3
    assert events_by_kind["BudgetPrecharged"].token_id == \
        events_by_kind["BudgetReconciled"].token_id

    # Happy-path PlanOutcome variant — must be AppliedFromLlm, not AppliedFromRecipe.
    assert isinstance(events_by_kind["PlanOutcomeEmitted"].outcome, AppliedFromLlm)

    assert isinstance(result, RecipeApplication.Applied)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "non_app_provenance",
    [p for p in Provenance if p not in {
        Provenance.AppDirect, Provenance.AppTransitive,
        Provenance.AppVendored, Provenance.Both,
    }],
)
async def test_run_non_app_layer_refuses_without_leaf_call(
    non_app_provenance,
    advisory_fix, repo_ctx_fix, recipe_selection_fix, capturing_event_log,
    fence_fix, canary_fix, prompt_builder_fix, harvester_fix, confidence_gate_fix,
):
    """Edge case row 1 + ADR-0012: every non-app-layer Provenance variant
    refuses before any leaf token spent. Event-absence is the load-bearing
    assurance — guarding only `BaseImage` would let `Unknown`/`RuntimeBundled`
    through."""
    provenance = MagicMock(); provenance.classify.return_value = non_app_provenance
    leaf = AsyncMock()
    leaf.invoke.side_effect = AssertionError(
        "leaf must not be called for non-app-layer provenance"
    )
    tier = FallbackTier(
        retriever=AsyncMock(), leaf=leaf, budget=MagicMock(),
        fence=fence_fix, canary=canary_fix, provenance=provenance,
        event_log=capturing_event_log,
        prompt_builder=prompt_builder_fix,
        harvester=harvester_fix,
        confidence_gate=confidence_gate_fix,
    )

    result = await tier.run(advisory_fix, repo_ctx_fix, recipe_selection_fix)

    assert isinstance(result, RecipeApplication.Refused)
    assert result.reason == "PROVENANCE_NOT_APP_LAYER"
    leaf.invoke.assert_not_awaited()
    kinds = [e.kind for e in capturing_event_log.recorded]
    assert kinds == ["ProvenanceClassified", "PlanOutcomeEmitted"]
    assert "LeafInvoked" not in kinds
    assert "BudgetPrechecked" not in kinds


@pytest.mark.asyncio
async def test_run_budget_precheck_refuses_without_leaf_call(
    advisory_fix, repo_ctx_fix, recipe_selection_fix, capturing_event_log,
    fence_fix, canary_fix, prompt_builder_fix, harvester_fix, confidence_gate_fix,
):
    """Cap exhaustion ⇒ Refused(BUDGET_EXCEEDED) before PromptBuilt/LeafInvoked.
    Why this matters: a missed precheck spends tokens on a request the cap
    forbids (ADR-0010 §Pattern fit, the Circuit Breaker open state)."""
    budget = MagicMock()
    budget.running_total.return_value = BudgetSnapshot(
        consumed_tokens=249_000, ...
    )  # next call would exceed 250_000
    budget.precharge.side_effect = BudgetExceeded(...)
    provenance = MagicMock(); provenance.classify.return_value = Provenance.AppDirect
    leaf = AsyncMock()
    leaf.invoke.side_effect = AssertionError("leaf must not be called on budget refuse")
    tier = FallbackTier(
        retriever=AsyncMock(), leaf=leaf, budget=budget,
        fence=fence_fix, canary=canary_fix, provenance=provenance,
        event_log=capturing_event_log,
        prompt_builder=prompt_builder_fix,
        harvester=harvester_fix,
        confidence_gate=confidence_gate_fix,
    )

    result = await tier.run(advisory_fix, repo_ctx_fix, recipe_selection_fix)

    assert isinstance(result, RecipeApplication.Refused)
    assert result.reason == "BUDGET_EXCEEDED"
    leaf.invoke.assert_not_awaited()
    kinds = [e.kind for e in capturing_event_log.recorded]
    assert kinds == ["ProvenanceClassified", "BudgetPrechecked", "PlanOutcomeEmitted"]
    for absent in ("PromptBuilt", "BudgetPrecharged", "LeafInvoked"):
        assert absent not in kinds


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "abort_setup, expected_terminal_reason, expected_prefix",
    [
        # abort points → expected event prefix from HAPPY_PATH_KINDS
        ("non_app_provenance", "PROVENANCE_NOT_APP_LAYER", HAPPY_PATH_KINDS[:1]),
        ("budget_precheck_fail", "BUDGET_EXCEEDED",       HAPPY_PATH_KINDS[:2]),
        ("leaf_refuses",         "LEAF_REFUSED",          HAPPY_PATH_KINDS[:8]),
        ("leaf_schema_violation","LEAF_SCHEMA_VIOLATION", HAPPY_PATH_KINDS[:8]),
    ],
    indirect=["abort_setup"],
)
async def test_event_emission_is_prefix_of_happy_path(
    abort_setup, expected_terminal_reason, expected_prefix,
    advisory_fix, repo_ctx_fix, recipe_selection_fix, capturing_event_log,
):
    """Prefix-ordering invariant: every abort emits a strict prefix of the
    happy-path event list + a terminal PlanOutcomeEmitted. Catches reorderings
    that happen to land identical kind sets but different sequences."""
    tier = abort_setup.tier
    result = await tier.run(advisory_fix, repo_ctx_fix, recipe_selection_fix)
    kinds = [e.kind for e in capturing_event_log.recorded]
    assert kinds == expected_prefix + ["PlanOutcomeEmitted"]
    assert isinstance(result, RecipeApplication.Refused)
    assert result.reason == expected_terminal_reason


@pytest.mark.asyncio
async def test_typed_error_policy(
    advisory_fix, repo_ctx_fix, recipe_selection_fix, capturing_event_log,
):
    """EgressViolation propagates; LeafProtocolViolation + BudgetExceeded
    are caught and projected to Refused(...). Pins arch §Component 1
    'Failure behavior' against drift."""
    # ... three sub-assertions, one per error class ...


@pytest.mark.asyncio
async def test_on_validated_stub_raises():
    """S6-01 ships only the signature; the body lands in S6-03.
    Pins the method's existence so Phase 5 callsites compile from Step 6 on."""
    tier = make_fallback_tier_for_fixtures()
    with pytest.raises(NotImplementedError, match="see S6-03"):
        await tier.on_validated(outcome=..., trust=...)


def test_plan_outcome_emitted_payload_is_typed(capturing_event_log):
    """PlanOutcomeEmitted.outcome must be the discriminated union,
    not dict[str, Any]. Anti-pattern: untyped event payload (arch §3)."""
    # serialise + deserialise via the event-log adapter; assert variant tag preserved


# tests/fixtures/test_fallback_tier_callable.py
def test_factory_constructs():
    """A typo-broken fixture would silently pass an export-existence check;
    this one actually constructs the tier."""
    from tests.fixtures.fallback_tier_callable import make_fallback_tier_for_fixtures
    tier = make_fallback_tier_for_fixtures()
    assert isinstance(tier, FallbackTier)
```

### Green — make it pass

- Land `src/codegenie/fallback/tier.py` with the nine-step dispatch in the order the tests demand.
- Extract module-level pure `transform_from_plan(plan: PlanProposal) -> Transform` with `match` + `assert_never`; cover every variant in `test_transform_builder.py`.
- Wire `_event_log.emit` calls precisely one per step (step 6 emits two — `LeafInvoked` then `LeafReturned`); terminal `PlanOutcomeEmitted` on every exit path.
- Register the new event kinds in `src/codegenie/plugins/events.py` (`WorkflowInternalEvent` union + `_INTERNAL_CLASSES`); round-trip them through `_INTERNAL_ADAPTER` in `tests/unit/plugins/test_events.py`.
- Build `RecipeApplication.Refused(reason=<closed Literal>)` via the typed `Literal[...]` alias.

### Refactor — clean up

- Extract `_emit(kind, **fields)` helper **only if** ≥ 2 fields (e.g., `workflow_id`, `advisory.cve_id`) are shared verbatim across every emit; otherwise leave inline (Rule 2). Outline §5 reconciles to "only-if-duplication".
- Resist the urge to introduce a `_TierStep` Protocol / for-loop — the chain order *is* the policy (ADR-0002 §Pattern fit). Rule-of-three: revisit when Phase 13 adds the third tier-shaped extension.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/tier.py` | The pipeline (new file) + pure `transform_from_plan` functional core. |
| `src/codegenie/fallback/__init__.py` | Export `FallbackTier`. |
| `src/codegenie/plugins/events.py` | Add the ten new event kinds (`ProvenanceClassified`, `BudgetPrechecked`, `RagHit`, `RagDegraded`, `RagMiss`, `PromptBuilt`, `BudgetPrecharged`, `LeafInvoked`, `LeafReturned`, `BudgetReconciled`, `TransformBuilt`, `PlanOutcomeEmitted`) to `WorkflowInternalEvent` union + `_INTERNAL_CLASSES`. Skip any already shipped by S2-01 / S2-04 / S4-01. |
| `tests/unit/plugins/test_events.py` | Round-trip each new event kind via `_INTERNAL_ADAPTER`. |
| `tests/unit/fallback/test_fallback_tier.py` | Happy-path event tape (incl. multiplicity + payload-identity); parametrized provenance short-circuit; budget-precheck refuse; leaf-refuses; leaf-schema-violation; prefix-ordering invariant; typed-error policy; `on_validated` stub raises; `PlanOutcomeEmitted` payload typed. |
| `tests/unit/fallback/test_transform_builder.py` | Exercise `transform_from_plan` over every `PlanProposal` variant + `assert_never` arm in isolation. |
| `tests/fence/test_fallback_tier_assert_never.py` | AST-walks `tier.py` asserting `match plan: ... case _: assert_never(plan)` exists. |
| `tests/fence/test_no_raw_completions_logged.py` | AST-walks the codebase; `log.info(..., response.content, ...)` patterns fail (arch §Harness §Logging). Includes a positive case asserting an inline violation IS flagged. |
| `tests/fixtures/fallback_tier_callable.py` | Fixture factory; published contract for Phase 6 lift. |
| `tests/fixtures/test_fallback_tier_callable.py` | `test_factory_constructs` exercises the fixture (typo-broken fixture fails loudly). |

**Note:** No new import-linter test for `BudgetToken` scope. S2-05 already shipped `tests/fence/test_budget_token_scope.py` pinning the import scope to `{codegenie.fallback.budget, codegenie.fallback.tier, codegenie.fallback.leaf.anthropic_adapter}`; this story exercises that contract by introducing `tier.py` as one of the permitted importers.

## Out of scope

- Retry path (`prior_attempts != []`) — **S6-02**.
- `on_validated` harvest hook — **S6-03**.
- `typecheck.typescript` SignalKind registration — **S6-04**/**S6-05**/**S6-06**.
- Determinism-under-cassette-replay property — **S6-07**.
- LangGraph migration — Phase 6.
- Integration tests against live API or real RAG store — those land via S6-05 / S7-06.

## Notes for the implementer

- **The chain order *is* the policy (ADR-0002).** If you find yourself wanting a `for tier in self._tiers:` loop or a `_TierStep` Protocol, stop and re-read ADR-0002 §Pattern fit. Rule-of-three: when Phase 13 (cost-aware tier re-rank) adds the *third* tier-shaped extension, revisit; until then the linear body is correct.
- **`BudgetToken` must flow through exactly two frames.** If you find yourself threading it through `PromptBuilder` or `FenceWrapper`, you've broken ADR-0010; surface per Global Rule 7.
- **Functional core / imperative shell.** The `transform_from_plan(plan)` extraction in outline §4 is deliberate — it lets you exercise every `PlanProposal` variant + the `assert_never` arm without standing up the whole `FallbackTier`. Resist extracting more — every other step in `run()` is genuinely I/O-driven imperative shell.
- **`prior_attempts: Sequence[AttemptSummary] = ()` — the mutable-default footgun.** Python's `def f(x=[])` shares the list across calls; `()` is immutable and safe. `Sequence` is read-covariant, so callers passing `list[AttemptSummary]` still typecheck. **Phase-5 contract conflict watch (Global Rule 7):** if S5-01's already-merged `ReplanHook` Protocol literally types `prior_attempts: list[AttemptSummary]` and Phase 5 invariantly imports the annotation string, surface the conflict; do not silently blend — pick one side and amend the contract.
- **`RecipeApplication` shape conflict (Global Rule 7).** Phase 4 arch §Component 1 lines 430/475 and ADR-0012 §Decision authoritatively declare `RecipeApplication.Applied | RecipeApplication.Refused(reason=...)` (a tagged union). Phase 5 stories (S5-01 line 40, S5-02 line 49) describe `RecipeApplication.diff: bytes` as a single attribute. **These are compatible only if `RecipeApplication` is a tagged union where `Applied` carries `.diff: bytes`.** Before shipping, check the actual `RecipeApplication` definition (Phase 3 ships it):
  - If it is a tagged union → no action, keep ACs as written.
  - If it is a single Pydantic class with `.diff: bytes` → **surface the conflict**, do not silently coerce. Either amend Phase 4 arch (ADR-amendment) or amend Phase 3's `RecipeApplication`. Picking one side silently violates Rule 7.
- **`Refused.reason` is a closed `Literal[...]`** — not a raw `str`. Use `Literal["PROVENANCE_NOT_APP_LAYER", "BUDGET_EXCEEDED", "LEAF_REFUSED", "LEAF_SCHEMA_VIOLATION"]` (or a `RefuseReason: TypeAlias = Literal[...]` in `fallback/refuse_reasons.py`); `mypy --strict` rejects unknown literals. Anti-pattern avoided §3 (stringly-typed identifiers).
- **Typed-error projection vs propagation.** `EgressViolation` propagates out of `run` — Phase 3 plugin wrapper catches. `LeafProtocolViolation` and `BudgetExceeded` are caught inside `run` and projected to `Refused(reason=...)`. Pinned in AC; mismatch causes the typed-error test to fail.
- **`PlanOutcome` is a discriminated union, not a `dict`.** The `PlanOutcomeEmitted.outcome` field must be typed as the closed union (`AppliedFromRecipe | AppliedFromLlm | RagOnlyApplicable | Refused`); JSON serialisation preserves the discriminator. The anti-pattern is silently flattening to `dict[str, Any]` for "event-log convenience" — it loses the variant tag and ADR-0004 §Consequences breaks.
- **`assert_never(plan)` exhaustiveness requires mypy `--strict` enforced in CI.** `make typecheck` must be load-bearing; the fence test `test_fallback_tier_assert_never.py` is a structural backup in case mypy is silently relaxed.
- **Event registration is part of this story.** The new event kinds must land in `src/codegenie/plugins/events.py` `WorkflowInternalEvent` discriminated union + `_INTERNAL_CLASSES`; missing registration = Pydantic-discriminator failure at first emission. Check whether S2-01 / S2-04 / S4-01 already shipped `ProvenanceClassified` / `PromptBuilt` / `RagHit` etc.; do not re-register.
- **Publishing `tests/fixtures/fallback_tier_callable.py` in this story** (rather than in S7-10) is intentional — ADR-0002 §Reversibility names it as the Phase-6 contract. The `test_factory_constructs` test ensures a typo-broken fixture fails loudly rather than silently passing the export-existence check.
- **The terminal `PlanOutcomeEmitted` event is *in addition to* the per-step events** — ten audit events total on happy path, not nine. ADR-0004 §Consequences explicitly authorizes the "two events per outcome" cost for clean layering.
