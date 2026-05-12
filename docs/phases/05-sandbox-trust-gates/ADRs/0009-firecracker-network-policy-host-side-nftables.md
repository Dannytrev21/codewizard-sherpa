# ADR-0009: Firecracker network policy via host-side TAP + nftables

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** firecracker · network · isolation
**Related:** [ADR-0004](0004-dind-default-macos-with-gate-isolation-class.md), [production ADR-0019](../../../production/adrs/0019-sandbox-stack.md)

## Context

`SandboxSpec.network: Literal["none", "scoped"]` + `egress_allowlist: list[str]` are the contract every backend must enforce. DinD uses iptables in `sandbox/did/network_policy.py`. Firecracker is a microVM with no iptables analog — the synthesis was silent on *how* Firecracker enforces the same policy. Without a specified mechanism, the smoke test would pass (the workload is isolated by KVM) but `network=scoped` would either drop all egress (overconservative; `npm ci` fails) or allow all (under-specified; isolation story incomplete). See [phase-arch-design.md §Gap 4](../phase-arch-design.md#gap-4-networkscoped-allowlist-enforcement-on-firecracker-has-no-implementation-specified).

## Options considered

- **Inside-guest filtering** — Run iptables inside the microVM. Requires kernel modules in the pinned rootfs; the rootfs becomes more complex; the guest is part of the TCB.
- **Firecracker MMDS-based DNS allowlist** — Use Firecracker's metadata service to provide a DNS allowlist; rely on the guest to obey. Trusts the guest — wrong direction.
- **Host-side TAP device + nftables** — Firecracker boots with a `tap0` virtual interface on the host; host nftables rules drop egress not matching the allowlist; the host is the enforcement boundary, not the guest. This is Firecracker's recommended pattern.
- **slirp4netns** — Rootless user-space networking. Better isolation than the no-policy stub; slower and less commonly deployed; nftables better matches the existing DinD shape.

## Decision

`sandbox/firecracker/network_policy.py` applies `network=scoped` policy via a host-side TAP device + nftables ruleset. The trusted boundary is the host kernel; the guest is untrusted. `network=none` configures the microVM with no network interface at all.

## Tradeoffs

| Gain | Cost |
|---|---|
| Enforcement boundary is the host kernel, not the guest — defense-in-depth against compromised workloads | Requires nftables on the runner; not portable to non-Linux hosts (acceptable — Firecracker is Linux-only by [ADR-0004](0004-dind-default-macos-with-gate-isolation-class.md)) |
| Architectural symmetry with `did/network_policy.py` — both backends apply host-level packet filtering | Two implementations (iptables for DinD, nftables for Firecracker) to maintain |
| `tests/integration/sandbox/test_firecracker_network_policy.py` is straightforward: boot microVM, `curl registry.npmjs.org` succeeds, `curl github.com` fails | Integration test is KVM-only, runs on the self-hosted runner + weekly cron |
| Pre-baked rootfs stays minimal — no iptables/nftables binaries needed in the guest | Network setup is per-`execute` (tap creation + rule install + teardown) — ~50–100 ms overhead per gate |
| `egress_allowlist` accepts hostnames; resolution happens on the host via standard DNS (allowlist-checked) | DNS resolution failures on the host masquerade as "egress denied" — error message must be clear |

## Consequences

- `src/codegenie/sandbox/firecracker/network_policy.py` implements `apply_policy(spec: SandboxSpec) -> NetNamespaceConfig` (tap creation + rule install).
- `tests/golden/nftables_rules_<network-policy>.txt` golden-files the exact ruleset for each policy.
- `tests/integration/sandbox/test_firecracker_network_policy.py` is `skip_if_no_kvm`.
- Subprocess invocation of `nft` is gated to this module — the same chokepoint pattern as `did/network_policy.py`'s `iptables` call.
- Cleanup on `execute` exit: TAP teardown + rule removal; orphan TAPs are detected by `codegenie sandbox health` and cleaned by `codegenie sandbox gc`.
- New invariant: every `SandboxClient` implementation enforces `network`/`egress_allowlist` at the host boundary (never the guest).

## Reversibility

**Medium.** Switching to slirp4netns or MMDS-DNS-allowlist would replace the implementation file but keep the contract surface. Switching to *in-guest* enforcement would weaken isolation and likely require chain-compat regeneration of trace baselines (different egress observability). The decision to keep enforcement host-side is intended to be durable.

## Evidence / sources

- [phase-arch-design.md §Gap analysis Gap 4](../phase-arch-design.md#gap-4-networkscoped-allowlist-enforcement-on-firecracker-has-no-implementation-specified)
- [phase-arch-design.md §Physical view](../phase-arch-design.md#physical-view--where-does-this-code-run)
- [final-design.md §Risk surface](../final-design.md#) — egress as defense-in-depth
- [production ADR-0019](../../../production/adrs/0019-sandbox-stack.md) — sandbox stack target Phase 5 generates evidence for
