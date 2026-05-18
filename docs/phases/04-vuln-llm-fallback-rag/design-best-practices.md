# Phase 04 — Vuln remediation: LLM fallback + solved-example RAG: Best-practices design

**Lens:** Best practices — idiomatic, maintainable, conventional, well-tested.
**Designed by:** Best-practices design subagent
**Date:** 2026-05-18

---

## Lens summary

This design optimizes for the next engineer reading the diff cold. Phase 4 lands the **second tier** of ADR-0011's `Recipe → RAG → LLM` chain inside the existing plugin (`plugins/vulnerability-remediation--node--npm/`), reuses every Phase-3 spine artifact (`RemediationOrchestrator`, `TrustScorer`, `Transform`, `ApplyContext`, `RecipeEngine`, `EventLog`, `SubprocessJail`, `VulnIndex`), and adds exactly two new in-tree top-level packages: `src/codegenie/rag/` (vector store + retrieval, with no plugin coupling) and `src/codegenie/llm/` (a small Anthropic adapter behind a `LeafLLM` Protocol). Everything else is a plugin-local file. LangGraph is used **only** to wrap the single `LlmReplanner` leaf node so Phase 6's later state-machine refactor inherits the topology — it does not own dispatch, retry, or any pipeline shape that already lives in Phase 3 code.

Deprioritized: peak performance (we choose in-process `chromadb` over `qdrant` Docker; local `sentence-transformers` over Voyage remote; ~1–3 s p50 cold-start cost is acceptable), threat-modeling of supplier-supply-chain attacks on the LLM SDK (Phase 16), and any speculative "second LLM provider" abstraction beyond what `LeafLLM` Protocol already gives us. We pay no tax for hypothetical futures; we pay the tax exactly when ADR-0020 un-defers.

---

## Conventions honored

- **No LLM in the gather pipeline → ADR-0005.** `src/codegenie/rag/`, `src/codegenie/llm/`, and the plugin's `recipes/llm_replan.py` are all banned from `src/codegenie/probes/`, `src/codegenie/coordinator/`, `src/codegenie/cache/`, `src/codegenie/output/`, `src/codegenie/schema/` by the existing `import-linter` contract (Phase 3 ADR-0009 / ADR-0011 already wire this fence; we add Phase 4's new modules to the **allow-list of LLM-touching modules**, not the forbidden set). Existing pytest fence (`tests/unit/test_pyproject_fence.py`) is **not** widened to admit `anthropic` into the pipeline closure; instead, `anthropic` is admitted only inside `[project.optional-dependencies] llm` and is wrapped by a runtime import barrier in `src/codegenie/llm/anthropic_adapter.py`.
- **Facts, not judgments → §2.2.** The leaf agent's prose output is never trusted. Only its produced `Transform` (diff bytes) is consumed; the prose goes to the event log for observability. Confidence is computed by `TrustScorer.score(signals)` strict-AND on objective signals (`build`, `install`, `tests`, `lockfile_policy`, `cve_delta`, **`typecheck.node`** newly registered). LLM self-confidence is logged and **discarded** before scoring (ADR-0008).
- **Extension by addition → §2.5.** The diff for Phase 4 touches: (a) two new top-level packages (`rag/`, `llm/`); (b) new files inside the existing `vulnerability-remediation--node--npm` plugin (`recipes/rag_match.py`, `recipes/llm_replan.py`, `tccm.yaml` entries under `provides:`); (c) one new `@register_signal_kind("typecheck.node")` registration (additive on Phase 3's open registry, ADR-0037); (d) one new ADR amendment to `ALLOWED_BINARIES` admitting `tsc` (`node_modules/.bin/tsc`). **Zero edits to `RemediationOrchestrator`, `TrustScorer`, `RecipeEngine` Protocol, `Transform` ABC, `ApplyContext`, `EventLog`, `SubprocessJail`, `PluginRegistry`, or the kernel `Plugin` Protocol.** A CI fence (Phase 3's `tests/fence/test_kernel_frozen.py`) asserts this.
- **Plugin architecture (ADR-0031) → all work lands in `plugins/vulnerability-remediation--node--npm/` plus the two new top-level packages that are plugin-agnostic substrates.** No new plugin is created — Phase 4 is the same task class, same language, same build tool. RAG and LLM are **substrates** (like `SubprocessJail` is) consumed by plugin recipes through Protocols. Phase 7's distroless plugin will register its own `Recipe`s against the same substrates without editing them.
- **Domain modeling discipline (ADR-0033) → §"Domain types" below.** Every new identifier is a `NewType`; every state machine that ships is a Pydantic discriminated union with exhaustive `match` + `assert_never`; the `RecipeOutcome` Phase 3 already ships gains two non-LLM variants (`MatchedFromRag`, `ReplannedByLlm`) by additive union widening — not by `Optional[X]` fields on existing variants.
- **Recipe → RAG → LLM-fallback decision chain (ADR-0011) → the plugin's subgraph already has the four-node shape per Phase 3 final design.** Phase 4 fills the previously-stub `rag_match` and `llm_replan` nodes. Decision order, transition predicates, and the `Step_Emitter` final node are unchanged — they are the contract Phase 3 froze.
- **Objective signals only (ADR-0008) → see "Facts, not judgments" above** and `TrustScorer` extension via `@register_signal_kind("typecheck.node")`. The LLM never sees the gate.

---

## Goals (concrete, measurable)

- **Public API surface (count):** ≤ 8 net-new public symbols.
  - `rag.SolvedExampleStore` (smart-constructor `SolvedExampleStore.open(path: Path) -> SolvedExampleStore`).
  - `rag.SolvedExample` (Pydantic, `frozen=True`, `extra="forbid"`).
  - `rag.Query` (Pydantic).
  - `rag.RetrievalOutcome` (sum type: `RagHit | RagMiss | RagDegraded`).
  - `llm.LeafLLM` (Protocol).
  - `llm.AnthropicLeafLLM` (concrete adapter).
  - `llm.LeafLLMRequest`, `llm.LeafLLMResponse` (Pydantic).
