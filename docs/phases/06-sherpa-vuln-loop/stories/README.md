# Phase 06 — SHERPA-style state machine for the vuln loop: Stories manifest

**Status:** Backlog ready  
**Date:** 2026-05-18

| Step | Stories |
|---|---|
| 1 | [S1-01](S1-01-sut-contract-types.md), [S1-02](S1-02-ledger-state-union.md) |
| 2 | [S2-01](S2-01-semantic-checkpoints.md), [S2-02](S2-02-replay-verification.md) |
| 3 | [S3-01](S3-01-plugin-local-subgraph.md), [S3-02](S3-02-transition-table-tests.md) |
| 4 | [S4-01](S4-01-hitl-interrupt-and-resume.md) |
| 5 | [S5-01](S5-01-stable-sut-adapter.md) |
| 6 | [S6-01](S6-01-e2e-kill-resume-closeout.md) |

## Definition of done

- Story acceptance criteria are green.
- New public types are covered by mypy-strict and serialization tests.
- No graph node directly calls another node.
- Resume paths are replay-verified.
- Any change to `VulnRemediationSut` updates ADR-0001 and the Phase 6.5 contract tests.
