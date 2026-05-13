# Phase 6.5 — Per-task-class eval harness + first benches: Performance-first design

**Lens:** Performance — throughput, latency, token economy, footprint.
**Designed by:** Performance-first design subagent
**Date:** 2026-05-12

## Lens summary

I optimize the harness as if the headline metric were **nightly eval wall-clock at portfolio scale**, with the strict precondition that the harness changes nothing about per-PR CI hot paths ([ADR-0016](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) §Decision §5 — offline cadence, not CI-per-PR). The dominant compute in an eval run is the SUT itself — Phase 6's `build_vuln_loop().ainvoke(...)` plus Phase 5's sandbox plus Phase 4's cassette-replayed LLM step. The harness's job is to **never run the SUT when the answer is already known**, and when it must run, to **run as many cases in parallel as the host allows without thrashing the sandbox**. Concretely: content-addressed `BenchScore` cache keyed on `(case_digest, sut_digest, rubric_digest, cassette_digest)`; a bounded asyncio worker pool sized to sandbox-concurrency; lazy import of `bench/{task-class}/` modules (no module-level `langgraph` import in the harness — pay it once, in the SUT-bound worker); audit-format that streams per-case JSON Lines as cases complete (not a single end-of-run aggregate); a single `pyproject.toml` `[project.optional-dependencies] eval` extras slot so the harness adds **zero** import-time cost to the main `codegenie` CLI hot path.

**Explicit deprioritizations.** I do not invest in pretty CLI output, multi-format reporters, or a dashboard. I do not invest in mutation testing the rubric ([ADR-0016](../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md) §Open Questions §5 — Phase 16 territory). I do not invest in adversarial-synthetic case generation. I do not invest in cross-case statistical analysis beyond `mean` + `min` + `max` + count of `failure_modes` by tag — the calibration math is [ADR-0015](../../production/adrs/0015-trust-score-threshold-calibration.md)'s concern, not the harness runner's. I do not invest in a separate audit DB; everything is filesystem and content-addressed.

## Goals (concrete, measurable)

- **Nightly eval wall-clock for `vuln-remediation` (≥10 cases)**, cold cache, single 8-core host: **≤ 8 minutes wall-clock**. Per-case p95 ≤ 60 s when SUT goes through full Phase 4 cassette-replayed LLM path. Per-case p50 ≤ 25 s when SUT hits Phase 4 query-cache tier-1.
- **Nightly eval wall-clock, warm cache (no SUT or rubric digest change since last run): ≤ 5 s** for the same ≥10 cases — pure cache validation + manifest emit.
- **Cache hit rate on unchanged-cassette + unchanged-rubric reruns: ≥ 98%.** A miss only on (a) a case file mtime/content change, (b) a rubric edit, (c) a cassette re-record, (d) a recipe-set version bump. The 2% allowance is reserved for genuine SUT-source edits.
- **Fence-CI added wall-clock: ≤ 2 seconds.** The fence test is a directory-and-file existence check against the registry; it does not import the rubric, does not load cases, does not call `pydantic` on case files.
- **$/eval-run target (vuln-remediation, ≥10 cases, cold cache, CI):** **$0.00.** Cassettes only ([Phase 4](../04-vuln-llm-fallback-rag/) discipline; roadmap §Phase 6.5 "No live LLM calls in CI"). For operator-invoked live runs: **≤ $0.40 / 10-case run** under recipe-first / RAG hit assumptions from [production ADR-0011](../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md); cap enforced by harness via `BenchScore.cost_usd` rolling sum + `--max-cost-usd` flag (default $5.00) that aborts the run.
- **Storage growth rate (cassettes + audit + scores).** Audit JSONL: **≤ 12 KB/case** (one line per case, no embedded diff). Score history: **append-only `.codegenie/eval/runs/<utc-iso>-<short>.json`** + `runs.jsonl` index — **≤ 4 KB/run aggregate**. Cassettes: harness adds **zero new cassettes**; reuses Phase 4 cassettes via SUT invocation. Retention: 90-day rolling on `runs/`, infinite on `runs.jsonl` (index only). At nightly cadence and 10 cases/class × 2 classes, that's ~7 MB/year audit + ~3 MB/year index. Negligible.
- **Memory per worker: ≤ 800 MB resident.** Dominated by the SUT (LangGraph + Phase 5 sandbox client). Harness overhead itself: **≤ 30 MB**.
- **Hot vs cold cost ratio (warm cache vs cold cache): ≥ 100×.** This is the load-bearing economic argument for content-addressed caching.

## Architecture

