# Phase 03 — Vuln remediation: deterministic recipe path: Security-first design

**Lens:** Security — isolation, least privilege, audit, supply chain.
**Designed by:** Security-first design subagent
**Date:** 2026-05-15

## Lens summary

Phase 3 ships the first plugin that actually patches a repository's lockfile and runs `npm install`, plus the universal `(*, *, *)` HITL fallback. Phase 5 — which owns the microVM Trust-Aware gate ([ADR-0012](../../production/adrs/0012-microvm-sandbox-for-trust-gates.md)) — has not shipped. The security-first answer is *not* to defer the work to Phase 5 (the roadmap says Phase 3 ships the working diff) and *not* to silently lean on a weaker sandbox: we lean on the principle that **Phase 3 never executes the patched repository's code on the orchestrator host at all**. The patched diff is *computed* (deterministically, by recipes operating on parsed AST/lockfile data) and `npm install` is run under a tightly-bounded subprocess jail (no postinstall, no scripts, offline mirror, no network egress); the *runtime* validation of the patched repo — `npm test`, `node` actually executing — is **deferred to Phase 5's microVM** and Phase 3 emits a `RequiresSandboxValidation` event the next phase consumes. I optimized for *blast-radius containment* (a compromised CVE feed, a malicious package on the npm mirror, a plugin manifest with attacker-controlled `extends` chains) and for *audit completeness* (every plugin resolution, recipe application, install attempt, file write, and git op is an event-sourced typed record per [ADR-0034](../../production/adrs/0034-event-sourcing-canonical-primitive.md)). I explicitly deprioritized: latency (cold-path npm install with `--ignore-scripts` and an offline cache is slower than a warm `npm install`), recipe authoring ergonomics (recipe authors operate inside a small whitelisted DSL of file-mutation operations, not arbitrary Python), and developer convenience (no editable installs, no relative `extends:` paths, no plugin-loaded environment variables).

## Threat model

### Assets to protect

- **The orchestrator host filesystem** — at Phase 3 there is no microVM yet; the orchestrator is the developer's laptop or a CI runner. Path traversal out of the analyzed repo, or arbitrary file writes via a malicious recipe, must be impossible.
- **The orchestrator's network identity** — Phase 11 will add `git push` and PR-creation credentials, but Phase 3 still runs from a developer machine that holds personal SSH keys, GitHub tokens, and cloud credentials in `~/.aws/`, `~/.config/gh/`, `~/.ssh/`. Any code we run that can read `~/` is a credential-leak vector.
- **The target repository's git state** — branch creation and local commits must not silently overwrite developer work, must not push, must not modify unrelated branches, must not leave uncommitted patch state behind on a crash.
- **The `.codegenie/` audit chain** — the event log must be append-only and tamper-evident. An attacker who can rewrite history can hide a malicious recipe run.
- **The plugin registry itself** — the file tree `plugins/` is *trusted code* loaded at startup. An attacker who lands a malicious plugin via a normal PR has won; this is supply-chain compromise of the project itself. Plugin signing and review discipline are part of the threat model even though they are partially out of scope for the code in this phase.

### Adversaries assumed

1. **A poisoned upstream CVE feed entry.** NVD, GHSA, and OSV are *public* and *adversary-writable* — anyone can file a CVE. We must assume crafted CVE records with malicious URLs, oversized fields, embedded null bytes, JS-injection-shaped strings in human-readable descriptions, and `affected_module` strings containing path-traversal sequences, `..`, glob characters, command-injection characters, and YAML/JSON parser-exploit shapes.
2. **A malicious npm package.** A direct or transitive dependency of the *target repo* may be malicious. Even patched versions can contain malware (the `event-stream` 2018 compromise, `ua-parser-js` 2021, `colors`/`faker` 2022 sabotage events, the ongoing pipeline of typosquats). The patched package we install is, by definition, *new* dependency content we are pulling onto disk.
3. **A compromised or malicious plugin landing via PR.** The plugin loader executes Python at import time. A plugin's `extends` chain transitively loads parent plugins. A "vendor-friendly" plugin authored by an outside contributor can pivot the gather pipeline if we treat plugins as untyped imports.
4. **A malicious recipe.** Recipes are the deterministic transforms; a recipe that says "replace `package.json` with `<attacker-payload>`" must be impossible by *construction*, not by review.
5. **Repo content as adversarial input.** Phase 3 reads `package.json`, `package-lock.json`, `.npmrc`, `.yarnrc.yml`, `node_modules/**/package.json`. A repo with a malicious `.npmrc` containing `registry=http://attacker/` is the *standard* npm credential-leak attack and we must neutralize it.
6. **Prompt-injection-style content in repo files.** Phase 3 has *no LLM in the loop* but the audit log and the HITL escalation pass repo content to humans; injection-shaped strings (zero-width chars, ANSI escapes, malicious unicode bidi, file-rendering tricks) must be sanitized before they hit any reviewer-facing surface.

### Attack surfaces specific to this phase

1. **CVE feed ingestion.** Parsers for NVD JSON 2.0, GHSA, OSV. Three different schemas, three different parsing surfaces.
2. **Plugin loading.** `plugins/vulnerability-remediation--node--npm/` and `plugins/universal--*--*/`. Python imports at startup; manifest YAML parsing; `extends` chain resolution.
3. **OpenRewrite recipe execution.** Recipes run inside a JVM. The JVM is a large, network-capable attack surface.
4. **`npm install` execution.** Phase 3's most dangerous primitive. npm's `preinstall`/`install`/`postinstall` scripts are arbitrary shell code from arbitrary packages.
5. **Git operations.** `git checkout -b`, `git add`, `git commit`. Even local-only, these mutate filesystem and refs in a directory we do not own.
6. **Filesystem writes.** Patched `package.json`, patched `package-lock.json`, recipe-produced diffs, audit log appends, event sourcing payloads.
7. **HITL escalation rendering.** The universal `(*, *, *)` fallback produces a human-readable artifact for triage; that content is partly attacker-controlled.

### Trust boundaries

```
                  ┌─────────────────────────────────────────────────────────────────┐
                  │ TRUSTED CORE (Python orchestrator process)                       │
                  │  - codegenie.cli                                                 │
                  │  - codegenie.events (append-only Postgres-ready local log)      │
                  │  - codegenie.plugin.registry (after signature & schema check)    │
                  │  - codegenie.fs.SandboxedPath (smart-constructor; jailed)        │
                  │  - codegenie.cap (Capability tokens)                             │
                  └─────────────────────────────────────────────────────────────────┘
                          ▲ TB-A: capability tokens cross this line         ▲
                          │ (mintable only via narrow factories)            │
  ┌───────────────────────┴──────┐    ┌─────────────────────────────────────┴────────┐
  │ SEMI-TRUSTED — Plugin code   │    │ SEMI-TRUSTED — In-process JVM (OpenRewrite)  │
  │  - executes Python in proc   │    │  - separate child process                     │
  │  - bounded by Capability     │    │  - no network egress (firewalled)             │
  │  - validated manifest, signed│    │  - no filesystem outside copy-in dir          │
  │    `extends` chain           │    │  - bwrap/sandbox-exec wrapped on Linux/macOS  │
  └──────────────────────────────┘    └───────────────────────────────────────────────┘
                          ▲ TB-B: copy-in/out is the only file boundary
                          │
  ┌───────────────────────┴───────────────────────────────────────────────────────┐
  │ UNTRUSTED — npm install subprocess                                              │
  │  - runs under user nobody on Linux / dedicated UID on macOS                     │
  │  - no postinstall scripts (--ignore-scripts everywhere, enforced)                │
  │  - bwrap/sandbox-exec: read-only $HOME, no /etc, only the copy-in repo R/W       │
  │  - egress firewalled to a single configured registry mirror                      │
  │  - pids/memory/time/disk-quota capped                                            │
  │  - exit code + stdout/stderr captured as typed events                            │
  └─────────────────────────────────────────────────────────────────────────────────┘
                          ▲ TB-C: subprocess output is parsed by smart constructors;
                          │ nothing is `exec`'d on return.
  ┌───────────────────────┴────────────────────────────────────────────────────────┐
  │ UNTRUSTED — repository content                                                   │
  │  - `package.json`, `package-lock.json`, `.npmrc` (the last one is neutralized)   │
  │  - read through SandboxedPath; never written outside the repo jail               │
  │  - all read I/O size-capped; YAML reads use safe_load only                       │
  └────────────────────────────────────────────────────────────────────────────────┘
                          ▲ TB-D: CVE feed input crosses this line into the core
                          │ via the smart-constructor `CveAdvisory.parse(...)`.
  ┌───────────────────────┴────────────────────────────────────────────────────────┐
  │ UNTRUSTED — public CVE feeds (NVD, GHSA, OSV)                                    │
  │  - fetched into `.codegenie/cve-cache/` (read-only after fetch)                  │
  │  - JSON parsed with size cap, depth cap, integer cap                             │
  │  - every field passes through a typed parser; raw text never reaches a shell      │
  └────────────────────────────────────────────────────────────────────────────────┘
```

