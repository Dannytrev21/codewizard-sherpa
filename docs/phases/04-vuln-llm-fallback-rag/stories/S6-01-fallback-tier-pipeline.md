# Story S6-01 — `FallbackTier` named-sequential pipeline

**Step:** Step 6 — Compose FallbackTier + register typecheck.typescript SignalKind + integration
**Status:** Ready
**Effort:** L
**Depends on:** S2-01 (ProvenanceGate), S2-05 (LlmInvocationGuard + BudgetToken), S3-02 (AnthropicLeafAdapter), S5-02 (two-threshold band classifier); transitively S2-02..S2-04, S4-*, S5-01
**ADRs honored:** ADR-0002 (named sequential Pipeline — no LangGraph), ADR-0004 (`PlanOutcome` wraps `RecipeOutcome` — no widening), ADR-0010 (`BudgetToken` capability flows only two frames), ADR-0012 (ProvenanceGate as explicit tier-0), ADR-0013 (FenceWrapper / CanaryGuard discipline)

## Context

Phase 4's recipe → RAG → LLM dispatch order is fixed by production ADR-0011. ADR-04-0002 records the structural choice: `FallbackTier` is a **single `async def run(...)` composed as a short, named, sequential pipeline** — no LangGraph (Phase 6 owns that), no async generator, no `Chain-of-Responsibility` Protocol. The order *is* the policy.

Phase 5 has already merged the callsite `FallbackTier.run(advisory, repo_ctx, recipe_selection, *, prior_attempts=[]) -> RecipeApplication` (arch §Goals G2). Phase 4 must produce that exact signature so Phase 5's `GateRunner` retry path works the day Phase 4 merges.

The pipeline composes nine named steps (arch §Control flow happy-path 1–9): provenance.classify → budget.running_total precheck → retrieval (or retry-bypass — covered by S6-02) → prompt-build → budget.precharge → leaf.invoke → budget.reconcile → build Transform → return `RecipeApplication`. Each step emits **one** audit event; failure surfaces as `RecipeApplication.Refused(reason=…)` or a typed exception that the Phase-3 plugin wrapper catches.

This story lands the dispatch shell + happy-path; S6-02 lands retry-bypass; S6-03 lands `on_validated`; S6-07 pins determinism under cassette replay.

## References — where to look

- **Architecture:** [phase-arch-design.md §Component 1 — FallbackTier](../phase-arch-design.md) (lines 438–475); §Control flow (lines 799–819); §Design patterns applied row 1 (Pipeline); §Anti-patterns avoided (capability-through-two-frames).
- **Phase ADRs:** [ADR-0002](../ADRs/0002-fallback-tier-pipeline-no-langgraph.md) (the structural choice); [ADR-0004](../ADRs/0004-plan-outcome-wraps-recipe-outcome.md) (`PlanOutcome` wraps not widens); [ADR-0010](../ADRs/0010-llm-invocation-guard-budget-token-capability.md) (`BudgetToken` capability scope); [ADR-0012](../ADRs/0012-provenance-gate-explicit-tier-zero.md) (gate runs first); [ADR-0013](../ADRs/0013-fence-wrapper-canary-scan-before-truncation.md).
- **Production ADRs:** [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) (chain order); [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md) (TrustOutcome shape `on_validated` consumes).
- **Source design:** [final-design.md §Component 1 — FallbackTier](../final-design.md); §"Three load-bearing structural lines" item 1.
- **High-level impl:** [High-level-impl.md §Step 6](../High-level-impl.md) (Features delivered list).
- **Existing code:** `src/codegenie/fallback/{plan_outcome.py,plan_proposal.py,types.py,provenance_gate.py,budget.py,fence/}`, `src/codegenie/fallback/leaf/{port.py,anthropic_adapter.py}`, `src/codegenie/rag/retriever.py` — every collaborator already exists at Step-6 start.

## Goal

