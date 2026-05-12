# ADR-0008: LLM Judge persona deferred; surfaced as roadmap gap

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** roadmap-gap · deferral · persona
**Related:** [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md), [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md)

## Context

`docs/production/design.md §3.1` lists an "LLM Judge / Functional-Equivalence Critic" persona at Stage 5 Validation, invoked "on disagreement when objective signals conflict." All three Phase-5 input designs defer this persona to "Phase 5+N." The synthesis defers it. The roadmap (Phases 5–16) does not name an owner. `ADR-0008` explicitly forbids LLM self-confidence as a *trust-score input*, but does not forbid LLM *adjudication of conflicting objective signals* — those are different functions. There is a real gap between the production-design persona and the roadmap. See [final-design.md §Roadmap gap surfaced](../final-design.md#roadmap-gap-surfaced-architect-should-pick-up-separately) and [phase-arch-design.md §Gap 3](../phase-arch-design.md#gap-3-the-llm-judge-persona-is-unowned-by-any-roadmap-phase).

## Options considered

- **Ship the persona in Phase 5** — Adds a probabilistic component to a deterministic phase. Violates the Phase 5 fence-CI deny-list (`anthropic` import is forbidden in `gates/`). Pre-empts a decision that needs ADR-0008 calibration data first.
- **Drop the persona from `production/design.md §3.1`** — Removes the gap, but loses a documented capability the production design considered necessary.
- **Defer with explicit ownership ask** — Record this ADR as the explicit deferral; flag a roadmap-amendment task; document that Phase 5's `ObjectiveSignals` strict-AND is the *only* gate verdict source until a future phase ships the Judge.

## Decision

The LLM Judge persona is deferred from Phase 5. This ADR records the deferral and the unowned-by-roadmap status. A roadmap-amendment task is opened to either: (a) assign the persona to Phase 12 (Stage 4/5 validation depth) or Phase 16 (production hardening); (b) drop the persona from `production/design.md §3.1`; (c) introduce a new mid-roadmap phase. Phase 5's architect is not authorized to make this choice but is authorized to surface it loudly.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 5's deterministic guarantee is preserved — no LLM in any gate decision path | `production/design.md §3.1`'s persona is not actually owned; risk that future readers assume Phase 5 covers it |
| Strict-AND with `extra="forbid"` is the strongest objective-signal contract; deferring the Judge avoids weakening it before evidence accrues | "Disagreement on objective signals" cases (e.g., trace says new endpoint, policy says allowed) currently escalate to human — possibly more often than necessary |
| The roadmap-amendment task is concrete and assignable | Until the amendment lands, every future architect re-discovers the gap |
| ADR-0008 (production) — LLM self-confidence in trust scoring is forbidden — remains crisp; this ADR distinguishes it from *adjudication* of conflicting facts | The two LLM-uses-in-validation are easy to conflate in discussion |

## Consequences

- A TODO is added to `docs/production/design.md §3.1` pointing to this ADR.
- The roadmap-amendment task is the deliverable; it is not Phase 5's deliverable.
- Phase 5 ships no LLM Judge code; the fence-CI deny-list stays.
- If the persona lands in a future phase, this ADR is **superseded** (the new ADR cross-links back); the deferral ends.
- New invariant: any future ADR introducing an LLM into gate adjudication must explicitly distinguish it from "LLM self-confidence as trust-score input" (forbidden by ADR-0008) and supersede this ADR.

## Reversibility

**High.** This ADR is a deferral record, not a structural decision. The reversal is the future phase's ADR introducing the Judge; this ADR is then marked superseded. Cost of reversal is the new phase's implementation, not any rework here.

## Evidence / sources

- [final-design.md §Roadmap gap surfaced](../final-design.md#roadmap-gap-surfaced-architect-should-pick-up-separately)
- [phase-arch-design.md §Gap 3](../phase-arch-design.md#gap-3-the-llm-judge-persona-is-unowned-by-any-roadmap-phase)
- [critique.md roadmap §5](../critique.md)
- `docs/production/design.md §3.1` — the persona this defers
- [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md) — what this ADR composes with but does not violate
