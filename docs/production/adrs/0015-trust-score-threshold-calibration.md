# ADR-0015: Trust-score threshold calibration

**Status:** Deferred
**Date:** 2026-05-11
**Tags:** trust · calibration
**Related:** ADR-0008

## Context

ADR-0008 commits to computing the trust score from objective signals only — sandbox build, test pass/fail, SAST findings, CVE delta, runtime-trace coverage, policy-engine block events, coverage of changed code. Each of those signals can be normalized to a score; the trust score is a weighted aggregate.

But: what are the weights, and what's the threshold below which a transition is blocked or routed to human review? Setting these a priori without production data is guesswork. Calibrating after production data lands is empirically defensible.

The user's initial proposal was `T_conf ≤ 0.90` as the reject threshold. Whether that number is right depends on the distribution of objective-signal values across successful and failed migrations — which we don't yet have.

## Options considered

- **Set thresholds a priori.** Pick `T ≤ 0.90` and ship. Risk: miscalibrated, either too permissive (catastrophic merges) or too strict (every transition escalates).
- **Binary pass/fail until calibration.** Until production data exists, gates use binary "did all critical signals pass?" — no scoring threshold. Conservative.
- **Defer formula and threshold; calibrate against first N production migrations.** Start binary; aggregate signal distributions; fit a threshold against post-merge incident data once N is large enough.

## Default until decided

**Binary pass/fail on the most direct objective signal at each gate.** Build must pass; tests must pass; SAST must not find new high-severity issues; CVE delta must be non-positive. If any of these fail, the gate fails (route back / escalate per ADR-0014). No scoring threshold yet.

The trust-score *formula* — what signals contribute how much — is also deferred. Until calibration, gates evaluate signals independently with AND semantics.

## Evidence needed to resolve

- **N = 50 production migrations** with full objective-signal traces and post-merge outcome data (merged-clean, merged-then-rolled-back, abandoned).
- **Signal distribution analysis.** Which signals are noisy in successful migrations? Which are reliable predictors of post-merge incidents?
- **Threshold calibration.** Receiver operating characteristic (ROC) curve against post-merge incidents to pick a threshold that balances false-positive (overflagged) and false-negative (missed regressions) rates.
- **Per-task-class refinement.** Vulnerability patches likely tolerate higher gate threshold than convenience migrations; calibrate separately.

## Reversibility (of the eventual calibration)

**Low cost.** Once a threshold is set, adjusting it is a config change. The gate logic is signal-agnostic; the threshold is a knob.

## Evidence / sources

- `../design.md §4.6` (push-back, objective signals)
- `../design.md §5` (Trust score and gates subsection)
- `../design.md §7` (Open questions — Trust-score threshold calibration)
- ADR-0008 (the underlying commitment to objective signals)
