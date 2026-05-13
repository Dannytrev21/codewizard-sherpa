# ADR-0013: `ShellInvocationTraceProbe` runs at gate time inside Phase 5's sandbox chokepoint — 30 s strace budget

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** probes · gate-time · sandbox · strace · threat-model
**Related:** [ADR-0002](0002-register-gate-probe-new-registry.md), [ADR-0006](0006-runtime-trace-probe-stub-kept-forever.md), [production ADR-0012](../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md), [production ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md)

## Context

`ShellInvocationTraceProbe` empirically validates the distroless target by observing whether the candidate (post-recipe) image's entrypoint invokes a shell at runtime. Two decisions are load-bearing and intertwined: **where does the probe execute** (gather time on the host, gather time in a sandbox, gate time in the Phase 5 chokepoint) and **what is the strace wall-clock budget** (10 s, 30 s, longer).

The lens designs disagreed (`final-design.md §Conflict-resolution rows 1 and 14`):

- `[P]` ran it at gather time with a 10 s budget. The critic landed (`§performance.1`): executing the target's `docker buildx build --load` plus `docker run --rm` of an attacker-influenceable Dockerfile at gather time violates Phase 2's threat model (no target-binary execution at gather time). Phase 2's `RuntimeTraceProbe` was deferred precisely for this reason.
- `[S]` ran it at gate time with a 30 s budget. The synthesizer accepts the lifecycle and the budget, separately resolving the registry seam via the new `@register_gate_probe` (ADR-0002 in this phase).

The 10 s budget was attacked separately (`§performance.risk.1`): produces too many `confidence=medium` cache entries on legitimate slow-starting entrypoints (Node app initialization, JVM warm-up). Each `confidence=medium` cascades into strict-AND failure → Phase 5 three-retry → LLM-fallback "fixing" a non-bug → human escalation. The 30 s budget — `[S]`'s pick — closes the false-positive cascade.

## Options considered

