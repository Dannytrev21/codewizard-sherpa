# ADR-0011: The recipe→RAG→LLM router is a fixed three-step pipeline, not a registry

**Status:** Accepted
**Date:** 2026-05-21
**Tags:** Pipeline (fixed steps) · Hexagonal / ports & adapters · anti-decision: no premature pluggability
**Related:** ADR-0001, [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md), [production ADR-0018](../../../production/adrs/0018-supervisor-pure-routing-vs-llm.md), [production ADR-0020](../../../production/adrs/0020-leaf-agents-sdk.md)

## Context

`PlannerNode.route` decides whether a workflow enters at the recipe tier, the RAG tier, or the LLM tier — and logs the decision. [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) fixes the order: recipe-first, then solved-example RAG, then LLM-fallback — exactly three tiers.

Phase 8 must decide how to *structure* those three steps. [critique.md §Design-pattern critiques](../critique.md#design-pattern-critiques-cross-cutting) shows two lenses labeled the recipe→RAG→LLM chain "Chain of responsibility" — and the critic rejects the label: "CoR is about a *runtime-variable, decoupled* set of handlers where the sender does not know which handler responds. Three hardcoded steps in a fixed order, where the caller knows exactly the three and their order, is a pipeline / an `if-elif-else`." A registry (`@register_planning_step`) for three fixed, ADR-0011-mandated steps would be premature pluggability. Separately, the RAG tier has no real backend in Phase 8 — the Knowledge Graph arrives in Phase 11 — so the RAG step needs a concrete-but-empty adapter.

## Options considered

- **Option A — A `@register_planning_step` strategy registry.** Routing tiers register themselves; `route` iterates the registry. **Pattern:** Strategy registry — but the toolkit flags "Strategy with a single [or fixed] set of implementations = unnecessary indirection." Three steps fixed by ADR-0011 are not a runtime-variable set; a registry is premature pluggability (toolkit "flag on sight").
- **Option B — A class hierarchy / Chain-of-Responsibility handler set.** Each tier is a handler that processes or passes. **Pattern:** Chain of responsibility — *mislabeled* here; CoR is for decoupled, runtime-variable handlers. Three steps the caller knows exactly is not CoR.
- **Option C — A fixed ordered `tuple[(PlanningRoute, port-callable), ...]` iterated in order; first hit wins; fallthrough is `LLM`.** The three tiers are reached through `RecipeMatchPort`, `SolvedExampleRagPort`, `LeafLlmPort` (Protocols); the RAG port is a `NullRagPort` in Phase 8. **Pattern:** Pipeline (fixed steps) + Hexagonal / ports & adapters.

## Decision

`PlannerNode.route` is a **fixed three-step pipeline**: an ordered `tuple[(PlanningRoute, port-callable), ...]` iterated in order, first hit wins, fallthrough is `LLM`. There is **no registry and no class hierarchy** — exactly three steps fixed by ADR-0011. Each tier is reached through a `Protocol` Port (`RecipeMatchPort`, `SolvedExampleRagPort`, `LeafLlmPort`); the RAG Port is a **`NullRagPort`** in Phase 8 (the KG arrives Phase 11), so the three-step *shape* is correct from day one and Phase 11 swaps the adapter with zero routing-code change. This is the **Pipeline (fixed steps)** pattern with **Ports and adapters** at each tier boundary.

## Tradeoffs

| Gain | Cost |
|---|---|
| The honest shape — three known, ordered steps — is an ordered `tuple` iterated; no registry indirection for a fixed set | Adding a *fourth* routing tier later means editing the tuple — but ADR-0011 fixes exactly three, so a fourth would itself need an ADR |
| Each tier is a `Protocol` Port — the routing *logic* stays LLM-free and `import-linter`-fenced; the LLM is a leaf behind `LeafLlmPort` | The `NullRagPort` means the RAG branch is fake-port-tested, not real-data-tested, until Phase 11 |
| `NullRagPort` keeps the three-step shape from day one — Phase 11 swaps in the KG adapter with zero routing-code change | In Phase 8 the planner effectively makes a recipe-or-LLM decision; the RAG path is structurally present but unreachable with real data (a documented gap, edge-case-tested) |
| The selection logic is pure and 100%-branch-coverable — three steps, no dynamic dispatch to reason about | A reviewer expecting a pluggable router must read this ADR to see why a fixed tuple is deliberate |

## Pattern fit

The toolkit's "Chain of responsibility / Pipeline" entry names "the recipe → RAG → LLM-fallback decision chain" as a pipeline example, and its anti-pattern list flags "premature pluggability — we made it pluggable in case… with one [fixed set of] implementation. YAGNI. If there's exactly one strategy, it's a function." Three ADR-0011-fixed steps are a pipeline, not a registry and not Chain of Responsibility (which requires runtime-variable, decoupled handlers). The Ports (`RecipeMatchPort`, `SolvedExampleRagPort`, `LeafLlmPort`) are the toolkit's "Hexagonal" pattern — the planner crosses a technology boundary (LLM, KG) through interfaces, keeping the routing core LLM-free. `NullRagPort` is the toolkit's honest "wait for the second implementation" discipline applied forward — the Port exists, the real adapter lands when the KG does.

## Consequences

- `PlannerNode.route` iterates a fixed ordered `tuple` of `(PlanningRoute, port-callable)`; first hit wins; `LLM` is the fallthrough.
- `RecipeMatchPort`, `SolvedExampleRagPort`, `LeafLlmPort` are `Protocol`s; concrete adapters are injected.
- `codegenie.planner.routing` is `import-linter`-fenced against every LLM SDK — the routing *logic* is LLM-free; the LLM is reached only through `LeafLlmPort`.
- The RAG Port is a `NullRagPort` in Phase 8 — structurally present, fake-port-unit-tested; Phase 11 swaps the KG-backed adapter in with zero routing-code change.
- The selection logic is pure and 100%-branch-covered (it is an exit-criteria-bearing function).
- Adding a fourth routing tier would require editing the tuple *and* an ADR amendment to ADR-0011 — extension here is deliberately gated, not free.
- A `route()` misprediction (recipe stale) is handled by Phase 4's `FallbackTier` descent; a `RouteDescended` event makes the misprediction rate a measured number.

## Reversibility

**High.** The fixed tuple is a few lines; converting it to a registry later (if a genuine runtime-variable tier set ever emerged) is a localized refactor — and would correctly be gated by an ADR-0011 amendment. The `NullRagPort` → KG-adapter swap is the *designed* evolution (Phase 11) and is zero-routing-code-change by construction. Nothing about the fixed-pipeline choice is hard to revisit; the ADR records *why* the simple shape is correct *now*.

## Reversibility note — the anti-decision

This ADR is partly an **anti-decision**: it records that a Strategy registry and a Chain-of-Responsibility handler set were *deliberately not* introduced. The tempting pattern was pluggability (a `@register_planning_step` registry mirroring `@register_probe`); the anti-pattern it would have created is "premature pluggability" — registry machinery for a set of three steps ADR-0011 fixes. A future engineer who wants to "make the router extensible" should read this ADR first: the extension point is an ADR-0011 amendment, not a registry.

## Evidence / sources

- ../phase-arch-design.md §C3 — PlannerNode; "a fixed three-step pipeline"
- ../phase-arch-design.md §Patterns considered and deliberately rejected — Strategy registry, Chain of responsibility
- ../final-design.md §Pattern reconciliation — "Chain of responsibility… Renamed to Pipeline"
- ../critique.md §Design-pattern critiques — "Chain of responsibility (preserved)" mislabel
- ../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md — the fixed three-tier order
- ../../../production/adrs/0018-supervisor-pure-routing-vs-llm.md; ../../../production/adrs/0020-leaf-agents-sdk.md
- `design-patterns-toolkit.md` §Chain of responsibility / Pipeline; §Anti-patterns — "Premature pluggability"
