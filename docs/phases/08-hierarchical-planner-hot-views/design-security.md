# Phase 08 — Hierarchical Planner + pre-rendered hot views: Security-first design

**Lens:** Security — isolation, least privilege, audit, supply chain.
**Designed by:** Security-first design subagent
**Date:** 2026-05-21

## Lens summary

Phase 8 adds the first component that *reads attacker-controlled data and acts on it to choose what runs next*: the Supervisor resolves a plugin from a `(task × language × build-tool)` tuple derived from a repo the system does not own, loads that plugin's manifest and TCCM, builds a Context Bundle by running graph-aware queries over repo content, and routes work between recipe / RAG / LLM. Every one of those inputs is adversary-reachable. This design treats the Planner as a **trust-boundary translator**, not a router: its job is to take untrusted shapes (`RepoContext` slices, plugin manifests, CVE feed records, repo source text) and emit *only typed, validated, capability-bearing* artifacts to the worker subgraphs. The single most important security property is that **a plugin cannot be selected, and a Context Bundle cannot be built, without crossing a smart constructor that the type system forces every consumer through**. I optimize for: (1) plugin-manifest integrity (a poisoned `plugin.yaml` must never be loadable, never silently widen scope, never inject an arbitrary import path); (2) Context Bundle as a sealed, provenance-stamped value — no `dict[str, Any]` ever reaches an LLM prompt; (3) the Skills MCP server as a *least-privilege read-only port* with no filesystem-escape and no credential surface; (4) Redis hot views as an integrity-checked cache that **fails closed to cold storage** rather than serving a poisoned slice; (5) an append-only, hash-chained planner-decision log so every recipe/RAG/LLM choice is replayable and tamper-evident. I deprioritize: raw planner latency beyond the <50ms p95 exit bar (I will spend milliseconds on signature verification and bundle sealing and say so), Redis memory efficiency, and operator ergonomics for plugin authors (authoring a plugin is deliberately more friction under this design).

## Threat model

### Assets to protect

- **The plugin resolution decision.** Which plugin handles a workflow determines which subgraph runs, which probes execute, which recipes apply, and ultimately what code lands in a PR. Mis-resolution is a code-execution-path hijack.
- **The Context Bundle.** It becomes the worker subgraph's initial state and the LLM's few-shot prompt. Poisoned bundle content is a prompt-injection delivery vehicle directly into the one LLM call Phase 8 routes to.
- **The planner-decision audit trail.** If an attacker can rewrite "we chose LLM-fallback" to "we chose recipe-lookup," the system loses the ability to prove what produced a given PR.
- **Credentials the Phase 8 layer touches.** LLM API keys (the LLM-fallback route), and — transitively — git push tokens and registry credentials held by *downstream* stages that consume what Phase 8 plans. Phase 8 itself should hold the *fewest possible* credentials: ideally only a scoped LLM key, minted per-workflow.
- **The Redis instance.** It pre-renders agent context. A writable Redis is a write primitive into every planner's context window.
- **The Skills MCP server's process boundary.** It runs as a local stdio child process; if it can be made to read arbitrary files or spawn subprocesses, it is a host-compromise pivot.

### Adversaries assumed

- **A compromised dependency in a target repo** — the repo's `package.json` / `pyproject.toml` resolves a malicious transitive dep. Its presence shapes `RepoContext.languages` / `build_systems` and therefore plugin resolution.
- **An adversarial CVE feed input** — NVD/GHSA/OSV records are partly free-text and partly attacker-influenced (a CVE description, affected-version ranges, affected-symbol names). The `vuln.provenance` derived query and the `risk_flags` hot view consume them. A crafted CVE record can carry prompt-injection payload into the bundle, or steer provenance to mis-route a workflow.
- **Prompt injection in repo content** — source files, README, comments, commit messages, even file *paths*. Anything the graph-aware queries pull into `must_read` / `should_read` is candidate injection text. The LLM-fallback node is the target.
- **A poisoned plugin manifest** — a `plugin.yaml` or `tccm.yaml` that is malformed, over-scoped (claims `(*, *, *)` to shadow the universal HITL fallback), declares a hostile `contributes.adapters` import path (`os:system`, a path-traversal module), sets an absurd `budget`, or weaponizes the `extends` chain (cyclic, or extends a higher-privilege plugin to inherit its contributions). At adoption all plugins are in-tree (ADR-0031 — out-of-tree is a v2 deferral), so the *primary* manifest threat is a malicious or buggy PR into the `plugins/` tree; the design must still treat the manifest as untrusted-until-validated so the in-tree assumption is defense-in-depth, not the only defense.
- **A malicious TCCM** — a `tccm.yaml` whose `derived` queries are crafted to exfiltrate the whole monorepo (`max_files` set to a huge number, a `transitive_callers` query with `depth: 99`), or whose `must_read` keys pull secret-shaped files (`.env`, `*.pem`) into the bundle.
- **A tampered hot view** — anyone with Redis write access (a misconfigured network, a second compromised service sharing the Redis) can pre-load a poisoned `available_skills` or `risk_flags` slice so the planner reads attacker-chosen context with single-digit-ms latency and full trust.
- **A compromised worker / subgraph node** — assume the LLM-fallback node, or a probe, executes attacker-influenced logic. What can it reach? (Answer below: a Context Bundle, a read-only Skills port, and nothing else.)

### Attack surfaces specific to this phase

1. **`plugin.yaml` / `tccm.yaml` parsing.** YAML deserialization (must be `yaml.safe_load`, never `yaml.load`), Pydantic validation, and — the dangerous one — the `contributes.adapters` import-path resolution, which is *code import driven by file content*.
2. **The `extends` inheritance walker.** Graph traversal over attacker-influenceable manifest data: cycles, depth, and privilege-inheritance.
3. **The graph-aware query executor (Bundle Builder).** Runs `scip.refs`, `import_graph.*`, `dep_graph.consumers`, `test_inventory.*` over repo content with `max_files` / `depth` parameters that come from the TCCM.
4. **The CVE-feed → bundle path.** `vuln.provenance` derived queries and the `risk_flags` hot view ingest CVE records.
5. **The Redis hot-view read path.** The planner reads `available_skills`, `entrypoint`, `risk_flags`, `confidence_summary` from Redis on the hot path.
6. **The Skills MCP stdio server.** A new long-lived child process speaking MCP over stdio; its tool surface is the attack surface.
7. **The view pre-render background asyncio task.** It runs off probe re-runs and writes Redis; a crafted gather can drive it.

### Trust boundaries

```
  TB-1  Target repo content / CVE feeds / plugin & TCCM files  →  in-process typed values
        (the gather layer crossed this for probes; Phase 8 re-crosses it for
         the Planner, the Bundle Builder, and the Skills server)
  TB-2  Supervisor (trusted core)  →  worker subgraph + LLM-fallback node (semi-trusted)
        (the Context Bundle is the ONLY thing that crosses; it is sealed)
  TB-3  Planner / Bundle Builder  →  Skills MCP server (separate OS process, semi-trusted)
        (stdio only; no shared memory; read-only tool surface)
  TB-4  Planner  →  Redis (separate process / network)  — untrusted-on-read cache
        (every read is integrity-checked; failure → cold-storage fallback)
  TB-5  LLM-fallback node  →  LLM provider (external network)
        (a per-workflow scoped, short-TTL key; egress allowlisted to the provider)
```

