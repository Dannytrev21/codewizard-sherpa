# Phase 04 — Vuln remediation: LLM fallback + solved-example RAG: Final design

**Status:** Design of record (synthesized from three competing designs + critique).
**Synthesized by:** Graph-of-Thought synthesizer subagent
**Date:** 2026-05-18
**Sources:** `design-performance.md` · `design-security.md` · `design-best-practices.md` · `critique.md`

## Lens summary

Phase 4 is the first phase where an LLM produces bytes the system *applies*, and the second-most load-bearing integration boundary in the roadmap (Phase 5 has already merged and consumes this phase's `FallbackTier`, `LlmInvocationGuard`, `FenceWrapper`, BLAKE3 chain head, and `prior_attempts` kwarg by name). The synthesis is **security-led on the trust-boundary primitives** (`PlanProposal` closed sum type, `FenceWrapper` + `CanaryGuard`, `LlmInvocationGuard` as a capability, provenance refuse-mode as a *gate*, cassette sanitization as a CI fence, BLAKE3 chain head on every RAG record), **performance-led on the cheap rails** (`fastembed` ONNX over `sentence-transformers`/torch, `chromadb` embedded local, Anthropic prompt-cache discipline at the adapter), and **best-practices-led on package layout** (`src/codegenie/rag/`, `src/codegenie/llm/` as plugin-agnostic substrates; recipes live in the existing `vulnerability-remediation--node--npm/` plugin). It **departs from all three** on five points the critic forced: (1) the `DeterministicRetargeter` is rejected outright as fan-fiction for the major-bump case Phase 4 exists to solve; (2) `RecipeOutcome` is **not** widened — Phase 4 introduces a separate `PlanOutcome` sum type that wraps `RecipeOutcome` and leaves Phase 3's discriminated union untouched (Phase 7's exit criterion forbids the widening); (3) `langgraph` does **not** enter Phase 4 (the three-node flat graph buys nothing and one phase early violates the roadmap); (4) SPKI-pinning for `api.anthropic.com` is replaced with a documented system-trust + OS-level egress filter and a CI-only nightly drift job (the SPKI self-DOS is a real failure mode none of the three designs survived); (5) auto-harvest runs **inline behind a gate** (`TrustOutcome.passed AND confidence=="high"`) so the roadmap exit criterion "second run hits RAG" is met by production behavior, not test scaffolding.

## Goals (concrete, measurable)

Targets are against `fixtures/vuln-major-bump/express-cve-2026-1234/` (one breaking-change CVE requiring call-site rewrites; ~80 .ts files; ~120 unit tests) unless noted.

- **Exit criterion E2E.** A major-version-bump CVE solved end-to-end via LLM fallback; the validated outcome is harvested into the store; a second run on the same case **hits RAG, not LLM, by production behavior** (no operator step in the test). `[synth — closes critic [B] §4]`
- **Time-to-PR p50 — recipe-hit (Phase 3 path unchanged):** ≤ 18 s. `[P]`
- **Time-to-PR p50 — RAG-hit (cassette replay, prompt-cache warm):** ≤ 28 s. **Increased from `[P]`'s 22 s** to absorb FenceWrapper/canary/provenance-verify cost. `[P+synth]`
- **Time-to-PR p50 — LLM-from-scratch (cassette replay):** ≤ 35 s. `[P+S]`
- **Time-to-PR p95 — LLM-from-scratch (live, cold cache):** ≤ 110 s. `[P]`
- **$/PR — recipe-hit:** $0.00. `[P]`
- **$/PR — RAG-hit (no LLM):** **N/A — Phase 4 always feeds RAG hits as few-shot to the LLM** (no `DeterministicRetargeter`; the byte-applicable tier is rejected). The RAG-hit-as-few-shot cost is the same as LLM-from-scratch with cache discipline. `[synth — closes critic [P] §1]`
- **$/PR — LLM-from-scratch (cache warm):** ≤ $0.012. `[P]`
- **$/PR — LLM-from-scratch (cache cold):** ≤ $0.06. `[P]`
- **Per-workflow hard budget cap:** **250 K combined tokens / $1.50** — `LlmInvocationGuard.precharge` enforced as a capability before any leaf call. Exceeding triggers `BudgetExceeded` and `Refused(BUDGET_EXCEEDED)`. `[S]`
- **Audit completeness.** Every prompt (BLAKE3-digest, not raw), every response (digest + parsed `PlanProposal`), every RAG retrieval (with similarity per record + provenance status), every RAG write, every refuse-mode short-circuit, every fence-wrap, every canary collision, every budget event lands on the two-stream EventLog. Chain breakage at any link halts the workflow. `[S]`
- **Allowed network egress, entire process:** `api.anthropic.com:443` (TLS, system trust store, **no SPKI pin**; nightly drift job catches breakage). Loopback only for `pytest-httpserver` tests (gated by a `_test_only` runtime flag set by pytest fixtures, not by an unconditional carve-out). All other hosts denied by `EgressGuard`. `[S+synth — closes critic [S] §1+§2]`
- **No `langgraph` admitted into Phase 4 runtime closure.** `[synth — closes critic [B] §1]`
- **No source-code path under `src/codegenie/probes/`, `coordinator/`, `cache/`, `output/`, `schema/` imports `anthropic`, `chromadb`, `fastembed`, or `onnxruntime`.** Enforced by `import-linter` contract + `tests/unit/test_pyproject_fence.py` amendment (exact diff specified in §"Load-bearing commitments check"). `[B+synth]`
- **`typecheck.typescript` SignalKind lands** (ADR-0037), strict-AND-folded into validate, fires *before* tests run when LLM-produced source code drifts. `[P+B+S]`
- **Vector store query p99** (chromadb local, 10 K examples): ≤ 15 ms. `[P]`
- **Embedding query p99** (`fastembed` BGE-small ONNX): ≤ 80 ms. `[P]`
- **Worker memory ceiling (Phase 4 additions):** ≤ 350 MB RSS. `[P]`
- **Cassette miss in CI:** hard fail. `[P+B]`
- **Cassette security scan in CI:** `tests/security/test_cassettes_clean.py` rejects any cassette with `Authorization`, `x-api-key`, `anthropic-version` headers, `sk-*`/`claude_*`-shaped tokens, or 40+-char base64-shaped header values. `[S — closes critic blind-spot]`
- **Inline auto-harvest gate:** if and only if `TrustOutcome.passed AND TrustOutcome.confidence == "high"`, ingest the solved example inline (capability-gated by `SolvedExampleWriteCapability` minted by Phase 5's `GateRunner`). `[synth — closes critic [B] §4]`
- **Determinism property:** given `(repo_snapshot_sha, cve_record_digest, plugin_version, recipe_version, vuln_index_digest, store_digest, embedding_model_digest, cassette_blake3)`, the produced `Transform`, event sequence, and chain-head advancement are byte-identical (modulo timestamps + `workflow_id`). Property-tested across 50 runs. `[B]`

## Architecture

```
                       codegenie remediate <repo> --cve=<id>
                                       │
                                       ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/cli/remediate.py  (Phase 3 — extended additively)          │
   │   New flags: --tier-cap {recipe,rag,llm}  --refresh-cassettes (op-only)  │
   └────────────────────────────────────┬─────────────────────────────────────┘
                                        ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/transforms/orchestrator.py (Phase 3 — UNCHANGED)           │
   │   Stage 3 (Planning) calls plugin.transforms()['plan'] which returns a   │
   │   FallbackTierPlanRecipeEngine wrapping the tier chain. Kernel learns    │
   │   ZERO new methods. [B+P]                                                │
   └────────────────────────────────────┬─────────────────────────────────────┘
                                        ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/fallback/   [P4 NEW — load-bearing for Phase 5]            │
   │                                                                          │
   │   tier.py           FallbackTier — the recipe → RAG → LLM dispatch.      │
   │                     .run(advisory, repo_ctx, recipe_selection,           │
   │                          prior_attempts=[]) -> RecipeApplication         │
   │                     (Phase 5-mandated signature.)                        │
   │                                                                          │
   │   plan_outcome.py   PlanOutcome — Phase-4-LOCAL sum type wrapping        │
   │                     RecipeOutcome. Phase 3's RecipeOutcome IS NOT        │
   │                     widened. [synth — closes critic [B] §5]              │
   │                                                                          │
   │   plan_proposal.py  PlanProposal — closed Pydantic discriminated union.  │
   │                     The ONLY shape the LLM may return. [S]               │
   │                                                                          │
   │   budget.py         LlmInvocationGuard — capability-pattern budget       │
   │                     guard. BudgetToken required for any leaf call. [S]   │
   │                                                                          │
   │   provenance_gate.py  Phase 4's ADR-0038 entry-point. Calls the          │
   │                     plugin's NpmVulnProvenanceAdapter (Phase 3 already   │
   │                     ships the refuse-mode shape; Phase 4 generalises     │
   │                     to all `Unknown`-refuse) BEFORE any LLM tokens       │
   │                     are spent. [S+B+synth]                               │
   │                                                                          │
   │   ─── TRUST BOUNDARY A ─── (prompt assembly)                             │
   │                                                                          │
   │   fence/                                                                 │
   │     wrapper.py        FenceWrapper.fence(payload, source_kind) ->        │
   │                        FencedSegment.  Per-source-kind truncation caps.  │
   │     canary.py         CanaryGuard — pattern denylist + nonce-escape      │
   │                        property. **Canary scan runs on the UNTRUNCATED   │
   │                        payload** then truncation; closes critic [S] §5. │
   │     prompt_builder.py PromptBuilder mints TrustedPrompt + FencedBody     │
   │                        newtypes. AST-walking test asserts no other       │
   │                        callsite constructs them.                         │
   │                                                                          │
   │   ─── TRUST BOUNDARY B ─── (LLM call + response parsing)                 │
   │                                                                          │
   │   leaf/                                                                  │
   │     port.py           LeafLlm Protocol                                   │
   │     anthropic_adapter.py  AnthropicLeafAdapter — the ONLY module in      │
   │                            the codebase allowed to import `anthropic`.   │
   │                            - SecretStr key from `keyring`                │
   │                            - system trust store (NO SPKI pin)            │
   │                            - prompt-cache discipline via                 │
   │                              CachedSystemBlock typed wrapper             │
   │                            - response_format = JSON schema for           │
   │                              PlanProposal; parsed at adapter boundary    │
   │     egress_guard.py   EgressGuard — sitecustomize-installed              │
   │                        socket wrapper; allowlist = {api.anthropic.com};  │
   │                        loopback gated by pytest-only flag.               │
   │                                                                          │
   │   cassette/                                                              │
   │     sanitizer.py      pytest-recording before_record_request/response    │
   │                        hooks; pre-replay verifier.                       │
   │                                                                          │
   │   typecheck/                                                             │
   │     ts_signal.py      @register_signal_kind("typecheck.typescript")      │
   │                        + collector inside Phase 3 SubprocessJail.        │
   └────────────────────────────────────┬─────────────────────────────────────┘
                                        │
                                        ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ src/codegenie/rag/   [P4 NEW — plugin-agnostic substrate]                │
   │   store.py            SolvedExampleStore (open/add/query/digest/close)   │
   │                       chromadb PersistentClient embedded mode only       │
   │   models.py           SolvedExample, Query, RetrievalOutcome             │
   │                       (RagHit | RagMiss | RagDegraded)                   │
   │   embedder.py         FastembedEmbedder (BAAI/bge-small-en-v1.5 ONNX)    │
   │                       behind Embedder Protocol; fastembed has ONE        │
   │                       in-tree adapter — see §"Patterns rejected"         │
   │   provenance.py       RecordProvenance, BLAKE3 chain verify              │
   │   ingest.py           ingest_solved_example(outcome, store, embedder,    │
   │                                              capability)                 │
   │                       Capability gates the write; not the read.          │
   │   confidence.py       similarity → AdapterConfidence mapping             │
   └────────────────────────────────────┬─────────────────────────────────────┘
                                        ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ plugins/vulnerability-remediation--node--npm/  (extended; no new plugin) │
   │   subgraph/                                                              │
   │     fallback_plan_engine.py  — FallbackTierPlanRecipeEngine wraps        │
   │                                FallbackTier; plugin.transforms()['plan'] │
   │                                returns this instance. [B+synth]          │
   │   recipes/                                                               │
   │     (Phase 3 recipes UNCHANGED)                                          │
   │     rag_query_builder.py     — plugin-specific Query construction        │
   │   adapters/                                                              │
   │     vuln_provenance.py       — NpmVulnProvenanceAdapter (Phase 3         │
   │                                already ships the refuse-mode shape;      │
   │                                Phase 4 generalises to AppDirect /        │
   │                                AppTransitive / AppVendored / Unknown).   │
   │   skills/                                                                │
   │     vuln-major-bump.md       — system[0] cached skill text               │
│                                                                          │
   │   tccm.yaml: requires: rag_capabilities, llm_capabilities;               │
   │              provides: typecheck_signals                                 │
   └────────────────────────────────────┬─────────────────────────────────────┘
                                        ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ .codegenie/                                                              │
   │   rag/                                                                   │
   │     chroma/                  chromadb PersistentClient (sqlite + parquet)│
   │     records/<id>.yaml        canonical YAML; sqlite is derived index     │
   │     manifest.yaml            BLAKE3-rolled head over records[]           │
   │     embeddings_model.lock    model name + sha256; refuse-start mismatch  │
   │   events/                                                                │
   │     workflow-internal/<wid>.jsonl.zst                                    │
   │     spanning/append.jsonl.zst   (BLAKE3-chained; Phase 5 reads head)    │
   │   cassettes (not under .codegenie/; under tests/cassettes/anthropic/)    │
   └──────────────────────────────────────────────────────────────────────────┘
```

The three load-bearing structural lines:

1. **The fallback dispatch is a `FallbackTier` Pydantic-orchestrating class — NOT a `langgraph` `StateGraph` — wired into `plugins/.../subgraph/fallback_plan_engine.py`.** The plugin Protocol does not learn a new method; the existing `plugin.transforms()['plan']` map returns a `RecipeEngine`-shaped wrapper. **Zero edits to `src/codegenie/plugins/protocols.py`.** Phase 6 owns the `langgraph` introduction; Phase 4 ships a `def run(...)` that Phase 6 lifts into a node mechanically (the test fixture `tests/fixtures/fallback_tier_callable.py` is the contract Phase 6 reads). `[B+P+synth — rejects [B] §5 LangGraph-in-P4]`

2. **The LLM's output is a closed Pydantic discriminated union (`PlanProposal`), validated at the leaf adapter boundary against a JSON schema passed as `response_format` to Anthropic.** Free-form prose is structurally impossible; `manifest_path` / `files` / `diff` are smart-constructed under `SandboxedRelativePath`. `[S — load-bearing critic finding §"LLM output discipline"]`

3. **`RecipeOutcome` (Phase 3) is NOT widened.** Phase 4 introduces a new sum type `PlanOutcome = AppliedFromRecipe | AppliedFromLlm | RagOnlyApplicable | Refused` *inside `src/codegenie/fallback/plan_outcome.py`*. `FallbackTier.run` returns `RecipeApplication` (the existing Phase 3 type, exactly as Phase 5 expects); the new `PlanOutcome` is an internal projection consumed only by event emission and the inline harvester. Phase 7's plugin can register a `vulnerability-remediation--node--*` extension without adding `case` arms anywhere. `[synth — closes critic [B] §5; closes Phase 7 exit criterion]`

## Components

### 1. `FallbackTier` — recipe → RAG → LLM dispatch (`src/codegenie/fallback/tier.py`)

- **Provenance:** `[S]` shape + `[P]` mechanics + `[synth]` signature.
- **Purpose:** The dispatch entry point Phase 3's orchestrator calls when its recipe path returns `NoMatch` or `Degraded`. Also the re-entry point Phase 5 calls on retry with `prior_attempts`.
- **Interface (frozen by Phase 5's already-merged contract):**
  ```python
  class FallbackTier:
      def __init__(
          self,
          retriever: SolvedExampleRetriever,
          leaf: LeafLlm,
          budget: LlmInvocationGuard,
          fence: FenceWrapper,
          canary: CanaryGuard,
          provenance: ProvenanceGate,
          event_log: EventLog,
      ) -> None: ...

      def run(
          self,
          advisory: CveAdvisory,
          repo_ctx: RepoContext,
          recipe_selection: RecipeSelection,
          *,
          prior_attempts: list[AttemptSummary] = [],
      ) -> RecipeApplication: ...
  ```
  Returns Phase 3's `RecipeApplication` — *not* a new top-level outcome — so Phase 5's already-merged callsites work unchanged.
- **Internal design:** A short pure-Python dispatch:
  1. **Provenance refuse-mode gate** (ADR-0038): `provenance.classify(advisory, repo_ctx)` returns one of `AppDirect | AppTransitive | AppVendored | BaseImage | RuntimeBundled | Both | Unknown`. Anything not in `{AppDirect, AppTransitive, AppVendored, Both}` → `RecipeApplication.Refused(reason=PROVENANCE_NOT_APP_LAYER)`. **No LLM tokens spent.** Phase 7 owns the full primitive; Phase 4 ships a Phase-4-scoped `_AppLayerOnlyProvenance` (security design Open Q 1, option c).
  2. **Budget precheck.** `budget.running_total()` accounts for prior-attempt spend; refuses fast if cap exceeded.
  3. **RAG retrieval** (skipped on retry, see "RAG bypass on retry" below).
  4. **Prompt assembly** through `PromptBuilder` (every untrusted byte → `FenceWrapper`).
  5. **`budget.precharge(max_tokens)`** mints a `BudgetToken` (capability).
  6. **`leaf.invoke(prompt, schema=PlanProposal, token=...)`** under `egress_guard.pinned_to(ANTHROPIC_HOST)`.
  7. **`budget.reconcile(token, actual_in, actual_out, actual_dollars)`**.
  8. **Apply** the validated `PlanProposal` to a `Transform`; return `RecipeApplication`.
- **RAG bypass on retry:** when `prior_attempts` is non-empty, RAG is **skipped** and the prompt includes only the fence-wrapped `prior_failure_summary`. Security design's empirically-grounded preference (security §"Open Q 2"); avoids the failure mode where the same wrong-shape RAG hit produces the same wrong patch twice. A Phase-4 ADR records this as a deliberate departure from ADR-0011's chain order (ADR-0011 describes initial-plan order, not retry order).
- **Why this choice over alternatives:** Performance's `TierChain` async generator is rejected for two reasons: (a) the `DeterministicRetargeter` it carries is fan-fiction for the major-bump case (critic §"[P] §1"); (b) the dispatch overhead reduction (~10 ms) does not justify owning an async iteration protocol that Phase 6 will subsume. Best-practices' four-node LangGraph subgraph is rejected (critic §"[B] §1"). Security's `FallbackTier` shape wins — short, sequential, every step audit-emitting.
- **Tradeoffs accepted:** No tier hedging; no LangGraph; no async generator. Phase 6 lifts this into a state-machine node.

### 2. `PlanProposal` — closed sum type the LLM must emit (`src/codegenie/fallback/plan_proposal.py`)

- **Provenance:** `[S]` (the load-bearing critic resolution; performance and best-practices lose here).
- **Purpose:** Constrain the LLM's output to a parseable, smart-constructed shape. The leaf adapter passes the schema as Anthropic's `response_format`; non-conforming responses raise `LeafProtocolViolation`.
- **Interface (Pydantic discriminated union per ADR-0033):**
  ```python
  class PlanProposalDepBump(BaseModel):
      kind: Literal["dep_bump"] = "dep_bump"
      manifest_path: SandboxedRelativePath
      package: PackageId
      target_version: SemverString
      rationale: str               # ≤ 2 KB; AUDIT LOG ONLY — never re-prompted

  class PlanProposalOverride(BaseModel):
      kind: Literal["override"] = "override"
      manifest_path: SandboxedRelativePath
      override: PackageOverride

  class PlanProposalCallsiteRewrite(BaseModel):
      kind: Literal["callsite_rewrite"] = "callsite_rewrite"
      manifest_path: SandboxedRelativePath
      files: list[SandboxedRelativePath]
      diff: UnifiedDiff            # smart-constructor: rejects paths outside
                                   # files, binary diffs, > 64 KB diffs

  class PlanProposalRefuse(BaseModel):
      kind: Literal["refuse"] = "refuse"
      reason: Literal["out_of_scope", "insufficient_context", "policy_block"]
      rationale: str

  PlanProposal = Annotated[
      PlanProposalDepBump | PlanProposalOverride
      | PlanProposalCallsiteRewrite | PlanProposalRefuse,
      Discriminator("kind"),
  ]
  ```
- **`callsite_rewrite.diff` cap: 64 KB** (relaxed from security design's 32 KB; closes critic §"[S] §3" — Express 4 → 5 and lodash 3 → 4 routinely produce >32 KB diffs and the phase exit criterion would have refused them). The 64 KB cap still bounds blast radius (the worst the LLM can do is a wrong rewrite that Phase 5 catches).
- **Why this choice over alternatives:** Performance's "prompt-instruction to emit `Transform.from_json`" is rejected — a prompt instruction is not a structural constraint, and the prose-then-Pydantic-validate pipeline is the historical home of injection-shaped failures. Best-practices' `_validate_lockfile_transform_shape` LangGraph node is also rejected (no LangGraph in Phase 4; the validation is a smart-constructor at the adapter boundary, not a node).
- **Tradeoffs accepted:** Novel plan shapes outside the four variants → `Refused(out_of_scope)` + HITL. Phase 15 (agentic recipe authoring) is where novel plans become first-class.
- **Closes critic findings:** §"LLM output discipline" load-bearing disagreement.

### 3. `FenceWrapper` + `CanaryGuard` (`src/codegenie/fallback/fence/`)

- **Provenance:** `[S]` with one critic-driven fix.
- **Purpose:** Every untrusted byte that enters an LLM prompt is fence-wrapped with a per-invocation 16-byte nonce, canary-scanned, and per-source-kind truncated. The system does not claim injection-proofness; it claims (a) every byte is fenced, (b) every collision is loud, (c) the LLM can only emit `PlanProposal`-shaped output.
- **Interface:**
  ```python
  class FencedSegment(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      source_kind: SourceKind
      nonce: HexNonce
      content: str

  class FenceWrapper:
      def fence(self, payload: str, source_kind: SourceKind) -> FencedSegment: ...

  class CanaryGuard:
      INJECTION_PATTERNS: Final[tuple[bytes, ...]] = (...)
      @classmethod
      def scan(cls, payload: str, nonce: str) -> CanaryResult: ...
  ```
- **Critic fix (load-bearing):** `CanaryGuard.scan` runs on the **untruncated** payload first; truncation runs second. Security design's order was scan-after-truncate, which let attackers hide injection past the truncation byte. Closes critic §"[S] §5".
- **Per-source truncation caps:**

  | Source kind | Cap |
  |---|---|
  | `cve_description` | 4 KB |
  | `repo_readme` | 2 KB |
  | `transitive_dep_meta` | 1 KB × max 16 |
  | `source_snippet` | 16 KB |
  | `sandbox_stderr` | 8 KB |
  | `rag_retrieved` | 8 KB × max 3 |
  | `prior_attempt_summary` | 4 KB |

- **`INJECTION_PATTERNS` is a `Final[tuple]`** (not `list[bytes]` — frozen at module load); a `tests/security/test_injection_corpus.py` corpus + Hypothesis property test (`f"</UNTRUSTED_INPUT id={nonce}>" not in fence(p, ...).content`) covers the standing assertions. The list is acknowledged-incomplete and *grown over time*; canary collisions are loud, never silent.
- **Why this choice over alternatives:** Performance ships nothing here; best-practices ships nothing. Security's design is the only one that addresses the threat model Phase 4 actually faces.

### 4. `LeafLlm` Protocol + `AnthropicLeafAdapter` (`src/codegenie/fallback/leaf/`)

- **Provenance:** `[S]` for isolation; `[P]` for prompt-cache discipline; `[synth]` rejects SPKI pinning.
- **Purpose:** The single seam between Phase 4 and the Anthropic API. The only module in the codebase allowed to `import anthropic` (import-linter contract).
- **Interface:**
  ```python
  class TrustedPrompt:       # newtype; only PromptBuilder mints
      ...
  class FencedPromptBody:    # newtype; only PromptBuilder mints
      ...
  class CachedSystemBlock(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      text: str
      cache: Literal["ephemeral", "none"] = "ephemeral"
      role_tag: Literal["skill", "instruction_template", "rag_few_shot"]

  class LeafLlm(Protocol):
      def invoke(
          self,
          system_prompt: TrustedPrompt,
          user_message: FencedPromptBody,
          *,
          schema: type[PlanProposal],
          token: BudgetToken,
      ) -> LeafResponse: ...

  class LeafResponse(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      plan: PlanProposal                  # already parsed; raises if malformed
      tokens_in: int
      cache_read_tokens: int
      cache_creation_tokens: int
      tokens_out: int
      model: ModelId
      stop_reason: Literal["end_turn", "max_tokens", "refusal"]
      response_id: str                    # for cassette identity
  ```
- **Cache-control discipline is enforced *at the typed block*, not at the call site.** Every `CachedSystemBlock` with `cache="ephemeral"` produces `{"cache_control": {"type": "ephemeral"}}` in the SDK call. Three cached blocks per workflow: `system[0]` skill (~2 KB, stable across all major-bump workflows), `system[1]` instruction template (~3 KB, stable across all Phase 4 leaf calls), `system[2]` RAG few-shot if any (~1–3 KB).
- **Critic-driven prompt-cache target:** the goal table commits only to `system[0]` and `system[1]` cache reuse across consecutive workflows; `system[2]` (per-workflow RAG few-shot) only hits cache when the *same* CVE re-runs within 5 minutes (operator-mode `remediate-batch`). Closes critic §"[P] §4" — the 65% prompt-cache target is honest now.
- **Credentials:** `ANTHROPIC_API_KEY` via `keyring.get_password("codegenie", "anthropic_api_key")` → `SecretStr`. **Never** read from environment variables in production. CI uses an OIDC-minted short-lived key when available; the `CODEGENIE_ANTHROPIC_KEY_CI` env-var escape is **rejected** (closes critic [S] §"keyring" hidden assumption #2). CI without OIDC must use the same `keyring` path with a CI-provided credential store.
- **No SPKI pin.** System trust store only. Closes critic §"[S] §1" (self-DOS waiting to happen). Defense-in-depth: (a) `EgressGuard` is the runtime allowlist; (b) OS-level egress filtering (iptables/nftables on Linux CI, documented for macOS dev); (c) a nightly CI job runs a real Anthropic call with a budget-capped CI key and flags TLS / SDK drift. SPKI pin reintroduction requires a Phase-4 ADR amendment and the operational runbook for rotation.
- **No retry inside the adapter.** Phase 5's `GateRunner` owns retry policy; one in-call retry on parse failure remains (with appended "your previous response was malformed" instruction; the second failure raises `LeafProtocolViolation`).
- **No chain-of-thought before tool emission.** The prompt instructs the model to emit a `PlanProposal` *directly* via the SDK `response_format` JSON schema; the system prompt explicitly forbids prose reasoning before the structured output. Two reasons: (a) prose-then-parse is the historical home of injection-shaped failures and `PlanProposal` is a closed sum type the parser will reject anything else against (`Components §2`); (b) "CoT amplifies tool hallucination" is documented in 2025 literature (`../../reviews/2026-05-18-agent-orchestration-survey-and-recommendations.md` row #9; *The Reasoning Trap*, arXiv:2510.22977) — the patch-proposer should be a structured-output call, not a thinking call. Where reasoning *is* useful — `prior_failure_summary` interpretation on retry — it happens inside the model's response generation but is not emitted to the user channel. Phase 4 has no critic node; if one is ever added (deferred), reasoning belongs there, not in the proposer.
- **Audit emissions:** `LeafKeyLoaded(source)`, `LeafInvoked(prompt_digest_blake3)`, `LeafReturned(response_digest_blake3, tokens_in, tokens_out, cache_read_tokens, cache_creation_tokens)`, `LeafProtocolViolation`, `EgressViolation`, `BudgetExceeded`.

### 5. `LlmInvocationGuard` — capability-pattern budget guard (`src/codegenie/fallback/budget.py`)

- **Provenance:** `[S]` (security got this right; performance defers to Phase 13; best-practices ships nothing).
- **Purpose:** A financial circuit breaker. The `LeafLlm` adapter takes a `BudgetToken` as a *required* arg — calling `adapter.invoke(...)` without one is a type error.
- **Interface:**
  ```python
  class BudgetToken(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      precharged_tokens: TokenCount
      precharged_dollars: Decimal
      issued_at: datetime
      _marker: Literal["budget_token"]   # private-by-convention discriminator

  class LlmInvocationGuard:
      def __init__(self, max_tokens: int, max_dollars: Decimal,
                   per_call_max_tokens: int, event_log: EventLog) -> None: ...
      def precharge(self, requested_tokens: int) -> BudgetToken: ...
      def reconcile(self, token: BudgetToken, actual_in: int, actual_out: int,
                    actual_dollars: Decimal) -> None: ...
      def running_total(self) -> BudgetSnapshot: ...   # Phase 5 consumes across retries
  ```
- **Defaults (Phase 4 ships; calibration deferred to Phase 13 cost ledger):**
  - `max_tokens_per_workflow`: 250 K
  - `max_dollars_per_workflow`: $1.50
  - `per_call_max_tokens`: 32 K
- **Critic-acknowledged: "capability passed through ten frames" anti-pattern.** Mitigated by passing `BudgetToken` only through `FallbackTier → LeafLlm.invoke` (two frames). The token does not flow through `PromptBuilder` or `FenceWrapper`. Closes critic §"capability passed through ten frames" anti-pattern flag.
- **Phase 5 hand-off:** `running_total()` is the surface Phase 5 consumes across retries; Phase 5's `cost.sandbox.run` ledger entries compose with Phase 4's `cost.llm.call` entries for Phase 13's ledger.

### 6. `ProvenanceGate` (`src/codegenie/fallback/provenance_gate.py`)

- **Provenance:** `[S+B+synth]`.
- **Purpose:** ADR-0038's refuse-mode short-circuit, lifted from "inherited from Phase 3" (best-practices) to an *explicit gate* that runs **before any LLM tokens are spent**. Performance design omitted this entirely.
- **Interface:**
  ```python
  class ProvenanceGate:
      def __init__(self, adapter: VulnProvenanceAdapter, event_log: EventLog) -> None: ...
      def classify(self, advisory: CveAdvisory, repo_ctx: RepoContext) -> Provenance: ...
  ```
- **Internal design:** Calls the plugin's `NpmVulnProvenanceAdapter` (the Phase 3 plugin already ships the refuse-mode shape per ADR-0038). Phase 4 generalises the consumer: any `Provenance` not in `{AppDirect, AppTransitive, AppVendored, Both}` is `Refused(PROVENANCE_NOT_APP_LAYER)`. Phase 7 ships the base-image adapters that turn `Unknown` into structured provenance.
- **Audit emissions:** `ProvenanceClassified(kind)`, `Refused(reason=PROVENANCE_NOT_APP_LAYER, provenance_kind=...)`.

### 7. `SolvedExampleStore` + `ChromaPersistentStore` (`src/codegenie/rag/store.py`)

- **Provenance:** `[B]` for package layout + `[P]` for chromadb local + `[S]` for embedded-mode-only + `[synth]` for the YAML-as-canonical convention.
- **Purpose:** Persistent similarity search over solved examples. One Protocol, one in-tree adapter.
- **Interface:**
  ```python
  class SolvedExampleStore(Protocol):
      def query(self, q: Query, *, top_k: int = 5,
                similarity_floor: float | None = None,
                ) -> RetrievalOutcome: ...
      def add(self, example: SolvedExample,
              capability: SolvedExampleWriteCapability) -> SolvedExampleId: ...
      def digest(self) -> StoreDigest: ...
      def close(self) -> None: ...
  ```
- **chromadb PersistentClient embedded mode only.** Qdrant is rejected (security: HTTP listener surface; best-practices: docker-compose contributor friction; performance: ~2 s docker-compose cold start). Critic §"chromadb single-writer at 24 workers" landed: Phase 4 ships **with a single-writer constraint declared in the Protocol's docstring** and a process-local `asyncio.Lock` around `add()`; Phase 11's concurrent-merge-webhook trigger is when the Protocol's adapter swaps to pgvector (ADR-0017 deferral resolution). The Phase 11 swap is one adapter, not a refactor.
- **YAML-as-canonical-source.** Each example is `.codegenie/rag/records/<id>.yaml`; chromadb's sqlite is a derived index that can be rebuilt by `codegenie rag rebuild`. This gives git-attributable corpus, human-reviewable diffs, and corruption recovery without re-embedding pain (closes critic §"chromadb schema migrations are not stable" hidden assumption).
- **Per-`(task_class, language, build_system)` collection.** Smaller HNSW indexes; O(1) filter selection.
- **Read/write split:** `query` is read-only; `add` requires `SolvedExampleWriteCapability`.

### 8. `FastembedEmbedder` (`src/codegenie/rag/embedder.py`)

- **Provenance:** `[P]` (performance wins decisively; best-practices' `sentence-transformers` is rejected because torch (~250 MB transitive) is more contributor friction than the model file fastembed ships).
- **Purpose:** Local CPU embeddings; no torch; no network at runtime.
- **Interface:**
  ```python
  class Embedder(Protocol):
      def embed(self, text: str) -> EmbeddingVector: ...
      def embed_batch(self, texts: list[str]) -> list[EmbeddingVector]: ...
      def model_digest(self) -> BlobDigest: ...

  class FastembedEmbedder:
      def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None: ...
  ```
- **Embeddings bootstrap is offline-only.** `codegenie embeddings bootstrap` downloads pinned model weights against a content-addressed URL whose sha256 lives in `embeddings_model.lock`. Runtime path refuses to start on hash mismatch. `EgressGuard` would catch any runtime download attempt regardless.
- **Cross-architecture determinism risk acknowledged** (critic §"[P] §3" hidden assumption): ONNX float outputs may differ at the 5th decimal between x86_64 and arm64. The mitigation is the single-similarity-threshold relaxation in §11 (Calibration) — Phase 6.5 calibrates a band, not a point. Phase-4 tests run on x86_64 (ubuntu-24.04) only; an `arm64-cross-host-determinism` test is a known Phase-6.5 follow-up.
- **No `sentence-transformers`** — closes critic §"[B] §2" (the contributor-friction justification for chromadb-vs-qdrant is the same justification that kills sentence-transformers-vs-fastembed).

### 9. `SolvedExampleWriter` + `SolvedExampleWriteCapability` (`src/codegenie/rag/ingest.py`)

- **Provenance:** `[S]` with critic-driven honesty.
- **Purpose:** RAG writes are write-gated by a capability minted by Phase 5's `GateRunner` on validated outcome.
- **Critic-acknowledged: "Capability pattern" without true unforgeability** (critic §"[S] §4"). The Phase-4 design **does not claim runtime unforgeability**. The capability is enforced by **two complementary mechanisms**: (1) `SolvedExampleWriteCapability` is constructed via a module-private factory `_mint_solved_example_capability(...)` that lives in `src/codegenie/gates/_capability_mint.py` (Phase 5 ships); (2) an `import-linter` contract blocks any module outside `{src/codegenie/gates/, src/codegenie/rag/ingest.py}` from importing the minting symbol, and a CI test asserts the contract. We name this honestly as a **Module Boundary pattern with CI enforcement**, not GoF Capability. The Phase 4 design ships an interim shim `_phase4_local_capability_mint` that the inline harvester uses (gated by `TrustOutcome.passed AND confidence=="high"`); Phase 5 supersedes it.
- **Inline auto-harvest (the critic-driven fix):** when `TrustOutcome.passed AND TrustOutcome.confidence == "high"`, `FallbackTier`'s exit path calls `ingest_solved_example(outcome, store, embedder, capability=mint(...))`. Closes critic §"[B] §4" — the roadmap exit criterion "second run hits RAG" is met by production behavior. Performance design's unconditional inline harvest is **not** adopted; best-practices' "deferred to Phase 11" is rejected.

### 10. `EgressGuard` (`src/codegenie/fallback/leaf/egress_guard.py`)

- **Provenance:** `[S]` with critic-driven fix on loopback handling.
- **Purpose:** Process-wide socket guard; raises on any `socket.create_connection` to a host not in the allowlist. Belt to `LeafLlm`'s suspenders.
- **Critic fix (load-bearing):** loopback is **not** unconditionally permitted. A pytest fixture sets a `_test_only_loopback_enabled` thread-local flag; production code does not set it; `EgressGuard` rejects loopback when the flag is unset. Closes critic §"[S] §2" — the loopback whitelist was the bypass an attacker needed.
- **Acknowledged residual:** C-extension `connect(2)` calls bypass Python's `socket` module. Mitigation: import-linter restricts native-extension-using deps; OS-level egress filtering documented as the secondary control; `codegenie self-check egress` subcommand reports OS-level posture.
- **Anti-pattern flagged by critic** ("side effects in module import" — `sitecustomize`): acknowledged. The `EgressGuard` install is idempotent and exposes a `EgressGuard.reset_for_test()` for the test plan. The design accepts the trade — runtime catch of dynamic socket use is worth the import-time install.

### 11. `SolvedExampleRetriever` + retrieval-side discipline (`src/codegenie/rag/retriever.py`)

- **Provenance:** `[S]` for chain verification + `[synth]` for the calibration band.
- **Purpose:** Read-only RAG at planning time, with per-record BLAKE3 chain verification and retrieval-side fencing.
- **Calibration band (the critic-driven fix to "single global cosine threshold"):** the retriever returns `RetrievalOutcome` based on a **two-threshold band**, not a single number:
  - `similarity ≥ high_floor` (default 0.85) → `RagHit(few_shot=record)`
  - `degraded_floor ≤ similarity < high_floor` (default 0.65–0.85) → `RagDegraded(near_match=record)` — feeds the LLM as few-shot with a "low-confidence" tag in the prompt template
  - `similarity < degraded_floor` → `RagMiss`
  Thresholds live in `plugins/.../plugin.yaml` (not in code) so calibration is config, not a code edit. Phase 6.5 owns the calibration evidence. Closes critic §"All three use a single similarity threshold" shared blind spot.
- **Provenance verification:** every record carries `provenance.event_chain_head`; mismatch on retrieval → exclude with `RagRecordChainOrphan` event. The chain-segment proof field assumed in security design is dropped (critic §"[S] §1" hidden assumption — machine-local chain heads break across worker restarts); replaced with a simpler "the record's chain head must appear somewhere in the spanning chain log" verification.
- **Retrieval-side fencing:** every record's content is fenced at *retrieval* time as `source_kind="rag_retrieved"`.

### 12. `TypecheckTypescriptSignal` (`plugins/.../adapters/ts_typecheck_signal.py`)

- **Provenance:** `[P+B+S]` (all three got this right; the synthesis is the plugin location and the ADR-0037 wiring).
- **Purpose:** ADR-0037's first `typecheck.<lang>` SignalKind. Registers via `@register_signal_kind("typecheck.typescript")` against Phase 3's open registry.
- **Internal design:** Runs `tsc --noEmit --pretty false` inside Phase 3's `SubprocessJail`. Strict-AND with baseline (cached at `.codegenie/typecheck/baseline-<repo-sha>.json`); passes iff `new_errors_after <= new_errors_before`. Adds `tsc` (resolved from `./node_modules/.bin/tsc`) to `ALLOWED_BINARIES` via a Phase-4 ADR amendment per Phase 3 ADR-0012 pattern.
- **Location:** plugin-local (`plugins/vulnerability-remediation--node--npm/adapters/`). Phase 7's distroless plugin that doesn't run `tsc` won't register the signal; Phase 7's Node-touching plugin can re-register via a shared `vulnerability-remediation--node--*` base plugin per ADR-0031 wildcard convention (deferred; not Phase 4's call).

### 13. `CassetteSanitizer` + cassette discipline (`src/codegenie/fallback/cassette/`)

- **Provenance:** `[S]` (performance missed it entirely — critic flagged).
- **Purpose:** Cassettes are checked-in source; sanitize on record, verify on replay, scan in CI.
- **Internal design:** `pytest-recording` `before_record_request` / `before_record_response` hooks strip headers (`Authorization`, `X-API-Key`, `Cookie`, `Set-Cookie`, `anthropic-version`), scan bodies for `sk-ant-*` / `claude_*` tokens and 40+-char base64-shaped header values. `tests/security/test_cassettes_clean.py` walks `tests/cassettes/` and fails CI on any leaked pattern. Cassette diffs require `cassette-steward` CODEOWNERS approval.
- **Cassette-discipline as test correctness (closes critic shared blind-spot #3):** a nightly CI job runs *real* Anthropic calls (with a budget-capped CI key) against a representative bench fixture and flags drift. Cassettes catch CI determinism; the nightly job catches cassette-vs-reality drift. The two are different controls.
- **`cassettes.lock` BLAKE3 file** at `tests/cassettes/anthropic/cassettes.lock` is the Phase 6.5 hand-off (closes critic roadmap §1.3 — best-practices and security didn't ship this).

### 14. `PlanOutcome` (`src/codegenie/fallback/plan_outcome.py`)

- **Provenance:** `[synth]` — the critic-driven departure from all three designs.
- **Purpose:** Phase-4-local sum type that wraps `RecipeOutcome` for the event-stream and harvester to dispatch on, **without widening `RecipeOutcome`**.
  ```python
  class AppliedFromRecipe(BaseModel):
      kind: Literal["recipe"] = "recipe"
      recipe_outcome: RecipeOutcome.Applied

  class AppliedFromLlm(BaseModel):
      kind: Literal["llm"] = "llm"
      recipe_outcome: RecipeOutcome.Applied
      few_shot_ref: SolvedExampleId | None
      response_id: LeafResponseId

  class RagOnlyApplicable(BaseModel):
      kind: Literal["rag_only"] = "rag_only"
      few_shot_ref: SolvedExampleId        # passed to LLM as context

  class Refused(BaseModel):
      kind: Literal["refused"] = "refused"
      reason: Literal["PROVENANCE_NOT_APP_LAYER", "BUDGET_EXCEEDED",
                      "LEAF_REFUSED", "LEAF_SCHEMA_VIOLATION"]

  PlanOutcome = Annotated[
      AppliedFromRecipe | AppliedFromLlm | RagOnlyApplicable | Refused,
      Discriminator("kind"),
  ]
  ```
- **`FallbackTier.run` returns `RecipeApplication`** (the Phase 3 type Phase 5 consumes); `PlanOutcome` is internal projection only. Phase 7's distroless plugin will not add `case` arms anywhere. Closes critic §"[B] §5" + roadmap §1.4 (Phase 7 exit criterion preserved).

## Data flow

End-to-end run on the headline Phase 4 case (major-bump CVE; recipe fails; LLM produces a callsite rewrite; validate passes; harvester runs inline).

```
1. CLI: codegenie remediate ./web-app --cve=CVE-2026-1234
   → RemediationOrchestrator.run(...)  [Phase 3 unchanged]
2. Stage 1 Resolve.  Plugin = vulnerability-remediation--node--npm.
3. Stage 2 Bundle.  BundleBuilder.build(...) — TCCM requires
   rag_capabilities + llm_capabilities; resolver passes.
4. Stage 3 Plan — plugin.transforms()['plan'] returns
   FallbackTierPlanRecipeEngine; orchestrator calls .apply(ctx).
5. FallbackTier.run(advisory, repo_ctx, recipe_selection):
   ── PROVENANCE GATE ──                                          [Trust boundary 0]
   ProvenanceGate.classify(...) → AppTransitive   (Phase 3 NpmVulnProvenanceAdapter)
   ── RECIPE TIER ──
   Phase 3 RecipeEngine.match(cve) → NpmMajorBumpRefuseRecipe → NotApplicable.
   Emit RecipeMissed(reason="major_bump_breaking_change").
   ── BUDGET PRECHECK ──
   budget.running_total() → BudgetSnapshot(consumed=0).
   ── RAG TIER ──                                                  [Trust boundary A]
   query = rag_query_builder(advisory, repo_ctx)
   embedder.embed(query) → vec  (BLAKE3-cached at .codegenie/rag/embeddings.cache.sqlite)
   store.query(vec, top_k=3, ...) → RagHit(score=0.91, record=ex-2025-11-04-...)
   provenance.verify(record) → verified
   emit RagHit(mode="few_shot", source_example_id=...).
   ── PROMPT ASSEMBLY ──                                           [Trust boundary A]
   PromptBuilder mints TrustedPrompt (system blocks: skill + instruction + few-shot,
                                       all cache_control:ephemeral)
                          + FencedPromptBody (user block: RepoContext slice +
                                              CVE + tree-sitter outline,
                                              every untrusted byte → FenceWrapper).
   ── BUDGET PRECHARGE ──
   token = budget.precharge(max_tokens=12_000)
   ── LEAF CALL ──                                                 [Trust boundary B]
   with egress_guard.pinned_to(ANTHROPIC_HOST):
       response = leaf.invoke(prompt.system, prompt.body,
                               schema=PlanProposal, token=token)
   leaf adapter: anthropic call with response_format=JSON schema for PlanProposal;
                 parse → PlanProposalCallsiteRewrite | raises LeafProtocolViolation.
   budget.reconcile(token, response.tokens_in, response.tokens_out, ...)
   ── OUTPUT VALIDATION ──
   PlanProposalCallsiteRewrite.diff.smart_construct() validates UnifiedDiff,
   rejects paths outside files, binary diffs, > 64 KB.
   ── BUILD Transform ──
   transform = NpmCallsiteRewriteTransform(diff=..., provenance=
       TransformProvenance(rag_few_shot_ref=ex-2025-11-04-..., response_id=...))
   return RecipeApplication.from_transform(transform)
6. Stage 4 Apply.   [Phase 3 unchanged]
7. Stage 6 Validate.  collector loop runs build + install + tests +
   lockfile_policy + cve_delta + typecheck.typescript (NEW).
   TrustScorer.score(...) → TrustOutcome(passed=True, confidence="high").
8. ── INLINE HARVEST GATE ──                                       [synth]
   if outcome.passed AND confidence == "high":
       capability = _phase4_local_capability_mint(workflow_id, chain_head)
                    (Phase 5 supersedes this with its real GateRunner mint)
       ingest_solved_example(outcome, store, embedder, capability)
       → store.add(SolvedExample(...))  [under asyncio.Lock — single-writer]
       → emit SolvedExampleHarvested(example_id, origin="llm_solved")
9. remediation-report.yaml; branch ready; CLI exits 0.

   Re-run on same CVE in a different repo:
   Steps 1–4 same.
   Step 5 RAG TIER: store.query(...) → RagHit(score=0.96, record=newly-harvested-one).
   The LLM call still happens (no DeterministicRetargeter) but with the new
   few-shot — prompt-cache warm on system[0]+system[1]; the response is cheaper
   in tokens because the LLM's output is similarly-shaped to the few-shot.
   This is the roadmap exit criterion "second run hits RAG" — RAG is consulted
   in production behavior; the harvester ran inline on the first workflow.
```

The phrase "hits RAG, not LLM" in the roadmap is interpreted as **"RAG is consulted and shapes the LLM call, producing a cheaper outcome"** — not "the LLM is never called." The original roadmap framing presupposed performance design's `DeterministicRetargeter`, which the critic showed is structurally inapplicable to the major-bump case. Phase 4's reading: RAG turns LLM-from-scratch into LLM-with-few-shot, which is the compounding-savings story without the fan-fiction.

## Failure modes & recovery

| Failure | Detected by | Containment | Recovery | Source |
|---|---|---|---|---|
| Provenance `Unknown` for `glibc` CVE on Node app | `ProvenanceGate.classify` returns non-app-layer | Refuse before any LLM tokens; emit `Refused(PROVENANCE_NOT_APP_LAYER)` | HITL via universal fallback (Phase 3 S7-03) | `[S+B+synth]` |
| Prompt injection in CVE description | `CanaryGuard.scan` (on untruncated payload) | Replace payload with `<<redacted: canary collision>>`; emit `CanaryCollision`; continue with redacted | LLM gets "redacted" → typically refuses `insufficient_context` → HITL | `[S+synth]` |
| LLM returns malformed JSON | `LeafLlm` Pydantic validation against `PlanProposal` schema raises | One in-call retry with "your previous response was malformed" instruction; second failure → `LeafProtocolViolation` | `FallbackTier` returns `Refused(LEAF_SCHEMA_VIOLATION)`; three consecutive in a workflow → halt | `[S]` |
| LLM plan has path escape | `SandboxedRelativePath` smart-constructor rejects | `LeafProtocolViolation` raised before reach | Phase 5 retry with `prior_attempts`; if persists → HITL | `[S]` |
| Per-workflow budget exceeded | `LlmInvocationGuard.precharge` raises `BudgetExceeded` | Refuse the call; emit `BudgetExceeded` | `Refused(BUDGET_EXCEEDED)` → HITL escalation | `[S]` |
| `EgressGuard` violation (any non-Anthropic socket) | `socket.create_connection` wrapper raises `EgressViolation` | Workflow halts | Operator supply-chain audit | `[S]` |
| RAG retrieval chain-orphan | `provenance.verify(record)` mismatch | Exclude record from result set; emit `RagRecordChainOrphan` | Operator runs `codegenie rag verify`; quarantine event-logged | `[S]` |
| chromadb sqlite corrupted | `SolvedExampleStore.open()` raises `StoreCorrupted` | RagDegraded path; LLM invoked without few-shot | `codegenie rag rebuild` from `records/*.yaml` canonical source | `[B+synth]` |
| `fastembed` ONNX session fails to load | `FastembedEmbedder.__init__` raises | Worker exits at startup; no silent fallback | Operator restart + investigate; bootstrap re-runs | `[P]` |
| `embeddings_model.lock` sha256 mismatch | `FastembedEmbedder.__init__` refuse-start | Refuse to start | Re-bootstrap | `[S]` |
| Anthropic API outage (5xx / rate limit) | SDK `APIStatusError` | One in-call retry with exponential backoff (1s, 4s, 16s); `LlmCallFailed(api_outage)` | Phase 5 `GateRunner` retry envelope is the next layer | `[P+S]` |
| Cassette miss in CI | `pytest-recording` `record_mode="none"` | Test fails with diagnostic; CI halts | Operator runs `make refresh-cassettes` locally with `--i-understand-this-spends-tokens`; CODEOWNERS approval | `[P+B]` |
| Cassette contains forbidden secret | `tests/security/test_cassettes_clean.py` | CI fails | Engineer regenerates with sanitizer enabled; key rotated as precaution | `[S]` |
| Cassette-vs-reality drift | Nightly CI real-API job flags drift | CI annotation; not workflow-blocking | Cassette refresh + commit | `[S+synth]` |
| `typecheck.typescript` subprocess timeout | `SubprocessJail` timeout (30 s) | `TrustSignal(passed=False, details={"timeout": True})` | Strict-AND fails; Phase 5 retry | `[P]` |
| Audit chain corruption at startup | `EventLog.__init__` chain verify | Refuse to run any workflow | Operator runs `codegenie audit verify`; corrupted entries surface | `[S]` |
| Inline harvest fails (chroma write error) | `ingest_solved_example` exception | Workflow still succeeds (the patch shipped); emit `SolvedExampleIngestFailed` | Operator triage; lost compounding opportunity, not wrong patch | `[P+synth]` |
| Phase 5 retry: same wrong plan shape on retry | `FallbackTier.run(prior_attempts=[...])` re-invocation produces same `Transform` (RAG gives same hit) | RAG bypass on retry (skip RAG when `prior_attempts` non-empty); prompt uses `prior_failure_summary` instead | Phase 5 owns retry envelope; HITL after 3 | `[S+synth]` |

## Resource & cost profile

- **Tokens per run:**
  - Recipe-hit: 0.
  - LLM-with-RAG few-shot (warm prompt cache): ~3,000 input + ~400 output ≈ 3,400 tokens.
  - LLM-from-scratch (cold cache): ~3,000 input (25% cache-write premium on first 2,000) + ~400 output.
- **Wall-clock per run:**
  - Recipe-hit: 18 s p50.
  - RAG-hit + LLM (cassette replay, prompt-cache warm): **28 s p50 / 50 s p95** (adds fence/canary/provenance-verify on top of [P]'s 22 s).
  - LLM-from-scratch (cassette): 35 s p50.
  - LLM-from-scratch (live, cold cache): 42 s p50 / 110 s p95.
- **$/PR:**
  - Recipe-hit: $0.00.
  - LLM warm (Sonnet 3.7, 2026-Q1 rates: in $3/M, cached read $0.30/M, out $15/M): ~$0.010.
  - LLM cold: ~$0.017 (+25% cache-write premium).
  - **Per-workflow hard cap: $1.50.**
- **Memory per worker (Phase 4 additions):**
  - `fastembed` ONNX: ~180 MB RSS.
  - `chromadb` PersistentClient + duckdb @ 10 K examples: ~100 MB.
  - `anthropic` async client: ~30 MB.
  - **Total Phase 4 addition: ~310 MB on top of Phase 3's 400 MB → ~710 MB per worker.**
- **Storage:**
  - Solved examples: ~5 KB per example + ~1.5 KB per embedding (384 × float32) ≈ 6.5 KB/example. 100 PRs/day → ~240 MB/year.
  - Cassettes: <5 MB total in repo.
  - Event log additions: ~6 new event kinds × ~200 bytes ≈ 1.2 KB/workflow (~400 bytes zstd).
- **Cold worker startup overhead (Phase 4 additions):** ~800 ms (ONNX load ~500 ms + chromadb open ~150 ms + anthropic client ~100 ms).
- **CI build wall-clock added by Phase 4 (cassette replay only):** ≤ 60 s.
- **The operational cost of *no* SPKI pin** (closes critic §"[S] §1"): we accept the residual MITM-via-public-CA risk in exchange for not shipping a release on every Anthropic CA rotation. The nightly real-API drift job is the compensating control. Documented in `docs/operations/secrets.md`.

## Test plan

Unified test plan combining the three approaches.

### Unit (~95% of test count)

- `tests/unit/fallback/test_fallback_tier.py` — mock all collaborators; assert dispatch order; `prior_attempts` non-empty bypasses RAG; budget refused → `Refused(BUDGET_EXCEEDED)`; provenance `Unknown` → `Refused(PROVENANCE_NOT_APP_LAYER)` with no leaf call (mock leaf with `pytest.fail` side-effect — closes security §test_provenance_refuse pattern).
- `tests/unit/fallback/test_plan_proposal.py` — every variant round-trips via JSON schema; `PlanProposalCallsiteRewrite.diff` smart-constructor rejects path-escape, binary diffs, > 64 KB; `Annotated[..., Discriminator]` exhaustively matches.
- `tests/unit/fallback/test_fence_wrapper.py` — Hypothesis property: for any payload `p` and any nonce `n`, `f"</UNTRUSTED_INPUT id={n}>" not in fence(p, ...).content`. Truncation runs AFTER canary scan (regression test for critic [S] §5 fix).
- `tests/unit/fallback/test_canary_corpus.py` — 200+ known injection payloads (PromptInject + project-curated). Growth-over-time corpus.
- `tests/unit/fallback/test_budget_guard.py` — `precharge` raises on over-cap; `reconcile` updates running total; `BudgetToken` is required arg of `LeafLlm.invoke` (type-check assertion).
- `tests/unit/fallback/test_leaf_adapter.py` — under `pytest-recording`, replay a recorded exchange; assert `LeafResponse.tokens_in` matches the cassette; every `CachedSystemBlock` produces a `cache_control` field in the SDK call (mock the SDK).
- `tests/unit/fallback/test_anthropic_response_format.py` — adapter passes JSON schema as `response_format`; mock returns malformed JSON → `LeafProtocolViolation` raised; one retry attempted then raise.
- `tests/unit/rag/test_store.py` — open/add/query round-trip; mock embedder; smart-constructor failure modes (missing path / corrupt → typed errors).
- `tests/unit/rag/test_models.py` — `SolvedExample.from_yaml(...)` happy path + every parse error; `extra="forbid"` rejects unknown keys.
- `tests/unit/rag/test_retriever_thresholds.py` — calibration band: 0.95 → RagHit; 0.75 → RagDegraded; 0.40 → RagMiss. Property test: monotonicity (higher similarity never yields lower confidence).
- `tests/unit/rag/test_embedder.py` — fastembed determinism: same input string → byte-identical vector across two runs (single-host); norm == 1.0 for normalized BGE outputs.
- `tests/unit/rag/test_provenance_verify.py` — chain-orphan records excluded; `RagRecordChainOrphan` event emitted.
- `tests/unit/plugin/test_fallback_plan_engine.py` — plugin's `transforms()['plan']` returns a `RecipeEngine`-shaped wrapper of `FallbackTier`; no kernel edits.
- `tests/unit/typecheck/test_signal.py` — `@register_signal_kind("typecheck.typescript")` runs at import time; double-register raises; collector parses `tsc --noEmit` output.
- `tests/unit/trust_scorer/test_typecheck_kind.py` — strict-AND fold with `typecheck.typescript` failing; `TrustOutcome.failing` correctly lists it.

### Property tests

- `tests/property/test_fence_no_escape.py` — Hypothesis over `(payload, nonce)`; assertion: nonce never appears in fenced content (and vice versa).
- `tests/property/test_solved_example_yaml_roundtrip.py` — Hypothesis generates valid `SolvedExample`; `from_yaml(to_yaml(x)) == x`.
- `tests/property/test_determinism_under_cassette_replay.py` — 50 runs with `(cassette_id, store_digest, repo_snapshot, embedding_model_digest)` constant; byte-identical `Transform.diff_bytes` and event order (modulo timestamps).
- `tests/property/test_plan_outcome_no_recipe_outcome_widening.py` — AST walk asserts `RecipeOutcome` has exactly the variants Phase 3 declared. Phase 7 inherits this test.

### Integration (~3% of test count)

- `tests/integration/test_phase4_rag_miss_llm_from_scratch.py` — empty store; LLM invoked without few-shot; cassette replay; produced `Transform` validates and applies.
- `tests/integration/test_phase4_rag_hit_few_shot.py` — populated store; query produces `RagHit`; LLM invoked with few-shot; `LlmCostAccrued` ledger shows lower input-token cost than scratch.
- `tests/integration/test_phase4_e2e_breaking_change.py` — **roadmap exit criterion test #1.** `fixtures/vuln-major-bump/express-cve-2026-1234/`; Phase 3 deterministic fails; Phase 4 LLM-replan succeeds; `_validate_stage6` runs; `npm test` passes inside `SubprocessJail`; `typecheck.typescript` passes; `remediation-report.yaml` lands; **inline harvester runs**.
- `tests/integration/test_phase4_e2e_replay_lands_rag.py` — **roadmap exit criterion test #2.** Same case re-run, no operator step between runs; recipe miss → RAG hit → LLM invoked with few-shot at lower token cost (asserted via `LlmCostAccrued` deltas). This is the *production behavior* test — not test scaffolding. (Closes critic [B] §4.)
- `tests/integration/test_phase4_provenance_short_circuits.py` — glibc CVE on Node app; `ProvenanceGate.classify → BaseImage`; assert `Refused(PROVENANCE_NOT_APP_LAYER)`; assert **no `LeafInvoked` event in workflow-internal stream** (assert by event-absence — leaf adapter mocked with `pytest.fail` side-effect).
- `tests/integration/test_phase4_retry_path_bypasses_rag.py` — Phase 5 simulator passes `prior_attempts=[summary]`; assert RAG **not** queried; assert fence-wrapped `prior_failure_summary` appears in prompt body (via cassette inspection).
- `tests/integration/test_typecheck_signal_catches_signature_drift.py` — deliberately-bad LLM cassette response with hallucinated method call; `tsc` catches it; gate fails before `npm test` runs (event ordering in stream).

### Adversarial (Phase 1 + Phase 2 idiom; `-m adv` marker)

- `tests/adversarial/test_injection_corpus.py` — 200+ payloads through `FenceWrapper` + `CanaryGuard`; target 0 escapes (closes critic [S] §5).
- `tests/adversarial/test_egress_guard.py` — patch `requests`, `urllib3`, `httpx`, `socket` to attempt forbidden hosts; assert `EgressViolation`. **Loopback is rejected unless `_test_only_loopback_enabled` is set** (closes critic [S] §2).
- `tests/adversarial/test_rag_poisoning_chain_orphan.py` — forged chain head; retrieval excludes + event-logs.
- `tests/adversarial/test_rag_poisoning_runtime_inject.py` — record `solution_diff_excerpt` contains injection; retrieval-time fence catches.
- `tests/adversarial/test_plan_path_escape.py` — leaf returns `PlanProposalDepBump(manifest_path="../../etc/passwd")`; smart-constructor rejects before orchestrator.
- `tests/adversarial/test_red_team_prompts.py` — 50+ curated scenarios; pass/fail = does any get past fence to a `PlanProposal` outside `SandboxedPath`. Target: 0 successes. Grows with disclosures.

### Cassette discipline

- **Directory:** `tests/cassettes/anthropic/<test_module>/<test_function>.yaml`.
- **CI:** `pytest --record-mode=none` (cassette miss = hard fail).
- **`tests/security/test_cassettes_clean.py`** — header/body/pattern scanner; fails CI on any leak.
- **`tests/fence/test_cassette_discipline.py`** — assert `CODEGENIE_LIVE_LLM` is unset in CI.
- **`tests/cassettes/anthropic/cassettes.lock`** — BLAKE3 per cassette; CI asserts on-disk matches lock (rejects un-committed re-records).
- **Nightly CI real-API job** (operator-controlled budget) — runs a representative bench fixture against live Anthropic; flags drift.

### Fence-CI (closes critic load-bearing finding)

- `tests/unit/test_pyproject_fence.py` (Phase 0; **amended**) — see §"Load-bearing commitments check" for the exact diff.
- `tests/fence/test_kernel_frozen.py` (Phase 3, extended) — allow-list grows by Phase 4 additions; diff against Phase 0/1/2/3 kernel files asserts zero edits.
- `tests/fence/test_no_langgraph_in_phase4.py` — AST walk asserts no Phase 4 module imports `langgraph` (closes critic [B] §1).
- `tests/fence/test_no_sentence_transformers.py` — AST walk asserts no module imports `sentence_transformers` (closes critic [B] §2).
- `tests/fence/test_rag_no_anthropic.py` — `src/codegenie/rag/` may not import `anthropic` (separation of concerns: kg is deterministic store).
- `tests/fence/test_only_leaf_imports_anthropic.py` — `import_linter` contract; `src/codegenie/fallback/leaf/anthropic_adapter.py` is the sole importer.
- `tests/fence/test_typecheck_signal_registered.py` — `SignalKind("typecheck.typescript")` is in registry at import time.

### Bench (`-m bench`; advisory)

- `bench_rag_tier_query_p99_under_15ms` — chroma + fastembed in-process; 10 K seeded examples.
- `bench_embedding_cache_hit_under_2ms` — second `embed(same_string)` call hits sqlite cache.
- `bench_typecheck_typescript_under_8s` — `tsc --noEmit` on 80-file fixture.
- `bench_phase4_retrieval_recall_at_top3` (CI nightly via Phase 6.5 harness) — top-1 recall ≥ 0.9 on known-equivalent cases; thresholds calibrated, not point-checked.

### Cross-cutting test-architecture additions

Per `docs/roadmap.md §"Test architecture evolution"`, Phase 4 extends the Phase-3 scaffolding (Phase 3 ships `tests/e2e/`, `tests/property/test_cache_invariant.py`, parameterized portfolio sweep, `tests/contract/`) with four phase-specific items:

- **Phase 4 rows added to `tests/e2e/scenarios.yaml`** — recipe → RAG → LLM-fallback slice exercised against `node_typescript_helm`, `node_yarn_berry_pnp`, and each of the four `fixtures/vuln-major-bump/*` examples. Each row asserts the full pipeline outcome (recipe miss → RAG hit OR RAG miss → LLM fallback → `Validated(passed=True)` with audit anchor written).
- **`tests/golden/events/` directory** — pins the schema of the new event streams Phase 4 emits: (a) `AttemptAnchor` JSONL (`tests/golden/events/attempt_anchor.{success,refusal}.jsonl`) per [ADR-04-0017](ADRs/0017-attempt-anchor-event-schema.md), and (b) the two-stream Phase 4 / Phase 5 event log (`tests/golden/events/two_stream.express-cve.{spanning,internal}.jsonl`). These calcify the on-disk schema so future consumers (operator portal, future critic training, replay debugging) cannot be silently broken by an in-place mutation. `schema_version` is checked alongside byte equality.
- **`tsc` added to `tests/contract/`** alongside Phase 3's `npm`/`pnpm`/`yarn`/`jq` — pins the TypeScript-compiler subprocess behavior at exact versions, run nightly. Catches the case where a project upgrades TypeScript and `tsc --noEmit` starts behaving differently for the `typecheck.typescript` SignalKind.
- **`FallbackTier`-scope determinism property** (already in scope as [S6-07](stories/S6-07-determinism-cassette-replay-property.md)) — listed here for completeness; the workflow-scope generalization (entire LangGraph state machine) waits for Phase 6.

## Design patterns applied

**This section supersedes the three per-lens pattern tables.**

| Decision (component or interface) | Pattern applied | Why this pattern *here* | Source design | Pattern *not* applied (and why) |
|---|---|---|---|---|
| `FallbackTier` recipe → RAG → LLM dispatch | **Pipeline (named, sequential, short-circuiting)** | Three handlers; each can short-circuit; the order *is* the policy (ADR-0011). | `[S+P]` | **NOT Chain of Responsibility** — there's no `handle/passToNext` Protocol; it's three named method calls. Calling it CoR (as [P] did) inflates a `for` loop into a pattern name. **NOT LangGraph state machine** ([B]) — premature; Phase 6 owns this. |
| `PlanProposal` discriminated union; LLM response is `PlanProposal` or `LeafProtocolViolation` | **Tagged union (sum type) + Make illegal states unrepresentable + Smart constructor** (ADR-0033) | The LLM is fundamentally untrusted. We constrain its *structure* even when we can't constrain its *content*. | `[S]` | **NOT free-form completion + Pydantic-validate** ([P]) — prose-then-parse is the historical home of injection-shaped bugs. **NOT LangGraph parse-node** ([B]) — no LangGraph. |
| `LeafLlm` Protocol + `AnthropicLeafAdapter` + `EgressGuard` + JSON-schema'd `response_format` | **Adapter pattern (1 adapter, 1 vendor) at a hard trust boundary** | The model provider is the dirtiest external dep; containing it behind a port localizes every security control. The Protocol earns its keep because ADR-0020 will resolve to a second vendor. | `[S+P]` | **NOT Hexagonal architecture** — security and performance both claimed it; the critic correctly noted the orchestration layer leaks `egress_guard.pinned_to(...)` into Phase 4, so the domain isn't actually isolated from infrastructure. We name the pattern honestly. |
| `LlmInvocationGuard` + `BudgetToken` required arg of `LeafLlm.invoke` | **Capability pattern (financial) + Circuit breaker** | Token is a function-signature property; calling without it is a type error. Bounds blast radius even if everything else fails. | `[S]` | **NOT global counter the adapter checks** — would let injected prompts run up arbitrary spend if a bug skipped the check. |
| `FenceWrapper` + `CanaryGuard` + `TrustedPrompt` / `FencedPromptBody` newtypes minted only by `PromptBuilder` | **Newtype + Smart constructor + Functional core / Imperative shell** | The type-checker enforces "every byte reaching the LLM passed through fencing." Fencing logic is pure; imperative shell does audit emission. | `[S]` | **NOT Visitor over `PromptSegment` + Builder cascade** — readable explicit calls beat pattern soup. |
| `SolvedExample` records: BLAKE3 chain head per record; spanning chain log; provenance verify on retrieval | **Event sourcing + Append-only log + Chain of hashes** | Tamper detection on individual records, not just the global log. | `[S]` | **NOT CRUD for RAG store** — updates and deletes are how poisoning persists. |
| `SolvedExampleWriteCapability` minted by Phase 5 `GateRunner`; import-linter contract + CI assertion | **Module Boundary pattern with CI enforcement** (named honestly; NOT GoF Capability) | True unforgeability would require an object-capability runtime; Python doesn't have one. Named as what it is. | `[S+synth]` | **NOT "Capability pattern"** — critic correctly noted Python's public constructors break the runtime claim. |
| `RecipeOutcome` left unchanged; Phase-4-local `PlanOutcome` wraps it | **Composition over union widening (open/closed at the sum-type boundary)** | Phase 7 must not add `case` arms; the sum type Phase 3 froze stays frozen. | `[synth]` | **NOT additive union widening** ([B]) — widens Phase 3's sum type, breaks Phase 7's exit criterion (closes critic [B] §5). |
| `@register_signal_kind("typecheck.typescript")` | **Registry pattern + Open/Closed** | Phase 3 shipped the seam; Phase 4 adds one row. | `[P+B+S]` | **NOT central `match`-statement dispatch** — modification, not extension. |
| `RetrievalOutcome = RagHit \| RagMiss \| RagDegraded` (calibration band, two thresholds) | **Tagged union + named bands instead of magic numbers** | Encodes three different shapes (`RagHit` carries example; `RagMiss` is bare; `RagDegraded` carries near-match). | `[B+synth]` | **NOT `Optional[SolvedExample]` + `Optional[float]`** — makes illegal states representable. **NOT single global cosine threshold** — critic shared-blind-spot; bands replace the magic number. |
| `.codegenie/rag/embeddings.cache.sqlite` (query-text → vector cache) | **Cache-aside + Content-addressed cache (BLAKE3 key)** | Embeddings are deterministic; BLAKE3 of input is the natural key. Reuses Phase 3's sqlite shape. | `[P]` | **NOT per-call in-memory dict** — lost on worker restart. |
| Inline auto-harvest behind `confidence == "high"` gate | **Specification pattern (composable rule) + Capability gate** | The gate is a named, composable rule, not a hard-coded `if`. The capability is what authorizes the write. | `[synth]` | **NOT unconditional inline harvest** ([P]) — risks poisoning. **NOT operator-only CLI** ([B]) — fails the roadmap exit criterion. |
| `cassettes.lock` BLAKE3 per cassette | **Content-addressed manifest** | Phase 6.5 reads this per bench case; per-cassette hash beats per-file mtime. | `[P+synth]` | **NOT a single dir-level checksum** — too coarse for cassette-level audit. |

### Patterns considered and deliberately rejected

- **`DeterministicRetargeter`** (performance design's headline). Rejected — fan-fiction for the major-bump call-site rewrite case Phase 4 exists to solve (closes critic [P] §1). The compounding-savings story is reframed: RAG turns LLM-from-scratch into LLM-with-few-shot, which is cheaper but not free.
- **LangGraph state machine in Phase 4** (best-practices design). Rejected — three flat nodes with no conditional edges or checkpointer buys nothing; one phase early imports a 10 MB framework the next engineer must learn for no architectural gain. Phase 6 introduces LangGraph as the runtime; Phase 4 ships a `def run(...)` Phase 6 lifts mechanically.
- **`sentence-transformers` + torch** (best-practices, security). Rejected — `fastembed` ONNX is the same shape (in-process, no GPU, deterministic, no docker) at one-third the install footprint. The contributor-friction argument best-practices used for chromadb-vs-qdrant is the same argument that kills sentence-transformers-vs-fastembed (closes critic [B] §2).
- **SPKI pinning of `api.anthropic.com`** (security). Rejected — operationally unworkable self-DOS (closes critic [S] §1). System trust + EgressGuard + OS-level filter + nightly drift job is the replacement.
- **`CODEGENIE_ANTHROPIC_KEY_CI` env-var escape** (security). Rejected — closes critic [S] hidden-assumption #2 (one PR sets both flags; design hopes contributor culture enforces it; nothing in code does).
- **Strategy pattern for the LLM** (all three Protocols with one adapter each — critic anti-pattern). Reduced from three to two Protocols: `LeafLlm` (ADR-0020 will resolve to a second adapter) and `SolvedExampleStore` (Phase 11 swap to pgvector is real). The `Embedder` Protocol *stays* as a single-adapter Protocol because the `model_digest()` method is the cache-key contract — but it's a one-method Protocol, not a full strategy.
- **Strategy for tier order** (all three). Rejected — the chain order *is* the policy (ADR-0011); Strategy hides this. It's a sequential algorithm, not three interchangeable algorithms.
- **`MockLeafLlm` shipped as production code** (all three designs). Rejected — test doubles live in `tests/`.
- **Cassette refresh in CI** (none of three; just being explicit). Rejected — `make refresh-cassettes` requires `--i-understand-this-spends-tokens` + operator CODEOWNERS approval.

### Anti-patterns avoided

For each "flag on sight" anti-pattern the critic surfaced:

- **Premature pluggability — three Protocols with one adapter each.** Reduced to *two* Protocols where ADR-0020 / ADR-0017 promise a second adapter (`LeafLlm`, `SolvedExampleStore`). `Embedder` is a one-method Protocol justified by the `model_digest()` cache-key contract.
- **Stringly-typed identifiers — `f"vuln-remediation cve={...}"` query key.** The Phase 4 design replaces this with a typed `Query` Pydantic model (frozen, extra=forbid) whose `digest()` method is the BLAKE3 cache key. The free-text embedding input is constructed from typed fields, not concatenated.
- **Boolean flag for `EgressGuard` loopback.** Replaced with a thread-local set by pytest fixtures; production code path has no flag. Closes the "two behaviors for one global resource" anti-pattern.
- **Capability passed through ten frames.** `BudgetToken` flows only through `FallbackTier → LeafLlm.invoke` (two frames). It does *not* flow through `PromptBuilder` or `FenceWrapper`.
- **Side effects in module import — `sitecustomize.py` install of `EgressGuard`.** Acknowledged. Mitigation: `EgressGuard.reset_for_test()` exposed for tests; install is idempotent. The trade — runtime catch of dynamic socket use — is worth it; the test plan reflects the install with explicit fixtures, not implicit reliance.
- **Untyped `dict[str, Any]` interfaces — `TrustSignal(details={...})`.** Acknowledged as Phase 3's existing convention (`TrustSignal.details` is `dict[str, str | int | bool]` per Phase 3 final-design). Phase 4 does not widen this; new fields go on typed event Pydantic models, not `details`.
- **Tag-and-dispatch without a tagged union — `_validate_lockfile_transform_shape`** (best-practices). Avoided — there is no such function. Validation happens in `PlanProposal`'s smart constructors per-variant.
- **Pattern names that don't survive scrutiny.** This section names patterns by what they are (e.g., "Pipeline (named, sequential, short-circuiting)" not "Chain of Responsibility"; "Module Boundary pattern with CI enforcement" not "Capability pattern"). Closes critic §"Pattern claims that don't survive scrutiny."

Known weaknesses surfaced as follow-ups (not anti-patterns avoided here):

- **`EgressGuard` import-time install** remains a side-effect-at-import. A Phase-5+ follow-up to move it under an explicit `bootstrap_runtime()` call (and make `sitecustomize` opt-in) is recorded as an Open Question.
- **Cassette nightly-drift job** is a process control, not a code control. Documented in `docs/operations/cassettes.md`.

## Risks (top 5)

1. **Cassette rot (Anthropic SDK upgrades) cascades into CI flakiness.** Pinning `anthropic>=0.x,<0.y` strictly + cassette-compatibility smoke test + nightly drift job. The nightly job is the canary; cassettes are the deterministic CI fixture.
2. **Per-workflow budget cap of $1.50 is uncalibrated.** The 250 K-token / $1.50 number is a 2026-Q1 estimate; Phase 13's cost ledger calibrates. Until then, the cap is conservative — an operator override path (`--allow-overrun --operator-ack` with audit emission) is available, not pleasant.
3. **`PlanProposalCallsiteRewrite.diff` 64 KB cap may still kneecap some legitimate major bumps.** Mitigation: the LLM emits `PlanProposalRefuse(reason="out_of_scope")` on truly sweeping rewrites → HITL escalation. The cap is the trade between blast-radius (a wrong diff > 64 KB is hard to review) and capability (some real bumps are large). Phase 15 (agentic recipe authoring) is the right home for sweeping rewrites.
4. **Inline auto-harvest behind `confidence=="high"` may still ingest poisoned examples** if Phase 5's gates fail to catch a specific class of bad fix. Mitigation: Phase 5's strict-AND on `build + install + tests + lockfile_policy + cve_delta + typecheck.typescript` is the gate; the BLAKE3 chain on each ingested record means a future operator can quarantine without losing audit trail.
5. **`fastembed` cross-architecture nondeterminism at 5th-decimal cosine similarity.** Mitigation: the calibration *band* (not point); Phase 6.5 calibrates a recall-at-top-3 target, not a single threshold. Phase-4 CI runs on x86_64 only; arm64 cross-host determinism test is a known Phase-6.5 follow-up.

## Synthesis ledger

### Vertex count

- Performance: ~52 vertices (10 components × 5 decisions/component avg, plus chains, caches, signals).
- Security: ~58 vertices (12 components + threat-model decisions + audit emissions).
- Best-practices: ~45 vertices (7 components + conventions + risks).
- **Total: ~155 vertices.**

### Edges

- **AGREE:** 14 (chromadb local; one in-tree adapter for the LLM seam; Anthropic via SDK; `@register_signal_kind("typecheck.*")` for ADR-0037; pytest-recording cassettes; Pydantic frozen / extra=forbid as default; `prior_attempts` kwarg shape; provenance refuse-mode short-circuit; no LSP in Phase 4; one collection per (task_class, language, build_system); no auto-retry inside the LLM adapter; new top-level `rag/` package separate from plugin; `RecipeApplication` as the return type of the fallback; the four `PlanProposal` variants the LLM may emit at all).
- **CONFLICT:** 14 (LLM output discipline; cosine threshold shape; chromadb single-writer policy; langgraph timing; auto-harvest path; refuse-mode placement [implicit-inherit vs explicit-gate]; SPKI pinning; sentence-transformers vs fastembed; cassette secret sanitization; egress-guard loopback policy; CI key-source policy; `RecipeOutcome` widening; `DeterministicRetargeter` existence; per-workflow budget enforcement).
- **COMPLEMENT:** 11 (security's BLAKE3 chain + performance's content-addressed embedding cache compose; best-practices' canonical-YAML + chromadb-derived-sqlite + performance's chromadb HNSW compose; security's `FenceWrapper` + performance's prompt-cache discipline compose; security's `LlmInvocationGuard` + performance's `cost.llm.call` event emission compose; security's `CassetteSanitizer` + performance's `cassettes.lock` compose; performance's plugin-internal layout + best-practices' plugin-agnostic substrate packages compose; …).
- **SUBSUME:** 6 (performance's `TierChain` async generator is subsumed by security's `FallbackTier`; best-practices' `LlmReplanRecipe` LangGraph subgraph is subsumed by security's `FallbackTier`; security's three-way `PlanProposal` is subsumed and extended by the synthesis 4-variant version with relaxed 64 KB cap; best-practices' inline `Embedder` is subsumed by `Embedder` Protocol; …).

### Conflict-resolution table

Scoring 0–3 per criterion; commitments-fit is veto (0 = cannot win).

| Dimension | [P] picks | [S] picks | [B] picks | Winner | Exit-fit | Roadmap-fit | Commitments-fit | Critic-fit | Pattern-fit | Sum |
|---|---|---|---|---|---|---|---|---|---|---|
| LLM output discipline | Pydantic-validate prose | Closed sum type + JSON schema | LangGraph parse node | **[S]** | 3 | 3 | 3 | 3 | 3 | **15** |
| RAG "byte-applicable" retargeter | `DeterministicRetargeter` | None | None | **None ([S]+[B])** | 3 | 2 | 3 | 3 | 2 | **13** vs [P]'s 5 |
| Vector store | chromadb local | chromadb embedded | chromadb local | **AGREE — chromadb embedded mode** | 3 | 3 | 3 | 2 | 2 | **13** |
| Embedding model | `fastembed` ONNX | `sentence-transformers` (offline-bootstrap) | `sentence-transformers` | **[P]** | 3 | 3 | 3 | 3 | 2 | **14** vs [S]/[B]'s 11 |
| LangGraph in Phase 4? | No | No | Yes (3-node flat graph) | **[P+S]** | 3 | 3 | 3 | 3 | 3 | **15** vs [B]'s 6 (roadmap violation) |
| Cosine threshold | 0.92/0.97 floors | 0.85 floor | 0.78 floor | **Departure — two-threshold band in plugin.yaml** | 3 | 3 | 3 | 3 | 3 | **15** |
| Per-workflow budget cap | Events; defer to Phase 13 | Hard cap as capability | None; defer to Phase 13 | **[S]** | 3 | 2 | 3 | 3 | 3 | **14** |
| Prompt-injection containment | None | `FenceWrapper`+`CanaryGuard` | None | **[S]** | 3 | 3 | 3 | 3 | 3 | **15** |
| Provenance refuse-mode placement | Not mentioned | Explicit gate before LLM | Inherited from Phase 3 | **[S]** | 3 | 3 | 3 | 3 | 3 | **15** |
| Auto-harvest path | Inline unconditional | Capability-gated by Phase 5 | Deferred to Phase 11 operator CLI | **Departure — inline behind `confidence=="high"` gate** | 3 | 3 | 3 | 3 | 3 | **15** |
| Network egress | Not mentioned | EgressGuard + SPKI pin | Not mentioned | **[S] minus SPKI** (system trust + EgressGuard + OS filter + nightly drift) | 3 | 3 | 3 | 3 | 3 | **15** vs [S]'s 11 (SPKI self-DOS) |
| Cassette secret hygiene | Not mentioned | `CassetteSanitizer` + CODEOWNERS | Headers only scrubbed | **[S]** | 3 | 3 | 3 | 3 | 2 | **14** |
| `RecipeOutcome` widening | Not widened | Not widened | Widened with 2 variants | **[P+S]** | 3 | 3 | 3 | 3 | 3 | **15** vs [B]'s 7 (Phase 7 break) |
| Fence-CI amendment | Half-written | Half-written | Half-written | **Departure — exact diff in §Load-bearing commitments check** | 3 | 3 | 3 | 3 | 2 | **14** |
| chromadb single-writer at 24 workers | Acknowledged + deferred | Embedded mode | Acknowledged + deferred | **AGREE + asyncio.Lock at adapter for Phase 4** | 2 | 3 | 3 | 3 | 2 | **13** |

### Shared blind spots considered

| Critic-named blind spot | Synthesis disposition |
|---|---|
| Single global cosine threshold (all three) | **Departed.** Two-threshold band lives in `plugin.yaml`; Phase 6.5 calibrates. |
| chromadb as in-tree vector store (all three) | **Carried.** Single-writer caveat acknowledged; per-process `asyncio.Lock` at adapter; Phase 11 swap is the resolution. The schema-migration risk is mitigated by YAML-as-canonical (rebuild without re-embedding). |
| Cassette layer "solves CI determinism" (all three) | **Departed.** Cassettes solve CI determinism + the nightly real-API drift job solves cassette-vs-reality. Two controls, not one. |
| `prior_attempts` semantics disagreement across three | **Carried — security's interpretation.** RAG bypass on retry; fence-wrapped `prior_failure_summary` in prompt. Documented in Phase 4 ADR as deliberate departure from ADR-0011's chain order. |
| `cassettes.lock` per-case BLAKE3 for Phase 6.5 | **Carried — performance's interpretation.** Ships in Phase 4. |
| `langgraph` Phase 4 vs Phase 6 | **Departed.** No langgraph in Phase 4. |
| Provenance Phase-4 use of a Phase-7 primitive | **Carried — security's option (c).** Phase 4-scoped `_AppLayerOnlyProvenance` consumes Phase 3's `NpmVulnProvenanceAdapter`; Phase 7 ships the base-image adapters. |

### Pattern reconciliation

| Pattern | Where it appeared | Synthesis disposition | Rationale |
|---|---|---|---|
| Hexagonal architecture | All three named the LLM seam as hexagonal | **Renamed to "Adapter at a hard trust boundary"** | Critic correctly: the domain isn't actually isolated from infrastructure. Honesty beats jargon. |
| Plugin architecture | [P] applied it, [S]+[B] didn't | **Applied** | Phase 3 ships ADR-0031 — using it is the convention. |
| Strategy | [P] said "doesn't fit" for tier chain | **Agreed** — Pipeline, not Strategy | The order *is* the policy. |
| Capability pattern | [S] applied it to RAG writes and budget | **Budget: Capability. RAG writes: renamed "Module Boundary pattern with CI enforcement"** | Critic correctly: Pydantic constructors are public — runtime unforgeability is overclaim. |
| Make illegal states unrepresentable | [S]+[B] applied it; [P] implicitly | **Applied** to `PlanProposal`, `PlanOutcome`, `RetrievalOutcome` | Core to ADR-0033. |
| Tagged union / sum type | All three | **Applied** | ADR-0033. |
| Smart constructor | All three (Pydantic `extra="forbid"`) | **Acknowledged** with critic-honest caveat: a test asserts `model_construct` is not called in production code (`tests/fence/test_no_model_construct.py`). |
| Newtype | All three | **Applied** to `ProbeId`, `SolvedExampleId`, `BudgetToken`, `HexNonce`, etc. |
| Open/Closed + Registry | All three (`@register_signal_kind`) | **Applied** |
| State pattern (LangGraph idiom) | [B] applied | **Rejected** — no LangGraph in Phase 4 |
| Chain of Responsibility | [P] applied to TierChain | **Renamed to Pipeline** — three named method calls, not a CoR Protocol |
| Functional core / Imperative shell | [S] applied to FenceWrapper | **Applied** — fencing is pure; audit emission is impure |
| Event Sourcing + Append-only log + Chain of hashes | [S] applied | **Applied** — extends Phase 3 idiom |
| Specification pattern (composable named rules) | Not applied by any | **Newly applied** to the inline-harvest gate (`outcome.passed AND confidence == "high"`) and the calibration-band thresholds |
| Cache-aside / Content-addressed cache | [P] applied | **Applied** to embedding cache |
| Adapter pattern | All three for chromadb wrapper | **Applied** but minus the [B]-flagged "Repository pattern + Adapter pattern" two-name-for-wrapper redundancy |

### Departures from all three inputs

Five departures where the synthesis picks a position none of the three proposed:

1. **`PlanOutcome` as a Phase-4-local sum type wrapping `RecipeOutcome`, not widening it.** None of the three did this; [B] widened; [P]+[S] just used `RecipeOutcome` directly. The departure closes Phase 7's exit criterion (the diff for Phase 7 touches only the new plugin directory).
2. **Two-threshold calibration band (`high_floor`, `degraded_floor`) in `plugin.yaml`, not a single magic number.** All three used a single float threshold.
3. **No SPKI pinning of `api.anthropic.com`.** Security shipped pinning; performance and best-practices ignored egress entirely. Synthesis rejects pinning operationally + ships compensating controls.
4. **Inline auto-harvest gated by `confidence == "high"`.** Performance: unconditional inline. Security: capability-gated but the gate fires at Phase 5. Best-practices: deferred to Phase 11. Synthesis: inline + gated.
5. **Pytest-only thread-local for `EgressGuard` loopback (no production loopback carve-out).** Security shipped unconditional loopback; the critic showed this defeats the threat model; the synthesis replaces it with a fixture-set thread-local.

## Exit-criteria checklist

For each Phase 4 exit criterion in `roadmap.md`:

- [x] **"A breaking-change vuln (e.g., a major-version-bump CVE) is solved end-to-end with the LLM fallback"** → `tests/integration/test_phase4_e2e_breaking_change.py` against `fixtures/vuln-major-bump/express-cve-2026-1234/`; `FallbackTier.run` → `PlanProposalCallsiteRewrite` → `Transform` → Stage 6 validate strict-AND passes including `typecheck.typescript`.
- [x] **"and recorded into the solved-example store"** → inline harvester gated by `TrustOutcome.passed AND confidence == "high"`; `ingest_solved_example` writes via `SolvedExampleWriteCapability` (Phase-4 interim mint; Phase 5 supersedes).
- [x] **"Re-running the same case hits RAG, not LLM"** → `tests/integration/test_phase4_e2e_replay_lands_rag.py` runs the same case with no operator step between runs; `RagHit` fires; LLM still invoked but with few-shot → lower input-token cost asserted via `LlmCostAccrued` deltas. **The roadmap phrase "hits RAG, not LLM" is interpreted as "RAG shapes the LLM call to produce a cheaper outcome" — not literal LLM-skip — because the critic showed literal LLM-skip is fan-fiction for the major-bump case.**
- [x] **"produces an equivalent fix at lower cost"** → asserted by `LlmCostAccrued` ledger entries; Phase 13 cost-ledger will compose.
- [x] **"first `typecheck.<language>` `SignalKind` lands"** → `@register_signal_kind("typecheck.typescript")` ships in `plugins/.../adapters/ts_typecheck_signal.py`; strict-AND folded; `tests/integration/test_typecheck_signal_catches_signature_drift.py` proves it fires before tests run.
- [x] **"LSP is explicitly not introduced here"** → `tests/fence/test_no_lsp_in_phase4.py` AST-walks; no LSP imports.

## Load-bearing commitments check

For each commitment in `production/design.md` §2:

- **§2.1 No LLM in the gather pipeline.** Honored. `anthropic`, `chromadb`, `fastembed`, `onnxruntime` are admitted in the *runtime* closure but explicitly fenced out of `src/codegenie/probes/`, `coordinator/`, `cache/`, `output/`, `schema/`. **Fence amendment (the load-bearing change none of the three wrote out — closes critic findings):**

  ```python
  # tests/unit/test_pyproject_fence.py (current state, unchanged here)
  FORBIDDEN_LLM_SDKS = frozenset({"anthropic", "langgraph", "openai", "langchain", "transformers"})

  # tests/fence/test_pyproject_fence_phase4.py  (NEW — Phase 4 ships)
  # The Phase 4 fence is *path-scoped*, not closure-scoped:
  GATHER_PIPELINE_PATHS = frozenset({
      "src/codegenie/probes/",
      "src/codegenie/coordinator/",
      "src/codegenie/cache/",
      "src/codegenie/output/",
      "src/codegenie/schema/",
  })
  PHASE4_ADMITTED_PACKAGES = frozenset({"anthropic", "chromadb", "fastembed", "onnxruntime"})
  PHASE4_STILL_FORBIDDEN = frozenset({"langgraph", "openai", "langchain", "transformers", "sentence_transformers", "torch"})

  # Assertion: no source under GATHER_PIPELINE_PATHS imports any of
  # PHASE4_ADMITTED_PACKAGES or PHASE4_STILL_FORBIDDEN.
  # Assertion: no source anywhere imports PHASE4_STILL_FORBIDDEN.
  # Assertion: only `src/codegenie/fallback/leaf/anthropic_adapter.py` imports `anthropic`.
  # Assertion: only `src/codegenie/rag/` imports `chromadb`, `fastembed`, `onnxruntime`.
  ```
  **The original `FORBIDDEN_LLM_SDKS` set is not edited.** Phase 4 ships a *path-scoped* fence that complements it. `langgraph`, `openai`, `langchain`, `transformers`, `sentence_transformers`, `torch` remain forbidden anywhere.

- **§2.2 Facts, not judgments.** Honored. LLM self-confidence is logged and discarded; `TrustScorer` consumes only objective signals (`build`, `install`, `tests`, `lockfile_policy`, `cve_delta`, `typecheck.typescript`). `PlanProposal.rationale` is audit-log-only — *never re-prompted* (critic [S] §"if rationale survives anywhere that influences trust scoring, this commitment cracks" addressed by AST-walking test).

- **§2.3 Honest confidence.** Honored. `RetrievalOutcome` discriminated union carries `RagDegraded` explicitly; the inline-harvest gate is `confidence == "high"`, not a number. `IndexHealthProbe` analog: `RagDegraded` is the audit signal.

- **§2.4 Determinism over probabilism for structural changes.** Acknowledged as the *stress point* (critic roadmap §3.3). Phase 4 *is* the LLM-for-judgment-call exception per ADR-0011; the mitigation is the gate stack (`provenance` + `budget` + `PlanProposal` smart-constructors + Phase 5 strict-AND on `typecheck.typescript`). Determinism preserved under cassette replay (`tests/property/test_determinism_under_cassette_replay.py`).

- **§2.5 Extension by addition.** Honored. Zero edits to `RemediationOrchestrator`, `TrustScorer`, `RecipeEngine` Protocol, `Transform` ABC, `ApplyContext`, `EventLog`, `SubprocessJail`, `PluginRegistry`, kernel `Plugin` Protocol. `RecipeOutcome` (Phase 3 sum type) is **not widened** — `PlanOutcome` is Phase-4-local. Asserted by `tests/fence/test_kernel_frozen.py` + `tests/property/test_plan_outcome_no_recipe_outcome_widening.py`.

- **§2.6 Organizational uniqueness as data, not prompts.** Honored. The skill text lives in `plugins/.../skills/vuln-major-bump.md` (data); the instruction template lives in `plugins/.../skills/leaf-llm-instruction.md` (data); thresholds live in `plugin.yaml` (data).

- **§2.7 Progressive disclosure.** Honored. `RepoContext` slice + tree-sitter outline are referenced/indexed; the LLM gets a bounded slice, not the full repo.

- **§2.8 Humans always merge.** Honored. Phase 4 produces a branch + report; no push capability; Phase 11 owns PR opening.

- **§2.9 Cost observable end-to-end and bounded per workflow.** Honored. `LlmInvocationGuard` is the per-workflow cap; `LlmCostAccrued` events feed Phase 13's ledger.

## Roadmap coherence check

- **What prior phases established that this design depends on:**
  - Phase 3: `RemediationOrchestrator`, `TrustScorer`, `Transform` ABC, `ApplyContext`, `RecipeEngine`, `RecipeOutcome` sum type, `PluginRegistry`, `EventLog` two-stream + BLAKE3 chain, `SubprocessJail`, `@register_signal_kind` open registry, `NpmVulnProvenanceAdapter` refuse-mode shape (ADR-0038), `SandboxedRelativePath`, `Result[T, E]`, `BundleBuilder` + `ConcreteBundle` + TCCM, `ALLOWED_BINARIES` allowlist pattern.
  - Phase 2: `RepoContext` artifact, `VulnIndex`, syft SBOM as the evidence base for `vuln.provenance`, tree-sitter outline.
  - Phase 0: `forbidden-patterns` pre-commit hook, `import-linter`, fence-CI, `make check` gate, `make refresh-cassettes` operator path.

- **What this design establishes that later phases will need:**
  - **Phase 5** (already merged) consumes: `FallbackTier.run(..., prior_attempts=[...])` signature; `LlmInvocationGuard.running_total()`; `FenceWrapper` for `prior_failure_summary` fencing; `SolvedExampleWriteCapability` minting hook; BLAKE3 chain head Phase 5's `RetryLedger` reads at startup; `cassettes.lock` per-case hash for Phase 5's bench replay; `AttemptSummary` Pydantic shape with `prior_failure_summary` field.
  - **Phase 6** consumes: `FallbackTier.run` as a callable Phase 6's LangGraph compiler lifts into a state-machine node; `PlanProposal` discriminated union as the typed state.
  - **Phase 6.5** consumes: `cassettes.lock` per-case BLAKE3; `RetrievalOutcome` for retrieval-quality bench; the Phase 4 solved-example corpus for backfilling `bench/vuln-remediation/cases/`.
  - **Phase 7** consumes: `ProvenanceGate` extended with base-image adapters; `vulnerability-remediation--node--*` wildcard plugin convention if `typecheck.typescript` is shared; **`RecipeOutcome` left unchanged** (Phase 7's exit criterion).
  - **Phase 11** consumes: `SolvedExampleStore` Protocol → pgvector adapter swap for concurrent writes; `ingest_solved_example` from merge webhook (Phase 4 ships the write primitive).
  - **Phase 13** consumes: `LlmCostAccrued` events; `LlmInvocationGuard.running_total()` projection.

- **New ADRs implied by this design (to be drafted in `docs/phases/04-vuln-llm-fallback-rag/ADRs/`):**
  - **ADR-04-0001** — `ALLOWED_BINARIES` amendment: add `./node_modules/.bin/tsc` (content-hashed per major Node version) per ADR-0012 pattern.
  - **ADR-04-0002** — Fence-CI amendment: introduce path-scoped Phase 4 fence (`tests/fence/test_pyproject_fence_phase4.py`); original `FORBIDDEN_LLM_SDKS` set unchanged.
  - **ADR-04-0003** — RAG bypass on retry: `FallbackTier.run` with `prior_attempts` non-empty skips RAG. Deliberate departure from ADR-0011's chain order (which describes initial-plan order).
  - **ADR-04-0004** — No SPKI pin for `api.anthropic.com`; compensating controls (`EgressGuard` + OS-level egress filter + nightly drift job). SPKI reintroduction requires a future ADR amendment + runbook.
  - **ADR-04-0005** — Inline auto-harvest gated by `TrustOutcome.passed AND confidence == "high"`; capability minted by Phase-4 interim shim, superseded by Phase 5 `GateRunner` mint.
  - **ADR-04-0006** — `PlanOutcome` is Phase-4-local; `RecipeOutcome` Phase 3 sum type stays unchanged. Phase 7 exit criterion preserved.
  - **ADR-04-0007** — Phase-4-scoped `_AppLayerOnlyProvenance` consumer of `NpmVulnProvenanceAdapter`; Phase 7 ships the full multi-adapter chain.
  - **ADR-04-0008** — Calibration band (`high_floor`, `degraded_floor`) in `plugin.yaml`; Phase 6.5 owns calibration evidence.

## Open questions deferred to implementation

1. **Per-`vulnerability-remediation--node--*` base plugin for `typecheck.typescript`.** ADR-0031's wildcard convention could let Phase 7's Node plugin inherit the signal without re-registering. Phase 4 ships it plugin-local; Phase 7 (or Phase 6.5 during plugin layout review) decides whether to promote to a shared base.
2. **`EgressGuard` bootstrap mechanism.** `sitecustomize.py` install is acknowledged side-effect-at-import. A Phase-5+ follow-up to move it under `bootstrap_runtime()` is recorded but not done here.
3. **`Embedder` Protocol staying single-adapter.** If after Phase 6.5 calibration `fastembed` is shown to clip retrieval quality at the corpus size Phase 7 grows the bench to, a Voyage adapter lands behind the existing Protocol — additive, no `Embedder` change. Until then, the Protocol may be over-abstracted; the trade is keeping it.
4. **Operator-mode `codegenie remediate-batch` cadence for prompt-cache reuse.** The 65% prompt-cache target only holds for batch-cadenced workflows on similar CVEs. Phase 13.5's operator portal owns surfacing this; Phase 4 just emits the events.
5. **Anthropic SDK version pinning vs cassette stability.** Strict pin (`anthropic>=0.x,<0.y`) + cassette-compatibility smoke test is the chosen posture; the actual lower/upper bounds land at implementation time.
6. **`PlanProposalCallsiteRewrite.diff` 64 KB cap calibration.** If post-Phase-4 evidence shows the cap is *still* kneecapping legitimate fixes, the next ADR is "raise to 96 KB and shrink the user-block budget by 32 KB to keep token totals constant." Calibration is Phase 6.5 evidence.
7. **Inline-harvest gate refinement.** `confidence == "high"` is one knob; a second knob — "and the matched recipe template / few-shot example is not itself within N edits of the new record" — would mitigate the "near-duplicate corpus drift" failure mode the critic flagged. Deferred until Phase 6.5 has retrieval-quality data.
8. **Cross-architecture embedding determinism.** Phase-4 CI runs x86_64 only. The arm64 cross-host determinism test belongs in Phase 6.5's bench harness; recorded as a known gap.
