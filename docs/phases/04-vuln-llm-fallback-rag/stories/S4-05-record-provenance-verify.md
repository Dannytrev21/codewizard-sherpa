# Story S4-05 - `RecordProvenance.verify(record, spanning_log) -> bool` + `RagRecordChainOrphan` emission

**Step:** Step 4 - Ship RAG substrate kernel: Embedder + SolvedExampleStore + record provenance
**Status:** HARDENED
**Effort:** S
**Depends on:** S1-01 (`ChainHead`, `SolvedExampleId`, `BlobDigest`, `EventId`, `WorkflowId` newtypes), S1-04 (`SolvedExample` / `RecordProvenance` models), S4-04 (canonical YAML + manifest in place - the manifest's `chain_head` is the store's content head; per-record provenance is a separate chain anchor in the spanning event log)
**ADRs honored:** ADR-0016 (chain verification is part of read-side discipline), final-design §Component 11 - "the record's chain head must appear somewhere in the spanning chain log", Phase-3 ADR-0005 / S6-01 event-log surface (`codegenie.plugins.events.EventLog`)

## Validation notes

Validated: 2026-05-22
Verdict: HARDENED
Findings addressed: 15 - 4 block, 9 harden, 2 nit

Changes applied:
- **Event surface corrected (block).** `RagRecordChainOrphan` now lands in `src/codegenie/plugins/events.py` as a `WorkflowInternalEvent` with `event_type`, `event_id`, `workflow_id`, and `timestamp`, wired into the union, `_INTERNAL_CLASSES`, and `__all__`. The draft's `src/codegenie/rag/events.py` + `kind` shape would not be accepted by the actual `EventLog.emit_internal(...)` API.
- **Model-shape drift fixed (block).** The implementation outline now consumes S1-04's hardened `RecordProvenance` fields (`workflow_id`, `event_chain_head`, `created_at`, `signing_method`) instead of an older draft shape with `record_chain_head`, `model_id`, `embedding_dim`, and other non-existent fields.
- **Staticmethod alias removed (block).** The verifier is a module-level pure function in `codegenie.rag.provenance`. S1-04 keeps `RecordProvenance` as frozen data; this story no longer edits `models.py` to add behavior or a circular local import.
- **AC-9 integration test fixed (block).** The draft `await store.query(...) -> records` shape contradicted `SolvedExampleStore.query(...) -> RetrievalOutcome`. The hardened smoke test uses a retriever-like caller shim over an explicit candidate sequence and emits through the real `EventLog`.
- **AC-3 event fields clarified.** `record_chain_head` was renamed to `record_event_chain_head` so it cannot be confused with S4-04's store manifest / record-chain head. `spanning_log_head` remains a caller-supplied triage field; it is not added to the one-method `SpanningChainLog` Protocol.
- **AC-6 and AC-7 hardened.** Purity is now pinned by both call-count and AST side-effect checks; the empty-head defensive test uses `model_copy(update=...)` rather than mutating a frozen Pydantic model.
- **AC-8 rewritten.** The alias-equivalence property became the real property: for arbitrary candidate heads and known-head sets, `verify(record, log) == (record.provenance.event_chain_head in known_heads)`.
- **Files-to-touch reconciled.** Removed `src/codegenie/rag/models.py` and `src/codegenie/rag/events.py`; added `src/codegenie/plugins/events.py`, `tests/unit/plugins/test_events.py`, and a property test for the membership predicate.

Full audit log: docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S4-05-record-provenance-verify.md

## Context

Each `SolvedExample` carries a `provenance: RecordProvenance` field (S1-04). The provenance's `event_chain_head: ChainHead` records the **spanning-event-log chain head** at the moment the record was witnessed - the harvest event's enclosing chain head. At retrieval time (S5-01), every candidate record must be **chain-verified**: the record's `event_chain_head` must appear somewhere in the **current spanning chain log**. A record whose chain head is absent is a **chain-orphan**. Typical causes:

- A forged record (RAG-poisoning attempt) whose `event_chain_head` was fabricated.
- A record harvested by a worker whose event log was lost (machine crash, log rotation missed a window).
- A record imported from a different deployment whose spanning log is not the current one.

Final-design §Component 11 names this the simpler "the record's chain head must appear somewhere in the spanning chain log" verification - **not** a chain-segment proof and not a `(record_id, chain_head)` proof. The security guarantee is "this record claims a harvest-time chain head that is in our spanning log, not a head from nowhere." Edge case #14 says a chain-orphan is excluded and `RagRecordChainOrphan` is emitted; it **does not halt the workflow**. A broken or unreadable spanning event log is a different integrity failure owned by Phase 3's event-log verifier, not by this predicate.

