# ADR-0008: Trust score uses objective signals only — no LLM self-confidence

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** trust · safety
**Related:** ADR-0009, ADR-0012, ADR-0015

## Context

The Trust-Aware gate layer (`../design.md §4.1` Layer 3) gates every state transition behind a "is this safe to advance?" check. The natural temptation is to ask the LLM itself: "how confident are you in this output?" and use the answer as a gate input.

Published research argues this is worse than no signal at all. The "Confidence Trap" finding in `../../gemini-auto-agent-design.md §"Mitigating the Confidence Trap"` reports that agentic PRs at the highest self-reported confidence levels (8–10 out of 10) still introduce breaking changes at 3.16–3.96%. At confidence 10, the rate is 3.16% — 458 breaks out of 14,509 commits. The correlation between LLM-reported confidence and code correctness breaks down completely during maintenance tasks.

A gate keyed on self-reported confidence produces false reassurance proportional to risk.

## Options considered

- **LLM self-reported confidence.** Cheap, easy, available. Empirically miscalibrated during the exact tasks (maintenance, refactor) where the system makes its money.
- **Objective signals only.** Sandbox build status, test pass/fail counts, SAST findings, CVE delta direction, runtime-trace coverage, policy-engine block events. Slower, more infrastructure, but the signal is from the world, not from the model.
- **Hybrid: objective primary, self-confidence as tie-breaker.** Compromise. Still vulnerable to the Confidence Trap when objective signals are borderline.

## Decision

**Trust score is computed from objective evidence only.** Specifically:

- Sandbox build status (binary)
- Test pass/fail counts and delta vs baseline
- SAST/DAST findings, new vs baseline
- CVE delta direction (more, same, or fewer)
- Runtime-trace coverage (which scenarios completed cleanly)
- Policy-engine block events (did any deterministic rule fire?)
- Coverage of changed code by existing tests

LLM self-reported confidence **may** be logged for observability and drift analysis. It **must not** feed the gate.

## Tradeoffs

| Gain | Cost |
|---|---|
| Gate is grounded in reality, not model self-report | More infrastructure: sandbox + scanners + signal aggregator |
| Confidence-Trap immunity — agents cannot "talk their way past" the gate | Gates take seconds/minutes (sandbox checks), not milliseconds |
| Gate verdicts are explainable — show the failing signal | Some classes of intent-level wrongness (semantically correct but goal-wrong code) are invisible to objective signals |
| Calibration is empirical (sample real outcomes, tune thresholds) | Threshold calibration (ADR-0015) requires production data — can't be set a priori |

## Consequences

- Stage 5 Validation (`../design.md §3` Stage 5) is the canonical objective-signal collector. The gate logic at every other stage's transition leans on the same signal sources.
- The trust-score formula is a weighted sum of objective signals; weights and the gate threshold are calibrated against post-merge incident data (ADR-0015 deferred).
- Until calibration data exists, gates use **binary pass/fail** on the most direct objective signal (build passes / tests pass / SAST finds nothing new). Conservative default.
- The "40-Point Rule" from `../../gemini-auto-agent-design.md` — halt when confidence/information gap exceeds 40 points — is interesting but contingent on reliable confidence signals. Per this ADR, we do not yet have those. Phase 3 concern.

## Reversibility

**Low cost** in the trivial direction (start including self-confidence in the score). **High cost** in the meaningful direction — if self-confidence ever enters the score, every gate's calibration must be redone, and the Confidence-Trap exposure returns.

## Evidence / sources

- `../design.md §4.6` (push-back: trust score uses objective signals only)
- `../../gemini-auto-agent-design.md §"Mitigating the Confidence Trap"` — empirical Confidence-Trap data
- `../../gemini-auto-agent-design.md §"Empirical Realities"` — agentic-PR breaking-change rates by task type
- arXiv 2603.27524 "Safer Builders, Risky Maintainers" — agents fail at higher rates during maintenance than feature work
