# Phase 08 — Hierarchical Planner + pre-rendered hot views: Performance-first design

**Lens:** Performance — throughput, latency, token economy, footprint.
**Designed by:** Performance-first design subagent
**Date:** 2026-05-21

## Lens summary

I optimized for one number: **workflows opened per hour across a portfolio**. Phase 8 introduces the Supervisor, the layer every workflow now passes through before it can do useful work — so the Supervisor's per-workflow overhead multiplies by every repo in the portfolio. The whole design is built to make that overhead *vanish into a cache hit*. Plugin resolution, TCCM composition, and the union of `must_read` slices are all **pure functions of inputs that change only when a probe re-runs** — so I pre-compute them off the gather's tail (the moment the data can change is the only moment to recompute it) and the Supervisor's steady-state job collapses to four Redis `GET`s and one `match`. The routing decision (recipe vs. RAG vs. LLM) is pushed to the cheapest tier that can answer it — a deterministic recipe-existence check that never touches an LLM. The MCP Skills server is a long-lived stdio process with an in-memory skill index, not a fork-per-call. I **explicitly deprioritize**: per-stage MCP topology richness (ADR-0023 is Deferred — one server, in-process, until it hurts), authorization granularity inside the Skills server (Phase 8 is local; identity is Phase 9+), and any speculative multi-region Redis story. I accept extra moving parts (a background pre-render task, a versioned hot-view schema, a warm-set eviction policy) to buy a sub-50ms Supervisor.

## Goals (concrete, measurable)

- **Workflows/hour target:** ≥ 1,200 wph steady-state per worker pool (8 workers), bounded by downstream subgraph wall-clock, *not* by Supervisor/context overhead. The Supervisor itself must never be the throughput ceiling — its per-workflow cost is budgeted at **< 5 ms p95** (warm path).
- **Time-to-PR p95:** Supervisor + context-bundle assembly contributes **≤ 60 ms p95** of the end-to-end budget on the warm path (hot views hit). Cold path (first workflow on a never-seen repo, pre-render miss) ≤ 350 ms — still a rounding error against the 18–110 s downstream.
- **$/PR target:** Phase 8 adds **$0.00** of LLM spend. The Supervisor and hot views are 100% deterministic — no token cost. The routing decision *saves* money: every recipe-route avoids an LLM call a naive planner would have made.
- **Cache hit rate target:** ≥ 97% on hot-view reads in steady state (a view miss only on the first workflow after a probe re-run for that repo, or after a hot-view schema-version bump). ≥ 99% on plugin-resolution results (resolution is repo-stable between gathers).
- **Per-worker memory ceiling:** Supervisor + hot-view client + MCP Skills client adds **≤ 40 MB RSS** to a worker. Redis itself: **≤ 1.5 KB per repo** across the four pre-rendered slices → ~1.5 MB per 1,000 repos, ~150 MB at 100k repos. Bounded and linear.

## Architecture

```
  ┌── GATHER PIPELINE (deterministic; Phase 1–7.5; UNCHANGED) ───────────────┐
  │  Probe Coordinator → ProbeOutput → sanitizer → writer                    │
  │     .codegenie/context/repo-context.yaml  +  raw/*.json                  │
  │                              │                                          │
  │   final step of every gather (ADR-0013): fire HotViewRenderer            │
  └──────────────────────────────┼──────────────────────────────────────────┘
                                 │ asyncio.create_task — does NOT block gather
                                 ▼
  ┌── HotViewRenderer (background asyncio task) ─────────────────────────────┐
  │  pure render(RepoContext, resolved_plugin_chain) → 4 slices:             │
  │    available_skills · entrypoint · risk_flags · confidence_summary       │
  │  + DERIVED: plugin_resolution (cached resolve() result)                  │
  │  + DERIVED: context_bundle_skeleton (TCCM union of must_read slices)     │
  │  writes Redis: HSET repo:{id}:hotviews  (versioned, no TTL)              │
  └──────────────────────────────┼──────────────────────────────────────────┘
                                 ▼
                         ┌───────────────┐
                         │     REDIS     │  single instance, docker-compose
                         │  repo:{id}:*  │  pipelined reads, MGET/HGETALL
                         └───────┬───────┘
                                 │ HGETALL  (one round-trip, <2ms)
   workflow trigger              │
        │                        ▼
        ▼            ┌─────────────────────────────────────────┐
  ┌──────────┐       │  SUPERVISOR  (codegenie.supervisor)      │
  │ Temporal │──────▶│  warm path:                              │
  │  / CLI   │       │   1. HGETALL repo hotviews  (1 RT)       │
  └──────────┘       │   2. plugin_resolution: read cached     │
                     │      ConcreteResolution | Universal      │
                     │   3. ContextBundle: assemble from        │
                     │      skeleton + lazy may_read refs       │
                     │   4. route(): recipe? RAG? LLM?          │
                     │      — deterministic, logged ALWAYS      │
                     │  cold path: miss → resolve() inline,     │
                     │      render synchronously, backfill Redis│
                     └───────────────┬─────────────────────────┘
                                     │ drop payload into plugin subgraph
                                     ▼
                  ┌──────────────────────────────────────────┐
                  │  Plugin subgraph (Phase 6 SHERPA loop)    │
                  │  FallbackTier: recipe → RAG → LLM         │
                  │  (Phase 4 — UNCHANGED; route() picks      │
                  │   the ENTRY tier, FallbackTier still      │
                  │   owns descent on miss)                   │
                  └──────────────────────────────────────────┘

  ┌── MCP SKILLS SERVER (codegenie.mcp.skills) ─────────────────────────────┐
  │  long-lived stdio process · in-memory skill index built once at start   │
  │  tools: list_skills(repo_id) · get_skill(skill_id) · resolve_tccm(...)   │
  │  reads the SAME Redis hot views — never re-scans plugin dirs per call    │
  └─────────────────────────────────────────────────────────────────────────┘
```

