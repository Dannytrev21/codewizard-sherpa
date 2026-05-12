# ADR-0005: `RetryLedger` startup verifies Phase 4 chain-head compatibility

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** audit-chain · phase-boundary · cross-phase-test
**Related:** [ADR-0002](0002-additive-prior-attempts-kwarg.md), [ADR-0007](0007-pre-execute-marker-for-resume-safety.md), [production ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md)

## Context

Phase 4 emits BLAKE3-chained audit events (`solved_example.duplicate_skipped`, `engine_used` stamping). Phase 5's `RetryLedger` extends that same chain: every attempt's `chain_hash = blake3(prev_hash || canonical_json(attempt))`. The critic's [roadmap §6 attack](../critique.md) was that "none of the three designs verified that Phase 4's chain events produce entries Phase 5 will consume." Without an explicit chain-compatibility test, Phase 4 can mutate its event shape, and Phase 5 will read corrupt or unparseable predecessor entries — likely silently. See [final-design.md §Synthesis ledger](../final-design.md#synthesis-ledger) and [phase-arch-design.md §Component design — RetryLedger](../phase-arch-design.md#retryledger).

## Options considered

- **Trust the chain implicitly** — Phase 5 reads the chain head; if BLAKE3 verifies, proceed. Catches tampering but not schema drift in Phase 4's event payloads (a re-named field passes BLAKE3 verification fine).
- **Re-implement chain primitives in Phase 5** — Decouples Phase 5 from Phase 4's chain. Loses end-to-end tamper-evidence; reviewer can no longer trust the chain spans the LLM-decision boundary.
- **Golden Phase 4 chain-head fixture + Phase 5 startup test** — Capture a known-good Phase 4 chain head as a binary fixture; Phase 5's `RetryLedger.__init__` reads `.codegenie/remediation/<run-id>/chain_head.bin` and refuses to start if mismatch; `tests/schema/test_phase4_chain_compat.py` regenerates the fixture and would fail loudly if Phase 4's shape drifts.

## Decision

`RetryLedger.__init__` accepts `prev_chain_head: bytes | None`, reads it from `.codegenie/remediation/<run-id>/chain_head.bin` (Phase 4's last write), and raises `AuditChainCorrupted` on mismatch. A binary fixture `tests/golden/phase4_chain_head.bin` plus an integration test verifies Phase 4's last entry produces a chain head whose shape Phase 5 can read. Startup test refuses to run any gate if compatibility fails.

## Tradeoffs

| Gain | Cost |
|---|---|
| The audit chain spans Phase 4's LLM-decision boundary all the way into Phase 5's gate verdicts | Cross-phase coupling: Phase 4 cannot change its chain event shape without regenerating Phase 5's fixture |
| Startup refusal is loud and fail-loud per [global rule 12](../../../../CLAUDE.md) — silent chain drift is impossible | Operators who hand-edit `attempts.jsonl` or `chain_head.bin` (e.g., for forensics) will trigger `AuditChainCorrupted` |
| Tamper detection extends through every gate retry | Per-attempt `record()` fsyncs (~10 ms) — durability over throughput |
| `tests/golden/phase4_chain_head.bin` is regenerated as part of any Phase 4 chain-shape PR — Phase 4 cannot drift silently | The fixture is a tiny binary file checked into Git; its byte-stability is part of the test contract |

## Consequences

- `RetryLedger.__init__` is the load-bearing chain-compat enforcement point.
- `tests/schema/test_phase4_chain_compat.py` regenerates the fixture; Phase 4 PR that changes event shape must include a Phase 5 fixture update — the diff signals the cross-phase change.
- `codegenie sandbox inspect <gate-run-id>` re-verifies the chain on every invocation; `AuditChainCorrupted` surfaces with a clear remediation message.
- The chain is the contract Phase 11 (handoff) consumes for evidence bundles.
- New invariant: any Phase 4 event-shape change requires regenerating `phase4_chain_head.bin` *and* an ADR amendment on either side that surfaces the cross-phase break.
- The `attempts.jsonl` file is append-only with BLAKE3 per-line chain — second `record(Attempt(attempt_id=1, ...))` raises `LedgerAttemptOutOfOrder`.

## Reversibility

**Medium.** The chain-compat test is independent of the chain primitive; the primitive could be replaced (e.g., move to Merkle tree). Removing the startup refusal would re-open silent drift — that part is hard to reverse without forfeiting tamper-evidence. The fixture/test pattern is portable.

## Evidence / sources

- [final-design.md §New ADRs implied — ADR-P5-005](../final-design.md#new-adrs-implied-by-this-design)
- [final-design.md §Synthesis ledger — chain compatibility](../final-design.md#synthesis-ledger)
- [phase-arch-design.md §Component design — RetryLedger](../phase-arch-design.md#retryledger)
- [phase-arch-design.md §Edge cases §11–12](../phase-arch-design.md#edge-cases)
- [critique.md §roadmap §6](../critique.md)
- [production ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md)
