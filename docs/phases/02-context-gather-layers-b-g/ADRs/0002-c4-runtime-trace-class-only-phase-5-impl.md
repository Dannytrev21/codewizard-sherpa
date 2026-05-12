# ADR-0002: `RuntimeTraceProbe` (C4) ships class + sub-schema only in Phase 2; implementation deferred to Phase 5

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** scope · layer-c · phase-evolution · sandbox-dependency · contract-surface
**Related:** [production ADR-0019](../../../production/adrs/0019-sandbox-execution-stack.md), ADR-0003, ADR-0011, [roadmap.md Phase 2 + Phase 5 + Phase 7](../../../roadmap.md)

## Context

Layer C of `localv2.md §5.3` enumerates seven probes; Phase 2's roadmap exit criterion is "every probe layer runs against real repos." All three lens designs failed this criterion in different ways for the C-layer dynamic probes (SBOM, CVE, RuntimeTrace): performance shipped them but gated `C4 RuntimeTraceProbe` behind `applies_to_tasks` that don't exist yet (effective deferral disguised as completeness — `critique.md §P.4`); security shipped them with rootless Podman + `CAP_SYS_PTRACE` + an in-sandbox stub-service mesh (Phase 5 work disguised as Phase 2 — `critique.md §S.2`); best-practices deferred all three (direct roadmap scope violation — `critique.md §B.1` is the strongest single attack in the whole critique).

The three probes are not symmetrically deferable. `SyftSBOMProbe` and `GrypeCVEProbe` are unblocked by Phase 1's sandbox profile extended with `--network=scoped` for the base-image pull (`final-design.md §"Conflict-resolution table" D9`); Phase 3's vuln-remediation work hard-depends on their evidence. `RuntimeTraceProbe`, by contrast, requires `strace`/`dtruss`/eBPF inside a sandbox capable of running the produced container image — which is `--privileged`/`CAP_SYS_PTRACE`-shaped, exactly the question production ADR-0019 (sandbox execution stack) has explicitly left open. C4's first real consumer is Phase 7 (Chainguard distroless), which is after Phase 5 in the roadmap.

## Options considered