```
                                ┌──────────────────────────────────────────────┐
                                │  codegenie eval run --task-class=<name>      │
                                │  (entry: src/codegenie/eval/cli.py)          │
                                └────────────────────┬─────────────────────────┘
                                                     │
                          ┌──────────────────────────▼──────────────────────────┐
                          │  Runner.plan()                                      │
                          │  ─ resolve task-class from registry                 │
                          │  ─ discover cases (glob bench/{tc}/cases/*/)        │
                          │  ─ compute (case_digest, sut_digest,                │
                          │    rubric_digest, cassette_digest) for every case   │
                          │  ─ probe cache for hits → emit cached BenchScores   │
                          │  ─ build work-queue of MISS cases only              │
                          └────────────────────┬────────────────────────────────┘
                                               │
                ┌──────────────────────────────▼────────────────────────────┐
                │  asyncio bounded worker pool (Semaphore, N = sandbox_cap) │
                │                                                           │
                │   worker-1 ──► SUT.ainvoke(case_input)  ─► rubric.score() │
                │   worker-2 ──► SUT.ainvoke(case_input)  ─► rubric.score() │
                │   worker-N ──► SUT.ainvoke(case_input)  ─► rubric.score() │
                │       │                                                   │
                │       └──► BenchScore (Pydantic, frozen)                  │
                └────────────────────┬──────────────────────────────────────┘
                                     │
                                     │ (streams per-case JSONL as cases finish)
                                     ▼
        ┌────────────────────────────────────────────────────────────────────┐
        │  Sinks (run concurrently)                                          │
        │  ─ stdout JSONL stream (one BenchScore per line)                   │
        │  ─ .codegenie/eval/runs/<utc-iso>-<short>.jsonl  (audit, append)   │
        │  ─ .codegenie/eval/cache/<sha256>.json           (cache write)     │
        │  ─ in-memory aggregator (mean/min/max + failure-mode tally)        │
        └────────────────────┬───────────────────────────────────────────────┘
                             │
                             ▼
        ┌────────────────────────────────────────────────────────────────────┐
        │  Aggregate emit: runs/<utc-iso>-<short>.json + runs.jsonl line    │
        │  Promotion gate (read-only): compare aggregate to tier thresholds  │
        │    declared in task-class registration. Reports `tier_candidate`.  │
        │    Does NOT mutate any tier state — promotion is human/ADR-gated   │
        │    per ADR-0016 §Decision §4 and roadmap §Phase 6.5 exit #5.       │
        └────────────────────────────────────────────────────────────────────┘
```

