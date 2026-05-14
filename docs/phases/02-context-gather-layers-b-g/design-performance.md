# Phase 02 — Context gathering — Layers B–G: Performance-first design

**Lens:** Performance — throughput, latency, token economy, footprint.
**Designed by:** Performance-first design subagent
**Date:** 2026-05-14

## Lens summary

Phase 2 is where the gather pipeline stops being cheap. Phase 1 was a 1-second walk of `package.json` plus a few YAML reads; Phase 2 adds `scip-typescript` (8 s cold on a 50k-LOC repo), `syft` against a built image (3 s after a 47 s `docker build`), `grype` (5 s), `semgrep` (12 s), and `strace`-driven runtime traces across five scenarios (84 s). Cold gather *is* the localv2.md §3.2 figure of 3–6 minutes; Phase 2 is what makes that number real. The continuous-gather model from ADR-0006 (50,000+ gathers/day at portfolio scale) does not survive a naïve Phase 2 implementation.

My lens optimizes for three things in this order: **(1) keep every probe off the critical path that the cache can answer for it** — Phase 1's cache-hit math (cold 6 min → warm 30 s → incremental <10 s) is a function of `declared_inputs` discipline, and Layer B–G probes have wildly more inputs than Layer A (a SCIP index depends on every `.ts` file, a runtime trace depends on the built image digest, semgrep depends on every source file plus the rule pack); each probe's `declared_inputs` must be designed to maximize hit rate per cost tier. **(2) Bound the cold path** via cost-tier-aware concurrency: B/G CPU-bound parsers run at `cpu_count()` slots, C heavy I/O (docker build + strace) gets serialized to 1 slot, network probes (registry pulls) get a separate budget. The single fork-and-forget asyncio.Semaphore from Phase 0 is insufficient. **(3) Shape outputs for TCCM consumption** (ADR-0029, ADR-0030) — every structural artifact this phase produces is the input to a graph-aware derived query in Phase 3+. If the shape requires re-parsing or re-indexing at query time, we lose the cache leverage we already paid for in gather. `import_graph.reverse_lookup` and `test_inventory.tests_exercising` must be pre-projected as adjacency lists keyed by module path, not raw SCIP/tree-sitter dumps the Bundle Builder re-walks.

