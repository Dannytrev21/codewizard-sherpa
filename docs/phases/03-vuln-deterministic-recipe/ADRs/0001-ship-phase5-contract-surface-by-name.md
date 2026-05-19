# ADR-0001: Ship the Phase-5 contract surface in Phase 3 — `RemediationOrchestrator`, `TrustScorer`, `Transform`, `ApplyContext`, `RecipeEngine`, `remediation-report.yaml`

**Status:** Accepted
**Date:** 2026-05-17
**Tags:** phase-boundary · contract · architecture · phase-5-integration
**Related:** [0002](0002-plugin-registry-kernel-instance-with-default-singleton.md), [0005](0005-two-stream-event-log-per-adr-0034.md), [0007](0007-run-npm-install-and-npm-test-in-phase3-jail.md), [production ADR-0031](../../../production/adrs/0031-plugin-architecture.md), [production ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md)

## Context

Phase 5's already-merged design (see `docs/phases/05-sandbox-trust-gates/`) names six load-bearing symbols by exact identifier: `RemediationOrchestrator`, `TrustScorer`, `Transform` ABC, `ApplyContext`, `RecipeEngine`, and the `remediation-report.yaml` artifact. Phase 5's `GateRunner.run(transition=stage6_validate, ctx=GateContext(...))` calls into the orchestrator's `_validate_stage6` method by name; `GateContext.transform_output: Transform` is typed against the ABC; `TrustScorer.score` is the scorer Phase 5 widens additively via `@register_signal_kind` (05-ADR-0003); `ApplyContext.prior_attempts` is the field Phase 5's ADR-P5-002 amends additively.

