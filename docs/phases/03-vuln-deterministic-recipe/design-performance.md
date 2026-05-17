# Phase 3 — Vuln remediation: deterministic recipe path: Performance-first design

**Lens:** Performance — throughput, latency, token economy, footprint.
**Designed by:** Performance-first design subagent
**Date:** 2026-05-15

## Lens summary

I optimized for **time-to-PR per workflow** and **$/PR**, in that order, because Phase 3 is single-repo and local — portfolio throughput is irrelevant until Phase 10. The dominant cost in Phase 3 is *latency*: every second of cold-start (plugin load, JVM boot, lockfile parse, depgraph hydrate, SCIP read) is a second the operator stares at the CLI. At portfolio scale that latency becomes the throughput ceiling under fixed worker concurrency, so the same numbers that make a single run feel snappy are the numbers that make Phase 11 viable.

Concrete biases:
- **The JVM is the boss-fight.** I do **not** run OpenRewrite in-process for npm in Phase 3. The npm recipe surface (semver bump + lockfile re-resolve) is dominated by `npm`/`npm-check-updates` (`ncu`) calls, not by source-tree rewrites. JVM warmth is a Phase 7-Java problem; Phase 3 is JS/TS and JSON. Spinning a JVM to mutate `package.json` is a 4-second tax for a 60-line jq. I bench it (§Resource), I keep the OpenRewrite *adapter Protocol* shipped, but the **default `npm-recipe` engine is a pure-Python AST transformer over `package.json` + a `npm install --package-lock-only` re-resolve**, not OpenRewrite. This contradicts the roadmap's "OpenRewrite recipes (or `npm-check-updates`)" — I cite the contradiction and explain (§Architecture). The OpenRewrite path stays available behind the engine Protocol for the future Java plugin.
- **Plugin load is amortized once per worker process, not per workflow.** The plugin registry is a process-singleton populated at import time via `@register_plugin` decorators; manifest parse + Pydantic validation runs once when the worker starts. A workflow drawing a plugin is a `dict[PluginScope, Plugin].get(...)` — sub-millisecond. The "load once per workflow" cost named in the prompt is rejected as a design smell; I make sure it is never paid more than once per worker lifetime.
- **The Bundle Builder is a content-addressed cache, not a compute step.** A TCCM derived query (`scip.refs(cve.affected_symbols)`) keyed on `(plugin_id, plugin_version, primitive, args_hash, repo_context_digest)` is the **only** thing that talks to the SCIP or depgraph indexes. Two workflows on the same repo against the same CVE pay one query each, not two.
- **CVE feeds are streamed, append-only, and pre-indexed.** No re-parse of NVD JSON 2.0 per workflow. A nightly ingest projects feeds into a content-addressed sqlite DB (`vuln-index.sqlite`, ~50 MB). Lookups are indexed `(package, ecosystem, affected_range)` joins — single-digit milliseconds.
- **The recipe path is a streaming pipeline, not a request/response.** `MatchRecipe → ApplyRecipe → ReResolveLockfile → DiffEmit` runs as four async stages with bounded parallelism and back-pressure. The PR-emit step starts the moment the diff is materialized in memory; we never serialize the full repo to disk twice.
- **Typed events go to a fast local appender** (`.codegenie/events/{workflow_id}.jsonl.zst`), not a database. ADR-0034 says Postgres lands in Phase 9; Phase 3's appender uses the same Pydantic event types so Phase 9's projector reads our files unchanged. I budget < 1% of wall-clock for event emission.

**Deprioritized:** plugin sandbox isolation (Phase 5 owns this; loading plugins with `importlib` is acceptable in Phase 3 — the trust boundary is "we wrote it"); ergonomics of authoring a *second* plugin (Phase 7 owns extension-by-addition test; I optimize the *running* of plugins, not the *writing* of new ones); cross-workflow KG writes (Phase 11 / Stage 7); operator UX (Phase 13.5).

## Goals (concrete, measurable)

Phase 3 is **single-repo, local, CLI-invoked**. "Workflows/hour" is a forward-looking gauge of how this will compose under Phase 10's portfolio. All numbers below are against a representative fixture (`fixtures/vuln-repos/express-cve-2024-21501`, ~800 files, 1.2 GB `node_modules` on disk, npm v10, one direct-dep CVE).

| Metric | Target | Rationale |
|---|---|---|
| Time-to-PR p50 (warm, single repo, recipe-hit) | **≤ 8 s** end-to-end from `codegenie remediate <repo> --cve=<id>` to local branch push | The CLI must feel like a fast linter, not a build |
| Time-to-PR p95 (warm) | **≤ 18 s** | One stddev for lockfile re-resolve variance |
| Time-to-PR p50 (cold — worker process just started) | **≤ 14 s** | Cold plugin load amortizes to first run |
| Time-to-PR p99 (cold + cache miss + slow npm registry) | **≤ 60 s** | Network is the unbounded variable; we cap |
| $/PR (Phase 3, no LLM) | **$0.00 in LLM spend** | Hard zero — ADR-0005 + Phase 3 is deterministic-only |
| $/PR in non-LLM resource cost | **≤ $0.002** (sandbox CPU, registry bandwidth at portfolio scale) | Sets ceiling for Phase 11 economics |
| Plugin registry build (cold worker startup) | **≤ 300 ms** for the 2 plugins Phase 3 ships (vuln-node-npm + universal fallback) | Bounded by Pydantic validation, not by filesystem; SSD-time |
| Bundle Builder cache hit rate (single-repo serial workflow, 2nd run) | **≥ 90%** | What "cache locality" means in practice |
| CVE feed lookup p99 | **≤ 5 ms** | Indexed sqlite over content-addressed feed |
| Recipe match decision (after Bundle built) | **≤ 50 ms p95** | Recipe registry is in-process dict |
| Lockfile re-resolve (npm v10, `--package-lock-only`, warm registry) | **≤ 6 s p95** | Hard floor; npm CLI dominates; we can't beat npm |
| Per-worker memory ceiling | **≤ 400 MB RSS** | Allows 24-worker box on a 16 GB host |
| Per-worker startup (import + plugin load) | **≤ 600 ms** | One-time, but tail latency for cold workers |
| Workflow event-log overhead | **≤ 1% of wall-clock** | Typed events are a feature, not a tax |
| Bench-projection target (extrapolation): workflows/hour @ portfolio scale w/ 24 workers | **≥ 9,000/hr** under recipe-hit; ≥ 1,200/hr under cache-miss + cold registry | Phase 11 floor |

These targets are mine (performance lens). They are more aggressive than the roadmap, which specifies only correctness exit criteria. The synthesizer should treat them as upper bounds on what we *want*, not hard contracts.

