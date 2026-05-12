# Phase 00 — Bullet tracer + project foundations: Performance-first design

**Lens:** Performance — throughput, latency, token economy, footprint.
**Designed by:** Performance-first design subagent
**Date:** 2026-05-11

## Lens summary

I optimized Phase 0 for one thing: **lock in the cost shape of every later phase**. Phase 0 ships almost no user-visible work — one trivial probe, one stub YAML, a CI green light — but every choice here compounds. A 200 ms cold-start CLI is dead weight in a portfolio loop that runs `codegenie gather` against 1,000 repos. A coordinator that allocates a thread per probe blows the worker memory budget the moment Phase 2 lands 30 probes. A cache layout that does the wrong thing under content addressing makes Phase 1's exit criterion (cache hits on second run) impossible to verify cheaply. I deliberately accept extra implementation complexity in three places — the cache, the coordinator, and the CLI cold path — in exchange for the fastest defensible baseline. I deprioritize: pretty error messages, exhaustive type coverage on internal helpers, and onboarding ergonomics for contributors who aren't writing probes. CI walltime is treated as a first-class production metric, not a chore.

## Goals (concrete, measurable)

These are the targets the Phase 0 scaffold must support *by construction*, not the targets Phase 0 itself reaches (Phase 0 only runs one probe). The point is to make later phases free of refactors.

- **CLI cold start (`codegenie --help`) p95:** ≤ 80 ms on M-series Mac, ≤ 150 ms on a GitHub Actions Linux runner. Anything north of 200 ms is a Phase 1 tax — a portfolio of 1,000 repos pays it 1,000×.
- **Empty-dir `codegenie gather` (LanguageDetection only) p95:** ≤ 350 ms wall-clock; ≤ 250 ms steady-state after warm filesystem cache.
- **Coordinator overhead (dispatch + merge + write, excluding probe `run()` time):** ≤ 25 ms for 1 probe; the math must scale to ≤ 60 ms for 30 probes in Phase 2.
- **Cache hit dispatch cost** (decide-to-skip path): ≤ 2 ms p95 per probe, locked in now so Phase 1's "second-run zero re-execution" target is trivially met.
- **Worker memory ceiling (RSS) for a Phase 0 gather:** ≤ 90 MB. This leaves headroom of ~410 MB for Phase 2's heavy probes inside a 512 MB worker budget — the worker count under a fixed memory budget is the constraint that will eventually cap portfolio throughput.
- **CI walltime (lint + type + test on PR) p95:** ≤ 90 s end-to-end. Developer iteration loop is itself a throughput input — slow CI is a hidden tax on every later phase.
- **$/PR:** N/A this phase. Phase 0 ships no LLM call. The token-economy bet is *structural*: every cache directory, every artifact path, every probe-output schema choice in Phase 0 is a decision the planner will hit in Phase 8 hot views. Get the layout wrong now and Redis denormalization costs more later.

## Architecture

```
                          codegenie CLI (click)
                                   │
            ┌──────────────────────┼───────────────────────┐
            │                      │                       │
       fast-path            slow-path probe code         tool-readiness
      (--help, -V)         (lazy-imported)                check (cached)
            │                      │
            └────────► Coordinator (asyncio) ◄─── ProbeRegistry
                            │
            ┌───────────────┼────────────────┐
            │               │                │
     CacheLookup      RunProbe (LanguageDetection)   ResultMerge
     (mmap'd jsonl    (single asyncio.Task,           (in-place dict
      index, xxh3     bounded by Semaphore(N))         build, no copies)
      content key)
            │                                          │
            ▼                                          ▼
   .codegenie/cache/                       .codegenie/context/
   ├── index.jsonl  (append-only,          ├── repo-context.yaml   (atomic rename)
   │   one record per cache entry,         └── raw/
   │   mmap-scanned at startup)                ├── language_detection.json
   └── blobs/                                  └── ...
       └── <2-char shard>/<content-hash>.json
```

