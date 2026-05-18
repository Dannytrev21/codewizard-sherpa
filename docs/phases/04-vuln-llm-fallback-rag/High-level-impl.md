# Phase 04 — Vuln remediation: LLM fallback + solved-example RAG: High-level implementation plan

**Status:** Implementation plan
**Date:** 2026-05-18
**Architecture reference:** [phase-arch-design.md](phase-arch-design.md)
**ADRs:** [ADRs/](ADRs/)
**Source design:** [final-design.md](final-design.md)
**Roadmap reference:** [docs/roadmap.md](../../roadmap.md) §"Phase 4"

## Executive summary

Phase 4 introduces the first LLM-produced bytes the system applies, lifted into a closed `PlanProposal` discriminated union and gated behind a `ProvenanceGate` that spends zero tokens on non-app-layer CVEs. The work lands as two new substrate packages — `src/codegenie/fallback/` (tier, leaf, budget, fence, prompt, plan-outcome) and `src/codegenie/rag/` (store, embedder, retriever, ingest) — composed by a new `FallbackTierPlanRecipeEngine` inside the existing Phase-3 plugin (`plugins/vulnerability-remediation--node--npm/subgraph/`); no edits to Phase 0–3 kernel files. The phase ships with the path-scoped fence amendment (`anthropic` admitted only under `src/codegenie/fallback/leaf/`; `chromadb`/`fastembed`/`onnxruntime` only under `src/codegenie/rag/`), the first `typecheck.typescript` SignalKind into Phase 3's open registry, and inline auto-harvest gated by `TrustOutcome.passed AND confidence == "high"` so the roadmap "second run hits RAG" exit criterion is met by production behavior. Cassette discipline, `cassettes.lock` BLAKE3 manifest, and the `_phase4_local_capability_mint` shim land so Phase 5's already-merged `FallbackTier.run(..., prior_attempts=[])` callsite and Phase 6.5's bench replay both work the day Phase 4 merges.

## Order of operations

This sequence is dictated by **pattern dependencies, fence-CI invariants, and Phase-5 contract pre-commitments** — not by perceived code volume. Newtypes, smart constructors, and Pydantic discriminated unions for the boundary shapes (`PlanProposal`, `SolvedExample`, `BudgetToken`, `RetrievalOutcome`, `PlanOutcome`, `TypecheckNodeSignal`) carry every downstream invariant the rest of the phase depends on, so they land **first**, in Step 1, alongside the path-scoped fence-CI amendment — admitting `anthropic`/`chromadb`/`fastembed`/`onnxruntime` into the package closure without the fence in place would silently break the gather-pipeline closure for the duration of implementation. Step 2 lands `ProvenanceGate` + `LlmInvocationGuard`/`BudgetToken` and `FenceWrapper`/`CanaryGuard`/`PromptBuilder` together because all three are pure, none have external deps, and they form the trust-boundary primitives every subsequent step composes against (capability-as-arg is a function signature property — minting must precede first consumer). Step 3 is the `LeafLlm` Port → `AnthropicLeafAdapter` (Adapter at a hard trust boundary) with `EgressGuard` and cassette-sanitizer discipline; `tests/security/test_cassettes_clean.py` lands in the **same** step the first cassette is recorded so no cassette is ever checked in unscanned. Step 4 builds the RAG substrate kernel — embedder + store + provenance/chain-verify — independent of LLM and queryable in isolation, so the retriever in Step 5 has a stable foundation. Step 5 wires `SolvedExampleRetriever` + the two-threshold band + the calibration smoke test (Gap 6) on top of the kernel. Step 6 composes `FallbackTier` end-to-end including the retry RAG-bypass, registers the `typecheck.typescript` SignalKind into Phase 3's `@register_signal_kind` registry (which must already import cleanly), and lands the first integration tests. Step 7 ships the plugin-side adapter (`FallbackTierPlanRecipeEngine` wired through `plugin.transforms()['plan']`), inline harvest, and the two E2E exit-criterion tests; this is last so the "extension by addition" / "diff touches only the new plugin directory" Phase-7 precondition is verified by the act of merging Step 7 with zero edits to the Phase-3 kernel.

## Step 1 — Establish Phase-4 type substrate + path-scoped fence amendment

**Goal:** Land every Newtype, Pydantic frozen-extra-forbid model, discriminated union, and the fence-CI path-scoping change that the rest of the phase depends on — with nothing else.

