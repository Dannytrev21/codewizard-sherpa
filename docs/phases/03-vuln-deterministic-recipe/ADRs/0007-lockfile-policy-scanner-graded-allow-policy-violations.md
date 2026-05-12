# ADR-0007: `LockfilePolicyScanner` is a fact-emitting validator with a graded `--allow-policy-violations` escape valve; widening retry deferred to Phase 5

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** lockfile-policy · supply-chain · facts-not-judgments · synthesizer-departure · phase-5-handoff
**Related:** ADR-0001, ADR-0006, [Phase 2 ADR-0007](../../02-context-gather-layers-b-g/ADRs/0007-buildgraph-ignore-scripts-and-resolution-status.md), [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md)

## Context

Lockfiles can encode structural threats: `resolved:` URLs pointing at attacker hosts, missing `integrity:` fields, `overrides`/`resolutions` redirection, `publishConfig.registry` overrides, declared lifecycle scripts. The security-first lens introduced `LockfilePolicyScanner` to reject lockfiles with these patterns before any `npm install` runs — and made the violation **non-retryable** with "escalation to human review" as the only recourse (`design-security.md §"Goals" #7`).

The critic dismantled this in two blows (`critique.md §"Attacks on security-first" §"Concrete problems" #2`):

1. Legitimate packages introduce a `resolved:` host outside `registry.npmjs.org` — e.g., GitHub-tarball deps for forks. Refusing to proceed means a perfectly normal repo cannot be remediated.
2. Legitimate enterprises set `publishConfig.registry` to their private registry while still resolving from the public one for installs. Refusing this is a false-positive on a meaningful fraction of corporate repos.

