# Story S4-05 — `RecordProvenance.verify(record, spanning_log) -> bool` + `RagRecordChainOrphan` emission

**Step:** Step 4 — Ship RAG substrate kernel: Embedder + SolvedExampleStore + record provenance
**Status:** Ready
**Effort:** S
**Depends on:** S4-04 (canonical YAML + manifest in place — the manifest's `chain_head` is the store's content head; per-record provenance is a separate chain in the spanning event log)
**ADRs honored:** ADR-0016 (chain verification is part of read-side discipline), final-design §Component 11 — "the record's chain head must appear somewhere in the spanning chain log"

## Context

Each `SolvedExample` carries a `provenance: RecordProvenance` field (S1-04). The provenance's `event_chain_head: ChainHead` records the **spanning-event-log chain head** at the moment the record was witnessed — i.e., the harvest event's enclosing chain head. At retrieval time (S5-01), every candidate record must be **chain-verified**: the record's `event_chain_head` must appear somewhere in the **current spanning chain log**. A record whose chain head is absent is a **chain-orphan** — typical causes:

- A forged record (RAG-poisoning attempt) whose `event_chain_head` was fabricated.
- A record harvested by a worker whose event-log was lost (machine crash, log rotation missed a window).
- A record imported from a different deployment whose spanning log is not the current one.

Final-design §Component 11 names this the simpler "the record's chain head must appear somewhere in the spanning chain log" verification — **not** a chain-segment proof (which would require maintaining per-record chain segments and break across worker restarts). The security guarantee is "this record's harvest event is in *our* event log, not somewhere else." Edge case #14 → exclude record + emit `RagRecordChainOrphan`; **never halts a workflow**.

This story lands the pure verifier at `src/codegenie/rag/provenance.py` (the path arch §System view names) + the `RagRecordChainOrphan` event class. S5-01 wires the verifier into the retriever; S7-09's adversarial test (`test_rag_poisoning_chain_orphan.py`) proves a forged chain head is excluded + event-logged.

The verifier is a **pure function** over the `SolvedExample` and a `spanning_log: SpanningChainLog` abstraction. `SpanningChainLog` is a minimal Protocol with one method: `def contains_chain_head(self, head: ChainHead) -> bool`. The actual spanning-log implementation lives in Phase 3's event-log infrastructure; this story takes it via injection.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 7 — SolvedExampleStore` — `RecordProvenance` is a dependency; chain-orphan is a typed failure mode.
  - `../phase-arch-design.md §Component 9 — SolvedExampleRetriever` (line 605) — "Chain-orphan record excluded + `RagRecordChainOrphan` emitted. Returns `RagMiss` rather than raising when the store is empty."
  - `../phase-arch-design.md §Edge case #14` — chain-orphan detection: `provenance.event_chain_head` not in spanning log → `RecordProvenance.verify` → exclude record from result set + emit `RagRecordChainOrphan`; **continue** (never halts).
  - `../phase-arch-design.md §"Logging strategy"` (line 825) — `RagRecordChainOrphan` is a WARN event.
  - `../phase-arch-design.md §"Adversarial tests"` (line 1006) — `tests/adversarial/test_rag_poisoning_chain_orphan.py` is the eventual security test (S7-09 ships).
- **Phase ADRs:**
  - `../ADRs/0016-chromadb-embedded-yaml-canonical-store.md` §Consequences — `RecordProvenance.verify` is the read-side discipline that protects against poisoning at retrieval time.
- **Source design:**
  - `../final-design.md §Component 11 — SolvedExampleRetriever + retrieval-side discipline` (line 445) — the simpler "appears in spanning log" verification (chain-segment proof rejected as critic §"[S] §1" hidden assumption).
- **Existing code (precedent to mirror):**
  - Phase-3 event-log emission patterns (whichever module Phase 3 ships for `EventLog` / `spanning-event-log` writers) — mirror the event payload shape and the WARN-level emission discipline. If Phase 3's event-log is not yet sufficiently shipped for this dependency, this story takes the `SpanningChainLog` Protocol via injection and S5-01 wires the real impl.
  - `src/codegenie/types/identifiers.py` for `ChainHead`.

