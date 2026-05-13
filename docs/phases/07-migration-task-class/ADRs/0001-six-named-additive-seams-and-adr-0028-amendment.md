# ADR-0001: Six named additive seams across Phase 0–6, plus an amendment to ADR-0028

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** extension-by-addition · contract-surface · adr-0028 · load-bearing
**Related:** [ADR-0002](0002-register-gate-probe-new-registry.md), [ADR-0003](0003-objective-signals-widening-and-allowlists.md), [ADR-0004](0004-fallback-tier-task-type-kwarg.md), [ADR-0005](0005-openrewrite-rewrite-docker-deferred.md), [ADR-0006](0006-runtime-trace-probe-stub-kept-forever.md), [ADR-0007](0007-recipe-engine-literal-extended-with-dockerfile.md), [ADR-0009](0009-contract-surface-snapshot-canary.md), [production ADR-0028](../../../production/adrs/0028-task-class-introduction-order.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)

## Context

The roadmap's Phase 7 exit criterion says "the diff for this phase touches **only** new files — no Phase 0–6 source code is modified" (`roadmap.md §Phase 7 Exit criteria`; restated in production ADR-0028 Consequences). The three lens designs proved that reading is incompatible with the actually-shipped Phase 0–6 contracts (`critique.md §Cross-design observations §"Which disagreement matters most for this phase?"`):

- Phase 2's `Probe` ABC and coordinator are byte-frozen per ADR-0007 — `[S]`'s `applies_to_lifecycle: ClassVar` field is the edit it claims isn't.
- Phase 3's `Recipe.engine` and `RecipeSelection.reason` are closed `Literal`s — `[B]`'s "additive" new value is a source edit.
- Phase 4's `FallbackTier.run` does not take a `task_type` kwarg — all three designs assume task-class-routed prompts and corpora that don't exist without one.
- Phase 5's `ObjectiveSignals` is the cross-phase signal contract — adding four new signal kinds means widening it.

The synthesizer enumerated *exactly six* additive seams crossing Phase 0–6 surfaces, each with a per-phase ADR (this ADR plus 0002–0007), each with its diff snapshotted by the new permanent contract-surface canary (ADR-0009 in this phase), each PR-amended 1:1 with the snapshot regeneration (`final-design.md §"Departures from all three inputs" #3`; `phase-arch-design.md §Component 13`). The alternative — preserving the literal "zero source-line diff" reading by forking `FallbackTier`, the engine `Literal`, the signal model, and the CLI dispatch — bequeaths doubled surface area to Phase 8 (`final-design.md §"Departures from all three inputs" #5`).

This ADR records the central decision: **amend production ADR-0028 to define "extension by addition" as *behavior-preserving additive extension*, count the seams Phase 7 opens, and make the snapshot canary the permanent enforcement going forward.**

## Options considered

