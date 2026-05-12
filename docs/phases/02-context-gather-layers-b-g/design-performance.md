# Phase 2 — Context gathering — Layers B–G: Performance-first design

**Lens:** Performance — throughput, latency, token economy, footprint.
**Designed by:** Performance-first design subagent
**Date:** 2026-05-12

## Lens summary

Phase 2 is the phase that, if designed naively, destroys the continuous-gather model. Phase 1 is six pure-Python parsers over manifest files; cold p95 lands at single-digit seconds. Phase 2 introduces probes that wrap `semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, `tree-sitter`, runtime tracers, and a `networkx` depgraph. Each of those tools, run from scratch on every gather, is 5–60 s of cold subprocess. Six of them in sequence on every push at portfolio scale is the Cursor reference workload run in reverse — instead of >90% cache reuse, you get >90% wall-clock spent on tools that nothing changed for. ADR-0006 ("continuous deterministic gather") and ADR-0013 (pre-rendered hot views) only survive Phase 2 if the layer is engineered for **cache hits at the granularity each tool changes at**.

I optimized for, in priority order:
1. **Cache hit rate per probe at portfolio scale.** Most probes' inputs change rarely; the cache key must reflect that. `SCIPIndexProbe` invalidates on TS source change but not on `Dockerfile` change. `SemgrepProbe` invalidates on rule-pack version OR target files. `IndexHealthProbe` must be cheap enough to run on every gather without itself becoming the bottleneck.
2. **Incremental work on warm-but-changed gathers.** When only `package.json` changed, only the probes whose declared inputs include `package.json` should fire. Phase 1's PathIndex-style fingerprint extends here.
3. **Eager pre-warm via daemons** for the tools whose startup costs dominate their actual work. `scip-typescript` and `semgrep --metrics off` both lose 1.5–3 s of their per-run wall clock to JVM/Python startup. A long-lived worker daemon model eliminates that on repeat gathers within the same worker lifetime — which is the Phase 14 worker model anyway.
4. **Tier the probes by cost and gate by need.** The 80-second runtime trace (`RuntimeTraceProbe`) is opt-in per task class; for the Phase 1 "every push" workload we run the cheap probes deterministically and let the expensive probes fire only when an *expensive-input* (Dockerfile, lockfile) changed. This is the difference between 50,000 useless 80-second runs/day and 50,000 useful 250-ms ones.
5. **Pre-shaping for ADR-0013 hot views.** Same as Phase 1: the slices Phase 8 will project into Redis (`risk_flags`, `confidence_summary`) get their canonical shape now so Phase 8's projection is a dict-copy, not a full re-walk.

I deprioritized: defensive depth of the runtime-trace probe across container runtimes (one happy path: Docker on Linux via `strace`); a "developer-friendly" cold-run UX when a fresh dev box has none of the tools installed; cross-platform parity (macOS gets degraded `RuntimeTraceProbe` and that's fine — Phase 14 runs Linux). I deprioritized "pretty progress logs" beyond what Phase 0 sanitizer already gives. I deprioritized supporting *every* SCIP indexer language; Layer B Phase 2 ships TypeScript only.

## Goals (concrete, measurable)

These are aggressive targets measured against the ADR-0006 continuous-gather model. The roadmap exit criterion ("every probe layer runs against real repos; IndexHealthProbe surfaces at least one real staleness case") is the floor; below are the ceiling I'm optimizing for.

- **Workflows/hour at portfolio scale (single 16-core worker, Phase-14 shape):** ≥ 1,200/hr in steady state across Phases 1+2 combined. That implies p50 ≤ 3 s end-to-end per incremental gather including all Layer B–G probes; ≥ 88% per-probe cache hit at portfolio steady state.
- **Time-to-PR contribution from Phase 2 (p95):**
  - Incremental gather (no semantically-relevant file changed): ≤ 400 ms — the gather is dominated by `IndexHealthProbe` cheap check + cache lookups for everything else.
  - Warm gather (TS source changed, no Dockerfile change): ≤ 6 s — SCIP re-index dominates; everything else cache-hits.
  - Warm gather (Dockerfile changed, no source change): ≤ 8 s — `semgrep` over Dockerfile rules + dependency graph re-compute dominate; SCIP cache-hits.
  - Cold first-run (50k LOC TS service, no cache): ≤ 90 s **with the daemons cold-started**, ≤ 60 s when daemons are pre-warmed. `RuntimeTraceProbe` is **not in this number** because it's opt-in per task class (Phase 3+ gates it).
  - `RuntimeTraceProbe` when invoked: ≤ 90 s (5 scenarios, parallel where independent). Same as Phase 1 localv2 baseline.
- **Tokens per run:** 0. ADR-0005 invariant; `fence` CI job extended to Phase 2 deps.
- **$/PR target:** $0.00 for the gather; the CPU-budget budget is ≤ 8 CPU-seconds per incremental gather (Phase 2 contribution); ≤ 80 CPU-seconds per cold gather (most of that is `scip-typescript`).
- **Cache hit rate per probe at portfolio steady state:**
  - `IndexHealthProbe`: **N/A — it does not cache**, but its work budget is ≤ 50 ms per gather.
  - `SCIPIndexProbe`: ≥ 92% (TS source files change rarely on average across portfolio).
  - `SemgrepProbe`: ≥ 90% (rule pack version + source hash; rule packs are versioned).
  - `GitleaksProbe`: ≥ 90% — same model; bonus optimization with `gitleaks --staged` mode for PR webhook trigger to scan only the diff.
  - `SyftSBOMProbe` / `GrypeCVEProbe`: ≥ 95% on warm + ≥ 85% on CVE-feed-triggered (a new CVE is only relevant if the SBOM contains the affected package).
  - `RuntimeTraceProbe`: ≥ 98% on incremental; runs only on Dockerfile / lockfile / image-digest changes.
  - `DepGraphProbe`: ≥ 90%.
  - `ConventionsProbe` / `SkillsLoaderProbe` / `ADRProbe` / `RepoNotesProbe`: ≥ 99% (these change at PR rate, not push rate).
- **Per-worker memory ceiling:** ≤ 600 MB RSS per active gather including the daemon for `scip-typescript`; ≤ 200 MB resident between gathers. The runtime trace probe is a separate process so it doesn't perturb the worker's resident set.
- **Cold-start daemon budget (Phase 14 worker boot):** ≤ 4 s to pre-warm `scip-typescript --pipe`, `semgrep --pre-load`, and a `tree-sitter` parser bank. Done once per worker lifetime, amortized over thousands of gathers.
- **Tail latency (p99):** ≤ 1.5 s on incremental gather. The 99th percentile is what shows up in Phase 13's cost-per-PR ledger.
- **Hot-view pre-render budget:** Phase 2 must produce `risk_flags` and `confidence_summary` (the two Phase-8 hot views Phase 2 newly informs) in canonical shape — ≤ 5 ms projection at Phase 8 time. Done by Phase 2 emitting these slices in their final shape, not via Phase 1's `views.json` artifact (which the synthesizer correctly rejected) but via the same per-probe sub-schemas Phase 1 established.

## Architecture

```
                            codegenie gather <path>
                                       │
                                       ▼
                  ┌───────────────────────────────────────────┐
                  │  Phase 0/1 CLI entry + Coordinator        │  ← unchanged
                  │  - ProbeExecution ∈ {Ran, CacheHit, Skipped}│
                  │  - ParsedManifestMemo (Phase 1)           │
                  │  - SnapshotBuilder/PathIndex (Phase 1)    │
                  └─────────────────┬─────────────────────────┘
                                    │
                                    ▼
                  ┌───────────────────────────────────────────┐
                  │   DaemonPool (NEW — Phase 2)              │
                  │  - scip-typescript --pipe (long-lived)    │
                  │  - semgrep --pre-load (Python proc)       │
                  │  - tree-sitter parser bank (in-process)   │
                  │  - lifecycle = worker lifetime            │
                  │  - PER PROBE: invoke via stdin/stdout     │
                  │    rather than spawn fresh process        │
                  └─────────────────┬─────────────────────────┘
                                    │
        ┌───────────────────────────┴─────────────────────────────────────┐
        │                                                                 │
        ▼                          ▼                          ▼            ▼
