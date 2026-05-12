# ADR-0015: Test-inventory `delta < 0` fails strict-AND; `delta > 0` is informational

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** signals · adversarial · trust
**Related:** [ADR-0014](0014-objectivesignals-extra-forbid-static-introspection.md), [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md)

## Context

An LLM-produced patch that *removes a test* to make `npm test` pass is a documented adversarial path. Security-first's design proposed hard-failing on any test-inventory delta ≠ 0 — forbidding both removed and added tests. The critic noted this forbids legitimate test additions (a CVE fix that adds a regression test would fail the gate). Performance-first and best-practices designs did not address this. The synthesis: asymmetric policy. See [phase-arch-design.md §Edge cases 6 and 7](../phase-arch-design.md#edge-cases) and [final-design.md §Departures §3](../final-design.md#departures-from-all-three-inputs).

## Options considered

- **Hard-fail on any delta ≠ 0 (security-first)** — Forbids both removed and added tests. False positives on legitimate test additions. Cripples Phase 4's fallback path on CVE fixes that include regression tests.
- **Soft signal (just log)** — Record the delta; never fail. Adversarial path (LLM removes test) succeeds.
- **Asymmetric: `delta < 0` fails, `delta > 0` informational** — Removed tests indicate a likely adversarial patch (or accidental destruction); added tests are usually legitimate. Reviewer sees both in the evidence bundle ([ADR-0009](../../../production/adrs/0009-humans-always-merge.md)).

## Decision

`TestSignal.passed = False` when `delta_test_count < 0`. `delta_test_count > 0` is recorded in `details` but does not fail the signal. `details["delta_test_count"]` is always emitted (zero, positive, or negative). At 3× repeated `delta < 0`, the loop returns `failed_unrecoverable` (CLI exit 12) — distinct from `escalate` so reviewers know the LLM is producing the same wrong destructive patch repeatedly.

## Tradeoffs

| Gain | Cost |
|---|---|
| Adversarial path (LLM removes test) is caught and fails the gate | A patch that legitimately consolidates two tests into one (delta = -1) fails the gate — false positive |
| Legitimate test additions in CVE fixes are not blocked | The delta is computed from a pre-patch inventory snapshot — Phase 3 must produce and persist that snapshot before Phase 4 runs |
| Reviewer always sees the delta in evidence — annotation, not just verdict | Reviewer must consult evidence to understand `delta > 0` cases; default behavior is silent acceptance |
| `failed_unrecoverable` distinguishes "LLM stuck on destructive pattern" from "transient build flake" — reviewer knows the failure type | Two terminal states (`escalate` vs `failed_unrecoverable`) increase reviewer cognitive load; Phase 11 UX must explain |

## Consequences

- `collect_test_signal` reads `pre_patch_inventory_path` from `GateContext`; Phase 3 is responsible for producing the snapshot.
- `tests/adversarial/test_patch_disables_test.py` is the load-bearing adversarial test.
- `details["delta_test_count"]` is always present in `TestSignal.details` (int field).
- `GateRunner` detects "same failing signals 3×" via the failing-signals tuple equality across attempts; returns `failed_unrecoverable` (exit 12) per [phase-arch-design.md §Edge case 17](../phase-arch-design.md#edge-cases).
- Phase 11's evidence bundle exposes `delta > 0` as a noted addition; reviewers can choose to scrutinize.
- New invariant: every `TestSignal` carries `delta_test_count`; a missing value is `0` (explicit, not `None`).

## Reversibility

**Medium.** Tightening (any delta fails) re-opens false-positive blockers; loosening (no delta fail) re-opens adversarial vector. Adding more granularity (e.g., test-name diff, not just count) is a forward-compatible extension. The asymmetric stance is intended to be durable.

## Evidence / sources

- [final-design.md §Synthesis ledger — Test-inventory delta row](../final-design.md#synthesis-ledger) (winner score 12)
- [final-design.md §Departures §3](../final-design.md#departures-from-all-three-inputs)
- [phase-arch-design.md §Edge cases 6, 7, 17](../phase-arch-design.md#edge-cases)
- [phase-arch-design.md §Adversarial tests — test_patch_disables_test](../phase-arch-design.md#adversarial-tests)
- [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md)