The "escape valve" was conspicuously absent — there is no `--allow-registry` flag or per-repo override; just "human review," which is not a Phase 3 deliverable (`production ADR-0009`'s "humans always merge" applies at PR-merge time, not at policy gate time). The synth softens the response to **graded** behavior (`final-design.md §"Trust & safety goals"` #10): violations are still emitted as facts, but the orchestrator's response is graded by operator opt-in. The critic-recommended "retryable with widening" lands as Phase 5 work; Phase 3 ships the escape valve.

## Options considered

- **No lockfile policy at all [P, B].** Treats malicious lockfiles as someone else's problem. Phase 3 ships diffs that may install attacker-controlled code.
- **Hard non-retryable, no escape [S].** Refuses legitimate repos. Routes to nonexistent human reviewer.
- **Soft warning only.** Operators see the warning but the diff ships anyway. Defeats the policy.
- **Graded response: scanner emits facts, orchestrator response is configurable via `--allow-policy-violations`; Phase 5 wraps with widening retry [synth].** Phase 3 emits violations, exits with a structured event, and provides operator opt-in for known-legitimate cases. Phase 5 adds three-retry widening per critic recommendation.

## Decision

**`LockfilePolicyScanner` runs as a Stage 4 pre-transform validator (in `src/codegenie/transforms/validation/lockfile_policy.py`):**

- **Interface:** `scan(lockfile_path, *, allowed_registries) -> LockfileScanResult(violations: list[Violation])`.
- **Violation types** (typed, closed enum):
  - `RegistryRedirect` — `resolved:` URL points at host outside `allowed_registries`.
  - `MissingIntegrity` — entry lacks `integrity:` SRI hash.
  - `LifecycleScriptDeclared` — package declares preinstall/install/postinstall scripts in lockfile.
  - `PublishConfigOverride` — `publishConfig.registry` differs from `allowed_registries`.
  - `ResolutionsRedirect` — `overrides`/`resolutions` redirect to non-allowed host.
- **Pure Python.** Reads lockfile JSON with hard size cap (≤ 50 MB).
- **Facts, not judgments.** The scanner does not exit; the orchestrator interprets the result per `production/design.md §2.2`.

**Orchestrator response (Phase 3):**

- Default: any violation → `TransformOutput(confidence="low", warnings=[...])`, **exit 7** with audit event `escalation.policy_violation`.
- **`--allow-policy-violations <types>` flag** (comma-separated violation types, e.g., `RegistryRedirect,PublishConfigOverride`): operator can opt in to specific known-legitimate cases per run. Allowed types are recorded in the audit event; the violation is still emitted as a fact, but the orchestrator continues.
- Violations are **not** hard-non-retryable; they are graded.

**Phase 5 wraps:** the three-retry gate machinery widens the lockfile-policy decision: Retry 1 narrows the allowed-registries set, Retry 2 tries with an alternate fix path. Phase 3 ships the substrate; Phase 5 ships the policy.

**Allowed registries default:** `["registry.npmjs.org"]`. Configurable per repo via `.codegenie/config.yaml` (Phase 2 precedent).

## Tradeoffs

| Gain | Cost |
|---|---|
| Legitimate enterprise repos (GitHub-tarball deps, private `publishConfig.registry`) can be remediated with one explicit operator flag — first-run friction only | Operators must understand their repo's known-legitimate violations and opt in deliberately — false-positive triage is a real operational task |
| Violations are facts (`production/design.md §2.2`) — the scanner emits per-type evidence, not judgments — Phase 4–5 read the typed violations | The closed-enum violation type list is a contract; adding a new type (e.g., `WorkspaceProtocolOverride`) requires ADR amendment |
| Exit 7 + `escalation.policy_violation` audit event is operator-visible; `--allow-policy-violations` records the opt-in for forensic review | `--allow-policy-violations` can become a lazy escape — discipline required at code review of any per-repo configuration that pre-sets it |
| Phase 5's widening retry lands additively — three-retry policy reads the violation list and widens accordingly; no Phase 3 code changes | Phase 5 must decide what "widening" means for each violation type (narrowing allowed-registries doesn't widen anything; trying an alternate fix path is the actual widening — Phase 5 ADR territory) |
| Hard size cap (≤ 50 MB) bounds parser-DoS risk; same posture as Phase 2 parser caps | Repos with abnormally large lockfiles fail the scanner; flagged as a tunable in implementation; the cap is generous |
| Violation list is typed Pydantic models — Phase 4 reads `LockfileScanResult.violations` for diagnostic context (per ADR-0004's `diagnostics` dict pattern) | Two violation surfaces in Phase 3: the scanner's typed violations *and* the install/test validators' free-form errors; Phase 4 must merge them |

## Consequences

- `src/codegenie/transforms/validation/lockfile_policy.py` ships the scanner; `Violation` is a closed `Literal[...]`-tagged union.
- `transforms/coordinator.py` Stage 4 calls the scanner; on violations + no `--allow-policy-violations`, exits 7.
- CLI flag `--allow-policy-violations <comma-separated-types>` added; per-type allowlist recorded in audit event.
- Audit event `lockfile.scanned` carries `violations: list[Violation]` plus `allowed_overrides: list[str]`.
- Audit event `escalation.policy_violation` emitted on exit-7 paths.
- `tests/unit/test_lockfile_policy_scanner.py` ships ≥ 5 cases — one per violation type plus an empty-clean fixture.
- `tests/integration/test_remediate_lockfile_policy_violation_blocked.py` and `test_remediate_lockfile_policy_violation_allowed.py` (same fixture + `--allow-policy-violations RegistryRedirect`).
- Phase 5 wraps with widening retry; the production ADR-0014 three-retry envelope reads the violation list.
- Phase 4's planning coordinator reads typed violations for RAG/LLM context.
- Documentation: operator guide enumerates common legitimate cases (GitHub-tarball deps under a known org; corporate private registries) and the corresponding `--allow-policy-violations` invocations.

## Reversibility

**Low for the graded response shape; Medium for the violation type set.** Switching back to hard-non-retryable (removing `--allow-policy-violations`) is **operationally expensive** — repos that depended on the flag would silently start failing at Phase 3. Adding new violation types is mechanically additive but each addition must be coordinated with Phase 5's widening logic. Removing a violation type is medium-cost — repos that depended on the type firing would silently start shipping unsafe diffs. The "graded, fact-emitting" shape is the load-bearing piece; the specific type set evolves with the threat model.

## Evidence / sources

- `../final-design.md §"Goals" §"Trust & safety goals"` #10
- `../final-design.md §"Components" #6 "LockfilePolicyScanner (validation helper)"`
- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row "Lockfile policy"
- `../phase-arch-design.md §"Component design" #10 "LockfilePolicyScanner"`
- `../critique.md §"Attacks on security-first" §"Concrete problems" #2` — escape-valve absence
- `../critique.md §"Attacks on best-practices" §"Things this design missed"` — best-practices omitted lockfile policy entirely
- [Phase 2 ADR-0007](../../02-context-gather-layers-b-g/ADRs/0007-buildgraph-ignore-scripts-and-resolution-status.md) — facts-not-judgments precedent
- [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md) — human-review semantics at PR-merge, not policy gate