┌──────────────┐    ┌────────────────────┐    ┌──────────────────┐  ┌────────────┐
│ Tier-0       │    │ Tier-1             │    │ Tier-2           │  │ Tier-3     │
│ Pure-Python  │    │ Daemon-pooled tool │    │ Subprocess tool  │  │ Opt-in by  │
│ no I/O       │    │ invocations        │    │ heavy            │  │ task class │
│              │    │                    │    │                  │  │            │
│ B2 IndexHlth │    │ B1 SCIPIndex       │    │ C2 Syft (image)  │  │ C4 Runtime │
│ D1-D7 confs/ │    │ B4 GeneratedCode   │    │ C3 Grype (SBOM)  │  │   Trace    │
│   skills/    │    │   (tree-sitter)    │    │ G1 Semgrep       │  │   (Phase 5 │
│   ADRs/exc/  │    │ B3 Reflection      │    │   (full corpus)  │  │    gates   │
│   notes      │    │   (tree-sitter)    │    │ F1 Gitleaks      │  │   it on)   │
│ B5 DepGraph  │    │                    │    │                  │  │            │
│   (networkx) │    │                    │    │                  │  │            │
└──────────────┘    └────────────────────┘    └──────────────────┘  └────────────┘
        │                          │                          │            │
        └─────────────┬────────────┴──────────────────────────┴────────────┘
                      │
                      ▼
        ┌───────────────────────────────────────────┐
        │  Per-probe content-addressed cache         │
        │  (Phase 0/1 store, extended with daemon-  │
        │   aware key components)                   │
        └─────────────────┬─────────────────────────┘
                          │
                          ▼
        ┌───────────────────────────────────────────┐
        │  Stream-merge + sanitizer (Phase 0/1)     │
        │  + new sub-schemas:                       │
        │    index_health.schema.json               │
        │    semantic_index.schema.json             │
        │    reflection.schema.json                 │
        │    generated_code.schema.json             │
        │    build_graph.schema.json                │
        │    sbom.schema.json                       │
        │    cve_scan.schema.json                   │
        │    secret_scan.schema.json                │
        │    semgrep_findings.schema.json           │
        │    test_coverage_map.schema.json          │
        │    organizational.schema.json (extension) │
        └─────────────────┬─────────────────────────┘
                          │
                          ▼
        .codegenie/context/repo-context.yaml   (envelope + Phase 1 + Phase 2)
        .codegenie/context/raw/                (per-probe blobs)
        .codegenie/cache/                      (Phase 0 layout — preserved)
        .codegenie/index/scip-index.scip       (NEW — long-lived index artifact)
        .codegenie/index/tree-sitter-cache/    (NEW — per-file parsed cache)
        .codegenie/index/bm25/                 (NEW — Tantivy index for D-layer external docs)
```

Three load-bearing observations from the diagram:

1. **The DaemonPool is the central performance optimization.** It is *new infrastructure*; Phase 1 had no equivalent. ADR-0007 (probe contract preserved) is honored because daemons live *below* the probe ABC — probes still implement `async def run()`; they just dispatch through the DaemonPool helper rather than spawning fresh subprocesses. The probe contract is untouched.
2. **The tier split is the cost-router.** Tier-0 probes (pure Python, no I/O, ≤ 10 ms) run on every gather. Tier-1 probes (daemon-pooled, 100ms-1s) run when their inputs change. Tier-2 probes (heavy subprocess, 5-30s) cache aggressively. Tier-3 probes (runtime trace) gate themselves on task class — they do not run on every gather.
3. **The `.codegenie/index/` directory is new.** It holds artifacts that are bigger than cache blobs but should not be regenerated on every cold worker boot. The SCIP index is the prototype: ~5 MB binary, regenerated incrementally, lives on disk across worker restarts.

## Components

### 1. DaemonPool (`codegenie/coordinator/daemons.py` — NEW)

- **Purpose:** Eliminate fork+exec+JVM/Python-startup costs for tools we invoke repeatedly. `scip-typescript`, `semgrep`, and `tree-sitter` all benefit. Without this, Phase 2 wall-clock budget is consumed by process startup, not by useful work.
- **Interface:**
  - `async def acquire(name: Literal["scip", "semgrep", "tree_sitter"]) -> DaemonHandle`
  - `DaemonHandle.send(payload: bytes) -> bytes` — send a request, get a framed response.
  - `DaemonHandle.release() -> None`
  - Errors: `DaemonStartupFailed`, `DaemonCrashed` (auto-restart with backoff), `DaemonProtocolError`.
- **Internal design:**
  - **`scip-typescript` daemon:** invoked as `scip-typescript --stdio` (the tool supports a JSON-RPC-like pipe mode in recent releases; if not, we wrap it with a tiny Node.js loop that calls the indexer's library API and emits SCIP bytes per request). One request = "index repo at this rooted path with this tsconfig"; one response = SCIP index bytes + diagnostics. The daemon caches its own parsed `node_modules` type-declaration tree across requests; that's where the 1.5–3 s startup comes from, and it's amortized over the worker lifetime.
  - **`semgrep` daemon:** invoked as `semgrep --x-language-server` or, failing that, `python -c "from semgrep import ...; while True: read_req(); run(); write_resp()"`. The win is pre-loading rule packs (~1.2 s) and the Python interpreter (~300 ms). Each request specifies a file list + rule-pack version.
  - **`tree-sitter` parsers:** loaded in-process via the `tree-sitter` Python bindings, one parser per language. No subprocess at all; the parsers are C extensions and are loaded once.
  - **Health and lifecycle:** each daemon's health is checked via a `ping` request every 30 s. A crashed daemon is restarted with exponential backoff; if backoff reaches 60 s, the corresponding probes degrade to fresh-subprocess mode and log `daemon.fallback`. The DaemonPool is owned by the Coordinator and reused across gathers within one worker process.
  - **Concurrency:** each daemon serializes its own requests (a single `asyncio.Lock`). For Phase 2 portfolio scale, one `scip-typescript` daemon per worker is sufficient — Layer B index requests are not the bottleneck; SCIP itself is single-threaded internally. If profiling shows daemon contention, the pool can spawn N daemons; the lock becomes a `Semaphore`.
- **Tradeoffs accepted:**
  - **Daemon lifecycle introduces failure modes Phase 0/1 didn't have.** A daemon crash mid-gather is recoverable (fallback to fresh subprocess + retry), but the audit log entries get noisier. Mitigation: structured `daemon.crashed`, `daemon.restarted`, `daemon.fallback` events with cardinality budget.
  - **Pre-warming on worker boot adds 4 s to Phase 14 worker startup.** Acceptable: workers boot rarely (autoscaling event, deploy event); gathers happen constantly.
  - **Daemons hold per-worker memory between gathers.** The `scip-typescript` daemon holds ~200 MB. This is the right trade — saving 1.5 s on every cold gather pays for 200 MB once.
  - **`scip-typescript --stdio` may not exist in the upstream release.** Fallback: shell wrapper that invokes the indexer's Node.js API as a long-lived script. Tested at integration time; if neither works the daemon falls back to fresh-process mode and we eat the startup cost. Surfaced as a degradation, not a failure.

### 2. SCIPIndexProbe — B1 (`codegenie/probes/scip_index.py` — NEW)

- **Purpose:** Build the SCIP index for TypeScript repos. The single largest source of Phase 2 wall-clock on cold gathers.
- **Interface:** standard probe ABC. `name = "scip_index"`, `layer = "B"`, `applies_to_languages = ["javascript", "typescript"]`, `applies_to_tasks = ["*"]`, `requires = ["language_detection", "node_build_system"]`, `timeout_seconds = 180`, `declared_inputs = ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.mjs", "**/*.cjs", "tsconfig.json", "tsconfig.*.json", "package.json", "pnpm-lock.yaml", "yarn.lock", "package-lock.json"]`.
- **Internal design:**
  - **Daemon-pooled invocation.** The probe acquires a `scip` daemon handle, sends the rooted path + tsconfig, receives SCIP bytes. On a 50k-LOC TS service: ~25 s on cold daemon (first request), ~12 s on warm daemon (subsequent requests, type-decl cache hit).
  - **Incremental indexing.** SCIP supports per-file re-indexing. The probe diffs the input file set against the previously-indexed file set (stored as `scip-manifest.json` next to the index), submits only the changed files to the daemon, and the daemon emits an incremental update. On a typical PR (5–50 files changed out of 50k LOC), incremental index is ~1.5 s. **This is the load-bearing perf win for ADR-0006's "incremental gather" property.**
  - **Cache key composition.** `(probe_name, probe_version, sub_schema_version, content_hash_of_ts_sources, tsconfig_hash, lockfile_hash, scip_typescript_version)`. The TS-source hash is computed from the PathIndex (Phase 1's PathIndex extends to expose `by_extension` slices). The `scip_typescript_version` field invalidates everyone when the indexer is upgraded — required correctness, not optional.
  - **Index artifact lives at `.codegenie/index/scip-index.scip`** — *not* under `cache/`. The `cache/` directory holds probe outputs (`ProbeOutput` slices); the SCIP index is a working artifact that the daemon updates in place. The probe's `ProbeOutput.schema_slice` references it by path + content hash; downstream consumers (Layer F probes in Phase 3+, the IndexHealthProbe, Stage 3 Planning) read the file directly.
- **Tradeoffs accepted:**
  - Incremental indexing requires the daemon to be present. On a cold worker boot, the first gather pays the ~25 s cost; from then on, gathers within the worker's lifetime hit incremental.
  - The `.codegenie/index/` directory is new on-disk state outside `cache/`. The `cache gc` subcommand (from Phase 0) must be extended to clean stale `.codegenie/index/scip-index.scip` files. Open question for the synthesizer: should this be in the cache or in its own namespace? My answer: separate namespace, because the SCIP index lifecycle differs from probe-output blob lifecycle.
  - **The probe ABC's `declared_inputs` is a glob list, not a content-hash receipt.** A pathological repo with 200k `.ts` files (vendored JS shipped as TS) would generate a huge content hash. Mitigation: same exclusion set Phase 1 introduced for SnapshotBuilder (`node_modules`, `dist`, `.next`, `.turbo`, `build`, `coverage`) applies.

### 3. IndexHealthProbe — B2 (`codegenie/probes/index_health.py` — NEW)

- **Purpose:** The single most important probe in the system per `production/design.md §2.3` and `localv2.md §5.2 B2`. Silent index staleness is the worst failure mode of the gather pipeline. This probe makes it loud. Performance constraint: **it must run on every gather**, including cache-hit-everything gathers, so its budget is ≤ 50 ms p95.
- **Interface:** standard probe ABC. `name = "index_health"`, `layer = "B"`, `applies_to_languages = ["*"]`, `applies_to_tasks = ["*"]`, `requires = ["scip_index", "syft_sbom", "grype_cves", "semgrep", "runtime_trace"]` (with optional-requires: probes that didn't run for this gather don't block; the health probe reports their absence as `not_run`). `timeout_seconds = 10`, `declared_inputs = []` — **it reads from other probe outputs, not files**.
- **Internal design:**
  - **No tool subprocess; no file parse.** It's pure-Python over already-materialized `ProbeOutput` dicts in memory. The Phase 0/1 coordinator already keeps the in-progress `ProbeOutput` map; this probe reads from it.
  - **What it computes per upstream probe:**
    - `last_indexed_commit` (from the upstream probe's output) vs `current_commit` (from RepoSnapshot.git_commit) → `commits_behind` count via `git rev-list --count`.
    - `last_indexed_at` (from upstream `ProbeOutput.metadata`) vs `now`.
    - For SCIP: declared `files_indexed` vs `files_in_repo` (from PathIndex `by_extension` counts) → `coverage_pct`.
    - For Syft/Grype: `image_digest_match` (the image digest the SBOM was generated against vs the digest the Dockerfile currently produces — derived from `DockerfileProbe` output and a deterministic build-config hash, **not** an actual rebuild).
    - For RuntimeTrace: `trace_image_digest_match`; `scenarios_run` vs `scenarios_configured`.
    - For Semgrep: `rule_pack_versions` vs the latest pinned version in the repo config.
  - **Per-upstream-probe confidence rollup:** the probe emits a sub-slice per upstream probe with `confidence ∈ {high, medium, low}` and an explicit `staleness_reason` list. The aggregated `confidence_summary` slice (one of the four Phase-8 hot views) is materialized here.
  - **Cache strategy: `cache_strategy = "none"`.** This is the only Phase 2 probe that explicitly does not cache. Reason: its inputs are other probes' outputs, which already cache; if upstream cache hits then `index_health` re-computes against the cached output deterministically and gets the same answer. The work is ~30 ms of dict-walking; not worth a cache layer of its own.
  - **Tail-latency budget enforcement:** the probe sets a hard internal 50 ms wall-clock limit via `asyncio.wait_for`. If it exceeds, it emits `confidence: low` and logs `index_health.budget_exceeded`. This is the load-bearing guarantee — on every gather, even if everything else degrades, the staleness report still arrives.
- **Tradeoffs accepted:**
  - **Image-digest match is computed without a rebuild.** I use a Dockerfile-derived deterministic build-config hash (parser output + base-image digest from the registry + COPY directives + RUN command hashes) as a proxy. A real rebuild would catch base-image-floating-tag drift, but a real rebuild costs 30–60 s and runs in `SyftSBOMProbe` already. Mitigation: when `SyftSBOMProbe` actually rebuilds (cache-miss path), the real image digest lands in its output; `IndexHealthProbe` cross-checks against it.
  - **The probe trusts upstream probe outputs to declare their own staleness facts honestly.** A buggy upstream probe that reports `last_indexed_commit: <stale>` truthfully looks like staleness; a buggy upstream probe that reports `last_indexed_commit: <current>` while indexing stale files looks like health. Mitigation: each upstream probe writes its `last_indexed_at` and `last_indexed_commit` *after* the index is on disk; the probe's audit record (Phase 0) commits the timestamps. The structural defense is the cache-key correctness (declared_inputs must capture all real inputs).

### 4. NodeReflectionProbe — B3 (`codegenie/probes/node_reflection.py` — NEW)

- **Purpose:** Surface dynamic-dispatch patterns SCIP can't resolve. Per `localv2.md §5.2 B3`.
- **Interface:** standard probe ABC. `name = "node_reflection"`, `layer = "B"`, `applies_to_languages = ["javascript", "typescript"]`, `requires = ["language_detection"]`, `declared_inputs = ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.mjs", "**/*.cjs"]`, `timeout_seconds = 30`.
- **Internal design:**
  - **`tree-sitter` queries via in-process bindings.** The DaemonPool exposes a `tree_sitter` interface; the probe runs ~12 pre-compiled queries (dynamic property access, eval, dynamic require, dynamic import, prototype manipulation, decorator presence, middleware chain shape, env-var-gated branches) over each file.
  - **Per-file content-hash caching.** Each file's parse result is keyed on `(content_blake3, query_pack_version)`. Stored under `.codegenie/index/tree-sitter-cache/` as one msgpack-packed file per source-file content hash. Cache hit rate at portfolio scale: ≥ 98% (source files change rarely; queries change with releases).
  - **Per-file work budget: ≤ 5 ms p95.** Tree-sitter parses TS at ~10k LOC/s on a modern CPU; query evaluation is bounded by the number of matches.
  - **Result aggregation streaming.** As each file completes, its findings are appended to an in-memory accumulator; no per-file allocation of the full file's AST is retained.