This story lands the pure verifier at `src/codegenie/rag/provenance.py` (the path arch §System view names) plus the `RagRecordChainOrphan` `WorkflowInternalEvent` class in `src/codegenie/plugins/events.py`. S5-01 wires the verifier into the retriever; S7-09's adversarial test (`test_rag_poisoning_chain_orphan.py`) proves a forged chain head is excluded and event-logged.

The verifier is a **pure function** over the `SolvedExample` and a `spanning_log: SpanningChainLog` abstraction. `SpanningChainLog` is a minimal Protocol with one method: `def contains_chain_head(self, head: ChainHead) -> bool`. The actual spanning-log implementation lives in Phase 3's event-log infrastructure; this story takes it via injection.

## References - where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 7 - SolvedExampleStore` - `RecordProvenance` is a dependency; chain-orphan is a typed failure mode.
  - `../phase-arch-design.md §Component 9 - SolvedExampleRetriever` (line 605) - "Chain-orphan record excluded + `RagRecordChainOrphan` emitted. Returns `RagMiss` rather than raising when the store is empty."
  - `../phase-arch-design.md §Edge case #14` - chain-orphan detection: `provenance.event_chain_head` not in spanning log -> `RecordProvenance.verify` -> exclude record from result set + emit `RagRecordChainOrphan`; **continue**.
  - `../phase-arch-design.md §"Logging strategy"` (line 825) - `RagRecordChainOrphan` is a WARN event.
  - `../phase-arch-design.md §"Adversarial tests"` (line 1006) - `tests/adversarial/test_rag_poisoning_chain_orphan.py` is the eventual security test (S7-09 ships).
- **Phase ADRs:**
  - `../ADRs/0016-chromadb-embedded-yaml-canonical-store.md` §Consequences - `RecordProvenance.verify` is the read-side discipline that protects against poisoning at retrieval time.
- **Source design:**
  - `../final-design.md §Component 11 - SolvedExampleRetriever + retrieval-side discipline` (line 445) - the simpler "appears in spanning log" verification (chain-segment proof rejected as critic §"[S] §1" hidden assumption).
- **Existing code and hardened precedents:**
  - `src/codegenie/plugins/events.py` - the actual Phase-3+ event sourcing surface. `EventLog.emit_internal(...)` accepts typed `WorkflowInternalEvent` variants; registering an event means adding a Pydantic class, the `WorkflowInternalEvent` union row, `_INTERNAL_CLASSES`, and `__all__`.
  - `docs/phases/04-vuln-llm-fallback-rag/stories/S1-04-rag-pydantic-models.md` - source of truth for `SolvedExample` and `RecordProvenance` field shapes.
  - `docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S2-01-provenance-gate-tier-zero.md`, `S2-02-fence-wrapper.md`, `S2-05-llm-invocation-guard-budget-token.md` - repeated correction from stale `codegenie.audit.EventLog` / ad hoc event shapes to `codegenie.plugins.events`.
  - `src/codegenie/types/identifiers.py` for `ChainHead`, `SolvedExampleId`, `BlobDigest`, `EventId`, and `WorkflowId` after S1-01 lands.

## Goal

Ship `codegenie.rag.provenance.verify(record: SolvedExample, spanning_log: SpanningChainLog) -> bool` plus the one-method `SpanningChainLog` Protocol and the typed `RagRecordChainOrphan` internal event. The verifier returns `True` iff `record.provenance.event_chain_head` appears in the spanning log; returns `False` for empty / absent heads; performs no I/O, mutation, or event emission; and leaves exclusion + `RagRecordChainOrphan` emission to the caller (S5-01 retriever).

## Acceptance criteria

- [ ] **AC-1 - `verify` signature and purity boundary.** `src/codegenie/rag/provenance.py` exports a **module-level function**:
    ```python
    def verify(record: SolvedExample, spanning_log: SpanningChainLog) -> bool: ...
    ```
    It reads exactly `record.provenance.event_chain_head`, returns `False` when that value is empty / falsey, otherwise returns `spanning_log.contains_chain_head(head)`. It emits no events, writes no files, reads no env vars, opens no sockets, and does not mutate `record`. There is **no** `RecordProvenance.verify(...)` staticmethod alias and no edit to `src/codegenie/rag/models.py`: S1-04 keeps `RecordProvenance` as frozen data, and this module is the verification policy. (validator: hardened - removed circular-import-prone staticmethod alias while preserving the arch prose contract as the module docstring / function name.)
