# ADR-0019: Sandbox stack (Firecracker / gVisor / nested QEMU)

**Status:** Deferred
**Date:** 2026-05-11
**Tags:** platform · sandbox
**Related:** ADR-0012

## Context

ADR-0012 commits to microVM isolation for Trust-Aware gate evaluations. The specific microVM stack is deferred because the choice depends on workload characteristics we won't know definitively until production.

The three candidates have different cost profiles:

- **Firecracker** (AWS's microVM, used in Lambda and Fargate). Hardware-virtualized, KVM-backed, sub-100ms cold start. Used by major production systems for exactly this workload pattern. Linux-only guest. Limited filesystem features compared to a full VM.
- **gVisor** (Google's user-space kernel). Strong isolation via system-call interception. Lower overhead than a true microVM in some workloads, higher in others. Better Linux compatibility than Firecracker. Slightly weaker isolation boundary than Firecracker's hardware virtualization.
- **Nested QEMU.** A full VM inside another VM. Maximum compatibility, slowest cold start, highest overhead. Useful when guest needs unusual kernel features.

## Options considered

- **Firecracker.** Best for high-volume, fast-cold-start, Linux-only sandbox workloads.
- **gVisor.** Best when guest needs broader syscall surface than Firecracker provides (some `strace`/eBPF setups, exotic filesystem operations).
- **Nested QEMU.** Best when guest needs to run a different OS or specific kernel features.
- **Multiple stacks in parallel** — route gate workloads to the appropriate stack by tag. Operational complexity in exchange for flexibility.

## Default until decided

**No default committed.** During POC and pre-production, gates can run in Docker-with-seccomp on a dedicated sandbox host (acceptable risk for non-production workloads). Production rollout requires this ADR to be resolved.

## Evidence needed to resolve

- **Cold-start latency tolerance.** How often do gates fire? If thousands per minute, sub-100ms cold start matters; if dozens per minute, seconds-of-cold-start is fine.
- **Kernel feature requirements inside the sandbox.** The gate runs `docker build`, `strace`, possibly eBPF tools, possibly Vagrant. Does each stack support what we need?
- **Operational experience.** Firecracker requires KVM-capable hosts; gVisor runs anywhere; nested QEMU works but is operationally complex.
- **Cost per evaluation.** Sandbox lifecycle cost (compute + storage churn) dominates non-LLM cost at portfolio scale. Cheaper-per-evaluation wins.
- **Compliance posture.** Some compliance frameworks treat hardware-isolated (Firecracker) and user-space-isolated (gVisor) sandboxes differently for "execute untrusted code" categories.

## Reversibility (of the eventual choice)

**Medium.** The `sandbox/` package wraps the stack behind a stable RPC contract (per ADR-0012). Replacing one stack with another is a localized change to the sandbox client; gate logic is unaffected. But: migration during production has downtime risk.

## Evidence / sources

- `../design.md §5` (Sandboxed reality checks subsection — explicit deferral)
- `../design.md §7` (Open questions — Sandbox stack)
- `../design.md §8.4` (physical view — sandbox cluster as separate trust boundary)
- Firecracker public case studies — AWS Lambda, Fargate
- gVisor production usage at Google Cloud
- OpenHands V1 architecture — Docker isolation pattern, cited as reference for upgrading to microVM