**Features delivered:**
- New package skeletons: `src/codegenie/fallback/{__init__.py, plan_proposal.py, plan_outcome.py, types.py}` and `src/codegenie/rag/{__init__.py, models.py, provenance.py, types.py}`.
- Newtypes per arch §Data model: `SolvedExampleId`, `EmbeddingVector`, `StoreDigest`, `Similarity` (smart-constructed `[-1.0, 1.0]`), `ModelId`, `TokenCount` (non-negative), `LeafResponseId`, `BudgetTokenId`, `CassetteId`, `HexNonce` (32 hex chars), `BlobDigest`, `ChainHead`. All under `src/codegenie/fallback/types.py` and `src/codegenie/rag/types.py` — never raw `str`.
- `PlanProposal` closed discriminated union (`dep_bump`, `override`, `callsite_rewrite`, `refuse`) — all `frozen=True, extra="forbid"`; `SandboxedRelativePath`, `PackageId`, `SemverString` reused from Phase 3; `UnifiedDiff` smart constructor rejecting path-escape / binary / `len > 64 KB`.
- `PlanOutcome` Phase-4-local sum type (`AppliedFromRecipe | AppliedFromLlm | RagOnlyApplicable | Refused`) — does **not** widen Phase-3 `RecipeOutcome`.
- `BudgetSnapshot`, `BudgetToken` (with `_marker: Literal["budget_token"]`), `RetrievalOutcome` (`RagHit | RagMiss | RagDegraded`), `Query`, `SolvedExample`, `RecordProvenance`, `TypecheckNodeSignal` Pydantic models.
- `pyproject.toml` adds `anthropic`, `chromadb`, `fastembed`, `onnxruntime` to runtime deps (strict-pinned) and `keyring` (admitted under leaf only).
- `tests/unit/test_pyproject_fence.py` removes `anthropic` from `FORBIDDEN_LLM_SDKS`; **adds** `sentence_transformers`, `torch` to keep the invariant honest (per Gap 5).
- New `tests/fence/test_pyproject_fence_phase4.py`: path-scoped fence — no source under `src/codegenie/{probes,coordinator,cache,output,schema}/` imports any of `{anthropic, chromadb, fastembed, onnxruntime}` ∪ `FORBIDDEN_LLM_SDKS`; **only** `src/codegenie/fallback/leaf/anthropic_adapter.py` imports `anthropic`; **only** `src/codegenie/rag/` imports `chromadb`/`fastembed`/`onnxruntime`.
- `import-linter` contract additions mirroring the fence (one per admission).

**Done criteria:**
- [ ] `make typecheck` (mypy --strict) passes against the new packages.
- [ ] `make lint-imports` passes; new contracts present in `pyproject.toml`/`importlinter` config.
- [ ] `tests/unit/test_pyproject_fence.py` and `tests/fence/test_pyproject_fence_phase4.py` both green; deliberately-violating fixtures (a test-only file that imports `anthropic` outside leaf) fail with the diagnostic naming the offending path.
- [ ] Property test: `PlanProposal.model_json_schema()` round-trips through `json.dumps`/`loads`; the four discriminator tags exhaustively cover the union (mypy `assert_never` exhaustiveness asserted in a deliberate-failure test).
- [ ] AST-walk test: every domain identifier in the new packages is a `NewType` (no raw `str` annotations) — pattern-discipline guard mirroring Phase 3.
- [ ] `tests/property/test_plan_outcome_no_recipe_outcome_widening.py` walks Phase-3 `RecipeOutcome` AST and asserts the variant list is byte-identical to the Phase-3 snapshot.
- [ ] Zero edits to `src/codegenie/{probes,coordinator,cache,output,schema}/` (asserted by `tests/fence/test_kernel_frozen.py` — new in this step).

**Depends on:** Phase 3 kernel stable; `RecipeOutcome`, `SandboxedRelativePath`, `PackageId`, `SemverString`, `@register_signal_kind`, `CveAdvisory`, `RepoContext` all in place.

**Effort:** M — substrate is small in lines but every type is contract surface; fence-CI is mechanically delicate.

**Risks specific to this step:**
- Fence amendment is mechanically delicate (Gap 5): honest framing is that the original deny-set **narrows** (anthropic moves out) while the path-scoped fence compensates. Get the wording in the ADR and the test diagnostic message right *before* admitting the dep, or the next 100 PRs run under a silently-broken invariant.
- Pydantic v2 `Discriminator` semantics differ subtly from v1 `Field(discriminator=...)`; pin the v2 idiom in `plan_proposal.py` to match the existing Phase-3 idiom — surface the conflict per Global Rule 7 if Phase-3 used v1 shape.

## Step 2 — Ship trust-boundary primitives: ProvenanceGate, FenceWrapper/CanaryGuard/PromptBuilder, LlmInvocationGuard/BudgetToken

**Goal:** Land the deterministic, side-effect-free primitives that every LLM-touching path must compose against — gate, fence, canary, prompt builder, budget guard — with full unit + property coverage *before* any leaf adapter exists to consume them.

**Features delivered:**
- `src/codegenie/fallback/provenance_gate.py`: `ProvenanceGate.classify(advisory, repo_ctx) -> Provenance`. Delegates to Phase 3 `NpmVulnProvenanceAdapter` (small generalisation; see Step 7 plugin work). Emits `ProvenanceClassified(kind)` always.
- `src/codegenie/fallback/fence/wrapper.py`: `FenceWrapper.fence(payload, source_kind) -> FencedSegment` — pure functional core (`fence_pure`) + imperative-shell audit emission. Per-source-kind truncation caps in module-level `Final` dict (arch table §3); growth requires ADR amendment.
- `src/codegenie/fallback/fence/canary.py`: `CanaryGuard.scan(payload, nonce) -> CanaryResult` — scans **untruncated**; pure-bytes core. `INJECTION_PATTERNS` is module-level `Final` tuple.
- `src/codegenie/fallback/fence/prompt_builder.py`: `PromptBuilder.build(...) -> tuple[TrustedPrompt, FencedPromptBody]` — **sole minting site** for these newtypes (asserted by AST-walking test).
- `src/codegenie/fallback/budget.py`: `LlmInvocationGuard.precharge`/`reconcile`/`running_total`; `BudgetToken` Pydantic frozen-extra-forbid (already declared in Step 1 — wire the issuer here).
- All side-effects (event emission) confined to the imperative-shell wrappers; pure cores are stdlib-only.

