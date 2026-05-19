# ADR-0012: `DockerfilePolicyGate` is hard-fail strict-AND across six invariants — no `--allow-policy-violations` flag

**Status:** Accepted
**Date:** 2026-05-19
**Tags:** strict-and · objective-signals · gate · honest-confidence
**Related:** [0013](0013-dockerfile-recipe-engine-dockerfile-parse.md), [0002](0002-shell-invocation-trace-probe-runs-in-microvm.md), [Phase 5 ADR-0003](../../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md), [production §2.3](../../../production/design.md)

## Context

Phase 5 establishes the strict-AND `TrustScorer` discipline: trust score is the conjunction over objective signals; a single failing gate fails the whole score; no thresholds, no overrides. Phase 7's distroless migration introduces a new gate class — pre-build static checks on the rendered Dockerfile.

The security-first lens design proposed `DockerfilePolicyGate` as a hard-fail strict-AND scanner over six invariants:

1. `USER` is set and is non-root.
2. No new `--cap-add` instructions beyond the Phase 6.5 baseline.
3. No new `--privileged` flag.
4. `ENTRYPOINT` is in exec form (not shell form).
5. `HEALTHCHECK` is not in shell form.
6. No new build-time secret mounts (`--mount=type=secret`).

There is no `--allow-policy-violations` override flag. Security framed the position as "non-negotiable." The critic concurred (the only critic objection was that strict-AND over an extensible set requires future gates to be at least permissive by default — a real concern but separable from the override question).

`final-design.md §Components §11` and `phase-arch-design.md §Component design §12` lock the no-override position. Operators get a failing-invariants list in the audit log; they fix the Dockerfile or the recipe; they do not flag-override.

## Options considered

- **Option A — Strict-AND six invariants, no override.** Security-first. **Pattern:** Strict-AND objective-signal gate ([production §2.3 Honest confidence](../../../production/design.md)).
- **Option B — Strict-AND with `--allow-policy-violations <invariant>` flag for narrow operator override per invariant.** **Pattern:** Override-with-audit. Rejected: defeats the honest-confidence commitment; introduces a per-invariant policy debate; opens the door to "I'll just override this one" drift.
- **Option C — Warning-only mode.** Soft fail; the trust score deducts but doesn't refuse. **Pattern:** Threshold gate. Rejected: silent regressions; not "objective signals."

## Decision

Adopt **Option A.** `DockerfilePolicyGate` runs over the rendered Dockerfile text + parsed AST (pure function, no microVM needed — `isolation_class="none"`) and emits `DockerfilePolicyGatePassed | DockerfilePolicyGateFailed(failing_invariants=[...])`. On any failing invariant, the strict-AND `TrustScorer` fails the workflow at the gate. No `--allow-policy-violations` flag. No per-invariant warning mode. No threshold tunable. Operators reading the audit log see the failing-invariants list and fix the Dockerfile or the recipe.

## Tradeoffs

| Gain | Cost |
|---|---|
| Honors [production §2.3 — Honest confidence](../../../production/design.md): the gate has only two states (pass / fail); operators cannot tune away a "just barely" failure | A legitimate edge case (e.g., a build genuinely requires a `--cap-add` for a niche workload) cannot ship via override; it must update the recipe or document the exception path |
| Six invariants are objective and statically checkable from the rendered Dockerfile — `DockerfilePolicyGate` is a pure function, runs in ≤ 10 ms, no microVM needed | The invariant list is hardcoded; adding a seventh invariant is a Phase-7-ADR amendment + fence amendment + new gate-test. Worth it; mirrors the gate-extension discipline of `@register_signal_kind` |
| Strict-AND fits the existing `TrustScorer` pattern (Phase 5 ADR-0003) — Phase 7 contributes a gate, not a parallel scoring mechanism | Strict-AND over an extensible signal set means future gates must be at least permissive by default; if a new gate ships off-by-default but enables in a later phase, the trust contract subtly shifts. Mitigated: every new gate goes through `@register_signal_kind` + an ADR for the on/off default |
| No override flag means no override-mode CLI surface, no per-invariant policy YAML, no debate at every fail — the policy lives in code | Operators may be frustrated by a hard fail; the project's stance is that this is the cost of objective signals. Rule 12 (Fail loud) applies |
| Failing-invariants list in the audit event (`DockerfilePolicyGateFailed(failing_invariants=[Invariant.USER_REMOVED, Invariant.CAP_ADD_INTRODUCED, ...])`) is machine-readable + operator-readable — HITL gets a concrete diagnostic | The `Invariant` enum is load-bearing; each invariant's name appears in audit logs; renames coordinate with Phase 8+ consumers |

