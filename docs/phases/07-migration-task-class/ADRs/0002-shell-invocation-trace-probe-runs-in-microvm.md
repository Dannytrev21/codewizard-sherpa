# ADR-0002: `ShellInvocationTraceProbe` executes target-repo code inside the Phase 5 microVM

**Status:** Accepted
**Date:** 2026-05-19
**Tags:** threat-model · sandbox · phase-5-integration · probe-discipline
**Related:** [0003](0003-sandbox-role-additive-enum-on-spawn.md), [0005](0005-probes-live-under-plugin-not-core-tree.md), [0015](0015-allowed-binaries-amendment-dive-buildx.md), [Phase 5 ADR-0001](../../05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md), [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md), [Phase 3 ADR-0006](../../03-vuln-deterministic-recipe/ADRs/0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md)

## Context

`ShellInvocationTraceProbe` answers the question "does this repo's container actually invoke a shell?" — the precondition for distroless migration to be safe (distroless images have no `/bin/sh`). The three lens designs disagreed sharply on what the probe IS:

- **Performance-first** treated it as a reducer over a Phase-2-captured runtime trace (~80 ms; no isolation needed). The critic landed this is **wrong on the facts**: Phase 2 ships no runtime-trace artifact today. Performance invented a precondition that does not exist.
- **Best-practices** invented a `dive` + `strace` wrapper running in a "Phase-2-shaped sandbox" (10–30 s). The critic flagged this as **a sandbox tier that doesn't exist**; `strace` also requires `CAP_SYS_PTRACE` and is a half-measure in a shared-kernel environment.
- **Security-first** committed to the honest reading: the probe **executes the target repo's build commands** to observe shell invocations, and must therefore be isolated. Security correctly identified this as the **first probe in the gather pipeline to run target-repo code** — a binding threat-model event.

Per `final-design.md §Lens summary §2` and `critique.md §Cross-design observations` ("The three designs literally do not agree on what the probe is"), the synthesis adopts security's framing: target-repo code execution at gather time is a new trust-boundary event and Phase 5's microVM stack is the only honest answer.

## Options considered

- **Option A — Reducer over a Phase 2 runtime-trace artifact.** Performance-first position. **Pattern:** Adapter over pre-existing evidence. **Rejected** — Phase 2 ships no such artifact.
- **Option B — `dive` + `strace` in a notional "Phase-2-shaped sandbox" tier.** Best-practices position. **Pattern:** Strategy with new sandbox tier. **Rejected** — the tier does not exist; `strace` is a `CAP_SYS_PTRACE`-requiring half-measure in shared-kernel environments; convention drift against Phase 5's microVM stack.
- **Option C — Execute the build inside Phase 5's microVM stack via `SandboxClient.spawn(role=Role.PROBE)`; trace from outside the VM via Phase 5's existing eBPF host-side view.** **Pattern:** Hexagonal Port + Adapter (reuse Phase 5's port; new caller, no new isolation tech).
- **Option D — Stand up a parallel `probe-control` process alongside Phase 5's `gate-control`.** Security's original framing. **Rejected** ([0003](0003-sandbox-role-additive-enum-on-spawn.md)) — doubles the supervision tree and credential boundary count.

## Decision

Adopt **Option C.** `ShellInvocationTraceProbe`'s `run()` calls `SandboxClient.spawn(role=Role.PROBE, workspace=repo.workspace, command=["docker", "buildx", "build", "--target=builder", "."], capture_trace=True)`. The microVM (Firecracker on Linux, Lima on macOS, per Phase 5's stack) runs `docker buildx build` against the rendered builder stage plus a short container boot. The shell-invocation trace is captured **outside the VM** via Phase 5's existing eBPF host-side view. The in-VM `strace` is informational only and is **not** added to `ALLOWED_BINARIES` ([0015](0015-allowed-binaries-amendment-dive-buildx.md)). The probe is `heaviness="heavy"`, `runs_last=True`, content-cached on `(image-digest, Dockerfile-digest, package.json-digest)`.

## Tradeoffs

