# Phase 00 — Bullet tracer + project foundations: Security-first design

**Lens:** Security — isolation, least privilege, audit, supply chain, defense in depth.
**Designed by:** Security-first design subagent
**Date:** 2026-05-11

## Lens summary

Phase 0 looks security-trivial — one trivial probe, a stub YAML, CI green — and that is precisely the trap. **Posture is set in Phase 0 and inherited by every later phase.** A repo whose CI signs nothing, whose dependencies have no lockfile, whose pre-commit hooks don't run on the agent's own commits, whose `.codegenie/` directory leaks the absolute paths of the developer's home tree, and whose probe contract has no notion of an output trust boundary will *never* climb back out of that hole. By Phase 11 the same system will be opening PRs against production repos at portfolio scale, and the supply-chain attack surface of `codewizard-sherpa` will *be* the supply-chain attack surface of every repo it touches. That is what I am defending against now.

I optimized Phase 0 for five things, in order: **(1) supply-chain integrity** of `codewizard-sherpa` itself (lockfile, hash-pinning, signed CI, no transitive surprise); **(2) least-privilege filesystem and process posture** for the CLI (no recursive walks above the analyzed repo, no implicit network egress, subprocess allowlist baked in from day one); **(3) safe-by-default secret handling** (no probe ever writes a credential to `.codegenie/`, the cache, or stdout); **(4) audit trail discipline** (every probe run is logged with provenance; nothing is "silently skipped"); **(5) a probe-output trust boundary** (probes return data, never executable artifacts, and the schema enforces this structurally).