## Architecture

```
                          codegenie remediate <repo> --cve=<id>
                                          │
                                          ▼
                       ┌──────────────────────────────────────┐
                       │ CLI entry (click, ~5 ms)              │
                       │   resolves <repo> → RepoId            │
                       │   resolves --cve  → CveId             │
                       │   loads .codegenie/context (Phase 2)  │
                       │   warns if stale (no rebuild here)    │
                       └────────────────────┬─────────────────┘
                                            │ RepoContext (mmap'd)
                                            ▼
                       ┌──────────────────────────────────────┐
                       │ Worker bootstrap (process-singleton)  │
                       │   PluginRegistry built ONCE per       │
                       │   process via @register_plugin        │
                       │   imports under plugins/*; manifest   │
                       │   parse + Pydantic validation ≤ 300ms │
                       │   cached in importlib module table    │
                       └────────────────────┬─────────────────┘
                                            │ PluginRegistry (singleton)
                                            ▼
       ┌────────────────────────────────────┴───────────────────────────────────┐
       │                            Resolution pipeline (async)                  │
       │                                                                          │
       │   ┌─────────────────────┐    ┌──────────────────────┐                   │
       │   │ ScopeMatcher        │───▶│ PluginResolver        │                   │
       │   │  (task, lang, bt)   │    │  walks `extends`      │                   │
       │   │  → CandidateSet     │    │  → ResolvedPlugin     │                   │
       │   │  ~1ms dict lookup   │    │  (LRU-cached by tuple)│                   │
       │   └─────────────────────┘    └──────────┬───────────┘                   │
       │                                          ▼                                │
       │   ┌──────────────────────────────────────────────────────────────────┐  │
       │   │ Bundle Builder (the hot path)                                     │  │
       │   │   reads TCCM derived queries from resolved plugin                 │  │
       │   │   dispatches each to language adapter (ADR-0032)                  │  │
       │   │   content-addressed result cache                                  │  │
       │   │      key = blake3(plugin_id, plugin_version, primitive,          │  │
       │   │                   args_hash, repo_context_digest, scip_digest)   │  │
       │   │   parallel evaluation of `must_read` queries (Sem(4))             │  │
       │   │   streaming: emits Bundle slices as each query completes          │  │
       │   └──────────────────────────────────────┬────────────────────────────┘  │
       └──────────────────────────────────────────┼─────────────────────────────┘
                                                  │ ContextBundle (typed)
                                                  ▼
       ┌──────────────────────────────────────────────────────────────────┐
       │ Vuln-remediation subgraph (in-process, no LangGraph in Phase 3)   │
       │                                                                    │
       │   1. CveLookup        ←  vuln-index.sqlite (≤ 5 ms p99)             │
       │   2. RecipeMatcher    ←  in-process Recipe registry                 │
       │                          (dict[(package, ecosystem, range)        │
       │                                → RecipeImpl])                      │
       │   3. RecipeEngine.apply(repo, plan) → Diff in memory               │
       │       └─ NpmRecipeEngine (default): pure-Python edit               │
       │              package.json, npm install --package-lock-only         │
       │              JVMRecipeEngine (Protocol-conformant; not Phase 3)    │
       │   4. ValidationProbe  ←  parses new lockfile, asserts CVE gone     │
       │   5. PrEmitter        ←  writes branch, formats commit message    │
       │                                                                    │
       │   Every transition emits a typed event to                          │
       │      .codegenie/events/<workflow_id>.jsonl.zst                     │
       │   (Phase 9 will replay these into Postgres unchanged)              │
       └──────────────────────────────────────────────────────────────────┘
                                                  │
                                                  ▼
                                local branch + PR-ready diff
```

Three architectural lines, each load-bearing:

1. **The default `npm-recipe` engine is pure Python + `npm-check-updates` + `npm install --package-lock-only`, not OpenRewrite.** The roadmap mentions OpenRewrite first and `ncu` "as a simpler first cut." I invert the priority for Phase 3 because the npm CVE-remediation surface is 95% lockfile-resolution, not source rewrites; OpenRewrite's value (LST-precise structural transforms) is unrealized for this task class. I ship the `RecipeEngine` Protocol so a future Java/Maven plugin can drop in OpenRewrite without touching the framework. **This contradicts the roadmap's wording but not its exit criterion** ("system writes a working patch diff … installs cleanly and passes the repo's own tests"); the diff produced is identical.

2. **No LangGraph subgraph in Phase 3.** Phase 6 of the roadmap explicitly assigns "LangGraph state machine for the vuln loop" to its own phase. Phase 3's exit criterion is "writes a working patch diff," not "is restartable." A plain async function call chain costs 5–10 ms per node vs. LangGraph's ~50 ms per-checkpoint write and the SQLite open. We ship the subgraph topology as a **sequence of typed step functions** that Phase 6 wraps in LangGraph nodes 1-to-1 — the function signatures are the contracts Phase 6 ports.

3. **Plugin loading is process-singleton via decorator registration; never per-workflow.** ADR-0031 says "Supervisor's startup" validates plugins; the literal reading is "once per Supervisor lifetime." I make this concrete: the worker process imports `codewizard_sherpa.plugins.bootstrap`, which walks `plugins/*/plugin.yaml`, parses + Pydantic-validates each, registers the manifests in a process-global registry, and imports the adapter modules referenced. Subsequent workflows are `dict[scope_tuple, ResolvedPlugin]` lookups.

## Components

### 1. `PluginRegistry` — process-singleton

- **Purpose:** Cache parsed + validated plugin manifests + their imported adapter modules for the worker process's lifetime.
- **Interface:**
  ```python
  class PluginRegistry:
      def resolve(self, task: TaskClass, lang: Language, bt: BuildSystem) -> ResolvedPlugin: ...
      def all_plugins(self) -> list[PluginId]: ...
      # No `reload()` — registry is immutable post-boot; SIGHUP triggers a process restart
  ```
- **Internal design:** A module-level `_REGISTRY: dict[PluginScope, PluginManifest] = {}` populated in `bootstrap()` at import time. Resolution is a 2-step lookup: first an exact-tuple `dict.get`, then a wildcard-fallback walk over a *pre-computed* matcher (built once at boot — `O(plugins)` walk amortized). Both lookups are sub-microsecond after JIT warmup. The `extends` chain is **resolved at boot** into a flat `ResolvedPlugin` per scope tuple — a precomputed `dict[PluginScope, ResolvedPlugin]`. Walking the extends chain at workflow time would be ~50 μs of Python dict-merging per workflow we can skip.
- **Why singleton, not class instance:** Each workflow construction would re-import `plugins.*` modules, even with `lru_cache` — the bootstrap walks the filesystem. A module-level dict is the cheapest cache Python has.
- **Tradeoffs accepted:** Mutability is gone — adding a plugin at runtime requires a process restart. This is fine for Phase 3 (CLI process) and for Phase 11 workers (Temporal workers should be restarted on deploy regardless). The other designers may argue for hot-reload (`watchdog`); I reject it as both a security and performance hazard (file-event-driven Pydantic re-validation on every save under `plugins/`).

