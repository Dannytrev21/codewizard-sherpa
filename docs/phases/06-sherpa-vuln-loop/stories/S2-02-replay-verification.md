# S2-02 — Replay verification

**Status:** Ready  
**Goal:** Verify checkpoint integrity before resume.

## Acceptance criteria

- Tampered checkpoint chains fail closed.
- Partial final writes do not hydrate.
- Resume returns typed integrity failure.

## TDD plan

Red: tamper and partial-write tests.  
Green: chain verification before hydrate.  
Refactor: isolate replay helpers.
