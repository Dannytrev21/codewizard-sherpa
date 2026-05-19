# ADR-0003: Phase 5 `SandboxClient.spawn(...)` gains `role: SandboxRole` (additive enum)

**Status:** Accepted
**Date:** 2026-05-19
**Tags:** open-closed · phase-5-amendment · enum · sandbox-role
**Related:** [0002](0002-shell-invocation-trace-probe-runs-in-microvm.md), [0009](0009-phase-7-byte-edit-allowlist-fence.md), [Phase 5 ADR-0001](../../05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md), [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md)

## Context

Phase 5's `SandboxClient.spawn(...)` was designed for gates — a single `gate-control` privileged process spawning microVMs for `Gate` ABC subclasses. Phase 7's [`ShellInvocationTraceProbe`](0002-shell-invocation-trace-probe-runs-in-microvm.md) is the first **probe** that needs the same microVM isolation. The security-first lens design proposed standing up a parallel `probe-control` process — a second long-running privileged process with its own microVM CP creds, HMAC key, TLS endpoint, and supervision tree.

The critic landed Sec-5 and roadmap-3 hard in `critique.md`: "New caller" understates a major topology change; doubling the privileged-process count doubles the credential boundary count, the operational surface, and the supervision tree. The honest answer is to **parametrize the existing `SandboxClient.spawn(...)` with a role enum** and reuse the existing process.

`final-design.md §Lens summary §2` and §Synthesis ledger departure #3 take this position: one additive enum value, one additive parameter on an existing method — minimum Phase-5 amendment surface.

## Options considered

- **Option A — Parallel `probe-control` process.** Security-first position. **Pattern:** Process-per-role. Doubles supervision tree, credential boundary count, and operational surface for a single new caller.
- **Option B — Overload `Role.GATE` semantically; let `ShellInvocationTraceProbe` call `spawn(role=Role.GATE, ...)`.** Cheapest in code; **rejected** because audit logs and per-role policy become semantically wrong (a probe is not a gate; the trust class differs).
- **Option C — Add `role: SandboxRole` parameter to Phase 5's existing `SandboxClient.spawn(...)`, with `SandboxRole = Role.GATE | Role.PROBE` sum-type enum and `Role.GATE` as the default to preserve all existing call sites.** **Pattern:** Open/Closed via additive enum value; Strategy via data.

## Decision

Adopt **Option C.** Phase 5's `SandboxClient.spawn(...)` gains exactly one new parameter — `role: SandboxRole = Role.GATE` — and one new value in the `SandboxRole` enum: `Role.PROBE`. The same Firecracker / gVisor / Lima stack is reused; `gate-control` remains the single privileged process. `Role.PROBE` is routed to identical microVM topology as `Role.GATE` but is tagged distinctly in audit logs and is the routing signal Phase 8's Planner may later use to schedule probes on cheaper runners. This is the **one explicit Phase 5 amendment Phase 7 makes**.

## Tradeoffs

| Gain | Cost |
|---|---|
| One parameter, one enum value — the smallest possible Phase-5 amendment surface; future task classes (`Role.RECIPE`, `Role.AUDIT`) add their roles by the same additive shape | Phase 5 must ratify the amendment; if Phase 5 rejects, Phase 7 falls back to calling `spawn(role=Role.GATE)` with the audit-clarity cost documented in `final-design.md §Risks #1` |
| The existing `gate-control` supervision tree, HMAC key, TLS endpoint, and CP credential are reused verbatim — credential boundary count stays at one | The audit-log `role` field is the only Phase-7-visible per-role distinction in Phase 7; richer per-role policy (e.g., probe runs on cheaper runners) is deferred to Phase 8's planner that consumes the role |
| `SandboxRole` is a sum-type enum per ADR-0033 — exhaustive `match` handling at every consumer; adding a new role family is an ADR-worthy event | Default value (`Role.GATE`) is load-bearing for backward compatibility; if a future caller forgets to pass a role, it silently lands in `Role.GATE` rather than failing. Mitigated by the explicit-keyword-arg-only convention at the call site |
| One pattern for all future task classes — the next migration task class that introduces a probe with side effects doesn't argue about process topology | The enum value names ("GATE", "PROBE", ...) become a small public vocabulary Phase 5 owns; any rename is a coordinated multi-phase change |

## Pattern fit

Implements **Open/Closed via additive enum value** (toolkit §Composition / coupling, §Open/Closed precedent): the existing `SandboxClient` is open for extension (new role values) but closed for modification (no method signature changes beyond the additive default-valued parameter). Also instantiates **Strategy via data** (toolkit §Behavioral) — the role drives audit-tag selection and (future) scheduling policy via a sum-type discriminator, not via a parallel class hierarchy. Newtype + sum-type discipline per [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md).

## Consequences

- `src/codegenie/sandbox/client.py` gains the `role: SandboxRole = Role.GATE` parameter on `spawn(...)`. The change is exactly two lines (one signature, one default).
- `src/codegenie/sandbox/__init__.py` gains `Role` to its `__all__`. Phase 7 fence allowlist ([0009](0009-phase-7-byte-edit-allowlist-fence.md)) authorizes these two edits and only these.
- The Phase 5 audit-log event format gains a `role` field (additive; existing fields untouched). Pydantic `extra="forbid"` continues to hold.
- Every existing `SandboxClient.spawn(...)` call site in Phase 5 keeps working unchanged (default `Role.GATE`).
- `ShellInvocationTraceProbe` is the sole Phase 7 caller of `spawn(role=Role.PROBE)`.
- Integration test `tests/integration/test_sandbox_client_role_probe.py` asserts: `spawn(role=Role.PROBE)` boots a microVM with identical topology to `spawn(role=Role.GATE)` plus the audit-log role-tag distinction.
- Risk #1 in `final-design.md` documents the **fallback** if Phase 5 rejects the amendment: the probe calls `spawn(role=Role.GATE)` (semantically wrong, operationally identical) and pays an audit-clarity cost. The fallback is logged in the attempt log if invoked.
- Future task classes' roles (`Role.RECIPE`, `Role.AUDIT`, etc.) add via the same additive-enum-value shape — no further Phase-5 method-signature changes.

## Reversibility

**High.** The amendment is one parameter with a default value and one enum value. If Phase 5 wants to restructure roles (e.g., split `Role.PROBE` into `Role.PROBE_LIGHT` / `Role.PROBE_HEAVY`), the change is additive (add the new values, deprecate `Role.PROBE` as an alias). If Phase 5 outright rejects the amendment, the fallback is documented and Phase 7 still ships.

## Evidence / sources

- `../final-design.md §Lens summary §2`, §Synthesis ledger row 8 + departure #3, §Risks #1
- `../phase-arch-design.md §Component design §9` (`ShellInvocationTraceProbe`), §Tradeoffs (consolidated) row "Phase 5 `SandboxClient.spawn(...)` gains one `role: SandboxRole` parameter"
- `../critique.md §Attacks on the security-first design §5` (parallel `probe-control` apparatus), §Roadmap-level critiques §3 (Phase 5 capability that may not exist)
- [Phase 5 ADR-0001 — two-chokepoint sandbox seam](../../05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md)
- [production ADR-0033 — Domain modeling discipline](../../../production/adrs/0033-domain-modeling-discipline.md)
