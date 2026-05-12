# Phase 01 — Context gathering: Layer A (Node.js): Performance-first design

**Lens:** Performance — throughput, latency, token economy, footprint.
**Designed by:** Performance-first design subagent
**Date:** 2026-05-12

## Lens summary

The whole point of Phase 1 — measured against the production target — is to make Stage 2 (Deep Scan) a *cache hit in single-digit seconds* on every workflow at portfolio scale. ADR-0006 (continuous deterministic gather) commits the system to running this code on every push, every PR, every CVE event, against every watched repo. ADR-0013 commits to single-digit-ms agent reads of hot views. If Phase 1's Layer A is a 30-second blob of subprocess churn, the continuous-gather model collapses under its own weight at 1,000 watched repos × 50 pushes/day = 50,000 gathers/day. Layer A is touched on **every** gather (it derives the language fingerprint everything else gates on), so it sits squarely on the critical path.

I optimized for: (1) cache hit rate at portfolio scale, where the headline number is "near-zero work when nothing changed"; (2) wall-clock on warm + incremental paths, because cold gathers are a one-time tax per repo while warm/incremental dominate steady state; (3) avoiding the fork-exec-parse-discard pattern that subprocess-heavy probes default to in Python; (4) keeping `repo-context.yaml` writes cheap because Phase 13's cost ledger and Phase 14's continuous gather both fan out from this artifact.

I deprioritized: defensive security beyond what Phase 0's chokepoints already provide; "pretty" error messages; readable intermediate logs; ecosystem expansion (Phase 2 Layer B is explicitly *not* my problem); developer-time UX of the first cold run on a fresh dev box. I will measure things; I will not gold-plate the measuring.

## Goals (concrete, measurable)

These are aggressive vs. the roadmap's "useful on a real Node.js repo" exit criterion. They are the targets I want the synthesizer to push back on.

- **Workflows/hour target (Layer A only, single 8-core worker):** ≥ 2,400/hr in steady state (= 1.5s p50 wall clock per incremental gather; ≥90% cache-hit by probe).
- **Time-to-PR contribution from Layer A (p95):** ≤ 250 ms on incremental gather (only the changed-input probes re-execute); ≤ 4 s on warm gather (all Layer A probes re-execute, no cold subprocesses); ≤ 12 s on cold first-run for a typical 50k-LOC Node service.
- **$/PR target:** $0.00 — Layer A is fully deterministic per ADR-0005; the only spend is CPU-seconds. Target ≤ 2 CPU-seconds per incremental gather, ≤ 12 CPU-seconds per warm gather.
- **Cache hit rate target:** ≥ 92% per-probe across a steady-state portfolio (matches the Cursor reference number cited in `production/design.md §3.2`). 100% on a re-run with zero file changes (this is the roadmap's exit criterion; I make it a regression test).
- **Per-worker memory ceiling:** ≤ 250 MB RSS per active gather; ≤ 80 MB resident for the CLI itself between gathers (this matters when Phase 14 runs gathers as long-lived workers). Phase 0's `ResourceBudget(rss_mb=200, ...)` default holds; I tighten it for Layer A probes that don't shell out.
- **Tail latency (p99) on incremental gather:** ≤ 600 ms. The 99th percentile is the one that determines portfolio throughput, not the median.
- **Hot-view pre-render budget:** Phase 1 doesn't ship Redis yet (that's Phase 8), but Layer A's output must be *shaped* so that the four pre-rendered slices (ADR-0013: `available_skills`, `entrypoint`, `risk_flags`, `confidence_summary`) can be projected from `repo-context.yaml` in ≤ 5 ms with zero re-parsing.

## Architecture

```
                            codegenie gather <path>
                                        │
                                        ▼
                  ┌─────────────────────────────────────────┐
                  │   Snapshot builder (single fs.walk)      │
                  │  - one-pass os.scandir, gitignore-aware  │
                  │  - emits PathIndex: dict[str, FileStat]  │
                  │  - the only filesystem traversal of the  │
                  │    repo per gather. PERIOD.              │
                  └────────────────┬────────────────────────┘
                                   │
                                   ▼
                  ┌─────────────────────────────────────────┐
                  │   Coordinator (asyncio, from Phase 0)    │
                  │  - probe DAG = explicit edges, not       │
                  │    `requires:` string lookup at runtime  │
                  │  - per-probe cache check BEFORE          │
                  │    subprocess (the canonical bug)        │
                  │  - bounded Semaphore(min(cpu, 8))        │
                  └────────────────┬────────────────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────────────┐
        │  Tier-0: zero-subprocess │  Tier-1: pure-python parse       │
        │  (LanguageDetection,     │  (NodeManifest, NodeBuildSystem, │
        │   prelude — runs first)  │   CI, Deployment, TestInventory) │
        │  cache key from PathIndex│  cache key from declared_inputs  │
        │  fingerprint only        │  blob hashes only                │
        └──────────────────────────┴──────────────────────────────────┘
                                   │
                                   ▼
                  ┌─────────────────────────────────────────┐
                  │   Per-probe cache (Phase 0 store)        │
                  │  - hot in-memory LRU layered above       │
                  │    filesystem (mmap'd index)             │
                  │  - hit returns ProbeOutput w/o I/O       │
                  └────────────────┬────────────────────────┘
                                   │
                                   ▼
                  ┌─────────────────────────────────────────┐
                  │   Streaming merger + sanitizer            │
                  │  - YAML writer emits as probes finish     │
                  │    (no buffer the whole RepoContext)      │
                  │  - hot-view projection emitted as a       │
                  │    sibling .codegenie/context/views.json  │
                  │    (Phase 8 reads this directly into      │
                  │    Redis without re-parsing YAML)         │
                  └────────────────┬────────────────────────┘
                                   │
                                   ▼
                  .codegenie/context/repo-context.yaml
                  .codegenie/context/views.json          [new — for Phase 8]
                  .codegenie/context/raw/<probe>.json
                  .codegenie/cache/blobs/...             (Phase 0 layout)
```

