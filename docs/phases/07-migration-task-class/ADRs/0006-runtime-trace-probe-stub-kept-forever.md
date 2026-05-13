# ADR-0006: Phase 2 `RuntimeTraceProbe` stub kept in place forever as a no-op

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** phase2-contract · probes · backward-compatibility · pure-preservation
**Related:** [ADR-0001](0001-six-named-additive-seams-and-adr-0028-amendment.md), [ADR-0002](0002-register-gate-probe-new-registry.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)

## Context

Phase 2 shipped `RuntimeTraceProbe` (C4) as a deliberate stub with `applies() = False`, intended as the "future hook" for runtime tracing while keeping the probe registry inventory complete. Phase 7's `ShellInvocationTraceProbe` is the concrete instantiation of what that hook was reserved for — runtime tracing of a target image's entrypoint.

The three lens designs handled this differently (`final-design.md §Component 2`):

- `[B]` proposed replacing the Phase 2 stub: rename `RuntimeTraceProbe` → `ShellInvocationTraceProbe`, change the file's contents. This would be a Phase 2 source-line edit on `src/codegenie/probes/runtime_trace.py`.
- `[S]` proposed flipping the stub's `applies()` to `True` and routing through new lifecycle infrastructure. Also a Phase 2 edit.
- The synthesizer's pick (`final-design.md §Component 2`): keep the stub byte-identical forever; `ShellInvocationTraceProbe` ships as a sibling new file with a distinct name and registers via the new `@register_gate_probe` registry (ADR-0002 in this phase).

The cost is one perpetually-dormant probe in the registry. The benefit is the Phase 2 source is byte-identical pre- and post-Phase 7, the production ADR-0007 commitment is honored verbatim, and the contract-surface snapshot for Phase 2 modules has a zero-line diff in the Phase 7 PR.

## Options considered

- **Replace Phase 2's `runtime_trace.py` (rename / rewrite).** One file edit; cleaner registry; violates production ADR-0007's byte-stability promise and forces the contract-surface canary (ADR-0009) to fail on a non-additive Phase 2 file diff.
- **Flip Phase 2's stub `applies()` to `True` and wire it to gate-time execution.** Phase 2 source edit; also forces gate-lifecycle logic into the Phase 2 coordinator (the edit ADR-0002 was specifically designed to avoid).
- **Keep Phase 2's stub byte-identical; ship `ShellInvocationTraceProbe` as a sibling new file under `@register_gate_probe`.** No Phase 2 edit; one perpetually-dormant probe. The synthesizer's pick.

## Decision

`src/codegenie/probes/runtime_trace.py` (Phase 2) is byte-identical pre- and post-Phase 7. Its `RuntimeTraceProbe` class retains `applies() = False` and stays in the `@register_probe` registry as a no-op. Phase 7's `ShellInvocationTraceProbe` ships at `src/codegenie/probes/shell_invocation_trace.py` as a new file, registers via `@register_gate_probe`, and has a distinct `name = "shell_invocation_trace"` (not "runtime_trace").

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 2 source is byte-identical — production ADR-0007 honored verbatim; contract-surface snapshot for Phase 2 has zero diff in the Phase 7 PR | One perpetually-dormant probe in the Phase 2 registry — `RuntimeTraceProbe` will never run, never produce a slice, never be invoked at gather time |
| `RuntimeTraceProbe.name = "runtime_trace"` is reserved namespace — if Phase 12+ ever wants a true gather-time runtime trace (e.g., for non-Docker workloads), the slot is available | Readers of the registry must understand why a no-op probe persists; a comment in `runtime_trace.py` and this ADR are the documentation |
| Distinct names (`runtime_trace` vs `shell_invocation_trace`) prevent any confusion in `prior_attempts` audit logs about which probe produced what; cross-task search by `name` returns disjoint results | Slight asymmetry: the Phase 2 stub was *named* for "runtime trace," but the concrete Phase 7 probe is named for a *specific* runtime observation (shell invocation). Future runtime traces (e.g., network endpoints) may want their own probes — same pattern applies |

## Consequences

- `src/codegenie/probes/runtime_trace.py` is on the contract-surface snapshot canary's "must be byte-identical" list (ADR-0009).
- A unit test asserts `RuntimeTraceProbe().applies(any_view) is False` — Phase 2's contract holds.
- Phase 7's `ShellInvocationTraceProbe` registers via `@register_gate_probe` (ADR-0002) — not `@register_probe`. The `all_probes()` registry contains `RuntimeTraceProbe` (no-op); `all_gate_probes()` contains `ShellInvocationTraceProbe`.
- Future runtime-trace work (Phase 12+ ELF-symbol scanning; non-Docker workload tracing) adds sibling files under the gate registry — `RuntimeTraceProbe` stays untouched.
- The asymmetry of "stub forever, real probe sibling" propagates as a documented pattern for any future Phase 2 stub that gets concretized in a later phase.

## Reversibility

**Low.** Removing the stub now requires editing Phase 2 source — exactly what this ADR exists to avoid. Renaming `ShellInvocationTraceProbe` to `RuntimeTraceProbe` would conflict with the existing stub class name. The asymmetry is intentional: this ADR documents a *preservation*, not an extension; reverting means amending production ADR-0007.

## Evidence / sources

- `../final-design.md §Component 2 "Tradeoffs accepted"` ("Phase 2's old 'stub `RuntimeTraceProbe` with `applies()=False`' stays in place forever as a no-op")
- `../final-design.md §"Departures #3 ADR-P7-005"` (pure preservation)
- `../phase-arch-design.md §Component 2 "Failure behavior"` (the Phase 2 stub stays in place forever as a no-op)
- `../phase-arch-design.md §Component 13 ADR-P7-005` (no edit; pure preservation)
- [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) — Probe contract preserved
