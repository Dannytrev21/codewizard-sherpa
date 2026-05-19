# Phase 04 — Vuln remediation: LLM fallback + solved-example RAG: ADRs

Architecture Decision Records for Phase 4, in Nygard format. Each ADR captures one load-bearing decision: the context, the alternatives considered, what was chosen, the tradeoffs accepted, the consequences, and how reversible the choice is.

**Phase architecture:** [phase-arch-design.md](../phase-arch-design.md) — full architecture spec (4+1 views, components, data model, edge cases, harness engineering).
**Source design:** [final-design.md](../final-design.md) — synthesized from three competing lens designs (`design-performance.md`, `design-security.md`, `design-best-practices.md`).
**Critique:** [critique.md](../critique.md) — devil's-advocate review whose findings drove several of these ADRs.
**Production reference:** [docs/production/adrs/](../../../production/adrs/) — the project-level ADR set this phase composes with.

## Index

| # | Title | Tags |
|---|---|---|
| [0001](0001-plan-proposal-closed-sum-type.md) | `PlanProposal` closed Pydantic discriminated union as the only shape the LLM may emit | tagged-union · smart-constructor · make-illegal-states-unrepresentable · llm-output-discipline |
| [0002](0002-fallback-tier-pipeline-no-langgraph.md) | `FallbackTier` as a named sequential Pipeline — no LangGraph in Phase 4 | pipeline · open-closed · phase-boundary · roadmap-coherence |
| [0003](0003-path-scoped-fence-amendment.md) | Path-scoped fence amendment — admit `anthropic`, `chromadb`, `fastembed`, `onnxruntime` only outside the gather pipeline | module-boundary · ci-enforcement · fence · import-linter |
| [0004](0004-plan-outcome-wraps-recipe-outcome.md) | `PlanOutcome` wraps `RecipeOutcome` — Phase-3 sum type is not widened | composition-over-inheritance · open-closed · tagged-union · phase-boundary |
| [0005](0005-no-spki-pin-egress-defense-in-depth.md) | No SPKI pin for `api.anthropic.com` — `EgressGuard` + system trust + OS filter + nightly drift job | defense-in-depth · operational-resilience · trust-boundary · network-egress |
| [0006](0006-egress-guard-no-production-loopback-carveout.md) | `EgressGuard` rejects loopback in production — pytest-only thread-local opt-in | threat-model · trust-boundary · test-isolation · anti-pattern-avoidance |
| [0007](0007-fastembed-onnx-over-sentence-transformers.md) | `fastembed` ONNX over `sentence-transformers`/torch for local embeddings | dependency-discipline · embedded-runtime · contributor-friction · ports-and-adapters |
| [0008](0008-two-threshold-calibration-band.md) | Two-threshold calibration band for RAG retrieval — `high_floor`, `degraded_floor` in `plugin.yaml` | tagged-union · honest-confidence · config-as-data · specification-pattern |
| [0009](0009-inline-auto-harvest-confidence-gate.md) | Inline auto-harvest gated by `TrustOutcome.passed AND confidence == "high"`; capability via Module Boundary | specification-pattern · module-boundary · ci-enforcement · exit-criterion · honest-naming |
| [0010](0010-llm-invocation-guard-budget-token-capability.md) | `LlmInvocationGuard` + `BudgetToken` — per-workflow budget cap as a function-signature capability | capability-pattern · circuit-breaker · type-driven-safety · cost-discipline |
| [0011](0011-rag-bypass-on-retry.md) | RAG bypass on retry — `prior_attempts` non-empty skips RAG, prompt carries fence-wrapped `prior_failure_summary` | retry-semantics · same-wrong-answer-twice · phase-5-contract |
| [0012](0012-provenance-gate-explicit-tier-zero.md) | `ProvenanceGate` as an explicit tier-0 gate — refuse non-app-layer CVEs before any LLM tokens are spent | specification-pattern · refuse-mode · tier-zero · cost-discipline |
| [0013](0013-fence-wrapper-canary-scan-before-truncation.md) | `FenceWrapper` + `CanaryGuard` — canary scans the UNTRUNCATED payload, then truncate | functional-core-imperative-shell · trust-boundary · newtype · smart-constructor · prompt-injection-containment |
| [0014](0014-cassette-discipline-security-control.md) | Cassette discipline as a security control — `CassetteSanitizer` + `cassettes.lock` + nightly drift job | ci-enforcement · supply-chain · test-determinism · nightly-canary · content-addressed-manifest |
| [0015](0015-typecheck-typescript-signal-and-tsc-allowed-binary.md) | `typecheck.typescript` `SignalKind` lands; `./node_modules/.bin/tsc` added to `ALLOWED_BINARIES` | registry-pattern · open-closed · trust-signal · subprocess-allowlist |
| [0016](0016-chromadb-embedded-yaml-canonical-store.md) | chromadb PersistentClient embedded mode; YAML records as canonical source; sqlite derived | ports-and-adapters · content-addressed-storage · single-writer · operational-recovery |
| [0017](0017-attempt-anchor-event-schema.md) | `AttemptAnchor` event — schema for future critic-training and replay audit | event-sourcing · audit-anchor · schema-versioning · extension-by-addition · option-preservation |

## Conventions

- Filenames `NNNN-kebab-case-title.md`, 4-digit zero-padded, numbered locally per phase from 0001.
- Numbers are immutable — superseded ADR keeps its number; the new ADR gets the next.
- Cross-references to production ADRs use `../../../production/adrs/NNNN-*.md`.
- Cross-references to peer Phase-4 ADRs use bare filenames (e.g., `[ADR-0001](0001-plan-proposal-closed-sum-type.md)`).