**Done criteria:**
- [ ] `tests/property/test_fence_no_escape.py` — Hypothesis over `(payload, nonce)`: `f"</UNTRUSTED_INPUT id={nonce}>"` never appears inside `fence(payload, …).content`. 1000+ runs green.
- [ ] `tests/property/test_canary_scan_untruncated.py` — for any injection-prefixed payload longer than the source-kind cap, `CanaryGuard.scan` fires *before* truncation. Hypothesis green.
- [ ] `tests/adversarial/test_canary_bypass_via_truncation.py` — injection past truncation byte; canary still fires.
- [ ] `tests/property/test_budget_token_non_reuse.py` — `BudgetToken` IDs are uuid4-unique; double-reconcile raises.
- [ ] `tests/unit/fallback/test_prompt_builder_sole_mint_site.py` — AST-walks the codebase and asserts only `prompt_builder.py` constructs `TrustedPrompt` or `FencedPromptBody`.
- [ ] `tests/unit/fallback/test_canary_corpus.py` — 50+ curated injection payloads; each is caught.
- [ ] `tests/unit/fallback/test_provenance_gate.py` — table-driven over all seven `Provenance` variants; refuse-set is exactly `{BaseImage, RuntimeBundled, Unknown}`.
- [ ] Functional-core test: `fence_pure`, `scan_pure` are AST-asserted side-effect-free (no `log.*`, no event emission, no file I/O).
- [ ] `make check` green; coverage on new modules ≥ 95%.

**Depends on:** Step 1 (types + fence-CI).

**Effort:** M — most components are short and pure, but the property + adversarial coverage is the load-bearing assurance and is non-trivial to set up.

**Risks specific to this step:**
- `BudgetToken` flowing through more than two frames is the anti-pattern arch §Anti-patterns flags; resist the temptation to thread it through `PromptBuilder`/`FenceWrapper`. Test enforcement: import-linter contract that only `tier.py` and `leaf/anthropic_adapter.py` reference `BudgetToken`.

## Step 3 — Ship LeafLlm Port + AnthropicLeafAdapter + EgressGuard + cassette discipline

**Goal:** The single seam between Phase 4 and any LLM provider — Port → one Adapter — with the egress guard, cassette sanitizer, and cassette-cleanliness CI scanner all landing together so no cassette is ever checked in unscanned.

**Features delivered:**
- `src/codegenie/fallback/leaf/port.py`: `LeafLlm` Protocol (`async invoke(system_prompt, user_message, *, schema, token) -> LeafResponse`). `LeafResponse` frozen-extra-forbid Pydantic.
- `src/codegenie/fallback/leaf/anthropic_adapter.py`: `AnthropicLeafAdapter` — thin async wrapper over `anthropic.AsyncAnthropic`. Key from `keyring.get_password("codegenie", "anthropic_api_key")` → `SecretStr`. **No `CODEGENIE_ANTHROPIC_KEY_CI` env-var fallback.** Three cached system blocks (skill, instruction template, RAG few-shot when present), each `cache="ephemeral"`. Sets `response_format = schema.model_json_schema()`. **One** in-call retry on JSON-parse failure with appended "your previous response was malformed" instruction. **Three** in-adapter retries on transport `APIStatusError` with backoff (1s/4s/16s); **no** other retries — Phase 5 owns the rest.
- `src/codegenie/fallback/leaf/egress_guard.py`: `EgressGuard.install()` via `sitecustomize.py` wraps `socket.create_connection` — allowlist `api.anthropic.com:443` only. Loopback rejected unless pytest-fixture-set thread-local flag. `EgressGuard.reset_for_test()` exposed. `codegenie self-check egress` CLI subcommand (one liner) reports posture.
- `src/codegenie/fallback/cassette/sanitizer.py`: `pytest_recording` `before_record_request`/`before_record_response` hooks — strip `Authorization`, `X-API-Key`, `Cookie`, `Set-Cookie`, `anthropic-version`; body-scan for `sk-ant-*` / `claude_*` / 40+-char base64-shaped strings. Drop silently in record path.
- `tests/security/test_cassettes_clean.py` — walks `tests/cassettes/` and hard-fails CI on any leaked pattern.
- `tests/cassettes/anthropic/cassettes.lock` — per-cassette BLAKE3 manifest (Phase 6.5 reads this). CI test compares.
- `CODEOWNERS` entry for `tests/cassettes/anthropic/` naming the rotating cassette-steward (Gap 2); `docs/operations/cassettes.md` runbook.
- `make refresh-cassettes` target requiring `--i-understand-this-spends-tokens` and `CODEGENIE_LIVE_LLM=1`.

**Done criteria:**
- [ ] Unit tests: `tests/unit/fallback/test_leaf_adapter.py` covers schema-validation path, single in-call retry on malformed JSON, transport-retry-backoff schedule, key-loading from keyring, refuse-to-start on missing key.
- [ ] `tests/unit/fallback/test_anthropic_response_format.py` — verifies the SDK call passes `response_format=PlanProposal.model_json_schema()`; mocked SDK validates schema shape.
- [ ] `tests/adversarial/test_egress_guard.py` — patches `requests`, `urllib3`, `httpx`, `socket` to attempt forbidden hosts; assert `EgressViolation`; loopback rejected unless thread-local set.
- [ ] `tests/security/test_cassettes_clean.py` runs against every cassette under `tests/cassettes/anthropic/`; deliberate sk-ant-prefixed fixture cassette fails CI loudly.
- [ ] `cassettes.lock` BLAKE3 entries match recorded files; CI fails if cassette body changes without lock update.
- [ ] `tests/fence/test_only_leaf_imports_anthropic.py` AST-walks: only `anthropic_adapter.py` `import anthropic`.
- [ ] First two cassettes recorded against live API for the LLM-from-scratch and RAG-hit scenarios — both pass sanitizer scan.

