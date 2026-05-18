# ADR-0006: Hexagonal `SubprocessJail` Port — bwrap (Linux) + sandbox-exec (macOS) adapters as the Phase-3 interim sandbox; Phase 5 substitutes microVM via the same Port

**Status:** Accepted
**Date:** 2026-05-17
**Tags:** hexagonal · sandbox · ports-and-adapters · phase-5-substitution · interim-substrate
**Related:** [0007](0007-run-npm-install-and-npm-test-in-phase3-jail.md), [0011](0011-honest-framing-capability-sandboxedpath-pluginslock.md), [0012](0012-amend-allowed-binaries-npm-bwrap-sandbox-exec-jq.md), [production ADR-0012](../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md), [production ADR-0019](../../../production/adrs/0019-sandbox-stack.md)

## Context

Phase 3's roadmap exit criterion requires running `npm install` and `npm test` against an unknown target repo on the operator's laptop or a CI runner (Goal G1 in `phase-arch-design.md`). Production ADR-0012 commits to a microVM (Firecracker) sandbox for trust gates, but that substrate is owned by Phase 5 (`05-ADR-0004`). Phase 3 cannot wait for Firecracker without slipping its exit criterion by an entire phase.

The architecture spec resolves the substrate question via Hexagonal architecture: define a `SubprocessJail` **Port** in Phase 3, ship two **Adapters** (bwrap on Linux, sandbox-exec on macOS) as the interim substrate, and arrange the interface so Phase 5's Firecracker / DinD adapters substitute via the same Port with zero changes to `RemediationOrchestrator` or any plugin (`phase-arch-design.md §Component design C8`, §Design patterns applied row 3, §Physical view).

The critic attacked the security lens's earlier macOS-prefetch-online-offline flow (`critique.md §Attacks on the security-first design — Issue 2`) — prefetching dependencies in an unjailed flow before running offline npm creates a second, *unjailed* trust boundary that defeats the primary defense. The architecture spec rejects offline mode and ships **online-mode-default on both substrates**, with `RegistryAllowlist(["registry.npmjs.org"])` enforced at the netns / pf layer per Adapter.

## Options considered

- **Option A — No jail in Phase 3; spawn `npm install` / `npm test` directly via `run_external_cli`. Phase 5 adds the jail.** **Pattern:** No isolation. Postinstall scripts execute on the host filesystem; network egress unrestricted; one malicious `package.json` exfiltrates `~/.ssh`. Unacceptable threat model for Phase-3 unattended use.
- **Option B — Ship Firecracker in Phase 3.** **Pattern:** Hexagonal substrate, but premature — Firecracker requires KVM, virtio image management, networking setup, and ops scaffolding that Phase 5 already owns. Duplicates Phase 5's work; doesn't change the threat model meaningfully for an operator-laptop POC.
- **Option C — Hexagonal Port `SubprocessJail` with two Adapters (`BwrapAdapter` for Linux, `SandboxExecAdapter` for macOS).** Phase 5 substitutes `FirecrackerAdapter` (Linux/CI) and `DinDAdapter` (macOS dev) via the same Port. The orchestrator is substrate-agnostic. **Pattern:** Hexagonal architecture / Ports and adapters — two real implementations from day one (Linux vs macOS); Phase 5 is the real third adapter.

## Decision

Adopt **Option C.** Ship `SubprocessJail(Protocol)` in `src/codegenie/transforms/sandbox_jail.py` with one method `async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult`. Ship two production Adapters:

- **`BwrapAdapter` (Linux)** — `bwrap --unshare-all --new-session --die-with-parent --ro-bind / / --tmpfs /tmp --bind <jail> <jail>`; seccomp blocks `mount`, `pivot_root`, `ptrace`, `bpf`, `unshare`, `keyctl`. Parent process owns the network namespace; child sees `lo` + pf-routed `RegistryAllowlist`.
- **`SandboxExecAdapter` (macOS)** — `sandbox-exec -f <generated.sb>` with `deny default`; explicit allow-rules for the jail and `RegistryAllowlist` hosts.

