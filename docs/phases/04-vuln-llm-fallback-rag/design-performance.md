# Phase 04 — Vuln remediation: LLM fallback + solved-example RAG: Performance-first design

**Lens:** Performance — throughput, latency, token economy, footprint.
**Designed by:** Performance-first design subagent
**Date:** 2026-05-12

---

## Lens summary

Phase 4 is the first phase where Claude tokens hit the wire. Everything in this design is shaped by one observation: **the LLM call is two-to-four orders of magnitude more expensive (in dollars and wall-clock) than every other component combined**. So the design is built around making sure the LLM is invoked as rarely as possible, and when it is invoked, as cheaply as possible. The decision chain (`recipe → RAG → LLM`) is the headline ADR-0011 commitment, and the performance-first reading of it is: turn the chain into a *cache hierarchy*, where each tier (a) returns in microseconds when it hits, (b) is decided by deterministic signal — never by an LLM — and (c) writes back to the previous tier on success so the next call gets cheaper.

What I optimized for, in priority order: (1) **RAG hit rate** — every RAG hit is a saved $0.05–$0.40 LLM invocation and saves ~6–25 s of wall-clock; (2) **Anthropic prompt-caching hit rate** — when we *must* call the LLM, ≥ 80 % of input tokens should be cached; (3) **time-to-first-diff** — streaming the model output through a structured-output parser so the diff can be validated incrementally; (4) **embedding latency on the hot path** — single-vector embed in ≤ 30 ms p95 via a long-lived `sentence-transformers` process behind a Unix domain socket; (5) **zero network egress in CI** — VCR cassettes content-addressed so even cold CI runs are cache-perfect.

What I explicitly deprioritized: **leaf-agent-SDK portability** (ADR-0020 leaves the choice deferred; I pick Anthropic-direct and accept the rework if Phase 16 swaps SDKs), **vector-store portability** (I pick `chromadb` local persistent client over docker'd `qdrant`; Phase 14 may redo this), **fine-grained retrieval explainability** (the synthesizer can add it), and **adversarial-corpus prompt-injection hardening** at the RAG ingest boundary (the security-first design will own that — I do basic schema neutralization but don't sandbox embedding).

Where this design accepts tension with the ADRs: ADR-0014 says three-retry default per gate, but **inside Phase 4 the LLM leaf retries against the planner's gates with retry = 1 by default** and *defers the two additional retries to Phase 5*, because retry-2 and retry-3 are 95 % of the cost variance per [ADR-0024](../../production/adrs/0024-cost-observability-end-to-end.md) and Phase 4 has no gate machinery yet to widen on retry. This is explicit, not silent — the orchestrator wraps with retry = 1, Phase 5 raises to 3. Surfaced for the synthesizer.

---

## Goals (concrete, measurable)

All figures are M-series Mac / 4-vCPU Linux runner; Node fixture portfolio (~10 fixtures); a vector store of 100 solved examples (seeded by replaying Phase 3 successful runs through a one-shot ingestion command).

| Metric | Target | Rationale |
|---|---|---|
| **Workflows/hour (single worker, RAG-hot path)** | ≥ 120 | RAG hits return in < 250 ms; the dominant cost is the still-required validation rerun (`npm ci` + `npm test`) inherited from Phase 3, not the planner. |
| **Workflows/hour (LLM-cold path)** | ≥ 20 | Cold LLM is the floor: one Sonnet 4.7 call at p95 ≈ 14 s + Phase 3 install/test. |
| **Time-to-PR p95 — RAG path** | ≤ 95 s | Inherits Phase 3's p95 ≤ 90 s with ~5 s of selection-chain overhead. |
| **Time-to-PR p95 — LLM path** | ≤ 180 s | +60–90 s for the LLM call + recipe-application + validate. |
| **Selector-chain decision latency** (recipe-miss → RAG decision OR LLM decision) | p50 ≤ 80 ms / p95 ≤ 250 ms | Embedding + vector search; no LLM. |
| **$/PR — RAG path** | $0 | No LLM call, by construction. |
| **$/PR — LLM path (cold)** | ≤ $0.08 per PR with Sonnet 4.7 + prompt caching at ≥ 80 % | Single leaf invocation, ~25k input tokens of which ≥ 20k cached; ~2k output. |
| **$/PR — LLM path (warm cache hit, same advisory back-to-back)** | ≤ $0.012 | Anthropic 5-min ephemeral cache TTL refresh. |
| **RAG hit rate (after seeding ≥ 50 examples)** | ≥ 55 % | Above this, the compounding-savings story is real. |
| **Prompt-cache hit rate (when LLM invoked)** | ≥ 80 % | System prompt + skills manifest + recipe-failure context are stable across one workflow's retries and across portfolio peers. |
| **Per-worker steady-state memory ceiling** | ≤ 900 MB Python RSS (gather + planner) + ≤ 600 MB shared embed worker + ≤ 200 MB chromadb mmap = **≤ 1.7 GB** total | Lets a 16 GB worker host ~8 parallel workflows. |
| **Cold-start embed-worker boot** | ≤ 2.5 s | Lazy-loaded model on first `gather`; persisted in worker process thereafter. |
| **VCR cassette hit rate in CI** | 100 % | Network is *banned* from CI; missing cassette = test fails loud. |
| **Token-budget overrun rate** | 0 | The `--max-tokens` per-leaf cap fires before the LLM completion is committed. |

---

## Architecture