**Depends on:** Steps 1–2 (`PlanProposal`, `BudgetToken`, `TrustedPrompt`, `FencedPromptBody`).

**Effort:** L — the adapter is small but EgressGuard is a process-wide install with subtle test interactions; cassette discipline + lock file + CODEOWNERS rotates several moving parts.

**Risks specific to this step:**
- `sitecustomize.py` install is import-time side-effect (acknowledged residual): tests **must** explicitly `reset_for_test()` rather than relying on implicit install state, or test order will become load-bearing. Bake this into a `pytest` fixture and document loudly.
- C-extension `connect(2)` bypass acknowledged; `import-linter` restriction on native-extension-using deps is the compensating control — verify the restriction list is non-empty before merging.

## Step 4 — Ship RAG substrate kernel: Embedder + SolvedExampleStore + record provenance

**Goal:** Land the deterministic RAG substrate independently — pinned-model embedder, single-writer chroma store, canonical YAML records, BLAKE3-rolled manifest, chain-verify — so it is queryable in isolation before the retriever (Step 5) composes them.

**Features delivered:**
- `src/codegenie/rag/embedder.py`: `Embedder` Protocol (`embed`, `embed_batch`, `model_digest`). `FastembedEmbedder` wraps `fastembed.TextEmbedding("BAAI/bge-small-en-v1.5")`. Bootstrap-only model fetch: `codegenie embeddings bootstrap` CLI downloads with content-addressed sha256; runtime `__init__` refuses-start on `embeddings_model.lock` hash mismatch.
- `.codegenie/rag/embeddings.cache.sqlite` — BLAKE3(text) → vector cache; cache-aside; lazy-open; rebuild-on-corruption.
- `src/codegenie/rag/store.py`: `SolvedExampleStore` Protocol + `ChromaPersistentStore` over `chromadb.PersistentClient`. One collection per `(task_class, language, build_system)` triple. `add()` guarded by process-local `asyncio.Lock` **with a 30s timeout raising `StoreWriteContention`** (Gap 3). `digest()` = BLAKE3-rolled head over canonical records.
- Canonical YAML at `.codegenie/rag/records/<id>.yaml`; chroma sqlite is **derived**. `codegenie rag rebuild` CLI reconstructs chroma from canonical YAML; `--reembed` re-embeds (Gap 1).
- `.codegenie/rag/manifest.yaml` with `chain_head: ChainHead` (BLAKE3-rolled).
- `src/codegenie/rag/provenance.py`: `RecordProvenance.verify(record, spanning_log) -> bool` — chain verification.
- `src/codegenie/rag/ingest.py`: `SolvedExampleWriter` + `SolvedExampleWriteCapability` (Module-Boundary pattern). `_phase4_local_capability_mint(workflow_id, chain_head)` private factory; `import-linter` contract blocks any module outside `{src/codegenie/gates/, src/codegenie/rag/ingest.py}` from importing the mint symbol.

**Done criteria:**
- [ ] `tests/unit/rag/test_store.py` — open, add, query, digest, close lifecycle; deterministic `digest()` over identical record sets.
- [ ] `tests/unit/rag/test_embedder.py` — refuse-start on lock-hash drift; cache-hit avoids second embed; `model_digest()` stable.
- [ ] `tests/unit/rag/test_provenance_verify.py` — chain-orphan record `verify() == False`; emits `RagRecordChainOrphan` from caller.
- [ ] `tests/property/test_solved_example_yaml_roundtrip.py` — Hypothesis: `from_yaml(to_yaml(x)) == x` for valid `SolvedExample`.
- [ ] `tests/integration/test_phase4_harvest_contention.py` (Gap 3) — two harvest coroutines on the same store under `asyncio.gather` both succeed (sequenced) and chain-head advances monotonically; deliberate timeout fixture raises `StoreWriteContention`.
- [ ] `codegenie rag rebuild` reconstructs chroma deterministically from canonical YAML (golden file: `digest()` byte-identical).
- [ ] `codegenie embeddings bootstrap` is idempotent; CI runs it once and caches model weights.
- [ ] `tests/unit/rag/test_capability_mint_scoped.py` — import-linter contract blocks `from codegenie.rag.ingest import _phase4_local_capability_mint` from any module outside the two allowed callsites.

**Depends on:** Step 1 (types).

**Effort:** L — chromadb embedded mode + fastembed ONNX + the YAML-canonical / chroma-derived split each have edges, and the contention test pins a behavior Phase 11 will conform to.

**Risks specific to this step:**
- Cross-architecture ONNX float drift at the 5th decimal is acknowledged — mitigated by the two-threshold band in Step 5. Don't try to hash embeddings for cache keys; hash the *input text* (BLAKE3) as the cache key per arch §Idempotence.
- chromadb embedded-mode lock semantics are not deeply documented; spike the timeout/contention behavior under `asyncio.gather` early to confirm the 30s wait + raise contract is achievable. If chromadb itself blocks the loop, wrap `store.add` in `loop.run_in_executor` with the asyncio.Lock outside.