- **Test coverage target:** ≥ 90% line / 80% branch on `src/codegenie/rag/` and `src/codegenie/llm/`. 95% / 90% on the plugin's two new recipe files. Phase-wide coverage gate (Phase 0's `--cov-fail-under=85`) cannot regress.
- **Cyclomatic complexity ceiling per module:** ≤ 10 per function (ruff `C901` enabled). The `LlmReplanRecipe.run` function in particular is checked by a unit-level radon/lizard assertion in CI.
- **Number of net-new top-level packages:** **2** — `src/codegenie/rag/`, `src/codegenie/llm/`. Anything else is either inside the plugin or inside an existing top-level package.
- **Lines of plain Python vs framework-coupled code:** ~85% plain Python, ~10% Pydantic, ~5% LangGraph-touched. LangGraph appears only in `plugins/vulnerability-remediation--node--npm/recipes/llm_replan.py` to wrap a single leaf invocation; the rest of the file is plain Python.
- **Cassette discipline:** 100% of CI runs replay frozen cassettes; live API calls are gated behind `CODEGENIE_LIVE_LLM=1` and refuse to run in CI by checking `os.environ.get("CI")`.
- **Determinism property:** given `(repo_snapshot_sha, cve_record_digest, plugin_version, recipe_version, vuln_index_digest, store_digest, cassette_id)`, the produced `Transform` and event sequence are byte-identical (modulo timestamps + `workflow_id`). Property-tested across 50 runs.
- **`typecheck.node` signal lands and is strict-AND-folded.** A regression in the type-shape after an LLM replan **fails** the gate without the build or tests catching it (single fixture exercised in `tests/integration/test_typecheck_signal_catches_signature_drift.py`).
- **Zero edits to Phase 0/1/2/3 code outside the allow-list.** Asserted by `tests/fence/test_kernel_frozen.py`.

---

## Architecture

```
                       codegenie remediate <repo> --cve <id>
                                       │
                                       ▼ (Phase 3 entrypoint unchanged)
            ┌──────────────────────────────────────────────────────────────┐
            │ src/codegenie/transforms/orchestrator.py                      │
            │   RemediationOrchestrator (Phase 3 — UNCHANGED)              │
            │     Stage 1 Resolve → Stage 2 Bundle → Stage 3 Plan          │
            │     → Stage 4 Apply → Stage 5 (Phase 6 territory)            │
            │     → Stage 6 Validate (Phase 5 wraps this)                  │
            └────────────────────────────────┬─────────────────────────────┘
                                             │
                                             ▼
            ┌──────────────────────────────────────────────────────────────┐
            │ plugins/vulnerability-remediation--node--npm/                 │
            │   subgraph/                                                   │
            │     Recipe_Matcher  ──┐  (Phase 3, unchanged)                 │
            │                       │  hit → Step_Emitter                   │
            │                       │                                       │
            │     Rag_Retriever     ▼  (Phase 4, NEW)                       │
            │                       │  hit → Llm_Replanner                  │
            │                       │       (as few-shot context)           │
            │                       │  miss → Llm_Replanner (no context)    │
            │                       │  degraded → Step_Emitter(escalate)    │
            │                       │                                       │
            │     Llm_Replanner     ▼  (Phase 4, NEW; wraps LeafLLM)        │
            │                       │  applied → Step_Emitter               │
            │                       │  refused → Step_Emitter(escalate)     │
            │                       ▼                                       │
            │     Step_Emitter         (Phase 3, unchanged)                 │
            │                                                               │
            │   recipes/                                                    │
            │     lockfile_semver_bump.py     (P3, unchanged)               │
            │     peer_dep_conflict.py        (P3, unchanged)               │
            │     transitive_overrides.py     (P3, unchanged)               │
            │     major_bump_refuse.py        (P3, unchanged)               │
            │     rag_match.py                (P4, NEW)                     │
            │     llm_replan.py               (P4, NEW)                     │
            │     typecheck_signal.py         (P4, NEW — registers          │
            │                                  typecheck.node SignalKind)   │
            │   tccm.yaml                     (P4 adds provides:            │
            │                                  rag_capabilities,            │
            │                                  llm_capabilities,            │
            │                                  typecheck_signals)           │
            └─────────────────┬──────────────────────────────┬──────────────┘
                              │                              │
                              ▼                              ▼
          ┌──────────────────────────────┐    ┌──────────────────────────────────┐
          │ src/codegenie/rag/  [P4 NEW] │    │ src/codegenie/llm/  [P4 NEW]     │
          │   store.py                   │    │   protocol.py                    │
          │     SolvedExampleStore        │    │     LeafLLM Protocol             │
          │       .open(path)            │    │     LeafLLMRequest / Response    │
          │       .add(example)          │    │   anthropic_adapter.py           │
          │       .query(q) → Outcome    │    │     AnthropicLeafLLM             │
          │   embedding.py               │    │       (anthropic.Anthropic)      │
          │     SentenceTxEmbedder        │    │   cassettes.py                   │
          │       (sentence-transformers │    │     pytest-recording config      │
          │        local model)          │    │     scrubbing + replay rules     │
          │   models.py                  │    │   errors.py                      │
          │     SolvedExample, Query,    │    │     LeafLLMError                 │
          │     RagHit, RagMiss,         │    │     RateLimitExceeded            │
          │     RagDegraded              │    │     ContextWindowExceeded        │
          │     EmbeddingVector NewType  │    │     LeafLLMRefused (typed)       │
          │   confidence.py              │    │                                  │
          │     similarity-threshold-    │    └──────────────────────────────────┘
          │     to-AdapterConfidence     │                   ▲
          │     mapping (objective only) │                   │ (LangGraph wraps
          └──────────────┬───────────────┘                   │  this one node only)
                         │                                   │
                         └────────────────────┬──────────────┘
                                              │
                                              ▼
          ┌──────────────────────────────────────────────────────────────┐
          │ src/codegenie/transforms/trust_scorer.py  (P3 — extended via  │
          │   @register_signal_kind("typecheck.node"))                    │
          │                                                               │
          │   New signal: TypecheckSignal                                 │
          │     kind = SignalKind("typecheck.node")                       │
          │     passed = (tsc --noEmit exit_code == 0)                    │
          │     details = {"new_errors": int, "stderr_head": str}         │
          │                                                               │
          │   Wired via SubprocessJail.run(["./node_modules/.bin/tsc",    │
          │                                  "--noEmit"]) — Phase 3       │
          │   SubprocessJail Port unchanged.                              │
          └──────────────────────────────────────────────────────────────┘

          ┌──────────────────────────────────────────────────────────────┐
          │ .codegenie/events/ (Phase 3 EventLog, additive event variants)│
          │   workflow-internal/<workflow_id>.jsonl.zst:                  │
          │     RagQueried, RagHitConsumed, RagMissEscalated,             │
          │     LeafLlmRequested, LeafLlmResponded, LeafLlmRefused,       │
          │     TypecheckSignalEmitted                                    │
          │   spanning/append.jsonl.zst:                                  │
          │     SolvedExampleHarvested (new example added to store)       │
          │     LlmCostAccrued (input/output tokens × model rate)         │
          └──────────────────────────────────────────────────────────────┘

          ┌──────────────────────────────────────────────────────────────┐
          │ .codegenie/rag/                                                │
          │   store.sqlite3        (chromadb persistent client; in-tree)  │
          │   manifest.json        (store digest; cache-key contribution) │
          │   solved-examples/*.yaml  (canonical YAML source-of-truth;    │
          │                            sqlite is the derived index)       │
          └──────────────────────────────────────────────────────────────┘
```

