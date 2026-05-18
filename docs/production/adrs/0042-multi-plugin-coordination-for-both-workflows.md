# ADR-0042: Multi-plugin coordination for `Both` workflows

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** orchestration · coordination · planning
**Related:** ADR-0011, ADR-0031, ADR-0038, ADR-0039

## Context

`vuln.provenance` introduces a `both` outcome when a CVE is present in app and base-image layers. The architecture previously named the case but lacked a coordination rule for whether one or two plugins should act.

## Decision

`Both` workflows are one parent remediation workflow with multiple coordinated plugin work items. The Planner owns sequencing, shared evidence, and cross-PR status; plugins remain independently responsible for their own transforms and validation.

## Tradeoffs

| Gain | Cost |
|---|---|
| Keeps multi-PR remediation coherent and auditable | Planning logic becomes more complex |
| Avoids hiding coordination inside one plugin | Some workflows now need parent/child state |

## Consequences

- Phase 8 must model parent workflow plus plugin work items.
- Phase 10 assessment surfaces `both` as a coordination candidate, not as two unrelated findings.
