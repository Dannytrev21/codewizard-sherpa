# ADR-0002: `@register_gate_probe` — a new registry module, not an `applies_to_lifecycle` field on the `Probe` ABC

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** probes · phase2-contract · gate-lifecycle · new-file-only
**Related:** [ADR-0001](0001-six-named-additive-seams-and-adr-0028-amendment.md), [ADR-0006](0006-runtime-trace-probe-stub-kept-forever.md), [ADR-0013](0013-shell-trace-runs-gate-time-in-phase5-chokepoint.md), [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)

## Context

`ShellInvocationTraceProbe` must observe whether the **candidate (post-recipe) image's** entrypoint invokes a shell at runtime. It is structurally a *gate-time* probe — it runs inside Phase 5's `run_in_sandbox` chokepoint against the rebuilt image — but it is also written as a `Probe` ABC (Phase 2's `name`, `applies_to_tasks`, `declared_inputs`, `run(view)` shape) because the Phase 2 surface is the right vocabulary.

The three lenses split badly on how to encode the lifecycle distinction (`critique.md §security.1`, `§security.2`, `§performance.1`):

- `[S]` proposed an `applies_to_lifecycle: ClassVar = ["gather"]` default on `src/codegenie/probes/base.py`. The critic landed: adding a class attribute with a default to the `Probe` ABC is a Phase 2 edit; Phase 2's `consumes_peer_outputs` precedent was ADR-gated *at the time Phase 2 shipped* and cannot be replayed against a frozen ABC. Production ADR-0007 forbids it.
- `[S]` further required Phase 2's coordinator to refuse `lifecycle=["gate"]` probes at gather time — a second edit, this time to `coordinator.py`.
- `[P]` ran the probe at gather time. The critic landed: executing the target's entrypoint at gather time violates Phase 2's threat model (production ADR-0007 + production design §2.1).

The synthesizer needs a way to register `ShellInvocationTraceProbe` such that (a) the Phase 2 `Probe` ABC is byte-identical, (b) the Phase 2 coordinator is byte-identical and never dispatches a gate probe at gather time, (c) Phase 5's `GateRunner` can still discover and invoke the probe at gate time (`phase-arch-design.md §Component 3`).

## Options considered

- **`applies_to_lifecycle` field on the `Probe` ABC + coordinator branch (`[S]`).** Two Phase 0–6 edits; the security design's own BLAKE3-of-source freeze CI test would fail on it (`critique.md §security.1`).
- **Run at gather time (`[P]`).** Violates Phase 2's threat model; no.
- **New registry module `src/codegenie/probes/gate_registry.py` with `@register_gate_probe`.** Pure file addition; ~30 LOC; the `Probe` ABC and Phase 2 coordinator are byte-identical; gate-time consumers (Phase 5's `GateRunner` and signal collectors) read `all_gate_probes()` directly. The synthesizer's original.

## Decision

Add a new module `src/codegenie/probes/gate_registry.py` exporting `register_gate_probe(cls) -> cls` and `all_gate_probes() -> Sequence[type[Probe]]`. `ShellInvocationTraceProbe` decorates with `@register_gate_probe` (not `@register_probe`). The Phase 2 coordinator never imports this module. Phase 5's `GateRunner` (or its `signals/` collectors) is the only consumer of `all_gate_probes()`.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 2 `Probe` ABC source byte is identical pre- and post-Phase 7 — production ADR-0007 honored verbatim | A second registry exists alongside `@register_probe` — readers must learn the distinction (gather vs gate) and remember which registry consumers read |
| Phase 2 coordinator does not learn the word "lifecycle" — no `if applies_to_lifecycle == "gate": skip` branch | The Phase 2 `RuntimeTraceProbe` stub stays in place forever as a no-op sibling (ADR-0006 in this phase) — one perpetually-dormant probe in the registry |
| The lifecycle distinction is encoded *by registration site*, not by ABC field — adding more lifecycle classes later (e.g., `discovery-time` probes for Phase 10) follows the same pattern: new registry, new decorator | Two registries means two `all_*_probes()` accessors; any future tooling that wants "every probe ever" needs to merge them |
| ~30 LOC of pure addition; no import from `codegenie.coordinator`; the contract-surface snapshot for `Probe` ABC + Phase 2 registry is unchanged | Phase 2's open `@register_probe` decorator is now *one of two* — the implicit "the probe registry" mental model loses its singleton |

## Consequences

- `src/codegenie/probes/gate_registry.py` is a new file with the canonical decorator + accessor shape from `phase-arch-design.md §Component 3`.
- Phase 5's `GateRunner.run_one` (or its `sandbox/signals/` collectors) reads `all_gate_probes()` and dispatches gate probes that match the active gate's task type.
- Unit test `tests/unit/probes/test_gate_registry.py` asserts: (a) `@register_gate_probe` appends the class to a module-level list; (b) double-registration is allowed but a uniqueness test on `name` flags it; (c) the decorator does not raise.
- The contract-surface snapshot (ADR-0009) captures the new decorator's signature under `registries`; future phases adding a third lifecycle (e.g., discovery) follow the same pattern with a new ADR.
- Phase 8's supervisor (when it lands) does not need to know about the gate registry; it dispatches `task_type` to `build_*_loop()` factories and lets each subgraph wire its own gate probes.
- Phase 9's Temporal worker inherits the same pattern — the gate registry is module-level, registered at import time, identical inside a worker process as in the CLI.

## Reversibility

**High.** Removing the gate registry and merging into `@register_probe` is a localized refactor (move the class, change the decorator, update the one Phase 5 consumer). The Phase 2 `Probe` ABC stays untouched in either direction; the registry split is a presentation choice, not a contract change. The only durable cost of reversal is the Phase 2 coordinator would then need the lifecycle branch this ADR was designed to avoid.

## Evidence / sources

- `../final-design.md §Conflict-resolution row 1` (lifecycle classification)
- `../final-design.md §Conflict-resolution row 2` (ABC additive field rejected)
- `../final-design.md §Conflict-resolution row 3` (coordinator branch rejected)
- `../final-design.md §"Departures from all three inputs" #1` (synthesis-original)
- `../phase-arch-design.md §Component 3` (gate_registry.py interface)
- `../critique.md §security.1` (the `applies_to_lifecycle` edit)
- `../critique.md §security.2` (the coordinator edit)
- `../critique.md §performance.1` (gather-time threat-model violation)
- [production ADR-0007](../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md) — Probe contract preserved unchanged