The bullet for "additive surfaces only" is **everything outside the four boxes labeled NEW or P4**. Phase 5's already-merged design wraps `_validate_stage6` — that function gains one new signal collector (`collect_typecheck_signal(...)`) by addition into the existing collector list, not by change to the loop shape.

---

## Components

### 1. `SolvedExampleStore` (`src/codegenie/rag/store.py`)
- **Purpose:** Single source of truth for solved-example retrieval. One class; one storage backend (chromadb persistent client); one query method returning a typed sum.
- **Public interface:**
  ```python
  class SolvedExampleStore:
      @classmethod
      def open(cls, path: Path) -> "SolvedExampleStore": ...      # smart constructor
      def add(self, example: SolvedExample) -> SolvedExampleId: ...
      def query(self, q: Query, *, top_k: int = 5) -> RetrievalOutcome: ...
      def digest(self) -> StoreDigest: ...                          # cache-key input
      def close(self) -> None: ...
  ```
- **Internal design:** thin wrapper over `chromadb.PersistentClient(path=...)`. Embeddings computed by `SentenceTxEmbedder` injected at construction (dependency inversion). Two-table layout inside chromadb: one collection per `(task_class, language, build_tool)` slice — the slice is part of the cache key, so a vuln-remediation--node--npm worker never sees a distroless-migration example. **Files-on-disk are canonical:** each example lives at `.codegenie/rag/solved-examples/<sha256>.yaml`; sqlite is a derived index that can be rebuilt from the YAML directory. This means git can review additions, diff is human-readable, and a corrupted sqlite is a `codegenie rag rebuild` away.
- **Dependencies:** `chromadb` (vector store), `sentence-transformers` (embeddings), `pydantic` (models). **Not `qdrant-client`** — qdrant requires running a Docker server; we prefer the in-process choice for maintainability. The next engineer can `python -m codegenie.rag.inspect path/to/store` without docker-compose.
- **Where it lives:** `src/codegenie/rag/store.py`. The `rag/` package is **deliberately plugin-agnostic** — it has no knowledge of `vulnerability-remediation`, `npm`, `Node`. Plugins pass a `Query` and consume a `RetrievalOutcome`; the store does not know what task class is asking.
- **Tradeoffs accepted:** chromadb has a smaller community than qdrant; in-process model load is ~80 MB cold; query latency 5–20 ms — slower than qdrant's 1–3 ms. We accept these because the alternative is docker-compose in development, a contributor barrier that costs more than the latency saves.

### 2. `SentenceTxEmbedder` (`src/codegenie/rag/embedding.py`)
- **Purpose:** Produce `EmbeddingVector` for a free-text query or a stored example. One implementation, behind a Protocol for testability.
- **Public interface:**
  ```python
  class Embedder(Protocol):
      def embed(self, text: str) -> EmbeddingVector: ...
      @property
      def dim(self) -> int: ...
      @property
      def model_id(self) -> ModelId: ...

  class SentenceTxEmbedder:
      def __init__(self, model: str = "all-MiniLM-L6-v2", cache_dir: Path | None = None) -> None: ...
  ```
- **Internal design:** lazy load of `sentence_transformers.SentenceTransformer` (first `embed()` call materializes the model — Phase 0's `tests/unit/test_pyproject_fence.py` is updated to admit `sentence_transformers` outside the gather closure). `model_id` is part of `StoreDigest` so switching models invalidates the cache deterministically.
- **Dependencies:** `sentence-transformers` (chosen over Voyage remote because: zero API key management, deterministic across machines once the model file is pinned, no rate-limit-induced flakiness in CI). We accept the one-time ~80 MB model download — pre-commit hook caches it.
- **Where it lives:** `src/codegenie/rag/embedding.py`. Behind an `Embedder` Protocol so a Voyage adapter can be added later without touching `SolvedExampleStore`.
- **Tradeoffs accepted:** local embeddings are coarser than Voyage's `voyage-code-2` for code-specific tokens; calibration is "good enough" for Phase 4's small corpus (<200 solved examples expected by Phase 7). When the corpus crosses 1000 examples or recall calibration shows a gap, a Voyage adapter lands in a follow-up ADR.

### 3. `LeafLLM` Protocol + `AnthropicLeafLLM` (`src/codegenie/llm/`)
- **Purpose:** The only place in the codebase that talks to a hosted LLM. One Protocol, one adapter.
- **Public interface:**
  ```python
  class LeafLLM(Protocol):
      def invoke(self, request: LeafLLMRequest) -> LeafLLMResponse: ...

  class LeafLLMRequest(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      system: str
      user: str
      few_shot: list[SolvedExample] = Field(default_factory=list)
      max_tokens: TokenCount
      model: ModelId        # NewType; must be in the pinned-models registry

  class LeafLLMResponse(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      text: str
      tokens_in: TokenCount
      tokens_out: TokenCount
      model: ModelId
      stop_reason: Literal["end_turn", "max_tokens", "refusal"]
  ```
- **Internal design:** `AnthropicLeafLLM.__init__(self, client: anthropic.Anthropic)` — client is injected (dependency inversion; tests pass a mock or pytest-recording-driven instance). The adapter translates `LeafLLMRequest` to the SDK's call shape and back. **No retry logic** — that's `LlmReplanRecipe`'s job and ultimately Phase 5's `GateRunner`. **No prompt-engineering layer** — system+user are passed through verbatim; prompt construction is the plugin's responsibility (the LLM substrate shouldn't know what task class is using it).
- **Dependencies:** `anthropic` Python SDK (pinned; in `[project.optional-dependencies] llm`). The fence test admits this module *only* outside the gather closure.
- **Where it lives:** `src/codegenie/llm/anthropic_adapter.py`. Cassette-replay glue lives in `src/codegenie/llm/cassettes.py` — pytest-recording's VCR config, request scrubbing (strip `x-api-key`), and the directory layout.
- **Tradeoffs accepted:** A single hosted-LLM adapter, no abstraction over Claude vs GPT-4 right now. ADR-0020 is deferred; we don't pay for that abstraction until the deferral resolves. Reversal cost is small: when ADR-0020 lands, `LeafLLM` Protocol already exists and a second adapter is additive.

