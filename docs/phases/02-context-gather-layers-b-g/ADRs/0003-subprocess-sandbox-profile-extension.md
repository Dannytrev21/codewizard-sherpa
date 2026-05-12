# ADR-0003: Extend Phase 1's `run_in_sandbox` chokepoint; no new `SandboxStrategy` interface

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** security · sandbox · chokepoint-preservation · scope-discipline · synthesizer-departure
**Related:** [Phase 0 ADR-0007](../../00-bullet-tracer-foundations/ADRs/0007-probe-contract-frozen-snapshot.md), [Phase 1 ADR-0008](../../01-context-gather-layer-a-node/ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md), [production ADR-0019](../../../production/adrs/0019-sandbox-execution-stack.md), ADR-0002, ADR-0005

## Context

Phase 2 is the first phase that **executes foreign code on hostile input at scale**: `scip-typescript`, `semgrep`, `gitleaks`, `syft`, `grype`, `docker build`, and tree-sitter grammars all load attacker-controlled bytes (`final-design.md "Lens summary"`). Phase 1's threat model was *parser hardening* — adversarial JSON/YAML against in-process parsers (Phase 1 ADR-0008). Phase 2 jumps a category: code-loading interpreters, image builds, network-capable tools.

The security-first lens responded by introducing a four-strategy `SandboxStrategy` interface (`InProcessSubprocess` / `RootlessPodmanContainer` / `DockerInDocker` / `MicroVM`), a local pull-only registry mirror at `127.0.0.1:55300`, a `codegenie/probe-runtime` container image, and a capability-negotiation lattice (`design-security.md §"RootlessPodmanContainer strategy"`, `§"SandboxStrategy interface"`). The critic attacked this in three blows (`critique.md "Attacks on the security-first design"` #2, #4): forward-declares Phase 5's architecture (production ADR-0019 is explicitly deferred); introduces a long-lived registry service (violates `localv2.md` "single Python project, no services, no databases"); and adds infrastructure tax (probe-runtime image build pipeline, digest rotation policy) that no Phase 2 probe alone needs.

Phase 1 ADR-0008 already faced the same temptation and refused: the per-probe fork+exec sandbox lost to in-process caps in `parsers/`. The Phase 1 precedent applies; the question is whether Phase 2's expanded threat model justifies reversing it. The synthesis's answer (`final-design.md "Conflict-resolution table" D2`): no — preserve the chokepoint, extend the profile.

## Options considered

- **`SandboxStrategy` interface + rootless Podman + local registry mirror + probe-runtime image [S].** Strongest in-Phase-2 threat closure. New architectural layer ADR-0019 has not sanctioned. Forward-declares Phase 5 and Phase 14 infrastructure. Adds an always-on local-registry service. Adds a built+pinned container image as a Phase-2 deliverable.
- **Inherit Phase 1's `run_in_sandbox` unchanged [P/B].** No new security surface; same `bwrap`/`sandbox-exec` posture as Phase 1's parsers. Misses the network-egress concern that Phase 2's tools introduce; misses credential-shaped env-strip needs for `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `CHAINGUARD_TOKEN`, etc.
- **Extend Phase 1's `run_in_sandbox` profile in place [synth].** Same chokepoint, same call site, same probe-side contract. Adds `network: Literal["none", "scoped"] = "none"` parameter; extends env-strip; tightens the bwrap profile. No new abstraction. Phase 5 promotes the chokepoint *to a microVM* without changing the API. Phase 14 adds the local registry mirror *at the same chokepoint* without probe-code changes.

## Decision

**Extend Phase 1's `run_in_sandbox` chokepoint in `src/codegenie/exec.py` with a tighter Phase 2 profile.** No new module, no new abstraction layer, no new strategy interface. The signature gains one parameter:

```python
def run_in_sandbox(
    argv, *,
    allowlist, env, timeout_s, cwd,
    network: Literal["none", "scoped"] = "none",
    ...
) -> ProcessResult
```

- **Default `network="none"`.** Linux: `bwrap --unshare-all --unshare-net`. macOS: `sandbox-exec` profile with `(deny network*)` (best-effort; documented loudly in the module docstring).
- **`network="scoped"` requires per-tool allowlist.** Phase 2 has exactly one tool with a documented egress need: `grype db update` on cache miss. Phase 2 has one base-image-pull egress: `docker build` for `SyftSBOMProbe`. Both go through a per-tool allowlist (`grype-vuln-db-host`, `configured-base-image-registry-host`). Nothing else egresses.
- **Tighter env-strip.** Phase 1's `--unsetenv` list extends for: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `CHAINGUARD_TOKEN`, `GITHUB_TOKEN`, `AWS_*`, `GCP_*`, `AZURE_*`. Test `tests/adv/test_no_credentials_in_subprocess_env.py` asserts the sandboxed env contains none.
- **`--tmpfs /tmp`, `--ro-bind <repo> /repo`, `--ro-bind <tools-bin> /usr/local/bin`, `--die-with-parent`.** Same shape as Phase 1; tightened for the new tools.
- **No `SandboxStrategy` interface.** No `InProcessSubprocess` / `RootlessPodmanContainer` / `DockerInDocker` / `MicroVM` taxonomy. The chokepoint is the abstraction.
- **No local registry mirror, no `codegenie/probe-runtime` image.** `docker build` for SBOM pulls base images from the configured registry under `network="scoped"`; the supply-chain isolation that a mirror would provide is Phase 14's deliverable.
- **Phase 5's microVM lands at the same chokepoint.** When ADR-0019 resolves, the implementation inside `run_in_sandbox` changes (one branch); the call site changes nothing. Probes never know they moved from bwrap to a microVM. That's the architectural promise this ADR preserves.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 1 ADR-0008's "in-process caps via shared `parsers/`, no per-probe sandbox interface" precedent generalizes — same chokepoint discipline | `bwrap` / `sandbox-exec` is a kernel-shared sandbox, weaker than a microVM; a kernel zero-day in `io_uring`/`epoll`/`bwrap`'s userns handling breaks the boundary |
| Phase 5's microVM upgrade is a one-branch change inside `run_in_sandbox`; no probe code moves | Phase 2 ships without microVM-grade isolation against in-tool RCE — accepted, mitigated by the `RuntimeTraceProbe` deferral (ADR-0002) which is the one probe that would have most needed it |
| `localv2.md`'s "single Python project, no services" invariant holds — no local registry mirror, no built+pinned probe-runtime image | Base-image pulls for `SyftSBOMProbe` hit the configured registry (potentially `docker.io`); supply-chain isolation is incomplete in Phase 2; closed in Phase 14 |
| macOS dev parity via `sandbox-exec` — Phase 2 does not depend on rootless Podman being available everywhere | macOS `--network=none` enforcement is best-effort via `sandbox-exec`'s `(deny network*)`; documented loudly |
| One sandbox API; one set of tests; one threat-model surface to audit | The `network="scoped"` allowlist mechanism is a new sub-surface that needs its own test discipline; `tests/adv/test_no_credentials_in_subprocess_env.py` and `test_no_unscoped_network_egress.py` are CI-gating |
| Extension by addition: zero new top-level packages, zero new abstractions — same Phase-1 precedent | The Phase 5 sandbox-stack ADR-0019 still has open questions; Phase 2 is shipping inside that open question rather than resolving it, by design |
| Refuses gold-plating: no four-way strategy interface for three unused strategies | Reviewers reading `design-security.md` see the four-strategy lattice and must find this ADR to learn why it's not built |

## Consequences

- `src/codegenie/exec.py` gains: `network` parameter, extended `--unsetenv` list, `--tmpfs /tmp` default, per-tool scoped-egress helper (`with_scoped_network(hosts: list[str])`).
- `src/codegenie/tools/` wrappers call `run_in_sandbox` with `network="none"` by default. Two wrappers (`grype.py`, `docker.py`) declare per-call `network="scoped"` paths gated by configuration.
- `tests/adv/` ships: `test_no_credentials_in_subprocess_env.py`, `test_no_unscoped_network_egress.py`, `test_hostile_dockerfile_curl.py` (build network=none ⇒ `curl` fails inside sandbox).
- macOS path: `sandbox-exec` profile committed at `src/codegenie/exec/sandbox_exec.profile`; documented as best-effort for `--network=none`.
- Phase 5 owns the microVM landing: same call signature, new branch inside `run_in_sandbox`. Probes never change.
- Phase 14 owns the local registry mirror: lives outside `codegenie/` as a CI/operational service, not a code dependency.
- The four-strategy `SandboxStrategy` interface from `design-security.md` is documented as "rejected in Phase 2" in this ADR; production ADR-0019 is the place where the strategy question genuinely resolves.

## Reversibility

**Medium.** Promoting the chokepoint to a microVM (Phase 5) or adding a registry mirror (Phase 14) is mechanically additive — Probes' call sites stay identical. Replacing the chokepoint with a `SandboxStrategy` interface (the rejected option) requires either deleting the chokepoint or wrapping it — both of which are non-additive and would surface the question across every probe's wrapper. The chokepoint is the load-bearing piece; the *profile* is configuration. The decision to *not* introduce a strategy interface is high-cost to reverse because every probe-wrapper would need to learn about strategies; the decision *what to put in the chokepoint* is low-cost.

## Evidence / sources

- `../final-design.md "Goals (concrete, measurable)"` Subprocess-sandbox bullet — the profile spec
- `../final-design.md "Components" #2 Subprocess sandbox profile extension` — interface
- `../final-design.md "Conflict-resolution table" D2` — the resolution
- `../final-design.md "Architecture"` observation 3 — the chokepoint claim
- `../phase-arch-design.md "Goals" #8` — the profile statement
- `../phase-arch-design.md "Non-goals" #3` — explicit rejection of `SandboxStrategy`/registry mirror/runtime image
- `../critique.md "Attacks on the security-first design"` #2, #4 — the dismantling
- `../critique.md "Cross-design observations"` "Things this design missed" — perf cost of `--network=none` per container
- [Phase 1 ADR-0008](../../01-context-gather-layer-a-node/ADRs/0008-in-process-parse-caps-not-per-probe-sandbox.md) — the precedent
- [production ADR-0019](../../../production/adrs/0019-sandbox-execution-stack.md) — the deferred question Phase 5 owns
