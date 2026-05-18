# S1-01 — SUT contract types

**Status:** Ready  
**Goal:** Define the stable harness-facing `VulnRemediationSut` contract and immutable request/result models.

## Acceptance criteria

- `VulnRemediationCase`, `VulnRemediationResult`, `SutDigest`, and `VulnRemediationSut` exist.
- Result serialization exposes only sanitized evidence.
- Contract snapshot tests pass.

## TDD plan

Red: write serialization and forbidden-field tests.  
Green: add the models and protocol.  
Refactor: extract shared identifiers into newtypes.
