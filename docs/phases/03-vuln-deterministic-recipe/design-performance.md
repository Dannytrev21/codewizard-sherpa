# Phase 3 — Vuln remediation: deterministic recipe path: Performance-first design

**Lens:** Performance — throughput, latency, token economy, footprint.
**Designed by:** Performance-first design subagent
**Date:** 2026-05-12

## Lens summary

Phase 3 is the cheapest workflow in the whole roadmap and should stay that way: zero LLM tokens (ADR-0005, ADR-0011 recipe tier), pure deterministic transforms, and three large external costs to amortize aggressively — the CVE feeds, `npm install`/lockfile resolution, and the repo test suite. The design tiers every operation by cost (cache → recipe → install-lockfile-only → install-full → test) and pushes work to the cheapest tier that yields the answer. The hot path for a known-CVE-on-watched-repo is **near-zero compute**: the CVE→fix mapping is a pre-rendered lookup against a content-addressed CVE store, the recipe is a one-line lockfile rewrite via `npm-check-updates` then `npm install --package-lock-only`, validation is fast-path test selection driven by `RepoContext.depgraph` reverse-reachability from the bumped package. Full `npm ci` + full test suite only run inside the final validation gate, in the same `run_in_sandbox` chokepoint Phase 1/2 already use (no fork). OpenRewrite is **not** the default — JVM cold start kills the throughput target — and is deferred to a behind-flag fallback. The first task class is also the one where determinism is most achievable, so we lean into it: everything is cacheable, everything is content-addressed, and the only "live" work is the per-CVE recipe attempt.

## Goals (concrete, measurable)