I deprioritize: pretty progress UX, semantically rich error messages, parallelism inside individual external tools (we don't control their threading), and the second-order observability surface (Phase 13 owns that). I will surface `IndexHealthProbe` (B2) as the most expensive thing the cache cannot save us from — and the cheapest thing the cache *makes load-bearing* — and design accordingly.

## Goals (concrete, measurable)

These are aggressive against the localv2.md baseline; the synthesizer should push back where the security or best-practices lens reaches a hard veto.

- **Workflows/hour target (Layer B–G only, single 8-core worker, steady state):** ≥ 600/hr (= 6 s p50 wall clock per incremental gather, ≥ 92% cache hit per probe across the portfolio). Cold gathers are amortized — at portfolio scale they happen once per repo per quarter.
- **Time-to-PR contribution from Layer B–G (p95):**
  - Incremental gather (one source file changed, SCIP delta only, no image rebuild): ≤ 2 s.
  - Warm gather (source unchanged, image unchanged, all caches valid): ≤ 0.8 s.
  - Cold gather, typical 50k-LOC Node service with built image: ≤ 180 s (vs. localv2.md §3.2's 3–6 minute baseline — the floor is image build + scip-typescript, not Python).
  - Cold gather *excluding* `docker build` (image already in local registry): ≤ 60 s.
- **$/PR target:** $0.00 for the gather pipeline itself (ADR-0005 — no LLM anywhere). Out-of-pocket cost is CPU-seconds + registry-pull bytes; budget ≤ 30 CPU-seconds per incremental gather, ≤ 360 CPU-seconds per cold gather.
- **Cache hit rate target per probe (rolling 7-day portfolio average):**
  - `SCIPIndexProbe` (B1): ≥ 70% (every push touching `.ts` invalidates).
  - `IndexHealthProbe` (B2): N/A — must run every gather (its job is to validate other probes' freshness; if cached itself, the whole staleness story collapses).
  - `SBOMProbe` (C2), `CVEProbe` (C3): ≥ 95% (keyed on image digest; only changes on `docker build`).
  - `RuntimeTraceProbe` (C4): ≥ 90% (keyed on image digest + scenario set).
  - `SemgrepProbe` (G1): ≥ 80% (keyed on source-tree hash + rule-pack version).
  - `SkillsIndexProbe`, `ConventionProbe`, `ExternalDocsIndexProbe` (D2, D5, D9): ≥ 99% (rule packs and skills change at human cadence, not commit cadence).
- **Per-worker memory ceiling:** ≤ 800 MB RSS during cold gather (dominated by `scip-typescript` and `semgrep` subprocesses we don't control); ≤ 300 MB RSS during warm gather; ≤ 120 MB RSS idle between gathers in Phase 14's long-lived worker mode.
- **p99 incremental gather:** ≤ 4 s. The 99th percentile is what determines worker-pool sizing in Phase 14, not the median.
- **TCCM consumer latency (forward-looking, no Redis yet):** the four ADR-0032 adapter operations (`dep_graph.consumers`, `import_graph.reverse_lookup`, `scip.refs`, `test_inventory.tests_exercising`) must be answerable in ≤ 50 ms p95 from Phase 2's on-disk outputs, with zero re-indexing. The hot views (ADR-0013) Phase 8 will project from these must reduce to ≤ 5 ms; Phase 2's job is to make the *cold* (un-Redis-cached) answer fast enough that Phase 8 is a 10× polish, not a 100× rescue.
- **IndexHealthProbe staleness blast radius:** zero workflows reach Stage 3 (planning) with `scip.confidence < 0.7` and no logged adapter downgrade. Operationalized as a fence-CI assertion against a deliberately-seeded stale-index fixture per the roadmap exit criterion.
- **Tokens per run:** 0. Phase 0 `fence` CI job continues to assert (Layer B–G adds zero LLM SDKs to `gather` extras).

## Architecture

```
                                codegenie gather <path>
                                          │
                                          ▼
                       ┌────────────────────────────┐
                       │  Phase 0/1 CLI + Coordinator│
                       │  (unchanged; PathIndex      │
                       │   already built; Layer A    │
                       │   slices already in cache)  │
                       └──────────────┬─────────────┘
                                      │
                  ┌───────────────────┴────────────────────────────┐
                  │           PLUGIN LOADER (Phase 2 addition)      │
                  │  - scans plugins/*/plugin.yaml at startup       │
                  │  - resolves (task × lang × build-tool) tuple    │
                  │    from RepoContext.layer_a slices              │
                  │  - unions probe requirements across resolved    │
                  │    plugin chain (ADR-0031)                      │
                  │  - registers adapter import paths (ADR-0032)    │
                  │  - Pydantic-validated; fail-fast on bad manifest│
                  │  - PHASE 2 SHIPS: kernel-only probes registered │
                  │    by `plugins/universal--*--*/plugin.yaml`     │
                  │    (the fallback); Phase 3 adds the first       │
                  │    concrete plugin (vuln-remed--node--npm)      │
                  └───────────────────┬────────────────────────────┘
                                      │
                                      ▼
        ┌─────────────────────────────────────────────────────────────┐
        │     COST-TIER COORDINATOR (Phase 2 extension of Phase 0)     │
        │                                                              │
        │   Tier 0  zero-fork, pure-Python (kernel)                    │
        │     ConventionProbe, ExceptionProbe, ADRProbe,               │
        │     RepoConfigProbe, RepoNotesProbe, SkillsIndexProbe,       │
        │     IndexHealthProbe                                         │
        │     concurrency: Semaphore(cpu_count())                      │
        │                                                              │
        │   Tier 1  CPU-bound subprocess (kernel)                      │
        │     SemgrepProbe, AstGrepProbe, GrepProbe,                   │
        │     SCIPIndexProbe (scip-typescript), BuildGraphProbe,       │
        │     GeneratedCodeProbe, NodeReflectionProbe                  │
        │     concurrency: Semaphore(max(cpu_count() // 2, 2))         │
        │                                                              │
        │   Tier 2  heavy I/O / container builds (kernel)              │
        │     DockerfileProbe, SBOMProbe, CVEProbe, CertificateProbe,  │
        │     EntrypointProbe, ShellUsageProbe                         │
        │     concurrency: Semaphore(2)  [docker daemon serializes     │
        │                                  builds anyway]              │
        │                                                              │
        │   Tier 3  network + sandbox  (kernel)                        │
        │     ExternalDocsProbe (Confluence/URL fetches),              │
        │     RuntimeTraceProbe (5-scenario strace)                    │
        │     concurrency: Semaphore(1) [strace cannot share a         │
        │                                running container instance]   │
        └─────────────────────────────────────────────────────────────┘
                                      │
                  ┌───────────────────┴────────────────────────────┐
                  │  PER-PROBE CACHE (Phase 0 + per-tier policy)    │
                  │  - Tier 0: blob hash over declared_inputs       │
                  │  - Tier 1: blob hash + tool-version stamp       │
                  │  - Tier 2: image-digest-keyed cache (orthogonal │
                  │    to source-tree hash; per-image, not per-run) │
                  │  - Tier 3: scenario-set + image-digest          │
                  └───────────────────┬────────────────────────────┘
                                      │
                                      ▼
                  ┌─────────────────────────────────────────────────┐
                  │  TCCM-SHAPED OUTPUT PROJECTIONS                  │
                  │  (Phase 2 addition; pre-rendered at write time) │
                  │                                                  │
                  │  .codegenie/context/raw/         (raw probe outs)│
                  │  .codegenie/context/projections/                 │
                  │    ├── import_graph.adj.json   (forward+reverse) │
                  │    ├── dep_graph.adj.json      (forward+reverse) │
                  │    ├── scip.symbols.idx        (mmap-able)       │
                  │    ├── test_exercises.adj.json (test → src files)│
                  │    └── _provenance.json        (which probes,    │
                  │                                 which versions,  │
                  │                                 fold-input hash) │
                  └─────────────────────────────────────────────────┘
                                      │
                                      ▼
                  .codegenie/context/repo-context.yaml  (envelope)
                  .codegenie/context/raw/                (probe blobs)
                  .codegenie/context/projections/        (TCCM hot paths)
                  .codegenie/events/                     (append-only;
                                                          Phase 9 will
                                                          project from)
```

Three things to read from the diagram:

1. **Cost tiers replace the single Phase 0/1 Semaphore.** A `RuntimeTraceProbe` taking 84 seconds inside the same concurrency budget as a `ConventionProbe` taking 8 ms is the architectural bug that kills cold-gather wall-clock. Per-tier semaphores let cheap probes finish during the long-tail of expensive ones without making the docker daemon queue 14 builds at once.
2. **The Plugin Loader runs at startup, not per-probe.** This phase ships the loader and the universal-fallback plugin only (per ADR-0031's "no-match fallback" — every workflow must have a known handler from day one). Phase 3 ships the first concrete plugin without re-architecting the loader. The kernel-resident Layer B–G probes register via the universal-fallback plugin's `contributes.probes:` list, not by being imported at coordinator-init time.
3. **TCCM projections are a write-time fan-out, not a query-time computation.** ADR-0030's `import_graph.reverse_lookup(module)` is an O(1) dict lookup against a projection if we pre-compute the reverse adjacency list at gather time; it's an O(N files) tree-sitter re-walk if we don't. Phase 2 pre-pays this cost so Phase 3's plugin and Phase 8's hot views inherit a cache that already knows the answer.

## Components

### 1. Cost-tier coordinator (extends Phase 0/1)

- **Purpose:** Run the right number of expensive probes at the right time. Phase 0/1's single `Semaphore(min(cpu_count(), 8))` is fine when every probe is a 50-ms YAML parse; it falls apart when one probe is `docker build` and another is `strace`-on-running-container. The tier model is the cheapest, smallest change to Phase 0 that fixes this.
- **Interface:** Each probe declares a new optional `cost_tier: Literal[0, 1, 2, 3]` field on the `Probe` class (default `0` for backward compatibility — Phase 0/1 probes are untouched). The coordinator holds four `asyncio.Semaphore`s sized per tier; `_acquire_for(probe)` picks the right one. This is **one** added field on the ABC and is gated by a Phase-2 ADR (`docs/phases/02-context-gather-layers-b-g/ADRs/0001-cost-tier-coordinator.md`) — same governance discipline as Phase 1's `parsed_manifest` field addition.
- **Internal design:**
  - Tier-0 cap: `cpu_count()` slots. Probes are pure Python, sub-100ms each. Letting all of them race finishes the cheap work before tier-1 needs to wait.
  - Tier-1 cap: `max(cpu_count() // 2, 2)`. CPU-bound external tools (`semgrep`, `scip-typescript`) consume their own CPU. Two of them on an 8-core box is the sweet spot; four contend.
  - Tier-2 cap: `2`. The docker daemon serializes builds at the daemon level anyway; running more in parallel just queues them and triples wall-clock variance. The cap of 2 lets a build + a `syft`-against-built-image run concurrently.
  - Tier-3 cap: `1`. Strace against a running container cannot share the container with another strace, and the runtime-trace scenarios *within* a probe run serially by design (startup, then smoke, then healthcheck, etc.).
  - **No global semaphore.** Tiers do not gate each other. A tier-3 strace run can be in flight while tier-0 conventions parse. This is the whole point.
- **Tradeoffs accepted:**
  - More state in the coordinator (four semaphores, one per probe acquire/release cycle).
  - Probes pick their own tier; misclassification means worse throughput. Mitigated by a CI lint that asserts each probe declares `cost_tier` explicitly (no default) and a per-tier wall-clock canary in `tests/bench/` that fails the build if a tier-0 probe's p95 exceeds 200 ms.
- **Pattern decision:** Plugin architecture (the kernel knows about tiers; probes self-classify). Refuses Strategy with one implementation — tiers are *data on the probe*, not a class hierarchy.

### 2. PluginLoader (`codegenie/plugins/loader.py` — NEW)

- **Purpose:** Operationalize ADR-0031 minimally in Phase 2. Ships the universal `(*, *, *)` fallback plugin so the kernel-resident Layer B–G probes are registered through the same mechanism Phase 3's concrete plugin will use — no special case in the coordinator, no kernel-resident "blessed" import paths.
- **Interface:**
  - `PluginLoader.discover(plugins_root: Path) -> PluginRegistry`: filesystem walk; one `plugin.yaml` per plugin directory; Pydantic-validated on load; fail-fast diagnostic naming file + field on any malformed manifest (per ADR-0031's "Schema enforcement and validation" section).
  - `PluginRegistry.resolve(task: TaskClass, lang: Language, build: BuildSystem) -> ResolvedPluginChain`: returns the ordered `extends` chain; in Phase 2 always resolves to `[universal--*--*]` because no concrete plugin exists yet.
  - `ResolvedPluginChain.probe_requirements() -> set[ProbeId]`: unions probe-requirement contributions across the chain. The coordinator's probe-set for the gather is this union plus Layer A probes (Layer A is universally required).
- **Internal design:**
  - The kernel ships *one* plugin in Phase 2: `plugins/universal--*--*/`. It declares: scope `(*, *, *)`, precedence `0` (lowest — every concrete plugin beats it), and contributes every Layer B–G kernel-resident probe (`SCIPIndexProbe`, `IndexHealthProbe`, `SemgrepProbe`, `RuntimeTraceProbe`, the full list) plus the universal HITL escalation subgraph (Phase 2 ships only a stub subgraph; Phase 6 makes it real).
  - **Adapter registration in Phase 2 is empty.** The universal fallback declares `contributes.adapters: {}` because no concrete language stack lives in the kernel. Phase 3's first plugin ships the four ADR-0032 adapters. Phase 2's job is to make sure the manifest mechanism exists and the loader fails-fast on bad imports — not to ship adapters yet.
  - **Plugin discovery is at CLI startup**, not per-gather. The registry is built once, cached in-process, invalidated only on `plugin.yaml` mtime change (a 4 ms `os.stat` check on each gather).
  - Pydantic models for `plugin.yaml` schema live at `codegenie/plugins/manifest.py`. Same domain-modeling discipline as ADR-0033 — `PluginId`, `PluginScope` (smart-constructor-parsed from `task--lang--build` strings), `PluginPrecedence`, `ExtendsChain`. No `dict[str, Any]` plugin manifest soup.
- **Tradeoffs accepted:**
  - Shipping the loader in Phase 2 before its first concrete consumer (Phase 3) feels speculative. Justified: the alternative is registering Phase 2's B–G probes via the Phase 0/1 import-side-effect mechanism and then refactoring them into a plugin in Phase 3 — that refactor would be either an "extension by editing" violation or a multi-week churn. Better to ship the seam now with one trivial plugin.
  - The universal fallback's subgraph is a stub. That's correct — Phase 2 is gather-only; subgraphs ship with consuming phases.
- **Pattern decision:** Plugin architecture (kernel never imports plugins by name; the loader is the registry). Registry pattern at the manifest level (the `PluginRegistry` is a typed dict). Hexagonal: the loader is a Port; "Pydantic-validated YAML on disk" is the only Adapter today, but Phase 14's webhook-driven loader and Phase 16's signed-plugin loader plug into the same Port.

### 3. IndexHealthProbe (B2 — the most important probe)

- **Purpose:** Make stale-index failures *loud*, not silent. Per ADR-0030: when SCIP is stale, `scip.refs` returns wrong call sites and the entire TCCM-driven Bundle is wrong. ADR-0032 declares the SCIP adapter's `confidence()` as the gate input to graceful degradation. `IndexHealthProbe` is what computes that confidence.
- **Interface:** Standard probe ABC. `name = "index_health"`, `layer = "B"`, `cost_tier = 0`, `applies_to_languages = ["*"]`, `applies_to_tasks = ["*"]`, `requires = []`. **`cache_strategy = "none"`** — the probe must run every gather; caching the freshness report is the same bug as caching `Date.now()`.
- **Internal design:**
  - Reads only Phase 2 probe outputs that already wrote to `.codegenie/context/raw/`. **It does no source-tree walk of its own** — the inputs are sibling-probe artifacts plus a small set of cheap repo facts.
  - Per-source-of-truth freshness checks (each is one logical assertion, all sub-millisecond):
    - **SCIP:** `(scip_indexed_commit == repo.HEAD)`, `(files_indexed / files_in_repo >= 0.95)`, `(indexer_errors == 0)`, `(scip_index_mtime > all source-file mtimes)`. Confidence is the harmonic mean of the four signals, snapped to `{trusted, degraded, unavailable}` per ADR-0033 sum-type discipline.
    - **Runtime trace:** `(traced_image_digest == current_built_image_digest)`, `(all configured scenarios present)`, `(no scenario_failed flag)`. Image-digest mismatch is the killer — and it's the most common silent failure in distroless migration, hence the load-bearing test.
    - **SBOM / CVE:** image-digest match.
    - **Semgrep:** `(scanned_files == files_in_repo for matching extensions)`, `(rule_pack_version matches probe's declared version)`.
  - The output slice is the localv2.md §5.2 B2 shape verbatim, with `confidence` modeled as a tagged-union `AdapterConfidence = Trusted | Degraded(reason: str) | Unavailable(reason: str)` per ADR-0033. `Degraded` and `Unavailable` carry a reason string the adapter dispatch (ADR-0032) and Phase 11 audit can read without parsing free text.
  - **Loud-not-quiet on degradation:** every `Degraded`/`Unavailable` confidence emits a Pydantic event written to `.codegenie/events/` (the Phase 9-shaped event log; see Component 8) AND a CLI warning visible in the run summary. Phase 14's continuous gather will dashboard these.
- **Performance argument:** `IndexHealthProbe` itself is sub-100ms — it does no work except read sibling outputs and run cheap assertions. The cost it imposes is the cost of *running every gather*, which against the cache-hit rate target is 1 invocation per incremental gather (most other probes hit cache). It is the cheapest probe in the system and the highest-leverage one.
- **Tradeoffs accepted:**
  - It depends on every other Layer B/C probe having already written its output. In the cache-hit case those outputs are loaded from cache rather than freshly written; the probe runs after the merge step (Phase 0's existing merge sequence handles this — `IndexHealthProbe` declares `requires` for every probe it consults; the existing topological ordering enforces it).
  - The probe knows about every other probe's output shape — coupling. Mitigated by exposing the freshness assertions as small per-probe `health_check(slice) -> AdapterConfidence` Protocol implementations, registered alongside each probe. `IndexHealthProbe` is a fold over those checks. New Phase 3+ probes self-register a health-check; `IndexHealthProbe` doesn't change.
- **Pattern decisions:** Tagged union for `AdapterConfidence` (illegal-states-unrepresentable: a `Trusted` cannot carry a `reason`, an `Unavailable` cannot lack one). Specification pattern for the per-source-of-truth assertion suite. Open/Closed: adding a new freshness signal is a new `health_check` registration, not an edit to `IndexHealthProbe`.

### 4. SCIPIndexProbe + projection (B1)

- **Purpose:** Run `scip-typescript` and write its output in two shapes — the raw `.scip` binary blob (for SCIP tooling that consumes it natively) AND a pre-computed adjacency-list projection at `projections/scip.symbols.idx` keyed by symbol so `scip.refs(symbol)` in ADR-0032's adapter is an O(log N) mmap'd lookup.
- **Interface:** Standard probe ABC. `cost_tier = 1`. `declared_inputs` includes every `.ts`, `.tsx`, `.js`, `.mjs`, `.cjs` in the repo plus `tsconfig*.json` plus the `scip-typescript` binary version stamp (so a tool upgrade invalidates the index — the alternative is silent staleness when the tool itself changes).
- **Internal design:**
  - Runs `scip-typescript index --output .codegenie/context/raw/scip-index.scip --infer-tsconfig` via `exec.run_allowlisted`. Hard cap `timeout_seconds = 300` (cold gather on a large monorepo); typical 8-15 s on a 50k-LOC repo per localv2.md §1.
  - After the binary write, a small in-process parser walks the SCIP protobuf using the `scip-python` reader library (added as a Phase 2 dep, ratified by ADR `0002-scip-python-reader-for-projections.md`). It emits `projections/scip.symbols.idx` as a sorted-by-symbol-id MessagePack-on-disk index (chosen over JSON for **deserialization speed** — MessagePack parses ~5× faster than JSON for the 100k-symbol shapes typical of a medium-sized service, which is the load-bearing property for the ADR-0032 adapter's p95 latency target). The index format is documented in `docs/phases/02-context-gather-layers-b-g/projection-formats.md`. The Phase 2 ADR captures: `scip-python` is read-only here (it's a parser, not an indexer; we use `scip-typescript` to *write*); the MessagePack-on-disk choice resolves the "should we re-parse `.scip` every query" question against ADR-0030's 50ms p95 target.
  - The projection structure: a length-prefixed list of `(symbol_id_bytes, ref_count, ref_offset)` records, sorted by `symbol_id_bytes`. Lookups by symbol are binary search over the header; ref payloads are mmap'd. No re-parse, no full-load.
  - **Incremental SCIP is NOT in Phase 2 scope.** `scip-typescript` does not support per-file incremental index update at the time of writing; we re-index the whole repo on any `.ts` change. This is the dominant cold-gather cost. Two mitigations: (a) cache key includes a Merkle root over `.ts` files, so an unchanged repo on a re-run is a cache hit (the common case in a portfolio); (b) the projection step is itself cached against the `.scip` blob hash, so even a SCIP re-index whose output happens to match (rare but possible for whitespace-only edits) skips the projection write.
- **Tradeoffs accepted:**
  - One full re-index per `.ts` change. The portfolio-scale economics still work because (i) the cache invalidation is per-repo, not per-org; (ii) `scip-typescript` upstream is moving toward incremental and Phase 14 can adopt it without changing the projection shape; (iii) the projection write is cheap (~500ms for a 100k-symbol service).
  - Adds `msgpack` and `scip-python` (parser-only) to `gather` extras. Two libraries, both pure-Python or pure-C with no LLM ancestry. Phase 0's fence test continues to pass.
- **Pattern decisions:** Functional core (the projector is pure: `.scip` bytes → projection bytes), imperative shell (the probe runs the subprocess and writes the artifacts). Adapter pattern (the projection IS the adapter interface — Phase 3's `NodeScipAdapter` reads this format directly, no translation needed).

### 5. Dependency graph + tree-sitter import graph (B5 + B3 + new projection)

- **Purpose:** Produce the three remaining ADR-0032 adapter inputs — `dep_graph` (forward+reverse package adjacency), `import_graph` (forward+reverse file-level edges from tree-sitter), and `test_inventory.tests_exercising` (test-file → exercised-source-file map) — as pre-projected adjacency lists.
- **Interface:**
  - `BuildGraphProbe` (B5 — Phase 2 promotes from "monorepo-only" to "always-runs"): emits `projections/dep_graph.adj.json` with forward edges `{package: [deps]}` and reverse edges `{package: [consumers]}`. Single repos collapse to a one-node graph.
  - `NodeReflectionProbe` (B3 — extended) + new `TreeSitterImportGraphProbe`: the latter is a `cost_tier=1` probe that runs `tree-sitter`-based import extraction across every source file and emits `projections/import_graph.adj.json` with forward+reverse adjacency.
  - `TestCoverageMappingProbe` (G3) emits `projections/test_exercises.adj.json` by joining its coverage data against the import graph.
- **Internal design:**
  - **Tree-sitter import extraction** runs in-process via `py-tree-sitter` bindings (already a Phase 1 dep per localv2.md §6 for the `tree-sitter` fallback). Per-file extraction is ~5 ms; for a 50k-LOC repo with 2k source files, ~10 s cold. **Concurrency: tier-1 cap (`cpu_count() // 2`)**, but the actual extraction parallelism comes from `concurrent.futures.ThreadPoolExecutor` *inside* the probe (the GIL releases for the tree-sitter C extension, so threading is real) — the probe sees one tier-1 slot but uses ~4 threads inside it. This is the second concurrency layer the Phase 0 architecture does not anticipate; it lives inside the probe, not the coordinator, so no Phase 0 contract change.
  - All three projections share a common file shape: `{"forward": {node: [neighbors]}, "reverse": {node: [neighbors]}, "_provenance": {...}}`. Adapter implementations (Phase 3) load the JSON once on first call and keep it in adapter-instance memory (~10 MB peak for a 50k-LOC service — well under the 800 MB worker ceiling).
  - **Projection invalidation is per-projection**, not per-gather. If `BuildGraphProbe` hit cache but `TreeSitterImportGraphProbe` re-ran, only `import_graph.adj.json` rewrites. Phase 0's per-probe-output write model already gives us this; we just have to keep projections out of `repo-context.yaml` (they're sibling artifacts in `projections/`).
- **Why this shape:**
  - **TCCM derived queries become O(lookup), not O(walk).** ADR-0030's `import_graph.reverse_lookup(module)` is `proj["reverse"][module]` — a dict access against a pre-built mapping, sub-millisecond. Without this projection, the adapter has to walk the SCIP index or re-parse tree-sitter output every call, which is the Phase 3 trap (cold queries dominate the Bundle Builder's p95).
  - **The "wider net" cases scale with `should_read` / `may_read` budget, not with repo size.** A `transitive_callers(file_set, depth=3)` query is a bounded BFS over the projection. On a 5k-file repo it's the same cost as on a 50k-file repo because the bound is on the result set, not the graph.
- **Tradeoffs accepted:**
  - Three sibling JSON files growing over repo size. For a 50k-LOC service the total projection footprint is ~5 MB, well below the per-gather storage budget.
  - The forward+reverse duplication doubles storage per graph. Cheaper than recomputing reverse at query time across the portfolio: a 5 MB write at gather time vs. a 50 ms recomputation per Bundle build × 50,000 gathers/day × 7+ TCCM queries per workflow.
- **Pattern decisions:** Functional core (graph projection is a pure fold over probe outputs). Adapter pattern at the file-format level (the projection format IS the ADR-0032 adapter contract; the adapter is a thin loader). Open/Closed: new graph types (call graph from runtime traces, code-ownership graph) land as additional projection files, never as edits to existing ones.

### 6. Tier-2 container probes (C1–C7) — image-digest-keyed cache

- **Purpose:** Make the C-layer probes cache against *image digest*, not against source-tree hash. A repo whose `Dockerfile` is unchanged but whose `package.json` changed re-runs A and B probes; the C-layer probes that consume the built image (SBOM, CVE, runtime trace, certificate) should hit cache as long as the image digest hasn't moved.
- **Interface:** The Phase 0 cache key derivation gets a per-probe override hook. Probes opt into image-digest keying by overriding `cache_key`:
  ```python
  class SBOMProbe(Probe):
      cost_tier = 2
      cache_strategy = "content"
      def cache_key(self, repo: RepoSnapshot, task: Task) -> str:
          image_digest = self._read_built_image_digest(repo)
          return hash_tuple(self.name, self.version, image_digest)
  ```
  The Dockerfile probe (C1) keys against the Dockerfile content. SBOM/CVE/runtime-trace key against the built image digest.
- **Internal design:**
  - **`DockerfileProbe` runs first within tier 2** (declares `requires = []`); emits the parsed Dockerfile and triggers `docker build` if no built image with the expected digest is present in the local registry (`docker images --digests --filter "label=codegenie.builds=<hash>"`). The build step is what costs 47 s in the localv2.md timing — and it's the cache key the rest of tier 2 inherits. We do NOT re-build if the digest matches.
  - **`SBOMProbe`, `CVEProbe`, `CertificateProbe`** all share the image digest as their cache key. Result: on a `package.json`-only change with no Dockerfile or lockfile change, all three hit cache. On a `Dockerfile` change, all three miss together — they share the cost of rebuilding the image once.
  - **`RuntimeTraceProbe`** keys on `(image_digest, scenario_set_hash, scenario_timeout_seconds)`. Scenario-set changes (a user adds an error-path scenario to config) invalidate. **The probe itself runs scenarios serially** (tier-3 cap of 1, internal serial loop) — there is no parallel-strace story that survives container determinism.
  - **All tier-2 probes share an `exec.run_allowlisted` wrapper that scrubs `docker`/`podman` output of timestamps**, image build-IDs, and ephemeral container IDs before hashing. Without this, two byte-identical runs of `docker build` produce non-identical stdout and break the cache. This wrapper lives in `codegenie/probes/_container/normalize.py`.
- **Tradeoffs accepted:**
  - The image-digest cache key bypasses the Phase 0 `declared_inputs` mechanism for these probes. **This is the one Phase 2 deviation from Phase 0/1's source-tree-hash cache discipline**, and it requires an ADR (`0003-image-digest-cache-keys.md`). The justification: the image digest IS the content the probe consumes; source-tree hash would force re-runs on every commit even when the built image hasn't moved, and at portfolio-scale 50k gathers/day × 5 container probes × 5 s saved per cache hit = a meaningful cost reduction.
  - The cache survives `docker system prune`. If the user prunes the image, the next gather rebuilds (it has to). The cache entry's image-digest key just becomes unresolvable — the probe re-runs, fills the cache, and life continues. This is correct.
- **Pattern decisions:** Strategy pattern at the cache-key level (probes choose source-tree-hash vs. image-digest keying via the existing `cache_key` override). Refuses making this a Phase 0 ABC change — the override hook already exists; we just exercise it.

### 7. Skills loader + conventions catalog + external docs (D2, D5, D8, D9)

- **Purpose:** The "human-cadence" probes — SkillsIndexProbe, ConventionProbe, ExternalDocsProbe, ExternalDocsIndexProbe — change at human writing speed (days/weeks), not commit speed (minutes). They must hit cache aggressively and pre-render their outputs for hot consumption.
- **Interface:** Standard probe ABC, all `cost_tier = 0` except `ExternalDocsProbe` (`cost_tier = 3` — does network fetches).
- **Internal design:**
  - **SkillsIndexProbe:** walks `~/.codegenie/skills/`, `.codegenie/skills/`, `~/.codegenie/skills-org/`. Parses YAML frontmatter only (the body is never loaded into `RepoContext`, per the localv2.md §5.4 D2 spec). Cache key includes file mtimes of every `SKILL.md` plus the Phase 0 schema version. Output: a flat list of `{name, description, applies_to, requires_evidence, required_tools, source_path}` records. ~10 ms cold on a typical Skills directory of ~30 entries.
  - **ConventionProbe:** loads `~/.codegenie/conventions/*.yaml`, validates each rule against a schema, indexes by `detect.type`. The detection itself doesn't run during gather — gather only enumerates available conventions; per-rule evaluation happens at Planner time (Phase 3+) to keep gather purely structural.
  - **ExternalDocsProbe (D8) + ExternalDocsIndexProbe (D9):** These are the two probes where caching has to be very aggressive — external fetches against Confluence/Notion are slow and rate-limited. Cache key: hash of `external_docs:` config + per-source fetch endpoint + per-source `last_modified` (which the source itself reports). Index (BM25 via Tantivy) is rebuilt only if any underlying doc changed.
  - **All four probes pre-render their TCCM consumption shapes.** `SkillsIndexProbe` writes a `projections/skills.by_applies_to.json` keyed by `(task_class, language)` so the Bundle Builder's "which skills apply" lookup is O(1). `ConventionProbe` writes `projections/conventions.by_detect_type.json`. The Phase 8 hot views (ADR-0013) project from these projections; same shape, just in Redis.
- **Tradeoffs accepted:**
  - The skills directory mtime walk is a few hundred `os.stat` calls. ~5 ms even on a large skills directory. Cheaper than caching the directory listing itself (which would need its own invalidation logic).
  - The Tantivy BM25 index is a directory of files, ~5 MB per ~50 docs. Acceptable; the alternative (re-indexing every gather) is 1-2 seconds we don't want to pay on the warm path.
- **Pattern decisions:** Registry pattern (skills register themselves by being on disk; the probe is the loader). Functional core (parsing + indexing). Refuses Strategy for the doc-source kinds — there are three (Confluence, Notion, filesystem URL list) and they share enough that a single source-walker with three loaders is cleaner than three Strategy implementations.

### 8. Append-only events stream (`codegenie/events/`)

- **Purpose:** Per ADR-0034, the canonical Postgres event log lands in Phase 9. Phase 2 cannot ship the database, but it can ship probe outputs in a *shape that projects cleanly* into the future event stream. Specifically: every probe that reports a degradation, a low-confidence answer, an adapter fallback, or a cache invalidation that surprised an operator emits a typed event to `.codegenie/events/<gather-utc>-<probe>.jsonl`.
- **Interface:** A small `codegenie/events/writer.py` exposes `emit(event: PhaseEvent)` where `PhaseEvent` is a Pydantic discriminated union per ADR-0033. Phase 2 ships three event variants:
  ```python
  class IndexHealthDegraded(BaseModel):
      kind: Literal["index_health_degraded"] = "index_health_degraded"
      probe_id: ProbeId
      confidence: AdapterConfidence
      reason: str

  class ProbeCacheInvalidated(BaseModel):
      kind: Literal["probe_cache_invalidated"] = "probe_cache_invalidated"
      probe_id: ProbeId
      reason: Literal["input_changed", "tool_version_changed", "schema_version_changed", "image_digest_changed"]

  class ExternalToolMissing(BaseModel):
      kind: Literal["external_tool_missing"] = "external_tool_missing"
      tool: str
      probe_id: ProbeId
      downgrade_path: str
  ```
- **Internal design:**
  - Append-only JSONL per gather, named for the UTC start time. Atomic-replace not needed (single writer per gather; OS-level `O_APPEND` semantics suffice).
  - Phase 9 will project these into the canonical Postgres event log by walking `.codegenie/events/` and `INSERT INTO events ... ON CONFLICT DO NOTHING` keyed by `event_id`. We pre-generate UUIDv7 `event_id`s in Phase 2 so the migration is collision-safe.
  - The event log is **NOT** the place we write every probe execution. It's the place we write *decisions* — Phase 13 will read it to compute fallback-trigger rates, Phase 14 will alert on `IndexHealthDegraded` spikes, Phase 11 will project per-workflow audit trails. Verbose probe-execution logging stays in `.codegenie/logs/`.
- **Performance argument:** ~10 events per gather × 200 bytes × 50k gathers/day = ~100 MB/day of event JSON. Negligible at portfolio scale, eligible for daily rotation + compression. The cost of *not* shipping this shape in Phase 2 is that Phase 9 has to retrofit it across every probe — and the post-hoc retrofit is what produces "event soup" per the ADR-0034 warning.
- **Tradeoffs accepted:**
  - Adds a new on-disk artifact category (`events/`). Documented in localv2.md as part of Phase 2.
  - The schema is forward-evolving — new event variants land additively. Phase 9 imposes the full type discipline; Phase 2 ships the three load-bearing events plus the extension hook.
- **Pattern decisions:** Event sourcing (the future canonical primitive, pre-shaped). Tagged union for event variants (illegal-states-unrepresentable). Registry pattern is *not* applied here — events are emitted in-line by probes that care; there's no central event handler in Phase 2.

### 9. Multi-repo fixture portfolio + golden-file test infrastructure

- **Purpose:** Per the roadmap exit criterion, Phase 2 needs golden-file tests per probe AND a multi-repo fixture portfolio of 3–5 small repos. The performance lens requires this to be *fast enough that CI doesn't degrade* — golden-file diffs on heavy probe outputs (semgrep findings on a 200-file repo) can dominate CI time if naively implemented.
- **Interface:**
  - `tests/fixtures/portfolio/{minimal-ts, native-modules, monorepo-pnpm, distroless-target, vuln-seeded}/` — five fixture repos. Each is ~50-500 source files; each exercises a different Phase 2 probe surface.
  - `tests/golden/<probe>/<fixture-name>.json` — committed expected output per (probe, fixture) pair.
  - `pytest --update-golden` regenerates; without the flag, diffs are CI failures.
- **Internal design:**
  - Heavy probes (SCIP, semgrep, runtime trace) run against the portfolio in a `pytest-xdist`-parallel CI lane separated from the Phase 0 unit-test lane. The xdist budget is the one Phase 1 `synth` explicitly refused — Phase 2 ships it specifically for the portfolio runs because per-probe wall-clocks are now in the tens of seconds and serial CI is hostile.
  - The runtime-trace fixture (`distroless-target`) uses a frozen Docker image (`localhost:5000/cw-fixture-runtime:sha-<digest>`) committed to a local registry container, started in CI as a sidecar. This eliminates `docker build` time from the fixture path (we already verified `docker build` in unit tests for `DockerfileProbe`).
  - **A deliberately-seeded stale-index fixture** lives at `tests/fixtures/portfolio/stale-scip/`. Its `.codegenie/cache/` is pre-populated with a SCIP index from a known prior commit; the repo HEAD has moved. `IndexHealthProbe` MUST detect this and emit `IndexHealthDegraded` event. This is the roadmap exit criterion ("IndexHealthProbe surfaces at least one real staleness case in CI"), encoded as a CI assertion.
- **Tradeoffs accepted:**
  - CI walltime grows. Estimate: +3 minutes p50 on the portfolio lane. Acceptable — it runs in parallel with the unit lane, total wall-clock CI is dominated by the slower of the two.
  - The frozen runtime-trace fixture image must be rebuilt occasionally as upstream base images age. Tracked as a Phase 2 maintenance task.

## Data flow

A representative warm-path run on a real Node.js repo (~5k files, TypeScript, pnpm, GitHub Actions, Helm, built `node:20-alpine` image present in local registry) where `src/payments/processor.ts` changed since last gather:

1. **CLI + Phase 0/1 prelude** (unchanged). PathIndex built (one walk). Layer A probes run; `language_detection`, `node_build_system`, `node_manifest`, `ci`, `deployment`, `test_inventory` all cache-hit except `language_detection` (per-file walk fingerprint changed). Phase 1 wall-clock so far: ~150 ms.
2. **Plugin loader resolves** to `[universal--*--*]` (no concrete Phase 3 plugin yet). Probe-requirement union = Layer A (already done) + Layer B–G kernel probes from the universal plugin manifest.
3. **Cost-tier coordinator dispatches in waves**:
   - **Tier-0 wave (parallel up to cpu_count() = 8):** `ConventionProbe`, `ExceptionProbe`, `ADRProbe`, `RepoConfigProbe`, `RepoNotesProbe`, `SkillsIndexProbe` all cache-hit (none of their inputs changed). `IndexHealthProbe` is queued behind the probes it `requires`; placeholder. **Wall-clock added: ~20 ms (cache-hit retrievals + sub-schema validation).**
   - **Tier-1 wave (parallel up to 4):** `SemgrepProbe` cache-hit (source-tree hash matches if only `.ts` files changed by content not count — semgrep's cache key is the Merkle root of source + rule-pack version; both unchanged on a single-file edit if rule packs haven't been bumped — wait: source changed, so semgrep MISSES). Actually: `processor.ts` changed → SemgrepProbe re-runs on the affected file set (~3 s on a 5k-file repo with incremental scope per the `--baseline-ref` flag we configure with the git HEAD~1). `SCIPIndexProbe` MISSES — re-indexes the whole repo (~8 s). `BuildGraphProbe` cache-hit. `NodeReflectionProbe` cache-hit if `processor.ts` did not introduce new reflection patterns (per-file hash). `GeneratedCodeProbe` cache-hit. `TreeSitterImportGraphProbe` re-runs *just for `processor.ts`* (per-file projection update) — ~50 ms. `AstGrepProbe` re-runs on affected files (~500 ms). **Wall-clock added: ~8 s (SCIP dominates).**
   - **Tier-2 wave (parallel up to 2):** `DockerfileProbe` cache-hit (Dockerfile unchanged). Image digest unchanged → `SBOMProbe`, `CVEProbe`, `CertificateProbe`, `EntrypointProbe`, `ShellUsageProbe` all cache-hit. **Wall-clock added: ~50 ms (cache retrievals).**
   - **Tier-3 wave (serial, slot of 1):** `RuntimeTraceProbe` cache-hit (image digest matches, scenarios unchanged). `ExternalDocsProbe` cache-hit (source mtimes unchanged). **Wall-clock added: ~10 ms.**
4. **Projection write fan-out** (parallel, all `cost_tier = 0` projection writers):
   - `scip.symbols.idx` re-writes (SCIP re-indexed) — ~300 ms.
   - `import_graph.adj.json` updates the `processor.ts` row + reverse edges — ~5 ms (single-file delta).
   - `dep_graph.adj.json` unchanged (cache hit).
   - `test_exercises.adj.json` updates rows for tests transitively touching `processor.ts` — ~10 ms.
5. **`IndexHealthProbe` runs** (requires-graph satisfied). Reads all sibling slices. SCIP confidence = `Trusted` (just re-indexed, all signals green). Runtime trace confidence = `Trusted` (image digest match). No events emitted. **Wall-clock added: ~30 ms.**
6. **Output merge + schema validation** (Phase 0 + Phase 1 sub-schemas + Phase 2 per-probe sub-schemas for B–G probes). ~100 ms.
7. **YAML write + raw artifact write + projection write** (atomic `.tmp` → `os.replace`, 0600 mode per Phase 0). ~50 ms.
8. **Audit record** (Phase 0). Per-probe execution path (`Ran` / `CacheHit` / `Skipped`).
9. **Exit 0.** Total wall-clock: ~9 s, dominated by SCIP re-index. Without SCIP re-index (whitespace-only edit, SCIP cache-hits): ~600 ms.

**Cold gather (first time on a 50k-LOC service with no built image):** sequential floor is `docker build` (~47 s) + `scip-typescript` (~8-15 s) + `RuntimeTraceProbe` 5 scenarios (~80 s). Tier-1 probes (semgrep, ast-grep, tree-sitter graph) run in parallel against tier-2 (docker build) and tier-3 (runtime trace). Total: ~170 s vs. the localv2.md §3.2 baseline of 3-6 minutes. **Meets the cold-gather goal.**

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| `scip-typescript` exits non-zero (TypeScript compile error in repo) | Probe `run()` catches subprocess exit code | `ProbeOutput(confidence="low", errors=[stderr_tail])`; `IndexHealthProbe` reads this → SCIP confidence = `Unavailable("indexer_failed")`; `IndexHealthDegraded` event emitted; Phase 3+ adapter dispatch falls back per ADR-0032 |
| `scip-typescript` exceeds `timeout_seconds=300` (huge monorepo) | Phase 0 coordinator `asyncio.wait_for` | Cancel + SIGKILL at 1.5× timeout; SCIP slice empty; Phase 3+ Bundle Builder degrades to tree-sitter-only per ADR-0032 declared fallback |
| Image digest cache-key miss with no local image present | `DockerfileProbe` resolves the expected digest, finds none | Triggers `docker build`; takes 47 s; subsequent probes cache-key on the new digest |
| `docker build` fails (Dockerfile syntax, base-image pull failure) | Subprocess exit code | Tier-2 probes that depend on the built image emit `confidence="unavailable"`, `errors=["image_build_failed: <stderr_tail>"]`; gather completes with degraded tier-2 |
| `strace` exec fails (macOS, missing binary) | `exec.run_allowlisted` raises | `RuntimeTraceProbe` slice marked `confidence="low"`, scenarios skipped; `IndexHealthProbe` flags runtime_trace as `Unavailable("strace_missing")`; **gather still succeeds** — localv2.md §6 already documents this macOS case |
| `gitleaks` finds a secret in the analyzed repo's source | Probe parses gitleaks JSON output | Phase 0 `OutputSanitizer` field-name regex catches it as a secondary defense; PathSpec-based scrubbing strips the secret value from the probe output; the *finding* (file:line, secret-type) survives; the *secret value* never reaches `repo-context.yaml` |
| Plugin manifest malformed (`plugin.yaml` missing required field) | Pydantic validation at loader.discover() time | Loader fails-fast at CLI startup with diagnostic naming file + field per ADR-0031; gather refuses to start (loud) |
| Plugin import path unresolvable (`contributes.adapters` points at missing module) | Phase 2 ships no adapters in the universal plugin so this is a forward concern; loader still validates import paths at startup | Fails-fast at startup per ADR-0031 |
| `IndexHealthProbe` cache pollution (somebody runs with `--no-cache` then back to normal) | Probe `cache_strategy = "none"` enforces re-run every gather | No staleness possible; probe is by construction always-fresh |
| Stale-SCIP fixture in CI (deliberate seeded staleness) | `IndexHealthProbe` confidence computation flags `commits_behind > 0`, fails the `image_digest_match` style assertion | `IndexHealthDegraded` event emitted; CI test asserts event presence + correct `reason`; build passes only if the probe caught the staleness |
| Tier-2 image-digest cache invalidated by orphaned cache entries (image pruned but cache entry persists) | `DockerfileProbe` resolves expected digest, attempts to read from cache — cache entry references an image no longer in registry | Cache entry expired silently (Phase 0 store handles missing referenced artifacts as cache-miss); tier-2 probes re-run with rebuilt image |
| Projection write fails (disk full mid-write) | `writer.atomic_replace` exception | Probe completes; projection rewrite fails; downstream adapter sees an old projection and emits low confidence; loud via `IndexHealthProbe` |
| Tier-3 strace produces 500 MB trace file (long-running scenario) | Probe hard caps per-scenario trace at 100 MB via `--limit-bytes`-equivalent | Scenario output truncated; `scenario_truncated: true` field set; confidence drops to `medium` |
| External docs fetch hangs (Confluence timeout) | Per-source `httpx.Client(timeout=30)` | Source marked `fetch_failures: [...]`; index probe runs over the docs that succeeded; gather continues |
| Concurrent gather race (two `codegenie gather` invocations against same repo) | Phase 0 advisory lock at `.codegenie/cache/.lock` | Second invocation either waits or fails fast (configurable); image-digest cache races resolved by the `docker pull`/`docker build` daemon-level serialization |

The pattern: **loud degradation at every probe boundary, never silent omission**. The cache layer never lies about its contents; `IndexHealthProbe` never reports `Trusted` for a stale signal; the event stream captures every degradation for Phase 9/13 to project.

## Resource & cost profile

- **Tokens per run:** 0. Phase 0 `fence` job continues to assert. The `gather` extras list grows by `msgpack`, `scip-python` (parser-only), `tantivy`, `pyarn`-or-built-in-fallback, `tree-sitter-python` bindings, `gitleaks-python`, `httpx`. **Zero LLM SDKs.**
- **Wall-clock targets met on a 50k-LOC TypeScript service:**
  - Cold (no built image, no caches): ~170 s. Floor = `docker build` (47 s) + `scip-typescript` (8-15 s) + `RuntimeTraceProbe` (80 s) running in parallel across tiers.
  - Cold (image present in local registry): ~95 s. Tier-2 collapses to tier-1 in concurrency terms.
  - Warm (all caches valid): ~0.6 s. Dominated by cache-hit retrievals + schema validation + YAML write + projection-file existence checks.
  - Incremental (single `.ts` change): ~9 s. SCIP re-index dominates; everything else cache-hits or runs in parallel.
- **Memory (RSS):**
  - Cold gather peak: ~800 MB. `scip-typescript` subprocess ~400 MB; `semgrep` subprocess ~200 MB; coordinator + Python ~150 MB.
  - Warm gather peak: ~250 MB. Most of the cold-gather subprocesses never start.
  - Idle (Phase 14 long-lived worker): ~120 MB.
- **Storage per gather:**
  - `repo-context.yaml` ~60 KB (Phase 1's 30 KB + Phase 2 slices).
  - `raw/` ~8 MB (SCIP binary 2-3 MB; SBOM 1-2 MB; runtime traces 4-5 MB summed across 5 scenarios).
  - `projections/` ~5 MB (graph adjacencies + symbol index).
  - `cache/blobs/` grows by ~10 MB per cold gather; per-blob, ~50-500 KB.
  - `events/` ~5 KB per gather (10 events × 500 bytes).
  - **Total per cold gather: ~25 MB on disk. Per warm gather: ~70 KB.**
- **CI walltime delta vs. Phase 1:** +5 minutes on the portfolio lane (running in parallel via `pytest-xdist`); +15 s on the unit lane. Total CI walltime grows ~3 minutes if both lanes are well-balanced.
- **External-dep additions:** `msgpack`, `scip-python` (parser-only), `tantivy`, `tree-sitter-python` bindings, `gitleaks-python`, `httpx`. Each one ratified by ADR; each one tracked by Dependabot per Phase 0 §2.5. No C-extension churn beyond what Phase 0 already accepted (`blake3`, `pyyaml` with `CSafeLoader`).
- **External CLI runtime additions:** `semgrep`, `syft`, `grype`, `gitleaks`, `scip-typescript`, `strace` (Linux), `dive` (optional). All checked at CLI startup per Phase 0's tool-readiness gate.

## Test plan

The test pyramid widens at the integration tier (portfolio fixtures) without losing the unit-test floor.

### Unit tests (`tests/unit/probes/`)

| Test module | Asserts |
|---|---|
| `test_scip_index_probe.py` | `scip-typescript` invocation; output projection format; per-symbol lookup correctness; cache-key sensitivity to tool-version stamp; timeout → low confidence |
| `test_index_health_probe.py` | Per-source-of-truth assertions (SCIP commit match, runtime-trace image-digest match, semgrep coverage); confidence-tier transitions; event emission on `Degraded` and `Unavailable`; `cache_strategy = "none"` enforced |
| `test_dependency_graph_probes.py` | Forward + reverse adjacency correctness; monorepo vs. single-package handling; projection format roundtrip |
| `test_tree_sitter_import_graph_probe.py` | Per-file extraction correctness; internal thread-pool parallelism; projection adjacency invariants (forward[a] contains b ↔ reverse[b] contains a) |
| `test_sbom_probe.py`, `test_cve_probe.py` | `syft` and `grype` invocation; cross-validation between `grype` and `trivy`; image-digest cache-key correctness; absence of image → low confidence |
| `test_runtime_trace_probe.py` | Per-scenario serial execution; per-scenario timeout; trace-file size cap; `cert_paths_read`/`shared_libs_loaded` parsing; macOS-fallback path |
| `test_semgrep_probe.py` | Rule-pack version stamp; finding-shape correctness; incremental `--baseline-ref` cache-key derivation |
| `test_skills_index_probe.py`, `test_convention_probe.py`, `test_exception_probe.py` | Frontmatter parsing; multi-source merging; pre-projection write |
| `test_external_docs_probes.py` | Filesystem + URL list + Confluence (mocked); BM25 index roundtrip; per-source fetch failure isolation |
| `test_cost_tier_coordinator.py` | Per-tier semaphore correctness; cross-tier non-blocking; default tier=0 backward-compat; misclassification CI lint |
| `test_plugin_loader.py` | Manifest Pydantic validation; fail-fast on missing field; universal-fallback resolution; `extends` chain walk |
| `test_events_writer.py` | Event variant Pydantic discrimination; JSONL append correctness; UUIDv7 uniqueness; forward-projectable to Phase 9 schema |
| `test_projection_formats.py` | All four projection files have well-defined formats; adapter Protocol implementations (Phase 3 will read these) get the shape they expect |

### Golden-file tests (`tests/golden/<probe>/<fixture>.json`)

One per `(probe, fixture)` pair in the portfolio. CI diffs live output vs. committed expected; `pytest --update-golden` regenerates. Adversarial fixtures (deliberately malformed source files, oversized inputs) live at `tests/golden/_adversarial/`.

### Integration tests (`tests/integration/portfolio/`)

| Test module | Asserts |
|---|---|
| `test_portfolio_minimal_ts.py` | Full gather against `minimal-ts` fixture; all probes complete; `IndexHealthProbe` reports `Trusted` across the board; total wall-clock < 30 s in CI |
| `test_portfolio_native_modules.py` | Native module catalog hits (sharp + bcrypt); `RuntimeTraceProbe` enumerates expected shared libs; SBOM includes `libvips` |
| `test_portfolio_monorepo_pnpm.py` | `BuildGraphProbe` produces correct module graph; projections are per-monorepo |
| `test_portfolio_distroless_target.py` | Pre-built image fixture; all tier-2 probes hit the digest cache after first run; cold→warm ratio matches goal |
| `test_portfolio_vuln_seeded.py` | Seeded CVE in lockfile; `CVEProbe` finds it; `grype`/`trivy` cross-validation triggers |

### Adversarial / fail-loud tests (`tests/adv/`)

| Test module | Asserts |
|---|---|
| `test_stale_scip_fixture.py` | The deliberately-seeded `stale-scip` fixture is detected by `IndexHealthProbe`; `IndexHealthDegraded` event emitted; build FAILS if probe doesn't catch it (the roadmap exit criterion) |
| `test_huge_repo_timeout.py` | 200k-file fixture triggers Phase 1's `--max-files` refusal; gather exits with clear error |
| `test_malformed_plugin_manifest.py` | Bad `plugin.yaml` fails CLI startup loudly; gather refuses to run |
| `test_image_digest_drift.py` | Mutating the built image between gathers correctly invalidates all tier-2 caches |
| `test_secret_in_source.py` | gitleaks finds seeded secret; OutputSanitizer scrubs value; finding metadata survives |
| `test_projection_corruption.py` | Truncated `scip.symbols.idx` triggers loud failure on first read; never silent-degrades the adapter |
| `test_concurrent_gather_race.py` | Two concurrent gathers don't corrupt cache or projections; advisory lock works |

### Performance canary tests (`tests/bench/`)

Advisory, not gating (per Phase 0 §3.2 — bench is surfaced, not enforced).

| Test | Tracks |
|---|---|
| `bench_warm_gather_walltime.py` | Warm gather p50/p95 against the portfolio; flags regressions > 50% |
| `bench_cold_gather_walltime.py` | Cold gather p50/p95 (image pre-pulled to isolate from network) |
| `bench_per_tier_concurrency.py` | Verifies tier-0 probes finish during long-tail of tier-1/2/3 |
| `bench_projection_adapter_latency.py` | Phase 3 forward-looking: simulates ADR-0032 adapter calls against gathered projections; verifies p95 < 50 ms target |

## Design patterns applied

| Decision | Pattern applied | Why here | Pattern NOT applied (and why) |
|---|---|---|---|
| Cost-tier coordinator | Plugin architecture (probes self-classify tier as data); composition over inheritance (tiers are a field, not a class hierarchy) | Tiers are data; the coordinator knows about tiers but not about probes; new probes pick their tier in the registration | Strategy pattern — there is no algorithm to swap; the tier is just a semaphore selector |
| Plugin loader | Plugin architecture; Registry pattern; Dependency inversion (kernel depends on `Probe` Protocol, never on plugin-specific classes); Hexagonal (the loader is a Port; YAML-on-disk is one Adapter, Phase 14 webhook will be another) | ADR-0031 explicitly requires the kernel never import plugins by name; the loader is the only allowed coupling point | Inheritance for probe contributions — probes are *registered* via the manifest's `contributes.probes` list, not extended from a plugin base class |
| IndexHealthProbe + AdapterConfidence sum type | Tagged union for state (`Trusted | Degraded | Unavailable`); make illegal states unrepresentable (`Trusted` cannot carry a `reason`); Specification pattern for the per-source-of-truth freshness checks; Open/Closed (new health checks register, never edit `IndexHealthProbe`) | ADR-0033 discipline applied to a state machine that's *load-bearing* for ADR-0032 adapter dispatch; the worst failure mode (silent staleness) is exactly the thing booleans + None lets through | Pattern-matching exhaustiveness via `match` is enforced; assert_never on the AdapterConfidence handler |
| Tier-2 image-digest cache-key strategy | Strategy pattern at the cache-key derivation level (probes override `cache_key`); Adapter pattern wraps `docker`/`syft`/`grype` output to a stable hash | The probes consume image-digest-keyed evidence, not source-tree-keyed evidence; using the source-tree key would force re-runs that produce identical output | Premature pluggability for cache backends — the Phase 0 filesystem store is sufficient; the strategy is on the key derivation, not the store |
| TCCM projection format (`projections/*.json`, `scip.symbols.idx`) | Functional core, imperative shell (projection is a pure fold over probe outputs; the writer is the shell); Adapter pattern (projection format IS the ADR-0032 adapter contract) | The projection's purpose is to make ADR-0030's graph-aware queries O(lookup); doing it as a pure projection lets Phase 3's adapters be thin loaders, not graph-walking machines | Event sourcing for projections — projections are *derived state*, not the source of truth; rebuilding is cheap |
| Events writer | Event sourcing (pre-shape for Phase 9 ADR-0034); Tagged union for `PhaseEvent`; Registry pattern *deliberately* not applied (events are emitted in-line by probes) | Pre-shaping the canonical Postgres event log lets Phase 9 be a projection migration, not a forensic data archaeology project | Pattern-matching dispatch — Phase 2 doesn't *consume* events; it only writes them. Phase 9 owns the consumer |

## Risks (top 3-5)

1. **`scip-typescript` cold-gather wall-clock is a hard floor.** Our 60 s cold-without-build target sits right on the SCIP indexer's typical 8-15 s runtime for a 50k-LOC repo; for a 500k-LOC monorepo it's 60-90 s alone. Incremental SCIP is unreleased upstream at the time of writing. **Mitigation:** the per-repo Merkle-root cache key means we only pay the cold cost once per `.ts` change at the repo level; portfolio-scale economics still work. If `scip-typescript` performance regresses, the projection format insulates us — we can swap the indexer (`scip-typescript-next`, `sourcegraph-scip` direct, etc.) without touching ADR-0032 adapters.

2. **Image-digest cache-key strategy is the one Phase 2 deviation from Phase 0/1 cache discipline.** A bug in image-digest resolution silently fails-quiet (cache-hits when it should miss). **Mitigation:** the deviation is ADR-gated, the digest-resolution helper is in one place, and there's an adversarial test (`test_image_digest_drift.py`) that mutates the image between gathers. Phase 14 will revisit the multi-actor cache story per Phase 0 §2.7's commitment.

3. **Projection format is now a *second* on-disk schema** (the first being `repo-context.yaml`). Schema evolution discipline applies to both. **Mitigation:** the projection format is versioned per-file (`_provenance.json` carries `format_version`); ADR-0032 adapters check the version on load and refuse mismatched formats loudly. Adding a new field is additive; renaming requires an ADR amendment + migration test.

4. **Plugin loader ships in Phase 2 before its first concrete consumer (Phase 3 plugin).** YAGNI charge: we're shipping infrastructure on speculation. **Mitigation:** the universal fallback plugin is not speculative — it's the actual mechanism by which kernel-resident B–G probes register, per ADR-0031's "no-match fallback" requirement. The shipped surface is small (~300 LOC for loader + manifest models). The risk is over-design on the manifest schema — refused by keeping the Phase 2 manifest to the four required fields (`name`, `version`, `scope`, `contributes`) and one optional (`extends`).

5. **Tier-3 serialization (RuntimeTraceProbe) is the cold-gather wall-clock dominator.** Five scenarios × 16-20 s each = 80-100 s, and we cannot parallelize without contaminating traces. **Mitigation:** the scenario set is configurable per-repo (`runtime_trace.scenarios:` in `.codegenie/config.yaml`); a repo that doesn't need `error_path` skips it. Image-digest caching means in steady state most workflows hit cache and pay zero. Future optimization (Phase 14+): pre-warm the trace cache as part of the continuous-gather Dispatcher's nightly cron, not in the workflow critical path.

## Acknowledged blind spots

- **Cross-language gather** is out of scope. Phase 1 designed for Node.js; Phase 2 extends with language-agnostic probes (semgrep, gitleaks, conventions, skills) but the SCIP indexer + tree-sitter grammars shipped in Phase 2 are TypeScript-only. Adding Java/Python is the Phase 3+ language-plugin path per ADR-0031.
- **No Layer F.** Per localv2.md §5.7, Layer F (vuln-specific evidence — CodeQL, taint flow) is Phase 3+ scope. Our schema accommodates it, our cost tiers anticipate the addition, our event log is shape-compatible — but we don't ship the probes.
- **Concurrent gather discipline against the same repo** is delegated to Phase 0's advisory lock + the docker daemon's natural serialization of builds. We do not design a distributed-coordinator story for Phase 14's webhook-driven concurrent gathers — that's a Phase 14 problem.
- **Cache eviction policy.** Phase 0/1's cache grows unboundedly. Phase 2 doesn't tackle this either. At ~25 MB per cold gather and a normal portfolio cadence of one cold gather per repo per quarter, the disk pressure is sub-1 GB per repo per year — out of scope for our timeline but tracked.
- **MCP serving of `RepoContext` and projections.** Production design.md §8 describes MCP; Phase 2 writes files on disk. Phase 8's MCP server reads our files. We do not pre-design the MCP API — we trust the file format to be the contract.
- **Cross-validation between probes that should agree.** `IndexHealthProbe` reads each probe's slice independently; if two probes contradict each other (e.g., `SemgrepProbe` says a `.ts` file exists that `SCIPIndexProbe` does not see), we currently surface this as two confidence values, not as a contradiction event. Phase 9's event projection can fix this; we do not.

## Open questions for the synthesizer

1. **Should the universal-fallback plugin manifest be hand-edited or generated?** I lean hand-edited (~50 lines, reviewed-as-data). The best-practices lens may want a generator from probe registrations; the security lens may want the manifest signed. Pick one.
2. **Is `msgpack` for the SCIP symbol-index projection the right choice vs. a small custom binary format?** Performance argument: msgpack is ~5× faster than JSON and ships as a maintained C extension. Best-practices may want JSON for diffability; security may flag any new C extension. I picked msgpack; defend or replace.
3. **The image-digest cache-key deviation from Phase 0's source-tree discipline is one ADR away from being a separate cache substore.** I kept it in the unified Phase 0 cache for simplicity. The synthesizer may want a separate substore at `cache/by-image-digest/` for clarity; I'd accept it if the API surface stays the same.
4. **`pytest-xdist` for the portfolio test lane reverses Phase 1's `synth` decision.** Phase 1 vetoed xdist for the unit lane; Phase 2 needs it for the portfolio lane (heavy probes). The synthesizer should confirm whether this is a reversal of Phase 1 §2.2 (`pytest-xdist: NOT enabled`) or an additive scope-limited adoption. I read it as additive; the synthesizer rules.
5. **Should `IndexHealthProbe`'s event emission be synchronous (blocks gather completion) or fire-and-forget?** I designed it synchronous (loud-not-quiet). The performance argument for fire-and-forget is marginal (~5 ms saved); the risk is silent event loss. I picked synchronous; the synthesizer can override if Phase 14 telemetry pressure makes async necessary.
6. **`TreeSitterImportGraphProbe` runs its own internal thread pool inside a tier-1 slot.** This is a second concurrency layer the coordinator doesn't see. The synthesizer should rule on whether this is acceptable (it works because tree-sitter's C extension releases the GIL) or whether it's a hidden coupling that should be explicit in the coordinator's accounting.
7. **Phase 2 ships the event-stream skeleton (`.codegenie/events/`) without the Phase 9 Postgres backend.** Three events are defined. The synthesizer should rule whether to ship more events now (more upfront design, lower Phase 9 risk) or fewer (less upfront commitment, higher Phase 9 migration cost). I picked three load-bearing ones; defend or expand.
