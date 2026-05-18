# S5-01 — Stable SUT adapter

**Status:** Ready  
**Goal:** Implement the concrete adapter behind `VulnRemediationSut` while keeping the graph builder private.

## Acceptance criteria

- Harness can call only the stable contract.
- Adapter returns sanitized result fields.
- `SutDigest` is deterministic for the same graph/config/prompt inputs.

## TDD plan

Red: contract-only consumer test.  
Green: implement adapter.  
Refactor: move private builder imports behind the adapter.
