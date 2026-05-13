# ADR-0010: `isolation_class` annotation on `BenchRunReport` for Phase 16 microVM upgrade safety

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** audit-chain · phase-16-handoff · isolation-upgrade · population-mixing
**Related:** [ADR-0001](0001-rubric-execution-isolation-via-subprocess.md), [ADR-0002](0002-promotion-gate-keys-on-lower-bound-95.md), [Phase 5 ADR-0016](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md)

## Context

[ADR-0001](0001-rubric-execution-isolation-via-subprocess.md) picks subprocess + scrubbed env as the Phase 6.5 rubric-isolation posture; [Phase 5 ADR-0016 §Open Questions §5](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) explicitly defers the microVM upgrade decision to Phase 16. The critic identified the load-bearing observation (critic §"Which disagreement matters most for *this* phase?"): **scoring is not invariant under the isolation upgrade**. Different process model (subprocess fork vs microVM kernel boot), different timing (~150 ms vs seconds), and different env reachability (host environ visible-but-scrubbed vs guest kernel with no host environ at all) yield different `BenchScore` values for the same case and same rubric. A rubric that times out on subprocess (because some host syscall is slow) may complete inside a microVM (because the guest kernel handles it differently), and vice versa.

If Phase 16 upgrades rubric isolation from subprocess to microVM and the audit chain extends without distinguishing the two populations, the promotion gate's lookback over "the last N days" silently mixes pre-upgrade and post-upgrade `BenchRunReport`s. The mixed population's `lower_bound_95` is statistically meaningless — half the data is from one experiment, half from another, and the bootstrap treats them as a single distribution. The failure is silent: no exception, no warning, just a verdict computed on apples-and-oranges evidence.

