# Phase 6 — SHERPA-style state machine for the vuln loop: Final design

**Status:** Design of record  
**Date:** 2026-05-18  
**Roadmap source:** [`../../roadmap.md`](../../roadmap.md) §"Phase 6"

## Executive summary

Phase 6 turns the Phase 3 deterministic recipe path, the Phase 4 RAG-shaped LLM fallback, and the Phase 5 sandbox gates into one restartable SHERPA-style workflow. It does **not** redesign those capabilities. It composes them inside a plugin-local LangGraph subgraph, persists a typed ledger at semantic boundaries, and exposes one stable harness-facing contract, `VulnRemediationSut`, that Phase 6.5 may consume without knowing the graph's internal topology.

## Decisions of record

1. **Plugin-local graph topology.** The graph lives under `plugins/vulnerability-remediation--node--npm/subgraph/`; reusable ports and typed contracts live under `src/codegenie/`.
2. **Stable harness-facing SUT contract.** Phase 6 owns `VulnRemediationSut`:

   ```python
   class VulnRemediationSut(Protocol):
       async def run_case(self, request: VulnRemediationCase) -> VulnRemediationResult: ...
       def digest(self) -> SutDigest: ...
   ```

   `VulnRemediationCase` names the repo fixture, CVE, cassette pin, and requested execution mode. `VulnRemediationResult` exposes sanitized outputs the harness needs: terminal state, patch digest, gate summary, failure modes, cost summary, and evidence references. The concrete LangGraph builder is behind the adapter.
3. **Checkpoint on semantic boundaries.** The ledger persists after plan acceptance, patch application, gate result, escalation, and terminal completion. Resume verifies the prior chain head before replay.
4. **Edges own control flow.** Nodes compute; conditional edges decide. No node directly calls another node.
5. **Typed interruption.** HITL is a discriminated-union outcome carrying reason, evidence, and resumption contract. "Paused" is not a boolean side channel.
6. **No new trust bypass.** Patch application, LLM invocation, and sandbox execution continue through Phase 3/4/5 ports and policies.

## State model

The ledger uses a closed sum type:

- `NeedsPlan`
- `PlanReady`
- `PatchApplied`
- `GateFailedRetryable`
- `AwaitingHumanReview`
- `Completed`
- `FailedUnrecoverable`

Every transition records: prior state id, next state id, triggering outcome, evidence digest, and checkpoint chain head.

## Main workflow

1. Load `VulnRemediationCase`.
2. Build or resume `VulnLedger`.
3. Plan through recipe-first → RAG-shaped LLM fallback.
4. Apply patch through the existing transform port.
5. Validate through the Phase 5 gate runner.
6. Route:
   - pass → `Completed`
   - retryable failure → replan
   - repeated failure or policy block → `AwaitingHumanReview`
   - impossible state / integrity failure → `FailedUnrecoverable`
7. Return `VulnRemediationResult` through `VulnRemediationSut`.

## Relationship to Phase 6.5

Phase 6.5 may depend on:

- the `VulnRemediationSut` protocol
- `VulnRemediationCase`
- `VulnRemediationResult`
- `SutDigest`

Phase 6.5 may **not** depend on:

- the concrete graph builder
- node names
- checkpoint backend internals
- plugin-local file layout

That contract boundary is the main redesign outcome. It lets the harness measure behavior while Phase 6 remains free to refactor graph internals.

## Exit criteria mapping

| Roadmap exit criterion | Phase 6 commitment |
|---|---|
| LangGraph state machine runs the vuln loop | Plugin-local subgraph with typed state ledger |
| Mid-run kill + resume works | Replay-verified semantic checkpoints |
| HITL interrupt resumes correctly | Typed interrupt outcome + resume validation |
| Phase 6.5 can evaluate the loop | Stable `VulnRemediationSut` contract |

## Non-goals

- No second task class.
- No Temporal durability yet; Phase 9 owns that.
- No replacement of Phase 3/4/5 domain logic.
- No generalized graph framework for every future plugin before Phase 7 proves the second plugin shape.

## Deferred questions

- Whether SQLite remains the local checkpoint backend after Phase 9 introduces Postgres.
- Whether future task classes share any workflow node implementations or only ports.
- Whether `SutDigest` needs to include prompt-template version once model release policy lands.
