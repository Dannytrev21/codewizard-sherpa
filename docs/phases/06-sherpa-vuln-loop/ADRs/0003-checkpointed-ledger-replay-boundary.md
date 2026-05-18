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
