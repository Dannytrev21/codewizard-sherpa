# S6-01 — E2E kill/resume closeout

**Status:** Ready
**Goal:** Prove the Phase 6 exit criteria end to end and publish the downstream handoff.

## Acceptance criteria

- Clean-completion, retry-recovery, kill/resume, and HITL-resume integrations pass.
- Phase 6.5 contract test imports `VulnRemediationSut`, not graph internals.
- Roadmap and docs links resolve to the Phase 6 package.

## TDD plan

Red: failing integration fixtures and docs assertions.
Green: finish workflow wiring.
Refactor: close duplicated fixture setup.
