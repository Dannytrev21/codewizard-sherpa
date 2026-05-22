"""S6-02 — :class:`TrustScorer`, the strict-AND Stage-6 scoring kernel.

The scorer folds the five Stage-6 :class:`TrustSignal`s into one
:class:`TrustOutcome`:

* ``passed`` is strict-AND — true exactly when *every* signal passed.
* ``failing`` lists the failed signal kinds in **caller order** (never sorted
  — Phase 5's gate-runner and the S5-05 report writer display the
  first-failing signal to humans).
* ``confidence`` folds the workflow's own event stream: ``"degraded"`` when
  any :class:`~codegenie.plugins.events.AdapterDegraded` event for *this*
  workflow appears in the injected log, else ``"high"``.

**Constructor injection (Gap 5 — ADR-0001 / ADR-0005).** ``__init__`` takes
the :class:`~codegenie.plugins.events.EventLog` explicitly. The ambient-state
alternative (``score`` discovering the log via ``os.environ`` / a thread-
local) is rejected: it is unmockable, hides coupling, and breaks under
concurrent workflows in one process. The constructor argument *is* the
contract.

**Functional core / imperative shell.** :func:`_compute_strict_and` and
:func:`_has_adapter_degraded_for_workflow` are pure — they carry the logic and
touch no event log, no filesystem, no module state. :meth:`TrustScorer.score`
is the only impure code; it reads the event log once per call and is stateless
across calls (Phase 5 reuses one scorer across retries — ADR-0007).

**Import-cycle note.** ``codegenie.plugins.events`` transitively imports
``codegenie.transforms`` (events → cache_gc → cache → bundle →
adapters.confidence → transforms.outcomes). Importing ``AdapterDegraded`` at
this module's top level would close that cycle, so the event types used only
in annotations are ``TYPE_CHECKING``-guarded and the one runtime use
(``isinstance`` in :func:`_has_adapter_degraded_for_workflow`) takes a
function-local import. This module therefore has **no** runtime dependency on
``codegenie.plugins.events``.

``TrustSignal`` / ``TrustOutcome`` are the canonical Pydantic value types
from :mod:`codegenie.transforms.outcomes` (shipped ahead by S1-03 — the arch
spec's Data-model section names them as "S6-02's"). This module re-exports
them so ``from codegenie.transforms.trust_scorer import TrustOutcome`` works,
but never redefines them — there is one definition (ADR-0010).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, TypeAlias

from codegenie.errors import CodegenieError
from codegenie.transforms.outcomes import TrustOutcome, TrustSignal
from codegenie.transforms.signal_kinds import signal_kind_registry
from codegenie.types.identifiers import SignalKind, WorkflowId

if TYPE_CHECKING:  # pragma: no cover — type-checker-only (see "Import-cycle note")
    from codegenie.plugins.events import (
        EventLog,
        WorkflowInternalEvent,
        WorkflowSpanningEvent,
    )

__all__ = [
    "EmptySignals",
    "StageOutcome",
    "TrustOutcome",
    "TrustScorer",
    "TrustSignal",
    "UnregisteredSignalKind",
]

StageOutcome: TypeAlias = TrustOutcome
"""ADR-0015/S6-04 Phase-5 name for the Stage-6 validation return type."""


class UnregisteredSignalKind(CodegenieError):
    """Raised by :meth:`TrustScorer.score` when a signal names an unknown kind.

    A *usage* error — a caller passed a :class:`SignalKind` no module
    registered via :func:`~codegenie.transforms.signal_kinds.register_signal_kind`.
    Carries a typed ``.kind`` attribute. Categorically distinct from the
    import-time :class:`~codegenie.transforms.signal_kinds.SignalKindAlreadyRegistered`.
    """

    kind: SignalKind

    def __init__(self, kind: SignalKind) -> None:
        self.kind = kind
        super().__init__(f"signal kind {kind!r} is not registered")


class EmptySignals(CodegenieError):
    """Raised by :meth:`TrustScorer.score` when called with no signals.

    The architecture pins Stage 6 to exactly five signals; an empty list is a
    caller bug. Silently returning ``passed=True`` would mis-report a broken
    Stage-6 collection as a successful workflow (fail loud — Rule 12).
    """


def _compute_strict_and(signals: list[TrustSignal]) -> tuple[bool, list[SignalKind]]:
    """Return ``(all-passed, failed-kinds-in-input-order)`` — pure, no I/O.

    ``failing`` preserves caller order; it is never sorted or deduplicated.
    """
    failing = [s.kind for s in signals if not s.passed]
    return (not failing, failing)


def _has_adapter_degraded_for_workflow(
    events: Iterable[WorkflowInternalEvent | WorkflowSpanningEvent],
    workflow_id: WorkflowId,
) -> bool:
    """Return whether any event is an ``AdapterDegraded`` for ``workflow_id``.

    Pure: takes an already-materialised iterable of events; it neither reads a
    log nor touches the filesystem. The filter is on event-type **and**
    workflow id — neither alone flips the result. ``AdapterDegraded`` is
    imported function-locally to keep this module free of a runtime
    ``codegenie.plugins.events`` dependency (see the module's import-cycle note).
    """
    from codegenie.plugins.events import AdapterDegraded

    return any(
        isinstance(event, AdapterDegraded) and event.workflow_id == workflow_id for event in events
    )


class TrustScorer:
    """Strict-AND scoring kernel with a constructor-injected event log.

    Construct one per workflow: ``TrustScorer(event_log=workflow_log)``. The
    scorer is stateless across :meth:`score` calls — it re-reads the log every
    call so an :class:`~codegenie.plugins.events.AdapterDegraded` emitted
    between two calls is reflected by the second outcome.
    """

    def __init__(self, event_log: EventLog) -> None:
        self._event_log = event_log

    def score(self, signals: list[TrustSignal]) -> TrustOutcome:
        """Fold ``signals`` into a :class:`TrustOutcome` (strict-AND + confidence).

        Raises :class:`EmptySignals` on an empty list and
        :class:`UnregisteredSignalKind` on the first signal whose ``kind`` is
        not in the :data:`~codegenie.transforms.signal_kinds.signal_kind_registry`.
        Registry membership is the *only* validation ``score`` performs.
        """
        if not signals:
            raise EmptySignals("TrustScorer.score requires at least one signal")
        for signal in signals:
            if signal.kind not in signal_kind_registry:
                raise UnregisteredSignalKind(signal.kind)

        passed, failing = _compute_strict_and(signals)
        degraded = _has_adapter_degraded_for_workflow(
            self._event_log.replay(), self._event_log.workflow_id
        )
        return TrustOutcome(
            passed=passed,
            failing=failing,
            signals=signals,
            confidence="degraded" if degraded else "high",
        )