The load-bearing move: **everything between "workflow triggered" and "subgraph entered" is a cache lookup in steady state.** Resolution, TCCM composition, and slice-union are pure; their inputs change only on gather; so they are computed exactly once per gather, off the gather's tail, never on the workflow's critical path.

## Components

### Supervisor — `codegenie.supervisor`

- **Purpose:** The planning layer above the state machines. Given a workflow trigger, resolve the plugin, assemble the Context Bundle, make and log the recipe/RAG/LLM routing decision, and drop the payload into the plugin subgraph. It is the per-workflow tollbooth — so it must be a fast toll.
- **Interface:**
  - In: `WorkflowTrigger(repo_id: RepoId, task_class: TaskClassName, cve_id: CveId | None)`.
  - Out: `SupervisorDecision` — a closed sum type: `Dispatched(plugin_id, plugin_version, bundle: ContextBundle, route: RouteDecision)` | `EscalatedToHITL(reason, evidence)`. No `Plugin | None`; the universal-fallback path is a *variant*, statically un-droppable (the resolver already returns this discipline; the Supervisor preserves it).
  - Errors: `SupervisorColdMiss` is *not* an error — it is a logged slow-path branch. `HotViewSchemaVersionMismatch` triggers a synchronous re-render, logged. `RedisUnavailable` degrades to fully-inline resolution (correct, slower) and emits `supervisor.redis.degraded`.
- **Internal design:**
  - **Warm path is branchless and allocation-light.** One `HGETALL repo:{id}:hotviews` (single Redis round-trip, pipelined with the resolution-cache read). Parse the four slices + the cached `plugin_resolution` blob (a pre-serialized `ConcreteResolution`/`UniversalFallbackResolution`). The Supervisor does **zero** plugin-directory walking, **zero** Pydantic re-validation of `plugin.yaml`, **zero** `extends`-chain traversal on the warm path — all of that happened at plugin-load (manifest validation, ADR-0031) and at render time (resolution).
  - **`route()` is a pure function**, `route(RepoContext.recipe_index, cve_record, plugin_chain) -> RouteDecision`. `RouteDecision` is a sum type: `RouteRecipe(recipe_id)` | `RouteRag` | `RouteLlm(reason)`. The decision is *deterministic*: a recipe exists for this `(cve, ecosystem, fix-shape)` ⇒ `RouteRecipe`; no recipe but the solved-example store is non-empty for this fingerprint ⇒ `RouteRag`; neither ⇒ `RouteLlm`. This is **Rule 5 applied** — recipe existence is a lookup, not a judgment; no LLM decides routing. The chosen route is logged on **every** workflow (exit criterion 1) as a typed `RoutingDecided` event.
  - **`route()` picks the *entry* tier; `FallbackTier` (Phase 4) still owns descent.** The Supervisor does not re-implement the recipe→RAG→LLM chain — it pre-selects the cheapest entry point so a recipe-eligible workflow never pays the RAG-retrieval round-trip just to discover a recipe was available. On a recipe *miss at apply time*, `FallbackTier` descends exactly as Phase 4 designed. This keeps Phase 4 untouched (extension by addition) and turns `route()` into a pure throughput optimization: it shaves the RAG embedding+query (~80–150 ms) off every recipe-route workflow.
  - **Cold path** (hot-view miss — first workflow on a fresh repo, or post-schema-bump): resolve inline via the existing `PluginRegistry.resolve`, assemble the bundle, render the four slices synchronously, backfill Redis, then proceed. Logged as `supervisor.cold_path`. Bounded: resolution is ~5 ms, bundle skeleton assembly ~20–40 ms; the cold path is ≤ 350 ms and self-heals (the backfill means the *next* workflow on that repo is warm).
  - **Functional core / imperative shell.** `resolve_decision(trigger, hot_views, registry_snapshot) -> SupervisorDecision` is pure and exhaustively unit-testable with no Redis, no I/O. The shell is `dispatch(trigger)`: Redis read → call core → Temporal/subgraph handoff. This is what makes the warm path benchable in isolation and what keeps a 5 ms p95 claim falsifiable.
