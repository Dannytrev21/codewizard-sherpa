# ADR-0012: Audit log gains a rolling BLAKE3 chain head; chain breaks are observability, not gather failure

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** audit · integrity · supply-chain · observability · phase-evolution
**Related:** [Phase 0 ADR-0004](../../00-bullet-tracer-foundations/ADRs/0004-audit-anchor-on-every-gather.md), ADR-0003, ADR-0004

## Context

Phase 0's audit anchor (Phase 0 ADR-0004) writes one append-only `runs/<utc>-<short>.json` per gather, containing cache decisions, per-probe metadata, and tool invocations. Phase 14's eventual transparency-log integration (production design.md §future-state) is the production-grade integrity surface. Phase 2 sits between: it introduces tool-digest pinning (ADR-0004), six new external CLIs (ADR-0005), and `OutputSanitizer` Pass 4/5 (ADR-0006) — all integrity-relevant. The audit needs a tamper-evidence mechanism that does not require Phase 14's infrastructure.

The security lens (`design-security.md`) proposed a rolling BLAKE3 chain head per gather: each `runs/<utc>.json` includes `previous_hash` pointing at the prior gather's chain head; on next gather start, the verifier reads the prior file and checks. A chain break (someone deleted, edited, or reordered the prior `runs/` file) emits a structured audit event but does *not* fail the gather — it's observability, not enforcement. Phase 14 promotes this to a real transparency log.

The critic was silent on this; the synthesis adopted it (`final-design.md "Conflict-resolution table" D16`, `"Departures from all three inputs"` is silent because all three lenses had some version of "audit").

## Options considered

- **No chain head; Phase 0's audit anchor as-is.** Cheapest. No tamper-evidence between gathers; the only integrity check is git history on the `runs/` directory if it's committed.
- **Append-only JSONL with BLAKE3 chain head per record.** Strongest; mirrors transparency-log mechanics; expensive (per-record hash chain). Overkill for Phase 2.
- **Rolling BLAKE3 chain head per gather; verify on next start; chain break is observability-only [S].** Lightweight; one hash per gather; failure mode is loud but not enforcing. Phase 14's real transparency log replaces the mechanism without breaking the audit shape.

## Decision

**Phase 2 extends Phase 0's `AuditWriter` with a rolling BLAKE3 chain head**:

- **Per-gather record.** Each `runs/<utc>-<short>.json` includes `previous_hash: blake3(prior_gather_record_bytes)`. The hash is computed over the prior `runs/...json`'s canonical byte serialization.
- **Verification at start.** On every `codegenie gather` invocation, before any probe runs, the AuditWriter reads the most recent `runs/` file and recomputes its expected `previous_hash` (the hash of *its* predecessor). If the recomputed hash does not match the stored value, emit `audit.chain_break_detected` (observability event) and continue.
- **No gather failure on chain break.** The chain break is loud but not enforcing — gather completes normally. Operators see the event in the audit log; CI dashboards can alert.
- **`--strict-audit` flag (future-amendment).** Not in Phase 2; documented as the future failure-loud handle if operators want chain breaks to fail the gather. Phase 14's transparency log makes this moot.
- **Where it lives.** `src/codegenie/audit/` is the Phase 0 module; Phase 2 extends it with one new field on the record schema (`previous_hash`) and one new event family (`audit.chain_break_detected`).
- **Compatibility with cache and snapshot.** The chain-head verification runs *before* the coordinator dispatches probes; it's a startup check, not a gather concern.

## Tradeoffs

| Gain | Cost |
|---|---|
| Tamper-evidence between gathers — silent deletion/edit of a prior `runs/` file produces a loud `audit.chain_break_detected` event | The check requires reading the most recent `runs/` file at every gather start; ~5 ms; immaterial |
| Phase 14's transparency log replaces the mechanism without changing the audit record shape — `previous_hash` field stays, gets stronger backing | The chain is one-deep (only the immediate predecessor) — an adversary who modifies both N and N-1 in lockstep escapes the check; mitigated by Phase 14's append-only log |
| Failure mode is observability, not enforcement — operators get signal; gather isn't held hostage to a missing predecessor file | An operator who silently deletes a `runs/` file (legitimate housekeeping, e.g., GC) gets a `chain_break_detected` event they must dismiss; mitigated by the audit-gc procedure documented in the audit module |
| The chain head is per-gather, not per-probe — cheap to compute, low audit-log overhead | Per-probe tamper-evidence would be stronger but is Phase 14's job; Phase 2 ships the mechanism that scales to that |
| `chain_break_detected` is a structured event consumable by Phase 8's observability stack — the same field shape as Phase 14's transparency-log alerts | Phase 8's observability must learn the event; documented in the AuditWriter README |
| Tool-digest changes are recorded *in* the audit record (ADR-0004); the chain head provides cross-gather tamper-evidence for the digest history too | The audit record grows by ~32 bytes per gather (one BLAKE3); immaterial |

## Consequences

- `src/codegenie/audit/writer.py` gains `previous_hash` field on the record schema and `verify_previous_chain_head()` helper invoked at coordinator start.
- `src/codegenie/audit/schema.json` (or inline) declares `previous_hash: string (64-char hex BLAKE3)` as a required field on every record.
- `tests/adv/test_audit_chain_break_observability.py` corrupts a prior `runs/...json` file; asserts the next gather emits `audit.chain_break_detected` and **exits 0** (not a failure — observability).
- `tests/unit/audit/test_audit_chain_head.py` asserts the chain head is recomputed correctly on round-trip; assert `previous_hash` propagates across multiple gathers.
- Phase 14's transparency-log integration replaces the `verify_previous_chain_head` implementation with a remote-log lookup; the API stays the same.
- The chain-head verification cost (~5 ms per gather start) is included in the warm-path budget; well within the 1.5 s p50 target.
- The audit record's other fields (`tool_digest`, per-probe metadata, cache decisions, sanitizer pass count) are unchanged by this ADR; they were already in Phase 0's anchor.

## Reversibility

**High.** Removing the chain-head verification is a one-method deletion; removing `previous_hash` from the record schema is a one-field edit. The audit anchor (Phase 0 ADR-0004) remains intact and functional. The capability lost (tamper-evidence) was not enforcement-grade in the first place — Phase 14 owns the production-grade integrity surface. Reversal cost is low; future Phases would replace with the transparency-log mechanism, not relitigate this one.

## Evidence / sources

- `../final-design.md "Components" §10 AuditWriter — rolling BLAKE3 chain head`
- `../final-design.md "Conflict-resolution table" D16` — the resolution
- `../final-design.md "Failure modes & recovery"` audit-chain-break row
- `../phase-arch-design.md "Goals" #14` (audit chain head as one of the named Phase-0 in-place edit categories)
- `../phase-arch-design.md "4+1 architectural views" "Logical view"` — AuditWriter class diagram with `chain_head_blake3` field
- [Phase 0 ADR-0004](../../00-bullet-tracer-foundations/ADRs/0004-audit-anchor-on-every-gather.md) — the audit anchor this extends
- ADR-0004 — tool-digest pinning; entries in the audit record now have cross-gather tamper-evidence
