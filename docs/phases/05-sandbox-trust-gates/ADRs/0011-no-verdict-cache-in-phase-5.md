# ADR-0011: No verdict cache in Phase 5; ship `sandbox_spec_hash` as the forward-compat seam

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** cache · deferral · phase-9-handoff
**Related:** [ADR-0007](0007-pre-execute-marker-for-resume-safety.md), [production ADR-0003](../../../production/adrs/0003-temporal-as-workflow-substrate.md)

## Context

Performance-first's design proposed a `GateVerdictCache` keyed on a sandbox-input hash so retry-3 of a known-good build/install signal could short-circuit. The critic attacked the cache aggressively: the proposed key omitted registry-mirror state, kernel/rootfs digest, gate-impl source hash, policy YAML bytes, and grype DB version — any of which could change between cache write and cache read, returning a stale "pass" verdict. Stale-pass on a security-sensitive gate is the worst failure mode (silent compromise of the trust boundary). Phase 9 (Temporal) owns activity-level idempotency and is the right home for a cache with proper input-key audit. See [final-design.md §Synthesis ledger — verdict cache row](../final-design.md#synthesis-ledger) and [phase-arch-design.md §Non-goals §1](../phase-arch-design.md#non-goals).

## Options considered

- **Ship `GateVerdictCache` (performance-first)** — Saves wall-clock on retries with stable inputs. Stale-pass risk if the cache key misses any input.
- **Ship a "soft" cache (warn on hit)** — Cache miss runs full sandbox; cache hit runs full sandbox too and *compares* the verdict, logging mismatches. No latency win; only useful as a calibration tool.
- **Defer; ship the seam** — Phase 5 emits `SandboxSpec.sandbox_spec_hash` (BLAKE3 of canonical-JSON of the spec with sorted env keys) but does not implement the cache. Phase 9 with Temporal's activity idempotency owns the cache with the input-key audit the critic demanded.

## Decision

No verdict cache in Phase 5. Every retry runs full sandbox boot + install + test. `SandboxSpec.sandbox_spec_hash` is shipped as a forward-compat seam: Phase 9's Temporal activity layer will use it as the idempotency key, but Phase 5 only emits it.

## Tradeoffs

| Gain | Cost |
|---|---|
| Zero stale-pass risk on retries; honest verdicts every attempt | Retry-3 pays full freight (~6 gates × 90 s wall ≈ 540 s worst case); per-workflow cost-cap ([ADR-0025](../../../production/adrs/0025-per-workflow-cost-cap.md)) is stressed earlier |
| Phase 13's cost ledger sees true cost — no cached-out underreporting | Performance regression test bars are set against full re-runs; CI is slower than it could be |
| Phase 9 owns the cache with Temporal's idempotency model — input-key audit is part of that ADR | A future "fast lane" use case for cheap repeat verdicts (e.g., re-running gates against unchanged code in CI) is deferred to Phase 9 |
| `sandbox_spec_hash` is stable today — Phase 9 lifts it without needing a fresh contract | Phase 5 shipping the hash without using it produces an unused field critical readers may want to delete |

## Consequences

- `SandboxSpec.sandbox_spec_hash` is computed by `SandboxSpecBuilder` (BLAKE3 over canonical-JSON, sorted env keys) and present on every `SandboxRun`.
- A property test asserts byte-stability under env-key reordering.
- No code path in Phase 5 reads the hash for cache lookup; it is emit-only.
- `tests/sandbox/test_sandbox_spec_hash.py` is the load-bearing property test.
- New invariant: the hash includes — at minimum — all `SandboxSpec` fields plus the base-image digest plus the gate's required-signals tuple. Any field added to `SandboxSpec` must extend the hash inputs.
- The retry-2 wall-clock budget (≤ 1.6× retry-1; [phase-arch-design.md §Goals 11](../phase-arch-design.md#goals)) is set against full re-runs — defended by this ADR.

## Reversibility

**Medium.** Shipping a cache later is a forward-compatible addition (the hash is already emitted). Removing the hash now would orphan Phase 9's design. The decision is "defer," not "preclude" — Phase 9's ADR will supersede if it adopts the cache.

## Evidence / sources

- [final-design.md §Synthesis ledger — verdict cache row](../final-design.md#synthesis-ledger) (winner score 12 — None)
- [final-design.md §Path to production end state](../final-design.md#) — "no verdict cache" explicitly
- [phase-arch-design.md §Non-goals §1](../phase-arch-design.md#non-goals)
- [critique.md performance §1](../critique.md)
- [production ADR-0003](../../../production/adrs/0003-temporal-as-workflow-substrate.md) — Temporal is Phase 9's substrate
