# Phase 04 — Vuln remediation: LLM fallback + solved-example RAG: Performance-first design

**Lens:** Performance — throughput, latency, token economy, footprint.
**Designed by:** Performance-first design subagent
**Date:** 2026-05-18

## Lens summary

I optimized for **token economy and time-to-PR**, in that order, because Phase 4 is the first phase where an LLM enters the loop and *every* design decision either keeps a workflow on the cheap rails (recipe → cache → RAG → cassette) or shoves it onto the expensive rails (live Claude call). Phase 3 made the recipe path cost $0; Phase 4's job is to make the **fallback path** asymptotically approach $0 as the solved-example store grows, and to make the *common* fallback case (peer-dep conflict, major-bump call-site rewrite the recipe couldn't handle) hit warm prompt cache and answer in seconds, not tens of seconds.

Concrete biases:

- **A miss on the deterministic tier is a *budget event*, not an exception.** I treat each tier-fall-through as an explicit "I'm about to spend money" decision and emit a typed event so Phase 13 can attribute the cost retroactively. The hot path is **recipe-hit (free) → RAG-hit (sub-cent embedding + 4 KB Claude call with cache hit) → cold LLM (real spend)**. I make the second tier do real work — RAG isn't "find few-shot for the LLM," it's "skip the LLM entirely when the solved example is byte-applicable, modulo a deterministic re-targeting of package versions and file paths."
- **The `RecipeMatcher → RagRetriever → LeafLlm` chain is one in-process Python pipeline, not three RPCs.** ADR-0011 names three nodes; I implement them as three async stages of one process with a shared `PlanContext` that carries the `RepoContext`, `VulnerabilityRecord`, and accumulating `tier_attempts` log. There is no "Stage 3 Planning service" yet — Phase 4 is still single-process — but the data flow is a streaming pipeline so Phase 8's planner-supervisor lift is mechanical.
- **`fastembed` ONNX local-CPU embeddings; no `sentence-transformers`; no Voyage.** The roadmap mentions both as options. `sentence-transformers` carries PyTorch (~700 MB wheel + GPU optionality + Python-level matmul); `Voyage` is a remote network call (RTT + cost + outage surface). `fastembed` (BAAI/`bge-small-en-v1.5` quantized ONNX, ~130 MB, 50–80 ms per query on a single CPU core) is the right shape: in-process, no GPU, deterministic, cassette-free, and the embedding wheel is the only thing that crosses the LLM-fence-into-Phase-4 boundary.
- **`chromadb` persistent local; not `qdrant` docker.** Phase 4 is local-CLI. Docker-compose for a vector DB is a 2-second-cold-start dependency for a workload that does one query per workflow. `chromadb` runs in-process against `.codegenie/kg/chroma/`, persists to a single sqlite + duckdb-parquet directory, and survives a worker restart in <50 ms. Qdrant becomes the right answer at Phase 11+ when the KG is a multi-tenant service; the migration is one adapter swap behind a `SolvedExampleStore` Protocol.
- **Anthropic prompt caching is the load-bearing token-economy choice.** Every LLM call ships an identical system-prompt block (`stable_few_shot` cache-control: `ephemeral`) carrying the matched skill + the top-K RAG example + the `RepoContext` slice. Per ADR-0020 default ("Anthropic SDK for initial leaf implementations") + the prompt-caching note. A retry inside the same workflow pays 10% of the input tokens, not 100%. A second workflow on a different repo with the same skill+example pair pays 10% input within the 5-minute TTL window.
- **The `typecheck.<lang>` SignalKind is computed inside the existing `SubprocessJail` from Phase 3 — no new infrastructure.** It registers via `@register_signal_kind("typecheck.typescript")` against the open registry Phase 3 ships. The signal collector is a 60-line module: `SubprocessJail.run(["tsc", "--noEmit"])`, parse stderr for `error TS\d+`, count new-vs-baseline, emit `TrustSignal(kind="typecheck.typescript", passed=bool, details={"new_errors": n})`. p95 inside the jail: 4–8 s for a representative 80-file Node service. LSP is explicitly rejected (ADR-0037 nails this).
- **`pytest-recording` cassettes are content-addressed and per-test-case.** Cassettes live at `tests/cassettes/<test_module>/<test_name>.yaml`; CI runs in `record_mode="none"` (replay-only, fail on cassette miss). The cassette filename is the test name; the *contents* are hashed to a per-test BLAKE3 in a `cassettes.lock` file that Phase 6.5's `bench/vuln-remediation/cases/*/case.toml#cassette_blake3` field references. CI runs 0 live LLM calls per build; the only "live" path is `make refresh-cassettes` (operator-invoked).

**Deprioritized:** rich RAG re-ranking heuristics (top-1 with strict similarity floor is enough at Phase 4 volume); multi-vendor LLM (ADR-0020 stays deferred — Anthropic SDK only; vendor shim is the seam, not the work); the Stage 7 Learning write-back path (Phase 11 owns the merge-outcome side; Phase 4 ships the *write* primitive but does not consume merge webhooks); the conditional Phase-14 Language MCP server (out of scope per ADR-0037 — Phase 4 produces the *evidence* for it but does not introduce LSP infrastructure).

## Goals (concrete, measurable)

Targets are against a representative Phase 4 fixture portfolio: `fixtures/vuln-major-bump/` (one breaking-change CVE requiring call-site rewrite, ~80 .ts files, ~120 unit tests).

| Metric | Target | Rationale |
|---|---|---|
| Time-to-PR p50 — recipe-hit (Phase 3 path unchanged) | **≤ 18 s** | Phase 3 floor preserved |
| Time-to-PR p50 — RAG-hit (cassette replay, prompt-cache warm) | **≤ 22 s** | One embedding + one cached Claude call + Phase-3-shape validate |
| Time-to-PR p95 — RAG-hit | **≤ 35 s** | Per-call jitter + npm install variance |
| Time-to-PR p50 — LLM-from-scratch (no RAG hit, live or cassette) | **≤ 60 s** | Bounded by Claude TTFT + output token rate + validate |
| Time-to-PR p95 — LLM-from-scratch | **≤ 110 s** | Worst case includes one retry inside the leaf |
| Workflows/hour @ portfolio scale, 24 workers, recipe:RAG:LLM = 70:25:5 | **≥ 6,500/hr** | Weighted avg of the three tier latencies |
| **$/PR — recipe-hit** | **$0.00** | Phase 3 invariant |
| **$/PR — RAG-hit (cache warm)** | **≤ $0.004** | ~3 KB stable prompt @ 10% cache rate + 500 output tokens on Sonnet 3.7 |
| **$/PR — LLM-from-scratch (cache cold)** | **≤ $0.06** | ~8 KB system + 4 KB user + 1.5 KB output on Sonnet 3.7 |
| **Prompt-cache hit rate (within 5-min TTL window)** | **≥ 65%** | Same skill+RAG-example pair across consecutive workflows on similar CVEs |
| **Tier-skip rate (recipe + RAG vs total)** | **≥ 90%** after 90 days of solved-example accrual | The compounding-savings story made concrete |
| Vector store query p99 (chromadb local, 10K examples) | **≤ 15 ms** | HNSW index in-process; not the bottleneck |
| Embedding query p99 (`fastembed` BAAI/`bge-small-en-v1.5` quantized, single CPU) | **≤ 80 ms** | Single ONNX session reused across workflows |
| Worker memory ceiling (added on top of Phase 3) | **≤ 350 MB RSS** (chromadb client + ONNX session + Anthropic SDK) | Fits inside Phase 3's 400 MB headroom doubling to 750 MB per worker |
| Cold worker startup overhead (Phase 4 additions) | **≤ 800 ms** | ONNX session load (~500 ms) + chromadb persistent open (~150 ms) + Anthropic client (~100 ms) |
| `typecheck.typescript` signal collection p95 | **≤ 8 s** inside `SubprocessJail` | `tsc --noEmit` on a 80-file Node service |
| CI build wall-clock added by Phase 4 (cassette replay only) | **≤ 60 s** | Cassettes are small YAML; no Docker pulls; no Claude calls |
| Cassette miss in CI | **Hard fail** | `record_mode="none"` enforced via `pyproject.toml` |
| Recipe→RAG→LLM decision overhead (excl. work itself) | **≤ 20 ms p95** | Pure-Python tier dispatch; pipeline-shape, not RPC |