- **Tradeoffs accepted:** The Supervisor caches a *derived* artifact (resolution + bundle skeleton) — a second cache to invalidate beyond the four ADR-0013 slices. I accept this because the alternative (resolve + compose-TCCM + union-slices on every workflow) costs 25–50 ms × every workflow × portfolio scale, and resolution is provably gather-stable. The invalidation is *not* a separate concern: the HotViewRenderer recomputes resolution as one more derived slice in the same atomic write, so the resolution cache is exactly as fresh as the four slices. No independent staleness window.

### HotViewRenderer — `codegenie.hotviews.renderer`

- **Purpose:** Pre-compute every expensive lookup the Supervisor and the MCP server would otherwise do inline, the instant the underlying data can change — i.e. as the final step of every gather (ADR-0013).
- **Interface:**
  - In: `RenderRequest(repo_id, repo_context_path)` — fired by the gather pipeline's tail.
  - Out: side effect — `HSET repo:{id}:hotviews {slice}:{version} <json>` for six slices: the four ADR-0013 slices (`available_skills`, `entrypoint`, `risk_flags`, `confidence_summary`) plus two performance-derived slices (`plugin_resolution`, `context_bundle_skeleton`).
  - Errors: render failure emits `hotview.render.failed` and leaves the *prior* version in place (stale-but-correct beats absent) — the next gather retries. A render never blocks or fails the gather (it is a detached `asyncio.create_task`).
- **Internal design:**
  - **Pure render functions.** `render_available_skills(repo_context, plugin_chain) -> AvailableSkillsView` etc. — no I/O, deterministic. Each is independently memoizable and property-testable. The shell does the one `HSET`.
  - **The two derived slices are the throughput payoff.** `plugin_resolution` is the serialized `resolve()` output for the repo's `(languages, build_systems)` against the registered task classes — computed once here, read as bytes by both the Supervisor and the MCP server. `context_bundle_skeleton` is the **union of `must_read` entries across the active plugins' TCCMs**, already composed down the `extends` chain (ADR-0029/0031) — exactly the slice set the roadmap says the hot views derive from. The Supervisor's "assemble the Context Bundle" step becomes "hydrate the skeleton + attach lazy `may_read` references."
  - **Single Redis write per repo per gather, pipelined.** All six slices land in one `HSET` (one round-trip), versioned by a `HOTVIEW_SCHEMA_VERSION` constant. No TTL — invalidation is gather-driven (ADR-0013): every gather either overwrites or is the authority. This means **zero clock-based staleness** and zero background reaper.
  - **Triggered off probe re-runs, batched.** The roadmap says "background asyncio task triggered off probe re-runs." A burst of probe re-runs on one repo (e.g., a multi-file push) coalesces: the renderer debounces 250 ms per `repo_id` and renders once against the final `RepoContext`. This caps render amplification under churn — a hot monorepo that pushes 40 times an hour renders ~40 times, not 40×N-probes times.
- **Tradeoffs accepted:** Pre-rendering does work that *might* be wasted (a repo gathered but never run through a workflow). I accept this: a render is ~5–20 ms of pure CPU and ~1.5 KB of Redis; against the portfolio-scale win of a sub-5ms Supervisor it is free. The roadmap and ADR-0013 mandate gather-tail rendering anyway; I am extending the rendered set by two derived slices, not changing the trigger.

### Hot-view store — Redis (`codegenie.hotviews.store`)

