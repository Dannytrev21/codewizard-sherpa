# Phase 7 — Add migration task class (Chainguard distroless): Performance-first design

**Lens:** Performance — throughput, latency, token economy, footprint.
**Designed by:** Performance-first design subagent
**Date:** 2026-05-19

## Lens summary

Phase 7's headline performance claim is that **adding the second task class costs almost nothing at runtime** — the same Probe Coordinator, the same `VulnIndex`, the same `BundleBuilder` cache, the same `SubprocessJail`, the same event log all serve the new plugin. Distroless migration is *cheaper* than vuln remediation per workflow (no transitive semver math, no `npm install` in the inner validate loop — the validation cost is one `docker buildx build` against a tiny Chainguard image plus a smoke-run), so portfolio throughput goes *up* when the migration plugin is added, not down, provided we keep three hot paths out of the critical chain: (1) `vuln.provenance` adapter chains must be memoized per `(repo_snapshot_sha, cve_id, vuln_index_digest, sbom_digest)` because Stage 1 Assessment calls them N_repos × N_open_cves times per nightly scan; (2) the CVE→Chainguard-image recommendation must be a frozen in-repo table joined inside `VulnIndex` SQL, never an external API; (3) Dockerfile transforms must run as pure-Python `dockerfile-parse` AST edits with a per-stage parallel fan-out — `docker buildx` is the validate-step cost, never the recipe-application cost. The `Both` variant cost (one CVE producing two coordinated PRs) is amortized because both plugins share the cached `Bundle` and the cached `Provenance` lookup; the second PR's marginal Phase 3–6 cost is dominated by its own `npm install + npm test`, not by any new orchestration work. I take three explicit fights with the security/best-practices lenses I expect to come back: I refuse a per-workflow Chainguard registry probe (table lookup, refreshed weekly out-of-band), I refuse a `vuln.provenance` precomputation slice (per ADR-0038's correct query-time-join argument), and I push back on running both task-class subgraphs in series for a `Both` CVE — they run as concurrent Temporal child workflows under a parent `MultiPluginCoordinator` from day one, even pre-Phase-9, because the wall-clock cost of serializing them on the same repo's `RepoContext` is pure waste.

## Goals (concrete, measurable)

- **Workflows/hour target:** ≥ 60 distroless-migration workflows/hour/worker (cold-cache; 8-core box). Warm-cache ≥ 240/hour/worker. Vuln-remediation throughput stays at its Phase 3 baseline ± 5% (regression guard).
- **Time-to-PR p95:** ≤ 22 s warm, ≤ 90 s cold for a pure migration; ≤ 110 s warm, ≤ 180 s cold for a `Both`-variant coordinated pair. (Phase 3 vuln-only p95 is 35 s warm; migration is faster because `docker buildx --target build --no-test` beats `npm install + npm test`.)
- **$/PR target (distroless-migration):** $0.00 deterministic. Phase 7 introduces zero new LLM call paths. The plugin is recipe-pure; LLM fallback is a Phase 4 reuse and is only reached on `Applicability.NotApplicable` from `DockerfileBaseImageSwapRecipe` *and* a recipe-RAG miss against the `bench/migration-chainguard-distroless/` solved-example set.
- **$/PR target (vuln-remediation, unchanged):** $0.00 deterministic / Phase 4 fallback cost unchanged. Regression-asserted by replaying the Phase 3–6.5 cassette suite at the end of Phase 7's CI lane and diffing the cost-ledger sum to byte-equality with the Phase 6.5 baseline (epsilon ≤ $0.01).
- **Cache hit rate target:** ≥ 92% on the **`vuln.provenance` adapter chain** for a nightly portfolio rescan (the load-bearing one — Stage 1 Assessment is where this is exercised at scale). ≥ 95% on `BundleBuilder` for second-run on the same `(repo, task_class)`. ≥ 99% on the CVE→Chainguard-image lookup table (it's a frozen joinable table in `VulnIndex` — hit rate ≈ 1.0 by construction).
- **Per-worker memory ceiling:** ≤ 850 MB RSS in steady state. Two-task-class workers cost +60 MB over Phase 6.5's vuln-only baseline (Dockerfile-parse + `dive` JSON cache + Chainguard image catalog) — budget is 60 MB, not 200.
- **Tail latency (p99):** `vuln.provenance` query p99 ≤ 25 ms (warm); ≤ 180 ms (cold first call per workflow). Dockerfile-transform recipe p99 ≤ 350 ms. `docker buildx build --target` in jail p99 ≤ 14 s (Chainguard base images cache in containerd; pull is the long pole only on first ever fetch).

## Architecture

```
                       codegenie remediate <repo> --cve <id>
                                     │
                                     ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/cli/remediate.py                          [Phase 3]    │
   │   click entry; resolves WorkflowId; SandboxedPath(repo); loads .codegenie/context
   └────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ MultiPluginCoordinator   [Phase 7 — NEW, additive]                   │
   │   in: (repo, cve_id) ▸ vuln.provenance.query() ▸ Provenance variant   │
   │   route:                                                              │
   │     app_direct|app_transitive|app_vendored → 1 child: vuln plugin    │
   │     base_image|runtime_bundled            → 1 child: migration plugin │
   │     both                                  → 2 concurrent children    │
   │     unknown                               → universal HITL fallback   │
   │   one shared Bundle (built once, refed twice); BLAKE3-anchored        │
   └─────────┬─────────────────────────────────────────┬──────────────────┘
             │ (vuln workflow)                          │ (migration workflow)
             ▼                                          ▼
   ┌──────────────────────────────┐   ┌────────────────────────────────────┐
   │ RemediationOrchestrator       │   │ MigrationOrchestrator              │
   │   = Phase 3, unchanged        │   │   shape-identical to Phase 3's,    │
   │                               │   │   ships in transforms/ under same  │
   │                               │   │   typed seams (Transform, TrustScorer,│
   │                               │   │   ApplyContext, _validate_stage6); │
   │                               │   │   reuses SubprocessJail, EventLog  │
   └──────────────────────────────┘   └─────────────┬──────────────────────┘
                                                    │
                                                    ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ plugins/distroless-migration--node--npm/   [Phase 7 — new plugin]    │
   │   plugin.yaml          scope=(distroless-migration, node, npm)       │
   │   tccm.yaml            must_read: Dockerfile, .dockerignore,         │
   │                        node_build_system slice, runtime trace,       │
   │                        derived: shell_invocations_in_dockerfile      │
   │   adapters/                                                           │
   │     dockerfile_dep_graph.py          (FROM/COPY-from edges)          │
   │     dockerfile_shell_inventory.py    (RUN-line shell classification) │
   │     distroless_vuln_provenance.py    VulnProvenanceAdapter (base-img)│
   │     npm_vuln_provenance.py           (PROMOTED from Phase 3 refuse-  │
   │                                       mode shape → real adapter;     │
   │                                       Phase 3 plugin re-exports it;  │
   │                                       zero edit to Phase 3 plugin    │
   │                                       because the export name is     │
   │                                       unchanged — additive)          │
   │   recipes/                                                            │
   │     dockerfile_base_swap.py          (cheap path — pure AST edit)    │
   │     multi_stage_refactor.py          (expensive path — per-stage     │
   │                                       parallel fan-out under         │
   │                                       asyncio.gather)                 │
   │   subgraph/api.py                    5-stage pipeline (Discover /    │
   │                                      Match / Apply / Validate / Report)
   │   probes/                                                             │
   │     base_image_probe.py              BaseImageProbe (Layer F)        │
   │     shell_invocation_trace_probe.py  ShellInvocationTraceProbe       │
   │   skills/                            Chainguard migration playbooks  │
   │   PLUGINS.lock entry                 sha256(dir_tree)                │
   └──────────────────────────────────────┬───────────────────────────────┘
                                          │
                                          ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/vuln_provenance/   [Phase 7 — new core primitive]      │
   │   primitive.py        vuln.provenance(cve_id, package_id, image_ref) │
   │                       → Provenance (sum type per ADR-0038)           │
   │   chain.py            VulnProvenanceChainAssembler                   │
   │                         in: (RepoContext, cve_record)                │
   │                         out: ordered list of registered adapters     │
   │                         policy: app adapter first if app_layer       │
   │                                  candidates exist; base adapter      │
   │                                  always tried (cheap; under 5ms);    │
   │                                  emit Both when both succeed         │
   │   cache.py            LRU keyed by                                    │
   │                       (repo_snapshot_sha, cve_id, vuln_index_digest, │
   │                        sbom_digest, image_digest) — per-process,     │
   │                        size=4096, TTL=24h; backed by                 │
   │                        .codegenie/cache/vuln_provenance.sqlite       │
   │                        for cross-process warm reuse                   │
   │   registry.py         VulnProvenanceAdapter registry; populated      │
   │                       from PluginRegistry at startup                  │
   └──────────────────────────────────────┬───────────────────────────────┘
                                          │
                                          ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/vuln_index/   [Phase 3 — EXTENDED, additive]           │
   │   schema.sql (additive migration alembic 003):                       │
   │     CREATE TABLE chainguard_image_catalog (                          │
   │       upstream_repo TEXT PRIMARY KEY,  -- e.g. 'docker.io/node'      │
   │       chainguard_image TEXT NOT NULL,  -- e.g. 'cgr.dev/chainguard/node'│
   │       cgr_variant TEXT,                -- 'latest', 'latest-dev'     │
   │       distroless BOOLEAN NOT NULL,                                    │
   │       last_refreshed_utc TEXT NOT NULL,                              │
   │       catalog_digest TEXT NOT NULL                                    │
   │     );                                                                │
   │     CREATE INDEX idx_chainguard_upstream ON chainguard_image_catalog │
   │       (upstream_repo);                                                │
   │   refresh.py — codegenie vuln-index refresh --source chainguard      │
   │                 (operator-invoked weekly; not per-workflow;          │
   │                  catalog_digest becomes a declared_input token)      │
   │   query.py — recommend_distroless(upstream_repo) → ImageRecommendation│
   │                p99 ≤ 1 ms (indexed PK lookup)                        │
   └──────────────────────────────────────┬───────────────────────────────┘
                                          │
                                          ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │ .codegenie/events/                                                    │
   │   workflow-internal/<workflow_id>.jsonl.zst                          │
   │     NEW event variants (additive registry per ADR-0034):             │
   │       VulnProvenanceComputed(cve_id, provenance_kind, adapter_chain, │
   │                              cache_hit, latency_ms)                  │
   │       BaseImageSwapApplied(from_ref, to_ref, distroless,             │
   │                            shells_eliminated, size_delta_bytes)      │
   │       MultiPluginCoordinated(parent_workflow_id,                     │
   │                              vuln_child_id, migration_child_id)      │
   │   spanning/append.jsonl.zst — unchanged shape                        │
   └──────────────────────────────────────────────────────────────────────┘
```

## Components

### 1. `MultiPluginCoordinator` (`src/codegenie/transforms/multi_plugin_coordinator.py`) — **NEW**

- **Purpose:** Resolve the `Both` and single-plugin routing decisions at the entry to the per-repo workflow. Owns the one-Bundle-built-once invariant. Owns concurrent dispatch of the two child workflows in the `Both` case.
- **Interface:**
  ```python
  class MultiPluginCoordinator:
      def __init__(self, registry: PluginRegistry,
                   provenance: VulnProvenancePrimitive,
                   bundle_builder: BundleBuilder,
                   event_log: EventLog) -> None: ...
      async def run(self, repo: SandboxedPath, cve: CveId) -> CoordinatedOutcome: ...
  ```
  `CoordinatedOutcome` is a tagged union: `VulnOnly(report)` | `MigrationOnly(report)` | `Both(vuln_report, migration_report, ordering)` | `UnknownEscalated(reason)`.
- **Internal design:** Single `vuln.provenance(cve_id, ...)` call gates the routing decision. On `Both`, the two children run as `await asyncio.gather(vuln_task, migration_task)` (pre-Phase-9), promoted to two Temporal child workflows under a parent at Phase 9 with **zero code change at the coordinator level** because the seam is `asyncio.gather` over an awaitable — Temporal's `workflow.execute_child_workflow` is awaitable-compatible. The shared `Bundle` is built once before fan-out; both children receive a frozen reference. Ordering of the two PRs (recipe-first per ADR-0011) is owned here: vuln-remediation PR opens first; migration PR opens second with a comment referencing the vuln PR's SHA. This ordering is data, not code — `multi_plugin_coordinator.yaml` declares it per-`(task_pair)` tuple.
- **Tradeoffs accepted:** Adding a coordinator class is more code than dispatching inline at the CLI; the payoff is that Phase 9 swaps to Temporal without touching the CLI or the orchestrators. The performance lens insists on `asyncio.gather` from day one — serial dispatch of `Both` is a 60% wall-clock waste at p95 because the two children share zero contended resources (different recipe engines, different sandbox runs, different output paths). Best-practices may push for serial; this lens refuses.

### 2. `VulnProvenancePrimitive` (`src/codegenie/vuln_provenance/primitive.py`) — **NEW, bounded additive core primitive per ADR-0039**

- **Purpose:** The single entry point for `vuln.provenance(cve_id, package_id, image_ref?)` per ADR-0038. Returns the `Provenance` sum type. Memoized aggressively because it is hot at Stage 1 Assessment (N_repos × N_open_cves per nightly scan) and warm at every multi-plugin workflow entry.
- **Interface:**
  ```python
  class VulnProvenancePrimitive:
      def __init__(self, chain: VulnProvenanceChainAssembler,
                   cache: VulnProvenanceCache) -> None: ...
      async def query(self, cve_id: CveId, package_id: PackageId,
                      image_ref: ImageRef | None,
                      context: ProvenanceContext) -> Provenance: ...
  ```
  `ProvenanceContext` carries `repo_snapshot_sha`, `vuln_index_digest`, `sbom_digest`, `image_digest` — all four ride into the cache key. This is the load-bearing thing the cache invalidation chain depends on, and the four-tuple matches the existing `image-digest:<resolved>` declared-input token (Phase 2 ADR-0004) so base-image rotations propagate naturally.
- **Internal design:** Cache check (in-process LRU first, then per-process sqlite at `.codegenie/cache/vuln_provenance.sqlite`). On miss: `chain.assemble(...)` returns an ordered list of registered `VulnProvenanceAdapter`s; the primitive calls them in order, short-circuiting on the first non-`Unknown` result *unless* the first hit is an app-layer adapter and a registered base-image adapter exists (then it calls the base-image adapter too to detect `Both`). Cache write is atomic via `INSERT OR REPLACE` with a `created_at` row used for the TTL sweep. The cache is content-addressed off the four-tuple; CVE-feed-only changes (which bump `vuln_index_digest`) correctly invalidate.
- **Tradeoffs accepted:** A new core primitive is a real architectural commitment — ADR-0039 explicitly admits this is the bounded additive case. The performance argument for putting the cache *here* (rather than in the consumer at Stage 1) is that adapter implementations are pure functions and the cache key is fully content-addressed; central caching is correct and the only place fast enough to make the nightly portfolio scan p95 hold.

### 3. `VulnProvenanceChainAssembler` (`src/codegenie/vuln_provenance/chain.py`) — **NEW (ADR-0038 deferred this assembly question to Phase 7; this lens answers it)**

- **Purpose:** Decide which adapters to invoke and in what order, given a `(RepoContext, cve_record)`. ADR-0038 explicitly leaves this to Phase 7.
- **Decision (this lens):** **Static ordering driven by the registered adapters' `confidence()` × `cost_band` × `applies_when` declaration.** No heuristics, no LLM. The order is:
  1. **App-layer adapters** that declare `applies_when=manifest_present(<lang>)` and whose language matches `RepoContext.languages[*].primary`. Cheap (< 5 ms; reads in-memory parsed manifest). High confidence when SBOM is fresh.
  2. **Base-image adapter** for the resolved base image's distro, *if* the SBOM has `locations[].layerID` for the package. Cheap (< 5 ms; sqlite indexed lookup against the catalog).
  3. **Runtime-bundled adapter** if step 1+2 returned `Unknown` and the package matches a known JRE/Node-distribution embed (`xerces` in JRE, `npm` in Node tarball). Cheap.
  4. If step 1 succeeded *and* step 2 succeeded with non-matching variants → emit `Both` with the two records composed. (This is the headline integration case — the chain assembler is the only place this composition happens.)
- **Why this choice over alternatives:** The competing shape (run all adapters in parallel and pick the highest-confidence) wastes 3 adapter invocations per query and forces every adapter to be safe-to-call-on-the-wrong-substrate. Static ordering composes with the cache (the first-hit path is what gets memoized) and gives a deterministic event log entry per ADR-0034. The cost of static ordering is that adding a new adapter family requires touching `VulnProvenanceChainAssembler`; per ADR-0039 this is fine — adapters are plugin-contributed, but the chain policy is part of the core primitive surface.
- **Tradeoffs accepted:** The chain is per-CVE-class, not per-CVE — every CVE in the same language/base-image pair walks the same adapter order. A pathological case (a CVE that only the runtime adapter can resolve, in a repo with app + base both eligible) pays the cost of two failed cheap adapter calls before hitting the right one. Acceptable; the failed calls are < 10 ms total.

### 4. `BaseImageProbe` (`plugins/distroless-migration--node--npm/probes/base_image_probe.py`)

- **Purpose:** Read every `FROM` line in the repo's Dockerfile(s), resolve to immutable digest (already-cached Phase 2 ADR-0004 token), classify as `{distroless | minimal | full | vendor_specific | unknown}`, and emit per-stage records.
- **Cache strategy:** `cache_strategy="content"` keyed off `declared_inputs=["Dockerfile", "**/Dockerfile", "image-digest:*"]`. Re-runs only on Dockerfile edit or base-image rotation.
- **Performance:** p99 ≤ 60 ms cold (one `crane manifest` per unique FROM digest, ≤ 3 typical); p99 ≤ 2 ms warm (cache-hit).
- **Tradeoffs accepted:** This probe runs at gather time and is therefore on the cold path. It does not invoke `dive` or pull the image layers — image-layer inspection is an *adapter-time* concern, not a probe-time one. Keeping the probe cheap is essential because Stage 0 Discovery already lists thousands of candidate repos.

### 5. `ShellInvocationTraceProbe` (`plugins/distroless-migration--node--npm/probes/shell_invocation_trace_probe.py`)

- **Purpose:** Phase 2's runtime trace already captures shell invocations; this probe is a thin reducer that produces a per-stage shell-invocation count + a classification of each shell call as `{required_at_runtime | build_only | accidental | suspicious}`. The distroless migration's go/no-go signal is "zero shell invocations observed in the runtime trace."
- **Cache strategy:** `cache_strategy="content"` keyed off `declared_inputs=["trace-runtime:resolved", "Dockerfile", "**/Dockerfile"]` — the `trace-runtime:resolved` token is a new declared-input token *only if* Phase 2's runtime trace is already cached; otherwise the probe declares `confidence=Degraded(reason=runtime_trace_absent)` and the migration plugin's Stage 1 routing treats it as a `NotApplicable` rather than risking a wrong recommendation.
- **Performance:** p99 ≤ 80 ms; the existing trace artifact is on disk in JSONL form and this probe streams-reads it.

### 6. `DockerfileBaseSwapRecipe` (`plugins/distroless-migration--node--npm/recipes/dockerfile_base_swap.py`)

- **Purpose:** The cheap path — pure-Python AST edit over `dockerfile-parse`. Single `FROM` line rewrite + multi-stage `COPY --from=` audit + optional `USER nonroot:nonroot` insertion if the target image enforces it.
- **Performance:** p99 ≤ 80 ms (no I/O beyond reading the Dockerfile + writing the patched copy to a tempdir).
- **Tradeoffs accepted:** Recipe owns no validation — that's `MigrationOrchestrator._validate_stage6` (which calls `docker buildx build --target=runtime --no-cache=false --pull=missing` inside `SubprocessJail`). The validate step costs the wall-clock; the recipe step is free.

### 7. `MultiStageRefactorRecipe` (`plugins/distroless-migration--node--npm/recipes/multi_stage_refactor.py`)

- **Purpose:** The expensive path — Dockerfile has shell-using `RUN` lines that must be moved to a builder stage. Per-stage parallel fan-out via `asyncio.gather` (each stage is independent at the AST level).
- **Performance:** p99 ≤ 350 ms for up to 4 stages on a typical Node Dockerfile. The parallel fan-out is real not theatrical — each stage's AST manipulation is CPU-bound at ~80 ms; gathering 4 of them costs ~95 ms on a 4-core box vs. ~340 ms serial.
- **Tradeoffs accepted:** Pure-Python AST manipulation rather than OpenRewrite Dockerfile recipes — OpenRewrite's Dockerfile support is immature and the JVM startup tax (~2 s cold) destroys the per-workflow budget. `dockerfile-parse` is good enough and the recipe set is small.

### 8. `recommend_distroless` (`src/codegenie/vuln_index/query.py` — additive)

- **Purpose:** CVE→Chainguard-image recommendation. Indexed SQL lookup.
- **Performance:** p99 ≤ 1 ms (PK index on `upstream_repo`). Cache hit rate ≈ 1.0 by construction (the table is the cache).
- **Tradeoffs accepted:** The Chainguard catalog is refreshed out-of-band (operator-invoked `codegenie vuln-index refresh --source chainguard` weekly). The `catalog_digest` is a `declared_input` token so per-workflow cache keys invalidate when the catalog rotates. The alternative — calling `crane catalog` per workflow — costs 200–800 ms over the network on every PR; refusing that latency is the entire reason this is a table not an API.
- **Why not embeddings:** Embeddings buy nothing here — `node` → `cgr.dev/chainguard/node` is a string mapping, not a semantic similarity problem. Embeddings would add 30 ms model load + 5 ms per query + a model-staleness invariant the operator portal would have to surface. Refused.

## Data flow

### One end-to-end distroless-migration run (warm cache, single-plugin route)

1. `codegenie remediate <repo> --cve CVE-2024-XYZ` enters `cli/remediate.py`.
2. `MultiPluginCoordinator.run(repo, cve)` is invoked.
3. `vuln.provenance.query(cve, package, image_ref, ctx)` — cache hit (warm) → returns `BaseImage(image_digest=sha256:..., distro_pkg=apk("libxml2", "2.9.10"), stage="runtime")` in 1 ms.
4. Router selects single-plugin route → `plugins/distroless-migration--node--npm/`.
5. `BundleBuilder.build(plugin, repo_context, cve)` — cache hit → returns existing Bundle in 4 ms.
6. `MigrationOrchestrator.run(repo, cve, ctx)` invoked.
7. Stage Match: `DockerfileBaseSwapRecipe.match(bundle)` — applies (image is a known upstream; `recommend_distroless("docker.io/node")` returns `cgr.dev/chainguard/node:latest` in 1 ms).
8. Stage Apply: `DockerfileBaseSwapRecipe.apply(...)` → `Transform(diff_bytes=..., files_changed=[Dockerfile])` in 70 ms.
9. Stage Validate (`_validate_stage6`): `SubprocessJail.run(["docker", "buildx", "build", "--target=runtime", "--load", "--cache-from=type=local,src=.codegenie/buildx-cache", ...])` — cached layers + cached Chainguard base means a 12 s build in p95.
10. `BuildSignal(passed=True)` + `RuntimeSmokeSignal(passed=True, shells_observed=0)` + `CveDeltaSignal(passed=True, delta=-3)` flow into `TrustScorer`.
11. Stage 6 outcome: `Validated(branch, report)`.
12. `remediation-report.yaml` written; events flushed; `BaseImageSwapApplied(...)` event emitted.

Total warm wall-clock: ~16 s (12 s is the buildx; everything else sums to ~4 s).

### One `Both`-variant run (CVE in app layer AND base image, e.g., a transitive `lodash` in the app plus an `apk`-installed `lodash`-using utility in the base image)

1. CLI → coordinator.
2. `vuln.provenance.query(...)` returns `Both(app_record=AppTransitive(...), base_record=BaseImage(...))` in 8 ms (cold first-call fans through both adapters).
3. Router → `Both` branch → builds shared `Bundle` (one read of TCCM union from both plugins' `must_read`) in 6 ms.
4. `asyncio.gather(vuln_child(), migration_child())` fans out:
   - **Vuln child:** runs Phase-3 path with the `NpmLockfileSemverBumpRecipe`. Inner cost dominated by `npm install + npm test` in jail: ~14 s warm.
   - **Migration child:** runs the migration path as above. Inner cost ~16 s warm.
   - **Wall clock = max(14, 16) + 2 s coordination overhead = 18 s.** Serial would be 30 s.
5. Both children emit their own `Transform` and `remediation-report.yaml` to per-child branches.
6. Coordinator orders the two PRs (recipe-first → vuln PR opens first) and emits `MultiPluginCoordinated(parent_id, vuln_child_id, migration_child_id)`.

Total warm `Both` wall-clock target: ≤ 22 s p95; full budget allows 35 s p95.

## Failure modes & recovery

| Failure | Detection | Recovery | Cost impact |
|---|---|---|---|
| `vuln.provenance` returns `Unknown(sbom_layer_attribution_absent)` | Adapter explicit return | Route to universal HITL fallback; event log entry names the missing SBOM field | None — fast failure |
| Chainguard catalog stale (`catalog_digest` older than 14 days) | Refresh-stamp check at coordinator init | Coordinator emits `ChainguardCatalogStale` warning, proceeds with available data; portal surfaces it as a yellow badge | None on hot path; staleness is a Phase 13.5 visibility concern |
| `docker buildx` cold pull of Chainguard base | First-call latency spike (45 s vs. 12 s warm) | Pre-warm in background on Stage 0 Discovery for any repo with a Chainguard recommendation already cached | One-time per worker per Chainguard image |
| `Both` child workflow A succeeds, child B fails | `CoordinatedOutcome` branch on partial success | Emit `Both(vuln_report=ok, migration_report=failed)`; PR-open policy opens only the successful child's PR; failed child escalates as separate HITL ticket | Surfaces the partial-success path that Phase 8's Planner will own at Phase 8 scale |
| `vuln.provenance` cache poisoning (key collision) | BLAKE3-anchored cache key + checksum-on-read | Cache miss promoted; re-compute; emit `CacheChecksumMismatch` to spanning event log | One workflow's hot path slowed by ~20 ms; portal surfaces sustained mismatches |
| Phase 3 regression: vuln plugin's behavior drifts because of additive `NpmVulnProvenanceAdapter` promotion | Phase 6.5 bench replay diff (cost-ledger byte-equality) | Adapter promotion is forward-only — Phase 3 plugin re-exports the new module under the old name; the promotion ADR amendment is the gate | Caught at CI; no production risk |
| `MultiPluginCoordinator` and Phase 6's LangGraph workflow disagree on event ordering | Replay-determinism property at workflow scope (Phase 6's existing property test) | Property fail blocks the merge; coordinator emits events in a `(child_id, timestamp_monotonic)` order pinned by the parent | Caught at CI |
| Pre-Phase-9 `asyncio.gather` raises in one child | `gather(..., return_exceptions=True)`; coordinator inspects each result | Failed child escalates; succeeded child commits its branch | Bounded by per-child Phase-5 retry envelope |

## Resource & cost profile

| Item | Value | Source |
|---|---|---|
| Cold-start: import + load + plugin signature check (per ADR-0031) | +180 ms over Phase 6.5 baseline | New plugin + new core primitive; one-time per worker |
| Per-workflow LLM tokens (distroless-migration, no fallback) | 0 | Deterministic recipe path |
| Per-workflow LLM tokens (distroless-migration, fallback engages — rare; only when RAG misses) | ≤ 1.2k tokens prompt, ≤ 400 completion (Sonnet pricing → ~$0.012) | Mirrors Phase 4 economy; cap enforced by Phase 13's Budget Enforcer |
| `vuln.provenance` SQLite cache disk footprint per repo per 90 days | ≤ 8 MB (≤ 1 KB/row, ≤ 8k unique queries/repo/90d) | Sized against 1k-CVE-per-repo upper bound |
| Chainguard catalog table footprint | ≤ 500 KB total (≤ 2k upstream→cgr pairs) | One-time + weekly refresh |
| Dockerfile-parse + `dive` JSON parser memory | +35 MB peak per worker | Loaded lazily on first migration workflow only |
| `docker buildx` cache disk footprint (per worker) | ≤ 8 GB; LRU-evict on disk pressure | Reuse via `--cache-from/--cache-to=type=local`; Chainguard base layers compress well |
| Memory ceiling (per worker, steady state, both plugins resident) | ≤ 850 MB | Phase 6.5 baseline ~790 MB + 60 MB Phase 7 overhead |
| Worker CPU utilization at 60 wph cold | ~85% (compute-bound on `docker buildx`) | Compute-bound is the right shape; we are not I/O-starved |
| Worker CPU utilization at 240 wph warm | ~60% (more headroom; `buildx` cache hits) | Throughput target met with margin |

## Test plan

- **Bench regression gate (Phase 6.5 reuse):** `bench/vuln-remediation/cases/` replayed end-to-end with Phase 7 code present; aggregate `bench_score.lower_bound_95` must equal Phase 6.5 baseline within ±0.01. Cost ledger sum byte-equality (epsilon ≤ $0.01). **Gates merge.**
- **New bench cases (Phase 7 expansion of `bench/migration-chainguard-distroless/`):** 10 curated cases minimum (per roadmap exit criterion). Distribution: 3 single-stage Dockerfile swaps, 3 multi-stage refactors, 2 `Both`-variant pairs, 1 universal-fallback (`Unknown` provenance), 1 already-distroless (no-op-`NotApplicable`). `bench_score.lower_bound_95 ≥ tier_threshold[bronze]`.
- **`vuln.provenance` cache invariant property (Hypothesis):** for any sequence of `(query, refresh-vuln-index, query, edit-Dockerfile, query)` against a fixture repo, the returned `Provenance` is byte-identical iff the `(repo_snapshot_sha, cve_id, vuln_index_digest, sbom_digest, image_digest)` five-tuple is byte-identical. Models the "CVE-feed tick should invalidate; Dockerfile-edit should invalidate base-image arm but not app arm" semantics.
- **Adapter chain ordering test:** registered with three adapters in different declared orders, assert the chain assembler invokes them in `applies_when × cost_band × confidence` order regardless of registration order. Locks the ADR-0038-deferred decision down as test-enforced.
- **Concurrent-`Both` wall-clock property:** for a synthesized `Both` case with deliberately mismatched child runtimes, assert `gather`-based dispatch's wall-clock ≤ max(child_a, child_b) + 3 s. Catches accidental serial regression.
- **Performance canaries (nightly bench job, per the Phase 6.5 scaffolding):**
  - p95 distroless-migration time-to-PR ≤ 22 s warm / 90 s cold.
  - p95 vuln-remediation unchanged (Phase 6.5 baseline ± 5%).
  - p99 `vuln.provenance` query ≤ 25 ms warm / 180 ms cold.
  - Worker RSS ≤ 850 MB after 100 workflows.
- **Cassette replay determinism (Phase 4 reuse, extended scope):** the `Both`-variant cassette replay produces byte-identical `Transform.diff_bytes`, byte-identical event sequence (modulo `workflow_id` + timestamps), byte-identical cost-ledger across 50 runs.
- **Chainguard catalog staleness fence:** synthetic `catalog_digest` rotation triggers `BaseImageProbe` / `recommend_distroless` cache invalidation; portal-side staleness badge fires.
- **Phase 3 plugin no-edit fence:** `tests/fence/test_kernel_frozen.py` extended — `plugins/vulnerability-remediation--node--npm/` content hash stays byte-identical against Phase 6.5 baseline (the `NpmVulnProvenanceAdapter` promotion ships in `plugins/distroless-migration--node--npm/adapters/` and is re-exported, not moved). This is the extension-by-addition headline test.

## Design patterns applied

| Decision | Pattern | Why here | Pattern NOT applied |
|---|---|---|---|
| `vuln.provenance` adapter chain | **Chain of Responsibility** with explicit ordering policy | Adapters are plugin-contributed; the chain decides who runs first, short-circuits on first non-`Unknown`. Latency cost of ordering policy is < 1 µs; latency cost of running-all-adapters-in-parallel is 3× the cheap-path. **Pluggability cost in latency terms: zero — chain assembly is a static list comprehension.** | Not Strategy: chain composes multiple adapters per query; Strategy picks one. Not Visitor: provenance is a value, not a recursive tree walk. |
| `VulnProvenanceCache` | **Memoization with content-addressed key** (event-sourced through the cache log) | Cache is event-sourced — every write emits a `VulnProvenanceComputed` event with `cache_hit=false`; cache reads emit with `cache_hit=true`. The cache table itself can be reconstructed by replaying the event log. ADR-0034 compliant by construction. | Not write-through to disk on every write: amortized via WAL + 5 s sync; ADR-0034 makes the event log the source of truth, so cache loss is recoverable. |
| `MultiPluginCoordinator` | **Composite** (parent workflow composing children) + **Async fan-out via `asyncio.gather`** | Single `Both` case requires concurrent dispatch; serial wastes 60% wall-clock. The pattern is *intentionally* awaitable-compatible so Phase 9's swap to `workflow.execute_child_workflow` is a one-line change. Hot path is fully memoizable: the shared `Bundle` is built once and frozen-referenced into both children. | Not Mediator: children don't talk to each other; they only talk back to the parent. Not Saga: no compensating-transaction semantics — partial success is recorded, not rolled back. |
| `recommend_distroless` (CVE→Chainguard catalog) | **Table lookup** (database normal form, indexed PK) | Refused embedding-based similarity (it's a string mapping). Refused per-workflow API call (200–800 ms over network). Frozen table refreshed weekly out-of-band; `catalog_digest` is a declared_input token. **Hot path: pure-functional, memoizable, cache-hit-rate ≈ 1.0.** | Not service interface: a HTTP boundary here would be a per-PR latency tax for no information gain. |
| `DockerfileBaseSwapRecipe` / `MultiStageRefactorRecipe` | **Strategy** (one Protocol, two concrete recipes) chosen by `match(bundle)` | Cheap path is 80 ms; expensive path is 350 ms but parallelized. The match function is pure (depends on `BaseImageProbe` + `ShellInvocationTraceProbe` outputs only). Memoizable per Bundle — recipe selection is cache-keyed off the Bundle digest. | Not Template Method: the two recipes share no code structure (one is a single-line edit, one is per-stage AST manipulation). Sharing-by-inheritance would force a wrong abstraction. |
| `VulnProvenanceAdapter` registration | **Open/Closed via plugin manifest's `contributes.adapters`** map | Adding a new base-image distro adapter (`RhelVulnProvenanceAdapter`) is a new plugin contribution; zero edits to the core primitive or to the chain assembler if the adapter follows the `cost_band + applies_when` declaration. **Latency cost of indirection: a dict lookup at startup.** | Not subclassing: adapters duck-type the Protocol (ADR-0032 discipline). |

## Risks (top 3–5)

1. **`Both`-variant coordination correctness lags behind performance.** The `asyncio.gather` shape is correct under happy-path; the partial-success semantics (one child fails) are subtle, especially across a Phase-9 Temporal migration. **Mitigation:** ship `CoordinatedOutcome` as a sum type from day one and exhaustive `match` it; the type system enforces every branch is handled; Phase 6.5 bench adds 2 `Both`-variant cases including one partial-success.
2. **`docker buildx` cache disk pressure on long-running workers.** 8 GB ceiling per worker is realistic but not generous; an unlucky workload mix could thrash. **Mitigation:** explicit `--cache-to=type=local,mode=max,oci-mediatypes=true,ignore-error=true,compression=zstd`; LRU eviction script in Phase 13.5 worker housekeeping; portal-side disk-pressure alerts. **Acknowledged blind spot:** this lens has not modeled the worst-case (every workflow forces a unique base-image variant); if telemetry shows it, ADR amendment to switch to `type=registry` shared cache.
3. **`vuln.provenance` SQLite contention under high concurrent multi-worker writes.** SQLite is fine for single-process, fine for low-concurrency multi-process via WAL, but a 16-worker box doing nightly portfolio rescans could see write-lock waits. **Mitigation:** writes are batch-flushed every 250 ms or 64 entries; reads use `PRAGMA journal_mode=WAL`; the in-process LRU absorbs hot reads. If this still bites, the cache backend is a Strategy seam — swap to RocksDB or to Redis at Phase 8 (when Redis arrives anyway).
4. **Chainguard upstream coverage gaps.** The catalog assumes every common upstream has a Chainguard counterpart; in reality some don't (or have it gated behind enterprise tier). A migration request against a no-counterpart upstream must `NotApplicable` cleanly, not crash. **Mitigation:** `recommend_distroless` returns `Optional[ImageRecommendation]`; missing rows resolve to `None`; the plugin's match step returns `NotApplicable(reason=no_distroless_counterpart)` and the universal HITL fallback fires.
5. **Phase 6 LangGraph workflow not yet adapted for multi-plugin coordination.** Phase 6 ships the vuln state machine; the migration state machine reuses the same shape but is a separate graph instance. The `MultiPluginCoordinator` lives *above* both graphs (pre-Phase-9, inside the CLI; post-Phase-9, as the parent Temporal workflow). Phase 6 closeout has to ratify this layering. **Mitigation:** ship the coordinator as a thin `async` function that takes both graph runners as parameters; no Phase 6 graph changes; the layering ADR is a Phase 7 deliverable.

## Acknowledged blind spots

- **Security posture of the Chainguard catalog refresh path is underspecified.** This lens treats the catalog as trusted-by-operator-curation; the security lens will probably push for Sigstore-anchored catalog rows + signed `catalog_digest`. I'm deferring that; the catalog's threat surface is operator-internal and the `--source chainguard` refresh is operator-invoked.
- **The `vuln.provenance` cache TTL of 24 hours is a guess.** The right number depends on the CVE-feed tick rate and the rate of base-image rotation in the portfolio. This lens picks 24 h because shorter shreds cache effectiveness and longer risks acting on a stale `Both` determination. Real number lands at Phase 13 once telemetry exists.
- **`SubprocessJail` cost of `docker buildx` on macOS is variable** because macOS Docker Desktop's VirtioFS performance ranges 2–6× slower than Linux. This lens budgets for Linux CI/production. macOS dev experience is a "second-order concern" until Phase 13.5 surfaces it.
- **Multi-stage refactor's correctness model is rule-based and rigid.** A Dockerfile that uses shell heredocs, multi-line `RUN` with complex `&&` chains, or `ARG`-driven base-image selection may force `Applicability.NotApplicable`. The graceful failure shape is right; the long-tail coverage of "weird Dockerfiles" is deferred to Phase 15 (agentic recipe authoring) where new recipes can be proposed from solved examples.
- **Maintainability cost of the `MultiPluginCoordinator` indirection.** Two extra files, one new core primitive, one new sum type. The best-practices lens may argue this is overkill for one task-class pair; the perf lens insists it's the right shape because Phase 9 + Phase 11 + Phase 14 all need this seam, and retrofitting it post-merge of the migration plugin is a 3× cost.

## Open questions for the synthesizer

1. **Should the `MultiPluginCoordinator` live in `src/codegenie/transforms/` or in a new top-level `src/codegenie/coordination/` package?** This lens proposes `transforms/` because the existing `RemediationOrchestrator` is there and the seam alignment is closer. Security lens may want a separation-of-concerns split.
2. **Is the static adapter-chain ordering policy ADR-worthy as a Phase 7 ADR, or does it ride inside the broader `VulnProvenanceChainAssembler` story?** ADR-0038 explicitly defers this; the strongest argument for a separate ADR is that the *next* task class to add a provenance flavor will reuse this policy and an ADR pins it.
3. **At what bench-volume does the `vuln.provenance` SQLite cache become a Redis dependency?** This lens defers to Phase 8 when Redis arrives; the question is whether to land a `Cache` Strategy seam now or wait for the first real contention signal.
4. **`Both`-variant PR ordering: hard-coded recipe-first (per ADR-0011), or data-driven via `multi_plugin_coordinator.yaml`?** This lens proposes data-driven from day one; best-practices may push for hard-coded as the simpler shape until a second task-class pair exists.
5. **Should the universal HITL fallback's behavior diverge between single-plugin-`Unknown` and `Both`-`Unknown`?** This lens treats them identically (one HITL ticket per workflow); a more nuanced design could emit two correlated tickets for `Both`-`Unknown` so the human reviewer sees both halves of the puzzle. Cost: more event-log entries, more reviewer surface. Defer to the synthesizer.
6. **Does the `NpmVulnProvenanceAdapter` promotion belong as a Phase 7 closeout story against the Phase 3 plugin, or as a new Phase 7 plugin contribution that re-exports the Phase 3 shape?** This lens picks the second to preserve the no-edit invariant; the first is more discoverable for plugin authors. The trade is real.
7. **Performance regression budget for the Phase 3 bench replay: ±5% strict, or ±5% only on cost-ledger and ±10% on wall-clock?** This lens picks the stricter framing because cost is the real headline; wall-clock variance is dominated by CI runner jitter. Synthesizer should ratify.