### 4. `RagMatchRecipe` (`plugins/vulnerability-remediation--node--npm/recipes/rag_match.py`)
- **Purpose:** Query the solved-example store for the current `(cve, repo_context)` and produce a `RetrievalOutcome` for the subgraph to dispatch on.
- **Public interface:** standard plugin recipe shape (Phase 3 contract):
  ```python
  class RagMatchRecipe:
      def __init__(self, store: SolvedExampleStore, embedder: Embedder) -> None: ...
      def applies_to(self, ctx: PluginContext, cve: CveRecord) -> bool: ...
      def run(self, ctx: PluginContext, cve: CveRecord) -> RecipeOutcome: ...
  ```
  Returns `RecipeOutcome` sum-type variants `MatchedFromRag(example: SolvedExample, similarity: Similarity)` (new variant, additive) or `RecipeOutcome.Skipped(reason="rag_miss" | "rag_degraded")`.
- **Internal design:** the `Query` is constructed from `(cve.affected_package, cve.advisory_id, repo_context.framework_signals, plugin_id)` and passed through. The recipe is a thin orchestrator: query → outcome → typed result. **Similarity-to-confidence mapping lives in `rag/confidence.py`, not here** — it's an objective signal that the `TrustScorer` could read independently. The recipe is dumb on purpose.
- **Dependencies:** `rag.SolvedExampleStore`, `rag.Embedder`, the four Phase-3 `Adapter`s already wired (`NpmDepGraph` etc.) for query-context construction.
- **Where it lives:** plugin-local under `plugins/vulnerability-remediation--node--npm/recipes/`. **Cannot be moved to a shared location** because the query construction is plugin-specific.
- **Tradeoffs accepted:** the similarity threshold (default `0.78`) is a hand-calibrated number, not a learned one. Calibration happens against `bench/vuln-remediation/cases/` in Phase 6.5 and tightens over time. Until then, threshold lives in YAML (`plugin.yaml` → `recipes.rag_match.similarity_threshold`) so changing it doesn't require a code edit.

### 5. `LlmReplanRecipe` (`plugins/vulnerability-remediation--node--npm/recipes/llm_replan.py`)
- **Purpose:** Invoke the leaf LLM with `RepoContext` + matched Skill + optional few-shot from RAG; produce a candidate `Transform` (lockfile-and-source patch); refuse if the model returns nothing useful.
- **Public interface:** plugin recipe shape (Phase 3 contract). Returns `RecipeOutcome.ReplannedByLlm(transform: NpmLockfileTransform, response_id: LeafLlmResponseId)` (new variant, additive) or `RecipeOutcome.Skipped(reason="llm_refused" | "llm_budget_exhausted")`.
- **Internal design:** a **minimal LangGraph subgraph** wraps the `LeafLLM` invocation purely so Phase 6's state-machine refactor inherits the topology:
  ```python
  # llm_replan.py — the only LangGraph touchpoint in Phase 4
  from langgraph.graph import StateGraph, END

  class _LlmReplanState(BaseModel):
      model_config = ConfigDict(frozen=False, extra="forbid")
      request: LeafLLMRequest
      response: LeafLLMResponse | None = None
      transform: NpmLockfileTransform | None = None
      refusal: LlmRefusal | None = None

  def _build_graph(llm: LeafLLM) -> CompiledGraph:
      g = StateGraph(_LlmReplanState)
      g.add_node("invoke", lambda s: s.model_copy(update={"response": llm.invoke(s.request)}))
      g.add_node("parse", _parse_diff_from_response)
      g.add_node("validate_shape", _validate_lockfile_transform_shape)
      g.set_entry_point("invoke")
      g.add_edge("invoke", "parse")
      g.add_edge("parse", "validate_shape")
      g.add_edge("validate_shape", END)
      return g.compile()
  ```
  Three nodes, no conditional edges, no checkpointer. The graph is *flat* on purpose — its only job is to be a callable that Phase 6's compiler can subsume as a sub-graph. **No prompt-construction logic in the graph nodes** — prompt building is a pure function (`_build_prompt(cve, ctx, few_shot) -> LeafLLMRequest`) tested independently.
- **Dependencies:** `llm.LeafLLM`, `rag.SolvedExample`, `langgraph` (minimal). The graph's compile happens once at plugin import; subsequent runs reuse it.
- **Where it lives:** plugin-local.
- **Tradeoffs accepted:** introducing `langgraph` as a dependency at Phase 4 is one phase earlier than the roadmap originally suggested (Phase 6 introduces LangGraph as the runtime). We do this because the leaf-agent topology is the canonical use-case for LangGraph in this codebase and the cost is one `import` per process. Phase 6's state-machine refactor will lift this exact graph (via `g.add_subgraph(...)`).

### 6. `TypecheckSignalCollector` (`plugins/vulnerability-remediation--node--npm/recipes/typecheck_signal.py`)
- **Purpose:** Register the first `typecheck.*` `SignalKind` per ADR-0037; emit a `TypecheckSignal` from a single `tsc --noEmit` invocation inside `SubprocessJail`.
- **Public interface:** a function `collect_typecheck_node_signal(jail: SubprocessJail, ctx: ApplyContext) -> TrustSignal` plus a module-level `@register_signal_kind("typecheck.node")` line. **No new public class**; this is signal-collector glue.
- **Internal design:** wraps `jail.run([repo / "node_modules/.bin/tsc", "--noEmit", "--pretty", "false"], cwd=repo, allow_network=False, timeout_s=120)`. Parses stderr/stdout for the `Found N errors` summary. Returns `TrustSignal(kind=SignalKind("typecheck.node"), passed=(n == 0), details={"new_errors": n, "stderr_head": stderr[:500]})`. The `_validate_stage6` collector loop in `RemediationOrchestrator` is **not edited**; the new collector is appended via a registry that already exists for that purpose in Phase 3. Adding the binary `tsc` to `ALLOWED_BINARIES` is a one-line ADR-amendment file per Phase 3 ADR-0012's pattern (`docs/phases/04-vuln-llm-fallback-rag/ADRs/0XYZ-amend-allowed-binaries-tsc.md`).
- **Dependencies:** Phase 3 `SubprocessJail`, `TrustSignal`, `@register_signal_kind`. **Nothing else.**
- **Where it lives:** plugin-local. The reason: `tsc` is a Node-toolchain binary specific to this plugin's scope. A Phase 7 distroless migration that does not run `tsc` does not register this signal.
- **Tradeoffs accepted:** `tsc --noEmit` is binary (passes / fails); fine-grained per-file granularity is deferred to Phase 12 per ADR-0037 §Consequences. We do not pay for that today.

