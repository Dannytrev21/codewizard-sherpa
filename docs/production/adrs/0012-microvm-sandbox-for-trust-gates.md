# ADR-0012: microVM sandbox isolation for Trust-Aware gates

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** trust · sandbox · safety
**Related:** ADR-0008, ADR-0019

## Context

Trust-Aware gates evaluate agent output by running it: building the candidate image, executing the test suite, running SAST/DAST, capturing a runtime trace. This requires executing untrusted code (the agent's output is, by definition, code the system has not yet verified) on infrastructure that runs alongside production-adjacent systems.

The isolation boundary between "agent output" and "everything else" is therefore safety-critical. A weak sandbox lets an agent's mistake (or worse — a prompt-injection-induced malicious change) reach the Temporal cluster, the MCP servers, the credentials, or the host kernel.

## Options considered

- **Bare-metal / shared kernel containers.** Run `docker build` on the same host as workers. Fastest, lowest isolation. Container escapes have been demonstrated against real kernels; this is unsafe for production.
- **Standard Docker containers with seccomp/AppArmor.** Better than bare metal; still shared kernel. Acceptable for trusted workloads, not for agent-generated code.
- **microVM (Firecracker / gVisor / nested QEMU).** Each gate evaluation runs in its own kernel. Hardware-isolated boundary. Higher cold-start cost; significantly stronger isolation.
- **Remote sandbox service (e.g., third-party).** Outsources the safety boundary. Cost and data-residency tradeoffs; introduces vendor dependency.

## Decision

**Every Trust-Aware gate evaluation runs inside a microVM.** Each gate invocation gets its own ephemeral microVM with no persistent storage and no network access except to the artifact registry (for base-image pulls) and the gate result reporting endpoint.

The specific microVM stack (Firecracker vs gVisor vs nested QEMU) is **deferred** to ADR-0019 — that decision depends on cold-start latency tolerance and kernel-feature requirements for `strace`/eBPF inside the sandbox.

## Tradeoffs

| Gain | Cost |
|---|---|
| Hardware-grade isolation between agent output and the orchestrator | Cold-start latency higher than shared-kernel containers (depending on stack: 100ms Firecracker, seconds for nested QEMU) |
| A malicious or buggy agent output cannot escape into the host environment | Operational complexity — microVM clusters are not "just run docker" |
| Reproducible — sandbox state is ephemeral, every gate starts clean | Resource overhead: full kernel per gate, not shared |
| Container-escape CVEs in shared-kernel runtimes do not threaten the orchestrator | Cannot mount host directories trivially — must use explicit copy-in/copy-out |
| Compliance posture is dramatically simpler — "agent code runs in its own VM" is a clean story | Sandbox stack itself becomes attack surface; must be patched aggressively |

## Consequences

- The `sandbox/` package in the codebase wraps a microVM client. The Trust-Aware gate logic calls into it via a stable RPC contract — same contract regardless of which stack ADR-0019 picks.
- microVM clusters are autoscaled independently from worker pods (`../design.md §8.4` physical view). Capacity planning treats them as a distinct concern.
- Cost model: each gate evaluation pays for the microVM lifecycle plus the actual build/test compute. At portfolio scale this is the dominant non-LLM cost.
- Network policy inside the sandbox: deny-all by default, with an allowlist for `cgr.dev`, `docker.io` (or the org's internal registry), and the gate-result endpoint. No connections to the Temporal cluster, MCP servers, or anything else.
- Pulling intermediate build artifacts back to the orchestrator goes through explicit copy-out steps, not shared volumes.

## Reversibility

**Medium.** Replacing the microVM stack (e.g., Firecracker → gVisor) is well-scoped — change the sandbox client implementation, keep the RPC contract. Reversing the *decision to sandbox* (going back to shared-kernel containers) is high cost both technically (lose isolation guarantees) and socially (any security review of the system would re-flag the decision).

## Evidence / sources

- `../design.md §4.1` (Layer 3 — Trust-Aware Verification)
- `../design.md §5` (sandboxed reality checks subsection)
- `../design.md §8.4` (physical view — sandbox cluster as separate trust boundary)
- `../../gemini-auto-agent-design.md §"Multi-Repository Orchestration and Control Planes"` — Environment Agents in sandboxes
- OpenHands V1 architecture — Docker-based isolation for agent code execution
- Firecracker production usage at AWS Lambda — microsecond cold start, hardware isolation
