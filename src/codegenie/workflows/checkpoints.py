"""Phase 6 S2-01 — replay-safe checkpoint store port + closed boundary catalog.

This module is the Open/Closed kernel of the checkpoint substrate
(ADR-0003). The Protocol declared here is the *contract* every adapter
must satisfy; the production SQLite adapter lives in
:mod:`codegenie.workflows.sqlite_checkpoints` and the test-only
in-memory adapter in :mod:`codegenie.workflows.in_memory_checkpoints`.
The Phase-9 Postgres adapter (Phase-9 S5-01) lands additively beside
them — no kernel edit.

Three closed-set constants live here:

* :data:`_SEMANTIC_BOUNDARY_KINDS` — the six
  :data:`~codegenie.workflows.vuln_ledger.LedgerStateKind` values at
  which the orchestrator MUST checkpoint (final-design.md §"Decisions of
  record" item 3 — plan acceptance / patch application / gate result
  retryable arm / escalation / terminal completion). Adding a seventh
  is an ADR-0003 amendment.
* :data:`_MAX_EVENT_BYTES` — the 64 KiB per-event canonical-JSON cap.
  The cap lives at the *store* layer, never the *model* layer:
  ``TransitionEvent`` itself is uncapped so the forensic ``EventLog``
  (Phase-3 S6-01) can carry full evidence; only the checkpoint chain is
  bounded.
* :data:`_GENESIS_CHAIN_HEAD` — the bare-64-hex zero seed for every
  workflow's empty chain (matches the convention pinned by
  ``codegenie.types.parsers.parse_chain_head`` + every existing
  ``ChainHead`` call site).

Disambiguation (S2-01 References §"Disambiguation note"): the
:class:`CheckpointStore` Protocol is **deliberately distinct** from the
Phase-3 :class:`~codegenie.plugins.events.EventStreamSink` Protocol. The
``EventLog`` is the *forensic* two-stream log (provenance gates,
capability mints, RAG harvest); the ``CheckpointStore`` is the
*replay-safe* per-workflow transition chain. Conflating them would
couple the replay-verification path (S2-02) to the forensic-log path
(S6-01). Two ports, two adapter pairs, no shared base — see also the
Anti-refactor block in the S2-01 story.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager
from typing import Final, Protocol, runtime_checkable

from codegenie.types.identifiers import ChainHead, WorkflowId
from codegenie.workflows.vuln_ledger import (
    _TERMINAL_LEDGER_KINDS,
    LedgerStateKind,
    TransitionEvent,
)

__all__ = [
    "CheckpointStore",
]


# ---------------------------------------------------------------------------
# Closed semantic-boundary catalog. Membership is byte-equal to the six
# kinds final-design.md §"Decisions of record" item 3 enumerates. The
# orchestrator (Phase-6 S6-04 precedent + Phase-6 S3-01 subgraph nodes)
# checkpoints ONLY when ``event.next_state_id`` is in this set.
# ---------------------------------------------------------------------------

_SEMANTIC_BOUNDARY_KINDS: Final[frozenset[LedgerStateKind]] = frozenset(
    {
        "plan_ready",
        "patch_applied",
        "gate_failed_retryable",
        "awaiting_human_review",
        "completed",
        "failed_unrecoverable",
    }
)
"""Six-element closed boundary catalog (ADR-0003). Adding a seventh is
an ADR-0003 amendment + an edit to this constant — never a runtime
decoration."""


# Defensive: cross-story consistency with S1-02's terminal partition.
# Terminal states are always boundary states (a workflow that ends MUST
# have a final durable checkpoint). The drift assertion catches the case
# where S1-02 grows a new terminal but this file is not updated.
assert _TERMINAL_LEDGER_KINDS <= _SEMANTIC_BOUNDARY_KINDS, (
    "checkpoints._SEMANTIC_BOUNDARY_KINDS drift — every terminal "
    "LedgerStateKind must be a semantic-boundary kind (ADR-0003 §Consequences)."
)


# ---------------------------------------------------------------------------
# Per-event canonical-JSON byte cap. 64 KiB is conservative — typical
# events are <2 KiB. The cap surfaces accidental evidence inlining (a
# node storing a full RAG cassette as ``triggering_outcome`` rather than
# a BlobDigest reference); see story Notes-for-implementer.
# ---------------------------------------------------------------------------

_MAX_EVENT_BYTES: Final[int] = 65_536


# ---------------------------------------------------------------------------
# Genesis chain head — bare 64-hex zeros (matches the ChainHead newtype
# shape established in Phase-4 + the convention every existing
# ``ChainHead`` call site uses). Adapters seed an empty workflow's
# ``tail_chain_head`` with this value.
# ---------------------------------------------------------------------------

_GENESIS_CHAIN_HEAD: Final[ChainHead] = ChainHead("0" * 64)


# ---------------------------------------------------------------------------
# Directive strings — surface the policy reason on failure so future
# executors don't re-derive the rationale.
# ---------------------------------------------------------------------------

_BOUNDARY_VIOLATION_DIRECTIVE: Final[str] = (
    "Phase-6 checkpoint policy violation. Semantic boundaries are "
    "{plan_ready, patch_applied, gate_failed_retryable, "
    "awaiting_human_review, completed, failed_unrecoverable} (ADR-0003). "
    "The orchestrator attempted to checkpoint at {next_state_id}. If this "
    "is a new boundary, amend ADR-0003 §Decision + _SEMANTIC_BOUNDARY_KINDS. "
    "If this is a non-boundary transition, the orchestrator should log "
    "the transition via the forensic EventLog (Phase-3 S6-01) without "
    "persisting a checkpoint row."
)


_PAYLOAD_TOO_LARGE_DIRECTIVE: Final[str] = (
    "Phase-6 checkpoint payload exceeds the 64 KiB per-event cap "
    "(ADR-0003 §Tradeoffs `Ledger code is slightly more involved than "
    "naïve snapshots` — large evidence is referenced via blob digest, "
    "never inlined). The orchestrator should write large evidence to "
    "the blob-ref store (Phase-9 S3-05) and reference it by BlobDigest "
    "in the transition."
)


# ---------------------------------------------------------------------------
# Boundary policy helper (composition-over-inheritance — a free function,
# called from both adapters). Anti-refactor #1: do NOT promote this to
# a ``BaseCheckpointStore`` ABC; adapters share the Protocol, never a
# base class.
# ---------------------------------------------------------------------------


def _assert_boundary(event: TransitionEvent) -> None:
    """Raise :class:`ValueError` if ``event.next_state_id`` is not a boundary kind.

    Called as the first line of every adapter's :meth:`CheckpointStore.append`.
    Mirrors the orchestrator-side contract phase-arch-design.md §"Process
    view" pins ("G->>L: checkpoint PlanReady" — the call shape implies
    a boundary).
    """
    if event.next_state_id not in _SEMANTIC_BOUNDARY_KINDS:
        directive = _BOUNDARY_VIOLATION_DIRECTIVE.replace(
            "{next_state_id}", repr(event.next_state_id)
        )
        raise ValueError(directive)


# ---------------------------------------------------------------------------
# Canonical event bytes (composition-over-inheritance — both adapters
# call this free function rather than sharing a base class).
# Pydantic v2's ``model_dump_json()`` is deterministic on a frozen +
# ``extra="forbid"`` model (S1-02 ADR-0003 + _FROZEN_FORBID). The
# ``sort_keys=True`` arg is structural belt-and-braces — the inner
# triggering_outcome ``JsonValue`` could carry user-controlled keys that
# Pydantic preserves in insertion order, so we force a canonical sort
# before bytes hit the chain.
# ---------------------------------------------------------------------------


def _canonical_event_bytes(event: TransitionEvent) -> bytes:
    """Return the canonical-JSON bytes for ``event``.

    Single declaration site so both adapters compute the same bytes and
    the parity contract test (AC-6) sees byte-equal payloads.
    """
    return event.model_dump_json().encode("utf-8")


# ---------------------------------------------------------------------------
# The Protocol — five methods, runtime_checkable. The kernel.
# ---------------------------------------------------------------------------


@runtime_checkable
class CheckpointStore(Protocol):
    """Replay-safe per-workflow append-and-read substrate (ADR-0003).

    Five methods, one append discipline (boundary-only via
    :func:`_assert_boundary`), one read discipline (monotonic append
    order, per-workflow filter), one lock discipline (cross-process
    exclusion via the adapter's substrate-specific primitive).

    Open/Closed at the file boundary: this file freezes the Protocol;
    adapters land beside it (``sqlite_checkpoints.py``,
    ``in_memory_checkpoints.py``, Phase-9 ``postgres_checkpoints.py``).

    Disambiguation: the Phase-3
    :class:`~codegenie.plugins.events.EventStreamSink` Protocol is a
    *different* port (forensic-log substrate, byte-line sink); the two
    do not share methods or inherit from a common base. The
    similarities are surface-only.
    """

    def append(self, event: TransitionEvent) -> ChainHead:
        """Append ``event`` under the workflow's append-lock; return the new chain head.

        Must reject any ``event`` whose ``next_state_id`` is not in
        :data:`_SEMANTIC_BOUNDARY_KINDS` (raising :class:`ValueError`)
        and any ``event`` whose canonical-JSON byte length exceeds
        :data:`_MAX_EVENT_BYTES` (raising
        :class:`~codegenie.workflows.errors.CheckpointPayloadTooLargeError`).
        """
        ...

    def read_all_for_workflow(self, workflow_id: WorkflowId) -> Iterator[TransitionEvent]:
        """Yield every :class:`TransitionEvent` for ``workflow_id`` in monotonic append order."""
        ...

    def iter_persisted_chain(
        self, workflow_id: WorkflowId
    ) -> Iterator[tuple[TransitionEvent, ChainHead]]:
        """Yield ``(event, persisted_next_head)`` pairs in monotonic append order.

        Phase-6 S2-02 — substrate for the replay verifier. The
        ``persisted_next_head`` is whatever the adapter wrote at append
        time; the verifier compares it row-by-row to a fresh
        re-computation to find the first divergence index. **No
        recomputation in the substrate** (S2-01 AC-11 detection-only
        contract); the persisted bytes are what they are.

        Additive Protocol extension (ADR-0003 amendment 2026-05-25): does
        NOT replace :meth:`read_all_for_workflow` or
        :meth:`tail_chain_head`; complements them.
        """
        ...

    def tail_chain_head(self, workflow_id: WorkflowId) -> ChainHead:
        """Return the latest chain head for ``workflow_id``, or :data:`_GENESIS_CHAIN_HEAD` if none.

        **Detection-substrate-only** (AC-11): this method returns
        whatever the substrate persisted. It does **not** recompute the
        chain. Recomputation belongs to the S2-02 replay verifier
        (which compares the persisted chain head to a fresh fold over
        the event sequence). Conflating the two collapses the
        detection / policy separation ADR-0003 depends on.
        """
        ...

    def lock(self, workflow_id: WorkflowId) -> AbstractContextManager[None]:
        """Acquire the exclusive append lock for ``workflow_id``."""
        ...

    def close(self) -> None:
        """Release substrate resources (connection pools, file handles)."""
        ...
