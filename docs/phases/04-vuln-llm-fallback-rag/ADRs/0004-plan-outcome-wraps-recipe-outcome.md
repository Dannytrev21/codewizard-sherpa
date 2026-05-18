# ADR-0004: `PlanOutcome` wraps `RecipeOutcome` — Phase-3 sum type is not widened

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** composition-over-inheritance · open-closed · tagged-union · phase-boundary · adr-0033
**Related:** ADR-0001 (this phase) · [production ADR-0031](../../../production/adrs/0031-plugin-architecture.md) · [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md)

## Context

Phase 3 shipped `RecipeOutcome = Applied | Skipped | Failed` (per Phase 3 final-design §3) as the discriminated union the orchestrator's Stage 3 (Planning) and downstream consumers `match` against. Phase 7's exit criterion (`roadmap.md §Phase 7`) is that "the diff for this phase touches *only* the new plugin directory" — Phase 7 must not edit `case` arms in Phase 3 / 4 / 5 / 6 files.

The best-practices design lens widened `RecipeOutcome` by addition: `Applied | Skipped | Failed | MatchedFromRag | ReplannedByLlm`. The critic correctly flagged this as a structural break (`critique.md §"[B] §5"`): adding variants to a sum type used by exhaustive `match` statements forces every consumer to add new `case` arms or fire `assert_never`. Phase 7's distroless plugin would have to add `case MatchedFromRag` / `case ReplannedByLlm` clauses *just to compile*, even though it has nothing to do with RAG or LLM. "Extension by addition" was being equivocated — adding new sum types is extension; widening an existing sum type is modification dressed as extension.

Phase 4 needs *some* sum type to dispatch on for event emission and the inline harvester (was the outcome from recipe? from LLM? RAG-only-applicable? refused-pre-LLM?). The choice is where this sum type lives.

## Options considered

- **Widen `RecipeOutcome` additively** (best-practices lens). Add two variants (`MatchedFromRag`, `ReplannedByLlm`) to Phase 3's union. **Pattern:** Additive union widening. Breaks Phase 7's exit criterion structurally.
- **Add Phase-4-specific fields to existing `RecipeOutcome` variants** (`Optional[SolvedExampleId]` on `Applied`, etc.). **Pattern:** Field accretion. Makes the existing variants schizophrenic (their meaning depends on which fields are populated); the toolkit's "Make illegal states unrepresentable" flag fires.
- **Return raw `dict[str, Any]` enriched alongside `RecipeApplication`** for event emission. **Pattern:** Untyped payload. The toolkit's `Untyped dict[str, Any] interfaces` anti-pattern fires immediately.
- **Phase-4-local `PlanOutcome` sum type composing `RecipeOutcome`** (synthesis departure). `PlanOutcome = AppliedFromRecipe(recipe_outcome) | AppliedFromLlm(recipe_outcome, few_shot_ref, response_id) | RagOnlyApplicable(few_shot_ref) | Refused(reason)`. `FallbackTier.run` still returns Phase 3's `RecipeApplication`; `PlanOutcome` is internal projection only. **Pattern:** Composition over union widening (Open/Closed at the sum-type boundary).

## Decision