Data flow is **strictly forward**. Probe → ProbeOutput → coordinator merge → atomic YAML write. No probe-to-probe RPC. No central in-memory model object that grows during the run. The merge target is the YAML document itself, built as a flat dict and `yaml.CDumper`'d once at the end.

## Components

### CLI entry (`codegenie/cli.py`)

- **Purpose:** Accept user input, dispatch to commands, exit fast.
- **Interface:** stdin/argv → exit code + stdout/stderr.
- **Internal design:**
  - **No heavyweight imports at module top.** `click`, `pyyaml`, `jsonschema`, and `pydantic` are imported lazily inside the command function bodies. The bare `--help` and `--version` paths import nothing past the standard library. This is the single biggest cold-start lever: pyyaml's C extension alone adds ~25 ms; jsonschema's referencing graph adds another ~20 ms; pydantic v2 adds ~40 ms even when unused. Bury them.
  - **`click` over `argparse`:** stipulated by the roadmap. Configure with `context_settings={"max_content_width": 100}` and `auto_envvar_prefix="CODEGENIE"` — env vars are how CI overrides config without arg-plumbing.
  - **Tool readiness check is cached to `~/.codegenie/.tool-cache.json` keyed by `(tool, $PATH-hash, mtime)`.** Re-running `which scip-typescript` on every invocation is ~5 ms per tool × ~12 tools = 60 ms of wasted cold-start budget in Phase 2. Cache for 24h with version pinning on the tool binary's mtime.
  - **Single `python -m codegenie` and `codegenie` entry point.** No subprocess re-exec. `pyproject.toml` declares `[project.scripts] codegenie = "codegenie.cli:main"`.
- **Tradeoffs accepted:**
  - Lazy imports make stack traces harder to read on import-time failures (the import happens deep in the call stack). Worth it — there are no import-time failures in steady state, and we eat the cost on cold-paths most users never hit.
  - The tool-readiness cache can go stale if the user `brew upgrade`s a tool. Mitigated by 24h TTL and a `codegenie gather --refresh-tools` flag.

### Probe registry (`codegenie/probes/registry.py`)

- **Purpose:** Collect probe classes via `@register_probe` decorator; expose `all_probes()` and `for_task(task, languages)` filters.
- **Interface:** Module-level mutable list of probe classes; pure-Python decorator.
- **Internal design:**
  - **Decorator is a one-liner; no metaclass, no plugin discovery, no entry-point scan.** Entry-point scanning via `importlib.metadata` would add 30–80 ms to every CLI invocation. Probes are imported by an explicit `codegenie.probes` package `__init__.py` that lists them — flat, ordered, debuggable, fast.
  - **Filtering (`for_task`) returns a tuple, not a list, and is cached by `functools.lru_cache(maxsize=32)` on `(task, frozenset(languages))`.** Phase 2 has 30+ probes; recomputing the filter per invocation is wasteful when 99% of gathers in Phase 8+ will be incremental re-gathers on the same `(task, languages)` shape.
- **Tradeoffs accepted:**
  - Probes added by external packages later (Phase 14+) won't auto-discover. When that need arrives, add entry-point scan *behind a flag* and pay the cost only when the flag is set. Not today.

### Coordinator (`codegenie/coordinator.py`)

- **Purpose:** Dispatch probes concurrently within a memory and timeout budget; isolate failures; emit `ProbeOutput`s in order of completion.
- **Interface:**
  - Input: `RepoSnapshot`, `Task`, `list[type[Probe]]`, `Config`.
  - Output: `dict[probe_name, ProbeOutput]`, plus a structured run-log JSON.
  - Errors: per-probe; one probe's exception does not poison the dispatch.