- **Workflows/hour per worker:** **≥ 60** for a known-CVE-on-cached-repo (cache-hit on RepoContext + CVE store + lockfile-resolve cache). **≥ 12** for a cold CVE with cached RepoContext but cold lockfile resolution. (Single worker, 4 vCPU / 8 GB.)
- **Time-to-PR p50 / p95** (locally produced branch + diff, Phase 3's terminal artifact):
  - Hot path (recipe cache hit, lockfile cache hit, fast-path test subset green): **p50 ≤ 18 s, p95 ≤ 45 s.**
  - Cold lockfile (must run `npm install --package-lock-only`): **p50 ≤ 75 s, p95 ≤ 150 s.**
  - Full-suite validation required (no fast-path subset eligible): **p50 ≤ 4 min, p95 ≤ 9 min** — dominated entirely by the repo's own test suite, which Phase 3 cannot make faster.
- **$/PR:** **$0.00 LLM tokens.** Only attributable cost is local compute + amortized CVE-feed bandwidth. Per-PR amortized cost target: **< $0.01** (mostly `grype db update` bytes + npm registry pulls, both registry-cached locally).
- **Cache hit rate targets:**
  - CVE feed: **≥ 99.5%** of CVE lookups against pre-rendered hot view; refresh budget < 1% of gather wall-clock.
  - Recipe selection (CVE → bump-target): **≥ 95%** hit on the pre-rendered `cve_fix_index` view; cold compute only on first-ever observation of a given CVE.
  - Lockfile resolution (`npm install --package-lock-only`): **≥ 80%** hit on the `(package_lock_hash, target_package@version, registry_mirror_digest)` cache across the portfolio (one repo's resolution often answers another's).
  - Test-selection: opportunistic; not load-bearing for correctness.
- **Per-worker memory ceiling:** **≤ 1.2 GB RSS** steady-state. Phase 3 process itself ≤ 350 MB; subprocess peak (`npm`/test runner) bounded by `rlimit_as` to 900 MB. No JVM unless OpenRewrite fallback is explicitly invoked (then ≤ 2 GB, gated).
- **Tail latency p99 contract:** p99 of any *deterministic* stage (recipe selection, lockfile diff generation, CVE lookup) ≤ 2× p95. Test suite p99 is repo-dominated and is not part of Phase 3's contract — but Phase 3 must surface its own time inside the test invocation separately so a long test isn't blamed on us.

## Architecture

```
                              ┌──────────────────────────────────────────────┐
                              │  Phase 1/2 outputs (already on disk)         │
                              │    .codegenie/context/repo-context.yaml      │
                              │    .codegenie/context/raw/syft_sbom.json     │
                              │    .codegenie/context/raw/grype_cve.json     │
                              │    .codegenie/skills/  (loaded indices)      │
                              │    .codegenie/index/depgraph.json (B5)       │
                              └────────────────────┬─────────────────────────┘
                                                   │ read-only consumers
                                                   ▼
 ┌───────────────────────────────────────────────────────────────────────────────┐
 │                         codegenie remediate <repo>                            │
 │                          (new CLI subcommand)                                 │
 │                                                                               │
 │   ┌────────────┐    ┌──────────────────┐    ┌────────────────────────────┐    │
 │   │ CVE Loader │ →  │ Fix-Plan Builder │ →  │ Recipe Selector            │    │
 │   │ (hot view) │    │ (per-CVE bump    │    │ (recipe registry +         │    │
 │   │            │    │  target)         │    │  applies_to)                │    │
 │   └────────────┘    └──────────────────┘    └──────────────┬─────────────┘    │
 │         ▲                                                  │                  │
 │         │ pre-rendered                                     ▼                  │
 │   ┌─────┴──────────────────────────────────────────┐  ┌──────────────────┐    │
 │   │  CVE Hot Views (content-addressed)             │  │ Recipe Engine    │    │
 │   │  .codegenie/cve/by-cve/<cve-id>.json           │  │ default: NCU+npm │    │
 │   │  .codegenie/cve/by-ecosystem/npm/index.json    │  │ fallback: AST    │    │
 │   │  .codegenie/cve/fix-index.json (CVE→{min,safe})│  │ fallback²:OpenRw │    │
 │   └────────────────────────────────────────────────┘  └────────┬─────────┘    │
 │         ▲                                                       │              │
 │         │ async daemon writes (decoupled from request path)     ▼              │
 │   ┌─────┴────────────────────────┐                  ┌──────────────────────┐  │
 │   │ Feed Ingestor                │                  │ Lockfile Resolver    │  │
 │   │  NVD JSON 2.0 / GHSA / OSV   │                  │ npm install          │  │
 │   │  60-min cron, content-addr   │                  │  --package-lock-only │  │
 │   │  delta-merge (no re-fetch)   │                  │  cached on            │  │
 │   └──────────────────────────────┘                  │  (lock_hash,tgt,reg) │  │
 │                                                     └──────────┬───────────┘  │
 │                                                                ▼              │
 │                                                ┌──────────────────────────┐   │
 │                                                │ Attempt Recorder         │   │
 │                                                │ .codegenie/attempts/     │   │
 │                                                │   <attempt_id>/          │   │
 │                                                │     diff.patch           │   │
 │                                                │     lockfile.diff        │   │
 │                                                │     metadata.json        │   │
 │                                                └──────────┬───────────────┘   │
 │                                                           ▼                   │
 │                                                ┌──────────────────────────┐   │
 │                                                │ Validation Pyramid       │   │
 │                                                │  1. install-clean (ci)   │   │
 │                                                │  2. fast-path tests      │   │
 │                                                │  3. full suite (last)    │   │
 │                                                │  all in run_in_sandbox   │   │
 │                                                └──────────┬───────────────┘   │
 │                                                           ▼                   │
 │                                              ┌──────────────────────────────┐ │
 │                                              │ Branch Writer                │ │
 │                                              │  git branch + commit (local) │ │
 │                                              └──────────────────────────────┘ │
 │                                                                               │
 └───────────────────────────────────────────────────────────────────────────────┘

 ──────────────  out-of-band, daemon-style  ──────────────
 ┌────────────────────────────────────────────────────────┐
 │ Feed Ingestor (runs from cron / `codegenie cve sync`)  │
 │   NVD JSON 2.0:  modified-since window only            │
 │   GHSA:          since=<last_etag>                     │
 │   OSV:           changeset endpoint                    │
 │   Output:                                              │
 │     .codegenie/cve/raw/<source>/<sha256>.json.zst      │
 │     .codegenie/cve/by-cve/<cve-id>.json    (merged)    │
 │     .codegenie/cve/fix-index.json          (rendered)  │
 │   Selective invalidation: only CVEs whose record       │
 │   changed since last run get re-rendered.              │
 └────────────────────────────────────────────────────────┘
```

## Components

### CVE Feed Ingestor (`codegenie cve sync` + cron entry)

- **Purpose:** Keep `.codegenie/cve/` warm at all times. Decouple feed-fetch latency from the request path. This is where Phase 3's biggest performance lever lives: every CVE byte fetched once per portfolio, not once per workflow.
- **Interface:**
  - Inputs: NVD JSON 2.0 (`/rest/json/cves/2.0?lastModStartDate=…`), GHSA GraphQL with `If-None-Match`, OSV `https://api.osv.dev/v1/vulns` and the OSV "changed since" export.
  - Outputs: content-addressed raw blobs under `.codegenie/cve/raw/<source>/<sha256>.json.zst`; merged per-CVE records under `.codegenie/cve/by-cve/<cve-id>.json`; rendered fix-index at `.codegenie/cve/fix-index.json`.
  - Errors: feed timeout / 5xx → keep stale view, increment `staleness_seconds` (B2's honest-confidence pattern); never block the request path.
- **Internal design:**
  - **Refresh cadence: 60-minute cron (configurable).** NVD throttles aggressively; the 2-hour-old data they publish is already lagging upstream CVE reports by ~24 hours. Sub-hourly polling is wasted bandwidth. CVE-feed event triggers (Phase 14) override the cron for hot CVEs.
  - **Delta-only fetch.** NVD `lastModStartDate=<last_run>`; GHSA `If-None-Match` against stored ETag; OSV's incremental changeset. The full corpus is fetched once on first-run; thereafter only deltas. On a steady-state worker this is < 5 MB / hour total.
  - **Content-addressed storage** under `.codegenie/cve/raw/`. SHA-256 of the canonicalized record is the key. Three feeds reporting the same CVE produce one stored blob and three pointers. zstd compression at level 3 (fast decode, ~5× compression on JSON).
  - **Selective invalidation** of the per-CVE merged file: only re-render `by-cve/<cve-id>.json` if at least one of its three source SHAs changed. This is the same pattern Phase 2's grype cache uses (`sbom_content_hash + grype_db_version` invalidation); we reuse the discipline.
  - **Pre-rendered `fix-index.json`** is the hot view: `{cve_id: {ecosystem: "npm", package: "lodash", min_safe: "4.17.21", recommended: "4.17.21", patched_ranges: [">=4.17.21"], cwe: [...]}}`. Built incrementally — only the rows for CVEs whose merged view changed get recomputed.
- **Tradeoffs accepted:**
  - Stale CVE data possible up to 60 min. Acceptable for Phase 3 (single-repo, local, no SLA on freshness). Phase 14's CVE-feed webhook closes this gap.
  - We do **not** dedupe by alias graph (CVE↔GHSA↔OSV alias maps) beyond the obvious primary CVE ID; the few percent of edge cases where OSV-only IDs (`GHSA-*`, `MAL-*`) don't map to a CVE ID are queryable separately. Phase 4+ knowledge-graph build will close this.

### CVE Loader (request path)

- **Purpose:** Translate `RepoContext.cve_scan` (Phase 2 `GrypeCVEProbe` output) into a list of `(cve_id, package, current_version, min_safe_version, recommended_version)` tuples. **Pure cache reads; zero subprocess.**
- **Interface:** input = path to `repo-context.yaml`; output = `list[CveFixTarget]`. Error = missing `fix-index.json` row → fall back to grype's own `fix.versions` field (already in `grype_cve.json`); never block.
- **Internal design:** One mmap of `fix-index.json` (~20–50 MB for the full corpus; loads in < 50 ms). Optional in-memory LRU on the daemon if running long. No DB.
- **Tradeoffs accepted:** Loading the entire fix-index even when we only want a handful of CVEs. The index is small enough (well under 100 MB for the full NVD corpus rendered) that a partial-load codepath is wasted complexity at this phase. If the index ever exceeds 200 MB, switch to a sqlite-backed view — the chokepoint is one function, so the upgrade is local.

### Fix-Plan Builder

- **Purpose:** Given the list of `CveFixTarget`s and `RepoContext.node_manifest` + `RepoContext.depgraph`, decide what to bump to where. Group CVEs that hit the same package into one bump. Detect peer-dep conflicts deterministically.
- **Interface:** input = `(targets, RepoContext)`; output = `FixPlan = {bumps: list[(pkg, from_ver, to_ver, why: [cve_ids])], conflicts: [...], skipped: [(cve_id, reason)]}`.
- **Internal design:**
  - Pure Python; consumes Phase 2's `depgraph` (which already includes resolved versions and peer-dep edges) — no `npm view` calls in the planner. The depgraph is Phase 2's expensive output; Phase 3 cashes that check in.
  - Bump-target = `max(min_safe_version)` across all CVEs targeting this package within the **lockfile-existing semver range** if any exists; otherwise the lowest patched version meeting the existing range; otherwise mark as "range-break" and schedule for major-bump path.
  - Peer-dep conflict detection: walk the depgraph and verify candidate bump satisfies all peer-dep predicates of incoming edges. Pure graph traversal in `networkx` (already in Phase 2's deps).
  - **Confidence is a per-CVE bool, not a free-form judgment.** A bump is `high_confidence` iff: (a) it stays inside the existing semver range, (b) no peer-dep conflict in the depgraph, (c) the bumped package is not on the conventions catalog's "manual review required" list.
- **Tradeoffs accepted:**
  - Transitive vulns where the surface dependency can't accept the patched range get marked `skipped: range_break` and routed to Phase 4 in the future. Phase 3 deliberately handles only the deterministic majority — per ADR-0011 recipe-first, this is the cheap tier and we keep it cheap.
  - We trust Phase 2's depgraph as ground truth. If `IndexHealthProbe` flagged the depgraph as `confidence: low`, the planner halts with an honest error rather than guessing. This is the B2 invariant turned into a control-flow rule.

### Recipe Selector + Recipe Engine

- **Purpose:** Map `(ecosystem, kind=version_bump, pkg, from, to)` to a concrete deterministic transform. Apply it.
- **Interface:** input = `FixPlan`; output = `Attempt = {diff_path, lockfile_diff_path, applied_bumps, branch_name, attempt_id}`.
- **Internal design — pick one default, name the fallbacks:**
  - **Default hot path: `npm-check-updates` + `npm install --package-lock-only`.** This is the chosen default for all `(ecosystem=npm, kind=version_bump_within_range or up_to_minor)` cases. Rationale:
    - **Cold-start cost:** `ncu` is a node CLI; cold-start is ~150–250 ms. `npm install --package-lock-only` is ~1.5–5 s for a typical service. Total per-attempt overhead < 6 s on cold lockfile; < 200 ms on cached lockfile.
    - **OpenRewrite alternative** (`org.openrewrite.npm` recipes) requires a JVM. JVM cold start is **2–5 s minimum** even on a warm-disk machine, and a "modern" recipe run via `rewrite-maven-plugin` or `mod` CLI is closer to 8–15 s before doing useful work. At a 60 workflows/hour/worker target, JVM cold start alone would consume ~5–12 minutes per hour. **OpenRewrite is the wrong default for npm** at our throughput target — its sweet spot is large Java refactors where JVM warmup amortizes over millions of LOC scanned. We will **keep OpenRewrite behind a `--engine=openrewrite` flag** for cases the default cannot handle and warm-up the JVM with `--keep-alive` mode if that flag is invoked across many repos in a batch.
    - **Hand-rolled AST manipulation** (parse `package.json` + `package-lock.json` with stdlib JSON, mutate, write) is even faster than ncu — ~30 ms — but loses ncu's range-resolution logic. We use **stdlib JSON mutation directly for the `package.json` line edit** (it's just `dependencies[pkg] = new_range`) and let `npm install --package-lock-only` compute the lockfile delta. ncu is used only when we need its smart-range logic (e.g., target "minor" vs "patch"); for our Phase 3 use case (bump to known min-safe version) we mostly bypass ncu and write the new range directly.
  - **Effective default for the typical CVE:** stdlib JSON mutation → `npm install --package-lock-only` → diff. No JVM. No ncu shell unless the bump policy is range-fuzzy.
  - **Recipe registry** is a YAML manifest under `src/codegenie/recipes/npm/`: each recipe is `{id, applies_to: {ecosystem, kind}, engine: stdlib_json|ncu|openrewrite, params, declared_inputs}`. Registry is loaded once at startup into an in-memory dict keyed by `(ecosystem, kind)`. Adding a new recipe is a YAML file plus an engine function reference — no edits to the selector.
- **Tradeoffs accepted:**
  - We give up OpenRewrite's recipe ecosystem for the npm case. Acceptable: the npm-specific OpenRewrite recipes (`org.openrewrite.npm.UpgradeDependencyVersion`) are functionally equivalent to what ncu+`npm install --package-lock-only` produces; we lose nothing semantic.
  - Hand-rolled engines must be maintained per ecosystem. Phase 3 is npm-only by scope; Phase 7 (Chainguard distroless) and beyond will add their own engines — that's the extension-by-addition pattern, not a fork.

### Lockfile Resolver (`npm install --package-lock-only`)

- **Purpose:** Generate the new `package-lock.json` for the proposed bump without doing a full `npm install`. This is the most important latency lever in Phase 3 and explicitly answers the prompt's question: **yes, we use `--package-lock-only` on the diff-generation path and reserve full `npm ci` for the validation gate.**
- **Interface:** `(repo_path, package_json_diff) -> (new_lockfile_bytes, lockfile_diff)`. Errors = `npm` exit non-zero with diagnostic captured in attempt metadata.
- **Internal design:**
  - Invoke `npm install --package-lock-only --ignore-scripts --no-audit --no-fund` inside `run_in_sandbox` (`network="scoped"`, allowlist = npm registry host). `--ignore-scripts` is non-negotiable: postinstall scripts during diff-generation would execute supply-chain code without any audit. `--no-audit --no-fund` shaves ~500 ms of unrelated network chatter.
  - **Cache key:** `(blake3(package.json_post_bump), blake3(package-lock.json_pre), npm_registry_mirror_digest, npm_version_digest)`. On hit, replay the cached lockfile bytes — **zero subprocess.** This is a portfolio-wide cache: if service A and service B both bump `lodash@4.17.20 → 4.17.21` with identical surrounding deps, the second hit answers in microseconds.
  - **Persistence:** cache lives under `.codegenie/cache/lockfile/<blake3-of-key>.zst`, alongside Phase 1/2's content-addressed cache. Same GC discipline.
  - **Hot-warm-cold tiering:**
    - Hot (cache hit): replay → ~5 ms.
    - Warm (registry packuments cached by npm in its own `~/.npm`): cold-resolution ~1.5–3 s.
    - Cold (no npm cache, fresh registry pulls): ~5–15 s for a service-sized lockfile.
  - **Registry mirror.** We do **not** spin up a local registry mirror in Phase 3 (rejected per the Phase 2 synthesis pattern: no long-lived services in the POC). We **do** point npm at the shared `~/.npm` cache and pre-warm it for the top-N packages the portfolio's depgraphs collectively reference (renderable from Phase 2's outputs at idle time).
- **Tradeoffs accepted:**
  - `npm install --package-lock-only` still hits the network for packuments on cache miss. We pay that once and amortize via the npm cache. Going fully offline requires the registry-mirror service Phase 14 introduces — out of scope here.
  - We trust `npm`'s lockfile output as a deterministic function of its inputs (within a given npm version). This is true in practice for `npm >= 9` and we pin the npm version in `tools/digests.yaml` so cache keys are valid.

### Validation Pyramid (Trust-Aware gate, Phase-3 shape)

- **Purpose:** Prove the diff installs cleanly and doesn't break tests, **without paying full-suite cost when a fast-path subset proves it.** This is Phase 3's biggest tail-latency lever.
- **Interface:** input = `Attempt`; output = `ValidationResult = {install_clean: bool, fast_subset_status, full_suite_status, signals: {...}}`.
- **Internal design — pyramid order, fail-fast:**
  1. **Lint / static** (≤ 2 s): JSON-validate the new `package.json` and `package-lock.json`. Cheap, catches the malformed-mutation class entirely.
  2. **Install-clean** (`npm ci --ignore-scripts` in `run_in_sandbox`, `network="scoped"`): bound 60 s wall-clock for a typical service. This is the gate the exit criterion cares about most.
  3. **Fast-path tests** (≤ 60 s typical): use `RepoContext.depgraph` to compute the **reverse-reachability set** from the bumped package — every test file that imports a module that (transitively) imports the bumped package. Drive that set through the repo's existing test runner with the repo's `testMatch`/`--testPathPattern`-equivalent flag. **This is the canary.** If the bumped package is `lodash` and 4 of the repo's 1,200 test files touch it transitively, we run those 4 first; if any fail, we never run the other 1,196.
  4. **Full suite** (repo-dominated): only run if the fast-path subset was green **and** the bumped package's transitive blast radius exceeds a threshold (e.g., > 25% of the depgraph). For small-blast bumps, the fast-path is sufficient evidence; for large-blast bumps, run the whole suite.
  - **All three stages run inside `run_in_sandbox`** — the Phase 1 `bwrap`/`sandbox-exec` chokepoint, extended to `network="scoped"` for registry pulls only during step 2. No fork. The microVM upgrade lands at Phase 5 via the same chokepoint; Phase 3 doesn't pay that overhead yet.
  - **Failure attribution.** The validation result records which stage failed and which signal flipped (build error code, failing test names + first 1KB of stdout). Phase 4's RAG will index these; Phase 3 just writes them to disk.
- **Tradeoffs accepted:**
  - Fast-path test selection can miss a test that catches the bump's regression but doesn't statically import the bumped module (dynamic `require`, plugin systems). Mitigation: when `RepoContext.repo_notes` or skills flag the repo as "uses plugin loading at runtime," fast-path is disabled and we go straight to full suite. The B2 honesty principle applies — we degrade loudly rather than silently.
  - Some repos have no tests at all. Phase 3 then writes the diff with `validation.signal: tests_absent` and the gate decision policy is "advance if install-clean only" — the human reviewer at PR time is the final gate (ADR-0009). This is honest.

### Attempt Recorder + Branch Writer

- **Purpose:** Persist every recipe attempt for cache reuse and Phase 4/15 ingestion. Write the working branch + diff that the exit criterion demands.
- **Interface:** input = `(Attempt, ValidationResult)`; output = local git branch `codegenie/cve/<cve-ids-joined>-<short-attempt-id>`; `.codegenie/attempts/<attempt_id>/` populated.
- **Internal design:**
  - **`.codegenie/attempts/<attempt_id>/`:** `diff.patch`, `lockfile.diff`, `metadata.json` (timestamps, recipe id, engine, npm version, signals, cache-hit flags), `validation/install.log`, `validation/fast_subset.json`, `validation/full_suite.json` (only if run).
  - **Attempt ID = BLAKE3** of `(repo_head_sha, fix_plan_canonical_json, recipe_id, engine_version)`. Re-running an identical attempt is a cache hit — the entire pipeline short-circuits if `metadata.json` exists for that attempt_id.
  - **Branch writer** uses `git worktree add` to apply on a detached worktree, runs validation there, then `git fast-import` the resulting tree onto a new branch in the original repo. This avoids contaminating the user's working tree if they're concurrently developing, and lets parallel attempts (multiple CVEs against the same repo) run on multiple worktrees without contention.
- **Tradeoffs accepted:**
  - `git worktree` requires the repo to be a clean clone; if the user has uncommitted changes in their main worktree we run in `.codegenie/scratch/<attempt_id>/` instead and message the user. The branch ends up in the original repo regardless.
  - Attempt artifacts accumulate. GC policy: keep last 50 successful + all failed-and-escalated attempts per repo; older successful attempts collapse to a manifest entry referencing the merged solution.

### Parallelism strategy

- **Per worker, single-process asyncio.** No threads, no multiprocessing. The expensive units (`npm install --package-lock-only`, `npm ci`, the test suite) are all subprocess; asyncio drives them concurrently with bounded `Semaphore`s.
- **Per repo, attempts are sequential.** Two attempts in the same repo would race on `node_modules`. We don't try to be clever.
- **Per portfolio (across repos), attempts are parallel.** Default `--max-concurrent=4` per worker (one per vCPU). Each attempt is fully isolated by `git worktree`. Bounded by the lockfile-resolver semaphore and the test-runner semaphore independently (the test runner is typically the heaviest user of memory and we don't want N concurrent full suites starving each other).
- **Per CVE within a single repo:** **batch into one bump plan, not one attempt per CVE.** Three CVEs against `lodash` produce one `lodash@x.y.z → 4.17.21` bump, one lockfile resolve, one validation run. This is a 3× cost saving on the common multi-CVE-same-package case and is purely a planner-level decision (Fix-Plan Builder groups by package).
- **ADR-0014 retries.** Three-retry default applies per attempt, not per CVE. A failed install-clean step is a retryable failure with a typed error reason; the retry budget caps the time spent on a single fix-plan at `3 × p95 ≈ 30 min` for a worst-case full-suite plan. The retry counter lives in `metadata.json`. We don't yet have the LangGraph machinery to back this with state-machine retries — Phase 6 lands that — so Phase 3 implements retry inside the imperative coordinator with the same cap.

## Data flow

End-to-end run for `codegenie remediate ./services/auth-service`:

1. **t=0 ms:** CLI loads `repo-context.yaml` + `grype_cve.json` (mmap, ~50 ms total).
2. **t=50 ms:** CVE Loader looks up each `cve_id` against `fix-index.json` (mmap, < 1 ms per lookup).
3. **t=80 ms:** Fix-Plan Builder groups by package, computes bump targets, walks depgraph for peer-dep conflicts (~20–80 ms; pure Python on Phase 2's `depgraph.json`).
4. **t=150 ms:** Recipe Selector picks engine = `stdlib_json` for the typical case. Mutates `package.json` in-memory.
5. **t=170 ms:** Lockfile Resolver computes cache key. **On hit:** replay cached lockfile bytes (≈ 5 ms). **On miss:** spawn `npm install --package-lock-only --ignore-scripts --no-audit --no-fund` inside sandbox; 1.5–5 s warm, 5–15 s cold. Write cache.
6. **t ~ 200 ms (hot) / 2–6 s (warm) / 6–16 s (cold):** Attempt Recorder writes the diff + metadata. Attempt ID computed.
7. **Validation pyramid:**
   - Lint/static (≤ 2 s).
   - `npm ci` in sandbox (~5–30 s typical; can be skipped if a recent install-clean cache for the same lockfile exists).
   - Fast-path tests: ~5–60 s depending on subset size.
   - Full suite (conditional): repo-dominated, 30 s–10 min.
8. **t = end:** Branch Writer creates `codegenie/cve/<cve-ids>-<attempt_short>` in the user's repo via `git worktree`-staged tree. Attempt artifacts under `.codegenie/attempts/<attempt_id>/`. Exit code 0 if `install_clean && (fast_subset_green || full_suite_green)`.

**Cache-hit waterfall on the hot path:**

| Step | Hot path latency | Driver |
|---|---|---|
| Context + grype load | 50 ms | mmap |
| CVE lookup | 1 ms × N | mmap dict |
| Fix-plan | 30 ms | networkx |
| Recipe select | 0 ms | dict lookup |
| Stdlib JSON mutate | 5 ms | in-memory |
| Lockfile resolve | 5 ms (cache hit) | replay bytes |
| Attempt write | 10 ms | filesystem |
| Lint/static | 1.5 s | jsonschema |
| Install-clean (cache hit) | 0 ms | cached attestation |
| Fast-path tests | 5–60 s | repo test runner |
| Branch write | 200 ms | git worktree |

Hot-path total without test execution: **~2 s.** With a 30-s fast-path test subset: **~32 s.**

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| CVE feed unavailable on cron tick | Feed Ingestor exit code | Keep prior `fix-index.json`; B2-style `staleness_seconds` recorded; request path proceeds against stale data. Never blocks. |
| Stale CVE staleness exceeds 24 h | Feed Ingestor watchdog | Surface `WARN: CVE feed stale 27 h` on every `remediate` invocation. CI canary: `codegenie cve status` exits non-zero. |
| `RepoContext` missing or older than HEAD | CLI startup check | Refuse with `error: stale repo-context.yaml; run codegenie gather first`. No automatic re-gather (out of Phase 3 scope; Phase 14 closes this). |
| `IndexHealthProbe` flagged depgraph `confidence: low` | Fix-Plan Builder reads B2 output | Halt with honest error: `depgraph confidence low; cannot deterministically plan bumps; rerun gather with --force-refresh`. |
| Recipe miss (no recipe applies to this CVE class) | Recipe Selector | Record `skipped: no_recipe`; CVE flows out the door unfixed. Phase 4 picks it up via RAG/LLM. **Not a Phase 3 failure.** |
| Peer-dep conflict | Fix-Plan Builder | Record `skipped: peer_dep_conflict`; emit diagnostic with the conflicting edges. |
| `npm install --package-lock-only` non-zero | Lockfile Resolver | Retry up to 3 times if exit code matches `transient_npm_codes` set (network, ETIMEDOUT, EAI_AGAIN). Otherwise fail fast with the exit code captured. |
| `npm ci` fails | Validation Pyramid step 2 | Fail attempt; ADR-0014 retry budget. After 3, halt and write `.codegenie/attempts/<id>/escalation.json`. |
| Fast-path tests fail | Validation Pyramid step 3 | Fail attempt; same retry budget. |
| Full suite fails after fast-path passed | Validation Pyramid step 4 | Fail attempt; metadata records which suite step failed for Phase 4 RAG ingestion. |
| `npm install` postinstall executes (should be blocked by `--ignore-scripts`) | Sandbox trace + npm config check | Hard CI failure; this is a security invariant breach. |
| Concurrent attempt collides on `node_modules` | Worktree semaphore | Second attempt waits or runs in `.codegenie/scratch/<attempt_id>/`. Never corrupts. |
| Cache poisoning (lockfile cache wrong for an input) | Validation Pyramid catches it via install/test failure | Attempt fails; cache entry invalidated by content-hash mismatch on next hit. We don't aggressively detect poisoning — we let validation be the oracle. |
| Disk full on `.codegenie/cache/` | Cache writer | Cache writes are skipped; the run still completes; warning emitted. GC reaper runs at startup if `df` < 5%. |

## Resource & cost profile

**Per-worker steady-state (4 vCPU / 8 GB):**

| Resource | Idle | Hot-path attempt | Cold lockfile attempt | Full-suite validation |
|---|---|---|---|---|
| RSS (codegenie process) | 150 MB | 250 MB | 350 MB | 350 MB |
| RSS (npm/test subprocess peak) | — | 300 MB | 600 MB | repo-dependent, capped at 900 MB |
| CPU | < 1% | 1–2 cores × few seconds | 1 core × 5–15 s | repo-dependent |
| Network egress | 0 | 0 (registry-cached) | 1–20 MB | 0–5 MB |
| Disk write (cache) | 0 | ~20 KB | ~200 KB lockfile | ~5 MB logs |

**Throughput math:** at p50 hot-path 18 s, single worker = 200 workflows/hour theoretical. Real-world target of 60/hour assumes 30% cold lockfiles and 10% full-suite. **Throughput is dominated by test-suite wall-clock for the cold-suite cases**, which is correctly outside Phase 3's control.

**$/PR accounting** (per 1,000 PRs at portfolio scale):

| Cost source | Per-1000-PR cost | Notes |
|---|---|---|
| LLM tokens | $0.00 | ADR-0011 recipe tier; no LLM. |
| CVE feeds | ~$0.001 | Bandwidth amortized across portfolio; ingestor runs once per worker. |
| npm registry pulls | ~$0.10 | Amortized across portfolio via shared `~/.npm`. |
| Local compute | repo-dependent | Test-suite wall-clock dominates. |
| Sandbox overhead | negligible | `bwrap`/`sandbox-exec` is ~10 ms per invocation. |

The number to remember: **Phase 3's marginal $/PR is approximately the cost of running the repo's own tests**, plus rounding error.

**Storage growth:** `.codegenie/cve/` reaches steady state at ~150 MB on disk (NVD full corpus + zstd). `.codegenie/cache/lockfile/` grows linearly with unique bump combinations; bounded GC keeps it under 2 GB across the portfolio. `.codegenie/attempts/` keeps last-50-per-repo + all-failed = ~50–500 MB typical.

## Test plan

**"Passes its tests" means:**

1. **Unit tests** for every pure module: CVE Loader (against fixture `fix-index.json`), Fix-Plan Builder (against fixture depgraphs with crafted peer-dep conflicts), Recipe Selector (recipe-registry resolution, deterministic ordering), Attempt ID derivation (golden-file test; same inputs → same hash).
2. **Integration tests, fixture-repo style:** a `tests/fixtures/vuln-fix/` directory of small Node.js repos, each with a deliberately vulnerable lockfile (e.g., `lodash@4.17.20`, `minimist@1.2.5`). Each fixture has its own test suite. For each fixture:
   - `codegenie remediate <fixture>` exits 0.
   - The local branch contains the expected lockfile diff (golden-file).
   - `git checkout <branch> && npm ci && npm test` from a fresh clone passes.
   - The exit criterion is verified end-to-end.
3. **Edge-case fixtures** (each its own directory under `tests/fixtures/vuln-fix/edge-cases/`):
   - **peer-dep conflict**: a repo where the patched version breaks a peer dep declared by another package. Expected: `skipped: peer_dep_conflict`; exit 0 with no branch written for that CVE.
   - **transitive CVE pinned to old major at the surface**: expected `skipped: range_break`.
   - **multi-CVE same package**: three CVEs against the same package → one bump, one attempt, three CVE IDs in the metadata.
   - **no tests**: expected `validation.signal: tests_absent`; branch still written; exit 0 with warning.
   - **dynamic require / plugin loader** (flagged in `repo_notes`): expected fast-path disabled, full-suite run.
   - **postinstall hostile package**: a fixture with `postinstall: rm -rf /` (well, harmless `touch` for testing); expected `--ignore-scripts` blocks it, attempt succeeds, sandbox audit confirms no postinstall ran.
4. **Cache correctness tests:** run twice; assert second run hits the cache for lockfile + attempt + validation; assert mutating any input invalidates the right cache layer.
5. **Performance regression canary** (the headline one — runs in CI):
   - `tests/perf/test_hot_path_latency.py` runs `remediate` against a pre-prepared fixture with all caches warm. Asserts **p95 wall-clock ≤ 5 s** (excluding test-suite execution; fixture has a single-test suite that finishes < 1 s). Threshold is a budget — if a future change blows past it, CI fails loud. This is the perf-equivalent of Phase 2's golden-file discipline.
   - `tests/perf/test_cold_lockfile_latency.py` runs with the lockfile cache cleared. Asserts p95 ≤ 30 s, allowing for warm `~/.npm`. Tagged `slow`, runs on every PR but only blocking on `main`.
   - Memory regression canary: track `resource.getrusage(RUSAGE_CHILDREN)` peak RSS in the same tests; fail if > 1.5 GB.
6. **Determinism canary:** run `remediate` 5 times back-to-back against the same fixture; assert all five produce **byte-identical** lockfile diffs and branch SHAs. If determinism slips, recipe selection or lockfile-resolver caching is broken.
7. **Schema validation:** every `Attempt` and `ValidationResult` serializes through a JSON Schema in `src/codegenie/schema/attempts/`. CI gate.

## Risks (top 3–5)

1. **`npm install --package-lock-only` is not perfectly deterministic across npm versions.** `npm v9 → v10` changed lockfile format twice in 2024–2025. **Mitigation:** pin npm digest in `tools/digests.yaml`, include npm version in lockfile cache key, run a per-PR canary that asserts our pinned npm produces an unchanged lockfile for a fixture. **Residual risk:** when we bump npm, the entire lockfile cache invalidates portfolio-wide — a stampede. Mitigation: warm the cache during the npm-bump PR's CI run.
2. **Fast-path test selection misses regressions.** Static reverse-reachability over `RepoContext.depgraph` cannot see dynamic loads, monkey-patches, or test-only side effects. **Mitigation:** repo-notes flags promote to full-suite; randomized canary in CI runs `--no-fast-path` and compares results to fast-path runs over a fixture portfolio. **Residual risk:** in production this could ship a regression Phase 3 marks green. Phase 5's microVM-based runtime tracing closes the loop; Phase 3 explicitly documents the tradeoff.
3. **CVE feed lag relative to npm advisories.** NVD enrichment lags GHSA by 24–72 h on novel disclosures. Workflows fired on cron may miss fresh CVEs. **Mitigation:** GHSA is also one of our feeds; on first-fetch GHSA usually has the record. Phase 14 webhook closes this further.
4. **Lockfile cache poisoning across npm registry changes.** If a package on the registry is tampered with (rare; npm has integrity checks) or `npm` resolution changes due to registry-side state, two `--package-lock-only` runs with identical inputs can produce different outputs. **Mitigation:** lockfile cache key includes npm-registry mirror digest; we treat registry digest drift as a cache-bust event. We also validate `integrity` fields in the new lockfile match the registry's reported integrity for at least the bumped packages.
5. **`git worktree` contention on busy dev laptops.** Multiple parallel attempts on the same repo path create many worktrees; cleanup is fragile if `codegenie` crashes mid-attempt. **Mitigation:** atexit handler + startup reaper of orphaned `.codegenie/scratch/`. The git worktree pattern is well-trodden but error-handling needs care.

## Acknowledged blind spots

- **Security posture beyond `--ignore-scripts`.** This design assumes Phase 2's `run_in_sandbox` (`bwrap`/`sandbox-exec` with `network="none"` for non-pull steps and scoped network for registry/feed pulls) is adequate. A determined attacker who plants a malicious package matching our bump target could still execute code during `npm ci` regardless of `--ignore-scripts` (e.g., via native gyp builds). The security-first design will likely call for tighter isolation — probably correctly. Performance-first defers to Phase 5/14 microVM here.
- **No deduplication of CVE alias graphs.** GHSA-only IDs and OSV-only `MAL-*` records are second-class citizens in `fix-index.json`. Acceptable for Phase 3 npm scope; will hurt at multi-ecosystem scale.
- **Single-recipe-per-CVE assumption.** Some CVEs have multiple valid fix paths (drop dep, swap dep, bump dep). We pick "bump" universally because it's the lowest-risk deterministic choice. Phase 4 will explore alternatives via RAG.
- **No reviewer-time accounting yet.** The "PR" Phase 3 produces is a local branch + diff; humans-always-merge (ADR-0009) is enforced at Phase 11, not here. Reviewer time, which dominates the *real* cost-per-PR economics, is not in this design's scope and we don't pretend otherwise.
- **Test runner heterogeneity.** We assume `npm test` works; some monorepos route through Nx/Turbo and need workspace-aware invocation. The Recipe Selector reads `RepoContext.test_inventory` (Phase 1 Layer A) for the right command, but we don't have fixtures for every variant yet.
- **Cold-portfolio bootstrap.** On a brand-new install, the lockfile cache is empty across the whole portfolio. The first 100 workflows are paying full cold cost. This is fine for the first hour of operation; documented but not optimized.

## Open questions for the synthesizer

1. **OpenRewrite reservation policy.** Performance defers OpenRewrite behind a flag; best-practices may argue it should be the structural-changes default for the npm Dockerfile-rewrite case in Phase 7. Where does the seam land? My read: stdlib_json/ncu for `npm` ecosystem version bumps; reserve OpenRewrite for Java (Phase TBD) and structural Dockerfile rewrites (Phase 7) where it actually wins. Confirm.
2. **`--ignore-scripts` posture in `npm ci` for the validation gate.** I left `--ignore-scripts` on for *both* `--package-lock-only` (definitely correct) and `npm ci` (debatable — some real services depend on postinstalls for native builds). The security design likely wants this hardline. Performance-wise, leaving it on shaves ~5–30% of `npm ci` time, which is meaningful. The synthesizer should pick.
3. **Validation pyramid completeness for Phase 3 exit criterion.** The roadmap says "passes the repo's own tests." Does "fast-path subset green + skip full suite on small blast radius" satisfy this? Performance says yes (the bumped package's blast radius bounds what tests can possibly catch the regression). Best-practices may argue no (run the whole suite always). Net cost difference is large.
4. **Single CVE vs grouped CVE attempt semantics for the branch.** I batch all CVEs against a single package into one bump on one branch. Should each CVE get its own branch for granular human review? Performance says no (one bump = one PR); humans-always-merge (ADR-0009) framing says it depends on reviewer ergonomics, which Phase 11 will decide.
5. **`fix-index.json` rendering cadence vs request-time computation.** I pre-render the full index. An alternative is to render lazily per-CVE on first miss. For Phase 3 single-repo local POC, lazy might be enough. For the portfolio scale the design is forward-compatible with, pre-render wins. Confirm we're optimizing for the forward shape now (the seams cost nothing to keep open).
6. **Cache key inclusion of npm version: portfolio-wide vs per-worker.** I include npm digest in the lockfile cache key, which means bumping npm invalidates the whole portfolio's lockfile cache. Alternative: key by `(npm_major.minor)` and let patch versions share. Performance says the latter is fine and saves stampedes. Determinism says the former is safer. Pick.
7. **Cross-phase contract: does Phase 3 emit a structured attempt artifact that Phase 4's RAG can ingest as a solved example without rework?** I designed `.codegenie/attempts/<id>/metadata.json` with that in mind. Confirm the schema with the Phase 4 designer when they come online; small additions now beat schema migrations later.
