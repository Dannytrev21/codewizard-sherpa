# ADR-0004: DinD is the macOS default; `gate_isolation_class` annotation propagates

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** sandbox · macos · isolation · downstream-signal
**Related:** [ADR-0009](0009-firecracker-network-policy-host-side-nftables.md), [production ADR-0009](../../../production/adrs/0009-humans-always-merge.md), [production ADR-0012](../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md), [production ADR-0019](../../../production/adrs/0019-sandbox-stack.md)

## Context

The roadmap names Docker-in-Docker (DinD via Docker Desktop) as the portable macOS sandbox choice. One of the three Phase 5 input designs (security-first) refused DinD-on-macOS, requiring Lima + microVM on every developer laptop. The critic flagged this as the central conflict: DinD on macOS is a *shared-kernel* boundary, so an attacker who (a) influences Phase 4's LLM output and (b) defeats `--ignore-scripts` could escape on a developer's laptop. Lima would close that gap but stalls every developer's dev loop (slow boot, fragile, not in the roadmap). See [final-design.md §Synthesis ledger row: Sandbox stack default macOS](../final-design.md#synthesis-ledger) and [critique.md](../critique.md) (central attack).

## Options considered

- **Lima + microVM on macOS (security-first)** — Hardware-class isolation everywhere. Closes the LLM-patch-escape vector on dev laptops. Costs: every developer maintains a Lima VM; cold boot 20–60 s; failure modes the rest of the team has never debugged.
- **DinD on macOS, gVisor on Linux (mixed)** — Two production stacks; no single integration point; pre-empts [ADR-0019](../../../production/adrs/0019-sandbox-stack.md) before evidence exists.
- **DinD on macOS, Firecracker on Linux/CI, `gate_isolation_class` annotation** — Honor the roadmap; ship both backends; annotate every verdict with its isolation class so downstream phases can refuse to auto-promote shared-kernel verdicts; humans always merge ([ADR-0009](../../../production/adrs/0009-humans-always-merge.md)) is the final gate.

## Decision

DinD via Docker Desktop is the default macOS backend; Firecracker is the Linux/CI second backend (KVM-gated, exercised by a single CI smoke test + weekly cron). Every `SandboxRun` carries a `gate_isolation_class: Literal["shared_kernel", "microvm"]` field. Downstream phases (Phase 11 merge-gate, Phase 13 cost dashboard) consume this annotation explicitly.

## Tradeoffs

| Gain | Cost |
|---|---|
| Roadmap honored; Phase 6/7's dev loop works on any Mac without operator heroics | DinD on macOS is shared-kernel; LLM-patch-driven escape on a developer laptop is an acknowledged residual risk |
| Annotation propagates downstream — Phase 11 can refuse to auto-promote `shared_kernel` verdicts; Phase 13 can segment cost by class | Every `SandboxRun` and `RetryLedger` entry carries a new field forever — Phase 6 state ledger must lift it |
| Both backends share the `SandboxClient` Protocol — single contract surface | Two backends to maintain; rootfs/digest pinning is non-trivial (covered by `tools/digests.yaml#sandbox.{firecracker,vmlinux,rootfs}`) |
| Real Firecracker (not stub) generates ADR-0019-grade evidence (cold-start latency, kernel feature requirements, per-evaluation cost) | One self-hosted KVM runner is required for CI; weekly cron infra has an owner (open Q6) |
| Humans always merge ([ADR-0009](../../../production/adrs/0009-humans-always-merge.md)) is the final gate — shared-kernel is not the last line of defense | Reviewers must learn the annotation's meaning; evidence-bundle UX (Phase 11) carries the explanatory burden |

## Consequences

- `SandboxRun.gate_isolation_class` is a load-bearing contract field; removing it requires migrating Phase 11 and Phase 13.
- `codegenie sandbox auto-detect` returns Firecracker if `/dev/kvm` is readable, else DinD; structured fallback INFO log on macOS.
- `tests/integration/sandbox/test_firecracker_smoke.py` is `pytest.mark.skip_if_no_kvm`; weekly cron job exercises it on the self-hosted runner.
- macOS developer-laptop verdicts are *evidence*, never *auto-merge tickets*. The dev-loop posture is documented in this ADR so future readers do not "fix" macOS to Lima without first measuring downstream cost.
- The roadmap is honored over the security purist position; the residual risk is explicit, not hidden.
- New invariant: any new sandbox backend (e.g., gVisor in a future phase) must declare its `gate_isolation_class` value; the union widens additively.

## Reversibility

**Low.** Reverting to Lima-on-macOS would force every developer to install + maintain a microVM stack; the dev-loop cost is documented and substantial. Reverting the annotation field would orphan downstream phases that already consume it. The tradeoff is explicitly accepted; reopening it requires fresh evidence (e.g., a measured LLM-patch escape incident on a dev laptop) and a roadmap amendment.

## Evidence / sources

- [final-design.md §Synthesis ledger — Sandbox stack default macOS row](../final-design.md#synthesis-ledger) (winner score 11)
- [final-design.md §Risks risk-1 (DiD on macOS = shared kernel)](../final-design.md#) [phase-arch-design.md §Physical view](../phase-arch-design.md#physical-view--where-does-this-code-run)
- [phase-arch-design.md §Goals 5 and 6](../phase-arch-design.md#goals)
- [critique.md](../critique.md) — central conflict
- [production ADR-0019](../../../production/adrs/0019-sandbox-stack.md) — to be resolved with Phase 5/13/16 evidence