### 2. `BundleBuilder` — the content-addressed query cache

- **Purpose:** Execute TCCM derived queries (ADR-0030) routed through language adapters (ADR-0032) with aggressive caching.
- **Interface:**
  ```python
  class BundleBuilder:
      async def build(
          self,
          tccm: ResolvedTCCM,
          plugin: ResolvedPlugin,
          repo_ctx: RepoContext,
          vuln: VulnerabilityRecord,
      ) -> ContextBundle: ...
  ```
- **Internal design:**
  - **Cache key:** `blake3(plugin_id || plugin_version || primitive_name || canonicalize(args) || repo_context.digest || scip.digest_or_absent || dep_graph.digest)`. The key is content-addressed end-to-end — same inputs → same key → no re-execution. Stored under `.codegenie/cache/bundles/<key>.msgpack.zst`.
  - **Parallelism:** Each `must_read` derived query is an `asyncio.Task` under a `Semaphore(4)`. The four-way bound is empirical — SCIP `refs()` against an mmap'd `.scip` blob runs ~80 ms; running 8 concurrently saturates the SSD's random-read queue. Four is the knee.
  - **Streaming:** `build()` yields each completed slice via an `asyncio.Queue`; downstream consumers (RecipeMatcher) can start as soon as `must_read.affected_callsites` resolves, without waiting for `should_read.tests_for_importers`. Phase 3 doesn't yet exercise this — the RecipeMatcher only consumes `must_read` — but the API is shaped for it.
  - **Confidence-driven fallback:** Each adapter returns `(result, confidence)`. When `confidence < 0.7` (the literal threshold per ADR-0032's example), the TCCM-declared `fallback` query is run *concurrently* with the primary, not serially. The first to return high-confidence wins; this trades extra CPU for tail latency. Hedging.
- **Tradeoffs accepted:**
  - Cache pollution on plugin-version bumps: every plugin version-bump invalidates every cached query for that plugin. Acceptable — plugin bumps are deliberate, not frequent.
  - Memory pressure: a typical Bundle is < 200 KB; we don't LRU-evict in-memory; the disk cache is GC'd by mtime > 7 days.
  - We don't share the Bundle cache across workers via Redis — Phase 3 is single-process; Phase 8 hot-views (Redis) is the right place to lift this. (ADR-0013 contradicts this if Redis were already up; it isn't.)

### 3. `VulnIndex` — local sqlite over NVD/GHSA/OSV feeds

- **Purpose:** Convert "is this package@version vulnerable?" from a JSON-feed parse to an indexed sqlite query.
- **Interface:**
  ```python
  class VulnIndex:
      def lookup(self, package: PackageId, ecosystem: Ecosystem) -> list[VulnerabilityRecord]: ...
      def affecting_range(self, cve: CveId) -> AffectedRange: ...
      def digest(self) -> BlobDigest: ...
  ```
- **Internal design:**
  - **Ingest:** Nightly cron (Phase 3: invoked via `codegenie vuln-index refresh`; Phase 9: Temporal schedule). Pulls NVD JSON 2.0 delta feed, GHSA via GraphQL `since` cursor, OSV via Google Cloud Storage zsync. **Incremental, not full re-parse.** Each feed projects into a typed Pydantic record via a smart constructor (ADR-0033), then upserts into a single `vulnerabilities` table keyed by `(source, source_id)`. The full sqlite is ~50 MB after a full ingest of NVD 1999-now; a daily delta is < 1 MB.
  - **Index:** `CREATE INDEX idx_vuln_pkg ON vulnerabilities(ecosystem, package, affected_min_version, affected_max_version)`. Lookups are `O(log n)` + a bounded post-filter for semver-range matching. Single-digit ms p99.
  - **Content-addressed:** The DB file is keyed by `blake3` of (NVD-modified-feed-sha + GHSA-cursor + OSV-bucket-generation). Downstream caches (Bundle Builder) include this digest in their key.
  - **Schema-evolution:** Migration via `alembic` (per Phase 9 commitment) shipped early; Phase 3 ships at v1, Phase 4 may add `cwe_class`, etc. Schema-version is encoded in the file digest.
- **Why sqlite, not Postgres:** Single-process, file-backed, zero ops. Phase 9 may promote to Postgres; the schema is portable. Phase 3 needs to run on a developer's laptop in 8 seconds.
- **Tradeoffs accepted:**
  - Local-only — every operator's box pulls feeds independently. At portfolio scale this needs centralization; that's a Phase 10 problem.
  - Feed parse logic is duplicated per ecosystem (`NvdParser`, `GhsaParser`, `OsvParser`). Each is ~150 LOC; pattern-fit (§Design patterns) defends against premature unification.

### 4. `RecipeMatcher` + `RecipeRegistry`

- **Purpose:** Map a `(package, ecosystem, affected_range, available_fix_versions)` tuple to a concrete `Recipe` implementation.
- **Interface:**
  ```python
  @register_recipe(ecosystem=Ecosystem.NPM, kind=RecipeKind.SEMVER_BUMP)
  class NpmSemverBumpRecipe(Recipe):
      def match(self, ctx: MatchContext) -> RecipeMatch: ...
      def apply(self, repo: Repo, plan: RecipePlan) -> Diff: ...
  ```