- **Tradeoffs accepted:**
  - Per-file cache means more inode pressure on the disk. Mitigation: msgpack files are ~1 KB each on average; 50k files = 50 MB. The `cache gc` job collapses files older than 30 days.
  - Tree-sitter queries are language-specific. Adding Java in v0.2 means new query files; the probe's query-pack is loaded by language ID, not hardcoded.

### 5. GeneratedCodeProbe — B4 (`codegenie/probes/generated_code.py` — NEW)

- **Purpose:** Identify generated code so the planner doesn't try to edit it. Per `localv2.md §5.2 B4`.
- **Interface:** standard probe ABC. `name = "generated_code"`, `layer = "B"`, `applies_to_languages = ["*"]`, `requires = ["language_detection"]`, `declared_inputs = ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.mjs", "**/*.cjs", "**/*.pb.ts", "**/*.pb.js", "schema.prisma", "src/generated/**", "src/**/__generated__/**", "src/**/*.graphql"]`, `timeout_seconds = 15`.
- **Internal design:**
  - **Header pattern match first.** A tiny fast-path: read the first 256 bytes of each file (via `mmap` or buffered read with `read(256)`) and match against a precompiled regex set for `// Generated by`, `# Generated by`, `/* DO NOT EDIT */`, etc. ~99% of generated files match here; cost is ~5 µs per file.
  - **Dependency-based detection second.** From the cached `parsed package.json` (`ParsedManifestMemo` from Phase 1): if `@graphql-codegen/cli`, `openapi-typescript`, `prisma`, `@prisma/client`, `protobuf` are declared, mark conventional output directories (`src/generated/`, `__generated__/`) as generated.
  - **No tree-sitter parsing needed** for the common case. Tree-sitter only invoked for files matching ambiguous patterns (a `.ts` file in `src/` that has `/* DO NOT EDIT */` but is also imported by source files — surfaced as `confidence: medium`).
  - **Cache key: declared-inputs content hash + header regex pack version + dependency manifest hash.**
- **Tradeoffs accepted:**
  - Header pattern matching can be evaded by deliberately-bad generators that emit no header. Mitigation: the dependency-based detection catches the conventional output dirs; the probe reports `confidence: medium` on files with no header but in a conventional dir.
  - Build outputs (`dist/`, `build/`) are detected by Phase 1's `NodeBuildSystemProbe` and surfaced there; this probe doesn't duplicate that work.

### 6. BuildGraphProbe — B5 (`codegenie/probes/build_graph.py` — NEW)

