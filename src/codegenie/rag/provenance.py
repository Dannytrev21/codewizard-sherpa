"""Phase-4 S4-05 — chain-orphan exclusion (read-side discipline).

Final-design §Component 11 frames the contract:

    "the record's chain head must appear somewhere in the spanning chain log"

— NOT a chain-segment Merkle proof, NOT a ``(record_id, chain_head)`` pair-
bound proof. Critic §[S] §1 rejected machine-local chain segments because
heads break across worker restarts; appearance-in-log is the right
abstraction for Phase-9 Temporal.

This module ships the pure-predicate kernel of that contract:

- :class:`SpanningChainLog` — one-method ``@runtime_checkable`` Protocol.
- :func:`verify` — module-level pure function over
  ``(record, spanning_log)``. Returns ``True`` iff
  ``record.provenance.event_chain_head`` appears in the spanning log.

**Edge case #14.** A chain-orphan is excluded from the result set and a
:class:`~codegenie.plugins.events.RagRecordChainOrphan` event is emitted —
the workflow **does not halt**. A broken or unreadable spanning event log
is a different integrity failure owned by Phase-3's event-log verifier,
not by this predicate. The arch §Component 7 prose contract names this as
``RecordProvenance.verify(record, spanning_log) -> bool``; the
implementation surface is module-level (not a staticmethod alias) so
``codegenie.rag.models`` stays a frozen data module and no
``models.py`` → ``provenance.py`` → ``models.py`` import cycle can form.

**Exclusion + event emission is the caller's job.** The retriever (S5-01)
calls ``verify`` per candidate, drops orphans, and emits
``RagRecordChainOrphan`` through
:meth:`~codegenie.plugins.events.EventLog.emit_internal`. Keeping that
discipline outside this module makes the predicate trivially testable
(no event-sink mocks) and centralises emission where the event has full
query context.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from codegenie.rag.models import SolvedExample
from codegenie.types.identifiers import ChainHead


@runtime_checkable
class SpanningChainLog(Protocol):
    """Minimal read-only view of spanning event-log chain heads.

    Phase-3's event-log infrastructure (or a Phase-4 adapter over it,
    landed by S5-01 if translation is needed) satisfies this Protocol
    implicitly. The surface is intentionally one method: final-design
    §Component 11 chose appearance-in-log, not segment proof.
    """

    def contains_chain_head(self, head: ChainHead) -> bool: ...


def verify(record: SolvedExample, spanning_log: SpanningChainLog) -> bool:
    """Return ``True`` iff ``record.provenance.event_chain_head`` appears
    in ``spanning_log``.

    Pure predicate: no I/O, no mutation, no event emission. The caller
    (S5-01 retriever) excludes orphans and emits
    :class:`~codegenie.plugins.events.RagRecordChainOrphan`.

    An empty ``event_chain_head`` returns ``False`` without consulting
    the log — defence in depth against a forged
    ``record.model_copy(update={"event_chain_head": ChainHead("")})``
    bypass of S1-01's smart-constructor non-empty invariant.
    """
    head = record.provenance.event_chain_head
    if not head:
        return False
    return spanning_log.contains_chain_head(head)


__all__ = ("SpanningChainLog", "verify")