- **Literal-zero-edit (the maximalist reading).** Fork everything Phase 7 needs: parallel `MigrationFallbackTier`, parallel signal Pydantic model, parallel engine `Literal`, parallel CLI dispatch with its own subcommand surface. Preserves the strict reading; bequeaths Phase 8 every fork to merge (`final-design.md §"Departures from all three inputs" #5`).
- **Quiet edits (the maximalist's opposite).** Edit Phase 0–6 files as needed, justify each in commit messages, no separate ADR per edit. Fast but violates the load-bearing commitment.
- **Six named additive seams + ADR-0028 amendment.** Enumerate the minimum set of additive extensions (new file, optional field, default-`None` kwarg, additive `Literal` value, additive registry entry), one per-phase ADR, contract-surface canary catches anything outside the list. The synthesizer's hybrid (c).

## Decision

Amend production ADR-0028 with a one-paragraph refinement: *"Extension by addition means **behavior-preserving additive extension**: new files; new registry entries; new optional fields on Pydantic models; new default-`None` kwargs on existing functions; new values in previously-closed `Literal`s — each gated by a per-phase ADR that names the exact diff and amends the contract-surface snapshot in the same PR. Behavior-changing edits to existing logic remain forbidden."* Phase 7 opens exactly six seams under this rule — ADR-P7-001 through ADR-P7-006 (mapped to ADRs 0002–0007 in this phase folder). Any seventh seam is a contract-surface canary failure (ADR-0009) and blocks the PR.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 8's supervisor inherits *one* `FallbackTier`, *one* signal model, *one* engine registry — not parallel forks of each | Production ADR-0028 carries a permanent amendment paragraph; reviewers of any later task class must read it before judging "is this PR additive?" |
| Six is small enough to enumerate in one ADR table; reviewers can audit the full seam list against the PR diff in one glance | The literal "zero source-line diff" reading of Phase 7's roadmap exit criterion is *qualified*, not satisfied — the roadmap entry needs an accompanying note pointing at this ADR set |
| Each seam is per-phase ADR'd, contract-surface-snapshotted, and reviewable in isolation — extension-by-addition becomes a checklist, not a vibe | The contract-surface snapshot becomes a permanent artifact every later phase must touch when its own seams open — discipline survives only if every phase author actually writes the ADR (ADR-0009 enforces the linkage mechanically) |
| The "extension-by-addition" commitment now has an operational definition that survives whitespace edits and in-file refactors (which BLAKE3-of-source freeze breaks) | Phase 7 is the phase that lands the amendment — reviewers may push back on widening the commitment's text in the *same* PR that exercises it |
| Phase 13/14/15 inherit a small, named extension grammar — they pattern-match instead of inventing new contract-violation shapes | The amendment is itself a load-bearing commitment; future phases that don't fit the six allowed shapes must either propose a seventh seam (with ADR) or fork |

## Consequences

- Production ADR-0028 receives a one-paragraph amendment when Phase 7 merges; the amendment is referenced from this ADR and `final-design.md §Goals#18 / §"Departures" #3`.
- Phase 7's PR ships *seven* documents in lockstep: this ADR, six seam ADRs (0002–0007), the regenerated `tools/contract-surface.snapshot.json`, and the amendment to production ADR-0028.
- The contract-surface snapshot canary (ADR-0009) is the *mechanical* enforcement; PR template + `tools/snapshot_regen_audit.py` (phase-arch-design §Gap 5) require an ADR-NNNN reference for every snapshot diff.
- Phase 8's first PR is the *first test* of whether the discipline propagates: it will exercise its own additive seams; if Phase 8 cannot fit them into the six allowed shapes, the amendment is revisited.
- Any later phase wanting to add a *new shape* of seam (e.g., a renamed registry, a new ABC) cannot — they must either fit one of the six patterns or write a Phase-N-level amendment to this ADR.
- The strict-zero-edit alternative remains documented (`final-design.md §"Departures from all three inputs" #5`) for the user; this ADR records the synthesizer's recommendation, not a foreclosure.

## Reversibility

**Low.** Once the amendment to ADR-0028 ships and Phase 8 builds on the six-seam vocabulary, reverting means re-forking everything Phase 7 unified — Phase 8's supervisor would have to learn two `FallbackTier` shapes, two engine `Literal`s, two signal models. Reverting *before* Phase 8 lands is moderate (one phase of code; the amendment paragraph can be removed). After Phase 8: high cost. The asymmetry is intentional — the amendment exists to *prevent* the doubled-surface-area outcome, and reversal recreates it.

## Evidence / sources

- `../final-design.md §"Lens summary"` (the synthesizer's hybrid (c) position)
- `../final-design.md §Goals#18` ("frozen Phase 0–6 behavioral code")
- `../final-design.md §"Departures from all three inputs" #3` (the six-seam enumeration)
- `../final-design.md §"Departures from all three inputs" #5` (strict-zero-edit alternative)
- `../final-design.md §"Roadmap coherence check"` ("Extension by addition. Honored *with explicit, named amendment*.")
- `../phase-arch-design.md §Executive summary` (the amendment text)
- `../phase-arch-design.md §Component 13` (the seam-by-seam breakdown)
- `../critique.md §"Cross-design observations" §"Which disagreement matters most for this phase?"` (closed-Literal wall)
- [production ADR-0028](../../../production/adrs/0028-task-class-introduction-order.md) — the production ADR this phase amends
- [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) — Probe contract preserved