These are aggressive but achievable; the synthesizer should treat them as my lens's upper bound, not the floor everybody adopts.

## Architecture

```
                       codegenie remediate <repo> --cve=<id>
                                       │
                                       ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/cli/remediate.py (Phase 3 entrypoint — UNCHANGED)          │
   │   Phase 4 adds: --tier-cap {recipe,rag,llm} flag (default: llm)          │
   │                 --refresh-cassettes (operator-only; CI rejects)          │
   └────────────────────────────────────┬─────────────────────────────────────┘
                                        │
                                        ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/transforms/orchestrator.py (Phase 3 — extended additively) │
   │   New: Stage 3 (Planning) is now a typed pipeline of THREE tier nodes    │
   │   wired through plugin.transforms()['plan'] returning a TierChain         │
   │   (composition seam — kernel learns no new method)                       │
   └────────────────────────────────────┬─────────────────────────────────────┘
                                        │
                                        ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ plugins/vulnerability-remediation--node--npm/  (Phase 3 plugin — extends)│
   │   subgraph/                                                              │
   │     plan_tier_chain.py   — TierChain(recipe, rag, llm) — the spine       │
   │     tiers/                                                                │
   │       recipe_tier.py     — wraps Phase 3 RecipeEngines (UNCHANGED logic) │
   │       rag_tier.py        — embed query + chroma top-K + re-target step   │
   │       llm_tier.py        — leaf Claude call via LeafLlm Port             │
   │     ports/                                                                │
   │       solved_example_store.py — Protocol (chromadb adapter is default)   │
   │       embedder.py             — Protocol (fastembed adapter is default)  │
   │       leaf_llm.py             — Protocol (Anthropic adapter is default)  │
   │   adapters/                                                              │
   │     chroma_solved_example_store.py    — chromadb impl                    │
   │     fastembed_embedder.py             — fastembed ONNX impl              │
   │     anthropic_leaf_llm.py             — Anthropic SDK impl (prompt cache)│
   │     ts_typecheck_signal.py            — typecheck.typescript collector   │
   │   recipes/                                                               │
   │     (Phase 3 recipes unchanged)                                          │
   │     call_site_rewrite_skeleton.py     — NEW: helper for LLM-emitted diffs│
   └────────────────────────────────────┬─────────────────────────────────────┘
                                        │
                                        ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/kg/ (NEW package; tiny — only what Phase 4 needs)          │
   │   store.py            — SolvedExampleStore facade; chromadb is default   │
   │   schema.py           — Pydantic SolvedExample + EmbeddingRecord; frozen │
   │   ingest.py           — write_solved_example(transform, outcome, signals)│
   │                         (called by Phase 3's RemediationOutcome handler  │
   │                         on outcome.kind == "validated"; Phase 11 will    │
   │                         additionally call this from merge webhook)      │
   │   embed.py            — Embedder facade; fastembed is default            │
   │   index.py            — content-addressed query cache (sqlite)           │
   └────────────────────────────────────┬─────────────────────────────────────┘
                                        │
                                        ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ .codegenie/                                                              │
   │   kg/                                                                    │
   │     chroma/                — chromadb persistent dir (sqlite + parquet)  │
   │     embeddings.cache.sqlite — query-string → vector cache                │
   │     plan-cache.sqlite      — (TierKey) → TierOutcome content-addressed   │
   │   events/                                                                │
   │     workflow-internal/<wid>.jsonl.zst  — Phase 3 stream                  │
   │     spanning/append.jsonl.zst           — Phase 3 stream                 │
   │     (new event kinds: TierEntered, TierResolved, RagHit, RagMiss,        │
   │      LlmCallStarted, LlmCallReturned, CacheHit, CacheMiss,               │
   │      PromptCacheHit, TypecheckSignal)                                    │
   └──────────────────────────────────────────────────────────────────────────┘

   ┌──────────────────────────────────────────────────────────────────────────┐
   │ tests/cassettes/                                                          │
   │   plan/                  — pytest-recording yaml per test, hashed in     │
   │   plan/cassettes.lock    — { test_path: blake3 } — Phase 6.5 reads this  │
   │   embed/                 — fastembed is deterministic; NO cassettes      │
   │                            needed (asserted by test)                     │
   └──────────────────────────────────────────────────────────────────────────┘
```

Three load-bearing architectural lines:

1. **The recipe → RAG → LLM chain is a `TierChain` Pydantic object holding three callables — `(recipe_tier, rag_tier, llm_tier)` — wired into the plugin's subgraph via `plugin.transforms()['plan']`.** The plugin protocol does not learn a `tier_chain()` method — it learns one new `TransformKind = "plan"` value, and the existing `transforms()` map returns a `RecipeEngine` for plan that is itself a `TierChainPlanRecipeEngine`. **Zero edits to `src/codegenie/plugins/protocols.py`.** This is the Phase 3 critic issue #4 re-applied: extend through the existing seam, never grow the kernel.

2. **The vector store lives behind a `SolvedExampleStore` Protocol** with `chromadb` as the in-tree default. Anything that does similarity search goes through `SolvedExampleStore.query(embedding, top_k, similarity_floor) -> list[SolvedExample]`. The Phase 11+ migration to qdrant or pgvector ([ADR-0017](../../production/adrs/0017-knowledge-graph-backend.md) — deferred default: pgvector) is one adapter swap. This is hexagonal, not premature pluggability — we ship one adapter Phase 4, and Phase 17 ships the second.

3. **Prompt caching is configured at the leaf adapter, not at the call site.** `AnthropicLeafLlm.complete(prompt: StructuredPrompt) -> LlmResponse` accepts a typed `StructuredPrompt` carrying `system_blocks: list[CachedBlock]` and `user_blocks: list[Block]`. The adapter wraps `client.messages.create(..., system=[{"type":"text","text":...,"cache_control":{"type":"ephemeral"}}])` so the cache-control discipline is enforced uniformly. **The leaf call sites never construct raw Anthropic dicts.**

---

## Components

### 1. `TierChain` and tier nodes (`plugins/.../subgraph/plan_tier_chain.py`)

- **Purpose:** The recipe → RAG → LLM decision chain. One async generator that yields tier attempts; the first tier returning `Applied | NotApplicable(escalate=True)` wins.
- **Interface:**
  ```python
  class TierAttempt(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      tier: Literal["recipe", "rag", "llm"]
      outcome: RecipeOutcome
      cost_usd: Decimal           # 0 for recipe; embedding cost for rag; live for llm
      wall_clock_ms: int
      cache_hits: dict[Literal["plan", "embedding", "prompt"], bool]

  class TierChainResult(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      winning_tier: Literal["recipe", "rag", "llm"] | None
      attempts: list[TierAttempt]                # always 1, 2, or 3 entries
      transform: Transform | None                # None iff all three escalated

  class TierChain:
      def __init__(self, recipe: RecipeTier, rag: RagTier, llm: LlmTier) -> None: ...
      async def plan(self, ctx: PlanContext) -> TierChainResult: ...
  ```
