# ADR-0040: Data lifecycle, retention, and classification

**Status:** Accepted  
**Date:** 2026-05-18  
**Tags:** data · governance · retention  
**Related:** ADR-0008, ADR-0024, ADR-0034

## Context

Portfolio-scale operation will persist repo context, audit events, prompts, evidence bundles, and cost data. The design previously described those stores without a single retention or classification policy.

## Decision

All persisted artifacts carry a data class (`public`, `internal`, `sensitive`, `restricted`) and an owning retention policy. Raw prompts, cassettes, and evidence bundles default to `sensitive`; cost summaries and derived metrics default to `internal`; secret-bearing material is never intentionally persisted.

## Tradeoffs

| Gain | Cost |
|---|---|
| Prevents indefinite growth and accidental over-retention | Adds lifecycle metadata to every durable artifact |
| Gives security review a concrete control surface | Some debugging material expires sooner |

## Consequences

- Every future durable store must define classification, retention, deletion, and legal-hold behavior.
- Phase 10 discovery and later portal views may project only data whose class allows it.