- [ ] **AC-2 - `SpanningChainLog` Protocol.** `src/codegenie/rag/provenance.py` declares:
    ```python
    @runtime_checkable
    class SpanningChainLog(Protocol):
        def contains_chain_head(self, head: ChainHead) -> bool: ...
    ```
    One method. Do not add `get_chain_segment`, `current_head`, `iter_events`, or `record_id_for_head`. The caller may have a current spanning head from its own event-log context for event payload triage, but that field does **not** belong on this Protocol.
- [ ] **AC-3 - `RagRecordChainOrphan` event class uses the real EventLog surface.** `src/codegenie/plugins/events.py` defines a frozen Pydantic `WorkflowInternalEvent` variant:
    ```python
    class RagRecordChainOrphan(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")
        event_type: Literal["rag_record_chain_orphan"] = "rag_record_chain_orphan"
        event_id: EventId
        workflow_id: WorkflowId
        timestamp: datetime
        record_id: SolvedExampleId
        record_event_chain_head: ChainHead  # record.provenance.event_chain_head that was absent
        spanning_log_head: ChainHead        # caller-supplied current head for triage
    ```
    The class is wired into the `WorkflowInternalEvent` discriminated union, `_INTERNAL_CLASSES`, and `__all__`. It is **workflow-internal**, not spanning: it describes one retrieval query's filter decision and carries no `prev_hash`. Do not create `src/codegenie/rag/events.py` for this story; that would fork the event registry and bypass `EventLog.emit_internal(...)`.
- [ ] **AC-4 - Verifier returns True on present chain head.** Given a fake `SpanningChainLog` whose `contains_chain_head(h)` returns `h == ChainHead("a" * 64)`, a record whose `provenance.event_chain_head == ChainHead("a" * 64)` returns `True`; `contains_chain_head` is called exactly once with that head.
- [ ] **AC-5 - Verifier returns False on absent chain head.** Given the same fake log, a record whose `provenance.event_chain_head == ChainHead("b" * 64)` returns `False`; `contains_chain_head` is called exactly once with that head. S7-09's adversarial test reuses this fixture shape against the retriever.
- [ ] **AC-6 - Verifier is pure and side-effect-free.** Unit tests assert that `verify` does not mutate `record`, does not call any side-effect-producing method on `spanning_log` beyond `contains_chain_head`, and does not access network/disk/env. Two checks pin this:
    - A `unittest.mock.Mock(spec=SpanningChainLog)` asserts `contains_chain_head` is called exactly once for non-empty heads and no other mock method is called.
    - An AST test over `codegenie.rag.provenance.verify` resolves calls and fails closed: allowed calls are only `bool`, attribute access, and `spanning_log.contains_chain_head`; forbidden calls include `open`, `Path.*`, `os.*`, `subprocess.*`, `socket.*`, `requests.*`, `logging.*`, `EventLog(...)`, `emit_internal`, and `emit_spanning`.
- [ ] **AC-7 - Verifier handles an empty chain head defensively.** Although `RecordProvenance.event_chain_head: ChainHead` is non-empty by S1-01's smart constructor, a forged in-memory model can still be built with `model_copy(update=...)` or a direct `ChainHead("")` cast. Test pins: create a valid `SolvedExample`, then derive a copy with `record.provenance.event_chain_head = ChainHead("")` using `model_copy(update=...)`; `verify(...)` returns `False` and does **not** call `spanning_log.contains_chain_head`. Do not mutate the frozen model in place.
- [ ] **AC-8 - Membership property.** `tests/property/test_provenance_verify_membership_property.py` uses Hypothesis to generate a valid 64-hex `record_head` and a set of valid 64-hex `known_heads`; it constructs a fake `SpanningChainLog` backed by `known_heads` and asserts:
    ```python
    verify(record, log) == (record.provenance.event_chain_head in known_heads)
    ```
    for at least 50 cases. This kills always-True, always-False, inverted-membership, and wrong-field mutants. The property also asserts `contains_chain_head` is called exactly once for every non-empty generated head.