| Gain | Cost |
|---|---|
| Honest threat model — target-repo code execution is isolated in a microVM, the same isolation tier Phase 5 already established for gates | Cold-path wall-clock is seconds (Firecracker boot ~150 ms + container boot 2–10 s + build time), not the ~80 ms performance-first claimed |
| Reuses Phase 5's microVM stack (Firecracker/gVisor/Lima) verbatim — no new isolation tech | Requires Phase 5 amendment ([0003](0003-sandbox-role-additive-enum-on-spawn.md)) for the `Role.PROBE` enum value; Phase 5 must ratify |
| Caching is effective: warm path ≤ 100 ms via content-cache hit on `(image-digest, Dockerfile-digest, package.json-digest)` | Portfolio-scale dispatch cost (Phase 10) is real and named in §Risks #4 of `final-design.md` — the dispatch-time filter `applies_to_tasks` is not a gather-time gate, so the heavy probe may run on repos that ultimately never select migration |
| Phase 5's eBPF host-side view is the canonical trace surface; the in-VM observation is informational only — no `strace` privilege escalation | macOS-via-Lima cost is non-trivial; Phase 7 accepts seconds-scale cold runs there. Phase 8's warm-pool reuse is the Planned mitigation, not Phase 7's |
| A fence test (`tests/fence/test_shell_trace_probe_isolation.py`) AST-walks `run()` and asserts only `SandboxClient.spawn(...)` is reachable — no `subprocess.run`, `os.system`, `os.popen`, `shell=True` | Fence is structural; doesn't catch dynamic code that bypasses the AST check. Acceptable; `forbidden-patterns` hook covers the runtime cases |

## Pattern fit

Implements **Hexagonal Port + Adapter** (toolkit §Architecture / boundaries; [Phase 3 ADR-0006](../../03-vuln-deterministic-recipe/ADRs/0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md) precedent): the probe depends on Phase 5's `SandboxClient` port; the microVM is the adapter; the probe does not know which sandbox backend (Firecracker / gVisor / Lima) is being used. Also instantiates **Threat-model-binding** (toolkit §Adversarial review): the first piece of gather-time code execution defines a new trust boundary, and the design surfaces it explicitly rather than smuggling it in.

## Consequences

- The probe lives in `plugins/distroless-migration--node--npm/probes/shell_trace_probe.py` per [0005](0005-probes-live-under-plugin-not-core-tree.md). It does **not** ship in `src/codegenie/probes/`.
- `Probe.run(repo, ctx)` receives `ctx.sandbox_client` via the existing `ProbeContext` capability shape. No new top-level context attribute is needed beyond what Phase 5 already wires.
- `tests/fence/test_shell_trace_probe_isolation.py` AST-walks the probe module and asserts: zero `subprocess.run` / `os.system` / `os.popen` / `shell=True`; the only privileged exit is `SandboxClient.spawn(role=Role.PROBE, ...)`. Mirrors the discipline of `tests/fence/test_capability_fence.py` (Phase 3).
- Cache strategy is `cache_strategy="content"` with `declared_inputs = ["Dockerfile", "**/Dockerfile", "package.json", "image-digest:<resolved>"]`. Cold-path cost is real but warm-path cost is ≤ 100 ms per the perf envelope.
- Failure modes are typed: microVM boot failure → `confidence: "low"` with `reason: "build_failed"`; non-zero docker buildx exit → `confidence: "low"` with `reason: "build_failed"`; success → `confidence: "high"` with the invocation list.
- Phase 7 fence allowlist ([0009](0009-phase-7-byte-edit-allowlist-fence.md)) does not authorize a parallel `probe-control` process; the security design's separate-process apparatus is closed off structurally.
- Warning IDs are pre-registered: `shell_invocation_trace.sandbox_boot_failed`, `shell_invocation_trace.build_failed`. Match `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` per Phase 1 ADR-0007.

## Reversibility

**Medium.** If Phase 8 surfaces a different probe-isolation model (e.g., warm-pool microVMs as a Phase-5-amended `Role.WARM_PROBE`), Phase 7's `Role.PROBE` use site is one parameter to swap. If a future Phase 2 lift produces a runtime-trace artifact for free, this probe could conceivably become a reducer — but that's a multi-phase change with its own ADR, not a Phase-7 reversal.

## Evidence / sources

- `../final-design.md §Lens summary §2`, §Component §6, §Synthesis ledger row 2 (score 13/15)
- `../phase-arch-design.md §Component design §9` (`ShellInvocationTraceProbe`), §Edge cases #2, §Testing strategy §Fence / structural
- `../critique.md §Attacks on the performance-first design "Things this design missed"`, §Attacks on the best-practices design §2 (assumption breakdown), §Cross-design observations
- [Phase 5 ADR-0001 — two-chokepoint sandbox seam](../../05-sandbox-trust-gates/ADRs/0001-two-chokepoint-sandbox-seam.md)
- [Phase 3 ADR-0006 — Hexagonal `SubprocessJail` Port](../../03-vuln-deterministic-recipe/ADRs/0006-hexagonal-subprocessjail-port-bwrap-sandbox-exec.md) (precedent: hexagonal sandbox port)
- [production ADR-0005 — No LLM in gather pipeline](../../../production/adrs/0005-no-llm-in-gather-pipeline.md)
