# ADR-0008: `dive_efficiency` ships advisory-only — `passed=True` always; not a strict-AND gate signal

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** gate-signals · facts-not-judgments · trust-score · phase13-calibration
**Related:** [ADR-0003](0003-objective-signals-widening-and-allowlists.md), [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md), [production ADR-0015](../../../production/adrs/0015-trust-score-threshold-calibration.md)

## Context

`dive` reports several image metrics: final size, efficiency percentage, wasted bytes, and the size-ratio between the pre-image and post-image. The security design proposed `image_size_post / image_size_pre ≤ 0.8` as a strict-AND signal: the gate fails if the migrated image grew more than 25% (`critique.md §security.3`).

The critic landed hard on this: legitimate Alpine→glibc Chainguard migrations *will* grow the image (Alpine's musl is dramatically smaller than glibc-based distroless; the Chainguard `*-glibc` variants pull in extra runtime support). A strict-AND on size ratio auto-fails these migrations every time → Phase 5's three-retry semantics → LLM fallback "fixing" a non-bug → retry-3 → human escalation. The $/PR target (≤ $0.12) blows up on cases that have nothing wrong (`critique.md §security.3`).

Production ADR-0008 ("Trust score uses objective signals only — no LLM self-confidence") and the load-bearing commitment "Facts, not judgments" (production/design §2.2) drove the synthesizer's resolution (`final-design.md §Conflict-resolution row 13`): emit the size ratio and efficiency as evidence in `details`, but `passed=True` always. The gate's binary verdict consumes `shell_presence` and `shell_invocation_trace` (strict-AND); `dive` produces facts the human can inspect.

Phase 13 (production ADR-0015 — trust-score threshold calibration) is the right phase to revisit whether to harden any of these advisory signals into strict-AND, once production data on image-size distributions exists.

## Options considered

- **Strict-AND `image_size_post / image_size_pre ≤ 0.8` (security's pick).** Auto-fails legitimate Alpine→glibc migrations; cascades into LLM-fallback spend on non-bugs.
- **Strict-AND with a hardcoded allowlist of "expected-growth" migrations.** Operator must maintain the allowlist; brittle on new Chainguard variant introductions.
- **Advisory-only, `passed=True` always, `details` carry the metrics for human review (synthesizer's pick).** Preserves "facts, not judgments"; Phase 13 calibration decides whether to harden.
- **Soft confidence (`passed=True` but `confidence=low` on ratio > 1.0).** Less honest — `confidence` is reserved for probe-internal uncertainty (e.g., `parser_skipped_lines > 0`), not human-judgment-flagging.

## Decision

`sandbox/signals/dive.py` ships with `passed=True` always. The collector populates `details["size_ratio_post_pre"]`, `details["final_size_bytes"]`, `details["efficiency_pct"]`, `details["wasted_bytes"]` from `dive --json` output. `migration-report.yaml` surfaces the same metrics under `dive_summary` so humans see the size delta when they review the PR. Phase 5's `StrictAndGate.evaluate` consumes `dive.passed` (always `True`) — the signal counts toward strict-AND but never fails it.

## Tradeoffs

| Gain | Cost |
|---|---|
| Legitimate Alpine→glibc migrations no longer auto-fail; $/PR target ($0.12 LLM-fallback) holds on cases that have nothing wrong | Image-size regressions on what *should* be a smaller image (e.g., a buggy multi-stage recipe leaving build artifacts in the runtime layer) are not gate-enforced — caught only at human review |
| "Facts, not judgments" honored: the probe emits evidence (size, ratio, efficiency); the gate doesn't write `is_growth_legitimate` | Phase 13's calibration burden inherits an extra signal to decide on — strict-AND? threshold? task-class-specific? |
| Phase 13's threshold-calibration ADR (production ADR-0015) has a per-signal hook to harden later; the seam already exists | Operators may expect a size-regression alarm; the absence is documented here and surfaced in `migration-report.yaml`, but unread-report failure mode is real |
| One ADR records the *why* — future readers seeing `passed=True` always know it's intentional, not a bug | If Chainguard variants stabilize and the legitimate-growth case becomes rare, the conservative position outlives its usefulness; Phase 13 should revisit |

## Consequences

- `sandbox/signals/dive.py` is implemented with `passed=True` hardcoded; the collector's signature is `collect_dive(image_digest, ctx) -> DiveSignal`.
- `DiveSignal` Pydantic model has `passed: bool` and `details: dict[str, int | float | str]` — same shape as other `*Signal` types, but the `passed` field is informational here.
- `migration-report.yaml` includes `dive_summary` so the human reviewer sees the size ratio; the operator-facing CLI flag `--json` exposes the same data.
- `tests/unit/sandbox/signals/test_dive_signal.py` asserts `passed=True` even when `size_ratio_post_pre > 1.0` (the legitimate-growth case).
- Phase 13's calibration work reads `tests/perf/` empirical distributions of `size_ratio_post_pre` across the fixture portfolio; harden to strict-AND only with measured thresholds + a Phase 13 ADR.
- The other three new signals — `shell_presence`, `shell_invocation_trace`, `base_image` — each have their own policy (`shell_presence`/`shell_invocation_trace` are strict-AND; `base_image` is informational). This ADR covers `dive` specifically.

## Reversibility

**Low for tightening, high for loosening.** Switching `dive.passed` to strict-AND with a threshold is a one-line change in the collector — but every legitimate Alpine→glibc migration in the fixture corpus + every operator's portfolio starts auto-failing. Loosening further (removing the signal entirely) is also one-line. The asymmetry favors keeping the current shape until Phase 13's data lands.

## Evidence / sources

- `../final-design.md §Conflict-resolution row 13` (advisory-only resolution)
- `../final-design.md §"Departures #3 ADR-P7-007"` (new vs final-design; design constraint recorded as ADR)
- `../final-design.md §"Departures #4"` (synthesis-original)
- `../phase-arch-design.md §Component 8` (signal collectors — `dive` advisory)
- `../phase-arch-design.md §"Tradeoffs"` row "dive_efficiency advisory-only"
- `../critique.md §security.3` (strict-AND on size ratio attacked)
- [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md) — objective-signal trust score
- [production ADR-0015](../../../production/adrs/0015-trust-score-threshold-calibration.md) — trust-score threshold calibration (Phase 13 re-evaluates)
