# ADR-0001: Stable `VulnRemediationSut` contract for harness consumers

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** contract · eval · phase-boundary

## Context

Phase 6.5 needs a system-under-test, but binding it to a concrete graph builder would make harness docs and future code depend on Phase 6 internals.

## Decision

Phase 6 exposes `VulnRemediationSut`, `VulnRemediationCase`, `VulnRemediationResult`, and `SutDigest` as the harness-facing contract. The concrete LangGraph builder remains private.

## Tradeoffs

| Gain | Cost |
|---|---|
| Eval harness survives graph refactors | One more explicit contract to version |
| Bench cache keys gain a stable digest seam | Some graph-only diagnostics must be summarized into result fields |

## Consequences

- Phase 6.5 imports the contract only.
- Contract changes require ADR amendment and downstream review.