## Goals (concrete, measurable)

- **Sandbox escape risk / mitigations.** Phase 8 introduces no microVM-class workload (no code execution of agent output — that is Stages 4/5, ADR-0012). But it introduces two new process boundaries that must not become escape routes: the Skills MCP child process and the Redis client. **Goal:** the Skills MCP server runs as an unprivileged process with a read-only mount of the Skills/TCCM tree, `no_new_privileges`, a seccomp profile that denies `execve`/`ptrace`/`mount`, and zero network capability. The Bundle Builder's graph-query execution runs entirely in-process over already-gathered, already-sanitized `RepoContext` artifacts — it never re-reads raw repo bytes — so it inherits the gather layer's TB-1 crossing rather than opening a new one. **Measurable:** a fence test (`tests/fence/test_skills_mcp_isolation.py`) AST-walks the Skills server and asserts no `subprocess`, `os.system`, `socket`, `open(` outside the configured read-only root, and no import of any HTTP client.
- **Credential blast radius if a worker is compromised.** A compromised LLM-fallback node (or any subgraph node) can reach exactly: its sealed Context Bundle, the read-only Skills MCP port, and a **per-workflow LLM capability token** scoped to one model, one workflow ID, with a hard token-count cap and a TTL ≤ the workflow's planning-stage budget. It cannot reach: git tokens, registry credentials, the Redis write path, the audit log's signing key, the plugin registry, or another workflow's bundle. **Measurable:** the Planner process holds no git/registry credential at all (verified by an env-introspection CI test mirroring Phase 5 Goal 6 — no env var matching `GIT|GITHUB|REGISTRY|PUSH|*_TOKEN` is readable inside the planner package's process). The LLM key is never an env var; it is fetched per-workflow from a secrets broker and held only as an in-memory `LlmCapability` object that is revoked at planning-stage exit.
- **Audit completeness target.** 100% of plugin-resolution decisions and 100% of recipe/RAG/LLM routing decisions emit a typed, hash-chained `PlannerDecisionEvent`. The exit criterion ("the chosen path is logged on every workflow") is satisfied by *construction*: the routing edge cannot transition without a `PlannerDecisionEvent` having been appended — the event is the precondition of the transition, not a side effect. A CI test asserts that no routing edge in the subgraph can be reached on a code path that skips the append.
- **Allowed network egress.** The Planner process: **deny-all except** the secrets broker (to mint the LLM key) and the LLM provider endpoint (one host, TLS-pinned). The Skills MCP server: **zero network** — it serves local files only. Redis: a private network segment, mTLS, not internet-reachable. The view pre-render task: **zero network** — it reads `RepoContext` from the existing object store/Postgres and writes Redis, no external calls. CVE feeds are *not* fetched by Phase 8 — they are already in the `VulnIndex` snapshot the gather layer committed (Phase 3 S3-03); Phase 8 reads that snapshot, it does not call NVD/GHSA/OSV.

## Architecture

```
                    ╔═══════════ TB-1: untrusted inputs ═══════════╗
                    ║  plugins/*/plugin.yaml   plugins/*/tccm.yaml ║
                    ║  RepoContext slices (gathered)               ║
                    ║  VulnIndex snapshot (CVE records)            ║
                    ╚══════════════════════╤══════════════════════╝
                                           │ yaml.safe_load + Pydantic
                                           │ smart constructors only
   ┌───────────────────────────────────────▼───────────────────────────────────┐
   │  TRUSTED CORE  —  src/codegenie/planner/                                    │
   │                                                                             │
   │  ┌─────────────────────┐   PluginManifest (validated, frozen)               │
   │  │ PluginRegistry      │◄── load: yaml.safe_load → Pydantic → import-path    │
   │  │  (build-then-publish│       allowlist check → fail-fast at startup        │
   │  │   staging swap)     │                                                    │
   │  └──────────┬──────────┘                                                    │
   │             │ resolve(task,lang,build) — pure; cycle-bounded extends walk    │
   │             ▼                                                                │
   │  ┌─────────────────────┐   ResolvedPlugin (sum type)                        │
   │  │ Supervisor          │     = ConcretePlugin | UniversalHitlFallback        │
   │  │  routes via         │                                                    │
   │  │  conditional_edge   │                                                    │
   │  └──────────┬──────────┘                                                    │
   │             │ ResolvedPlugin                                                 │
   │             ▼                                                                │
   │  ┌─────────────────────┐   reads TCCM derived queries                       │
   │  │ BundleBuilder       │── runs scip/import/dep/test queries over            │
   │  │  (functional core)  │   gathered artifacts, max_files/depth CLAMPED       │
   │  │                     │── secret-shaped-path REJECTION on every file        │
   │  │                     │── per-query provenance recorded                    │
   │  └──────────┬──────────┘                                                    │
   │             │ ContextBundle  ── SEALED: smart-constructed, frozen,           │
   │             │                  content-hash stamped, provenance attached    │
   │  ┌──────────▼──────────┐                                                    │
   │  │ PlannerSubgraph     │  routes: recipe → RAG → LLM-fallback                │
   │  │  every routing edge │  ▶ PlannerDecisionEvent appended BEFORE transition  │
   │  └──────┬───────┬──────┘                                                    │
   │         │       │ recipe / RAG: in-core, no LLM                              │
   │         │       └──────────────────────────────┐                            │
   │  ════ TB-2 ═══════════════════════════════════  │ ContextBundle (sealed)     │
   │         ▼ LLM-fallback node (semi-trusted)      ▼                            │
   │  ┌──────────────────┐               ┌────────────────────────────┐          │
   │  │ holds LlmCapability│  ══ TB-5 ══► │ LLM provider (egress        │          │
   │  │ (scoped, TTL'd)    │  TLS-pinned  │  allowlist: 1 host)         │          │
   │  └──────────────────┘               └────────────────────────────┘          │
   └───────────┬──────────────────────────────┬────────────────────────────┬─────┘
   ══ TB-3 ════│                  ══ TB-4 ════│                             │
               ▼ stdio (no net)               ▼ mTLS, private net          ▼ append-only
   ┌────────────────────────┐    ┌──────────────────────────┐   ┌────────────────────┐
   │ Skills MCP server      │    │ Redis hot views          │   │ PlannerDecisionLog  │
   │  separate OS process   │    │  available_skills,       │   │  hash-chained,      │
   │  read-only Skills+TCCM │    │  entrypoint, risk_flags, │   │  signed, immutable  │
   │  mount; seccomp;       │    │  confidence_summary      │   │  (event-sourced)    │
   │  no_new_privileges;    │    │  ▶ each value HMAC-tagged │   └────────────────────┘
   │  zero network          │    │  ▶ read verify → on fail │
   └────────────────────────┘    │    FALL THROUGH to cold  │
                                 │    storage (fail-closed) │
                                 └──────────────────────────┘
                  ▲ writes
   ┌──────────────┴───────────────┐
   │ View pre-render asyncio task  │  triggered off probe re-runs; zero network;
   │  derives slices from union of │  writes HMAC-tagged values; never serves stale
   │  must_read across active TCCMs│  (gather-driven invalidation per ADR-0013)
   └───────────────────────────────┘
```