- **Purpose:** The single-digit-millisecond key-value layer between the gather and the agent. ADR-0013's substrate.
- **Interface:** Thin typed wrapper over `redis-py`. `get_hotviews(repo_id) -> HotViewBundle | None` (one `HGETALL`); `put_hotviews(repo_id, bundle)` (one `HSET`). Reads on the workflow path are **read-only and pipelined**; the Supervisor batches its `HGETALL` with the resolution-blob read into a single `pipeline()` flush → one network round-trip total.
- **Internal design:**
  - **One Redis instance, in docker-compose.** ADR-0023 (MCP topology) is *Deferred*; I extend that deferral to Redis sharding. At 100k repos × 1.5 KB the entire hot-view set is ~150 MB — it fits in RAM on a single node with vast headroom. Sharding/replication is a Phase 14+ ops concern; designing it now is speculative complexity that buys nothing this phase.
  - **Hash-per-repo, not key-per-slice.** `HGETALL repo:{id}:hotviews` fetches all six slices in one round-trip. Six separate `GET`s would be six round-trips or one `MGET` with key construction; the hash is the cleanest shape and lets a partial `HSET` update one slice if a future phase needs it.
  - **Versioned keys, evict-on-read mismatch.** Slice field names embed `HOTVIEW_SCHEMA_VERSION`. A worker reading a stale-version field treats it as a miss → cold path → re-render at current version. No migration job; the schema bump is self-healing on first touch. This is the ADR-0013 "versioned views, evicted on read" consequence rendered concretely.
- **Tradeoffs accepted:** Redis is a new operational dependency (one container). ADR-0013 already accepted this and notes Redis is operationally simple vs. Postgres. I do not add persistence/AOF — the hot views are a *cache*, fully reconstructable from the next gather; an empty Redis after a restart is a portfolio-wide cold path that self-heals on first workflow per repo. Skipping AOF saves fsync latency on every write.

### Routing decision — `codegenie.supervisor.routing`

- **Purpose:** Make and log the recipe/RAG/LLM decision on every workflow (exit criterion 1). Pick the cheapest tier that can possibly succeed so no workflow pays for a tier it didn't need.
- **Interface:** `route(recipe_index: RecipeIndex, cve: CveRecord, plugin_chain, store_stats: SolvedExampleStats) -> RouteDecision`. Pure. `RouteDecision = RouteRecipe | RouteRag | RouteLlm`, a discriminated union — the chosen variant *is* the logged record.
- **Internal design:**
  - **Tier ordering is cost-ascending and the decision is a lookup.** A recipe's existence for `(cve fix-shape, ecosystem, build-tool)` is a key-membership test against the plugin's recipe registry (`@register_recipe`-style index, already content-addressed). The solved-example store's non-emptiness *for this fingerprint* is a cheap count query against the Phase 4 RAG store. Neither consults an LLM. `RouteRecipe` if a recipe matches; else `RouteRag` if the store has ≥1 example for the fingerprint; else `RouteLlm(reason="no_recipe_no_example")`.
  - **The decision is advisory to `FallbackTier`, authoritative for logging.** `route()` selects the entry tier; if a recipe-route's recipe turns out to mismatch at apply time, Phase 4's `FallbackTier` descends — and that descent is logged too. The exit criterion ("the chosen path is logged on every workflow") is satisfied by the `RoutingDecided` event *plus* any `RoutingDescended` events; the audit trail shows both the prediction and the outcome.
  - **Why pure + deterministic:** routing on portfolio scale must be reproducible (replay an audit), branchless-cheap (it is on every workflow), and free (Rule 5: a recipe-existence check is plain code). An LLM "router" would cost a token call per workflow — at 1,200 wph that is 1,200 needless LLM calls/hour. Rejected outright.
- **Tradeoffs accepted:** `route()` can mispredict (recipe present in the index but stale/inapplicable) → a recipe-route that descends to RAG/LLM. The cost of a misprediction is one wasted recipe-match attempt (~milliseconds), strictly cheaper than the RAG round-trip it usually saves. Net-positive in expectation; the audit log makes mispredictions measurable and Stage 7 Learning can tune the recipe index.

### MCP Skills server — `codegenie.mcp.skills`