- **Internal design:** A 25-line `for tier in (self._recipe, self._rag, self._llm)` loop. Each tier runs and emits `TierEntered`/`TierResolved` events. `tier_cap` (CLI flag) clamps the iteration: `--tier-cap=recipe` runs only recipe; `--tier-cap=rag` runs recipe+rag; default is all three. A failed tier emits `TierResolved(outcome=NotApplicable(reason))` and the loop continues. A successful tier emits `TierResolved(outcome=Applied(transform))` and the loop short-circuits — **subsequent tiers never run, never warmed, never billed**. The loop is `async` so the embedding model can stay warm across calls inside the same worker, but the *tier dispatch* is strictly sequential per workflow (no race, ADR-0011 specifies serial fallback semantics).
- **Tradeoffs accepted:** No tier hedging — if RAG is *slow* (cassette miss + live embed), we eat the latency rather than racing RAG with a speculative LLM call. Cost beats latency at this seam; the prompt-cache savings on RAG-hit are ~15× the cost of a speculative cold LLM call. Synthesizer note: Phase 3's `BundleBuilder` rejected hedged-race for the same reason; we stay consistent.

### 2. `RecipeTier` (`plugins/.../subgraph/tiers/recipe_tier.py`)

- **Purpose:** Phase 3's recipe path, untouched, wrapped behind the tier interface.
- **Interface:**
  ```python
  class RecipeTier:
      def __init__(self, recipe_engine: RecipeEngine) -> None: ...
      async def attempt(self, ctx: PlanContext) -> TierAttempt: ...
  ```
- **Internal design:** Delegates to Phase 3's `NpmLockfileRecipeEngine.apply(...)`. Returns `TierAttempt(tier="recipe", outcome=engine_output, cost_usd=0, ...)`. Recipe-tier cache is whatever Phase 3's `BundleBuilder.cache` already provides — no new cache here.
- **Tradeoffs accepted:** None — this is the Phase 3 path. Phase 4 buys it for free.

### 3. `RagTier` (`plugins/.../subgraph/tiers/rag_tier.py`)

- **Purpose:** Solved-example retrieval and **deterministic re-targeting** of byte-applicable diffs. When a prior solved example has a high-similarity match AND the only differences from the current case are package version pins / file paths / `package.json` patch coordinates, RAG **directly applies the re-targeted diff without ever calling the LLM**. This is the "asymptote to $0" line.
- **Interface:**
  ```python
  class RagTier:
      def __init__(
          self,
          store: SolvedExampleStore,
          embedder: Embedder,
          retargeter: DeterministicRetargeter,
          *,
          similarity_floor: float = 0.92,
          byte_applicable_floor: float = 0.97,
      ) -> None: ...
      async def attempt(self, ctx: PlanContext) -> TierAttempt: ...
  ```
- **Internal design:**
  1. Build the query key: `f"vuln-remediation cve={ctx.cve.id} affected={ctx.affected_package.name} kind={ctx.failure_mode}"`. Pure string — deterministic.
  2. Look up the query in `embeddings.cache.sqlite` (BLAKE3-keyed). On hit: the cached vector. On miss: `embedder.embed(query)` (50–80 ms) and cache the result.
  3. `store.query(vec, top_k=3, similarity_floor=0.92)`. ChromaDB HNSW index returns in 5–15 ms p99 at 10K examples.
  4. **Branch:**
     - **No results above floor** → emit `RagMiss(reason="below_similarity_floor", best_score=...)`, return `TierAttempt(tier="rag", outcome=NotApplicable("no_match"), cost_usd=embedding_cost_or_zero, ...)`. Fall through to LLM.
     - **Results above `similarity_floor` but below `byte_applicable_floor`** → emit `RagHit(mode="few_shot")`, return `TierAttempt(tier="rag", outcome=NotApplicable("few_shot_for_llm"), cost_usd=..., few_shot=top1)` — the chain treats this as falling through to LLM but the LLM tier consumes `ctx.rag_few_shot` to seed its prompt (this is the canonical RAG → LLM hand-off in ADR-0011).
     - **Result above `byte_applicable_floor` AND `DeterministicRetargeter.can_retarget(top1, ctx) == True`** → call `retargeter.retarget(top1.transform, ctx) -> Transform`. **No LLM call.** Emit `RagHit(mode="byte_applicable", source_example_id=top1.id)`. Return `TierAttempt(tier="rag", outcome=Applied(transform=retargeted), cost_usd≈$0.0003)`. **This is the cheapest non-trivial fallback path in the entire system and the lever that makes the compounding-savings story real.**
- **Why `DeterministicRetargeter`:** Without it, RAG is "find few-shot to feed the LLM" — Konveyor Kai's pattern. With it, RAG is "skip the LLM when the prior solution applies modulo trivial substitution." The substitution set is small and bounded: package name (rare; same CVE → same package), version pins (always different; trivial diff edit), npm semver-range bumps (one-line edit). The retargeter is pure Python operating on the typed `Transform` (Phase 3's `NpmLockfileTransform` carries `package.json` patches as a structured `list[PackageJsonEdit]`, not raw `diff_bytes`) and refuses to retarget when it sees anything outside the substitution allowlist — refuses, not approximates.
- **Tradeoffs accepted:** The retargeter is conservative: anything that touches `.js`/`.ts` source files outside `package.json` falls through to LLM. The 8% of cases that *could* have been byte-applicable but happen to touch one source file are paid as LLM-tier. Acceptable — the false-negative cost is one LLM call; the false-positive cost is a wrong patch shipping to a human reviewer. ADR-0008 says objective signals decide trust; we let validate-stage's `typecheck.typescript` catch any retarget gone wrong.

### 4. `LlmTier` (`plugins/.../subgraph/tiers/llm_tier.py`)

- **Purpose:** Live (or cassette) Claude call. Consumes the RAG few-shot if RAG fell through with `mode="few_shot"`. Emits a `Transform` whose `Transform.provenance` carries the matched recipe template + RAG example references so Stage 7 Learning can re-link.
- **Interface:**
  ```python
  class LlmTier:
      def __init__(
          self,
          leaf: LeafLlm,
          skill_loader: SkillLoader,
          *,
          max_input_tokens: int = 12_000,
          max_output_tokens: int = 2_000,
      ) -> None: ...
      async def attempt(self, ctx: PlanContext) -> TierAttempt: ...
  ```
