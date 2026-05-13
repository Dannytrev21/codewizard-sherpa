# ADR-0002: Promotion gate keys on `lower_bound_95` (BCa bootstrap), not `mean_score`

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** statistics · promotion · honest-confidence · phase-7-precondition
**Related:** [ADR-0009](0009-automatic-demotion-as-recommendation-shift.md), [Phase 5 ADR-0016](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md), [production ADR-0015](../../../production/adrs/0015-trust-score-threshold-calibration.md), [production ADR-0028](../../../production/adrs/0028-task-class-introduction-order.md)

## Context

[Phase 5 ADR-0016 §Decision §4](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) wrote the promotion criterion as `bench_score.mean ≥ tier_threshold[N+1]` over `≥ min_cases_for_promotion[N+1]` cases. All three Phase 6.5 input designs implicitly inherited `mean` as the gate signal. The critic surfaced the load-bearing problem (critic roadmap-level #1): N=10 is the floor for `min_cases_for_promotion[bronze]`, and at N=10 the sample mean carries substantial uncertainty — `mean - 2·stddev` may be a full tier below the threshold the mean nominally crosses. A gate that flips `evidence_sufficient = True` on a sample mean that crosses threshold by 0.01 with stddev 0.12 is calling something "sufficient evidence" that is, statistically, indistinguishable from "we got lucky on 10 draws."

This collides with [CLAUDE.md §"Honest confidence"](../../../CLAUDE.md): every probe reports its confidence and provenance. The eval harness *is* a probe on judgment quality; reporting only `mean` hides the uncertainty that is the load-bearing fact for whether the harness's evidence is actionable. [Production ADR-0015 (threshold calibration)](../../../production/adrs/0015-trust-score-threshold-calibration.md) further requires "per-task-class refinement … balance false-positive and false-negative rates" — a discipline that cannot be exercised against a point estimate.

The shift from `mean` to a one-sided lower bound is the safe direction: a bound that exceeds the threshold means *every plausible value of the true mean* exceeds the threshold (at the 95% confidence level). A bound that does not exceed it means the harness is honest about what it cannot yet conclude. For Phase 7's hard precondition (`roadmap.md §Phase 7` exit criteria), this is a strict tightening — not a weakening — of the bar.

## Options considered

- **`mean_score ≥ tier_threshold`** (ADR-0016's literal text). Simplest; matches sentiment. Fails the N=10 statistical-noise test the critic identified.
- **Wilson score interval on `passed_count / total_count`** (pass/fail binomial). Natural for binary outcomes; well-studied at small N. But `BenchScore.score ∈ [0, 1]` is a continuous statistic, not pass/fail — Wilson loses signal in the partial-credit range that rubrics emit.
- **`lower_bound_95` from BCa bootstrap on the per-case `score` distribution.** Standard for asymmetric distributions on `[0, 1]`. Deterministic with a seed; one-sided lower confidence bound is the directionally safe operationalization of "honest confidence." 1000 resamples is the literature default; seeded by `int(run_id[:8], 16)` for reproducibility.
- **Frequentist t-interval on the mean.** Assumes normality; `BenchScore.score` is bounded on `[0, 1]` and often skewed — t-interval may produce bounds outside `[0, 1]`. Rejected.

## Decision

`PromotionGate.evaluate(...)` keys `evidence_sufficient` on `report.lower_bound_95 ≥ tier_threshold[target_tier]`, **not** on `mean_score`. `lower_bound_95` is computed as the 2.5th percentile of a 1000-resample BCa bootstrap over the per-case `BenchScore.score` values, with a deterministic seed `int(run_id[:8], 16)`. `mean_score` and `score_stddev` continue to land on `BenchRunReport` for human review. Phase 7's exit criterion (`roadmap.md §Phase 7`) is amended in lockstep: `bench_score.mean ≥ tier_threshold[bronze]` becomes `bench_score.lower_bound_95 ≥ tier_threshold[bronze]`.

## Tradeoffs

| Gain | Cost |
|---|---|
| Honest confidence ([CLAUDE.md](../../../CLAUDE.md)) is operationalized — the gate cannot flip on N=10 noise that a point estimate would mask | First-10-case runs will produce `evidence_sufficient=False` even when the sample mean is above threshold; promotion timelines stretch by weeks until N grows |
| One-sided lower bound is directionally safe: if the bound exceeds the threshold, every plausible true mean (at 95%) exceeds it | Bootstrap CI at N=10 has known small-sample issues (`final-design.md §Open Q #5`); the gate is conservative, but the precision of the bound itself is limited |
| Phase 7's exit criterion tightens: same threshold value, more evidence required to cross it. The criterion is met *more honestly*, not less | The roadmap text needs a one-word substitution; Phase 7's planning assumed `mean` and may need recalibration of expected promotion cadence |
| `mean_score` and `score_stddev` continue to ship — the operator still sees the point estimate and dispersion; only the *gate* keys on the bound | Two-statistic reporting plus the gate's one-statistic decision means readers must understand which signal the gate consumes |
| Deterministic bootstrap seed (`int(run_id[:8], 16)`) keeps `BenchRunReport`s byte-identical across reruns of the same inputs | The seed-derivation rule is structural state; changing it would invalidate the audit chain's reproducibility claim |
| When `BenchScore.score` collapses to `{0.0, 1.0}` in practice (binary pass/fail in disguise), Wilson on `passed_count/total` becomes a more natural signal — and the switch is one function call in `runner.py` | A future switch to Wilson is itself an ADR amendment (see ADR-0002 §"Revisit trigger" below); the gate signal is not free to evolve silently |

## Consequences

- `BenchRunReport` carries three statistics: `mean_score`, `score_stddev`, `lower_bound_95`. `lower_bound_95` is the sole input to `PromotionGate.evaluate(...)`.
- Phase 7's hard precondition (`roadmap.md §Phase 7` exit criterion: "≥ 10 cases + `bench_score.X ≥ tier_threshold[bronze]`") shifts `X` from `mean` to `lower_bound_95`. The roadmap edit is the same word-substitution discipline as [ADR-0009](0009-automatic-demotion-as-recommendation-shift.md).
- The Phase 6.5 implementation ships a `tests/unit/test_bootstrap.py` invariant suite: deterministic `lower_bound_95` for a fixed seed; `mean - 2·stddev ≤ lower_bound_95 ≤ mean` as a sanity property (Hypothesis-property-tested).
- The bootstrap is the **single probabilistic surface** in an otherwise fully-deterministic harness (`phase-arch-design.md §Determinism vs probabilism`). Leafed and seeded — no other component branches on RNG.
- **Revisit trigger.** If after Phase 7 ships and the first 50 cases land for `migration-chainguard-distroless`, the per-case `score ∈ {0.0, 1.0}` rate exceeds 80% (the rubric is effectively binary), the gate switches to Wilson on `passed_count / total`. The condition is observable from `BenchRunReport`s; the switch is a one-function-call change in `runner.py` and an ADR amendment.
- [Production ADR-0015](../../../production/adrs/0015-trust-score-threshold-calibration.md) gains structural evidence: per-task-class threshold candidates must be picked *below* the observed mean over the first ≥ 50 production cases — not at it — because `lower_bound_95` at N=10 typically sits 0.05–0.15 below the mean.
- The promotion gate's `reasons` tuple enumerates the lower-bound shortfall explicitly when `evidence_sufficient=False` (e.g., `("lower_bound_95=0.78 < threshold=0.80",)`), so the human reviewer sees the gap, not just the verdict.

## Reversibility

**Medium.** Reverting to `mean_score` is one branch change in `PromotionGate.evaluate`. But every prior `BenchRunReport` would need its verdict recomputed under the old rule before the chain can be cited as evidence at the old threshold — and the prior verdicts are part of the BLAKE3 chain. The path is "supersede this ADR, recompute verdicts as advisory data, do not rewrite the chain." Forward evolution to Wilson (per the revisit trigger above) is mechanically easier than reverting to `mean`. The Phase 7 exit criterion's one-word substitution is the load-bearing externality; once Phase 7 ships under `lower_bound_95`, reverting tightens Phase 7's bar retroactively, which is awkward but not data-destroying.

## Evidence / sources

- [final-design.md §Departures from all three inputs #2](../final-design.md#departures-from-all-three-inputs)
- [final-design.md §Synthesis ledger row "Promotion gate key statistic"](../final-design.md#conflict-resolution-table)
- [final-design.md §Risks #3](../final-design.md#risks-top-5)
- [final-design.md §Open questions #5](../final-design.md#open-questions-deferred-to-implementation)
- [phase-arch-design.md §Goals #8](../phase-arch-design.md#goals)
- [phase-arch-design.md §Agentic best practices — Confidence handling](../phase-arch-design.md#agentic-best-practices)
- [phase-arch-design.md §Gap analysis Gap 6](../phase-arch-design.md#gap-6-bootstrap-method-choice-deferred-without-naming-the-precondition-for-revisiting)
- [critique.md §Roadmap-level critiques #1](../critique.md#roadmap-level-critiques)
- [Phase 5 ADR-0016 §Decision §4](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) — the text this ADR shifts from `mean` to `lower_bound_95`
- [production ADR-0015](../../../production/adrs/0015-trust-score-threshold-calibration.md) — the threshold-calibration ADR whose evidence shape this ADR sharpens
- BCa bootstrap: Efron, *An Introduction to the Bootstrap* (1993), §14