- **Gather-time, 10 s budget (`[P]`).** Phase 2 threat-model violation; too tight; rejected.
- **Gather-time, 30 s budget.** Same threat-model violation, just slower; rejected.
- **Gate-time in Phase 5 chokepoint, 10 s budget (`[P]`'s budget at `[S]`'s lifecycle).** Correct lifecycle; too tight a budget; cascades into false-positive HITL escalations.
- **Gate-time in Phase 5 chokepoint, 30 s budget (synthesizer's pick).** Correct lifecycle; honest budget; closes false-positive cascade. ~20 s extra worst-case wall-clock per workflow accepted as the cost of fewer cascaded HITLs (production ADR-0014 three-retry cap still applies).

## Decision

`ShellInvocationTraceProbe` runs **at gate time only**, **inside Phase 5's existing `run_in_sandbox` chokepoint**. The strace budget is **30 s** (`tools/digests.yaml#gate.shell_trace.budget_s`, configurable). On budget exhaust: `confidence=medium`, `entrypoint_steady=False`, `runtime_shell_count=None`. The strict-AND collector treats `confidence != "high" OR runtime_shell_count != 0` as `passed=False, retryable=True`. Phase 5's three-retry semantics + HITL on exhaustion apply unchanged. **No new sandbox profile, no rootfs digest bump** (closes `[S]`'s +350–600 MB rootfs proposal).

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 2 threat model preserved verbatim — no target-binary execution at gather time; the gather pipeline stays deterministic and side-effect-free | The probe's *cold* path is a `docker buildx build` plus a `docker run` plus 30 s of strace — wall-clock 25–60 s on Linux DinD, 10–25 s on macOS DiD; absorbed by Goal G3 (recipe hot path ≤ 240 s) but real |
| Phase 5 chokepoint reused as-is — no new microVM profile, no rootfs bump, no new daemon, no new socket | Strace must run inside the sandbox; on macOS DiD, the sandbox kernel is the Docker Desktop VM's Linux kernel — strace runs *inside the container* (Gap 4 in `phase-arch-design.md` specifies sibling sidecar pattern: `docker --pid=container:<candidate>` with strace in a pinned Alpine sidecar) |
| 30 s budget closes the false-positive cascade — slow-starting entrypoints (Node init, JVM warm-up) reach steady-state under budget; legitimate migrations don't cascade into LLM-fallback spend | ~20 s extra worst-case wall-clock per workflow compared to `[P]`'s 10 s — accepted because each `confidence=medium` cascade would have cost a full LLM-fallback + a retry-3 escalation, dramatically worse |
| Budget is configurable (`tools/digests.yaml#gate.shell_trace.budget_s`) — Phase 13's perf canary tracks the empirical distribution; if p95 entrypoint-steady-state exceeds 24 s, bump via ADR amendment | Configuration surface area (one tunable) — operators may tune it down for time-sensitive workflows and re-introduce the cascade; documented in Risk #3 (`final-design.md`) |
| Strace runs `--network=none` in the workload — no Chainguard credential exposure inside the sandbox; the gate's only credential surface is Phase 5's egress allowlist (ADR-0003) for the *daemon's* pulls | Network-touching entrypoints (e.g., dial-home services) reach steady-state by failing — observed empirically; the trace records `network_endpoints_touched=[]` (always empty given `--network=none`); the field is kept for forward compatibility |

## Consequences

- `src/codegenie/probes/shell_invocation_trace.py` is a new file registered via `@register_gate_probe` (ADR-0002).
- `tools/strace.py` is a new Pydantic-wrapped subprocess wrapper; pinned in `tools/digests.yaml#sandbox.strace`.
- `tools/digests.yaml#gate.shell_trace.budget_s` defaults to 30; configurable.
- The strace sidecar pattern (`phase-arch-design.md §Gap 4`) uses `docker --pid=container:<candidate>` with strace pinned in `tools/digests.yaml#sandbox.strace_sidecar` (an Alpine image); avoids the ENTRYPOINT-wrapper anti-pattern (which would alter PID 1 / signal handling on the candidate).
- The probe's strict-AND collector emits `ShellInvocationTraceSignal(passed, retryable, details)` — `retryable=True` on budget exhaust, `retryable=False` on observed shell.
- Phase 5's `StrictAndGate.evaluate` consumes the signal alongside `shell_presence` (the static check) for the binary verdict.
- `tests/integration/test_migrate_shell_required_hitl.py` is the regression fixture — a Node service whose `/admin` route conditionally shells out; the probe flags it; gate fails; `await_human` interrupt; mocked `HumanDecision(action="abort")` aborts cleanly.
- `tests/perf/test_strace_budget_distribution.py` records the empirical wall-clock distribution; fires warning if p95 > 24 s (Risk #3 in `final-design.md`).
- Phase 13's calibration window (production ADR-0015) reads this data and decides whether the default needs adjustment.

## Reversibility

**Medium.** Tightening the budget to 10 s is one-line in `tools/digests.yaml` — but re-introduces the false-positive cascade. Moving the probe to gather time is a Phase 2 threat-model rollback — not feasible without amending production ADR-0007 and the gather-pipeline determinism commitment. The asymmetry favors keeping the current design; the budget tunable is the documented escape valve for genuinely-different runtime profiles.

## Evidence / sources

- `../final-design.md §Conflict-resolution row 1` (gate-time lifecycle)
- `../final-design.md §Conflict-resolution row 14` (30 s budget)
- `../final-design.md §Component 2` (full design)
- `../phase-arch-design.md §Component 2` (gate-time strace internals)
- `../phase-arch-design.md §Gap 4` (sidecar pattern)
- `../critique.md §performance.1` (gather-time threat-model violation)
- `../critique.md §performance.risk.1` (10 s budget too tight)
- [production ADR-0012](../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md) — microVM sandbox for trust gates
- [production ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md) — three-retry default