The boundaries are deliberately concentric: TB-D (CVE feed in) → TB-C (subprocess out) → TB-B (JVM out) → TB-A (capability tokens in). An attacker pivoting from TB-D must defeat the smart constructor (TB-D), then influence a recipe selection (TB-A capability needed), then escape the JVM jail (TB-B), then escape the npm install jail (TB-C), to touch the host. No single layer is the only defense — each layer is described below in terms of what it costs the attacker to defeat.

## Goals (concrete, measurable)

- **Sandbox-escape risk: TB-C and TB-B are containment, not isolation.** The microVM ships in Phase 5; Phase 3's gap is closed by *not running test code at all in this phase*. The objective: an attacker who plants `event-stream`-style malware in a patched dependency's postinstall script gets *zero shell execution* on the Phase 3 orchestrator host. Measured by: a deliberate-malware test fixture that fails the build if any of `~/.codegenie/test-canary-files/` are written/read by the install subprocess.
- **Credential blast radius if the orchestrator is compromised:** at Phase 3, *zero remote credentials are present in the codebase or process environment*. The plugin loader strips known credential-env-vars before plugin imports; the npm install subprocess inherits *no* environment except an explicit `PATH=/usr/bin:/bin` and `npm_config_*` allowlist. Measured by: env-allowlist test, plus a `grep -R` audit-test for `os.environ` reads anywhere outside `codegenie.config.env`.
- **Audit completeness target:** **every** plugin resolution, recipe selection, recipe application, install attempt, file mutation, branch creation, and HITL escalation emits a typed event (ADR-0034). An offline replay of `.codegenie/events/*.jsonl` must reconstruct the full set of patch changes byte-for-byte. Measured by: a replay test that takes a recorded session, replays the events, and asserts the working tree is bit-identical to the recorded post-state.
- **Allowed network egress (orchestrator + all subprocesses combined):**
  - CVE feeds: only on explicit `codegenie cve-feed sync` invocation; allowlisted hostnames (`nvd.nist.gov`, `api.github.com`/advisories, `osv.dev`); HTTPS only; certificate pinning.
  - npm install: outbound to a single configured registry mirror (default: deny all; user must set `--npm-registry-mirror` or run with a pre-populated offline cache).
  - JVM (OpenRewrite): deny all egress (recipe metadata bundled with the recipe; no Maven Central lookup at recipe execution time).
  - Everything else: deny.
- **Determinism guarantee:** running the same plugin against the same repo at the same content-addressed cache state produces the same diff and the same event sequence (modulo timestamps and run-id). Measured by: byte-equal diff across two consecutive runs in CI, after redacting timestamps/IDs.
- **HITL escalation never silently fails.** The universal `(*, *, *)` fallback emits `requires_human_review` with a fully-sanitized context payload; the workflow halts (does not retry, does not auto-resolve). Measured by: an integration test where the plugin registry contains *only* the universal fallback, and the run produces exactly one `requires_human_review` event and exits non-zero with a documented exit code.

## Architecture

```
                          codegenie vuln <repo-path> --cve <id>
                                       │
                                       ▼
                ┌──────────────────────────────────────────────┐
                │ codegenie.cli.vuln                            │
                │  - parses CLI args via Pydantic               │
                │  - resolves <repo-path> through SandboxedPath │
                │  - mints WorkflowId (UUID, recorded in event) │
                └──────────────────────────────────────────────┘
                                       │
                                       ▼  [TB-D crossing: CVE id → CveAdvisory]
                ┌──────────────────────────────────────────────┐
                │ codegenie.cve.AdvisoryStore                    │
                │  - reads .codegenie/cve-cache/{nvd,ghsa,osv}/ │
                │  - parses with smart-constructor               │
                │  - returns CveAdvisory (frozen, typed)         │
                │  - emits CveAdvisoryLoaded event              │
                └──────────────────────────────────────────────┘
                                       │
                                       ▼
                ┌──────────────────────────────────────────────┐
                │ codegenie.gather.RepoContextLoader            │
                │  - reads existing repo-context.yaml (Phase 2) │
                │  - validates schema; refuses partial/missing  │
                │  - emits RepoContextLoaded event              │
                └──────────────────────────────────────────────┘
                                       │
                                       ▼
                ┌──────────────────────────────────────────────┐
                │ codegenie.plugin.Resolver                     │
                │  - reads plugins/ from in-tree filesystem     │
                │  - validates plugin.yaml (Pydantic)           │
                │  - SIGNATURE check (Phase-3 simple: SHA256    │
                │    of plugin dir tree must match an entry in  │
                │    plugins/PLUGINS.lock checked into the repo)│
                │  - resolves extends chain (cycles refused)    │
                │  - matches (task=vuln, lang, build) tuple     │
                │  - returns ResolvedPlugin or                  │
                │    UniversalFallbackPlugin                    │
                │  - emits PluginResolved event                 │
                └──────────────────────────────────────────────┘
                                       │
                                       ▼  [TB-A crossing: capability mint]
                ┌──────────────────────────────────────────────┐
                │ codegenie.exec.CapabilityMint                  │
                │  - mints exactly the capabilities this plugin │
                │    declared in plugin.yaml capabilities-needed:│
                │     - FsReadWriteCapability(jail=repo_path)    │
                │     - NpmInstallCapability(registry=allowlist) │
                │     - GitLocalOpsCapability(repo=repo_path)    │
                │  - capabilities are unforgeable tokens;        │
                │    no plugin can construct them                │
                └──────────────────────────────────────────────┘
                                       │
                                       ▼
                ┌──────────────────────────────────────────────┐
                │ Plugin subgraph entry (resolved plugin)        │
                │  ──Node: RecipeMatcher                         │
                │     - reads RepoContext + CveAdvisory          │
                │     - matches against bundled recipes          │
                │     - returns RecipeMatch | NoMatch            │
                │  ──Node: RecipeApplier                          │
                │     - invokes OpenRewriteRunner                │
                │       OR NpmDepBumpRecipe (pure-Python)        │
                │  ──Node: InstallValidator                       │
                │     - runs `npm install --ignore-scripts`      │
                │       in a sandbox subprocess                  │
                │  ──Node: GitDiffWriter                          │
                │     - mints branch name; commits patch         │
                │  ──Node: EmitRequiresSandboxValidation         │
                │     - emits event for Phase 5 to consume       │
                └──────────────────────────────────────────────┘
                                       │
                                       ▼  [TB-B crossing: bwrap/sandbox-exec]
                ┌──────────────────────────────────────────────┐
                │ codegenie.sandbox.SubprocessJail (Phase-3)    │
                │  - wraps subprocess.run with:                  │
                │    Linux: bubblewrap + seccomp profile         │
                │    macOS: sandbox-exec + custom .sb profile    │
                │  - read-only $HOME, no /etc                    │
                │  - per-process: PIDs cap, RSS cap, CPU-time cap│
                │  - egress firewall: iptables/pfctl rule via    │
                │    a child-network-namespace                   │
                │  - all stdout/stderr captured as bytes;         │
                │    parsed only by smart constructors            │
                └──────────────────────────────────────────────┘
                                       │
                                       ▼  [TB-C: subprocess returns]
                ┌──────────────────────────────────────────────┐
                │ codegenie.events.EventLog (append-only JSONL) │
                │  - BLAKE3-chained per ADR-0034                 │
                │  - every event Pydantic-typed                  │
                │  - 0600 perms, atomic rename per append        │
                └──────────────────────────────────────────────┘
```

The trust boundaries are not just diagram lines — each is enforced by a Python type. `SandboxedPath` cannot point outside the repo jail. `NpmInstallCapability` cannot be constructed without the resolver having minted it. `CveAdvisory` cannot exist if the input failed parsing. `EventLog` writes have no public mutator that doesn't append+hash. The diagram describes the runtime; the type system describes why the runtime can't be subverted.

## Components

### 3.1 `codegenie.cve.AdvisoryStore` — adversarial-input parser

