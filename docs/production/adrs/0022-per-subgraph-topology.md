# ADR-0022: Per-subgraph topology — when to extract shared structure

**Status:** Deferred
**Date:** 2026-05-11
**Tags:** orchestration · refactor
**Related:** ADR-0002, ADR-0010

## Context

Each task type gets its own SHERPA-disciplined subgraph: Migration Subgraph, Vulnerability Subgraph, future Language-Upgrade Subgraph, etc. Each subgraph has its own state model, its own node sequence, and its own gate configurations.

The two example subgraphs in `../design.md §4.5` are similar in shape (linear progression with gate-at-every-edge) but different in node names, gate strictness, and state model. The question is: when should shared structure be extracted into a reusable base, and what should be left subgraph-specific?

Premature abstraction risks coupling subgraphs in ways that make later changes harder. Premature duplication makes consistency fixes painful.

## Options considered

- **Pre-design shared structure.** Identify common patterns up front; build a `BaseSubgraph` class with hooks. Risk: the abstraction is wrong because we lack production data.
- **Pure duplication, refactor later.** Every subgraph is independent; extract common structure only once 3+ concrete subgraphs exist and the pattern is visible. Three Strikes And You Refactor.
- **Shared mixins / helpers from day one.** Build common Pydantic state base classes, common gate runners, common retry logic — but no `BaseSubgraph` inheritance. Composition over inheritance.

## Default until decided

**Pure duplication for the first two subgraphs (Migration and Vulnerability).** Build each independently, with full freedom to differ in state shape, node sequence, and gate config. Extract shared structure when a third subgraph reveals the pattern.

Three Strikes And You Refactor.

## Evidence needed to resolve

- **Third subgraph implementation.** Language-Upgrade Subgraph or similar — implementing it will reveal which parts are genuinely shared (gate runner, retry counter, knowledge-graph lookup) and which are subgraph-specific (state shape, node sequence).
- **Maintenance experience.** After 3–6 months of evolving the first two subgraphs, where did consistency-bug fixes show up? Those are the abstraction targets.
- **State-model overlap.** If 80% of state fields are shared across subgraphs, a base Pydantic model is justified. If only 20%, composition is better.

## Reversibility (of the eventual choice)

**Medium-high cost** to extract abstraction *after* subgraphs are mature — refactoring three concrete subgraphs into a shared base touches a lot of code. **Low cost** to add an abstraction earlier and rip it out — but the rip-out is the same painful refactor in reverse.

Three Strikes And You Refactor minimizes the regret either way.

## Evidence / sources

- `../design.md §4.5` (both worked subgraph examples — Migration and Vulnerability)
- `../design.md §7` (Open questions — Per-subgraph topology)
- `../design.md §8.8` (Migration Subgraph state diagram as the concrete reference for the pattern)
- Three Strikes And You Refactor — Martin Fowler / Don Roberts