### 7. `SolvedExample` model (`src/codegenie/rag/models.py`)
- **Purpose:** The canonical Pydantic shape of a stored solved example.
- **Public interface:**
  ```python
  class SolvedExample(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      example_id: SolvedExampleId
      task_class: TaskClass
      language: Language
      build_system: BuildSystem
      cve_id: CveId | None        # None for non-vuln examples (Phase 7+)
      affected_package: PackageId | None
      from_version: SemverRange | None
      to_version: SemverRange | None
      problem_summary: str        # human prose; <= 2000 chars
      solution_diff: bytes        # the actual diff
      solution_explanation: str   # short rationale, <= 1000 chars
      provenance: SolvedExampleProvenance   # sum type — Harvested / HandCurated / Imported
      created_at: datetime
      validated_at: datetime | None
      bench_score: BenchScore | None        # forward-ref to Phase 6.5
  ```
- **Internal design:** parse path is `SolvedExample.from_yaml(path: Path) -> Result[SolvedExample, ParseError]` (smart constructor returning Phase-3's `Result` type — same shape as `PluginScope.parse`).
- **Tradeoffs accepted:** the model is "wide" (12 fields); we accept this because the alternative is a `metadata: dict[str, Any]` escape hatch and that violates ADR-0033.

---

## Data flow

End-to-end run of a Phase 4 workflow on a Node.js repo with a CVE that Phase 3 cannot mechanically patch (e.g., a major-version bump that requires call-site rewrites):

1. **CLI entry.** `codegenie remediate <repo> --cve CVE-2025-XXXXX` invokes `RemediationOrchestrator.run(...)` (Phase 3 unchanged).
2. **Stage 1 Resolve.** `PluginResolver` picks `vulnerability-remediation--node--npm`. *(No change.)*
3. **Stage 2 Bundle.** `BundleBuilder` builds the `ConcreteBundle` from the plugin's TCCM. The TCCM now declares `requires: rag_capabilities, llm_capabilities` and `provides: typecheck_signals` — the resolver validates that the active environment satisfies both, otherwise it short-circuits with a typed error (no LLM substrate? → escalate to universal HITL fallback). *(Additive TCCM change; resolver code unchanged.)*
4. **Stage 3 Plan — Recipe_Matcher node.** Phase 3 deterministic recipes try first. If `NpmLockfileSemverBumpRecipe.applies_to(...)` returns `True` and produces an `Applied(...)`, the subgraph short-circuits to `Step_Emitter`. **The LLM is not invoked.** This is ADR-0011's cheap path.
5. **Stage 3 Plan — Rag_Retriever node.** If recipe miss, `RagMatchRecipe.run(...)` queries `SolvedExampleStore`. Three outcomes:
   - `MatchedFromRag(example, similarity=0.91)` → `LlmReplanner` is invoked with the example as few-shot.
   - `Skipped(reason="rag_miss")` → `LlmReplanner` is invoked without few-shot.
   - `Skipped(reason="rag_degraded")` (sentence-transformers model unavailable, or store sqlite corrupt) → `Step_Emitter(escalate)` → universal HITL fallback.
6. **Stage 3 Plan — Llm_Replanner node.** `LlmReplanRecipe.run(...)` invokes the leaf LLM via the three-node mini-graph. The graph's `validate_shape` node parses the response into an `NpmLockfileTransform` candidate or returns `LlmRefused`. Either way, an event lands on the workflow-internal stream.
7. **Stage 4 Apply.** `Transform.apply(repo)` writes the diff onto a temp worktree. *(Phase 3 unchanged.)*
8. **Stage 6 Validate.** Inside `_validate_stage6`, the collector loop now includes `collect_typecheck_node_signal(jail, ctx)`. The signal list passed to `TrustScorer.score(...)` becomes: `[BuildSignal, InstallSignal, TestSignal, LockfilePolicySignal, CveDeltaSignal, TypecheckSignal]`. Strict-AND across all six. If `typecheck.node` fails (e.g., LLM hallucinated a method that doesn't exist on the new API), the gate fails *before* tests get a chance to run, saving sandbox seconds.
9. **Outcome.** If `TrustOutcome.passed`, the orchestrator writes `remediation-report.yaml`, emits a `BenchReplayable` spanning event, and (post-merge in Phase 11) the `SolvedExampleHarvester` writes the successful diff back into `SolvedExampleStore` for future RAG hits. **Phase 4 ships the harvester as a separate CLI** (`codegenie rag harvest <workflow_id>`) and does NOT auto-harvest in Phase 4 — auto-harvest waits for Phase 11's post-merge webhook.

Where convention shines through:
- Same probe contract; same plugin contract; same `RemediationOrchestrator`. The change is **purely additive** at every layer.
- Same Pydantic model discipline (`frozen=True`, `extra="forbid"`).
- Same `Result[T, E]` sum-type for smart constructors.
- Same `@register_*` decorator family pattern.

---

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| `chromadb` sqlite file corrupted | `SolvedExampleStore.open()` raises `StoreCorrupted` (typed); recovery rebuilds the index from `.codegenie/rag/solved-examples/*.yaml` source-of-truth | `codegenie rag rebuild` CLI; emits `SolvedExampleStoreRebuilt` spanning event |
| `sentence-transformers` model file missing | `SentenceTxEmbedder.embed()` first call raises `ModelNotPresent` (typed) | Fall back to `RagDegraded`; LLM invoked without few-shot; spanning event `EmbedderUnavailable` emitted |
| `anthropic.RateLimitError` | `AnthropicLeafLLM.invoke()` raises `RateLimitExceeded` (typed) | Phase 5's three-retry envelope owns retry policy; Phase 4 emits typed error and returns to caller |
| `anthropic.APIStatusError(401)` | `AnthropicLeafLLM.invoke()` raises `LeafLLMAuthError` (typed) | Hard fail with exit code 9 (operator action required); does NOT retry |
| LLM returns malformed diff (not valid `package.json` patch) | `_validate_lockfile_transform_shape` node raises `LeafLLMRefused(reason="malformed_diff")` (typed) | `LlmReplanRecipe.run()` returns `RecipeOutcome.Skipped(reason="llm_refused")`; subgraph dispatches to `Step_Emitter(escalate)`; HITL via universal fallback |
| `tsc --noEmit` reports errors after LLM replan | `TypecheckSignal.passed = False` | Strict-AND fail; `TrustOutcome.failing = ["typecheck.node"]`; Phase 5 (when wrapped) consumes `prior_attempts` and re-invokes `LlmReplanner` with the typecheck error log in context |
| Cassette miss in CI (no recording for new test) | `pytest-recording` raises `CannotOverwriteExistingCassetteError` | Test fails; engineer runs `pytest --record-mode=once tests/integration/test_llm_replan_X.py` locally with `CODEGENIE_LIVE_LLM=1`; commits the cassette file |
| `vuln.provenance(...) → Provenance.NotApplicable(reason=CVE_NOT_IN_APP_LAYER)` (Phase 3 refuse-mode, inherited per ADR-0038) | `RagMatchRecipe.applies_to(...)` returns `False`; orchestrator short-circuits at Stage 1 | Universal HITL fallback fires; **LLM is never invoked** for an out-of-scope CVE |

Custom exception classes (all typed, all in `src/codegenie/llm/errors.py` and `src/codegenie/rag/errors.py`):
- `LeafLLMError` (base) → `RateLimitExceeded`, `LeafLLMAuthError`, `ContextWindowExceeded`, `LeafLLMRefused(reason: Literal[...])`
- `RagError` (base) → `StoreCorrupted`, `EmbedderUnavailable`, `ModelNotPresent`

Standard-library exceptions used: `FileNotFoundError`, `PermissionError`, `subprocess.CalledProcessError` (the last only inside `SubprocessJail.run`, never bubbling out of Phase 4 modules). Nothing bare-`except`; ruff `BLE001` catches that.

---

## Resource & cost profile

| Metric | Cold (first run, no caches) | Warm (cache hit) |
|---|---|---|
| RAG store open + embedder load | 0.8–2.5 s (one-time `SentenceTransformer.from_pretrained`) | 0 s (process-cached) |
| RAG query | 5–20 ms | 5–20 ms |
| LLM invoke (Claude Sonnet, ~6k input + ~2k output tokens) | 4–12 s | 4–12 s (or 0.05–0.2 s cassette replay) |
| `tsc --noEmit` (small Node service) | 1–4 s | 1–4 s |
| Phase 4 end-to-end addition (on top of Phase 3 baseline) | +5–15 s p50 | +5–15 s p50 (with live LLM); +0.5–2 s with cassette |
| LLM cost per Phase 4 workflow (live) | $0.02–$0.10 (Sonnet pricing, 2026-Q1) | same |
| LLM cost per Phase 4 workflow (CI, cassette) | $0.00 (asserted by CI fence) | $0.00 |
| New Python dep weight | `chromadb` ~50 MB; `sentence-transformers` ~250 MB (transitive `torch`); `anthropic` ~5 MB; `langgraph` ~10 MB | — |

The big number is `torch` (transitive via `sentence-transformers`). We accept it because the alternative (Voyage remote) introduces an API key, a rate-limit-induced flakiness vector, and a hosted-service dependency for CI. `torch` is well-supported across our CI matrix (Python 3.11/3.12, ubuntu-24.04 — both have prebuilt wheels). Where convention costs us: install time grows by ~40 s on a cold CI run. Where it saves us: zero hosted-API integration, zero credential management, zero "we couldn't reproduce the CI failure locally" because the embedder shipped with us.

---

## Test plan

### Unit tests (~95% of test count)

- `tests/unit/rag/test_store_open.py` — smart-constructor failure modes (missing path → typed error; existing-but-corrupt → `StoreCorrupted`; existing-and-valid → store instance).
- `tests/unit/rag/test_store_add_query.py` — round-trip: add example, query for similar, assert hit. Mocked embedder returns deterministic vectors.
- `tests/unit/rag/test_models.py` — `SolvedExample.from_yaml(...)` happy path + every parse error; `extra="forbid"` rejects unknown keys.
- `tests/unit/rag/test_confidence_mapping.py` — similarity → `AdapterConfidence` boundaries (similarity ≥ 0.78 → High; 0.55–0.78 → Degraded; < 0.55 → Unavailable). Property test: monotonicity (higher similarity never yields lower confidence).
- `tests/unit/llm/test_anthropic_adapter.py` — request translation, response parsing, error mapping (`RateLimitError` → `RateLimitExceeded`).
- `tests/unit/llm/test_protocol_contract.py` — `assert issubclass(AnthropicLeafLLM, LeafLLM)` via runtime-checkable Protocol; signature compatibility.
- `tests/unit/llm/test_no_network_in_unit_tests.py` — patches `anthropic.Anthropic._client.post` to raise; asserts every other unit test in `tests/unit/llm/` does not hit the network.
- `tests/unit/plugins/vulnerability_remediation_node_npm/recipes/test_rag_match.py` — `applies_to` boundary cases; `run` returns correct `RecipeOutcome` variant per `(rag_outcome, threshold)`.
- `tests/unit/plugins/vulnerability_remediation_node_npm/recipes/test_llm_replan.py` — mock `LeafLLM`; assert the three-node graph dispatches correctly; refusal path produces typed `LlmRefused`.
- `tests/unit/plugins/vulnerability_remediation_node_npm/recipes/test_typecheck_signal.py` — `SignalKind("typecheck.node")` registers exactly once (registry double-registration raises); collector parses `tsc` output for known fixtures.
- `tests/unit/transforms/test_trust_scorer_typecheck_kind.py` — strict-AND fold with `typecheck.node` failing; `TrustOutcome.failing` correctly lists it.

### Integration tests (~3% of test count)

- `tests/integration/test_phase4_rag_hit.py` — populated store; query produces hit; `LlmReplanner` invoked with few-shot; cassette replay; produced `Transform` matches golden diff.
- `tests/integration/test_phase4_rag_miss_llm_solo.py` — empty store; LLM invoked without few-shot; cassette replay; produced `Transform` differs from RAG-hit version but still validates.
- `tests/integration/test_phase4_e2e_breaking_change.py` — small fixture Node service with a known major-version-bump CVE; Phase 3 deterministic path fails; Phase 4 LLM-replan succeeds; full `_validate_stage6` runs; `npm test` passes inside `SubprocessJail`; `typecheck.node` passes; `remediation-report.yaml` lands on disk. This is the **roadmap exit-criterion test**.
- `tests/integration/test_phase4_e2e_replay_lands_rag.py` — same case re-run with the harvested example in the store → recipe miss → **RAG hit** → LLM invoked with few-shot at lower token cost (asserted via `LlmCostAccrued` ledger entry). This is the **"cheaper on second run" exit criterion test**.
- `tests/integration/test_typecheck_signal_catches_signature_drift.py` — a deliberately-bad LLM cassette response with a hallucinated method call; `tsc --noEmit` catches it; gate fails before `npm test` runs (asserted via event ordering in the workflow-internal stream).
- `tests/integration/test_provenance_refusal_short_circuits.py` — a glibc CVE (base-image provenance, Phase 3 refuse-mode inherited); `RagMatchRecipe.applies_to` returns `False`; the LLM is **never invoked** (assert by event-absence: no `LeafLlmRequested` event in workflow-internal stream).

### E2E tests (~1% of test count)

- `tests/e2e/test_phase4_full_remediation.py` — one shell-script-driven scenario hitting `codegenie remediate` from the command line on a real fixture repo with cassette replay. Asserts exit code, branch created, `remediation-report.yaml` present, event log valid.

### Property tests

- `tests/property/test_similarity_monotonicity.py` — `hypothesis` strategy over `(vec_a, vec_b)`; assert `cosine_similarity` is symmetric and in `[-1, 1]`.
- `tests/property/test_solved_example_yaml_roundtrip.py` — `hypothesis` generates valid `SolvedExample` instances; assert `from_yaml(to_yaml(x)) == x`.
- `tests/property/test_determinism_under_cassette_replay.py` — given the same `(cassette_id, store_digest, repo_snapshot)`, run the full Phase 4 pipeline 50 times; assert byte-identical `Transform.diff_bytes` and identical event ordering (modulo timestamps).

### Cassette discipline (pytest-recording / VCR)

- **Directory:** `tests/cassettes/anthropic/<test_module_name>/<test_function_name>.yaml`. One cassette per test function (not per request), so a test that makes 3 API calls has 1 cassette with 3 interactions.
- **Scrubbing:** request headers `x-api-key`, `authorization`, `anthropic-version` are scrubbed to placeholders before recording. Response body is preserved verbatim (no PII in our test corpus). Request bodies are preserved verbatim because the request content IS the test fixture.
- **Refresh policy:**
  - `pytest --record-mode=none` (default; CI). Cassette miss → test fails.
  - `pytest --record-mode=once` (local; for new tests). Re-records only when no cassette exists.
  - `pytest --record-mode=new_episodes` (local, with `CODEGENIE_LIVE_LLM=1`). Appends new interactions to existing cassettes.
  - `pytest --record-mode=all` (local; bulk refresh). Re-records everything.
- **CI fence:** a `tests/fence/test_cassette_discipline.py` asserts `CODEGENIE_LIVE_LLM` is unset in CI and `--record-mode` resolves to `none`.

### Fence tests (CI gate)

- `tests/fence/test_kernel_frozen.py` (Phase 3, extended) — file allow-list grows by the Phase 4 additions; diff against Phase 0/1/2/3 kernel files asserts zero edits.
- `tests/fence/test_pyproject_fence_phase4.py` — `anthropic`, `chromadb`, `sentence-transformers`, `langgraph` are admitted in the **runtime** closure but `tests/unit/test_pyproject_fence.py` is updated additively to keep them out of `src/codegenie/probes/`, `src/codegenie/coordinator/`, `src/codegenie/cache/`, `src/codegenie/output/`, `src/codegenie/schema/`. The import-linter contract is also updated.
- `tests/fence/test_typecheck_signal_registered.py` — at module-import time, `SignalKind("typecheck.node")` is in the registry; double-registration raises.

---

## Design patterns applied

| Decision (component or interface) | Pattern applied | Why this pattern *here* | Pattern *not* applied (and why) |
|---|---|---|---|
| `LeafLLM` Protocol + `AnthropicLeafLLM` adapter | **Hexagonal architecture (Ports & Adapters)** + **Dependency inversion** | The gather pipeline must not import `anthropic`; the plugin must not know which LLM SDK it's talking to. One Port, one adapter today, room for a Voyage-equivalent or OpenAI adapter tomorrow without editing callers. | **NOT Strategy** (no runtime swapping among a family of LLMs today — only one implementation). When ADR-0020 lands a second concrete adapter, the Port already exists; we don't pay for the Strategy ceremony until then. |
| `SolvedExampleStore` (single backend) | **Repository pattern** + **Adapter pattern** (chromadb wrapped) | The plugin recipes call `store.query(q)` and consume a typed sum; they don't know chromadb exists. Swapping to qdrant later is one file change. | **NOT a multi-backend Factory.** One backend today; the abstraction is the `SolvedExampleStore` class itself, not a factory over backends. Premature pluggability anti-pattern avoided. |
| `RagMatchRecipe`, `LlmReplanRecipe`, existing Phase-3 recipes | **Chain of Responsibility / Pipeline** (the plugin subgraph) | Recipe → RAG → LLM is exactly ADR-0011's three-tier fallback; each node decides "handle or pass." Each handler's contract is narrow (`applies_to` + `run`). | **NOT one giant `if cve.is_simple: ... elif: ... else:`** function — the design-patterns-toolkit explicitly calls this out as tag-and-dispatch-without-a-tagged-union. |
| `RetrievalOutcome = RagHit | RagMiss | RagDegraded`; `RecipeOutcome` extended with `MatchedFromRag`, `ReplannedByLlm` | **Tagged union / sum type for state** (ADR-0033 §3) | Three retrieval outcomes have different fields (`RagHit` has the example + similarity; `RagMiss` is bare; `RagDegraded` carries a `reason`). Encoding them as one Pydantic class with optional fields would make illegal states representable. | **NOT** `Optional[SolvedExample]` + `Optional[float]` on a single `RetrievalResult` class. ADR-0033 §4 (illegal states unrepresentable) is the spine of this design. |
| `SignalKind("typecheck.node")` registration; `@register_signal_kind` reused | **Open/Closed Principle** + **Registry pattern** | Phase 3 already shipped the open registry for exactly this case (ADR-0037 §Decision). Phase 4 adds a row via decorator at import time; no edits to `TrustScorer`, no edits to `SignalKind` enum. | **NOT a hardcoded `Literal["build","install","tests","lockfile_policy","cve_delta","typecheck.node"]`** — that would force `TrustScorer` edits every time a new signal lands. |
| `_LlmReplanState` (mutable Pydantic) inside LangGraph subgraph | **State pattern** (LangGraph idiom) | LangGraph's contract is "nodes mutate state by returning patches"; using a frozen model would require workarounds. The mutation is scoped to a single compiled graph invocation and never escapes. | **NOT a shared mutable global / module-level state.** The state lives inside the graph invocation only; outside the graph, every model is `frozen=True`. |
| `SolvedExample.from_yaml(path) -> Result[SolvedExample, ParseError]` | **Smart constructor** (ADR-0033 §2) | External-data parsing must fail at the boundary with typed errors, not at first-use deep in `RagMatchRecipe.run`. | **NOT bare `SolvedExample(**yaml.safe_load(...))`** — runtime KeyError / ValidationError leaking 4 frames up. |

---

## Patterns deliberately avoided

- **Visitor.** No call graph here that branches over a closed set of node types; the subgraph dispatch is by `RecipeOutcome.kind` (discriminated-union match), not Visitor.
- **Abstract Factory for "LLM provider families."** One provider today (Anthropic). Adding a second is a one-file additive ADR-0020 resolution. No `LeafLLMProviderFactory` interface today.
- **Builder for `LeafLLMRequest`.** It has 5 fields; the Pydantic constructor IS the builder. Adding `.with_few_shot(...)` chains would be ceremony.
- **Observer for cost telemetry.** The existing `EventLog.emit_spanning(LlmCostAccrued(...))` is the observer pattern done by direct event emission; no `Subject`+`Observer` classes needed.
- **Singleton for `SolvedExampleStore`.** Plugin recipes accept a store as a parameter (dependency injection); module-level singletons are the anti-pattern flagged in Phase 3 ADR-0002.
- **Async/await throughout `rag/` and `llm/`.** The LLM call is the only blocking I/O; wrapping the entire chain in async for one I/O call buys nothing and complicates testing. Phase 9's Temporal envelope owns concurrency; Phase 4 modules are synchronous Python and tested as such. (If this ever proves wrong, the conversion is mechanical — `def → async def` per Phase 0's existing `asyncio_mode = "auto"` pytest config.)

---

## Risks (top 3–5)

1. **Cassette rot.** As the Anthropic API evolves, cassettes recorded today may not match the SDK's expected wire shape later, causing CI flakiness even though semantics are unchanged. *Mitigation:* `pytest-recording`'s `match_on=("method","path","body")` matching; an explicit `tests/cassettes/README.md` documenting the refresh recipe; a quarterly cassette-refresh runbook entry.
2. **Embedder model file drift.** `sentence-transformers` may auto-update model weights when versions move; `StoreDigest` includes `model_id` but not the weight hash. *Mitigation:* pin `sentence-transformers` to an exact version in `pyproject.toml`; add a `weight_sha256` field to `StoreDigest` in a follow-up if drift is observed in Phase 6.5 calibration.
3. **LLM substrate goes down mid-development.** A multi-hour Anthropic outage blocks all new test recording (though replay still works). *Mitigation:* cassette-only CI; recording is a developer-local activity, never a CI dependency.
4. **`typecheck.node` flaky in monorepos.** A Phase-2 fixture without proper `tsconfig.json` could report spurious errors against unrelated files. *Mitigation:* the collector passes `--project <repo>/tsconfig.json` explicitly when present; falls back to `--noEmit --skipLibCheck` otherwise; emits `TrustSignal(passed=True, details={"degraded_reason": "no_tsconfig"})` when neither path is viable. This is a `Degraded` confidence path, ADR-0033-compliant.
5. **The 80MB embedder model is a contributor friction point.** New contributors clone the repo and need to download the model on first test run. *Mitigation:* the model loads to `~/.cache/sentence-transformers/`; a `make bootstrap` step prefetches it; CI caches it across runs via `actions/cache`.

---

## Acknowledged blind spots

- **No latency tuning.** Performance-first will likely propose embedder model swaps (smaller models), pre-warmed embedder processes, or qdrant in Docker. We accept the slower defaults because the choice is invisible to callers and reversal is a one-file change.
- **No supply-chain hardening of the LLM SDK.** Phase 16 handles this. We trust `anthropic` from PyPI today on the same terms we trust `pydantic`.
- **No multi-LLM routing.** ADR-0020 deferral; one model, one adapter.
- **No retrieval-quality calibration today.** The 0.78 similarity threshold is a guess; calibration is Phase 6.5's job once `bench/vuln-remediation/cases/` accumulates real solved-example labels.
- **No streaming token responses.** Sync `invoke()` returns the full response; streaming buys latency to first token but complicates the Protocol. If the leaf-agent loop in Phase 15 needs it, the `LeafLLM` Protocol gets a sibling `invoke_streaming(...)` method by addition.
- **Operator-portal coupling.** Phase 13.5 will project off `LlmCostAccrued` events; we emit them in the spanning stream so the projection is free. We do **not** ship dashboards in Phase 4.

---

## Open questions for the synthesizer

1. **Auto-harvest vs operator-curated solved-examples in Phase 4.** This design defers auto-harvest to Phase 11 (post-merge webhook ingestion). Performance-first may argue for inline harvest to make "second run is cheaper" immediate. The argument against: a failed-but-not-yet-retracted LLM output could enter the store as a poisoned example. *Question for synthesizer:* should the harvester run inline behind a deterministic gate (e.g., only harvest when `TrustOutcome.passed AND TrustOutcome.confidence == "high"`)?
2. **chromadb vs qdrant.** Best-practices picks chromadb for in-process simplicity. Performance-first will likely pick qdrant for query latency and richer filtering. The cross-cutting concern is the contributor experience: docker-compose dependency for `make bootstrap` vs none. *Question for synthesizer:* is the synthesis a stage-gated migration (chromadb in Phase 4, qdrant once corpus crosses N examples), or is one choice canonical from day one?
3. **`langgraph` as a Phase 4 dep vs Phase 6.** This design admits `langgraph` one phase early to lock the leaf-agent topology now. Alternatives: (a) ship `LlmReplanRecipe` as plain Python today, port to LangGraph in Phase 6 (smaller Phase 4 dep footprint, more Phase 6 work); (b) ship `LlmReplanRecipe` with a hand-rolled "tiny state machine" Phase 4 wrote (avoids the dep entirely but reinvents LangGraph). *Question for synthesizer:* which Phase 6 migration cost is the design willing to pay?
4. **Universal-fallback dispatch on `RagDegraded`.** This design escalates to HITL when the embedder is unavailable. Performance-first may argue: skip RAG, go straight to LLM-without-few-shot, log the degradation. Security-first may argue: refuse the LLM call entirely and HITL on `RagDegraded`. *Question for synthesizer:* what's the calibrated trust posture when the retrieval substrate is missing — pessimist (HITL), neutral (LLM solo), or optimist (assume miss == "no relevant example exists")?
5. **Cassette scrubbing aggressiveness.** This design scrubs auth headers only. Security-first may demand full response-body PII scrubbing. *Question for synthesizer:* is the test corpus disciplined enough that response bodies are safe-by-default, or do we need a redaction pass at recording time?