- **Purpose:** Serve Skills (and the TCCM index) to the eventual leaf LLM nodes via MCP stdio — the first concrete piece of the future MCP topology (ADR-0023).
- **Interface:** MCP stdio process. Tools: `list_skills(repo_id) -> SkillManifest[]`, `get_skill(skill_id) -> SkillBody`, `resolve_tccm(task_class, repo_id) -> TccmView`. Contract-pinned by a snapshot test (Phase 8 "MCP server contract tests pin the public interface").
- **Internal design:**
  - **Long-lived process, in-memory skill index built once at startup.** A fork-per-call or scan-plugin-dirs-per-call MCP server would re-pay filesystem + YAML-parse cost on every `list_skills`. Instead: at startup, walk `plugins/*/skills/`, parse all YAML-frontmatter Skills once, build an in-memory index keyed by `(task_class, language, build_tool)`. `list_skills(repo_id)` becomes a dict lookup against the repo's pre-rendered `available_skills` hot view → **the MCP server reads the same Redis hot views the Supervisor does.** It never re-derives "which skills apply to this repo" — that was rendered at gather time.
  - **Stdio, single process, no auth.** ADR-0023 is Deferred and Phase 8 is explicitly local ("prefiguring the eventual MCP topology"). One stdio process, no network listener, no per-agent identity — that is Phase 9+ when Temporal and real identity land. Designing auth now is speculative; the contract snapshot test is the forward-compat guarantee.
  - **`get_skill` bodies are content-addressed and lazily read.** Progressive disclosure (commitment §7): `list_skills` returns *manifests only* (id, frontmatter, digest); the agent calls `get_skill` only for the ones it actually opens. Skill bodies are cached in-process keyed by digest — a skill body changes only when its file changes, so the digest is the cache key and re-reads are eliminated.
- **Tradeoffs accepted:** An in-memory index means a plugin/skill change requires an MCP server restart to pick up (Phase 8 has no hot-reload). Acceptable: plugins are in-tree and change at deploy time, not runtime (ADR-0031 "in-tree-only at adoption"). A long-lived process holds the full skill index in RAM — bounded (~hundreds of small YAML files, single-digit MB) and the alternative (re-scan per call) is the throughput killer.

## Data flow

**One representative warm run — vuln remediation on a previously-gathered Node/npm repo:**

1. **Trigger.** Temporal (or the CLI, pre-Phase-9) fires `WorkflowTrigger(repo_id, "vulnerability-remediation", cve_id)`.
2. **Supervisor warm path.** One pipelined Redis flush: `HGETALL repo:{id}:hotviews`. Returns the six slices including the pre-serialized `plugin_resolution` (a `ConcreteResolution` for `vulnerability-remediation--node--npm`) and the `context_bundle_skeleton`. **No plugin-dir walk, no Pydantic re-validation, no `extends` traversal** — all done at plugin-load and render time. Cost: ~2 ms (one round-trip) + ~1 ms parse.
3. **Bundle hydration.** The Supervisor hydrates the `context_bundle_skeleton` (the TCCM `must_read` union, already composed) into a `ContextBundle`, attaching *lazy references* for `should_read`/`may_read` — those are not fetched now; a subgraph node promotes them on demand (ADR-0030 `may_read` escape hatch). **Parallelism deferred, not extracted:** the bundle skeleton is already materialized; the only deferred work is the `may_read` superset, and deferring it *is* the optimization.
4. **Route.** `route()` checks the recipe index for the CVE's fix-shape: a recipe exists → `RouteRecipe(recipe_id)`. A `RoutingDecided` event is emitted (exit criterion 1). Cost: ~0.5 ms (index lookup).
5. **Dispatch.** `Dispatched(plugin_id, version, bundle, RouteRecipe)` → payload dropped into the Phase 6 SHERPA subgraph with `FallbackTier` entered at the recipe tier — **skipping the RAG embedding+query** the workflow would have paid had it entered at the chain head.
6. **Subgraph runs** (Phase 6 SHERPA loop, Phase 4 `FallbackTier`, Phase 5 gates) — unchanged by Phase 8.
7. **Gather tail (asynchronous, decoupled).** Whenever a probe re-runs for this repo (push, CVE feed), the gather's final step fires `HotViewRenderer` as a detached task. It re-renders all six slices and one `HSET` updates Redis. The *next* workflow on this repo sees fresh views. The workflow in flight is never blocked by — and never waits for — a re-render.

