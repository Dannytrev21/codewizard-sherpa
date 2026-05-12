# ADR-0003: Extend Phase 3 `TrustScorer` via open signal-kind registry; do not replace

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** trust · extension-by-addition · registry · phase-boundary
**Related:** [ADR-0002](0002-additive-prior-attempts-kwarg.md), [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md), [production ADR-0015](../../../production/adrs/0015-trust-score-threshold-calibration.md)

## Context

Phase 3 already ships a `TrustScorer` implementing the strict-AND of objective signals per [ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md). Phase 5 needs to score six signal kinds (build, install, tests, trace, policy, cve_delta) — three of which (trace, policy, cve_delta) Phase 3 doesn't know about. Phase 7 distroless will later add `baseimage` and `shell_presence`. Two of the three input designs proposed *replacing* Phase 3's scorer with a new aggregator; one proposed extending. The roadmap's "extension by addition" commitment forbids editing existing components when new task types arrive. See [final-design.md §Synthesis ledger row: Phase 3 `TrustScorer` relationship](../final-design.md#synthesis-ledger) and [phase-arch-design.md §Component design — `Gate` + `StrictAndGate`](../phase-arch-design.md#gate-abc--strictandgate).

## Options considered

- **Replace with `SignalAggregator` (performance-first)** — New Phase 5 scorer. Drops Phase 3's strict-AND. Forces Phase 3 callsites to migrate or wrap.
- **Replace with `ObjectiveSignals` model + new evaluator (security-first)** — Type-strict, but two scorers coexist in the codebase with no clear precedence.
- **Closed `Literal` of signal kinds in Phase 5 (best-practices)** — Extends `TrustScorer` but pins the signal set to four kinds. Phase 7 distroless can't add a kind without editing Phase 5's Literal.
- **Extend Phase 3's `TrustScorer`; widen signal kinds via an open `@register_signal_kind` registry** — Reuses Phase 1's `@register_probe` pattern. `StrictAndGate` is a ~40 LOC adapter that materializes `TrustSignal` list from `ObjectiveSignals` and calls Phase 3's existing `score(...)`.

## Decision

Phase 3's `TrustScorer` is the canonical strict-AND scorer; Phase 5 does not ship a second one. `StrictAndGate.evaluate` is a thin adapter that materializes `list[TrustSignal]` from populated `ObjectiveSignals` sub-models and delegates to `Phase3TrustScorer.score(signals)`. New signal kinds register via `@register_signal_kind("name")` decorator; `TrustSignal.kind` is widened from a closed enum to an open string keyed by the registry. The widening is additive and one-shot in Phase 3; Phase 7 (and beyond) registers kinds without editing.

## Tradeoffs

| Gain | Cost |
|---|---|
| Single source of truth for strict-AND scoring — Phase 3's logic is reused untouched | A ~40 LOC adapter must translate `ObjectiveSignals` → `list[TrustSignal]` faithfully (property test enforces equivalence) |
| Phase 7 distroless adds `baseimage` + `shell_presence` collectors without touching `TrustScorer` or `StrictAndGate` | `TrustSignal.kind` is now an open string — the type system no longer enumerates valid kinds (registry collision must be caught at import) |
| Honors "extension by addition" — the most-attacked commitment in [final-design.md §Load-bearing commitments §2.5](../final-design.md#load-bearing-commitments-check) | Adding a kind means an ADR amendment + a new optional field on `ObjectiveSignals` + a decorator registration; not a one-line change |
| Property test: `StrictAndGate.evaluate` returns the same `passed` value as `all(s.passed for s in signals)` AND as what Phase 3's `TrustScorer.score(...)` returns — equivalence regression-protects both sides | If Phase 3 ever drops strict-AND for weighted scoring, this adapter and its test loudly break |
| `tests/integration/test_trustscorer_widening.py` is a worked example Phase 7 can copy | Test fixtures must enumerate the cartesian product of populated/unpopulated signal kinds — ~2^6 cases |

## Consequences

- `src/codegenie/gates/strict_and.py` is the only adapter — ~40 LOC, no business logic.
- `TrustSignal.kind` widens from `Literal[...]` to `str` keyed by the `@register_signal_kind` registry; Phase 3's contract-snapshot test regenerates.
- `tests/integration/test_trustscorer_widening.py` exercises: (a) Phase 3's strict-AND still passes with only build/install/test populated; (b) the new kinds (trace, policy, cve_delta) participate in strict-AND without changing scorer logic.
- `sandbox/signals/registry.py` raises `SignalKindAlreadyRegistered` at import on duplicate kind — open Q10.
- Phase 5 does not own the threshold calibration logic ([ADR-0015](../../../production/adrs/0015-trust-score-threshold-calibration.md)) — strict-AND is binary; calibration is a future-phase concern when scoring becomes weighted.
- New invariant: any new signal kind must (a) register via decorator, (b) add an optional `<kind>: SignalSubModel | None = None` field to `ObjectiveSignals`, (c) be referenced by an ADR amendment. The Pydantic model widening is the only "edit" — and it is explicitly ADR-gated.

## Reversibility

**Low.** Reverting means picking a winner between "open registry of signal kinds" and "closed Literal." Switching back to closed would break Phase 7's planned extension and invalidate the registry pattern reused from `@register_probe`. Reverting to a *separate* scorer (not extending Phase 3's) would duplicate strict-AND logic and force a divergence resolution in every later phase. The adapter is small enough to delete; the contract decisions it enables are not.

## Evidence / sources

- [final-design.md §Synthesis ledger — Phase 3 `TrustScorer` relationship row](../final-design.md#synthesis-ledger) (winner score 12)
- [final-design.md §Synthesis ledger — Signal kind enum shape row](../final-design.md#synthesis-ledger) (winner: open registry — departure from all three)
- [final-design.md §Departures §1](../final-design.md#departures-from-all-three-inputs) — open signal-kind registry
- [final-design.md §Load-bearing commitments §2.5 — Extension by addition](../final-design.md#load-bearing-commitments-check)
- [phase-arch-design.md §Component design — Signal collectors](../phase-arch-design.md#signal-collectors-six-functions-open-registry)
- [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md) — the strict-AND contract this extends
