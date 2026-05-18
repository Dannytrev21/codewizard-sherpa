# S2-01 — Semantic checkpoints

**Status:** Ready
**Goal:** Persist workflow checkpoints only at the semantic boundaries named in ADR-0003.

## Acceptance criteria

- Checkpoints append at plan, patch, gate, interrupt, and terminal boundaries.
- Golden ordering test is deterministic.
- Payload size remains bounded.

## TDD plan

Red: golden checkpoint-order test.
Green: append logic.
Refactor: share canonical serialization helpers.