Data flow: one filesystem walk → one PathIndex → six probes consume slices → cache layer short-circuits unchanged probes → results stream to YAML + JSON views. The PathIndex is the load-bearing object — it's why Layer A can be sub-second on the warm path.

## Components

### 1. SnapshotBuilder (`codegenie/coordinator/snapshot.py` — extends Phase 0)

- **Purpose:** Walk the repo exactly once. All six Layer A probes read from the resulting `PathIndex` rather than re-walking. Critique-proof against the "every probe runs its own `os.walk`" antipattern.
- **Interface:**
  - in: `repo_root: Path`, `gitignore_rules: PathSpec`
  - out: `PathIndex` (frozen dataclass): `paths: tuple[FileEntry, ...]` sorted by path; `by_extension: dict[str, tuple[FileEntry, ...]]` (precomputed bucket views — these are the slices probes actually consume); `manifests_present: frozenset[str]` (subset check for `package.json`, `pnpm-lock.yaml`, etc., precomputed); `fingerprint: str` (BLAKE3 over the sorted `(rel_path, size, mtime_ns)` tuple — the cache key root for tier-0 probes).
  - errors: refuses symlinks crossing repo root (inherited from Phase 0); refuses ≥ 200k files without `--max-files` (avoids accidental walk of vendored monorepos — fails loud per Rule 12).