- **Purpose:** parse NVD JSON 2.0, GHSA, and OSV feed records into a frozen, typed `CveAdvisory` model that downstream code can rely on.
- **Trust level:** **trusted output, untrusted input.** Inputs cross TB-D; outputs are trusted.
- **Interface:** `AdvisoryStore.load(cve_id: CveId) -> Result[CveAdvisory, ParseError]`. Errors enumerated: `MalformedJson`, `SchemaViolation`, `OversizedField`, `SuspiciousString`, `UnknownSchemaVersion`. No `Optional[CveAdvisory]` return — sum-type only, per [ADR-0033](../../production/adrs/0033-domain-modeling-discipline.md).
- **Adversarial inputs neutralized:**
  - Top-level JSON parsed with `json.loads` only after a 1 MiB size cap and a max-depth=16 reject.
  - Every string field is `len ≤ 8 KiB`, no `NUL` bytes, no control chars except `\t\n\r`, no ANSI escape sequences (`\x1b[`).
  - `affected_module` strings rejected if they contain `/`, `..`, `\`, `*`, `?`, `[`, `]`, `:`, whitespace, or `@` other than the optional scope marker — npm package names have a tight grammar; we enforce it. URL fields parsed with `urllib.parse.urlparse`, scheme allowlist `{https}`, no userinfo, no IDN tricks.
  - References to external URLs are stored as opaque `ExternalUrl` newtypes and never followed by Phase 3 (they are advisory-rendering data for HITL only).
  - Unicode bidi/zero-width characters in description fields stripped via an allowlist of NFKC-normalized printable + standard whitespace.
- **Isolation:** pure Python, no subprocess, no network at parse time. The fetch step (which *is* networked) is a separate `codegenie cve-feed sync` command with its own component (not described in detail here; it writes signed-timestamped feed files into `.codegenie/cve-cache/` and we only *read* the cache here).
- **Credentials accessed:** none.
- **Audit emissions:** `CveAdvisoryLoaded` (success) or `CveAdvisoryRejected(reason)` (parse failure). Rejections include the cause but **not the raw input** (which is logged hashed-only to avoid an attacker controlling our log content).
- **Tradeoffs accepted:** field-length caps are conservative; a legitimate CVE description >8 KiB is truncated at load with an explicit event. Acceptable — the description is human-rendered context, not decision input.

### 3.2 `codegenie.plugin.Resolver` — gated plugin loader

- **Purpose:** discover plugins under `plugins/`, validate manifests, resolve the `(task, language, build)` tuple to a specific plugin, walk the `extends` chain, and produce a `ResolvedPlugin` (or a `UniversalFallbackPlugin`).
- **Trust level:** **trusted output, semi-trusted input** (plugin code is reviewed via PR but each plugin still imports Python at load time — a malicious PR is a real threat).
- **Interface:** `Resolver.resolve(scope: PluginScope) -> ResolvedPlugin`. `ResolvedPlugin` is a sum type: `ConcreteResolved(plugin_id, extends_chain) | UniversalFallback(reason)`. The third case ("no plugin and no fallback") is type-unrepresentable — the universal fallback is mandatory.
- **Adversarial inputs neutralized:**
  - **Manifest schema:** `plugin.yaml` parsed with `yaml.safe_load`, validated as a Pydantic model with `extra="forbid"`. Unknown fields fail loud.
  - **Signature check:** `plugins/PLUGINS.lock` is a checked-in file listing `{plugin_id: sha256_of_dir_tree}`. The Resolver computes the actual SHA-256 of each plugin directory (sorted, excluding `__pycache__`) and refuses to load any plugin whose hash does not match the lockfile. Adding a plugin requires a PR that updates both the plugin and the lockfile; the lockfile change is the trust anchor. (This is a Phase-3-appropriate substitute for full Sigstore-style signing, which lands in Phase 11.)
  - **`extends` chain:** resolved iteratively with cycle detection (visited-set); max depth 4 (an arbitrary cap that catches infinite chains while leaving room for real composition); each entry must be a `PluginId` in the in-tree registry — no remote URLs, no file paths, no env-var interpolation. Relative paths in `extends` are *refused* at parse.
  - **Adapter import paths:** validated at load (`importlib` resolve fails fast) and the imported class must satisfy the declared Protocol via `runtime_checkable`. Adapter code is real Python, but the import itself happens inside a context manager that strips credential env-vars from `os.environ` and restores them on exit.
  - **`capabilities-needed` declaration:** each plugin declares the capabilities it needs (`FsReadWrite`, `NpmInstall`, `GitLocalOps`). The Resolver refuses to load a plugin that asks for an unknown capability or one outside the Phase 3 allowlist. A plugin that does *not* declare a capability cannot receive that capability later (the type system enforces this — see 3.5).
- **Isolation:** the plugin's Python `__init__.py` is imported, but the import is wrapped: `sys.modules` snapshot taken, plugin imported, snapshot diffed — any plugin that mutates `sys.modules` outside its own namespace fails the load. Network calls from plugin import are blocked by a `socket.socket` monkey-patch active during the import window (this is a soft control; the JVM and npm jails are the hard controls).
- **Credentials accessed:** none. The environment is stripped of `*_TOKEN`, `*_KEY`, `*_SECRET`, `*_PASSWORD`, `AWS_*`, `GH_*`, `GITHUB_*`, `NPM_*` for the import window.
- **Audit emissions:** `PluginResolved(plugin_id, extends_chain, matched_scope, fallback_used)` (typed per [ADR-0034](../../production/adrs/0034-event-sourcing-canonical-primitive.md)); `PluginRejected(plugin_id, reason)` on signature/schema/extends failure; `PluginRegistryCorrupted(reason)` when the lockfile contradicts on-disk content (refuses to start).
- **Tradeoffs accepted:** the `PLUGINS.lock` mechanism is *not* cryptographic signing — anyone with PR rights can update both files at once. We get tamper-evident-on-disk and "no plugin loads outside review" but not "the third-party author is verified." That gap is closed in Phase 11 with Sigstore. Recording it explicitly so the synthesizer can see the tradeoff.

### 3.3 `codegenie.fs.SandboxedPath` — jailed-path smart constructor

- **Purpose:** make path traversal unrepresentable. A `SandboxedPath` exists only if it was constructed inside a specific jail directory and the resulting absolute path is still inside that jail (after `realpath` resolution of all symlinks).
- **Trust level:** trusted.
- **Interface:** `SandboxedPath.create(jail: Path, relative: str | Path) -> Result[SandboxedPath, PathEscape]`. There is *no public constructor*; the dataclass is `frozen=True` with `init=False`. Once you have a `SandboxedPath`, the absolute resolved path is in `self.absolute` and is guaranteed inside the jail; the original input is not reachable.
- **Adversarial inputs neutralized:**
  - `..` segments: resolved before jail check.
  - Symlinks: `Path.resolve(strict=True)` follows them; the resolved path must `startswith(jail.resolve())` byte-prefix (no string-prefix tricks — full path-component comparison via `relative_to`).
  - Symlinks created mid-operation (TOCTOU): every write goes through `os.open(O_NOFOLLOW)` so a swap-symlink attack fails the open, not the path check.
  - Absolute paths in the `relative` argument: rejected unless `relative.is_absolute() and relative.resolve().is_relative_to(jail.resolve())`.
- **Isolation:** none needed — pure type discipline.
- **Credentials accessed:** none.
- **Audit emissions:** none directly. `PathEscape` failures are propagated as event payloads by callers.
- **Tradeoffs accepted:** every filesystem call in Phase 3 must take a `SandboxedPath`, not a `Path` or `str`. This is a slight API friction; mypy `--strict` enforces it. Worth it.

### 3.4 `codegenie.sandbox.SubprocessJail` — npm/JVM containment

- **Purpose:** wrap every subprocess.run for Phase 3 so that the child cannot reach the host filesystem outside the repo jail, cannot reach the network outside a configured registry mirror, and cannot exceed time/memory/PID caps.
- **Trust level:** trusted output, **untrusted child**.
- **Interface:** `SubprocessJail.run(spec: JailedSubprocessSpec) -> JailedSubprocessResult`. `JailedSubprocessSpec` is frozen Pydantic with `cmd: tuple[str, ...]`, `cwd: SandboxedPath`, `env: Mapping[NpmEnvKey, str]` (typed env-var key newtype — see below), `network: NetworkPolicy` (sum type: `DenyAll | RegistryMirrorOnly(url=...)`), `time_budget_s`, `memory_mib`, `pids_max`. `JailedSubprocessResult` is also a sum type: `Completed(exit_code, stdout_bytes, stderr_bytes, duration_ms) | TimedOut | OomKilled | NetworkDenied(host)`.
- **Linux implementation:** `bwrap` (bubblewrap) with `--unshare-all --new-session --die-with-parent --ro-bind / / --tmpfs /tmp --bind <repo_jail> <repo_jail>`. Optional seccomp filter blocking `mount`, `pivot_root`, `ptrace`, `bpf`, `unshare`, `keyctl`. Network namespace owned by parent; child sees only a `lo` interface plus a single `pf`-routed outbound to the configured mirror IP/port.
- **macOS implementation:** `sandbox-exec -f profile.sb`. The `.sb` file is generated per-spec with explicit `allow file-read* file-write*` only for the jail dir, `deny default`. Egress: macOS does not have per-process firewalling in the same form; we run npm install with `npm_config_offline=true` and an `npm_config_cache=<jail>/.npm-cache` populated *before* the jailed call, by a separate pre-fetch step that **does** have controlled network access (described below).
- **`--ignore-scripts` enforcement:** every npm invocation has `--ignore-scripts` *and* the env contains `npm_config_ignore_scripts=true` (belt and suspenders — npm has historically had bugs where one or the other was honored). The CLI also runs `npm config get ignore-scripts` post-init and asserts `true` before any install command, emitting `NpmScriptsLockEnforced` on success.
- **macOS offline mirror flow:** Phase 3 supports two modes — `--npm-online` (Linux only, uses bwrap egress allowlist) and `--npm-offline` (the only macOS mode). In offline mode, a separate **pre-fetch step** runs *outside the install jail* but with its own narrow tool — `codegenie cve-prefetch --package <name> --version <v>` — which downloads the patched-version tarball and its dependency closure to `.codegenie/npm-cache/` using `npm pack` against the configured registry, with the JVM/npm install jail not yet active. The pre-fetch step has tightly-scoped network access (only to the registry mirror) and writes only into the cache. The install jail then runs fully offline.
- **Adversarial behavior neutralized:**
  - npm postinstall RCE: `--ignore-scripts` + env enforcement + bwrap/sandbox-exec means the *worst case* is that a malicious `package.json` causes npm to fail; no script runs.
  - Resource exhaustion: PIDs/memory/time caps; cgroup limits on Linux, `ulimit` on macOS.
  - Filesystem escape: bwrap `--ro-bind / /` + writable jail dir only; macOS `sandbox-exec deny default`.
  - Network exfiltration: bwrap network namespace with explicit allowlist; offline mode on macOS.
- **Credentials accessed:** none. Env passed via a smart-constructed `NpmEnvBuilder` that allows only `npm_config_*` keys; `HOME` is set to the jail subdir; `PATH=/usr/bin:/bin` only; everything else removed.
- **Audit emissions:** `SubprocessJailStarted(spec_hash, cmd_canonical)`, `SubprocessJailCompleted(result_summary)`. The `stdout_bytes` are written to `.codegenie/runs/<run_id>/<step>/stdout.bin` (0600), not inlined in the event log, to keep the event log compact and avoid large-payload attacks.
- **Tradeoffs accepted:** offline-mode-only on macOS is friction (the cache must be pre-populated). Compensated by Linux/CI using the egress-allowlisted online path. Cold-path npm install is significantly slower than `npm install` developers are used to — Phase 3 is not optimized for developer-loop speed; Phase 5 is when sandbox warm-pools become relevant.

### 3.5 `codegenie.cap` — Capability tokens

- **Purpose:** ensure that the *ability* to write files, call npm, or run git is held only by code paths the Resolver has explicitly minted a token for.
- **Trust level:** trusted infrastructure.
- **Interface:** capabilities are frozen Pydantic models with a private `_minted_by: PluginId` field and no public constructor. The `CapabilityMint` (used only by `Resolver` after manifest validation) returns capability tokens. Consumer code receives them as function arguments:
  ```python
  def apply_npm_dep_bump(
      capability: NpmInstallCapability,    # cannot be forged
      target: SandboxedPath,                # cannot escape jail
      package: PackageId,                   # cannot be wrong type
      to_version: SemverVersion,            # smart-constructed
  ) -> Result[InstallReport, InstallError]:
      ...
  ```
- **Capability variants in Phase 3** (sum type):
  - `FsReadWriteCapability(jail: SandboxedPath)` — write under the jail.
  - `NpmInstallCapability(registry: RegistryUrl, mode: Literal["online","offline"])` — invoke `SubprocessJail.run` with an npm command. The capability *carries* the policy.
  - `GitLocalOpsCapability(repo: SandboxedPath, branch_prefix: BranchPrefix)` — branch + commit allowed inside the prefix; pushing is not a Phase 3 capability and minting one fails.
  - `EmitEventCapability(event_log: EventLog)` — append-only writes to the event log; not minted to plugin code (only `RecipeApplier` and `InstallValidator` core nodes have it; plugin contributions emit via the core).
- **Forgeability defenses:** the `__init__` is private; Pydantic's `model_validate` raises `CapabilityForgeryAttempt` if called outside `CapabilityMint`. mypy `--strict` plus a custom flake8/ruff rule fails CI if any module other than `codegenie.cap` imports a `Capability` constructor directly. The capability classes themselves are sealed: subclassing them outside the package raises at import time.
- **Audit emissions:** `CapabilityMinted(token_id, capability_type, scope, granted_to)`. Every capability use logs `CapabilityUsed(token_id, operation)`.
- **Tradeoffs accepted:** more verbose call signatures than passing strings. This *is* the point — the verbosity is the audit trail at compile time.

### 3.6 `codegenie.recipes.OpenRewriteRunner` — JVM jail

- **Purpose:** run OpenRewrite npm-dependency recipes against the target repo without exposing the JVM to the host.
- **Trust level:** semi-trusted child process.
- **Interface:** `OpenRewriteRunner.apply(recipe_id: RecipeId, target: SandboxedPath) -> Result[RecipeOutcome, RecipeError]`. `RecipeOutcome` is `AppliedClean | AppliedWithWarnings(list[Warning]) | NoOp`.
- **JVM containment:**
  - Recipe JARs are checked into `plugins/vulnerability-remediation--node--npm/recipes/` and their SHA-256 is in `plugins/PLUGINS.lock`; the runner refuses to execute a JAR whose hash doesn't match.
  - JVM invoked under `SubprocessJail` with `network=DenyAll`. OpenRewrite does *not* attempt Maven Central lookups at recipe runtime — all recipe definitions must be self-contained (Phase 3 ships only the dep-bump recipes, which are self-contained).
  - JVM flags: `-XX:MaxRAMPercentage=25 -Djava.security.manager=default -Dfile.encoding=UTF-8 -Djava.net.preferIPv4Stack=true` plus an `--add-opens` allowlist scoped to OpenRewrite's needs.
  - Java SecurityManager policy file (deprecated in modern Java, but Phase 3's JVM is pinned to Java 17 LTS with SecurityManager still functional) denies `java.io.FilePermission` outside the jail, denies `java.net.SocketPermission`, denies `RuntimePermission("exec")` and `RuntimePermission("loadLibrary.*")`.
- **Fallback for cases OpenRewrite doesn't yet cover:** a hand-rolled Python `NpmDepBumpRecipe` that parses `package.json` and `package-lock.json` with smart constructors, applies the version bump (`semver` library), and writes back through `SandboxedPath`. This path is **preferred** when applicable because pure Python is a smaller attack surface than the JVM. Recipe selection is "pure Python if available; OpenRewrite otherwise."
- **Audit emissions:** `RecipeMatched`, `RecipeApplied`, `RecipeFailed`, `RecipeJarRejected` (signature mismatch).
- **Tradeoffs accepted:** SecurityManager is deprecated upstream; we accept a future "ugrade the JVM containment" debt and document it in the phase's ADR. The bwrap layer is the real defense; SecurityManager is defense-in-depth inside the JVM.

### 3.7 `codegenie.git.LocalGitOps` — narrow git wrapper

- **Purpose:** create a local branch, commit the patch, write the diff to a file. Nothing else.
- **Trust level:** trusted.
- **Interface:** `LocalGitOps.create_patch_branch(cap: GitLocalOpsCapability, repo: SandboxedPath, patch: Patch) -> Result[BranchRef, GitError]`. Operations: `checkout -b <prefix>-cve-<id>-<short-uuid>`, `add <SandboxedPath list>`, `commit -m <sanitized message>`, `format-patch HEAD~1 -o <out>`. Operations *not* offered: `push`, `merge`, `rebase`, `reset --hard`, anything mutating other branches, anything using `--allow-empty`, anything with `hooks` enabled (`--no-verify` is set everywhere because we are explicit and audited; we do not silently bypass them — see audit below).
- **Adversarial inputs neutralized:**
  - Commit messages are constructed from CveAdvisory fields *after* sanitization (no unicode-bidi, no ANSI escapes; full NFKC normalize).
  - Branch names are derived deterministically and validated against `^[a-z0-9-]+$` after canonicalization.
  - `git config --local core.hooksPath /dev/null` is set in the run wrapper so a malicious `.git/hooks/pre-commit` in the target repo cannot execute. This bypass is explicitly logged as `GitHooksDisabledForRun` so a human reviewer in HITL sees it.
  - All git invocations go through `SubprocessJail` with `network=DenyAll` and a writable jail confined to the repo.
- **Credentials accessed:** none. `GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=/bin/false`, `SSH_ASKPASS=/bin/false` set so any prompt fails immediately.
- **Audit emissions:** `GitBranchCreated`, `GitCommitWritten(sha, sanitized_message)`, `GitHooksDisabledForRun`, `GitPatchEmitted(path, sha256)`.
- **Tradeoffs accepted:** developers who use git hooks legitimately in the target repo will see them bypassed for our run. The patch they review can be re-applied through their normal workflow with hooks enabled — we don't push, we don't merge, the developer remains the final approver per [ADR-0009](../../production/adrs/0009-humans-always-merge.md).

### 3.8 `codegenie.plugin.UniversalFallback` — never-silent-failure

- **Purpose:** when no concrete plugin matches `(task, language, build)`, produce a HITL escalation that contains enough context for a human triage but never executes any transform.
- **Trust level:** trusted code; semi-trusted rendering of repo content.
- **Interface:** the fallback plugin's subgraph is a single node `EmitRequiresHumanReview`. It reads `RepoContext`, the requested `CveAdvisory`, and a list of "why no plugin matched" reasons from the Resolver, sanitizes them all (NFKC, ANSI strip, bidi strip, length caps), and emits a `RequiresHumanReview` event. It writes a human-readable `.codegenie/handoff/<workflow_id>.md` (0644) summarizing the case. The workflow exits with code `7` (`E_REQUIRES_HUMAN`).
- **Adversarial inputs neutralized:** the rendered markdown is generated through a single function `render_handoff(payload: SanitizedHandoffPayload) -> str` where the `SanitizedHandoffPayload` is a smart-constructed type that has *already* passed through the sanitizer. Markdown injection is neutralized by escaping `<>{}\\`` and refusing inline HTML.
- **Credentials accessed:** none.
- **Audit emissions:** `RequiresHumanReview(workflow_id, reasons, sanitized_context_digest)`. The full context is on disk; the event references it by digest.
- **Tradeoffs accepted:** the universal fallback is *deliberately* boring. It does not try to fall back to "guess at a recipe." Silent failures, partial successes, and "best-effort" transforms are explicitly prohibited.

