# Phase 00 — Bullet tracer + project foundations: Final design (design of record)

**Role:** Graph-of-Thought synthesizer.
**Date:** 2026-05-11
**Inputs:** `design-performance.md` [P], `design-security.md` [S], `design-best-practices.md` [B], `critique.md`.
**Authority:** This document is the design of record. The three lens designs are background; they are *not* normative. The critique is treated as a structured set of constraints that this synthesis must address. Conflicts between this design and the lens designs are resolved in favor of this design.

Provenance tags below: `[P]` perf-lens only, `[S]` security-lens only, `[B]` best-practices-lens only, `[P+S]` / `[P+B]` / `[S+B]` two lenses agreed, `[all]` all three agreed, `[synth]` synthesizer departure from all three.

---

## 0. Posture

Phase 0 ships almost no business logic. It ships the **conventions, contracts, and chokepoints every later phase will inherit**. A reviewer must be able to clone the repo, run `make bootstrap`, run `make check`, and have a green check, an artifact on disk, and an audit record in under five minutes on a warm cache. The harness must be the *real* harness that Phases 1–16 load into — not a stub that Phase 1 will rewrite.

The single most important Phase 0 bet [synth]: **the probe-output contract is a structural trust boundary** (Pydantic, recursive `JSONValue`, no `bytes`/`Callable`/`Any`) **and a deterministic-gather invariant** (gather extras lock out LLM SDKs from `pyproject.toml`) **rolled into one type signature**. Every subsequent phase reads through this seam. Get it wrong here and Phase 4's LLM-fallback, Phase 11's PR-opening, Phase 13's cost ledger, and Phase 14's continuous gather all pay compound interest.

---

## 1. Architecture

```
                                codegenie CLI (click)
                                          │
                ┌─────────────────────────┼────────────────────────────┐
                │                         │                            │
        Path/symlink validation   Subprocess Allowlist          Tool readiness
        (resolve(strict=True);    {git} in Phase 0;              cache @
        refuse symlinks out of    DisallowedSubprocessError)     ~/.codegenie/.tool-cache.json
        repo root)                                                (TTL 24h; --refresh-tools)
                │
                └────────► Coordinator (asyncio)
                                  │
                                  ├── ProbeRegistry — explicit import only,
                                  │   no entry-point discovery
                                  │
                ┌─────────────────┼──────────────────────┐
                │                 │                      │
         CacheLookup        RunProbe (LanguageDetection) ResultMerge
         (BLAKE3 content    (one asyncio.Task;            (shallow dict.update;
          hash; SHA-256     bounded by Semaphore;          skip-marker for
          identity tag;     read-only RepoSnapshot;        cache-hit pass-through)
          O_APPEND index    no network, no subprocess
          on JSONL)         in Phase 0)
                │                                          │
                ▼                                          ▼
       .codegenie/cache/                       ProbeOutput (Pydantic,
       ├── index.jsonl  (append-only)          frozen, recursive JSONValue,
       └── blobs/                              field-name regex filter)
           └── <2-char shard>/<blake3>.json            │
                                                      ▼
                                          ┌──────────────────────┐
                                          │ Output Sanitizer     │
                                          │  1. field-name regex │
                                          │     (defense-in-depth)│
                                          │  2. absolute→relative │
                                          │     path scrubbing   │
                                          └──────┬───────────────┘
                                                 │
                                                 ▼
                                .codegenie/context/
                                ├── repo-context.yaml  (atomic os.replace; 0600)
                                ├── schema-version.txt
                                ├── raw/<probe>.json   (0600)
                                └── runs/<utc-iso>-<short>.json   (audit anchor)
```

Two architectural lines carry the synthesis [P+S]:

1. **The Coordinator is async from day one, single probe in Phase 0, multiple in Phase 1.** A serial-in-Phase-0 stub [B] gets *replaced* in Phase 1, not extended — critique §3.1.1 makes this fatal. The async harness lands now with `Semaphore(min(cpu_count(), 8))`, one `asyncio.Task` per probe, `asyncio.wait_for` per-probe timeout. Phase 0 dispatches exactly one probe through the same code path Phase 1 dispatches six through.

2. **One chokepoint per cross-cutting concern.** `codegenie.exec.run_allowlisted` is the only subprocess path [S]. `codegenie.output_sanitizer.scrub` is the only path from `ProbeOutput` to persisted YAML [S]. `codegenie.cache` is the only path to/from cache blobs and is the only place hash functions live [P+S]. Each chokepoint is a single file, a single public API, and a single set of tests. Phase 1 adds probes and tools; it does not add second paths around these gates.

---

## 2. Components

### 2.1 Project layout (`src/` layout) [B]

```
codewizard-sherpa/
├── pyproject.toml              # PEP 621
├── uv.lock                     # committed
├── README.md
├── CLAUDE.md
├── Makefile                    # bootstrap | check | fmt | lint | types | test | docs | clean
├── .pre-commit-config.yaml
├── .gitignore                  # includes .codegenie/
├── .editorconfig
├── mkdocs.yml
├── .github/
│   ├── workflows/ci.yml
│   ├── dependabot.yml
│   ├── ISSUE_TEMPLATE/{new-probe.md, new-skill.md, adr-amendment.md}
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── CODEOWNERS
├── docs/                       # mkdocs serves this; existing tree retained
├── src/
│   └── codegenie/
│       ├── __init__.py         # exports __version__ only
│       ├── __main__.py
│       ├── cli.py
│       ├── version.py
│       ├── logging.py          # structlog config
│       ├── errors.py           # one exception hierarchy
│       ├── exec.py             # subprocess allowlist  [S]
│       ├── hashing.py          # single source of truth for hash choices [synth]
│       ├── config/{loader.py, defaults.py}
│       ├── probes/{base.py, registry.py, language_detection.py}
│       ├── coordinator/{coordinator.py, snapshot.py}
│       ├── cache/{store.py, keys.py}
│       ├── schema/{repo_context.schema.json, validator.py}
│       ├── output/{writer.py, sanitizer.py, paths.py}
│       └── audit.py
├── tests/
│   ├── conftest.py
│   ├── unit/         # probe contract, registry, cache, schema, writer, sanitizer, exec
│   ├── smoke/        # bullet tracer end-to-end test
│   ├── adv/          # adversarial: path traversal, symlink, cache poisoning, secret leak
│   ├── bench/        # CLI cold-start canary (advisory, not gating)
│   └── fixtures/
└── docs/phases/00-bullet-tracer-foundations/
    ├── design-best-practices.md, design-performance.md, design-security.md
    ├── critique.md
    └── final-design.md          # this file (the design of record)
```

`src/` layout [B+synth]: forces every test to exercise the installed wheel path; flat-layout is rejected. One distribution, one package name. `__main__.py` exists so `python -m codegenie gather` works pre-install.

### 2.2 Tooling and dependencies [B with [P]/[S] modifications]

