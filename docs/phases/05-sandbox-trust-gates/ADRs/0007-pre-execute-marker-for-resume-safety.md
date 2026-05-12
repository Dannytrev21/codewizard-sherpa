# ADR-0007: `pre_execute` marker written to ledger before `SandboxClient.execute`

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** resume · idempotency · phase-6-handoff
**Related:** [ADR-0005](0005-phase4-chain-head-compatibility.md), [production ADR-0016](../../../production/adrs/0016-checkpointer-backend.md)

## Context

`SandboxClient.execute` is **not** idempotent — it pulls images, runs builds, may hit live grype DB, and produces a new `SandboxRun.run_id` on every call. Phase 6 (LangGraph state machine) will lift Phase 5's loop into a subgraph with a SQLite checkpointer. If the worker dies between `execute` returning and `RetryLedger.record` writing the attempt, a resume currently has no record an execute happened — Phase 6 would re-execute and pay full cost (sandbox time + Phase 4 LLM tokens on re-plan + grype DB hits). The synthesis declared the loop's data shapes as the Phase-6 contract but [phase-arch-design.md §Gap analysis Gap 1](../phase-arch-design.md#gap-1-sandboxclientexecute-is-not-idempotent-but-phase-6s-checkpointer-assumes-it-can-resume-from-any-state) surfaced this gap.

## Options considered

- **Best-effort: re-execute on resume** — Phase 6 always re-executes if no `attempt` record exists. Simple, but doubles cost on every mid-attempt crash; for non-deterministic workloads (grype, live CVE DB) it can change the signal verdict.
- **Idempotency key on `SandboxClient.execute`** — Make backends idempotent on `sandbox_spec_hash`. Forces every backend to maintain a cache; introduces a verdict-cache by stealth (rejected by [ADR-0008-style cache attacks in this phase's `final-design.md`](../final-design.md#synthesis-ledger)).
- **Two-phase write: marker before execute, record after** — `RetryLedger.record_pre_execute(attempt_id, sandbox_spec_hash, started_at)` writes a JSONL line of type `"pre_execute"` before `SandboxClient.execute`; the subsequent attempt record is type `"attempt"`. On resume, a `pre_execute` without a matching `attempt` signals: an execute happened, the result is lost. Phase 6 picks the policy (default: re-execute and accept cost; opt-in skip via `SandboxResumeBehavior`).

## Decision

`RetryLedger` exposes `record_pre_execute(attempt_id, sandbox_spec_hash, started_at) -> None` called inside `GateRunner.run` immediately before `client.execute(spec)`. The marker is a JSONL line `{"type": "pre_execute", ...}` chained into the BLAKE3 chain. The subsequent `record(Attempt(...))` writes a `{"type": "attempt", ...}` line. Phase 5 ships the marker; Phase 6 ships the resume policy.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 6 can detect "execute happened, result is lost" and choose policy explicitly — no silent double-spend on LLM tokens | One extra ledger write per attempt (~10 ms fsync) |
| The marker is BLAKE3-chained — tamper-evident as the rest of the ledger | `attempts.jsonl` now has two row types; readers must handle both |
| Resume policy is Phase 6's choice (not hardcoded) — `SandboxResumeBehavior` enum on `GateContext` is the contract seam | If Phase 6 picks "skip re-execute" without verifying the original run produced complete signal data, verdicts can be partial |
| Honors fail-loud: an orphan `pre_execute` is *visible* on inspect | A crash *before* `record_pre_execute` still results in silent state — but the orchestrator process is the credential holder and a crash there is non-recoverable anyway |

## Consequences

- `gates/retry_ledger.py` gains `record_pre_execute(...)`; `GateRunner.run` calls it inside the loop body before `client.execute`.
- `tests/gates/test_pre_execute_marker.py` asserts: (a) marker is written before execute; (b) JSONL has correct ordering; (c) marker BLAKE3 chains to next attempt record.
- `codegenie sandbox inspect` shows pre-execute markers explicitly (annotated as "execute started, result missing" when no matching attempt).
- Phase 6 carries `SandboxResumeBehavior` on `GateContext`; default value is `"re_execute"` so existing behavior is unchanged.
- The marker shape is part of the chain — changing it triggers [ADR-0005](0005-phase4-chain-head-compatibility.md)-style chain-compat regeneration.
- New invariant: a `pre_execute` row without a matching `attempt` row at the same `attempt_id` is an *expected* state during recovery (not corruption); `RetryLedger.attempts()` returns both types so callers can detect.

## Reversibility

**Medium.** The marker is additive — removing it falls back to "re-execute on every resume." Reverting the JSONL row type and chain shape requires a chain-compat regeneration. Phase 6's resume-policy contract surface (the `SandboxResumeBehavior` enum) becomes orphaned if reverted. The marker primitive can be replaced (e.g., separate file) without losing the chain.

## Evidence / sources

- [phase-arch-design.md §Gap analysis Gap 1](../phase-arch-design.md#gap-1-sandboxclientexecute-is-not-idempotent-but-phase-6s-checkpointer-assumes-it-can-resume-from-any-state)
- [phase-arch-design.md §Integration with Phase 6](../phase-arch-design.md#integration-with-phase-6-next-phase)
- [phase-arch-design.md §Open questions §8](../phase-arch-design.md#open-questions-deferred-to-implementation)
- [production ADR-0016](../../../production/adrs/0016-checkpointer-backend.md) — Phase 6's checkpointer this contract serves
