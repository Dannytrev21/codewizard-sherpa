# Phase 05 — Sandbox + Trust-Aware gates: Devil's-advocate critique

**Reviewed by:** Devil's-advocate critic subagent
**Date:** 2026-05-12

## Method

I read all three designs and attacked each on its own terms. I do not propose alternatives. My job is to surface what the synthesizer needs to see before it merges.

---

## Attacks on the performance-first design

### Concrete problems

1. **Problem:** The `GateVerdictCache` key is `blake3(patch || lockfile || base_image_digest || gate_id || gate_inputs_digest || gate_impl_hash)` but it deliberately *omits* the `grype` vuln-DB digest from the cache key for the Build/Install/Test gates and segregates CVE-delta as a "different cache-key shape." That segregation is the bug. A patch's *Test* result depends on transitively-resolved registry tarballs whose ground truth changes when registry mirror state changes — but the design pins only `registry_mirror_digest` inside the lockfile resolver (Phase 3), not in the Phase 5 verdict cache. If the npm registry serves a `latest`-resolved transitive dep differently between retry-1 and retry-2 (typo-squat takedown, yanked version, mirror swap) the Test verdict cached at retry-1 is wrong on the next workflow. The design says "passing gates whose inputs didn't change hit cache" — but the inputs the cache sees are not the inputs that produced the verdict.
   **Why it matters:** A "warm" verdict cache serves stale "pass" verdicts. Phase 13's cost dashboard will show savings; production will ship CVEs.
   **Where:** §Architecture `GateVerdictCache`, §Components `GateVerdictCache.key_for`, §Data flow step 2 ("five hits").