- **Ship C4 fully in Phase 2 [S/P].** Requires committing to a sandbox stack ADR-0019 has not resolved (rootless Podman with capability negotiation [S], or `applies_to_tasks` gate on Tier-3 evidence [P]). Either pre-commits Phase 5's architectural choice or ships dead code disguised as completeness.
- **Defer entirely [B].** No probe class, no sub-schema. Phase 5 lands the contract from scratch. Phase 3 / Phase 7 consumers have nothing to bind against in the interim; `IndexHealthProbe`'s runtime_trace domain has no shape to declare; the `applies()=False` honest-deferral signal cannot be encoded.
- **Ship class + sub-schema only; `applies()` returns `False` [synth].** The contract surface lands. B2 reports `runtime_trace: {status: not_applicable}` rather than `not_run`, which structurally separates "expected absence" from "unexpected absence" (closes critic shared blind spot #2). Phase 5 lands the implementation behind the same probe ABC. Phase 7 / Phase 3 consumers read a stable schema today.

## Decision

**Phase 2 ships `src/codegenie/probes/runtime_trace.py` with the probe class registered, `applies()` returning `False`, and `src/codegenie/schema/probes/runtime_trace.schema.json` declaring the slice as `{status: "deferred_to_phase_5", reason: "C4 requires sandbox stack ADR-0019 resolution"}`.**

- **The class exists.** Imported in `probes/__init__.py`; the probe ABC contract is honored; `requires`, `declared_inputs`, `applies_to_languages`, `applies_to_tasks` are all declared as the Phase 5 implementation will need them (kept narrow to avoid pre-committing).
- **`applies()` returns `False` unconditionally in Phase 2.** No invocation path; no subprocess; no sandbox tax.
- **The sub-schema is fully specified.** `additionalProperties: false` at its root; `status: deferred_to_phase_5` is the only valid emission shape in Phase 2; the schema documents the Phase 5 fields (syscall histogram, network attempts, mount accesses, env reads, child processes, exit code, wall-clock) so consumers can write against them today.
- **`IndexHealthProbe`'s runtime_trace domain.** B2 reports `runtime_trace: {status: not_applicable, reason: "C4 deferred to Phase 5"}` — never `not_run`, never `low`. The seeded-staleness signal is not drowned by C4 noise; that's the architectural property `final-design.md "Departures from all three inputs"` #5 calls out.
- **Phase 5 owns the implementation.** Named deliverable, documented as a hard dependency by this ADR. Phase 5's design must include: production ADR-0019 resolution (microVM choice), C4 syscall capture mechanism, runtime image lifecycle, the sub-schema's `status` field flipping from `deferred_to_phase_5` to `observed | failed | timeout`.
- **Phase 7 (distroless) is the first real consumer** and is downstream of Phase 5. `ShellUsageProbe`, `CertificateProbe`, `EntrypointProbe` in Phase 2 emit `runtime_trace_pending: true` in their own slices where the static evidence is incomplete — consumers know the dynamic confirmation is owed by Phase 5.

## Tradeoffs

| Gain | Cost |
|---|---|
| Contract surface lands; Phase 3 / 5 / 7 consumers bind against a stable schema today | Phase 2's roadmap exit criterion "every probe layer runs against real repos" is partially met by *departure* — surfaced openly in `final-design.md` "Exit-criteria checklist" |
| Phase 5 inherits a class + schema, not a green-field design — sandbox-stack ADR-0019 only needs to resolve the runtime, not the contract | The class file is "dead" for the duration of Phase 2 → Phase 5; a future reader sees `applies()=False` and must follow the ADR trail to learn why |
| B2's runtime_trace domain emits `not_applicable` — structurally distinguishable from "missing because of bug" | A probe whose `applies()` returns `False` is a code-smell shape that the registry CI lint must explicitly allow; tested by `tests/unit/probes/test_runtime_trace_deferred.py` |
| Phase 7's distroless consumers can already read the slice shape from the published sub-schema — no schema breaks when Phase 5 lands | The sub-schema may be revised in Phase 5 if implementation surfaces fields not anticipated; `additionalProperties: false` is the structural defense, the lockstep with implementation is the operational defense |
| Phase 5's exit criterion ("the three-retry loop works end-to-end") and Phase 5's hard dependency on ADR-0019 are aligned with C4 landing | Phase 5 slipping (e.g., ADR-0019 resolves toward Firecracker but C4 implementation is deprioritized) leaves Phase 7 without runtime-trace evidence — Risk #5 in `final-design.md` |
| The `runtime_trace_pending` slice in C5/C6/C7 is a first-class signal — the Planner reads it as "static evidence; dynamic confirmation owed by Phase 5" | One extra field per static C-layer probe; documented per `localv2.md §5.3` |

## Consequences

- `src/codegenie/probes/runtime_trace.py` lands as a tiny file: probe class, `applies()` returning `False`, structured slice emission of `{status: "deferred_to_phase_5"}` if ever called (defense in depth).
- `src/codegenie/schema/probes/runtime_trace.schema.json` lands with `status` enum `["deferred_to_phase_5", "observed", "failed", "timeout"]` and the Phase 5 field set documented but not required.
- `IndexHealthProbe`'s per-domain table includes `runtime_trace` with `status: "not_applicable"` in Phase 2; the synth's "expected absence" signal-to-noise framing holds.
- `ShellUsageProbe`, `CertificateProbe`, `EntrypointProbe` declare `runtime_trace_pending: true` in their sub-schemas in cases where static evidence is incomplete.
- Phase 5's design must explicitly own:
  - ADR-0019 resolution (`microVM-choice`).
  - `runtime_trace.py` implementation under the same probe class.
  - Sub-schema `status` field flipping from `deferred_to_phase_5` to one of the observed states.
  - B2's `runtime_trace` domain promoting from `not_applicable` to active.
- The `tests/integration/test_phase2_real_oss.py` test asserts `runtime_trace` slice present with `status: deferred_to_phase_5`; no probe invocation.
- The `tests/unit/probes/test_runtime_trace_deferred.py` test asserts `applies()` returns `False` for every fixture; the registry imports the class; the schema validates.

## Reversibility

**Medium.** Promoting C4 from class-only to fully-implemented in Phase 5 is mechanically additive: flip `applies()`, implement `run()`, swap the sub-schema's default `status` enum, flip B2's runtime_trace domain. Reverting the *deferral* (i.e., trying to ship C4 fully in Phase 2 after this ADR lands) requires resolving ADR-0019 inside Phase 2's scope — which contradicts both Phase 2 and Phase 5's commitments and would be Phase-replanning, not ADR-amending. The class-only artifact is cheap to keep; the deferral is the load-bearing piece.

## Evidence / sources

- `../final-design.md "Components" §4.4 RuntimeTraceProbe (C4) — class only`
- `../final-design.md "Conflict-resolution table" D8 and D10` — Layer C scope split
- `../final-design.md "Departures from all three inputs" #1, #5` — synth call-outs
- `../final-design.md "Risks" #5` — the Phase 5 hard-dependency risk
- `../phase-arch-design.md "Goals" #1, "Non-goals" #1` — explicit scope statement
- `../critique.md "Cross-design observations"` Layer C dynamic-probes table — the framing
- `../critique.md "Attacks on the best-practices design"` #1 — the scope violation
- `../critique.md "Attacks on the performance-first design"` #4 — the `applies_to_tasks` deferral attack
- [production ADR-0019](../../../production/adrs/0019-sandbox-execution-stack.md) — the unresolved sandbox-stack question
- [`roadmap.md` Phase 2, Phase 5, Phase 7](../../../roadmap.md) — the dependency graph
