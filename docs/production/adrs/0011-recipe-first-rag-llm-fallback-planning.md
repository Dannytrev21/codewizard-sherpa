# ADR-0011: Recipe-first → solved-example RAG → LLM-fallback planning order

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** planning · cost
**Related:** ADR-0005, ADR-0008

## Context

Stage 3 Planning emits the step files that Stage 4 Execution will apply. The agent has three plausible ways to plan:

1. **Recipe**: a deterministic transformation library (OpenRewrite for Java; `rewrite-docker` for Dockerfiles; internal rulesets) matched against the `RepoContext`. Fast, idempotent, no LLM cost, no creativity.
2. **Solved-example RAG**: vector search over the knowledge graph for a prior migration that closely matches this `RepoContext` fingerprint. The matched example becomes few-shot input to the LLM.
3. **LLM from scratch**: the LLM plans against the `RepoContext` plus the matched Skill. Most flexible, most expensive, most prone to hallucination.

The order in which these are tried is consequential. Cost, quality, and reproducibility all depend on it.

## Options considered

- **LLM-first.** Let the LLM plan; use recipes as a sanity check. Maximum flexibility, maximum cost, maximum risk.
- **Recipe-only.** Only execute changes that map to a known recipe. Reject everything else. Highest reliability, narrowest coverage.
- **Recipe → RAG → LLM (the three-tier fallback).** Try the cheapest, most reliable option first; fall through tiers if no match.

## Decision

Stage 3 Planning is a SHERPA subgraph with four nodes:

```
Recipe_Matcher → Solved_Example_RAG_Retriever → LLM_Planner → Step_Emitter
```

Transitions:
- `Recipe_Matcher` finds a deterministic transformation → skip directly to `Step_Emitter`. No LLM invoked.
- No recipe match, but `Solved_Example_RAG_Retriever` finds a high-similarity prior solution → LLM plans with that example as few-shot.
- Neither recipe nor solved example matches → LLM plans from scratch with `RepoContext` and matched Skill as context.
- All three failed → escalate to human (Trust-Aware retry exhaustion, ADR-0014).

## Tradeoffs

| Gain | Cost |
|---|---|
| Cheap path for the common case — most distroless migrations match a recipe | Subgraph topology is more complex than a single LLM-plan node |
| Quality scales with the knowledge graph — every successful merge adds a solved example for Worker #N to reuse (the Scenario B effect from `../design.md §4.5`) | Recipes must be maintained as the OpenRewrite / internal-ruleset library evolves |
| LLM cost is bounded: not invoked when recipe matches; few-shot grounded when solved example matches | Planning latency per repo can be unpredictable — recipe match is ms, LLM-from-scratch is seconds |
| Stage 7 Learning has a clear deposit target (the solved-example store) | Cold start: no solved examples until the system has shipped real migrations |

## Consequences

- The knowledge graph (ADR-0017) is dual-purpose: it indexes both deterministic recipes (lookup keyed by `RepoContext` fingerprint) and solved examples (vector-similarity search). The architecture treats them as related but distinct stores.
- Recipe authoring becomes a high-leverage activity. A recipe that covers 10% of repos eliminates LLM spend on those 10%.
- Stage 3's subgraph state machine has the canonical "tiered fallback" shape; other stages can adopt it as the pattern proves out.
- The Konveyor Kai pattern of solved-example retrieval (`../../auto-agent-design.md §2.1`) is directly inherited.

## Reversibility

**Low cost.** Reordering nodes or removing one (e.g., LLM-first if we change cost stance) is a localized subgraph change. The Step File output contract is stable regardless of which node emits the plan.

## Evidence / sources

- `../design.md §3` Stage 3 description
- `../design.md §4.4` (Stage 3 maps to a SHERPA subgraph)
- `../design.md §4.5` Scenario B — solved-example reuse (Worker #45 benefits from Worker #2)
- `../../auto-agent-design.md §2.1` — Konveyor Kai's solved-example pattern
- `../../auto-agent-design.md §2.2` — OpenRewrite recipes
