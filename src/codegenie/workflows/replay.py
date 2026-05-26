"""Phase 6 S2-02 — replay verifier + integrity-policy gate (ADR-0003 §Decision second half).

This module is the *imperative shell* counterpart of
:mod:`codegenie.workflows._replay` (the pure fold). It owns:

* the closed four-variant :data:`ReplayVerdict` discriminated union
  (:class:`Verified` / :class:`ChainMismatch` / :class:`TornWrite` /
  :class:`EmptyWorkflow`);
* the :class:`ReplayVerifier` class — a thin imperative shell over the
  :class:`~codegenie.workflows.checkpoints.CheckpointStore` Protocol
  (constructor-injected; ``__slots__``-locked; substrate-agnostic by
  dispatching through the Protocol);
* the :func:`hydrate_or_fail` integrity-policy gate — the **SOLE site**
  that maps :class:`ChainMismatch` | :class:`TornWrite` →
  :class:`~codegenie.workflows.vuln_ledger.FailedUnrecoverable` with
  ``reason="checkpoint_integrity"``;
* the :class:`Hydrated` success carrier and the :data:`HydrationResult`
  return union.

The detection / policy separation is the load-bearing invariant of the
ADR-0003 substrate:

* :meth:`~codegenie.workflows.checkpoints.CheckpointStore.tail_chain_head`
  is *detection-only* — it returns whatever the substrate persisted
  (S2-01 AC-11).
* :meth:`ReplayVerifier.verify` is the *policy* — it recomputes the
  chain via the pure fold and classifies the verdict.

Conflating the two would collapse ADR-0003's "verify the previous chain
head before hydration" into the substrate. Neither half can be
short-circuited: the substrate refusing to recompute is *what makes*
tamper detection possible.

Sum-type discipline: :data:`ReplayVerdict` mirrors the project-wide
``Annotated[..., Field(discriminator="kind")]`` pattern
(:data:`~codegenie.workflows.vuln_ledger.VulnLedgerState` is the
canonical sibling). All four variant ``BaseModel`` subclasses use
:data:`_FROZEN_FORBID` — never an inlined ``ConfigDict`` (ADR-0010 +
S1-01 AC-4 single-canonical-declaration discipline).

Anti-refactor (story §"Anti-refactor"; CLAUDE.md "composition over
inheritance" + Rule 2):

1. No ``BaseReplayVerifier`` ABC — one concrete verifier; the Protocol
   IS :class:`CheckpointStore`.
2. No ``VerifierStrategy`` Strategy abstraction — the fold is the *one*
   canonical policy (sanitize-then-fold mirroring the write path).
3. No boolean return from ``verify()`` — the tagged union IS the
   contract.
4. No ``ReplayVerifierRegistry`` — substrate-agnostic, no dispatch to
   register.
5. No async ``verify()`` — the orchestrator wraps in
   :func:`asyncio.to_thread` (same pattern S2-01 pinned for ``append``).
6. No ``ReplayCache`` — verification is cheap and idempotent; caching
   couples cache invalidation to tamper detection.
7. No ``verify_or_raise()`` convenience wrapper — raising defeats the
   discriminated-union exhaustiveness guarantee.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import BaseModel, Field, ValidationError

from codegenie.transforms.outcomes import RemediationError
from codegenie.types.identifiers import (
    ChainHead,
    ErrorId,
    TransitionId,
    WorkflowId,
)
from codegenie.workflows._frozen import _FROZEN_FORBID
from codegenie.workflows._replay import _replay_fold
from codegenie.workflows.checkpoints import (
    _GENESIS_CHAIN_HEAD,
    CheckpointStore,
)
from codegenie.workflows.vuln_ledger import (
    FailedUnrecoverable,
    LedgerStateKind,
    TransitionEvent,
)

# Note: the `del _replay_fold` line is intentional only if unused; we
# keep it imported for downstream test reach + symmetry with the
# pure-core module. Suppress unused-import false positive.
_ = _replay_fold


__all__ = [
    "ChainMismatch",
    "EmptyWorkflow",
    "Hydrated",
    "HydrationResult",
    "ReplayVerdict",
    "ReplayVerifier",
    "TornWrite",
    "Verified",
    "hydrate_or_fail",
]


_INTEGRITY_ERROR_ID: Final[ErrorId] = ErrorId("workflows.checkpoint_integrity_violation")
"""Closed :data:`ErrorId` for the integrity-failure payload. Module-local
because there is no project-wide ``error_id`` registry today; when one
lands (Phase 9+), the constant migrates additively (Phase-1 ADR-0007
dotted-snake-case grammar)."""


# ---------------------------------------------------------------------------
# Closed four-variant verdict union (project canonical pattern — see
# VulnLedgerState in vuln_ledger.py, RecipeOutcome in transforms/outcomes.py).
# ---------------------------------------------------------------------------


class Verified(BaseModel):
    """Successful verification — the chain folds match the persisted tail."""

    model_config = _FROZEN_FORBID
    kind: Literal["verified"] = "verified"
    tail_chain_head: ChainHead
    events: tuple[TransitionEvent, ...]


class ChainMismatch(BaseModel):
    """The recomputed chain differs from the persisted chain at some row.

    ``divergence_index`` is the 0-based index of the FIRST row where the
    recomputed head differs from the persisted head (the verifier walks
    front-to-back and reports the earliest divergence).
    """

    model_config = _FROZEN_FORBID
    kind: Literal["chain_mismatch"] = "chain_mismatch"
    persisted_tail: ChainHead
    recomputed_tail: ChainHead
    divergence_index: int = Field(ge=0)
    offending_transition_id: TransitionId


class TornWrite(BaseModel):
    """A persisted row is structurally damaged (parse failure or duplicate link)."""

    model_config = _FROZEN_FORBID
    kind: Literal["torn_write"] = "torn_write"
    reason: Literal["unparseable_event", "null_event_bytes", "duplicate_chain_link"]
    offending_sequence: int = Field(ge=0)


class EmptyWorkflow(BaseModel):
    """The workflow has zero persisted rows — trivially verified at genesis."""

    model_config = _FROZEN_FORBID
    kind: Literal["empty_workflow"] = "empty_workflow"
    genesis_chain_head: ChainHead


ReplayVerdict = Annotated[
    Verified | ChainMismatch | TornWrite | EmptyWorkflow,
    Field(discriminator="kind"),
]
"""Closed four-variant verdict union. Adding a fifth variant is an
ADR-0003 amendment + an additive edit to :func:`_dispatch_verdict`'s
``match`` (the AST test counts arms — drift fails loud)."""


# ---------------------------------------------------------------------------
# Hydration result — the verifier's return shape to the orchestrator.
# Hydrated.kind is deliberately a NEW closed-set tag, NOT reused from
# LedgerStateKind (the two unions answer different questions).
# ---------------------------------------------------------------------------


class Hydrated(BaseModel):
    """Successful hydration — verified events + the latest legal state kind."""

    model_config = _FROZEN_FORBID
    kind: Literal["hydrated"] = "hydrated"
    events: tuple[TransitionEvent, ...]
    latest_state_kind: LedgerStateKind


HydrationResult = Annotated[
    Hydrated | FailedUnrecoverable,
    Field(discriminator="kind"),
]
"""Closed two-variant hydration outcome. The orchestrator branches on
``result.kind``: ``"hydrated"`` → run the subgraph with the hydrated
events; ``"failed_unrecoverable"`` → emit the typed terminal state."""


# ---------------------------------------------------------------------------
# The verifier — imperative shell over the CheckpointStore Protocol.
# ---------------------------------------------------------------------------


class ReplayVerifier:
    """Recompute the chain over the persisted sequence; classify the verdict.

    Substrate-agnostic by construction — every read goes through the
    :class:`~codegenie.workflows.checkpoints.CheckpointStore` Protocol.
    No SQLite-specific shortcuts; no in-memory cache. The AC-6 parity
    matrix asserts the verdict is byte-equivalent across adapters.
    """

    __slots__ = ("_store",)

    def __init__(self, store: CheckpointStore) -> None:
        self._store = store

    def verify(self, workflow_id: WorkflowId) -> ReplayVerdict:
        """Return the :data:`ReplayVerdict` for ``workflow_id``."""
        running_head: ChainHead = _GENESIS_CHAIN_HEAD
        events: list[TransitionEvent] = []
        # ``sequence_count`` advances AFTER a successful iteration so a
        # ValidationError raised by the iterator's next() (i.e. parse
        # failure on the NEXT row) surfaces with the correct
        # ``offending_sequence``.
        sequence_count = 0
        iterator = self._store.iter_persisted_chain(workflow_id)
        while True:
            try:
                event, persisted_next_head = next(iterator)
            except StopIteration:
                break
            except ValidationError:
                return TornWrite(
                    reason="unparseable_event",
                    offending_sequence=sequence_count,
                )
            events.append(event)
            running_head = _fold_one(running_head, event)
            if running_head != persisted_next_head:
                persisted_tail = self._store.tail_chain_head(workflow_id)
                return ChainMismatch(
                    persisted_tail=persisted_tail,
                    recomputed_tail=running_head,
                    divergence_index=sequence_count,
                    offending_transition_id=event.transition_id,
                )
            sequence_count += 1

        if not events:
            return EmptyWorkflow(genesis_chain_head=_GENESIS_CHAIN_HEAD)
        return Verified(tail_chain_head=running_head, events=tuple(events))


def _fold_one(prior: ChainHead, event: TransitionEvent) -> ChainHead:
    """Single-step fold — keeps the imperative shell free of the pure helper's import name.

    Routed through the canonical pure helper :func:`_replay_fold` for a
    one-event iterable to honour the AST-fence-protected pure-core
    pipeline (rather than reaching into ``_chain.py`` directly here).
    """
    return _replay_fold([event], genesis=prior)


# ---------------------------------------------------------------------------
# The integrity-policy gate — the SOLE site mapping non-Verified verdicts
# to FailedUnrecoverable(reason="checkpoint_integrity").
# ---------------------------------------------------------------------------


def hydrate_or_fail(store: CheckpointStore, workflow_id: WorkflowId) -> HydrationResult:
    """Verify the chain; on success return Hydrated, else FailedUnrecoverable.

    ADR-0003 §Consequences "Failed verification transitions to
    ``FailedUnrecoverable``" is implemented HERE — and ONLY here. The
    fail-closed-before-hydrate AST fence
    (``tests/fence/test_hydrate_no_state_construction.py``) asserts no
    non-:class:`FailedUnrecoverable` ledger-state variant is constructed
    on this code path.
    """
    verdict = ReplayVerifier(store).verify(workflow_id)
    return _dispatch_verdict(verdict)


def _dispatch_verdict(verdict: ReplayVerdict) -> HydrationResult:
    """Exhaustive ``match`` over the four verdict kinds (AST-test-enforced)."""
    match verdict.kind:
        case "verified":
            assert isinstance(verdict, Verified)
            latest = verdict.events[-1].next_state_id if verdict.events else "needs_plan"
            return Hydrated(events=verdict.events, latest_state_kind=latest)
        case "empty_workflow":
            assert isinstance(verdict, EmptyWorkflow)
            return Hydrated(events=(), latest_state_kind="needs_plan")
        case "chain_mismatch":
            assert isinstance(verdict, ChainMismatch)
            return FailedUnrecoverable(
                reason="checkpoint_integrity",
                error=RemediationError(
                    error_id=_INTEGRITY_ERROR_ID,
                    message=_format_integrity_message(verdict),
                ),
            )
        case "torn_write":
            assert isinstance(verdict, TornWrite)
            return FailedUnrecoverable(
                reason="checkpoint_integrity",
                error=RemediationError(
                    error_id=_INTEGRITY_ERROR_ID,
                    message=_format_integrity_message(verdict),
                ),
            )
        case _:
            raise AssertionError(
                f"verdict_kind drift — amend ReplayVerdict + _dispatch_verdict: "
                f"got {verdict.kind!r}"
            )


def _format_integrity_message(
    verdict: ChainMismatch | TornWrite,
) -> str:
    """Pure helper — produces the diagnostic message for the integrity payload.

    The message names the verdict kind, the offending sequence /
    transition, and the persisted vs recomputed heads (for
    ``ChainMismatch``). No clock, no env, no I/O — timestamping is the
    orchestrator's job at the call site.
    """
    if isinstance(verdict, ChainMismatch):
        return (
            f"Checkpoint integrity violation: chain_mismatch at "
            f"divergence_index={verdict.divergence_index}; "
            f"offending_transition_id={verdict.offending_transition_id!r}; "
            f"persisted_tail={verdict.persisted_tail!r}; "
            f"recomputed_tail={verdict.recomputed_tail!r}. "
            f"ADR-0003: tamper or partial writes fail closed."
        )
    return (
        f"Checkpoint integrity violation: torn_write "
        f"(reason={verdict.reason!r}) at offending_sequence={verdict.offending_sequence}. "
        f"ADR-0003: tamper or partial writes fail closed."
    )
