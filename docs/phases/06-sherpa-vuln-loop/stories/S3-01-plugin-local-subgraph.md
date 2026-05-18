# S3-01 — Plugin-local subgraph

**Status:** Ready
**Goal:** Wire the vuln remediation graph under the plugin directory and compose existing Phase 3–5 ports.

## Acceptance criteria

- Graph package lives under the plugin.
- Planner, transform, and gate services are injected ports.
- No duplicate domain logic is introduced.

## TDD plan

Red: import-boundary test.
Green: add graph builder and node wiring.
Refactor: extract pure reducers.