## Step 5 — Ship SolvedExampleRetriever + two-threshold band + calibration smoke test

**Goal:** Compose the read-side RAG path — `Query` build → embed → store query → chain-verify → fence retrieved content → classify into `RagHit | RagDegraded | RagMiss` — with thresholds in `plugin.yaml` and a Phase-4 calibration smoke test that fails loud if the defaults are wrong for the fixture portfolio.

**Features delivered:**
- `src/codegenie/rag/retriever.py`: `SolvedExampleRetriever.query(advisory, repo_ctx) -> RetrievalOutcome`. Builds `Query` via plugin's `rag_query_builder` (Step 7 ships the plugin-side builder; this step takes it via injection). Embeds; queries store; per-record verifies `provenance.event_chain_head` against spanning log; fences record content as `source_kind="rag_retrieved"`; classifies similarity per `plugin.yaml` `(high_floor, degraded_floor)`. Excludes records whose `embedding_model != embedder.model_digest()` and emits `RagRecordModelMismatch` (Gap 1, edge case #19).
- `src/codegenie/rag/confidence.py`: pure similarity → `AdapterConfidence` mapping, named-bands instead of magic numbers (`high_floor=0.85`, `degraded_floor=0.65` defaults).
- `tests/integration/test_phase4_threshold_smoke.py` (Gap 6): seeds the store with the four `fixtures/vuln-major-bump/*` solved examples and asserts each fixture's re-run scores `RagHit` (≥ 0.85); crossing-CVE queries score `RagMiss` (< 0.65). Fails Phase-4 merge if defaults are wrong for the shipped fixtures.

**Done criteria:**
- [ ] `tests/unit/rag/test_retriever_thresholds.py` — table-driven over scores in/near both floors; correct band classification; ties go to the lower band.
- [ ] `tests/property/test_retriever_threshold_monotonicity.py` — Hypothesis: higher similarity never yields lower confidence.
- [ ] `tests/integration/test_phase4_threshold_smoke.py` green against fixture portfolio.
- [ ] Chain-orphan record excluded from result set; `RagRecordChainOrphan` emitted; integration assert.
- [ ] `RagMiss` returned (not raised) when store is empty.
- [ ] Embedding-model-mismatch record excluded; `RagRecordModelMismatch(count)` emitted once per query.
- [ ] Retriever performance: p99 ≤ 100ms total (embedding ≤ 80ms + store query ≤ 15ms) on 10K-example seeded store; tracked under `-m bench`.

**Depends on:** Step 4 (store, embedder, provenance).

**Effort:** M — most of the logic is composition; the calibration smoke test is the load-bearing assurance and depends on having representative fixtures ready.

**Risks specific to this step:**
- Calibration smoke test failing at merge time means the defaults are wrong; resolution path is an ADR amendment updating the floors *before* merge, not relaxing the test. Surface loudly per Global Rule 12.

## Step 6 — Compose FallbackTier + register typecheck.typescript SignalKind + integration

**Goal:** Wire the recipe → RAG → LLM dispatch pipeline end-to-end, register the first `typecheck.*` SignalKind into Phase 3's open registry, and prove integration with the Phase-3 orchestrator + Phase-5 retry contract.

**Features delivered:**
- `src/codegenie/fallback/tier.py`: `FallbackTier.__init__(retriever, leaf, budget, fence, canary, provenance, event_log, *, prompt_builder, harvester, confidence_gate)` and `async run(advisory, repo_ctx, recipe_selection, *, prior_attempts=[]) -> RecipeApplication`. Named-sequential pipeline (provenance → budget-precheck → retrieval-or-skip → prompt-build → budget-precharge → leaf-invoke → reconcile → build-transform). Each step emits one audit event. **RAG bypassed when `prior_attempts != []`**; fence-wraps `prior_failure_summary` with `source_kind="prior_attempt_summary"` (ADR-04-0003 documents the departure from ADR-0011 chain order).
- `async on_validated(outcome, trust)` — orchestrator-invoked harvest hook; confidence-gate (`trust.passed AND trust.confidence == "high"`); mints capability via `_phase4_local_capability_mint`; calls `ingest_solved_example`; emits `SolvedExampleHarvested` or `HarvestSkipped(reason)`.
- `plugins/vulnerability-remediation--node--npm/adapters/ts_typecheck_signal.py`: `TypecheckTypescriptSignal` collector decorated with `@register_signal_kind("typecheck.typescript")`. Resolves `./node_modules/.bin/tsc`; runs `tsc --noEmit --pretty false` in Phase 3 `SubprocessJail` (30s cap). **Applicability detection per Gap 4**: presence of `tsconfig.json` + any `.ts` files. Strict-AND with baseline at `.codegenie/typecheck/baseline-<repo-sha>.json`.
- ADR-04-0001 amends `ALLOWED_BINARIES` to admit `./node_modules/.bin/tsc`.
- Typed errors: `LeafProtocolViolation`, `BudgetExceeded`, `EgressViolation`, `Refused(reason=...)`.

