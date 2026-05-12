# ADR-0021: Policy engine — build vs adopt RuleZ

**Status:** Deferred
**Date:** 2026-05-11
**Tags:** platform · safety
**Related:** ADR-0001, ADR-0012

## Context

The Trust-Aware layer integrates a deterministic policy engine that intercepts every tool call and state transition with sub-10ms latency, returning allow / block / inject-context. This is the "Agent RuleZ" pattern described in `../../gemini-auto-agent-design.md §"Deterministic Policy Engines"`.

The pattern is well-described; a reference implementation (`agent_rulez`) exists. The question is whether to adopt the library directly or build a project-specific equivalent on top of LangGraph's `conditional_edge` primitives.

## Options considered

- **Adopt `agent_rulez` directly.** Use the library's YAML policy DSL, hook model, and metadata-emission. Fastest to start. Vendor/library dependency.
- **Build on LangGraph `conditional_edge` primitives.** Conditional edges in LangGraph are already evaluation hooks. Layer a small "rules → conditional logic" helper on top. Fewer external dependencies, more code to maintain.
- **Hybrid: build a minimal helper, adopt RuleZ later if the policy DSL becomes a productivity multiplier.** Default to building; reserve the right to adopt.

## Default until decided

**Build a minimal helper on top of LangGraph `conditional_edge` primitives for Phase 1.** Reasoning:

- The policy surface in Phase 1 is small (block force-push, block unallowed network calls, block non-allowlisted base images, mandatory PR labels). A YAML DSL is overkill until the surface grows.
- LangGraph's edges are already evaluation points. Wrapping them with a small "policy hook" helper is ~100 lines of code.
- Adopting an external library now creates a dependency on an evolving project — its API may shift.
- If the policy surface grows to dozens or hundreds of rules, the DSL ergonomics of `agent_rulez` become attractive and an upgrade is straightforward.

## Evidence needed to resolve

- **Rule count growth.** If the policy catalog grows past ~30 rules, a DSL becomes worth its keep.
- **Author-engineer experience.** Are platform engineers writing rules, or is this developer-facing? A DSL helps non-engineers; Python predicates help engineers.
- **Policy iteration velocity.** How often do rules change? Frequent changes favor a DSL with hot reload.
- **`agent_rulez` library maturity.** Is it stable enough for production dependency? Check release cadence, breaking-change history, maintainer responsiveness.

## Reversibility (of the eventual choice)

**Medium.** Adopting `agent_rulez` later requires migrating Python predicates to YAML rules (manual translation). Going from `agent_rulez` to in-house is similar — rewrite YAML as Python.

## Evidence / sources

- `../design.md §4.1` (Layer 3 — Trust-Aware gates are the natural Agent RuleZ integration point)
- `../design.md §5` (Identity and tool governance subsection)
- `../design.md §7` (Open questions — Policy engine: build vs adopt)
- `../../gemini-auto-agent-design.md §"Deterministic Policy Engines"` — Agent RuleZ pattern description
