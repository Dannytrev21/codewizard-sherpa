# S3-02 — Transition table tests

**Status:** Ready  
**Goal:** Pin every conditional edge and forbid direct node-to-node calls.

## Acceptance criteria

- Every valid edge has a test.
- Invalid edges fail predictably.
- AST test rejects direct peer-node calls.

## TDD plan

Red: missing-edge and direct-call tests.  
Green: implement transition router.  
Refactor: table-drive the routing rules.