**Where parallelism is extracted:** the HotViewRenderer runs concurrently with — and entirely off the critical path of — every workflow. The render of repo A and the workflow of repo B are independent and concurrent across the worker pool. **Where caches are consulted:** the Supervisor consults Redis (hot views + resolution); the MCP server consults Redis (`available_skills`) and an in-process digest cache (skill bodies); `route()` consults the recipe index and the RAG store-stats. **Where I serialize:** the single `HSET` per gather is one atomic write (all six slices land together — no torn read where resolution is fresh but `risk_flags` is stale); and the Supervisor's `route()` runs after bundle hydration because routing reads recipe applicability that depends on the resolved plugin chain. Both serializations are intrinsic data dependencies, not artificial.

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| Redis unavailable | `redis-py` connection error on Supervisor read | Degrade to fully-inline resolution + bundle assembly (correct, ~30 ms slower); emit `supervisor.redis.degraded`; workflows continue. Redis is a cache, never a system-of-record. |
| Hot-view miss (fresh repo / post-schema-bump) | `HGETALL` returns nil or wrong-version fields | Cold path: resolve + render synchronously, backfill Redis, proceed; emit `supervisor.cold_path`. Self-healing — next workflow on that repo is warm. |
| Stale hot view (probe re-ran, render lagged) | Render is the gather's final step; a window exists only if render failed | Bounded staleness ≤ one gather cycle. `confidence_summary` carries `IndexHealthProbe` output, so a stale-but-served view still surfaces its own staleness honestly (commitment §3). Render-failure emits `hotview.render.failed`; prior version stays (stale-but-correct > absent). |
| HotViewRenderer crash mid-render | Detached task exception handler; no `HSET` issued | Prior version untouched (atomic single-write); next gather retries. The gather itself never fails — render is a detached task. |
| Plugin resolution returns no concrete match | `resolve()` returns `UniversalFallbackResolution` | Supervisor produces `EscalatedToHITL` — a *typed variant*, not an error; un-droppable in `match`. ADR-0031 universal `(*,*,*)` fallback handles it. Logged. |
| `route()` mispredicts (recipe stale) | Recipe-match fails at apply time inside `FallbackTier` | `FallbackTier` descends RAG→LLM as Phase 4 designed; `RoutingDescended` event logged alongside the original `RoutingDecided`. Audit shows prediction vs. outcome; Stage 7 tunes the index. |
| MCP Skills server dead / slow | MCP client timeout in a leaf node | Leaf node degrades to `available_skills` hot view directly (the same data Redis already holds) and logs `mcp.skills.degraded`. The MCP server is an ergonomic layer, not a hard dependency this phase. |
| Redis memory pressure at extreme scale | Redis `INFO memory` / ops alert | Hot views are ~1.5 KB/repo — 100k repos ≈ 150 MB. If a portfolio ever dwarfs this, `maxmemory-policy allkeys-lru` turns Redis into a bounded LRU and evicted repos take the cold path. Correctness preserved; throughput degrades gracefully. |

## Resource & cost profile

- **Tokens/run added by Phase 8:** **0.** The Supervisor, hot views, routing, and MCP server are fully deterministic. Phase 8 adds no LLM call. It *saves* tokens: every `RouteRecipe` is an LLM call a naive planner would have spent.
- **Wall-clock (Supervisor + context-bundle contribution to time-to-PR):**
  - Warm path p50: ~3 ms · p95: ~5 ms · p99: ~9 ms (one Redis round-trip dominates; the rest is parse + pure `route()`).
  - Cold path p50: ~180 ms · p95: ~350 ms (inline `resolve()` ~5 ms + bundle skeleton assembly 20–40 ms + synchronous render 5–20 ms + Redis backfill; the bulk is reading `RepoContext` from disk/object store).
  - Hot:cold cost ratio ≈ **1:70**. With a ≥97% hit rate the *amortized* Supervisor cost is ~13 ms — still ≤ 60 ms of the time-to-PR budget with wide margin.
- **Memory/worker:** Supervisor + hot-view client + MCP client ≈ **≤ 40 MB** added RSS. The MCP Skills server process: ~30–60 MB resident (in-memory skill index, single-digit-MB of YAML + Python overhead).
- **Redis footprint:** ~1.5 KB/repo × 6 slices → ~1.5 MB per 1,000 repos; ~150 MB at 100k repos. Single instance, no AOF, no sharding. Growth is **strictly linear in watched-repo count**, independent of workflow volume.
- **Storage growth:** Phase 8 adds no durable storage (Redis is a reconstructable cache; the `RoutingDecided` events ride the existing event log). The event-log delta is one small typed record per workflow (~200 bytes).
- **Hot-view render cost:** ~5–20 ms pure CPU + one Redis `HSET` per gather per repo, debounced 250 ms under churn. Off the critical path entirely.

## Test plan

"Passes its tests" for Phase 8 means:

- **Supervisor routing tests** (roadmap-mandated). Given a fixture `RepoContext` + skill manifest + recipe index, assert `route()` returns the expected `RouteDecision` variant. Parametrized across: recipe-present, recipe-absent-store-warm, recipe-absent-store-cold. The `RoutingDecided` event is asserted present on **every** path (exit criterion 1 is a test, not a hope).
- **Hot-view cache-invalidation tests** (roadmap-mandated). Re-run a probe → assert the renderer fires → assert the right slices in Redis change and the others don't → assert the next Supervisor read is warm and reflects the new data. A schema-version bump test asserts old-version fields are treated as a miss and re-rendered.
- **MCP server contract tests** (roadmap-mandated). A snapshot test pins `list_skills` / `get_skill` / `resolve_tccm` request/response shapes byte-for-byte. Breaking the contract fails CI.
- **Warm/cold path correctness equivalence.** Property test: for the same inputs, the warm path (Redis-cached resolution) and the cold path (inline `resolve()`) produce the **identical** `SupervisorDecision`. The cache must never change the answer — only the latency.
- **Functional-core purity fence.** AST source-scan asserting `resolve_decision`, `route`, and the `render_*` functions import no I/O modules (mirrors the existing `tests/unit/plugins/test_resolver_purity.py` discipline).
- **Performance regression canary** (`@pytest.mark.bench`, advisory, CI-tracked). A benchmark: 1,000 synthetic warm Supervisor dispatches against a real local Redis, asserting **p95 < 50 ms** for hot-view-served context (exit criterion 2, made a test). A second canary asserts warm-path Supervisor overhead p95 < 5 ms. A regression of >20% on either fails the advisory gate and surfaces a CI annotation — the throughput ceiling stays visible.

## Design patterns applied

| Decision | Pattern applied | Why this pattern here | Pattern not applied (and why) |
|---|---|---|---|
| `route()`, `resolve_decision()`, `render_*()` are pure functions; the Supervisor/renderer shells do all I/O | Functional core, imperative shell | The hot path must be benchable in isolation and memoizable. Pure cores let the warm-path p95<5ms and hot-view-render claims be falsifiable unit tests with zero mocks. Purity *is* the cacheability — a pure `resolve()` is what makes pre-rendering resolution sound. | — |
| Hot views pre-computed at gather tail, served from Redis; resolution + bundle-skeleton are derived slices | Pre-computed read model / event-sourced projection (off the gather as the "event") | The gather is the only moment inputs change; computing the read model exactly then, off the critical path, is the throughput win. The read model is content-addressed (gather-driven invalidation, versioned, no TTL) — so it is never stale-without-knowing-it. | A general-purpose cache with TTL — rejected: clock-based expiry creates a staleness window the gather-tail trigger eliminates entirely. |
| `route()` selects a tier; `FallbackTier` (Phase 4) still owns descent; Supervisor doesn't reimplement the chain | Chain of responsibility (preserved, not rebuilt) + extension by addition | Phase 4's recipe→RAG→LLM chain is correct and tested; Phase 8 adds a *pre-selector* in front of it, editing nothing. The pattern stays; Phase 8 just enters it cheaper. Open/Closed at the file boundary. | Rebuilding routing inside the Supervisor — rejected: duplicates Phase 4, violates extension-by-addition, and a second copy of the chain drifts. |
| `RouteDecision` and `SupervisorDecision` are Pydantic discriminated unions; `EscalatedToHITL` is a variant, not `None` | Tagged union / make illegal states unrepresentable | The "no plugin matched" and "route is LLM" paths must be impossible to silently drop — `match` + `assert_never` forces every dispatch site to handle them (commitment §8, humans always merge). The chosen variant *is* the logged audit record — one type, two jobs. | Boolean flags / `Optional[Plugin]` — rejected: `is_hitl: bool` allows illegal combinations and lets the escalation path be forgotten. |
| MCP Skills server: long-lived stdio process, in-memory index, reads the shared Redis hot views | Registry (in-memory skill index) + shared read model | A fork-per-call or scan-per-call server re-pays filesystem+YAML cost on every request — death at portfolio scale. The index is built once; per-call work is a dict lookup. Reusing the Redis `available_skills` slice means the server never re-derives applicability. | Per-stage MCP topology / per-agent auth (ADR-0023) — deliberately deferred: ADR-0023 is *Deferred*, Phase 8 is local; building four servers + auth now is speculative complexity with no Phase-8 payoff. |
| One Redis instance, hash-per-repo, no sharding, no AOF | Deliberate non-pattern: simplest sufficient store | At 100k repos the entire hot-view set is ~150 MB — single-node RAM with headroom. Sharding/replication is premature pluggability; an LRU eviction policy is the only scale concession and it is one config line. AOF is skipped because the cache is reconstructable — saving an fsync per write. | Redis Cluster / read-replicas — rejected as YAGNI: the data volume does not justify the operational surface this phase. |

## Risks (top 3–5)