### 3.9 `codegenie.events.EventLog` — append-only audit chain

- **Purpose:** the substrate ADR-0034 specifies. Phase 3 is pre-Postgres-event-log; we ship the on-disk JSONL precursor with the same envelope shape so Phase 9's migration is a pure import job.
- **Trust level:** trusted infrastructure.
- **Interface:** `EventLog.append(event: Event) -> Result[EventRecord, AppendError]`. `Event` is the discriminated-union of every event variant in Phase 3. Internally: BLAKE3-chained, `prev_hash` field in each record, fsync on append, `0600`, written under `.codegenie/events/<workflow_id>.jsonl`.
- **Tamper evidence:** `codegenie audit verify` walks the chain and reports the first divergence. Without the prev-hash chain, an attacker who got filesystem write access could edit a single event and the system wouldn't know. With it, *every* downstream event's hash changes — single-edit detection.
- **Credentials accessed:** none.
- **Audit emissions:** is itself the audit emissions. Self-tested: appending an event must result in a `verify` pass; CI runs this on a fixture workflow.
- **Tradeoffs accepted:** BLAKE3-chain on every write costs ~microseconds per event; we will easily emit thousands of events per workflow at portfolio scale. Acceptable; far cheaper than the subprocess setup costs the events describe.

## Data flow — one end-to-end run

