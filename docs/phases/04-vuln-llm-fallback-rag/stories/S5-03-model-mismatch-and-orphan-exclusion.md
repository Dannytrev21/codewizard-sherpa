# Story S5-03 — Model-mismatch + chain-orphan exclusion

**Step:** Step 5 — Ship SolvedExampleRetriever + two-threshold band + calibration smoke test
**Status:** Ready
**Effort:** S
**Depends on:** S5-02 (`BandClassifier` is in place; this story plugs the *exclusion filter* between chain-verify and classify), S5-01 (`SolvedExampleRetriever` accepts the optional `model_digest_filter` hook), S4-01 (`Embedder.model_digest()` is the contract being compared against), S4-05 (`RecordProvenance.verify` + chain-orphan event emission shipped here)
**ADRs honored:** ADR-04-0007 (`fastembed` BGE-small pinned; `model_digest()` is the cache-key contract — records embedded under a different model are *not* comparable cosine-similarity-wise and must be excluded), ADR-04-0016 (canonical YAML; `embeddings.cache.sqlite` is derived; `codegenie rag rebuild --reembed` is the operator remediation), production ADR-0008 (honest confidence — silently mixing embedding spaces would be a silent failure mode worse than missing records altogether), production ADR-0033 (closed sum types — exclusion produces `RagMiss(reason="all_candidates_model_mismatch")` or `RagMiss(reason="all_candidates_chain_orphan")`, never untyped sentinels)

## Context

S5-01 wired the read pipeline with an optional `model_digest_filter` hook and emitted `RagRecordChainOrphan` events per excluded record. S5-02 shipped the pure band classifier. This story closes two correctness holes that the retriever-as-shipped depends on:

1. **Embedding-model drift exclusion (edge case #19).** When the operator bumps the embedding model (e.g., from `BAAI/bge-small-en-v1.5` to a newer pin), the `embeddings_model.lock` SHA changes and `Embedder.model_digest()` returns a new `BlobDigest`. Existing records in the store carry `SolvedExample.embedding_model` pointing at the *previous* digest. A naive cosine-similarity query treats those records as comparable — but the embedding space is different, so the scores are meaningless. Including them silently would be the worst failure mode: the band classifier would receive scores from two embedding spaces and return high-confidence hits on records embedded under a different model. The system must **exclude** mismatched records and emit one `RagRecordModelMismatch(count)` event per query (not per record — operators want a single "you have 47 stale records; run `codegenie rag rebuild --reembed`" signal, not 47 noisy events).
2. **Chain-orphan exclusion exhaustiveness (edge case #14).** S5-01 emitted `RagRecordChainOrphan` per excluded record and returned `RagMiss(reason="all_candidates_chain_orphan")` when *all* candidates were orphans. This story adds the missing adversarial coverage: a poisoned record with a forged `event_chain_head` value that *does* hash-match a real spanning-log entry but was minted by a non-orchestrator path. The chain verification (S4-05) catches this; this story pins the test that `RecordProvenance.verify` does not accept the forgery and that the retriever's exclusion path fires.

The model-mismatch filter is the production case of S5-01's `model_digest_filter` hook. This story ships the concrete `EmbeddingModelMismatchFilter` and wires it into the production `SolvedExampleRetriever` construction site at plugin load (eventually S7-01; this story makes the filter available and the wiring exercise an integration test).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Edge cases #19` (line 946) — "RAG record `embedding_model` mismatch with current model → exclude + emit `RagRecordModelMismatch`; operator triggers `codegenie rag rebuild --reembed`."
  - `../phase-arch-design.md §Edge cases #14` (line 941) — "RAG record chain-orphan on retrieval → exclude record from result set; emit `RagRecordChainOrphan`; continue."
  - `../phase-arch-design.md §Gap-analysis remediations` item 1 (line 1091) — "`SolvedExampleRetriever` excludes records whose `embedding_model != embedder.model_digest()` and emits `RagRecordModelMismatch(count)` once per workflow (already in edge case #19)."
  - `../phase-arch-design.md §Adversarial tests` (line 1006) — `tests/adversarial/test_rag_poisoning_chain_orphan.py` "forged chain head; retrieval excludes + event-logs."
- **Phase ADRs:**
  - `../ADRs/0007-fastembed-onnx-over-sentence-transformers.md` — `model_digest()` is the cache-key + comparability contract.
  - `../ADRs/0016-chromadb-embedded-yaml-canonical-store.md` — canonical YAML records carry `embedding_model`; chroma is derived.
- **Production ADRs:**
  - `../../../production/adrs/0008-objective-signal-trust-score.md` — silent space-mixing would violate honest-confidence.
- **Source design:**
  - `../final-design.md §Component 11 — SolvedExampleRetriever` — "excludes records whose `embedding_model != embedder.model_digest()`".
- **High-level impl:**
  - `../High-level-impl.md §Step 5` (line 147) — "Excludes records whose `embedding_model != embedder.model_digest()` and emits `RagRecordModelMismatch` (Gap 1, edge case #19)."
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/rag/retriever.py` (S5-01) — the `model_digest_filter: Callable[[Iterable[SolvedExample]], tuple[list[SolvedExample], int]] | None` hook (AC-17 of S5-01).
  - `src/codegenie/rag/embedder.py` (S4-01) — `Embedder.model_digest() -> BlobDigest` is the comparison-target.
  - `src/codegenie/rag/provenance.py` (S4-05) — `RecordProvenance.verify(record, spanning_log) -> bool`; this story adds the forged-chain-head adversarial case.
  - `src/codegenie/rag/models.py` (S1-04) — `SolvedExample.embedding_model: BlobDigest`; `RagMiss.reason: Literal["empty_store","top1_below_floor","all_candidates_chain_orphan","all_candidates_model_mismatch"]`.

## Goal

Ship `EmbeddingModelMismatchFilter` — the concrete `model_digest_filter` callable that excludes `SolvedExample` records whose `embedding_model != embedder.model_digest()` and emits exactly one `RagRecordModelMismatch(count)` event per query — and pin the adversarial test that forged-chain-head records are excluded by `RecordProvenance.verify`.

## Acceptance criteria

### Concrete filter shape

- [ ] AC-1 — `src/codegenie/rag/exclusion.py` (new module) exports `EmbeddingModelMismatchFilter`, a frozen dataclass with `embedder: Embedder` and `event_log: EventLog`. Constructor reads `embedder.model_digest()` once and stores the resulting `BlobDigest` on the instance (cache; the embedder is pinned for the embedder lifetime per ADR-04-0007 refuse-start guard).
- [ ] AC-2 — `EmbeddingModelMismatchFilter.__call__(records: Iterable[SolvedExample]) -> tuple[list[SolvedExample], int]` — returns `(surviving, excluded_count)`. Surviving records are those whose `embedding_model == self._current_model_digest`. The filter is **callable** (implements `Callable[[Iterable[SolvedExample]], tuple[list[SolvedExample], int]]`) so it plugs into S5-01's `model_digest_filter` hook signature byte-identically.
- [ ] AC-3 — On `excluded_count > 0`, emits **exactly one** `RagRecordModelMismatch(count=excluded_count, current_model=current_digest, sample_stale_model=any_excluded.embedding_model)` event. The `sample_stale_model` field carries one excluded record's digest so the operator can grep audit logs for the specific drift; **not** a list of digests (audit-volume bound: one event per query, fixed-shape payload).
- [ ] AC-4 — On `excluded_count == 0`, no event is emitted (no `RagRecordModelMismatch(count=0)` noise). Unit test asserts event-absence via mock with `pytest.fail` side effect.

### Wiring into retriever

- [ ] AC-5 — `tests/unit/rag/test_retriever_with_model_mismatch_filter.py` — constructs `SolvedExampleRetriever(model_digest_filter=EmbeddingModelMismatchFilter(...), ...)`; seeds 5 candidates of which 3 carry the current model digest and 2 carry a stale digest. Asserts: classifier is called with 3 candidates; exactly one `RagRecordModelMismatch(count=2)` event emitted.
- [ ] AC-6 — When **all** candidates are model-mismatched, the retriever (via the path S5-01 ACs 17 added) returns `RagMiss(reason="all_candidates_model_mismatch")` after emitting one `RagRecordModelMismatch(count=N)` event. The classifier is **not** called. Mock-classifier with `side_effect=pytest.fail("classifier called when all candidates excluded")`.
- [ ] AC-7 — Determinism: invoking the filter twice with identical record iterables returns equal `(surviving, excluded_count)`. The filter is stateless apart from the cached `current_model_digest`; no I/O, no mutable internal counters.

### Chain-orphan adversarial coverage (the missing piece from S5-01)

- [ ] AC-8 — `tests/adversarial/test_rag_poisoning_chain_orphan.py` (new file) — seeds the store with a record whose `provenance.event_chain_head` is a syntactically-valid 64-hex BLAKE3 string but does **not** appear in the spanning log (a forged head that was never minted by the orchestrator). The retriever excludes the record + emits `RagRecordChainOrphan`. **Pins the adversarial-test entry already promised in arch §Adversarial tests.**
- [ ] AC-9 — `tests/adversarial/test_rag_poisoning_chain_orphan.py::test_forged_head_that_collides_with_unrelated_log_entry` — seeds a record whose `event_chain_head` does match a spanning-log entry, but the entry references a **different** record `id`. `RecordProvenance.verify` must check the (record_id, chain_head) pair, not just the head's presence. If S4-05's verify implementation only checks "head is in log," surface per Global Rule 7 — this is a verification bug, not an S5-03 scope edit. Document in `_attempts/` log.
- [ ] AC-10 — `tests/adversarial/test_rag_poisoning_chain_orphan.py::test_chain_orphan_does_not_halt_workflow` — five candidates, three orphans + two valid; retriever returns `RagHit`/`RagDegraded`/`RagMiss` (whichever band the top of the two valids lands in) **without raising**. Asserts three `RagRecordChainOrphan` events fired and the workflow completed.

### Combined exclusion order

- [ ] AC-11 — When both chain-orphan and model-mismatch records are present, chain-orphan exclusion runs **first** (per S5-01's dispatch). Test: five candidates — 2 chain-orphans, 1 model-mismatch, 2 valid. After both filters: classifier sees 2 valid candidates; events emitted: 2 × `RagRecordChainOrphan`, 1 × `RagRecordModelMismatch(count=1)`. Order matters because chain-orphan exclusion is a *correctness* gate (forgery defense) while model-mismatch is a *comparability* gate; a forged record with a stale embedding model would otherwise be reported as a model-mismatch (wrong attribution).
- [ ] AC-12 — When chain-orphan exclusion removes all candidates that *would* have been model-mismatched, the `RagRecordModelMismatch` event is **not** emitted (zero remaining records to compare). Test: 3 chain-orphan + model-mismatched records, 2 valid → after chain-orphan filter, only 2 valid remain → model-mismatch filter sees 0 mismatched → no event.

### Event shape + once-per-query invariant

- [ ] AC-13 — `RagRecordModelMismatch` is a frozen Pydantic model with `model_config = ConfigDict(frozen=True, extra="forbid")`; fields: `count: int (ge=1)`, `current_model: BlobDigest`, `sample_stale_model: BlobDigest`. `RagRecordChainOrphan` is per-record with `record_id: SolvedExampleId`, `chain_head: ChainHead`, `expected_chain_head: ChainHead`.
- [ ] AC-14 — `tests/unit/rag/test_model_mismatch_event_shape.py` — `RagRecordModelMismatch` rejects `count=0` (`ge=1` validator); rejects unknown fields (`extra="forbid"`); round-trips through `model_dump_json` / `model_validate_json` byte-identically.
- [ ] AC-15 — `tests/property/test_model_mismatch_once_per_query.py` — Hypothesis: for any non-empty list of records where `k > 0` have a mismatched digest, exactly one `RagRecordModelMismatch` event is emitted per `filter(records)` call; `event.count == k`.

## Implementation outline

```python
# src/codegenie/rag/exclusion.py
"""Model-mismatch exclusion filter for the S5-01 retriever's
`model_digest_filter` hook.

ADR-04-0007: records embedded under a different model digest are NOT
comparable cosine-similarity-wise and MUST be excluded from retrieval.
Silent inclusion would mix embedding spaces — the worst RAG failure mode.

ADR-04-0016: operator remediation is `codegenie rag rebuild --reembed`.
"""

from typing import Iterable
from dataclasses import dataclass

from codegenie.rag.embedder import Embedder
from codegenie.rag.models import SolvedExample
from codegenie.rag.events import RagRecordModelMismatch
from codegenie.events import EventLog
from codegenie.types.identifiers import BlobDigest


@dataclass(frozen=True)
class EmbeddingModelMismatchFilter:
    embedder: Embedder
    event_log: EventLog
    _current_model_digest: BlobDigest = field(init=False)

    def __post_init__(self) -> None:
        # ADR-04-0007: embedder is refuse-start on hash mismatch, so the
        # digest is pinned for embedder lifetime; cache once.
        object.__setattr__(self, "_current_model_digest", self.embedder.model_digest())

    def __call__(
        self, records: Iterable[SolvedExample],
    ) -> tuple[list[SolvedExample], int]:
        surviving: list[SolvedExample] = []
        excluded: list[SolvedExample] = []
        for record in records:
            if record.embedding_model == self._current_model_digest:
                surviving.append(record)
            else:
                excluded.append(record)
        if excluded:
            self.event_log.emit(RagRecordModelMismatch(
                count=len(excluded),
                current_model=self._current_model_digest,
                sample_stale_model=excluded[0].embedding_model,
            ))
        return surviving, len(excluded)
```

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/rag/test_retriever_with_model_mismatch_filter.py
import pytest
from unittest.mock import MagicMock, AsyncMock

@pytest.mark.asyncio
async def test_stale_model_records_excluded_with_single_event(
    advisory_fixture, repo_ctx_fixture, fenced_segment_fixture,
):
    """ADR-04-0007 mandates exclusion of records embedded under a stale
    model digest — they are not cosine-comparable. Silent inclusion is
    the worst failure mode (mixing embedding spaces → meaningless scores).

    The filter MUST emit exactly one RagRecordModelMismatch event per
    query (not per record): operators want one 'you have N stale records;
    run codegenie rag rebuild --reembed' signal, not N noisy events.
    Asserting count=2 (not 2× count=1) is the load-bearing invariant."""
    current = BlobDigest("a" * 64)
    stale = BlobDigest("b" * 64)
    embedder = MagicMock(); embedder.model_digest.return_value = current
    embedder.embed = AsyncMock(return_value=[0.1] * 384)
    event_log = MagicMock()
    filter_fn = EmbeddingModelMismatchFilter(embedder=embedder, event_log=event_log)

    records = [
        solved_example_fixture(id="r1", embedding_model=current),
        solved_example_fixture(id="r2", embedding_model=stale),
        solved_example_fixture(id="r3", embedding_model=current),
        solved_example_fixture(id="r4", embedding_model=stale),
        solved_example_fixture(id="r5", embedding_model=current),
    ]
    surviving, count = filter_fn(records)
    assert len(surviving) == 3
    assert count == 2
    emitted_kinds = [type(c.args[0]).__name__ for c in event_log.emit.call_args_list]
    assert emitted_kinds.count("RagRecordModelMismatch") == 1
    evt = event_log.emit.call_args_list[0].args[0]
    assert evt.count == 2 and evt.current_model == current
```

### Green — make it pass

1. Land `src/codegenie/rag/exclusion.py` with `EmbeddingModelMismatchFilter` per the implementation outline.
2. Land `src/codegenie/rag/events.py::RagRecordModelMismatch` (or extend S5-01's events module) with `count: Annotated[int, Field(ge=1)]`, `current_model: BlobDigest`, `sample_stale_model: BlobDigest`. Frozen + extra=forbid.
3. Wire the filter into the retriever construction site for the integration test: `SolvedExampleRetriever(model_digest_filter=EmbeddingModelMismatchFilter(embedder, event_log), ...)`. S5-01 already accepts the optional hook (AC-17 of S5-01); this is the production wiring.
4. Land the adversarial chain-orphan tests under `tests/adversarial/test_rag_poisoning_chain_orphan.py` — three cases: forged head not in log, forged head colliding with unrelated entry (this discovers whether S4-05's `verify` is record-id-bound or head-only-bound; if head-only, surface per Global Rule 7), and chain-orphan-doesn't-halt-workflow.
5. Land the combined-exclusion-order test pinning chain-orphan-first.

### Refactor — clean up

- The `EmbeddingModelMismatchFilter` is small (≤ 30 LOC); resist generalizing to a `RecordFilter` Protocol unless S6+ introduces a second concrete filter (pattern-of-three rule).
- Confirm `__post_init__` for the `_current_model_digest` cache uses `object.__setattr__` (frozen dataclass requires it); add an inline comment so the reader knows why.
- Audit-volume check: a workflow with thousands of mismatched records still emits exactly one event (`count` carries the magnitude). Validate by seeding 1000 mismatched records in a test and asserting `len(event_log.emit.call_args_list) == 1`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/exclusion.py` | NEW — `EmbeddingModelMismatchFilter`. |
| `src/codegenie/rag/events.py` (or extend) | EXT — add `RagRecordModelMismatch` event model. |
| `tests/unit/rag/test_model_mismatch_filter.py` | NEW — basic surviving/excluded behavior. |
| `tests/unit/rag/test_retriever_with_model_mismatch_filter.py` | NEW — retriever + concrete filter integration. |
| `tests/unit/rag/test_model_mismatch_event_shape.py` | NEW — event Pydantic validation. |
| `tests/property/test_model_mismatch_once_per_query.py` | NEW — Hypothesis: exactly-one-event invariant. |
| `tests/adversarial/test_rag_poisoning_chain_orphan.py` | NEW — forged head + collision + non-halt. |
| `tests/unit/rag/test_combined_exclusion_order.py` | NEW — chain-orphan-then-model-mismatch ordering. |
| `tests/unit/rag/test_retriever_all_model_mismatch_returns_miss.py` | NEW — all-excluded → `RagMiss(reason="all_candidates_model_mismatch")`. |

## Out of scope

- **`codegenie rag rebuild --reembed` CLI** — S4-07 ships the rebuild path. This story does not edit the CLI; it merely emits the event whose operator-facing message says "run `codegenie rag rebuild --reembed`".
- **Per-record `RagRecordModelMismatch` events** — out of scope by design. One event per query, `count` carries magnitude. If a future need arises to enumerate the stale `record_id`s, that's a Phase-7 audit-shape amendment; do not anticipate.
- **`RecordProvenance.verify` semantic fix** — if AC-9 discovers that S4-05's verify only checks head presence (not record-id binding), the fix belongs in S4-05's module + tests, not in S5-03. Surface per Global Rule 7 with a `_attempts/` note and let phase-story-validator decide the remediation path.
- **Multiple embedder support** — Phase 4 ships one embedder per workflow; `model_digest()` is pinned-cached at filter construction. A future multi-embedder design (Phase 11+) would replace this filter with a Strategy keyed on `(task_class, embedder_id)`; not Phase 4's problem.
- **Cassette/embeddings cache invalidation** — `.codegenie/rag/embeddings.cache.sqlite` is keyed on BLAKE3(text), not on model digest (per arch §Idempotence). A model bump invalidates record-side `embedding_model` but does not corrupt the cache; out of scope.

## Notes for the implementer

- **Why one event per query, not per record.** Operators triage by audit-event volume. A workflow with 200 mismatched records would otherwise emit 200 `RagRecordModelMismatch` events drowning out genuinely-distinct events (`RagHit`, `LeafInvoked`, `SolvedExampleHarvested`). The arch design's "emits `RagRecordModelMismatch(count)` once per workflow" framing is deliberate; the test pin is `len(event_log.emit.call_args_list) == 1` even for `N=1000`.
- **Why chain-orphan runs first.** A forged record with a stale embedding model would, under model-mismatch-first ordering, be excluded for model-mismatch and the chain-orphan signal would be lost. The reverse (chain-orphan-first) attributes the exclusion correctly: forgery is the more serious failure mode (active attack vs benign staleness from an operator-intentional model bump). The dispatch order is encoded in S5-01's `query()` body; this story pins the behavior via AC-11.
- **`object.__setattr__` for the frozen cache.** Frozen dataclasses reject `self.x = y` in `__post_init__`. The idiom `object.__setattr__(self, "x", y)` is the established Python pattern; add an inline comment naming "frozen dataclass + lazy-cache attribute" so future readers don't think it's a hack.
- **The `sample_stale_model` carries one digest, not all.** Audit volume cap: the `RagRecordModelMismatch` event payload is bounded-size. If the operator needs to enumerate all stale digests, they can grep `.codegenie/rag/records/<id>.yaml` for `embedding_model: <not-current-digest>`. The audit event is for *signalling*, not enumeration.
- **The S4-05 verification gap (AC-9).** Read S4-05's `provenance.py` before writing the adversarial test; if `verify` only checks `record.provenance.event_chain_head in spanning_log.heads()`, that's a record-id-unbound check and the forgery passes. Surface per Global Rule 7 with a concrete reproducer; the remediation path is S4-05 amendment, not S5-03 scope creep.
- **The cached `_current_model_digest`.** ADR-04-0007 commits to refuse-start on lock-hash drift, so `embedder.model_digest()` is invariant for the embedder lifetime. Caching at filter construction is correct; re-reading on every `__call__` would be a needless `model_digest()` round-trip (the embedder may compute it lazily). Document in the docstring.
- **Hypothesis property for once-per-query.** The `test_model_mismatch_once_per_query.py` property generates `(num_records, k_mismatched)` and asserts the event count is `1 if k > 0 else 0` and `event.count == k`. Cover the boundary `k=0` (no event), `k=1`, `k=N` (all mismatched — combined with the `RagMiss(reason="all_candidates_model_mismatch")` retriever-level test from AC-6).
- **No reliance on insertion order for `excluded[0]`.** The `sample_stale_model` is "any one stale digest." If the test seeds records in a specific order and asserts a specific sample, that couples to iteration semantics; assert `evt.sample_stale_model in {stale_digests_in_input}` instead.
