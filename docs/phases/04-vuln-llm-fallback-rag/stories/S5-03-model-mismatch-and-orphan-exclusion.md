# Story S5-03 — Embedding-model-mismatch exclusion filter + combined exclusion order

**Step:** Step 5 — Ship SolvedExampleRetriever + two-threshold band + calibration smoke test
**Status:** HARDENED
**Effort:** S
**Depends on:** S5-01 (**HARDENED, not GREEN** — ships `SolvedExampleRetriever`, the frozen `ScoredSolvedExample(record, score)` DTO, and the optional `model_digest_filter` hook typed `Callable[[Sequence[ScoredSolvedExample]], tuple[list[ScoredSolvedExample], int]] | None`; this story ships the concrete filter that plugs into that hook), S5-02 (**HARDENED, not GREEN** — `BandClassifier`; only needed by the retriever-integration ACs, which may use a mock classifier), S4-01 (`Embedder.model_digest() -> BlobDigest` is the comparability contract), S4-05 (**HARDENED, not GREEN** — module-level `codegenie.rag.provenance.verify(record, spanning_log) -> bool` + `SpanningChainLog` Protocol + the `RagRecordChainOrphan` `WorkflowInternalEvent`)
**ADRs honored:** ADR-04-0007 (`fastembed` BGE-small pinned; `model_digest()` is the cache-key + comparability contract — records embedded under a different model are *not* comparable cosine-similarity-wise and must be excluded), ADR-04-0016 (canonical YAML; `embeddings.cache.sqlite` is derived; `codegenie rag rebuild --reembed` is the operator remediation), production ADR-0008 (objective-signal trust scoring — silently mixing embedding spaces would produce high-confidence scores from incomparable evidence), production ADR-0033 (closed sum types — the all-excluded path returns a **bare** `RagMiss()`; the *reason* is carried by S5-01's typed `RagMissEvent(reason="all_candidates_model_mismatch")`, never a field on `RagMiss`)

## Validation notes

Validated: 2026-05-22
Verdict: HARDENED
Findings addressed: 18 — 7 blocks, 8 hardens, 3 nits

Changes applied:
- **Filter retyped to the hardened S5-01 hook (block).** S5-01 (HARDENED, AC-17) froze `model_digest_filter` as `Callable[[Sequence[ScoredSolvedExample]], tuple[list[ScoredSolvedExample], int]]`. The draft's filter was `Iterable[SolvedExample] -> tuple[list[SolvedExample], int]` — not assignable to the hook (a mypy `--strict` error; `SolvedExample` is not `ScoredSolvedExample`). Every AC, the outline, the TDD plan, and the property test now consume `Sequence[ScoredSolvedExample]` and partition on `candidate.record.embedding_model`.
- **Wrong event module (block).** The draft routed `RagRecordModelMismatch` through `src/codegenie/rag/events.py`. That module does not exist and is forbidden — S4-05 (HARDENED) and S5-01 (HARDENED) both route every RAG event into `src/codegenie/plugins/events.py` as a `WorkflowInternalEvent`. The event now lands there, wired into the union, `_INTERNAL_CLASSES`, and `__all__`.
- **`RagMiss(reason=...)` removed (block).** S1-04 / S5-01 / S5-02 (all HARDENED) fixed `RagMiss` to **bare** per ADR-04-0008. AC-6 now returns bare `RagMiss()` and the reason rides S5-01's `RagMissEvent(reason="all_candidates_model_mismatch")`.
- **`RecordProvenance.verify` corrected (block).** S4-05 (HARDENED, AC-1) ships a *module-level* `codegenie.rag.provenance.verify(record, spanning_log)`; `RecordProvenance` stays frozen data with no behavior. Every reference corrected.
- **`RagRecordModelMismatch` double-emission resolved (block, Rule 7).** S5-01 AC-17 currently also has the *retriever* emit `RagRecordModelMismatch`; with this story's filter emitting too, that is two events — violating "exactly one per query". The filter owns the emission (only it holds `current_model` + `sample_stale_model`). **Pre-execution reconciliation required:** S5-01 AC-17 + Files-to-touch must drop the retriever-side emission and the retriever-side event-class definition. See Out-of-scope.
- **AC-9 removed (block).** The draft's AC-9 demanded `verify` check the `(record_id, chain_head)` pair and called head-only verification "a bug". S4-05 (HARDENED) + final-design §Component 11 *deliberately* chose head-only verification ("not a `(record_id, chain_head)` proof"); `SpanningChainLog` has exactly one method and `record_id_for_head` is explicitly forbidden. The AC contradicted a HARDENED decision and was removed.
- **Adversarial chain-orphan file de-conflicted (block).** The draft created `tests/adversarial/test_rag_poisoning_chain_orphan.py`; that file is owned by S7-09 (Files-to-touch + done-criteria) and S4-05 (line 37). S5-03's draft AC-8/AC-10 duplicated coverage already in S4-05 AC-9 (orphan-emit smoke) and S7-09 (adversarial corpus). They were removed; S5-03's genuine, non-duplicative chain-orphan contribution — the **combined exclusion order** — is retained and strengthened (AC-8/AC-9).
- **Smaller hardens:** `event_log.emit(...)` → `emit_internal(...)` (`EventLog` has no bare `emit`); retriever-integration ACs given an `xfail(strict=True)` deferral keyed on "S5-01 GREEN" (mirrors S5-02 AC-14); the event model now declares the standard `WorkflowInternalEvent` fields; AC-11 adds a discriminator-registration assertion; the filter's `workflow_id`/`event_id` source is pinned; the Hypothesis property now also covers `k=0`; Red snippet renamed to the file it actually tests.

Full audit log: docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S5-03-model-mismatch-and-orphan-exclusion.md

## Context

S5-01 wired the read pipeline with an optional `model_digest_filter` hook applied between chain-verification and fencing; when the hook is `None` (S5-01's default) all candidates pass through. S5-02 shipped the pure band classifier. This story closes the embedding-model-drift correctness hole and pins the order in which the two exclusion gates compose:

1. **Embedding-model drift exclusion (edge case #19, Gap 1).** When the operator bumps the embedding model (e.g. from `BAAI/bge-small-en-v1.5` to a newer pin), the `embeddings_model.lock` SHA changes and `Embedder.model_digest()` returns a new `BlobDigest`. Existing records in the store carry `SolvedExample.embedding_model` pointing at the *previous* digest. A naive cosine-similarity query treats those records as comparable — but the embedding space is different, so the scores are meaningless. Including them silently is the worst RAG failure mode: the band classifier would receive scores from two embedding spaces and return high-confidence hits on records embedded under a different model. The filter must **exclude** mismatched candidates and emit exactly one `RagRecordModelMismatch(count)` event per query — not one per record: operators want a single "you have 47 stale records; run `codegenie rag rebuild --reembed`" signal, not 47 noisy events.

2. **Combined exclusion order (edge case #14 interaction).** S5-01's retriever runs chain-orphan verification *before* the `model_digest_filter`. This story pins that order: chain-orphan exclusion is a **forgery-correctness** gate; model-mismatch exclusion is a **comparability** gate. A forged record that *also* carries a stale embedding model must be attributed to forgery (`RagRecordChainOrphan`), not to benign operator staleness (`RagRecordModelMismatch`). Order-dependence is a real correctness property, so it gets explicit tests.

`EmbeddingModelMismatchFilter` is the concrete, production case of S5-01's `model_digest_filter` hook. This story ships it and wires it into the `SolvedExampleRetriever` construction site via integration tests; the production plugin-load wiring lands later (S7-01).

The forged-chain-head **adversarial** corpus (`tests/adversarial/test_rag_poisoning_chain_orphan.py`) is **not** this story's deliverable — it is owned by S7-09, and S4-05 AC-9 already ships the chain-orphan emit smoke test. See Out-of-scope.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Edge cases #19` (line 946) — "RAG record `embedding_model` mismatch with current model → exclude + emit `RagRecordModelMismatch`; operator triggers `codegenie rag rebuild --reembed`."
  - `../phase-arch-design.md §Edge cases #14` (line 941) — "RAG record chain-orphan on retrieval → exclude record from result set; emit `RagRecordChainOrphan`; continue."
  - `../phase-arch-design.md §Gap-analysis remediations` item 1 (line 1091) — "`SolvedExampleRetriever` excludes records whose `embedding_model != embedder.model_digest()` and emits `RagRecordModelMismatch(count)` once per workflow (already in edge case #19)."
- **Phase ADRs:**
  - `../ADRs/0007-fastembed-onnx-over-sentence-transformers.md` — `model_digest()` is the cache-key + comparability contract; the embedder refuse-starts on lock-hash drift.
  - `../ADRs/0016-chromadb-embedded-yaml-canonical-store.md` — canonical YAML records carry `embedding_model`; chroma is derived.
- **Production ADRs:**
  - `../../../production/adrs/0008-objective-signal-trust-score.md` — confidence must rest on comparable evidence; mixing embedding spaces would inflate it.
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — closed sum types; `RagMiss` is bare; reasons are typed events.
- **Source design:**
  - `../final-design.md §Component 11 — SolvedExampleRetriever` — "excludes records whose `embedding_model != embedder.model_digest()`"; chain verification is "the record's chain head must appear somewhere in the spanning chain log — not a `(record_id, chain_head)` proof".
- **High-level impl:**
  - `../High-level-impl.md §Step 5` (line 147) — "Excludes records whose `embedding_model != embedder.model_digest()` and emits `RagRecordModelMismatch` (Gap 1, edge case #19)."
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - `src/codegenie/rag/retriever.py` (S5-01) — the `model_digest_filter: Callable[[Sequence[ScoredSolvedExample]], tuple[list[ScoredSolvedExample], int]] | None` hook (S5-01 AC-17); the frozen `ScoredSolvedExample(record: SolvedExample, score: Similarity)` DTO; the retriever's `chain-verify → model_digest_filter → fence → classify` dispatch.
  - `src/codegenie/rag/embedder.py` (S4-01) — `Embedder.model_digest() -> BlobDigest` is the comparison target.
  - `src/codegenie/rag/provenance.py` (S4-05) — module-level `verify(record, spanning_log) -> bool`; head-only membership semantics. `RecordProvenance` is frozen data with no behavior.
  - `src/codegenie/plugins/events.py` (S6-01) — the real `EventLog`. `emit_internal(event)` accepts a `WorkflowInternalEvent`, stamps `timestamp`, and requires the event ∈ `_INTERNAL_CLASSES`. `EventLog.workflow_id` is public. S4-05 ships `RagRecordChainOrphan` here; this story adds `RagRecordModelMismatch` here.
  - `src/codegenie/rag/models.py` (S1-04) — `SolvedExample.embedding_model: BlobDigest`; `RagMiss` is **bare** (no `reason` field).
  - `src/codegenie/types/identifiers.py` — `BlobDigest`, `EventId`, `WorkflowId`, `Similarity`, `SolvedExampleId` newtypes; import, do not redefine.

## Goal

Ship `EmbeddingModelMismatchFilter` — the concrete `model_digest_filter` callable that excludes `ScoredSolvedExample` candidates whose `record.embedding_model != embedder.model_digest()` and emits exactly one `RagRecordModelMismatch` event per query — and pin the **combined exclusion order** (chain-orphan verification before model-mismatch filtering) in the retriever's dispatch.

## Acceptance criteria

### Concrete filter shape

- [ ] AC-1 — `src/codegenie/rag/exclusion.py` (new module) exports `EmbeddingModelMismatchFilter`, a `@dataclass(frozen=True)` with fields `embedder: Embedder` and `event_log: EventLog`. `__post_init__` reads `embedder.model_digest()` once and caches the resulting `BlobDigest` on a `_current_model_digest: BlobDigest = field(init=False)` attribute via `object.__setattr__` (frozen-dataclass lazy-cache idiom — ADR-04-0007 pins the digest for the embedder lifetime, so caching is correct). `__all__` is pinned to exactly `("EmbeddingModelMismatchFilter",)`.
- [ ] AC-2 — `EmbeddingModelMismatchFilter.__call__(candidates: Sequence[ScoredSolvedExample]) -> tuple[list[ScoredSolvedExample], int]` returns `(surviving, excluded_count)`. Surviving candidates are exactly those whose `candidate.record.embedding_model == self._current_model_digest`. The signature is **byte-identical** to S5-01's `model_digest_filter` hook (`Sequence[ScoredSolvedExample]` in, `tuple[list[ScoredSolvedExample], int]` out) so the filter is directly assignable to it — a mypy `--strict` assignability test pins this.
- [ ] AC-3 — On `excluded_count > 0`, the filter emits **exactly one** `RagRecordModelMismatch` event via `self.event_log.emit_internal(...)`, with `count=excluded_count`, `current_model=self._current_model_digest`, `sample_stale_model=<any one excluded candidate's record.embedding_model>`, `workflow_id=self.event_log.workflow_id`, and a freshly minted `event_id` (per the convention used by sibling `WorkflowInternalEvent` emitters — S4-05's orphan-emit, S5-01's retriever events). `sample_stale_model` carries **one** digest, not a list (fixed-shape, audit-volume-bounded payload). `timestamp` is supplied as a placeholder and overwritten by `emit_internal`'s stamper.
- [ ] AC-4 — On `excluded_count == 0` (including an empty input), **no** event is emitted — no `RagRecordModelMismatch(count=0)` noise. Unit test asserts `event_log.emit_internal` was not called, via a `MagicMock` whose `emit_internal` has `side_effect=pytest.fail("emitted on zero exclusions")`.
- [ ] AC-7 — Determinism: invoking the filter twice with the same input `Sequence[ScoredSolvedExample]` returns equal `(surviving, excluded_count)` — equal element order and equal count. The filter holds no mutable state apart from the construction-time cached digest; the partition is order-preserving (surviving candidates appear in input order).

### Wiring into the retriever

- [ ] AC-5 — `tests/unit/rag/test_retriever_with_model_mismatch_filter.py` — constructs `SolvedExampleRetriever(model_digest_filter=EmbeddingModelMismatchFilter(...), ...)`; seeds 5 chain-verified `ScoredSolvedExample` candidates of which 3 carry the current model digest and 2 carry a stale digest. Asserts: the (mock) classifier is called with exactly the 3 current-digest candidates; exactly one `RagRecordModelMismatch(count=2)` event is emitted. **Precondition:** exercises S5-01's retriever end-to-end and requires S5-01 GREEN — until then land as `xfail(strict=True, reason="depends on S5-01 GREEN")` and record the deferral in the attempt log; do not silently skip.
- [ ] AC-6 — When **all** chain-verified candidates are model-mismatched, the retriever (via S5-01's all-excluded path) returns a **bare `RagMiss()`** and emits S5-01's `RagMissEvent(reason="all_candidates_model_mismatch")` — *after* the filter has emitted one `RagRecordModelMismatch(count=N)`. The classifier is **not** called (mock classifier with `side_effect=pytest.fail("classifier called when all candidates excluded")`). There is no `RagMiss(reason=...)` anywhere — `RagMiss` is bare (S1-04/ADR-04-0008). Same S5-01-GREEN `xfail` precondition as AC-5.

### Combined exclusion order (chain-orphan + model-mismatch)

- [ ] AC-8 — `tests/unit/rag/test_combined_exclusion_order.py` — exercises `SolvedExampleRetriever` with a `record_verifier` that flags chain-orphans and the `EmbeddingModelMismatchFilter`. Seed five `ScoredSolvedExample` candidates: 2 chain-orphans, 1 model-mismatch, 2 valid. Asserts: chain-orphan verification runs **before** the `model_digest_filter` (S5-01's dispatch order); after both gates the classifier sees exactly the 2 valid candidates; events emitted are 2 × `RagRecordChainOrphan` (S4-05's shape) + 1 × `RagRecordModelMismatch(count=1)`. Order matters — a forged record with a stale embedding model must be attributed to forgery, not staleness. Same S5-01-GREEN `xfail` precondition.
- [ ] AC-9 — `tests/unit/rag/test_combined_exclusion_order.py::test_chain_orphan_removes_all_would_be_mismatched` — seed 3 candidates that are *both* chain-orphan **and** model-mismatched, plus 2 valid. After chain-orphan exclusion only the 2 valid candidates reach the `model_digest_filter`; the filter therefore sees 0 mismatched and emits **no** `RagRecordModelMismatch` event. Pins that the dispatch order prevents double-attribution (a chain-orphan is never also counted as a model-mismatch). Same S5-01-GREEN `xfail` precondition.

### Event shape + once-per-query invariant

- [ ] AC-10 — `src/codegenie/plugins/events.py` defines `RagRecordModelMismatch`, a frozen Pydantic `WorkflowInternalEvent` variant: `model_config = ConfigDict(frozen=True, extra="forbid")`; `event_type: Literal["rag_record_model_mismatch"] = "rag_record_model_mismatch"`; `event_id: EventId`; `workflow_id: WorkflowId`; `timestamp: datetime`; `count: Annotated[int, Field(ge=1)]`; `current_model: BlobDigest`; `sample_stale_model: BlobDigest`. It is wired into the `WorkflowInternalEvent` discriminated union, the `_INTERNAL_CLASSES` tuple, and `__all__` (matching the S4-05 `RagRecordChainOrphan` precedent). This story does **not** define or redefine `RagRecordChainOrphan` — S4-05 owns it (`record_id`, `record_event_chain_head`, `spanning_log_head`).
- [ ] AC-11 — `tests/unit/rag/test_model_mismatch_event_shape.py` + `tests/unit/plugins/test_events.py` — `RagRecordModelMismatch` rejects `count=0` (the `ge=1` validator), rejects unknown fields (`extra="forbid"`), and round-trips through `model_dump_json` / `model_validate_json` byte-identically. `tests/unit/plugins/test_events.py` additionally asserts `"rag_record_model_mismatch"` appears in `TypeAdapter(WorkflowInternalEvent).json_schema()["discriminator"]["mapping"]` and that the event round-trips through `EventLog.emit_internal(...)` / `replay()` — catching a "forgot to wire the union / `_INTERNAL_CLASSES`" mutant.
- [ ] AC-12 — `tests/property/test_model_mismatch_once_per_query.py` — Hypothesis: for any `Sequence[ScoredSolvedExample]` (including empty) where `k` candidates carry a mismatched digest, the filter emits exactly `1 if k > 0 else 0` `RagRecordModelMismatch` events per `__call__`; when emitted, `event.count == k` and `len(surviving) == len(input) - k`. The `k = 0` arm kills an "emit unconditionally" mutant; the `event.count == k` arm kills a "count = len(surviving)" mutant.

## Implementation outline

```python
# src/codegenie/rag/exclusion.py
"""Embedding-model-mismatch exclusion filter — the concrete production case
of S5-01's `model_digest_filter` hook.

ADR-04-0007: records embedded under a different model digest are NOT
comparable cosine-similarity-wise and MUST be excluded from retrieval.
Silent inclusion would mix embedding spaces — the worst RAG failure mode.

ADR-04-0016: operator remediation is `codegenie rag rebuild --reembed`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from codegenie.plugins.events import EventLog, RagRecordModelMismatch
from codegenie.rag.embedder import Embedder
from codegenie.rag.retriever import ScoredSolvedExample
from codegenie.types.identifiers import BlobDigest, EventId

__all__ = ("EmbeddingModelMismatchFilter",)


@dataclass(frozen=True)
class EmbeddingModelMismatchFilter:
    embedder: Embedder
    event_log: EventLog
    _current_model_digest: BlobDigest = field(init=False)

    def __post_init__(self) -> None:
        # frozen dataclass + lazy-cache attribute: object.__setattr__ is the
        # established idiom for assigning in __post_init__ on a frozen class.
        # ADR-04-0007: the embedder refuse-starts on lock-hash drift, so the
        # digest is invariant for the embedder lifetime — cache once.
        object.__setattr__(
            self, "_current_model_digest", self.embedder.model_digest()
        )

    def __call__(
        self, candidates: Sequence[ScoredSolvedExample],
    ) -> tuple[list[ScoredSolvedExample], int]:
        surviving: list[ScoredSolvedExample] = []
        excluded: list[ScoredSolvedExample] = []
        for candidate in candidates:
            if candidate.record.embedding_model == self._current_model_digest:
                surviving.append(candidate)
            else:
                excluded.append(candidate)
        if excluded:
            self.event_log.emit_internal(
                RagRecordModelMismatch(
                    event_id=EventId(str(uuid4())),  # sibling-emitter convention
                    workflow_id=self.event_log.workflow_id,
                    timestamp=datetime.now(tz=UTC),  # overwritten by emit_internal
                    count=len(excluded),
                    current_model=self._current_model_digest,
                    sample_stale_model=excluded[0].record.embedding_model,
                )
            )
        return surviving, len(excluded)
```

## TDD plan — red / green / refactor

### Red — write the failing test first

```python
# tests/unit/rag/test_model_mismatch_filter.py
from unittest.mock import MagicMock

from codegenie.rag.exclusion import EmbeddingModelMismatchFilter
from codegenie.rag.retriever import ScoredSolvedExample
from codegenie.types.identifiers import BlobDigest, Similarity, WorkflowId


def test_stale_model_candidates_excluded_with_single_event(solved_example_fixture):
    """ADR-04-0007 mandates exclusion of candidates whose record was embedded
    under a stale model digest — they are not cosine-comparable. Silent
    inclusion is the worst failure mode (mixing embedding spaces -> meaningless
    scores).

    The filter MUST emit exactly one RagRecordModelMismatch event per query
    (not per record): operators want one 'you have N stale records; run
    codegenie rag rebuild --reembed' signal, not N noisy events. Asserting
    count=2 (not 2x count=1) is the load-bearing invariant."""
    current = BlobDigest("a" * 64)
    stale = BlobDigest("b" * 64)
    embedder = MagicMock()
    embedder.model_digest.return_value = current
    event_log = MagicMock()
    event_log.workflow_id = WorkflowId("wf-test")
    filter_fn = EmbeddingModelMismatchFilter(embedder=embedder, event_log=event_log)

    def scored(rid, digest):
        return ScoredSolvedExample(
            record=solved_example_fixture(id=rid, embedding_model=digest),
            score=Similarity(0.9),
        )

    candidates = [
        scored("r1", current), scored("r2", stale), scored("r3", current),
        scored("r4", stale), scored("r5", current),
    ]
    surviving, count = filter_fn(candidates)

    assert [c.record.id for c in surviving] == ["r1", "r3", "r5"]  # order preserved
    assert count == 2
    emitted = [type(c.args[0]).__name__ for c in event_log.emit_internal.call_args_list]
    assert emitted.count("RagRecordModelMismatch") == 1
    evt = event_log.emit_internal.call_args_list[0].args[0]
    assert evt.count == 2
    assert evt.current_model == current
    assert evt.sample_stale_model == stale  # the only stale digest in the input
```

### Green — make it pass

1. Land `src/codegenie/plugins/events.py::RagRecordModelMismatch` per AC-10 — frozen, `extra="forbid"`, `count` annotated `Field(ge=1)`, the standard `WorkflowInternalEvent` fields — and wire it into the `WorkflowInternalEvent` union, `_INTERNAL_CLASSES`, and `__all__`. Add the discriminator-mapping + `emit_internal`/`replay` round-trip coverage in `tests/unit/plugins/test_events.py`.
2. Land `src/codegenie/rag/exclusion.py` with `EmbeddingModelMismatchFilter` per the implementation outline.
3. Land the filter unit tests (`test_model_mismatch_filter.py`): surviving/excluded partition, single-event invariant, zero-exclusion silence, empty input, determinism.
4. Land the event-shape tests (`test_model_mismatch_event_shape.py`) and the Hypothesis once-per-query property.
5. Land the retriever-integration tests (`test_retriever_with_model_mismatch_filter.py`, `test_retriever_all_model_mismatch_returns_miss.py`, `test_combined_exclusion_order.py`). **If S5-01 is not yet GREEN**, land each as `xfail(strict=True, reason="depends on S5-01 GREEN")` and record the deferral in the attempt log — do not skip silently (Rule 12).

### Refactor — clean up

- `EmbeddingModelMismatchFilter` is small (≤ 30 LOC); resist generalizing to a `RecordFilter` Protocol unless S6+ introduces a *second* concrete filter (rule-of-three — Rule 2).
- Confirm `__post_init__`'s `object.__setattr__` carries the inline "frozen dataclass + lazy-cache" comment so a future reader does not read it as a hack.
- Audit-volume check: a workflow with thousands of mismatched candidates still emits exactly one event (`count` carries the magnitude). Validate by seeding 1000 mismatched candidates in a test and asserting `event_log.emit_internal` was called exactly once.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/exclusion.py` | NEW — `EmbeddingModelMismatchFilter`. |
| `src/codegenie/plugins/events.py` | EXT — add `RagRecordModelMismatch`; wire into the `WorkflowInternalEvent` union, `_INTERNAL_CLASSES`, `__all__`. |
| `tests/unit/plugins/test_events.py` | EXT — discriminator-mapping + `emit_internal`/`replay` round-trip for `RagRecordModelMismatch`. |
| `tests/unit/rag/test_model_mismatch_filter.py` | NEW — partition behavior, single-event invariant, zero-exclusion silence, empty input, determinism. |
| `tests/unit/rag/test_model_mismatch_event_shape.py` | NEW — `RagRecordModelMismatch` Pydantic validation + JSON round-trip. |
| `tests/property/test_model_mismatch_once_per_query.py` | NEW — Hypothesis: exactly `1 if k>0 else 0` events; `count == k`. |
| `tests/unit/rag/test_retriever_with_model_mismatch_filter.py` | NEW — retriever + concrete filter integration (`xfail` until S5-01 GREEN). |
| `tests/unit/rag/test_retriever_all_model_mismatch_returns_miss.py` | NEW — all-excluded → bare `RagMiss()` + `RagMissEvent(reason="all_candidates_model_mismatch")` (`xfail` until S5-01 GREEN). |
| `tests/unit/rag/test_combined_exclusion_order.py` | NEW — chain-orphan-then-model-mismatch ordering + no double-attribution (`xfail` until S5-01 GREEN). |

## Out of scope

- **The forged-chain-head adversarial corpus** — `tests/adversarial/test_rag_poisoning_chain_orphan.py` is owned by **S7-09** (its Files-to-touch + done criteria) and named there by S4-05 (line 37). S4-05 AC-9 already ships the chain-orphan emit smoke test. S5-03 contributes only the *combined exclusion order* (AC-8/AC-9); it does not author the `tests/adversarial/` poisoning suite.
- **`(record_id, chain_head)`-bound provenance verification** — S4-05 (HARDENED) + final-design §Component 11 *deliberately* chose head-only verification ("the record's chain head must appear somewhere in the spanning chain log — not a `(record_id, chain_head)` proof"). `SpanningChainLog` exposes exactly one method; `record_id_for_head` is explicitly forbidden. Strengthening to record-id binding is a final-design + S4-05 ADR amendment, not S5-03 scope.
- **`RagRecordModelMismatch` emission by the retriever** — S5-01 AC-17 currently *also* specifies the retriever emitting this event. The concrete filter (this story) owns the emission, because only it holds `current_model` and `sample_stale_model`. **Pre-execution reconciliation (Rule 7):** S5-01 AC-17 + Files-to-touch must drop the retriever-side emission and the retriever-side event-class definition; the retriever uses the filter's returned `excluded_count` only to decide the all-excluded → bare `RagMiss()` branch. S5-01 is HARDENED (not GREEN), so this is amendable; surface it before either story executes.
- **`codegenie rag rebuild --reembed` CLI** — S4-07 ships the rebuild path. This story only emits the event whose operator-facing message points at that command.
- **Per-record `RagRecordModelMismatch` events** — out of scope by design. One event per query; `count` carries the magnitude; `sample_stale_model` carries one digest for grep triage. Enumerating every stale `record_id` is a future audit-shape amendment; do not anticipate.
- **Multiple-embedder support** — Phase 4 ships one embedder per workflow; `model_digest()` is pinned-cached at filter construction. A future multi-embedder design (Phase 11+) would replace this filter with a Strategy keyed on `(task_class, embedder_id)`; not Phase 4's problem.
- **Cassette / embeddings cache invalidation** — `.codegenie/rag/embeddings.cache.sqlite` is keyed on `BLAKE3(text)`, not on model digest (arch §Idempotence). A model bump invalidates the record-side `embedding_model` but does not corrupt the cache.

## Notes for the implementer

- **Why one event per query, not per record.** Operators triage by audit-event volume. A workflow with 200 mismatched records would otherwise emit 200 `RagRecordModelMismatch` events drowning out genuinely-distinct events (`RagHitEvent`, `LeafInvoked`, `SolvedExampleHarvested`). The arch design's "emits `RagRecordModelMismatch(count)` once per workflow" framing is deliberate; the pin is `event_log.emit_internal` called exactly once even for `count=1000`.
- **The filter consumes `ScoredSolvedExample`, not `SolvedExample`.** S5-01's retriever applies `model_digest_filter` to its `verified` list — `list[ScoredSolvedExample]`. Partition on `candidate.record.embedding_model`. A filter typed over `SolvedExample` is not assignable to the hook and fails mypy `--strict`; the assignability test in AC-2 is the structural guard.
- **The filter emits; it is not pure.** Unlike S5-02's classifier, this filter has a side effect (`emit_internal`). The *partition* is pure and order-preserving; the emission is the single impure tail. There is no purity AST-test for this module — emission is intentional. Keep the partition loop and the emission cleanly separated so the intent is legible.
- **`workflow_id` comes from the `EventLog`.** `EventLog.workflow_id` is public (S6-01). The filter does not need its own `workflow_id` constructor field — read `self.event_log.workflow_id`. Mint `event_id` the same way sibling `WorkflowInternalEvent` emitters do (S4-05's orphan-emit, S5-01's retriever events); `emit_internal` overwrites `timestamp` via its stamper, so any placeholder is fine.
- **`RagMiss` is bare — never `RagMiss(reason=...)`.** S1-04, S5-01, and S5-02 (all HARDENED) fixed `RagMiss` to carry no payload. The all-model-mismatch miss returns a bare `RagMiss()`; the reason rides S5-01's `RagMissEvent(reason="all_candidates_model_mismatch")`, emitted from the retriever's `match outcome` arm. Constructing `RagMiss(reason=...)` is an ADR-04-0008 violation.
- **Why chain-orphan runs first.** A forged record that also carries a stale embedding model would, under model-mismatch-first ordering, be excluded as a model-mismatch and the forgery signal would be lost. Chain-orphan-first attributes the exclusion correctly: forgery (active attack) is the more serious failure mode than benign staleness (an operator-intentional model bump). The dispatch order lives in S5-01's `query()` body; AC-8/AC-9 pin the observable behavior.
- **Consider injecting `BlobDigest` instead of `Embedder` (implementer's call).** AC-1 keeps `embedder: Embedder` to match the story's framing, but the filter only ever calls `model_digest()` once. Taking `current_model_digest: BlobDigest` directly would delete the `field(init=False)` / `__post_init__` / `object.__setattr__` frozen-cache dance entirely and make the filter trivially test-constructible (a 64-hex string vs a mocked `Embedder`). It narrows the dependency to exactly what is used. This is the *first* record filter, so it is below the rule-of-three threshold — either shape is acceptable; if you take the `BlobDigest` route, do it consistently across AC-1, the outline, and the tests, and note it in the attempt log.
- **`sample_stale_model` carries one digest, not all.** Audit-volume cap: the event payload is fixed-shape. If an operator needs to enumerate every stale digest, they grep `.codegenie/rag/records/<id>.yaml` for `embedding_model: <not-current-digest>`. The event is for *signalling*, not enumeration. Do not assert a *specific* `sample_stale_model` coupled to iteration order — assert membership in the set of stale digests in the input (the outline's `excluded[0]` is "any one", which is fine; the test must not over-pin it).
- **The cached `_current_model_digest`.** ADR-04-0007 commits the embedder to refuse-start on lock-hash drift, so `embedder.model_digest()` is invariant for the embedder lifetime. Caching at construction is correct; re-reading on every `__call__` would be a needless round-trip.
- **Hypothesis property boundaries.** `test_model_mismatch_once_per_query.py` generates `(num_candidates, k_mismatched)` and asserts `1 if k > 0 else 0` events and `event.count == k`. Cover `k=0` (no event — kills the "emit unconditionally" mutant), `k=1`, and `k=N` (all mismatched — pairs with AC-6's retriever-level all-excluded test).