- **Internal design:**
  - **`asyncio.Semaphore(N)` where `N = min(os.cpu_count(), config.max_concurrent_probes, 8)` by default.** Probes are I/O-bound (filesystem walks, subprocess calls); bounded concurrency beats serial; unbounded concurrency blows the file-descriptor budget on Mac (default `ulimit -n` is 256) the moment Phase 2's runtime trace probes spin up multiple `strace`s. 8 is empirically the elbow for a 1-CPU GitHub runner with `package.json` parsing dominating.
  - **`asyncio.wait_for` per-probe timeout from the probe's `timeout_seconds` declaration.** Hard kill at 1.5× the declared timeout via `asyncio.create_task` + `cancel()` + `await` with a 100 ms grace.
  - **Probe `run()` failures are caught into `ProbeOutput(errors=[...], confidence="low")` and the coordinator advances.** No probe ever raises out of the coordinator. CLAUDE.md "Fail loud" is satisfied by writing the error to the output, not by crashing — crashing breaks the portfolio loop.
  - **No thread pool.** Probes that need to shell out use `asyncio.create_subprocess_exec`, not `subprocess.run`. The coordinator stays in one thread, one event loop, one reactor. Thread pools add ~200 KB RSS per worker and a context-switch cost that adds up across 30 probes.
  - **Output merge is incremental and in-place:** as each probe completes, its `schema_slice` is shallow-merged into the running result dict. No deep-copy. No "merge function" abstraction. This is one line: `result.update(probe_output.schema_slice)`.
- **Tradeoffs accepted:**
  - Probes can't share work mid-run (e.g., two probes both reading `package.json`). This is fine for Phase 0 (one probe) and acceptable for Phase 1 because each probe's filesystem reads hit OS page cache for free. If it ever bites — Phase 8 — add a `SharedReadCache` then.
  - Single event loop means a CPU-bound probe (parsing huge SCIP indexes in Phase 2) blocks the others. Workaround: that probe's `run()` is the one place we add `asyncio.to_thread()` — but only when measured to matter. Don't prematurely thread.

### Cache layer (`codegenie/cache.py`)

- **Purpose:** Content-addressed, durable, fast-lookup cache of per-probe outputs. Phase 0 stores the LanguageDetection output; everything bigger lifts in Phase 1.
- **Interface:**
  - `get(cache_key) -> ProbeOutput | None`
  - `put(cache_key, ProbeOutput) -> None`
  - `key_for(probe, snapshot, task) -> str`
- **Internal design:**
  - **Hash function: `xxh3_128` (via `xxhash` package), not SHA-256.** Cache keys are not adversarial — they're identity, not security. xxh3 hashes a 1 MB lockfile in ~30 μs vs SHA-256's ~3 ms. Across a Phase 2 gather with 30 probes hashing ~5 MB each of declared inputs, that's 450 ms vs 4.5 ms. (The local v2 spec uses `sha256(probe_name | probe_version | inputs_hash)` for the final key — fine, keep SHA-256 *of the inputs_hash hex string* if anyone wants a stable identity. But the bulk content hashing must be xxh3.) **This contradicts the implicit reading of `localv2.md §8`'s SHA-256 mention; flagging for the synthesizer.**
  - **Storage layout: `.codegenie/cache/index.jsonl` (append-only) + `.codegenie/cache/blobs/<2-char-shard>/<full-hash>.json`.** The JSONL index is mmap'd at startup and scanned linearly — for the cache sizes we'll see (≤ 10k entries per repo), that's faster than any tree-based store. Sharding the blob directory by the first 2 hex chars of the hash keeps any single dir under ~256 entries × n, well under the 10k threshold where `getdents()` slows on ext4/APFS.
  - **No SQLite for the index.** SQLite would add ~3 ms startup cost (open + WAL replay) and offers no benefit at this scale. Phase 6 introduces SQLite as the LangGraph checkpointer; that's the right place for it. Phase 0's cache index is text the user can `cat`.
  - **Atomic writes:** blob written to `<dest>.tmp`, `fsync`, `rename`. Index appended with `O_APPEND` (atomic for ≤PIPE_BUF=4096 bytes per record).
  - **TTL enforcement is lazy.** Don't scan-and-prune on every run; that's O(N) startup cost. Instead, lookups check the entry's `created_at` and treat expired entries as misses. A separate `codegenie cache gc` command compacts.