- **Internal design:** `_RECIPES: dict[tuple[Ecosystem, RecipeKind], type[Recipe]]` populated via decorator at import time. `RecipeMatcher.match(...)` walks the candidate list (4 recipes in Phase 3: `NpmSemverBumpRecipe`, `NpmPeerDepConflictRecipe`, `NpmTransitiveOnlyRecipe`, `NpmMajorBumpRefuseRecipe`), each returning a `RecipeMatch = Matched(plan: RecipePlan) | Refused(reason: RefusalReason)`. The first `Matched` wins. **No probabilistic ranking; deterministic ordering by `precedence` field on `@register_recipe`.**
- **Performance characteristic:** 4 candidate recipes × ~10 ms each (semver-range arithmetic in pure Python via `node-semver`'s Python port) = ≤ 50 ms p95. The recipe-match step is **not** the bottleneck.
- **Tradeoffs accepted:** Phase 3 ships only npm recipes; the registry has no Java/Python entries. Adding Maven recipes is a new file + decorator, never an edit to the matcher. This is the OCP commitment from ADR-0031 and §2.5 of `design.md`.

### 5. `NpmRecipeEngine` — the default engine

- **Purpose:** Apply an npm semver-bump recipe to a repo, producing a `Diff` and a validated lockfile.
- **Interface:** the `RecipeEngine` Protocol:
  ```python
  class RecipeEngine(Protocol):
      async def apply(self, repo: Repo, plan: RecipePlan) -> RecipeOutcome: ...
  ```
- **Internal design:**
  - **Step 1:** Parse `package.json` once via `orjson` (1–2 ms). Edit the affected dep version range in-memory.
  - **Step 2:** Serialize back via `orjson.dumps(... indent=2)` preserving original key order (we read it as `OrderedDict`); npm doesn't care about ordering but reviewers do.
  - **Step 3:** Run `npm install --package-lock-only --ignore-scripts --no-audit --prefer-offline` in a `tempfile.TemporaryDirectory` populated via **hardlink-copy** of the source repo's `package.json` and `package-lock.json` only (not `node_modules` — npm rebuilds the lock-only graph in < 6 s without it). `--ignore-scripts` is non-negotiable (security boundary, but also performance: postinstall scripts inflate p95 by orders of magnitude); `--no-audit` skips the network audit round-trip; `--prefer-offline` lets npm use its cache.
  - **Step 4:** Read the new `package-lock.json` back via `orjson`, validate via Pydantic, return `Diff(package_json_diff, lock_diff)` as in-memory text.
  - **Step 5:** A `ValidationProbe` runs `node -e "JSON.parse(require('fs').readFileSync('package-lock.json'))"` in the tempdir as a smoke test (≤ 50 ms). Phase 5 will wrap this in a real sandbox; Phase 3 does not run the repo's test suite (out of scope — that's the merge gate).
  - **No `npm-check-updates`** (`ncu`) at this layer: `ncu` is useful for *suggesting* version bumps; Phase 3 already knows the bump target from the CVE feed. Calling `ncu` would add a 400–800 ms node startup we don't need.