## Reading guide

Read in this order if you're new to the phase:

1. **[0001](0001-plan-proposal-closed-sum-type.md)** — the LLM output shape; everything downstream depends on this being a closed sum type.
2. **[0002](0002-fallback-tier-pipeline-no-langgraph.md)** — the dispatch shape; explains why Phase 4 has no LangGraph.
3. **[0004](0004-plan-outcome-wraps-recipe-outcome.md)** — how Phase 4's new types compose with Phase 3's frozen `RecipeOutcome` without widening it.
4. **[0003](0003-path-scoped-fence-amendment.md)** — how `anthropic`/`chromadb`/`fastembed`/`onnxruntime` enter the runtime closure without breaking commitment §2.1.
5. **[0012](0012-provenance-gate-explicit-tier-zero.md)** + **[0010](0010-llm-invocation-guard-budget-token-capability.md)** — the cost-protection stack: provenance refuses pre-LLM, budget caps in-LLM.
6. **[0013](0013-fence-wrapper-canary-scan-before-truncation.md)** — the trust-boundary discipline for untrusted bytes entering the prompt.
7. **[0005](0005-no-spki-pin-egress-defense-in-depth.md)** + **[0006](0006-egress-guard-no-production-loopback-carveout.md)** — network-egress posture: defense-in-depth without SPKI fragility; no loopback carve-out.
8. **[0008](0008-two-threshold-calibration-band.md)** + **[0009](0009-inline-auto-harvest-confidence-gate.md)** — RAG honesty: a three-outcome band + the harvest gate that makes the roadmap exit criterion hold in production behavior.
9. **[0011](0011-rag-bypass-on-retry.md)** — Phase 5's retry path semantics: a deliberate departure from production ADR-0011's chain order.
10. **[0007](0007-fastembed-onnx-over-sentence-transformers.md)** + **[0016](0016-chromadb-embedded-yaml-canonical-store.md)** — embedded RAG runtime choices.
11. **[0014](0014-cassette-discipline-security-control.md)** — cassette discipline as a four-layer control (sanitize / scanner / manifest / nightly drift).
12. **[0015](0015-typecheck-typescript-signal-and-tsc-allowed-binary.md)** — first `typecheck.<lang>` signal per production ADR-0037.

## Cross-references to production ADRs amended or extended by this phase

- [production ADR-0005](../../../production/adrs/0005-no-llm-in-gather-pipeline.md) — Commitment §2.1 honored via path-scoped fence ([0003](0003-path-scoped-fence-amendment.md)).
- [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) — Initial-plan chain order; retry path is a deliberate departure ([0011](0011-rag-bypass-on-retry.md)).
- [production ADR-0017](../../../production/adrs/0017-knowledge-graph-backend.md) — Deferred KG-backend; Phase 4 ships chromadb local + Protocol for Phase 11 pgvector swap ([0016](0016-chromadb-embedded-yaml-canonical-store.md)).
- [production ADR-0020](../../../production/adrs/0020-leaf-agents-sdk.md) — Deferred multi-vendor; Phase 4 ships one vendor (Anthropic) behind a `LeafLlm` Protocol; defense-in-depth ([0005](0005-no-spki-pin-egress-defense-in-depth.md)) keeps the un-deferral cheap.
- [production ADR-0025](../../../production/adrs/0025-per-workflow-cost-cap.md) — Cost cap pattern; Phase 4 ships the local-POC instance via `LlmInvocationGuard` ([0010](0010-llm-invocation-guard-budget-token-capability.md)).
- [production ADR-0033](../../../production/adrs/0033-domain-modeling-discipline.md) — Sum-type discipline applied to `PlanProposal` ([0001](0001-plan-proposal-closed-sum-type.md)) and `RetrievalOutcome` ([0008](0008-two-threshold-calibration-band.md)).
- [production ADR-0037](../../../production/adrs/0037-layered-analysis-funnel-scip-typechecker-lsp.md) — First `typecheck.<lang>` `SignalKind` lands ([0015](0015-typecheck-typescript-signal-and-tsc-allowed-binary.md)).
- [production ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md) — Refuse-mode lifted to explicit tier-0 gate ([0012](0012-provenance-gate-explicit-tier-zero.md)); Phase 7 ships full multi-adapter primitive.

## Decisions noted but not yet documented in arch / final-design

All decisions surfaced in `final-design.md`'s Synthesis ledger + Departures + the Architect's "8 new Phase-4 ADRs implied" list are documented above. Two design choices were folded into existing ADRs rather than separated:

- **`LeafLlm` Protocol earning its keep with one adapter today** — covered in [ADR-0005](0005-no-spki-pin-egress-defense-in-depth.md) (defense-in-depth makes [production ADR-0020](../../../production/adrs/0020-leaf-agents-sdk.md)'s un-deferral cheap) and [ADR-0001](0001-plan-proposal-closed-sum-type.md) (the Protocol is the trust boundary `PlanProposal` validation hangs off). No standalone ADR — the Protocol's existence is implied by ADR-0020's eventual resolution; Phase 4 ships the adapter and the Protocol's tests but doesn't justify the Protocol separately.
- **`Embedder` Protocol kept despite single-adapter premature-pluggability flag** — covered in [ADR-0007](0007-fastembed-onnx-over-sentence-transformers.md) (the `model_digest()` method is the cache-key contract; the Protocol stays for that reason). The toolkit's premature-pluggability flag is acknowledged in the ADR; no separate ADR for the meta-decision.

If a future reader of this index sees a load-bearing decision they expected here and don't find, the absence is intentional or an oversight worth raising via a new ADR amendment.