None of the three Phase 3 lens designs (performance, security, best-practices) actually shipped these names — the critic flagged this as Issue 1 in `critique.md`. The architecture spec resolves it (`phase-arch-design.md §Executive summary`, §Goal G2, §Component design C1–C6, §Departures from all three inputs #1; `final-design.md §Synthesis ledger row 1`, score 15/15). Either Phase 3 ships the contract surface now or Phase 5 re-amends Phase 3 contracts before it can land.

## Options considered

- **Option A — Defer the named seams to Phase 5.** Phase 5 ships its `GateRunner` against a stub orchestrator it has to build itself, then back-fills the seam contract during its own work. **Pattern:** none — pure ordering choice that breaks extension-by-addition the other way.
- **Option B — Ship the names but leave Phase-5-only fields off the models (e.g., omit `ApplyContext.prior_attempts`).** Phase 5 amends the Pydantic models when its retry envelope lands. **Pattern:** Smart constructor with under-specified shape — breaks the contract-snapshot test.
- **Option C — Ship the full named surface in Phase 3 with Phase-5-required fields already present (`prior_attempts: list[AttemptSummary] = []`), guarded by a contract-snapshot test.** **Pattern:** Dependency inversion + Phase-boundary stable contract — Phase 5 wraps the existing surface, never re-edits it.

## Decision

Adopt **Option C.** Phase 3 ships `RemediationOrchestrator` (`src/codegenie/transforms/orchestrator.py`), `TrustScorer` (`trust_scorer.py`), `Transform` ABC + concrete subclasses (`transform.py`), `ApplyContext` with `prior_attempts: list[AttemptSummary] = Field(default_factory=list)` (`apply_context.py`), `RecipeEngine` Protocol (`plugins/protocols.py`), and writes `remediation-report.yaml` from every workflow. A CI-gating `tests/integration/test_phase5_contract_snapshot.py` byte-snapshots the surface so Phase 5 cannot land if Phase 3 has drifted.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 5 lands without re-amending Phase 3 — its `GateRunner` wraps an existing method, not a method it has to invent | `prior_attempts` is dead weight in Phase 3 (always empty); the `_validate_stage6` underscore-prefix is load-bearing-but-private-looking |
| The contract-snapshot test catches any drift before Phase 5 work starts (G2 in phase-arch-design.md) | Snapshot tests are brittle; any intentional cross-phase contract change requires deliberate snapshot regeneration + ADR amendment |
| `Transform` ABC + sealed concrete hierarchy makes `isinstance(t, Transform)` checks in Phase 5 work without `runtime_checkable` Protocol overhead (see [ADR-0006 of Phase 5](../../05-sandbox-trust-gates/ADRs/0006-protocol-vs-abc-convention.md)) | One symbol breaks the otherwise-uniform Protocol-everywhere convention; reviewer might miss the rationale |
| `remediation-report.yaml` is the artifact Phase 5 reads to decide retry; shipping its schema now means Phase 5's gate-runner emits compatible output verbatim | Schema rigidity — Pydantic `extra="forbid"` means Phase 5 cannot quietly add fields; every addition is a contract amendment |
| `TrustScorer.score` signature is fixed at Phase 3 time; Phase 5's `SignalKind` registry widening is additive (05-ADR-0003 confirms the shape) | The scorer must read its own workflow's event log for `AdapterDegraded` markers — Constructor-injection of `EventLog` is required (see Consequences) |

## Pattern fit

Implements **Dependency inversion** (toolkit §Composition / coupling patterns): the Phase-3 modules declare the abstractions; Phase 5's higher-level retry envelope depends on those abstractions, not on Phase 3 internals. Also instantiates **Phase-boundary stable contract** — once shipped under the `transforms/` namespace, the public symbols are closed for modification, open for extension via subclass / decorator. The `Transform` ABC is the documented exception to the Protocol-everywhere preference (toolkit §Composition over inheritance): a sealed hierarchy beats a `runtime_checkable` Protocol when downstream code uses `isinstance`.

## Consequences

- `src/codegenie/transforms/__init__.py` re-exports `RemediationOrchestrator`, `TrustScorer`, `Transform`, `ApplyContext`, `RecipeEngine`, `RemediationOutcome`, `TrustOutcome`. A fence test asserts the export list.
- `tests/integration/test_phase5_contract_snapshot.py` is CI-required; failure blocks Phase 3 merges.
- `TrustScorer.__init__(event_log: EventLog)` (constructor-injection per Gap 5 in the architecture spec) — the scorer reads its workflow's event stream to fold `AdapterDegraded` events into `TrustOutcome.confidence`. Ambient-state alternative rejected.
- `RemediationOrchestrator._validate_stage6` is the explicit Phase-5 wrap target; renaming it is a contract break.
- Phase 4's `LLMProducedTransform(Transform)` subclass is the natural extension point — no edits to Phase 3's `Transform` ABC.
- The `remediation-report.yaml` schema lives in `src/codegenie/transforms/report.py` and ships with golden-file tests under `tests/golden/remediation-reports/`.
- New invariant: any change to the six named symbols requires a Phase-3 ADR amendment + Phase-5 ADR-update referencing the new shape.

**Amendment 2026-05-19 (S5-01):** `NotApplicableReason` Literal widened additively with `"NO_RECIPES_REGISTERED"`; `RecipeNotApplicable` widened with `considered: list[NotApplies] = Field(default_factory=list)`. Both changes are additive — Phase-5 callers reading only `.reason` continue to work (`considered=[]` default; pre-existing five Literal members preserved). Phase-4's prompt builder is the sole consumer of `considered`. The S6-06 Phase-5 contract snapshot (still pending implementation as of this amendment) will be baked with the new shape; ADR-0009 amendment of the same date moves the canonical `RecipeEngine` Protocol home to `src/codegenie/transforms/recipe_engine.py` (re-exported from `plugins/protocols.py`).

## Reversibility

**Low.** Once Phase 4, Phase 5, and Phase 6 land against these symbols, renaming or restructuring requires multi-phase coordination — every consumer of `RemediationOutcome`, `Transform`, or `ApplyContext` would need to migrate. The contract-snapshot test makes the cost visible at every PR; that's a feature, not a bug. A reversal would mean re-architecting the Stage 3–6 substrate.

## Evidence / sources

- `../phase-arch-design.md §Executive summary`, §Goals G2, §Component design C1, §Patterns considered and deliberately rejected (no factory)
- `../final-design.md §Synthesis ledger row 1` (score 15/15) and `§Departures from all three inputs #1`
- `../critique.md` Issue 1 ("Phase 5 integration — none of the three designs shipped the named seams")
- [Phase 5 ADR-0001 — two-chokepoint sandbox seam](../../05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md)
- [Phase 5 ADR-0002 — additive `prior_attempts` kwarg](../../05-sandbox-trust-gates/ADRs/0002-additive-prior-attempts-kwarg.md)
- [Phase 5 ADR-0003 — `TrustScorer` extension via `SignalKind` registry](../../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md)
- [Phase 5 ADR-0006 — Protocol vs ABC convention](../../05-sandbox-trust-gates/ADRs/0006-protocol-vs-abc-convention.md)
- [production ADR-0014 — three-retry default per gate](../../../production/adrs/0014-three-retry-default-per-gate.md)