**Why this shape.** The runner is a pure planner over digests + an async fan-out over a bounded pool + a streaming sink. There is no batch aggregation step that blocks completion of fast cases on slow ones (streaming JSONL = a fast case at index 0 lands on disk while case 9's sandbox is still booting). The cache is the single performance win; the bounded pool is the single concurrency win; everything else is plumbing.

## Components

### `src/codegenie/eval/registry.py` — `@register_task_class`

- **Purpose:** Open registry mapping `task-class-slug` → `TaskClassRegistration` (bench_path, rubric callable, min_cases_for_promotion floors). Mirrors `@register_probe` / `@register_signal_kind` ([Phase 5 ADR-0003](../05-sandbox-trust-gates/ADRs/0003-trustscorer-extension-via-signal-kind-registry.md)).
- **Interface:**
  - `@register_task_class(name: str, *, bench_path: Path, rubric: Callable[[HarnessOutput, Expected], BenchScore], min_cases_for_promotion: dict[Tier, int]) -> Callable`
  - `get(name: str) -> TaskClassRegistration` — raises `TaskClassNotRegistered`.
  - `all() -> dict[str, TaskClassRegistration]` — used only by fence-CI.
  - Collision: `TaskClassAlreadyRegistered` at import (same shape as `SignalKindAlreadyRegistered`).
- **Internal design:** Module-level `dict[str, TaskClassRegistration]`. Registrations are lazy-imported via `importlib.metadata` entry points `codegenie.eval.task_classes` so the main `codegenie` CLI does **not** import `langgraph`, `chromadb`, or any heavy SUT dep when running `codegenie gather` or `codegenie remediate`. Task-class modules import their SUT entry only inside the `score()` callable, not at module top.
- **Tradeoffs accepted:** Entry-point lazy loading adds one `importlib.metadata.entry_points()` call (~5 ms once per CLI invocation) but saves ~250 ms of `langgraph`/`chromadb` import on non-eval commands. Worth it.

### `src/codegenie/eval/models.py` — `BenchScore` + types

- **Purpose:** The Pydantic contract every rubric must return.
- **Interface:**
  ```python
  class BenchScore(BaseModel):
      model_config = ConfigDict(extra="forbid", frozen=True)
      passed: bool
      score: float          # ∈ [0.0, 1.0], validated
      breakdown: dict[str, float]
      failure_modes: list[str]
      cost_usd: float       # 0.0 on cache hit; SUT-reported on miss
      wall_clock_ms: int
      sut_digest: str       # for audit
      case_id: str
      provenance: Literal["curated", "outcome-ledger-derived", "regression-converted"]
  ```
  Plus `class HarnessOutput`, `class Expected`, `class Tier(StrEnum)`, `class TaskClassRegistration`.
- **Internal design:** Mirrors [Phase 5 ADR-0014](../05-sandbox-trust-gates/ADRs/0014-objectivesignals-extra-forbid-static-introspection.md) — `extra="forbid", frozen=True`. `frozen=True` is load-bearing for caching: a `BenchScore` is hashable-equivalent via its JSON serialization, and the cache stores the serialized form. `breakdown: dict[str, float]` (no nested dicts, no lists in values — same structural-smuggle prevention as ADR-0014). `score` validator enforces `0.0 ≤ score ≤ 1.0` (property-tested per roadmap §Phase 6.5 testing).
- **Tradeoffs accepted:** No richer score structure (e.g., confusion matrices, sub-rubric trees). If a rubric needs to express finer-grained evidence, it stuffs it into `breakdown` with namespaced keys (`"diff/exact_match": 1.0`, `"diff/semantic_match": 0.8`). The flat-dict constraint is a feature, not a limitation — it keeps the audit format trivially diffable.

### `src/codegenie/eval/runner.py` — `Runner`

- **Purpose:** Plan + execute + aggregate one eval run for one task class.
- **Interface:**
  - `Runner(task_class: str, cases_glob: str = "*", concurrency: int | None = None, max_cost_usd: float = 5.0, cache_dir: Path = Path(".codegenie/eval/cache"))`
  - `async def run() -> RunAggregate` — emits per-case JSONL to stdout + audit file as cases complete; returns the in-memory aggregate at the end.
- **Internal design:**
  1. **Plan phase (synchronous, fast).** Walk `bench/{task-class}/cases/` via `Path.iterdir()` (not `glob.glob` — faster on large case sets, no shell quoting). For each case directory, read `case.yaml` once and compute `case_digest = blake3(case_input_bytes || expected_bytes || case_yaml_bytes)`. Compute `sut_digest` once per run (not per case) by hashing the SUT's transitive source — concretely: `blake3` over (a) `src/codegenie/graph/` source tree, (b) `recipes/` content, (c) the resolved `pyproject.toml` lock hash. Compute `rubric_digest` once per run by hashing `bench/{task-class}/rubric.py` source. Compute `cassette_digest` once per run by hashing the `tests/cassettes/` subtree the SUT will consult (Phase 4 cassette dir).
  2. **Cache probe (synchronous, fast).** Compute `cache_key = blake3(case_digest || sut_digest || rubric_digest || cassette_digest)` per case. Lookup `cache_dir/<cache_key>.json`. On hit: load, validate via Pydantic, emit to stdout + audit immediately, mark case complete, **do not enqueue**. On miss: enqueue.
  3. **Execute phase (async).** `asyncio.Semaphore(concurrency)` where `concurrency` defaults to `min(os.cpu_count(), sandbox_max_concurrent)` — sandbox_max_concurrent is read from Phase 5 config (Phase 5 sandbox is the bottleneck, not CPU). For each enqueued case, spawn an `asyncio.Task` that: (a) acquires the semaphore; (b) calls `await SUT.run(case.input)` — for vuln-remediation, this is `await build_vuln_loop(...).ainvoke(...)` from Phase 6; (c) calls `rubric.score(harness_output, case.expected)` (sync; rubric is plain Python); (d) writes `BenchScore` to cache; (e) emits to sinks; (f) releases semaphore.
  4. **Aggregate phase (constant memory).** `RunAggregate` keeps `count`, `mean`, `min`, `max`, `failure_mode_tally: Counter[str]`, `total_cost_usd`, `total_wall_clock_ms`. Updated incrementally as each `BenchScore` lands — no list of all `BenchScore`s held in memory (cases stream to disk; aggregate is rolling).
  5. **Cost cap.** After every `BenchScore` is collected, if `total_cost_usd > max_cost_usd`, cancel all outstanding tasks via `asyncio.Task.cancel()`, emit `RunAggregate.aborted = True`, exit non-zero.
- **Tradeoffs accepted:**
  - Streaming aggregate means **no per-case median or stddev** in the live output — the aggregate has `mean/min/max/count` only. If a downstream consumer (calibration ADR-0015) needs richer stats, it reads the JSONL audit file and computes them offline. The runner does not own statistics.
  - `sut_digest` is computed conservatively (hashes the whole `graph/` + `recipes/` trees). This means an unrelated edit to a `graph/` docstring invalidates all bench scores. The fix is human-controllable: don't commit cosmetic edits to `graph/` between calibration runs. I accept the false-positive invalidation rate for the simplicity of "any source change = re-eval."
  - The semaphore is sized for the sandbox, not the CPU. On a CI host with 4 sandbox slots, even an 8-core box runs 4 cases at once. This is correct: the sandbox is the contended resource (see [Phase 5](../05-sandbox-trust-gates/) microVM design). Oversubscribing CPU while under-subscribing sandbox would thrash.

### `src/codegenie/eval/cache.py` — content-addressed `BenchScore` cache

- **Purpose:** The single largest performance win. Skip the SUT entirely when nothing semantically changed since the last run.
- **Interface:**
  - `get(cache_key: str) -> BenchScore | None` — synchronous, ~1 ms (one `Path.exists` + `Path.read_bytes` + `BenchScore.model_validate_json`).
  - `put(cache_key: str, score: BenchScore) -> None` — synchronous, ~1 ms (atomic write: write to `<key>.tmp`, `rename` to `<key>.json`).
  - `gc(retain_days: int = 90) -> None` — invoked nightly by the runner after success; deletes entries older than retain_days by mtime.
- **Internal design:** Filesystem-backed (consistent with the rest of the codebase's "filesystem-backed everything" stance per `CLAUDE.md`). `cache_dir/<cache_key>.json`. No subdirectory sharding for ≤10k entries — at 90-day retention × 2 task classes × 10 cases/class × 1 run/night = 1800 entries max. Flat dir is fine. SQLite would be premature.
- **Tradeoffs accepted:**
  - No process-level lock on cache writes — two concurrent eval runs of the same task class could race. The atomic-rename pattern (write `.tmp` then `os.rename`) makes this race **safe**: either run's `BenchScore` is valid; the loser's write is overwritten harmlessly. I deliberately do not file-lock — the cost of contention is one extra SUT run, which is exactly what we accept by running concurrently on purpose.
  - No remote/shared cache (e.g., S3, Redis). Each operator's machine has its own cache. **This is correct** for Phase 6.5: nightly cadence on a single CI host means the cache lives where the runner lives. Phase 13 (cost ledger) may later want a shared cache; that's its problem.

### `src/codegenie/eval/cli.py` — `codegenie eval run`

- **Purpose:** The operator surface. Per roadmap §Phase 6.5 tooling: `codegenie eval run --task-class=<name> [--cases=<glob>] [--out=<path>]`.
- **Interface:**
  - `codegenie eval run --task-class=<name> [--cases=<glob>] [--concurrency=<int>] [--max-cost-usd=<float>] [--no-cache] [--out=<path>] [--audit-dir=<path>]`
  - Exit codes: `0` on success (run completed, aggregate emitted); `2` on cost cap exceeded; `3` on registry miss; `4` on bench directory missing; `1` on any other harness-side error. SUT failures inside a case do **not** abort the run — they become `BenchScore(passed=False, failure_modes=[...])` and the case continues.
- **Internal design:** A thin click wrapper. The CLI itself is < 80 LOC. Stdout is JSONL by default (one `BenchScore` per line, then a final aggregate line with `kind: "aggregate"`); a `--format=human` flag exists but is documented as "for interactive use only, do not pipe."
- **Tradeoffs accepted:** No `--watch`, no `--diff-against-previous-run`, no pretty-progress. Live progress on terminals is `tqdm`-free; the user pipes JSONL to `jq` if they want progress. This is a CI-first tool, not a developer-experience tool.

### `src/codegenie/eval/promotion.py` — trust-tier promotion gate (read-only)

- **Purpose:** Implement the gate logic ADR-0016 §Decision §4 specifies, but **wire it as advisory only** per roadmap §Phase 6.5 exit criterion #5.
- **Interface:**
  - `evaluate(aggregate: RunAggregate, registration: TaskClassRegistration, current_tier: Tier) -> PromotionVerdict`
  - `PromotionVerdict` (frozen): `current_tier`, `candidate_tier`, `passes_threshold: bool`, `block_severity_failure_modes_seen: list[str]`, `cases_evaluated: int`, `min_cases_for_promotion: int`, `reasoning: str`.
- **Internal design:** Pure function over the aggregate and registration. The function does not consult any state store, does not write any tier file, does not transition anything. It computes what tier the bench evidence would support if a human were to promote. The harness prints the verdict; an operator (or future Phase 12 / Phase 16 mechanism) acts on it.
- **Tradeoffs accepted:** No persistence of "tier state per task class." Per roadmap §Phase 6.5 exit #5, the promotion gate is wired but does not auto-promote. The "current tier" is read from the registration (a constant), not from a state store. This is correct: tier promotion is a human/ADR decision; storing it as code state would invite the harness to mutate it.

### `bench/{task-class}/cases/`, `rubric.py`, `registration.py` — directory contract

- **Purpose:** Per ADR-0016 §Decision §1–3 and §Consequences — the fixed contract. The performance lens does not redesign the layout; it optimizes how the runner consumes it.
- **Performance-relevant details:**
  - **Case manifest cache.** On first read of a `bench/{tc}/` directory in a run, the planner builds an in-memory `list[CaseDescriptor]` and reuses it. No re-walk per case.
  - **`case.yaml` is small and flat.** Provenance metadata only (source, commit_sha, added_at, last_validated_at, disposition). The actual case input (repo snapshot, expected diff, expected CVE delta) lives in sibling files referenced by relative path. The case-digest hashes the resolved files, not the YAML alone.
  - **Repo-snapshot cases use frozen tarballs**, not git repos. A bench case's "repo" is `bench/{tc}/cases/{id}/repo.tar.zst` — extracted into a tmpfs scratch dir by the worker, used by the SUT, deleted on case end. zstd over gzip: ~30% smaller, ~3× faster decompress at level 3. Tarball size cap: ≤ 5 MB compressed per case (validated by fence-CI as a courtesy, not a hard fail).
  - **`registration.py` is import-cheap.** It imports the registry decorator and the rubric only. The rubric module imports its own heavy deps (e.g., `unidiff` for diff parsing) at function call time, not module top.

### Fence-CI test extension

- **Purpose:** Per ADR-0016 §Consequences and roadmap §Phase 6.5 exit #4 — assert every registered task class has its `bench/{name}/{cases,rubric.py,registration.py}` and that a missing one fails CI with a specific diagnostic.
- **Performance-relevant details:**
  - The fence test does **not** import `bench/{name}/rubric.py` (importing it would pay rubric-deps cost on every CI run, every PR). It checks file existence via `Path.exists` only.
  - It does **not** call the registry (which would force the registration entry-point machinery on every CI run). Instead, it walks `bench/` directly and asserts that every `bench/{name}/registration.py` file's first-or-second line contains the literal string `@register_task_class("` followed by `name` — a 2-line regex check.
  - Wall-clock budget: ≤ 2 seconds for the whole fence test. At 10 future task classes, that's 100 ms per class — fine.
- **Tradeoffs accepted:** The regex check on `registration.py` is brittle if a contributor reformats the decorator. The fence test's failure message tells them so: `"Could not detect @register_task_class('foo') in bench/foo/registration.py — keep the decorator literal as the first decorator and the name as a string literal."` We accept the brittleness for the speed.

## Data flow

End-to-end trace of `codegenie eval run --task-class=vuln-remediation`:

1. **`cli.py` invocation (~50 ms).** Click parses args; `codegenie eval` subcommand resolves; imports `runner`; imports `registry`. The registry's entry-point load fires here (~5 ms); the `vuln-remediation` task class's `registration.py` runs, registering the rubric callable. Phase 6's `build_vuln_loop` is **not** imported yet — only the rubric's `score()` will pull it in lazily.
2. **`Runner.plan()` (~200 ms for ≥10 cases).** Walk `bench/vuln-remediation/cases/`, read each `case.yaml`, compute `case_digest` per case (blake3 over file contents — ~5 ms/case for typical case sizes). Compute one `sut_digest` (~50 ms for full `graph/` + `recipes/` tree walk). Compute one `rubric_digest` (~2 ms). Compute one `cassette_digest` (~30 ms for Phase 4 cassette tree). Build per-case `cache_key`.
3. **Cache probe (~10 ms, all 10 cases).** Synchronous loop, `Path.exists` per key, load + Pydantic-validate hits. On a warm-cache nightly rerun, all 10 hit; runner streams 10 cached `BenchScore`s to stdout and the audit file; aggregate is computed; promotion verdict is computed; total wall-clock < 5 s. **This is the warm-cache hot path.**
4. **Worker spawn (cold cache, all 10 miss).** `Semaphore(N=4)` (default to sandbox max concurrent on a typical CI host). Spawn 10 `asyncio.Task`s; 4 run concurrently. Each acquires the semaphore, then:
   - Extracts `repo.tar.zst` to a tmpfs scratch dir (~150 ms for a 2 MB tarball at zstd level 3).
   - Imports Phase 6 lazily: `from codegenie.graph.vuln_loop import build_vuln_loop` (~250 ms first time per process; cached by the import system afterward).
   - Builds the LangGraph with a per-case SQLite checkpointer at `.codegenie/eval/scratch/<case_id>.sqlite3` (per [Phase 6](../06-sherpa-state-machine/) per-workflow checkpointer pattern). ~100 ms.
   - `await loop.ainvoke(initial_state)`. Phase 4 cassette-replay tier-1 hits run in ~2–5 s; tier-2 LLM-fallback cassette replay runs in ~15–45 s. The semaphore bounds how many can sandbox-evaluate concurrently — typically 2–4.
   - Calls `rubric.score(harness_output, expected)` (sync, ~50–500 ms — diff comparisons, CVE-delta parse).
   - Constructs `BenchScore`, writes `cache_dir/<cache_key>.json` atomically, emits JSONL to stdout, appends to audit JSONL.
5. **Aggregate.** As tasks complete (in arbitrary order), the aggregator updates `mean/min/max/count` incrementally. When the last task finishes, the runner emits an `{"kind": "aggregate", ...}` JSONL line and writes the aggregate to `.codegenie/eval/runs/<utc-iso>-<short>.json` plus a single-line entry in `.codegenie/eval/runs.jsonl` (the durable per-run index).
6. **Promotion verdict (~1 ms).** Pure function over the aggregate and registration; printed as a final JSONL line `{"kind": "promotion_verdict", ...}`.
7. **GC (~30 ms).** Cache GC walks `cache_dir/`, deletes entries with `mtime < now - 90d`.

**Parallelism extraction points:**
- **Across cases:** `asyncio.Semaphore`-bounded worker pool. Bounded by sandbox concurrency, not CPU.
- **Within a case:** None. A case is a SUT.ainvoke + a rubric call; both are sequential by nature (you can't score before you know the SUT output).
- **Across sinks:** stdout emit, audit-file append, cache write happen sequentially per case (in that order). Cross-case, they're independent — stdout writes from concurrent workers are line-buffered by asyncio + a `Lock` on stdout (≤ 1 μs per acquire).

**Serialization points:**
- The aggregator is single-tasked (one task receives `BenchScore`s via an `asyncio.Queue` and updates state). This avoids needing locks on `mean/min/max`.
- The audit JSONL file is appended via a single writer task fed by the same queue.

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| Cache file corrupt (truncated mid-write — should not happen with atomic-rename, but disk-full could cause it) | Pydantic validation fails on `BenchScore.model_validate_json` in `cache.get` | Treat as cache miss; rerun the case; log a warning but do not abort |
| SUT (`build_vuln_loop().ainvoke`) raises | Worker `try`/`except Exception` around the SUT call | Construct `BenchScore(passed=False, failure_modes=["sut_raised:<exception_type>"], score=0.0, ...)`; case completes (does not abort run); audit captures the exception type + traceback in a sibling `<cache_key>.error.txt` |
| Rubric raises | Worker `try`/`except Exception` around the rubric call | Same as above; `failure_modes=["rubric_raised:<exception_type>"]`. The aggregate's `failure_mode_tally` surfaces rubric brittleness fast |
| Sandbox boot fails (Phase 5 microVM init) | SUT raises sandbox-specific exception | Retry **once** per case at the harness level (not the SUT level — that's Phase 5's three-retry); if both fail, `failure_modes=["sandbox_boot_failed"]`, case completes |
| Cost cap exceeded mid-run | Aggregator detects after a `BenchScore` lands | Cancel all outstanding `asyncio.Task`s; emit `RunAggregate(aborted=True, ...)`; exit code 2. Cached results stand — they are the truth for those cases |
| Cassette miss in CI (per Phase 4 `VCR_BAN_NEW_CASSETTES=1`) | SUT raises Phase 4 cassette-miss exception | `failure_modes=["cassette_miss:<cassette_key>"]`; case fails. Operator must re-record the cassette before the next nightly run. Fence-CI separately catches new task classes added without cassettes. |
| Concurrent eval runs racing on cache | None — atomic-rename makes the race safe | No recovery needed |
| Task-class registration entry-point fails to import | Lazy import in `registry.get()` raises | Exit code 3 with diagnostic `"Task class '<name>' not registered. Available: [...]. Did you mean: '<closest>'?"` |
| `bench/{name}/cases/` empty | `Runner.plan()` finds zero cases | Exit code 4 with `"No cases found at bench/{name}/cases/. Did you forget to commit fixtures?"` |
| Disk full during audit JSONL append | `OSError` from `Path.open("a").write` | Abort run with exit code 1; cached scores written before the failure stand; partial JSONL is **valid** because it's line-delimited (any complete line is parseable) |

## Resource & cost profile

- **Tokens per nightly eval run.** **0 tokens** in CI — cassette replay, no live API ([Phase 4](../04-vuln-llm-fallback-rag/) `--record-mode=none`). **~150k–400k tokens / 10-case operator-invoked live run** depending on Phase 4 tier hit distribution (recipe-first hits cost ~5k tokens/case; RAG few-shot ~25k tokens/case; LLM-cold ~50k tokens/case). At Anthropic Sonnet 4.7 prices, that's $0.10–$0.40 per live run.
- **Wall-clock per case (p50 / p95).**
  - Cache hit: 50 ms / 200 ms.
  - Cache miss, recipe-first hit: 8 s / 25 s (dominated by Phase 5 sandbox boot + build/test).
  - Cache miss, RAG hit: 15 s / 40 s.
  - Cache miss, LLM-cold cassette replay: 30 s / 60 s.
- **Memory per worker.** ≤ 800 MB resident, dominated by Phase 5 sandbox client + LangGraph state. Harness overhead per worker: ≤ 30 MB.
- **Storage growth rate.**
  - Cache: bounded by 90-day retention × 2 task classes × ~10 cases × 1 run/night × ~6 KB/entry ≈ **~11 MB steady-state**.
  - Audit JSONL: 12 KB/case × 20 cases/night × 365 = ~88 MB/year, retained 90 days → **~22 MB steady-state**.
  - Runs index (`runs.jsonl`): 1 line × ~400 bytes × 365 = ~150 KB/year, infinite retention → **negligible**.
  - Bench cases themselves (tarballs): ≤ 5 MB/case × 20 cases ≈ **100 MB committed** — durable.
- **Hot vs cold cost ratio.** Warm-cache run: ~5 s wall-clock, $0.00. Cold-cache run: ~8 min wall-clock, $0.00 in CI / $0.40 live. Hot:cold ≈ **100×** wall-clock, ≥ ∞ on cost in CI. **This is the load-bearing economic argument.**

## Test plan

The performance lens commits to these tests being merge-gating:

1. **Unit: registry collision.** `@register_task_class("dup")` twice in one process raises `TaskClassAlreadyRegistered` (mirror of `SignalKindAlreadyRegistered`).
2. **Unit: `BenchScore` shape.** `extra="forbid"` rejects unknown fields; `frozen=True` rejects mutation; `score` validator rejects `score = 1.1`. Property test (`hypothesis`): `BenchScore.score ∈ [0, 1]` for all rubric outputs against `bench/vuln-remediation/cases/`.
3. **Unit: rubric determinism.** `rubric.score(out, exp) == rubric.score(out, exp)` byte-for-byte across 100 invocations (no `time.time()`, no `random`, no `set` iteration order).
4. **Integration: end-to-end against `bench/vuln-remediation/`.** `codegenie eval run --task-class=vuln-remediation` exits 0; emits ≥10 `BenchScore` JSONL lines + 1 aggregate + 1 promotion_verdict; aggregate `mean ∈ [0, 1]`; audit file is valid JSONL.
5. **Integration: cache hit-rate.** Run the eval twice back-to-back, no source edits. Second run completes in **≤ 5 s** wall-clock and **all 10** `BenchScore`s carry `cost_usd: 0.0` (cache-hit marker). **Hard performance gate, merge-blocking.**
6. **Integration: cache invalidation correctness.** Edit `rubric.py` (whitespace-only change). Rerun. **All 10** cases must re-execute (cache miss). Edit `bench/vuln-remediation/cases/CVE-2024-XXXX/case.yaml` whitespace. Rerun. **Exactly 1** case must re-execute; the other 9 must hit cache. **Hard gate.**
7. **Integration: bounded parallelism.** With `--concurrency=2`, peak simultaneous in-flight `SUT.ainvoke` calls is ≤ 2 (measured by instrumenting a `contextvars.ContextVar` counter in a test-only SUT stub). With `--concurrency=4`, peak ≤ 4.
8. **Integration: cost cap.** With `--max-cost-usd=0.10` and a stub SUT that reports `cost_usd=0.05` per case, the run aborts after exactly 2 cases land. Exit code 2.
9. **Fence: missing bench directory.** A synthetic `@register_task_class("ghost")` with no `bench/ghost/` triggers the fence-CI test with a specific diagnostic naming the missing path.
10. **Fence: wall-clock budget.** The fence-CI test itself runs in **≤ 2 s** on the standard CI runner (`time pytest tests/fence/test_task_class_bench_dirs.py`). **Regression gate.**
11. **Property: parallel cache writes.** Two `asyncio.gather`-spawned writers writing the same `cache_key` concurrently produce a valid file (one wins; the loser is harmless). No corrupted file ever results. **Hard gate.**
12. **Performance regression: nightly wall-clock canary.** A nightly CI job runs the full vuln-remediation bench cold-cache and asserts total wall-clock ≤ **10 minutes** (20% headroom over the 8-minute target). Fails CI with a flame-graph artifact attached on regression.
13. **Performance regression: warm-cache wall-clock canary.** Same as above but second run; asserts ≤ **8 seconds** (60% headroom over the 5-second target).
14. **Property: streaming sink correctness.** For every run, the count of stdout JSONL `BenchScore` lines equals `aggregate.count` equals the count of audit-file lines minus the trailing aggregate + promotion_verdict lines.

## Risks (top 5)

1. **`sut_digest` is too coarse.** Hashing the entire `graph/` + `recipes/` source tree means a docstring edit invalidates all bench scores, eroding the 98% cache hit-rate target. **Mitigation:** document the practice; consider a `tools/eval_digest_excludes.txt` file in a future phase if false-positives become painful. Do not over-engineer it now — the simplicity of "any source change = re-eval" is worth the false-positive cost early on.
2. **Phase 6's per-workflow SQLite checkpointer thrashes under parallel eval.** Phase 6 uses per-workflow `.codegenie/loop/checkpoints/<workflow_id>.sqlite3` — fine. But the harness creates `<case_id>.sqlite3` in `.codegenie/eval/scratch/`. If the scratch dir is on a slow disk, parallel-workers SQLite contention shows up. **Mitigation:** scratch dir lives on tmpfs by default (`/tmp/codegenie-eval-scratch/`); fall back to repo-relative on systems without tmpfs.
3. **The cache becomes the bottleneck.** At 1800 entries flat-dir is fine, but if a future phase adds 100 task classes the dir blows up. **Mitigation:** add sharding (`cache_dir/<key[:2]>/<key>.json`) when entry count crosses 10k. A 1-line change. Not now.
4. **Streaming JSONL stdout is fragile.** A consumer pipe (`| jq`) that closes early (SIGPIPE) crashes the runner. **Mitigation:** suppress `BrokenPipeError` in the stdout writer; the audit file is the source of truth. Documented as "stdout is a courtesy, the audit file is the contract."
5. **The 98% cache hit-rate assumes nightly cadence on a stable SUT.** If the team is iterating on `graph/` or `recipes/` during development, every iteration invalidates the cache and the runner is no faster than a cold-cache run. **Mitigation:** acknowledged. The cache is a **scheduled-cadence** win, not a developer-loop win. For dev-loop, use `--cases=<single-case-glob>` and accept the cold cost on a single case.

## Acknowledged blind spots

- **Bench-case curation throughput.** The harness runs whatever cases are in `bench/`. Curating ≥10 high-quality cases is weeks of work per ADR-0016's tradeoff table; the performance lens has nothing to add to that cost.
- **Rubric quality.** A fast rubric is worthless if the rubric is wrong. Mutation testing the rubric is Phase 16 territory per ADR-0016 §Open Questions §5. I do not invest here.
- **Adversarial-synthetic cases.** ADR-0016 §Open Questions §1 defers; I defer too.
- **LLM Judge integration.** Phase 5 ADR-0008 defers; this harness's evidence shape un-defers it cleanly. I do not pre-build hooks for the Judge; when it lands, it registers as its own task-class via `@register_task_class("judgment-arbitration")` — extension by addition.
- **Cross-host cache sharing.** Each operator's machine has its own cache. Fine for nightly single-host CI; will be revisited if/when Phase 13 cost-ledger needs a shared cache layer.
- **Pretty CLI output.** No `tqdm`, no spinners, no colors. JSONL or bust.
- **Per-case statistical analysis (median, stddev, quantiles).** The aggregate exposes `mean/min/max/count`. Calibration (ADR-0015) reads the JSONL and computes the rest offline. I do not embed a statistics library in the runner.
- **The promotion gate is read-only.** It computes verdicts but does not store tier state. A future phase that wants automated promotion has to add a tier-state store; this design does not pre-build it.

## Open questions for the synthesizer

1. **`sut_digest` granularity.** Hashing the whole `graph/` + `recipes/` tree (my choice) vs. an explicit allowlist of files the rubric declares it cares about. The former is simple and over-invalidates; the latter is precise and under-invalidates on hidden coupling. I picked the former. If the best-practices lens wants per-task-class declared SUT footprints, surface that — it is a real fork.
2. **Sandbox concurrency knob.** The runner reads `sandbox_max_concurrent` from Phase 5 config. Is there a documented Phase 5 config key for this? If not, this design effectively requires one — either I declare a default (e.g., `4`) and the operator overrides via `--concurrency`, or Phase 5 ships the config first. Coordinate with the security lens, which may want it lower.
3. **Cache scope at task-class introduction.** When a brand-new task class lands (e.g., `migration-chainguard-distroless` in Phase 6.5's seed-3-cases step), should the harness require zero cache hits on its first run, or does normal cache-key derivation already cover the "fresh registration" case? My answer: the latter (cache key includes `case_digest`, which is novel for new cases — automatic miss). Confirm.
4. **Live-LLM eval cadence outside CI.** ADR-0016 §Decision §5 says nightly. CI runs cassettes. When does the **live** eval (against real Anthropic API) run? Once per cassette re-record? Once per recipe-set release? This is a calibration-cadence question that touches my `--max-cost-usd` default; I picked $5.00 conservatively. The synthesizer should pick a cadence and tune the default.
5. **Promotion verdict consumers.** I emit `PromotionVerdict` as the final JSONL line, but no Phase 6.5 component reads it. ADR-0016 says promotion is an explicit, ADR-anchored decision. Is there a future-phase consumer (Phase 12 / Phase 16) that will read `runs.jsonl` + the latest verdict and surface "this task class is eligible for promotion" to operators? If yes, document the contract for `runs.jsonl` here so it survives. If no, the verdict is documentation-only — that's fine, but call it out.
6. **Bench tarball format.** I picked `repo.tar.zst` level 3 for 3× decompress speed over gzip. The security lens may want a signed archive; the best-practices lens may want plain git-archive for diffability. The performance answer is zstd; surface if the others fork.