A user invokes `codegenie vuln /repos/web-app --cve CVE-2024-12345`. Walk-through with trust-boundary crossings marked.

1. **CLI parses arguments.** `repo_path` resolved through `SandboxedPath.create(jail=Path("/repos"), relative="web-app")` → `Result.Ok`. Workflow ID minted (UUID4). Event `WorkflowStarted(workflow_id, cli_args_canonical, cwd_resolved)` appended.

2. **CVE advisory loaded.** `AdvisoryStore.load(CveId("CVE-2024-12345"))` reads `.codegenie/cve-cache/`. **[TB-D crossing]** Raw JSON parsed under size/depth/charset caps; smart constructor returns `CveAdvisory` with typed fields. Event `CveAdvisoryLoaded(cve_id, affected_package, fixed_version)` appended.

3. **RepoContext loaded.** Phase 2's `repo-context.yaml` read via `SandboxedPath`, validated against schema, frozen. Event `RepoContextLoaded(workflow_id, repo_id, schema_version, slice_digest)` appended.

4. **Plugin resolution.** `Resolver.resolve(PluginScope(task=vuln, language=javascript, build=npm))` walks `plugins/`:
   - `plugins/PLUGINS.lock` read; each plugin dir's SHA-256 computed; mismatch → `PluginRegistryCorrupted`, workflow aborts.
   - Each `plugin.yaml` parsed under `extra="forbid"`; capability declarations validated against the Phase 3 allowlist.
   - `vulnerability-remediation--node--npm` matches; `extends: [vulnerability-remediation--node--*]` resolved; cycle-check passes; resolution chain `[vulnerability-remediation--node--*, vulnerability-remediation--node--npm]` recorded.
   - Event `PluginResolved(plugin_id, extends_chain, matched_scope, fallback_used=False)` appended.

