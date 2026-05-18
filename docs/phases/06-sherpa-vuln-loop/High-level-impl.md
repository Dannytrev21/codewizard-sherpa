# Phase 06 — SHERPA-style state machine for the vuln loop: High-level implementation plan

**Status:** Implementation plan  
**Date:** 2026-05-18  
**Architecture reference:** [phase-arch-design.md](phase-arch-design.md)  
**ADRs:** [ADRs/](ADRs/)

## Executive summary

Implement Phase 6 contracts-first: define `VulnRemediationSut` and the ledger model before wiring LangGraph; then build plugin-local topology, checkpoint/replay, HITL resume, and the integration tests that Phase 6.5 will rely on.

## Step 1 — Public contracts and typed ledger

- Add `VulnRemediationCase`, `VulnRemediationResult`, `SutDigest`, `VulnRemediationSut`.
- Add the closed ledger state union and transition event types.
- Add serialization and redaction tests.

## Step 2 — Replay-safe checkpoint store

- Implement semantic checkpoint append/read.
- Verify prior chain head before hydrate.
- Add tamper and resume golden tests.

## Step 3 — Plugin-local graph topology

- Add the vuln subgraph package under the plugin directory.
- Wire planner, transform, and gate ports through reducers and conditional edges.
- Add static tests forbidding direct node-to-node calls.

## Step 4 — HITL and failure routing

- Add typed interrupt payloads and resume validation.
- Distinguish retryable, terminal, and failed-unrecoverable states.
- Prove stale approvals are rejected.

## Step 5 — Stable SUT adapter and downstream handoff

- Implement the concrete adapter behind `VulnRemediationSut`.
- Keep graph builder private.
- Add contract tests proving Phase 6.5 can invoke the SUT without graph imports.

## Step 6 — End-to-end verification

- Clean completion fixture.
- Retry-then-recover fixture.
- Kill/resume fixture.
- HITL interrupt/resume fixture.
- Docs + contract snapshot closeout.