- [ ] **AC-9 - `RagRecordChainOrphan` emission integration smoke test.** A thin integration test in `tests/integration/test_phase4_provenance_orphan_emit.py` constructs:
    - an actual `EventLog(root=tmp_path, workflow_id=WorkflowId(...))`;
    - a fake `SpanningChainLog` backed by one valid head and a caller-supplied `spanning_log_head`;
    - a retriever-like caller shim that iterates an explicit `Sequence[SolvedExample]`, calls `verify(record, spanning_log)` for each candidate, emits `RagRecordChainOrphan` via `event_log.emit_internal(...)` on `False`, and continues processing.
    With candidates `[forged_record, valid_record]`, the test asserts exactly one replayed event has `event_type == "rag_record_chain_orphan"`, with matching `record_id`, `record_event_chain_head`, and `spanning_log_head`; and the valid record is still processed after the orphan. The test must not call `SolvedExampleStore.query(...)` because that returns a `RetrievalOutcome`, not a raw record list.
- [ ] **AC-10 - Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean on the new modules + tests.
- [ ] **AC-11 - Event registration cannot drift.** `tests/unit/plugins/test_events.py` asserts `TypeAdapter(WorkflowInternalEvent).json_schema()["discriminator"]["mapping"]` contains `"rag_record_chain_orphan"` and that `RagRecordChainOrphan` round-trips through `EventLog.emit_internal(...)` / `replay()`. A typo such as `"ragRecordChainOrphan"`, or forgetting `_INTERNAL_CLASSES`, must fail.
- [ ] **AC-12 - S1-04 field-shape lock.** A small regression test or fixture assertion verifies the verifier reads `record.provenance.event_chain_head` and **does not** reference `record.provenance.record_chain_head`, `record.provenance.model_id`, `record.provenance.embedding_dim`, or any other field removed by S1-04's hardened contract. A simple AST test over `provenance.py` is sufficient: those stale attribute names must not appear.

## Implementation outline

1. **Create `src/codegenie/rag/provenance.py`:**
   ```python
   from __future__ import annotations

   from typing import Protocol, runtime_checkable

   from codegenie.rag.models import SolvedExample
   from codegenie.types.identifiers import ChainHead


   @runtime_checkable
   class SpanningChainLog(Protocol):
       """Minimal read-only view of spanning event-log chain heads.

       Phase 3's event-log infrastructure, or a thin Phase-4 adapter over it,
       satisfies this Protocol implicitly. Keep the surface minimal: final-design
       Component 11 chose appearance-in-log, not segment proof.
       """

       def contains_chain_head(self, head: ChainHead) -> bool: ...


   def verify(record: SolvedExample, spanning_log: SpanningChainLog) -> bool:
       """Return True iff record.provenance.event_chain_head is present in the
       spanning log. Pure predicate; caller owns exclusion + event emission."""
       head = record.provenance.event_chain_head
       if not head:
           return False
       return spanning_log.contains_chain_head(head)
   ```
   No local import from `models.py`, no `RecordProvenance.verify` staticmethod, and no event-log dependency.
2. **Register `RagRecordChainOrphan` in `src/codegenie/plugins/events.py`:**
   - Add the Pydantic class beside the other workflow-internal event classes.
   - Add it to `WorkflowInternalEvent = Annotated[...]`, `_INTERNAL_CLASSES`, and `__all__`.
   - Keep it internal and give it no `prev_hash`; `EventLog.emit_internal(...)` is the write path.
3. **Unit tests for the predicate:**
   - `tests/unit/rag/test_provenance_verify.py` covers AC-1, AC-2, AC-4, AC-5, AC-6, AC-7, and AC-12.
   - `tests/property/test_provenance_verify_membership_property.py` covers AC-8.
   - Extend `tests/fixtures/rag/fake_solved_example.py` (from S4-03/S4-04) to accept `event_chain_head: str = "a" * 64` and populate `RecordProvenance.event_chain_head`. Do **not** add `record_chain_head` to `RecordProvenance`.
4. **Event tests:**
   - Extend `tests/unit/plugins/test_events.py` for AC-11. Mirror the existing event-union tests: schema discriminator mapping contains the event type, `emit_internal` accepts the registered class, and `replay()` returns the typed instance.
   - Add `tests/integration/test_phase4_provenance_orphan_emit.py` for AC-9. Use a caller shim, not the real retriever; S5-01 owns retriever composition.

## TDD plan - red / green / refactor

### Red - write the failing tests first

Test file: `tests/unit/rag/test_provenance_verify.py`