5. **Capability mint.** **[TB-A crossing]** `CapabilityMint` (consulting the resolved plugin's `capabilities-needed`) returns:
   - `FsReadWriteCapability(jail=repo_path)`
   - `NpmInstallCapability(registry=RegistryUrl("https://registry.npmjs.org"), mode="offline")` (because we're on macOS)
   - `GitLocalOpsCapability(repo=repo_path, branch_prefix=BranchPrefix("codegenie/vuln"))`
   - Event `CapabilityMinted(token_id, capability_type, scope)` × 3.

6. **Recipe matching.** Plugin subgraph entry node `RecipeMatcher` reads `CveAdvisory.affected_package`, `CveAdvisory.fixed_version`, and `RepoContext.lockfile_slice`. Matches against bundled recipe metadata. A pure-Python `NpmDepBumpRecipe` matches (preferred over OpenRewrite). Event `RecipeMatched(recipe_id, recipe_kind="pure_python")` appended.

7. **Recipe application.** `NpmDepBumpRecipe.apply(cap_fs, target_repo, package, fixed_version)`:
   - Reads `package.json` via `SandboxedPath`; parses with size cap (1 MiB), Pydantic model.
   - Reads `package-lock.json`; size cap (32 MiB — large monorepo lockfiles); parses with depth cap (24).
   - Modifies the version pin and the lockfile entry; recomputes `integrity` hashes (these come from the registry data we cached pre-run, not computed locally — see step 8 below).
   - Writes both files through `SandboxedPath` with `O_NOFOLLOW`, atomic rename.
   - Event `RecipeApplied(recipe_id, files_changed=[paths], diff_size_bytes)` appended.

8. **Pre-fetch step (because mode="offline").** Before `npm install`, a separate `CvePrefetch` step runs *outside* the install jail but inside its own narrow component:
   - Network policy: allowlisted to `registry.npmjs.org` only.
   - Downloads tarball + dependency-closure tarballs into `.codegenie/npm-cache/`.
   - Validates each tarball's SHA-512 against the registry metadata response.
   - **[TB-D crossing again, narrower]** the registry response is parsed as JSON with the same size/depth/charset caps as CVE feeds.
   - Event `NpmCachePrefetched(packages, total_bytes, tarball_digests)` appended.

9. **Install validation.** `InstallValidator` invokes `SubprocessJail.run(JailedSubprocessSpec(cmd=("npm", "install", "--ignore-scripts", "--offline", "--no-audit", "--no-fund"), cwd=repo_path, env=npm_env_offline, network=DenyAll, time_budget_s=180, memory_mib=2048, pids_max=512))`. **[TB-B/TB-C crossings]**
   - Bubblewrap (Linux) or sandbox-exec (macOS) sets up the jail.
   - npm runs entirely from `.codegenie/npm-cache/`; no network attempt; `--ignore-scripts` blocks any postinstall.
   - Exit code captured; stdout/stderr written to `runs/<workflow_id>/install/`; smart-constructor parses npm's structured output (preferred) or treats it as opaque bytes if `--json` output is malformed.
   - Event `SubprocessJailStarted(spec_hash, cmd_canonical)` and `SubprocessJailCompleted(JailedSubprocessResult)` appended.

10. **Git ops.** `LocalGitOps.create_patch_branch(cap_git, repo_path, patch)`:
    - `git config --local core.hooksPath /dev/null`; event `GitHooksDisabledForRun`.
    - `git checkout -b codegenie/vuln-cve-2024-12345-<short-uuid>`; event `GitBranchCreated`.
    - `git add <package.json> <package-lock.json>`; commit with sanitized message; event `GitCommitWritten(sha)`.
    - `git format-patch HEAD~1 -o .codegenie/runs/<workflow_id>/diff/`; event `GitPatchEmitted(path, sha256)`.

11. **Emit handoff to Phase 5.** Event `RequiresSandboxValidation(workflow_id, repo_id, plugin_id, branch_ref, patch_sha256, cve_id)`. This is the consumer Phase 5 will pick up to actually *run tests inside a microVM*. Phase 3 itself never runs `npm test`.

12. **Workflow complete.** Event `WorkflowCompleted(workflow_id, outcome=success, exit_code=0)`. CLI prints the branch ref + a pointer to the audit log path + the next-step instruction ("review the patch and run `codegenie validate` once Phase 5 ships").

The full data flow has exactly four trust-boundary crossings: TB-D (CVE feed + registry response parsing), TB-A (capability mint), TB-B (JVM if recipe is OpenRewrite, or the bwrap/sandbox-exec boundary for npm), TB-C (subprocess return). Each crossing has a single typed funnel.

## Failure modes & recovery

| Failure | Detected by | Containment | Recovery |
|---|---|---|---|
| Malformed CVE record (oversized field, NULs, JS injection in description) | `AdvisoryStore.load` smart constructor | Returns `Err(ParseError)`; workflow aborts | `CveAdvisoryRejected` event; no transform attempted; human reviews CVE feed |
| Crafted `affected_module` with path traversal (`../../etc/passwd`) | npm-package-name grammar regex in CVE parser | Reject at parse; never reaches filesystem code | Same as above |
| Plugin `extends` cycle | Resolver cycle detection (visited set) | Refuse to load any plugin in the cycle | `PluginRegistryCorrupted`; abort startup |
| Plugin SHA-256 mismatch vs `PLUGINS.lock` | Resolver hash check on every load | Refuse to load the plugin | `PluginRejected(signature_mismatch)`; abort if requested plugin was the rejected one |
| Plugin asks for capability outside Phase 3 allowlist | Manifest validation at load | Refuse to load | `PluginRejected(unknown_capability)` |
| Malicious recipe attempts file write outside repo jail | `SandboxedPath` constructor (path-escape) | `O_NOFOLLOW` open fails or path check raises | `RecipeFailed(path_escape)`; rollback any partial write via `git stash` of pre-state |
| Malicious npm postinstall script | `--ignore-scripts` env+CLI + bwrap/sandbox-exec | Script never runs; if npm has a 0day bypass, bwrap/SBPL contains the process | `SubprocessJailCompleted(exit_code≠0)` if npm errored; canary-file test asserts containment |
| npm install attempts non-mirror egress | bwrap network namespace / sandbox-exec deny | Connection blocked; npm reports network error | `JailedSubprocessResult.NetworkDenied(host)`; workflow exits with a flag indicating tampered-package suspicion |
| Subprocess time/memory/PID overrun | cgroup limits / `ulimit` | Process killed | `JailedSubprocessResult.TimedOut` or `OomKilled`; no retry (this is Phase 5's three-retry territory) |
| Symlink-swap TOCTOU between path validation and file open | `O_NOFOLLOW` on every open | `open()` returns `ELOOP`; raised as exception | Workflow aborts with `FilesystemRaceDetected` event |
| Git hook in target repo attempts to run on commit | `core.hooksPath=/dev/null` set per run | Hooks not executed | `GitHooksDisabledForRun` event makes the bypass visible to reviewer |
| Concurrent run racing same repo | per-repo file lock `.codegenie/.lock` (flock); fails fast on contention | Second invocation exits with `WorkflowConcurrent` | Operator chooses which to keep |
| Event log corrupted (BLAKE3 chain break) | `codegenie audit verify` | Workflow refuses to start if chain head doesn't match its prev-pointer | Operator investigates; reconstruction from JSONL is possible if outer file integrity is intact |
| Universal fallback emits handoff with attacker-controlled content | `SanitizedHandoffPayload` smart constructor strips bidi/ANSI/etc.; render escapes HTML | Reviewer sees normalized content | None needed; this is the design point |
| Disk fills mid-write of patched lockfile | Atomic-rename pattern; pre-write `os.statvfs` check | Partial write never visible | Rollback the branch; emit `WorkflowFailed(disk_full)` |
| Compromised plugin successfully lands via PR review failure | Out of band: code review, PR templates, branch protection | Not detected at runtime — this is a known gap closed by Phase 11's Sigstore signing | Document explicitly; treat `PLUGINS.lock` updates as security-sensitive PRs |
| Adversarial repo content (zero-width chars in `package.json` "name") | npm grammar regex; UTF-8 NFKC normalize then re-validate | Reject at parse | `RecipeFailed(invalid_repo_content)` |
| OpenRewrite JAR with attacker-bundled code (JAR-confusion attack) | SHA-256 against `PLUGINS.lock` | Refuse to execute mismatched JAR | `RecipeJarRejected` |

Three failures deliberately *not* in scope for Phase 3:
- *Patch produces working diff but tests fail under runtime.* That's Phase 5's three-retry gate territory; Phase 3 emits `RequiresSandboxValidation` and stops.
- *Org-wide credential rotation.* Phase 11 owns push tokens.
- *Per-plugin LLM cost cap.* No LLM in Phase 3; Phase 4 owns this.

## Resource & cost profile

These numbers assume a 200-MB Node.js repo with a 12-MB `package-lock.json`, on Linux orchestrator. macOS adds ~30% for sandbox-exec startup.

| Operation | Wall time | Memory (peak) | Disk write |
|---|---|---|---|
| CVE advisory load (cache-warm) | < 30 ms | 8 MiB | 0 (read-only) |
| RepoContext load (cache-warm) | < 80 ms | 25 MiB | 0 |
| Plugin resolution (3 plugins, SHA-256 walk) | 150–400 ms (cold), <50 ms (cache) | 12 MiB | 0 |
| Recipe match | < 20 ms | 5 MiB | 0 |
| Pure-Python NpmDepBumpRecipe apply | 100–300 ms | 30 MiB (peak during lockfile parse) | <1 MiB |
| Pre-fetch step (1 pkg + closure of ~50 transitive deps) | 5–25 s | 60 MiB | 30–150 MiB |
| `npm install --offline --ignore-scripts` inside bwrap | 8–40 s | 800 MiB | 200–600 MiB (node_modules) |
| Git branch + commit + format-patch | 200–600 ms | 25 MiB | <1 MiB |
| Event-log appends (50 events, BLAKE3 chain) | 5–15 ms | trivial | <100 KiB |
| **Total end-to-end** | **15–70 s** | **~1 GiB peak** | **~700 MiB** |

**Cost of security vs unsecured baseline:**

- Pre-fetch step adds ~5–25 s; a developer running `npm install` normally hits the registry directly and may save a few seconds when the cache is warm. Net: +0–20 s.
- Bubblewrap / sandbox-exec setup: ~150 ms per subprocess invocation. Phase 3 has ~3 jailed invocations per workflow. Net: ~500 ms.
- BLAKE3 chain on event log: ~1 µs per event × ~50 events. Net: 50 µs. Negligible.
- SHA-256 of plugin tree on resolution: 150–400 ms for 3 plugins of typical size. Cacheable but conservatively not cached in Phase 3. Net: 150–400 ms.
- JVM SecurityManager + custom policy file load: ~500 ms cold (only when OpenRewrite is the recipe). The pure-Python recipe path avoids this.

**Total cost of security in Phase 3: ~1–2 s of overhead per workflow, plus the pre-fetch step (which is the largest item).** At portfolio scale (let's say 1000 workflows/day), that's ~25 min/day of extra wall time. The unsecured alternative — running `npm install` with postinstall scripts active on the orchestrator host — is *categorically* unacceptable, not a performance comparison.

## Test plan

Phase 3 passes when *all* of the following are green in CI. Adversarial tests are first-class and outnumber the happy-path tests.

### Happy path

1. **End-to-end fixture (`tests/integration/test_vuln_endtoend.py`):** a fixture Node.js repo with `lodash@4.17.20` and a fixture CVE matching `lodash <4.17.21`. `codegenie vuln` produces a branch with the bump, `npm install --offline` exits 0 inside the jail, a `.patch` file appears, and `RequiresSandboxValidation` event fires.

2. **Determinism (`tests/integration/test_vuln_deterministic.py`):** the same workflow run twice produces byte-identical patches and (after redacting `workflow_id`/timestamps) byte-identical event sequences.

3. **Universal fallback (`tests/integration/test_universal_fallback.py`):** plugin registry contains only `universal--*--*/`; workflow exits with code 7, produces exactly one `RequiresHumanReview` event, writes a non-empty `.codegenie/handoff/*.md`.

### Adversarial — CVE feed input

4. **CVE with oversized description field** (`tests/security/test_cve_oversized.py`): 128 MiB description → `MalformedJson` (size-cap rejection) → `CveAdvisoryRejected`. No memory exhaustion.

5. **CVE with NUL bytes / control chars in `affected_module`:** `CveAdvisoryRejected(invalid_chars)`.

6. **CVE with `..` path traversal in `affected_module`:** package-name regex reject. `CveAdvisoryRejected`.

7. **CVE with malicious URL in `references` (`javascript:`, `data:`, file URIs):** scheme allowlist fails → reference dropped silently with `CveReferenceDropped` event (URL not used by Phase 3 but logged).

8. **CVE with unicode bidi tricks in description:** NFKC + bidi-strip; rendered output free of `U+202E` etc. Asserted on `RequiresHumanReview` handoff content.

### Adversarial — plugin loader

9. **Plugin with `extends` cycle** (`tests/security/test_plugin_cycle.py`): `A extends B; B extends A`. Resolver refuses both. `PluginRejected(extends_cycle)`.

10. **Plugin SHA-256 mismatch with `PLUGINS.lock`:** mutate a plugin file post-lock; resolver refuses to load. `PluginRejected(signature_mismatch)`.

11. **Plugin manifest declaring unknown capability `NetworkEgressCapability`:** manifest validation fails at `extra="forbid"`/allowlist check. `PluginRejected(unknown_capability)`.

12. **Plugin manifest declaring relative `extends: ../../my-evil-plugin`:** path-resolution check fails. `PluginRejected(invalid_extends_path)`.

13. **Plugin import that writes to `sys.modules` outside its namespace:** snapshot-diff check fails. `PluginRejected(import_pollution)`.

14. **Plugin import that calls `socket.socket()`:** monkey-patch raises `NetworkInImport` → `PluginRejected`.

### Adversarial — recipe and filesystem

15. **Recipe attempts to write `../etc/passwd`** (test recipe in `tests/security/recipes/`): `SandboxedPath.create` returns `Err(PathEscape)`. Recipe runner converts to `RecipeFailed`.

16. **Symlink-swap TOCTOU:** test creates a symlink to `/etc/hosts` between path validation and open. `O_NOFOLLOW` raises `ELOOP`. `FilesystemRaceDetected` event.

17. **OpenRewrite JAR mutated post-lock:** JAR SHA-256 mismatch; `RecipeJarRejected`.

### Adversarial — npm install jail

18. **Malicious postinstall canary** (`tests/security/test_postinstall_canary.py`): fixture package with `postinstall` script that touches `~/.codegenie/test-canary-files/touched`. Run workflow. Assert: canary file does NOT exist; `--ignore-scripts` confirmed; if bwrap stripped the script anyway, double confirmation.

19. **Egress attempt during npm install:** fixture package whose `npmrc` redirects registry to `attacker.example.com`. Inside the jail, the network namespace blocks all egress except the mirror IP. `JailedSubprocessResult.NetworkDenied(host)`.

20. **Resource exhaustion:** fixture with a deeply nested dep tree that drives `node_modules` over the disk quota. Subprocess killed by cgroup; `JailedSubprocessResult.OomKilled` or `DiskQuotaExceeded`.

21. **Env var leak attempt:** set `AWS_SECRET_ACCESS_KEY` in parent process; assert npm subprocess does NOT see it (env-allowlist test).

### Adversarial — git ops

22. **Repo with malicious `.git/hooks/pre-commit`:** `core.hooksPath=/dev/null` prevents execution. Canary not touched. `GitHooksDisabledForRun` event emitted.

23. **Repo with mid-workflow concurrent invocation:** second `codegenie vuln` on same repo blocks on flock; exits with `WorkflowConcurrent`.

### Audit completeness

24. **Replay test (`tests/integration/test_event_replay.py`):** record a full successful workflow's events; replay against a clean copy of the repo; assert byte-identical post-state.

25. **Chain tamper test:** record events; mutate one event payload; `codegenie audit verify` reports the divergence at the correct event index.

26. **Type-system fence test (`tests/static/test_capability_fence.py`):** ruff/mypy plugin asserts no module outside `codegenie.cap` constructs a `Capability` directly. CI failure if any caller smuggles in a token.

### Property-based

27. **CVE-parser property test:** for any random bytes ≤ 1 MiB, parse either returns `Err(...)` or returns a `CveAdvisory` whose fields are all known-grammar. No panics, no infinite loops, no OOM.

28. **SandboxedPath property test:** for any path argument (random bytes interpretation), either get a `SandboxedPath` whose absolute is under the jail, or get a `PathEscape`. No third outcome.

## Design patterns applied

| Decision (control or boundary) | Pattern applied | Why this pattern *here* | Pattern *not* applied (and why) |
|---|---|---|---|
| Sandbox isolation (Phase 3 npm/git/JVM) | **Hexagonal Port + Adapter** ([toolkit §"Hexagonal"](../../../.claude/skills/roadmap-phase-designer/references/design-patterns-toolkit.md)) | `SubprocessJail` is the Port (one interface); `BwrapAdapter` (Linux), `SandboxExecAdapter` (macOS), and the future `FirecrackerAdapter` (Phase 5) are Adapters. Phase 3 doesn't depend on which substrate is active; Phase 5 swaps adapters without core changes. Defends ADR-0012's "stack choice deferred" by making the choice swappable | Skipped pure **Strategy** — Strategy would put substrate selection per-call; we want per-deployment selection of one adapter at startup, which is a Port/Adapter shape, not a Strategy with context |
| Capability tokens (`NpmInstallCapability`, `FsReadWriteCapability`, `GitLocalOpsCapability`) | **Capability pattern** + **smart constructor** + **make illegal states unrepresentable** | Holding a token *is* the proof of authorization; a plugin can't forge `NpmInstallCapability` because the constructor is private and `CapabilityMint` is the only minter. The capability *carries* its scope (registry URL, jail path, branch prefix) so `capability.invoke(...)` doesn't take an "is this allowed?" boolean — the question is already answered by the type | Skipped role-/permission-string-keyed `is_allowed(action: str)` runtime check — strings are forgeable, easy to misspell, and the type checker can't validate them. Capabilities make the check structural |
| Plugin `extends` chain + `PLUGINS.lock` signature | **Plugin architecture** (toolkit §"Plugin architecture") + **registry pattern** | The kernel (`Resolver`) never imports specific plugins; plugins register via discovery + hash-locked manifest. The lockfile mechanism is the smallest viable signing story for Phase 3 — not Sigstore-grade, but tamper-evident-on-disk and tied to PR review. Honest about its limits | Skipped Python entry-points discovery — entry-points are out-of-tree-installable, which weakens the trust story (a `pip install evil` can register a plugin we didn't review). In-tree-only is a deliberate v1 choice per [ADR-0031](../../production/adrs/0031-plugin-architecture.md) §"Out-of-tree pip-installable plugins are v2" |
| `SandboxedPath` (path-jail enforcement) | **Smart constructor** + **make illegal states unrepresentable** + **newtype** | Once you have a `SandboxedPath`, the type is *evidence* the path is in-jail; you can't typecheck if you accidentally use a raw `Path`. Every file I/O in Phase 3 demands a `SandboxedPath` parameter. Compiler-enforced sandbox boundary | Skipped runtime `assert path.is_relative_to(jail)` sprinkled at every call site — every assert is a TODO that someone forgets. Smart constructor centralizes the check once |
| Typed event log (every plugin resolution, recipe application, install attempt, git op) | **Event sourcing** ([ADR-0034](../../production/adrs/0034-event-sourcing-canonical-primitive.md)) + **command pattern** + **tagged union for event variants** | The audit trail is *the* state-of-record for "what did the agent do?" Replay tests prove the workflow is reconstructable; tamper-evidence catches a compromised orchestrator. ADR-0034 commits to event sourcing as canonical; Phase 3 is the first concrete user. Discriminated-union event types make `mypy --strict` exhaustiveness-check every projection consumer | Skipped per-component ad-hoc log files — that's 6 schemas in 6 places, no cross-cutting query, no replay |
| `CveAdvisory`, `BuildOutcome`, `JailedSubprocessResult` as sum types instead of `Optional`/`bool` flags | **Tagged union for state** + **make illegal states unrepresentable** ([ADR-0033](../../production/adrs/0033-domain-modeling-discipline.md)) | `JailedSubprocessResult = Completed | TimedOut | OomKilled | NetworkDenied(host)` — each variant carries exactly the fields it needs; `(timed_out=True, network_denied="x")` is unconstructible. Exhaustiveness checking via `match` + `assert_never` makes every consumer handle every failure. Maps directly to ADR-0033's discipline | Skipped `result.success: bool` + `result.error_message: str` shape — booleans plus optional strings allow "successful but with an error message?" half-states |
| Universal `(*, *, *)` HITL fallback | **Chain of responsibility / pipeline** + **make illegal states unrepresentable** | Resolution chain ends at the universal fallback, deterministically. `ResolvedPlugin` is `ConcreteResolved | UniversalFallback` — the "no plugin matched and we kept going anyway" state is unrepresentable. Pipeline shape makes "what handled this workflow?" answerable in one event lookup | Skipped exception-on-no-match — exceptions are easy to swallow; an explicit fallback plugin is harder to bypass. Also, exceptions don't carry the structured context that the HITL flow needs |

## Risks (top 5)

1. **The pre-fetch step is the new attack surface.** The `codegenie cve-prefetch` step runs *outside* the install jail and *does* talk to the npm registry. It's narrower than letting npm itself talk to the registry, but it's still network I/O. A compromised registry response (or a successful MITM despite TLS pinning) lands attacker-controlled bytes in `.codegenie/npm-cache/`. The defense is registry-response size/depth caps + tarball SHA-512 validation against the registry's own metadata response — which is circular if the metadata is also compromised. **Mitigation:** in Phase 3, accept the residual risk (real-world npm trust depends on registry signing, which is partial today). Document the gap for Phase 11.

2. **The `PLUGINS.lock` mechanism is not real signing.** A PR that updates both the plugin and the lockfile passes the runtime check; the trust is in the review process, not in cryptography. A reviewer who waves through `PLUGINS.lock` changes without checking the diff is the entire compromise vector. **Mitigation:** CODEOWNERS on `plugins/PLUGINS.lock` requiring a second security-team reviewer; PR template that highlights the lockfile change; Phase 11 replaces with Sigstore.

3. **JVM SecurityManager is deprecated.** Java 17 still has it, but it's removal-flagged for future Java LTS. Phase 3's JVM containment leans on bwrap/sandbox-exec as the *real* boundary; SecurityManager is defense-in-depth. **Mitigation:** when Java 25+ ships without SecurityManager, the bwrap layer remains. If we cannot get a working policy at all, fall back to pure-Python recipes only and treat OpenRewrite as Phase 5-or-later territory. The pure-Python `NpmDepBumpRecipe` covers the canonical CVE case (transitive dep bump) so this is not a feature blocker.

4. **macOS subprocess containment is weaker than Linux.** `sandbox-exec` works but uses an undocumented profile language Apple has signaled may go away. Per-process firewalling is harder on macOS. Mitigation: offline-mode-only on macOS, which means the install jail has no network adapter at all — egress can't happen because there's nowhere to egress to. Linux is the production substrate; macOS is developer-loop only. The phase ADR records this asymmetry.

5. **Event log is local-disk-only in Phase 3.** ADR-0034 specifies a Postgres event log starting Phase 9; Phase 3's JSONL is the bridge. A compromised orchestrator with disk-write access can rewrite history (BLAKE3 chain detects this but does not prevent it). **Mitigation:** the chain-verify is part of the start-up check on every workflow — re-corruption is detected the next time the system runs. Phase 9 ships durable Postgres + Temporal history. Phase 3 commits to the same envelope shape so migration is mechanical.

## Acknowledged blind spots

- **Latency.** The pre-fetch step + cold subprocess jail boot adds seconds per workflow. The performance-first design probably skips the offline mode entirely on Linux (relying on bwrap egress allowlist), accepts a slower jail boot, and has more headroom for parallel installs. The synthesizer should weigh whether to ship online-mode on Linux as a flag while keeping offline-mode the default.
- **Developer ergonomics.** Capability tokens + `SandboxedPath` arguments make Phase 3 code more verbose than a "just call subprocess.run" version. The best-practices design probably uses higher-level façades. I'm betting verbosity at compile time saves debugging time at the breach. If the synthesizer values onboarding cost, expect a façade layer that bundles capabilities.
- **OpenRewrite recipe coverage.** I've leaned heavily on the pure-Python recipe path because it's a smaller attack surface than the JVM. That means OpenRewrite recipes — the *roadmap-stated* primary tool — get less weight in this design. The synthesizer should note that the roadmap is explicit about OpenRewrite as the *first* path with hand-rolled AST as fallback; my security ordering flips that priority for safety reasons and the synthesizer must decide.
- **Concurrent workflows on the same orchestrator.** I serialize per-repo via flock but don't parallelize across repos. A performance-tuned design would handle the cross-repo case explicitly. Phase 5/9 owns concurrency, but in the meantime the security design is "one workflow per orchestrator at a time" — that's a real product limitation.
- **No `npm test` in Phase 3.** This is the biggest scope choice. The roadmap exit criterion is "passes the repo's own tests." I'm reading that as "the patch is provably installable and Phase 5 will run the tests." A different reading — "run the tests in Phase 3 too, in some weaker sandbox" — is defensible. I rejected it because *any* test execution runs the repo's code, and the repo's code can include malicious test files. The synthesizer must decide whether the exit criterion needs a weaker sandbox to satisfy now or is OK with `RequiresSandboxValidation` as the handoff.
- **Cost observability.** Phase 13 owns this; Phase 3 emits events that the future cost ledger projects from, but doesn't surface per-workflow cost. The other lenses may push for inline cost surfacing.

## Open questions for the synthesizer

1. **Online-mode vs offline-mode on Linux.** Bubblewrap with an egress allowlist to the registry mirror is a credible production posture and is faster than the pre-fetch + offline path. macOS will be offline-only either way. Do we ship one mode (offline everywhere) or two (online on Linux, offline on macOS) with a flag?

2. **Does Phase 3 ship `npm test` inside a weaker sandbox to satisfy "passes the repo's own tests" exit criterion, or does it explicitly defer that to Phase 5?** Security says defer; the roadmap reads ambiguously. The synthesizer should decide.

3. **Should the JVM/OpenRewrite path ship in Phase 3 at all, or only the pure-Python recipe path with OpenRewrite added in Phase 4 alongside the LLM fallback?** Dropping the JVM avoids a large attack surface and a deprecated-API risk. The roadmap mentions OpenRewrite first but offers "hand-rolled AST as a fallback for cases OpenRewrite does not yet cover" — for npm dep bumps, the hand-rolled path covers the canonical case completely.

4. **`PLUGINS.lock` vs Sigstore-style signing.** Phase 3's lockfile mechanism is the minimal viable trust anchor. Should Phase 3 ship the harder Sigstore-style signing infrastructure now (cost: significant Phase 3 scope expansion) or defer to Phase 11 (cost: living with the weaker mechanism through 8 phases)?

5. **Universal HITL fallback's rendered output — markdown or sandboxed HTML?** Markdown with strict escaping is what I designed; a rendered-HTML option (in a sandboxed iframe inside an operator portal) would let the reviewer see syntax-highlighted diffs. Phase 13.5 owns the operator portal; Phase 3 ships disk markdown only. Is the synthesizer comfortable with that?

6. **Where do CVE feed *fetches* live?** I split fetch (`codegenie cve-feed sync`, networked, separate component) from parse (`AdvisoryStore.load`, local-only). The fetch step needs its own threat-model treatment that I scoped out. Should Phase 3 include it, or treat CVE-feed sync as Phase 13's CVE-event ingestion territory and assume `.codegenie/cve-cache/` is pre-populated by an out-of-band process for Phase 3?
