# Phase 01 — Context gathering: Layer A (Node.js): Security-first design

**Lens:** Security — isolation, least privilege, audit, supply chain.
**Designed by:** Security-first design subagent
**Date:** 2026-05-12

---

## Lens summary

Phase 1 is the first phase that *reads adversarial repo content at scale*. Phase 0 walked a directory and counted file extensions; Phase 1 parses `package.json`, lockfiles, CI YAML, Helm/Kustomize/Terraform deployment manifests, and Dockerfiles produced by people we do not trust. The gather pipeline is also the **upstream of every downstream judgment** in the system — by Phase 3 a planner consumes `repo-context.yaml` to write code; by Phase 11 that artifact gets committed into a PR. A bug in Phase 1's parsers is not a parser bug; it is a typed channel from adversarial bytes to production diffs.

Security in this phase means: treat every probe's input as untrusted, every parser as a potential CVE, every cache write as a future cache-poisoning attempt, and every output field as a potential exfiltration channel into the human-facing report and the eventual PR body. The design priorities, in order: (1) parsers run in a process-isolated *parser sandbox* with hard CPU/memory/time/output-size caps; (2) `declared_inputs` and cache keys are tamper-resistant; (3) the Phase 0 sanitizer chokepoint ([ADR-0008](../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md)) grows a third structural pass (size/depth caps) but stays out of the gather hot path for gitleaks; (4) the audit trail captures *what bytes were parsed* (hash + size) so a later compromise can be triaged.

The lens deliberately spends performance to buy auditability. Where a probe could parse `pnpm-lock.yaml` in-process at 30 ms, this design forks a hardened subprocess at 200 ms. The cost is paid once per cache miss; the benefit is paid every time an attacker tries something. Given Phase 11's PR-opening commits these artifacts into shared repos, the asymmetry is in security's favor.

---

## Threat model

### Assets to protect

1. **Developer/CI host integrity.** A probe running as the engineer's user must not be able to read `~/.ssh/`, `~/.aws/credentials`, env-vars holding LLM keys, or write outside `.codegenie/` and (opt-in) the analyzed-repo `.gitignore`.
2. **The `repo-context.yaml` artifact's truthfulness.** By Phase 3 the planner trusts this artifact end-to-end. Lying in it (via a poisoned cache or an attacker-controlled probe output) is a privileged write into the eventual diff.
3. **The content-addressed cache.** Cache poisoning is the only known way to make Phase 14's continuous-gather model produce wrong answers without re-executing probes. A poisoned cache entry is a persistent backdoor across gathers.
4. **Audit trail integrity.** `runs/<utc-iso>-<short>.json` is the only mechanism that lets a later operator answer "what did Phase 1 see on commit X?" If the audit trail can be edited post-hoc by the same code path that writes it, it is not an audit trail.
5. **Downstream prompt context (Phase 3+).** Probe output strings flow verbatim into LLM context windows. A malicious `package.json` field can carry indirect prompt-injection payloads. The threat is one phase away; the structural defense (no-strings-into-prompts-without-channels) lands here, not later.
6. **Supply chain integrity of the gather binary itself.** A tampered `pnpm-lock.yaml` parser or `tree-sitter-typescript` grammar inverts every probe that uses it. Pinning by hash is non-negotiable.

### Adversaries assumed

- **Malicious repo author** (primary). Crafts adversarial `package.json`, lockfiles, `.github/workflows/*.yml`, Helm `values.yaml`, Dockerfile, `tsconfig.json`, etc. Goal: arbitrary code execution in the gather process, exfiltration of host secrets, cache poisoning, or planting prompt-injection strings that will activate at Phase 3 LLM inference.
- **Compromised dependency** of `codewizard-sherpa` itself. A malicious or compromised version of `pyyaml`, `jsonschema`, `tree-sitter`, `aiofiles`, or a transitively pulled package. Goal: code execution at import time or at probe-run time.
- **Hostile CI environment.** A workflow run on a fork PR has access to a read-only `GITHUB_TOKEN` but can read the repo. The repo's `.codegenie/` cache (if shared via `actions/cache`) is a poisoning vector across PRs.
- **Local multi-tenant developer host.** Another user on the same Linux box reading `~/.codegenie/` or the analyzed repo's `.codegenie/cache/` — already addressed by [ADR-0011](../00-bullet-tracer-foundations/ADRs/0011-codegenie-directory-permissions-model.md), extended in this phase.

**Out of scope:** physical access; kernel zero-days; a compromised Python interpreter; an attacker with write access to the developer's home directory before gather runs.

### Attack surfaces specific to this phase

| Surface | Carrier | Threat | Phase 0 coverage |
|---|---|---|---|
| `package.json` parsing | `json.loads` | JSON bombs, deeply nested objects, OOM via 1 GB string | None |
| Lockfile parsing | YAML (`pnpm-lock.yaml`), JSON (`package-lock.json`), custom (`yarn.lock`) | YAML bombs ("billion laughs"), `!!python/object` (if unsafe), 200 MB lockfile OOM, regex-DoS on yarn.lock | Banned `yaml.load` without `Loader=` (Phase 0 forbidden-patterns hook) |
| CI YAML parsing | `.github/workflows/*.yml`, `.gitlab-ci.yml`, `Jenkinsfile` | YAML bombs; `${{ ... }}` expression injection (does not run, but flows into outputs); Jenkinsfile regex DoS | None |
| Helm/Kustomize traversal | filesystem walk through `deploy/` | Symlink-out, zip-slip-style `../../../etc/passwd` in `kustomization.yaml`'s `resources:` field, hostile filename lengths, deep directory recursion | Symlink-cross-repo-boundary check (Phase 0 walker) |
| Terraform/HCL parsing | optional `hcl2` library | Library-specific CVEs; deeply nested HCL DoS | None |
| `tree-sitter` ambiguity fallback (A1) | grammar invocation | Grammar bugs (memory-unsafe historically; native code); pathological input causing parse stack overflow | Banned in Phase 0 (deferred to Phase 1) |
| `tsconfig.json` parsing | JSON with comments (JSONC) | Comment-parser confusion; circular `extends` chains | None |
| `node --version` invocation | subprocess | If `$PATH` includes a malicious `node` shim planted by the repo, RCE in gather context | Phase 0 allowlist allows only `git`; this phase widens |
| Cache key computation | `declared_inputs` glob expansion | Glob expansion outside repo root via symlinks; cache-key collision via path normalization | Phase 0 BLAKE3 of `(path, size)` tuples; declared inputs constrained |
| `.codegenie/cache/` blob writes | filesystem | Race condition between concurrent gathers; symlink-to-`/etc/passwd` cache target; disk-fill DoS | 0700/0600 modes; atomic write |
| Output writer | `repo-context.yaml`, `CONTEXT_REPORT.md` | Indirect prompt-injection strings preserved into Phase 3 context; absolute-path leak | Phase 0 sanitizer (field-name + path scrub) |
| Audit record | `runs/<ts>.json` | Forgery (probe rewrites its own audit entry); deletion (gather wipes its tracks) | 0600 mode; one file per run |

