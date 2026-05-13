# ADR-0009: "Automatic demotion" semantics — recommendation-shift, not side-effect (amends Phase 5 ADR-0016)

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** promotion · demotion · humans-always-merge · adr-amendment
**Related:** [ADR-0002](0002-promotion-gate-keys-on-lower-bound-95.md), [ADR-0003](0003-tier-identifiers-as-str-validated-at-startup.md), [Phase 5 ADR-0016](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md), [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md)

## Context

[Phase 5 ADR-0016 §Decision §4](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) writes:

> Demotion is automatic on any production regression that the bench set fails to catch (the regression becomes a new bench case; the score recomputes; the tier drops if it falls below threshold).

The text reads two ways. **Reading A (process-shift):** demotion is "automatic" in the sense that a `PromotionVerdict` mechanically flips from `evidence_sufficient=True` to `evidence_sufficient=False` when a regression-converted case lands and the recomputed `lower_bound_95` falls below the current tier's threshold. The verdict surfaces in `.codegenie/eval/recommendations/`; a human still authors the PR that edits `docs/trust-tiers.yaml` to record the tier downgrade. **Reading B (side-effect):** demotion is "automatic" in the sense that *code somewhere mutates the current-tier state* — `docs/trust-tiers.yaml` updates, or a `current_tier` field on a registry record flips — without a human PR.

Reading B violates [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md): "humans always merge." If a regression auto-demotes a task class from silver to bronze without a human-authored PR, the system has decided autonomously that a fleet of in-flight PRs operating at silver-tier autonomy should be downgraded — a decision with real operator-trust and customer-trust consequences. The Phase 6.5 input designs all chose Reading A implicitly (the promotion gate is read-only; `apply()` raises; tier mutations require hand-edited PRs), but none of the three made the interpretation explicit. The synthesis ledger flagged this (`final-design.md §Load-bearing commitments` — ADR-0016 §Decision §4 row).

This ADR resolves the ambiguity by amending Phase 5 ADR-0016: "automatic demotion" means *the verdict recomputes mechanically*; demotion as a state-change requires the same human-authored PR + CODEOWNERS approval + ADR amendment path as promotion. Future phases reading ADR-0016 §Decision §4 should not re-litigate this.

## Options considered

- **Reading B as-stated** (auto-mutation on regression). Smallest verdict-loop latency; recipe-set degrades silently from operator perspective. Violates [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md); makes a tier-state mutation a code-driven side effect.
- **Reading A — recommendation-shift only** (synthesized). `PromotionGate.evaluate(...)` returns the new verdict; `PromotionGate.apply(...)` raises unconditionally; the tier state in `docs/trust-tiers.yaml` is hand-edited by the operator who reviewed the recommendation. The "automation" is the mechanical recomputation of the verdict, not the mechanical mutation of state. Symmetrical to promotion's "humans always promote" structural marker.
- **Time-bound auto-demotion with an override window** (hybrid). Auto-mutates after N days of `evidence_sufficient=False`, unless an operator opts out. Adds a time-based control loop, introduces the "operator went on vacation" failure mode, still violates ADR-0009 on its primary path. Rejected.

## Decision

This ADR amends [Phase 5 ADR-0016 §Decision §4](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md): "demotion is automatic" is read as "the `PromotionVerdict` is recomputed automatically; demotion as a state-change is a human-authored PR." `PromotionGate.evaluate(...)` emits an advisory verdict (the `requires_human_approval: Literal[True]` field is the structural marker). `PromotionGate.apply(...)` raises `PromotionMustBeHumanAuthorized` unconditionally; the asymmetry is the load-bearing structural enforcement of "humans always promote, humans always demote." Tier mutations require the same path as promotions: hand-edited PR against `docs/trust-tiers.yaml` + CODEOWNERS approval + ADR amendment naming the new tier-state evidence.

## Tradeoffs

