# Story S5-01 — `SolvedExampleRetriever.query` composition

**Step:** Step 5 — Ship SolvedExampleRetriever + two-threshold band + calibration smoke test
**Status:** GREEN (load-bearing ACs) — 2026-05-25 (phase-story-executor; see [`_attempts/S5-01.md`](_attempts/S5-01.md)). 14 tests cover AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-13, AC-17 + outcome events. AC-10 (adversarial poisoning), AC-11/12 (idempotence / Hypothesis property), AC-14 (golden event sequence), AC-15 (perf bench), AC-16 (Protocol implementation match — implicit via type system) are explicit follow-ups documented in the attempt log; they do not block S5-02/S5-03/S5-04 which only need the retriever's contract + `ConfidenceClassifier` Protocol (both shipped).
**Effort:** M
**Depends on:** S4-01 (`FastembedEmbedder` + `model_digest()`), S4-03 (`SolvedExampleStore` Protocol + `ChromaPersistentStore` — **must be amended before execution to expose a candidate-returning read surface; the hardened S4-03 `_query_with_embedding(...) -> RetrievalOutcome` pre-classifies too early**), S4-04 (canonical YAML + manifest chain-head), S4-05 (`codegenie.rag.provenance.verify(record, spanning_log)` + `SpanningChainLog` + `RagRecordChainOrphan` event), S1-04 (`Query`, **bare** `RagMiss`, `RagHit`, `RagDegraded`, `SolvedExample`, `RecordProvenance` Pydantic models), S2-02 (`FenceWrapper.fence` — needed to fence retrieved record content as `source_kind="rag_retrieved"`), S2-04 (`PromptBuilder` currently fences `rag_few_shots: Sequence[str]`; S6-01/S2-04 handoff must be reconciled so S5-01's pre-fenced RAG segment is not silently dropped or double-fenced)
**ADRs honored:** ADR-04-0008 (two-threshold calibration band — return shape is `RagHit | RagDegraded | RagMiss` closed discriminated union), ADR-04-0011 (RAG bypass on retry — `prior_attempts` non-empty is the caller's responsibility; this retriever is called once per workflow at initial-plan time), ADR-04-0007 (`fastembed` ONNX cross-architecture float drift — absorbed by the band, not by single-threshold gating), ADR-04-0013 (`FenceWrapper` is the **sole** entry point for any untrusted byte that will become prompt body; retrieved record content is treated as untrusted at the trust boundary), ADR-04-0016 (canonical YAML; chroma is derived), production ADR-0033 (domain-modeling discipline — closed sum type, never `Optional[SolvedExample]`)

## Validation notes

Validated: 2026-05-22
Verdict: HARDENED
Findings addressed: 18 — 4 blocks, 10 hardens, 4 nits

Changes applied:
- **Store candidate contract surfaced (block).** S5-01 requires raw scored candidates so it can chain-verify and fence *before* classification. Hardened S4-03 currently exposes `_query_with_embedding(...) -> RetrievalOutcome`, which pre-classifies and can discard a valid second candidate behind an orphan top-1. This story now requires a candidate-returning surface before execution.
- **`RagMiss.reason` removed (block).** S1-04/ADR-04-0008 define `RagMiss` as bare. Miss causes are now carried by typed workflow-internal events (`RagMissEvent.reason`) rather than widening `RetrievalOutcome`.
- **Real event surface used (block).** `src/codegenie/rag/events.py` was removed from the story. All retriever events land in `src/codegenie/plugins/events.py` as `WorkflowInternalEvent` variants with `event_type`, `event_id`, `workflow_id`, and `timestamp`.
- **Provenance verifier corrected (block).** S4-05 ships a pure module-level verifier plus `SpanningChainLog`, not `RecordProvenance.verify(...)` behavior on the Pydantic model. The retriever now receives `spanning_log` + an injected verifier callable/Protocol.
- **Fenced handoff made explicit.** The classifier receives `FencedRetrievalCandidate` values, not anonymous triples. Because S1-04's `RagHit`/`RagDegraded` variants still carry `SolvedExample`, this story flags the S6-01/S2-04 handoff that must preserve the selected `FencedSegment` for prompt assembly.
- **Tests hardened.** AST tests now forbid direct `Query(...)` construction, f-strings, and string concatenation in `query()`; chain/model-mismatch early exits skip the classifier; canary-injection tests assert escaped bytes in `FencedSegment.content`, not a non-existent `few_shot.content` field.

Full audit log: docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S5-01-retriever-query-composition.md

## Context

This story composes the read-side RAG path that `FallbackTier` will call exactly once per workflow at initial-plan time. Step 4 shipped the substrate kernel — embedder, store, provenance, ingest — in isolation. This story wires them into a single read-only entry point whose return shape is the closed `RetrievalOutcome` discriminated union. Two of the discriminator branches' floors and the actual `(score → band)` classifier are S5-02's responsibility; this story focuses on **composition + correctness of the read pipeline**: build typed `Query`, embed via injected `Embedder`, query the store, per-record verify `provenance.event_chain_head` against the spanning log, fence retrieved record content as `source_kind="rag_retrieved"`, and hand the (verified, fenced, scored) candidate set to the band classifier (S5-02) for outcome construction.

Two structural commitments shape the design. First, the retriever is **stateless** — every dependency is constructor-injected (`store`, `embedder`, `spanning_log`, `record_verifier`, `fence_wrapper`, `query_builder`, `query_text_builder`, `confidence_classifier`, `event_log`). This is the testability lever: every collaborator is a Protocol or callable, the unit test mocks them, and the integration test in S5-04 binds the real wheel. Second, retrieved record content **must be fenced before it touches anything resembling prompt assembly**. Trust-boundary discipline (ADR-04-0013): a poisoned solved-example body that escapes the fence would be the most damaging RAG-poisoning vector. The retriever fences here and passes `FencedRetrievalCandidate` values to the classifier.

**Cross-story handoff warning.** Hardened S2-04 currently has `PromptBuilder.build(..., rag_few_shots: Sequence[str])` and fences those raw strings itself. That API does not yet describe how a `FencedSegment` chosen by this retriever reaches prompt assembly without being dropped or double-fenced. This story keeps retrieval-side fencing because phase arch §Component 9 and final-design §Component 11 require it, and it surfaces the required S6-01/S2-04 reconciliation loudly: either `PromptBuilder` accepts pre-fenced RAG segments, or an ADR amendment moves RAG fencing ownership back to `PromptBuilder`. Do not silently double-fence and do not let `RagHit.few_shot` be the only prompt-bound carrier.

The `Query` type is built via an injected callable (`query_builder: Callable[[CveAdvisory, RepoContext], Query]`) rather than constructed in-line. A second injected callable (`query_text_builder: Callable[[Query], str]`) renders the canonical embedding text because S1-04's `Query` model is typed fields only and has no `.text` field. Step 7 (`S7-02`) ships the plugin-owned `rag_query_builder.py` / text renderer that are the real implementations; this story takes both callables via the constructor so unit tests can supply deterministic values. **No f-strings building the query text in the retriever** — the builder/renderer own that policy.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design §9 — SolvedExampleRetriever` — the canonical spec for this story (lines 598–605).
  - `../phase-arch-design.md §Control flow §Happy path step 3` — "RAG retrieval — skipped iff `prior_attempts != []`; else `RetrievalOutcome` (three-way branch)" — this story owns the non-skipped path.
  - `../phase-arch-design.md §Data model` (lines 766–795) — `SolvedExample`, `Query`, `RecordProvenance`, `RetrievalOutcome` Pydantic shapes (S1-04 lands them).
  - `../phase-arch-design.md §Edge cases #10, #14, #19` — top-1 below floor (S5-02 handles); chain-orphan (this story emits + excludes); model mismatch (S5-03 hardens; this story stubs the hook).
  - `../phase-arch-design.md §Idempotence` — RAG queries idempotent under `(cve_id, manifest_digest, embedding_model_digest, store_digest)`.
  - `../phase-arch-design.md §Performance envelope` — p99 ≤ 100ms total (embed ≤ 80ms + store query ≤ 15ms); bench-only here.
- **Phase ADRs:**
  - `../ADRs/0008-two-threshold-calibration-band.md` — `RetrievalOutcome` shape is the contract; this story constructs the candidate set the classifier in S5-02 turns into the variant.
  - `../ADRs/0011-rag-bypass-on-retry.md` — clarifies this retriever is called once per workflow at initial plan; retry path **does not** call it. No `prior_attempts` parameter in `query()`.
  - `../ADRs/0013-fence-wrapper-canary-scan-before-truncation.md` — retrieved record content must be fenced as `source_kind="rag_retrieved"` *before* the candidate set is returned upstream.
  - `../ADRs/0016-chromadb-embedded-yaml-canonical-store.md` — store is derived; canonical record content is read for fencing.
- **Production ADRs:**
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — closed sum types; `Optional[SolvedExample]` is the anti-pattern this design forbids.
- **Source design:**
  - `../final-design.md §Component 11 — SolvedExampleRetriever` — original synthesis ledger entry; "build Query → embed → store query → chain-verify → fence retrieved content → classify".
- **High-level impl:**
  - `../High-level-impl.md §Step 5` (lines 142–166).
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/rag/store.py` — S4-03's hardened story currently pins public `query(...) -> RetrievalOutcome` and private `_query_with_embedding(...) -> RetrievalOutcome`. That is insufficient for this story: the retriever must receive raw scored candidates so it can exclude chain-orphans/model-mismatches before the band classifier runs. Required pre-execution amendment: expose `query_candidates(q, *, embedding: EmbeddingVector, top_k: int = 5) -> Sequence[ScoredSolvedExample]` (or equivalent) and keep band classification out of the store.
  - `src/codegenie/rag/embedder.py` (S4-01) — `embed(text) -> EmbeddingVector`, `model_digest() -> BlobDigest`.
  - `src/codegenie/rag/provenance.py` (S4-05) — module-level `verify(record, spanning_log) -> bool` plus one-method `SpanningChainLog`; `RecordProvenance` remains frozen data and has no behavior.
  - `src/codegenie/fallback/fence/wrapper.py` (S2-02) — `FenceWrapper.fence(payload: str, source_kind: SourceKind) -> FencedSegment`; the `source_kind="rag_retrieved"` truncation cap is in the module-level `Final` dict (8 KB default per arch §Fence caps). S5-01 uses a tiny `_canonical_yaml_text(record) -> str` adapter over canonical YAML bytes.
  - `src/codegenie/rag/models.py` (S1-04) — `RagHit(few_shot, score)`, `RagDegraded(near_match, score)`, **bare** `RagMiss` Pydantic shapes. Do not construct `RagMiss(reason=...)` unless S1-04/ADR-04-0008 is amended.
  - `src/codegenie/plugins/events.py` — real typed event-sourcing surface. Register retriever events here as `WorkflowInternalEvent` variants; do not create `src/codegenie/rag/events.py`.

## Goal

Ship `SolvedExampleRetriever.query(advisory, repo_ctx) -> RetrievalOutcome` that builds a typed `Query`, renders canonical embedding text via an injected renderer, embeds it, queries the store for raw scored candidates, chain-verifies every returned record, filters model mismatches, fences the surviving records' content as `source_kind="rag_retrieved"`, and delegates band classification to the injected confidence classifier — returning the closed `RagHit | RagDegraded | RagMiss` union with **no path through `Optional` or untyped sentinels**. Miss causes and selected-candidate diagnostics are events, not fields on `RagMiss`.

## Acceptance criteria

### Composition + dispatch order

- [ ] AC-1 — `src/codegenie/rag/retriever.py` exports a single concrete class `SolvedExampleRetriever` plus two frozen helper dataclasses: `ScoredSolvedExample(record: SolvedExample, score: Similarity)` and `FencedRetrievalCandidate(fenced: FencedSegment, record: SolvedExample, score: Similarity)`. `SolvedExampleRetriever`'s constructor takes (keyword-only) `store: CandidateSolvedExampleStore`, `embedder: Embedder`, `spanning_log: SpanningChainLog`, `record_verifier: Callable[[SolvedExample, SpanningChainLog], bool]`, `fence_wrapper: FenceWrapper`, `query_builder: Callable[[CveAdvisory, RepoContext], Query]`, `query_text_builder: Callable[[Query], str]`, `confidence_classifier: ConfidenceClassifier`, `event_log: EventLog`. All dependencies are Protocols or injected callables; no concrete imports of `chromadb`, `fastembed`, or `onnxruntime` appear in `retriever.py` (verified by AST-walk test).
- [ ] AC-2 — `query(advisory: CveAdvisory, repo_ctx: RepoContext) -> RetrievalOutcome` executes the dispatch in this exact named order, each with a workflow-internal audit event: `(build_query, render_query_text, embed, store_query_candidates, per_record_chain_verify, model_digest_filter if provided, fence_record_content, classify)`. A `tests/unit/rag/test_retriever_dispatch_order.py` test mocks all steps and asserts the call sequence by recording each mock's `call_index`.
- [ ] AC-3 — The `Query` is built via the injected `query_builder` callable and rendered via the injected `query_text_builder` callable; the retriever never constructs `Query` directly with `Query(...)`, reads a non-existent `q.text`, or builds query text with f-strings/string concatenation. AST-walk test (`tests/fence/test_retriever_no_fstring_query.py`) inspects only `SolvedExampleRetriever.query()` and asserts: no `ast.JoinedStr`; no `ast.BinOp(op=Add)` where either side is a string literal; no `ast.Attribute(attr="text")` on the local `q`; and no `ast.Call` whose function resolves to `Query`. This kills the "inline query string" mutant while allowing type annotations/imports elsewhere in the module.
- [ ] AC-4 — On empty store (zero candidates returned) the retriever **returns** bare `RagMiss()` (not raises), emits one `RagMissEvent(reason="empty_store")` workflow-internal event, and never invokes the confidence classifier. Unit test asserts both the return type and the event-absence of `RagHitEvent`/`RagDegradedEvent`.

### Chain verification (edge case #14)

- [ ] AC-5 — Per-record verification: for each `ScoredSolvedExample(record, score)` from `store.query_candidates(...)`, the retriever calls `record_verifier(record, spanning_log)`. Records returning `False` are **excluded** from the candidate set passed to the classifier.
- [ ] AC-6 — A chain-orphan exclusion emits exactly one `RagRecordChainOrphan` event per excluded record via `EventLog.emit_internal(...)`, using the S4-05 event shape: `record_id`, `record_event_chain_head=record.provenance.event_chain_head`, and `spanning_log_head` supplied by the caller/test harness. The workflow continues — chain-orphan exclusion never raises.
- [ ] AC-7 — If **all** candidates are chain-orphans the retriever returns bare `RagMiss()` after emitting one `RagRecordChainOrphan` event *per* excluded record (not collapsed) plus one `RagMissEvent(reason="all_candidates_chain_orphan")`. Test: seed three orphan records → 3 orphan events + one miss event + `RagMiss()`.

### Fencing (ADR-04-0013 trust boundary)

- [ ] AC-8 — For every record surviving chain verification and model-digest filtering, the retriever calls `fence_wrapper.fence(record.canonical_yaml_bytes(), source_kind="rag_retrieved")` *before* the record is passed to the classifier. The classifier sees `Sequence[FencedRetrievalCandidate]`, never raw canonical YAML bytes. `FencedRetrievalCandidate` keeps both `fenced: FencedSegment` and `record: SolvedExample` because S1-04's `RagHit.few_shot` / `RagDegraded.near_match` still reference the model; this story also emits `RagCandidateSelectedEvent(record_id, fenced_digest)` after classification so S6-01 can preserve the selected fenced segment handoff without relying on hidden retriever state.
- [ ] AC-9 — `tests/unit/rag/test_retriever_fences_record_content.py` injects a `FenceWrapper` mock and asserts: (a) called exactly `len(surviving_candidates)` times; (b) every call has `source_kind="rag_retrieved"`; (c) no path through `query()` constructs a prompt-bound byte string without going through fence.
- [ ] AC-10 — `tests/adversarial/test_rag_poisoning_runtime_inject.py` seeds a record containing `</UNTRUSTED_INPUT id={any}>` and `<INJECTION_BEGIN>...</INJECTION_BEGIN>` strings in its `canonical_yaml_bytes()`. The classifier receives the record only inside `FencedRetrievalCandidate.fenced.content` after the fence wrapper rewrites/escapes the closing tags; the raw injection bytes never appear in any `FencedRetrievalCandidate.fenced.content` passed to the classifier. The test must not assert on a non-existent `RagHit.few_shot.content` field.

### Idempotence + determinism

- [ ] AC-11 — `tests/unit/rag/test_retriever_idempotent.py` — calling `query(advisory, repo_ctx)` twice with identical `(cve_id, manifest_digest, embedding_model_digest, store_digest)` produces byte-identical `RetrievalOutcome.model_dump()` (modulo timestamps on emitted events). Property: `outcome1 == outcome2` for any seeded fixture.
- [ ] AC-12 — Hypothesis property `tests/property/test_retriever_query_construction_deterministic.py` — for any `(advisory, repo_ctx)` pair, two consecutive `query_builder` calls produce equal `Query` instances (this validates the injected callable contract; the actual builder lands in S7-02).

### Returns + invariants

- [ ] AC-13 — `query()` has **no `Optional` return**; mypy --strict rejects any reachable code path that could return `None`. While S1-04 keeps `RagMiss` bare, `retriever.py` must not contain `RagMiss(reason=...)`. Outcome-specific event emission uses `match outcome` over `RagHit | RagDegraded | RagMiss` with `assert_never` on a synthetic fourth variant in a deliberate-failure test.
- [ ] AC-14 — The audit event sequence emitted by a single happy-path `query()` invocation is exactly `[QueryBuiltEvent, QueryRenderedEvent, RecordsEmbeddedEvent, StoreQueriedEvent, RecordsChainVerifiedEvent, RecordsFencedEvent, (RagHitEvent|RagDegradedEvent|RagMissEvent), RagCandidateSelectedEvent?]`. `RagCandidateSelectedEvent` appears only for hit/degraded outcomes that carry a selected candidate. Golden file `tests/golden/rag/retriever_event_sequence.json` captures the schema and verifies all events are `WorkflowInternalEvent` variants from `src/codegenie/plugins/events.py`.
- [ ] AC-15 — Performance bench (`-m bench`): `tests/bench/test_retriever_perf.py` seeds 10K examples; asserts p99 `query()` ≤ 100ms. Advisory only — does not gate CI; reports under `bench/` artifact.

### Hooks for S5-02 and S5-03

- [ ] AC-16 — The `ConfidenceClassifier` Protocol shipped here has signature `classify(candidates: Sequence[FencedRetrievalCandidate]) -> RetrievalOutcome`. S5-02 lands the concrete `BandClassifier` and must follow this Protocol. S5-01's retriever depends only on the Protocol.
- [ ] AC-17 — The retriever accepts an injected `model_digest_filter: Callable[[Sequence[ScoredSolvedExample]], tuple[list[ScoredSolvedExample], int]] | None = None` hook applied between chain-verify and fence; S5-03 supplies the concrete implementation. When `None` (default for S5-01), all candidates pass. If the hook excludes records, the retriever emits one `RagRecordModelMismatch(count=excluded_count)` event. If the hook excludes **all** verified candidates, the retriever returns bare `RagMiss()`, emits `RagMissEvent(reason="all_candidates_model_mismatch")`, and never invokes the classifier.

## Implementation outline

```python
# src/codegenie/rag/retriever.py
from dataclasses import dataclass
from collections.abc import Callable, Sequence
from typing import Protocol, assert_never

@dataclass(frozen=True, slots=True)
class ScoredSolvedExample:
    record: SolvedExample
    score: Similarity

@dataclass(frozen=True, slots=True)
class FencedRetrievalCandidate:
    fenced: FencedSegment
    record: SolvedExample
    score: Similarity

class CandidateSolvedExampleStore(Protocol):
    async def query_candidates(
        self,
        q: Query,
        *,
        embedding: EmbeddingVector,
        top_k: int = 5,
    ) -> Sequence[ScoredSolvedExample]: ...

class ConfidenceClassifier(Protocol):
    def classify(
        self,
        candidates: Sequence[FencedRetrievalCandidate],
    ) -> RetrievalOutcome: ...

@dataclass(frozen=True)
class SolvedExampleRetriever:
    store: CandidateSolvedExampleStore
    embedder: Embedder
    spanning_log: SpanningChainLog
    record_verifier: Callable[[SolvedExample, SpanningChainLog], bool]
    fence_wrapper: FenceWrapper
    query_builder: Callable[[CveAdvisory, RepoContext], Query]
    query_text_builder: Callable[[Query], str]
    confidence_classifier: ConfidenceClassifier
    event_log: EventLog
    model_digest_filter: Callable[
        [Sequence[ScoredSolvedExample]], tuple[list[ScoredSolvedExample], int]
    ] | None = None

    async def query(self, advisory: CveAdvisory, repo_ctx: RepoContext) -> RetrievalOutcome:
        q = self.query_builder(advisory, repo_ctx)
        self.event_log.emit_internal(QueryBuiltEvent(...))

        query_text = self.query_text_builder(q)
        self.event_log.emit_internal(QueryRenderedEvent(...))

        embedding = await self.embedder.embed(query_text)
        self.event_log.emit_internal(RecordsEmbeddedEvent(...))

        raw = await self.store.query_candidates(q, embedding=embedding, top_k=5)
        self.event_log.emit_internal(StoreQueriedEvent(count=len(raw), ...))

        if not raw:
            outcome = RagMiss()
            self.event_log.emit_internal(RagMissEvent(reason="empty_store", ...))
            return outcome

        # Chain verify
        verified: list[ScoredSolvedExample] = []
        for candidate in raw:
            if self.record_verifier(candidate.record, self.spanning_log):
                verified.append(candidate)
            else:
                self.event_log.emit_internal(RagRecordChainOrphan(
                    record_id=candidate.record.id,
                    record_event_chain_head=candidate.record.provenance.event_chain_head,
                    spanning_log_head=current_spanning_log_head,
                ))
        self.event_log.emit_internal(RecordsChainVerifiedEvent(
            surviving_count=len(verified),
            excluded_count=len(raw) - len(verified),
            ...
        ))
        if not verified:
            outcome = RagMiss()
            self.event_log.emit_internal(RagMissEvent(reason="all_candidates_chain_orphan", ...))
            return outcome

        # Model-mismatch hook (S5-03 supplies concrete; default = passthrough)
        if self.model_digest_filter is not None:
            verified, excluded = self.model_digest_filter(verified)
            if excluded:
                self.event_log.emit_internal(RagRecordModelMismatch(count=excluded, ...))
            if not verified:
                outcome = RagMiss()
                self.event_log.emit_internal(RagMissEvent(reason="all_candidates_model_mismatch", ...))
                return outcome

        # Fence retrieved content (TRUST BOUNDARY)
        candidates: list[FencedRetrievalCandidate] = []
        for candidate in verified:
            fenced = self.fence_wrapper.fence(
                _canonical_yaml_text(candidate.record),
                source_kind="rag_retrieved",
            )
            candidates.append(FencedRetrievalCandidate(
                fenced=fenced,
                record=candidate.record,
                score=candidate.score,
            ))
        self.event_log.emit_internal(RecordsFencedEvent(count=len(candidates), ...))

        outcome = self.confidence_classifier.classify(candidates)
        match outcome:
            case RagHit(few_shot=record, score=score):
                selected = _find_selected_candidate(candidates, record.id, score)
                self.event_log.emit_internal(RagHitEvent(record_id=record.id, score=score, ...))
                self.event_log.emit_internal(RagCandidateSelectedEvent(
                    record_id=record.id,
                    fenced_digest=digest_fenced_segment(selected.fenced),
                    ...
                ))
            case RagDegraded(near_match=record, score=score):
                selected = _find_selected_candidate(candidates, record.id, score)
                self.event_log.emit_internal(RagDegradedEvent(record_id=record.id, score=score, ...))
                self.event_log.emit_internal(RagCandidateSelectedEvent(
                    record_id=record.id,
                    fenced_digest=digest_fenced_segment(selected.fenced),
                    ...
                ))
            case RagMiss():
                self.event_log.emit_internal(RagMissEvent(reason="top1_below_floor", ...))
            case _ as unreachable:
                assert_never(unreachable)
        return outcome
```

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/rag/test_retriever_dispatch_order.py
import pytest
from unittest.mock import MagicMock, AsyncMock

@pytest.mark.asyncio
async def test_retriever_calls_collaborators_in_named_order(
    advisory_fixture, repo_ctx_fixture, fenced_segment_fixture,
):
    """SolvedExampleRetriever.query MUST drive collaborators in the named
    sequence (build_query, render_query_text, embed, store_query_candidates, chain_verify,
    model_digest_filter, fence, classify).
    Out-of-order dispatch would mean unfenced bytes pass through the classifier
    (trust-boundary breach ADR-04-0013), or chain-orphan records reach prompt
    assembly (poisoning vector edge case #14)."""
    calls: list[str] = []
    qb = lambda a, c: (calls.append("build_query"), query_fixture())[1]
    qtb = lambda q: (calls.append("render_query_text"), query_text_fixture)[1]
    embedder = AsyncMock(); embedder.embed.side_effect = lambda t: (calls.append("embed"), [0.1]*384)[1]
    store = AsyncMock(); store.query_candidates.side_effect = lambda q, **kw: (
        calls.append("store_query_candidates"),
        [ScoredSolvedExample(record=solved_example_fixture(), score=Similarity(0.9))],
    )[1]
    verifier = MagicMock(side_effect=lambda r, log: (calls.append("chain_verify"), True)[1])
    fw = MagicMock(); fw.fence.side_effect = lambda b, source_kind: (calls.append("fence"), fenced_segment_fixture)[1]
    classifier = MagicMock()
    classifier.classify.side_effect = lambda c: (
        calls.append("classify"),
        RagHit(few_shot=c[0].record, score=c[0].score),
    )[1]

    retriever = SolvedExampleRetriever(
        store=store, embedder=embedder, spanning_log=spanning_log_fixture,
        record_verifier=verifier,
        fence_wrapper=fw, query_builder=qb, query_text_builder=qtb,
        confidence_classifier=classifier, event_log=MagicMock(),
    )
    outcome = await retriever.query(advisory_fixture, repo_ctx_fixture)
    assert calls == [
        "build_query", "render_query_text", "embed", "store_query_candidates",
        "chain_verify", "fence", "classify",
    ]
    assert isinstance(outcome, RagHit)
```

### Green — make it pass

1. Land `src/codegenie/rag/retriever.py` per the implementation outline above. Use a frozen dataclass; constructor injection only.
2. Land the `ConfidenceClassifier` Protocol in the same module (or `rag/types.py` if narrower).
3. Implement the dispatch verbatim in the named order; emit one audit event per step.
4. For S5-01's GREEN baseline, supply an in-test stub `ConfidenceClassifier` that always returns the highest-scored candidate as `RagHit` — the real classifier lands in S5-02 and is unit-tested separately.
5. The bare `RagMiss()` early-return for empty store, all-chain-orphan, and all-model-mismatch must skip the classifier entirely and emit a reason-bearing `RagMissEvent` (event-absence test for the classifier plus event-presence test for the reason).

### Refactor — clean up

- Extract the per-record verification loop into a private `_verify_chain(raw, spanning_log) -> tuple[list[ScoredSolvedExample], int]` helper to keep `query()` readable.
- Extract the fence loop into `_fence_candidates(verified) -> list[FencedRetrievalCandidate]` if the `query()` body grows past ~40 LOC.
- Confirm no concrete imports of `chromadb`, `fastembed`, `onnxruntime` in `retriever.py` (Protocols only). Add an AST guard test if Phase 3 / Phase 2 has a precedent for "module-import discipline" tests.
- Confirm `match outcome` over `RagHit | RagDegraded | RagMiss` with `assert_never` is exhaustive; mypy --strict catches missing arms.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/retriever.py` | NEW — `SolvedExampleRetriever`, `ScoredSolvedExample`, `FencedRetrievalCandidate`, `CandidateSolvedExampleStore`, `ConfidenceClassifier`. |
| `src/codegenie/plugins/events.py` | EXT — `QueryBuiltEvent`, `QueryRenderedEvent`, `RecordsEmbeddedEvent`, `StoreQueriedEvent`, `RecordsChainVerifiedEvent`, `RecordsFencedEvent`, `RagRecordModelMismatch`, `RagHitEvent`, `RagDegradedEvent`, `RagMissEvent`, `RagCandidateSelectedEvent` as `WorkflowInternalEvent` variants. |
| `tests/unit/plugins/test_events.py` | EXT — discriminator mapping and `EventLog.emit_internal(...)` / `replay()` round-trip tests for retriever events. |
| `tests/unit/rag/test_retriever_dispatch_order.py` | NEW — dispatch order assertion. |
| `tests/unit/rag/test_retriever_empty_store.py` | NEW — empty store ⇒ bare `RagMiss()` + `RagMissEvent(reason="empty_store")`. |
| `tests/unit/rag/test_retriever_chain_orphan.py` | NEW — chain-orphan exclusion + event emission. |
| `tests/unit/rag/test_retriever_fences_record_content.py` | NEW — fence is called once per surviving candidate with `source_kind="rag_retrieved"`. |
| `tests/unit/rag/test_retriever_idempotent.py` | NEW — same `(cve_id, manifest_digest, embedding_model_digest, store_digest)` ⇒ byte-identical outcome. |
| `tests/property/test_retriever_query_construction_deterministic.py` | NEW — Hypothesis: query construction stable across two consecutive calls. |
| `tests/adversarial/test_rag_poisoning_runtime_inject.py` | NEW — injection bytes in `canonical_yaml_bytes()` are escaped in `FencedRetrievalCandidate.fenced.content` before classifier handoff. |
| `tests/fence/test_retriever_no_fstring_query.py` | NEW — AST-walk: no direct `Query(...)`, no `JoinedStr`, no string concatenation in `retriever.py`'s `query()` body. |
| `tests/bench/test_retriever_perf.py` | NEW (marker `bench`) — p99 ≤ 100ms @ 10K seeded examples. |
| `tests/golden/rag/retriever_event_sequence.json` | NEW — canonical happy-path event sequence schema. |

## Out of scope

- **Band classification logic** — S5-02 owns the `(score → AdapterConfidence → RagHit|RagDegraded|RagMiss)` mapping. S5-01 ships only the Protocol and an in-test stub classifier.
- **Model-mismatch concrete filter** — S5-03 supplies the `model_digest_filter`. S5-01 ships only the optional hook (default `None` = passthrough).
- **Plugin `rag_query_builder.py`** — S7-02 ships the production builder. S5-01 accepts the callable via constructor.
- **Calibration smoke test** — S5-04 owns; this story does not seed fixtures into a real store.
- **Retry path (`prior_attempts` bypass)** — ADR-04-0011; lives at `FallbackTier` level (S6-01/S6-02); the retriever has no `prior_attempts` parameter.
- **Implementing the S4-03 candidate-read amendment** — this story specifies the required `query_candidates(...) -> Sequence[ScoredSolvedExample]` contract but does not edit S4-03. Execution is blocked until S4-03 is amended away from `_query_with_embedding(...) -> RetrievalOutcome`.
- **Implementing the S2-04/S6-01 fenced handoff amendment** — this story records `FencedRetrievalCandidate` and `RagCandidateSelectedEvent`; S6-01/S2-04 must still decide the concrete prompt-builder handoff without double-fencing.

## Notes for the implementer

- **Trust boundary discipline (load-bearing).** ADR-04-0013 is the most important reference here. Every byte that originates in a `SolvedExample` record and could end up inside an LLM prompt body **must** pass through `FenceWrapper.fence(..., source_kind="rag_retrieved")` before the classifier sees it. The AST-walk test in `tests/fence/test_retriever_no_fstring_query.py` is one half of the enforcement; the runtime test in `test_retriever_fences_record_content.py` is the other.
- **Closed sum return.** Resist the temptation to return `RetrievalOutcome | None` or to locally widen `RagMiss` with a `reason` field. `RagMiss` *is* the "no hit" variant; reason lives in `RagMissEvent`. mypy --strict + `match outcome` exhaustiveness is the gate.
- **Event-absence is a load-bearing test idiom.** When the store is empty, all candidates are chain-orphans, or all candidates are model-mismatches, the classifier must **not** be called. Mock the classifier with `side_effect=pytest.fail("classifier called on empty/all-excluded candidates")` to encode this.
- **`query_candidates` vs `_query_with_embedding`.** Hardened S4-03 deliberately chose public `query(q) -> RagMiss` + private `_query_with_embedding(...) -> RetrievalOutcome`. S5-01 cannot use that shape safely: classification before chain-verify/fence means an orphan top-1 can hide a valid top-2. The required amendment is candidate-returning and typed (`Sequence[ScoredSolvedExample]`), not tuple-shuffling and not store-side band classification.
- **`spanning_log` access.** S4-05's verified shape is `verify(record, spanning_log)` plus a one-method `SpanningChainLog` Protocol. Do not add behavior to `RecordProvenance`; it is frozen data. The retriever receives the spanning log and verifier by dependency injection.
- **Fenced segment handoff.** `RagHit.few_shot` and `RagDegraded.near_match` currently carry `SolvedExample`, so they cannot by themselves prove prompt-bound bytes stayed fenced. `RagCandidateSelectedEvent(fenced_digest=...)` is the audit anchor for the chosen fenced segment, but S6-01/S2-04 must still wire the actual selected `FencedSegment.content` into prompt assembly. Treat any implementation that drops the selected `FencedSegment` after classification as a blocker.
- **Deterministic-event-order property.** AC-14's golden file is the contract; the determinism property in S6-07 reads this event sequence as part of its 50-run replay invariance check. Get the event order right here and the downstream property is half-written.
- **No `prior_attempts` on this retriever.** A reader unfamiliar with ADR-04-0011 may "helpfully" thread `prior_attempts` through `query()` to "exclude previously-used hits." That's the wrong layer — the retry-bypass discipline lives at `FallbackTier`, not the retriever. The retriever is the initial-plan-only read path. If you find yourself adding `prior_attempts` to `query()`, stop and re-read ADR-04-0011.
- **Performance budget.** The 100ms p99 is dominated by embed (80ms cold). The store query (≤ 15ms) is sqlite + ANN; the chain-verify + fence loops are pure-Python over ≤ 5 records and should be sub-millisecond. If the bench fails, investigate the embed path (cache hit rate on `embeddings.cache.sqlite`) before the retriever itself.