```
                              codegenie remediate <repo> --cve <id>
                                              │
                                              ▼
                              ┌────────────────────────────┐
                              │   Phase 3 coordinator       │
                              │   (Stage 1–4 unchanged)     │
                              └────────────┬───────────────┘
                                           │
                            Phase 3's selector.select(...)
                                           │
                                           ▼
                              ┌────────────────────────────┐
                              │  RecipeSelection            │
                              │   reason ∈ {matched,        │
                              │   catalog_miss, range_break │
                              │   peer_dep_conflict, ...}   │
                              └────────────┬───────────────┘
                                           │
                                  ┌────────┴────────┐
                                  │                 │
                            matched              not matched
                                  │                 │
                                  ▼                 ▼
                          Phase 3 transform   ┌─────────────────────────────────┐
                          (unchanged)          │  Phase 4 PLANNER                │
                                               │   (no LLM call decides routing) │
                                               │  ┌───────────────────────────┐  │
                                               │  │ tier1: query-key cache    │  │
                                               │  │   hit → return Plan       │  │  ← exact-replay
                                               │  └─────────┬─────────────────┘  │
                                               │            │ miss                │
                                               │            ▼                     │
                                               │  ┌───────────────────────────┐  │
                                               │  │ tier2: embed + RAG search │  │
                                               │  │   chromadb persistent     │  │
                                               │  │   in-proc mmap            │  │
                                               │  │   top-k=8 → rerank        │  │
                                               │  │   score ≥ τ_hit → return  │  │
                                               │  │     RagPlan (no LLM)      │  │
                                               │  │   score ≥ τ_few  → carry  │  │
                                               │  │     as few-shot to tier3  │  │
                                               │  └─────────┬─────────────────┘  │
                                               │            │ miss/below-τ_hit   │
                                               │            ▼                     │
                                               │  ┌───────────────────────────┐  │
                                               │  │ tier3: leaf LLM call      │  │
                                               │  │   Anthropic Sonnet 4.7    │  │
                                               │  │   prompt-cache breakpoints│  │
                                               │  │   streaming SSE → parser  │  │
                                               │  │   max_tokens cap          │  │
                                               │  │   structured-output       │  │
                                               │  │     (Plan JSON schema)    │  │
                                               │  └─────────┬─────────────────┘  │
                                               │            │                    │
                                               └────────────┼────────────────────┘
                                                            │
                                                            ▼
                                               ┌─────────────────────────────────┐
                                               │  Plan → Phase 3 transform path  │
                                               │  (RecipeEngine.apply if recipe; │
                                               │   ManualPatchEngine if LLM      │
                                               │   produced a hand patch)        │
                                               └────────────┬────────────────────┘
                                                            │
                                                            ▼
                                               ┌─────────────────────────────────┐
                                               │  Validation (Phase 3 unchanged) │
                                               │  install + test + build + trust │
                                               └────────────┬────────────────────┘
                                                            │ success
                                                            ▼
                                               ┌─────────────────────────────────┐
                                               │  ASYNC FIRE-AND-FORGET:         │
                                               │   solved_example_recorder       │
                                               │     · compute embedding         │
                                               │     · upsert chromadb           │
                                               │     · write query-key cache     │
                                               │   This happens OFF the critical │
                                               │   path. Worker exits before     │
                                               │   write completes.              │
                                               └─────────────────────────────────┘

  Sidecar processes (single per host, shared across workers):
  ┌──────────────────────────┐    ┌──────────────────────────┐
  │ embed_worker (asyncio    │    │  chromadb persistent     │
  │   IPC over UDS)           │    │  client (in-proc mmap;   │
  │  · sentence-transformers │    │   no HTTP)               │
  │  · all-MiniLM-L6-v2      │    │  · SQLite + parquet      │
  │  · 384-dim, lazy-loaded  │    │  · ~200 MB at 100 ex.    │
  │                          │    │  · WAL mode              │
  └──────────────────────────┘    └──────────────────────────┘

  Cache layout (added under .codegenie/):
  .codegenie/
    cache/
      lockfile/                    ← Phase 3 (unchanged)
      planner/
        query_key/<sha256>.json    ← tier-1 exact-replay cache
        embeddings/<sha256>.f16    ← float16 embeddings, mmap-readable
        llm_responses/<sha256>.json.zst  ← raw API responses, zstd
    rag/
      chroma/                       ← chromadb persistent dir
        chroma.sqlite3
        <collection>.parquet
      examples/                     ← canonical solved-example bundles
        <example-id>.yaml
        <example-id>/diff.patch
        <example-id>/skill.yaml
    audit/                          ← Phase 2 chain (Phase 4 appends)
```

---

## Components

### 1. `Planner` (the chain)

- **Purpose:** Given a `RecipeSelection` from Phase 3 indicating no recipe matched (or matched with low confidence), produce a `Plan` that the Phase 3 transform pipeline can execute. Three tiers, in order, with deterministic short-circuit between them.
- **Interface:**
  ```python
  class Planner:
      def plan(
          self,
          advisory: Advisory,
          repo_ctx: RepoContextView,
          recipe_selection: RecipeSelection,
          run_id: str,
      ) -> PlanResult
  ```
  `PlanResult` carries `(plan: Plan, source: Literal["query_cache","rag_exact","rag_fewshot_llm","llm_cold"], cost_ms: dict[str,int], cost_tokens: dict[str,int], confidence_signals: dict[str,Any])`.