Introduce `PlanOutcome` as a Phase-4-*local* Pydantic discriminated union at `src/codegenie/fallback/plan_outcome.py`. Variants: `AppliedFromRecipe`, `AppliedFromLlm`, `RagOnlyApplicable`, `Refused(reason: Literal["PROVENANCE_NOT_APP_LAYER","BUDGET_EXCEEDED","LEAF_REFUSED","LEAF_SCHEMA_VIOLATION"])`. `FallbackTier.run` continues to return Phase 3's `RecipeApplication` (the type Phase 5 already consumes); `PlanOutcome` is consumed only by event emission and the inline harvester. **Pattern:** Composition over union widening — Open/Closed at the sum-type boundary. Asserted by `tests/property/test_plan_outcome_no_recipe_outcome_widening.py` (AST walk over `RecipeOutcome` definition; fails if variants drift from Phase 3 declaration).

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 7's "diff touches only the new plugin directory" exit criterion holds — Phase 7's plugin doesn't add `case` arms anywhere in Phase 4/5 code | `PlanOutcome` and `RecipeOutcome` are two sum types covering overlapping ground; reading the event log requires understanding both |
| Phase 5's already-merged `FallbackTier.run → RecipeApplication` signature is preserved literally — no contract change | The internal projection (`PlanOutcome` from `RecipeApplication` + Phase-4 metadata) is a separate construction step inside `FallbackTier`; small extra code |
| Event emission and harvester get the rich four-variant shape they need without leaking the LLM-specific metadata into Phase 3's deterministic-orchestrator vocabulary | If Phase 4's metadata fields (`few_shot_ref`, `response_id`) need to flow downstream to Phase 5/6, they must do so via a separate typed envelope — not by piggybacking on `RecipeOutcome` |
| `tests/property/test_plan_outcome_no_recipe_outcome_widening.py` becomes an inheritable test — Phase 7 inherits the assertion and the test fails if Phase 7 (or any future phase) widens Phase 3's union | A property test on AST shape is a static-analysis test; it fails fast but engineers can sometimes work around it (a documented anti-pattern in the test's docstring) |
| `assert_never` exhaustiveness in `PlanOutcome` consumers is local to Phase 4 — adding a fifth Phase-4-internal variant doesn't propagate | Phase 4's *external* contract (the `RecipeApplication.Refused(reason=...)` literal) does need maintenance if new refuse reasons emerge — but those have always lived in Phase 3 |

## Pattern fit

The toolkit's tagged union / sum type pattern requires *closure* to be valuable — "the failure mode if misapplied: a 'sum type' that grows new variants in every release breaks all the exhaustive matches that depended on it." Composition over union widening is the explicit pattern for cross-phase extension: instead of editing Phase 3's sum type, Phase 4 introduces *its own* sum type that wraps Phase 3's. This is the toolkit's Open/Closed principle applied at the sum-type boundary — "open for extension (Phase-4-local new variants), closed for modification (Phase 3's union stays frozen)."

## Consequences

- Phase 7's distroless plugin registers a new plugin per [ADR-0031](../../../production/adrs/0031-plugin-architecture.md); its plugin emits its own `Phase7Outcome` (if needed) wrapping `RecipeOutcome` the same way. No edits to Phase 3, 4, 5, or 6 code.
- Phase 11's merge-webhook harvester consumes `PlanOutcome` (or its Phase-7 sibling) via the event log; it does not need to widen any union.
- `RecipeOutcome` stays exactly `Applied | Skipped | Failed` for the life of the codebase. The fence test (`tests/property/test_plan_outcome_no_recipe_outcome_widening.py`) inherits to every future phase.
- Phase 4's audit chain emits both `PlanOutcome` (for harvester/operator-portal consumers) and the underlying `RecipeOutcome` (for Phase 3 orchestration consumers) — two events per outcome is acceptable cost for clean layering.
- Engineers reading Phase 4 must understand the wrapping pattern: `AppliedFromLlm` *contains* `RecipeOutcome.Applied`; consumers project to whichever sum type they're working with.
- The inline harvester's `match outcome` is over `PlanOutcome` (it cares about `AppliedFromLlm.few_shot_ref`); Phase 5's `GateRunner.match outcome` is over `RecipeOutcome` (it cares only about applied-vs-failed for retry).

## Reversibility

**Low.** Widening or shrinking `PlanOutcome` is Phase-4-local — Phase 4 owns every consumer. Reversing the choice (folding `PlanOutcome` back into a widened `RecipeOutcome`) is highly costly: every Phase 3/5/6 consumer needs new `case` arms, Phase 7's exit criterion breaks retroactively, and `tests/property/test_plan_outcome_no_recipe_outcome_widening.py` must be deleted (load-bearing fence test).

## Evidence / sources

- `../final-design.md §"Three load-bearing structural lines"` item 3
- `../final-design.md §Component 14 — PlanOutcome`
- `../final-design.md §Departures from all three inputs` item 1
- `../phase-arch-design.md §Goals — G3` (zero edits to kernel)
- `../phase-arch-design.md §Component design — PlanOutcome`
- `../critique.md §"[B] §5"` (RecipeOutcome widening breaks Phase 7)
- [production ADR-0031](../../../production/adrs/0031-plugin-architecture.md) (Phase 7's distroless plugin convention)
- [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) (sum types as a discipline)
- `roadmap.md §Phase 7` (exit criterion: diff touches only new plugin directory)