I deliberately accept friction in three places: contributor onboarding (signing commits, hash-pinned deps, restricted CI runners are all extra steps), implementation speed (a subprocess allowlist and an output sanitizer in Phase 0 is over-engineering for one probe — but every subsequent phase adds probes that shell out, and retrofitting an allowlist is impossible once the codebase has 50 callsites), and developer ergonomics (the cache directory's permissions are 0700, not 0755). I deprioritize: marketing-friendly error messages, fancy progress UIs, anything that requires phoning home to a metrics endpoint.

The single most important Phase 0 security bet: **the probe contract's output type is a Pydantic model with no execution semantics, no shell strings, no path-like-but-stringy fields, no `eval`-able dicts.** A probe returns structured evidence. If a future probe wants to return "the command to run next," that probe is wrong by construction. This is the deterministic-gather commitment (load-bearing commitment §1, ADR-0005) re-expressed as a type signature — and it is also the single most important supply-chain isolation property the whole system has.

## Goals (concrete, measurable)

The Phase 0 scaffold must support these *by construction* — not "we'll add it in Phase 5":

- **Lockfile coverage:** 100% of declared dependencies and 100% of transitive dependencies pinned to exact versions with hashes (`uv pip compile --generate-hashes` or equivalent). Zero unhashed installs in CI.
- **Supply-chain signature verification:** every CI job verifies the integrity of fetched packages against the lockfile hashes. A tampered package fails the job, not the test suite.
- **Reproducible builds:** two CI runs of the same commit produce byte-identical wheels (within the limits of `PYTHONHASHSEED=0` and `SOURCE_DATE_EPOCH`).
- **Filesystem blast radius:** `codegenie gather <path>` reads only files under `<path>` and writes only under `<path>/.codegenie/`. Zero writes outside the analyzed repo. The single exception is the user-level tool-readiness cache under `~/.codegenie/` — and that path is created with 0700 perms and never holds repo content.
- **Network egress in Phase 0:** **zero** outbound network calls during `codegenie gather`. Tool-readiness check is local-only; LanguageDetection is local-only; cache I/O is local-only. The CLI prints a clear refusal if any subprocess attempts egress (verified in CI via `unshare -n` or netns equivalent).
- **Subprocess allowlist:** the CLI maintains a module-level allowlist of permitted external commands. Phase 0 ships with `{git}` only. Adding `npm` requires a code-change PR and review; adding `curl` requires an ADR. No shell strings; everything goes through `asyncio.create_subprocess_exec` with `argv` arrays and no `shell=True`.
- **Secret-leak defense in depth:** three layers — (a) the probe-output schema rejects any field whose name matches `(?i)(secret|token|key|password|credential|auth)`; (b) the output writer runs `gitleaks` against the produced `repo-context.yaml` and refuses to write if findings exceed zero; (c) CI runs `gitleaks` over the repo on every PR. Layer (a) is *new* to this phase and is the load-bearing one.
- **Audit trail:** every gather run emits a `run-record.json` to `.codegenie/runs/<utc-iso-timestamp>-<short-hash>.json` capturing CLI version, git commit of `codewizard-sherpa`, probe versions, cache hits/misses, tool versions used, wall-clock per probe, and the user/host (host name redacted to a hash, not the literal value). Append-only; never truncated by the tool.
- **Probe-output trust boundary:** the `ProbeOutput` Pydantic model has no field of type `bytes`, no field of type `Callable`, no `Dict[str, Any]` with un-typed payloads. `schema_slice` is `dict[str, JSONValue]` where `JSONValue` is the recursive union of JSON-safe primitives. Enforced by mypy.
- **Permissions hygiene:** every file the CLI writes is mode 0600 by default; every directory is 0700. CI verifies this with a test that mode-bit-checks every file in `.codegenie/` after a fixture gather.
- **CI runner posture:** GitHub Actions jobs run with the minimum-required `permissions:` block (`contents: read`, `actions: read` only; nothing else). `GITHUB_TOKEN` has read-only scope. Forks do not get write access. Workflow files are protected branches.
- **Pre-commit hooks:** `gitleaks`, `ruff`, `mypy --strict`, and a custom hook that blocks `eval/exec/__import__/os.system/subprocess.run(...shell=True)` patterns. Pre-commit is mandatory for contributors; CI re-runs the same hooks so disabling locally fails the PR.
- **Dependency vetting at Phase 0:** every direct dependency declared in `pyproject.toml` (`click`, `pyyaml`, `jsonschema`, `aiofiles`, `pydantic`) is reviewed against OSV/GHSA at PR-merge time. A dependency CVE published *after* Phase 0 ships triggers an automated PR proposing the upgrade (via `dependabot` or `renovate`). The infrastructure for this is wired in Phase 0, not Phase 13.

## Architecture

```
                              codegenie CLI (click)
                                       │
                ┌──────────────────────┼───────────────────────┐
                │                      │                       │
        argparse path        Subprocess Allowlist        Tool Readiness
        (no eval, no         (module-level frozenset;     Check (signed
        shell=True)          enforced by exec wrapper)    versions only)
                │                      │
                └────────► Coordinator ◄──── ProbeRegistry
                                │              (no entry-point
                                │               plugin discovery —
                                │               explicit imports only)
                ┌───────────────┼────────────────┐
                │               │                │
         CacheLookup      RunProbe              ResultMerge
         (0700 dir,       (sandbox-               │
          0600 files,     ready: no              ▼
          content hash    network,         ProbeOutput
          + schema        no parent-dir    (Pydantic; JSONValue
          version)        escape)          recursive type;
                │                          no bytes/Callable;
                │                          name-regex filter
                ▼                          for secret-looking
       .codegenie/cache/                   field names)
       ├── index.jsonl  (append-only;            │
       │   each line signed by HMAC              │
       │   over (probe, key, sha))               ▼
       └── blobs/                       ┌──────────────────┐
           └── <hash>.json              │ Output Sanitizer │
              (0600;                    │  - gitleaks scan │
              path-string scrub)        │  - secret regex  │
                                        │  - path scrub    │
                                        └──────┬───────────┘
                                               │
                                               ▼
                                .codegenie/context/
                                ├── repo-context.yaml  (0600, atomic write)
                                ├── raw/  (0700)
                                └── runs/<ts>-<hash>.json (append-only audit)
```

Two architectural lines that carry the security thesis:

1. **The Subprocess Allowlist is a hard wall.** Every place in the codebase that needs to invoke an external binary goes through `codegenie.exec.run_allowlisted(argv: list[str])`. The list of permitted binaries is a `frozenset` defined in `codegenie.exec`. Phase 0 ships with `{"git"}`. The function refuses any binary not in the set, raises a typed `DisallowedSubprocessError`, and the error is also a CI test fixture. **No `shell=True` anywhere in the codebase**, enforced by a pre-commit grep hook.

2. **The Output Sanitizer is a forced choke point.** Every probe's output flows through `OutputSanitizer.scrub(probe_output) -> SanitizedProbeOutput` before reaching the cache or the YAML writer. Phase 0's sanitizer does three things: (a) the field-name regex filter, (b) absolute-path-to-relative-path normalization (so `.codegenie/` artifacts don't leak `/Users/dannytrevino/...`), (c) `gitleaks` invoked as a subprocess on the serialized JSON. The sanitizer is the *single* code-path between probes and persisted artifacts. Adding a probe in Phase 1 inherits all three defenses for free; bypassing them requires an explicit code change visible in a PR.

## Components

### CLI entry (`codegenie/cli.py`)

- **Purpose:** Accept user input, dispatch to commands, exit fast — without ever invoking a shell or evaluating user-supplied strings.
- **Interface:** argv → exit code + stdout/stderr.
- **Internal design:**
  - **No `shell=True`. Anywhere. Ever.** Every subprocess invocation is `asyncio.create_subprocess_exec` with a `list[str]` argv. Pre-commit enforces this via a `forbidden-pattern` hook (regex blocks `shell=True`, `os.system`, `os.popen`, `commands.getoutput`).
  - **No `eval`, `exec`, `compile`, or `__import__` of user input.** Pre-commit blocks all of these patterns at the source level. We accept the false positives on `compile` (the regex won't fire on `re.compile`; the hook is scoped to `codegenie/` paths and excludes `pattern.compile` lookups by AST check).
  - **Path validation on every `<path>` argument:** `Path(arg).resolve(strict=True)` — must exist, must be a directory, must not traverse a symlink that crosses the path the user passed. A symlink inside the analyzed repo pointing to `/etc/passwd` is rejected.
  - **No environment-variable expansion** in paths. `codegenie gather $HOME/x` passes the literal string `$HOME/x` to `Path()` and fails as a non-existent dir — by design. Click's `auto_envvar_prefix="CODEGENIE"` is *off* in Phase 0 specifically because env-var injection from a parent shell is an under-appreciated path-traversal vector when the CLI is invoked by a CI orchestrator. Re-enable in Phase 9 with a documented scope.
  - **TLS only**, if any HTTPS calls land in later phases: enforced via a `codegenie.net` module that wraps `httpx` with `verify=True` and pins TLS 1.2+ minimum. Phase 0 has no network calls; the module exists as a stub so Phase 14's webhook listener inherits the posture.
- **Tradeoffs accepted:**
  - Click env-var expansion is off; CI orchestrators that wanted to use `$CODEGENIE_CACHE_DIR` have to use `--cache-dir`. Worth it. Reintroduce only behind an explicit `--use-env` flag with a documented scope.
  - Lazy imports of heavy modules (matched with the performance lens) have a *security* upside too: if a malicious dependency lurks deeper in the import graph, it cannot fire on `codegenie --help`. A scanning honeypot that runs `--help` on a corpus of CLIs to detect malware never reaches the payload.

### Subprocess allowlist (`codegenie/exec.py`)

- **Purpose:** The single chokepoint for every external-binary invocation.
- **Interface:**
  - `ALLOWED_BINARIES: frozenset[str] = frozenset({"git"})`
  - `async def run_allowlisted(argv: list[str], *, cwd: Path, timeout_s: float) -> ProcessResult`
  - Raises `DisallowedSubprocessError` on any `argv[0]` not in the set.
- **Internal design:**
  - **Allowlist is a `frozenset`** at module scope. Adding `npm` requires a PR; reviewers see a one-line diff that adds `"npm"` and assess the implications.
  - **`argv` is `list[str]`** with no shell interpretation. `subprocess` is called with `shell=False` explicitly even though it's the default — the explicitness is a hardening signal for code review.
  - **`cwd` is mandatory** and must resolve under the analyzed-repo path. The wrapper refuses to run a subprocess with `cwd` outside the repo. This blocks a buggy or malicious probe from running `git rev-parse HEAD` against `~/.ssh/known_hosts`-adjacent trees.
  - **Timeouts are mandatory.** No default to "no timeout." A subprocess that doesn't terminate within the timeout is `SIGKILL`'d (not `SIGTERM`'d — we don't trust the child to clean up). 1.5× the timeout is the hard ceiling per ADR-0014's three-retry pattern, but in Phase 0 a single timeout is fine.
  - **Environment is filtered to a tight allowlist:** `{PATH, HOME, LANG, LC_ALL}` only. `PATH` is the user's `PATH` (so locally-installed tools work), but every other env var (`SSH_AUTH_SOCK`, `AWS_*`, `GITHUB_TOKEN`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) is stripped from the child's environment. This is enforced by passing `env=filtered_env` to the subprocess call.
  - **stdin is `DEVNULL`** unless explicitly passed. No subprocess inherits the CLI's stdin.
- **Tradeoffs accepted:**
  - Env-var filtering can break tools that genuinely need to see `https_proxy` or similar. The escape hatch is: add the var to the per-binary allowlist in `exec.py` (e.g., `git: extra_env={"GIT_SSH_COMMAND"}`), reviewable per-PR.
  - Phase 0 has only one allowlisted binary (`git`); a critic will say "this allowlist is theatre with one entry." The infrastructure *is* the point — Phase 1 will add `tree-sitter`, `scip-typescript`, and the rest, and the allowlist is the gate that surfaces each addition.

### Probe registry (`codegenie/probes/registry.py`)

- **Purpose:** Collect probe classes; expose `all_probes()` and `for_task()` filters — without dynamic plugin discovery that an attacker could exploit.
- **Interface:** `@register_probe` decorator + `all_probes()`, `for_task(task, languages)` queries.
- **Internal design:**
  - **No entry-point plugin discovery.** `importlib.metadata`-based plugin scanning would mean any installed Python package declaring a `codegenie.probes` entry point gets loaded. That is a supply-chain attack vector: install a malicious package in the user's environment and arbitrary code runs inside the CLI's process. Phase 0 (and Phase 1, and Phase 2) loads probes via explicit imports in `codegenie/probes/__init__.py`.
  - **`@register_probe` validates the class structure at decoration time:** must subclass `Probe`, must declare `name: str`, `version: str`, `declared_inputs: tuple[str, ...]`, `applies_to_tasks: tuple[str, ...]`, `applies_to_languages: tuple[str, ...]`, and `timeout_seconds: float`. Missing fields raise at import time.
  - **Probe names are unique;** double-registration is rejected. This blocks the "two installed copies of the same probe-name shadow each other" failure mode that comes up when packaging mistakes happen.
- **Tradeoffs accepted:**
  - External plugin authoring is harder. By Phase 14+ we'll want third-party probes (vendors writing their own probes for their own toolchains). At that point we introduce a signed-manifest plugin mechanism — code-signed, hash-verified, explicitly opted in. *Never* an unsigned entry-point scan.

### Coordinator (`codegenie/coordinator.py`)

- **Purpose:** Dispatch probes concurrently with bounded resource use and full failure isolation.
- **Interface:** as in the performance design (input/output identical).
- **Internal design:**
  - **Probe failures are caught and turned into `ProbeOutput(errors=[...], confidence="low")`.** This is also CLAUDE.md "Fail loud" — the failure is visible in the artifact, in stdout, and in the `run-record.json`. The point is: a failing probe does not abort the gather, but the failure *is not hidden*. Silently skipping is the worst failure mode.
  - **Per-probe wall-clock and CPU-time captured for the audit trail.** A probe that consistently takes 3× longer than its declared `timeout_seconds` is a signal worth surfacing in Phase 13 dashboards.
  - **No probe-to-probe communication.** Each probe gets a read-only `RepoSnapshot`; it cannot write to a shared dict. This blocks one buggy probe from corrupting another's inputs. (See the performance design for the same conclusion driven by latency rather than safety — two lenses agree.)
  - **The coordinator never re-raises probe exceptions to the caller.** The CLI's exit code is `0` if at least one probe produced a valid output; `2` if all probes failed; `3` if schema validation on the final document failed. Each is documented and CI-tested.
  - **Cancellation propagation:** if the user `Ctrl-C`s, the coordinator sends `cancel()` to every in-flight probe task, awaits with a 100 ms grace, then `SIGKILL`s any remaining subprocess via the allowlisted-exec wrapper's process-tracking table. No orphan processes.
- **Tradeoffs accepted:**
  - The exit-code scheme (0/2/3) is non-standard. Document it in `--help` and in the `mkdocs` site. CI scripts that check exit codes are explicit beneficiaries.

### Cache layer (`codegenie/cache.py`)

- **Purpose:** Content-addressed durable cache for probe outputs, with integrity guarantees.
- **Interface:** `get`, `put`, `key_for` — same as the performance design.
- **Internal design:**
  - **Cache key includes the probe's `version` field and a `schema_version` constant.** Bumping the schema invalidates all cached entries by construction. No "stale cache returns malformed output" failure mode.
  - **Hash function: SHA-256** for the public cache key (the directory name and the index entry). I am explicitly overruling the performance lens here: the cache key is the artifact's identity for audit-trail purposes; collisions are a *security* concern (an attacker who can produce a hash collision can swap one probe's output for another's). SHA-256's collision resistance is the load-bearing property; xxh3's speed advantage is irrelevant at Phase 0 scale (a few cache writes per gather). **If performance becomes a real constraint at Phase 14 portfolio scale, evaluate `blake3` (cryptographic, fast) — not `xxh3` (non-cryptographic, fast, collision-vulnerable).**
  - **Each index record is HMAC-signed** with a per-installation key stored at `~/.codegenie/.cache-key` (mode 0600, generated on first run via `secrets.token_bytes(32)`). On `get()`, the HMAC is verified before the blob is loaded. A tampered index entry fails verification, is treated as a miss, and the event is logged to the audit trail.
  - **Why the HMAC matters in Phase 0:** a malicious commit to the user's repo could include a pre-populated `.codegenie/cache/blobs/` with crafted outputs designed to make the gather report "no shell invocation needed" when shell is in fact needed. The HMAC blocks that — a third party cannot forge a valid index entry without the installation key. The user's own machine writes its own cache; that's the trust boundary.
  - **Cache directory permissions:** `.codegenie/cache/` is `0700`. Files inside are `0600`. Verified by a test that mode-checks every file after a fixture gather.
  - **Atomic writes:** blob to `<dest>.tmp`, `fsync`, `os.replace`. Index appended with `O_APPEND` (atomic for ≤ `PIPE_BUF` writes; record format is bounded length).
  - **TTL enforcement is lazy** but a `cache verify` subcommand exists from Phase 0 to walk the index and re-check every HMAC; integrity-check tooling lands now so Phase 14's compliance asks ("prove the cache hasn't been tampered with") have an answer.
- **Tradeoffs accepted:**
  - SHA-256 is slower than xxh3. Documented; performance impact at Phase 0 scale is negligible. I am explicit that I am overruling the performance lens — see "Surface to synthesizer" below.
  - HMAC-signing the index adds ~30 μs per entry and a key-management step. Worth it. The key is per-installation, never leaves the machine, never transmitted, regeneratable (regeneration = full cache invalidation, which is the correct behavior after a suspected compromise).
  - The HMAC defends against tampering, not against an attacker with read+write access to the cache directory *and* the key file. If they have both, the threat model is already lost — but that's a true statement about every endpoint security model.

### Probe contract (`codegenie/probes/base.py`)

- **Purpose:** The ABC and the trust boundary for probe outputs.
- **Interface:** As specified in `localv2.md §4`.
- **Internal design (security additions to the contract):**
  - **`ProbeOutput.schema_slice: dict[str, JSONValue]`** where `JSONValue = Union[None, bool, int, float, str, list["JSONValue"], dict[str, "JSONValue"]]`. Enforced via Pydantic's discriminated-union validation. **No `bytes`, no `Callable`, no `Any`, no `object`.** A probe that wants to return binary data writes it to `.codegenie/context/raw/<probe-name>.bin` and references the path in `schema_slice` — and the path goes through the Output Sanitizer.
  - **Field-name regex filter:** the `ProbeOutput` validator iterates `schema_slice` recursively and rejects any key matching `(?i)^.*(secret|token|password|credential|api[_-]?key|auth[_-]?token|bearer).*$`. A probe trying to emit `{"github_token": "..."}` fails validation. The error is a `SecretLikelyFieldNameError` and is also a CI test fixture. This is *defense in depth*; gitleaks is the second layer; CI's gitleaks-on-PR is the third.
  - **Probe `declared_inputs` are restricted to globs under the analyzed-repo root.** A glob like `../../../etc/passwd` is rejected at registration time. The probe lifecycle resolves every glob against the snapshot root and refuses results that traverse upward.
  - **No `__init__` arguments.** Probes are instantiated by the coordinator with `ProbeClass()` and configured via class-level attributes only. This removes the "constructor argument injection" attack vector and keeps probes purely declarative.
  - **`Probe.run()` receives a `RepoSnapshot` that is itself immutable** (a `pydantic.BaseModel` with `model_config = ConfigDict(frozen=True)`). A probe cannot mutate the snapshot and cannot pass-by-reference shared state.
- **Tradeoffs accepted:**
  - The recursive `JSONValue` type makes Pydantic's autogenerated schemas more verbose. Acceptable. The structural guarantee is what we're buying.
  - A regex on field names is heuristic; a probe wanting to emit a field literally called `decryption_steps` will trip it. The escape hatch is an explicit `allow_field_name` decorator on the probe class with code-review per usage.

### LanguageDetection probe (`codegenie/probes/language_detection.py`)

- **Purpose:** The one trivial probe that proves the harness — security stance: read-only, no network, no subprocess.
- **Internal design:**
  - **No subprocess calls.** Phase 0's LanguageDetection is a pure-Python `os.scandir` walk + extension counting. No `git`, no `file`, no `tree-sitter`. The performance design and the security design agree here for different reasons.
  - **Path resolution refuses to follow symlinks out of the repo root.** `os.scandir` returns `DirEntry` with `is_symlink()`; entries that resolve outside the root are skipped and logged.
  - **Excluded directories** (the noise list — `node_modules`, `.git`, etc.) are also security-relevant: `.git/hooks/` could contain credentials, `.env` files lurk in many trees. The exclusion list explicitly includes `.env*`, `.aws`, `.ssh`, `.gnupg`, `id_rsa*`, plus the standard noise dirs. Documented in code with the rationale.
  - **No file-content reads in Phase 0.** Extension counting is metadata-only (`DirEntry.name`). A future tree-sitter pass in Phase 1 will read file contents — and that's the right point to add a per-file size limit (refuse to parse files > 10 MB) and an explicit binary-file skip.

### Output writer + sanitizer (`codegenie/output.py`, `codegenie/output_sanitizer.py`)

- **Purpose:** Build `repo-context.yaml` after sanitizing every probe output, atomically replace prior outputs.
- **Interface:** `OutputSanitizer.scrub(probe_output) -> SanitizedProbeOutput`; `Writer.write(sanitized_outputs, output_dir)`.
- **Internal design:**
  - **Sanitizer runs three passes in fixed order:**
    1. **Field-name regex filter** (defense-in-depth; should never fire because the probe contract caught it, but the second pass is here to catch a buggy probe that bypassed validation).
    2. **Path scrubbing:** any string value that starts with `/Users/`, `/home/`, `/root/`, or the analyzed-repo's absolute path is rewritten to a path relative to the repo root (e.g., `/Users/dannytrevino/work/svc/package.json` → `package.json`). This prevents leaking the developer's home directory tree into committed artifacts. Critical because Phase 11's PR-opening stage will *commit* the YAML to a real repo.
    3. **`gitleaks` invocation on the serialized JSON form of the output.** If gitleaks reports > 0 findings, the writer raises `LeakedSecretError`, refuses to write the YAML, and exits with code 4. The leaking probe's name is in the error.
  - **YAML writer uses `yaml.CSafeDumper`** — the C extension and the safe-mode dumper. `yaml.Dumper` (unsafe) is a CVE waiting; we use `SafeDumper`-family always.
  - **Output files are written `0600`;** directories are created `0700`. The `Writer` constructor takes an `umask` parameter to make this explicit and testable.
  - **Atomic publish:** `repo-context.yaml.tmp` written with `os.replace` to `repo-context.yaml`. The temp file is *also* `0600` (the tempfile module's default is `0600`; we don't relax).
  - **No symlink-following on output write.** If `repo-context.yaml` already exists as a symlink to `/etc/somewhere`, the writer detects the symlink (via `Path.is_symlink()`) and refuses to write. This blocks a malicious commit from planting a symlink that redirects the gather's writes.
- **Tradeoffs accepted:**
  - Gitleaks on every gather is ~50–200 ms. Acceptable. Sanitizer is the single most important Phase 0 invariant; the cost is the price of admission.

### Audit trail (`codegenie/audit.py`)

- **Purpose:** Tamper-evident, append-only record of every gather run.
- **Interface:** `AuditWriter.record(run_record: RunRecord) -> None`.
- **Internal design:**
  - **`run-record.json` is written to `.codegenie/runs/<utc-iso-timestamp>-<short-hash>.json`** with `0600` perms. One file per run. Never truncated. Never mutated after writing.
  - **The record includes:** CLI version, `codewizard-sherpa` git commit SHA, Python version, OS+kernel string (no hostnames), per-probe (name, version, cache-hit boolean, wall-clock, exit status), tool versions used (from the readiness cache), and the SHA-256 of the final `repo-context.yaml`. The artifact hash is the audit anchor — a third party can recompute it and verify the run output matches the audit record.
  - **Records are append-only by file convention** (one file per run; the directory grows). A separate `codegenie audit verify` subcommand walks the directory, re-hashes each run's claimed artifact, and reports mismatches. Lands in Phase 0 with one verifier check; richer verification lands in Phase 16.
- **Tradeoffs accepted:**
  - Disk growth is a real concern at portfolio scale; Phase 13's AgentOps work handles rotation. Phase 0 just appends; users with disk concerns prune manually.
  - Audit records don't include the user's username — by design. Auditability is about the *system*, not the *user*. (Multi-tenant audit lands in Phase 16; that's where per-user attribution matters.)

### Schema validation (`codegenie/schema.py`)

- **Purpose:** Validate produced `repo-context.yaml` against a JSON Schema; the schema is itself a security invariant.
- **Internal design:**
  - **`jsonschema.Draft202012Validator`** with the schema loaded from `codegenie/schemas/repo-context.v1.json`. **No `fastjsonschema`** — I am explicitly overruling the performance lens here. `fastjsonschema` generates Python code at runtime and `exec`s it; the perf win comes from compiling-the-validator-to-Python. That code generation is a (small) supply-chain surface area and the resulting code is not statically inspectable. `jsonschema` is slower but transparent and audit-friendly. At Phase 0 scale the cost is invisible.
  - **The schema includes `"additionalProperties": false`** at every level. Unknown fields in `repo-context.yaml` are a validation failure — surfacing buggy probes that emit fields the schema doesn't know about.
  - **The schema is loaded once, module-level, frozen.** No runtime schema mutation.
- **Tradeoffs accepted:**
  - Slower validation. Documented. `fastjsonschema` becomes a Phase 13+ optimization if and only if profiling shows it on the hot path *and* the team accepts the code-generation surface. (Note for synthesizer: this is a genuine cross-lens disagreement.)

### Pre-commit hooks + CI (`pyproject.toml`, `.pre-commit-config.yaml`, `.github/workflows/`)

- **Purpose:** Defense in depth: every commit is checked locally and re-checked in CI.
- **Internal design:**
  - **Pre-commit hooks (required for all contributors):**
    - `ruff check` and `ruff format --check` (style/lint).
    - `mypy --strict` on `codegenie/`.
    - **`gitleaks` on staged files.** Catches accidentally-committed secrets at commit time. Same gitleaks runs in CI on the full repo on every PR.
    - **`bandit` on `codegenie/`.** Catches `shell=True`, `eval`, `assert`-as-control-flow, hardcoded passwords. Configured to fail on `MEDIUM` and above; the noisy `LOW`-severity findings are tuned out in `pyproject.toml`.
    - **Custom regex hook (`forbidden-patterns`) that blocks:** `shell=True`, `os.system`, `os.popen(`, `commands.getoutput`, `pickle.loads`, `yaml.load(` (without `Loader=`), `subprocess.run(...shell=True)`, `eval(`, `exec(`, `__import__(`. The hook is scoped to `codegenie/` paths.
    - **`detect-private-key`** from `pre-commit-hooks`. Catches accidentally-committed SSH keys.
  - **CI workflow (`.github/workflows/ci.yml`):**
    - **`permissions: contents: read` at the workflow level**, with no per-job elevation. Forks cannot get write access. `GITHUB_TOKEN` is read-only.
    - **Pinned-by-SHA actions** (not by tag). `actions/checkout@<sha>` not `@v4`. A tag can be moved by the publisher; a SHA cannot. The trade is that updating actions becomes a deliberate PR — which is the point.
    - **Hash-verified dependency install.** `pip install --require-hashes -r requirements-locked.txt` (or `uv pip sync requirements-locked.txt` with `--require-hashes`). A package whose hash does not match the lockfile fails the install. The lockfile is generated by `uv pip compile --generate-hashes` and committed.
    - **Three parallel jobs:** `lint`, `typecheck`, `test`. Plus a `security` job that runs `pip-audit` and `osv-scanner` against the lockfile. PR-blocking on `HIGH`/`CRITICAL` CVE findings; advisory on `MEDIUM`.
    - **A network-isolated test job** that runs `codegenie gather` inside a runner with egress firewalled (via `step-security/harden-runner@<sha>` with `egress-policy: block`). Validates the "zero outbound network in Phase 0" guarantee.
    - **A reproducibility check:** runs the build twice with `PYTHONHASHSEED=0` and `SOURCE_DATE_EPOCH` set; diff'ing the two wheels must be byte-identical. Catches non-determinism early.
    - **SBOM generation:** `syft` generates an SBOM of the built wheel; uploaded as a CI artifact. Phase 14 will wire SLSA attestations on top; the SBOM lands now.
    - **Workflow files live on a protected branch** (`main`); modifying `.github/workflows/` requires a PR with at least one approving review from a CODEOWNER. Configured in repo settings; documented in `CONTRIBUTING.md`.
  - **`dependabot.yml`** (or `renovate.json`): scans daily; auto-PRs for `pip` ecosystem; security updates labeled `security` and merged eagerly under a documented policy.
- **Tradeoffs accepted:**
  - Pinned-by-SHA actions = no automatic action updates. Dependabot's `github-actions` ecosystem PRs handle the upgrade cadence — explicit review per upgrade.
  - Hash-verified installs mean adding a dependency is a two-step process (`uv pip compile --generate-hashes` regenerates the lockfile, then commit both `pyproject.toml` and `requirements-locked.txt`). Friction, deliberately. Catches "I added `click==8.1.7` but didn't pin hashes" by failing CI.

## Data flow

A representative Phase 0 run, `codegenie gather /path/to/repo`, with security checkpoints called out:

1. **CLI entry.** argv parsed by `click`. Path argument resolved with `Path.resolve(strict=True)`; symlink-traversal-out-of-repo rejected here. *Security gate: path validation.*
2. **Tool readiness check.** Reads `~/.codegenie/.tool-cache.json`. Cache mode-checked (0600 expected; warns if relaxed). Tool binary version-checked; mismatch invalidates the entry. *Security gate: tool-version integrity.*
3. **HMAC key load or generation.** Reads `~/.codegenie/.cache-key` if exists; generates via `secrets.token_bytes(32)` if not. Mode 0600 enforced; ownership checked (refuses to use a key file owned by another user). *Security gate: per-installation cache integrity.*
4. **RepoSnapshot construction.** `git rev-parse HEAD` via the allowlisted exec wrapper — the `git` binary is the only allowed subprocess in Phase 0. Snapshot is a frozen Pydantic model. *Security gate: subprocess allowlist.*
5. **Probe registry filter.** `LanguageDetectionProbe` selected. `declared_inputs` re-validated against the repo root (none traverse upward).
6. **Coordinator dispatch.** One asyncio task spawned; `asyncio.Semaphore(8)` (Phase 1 onward) enforces the concurrency cap. *Security gate: bounded resource use.*
7. **Cache lookup.** Index entry for the (probe, key) found? HMAC verified? If yes-and-yes: blob loaded and returned. If HMAC fails: logged to audit trail, entry treated as miss, probe re-runs. *Security gate: cache integrity.*
8. **Probe execution.** `os.scandir` walk; no subprocess; no network; no file content reads. Symlinks crossing the repo boundary skipped + logged.
9. **Probe output validation.** Pydantic `ProbeOutput` constructed; `schema_slice` traversed; field-name regex applied; `JSONValue` type enforced. *Security gate: probe trust boundary.*
10. **Output sanitizer.** Three passes: field-name filter (redundant; expected to be a no-op), path scrubbing (absolute → relative), gitleaks. *Security gate: secret-leak defense in depth.*
11. **Cache write.** Blob written 0600 to `.codegenie/cache/blobs/`; index record signed with HMAC; appended with `O_APPEND`. *Security gate: append-only audit + signed entries.*
12. **Output merge.** Single merged dict; YAML serialized via `CSafeDumper`.
13. **Schema validation.** `Draft202012Validator` on the merged dict. `additionalProperties: false` enforced. *Security gate: artifact structure.*
14. **YAML write.** `.tmp` → `os.replace`. 0600 perms. No symlink following. *Security gate: atomicity + permissions hygiene.*
15. **Audit record.** `run-record.json` written to `.codegenie/runs/`; SHA-256 of the final YAML recorded as the audit anchor. *Security gate: tamper-evident audit trail.*
16. **Exit.**

**Network egress over this run: zero.** Verified by the netns-isolated CI job.

**Subprocesses launched: one** (`git rev-parse HEAD`). Verified by an audit-trail assertion in the smoke test.

**Files written outside `.codegenie/`: zero.** Verified by an inotify-style test in the smoke suite.

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| Probe `run()` raises | Coordinator `try/except` | Probe gets `ProbeOutput(errors=[...], confidence="low")`; coordinator continues; failure is in the YAML, in stdout, and in `run-record.json` — never silent |
| Probe exceeds timeout | `asyncio.wait_for` + `SIGKILL` | Same as above; subprocess child force-killed; warning logged with elapsed time |
| Subprocess allowlist violation | `DisallowedSubprocessError` from `exec.run_allowlisted` | Probe fails; gather continues; audit record captures the disallowed binary name |
| Cache HMAC fails | `cache.get` HMAC verification | Treat as miss; probe re-runs; tamper event logged to audit trail with the affected probe + key |
| Cache index corruption | JSONL parse error | Last partial line discarded; valid records retained; affected probes treated as misses |
| Path traversal attempt (symlink out of repo) | `Path.resolve` + boundary check | Entry skipped; logged; gather continues |
| Probe emits secret-like field name | Pydantic `ProbeOutput` validation | Probe output rejected; `SecretLikelyFieldNameError` raised; probe treated as failed; gather continues with the failure recorded |
| Gitleaks finds a secret in serialized output | `OutputSanitizer.scrub` | Writer refuses to write; CLI exits 4; offending probe named in stderr; *no artifact persisted*. This is "fail closed." |
| Schema validation fails | `Draft202012Validator` | YAML written with `.invalid` suffix; CLI exits 3; structured error in stderr |
| Output destination is a symlink | `Path.is_symlink()` check | Writer refuses; CLI exits 5; suspicious-symlink event logged |
| HMAC key file has wrong permissions or ownership | Startup check in `audit.py` | Refuse to proceed; CLI exits 6 with instructions to fix perms |
| Lockfile-hash verification fails in CI | `uv pip sync --require-hashes` | CI job fails; not retried (a hash mismatch is *the* signal we want to see, not a flake) |
| `gitleaks` finds a real secret in the repo on PR | Pre-commit + CI `gitleaks` job | PR blocked; remediation guidance in the job log (rewrite history, rotate the credential) |
| `pip-audit` finds a HIGH/CRITICAL CVE in a dependency | CI `security` job | PR blocked; remediation via `dependabot` or manual lockfile bump in a follow-up PR |
| Network egress detected in test job | `harden-runner` egress-policy block | Job fails with the egress-attempt log; treat as a P1 regression |
| Reproducibility check fails | Two-build diff | Job fails; investigation required (most likely cause: a transitive dep introduced non-determinism) |

## Resource & cost profile

The security overhead is real but bounded:

- **Per-gather wall-clock overhead vs. minimal-security baseline:**
  - Gitleaks invocation: ~50–200 ms (depends on output size; Phase 0's tiny YAML is ~50 ms).
  - HMAC verification on a cache hit: ~30 μs. Effectively zero.
  - Pydantic `JSONValue` recursive validation on probe outputs: ~1–5 ms for typical sizes.
  - SHA-256 over input files (vs. xxh3): adds ~5 ms per MB of input. For Phase 0's LanguageDetection (metadata-only, ~zero bytes hashed), negligible. At Phase 2's 30-probe scale with a 5 MB lockfile being re-hashed, this is ~25 ms total — well inside any practical budget.
  - Audit-record write: ~2 ms.
  - **Total Phase 0 security tax: ~75–250 ms per gather.** Acceptable given the property guarantees.
- **Per-gather wall-clock with security overhead (M-series Mac):**
  - `codegenie gather` on a 1k-file repo: 300 ms / 500 ms (p50 / p95).
  - `codegenie gather` on a 50k-file repo: 900 ms / 1700 ms.
- **Storage growth:**
  - Audit trail: one `run-record.json` per gather (~2 KB). After a year of nightly continuous gather, ~700 KB. Acceptable.
  - Cache: same as the performance design's estimates; HMAC adds ~32 bytes per index record. Negligible.
- **CI cost:**
  - The `security` job (pip-audit + osv-scanner) is ~30 s on warm cache.
  - The `netns-isolated` test job is ~10 s overhead (the firewall harden step itself is fast).
  - The `reproducibility` check is ~2× the normal build time, ~60 s total.
  - Total CI walltime budget (Phase 0): ~3–4 minutes for the full PR check matrix. Compatible with developer iteration speed.
- **Tokens per run:** 0. Phase 0 makes no LLM calls.
- **Maintenance burden:**
  - One lockfile regeneration step per dependency change (~2 minutes of developer time).
  - One pre-commit setup per contributor (~2 minutes).
  - Dependabot PRs land ~weekly in steady state; each ~5 minutes of reviewer time.

## Test plan

"Passes its tests" for Phase 0 means, in addition to the performance-lens tests:

1. **Unit tests (security-specific):**
   - `exec.run_allowlisted("git", ["--version"])` succeeds; `exec.run_allowlisted("npm", ["--version"])` raises `DisallowedSubprocessError`.
   - `exec.run_allowlisted` strips `AWS_*`, `GITHUB_TOKEN`, `OPENAI_API_KEY` from the child env.
   - `Path` arg with a symlink that resolves out of the repo root is rejected.
   - `ProbeOutput` with a field named `github_token` raises `SecretLikelyFieldNameError`.
   - `ProbeOutput` with a `bytes` field fails Pydantic validation.
   - `cache.get` with a tampered HMAC entry returns `None` and logs a tamper event.
   - Output sanitizer rewrites absolute `/Users/...` paths to relative form.
   - `gitleaks` integration: a probe output containing a fake AWS access key fails the sanitizer and the writer exits 4.
   - YAML write refuses to overwrite a symlink target.
   - `.codegenie/` files post-gather have mode 0600; directories 0700.
2. **Smoke tests:**
   - `codegenie gather /tmp/empty-dir` (after fixture setup) produces a valid YAML and a `run-record.json`.
   - The smoke run launches exactly one subprocess (`git rev-parse HEAD`).
   - The smoke run makes zero outbound network calls (run with `unshare -n` or `network=none` in CI).
   - The smoke run writes zero files outside `<analyzed-repo>/.codegenie/` (verified by inotify or fs-snapshot diff).
3. **CI invariants (security-specific):**
   - `pip-audit` and `osv-scanner` jobs green; no HIGH/CRITICAL CVE in any dependency.
   - Reproducibility job: two builds produce byte-identical wheels.
   - `gitleaks` over the repo finds zero new secrets on every PR.
   - `bandit` finds zero MEDIUM-or-above findings on every PR.
   - SBOM artifact uploaded on every release tag.
4. **Adversarial tests (the canaries):**
   - **`tests/adv/test_path_traversal.py`** — a probe whose `declared_inputs` contains `"../../../etc/passwd"` fails to register.
   - **`tests/adv/test_symlink_escape.py`** — a fixture repo containing `link -> /etc` is walked; the symlink is skipped and logged; gather succeeds.
   - **`tests/adv/test_cache_poisoning.py`** — a fixture `.codegenie/cache/` with a pre-populated blob and a forged index entry (no HMAC) is rejected; the probe re-runs from scratch.
   - **`tests/adv/test_secret_leak.py`** — a probe whose output contains an AWS access key triggers the sanitizer; the writer exits 4 and no YAML is written.
   - **`tests/adv/test_env_var_strip.py`** — a child subprocess invoked via the allowlist wrapper does *not* see `OPENAI_API_KEY` in its environment, even when the parent has it set.
   - **`tests/adv/test_yaml_unsafe_load.py`** — the YAML produced is parseable by `yaml.safe_load` (no `!!python/object` tags); a malicious YAML file containing such tags fails to round-trip through our writer (we never write such tags; the test verifies the asymmetry holds).
   - **`tests/adv/test_pickle_forbidden.py`** — the codebase contains zero `pickle.loads` calls (AST scan).
   - **`tests/adv/test_no_shell_true.py`** — the codebase contains zero `shell=True` references (AST scan; the pre-commit regex hook is the first line, this is the belt to the suspenders).

## Risks (top 3–5)

1. **Pre-commit hooks erode under contributor pressure.** A new contributor finds `gitleaks` slow on a `git commit -a` of 200 files and adds `--no-verify` to their workflow. Six months later a real secret leaks. **Mitigation:** CI re-runs every pre-commit hook on every PR, so local bypass doesn't bypass merge. Make this fact prominent in `CONTRIBUTING.md`. Tune gitleaks's allowlist (false-positive whitelist) aggressively so it's not slow-and-noisy in practice.
2. **Lockfile maintenance fatigue.** Hash-pinned lockfiles mean adding a dependency is two commits' worth of work, regenerating hashes, etc. Over time, contributors will reach for `pip install foo` and "forget" to update the lockfile. **Mitigation:** `requirements-locked.txt` is in CI's `--require-hashes` install path; missing hashes fail the install. Make the regen command a one-liner in `Makefile`. Document it. Dependabot handles routine bumps automatically.
3. **Pinned-by-SHA actions decay into unmaintained state.** Six months in, the team has accumulated 20 actions pinned by SHA; nobody updates them; CVE in one of them goes unpatched. **Mitigation:** `dependabot.yml` covers the `github-actions` ecosystem with weekly cadence; new SHAs land as PRs; reviewers approve per-PR. Friction is the design; ignoring the friction is the failure mode.
4. **HMAC key compromise is silent.** If the user's `~/.codegenie/.cache-key` is exfiltrated (a malicious dep in *another* project running on the same machine), an attacker can forge cache entries. **Mitigation:** the threat model is bounded — the attacker would need filesystem write access to the analyzed repo *and* the key; if they have both, our cache isn't the weak link. A `codegenie audit rotate-key` subcommand exists in Phase 0 for the "I think this machine was compromised" case; it regenerates the key and invalidates all caches. Document the rotation procedure prominently.
5. **The "no LLM in gather" property erodes by accident.** A future contributor "helpfully" adds an `openai` call to a probe to disambiguate a tricky file type. The whole audit + reproducibility + cost story collapses. **Mitigation:** `pip-audit` is part of CI; we add a custom CI step that asserts the lockfile contains *none* of `{openai, anthropic, langchain, langgraph, transformers, ...}` in Phase 0. Phase 4 will add `anthropic` and `langgraph` to the *service* dependencies, but the *gather pipeline*'s allowlist stays clean — encoded as a separate `pyproject.toml` extra (`[project.optional-dependencies.gather]`) with the deterministic-only deps. A test asserts the gather extra is the only one needed to run the CLI.

## Acknowledged blind spots

What this lens deprioritized — the synthesizer should weigh these against the performance and best-practices designs:

- **Developer onboarding speed.** Hash-pinned lockfiles, SHA-pinned actions, gitleaks pre-commit, HMAC-signed cache, sandboxed CI runners, mandatory pre-commit — every one of these is a thing a new contributor has to learn and tolerate. The best-practices lens will likely propose tooling to smooth this; I accept the friction as a cost of correctness.
- **CI walltime.** Adding the `security` job, the netns-isolated test job, and the reproducibility check probably costs 30–60 s of CI walltime per PR. Performance lens explicitly target ≤ 90 s; this lens accepts ~120 s. The synthesizer will need to call this.
- **`fastjsonschema` vs. `jsonschema`.** I overruled the performance lens here; `fastjsonschema` does runtime code generation and I don't trust the surface in a security-critical path. If profiling proves it on the hot path at Phase 14 scale, revisit.
- **SHA-256 vs. xxh3 for cache content hashing.** Direct contradiction with the performance lens. My argument: cache key is identity and collisions are a security concern; xxh3 is non-cryptographic. Performance lens's argument: speed at scale. **`blake3` is the compromise** — cryptographic, fast — and I'd accept it as a synthesis. Flagging explicitly.
- **Audit-trail rotation.** Phase 0 just appends. Disk growth at portfolio scale is real but bounded; Phase 13's AgentOps handles rotation. I am content to defer.
- **Multi-user filesystem permissions.** Phase 0 assumes a single-user workstation. Multi-user audit lands in Phase 16. The HMAC key's per-installation property is the only single-user assumption — it would need to be per-user in a shared environment.
- **Windows.** Not supported. mode 0600 / 0700 are POSIX concepts; the ACL equivalent on Windows is more complex; we don't pay that cost. CLAUDE.md says macOS+Linux; aligned.
- **Threat model excludes nation-state actors on the developer workstation.** If an attacker has root on the dev machine, every assumption here is moot. We are defending against: a malicious or compromised package in the user's `site-packages`; a malicious commit in the analyzed repo; an exfiltrated CI token. Not: a kernel-mode rootkit on the developer's laptop.

## Open questions for the synthesizer

1. **SHA-256 vs. xxh3 vs. blake3 for cache content hashing.** Direct contradiction with the performance design. My pick: **SHA-256 in Phase 0** (cost is negligible at this scale and the integrity story is the load-bearing one); **blake3 if/when measured as the bottleneck** at Phase 14 portfolio scale. The performance design's xxh3 is a non-starter from a security lens — it's not collision-resistant.
2. **`fastjsonschema` vs. stock `jsonschema`.** Direct contradiction. My pick: **`jsonschema` only.** The runtime code-generation surface area of `fastjsonschema` is not worth the 10× speedup at Phase 0 scale. Revisit if profiling proves it material.
3. **Field-name regex filter on probe outputs.** Heuristic; flags `decryption_steps` as well as real secrets. Synthesizer should decide if the false-positive rate is tolerable or if the filter should be opt-in per probe.
4. **HMAC-signed cache index.** Adds complexity that no other Python CLI I know of carries. Synthesizer should weigh this against the threat model — am I over-defending against an attacker who can write to `.codegenie/cache/` but not elsewhere? Counterargument: a malicious commit can write to `.codegenie/cache/`; HMAC is the cheapest way to make it not matter.
5. **Lockfile-hash discipline as a hard CI gate.** I am proposing failing CI on any unhashed install. A real cost in contributor friction. Synthesizer's call whether the trade is worth it now or whether it should land in Phase 2 once there are more contributors.
6. **Reproducibility check in CI.** Genuinely useful as an early signal but adds ~60 s of CI walltime. Synthesizer's call whether to run it on every PR, every release, or every nightly.
7. **The `[project.optional-dependencies.gather]` extra that locks the gather pipeline out of LLM SDKs.** I am proposing this as a Phase 0 invariant — the gather extra is the only one needed to run the CLI, and it contains no LLM SDK. The synthesizer should validate this is compatible with the roadmap's Phase 4 architecture (the LLM-fallback would live in a *different* package or a different extra).