- **Internal design (performance reasoning):**
  - **No LLM call decides anything in the chain.** Every transition is decided by an objective scalar: query-key sha256 match (binary), top-1 similarity score vs `τ_hit`, top-k similarity vs `τ_few`. This honors ADR-0008 *and* ADR-0011 *and* removes a per-workflow LLM call that some designs would add as a "router."
  - **Tier 1 — query-key exact replay cache.** The "query key" is a content-addressed hash over `(advisory.canonical_id, advisory.fixed_versions_canonical, repo_ctx.lockfile_blake3, repo_ctx.engines.node_major, recipe_selection.reason, recipe_catalog_blake3)`. If we've planned for this exact tuple before and that plan validated cleanly, replay the plan. **This is the single biggest win** — a portfolio of 50 services on the same `lodash` CVE produces one plan and 49 replays. Replay cost: ~3 ms (sha256 + mmap'd JSON read).
  - **Tier 2 — RAG (in-process chromadb).** The vector store is read via `chromadb.PersistentClient` with `is_persistent=True`, **in the same process as the planner**. No HTTP, no docker, no IPC. Mmap'd parquet under WAL mode. Single similarity call returns in 5–30 ms for 100 examples; scales to ~1k before we need a real vector DB. Top-k = 8 with cosine; rerank by a cheap **lexical overlay** (BM25 over advisory text + recipe-failure error string), which is free and helps the false-positive rate on near-duplicate CVE titles.
  - **Tier 3 — leaf LLM, with caching as a first-class concern.** Anthropic SDK direct (per ADR-0020 default), Sonnet 4.7. The leaf is the *only* component in Phase 4 that imports `anthropic`.
- **Tradeoffs accepted:**
  - Skipping the LLM-router (some designs introduce one to "choose the path") saves $0.01–$0.03 per workflow and 1.5 s p95. The cost is: the *thresholds* `τ_hit` and `τ_few` are tunable knobs that need calibration. I ship defaults: `τ_hit = 0.86`, `τ_few = 0.72` cosine. Calibration plan in test section.
  - Synchronous tiers within one process (no async between tiers): simpler, faster, but means a tier-1 miss serializes into the tier-2 call. This is fine because tier-2 is fast. **Inside tier 3** we go full async / streaming (see §3).

### 2. `EmbedWorker` (sidecar)

- **Purpose:** Compute a single 384-d float32 embedding for any text in ≤ 30 ms p95 with a < 600 MB resident footprint.
- **Interface:** `embed(text: str) -> np.ndarray[384, float32]`. Wire format: UDS (`.codegenie/run/embed.sock`), msgpack frames. **Or** in-proc import if `CODEGENIE_EMBED_INPROC=1` (single-worker dev mode).
- **Internal design:**
  - **One process per host, shared across workers.** This is the load-bearing performance call. `sentence-transformers` cold-start with `all-MiniLM-L6-v2` is ~2 s; loading a model per worker on every workflow is unaffordable. The worker is started lazily by the first `remediate` invocation and reused across all subsequent invocations until idle-shutdown (default: 30 min). A `tools/embed_worker.service` is provided for operators who want a long-running daemon.
  - **Model: `sentence-transformers/all-MiniLM-L6-v2`.** 384-d, ~80 MB on disk, CPU-fast. Better-quality models (`bge-base-en`, 768-d, ~440 MB) are gated behind `--embed-model` flag — measured RAG hit-rate gain has to clear 10 % to justify the memory cost.
  - **Embedding cache.** Every embedding written to `.codegenie/cache/planner/embeddings/<sha256(text)>.f16` (float16 on disk to halve I/O; recast on read). Lifetime: indefinite, GC'd by LRU at 1 GB.
  - **Voyage remote embeddings (`voyage-3`, 1024-d).** Supported behind `--embed=voyage`. Quality higher; latency dominated by HTTPS RTT (~100–250 ms); cost ~$0.02 / 1 M tokens. **Disabled by default** in v0.4.0 because the local model wins on latency, and Phase 13 is where we own the per-vendor cost decision.
- **Tradeoffs accepted:**
  - Embedding *quality* is the lever; the model swap is one config line so the synthesizer can rebalance. But the architecture commits to *one* embedding model per chromadb collection — switching models requires re-ingesting examples.
  - The UDS sidecar adds an IPC hop (~3 ms) vs. in-process. In return, we don't pay the 2 s cold-start per workflow. Net win past workflow #2 of any session.

### 3. Leaf LLM caller — `src/codegenie/planner/llm/anthropic_leaf.py`

- **Purpose:** When tiers 1 + 2 miss, generate a `Plan` from `(advisory, repo_ctx subset, skills, recipe-failure trace, optional RAG few-shots)`. **Aggressively cached, structured output, streaming, hard-capped on tokens.**
- **Interface:**
  ```python
  async def invoke_leaf(
      cassette: CassetteKey,
      system_prefix: str,
      few_shots: list[SolvedExampleFewShot],
      query: PlanQuery,
      *,
      max_tokens: int = 2048,
      model: str = "claude-sonnet-4-7",
  ) -> LeafResult
  ```
