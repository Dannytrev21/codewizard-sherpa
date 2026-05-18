# S4-01 — HITL interrupt and resume

**Status:** Ready
**Goal:** Emit typed HITL interrupts and validate resume input before continuation.

## Acceptance criteria

- Retry exhaustion enters `AwaitingHumanReview`.
- Resume rejects stale or malformed approval payloads.
- Approved resume continues from latest verified checkpoint.

## TDD plan

Red: stale approval and resume tests.
Green: interrupt payload + validator.
Refactor: share timestamp and evidence validation.