## Goal

Ship `RecordProvenance.verify(record: SolvedExample, spanning_log: SpanningChainLog) -> bool` as a pure function at `src/codegenie/rag/provenance.py`, plus the `SpanningChainLog` Protocol it consumes and the `RagRecordChainOrphan` typed event class; verifier returns `True` iff `record.provenance.event_chain_head` appears in the spanning log (else `False`); never raises; the caller (S5-01 retriever) is responsible for emitting `RagRecordChainOrphan` on `False`.

## Acceptance criteria

- [ ] **AC-1 — `RecordProvenance.verify` signature.** `src/codegenie/rag/provenance.py` exports a **module-level function** (not a method on the Pydantic model — keep the model pure data; verification is policy):
    ```python
    def verify(record: SolvedExample, spanning_log: SpanningChainLog) -> bool: ...
    ```
    Returns `True` iff `spanning_log.contains_chain_head(record.provenance.event_chain_head)`; **never raises** on a malformed `record.provenance` (Pydantic already validated at construction). The module also exports a class-method-style alias `RecordProvenance.verify(record, spanning_log)` for naming-symmetry with arch §Component 7's `RecordProvenance.verify(record, spanning_log) -> bool` text — implemented as a `@staticmethod` on the `RecordProvenance` model that delegates to the module function.
- [ ] **AC-2 — `SpanningChainLog` Protocol.** `src/codegenie/rag/provenance.py` (or `src/codegenie/rag/event_log.py` — pick one and document the choice; **prefer** `provenance.py` so the verifier and its dependency live together) declares:
    ```python
    @runtime_checkable
    class SpanningChainLog(Protocol):
        def contains_chain_head(self, head: ChainHead) -> bool: ...
    ```
    One method. The Phase-3 event-log implementation (or a Phase-4 thin adapter over it) satisfies this Protocol implicitly — `isinstance(phase3_event_log, SpanningChainLog) is True` after the adapter ships.
- [ ] **AC-3 — `RagRecordChainOrphan` event class.** `src/codegenie/rag/events.py` exports a frozen Pydantic model:
    ```python
    class RagRecordChainOrphan(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")
        kind: Literal["rag_record_chain_orphan"] = "rag_record_chain_orphan"
        record_id: SolvedExampleId
        record_chain_head: ChainHead   # the head that wasn't found
        spanning_log_head: ChainHead   # the current spanning head, for triage
    ```
    The event is **emitted by the caller** (S5-01 retriever), not by the verifier — keep `verify` pure.
