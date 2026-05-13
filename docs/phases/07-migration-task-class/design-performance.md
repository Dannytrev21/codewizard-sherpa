# Phase 07 — Add migration task class (Chainguard distroless): Performance-first design

**Lens:** Performance — throughput, latency, token economy, footprint.
**Designed by:** Performance-first design subagent
**Date:** 2026-05-12

## Lens summary

Phase 7's headline is "extension by addition" — but the *performance* story it tells is "the second task class costs almost nothing per workflow because everything expensive is shared with the first." The two slow knobs on a distroless migration are (1) **Docker image work** (pull, build, scan, dive) and (2) **runtime tracing** (the new `ShellInvocationTraceProbe`). Both are far more expensive than anything Phase 3–6 had to deal with — a single `docker buildx` against an unwarmed base can take 30–90s, a `grype` scan another 20–40s, a `dive` walk 5–15s, and the runtime trace by definition has to *boot the candidate container* and exercise the entrypoint. Naïvely added, this task class would 5–10× the per-workflow wall-clock and the per-workflow disk footprint, and it would push the Phase 5 microVM gate cluster from "occasionally tight" to "the bottleneck of the whole pipeline." So this design treats Phase 7 not as "more probes + more recipes" but as the moment we **introduce a content-addressed Docker-artifact cache, a base-image catalog hot view, a per-step Buildx layer cache, and shared trace baselines** so that the second, fifth, and fiftieth distroless migration ride on warmed shelves. The recipe path stays the cheap path — a YAML base-image swap with a deterministic `FROM` line replacement plus a multi-stage refactor template — and the RAG/LLM tiers stay only for the long tail (custom base images, entrypoints calling `bash -c`, glibc-vs-musl edge cases). Every cache key is shape-compatible with Phase 8's hot views and Phase 9's Temporal idempotency primitive, so the perf work here is forward-amortized. The mandatory pre-merge regression suite (the Phase 7 entry gate from `roadmap.md`) is the *other* perf story: it has to be fast enough to not bottleneck Phases 8–16, so this design specifies its parallelism shape (xdist worker-per-fixture, per-fixture frozen `node_modules` tarball, registry-mirror reuse) up front.

Departures from the obvious approach are deliberate and called out: **no `docker run` of the rebuilt image in Phase 7's hot path** — `ShellInvocationTraceProbe` runs against a **prebuilt fixture image at gather time**, not against the candidate image at gate time; gate-time runtime checks reuse Phase 5's strace overlay against the rebuilt image's `ENTRYPOINT` in `--no-network --short-lived` mode with a 10s budget. **No new microVM profile** — Phase 5's chokepoint is extended via a `task_class=migration` overlay flag, identical pattern to Phase 5's `test_execution=True` overlay. **No persistent Buildx daemon** — buildkit is invoked stateless per call but pointed at a content-addressed disk layer cache (`.codegenie/cache/buildkit/`) so warm builds skip pulled-layer work entirely.

## Goals (concrete, measurable)