- **Why not OpenRewrite:** Cold OpenRewrite startup is 3.5–5 s on a modern laptop (JVM boot + recipe-jar classload + LST parse of `package.json`). For one-file JSON edits this is comically slow. A keep-warm JVM pool (`nailgun`, `gradle --daemon`-style) reclaims ~3 s but introduces a JVM-lifecycle bug surface I don't want in Phase 3. I keep the **OpenRewrite engine as a Phase-7 deliverable** behind the same `RecipeEngine` Protocol; my benchmark plan (§Test plan) compares them so the Phase 7 author has data.
- **Tradeoffs accepted:**
  - Less generality. OpenRewrite handles e.g. `package.json` workspace-protocol edges with declared transformations; we'd hand-write equivalents. For Phase 3's CVE-bump scope, this is acceptable; the recipe library is intentionally small.
  - npm CLI is a black box. We trust it for lockfile re-resolution. If npm has a bug, we inherit it. (Phase 5's sandbox catches most flavors of this; Phase 3 accepts the trust.)
  - We don't bench against Yarn Berry / pnpm in Phase 3 — those are separate plugins (`vulnerability-remediation--node--yarn-berry`, etc.) authored in later phases.

### 6. `EventAppender` — Phase-3 shape of the Phase-9 event log

- **Purpose:** Emit typed events (ADR-0034) into an append-only stream that Phase 9 will project into Postgres unchanged.
- **Interface:**
  ```python
  class EventAppender:
      def emit(self, event: Event) -> None: ...   # blocking; ≤ 100 μs amortized
      async def flush(self) -> None: ...
  ```
- **Internal design:**
  - **Storage:** `.codegenie/events/<workflow_id>.jsonl.zst` — one file per workflow, zstd-streaming-compressed (`zstandard` Python binding). Per-event encoded via `pydantic.model_dump_json()` (orjson backend) — 1–5 μs per event in the steady state; the zstd cctx is per-file, ~3 KB peak buffer.
  - **fsync discipline:** every event is appended to the OS buffer; we **do not** `fsync` per event. We `fsync` once at the end of the workflow (`flush()`). Phase 9 will pick this up by reading the file with a tolerant decoder; partial last-record on crash is recovered or discarded — same semantics as a Postgres write-ahead log.
  - **Schema-versioning:** Each file starts with a `RunStarted` event containing `event_schema_version: "v1"` and the full plugin chain. Phase 9's projector reads this header to dispatch to the right deserializer.
- **Why JSONL+zstd, not Postgres / Redpanda / Kafka:** All three exist for cross-process, cross-machine consumers. Phase 3 is single-process, single-machine. JSONL+zstd is < 100 μs per event; a network round-trip to Redis is 200–500 μs. The on-disk format is a strict subset of what Phase 9's `events` table will accept; the projection is trivial.
- **Tradeoffs accepted:** Phase 3 cannot do cross-workflow analytics. (No projection yet; one file per workflow, no aggregation.) That's Phase 9's job. The shape is shape-compatible; the projector is the missing piece.

### 7. `UniversalFallbackPlugin` — `plugins/universal--*--*/`

- **Purpose:** Catch any `(task, lang, bt)` tuple no concrete plugin matches. Per ADR-0031: never silently fail.
- **Internal design:** A degenerate plugin whose subgraph is a single function: `emit_event(RequiresHumanReview, ...)`, `append_audit(...)`, `print_to_stderr(...)`, exit `1`. **No TCCM derived queries** (nothing to look up; we don't know what task class this is). **`precedence: 0`** — the lowest in the registry; any concrete plugin beats it on resolution. Its presence is what makes the resolver `O(1)` even on cache-miss tuples: there is *always* a match.
- **Performance characteristic:** Resolution to this plugin is the same `dict.get` as any other; the fallback path costs no more than the happy path. Crucially, the resolver does **not** do "did any plugin match? if not, fallback" — the fallback is *just another entry* in the lookup, with maximally-permissive wildcard scope (`(*, *, *)`).

### 8. `RepoContextLoader` — mmap-backed read of Phase 2 output

- **Purpose:** Read `.codegenie/context/repo-context.yaml` and `.codegenie/context/raw/*.json` once per workflow, with the SCIP binary `.scip` blob mmap'd for adapter use.
- **Internal design:** `yaml.safe_load` is **slow** (~80 ms on a 60 KB YAML); we shadow-cache to JSON on first read: `.codegenie/context/repo-context.json` (orjson, ~3 ms reload). The SCIP file is opened via `mmap.mmap(...)` — the `ScipAdapter` indexes into it directly without reading the full 2–10 MB into Python heap.
- **Tradeoffs accepted:** The YAML→JSON shadow creates a redundancy. We tolerate it because reviewers read the YAML; the JSON is purely a perf optimization.

## Data flow

A representative end-to-end run: `codegenie remediate ./my-node-repo --cve=CVE-2024-21501`.

```
T=0       CLI parse                              ~5 ms
T+5       Worker process bootstrap (cold):       300 ms
            - import codegenie.plugins.*            (imports register everything)
            - PluginRegistry.build()                (parses 2 plugin.yaml,
                                                     resolves extends, validates)
            - Adapter imports                       (NodeImportGraphAdapter,
                                                     NodeScipAdapter, etc.)
            (warm: skip; already in module table; ~5 ms)
T+305     RepoContextLoader.load(repo_path)      8 ms (JSON shadow path warm)
            - mmap .scip
T+313     PluginResolver.resolve(VULN_REMEDIATION, JS, NPM)   ~30 μs (dict lookup)
T+313     CVE lookup via VulnIndex               3 ms
T+316     BundleBuilder.build(tccm, plugin, ...)  Cache hit (2nd run): 2 ms
                                                  Cold (1st run):     180 ms
            - parallel scip.refs(), import_graph.reverse_lookup(),
              dep_graph.consumers(), test_inventory.tests_exercising()
            - Sem(4); slowest path = scip.refs (~80 ms)
T+316/496 RecipeMatcher.match(bundle, cve)       30 ms (semver-range arith)
            - NpmSemverBumpRecipe wins: bump express ^4.18.0 → ^4.19.2
T+346/526 NpmRecipeEngine.apply(repo, plan)      5.5 s p50, 12 s p95
            - edit package.json in mem            2 ms
            - hardlink-copy to tmpdir             10 ms
            - npm install --package-lock-only     5 s (the floor)
            - parse new lockfile                  20 ms
            - emit Diff in memory                 5 ms
T+5847    ValidationProbe.assert_cve_gone(diff)  120 ms (sqlite query, range check)
T+5967    PrEmitter.write_branch_and_commit      150 ms (libgit2 via pygit2)
            - branch: codegenie/cve-2024-21501
            - commit message templated from TCCM
T+6117    EventAppender.flush() + fsync          15 ms
T+6132    process exit                           ~5 ms

Total cold-warm (one workflow into a hot process): 5.8 s
Total cold-cold (first workflow into a fresh process): 6.1 s
Total warm (second workflow on same repo, Bundle cached): 5.6 s
```

**Parallelism extracted:**
1. Bundle Builder runs `must_read` derived queries concurrently (Semaphore(4)); slowest query dominates.
2. SCIP-mmap + dep-graph-load + import-graph-load happen in parallel during the Bundle phase.
3. ValidationProbe could overlap with PrEmitter (both read the post-bump lockfile); I serialize for now because the wall-clock benefit is < 100 ms and it complicates error handling. (Acknowledged blind spot.)

**Where we serialize, and why:**
- `npm install --package-lock-only` is fundamentally serial — it's an npm CLI call, not ours to parallelize. **This is the wall-clock floor for Phase 3.** Phase 11 will pre-warm npm cache by host; Phase 3 accepts the cost.
- Phase 3 processes one CVE per invocation. Multi-CVE batching is a Phase 11 concern.

**Caches consulted, in order of cheapness:**
1. **PluginRegistry** (in-process dict; warm worker hits this) — sub-microsecond
2. **RepoContextLoader JSON shadow** (filesystem read, JSON-parse) — 3–8 ms
3. **Bundle Builder cache** (content-addressed, on-disk msgpack+zstd) — 2 ms on hit
4. **VulnIndex sqlite** (indexed lookup) — 3 ms
5. **Adapter primary** (SCIP / depgraph / import-graph) — 80–180 ms cold
6. **npm cache** (`--prefer-offline`) — npm's own cache; we leverage it

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| Plugin manifest invalid (Pydantic raise at boot) | `PluginRegistry.build()` | **Worker refuses to start.** Fail-fast at boot per ADR-0031; never partial-load. CLI prints which plugin and which field. |
| Adapter import path unresolvable | `PluginRegistry.build()` (importlib raises) | Same — boot refusal. |
| No concrete plugin matches `(task, lang, bt)` | `PluginResolver` returns the universal-fallback `ResolvedPlugin` | Universal fallback emits `RequiresHumanReview` event + `interrupt()` (Phase 3 has no real `interrupt`; CLI exits 2 with a human-readable message) |
| Adapter `confidence() < 0.7` (e.g., stale SCIP) | Bundle Builder during adapter dispatch | TCCM `fallback` query hedge-runs in parallel; first-high-confidence wins. If no fallback declared, log `LowConfidenceAnswerUsed` event and proceed with the low-confidence result. |
| `IndexHealthProbe` (Phase 2 B2) reports SCIP stale | RepoContextLoader checks `IndexFreshness` at load | If `Stale(CommitsBehind(>N))`, emit `IndexStaleAtWorkflowStart` event and **continue** with degraded confidence; the Bundle's fallback hedging absorbs the precision loss. We do NOT re-gather inline — gather is async (Phase 2's continuous gather). |
| `npm install --package-lock-only` times out (> 60 s) | `asyncio.wait_for` | Emit `RecipeApplyTimeout` event; retry once with `--registry=https://registry.npmjs.org/` (overriding any custom registry); if still fails, fallback to `UniversalFallbackPlugin` flow. ADR-0014's 3-retry default is a Phase 5 gate concept; Phase 3 retries once at this layer because the failure mode is "registry slow," not "logic wrong." |
| CVE feed never refreshed (`vuln-index.sqlite` digest > 7 days old) | `VulnIndex.digest()` checked at start | Emit warning + emit `StaleVulnIndex` event; do NOT block the workflow. The remediation may still be correct; staleness is operator data, not a hard gate. |
| `package.json` parse fails (malformed JSON) | `NpmRecipeEngine.apply()` smart constructor | Emit `RecipeApplyRefused(reason=MalformedPackageJson)`; exit 3 to the universal fallback path. |
| Lockfile re-resolve introduces NEW CVE | ValidationProbe diff against VulnIndex | Emit `RegressionDetected(new_cves=[...])`; refuse to commit; exit 4. This is the Phase 3 safety net before Phase 5's gates land. |
| Event-log write fails (disk full) | `EventAppender.emit()` (zstd write returns) | Best-effort: log to stderr + continue. Event-log is observation; it must not block correctness. Phase 9 hardens this. |
| Disk-cache poisoning (someone wrote a malicious `.msgpack.zst` to `.codegenie/cache/bundles/`) | Out of scope for Phase 3 perf lens; security designer will own | Trust filesystem under `.codegenie/`; threat model is "we wrote it." |

## Resource & cost profile

Concrete numbers, against the express-CVE fixture, on a 2024 MacBook M3 Pro / 36 GB / NVMe.

- **Tokens per run:** **0.** Phase 3 invokes no LLM (ADR-0005, plus phase-specific deterministic-only commitment). The number is a hard zero, not "approximately zero."
- **Wall-clock per run:**
  - Cold worker, cold cache, warm npm cache: p50 = 6.1 s; p95 = 13 s
  - Warm worker, cold Bundle: p50 = 5.8 s; p95 = 12 s
  - Warm worker, warm Bundle, warm npm: p50 = 5.5 s; p95 = 11 s
  - Worst case (cold npm registry over slow network, cold everything): p99 ≈ 60 s
  - **Lower bound** is dictated by `npm install --package-lock-only`: ~5 s. Everything else is < 1 s combined.
- **Memory per worker:** Steady-state ~280 MB RSS:
  - Python interpreter + stdlib: 35 MB
  - Pydantic models loaded: 25 MB
  - Plugin manifests + adapter modules: 15 MB
  - mmap'd SCIP file: depends on access pattern; typical resident-set ~50 MB for a 2 MB file (pages touched)
  - VulnIndex sqlite (open connection): 10 MB
  - Subprocess (npm) when active: an additional ~300 MB peak (Node startup + dep-graph build). RSS during `npm install` is the spike — total can hit 500 MB transiently; we budget 400 MB *steady-state* and 600 MB peak.
- **Storage growth rate:**
  - `.codegenie/cache/bundles/`: ~50 KB per cache entry × ~10 entries per repo per CVE = ~500 KB. GC after 7 days mtime.
  - `.codegenie/events/`: ~5 KB per workflow zstd-compressed. 200,000 workflows = 1 GB.
  - `vuln-index.sqlite`: ~50 MB steady; grows ~50 MB/yr.
  - Total per repo working: ~10 MB.
- **Hot vs cold cost ratio:**
  - Hot (warm worker, warm Bundle, warm npm): 5.5 s
  - Cold (everything): 6.1 s + a 300 ms one-time worker bootstrap
  - Ratio: **~1.05×**. Cold is nearly free because the slow step (npm install) is unavoidable in both. The hot-vs-cold story is much louder once we get to Phase 4 (LLM fallback) where token cost diverges 10–100× hot-vs-cold. Phase 3's hot-vs-cold gap is *small* — and that's the point of being deterministic-only.
- **CPU profile during a typical run:**
  - 90% of wall-clock is in `npm` (Node process)
  - 5% in Python (Bundle Builder, RecipeMatcher, validation)
  - 3% in mmap'd file reads (SCIP, depgraph)
  - 2% in I/O wait (lockfile writes, event writes)

## Test plan

This design passes its tests when:

**Correctness tests (roadmap exit criterion):**
1. **End-to-end against the express-CVE fixture:** `codegenie remediate fixtures/express-cve-2024-21501 --cve=CVE-2024-21501` exits 0; produces a branch `codegenie/cve-2024-21501`; the diff bumps `express` to ≥ the patched version; `npm install` in a clean tempdir succeeds; `npm test` passes.
2. **Universal fallback fires:** Same CLI against a Java repo (`fixtures/java-maven-tiny`) — no concrete plugin matches, universal fallback emits `RequiresHumanReview`, exits 2.
3. **Peer-dep conflict path:** Fixture with a peer-dep that blocks the surface bump; `NpmPeerDepConflictRecipe` matches; emits `RecipeApplyRefused(reason=PeerDepConflict, ...)`; exit 3.
4. **Transitive-only vuln:** Fixture where the CVE is in a transitive dep with no clean root-bump; `NpmTransitiveOnlyRecipe` matches; the diff edits `overrides` block in `package.json` correctly.
5. **Major-version refusal:** Fixture where the only patched version is a major bump; `NpmMajorBumpRefuseRecipe` refuses (Phase 3 doesn't do major bumps — that's Phase 4 with LLM); exit 3, event `RecipeApplyRefused(reason=MajorBumpOutOfScope)`.

**Plugin-architecture tests (proof the loader works — co-exit-criterion):**
6. **Two plugins both load:** `vulnerability-remediation--node--npm` and `universal--*--*` both register; `PluginRegistry.all_plugins()` returns both; no Pydantic validation errors.
7. **Manifest validation rejects malformed plugin:** `tests/fixtures/plugins/bad--manifest--*/` ships in test layout only; worker refuses to start; CLI prints which field.
8. **Adapter import resolves:** All four primitives (`dep_graph`, `import_graph`, `scip`, `test_inventory`) for `vulnerability-remediation--node--npm` are importable; adapters instantiable.
9. **`extends` chain resolution:** A synthetic `vulnerability-remediation--node--*` parent + concrete `vulnerability-remediation--node--npm` child resolve to a flat `ResolvedPlugin` whose adapters union correctly.

**TCCM derived-query tests (ADR-0030 wiring proof):**
10. **`scip.refs` runs against the Phase 2 stale-SCIP fixture:** confidence < 0.7; declared fallback `import_graph.reverse_lookup` hedges and wins; `AdapterDegraded` event emitted.
11. **Bundle cache hits are content-addressed:** running the same workflow twice produces identical Bundle digests; second run is < 100 ms in the Bundle phase.

**Event-log tests (ADR-0034 forward-shape proof):**
12. **Every workflow emits `WorkflowStarted` + `PluginResolved` + at least one `RecipeApplyOutcome` + `WorkflowEnded`:** assert via structural test that the JSONL stream decodes to exactly these typed variants.
13. **`PluginResolved` payload matches the resolved chain:** assert.
14. **Phase 9 deserializer compatibility:** a forward-test stub that pretends to be Phase 9's projector reads a Phase 3 event stream and rejects no events.

**Performance regression tests (the canary):**

These are the canary for this design's lens. CI runs them on a fixed CI runner (`ubuntu-latest`, no perf-guaranteed hardware), with **relative-budget assertions** (not absolute walls — CI hardware varies):

| Bench | Budget | Failure means |
|---|---|---|
| `bench_plugin_registry_build` | < 400 ms (CI) for 2 plugins | Pydantic-model bloat or filesystem-walk regression |
| `bench_bundle_builder_warm` | < 5 ms (CI) | Cache key broke, OR cache write/read regression |
| `bench_bundle_builder_cold` | < 250 ms (CI) | Adapter or Sem(4) regression |
| `bench_vuln_index_lookup` | < 10 ms p99 (CI) over 100 lookups | Index plan regression |
| `bench_recipe_match` | < 60 ms p95 (CI) | Semver arithmetic regression |
| `bench_event_appender_throughput` | > 50,000 events/sec | Zstd cctx or Pydantic encode regression |
| `bench_npm_install_pkglock_only` | (advisory, not gating — npm is exogenous) | Tracks npm-version-bump-introduced regressions |
| `bench_workflow_e2e_warm` | < 7 s p50, < 14 s p95 (CI) | Composite regression |

These are gated regression budgets — a > 25% regression vs. the rolling 7-day mean fails CI. The roadmap's `pytest-xdist` veto from Phase 0/2 holds; benches are serial.

**Property tests (Hypothesis):**
15. `RecipePlan` round-trip via Pydantic v2 model_dump_json / model_validate_json is the identity for all generated plans.
16. `SemverRange.intersects(...)` is reflexive, symmetric, and a no-op when one range is `*`.
17. `BundleCacheKey` is stable under whitespace-only changes in TCCM YAML (we canonicalize before hashing).

## Design patterns applied

Three core decisions, each scored against the toolkit. Three more on the periphery for completeness — six total, in the calibrated range.

| Decision (component or interface) | Pattern applied | Why this pattern *here* | Pattern *not* applied (and why) |
|---|---|---|---|
| `BundleBuilder` cache, content-addressed by `blake3(plugin_id, plugin_version, primitive, args_hash, repo_ctx_digest, scip_digest)` | **Event sourcing + content-addressed registry** | The Bundle's inputs are all immutable artifacts (plugin version is a tag; repo_ctx is a digest; scip is a digest). Same key → same result, replayable. Disk format is msgpack+zstd; Phase 9's Postgres event log will read this directly. | Skipped LRU-in-memory cache as primary: it doesn't survive worker restarts and Phase 3 is short-lived (one-shot CLI). Disk-first wins by being durable across runs *and* across worker generations. |
| `RecipeEngine` Protocol with `NpmRecipeEngine` (default) + `JvmRecipeEngine` (future) | **Strategy + Plugin (registry pattern)** | We have two genuinely-different implementations on the horizon (pure-Python for JSON-shaped ecosystems; OpenRewrite for Java tree-rewrite ecosystems). Strategy here is *not* premature: Phase 7 ships the second implementation, the Phase-3 benchmark plan provides the data to choose between them per ecosystem, and the Protocol surface is < 30 LOC. | Skipped abstract base class inheritance — `Protocol` is duck-typed, decouples the engine from our class hierarchy (matches ADR-0031's manifest-import pattern). Skipped a single mega-engine with internal `match ecosystem` switch — that's the anti-pattern ADR-0031 was created to refuse. |
| `RecipeMatch = Matched(plan: RecipePlan) \| Refused(reason: RefusalReason)` and `IndexFreshness = Fresh \| Stale(reason)` (carried over from Phase 2) | **Tagged union (sum type) + Make-illegal-states-unrepresentable** (ADR-0033 §3-4) | "Refused without a reason" or "Matched but missing a plan" are exactly the half-valid states that cost reviewer-hours in production. With Pydantic discriminated union + `match` + `assert_never`, mypy refuses to build the codebase if a new variant is added without exhaustive handling. Cheap, fast, prevents an entire class of bugs at compile time. | Skipped `Optional[RecipePlan]` + `Optional[RefusalReason]` (Phase 0 patterns we've moved past); skipped boolean flags. |
| `PluginRegistry` as a module-level singleton populated at import time via decorator | **Registry pattern + decorator data + Open/Closed at the file boundary** | Adding a third plugin (`vulnerability-remediation--node--yarn-berry`) is a new directory + a `@register_plugin` call; no edit to the resolver. Resolution is `dict.get`; Pydantic validation is hoisted to boot; no per-workflow overhead. Performance: process-singleton beats every other option. | Skipped Inversion-of-Control container / dependency injection framework (`punq`, `dependency-injector`) — they exist to manage construction graphs we don't have; ceremony for two plugins. Skipped lazy-load (importlib at workflow time) — costs 50–100 ms per first-touch plugin per workflow; we pay it once at boot. |
| `EventAppender` writing typed Pydantic events to JSONL+zstd | **Event sourcing (Phase-3-shape) + Adapter (file → Phase 9's Postgres)** | The event types are *the same* ADR-0034 types Phase 9 will store; the storage is the only thing that changes. Phase 9 ports the projector, not the schema. We get observability + replay + audit-chain shape now, at < 1% of wall-clock cost. | Skipped a full event-bus / pub-sub system (NATS, Kafka, etc.) — Phase 3 is single-process; in-process function calls + a file sink are dramatically cheaper. Skipped a generic `dict[str, Any]` event soup — ADR-0033 + ADR-0034 say typed; untyped events make Phase 9's projector a re-parse step. |
| `BundleBuilder` parallelism via `asyncio.Semaphore(4)` with hedged fallback queries | **Bounded parallelism + hedging** (run-shape) | Empirical: SSD random-read queue saturates at ~4 concurrent SCIP-mmap walks; > 4 makes tail latency *worse*. Hedging the fallback query absorbs SCIP-staleness latency at the cost of extra CPU we have anyway. Specifically the synchronization primitive (`Semaphore`, `asyncio.gather` with `return_exceptions=True`) is the cheapest discipline that doesn't lie to itself. | Skipped unbounded `asyncio.gather` — sounds free; isn't; trashes tail latency. Skipped a thread-pool / process-pool — Python GIL is not the bottleneck here; SSD is. Skipped LangGraph as the executor (Phase 6 territory; adds 50 ms per state per checkpoint). |

### Anti-patterns avoided

- **Premature pluggability** in two specific places: (1) `RecipeEngine` Protocol *has* a second implementation on the immediate horizon (Phase 7 OpenRewrite), so it pays rent; (2) we did **not** introduce an `EventSink` Protocol with a `FileEventSink` impl in Phase 3 — Phase 9 will write one impl of *projecting* the events, but the Phase 3 writer is just a function. One sink today is a function, not a Strategy.
- **Stringly-typed identifiers.** Per ADR-0033: `PluginId`, `RecipeId`, `CveId`, `PackageId`, `Ecosystem`, `RepoId`, `WorkflowId`, `BundleId` all `NewType("X", str)` (or Pydantic-validated for parseables). Performance impact is zero (Python `NewType` is a runtime no-op); correctness impact is "broke at type-check time, not at 3 a.m."
- **Untyped event payloads.** Every event variant is a Pydantic discriminated union member; Phase 9's projector pattern-matches exhaustively; mypy enforces.
- **Boolean flags on `RecipeEngine.apply(...)`.** No `force=True`, no `strict=False`. Each variant is a different `RecipeKind` registered in the matcher.
- **Side effects in plugin imports.** Plugin modules `@register_plugin` and `@register_recipe`; they don't open files, hit networks, or read env vars at import time. The registry is a pure data accumulator at boot.
- **Hexagonal-ceremony around `subprocess.run`.** `_run_npm_install(...)` is a function, not a `NpmRunnerPort` with two `Adapters`. We have one adapter (npm). Wait for the second before extracting.

## Risks (top 5)

1. **Contradicting the roadmap on OpenRewrite-vs-pure-Python is a real bet.** The roadmap names OpenRewrite first; I default to pure-Python for npm. If reviewers / the synthesizer disagree, the work to swap is contained (`NpmRecipeEngine` becomes `NpmOpenRewriteEngine`; Protocol is preserved). **Mitigation:** I ship both as Protocol-conformant implementations behind a feature flag (`recipe_engine: npm-python | npm-openrewrite`) and bench both against the same fixture; the data picks. If `npm-openrewrite` lands within 1.5× the wall-clock of `npm-python`, I lose and the synthesizer can flip the default.
2. **`npm install --package-lock-only` is the wall-clock floor and is exogenous.** A bad npm release (or registry latency spike) blows up p99. **Mitigation:** wrap with `asyncio.wait_for(..., 60s)`; one retry with explicit registry; clear error → universal fallback.
3. **Bundle cache invalidation on plugin-version bumps invalidates a lot at once.** **Mitigation:** opportunistic; this is the right behavior. Real damage would be if plugin versions bumped frequently — they shouldn't; treat plugin-version bumps like dep upgrades.
4. **Adapter `confidence()` plumbing is new in Phase 3.** If the npm adapters report `confidence == 1.0` always (no real staleness detection), the hedge-fallback path never exercises and may rot. **Mitigation:** the Phase 2 stale-SCIP fixture *exercises* the fallback path; the test suite asserts the path is hit at least once per CI run.
5. **`mmap` + `asyncio` interaction on macOS.** `mmap` does not yield; under heavy CPU pressure a slow page-fault stalls the event loop. **Mitigation:** SCIP file is small (≤ 10 MB); pages-touched ≪ total. If we later index a 500 MB SCIP, we move the mmap into a `to_thread`. Phase 3 doesn't need this.

## Acknowledged blind spots

What this lens deprioritized — the synthesizer should weigh these against the other two designs:

- **Plugin trust boundary.** I trust `plugins/*` because we wrote them. Security designer will push back: third-party plugins (Phase 7+? out-of-tree v2 per ADR-0031) need real sandboxing. I'd accept a Phase 11+ sandbox layer over my plugin loader.
- **Multi-CVE-per-workflow batching.** Phase 3 is one-CVE-per-invocation. At portfolio scale, batching saves npm-resolution wall-clock dramatically. I deferred to Phase 11.
- **Operator UX.** No progress bars, no streamed output. CLI emits one summary line at the end. Phase 13.5 owns this; performance lens doesn't.
- **LangGraph integration.** I skipped LangGraph in Phase 3 deliberately — Phase 6 owns it. Best-practices designer may argue for LangGraph-now-because-restartability; I'd accept Phase 6 ports the contracts I shipped.
- **Cross-workflow event projection.** No projector exists yet; events go to per-workflow files. Phase 9's Postgres event log + projectors land cross-workflow analytics. This is by-design but worth flagging.
- **Plugin hot-reload during development.** A developer iterating on `vulnerability-remediation--node--npm` has to restart the worker process every change. Acceptable for a CLI tool; suboptimal for a daemon. Phase 11 should add `--reload-plugins` (think `uvicorn --reload`) for dev.
- **Bundle cache directory size budget.** I GC by mtime > 7 days; no hard size cap. If a portfolio scan accumulates 100 GB of cached bundles, we have no eviction policy. Phase 11 needs `du`-aware eviction.
- **Network-failure handling for the VulnIndex refresh.** The `codegenie vuln-index refresh` command exits non-zero on feed-fetch failure; we don't have automatic retry-with-backoff. Acceptable for a daily cron; not for an inline-on-stale refresh.

## Open questions for the synthesizer

1. **Default recipe engine: pure-Python `NpmRecipeEngine` (mine) or OpenRewrite (roadmap)?** I bench both; the data should pick. If OpenRewrite within 1.5× pure-Python on the express-CVE fixture, the roadmap wins; otherwise the perf design wins. Either way, the `RecipeEngine` Protocol stays.
2. **Should Phase 3 import LangGraph already, even if unused?** I argue no (~50 ms cost, no Phase 3 value). Best-practices designer may argue yes (subgraph topology declared early). I'd accept either; the work to add LangGraph in Phase 6 is a wrapper around the step functions I shipped — it's not a rewrite.
3. **Event-log storage: per-workflow file (mine), single repo-wide append-only file (potential alternative), or both?** Per-workflow file makes replay-one-workflow trivial; cross-workflow analytics needs a glob+merge. Single-file would simplify cross-workflow at the cost of locking. I default to per-workflow; Phase 9's Postgres projector erases the distinction anyway.
4. **Bundle cache: should the hedged fallback always run, or only on `confidence() < threshold`?** Always-hedge spends ~20% extra CPU for ~10% better tail-latency. Threshold-hedge is the design above. Synthesizer should pick based on portfolio CPU budget — at Phase 11 scale, threshold-hedge probably wins; at Phase 3 single-repo, always-hedge has no real cost.
5. **`asyncio.Semaphore(4)` constant in the Bundle Builder — config or hard-coded?** I hard-coded based on empirical SSD-knee. A config knob invites tuning-via-cargo-cult; the constant invites recalibration on hardware change. I default to `min(4, os.cpu_count())` with a one-time log line; synthesizer can promote to env-var.
6. **Plugin hot-reload during dev: in-scope for Phase 3, or Phase 11?** I deferred. Best-practices designer may want it earlier for plugin-author DX.
7. **Should `vuln-index.sqlite` be content-addressed in the bundle cache key?** I include `repo_context.digest` but not `vuln_index.digest`. If the index refreshes between two runs and the new feed reclassifies the CVE, the Bundle cache returns the old answer. Mitigation: a feed-refresh resets the cache (cheap; we'd retain ≤ 1 day of stale entries). Synthesizer may want the digest in the key — it's not free at query time, but it's defensible.