`JailedSubprocessResult` is a tagged union: `Completed | TimedOut | OomKilled | NetworkDenied | DiskQuotaExceeded` — every branch typed; no `dict[str, Any]`; no bare exceptions. **Online mode is the default on both substrates** (rejects the security lens's offline-prefetch flow per critic Issue 2). `--ignore-scripts` is enforced at both the npm CLI AND the env var (`npm_config_ignore_scripts=true`) because npm has historically respected only one or the other.

## Tradeoffs

| Gain | Cost |
|---|---|
| `RemediationOrchestrator` and every plugin's `RecipeEngine` are substrate-agnostic — Phase 5's microVM swap is a constructor-injection swap, not a refactor | Three substrate code paths to maintain (bwrap, sandbox-exec, and Phase 5's Firecracker/DinD); each has its own quirks |
| Phase-3 exit criterion meetable without Phase-5 dependency — Goal G1 lands now | bwrap/sandbox-exec are weaker than microVM isolation; a kernel-level CVE in seccomp or sandbox-exec could escape. We document this as accepted-for-Phase-3-threat-model |
| Two real implementations from day one — `Hexagonal Port` pays rent immediately, not "after Phase 5 ships the second one" | macOS `sandbox-exec` is deprecation-flagged by Apple; Phase 5 substitutes Lima/DinD on macOS. Phase 3 carries the tech-debt explicitly (sized as ~150 LOC of `.sb` profile generation) |
| `JailedSubprocessResult` is a tagged union — `NetworkDenied(host)` is observable; the test stack can branch on each failure mode | Adapter authors must map their substrate's failure signals to the right variant — bwrap signals differ from sandbox-exec which differ from Firecracker. Each Adapter ships its own translator |
| Online-mode default on both substrates with `RegistryAllowlist` enforced at the netns/pf layer — no second trust boundary (per critic Issue 2 rejection of offline-prefetch flow) | Network policy must be enforced *outside* the child — relies on parent-process netns ownership (Linux) and pf rules (macOS); a misconfigured Adapter is a real egress hole |
| Hexagonal seam is one method (`run(spec) -> result`); Phase 5's three-retry envelope wraps the orchestrator's stage-6 method, not this Port — clean separation | The Port carries no concept of "retry within the jail"; retry envelope responsibility lives at the orchestrator/gate layer, which is correct but requires understanding Phase 5's wrap pattern |
| Setup cost ~80–200 ms (Linux) / ~50–150 ms (macOS) per spawn; 3 spawns/workflow → ~600 ms substrate cost — well within the p50 ≤ 18 s budget | Cold-start CI runners may see higher first-spawn cost; relative-budget assertions catch regressions |

## Pattern fit

Implements **Hexagonal architecture / Ports and adapters** (toolkit §Architecture-scale patterns) faithfully: the core domain (`RemediationOrchestrator`, recipe engines) talks to the outside world (npm, OS isolation primitives) only through the `SubprocessJail` Port. The two Adapters ship as real, working implementations on day one — escaping the toolkit's failure mode "a 'hexagonal' design that smuggles `requests.get(...)` directly into a domain function." Phase 5's microVM substitution is the canonical use case: same Port, swappable substrate, zero domain edits.

## Consequences

- `src/codegenie/transforms/sandbox_jail.py` houses the Port and the two Adapters; `tests/unit/transforms/test_sandbox_jail.py` tests each branch of `JailedSubprocessResult`.
- ADR-0012 (this phase) amends Phase-0/2 `ALLOWED_BINARIES` with `bwrap` and `sandbox-exec`.
- macOS `sandbox-exec` profile content (`tooling/sandbox/macos-npm.sb`) is implementation-defined; the architecture only commits to the policy at the YAML/profile level.
- macOS CI runs as a nightly smoke job (not per-PR) — sandbox-exec adapter is exercised once per day; Linux bwrap path is the per-PR substrate.
- Phase 5's `FirecrackerAdapter` (Linux/CI) and `DinDAdapter` (macOS dev) substitute the Adapters; `RemediationOrchestrator`'s `__init__(sandbox: SubprocessJail | None = None)` accepts either.
- Adversarial tests: `tests/adversarial/test_postinstall_canary.py` (postinstall does not write canary); `tests/adversarial/test_malicious_npmrc.py` (`.npmrc` redirect to attacker host → `NetworkDenied`); `tests/adversarial/test_symlink_toctou.py` (`SandboxedPath` `O_NOFOLLOW` raises `ELOOP`).
- Defers ADR-0019 (sandbox stack final choice) — Phase 5 sharpens it, Phase 13 resolves it with bench evidence.

## Reversibility

**High.** Adding a third Adapter (or substituting Phase 5's Firecracker) is a new module + constructor injection — zero edits to existing code. Removing the Port entirely (collapse back to direct `subprocess.run`) would require unpicking every recipe engine's `SubprocessJail` dependency — feasible but loses the substitution property. The Port is the easy-to-extend direction; the no-jail direction is the hard one.

## Evidence / sources

- `../phase-arch-design.md §Component design C8`, §Design patterns applied row 3, §Physical view, §Edge cases E7 + E8 + E12
- `../final-design.md §Synthesis ledger row "Sandbox for npm"` (score 14/15)
- `../critique.md §Attacks on the security-first design — Issue 2` (offline-prefetch flow rejected) and §Issue 4 (JVM SecurityManager rejected; `SubprocessJail` is the real defense)
- [production ADR-0012 — microVM sandbox for trust gates](../../../production/adrs/0012-microvm-sandbox-for-trust-gates.md)
- [production ADR-0019 — sandbox stack (deferred)](../../../production/adrs/0019-sandbox-stack.md)
- [Phase 5 ADR-0004 — DinD default macOS with gate isolation class](../../05-sandbox-trust-gates/ADRs/0004-dind-default-macos-with-gate-isolation-class.md)
- design-patterns-toolkit.md §Hexagonal architecture / Ports and adapters
