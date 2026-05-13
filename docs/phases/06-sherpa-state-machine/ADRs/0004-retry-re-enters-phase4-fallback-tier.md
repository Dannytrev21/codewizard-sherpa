# ADR-0004: Retry routes back to Phase 4's `FallbackTier.run` via a single `retry_phase4` edge

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** retry · phase4-integration · planner
**Related:** [ADR-0003](0003-per-gate-retry-counter-scope.md), [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md), [production ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md)

## Context

When `validate_in_sandbox` fails with `retryable=True` and `retry_count < max_attempts`, the graph has to do *something* to make the next attempt different. The three lenses disagreed:

- **Performance:** Re-apply the same `RecipeApplication`; the gate re-evaluates. Cheap, but `critique.md performance.1` landed: this directly violates Phase 5 exit-criterion #19 ("Phase 4's `FallbackTier.run` is invoked with `prior_attempts` and produces a *different* `RecipeApplication`") and the Phase 5 parity test for distinct patch bytes cannot pass.
- **Security:** Call `plan_llm` directly on retry — bypasses Phase 4's tier ordering. Works but skips RAG-on-retry and bakes recipe-vs-RAG-vs-LLM ordering into Phase 6.
- **Best-practices:** Route via `retryable_{engine}` f-string edges (three edges: `retryable_recipe`, `retryable_rag`, `retryable_llm`). `critique.md best-practices.3` flagged: if `last_engine` is `None` (e.g., a node crashed pre-write), the f-string produces `"retryable_None"`, which isn't in the conditional-edges mapping → KeyError at routing time.

The constraint is hard: Phase 5 exit-criterion #19 requires the retry to produce *distinct patch bytes* and Phase 4's prompt on attempt 2 to contain the fence-wrapped failure summary. Whatever shape Phase 6 ships must route through Phase 4's `FallbackTier.run(..., prior_attempts=...)` because that's where the recipe-vs-RAG-vs-LLM decision lives ([production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md)) and where the `prior_attempts` feedback semantics are implemented (ADR-P5-002).

## Options considered

- **Re-apply same recipe on retry.** Edge `retry_same_recipe`. Cheap; violates Phase 5 exit-#19; rejected by `critique.md performance.1`.
- **Three `retryable_{engine}` edges.** Encodes which tier to re-enter at the edge level; fragile to `last_engine=None`; duplicates Phase 4's tier ordering inside Phase 6.
- **Single `retry_phase4` edge, delegate to Phase 4.** One edge from `record_attempt` to `replan_with_phase4`. `replan_with_phase4` calls `FallbackTier.run(advisory, repo_ctx, recipe_selection, prior_attempts=state.prior_attempts)`. Phase 4 internally decides recipe / RAG / LLM. Phase 6 doesn't replicate the tier logic; the prior-attempts-aware re-planning is Phase 4's job.

## Decision

`route_after_attempt` returns a single `retry_phase4` label when retry conditions hold. That edge routes from `record_attempt` to `replan_with_phase4`, which calls `FallbackTier.run(advisory, repo_ctx, recipe_selection, prior_attempts=state.prior_attempts)`. Phase 4 owns the recipe-vs-RAG-vs-LLM decision on every retry, including the first call (which passes `prior_attempts=[]`). Phase 6's `replan_with_phase4` is the *only* node that imports from `codegenie.planner.fallback_tier`; the graph fence policy allows that one import.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 5 exit-criterion #19 is honored — retry produces distinct patch bytes via Phase 4 re-planning with fence-wrapped `prior_failure_summary` | Every retry pays Phase 4's LLM cost (3–8 s wall-clock and ~$0.01–0.05 in tokens, per Phase 4's own budget) — cheaper-retry strategies are forfeited |
| Phase 6 does not re-implement the recipe-vs-RAG-vs-LLM decision; Phase 4 owns it (single source of truth per [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md)) | A future "cheap retry" path (e.g., re-apply same patch under different sandbox config) cannot be added without amending this ADR |
| Topology is simpler — one retry edge instead of three; no `last_engine=None` failure mode | `replan_with_phase4` is the sole boundary between Phase 6 and any LLM-adjacent code, making it a fence-CI special case that future authors must preserve |
| HITL "continue" can reuse the same edge — routes to `replan_with_phase4` with `prior_attempts` intact (or reset, per Phase 6 design Gap 4) | The same-signature flake detector (ADR-0013) is the only short-circuit that prevents wasted Phase 4 invocations on a deterministic failure |

## Consequences

- `tests/integration/test_retry_reenters_phase4.py` is the **exit-criterion test** for this decision: asserts 2 entries in `attempts.jsonl` with distinct `attempt_id`, distinct `prior_failure_summary`, distinct `sandbox_run_id`, and **distinct patch bytes**.
- `replan_with_phase4` is fence-CI-allowed to import `codegenie.planner.fallback_tier` even though `graph/` cannot import `anthropic` directly — the Phase-4 module boundary is the trusted seam.
- Phase 4's `FallbackTier.run(advisory, repo_ctx, recipe_selection, prior_attempts=[])` signature is the contract Phase 6 depends on. ADR-P5-002 has already added `prior_attempts` as an additive kwarg; Phase 6 just uses it.
- The HITL `continue` route also lands on `replan_with_phase4`, not the previously-failed engine — so an operator-approved retry runs through Phase 4 re-planning, not a stale recipe re-application (`final-design.md §Component 6`).
- Phase 7's distroless loop ships its own `replan_with_phase4`-equivalent (`replan_with_phase4_for_distroless`? — Phase 7 decides) but the *shape* — single retry edge to a re-planner that consumes `prior_attempts` — is inherited.
- If Phase 4 ever exposes a cheaper retry primitive (e.g., `FallbackTier.retry_same(...)` for same-recipe retries), this ADR is the right place to record the amendment.

## Reversibility

**Medium.** Reverting to a "re-apply same recipe" path would break Phase 5 exit-criterion #19, the parity test, and the retry-bytes-distinct integration test simultaneously; the test failures localize the problem but the rollback would force amending Phase 5's exit criterion in lockstep. Adding a sibling cheap-retry edge (alongside `retry_phase4`) is reversible — it would be a topology extension, not a contract break.

## Evidence / sources

- [`../final-design.md` §Component 6 "replan_with_phase4"](../final-design.md)
- [`../final-design.md` §Synthesis ledger row 3 "Retry path"](../final-design.md)
- [`../final-design.md` §Goals row 5 "Retry feedback semantics honor Phase 5 exit-criterion #19"](../final-design.md)
- [`../phase-arch-design.md` §Component design — Nodes table](../phase-arch-design.md)
- [`../critique.md` §performance.1](../critique.md) — the "same recipe re-applied" rejection
- [Production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) — recipe-first → RAG → LLM ordering is Phase 4's job, not Phase 6's
