# Validation report: S5-01 — `SolvedExampleRetriever.query` composition

**Validated:** 2026-05-22 18:18 EDT
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S5-01 composes the Phase-4 RAG read path: build a typed `Query`, render embedding text, embed it, retrieve raw scored candidates, chain-verify and model-filter them, fence surviving solved-example content, then delegate band classification to S5-02's classifier. The goal is sound and traces to phase-arch Component 9, final-design Component 11, High-level-impl Step 5, ADR-04-0008, ADR-04-0013, ADR-04-0016, and production ADR-0033.

The draft was not executor-ready. It carried four block-level contradictions against already-hardened sibling stories: S4-03 pre-classified store results before S5-01 could verify/fence candidates; S1-04 defines bare `RagMiss` while this story used `RagMiss(reason=...)`; S4-05 exports a pure module-level verifier, not `RecordProvenance.verify(...)`; and the story used a new `rag/events.py` registry instead of the real `plugins.events` event log. All are fixable in place for this story by surfacing the required upstream amendments and tightening the retriever contract, so the verdict is **HARDENED**, with explicit pre-execution caveats.

18 findings — 4 block, 10 harden, 4 nit.

## Context brief

- **Story promise:** `SolvedExampleRetriever.query(...) -> RetrievalOutcome` composes read-only RAG retrieval without `Optional` or untyped sentinels.
- **Phase constraints:** retrieval is skipped only by the caller on retry; this method is the initial-plan RAG path. Retrieved content is untrusted and must be fenced as `source_kind="rag_retrieved"`. `RetrievalOutcome` is a closed union; miss causes are audit facts, not extra fields on `RagMiss`.
- **Sibling constraints:** S4-03 currently needs an amendment to return raw scored candidates; S4-05 owns the pure chain-head verifier and typed orphan event; S2-04 currently fences raw `rag_few_shots` itself and must be reconciled with S5-01's retrieval-side fencing during S6-01.
- **Open ambiguities after edit:** none for this story. The remaining blockers are named cross-story amendments.

## Findings by critic

### Coverage critic

**C1 (block) — Store pre-classifies too early.** S5-01 must inspect every returned candidate before classification; otherwise an orphan top-1 can hide a valid top-2. Hardened S4-03's private `_query_with_embedding(...) -> RetrievalOutcome` cannot support this.
**Fix:** S5-01 now requires a candidate-returning `query_candidates(..., embedding=...) -> Sequence[ScoredSolvedExample]` surface and marks S4-03 amendment as a pre-execution dependency.

**C2 (harden) — Model-mismatch all-excluded path was implicit.** AC-17 named a hook but did not pin the all-excluded behavior.
**Fix:** AC-17 now returns bare `RagMiss()`, emits `RagMissEvent(reason="all_candidates_model_mismatch")`, and skips the classifier.

**C3 (harden) — Empty/all-orphan miss causes needed observability without widening `RagMiss`.**
**Fix:** AC-4/AC-7 use bare `RagMiss()` plus typed `RagMissEvent.reason`.

**C4 (harden) — Fenced segment could be dropped after classification.** `RagHit.few_shot` still carries `SolvedExample`, so the selected `FencedSegment` needs an explicit handoff anchor.
**Fix:** AC-8/AC-14 add `FencedRetrievalCandidate` and `RagCandidateSelectedEvent(record_id, fenced_digest)`, and flag S6-01/S2-04 to preserve the selected fenced segment.

### Test-Quality critic

**T1 (harden) — Query construction AST guard only caught f-strings.** String concatenation, direct `Query(...)`, or `q.text` would pass.
**Fix:** AC-3 now forbids `JoinedStr`, string `BinOp(Add)`, direct `Query(...)`, and `q.text` in `query()`.

**T2 (harden) — `Query.text` was a non-existent field.** S1-04's `Query` is typed fields only.
**Fix:** Added injected `query_text_builder: Callable[[Query], str]`, plus `QueryRenderedEvent`.

**T3 (harden) — Runtime injection test asserted on a non-existent `RagHit.few_shot.content`.**
**Fix:** AC-10 now asserts raw injection bytes never reach `FencedRetrievalCandidate.fenced.content`.

**T4 (harden) — Dispatch-order test did not include the candidate-read surface or query-text render.**
**Fix:** TDD red snippet records `render_query_text` and `store_query_candidates`.

### Consistency critic

**K1 (block) — `RagMiss(reason=...)` contradicts S1-04 and ADR-04-0008.**
**Fix:** All ACs and implementation outline use bare `RagMiss()`; reason moves to `RagMissEvent`.

