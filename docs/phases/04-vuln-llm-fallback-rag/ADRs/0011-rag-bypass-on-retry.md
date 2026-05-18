# ADR-0011: RAG bypass on retry — `prior_attempts` non-empty skips RAG, prompt carries fence-wrapped `prior_failure_summary`

**Status:** Accepted
**Date:** 2026-05-18
**Tags:** retry-semantics · same-wrong-answer-twice · phase-5-contract
**Related:** ADR-0002 (this phase) · [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) · [production ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md)

## Context

Phase 5 has already merged a `FallbackTier.run(advisory, repo_ctx, recipe_selection, *, prior_attempts: list[AttemptSummary] = []) -> RecipeApplication` signature. When validation fails, Phase 5's `GateRunner` re-invokes `FallbackTier.run` with the failed attempt summarized in `prior_attempts`.

The default semantics — re-running the full tier chain with `prior_attempts` as additional context — has a failure mode the critic surfaced (`critique.md §"Phase 5 retry interface coupling"`): RAG retrieval is deterministic on inputs that don't change much between retries. A wrong-shape RAG hit produces a wrong patch the first time; on retry with the same retrieval, it produces the *same wrong patch* with `prior_attempts` as a side context the LLM may or may not weight. The fix arrives only by accident.

[Production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) describes the recipe → RAG → LLM chain order for *initial* planning. It does not address retry semantics. Phase 4 must choose:

- Re-run the full chain on retry (default), accepting the "same wrong answer twice" failure mode.
- Bypass RAG on retry, letting `prior_failure_summary` (the diagnosis of why the last attempt failed) substitute for the RAG few-shot.
- Re-rank RAG on retry to exclude the previously-used hit (smarter; more code; more state).

## Options considered

- **Re-run full chain on retry** (implicit baseline). Retry semantics identical to initial. **Pattern:** Idempotent retry. Risks "same wrong answer twice" via stable retrieval.
- **RAG bypass on retry**, prompt body carries fence-wrapped `prior_failure_summary` of the most recent attempt. **Pattern:** Retry-as-fresh-context. Diverges from initial chain order; explicit departure from [ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) (which addresses initial-plan order, not retry).
- **Exclude prior-attempt's RAG hit on retry** (re-rank to skip the previously-used few-shot). **Pattern:** Negative-cache retrieval. More state, more code, doesn't address the failure mode where RAG is *correct* but the LLM emitted the wrong patch from it.
- **Multi-arm bandit over RAG strategies** (re-rank/include/exclude/swap top-K). **Pattern:** Bandit-style exploration. Over-engineered for Phase 4's corpus size and retry count (≤3 per ADR-0014).

## Decision

When `FallbackTier.run` is called with `prior_attempts` non-empty, **RAG retrieval is skipped entirely.** The prompt body is assembled with the fence-wrapped `prior_failure_summary` from the most recent `AttemptSummary` as the substitute for what RAG would have contributed. **Pattern:** Retry-as-fresh-context. Recorded as a *deliberate departure* from [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md)'s chain order — which describes initial-plan order, not retry order.

## Tradeoffs

| Gain | Cost |
|---|---|
| The "same wrong RAG hit produces same wrong patch twice" failure mode is structurally eliminated — RAG is not consulted on retry | RAG-informed retries are impossible by design; if the initial RAG hit was *right* but the LLM emitted a wrong patch, retry doesn't get to retry-with-RAG |
| `prior_failure_summary` is fenced as `source_kind="prior_attempt_summary"` (4 KB cap) — the LLM sees diagnostic context, not raw RAG bytes | The fence cap (4 KB) bounds how much diagnostic context the LLM can see; long Phase-5 sandbox-stderr dumps must be truncated upstream |
| Retry path is structurally distinct in audit (`RagSkippedOnRetry` event); operator-portal renders the retry as "fresh LLM run, no RAG" | Two retry modes (retry-skips-RAG vs initial-uses-RAG) means the audit log carries two prompt shapes; consumers must handle both |
| Phase 5's `GateRunner` consumes the same `RecipeApplication` shape regardless of retry — no Phase-5 contract change | Phase 6's LangGraph migration must preserve the retry-bypass branch when lifting `FallbackTier.run` into a state-machine node — adding it to the test fixture (`tests/fixtures/fallback_tier_callable.py`) |
| The deliberate departure from [ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) is documented (not silently differing) — future readers see the rationale | A future "RAG-aware retry" amendment would need this ADR superseded plus a re-justification |

## Pattern fit

The toolkit doesn't name a "retry semantics" pattern explicitly. The honest framing is: retries are *not* idempotent on RAG because RAG retrieval is deterministic on stable inputs; idempotent re-runs reproduce the same wrong outcome. The pattern is "retry-as-fresh-context": the retry path is structurally distinct from the initial path, with the failure summary substituting for the RAG few-shot.

[Production ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md) caps retries at three per gate transition; combined with this ADR, the worst case is three LLM-only attempts (no RAG re-consultations). The bounded-blast-radius commitment (commitment §2.9) is preserved.

## Consequences

- `FallbackTier.run` has a branch on `bool(prior_attempts)`: empty → RAG path; non-empty → bypass path.
- Audit event `RagSkippedOnRetry(attempt_count, last_failure_kind)` fires on the bypass path.
- The prompt template (`plugins/.../skills/leaf-llm-instruction.md`) has a conditional block "you previously attempted this fix and it failed; here is the failure summary" gated by `prior_attempts != []`.
- Phase 5's `AttemptSummary` Pydantic shape must include `prior_failure_summary: str` (≤ 8 KB raw, truncated to 4 KB fenced) — Phase 5's contract.
- The integration test `tests/integration/test_phase4_retry_path_bypasses_rag.py` asserts: Phase 5 simulator passes `prior_attempts=[summary]`; RAG retriever is *not* called (mock with `pytest.fail` side effect); fence-wrapped `prior_failure_summary` appears in prompt body (verified via cassette inspection).
- Phase 6's LangGraph migration preserves the retry-bypass branch as a conditional edge in the lifted node — `tests/fixtures/fallback_tier_callable.py` is the contract.
- The deliberate departure from [ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) is recorded here; ADR-0011's chain order remains canonical for *initial* planning.
- Operators reviewing a HITL-escalated retry can read the audit chain and see that RAG was skipped (intentional), saving triage time.

## Reversibility

**Low.** Re-introducing RAG on retry is a one-line code change but reintroduces the "same wrong answer twice" failure mode. A future "RAG-aware retry" (e.g., exclude prior hit + re-query) is additive logic — would need a Phase-4 ADR amendment + Phase 5 contract addendum (`AttemptSummary.used_few_shot_ref`). Changing the bypass to a *re-rank-with-exclude* strategy is medium-cost: needs the negative-cache state in `SolvedExampleRetriever`.

## Evidence / sources

- `../final-design.md §Component 1 — FallbackTier — "RAG bypass on retry"`
- `../final-design.md §Shared blind spots considered` ("`prior_attempts` semantics disagreement across three")
- `../phase-arch-design.md §Control flow — Retry path`
- `../phase-arch-design.md §Edge cases — row 11`
- `../critique.md §"Phase 5 retry interface coupling"`
- [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) (initial-plan chain order; this ADR is the retry-path departure)
- [production ADR-0014](../../../production/adrs/0014-three-retry-default-per-gate.md) (three-retry cap composes with retry-bypass)
