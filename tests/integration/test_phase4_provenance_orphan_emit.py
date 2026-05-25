"""Phase-4 S4-05 AC-9 — caller-emission smoke test.

The verifier is a pure predicate (`tests/unit/rag/test_provenance_verify.py`).
This integration test proves the **emission discipline** the retriever owns
in S5-01: when ``verify`` returns ``False`` the caller emits
``RagRecordChainOrphan`` via the real
:meth:`codegenie.plugins.events.EventLog.emit_internal` and **continues**
processing the next candidate. Replay must yield exactly one event with
the matching ``record_id`` / ``record_event_chain_head`` /
``spanning_log_head`` triple.

The test deliberately does not call
:meth:`codegenie.rag.store.SolvedExampleStore.query` because that returns
a :class:`~codegenie.rag.models.RetrievalOutcome`, not a raw record list —
the retriever-shaped caller shim mirrors what S5-01 will own.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from codegenie.plugins.events import EventLog, RagRecordChainOrphan
from codegenie.rag.models import SolvedExample
from codegenie.rag.provenance import SpanningChainLog, verify
from codegenie.types.identifiers import ChainHead, EventId, SolvedExampleId, WorkflowId
from tests.fixtures.rag.fake_solved_example import make_solved_example

_KNOWN = ChainHead("a" * 64)
_FORGED = ChainHead("b" * 64)
_SPAN_HEAD = ChainHead("c" * 64)


def _wf() -> WorkflowId:
    return WorkflowId("01HORPHAN0000000000000000000")


def _now() -> datetime:
    return datetime(2026, 5, 25, 12, 0, 0, tzinfo=UTC)


class _FakeSpanningLog:
    """One-head ``SpanningChainLog`` impl backed by a known head."""

    def __init__(self, known: ChainHead) -> None:
        self._known = known

    def contains_chain_head(self, head: ChainHead) -> bool:
        return head == self._known


def _retriever_caller_shim(
    *,
    candidates: Sequence[SolvedExample],
    spanning_log: SpanningChainLog,
    spanning_log_head: ChainHead,
    event_log: EventLog,
    workflow_id: WorkflowId,
) -> list[SolvedExample]:
    """Caller-emission discipline S5-01 will own.

    Iterates the candidate sequence; on chain-orphan emits
    ``RagRecordChainOrphan`` once and continues. Returns the kept records.
    """
    kept: list[SolvedExample] = []
    next_event_seq = 1
    for record in candidates:
        if verify(record, spanning_log):
            kept.append(record)
            continue
        event_log.emit_internal(
            RagRecordChainOrphan(
                event_id=EventId(f"01HORPHANEMIT{next_event_seq:013d}"),
                workflow_id=workflow_id,
                timestamp=_now(),
                record_id=record.id,
                record_event_chain_head=record.provenance.event_chain_head,
                spanning_log_head=spanning_log_head,
            )
        )
        next_event_seq += 1
    return kept


def test_chain_orphan_emits_once_and_processing_continues(tmp_path: Path) -> None:
    """AC-9 — forged record excluded + event emitted + valid record kept."""
    workflow_id = _wf()
    event_log = EventLog(root=tmp_path, workflow_id=workflow_id, clock=_now)
    spanning_log = _FakeSpanningLog(_KNOWN)

    forged_record = make_solved_example(id_="forged-record-id", event_chain_head=str(_FORGED))
    valid_record = make_solved_example(id_="valid-record-id", event_chain_head=str(_KNOWN))

    kept = _retriever_caller_shim(
        candidates=[forged_record, valid_record],
        spanning_log=spanning_log,
        spanning_log_head=_SPAN_HEAD,
        event_log=event_log,
        workflow_id=workflow_id,
    )

    # Valid record survived; forged was excluded — processing continued.
    assert len(kept) == 1
    assert kept[0].id == SolvedExampleId("valid-record-id")

    event_log.flush()
    replayed = list(event_log.replay())
    orphan_events = [e for e in replayed if isinstance(e, RagRecordChainOrphan)]
    assert len(orphan_events) == 1, replayed

    orphan = orphan_events[0]
    assert orphan.event_type == "rag_record_chain_orphan"
    assert orphan.record_id == SolvedExampleId("forged-record-id")
    assert orphan.record_event_chain_head == _FORGED
    assert orphan.spanning_log_head == _SPAN_HEAD
    assert orphan.workflow_id == workflow_id