### Trust boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│                  HOST (developer or CI runner)                   │
│   $HOME, $PATH, env vars including secrets                       │
│   trust: SEMI-TRUSTED (own files, own creds — must not leak)    │
│                                                                  │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │            codegenie process (Python, uid=user)           │  │
│   │   trust: TRUSTED — pinned code, lockfile-verified         │  │
│   │   sees: $HOME (filtered), code, configs                   │  │
│   │                                                            │  │
│   │   ┌─────────────────────────────────────────────────────┐ │  │
│   │   │      Coordinator + Cache + Sanitizer + Writer        │ │  │
│   │   │      (no parsing of analyzed-repo content here)      │ │  │
│   │   └────────────────────┬────────────────────────────────┘ │  │
│   │                        │ structured ProbeOutput           │  │
│   │   ─────────────────────┼─────────────────────────────────── │ ← TRUST BOUNDARY 1
│   │   ┌────────────────────▼────────────────────────────────┐ │  │
│   │   │  Parser sandbox subprocess (per probe execution)     │ │  │
│   │   │  trust: SEMI-TRUSTED                                 │ │  │
│   │   │   - no network                                       │ │  │
│   │   │   - rlimits (RSS, CPU, FSIZE, NOFILE, AS)            │ │  │
│   │   │   - filtered env (no secrets)                        │ │  │
│   │   │   - cwd = analyzed-repo (read-only mount on Linux)   │ │  │
│   │   │   - writes only to per-probe tempdir + stdout pipe   │ │  │
│   │   │                                                       │ │  │
│   │   │   ──────────────────────────────────────────────────  │ │  │ ← TRUST BOUNDARY 2
│   │   │   ┌─────────────────────────────────────────────────┐│ │  │
│   │   │   │  Adversarial bytes (analyzed repo content)       ││ │  │
│   │   │   │  trust: UNTRUSTED                                ││ │  │
│   │   │   │   - package.json, *.lock, CI yaml, Dockerfile,   ││ │  │
│   │   │   │     Helm/Kustomize, tsconfig.json, .nvmrc, ...   ││ │  │
│   │   │   └─────────────────────────────────────────────────┘│ │  │
│   │   └──────────────────────────────────────────────────────┘ │  │
│   └──────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

**Boundary 1** is the in-process barrier: the parser sandbox subprocess returns a typed `ProbeOutput` *bytes* (JSON over stdout); the coordinator parses it as JSON, validates with Pydantic (Phase 0 `_ProbeOutputValidator`), sanitizes ([ADR-0008](../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md)), and only then merges. A compromised sandbox can return invalid output; it cannot reach back into the coordinator's Python state.

**Boundary 2** is the subprocess boundary: every byte the parser handles is treated as adversarial. The Phase 0 subprocess allowlist ([ADR-0012](../00-bullet-tracer-foundations/ADRs/0012-subprocess-allowlist-chokepoint.md)) governs *which binary* gets invoked; this phase adds *how the parser is invoked* — rlimits, env strip, read-only mount where the OS supports it.

---

## Goals (concrete, measurable)

