# ADR-0001: `Recipe.engine` Literal extends to include `rag_llm` and the orchestrator gains one conditional branch

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** contract · extension-by-addition · phase-3-edit · synthesizer-departure
**Related:** [ADR-0002](0002-two-tier-writeback-pending-promoted.md), [Phase 3 ADR-0001](../../03-vuln-deterministic-recipe/ADRs/0001-transform-recipe-engine-two-abc-contract.md), [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md), [production ADR-0028](../../../production/adrs/0028-task-class-introduction-order.md)

## Context

Phase 3 froze a public `Recipe.engine: Literal["ncu","openrewrite"]` Pydantic field and a six-call linear `RemediationOrchestrator`. Phase 4 ships the LLM fallback as a third `RecipeEngine` (`RagLlmEngine`) per [Phase 3 ADR-0001](../../03-vuln-deterministic-recipe/ADRs/0001-transform-recipe-engine-two-abc-contract.md), and persists solved examples on success. Both edges touch the Phase 3 contract: the engine Literal must admit a new value, and the orchestrator must learn to call `writeback_solved_example` after `TrustScorer.passed` *only when* the engine that produced the diff was `rag_llm`.

`CLAUDE.md §2.5` says "extension by addition." Editing the engine Literal and adding an orchestrator conditional are *additive in behavior* but *contractual edits in syntax* — the Phase 3 contract-snapshot test regenerates. The critic flagged this explicitly (`critique.md §best-practices.3`): ADR-gating does not make a contract edit additive. The synthesis accepts the edits and surfaces them as deliberate roadmap-level decisions rather than hiding them.

## Options considered

- **New orchestrator entrypoint that wraps Phase 3.** Performance-lens proposal: `remediate_v2` wraps `RemediationOrchestrator` and inserts the writeback after Phase 3 returns. Avoids editing Phase 3's call graph but doubles the orchestrator surface area, drifts diagnostics between two top-level commands, and means Phase 6's LangGraph wrap has two orchestrators to swallow.
- **New `LlmEngine` sibling ABC alongside `RecipeEngine`.** Performance's `ManualPatchEngine` proposal. Honors the deterministic-engine contract by not overloading it but doubles the engine ABCs and gives `RecipeSelector` two collection axes to iterate. The critic accepted the conflation as the better tradeoff (`critique.md §best-practices.1`) provided the `FallbackTier` mediator owns LLM-specific failure modes.
- **`FallbackRouter` inserted between Phase 3 stages.** Security-lens proposal. Same orchestrator-edit penalty as the chosen option, plus a new top-level component that doesn't compose with the selector chain Phase 3 already cut.
- **Two surgical edits to Phase 3.** Extend `Recipe.engine` Literal; add one conditional branch after `TrustScorer.passed`. Both gated by Phase 4 ADRs and the Phase 3 contract-snapshot test regenerates as a Phase 4 PR step.

## Decision

`Recipe.engine: Literal["ncu","openrewrite"]` extends to `Literal["ncu","openrewrite","rag_llm"]`. `RemediationOrchestrator` gains exactly one conditional branch after `TrustScorer.passed`: `if recipe_application.engine_used == "rag_llm": writeback_solved_example(...)`. No other Phase 0–3 code is edited. Phase 3's contract-snapshot test regenerates; the PR carries a `phase-3-contract-bumped` label so the edit is conspicuous.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 6 wraps one orchestrator, not two | Phase 3's contract-snapshot test regenerates, which is the snapshot test admitting it no longer protects what it was supposed to |
| Phase 7 (distroless) extends the same Literal — the precedent is set and the regen is mechanical | `CLAUDE.md §2.5` literal reading violated; surfaced as deliberate roadmap-level decision |
| `RecipeApplication.engine_used` carries the discriminator the writeback branch needs without a sidecar tag | One additional value to maintain in every exhaustive `match`/`if` over `engine` (mypy `assert_never` catches the misses) |
| Writeback logic lives in the orchestrator next to `TrustScorer` — the only place that knows trust passed | Future task classes will each add a value to the Literal; without a registry, the Literal grows linearly |

## Consequences

- The Phase 3 contract-snapshot test (`tests/contracts/test_recipe_engine_literal.py`) regenerates. The PR diff is one line; review focuses on the deliberateness.
- `RecipeSelector.engines = [Ncu, OpenRewriteStub, RagLlm]` — `RagLlmEngine.applies()` returns True only on a Phase 3 fallback reason (`catalog_miss`, `range_break`, `peer_dep_conflict`, `no_engine`, `unsupported_dialect`); never on a cold start.
- The orchestrator's branch is the only Phase 3 call-graph edit in Phase 4. Phase 5's retry-with-context and Phase 6's LangGraph wrap operate from *outside* the orchestrator — neither widens this precedent.
- Phase 7's distroless engine will repeat the same edit shape (extend the Literal, add a writeback branch). The two-edit precedent is now the documented pattern, not an exception.
- The `engine_used == "rag_llm"` discriminator is the single gate that controls writeback. Engine-spoof attempts (a non-`rag_llm` engine returning a `RecipeApplication` that *claims* to be `rag_llm`) are blocked by `writeback_solved_example`'s strict guard (see [ADR-0002](0002-two-tier-writeback-pending-promoted.md)).

## Reversibility

**Medium.** Removing `rag_llm` from the Literal requires deleting `RagLlmEngine`, unwinding the writeback branch, and migrating any persisted `RecipeApplication` payloads. Adding *another* engine value (Phase 7) is mechanical. Replacing the Literal with a registry (Phase 8+, if the value count grows past ~6) is a one-pass refactor of the snapshot test.

## Evidence / sources

- `../final-design.md §"Roadmap coherence check" §"New ADRs implied"` — ADR-P4-001, ADR-P4-002
- `../phase-arch-design.md §"Executive summary"` — "two ADR-gated additive edits"
- `../phase-arch-design.md §"Architectural context"` — diagram + caption
- `../critique.md §best-practices.3` — the contract-edit honesty argument
- `../../03-vuln-deterministic-recipe/ADRs/0001-transform-recipe-engine-two-abc-contract.md` — the contract being extended
- Production [ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) — the three-tier shape Phase 4 realizes
- Production [ADR-0028](../../../production/adrs/0028-task-class-introduction-order.md) — task-class introduction order