- [ ] **AC-4 — Verifier returns True on present chain head.** Given a fake `SpanningChainLog` whose `contains_chain_head(h)` returns `h == ChainHead("known-head-001")`, a record whose `provenance.event_chain_head == ChainHead("known-head-001")` returns `True`.
- [ ] **AC-5 — Verifier returns False on absent chain head.** Given the same fake log, a record whose `provenance.event_chain_head == ChainHead("forged-head-xyz")` returns `False`. (S7-09's adversarial test reuses this fixture shape against the retriever.)
- [ ] **AC-6 — Verifier is pure.** A unit test asserts that `verify` does not mutate `record`, does not call any side-effect-producing method on `spanning_log` beyond `contains_chain_head`, and does not access network/disk/env. Mock the `spanning_log` with `unittest.mock.Mock(spec=SpanningChainLog)`; assert `contains_chain_head` called exactly once with `record.provenance.event_chain_head` as the only argument.
- [ ] **AC-7 — Verifier handles None or empty chain head defensively.** Although `RecordProvenance.event_chain_head: ChainHead` is non-`None` by S1-04 schema, an empty-string Newtype value (which the Newtype's smart constructor should reject at S1-01 — but defense in depth) returns `False`. Test pins: `record.provenance.event_chain_head = ChainHead("")` → `verify(...)` returns `False` without calling `spanning_log.contains_chain_head` (early-return optimization that doubles as a paranoia guard).
- [ ] **AC-8 — `RecordProvenance.verify(record, spanning_log)` method form works identically.** Both `provenance.verify(record, spanning_log)` (module function) and `RecordProvenance.verify(record, spanning_log)` (staticmethod alias) return the same value for the same inputs across a Hypothesis-driven property test (50 random records × 2 fake logs).
- [ ] **AC-9 — `RagRecordChainOrphan` emission integration smoke test.** A thin integration test in `tests/integration/test_phase4_provenance_orphan_emit.py`:
    - Construct a fake retriever-like caller that loops `await store.query(...) -> records`, then for each record calls `verify(record, spanning_log)`; on `False` emits `RagRecordChainOrphan` to a captured event sink.
    - With a forged record (chain head not in fake log), assert the event sink received exactly one `RagRecordChainOrphan` with matching `record_id` and `record_chain_head`.
    - **Continues** the loop (never halts) — the next record (with a valid chain head) is still processed and counted.
- [ ] **AC-10 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean.

## Implementation outline

1. **Create `src/codegenie/rag/provenance.py`:**
   ```python
   from __future__ import annotations

   from typing import Protocol, runtime_checkable

   from codegenie.rag.models import SolvedExample  # (S1-04 location)
   from codegenie.types.identifiers import ChainHead


   @runtime_checkable
   class SpanningChainLog(Protocol):
       """Minimal read-only view of the spanning event log's chain heads.
       Phase 3's event-log infrastructure (or a thin Phase-4 adapter) satisfies
       this Protocol implicitly. Keep the Protocol surface minimal — Open/Closed
       at the file boundary."""

       def contains_chain_head(self, head: ChainHead) -> bool: ...


   def verify(record: SolvedExample, spanning_log: SpanningChainLog) -> bool:
       """Return True iff `record.provenance.event_chain_head` appears in the
       spanning log. Never raises. Pure — does not mutate `record` or perform I/O
       beyond delegating to `spanning_log.contains_chain_head`.

       Edge case #14: chain-orphan handling.  Final-design §Component 11 chose
       'simple appearance in spanning log' over 'chain-segment proof' (critic §[S]§1
       hidden-assumption resolution — machine-local chain heads break across worker
       restarts; appearance-in-log generalizes cleanly to Phase 9 Temporal).
       """
       head = record.provenance.event_chain_head
       if not head:
           return False  # defense in depth — S1-01 smart-constructor should already reject
       return spanning_log.contains_chain_head(head)
   ```
2. **`RecordProvenance.verify` staticmethod alias:** in `src/codegenie/rag/models.py` (or wherever S1-04 lands `RecordProvenance`), add:
   ```python
   class RecordProvenance(BaseModel):
       model_config = ConfigDict(frozen=True, extra="forbid")
       solved_example_id: SolvedExampleId
       workflow_id: WorkflowId
       event_chain_head: ChainHead
       trust_outcome_passed: bool
       confidence: Literal["high", "medium", "low"]
       model_id: ModelId
       embedding_dim: int
       harvested_at: datetime
       record_chain_head: ChainHead

       @staticmethod
       def verify(record: "SolvedExample", spanning_log: "SpanningChainLog") -> bool:
           from codegenie.rag.provenance import verify as _verify
           return _verify(record, spanning_log)
   ```
   The local import avoids the circular dependency (`models.py` → `provenance.py` → `models.py`); the `TYPE_CHECKING` guard on the parameter types makes mypy happy.
3. **`RagRecordChainOrphan` event class:** in `src/codegenie/rag/events.py`. This file is new; subsequent events (`RagRecordModelMismatch`, `SolvedExampleHarvested`, `HarvestSkipped`, `StoreWriteContention` as an event) live here too. For this story, only `RagRecordChainOrphan` ships.
4. **Tests:**
   - `tests/unit/rag/test_provenance_verify.py` — AC-1, AC-4, AC-5, AC-6, AC-7, AC-8.
   - `tests/property/test_provenance_verify_method_alias_equivalence.py` — AC-8 Hypothesis property.
   - `tests/integration/test_phase4_provenance_orphan_emit.py` — AC-9.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/unit/rag/test_provenance_verify.py`

```python
from __future__ import annotations

from unittest.mock import Mock

import pytest

from codegenie.rag.provenance import SpanningChainLog, verify
from codegenie.types.identifiers import ChainHead
from tests.fixtures.rag.fake_solved_example import make_solved_example


def test_verify_returns_true_when_chain_head_in_spanning_log() -> None:
    """Edge case #14 + final-design §Component 11: appearance-in-log is the
    chain-verification contract.  Catches "always-True" and "always-False" mutants."""
    record = make_solved_example(id_="ex-001", chain_head="known-head-001")
    log = Mock(spec=SpanningChainLog)
    log.contains_chain_head.side_effect = lambda h: h == ChainHead("known-head-001")

    assert verify(record, log) is True
    log.contains_chain_head.assert_called_once_with(ChainHead("known-head-001"))


def test_verify_returns_false_when_chain_head_absent() -> None:
    """Forged or chain-orphan record case — the load-bearing security property."""
    record = make_solved_example(id_="ex-forged", chain_head="forged-head-xyz")
    log = Mock(spec=SpanningChainLog)
    log.contains_chain_head.return_value = False

    assert verify(record, log) is False
    # The caller (S5-01) is responsible for emitting RagRecordChainOrphan; the
    # verifier itself stays pure — no event emission inside `verify`.
```

Why it fails: `codegenie.rag.provenance` does not exist; `make_solved_example` does not accept `chain_head=` kwarg yet.

### Green — make it pass

- Create `src/codegenie/rag/provenance.py` with the `SpanningChainLog` Protocol and the `verify` function.
- Extend `tests/fixtures/rag/fake_solved_example.py` (from S4-03) to accept a `chain_head=str` kwarg that populates `RecordProvenance.event_chain_head`.

### Refactor

- Module docstring with the full edge case #14 framing.
- The empty-string defense (AC-7) added as an explicit early-return.

### Required follow-on tests

- `test_verify_empty_chain_head_returns_false_without_log_call` (AC-7) — `record.provenance.event_chain_head = ChainHead("")`; assert `verify(...)` returns `False` AND `log.contains_chain_head.call_count == 0`.
- `test_verify_does_not_mutate_record` (AC-6) — record before/after `verify` is `==` (Pydantic equality; the model is frozen anyway, so this catches a future mutability regression).
- `test_recordprovenance_staticmethod_alias_equivalence` (AC-8) — `RecordProvenance.verify(r, log)` returns the same value as `provenance.verify(r, log)` for a Hypothesis-generated record × `log` pair (50 cases).
- `test_orphan_emission_integration` (AC-9) — `tests/integration/test_phase4_provenance_orphan_emit.py` per the AC body; verifies the emission contract that S5-01 will satisfy.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/rag/provenance.py` | `SpanningChainLog` Protocol + `verify(record, spanning_log)` pure function. |
| `src/codegenie/rag/models.py` | Add `RecordProvenance.verify` staticmethod alias (S1-04 ships the `RecordProvenance` model; this story adds the verify alias). |
| `src/codegenie/rag/events.py` | New module; `RagRecordChainOrphan` event class lands first. |
| `tests/fixtures/rag/fake_solved_example.py` | Extend with `chain_head=` kwarg. |
| `tests/unit/rag/test_provenance_verify.py` | Red test + AC follow-ons. |
| `tests/property/test_provenance_verify_method_alias_equivalence.py` | AC-8 Hypothesis property. |
| `tests/integration/test_phase4_provenance_orphan_emit.py` | AC-9 emission integration smoke. |

## Out of scope

- **Embedding-model mismatch exclusion (`RagRecordModelMismatch`)** — S5-03 (semantically a sibling to chain-orphan but lives on the read-side band classifier).
- **Wiring the verifier into the retriever** — S5-01 (this story exposes the function; S5-01 calls it in a loop).
- **Real Phase-3 `SpanningChainLog` adapter** — Phase-3 owns the event-log impl; this story takes the Protocol via injection. A small Phase-4 adapter (`src/codegenie/rag/spanning_log_adapter.py`) lands in S5-01 if Phase 3's surface needs translation; for now, the fake mock proves the contract.
- **Chain-segment proof (cryptographic Merkle path)** — explicitly rejected by final-design §Component 11 (critic §[S]§1 — machine-local heads break across worker restarts; appearance-in-log is the right abstraction for Phase 9 Temporal).
- **`RagRecordChainOrphan` log-rotation / replay** — Phase 9 Temporal concerns.

## Notes for the implementer

### §1 — Why `verify` is a module function and a staticmethod, both

`RecordProvenance.verify(record, spanning_log)` is the **prose contract** arch §Component 7 names (and final-design §Component 11). The naming-symmetry matters for the reader who lands on the arch doc. But making `verify` an instance method on `RecordProvenance` would force the verifier to be a method on the record itself (`record.provenance.verify(spanning_log)`) — that ties record-data to verification-policy and breaks the rule that the Pydantic model is **just data**. The compromise: module function (the actual impl) + `@staticmethod` alias (the documented surface). Both forms work identically (AC-8 pins this), and reviewers can use whichever reads better at the callsite.

### §2 — `SpanningChainLog` Protocol scope discipline

The Protocol has **one method**. The temptation is to also expose `get_chain_segment(head) -> ChainSegment` for "richer verification." **Resist** — final-design §Component 11 explicitly rejects chain-segment proofs (critic §[S]§1). One method, one contract. If Phase 9 Temporal needs a richer surface, an ADR amendment adds a method via extension (Open/Closed). Adding speculative methods now would force Phase 3's event-log adapter to implement them for no current consumer.

### §3 — Where `RagRecordChainOrphan` is emitted, not here

The verifier is pure (AC-6); event emission is the caller's job. This split keeps `verify` testable as a pure function (no event-sink mocks in `tests/unit/rag/test_provenance_verify.py`) and centralizes event emission in S5-01's retriever where the event has full context (the query that triggered it, the partition that was searched, etc.). The integration test (AC-9) builds a thin caller-shim that exercises the emission discipline; this is the testable contract S5-01 must honor.

### §4 — Hypothesis strategy for chain heads

For AC-8's property test, generate `record.provenance.event_chain_head` from `text(alphabet="abcdef0123456789", min_size=64, max_size=64)` (BLAKE3-hex-shaped). The fake `SpanningChainLog` precomputes a set of "known heads"; `contains_chain_head` is `head in known_set`. The property is: for every (record, log) pair, `verify(record, log) == (record.provenance.event_chain_head in known_set)`.

### §5 — Don't extend `verify` to multi-record batches

The temptation is to add `def verify_all(records, log) -> list[bool]` for batch performance. **Don't.** The hot path (S5-01) iterates `top_k=5` records — a Python-level for-loop is faster than a SQL roundtrip to the event log per record only if the event log isn't already memoizing. Phase 3's event log will internally memoize the spanning-log chain-head set (one in-memory `set[ChainHead]`); each `contains_chain_head` is O(1). Batching gives nothing. Surface per Rule 2.

### §6 — `RecordProvenance` field naming reminder

S1-04 lands the `RecordProvenance` Pydantic model with these fields (per the Step-4 cross-cutting reminders in the planner manifest):

```python
solved_example_id: SolvedExampleId
workflow_id: WorkflowId
trust_outcome_passed: bool
confidence: Literal["high", "medium", "low"]
model_id: ModelId
embedding_dim: int
harvested_at: datetime
record_chain_head: ChainHead   # the BLAKE3 chain-of-hashes per record
event_chain_head: ChainHead    # the spanning-log head at harvest time
```

This story consumes `event_chain_head` (the field `verify` checks against `spanning_log`). `record_chain_head` is per-record chain-of-hashes (S4-04 consumes for the store digest); they are **two different chain heads** living on the same `RecordProvenance` record. If a reviewer is confused, the docstrings on each field name the distinction explicitly.