| Concern | Choice | Provenance |
|---|---|---|
| Python | 3.11 + 3.12 in CI matrix | [B] |
| Build backend | `hatchling` | [B] |
| Installer (dev + CI) | `uv` pinned to exact version in CI; `pip install -e ".[dev]"` documented fallback | [P+B] |
| Lock | `uv.lock` committed; CI runs `uv sync --locked` | [B] |
| Lint + format | `ruff` (lint + format) | [all] |
| Type check | `mypy --strict` on `src/`; on `tests/` set `disable_error_code = ["misc", "no-untyped-def"]` for fixture pragmatism | [P+B compromise] |
| Test runner | `pytest` + `pytest-asyncio` + `pytest-cov` | [all] |
| `pytest-xdist` | **NOT** enabled in Phase 0 | [synth — overrules [P]] |
| Coverage | branch on; 85% line / 75% branch floor on `src/codegenie/` excluding `cli.py` | [synth — softer floor than [B]'s 90/80] |
| Pre-commit | ruff, mypy, end-of-file fixer, trailing whitespace, check-yaml, check-json, check-toml, no-commit-to-main, gitleaks, bandit, detect-private-key, `forbidden-patterns` | [B+S] |
| Docs | `mkdocs-material` with `mkdocs-include-markdown-plugin` | [B] |
| Strict mkdocs | `mkdocs build --strict` runs *only on `docs/phases/**` and `docs/production/**`* in Phase 0; `docs/local.md`, `docs/auto-agent-design.md`, `docs/gemini-auto-agent-design.md`, `docs/context.md`, and `docs/localv2.md` are excluded via `nav` until Phase 1 doc-cleanup pass | [synth — addresses critique §3.1.5] |
| Logging | `structlog` | [B] |
| `pydantic` | **v2; in Phase 0; lazy-imported from CLI entry** | [synth — overrules [B] deferral] |
| Schema validator | `jsonschema` (Draft 2020-12); compiled once at module scope behind `lru_cache` | [S+B — overrules [P]'s `fastjsonschema`] |
| Content hash | **BLAKE3** for cache content hashing; **SHA-256** for the public cache key tuple and the audit anchor | [synth — accepts critic's compromise; overrules both [P]'s xxh3 and [S]'s pure SHA-256] |
| HMAC-signed cache index | **NOT** in Phase 0; revisit at Phase 14 (continuous gather over webhooks introduces the threat model) | [synth — overrules [S]] |
| `aiofiles` | **removed** from Phase 0 deps; the roadmap lists it but no code path uses it. Add when an async probe needs it. | [synth — addresses critique §7.4] |
| `pyproject.toml` extras | `[project.optional-dependencies]` = `dev` (everything for the harness) + `gather` (the runtime deps of the deterministic gather pipeline only) | [synth — addresses critique §6.1] |

The `pyproject.toml` shape is a load-bearing departure [synth, addresses critique §6.1 and §7.2]:

```toml
[project]
name = "codewizard-sherpa"
version = "0.0.1"
requires-python = ">=3.11"
dependencies = [
  # gather-pipeline runtime — these are also the closure of "[project.optional-dependencies.gather]"
  "click>=8.1",
  "pyyaml>=6.0",
  "jsonschema>=4.21",
  "pydantic>=2.7",
  "structlog>=24.1",
  "blake3>=0.4",
]

[project.optional-dependencies]
gather = []  # intentionally empty; the gather pipeline's deps are [project.dependencies] above
dev = [
  "pytest>=8.0", "pytest-asyncio>=0.23", "pytest-cov>=5.0",
  "mypy>=1.10", "ruff>=0.5", "pre-commit>=3.7",
  "mkdocs-material>=9.5", "mkdocs-include-markdown-plugin>=6.2",
  "bandit>=1.7", "gitleaks-python>=8.0",
  "uv>=0.4",
]
# Future-reserved (Phase 4+); declared empty in Phase 0 so the slot exists:
service = []     # Phase 9+ (Temporal, Postgres clients)
agents  = []     # Phase 4+ (anthropic, langgraph) — the LLM SDKs land here, NOT in dependencies

[project.scripts]
codegenie = "codegenie.cli:main"
```

A Phase 0 CI test asserts: `set(distribution("codewizard-sherpa").requires) ∩ {"anthropic", "langgraph", "openai", "langchain", "transformers"}` is empty. This is the **load-bearing-commitment §2.1 fence**, encoded as a test, lit up in Phase 0. Any future phase adding an LLM SDK must route it through the `agents` extra and the gather extra remains clean.

### 2.3 Probe contract — verbatim, frozen by snapshot test [B+all]

`src/codegenie/probes/base.py` is byte-for-byte the ABC from [`localv2.md §4`](../../localv2.md). No renames. No "small improvements." No Pydantic wrapping of the *contract* itself (the contract is dataclass-based per the spec). The probe-output *envelope*, however, gets a structural trust boundary [synth, S-lens]:

- `RepoSnapshot`, `Task`, `ProbeContext`, `ProbeOutput` are the **dataclasses from §4** — verbatim.
- A separate `_ProbeOutputValidator` (Pydantic v2 `BaseModel` with `model_config = ConfigDict(frozen=True)`) is constructed from each `ProbeOutput` in the coordinator immediately before sanitization. It enforces:
  - `schema_slice: dict[str, JSONValue]` where `JSONValue = None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue]` (recursive). No `bytes`, no `Callable`, no `Any`. [S]
  - Field-name regex filter: keys matching `(?i)^.*(secret|token|password|credential|api[_-]?key|auth[_-]?token|bearer|access[_-]?key|private[_-]?key).*$` → `SecretLikelyFieldNameError`. [S]
  - Confidence value ∈ `{"high", "medium", "low"}`. [B]

This satisfies critique §3.2.2's concern about Phase 4's pydantic dep being unavoidable: pydantic lands in Phase 0, lazy-imported, used at the trust boundary only. The dataclass contract still lifts unchanged to the service per ADR-0007 — the validator is an *implementation detail of the coordinator*, not part of the contract.

**Contract freeze policy** [synth — addresses critique §6.3]:

- A test (`tests/unit/test_probe_contract.py`) imports `codegenie.probes.base` and snapshots the `Probe` class signature (field names, types, defaults, decorators, MRO) to a JSON file at `tests/snapshots/probe_contract.v1.json`.
- The snapshot includes a fingerprint hash referencing `localv2.md §4` content at the time of Phase 0 land (SHA-256 of §4's body as committed at Phase 0 close).
- When `localv2.md` updates, the snapshot must be regenerated **by ADR amendment** (issue template `adr-amendment.md` exists in Phase 0 for exactly this purpose). The fingerprint mismatch fails CI until the ADR amendment is merged.
- Resolution policy in the ADR amendment: **`localv2.md` is the source of truth; the implementation must conform**. A drift between code and `localv2.md` is always resolved by changing code, never by editing `localv2.md` to match.

This is ADR-0007 ("probe contract preserved POC → service") given an enforcement loop.

### 2.4 Probe registry [P+S agree, [B] decorator pattern]

- `@register_probe` decorator pattern, exactly as `localv2.md §4`. [all]
- **Explicit imports in `src/codegenie/probes/__init__.py`**, no `importlib.metadata` entry-point scan. Both performance (~30–80 ms startup cost) and security (supply-chain injection vector) argue against entry-points. [P+S]
- Duplicate registration by `name` raises at decoration time. [B+S]
- `for_task(task, languages)` cached via `functools.lru_cache(maxsize=32)`. [P]
- The registry is a `Registry` class with a module-level default instance, so tests can pass a fresh `Registry()` to avoid global state. [B]

### 2.5 Subprocess allowlist (`codegenie/exec.py`) [S — adopted as load-bearing]

This is the largest [P]→[S] departure in this synthesis: performance and best-practices both shrugged at subprocess hygiene; security made it load-bearing. Critique §1.3 and §3.3 both flag the omission as compounding by Phase 7 (`docker buildx`, `dive`, `dockerfile-parse`). Verdict: **adopt the allowlist now**.

- `ALLOWED_BINARIES: frozenset[str] = frozenset({"git"})` at module scope.
- `async def run_allowlisted(argv: list[str], *, cwd: Path, timeout_s: float, env_extra: dict[str, str] = {}) -> ProcessResult` is the only path. `shell=False` always; passed explicitly for code-review visibility.
- Filtered env: `{PATH, HOME, LANG, LC_ALL}` plus binary-specific extras (e.g., `GIT_SSH_COMMAND` for `git`). Strips `SSH_AUTH_SOCK`, `AWS_*`, `GITHUB_TOKEN`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.
- `stdin=DEVNULL` unless explicitly passed.
- Timeout mandatory. SIGKILL at `1.5 × timeout_s`.
- `cwd` mandatory and resolved to be under the analyzed-repo path.
- `forbidden-patterns` pre-commit hook + AST-scan test (`tests/adv/test_no_shell_true.py`) blocks `shell=True`, `os.system`, `os.popen`, `pickle.loads`, `yaml.load(` (without `Loader=`), `eval(`, `exec(`, `__import__(` from `src/codegenie/`. [S]

Phase 0 has exactly one allowed binary (`git`) and exactly one call site (`RepoSnapshot.git_commit` via `git rev-parse HEAD`). The infrastructure is the point.

### 2.6 Coordinator (`codegenie/coordinator.py`) [P+S agree on shape]

- `asyncio.Semaphore(min(os.cpu_count() or 1, config.max_concurrent_probes, 8))`. [P]
- One `asyncio.Task` per probe via `asyncio.create_task` + `asyncio.wait_for(timeout=timeout_s)`. [P+S]
- Hard kill at `1.5 × timeout_s` via cancel + 100ms grace. [P+S]
- Probe exceptions caught into `ProbeOutput(errors=[...], confidence="low")`; coordinator continues. CLI exit: `0` if ≥1 probe produced a valid output; `2` if all probes failed; `3` if schema validation failed; `4` if sanitizer rejected output. [P+S]
- Each `ProbeOutput` flows through `_ProbeOutputValidator → OutputSanitizer.scrub` *in the coordinator* before merge. [synth]
- **Cache-hit pass-through is first-class** [synth — addresses critique §6.5]: the coordinator's per-probe result is one of `{Ran(output), CacheHit(output, key), Skipped(reason)}`. The output `dict[probe_name, ProbeOutput]` is preserved, and a sibling `dict[probe_name, ProbeExecution]` records which path was taken. Phase 14's incremental-gather model needs this distinction at the coordinator interface; encoding it now means Phase 14 doesn't extend the contract.
- No probe-to-probe communication. Each probe gets a frozen `RepoSnapshot`. [P+S]
- `Ctrl-C` cancels in-flight tasks with 100ms grace, then SIGKILLs lingering subprocesses via `exec.py`'s process-tracking table. [S]
- No thread pool. Probes that shell out use `asyncio.create_subprocess_exec` (via `exec.run_allowlisted`). [P]

The coordinator dispatches exactly one probe in Phase 0 (LanguageDetection), but the interface is the Phase 1 interface unchanged.

### 2.7 Cache layer (`codegenie/cache.py`) [synth — explicitly resolves the headline conflict]

**The single most consequential decision in this synthesis** (critique §5). Resolution:

- **Cache key tuple identity**: `SHA-256(probe_name | probe_version | schema_version | inputs_hash_hex)`. SHA-256 here because (a) `localv2.md §8` specifies it, (b) the cache key is the audit anchor for Phase 13's cost ledger and Phase 11's PR provenance, and (c) collision resistance is load-bearing for the "Honest confidence" commitment (`production/design.md §2.3`) at Phase 14 portfolio scale.
- **Bulk content hashing of `declared_inputs`**: **BLAKE3** — cryptographic *and* fast (matches SHA-256's collision resistance, ~3 GB/s on modern hardware vs SHA-256's ~400 MB/s). Critique §2.3 explicitly proposes BLAKE3 as the compromise; security lens accepted it ("blake3 is the compromise"); performance lens's argument was about speed, which BLAKE3 satisfies. xxh3 is rejected: non-cryptographic, the threat model includes Phase 14's webhook-driven gather, and there is no point in the lifecycle where a non-cryptographic hash buys us anything we can't get from BLAKE3.
- **Hash choices live in one file**: `codegenie/hashing.py` exports `content_hash(path) -> str` (BLAKE3) and `identity_hash(*parts: str) -> str` (SHA-256). The hashing module is the only place either algorithm is named.
- Storage layout [P]: `.codegenie/cache/index.jsonl` (append-only) + `.codegenie/cache/blobs/<2-char shard>/<blake3-hex>.json`. Sharding by the first 2 hex chars keeps any single dir under ~256 entries × n.
- Index scanned linearly on startup. mmap is *not* used in Phase 0 [synth — overrules [P]]: mmap on Windows behaves differently, mmap of an append-only JSONL changing during read is racy under concurrent CLI invocations (critique §1.2.1), and the index is single-digit MB through Phase 13. Plain buffered read suffices; swap to mmap behind a flag if a Phase 14 measurement demands it.
- Atomic writes: blob to `<dest>.tmp`, `fsync`, `os.replace`. Index appended with `O_APPEND` (atomic for records ≤ `PIPE_BUF=4096` bytes).
- Permissions: `.codegenie/cache/` is `0700`; files inside are `0600`. [S]
- **No HMAC signing of index records** [synth — overrules [S]]: critique §2.1.1 establishes that the threat model can't articulate who has write access to `.codegenie/cache/` but not to `~/.codegenie/.cache-key` on a developer workstation. The CI threat model (ephemeral runner) is incompatible with persistent per-installation keys. Defer to Phase 14 when continuous webhook-driven gather actually introduces the multi-actor threat the HMAC would defend against; at that point design the key-storage path explicitly.
- TTL is lazy: lookups treat `created_at + ttl < now` as miss. Separate `codegenie cache gc` subcommand compacts. [P+S]
- Cache API is narrow: `get(key) -> ProbeOutput | None`, `put(key, output) -> None`, `key_for(probe, snapshot, task) -> str`. [P+S+B]

### 2.8 Output writer + sanitizer (`codegenie/output/writer.py`, `codegenie/output/sanitizer.py`) [S — adopted, [P] perf trims accepted]

- `OutputSanitizer.scrub(probe_output) -> SanitizedProbeOutput` is the only path from probe output to persisted artifact. [S]
- Sanitizer passes in fixed order [synth — modifies [S]]:
  1. **Field-name regex filter** (defense-in-depth; expected no-op because `_ProbeOutputValidator` caught it). [S]
  2. **Absolute → relative path scrubbing**: any string starting with `/Users/`, `/home/`, `/root/`, or the analyzed-repo's absolute path is rewritten relative to repo root. This is **load-bearing for Phase 11**: the PR-opening stage commits `.codegenie/` artifacts and must not leak developer home paths. [S]
  3. **No `gitleaks` in the synchronous write path** [synth — overrules [S], addresses critique §2.1.2]: gitleaks-in-write-path is O(seconds) at Phase 2's hundreds-of-KB artifacts and incompatible with the continuous-gather model. Instead, gitleaks runs as a **pre-commit hook on the analyzed-repo's own files** and as a **CI step over the codewizard-sherpa source**, but **not** synchronously inside `gather`. The structural defense (`_ProbeOutputValidator` field-name regex + the path scrubber + the `JSONValue` type) is the load-bearing defense; gitleaks is belt-and-suspenders at commit/PR time.
- YAML writer: `yaml.CSafeDumper` (the C extension; safe-mode). `yaml.Dumper` is banned by `forbidden-patterns`. `yaml.load` (without `Loader=`) is banned. [P+S]
- Atomic publish: write `repo-context.yaml.tmp`, `fsync`, `os.replace`. [P+S]
- Output files written `0600`; directories `0700`. **On CI runners where `actions/cache` restores with `0755`**, the writer re-applies modes via `os.chmod` post-restore [synth — addresses critique §6.4]. The mode-bit-check tests assert post-`gather` perms, not post-cache-restore perms.
- No symlink-following on write. If `repo-context.yaml` already exists as a symlink, refuse to write (exit 5). [S]
- Raw artifacts written first, YAML manifest last. [P]

### 2.9 Schema validation (`codegenie/schema/validator.py`)

- `jsonschema.Draft202012Validator` compiled once at module scope, cached behind `lru_cache`. [S+B]
- **No `fastjsonschema`** [synth — overrules [P], adopts [S+B]]: critique §1.1.3 lays out the runtime-`exec` attack surface convincingly; the speedup is not measurable in Phase 0. Revisit only if a Phase 14 measurement proves it bottlenecks the continuous-gather coordinator.
- Schema at `src/codegenie/schema/repo_context.schema.json`, shipped as package data.
- **`additionalProperties` policy is layered** [synth — resolves [S] vs [B] conflict, addresses critique §3.2.3]:
  - **`additionalProperties: false`** at the top-level envelope (`schema_version`, `generated_at`, `repo`, `probes`). [B+S]
  - **`additionalProperties: true`** under `probes.*`. [B]
  - **Each probe owns a sub-schema at `src/codegenie/schema/probes/<name>.schema.json`**, composed by `$ref` into the envelope. Adding a probe in Phase 1 = adding a new file under `schema/probes/` and one `$ref` line in the envelope. Extension-by-addition holds; structural validation strictness holds *at the boundaries where it matters*. [synth]
- `schema-version.txt` written next to the YAML. [B]
- The Phase 0 envelope is minimal but complete for what Phase 0 produces (see [B] §2.7); the `language_detection.schema.json` sub-schema is the first concrete probe sub-schema and lands in Phase 0.

### 2.10 LanguageDetectionProbe (`codegenie/probes/language_detection.py`)

- Pure-Python `os.scandir` recursive walk. No subprocess. No network. No file-content reads. [P+S]
- Noise dirs excluded at directory level: `node_modules`, `.git`, `dist`, `build`, `coverage`, `.next`, `.turbo`, `target`, plus security-relevant: `.env*`, `.aws`, `.ssh`, `.gnupg`, `.idea`, `.vscode`. [P+S]
- Symlinks crossing the repo boundary are skipped + logged. [S]
- Extension recognition (Phase 0): `javascript` (`.js`, `.mjs`, `.cjs`), `typescript` (`.ts`, `.tsx` excluding `.d.ts`), `python` (`.py`), `go` (`.go`), `rust` (`.rs`). [B]
- **Dockerfile detection deferred to Phase 1** [synth — addresses critique §3.1.3]: `LanguageDetectionProbe` in Phase 0 ships *only* the language-by-extension count. Dockerfile is a Phase 7 concern (migration task class); recognizing it in Phase 0 violates the scope rule the design itself enforces on B–G.
- **`declared_inputs` are not `["**/*"]`** [synth — addresses critique §3.1.4]: declared inputs are `["**/*.js", "**/*.mjs", "**/*.cjs", "**/*.ts", "**/*.tsx", "**/*.py", "**/*.go", "**/*.rs"]` plus the exclusion-aware walker honors them at hash time. The cache key derives from the BLAKE3 hash of the sorted set of (path, size) tuples for files matching `declared_inputs` after exclusion. A `README.md` edit does *not* invalidate the cache; a `.js` file edit does. This makes the Phase 0 exit-criterion "cache hits on second run" testable against a non-empty fixture.

### 2.11 CLI entry (`codegenie/cli.py`) [P+S compromises]

- `click` over `argparse`. [all]
- **Lazy imports of heavy modules** (pyyaml, jsonschema, pydantic, blake3, structlog) inside command function bodies. The `--help` and `--version` paths import only standard library + click. [P]
- **Click env-var expansion off in Phase 0** (`auto_envvar_prefix=None`). Re-enable in Phase 9 with documented scope. [S]
- Path validation: `Path(arg).resolve(strict=True)`; must be a directory; refuses symlinks that traverse outside the input path. [S]
- Tool-readiness check cached to `~/.codegenie/.tool-cache.json`, keyed by `(tool, $PATH-hash, mtime)`, TTL 24h, `--refresh-tools` to invalidate. Phase 0 only checks `git`; the infrastructure is in place. [P]
- **CLI cold-start canary is *advisory* in Phase 0** [synth — overrules [P]'s "hard gate"]: critique §1.1.2 establishes that the canary is structurally flaky on shared CI runners. The canary runs in `tests/bench/test_cli_cold_start.py` and posts numbers as a PR comment; it does *not* fail the build. A hard gate lands in Phase 8 when there's a real CI cost story and dedicated benchmark runners. The `import-linter` config blocks heavy-module imports from `codegenie.cli` and `codegenie.__init__` and is the *structural* defense.

### 2.12 Audit trail (`codegenie/audit.py`) [S — adopted; HMAC dropped]

- `run-record.json` written to `.codegenie/runs/<utc-iso>-<short-hash>.json`; mode `0600`; append-only by convention (one file per run). [S]
- Record includes: CLI version, `codewizard-sherpa` git commit SHA, Python version, OS+kernel string (hostnames redacted to SHA-256 hash), per-probe (name, version, cache-hit boolean, wall-clock, exit status), tool versions used, SHA-256 of the final `repo-context.yaml`. [S]
- `codegenie audit verify` subcommand walks the directory, re-hashes each run's claimed artifact, reports mismatches. [S]
- **No HMAC signing**: the per-installation key story doesn't work on ephemeral CI runners and the threat model is unclear (critique §2.1.1). Phase 14 revisits when webhook-driven gather actually introduces the threat. [synth]

### 2.13 Configuration loader (`codegenie/config/loader.py`) [B — adopted]

- Three sources, fixed precedence: `defaults` < `~/.codegenie/config.yaml` < `<repo>/.codegenie/config.yaml` < CLI flags. [B]
- `Config` is a frozen dataclass with every field present and typed in `defaults.py`. [B]
- Unknown config key → `ConfigError` with Levenshtein "did you mean?" suggestion. **Fail-loud rule**. [B]
- YAML parsing via `yaml.safe_load`. The `forbidden-patterns` hook bans `yaml.load(...)` without `Loader=`. [B+S]
- Each loaded field's `Provenance` (defaults/global/repo/cli) is logged at startup at DEBUG. [B]

### 2.14 Logging (`codegenie/logging.py`) [B — adopted]

- `structlog`; one configurator called once from `cli.py`. [B]
- JSON in CI, pretty-printed in TTY (autodetected). [B]
- `print()` banned in `src/` (ruff rule `T201`). [B]
- Lifecycle events: `probe.start`, `probe.cache_hit`, `probe.skip`, `probe.success`, `probe.failure`, `probe.timeout`. Phase 6 will subscribe these to the state ledger without renaming. [B]

### 2.15 `.gitignore` mutation [synth — addresses critique §6.2]

CLAUDE.md mandates the CLI offer to add `.codegenie/` to the *analyzed* repo's `.gitignore` on first run. Resolution:

- `codegenie gather` checks if `<analyzed-repo>/.gitignore` exists and contains `.codegenie/`.
- If absent and stdin is a TTY: prompt `Add .codegenie/ to .gitignore? [Y/n]`. On accept, append `.codegenie/` with a comment line above (`# codewizard-sherpa generated artifacts; safe to delete`). The append is **atomic** (read, edit, `fsync`, `os.replace`).
- If absent and stdin is **not** a TTY (CI, pipe): do nothing; log a structured warning `gitignore.codegenie.not_present`.
- `--auto-gitignore` flag forces the append non-interactively (for scripted runs).
- `--no-gitignore` flag suppresses both the prompt and the warning.
- A test asserts the prompt path is reached on a TTY and skipped without one.

This is the only Phase 0 code path that mutates the analyzed repo. It is bounded, atomic, and opt-in.

---

## 3. Pre-commit hooks + CI [B+S — with [P] perf trims]

### 3.1 Pre-commit (`.pre-commit-config.yaml`)

- `ruff check` and `ruff format --check`. [all]
- `mypy --strict` on `src/`. **Not** strict on `tests/` (critique §3.2.2); tests use `mypy --strict --disable-error-code=misc,no-untyped-def`. [synth]
- `gitleaks` on staged files. [S]
- `bandit` on `src/` (fail on MEDIUM+). [S]
- `forbidden-patterns` custom regex hook scoped to `src/codegenie/`: bans `shell=True`, `os.system`, `os.popen(`, `commands.getoutput`, `pickle.loads`, `yaml.load(` without `Loader=`, `eval(`, `exec(`, `__import__(`. [S]
- `detect-private-key`, `check-yaml`, `check-json`, `check-toml`, `end-of-file-fixer`, `trailing-whitespace`, `no-commit-to-main`. [B+S]
- `import-linter` for the lazy-import discipline on `codegenie.cli` and `codegenie.__init__`. [P]

### 3.2 CI workflow (`.github/workflows/ci.yml`)

- `permissions: contents: read` at workflow level; no per-job elevation. `GITHUB_TOKEN` read-only; forks have no write access. [S+B]
- **Actions pinned by SHA**, with `dependabot.yml` covering the `github-actions` ecosystem weekly. [S]
- `setup-uv` pinned to an exact version; `uv sync --locked` for install. Lockfile-hash verification via `--require-hashes` is in the lockfile, not a separate `pip install` step. [P+S+B]
- Matrix: `python-version: ["3.11", "3.12"]`, `os: [ubuntu-24.04]`. macOS and Windows not in matrix in Phase 0. [B]
- Jobs (run in parallel, gated by `needs` only for the docs publication):
  1. **`lint`** — `ruff check . && ruff format --check .`
  2. **`typecheck`** — `mypy --strict src/` + `mypy --strict --disable-error-code=misc,no-untyped-def tests/`
  3. **`test`** — `pytest -q --cov=src/codegenie --cov-branch --cov-fail-under=85`
  4. **`security`** — `pip-audit`, `osv-scanner` against `uv.lock`. PR-blocking on HIGH/CRITICAL; advisory on MEDIUM.
  5. **`docs`** — `mkdocs build --strict` over the **curated `nav`** (Phase 0 scope; see §2.2). Path-filtered: only runs if `docs/**` or `mkdocs.yml` changed.
  6. **`fence`** — asserts the `dependencies` closure of the wheel excludes `{anthropic, langgraph, openai, langchain, transformers}`. Phase 0's "no LLM in gather" fence. [synth, load-bearing]
- **No netns-isolated test job in Phase 0** [synth — addresses critique §2.2.1]: `unshare -n` is Linux-only and `localv2.md` supports macOS dev. The "zero outbound network" assertion is achieved by *structural means* (the subprocess allowlist contains no network tools; the codebase has no `httpx`/`requests` import; an import-linter rule blocks them in `src/codegenie/`). Phase 14 wires `harden-runner` on Linux when the webhook listener actually does network I/O.
- **No reproducibility check in Phase 0** [synth — addresses critique §2.3]: the build is a single `hatchling` wheel of pure-Python source — there is no non-determinism to surface yet. Phase 1 lands the check when actual probe outputs become reproducible-vs-not (SCIP indexing, runtime traces).
- **CI walltime budget: ≤ 90s p95** [P — adopted as target, not gate]: measured weekly via a CI dashboard; if exceeded for two consecutive weeks, opens an automatic issue. Not PR-blocking. The budget is a forcing function, not a flake source.
- A separate `weekly-drift.yml` runs `uv lock --upgrade` + the full suite to surface dependency drift early. [B]

### 3.3 Coverage policy

- **Floor: 85% line / 75% branch** on `src/codegenie/` excluding `cli.py` [synth — softer than [B]'s 90/80]. Critique §3.2.3 establishes that 90/80 with five Phase 0 tests is satisfiable only by gameable integration tests. 85/75 is achievable with focused unit tests; the floor ratchets to 90/80 in Phase 1 when there's real surface to test.
- `cli.py` exempt from the line floor (click parsing tested via smoke, not branches). [B]
- `--cov-fail-under=85` enforced in CI. [B]
- `# pragma: no cover` allowed only for `if TYPE_CHECKING:` and `raise NotImplementedError` in ABCs; other uses require a code-review comment. [B]

---

## 4. Developer experience [B — adopted verbatim]

`Makefile` at repo root with eight targets, mirroring CI:

```
make bootstrap   # uv sync; pre-commit install
make check       # ruff + mypy + pytest + mkdocs --strict (scoped)
make fmt         # ruff format
make lint        # ruff check
make types       # mypy --strict
make test        # pytest
make docs        # mkdocs serve
make clean       # rm -rf .venv .pytest_cache .mypy_cache .ruff_cache site
```

- Local `make check` mirrors CI exactly; drift is a P0 bug.
- No `scripts/` directory. Every snippet goes in Makefile.
- `pip install -e ".[dev]"` is documented as the fallback path for contributors who refuse to install `uv`; it must work, tested in the weekly drift job.

---

## 5. Documentation [B — adopted, plus critique §3.1.5 fix]

- `mkdocs.yml` with `mkdocs-material` and `mkdocs-include-markdown-plugin`.
- `nav` in Phase 0 includes: `README.md`, `docs/production/**`, `docs/phases/**`, `CLAUDE.md`. Excludes: `docs/local.md` (superseded), `docs/auto-agent-design.md`, `docs/gemini-auto-agent-design.md`, `docs/context.md`, `docs/localv2.md` — these stay in the tree as source-of-truth references but are not part of the strict-mkdocs build until Phase 1 adds a docs-cleanup task. The exclusion is *documented in `mkdocs.yml` with comments* pointing to this section.
- New page: `docs/contributing.md` (~1 page) — `make bootstrap`, `make check`, branching, PR template, ADR location.
- No `CHANGELOG.md`, no `CODE_OF_CONDUCT.md`, no `ARCHITECTURE.md`. The production design docs are the architecture doc.

---

## 6. Data flow — representative Phase 0 run

`codegenie gather /path/to/repo`:

1. **CLI entry.** `click` parses argv. Path resolved via `Path.resolve(strict=True)`; symlink-out-of-input rejected. [S]
2. **Tool-readiness check.** Reads `~/.codegenie/.tool-cache.json` (mode-checked 0600). Phase 0 only checks `git`. [P+S]
3. **`.gitignore` mutation check.** If `<repo>/.gitignore` missing `.codegenie/` and stdin is a TTY, prompts. [synth]
4. **Config load.** Defaults < global < repo < CLI; unknown-key fails loud. [B]
5. **`RepoSnapshot` construction.** `git rev-parse HEAD` via `exec.run_allowlisted("git", ...)`. [S]
6. **Probe registry filter.** `for_task("__bullet_tracer__", {"unknown"})` returns `[LanguageDetectionProbe]`. [P]
7. **Coordinator dispatch.** One `asyncio.Task` under `Semaphore(min(cpu_count(), 8))`. [P+S]
8. **Cache lookup.** Compute key via `hashing.identity_hash(probe_name, version, schema_version, blake3_of_declared_inputs)`. Phase 0 cold: miss. [synth]
9. **Probe execution.** `os.scandir` walk, extension count, `ProbeOutput` constructed. [P+S]
10. **`_ProbeOutputValidator`.** Pydantic; `JSONValue` recursive type; field-name regex. [S]
11. **`OutputSanitizer.scrub`.** Field-name pass (no-op expected); path scrub (abs → relative). [S]
12. **Cache write.** Blob to `.codegenie/cache/blobs/<shard>/<blake3>.json`; index appended. [P+S]
13. **Output merge.** `result.update(sanitized.schema_slice)`. [P]
14. **Schema validation.** `Draft202012Validator`; envelope strict, `probes.*` loose. [S+B]
15. **YAML write.** `repo-context.yaml.tmp` → `os.replace`. `CSafeDumper`, 0600. [P+S]
16. **`schema-version.txt`** written. [B]
17. **Audit record.** `runs/<utc-iso>-<short>.json` with SHA-256 of the final YAML. [S]
18. **Exit 0.**

Network egress: zero. Subprocesses: one (`git`). Files outside `.codegenie/`: zero (excluding the opt-in `.gitignore` append).

---

## 7. Test plan

### 7.1 Unit tests (`tests/unit/`)

| File | Asserts |
|---|---|
| `test_probe_contract.py` | Probe ABC matches `localv2.md §4` byte-for-byte (snapshot test); subclass without `run` → `TypeError`; `applies()` defaults to `True`. |
| `test_probe_output_validator.py` | `bytes` field → validation error; field name `github_token` → `SecretLikelyFieldNameError`; recursive `JSONValue` accepts nested dicts/lists; deep `bytes` rejected. |
| `test_registry.py` | Decorator adds class once; duplicate `name` rejected; fresh `Registry()` is empty; `for_task` filtering cached. |
| `test_exec.py` | `run_allowlisted("git", ...)` succeeds; `run_allowlisted("npm", ...)` raises `DisallowedSubprocessError`; child env strips `OPENAI_API_KEY`; `cwd` outside repo refused. |
| `test_cache_store.py` | Same cache key → same payload; different inputs → different keys; corrupt blob → re-run + warning; atomic write under crash simulation. |
| `test_schema_validation.py` | Valid envelope passes; missing `schema_version` fails; `additionalProperties: false` rejects unknown top-level keys; `probes.*` accepts unknown probe sub-keys. |
| `test_output_writer.py` | `.codegenie/context/` created; YAML + `schema-version.txt` + `raw/` directory; re-run overwrites cleanly; symlink target refused. |
| `test_output_sanitizer.py` | Absolute `/Users/...` → relative; field-name pass is a no-op when validator already caught it; explicit Pydantic-bypass injection still caught by sanitizer. |
| `test_hashing.py` | `content_hash` is BLAKE3; `identity_hash` is SHA-256; both stable across two invocations with same input. |
| `test_config_loader.py` | Precedence: defaults < global < repo < CLI; unknown key fails loud with "did you mean?" suggestion. |
| `test_logging.py` | `print()` in `src/` fails ruff; lifecycle event names are exact. |
| `test_gitignore_mutation.py` | Append happens with TTY accept; skipped without TTY; idempotent on second invocation. |
| `test_pyproject_fence.py` | Dependency closure of the wheel contains no LLM SDK. |

### 7.2 Smoke test (`tests/smoke/test_cli_end_to_end.py`)

- `codegenie gather --help` exits 0.
- `codegenie gather <empty_dir>` exits 0; writes `repo-context.yaml`, `schema-version.txt`, `raw/`, `runs/<ts>-<short>.json`. YAML validates against schema. Exactly one subprocess invocation (`git`) appears in the audit record. Zero outbound network calls (verified structurally — no network module is imported anywhere reachable from the CLI).
- `codegenie gather <fixture-with-js-files>` exits 0; produces a `language_stack` with `javascript` count > 0.
- **Cache-hit smoke**: `codegenie gather <fixture>` twice in a row, second invocation emits `probe.cache_hit` for `language_detection` and the coordinator's `ProbeExecution` dict reports `CacheHit` for that probe.

### 7.3 Adversarial tests (`tests/adv/`)

[S]-derived; not exhaustive but the load-bearing ones:

- `test_path_traversal.py` — probe declaring `"../../../etc/passwd"` in `declared_inputs` fails registration.
- `test_symlink_escape.py` — fixture repo with `link -> /etc`; symlink skipped + logged; gather succeeds.
- `test_secret_leak.py` — probe whose output contains a fake AWS access key triggers `_ProbeOutputValidator` (if field name matches) or the path scrubber. Verifies *structural* defenses; gitleaks-in-write-path was rejected.
- `test_env_var_strip.py` — child of `run_allowlisted` does not see `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` even when parent has them.
- `test_yaml_unsafe_load.py` — writer never emits `!!python/object`; an adversarial YAML with such a tag fails to round-trip.
- `test_no_shell_true.py` — AST scan over `src/codegenie/`; zero `shell=True` references.
- `test_no_network_imports.py` — AST scan over `src/codegenie/`; no `httpx`, `requests`, `urllib3`, `socket` imports.

### 7.4 Benchmark canaries (`tests/bench/`)

Advisory only. Posts PR comments. Does **not** fail the build. [synth — overrules [P]]

- `test_cli_cold_start.py` — `codegenie --help` p50 of 5 runs.
- `test_coordinator_overhead.py` — dispatch + merge + write for 1 no-op probe.
- `test_cache_hit_dispatch.py` — second run vs first run wall-clock ratio.

### 7.5 Tests explicitly **not** in Phase 0

- No integration tests against real Node.js repos (Phase 1).
- No golden-file tests (Phase 2).
- No property tests, fuzz tests, gating benchmarks (Phase 8).
- No CLI tests for non-existent flags (`--task`, `--language`, `--cache-clear`) — added when the flags ship.
- No netns-isolated jobs (no network code yet).
- No reproducibility job (no non-determinism yet).
- No HMAC verification tests (no HMAC in Phase 0).

---

## 8. Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| Probe `run()` raises | Coordinator try/except | `ProbeOutput(errors=[...], confidence="low")`; coordinator continues; recorded in `run-record.json` |
| Probe exceeds `1.5 × timeout_s` | `asyncio.wait_for` + SIGKILL | Same; subprocess child force-killed; warning logged |
| Subprocess allowlist violation | `DisallowedSubprocessError` | Probe fails; gather continues; audit record captures the disallowed binary name |
| Cache index corruption | JSONL parse error | Last partial line discarded; valid records retained |
| Path traversal attempt | `Path.resolve` + boundary check | Skipped + logged; gather continues |
| Probe emits secret-like field name | `_ProbeOutputValidator` | Probe output rejected; `SecretLikelyFieldNameError` recorded; gather continues with that probe marked failed |
| Schema validation fails | `Draft202012Validator` | YAML written with `.invalid` suffix; CLI exits 3 |
| Output destination is a symlink | `Path.is_symlink()` check | Writer refuses; CLI exits 5 |
| `.gitignore` append fails | OSError | Logged; gather continues; user can rerun with `--no-gitignore` |
| `uv sync --locked` fails | CI exit nonzero | No retry; investigate (lockfile drift or registry outage) |
| Lockfile hash mismatch | `uv sync --locked` | CI fails; merge blocked; fix via `uv lock` regeneration PR |
| `pip-audit` finds HIGH/CRITICAL CVE | `security` CI job | PR blocked; remediation via Dependabot or manual lock bump |
| `mkdocs build --strict` warns | Job fails | Investigate the curated `nav`; if a *new* doc reference broke, fix it; if it's a *pre-existing* `docs/local.md` issue, the curated nav excluded it — investigate the exclusion |
| Coverage below 85/75 | `pytest --cov-fail-under` | PR blocked; add tests |
| `fence` job finds LLM SDK in dependency closure | Test failure | PR blocked; **this is a load-bearing-commitment-violation alarm**, not a routine failure |

---

## 9. Resource and cost profile

- **Tokens per run**: 0. Phase 0 is deterministic gather end-to-end. [all]
- **Wall-clock per `codegenie gather`** (M-series Mac, p50 / p95):
  - Empty dir: 80 / 200 ms (cold), 30 / 80 ms (warm).
  - 1k-file repo: 250 / 450 ms (cold), 50 / 150 ms (warm, cache-hit).
  - 50k-file repo: 800 / 1500 ms (cold, dominated by `os.scandir`).
- **Memory per worker (RSS)**: ~70 MB idle, ~90 MB peak during a 50k-file gather. [P]
- **Storage growth**: `repo-context.yaml` ~2 KB; raw ~1 KB; cache blob ~1 KB; audit ~2 KB. After a year of nightly continuous gather on a single repo: ~3 MB total per repo. [P]
- **CI walltime target**: ≤ 90s p95 (advisory). Six jobs in parallel × ~70s slowest = ~70–90s wall-clock. The `fence` and `security` jobs are the longer ones at ~30–40s each. [synth — accepts [P]'s number with [S]'s additional jobs]
- **CI cost per PR**: ~4 minutes of GitHub Actions Linux runner time. [P]

---

## 10. Risks

1. **Lazy-import discipline erodes silently.** A new contributor adds `import yaml` to `errors.py`; cold start regresses; `import-linter` may not catch the transitive path (critique §1.1.2). **Mitigation:** `import-linter` config enumerates the full forbidden transitive set; the `bench/test_cli_cold_start.py` canary surfaces the regression as a PR comment (advisory but visible).
2. **`uv` resolver upgrades break lockfile reproducibility** (critique §1.2.2 + §2.3.3). **Mitigation:** `uv` is pinned by exact version in CI *and* in a `.tool-versions` file at repo root; the `weekly-drift` job uses the same pin; updating `uv` is a deliberate ADR-amendment PR.
3. **Phase 0 over-engineering creep.** Critique repeatedly flags that "scaffolding becomes the project." **Mitigation:** the file list in §2.1 is the ceiling, not the floor. Adding a subsystem in Phase 0 requires an ADR amendment.
4. **`docs/` excluded-from-strict drift.** Excluding `docs/local.md` et al. from the strict build defers a real cleanup. **Mitigation:** an issue is filed at Phase 0 close (`docs: clean up pre-v2 docs for strict mkdocs`), assigned to Phase 1.
5. **The `fence` test is the load-bearing commitment §2.1 enforcement.** If it ever fails open (e.g., dependency closure check has a bug), the "no LLM in gather" invariant erodes invisibly. **Mitigation:** the `fence` test ships with a deliberate-negative test (`tests/unit/test_pyproject_fence.py::test_fence_catches_planted_anthropic_dep`) that adds `anthropic` to a synthetic `pyproject.toml` and asserts the check fails.

---

## 11. Exit criteria (Phase 0 done means)

The roadmap-level exit criteria, expanded with the design-level verifications critique §7.1 demands:

1. **CLI runs.** `codegenie gather <path>` exits 0 on empty dir, JS fixture, polyglot fixture. `--help` lists every existing flag. Unknown flags exit non-zero with a usage hint.
2. **External-tool readiness check.** Startup logs which tools are present (Phase 0: `git` only; logged at INFO when running, at WARN if missing).
3. **`LanguageDetectionProbe` executes end-to-end** through the real coordinator, real cache, real schema validator, real output writer, real sanitizer, real audit writer.
4. **Cache works on a non-empty fixture.** Second run emits `probe.cache_hit` for `language_detection` and the coordinator's `ProbeExecution` dict reports `CacheHit`. *No probe re-execution of the filesystem* (verified by monkeypatching `os.scandir` in the test).
5. **CI green on `main`.** All six jobs pass on 3.11 and 3.12 / Ubuntu 24.04.
6. **Docs site builds locally** with zero warnings via `make docs`; `mkdocs build --strict` over the curated `nav` is green in CI.
7. **Pre-commit hooks installed** by `make bootstrap`; a commit with a lint violation, a `shell=True`, or a `yaml.load(` without `Loader=` is blocked.
8. **Coverage ≥ 85% line / ≥ 75% branch** on `src/codegenie/` excluding `cli.py`.
9. **Issue templates render** in the GitHub UI: `new-probe`, `new-skill`, `adr-amendment`.
10. **Probe ABC snapshot test passes** — implementation matches `localv2.md §4` byte-for-byte (the v1 contract fingerprint).
11. **The `fence` test passes** — dependency closure contains no LLM SDK.
12. **The audit anchor verifies.** `codegenie audit verify` over the smoke-test run-record reports zero mismatches.
13. **`.gitignore` mutation path is exercised** by a test (both TTY-accept and non-TTY-skip).

---

## 12. Handoff to Phase 1+

Phase 1 inherits and **may not change without ADR amendment**:

- `Probe` ABC in `src/codegenie/probes/base.py` (the §4 byte-for-byte contract).
- `@register_probe` decorator and `Registry` shape.
- The `.codegenie/` on-disk layout from `localv2.md §3.2`.
- The JSON Schema envelope at `src/codegenie/schema/repo_context.schema.json` (strict at the envelope, loose under `probes.*`).
- The cache key derivation (SHA-256 identity over BLAKE3 inputs hash).
- The subprocess allowlist API (`run_allowlisted` is the only path).
- The output sanitizer's two passes (field-name regex + path scrubbing).
- Config merge precedence + fail-loud-on-unknown-keys.
- The error hierarchy in `errors.py`.
- The Makefile target names.
- The CI matrix and the six jobs.
- Strict mypy on `src/`, relaxed on `tests/`.
- The coverage floor (85/75 in Phase 0, ratcheting up).
- The `fence` test that the gather pipeline has no LLM SDK dep.

Phase 1 **is expected to extend by addition**:

- New probes via `@register_probe` in new files.
- New per-probe sub-schemas under `src/codegenie/schema/probes/`.
- New entries in `exec.ALLOWED_BINARIES` (each requires an ADR-amendment PR).
- New external-tool checks in the startup readiness scan.
- Tree-sitter for `LanguageDetection` ambiguous cases.
- The 5 additional Layer A probes (`NodeBuildSystem`, `NodeManifest`, `CI`, `Deployment`, `TestInventory`).
- A real coverage ratchet to 90/80 in Phase 1.
- A reproducibility CI check (when there's non-determinism to surface).

---

# Synthesis ledger (mandatory)

This is the GoT decomposition trace. Vertices were extracted from each design, edges were classified across designs, conflicts were scored, and winners were selected.

## L1. Vertex extraction — rough counts

| Source | Atomic decision vertices extracted |
|---|---|
| `design-performance.md` [P] | 47 |
| `design-security.md` [S] | 53 |
| `design-best-practices.md` [B] | 41 |
| Critique-flagged shared blind spots | 5 |
| **Total** | **146** |

Vertices were grouped into 13 thematic clusters: project layout, tooling, probe contract, registry, coordinator, cache, hashing, exec/subprocess, output writer, sanitizer, schema, audit, CI/pre-commit. Within each cluster, edges between vertices from different designs were classified.

## L2. Edge classification summary

| Class | Count | Examples |
|---|---|---|
| AGREE | 38 | `click` over `argparse`; `ruff` for lint+format; no entry-point plugin scan; lazy heavy imports; per-probe failure isolation; bounded `Semaphore`; `0` outbound network in Phase 0 (target); `mkdocs-material`; pre-commit + CI; structured logging |
| COMPLEMENT | 27 | Lazy imports [P] + `auto_envvar_prefix=None` [S]; `os.scandir` [P] + symlink-out-of-root rejection [S]; field-name regex [S] + JSON Schema strictness [B]; `Semaphore(8)` [P] + filtered child env [S] |
| SUBSUME | 12 | `_ProbeOutputValidator` (Pydantic, recursive `JSONValue`) [S] subsumes [B]'s plain dataclass; `OutputSanitizer` chokepoint [S] subsumes [P]'s direct `CSafeDumper` write |
| CONFLICT | 16 | Cache hash (xxh3 / SHA-256 / blake3); `fastjsonschema` vs `jsonschema`; `pytest-xdist` on/off; `additionalProperties: false` everywhere vs only-at-envelope; serial coordinator vs async-day-one; HMAC-signed index vs none; gitleaks-in-write-path vs at-CI-only; `pydantic` in Phase 0 vs Phase 6; coverage floor 90/80 vs unset; netns enforcement vs structural; reproducibility CI vs none; CLI cold-start canary as gate vs advisory; benchmark canary as PR-blocker vs advisory; mmap of cache index vs plain read; tool-readiness cache TTL specifics; `aiofiles` as dep or not |
| SHARED-BLIND-SPOT | 5 | `pyproject.toml` shape for gather/service split; `.gitignore` mutation prompt; ABC frozen against moving `localv2.md`; `.codegenie/` permissions under CI cache restore; cache-hit pass-through in coordinator output type |
| **Total** | **98 edges across 146 vertices** | |

## L3. Conflict resolution table

Scoring rubric: each cell 0–3.
- **Exit-fit**: directly serves Phase 0 exit criteria.
- **Roadmap-fit**: makes later phases simpler / unblocks an inheritance.
- **Commitments-fit**: aligns with the load-bearing commitments in `production/design.md §2`. *Veto*: a score of 0 on commitments-fit cannot win regardless of other scores.
- **Critic-fit**: addresses critique-flagged concerns.

| # | Conflict | Option A | A scores (E/R/C/Cr, sum) | Option B | B scores (E/R/C/Cr, sum) | Option C | C scores (E/R/C/Cr, sum) | Winner | Rationale |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Cache content hash | xxh3-128 [P] | 2/0/**0**/0 = **VETO** | SHA-256 [S+B] | 2/2/3/2 = 9 | BLAKE3 (synth, critic-proposed) | 3/3/3/3 = **12** | **BLAKE3** for content; SHA-256 for identity tuple | xxh3 violates commitment §2.3 (Honest confidence — silent staleness) at Phase 14 webhook scale; vetoed. BLAKE3 is cryptographic *and* fast; matches commitment §2.3 and gives [P] its speed argument back. SHA-256 wraps the identity tuple per `localv2.md §8` for `localv2`-compatibility and audit anchor stability. |
| 2 | Schema validator | `fastjsonschema` [P] | 2/0/**1**/0 = 3 | `jsonschema` [S+B] | 2/3/3/3 = **11** | — | — | **`jsonschema`** | Critic §1.1.3 makes the `exec`-at-import attack surface concrete on a persistence path. `fastjsonschema`'s 10× speedup is invisible at Phase 0 scale; revisit in Phase 14. |
| 3 | `pytest-xdist` in Phase 0 | On from day one [P] | 1/1/2/0 = 4 | Off [B] | 2/2/3/3 = **10** | — | — | **Off** | Critic §1.1.4 names a real bug class (shared-fixture races) for zero parallelism win on 5 tests. Enable when there's actual concurrency value. |
| 4 | `additionalProperties` in envelope | `false` everywhere [S] | 2/0/**1**/1 = 4 | `false` at root only [B] | 2/3/3/3 = **11** | Layered (root `false`, `probes.*` `true`, per-probe sub-schemas) [synth] | 3/3/3/3 = **12** | **Layered** | Resolves [S] vs [B] structurally. Adding a probe in Phase 1 is one new file under `schema/probes/` and one `$ref` line — no edit to existing schemas. Honors commitment §2.5 (extension by addition) *and* Honest-confidence at the envelope boundary. |
| 5 | Coordinator concurrency in Phase 0 | Serial stub [B] | 1/0/2/0 = 3 | Async-day-one with `Semaphore(min(cpu, 8))` [P+S] | 2/3/3/3 = **11** | — | — | **Async-day-one** | Critic §3.1.1 makes shipping serial = shipping a stub Phase 1 *replaces*, not extends. Async harness with one probe in Phase 0 = same code path Phase 1 dispatches six probes through. |
| 6 | HMAC-signed cache index | HMAC always [S] | 2/1/2/1 = 6 | No HMAC; revisit Phase 14 [synth] | 3/2/3/3 = **11** | — | — | **No HMAC in Phase 0** | Critic §2.1.1 shows the threat model is unarticulated on dev workstations and broken on ephemeral CI runners. Phase 14's webhook-driven gather is when the multi-actor threat model arrives; design key storage there. |
| 7 | `gitleaks` in synchronous write path | Every gather [S] | 1/0/2/1 = 4 | Pre-commit + CI only [synth] | 3/3/3/3 = **12** | — | — | **Pre-commit + CI only** | Critic §2.1.2 establishes the synchronous cost (O(seconds) at Phase 2 scale) breaks the continuous-gather model. Structural defenses (`_ProbeOutputValidator` field-name regex + path scrubber + recursive `JSONValue`) carry the load-bearing weight. |
| 8 | `pydantic` in Phase 0 | Yes (perf-lazy + security trust boundary) [P+S] | 3/3/3/3 = **12** | No (defer to Phase 6) [B] | 1/0/2/1 = 4 | — | — | **Yes in Phase 0** | Critic §3.2.2: Phase 4's anthropic/langgraph forces pydantic v2 anyway. Lazy-importing it from `_ProbeOutputValidator` gives [S]'s trust boundary today and lets [P]'s cold-start budget hold. |
| 9 | Coverage floor | 90% line / 80% branch [B] | 1/1/1/0 = 3 | None [P] | 0/0/1/0 = 1 | 85% line / 75% branch, ratcheting [synth] | 3/3/3/3 = **12** | **85/75 ratcheting** | Critic §3.2.3: 90/80 with 5 tests is satisfiable only by gameable tests (Rule 9 violation). 85/75 is achievable with focused unit tests; ratchet to 90/80 in Phase 1 when there's surface to test. |
| 10 | Network egress enforcement | `unshare -n` / harden-runner in CI [S] | 1/0/2/1 = 4 | Structural (allowlist + no network imports) [synth] | 3/3/3/3 = **12** | — | — | **Structural** | Critic §2.2.1: `unshare -n` is Linux-only and `localv2.md` supports macOS dev. Structural defense works on every platform; netns CI lands in Phase 14 with the webhook listener. |
| 11 | Reproducibility CI check | Every PR [S] | 1/1/2/0 = 4 | None in Phase 0 [synth] | 3/2/3/2 = **10** | — | — | **None in Phase 0** | Pure-Python wheel build has no non-determinism. Phase 1's probe outputs (SCIP, traces) are where reproducibility matters; land the check then. |
| 12 | CLI cold-start canary | Hard gate [P] | 1/1/2/0 = 4 | Advisory + import-linter [synth] | 3/3/3/3 = **12** | — | — | **Advisory + import-linter** | Critic §1.1.2 shows the canary is structurally flaky on shared GHA runners. `import-linter` enforces the *invariant* structurally; the canary surfaces regressions without blocking PRs. |
| 13 | Click `auto_envvar_prefix` | `"CODEGENIE"` [P] | 2/1/1/0 = 4 | `None` (off in Phase 0) [S] | 2/2/3/3 = **10** | — | — | **Off in Phase 0** | Env-var injection is a real path-traversal vector; perf benefit is negligible; Phase 9 (durable workflows) re-enables with documented scope. |
| 14 | Tool-readiness cache mmap of index | mmap [P] | 1/0/2/0 = 3 | Plain buffered read [synth] | 3/3/3/2 = **11** | — | — | **Plain buffered read** | Critic §1.2.1: concurrent CLI processes mmap'ing an `O_APPEND` index is a race. Index is single-digit MB through Phase 13. Plain read costs nothing measurable. |
| 15 | `aiofiles` in Phase 0 deps | Yes (per roadmap text) | 1/0/2/0 = 3 | No (no code path uses it) [synth] | 3/3/3/3 = **12** | — | — | **Removed** | Critic §7.4: shipping unused deps in Phase 0 contradicts every lens's "simplicity" claim. The roadmap text is a documentation bug; add `aiofiles` when an async file-reading probe needs it. |
| 16 | `mkdocs build --strict` over full `docs/` tree | Yes [B implied] | 0/2/2/0 = 4 (Phase 0 cannot exit; critic §3.1.5) | Curated `nav` excluding `docs/local.md` etc. [synth] | 3/3/3/3 = **12** | — | — | **Curated `nav`** | Critic §3.1.5 establishes the existing tree has broken refs strict mode would surface today. Curated `nav` makes Phase 0 exit-criterion satisfiable; the cleanup is filed as a Phase 1 issue. |

## L4. Shared blind spots — resolutions

| # | Critic-flagged blind spot | Resolution |
|---|---|---|
| 1 | `pyproject.toml` shape for gather/service split | §2.2: `dependencies` *is* the gather closure; `[project.optional-dependencies]` has `gather` (empty marker), `dev` (harness), `service` (Phase 9+), `agents` (Phase 4+ LLM SDKs land here). The `fence` CI job asserts the dependency closure of the wheel contains no LLM SDK. |
| 2 | `.gitignore` mutation path | §2.15: opt-in prompt on TTY; structured-warning no-op on non-TTY; `--auto-gitignore` / `--no-gitignore` flags; atomic append; tested both paths. |
| 3 | ABC frozen against moving `localv2.md` | §2.3 contract freeze policy: snapshot test with a fingerprint hash of `localv2.md §4` content; drift fails CI; ADR amendment template exists in Phase 0; resolution is always "change code to match doc," never the inverse. |
| 4 | `.codegenie/` permissions under CI cache restore | §2.8: writer re-applies `0600`/`0700` via `os.chmod` post-`actions/cache` restore. Mode-bit-check tests assert post-gather perms, not post-cache-restore perms. |
| 5 | Cache-hit pass-through in coordinator output | §2.6: coordinator returns `dict[probe_name, ProbeExecution]` alongside `dict[probe_name, ProbeOutput]`, where `ProbeExecution ∈ {Ran, CacheHit, Skipped}`. Phase 14's incremental model needs this distinction; encoding it now means Phase 14 extends-by-addition, not by interface change. |

## L5. Aggregation — coherence check

A coherent design must avoid contradictions between adopted vertices. Two potential incoherences flagged:

- **Pydantic adopted + `_ProbeOutputValidator` is "an implementation detail of the coordinator" but the ABC is dataclass-based.** Resolved: the *contract* (`Probe`, `ProbeOutput`, `RepoSnapshot`, `Task`, `ProbeContext`) is dataclass-based per `localv2.md §4`. The *validator* (`_ProbeOutputValidator`) is internal Pydantic wrapping a `ProbeOutput` instance at the coordinator's trust-boundary point. The contract still lifts unchanged to the service per ADR-0007.
- **Coordinator returns `ProbeExecution` markers + cache `get/put` API stays narrow.** Resolved: `ProbeExecution` lives in the coordinator's *output* (the run-record schema), not in the cache API. The cache stays `get/put/key_for`; the coordinator records whether the result came from `get` or from `run`.

No further incoherences identified.

## L6. Sanity check — exit criteria, load-bearing commitments, critic concerns

**Exit criteria (roadmap-level):**
- "`codegenie gather` runs on any directory" → §6 data flow; smoke test in §7.2.
- "prints external-tool readiness" → §2.11 tool-readiness check.
- "executes LanguageDetection" → §2.10.
- "writes `.codegenie/context/repo-context.yaml`" → §2.8 writer.
- "CI is green on `main`" → §3.2 six jobs.
- "docs site builds locally without warnings" → §5 curated `nav`.

**Load-bearing commitments (`production/design.md §2`):**
- §2.1 (No LLM in gather) — encoded by the `fence` CI job (§3.2) and the `pyproject.toml` extras (§2.2). ✅
- §2.2 (Facts, not judgments) — `LanguageDetectionProbe` emits a count map, not a judgment. ✅
- §2.3 (Honest confidence) — BLAKE3 + SHA-256 hashing eliminates silent staleness under Phase 14 portfolio threat (§2.7). ✅
- §2.4 (Determinism over probabilism) — Phase 0 is deterministic end-to-end. ✅
- §2.5 (Extension by addition) — `additionalProperties` layered (§2.9); `@register_probe` (§2.4); per-probe sub-schemas. ✅
- §2.6 (Org uniqueness as data) — N/A in Phase 0 (no Skills loaded).
- §2.7 (Progressive disclosure) — `repo-context.yaml` is an index; raw artifacts referenced by path (§2.8). ✅
- §2.8 (Humans always merge) — N/A in Phase 0 (no PRs opened).
- §2.9 (Cost observable + bounded) — audit record captures per-probe timing (§2.12); cost dashboard is Phase 13.

**Critic's roadmap-level critiques (`critique.md §7`):**
- §7.1 (Phase 0 exit criteria don't validate Phase 1-14 contracts) — §11 final-design exit criteria items 4 (cache works on non-empty fixture), 10 (probe ABC snapshot), 11 (`fence` test), 12 (audit verify) close the gap.
- §7.2 (No LLM in gather enforced nowhere) — `fence` CI job + `pyproject.toml` extras shape. ✅
- §7.3 (Roadmap lists pydantic, [B] defers) — pydantic adopted in Phase 0. ✅
- §7.4 (`aiofiles` in roadmap but no design uses it) — removed (§2.2). ✅
- §7.5 (No "facts, not judgments" structural rule) — `_ProbeOutputValidator`'s recursive `JSONValue` + field-name regex makes "no LLM-judgment fields" structural at the probe boundary; the rule is enforced by *what types are representable*, not by review.
- §7.6 (`mkdocs build --strict` unverifiable on existing tree) — curated `nav`. ✅

All exit criteria, all load-bearing commitments, and all roadmap-level critic critiques are addressed.

---

*End of design of record. Implementation begins at §2.1's file layout.*
