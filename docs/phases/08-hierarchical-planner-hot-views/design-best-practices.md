# Phase 08 — Hierarchical Planner + pre-rendered hot views: Best-practices design

**Lens:** Best practices — idiomatic, maintainable, conventional, well-tested.
**Designed by:** Best-practices design subagent
**Date:** 2026-05-21

## Lens summary

I optimized for the next engineer reading this code cold: the Supervisor that resolves a plugin, the Bundle Builder that dispatches TCCM derived queries through adapters, the Planner that picks recipe/RAG/LLM, the hot-view renderer, and the Skills MCP server should each read like one obvious thing. Every piece reuses an existing seam — `codegenie.plugins.resolver` already resolves the `(task × language × build-tool)` tuple, `codegenie.tccm` already models manifests and the five derived queries, `codegenie.adapters` already carries `AdapterConfidence`. Phase 8 *wires* those into a Supervisor and adds two genuinely new things — a Redis hot-view layer and an MCP stdio server — and nothing else. I deprioritized raw latency micro-optimization (the design hits the <50ms p95 bar with a boring Redis GET, no clever batching), throughput at portfolio scale (single-process asyncio is fine for Phase 8; Temporal arrives in Phase 9), and any speculative pluggability beyond what ADR-0031/0032 already mandate. Where best practices and exit criteria collide, I surface it (see Risks): the `<50ms p95` bar is a hot-view *read* SLO and I make sure the routing decision never sits in that path.

## Conventions honored

- **No LLM in the gather pipeline.** The hot-view renderer, the Bundle Builder, the Supervisor's plugin resolution, and the MCP Skills server are all deterministic. The *only* LLM call in Phase 8 is the Planner's explicit `llm_fallback` node — a leaf, gated, one node. `import-linter` contracts forbid `anthropic|openai|langgraph|langchain|transformers` from `codegenie.planner.routing`, `codegenie.hotviews`, `codegenie.mcp`, and `codegenie.supervisor` (the routing/rendering/serving code is deterministic; the LLM leaf lives behind a Port).
- **Facts, not judgments.** Hot views pre-render *evidence slices* (`available_skills`, `entrypoint`, `risk_flags`, `confidence_summary`) — never conclusions. The Planner's *routing decision* is a logged judgment, correctly placed in the Planner, not the gather layer (commitment §2.2).
- **Extension by addition — no silent edits.** Phase 8 adds new top-level packages (`codegenie.supervisor`, `codegenie.planner`, `codegenie.hotviews`, `codegenie.mcp`) and reuses `codegenie.plugins`, `codegenie.tccm`, `codegenie.adapters` through their public surfaces. The only edits to shipped code are loud, compiler/fence-policed wiring lines, enumerated in a Phase-8 ADR allowlist on `tests/fence/`. The universal `(*, *, *)` HITL plugin is loaded by the same mechanism as every plugin — no special case in Supervisor code (ADR-0031 §No-match fallback).
- **Honest confidence.** The Bundle Builder reads `IndexHealthProbe` (B2) confidence and degrades SCIP→tree-sitter with a logged downgrade (ADR-0030, ADR-0032). The Planner's routing decision carries the confidence band it routed on.
- **Progressive disclosure.** Hot views index `must_read` slices; the Bundle Builder reads originals via the Context store at decision time. The MCP Skills server serves manifests, not inlined skill bodies.
- **Determinism over probabilism.** Plugin resolution, TCCM expansion, hot-view rendering, and recipe/RAG matching are all deterministic. The Planner reaches the LLM only on a recipe *and* RAG miss.
- **Pydantic state-ledger discipline.** Plugin/TCCM manifests validate via Pydantic at Supervisor startup (ADR-0031 §Schema enforcement); the planner's LangGraph state is a frozen Pydantic model.

## Goals (concrete, measurable)

