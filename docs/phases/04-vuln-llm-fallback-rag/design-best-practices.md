# Phase 4 — Vuln remediation: LLM fallback + solved-example RAG: Best-practices design

**Lens:** Best practices — idiomatic, maintainable, conventional, well-tested.
**Designed by:** Best-practices design subagent
**Date:** 2026-05-12
**Companions (parallel):** `design-performance.md`, `design-security.md`
**Source-of-truth scope:** `docs/roadmap.md` §"Phase 4"; `docs/production/design.md §2`–§3; ADR-0008, ADR-0009, ADR-0011, ADR-0014, ADR-0017, ADR-0020, ADR-0024, ADR-0025, ADR-0027; `docs/phases/03-vuln-deterministic-recipe/final-design.md`.

---

## Lens summary

Phase 3 landed the *first* probabilistic-adjacent contract — `RecipeEngine` — and committed to one rule that this phase must honour: **structural changes are deterministic; the LLM is invoked only at leaves**. Phase 4 is the first time the system spends a token. Every pattern set here propagates: how we wrap the Anthropic SDK, how we record cassettes, how we externalize prompts, how we structure a vector store, how we write back solved examples. If we get this wrong, every later LLM-touching phase (5, 6, 7, 11, 15) inherits the mistake.

The best-practices bet, identical in spirit to Phase 1's bet on `Probe` and Phase 3's bet on `Transform`/`RecipeEngine`: **Phase 4 is a third `RecipeEngine` registered alongside `NcuRecipeEngine` and `OpenRewriteEngineStub` — not a new top-level ABC.** The Phase 3 ABC was designed (via `RecipeSelection.reason` and the `--engine=<name>` opt-in pattern) to extend by addition. We honour that by adding a `RagLlmEngine` that satisfies the same contract. The Phase 3 `RecipeSelector` already iterates engines in order; *that* is the recipe → RAG → LLM chain-of-responsibility, and it already exists.

Concretely this lens means:

- **One new engine, one new ABC, three new components.** The engine is `RagLlmEngine` (satisfies `RecipeEngine`). The new ABC is `EmbeddingProvider` (so the embedding choice is swappable behind a dep). The three components are `SolvedExampleStore` (the vector store wrapper), `LeafLlmAgent` (the Anthropic SDK wrapper), `PromptLoader` (versioned YAML prompts). Everything else is wiring.
- **Two new top-level packages** — `src/codegenie/rag/` (embedding ABC + vector store wrapper + solved-example schema + writeback) and `src/codegenie/llm/` (Anthropic SDK shim + leaf agent + prompt loader + cost ledger emitter + cost guard). Both siblings of `transforms/` and `recipes/`. No new package for `planning/` — the Phase 3 `RecipeSelector` already *is* the planner.
- **`chromadb` over `qdrant-client`.** Pure-Python local-mode, no docker, no daemon. Single-process, embedded, file-on-disk. The Phase 9+ service mode can swap to qdrant or pgvector behind the same `SolvedExampleStore` interface; the embedded mode is the right Phase 4 shape.
- **Embeddings are local — `sentence-transformers` with a single pinned model (`BAAI/bge-small-en-v1.5`).** CI must be hermetic; tests cannot require Voyage's API. The model weights are fetched once via `huggingface_hub` snapshot-download pinned by SHA, cached under `~/.cache/codegenie/models/`. Voyage support exists as a *registered second `EmbeddingProvider`* (opt-in via env config) so the contract extends, mirroring Phase 3's two-engine pattern.
- **No LangGraph in Phase 4.** The roadmap places the SHERPA state machine in Phase 6. Wiring `StateGraph` here just to satisfy "minimally" couples Phase 4 to a runtime decision that Phase 6 makes properly. The leaf agent is a plain function with a typed input and a typed output. Phase 6 wraps it. (The roadmap line "imported minimally — just enough to wrap the leaf agent invocation" is honoured by *importing nothing* — `langgraph` does not appear in Phase 4's `pyproject.toml`.)
- **Anthropic SDK: sync client, prompt caching mandatory, no tool use in Phase 4.** Sync because the orchestrator is sync (Phase 3 invariant; Phase 6/9 reopen). Prompt caching because the matched solved example is reused across retries and exactly fits the cache-control discipline. No tool use because the leaf produces a patch as text, not a sequence of actions — actions are Phase 5's sandbox machinery. Tool use becomes additive in Phase 5/6 where the gate machinery needs it.
- **Prompts are versioned YAML under `src/codegenie/llm/prompts/`.** Schema-validated at load time. Each prompt has a `version` and a `cache_breakpoints` declaration. Prompt diffs are reviewable; prompt changes are revertable. **Inline f-string prompt construction is forbidden by `fence` CI.** This is the single most consequential best-practice in Phase 4 — every later LLM-using phase inherits the prompt-as-data discipline or has to fight it.
- **VCR cassettes are the test contract.** Every test that touches Anthropic or the embedding model uses `pytest-recording`. Cassettes are committed under `tests/cassettes/`. A pre-commit hook strips `x-api-key`, `authorization`, and `Set-Cookie` headers. CI runs `--record-mode=none`; no test ever hits the live API.
- **The solved-example schema is small and stable.** A Pydantic model with no business-logic fields beyond what the writeback orchestrator and the RAG retriever both need. Forward-compatible with Phase 7 (migrations), Phase 11 (KG writeback), Phase 15 (recipe authoring source).

What I deprioritize explicitly:

- **Voyage embeddings as default.** Hermetic CI matters more than embedding quality at the Phase 4 scale (a few dozen solved examples). When the corpus passes ~10k examples, retune.
- **LangGraph wrapping.** Phase 6's job. A `StateGraph` with one node and an `interrupt()` is theatre; the discipline of Phase 6 needs the full Pydantic state ledger and the proper checkpointer choice.
- **A LLM-driven supervisor / router.** ADR-0011's chain is deterministic. The selector iterates engines in order, period.
- **Full Budget Enforcer middleware** (ADR-0025). Phase 13's job. Phase 4 *measures* cost (emit to the ledger) and surfaces a per-run `cost_report.yaml`, but enforcement is the minimum: a per-invocation hard wall via `LlmInvocationGuard`. Multi-call per-workflow caps wait for Phase 13.

---

## Conventions honored

- **No LLM in the gather pipeline → extended to transforms (`production/design.md §2.1`, ADR-0005).** The Phase 3 `fence` CI gate forbids `anthropic`, `langgraph`, `chromadb`, `sentence-transformers`, `voyageai`, `qdrant-client` under `transforms/`, `recipes/`, `probes/`, `cve/`. Phase 4 *adds* `rag/` and `llm/` to the **allowed importers** for those deps and to a new fence stanza forbidding the same deps *outside* those two packages. **`transforms/` may not import `llm/` or `rag/`.** Only `recipes/engines/rag_llm.py` imports them, and it's registered through the existing `@register_recipe_engine` registry — same isolation pattern as `NcuRecipeEngine`.
- **Facts, not judgments (ADR-0008, `production/design.md §2.2`).** The leaf agent emits **a candidate patch as a `RecipeApplication`** — the exact same shape Phase 3 engines emit. **It does not emit a self-reported confidence field on its `RecipeApplication`.** Trust is the strict-AND of objective signals computed downstream by Phase 3's existing `TrustScorer`. The solved-example writeback records `validation_outcome: ValidatorOutput` from Phase 3's actual run — not "the LLM said it was good." This is ADR-0008 applied to the third place it can be violated (after probes and validators).
- **Extension by addition (`production/design.md §2.5`).** Two new packages (`rag/`, `llm/`); one new engine file under `recipes/engines/rag_llm.py`; one new probe (`SolvedExampleHealthProbe` — analog of B2's `IndexHealthProbe` for the vector store); zero edits to Phase 0/1/2/3 source code *except* two ADR-gated additive edits: (1) `Recipe.engine` Literal in `recipes/models.py` extends from `Literal["ncu","openrewrite"]` to `Literal["ncu","openrewrite","rag_llm"]` (surfaced as ADR-P4-001; protected by Phase 3's contract snapshot test, which regenerates as part of the Phase 4 PR); (2) `RemediationOrchestrator` gains one conditional branch after `TrustScorer.passed`: `if recipe_application.engine_used == "rag_llm": writeback_solved_example(...)` (surfaced as ADR-P4-002). **`ALLOWED_BINARIES` is unchanged** — embeddings and Anthropic calls are pure-Python.
- **Determinism over probabilism for structural changes (`production/design.md §2.4`).** The LLM produces a candidate patch; Phase 3's machinery (lockfile canonicalizer, validation gate, trust scorer, branch writer) verifies it deterministically. The probabilistic component is *one leaf*; everything around it is unchanged. The "Safer Builders, Risky Maintainers" finding (`gemini-auto-agent-design.md`) is the empirical basis: agents fail at maintenance/refactor tasks at ~3× the rate of new-feature tasks, so the LLM gets one bite at the apple and the deterministic gates own the verdict.
- **Humans always merge (ADR-0009).** Phase 4 stops at a local branch + a cost report. No `git push`. No GitHub API. The cost report lives at `.codegenie/remediation/<run-id>/cost-report.yaml` — Phase 13 reads it.
- **Recipe → RAG → LLM-fallback (ADR-0011).** Phase 4 implements the RAG arm and the LLM arm. The selector's existing chain (`engines = [Ncu, OpenRewriteStub, RagLlm]`) executes the three-tier order: Ncu / OpenRewrite handle recipe-matchable cases (emit `RecipeSelection(reason="matched")`); `RagLlmEngine.available()` returns `True` iff API key + embedding model + store all OK; when the previous engines return `reason ∈ {catalog_miss, range_break, peer_dep_conflict, unsupported_dialect}`, `RagLlmEngine.apply()` is invoked. Inside `RagLlmEngine.apply()`, RAG runs first: if a solved example matches above the similarity threshold, the LLM is invoked with that example as cached few-shot; otherwise the LLM is invoked with `RepoContext` + matched Skill as context. **The order is structural, not configurable.** Operators cannot flip RAG and LLM in the chain.
- **Honest confidence (ADR-0008).** The leaf agent **does not** emit a self-confidence number that any gate consumes. The Phase 3 `TrustScorer.score(signals)` strict-AND is the only confidence used. The solved-example store records `validation_outcome.passed` and the per-signal trust components — never an LLM self-report. Logged-only LLM self-confidence is allowed for *observability* (drift analysis, future calibration) — recorded under `cost-report.yaml#diagnostics.llm_self_reported_confidence` and explicitly excluded from any gate input.
- **Organizational uniqueness as data, not prompts (`production/design.md §2.6`).** Prompts are versioned YAML files, schema-validated, diff-reviewable. They are *not* prose in Python source. Skills frontmatter (Phase 2's loader) extends additively with `applies_to.llm_few_shot: bool = false` to mark Skills that are suitable for inclusion in the LLM context window — preserves the data-not-prose discipline.
- **Progressive disclosure (`production/design.md §2.7`).** The `RagLlmEngine` writes its artifacts under `.codegenie/remediation/<run-id>/llm/`: `prompt.yaml` (resolved prompt with variable substitutions), `request.json` (Anthropic request payload, sanitized), `response.json` (full response), `usage.json` (token usage), `retrieved_examples.json` (top-k *metadata*, not bodies — bodies are referenced by `solved_example_id`). The `remediation-report.yaml` indexes these; it does not inline them. Same shape as Phase 3.
- **Cost observability (ADR-0024, ADR-0027).** Every LLM call emits a `cost.llm.invoked` audit event with `(workflow_id, stage="planning", node="rag_llm_engine", model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, cost_usd)` — the exact aggregation key from `design.md §3.3`. Every embedding call emits `cost.embedding.run` with input bytes + provider + cost. Phase 4's cost ledger is a per-run JSONL under `.codegenie/remediation/<run-id>/cost-ledger.jsonl`. Phase 13 reads these and rolls up.
- **Per-workflow cost cap (ADR-0025).** Phase 13 lands the full Budget Enforcer middleware. Phase 4 ships `LlmInvocationGuard`: a hard per-invocation ceiling (default `$5.00` per `rag_llm` engine invocation, configurable via `~/.config/codegenie/llm.yaml`). Above the ceiling, the guard raises `CostCeilingBreached` before the Anthropic call. The orchestrator catches it, marks `confidence: low`, exits with code 9 (`cost_ceiling`). This is **the minimum enforcement needed to prevent a single-run disaster**; full per-workflow + per-task-class caps wait for Phase 13.
- **Cost attribution (ADR-0027).** Phase 4 cost entries are `direct` cost (one workflow caused them). The cost-ledger entry schema matches §3.3's aggregation-key table verbatim, so Phase 13's tiered roll-up (direct + amortized + overhead) can read Phase 4 entries without migration.

---

## Goals (concrete, measurable)

- **Public API surface count:** **One new ABC** (`EmbeddingProvider`). **One new `RecipeEngine` implementation** (`RagLlmEngine`). **One new probe** (`SolvedExampleHealthProbe`). **One new Pydantic model family** (`SolvedExample`, `RetrievedExample`, `LlmRequest`, `LlmResponse`, `PromptTemplate`, `CostLedgerEntry`). **One CLI subcommand group** (`codegenie solved-examples {list,show,prune,health}`). The Phase 3 `RecipeEngine` ABC, `Transform` ABC, `Validator` ABC, `Probe` ABC, and `RepoContext` schema are unchanged. The single *additive* edit is `Recipe.engine` Literal (ADR-gated).
- **New top-level packages:** **2** — `src/codegenie/rag/`, `src/codegenie/llm/`. Each siblings `transforms/`, `recipes/`, `probes/`. (Smaller new-package footprint than Phase 3's 2; deliberate. Fewer is better when fewer fits.)
- **Net new Python files in `src/`:** ~18 modules, ~2200 LOC target, 3000 hard ceiling. Breakdown: `rag/` (embedding ABC + sentence-transformers impl + Voyage stub + store + writeback + similarity + models = 7); `llm/` (Anthropic shim + leaf agent + prompt loader + cost emitter + guard + models = 6); `recipes/engines/rag_llm.py` (1); `probes/solved_example_health.py` (1); `cli/solved_examples.py` (1); `llm/prompts/*.yaml` (~3 prompts, not Python).
- **Net new lines of test code:** target ≥ 1.5× source LOC (~3300–4500 LOC). The ratio is the convention.
- **Test coverage target:** **90% line / 80% branch** on new packages; **95% line / 90% branch** on `recipes/engines/rag_llm.py` (the single most consequential new file). Phase 3's 90/80 floor stays in place codebase-wide.
- **Cyclomatic complexity ceiling:** **McCabe ≤ 10 per function**, ruff `C901` enforced. The `RagLlmEngine.apply()` orchestration body is the function most likely to push this; split into `_retrieve_candidates`, `_select_example`, `_invoke_llm`, `_parse_patch`, `_emit_telemetry` helpers.
- **Plain Python vs framework-coupled ratio:** ≥ 90% plain Python under the new packages. `anthropic` only inside `src/codegenie/llm/client.py`; `chromadb` only inside `src/codegenie/rag/store.py`; `sentence-transformers` only inside `src/codegenie/rag/embeddings/local.py`. **Three import lines total** for those three deps across the codebase. Enforced by fence CI.
- **New dependencies (count and justify each):** **4 production deps + 2 dev deps.**
  - `anthropic` (~latest 0.x): the SDK we committed to in ADR-0020's default. Mandatory.
  - `chromadb` (pinned minor; embedded mode): widely-used, pure-Python local mode, simpler operational footprint than qdrant for Phase 4. ADR-P4-003 documents the choice + the swap path to qdrant in Phase 9+.
  - `sentence-transformers` (pinned minor): hermetic offline embeddings. ADR-P4-004.
  - `huggingface_hub` (pinned minor): SHA-pinned model download for the `BAAI/bge-small-en-v1.5` weights. Transitive of sentence-transformers but pinned explicitly so the snapshot-download API is stable.
  - `pytest-recording` (dev): the cassette discipline. ADR-P4-005.
  - `vcrpy` (dev, transitive of `pytest-recording` but pinned explicitly for cassette format stability).
- **Tokens per run:** target — **0 if RAG hits**, **≤ 8k tokens if LLM fires**. Hard wall via `LlmInvocationGuard` at **`$5.00` per invocation** (≈ 80k tokens at current Sonnet pricing; deliberately generous so legitimate breaking-change repros aren't artificially capped — Phase 13 tightens).
- **Wall-clock targets (advisory):**
  - Hot path (recipe matched in Phase 3, no Phase 4 invocation): same as Phase 3 — p50 ≤ 30 s.
  - Cold path (RAG hit, LLM with cached few-shot): p50 ≤ 45 s, p95 ≤ 90 s — dominated by Anthropic latency + validation suite.
  - Cold path (LLM from scratch, no RAG hit): p50 ≤ 60 s, p95 ≤ 120 s.
  - Embedding a new query: p50 ≤ 100 ms (local model, batch size 1).
  - Vector search across ≤ 10k examples: p50 ≤ 50 ms (chromadb HNSW).
- **Solved-example writeback latency:** p50 ≤ 200 ms (embedding + chromadb insert + JSON write).

---

## Architecture

ASCII. Lean on established patterns. Most of Phase 4 slots into Phase 3's ABCs additively — minimize new abstractions.

```
                                  codegenie remediate <repo> --cve <id>
                                              │
                                              ▼  (unchanged Phase 3 entry)
                          ┌──────────────────────────────────────┐
                          │  Phase 0 CLI (click)                  │
                          │  Phase 3 RemediationOrchestrator      │
                          │  (linear sync; six function calls)    │
                          └──────────────────┬───────────────────┘
                                             │ Stage 3 — Select Recipe
                                             ▼
                          ┌──────────────────────────────────────┐
                          │  Phase 3 RecipeSelector (unchanged)   │
                          │  engines = [Ncu, OpenRewriteStub,     │
                          │             RagLlm]  ← Phase 4 add    │
                          │  iterates in order; first non-skip    │
                          │  reason wins. The chain-of-resp        │
                          │  *is* the recipe→RAG→LLM order.        │
                          └──────────────────┬───────────────────┘
                                             │ on Ncu/OpenRewrite returning
                                             │   reason ∈ {catalog_miss,
                                             │            range_break,
                                             │            peer_dep_conflict,
                                             │            unsupported_dialect}
                                             ▼
                          ┌──────────────────────────────────────┐
                          │  src/codegenie/recipes/engines/       │
                          │      rag_llm.py:RagLlmEngine          │
                          │                                       │
                          │  apply(recipe_skeleton, repo, ctx):   │
                          │    1. fingerprint = compute_fp(       │
                          │         advisory, repo_ctx)           │
                          │    2. retrieved =                     │
                          │       SolvedExampleStore.query(       │
                          │         fingerprint, top_k=5)         │
                          │    3. if retrieved.best.sim ≥ τ:      │
                          │         prompt_kind = "few_shot_rag"  │
                          │       else:                           │
                          │         prompt_kind = "from_scratch"  │
                          │    4. LlmInvocationGuard.check_budget │
                          │    5. resp = LeafLlmAgent.invoke(     │
                          │         PromptLoader.load(            │
                          │           prompt_kind, context={...}))│
                          │    6. patch = parse_patch(resp.text)  │
                          │    7. return RecipeApplication(       │
                          │         diff=patch, engine_used=      │
                          │         "rag_llm", ...)               │
                          └──────────────────┬───────────────────┘
                                             │ Stages 5-7 unchanged (Phase 3)
                                             ▼
                          ┌──────────────────────────────────────┐
                          │  Phase 3 LockfileResolver,            │
                          │   Canonicalizer, ValidationGate,      │
                          │   TrustScorer, PatchBranchWriter      │
                          └──────────────────┬───────────────────┘
                                             │ on TrustScore.passed:
                                             ▼
                          ┌──────────────────────────────────────┐
                          │  NEW: src/codegenie/rag/writeback.py  │
                          │  writeback_solved_example(            │
                          │    run_id, advisory, recipe,          │
                          │    patch, validation_outcome,         │
                          │    cost_summary)                      │
                          │  invoked by orchestrator at           │
                          │    validation-pass time, only if      │
                          │    engine_used == "rag_llm"           │
                          └──────────────────────────────────────┘


     New top-level packages
     ──────────────────────
     src/codegenie/rag/
       __init__.py
       models.py            ← SolvedExample, RetrievedExample, Fingerprint
       fingerprint.py       ← compute_fp(advisory, repo_ctx) → str
       similarity.py        ← cosine helpers (stdlib; chromadb does the work)
       embeddings/
         contract.py        ← EmbeddingProvider ABC
         local.py           ← SentenceTransformerProvider (default)
         voyage.py          ← VoyageProvider (opt-in, registered)
       store.py             ← SolvedExampleStore (chromadb wrapper)
       writeback.py         ← writeback_solved_example() function
       prune.py             ← CLI helper: drop stale / failed examples

     src/codegenie/llm/
       __init__.py
       models.py            ← LlmRequest, LlmResponse, CostLedgerEntry,
                              PromptTemplate
       client.py            ← AnthropicClient (sync wrapper; the ONE place
                              `import anthropic` appears)
       agent.py             ← LeafLlmAgent (typed input→output; calls client.py;
                              emits cost events)
       prompt_loader.py     ← PromptLoader: YAML→PromptTemplate;
                              schema-validated; cache breakpoints declared
       guard.py             ← LlmInvocationGuard (per-call $ ceiling)
       cost.py              ← cost-event emission helpers
       rates.yaml           ← pinned per-model rate table (data)
       prompts/
         _schema.json       ← JSON Schema for prompts
         vuln_remediation/
           system.v1.yaml
           few_shot_rag.v1.yaml
           from_scratch.v1.yaml

     New probe (registered via Phase 1 @register_probe)
     ─────────────────────────────────────────────────
     src/codegenie/probes/solved_example_health.py
       SolvedExampleHealthProbe — analog of IndexHealthProbe (B2).
       Reports vector-store freshness, embedding model digest, count,
       last-write-at, embedding dimensionality match. Confidence input
       for any Phase 5+ gate that wants to know if RAG is trustworthy.

     New engine (registered via Phase 3 @register_recipe_engine)
     ──────────────────────────────────────────────────────────
     src/codegenie/recipes/engines/rag_llm.py
       RagLlmEngine — implements RecipeEngine ABC. Available() → True iff
       (a) ANTHROPIC_API_KEY present, (b) embedding model resolvable,
       (c) SolvedExampleStore opens cleanly, (d) all prompts validate.
       The ONLY file outside rag/ and llm/ that imports from those
       packages.
```

Three things to notice in the diagram:

1. **The Phase 3 orchestrator does not change shape.** Not even the signature of `coordinator.remediate`. The new engine slots into the existing `engines` list. The new writeback call sits inside the orchestrator as one new conditional branch — `if recipe_application.engine_used == "rag_llm" and trust_score.passed: writeback(...)` — which **is** an edit to `coordinator.py`. Surfaced as ADR-P4-002. It is the *only* coordinator edit Phase 4 needs.
2. **The leaf is a plain function.** `LeafLlmAgent.invoke(request: LlmRequest) -> LlmResponse`. No `StateGraph`. No `interrupt()`. Phase 6 wraps; Phase 4 must not pre-empt.
3. **Three import lines.** `import anthropic` lives in `llm/client.py` only. `import chromadb` in `rag/store.py` only. `from sentence_transformers import SentenceTransformer` in `rag/embeddings/local.py` only. The fence CI gates this.

---

## Components

### 1. `RagLlmEngine` — the third `RecipeEngine`, the most consequential file in Phase 4

- **Purpose:** Satisfy the Phase 3 `RecipeEngine` contract using RAG + LLM. The single integration point between Phase 4's machinery and Phase 3's orchestrator.
- **Public interface:**
  ```python
  # src/codegenie/recipes/engines/rag_llm.py
  from codegenie.recipes.contract import RecipeEngine
  from codegenie.recipes.models import Recipe, ApplyContext, RecipeApplication
  from codegenie.rag.store import SolvedExampleStore
  from codegenie.llm.agent import LeafLlmAgent
  from codegenie.llm.guard import LlmInvocationGuard
  from codegenie.llm.prompt_loader import PromptLoader

  @register_recipe_engine
  class RagLlmEngine(RecipeEngine):
      name = "rag_llm"
      applies_to_engines = ("rag_llm",)

      def __init__(
          self,
          store: SolvedExampleStore,
          agent: LeafLlmAgent,
          loader: PromptLoader,
          guard: LlmInvocationGuard,
          *,
          similarity_threshold: float = 0.78,
      ) -> None:
          self._store = store
          self._agent = agent
          self._loader = loader
          self._guard = guard
          self._tau = similarity_threshold

      def available(self) -> bool:
          return (
              self._agent.available()
              and self._store.opens_cleanly()
              and self._loader.all_templates_validate()
          )

      def apply(
          self,
          recipe: Recipe,
          repo: Path,
          ctx: ApplyContext,
      ) -> RecipeApplication: ...
  ```
- **Internal design (idiomatic Python conventions cited):**
  - **Composition over inheritance.** The engine takes four collaborators in its constructor; each has a single responsibility. No subclassing of `RecipeEngine` beyond the one level.
  - **Public method does five things in order**, each in a tiny helper:
    ```python
    def apply(self, recipe, repo, ctx):
        fingerprint = self._compute_fingerprint(ctx)
        retrieved = self._retrieve_candidates(fingerprint)
        prompt_kind = "few_shot_rag" if retrieved.best_similarity >= self._tau else "from_scratch"
        self._guard.check_budget(self._loader.estimate(prompt_kind, ctx))
        response = self._invoke_llm(prompt_kind, retrieved, ctx)
        return self._materialize_application(recipe, response, ctx)
    ```
    Each helper is ≤ 30 lines. Cyclomatic complexity ≤ 5 per function.
  - **Strict-AND on objective signals only.** The engine never reads `response.self_reported_confidence` for control flow. That field, if the model emits it, is dropped into telemetry only (`cost-report.yaml#diagnostics`).
  - **Errors are explicit, typed:** `RagRetrievalFailed`, `EmbeddingFailed`, `LlmCallFailed`, `PatchParseFailed`, `CostCeilingBreached`, `SolvedExampleWritebackFailed`. Each maps to a distinct CLI exit code (see failure-modes table). No bare `Exception`.
  - **No retries.** Same Phase 3 discipline. The three-retry default (ADR-0014) is Phase 5's gate machinery; Phase 4 fails fast. Transport-layer retries (`anthropic.APIStatusError` for 5xx and 429) live inside `AnthropicClient` only.
- **Dependencies:** `pydantic`, `codegenie.recipes.contract`, `codegenie.rag.*`, `codegenie.llm.*`. **Does not import `anthropic` or `chromadb` directly** — those are encapsulated by `LeafLlmAgent` and `SolvedExampleStore` respectively.
- **Where it lives:** `src/codegenie/recipes/engines/rag_llm.py`.
- **Tradeoffs accepted:**
  - **`similarity_threshold` default of `0.78`.** Empirical guesswork in v0.4.0; calibrated against Phase 4's seed corpus. Configurable via `~/.config/codegenie/llm.yaml`. ADR-P4-006 documents the calibration target.
  - **Engine has no async path.** Phase 3 is sync; the Anthropic SDK supports sync. Async is the right shape in Phase 6 (state machine concurrency); the contract is forward-compatible — `LeafLlmAgent` is class-based so an `AsyncLeafLlmAgent` is a sibling addition.

### 2. `LeafLlmAgent` + `AnthropicClient` — the SDK wrapper

- **Purpose:** Centralize the single `import anthropic` site. Provide a typed input → typed output interface that the rest of the system uses. Emit cost telemetry consistently. Enforce prompt-caching discipline.
- **Public interface:**
  ```python
  # src/codegenie/llm/models.py
  class PromptBlock(BaseModel):
      type: Literal["text"] = "text"
      text: str
      cache_control: dict[str, str] | None = None

  class LlmRequest(BaseModel):
      model: str                           # "claude-opus-4-7-20260415" (pinned)
      system: list[PromptBlock]            # cacheable; cache_breakpoint declared
      messages: list[PromptBlock]          # user message(s)
      max_tokens: int = 8000
      temperature: float = 0.0             # deterministic by default
      stop_sequences: list[str] = []
      run_id: str
      prompt_template_id: str              # for telemetry
      prompt_template_version: str

  class LlmResponse(BaseModel):
      text: str
      stop_reason: Literal["end_turn", "max_tokens", "stop_sequence"]
      input_tokens: int
      output_tokens: int
      cache_creation_input_tokens: int
      cache_read_input_tokens: int
      raw_response_path: Path
      model: str
      cost_usd: Decimal                    # computed from rates.yaml

  # src/codegenie/llm/agent.py
  class LeafLlmAgent:
      def __init__(self, client: AnthropicClient, cost_emitter: CostEmitter) -> None: ...
      def available(self) -> bool: ...     # checks ANTHROPIC_API_KEY etc.
      def invoke(self, request: LlmRequest) -> LlmResponse: ...
  ```
- **Internal design:**
  - **Sync client only in Phase 4.** `anthropic.Anthropic(api_key=...)`. Async is the natural Phase 6 add.
  - **Prompt caching mandatory.** Every `LlmRequest.system` block carries `cache_control={"type": "ephemeral"}` on the *system prompt* and on *the retrieved solved example*. The user message (per-run RepoContext slice + advisory) is *not* cached. This matches the RAG few-shot pattern in ADR-0011: system prompt + retrieved example are stable across retries; per-run data is not.
  - **Pinned model version.** `claude-opus-4-7-20260415` (the current production model) is pinned in `~/.config/codegenie/llm.yaml`. Pinning is non-negotiable — model drift is the worst silent failure mode for an LLM-using component. Bumping the model is an ADR amendment.
  - **No tool use in Phase 4.** The leaf produces a unified diff as text inside a `<patch>...</patch>` block; `parse_patch` extracts it. Phase 5/6 add tool use when the sandbox feedback loop needs it.
  - **Cost computed locally** from a pinned rate table at `src/codegenie/llm/rates.yaml`. Anthropic's response `usage` fields are the source of truth for token counts; the rate table is the source of truth for dollar conversion. Rate table updates are ADR-amended.
  - **`AnthropicClient` is a thin wrapper** doing: (a) retries on `anthropic.APIStatusError` for 5xx and 429 (3 retries, exponential backoff, jittered); (b) request/response serialization to disk for VCR; (c) emission of `cost.llm.invoked` audit event. **Application-level retries (the gate-machinery three-retry from ADR-0014) are not here.** Only transport-layer retries.
- **Dependencies:** `anthropic`, `pydantic`, `tenacity` (already a transitive dep of many things; pinned). Stdlib otherwise.
- **Where it lives:** `src/codegenie/llm/client.py`, `agent.py`, `models.py`, `cost.py`.
- **Tradeoffs accepted:**
  - **Sync now, async later.** Async-from-day-one would couple Phase 4 to Phase 6's runtime decision.
  - **Prompt caching as an invariant** rather than an option. A future engineer's instinct will be to bypass the cache for "just this one prompt"; the agent's `invoke` method asserts every `LlmRequest.system` block has a `cache_control` field. CI test covers.

### 3. `PromptLoader` + YAML prompts — prompts as versioned data

- **Purpose:** Externalize every prompt out of Python source code. Make prompt changes git-diffable and revertable. Validate prompts at load time so a malformed prompt is a CLI startup error, not a runtime surprise.
- **Public interface:**
  ```python
  # src/codegenie/llm/models.py
  class PromptTemplate(BaseModel):
      id: str                              # "vuln_remediation.few_shot_rag"
      version: str                         # "1.0.0" — semver
      description: str
      system: list[PromptBlock]            # cacheable blocks
      user_template: str                   # {{var}} syntax only (no logic)
      required_variables: list[str]
      cache_breakpoints: list[Literal["system", "few_shot"]]
      max_tokens: int = 8000
      temperature: float = 0.0

  # src/codegenie/llm/prompt_loader.py
  class PromptLoader:
      def __init__(self, prompts_dir: Path) -> None: ...
      def all_templates_validate(self) -> bool: ...    # for available()
      def load(
          self,
          template_id: str,
          *,
          context: Mapping[str, str],
      ) -> LlmRequest: ...
      def estimate(self, template_id: str, context: Mapping[str, str]) -> int: ...
  ```
- **Internal design:**
  - **One YAML file per (prompt_id, version)** under `src/codegenie/llm/prompts/<task>/<id>.v<n>.yaml`. Two prompts ship in Phase 4: `few_shot_rag.v1.yaml` and `from_scratch.v1.yaml`. Plus a shared `system.v1.yaml` referenced via the `system` block.
  - **Schema-validated at import time.** `PromptLoader.__init__` walks the prompts dir, parses every YAML through `jsonschema` against `_schema.json`, and raises `PromptTemplateInvalid` on any failure. **Malformed prompt → CLI exit code 11 at startup.**
  - **Variable substitution is intentionally minimal** — `{{varname}}` only. No filters, no loops, no logic. If a prompt needs computation, the computation goes in Python and the result is passed as a string. The forbidden alternative (a full Jinja2 environment) couples the Phase 4 prompt surface to a templating language's quirks; explicitly out of scope.
  - **No inline f-strings in Python that build prompt text.** Enforced by a Phase 4 `fence` extension: AST scan of `src/codegenie/llm/` and `src/codegenie/recipes/engines/rag_llm.py` for any string literal of length ≥ 200 chars and any f-string containing `system:` / `user:` / `assistant:` keywords. Tripping this is a CI failure.
- **Example prompt** (`src/codegenie/llm/prompts/vuln_remediation/few_shot_rag.v1.yaml`):
  ```yaml
  id: vuln_remediation.few_shot_rag
  version: "1.0.0"
  description: |
    Generate a unified diff that remediates the advisory, grounded in a
    matched solved example. Reserved for cases where the deterministic
    recipe engines returned a non-matched reason.
  cache_breakpoints: ["system", "few_shot"]
  required_variables:
    - advisory_summary
    - repo_summary
    - solved_example_id
    - solved_example_advisory
    - solved_example_patch
    - file_inventory
  max_tokens: 8000
  temperature: 0.0
  system:
    - type: text
      text: |
        You are a deterministic patch generator. You produce one unified
        diff inside a <patch>...</patch> block. You do not explain.
      cache_control:
        type: ephemeral
    - type: text
      text: |
        Reference solved example:
        ID: {{solved_example_id}}
        Original advisory: {{solved_example_advisory}}
        Original patch:
        ```diff
        {{solved_example_patch}}
        ```
      cache_control:
        type: ephemeral
  user_template: |
    Advisory: {{advisory_summary}}
    Repository: {{repo_summary}}
    File inventory: {{file_inventory}}

    Produce the unified diff inside <patch>...</patch>.
  ```
- **Dependencies:** `pydantic`, `pyyaml` (via Phase 1's `safe_yaml`), `jsonschema` (already a Phase 0 dep).
- **Where it lives:** `src/codegenie/llm/prompt_loader.py`, `src/codegenie/llm/prompts/`.
- **Tradeoffs accepted:**
  - **Minimal templating language.** Engineers will want loops eventually. When they do, they should encode the loop as a Python helper that produces a pre-formatted string; the prompt-template language stays small.
  - **One file per version.** Bumping a prompt = creating `*.v2.yaml`. The `id` field is the stable handle; `version` evolves. Phase 4 ships `v1` files only.

### 4. `SolvedExampleStore` — the chromadb wrapper

- **Purpose:** Persist solved examples; retrieve top-k by similarity to a query fingerprint. Encapsulate `chromadb` so the rest of the system doesn't import it.
- **Public interface:**
  ```python
  # src/codegenie/rag/models.py
  class SolvedExample(BaseModel):
      id: str                              # "se-" + blake3(cve_id+repo_sig+timestamp)
      cve_id: str
      repo_signature: str                  # blake3(language|framework|runtime|...)
      advisory_summary: str                # short, ≤ 1000 chars
      recipe_attempted: str | None         # "ncu" / "openrewrite" / "rag_llm" / None
      recipe_failure_reason: Literal[      # mirrors Phase 3's RecipeSelection.reason
          "matched", "no_engine", "range_break",
          "peer_dep_conflict", "unsupported_dialect", "catalog_miss"
      ] | None
      llm_provided_patch: bytes            # the diff bytes
      patch_target_files: list[str]
      validation_outcome: dict             # frozen dump of Phase 3 ValidatorOutput
      cost_summary: dict                   # frozen dump of CostReport
      timestamps: dict                     # {"created_at": ..., "validated_at": ...}
      provenance: dict                     # {"run_id": ..., "engine_used": ...}
      embedding_model_digest: str          # which model embedded this; freshness gate
      schema_version: Literal["1.0.0"] = "1.0.0"

  class RetrievedExample(BaseModel):
      example: SolvedExample
      similarity: float                    # cosine, [0,1]
      retrieved_at: datetime

  # src/codegenie/rag/store.py
  class SolvedExampleStore:
      def __init__(
          self,
          db_path: Path,
          provider: EmbeddingProvider,
      ) -> None: ...
      def opens_cleanly(self) -> bool: ...
      def add(self, example: SolvedExample) -> None: ...
      def query(self, fingerprint: str, *, top_k: int = 5) -> list[RetrievedExample]: ...
      def count(self) -> int: ...
      def health(self) -> StoreHealth: ...  # for SolvedExampleHealthProbe
      def prune(self, predicate: Callable[[SolvedExample], bool]) -> int: ...
  ```
- **Internal design:**
  - **Embedded chromadb** (`chromadb.PersistentClient(path=...)`) under `.codegenie/rag/solved-examples/`. Single-process, no daemon, no docker.
  - **Two-table model.** The chromadb collection holds `(id, embedding, metadata)`. The `metadata` is the *small* dict (cve_id, repo_signature, similarity-relevant scalars). The *full* `SolvedExample` body lives as a sibling JSON file at `.codegenie/rag/bodies/<id>.json`. Why split: chromadb metadata has size limits and stringly-typed serialization quirks; JSON files are the source of truth; chromadb is the index. Same split Phase 1's content-addressed cache uses (chromadb = index; FS = bodies).
  - **Idempotent insert.** `add` is keyed by `id`; re-adding the same example is a no-op (deduplication is structural).
  - **Embedding model digest stored on every example.** Querying with a different embedding model is a `EmbeddingModelMismatch` warning surfaced via `health()`; never silently mixed.
  - **`opens_cleanly` is the lightweight version of `health`** — checks the directory exists, chromadb opens without error, ≥ 0 examples present. Used by `RagLlmEngine.available()`.
- **Dependencies:** `chromadb`, `pydantic`, `codegenie.rag.embeddings.contract.EmbeddingProvider`.
- **Where it lives:** `src/codegenie/rag/store.py`.
- **Tradeoffs accepted:**
  - **chromadb over qdrant.** Trades a slightly clunkier API for zero ops overhead. Phase 9+ swaps behind the same `SolvedExampleStore` interface (the public methods are vector-DB-agnostic). The chromadb embedded mode is well-supported and battle-tested. ADR-P4-003 captures the swap-out path.
  - **JSON bodies on disk, not in chromadb.** Larger disk footprint, simpler debugging (you can `cat` a solved example), forward-compatible with any swap target.

### 5. `EmbeddingProvider` ABC + `SentenceTransformerProvider` + `VoyageProvider` stub

- **Purpose:** Encapsulate the embedding model choice. CI must be hermetic; local sentence-transformers is the default. Voyage is a registered second provider for environments where API egress is acceptable.
- **Public interface:**
  ```python
  # src/codegenie/rag/embeddings/contract.py
  class EmbeddingProvider(ABC):
      name: str
      model_id: str                        # "BAAI/bge-small-en-v1.5"
      dimensions: int                      # 384 for bge-small
      model_digest: str                    # SHA-pinned

      @abstractmethod
      def available(self) -> bool: ...
      @abstractmethod
      def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

  # src/codegenie/rag/embeddings/local.py
  @register_embedding_provider
  class SentenceTransformerProvider(EmbeddingProvider):
      name = "sentence_transformers"
      model_id = "BAAI/bge-small-en-v1.5"
      dimensions = 384
      model_digest = "<sha256 of safetensors snapshot>"
      ...

  # src/codegenie/rag/embeddings/voyage.py
  @register_embedding_provider
  class VoyageProvider(EmbeddingProvider):
      """Opt-in. Available() returns True only if VOYAGE_API_KEY is set."""
      name = "voyage"
      ...
  ```
- **Internal design:**
  - **Registry decorator parallel to `@register_recipe_engine`** and `@register_probe`. Same shape; same idiom.
  - **Default selection by config.** `~/.config/codegenie/llm.yaml#embedding_provider` (default `sentence_transformers`). Picked at `SolvedExampleStore.__init__`.
  - **SHA-pinned model download.** `huggingface_hub.snapshot_download(repo_id, revision=<commit_sha>)` — pinning a specific revision, not the latest. Cache under `~/.cache/codegenie/models/`. First-run is the only network operation in the embedding path; subsequent runs are pure-local. Pin updates are ADR-amended (analog of Phase 2's `digests.yaml` discipline).
  - **`available()` checks two things:** (1) the model is on disk at the pinned digest; (2) `dimensions` matches whatever the store expects.
- **Dependencies:** `sentence-transformers`, `huggingface_hub` (local); `voyageai` (stub only — not added as a Phase 4 dep; only the import contract is wired in case operators want to install it).
- **Where it lives:** `src/codegenie/rag/embeddings/`.
- **Tradeoffs accepted:**
  - **Local model is ~120 MB on disk.** Acceptable for a developer tool; Phase 9 service mode may swap to a smaller / API-based provider.
  - **Embedding dimensionality is fixed per provider.** Mixing examples embedded by different providers in the same collection is a `dimensions` mismatch — `SolvedExampleStore.health()` surfaces this loudly.

### 6. `LlmInvocationGuard` — the smallest cost-cap enforcement

- **Purpose:** Refuse to issue an Anthropic call whose worst-case cost (estimated input + output tokens × pinned rate) exceeds the per-invocation ceiling. Phase 13's full Budget Enforcer subsumes this.
- **Public interface:**
  ```python
  # src/codegenie/llm/guard.py
  class LlmInvocationGuard:
      def __init__(self, ceiling_usd: Decimal, rates: RateTable) -> None: ...
      def check_budget(self, request: LlmRequest) -> None:
          """Raises CostCeilingBreached if estimated cost > ceiling_usd."""
  ```
- **Internal design:**
  - **Estimate input tokens** by character count ÷ 4 (chosen as a conservative upper bound; documented; calibrated against actual ratios on a fixture corpus). Estimate output tokens at `max_tokens` (worst case).
  - **Multiply by pinned rate, compare to ceiling.** If over, raise. Operator can opt in via `--allow-cost-overrun=<usd>` flag.
  - **No global state.** The guard is constructed once per orchestrator invocation; its decision is per-call, deterministic, idempotent.
- **Dependencies:** `pydantic`, stdlib `Decimal`.
- **Where it lives:** `src/codegenie/llm/guard.py`.
- **Tradeoffs accepted:**
  - **Token estimation is approximate.** A pathological input could underestimate by 20%+. The ceiling default is `$5.00`, deliberately well above expected per-invocation cost (~$0.10–$0.50 for Phase 4 use cases). The point is to prevent disaster, not micro-manage budget. Phase 13 lands per-workflow with the proper token-counting middleware.
  - **No multi-call budget.** Phase 13.

### 7. `writeback_solved_example` — the closing of the RAG loop

- **Purpose:** When a `rag_llm`-produced patch passes Phase 3's `TrustScorer`, persist the example so the next workflow on a similar problem hits RAG instead of LLM. **This is the function that makes Phase 4's exit criterion possible.**
- **Public interface:**
  ```python
  # src/codegenie/rag/writeback.py
  def writeback_solved_example(
      *,
      run_id: str,
      advisory: Advisory,
      recipe_selection: RecipeSelection,
      recipe_application: RecipeApplication,
      validation_outcome: list[ValidatorOutput],
      cost_report: CostReport,
      store: SolvedExampleStore,
  ) -> SolvedExample: ...
  ```
- **Internal design:**
  - **One pure function**, not a class. Called by the orchestrator at exactly one point: after `TrustScorer.score(signals).passed` and before `PatchBranchWriter` finalizes the report, gated on `recipe_application.engine_used == "rag_llm"`.
  - **Idempotent.** Called twice with the same `run_id` is a no-op (the `id` field is deterministic from inputs).
  - **Validation-passing only.** A failed run does *not* write back — the solved-example store contains successes only. Failures are reflected by the *absence* of a writeback; the audit log still records the LLM call attempt.
  - **Emits a `solved_example.written` audit event** with the example id, fingerprint, embedding model digest, and the validation-outcome summary.
- **Dependencies:** `pydantic`, `codegenie.rag.*`.
- **Where it lives:** `src/codegenie/rag/writeback.py`.
- **Tradeoffs accepted:**
  - **Only one writeback site.** Future phases (Phase 5's retry-and-recover, Phase 6's state machine) may want to write back partial / amended examples. The Phase 4 invariant is "successful examples only" — Phase 5+ relax this if/when there's a clear use case. Surfacing the constraint is a deliberate best-practice; relaxing it is reversible.

### 8. `SolvedExampleHealthProbe` — the B2 analog for Phase 4

- **Purpose:** Treat vector-store staleness as a first-class probe, exactly like `IndexHealthProbe` (B2). Silent vector-store rot — e.g., embedding-model drift, dimension mismatch, write failures, growing-but-never-read — is the canonical Phase 4 silent-staleness failure mode.
- **Public interface:** Standard `Probe` ABC. `name = "solved_example_health"`, `declared_inputs = [".codegenie/rag/solved-examples/**"]`, `applies_to_tasks = ["*"]`, `applies_to_languages = ["*"]`.
- **Output:**
  ```python
  class SolvedExampleHealthResult(BaseModel):
      count: int
      embedding_model_digest: str
      provider_name: str
      dimensions: int
      newest_example_age_days: int
      oldest_example_age_days: int
      mixed_embedding_models: bool        # >1 distinct digest in the corpus
      query_latency_p50_ms: float         # measured with 3 synthetic queries
      confidence: Confidence              # standard Phase 1 confidence enum
  ```
- **Internal design:** Reads the store via `SolvedExampleStore.health()`. Emits `low` confidence if `mixed_embedding_models` is true or `count == 0`. Emits `medium` if `newest_example_age_days > 30` (corpus going stale). Emits `high` otherwise. **This probe's `confidence` will eventually be a Phase 5 gate input** (analog of how `IndexHealthProbe.confidence` gates Phase 3); Phase 4 surfaces it but does not gate on it.
- **Dependencies:** `pydantic`, `codegenie.rag.*`.
- **Where it lives:** `src/codegenie/probes/solved_example_health.py`.
- **Tradeoffs accepted:**
  - **One more probe** is one more thing to maintain. Worth it: the whole point of the Phase 1 lens was that probes are how we capture facts about the system's own health. The RAG store needs its own.

### 9. CLI surface — one new subcommand group, three new `remediate` flags

- **Purpose:** Inspect, list, and prune the solved-example store. Mirrors the Phase 3 `codegenie cve sync` shape.
- **Public interface:**
  ```
  codegenie solved-examples list [--cve <id>] [--engine <name>] [--since DATE]
  codegenie solved-examples show <id>
  codegenie solved-examples prune --failed-validation
  codegenie solved-examples prune --older-than <days>
  codegenie solved-examples prune --model-digest <digest>   # for embedding-model migrations
  codegenie solved-examples health                          # invokes the probe; prints result
  ```
- **New flags on `codegenie remediate`:**
  - `codegenie remediate --no-llm` — force recipe-only (skip `RagLlmEngine`). Useful for hot-fix workflows that must not spend tokens.
  - `codegenie remediate --no-rag` — invoke `RagLlmEngine` but skip the RAG retrieval step; use only the from-scratch prompt. Diagnostic.
  - `codegenie remediate --allow-cost-overrun <usd>` — raises the `LlmInvocationGuard` ceiling for the run.
- **Dependencies:** `click`, `pydantic`. Same Phase 0/1/2/3 pattern.
- **Where it lives:** `src/codegenie/cli/solved_examples.py`.

---

## Data flow

End-to-end run for `codegenie remediate ./services/auth --cve CVE-2026-FAKE-NPM` where the deterministic engines miss (e.g., a major-version-bump breaking change):

1. **Stage 0–2** (Phase 3) unchanged: tool readiness, load `RepoContext`, resolve advisory.
2. **Stage 3 — Select Recipe:**
   - `RecipeSelector` iterates engines in order:
     - `NcuRecipeEngine.applies(advisory, repo_ctx) → False` (advisory marks a major bump; recipe matches patch range only).
     - `OpenRewriteEngineStub.applies(advisory, repo_ctx) → False` (no JVM-shaped npm recipe in the stub catalog).
     - `RagLlmEngine.applies(advisory, repo_ctx) → True` (engine is the fallback; always applies if available).
   - Selector returns `RecipeSelection(recipe=<synthetic rag_llm recipe>, reason="matched", diagnostics={previous_engines: ["ncu/range_break", "openrewrite/catalog_miss"]})`.
3. **Stage 4 — Lockfile policy scan** (Phase 3) runs on the pre-transform tree as usual. Passes.
4. **Stage 5 — Apply Transform** invokes `NpmPackageUpgradeTransform.run(input)`, which dispatches to the selected engine: `RagLlmEngine.apply(recipe, repo, ctx)`:
   - **a. Fingerprint.** `compute_fp(advisory, repo_ctx)` returns a stable string keyed on `(cve_id, package_name, vulnerable_range, language, framework, runtime_major_version, dep_graph_neighborhood_hash)`. Deterministic; no LLM.
   - **b. RAG retrieve.** `SolvedExampleStore.query(fingerprint, top_k=5)` → `list[RetrievedExample]`. Embedding of the fingerprint happens inside the store via the registered `EmbeddingProvider`. Best similarity is `0.62`.
   - **c. Prompt choice.** `0.62 < 0.78` threshold → `prompt_kind = "from_scratch"`.
   - **d. Cost-cap precheck.** `LlmInvocationGuard.check_budget(request)` — estimated cost `$0.24` < ceiling `$5.00` → pass.
   - **e. LLM invoke.** `LeafLlmAgent.invoke(request)`:
     - `AnthropicClient` does the HTTP. `pytest-recording` cassette in tests; real HTTP otherwise.
     - `system` block has `cache_control={"type": "ephemeral"}`. The system prompt is cached; first cold call pays creation; warm calls pay read.
     - Response captured to disk at `.codegenie/remediation/<run-id>/llm/response.json`.
     - Cost computed locally from `rates.yaml`; `cost.llm.invoked` audit event emitted.
   - **f. Parse patch.** Extract the `<patch>...</patch>` block; validate it's a well-formed unified diff via `unidiff` (already a Phase 3 transitive dep). On parse failure → `PatchParseFailed` → exit code 5 (`transform_fail`).
   - **g. Materialize `RecipeApplication`.** Same shape as Ncu / OpenRewriteStub return. `engine_used="rag_llm"`.
5. **Stage 5 cont — LockfileResolver** runs on the post-transform tree (Phase 3, unchanged).
6. **Stage 6 — Validate** (Phase 3, unchanged). `npm ci`, `npm test`, opt-in build. Emits `ValidatorOutput`s.
7. **Stage 7 — Trust score** (Phase 3). Strict-AND of objective signals. **Includes** `tests.exit_status == 0`; **does not include** any LLM self-confidence. If passes:
   - **Stage 7b — `writeback_solved_example`** is invoked (Phase 4 addition). The example lands in the store; the next workflow with a similar fingerprint sees the cosine similarity climb above 0.78.
   - **Branch + report** finalized (Phase 3).
8. **Re-run on the same CVE against a similar repo** — Stage 3 selector picks `RagLlmEngine`; Step b finds the just-written example at similarity ≥ 0.78; Step c picks `few_shot_rag`; Step e issues the LLM call *with the matched example as cached few-shot context* — input tokens drop, cache_read_tokens rise, cost falls. **The exit criterion is met:** the LLM-fallback case re-runs and hits RAG.

---

## Failure modes & recovery

Prefer explicit, typed errors. Each maps to a CLI exit code.

| Failure | Detected by | Containment | Recovery | Exit code |
|---|---|---|---|---|
| `ANTHROPIC_API_KEY` missing | `LeafLlmAgent.available()` | `RagLlmEngine.available() → False`; selector falls through to `reason="no_engine"` | Operator sets env var | 4 (`no_recipe`) — Phase 3 path |
| Embedding model not on disk | `SentenceTransformerProvider.available()` | Store opens with degraded health; `RagLlmEngine.available() → False` | Operator runs `codegenie models fetch` (a tiny new utility) | 4 |
| chromadb store corrupt | `SolvedExampleStore.opens_cleanly()` | Engine unavailable; orchestrator surfaces; advisory says "no LLM fallback possible" | Operator runs `codegenie solved-examples prune --rebuild` | 4 |
| `RagRetrievalFailed` | `SolvedExampleStore.query` raises | Treated as "no examples retrieved"; engine continues with `from_scratch` prompt | None needed — degrades gracefully | n/a (continues) |
| `EmbeddingFailed` (provider error) | `EmbeddingProvider.embed` raises | Engine fails fast; exits with `confidence: low` | Operator inspects logs | 5 (`transform_fail`) |
| `LlmCallFailed` (network, auth, model not found) | `AnthropicClient` after transport retries | Engine fails fast; explicit error in `RecipeApplication.exit_code` | Operator inspects logs; checks API key validity | 5 |
| `CostCeilingBreached` | `LlmInvocationGuard.check_budget` | Engine refuses to invoke; exits before any API call | Operator uses `--allow-cost-overrun` if warranted | 9 (`cost_ceiling`) |
| `PatchParseFailed` (no `<patch>` block) | `parse_patch` | Engine emits `errors=["patch_not_found"]`; orchestrator exits | None automated; Phase 5 retry-with-context | 5 |
| Patch parses but diff doesn't apply | Phase 3 `git apply --check` | `TransformOutput.warnings=[...]`; orchestrator continues to validator which will fail | None automated; Phase 5 retry | 6 (`validation_fail`) — Phase 3 path |
| `EmbeddingModelMismatch` (writeback with different dim) | `SolvedExampleStore.add` | Refuses write; surfaces via `solved_example_health.confidence = low` | Operator runs `prune --model-digest <old>` | n/a (orchestrator continues; example simply not persisted; loud warning) |
| `PromptTemplateInvalid` (malformed YAML) | `PromptLoader.__init__` | CLI startup fails | Fix prompt YAML | 11 (`config_invalid`) |
| `SolvedExampleWritebackFailed` (FS or chromadb error) | `writeback_solved_example` | Writeback aborts; orchestrator continues (branch + report still written) | Operator inspects FS; loud warning in `remediation-report.yaml` | 0 (success, with warning) |
| Anthropic API 429 / 5xx | `AnthropicClient` | Transport retry ≤ 3 with exp backoff; persistent → `LlmCallFailed` | None automated | 5 |
| Cassette miss in CI (`--record-mode=none`) | `pytest-recording` | Test fails loud | Engineer re-records locally + reviews diff + commits | n/a (CI failure) |

---

## Resource & cost profile

- **Tokens per run:**
  - Recipe matched (Ncu / OpenRewrite hits): **0 tokens.**
  - RAG hit, LLM with cached few-shot: **2–6k input + 1–3k output**, ~70% input is `cache_read` → **~$0.05–$0.20 per call** at current Sonnet pricing.
  - LLM from scratch: **3–10k input + 2–4k output**, ~50% input is `cache_read` (system prompt cached; per-run context not) → **~$0.15–$0.50 per call.**
  - Hard ceiling per invocation: `$5.00` via `LlmInvocationGuard`.
- **Embedding compute:** ~50 MB resident for the local model; ~100 ms per single-query embedding; ~5 ms per insert (post-warm).
- **Disk:**
  - `.codegenie/rag/solved-examples/` (chromadb): ≤ 200 MB at 10k examples.
  - `.codegenie/rag/bodies/`: ≤ 100 MB at 10k examples (avg ~10 KB / body).
  - `~/.cache/codegenie/models/`: ~120 MB for `bge-small-en-v1.5`.
  - `.codegenie/remediation/<run-id>/llm/`: ≤ 1 MB per run.
- **Network:** Zero outbound from `codegenie remediate` except (a) Anthropic API on LLM invoke, (b) first-time model fetch from Hugging Face. No webhooks; no telemetry beaconing.
- **New `ALLOWED_BINARIES` entries:** **none.** Phase 4 is library-only.
- **New runtime deps installed in target environments:** 4 production deps. Total install size ~ 600 MB (dominated by torch, which sentence-transformers pulls). Documented in ADR-P4-004.

---

## Test plan

### Unit tests (`tests/unit/`)

- `tests/unit/llm/test_prompt_loader.py` — ≥ 8 tests: every shipped prompt validates; malformed YAML raises `PromptTemplateInvalid`; missing required variables raises; variable substitution; cache-control preserved on `system` blocks.
- `tests/unit/llm/test_client.py` — ≥ 6 tests using VCR cassettes: happy path, 429 retry, 5xx retry, persistent failure, cost emission, cache-creation vs cache-read accounting.
- `tests/unit/llm/test_agent.py` — ≥ 6 tests: `invoke` returns typed `LlmResponse`; cost-emitter called with correct payload; `available()` reflects env-var presence.
- `tests/unit/llm/test_guard.py` — ≥ 6 tests: ceiling breach raises `CostCeilingBreached`; `--allow-cost-overrun` raises ceiling; estimation is conservative (input chars / 4 + max_tokens × rate).
- `tests/unit/rag/test_fingerprint.py` — ≥ 6 tests: deterministic for same input; differs for different repo neighborhoods; stable across Python versions (canonical JSON).
- `tests/unit/rag/test_store.py` — ≥ 8 tests: add+query round-trip; idempotent add; embedding-model-digest mismatch surfaces in `health()`; prune drops bodies; `opens_cleanly` on missing dir.
- `tests/unit/rag/embeddings/test_local.py` — ≥ 4 tests: `available()` reflects model presence; embed dimensions match contract; SHA-pinned download.
- `tests/unit/rag/test_writeback.py` — ≥ 6 tests: writes on validation pass; idempotent; refuses on `engine != rag_llm`; refuses on failed validation; emits audit event.
- `tests/unit/recipes/engines/test_rag_llm_engine.py` — ≥ 12 tests (this is the most consequential file): RAG-hit path, RAG-miss path, `available()` false branches (no API key / store corrupt / embedding model missing), cost-cap breach short-circuits, patch-parse failure, every typed error raised at the right boundary, `engine_used` correctly stamped on `RecipeApplication`.
- `tests/unit/probes/test_solved_example_health.py` — ≥ 6 tests: `count=0` → low; mixed model digests → low; warm store → high; query-latency-p50 measured.
- `tests/unit/cli/test_solved_examples.py` — ≥ 8 tests: `list`, `show`, `prune --failed-validation`, `prune --older-than`, `prune --model-digest`, `health`. All output JSON-stable.

### Integration tests (`tests/integration/`)

- `tests/integration/test_remediate_llm_from_scratch_e2e.py` — fixture: a Node repo with a major-version-bump CVE that no Ncu recipe handles. **Cassette-driven** end-to-end run. Asserts: orchestrator selects `RagLlmEngine`; LLM is invoked with `from_scratch` prompt; the patch applies; the validation gate passes; writeback persists the example; exit code 0.
- `tests/integration/test_remediate_rag_hit_after_llm_e2e.py` — runs the same fixture twice in sequence. First run: LLM from scratch (cassette A). Second run: a similar fixture (shared fingerprint via repo signature). Asserts: second run finds the first-run example at similarity ≥ 0.78; uses `few_shot_rag` prompt (cassette B); `cache_read_input_tokens > 0`; cost is lower than first run. **This is the exit-criterion test.**
- `tests/integration/test_remediate_no_llm_flag.py` — `--no-llm` skips the engine even when previous engines miss; orchestrator exits with code 4 (`no_recipe`).
- `tests/integration/test_remediate_cost_ceiling_breach.py` — set ceiling to `$0.01`; assert `CostCeilingBreached` and exit code 9.
- `tests/integration/test_remediate_no_rag_flag.py` — `--no-rag` invokes LLM with `from_scratch` prompt even when a high-similarity example exists; asserts cassette path matches the no-rag prompt.
- `tests/integration/test_phase3_unchanged.py` — re-runs every Phase 3 integration test verbatim. Asserts Phase 3's deterministic paths produce byte-identical outputs (no Phase 4 regression).
- `tests/integration/test_solved_example_health_probe.py` — runs the probe against a populated store; asserts the health output matches the schema.

### E2E (minimal set)

- `tests/e2e/test_breaking_change_vuln_end_to_end.py` — **the roadmap exit criterion.** A real CVE fixture (e.g., a known major-version bump that broke a real OSS repo's API) with cassettes recorded once and reviewed by hand. Asserts: first run → LLM fallback path, patch applied, tests pass, branch written, solved example stored. Second run on a synthetic-but-similar repo → RAG hit, lower cost, equivalent patch.

### Golden files

- `tests/golden/prompts/` — for each prompt + each fixture context, the resolved prompt text is golden'd. Regression on prompt-rendering is visible in PRs. `pytest --update-goldens` regenerates.
- `tests/golden/solved_examples/` — three frozen `SolvedExample` JSON files used by the integration tests. Schema drift = CI red.

### Property tests

- `tests/unit/rag/test_fingerprint_property.py` — Hypothesis: same `(advisory, repo_ctx)` always produces same fingerprint; small `repo_ctx` perturbations produce *different* fingerprints; whitespace in JSON keys does not affect fingerprint (canonical JSON enforced).
- `tests/unit/rag/test_store_property.py` — Hypothesis: `add` then `query` returns the added example at similarity 1.0 ± ε; prune-then-query never returns pruned ids.
- `tests/unit/llm/test_prompt_loader_property.py` — Hypothesis: `load(id, context)` is total over valid contexts; any context missing a required variable raises `PromptVariableMissing` with the variable name.

### VCR cassette discipline

- **Where:** `tests/cassettes/<test_module>/<test_function>.yaml`.
- **Record mode in CI:** `--record-mode=none`. Any test that triggers a real HTTP call fails loud.
- **Re-recording:** Engineer runs `pytest --record-mode=once tests/integration/test_remediate_llm_from_scratch_e2e.py`. The new cassette appears in the diff and **requires explicit human review in the PR** — a `LABEL_REQUIRED: cassettes-reviewed` GitHub label gates merge.
- **Sanitization:** Pre-commit hook (`scripts/sanitize_cassettes.py`) strips `x-api-key`, `authorization`, `cookie`, `set-cookie`. The `anthropic-version` header is kept (not secret; useful for debugging). The hook runs on every commit; CI re-runs it as a gate (assert no sanitization-changing diffs in staged cassettes).
- **Cassette schema check:** Each cassette is YAML-validated by `vcrpy`'s loader at test collection time. Malformed cassette = test errors out before running.
- **Cassette freshness:** Cassettes carry the `model: claude-...` request body. If the pinned model in `~/.config/codegenie/llm.yaml` changes, a CI script (`scripts/cassette_freshness.py`) reports every cassette whose recorded model differs — the PR that bumps the model must re-record all cassettes or explain why not.
- **No live calls in `tests/unit/`.** Unit tests use `unittest.mock` for the Anthropic client; only `tests/integration/` and `tests/e2e/` use cassettes.

### Test pyramid summary

```
                 ╱╲
                ╱E2╲          1 test  (the exit criterion)
               ╱────╲
              ╱ INT  ╲        ~8 tests  (cassette-driven)
             ╱────────╲
            ╱   UNIT   ╲     ~80 tests  (mock-driven; fast)
           ╱────────────╲
          ╱  PROPERTY    ╲    ~6 tests  (Hypothesis; fast)
         ╱────────────────╲
```

---

## Risks (top 5)

1. **The model pin is the most fragile invariant in Phase 4.** Anthropic may deprecate `claude-opus-4-7-20260415` before Phase 13 ships. **Mitigation:** ADR-P4-007 documents the model-bump procedure; `scripts/cassette_freshness.py` keeps cassettes aligned; bumping the model is a single config change + cassette re-record + ADR amendment. **Residual risk:** if Anthropic retires the model mid-quarter, cassettes go stale and a forced upgrade lands faster than planned.
2. **chromadb embedded mode has historically had backwards-incompatible storage format changes.** A chromadb upgrade may invalidate every solved example on disk. **Mitigation:** ADR-P4-003 pins the chromadb minor version and documents the storage-migration path. `SolvedExampleStore.health()` reports the chromadb format version. **Residual:** mid-phase migration may require a one-shot `prune --rebuild` operator action; documented loudly.
3. **The `RagLlmEngine` is the first place the system can hallucinate output.** A patch that *parses* as a diff but *applies wrong* (e.g., wrong file, wrong line numbers) will reach the validator and fail there — but Phase 4's failure mode is "silent low-quality output that wastes a validator run." **Mitigation:** strict-AND trust scoring (Phase 3) catches it; the writeback gate ensures failures don't poison the store; cassette-driven tests pin known-good outputs. **Residual:** the failure rate is empirical and visible only after real-world use.
4. **Prompt drift across phases.** Phase 5 will want to add tool use; Phase 6 will reshape prompts for the state machine. Without prompt-versioning discipline, each phase invents new templates and the prompt-as-data invariant erodes. **Mitigation:** prompt schema validation at load time; one ADR per prompt-shape change; the prompt-loader's `version` field is the wire. **Residual:** the discipline is enforced by review, not by code.
5. **The exit-criterion test is brittle to cassette regeneration.** "Solve a breaking-change vuln end-to-end" is the single most consequential test in Phase 4. If its cassettes need re-recording mid-implementation, the *human review* step in the cassette-recording flow becomes the bottleneck. **Mitigation:** the cassette PR includes a structured "what changed" section; an engineer cross-checks the diff (`request`, `response`, token counts, cost) before approving; the test reads cassettes deterministically thereafter.

---

## Acknowledged blind spots

1. **Embedding quality calibration is empirical.** `BAAI/bge-small-en-v1.5` is a 384-dim model trained on general text; vulnerability fingerprints may not embed well. The 0.78 similarity threshold is a guess. Phase 4 ships with the threshold configurable; calibration is a Phase 5+ activity once a real corpus exists.
2. **No prompt-injection defense in the few-shot RAG path.** A solved example, once written, becomes few-shot context for future calls. If a solved example's `advisory_summary` or `patch` contains a prompt-injection payload, future calls inherit it. **Mitigation deferred to Phase 5 (sandboxing) and Phase 11 (KG writeback security).** Phase 4 mitigation: the writeback path only persists patches that passed Phase 3's strict-AND validation gate, which limits attacker control over content. Surfaced as ADR-P4-008.
3. **No fallback for Anthropic outage.** When the API is down, Phase 4 fails. No multi-vendor SDK shim per ADR-0020's deferral. **Acceptable:** Anthropic API uptime is high; Phase 16's production-hardening lands the shim if/when needed.
4. **The cost ceiling is per-invocation, not per-workflow.** A pathological workflow could invoke the engine multiple times (it can't, in Phase 4 — the orchestrator is linear and the engine is called once — but Phase 6's state machine reopens this). The Phase 4 ceiling is the right primitive for Phase 4; Phase 6 must extend.
5. **Solved-example store has no GC.** Phase 4 ships `prune --older-than` but no automatic policy. A long-running portfolio will accumulate. Acceptable for Phase 4 scale (≤ 10k examples); Phase 13 / 14 / 15 retune.
6. **`anthropic` SDK version drift.** The SDK's caching API has changed shape across versions. **Mitigation:** version is pinned to a minor; the client's caching-related calls are guarded by an integration test that asserts response carries `cache_creation_input_tokens` and `cache_read_input_tokens` fields. A future SDK version that renames or drops these fields fails the test.

---

## Open questions for the synthesizer

1. **Should `RagLlmEngine` be a single composite engine or a chain of two separately registered engines?** This design picks the composite-engine shape (RAG + LLM together inside `RagLlmEngine`) over a chain (`RagEngine` + `LlmEngine` both registered). Composite is simpler and matches the "RAG is *conditioning*, not a separate decision" framing. The chain would be more orthodox-ADR-0011 ("recipe → RAG → LLM as three discrete tiers"). Performance-first may prefer the chain for partial-failure flexibility (RAG hit but LLM down → still emit the matched example as a recipe?). Surfacing.
2. **Where does the cost-ledger emission live — `llm/cost.py` or extending Phase 3's `audit_writer.py`?** This design picks `llm/cost.py` to keep the cost concern co-located with the LLM dep. Performance / cost lenses may prefer central audit emission. Synthesizer to arbitrate against Phase 13's eventual ledger shape.
3. **Should `LlmInvocationGuard` be in `llm/` or be a Phase 13-shaped cross-cutting middleware now?** This design puts the minimum-viable guard in `llm/guard.py` and explicitly defers the full Budget Enforcer to Phase 13. The security lens may want stricter Phase 4 enforcement.
4. **Cassette review label vs cassette signing.** This design uses GitHub label discipline; a stricter design might sign cassettes with a developer key. The signing path is heavier; the label is cheaper. Surfacing.
5. **Should the writeback record `failed_validation: True` examples too** (for Phase 15 to learn from)? Phase 4's invariant is "successes only," because failures could poison future few-shot context. But Phase 15's recipe-authoring agent will want failures as anti-patterns. Surfacing for synth + Phase 15 designer alignment.
6. **`Recipe.engine` Literal extension — should the synthesizer protect Phase 3's contract more aggressively?** The Phase 3 contract snapshot test will require regeneration when we extend the Literal. The Phase 3 design called this out: "any new engine is an ADR-amended addition." This design treats that as the correct path. A more conservative synthesizer might keep `Recipe.engine: str` and validate at engine-registration time instead.
7. **Should `SolvedExampleHealthProbe` write a confidence floor into a Phase 5 gate?** Phase 4 surfaces the probe and emits its output but does not wire it as a gate input. Phase 5 (Trust gates) is the proper home. Synthesizer to confirm the Phase 4 / Phase 5 boundary.
8. **Embedding model — `BAAI/bge-small-en-v1.5` vs `BAAI/bge-base-en-v1.5` (768-dim).** Best practices says: ship the smaller model first; upgrade based on real recall numbers. The performance lens may push for the larger model from day one. Surfacing.

---

## New ADRs implied

- **ADR-P4-001** — `Recipe.engine` Literal extends from `{ncu,openrewrite}` to `{ncu,openrewrite,rag_llm}`. The single Phase 3 source-code edit Phase 4 requires (other than ADR-P4-002).
- **ADR-P4-002** — `RemediationOrchestrator` gains one conditional branch after `TrustScorer.passed`: `if recipe_application.engine_used == "rag_llm": writeback_solved_example(...)`. Surfaced as an additive coordinator change.
- **ADR-P4-003** — `chromadb` (embedded mode) chosen as Phase 4 vector store; swap-out path to qdrant or pgvector documented for Phase 9+.
- **ADR-P4-004** — `sentence-transformers` + `BAAI/bge-small-en-v1.5` chosen as default embedding provider; CI hermeticity mandate; Voyage registered as opt-in.
- **ADR-P4-005** — `pytest-recording` cassette discipline: `--record-mode=none` in CI; sanitization pre-commit hook; cassette-reviewed PR label.
- **ADR-P4-006** — RAG similarity threshold default `0.78`; configurable; calibration deferred to Phase 5+.
- **ADR-P4-007** — Anthropic model pin discipline: `claude-opus-4-7-20260415` (or current at Phase 4 ship); bump procedure documented.
- **ADR-P4-008** — Prompt-injection threat model for the few-shot RAG path: relies on Phase 3's strict-AND validation gate as the writeback gate; full mitigation deferred to Phase 5.
- **ADR-P4-009** — Prompts as versioned YAML data under `src/codegenie/llm/prompts/`; inline f-string prompt construction forbidden by fence CI.
- **ADR-P4-010** — `LlmInvocationGuard` per-invocation cost ceiling as the smallest enforcement footprint; full Budget Enforcer deferred to Phase 13.
- **ADR-P4-011** — No LangGraph in Phase 4; the leaf agent is a plain typed function; state machine lands in Phase 6.

---

## Conventions check (against `production/design.md §2` and `CLAUDE.md` "Load-bearing architectural commitments")

- **§2.1 No LLM in gather pipeline → enforced.** Fence CI gates `transforms/`, `recipes/` (except `engines/rag_llm.py`), `probes/`, `cve/` from importing `anthropic`, `chromadb`, `sentence-transformers`. ✅
- **§2.2 Facts not judgments.** `LeafLlmAgent` emits a typed `LlmResponse` with token counts and text; no `success` field. `RecipeApplication` from `RagLlmEngine` carries `diff`, `files_changed`, `exit_code`; no `safe_to_apply`. ✅
- **§2.3 Honest confidence.** No LLM self-confidence consumed by any gate. `SolvedExampleHealthProbe` carries `confidence` like `IndexHealthProbe`. ✅
- **§2.4 Determinism over probabilism for structural changes.** LLM is one leaf; everything around it is Phase 3's deterministic machinery. ✅
- **§2.5 Extension by addition.** Two new packages; one new engine file; one new probe; zero edits to Phase 0/1/2 code; two ADR-gated additive edits to Phase 3 (`Recipe.engine` Literal + one coordinator branch). ✅
- **§2.6 Org uniqueness as data.** Prompts are versioned YAML; rates table is YAML; thresholds are YAML; Skills frontmatter additive `applies_to.llm_few_shot`. ✅
- **§2.7 Progressive disclosure.** LLM artifacts under `.codegenie/remediation/<run-id>/llm/`; bodies referenced by id; `remediation-report.yaml` indexes. ✅
- **§2.8 Humans always merge.** No `git push`; no GitHub API; Phase 4 stops at local branch + cost report. ✅
- **§2.9 Cost observability.** Per-call `cost.llm.invoked` events with the exact §3.3 aggregation key; cost-ledger JSONL under `.codegenie/remediation/<run-id>/cost-ledger.jsonl`; rolled up by Phase 13. ✅

### Tensions surfaced explicitly

- **Exit criterion vs. §2.3 (honest confidence) + cassette discipline.** The exit criterion ("a breaking-change vuln solved end-to-end with LLM fallback and recorded into the solved-example store; re-running hits RAG") requires the system to declare a run "successful" and write back. Success is *exactly* the strict-AND of Phase 3's objective signals (`TrustScorer.passed`). The cassette discipline pins the LLM responses. **The tension:** if the pinned LLM response stops applying to the fixture repo (e.g., the fixture's `package.json` shifts), the cassette test breaks. **Mitigation:** the fixture is itself a `.bundle` file (Phase 3 precedent) frozen at a specific tree-sha; cassettes are tied to that sha; both move together via the cassette-reviewed PR label. The tension is real and surfaced.
- **`Recipe.engine` Literal vs. Phase 3 contract snapshot.** The Phase 3 design explicitly froze contracts via snapshot tests. Extending the Literal will require regenerating the snapshot, which is a deliberate-but-loud diff in the Phase 4 PR. **Acceptable:** it's the only Phase 3 source edit Phase 4 needs (other than the coordinator branch in ADR-P4-002), and it's surfaced via ADR-P4-001.
- **Roadmap mentions "langgraph imported minimally" but this design imports nothing.** The roadmap line ("`langgraph` imported minimally — just enough to wrap the leaf agent invocation") is honoured by *not* importing — wrapping a one-node `StateGraph` with a synthetic `interrupt()` adds a runtime dep without delivering runtime value, and the Phase 6 designer will then have to either reconcile or rip out the Phase 4 wrapping. Best practices says: ship the dep when it pays for itself. **The tension is real; the design picks the cheaper-to-reverse direction (add later in Phase 6).** Surfaced for the synthesizer.