Ship `src/codegenie/fallback/tier.py` exposing `FallbackTier.__init__(...)` and `async run(advisory, repo_ctx, recipe_selection, *, prior_attempts=[]) -> RecipeApplication` as a named sequential pipeline of nine steps, each emitting exactly one audit event, with happy-path (initial planning, `prior_attempts=[]`) producing a typed `RecipeApplication` from a validated `PlanProposal`.

## Acceptance criteria

- [ ] `FallbackTier.__init__` matches arch §Component 1 signature exactly (positional `retriever, leaf, budget, fence, canary, provenance, event_log` + keyword-only `prompt_builder, harvester, confidence_gate`).
- [ ] `async def run(advisory, repo_ctx, recipe_selection, *, prior_attempts: list[AttemptSummary] = []) -> RecipeApplication` — keyword-only `prior_attempts` with default `[]`; mypy `--strict` clean (no `Any`).
- [ ] Dispatch order is **provenance.classify → budget.running_total (precheck) → retrieval (this story: always called when `prior_attempts == []`; S6-02 adds bypass) → prompt_builder.build → budget.precharge → leaf.invoke → budget.reconcile → transform-build → return** — asserted by `tests/unit/fallback/test_fallback_tier.py` mocking every collaborator and recording call order.
- [ ] Each step emits one audit event in order: `ProvenanceClassified(kind)`, `BudgetPrechecked(running, requested)`, `RagHit|RagDegraded|RagMiss`, `PromptBuilt(prompt_digest_blake3)`, `BudgetPrecharged(token_id, precharged)`, `LeafInvoked(prompt_digest_blake3)` / `LeafReturned(response_digest_blake3, tokens_in, tokens_out)`, `BudgetReconciled(token_id, actual_in, actual_out)`, `TransformBuilt(plan_kind)` — asserted by an event-order tape in the unit test.
- [ ] **ProvenanceGate is tier-0**: `Provenance` not in `{AppDirect, AppTransitive, AppVendored, Both}` ⇒ method returns `RecipeApplication.Refused(reason="PROVENANCE_NOT_APP_LAYER")` and **`LeafInvoked` event MUST NOT appear** (event-absence assertion; mocked leaf raises `pytest.fail` on entry). Honors ADR-0012 + arch §Edge case row 1.
- [ ] **Budget precheck**: `running_total + per_call_max_tokens > max_tokens_per_workflow` ⇒ `RecipeApplication.Refused(reason="BUDGET_EXCEEDED")` before any leaf call (event-absence on `LeafInvoked`).
- [ ] **BudgetToken flows through exactly two frames**: `FallbackTier.run` (mint via `budget.precharge`) → `LeafLlm.invoke` (consume). `tests/unit/fallback/test_budget_token_scope.py` (extending S2-05's import-linter contract) confirms no other module references `BudgetToken` instances — per ADR-0010 and arch §Anti-patterns avoided.
- [ ] **`PlanOutcome` emitted alongside `RecipeApplication`**: the method emits a `PlanOutcomeEmitted(outcome)` event carrying the Phase-4-local `PlanOutcome` variant (`AppliedFromRecipe | AppliedFromLlm | RagOnlyApplicable | Refused`) — without widening Phase-3 `RecipeOutcome`. ADR-0004 fence test (`tests/property/test_plan_outcome_no_recipe_outcome_widening.py` from S1-03) stays green after this story lands.
- [ ] **`PlanProposal.refuse` dispatch**: leaf returning `PlanProposal.refuse` ⇒ `RecipeApplication.Refused(reason="LEAF_REFUSED")`; `PlanProposal` validator failure ⇒ `Refused(reason="LEAF_SCHEMA_VIOLATION")`.
- [ ] **Typed errors**: raises `LeafProtocolViolation`, `BudgetExceeded`, `EgressViolation` for the unrecoverable cases; **never** logs raw LLM completions or raw prompts (only BLAKE3 digests) — AST-walking test `tests/fence/test_no_raw_completions_logged.py` (lands in this story) passes.
- [ ] `mypy --strict` clean on `src/codegenie/fallback/tier.py`; `make lint`, `make lint-imports`, `make typecheck`, `make test` all green.
- [ ] `tests/fixtures/fallback_tier_callable.py` exports the `FallbackTier.run` signature + a constructed-from-fakes factory — published as the contract Phase 6 (LangGraph migration) reads. ADR-0002 §Reversibility commits to this fixture.

## Implementation outline

1. New module `src/codegenie/fallback/tier.py`. Imports: Phase-3 `RecipeApplication`, `RecipeSelection`, `CveAdvisory`, `RepoContext`, `AttemptSummary` (from Phase-3 / Phase-5 contract types); Phase-4 collaborators (`SolvedExampleRetriever`, `LeafLlm`, `LlmInvocationGuard`, `BudgetToken`, `FenceWrapper`, `CanaryGuard`, `ProvenanceGate`, `PromptBuilder`, `SolvedExampleWriter`, `ConfidenceGate`); event log; `PlanProposal` + `PlanOutcome`.
2. `class FallbackTier`: store collaborators in `__init__`; **no state of its own** (arch §State: None).
3. `async def run`: stepwise method calls; **never** an explicit `match` ladder over collaborator return types beyond what's strictly necessary for dispatch — keep each step three to ten lines.
4. Use `match plan` over `PlanProposal` variants when building `Transform`; `case _: assert_never(plan)` exhaustiveness — mypy `--strict` catches missing arms (open question 5).
5. Emit one event per step via `self._event_log.emit(...)`. Refactor common metadata (workflow_id, advisory.cve_id) into a small `_emit(kind, **fields)` helper.
6. **No retry logic.** Three transport retries live inside `AnthropicLeafAdapter` (S3-02); Phase 5's `GateRunner` owns gate-level retry. `FallbackTier` is a single-shot dispatch.
7. `on_validated` — leave as stub raising `NotImplementedError("see S6-03")` so S6-03 can land independently.
8. Publish `tests/fixtures/fallback_tier_callable.py` exporting `make_fallback_tier_for_fixtures(...)` returning a constructed-from-fakes instance — read by Phase 6 (LangGraph) and by the determinism property test (S6-07).

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/fallback/test_fallback_tier.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from codegenie.fallback.tier import FallbackTier
from codegenie.fallback.plan_proposal import PlanProposal, CallsiteRewrite
from codegenie.fallback.provenance_gate import Provenance
from codegenie.rag.models import RagHit
# ...other Phase-4 imports...

@pytest.mark.asyncio
async def test_run_happy_path_emits_nine_events_in_order(
    advisory_fix, repo_ctx_fix, recipe_selection_fix,
    capturing_event_log,
):
    """Happy path: dispatch order is the policy (ADR-04-0002).
    Why this matters: re-ordering steps silently breaks the trust boundary
    (e.g., leaf invoked before provenance classify spends tokens on
    non-app-layer CVEs — ADR-0012)."""
    retriever = AsyncMock()
    retriever.query.return_value = RagHit(...)
    leaf = AsyncMock()
    leaf.invoke.return_value = LeafResponse(plan=CallsiteRewrite(...), ...)
    budget = MagicMock()
    budget.running_total.return_value = BudgetSnapshot(consumed_tokens=0, ...)
    budget.precharge.return_value = BudgetToken(...)
    provenance = MagicMock()
    provenance.classify.return_value = Provenance.AppDirect
    tier = FallbackTier(
        retriever=retriever, leaf=leaf, budget=budget,
        fence=fence_fix, canary=canary_fix, provenance=provenance,
        event_log=capturing_event_log,
        prompt_builder=prompt_builder_fix,
        harvester=harvester_fix,
        confidence_gate=confidence_gate_fix,
    )

    result = await tier.run(advisory_fix, repo_ctx_fix, recipe_selection_fix)

    kinds = [e.kind for e in capturing_event_log.recorded]
    assert kinds == [
        "ProvenanceClassified", "BudgetPrechecked", "RagHit",
        "PromptBuilt", "BudgetPrecharged", "LeafInvoked",
        "LeafReturned", "BudgetReconciled", "TransformBuilt",
        "PlanOutcomeEmitted",
    ]
    assert isinstance(result, RecipeApplication.Applied)


@pytest.mark.asyncio
async def test_run_provenance_baseimage_refuses_without_leaf_call(
    advisory_fix, repo_ctx_fix, recipe_selection_fix, capturing_event_log,
):
    """Edge case row 1 + ADR-0012: BaseImage CVE never reaches leaf.
    Event-absence assertion is the load-bearing assurance."""
    provenance = MagicMock()
    provenance.classify.return_value = Provenance.BaseImage
    leaf = AsyncMock(side_effect=pytest.fail.__wrapped__)  # any leaf call fails
    tier = FallbackTier(..., leaf=leaf, provenance=provenance, ...)

    result = await tier.run(advisory_fix, repo_ctx_fix, recipe_selection_fix)

    assert isinstance(result, RecipeApplication.Refused)
    assert result.reason == "PROVENANCE_NOT_APP_LAYER"
    leaf.invoke.assert_not_called()
    assert "LeafInvoked" not in [e.kind for e in capturing_event_log.recorded]
```

### Green — make it pass

- Land `src/codegenie/fallback/tier.py` with the nine-step dispatch in the order the tests demand.
- Wire `_event_log.emit` calls precisely one per step.
- Build `Transform` from the `PlanProposal` variant via `match` with `assert_never` final arm.

### Refactor — clean up

- Extract `_emit_provenance`, `_emit_budget_precheck`, etc. only if duplication exceeds two-line cost; otherwise leave the linear `async def run` body readable as a sequence.
- Resist the urge to introduce a `_TierStep` Protocol / for-loop — the chain order *is* the policy (ADR-0002 §Pattern fit).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/tier.py` | The pipeline (new file). |
| `src/codegenie/fallback/__init__.py` | Export `FallbackTier`. |
| `tests/unit/fallback/test_fallback_tier.py` | Happy-path + dispatch-order + provenance short-circuit. |
| `tests/unit/fallback/test_budget_token_scope.py` | Extend S2-05 import-linter contract; `BudgetToken` referenced only inside `tier.py` + `leaf/anthropic_adapter.py`. |
| `tests/fence/test_no_raw_completions_logged.py` | AST-walks the codebase; `log.info(..., response.content, ...)` patterns fail (arch §Harness §Logging). |
| `tests/fixtures/fallback_tier_callable.py` | Fixture factory; published contract for Phase 6 lift. |

## Out of scope

- Retry path (`prior_attempts != []`) — **S6-02**.
- `on_validated` harvest hook — **S6-03**.
- `typecheck.typescript` SignalKind registration — **S6-04**/**S6-05**/**S6-06**.
- Determinism-under-cassette-replay property — **S6-07**.
- LangGraph migration — Phase 6.
- Integration tests against live API or real RAG store — those land via S6-05 / S7-06.

## Notes for the implementer

- The chain order *is* the policy (ADR-0002). If you find yourself wanting a `for tier in self._tiers:` loop, stop and re-read ADR-0002 §Pattern fit.
- `BudgetToken` must flow through exactly two frames. If you find yourself threading it through `PromptBuilder` or `FenceWrapper`, you've broken ADR-0010; surface per Global Rule 7.
- Phase 5's `AttemptSummary` shape is part of Phase 5's pre-merged contract; for Step 6 it suffices to declare `list[AttemptSummary] = []`. S6-02 reads `prior_attempts[-1].prior_failure_summary`.
- `assert_never` exhaustiveness on `PlanProposal` requires `mypy --strict`; verify CI runs it as a hard gate (open question 5) — `make typecheck` must be load-bearing.
- Publishing `tests/fixtures/fallback_tier_callable.py` in this story (rather than in S7-10) is intentional — ADR-0002 §Reversibility names it as the Phase-6 contract.
- The `PlanOutcomeEmitted` event is **in addition to** the `RecipeApplication` return — two events per outcome is acceptable cost for clean layering (ADR-0004 §Consequences).