The synthesis acknowledged this risk (`final-design.md §Departures` row 1, §Risks #2), but the original design did not annotate the audit record with the isolation class — the field was unsurfaced. The `phase-arch-design.md §Gap analysis Gap 1` made the gap explicit: without `isolation_class` on `BenchRunReport`, the Phase 16 upgrade's downstream effect is detectable only by accident (an operator noticing scores shifted suspiciously around upgrade time). The cost of adding the field is one byte of wire schema; the cost of *not* adding it is a silent-correctness failure of the entire audit chain.

This ADR closes the gap. The field is additive on the wire schema; the promotion gate's `evaluate(...)` is extended with one precondition; the cost is one field + one branch. The benefit is a structural guard against a silent failure mode that would otherwise be detected only when promotion verdicts produced under mixed populations are challenged after the fact.

## Options considered

- **No annotation** (Phase 6.5 input designs and original synthesis). Phase 16 upgrade silently mixes populations. Failure mode is silent and post-hoc detected. Rejected — violates [CLAUDE.md §"Fail loud"](../../../CLAUDE.md).
- **Per-record `isolation_class` annotation + promotion gate refuses to mix.** `BenchRunReport.isolation_class: Literal["subprocess", "microvm"]`, defaults to `"subprocess"` for Phase 6.5. The promotion gate's `evaluate(...)` adds a fourth condition: every report in the evidence window must share the same `isolation_class`. When Phase 16 upgrades, the next `BenchRunReport` flips to `"microvm"`; the gate immediately refuses to mix until Phase 16 hand-curates a transition record (or operators opt into a `--allow-isolation-mix` override that a future ADR catalogs).
- **External annotation** (out-of-band manifest naming which run-id-prefix used which isolation). Same information; weaker enforcement (the audit chain is the canonical record; out-of-band metadata drifts).
- **Hash the isolation environment into `run_id`** (so `run_id` distinguishes populations implicitly). Composes; opaque to readers. The gate would need to know how to parse the hash. Less clear than an explicit field.

## Decision

`BenchRunReport` gains an additive field `isolation_class: Literal["subprocess", "microvm"]` with default `"subprocess"` for Phase 6.5. `PromotionGate.evaluate(...)` adds a fourth precondition to `evidence_sufficient=True`: all `BenchRunReport`s in the evidence window must share the same `isolation_class` as the report being evaluated. Mixed populations produce `evidence_sufficient=False` with `reasons=("isolation_class mismatch in evidence window: subprocess={N1}, microvm={N2}",)`. The field defaults preserve current behavior; Phase 16's upgrade flips the value, and the gate refuses to mix until Phase 16 ships a transition contract (deferred ADR — out of scope for Phase 6.5).

## Tradeoffs

| Gain | Cost |
|---|---|
| The Phase 16 upgrade cannot silently invalidate the promotion gate — the field flip is detected mechanically | Phase 6.5 emits a field that has only one valid value today (`"subprocess"`); the field is structural foresight, not currently-load-bearing |
| The audit chain is self-describing: any future reader sees `isolation_class` and can stratify; out-of-band metadata is unnecessary | One additional Pydantic field on `BenchRunReport`; ~12 bytes per record on disk (~4 KB/year at nightly cadence) |
| The transition path is explicit: Phase 16 ships a hand-curated transition record (or `--allow-isolation-mix` operator override) — the failure mode is anticipated, not improvised | The "transition record" contract is deferred to Phase 16's ADR; Phase 6.5 commits to the gate's refusal-to-mix but not to the resolution mechanism |
| Symmetrical to [Phase 5 ADR-0016 §Open Questions §5](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) — the open question is now structurally addressed (the field exists; the threshold for "OK to mix" is Phase 16's call) | The defaults `"subprocess"` ships hardcoded; a future scoreboard run intending to use a different isolation must explicitly pass the value — the field is opt-in to non-default |
| Extension by addition: a future third isolation class (gVisor? bare-metal?) is a `Literal` widening + an ADR amendment + a transition contract. The architecture accommodates more than two | Adding a third class would force a structural decision on "which classes are compatible" — the current binary "all must match" rule doesn't generalize cleanly to many-class lattices |
| Symmetric to [ADR-0007](0007-bench-invocation-tagging-on-sandbox-cost-entry.md)'s additive-field discipline for cross-phase artifact integrity | Two structural-correctness fields (`isolation_class`, `bench_invocation`) carry the same "additive flag" pattern; readers must understand each independently |

## Consequences

- `src/codegenie/eval/models.py` declares `BenchRunReport.isolation_class: Literal["subprocess", "microvm"] = "subprocess"`. Default preserves Phase 6.5 behavior.
- `src/codegenie/eval/runner.py` writes `isolation_class="subprocess"` on every report it produces; the value is structural, not a runtime measurement.
- `src/codegenie/eval/promotion.py`'s `evaluate(...)` adds a precondition: all reports in the evidence window must share the report's `isolation_class`. Mismatch → `evidence_sufficient=False`, reason enumerated.
- `tests/unit/test_promotion.py` adds a case: two reports in the chain, one `subprocess` one `microvm`, evaluating against either produces `evidence_sufficient=False`.
- Phase 16's microVM-upgrade work owns a new ADR that (a) flips `isolation_class` in the runner, (b) defines the transition mechanism (hand-curated transition record, recalibration window, operator override flag), (c) updates Phase 5 ADR-0016 if needed.
- The promotion gate's `reasons` tuple makes the mismatch operator-visible: "isolation_class mismatch in evidence window" is a clear diagnostic — operators don't need to discover the mixed-population issue by inspection.
- `phase-arch-design.md §Gap analysis Gap 1` is closed by this ADR.
- The field is durable: even if Phase 16 chooses *not* to upgrade rubric isolation, the field carries `"subprocess"` permanently and the gate's check is a no-op. The cost of the structural foresight is paid once, recovered on the first isolation upgrade.
- Cross-platform consideration: a future macOS-only isolation class (e.g., `"sip-sandbox"`) would extend the Literal and require a transition contract — but no current ADR commits to that path.

## Reversibility

**High.** The field is additive; removing it is a Pydantic edit. But once Phase 16 produces records with `isolation_class="microvm"`, removing the field loses the discriminator that prevents silent population mixing. The forward path is the realistic direction: Phase 16 adds the upgrade ADR, ships the transition contract, and the field becomes load-bearing for that boundary. Pre-Phase-16, the field is structural foresight at near-zero cost — reverting before Phase 16 ships is mechanically easy but loses the gap-#1 protection.

## Evidence / sources

- [final-design.md §Departures from all three inputs #1](../final-design.md#departures-from-all-three-inputs)
- [final-design.md §Risks #2](../final-design.md#risks-top-5)
- [phase-arch-design.md §Gap analysis Gap 1](../phase-arch-design.md#gap-1-the-rubric-isolation-upgrade-path-is-not-annotated-on-the-audit-record)
- [phase-arch-design.md §Tradeoffs (consolidated) — last row](../phase-arch-design.md#tradeoffs-consolidated)
- [phase-arch-design.md §Non-goals #1](../phase-arch-design.md#non-goals)
- [critique.md §"Which disagreement matters most for *this* phase?"](../critique.md#which-disagreement-matters-most-for-this-phase) — the load-bearing observation this ADR responds to
- [Phase 5 ADR-0016 §Open Questions §5](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) — the deferred upgrade decision this ADR makes structurally detectable
- [ADR-0001](0001-rubric-execution-isolation-via-subprocess.md) — the isolation choice this ADR annotates