**K2 (block) — Wrong provenance API.** S4-05 removed model behavior and shipped `verify(record, spanning_log)`.
**Fix:** Constructor now takes `spanning_log` and injected `record_verifier`; AC-6 uses the S4-05 `RagRecordChainOrphan` fields.

**K3 (block) — Wrong event module.** Prior Phase-4 validators repeatedly corrected stale `rag/events.py` / `audit.EventLog` assumptions.
**Fix:** Files-to-touch and AC-14 route all retriever events through `src/codegenie/plugins/events.py` and `tests/unit/plugins/test_events.py`.

**K4 (harden) — S2-04 prompt handoff conflict.** S2-04 fences raw `rag_few_shots`, while phase arch says retrieval-side fencing.
**Fix:** Story preserves retrieval-side fencing and surfaces the S6-01/S2-04 handoff amendment explicitly.

### Design-Patterns critic

**D1 (harden) — Anonymous tuples made illegal/ambiguous states easy.** `list[tuple[FencedSegment, SolvedExample, Similarity]]` is slot-order fragile.
**Fix:** Added frozen `ScoredSolvedExample` and `FencedRetrievalCandidate` dataclasses; `ConfidenceClassifier` consumes `Sequence[FencedRetrievalCandidate]`.

**D2 (harden) — Store classification violates dependency direction.** The store adapter should not own band classification; the retriever composes verification/fencing and delegates to a classifier strategy.
**Fix:** Candidate store Protocol is the port; classifier remains an injected strategy.

**D3 (nit) — No registry needed.** One retriever and one classifier Protocol do not justify a registry/decorator system.
**Fix:** Notes keep constructor injection and no speculative plugin registry.

**D4 (nit) — Canonical YAML bytes need a string adapter for `FenceWrapper`.**
**Fix:** Outline uses `_canonical_yaml_text(record)` as the small adapter boundary over canonical bytes.

## Research briefs

None. No finding required external research; all fixes came from in-repo ADRs, sibling validation reports, and current source conventions.

## Conflict resolutions

- **S1-04 vs S5-01 miss reasons:** S1-04/ADR-04-0008 win. The story uses bare `RagMiss` and reason-bearing events.
- **S4-03 vs S5-01 store split:** S5-01's goal requires raw candidates. The story does not edit S4-03, but records a required S4-03 amendment before execution.
- **S2-04 vs retrieval-side fencing:** Phase arch/final-design still require retrieval-side fencing. S5-01 preserves it, adds an event anchor for the selected fenced candidate, and defers the concrete prompt-builder handoff to S6-01/S2-04.

## Edits applied

1. Header set to `HARDENED`; dependency line expanded with S4-03, S4-05, S1-04, and S2-04 caveats.
2. Validation notes inserted under the header.
3. Context rewritten around constructor-injected `spanning_log`, `record_verifier`, and `query_text_builder`.
4. References corrected for S4-03 candidate-read conflict, S4-05 verifier shape, S1-04 bare `RagMiss`, S2-02 `FenceWrapper`, and `plugins.events`.
5. Goal rewritten to include query-text rendering, raw candidate retrieval, model filtering, and event-based miss reasons.
6. AC-1 adds `ScoredSolvedExample`, `FencedRetrievalCandidate`, `CandidateSolvedExampleStore`, and `query_text_builder`.
7. AC-2 dispatch order now includes render-query-text and candidate query.
8. AC-3 hardened the AST fence.
9. AC-4/AC-7/AC-17 changed miss returns to bare `RagMiss()` plus `RagMissEvent`.
10. AC-5/AC-6 use injected verifier + S4-05 event fields.
11. AC-8/AC-10 replace anonymous triples and non-existent `few_shot.content` assertions with `FencedRetrievalCandidate`.
12. AC-13/AC-14 pin event-sourced outcome dispatch and the internal event sequence.
13. Implementation outline and TDD snippet updated to the hardened contracts.
14. Files-to-touch route events through `plugins.events`; out-of-scope and notes name the required upstream amendments.

## Verdict rationale

**HARDENED.** The story's core goal remains valid, but the original draft depended on stale sibling-contract assumptions. The hardened version is executor-ready only after its named preconditions are cleared: S4-03 must expose raw scored candidates, and the S6-01/S2-04 prompt handoff must preserve the selected fenced RAG segment. No story-goal rewrite was needed, so this is not a RESCUE.

## Recommended next step

Before executing S5-01, amend S4-03's store read contract to expose raw scored candidates. When S6-01 is validated, reconcile the selected `FencedSegment` handoff into `PromptBuilder` so S5-01's retrieval-side fence is not dropped or double-fenced.