```python
from __future__ import annotations

import inspect
from unittest.mock import Mock

from codegenie.rag.provenance import SpanningChainLog, verify
from codegenie.types.identifiers import ChainHead
from tests.fixtures.rag.fake_solved_example import make_solved_example


KNOWN = ChainHead("a" * 64)
FORGED = ChainHead("b" * 64)


def test_verify_returns_true_when_chain_head_in_spanning_log() -> None:
    """Edge case #14 + final-design Component 11: appearance-in-log is the
    chain-verification contract. Catches always-True and always-False mutants."""
    record = make_solved_example(id_="a" * 64, event_chain_head=str(KNOWN))
    log = Mock(spec=SpanningChainLog)
    log.contains_chain_head.side_effect = lambda h: h == KNOWN

    assert verify(record, log) is True
    log.contains_chain_head.assert_called_once_with(KNOWN)


def test_verify_returns_false_when_chain_head_absent() -> None:
    """Forged or chain-orphan record case - the load-bearing security property."""
    record = make_solved_example(id_="b" * 64, event_chain_head=str(FORGED))
    log = Mock(spec=SpanningChainLog)
    log.contains_chain_head.return_value = False

    assert verify(record, log) is False
    log.contains_chain_head.assert_called_once_with(FORGED)


def test_verify_empty_chain_head_returns_false_without_log_call() -> None:
    """Defense in depth: direct NewType casts can forge an empty ChainHead even
    though S1-01's smart constructor rejects it."""
    record = make_solved_example(id_="c" * 64, event_chain_head=str(KNOWN))
    forged_provenance = record.provenance.model_copy(
        update={"event_chain_head": ChainHead("")}
    )
    forged_record = record.model_copy(update={"provenance": forged_provenance})
    log = Mock(spec=SpanningChainLog)

    assert verify(forged_record, log) is False
    log.contains_chain_head.assert_not_called()


def test_verify_has_no_event_log_or_io_dependency() -> None:
    """The verifier is the functional core. Caller owns EventLog emission."""
    src = inspect.getsource(verify)
    forbidden = [
        "EventLog",
        "emit_internal",
        "emit_spanning",
        "open(",
        "Path(",
        "os.",
        "subprocess.",
        "socket.",
    ]
    assert all(token not in src for token in forbidden)
```

Why it fails: `codegenie.rag.provenance` does not exist; `make_solved_example` does not accept `event_chain_head=` yet.

### Follow-on tests

- `tests/property/test_provenance_verify_membership_property.py` (AC-8): generate record heads and known-head sets; assert the membership equality and exactly-one log lookup for non-empty heads.
- `tests/unit/plugins/test_events.py::test_rag_record_chain_orphan_is_internal_event` (AC-11): class appears in the `WorkflowInternalEvent` discriminator mapping, constructs with typed fields, emits through `emit_internal`, and replays as `RagRecordChainOrphan`.
- `tests/integration/test_phase4_provenance_orphan_emit.py` (AC-9): caller shim emits once for a forged record and continues to the valid record.
- `tests/unit/rag/test_provenance_verify.py::test_verify_does_not_reference_stale_recordprovenance_fields` (AC-12): AST/source scan forbids `record_chain_head`, `model_id`, and `embedding_dim` in `provenance.py`.

### Green - make it pass

- Create `src/codegenie/rag/provenance.py` with the `SpanningChainLog` Protocol and the `verify` function.
- Extend `tests/fixtures/rag/fake_solved_example.py` to accept an `event_chain_head=str` kwarg that populates `RecordProvenance.event_chain_head`.
- Register `RagRecordChainOrphan` in `src/codegenie/plugins/events.py`, including the union and `_INTERNAL_CLASSES` rows.

### Refactor