| Gain | Cost |
|---|---|
| Honors [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md) end-to-end — no code path mutates tier state autonomously, on either promotion or demotion | Demotion latency grows: a regression-converted case landing on Tuesday produces a recommendation that may not be acted on until Thursday, during which time PRs continue to operate at the higher tier |
| Symmetrical interface: `PromotionGate.apply()` raising on *both* promotion and demotion means callers cannot accidentally rely on side-effect demotion in a way they could not rely on side-effect promotion | The "automatic" label in ADR-0016 prose is unintuitive — operators must read this ADR to discover it means "recommendation auto-updates," not "state auto-updates" |
| The recommendation surface (`.codegenie/eval/recommendations/<utc-iso>.json`) is the single source of truth for tier-change advice; both promotions and demotions land there in the same shape | A future operator-facing dashboard must promote demotion recommendations as prominently as promotion recommendations — otherwise the asymmetry becomes "promotion is visible, demotion is buried" |
| Closes a re-litigation surface: future phases reading ADR-0016 §Decision §4 see this amendment cited and do not need to redecide | The amendment-cite pattern (this ADR + Phase 5 ADR-0016 §Decision §4 cross-link) requires the Phase 5 ADR to be edited to add a "amended by" pointer — a cross-phase ADR edit |
| The "regression-converted case → recomputed verdict" loop is documented and the consumer contract is clear: Phase 13's outcome-ledger reconciliation produces new bench cases, Phase 6.5's harness recomputes the verdict, an operator reads the recommendation and decides | Phase 13's reconciliation cadence is not yet specified; the demotion-recommendation latency depends on Phase 13 design. This ADR does not commit Phase 13 to a specific cadence |

## Consequences

- **Phase 5 ADR-0016 is amended.** The amendment adds a paragraph after §Decision §4 reading: "'automatic' refers to the verdict recomputation; tier state in `docs/trust-tiers.yaml` is mutated only via human-authored PR per [Phase 6.5 ADR-0009](../../06.5-per-task-class-eval-harness/ADRs/0009-automatic-demotion-as-recommendation-shift.md)." The Phase 5 ADR-0016 file gains a "Amended by" entry under its Related list.
- `src/codegenie/eval/promotion.py`'s `PromotionGate.apply(...)` raises `PromotionMustBeHumanAuthorized` on *every* call — promotion *and* demotion. The error message names the path: "Tier changes require a hand-edited PR against `docs/trust-tiers.yaml` + CODEOWNERS approval + ADR amendment."
- `PromotionVerdict.requires_human_approval: Literal[True]` is the structural marker; the type system makes "not requiring approval" unrepresentable.
- The `PromotionVerdict` shape is the same for promotion and demotion recommendations — the `target_tier` field carries the recommended new tier (which may be lower than `current_tier`); `reasons` enumerates the evidence basis.
- The `.codegenie/eval/recommendations/<utc-iso>.json` directory carries both promotion and demotion recommendations; consumer tooling (Phase 11 PR provenance, future dashboards) reads both uniformly.
- `tests/adv/test_promotion_apply_raises.py` asserts `apply()` raises on every call signature; the test is part of the harness's load-bearing structural guarantee.
- Phase 13's outcome-ledger reconciliation (the producer of `regression-converted` bench cases) is the source of demotion-triggering evidence; the consumer side (recompute verdict + emit recommendation) lives in this phase.
- The interpretation extends to future tier semantics: if a fifth tier (e.g., `"emerald"`) is added per [ADR-0003](0003-tier-identifiers-as-str-validated-at-startup.md), the no-side-effect rule applies uniformly — all tier changes are human-authored PRs.

## Reversibility

**Low.** Reverting to Reading B (auto-mutation) would require deleting the `PromotionGate.apply()`-raises invariant and adding a write path to `docs/trust-tiers.yaml`. The change would re-open the [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md) violation surface; it would be detectable in code review but the trust-model degradation is durable. The Phase 5 ADR-0016 amendment cross-links this ADR; reverting requires editing both. The interpretation is the load-bearing fact; the encoding (raise on `apply`) is the structural enforcement. Forward evolution is fine — adding tier-change-evidence requirements, requiring two CODEOWNERS reviewers instead of one — these tighten the discipline, not loosen it.

## Evidence / sources

- [final-design.md §Load-bearing commitments check](../final-design.md#load-bearing-commitments-check) — "ADR-0016 §Decision §4 clauses honored: §4 trust-tier promotion gate: ✓ (`evaluate` reads, `apply` raises). 'Demotion is automatic on any production regression' interpreted as **recommendation-shift, not side-effect**"
- [final-design.md §Promotion gate semantics](../final-design.md#conflict-resolution-table)
- [phase-arch-design.md §Component design — `promotion.py`](../phase-arch-design.md#srccodegenieevalpromotionpy)
- [phase-arch-design.md §Goals #7](../phase-arch-design.md#goals)
- [phase-arch-design.md §Non-goals #12](../phase-arch-design.md#non-goals)
- [phase-arch-design.md §Scenarios — Scenario 4](../phase-arch-design.md#scenario-4-promotion-gate-verdict-flips-on-bootstrap-ci-shift-decision-point-flip)
- [critique.md §Roadmap-level critiques #3](../critique.md#roadmap-level-critiques) ("Load-bearing-commitment violations" — ADR-0009 carve-out concerns)
- [Phase 5 ADR-0016 §Decision §4](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) — the text this ADR amends
- [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md) — the load-bearing commitment this ADR preserves
