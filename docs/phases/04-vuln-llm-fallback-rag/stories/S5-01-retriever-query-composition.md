# Story S5-01 — `SolvedExampleRetriever.query` composition

**Step:** Step 5 — Ship SolvedExampleRetriever + two-threshold band + calibration smoke test
**Status:** Ready
**Effort:** M
**Depends on:** S4-01 (`FastembedEmbedder` + `model_digest()`), S4-03 (`SolvedExampleStore` Protocol + `ChromaPersistentStore`), S4-04 (canonical YAML + manifest chain-head), S4-05 (`RecordProvenance.verify`), S1-04 (`Query`, `RetrievalOutcome`, `SolvedExample`, `RecordProvenance` Pydantic models), S2-02 (`FenceWrapper.fence` — needed to fence retrieved record content as `source_kind="rag_retrieved"`)
**ADRs honored:** ADR-04-0008 (two-threshold calibration band — return shape is `RagHit | RagDegraded | RagMiss` closed discriminated union), ADR-04-0011 (RAG bypass on retry — `prior_attempts` non-empty is the caller's responsibility; this retriever is called once per workflow at initial-plan time), ADR-04-0007 (`fastembed` ONNX cross-architecture float drift — absorbed by the band, not by single-threshold gating), ADR-04-0013 (`FenceWrapper` is the **sole** entry point for any untrusted byte that will become prompt body; retrieved record content is treated as untrusted at the trust boundary), ADR-04-0016 (canonical YAML; chroma is derived), production ADR-0033 (domain-modeling discipline — closed sum type, never `Optional[SolvedExample]`)

## Context

This story composes the read-side RAG path that `FallbackTier` will call exactly once per workflow at initial-plan time. Step 4 shipped the substrate kernel — embedder, store, provenance, ingest — in isolation. This story wires them into a single read-only entry point whose return shape is the closed `RetrievalOutcome` discriminated union. Two of the discriminator branches' floors and the actual `(score → band)` classifier are S5-02's responsibility; this story focuses on **composition + correctness of the read pipeline**: build typed `Query`, embed via injected `Embedder`, query the store, per-record verify `provenance.event_chain_head` against the spanning log, fence retrieved record content as `source_kind="rag_retrieved"`, and hand the (verified, fenced, scored) candidate set to the band classifier (S5-02) for outcome construction.

Two structural commitments shape the design. First, the retriever is **stateless** — every dependency is constructor-injected (`store`, `embedder`, `record_provenance`, `fence_wrapper`, `query_builder`, `confidence_classifier`, `event_log`). This is the testability lever: every collaborator is a Protocol, the unit test mocks them, and the integration test in S5-04 binds the real wheel. Second, retrieved record content **must be fenced before it touches anything resembling prompt assembly**. Trust-boundary discipline (ADR-04-0013): a poisoned `SolvedExample.diff` body that escapes the fence would be the most damaging RAG-poisoning vector. The retriever fences here, and `PromptBuilder` (S2-04) only ever receives already-fenced bytes from the retriever. That's the property `test_retriever_fences_record_content` asserts.

The `Query` type is built via an injected callable (`query_builder: Callable[[CveAdvisory, RepoContext], Query]`) rather than constructed in-line. Step 7 (`S7-02`) ships the plugin-owned `rag_query_builder.py` that is the real implementation; this story takes the callable via the constructor so the unit tests can supply a deterministic `Query` and the integration tests can bind the plugin builder. **No f-strings building the query text** — the builder constructs the typed `Query` model directly.

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
  - `src/codegenie/rag/store.py` — Step 4 lands the Protocol with `query(q: Query, *, top_k: int = 5, similarity_floor: float | None = None) -> RetrievalOutcome` *signature*; this story discovers the Step-4 implementation returns a candidate list, not a final outcome, OR returns a list of `(SolvedExample, Similarity)` tuples for the retriever to classify. Surface the conflict per Global Rule 7 if Step-4's `store.query` already classifies; the cleaner split is store-returns-candidates / retriever-classifies.
  - `src/codegenie/rag/embedder.py` (S4-01) — `embed(text) -> EmbeddingVector`, `model_digest() -> BlobDigest`.
  - `src/codegenie/rag/provenance.py` (S4-05) — `RecordProvenance.verify(record, spanning_log) -> bool`.
  - `src/codegenie/fallback/fence/wrapper.py` (S2-02) — `FenceWrapper.fence(payload: bytes, source_kind: str) -> FencedSegment`; the `source_kind="rag_retrieved"` truncation cap is in the module-level `Final` dict (8 KB default per arch §Fence caps).
  - `src/codegenie/rag/models.py` (S1-04) — `RagHit(few_shot, score)`, `RagDegraded(near_match, score)`, `RagMiss` Pydantic shapes.

## Goal

Ship `SolvedExampleRetriever.query(advisory, repo_ctx) -> RetrievalOutcome` that builds a typed `Query`, embeds it, queries the store, chain-verifies every returned record, fences the surviving records' content as `source_kind="rag_retrieved"`, and delegates band classification to the injected confidence classifier — returning the closed `RagHit | RagDegraded | RagMiss` union with **no path through `Optional` or untyped sentinels**.

## Acceptance criteria

### Composition + dispatch order

- [ ] AC-1 — `src/codegenie/rag/retriever.py` exports a single concrete class `SolvedExampleRetriever` whose constructor takes (keyword-only) `store: SolvedExampleStore`, `embedder: Embedder`, `record_provenance: RecordProvenance`, `fence_wrapper: FenceWrapper`, `query_builder: Callable[[CveAdvisory, RepoContext], Query]`, `confidence_classifier: ConfidenceClassifier`, `event_log: EventLog`. All dependencies are Protocols; no concrete imports of `chromadb`, `fastembed`, or `onnxruntime` appear in `retriever.py` (verified by AST-walk test).
- [ ] AC-2 — `query(advisory: CveAdvisory, repo_ctx: RepoContext) -> RetrievalOutcome` executes the dispatch in this exact named order, each with an audit event: `(build_query, embed, store_query, per_record_chain_verify, fence_record_content, classify)`. A `tests/unit/rag/test_retriever_dispatch_order.py` test mocks all six collaborators and asserts the call sequence by recording each mock's `call_index`.
- [ ] AC-3 — The `Query` is built via the injected `query_builder` callable; the retriever never constructs `Query` with f-strings or string concatenation. AST-walk test (`tests/fence/test_retriever_no_fstring_query.py`) asserts no `JoinedStr` node appears anywhere in `retriever.py`'s `query()` method body.
- [ ] AC-4 — On empty store (zero candidates returned) the retriever **returns** `RagMiss` (not raises), emits one `RagMiss(reason="empty_store")` event, and never invokes the confidence classifier. Unit test asserts both the return type and the event-absence of `RagHit`/`RagDegraded`.

### Chain verification (edge case #14)

- [ ] AC-5 — Per-record verification: for each candidate `(record, score)` from `store.query(...)`, the retriever calls `record_provenance.verify(record, spanning_log)`. Records returning `False` are **excluded** from the candidate set passed to the classifier.
- [ ] AC-6 — A chain-orphan exclusion emits exactly one `RagRecordChainOrphan(record_id, chain_head, expected_chain_head)` event per excluded record, with the offending record's `event_chain_head` and the current spanning log's head in `details`. The workflow continues — chain-orphan exclusion never raises.
- [ ] AC-7 — If **all** candidates are chain-orphans the retriever returns `RagMiss(reason="all_candidates_chain_orphan")` after emitting one `RagRecordChainOrphan` event *per* excluded record (not collapsed). Test: seed three orphan records → 3 events + `RagMiss`.

### Fencing (ADR-04-0013 trust boundary)

- [ ] AC-8 — For every record surviving chain verification, the retriever calls `fence_wrapper.fence(record.canonical_yaml_bytes, source_kind="rag_retrieved")` *before* the record is passed to the classifier. The classifier sees `(FencedSegment, Similarity)`, never raw `SolvedExample` bytes. The closed shape passed to the classifier is `list[tuple[FencedSegment, SolvedExample, Similarity]]` — the unfenced model is kept alongside the fenced bytes so `RagHit.few_shot` / `RagDegraded.near_match` can reference the model, but the *content that flows to prompt assembly* is always the `FencedSegment`.
- [ ] AC-9 — `tests/unit/rag/test_retriever_fences_record_content.py` injects a `FenceWrapper` mock and asserts: (a) called exactly `len(surviving_candidates)` times; (b) every call has `source_kind="rag_retrieved"`; (c) no path through `query()` constructs a prompt-bound byte string without going through fence.
- [ ] AC-10 — `tests/adversarial/test_rag_poisoning_runtime_inject.py` seeds a record containing `</UNTRUSTED_INPUT id={any}>` and `<INJECTION_BEGIN>...</INJECTION_BEGIN>` strings in its `canonical_yaml_bytes`; the retriever returns the record only via `FencedSegment.content` (the fence wrapper rewrites/escapes the closing tags) — the raw injection bytes never appear inside any `RagHit.few_shot.content` field that goes to prompt assembly.

### Idempotence + determinism

- [ ] AC-11 — `tests/unit/rag/test_retriever_idempotent.py` — calling `query(advisory, repo_ctx)` twice with identical `(cve_id, manifest_digest, embedding_model_digest, store_digest)` produces byte-identical `RetrievalOutcome.model_dump()` (modulo timestamps on emitted events). Property: `outcome1 == outcome2` for any seeded fixture.
- [ ] AC-12 — Hypothesis property `tests/property/test_retriever_query_construction_deterministic.py` — for any `(advisory, repo_ctx)` pair, two consecutive `query_builder` calls produce equal `Query` instances (this validates the injected callable contract; the actual builder lands in S7-02).

### Returns + invariants

- [ ] AC-13 — `query()` has **no `Optional` return**; mypy --strict rejects any reachable code path that could return `None`. The body is exclusively `match outcome` over `RagHit | RagDegraded | RagMiss` (assert_never on synthetic fourth variant in a deliberate-failure test).
- [ ] AC-14 — The audit event sequence emitted by a single happy-path `query()` invocation is exactly `[QueryBuilt, RecordsEmbedded, StoreQueried, (RecordsChainVerified | RagRecordChainOrphan*), RecordsFenced, (RagHit|RagDegraded|RagMiss)]`. Golden file `tests/golden/rag/retriever_event_sequence.json` captures the schema.
- [ ] AC-15 — Performance bench (`-m bench`): `tests/bench/test_retriever_perf.py` seeds 10K examples; asserts p99 `query()` ≤ 100ms. Advisory only — does not gate CI; reports under `bench/` artifact.

### Hooks for S5-02 and S5-03

- [ ] AC-16 — The `ConfidenceClassifier` Protocol shipped here has signature `classify(candidates: list[tuple[FencedSegment, SolvedExample, Similarity]]) -> RetrievalOutcome`. S5-02 lands the concrete `BandClassifier`. S5-01's retriever depends only on the Protocol.
- [ ] AC-17 — The retriever accepts an injected `model_digest_filter: Callable[[Iterable[SolvedExample]], tuple[list[SolvedExample], int]] | None = None` hook applied between chain-verify and fence; S5-03 supplies the concrete implementation. When `None` (default for S5-01), all candidates pass. The hook returns `(surviving, excluded_count)`.

## Implementation outline

```python
# src/codegenie/rag/retriever.py
from typing import Protocol, Callable
from dataclasses import dataclass

class ConfidenceClassifier(Protocol):
    def classify(
        self,
        candidates: list[tuple[FencedSegment, SolvedExample, Similarity]],
    ) -> RetrievalOutcome: ...

@dataclass(frozen=True)
class SolvedExampleRetriever:
    store: SolvedExampleStore
    embedder: Embedder
    record_provenance: RecordProvenance
    fence_wrapper: FenceWrapper
    query_builder: Callable[[CveAdvisory, RepoContext], Query]
    confidence_classifier: ConfidenceClassifier
    event_log: EventLog
    model_digest_filter: Callable[[Iterable[SolvedExample]], tuple[list[SolvedExample], int]] | None = None

    async def query(self, advisory: CveAdvisory, repo_ctx: RepoContext) -> RetrievalOutcome:
        q = self.query_builder(advisory, repo_ctx)
        self.event_log.emit(QueryBuilt(cve_id=advisory.cve_id, query_digest=q.digest()))

        embedding = await self.embedder.embed(q.text)
        self.event_log.emit(RecordsEmbedded(query_digest=q.digest()))

        raw = await self.store.query_candidates(q, embedding=embedding, top_k=5)
        self.event_log.emit(StoreQueried(count=len(raw)))

        if not raw:
            outcome = RagMiss(reason="empty_store")
            self.event_log.emit(outcome.to_event())
            return outcome

        # Chain verify
        spanning_log = self.record_provenance.spanning_log()
        verified: list[tuple[SolvedExample, Similarity]] = []
        for record, score in raw:
            if self.record_provenance.verify(record, spanning_log):
                verified.append((record, score))
            else:
                self.event_log.emit(RagRecordChainOrphan(
                    record_id=record.id,
                    chain_head=record.provenance.event_chain_head,
                    expected_chain_head=spanning_log.head(),
                ))
        if not verified:
            outcome = RagMiss(reason="all_candidates_chain_orphan")
            self.event_log.emit(outcome.to_event())
            return outcome

        # Model-mismatch hook (S5-03 supplies concrete; default = passthrough)
        records = [r for r, _ in verified]
        if self.model_digest_filter is not None:
            surviving_records, excluded = self.model_digest_filter(records)
            if excluded:
                self.event_log.emit(RagRecordModelMismatch(count=excluded))
            verified = [(r, s) for (r, s) in verified if r in surviving_records]
            if not verified:
                outcome = RagMiss(reason="all_candidates_model_mismatch")
                self.event_log.emit(outcome.to_event())
                return outcome

        # Fence retrieved content (TRUST BOUNDARY)
        candidates: list[tuple[FencedSegment, SolvedExample, Similarity]] = []
        for record, score in verified:
            fenced = self.fence_wrapper.fence(
                record.canonical_yaml_bytes(),
                source_kind="rag_retrieved",
            )
            candidates.append((fenced, record, score))
        self.event_log.emit(RecordsFenced(count=len(candidates)))

        outcome = self.confidence_classifier.classify(candidates)
        self.event_log.emit(outcome.to_event())
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
    sequence (build_query, embed, store_query, chain_verify, fence, classify).
    Out-of-order dispatch would mean unfenced bytes pass through the classifier
    (trust-boundary breach ADR-04-0013), or chain-orphan records reach prompt
    assembly (poisoning vector edge case #14)."""
    calls: list[str] = []
    qb = lambda a, c: (calls.append("build_query"), Query(text="t"))[1]
    embedder = AsyncMock(); embedder.embed.side_effect = lambda t: (calls.append("embed"), [0.1]*384)[1]
    store = AsyncMock(); store.query_candidates.side_effect = lambda q, **kw: (
        calls.append("store_query"),
        [(solved_example_fixture(), Similarity(0.9))],
    )[1]
    rp = MagicMock(); rp.verify.side_effect = lambda r, log: (calls.append("chain_verify"), True)[1]
    fw = MagicMock(); fw.fence.side_effect = lambda b, source_kind: (calls.append("fence"), fenced_segment_fixture)[1]
    classifier = MagicMock(); classifier.classify.side_effect = lambda c: (calls.append("classify"), RagHit(few_shot=c[0][1], score=c[0][2]))[1]

    retriever = SolvedExampleRetriever(
        store=store, embedder=embedder, record_provenance=rp,
        fence_wrapper=fw, query_builder=qb,
        confidence_classifier=classifier, event_log=MagicMock(),
    )
    outcome = await retriever.query(advisory_fixture, repo_ctx_fixture)
    assert calls == ["build_query", "embed", "store_query", "chain_verify", "fence", "classify"]
    assert isinstance(outcome, RagHit)
```

### Green — make it pass

1. Land `src/codegenie/rag/retriever.py` per the implementation outline above. Use a frozen dataclass; constructor injection only.
2. Land the `ConfidenceClassifier` Protocol in the same module (or `rag/types.py` if narrower).
3. Implement the dispatch verbatim in the named order; emit one audit event per step.
4. For S5-01's GREEN baseline, supply an in-test stub `ConfidenceClassifier` that always returns the highest-scored candidate as `RagHit` — the real classifier lands in S5-02 and is unit-tested separately.
5. The `RagMiss(reason=...)` early-return for empty store, all-chain-orphan, and all-model-mismatch must skip the classifier entirely (event-absence test).

### Refactor — clean up

- Extract the per-record verification loop into a private `_verify_chain(raw, spanning_log) -> tuple[list[(SE, sim)], int]` helper to keep `query()` readable.
- Extract the fence loop into `_fence_candidates(verified) -> list[(FencedSegment, SE, sim)]` if the `query()` body grows past ~40 LOC.
- Confirm no concrete imports of `chromadb`, `fastembed`, `onnxruntime` in `retriever.py` (Protocols only). Add an AST guard test if Phase 3 / Phase 2 has a precedent for "module-import discipline" tests.
- Confirm `match outcome` over `RagHit | RagDegraded | RagMiss` with `assert_never` is exhaustive; mypy --strict catches missing arms.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/retriever.py` | NEW — `SolvedExampleRetriever` + `ConfidenceClassifier` Protocol. |
| `src/codegenie/rag/events.py` (or extend existing event module) | NEW/EXT — `QueryBuilt`, `RecordsEmbedded`, `StoreQueried`, `RecordsFenced`, `RagRecordChainOrphan`, `RagRecordModelMismatch` event types (Pydantic frozen, extra=forbid). |
| `tests/unit/rag/test_retriever_dispatch_order.py` | NEW — dispatch order assertion. |
| `tests/unit/rag/test_retriever_empty_store.py` | NEW — empty store ⇒ `RagMiss(reason="empty_store")`. |
| `tests/unit/rag/test_retriever_chain_orphan.py` | NEW — chain-orphan exclusion + event emission. |
| `tests/unit/rag/test_retriever_fences_record_content.py` | NEW — fence is called once per surviving candidate with `source_kind="rag_retrieved"`. |
| `tests/unit/rag/test_retriever_idempotent.py` | NEW — same `(cve_id, manifest_digest, embedding_model_digest, store_digest)` ⇒ byte-identical outcome. |
| `tests/property/test_retriever_query_construction_deterministic.py` | NEW — Hypothesis: query construction stable across two consecutive calls. |
| `tests/adversarial/test_rag_poisoning_runtime_inject.py` | NEW — injection bytes in `canonical_yaml_bytes` escape via fence; never reach prompt-bound surface. |
| `tests/fence/test_retriever_no_fstring_query.py` | NEW — AST-walk: no `JoinedStr` in `retriever.py`'s `query()` body. |
| `tests/bench/test_retriever_perf.py` | NEW (marker `bench`) — p99 ≤ 100ms @ 10K seeded examples. |
| `tests/golden/rag/retriever_event_sequence.json` | NEW — canonical happy-path event sequence schema. |

## Out of scope

- **Band classification logic** — S5-02 owns the `(score → AdapterConfidence → RagHit|RagDegraded|RagMiss)` mapping. S5-01 ships only the Protocol and an in-test stub classifier.
- **Model-mismatch concrete filter** — S5-03 supplies the `model_digest_filter`. S5-01 ships only the optional hook (default `None` = passthrough).
- **Plugin `rag_query_builder.py`** — S7-02 ships the production builder. S5-01 accepts the callable via constructor.
- **Calibration smoke test** — S5-04 owns; this story does not seed fixtures into a real store.
- **Retry path (`prior_attempts` bypass)** — ADR-04-0011; lives at `FallbackTier` level (S6-01/S6-02); the retriever has no `prior_attempts` parameter.
- **`store.query_candidates` interface** — Step 4 ships `store.query()` returning `RetrievalOutcome`; if Step-4's signature already classifies, surface per Global Rule 7 and split into `query_candidates() -> list[(SolvedExample, Similarity)]` (called by retriever) + `query() -> RetrievalOutcome` (caller convenience). Do not edit Step-4 to "blend" the two.

## Notes for the implementer

- **Trust boundary discipline (load-bearing).** ADR-04-0013 is the most important reference here. Every byte that originates in a `SolvedExample` record and could end up inside an LLM prompt body **must** pass through `FenceWrapper.fence(..., source_kind="rag_retrieved")` before leaving this module. The AST-walk test in `tests/fence/test_retriever_no_fstring_query.py` is one half of the enforcement; the runtime test in `test_retriever_fences_record_content.py` is the other.
- **Closed sum return.** Resist the temptation to return `RetrievalOutcome | None`. `RagMiss` *is* the "no hit" variant; `None` would be primitive obsession on the absence case (ADR-0033). mypy --strict + `match outcome` exhaustiveness is the gate.
- **Event-absence is a load-bearing test idiom.** When `RagMiss(reason="empty_store")` fires, the classifier must **not** be called. Mock the classifier with `side_effect=pytest.fail("classifier called on empty store")` to encode this.
- **`store.query_candidates` vs `store.query`.** Step 4's Protocol signature (`query(q, top_k, similarity_floor) -> RetrievalOutcome`) already returns a classified outcome. That is the wrong split — classification belongs to the retriever (so it composes with chain-verify + fence + model-mismatch). When you land S5-01, **rename Step-4's method to `query_candidates`** and have it return `list[tuple[SolvedExample, Similarity]]`. Document the rename as a Phase-4-internal Step-4-to-Step-5 contract refinement in the story's PR; do not surface as a Phase-5 contract change (still pre-Phase-5).
- **`spanning_log` access.** `RecordProvenance.spanning_log()` is the Step-4 surface; if Step 4 ships `verify(record, spanning_log)` with the caller supplying the log, that's fine — the retriever holds a `record_provenance` reference and calls `.spanning_log()` once at the top of `query()` to amortize.
- **Deterministic-event-order property.** AC-14's golden file is the contract; the determinism property in S6-07 reads this event sequence as part of its 50-run replay invariance check. Get the event order right here and the downstream property is half-written.
- **No `prior_attempts` on this retriever.** A reader unfamiliar with ADR-04-0011 may "helpfully" thread `prior_attempts` through `query()` to "exclude previously-used hits." That's the wrong layer — the retry-bypass discipline lives at `FallbackTier`, not the retriever. The retriever is the initial-plan-only read path. If you find yourself adding `prior_attempts` to `query()`, stop and re-read ADR-04-0011.
- **Performance budget.** The 100ms p99 is dominated by embed (80ms cold). The store query (≤ 15ms) is sqlite + ANN; the chain-verify + fence loops are pure-Python over ≤ 5 records and should be sub-millisecond. If the bench fails, investigate the embed path (cache hit rate on `embeddings.cache.sqlite`) before the retriever itself.