**Done criteria:**
- [ ] `tests/unit/fallback/test_fallback_tier.py` — dispatch-order assertion (mock all collaborators; assert sequence of called methods + emitted events).
- [ ] `tests/unit/fallback/test_fallback_tier_retry_bypasses_rag.py` — `prior_attempts != []` ⇒ retriever **not called**; prompt body carries fenced `prior_failure_summary`.
- [ ] `tests/unit/fallback/test_fallback_tier_provenance_short_circuit.py` — `Provenance.BaseImage` ⇒ `Refused(PROVENANCE_NOT_APP_LAYER)`; **`LeafInvoked` event must NOT appear** (event-absence assertion; mocked leaf with `pytest.fail` side-effect).
- [ ] `tests/integration/test_phase4_rag_miss_llm_from_scratch.py` — cassette-driven; full pipeline; RAG empty → leaf called → `PlanProposalCallsiteRewrite` returned → `RecipeApplication` built.
- [ ] `tests/integration/test_phase4_rag_hit_few_shot.py` — pre-seeded RAG hit fed as few-shot; leaf called with cached `system[2]`.
- [ ] `tests/integration/test_phase4_retry_path_bypasses_rag.py` — Phase-5 simulator passes `prior_attempts`; cassette inspection proves fence-wrapped `prior_failure_summary`.
- [ ] `tests/unit/typecheck/test_signal.py` — applicability matrix (Gap 4): four cases — `tsconfig+.ts` (applicable, run tsc), `tsconfig+no .ts` (applicable, 0 errors), `no tsconfig+.ts` (degraded, confidence=medium), `no tsconfig+no .ts` (`passed=True, applicable=False, confidence=high`).
- [ ] `tests/integration/test_typecheck_signal_catches_signature_drift.py` — deliberately-bad cassette response; `tsc` catches it before `npm test`.
- [ ] `tests/unit/trust_scorer/test_typecheck_kind.py` — Phase 3 `TrustScorer` strict-AND folds the new SignalKind without code edits.
- [ ] `tests/fence/test_typecheck_signal_registered.py` — registry contains exactly one `typecheck.*` entry post-import.
- [ ] Determinism property `tests/property/test_determinism_under_cassette_replay.py` — 50 runs with `(cassette_id, store_digest, repo_snapshot_sha, embedding_model_digest)` constant: byte-identical `Transform.diff_bytes` and event order (modulo timestamps).
- [ ] Performance regression `bench_phase4_e2e_cassette_replay` ≤ 35s p50.

**Depends on:** Steps 2, 3, 5; Phase 3 `@register_signal_kind` open registry.

**Effort:** L — full end-to-end composition, deterministic-replay property test, plus the first SignalKind extension into Phase 3's registry.

**Risks specific to this step:**
- The "RAG bypass on retry" behavior deliberately departs from ADR-0011's chain order — ADR-04-0003 must be present and cross-linked from `tests/integration/test_phase4_retry_path_bypasses_rag.py` so the next reader understands it's intentional, not a bug.
- `assert_never` exhaustiveness on `match plan` over `PlanProposal` is mypy --strict-only; CI must run mypy at strict, not just pytest, to catch a missing arm — verify the gate.

## Step 7 — Ship plugin wiring: FallbackTierPlanRecipeEngine + harvest + E2E exit criteria

**Goal:** Land the Adapter that wires `FallbackTier` into the existing Phase-3 plugin's `transforms()['plan']`, prove inline harvest meets the roadmap exit criterion under production behavior, and verify zero edits outside the plugin directory (the Phase-7 precondition).

