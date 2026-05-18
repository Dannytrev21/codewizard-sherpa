# ADR-0002: `FallbackTier` as a named sequential Pipeline — no LangGraph in Phase 4

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** pipeline · open-closed · phase-boundary · roadmap-coherence
**Related:** ADR-0004 (this phase) · [production ADR-0002](../../../production/adrs/0002-langgraph-as-runtime-sherpa-as-discipline.md) · [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md)

## Context

The recipe → RAG → LLM dispatch order is fixed by [ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md): try the cheapest most-reliable tier first; fall through on no-match. Phase 4 has to implement that dispatch. The three design lenses proposed three structures: performance shipped a `TierChain` async generator (each tier a yield-point); best-practices shipped a LangGraph three-node `StateGraph` (forward-compat with Phase 6's runtime); security shipped a short sequential Pydantic-orchestrating class (`FallbackTier`).

The critic surfaced two load-bearing problems with the LangGraph-in-Phase-4 path (`critique.md §"[B] §1"`): (a) the roadmap explicitly names Phase 6 as the *LangGraph introduction phase*; importing it in Phase 4 takes on the largest Phase 6 dep one phase early, and (b) the actual topology is three flat nodes with no conditional edges and no checkpointer — there is nothing to "lock." The critic also surfaced one with `TierChain` (`critique.md §"[P] §1"`): the async-generator yield-point ceremony is overhead for an `if/elif` ladder, and it carries `DeterministicRetargeter` as a non-existent tier (rejected separately).

Phase 5 has already merged a `FallbackTier.run(advisory, repo_ctx, recipe_selection, *, prior_attempts=[]) -> RecipeApplication` signature. Whatever we ship in Phase 4 must produce that signature. Phase 6 will mechanically lift this callable into a LangGraph node; the lift is one decorator if the callable is a plain `def run(...)`.

## Options considered

- **`TierChain` async generator** (performance lens). Each tier yields a `TierResult`; coordinator drives the iteration. **Pattern:** Iterator pattern / generator coroutine. Reduces dispatch overhead by ~10 ms but introduces an async-iteration protocol Phase 6 will subsume; carries `DeterministicRetargeter` fan-fiction.
- **Three-node LangGraph `StateGraph`** (best-practices lens). `FallbackPlan` graph with `_LlmReplanState` mutable Pydantic record passed through nodes. **Pattern:** State machine + LangGraph node graph. Lifts Phase 6 dep into Phase 4 one phase early; forces the codebase's single `frozen=False` Pydantic exception (`_LlmReplanState`); the lift Phase 6 supposedly gains is mechanical-or-bigger either way.
- **Short sequential `FallbackTier` class with one `async def run(...)`** (security lens). Provenance → budget → retrieval → prompt-build → leaf-invoke → reconcile, each step a named method call emitting one audit event. **Pattern:** Pipeline (named, sequential, short-circuiting).
- **Chain-of-Responsibility Protocol** (none of the three; alternate consideration). Define a `Tier` Protocol with `handle(ctx) -> Result | PassToNext`; register tiers; coordinator iterates. **Pattern:** Chain of Responsibility (GoF). Rejected: there are exactly three tiers, the order *is* the policy ([ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md)), and CoR's `passToNext` indirection adds nothing here.

## Decision

`FallbackTier` is a single `async def run(...)` composed as a short, named, sequential pipeline: `provenance.classify → budget.running_total → (retrieval | retry-bypass) → prompt-build → budget.precharge → leaf.invoke → budget.reconcile → build Transform → return RecipeApplication`. Each step emits one audit event. **No LangGraph, no async generator, no Chain-of-Responsibility Protocol.** **Pattern:** Pipeline (named, sequential, short-circuiting). Phase 6 mechanically lifts `FallbackTier.run` into a LangGraph node; the test fixture `tests/fixtures/fallback_tier_callable.py` is the contract Phase 6 reads.

## Tradeoffs

| Gain | Cost |
|---|---|
| Roadmap coherence — Phase 6 remains the LangGraph introduction phase per `roadmap.md` | Phase 6's migration is one decorator + state-shape adapter (still mechanical; no extra dep saved) |
| Zero new framework deps in Phase 4 — `anthropic`, `chromadb`, `fastembed` are the only new runtime additions | Three flat method calls don't look "architectural"; engineers reading the file may want pattern-soup ceremony — resisted explicitly |
| Every step is one async method emitting one audit event — debuggability is a sequence diagram, not a graph traversal | Hedging or tier-skipping would require explicit code (vs LangGraph's conditional edges); we accept this — the chain order *is* the policy |
| Phase 5's already-merged `run(..., prior_attempts=[]) -> RecipeApplication` signature works unchanged | Future tier additions (e.g., Phase 13's cost-aware re-rank) need an ADR amendment, not a graph-edge config change |
| Mutable state stays in *external* collaborators (budget guard, event log) — no `frozen=False` Pydantic model | Async-step ordering bugs are now logic bugs in one file, not topology bugs in a graph definition (test coverage on dispatch order is mandatory — `tests/unit/fallback/test_fallback_tier.py`) |

## Pattern fit

The toolkit names Pipeline / Chain of Responsibility as the patterns for "the recipe → RAG → LLM-fallback decision chain" — but warns CoR is `passToNext` indirection ("each can process, pass, or short-circuit"). Here every short-circuit is *named* (`Refused(PROVENANCE_NOT_APP_LAYER)`, `Refused(BUDGET_EXCEEDED)`, `Refused(LEAF_*)`), every step is *named*, and there are exactly three handlers. Calling this "Chain of Responsibility" inflates the `for` loop; calling it "LangGraph state machine" inflates the framework. The honest name is Pipeline (named, sequential, short-circuiting) — what's actually shipped.

## Consequences

- Phase 6's LangGraph migration is a wrapper, not a refactor: `@graph_node async def fallback_plan(state: State) -> State: result = await fallback_tier.run(...); return state.update(result)`.
- `_LlmReplanState` (best-practices' mutable Pydantic record) is *not* shipped; the codebase keeps its `frozen=True, extra="forbid"` discipline unbroken (commitment §"`extra='forbid'` everywhere").
- The Phase 6 migration cost is now visible: it's the topology *plus* checkpointer integration *plus* state-shape glue. None of those depend on Phase 4's shape.
- `tests/fence/test_no_langgraph_in_phase4.py` AST-walks every Phase 4 module asserting no `import langgraph`.
- `langgraph` remains in `FORBIDDEN_LLM_SDKS` (Phase 0 fence) — Phase 6 amends, not Phase 4.
- Async-step ordering is testable in isolation (`tests/unit/fallback/test_fallback_tier.py` mocks every collaborator) — graph-traversal tests are not needed.
- Phase 13's cost-aware tier re-ranking (deferred), Phase 11's concurrent-write upgrade, and any future tier additions need a Phase-4-amendment ADR rather than a config flip — *the chain order is the policy*.

## Reversibility

**Medium.** Lifting `FallbackTier.run` into a LangGraph node (Phase 6's job) is mechanical and low-risk. Going the other way — replacing Pipeline with a Chain-of-Responsibility `Tier` Protocol — is straightforward syntactic refactoring but rarely useful (the policy isn't pluggable). Reintroducing LangGraph *in Phase 4* would require reverting Phase 6's introduction and re-justifying the dep weight; high friction, contradicts the roadmap.

## Evidence / sources

- `../final-design.md §"Three load-bearing structural lines"` item 1
- `../final-design.md §Component 1 — FallbackTier — "Why this choice over alternatives"`
- `../final-design.md §Patterns considered and deliberately rejected` (LangGraph state machine; TierChain async generator)
- `../phase-arch-design.md §Non-goals` (No `langgraph` in Phase 4)
- `../phase-arch-design.md §Design patterns applied` row 1
- `../critique.md §"Attacks on the best-practices design"` items 1, 3
- `../critique.md §"Attacks on the performance-first design"` item 1
- [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) (the chain order)
- [production ADR-0002](../../../production/adrs/0002-langgraph-as-runtime-sherpa-as-discipline.md) (LangGraph is the runtime — but Phase 6 introduces it)
- `roadmap.md §Phase 6` (LangGraph introduction phase)