2. **Problem:** The Install→Test snapshot-sharing optimization (saves ~15–25 s on Test gate) is keyed on `(patch_blake3, lockfile_blake3)` and claimed read-only. But `npm test` *writes* (jest coverage outputs, `~/.npm/_cacache`, `/tmp` mutations, Node's V8 code-cache). The design says "read-only mount inside the Test VM" — a read-only mount of `node_modules` does not buy isolation if the test runner needs to write *anywhere* under that tree (e.g., `node_modules/.cache/`, which Babel, jest, webpack, and SWC all use). Either you make the layer copy-on-write (defeats the perf claim — you pay the upper-layer materialization), or tests genuinely-read-only fail mysteriously on real fixtures.
   **Why it matters:** The 15–25 s savings is the largest single perf claim in §Resource & cost profile. If it doesn't hold on real Node test suites, p50 cold goes from ~85 s to ~110 s and Goal 1 (24 cold workflows/hour) misses.
   **Where:** §Components `RootfsCache + WarmPool` last paragraph, §Risks risk-2.

3. **Problem:** Goal 6 says "Re-run of an identical patch on an identical fixture: 100% cache hit; 0 microVM boots." But Goal 11 measures `runtime_trace` as one of the six gates. The runtime trace's "stable vs. Phase 2 baseline" property depends on the *kernel version inside the rootfs*. The design rebakes rootfs per `(base_image_digest, node_major, fixture_class)` — there is no `kernel_digest` in the rootfs cache key, even though §Failure modes calls out "Firecracker vmlinux mismatch (rootfs built against newer kernel)." So after a `vmlinux` bump, every cached `runtime_trace` verdict is stale, but the verdict cache happily serves the prior pass.
   **Why it matters:** RuntimeTrace is *the* signal that detects "the patch added a new shell invocation." Caching that against a no-longer-relevant kernel is a silent failure of the gate's reason to exist.
   **Where:** §Components `GateVerdictCache`, §Failure modes row 1, gate type `runtime_trace.py` definition.

4. **Problem:** §Risks risk-1 acknowledges Firecracker hard-pin on Linux/CI is "a partial pre-emption of ADR-0019" and §Open questions #2 asks the synth to choose. The design then commits its entire performance budget to Firecracker (every number in §Goals 3, 4, 9, 10, 12 assumes snapshot-resume). On DinD-on-macOS the design admits the WarmPool "degrades to cold-boot mode" — that's not degradation, that's "the entire perf model evaporates." The design has no fallback target for the macOS path; it just shrugs. This means the perf design has no defensible perf claims for ~50% of the operator surface (developer laptops).
   **Why it matters:** The synthesizer cannot use these numbers as gate criteria. There is no committed cold-DinD perf budget anywhere in the doc.
   **Where:** §Goals row "DinD on macOS: ≤ 12 s," §Risks risk-1, §Open questions #2.

5. **Problem:** The `SignalAggregator` is "strict-AND over objective signals only" — but the design enumerates *six gates* (Build, Install, Test, Policy, RuntimeTrace, CVE-delta). ADR-0008 lists seven signal categories, and Phase 3's strict-AND `TrustScorer` already exists and consumes a different signal set (build, install, test, prove-it). The design says "Phase 3's `TrustScorer` already exists ... and is preserved" but also says `SignalAggregator.aggregate(ledger) -> TrustSignals`. There are two strict-AND scorers in the same pipeline: Phase 5's `SignalAggregator` and Phase 3's `TrustScorer`. Which one's `passed` field gates the workflow? The §Data flow says aggregator returns `passed=True` and the workflow finishes — Phase 3's `TrustScorer` is never re-invoked. So the design quietly replaces Phase 3's scorer. That is an edit, not an addition.
   **Why it matters:** Violates "extension by addition" (load-bearing commitment §2.5). Also: if Phase 5 ships its own scorer, then Phase 6's LangGraph conditional_edge has two scorer types to wrap and no clarity on which is canonical.
   **Where:** §Components `SignalAggregator`, §Data flow step 5, §Acknowledged blind spots.

6. **Problem:** §Goals row 12 ("retry-2 ≤ 110% of retry-1 wall-clock; retry-3 ≤ 115%") is a target the cache will pass *trivially* on green-path fixtures (where passing gates cache and only the failing gate re-runs). The number is meaningless because no fixture in the test suite contains the actual hard case — retry-1 fails on Test, retry-2 patches differently, retry-3 fails on a different gate. The §Test plan exit criterion ("retry-1 fails on Test, retry-2 passes") demonstrates only the favorable shape. There is no test where the failing gate *moves* between retries, which is the case where the cache shape matters.
   **Why it matters:** The perf targets are gameable by the chosen fixture. The synth should not treat them as honest.
   **Where:** §Goals row 12, §Test plan integration tests.

### Hidden assumptions

1. **Assumption:** "Same patch_blake3 means same Install result." The design uses `patch_blake3` + `lockfile_blake3` as the key for snapshot reuse and for verdict caching.
   **What breaks if it's wrong:** A patch that touches a `.npmrc`, `.node-version`, `node-gyp` build descriptor, or `package.json#engines` changes Install behavior but not the patch bytes' hash (if those files are *unmodified* by the patch but read by `npm ci`). Two workflows on two repos with the same patch + lockfile but different `.npmrc` configurations get the same verdict.

2. **Assumption:** "Cached verdicts are auditable on cache hit." The design says the cache hit "emits an audit.cache_replay event referencing the original BLAKE3-chained audit entry."
   **What breaks if it's wrong:** The Phase 11 PR evidence bundle needs to show *the actual signals from this workflow*, not a pointer to a historical entry. A merger looking at the PR cannot run a one-shot sandbox replay if the original evidence dir was GC'd at the 14-day boundary the design specifies. "Audit-chain extension" without preserved evidence is a citation to a deleted source.

3. **Assumption:** "Four concurrent gate slots per worker is safe with 1 GB Firecracker VMs."
   **What breaks if it's wrong:** §Resource & cost profile says 3.0 GB worker ceiling with "2 concurrent active VMs × 1 GB each." Then §Architecture says "4 concurrent gate slots." 4 × 1 GB + orchestrator 200 MB + chromadb 400 MB + RootfsCache 150 MB = 4.75 GB. The ceiling number contradicts the slot count. Whichever the synth picks, the other is wrong.

### Things this design missed that a different lens caught

- **Threat model.** Performance never names the adversary. The security design's Phase 5 threat model says this is the first phase that executes attacker-influenced code — performance treats `npm ci` like a benign tool invocation. The shared `node_modules` snapshot optimization across Install→Test is unimaginable under the security threat model and the perf design never acknowledges this trade.
- **No-credentials-in-sandbox.** Best-practices and security both call out the "no creds in the sandbox env" invariant; performance's `SandboxClient.exec(env=Mapping[str,str])` interface accepts arbitrary env — there is nothing in the contract forbidding the orchestrator from passing `ANTHROPIC_API_KEY`.
- **Operator surface / config.** Best-practices ships `codegenie sandbox {health,inspect,gc}` and a `SandboxHealthProbe` as the "B2 analog." Performance ships *no operator CLI* and no health probe. On a cold machine, the first sandbox failure is a stack trace.
- **YAML gate catalog.** Both other designs externalize gate definitions to data; performance bakes the six gate types into Python files. Adding a seventh gate (Phase 7 distroless work) is a code edit, not data — that violates extension-by-addition.

---

## Attacks on the security-first design

### Concrete problems

1. **Problem:** The design contradicts the roadmap on Docker-in-Docker for macOS dev and admits it: "I propose macOS gates run inside a Lima-managed Firecracker-or-gVisor VM" and "operators on macOS pay a Lima VM cost — non-negotiable." This makes Phase 5 *unrunnable on developer laptops without operator-side platform work*. The exit criterion in roadmap.md says "Local dev (including macOS): Docker-in-Docker, since it is the portable choice" — security explicitly throws this out. The `--unsafe-shared-kernel-gates` flag is the only escape and the design says verdicts produced under it are tainted forever. Net effect: a developer on a fresh MacBook cannot reproduce a CI gate failure locally without installing Lima + a microVM stack.
   **Why it matters:** Phase 6 (the next phase) tests the gate loop with `interrupt()` + checkpointer on developer laptops. If gates need Lima to run, Phase 6's tests need Lima to run. Phase 7 (distroless migration, *the second task class* and the test of extension-by-addition) needs gates to run during local development of the new probes. The security design's posture stalls every phase 6+.
   **Where:** §Lens summary "Contradiction-to-roadmap surfaced," §Goals item 1, §Risks risk-2, §Open questions #1.

2. **Problem:** The `gate-control daemon` is a separate process (`codegenie-gated` as a systemd / launchd unit) communicating over `AF_UNIX` with per-orchestrator-process HMAC keys. The design lists this under "components" without acknowledging that a daemon adds an entirely new failure mode the orchestrator never had: *the daemon must be running before any gate runs*. The §Failure modes table has a row for "Docker daemon unreachable" but not "codegenie-gated unreachable" or "codegenie-gated version-skew with orchestrator." Phase 5 was supposed to be a thin wrapper around an existing chokepoint; instead it ships its own OS-level service.
   **Why it matters:** Phase 5 is the foundation Phase 6's state machine consumes. Phase 6 assumes the gate is a function call; the security design makes it an out-of-process RPC to a systemd unit. Phase 6's tests now require a fixture that boots a daemon.
   **Where:** §Components "Gate-control daemon" entry, §Architecture diagram.

3. **Problem:** §Goals item 6 specifies *eight* strict-AND signals (build, tests, delta_test_count, sast, cve_delta, new_shell, new_endpoint, trace_coverage). One is `tests.delta_test_count == 0` — "the gate runs the pre-patch test inventory, not the post-patch one." This *forbids the LLM from adding a test that proves the fix*, which is a standard, legitimate engineering practice and is required by Phase 11's PR convention ("the agent ships tests proving the fix"). The §Open questions #4 admits the trade. Phase 4's exit criterion is "solves a breaking-change vuln end-to-end" — a major-version bump with API changes often legitimately removes/renames tests in the same patch. Phase 5 ships a gate that fails Phase 4's exit-criterion fixture.
   **Why it matters:** This forces every Phase 4 outcome to either fail Phase 5 or escalate to human review. The "three retries" loop becomes "always three retries then escalate."
   **Where:** §Goals item 6, §Threat model "Prompt-injection-pivoted adversary," §Open questions #4.

4. **Problem:** SAST is added to the gate via `semgrep ci --config /sandbox/semgrep-ruleset@<pinned>` baked into the rootfs. Phase 5 of the roadmap does *not* include SAST — the roadmap says "build/test/runtime gates." Phase 12 owns "Stage 4 validation depth" which is where contract testing and deeper validation live; ADR-0008 lists "SAST/DAST findings" as a signal but does not commit it to Phase 5. The security design quietly imports a Phase 12 deliverable into Phase 5 because "we're already running stuff in the microVM." This adds a maintenance burden (semgrep ruleset authorship, ruleset versioning, false-positive triage) the phase scope did not budget.
   **Why it matters:** Scope creep. Phase 5's exit criterion (per roadmap) is the three-retry loop demonstration. Adding SAST to the gate adds a whole new false-positive workflow the design has no plan for.
   **Where:** §Architecture ASCII workload step 4, §Goals item 6, §Components "microVM rootfs image."

5. **Problem:** The "ephemeral microVM per gate, no warm pool" decision (§Goals item 7) combined with "every Phase 5 gate boots its own microVM" produces *three cold microVM boots per workflow* for the vuln remediation pipeline (Build/Install/Test as three gates), then up to three retries = nine cold boots worst case. At ~150 ms Firecracker × 9 = 1.35 s — fine; at ~1.5 s gVisor on Lima × 9 = 13.5 s; at "3–10 s nested QEMU" × 9 = up to 90 s of boot overhead alone. The §Resource & cost profile's "p95: 200s" buries this. The Phase 6 LangGraph state machine adds `interrupt()` plumbing on top — every state transition is now a fresh microVM. Phase 5's "Cold-only in Phase 5 (no warm pool)" choice doesn't show up as a constraint in the perf budget.
   **Why it matters:** The hard "no warm pool ever" stance forces Phase 6 / Phase 9 (Temporal) to ship a warm pool that *invalidates* Phase 5's security model. The "no reuse" guarantee held by ADR-0012 §33 (every gate clean) is preserved only as long as no later phase needs throughput.
   **Where:** §Goals item 7, §Resource & cost profile, §Acknowledged blind spots first bullet.

6. **Problem:** The "pre-patch test inventory is signed by the orchestrator before the gate; gate refuses to run if the in-VM test discovery returns a different set." The signing key lives on the orchestrator. The verifying logic lives inside the microVM init. If the microVM is the untrusted zone and the in-VM init is the only thing trusted with the HMAC key (§Lens summary, "in-VM HMAC key held by init, unreachable by the workload"), then a *test-inventory tampering check inside the microVM* is being performed by code that the design itself classifies as semi-trusted at best. Either the check happens *outside* the VM (you mounted the post-patch tree on the host — defeats isolation), or inside (verifier shares fate with attacker). The design is silent on which.
   **Why it matters:** The single most adversarial-resistant claim in the design ("LLM can't disable tests because the gate runs the pre-patch inventory") has no clean implementation path. §Failure modes row "LLM-produced patch deliberately disables a gate" claims this works; §Acknowledged blind spots last bullet admits "if the workload exploits init... the HMAC key leaks."
   **Where:** §Goals item 6 `tests.delta_test_count`, §Failure modes "LLM-produced patch deliberately disables a gate," §Acknowledged blind spots.

### Hidden assumptions

1. **Assumption:** "Host-side eBPF will be available on every sandbox host."
   **What breaks if it's wrong:** §Goals item 6 requires `runtime_trace.coverage_ok == true` as one of the eight strict-AND signals; §Threat model "Runtime-trace tampering adversary" specifies host-side eBPF as the *trusted* trace source. macOS hosts have no eBPF. Lima-on-macOS has no privileged eBPF access into the inner microVM. The design admits this in §Risks risk-3 ("trace coverage check fires `runtime_trace.coverage_ok == false`; strict-AND treats it as a hard fail") — which means: every gate on every macOS dev machine fails by default. The design intends this; the operator experience is "no Phase 5 gate ever passes on a developer laptop." That is not a workable dev loop.

2. **Assumption:** "The npm registry tarball SHA can be verified against the lockfile `integrity` field by the egress proxy before the bytes reach the microVM."
   **What breaks if it's wrong:** §Threat model "Cache-poisoning adversary" says "registry pull through a verifying proxy that asserts the tarball SHA against the lockfile's `integrity` field." `npm ci` already does this check inside the workload. Doing it again at the proxy means the proxy must understand npm's `integrity` field format and trust a *lockfile inside the microVM* (which is attacker-influenced bytes from the patch). The proxy is being asked to enforce the integrity field of a file whose authority it cannot independently verify.

3. **Assumption:** "Per-gate fresh microVM with no persistent state means cache-poisoning is impossible across workflows."
   **What breaks if it's wrong:** The design says "build-cache scoped per-workflow per-run (no shared upper layer across workflows)" but also says base-image pulls go through `docker.io` / `cgr.dev`. The base image is the cross-workflow shared state. A poisoned Chainguard base image (compromised maintainer, dependency confusion in the registry, takedown-and-replace by a typo-squatter on a digest that resolves at boot) compromises every gate of every workflow. The 7-day patch SLA is real but doesn't help in the 0-7 day window.

### Things this design missed

- **Cache for verdicts.** Performance shows that retries with one gate failing produce 5/6 gates whose inputs haven't changed. Security insists on fresh microVMs and no verdict cache. So every retry pays *every* gate's full cost, not just the failing one. ADR-0014 specifies retries are bounded to 3, but at 3× the wall-clock and 3× the cost of every gate, the per-workflow budget (ADR-0025 — deferred to Phase 13 but the cap is real) is materially worse than necessary.
- **The `ObjectiveSignals` Pydantic model with `extra="forbid"` is one of the strongest ADR-0008 enforcements proposed.** Best-practices also forbids `confidence` but does it in `GateSignal.details: dict[str, primitive]` — a `details["confidence"]` key bypasses the static check. Security catches this; best-practices doesn't.
- **YAML gate catalog.** Security bakes gates into Python (the gate-control daemon dispatches to typed gate handlers). Adding a Phase 7 distroless gate (BaseImageProbe, ShellInvocationTraceProbe) means modifying the daemon. Best-practices' YAML catalog is the better extension-by-addition shape.
- **Operator CLI.** Best-practices ships `codegenie sandbox {health,inspect,gc}` plus a `SandboxHealthProbe` (an ADR-0007 honest-confidence input). Security ships `codegenie sandbox provision` and `codegenie sandbox up/status` — different surface, fewer subcommands, no health probe.

---

## Attacks on the best-practices design

### Concrete problems

1. **Problem:** §Goals row 1 says "0 deps for Firecracker stub (it's an out-of-process binary check)" and §Components 4 says "`FirecrackerClient` ... raises `BackendNotAvailable` ... unless `--firecracker-experimental` is set on the CLI AND the host has KVM + the pinned firecracker binary digest." So Phase 5's Firecracker support is *a stub that fails by default everywhere*. The exit criterion the design claims (§Goals row 14) is met entirely on DiD. ADR-0019 explicitly names "cold-start latency tolerance" and "operational experience" as the evidence Phase 5 should generate. The stub generates none of it. Phase 16 will revisit ADR-0019 with zero new data from the phase that was supposed to produce data.
   **Why it matters:** The phase exists in part to start producing the evidence ADR-0019 needs. Best-practices ships a stub instead of an experiment.
   **Where:** §Goals row 8, §Components 4, §Open questions #1, §Risks risk-3 (admits the stub bit-rots without a weekly cron).

2. **Problem:** `Gate` is `ABC`, `SandboxClient` is `Protocol`. The justification (§Components 1) is "composition over inheritance — backends are duck-typed via `runtime_checkable`." Then `Gate` is an ABC because... it has subclasses (`StrictAndGate`). Both shapes are used. Two different Python idioms for two contracts in the same package, with the design's own §Conventions honored claiming "best-practices rule 4: composition over inheritance." Pick one. The codebase already has a `Probe` ABC (Phase 1) and a `RecipeEngine` ABC (Phase 3); adding a Protocol next to them violates §"Match the codebase's conventions" (CLAUDE.md global rule 11).
   **Why it matters:** Convention drift inside the same PR. Phase 7 distroless will copy whichever idiom it sees first and now both idioms are sanctioned.
   **Where:** §Components 1 ("Why Protocol over ABC"), §Components 5 ("`Gate` ABC"), §Conventions honored item 4.

3. **Problem:** `GateSignal.details: dict[str, str | int | bool]` — explicitly a typed dict with primitive values, no nested structure, ≤ 8 keys. The four signal collectors emit `details={"failing_tests":3, "first_failure":"auth/jwt.test.ts: ..."}` (build/test) and the trace collector emits free strings naming "new entries." There is *nothing* in this schema that prevents a collector from emitting `details["confidence"] = 0.87` or `details["llm_says_ok"] = True`. The security design forbids these field names statically with a CI test on the Pydantic model; best-practices forbids them only in prose. ADR-0008 is enforced by convention, not by code.
   **Why it matters:** ADR-0008 is the load-bearing commitment for the trust score. A test introduced in Phase 6 (or Phase 15 recipe authoring) can slip a `confidence` value into `details` and the type system accepts it.
   **Where:** §Components 2 `GateSignal` definition, §Conventions honored item 2.

4. **Problem:** The "flaky-timer-node" fixture for the exit-criterion test (§Test plan, `test_stage6_retry_recovers.py`) is described as: "a `pytest_dynamic_test_order` fixture rewrites a flag inside the sandbox between attempts via a sidecar marker file written by the gate YAML's attempt-2 `cmd`." This is *the test demonstrating the central exit criterion* of the phase (ADR-0014's three-retry loop) — and it's a fixture whose attempt-1-fails-attempt-2-passes property is *engineered by a sidecar marker file*, not by anything resembling the real production case (where retry-2 fixes the patch via Phase 4's `RagLlmEngine.apply`). The fixture doesn't exercise the retry loop's *actual feedback path* — the `prior_failure_summary` field going into Phase 4 and producing a different patch. It exercises the loop's *control flow* only.
   **Why it matters:** The exit-criterion test cannot detect a regression in the retry feedback semantics. CLAUDE.md global rule 9: "every test must encode WHY the behavior matters, not just WHAT it does." A test that hardcodes the pass-on-2 outcome via a marker file doesn't encode why retries matter.
   **Where:** §Test plan integration tests `test_stage6_retry_recovers.py`, §Data flow step 8.

5. **Problem:** §Components 3 `DockerInDockerClient` admits subprocess use ("subprocess is allowed only inside `did/build.py` for `docker buildx build`...") because "the Python SDK's build progress streaming is awkward." Phase 1's `run_in_sandbox` chokepoint and Phase 3's lockfile resolver both explicitly avoid subprocess shelling for the same operations. The design carves out a single-file exception with no test boundary preventing that exception from spreading. The "one chokepoint" promised by Phase 0/1/2/3 conventions is now "two chokepoints, one of them shells out."
   **Why it matters:** The very first subprocess exception always grows. By Phase 9 there will be three exceptions and the chokepoint property is gone.
   **Where:** §Components 3 internal design third bullet.

6. **Problem:** §Components 9 "Signal collectors — four functions" includes `collect_policy_signal(run: SandboxRun, policy_yaml: Path) -> GateSignal`. The `policy_yaml` argument is *read from somewhere*. The design never says where — `~/.config/codegenie/policy.yaml`? In the repo (`.codegenie/policy.yaml`)? Baked into the gate-catalog YAML? If it's in-repo, it's attacker-influenced (the LLM-produced patch can modify it). If it's user-config, it's not portable across CI/dev. If it's baked, the operator can't tune it without an ADR amendment. The design silently leaves a real attack surface open by not specifying the trust source.
   **Why it matters:** Security caught this and pins SAST config to the digest-pinned rootfs (so the patch can't change it). Best-practices leaves the policy source unspecified — a Phase 11 PR can include `.codegenie/policy.yaml` modifications and the gate would honor them.
   **Where:** §Components 9 `collect_policy_signal` interface, §Failure modes "Policy gate fails."

### Hidden assumptions

1. **Assumption:** "strace is the boring choice that works on macOS DiD and Linux CI" (§Components 3 trace capture).
   **What breaks if it's wrong:** strace under Docker on macOS requires the `SYS_PTRACE` capability inside the container. Docker Desktop on macOS runs containers inside its own Linux VM, and `SYS_PTRACE` on processes in another container's namespace doesn't work out of the box without `--cap-add=SYS_PTRACE`, `--security-opt seccomp=unconfined`, and the docker version supporting it. The design says "the boring choice that works on macOS DiD" — it does not work without runtime config the design never lists.

2. **Assumption:** "Phase 5 ships no LLM call. Fence CI extended" (§Goals row 15).
   **What breaks if it's wrong:** The §Data flow step 8 says "next `SandboxSpecBuilder` call sees `prior_attempts=[Attempt(1)]` and (per `stage6_validate.yaml`) chooses a more verbose `cmd` for attempt 2." That re-prompts *Phase 4's `RagLlmEngine.apply`* with `prior_attempts` (§Components 6 internal design). Phase 4's `RagLlmEngine` calls Anthropic. Phase 5 does not directly invoke an LLM but each retry triggers an LLM call in Phase 4. The "tokens per run: 0" claim is honest only at the package boundary — every workflow that exercises retry-1-fail spends Phase 4 tokens × 2. Phase 13's per-workflow cap (ADR-0025) is the constraint, and Phase 5 will hit it routinely without admitting that Phase 5 is the driver.

3. **Assumption:** "Two ABCs is the public surface; adding a fifth signal is a fifth file" (§Goals row 1, §Components 9 tradeoffs).
   **What breaks if it's wrong:** Phase 7's distroless task class needs new signal kinds (base-image-vulnerability count, shell-binary-presence). Adding them requires extending `GateSignal.kind: Literal["build","tests","trace","policy"]` to include `"baseimage"` and `"shell_presence"`. That's editing a Literal type in a shared module, which is an edit, not addition. Best-practices claims extension-by-addition; this Literal makes the kind enum closed.

### Things this design missed

- **Threat model.** Best-practices spends one bullet in §Acknowledged blind spots on "security depth" — "we trust the DiD/Firecracker primitive. No seccomp profile authoring in Phase 5." There is no adversary named, no asset list, no isolation requirement. The security design's full threat model — orchestrator credentials, audit-chain integrity, runtime-trace tampering, prompt-injection-in-retry-feedback — is entirely absent from best-practices. Phase 5 is the *first phase to execute LLM-produced code*; that property does not show up here.
- **Performance.** §Goals rows 9–12 commit to latency budgets without a verdict cache, without snapshot reuse, without parallelism. §Acknowledged blind spots admits this. The result is honest but every retry pays full freight. Best-practices accepts the cost without surfacing what it would take to fix later.
- **Egress restriction depth.** Best-practices' `network_policy.yaml` produces iptables rules; the security design adds an in-VM egress proxy + byte cap + rate cap as defense-in-depth. A patch with a `postinstall` that calls out to `registry.npmjs.org` (an allowed domain) and exfiltrates 50 MB of data is invisible to best-practices' allowlist and visible to security's byte cap.
- **No-credentials-in-sandbox enforcement.** Best-practices' `SandboxSpec.env: dict[str, str]` accepts any env; the comment says "validated allowlist (PATH, NPM_CONFIG_*, NODE_ENV...)" but no code is shown enforcing the allowlist. The security design refuses env inheritance entirely.

---

## Cross-design observations

### Where do the three disagree?

| Dimension | Performance picks | Security picks | Best-practices picks | What's at stake |
|---|---|---|---|---|
| Sandbox stack default | Firecracker on Linux/CI, DinD on macOS | Firecracker on Linux/CI, gVisor-via-Lima on macOS (no shared-kernel anywhere) | DinD everywhere; Firecracker as a stub | macOS dev loop usability vs. isolation strength vs. ADR-0019 evidence gathering |
| Verdict / signal caching across retries | Content-addressed `GateVerdictCache`; passing gates cache, failing gate re-runs | No verdict cache; every gate fresh microVM every time | No verdict cache (Phase 9 territory) | Wall-clock per retry × cost-per-workflow vs. cache-poisoning surface |
| Snapshot reuse across gates in a workflow | Yes — read-only `node_modules` snapshot Install→Test | No — every gate is its own ephemeral microVM | No — per-gate fresh boot | 15–25 s saved per retry vs. ADR-0012 §33 "every gate starts clean" |
| `node_modules` / build state | Shared (read-only) within workflow | Strictly per-gate | Strictly per-gate | Same as above |
| LLM in retry feedback | Phase 4 replans via `FallbackTier` with failure signals | Phase 4 replans, error log fenced + canary-checked + 8 KB truncated | Phase 4 replans via `prior_attempts` | Token cost vs. prompt-injection-via-error-log surface |
| Gate definition shape | Six gate types as Python files | Eight strict-AND signals enforced in the Pydantic model | Two YAML catalogs (`strict`, `loose`) plus `StrictAndGate` Python class | Extension by addition (Phase 7) vs. type-safety vs. operator tunability |
| Process topology | Single orchestrator process; gates are async tasks | Three processes: orchestrator → `codegenie-gated` daemon → microVM | Single orchestrator process; gates are sync function calls | Operational complexity vs. credential confinement |
| `SignalAggregator` / scorer relationship to Phase 3's `TrustScorer` | Phase 5 ships its own `SignalAggregator` (replaces, doesn't extend) | Phase 5 ships its own typed `ObjectiveSignals` model | Phase 5 *injects new signals into Phase 3's `TrustScorer`* (extends) | "Extension by addition" — which design honors it |
| Test inventory tampering | Not addressed | Pre-patch test inventory signed; in-VM discovery refused if it differs | Not addressed | LLM-disables-test attack vs. legitimate test-addition patches |
| SAST in Phase 5 | No | Yes (semgrep inside the rootfs) | No | Phase 5 scope creep |
| eBPF / strace for runtime trace | strace inside the VM (informational) + (Linux-only) eBPF | Host-side eBPF *required*; in-guest strace informational | strace inside the VM (DiD trace capture) | macOS dev viability |
| Three-retry override flag | Configurable via CLI knob | **No override flag in Phase 5** (strict ADR-0014) | `--max-attempts-override <int>` requires `--operator-ack` | Whether ADR-0014's "configurable" property survives Phase 5 |
| Health probe | None | Implicit via daemon | `SandboxHealthProbe` (ADR-0007 honest-confidence input) | Operator surface; first-failure UX |

### Which disagreement matters most for *this* phase?

**The macOS dev-loop posture is the central conflict.** The roadmap says DinD on macOS is the portable choice; security says shared-kernel Docker is unacceptable for executing LLM-produced code; performance picks DinD and gives it no perf budget; best-practices picks DinD and quietly admits its trace-capture path doesn't actually work without runtime config. Three phases downstream (Phase 6 state machine, Phase 7 distroless task class, Phase 9 Temporal) all assume gates run on developer laptops during local dev. Whatever the synth picks here propagates to those phases. Every other conflict in the table (verdict cache, signal aggregator vs. TrustScorer, gate-control daemon) is downstream of this one — once you know whether macOS gates run in a shared-kernel container or a microVM-in-Lima, the rest of the architecture follows.

The synth must answer: *can Phase 5 ship a dev-loop that runs unmodified on a fresh MacBook?* If yes, security's full posture is unachievable and the threat-model trade is real. If no, Phase 6+ all need a "Lima-up" prerequisite documented and tested.

### Where do all three quietly agree on something questionable?

1. **All three accept that the patch under test is copied into the sandbox in full.** None of the three contemplate that the patch itself can contain a malicious `.gitignore`, a `.git/hooks/post-checkout`, or a `package.json#scripts.preinstall` (Phase 3's `--ignore-scripts` only blocks `install/postinstall`, not `preinstall` or arbitrary scripts invoked by `npm run`). Best-practices `cmd: ["sh","-c","cd /work && npm ci --ignore-scripts && npm test"]` — `npm test` runs arbitrary scripts by design. The shared assumption: "the microVM boundary makes this OK." It does for the orchestrator host. It does *not* for cache-poisoning attacks on the rootfs's persistent npm cache that all three either share (performance), rebake (security), or implicitly accept (best-practices).

2. **All three treat `runtime_trace` as a strict gate signal but none calibrates the baseline.** ADR-0008 says runtime-trace coverage is an objective signal; Phase 2 produces a trace baseline; all three Phase 5 designs diff against it. None addresses *how the baseline is updated* when a legitimate dependency upgrade introduces a new (benign) syscall pattern. Best-practices §Risks risk-4 names this as "trace baseline drift" and defers it to Phase 11. Security treats `coverage_ok==false` as a hard fail without a refresh path. Performance just consumes Phase 2's baseline as given. The shared blind spot: in production, this gate is going to fail benignly often, and the cost is reviewer fatigue (which Phase 11 will absorb without warning).

3. **All three assume Phase 4's `FallbackTier` will accept the failed-gate error log as a clean retry input.** Performance: "re-invoke upstream planner (Phase 4 `FallbackTier`) with the failure signals as context." Security: "fence-wrapped, truncated sandbox error log handed back to Phase 4." Best-practices: "`prior_attempts` appended; `RagLlmEngine` re-invoked." None of the three checked Phase 4's `final-design.md` to confirm `FallbackTier.run(...)` accepts a `prior_attempts: list[AttemptOutcome]` kwarg shape with the *exact* fields each Phase 5 design proposes. Phase 4's exit criterion (a breaking-change vuln solved end-to-end) does not test the prior-attempts path. If Phase 4 has to amend its interface to satisfy Phase 5, Phase 4 ships incomplete.

---

## Roadmap-level critiques

1. **Phase 6 (LangGraph state machine) will not be a thin wrap of Phase 5's coordinator.** Phase 5's roadmap entry says retries land here; Phase 6's roadmap entry says "the deterministic + LLM + sandbox loop is now stitched together as a proper state machine ... conditional edges are the Trust-Aware gates." Performance's `GateCoordinator` is sync-with-bounded-async; security's gate-control daemon is a separate process with HMAC handshakes; best-practices' `GateRunner` is sync. None of the three is a LangGraph node ready to lift unchanged. Phase 6 will either (a) re-implement the retry loop inside LangGraph, leaving Phase 5's coordinator as dead code, or (b) keep Phase 5's coordinator and inject LangGraph `interrupt()` into the middle, which is an edit. Either way, "Phase 6 will wrap `run()` as a single graph node" (performance §Components, §Open questions #4) is wishful — the state machine has more transitions than Phase 5 acknowledges.

2. **Phase 7 distroless task class (the test of extension-by-addition) needs new gates added without editing Phase 5.** Performance's six gate types are Python modules — adding a `BaseImageProbe` gate is a new file but adding a `shell-presence` *signal* is an edit to `SignalAggregator`'s known signal set. Security's `ObjectiveSignals` Pydantic model with `extra="forbid"` *literally cannot* accept a new signal without editing the model. Best-practices' `GateSignal.kind: Literal["build","tests","trace","policy"]` is a closed enum. All three of these violate the "extension by addition" invariant for Phase 7. The phase whose exit criterion is "the diff touches *only* new files" cannot ship against any of these three Phase 5 designs without modification.

3. **ADR-0019 is supposed to remain deferred until production evidence exists.** Performance hard-pins Firecracker on Linux/CI as a "partial pre-emption." Security commits to gVisor on macOS-via-Lima + Firecracker on Linux/CI, which is *two-stack production routing* — explicitly listed as an "option considered" in ADR-0019 but never decided. Best-practices ships a Firecracker stub, generating no evidence. All three either resolve ADR-0019 prematurely or refuse to engage with it. The synth must either honor the deferral (in which case Phase 5 must ship multi-backend test coverage and produce comparable cold-start / cost numbers) or resolve it with new evidence.

4. **Load-bearing commitment §2.5 "extension by addition" is at risk.** Performance ships a new strict-AND scorer that replaces Phase 3's `TrustScorer` (per its own §Data flow). Security ships a new `ObjectiveSignals` typed model that supplants Phase 3's signal set. Best-practices is the only one that injects new signals into Phase 3's existing scorer — and it does so by widening the type, which §Roadmap-level #2 above shows is itself a closed-enum edit. Phase 3 carefully cut a `TrustScorer` seam ("strict-AND objective signals only" with composable signal injection). Phase 5 must extend it, not replace it. The synth needs to enforce this and the best-practices design is the closest to honoring it — but not by a wide margin.

5. **Load-bearing commitment §2.1 "no LLM in the gather pipeline" extends to gates implicitly but is not literally what ADR-0008 says.** ADR-0008 says "Trust score uses objective signals only — no LLM self-confidence." Production design.md §3.1 lists an **LLM Judge persona** (Functional-Equivalence Critic) for Stage 5 Validation "on disagreement when objective signals conflict." All three Phase 5 designs say "no LLM in Phase 5." Security explicitly defers the LLM Judge to "Phase 5+N." Performance says "no LLM at the gate (ADR-0008 invariant)." Best-practices says "no LLM call. Fence CI extended." But the production design's stage-5 persona table *requires* an LLM judge for adjudication. Phase 5 is the phase that introduces sandboxed gates; deferring the LLM-judge persona to a later phase that doesn't exist on the roadmap means the production target has a persona no phase ever ships. This is a roadmap gap, not a phase bug — but Phase 5 is where the synth notices it.

6. **The audit chain extends across Phase 2 → Phase 3 → Phase 4 → Phase 5.** Performance's `GateVerdictCache` emits `audit.cache_replay` events referencing prior chain entries; security's gate-control daemon refuses to advance if the chain head mismatches at startup; best-practices' `RetryLedger` is BLAKE3-chained into the prior chain. All three claim to extend the chain. None has verified that Phase 4's `FallbackTier` audit emissions (Phase 4's `solved_example.duplicate_skipped` events, the `engine_used` stamping, etc.) produce chain entries with the same shape Phase 5 will consume. If Phase 4's chain events don't include the fields Phase 5's chain verification expects, Phase 5 refuses to start.