- **Internal design (performance reasoning):**
  - **Prompt-cache breakpoints.** Per Anthropic SDK 2026 prompt caching:
    1. System block: hard, stable instructions + Skills manifest + Recipe-engine surface. `cache_control={"type":"ephemeral"}`.
    2. Few-shot block: top-k solved examples, sorted by similarity (deterministic order). `cache_control={"type":"ephemeral"}`.
    3. Query block: the advisory + repo-context slice. Not cached.
    Anthropic's 5-min ephemeral TTL works in our favor: rapid-fire workflows in a portfolio scan all hit the cache; a one-off run pays the write-once cost on the first hit.
  - **Streaming + structured output.** `messages.stream` with `response_format` configured for the `Plan` JSON Schema (Anthropic 2026 supports server-side structured output for Sonnet 4.7). The streaming SSE is piped into an **incremental JSON parser** that:
    - Yields the `plan.intent` field as soon as it's complete (used to decide whether to early-cancel if the LLM is heading toward an unsupported transform).
    - Validates each `step` against the `Step` schema as it streams, cancelling the request on the first invalid step (`StreamCancelled`, charged for partial output only).
  - **Hard token cap.** `max_tokens=2048` default; per [ADR-0025](../../production/adrs/0025-per-workflow-cost-cap.md) the workflow has a $0.50 default cap. The leaf call is the only billed action in Phase 4; the leaf enforces its own cap and short-circuits the workflow cap as well. Both checks are cheap (sub-ms).
  - **VCR cassettes.** `pytest-recording` configured with a custom matcher that hashes `(system, few_shots, query)` to the cassette path. Path: `tests/fixtures/cassettes/<sha256>.yaml.zst`. **Banned in CI:** `VCR_BAN_NEW_CASSETTES=1` makes a cassette miss in CI a hard failure (with the recorded request body in the error so a dev can regenerate locally).
  - **`langgraph` imported minimally.** Only `langgraph.graph.StateGraph` for the leaf-node wrapper (per the phase spec). The full state-machine wrap is Phase 6. Avoiding the LangGraph runtime here removes ~50 ms of overhead — small but free.
  - **Retry policy:** retry = 1 on `RateLimitError` and `APIConnectionError`, with exponential backoff (max 4 s). No retry on `ValidationError` from the structured-output parser — that's a content failure; surface it. **See lens-summary surfaced tension with ADR-0014.**
- **Tradeoffs accepted:**
  - Anthropic-direct over a vendor-agnostic shim. ADR-0020 is deferred; Phase 4 picks Anthropic for prompt-caching reasons. **The leaf interface (`invoke_leaf`) is one function with vendor-neutral arguments**, so swapping in an OpenAI implementation is a single-file substitution — but no shim today.
  - Server-side structured output is an Anthropic feature; if it lags on a given model version, we fall back to a JSON-mode hint + client-side `pydantic` validation. The streaming parser handles both paths.
  - We do **not** use Anthropic's Files API or Code Execution tools in Phase 4. They're attractive but extend the leaf surface beyond what's needed for plan generation, and the test surface for tools is heavy.

### 4. `RagStore` — chromadb local persistent

- **Purpose:** Store `(embedding, metadata, content_ref)` triples for solved examples; serve top-k similarity in ≤ 30 ms.
- **Interface:** `upsert(example_id, vec, meta, content_ref)`, `search(vec, top_k, filters) -> list[Hit]`, `get(example_id) -> SolvedExample`.
- **Internal design:**
  - **`chromadb.PersistentClient` in-process.** No docker, no HTTP. Persisted under `.codegenie/rag/chroma/`. Single collection: `vuln_solved_examples`.
  - **Metadata fields indexed:** `ecosystem` (npm/pypi/etc), `language`, `cve_year`, `engine_used` (ncu/openrewrite-stub/manual), `recipe_id` (nullable), `node_major` (the runtime major). Filter by these *before* similarity to cut the search space — chromadb supports `where` filters. For a 100-example corpus this is overkill; at 1 k–10 k it's load-bearing.
  - **Hot-loaded into memory.** First search triggers `.peek(1)` to warm the file caches. The chromadb sqlite is ~25 MB at 100 examples — fits in OS page cache trivially.
  - **No qdrant.** The roadmap allows either. Performance reading: qdrant-local-docker adds a docker round-trip (~5–10 ms per call), needs a container running, and we don't get HNSW perf benefits below ~10 k vectors. We commit to chromadb for v0.4.0; **the swap to qdrant is an ADR amendment when the corpus crosses 5 k examples** (Phase 14-ish).
- **Tradeoffs accepted:**
  - Single-collection design. No per-tenant collection split. Phase 16 adds multi-tenancy and will need to revisit.
  - chromadb's index is recomputed on every restart (cheap at this size, painful at scale). Pin chromadb version in `pyproject.toml` and write a smoke test that catches API drift.

### 5. `SolvedExampleRecorder` — async, fire-and-forget