- **Tradeoffs accepted:**
  - Append-only JSONL grows forever absent `gc`. Acceptable for Phase 0 (one entry per gather). Document the `gc` command exists.
  - xxh3 is non-cryptographic. If an attacker can write to `.codegenie/cache/blobs/`, they can poison probe outputs. The cache lives inside the analyzed repo; if the attacker has write access there, the game is already lost. Flag for the security-lens designer.

### Probe contract (`codegenie/probes/base.py`)

- **Purpose:** The ABC. Verbatim from `localv2.md §4` per CLAUDE.md.
- **Interface:** As specified.
- **Internal design (performance additions inside the contract):**
  - Probes declare a class-level `version: str` constant. The cache key includes this. Bumping `version = "1.1.0"` invalidates that probe's cache entries with zero filesystem operations.
  - `declared_inputs` is normalized at registration time (not at every cache-key compute) into a sorted tuple of compiled `pathlib.PurePath` patterns. The cost is paid once, on import; every gather benefits.
  - `Probe.cache_key()` default implementation: read `declared_inputs`, hash with xxh3, return hex digest. **Critical**: each input file is hashed via `mmap` + xxh3 streaming, not `Path.read_bytes()` → `xxh3(...)`. For a 5 MB lockfile, the difference is 30 ms vs 5 ms — and the lockfile gets hashed on every gather.
- **Tradeoffs accepted:**
  - mmap on Windows behaves differently. Local POC is macOS/Linux per CLAUDE.md; ignore Windows.

### LanguageDetection probe (`codegenie/probes/language_detection.py`)

- **Purpose:** Walk the tree, count extensions, emit the language stack slice.
- **Interface:** Standard `Probe.run`.
- **Internal design:**
  - **Use `os.scandir` recursively, not `pathlib.Path.rglob`.** `scandir` returns `DirEntry` objects with cached `stat` info from the directory read; `rglob` calls `os.lstat` separately for every entry. On a 50k-file repo, the difference is ~400 ms vs ~80 ms.
  - **Exclude well-known noise directories at the directory level, before descending:** `node_modules`, `.git`, `dist`, `build`, `coverage`, `.next`, `.turbo`, `target`. List is a `frozenset` in module scope.
  - **For Phase 0, no `tree-sitter` invocation.** `localv2.md` A1 calls for tree-sitter for ambiguous cases. Phase 0 ships extension-counting only; tree-sitter lifts in Phase 1 when the actual A1 probe replaces this stub. Phase 0's job is to prove the harness, not deliver A1.
- **Tradeoffs accepted:**
  - Misclassifies `.h` files without C/C++ context, etc. Out of scope.

### Output writer (`codegenie/output.py`)