Targets are on the Phase 3/5/6 fixture portfolio extended with **3 distroless-migration fixtures**: (a) a small Node 18 Express service using `node:18-alpine`, (b) a multi-stage Node build with a runtime that uses `node:18`, (c) a Node service that calls `sh -c` from `package.json` scripts at runtime (the long-tail case that should fall through to RAG/LLM in Phase 4's terms).

| # | Goal | Target |
|---|---|---|
| 1 | **Workflows-per-hour, single-worker, distroless task class only** | ≥ 6 / hr cold (no caches), ≥ 30 / hr warm (Buildx layer cache + base catalog hot) |
| 2 | **Workflows-per-hour, mixed portfolio (vuln + distroless), single-worker** | ≥ 12 / hr warm — the vuln path is unchanged; distroless rides on shared caches |
| 3 | **Time-to-PR p95, distroless recipe hot path** | ≤ 180 s (recipe match → buildx warm → grype warm → strace 10 s) |
| 4 | **Time-to-PR p95, distroless RAG-fallback path** | ≤ 360 s |
| 5 | **Time-to-PR p95, distroless LLM-fallback path** | ≤ 540 s |
| 6 | **$/PR, distroless recipe path** | **$0** (no LLM call; Buildx + grype are CPU only) |
| 7 | **$/PR, distroless LLM-fallback path** | ≤ $0.12 (Sonnet 4.7; ≥ 80% prompt-cache hit per Phase 4) |
| 8 | **Buildx layer-cache hit rate across the 3-fixture portfolio after first run** | ≥ 85% on pulled base layers; ≥ 60% on derived layers |
| 9 | **`grype` DB cache hit rate** | 100% within `grype.db_max_age` (24h default); single fetch per gather portfolio |
| 10 | **`dive` invocation latency p95** | ≤ 10 s per candidate image (multi-stage Node ≤ 200 MB final) |
| 11 | **`ShellInvocationTraceProbe` p95 (gather-time)** | ≤ 30 s per fixture image; cached on `(image_digest, entrypoint_argv)` |
| 12 | **Cold-image-pull amortization** | First gather pulls each base once (`node:18-alpine`, `cgr.dev/chainguard/node:latest-dev`, `cgr.dev/chainguard/node:latest`); subsequent gathers across N repos in the same portfolio: 0 re-pulls |
| 13 | **Per-worker steady-state memory ceiling** | ≤ 2.4 GB (Phase 4 ceiling 1.7 GB + 700 MB for buildkit/grype/dive transient peaks) |
| 14 | **Regression suite wall-clock — full vuln + distroless** | p50 ≤ 4 min, p95 ≤ 7 min on the 4-vCPU CI runner with `-n auto` xdist parallelism and `tests/fixtures/buildkit-cache/` checked out as a git LFS pack |
| 15 | **Tokens per run inside Phase 7's package boundary** | 0 — recipe path emits 0; RAG path = Phase 4's RAG budget unchanged; LLM-fallback path = Phase 4's per-invocation cap unchanged |
| 16 | **Storage growth rate per workflow (distroless)** | ≤ 40 MB durable, ≤ 250 MB ephemeral (rebuilt image stored as a manifest reference + layer-cache delta; image bytes themselves live in containerd's content store, not under `.codegenie/`) |
| 17 | **Cache-key hash overhead per probe** | ≤ 100 µs (BLAKE3 over declared inputs; Phase 1 baseline holds) |

## Architecture

```
                       codegenie loop run <repo> --task distroless
                                       │
                                       ▼  (Phase 6 entry — cli/loop.py)
                          ┌──────────────────────────────────┐
                          │  build_distroless_loop()          │  [NEW, Phase 7 — Phase 6 builds it]
                          │  same shape as vuln_loop          │
                          └──────────────┬───────────────────┘
                                         │
                                         ▼
              ┌──────────────────────────────────────────────────────────┐
              │  Stage 1: Load context — RepoContext for distroless       │
              │   - reads .codegenie/context/repo-context.yaml            │
              │   - requires NEW slices populated: base_image,            │
              │     shell_invocation, dockerfile_parse, sbom              │
              │   - IndexHealthProbe (B2) reports cv ≥ medium on those    │
              │   - if missing → --auto-gather kicks Phase 0/1/2 +        │
              │     Phase 7's new probes                                  │
              └──────────────────┬───────────────────────────────────────┘
                                 │
                                 ▼
              ┌──────────────────────────────────────────────────────────┐
              │  Stage 2: Resolve target image                            │
              │   - reads tools/cve-to-distroless-map.yaml (CVE → image)  │
              │   - reads .codegenie/cache/base_catalog.json hot view     │  [Phase 13 hot-view seam]
              │   - chooses Chainguard target (e.g., cgr.dev/chainguard/  │
              │     node:18-latest-dev for build, :18-latest for runtime) │
              └──────────────────┬───────────────────────────────────────┘
                                 │
                                 ▼
              ┌──────────────────────────────────────────────────────────┐
              │  Stage 3: Plan transform — recipe → RAG → LLM             │  [reuses ADR-0011 chain]
              │   recipes = [DockerfileBaseImageSwap, MultiStageRefactor] │
              │   selector returns RecipeSelection(reason=...)            │  [reuses Phase 3 ABC]
              │   - matched: emit FixPlan(steps=[swap_from, swap_runtime])│
              │   - miss → Phase 4's RagLlmEngine on a distroless         │
              │     solved-example corpus shard                           │
              └──────────────────┬───────────────────────────────────────┘
                                 │
                                 ▼
              ┌──────────────────────────────────────────────────────────┐
              │  Stage 4: Apply transform — Transform ABC unchanged       │  [reuses Phase 3 ABC]
              │   - DockerfileTransform implementation                    │
              │   - writes Dockerfile bytes (deterministic ordering)      │
              │   - git format-patch -1 --stdout                          │
              └──────────────────┬───────────────────────────────────────┘
                                 │
                                 ▼
              ┌──────────────────────────────────────────────────────────┐
              │  Stage 5: Phase 5 GateRunner — three retries, gate YAML   │  [extends YAML catalog]
              │   gates/catalog/stage6_validate_distroless.yaml           │
              │   required signals (additive):                            │
              │     - build (buildx → candidate image manifest)           │
              │     - grype (scan candidate image; cve_delta.direction)   │
              │     - dive (image-size + efficiency signal)               │  [NEW kind, registered]
              │     - shell_presence (entrypoint shell-invocation diff)   │  [NEW kind, registered]
              │     - trace (10 s strace boot of ENTRYPOINT)              │
              │   isolation_class propagates as in Phase 5                │
              └──────────────────┬───────────────────────────────────────┘
                                 │
                                 ▼
              ┌──────────────────────────────────────────────────────────┐
              │  Stage 6: emit_artifact / escalate                        │
              └──────────────────────────────────────────────────────────┘

  Cross-cutting performance plumbing (NEW under .codegenie/):
    .codegenie/cache/buildkit/        ← content-addressed Buildx layer cache (oci-dir)
    .codegenie/cache/grype-db/        ← grype vulnerability DB, single fetch / 24h TTL
    .codegenie/cache/dockerfile-parse/← Pydantic-serialized DockerfileParseResult
                                        keyed on (file_blake3, dockerfile-parse-digest)
    .codegenie/cache/strace/          ← gather-time trace digests keyed on
                                        (image_digest, entrypoint_argv_blake3)
    .codegenie/cache/base_catalog.json← Phase 8-shaped hot view (pre-rendered)
                                        keyed on chainguard-registry-snapshot-sha

  Package layout (additions on top of Phase 6 — NO edits to Phase 0–6):
  src/codegenie/
    probes/
      base_image.py              ← BaseImageProbe (Layer C extension)
      shell_invocation_trace.py  ← ShellInvocationTraceProbe (Layer C extension)
      dockerfile_parse.py        ← DockerfileParseProbe (already-stubbed in Phase 2;
                                    now real implementation registered in addition)
    tools/
      buildkit.py                ← thin wrapper around `docker buildx build`
      dive.py                    ← thin wrapper around `dive --json`
      dockerfile_parse_wrap.py   ← thin wrapper around python `dockerfile-parse`
    recipes/catalog/
      distroless_node_swap.yaml          ← FROM-line swap recipe
      distroless_node_multistage.yaml    ← multi-stage refactor recipe
    transforms/
      dockerfile_transform.py    ← Transform ABC implementation for Dockerfile
    rag/
      seed_corpus/distroless/    ← seed solved examples for the RAG-fallback path
    sandbox/signals/
      dive.py                    ← @register_signal_kind("dive")
      shell_presence.py          ← @register_signal_kind("shell_presence")
    gates/catalog/
      stage6_validate_distroless.yaml
    graph/
      distroless_loop.py         ← build_distroless_loop() — same shape as vuln_loop
    cli/
      sherpa.py                  ← codegenie sherpa run <repo> --task {vuln,distroless}
                                   (NEW dispatch entry — does NOT edit cli/loop.py
                                    or cli/remediate.py per Phase 6 exit criterion)
    skills/catalog/
      distroless-migration.skill.md   ← YAML-frontmatter Skill
    catalogs/
      cve_to_distroless.yaml     ← CVE → recommended Chainguard target map

  Phase 0 fence policy CI updates (importer allowlist additions):
    probes/base_image.py             may import tools/buildkit, tools/dockerfile_parse_wrap
    probes/shell_invocation_trace.py may import tools/buildkit (gather-time strace runs
                                                                  inside Phase 5 chokepoint)
    transforms/dockerfile_transform  may NOT import langgraph|anthropic|chromadb
    sandbox/signals/dive             may NOT import langgraph|anthropic|chromadb
    sandbox/signals/shell_presence   may NOT import langgraph|anthropic|chromadb
    recipes/catalog/distroless_*     no import — they are data
```

## Components

### 1. `BaseImageProbe` (new Layer C probe)

- **Purpose:** Capture the repo's current base image(s), tagged digests, layer counts, and known CVEs **as evidence** — no judgment about whether they should be migrated.
- **Interface:** Standard `Probe` ABC (ADR-0007). `applies_to_tasks = ["*"]` (evidence is reusable), `applies_to_languages = ["*"]` (base image is language-agnostic), `declared_inputs = ["Dockerfile", "Dockerfile.*", ".dockerignore"]` plus a *fingerprint* input on `~/.docker/config.json` registry-mirror configuration (which can change the resolved digest).
- **Internal design:**
  - Reads `Dockerfile` via Phase 2's existing `DockerfileParseProbe` output if present in the snapshot; else invokes `dockerfile-parse` directly via `tools/dockerfile_parse_wrap.py`. Sub-200 µs typical.
  - For each parsed `FROM` reference, resolves the *current* digest via `docker buildx imagetools inspect --raw` (single HTTPS roundtrip, cacheable). Cache key: `(image_ref, registry_mirror_id)`. TTL: 24h.
  - Slices emitted: `base_image.references[]`, `base_image.is_multistage`, `base_image.stage_count`, `base_image.has_distroless_compatible_runtime` (heuristic: `entrypoint_uses_shell == False && expressly_known_runtime ∈ {node, python, java, ...}`). The last field is fact-shaped — it's a boolean derived from observed strings, not a recommendation.
  - **No `docker pull` here** — `inspect --raw` is a manifest-only roundtrip (small KB-sized JSON, no layer bytes). Pulls happen only at build time, against the Buildx layer cache.
- **Tradeoffs accepted:**
  - Slight false-positive risk on `is_multistage` for Dockerfiles that use `--target` from outside the file; documented as a known fact-not-judgment limitation. Defer to entrypoint runtime evidence (`ShellInvocationTraceProbe`).
  - Manifest-resolution cache can go stale within the TTL if Chainguard rotates a tag mid-day. The cache stores the digest plus a `resolved_at` timestamp; the IndexHealthProbe (B2) reports `confidence: medium` if `resolved_at` is >12h old.

### 2. `ShellInvocationTraceProbe` (new Layer C probe, expensive)

- **Purpose:** Observe whether the *current* container's entrypoint actually invokes a shell at runtime. This is the empirical evidence that decides whether a distroless target is viable: distroless images have no shell, so an entrypoint that secretly relies on `sh -c` will break.
- **Interface:** Standard `Probe` ABC. `applies_to_tasks = ["distroless-migration"]` (this probe is expensive enough to gate); `applies_to_languages = ["*"]`. `declared_inputs = ["Dockerfile", "Dockerfile.*", "package.json"]` plus an external fingerprint on `image_digest` of the *currently built* image (so an image rebuild from the same Dockerfile against a new base invalidates the cache).
- **Internal design — this is the perf-load-bearing one:**
  - Cache key: `(dockerfile_blake3, package_json_blake3, base_image_digest, strace_wrapper_digest)`. The wrapper digest pins exact strace flags so wrapper changes invalidate cleanly.
  - Cache **hit** path: read `(.codegenie/cache/strace/<key>.json.zst)`, return `ShellInvocationTraceResult`. Sub-2 ms.
  - Cache **miss** path:
    1. `docker buildx build --load --cache-from=type=local,src=.codegenie/cache/buildkit --cache-to=type=local,dest=.codegenie/cache/buildkit,mode=max .` against a small synthetic top-stage that copies the entrypoint script and any runtime config. **Layer cache hits make repeat invocations of this step cheap on the second-and-after fixture.**
    2. `docker run --rm --network=none --pids-limit=64 --memory=512m --read-only --tmpfs /tmp -v /tmp/strace.out:/strace.out:rw <image> /usr/bin/strace -f -e trace=execve -o /strace.out -- <entrypoint>` for **at most 10 s** (`SIGTERM` on budget exhaust). Returns the set of `execve` argv[0]s observed.
    3. Result is a boolean `entrypoint_invokes_shell: bool` plus `shell_invocations[]` (sorted, deduped, fact-shape: just argv[0]+argv[1] for each call). No judgments.
  - The probe runs inside Phase 5's `run_in_sandbox` chokepoint with a `task_class=migration` overlay flag (a tiny additive flag, identical pattern to Phase 5's `test_execution=True` overlay) — **no new sandbox profile is added**.
  - **Probe applies_to_tasks gate:** if a workflow runs only vuln remediation, this probe never executes. If a workflow runs a portfolio-wide gather that includes distroless, it runs once per repo and the result lives in cold storage forever (the fingerprint is stable on dockerfile+package.json+image-digest).
- **Tradeoffs accepted:**
  - 10 s budget might miss late-binding shell invocations (e.g., a Node service that shells out only on a specific request). Documented in the probe's confidence model: confidence is `medium` if the 10 s budget was hit without termination signals; `high` if the entrypoint completed under budget.
  - Requires `docker run` on the dev laptop. On macOS, Docker Desktop's Linux VM hosts the strace. On Linux CI, it's native. No new dependency beyond Docker (already required by Phase 2's `SBOMProbe`).

### 3. Recipe selector additions

- **Purpose:** Extend Phase 3's `RecipeSelector` with two new YAML recipes — `distroless_node_swap.yaml` and `distroless_node_multistage.yaml` — **without editing Phase 3 selector code**. Recipes are data; Phase 3's selector reads them from the catalog directory.
- **Interface:** Same `RecipeEngine` ABC. The recipes themselves declare `applies_to_tasks: ["distroless-migration"]` so the selector returns `RecipeSelection(reason="catalog_miss", ...)` cleanly for vuln workflows.
- **Internal design:**
  - `distroless_node_swap.yaml` matches when `base_image.is_multistage == False && shell_invocation_trace.entrypoint_invokes_shell == False && language == "node"`. The recipe's transform is a single regex-pinned `FROM` line swap to the Chainguard equivalent picked from `cve_to_distroless.yaml`. **No LLM. Sub-1 ms transform.**
  - `distroless_node_multistage.yaml` matches when `base_image.is_multistage == True && ...`. The transform writes a templated multi-stage Dockerfile that pins both `node:latest-dev` (build stage) and `chainguard/node:latest` (runtime stage). Templated via plain `string.Template` — no Jinja, no LLM.
  - Both recipes' applied bytes are routed through Phase 3's deterministic ordering helper so diffs are byte-stable across runs.
- **Tradeoffs accepted:**
  - The two recipes cover the common case but not custom base images (e.g., `acme-corp/node-with-curl:18`). Those fall through to `reason="catalog_miss"` and are handled by Phase 4's RAG/LLM. Acceptable: Phase 4's machinery is unchanged.
  - The CVE→image map (`cve_to_distroless.yaml`) is a static catalog at v0.7.0. Phase 15 (agentic recipe authoring) will eventually generate entries; Phase 7 ships ~30 hand-curated entries.

### 4. Buildx layer cache + `grype-db` cache

- **Purpose:** Make `docker buildx build` and `grype` cheap on the second-and-after call.
- **Interface:** Filesystem only. No process. Cache directories under `.codegenie/cache/buildkit/` and `.codegenie/cache/grype-db/`.
- **Internal design:**
  - **Buildkit:** every `tools/buildkit.py` invocation appends `--cache-from=type=local,src=$BUILDX_CACHE --cache-to=type=local,dest=$BUILDX_CACHE,mode=max`. The cache is content-addressed (buildkit's native OCI layout). Multiple parallel workers reading the same cache is safe — buildkit's local-cache export is concurrency-tolerant.
  - **Grype DB:** `grype db update` runs at most once per 24h, controlled by a sentinel file `.codegenie/cache/grype-db/.last_update`. All concurrent gather processes coordinate via a `flock(2)` advisory lock on that sentinel; the second arriver sees the recent update and skips the network call.
  - Both caches are subject to a portfolio-level GC: `codegenie cache gc` (a new CLI subcommand under Phase 0's CLI namespace) evicts entries with no `last_used` access in 30 days. The GC is operator-invoked, not automatic — surprise eviction during a long run would invalidate active cache keys.
- **Tradeoffs accepted:**
  - Filesystem-backed caches can grow to multi-GB on busy CI runners. Disk usage is documented; the regression suite's CI cache footprint is capped to 2 GB via a separate `tests/fixtures/buildkit-cache/` git-LFS pack that's restored before the suite runs.
  - No cross-host cache sharing in Phase 7. Phase 8's Redis hot views will overlay a small key→cache-location map; Phase 9's Postgres + object store will subsume the cache for distributed workers. Phase 7's filesystem cache is the cheap forward-shape.

### 5. Pre-rendered `base_catalog` hot view

- **Purpose:** Make recipe selection sub-millisecond by caching the resolved CVE→image map plus current Chainguard image digests.
- **Interface:** A single JSON file `.codegenie/cache/base_catalog.json` keyed on a snapshot SHA of the `cve_to_distroless.yaml` catalog plus the current Chainguard registry index.
- **Internal design:**
  - Rendered at end-of-gather by a new function `render_base_catalog()` called from Phase 2's gather coordinator after the (cached) `imagetools inspect` results land. Rendering itself is plain Python dict construction; sub-50 ms.
  - The hot view is **shape-compatible with Phase 8's Redis layout** (ADR-0013): same JSON schema, same key, same staleness signal. Phase 8 lifts the file into Redis without schema changes. This is the canonical "pre-render the seam" pattern.
  - On `codegenie sherpa run --task distroless`, `RecipeSelector` reads `base_catalog.json` once via `mmap`; subsequent lookups are dict-access (microseconds).
- **Tradeoffs accepted:**
  - The catalog is read-only during a workflow run; if Chainguard publishes a new image mid-run, the workflow uses the staler image until the next gather. Acceptable: distroless target selection is more stable than CVE feeds.

### 6. `dive` signal (new sandbox signal kind)

- **Purpose:** Emit image-efficiency facts — final image size, percentage of layer bytes that survived, count of unused files — as a gate signal.
- **Interface:** `@register_signal_kind("dive")` in `sandbox/signals/dive.py`. Returns a `DiveSignal` Pydantic fragment with fields `final_size_bytes`, `efficiency_pct`, `wasted_bytes`. Strict-AND inputs are: `final_size_bytes < base_image_size_bytes * 1.5` (a regression guard) and `efficiency_pct >= 0.85` (efficiency floor). Both are advisory at first — gate emits `confidence: low` rather than hard-fail — until Phase 13's calibration window passes.
- **Internal design:**
  - `tools/dive.py` invokes `dive --json --ci <image_digest>` inside Phase 5's sandbox chokepoint. Wall-clock p95 ≤ 10 s on a 200 MB final image.
  - Caches on `(image_digest, dive_binary_digest)`. Two workflows on the same rebuilt image (e.g., a retry without changes) hit the cache.
- **Tradeoffs accepted:**
  - Dive doesn't have a stable CLI between minor versions. We pin `dive` via `tools/digests.yaml` and re-vendor on upgrade.

### 7. `shell_presence` signal (new sandbox signal kind)

- **Purpose:** Gate the candidate (rebuilt) image on the absence of a shell binary in the runtime layer.
- **Interface:** `@register_signal_kind("shell_presence")` in `sandbox/signals/shell_presence.py`. Strict-AND input: `runtime_shell_count == 0`.
- **Internal design:**
  - Reads the rebuilt image's manifest (no full pull needed beyond the buildkit cache that already has the layers) and lists files in `/bin/`, `/usr/bin/`, `/usr/local/bin/` looking for known shell names. Done via `dive --json` output, which already enumerates files per layer — **no extra invocation**, just a different projection on the dive result. This is why the dive signal collector lands first.
  - p95 ≤ 50 ms once dive has run.

### 8. `build_distroless_loop()` — the LangGraph factory

- **Purpose:** Provide a Phase 6-shaped state machine for the distroless workflow without editing `build_vuln_loop()`.
- **Interface:** Identical signature to `build_vuln_loop()`: `(checkpointer, max_attempts=3, force_rebuild=False) -> CompiledGraph`. Module-level lazy compile, same pattern.
- **Internal design:**
  - Nodes: `ingest_target`, `resolve_image`, `select_recipe`, `apply_recipe`, `rag_lookup`, `replan_with_phase4`, `validate_in_sandbox`, `record_attempt`, `await_human`, `emit_artifact`, `escalate`. Note: 11 nodes vs `vuln_loop`'s 10 — the extra node is `resolve_image`, which reads `base_catalog.json` and picks the target Chainguard image. Cheap (sub-ms).
  - Edges have the same conditional shape as `vuln_loop` — `select_recipe → {matched: apply_recipe, miss: rag_lookup}`, etc. — so retry semantics are inherited verbatim.
  - Shared `VulnLedger` schema? **No** — a parallel `MigrationLedger` with `extra="forbid"`, `schema_version: Literal["v0.7.0"]`, and a different field set (no `cve_id`; instead `base_image_ref`, `target_image_ref`, `dockerfile_path`). The two ledgers live side by side and are dispatched by `codegenie sherpa run --task <name>`.
- **Tradeoffs accepted:**
  - Two ledgers is two schemas to evolve, not one. Trade-off chosen deliberately: trying to make `VulnLedger` cover both task classes would force fields like `cve_id: str | None` into the vuln ledger and `dockerfile_path: str | None` into something else, and the validity invariants would become messy. Discrete ledgers per task class is the extension-by-addition shape; the dispatch CLI (`codegenie sherpa`) is the single entry point that knows about both.

### 9. `codegenie sherpa run` — the dispatch CLI

- **Purpose:** Provide a single CLI surface that dispatches into the correct task-class loop without editing Phase 6's `cli/loop.py` or Phase 3's `cli/remediate.py`.
- **Interface:** `codegenie sherpa run <repo> --task {vuln,distroless} [--cve <id>] [--target <image>]`. Subcommands: `run`, `resume`, `inspect`, `replay` — same as Phase 6's `loop` subcommand surface.
- **Internal design:**
  - Pure router: dispatches on `--task` to `build_vuln_loop()` or `build_distroless_loop()`. ~30 LOC.
  - Phase 8's Hierarchical Planner will replace this dispatch with its routing supervisor; `codegenie sherpa` stays as the operator-facing CLI surface that the supervisor sits behind.

## Data flow

**End-to-end run, Phase 7's hot path — distroless migration of a Node Express service that's seen no prior distroless work:**

1. **Cold gather** (one-time, amortized across the portfolio): `codegenie gather <repo>` runs Phase 0–2 + the two new probes. `BaseImageProbe` resolves the `node:18-alpine` manifest digest (1 HTTPS roundtrip; cached for 24h). `ShellInvocationTraceProbe` runs once: build the current image into the Buildx cache (~30 s cold pull, 0 s warm), `docker run --rm` for ≤10 s with strace, result cached on `(dockerfile_blake3, image_digest, strace_wrapper_digest)`. Total cold gather adds ≤60 s on top of Phase 2's existing budget. `render_base_catalog()` writes `.codegenie/cache/base_catalog.json` at end-of-gather.
2. **Workflow start:** `codegenie sherpa run --task distroless <repo>` dispatches into `build_distroless_loop()`. The compiled graph is module-level singleton-cached. LangGraph node-overhead is ≤5 ms per node (Phase 6 canary baseline holds).
3. **Stage 1 Load context:** mmap-read `repo-context.yaml`, validate schema. `<1 ms`.
4. **Stage 2 Resolve image:** mmap-read `base_catalog.json`, look up `node:18-alpine` → `cgr.dev/chainguard/node:latest-dev` (build stage) + `cgr.dev/chainguard/node:latest` (runtime stage). `<1 ms`.
5. **Stage 3 Select recipe:** `RecipeSelector` matches `distroless_node_swap.yaml` (or `_multistage.yaml` depending on `base_image.is_multistage`). Recipe load is filesystem read once + cache. **p50 ≤ 3 s** dominated by selector startup, not the match itself.
6. **Stage 4 Apply transform:** write the new `Dockerfile`. Sub-1 ms.
7. **Stage 5 Phase 5 GateRunner:** five signals in parallel where independent (build → grype + dive in parallel; dive feeds shell_presence; trace runs in parallel with grype on the rebuilt image):
   - **build** signal: `tools/buildkit.py` runs `docker buildx build --load --cache-from=local --cache-to=local mode=max .`. Warm cache: 10–25 s. Cold: 60–90 s.
   - **grype** signal: scans the rebuilt image manifest. Warm DB: 8–15 s. Cold DB: +20–30 s (one-time).
   - **dive** signal: parses layer bytes from buildkit's local cache (no extra pull). ≤10 s.
   - **shell_presence** signal: projection on the dive result. ≤50 ms.
   - **trace** signal: Phase 5 strace overlay against the rebuilt image entrypoint, 10 s budget, `--network=none --short-lived`. ≤12 s.
   Strict-AND over the seven signals (Phase 3's six + dive + shell_presence + trace, minus tests if the repo has none): pass or fail.
8. **Stage 6 emit_artifact:** writes the patch + branch `codegenie/distroless/<short-sha>`, audit chain extended with Phase 7 event types (`base_image.resolved`, `dockerfile.transformed`, `dive.scanned`, `shell_presence.checked`, etc.).

**Parallelism:**
- Probes inside a gather: Phase 1's bounded worker pool, unchanged.
- Gate signals: Phase 5's GateRunner already parallelizes signal collection where the YAML catalog declares no dependency; the distroless catalog adds the dive→shell_presence dependency edge.
- Portfolio-level workflows: independent worker processes, sharing the same Buildx + grype caches via filesystem locks.

**Caching layering (cheapest to most expensive):**
1. Pre-rendered `base_catalog.json` — single dict lookup.
2. Manifest-digest cache (`imagetools inspect` results) — sub-ms.
3. Buildkit layer cache — re-uses layer bytes; saves the actual layer-build work.
4. Grype DB cache — saves 20–30s of DB fetch on every workflow after the first 24h.
5. Strace gather-time cache — saves 30–60s per fixture image after the first observation.
6. Phase 4's prompt cache + RAG corpus — unchanged.

**Serialization points (where the system would benefit from parallelism but doesn't have it in Phase 7):**
- Cold base-image pull: serializes the first workflow on each base. Acceptable: subsequent workflows ride the cache. Phase 9's distributed warmer (out of Phase 7 scope) can pre-warm.
- Stage 5 build: parallel inside a workflow's signal collection, but multiple concurrent workers building the same image both pay the build cost (they share the layer cache but not the `--load` work). Phase 9's Temporal workflow idempotency handles this; Phase 7 accepts the cost.

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| Chainguard registry unreachable for `imagetools inspect` | `tools/buildkit.py` HTTPS roundtrip non-200 | `BaseImageProbe` emits `confidence: low`, `references[].resolved_at = null`; gather succeeds; recipe selector falls through to `catalog_miss` (Phase 4 RAG/LLM owns the fallback) |
| Buildx layer cache corruption (rare; partial write) | Build exit code ≠ 0 with cache-IO error in stderr | Retry once with `--cache-from` only (no `--cache-to`); if that succeeds, GC and rebuild the corrupted entry; if not, emit signal `confidence: low` |
| Grype DB update fails (network) | `grype db update` non-zero exit | Fall back to the last cached DB if `last_update < 7d`; emit `cve_delta` signal with `confidence: medium`; emit `evidence_stale: true` audit event |
| Dive binary version drift | `dive_binary_digest` mismatch on cache lookup | Cache miss; re-run dive; record the new digest in `tools/digests.yaml` (operator-gated commit) |
| Strace probe times out (10s budget exhausted) | `subprocess.TimeoutExpired` from sandbox chokepoint | `ShellInvocationTraceResult.confidence = "medium"`, `entrypoint_invokes_shell = "unknown"`; recipe selector treats `unknown` as "do not match `distroless_node_swap`" — falls through to RAG/LLM |
| Rebuilt image build fails inside Phase 5 sandbox | `build` signal exit code ≠ 0 | Phase 5's three-retry loop kicks in; retry-1 re-enters Phase 4 with `prior_attempts` (per Phase 5 exit criterion #19); RAG can suggest a different target image |
| `shell_presence` signal sees a shell in the rebuilt image | Strict-AND fails on `runtime_shell_count == 0` | Retry: Phase 4 replans with a different target (`chainguard/node:latest-dev` vs `chainguard/node:latest`); if all retries fail, `await_human` escalation |
| `dive` reports `final_size_bytes > 1.5 × base_size_bytes` | Strict-AND signal fails | Advisory in v0.7.0 (logs `confidence: low`, does not hard-fail); the gate passes if all other signals do. Phase 13 calibration window decides whether to harden |
| Multiple concurrent gathers race on `grype db update` | `flock(2)` contention on `.last_update` sentinel | First-arriver wins; later arrivers see fresh sentinel, skip the update. Tested with a deterministic stress test in CI |
| `base_catalog.json` schema drift after a YAML catalog edit | `RecipeSelector` raises `BaseCatalogSchemaDrift` on load | Operator command `codegenie cache rebuild base-catalog` regenerates from `cve_to_distroless.yaml`; failure is loud, not silent |
| Phase 7 graph edits Phase 0–6 file (exit criterion violation) | Phase 0 `fence` CI job + a new `tests/contract/test_no_phase_0_6_edits.py` that asserts the diff for the Phase 7 PR touches only allowed paths | PR refuses to merge; Phase 7 author refactors via the addition seam |

## Resource & cost profile

- **Tokens per run:**
  - Recipe path: **0**.
  - RAG-fallback path: Phase 4's RAG-hit shape unchanged; 0 LLM tokens.
  - LLM-fallback path: ≤40k input + 8k output (Phase 4 caps unchanged); ≤$0.12 with ≥80% prompt-cache hit per goal #7.
  - Probes: 0. Recipe catalog: 0. Gate signals: 0.

- **Wall-clock per run** (4-vCPU CI / M-series Mac, distroless task only):
  - Recipe hot path (warm caches, ≤120 unit tests): **p50 ≈ 75 s, p95 ≤ 180 s.**
  - Recipe cold path (cold buildkit cache, cold grype DB): p50 ≈ 165 s, p95 ≤ 290 s.
  - RAG-fallback hot path: p50 ≈ 220 s, p95 ≤ 360 s.
  - LLM-fallback path: p50 ≈ 340 s, p95 ≤ 540 s.

- **Memory per worker** (steady-state, single workflow active):
  - Orchestrator + planner + LangGraph compiled cache: ~280 MB (Phase 6 baseline).
  - ChromaDB mmap + embed worker: ~720 MB (Phase 4 baseline; only loaded if RAG path engages).
  - Buildkit/grype/dive transient peaks: ~700 MB (only during Stage 5).
  - **Ceiling: 2.4 GB.** Above the Phase 4 baseline (1.7 GB) by 700 MB attributable to Docker subprocesses. If memory pressure hits Phase 9's worker pods (out of Phase 7 scope), each pod runs one workflow at a time per scheduler config; Phase 7 itself runs single-worker locally.

- **Storage growth rate:**
  - Per workflow durable: ≤40 MB (patch + branch + audit chain extension entries + `MigrationLedger` checkpoint).
  - Per workflow ephemeral: ≤250 MB (rebuilt image manifest reference; the actual image bytes live in containerd's content store, not under `.codegenie/`).
  - Portfolio-level caches: `.codegenie/cache/buildkit/` grows to multi-GB on busy runners; capped via `codegenie cache gc`. `.codegenie/cache/grype-db/` is ~150 MB. `.codegenie/cache/strace/` is <1 MB per fixture image.

- **Hot vs cold cost ratio:**
  - Time-to-PR hot/cold ratio: ~2.2× (75 s hot vs 165 s cold on the recipe path).
  - Build-cost hot/cold ratio (buildkit alone): ~6× (warm builds reuse 85%+ of pulled layer bytes).
  - Strace gather-time hot/cold ratio: ~25× (sub-2 ms cached read vs ~50 s cold build+strace).
  - The compound effect on portfolio-scale throughput is what makes goal #2 (≥12 workflows/hr warm, single-worker) achievable.

## Test plan

**Unit tests (per-component, fast):**
- `tests/unit/probes/test_base_image_probe.py` — golden fixtures: single-stage Dockerfile, multi-stage, Dockerfile with `ARG`-parameterized FROM, invalid Dockerfile (recipe fall-through path).
- `tests/unit/probes/test_shell_invocation_trace_probe.py` — fixture images bundled as `.tar` artifacts (lazy-loaded), strace output mocked via recorded JSON for the happy path; one integration test that actually runs strace (slow, marked `@pytest.mark.docker`).
- `tests/unit/recipes/test_distroless_node_swap.py` — byte-deterministic transform: 5× same input → identical bytes.
- `tests/unit/sandbox/signals/test_dive_signal.py` — recorded `dive --json` output; assert size/efficiency/wasted parsing.
- `tests/unit/sandbox/signals/test_shell_presence_signal.py` — fixture dive output with and without `/bin/sh`; assert strict-AND signal value.
- `tests/unit/graph/test_distroless_loop_topology.py` — golden-graph JSON snapshot (Phase 6's `get_graph().to_json()` pattern), assert no Phase 0–6 graph topology touched.

**Integration tests (slow, run in CI):**
- `tests/integration/test_phase7_e2e_recipe_path.py` — fixture (a): Express service with `node:18-alpine` → recipe match → apply → all gates pass → patch produced. Uses the pre-warmed `tests/fixtures/buildkit-cache/` LFS pack so wall-clock is bounded.
- `tests/integration/test_phase7_e2e_rag_path.py` — fixture (b): multi-stage build with a custom intermediate image not in the catalog → `catalog_miss` → Phase 4 RAG-fallback → known seed example matches → patch produced. Asserts $0 spend.
- `tests/integration/test_phase7_e2e_llm_path.py` — fixture (c): Node service that calls `sh -c` from `package.json` scripts at runtime → strace probe reports `entrypoint_invokes_shell=True` → recipe `catalog_miss` → RAG miss → Phase 4 LLM-fallback → cassette-driven LLM response → patch produced. Asserts ≤$0.12 spend per goal #7.
- `tests/integration/test_phase7_extension_by_addition.py` — runs `git diff HEAD~1 -- src/codegenie/` and asserts only paths under `probes/`, `tools/buildkit.py`, `tools/dive.py`, `tools/dockerfile_parse_wrap.py`, `recipes/catalog/distroless_*`, `transforms/dockerfile_transform.py`, `rag/seed_corpus/distroless/`, `sandbox/signals/dive.py`, `sandbox/signals/shell_presence.py`, `gates/catalog/stage6_validate_distroless.yaml`, `graph/distroless_loop.py`, `cli/sherpa.py`, `skills/catalog/distroless-migration.skill.md`, `catalogs/cve_to_distroless.yaml` plus the documented additive seams in `src/codegenie/probes/__init__.py` and `src/codegenie/sandbox/signals/__init__.py` are touched. **This test is the exit-criterion enforcement.**

**Regression suite (mandatory pre-merge per roadmap):**
- `tests/integration/test_phase3_*.py`, `tests/integration/test_phase4_*.py`, `tests/integration/test_phase5_*.py`, `tests/integration/test_phase6_*.py` — all run unchanged. Parallelized via `pytest-xdist -n auto`. Wall-clock budget: **p50 ≤ 4 min, p95 ≤ 7 min**. If the budget regresses, the bench in `tests/perf/test_regression_suite_wall_clock.py` fires.
- The suite uses `tests/fixtures/buildkit-cache/` (git LFS) and `tests/fixtures/grype-db/` (git LFS) to bypass cold-cache penalties. CI pulls LFS once per PR.

**Performance regression canary:**
- `tests/perf/test_phase7_canary.py` — runs `build_distroless_loop().ainvoke()` on a no-op fixture 100× and records p50/p95 node overhead vs `tests/perf/baseline.json`. Fails on regression >25% (same shape as Phase 6's canary).
- `tests/perf/test_buildkit_cache_hit_rate.py` — runs three fixtures back-to-back with a shared `.codegenie/cache/buildkit/`, asserts ≥85% pulled-layer cache hits on the second-and-after fixture per goal #8.
- `tests/perf/test_workflow_throughput.py` — runs 6 cold workflows + 30 warm workflows back-to-back, asserts goal #1 wall-clock per worker.

**What's not tested in Phase 7 (deferred):**
- Cross-host cache sharing (Phase 9).
- Concurrent workflow contention on Buildkit (Phase 9's Temporal idempotency).
- ROI dashboard cost attribution (Phase 13).
- Real PR opening (Phase 11).

## Risks (top 5)

1. **Strace probe is the new B2.** `ShellInvocationTraceProbe` is to Phase 7 what `IndexHealthProbe` is to Phase 2 — silent staleness or silent under-coverage is the worst failure mode. If a workflow's strace cache says `entrypoint_invokes_shell=False` because the 10 s budget was hit before the late-binding shell call fired, the recipe path picks `distroless_node_swap`, the gate sees no shell in `/bin/`, build/test/grype all pass, and the resulting image **breaks at production runtime on the request that triggers the shell call**. Mitigation: confidence signal hardened to `medium` on budget exhaust; the gate's strict-AND treats `medium` as a fail; the human-merge requirement (ADR-0009) is the last line. The probe ships with an adversarial fixture: a Node service that shells out only on a `/admin` route, with the request firing at strace second 11. Documented as known-acceptable.

2. **Buildkit cache as shared mutable state.** A cache poisoning bug in `tools/buildkit.py` (e.g., writing a malformed layer) would invalidate every subsequent workflow's cache hits and could mask CVE-bearing layers. Mitigation: buildkit's native content-addressed format makes physical poisoning hard (cache entries are hashed); we add a per-entry `created_by_codegenie_version` annotation so a version mismatch evicts forward. No cross-tenant cache reuse in Phase 7 (single-tenant local).

3. **The 10 s strace budget is wrong.** If real-world entrypoints routinely take longer to reach steady-state, the cache is full of `confidence: medium` entries, which all fail the gate, which pushes everything to Phase 4 LLM-fallback, which blows the $/PR budget. Mitigation: the budget is configurable in `tools/digests.yaml` (operator-tunable); we ship with 10 s but the bench tracks the distribution of `entrypoint_steady_state_time` across the fixture portfolio in `tests/perf/baseline.json`; if p95 exceeds 8 s we bump to 15 s with an ADR amendment.

4. **The regression-suite wall-clock target (p95 ≤ 7 min) becomes unachievable as the fixture portfolio grows.** Every later phase adds more fixtures; by Phase 12 the suite could easily exceed 20 min. Mitigation: Phase 7 ships `tests/perf/test_regression_suite_wall_clock.py` as a budget-tracking canary, so the cost of *adding* a fixture is visible to the author at PR-review time. Phase 8+ can shard the suite via Temporal child workflows or `pytest-xdist --tx=...`. We accept that Phase 7's target is a Phase-7-era target.

5. **`base_catalog.json` becomes stale faster than the IndexHealthProbe can detect.** Chainguard rotates image tags continuously; a stale catalog points to a digest that's been GC'd from `cgr.dev` (rare but possible). Mitigation: the catalog records `resolved_at` per entry; `BaseImageProbe` reads `resolved_at` and emits `confidence: medium` on entries >12h old; the gate treats `medium` as advisory; the operator-gated `codegenie cache refresh base-catalog` command forces a re-resolution. Phase 14 will replace this with continuous gather + webhooks.

## Acknowledged blind spots

- **Security defense-in-depth around the Docker daemon socket.** This design assumes Phase 5's microVM chokepoint isolates the buildkit + dive + grype invocations. If the chokepoint leaks (a Docker Desktop vulnerability, a buildkit RCE), Phase 7's new probes are the largest single attack surface. The security-first design lens for this phase will need to cover this in detail — including signed-base verification (Chainguard signs its images; we don't verify the signatures in Phase 7, deferring to Phase 16).
- **Multi-arch builds.** `docker buildx build --platform linux/arm64,linux/amd64` is common in real portfolios; this design assumes amd64-only for the v0.7.0 fixtures and defers multi-arch to a Phase 7.1 follow-up. The Buildkit cache shape supports it; the goal numbers don't.
- **Chainguard rate limits and credentials.** The roadmap mentions Chainguard registry credentials. This design assumes a single shared credential in `~/.docker/config.json`; no per-workflow scoping. Cost-attribution implications for Phase 13 are left to that phase.
- **`dockerfile-parse` Python library limitations.** It doesn't handle BuildKit-specific syntax (`# syntax=docker/dockerfile:1.6`) or Dockerfiles with `--mount=type=...` flags perfectly. The probe degrades gracefully to `confidence: low` on parse failure; full coverage is a Phase 7.1 ask.
- **glibc-vs-musl runtime semantics.** Switching from `node:18-alpine` (musl) to `chainguard/node:latest` (glibc) can break native modules. The strace probe catches the symptom (a failing `execve` of a native lib) but the LLM-fallback's fix quality on glibc/musl bugs is unmeasured in v0.7.0. Documented; not blocking.
- **Concurrent worker contention on `grype db update` `flock`.** Tested with a stress test, but the `flock` discipline is platform-dependent (macOS BSD flock vs Linux fcntl-based flock); cross-platform fixture coverage is partial.
- **Image-pull bandwidth, not just latency.** Goal #12 ("0 re-pulls") assumes each base image fits comfortably on disk. A 1.2 GB base on a CI runner with a 5 GB free-disk budget plus a multi-fixture portfolio could push GC to evict actively-used layers mid-suite. We monitor disk usage in `tests/perf/test_regression_suite_disk_footprint.py`.
- **No Phase 9 worker awareness.** This design optimizes the single-worker local case; Phase 9's Temporal worker pool will need a layer-cache distribution story (Redis-backed manifest cache + object-store-backed layer cache), which Phase 7's filesystem cache is forward-shaped for but doesn't pre-build.

## Open questions for the synthesizer

1. **Should `MigrationLedger` and `VulnLedger` share a common base class?** I argued no (extension by addition; separate ledgers per task class). The best-practices lens may argue yes (single `WorkflowLedger` with task-class discriminator) for forward compatibility with Phase 8's Supervisor. The conflict-resolution decision will affect how Phase 8 routes between subgraphs.
2. **Strace 10 s budget — fixed, configurable, or adaptive?** Performance argues configurable (in `tools/digests.yaml`); security may argue fixed (operator surface = attack surface). Adaptive (extend budget if late-binding shell signal is observed in repeat runs) is forward-attractive but introduces per-repo state into the cache, which Phase 7 avoided.
3. **Should `dive` and `shell_presence` be one signal collector or two?** Performance argues two (the projection on dive output is cheap; separate collectors keep `applies_to_tasks` honest). Best-practices may argue one (less surface). The synthesis affects the gate YAML schema.
4. **Does `ShellInvocationTraceProbe`'s 10 s budget need an audit-chain event for budget exhaustion?** I emit `strace.budget_exhausted` as an event. Security may want to harden this to a strict-AND signal failure (not just a confidence drop). The trade-off is over-escalation of long-running entrypoints to `await_human` in legitimate cases.
5. **`base_catalog.json` schema-version pinning.** I pin it to `Literal["v0.7.0"]` like `VulnLedger`. If Phase 8's Redis hot view lifts the file, does it need a different versioning story for migrations across Redis<->filesystem? Out of scope for Phase 7, but the synthesizer should flag it for Phase 8.
6. **Pre-warm strategy for `cgr.dev` base images.** Phase 7 does not include a pre-warm step — the first workflow pays the cold pull. Should the gather coordinator emit a `pre_warm_recommended` advisory when `BaseImageProbe` resolves a digest that's not in the local layer cache? Cheap to add; the operator could invoke `codegenie cache prewarm` once per portfolio.
7. **CVE→image map (`cve_to_distroless.yaml`) versioning.** I ship ~30 entries hand-curated at v0.7.0 and treat the file as data. Phase 15 (agentic recipe authoring) is supposed to grow it. Is there an intermediate phase where humans add entries via PR with a CI test enforcing entry shape? Synth should decide whether to ship an entry-validation CI gate in Phase 7 or defer.