- Module docstring with the full edge case #14 framing.
- Keep `verify` as a three-branch predicate (`head = ...`, `if not head: return False`, `return spanning_log.contains_chain_head(head)`). Do not add batching or event emission here.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/provenance.py` | `SpanningChainLog` Protocol + `verify(record, spanning_log)` pure function. |
| `src/codegenie/plugins/events.py` | Add `RagRecordChainOrphan` as a `WorkflowInternalEvent` variant. |
| `tests/fixtures/rag/fake_solved_example.py` | Extend with `event_chain_head=` kwarg. |
| `tests/unit/rag/test_provenance_verify.py` | Red test + AC follow-ons. |
| `tests/property/test_provenance_verify_membership_property.py` | AC-8 Hypothesis membership property. |
| `tests/unit/plugins/test_events.py` | AC-11 event registration + replay test. |
| `tests/integration/test_phase4_provenance_orphan_emit.py` | AC-9 caller-emission smoke. |

## Out of scope

- **Embedding-model mismatch exclusion (`RagRecordModelMismatch`)** - S5-03 (semantically a sibling to chain-orphan but lives on the read-side band classifier).
- **Wiring the verifier into the retriever** - S5-01 (this story exposes the function; S5-01 calls it in a loop).
- **Real Phase-3 `SpanningChainLog` adapter** - Phase-3 owns the event-log impl; this story takes the Protocol via injection. A small Phase-4 adapter (`src/codegenie/rag/spanning_log_adapter.py`) lands in S5-01 if Phase 3's surface needs translation; for now, the fake protocol proves the contract.
- **Record-id-bound provenance proof.** Final-design §Component 11 chose head-presence verification, not `(record_id, chain_head)` proof. If a later story needs a stronger pair-bound proof, that is an ADR / final-design amendment, not an S4-05 implementation choice.
- **Chain-segment proof (cryptographic Merkle path)** - explicitly rejected by final-design §Component 11 (critic §[S]§1 - machine-local heads break across worker restarts; appearance-in-log is the right abstraction for Phase 9 Temporal).
- **`RagRecordChainOrphan` log-rotation / replay policy** - Phase 9 Temporal concerns. This story only defines the event and proves the caller can emit it.

## Notes for the implementer

### §1 - Why `verify` is module-level only

`RecordProvenance.verify(record, spanning_log)` is the **prose contract** arch §Component 7 names, but S1-04 hardened `RecordProvenance` as a frozen Pydantic data model. Adding a staticmethod alias to `models.py` would mix data shape with verification policy and create a circular import (`models.py` -> `provenance.py` -> `models.py`). The implementation surface is therefore `codegenie.rag.provenance.verify(record, spanning_log)`. Mention the arch shorthand in the function docstring; do not mutate the model.

### §2 - `SpanningChainLog` Protocol scope discipline

The Protocol has **one method**. The temptation is to expose `current_head()` or `get_chain_segment(head) -> ChainSegment` for "richer verification." Resist it. Final-design §Component 11 explicitly rejects chain-segment proofs; this story's contract is only membership. The event's `spanning_log_head` is caller-supplied triage context, not a verifier dependency.

### §3 - Where `RagRecordChainOrphan` is emitted, not here

The verifier is pure (AC-6); event emission is the caller's job. This split keeps `verify` testable as a functional core (no event-sink mocks in `tests/unit/rag/test_provenance_verify.py`) and centralizes event emission in S5-01's retriever where the event has full context. The integration test (AC-9) builds a thin caller shim that exercises the emission discipline through the real `EventLog.emit_internal(...)` API.

### §4 - Event-log API is `codegenie.plugins.events`

Do not import `EventLog` from `codegenie.audit` and do not create a parallel `rag/events.py` registry. The shipped event source is `src/codegenie/plugins/events.py`: Pydantic variants discriminated by `event_type`, plus `WorkflowInternalEvent`, `_INTERNAL_CLASSES`, and `EventLog.emit_internal(...)`. This is the same stale-API trap S2-01/S2-02/S2-05 were hardened against.

### §5 - Hypothesis strategy for chain heads

For AC-8's property test, generate heads from `text(alphabet="abcdef0123456789", min_size=64, max_size=64)`. The fake `SpanningChainLog` precomputes a `set[ChainHead]`; `contains_chain_head` is `head in known_set`. The property is: for every `(record, known_set)`, `verify(record, log) == (record.provenance.event_chain_head in known_set)`.

### §6 - Don't extend `verify` to multi-record batches

The temptation is to add `def verify_all(records, log) -> list[bool]` for batch performance. Don't. The hot path (S5-01) iterates `top_k=5` records; a Python-level loop is simpler and keeps event emission per excluded record where the caller can attach query context. Batching gives nothing.

### §7 - `RecordProvenance` field naming reminder

S1-04 lands `RecordProvenance` with exactly:

```python
workflow_id: WorkflowId
event_chain_head: ChainHead
created_at: datetime
signing_method: Literal["hmac_sha256_chain", "operator_attestation"]
```

This story consumes `event_chain_head`. Do not reference stale draft fields like `record_chain_head`, `model_id`, `embedding_dim`, `trust_outcome_passed`, or `confidence` on `RecordProvenance`. `SolvedExample.embedding_model` exists on the outer record; `record_chain_head` / manifest content heads are S4-04 store concepts, not the retrieval-side event-log anchor.