- **Purpose:** Module-dependency graph for monorepos. Per `localv2.md §5.2 B5`.
- **Interface:** standard probe ABC. `name = "build_graph"`, `layer = "B"`, `applies_to_languages = ["javascript", "typescript"]`, `requires = ["language_detection"]`, `declared_inputs = ["pnpm-workspace.yaml", "package.json", "packages/*/package.json", "apps/*/package.json", "libs/*/package.json", "lerna.json", "nx.json", "turbo.json"]`, `timeout_seconds = 30`. `applies()` returns `False` for non-monorepo repos (gated by Phase 1's `LanguageDetectionProbe.monorepo` flag).
- **Internal design:**
  - **`networkx` in-process graph construction.** No subprocess. Read each workspace package's `package.json` (via Phase 1's `ParsedManifestMemo`-aware helper), construct a `networkx.DiGraph` with package names as nodes and `dependencies + devDependencies` edges. ~10 ms for a 100-package monorepo.
  - **No `pnpm list -r` / `nx graph --file=...` subprocess.** Both are slow (1–5 s) and require their respective tools installed at the right version. We compute the graph from the manifests alone; the result matches `pnpm list`'s output within the workspace boundary.
  - **Optional cross-check.** When `nx graph --file=` is available *and* the gather is running in `--paranoid` mode (off by default), cross-check our graph against `nx`'s output and emit a `build_graph.crosscheck_disagree` warning if they differ. Off by default for perf; on for golden-file regeneration.
  - **Cache key:** content hash of all workspace `package.json` files + `pnpm-workspace.yaml` + the marker files.
  - **`networkx` is a pure-Python dep.** Phase 2 adds it. Bench at integration: for 100-package graphs, `networkx` is fast; for 10k-package graphs (theoretical), we'd need to swap to `rustworkx` (drop-in API). Out of scope for Phase 2 unless we see a real 10k-package repo.
