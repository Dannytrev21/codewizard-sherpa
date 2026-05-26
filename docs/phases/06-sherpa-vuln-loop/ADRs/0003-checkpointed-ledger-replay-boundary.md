# ADR-0003: Semantic checkpoints with replay verification before resume

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** durability · replay · safety

## Context

Phase 6 must prove local restartability before Phase 9 introduces Temporal durability. Writing after every helper call is wasteful; resuming from unverified state is unsafe.

## Decision

Persist checkpoints only at semantic boundaries and verify the previous chain head before hydration on resume.

## Tradeoffs

| Gain | Cost |
|---|---|
| Durable enough for workflow recovery without excessive writes | A crash between semantic checkpoints replays a little work |
| Tamper or partial writes fail closed before new work starts | Ledger code is slightly more involved than naïve snapshots |

## Consequences

- Kill/resume tests pin checkpoint ordering.
- Failed verification transitions to `FailedUnrecoverable`.

## Amendment 2026-05-25 (S2-02)

Two additive clarifications surfaced by the S2-02 (replay verification) implementation:

1. **`CheckpointStore` Protocol gains a sixth method `iter_persisted_chain(workflow_id) -> Iterator[tuple[TransitionEvent, ChainHead]]`.** The replay verifier needs per-row persisted `next_head` to compute the `ChainMismatch.divergence_index`. The five existing methods (`append`, `read_all_for_workflow`, `tail_chain_head`, `lock`, `close`) are byte-equal-unchanged. The verifier dispatches through the Protocol (no substrate-specific shortcut), so the in-memory adapter parity holds. The contract-snapshot meta-test classifies this delta as additive.

2. **The chain head is folded over the sanitized-reconstructed event, not the live event.** S2-01 originally computed the chain head over the live (cleartext) event while persisting sanitized bytes — meaning the verifier could not reproduce the head from persisted bytes when sanitization triggered. The fix lands in both adapters: `append()` reparses `sanitize_for_persistence(canonical_bytes)` into a `TransitionEvent` and folds over that reconstructed event. For events with no secret-shaped content the reconstructed event is byte-equal to the live event, so existing chain heads and `tests/golden/phase6-checkpoint/clean_completion_chain.json` are unchanged. The chain now protects the bytes on disk — the substrate-replayable invariant the Phase-9 SQLite ↔ Postgres byte-equality test depends on.

Owner: Phase 6 S2-02 attempt log entry (Attempt 1, 2026-05-25).
