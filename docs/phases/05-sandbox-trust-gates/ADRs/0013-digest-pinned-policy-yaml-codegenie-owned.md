# ADR-0013: Sandbox policy YAML is codegenie-owned and digest-pinned; not repo-resident

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** policy · supply-chain · adversarial
**Related:** [ADR-0012](0012-static-env-allowlist-no-credentials-in-sandbox.md), [production ADR-0021](../../../production/adrs/0021-policy-engine-build-vs-adopt.md)

## Context

The `collect_policy_signal` collector evaluates patch + sandbox-run state against a YAML policy (lockfile rules, runtime-trace rules, test-inventory rules). One input design left the policy source unspecified; the critic noted that if the LLM-produced patch can edit the repo's `.codegenie/policy.yaml`, the gate can be silently neutered. Security-first proposed pinning the policy in the rootfs by digest — closer. The synthesis: explicit constant path `tools/policy/sandbox-policy.yaml`, digest in `tools/digests.yaml`, CI-asserted at startup. The repo's own `.codegenie/policy.yaml` (if present) is ignored entirely by Phase 5's policy collector. See [phase-arch-design.md §Edge case 10](../phase-arch-design.md#edge-cases) and [final-design.md §Synthesis ledger — Policy source row](../final-design.md#synthesis-ledger).

## Options considered

- **Repo-resident policy** — Each target repo carries its own `.codegenie/policy.yaml`. Maximum flexibility; LLM-influenced edits to the file silently relax the gate. Catastrophic.
- **Pinned in rootfs (security-first)** — Bake the policy into the sandbox rootfs at a known path. Closer; binds policy lifecycle to rootfs rebuild cadence; cross-backend variation (DinD vs Firecracker rootfs) creates two sources.
- **Codegenie-owned, digest-pinned constant** — `tools/policy/sandbox-policy.yaml` is the source of truth, bytes pinned in `tools/digests.yaml#sandbox.policy_yaml`. Startup integrity check refuses to run if hash mismatches. The collector reads the bytes from the codegenie process directory, not from anything under the target repo.

## Decision

The policy YAML is owned by codegenie at `tools/policy/sandbox-policy.yaml`, content-addressed in `tools/digests.yaml#sandbox.policy_yaml`. `collect_policy_signal` reads only this path. The startup integrity check verifies the digest; `SandboxHealthProbe` surfaces a mismatch as `reasons=["policy_digest_missing"]`. Repo-resident `.codegenie/policy.yaml` is ignored by the policy gate (it may still configure other tool behavior).

## Tradeoffs

| Gain | Cost |
|---|---|
| LLM-produced patches modifying the repo's policy file are irrelevant — the gate cannot be neutered from inside the sandbox | Per-repo policy variation is not supported by the policy gate (intentional — Phase 5 ships one policy) |
| Digest-pinned ensures policy changes require an explicit `tools/digests.yaml` edit + ADR amendment | Policy update cadence is global, not per-repo — slower roll-out for narrow fixes |
| `tests/adversarial/test_in_repo_policy_ignored.py` proves the property — patch modifies `.codegenie/policy.yaml`, gate result is unchanged | Operators learn there are two YAML files named similarly; documentation cost real |
| Source path is constant — readers find policy in one place | A future "per-team policy bundles" use case requires an ADR amendment to widen this |

## Consequences

- `tools/policy/sandbox-policy.yaml` is the single policy source.
- `tools/digests.yaml#sandbox.policy_yaml` carries the BLAKE3 digest.
- `tests/schema/test_digests_yaml.py` asserts `sandbox.policy_yaml` is present.
- `tests/adversarial/test_in_repo_policy_ignored.py` is the load-bearing adversarial test.
- `SandboxHealthProbe` startup check reads `tools/digests.yaml` and verifies; refuses to run on mismatch.
- New invariant: no module under `sandbox/signals/policy.py` reads from anywhere under the target repo's `.codegenie/`.
- Policy updates are global — they ship as a `tools/policy/sandbox-policy.yaml` edit + a `tools/digests.yaml` update + an ADR amendment.

## Reversibility

**Low.** Reverting to repo-resident policy reopens the adversarial vector. Adding *additional* policy sources (e.g., per-org bundles layered on top) is a forward-compatible extension. The "one policy, codegenie-owned" choice is intended to be durable until Phase 12+ adds calibrated per-org policy.

## Evidence / sources

- [final-design.md §Synthesis ledger — Policy source row](../final-design.md#synthesis-ledger) (winner score 11)
- [final-design.md §Departures §6](../final-design.md#departures-from-all-three-inputs)
- [phase-arch-design.md §Edge case 10](../phase-arch-design.md#edge-cases)
- [phase-arch-design.md §Component design — Signal collectors](../phase-arch-design.md#signal-collectors-six-functions-open-registry) — "Policy YAML source is the digest-pinned tools/policy/sandbox-policy.yaml — NOT the repo's .codegenie/policy.yaml"
- [phase-arch-design.md §Adversarial tests](../phase-arch-design.md#adversarial-tests)
- [production ADR-0021](../../../production/adrs/0021-policy-engine-build-vs-adopt.md)