**Credential flow.** Only one credential is minted in Phase 8: the `LlmCapability`. The Supervisor, on entering the planning stage, requests it from the secrets broker scoped to `(workflow_id, model_id, max_tokens, ttl)`. It is passed *into* the LLM-fallback node as a constructor argument — never read from environment, never logged, never checkpointed. On planning-stage exit (success, HITL escalation, or failure) the Supervisor calls `LlmCapability.revoke()`. If the workflow never reaches LLM-fallback (recipe or RAG hit), no LLM key is ever minted — least privilege by routing.

## Components

### Supervisor (Hierarchical Planner)

- **Purpose.** Resolve the matching plugin for a workflow, dispatch into its subgraph, orchestrate Bundle building, and own the planning-stage credential lifecycle.
- **Trust level.** Trusted core. It is the TB-1 → TB-2 translator; it must be the smallest, most-audited code in the phase.
- **Interface.** `supervise(workflow: WorkflowRequest) -> PlanningOutcome`. `WorkflowRequest` carries the task class (system-controlled, trusted) plus a `RepoContextRef` (a content-hash handle, not inline data). **Adversarial inputs:** the `RepoContext` it dereferences (gathered from an untrusted repo) and, transitively, the plugin/TCCM files it loads.
- **Isolation.** In-process with the Bundle Builder and registry, but holds *no* network capability except the secrets-broker call. Runs under a process-level egress allowlist (deny-all default).
- **Credentials accessed.** Mints the `LlmCapability` per-workflow (model-scoped, `max_tokens`-capped, TTL ≤ planning budget). Holds the audit-log signing key *handle* (HSM/KMS-backed — the raw key never enters process memory; signing is a KMS call). Holds **no** git/registry credential.
- **Audit emissions.** `WorkflowDispatched(workflow_id, task_class, repo_context_hash)`, `PluginResolved(...)` (see PluginRegistry), `LlmCapabilityMinted(workflow_id, model_id, ttl)` / `LlmCapabilityRevoked(...)`. All hash-chained.
- **Tradeoffs accepted.** The Supervisor is a single point of trust; I accept that and pay for it with the smallest possible code surface and a contract-snapshot fence on its public type (`tests/fence/test_supervisor_contract.py`). I do *not* split the Supervisor into per-stage processes — that is ADR-0023 territory and over-engineering for Phase 8; instead the credential-scoping discipline gives most of the blast-radius benefit without the operational cost.

### PluginRegistry