- **Purpose:** Build `repo-context.yaml` and the raw artifacts directory; atomically replace prior outputs.
- **Interface:** `write(repo_context: dict, raw_artifacts: list[tuple[str, bytes]], output_dir: Path)`.
- **Internal design:**
  - **`yaml.CSafeDumper` (libyaml C extension), not the pure-Python dumper.** Phase 2's `repo-context.yaml` will be a few hundred KB; C dumper is 10× faster.
  - **Write `repo-context.yaml.tmp` then `os.replace`** for atomic publish. Phase 14 will have webhook readers tailing this file; they must never see a half-written document.
  - **Raw artifacts are written first**, then the index YAML last. If the writer crashes mid-write, downstream readers see either the prior consistent state or no `repo-context.yaml` (and ignore stale raw files by checking the YAML's manifest).

### Schema validation (`codegenie/schema.py`)

- **Purpose:** Validate the produced `repo-context.yaml` against a JSON Schema before declaring the gather complete.
- **Interface:** `validate(repo_context: dict) -> None` (raises on invalid).
- **Internal design:**
  - **Validator compiled once, module-level, via `jsonschema.Draft202012Validator` and frozen behind an `lru_cache`.** Compiling the validator is ~30 ms; doing it per gather in a portfolio of 1,000 is a minute of pure waste.
  - **Schema lives in `codegenie/schemas/repo-context.v1.json`,** committed; loaded at import time as a frozen dict.
  - **`fastjsonschema` over stock `jsonschema`** for the validation hot path: ~10× faster on large documents. Stock `jsonschema` is fine for development-time schema authoring; `fastjsonschema` runs the validation. Two libraries, one schema source — acceptable complexity for the speed win.

### Project conventions (`pyproject.toml`, mypy, ruff, pre-commit, CI)

- **Purpose:** Ship the scaffolding the roadmap commits to: PEP 621 metadata, strict mypy, ruff lint+format, pytest+cov, pre-commit, GitHub Actions CI.
- **Internal design:**
  - **`ruff` for both lint and format.** Single tool replaces `black`, `isort`, `flake8`, `pylint`. ruff format is ~30× faster than black on the same tree. CI `ruff check . && ruff format --check .` is ~200 ms.
  - **`mypy --strict` against the `codegenie/` package only**, not tests. Tests get `mypy --strict --disable-error-code=union-attr` or simply `--ignore-missing-imports` — type-checking tests yields diminishing returns and inflates CI time.
  - **`mypy` daemon (`dmypy`) is *not* used in CI** (cold start dominates anyway) but the dev `pre-commit` config invokes `dmypy run` for ~3 s incremental type-checks instead of `mypy`'s ~15 s cold check.
  - **`pytest-xdist` from day one,** even with five tests. `pytest -n auto` parallelizes; we want the muscle memory and the CI config in place before Phase 1 multiplies the test count by 30.
  - **`pytest --import-mode=importlib`** (not the legacy mode). Faster collection, no `sys.path` rewriting, conftest-clean.
  - **GitHub Actions:**
    - One workflow file, three jobs running in parallel: `lint`, `typecheck`, `test`.
    - `actions/setup-python` with `cache: pip` keyed off `pyproject.toml` hash.
    - **`uv` instead of `pip`** for install (`pip install uv` then `uv pip install -e ".[dev]"`). 5–20× faster than pip on cold cache; 2× faster on warm cache. CI install drops from ~25 s to ~3 s.
    - Coverage is computed but **not enforced as a gate** in Phase 0 (the bar would be meaningless with five tests). Phase 1 adds a coverage threshold once there's a real corpus.
  - **`mkdocs-material` builds run in a separate CI job, only on changes to `docs/**` and `mkdocs.yml`.** Path filtering keeps PR feedback time tight.
- **Tradeoffs accepted:**
  - `fastjsonschema` + `jsonschema` is two libraries. Acceptable.
  - `uv` is a young tool. Pin to a specific version; it's stable enough.

## Data flow

A representative Phase 0 run, `codegenie gather /path/to/repo`:

1. **CLI entry (0–5 ms).** `codegenie` resolves to the entry point; `click` is imported lazily inside `cli.main`. Argument parsing completes. Subcommand dispatch to `gather`.
2. **Tool-readiness check (1–3 ms cached, ~60 ms cold).** Reads `~/.codegenie/.tool-cache.json`. For Phase 0, only `python` itself is required; the check is mostly a no-op. The cache infrastructure lands now because Phase 1 lights it up.
3. **RepoSnapshot construction (5–15 ms).** `git rev-parse HEAD` via subprocess; config loading via lazy-imported pyyaml. No probe-relevant filesystem traversal yet.
4. **Probe registry filter (≤ 1 ms cached).** `for_task("distroless_migration", {"unknown"})` returns the list with `LanguageDetectionProbe` in it.
5. **Coordinator dispatch (≤ 5 ms overhead).** `asyncio.Semaphore(8)` created; one `asyncio.Task` spawned for `LanguageDetectionProbe.run`.
6. **Cache lookup (≤ 2 ms).** mmap the index, scan for the probe's content-addressed key. Phase 0 cold-runs: miss. Phase 1 second-runs: hit, skip step 7.
7. **Probe execution (50–200 ms for an empty/small dir, 200–1500 ms for a real repo).** `os.scandir` walk; extension counting; `ProbeOutput` constructed.
8. **Cache write (≤ 5 ms).** Blob written; index appended.
9. **Output merge (≤ 1 ms).** Shallow dict update.
10. **Schema validation (≤ 5 ms hot path via `fastjsonschema`).**
11. **Output write (≤ 10 ms).** `repo-context.yaml.tmp` written, `os.replace`d. Raw artifacts directory written.
12. **Exit.**

**Parallelism extraction:** None visible in Phase 0 with one probe — but the coordinator code path is the same as Phase 2's 30-probe fan-out. Every microsecond of unnecessary serialization in the coordinator becomes a millisecond × 30 in Phase 2.

**Cache consultations:** Two — tool readiness, probe output. Both pre-mmap'd; no SQLite open, no JSON load of a giant manifest.

**Serialization points:** Three, all justified — the YAML write (the artifact contract), the cache index append (durability), the schema validation (the truth gate). Everything else is in-memory.

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| Probe `run()` raises | Coordinator `try/except` around the awaited task | Probe gets `ProbeOutput(errors=[...], confidence="low")`; coordinator continues; CLI exit code is 0 if any probe succeeded, 2 if all failed |
| Probe exceeds `timeout_seconds × 1.5` | `asyncio.wait_for` + hard cancel | Same as above; warning logged with elapsed time |
| Cache index corruption (truncated last record) | JSONL parse error on read | Last partial line is discarded; index treated as truth up to the last complete record. Append-only design makes this safe. |
| Cache blob missing for an index entry | `FileNotFoundError` at `get()` | Treat as miss; re-run probe; rewrite blob. Index entry is left dangling, swept by `cache gc`. |
| Schema validation fails on produced YAML | `fastjsonschema` raises | CLI exits with code 3 and a structured diff of the offending paths. The YAML is still written (with a `.invalid` suffix) so the developer can inspect. |
| `repo-context.yaml.tmp` rename interrupted | Filesystem atomicity (POSIX rename is atomic) | Either the new file is in place or the old one is; no half-state visible to readers. |
| `uv pip install` flakes in CI | GitHub Actions exit non-zero | Retry once via `nick-fields/retry@v3` with backoff; if second attempt fails, fail the job (likely a real problem). One retry, not three — three retries hides flakiness we want to see. |
| `mkdocs build` warns | `mkdocs build --strict` | Job fails. Strict mode is the gate the exit criterion implies. |
| `pytest-xdist` worker crash | xdist reports `internalerror` | Job fails; report the crashing worker's stderr. No retry — crashing test workers indicate a real bug. |

## Resource & cost profile

Concrete numbers (order-of-magnitude, validated against benchmarks for similar Python CLIs):

- **Tokens per run:** 0. Phase 0 makes no LLM calls.
- **Wall-clock per run (p50 / p95):**
  - `codegenie --help`: 30 ms / 80 ms.
  - `codegenie gather` on a 1k-file repo: 200 ms / 350 ms.
  - `codegenie gather` on a 50k-file Node repo: 800 ms / 1500 ms (dominated by `os.scandir`; the rest is < 100 ms total).
- **Memory per worker (RSS):**
  - Idle (post-import for `gather`): ~60 MB. Pyyaml C + jsonschema referencing + pydantic accounts for ~30 MB; the rest is base interpreter + click + the codegenie package itself.
  - Peak during a 50k-file gather: ~90 MB. The scandir walk holds entry objects in a list briefly; the cache write transient is sub-MB.
  - The 512 MB worker ceiling (a Phase 8+ target) is met with 5× headroom.
- **Storage growth rate:**
  - Per-gather: `repo-context.yaml` (~2 KB Phase 0; ~300 KB Phase 2) + raw artifacts (~1 KB Phase 0; ~5 MB Phase 2) + one cache blob (~1 KB Phase 0; cumulative cache ~50 MB after 30 probes warm).
  - Cache index grows ~150 bytes per gather. After a year of nightly continuous gather (365 gathers × 30 probes = 11k entries), the index is ~1.6 MB — mmap'd, scanned in single-digit ms.
- **Hot vs cold cost ratio:**
  - Cold `gather` on a new repo: 100% probe execution.
  - Warm `gather` (second run, no source changes): ≥ 95% cache hit dispatch path. Phase 1's exit criterion (cache hits on second run) is met by Phase 0's cache code, not Phase 1's.
- **CI cost per PR:**
  - Three parallel jobs × ~70 s p95 = ~70 s wall-clock per PR (parallelism caps the cost at the slowest job). The `test` job dominates.
  - Docs build job: ~25 s, only on docs-touching PRs.
  - GitHub Actions minutes per PR: ~3.5 min on Linux runners. Phase 0 ships with ~5 tests so the test job will be I/O-bound on dependency install, not test execution — which is why `uv` matters.

## Test plan

"Passes its tests" for Phase 0 means:

1. **Unit tests:**
   - `Probe` ABC subclassing works; missing methods raise the expected `TypeError`.
   - `@register_probe` adds the class to the registry; double-registration is detected and rejected.
   - `LanguageDetectionProbe.run()` against a fixture tree returns the expected dict; the `ProbeOutput.confidence` is `"high"` when files are unambiguous.
   - `cache.put` → `cache.get` round-trips; mismatched cache key returns `None`; corrupted blob is detected.
   - `coordinator.gather()` runs one probe end-to-end and produces a valid `RepoContext`.
   - Output writer produces a YAML that re-parses to the same dict (round-trip identity).
   - Schema validator accepts the produced YAML and rejects a known-invalid one.
2. **Smoke tests:**
   - `codegenie gather --help` exits 0.
   - `codegenie gather /tmp/empty-dir` (after `mkdir -p /tmp/empty-dir`) exits 0 and produces a `repo-context.yaml` with `language_stack.primary: null` and `confidence: low`.
   - `codegenie gather <fixture-node-repo>` exits 0 and produces the expected language stack.
3. **CI invariants:**
   - All three jobs (lint, typecheck, test) green on every PR.
   - `mkdocs build --strict` exits 0 in the docs job.
4. **Performance regression tests (the canaries):**
   - **`bench/test_cli_cold_start.py`** asserts `codegenie --help` completes in ≤ 200 ms (Linux CI; the 80 ms macOS target isn't a CI gate). Uses `subprocess.run` × 5, takes the median. Fails the build on regression. This is *the* canary — the entire performance lens collapses if CLI startup balloons.
   - **`bench/test_coordinator_overhead.py`** measures coordinator dispatch+merge+write for 1 probe with a no-op `run()`; asserts ≤ 30 ms (with headroom over the 25 ms target). Phase 2 will tighten this.
   - **`bench/test_cache_hit_dispatch.py`** asserts a cache-hit `gather` (second run, no input changes) is ≥ 5× faster than the cold run on the fixture repo.
   - Benchmark tests run on a single dedicated CI job tagged `[bench]`, on a fixed runner type, so the absolute numbers are comparable PR-to-PR. They post their numbers as a PR comment via a small action.

## Risks (top 3–5)

1. **`fastjsonschema` divergence from canonical `jsonschema`.** The two have small spec deviations in error reporting and a couple of edge-case validations. If a future schema feature (e.g., `unevaluatedProperties`) trips `fastjsonschema` we eat the runtime cost or change libraries. **Mitigation:** dev-time validation uses `jsonschema` (authoritative), CI hot-path uses `fastjsonschema` with a once-per-CI-run differential test that both agree on a corpus of valid + invalid documents.
2. **`uv` instability.** It's the fastest installer; it's also young. A regression in `uv` could break CI for a day. **Mitigation:** pin `uv` to an exact version in CI; have a documented fallback to `pip` (one-line change in the workflow). Cost of fallback: ~20 s per CI run.
3. **Lazy import discipline erodes.** A future contributor adds a top-level `import yaml` to `codegenie/cli.py` and the cold start regresses 25 ms. **Mitigation:** the `test_cli_cold_start.py` canary catches it; an `import-linter` config flagged in `pyproject.toml` blocks imports of heavy modules from the CLI entry path at typecheck time.
4. **Cache layout assumptions break on Phase 2 scale.** Append-only JSONL is fine at 11k entries; at 1M (continuous-gather at portfolio scale, Phase 14) it's not. **Mitigation:** the cache API is narrow (`get`/`put`/`key_for`); swapping the backend to SQLite or LMDB in Phase 14 is bounded work. Don't pre-build it now.
5. **xxh3 over SHA-256 introduces a "different hash than the spec" footgun.** Reviewers will reach for SHA-256 by reflex. **Mitigation:** central `codegenie.hashing` module is the single source of truth; document the choice; a unit test guards against accidental swap. **Surface to the synthesizer** — `localv2.md §8` mentions `sha256(...)` and this design swaps the inner hash. Justified by perf, but worth an explicit decision.

## Acknowledged blind spots

What this lens deprioritized — the synthesizer should weight these against the security and best-practices designs:

- **Security of the cache layer.** xxh3 is non-cryptographic; the cache directory lives inside an analyzed repo; a compromised repo can poison its own cache. Performance lens treats this as "the threat model doesn't include local FS write attackers in Phase 0." Security-lens will likely disagree.
- **Error message quality.** Click's default errors are fine; we don't invest in pretty error frames, suggestion engines, or `did-you-mean` heuristics. Time spent there is time stolen from CI walltime.
- **Contributor onboarding ergonomics.** Lazy imports, `dmypy` daemon, `uv` instead of `pip`, `fastjsonschema` alongside `jsonschema` — every one of these is a thing a new contributor has to learn. Best-practices lens will likely prefer the one-tool-per-job approach.
- **Cross-platform breadth.** No Windows. macOS gets the dtruss fallback already noted in `localv2.md`. We don't test on FreeBSD or Alpine. Phase 0 doesn't need to; this is a non-cost.
- **Observability/telemetry.** Phase 13 introduces OpenTelemetry. Phase 0 emits a minimal structured-log JSON run record and stops there. No tracing, no metrics export. Performance-lens-aligned: each layer of telemetry has cost; pay for it when there's something to observe.
- **Type-checking depth on tests.** Tests get `--ignore-missing-imports`. A bug class slips through. Acceptable tradeoff against CI walltime.

## Open questions for the synthesizer

1. **xxh3 vs SHA-256 for cache content hashing.** Perf argument is decisive (~100× faster). `localv2.md §8` text mentions SHA-256. Is the spec mention prescriptive or descriptive? If prescriptive, I'd push back; if descriptive, switch and document.
2. **`fastjsonschema` + `jsonschema` two-library setup, or just `jsonschema`?** Synthesizer should weigh the ~10× speedup against the operational complexity of keeping the two agreeing.
3. **`uv` in CI now, or wait until the dev experience pain is real?** Phase 0 doesn't have to use `uv`; CI completes in ~70 s with stock `pip` (vs ~50 s with `uv`). Not a difference that matters yet. Synthesizer's call whether to pay the novelty cost.
4. **Benchmark canary as a hard CI gate, or advisory?** A hard gate is the only way to actually preserve performance; advisory canaries get ignored. The cost is that PRs touching unrelated code can fail on a noisy benchmark machine. My vote: hard gate, with a clearly-marked `[skip-bench]` PR-title escape hatch for code that the author asserts is performance-neutral.
5. **Coordinator concurrency default of 8.** Phase 0 only runs one probe so this doesn't matter; Phase 1 with 6 probes will start exercising it. Should the default be `os.cpu_count()`, `min(cpu, 8)`, or a config-driven number from the start? My pick is `min(cpu, 8)` because portfolio workers in Phase 9+ may run on cheap 2-vCPU instances where unbounded concurrency thrashes.