- **Purpose:** When a remediation succeeds (regardless of which tier emitted the plan), persist it as a solved example so future workflows hit RAG/cache instead of LLM.
- **Interface:** `record(plan, advisory, repo_ctx, validation_signals) -> RecordReceipt`. Returns immediately; actual write happens on a background asyncio task.
- **Internal design (performance reasoning):**
  - **OFF the critical path.** The orchestrator does not `await` the recorder. The recorder is spawned via `asyncio.create_task` and the worker returns to the user. If the worker dies mid-write, the next run will retry (the recorder writes a marker file at the start so we don't double-write; idempotent on `example_id`).
  - **Embedding computed eagerly.** As soon as `Plan` is produced (any tier), schedule the embedding compute on the embed-worker so it's done by the time the validator finishes. We "earn" the time during the slow validator phase.
  - **Write fan-out:** (a) chromadb upsert; (b) write `.codegenie/rag/examples/<example-id>.yaml` (the canonical bundle); (c) write the query-key cache entry pointing to this `example_id`. All three are idempotent.
  - **Negative examples too.** If a plan validated *fail* but the failure is informative (e.g., consistent `peer_dep_conflict`), record under `vuln_negative_examples` collection so the LLM next time has a "tried this, didn't work" few-shot. This is cheap (one extra upsert) and downstream-valuable.
- **Tradeoffs accepted:**
  - Fire-and-forget means a worker crash within the ~50 ms window between success and write-complete loses the record. Acceptable: the next workflow that hits the same query key will simply retry the LLM and re-record.
  - Ingesting Phase 3 historical successes is a one-shot `codegenie rag ingest --from-phase3-runs` operator command, not automatic, to keep Phase 3 unchanged.

### 6. `QueryKey` exact-replay cache

- **Purpose:** Catch identical replans across a portfolio scan in microseconds.
- **Interface:** `get(query_key) -> CachedPlan | None`, `put(query_key, plan, example_id)`. Filesystem-backed.
- **Internal design:**
  - **Content-addressed.** Key = sha256 over a **canonical, schema-pinned tuple**: `(advisory.canonical_id, advisory.fixed_version, repo_ctx.lockfile_blake3, repo_ctx.engines.node_major, recipe_selection.reason, recipe_catalog_blake3)`. JSON-canonicalized via `_canonicalize_tuple()` (sorted keys, LF endings) before hashing — same primitive as Phase 3's lockfile canonicalization.
  - **Lock-free reads, single-writer.** Reads are mmap'd; writes are `os.replace`-atomic. No db engine.
  - **TTL: indefinite, but recipe-catalog-version-fenced.** The blake3 of the recipe catalog directory is part of the key. When a new recipe lands, entries from before the catalog change become cold automatically (because the new key no longer matches the old key). This avoids ever serving a stale plan when a new deterministic recipe could now handle the case.
- **Tradeoffs accepted:**
  - Whole-catalog hash is broader than necessary (one recipe change invalidates all entries that referenced the catalog version). Could segment by recipe-engine but the savings are small at 100 examples; revisit at scale.
  - No distributed cache. Phase 14 will move this to Redis hot views per ADR-0013.

### 7. Phase 3 integration shim — `Planner.plan()` glued to coordinator

- **Purpose:** Patch into Phase 3's coordinator at the single point where `RecipeSelection.reason != "matched"` causes `exit 4`. Replace `exit 4` with `Planner.plan()`; if the planner returns a `Plan`, feed it back into the Phase 3 transform stage.
- **Interface (change to Phase 3):** **none — Phase 3 coordinator stays unchanged.** We add a new orchestrator entrypoint `remediate_v2` (Phase 4) that *wraps* Phase 3's coordinator and intercepts the exit-4 signal. This honors the §2.5 extension-by-addition commitment.
- **Internal design:**
  - The Phase 4 wrapper installs a `select_callback` on the Phase 3 selector; if the callback returns a non-`matched` `RecipeSelection`, the wrapper invokes the planner and substitutes the resulting `Recipe` (or `ManualPatch`) into the downstream transform call.
  - **Plans that produce a recipe**: route to the existing `RecipeEngine.apply` path (unchanged Phase 3 code).
  - **Plans that produce a manual patch** (LLM path on a major-version bump with custom call-site rewrites): a new `ManualPatchEngine` implementing `RecipeEngine` ABC, applies a unified diff inside the worktree with `git apply --check` first. Falls under "engine ABC extends by addition" (Phase 3 §Component 2).
  - **Same validation pipeline.** The Phase 4 path goes through the *same* `npm ci`-then-`npm test` validator. The trust score is still strict-AND on objective signals. No new gate is added; Phase 5 adds gates.

### 8. CLI surface — additive

- New flags on `codegenie remediate`:
  - `--planner=on|off|cache-only` (default `on`); `--no-llm` (forces tiers 1+2 only).
  - `--max-llm-cost-usd=0.50` (default).
  - `--embed-model={minilm,bge,voyage}` (default `minilm`).
- New subcommands:
  - `codegenie rag ingest --from-phase3-runs [--since DATE]` — one-shot replay of Phase 3 audit logs to seed the store.
  - `codegenie rag stats` — corpus size, hit-rate-by-tier, last-N queries.
  - `codegenie rag search <query>` — debug introspection.

---

## Data flow

End-to-end run for `codegenie remediate ./services/auth --cve CVE-2024-12345` where this is a **major-version bump with breaking call-site rewrites** (LLM path):

1. **Phase 3 Stages 1–3 run unchanged.** Tool-readiness, load context, resolve advisory, lockfile policy scan. ~1.5 s.
2. **Phase 3 selector returns `RecipeSelection(reason="range_break", diagnostics={"current":"^4.x","fixed":"6.x"})`.** Wrapper intercepts.
3. **Planner tier 1: query-key cache.** Compute sha256 over the canonical tuple. Miss (first time we've seen this CVE-on-this-lockfile shape). ~2 ms.
4. **Planner tier 2: embed + RAG.** Build a short, schema-pinned query string: `f"CVE {advisory.id} {advisory.summary} | package {advisory.package} {current_range}->{fixed_range} | reason {reason} | node {node_major}"`. Send to embed-worker over UDS. Receive 384-d vec in ~28 ms. Filter chromadb by `ecosystem="npm"`, `cve_year=2024`, similarity search top-8 in ~12 ms. Top-1 score = 0.79 — above `τ_few` but below `τ_hit`. So we carry the top-3 as few-shots into tier 3.
5. **Planner tier 3: leaf LLM.** Build the three Anthropic message blocks. Cassette-key hash hits a miss in dev. The leaf call:
   - System prefix (~12k tokens): instructions + skills manifest + recipe-engine surface + ManualPatch JSON Schema. Cache-control `ephemeral`.
   - Few-shot block (~6k tokens): three solved examples. Cache-control `ephemeral`.
   - Query block (~2k tokens): the actual advisory + repo-context slice (lockfile-vulnerable-paths, top-N entrypoint files, the failed recipe trace from Phase 3).
   - Stream with `max_tokens=2048`, structured output schema = `Plan`.
   - In parallel: **eagerly enqueue the embedding compute for the to-be-recorded example** so it's done before validation finishes.
   - The first complete JSON object yields ~1.6 s into the stream. By 9.4 s total the full Plan is delivered. Cost: ~3 000 input billed (20k cached) + ~1 800 output = **$0.011** on Sonnet 4.7 per the 2026 pricing table.
6. **Plan executed via `ManualPatchEngine`.** `git apply --check` against the worktree; on green, apply and `git commit`. ~120 ms.
7. **Validation: same `npm ci` + `npm test`** that Phase 3 uses. Single sandbox profile. ~60 s.
8. **Strict-AND trust score → green.** Branch finalized, report written.
9. **`SolvedExampleRecorder` fires (async).** Embedding is already done (computed in step 5). Upserts chromadb; writes example bundle; writes query-key cache entry. ~80 ms. **The worker has already exited by the time this completes**, but the next portfolio peer with the same CVE on the same lockfile shape gets a tier-1 hit.

**Where parallelism is extracted.**
- Embedding-compute-for-record runs **during** the LLM stream (step 5 → 9 pipeline).
- Embedding-compute-for-search runs **during** the loading of the few-shot block from chromadb (chromadb fetch is ~12 ms, embed is ~28 ms — net 28 ms not 40 ms).
- VCR cassette read happens **during** the prompt-block assembly (`asyncio.gather`).

**Where caches are consulted (every run):** (a) query-key cache (tier 1); (b) embedding cache for the *query string* (avoids re-embedding repeat advisories); (c) Anthropic prompt cache (server-side, 5-min TTL); (d) cassette cache (test-only).

---

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| Embed-worker not running | UDS connect fail | Spawn lazily; fall back to in-proc embed (cold start ~2 s, logged) |
| chromadb db corrupted (SQLite checksum) | `chromadb` raises on open | Quarantine `<chroma_dir>` to `<chroma_dir>.corrupt-<ts>` + rebuild empty + force `--no-rag` for this run; loud warning |
| Embedding model file missing / hf-cache evicted | `sentence-transformers` ImportError on first call | Operator runs `codegenie tools install embed` (downloads model); orchestrator exits 9 with clear instruction |
| LLM streaming connection drop mid-stream | `anthropic.APIConnectionError` | Retry = 1 with backoff; on second failure escalate with `interrupt()`-equivalent exit code 10 |
| LLM produces invalid Plan JSON (structured output disagreement) | Incremental parser `ValidationError` | Cancel stream (charged only partial output); no retry; record as a *negative example* with the error context; surface exit code 11 |
| LLM produces a Plan whose patch fails `git apply --check` | `ManualPatchEngine.apply` | Exit 12; the plan is recorded as a negative example; do not call LLM again in the same workflow (Phase 5 wraps with 3-retry widening) |
| LLM call exceeds `--max-llm-cost-usd` (predicted from output tokens streamed) | Budget Enforcer on token count | `StreamCancelled` + exit 13; partial output discarded; record cost; surface budget-overrun audit event |
| RAG returns a high-score but objectively-wrong example (`τ_hit` met but plan fails validation) | Validator (Phase 3 strict-AND) | Plan fails normally; recorder stores the **misleading match as a negative example** with `mismatch_cluster_id` so future searches penalize this neighborhood; if a portfolio sees 3 such failures on the same neighborhood, auto-raise `τ_hit` for that cluster (advisory ID) |
| Query-key cache returns stale plan (recipe catalog changed but blake3 stale because file mtime didn't update) | Catalog blake3 recomputed at startup; mismatch → invalidate all | Cache invalidated; rebuild from next runs |
| Worker dies between success and `SolvedExampleRecorder` write | Next run is the canary | Next run sees no cache, retries; no data loss in chromadb (write is wal'd) |
| VCR cassette missing in CI | `VCR_BAN_NEW_CASSETTES=1` enforcement | Fail loud with the recorded request body in the error; dev regenerates locally |
| Anthropic returns 529 overloaded | `anthropic.OverloadedError` | Retry = 1 with jittered backoff; on persistent fail, escalate to operator (exit 14); no auto-fallback to a different model (avoids silent quality drift) |
| `langgraph` API drift breaks the leaf wrapper | Pinned to `langgraph==0.2.x` + smoke test | CI red on bump; revisit in Phase 6 |
| Cassette `sha256` collision on edited fixture | Deterministic content addressing makes this near-impossible | If it ever fires, surface as a test framework bug; cassettes are immutable |
| Two workers race to update same example_id | `os.replace` atomicity + chromadb WAL | Idempotent; last writer wins; warn in audit |

---

## Resource & cost profile

Numbers are order-of-magnitude with empirical anchoring against the Phase 3 baseline and the published Anthropic pricing / latency tables.

- **Steady-state worker memory** (one workflow active): Python orchestrator + Phase 3 state ≈ 350 MB; planner state (chroma client + cached embeddings) ≈ 200 MB; **embed-worker out of process** so 0 MB charged to the orchestrator. Per-worker ceiling: **≤ 900 MB**.
- **Embed-worker** (shared host singleton): **≤ 600 MB** with MiniLM, **≤ 1.4 GB** with BGE-base. Idle CPU: ~0.5 % (it's mostly asleep on the UDS).
- **chromadb on-disk:** ~25 MB at 100 examples, ~250 MB at 1 000. Page-cache resident: ~25 MB hot working set.
- **Cassette corpus:** **zstd-compressed** ~50 KB per cassette × ~50 cassettes ≈ **2.5 MB**. Cheap to ship in the repo. Cassettes for actual production runs (real CVE data) are **not committed** — only the synthetic fixtures.
- **Wall-clock budget per LLM call (Sonnet 4.7, ~25k input / 2k output, streaming):** p50 ≈ 8 s, p95 ≈ 14 s, p99 ≈ 22 s (per the 2026 latency tables; tight bound from prompt caching reducing prefill).
- **$/PR with cached prompt:** cost of input = `(uncached_input × $3/M) + (cached_input × $0.30/M) + (output × $15/M)`. With 80 % cache hit: `(5k × $3/M) + (20k × $0.30/M) + (2k × $15/M) = $0.015 + $0.006 + $0.030 = $0.051`. Under the **$0.08** target.
- **$/PR amortized across a portfolio of 100 services hitting the same CVE:** one cold LLM call ($0.051) + 99 tier-1 cache hits ($0) = **$0.00051 / PR**. This is the compounding-savings story per [ADR-0011](../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) made concrete.
- **Per-workflow token budget cap (ADR-0025):** default **$0.50**. The leaf cost is < 20 % of cap, so retries up to 9 are within budget — but in Phase 4 retry = 1 by construction; Phase 5 raises this.
- **Network egress (production):** Anthropic API only, on tier-3 invocations. ~25 KB request, ~10 KB response per call.
- **Network egress (CI):** zero. Banned.

---

## Test plan

### Unit tests

- `test_query_key_canonicalization.py` — same advisory + same lockfile → identical sha256, regardless of dict ordering; lockfile bit-flip → different sha256.
- `test_planner_tier_decisions.py` — synthetic objective signals assert routing: `(score=0.91 → rag_exact)`, `(score=0.78 → rag_fewshot_llm)`, `(score=0.50 → llm_cold)`. Tiers are pure functions of scores; no LLM.
- `test_embed_worker_uds_protocol.py` — round-trip msgpack frames; backpressure under burst; reconnect on socket loss.
- `test_anthropic_leaf_prompt_blocks.py` — assert the three message blocks have the correct `cache_control` markers; query block is uncached.
- `test_streaming_parser_invalidates_early.py` — synthetic SSE feed; on first invalid step, parser cancels and reports `tokens_burned` correctly.
- `test_max_tokens_cap_fires.py` — synthetic stream of 3 k output tokens with `max_tokens=2048` → cancelled at 2048.
- `test_solved_example_recorder_idempotent.py` — record same plan twice → single chromadb row; query-key cache entry stable.
- `test_negative_example_on_apply_failure.py` — `git apply --check` failure path records to `vuln_negative_examples` collection.
- `test_catalog_blake3_invalidates_query_cache.py` — write a recipe → catalog hash changes → tier-1 cache miss for any entry referencing the catalog.

### VCR-recorded integration tests

- `test_e2e_rag_hit.py` — pre-seeded chromadb with 5 fixtures; advisory matches one with score 0.92 → exits via `rag_exact` source; **no LLM call** (cassette assertion: zero outbound requests recorded).
- `test_e2e_llm_cold.py` — empty chromadb; cassette with a recorded plan; assert plan applies + validates green; assert recorder fires; **subsequent run on same fixture hits tier-1 cache** and produces byte-equivalent diff.
- `test_e2e_rag_then_llm_fewshot.py` — pre-seeded with one near-miss; cassette with the fewshot-augmented call recorded.
- `test_e2e_major_version_breaking_change.py` — the phase exit criterion. A `react-router@5 → @6` CVE fixture; LLM path; recorded into store; rerun hits RAG and produces equivalent fix at lower cost (assert cost-tokens delta).
- `test_phase3_unchanged.py` — Phase 3's full integration suite runs verbatim under Phase 4 imports loaded.

### RAG retrieval quality (labeled fixture set)

- `tests/fixtures/rag_labeled/` — 30 `(query, expected_top1, expected_in_top3)` triples spanning ecosystems and reasons.
- `test_rag_retrieval_at_k.py` — assert recall@3 ≥ 0.85 on the labeled set with MiniLM; **regression test** in CI.

### Property tests

- `test_planner_is_total.py` — Hypothesis: any well-formed `RecipeSelection(reason != "matched")` returns a `PlanResult` (success or escalation) without raising.
- `test_canonicalization_stable.py` — Hypothesis: arbitrary dict shuffling of the canonical tuple → same sha256.

### Performance canaries (gating in CI)

- **`test_selector_chain_p95_under_250ms.py`** — 100 iterations of tier-1-miss-tier-2-hit path; assert p95 ≤ 250 ms. Embeds against a pre-warmed worker.
- **`test_query_key_replay_under_5ms.py`** — 1 000 iterations of tier-1 hits; assert p95 ≤ 5 ms.
- **`test_prompt_cache_breakpoint_layout.py`** — record a cassette, parse its replayed request, assert (a) ≤ 2 `cache_control` markers; (b) the system block hash is stable across two runs with the same fixture (proving cache hits aren't being missed by an unstable prefix).
- **`test_e2e_llm_path_under_180s.py`** — wall-clock canary on the fixture LLM-path test; **CI red if p95 ≤ 180 s violated**.
- **`test_cost_ledger_predicts_within_5pct.py`** — pre-call token-prediction matches post-call `usage.input_tokens` ± 5 % so the budget enforcer can pre-cancel reliably.

### Cost regression canary

- A nightly CI job recomputes `$/PR` across the fixture portfolio using *cassette-replayed* token counts (no network) — drifts > 10 % vs. baseline are CI-red.

---

## Risks (top 5)

1. **`τ_hit` and `τ_few` thresholds are guesses until calibration data exists.** A `τ_hit` set too low silently emits wrong-package bumps (RAG hit on a near-twin CVE). **Mitigation:** ship conservative defaults (`τ_hit = 0.86`); the validator's strict-AND catches wrong-package outputs at `npm ci`; mismatches are recorded as negative examples and auto-raise `τ_hit` for that advisory neighborhood after 3 fails. **Residual:** the first 3 wrong matches per neighborhood waste a validate cycle (~60 s each). Acceptable.
2. **Anthropic prompt caching depends on byte-stable system blocks.** A trivial change (e.g., re-sorting the Skills manifest) silently drops cache hit rate to 0 % and 4× the cost. **Mitigation:** golden-file test on the system-block bytes; CI red on drift. **Residual:** cross-version SDK changes can also break the cache. Pin `anthropic` SDK.
3. **chromadb local-mode performance cliff at ~5–10 k examples.** We accept this as a "Phase 14 problem." **Residual:** if the portfolio scales faster than expected, the planner-chain budget blows past 250 ms p95 silently. **Mitigation:** the perf canary CI gates on the budget; firing the canary at 250 ms is the trigger to migrate to qdrant or pgvector (ADR amendment).
4. **Structured-output server-side validation may not be available on all Anthropic models.** **Mitigation:** dual-path the parser (server-side structured-output preferred, client-side `pydantic` fallback). **Residual:** the fallback path is slower by ~5 % and pays for tokens that get rejected — acceptable.
5. **Fire-and-forget recorder loses writes on worker crash.** A single lost write means the *next* identical workflow re-pays the LLM call (~$0.05). **Mitigation:** worker writes a `pending-record-<run-id>.json` marker; on next CLI invocation, `codegenie rag flush-pending` is a fast pre-check that replays unwritten records. **Residual:** if the operator never re-invokes the CLI, records are lost. Acceptable.

---

## Acknowledged blind spots

This lens deprioritized:

- **Prompt-injection / poisoned solved-example defense.** A malicious solved example could be embedded with adversarial text that biases the LLM toward harmful diffs. The performance design does *no* sanitization on RAG ingest beyond schema validation. The security-first design will own this; the synthesizer will need to merge.
- **Per-leaf-call token accounting fidelity.** I trust `usage.input_tokens`/`output_tokens` from the Anthropic response. If those fields drift in semantics, the budget enforcer fires late. The cost-observability ADR-0024 wants finer-grained attribution per persona (Stage 3 vs. Stage 1 assessor). I do per-call accounting but not per-stage attribution — defer to Phase 13.
- **Multi-vendor leaf-SDK portability.** ADR-0020 explicitly defers; I commit to Anthropic. Swap-cost: rewrite `anthropic_leaf.py` (~300 LOC). The best-practices-first design will likely advocate for a shim from day one.
- **Embedding-model swap-back-compat.** Switching from MiniLM to BGE requires re-ingesting the chromadb. I don't ship a re-ingest tool until needed; the operator has to call `codegenie rag reindex --model bge` which scans and re-embeds.
- **HITL prompts on uncertain RAG hits.** When `τ_few < score < τ_hit`, the design carries the example as few-shot — *not* asks the human. A best-practices-first or security-first design might require human confirmation. I optimized for throughput; the strict-AND validator catches wrong outputs.
- **Per-task-class cost cap differentiation.** ADR-0025 hints at vuln-vs-migration cap tiers; I use one cap across vuln subtypes. Phase 13 owns the AgentOps tuning.
- **Negative-example pollution.** If many wrong RAG hits accumulate, the negative store grows and slows lookups. I have no GC policy. Phase 15 (recipe-authoring) likely consumes negative examples and obviates them; punt.
- **Structured logging of LLM token-by-token cost** for observability. I emit per-call total to the audit chain; the AgentOps Phase 13 needs per-token granularity. Punt.

---

## Open questions for the synthesizer

1. **Should the planner's tier-2 carry the recipe-failure trace from Phase 3 as a *first-class* RAG metadata field?** It would let us filter by "examples where ncu also failed" and likely improve match quality, but it adds 200–500 tokens per example. Cost-of-storage vs. retrieval-quality tradeoff.
2. **Anthropic SDK vs. vendor-neutral shim from day one.** ADR-0020 defers. My performance argument: shim costs ~1.5 ms/call and obscures prompt-cache semantics. Best-practices argument: portability matters. Pick one explicitly in the synthesis.
3. **Should `SolvedExampleRecorder` write be made durable (e.g., a workflow Activity in Phase 9) earlier?** Performance says fire-and-forget; security may want a write-ahead log. Phase 9 (Temporal) takes ownership eventually — but in Phase 4 we have neither Temporal nor a real audit log beyond Phase 2's BLAKE3 JSONL chain.
4. **`τ_hit` calibration plan beyond conservative defaults.** Should Phase 4 ship with a `codegenie rag calibrate` command that runs ROC on the labeled fixture set and emits suggested thresholds? Adds dev-tool surface; arguably belongs in Phase 13/15.
5. **Voyage remote embeddings — block on the rerank-quality lift or punt to Phase 14?** Local MiniLM is fast enough but the recall@3 gap to Voyage `voyage-3` is ~15 % on labeled sets in published benchmarks. Cost = $0.02 / 1 M tokens and ~150 ms RTT.
6. **Should the negative-example collection feed back into the *prompt* (as "things we tried")?** Adds ~500–1 000 tokens per call, may improve LLM quality on retry-2/3 in Phase 5. Phase 5 problem? My instinct: surface and defer.
7. **Should the wrapping orchestrator (Phase 4) introduce its own audit-event types (`planner.tier1.hit`, `planner.tier2.fewshot`, `planner.tier3.invoked`, `llm.tokens.recorded`, `solved_example.recorded`)?** Phase 3 added a clear set; consistent additivity says yes. Performance says yes too (cheap). Surface as a checklist item for the synthesizer.
8. **OpenRewrite-stub engine interaction with the LLM path.** If the LLM produces an OpenRewrite-shaped recipe (Phase 15 preview), does Phase 4 dispatch through `OpenRewriteEngineStub` or always through `ManualPatchEngine`? Currently I route OpenRewrite-shaped plans through the stub; this is a hidden coupling to Phase 3 §Component 2.
