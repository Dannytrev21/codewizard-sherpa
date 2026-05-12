# ADR-0018: Hierarchical Planner — pure routing vs LLM-driven

**Status:** Deferred
**Date:** 2026-05-11
**Tags:** orchestration · cost
**Related:** ADR-0001, ADR-0002

## Context

The Hierarchical Planner / Supervisor (Layer 1) reads intent and dispatches to the appropriate subgraph. The intent space in Phase 1 is small and well-structured: "Migrate to distroless," "Fix CVE-X," "Upgrade Y version," with structured metadata attached. Routing based on intent type is mostly a lookup.

Two implementation choices:
- **Pure routing** — a deterministic classifier (intent.task_type → subgraph) plus structured rules. Cheap, predictable, deterministic.
- **LLM-driven supervisor** — an LLM reads the request (potentially natural language) and decides which subgraph, optionally with task decomposition logic.

The SHERPA paper allows ML-driven decisions in state-machine routing; it does not require them.

## Options considered

- **Pure routing.** Intent.task_type is a structured field on the input event. Switch statement → subgraph. No LLM.
- **LLM-driven supervisor.** LLM reads the request and emits structured routing output. Higher cost; can handle natural-language requests; can also decompose composite tasks ("Migrate every Node service AND upgrade them to Node 20").
- **Hybrid.** Default to pure routing; fall back to LLM only when the intent.task_type is unrecognized or the request is natural-language.

## Default until decided

**Pure routing for Phase 1.** The intent space is bounded (3–5 task types), the input comes from structured triggers (CVE feed, Stage 0 Discovery, scheduled jobs), and the supervisor's job is dispatch, not creativity.

LLM-driven supervisor is an upgrade path, not a Phase 1 requirement.

## Evidence needed to resolve

- **Intent-distribution data.** How many distinct intent types arise in production? If <10, pure routing trivially handles them.
- **Natural-language request volume.** Are humans submitting prose requests, or do all triggers come structured? If prose volume > ~5% of total, LLM-supervisor becomes attractive.
- **Composite-task frequency.** How often does one request decompose into multiple subworkflows? Pure routing handles this via Temporal child workflows; LLM-supervisor handles it more elegantly.
- **Cost data.** What does each LLM-supervisor invocation cost at the planned token budget?

## Reversibility (of the eventual choice)

**Low cost.** The supervisor is a single LangGraph node — its implementation can be swapped between pure-routing and LLM-driven without touching subgraphs. The Pydantic state ledger carries the routing decision either way.

## Evidence / sources

- `../design.md §4.1` (Layer 1 — Hierarchical Planner)
- `../design.md §7` (Open questions — Hierarchical Planner implementation)
- arXiv 2509.00272 — SHERPA paper allows ML-driven decisions in routing