- **Purpose.** Load every in-tree plugin manifest at startup, validate it, and answer `resolve(task, language, build) -> ResolvedPlugin`.
- **Trust level.** Trusted core *after* validation; the manifest *files* it ingests are untrusted (TB-1).
- **Interface.** `resolve(...)` is pure. Manifest loading happens once at startup via `load_plugin_registry(plugins_dir) -> PluginRegistry`. **Adversarial input:** every `plugin.yaml` and `tccm.yaml`.
- **Isolation.** No I/O after startup. The startup load is the only filesystem touch and is confined to the `plugins/` root (path-traversal-guarded — a manifest cannot reference a file outside its own plugin directory).
- **Credentials accessed.** None.
- **Audit emissions.** `PluginRegistryLoaded(plugin_count, manifest_hashes)`; per-resolution `PluginResolved(workflow_id, resolved_plugin_id, plugin_version, extends_chain, specificity_rank, fell_back_to_universal: bool)`.
- **Manifest defense (the load-bearing detail).** Manifest loading is a **smart constructor pipeline**, every stage of which must pass or the registry refuses to start (matching ADR-0031's "Supervisor refuses to start if any plugin fails validation" — partial-load is never silent):
  1. `yaml.safe_load` only. `yaml.load` is banned repo-wide by the `forbidden-patterns` pre-commit hook; a fence test extends the ban to assert the planner package never imports `yaml.Loader`/`yaml.FullLoader`.
  2. Pydantic v2 model `PluginManifest` with `extra="forbid"`, `frozen=True`. An unknown contribution category, a wrong type, a missing required field → `ValidationError` naming the file and field.
  3. **Import-path allowlist.** `contributes.adapters` values are `module:ClassName` strings. They are validated against a regex *and* the module prefix must start with `plugins.` or `codegenie.` — an adapter cannot point at `os`, `subprocess`, `builtins`, or any stdlib/3rd-party module. The import is resolved at startup (fail-fast per ADR-0031) but the resolved object's *type* is checked against the expected adapter Protocol before it is stored; a "module:ClassName" that resolves to a non-adapter is rejected.
  4. **Scope-claim guard.** A concrete plugin may not declare scope `(*, *, *)` — only the one in-tree `universal--*--*/` plugin may, and the loader asserts exactly one universal plugin exists. This stops a poisoned plugin from shadowing the HITL fallback or claiming every workflow.
  5. **`extends`-chain validation.** The walker is cycle-detected (a `seen` set; a cycle is a `PluginManifestError`) and depth-bounded (`MAX_EXTENDS_DEPTH = 8` — generous, finite). A child may not `extends` a plugin whose scope is *more specific* than its own (privilege/scope can only be inherited *downward* — a concrete plugin extending the universal base is fine; the reverse is rejected).
  6. **`budget` clamp.** TCCM `budget` fields (`max_files`, `max_tokens`, `per_file_max_tokens`) are validated against hard system ceilings via Pydantic field validators — a TCCM cannot declare `max_files: 1_000_000`. The *declared* budget is `min(declared, system_ceiling)` and the clamp is logged.
- **Tradeoffs accepted.** Build-then-publish staging (a fresh registry dict swapped in atomically only after *all* plugins validate) means a single bad manifest blocks startup of the whole planner — that is the correct fail-closed posture; a planner that runs with a partially-loaded registry would resolve workflows to the wrong plugin. The friction (a plugin author's typo blocks the dev loop) is accepted and is what `extra="forbid"` + a clear diagnostic is for.

### BundleBuilder

- **Purpose.** Given a `ResolvedPlugin`, execute its TCCM's `must_read` / `should_read` / derived queries against the gathered `RepoContext` artifacts and produce a sealed `ContextBundle`.
- **Trust level.** Trusted core (functional core). Its *inputs* — `RepoContext` slices, CVE records, file content pulled by queries — are untrusted (TB-1).
- **Interface.** `build(plugin: ResolvedPlugin, repo_context: RepoContext) -> ContextBundle`. Pure: same inputs → same bundle (the same determinism property the gather layer commits to in design.md §2.1, extended to bundle building). **Adversarial inputs:** every byte of every file a derived query selects; every CVE record a `vuln.provenance` query joins.
- **Isolation.** In-process, no network, no subprocess. It operates only on already-gathered, already-sanitized artifacts — it does **not** re-read raw repo bytes (the gather layer's sanitizer, design.md §"Sanitizer + writer", already scrubbed absolute paths and rejected secret-shaped fields at gather time). This is deliberate: re-reading raw bytes would open a second, weaker TB-1 crossing.
- **Credentials accessed.** None.
- **Audit emissions.** `BundleBuilt(workflow_id, plugin_id, tccm_hash, bundle_hash, queries: [QueryProvenance])` where each `QueryProvenance` records `{name, primitive, files_returned, files_included, files_deferred_budget, files_rejected_secret_shaped, adapter_confidence, downgraded: bool}`.
- **Defense in depth — what each layer stops.**
  - **`max_files` / `depth` clamp** (TCCM-declared, system-ceiling-capped per PluginRegistry §6) stops a *malicious TCCM* from exfiltrating a whole monorepo into the bundle via `transitive_callers(depth=99)`. Truncation is logged in `QueryProvenance`.
  - **Secret-shaped-path rejection** stops a TCCM (or a derived query that resolves to an unexpected file set) from pulling `.env`, `*.pem`, `*.key`, `id_rsa`, `credentials.json`, `.npmrc`, `.pypirc` into the bundle. This reuses the gather sanitizer's secret-field rejection (Phase 2 ADR-0005 / ADR-0010 `RedactedSlice`) but applies it at *path* granularity at bundle-build time — a second, independent check (defense in depth: the gather sanitizer scrubs *content*, the BundleBuilder rejects *whole files by path shape*).
  - **`IndexHealthProbe` confidence gate** (ADR-0030): if SCIP confidence is low the builder degrades to tree-sitter per the TCCM's declared `fallback` and records `downgraded: true`. A stale index that *silently* returns wrong call sites is the worst failure mode (CLAUDE.md); making the downgrade typed and logged is the mitigation.
  - **Bundle sealing** (the TB-2 control): `ContextBundle` is constructed only by `BundleBuilder.build` (smart constructor — the raw Pydantic constructor is not part of the public surface), is `frozen=True`, and carries a `bundle_hash` over its content + a `provenance` record. The worker subgraph and the LLM-fallback node receive a `ContextBundle` *value*; they cannot receive a `dict`, cannot mutate it, and cannot construct a forged one. **This makes "the LLM only ever sees validated context" a typed invariant, not a code-review hope.**
- **Prompt-injection containment.** The BundleBuilder cannot *prevent* injection text inside legitimately-selected source files (that text is genuinely part of the repo). What it does: (a) every file in the bundle carries its provenance (which query selected it, which path) so the LLM-fallback node's system prompt can fence repo content as untrusted data with explicit delimiters; (b) the bundle records a `contains_unverified_repo_content: true` flag whenever any `should_read`/`may_read` free-text slice is included, which the LLM-fallback node uses to apply the stricter "treat all bundle content as data, never as instructions" prompt template; (c) the planner's *routing* decision (recipe vs RAG vs LLM) is made on *structural* signals (recipe match, RAG similarity score) — never on free-text the LLM interpreted — so injection cannot flip the route itself.
- **Tradeoffs accepted.** Bundle sealing + content hashing costs ~1–3ms per build; I spend it and count it against the <50ms budget honestly (see Resource profile). I do *not* attempt LLM-output-side injection detection in Phase 8 — that is a deeper problem and belongs with the Trust-Aware gate layer; Phase 8's job is to make the *input* boundary clean and *typed*.

### PlannerSubgraph (recipe / RAG / LLM routing)

- **Purpose.** Inside the resolved plugin's subgraph, route work between recipe lookup, solved-example RAG, and LLM-fallback, and log the chosen path.
- **Trust level.** Trusted core for the recipe/RAG nodes; the LLM-fallback node is **semi-trusted** (it is the one component that processes attacker-influenceable free text through a model).
- **Interface.** Operates on the sealed `ContextBundle`. Routing is a `conditional_edge`. **Adversarial input:** the bundle content (already typed and sealed, but its *semantic* content is still repo-derived).
- **Isolation.** The LLM-fallback node is the only node that holds the `LlmCapability` and the only node with TB-5 egress. Recipe and RAG nodes have no network and no credential.
- **Credentials accessed.** LLM-fallback node only: the per-workflow `LlmCapability`.
- **Audit emissions.** `PlannerDecisionEvent(workflow_id, route: Literal["recipe","rag","llm_fallback"], reason, bundle_hash, recipe_match?, rag_top_score?)` — appended to the hash-chained log **before** the routing transition fires. The transition is gated on the append succeeding (Command pattern: the route is a `Command` whose `execute()` is the append + transition; the two are atomic).
- **Tradeoffs accepted.** Making the audit append a *precondition* of the transition (not a fire-and-forget side effect) adds a synchronous KMS-signed-append on every routing decision — a few ms. I pay it: the exit criterion "the chosen path is logged on every workflow" is then true by construction, not by hoping no code path skips the logger.

### Skills MCP server

- **Purpose.** Serve Skills (and the TCCM index, per ADR-0029) to the Planner over MCP stdio — the first concrete piece of the eventual MCP topology (ADR-0023).
- **Trust level.** Semi-trusted. It is a separate OS process; the Planner does not trust it with anything beyond a read-only data surface, and it does not trust the Planner with anything (it serves, it does not act).
- **Interface.** MCP stdio. A **read-only** tool surface: `list_skills(repo_scope)`, `get_skill(skill_id)`, `list_tccms()`, `get_tccm(plugin_id)`. **No write tool. No exec tool. No filesystem-path tool.** Inputs are skill/plugin IDs (validated as newtypes against a regex; a path-traversal ID like `../../etc/passwd` fails the newtype smart constructor).
- **Isolation.** Runs as an unprivileged user, `no_new_privileges`, a seccomp-bpf profile denying `execve`, `ptrace`, `mount`, `socket` (zero network — it serves local files), with a read-only bind-mount of *only* the Skills + TCCM tree as its entire visible filesystem. stdio is the only channel; no shared memory with the Planner. If it is compromised, it can read the (already-public-to-the-system) Skills tree and nothing else — it cannot pivot.
- **Credentials accessed.** None. Skills and TCCMs are non-secret data.
- **Audit emissions.** `SkillsServerStarted(version, served_tree_hash)`; per-request `SkillQueried(skill_id, requester_workflow_id)` (so an anomalous query pattern is visible).
- **Tradeoffs accepted.** A stdio child process is more operational surface than an in-process import. I accept it because (a) the roadmap explicitly calls for it ("the Skills server runs as a local MCP stdio process, prefiguring the eventual MCP topology"), and (b) the process boundary *is* a security gain: it lets the Skills surface run under a tighter seccomp/mount profile than the Planner can, and it forces the Skills interface to be an explicit, contract-tested port now rather than an organically-grown import graph later. I do *not* build the full per-stage MCP topology (ADR-0023 is `Deferred`); Phase 8 ships exactly one MCP server and treats it as the worked example.

### Redis hot-view layer

- **Purpose.** Serve `available_skills`, `entrypoint`, `risk_flags`, `confidence_summary` to the planner in <50ms p95.
- **Trust level.** Untrusted-on-read. Redis is a cache; the design assumes its contents *could* be tampered and never trusts a read blindly.
- **Interface.** `get_hot_view(repo, slice_name) -> HotViewSlice | None`. `None` → cold-storage fallback.
- **Isolation.** Redis runs on a private network segment, mTLS-authenticated, not internet-reachable, ACL'd so the Planner has read-only access and only the pre-render task has write access (Redis 6+ ACLs — `+get +mget` for the planner user, `+set +del` for the pre-render user).
- **Credentials accessed.** A Redis ACL credential (read-only for the planner, distinct write credential for the pre-render task). These are minted from the secrets broker, not env vars.
- **Audit emissions.** `HotViewServed(repo, slice, source: Literal["redis","cold_fallback"], integrity_ok: bool)`. An `integrity_ok: false` is a security event, alerted.
- **Integrity defense (the load-bearing detail).** Every value written to Redis by the pre-render task is **HMAC-tagged** with a key the pre-render task and the planner share (from the secrets broker; rotated). On read, the planner verifies the HMAC and the embedded `(repo, slice, gather_id, schema_version)` binding. If verification fails — tampering, a stale schema version, a wrong-repo value — the planner **discards the Redis value and falls through to cold storage** (Postgres + object store, per ADR-0013's documented fall-through path). This makes a writable-Redis compromise a *latency* problem, not an *integrity* problem: an attacker who poisons Redis cannot get a poisoned slice into a planner's context — they can only force a slower cold read. **Fail-closed, by design.**
- **Tradeoffs accepted.** HMAC verification adds ~0.1–0.3ms per read — trivially inside the <50ms budget. The HMAC tag adds ~32 bytes per slice — negligible against ADR-0013's already-bounded memory cost. I deliberately do *not* set a TTL (matching ADR-0013 — invalidation is gather-driven); the HMAC's `gather_id` binding is what makes a stale entry detectable instead.

### View pre-render asyncio task

- **Purpose.** After every successful gather, re-render the hot-view slices (derived from the union of `must_read` across active TCCMs) into Redis.
- **Trust level.** Trusted core; its *input* (the freshly-gathered `RepoContext`) is the gather layer's already-sanitized output.
- **Interface.** Triggered off probe re-runs (an internal event, not a network call). No public interface.
- **Isolation.** In-process background asyncio task within the gather/planner service. Zero network. Reads `RepoContext` from the existing store; writes Redis with the write-scoped ACL credential.
- **Credentials accessed.** The Redis write ACL credential; the HMAC signing key.
- **Audit emissions.** `HotViewsRendered(repo, gather_id, slices: [slice_name], tccm_union_hash)`.
- **Tradeoffs accepted.** Deriving the slice list from "the union of `must_read` across active plugins' TCCMs" means a poisoned TCCM could in principle widen what gets pre-rendered. Mitigation: the pre-render task only renders slices that *already exist* in the gathered `RepoContext` (missing keys are absence, not error — per ADR-0031) and every rendered value is still secret-shaped-rejected before write. A malicious TCCM can make the pre-render do slightly more work; it cannot make it render a secret.

### PlannerDecisionLog

- **Purpose.** The immutable, tamper-evident record of every plugin-resolution and routing decision.
- **Trust level.** Trusted core; append-only; its integrity is itself a protected asset.
- **Interface.** `append(event: PlannerEvent) -> ChainHead`. No update, no delete.
- **Isolation.** Backed by an append-only store. Each event is a typed Pydantic model (a discriminated union of `WorkflowDispatched | PluginResolved | BundleBuilt | PlannerDecisionEvent | LlmCapabilityMinted | ...`), BLAKE3-chained to its predecessor, and the chain head is signed by a KMS-held key (the raw signing key never enters the planner process). This mirrors the existing audit-chain pattern (`tests/integration` audit verify, `codegenie audit verify` CLI).
- **Credentials accessed.** A KMS *handle* for the chain-head signing operation — not the key itself.
- **Audit emissions.** It *is* the audit emission target.
- **Tradeoffs accepted.** A KMS signing call per chain-head update adds latency to the *batch* (chain head is signed per workflow, not per event) — acceptable. Event sourcing here is justified (not ceremony): the question "what did the planner choose for workflow X, and can I replay it" is a real operational and forensic need, and Phase 9 will make this log a projection of the canonical event store (design.md Phase 9 note) — Phase 8 builds it in the shape Phase 9 will adopt.

## Data flow

One representative run: a `vulnerability-remediation` workflow on a Node + npm repo whose `RepoContext` was gathered from an untrusted target repo.

1. **`supervise(WorkflowRequest)`.** Task class `vulnerability-remediation` (system-controlled, trusted); a `RepoContextRef` content-hash handle. The Supervisor dereferences the `RepoContext` from the store. **TB-1 crossing #1** — but the `RepoContext` is the gather layer's already-sanitized artifact, so this crossing reuses an existing-and-tested boundary.
2. **`PluginRegistry.resolve("vulnerability-remediation", "node"/"javascript", "npm")`.** The registry was loaded at startup; every manifest already passed the smart-constructor pipeline (TB-1 crossing #2 happened *once at startup*, fail-closed — a poisoned manifest would have prevented the planner from starting at all). `resolve` is a pure function over already-validated data; it walks the cycle-bounded `extends` chain, picks the most-specific plugin, and returns a `ResolvedPlugin` sum-type value. If nothing matched it would return `UniversalHitlFallback` — never a silent miss. `PluginResolved` event appended.
3. **`BundleBuilder.build(resolved_plugin, repo_context)`.** Reads the plugin's TCCM (already validated, budgets already clamped). Runs `must_read` derived queries — `scip.refs(vulnerability.affected_symbols)` etc. — through the plugin's language search adapters. Each query result is `max_files`-clamped; every selected file is secret-shaped-path-rejected; `IndexHealthProbe` confidence gates SCIP vs tree-sitter. The result is smart-constructed into a sealed, frozen, content-hashed `ContextBundle` with full `QueryProvenance`. `BundleBuilt` event appended.
4. **PlannerSubgraph routing.** Recipe-match node runs first on the bundle's *structural* slices — pure, no LLM. Suppose it misses. RAG node runs — vector similarity, pure, no LLM. Suppose it misses (`rag_top_score` below threshold). The routing edge selects LLM-fallback. **Before** the transition fires, a `PlannerDecisionEvent(route="llm_fallback", reason="recipe_miss+rag_below_threshold", bundle_hash, rag_top_score)` is appended to the hash-chained log; the transition is gated on that append.
5. **LLM-capability mint.** Only now — because the route is LLM-fallback — does the Supervisor request an `LlmCapability` from the secrets broker, scoped to `(workflow_id, model_id, max_tokens, ttl=planning_budget)`. **Credential minted here, just-in-time.** `LlmCapabilityMinted` appended. (Had recipe or RAG hit, no LLM key would ever exist for this workflow.)
6. **LLM-fallback node.** **TB-2 crossing** — the sealed `ContextBundle` is the *only* thing that crosses into the semi-trusted node. The node builds its prompt, fencing all repo-derived bundle content as untrusted data (the `contains_unverified_repo_content` flag selects the stricter template). **TB-5 crossing** — it calls the LLM provider over a TLS-pinned, single-host-allowlisted egress, authenticating with the `LlmCapability`. The model's output is a *plan*, not executed code; it flows back as a typed planning artifact.
7. **Planning-stage exit.** The Supervisor calls `LlmCapability.revoke()` — **credential revoked here**, regardless of success/failure/HITL. The chain head is KMS-signed. The planning outcome (a typed plan + the bundle provenance + the decision-log chain head) is handed to the next stage.

Throughout, hot-view reads (steps 3–4 consult `available_skills`, `risk_flags`, etc.) hit Redis; every read is HMAC-verified and falls through to cold storage on any verification failure (**TB-4** — never trusted blindly).

## Failure modes & recovery

| Failure | Detected by | Containment | Recovery |
|---|---|---|---|
| **Poisoned `plugin.yaml`** — malformed, over-scoped `(*,*,*)`, hostile adapter import path, weaponized `extends` | Smart-constructor pipeline at registry load: `yaml.safe_load` + Pydantic `extra="forbid"` + import-path allowlist + scope-claim guard + cycle/depth-bounded `extends` walk | Planner **refuses to start** (build-then-publish: the staging registry is never published if any manifest fails) — fail-closed | Reject the offending PR; the diagnostic names the file and field. No degraded-mode run. |
| **Malicious TCCM** — `max_files: 1e6`, `depth: 99`, `must_read` keys targeting `.env`/`*.pem` | TCCM Pydantic field validators (budget clamp); BundleBuilder per-file secret-shaped-path rejection | Budgets clamped to system ceilings (logged); secret-shaped files rejected and counted in `QueryProvenance.files_rejected_secret_shaped` | Bundle is built without the rejected files; the rejection count is a reviewable signal; an anomalous count alerts. |
| **Prompt injection in repo content** pulled into a `should_read` slice | Not preventable at selection time (the text is genuinely in the repo) | `ContextBundle.contains_unverified_repo_content` flag → LLM-fallback node uses the strict "all bundle content is data" prompt template with explicit delimiters; routing decision uses only structural signals so injection cannot flip the route | The model produces a *plan* (not executed code); the plan still passes through downstream Trust-Aware gates (ADR-0008 objective signals) and a human merge (ADR-0009). Defense in depth: Phase 8 cleans the input boundary; Phases 4/5 gate the output. |
| **Adversarial CVE feed record** — crafted description / affected-symbol carrying injection, or steering `vuln.provenance` to mis-route | `vuln.provenance` adapters are property-tested under poisoned `locations[].layerID` (Phase 7 precedent); CVE free-text in the bundle is fenced as untrusted data like any repo content | A crafted provenance steers to a *wrong plugin*, not to *code execution*; if provenance is `Unknown` the workflow routes to the universal HITL fallback — never silently mis-handled | Mis-routing is caught when the wrong plugin's TCCM finds no matching evidence and the subgraph escalates HITL; the decision log shows exactly which provenance value drove the route. |
| **Tampered hot view** — poisoned `available_skills`/`risk_flags` written to Redis | HMAC verification on every read (`integrity_ok: false`) | Planner **discards the Redis value, falls through to cold storage** — fail-closed; a writable-Redis compromise becomes a latency cost, not an integrity breach | `HotViewServed(source="cold_fallback", integrity_ok=false)` is a security event; alert + investigate Redis access. The planner's context is correct throughout. |
| **Sandbox-escape attempt via the Skills MCP server** — crafted skill ID / MCP message tries path traversal or subprocess spawn | Newtype smart constructor on skill/plugin IDs rejects traversal; seccomp denies `execve`/`socket`; read-only mount has nothing else to reach; fence test asserts no `subprocess`/`socket`/`open` outside root | A compromised Skills server can read only the (non-secret) Skills tree — no pivot, no network, no credential, no write | Restart the process from the pinned image; the read-only mount means no persistent state to clean. |
| **LLM key exfiltration** by a compromised LLM-fallback node | The key is never an env var, never logged (a CI test asserts no log line matches the key shape), never checkpointed; it is a TTL'd, model-scoped capability object | Even exfiltrated, the key is scoped to one model, one workflow, a hard token cap, and a TTL ≤ planning budget — and is `revoke()`d at stage exit | Rotate; the per-workflow scoping means one leaked key cannot be reused across workflows or after the TTL. |
| **Audit-log tampering** — attacker rewrites a routing decision | BLAKE3 hash chain + KMS-signed chain head; `codegenie audit verify` detects any break | A break is detectable, not preventable-at-write only — the chain makes silent rewrite impossible | Forensic: the last valid chain head bounds the tamper window; investigate. |
| **Registry-load partial failure** (one of 30 plugins fails mid-load) | Build-then-publish staging — the new registry dict is published only after *all* plugins validate | The previously-running registry stays live; the *new* (incomplete) one is never published | Old registry continues serving; the failed plugin's diagnostic is surfaced for fix. No partial-registry window. |

## Resource & cost profile

- **Latency budget (exit criterion: <50ms p95 for hot-view serving).** Hot-view Redis read ≈ 1–5ms (single-digit-ms per ADR-0013) + HMAC verify ≈ 0.1–0.3ms. **Security cost on the hot path: ~0.3ms** — well inside budget. Cold-storage fallback (on HMAC failure or miss) is the ADR-0013 baseline (~tens of ms) and is the correct, accepted cost of failing closed.
- **Plugin resolution.** Pure in-memory dict + a cycle-bounded `extends` walk: <1ms. Manifest validation cost is paid *once at startup* (not per workflow) — generous: ~10–50ms per plugin for `yaml.safe_load` + Pydantic + import-path resolution; for ~30 plugins, ~1–2s of startup time. Accepted: startup, not request path.
- **Bundle building.** Dominated by the graph queries themselves (ADR-0030: dep-graph pennies, tree-sitter ~100ms, SCIP single-digit-seconds for a hot query). Security additions: per-file secret-shaped-path check ≈ microseconds × `max_files`; bundle content-hash + seal ≈ 1–3ms. **Security cost: ~2–4ms on a multi-hundred-ms operation** — negligible.
- **Audit append.** Per-event append ≈ sub-ms; per-workflow KMS-signed chain head ≈ 5–20ms (a network call to KMS). **Security cost: ~10ms per workflow** — paid once, off the hot path.
- **Skills MCP server.** One extra long-lived process, ~30–80MB RSS, near-zero CPU at idle. The seccomp/mount setup is one-time at process start.
- **Redis memory.** ADR-0013's bounded cost + ~32 bytes/slice HMAC tag — negligible.
- **What would be cheaper without these controls.** Dropping HMAC on hot views saves ~0.3ms/read and 32 bytes/slice — and turns a writable-Redis compromise into a context-poisoning RCE-adjacent. Dropping the Skills-server process boundary (importing Skills in-process) saves a process and ~50MB — and removes the ability to seccomp/mount-confine the Skills surface and forfeits the ADR-0023 worked example. Dropping just-in-time LLM-key minting (a static env-var key) saves a secrets-broker round-trip per LLM-fallback workflow (~10–30ms) — and makes one leaked key reusable across every workflow forever. Dropping bundle sealing saves ~3ms and lets workers pass `dict`s around — and loses the typed guarantee that the LLM only sees validated context. **Every control here costs single-digit milliseconds and buys a typed, fail-closed invariant. The total security tax on the hot path is under 1ms; off the hot path, under ~15ms per workflow.** That is cheap.

## Test plan

"Passes" means: every adversarial case below is exercised in CI and fails *closed*, and every typed invariant has a fence test that fails if the invariant is removed.

- **Plugin-resolution tests** (roadmap-named). Fixture context + skill manifest → assert the resolved plugin and `extends` chain. Plus the no-match case → asserts `UniversalHitlFallback`.
- **Manifest-poisoning suite.** A `tests/fixtures/plugins/malicious/` tree: a `(*,*,*)`-claiming concrete plugin, a manifest with `contributes.adapters: os:system`, a cyclic `extends`, a 9-deep `extends`, a manifest with `extra` keys, a TCCM with `max_files: 1_000_000`. Each must make `load_plugin_registry` raise the specific typed error and the planner must not start.
- **Bundle secret-rejection test.** A fixture `RepoContext` whose derived-query expansion would select `.env`, `id_rsa`, `.npmrc`. Assert those files are absent from the built `ContextBundle` and `QueryProvenance.files_rejected_secret_shaped` counts them.
- **Bundle-seal fence.** `tests/fence/test_context_bundle_sealed.py` — assert `ContextBundle` is `frozen=True`, has no public raw constructor, and that the worker-subgraph entry signature accepts only `ContextBundle` (no `dict`). AST-walk asserts no subgraph node receives an unsealed mapping.
- **Hot-view integrity test.** Write a value to Redis with a wrong HMAC; assert the planner discards it, falls through to cold storage, returns the correct value, and emits `HotViewServed(integrity_ok=false)`.
- **Redis-tamper / fail-closed test.** Simulate a Redis returning attacker-controlled bytes for `risk_flags`; assert the planner's bundle is built from cold storage and is byte-identical to the no-tamper run.
- **Skills-MCP isolation fence.** `tests/fence/test_skills_mcp_isolation.py` AST-walks the server: no `subprocess`, no `os.system`, no `socket`/HTTP-client import, no `open(` outside the configured read-only root. A contract test pins the MCP tool surface (read-only — `list_skills`/`get_skill`/`list_tccms`/`get_tccm`; *no* write/exec tool).
- **Skills-ID traversal test.** `get_skill("../../etc/passwd")` → the newtype smart constructor rejects it before any filesystem touch.
- **Credential-isolation CI test.** Env introspection inside the planner package's process: no var matching `GIT|GITHUB|REGISTRY|PUSH|.*_TOKEN|.*_KEY|.*_SECRET` is readable. A log-scraping test asserts no `LlmCapability` token shape ever appears in any emitted log line.
- **Just-in-time credential test.** A workflow that hits a recipe match → assert *no* `LlmCapabilityMinted` event was emitted (no key ever existed). A workflow that routes to LLM-fallback → assert `LlmCapabilityMinted` then `LlmCapabilityRevoked` bracket the LLM call.
- **Decision-log completeness test.** Run N fixture workflows across all three routes; assert exactly N `PlannerDecisionEvent`s, the hash chain verifies end-to-end, and a deliberately-introduced gap in the chain is caught by `audit verify`. A static test asserts no routing edge is reachable on a code path that skips the append.
- **Prompt-injection fixture.** A repo fixture with an injection string in a `should_read`-selected source file; assert `ContextBundle.contains_unverified_repo_content` is `true`, the strict prompt template is selected, and the *route* (decided on structural signals) is unaffected by the injected text.
- **Determinism test.** `BundleBuilder.build` on the same `(plugin, repo_context)` twice → byte-identical `bundle_hash` (the gather-layer determinism property, extended).

## Design patterns applied

| Decision | Pattern applied | Why this pattern here | Pattern not applied (and why) |
|---|---|---|---|
| `ContextBundle` is constructed only via `BundleBuilder.build`, is frozen + content-hashed, and is the only type that crosses TB-2 into the worker/LLM node | **Smart constructor** + **make-illegal-states-unrepresentable** | The control "the LLM only ever sees validated context" must be *unforgeable*, not a code-review hope. If the raw constructor is private and the worker entry signature accepts only `ContextBundle`, an unvalidated `dict` reaching a prompt is a compile-time error. The invariant is the type. | Runtime validation at the LLM node ("assert bundle is valid") — rejected: someone forgets it; an assert is not an invariant. |
| `LlmCapability` — a TTL'd, model-scoped, token-capped object minted just-in-time only on the LLM-fallback route, passed as a constructor arg, `revoke()`d at stage exit | **Capability pattern** | A capability that *grants* the LLM call is harder to forge and easier to scope than an ambient env-var key checked by an `is_authorized` flag. No capability = no LLM call = least privilege by routing: a recipe/RAG hit never mints a key at all. | An `is_llm_allowed` boolean or a process-wide env-var key — rejected: ambient credentials have unbounded blast radius and cannot be scoped per-workflow or TTL'd. |
| Plugin resolution result is `ResolvedPlugin = ConcretePlugin \| UniversalHitlFallback`; planner routes are `Literal["recipe","rag","llm_fallback"]`; planner events are a discriminated union | **Tagged union / sum type for state** | "No specific plugin matched" must be an explicit, type-checked variant the Supervisor is *forced* to handle (ADR-0031: never a silent miss). A sum type makes the HITL fallback unforgettable; a nullable `ConcretePlugin \| None` would let a `None` slip through. | A nullable plugin + an `if plugin is None` check scattered at call sites — rejected: tag-and-dispatch without a tagged union; the missing-handler bug is invisible. |
| Each routing decision is a `Command` whose `execute()` atomically appends a `PlannerDecisionEvent` *then* fires the transition; the log is a BLAKE3-chained, KMS-signed event stream | **Command pattern** + **event sourcing** | The exit criterion "the chosen path is logged on every workflow" is a *security* and *forensic* requirement — it must be true by construction. A Command that fuses log-append with the transition makes "route without logging" unrepresentable; event sourcing makes the decision history replayable and tamper-evident, and matches the shape Phase 9's canonical event log will adopt. | Fire-and-forget logging after the transition — rejected: a code path can skip it; "100% logged" becomes a hope. CRUD audit table — rejected: not tamper-evident, not replayable. |
| The Skills MCP server is a separate seccomp/mount-confined process exposing a read-only port; isolation boundaries (Skills server, Redis, LLM provider) are Ports with concrete Adapters | **Hexagonal / ports & adapters** | Every trust-boundary crossing is a Port: the Skills port (stdio adapter), the hot-view port (Redis adapter, with cold-storage as the fallback adapter), the LLM port (provider adapter). The core Planner depends on Protocols, never on `redis-py` or the `mcp` SDK directly — so the boundary is enforced by the type system and each adapter can carry its own confinement (the Skills adapter spawns the seccomp'd process; the Redis adapter does HMAC verify). | A "hexagonal" design that imports `redis` directly into the Planner — rejected: smuggles the substrate into the core, and the boundary stops being a place you can confine. |
| Every manifest/TCCM/CVE/repo input crosses a `yaml.safe_load` + Pydantic `extra="forbid"` + import-path-allowlist pipeline before becoming an in-process value | **Smart constructor** (again, at the TB-1 boundary) + **plugin architecture with a guarded kernel** | The plugin architecture (ADR-0031) is the right extension model, but a plugin *manifest* is attacker-reachable data; the kernel must treat it as untrusted-until-validated. A smart-constructor pipeline that fails the *whole registry load* on any bad manifest is the fail-closed posture — partial load is never silent. | Trusting in-tree manifests because "they went through PR review" — rejected: defense in depth; PR review is one layer, the typed validation pipeline is the enforced one, and it is what makes the v2 out-of-tree-plugin future safe by default. |

## Risks (top 3–5)

1. **Prompt injection inside legitimately-selected repo content is not eliminated, only contained.** If a `should_read` slice genuinely must include a source file, and that file carries an injection payload, Phase 8 fences it as untrusted data but cannot strip it. Residual risk: a sufficiently clever payload influences the LLM-fallback plan. *Mitigation in depth:* the plan is not executed code; it passes through Phase 4/5 Trust-Aware gates (objective signals, ADR-0008) and a human merge (ADR-0009). Phase 8 makes the input boundary typed and fenced; it explicitly does not own output-side injection defense.
2. **The Supervisor is a single trusted core.** A bug in the manifest-validation pipeline or the `extends` walker is a high-value target. *Mitigation:* smallest-possible code surface, a contract-snapshot fence on its public type, the malicious-manifest test suite, and the build-then-publish fail-closed load. But "smallest possible" is a discipline, not a guarantee.
3. **HMAC key management for hot views is new operational surface.** The pre-render task and the planner share an HMAC key from the secrets broker; key rotation must not cause a window where in-flight Redis values fail verification *and* cause a thundering-herd of cold-storage reads. *Mitigation:* the HMAC tag embeds a key-version id; the planner accepts the current and previous key version during a rotation window. Still, this is a moving part the design adds.
4. **`vuln.provenance`-driven mis-routing.** A crafted CVE record could steer provenance to the wrong task class and thus the wrong plugin. The containment (wrong plugin → no matching evidence → HITL escalation) works, but it is a *detect-and-escalate* containment, not a *prevent*. A repo owner could see spurious HITL escalations from a poisoned upstream CVE feed.
5. **The Skills MCP stdio process is the first MCP server; its seccomp/mount profile is bespoke.** A misconfigured profile (too permissive, or too strict and the server can't read its mount) is a deployment risk. *Mitigation:* the isolation fence test catches *code-level* escapes; a startup self-check asserts the process cannot reach outside its mount. But the OS-level profile is infrastructure-as-code that must be reviewed as carefully as the code.

## Acknowledged blind spots

- **Latency under the security tax at true portfolio scale.** I claim ~0.3ms hot-path security cost and ~15ms/workflow off-path; these are estimates. Under thousands of concurrent workflows, KMS signing throughput and secrets-broker round-trips for LLM-key minting could become a contention point I have not modeled. The performance-first design will have sharper numbers here.
- **The recipe/RAG/LLM routing *logic itself*.** I have secured the *boundary* around the router and the *audit* of its decision, but I have said little about how recipe-match and RAG retrieval actually score — that is the substance of the planner and the best-practices design owns it. A poisoned solved-example in the RAG store is a supply-chain threat I flag but do not fully design the defense for (Stage 7 Learning writes that store; its integrity is a cross-phase concern).
- **Multi-plugin `Both`-workflow coordination** (ADR-0042) — the roadmap puts this at Phase 8's door but the scope text I was given centers single-plugin resolution. A parent workflow coordinating two child plugins multiplies the credential-scoping and audit surface; I have designed for single-plugin dispatch and only gestured at the `Both` case (provenance `Both` → HITL or a coordination candidate). If `Both` coordination is in Phase 8 scope, the `LlmCapability` and decision-log model need a parent/child extension I have not drawn.
- **Redis as a shared instance.** I assumed a private, mTLS, ACL'd Redis. If the deployment reality is a Redis shared with other services, the ACL story needs more than I specified, and the HMAC-fail-closed design becomes load-bearing rather than defense-in-depth.
- **Cost attribution of the security controls.** I asserted the controls are cheap; I did not build the cost-ledger entries for "HMAC verifications performed," "cold-storage fallbacks triggered," "LLM capabilities minted." If a Redis compromise silently degrades every read to cold storage, the *latency* is contained but the *cost* signal that would surface the attack is something I flagged but did not specify.

## Open questions for the synthesizer

1. **Does the `LlmCapability` just-in-time mint cost (a secrets-broker round-trip on every LLM-fallback workflow) fit the latency budget the performance design assumes?** If the performance design wants a warm/pooled key, the synthesizer must decide between pooled-but-broader-blast-radius and minted-but-slower. My position: per-workflow minting is non-negotiable for blast radius; if it is too slow, narrow the *pool* to short-lived per-batch keys rather than going back to an ambient key.
2. **Is the Skills MCP server in-scope to be hardened to this degree in Phase 8, or is Phase 8's MCP server a "prefiguring" prototype where a lighter profile is acceptable?** The roadmap says "prefiguring the eventual MCP topology." I designed full seccomp/mount confinement; a lighter design might argue that is premature for a prototype. My position: the process boundary is cheap and the confinement is the *point* of doing the prototype right.
3. **HMAC-tagging every hot-view value vs. trusting Redis on a private network.** The best-practices design may argue a private, ACL'd Redis is enough and HMAC is belt-and-suspenders. My position: ~0.3ms and 32 bytes is too cheap to skip, and "fail-closed to cold storage on tamper" is a property worth having; but the synthesizer should weigh it against the key-rotation operational cost (Risk 3).
4. **Where does the manifest-validation pipeline live relative to ADR-0031's existing "Supervisor validates plugins via Pydantic at startup"?** ADR-0031 already mandates Pydantic validation and import-path resolution at startup. My design *adds* the import-path *allowlist*, the scope-claim guard, the `extends` cycle/depth bound, and the budget clamp. The synthesizer should confirm these are additive hardening of ADR-0031's stated mechanism, not a contradiction — I read them as additive, but ADR-0031 does not explicitly name an import-path allowlist, so this is the one place to check for ADR drift.
5. **Should the `PlannerDecisionLog` be a standalone store in Phase 8, or should Phase 8 already write into a shape Phase 9's canonical Postgres event log will adopt?** design.md's Phase 9 note says attempt logs and plugin-resolution records "migrate to event-stream projections" at Phase 9. I built the log event-sourced and hash-chained precisely so that migration is a re-pointing, not a rewrite — but the synthesizer should confirm Phase 8 is not expected to *defer* the log to Phase 9 entirely. My position: the exit criterion "logged on every workflow" forces the log to exist in Phase 8; building it event-sourced now is the cheap-correct choice.