- **Tradeoffs accepted:**
  - Graph is *declared*, not *resolved* (we don't honor lockfile version pinning). For Phase 2 the consumer is Stage 3 Planning's blast-radius computation, which cares about which packages depend on which, not about which version. If a future consumer needs resolved-version graphs, that's a Phase 12 task.

### 7. SyftSBOMProbe — C2 (`codegenie/probes/syft_sbom.py` — extends Phase 1's DockerfileProbe interfacing)

- **Purpose:** Generate the SBOM for the current container image. Heavy: 3–8 s of `syft` subprocess + a `docker build` if no built image exists.
- **Interface:** standard probe ABC. `name = "syft_sbom"`, `layer = "C"`, `applies_to_languages = ["*"]`, `requires = ["dockerfile"]` (Phase 1 ships DockerfileProbe under the C-layer; Phase 2 picks up here), `declared_inputs = ["Dockerfile", "Dockerfile.*", ".dockerignore", "package.json", "pnpm-lock.yaml", "yarn.lock", "package-lock.json"]`, `timeout_seconds = 300`.
- **Internal design:**
  - **Cache key includes the deterministic build-config hash.** `(probe_name, probe_version, sub_schema, dockerfile_hash, dockerignore_hash, lockfile_hash, base_image_digest_at_registry, syft_version)`. The base-image digest is resolved by a single `skopeo inspect` call against the registry (~200 ms, cached for 1 hour in an in-process LRU since base-image digests rarely change within a portfolio scan).
  - **Build only if cache miss AND no recent built-image artifact.** Phase 1's `DockerfileProbe` produces a parsed Dockerfile; the SBOM probe checks `.codegenie/index/built-images/<dockerfile_hash>.image-digest` for a recent build. If present and < 24h old, syft scans that image. If absent, the probe builds: `docker build --quiet -t codegenie/<repo_hash>:<gather_id> .` (~30–60 s on a typical Node image).
  - **`syft <image-digest> -o json` invocation.** ~3 s on a 500 MB image. The output is the SBOM blob; the probe parses it for the counts/classifications and writes the full blob under `.codegenie/context/raw/syft-sbom.json`.
  - **`buildx` cache mounted from `.codegenie/index/buildx-cache/`.** Phase 14's worker model preserves the buildx cache across worker boots; cold gathers of an unchanged Dockerfile hit the buildx cache and rebuild in ~5 s.
- **Tradeoffs accepted:**
  - `docker build` is the dominant cost. Mitigation: the probe is Tier-2 and only fires on cache miss; portfolio-steady-state cache hit rate ≥ 95% (Dockerfiles change rarely).
  - The registry-inspection call introduces a network dep. Mitigation: 1-hour LRU; offline mode (`--no-network`) falls back to the cached digest.

### 8. GrypeCVEProbe — C3 (`codegenie/probes/grype_cve.py` — NEW)

- **Purpose:** CVE scan against the SBOM.
- **Interface:** standard probe ABC. `name = "grype_cve"`, `layer = "C"`, `requires = ["syft_sbom"]`, `declared_inputs = []` (consumes the SBOM output of the prior probe), `timeout_seconds = 120`.
- **Internal design:**
  - **No subprocess fork for grype's vuln DB load on every gather.** `grype` reads its vulnerability DB at startup (~600 ms for the JSON DB). For repeated gathers on the same worker, we keep `grype --update db` synced once per worker lifetime (the DaemonPool isn't appropriate here — grype doesn't have a pipe mode — but we keep the DB path stable).
  - **Invocation: `grype sbom:<path-to-sbom-json> -o json --quiet`.** ~2 s on a typical SBOM.
  - **Optional `trivy` cross-check is OFF in Phase 2.** `localv2.md §5.3 C3` mentions trivy as a cross-validator; Phase 2 ships grype-only by default to hit perf budget. Trivy cross-check is opt-in via `--paranoid` flag; for default workloads, the ~2× wall-clock cost isn't justified by the perf-vs-truth tradeoff.
  - **Cache key:** `(probe_name, probe_version, sbom_content_hash, grype_db_version)`. The `grype_db_version` field invalidates everyone when the DB updates (daily at portfolio scale).
- **Tradeoffs accepted:**
  - **CVE-feed-triggered gather:** a new CVE published doesn't trigger a re-scan of every repo. Instead, the Continuous Gather Dispatcher (Phase 14) checks the CVE's affected packages against the cached SBOMs and only invalidates `grype_cve` cache for repos whose SBOM mentions the package. This is what makes the "10-minute portfolio reassessment" target in Phase 14 feasible.

### 9. GitleaksProbe — F-ish (`codegenie/probes/gitleaks.py` — NEW)

- **Purpose:** Secret scanning. Per Phase 2 roadmap scope.
- **Interface:** standard probe ABC. `name = "gitleaks"`, `layer = "F"` (security probe; classified under what `localv2.md` calls "Layer F" in the broader sense — exact layer label is flexible per ADR-0007's "extension by addition" semantics, the probe doesn't care, the sub-schema is its own slice), `applies_to_languages = ["*"]`, `applies_to_tasks = ["*"]`, `requires = []`, `declared_inputs = ["**/*"]` filtered by the SnapshotBuilder's exclusion list, `timeout_seconds = 60`.
- **Internal design:**
  - **Two invocation modes.**
    - Default: `gitleaks detect --no-banner --redact --no-git -f json -s <path>` — scans the working tree.
    - PR-trigger mode (when invoked from Phase 14's PR-opened webhook): `gitleaks detect --no-banner --redact --no-git -f json --baseline-path <baseline> -s <path>` — uses the prior gather's findings as a baseline and reports only new findings. ~10× faster on incremental.
  - **No `--no-git` toggle for `git-based` mode:** the working-tree scan is sufficient for the gather's purpose; the commit-history scan is opt-in and bounded.
  - **Subprocess streaming.** Read the JSON output line-by-line via `asyncio.subprocess.PIPE` rather than buffer-then-parse. Gitleaks emits one JSON object per finding; we stream-aggregate.
  - **Output sanitization is structural, not regex.** The probe records `(file, line, rule_id, fingerprint)` per finding. **It does not record the matched secret value.** The `gitleaks --redact` flag enforces this on the tool's side; the probe's sub-schema rejects any field shape that could contain raw secret bytes. Phase 0's `OutputSanitizer` is the belt-and-suspenders second pass.
- **Tradeoffs accepted:**
  - Gitleaks' subprocess startup is ~200 ms; daemon-pooling doesn't apply (gitleaks is a Go binary, no pipe mode worth pursuing). Acceptable: the probe is Tier-2 and caches aggressively.

### 10. SemgrepProbe — G1 (`codegenie/probes/semgrep.py` — NEW)

- **Purpose:** Static analysis findings. The expensive Layer G probe.
- **Interface:** standard probe ABC. `name = "semgrep"`, `layer = "G"`, `requires = ["language_detection"]`, `declared_inputs = ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.mjs", "**/*.cjs", "Dockerfile", "Dockerfile.*", ".codegenie/semgrep-rules/**/*.yaml"]`, `timeout_seconds = 240`.
- **Internal design:**
  - **DaemonPool-backed.** Per the DaemonPool description, semgrep daemon pre-loads rule packs once per worker. Per-gather invocation: send file list + rule-pack version; receive findings JSON. ~3 s on a 50k-LOC Node service with the `p/nodejs` + `p/dockerfile` + `p/secrets` packs (vs ~8 s cold-start including Python interpreter).
  - **Per-file findings cache.** A file's findings depend on `(file_content_hash, rule_pack_version)`. Stored as `(file_content_hash, rule_pack_version_hash) → findings_blob` in a content-addressed cache under `.codegenie/cache/semgrep/`. On incremental gather (5 files changed), we re-run semgrep over those 5 files only and union with the cached findings of the rest.
  - **Targeted rule packs.** Default: `p/nodejs`, `p/dockerfile`, `p/secrets`. Phase 2 adds `p/owasp-top-ten` and `p/cwe-top-25` because the roadmap mentions them; these are gated by `applies_to_tasks` so they fire only when the planner declares a task that needs them. Vuln-remediation Phase 3+ will read these; Phase 2's distroless lookahead doesn't need them.
  - **Custom rules under `~/.codegenie/semgrep-rules/`** (org-level) and `.codegenie/semgrep-rules/` (repo-level). Their content hashes participate in the cache key.
- **Tradeoffs accepted:**
  - The per-file-findings cache assumes findings are *per-file*. Semgrep's cross-file taint mode (`--config p/taint-mode`) doesn't fit this model. Phase 2 ships per-file mode; taint mode is opt-in via `--paranoid` and bypasses the per-file cache.
  - DaemonPool fallback to fresh-subprocess mode loses the rule-pack pre-load. Accept ~1.2 s slower on those gathers; surfaced in audit.

### 11. ConventionsCatalog + SkillsLoader — D5/D2 (`codegenie/probes/conventions.py`, `codegenie/probes/skills_loader.py` — NEW)

- **Purpose:** Per `localv2.md §5.4 D2` and `D5`. Conventions are org-curated YAML rules; Skills are YAML-frontmatter markdown files in `.codegenie/skills/` and `~/.codegenie/skills/` and `~/.codegenie/skills-org/`.
- **Interface:** standard probe ABC. Both probes are Tier-0 (pure-Python YAML reads).
  - `conventions`: `declared_inputs = ["~/.codegenie/conventions/**/*.yaml", ".codegenie/conventions/**/*.yaml"]`, `timeout_seconds = 10`.
  - `skills_loader`: `declared_inputs = ["~/.codegenie/skills/**/SKILL.md", "~/.codegenie/skills-org/**/SKILL.md", ".codegenie/skills/**/SKILL.md"]`, `timeout_seconds = 10`.
- **Internal design:**
  - **Skills loader: frontmatter-only parse.** Skill bodies are not loaded. `frontmatter` library (or a tiny hand-rolled YAML-frontmatter splitter — 30 lines, no new dep). Each skill emits `{name, description, applies_to, requires_evidence, path}`; the body content is referenced by path only. This is `production/design.md §"Progressive disclosure"` made operational: the Planner reads bodies on demand via MCP.
  - **Conventions: precompiled rule cache.** Rules with `detect.type: dockerfile_pattern` compile their regex once at module-load time. Rules with `detect.type: file_glob` are pathspec-compiled. Per-gather match time: ~1 ms for ~50 rules.
  - **Catalog version in cache key.** Each conventions file declares a `version: int`; the version participates in the cache key. Bumping the version invalidates downstream consumers that read the conventions slice.
- **Tradeoffs accepted:**
  - Symlink resolution at `~/.codegenie/` walks the home directory. Mitigation: `O_NOFOLLOW` (per Phase 1's pattern); skip on stat error.
  - Skill bodies aren't validated at gather time. A malformed skill body manifests as a Planner-time error in Phase 3+; acceptable since the gather doesn't consume bodies.

### 12. ExceptionRegistry, ADRProbe, RepoConfigProbe, RepoNotesProbe — D3/D6/D1/D7

- **Purpose:** Per `localv2.md §5.4`. These are *all* Tier-0 (pure-Python file reads).
- **Internal design — collapsed because they share shape:**
  - All read small YAML/markdown files. None invoke a tool.
  - Per-probe cost budget: ≤ 10 ms p95.
  - **`RepoNotesProbe`** extracts markdown headings only (no body content). Same `production/design.md §"Progressive disclosure"` rule.
  - **`ExceptionRegistry`** loads `.codegenie/exceptions.yaml` and a optional org-wide path; date-parses `expires`; emits structured entries.
  - **`ADRProbe`** walks `docs/adr/` and friends; extracts ADR ID + status + title only.
  - **`RepoConfigProbe`** parses frontmatter from `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`; emits metadata only.
- **Tradeoffs accepted:**
  - These probes individually save very little wall-clock. Bunched together, they make the `organizational` slice cheap enough to update on every gather, which is what ADR-0006's continuous-gather model demands.

### 13. RuntimeTraceProbe — C4 (`codegenie/probes/runtime_trace.py` — NEW, OPT-IN)

- **Purpose:** Per `localv2.md §5.3 C4`. **The single most valuable probe for distroless confidence**, and **the single most expensive Phase 2 probe.** 80 s wall-clock when run.
- **Interface:** standard probe ABC. `name = "runtime_trace"`, `layer = "C"`, `applies_to_tasks = ["distroless_migration", "container_hardening"]`, `applies_to_languages = ["javascript", "typescript"]`, `requires = ["syft_sbom"]`, `declared_inputs = ["Dockerfile", "Dockerfile.*", "scripts/smoke.sh", "tests/smoke/**", "package.json", "pnpm-lock.yaml", "yarn.lock", "package-lock.json"]`, `timeout_seconds = 600`.
- **Internal design:**
  - **`applies_to_tasks` gating.** Phase 2 ships this probe but it does NOT run on every gather. The Phase 0/1 registry filter on `applies_to_tasks` ensures it fires only when the gather is invoked with `--task distroless_migration` (or another task that needs it). For the Phase 14 continuous-gather model: cron-triggered scans for watched repos with distroless tasks active will hit it; push-triggered scans for general repos will not.
  - **Scenario parallelization where independent.** Scenarios 1 (startup), 3 (healthcheck poll), 5 (error path) can run in independent container instances in parallel; scenarios 2 (smoke) and 4 (shutdown) are sequential. Three-way parallelism cuts wall-clock from ~80 s to ~35 s on multi-core workers.
  - **`strace -f -e trace=openat,execve,connect,bind,mmap` on Linux**; degraded to `dtruss` (with sudo) or skip-with-warning on macOS. Phase 14 production is Linux; macOS is dev-only.
  - **eBPF augmentation is OFF by default.** `bpftrace` requires kernel features that vary across hosts; opt-in via `--use-ebpf`.
  - **Cache key:** Dockerfile + lockfile content hash + scenario script hashes + base-image digest. Image-digest mismatch is the dominant invalidator.
  - **Trace output streaming.** Each scenario's strace output is read line-by-line via `asyncio.subprocess.PIPE`; we aggregate into the unioned `shared_libs_loaded`, `files_read_at_runtime`, `network_endpoints_touched` slices without buffering the full strace text in memory.
- **Tradeoffs accepted:**
  - **macOS degradation is intentional.** macOS dev workstations get `trace_coverage_confidence: low` and a warning; Phase 14 production runs Linux. Not optimizing for macOS UX is on the deprioritized list above.
  - The probe runs containers. That's a security surface; the security-first design will say more. Performance lens: the cost is real; the gating via `applies_to_tasks` is the perf-defining choice.

### 14. ExternalDocsIndexProbe — D9 — Tantivy BM25 (`codegenie/probes/external_docs_index.py` — NEW)

- **Purpose:** BM25 index over external docs per `localv2.md §5.4 D9`. Performance constraint: the Planner queries this on-demand at Stage 3; index quality must be high enough that the Planner doesn't re-scan docs, and build cost must be low enough that re-indexing is cheap.
- **Interface:** standard probe ABC. `name = "external_docs_index"`, `layer = "D"`, `requires = ["external_docs", "repo_notes"]`, `declared_inputs = [".codegenie/notes/**/*.md", ".codegenie/context/raw/external-docs/**/*.md"]`, `timeout_seconds = 30`.
- **Internal design:**
  - **`tantivy` Python bindings.** Builds an inverted index keyed on (title, headings, first paragraph, tags) per `localv2.md §5.4 D9` spec. ~50 ms per 100 docs.
  - **Index lives at `.codegenie/index/bm25/`** — same lifecycle namespace as the SCIP index. Per-doc content hash determines whether the doc is re-indexed.
  - **Querying is NOT this probe's job.** The Planner queries via MCP. This probe only builds; query latency at Stage 3 is ≤ 5 ms per query, which makes `production/design.md §"Progressive disclosure"` operationally cheap.
  - **`ripgrep` fallback** if `tantivy` is not installed: a small wrapper that exposes the same query interface but is slower (~50 ms per query). Acceptable for local-dev.
- **Tradeoffs accepted:**
  - Tantivy adds a Rust-backed C-extension dep. The Phase 1 synthesizer explicitly rejected `ruamel.yaml` and `pyjson5` on the same grounds. This case is different: tantivy is the only viable BM25 indexer for our scale, and the alternative (no D9) loses a `production/design.md §"Progressive disclosure"` capability. Open question for the synthesizer.

### 15. TestCoverageMappingProbe — G3 (`codegenie/probes/test_coverage_map.py` — NEW)

- **Purpose:** Per `localv2.md §5.6 G3`. Maps tests to source via lcov + SCIP symbol resolution.
- **Interface:** standard probe ABC. `name = "test_coverage_map"`, `layer = "G"`, `requires = ["scip_index", "test_inventory"]`, `declared_inputs = ["coverage/lcov.info", "coverage/coverage-final.json"]`, `timeout_seconds = 30`.
- **Internal design:**
  - **`lcov.info` parser is the Phase-1 line-scanner extended** (the synthesizer noted ~40 lines of stdlib is enough). Phase 2 lifts the same parser into a shared module.
  - **SCIP symbol resolution via the SCIP index file** (no daemon re-call). The probe reads `.codegenie/index/scip-index.scip` via the `scip` Python bindings (or `protobuf` directly — the format is protobuf). Per-symbol lookup: ~10 µs.
  - **Cache key:** `lcov_content_hash + scip_index_content_hash`.
- **Tradeoffs accepted:**
  - Requires SCIP to have run. On non-TS repos, this probe doesn't apply (correctly filtered out by `requires`).

### 16. Cache layer extension (`codegenie/cache/store.py` extensions)

- **Purpose:** Phase 2 introduces new cache-key components (rule-pack versions, grype DB version, scip-typescript version, daemon protocol versions). The cache key derivation extends; nothing else changes.
- **Interface:** Phase 0/1 API preserved.
- **Internal design:**
  - **Cache key components for Phase 2 probes** include tool version (e.g., `semgrep --version` parsed at worker boot; `grype db status` parsed daily; `scip-typescript --version` parsed at daemon spawn). Tool versions are baked into the cache key so a tool upgrade invalidates all of its probe's entries.
  - **Per-file-findings sub-caches** (semgrep, tree-sitter) live at `.codegenie/cache/<probe>/by-file/` with the file's content hash as the key. The per-gather `ProbeOutput` cache (at `.codegenie/cache/blobs/`) and the per-file sub-cache are independent layers.
  - **No mmap.** Phase 0 deferred it; Phase 1's synthesizer kept the deferral. Phase 2 inherits.
- **Tradeoffs accepted:**
  - Per-file sub-caches add inode pressure. `cache gc` extended to GC by access time per sub-cache.

### 17. Per-probe sub-schemas — Phase 2 additions

- **Purpose:** Continue Phase 1's per-probe sub-schema policy: strictness at the per-probe root, `probes.*` remains `additionalProperties: true` per Phase 0 §2.9.
- **Internal design:** New schema files at `src/codegenie/schema/probes/`:
  - `semantic_index.schema.json` (SCIP)
  - `index_health.schema.json`
  - `reflection.schema.json`
  - `generated_code.schema.json`
  - `build_graph.schema.json`
  - `sbom.schema.json`
  - `cve_scan.schema.json`
  - `secret_scan.schema.json`
  - `semgrep_findings.schema.json`
  - `runtime_trace.schema.json`
  - `test_coverage_map.schema.json`
  - `external_docs_index.schema.json`
  - Extensions to `organizational.schema.json` for the D-probe slices.
- Each declares `additionalProperties: false` at its root; warnings constrained to Phase 1's pattern (`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`).
- **Tradeoffs accepted:** ~12 new schema files. Schema-evolution discipline maintained: adding a field is a code + schema PR.

## Data flow

Representative incremental-gather run on Phase 14's worker (one TS source file changed since last gather):

1. **Trigger (Phase 14 webhook):** push event for `repo-9876` fires. Continuous Gather Dispatcher routes to a worker.
2. **Worker is already up; DaemonPool is pre-warmed.** `scip-typescript`, `semgrep` daemons live; `tree-sitter` parsers loaded in-process. ~0 ms overhead.
3. **Coordinator startup (~30 ms):** Click parses args; Pydantic, jsonschema imported lazily (already cached in worker memory).
4. **SnapshotBuilder run (Phase 1, ~150 ms warm-cache walk):** one `os.scandir` over the repo. PathIndex fingerprint computed. ~30 MB resident.
5. **Prelude (LanguageDetectionProbe, ~8 ms):** LRU hit.
6. **Wave 2: Phase 1 Layer A probes (~50 ms total).** `node_build_system`, `node_manifest`, `ci`, `deployment`, `test_inventory`. Mostly cache hits; `node_manifest` and `node_build_system` miss (the changed TS file touches `package.json`'s `dependencies`? No — pure source change. They cache-hit).
7. **Wave 3: Layer B probes dispatch in parallel.**
   - **`scip_index` (`~1.4 s`):** content-hash diff against `.codegenie/index/scip-manifest.json` reveals one TS file changed. Daemon receives the incremental request, re-indexes that file, emits a delta SCIP block. SCIP-index artifact updated in place via `os.replace`.
   - **`node_reflection` (`~80 ms`):** per-file cache hit for all unchanged files (`tree-sitter-cache/`); re-parse + query the one changed file (~5 ms).
   - **`generated_code` (~30 ms):** header-pattern cache hit; only the changed file's header re-checked.
   - **`build_graph`:** non-monorepo, `applies()` returns false. Skipped.
8. **Wave 4: Layer C heavy probes (`~150 ms`):** `dockerfile` (Phase 1) cache-hit; `syft_sbom` cache-hit (Dockerfile + lockfile unchanged → build-config hash unchanged); `grype_cve` cache-hit; `runtime_trace` not applicable (task class is `vuln_remediation`, not `distroless_migration`).
9. **Wave 5: Layer G probes (`~120 ms`):**
   - **`semgrep` (~80 ms):** per-file cache hits for all unchanged files; re-scan only the one changed file via the daemon (~30 ms with rule packs pre-loaded).
   - **`gitleaks` (~40 ms):** PR-trigger mode with baseline; only the diff is scanned.
   - **`test_coverage_map`:** depends on SCIP index + lcov; both changed (SCIP delta), so re-resolve symbols (~20 ms).
10. **Wave 6: Layer D probes (`~30 ms`):** `conventions`, `skills_loader`, `adrs`, `repo_notes`, `repo_config` — all Tier-0 reads, mostly cache-hit.
11. **`index_health` runs last (`~25 ms`):** reads all upstream `ProbeOutput`s in memory; computes per-probe staleness and the aggregated `confidence_summary` slice. No subprocess.
12. **Stream-merge + sub-schema validation (`~40 ms`):** Phase 0/1 pipeline; per-probe sub-schemas check shape.
13. **Atomic YAML write (`~10 ms`).**
14. **Total wall-clock: ~2 s p50.** Under the 3 s portfolio-steady-state target.

For the pure no-change incremental gather (nothing relevant changed), everything in step 5–10 cache-hits; step 11 still runs (`index_health` is the regression gate); total ~250 ms.

For the cold first-gather on a fresh worker, the daemons cold-start (~3 s for SCIP, ~1.2 s for semgrep) but subsequent gathers in the worker amortize that cost over hundreds of gathers.

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| `scip-typescript` daemon crashes mid-gather | DaemonHandle protocol error | Restart daemon with exponential backoff; current probe falls back to fresh-subprocess invocation; emit `daemon.crashed.scip` audit event |
| Daemon protocol mismatch (worker upgraded SCIP but daemon spawned with old version) | Version handshake in DaemonHandle.acquire() | Daemon respawned; first request takes the cold-start cost; subsequent requests warm |
| `scip-typescript --stdio` mode doesn't exist in installed version | Daemon spawn checks for support flag | Fall back to per-gather fresh subprocess; emit `daemon.unsupported.scip`; perf budget breached but correctness preserved |
| SCIP incremental indexing produces a corrupted delta | SCIP index file fails to load on next read | Fall back to full re-index (slow path); emit `scip.incremental_failed`; cache entry for `scip_index` invalidated |
| `IndexHealthProbe` 50 ms budget breached | `asyncio.wait_for(50ms)` | Emit `confidence: low` for the per-probe sub-slice that wasn't computed; gather continues; staleness is *not* silent (this is the whole point) |
| `grype` DB out-of-date when CVE-feed trigger fires | DB version hash mismatch with feed-event payload | Background `grype --update db` fires; gather continues with previous DB; emit `grype.db.stale` |
| `docker build` fails (Dockerfile syntax error, base-image pull failure) | Phase 0 subprocess exit code | `syft_sbom` returns `confidence: low`; dependent `grype_cve` and `runtime_trace` mark themselves not-applicable due to upstream failure; `index_health` reports the chain |
| `semgrep` daemon hangs on a pathological file (regex catastrophic backtracking in custom rule) | Per-probe `timeout_seconds = 240` | Daemon process killed; daemon respawned; probe records `confidence: low`; the offending custom rule is flagged in the audit (we don't ban the rule — that's a human's call) |
| `gitleaks` finds a secret in a generated file (false positive on a test fixture) | Always — both true and false positives report | Sub-schema declares `finding.suppressed_by: ["allowlist_path", ...]`; org-level allowlist YAML at `.codegenie/gitleaks-allowlist.yaml`; same `ConventionsCatalog` shape |
| Tree-sitter parser pack version drift between worker and on-disk cache | Cache key includes pack version | Cache miss → re-parse all files; expensive but correct |
| `tantivy` index corruption (worker SIGKILL mid-build) | Index header check on open | Rebuild from scratch (~200 ms for ~100 docs); emit `bm25.rebuilt` |
| Disk full on `.codegenie/index/` | I/O error on artifact write | Probe records `confidence: low`; the file isn't written; downstream probes detect the missing file via `index_health` |
| `RuntimeTraceProbe` container fails to start (image build broken upstream) | Docker exit code | All scenarios marked failed; `trace_coverage_confidence: low`; gather continues; planner sees the broken trace and routes appropriately |
| Network unavailable when `skopeo inspect` runs against the registry | Connection error | LRU returns last-known digest; emit `registry.offline`; SBOM may build against a stale base — surfaced in `index_health` |

The pattern from Phase 1 holds: explicit confidence per upstream probe, no silent degradation, audit events for every degradation path. `IndexHealthProbe` is the regression gate that surfaces silent staleness across all of these.

## Resource & cost profile

- **Tokens per run:** 0. ADR-0005 invariant; `fence` CI job extended.
- **Wall-clock per `codegenie gather` (Phase 2 contribution, Linux Phase-14 worker):**
  - Cold first-gather on a 50k-LOC TS service, daemons cold-starting: p50 ~75 s, p95 ~95 s. SCIP indexing + first `docker build` + `syft` dominate.
  - Cold first-gather with daemons pre-warmed (worker boot cost amortized): p50 ~55 s, p95 ~70 s.
  - Warm gather (TS source change, no Dockerfile change): p50 ~3.5 s, p95 ~6 s. SCIP incremental + per-file semgrep cache + IndexHealth dominate.
  - Warm gather (Dockerfile change, no source change): p50 ~5 s, p95 ~8 s. `syft_sbom` rebuild dominates.
  - Incremental gather (no semantically-relevant change): p50 ~250 ms, p95 ~400 ms. SnapshotBuilder + IndexHealth dominate; everything else cache-hits.
  - `RuntimeTraceProbe` when invoked: ~35 s with 3-way parallelism (single scenario timing is ~25 s each).
- **Memory per worker:**
  - Idle (post-warm, between gathers): ~250 MB (DaemonPool: ~200 MB for SCIP, ~30 MB for semgrep; ~20 MB for the Python coordinator).
  - Peak during cold gather: ~600 MB (lockfile dicts + SCIP delta buffer + Docker daemon-side memory).
  - Peak during incremental gather: ~310 MB.
- **CPU per run:**
  - Cold: ~40 CPU-seconds (SCIP indexing + Docker build dominate).
  - Warm: ~2 CPU-seconds.
  - Incremental: ~0.4 CPU-seconds.
- **Storage growth:**
  - `.codegenie/cache/`: ~50 KB per gather (Phase 0 layout).
  - `.codegenie/cache/<probe>/by-file/`: ~1–5 MB per gather growth on a 50k-LOC repo (semgrep per-file findings + tree-sitter per-file parses).
  - `.codegenie/index/scip-index.scip`: ~5 MB per repo, rewritten in place.
  - `.codegenie/index/tree-sitter-cache/`: ~50 MB per repo; GC'd weekly.
  - `.codegenie/index/bm25/`: ~1 MB per ~100 docs.
- **Hot vs cold cost ratio:** ~150–200× (cold 75s vs incremental 0.25s). The Phase 1 ratio was ~40×; Phase 2 stretches it because the cold ceiling rises with `scip-typescript` and `docker build`, but the incremental floor stays nearly flat thanks to per-probe caching + DaemonPool + IndexHealth's design.
- **Per-probe peak RSS:**
  - SCIP daemon: ~200 MB (lives across gathers).
  - semgrep daemon: ~30 MB.
  - Per-gather Layer-B probes (in-process tree-sitter, networkx): ~40 MB.
  - syft + grype subprocesses: ~100 MB each (their own).
  - runtime trace (when invoked): ~50 MB Python + container memory separate.
- **External-dep additions (Python):** `networkx`, `tantivy` (Python bindings), `tree-sitter` Python bindings + per-language grammars, `python-frontmatter` (or hand-rolled, deferred to land-time per the same Phase-1 yarn-parser pattern). External-dep additions (system): `scip-typescript`, `semgrep`, `syft`, `grype`, `gitleaks`, `strace` (Linux only), `tree-sitter` CLI (for grammar updates only).

## Test plan

The Phase 1 test pyramid extends here. Adversarial fixtures stay CI-gating; benchmark tests gate cache + daemon + coordinator changes.

- **`tests/bench/test_warm_path_phase2.py`** — gather a fixture repo twice (cold then warm). Asserts:
  - Cold-with-pre-warmed-daemons p95 ≤ 70 s.
  - Warm p95 ≤ 6 s.
  - Incremental (one TS file changed) p95 ≤ 400 ms.
  - Per-probe cache hit rate on incremental: ≥ 88% across all Phase 2 probes.
  - CI-blocking on PRs touching `src/codegenie/probes/`, `src/codegenie/coordinator/daemons.py`, `src/codegenie/cache/`.
- **`tests/bench/test_daemon_warmup.py`** — boot a Coordinator; measure DaemonPool pre-warm time. Asserts ≤ 4 s p95.
- **`tests/bench/test_index_health_budget.py`** — `IndexHealthProbe.run()` against a populated `ProbeOutput` map. Asserts ≤ 50 ms p99 across 1000 iterations.
- **`tests/bench/test_scip_incremental.py`** — index a fixture; change one TS file; re-index. Asserts incremental delta ≤ 1.5 s.
- **`tests/unit/probes/test_index_health.py`** — IndexHealthProbe correctness:
  - Stale SCIP index (deliberately-old `last_indexed_commit`) produces `confidence: low` for SCIP slice.
  - Image digest mismatch produces `confidence: low` for SBOM.
  - All-fresh state produces `confidence: high`.
  - Missing upstream probe (e.g., SCIP not applicable on Go repo) produces `not_run` not `error`.
  - **This is the roadmap exit criterion test: a deliberately-seeded staleness fixture must be surfaced.**
- **`tests/unit/probes/test_scip_index.py`** — daemon-mocked unit tests; cache-key stability; incremental delta correctness.
- **`tests/unit/probes/test_node_reflection.py`** — query-pack correctness per pattern (eval, dynamic require, decorators, env-var-gated branches); per-file cache hit on unchanged content.
- **`tests/unit/probes/test_generated_code.py`** — header-regex fast path; dependency-based detection; ambiguous-case `confidence: medium`.
- **`tests/unit/probes/test_build_graph.py`** — `networkx` graph construction from synthetic monorepo manifests; cycle detection; cross-check against pnpm output (fixture-pinned).
- **`tests/unit/probes/test_syft_sbom.py`** — registry-inspect LRU; build-config hash determinism; cache hit on unchanged Dockerfile.
- **`tests/unit/probes/test_grype_cve.py`** — DB version invalidation; CVE-feed-trigger selective invalidation (the SBOM-affected-package check).
- **`tests/unit/probes/test_gitleaks.py`** — finding shape; secret value never appears in output; baseline diff mode; `--redact` enforced.
- **`tests/unit/probes/test_semgrep.py`** — daemon-mocked; per-file findings cache; rule-pack version cache key.
- **`tests/unit/probes/test_conventions_catalog.py`** — rule precompilation; catalog version cache participation.
- **`tests/unit/probes/test_skills_loader.py`** — frontmatter-only parse; body never loaded; manifest schema correctness.
- **`tests/unit/coordinator/test_daemon_pool.py`** — daemon lifecycle (acquire, release, crash, restart, fallback); concurrent acquisition; per-daemon lock correctness.
- **`tests/adv/test_runtime_trace_container_escape.py`** — runtime trace runs untrusted container; verify no host-FS access escapes the sandbox container; (security-first lens owns this fixture).
- **`tests/adv/test_semgrep_catastrophic_backtracking.py`** — custom rule with pathological regex; assert daemon timeout fires; probe records `confidence: low`.
- **`tests/adv/test_yaml_bomb_in_conventions.py`** — billion-laughs in a conventions YAML; assert Phase 1's `safe_yaml` caps fire.
- **`tests/adv/test_lcov_huge.py`** — 1 GB lcov; parser size cap fires.
- **`tests/adv/test_scip_index_corruption.py`** — corrupt SCIP file; daemon detects on load; full re-index fallback fires.
- **`tests/integration/test_phase2_end_to_end.py`** — full gather on `tests/fixtures/node_typescript_with_b_through_g/`; every Phase 2 slice populated; envelope validates.
- **`tests/integration/test_cache_hit_phase2.py`** — gather twice; second run all Phase 2 probes cache-hit; SCIP daemon doesn't receive incremental request.
- **`tests/integration/test_incremental_scip.py`** — gather; change one `.ts` file; gather again; assert SCIP incremental delta (not full re-index) was used; cache hit for all other Phase 2 probes.
- **`tests/golden/`** — Phase 2 fills in golden files per `localv2.md §"Testing"`. Each probe has a fixture with an expected output. Updating a golden file is a deliberate PR step (`make update-goldens`).
- **`tests/integration/test_index_health_staleness_seeded.py`** — **the roadmap's literal exit criterion.** Deliberately-seeded staleness fixture (SCIP commit drifted by 5; image digest mismatched). Assert `IndexHealthProbe` surfaces both; gather exits 0 with `confidence: low` slices.

CI canary policy: warm-path-phase2 and incremental-phase2 latency tests are regression gates. 25% degradation on warm p95 or 30% on incremental p95 fails CI. Cold p95 is measured but advisory.

## Risks (top 5)

1. **DaemonPool is new architectural infrastructure Phase 0/1 didn't sanction.** It lives below the probe ABC; the contract is preserved; but the *coordinator* is now stateful across gathers in a new way. Phase 14's Temporal lift will need to redesign daemon lifecycle (per-Activity? per-Worker? per-Task-Queue?). Mitigation: ADR-0007's "extension by addition" is honored at the probe-contract layer; the daemon layer is documented as a Phase 1→Phase 14 implementation seam. Phase 14's design must explicitly account for it.
2. **The `applies_to_tasks` gate on `RuntimeTraceProbe` may surprise consumers.** Phase 2 ships the probe but it's not in the default-gather set. A consumer that assumes "Phase 2 ran, therefore I have a runtime trace" will find that assumption wrong. Mitigation: the per-probe sub-schema for runtime_trace declares it nullable; `IndexHealthProbe` reports `not_run` not `error` when it's absent; documentation is loud.
3. **SCIP incremental indexing is a new code path I haven't shipped.** If `scip-typescript --stdio` doesn't support incremental mode, the fall-back is full re-index every time (~25 s). Mitigation: the daemon adapter abstracts the protocol; the per-gather cache key falls back to declared_inputs hashing in fresh-process mode; correctness is preserved at the cost of wall-clock. Open question for the synthesizer.
4. **Tantivy adds a Rust-extension dep where Phase 1's synthesizer rejected similar deps.** The justification (BM25 over external docs is the only non-LLM way to make the `production/design.md §"Progressive disclosure"` model operationally cheap at portfolio scale) is structural, not perf-marginal. If the synthesizer keeps Phase 1's stance, BM25 falls back to `ripgrep`-based query (10× slower at Stage 3 query time, but still operational).
5. **The CVE-feed-triggered selective-invalidation logic** in `grype_cve`'s cache layer is the load-bearing piece of Phase 14's "10-minute portfolio reassessment" promise, but it's not exercised end-to-end until Phase 14. We design it in Phase 2; we test it via a unit test that simulates a CVE-feed event; we don't test it in production until Phase 14 lands. Risk: an edge case (e.g., a CVE that affects a transitive package not in the top-level SBOM) is missed in Phase 2 testing and surfaces in Phase 14. Mitigation: explicit fixture test in Phase 2; tracked as a Phase 14 integration-test precondition.

## Acknowledged blind spots

- **DaemonPool lifecycle under Temporal (Phase 9+).** I designed DaemonPool around the long-lived worker model. Temporal Activities are units of work that can run on different workers; the worker-affinity model needed for daemon reuse is non-trivial. Phase 9 will either pin daemons to Activity Task Queues or redesign. My numbers assume worker-affinity exists; if Phase 9 disagrees, Phase 2 numbers are optimistic.
- **Cross-language Layer B (Java/Python).** I designed SCIP integration for TypeScript only. Java's `scip-java` and Python's `scip-python` have different daemon characteristics; the DaemonPool abstraction works in theory but I haven't verified it on those tools. Phase 2's exit criterion is "every probe layer runs against real repos"; the roadmap implies Node only at Phase 2; v0.2 deals with Java.
- **macOS dev UX.** `strace` doesn't exist; runtime trace degrades; eBPF doesn't apply. Docker on macOS is slower (~2× the build time). My numbers are Linux-Phase-14 numbers. Local-dev experience on a Mac will be ~3× slower on the cold path.
- **The `IndexHealthProbe`'s "image digest match without rebuild" proxy** is heuristic. A floating base-image tag (e.g., `node:20-alpine` resolving to a different digest tomorrow than today) would make our build-config hash match while the real built image diverges. Mitigation: `syft_sbom`'s cache key includes the registry-resolved base-image digest; if the registry returns a different digest, the SBOM cache invalidates and a real rebuild fires; `IndexHealthProbe` cross-checks against the rebuild's actual digest. Edge case: registry call fails → LRU returns stale → false-positive health. Recorded.
- **No probe in Phase 2 closes the supply-chain dimension** of lockfile integrity (signature verification of package metadata, npm provenance attestations). That's a Phase 12 task. Phase 2's `gitleaks` + `grype` catch some of the surface; the rest is out of scope.
- **Bencher methodology — same as Phase 1.** Numbers are designed targets; CI bench tests will land them and the actual values will move. I committed to targets, not measurements.
- **`semgrep`'s daemon mode (`--x-language-server`) is a newer feature.** If the installed version doesn't support it, we fall back to fresh-process per-gather with `--metrics off` to skip telemetry; per-gather budget breached by ~1 s. The synthesizer should treat this as a real risk to pin in CI.

## Open questions for the synthesizer

1. **DaemonPool as new architectural infrastructure.** Is the Phase 14 Temporal worker model expected to support daemon-style state across activities? My design assumes yes; if the synthesizer says no, the Phase 2 perf numbers move by 30–60% on the cold path.
2. **Per-task gating of `RuntimeTraceProbe`.** I propose `applies_to_tasks = ["distroless_migration", "container_hardening"]` so it doesn't run on every push. Is this the right gating mechanism, or should it be a separate "expensive probes" tier that the registry filters explicitly?
3. **`tantivy` Python bindings as a Rust-extension dep.** Phase 1's synthesizer rejected similar deps. The BM25 use case is structural (D9 doesn't exist without it). Ship tantivy, or ship `ripgrep` fallback only?
4. **SCIP incremental indexing.** The 1.5 s incremental delta number rests on `scip-typescript --stdio` supporting incremental mode. If it doesn't, full re-index per gather is ~25 s. Should Phase 2 ship the wrapper script that exposes incremental mode regardless, or fall back to per-gather full re-index and accept the ~10× perf hit?
5. **`grype_cve` selective invalidation on CVE-feed events.** This is the Phase 14 integration seam. Should Phase 2 ship the cache-invalidation API endpoint that Phase 14 will call, or leave it as Phase 14's problem?
6. **Per-file findings sub-caches** (semgrep, tree-sitter) introduce inode pressure. Cap their size via `cache gc`, or shard them differently?
7. **`IndexHealthProbe` 50 ms budget — is this hard-enforced (budget breach → confidence: low) or advisory?** My design is hard-enforced because silent staleness is the worst failure mode. The synthesizer might want advisory-only with a CI canary.
8. **The roadmap exit criterion "IndexHealthProbe surfaces at least one real staleness case in CI."** I propose the seeded-staleness fixture as the test. Is there a richer expectation here — e.g., a real run against an OSS repo where staleness emerges organically?