## Pattern fit

Implements **Strict-AND objective-signal gate** ([production §2.3](../../../production/design.md); Phase 5 ADR-0003 — TrustScorer extension via `@register_signal_kind` registry): trust score is the conjunction; signals are objective; no per-signal threshold. Also instantiates **Sum type for outcomes** ([production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md)): the gate result is `Passed | Failed(invariants)` — exhaustive `match` handling. Rejects **Override-with-audit** (toolkit §Operability) on the grounds that strict-AND's value is the discipline of refusing the override; an audited override defeats the discipline.

## Consequences

- `DockerfilePolicyGate` lives at `plugins/distroless-migration--node--npm/recipes/dockerfile_policy_gate.py` (it gates the recipe output; co-located with the recipes that produce its input).
- Registered via Phase 5's existing `@register_signal_kind(name="dockerfile_policy", isolation_class="none")`. Additive only — no edit to the `TrustScorer` itself.
- The six invariants are encoded as a sum type `Invariant`:
  - `USER_NOT_SET_OR_ROOT`
  - `CAP_ADD_INTRODUCED`
  - `PRIVILEGED_INTRODUCED`
  - `ENTRYPOINT_NOT_EXEC_FORM`
  - `HEALTHCHECK_SHELL_FORM`
  - `BUILD_TIME_SECRET_MOUNT_INTRODUCED`
- Gate output is `Passed | Failed(failing_invariants: tuple[Invariant, ...])`. Strict-AND consumers handle both arms via `match`/`assert_never`.
- Audit log events: `DockerfilePolicyGatePassed(rendered_dockerfile_digest)` and `DockerfilePolicyGateFailed(rendered_dockerfile_digest, failing_invariants)`.
- The audit log + the `remediation-report.yaml` carry the failing-invariants list; HITL escalation gets a concrete diagnostic.
- No `--allow-policy-violations` flag is added to the CLI. The CLI's `--help` does not document any override path.
- Adding a seventh invariant requires a Phase-7-ADR amendment, a `tests/unit/recipes/test_dockerfile_policy_gate.py` test case, and the `Invariant` enum addition.
- The performance-first / best-practices designs did not propose this gate; security-first's framing is adopted in full.
- Edge case #8 in `phase-arch-design.md` is the policy-gate failure path; the test fixture set includes Dockerfiles that fail each invariant individually plus combinations.

## Reversibility

**Low.** Removing the gate or adding an override would require ratifying a policy change that contradicts §2.3 — a multi-phase coordination and an ADR amendment. Adding invariants is forward-additive (new `Invariant` enum value + test). Replacing the gate's implementation (e.g., switching from `dockerfile-parse` AST to a different parser) is internal — the gate's external contract (signal kind + sum-type outcome) is stable.

## Evidence / sources

- `../final-design.md §Goals` ("`DockerfilePolicyGate` ships as a Phase 5 gate-catalog contribution — security's hard-fail invariant scanner"), §Failure modes table (DockerfilePolicyGate failure path)
- `../phase-arch-design.md §Component design §12` (`DockerfilePolicyGate` + `DistrolessBuildGate` + `ShellInvocationDeltaGate`), §Edge cases #7, #8 (policy-gate failure paths)
- `../critique.md §Attacks on the best-practices design "Things this design missed"` ("No story for shell-call-rewriter recipe" — handled by gate composition)
- [Phase 5 ADR-0003 — TrustScorer extension via `SignalKind` registry](../../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md)
- [production §2.3 — Honest confidence](../../../production/design.md)
- [production ADR-0033 — Domain modeling discipline](../../../production/adrs/0033-domain-modeling-discipline.md)