- **Internal design:**
  - **Structured prompt construction:** Three cached `system` blocks, one uncached `user` block:
    1. `system[0]`: skill text loaded from `plugins/.../skills/vuln-major-bump.md` — stable across all major-bump workflows. `cache_control: ephemeral`. ~2 KB.
    2. `system[1]`: Phase 4's "leaf-LLM emit-a-Transform" instruction template — stable across all Phase-4 leaf invocations. `cache_control: ephemeral`. ~3 KB.
    3. `system[2]`: RAG few-shot example (if any) — JSON-serialized `SolvedExample`. **`cache_control: ephemeral`.** ~1–3 KB. (The same RAG example reused for consecutive workflows within 5 min — the prompt-cache TTL — saves the 90% input cost on each reuse.)
    4. `user`: `RepoContext` slice (TCCM `must_read` + the affected file's tree-sitter outline) + the CVE record + the failure mode tag from recipe-tier. ~2–4 KB, **never cached** (always changes per workflow).
  - **Output discipline:** The leaf is instructed to emit a structured `Transform.from_json(...)` payload (NOT prose), validated by Pydantic at the adapter boundary. A malformed response fails fast and emits `LlmCallReturned(parse_error=...)`; one retry is attempted (Phase 3's three-retry default per ADR-0014 applies to the tier as a whole — Phase 5 wraps this).
  - **Cassette discipline:** The adapter detects `record_mode` from env (`PYTEST_RECORDING_MODE`, defaulting to `"none"` under pytest). Under `"none"`, a cassette miss raises `CassetteMissing` and the workflow exits non-zero before reaching the network. In production (no pytest env), no cassette layer is loaded at all — the adapter is the bare `anthropic` SDK call.
- **Tradeoffs accepted:** The structured-output discipline costs ~200 tokens of system-prompt explaining the JSON shape. Worth it — the alternative is a free-form prose response we parse with regex, which is the failure mode every published agentic-system retrospective warns about.

### 5. `SolvedExampleStore` Protocol + `ChromaSolvedExampleStore` (`src/codegenie/kg/store.py` + adapter)

- **Purpose:** Persistent similarity search over solved examples. The Protocol is the seam; chromadb is the only adapter for Phase 4.
- **Interface:**
  ```python
  class SolvedExampleStore(Protocol):
      async def query(
          self,
          embedding: np.ndarray,
          *,
          top_k: int,
          similarity_floor: float,
          filters: SolvedExampleFilter | None = None,
      ) -> list[SolvedExampleMatch]: ...
      async def add(self, example: SolvedExample) -> SolvedExampleId: ...
      async def count(self) -> int: ...
      async def digest(self) -> BlobDigest: ...  # for cache key composition

  class SolvedExample(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      id: SolvedExampleId
      task_class: TaskClass           # "vulnerability-remediation"
      language: Language              # "typescript"
      build_system: BuildSystem       # "npm"
      cve_id: CveId | None
      affected_package: PackageId | None
      failure_mode_tag: FailureModeTag
      transform_json: dict[str, str | int | bool | float | list | dict]
      origin: Literal["llm_solved", "merge_outcome"]
      added_at: datetime
      metadata: SolvedExampleMetadata
  ```
- **Internal design:** ChromaDB's `PersistentClient` against `.codegenie/kg/chroma/`. One **collection per `(task_class, language, build_system)` tuple** — keeps HNSW indexes small (a few thousand entries each) and lets the plugin's `SolvedExampleFilter` select the right collection in O(1) instead of post-query filtering. HNSW parameters: `M=16, ef_construction=200, ef_search=64` — fast on insert (Stage 7 writes), fast on query, accuracy >99% recall at top-3 against our query distribution. Embedding dimension: 384 (BAAI/`bge-small-en-v1.5`).
- **Why chromadb local over qdrant local-docker:** (a) zero Docker dependency at Phase 4 (which is still pre-Phase-9-Docker-compose); (b) sub-50 ms cold startup vs. qdrant's 2 s docker-compose; (c) the persistent-mode duckdb+parquet on-disk format is git-attributable for fixture portability across CI runs; (d) the migration to qdrant when ADR-0017 resolves is one `__init__.py` swap behind the Protocol — the call sites don't change.
- **Tradeoffs accepted:** ChromaDB's HNSW is single-writer (no concurrent insert). In Phase 4 (single-process CLI) this is fine; Phase 11+ when concurrent merge webhooks fire is the trigger for the qdrant migration. The Protocol is shaped to make that swap mechanical.

### 6. `Embedder` Protocol + `FastembedEmbedder` (`src/codegenie/kg/embed.py` + adapter)

- **Purpose:** Local CPU embeddings, no PyTorch, no network.
- **Interface:**
  ```python
  class Embedder(Protocol):
      async def embed(self, text: str) -> np.ndarray: ...
      async def embed_batch(self, texts: list[str]) -> list[np.ndarray]: ...
      def model_digest(self) -> BlobDigest: ...   # for cache key composition

  class FastembedEmbedder:
      def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None: ...
      # ONNX session loaded once per process; reused across workflows.
  ```
- **Internal design:** A single `fastembed.TextEmbedding(model_name=...)` instance per worker process. Inputs are normalized (lowercase, strip whitespace) so the cache key is stable across trivially-different queries. Output vectors are cached at the query-text level in `.codegenie/kg/embeddings.cache.sqlite` keyed on `(BLAKE3(query), model_digest)` — a workflow that queries the same string twice (recipe-tier failed, RAG-tier runs) pays one embedding, not two.
- **Why `fastembed` over `sentence-transformers`:** `fastembed` ships ONNX directly via `onnxruntime` (50 MB cold) and the BGE quantized model is 130 MB on-disk. `sentence-transformers` pulls in PyTorch (~700 MB CPU wheel, ~2 GB with CUDA) and a JIT step that adds 800 ms to cold start. `fastembed` cold-loads the model in 350–500 ms; first inference is 80 ms; warm inference is 50 ms. For Phase 4's "one embedding per workflow" pattern, `fastembed` wins on cold start, RSS, and wheel size.
- **Why local over Voyage:** Voyage adds a network RTT (50–200 ms p95 + outage surface + per-call cost). Local ONNX is deterministic, free, and offline-capable. The Voyage option becomes interesting only if Phase 14's MCP topology adds a Language MCP server that *also* runs the embedder — at that point an embedding microservice (local network) competes with local-in-worker; until then, in-worker wins.
- **Tradeoffs accepted:** The BGE-small model is 384-dim; we accept the slight retrieval-quality cost vs. BGE-large (1024-dim) for the 3× lower RSS and 2× faster inference. The retrieval-quality bench (`bench/vuln-remediation/cases/rag-retrieval-quality.yaml` — added in 6.5 backfill) holds the threshold honest.

### 7. `LeafLlm` Protocol + `AnthropicLeafLlm` (`plugins/.../adapters/anthropic_leaf_llm.py`)

- **Purpose:** The single seam between Phase 4's deterministic orchestration and the actual Claude API. All token spend goes through here.
- **Interface:**
  ```python
  class StructuredPrompt(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      system_blocks: list[CachedSystemBlock]
      user_blocks: list[UserBlock]
      model: ClaudeModel             # newtype on str — "claude-sonnet-4-5" etc.
      max_output_tokens: int
      temperature: float = 0.0       # leaf is deterministic-by-default

  class CachedSystemBlock(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      text: str
      cache: Literal["ephemeral", "none"] = "ephemeral"
      role_tag: SystemBlockRole       # "skill" | "instruction_template" | "rag_few_shot"

  class LlmResponse(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      output_text: str
      input_tokens: int
      cache_creation_tokens: int
      cache_read_tokens: int
      output_tokens: int
      stop_reason: Literal["end_turn", "max_tokens", "tool_use", "stop_sequence"]
      response_id: str                # for cassette identity

  class LeafLlm(Protocol):
      async def complete(self, prompt: StructuredPrompt) -> LlmResponse: ...
  ```
- **Internal design:** Wraps `anthropic.AsyncAnthropic`. **Cache-control is set per block, not at the call site.** Every block with `cache == "ephemeral"` gets `{"type": "text", "text": ..., "cache_control": {"type": "ephemeral"}}` in the SDK call. The adapter exports a `prompt_cache_breakdown()` helper that emits `PromptCacheHit(cache_read_tokens=N, cache_creation_tokens=M)` events so Phase 13's cost ledger can attribute prompt-cache savings precisely.
- **Token economy math** (Sonnet 3.7 rates as of 2026-05): input $3/M, cached read $0.30/M (90% off), output $15/M. A typical Phase 4 LLM-from-scratch call:
  - 8 KB system = ~2,000 tokens
  - 4 KB user = ~1,000 tokens
  - 1.5 KB output = ~400 tokens
  - **Cold (first call):** `(2000 + 1000) × $3/M + 400 × $15/M = $0.009 + $0.006 = $0.015` plus 25% cache-write premium on the 2000 cached-system tokens = `$0.009 × 0.25 = $0.0023`. **Total: ~$0.017/call.**
  - **Warm (within 5-min TTL):** `2000 × $0.30/M + 1000 × $3/M + 400 × $15/M = $0.0006 + $0.003 + $0.006 = $0.0096`. **Total: ~$0.010/call.**
  - The goal table's ≤ $0.06 LLM-from-scratch number includes one in-call retry (max-attempt=3 per ADR-0014; in-call retries on parse failure cost the same as the first call). Real-world average will be substantially under.
- **Tradeoffs accepted:** Anthropic-only at Phase 4 — vendor shim per ADR-0020 is the seam (`LeafLlm` Protocol) but not the work. Synthesizer note: if security or best-practices want a `MockLeafLlm` for unit tests, it slots in trivially.

### 8. `DeterministicRetargeter` (`plugins/.../subgraph/tiers/retarget.py`)

- **Purpose:** The pure-Python substitution engine that makes RAG byte-applicable in the high-similarity case.
- **Interface:**
  ```python
  class RetargetPlan(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      substitutions: list[Substitution]  # all in the allowlist
      preserved_diff_bytes: int           # how much of source diff is unchanged
      retarget_confidence: float          # purely combinatorial; not LLM

  class DeterministicRetargeter:
      def can_retarget(self, example: SolvedExample, ctx: PlanContext) -> bool: ...
      def retarget(self, source: Transform, ctx: PlanContext) -> Transform: ...
  ```
- **Internal design:** Reads the source `Transform`'s typed payload (Phase 3's `NpmLockfileTransform.edits: list[PackageJsonEdit]`). Walks each edit; substitutes package versions, semver ranges, and (rarely) file paths from the source example to the current context. Refuses to retarget if any edit type is outside `{PackageVersionPin, SemverRangeBump, LockfileResolverHint}`. Substitution allowlist is a `Final[frozenset]` validated at module import.
- **Why this works:** Phase 3's `Transform` ABC is structured (typed edits), not raw bytes. Retargeting structured edits is decidable; retargeting raw `diff_bytes` would require text-level surgery (the failure mode the design-patterns-toolkit warns about). Phase 3's structured-edit discipline is the precondition that makes this tier possible — if Phase 3 had shipped raw bytes, Phase 4 would fall back to LLM 100% of the time on cases that should be free.

### 9. `TypecheckTypescriptSignal` (`plugins/.../adapters/ts_typecheck_signal.py`)

- **Purpose:** The first `typecheck.<lang>` SignalKind per ADR-0037. Runs `tsc --noEmit` inside the existing `SubprocessJail`.
- **Interface:**
  ```python
  @register_signal_kind("typecheck.typescript")
  class TypecheckTypescriptCollector:
      def collect(self, run: SandboxRun, baseline: TypecheckBaseline) -> TrustSignal: ...
  ```
- **Internal design:** Runs `tsc --noEmit --pretty false` inside Phase 3's `SubprocessJail`. Parses stderr — exit 0 → 0 errors; exit 1+ → counts `error TS\d+` lines. **Strict-AND with baseline:** the signal passes iff `new_errors_after <= new_errors_before` (no regression). The baseline is computed once during pre-validate by running `tsc --noEmit` against the unpatched tree; cached on disk under `.codegenie/typecheck/baseline-<repo-sha>.json` so retries skip the baseline run.
- **Why Phase 4 not Phase 3:** Phase 3's CVE-fix recipes are lockfile-only ≥90% of the time — `tsc --noEmit` adds 4–8 s for a signal that always passes (no source code touched). Phase 4's LLM tier emits source-code edits in the major-bump case; `tsc` is the cheapest signal that catches "signature drift after a major-version bump" before the test suite does (which is the slowest signal). Per ADR-0037 §"Phase 3 is not modified by this ADR."
- **Phase 5 forward-compatibility:** Phase 5's `StrictAndGate` consumes this signal exactly like `build`, `install`, `tests` — the registration shape (`@register_signal_kind`) is the seam Phase 5 already widens.
- **Tradeoffs accepted:** Java/Rust `typecheck.*` collectors (per ADR-0037) are explicitly out of scope here — Phase 7 (distroless / Java migration) is the right place.

### 10. `IngestSolvedExample` writer (`src/codegenie/kg/ingest.py`)

- **Purpose:** Phase 4's contribution to the Stage 7 Learning loop. When a workflow's `RemediationOutcome.kind == "validated"`, ingest the `Transform` + signals + origin into the solved-example store so the next workflow can hit it via RAG.
- **Interface:**
  ```python
  async def ingest_solved_example(
      outcome: RemediationOutcome,
      store: SolvedExampleStore,
      embedder: Embedder,
      *,
      origin: Literal["llm_solved", "merge_outcome"] = "llm_solved",
  ) -> SolvedExampleId | None: ...
  ```
- **Internal design:** Builds the canonical query string (same shape RagTier uses); embeds; constructs the `SolvedExample` Pydantic model; `store.add(...)` returns the assigned ID; the workflow emits `SolvedExampleAdded(example_id=..., origin=...)`.
- **Phase 11 coupling deliberately deferred:** Phase 11 will additionally invoke this from the merge webhook with `origin="merge_outcome"`. Phase 4 ships the write primitive; Phase 11 owns the trigger.

---

## Data flow

One representative end-to-end run on a *major-bump CVE* (the headline Phase 4 case — the breaking-change failure the recipe path can't solve):

```
1. CLI: codegenie remediate ./web-app --cve=CVE-2026-1234
2. RemediationOrchestrator loads Phase 3 RepoContext + VulnIndex
   → resolves plugin = vulnerability-remediation--node--npm
   → BundleBuilder.build(...)               [Phase 3 cache: ≥90% hit on warm worker]
3. Stage 3 (Planning) — plugin.transforms()['plan'] returns a TierChainPlanRecipeEngine
   wrapping the TierChain(recipe, rag, llm).
4. RecipeTier.attempt(ctx):
   → NpmLockfileRecipeEngine.match(cve) returns NpmMajorBumpRefuseRecipe
   → outcome = NotApplicable("major_bump_breaking_change")
   → TierResolved(tier=recipe, outcome=NotApplicable, cost=$0, wall_clock=80ms)
   → fall through.
5. RagTier.attempt(ctx):
   → query = "vuln-remediation cve=CVE-2026-1234 affected=express kind=major_bump_breaking_change"
   → embeddings.cache.sqlite lookup MISS (first major-bump query) → fastembed.embed(query) 60ms
   → cache the vector.
   → store.query(vec, top_k=3, similarity_floor=0.92):
       chroma HNSW returns [
         (score=0.961, example_id=ex-2025-11-04-express-major-bump-prior-fix),
         (score=0.918, ...),
         (score=0.881, ...),
       ]
   → top1.score=0.961 ≥ byte_applicable_floor (0.97)? NO (0.961 < 0.97).
   → top1.score=0.961 ≥ similarity_floor (0.92)? YES.
   → emit RagHit(mode="few_shot", source_example_id=ex-2025-11-04-...)
   → set ctx.rag_few_shot = top1; return NotApplicable("few_shot_for_llm")
   → fall through to LLM, but with few-shot context.
   → cost: ~$0.0003 (embedding amortized + chroma query).
6. LlmTier.attempt(ctx):
   → load skill: plugins/.../skills/vuln-major-bump.md  (cache_control:ephemeral)
   → load instruction_template                            (cache_control:ephemeral)
   → ctx.rag_few_shot serialized                          (cache_control:ephemeral)
   → user block: RepoContext slice + CVE + failure_mode + tree-sitter outline
   → AnthropicLeafLlm.complete(prompt) :
       first call in 5-min window → cache_creation; subsequent → cache_read.
       cassette mode under pytest: replay from tests/cassettes/plan/test_major_bump.yaml
   → response → parse JSON → validate against Transform schema
   → Transform(diff_bytes, files_changed, provenance.rag_few_shot_ref=ex-2025-11-04-...)
   → TierResolved(tier=llm, outcome=Applied, cost=$0.010 warm, wall_clock=8500ms)
7. RemediationOrchestrator._validate_stage6(transform, ctx):
   → SubprocessJail.run(npm_install)
   → SubprocessJail.run(npm_test)
   → SubprocessJail.run(tsc --noEmit)              ← NEW: TypecheckTypescriptSignal
   → TrustSignal(kind=typecheck.typescript, passed=True, details={"new_errors":0})
   → TrustScorer.score([build, install, tests, typecheck.typescript, lockfile_policy, cve_delta])
   → TrustOutcome(passed=True, confidence="high")
8. RemediationOutcome.kind="validated" → ingest_solved_example(outcome, store, embedder,
   origin="llm_solved")
   → embed canonical query → store.add(SolvedExample(...))
   → SolvedExampleAdded(example_id=new) event
9. remediation-report.yaml on disk; branch ready; CLI exits 0.

Total wall-clock (cassette replay): ~28 s.
Total spend: ~$0.0103 (RAG embed + cached LLM call).
```

**Parallelism extracted:**
- Recipe-tier and RAG-tier are sequential (ADR-0011 mandates serial fallback; tiers must not race).
- Inside RAG-tier, embedding and HNSW query are sequential by nature.
- Inside LLM-tier, the three cached system blocks could be loaded in parallel (`asyncio.gather` over skill_loader + instruction_template + rag_few_shot serialization) — they are, but it's microseconds.
- Validate-stage signal collectors (`build`, `install`, `tests`, `typecheck.typescript`, `lockfile_policy`, `cve_delta`) **cannot run in parallel** in Phase 4 — each writes to the same `node_modules` and the `tsc` baseline needs `npm install` first. Phase 5 owns the question of whether validate-stage signals can be re-architected to parallelize; Phase 4 stays serial.

**Caches consulted:**
1. Phase 3 `BundleBuilder.cache` — content-addressed (already in place).
2. `.codegenie/kg/embeddings.cache.sqlite` — query-text → vector (new).
3. `.codegenie/kg/plan-cache.sqlite` — `(plan_cache_key) → TierChainResult` (new; opt-in via `--plan-cache=on`, default off). Cache key = `BLAKE3(workflow.repo_sha || cve.id || plugin.version || tier_chain.digest || store.digest)`. **Disabled by default** because the LLM tier's output is non-deterministic across re-records; cassette replay already gives us reproducibility in CI. Operator-mode-only opt-in.
4. **Anthropic prompt cache (server-side)** — 5-min TTL. Hit rate depends on workflow batching cadence; goal ≥ 65%.
5. `.codegenie/typecheck/baseline-<repo-sha>.json` — pre-patch baseline error count (new).

**Serialization points (and why):**
- `_validate_stage6` is serial because signals depend on filesystem state (`node_modules`).
- TierChain is serial because ADR-0011 requires serial fallback (no race).
- All within-workflow LLM calls are serial because retries depend on prior attempt's error info.

---

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| Cassette miss in CI | `AnthropicLeafLlm` adapter `record_mode == "none"` check raises `CassetteMissing` | **No automatic recovery.** CI fails fast with a diagnostic naming the missing cassette path. `make refresh-cassettes` is the operator action. |
| ChromaDB persistent dir corrupted | `ChromaSolvedExampleStore` raises on open | Falls back to empty store; `RagTier` emits `RagMiss(reason="store_unavailable")`; LLM-tier runs from scratch with no few-shot. Operator-side `codegenie kg rebuild` (out of Phase 4 scope; ship a stub). |
| `fastembed` ONNX session fails to load (corrupt cache, OOM) | `FastembedEmbedder.__init__` raises | Worker exits at startup. **Not recoverable per-workflow** — restart worker. No silent fallback to LLM-only (would silently break the cost story). |
| Anthropic API outage (5xx, timeout, rate limit) | SDK raises `APIStatusError` | Retry once with exponential backoff inside `AnthropicLeafLlm.complete` (1s, 4s, 16s). Three retries exhausted → emit `LlmCallFailed(reason="api_outage")`; `LlmTier.attempt` returns `Failed`; orchestrator emits `RemediationOutcome.Failed`. Phase 5's `GateRunner` retry envelope is the next layer of defense; not Phase 4's job. |
| LLM returns malformed JSON | `LlmTier` Pydantic validation raises | One retry inside the tier with appended "your previous response was malformed" instruction. Second failure → `LlmTier.attempt` returns `Failed(reason="malformed_output")`. |
| `DeterministicRetargeter` refuses (substitutions outside allowlist) | `retargeter.can_retarget(...) == False` | Fall through to LLM tier with `rag_mode="few_shot"`. No failure event. |
| RAG returns 0 results above similarity floor | `store.query(...) == []` | Emit `RagMiss(reason="below_similarity_floor")`. Fall through to LLM. Expected case in early days (empty store); no recovery needed. |
| `typecheck.typescript` collector subprocess timeout (> 30 s) | `SubprocessJail` timeout | Emit `TrustSignal(kind=typecheck.typescript, passed=False, details={"timeout": True})`. Strict-AND fails the validate gate. Phase 5 owns the retry; Phase 4 fails-loud. |
| Solved-example ingest fails (chroma write error, embedding fails) | `ingest_solved_example` exception | Workflow still succeeds (the patch is written; the branch exists). Ingest failure emits `SolvedExampleIngestFailed(reason=...)` for operator triage; **does not roll back the workflow**. The cost is one missed compounding opportunity, not a wrong patch shipping. |
| Prompt-cache cold (5-min TTL expired) | `LlmResponse.cache_read_tokens == 0` | No recovery needed — workflow proceeds at higher cost. `PromptCacheMiss(reason="ttl_expired")` event emitted. Phase 13 cost ledger sees the higher per-workflow spend. |
| Cassette divergence (recorded prompt differs from live prompt at the bytes level) | `pytest-recording` filter mismatch | CI fails with `vcr.errors.CannotOverwriteExistingCassetteException`. Operator must `make refresh-cassettes` for the affected test. Forces the prompt-structure changes to be explicit. |

---

## Resource & cost profile

Concrete numbers, measured against the representative fixture:

- **Tokens per run (LLM-from-scratch, warm prompt cache):** ~3,000 input (90% cached read at 5-min TTL) + ~400 output = **~3,400 total tokens**.
- **Tokens per run (LLM-from-scratch, cold cache):** ~3,000 input (cache creation, 25% premium on first 2,000) + ~400 output = **~3,400 total tokens, billed as cache-write**.
- **Tokens per run (RAG-hit byte-applicable):** **0**. Embedding is local CPU, no LLM call.
- **Tokens per run (RAG-hit few-shot → LLM):** Same as LLM-from-scratch; few-shot is one of the cached system blocks.

- **Wall-clock per run:**
  - Recipe-hit: 18 s p50 (Phase 3 unchanged).
  - RAG-hit byte-applicable: **22 s p50 / 35 s p95**. Dominated by `npm install` + `npm test` in validate.
  - RAG-hit few-shot → LLM (cassette): **28 s p50 / 50 s p95**. Adds ~6 s cassette replay + parse.
  - RAG-hit few-shot → LLM (live, warm cache): **34 s p50 / 65 s p95**. Live Claude latency + retry budget.
  - LLM-from-scratch (live, cold cache): **42 s p50 / 90 s p95**. Cache-creation TTFT penalty.

- **Memory per worker (Phase 4 additions):**
  - `fastembed` ONNX session: ~180 MB RSS (model weights + onnxruntime).
  - `chromadb` persistent client + duckdb: ~100 MB RSS at 10K examples.
  - `anthropic` async client + connection pool: ~30 MB RSS.
  - **Phase 4 total addition: ~310 MB.** On top of Phase 3's 400 MB → ~710 MB per worker. Allows ~22 workers on a 16 GB host.

- **Storage growth rate:**
  - Solved examples: ~5 KB per `SolvedExample` (JSON-serialized transform + metadata) + 1.5 KB per embedding (384 × float32). **At 100 PRs/day, ~6.5 KB/PR × 100 = 650 KB/day or ~240 MB/year.** Three years of data fits in a single chromadb collection.
  - Cassettes: ~50 KB per recorded LLM exchange. Bench corpus of 10–50 cassettes per task class. **Negligible** (<5 MB total in repo).
  - Event log additions: Phase 4 adds ~6 new event kinds × ~200 bytes each per workflow = ~1.2 KB/workflow on top of Phase 3's stream. Zstd-compressed: ~400 bytes added per workflow.

- **Hot vs cold cost ratio:**
  - Recipe-hit: $0.0000 every time. Trivially hot.
  - RAG-hit byte-applicable: $0.0003 every time (embedding + chroma; no LLM). Trivially hot.
  - RAG-hit few-shot → LLM, warm prompt cache: $0.010. Cold: $0.017. **Ratio: 1.7×.**
  - LLM-from-scratch, warm: $0.010. Cold: $0.017. **Ratio: 1.7×.**
  - **Conclusion: prompt cache hit/miss is the dominant cost lever once a workflow falls through to LLM.** Worth optimizing batch cadence (operator-mode CLI: `codegenie remediate-batch <repo-list> --cve=...` keeps the 5-min TTL hot across consecutive workflows).

---

## Test plan

What "this design passes its tests" means concretely:

**Unit:**
- `TierChain` — given mock tiers (one returns `Applied`, one `NotApplicable`, one `Failed`), assert tier-skip semantics (recipe `Applied` → no rag/llm; recipe `NotApplicable`, rag `Applied` → no llm; etc.). Property test: tier_cap flag clamps correctly across all 3 × 4 combinations.
- `RagTier.attempt` — given a mock store with seeded examples at various similarity scores, assert routing decisions (below floor → fall-through; between floors → few-shot fall-through; above byte_applicable → retarget). Determinism test: 100 runs with the same fixture produce the same `TierAttempt.outcome`.
- `DeterministicRetargeter.can_retarget` — exhaustive table-driven test over the `PackageJsonEdit` variants; refuses on every edit type outside the allowlist.
- `FastembedEmbedder.embed` — given a fixed input string, asserts the output vector is byte-identical across two runs (model determinism). Property test: norm == 1.0 for normalized BGE outputs.
- `AnthropicLeafLlm.complete` — under `pytest-recording`, replay a recorded exchange; assert `LlmResponse.input_tokens` matches the cassette. Property test: every `system_block` with `cache="ephemeral"` produces a `{"cache_control": {"type": "ephemeral"}}` field in the SDK call (mock the SDK).
- `TypecheckTypescriptCollector` — given a fixed `SandboxRun` stub with seeded stderr, asserts `TrustSignal(passed=bool, details={"new_errors":int})` correctness.
- `ingest_solved_example` — given a mock store, asserts one `store.add` call with the expected `SolvedExample` payload.

**Integration:**
- Full E2E on `fixtures/vuln-major-bump/express-cve-2026-1234`: recipe miss → RAG miss (cold store) → LLM call (cassette replay) → validate passes → solved example ingested → second run hits RAG → produces equivalent fix at **zero LLM cost**. This is the roadmap exit criterion implemented as a test.
- Tier-cap CLI flag E2E: `--tier-cap=recipe` on a major-bump fixture → orchestrator emits `Failed(reason="tier_cap_exhausted")`.
- `make refresh-cassettes` operator path E2E (local-only; not in CI): re-records the cassettes, asserts no diff to the recorded prompts (cassette discipline holds).

**Performance regression / canaries:**
- `pytest -m bench` runs (advisory; not gating):
  - `bench_rag_tier_query_p99_under_15ms` — chroma + fastembed in-process; 10K seeded examples; 100 query iterations; assert p99 < 15 ms.
  - `bench_embedding_cache_hit_under_2ms` — second `embed(same_string)` call hits sqlite cache; assert p99 < 2 ms.
  - `bench_typecheck_typescript_under_8s` — `tsc --noEmit` on the 80-file fixture inside `SubprocessJail`; assert p95 < 8 s.
  - `bench_tier_chain_overhead_under_20ms` — synthetic tier mocks returning instantly; assert dispatch overhead < 20 ms.
- **CI nightly bench** (Phase 6.5's harness territory): runs `bench/vuln-remediation/cases/*-rag.toml` against the chroma seed corpus, asserts top-1 retrieval recall ≥ 0.9 for known-equivalent cases.

**Cassette discipline:**
- `pyproject.toml` `[tool.pytest.ini_options].vcr_record_mode = "none"` enforced. A test that records a new cassette in CI fails.
- `cassettes.lock` file with BLAKE3 per cassette; CI asserts the lock matches the on-disk cassettes (rejects un-committed re-records).
- A test (`test_no_live_anthropic_calls.py`) monkey-patches `anthropic.AsyncAnthropic.__init__` to raise; runs the full Phase 4 test suite; asserts no test fails due to that raise. Catches "the cassette is bypassed by mistake."

**Fence-CI:**
- `tests/unit/test_pyproject_fence.py` (Phase 0 already enforces): `FORBIDDEN_LLM_SDKS` includes `anthropic` for the *gather-pipeline* runtime closure. Phase 4 amends the fence to allow `anthropic` under `plugins/vulnerability-remediation--node--npm/adapters/` and `src/codegenie/transforms/` only, **NOT** under `src/codegenie/probes/`, `src/codegenie/coordinator/`, `src/codegenie/cache/`. Hard CI gate.
- `import-linter` contract amended: `src/codegenie/kg/` may import `chromadb`, `fastembed`, `onnxruntime`. The kg package may NOT import `anthropic` (separation of concerns: the kg is a deterministic store; LLM is plugin-side).

---

## Design patterns applied

| Decision (component or interface) | Pattern applied | Why this pattern *here* | Pattern *not* applied (and why) |
|---|---|---|---|
| `TierChain` recipe → RAG → LLM | **Chain of responsibility / Pipeline** | Three handlers; each can short-circuit. The chain shape is the load-bearing structural decision of Phase 4 (ADR-0011). | Strategy. There aren't three interchangeable plan strategies — they're three tiers with cost-ordered fall-through. Strategy would lose the "fall-through" semantics. |
| `SolvedExampleStore`, `Embedder`, `LeafLlm` Protocols | **Hexagonal / Ports and adapters** | Three external technology boundaries (vector DB, embedding model, LLM provider) that will get swapped in Phase 11+ (qdrant/pgvector per ADR-0017) and Phase 16 (vendor-shim per ADR-0020). Ports are the seam. | Plugin architecture. The plugin layer is one level up — `vulnerability-remediation--node--npm` is the plugin; the Phase 4 adapters live *inside* that plugin. Pluggability within the plugin is overkill (Phase 4 ships exactly one adapter each). |
| `TierAttempt`, `RecipeOutcome`, `SolvedExample`, `LlmResponse` Pydantic models | **Tagged union / sum type for state + Smart constructor + Newtype** | Phase 3's domain-modeling discipline (ADR-0033) extended. Sum types kill the "what if it's both Applied and Failed?" question at compile time. | `dict[str, Any]` payloads. The temptation in agentic systems is to keep responses as flexible dicts; we don't, because we want refactor safety. |
| `DeterministicRetargeter` substitution allowlist | **Specification pattern + Make illegal states unrepresentable** | The "can_retarget?" question is a composable yes/no business rule. The allowlist as `Final[frozenset]` makes unauthorized edit types literally impossible to retarget. | A general-purpose template engine. We deliberately don't accept anything outside the substitution allowlist — refusing is correct behavior. |
| `AnthropicLeafLlm.complete` cache-control discipline | **Adapter pattern + Capability pattern** | The Anthropic SDK's raw API shape is "pass a dict with optional `cache_control` keys" — easy to forget. The adapter promotes cache-control to a typed `CachedSystemBlock` field that every call site is forced to set. The `LlmCostBudget` capability token (passed through `PlanContext`) is checked at the leaf before any spend. | Direct SDK use. Direct use means cache_control omissions go unnoticed for weeks. |
| `@register_signal_kind("typecheck.typescript")` | **Registry pattern + Open/Closed** | Phase 3 shipped the open-registry seam. Phase 4 adds one entry. Phase 7 will add `typecheck.java`, etc. Zero edits to the kernel. | A central `dispatch_signal_kind(name)` `match` block. That's modification, not extension. |
| `.codegenie/kg/embeddings.cache.sqlite` (query-text → vector cache) | **Cache-aside / Content-addressed cache** | Embeddings are deterministic given (model, input); BLAKE3 of the input is the natural key. sqlite is the same shape Phase 3 uses for `VulnIndex`. | Per-call in-memory dict. A worker restart loses the cache; cold start is worse than necessary. |

Six explicit pattern decisions; one explicit non-applied pattern (Strategy, Plugin-within-plugin) acknowledged.

---

## Risks (top 5)

1. **Prompt-cache hit rate misses the 65% target.** If workflows on different repos arrive non-batched (one per hour rather than five per minute), the 5-min TTL evaporates and every call is cache-cold. Mitigation: ship `codegenie remediate-batch` for operator mode; Phase 13 cost ledger surfaces cache-miss rate so the design assumption is observable. The risk is to the *cost* target, not to *correctness*.
2. **`DeterministicRetargeter` is overly conservative — RAG byte-applicable hit rate stays at ~30% instead of the hoped-for 50%+.** Mitigation: the failure mode is "we paid for an LLM call we could have avoided," not "we shipped a wrong patch." The compounding-savings story still works, just at a slower asymptote. Operator-side bench `bench/vuln-remediation/cases/*-retarget.toml` measures the rate; future phases can widen the substitution allowlist with evidence.
3. **Cassette drift.** A prompt-template edit changes the recorded bytes; CI fails until cassettes are re-recorded. If re-recording isn't operator-gated, contributors will silently re-record cassettes and never run the live path. Mitigation: `make refresh-cassettes` requires `--i-understand-this-spends-tokens` flag + emits a `CassettesRefreshed` event into the audit chain; PRs touching `tests/cassettes/` require a CODEOWNERS approval.
4. **ChromaDB's single-writer constraint bites at Phase 11.** Phase 11's merge-webhook-driven `ingest_solved_example` calls may concurrently write from multiple workflow workers, and chromadb will lock. Mitigation: the Protocol is the seam — ADR-0017's resolution to pgvector is one adapter swap at Phase 11. Phase 4 ships with `store.add` declared `async` but with documented "concurrent writes are not safe in chromadb adapter; serialize through a write-lock in Phase 11."
5. **`typecheck.typescript` adds 4–8 s p95 to validate-stage; Phase 4 wall-clock targets get tight.** If the signal turns out to be too slow on monorepo fixtures, we either skip it (un-doing ADR-0037 intent) or accept higher latency. Mitigation: `--skip-typecheck` flag (operator-mode-only; emits a `TypecheckSkipped(reason=...)` event so the post-merge audit can see what was bypassed); the default stays "on."

---

## Acknowledged blind spots

What this lens deprioritized:

- **Adversarial inputs to the embedder / vector store.** A poisoned `SolvedExample` (committed by a malicious contributor, or returned by a compromised remote KG once Phase 11 ships) could steer the LLM toward bad patches via few-shot manipulation. Security-first design owns this; I assumed in-tree solved examples + CODEOWNERS protection are sufficient at Phase 4.
- **Cost-cap circuit breakers per workflow.** Phase 13's `BudgetEnforcer` is the right home; I emit the cost events but don't *enforce* a per-workflow cap. A runaway LLM call (max_output_tokens=2000 budget breach via retry storm) could rack up tokens before Phase 5 cuts it off. The retry-3 default in `AnthropicLeafLlm` is the proximate guard; the architectural answer is Phase 13.
- **Multi-vendor LLM redundancy.** ADR-0020 stays deferred. If Anthropic has a 4-hour outage during a portfolio scan, every workflow that falls through to LLM-tier fails. Mitigation: the `LeafLlm` Protocol is the seam; a `MockLeafLlm` for tests + a future `OpenAILeafLlm` adapter slot in trivially. Phase 4 ships one adapter.
- **Solved-example provenance and lineage.** When the LLM emits a Transform citing `provenance.rag_few_shot_ref=ex-123`, and `ex-123` was itself emitted by an earlier LLM call, we have a transitive provenance chain. Phase 4 records the immediate parent; tracing the *full* chain back to the first human-merged example is Phase 15's territory.
- **Operator UX for inspecting why a particular tier won/lost.** Phase 13.5 (operator portal) is the right home. Phase 4 emits the events; surfacing them is later.
- **Cross-language `typecheck.*` adapters.** Only `typecheck.typescript` ships in Phase 4. Java/Rust/Go are Phase 7+ territory and ADR-0037 says so.
- **Provenance refuse-mode amplification.** Phase 3's `Applicability.NotApplicable(reason=CVE_NOT_IN_APP_LAYER)` shape stays unchanged in Phase 4 — the LLM tier inherits the same refusal. I deliberately *did not* try to make the LLM "decide" provenance; that's exactly the LLM-as-control-flow pattern ADR-0008 rejects.

---

## Open questions for the synthesizer

1. **Cassette discipline ownership.** Who owns the `make refresh-cassettes` operator workflow — Phase 4's `Makefile` or Phase 6.5's eval harness? They overlap (Phase 6.5 reads `cassette_blake3` per case from `case.toml`). My read: Phase 4 owns the `pytest-recording` plumbing; Phase 6.5 owns the bench-case-level integrity pinning. Synthesizer should confirm.
2. **`--plan-cache=on` opt-in default.** I default the `.codegenie/kg/plan-cache.sqlite` off because LLM-tier output is cassette-dependent (re-record changes the cache content). Should the synthesizer push for `--plan-cache=on` by default to maximize warm-start savings on portfolio scans? It's a token-economy vs. reproducibility tradeoff.
3. **Anthropic SDK version pinning vs. cassette stability.** Anthropic SDK version bumps can change response field names; cassettes break silently. Should we pin `anthropic>=0.x,<0.y` strictly + a `cassette_compatibility_test` that smoke-tests SDK parsing against a frozen cassette? I lean yes.
4. **`fastembed` model upgrade path.** When BGE-small-v2 ships, every embedding in the store is invalid (different vector space). Migration is "re-embed everything." For Phase 4 this is a one-line script; at Phase 11+ at portfolio scale, it's a longer-running batch job. Should the `SolvedExampleStore` carry `embedding_model_digest` and refuse queries on mismatch (with a "rebuild required" error), or auto-rebuild on detect? I lean refuse + explicit operator-side rebuild.
5. **Where exactly does `typecheck.typescript` live — plugin or core?** ADR-0037 says "per-language plugins register their own `typecheck.<lang>` collector." I put it under `plugins/.../adapters/ts_typecheck_signal.py`. The synthesizer should confirm this isn't shared core code that *all* future Node plugins (e.g., Phase 7's `distroless-migration--node--npm`) need to re-import; if it is, it belongs at `plugins/vulnerability-remediation--node--*/adapters/` (the base plugin per ADR-0031's wildcard convention) so Phase 7 inherits it via `extends`.
6. **Tier-skip-rate measurement.** "≥90% tier-skip rate after 90 days" needs a measurement contract — does it come from Phase 13's cost ledger projecting events from Phase 4's `TierResolved` stream? Phase 6.5's eval harness re-running historical fixtures? Both? I'd settle for "Phase 4 emits the events; whoever wants to measure projects them."