- **Public API surface (count):** ≤ 22 exported names across 4 new packages — `codegenie.supervisor` (≤5: `Supervisor`, `SupervisorState`, `PluginResolution`, `SupervisorError`, `build_supervisor_graph`), `codegenie.planner` (≤6: `PlannerNode`, `PlannerState`, `RouteDecision`, `PlanningRoute`, `LeafLlmPort`, `PlannerError`), `codegenie.hotviews` (≤6: `HotViewStore`, `HotViewKey`, `HotViewSlice`, `render_hot_views`, `HotViewRenderer`, `HotViewError`), `codegenie.mcp` (≤5: `SkillsMcpServer`, `serve_skills_stdio`, `SkillManifestTool`, `McpServerError`, `mcp_server_contract`).
- **Test coverage target:** ≥ 90% line on the four new packages (above the repo's 85% gate); 100% branch on the Planner routing decision and the hot-view cache-invalidation matcher — the two exit-criteria-bearing functions.
- **Cyclomatic complexity ceiling per module:** ≤ 8 per function (`ruff` `C901`); the Planner routing function and the Bundle Builder dispatcher are the only functions allowed to approach it, and both stay table-driven.
- **Number of net-new top-level packages:** 4 (`codegenie.supervisor`, `codegenie.planner`, `codegenie.hotviews`, `codegenie.mcp`). The Bundle Builder lives in the *existing* `codegenie.tccm` package (it consumes TCCM models and derived queries — that is its home).
- **Lines of plain Python vs framework-coupled code (rough ratio):** ~80/20. Plugin resolution, TCCM expansion, hot-view rendering, MCP tool handlers, and the routing decision are plain Python + Pydantic. LangGraph coupling is confined to two thin builder functions (`build_supervisor_graph`, the plugin subgraph wiring) — ~20% of new lines. redis-py touches one module (`HotViewStore`); the `mcp` SDK touches one module (`SkillsMcpServer`).

## Architecture

```
                       codegenie remediate <repo> --cve <id>          (Phase 3/6 CLI — UNCHANGED)
                                       │
                                       ▼
   ┌──────────────────────────────────────────────────────────────────────────────┐
   │ codegenie.supervisor.Supervisor          [NEW — Layer-1 Hierarchical Planner]  │
   │  build_supervisor_graph() → a tiny LangGraph: resolve → build_bundle → dispatch│
   │                                                                                │
   │   (1) resolve   ── codegenie.plugins.resolver  [REUSED — Phase 3/7]            │
   │                    resolve(task, languages, build_systems) → PluginResolution  │
   │                    walks `extends` chain · Pydantic-validated · (*,*,*) fallbk │
   │   (2) build_bundle ─ codegenie.tccm.BundleBuilder  [NEW — in existing pkg]     │
   │                    union TCCMs over resolved chain → expand derived queries    │
   │                    through plugin adapters (ADR-0032) → ContextBundle          │
   │                    reads IndexHealthProbe confidence → SCIP↘tree-sitter degrade│
   │   (3) dispatch  ── conditional_edge into resolved plugin's subgraph            │
   └────────────────────────────────────┬──────────────────────────────────────────┘
                                        │  ContextBundle as initial subgraph state
                                        ▼
   ┌──────────────────────────────────────────────────────────────────────────────┐
   │ plugin subgraph  (e.g. plugins/vulnerability-remediation--node--npm/subgraph/) │
   │                                                                                │
   │   codegenie.planner.PlannerNode          [NEW — the recipe/RAG/LLM router]     │
   │     route(bundle, hot_views) → RouteDecision(route=RECIPE|RAG|LLM, reason,     │
   │                                              confidence)                       │
   │       · RecipeMatchPort.match(bundle)        → recipe hit?  → RECIPE            │
   │       · SolvedExampleRagPort.retrieve(bundle)→ RAG hit?     → RAG              │
   │       · else                                                → LLM (LeafLlmPort)│
   │     emits planner.route.decided audit event EVERY workflow (exit criterion 1)  │
   └────────────────────────────────────┬──────────────────────────────────────────┘
                                        │ reads (never computes inline)
                                        ▼
   ┌──────────────────────────────────────────────────────────────────────────────┐
   │ codegenie.hotviews.HotViewStore          [NEW — Redis client wrapper]          │
   │   get(HotViewKey(repo, slice)) → HotViewSlice            (<50ms p95 — crit 2)  │
   │   keys: hotview:{repo_id}:{slice_name}:{schema_version}                         │
   │                                                                                │
   │ codegenie.hotviews.HotViewRenderer       [NEW — background asyncio task]        │
   │   on probe re-run → render_hot_views(repo, repo_context, active_tccms)          │
   │   slices = union of must_read across active plugins' TCCMs (ADR-0029)           │
   │   gather-driven invalidation, NO TTL (ADR-0013)                                 │
   └────────────────────────────────────────────────────────────────────────────────┘

   ┌──────────────────────────────────────────────────────────────────────────────┐
   │ codegenie.mcp.SkillsMcpServer            [NEW — local MCP stdio process]        │
   │   serve_skills_stdio()  — `mcp` SDK, stdio transport                           │
   │   tools: list_skills(repo) · get_skill(skill_id) — serve manifests, not bodies │
   │   reads codegenie.skills loader [REUSED]; contract-pinned by mcp_server_contract│
   └────────────────────────────────────────────────────────────────────────────────┘

   docker-compose.yml  +redis:7-alpine   (the one new runtime service)
```

The shape is deliberately flat: a Supervisor LangGraph with **three nodes** (resolve, build_bundle, dispatch), a Planner that is **one node** inside each plugin subgraph, a hot-view layer that is **one store + one renderer**, and an MCP server that is **one process with two tools**. No orchestration framework beyond the LangGraph already in use since Phase 6.

## Components

### `Supervisor` — Layer-1 Hierarchical Planner

- **Purpose.** Given a workflow (task class + repo), resolve the matching plugin, build the Context Bundle, and dispatch into the plugin's subgraph. The "reads intent; routes into the right subgraph" persona from `design.md §3.1`.
- **Public interface.**
  ```python
  def build_supervisor_graph(
      *,
      plugin_registry: PluginRegistry,
      bundle_builder: BundleBuilder,
      checkpointer: BaseCheckpointSaver | None = None,
  ) -> CompiledStateGraph: ...

  class SupervisorState(BaseModel):           # frozen LangGraph state
      model_config = ConfigDict(frozen=True)
      workflow_id: WorkflowId
      task_class: TaskClassId
      repo_id: RepoId
      resolution: PluginResolution | None = None
      bundle: ContextBundle | None = None

  class PluginResolution(BaseModel):          # the typed resolution result
      model_config = ConfigDict(frozen=True)
      primary: PluginId
      chain: tuple[PluginId, ...]             # extends chain, root→leaf
      matched_by: Literal["concrete", "wildcard", "universal_fallback"]
  ```
- **Internal design.** A LangGraph `StateGraph` with three nodes and two edges — the smallest graph that is still a graph (idiomatic LangGraph: a Supervisor *is* a graph node per `design.md §1`). Plugin resolution is **delegated entirely** to the already-shipped `codegenie.plugins.resolver.resolve(...)` — Phase 8 does not re-implement matching, wildcard precedence, or `extends`-chain walking; it calls the existing function and wraps the result in `PluginResolution`. The `matched_by` discriminator makes "we fell to the universal HITL plugin" a *typed, logged* outcome, not a silent default (ADR-0031 §No-match fallback; anti-pattern: tag-and-dispatch without a tagged union). The `dispatch` node is a LangGraph `conditional_edge` keyed on `resolution.primary` — the plugin registry maps `PluginId → compiled subgraph`. **Composition over inheritance:** the Supervisor holds a `PluginRegistry` and a `BundleBuilder`; it subclasses nothing.
- **Dependencies.** `langgraph` (already a runtime dep since Phase 6 — the planner subgraph framework); `pydantic` (state model); `codegenie.plugins` (resolver, registry — reused). No new third-party dep.
- **Where it lives.** `src/codegenie/supervisor/` — `graph.py` (builder), `state.py` (`SupervisorState`, `PluginResolution`), `errors.py`.
- **Tradeoffs accepted.** A three-node graph is arguably overkill versus a plain async function. I keep it a graph because (a) Phase 9 wraps each LangGraph step in a Temporal Activity — a graph now is the seam Phase 9 needs, and (b) `design.md §1` is explicit that the Supervisor is a LangGraph node. The cost is ~30 lines of builder boilerplate. Accepted: it buys forward-compatibility with no cleverness.

### `BundleBuilder` — TCCM expansion + adapter-routed derived queries

- **Purpose.** Turn the resolved plugin chain's unioned TCCM into a `ContextBundle` — the worker subgraph's initial context — by expanding `must_read`/`should_read` derived queries through the plugin's language search adapters (ADR-0029, ADR-0030, ADR-0032).
- **Public interface.**
  ```python
  class BundleBuilder:
      def __init__(self, *, adapter_dispatcher: AdapterDispatcher,
                   context_store: ContextStore) -> None: ...
      def build(self, resolution: PluginResolution, repo_context: RepoContext,
                workflow_vars: WorkflowVars) -> ContextBundle: ...

  class ContextBundle(BaseModel):
      model_config = ConfigDict(frozen=True)
      slices: Mapping[str, BundleSlice]            # repo_context_keys + globs
      derived: Mapping[str, DerivedResult]         # named query → file set + provenance
      provenance: BundleProvenance                 # which TCCM, included/deferred, downgrades
      truncations: tuple[Truncation, ...]          # max_files / budget-cap hits, logged
  ```
- **Internal design.** Lives in the *existing* `codegenie.tccm` package — it is the consumer of `TCCM` and the five `DerivedQuery` variants already modeled in `codegenie/tccm/queries.py`. The derived-query dispatch is a **table-driven** map `DerivedQuery variant → adapter primitive` (ADR-0030's five primitives), no `if/elif` ladder — each `DerivedQuery` is already a Pydantic discriminated union, so dispatch is `match query: case ScipRefsQuery(): ...`, exhaustive and `mypy`-checked. Adapter routing is delegated to an `AdapterDispatcher` that walks the resolved `extends` chain and picks the last-registered adapter per primitive (ADR-0031 §Inheritance, ADR-0032 §Dispatch) — Phase 8 *uses* this; the dispatcher contract is ADR-0032's. **Graceful degradation** is explicit: before issuing a `scip.refs` call the builder reads `IndexHealthProbe` confidence from `confidence_summary`; if below the TCCM-declared threshold it uses the declared `fallback` query and records a `Downgrade` in `provenance` (ADR-0032 §Graceful degradation). **Functional core / imperative shell:** TCCM-union, query-table lookup, and budget arithmetic are pure functions; the only impure surface is `context_store` reads and adapter calls, both injected.
- **Dependencies.** `pydantic`; `codegenie.tccm` (home package — `TCCM`, `DerivedQuery`); `codegenie.adapters` (`AdapterConfidence`); `codegenie.plugins` (`AdapterDispatcher` from the resolver result). No new third-party dep.
- **Where it lives.** `src/codegenie/tccm/bundle.py` (`BundleBuilder`, `ContextBundle`, `BundleProvenance`, `BundleSlice`, `DerivedResult`, `Truncation`). It belongs *in* `codegenie.tccm` because it is the manifest's consumer — putting it in a new package would split a cohesive concept.
- **Tradeoffs accepted.** The Bundle Builder is the most complex new function (the derived-query dispatch). I keep it under the complexity ceiling by making dispatch a `match` over the already-typed union — the complexity is in the *number* of cases (five), not in nesting. I deprioritize caching derived-query *results* in Phase 8 (ADR-0030 notes they *could* live in hot views) — Phase 8 caches only the four named slices ADR-0013 mandates; derived-query caching is a clean later addition and adding it now would be premature.

### `PlannerNode` — recipe / RAG / LLM routing

- **Purpose.** Inside the dispatched plugin's subgraph, decide whether this workflow is handled by a deterministic recipe, by solved-example RAG, or by LLM-from-scratch — and **log the decision on every workflow** (exit criterion 1). The `recipe_match → solved_example_rag → llm_fallback` chain of ADR-0011, rendered as one node.
- **Public interface.**
  ```python
  class PlanningRoute(StrEnum):
      RECIPE = "recipe"
      RAG = "rag"
      LLM = "llm"

  class RouteDecision(BaseModel):
      model_config = ConfigDict(frozen=True)
      route: PlanningRoute
      reason: str                              # human-readable: "recipe lodash-bump matched"
      confidence: Confidence                   # Literal["high","medium","low"]
      candidates_considered: tuple[str, ...]    # audit: what was tried before the hit

  class PlannerNode:
      def __init__(self, *, recipe_port: RecipeMatchPort,
                   rag_port: SolvedExampleRagPort,
                   llm_port: LeafLlmPort) -> None: ...
      async def route(self, bundle: ContextBundle,
                      hot_views: HotViewStore) -> RouteDecision: ...
  ```
- **Internal design.** A **chain of responsibility** (the GoF pattern ADR-0011 already describes prose-wise): try recipe, then RAG, then LLM — first hit wins, fallthrough is the LLM. Implemented as a plain ordered `tuple` of `(PlanningRoute, port-callable)` pairs iterated in order — *not* a class hierarchy, *not* a registry (there are exactly three steps, fixed by ADR-0011; a registry here would be premature pluggability). The three collaborators are **Ports** (`Protocol` classes — hexagonal architecture): `RecipeMatchPort`, `SolvedExampleRagPort`, `LeafLlmPort`. `LeafLlmPort` is the *only* LLM seam in Phase 8 — its concrete adapter (Agents SDK, per ADR-0020) is injected, so the routing logic itself is LLM-free and unit-testable with a fake port. The decision is a frozen `RouteDecision` with `route` as a `StrEnum` sum type — the chosen path is *data*, logged via the `planner.route.decided` audit event before the node returns. The node consults hot views (`available_skills`, `risk_flags`) for cheap reads; it never does an MCP roundtrip or a graph query inline (that is the Bundle Builder's job, done upstream).
- **Dependencies.** `pydantic`; `codegenie.hotviews` (the store); the three ports are defined here as `Protocol`s — no concrete LLM/RAG dependency in this package. The `RecipeMatchPort` adapter reuses Phase 3's recipe engine; `SolvedExampleRagPort` is stubbed in Phase 8 (the KG arrives in Phase 11) and returns "no hit" — honestly, a `NullRagPort`, so the chain is complete and the LLM fallback is exercised. Documented as a deliberate stub, not a hidden gap.
- **Where it lives.** `src/codegenie/planner/` — `routing.py` (`PlannerNode`, `RouteDecision`, `PlanningRoute`), `ports.py` (the three `Protocol`s), `errors.py`.
- **Tradeoffs accepted.** Phase 8's RAG port is a null implementation — every non-recipe workflow routes to LLM. This is correct for Phase 8 (KG is Phase 11) and the chain shape is right; the cost is that the RAG *branch* is only exercised by a fake port in tests until Phase 11. I surface this rather than pretend RAG works. The routing decision is `O(1)` port calls — recipe match is the only potentially slow one and it reads the Bundle, already in memory.

### `HotViewStore` + `HotViewRenderer` — pre-rendered Redis hot views

- **Purpose.** Serve the four agent-context slices (`available_skills`, `entrypoint`, `risk_flags`, `confidence_summary`) from Redis in <50ms p95 (exit criterion 2); re-render them as a background task when a probe re-run changes the underlying `RepoContext` (ADR-0013).
- **Public interface.**
  ```python
  class HotViewKey(BaseModel):                  # typed key — no f-string key-building at call sites
      model_config = ConfigDict(frozen=True)
      repo_id: RepoId
      slice_name: HotViewSliceName              # Literal of the four slices
      schema_version: int
      def redis_key(self) -> str: ...           # "hotview:{repo}:{slice}:v{n}"

  class HotViewStore:
      def __init__(self, *, redis: Redis, schema_version: int) -> None: ...
      async def get(self, repo: RepoId, slice_name: HotViewSliceName) -> HotViewSlice | None: ...
      async def get_all(self, repo: RepoId) -> Mapping[HotViewSliceName, HotViewSlice]: ...

  async def render_hot_views(                   # the background-task entry point
      repo: RepoId, repo_context: RepoContext,
      active_tccms: Sequence[TCCM], store: HotViewStore,
  ) -> RenderReport: ...
  ```
- **Internal design.** `HotViewStore` is a **thin wrapper over `redis-py`** — `get`/`get_all`/`put` and nothing else. Keys are built by `HotViewKey.redis_key()`, never by ad-hoc f-strings at call sites (stringly-typed-key anti-pattern killed; the schema version is *in* the key so a slice-shape change evicts on read per ADR-0013). The four slices are a closed `Literal` (`HotViewSliceName`), not free strings. **The renderer is a pure function** (`render_hot_views` computes the slice values from `RepoContext` + the union of `must_read` across `active_tccms` — ADR-0029) plus a thin write loop; "which slices to render" is *derived from TCCM aggregation*, not a hand-curated list (ADR-0013 §Consequences, ADR-0029). It runs as a **background `asyncio` task** triggered off the gather's probe-re-run completion (the existing continuous-gather dispatcher fires it as the gather's final step, per ADR-0006/ADR-0013 — "no time window where the gather is fresh but the views are stale"). Invalidation is **gather-driven, no TTL** (ADR-0013): each render either overwrites or deletes; a separate `invalidates(probe_outputs) → set[HotViewSliceName]` pure function maps which probes feed which slices, so a probe re-run re-renders exactly the affected slices — and that mapping is the unit under the cache-invalidation tests.
- **Dependencies.** `redis-py` (the one new runtime client lib — boring, ubiquitous, well-supported); `pydantic`; `codegenie.tccm` (`TCCM` for the `must_read` union). `redis:7-alpine` added to `docker-compose.yml`.
- **Where it lives.** `src/codegenie/hotviews/` — `store.py` (`HotViewStore`, `HotViewKey`), `renderer.py` (`render_hot_views`, `HotViewRenderer`, the `invalidates` matcher), `slices.py` (`HotViewSlice`, `HotViewSliceName`), `errors.py`.
- **Tradeoffs accepted.** Redis is a new service to operate. ADR-0013 already accepted this ("Redis is operationally simple compared to Postgres") and Phase 9 adds Postgres anyway. The store has no in-process LRU in front of Redis — a single Redis `GET` over a local socket is already well inside 50ms p95; adding a process-local cache would be a premature optimization and a second invalidation surface. Accepted: one cache, one invalidation story.

### `SkillsMcpServer` — local MCP stdio Skills server

- **Purpose.** Serve Skill manifests to the planner over MCP, as a local stdio subprocess — the first concrete piece of the eventual MCP topology (ADR-0023, currently *Deferred*; Phase 8 starts the Skills server only, the smallest committable slice).
- **Public interface.**
  ```python
  async def serve_skills_stdio(*, skills_registry: SkillsRegistry) -> None: ...

  class SkillsMcpServer:                        # the testable core, transport-agnostic
      def __init__(self, *, skills_registry: SkillsRegistry) -> None: ...
      def list_skills(self, repo: RepoId) -> list[SkillManifest]: ...
      def get_skill(self, skill_id: SkillId) -> SkillManifest: ...

  MCP_SKILLS_CONTRACT: Final[McpServerContract]  # the pinned public tool surface
  ```
- **Internal design.** Two MCP tools — `list_skills` and `get_skill` — registered on an `mcp` SDK `Server` running the **stdio transport** (the roadmap-named mode). The MCP-protocol wiring (`serve_skills_stdio`) is a *thin shell* around `SkillsMcpServer`, a plain class with two methods that take/return Pydantic models — so the contract tests exercise `SkillsMcpServer` directly without spawning a subprocess, and one integration test exercises the real stdio roundtrip. Skill data comes from the **existing `codegenie.skills` loader** — Phase 8 does not re-implement skill loading; it serves what is already loaded. Per progressive disclosure (commitment §2.7) the tools return *manifests* (id, frontmatter, path), never inlined skill bodies. The public tool surface is pinned by `MCP_SKILLS_CONTRACT`, a `Final` declared shape — the MCP contract test asserts the live server's advertised tools byte-match it (the probe-contract snapshot idiom, ADR-0007 style).
- **Dependencies.** `mcp` (the official Python SDK, stdio mode — boring, the standard); `pydantic`; `codegenie.skills` (reused loader). No custom protocol code.
- **Where it lives.** `src/codegenie/mcp/` — `skills_server.py` (`SkillsMcpServer`, `serve_skills_stdio`), `contract.py` (`MCP_SKILLS_CONTRACT`, `McpServerContract`), `errors.py`.
- **Tradeoffs accepted.** ADR-0023 (MCP topology) is *Deferred* — single-global vs per-stage is unresolved. Phase 8 sidesteps the decision by shipping *only* the Skills server as one stdio process; it does not commit to the topology. The cost: when the topology is decided (post-Phase 11), the Context/KG/Policy MCP servers are added then. This is the right call — building four MCP servers now would commit an undecided ADR. Surfaced as an open question.

## Data flow

One representative end-to-end run: a vuln-remediation workflow fires on a Node+npm repo with a fresh `RepoContext` already gathered.

1. **Workflow start.** The CLI (Phase 3, unchanged) hands the Supervisor a `SupervisorState(workflow_id, task_class="vulnerability-remediation", repo_id)`.
2. **resolve node.** The Supervisor calls `codegenie.plugins.resolver.resolve("vulnerability-remediation", repo_context.languages, repo_context.build_systems)`. The resolver matches `vulnerability-remediation--node--npm`, walks its `extends` chain (`vulnerability-remediation--node--*` → `vulnerability-remediation--*--*`), validates every manifest via Pydantic. The Supervisor wraps the result as `PluginResolution(primary=..., chain=(...), matched_by="concrete")`. *Where the convention shines:* had no plugin matched, `matched_by` would be `"universal_fallback"` — a typed value, logged — and the dispatched subgraph would be the universal HITL flow. No silent failure (ADR-0031).
3. **build_bundle node.** `BundleBuilder.build(resolution, repo_context, workflow_vars)` unions the `must_read`/`should_read` bands across the resolved TCCM chain. For the `affected_callsites` derived query (`scip.refs(...)`), it first reads `IndexHealthProbe` confidence from `confidence_summary`; SCIP is fresh, so it routes `scip.refs` through the chain's `NodeScipAdapter` (ADR-0032 dispatch — last-registered wins). The query returns 12 files, all within `max_files`; no truncation. The `ContextBundle` carries `slices`, `derived`, and a `BundleProvenance` recording "scip used, confidence high, 0 downgrades." *Where the convention shines:* the provenance is a typed audit record — an engineer can later trace exactly which queries fed the agent.
4. **dispatch.** A `conditional_edge` keyed on `resolution.primary` drops the `ContextBundle` into the `vulnerability-remediation--node--npm` subgraph as initial state.
5. **PlannerNode.route.** Inside the subgraph, `PlannerNode.route(bundle, hot_views)` reads `available_skills` and `risk_flags` from `HotViewStore.get(...)` — two Redis `GET`s, ~3ms total, well inside the 50ms SLO. It runs the chain: `RecipeMatchPort.match(bundle)` finds a `lodash@4.17.20` bump recipe → **hit**. `RouteDecision(route=RECIPE, reason="recipe lodash-transitive-bump matched", confidence="high", candidates_considered=("recipe",))` is built, the `planner.route.decided` audit event is emitted (**exit criterion 1 satisfied — every workflow logs the chosen path**), and the node returns. The LLM port is never touched.
6. **Subgraph continues.** The plugin's recipe path (Phase 3/6 logic) takes over — unchanged.
7. **Background, decoupled.** Earlier, when the gather re-ran on this repo's last push, the continuous-gather dispatcher fired `render_hot_views(repo, repo_context, active_tccms)` as its final step. The renderer computed the four slices from the union of `must_read` across the active plugins' TCCMs and wrote them to Redis under versioned keys. *Where the convention shines:* the Planner's step 5 reads pre-computed evidence — it never does an expensive lookup inline (ADR-0013), and the slices it reads are exactly the `must_read` aggregate (ADR-0029), not a hand-curated list.

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| No plugin matches `(task × lang × build)` | `resolver.resolve` returns the `(*, *, *)` plugin; `PluginResolution.matched_by == "universal_fallback"` | Dispatch into the universal HITL subgraph; emit `requires_human_review`; `interrupt()`. Typed, logged — never silent (ADR-0031). |
| Malformed `plugin.yaml` / `tccm.yaml` | Pydantic `ValidationError` at Supervisor startup | Supervisor refuses to start, names the file + field (ADR-0031 §Schema enforcement). Fail-fast, not fail-at-workflow-time. |
| Unresolvable adapter import path | `AdapterDispatcher` import check at plugin load | Fail-fast at startup with the broken `module:Class` path named (ADR-0032). |
| SCIP index stale (`IndexHealthProbe` low confidence) | `BundleBuilder` reads `confidence_summary` before `scip.refs` | Use the TCCM-declared `fallback` query (tree-sitter `reverse_lookup`); record a `Downgrade` in `BundleProvenance` (ADR-0030/0032). Honest degradation. |
| Derived query exceeds `max_files` | `BundleBuilder` budget arithmetic | Truncate; append a `Truncation` to `ContextBundle.truncations` with the query name and counts. Logged, not silent (ADR-0030). |
| Redis unreachable on `HotViewStore.get` | `redis-py` `ConnectionError` → caught, wrapped as `HotViewError` | Planner falls through to a direct Context-store read (slower, correct — ADR-0013 §Reversibility: "turning off pre-rendering reverts to slower-but-correct"). The fallback is logged so the Redis outage is visible, not masked. |
| Hot view stale (renderer crashed mid-run) | `render_hot_views` returns a `RenderReport` with `failed_slices`; schema-version mismatch on read evicts | Crashed render leaves the *old* (consistent) slice or no slice; a no-slice read triggers the direct-read fallback above. Versioned keys mean a *shape* change can never serve a stale shape. |
| LLM leaf call fails / times out | `LeafLlmPort` adapter raises `PlannerError` | The plugin subgraph's existing retry/HITL policy (Phase 6) handles it — Phase 8 adds no new retry logic; routing just reports the route it chose. |
| MCP server subprocess dies | Client-side `mcp` SDK transport error | The planner's skill lookups fall through to a direct `codegenie.skills` loader read (the server wraps the same loader). Logged. |

All Phase-8 error types descend from the existing `codegenie.errors.CodegenieError` base — `SupervisorError`, `BundleBuilderError` (in `codegenie.tccm`), `PlannerError`, `HotViewError`, `McpServerError` — each a small typed hierarchy. No bare `except Exception`; no exception soup.

## Resource & cost profile

- **LLM spend, Phase-8-introduced:** `$0.00` on the routing/rendering/serving code. The *only* LLM call is the Planner's `llm_fallback` leaf — and only on a recipe-and-RAG miss (ADR-0011). With Phase 8's null RAG port, every non-recipe workflow reaches the LLM; this is the expected Phase 8 cost shape and is unchanged from Phase 6's planning cost — Phase 8 adds routing, not new LLM calls.
- **Hot-view read latency:** a single `redis-py` `GET` over a local-network socket is ~0.3–1ms; `get_all` (4 keys, one pipeline) ~1–2ms. The <50ms p95 exit criterion has ~25× headroom — met with boring tech, no batching cleverness. *Where the convention costs nothing:* the Pydantic deserialization of a `HotViewSlice` adds ~0.1ms — immaterial against the SLO, and it buys a typed, validated slice instead of a raw dict.
- **Hot-view memory:** four slices × watched repos. Each slice is small (skill manifests, a risk-flag list, an entrypoint string, a confidence table) — order 1–10 KB. At 1,000 watched repos: ~10–40 MB Redis. Bounded and trivial (ADR-0013 accepted this).
- **Bundle Builder latency:** TCCM union + table-driven dispatch is microseconds; the cost is the adapter calls — tree-sitter `reverse_lookup` ~100ms, `scip.refs` single-digit seconds (ADR-0030's published figures). This sits *upstream* of the Planner, outside the 50ms hot-view SLO — the SLO is a *read* SLO and the design keeps graph queries out of it.
- **Where the convention costs performance:** the three-node Supervisor LangGraph adds ~1–2ms of framework overhead versus a plain async function. Accepted: it is the Phase-9 Temporal-Activity seam, and `design.md §1` mandates the Supervisor-as-graph shape. Reading clarity and forward-compatibility win over 2ms.
- **New runtime deps:** `redis` (client lib + `redis:7-alpine` service), `mcp` (SDK). Two, both boring and ubiquitous. `langgraph`/`pydantic` already present.

## Test plan

The pyramid: many fast unit tests, fewer integration, two e2e.

- **Unit (the base — ~70% of new tests).**
  - `codegenie.planner.routing`: **100% branch coverage on `PlannerNode.route`** — recipe-hit, RAG-hit, RAG-miss→LLM, recipe-miss→RAG-miss→LLM. Fake `RecipeMatchPort`/`SolvedExampleRagPort`/`LeafLlmPort` (the ports make this trivial — no LLM, no KG). Each test asserts the `RouteDecision` *and* that the `planner.route.decided` audit event fired (exit criterion 1 is an *every-workflow* claim — the test encodes that intent, per global Rule 9).
  - `codegenie.hotviews.renderer`: the **`invalidates(probe_outputs) → set[HotViewSliceName]` matcher** at 100% branch — given a probe re-run, exactly the right slices invalidate (the roadmap-named "cache-invalidation tests"). `render_hot_views` as a pure function: fixture `RepoContext` + fixture TCCMs → expected slice values; assert the slice set equals the `must_read` union (ADR-0029).
  - `codegenie.hotviews.store`: `HotViewKey.redis_key()` formatting, schema-version eviction on read, the Redis `ConnectionError` → `HotViewError` wrap. Redis itself faked with `fakeredis` so the unit tier needs no live service.
  - `codegenie.tccm.bundle`: the derived-query dispatch table — one test per `DerivedQuery` variant; the SCIP-low-confidence → declared-fallback path; `max_files` truncation produces a `Truncation` record.
  - `codegenie.supervisor`: `resolve` wraps the resolver result; `matched_by` is `"universal_fallback"` when the resolver returns the `(*,*,*)` plugin.
- **Integration (~25%).**
  - Supervisor graph end-to-end against a fixture plugin registry: workflow in → `ContextBundle` out → correct subgraph dispatched. One run for a concrete-match repo, one for a no-match repo (asserts HITL dispatch).
  - `HotViewStore` against a **real Redis** (the docker-compose `redis:7-alpine`, marked `integration`): write via `render_hot_views`, read back, assert <50ms (a soft assertion — the e2e owns the p95 claim).
  - MCP Skills server: the **contract test** spawns the real stdio server, lists tools, asserts they byte-match `MCP_SKILLS_CONTRACT` (the roadmap-named "MCP server contract tests pin the public interface"); `get_skill` / `list_skills` roundtrip returns valid `SkillManifest`s.
- **e2e (~5%, two tests, `@pytest.mark.phase08_e2e`).**
  - **Routing e2e:** a fixture vuln-remediation workflow through the full Supervisor → Planner path; assert the `planner.route.decided` event is in the audit log (exit criterion 1).
  - **Hot-view latency e2e:** 200 sequential `HotViewStore.get_all` calls against live Redis after a real `render_hot_views`; assert **p95 < 50ms** (exit criterion 2, measured, not asserted-by-faith — global Rule 12).
- **Golden.** `tests/golden/hotviews/{repo}/` — a gathered `RepoContext` + the expected four rendered slices; the renderer is deterministic, so a golden diff catches accidental shape change. TCCM-union goldens for the Bundle Builder.
- **Property.** `render_hot_views` idempotence — rendering twice over the same `RepoContext` yields byte-identical Redis values (Hypothesis over generated `RepoContext` slices). `BundleBuilder` budget invariant — no `ContextBundle` ever exceeds the TCCM's `max_files`/`max_tokens` cap, for any generated derived-query result set.
- **Fence.** A Phase-8 `tests/fence/` entry: the enumerated wiring-line allowlist (the new package imports, the `docker-compose.yml` redis service, the `pyproject.toml` `redis`/`mcp` rows) — any edit outside it fails. `import-linter` contracts: `codegenie.hotviews`, `codegenie.mcp`, `codegenie.supervisor`, `codegenie.planner.routing` may not import an LLM SDK.

## Design patterns applied

| Decision | Pattern applied | Why this pattern here | Pattern not applied (and why) |
|---|---|---|---|
| `PlannerNode` tries recipe → RAG → LLM, first hit wins | **Chain of responsibility / Pipeline** | ADR-0011 *is* this pattern in prose; three fixed, ordered steps with a fallthrough. A plain ordered `tuple` of `(route, port)` pairs, iterated. | **Registry** — rejected: exactly three steps, fixed by ADR-0011; a `@register_planning_step` decorator for 3 known steps is premature pluggability (the toolkit's named sin). |
| `RouteDecision.route`, `PluginResolution.matched_by`, `HotViewSliceName`, `PlanningRoute` | **Tagged union / sum type for state**; **Newtype** for every domain ID (`RepoId`, `PluginId`, `WorkflowId`, `SkillId` — already in `codegenie.types.identifiers`) | The chosen planning path and the match kind are *states*, not strings — modeling them as `StrEnum`/`Literal` makes "we hit the universal fallback" a typed, exhaustively-handled value and kills tag-and-dispatch-without-a-union. | Raw `str` for any of these — rejected outright (stringly-typed-identifier anti-pattern; the project mandates newtypes for domain IDs). |
| `RecipeMatchPort`, `SolvedExampleRagPort`, `LeafLlmPort`, `ContextStore` are `Protocol`s; concrete adapters injected | **Hexagonal / Ports & adapters**; **Dependency inversion** | The Planner crosses a trust/technology boundary (LLM, KG); the routing *logic* must be LLM-free and unit-testable with fakes. The LLM is a leaf behind a Port — exactly `design.md §1`'s discipline. | Direct `anthropic` import in the planner — rejected: would put an LLM SDK in routing code, violating commitment §2.1 and the `fence`. |
| Supervisor resolves the plugin tuple; the kernel never names a plugin | **Plugin architecture / Pluggable systems**; **Open/Closed** | ADR-0031 is this pattern; Phase 8 *consumes* the existing `@register_probe`/plugin-registry seams — adding a plugin needs no Supervisor edit. The universal `(*,*,*)` plugin is loaded by the same mechanism. | A hardcoded `task_class → subgraph` map in the Supervisor — rejected: that is "an `if/elif` ladder with extra steps" (toolkit's plugin failure mode). |
| `BundleBuilder.build`, `render_hot_views`, `invalidates`, TCCM-union are pure; Redis/adapter I/O at the edges | **Functional core, imperative shell** | The routing/rendering/expansion *logic* is "given inputs, compute outputs" — pure functions are trivially testable (no 11-mock functions). The shell is the store and the dispatcher, both injected. | Threading Redis/adapters through pure functions as params — avoided by injecting them into the one impure class each. |
| `HotViewKey`, `ContextBundle`, `RouteDecision`, `SupervisorState`, all manifests are frozen Pydantic; `ContextBundle.derived` is a typed `Mapping`, never `dict[str, Any]` | **Make illegal states unrepresentable**; **Type everything strictly** | A `ContextBundle` that type-checks is structurally valid; a derived result is a `DerivedResult`, not an opaque dict. `mypy --strict` then refactors safely. | `dict[str, Any]` bundle payloads — rejected (untyped-interface anti-pattern; the project bans it). |
| `MCP_SKILLS_CONTRACT` as a `Final` pinned shape, snapshot-tested against the live server | **Smart constructor / contract snapshot** (the ADR-0007 probe-contract idiom) | The MCP public tool surface is a *contract*; pinning it with a snapshot test makes any drift a loud, reviewable diff — exactly how the probe ABC is protected. | A frozen *file* — rejected per commitment §2.5: a contract is a snapshot test, not a frozen file. |

## Patterns deliberately avoided

- **Strategy registry for planning steps** — there are exactly three steps fixed by ADR-0011; a registry/decorator is premature pluggability. A tuple iterated in order is the honest shape.
- **Specification pattern for plugin matching** — the `(task × lang × build)` match with wildcard precedence already lives in `codegenie.plugins.resolver`; re-expressing it as composable `Specification` objects would re-implement a shipped, tested seam for zero gain.
- **Command pattern for the routing decision** — `RouteDecision` is *data* (a logged record), not a deferred-execution object; making it a `Command` with an `execute()` would be ceremony.
- **A second in-process cache in front of `HotViewStore`** — one Redis `GET` already clears the SLO by 25×; a process-local LRU adds a second invalidation surface for no measurable win.
- **Per-stage MCP servers (Context/KG/Policy)** — ADR-0023 is *Deferred*; building four servers now would commit an undecided ADR. Phase 8 ships only the Skills server.
- **Event-sourcing the routing decisions into a dedicated store** — ADR-0034's canonical event log lands operationally in Phase 9; Phase 8 emits the `planner.route.decided` audit event into the existing audit sink, and Phase 9 makes it an event-stream projection. Building the event store now would front-run Phase 9.
- **Caching derived-query results in hot views** — ADR-0030 notes it is *possible*; Phase 8 caches only the four ADR-0013-mandated slices. Adding derived-query caching is a clean later addition; doing it now is premature.

## Risks (top 3–5)

1. **The `<50ms p95` exit criterion could be misread as a routing-decision SLO.** It is a hot-view *read* SLO (ADR-0013). The design keeps the routing decision and all graph queries *out* of that path — the Planner only does Redis reads inline. If a reviewer expects "the whole routing decision in 50ms," that is a scope misunderstanding to correct early. *Mitigation:* the e2e latency test measures `HotViewStore.get_all` specifically, and the design doc states the boundary explicitly.
2. **The null RAG port leaves the RAG branch un-exercised by real data until Phase 11.** Every non-recipe workflow routes to LLM in Phase 8. The chain *shape* is correct and the branch is fake-port-tested, but a real RAG regression cannot surface until the KG exists. *Mitigation:* documented as a deliberate stub (`NullRagPort`), not a hidden gap; the routing tests cover the RAG-hit branch via a fake that returns a hit.
3. **TCCM-union semantics across a multi-parent `extends` chain are subtle.** ADR-0031's "later-in-list wins" rule for `must_read`/`should_read` collisions is correct but easy to implement wrong. *Mitigation:* the Bundle Builder's union is a pure function with golden tests over a deliberately-collision-heavy fixture chain.
4. **Background-task rendering can silently fall behind if a gather fires faster than a render completes.** Two renders for the same repo could interleave. *Mitigation:* `render_hot_views` is idempotent (property-tested) and versioned keys mean the *last writer wins* with a consistent shape; a stale-but-consistent slice is acceptable, a torn slice is not — and the design never produces a torn slice (each slice is one atomic Redis write).
5. **ADR-0023 is still Deferred.** Shipping the Skills server as one stdio process is the right minimal step, but if the eventual topology is "single global MCP," the Skills server may need to merge later. *Mitigation:* `SkillsMcpServer` is a transport-agnostic plain class; only the thin `serve_skills_stdio` shell is topology-coupled — a merge is a shell rewrite, not a core rewrite.

## Acknowledged blind spots

- **Concurrency under portfolio scale.** Phase 8 is single-process asyncio. Hundreds of concurrent workflows hammering one Redis and one MCP subprocess is a Phase-9/Temporal concern; this design does not model connection pooling, MCP-server-per-worker, or Redis cluster sizing. The performance-lens design will cover this — I deprioritized it deliberately.
- **MCP server authorization.** ADR-0023 ties topology to a per-agent identity model. Phase 8's local stdio Skills server has no auth (it is a child process of the trusted orchestrator). When the topology and identity model land, auth is a real addition this design does not pre-figure.
- **Hot-view memory growth past ~10k repos.** The 10–40 MB figure is for ~1k repos; the design does not model eviction policy for a portfolio an order of magnitude larger. ADR-0013's "memory ∝ watched repos" is accepted but not stress-tested here.
- **Bundle Builder behavior when a plugin contributes an adapter for a primitive no TCCM query uses.** Harmless (the adapter is just never called) but untested; an over-contributing plugin is a plausible authoring mistake.

## Open questions for the synthesizer

1. **Bundle Builder home.** I placed it in the existing `codegenie.tccm` package (it is the TCCM's consumer). The performance/security designs may put it in the Supervisor package or a new one. The cohesion argument (TCCM model + TCCM consumer together) is strong but not absolute — synthesizer should pick one and state why.
2. **Does Phase 8 emit `planner.route.decided` into the audit sink or front-run Phase 9's event log?** I chose the existing audit sink, leaving Phase 9 to make it an event projection. If the security/performance designs argue for the event log now, the synthesizer must reconcile against ADR-0034's "lands operationally in Phase 9."
3. **Should the Supervisor be a LangGraph graph or a plain async function in Phase 8?** I chose a (minimal) graph for the Phase-9 Temporal seam and `design.md §1` fidelity. A plain function is simpler *today*. The synthesizer should weigh "boring now" against "the seam Phase 9 needs."
4. **Redis as the only new service vs. starting Postgres early.** Phase 9 adds Postgres for the checkpointer; one could argue for adding it in Phase 8 to avoid two infra changes. I kept Phase 8 to *one* new service (Redis) — minimal scope — but the synthesizer should confirm against the Phase 9 boundary.
5. **`NullRagPort` vs. omitting the RAG branch entirely until Phase 11.** I kept the three-step chain with a null middle step so the *shape* is right from day one. An alternative is a two-step chain (recipe → LLM) that grows a third step in Phase 11. The first is more honest about ADR-0011's intent; the second is less speculative. Synthesizer's call.