- **Internal design:**
  - `os.scandir` recursive, **breadth-first**, with an exclusion set computed once from `.gitignore` + hard-coded noise dirs (`node_modules`, `.git`, `dist`, `build`, `coverage`, `.next`, `.turbo`, `target`). Excluded at directory level so `node_modules` is never even descended into.
  - `gitignore_rules` uses `pathspec` (compiled once) — orders of magnitude faster than per-file rule eval.
  - No `Path` objects in the hot loop. Strings + `os.DirEntry.stat(follow_symlinks=False)`. `Path` is constructed lazily when a probe asks.
  - `by_extension` materialized in the walk loop, not as a post-pass dict-comp. Branchless: a precomputed `dict[str, list]` per extension we care about (`.js`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.json`, `.yaml`, `.yml`, `.lock`, `.toml`, `.dockerfile`); everything else goes into a single `_other` bucket that is *not* sorted (saves a sort pass on the ~80% of files no probe cares about).
  - `fingerprint` is BLAKE3 over a packed byte buffer of `(len_path, path, size_u64, mtime_u64)` — no string concatenation, no JSON serialization. ~3 GB/s on modern hardware (Phase 0 ADR ratified BLAKE3).
- **Tradeoffs accepted:**
  - Every probe must accept a `PathIndex` argument. This is *not* the Phase 0 probe contract — it's a coordinator-level enrichment that probes can opt into via a typed helper. Probes that don't opt in walk the repo themselves (slow path, surfaced in logs).
  - The PathIndex holds `mtime_ns` in memory. On a 50k-file repo that's ~3 MB resident. Acceptable.
  - We re-walk the repo if the `--no-cache` flag is set or the PathIndex itself was invalidated by a config change. That's fine; cold path was never the target.

### 2. Coordinator extensions (`codegenie/coordinator/coordinator.py` — extends Phase 0)

- **Purpose:** Make the Phase 0 coordinator perform well at Layer A's fan-out (6 probes) and Phase 14's repeat rate (50k gathers/day).
- **Interface:** unchanged from Phase 0 (`async def gather(...) -> GatherResult`).
- **Internal design:**
  - **Cache check before probe instantiation.** Phase 0 already does this; I'm calling it out because the canonical performance regression is "we instantiated the probe, called `run()`, and *then* checked the cache." The cache lookup is keyed by `(probe_name, probe_version, per_probe_schema_version, declared_inputs_content_hash)`. For Layer A the `declared_inputs_content_hash` is derived from the PathIndex — never re-hashes file contents that were already hashed during the walk.
  - **Prelude pass = LanguageDetection only.** Phase 0 introduced the prelude pass. I tighten it: only LanguageDetection runs in the prelude, and it runs with the PathIndex *already populated* (no second walk). LanguageDetection is now an ~8 ms operation on the warm path (it reads `by_extension` bucket sizes and emits counts).
  - **Explicit DAG.** Phase 0 uses `requires: list[str]` strings. At runtime that means dict lookups. For Layer A's six probes I precompute the DAG at module import time into a `tuple[tuple[Probe, ...], ...]` — each tuple is a "wave" of probes that can run in parallel. Two waves: `(LanguageDetection,)` then `(NodeBuildSystem, NodeManifest, CI, Deployment, TestInventory)`. No per-run topological sort.
  - **Hot-path probe execution is `await` in the same event loop.** No thread pool, no process pool. Tier-0 and Tier-1 probes are pure-Python parse work; the GIL is irrelevant because we're parsing JSON/YAML, which releases the GIL in the C parsers. Concurrency is for hiding I/O, and at Layer A the only I/O is reading manifest files which the PathIndex already stat'd.
  - **`asyncio.Semaphore(min(os.cpu_count(), 8))`** stays — but Layer A almost never hits it because the 5 parallel probes in wave 2 are bounded by `min(5, semaphore)` anyway. The semaphore exists for Phase 2 Layer C, not for me.
  - **Cancellation is cooperative**, not best-effort. Each probe awaits `asyncio.sleep(0)` between major parse steps (reading lockfile → walking workspaces → emitting slice). Phase 14's webhook flood can pre-empt long-running probes cheaply.
- **Tradeoffs accepted:**
  - The explicit DAG means adding a new Layer A probe is two edits, not one (decorator + DAG tuple). Phase 0's `@register_probe` decorator + `requires:` lookup is preserved as the fallback for non-hot-path probes; this is an opt-in fast path. The cost is one tuple edit per new Layer A probe — bounded scope, well-known seam.

### 3. PathIndex-aware Probe mixin (`codegenie/probes/path_index_aware.py`)

- **Purpose:** Give Layer A probes a typed handle to the precomputed PathIndex without changing the Phase 0 ABC.
- **Interface:** A mixin class probes inherit from when they want PathIndex access. `def use_path_index(self, idx: PathIndex) -> None` is called by the coordinator before `run()`. Probes that don't inherit it get an empty stub.
- **Internal design:** Sets `self._idx`. Provides typed accessors: `files_with_extension(".ts") -> tuple[FileEntry, ...]`, `manifest_path("package.json") -> Path | None` (single dict lookup on `by_path`), `monorepo_marker_present() -> bool`. These are the operations all six Layer A probes do.
- **Tradeoffs accepted:** A second class hierarchy alongside `Probe`. Worth it because the alternative is every Layer A probe re-implementing "find me the package.json" or accepting a `PathIndex` constructor argument that breaks ABC byte-for-byte.

### 4. LanguageDetectionProbe (extends Phase 0)

- **Purpose:** Phase 0 already shipped this. I'm describing only the Layer A delta.
- **Interface:** Same. `schema_slice` output unchanged.
- **Internal design:**
  - **No filesystem walk** — reads `PathIndex.by_extension` lengths.
  - **Framework hints** (NestJS, Express, Fastify, Next.js) detected from `package.json`'s declared dependencies (parsed once by NodeManifestProbe and cached in-process for this gather — see the dependency note in NodeBuildSystemProbe below). `LanguageDetection` no longer parses package.json itself.
  - **Monorepo detection** via `PathIndex.manifests_present` set-membership check: `{"pnpm-workspace.yaml", "lerna.json", "nx.json", "turbo.json"} & manifests_present`.
- **Tradeoffs accepted:** Framework hints are now a Tier-1 output (not Tier-0). On the absolute cold path where NodeManifestProbe hasn't run yet, framework hints are empty; the planner doesn't strictly need them at language-detection-time anyway (they're consumed by Stage 3 Planning, which by then has the full context).

### 5. NodeBuildSystemProbe (`codegenie/probes/node_build_system.py`)

- **Purpose:** Detect package manager, Node version constraints, build commands, bundler, TypeScript config.
- **Interface:** outputs the `build_system` slice from `localv2.md §5.1 A2`.
- **Internal design:**
  - **`package.json` is parsed exactly once per gather** by `NodeManifestProbe` and the parsed dict is stuffed into `ProbeContext.workspace` as a sibling file `.parsed/package.json.msgpack` (msgpack chosen because it's ~10x faster than JSON for round-trip on dicts of this size). NodeBuildSystem reads the msgpack, not the raw JSON. Inter-probe sharing without violating the ABC: the contract still says "I read declared_inputs"; the implementation just notices the parsed form is available.
  - **Lockfile detection by manifest presence**, no file open. `pnpm > yarn > bun > npm` precedence is a single set-membership chain on `PathIndex.manifests_present`.
  - **`tsconfig.json` parsed with `orjson`** if installed (5–10x faster than stdlib `json` on real-world configs that contain comments — wait, no, `orjson` is strict JSON; `tsconfig.json` allows JSON5. Use `json5` library with its C extension `pyjson5`. Bench at integration time; if `pyjson5` underperforms a fork to `orjson` with a strip-comments pass, switch).
  - **Bundler detection from declared dependencies**, not from config-file probing. `webpack` in `dependencies` → bundler is webpack. One dict lookup per bundler. The config-file probe is a fallback only.
- **Tradeoffs accepted:**
  - The msgpack-cache-of-parsed-package.json pattern is an inter-probe optimization. It's documented as such; it's not a new contract. If a future Layer A probe doesn't want to read the msgpack it can re-parse from the source. Surfaced in Phase 0's chokepoint discussion as the "in-process probe cache."
  - I'm adding `msgpack` and `pyjson5` (or `orjson`) to dependencies. That's two new dependencies; they're both fast, stable, widely used. Justified by the warm-path latency target.

### 6. NodeManifestProbe (`codegenie/probes/node_manifest.py`)

- **Purpose:** Parse `package.json`, lockfile, detect native modules. The most expensive Layer A probe on cold gather (lockfile parsing dominates).
- **Interface:** outputs `manifests[]` slice per `localv2.md §5.1 A3`.
- **Internal design:**
  - **Lockfile parsing is the hot inner loop.**
    - `pnpm-lock.yaml`: parsed with `ruamel.yaml` in C-extension mode if available; fall back to `pyyaml.CSafeLoader`. *Never* `pyyaml.SafeLoader` (pure Python). `ruamel` is faster on large lockfiles but adds a dep; bench at integration; choose the winner.
    - `package-lock.json`: `orjson.loads` if available else stdlib `json`.
    - `yarn.lock`: there's no fast Python parser. Use the `@yarnpkg/parsers` JS package via a one-time `node -e` invocation, *or* a hand-rolled parser that handles only the 3 features we actually consume (package names, versions, integrity hashes). I'll hand-roll: the format is regular, and avoiding a node subprocess per gather is worth ~200 ms.
  - **Native module detection by package-name catalog match.** The catalog (`codegenie/catalogs/native-modules.yaml`) is a frozenset loaded once at module import. Match is `O(1)`: iterate parsed dependencies once, check `name in CATALOG`. No regex; no version range eval.
  - **Integrity validation deferred to Phase 2.** Lockfile integrity is a Phase 2 concern (B2 IndexHealth). Layer A reports `integrity_valid: null` with confidence `medium`; Phase 2 fills it in. Saves ~150 ms on the warm path.
  - **`engines` field extracted from the already-parsed `package.json`** (the msgpack cache). One dict access.
  - **In-place dict mutation in the parse-to-slice transform.** No copy of the lockfile data; build the output slice as a slim projection, drop references to the source dict at function exit. RSS doesn't grow.
- **Tradeoffs accepted:**
  - Hand-rolled `yarn.lock` parser is a maintenance liability. Mitigation: 1k LOC tops, fuzzed against real yarn.lock files in CI, falls back to the node subprocess if parsing returns empty. The fallback is a feature flag; the perf-first design ships with the hand-rolled parser on by default.
  - Native module catalog is "data, not prompts." Adding a native module is a YAML edit. Consistent with `production/design.md §2.6` ("Organizational uniqueness as data, not prompts").

### 7. CIProbe (`codegenie/probes/ci.py`)

- **Purpose:** Detect GitHub Actions / CircleCI / GitLab CI / Jenkins.
- **Interface:** outputs `ci` slice per A4.
- **Internal design:**
  - **Detection by directory presence**, not by parsing. `.github/workflows/` exists → GitHub Actions. `.circleci/` exists → CircleCI. Boolean short-circuit; no file I/O.
  - **Workflow YAML parsing only for the *one* workflow we care about** (the one matching `name: ci` or the alphabetically-first one if absent). Parsing every workflow file in a heavy repo is wasted work for Stage 3, which only consumes the build/test commands.
  - **`pyyaml.CSafeLoader`** mandatory; `pyyaml.SafeLoader` banned by Phase 0's `forbidden-patterns` hook.
- **Tradeoffs accepted:**
  - Skipping non-primary workflows means we miss multi-workflow setups (e.g., separate `build-image.yml` and `release.yml`). For Phase 1's exit criterion (useful `repo-context.yaml`), the primary workflow is enough. Phase 2's IndexHealthProbe can surface "we didn't parse 3 other workflows" as a confidence hit if it matters.

### 8. DeploymentProbe (`codegenie/probes/deployment.py`)

- **Purpose:** Detect Helm / Kustomize / Terraform / plain k8s manifests.
- **Interface:** outputs `deployment` slice per A5.
- **Internal design:**
  - **Existence check before parse.** `deploy/`, `helm/`, `charts/`, `k8s/`, `kustomization.yaml` — directory/file existence drives 90% of the classification.
  - **Helm `values.yaml` parsed only for the `image:` block**; nothing else is consumed by Stage 3 Planning. Selective key extraction via streaming YAML parse: use `ruamel.yaml`'s event-driven parser to stop at the first `image:` key, not full document parse.
  - **Terraform parsing optional.** `hcl2` is slow (pure Python, ~50 ms per file). Skipped by default; opt-in via `--probe-opts deployment.terraform=true`.
- **Tradeoffs accepted:**
  - Streaming YAML parse for one key is fragile (key ordering, nested anchors). If it fails it falls back to full-parse. Worth it on the happy path which is 99% of repos.
  - Terraform-off-by-default trades coverage for warm-path latency. Surface in the report as `deployment.terraform_skipped: true`.

### 9. TestInventoryProbe (`codegenie/probes/test_inventory.py`)

- **Purpose:** Detect test framework, count tests, find smoke test, read coverage.
- **Interface:** outputs `test_inventory` slice per A6.
- **Internal design:**
  - **Framework detection from `package.json` `devDependencies`**, not from filesystem scan. The msgpack-cached parsed package.json is reused. One dict lookup per framework.
  - **Test count from `PathIndex.by_extension[".test.ts"] + by_extension[".test.js"] + by_extension[".spec.ts"] + by_extension[".spec.js"]`** — len() on precomputed tuples. ~5 microseconds.
  - **Coverage data parsed lazily**: only if `coverage/lcov.info` exists *and* the planner declares `requires_evidence: test_inventory.coverage`. The probe emits `coverage_data.present: true, path: ...` without parsing the file. Phase 2's planner-on-demand-read pattern.
- **Tradeoffs accepted:**
  - We don't actually count tests; we count test *files*. A file with 30 `it()` blocks counts as 1. Stage 3 Planning consumes the count to pick recipes; recipes don't care about per-`it` granularity. Cheaper, less informative, sufficient.

### 10. Cache-layer hot path (`codegenie/cache/store.py` extensions)

- **Purpose:** Make the warm-path cache lookup memoryless from a wall-clock perspective.
- **Interface:** Phase 0 API unchanged; adds an in-process LRU.
- **Internal design:**
  - **`functools.lru_cache`-style in-process layer** above the Phase 0 filesystem store. `maxsize=128` (covers all probes on a portfolio of ~20 concurrently-being-gathered repos at the per-worker level — Phase 14's worker model).
  - **Cache lookup is one BLAKE3 of the PathIndex slice + one in-process dict lookup.** The slice is precomputed; the hash is ~1 microsecond per KB. For Layer A's typical declared_inputs (~5 files, ~20 KB total), the hash is ~50 microseconds.
  - **mmap of the on-disk index is now a yes.** Phase 0 deferred mmap citing cross-platform and concurrency concerns. I push back: macOS dev workstations are not the portfolio-scale target; Phase 14 runs Linux in k8s. Add mmap behind a feature flag `--cache-mmap` (default on Linux, default off on macOS). The Phase 0 critique that "the index is single-digit MB through Phase 13" was scoped to single-repo; portfolio cache at Phase 14 will see GB-scale aggregate. **Surfacing the conflict with Phase 0's no-mmap stance — this is the one place I push back on the prior phase.**
  - **Hash-validation on read is skipped on the LRU layer.** The on-disk store re-hashes blob contents per ADR-0006's integrity model; the in-process LRU trusts itself (it's in our address space). Saves ~200 microseconds per cache hit. Surfaces as a risk if RAM corruption is in the threat model; it's not.
- **Tradeoffs accepted:**
  - LRU size of 128 assumes the worker doesn't gather more than 128 distinct probe-keys concurrently. Fine for portfolio gather; might thrash on a one-shot CLI gather of a 10k-repo monorepo. Mitigation: `--lru-size` flag.
  - Pushing back on Phase 0's mmap stance is a real disagreement. I'm flagging it as an open question for the synthesizer; if Phase 0 stays no-mmap, my numbers move by ~5%.

### 11. Streaming writer + hot-view projection (`codegenie/output/writer.py` extensions)

- **Purpose:** Don't buffer the whole `RepoContext` in memory before writing. Pre-render the Phase-8 hot views as a side artifact during write.
- **Interface:** Phase 0's atomic-write semantics preserved.
- **Internal design:**
  - **YAML stream emission as probes finish.** Each probe's slice is written under its top-level key as soon as the slice arrives at the merger. The trailing `gather_status` and any cross-probe summary fields are written last. Reduces peak RSS by ~30% on a real Node repo (~200 KB YAML).
  - **`views.json` sibling artifact.** During the write pass, project the four ADR-0013 hot-view slices (`available_skills`, `entrypoint`, `risk_flags`, `confidence_summary`) directly into a JSON file at `.codegenie/context/views.json`. Phase 8 reads this and loads it into Redis without a YAML parse round-trip. **Pre-shaping for the Phase 8 hot path is the explicit cite of ADR-0013 — I'm doing the projection work now, two phases early, because it's free here (the data is in hand) and expensive there (Phase 8 would otherwise parse the YAML to project).**
  - **Sanitizer integrated into the streaming write**, not as a post-pass. The Phase 0 sanitizer's two passes (field-name regex + path scrub) run on each slice as it's emitted; no second walk over the merged dict.
- **Tradeoffs accepted:**
  - Streaming YAML emission means a probe failure mid-write leaves a partial artifact. Atomic-write via `.tmp` + `os.replace` still applies (the `.tmp` file is the streaming target); on probe failure the `.tmp` is unlinked and the previous artifact is preserved. Net: same correctness as Phase 0's batch write, lower peak RSS.
  - `views.json` is a Phase-1 artifact for a Phase-8 consumer. That's a forward dependency. Surface as a stable schema (`views.schema.json` lands in Phase 1); Phase 8 either consumes it or ignores it. If Phase 8 changes its hot-view list, Phase 1 follows; no breaking change for Phase 2–7.

## Data flow

Walk-through of one representative warm-path incremental gather on a 50k-LOC Node.js service:

1. **Trigger:** push webhook fires for `repo-1234`. Continuous Gather Dispatcher (Phase 14 — for Phase 1 this is the CLI) invokes `codegenie gather <path>`.
2. **CLI startup (≤ 80 ms):** lazy imports per Phase 0. Click parses args. Pydantic, jsonschema, pyyaml not yet imported.
3. **SnapshotBuilder (≤ 200 ms warm):** one `os.scandir` walk. ~50k files visited, ~8k in non-excluded dirs. Per-file work: `stat`, byte-pack into the fingerprint buffer, append to appropriate `by_extension` bucket. BLAKE3 of the packed buffer = `path_index_fingerprint`. RSS at this point ~30 MB.
4. **Prelude probe (LanguageDetection, ≤ 8 ms):** cache key = `sha256("language_detection", "v1", "v1", path_index_fingerprint)`. LRU hit (this is an incremental run; the PathIndex fingerprint matches the previous run because no `.js`/`.ts` files changed). Output materialized from LRU.
5. **Coordinator builds enriched snapshot:** `dataclasses.replace(snapshot, detected_languages=...)`. ≤ 1 ms.
6. **Wave 2 dispatch (5 probes in parallel):** for each probe, compute cache key from `(probe.name, probe.version, sub_schema_version, content_hash_of(declared_inputs))`. The content hash is computed *from the PathIndex* (the sizes and mtimes are already in hand); no re-reading of files. ≤ 10 ms total for all 5 cache-key computations.
7. **Cache lookups:** LRU first, on-disk store second. Assume `package.json` changed (push triggered the gather because someone bumped a dep): NodeManifest misses cache. The other 4 hit LRU.
8. **NodeManifest re-execute (~400 ms warm):** `package.json` parsed with `orjson` (~3 ms). `pnpm-lock.yaml` parsed with `ruamel.yaml` C-mode (~280 ms — the dominant cost, ~50k LOC of lockfile). Native module catalog match (~5 ms). Slice emission (~10 ms). msgpack-cache the parsed package.json for in-process reuse (~5 ms).
9. **NodeBuildSystem cache-hit → on-disk store hit (~3 ms):** the declared_inputs hash for NodeBuildSystem is `(package.json, pnpm-lock.yaml, .nvmrc, tsconfig.json)`. `package.json` changed; cache miss. Re-execute: read the msgpack-cached parsed package.json (~1 ms), pull engines + scripts + bundler hints (~5 ms). Total ~12 ms (msgpack saved us ~200 ms of re-parsing).
10. **CI, Deployment, TestInventory all LRU hits.**
11. **Streaming write begins:** as each probe completes (in any order), its slice is sanitized and appended to `repo-context.yaml.tmp`. Total write wall-clock ~80 ms.
12. **Hot-view projection:** during the write pass, `views.json.tmp` is populated with the four hot-view slices. ~5 ms.
13. **Schema validation:** `jsonschema.Draft202012Validator` (compiled-once, `lru_cache`'d) walks the in-memory dict. ~30 ms on a typical envelope.
14. **Atomic rename:** `os.replace` on both `.tmp` files. ~2 ms.
15. **Total wall-clock:** ~750 ms p50; ~1.2 s p95 on this scenario. Under the 4-s warm-path target.

For the pure no-change incremental gather (PathIndex fingerprint matches previous run), step 4 already provides the answer — total wall-clock ≤ 250 ms (dominated by the SnapshotBuilder walk).

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| LanguageDetection LRU stale (PathIndex fingerprint matches but on-disk filesystem changed under our feet — e.g., a parallel git checkout) | `path_index_fingerprint` mismatch on next gather | Next gather invalidates; correctness preserved at the cost of one extra warm gather. Surfaced in logs as `lru.stale_detected` event. |
| `pnpm-lock.yaml` parse timeout (huge lockfile, ruamel.yaml hangs) | Phase 0 per-probe `wait_for(timeout_s=30)` | `ProbeOutput(errors=["lockfile parse timeout"], confidence="low")`; gather continues with degraded NodeManifest slice; planner sees `confidence: low` and routes to RAG/LLM fallback. |
| Hand-rolled `yarn.lock` parser returns empty (format edge case we didn't handle) | Empty `direct_dependencies.production` on a repo where `package.json` declares deps | Coordinator detects the inconsistency (parsed package.json has deps; lockfile parse says none). Falls back to `node -e` subprocess parser. Surfaces as `node_manifest.fallback_parser_used` in the audit record. |
| msgpack cache corruption between probes | NodeBuildSystem's read of the msgpack fails with a parse error | Re-parse `package.json` from source. Add ~3 ms; correctness preserved. Surfaces as `inter_probe_cache.miss` in logs. |
| `views.json` schema doesn't match what Phase 8 expects | Phase 8 contract test (when Phase 8 lands) | Phase 1 ships `views.schema.json` as a versioned contract. Phase 8 either pins to v1 or migrates Phase 1 first. No silent drift. |
| LRU thrash on a workstation gathering a 10k-repo monorepo | RSS pressure observed | `--lru-size` flag to cap; default sized for portfolio-worker model. |
| Probe declares `declared_inputs` that doesn't actually capture all files it reads | Cache hit on a run where the un-declared input changed → stale slice | Out of scope for Phase 1 to *prevent*; Phase 2's IndexHealthProbe catches it. Phase 1 adds a `tests/adv/test_declared_inputs_completeness.py` fuzz test that mutates files outside `declared_inputs` and asserts cache hit — at least we know we're testing the property. |
| mmap-on-Linux flag enabled on a filesystem that doesn't support mmap (some FUSE setups) | mmap call returns EINVAL | Catch, fall back to plain buffered read, log once per process. |
| Streaming write fails after some slices were written | `.tmp` file exists but is incomplete | The previous valid `repo-context.yaml` is still in place (atomic rename hasn't happened). Unlink the `.tmp`; exit non-zero per Phase 0's exit code map. |

## Resource & cost profile

- **Tokens per run:** 0. (ADR-0005 — no LLM in gather.)
- **Wall-clock per run:**
  - Cold (first gather of a 50k-LOC Node repo): p50 ~8 s, p95 ~12 s. Dominated by initial PathIndex walk + first lockfile parse.
  - Warm (no cache, but PathIndex fingerprint partial-match): p50 ~750 ms, p95 ~1.2 s.
  - Incremental (no relevant file changed): p50 ~180 ms, p95 ~250 ms. Dominated by SnapshotBuilder walk + LRU.
- **Memory per worker:** ~80 MB resident between gathers; ~250 MB peak during a cold gather (PathIndex + lockfile dict + writer buffers). RSS returns to ~80 MB after gather completes (PathIndex dropped, msgpack cache cleared).
- **CPU per run:** Cold ~6 CPU-seconds. Warm ~1.5 CPU-seconds. Incremental ~0.3 CPU-seconds.
- **Storage growth rate:** `.codegenie/cache/blobs/` grows ~10 KB per cache entry per probe per content hash. For a portfolio of 1000 repos with 6 probes and ~50% weekly churn, ~30 MB/week of blobs. `cache gc` subcommand (from Phase 0) compacts weekly.
- **Hot vs cold cost ratio:** ~40× (cold 6s vs incremental 0.15s). This is the whole point of Phase 1's design — ADR-0006 says "continuous gather"; this ratio is what makes continuous gather affordable.
- **Per-probe peak RSS (advisory budget enforced from Phase 0):**
  - LanguageDetection: 5 MB.
  - NodeBuildSystem: 15 MB.
  - NodeManifest: 80 MB (lockfile parse dominates).
  - CI: 5 MB.
  - Deployment: 10 MB.
  - TestInventory: 5 MB.

## Test plan

Performance regression tests live alongside correctness tests, *not* in a separate suite. The Phase 0 `tests/bench/` directory is reused; tests are advisory-gated by default and CI-blocking on PRs that touch the cache, coordinator, or PathIndex.

- **`tests/bench/test_warm_path_latency.py`** — canary. Runs a `gather` against a committed 50k-LOC Node fixture twice (warm + warm-with-one-file-changed). Asserts:
  - Warm p95 ≤ 1.5 s (50% headroom over the 1.0 s target).
  - Incremental p95 ≤ 350 ms (40% headroom).
  - Cache hit rate ≥ 5/6 probes on incremental.
  - Test is hermetic: uses `freezegun` for time, fixed seed for any randomness, runs N=10 iterations and reports p50/p95/p99.
  - Failure mode: **CI-blocking** on PRs touching `src/codegenie/cache/`, `src/codegenie/coordinator/`, or `src/codegenie/probes/`. Advisory elsewhere.
- **`tests/bench/test_path_index_fingerprint_stability.py`** — asserts the same repo content yields the same fingerprint across runs and across machines (no embedded absolute paths, no platform-specific mtime granularity assumptions). This is *correctness* of the cache key; a flaky fingerprint silently kills the cache hit rate.
- **`tests/bench/test_per_probe_rss.py`** — uses `tracemalloc` to measure peak allocation per probe against a fixture; asserts the per-probe budget from §"Resource & cost profile".
- **`tests/unit/test_streaming_writer.py`** — asserts incremental probe completion produces an incrementally-growing `.tmp` file and that the final atomic-renamed YAML matches the all-at-once baseline byte-for-byte.
- **`tests/unit/test_views_json_projection.py`** — given a populated `RepoContext`, asserts the four hot-view slices are projected correctly and that `views.json` validates against `views.schema.json`. This is the Phase-8 forward-compat contract test.
- **`tests/adv/test_lru_correctness.py`** — fuzz test: mutate the underlying filesystem between gathers without touching the PathIndex; assert the gather still produces a correct artifact (the LRU must not lie about file contents it didn't actually see).
- **`tests/adv/test_cache_invalidation_on_probe_version_bump.py`** — bump a probe's `version` constant; assert next gather is a miss; assert the artifact still validates.
- **`tests/integration/test_real_repo_gather.py`** — clones a small real OSS Node repo (e.g., `expressjs/express` mirror, pinned to a SHA), runs gather twice, asserts:
  - First run: cold path, produces a valid `repo-context.yaml`.
  - Second run: incremental path, ≥ 5/6 probes cache-hit. (This is the roadmap's literal exit criterion, with a measurable assertion.)
  - JSON Schema validation passes in both runs.

CI canary policy: the warm-path latency test is the regression gate. A 20% degradation on warm p95 or incremental p95 fails CI. Cold p95 is measured but advisory (cold-path regressions matter less; portfolio steady-state is warm).

## Risks (top 3–5)

1. **mmap-on-Linux flag conflict with Phase 0's "no mmap" stance.** I am explicitly pushing back on a Phase 0 decision. The Phase 0 critique cited Windows behavior, concurrent CLI races, and "single-digit MB through Phase 13." All three are scoped concerns; my position is that portfolio scale at Phase 14 changes the math. If the synthesizer keeps no-mmap, warm-path latency moves by ~5%. **Surface as load-bearing disagreement, not silent revision.**
2. **Inter-probe in-process cache (msgpack-of-parsed-package.json) is a new pattern.** It's not in the Phase 0 ABC and not in `localv2.md §4`. It's a coordinator-level optimization that probes opt into. Risk: a future engineer treats it as the contract and starts requiring it. Mitigation: documented as "implementation detail of the in-process coordinator; not part of the ABC; probes must work without it." Phase 9's Temporal lift will *not* have this in-process cache (Activities run in separate workers); the lift is correct because each Activity re-parses. Performance regresses at Phase 9 — surfaced now so it's not a surprise then.
3. **Hand-rolled `yarn.lock` parser is a sharp edge.** I'm choosing it over a `node` subprocess for ~200 ms of warm-path latency. The maintenance cost over the lifetime of the project might exceed that win. Mitigation: feature flag, fuzz-tested in CI, falls back to subprocess on parse-empty. If we ever see a real bug from the hand-rolled parser, flip the flag.
4. **`views.json` is a forward dependency on Phase 8.** Phase 1 ships an artifact for a consumer two phases away. Versioned schema mitigates breaking-change risk; the risk is that Phase 8's hot-view list changes and Phase 1's projection is wrong. Mitigation: `views.schema.json` is in the same repo as the Phase-1 implementation; both move together.
5. **Per-probe ResourceBudget RSS enforcement is "advisory" in Phase 0.** I'm relying on advisory tracking for tight per-probe RSS budgets. If a probe silently breaches its budget (e.g., a pathological lockfile expands the heap), the worker OOMs at portfolio scale without warning. Mitigation: bench tests in `tests/bench/test_per_probe_rss.py` are advisory in Phase 1 but the planned Phase-14 RSS-enforcement landing must include Layer A probes in the first batch. **Open question for the synthesizer: should Phase 1 ship hard RSS enforcement for Tier-0 probes (cheap, all pure Python) even though Phase 0 deferred it?**

## Acknowledged blind spots

- **Cold-path latency.** I optimized for warm and incremental. Cold gathers on huge monorepos (`turbo`-style 100+ package workspaces) might hit 30s+; I did not model that workload. Stage 0 Discovery in Phase 10 will eventually need to cold-gather lots of repos in parallel; my numbers don't say anything about that.
- **Network probes.** Layer A is fully filesystem-local. Layer B (Phase 2) introduces network calls (registry lookups, advisory fetches). My streaming writer + LRU don't help there; the perf-first design for Phase 2 will need a different shape (connection pooling, batched fetches).
- **macOS dev UX.** I default mmap off on macOS, hand-rolled parsers can have platform-specific behavior, and the C-extension YAML loader's mtime granularity differs across filesystems. I haven't bench-tested on macOS; my numbers are Linux numbers.
- **Security posture of the in-process LRU.** Phase 0's structural trust boundary (`_ProbeOutputValidator`) runs *before* the LRU read on cache hit, but only when the probe newly executes. On LRU hit the ProbeOutput skips the validator. This is a deliberate optimization. The security lens will object; the answer is "the LRU only holds outputs that were validated when they were inserted." If the validator's invariants change (e.g., new secret regex), LRU entries don't re-validate. Either invalidate the LRU on validator version bump (one extra bit in the LRU key) or accept a one-shot recheck on validator change.
- **Bencher methodology.** All my latency numbers are "estimated from the design"; I have not run them against a real fixture. The bench tests are designed; the numbers will move. I committed to targets, not measurements.
- **Phase 2 collision.** Phase 2 introduces IndexHealthProbe, which observes Layer A's confidence claims. If Layer A claims `confidence: high` but skipped tail features (e.g., non-primary workflow files for CI), IndexHealthProbe surfaces it as `confidence_impact: medium`. I traded coverage for latency in CIProbe and DeploymentProbe; that trade is paid for in Phase 2's confidence story, not Phase 1's.

## Open questions for the synthesizer

1. **mmap-on-Linux:** keep my proposed flag (default on for Linux) or honor Phase 0's no-mmap stance? My ~5% warm-path number rests on this.
2. **In-process inter-probe cache (msgpack-of-parsed-package.json):** is this an acceptable Phase-1 pattern, or should the synthesizer push it back to a per-probe parse with the same ~200 ms cost?
3. **`views.json` forward-compat with Phase 8:** ship in Phase 1, or wait? The work is free now; the contract risk is real.
4. **`pyjson5` vs `orjson` + comment-strip vs sticking with stdlib `json` for `tsconfig.json`:** I'm proposing `pyjson5` for correctness on JSON5 syntax. Phase 0 didn't take a position. The dep-add cost is low; the perf delta vs stdlib `json` (after a regex comment-strip) is ~10 ms per gather. Bench at integration; let the synthesizer pick the floor.
5. **Hard RSS enforcement for Layer A Tier-0 probes:** ship now, or defer to Phase 14 with the rest? My numbers say Tier-0 is cheap to enforce.
6. **Hand-rolled `yarn.lock` parser:** ship it, or take the `node` subprocess hit until someone needs the latency? My answer is "ship, behind a flag, with subprocess fallback"; the synthesizer can flip the default.
7. **The roadmap exit criterion "useful repo-context.yaml":** my warm/incremental targets are ~5–20× more aggressive than the roadmap implies. Is the synthesizer optimizing for the roadmap's spec, or for the production-target ADR-0006 throughput? My answer is "ADR-0006"; the synthesizer might disagree.
