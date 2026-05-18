# ADR-0002: Plugin-local subgraph topology with shared ports

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** plugins · orchestration

## Context

Production ADR-0031 says plugins own behavior, while shared infrastructure remains reusable.

## Decision

The Phase 6 LangGraph topology lives in `plugins/vulnerability-remediation--node--npm/subgraph/`. Reusable types and service ports remain in `src/codegenie/`.

## Tradeoffs

| Gain | Cost |
|---|---|
| Keeps task behavior co-located with the plugin | Shared node implementations need clean interfaces |
| Leaves Phase 7 free to own a different graph | Cross-plugin graph reuse is explicit, not automatic |

## Consequences

- Subgraph topology is not inherited.
- Existing plugin behavior remains isolated from future task classes.
