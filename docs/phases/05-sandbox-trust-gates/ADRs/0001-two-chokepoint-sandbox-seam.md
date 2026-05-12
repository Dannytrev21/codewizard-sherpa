# ADR-0001: Two-chokepoint sandbox seam — `run_in_sandbox` and `SandboxClient` coexist

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** architecture · sandbox · gates · phase-boundary
**Related:** [ADR-0002](0002-additive-prior-attempts-kwarg.md), [ADR-0006](0006-protocol-vs-abc-convention.md), [production ADR-0012](../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md)

## Context

Phase 2 already shipped a sandbox chokepoint, `run_in_sandbox`, used by deterministic *probes* during context gathering. Phase 5 needs a sandbox seam for *gate execution* — running LLM-influenced patches under build/install/test/trace/policy/cve_delta gates, with a three-retry loop and a structured `SandboxRun` artifact downstream phases consume. The two callsites differ materially: probes are short, read-only, and produce evidence consumed only by the gatherer; gates execute mutable workloads, produce strict-AND verdicts, and feed Phase 4 re-planning on failure. Folding both into one chokepoint would force a least-common-denominator API. See [phase-arch-design.md §Component design](../phase-arch-design.md#component-design) and [final-design.md §Roadmap coherence check](../final-design.md#roadmap-coherence-check) (Phase 2 row).

## Options considered

- **Single chokepoint** — Generalize `run_in_sandbox` to serve both probes and gates. Adds optional kwargs (`copy_in`, `enable_trace`, `egress_allowlist`, `time_budget_seconds`, `copy_out`) to the probe API. Simpler call site count, but conflates two very different lifecycles in one signature.
- **Two chokepoints, shared backend** — Keep `run_in_sandbox` as-is for Phase 2 probes; introduce `SandboxClient` Protocol for Phase 5 gates. Both eventually call the same Docker/Firecracker primitives, but at distinct API boundaries with distinct invariants.
- **Replace `run_in_sandbox`** — Migrate Phase 2 probes onto `SandboxClient`. Edits an already-shipped phase to suit Phase 5; violates extension-by-addition.

## Decision

Two chokepoints coexist: `run_in_sandbox` remains the Phase 2 probe seam; `SandboxClient` is the new Phase 5 gate seam. Stage 6 Validate's callsite swaps from a direct `validation.*` call to `GateRunner.run`, which is the only consumer of `SandboxClient` in this phase.

## Tradeoffs

| Gain | Cost |
|---|---|
| Each chokepoint has tight, opinionated invariants matching its callsite (probe: no copy-out, no trace, ≤30 s; gate: copy-out, optional trace, ≤600 s) | Two sandbox seams to maintain instead of one |
| Phase 2 ships unchanged — extension by addition honored | Two implementations may drift unless a shared backend layer is enforced (followups: `sandbox/did/` is shared) |
| `SandboxClient` is a Protocol matching gate-execution shape; probes' `run_in_sandbox` keeps its function-call ergonomics | Readers must learn two names and when each applies |
| Static CI test `tests/schema/test_stage6_chokepoint.py` enforces "only `GateRunner` calls `validation.*`" — no leaks | Adding a *new* gate-execution callsite is gated by an ADR amendment |

## Consequences

- `src/codegenie/sandbox/contract.py` defines `SandboxClient`, `SandboxSpec`, `SandboxRun`; nothing under `src/codegenie/gather/` imports them.
- The orchestrator (Phase 3) is the single edit site: Stage 6's previous direct call becomes `GateRunner.run(ctx)`.
- Phase 7 distroless adds `BaseImageSignal` collectors that consume `SandboxRun` — no edits to `run_in_sandbox`.
- Phase 6 lifts `SandboxClient` unchanged into its LangGraph node side-effect; `run_in_sandbox` stays on its existing probe execution path.
- New invariant: any module under `sandbox/` or `gates/` that imports `subprocess` must live in one of the three allowlisted chokepoint files (`did/build.py`, `did/network_policy.py`, `firecracker/client.py`); AST-walked by `tests/schema/test_no_subprocess_outside_build_chokepoint.py`.
- Operator-facing: `codegenie sandbox health` covers gate-side health; existing `codegenie gather` health surface covers probe-side.

## Reversibility

**Medium.** If the two chokepoints diverge unhelpfully, a future phase can merge them by promoting `SandboxClient` to subsume `run_in_sandbox`'s callers (Phase 2 probes become `SandboxClient` consumers). The reverse — collapsing now and re-splitting later — would require touching every probe call site. The current split is the cheaper-to-reverse direction.

## Evidence / sources

- [final-design.md §Roadmap coherence check](../final-design.md#roadmap-coherence-check) — Phase 2 row, "two-chokepoint shape"
- [phase-arch-design.md §Component design — `SandboxClient`](../phase-arch-design.md#sandboxclient-protocol)
- [phase-arch-design.md §Testing strategy — `tests/schema/test_stage6_chokepoint.py`](../phase-arch-design.md#testing-strategy)
- [production ADR-0012](../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md) — sandbox-for-gates production target this composes with