**Features delivered:**
- `plugins/vulnerability-remediation--node--npm/subgraph/fallback_plan_engine.py`: `FallbackTierPlanRecipeEngine` — implements Phase-3 `RecipeEngine.apply(repo, plan, capability) -> RecipeOutcome`. Constructs `FallbackTier` from plugin-resolved adapters + RAG/LLM substrates; awaits `FallbackTier.run(...)`; projects `RecipeApplication → RecipeOutcome.Applied | RecipeOutcome.NotApplicable | RecipeOutcome.Failed`. Emits Phase-4 `PlanOutcome` to event log alongside the projected `RecipeOutcome`. **Zero edits to `src/codegenie/plugins/protocols.py`.**
- `plugins/vulnerability-remediation--node--npm/recipes/rag_query_builder.py`: builds typed `Query` (no f-strings).
- `plugins/vulnerability-remediation--node--npm/adapters/vuln_provenance.py`: small Phase-3 generalisation lifting `NpmVulnProvenanceAdapter` from refuse-mode to full `Provenance` classification. **Surgical** per Global Rule 3.
- `plugins/vulnerability-remediation--node--npm/skills/{vuln-major-bump.md, leaf-llm-instruction.md}`: prompt template + skill — schema-validated at plugin-load time.
- `plugins/vulnerability-remediation--node--npm/plugin.yaml`: requires `rag_capabilities` + `llm_capabilities`; thresholds (`high_floor=0.85, degraded_floor=0.65`); budget caps (`max_tokens_per_workflow=250000`, `max_dollars_per_workflow=1.50`, `per_call_max_tokens=32000`); embeddings model name; cassette directory.
- Plugin's `transforms()` updated to return `FallbackTierPlanRecipeEngine` for the `plan` slot.
- Fixtures: `fixtures/vuln-major-bump/express-cve-2026-1234/`, `fixtures/vuln-major-bump/lodash-cve-2026-9876/`, `fixtures/vuln-provenance/glibc-on-node/`, `fixtures/vuln-rag-hit/express-rerun/`, `fixtures/vuln-retry/cassette-attempt-1-fails-attempt-2-passes/`.
- `tests/integration/test_phase4_e2e_breaking_change.py` (roadmap exit criterion #1).
- `tests/integration/test_phase4_e2e_replay_lands_rag.py` (roadmap exit criterion #2) — no operator step between runs; `LlmCostAccrued` delta asserted (second run materially cheaper).
- `tests/integration/test_phase4_provenance_short_circuits.py` — asserts no `LeafInvoked` event.
- Adversarial: `tests/adversarial/{test_injection_corpus,test_rag_poisoning_chain_orphan,test_rag_poisoning_runtime_inject,test_plan_path_escape,test_red_team_prompts}.py`.

**Done criteria:**
- [ ] **Roadmap exit criterion #1:** `test_phase4_e2e_breaking_change.py` — express major-bump CVE end-to-end: Phase 3 recipe returns `NotApplicable` → Phase 4 LLM-replan succeeds → Stage 6 strict-AND (build, install, tests, lockfile_policy, cve_delta, **typecheck.typescript**) passes → outcome harvested into store. Green under cassette replay.
- [ ] **Roadmap exit criterion #2:** `test_phase4_e2e_replay_lands_rag.py` — second run on same case hits RAG (`RagHit` observed in events); leaf call shaped by few-shot; `LlmCostAccrued` second-run delta < first-run × 0.5; no operator step between runs.
- [ ] `tests/fence/test_kernel_frozen.py` green: zero edits to Phase 0/1/2/3 kernel files (`src/codegenie/{probes,coordinator,cache,output,schema,plugins/protocols.py}/`); zero edits to `RemediationOrchestrator`, `Plugin` Protocol, `RecipeEngine` Protocol, `Transform` ABC.
- [ ] `tests/integration/test_phase5_contract_snapshot.py` updated to capture additive interface lines from Phase 4 (`FallbackTier.run`, `LlmInvocationGuard.running_total`, `FenceWrapper`, `SolvedExampleWriteCapability` mint surface, `cassettes.lock` format).
- [ ] Adversarial suite (`-m adv`): 200+ injection payloads → 0 escapes; 50+ red-team prompts → 0 successes (any `PlanProposal` outside `SandboxedPath` is a failure).
- [ ] `tests/property/test_plan_outcome_no_recipe_outcome_widening.py` still green — Phase 3 `RecipeOutcome` variants unchanged.
- [ ] `tests/fixtures/fallback_tier_callable.py` published as the contract Phase 6 reads to lift `FallbackTier.run` into a LangGraph node.
- [ ] Documentation: `docs/operations/{secrets.md, cassettes.md, embeddings.md}` runbooks landed.

**Depends on:** Steps 1–6; Phase 3 plugin scaffold; Phase 5 having merged the `FallbackTier.run(prior_attempts=[])` callsite already (per arch G2).

**Effort:** L — fixtures are the slowest moving part; two E2E tests carry the roadmap exit criteria and must pass deterministically under cassette replay.

**Risks specific to this step:**
- If `test_kernel_frozen.py` fails (a sneaky edit to a Phase-3 file slipped in during Steps 1–6), the Phase-7 "diff touches only the new plugin directory" precondition is broken; fail loud per Global Rule 12 and revert.
- The deliberate `_phase4_local_capability_mint` interim-shim ownership is fuzzy until Phase 5 supersedes it; cross-link the Phase-5 ADR from the shim's docstring and add a `# TODO(phase-5): remove this shim once gates._capability_mint lands` so the swap is mechanical.

## Exit-criteria mapping

Phase 4 roadmap exit criteria are:
1. "A breaking-change vuln (e.g., a major-version-bump CVE) is solved end-to-end with the LLM fallback and recorded into the solved-example store."
2. "Re-running the same case hits RAG, not LLM, and produces an equivalent fix at lower cost."
3. "Phase 4's call-site-rewriting failure modes ... `typecheck.node` SignalKind (`tsc --noEmit`) registered via the Phase-3 `@register_signal_kind` open registry."

Plus implied from the Phase 4 plugin-redesign framing:
- Work lands inside `plugins/vulnerability-remediation--node--npm/` + new substrates in `src/codegenie/rag/` and `src/codegenie/fallback/` per ADR-0031.
- `ProvenanceGate` lifted as tier-0 gate per ADR-0038.

| Exit criterion | Step(s) |
|---|---|
| #1 — Breaking-change CVE solved end-to-end + harvested | Step 7 (`test_phase4_e2e_breaking_change.py`), composed of Steps 1–6 |
| #2 — Re-run hits RAG, equivalent fix, lower cost | Step 7 (`test_phase4_e2e_replay_lands_rag.py`), depends on Steps 4–5 (RAG substrate + retriever) and Step 6 (`on_validated` harvest) |
| #3 — `typecheck.typescript` SignalKind via `@register_signal_kind` | Step 6 (registration + strict-AND fold-in tests) + Step 7 (E2E uses it in strict-AND) |
| (Implied) work scoped under `plugins/vulnerability-remediation--node--npm/` + `src/codegenie/{fallback,rag}/` | All steps; Step 7 verifies via `test_kernel_frozen.py` |
| (Implied) `ProvenanceGate` as tier-0 short-circuit | Step 2 (gate primitive) + Step 6 (wired into `FallbackTier`) + Step 7 (E2E `test_phase4_provenance_short_circuits.py`) |
| (Implied — G2) Phase 5 contract preserved | Steps 1, 3, 6 (signatures, projections, fence-sharing) + Step 7 (snapshot test refresh) |
| (Implied — G5) LLM closure fenced; original deny-list invariant preserved | Step 1 (fence amendment + path-scoped fence) — load-bearing |
| (Implied — G7) Provenance gate spends zero LLM tokens on non-app-layer | Step 2 (gate); Step 6 (event-absence assertion); Step 7 (E2E refuse fixture) |
| (Implied — G8) Budget cap as capability | Step 2 (`BudgetToken` + `LlmInvocationGuard`); Step 3 (leaf consumes); Step 6 (tier mints + reconciles) |
| (Implied — G11) Cassette discipline operational | Step 3 (sanitizer + `cassettes.lock` + CI scanner + CODEOWNERS) |
| (Implied — G12) Single allowed egress host (`api.anthropic.com:443`) | Step 3 (`EgressGuard` + adversarial test) |

## Implementation-level risks

1. **Fence amendment is mechanically delicate, and the synthesis claim "original set unchanged" is wrong.** Gap 5 surfaces this honestly: the original `FORBIDDEN_LLM_SDKS` *narrows* (anthropic moves out) and is compensated by the path-scoped fence. Signal: a Phase-3 file silently imports `anthropic` after Step 1 lands. Mitigation: `tests/fence/test_kernel_frozen.py` is a Step-1 deliverable, not a Step-7 one; the ADR text must say "narrows" not "unchanged".

2. **Cassette rot under SDK upgrade.** Six months after Phase 4 ships, an `anthropic` SDK bump silently invalidates ~30 cassettes; nightly drift job catches it but the steward is ambiguous. Signal: nightly job red for >7 days with no PR. Mitigation: the CODEOWNERS entry + `docs/operations/cassettes.md` runbook (Gap 2) lands *in Step 3*, not deferred — the cost of writing it is one hour.

3. **chromadb writer contention behavior under `asyncio.gather`.** Embedded-mode lock semantics not deeply documented; if chroma's own write blocks the event loop, the `asyncio.Lock` outside doesn't help and the 30s-timeout contract is unmet. Signal: `test_phase4_harvest_contention.py` flaky or hangs. Mitigation: spike the contention behavior *first* in Step 4 (small executable script before writing the production code); fall back to `loop.run_in_executor` wrapping `store.add` if chroma blocks. Surface explicitly per Global Rule 12 if the 30s contract can't be met.

4. **Calibration smoke test failure at Phase-4 merge.** `high_floor=0.85` / `degraded_floor=0.65` are educated guesses; the smoke test (Gap 6) may red on the actual fixture portfolio. Signal: `test_phase4_threshold_smoke.py` red. Mitigation: ADR amendment updating the floors before merge — *not* relaxing the test. This is the right shape per Global Rule 12.

5. **`assert_never` exhaustiveness escapes because mypy --strict is skipped locally.** A missing `case` arm on `match plan` over `PlanProposal` silently passes pytest but breaks at runtime when a `Refuse` arrives. Signal: production raises `UnreachableError` first time the LLM refuses. Mitigation: verify CI runs `mypy --strict` as a hard gate (not advisory); add a test that runs mypy on a deliberately-broken fixture and asserts the diagnostic appears.

## What's next — handoff to Phase 5

After Phase 4 ships, Phase 5 (Sandbox + Trust-Aware gates) picks up:

- **`FallbackTier.run(advisory, repo_ctx, recipe_selection, *, prior_attempts: list[AttemptSummary] = []) -> RecipeApplication`** is the exact callsite Phase 5 has already merged against — Phase 5's `GateRunner` re-enters `FallbackTier` on retry with `prior_attempts` populated, and RAG bypasses automatically.
- **`LlmInvocationGuard.running_total()`** is name-stable; Phase 5's `cost.sandbox.run` ledger composes with `cost.llm.call` for Phase 13's ROI rollups.
- **`FenceWrapper`** is shared — Phase 5 fences `AttemptSummary.prior_failure_summary` with `source_kind="prior_attempt_summary"` using Phase 4's wrapper unchanged.
- **`typecheck.typescript`** SignalKind is registered via Phase 3's open registry; Phase 5's `TrustScorer` folds it into strict-AND automatically without code edits.
- **`PlanOutcome`** is consumed only by Phase 4's harvester; `RecipeApplication` (Phase 3) is what crosses into Phase 5 — Phase-4-local `PlanOutcome` does not widen the Phase-3 sum type, so Phase 7's "diff touches only the new plugin directory" precondition is preserved.
- **`ProvenanceGate`** is the tier-0 check before any LLM tokens are spent; Phase 5's retry path calls into `FallbackTier`, which gates again (defense in depth; cheap and idempotent).
- **`SolvedExampleWriteCapability`** mint surface: Phase 4's `_phase4_local_capability_mint` is the **interim shim**; Phase 5's `GateRunner` ships the real mint at `src/codegenie/gates/_capability_mint.py` and supersedes it. The `import-linter` contract on the mint symbol is the swap-safety net.
- **`tests/fixtures/fallback_tier_callable.py`** is the contract Phase 6 (LangGraph) reads when it lifts `FallbackTier.run` into a graph node — no code change to Phase 4 at that lift.