1. **Zero successful parse-driven RCE** against the Phase 1 adversarial fixture corpus (≥ 50 crafted hostile inputs covering YAML bombs, JSON bombs, symlink escape, regex DoS, deep nesting, oversized inputs, hostile filenames). CI gates on this.
2. **Every probe runs in a per-execution parser sandbox** with rlimits enforced. No probe parses adversarial bytes in the coordinator process.
3. **Cache key derivation is tamper-resistant.** The cache key for any probe output covers (probe code version, schema version, BLAKE3 of *file bytes* — not file paths or `(path, size)` tuples — of every input matching `declared_inputs` after symlink and path-traversal filtering). A poisoned cache entry from one run cannot be rehydrated for a different repo with the same path layout.
4. **All Layer A inputs have hard size, depth, and time caps.** No `package.json` > 5 MB; no lockfile > 50 MB; no YAML depth > 64; no parse > 30 s wall-clock; no probe stdout > 64 MB. Exceeding any cap fails the probe loudly (confidence: low, error logged, audit recorded).
5. **The probe-output sanitizer's third pass** (size/depth cap on the schema slice) lands and is exercised by tests. No single string in `schema_slice` > 64 KB; nesting depth ≤ 32.
6. **Indirect prompt-injection markers are recorded but isolated.** Strings containing `<|`, `<<SYS>>`, `[INST]`, `ignore previous`, etc., in untrusted source fields get a `prompt_injection_marker_count` metadata field; the strings themselves are preserved verbatim but tagged so Phase 3+ knows to channel them via tool-output, never inline.
7. **`scip-typescript` (added in Phase 2) is not in the Phase 1 allowlist.** This phase adds only what Layer A needs: nothing. No new entries in `ALLOWED_BINARIES`. All A-layer probes are pure-Python parsers.
8. **Audit records cover every parsed byte** by hash. `runs/<ts>.json` per-probe entry includes the BLAKE3 of each input file consumed, that file's size, and the probe's exit status. Reconstruction of "what was parsed" is exact.
9. **The Phase 1 `repo-context.yaml`** parses against a strict schema — `additionalProperties: false` at every Layer A probe boundary (Phase 0 was loose under `probes.*`; this phase tightens for the probes it owns).
10. **No new outbound network capability.** The Phase 0 structural defense (no `httpx`/`requests`/`socket` imports under `src/codegenie/`) holds verbatim in Phase 1. No probe makes a network call; the schema validator runs from a bundled schema file; tree-sitter grammars (Phase 2's concern) are not introduced here.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          codegenie process (TRUSTED)                          │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │  CLI ─► Config Loader ─► RepoSnapshot ─► Probe Registry filter        │    │
│  │                                                                        │    │
│  │  ┌────────────────────────────────────────────────────────────────┐   │    │
│  │  │ Coordinator (asyncio Semaphore, per-probe timeout, isolation)  │   │    │
│  │  │  ┌─────────────────────────────────────────────────────────┐  │   │    │
│  │  │  │ CacheStore (content-addressed)                           │  │   │    │
│  │  │  │  - get(key)  put(key, output)                            │  │   │    │
│  │  │  │  - cache key: SHA-256(name | ver | schema_ver | inputs)  │  │   │    │
│  │  │  │  - inputs hash: BLAKE3-merkle of *byte content* of files │  │   │    │
│  │  │  │    matching declared_inputs (paths excluded from input)  │  │   │    │
│  │  │  └──────────────────────────────────────────────────────────┘  │   │    │
│  │  │                                                                  │   │    │
│  │  │  per-probe: dispatch ─► (cache hit? merge : run_sandboxed)      │   │    │
│  │  └─────────────────────┬────────────────────────────────────────────┘  │    │
│  │                        │  fork+exec each probe execution               │    │
│  │  ╔═══════════════════ TRUST BOUNDARY 1 ═══════════════════╗            │    │
│  └──┼────────────────────────────────────────────────────────┼──────────┘    │
│     │                                                          │              │
│  ┌──▼──────────────── Parser Sandbox (SEMI-TRUSTED) ──────────▼─────────┐   │
│  │  python -m codegenie.probes._sandbox <probe-module>                    │   │
│  │  rlimits applied immediately on entry:                                 │   │
│  │    RLIMIT_AS = 512 MB,   RLIMIT_CPU = 30 s,                            │   │
│  │    RLIMIT_FSIZE = 64 MB, RLIMIT_NOFILE = 256                           │   │
│  │  env = {PATH, HOME=<empty tmpdir>, LANG, LC_ALL,                       │   │
│  │         CODEGENIE_INPUT_MANIFEST=<json>}                               │   │
│  │  stdin = DEVNULL                                                        │   │
│  │  stdout/stderr = pipes (capped, line-buffered)                         │   │
│  │  cwd = analyzed-repo (Linux: read-only bind mount or unshare)          │   │
│  │  On macOS: no-network sandbox-exec profile (best-effort)               │   │
│  │                                                                         │   │
│  │  ┌──────────────────────────────────────────────────────────────────┐ │   │
│  │  │ Probe.run() — pure Python, no subprocess (Layer A)                │ │   │
│  │  │   - Reads ONLY files declared in declared_inputs                  │ │   │
│  │  │   - Each open: enforce size cap, follow_symlinks=False            │ │   │
│  │  │   - Parsers: yaml.CSafeLoader, json with c_make_scanner,          │ │   │
│  │  │     all with depth cap                                            │ │   │
│  │  │   - Emits ProbeOutput as JSON on stdout                           │ │   │
│  │  │  ╔═══════════════════ TRUST BOUNDARY 2 ════════════════╗         │ │   │
│  │  │  ║   adversarial bytes (analyzed-repo content)          ║         │ │   │
│  │  │  ╚══════════════════════════════════════════════════════╝         │ │   │
│  │  └──────────────────────────────────────────────────────────────────┘ │   │
│  └────────────────────────────────────────────────────────────────────────┘   │
│                                                                                │
│  ┌────────────────────────────────────────────────────────────────────────┐   │
│  │ Coordinator (resume after sandbox exit)                                 │   │
│  │   - Receive ProbeOutput JSON, length-checked, validated                 │   │
│  │   - _ProbeOutputValidator (Pydantic): JSONValue type, field-name regex  │   │
│  │   - OutputSanitizer.scrub: field-name + path-scrub + size/depth caps    │   │
│  │   - CacheStore.put: write blob (0600) + index append                    │   │
│  │   - Merge into RepoContext envelope                                     │   │
│  └────────────────────────────────────────────────────────────────────────┘   │
│                                                                                │
│  ┌────────────────────────────────────────────────────────────────────────┐   │
│  │ Schema Validator (Draft202012; additionalProperties: false per probe)   │   │
│  │ Writer: atomic, 0600/0700, no-symlink-target refusal                    │   │
│  │ AuditWriter: input-byte hashes + per-probe execution record             │   │
│  └────────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────────┘
```

The architecture is **the Phase 0 architecture plus a fork**. The Phase 0 coordinator stays. The Phase 0 sanitizer stays. The Phase 0 cache stays. What changes: every `Probe.run()` call goes through a fork-and-exec subprocess wrapper that applies rlimits before any adversarial byte is read. The coordinator and the parser never share an address space.

---

## Components

### Parser Sandbox (`src/codegenie/sandbox.py`)

- **Purpose:** Run a single probe's `.run()` method in a hardened subprocess so a parser bug or malicious input cannot pivot into coordinator address space, exfiltrate env vars, or escape the analyzed-repo cwd.
- **Trust level:** Semi-trusted. Treated as a hostile process by the coordinator after launch — the parent reads stdout as opaque bytes, parses as JSON with a size cap, validates with Pydantic.
- **Interface:** `async def run_in_sandbox(probe_class: type[Probe], snapshot: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`. Internally: forks `python -m codegenie.probes._sandbox <module> <class>`; passes inputs via a JSON manifest in `CODEGENIE_INPUT_MANIFEST` (resolved paths only — no Python objects); receives `ProbeOutput` via stdout JSON; non-zero exit → `SandboxProbeError`.
- **Isolation:**
  - `RLIMIT_AS = 512 MB`, `RLIMIT_CPU = 30 s`, `RLIMIT_FSIZE = 64 MB`, `RLIMIT_NOFILE = 256`, `RLIMIT_NPROC = 32`. Set in a `preexec_fn` before `exec`.
  - Env stripped to `{PATH, LANG, LC_ALL}` plus a fresh `HOME` pointing to a per-execution tempdir under `.codegenie/sandbox/<probe>/<uuid>/` mode 0700 (cleaned on exit).
  - `stdin = DEVNULL`; `stdout`/`stderr` capped at 64 MB / 1 MB respectively (parent kills the child if exceeded).
  - On Linux: `bwrap --ro-bind <analyzed-repo> <analyzed-repo> --bind <sandbox-tmpdir> <sandbox-tmpdir> --unshare-net --unshare-ipc --new-session` if `bwrap` is available (detected at startup, advisory only — its absence emits a structured warning but does not fail the gather).
  - On macOS: `sandbox-exec` with an inline profile denying network and write-outside-tmpdir, best-effort. Documented as best-effort because `sandbox-exec` is deprecated; no security claim is staked on macOS isolation beyond rlimits + env strip.
  - On Windows: not supported in Phase 1 (Phase 0 already excludes Windows from CI matrix).
- **Credentials accessed:** **None.** The launcher strips every credential-shaped env var; the read-only mount excludes the host `$HOME`. The sandbox process cannot read `~/.ssh`, `~/.aws`, `~/.codegenie/config.yaml`, or any LLM key. The Phase 0 `exec.run_allowlisted` env-strip rules apply here verbatim ([ADR-0012](../00-bullet-tracer-foundations/ADRs/0012-subprocess-allowlist-chokepoint.md)).
- **Audit emissions:** `probe.sandbox.start` with `{probe, pid, cwd, declared_inputs_count}`; `probe.sandbox.exit` with `{probe, pid, exit_status, rss_peak, wall_ms, stdout_bytes, stderr_bytes}`; `probe.sandbox.rlimit_exceeded` if a limit fires.
- **Tradeoffs accepted:**
  - **Fork-and-exec cost per probe: ~150–300 ms baseline.** With six Layer A probes and cold cache, that's ~1.5 s of pure sandbox overhead. Cache hits skip the sandbox entirely so steady-state is unaffected. The hot path that matters (continuous gather, Phase 14) is cache-hit-dominated.
  - **`bwrap` unavailability is silent on macOS dev hosts.** Local dev sees rlimits + env strip only. We accept this because (a) local dev runs on the engineer's own malicious-repo-aware judgment, (b) the load-bearing security claim is *CI* and *production gather workers* (Linux), and (c) requiring `bwrap` on macOS would block local development entirely.
  - **No syscall filter (seccomp-bpf) in Phase 1.** Worth the cost in the production gather worker (Phase 14) but bwrap + rlimits + read-only mount cover the dominant threats here; seccomp profiles for a Python interpreter are notoriously brittle and add Linux-only complexity for marginal gain at this phase.

### Coordinator (`src/codegenie/coordinator.py`) — modifications to Phase 0

- **Purpose:** Same as Phase 0 — dispatch probes, enforce per-probe timeout, isolate failures, merge outputs. This phase makes every probe execution go through the parser sandbox.
- **Trust level:** Trusted.
- **Interface:** Phase 0's interface preserved. New: `coordinator.run(probes, snapshot, *, sandboxed: bool = True)`. The default is sandboxed; `sandboxed=False` is *only* allowed in tests that pin probe behavior in-process (gated by a `pytest` fixture, not a runtime flag).
- **Isolation:** The coordinator runs *one* asyncio task per probe; that task calls `sandbox.run_in_sandbox(...)`. The Phase 0 cancel + SIGKILL on `1.5 × timeout_s` becomes a SIGTERM-then-SIGKILL of the sandbox child PID, with the process-tracking table covering subprocess descendants (relevant when Phase 1 still doesn't shell out, but Phase 2's `scip-typescript` will, and the invariant is set here).
- **Credentials accessed:** None directly; the coordinator reads `~/.codegenie/config.yaml` (0600) and writes to `.codegenie/cache/` (0700/0600).
- **Audit emissions:** Phase 0's `probe.start`/`probe.success`/`probe.failure`/`probe.timeout`/`probe.cache_hit`/`probe.skip` events extended with `sandbox_pid` and `sandbox_exit_status` fields when sandboxed.
- **Tradeoffs accepted:**
  - **The `sandboxed=False` test escape hatch is a real risk** — a probe that subtly relies on coordinator-process state will pass tests and fail in production. Mitigation: a `tests/adv/test_no_sandbox_bypass_in_prod.py` asserts that no production code path constructs the coordinator with `sandboxed=False`.

### CacheStore — modifications to Phase 0

- **Purpose:** Same as Phase 0 — content-addressed cache under `.codegenie/cache/`. Phase 1 changes *what content is addressed*: the cache key derives from the **byte content of every file matching `declared_inputs`**, not the file paths or `(path, size)` tuples.
- **Trust level:** Trusted (the cache is owned by `codegenie`); the cached *content* is treated as untrusted on read-back (re-validated through `_ProbeOutputValidator`).
- **Interface:** Phase 0's `get(key)` / `put(key, output)` / `key_for(probe, snapshot, task)`. The change is internal to `key_for`:
  - `inputs_hash` = BLAKE3 of the canonical concatenation of `(relative_path_bytes, file_bytes_blake3)` for every file matching `declared_inputs` after symlink filtering and path-traversal exclusion, sorted by relative path.
  - **Files are read once with `O_NOFOLLOW`**, size-capped (caller-defined; defaults to 50 MB per file, 200 MB aggregate), and rejected on cap exceeded — invalidating the cache lookup and forcing a sandbox run that will record the same cap violation.
  - **`O_NOFOLLOW` on macOS** is supported; on platforms where it is not, the cache key derivation refuses to read symlinks under any circumstance.
- **Why content-of-files-not-(path,size):** the Phase 0 `(path, size)` cache key was a Phase-0-scoped choice (the only file content that matters there is the file extension set; size + name suffices). For Layer A, a `package.json` *containing a different version pin* must invalidate the cache; size alone does not catch a single-character diff. Cache-key derivation must read content. This also closes a poisoning vector: under `(path, size)`, an attacker can craft a malicious lockfile with the same byte length as a benign one and rehydrate the benign cache entry.
- **Cache validation on read:** every `get(key)` deserializes the blob, re-runs `_ProbeOutputValidator` (Pydantic), and rejects the blob if validation fails (e.g., a future-format poison from a different probe version that happened to collide). On rejection the cache entry is deleted and a `cache.blob.invalid` audit event is emitted.
- **Permissions:** 0700 directory, 0600 file, per [ADR-0011](../00-bullet-tracer-foundations/ADRs/0011-codegenie-directory-permissions-model.md).
- **Credentials accessed:** None.
- **Audit emissions:** `cache.hit`, `cache.miss`, `cache.put`, `cache.blob.invalid`, `cache.symlink.skipped`, `cache.size_cap_exceeded`, `cache.aggregate_cap_exceeded`.
- **Tradeoffs accepted:**
  - **Reading file bytes for cache-key derivation is slower than reading sizes.** Per repo, this is the cost of one BLAKE3 pass over the declared inputs (Layer A is ~kilobytes to ~tens of MB), well within the 90s CI budget.
  - **Aggregate read cap of 200 MB** on Layer A is intentionally tight. A repo whose declared-inputs total exceeds 200 MB has bigger problems than this probe (and Layer B/C will not run either).

### Layer A Probes (six new probes)

All six inherit the Phase 0 `Probe` ABC verbatim ([ADR-0007](../../production/adrs/0007-probe-contract-preserved-poc-to-service.md)). Each declares `declared_inputs` precisely; the sandbox launcher refuses to provide files outside that declaration.

| Probe | `declared_inputs` | Parser used | Hard caps (file size / parse depth / parse time) |
|---|---|---|---|
| `LanguageDetectionProbe` (extended from Phase 0) | `["**/*.{js,mjs,cjs,ts,tsx,py,go,rs,json}"]` plus `Dockerfile*` (now in scope) | `os.scandir` (no parsing) | 50k files / N/A / 5 s |
| `NodeBuildSystemProbe` | `["package.json", "pnpm-workspace.yaml", "lerna.json", "nx.json", "turbo.json", ".nvmrc", ".node-version", "tsconfig*.json"]` | `json.loads` with `c_make_scanner`; `yaml.CSafeLoader` with depth cap; `tsconfig.json` parsed as JSONC with a hand-rolled comment stripper (no eval, no `vm`, no JSON5) | 5 MB / 64 / 10 s |
| `NodeManifestProbe` | `["package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "node_modules/*/package.json"]` (the last is **opt-in via `--with-node-modules`**; default off because `node_modules` is hostile by definition) | JSON / YAML / yarn-lock parser written from scratch (deterministic regex, line-bounded, no backtracking) | 50 MB / 64 / 30 s |
| `CIProbe` | `[".github/workflows/*.{yml,yaml}", ".circleci/config.yml", ".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml"]` | `yaml.CSafeLoader` for YAML; Jenkinsfile *not parsed* in Phase 1 — only its presence is recorded plus a small set of regex extractors (no eval-style execution; matches bounded by line) | 10 MB / 64 / 10 s |
| `DeploymentProbe` | `["deploy/**/*.{yml,yaml}", "k8s/**/*.{yml,yaml}", "kubernetes/**/*.{yml,yaml}", "Chart.yaml", "values*.yaml", "kustomization.yaml", "*.tf", "*.tf.json"]` | `yaml.CSafeLoader`; `hcl2` is **not added** in Phase 1 — Terraform/HCL parsing is deferred until a proper parser sandbox profile exists (Phase 2). `*.tf` files are *enumerated by path only* (no parsing); the schema slice records `terraform_present: true` without parsed structure | 10 MB / 64 / 10 s |
| `TestInventoryProbe` | `["package.json", "vitest.config.*", "jest.config.*", "playwright.config.*", ".mocharc.*", "coverage/lcov.info"]` plus a filesystem walk for `*.test.{js,ts,mjs,cjs,tsx}`, `*.spec.{js,ts,mjs,cjs,tsx}` | `json.loads`, `yaml.CSafeLoader`, name-pattern matching | 5 MB / 64 / 10 s |

Per-probe specifics:

#### `NodeBuildSystemProbe`
- **Purpose:** Detect package manager, Node version constraints, scripts, bundler, TypeScript config. Per `localv2.md §5.1 A2`.
- **Trust level:** Semi-trusted (parses adversarial JSON/YAML).
- **Interface:** Phase 0 `Probe` ABC. `applies_to_tasks = ["*"]`, `applies_to_languages = ["javascript", "typescript"]`, `requires = ["language_detection"]`, `timeout_seconds = 30`.
- **Isolation:** Runs inside the parser sandbox. **Does not call `node --version`** in Phase 1 (despite `localv2.md` mentioning it); the probe reads `.nvmrc` / `engines` / `volta` fields as declarations only. Invoking `node` opens an RCE path (a malicious `$PATH` entry, a hostile `~/.npmrc`'s `script-shell` config) for a marginal data-quality gain. Phase 2 may revisit if needed; Phase 1 prefers static evidence.
- **Credentials accessed:** None.
- **Audit emissions:** `probe.start`/`probe.success`, plus `probe.evidence` with input-file BLAKE3 hashes.
- **Tradeoffs accepted:**
  - **`tsconfig.json`'s `extends:` chain is followed at most 4 levels deep** and only to relative paths under the repo root. A path escaping the repo or a circular chain fails the parse with `confidence: low` and a recorded error. `localv2.md` does not call this out; the security lens makes it explicit.
  - **Skipped: Volta config, Bun-specific config, deeply nested workspace patterns.** Phase 1 documents what's parsed; anything richer is a deliberate Phase-2 addition. The `NodeBuildSystem.schema.json` has `additionalProperties: false` so adding fields is an explicit PR.

#### `NodeManifestProbe`
- **Purpose:** Parse `package.json` + lockfile, enumerate dependencies (direct/dev/peer/optional/bundled), detect native modules per `localv2.md §5.1 A3`.
- **Trust level:** Semi-trusted; the **single most dangerous parser** in Phase 1 because lockfiles are large, deeply nested, and untrusted.
- **Interface:** Phase 0 `Probe` ABC. `timeout_seconds = 30`.
- **Isolation:** Parser sandbox. Lockfile parsing is the load-bearing capped parse: 50 MB file cap, 64 nesting depth cap, 30 s wall-clock cap. The `yarn.lock` parser is a hand-rolled line-based scanner — no regex backtracking, no recursion, no `eval`. The `pnpm-lock.yaml` parser uses `yaml.CSafeLoader` (banned by Phase 0 `forbidden-patterns` to use anything else).
- **Credentials accessed:** None.
- **Audit emissions:** `probe.start`/`probe.success`/`probe.failure`/`probe.timeout`, plus `manifest.native_module_detected` (with the native module name and version — useful for Phase 7 distroless migration triage).
- **Tradeoffs accepted:**
  - **Native module catalog is YAML in `src/codegenie/catalogs/native-modules.yaml`.** The catalog is part of the codegenie supply chain and is `additionalProperties: false`-validated at module load. Adding a native module is a PR, not a runtime config edit.
  - **The probe refuses to parse a lockfile if the `package.json` integrity check disagrees with the lockfile's recorded integrity.** This is *not* a security check on the supply chain (we are not the audit tool); it is a probe-confidence signal — disagreement triggers `confidence: low` and an `integrity_mismatch: true` field that downstream phases use to decide whether to trust the manifest at all.
  - **`node_modules/*/package.json` parsing is opt-in.** Default off because `node_modules` content is attacker-controlled and there are *many* such files. With `--with-node-modules`, each `package.json` inside `node_modules/` is parsed under the same sandbox + size caps; the aggregate input cap is raised to 1 GB.

#### `CIProbe`
- **Purpose:** Detect CI provider, workflow files, image-build presence, test/smoke commands per `localv2.md §5.1 A4`.
- **Trust level:** Semi-trusted.
- **Interface:** Phase 0 `Probe` ABC. `timeout_seconds = 10`.
- **Isolation:** Parser sandbox.
- **Credentials accessed:** None.
- **Audit emissions:** Standard probe lifecycle.
- **Tradeoffs accepted:**
  - **GitHub Actions `${{ ... }}` expressions are recorded verbatim as strings**, never evaluated. If a workflow uses `${{ secrets.NPM_TOKEN }}`, the probe records the literal string `${{ secrets.NPM_TOKEN }}` — it does not resolve the secret (it doesn't have access) and does not flag the string as a secret (because it is a *reference* to a secret, not the secret itself). The `_ProbeOutputValidator` field-name regex (Phase 0) catches keys named `*_token`, `*_secret`, etc., as a separate concern.
  - **Jenkinsfile is detected by path only.** Parsing Jenkins's Groovy DSL safely is hard; this phase records presence + path + size and leaves structured extraction to a future phase. A regex tries to pick the unit-test command (`sh 'pnpm test'` patterns) but is gated to a single capture group, bounded match length.
  - **`build_matrix` is parsed but limited to depth 3.** A workflow file using deeply nested anchor references hits the YAML depth cap (64) before this matters; the matrix-specific cap is belt-and-suspenders.

#### `DeploymentProbe`
- **Purpose:** Detect deployment style (Helm / Kustomize / plain manifests / Terraform), image reference, health probes, security context per `localv2.md §5.1 A5`.
- **Trust level:** Semi-trusted.
- **Interface:** Phase 0 `Probe` ABC. `timeout_seconds = 15`.
- **Isolation:** Parser sandbox. **Helm template rendering is not performed.** A `values.yaml` is parsed as YAML; a `Chart.yaml` is parsed as YAML; the *templated* output of `helm template` is never produced because `helm` is not in the allowlist (and adding `helm` opens a substantial RCE surface — Helm has shipped template-evaluation CVEs). The deployment evidence collected is the *raw configuration*; what gets generated at deploy time is out of scope for this probe.
- **Credentials accessed:** None.
- **Audit emissions:** Standard probe lifecycle + `deployment.terraform_present` (path-only) + `deployment.kustomization_resource_path_outside_repo` warning if `kustomization.yaml#resources:` references paths outside the repo root (a path-traversal smell).
- **Tradeoffs accepted:**
  - **No Helm rendering ⇒ image references in Helm charts that depend on template expressions are recorded as the literal template** (e.g., `{{ .Values.image.repository }}:{{ .Values.image.tag }}`). Downstream phases must resolve the template via the same `values.yaml` the probe captures. This is a deliberate fact-not-judgment line: render is interpretation; capture is evidence.
  - **`*.tf` enumerated by path only.** A future phase adds `hcl2` parsing inside a more restrictive sandbox profile.
  - **Kustomize overlay traversal capped at depth 5 and 50 total files.** Beyond that the probe records `confidence: low` and a `kustomize_overlay_depth_exceeded` warning. Real Kustomize trees don't approach this; pathological ones get rejected loudly.

#### `TestInventoryProbe`
- **Purpose:** Detect test framework, test commands, test counts, coverage data per `localv2.md §5.1 A6`.
- **Trust level:** Semi-trusted.
- **Interface:** Phase 0 `Probe` ABC. `timeout_seconds = 10`.
- **Isolation:** Parser sandbox. Test files are *enumerated* (count by extension/pattern) but **not parsed**; the count is the evidence.
- **Credentials accessed:** None.
- **Audit emissions:** Standard probe lifecycle.
- **Tradeoffs accepted:**
  - **`coverage/lcov.info` is parsed only for its summary** (total lines/branches, hit/miss counts). The file format is line-oriented and unambiguous; a custom line-by-line parser with no regex backtracking handles it. Hard 50 MB cap.
  - **Test counts may be inaccurate if the repo uses dynamic test generation** (e.g., `each(...)` patterns at runtime). The probe reports `unit_test_count` and `unit_test_count_static: true` to signal the limitation.

### Output Sanitizer — modifications to Phase 0 ([ADR-0008](../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md) extended)

- **Purpose:** Same as Phase 0 — the single path from `ProbeOutput` to disk. Phase 1 adds a third pass.
- **Trust level:** Trusted; runs in the coordinator process.
- **Interface:** `OutputSanitizer.scrub(probe_output, repo_root) -> SanitizedProbeOutput`. Three passes (fixed order):
  1. Field-name regex filter (Phase 0).
  2. Absolute → relative path scrubbing (Phase 0).
  3. **NEW: Size/depth cap on `schema_slice`.** No single string > 64 KB; total slice size ≤ 1 MB (a deliberate ceiling — `repo-context.yaml` indexes evidence, it does not inline it); nesting depth ≤ 32. Exceeding any cap rejects the probe output with `OversizedSchemaSliceError` and marks the probe failed (`confidence: low`); the human-facing report makes the failure visible.
- **Why this is in the sanitizer and not the probe:** the sanitizer is the chokepoint; the cap is a *system* invariant, not a per-probe one. A future probe that happens to produce a large schema slice does not get to negotiate the cap; the system rejects it.
- **Credentials accessed:** None.
- **Audit emissions:** `sanitizer.field_name_redacted` (no-op expected), `sanitizer.path_scrubbed` (count of paths rewritten), `sanitizer.size_cap_exceeded`, `sanitizer.depth_cap_exceeded`.
- **Tradeoffs accepted:**
  - **Pass 3 is a no-op in well-formed runs.** The cap is a safety net, not a normal path. If it fires, that probe needs redesign.
  - **No prompt-injection detection in the sanitizer.** Strings that look like prompt-injection payloads are preserved verbatim and *tagged* via a separate probe-side metadata field (`prompt_injection_marker_count`). The sanitizer doesn't try to filter content; it only enforces structural limits.

### Schema Validator — modifications to Phase 0

- **Purpose:** Same as Phase 0 — `Draft202012Validator`, schema as package data. Phase 1 adds the six Layer A probe sub-schemas (`probes/<name>.schema.json`) and tightens `additionalProperties` per probe.
- **Trust level:** Trusted.
- **Interface:** Phase 0 unchanged.
- **Isolation:** N/A — runs in the coordinator process *after* sanitization.
- **Credentials accessed:** None.
- **Audit emissions:** `schema.validation_passed` / `schema.validation_failed` with field path.
- **Tradeoffs accepted:**
  - **Each Layer A probe sub-schema sets `additionalProperties: false`.** Phase 0's policy allowed `true` under `probes.*`; for Phase 1's *own probes*, the security lens tightens. Adding a field is an explicit schema PR.
  - **CI gate:** the produced `repo-context.yaml` against a real fixture repo must validate, or the build fails. This is the roadmap-stated exit criterion; the security lens additionally asserts that **invalid output is written with a `.invalid` suffix** so a CI failure preserves the artifact for triage instead of silently dropping it.

### AuditWriter — modifications to Phase 0

- **Purpose:** Same as Phase 0 — write `runs/<utc-iso>-<short-hash>.json` per gather. Phase 1 extends the per-probe entry with input-byte evidence.
- **Trust level:** Trusted.
- **Interface:** Phase 0 unchanged.
- **Credentials accessed:** None.
- **Audit emissions:** The audit record is itself the emission; it contains per-probe: `{name, version, sandbox_pid, exit_status, cache_hit, wall_ms, rss_peak_kb, declared_inputs: [{relative_path, sha256_blake3, size_bytes}], stdout_bytes, errors, warnings}`.
- **Tradeoffs accepted:**
  - **The audit record can grow** (each input file contributes ~80 bytes of metadata). 100 declared inputs per probe × 6 probes = ~50 KB per run. Acceptable; this is exactly what makes "what did Phase 1 see on commit X" answerable.
  - **No HMAC signing.** Inherited from Phase 0 — the threat model for HMAC on a developer workstation does not close (per [ADR-0004](../00-bullet-tracer-foundations/ADRs/0004-probe-execution-audit-anchor.md) / Phase 0 §2.12). Phase 14 revisits.

---

## Data flow

```
                                   TRUST BOUNDARY 1 (process)
                                   TRUST BOUNDARY 2 (subprocess + analyzed-repo bytes)

  CLI ─► Config Loader ─► RepoSnapshot   [trusted, trusted, trusted]
   │
   ▼
  Coordinator dispatch (per probe)
   │
   ▼
  CacheStore.key_for(probe, snapshot)
   │   reads declared_inputs file BYTES under O_NOFOLLOW + size caps   ◄── crosses BOUNDARY 2 briefly,
   │   computes BLAKE3-merkle of byte content                            inside the coordinator,
   │   produces SHA-256(name|ver|schema_ver|inputs)                      but only to hash — no parsing
   ▼
  CacheStore.get(key)
   │   hit → deserialize blob → _ProbeOutputValidator → SanitizedProbeOutput → merge   [trusted re-validation]
   │   miss → fall through
   ▼
  sandbox.run_in_sandbox(probe, snapshot, ctx)        ─► forks subprocess
                                                       ─► rlimits applied PRE-exec
                                                       ─► env stripped
                                                       ─► cwd = analyzed-repo (Linux: ro mount)
                                                       ─► stdin=DEVNULL, stdout/stderr capped
   │                                                  ════════ BOUNDARY 1 ════════
   │                                                  inside the sandbox: probe.run()
   │                                                    ─► open(decl_input, O_NOFOLLOW)
   │                                                    ─► size cap check
   │                                                    ─► parser with depth cap        ════ BOUNDARY 2 ═══
   │                                                    ─► ProbeOutput → JSON → stdout    (adversarial bytes)
   │
   ▼
  Parent reads stdout (length-capped at 64 MB)
   │
   ▼
  json.loads (with c_make_scanner, depth cap)         [parser still adversarial — JSON, not pickle]
   │
   ▼
  _ProbeOutputValidator (Pydantic, JSONValue, field-name regex)   [first structural defense]
   │
   ▼
  OutputSanitizer.scrub (3 passes)                     [second structural defense]
   │
   ▼
  CacheStore.put(key, sanitized)                        [0600 blob, atomic write, index append]
   │
   ▼
  Merge into RepoContext envelope                       [coordinator-private state]
   │
   ▼
  Schema Validator (Draft202012, additionalProperties: false per Layer A probe)
   │
   ▼
  Writer (atomic, 0600/0700, no-symlink-target refusal)
   │
   ▼
  AuditWriter (input-byte hashes + per-probe exec record)
   │
   ▼
  Exit 0 / 2 / 3 / 4 / 5 (Phase 0 exit codes preserved)
```

Crossings:
- **BOUNDARY 1 (coordinator ↔ sandbox process):** crossed exactly once per probe execution per gather (cache misses only). Every byte returning across is JSON, length-bounded, and re-validated.
- **BOUNDARY 2 (sandbox ↔ analyzed-repo bytes):** crossed inside the sandbox, where rlimits and parsers with caps contain the damage. Coordinator never reads analyzed-repo bytes for parsing — only for cache-key BLAKE3 (a write-once, never-interpreted operation).

---

## Failure modes & recovery

| Failure | Detected by | Containment | Recovery |
|---|---|---|---|
| Probe parser hits YAML billion-laughs bomb | `yaml.CSafeLoader` depth cap | Parser raises within sandbox; sandbox subprocess catches into `ProbeOutput.errors`, exits 0 with `confidence: low` | Probe marked failed; coordinator continues; audit records `parse.depth_cap_exceeded` |
| Probe parser hits JSON 1 GB string OOM | `RLIMIT_AS = 512 MB` | Sandbox subprocess killed by kernel | Parent observes `exit_status != 0`, records `sandbox.rlimit_exceeded`; probe marked failed; coordinator continues |
| Probe wall-clock exceeds 30 s (`RLIMIT_CPU`) | Kernel | Sandbox subprocess SIGXCPU'd | Parent observes signal in exit status; probe marked failed |
| Probe `stdout` exceeds 64 MB | Parent's bounded pipe reader | Parent SIGKILLs sandbox child | Probe marked failed; `sandbox.stdout_cap_exceeded` audited |
| Symlink in `declared_inputs` points outside repo | `O_NOFOLLOW` open (cache key); sandbox `bwrap` ro-bind (parse) | `O_NOFOLLOW` fails with `ELOOP`; bwrap refuses the path | Symlink skipped + audited; cache-key derivation excludes the file; probe parses without that input |
| Path traversal via `kustomization.yaml#resources: ["../../../etc/passwd"]` | `DeploymentProbe` resolves the path relative to repo root and refuses if escape detected | Path rejected by probe; recorded as warning | Probe completes with `confidence: medium`; `deployment.kustomization_resource_path_outside_repo: true` |
| Hostile filename: a file named `package.json\x00.txt` | Python `os` rejects NUL in paths; secondary: `pathlib.Path` rejects | `FileNotFoundError` raised in sandbox | Probe records error; coordinator continues |
| Hostile filename: a 1 MB filename | Most filesystems reject; if accepted, `RLIMIT_NOFILE`/path length caps fire | Open fails | Probe records error |
| Sandbox subprocess refuses to exit on SIGTERM | Coordinator's `1.5 × timeout_s` SIGKILL | SIGKILL the sandbox PID + descendants via process-tracking table | Probe marked failed; `probe.timeout` audited |
| Cache blob is corrupt (truncation, JSON parse failure) | `CacheStore.get` deserialize | Cache entry deleted, `cache.blob.invalid` audited | Forces a sandbox run; cache rehydrates on success |
| Cache blob deserializes but fails `_ProbeOutputValidator` (poison) | Re-validation on read | Cache entry deleted, `cache.blob.poisoned` audited | Forces a sandbox run |
| `pnpm-lock.yaml` contains `!!python/object` | `yaml.CSafeLoader` does not load Python tags | Parse error within sandbox | Probe records `confidence: low`, `unsafe_yaml_tag_seen: true` |
| `package.json` is 200 MB | Per-file size cap | Open refuses; sandbox child records the size and exits 0 with `confidence: low` | Probe failed; coordinator continues; audit records `manifest.size_cap_exceeded` |
| `tsconfig.json#extends:` chain depth exceeded | Probe-internal counter | Probe records `tsconfig.extends_depth_exceeded` warning | Probe completes with `confidence: medium` |
| Aggregate declared-inputs > 200 MB | Cache-key derivation aggregate cap | Cache-key derivation aborts | Probe is not run from cache; sandbox run is attempted; cap is re-enforced inside; probe records `confidence: low` |
| A probe output contains a string with embedded `<\|im_start\|>` (prompt-injection marker) | Probe-side scan against a small marker set | String preserved verbatim; `prompt_injection_marker_count` incremented in schema slice | Future Phase 3+ context-assembly code reads the marker count and routes the string via tool-output channel, never inlined into a prompt — *this phase only records, doesn't filter* |
| Probe output exceeds 1 MB schema slice | OutputSanitizer pass 3 | `OversizedSchemaSliceError` raised; probe output rejected | Probe marked failed; gather continues with that probe's slice absent |
| Probe output field name matches secret-shape regex | `_ProbeOutputValidator` | `SecretLikelyFieldNameError` raised; probe output rejected | Probe marked failed; gather continues |
| Sandbox sees a planted `node` binary on `$PATH` and tries to exec | Phase 1's `NodeBuildSystemProbe` explicitly does **not** call `node`; the subprocess allowlist would block it anyway (Phase 0 [ADR-0012](../00-bullet-tracer-foundations/ADRs/0012-subprocess-allowlist-chokepoint.md)) | Blocked structurally | N/A |
| `python -m codegenie.probes._sandbox` itself contains a bug (parses input manifest as `pickle`) | Code review + `forbidden-patterns` hook banning `pickle.loads` from `src/codegenie/` | The bug cannot land per Phase 0 invariants | N/A |
| Two concurrent `codegenie gather` runs on the same repo collide on cache writes | Atomic write (`.tmp` → `os.replace`) + per-file `0600` | Last writer wins for the blob; index appended with `O_APPEND` (atomic for records ≤ `PIPE_BUF`) | No corruption; concurrent gathers complete independently |
| Hostile fixture in adversarial-test corpus achieves RCE during CI | CI failure (test asserts no RCE) | Build blocked | Investigate the regression; the offending probe/parser is reverted until fixed |

The malicious-failure cases above are not an exhaustive list — they are the ones the test corpus is sized to cover.

---

## Resource & cost profile

**The cost of security in this phase:**

- **Sandbox fork-and-exec overhead.** ~150–300 ms per probe execution. Six Layer A probes × cold cache = ~1.5 s wall-clock added. Warm cache (cache-hit): zero overhead, sandbox is not invoked.
- **Cache-key derivation reading file bytes.** O(input MB) at BLAKE3 speed (~3 GB/s). For a typical Node.js repo (~5 MB of declared inputs across Layer A), ~2 ms. Trivial.
- **Audit-record growth.** ~50 KB per run with per-input-file hashes (vs Phase 0's ~2 KB). After a year of nightly continuous gather: ~18 MB per repo. Still acceptable.
- **Schema sub-schema files.** Six new `probes/*.schema.json` files in package data; ~30 KB total. No runtime cost beyond Phase 0's `Draft202012Validator` compile (cached via `lru_cache`).
- **CI walltime.** The Phase 0 ≤ 90 s p95 target holds. Adversarial fixture suite adds ~20 s sequential, parallelized. Net CI: ~100–110 s p95. We exceed the Phase 0 target deliberately; the security gate is worth the spend.
- **Tokens per run.** 0. Phase 1 introduces zero LLM. (`fence` CI job enforces.)

What we are **not** spending on:
- No syscall filtering (`seccomp`) — deferred to Phase 14's production gather worker where the CI cost story justifies it.
- No microVM isolation — that's Phase 5's job ([production ADR-0012](../../production/adrs/0012-microvm-sandbox-for-trust-gates.md)). A sandbox-per-probe-execution under bwrap is the right cost/benefit point for a *parser*, not the right point for *executing a candidate diff*.
- No reproducibility verification of the gather output — deferred to Phase 14 when continuous gather makes "did the same commit produce the same context" answerable at scale.

---

## Test plan

### Unit tests (`tests/unit/`)

- `test_sandbox_rlimits.py` — fork a no-op child with each rlimit; verify the kernel enforces it; assert the parent observes the correct exit status.
- `test_sandbox_env_strip.py` — set `AWS_ACCESS_KEY_ID`, `OPENAI_API_KEY`, `SSH_AUTH_SOCK`, `GITHUB_TOKEN` in the parent; assert the sandbox child does not see them.
- `test_sandbox_stdout_cap.py` — child emits >64 MB; parent SIGKILLs; exit status records `stdout_cap_exceeded`.
- `test_sandbox_cwd_jail_linux.py` — *Linux only*, skip otherwise: assert `bwrap` ro-bind prevents writes outside `<sandbox-tmpdir>`.
- `test_cache_key_byte_content.py` — two `package.json` files with same size but different content produce different cache keys.
- `test_cache_key_symlink_excluded.py` — a symlink in `declared_inputs` is excluded from key derivation; a `cache.symlink.skipped` audit event is emitted.
- `test_cache_blob_poison_rejected.py` — write a hand-crafted blob that decodes to a `_ProbeOutputValidator`-rejecting structure; assert `CacheStore.get` deletes it and returns `None`.
- `test_sanitizer_size_depth_caps.py` — schema slice with a 100 KB string raises `OversizedSchemaSliceError`; depth 33 raises `OversizedSchemaSliceError`.
- `test_node_manifest_yarn_lock_no_regex_backtracking.py` — fixture `yarn.lock` constructed to be pathological for a naive regex; parser completes in < 1 s on a 10 MB file.
- `test_deployment_probe_kustomize_escape.py` — `kustomization.yaml` with `resources: ["../../../etc/passwd"]` produces a `kustomization_resource_path_outside_repo: true` warning, parses the rest, exits non-fatal.
- `test_schema_validator_per_probe_additional_props.py` — each of the six Layer A sub-schemas rejects unknown fields.
- `test_audit_record_input_byte_hashes.py` — gather a tiny fixture; audit record contains BLAKE3 + size for every declared input.
- `test_no_node_invocation.py` — `NodeBuildSystemProbe` does not appear in the subprocess audit table; no `node` in `ALLOWED_BINARIES`.

### Integration tests (`tests/integration/`)

- `test_phase1_e2e_real_repo.py` — clone a small real Node.js repo at a pinned commit (no network during test — fixture committed); run `codegenie gather`; assert all six Layer A probes produce schema-valid output; assert second run hits cache for all six.
- `test_phase1_e2e_monorepo.py` — pnpm-workspaces monorepo fixture with 5 packages; assert `LanguageDetectionProbe.monorepo == true`, `NodeBuildSystemProbe.package_manager == "pnpm"`, `NodeManifestProbe` lists all 5 package.json files.
- `test_phase1_e2e_cache_hit_no_sandbox.py` — instrument the sandbox launcher; assert second run forks zero sandboxes when all probes are cache-hits.

### Adversarial tests (`tests/adv/`) — the load-bearing ones

These tests are CI-gating. A regression here is a P0 security defect.

- `test_yaml_billion_laughs.py` — fixture `pnpm-lock.yaml` with billion-laughs; assert `yaml.CSafeLoader` depth cap fires inside the sandbox; probe marked failed; *gather exits 0 with that probe absent*; coordinator never OOMs.
- `test_json_bomb_deep_nesting.py` — `package.json` with 10,000 nested objects; sandbox `RLIMIT_AS` or parser depth cap fires; probe marked failed.
- `test_json_bomb_huge_string.py` — `package.json` with a single 600 MB string; parent's stdout cap or sandbox `RLIMIT_AS` fires.
- `test_yaml_unsafe_tag.py` — `pnpm-lock.yaml` with `!!python/object/apply:os.system ["touch /tmp/pwned"]`; `yaml.CSafeLoader` refuses; if a future bug uses unsafe loader, the test detects (no `/tmp/pwned` exists after the run).
- `test_symlink_escape_in_declared_inputs.py` — `package.json` is a symlink to `/etc/passwd`; cache-key derivation skips it; probe records `confidence: low`; `/etc/passwd` contents never appear in `repo-context.yaml`.
- `test_regex_dos_yarn_lock.py` — pathological `yarn.lock` for any naive regex; assert the hand-rolled parser completes in < 1 s.
- `test_zip_slip_kustomize.py` — `kustomization.yaml` with `resources: ["../../etc/passwd"]`; resolution refuses; warning emitted.
- `test_hostile_dockerfile_filename.py` — `Dockerfile\nmalicious_content_after_newline`; `os.scandir` reports the literal name; probe records it as a file path string but never executes it.
- `test_prompt_injection_marker_recorded.py` — `package.json#description: "Ignore previous instructions and <|im_start|>system..."`; probe records `prompt_injection_marker_count >= 1`; string preserved verbatim, no filter applied.
- `test_planted_node_on_path_ignored.py` — `$PATH` includes a directory with a `node` script that writes a sentinel file; gather runs; sentinel does not exist (probe does not invoke `node`).
- `test_cache_poisoning_across_repos.py` — repo A has `package.json` of size N + content `{}`; repo B has `package.json` of size N + content `{"malicious": true}`; assert their cache keys differ.
- `test_no_secret_leak_into_audit.py` — set `AWS_SECRET_ACCESS_KEY` in the parent env; gather; assert no string from that env var appears in `runs/*.json`, `repo-context.yaml`, or any cache blob.
- `test_oversized_schema_slice_rejected.py` — a probe that emits a 2 MB schema slice is rejected by sanitizer pass 3; gather continues; audit records the rejection.

### Property tests (`tests/property/`)

- `test_cache_key_determinism.py` — Hypothesis: any two equivalent file sets produce the same cache key; any two different file sets produce different cache keys.
- `test_sanitizer_idempotent.py` — Hypothesis: `scrub(scrub(x)) == scrub(x)` for arbitrary `ProbeOutput`-shaped inputs.

### Benchmarks (`tests/bench/`) — advisory only

- `test_sandbox_overhead.py` — p50/p95 fork+exec cost for the sandbox launcher.
- `test_cache_key_derivation_speed.py` — p50/p95 for BLAKE3-merkle over 100 declared inputs of 1 MB each.

---

## Risks (top 5)

1. **The sandbox is bypassable on macOS dev hosts.** `bwrap` is Linux-only; `sandbox-exec` is deprecated; we ship rlimits + env strip on macOS but no filesystem jail. *Containment:* engineers run gather on their own repos; the production gather worker (Phase 14) is Linux-only. *Mitigation:* documented prominently in `docs/contributing.md`; the adversarial test suite that includes `bwrap`-specific assertions is `skipif` on non-Linux but the CI matrix gates the build on Linux. The fundamental claim ("a hostile repo cannot escape the analyzer at scale") rests on the production worker, not local dev.
2. **Cache-key derivation reads file bytes for content hash — symlink races.** Between the `O_NOFOLLOW` open for hashing and the sandbox's read for parsing, an attacker with concurrent write access to the analyzed repo could swap the file. *Containment:* gather treats the analyzed repo as a snapshot at `git_commit` time; if the repo is modified mid-gather, the worst case is a cache key for content the probe never sees — leading to `_ProbeOutputValidator` rejection on the next read. *Mitigation:* document the assumption; in production gather (Phase 14), gather operates on a freshly-cloned worktree, not a shared workspace.
3. **`yaml.CSafeLoader` and `json` with `c_make_scanner` have CVEs.** A future `pyyaml` or `cpython` CVE in the YAML/JSON parser bypasses our depth caps. *Containment:* Phase 0's `pip-audit` + `osv-scanner` + Dependabot watch `pyyaml`; the sandbox's rlimits remain a backstop. *Mitigation:* the `security` CI job blocks PRs on HIGH/CRITICAL vulns affecting any pinned dep; the YAML parser cap is a defense-in-depth, not the only defense.
4. **The "no synchronous gitleaks" decision from [ADR-0008](../00-bullet-tracer-foundations/ADRs/0008-output-sanitizer-two-pass-chokepoint.md) means an embedded credential value (not field name) in a probe output flows to the cache and to `repo-context.yaml`.** Pre-commit and CI gitleaks catch it at commit time; gather does not. *Containment:* `repo-context.yaml` files are `0600` and inside `.codegenie/` which is `.gitignore`'d by default. *Mitigation:* Phase 11 (PR-opening) runs gitleaks over the proposed PR diff before opening — the credential cannot reach a real PR. The structural defenses (field-name regex, path scrubber, size cap, JSONValue type) carry the load.
5. **Adversarial test corpus drift.** New parsers and probes added Phase 2+ may introduce attack surfaces not covered by the Phase 1 fixture set. *Containment:* each new probe in Phase 2 ships its own adversarial fixtures as a PR-merge precondition (enforced by an `import-linter`-style "probe must have adv fixtures" rule in CI). *Mitigation:* Phase 2's design phase reads this risk list and inherits the discipline.

---

## Acknowledged blind spots

- **Indirect prompt injection is detected but not filtered.** The probe records `prompt_injection_marker_count` but preserves the offending string verbatim because *Phase 3+ has not yet defined the channel discipline* for repo-derived strings entering LLM context. Phase 1 captures the signal; the structural use is Phase 3's job to implement. If Phase 3 ships before this signal is consumed, we have collected metadata that nothing reads.
- **Helm template rendering not performed.** A `values.yaml` field that resolves to a private registry URL at render time is recorded as a raw template, not as the URL. Downstream phases that need the resolved image must render Helm themselves under their own sandbox profile.
- **`hcl2` / Terraform parsing deferred.** Terraform-defined services are recorded by path only. Phase 2 closes this when a richer parser sandbox profile lands.
- **`Jenkinsfile` parsed by regex only.** Sufficient for "this repo uses Jenkins"; insufficient for "this is the unit-test command in Jenkins." Phase 2 may revisit if a real consumer needs it.
- **The sandbox's tempdir on macOS is under `$TMPDIR` and inherits `$TMPDIR`'s permissions.** On most macOS hosts that's `0700` for the user already, but the security claim leans on macOS defaults rather than on enforcement.
- **The sandbox child can still consume up to 30 s of CPU and 512 MB of RSS.** That is a deliberate ceiling, not a cap — a malicious repo could absorb 30 s per probe × 6 probes per gather. In a per-repo, per-engineer-invocation context this is a denial-of-service against one gather, not against the engineer's host. In Phase 14's continuous gather, a per-repo total-budget cap (separate concern, deferred) is required.
- **We do not verify the integrity of `pyyaml`/`hatchling`/etc. beyond `uv.lock` hash pinning.** Supply-chain attacks against the resolver (lockfile injection during `uv lock`) are out of scope for this phase. Phase 16 (production hardening) revisits with sigstore / Cosign for the codewizard-sherpa wheel itself.

---

## Open questions for the synthesizer

1. **Is the per-probe sandbox overhead acceptable given the Phase 0 ≤ 90 s CI walltime target?** The security lens overshoots Phase 0's target by ~10–20 s on cold-cache integration tests; we judge it worth it. The performance lens will likely argue for in-process parsing with caps but no fork. The synthesizer should weigh: how much of the Phase 1 attack surface (YAML bombs, JSON bombs, deep nesting, regex DoS) does *in-process parsing with caps* actually leave open, vs the sandbox's marginal benefit on top of caps? My claim: in-process caps catch ~80% of the threats; the sandbox catches the remaining ~20% (parser CVEs, memory-unsafety in any C extension we use, `pickle`-style escapes in any future parser). The synthesizer's call is whether 20% is worth ~1.5 s per cold gather.
2. **Should cache-key derivation read file bytes (this design) or `(path, size)` (Phase 0)?** This design argues bytes-required for Layer A because *a single character change to `package.json` must invalidate the cache*. The performance lens will likely argue size + mtime. My counter: mtime is forge-able under `actions/cache` restore, and size-only is exploitable for cache poisoning. The synthesizer should consider whether BLAKE3 over Layer-A-sized inputs is anywhere close to a hot path (it isn't), in which case bytes-required is the right answer.
3. **Should `NodeBuildSystemProbe` invoke `node --version`?** This design says no. `localv2.md §5.1 A2` says yes. The synthesizer should adjudicate: is the data-quality gain (knowing the *actual* installed Node version, not just the declared constraint) worth opening the host-`PATH` attack surface? My recommendation is no, but I want this argued explicitly because `localv2.md` is the contract.
4. **Should `node_modules/*/package.json` parsing be on or off by default?** This design says off. The performance and best-practices lenses may want it on for richer native-module detection. The threat is that `node_modules` is attacker-controlled bytes at scale (thousands of files), and the failure mode of parsing them all is denial-of-service against the gather itself.
5. **Is the third sanitizer pass (size/depth caps) load-bearing or defense-in-depth?** I argue load-bearing — without it, a probe with a programmer error could emit a 200 MB schema slice and the schema validator would happily accept it. The synthesizer should decide whether to keep all three passes as enforced gates or to demote pass 3 to a warning-only.
6. **Should we record `prompt_injection_marker_count` in Phase 1, given that no Phase 1–2 consumer reads it?** I argue yes — the cost is trivial (a marker-list scan per probe string), and Phase 3's design will be easier if the signal is already in `RepoContext`. The synthesizer should confirm or defer.
7. **Where does the boundary live between "Phase 1 parser sandbox" and "Phase 5 microVM"?** Both are isolation mechanisms; Phase 5 escalates dramatically. This design treats them as serving different threats — Phase 1 contains a *parser bug*; Phase 5 contains an *adversarial diff being built and run*. The synthesizer should confirm this framing and that there's no scope leakage (no probe in Phase 1 builds containers; no validator in Phase 5 parses untrusted repo files).
8. **Should `bwrap` be a hard runtime dependency on Linux production gather workers (Phase 14)?** This design ships bwrap as advisory in Phase 1. The synthesizer should decide whether to set the precedent now — "Linux production: bwrap mandatory" — or to defer until Phase 14 builds the production worker image.