1. **The derived-slice cache (resolution + bundle skeleton) drifts from the four ADR-0013 slices.** Mitigation: render *all six* slices in one atomic `HSET` from the same `RepoContext` read — there is no code path that updates one without the others. A torn read is structurally impossible. The risk is a *future* edit that adds an out-of-band update; the cache-invalidation test suite is the guard.
2. **`route()` mispredicts often enough to erode the throughput win.** If recipe indexes are frequently stale, recipe-routes descend to RAG/LLM and the pre-selection saved nothing. Mitigation: the `RoutingDecided` vs. `RoutingDescended` event pair makes the misprediction rate a measured number; if it exceeds ~10% the recipe-index freshness becomes a Stage-7 tuning target. The downside of a misprediction is bounded (one wasted recipe-match) — never worse than not pre-selecting.
3. **Redis becomes a single point of failure for the whole portfolio's warm path.** Mitigation: the degraded path (fully-inline resolution) is *correct*, just ~30 ms slower — a Redis outage degrades throughput, never correctness. But a portfolio-wide cold-path storm after a Redis restart is a real thundering-herd risk; the 250 ms render debounce and the self-healing backfill spread the re-warm load.
4. **Hot-view schema evolution.** When a new task class or plugin adds a slice shape, the `HOTVIEW_SCHEMA_VERSION` bump cold-paths the entire portfolio once. Mitigation: self-healing (evict-on-read-mismatch, no migration job) and the cold path is bounded at ≤350 ms — a one-time portfolio re-warm, not an outage. Still, a synchronized bump across 100k repos is a load spike worth scheduling off-peak.
5. **MCP stdio server lifecycle.** A long-lived stdio process that dies silently strands leaf nodes. Mitigation: leaf nodes degrade to the Redis `available_skills` slice directly (same data); but Phase 9's Temporal envelope is where proper process supervision belongs — Phase 8 ships the degradation path and defers supervision.

## Acknowledged blind spots

- **Authorization.** The MCP Skills server has no auth, no per-agent identity, no scope enforcement. Phase 8 is local-process; this is fine *here* but a security reviewer will rightly flag that ADR-0023's per-stage authorization story is entirely unaddressed. I deprioritized it deliberately — it is Phase 9+ work — but I am not pretending it is solved.
- **Redis durability / multi-instance.** I chose no AOF and a single instance. A security/ops lens would want at least AOF or a replica so a Redis crash does not cold-path the whole portfolio. I traded that for write latency and operational simplicity; the synthesizer should weigh whether the cold-path-storm risk justifies AOF.
- **Hot-view memory at true extreme scale.** My 150 MB-at-100k-repos figure assumes ~1.5 KB/repo. A repo with a huge `risk_flags` set or a long `available_skills` list could blow that. I have not modeled the slice-size distribution's tail — `per_slice_max_bytes` caps are an untaken precaution.
- **Render amplification under pathological churn.** The 250 ms debounce caps it, but a portfolio where thousands of repos all churn continuously could still saturate the render worker pool. I have not sized the renderer's concurrency bound against worst-case portfolio churn.
- **The route()/FallbackTier seam.** I assert `route()` is "advisory, FallbackTier owns descent" — but I have not fully specified what happens if `route()` says `RouteLlm` and the LLM tier is budget-capped (ADR-0025). The interaction with the per-workflow cost cap is under-specified.

## Open questions for the synthesizer

1. **Does the derived-slice cache (resolution + bundle skeleton) belong in the hot views, or is that scope creep on ADR-0013?** ADR-0013 names exactly four slices and says "adding a slice requires a deliberate ADR amendment." My two performance-derived slices are the core throughput mechanism — but they technically need an ADR amendment. The synthesizer must decide: amend ADR-0013, or move resolution-caching to a separate Supervisor-local cache (a second invalidation surface I argued against).
2. **AOF or no AOF on Redis?** Performance says no (fsync latency, reconstructable cache). Security/ops may say yes (avoid portfolio-wide cold-path storm on restart). This is a genuine cross-lens tradeoff.
3. **Should `route()` ever be allowed to *skip* a tier the budget can't afford?** If the per-workflow cost cap (ADR-0025) is already low, `RouteLlm` may be infeasible — should `route()` know about budget and pre-emptively `EscalateToHITL`, or is that the subgraph's job? This couples routing to cost, which I kept separate for purity.
4. **MCP topology now or later.** I ship one stdio server and defer ADR-0023. If the security design wants per-stage servers + auth in Phase 8, the synthesizer must rule on whether that complexity is in-scope for a phase the roadmap explicitly frames as "prefiguring the eventual MCP topology."
5. **Debounce window.** 250 ms render debounce is a guess. The synthesizer (or a later phase) should validate it against real push-frequency data — too short amplifies renders, too long widens the staleness window.
