"""Phase 6 S1-02 — closed ledger state union + transition event substrate.

This module is the *internal* state-machine substrate every Phase-6 node and
the checkpoint store will dispatch on. It is the second half of
``High-level-impl.md §"Step 1 — Public contracts and typed ledger"``; the
public Result + Case + Protocol + SUT-digest substrate landed in S1-01.

What lands here:

* **The closed seven-variant** :data:`VulnLedgerState` discriminated union —
  four non-terminal variants (:class:`NeedsPlan`, :class:`PlanReady`,
  :class:`PatchApplied`, :class:`GateFailedRetryable`) and three terminal
  variants (:class:`AwaitingHumanReview`, :class:`Completed`,
  :class:`FailedUnrecoverable`). Verbatim with ``final-design.md §"State
  model"`` + ADR-0001's ``TerminalState`` partition.
* **The** :class:`TransitionEvent` **model** carrying the five fields
  ``final-design.md §"State model"`` mandates (prior state id, next state
  id, triggering outcome, evidence digest, chain head) plus two
  cross-cutting identifiers (transition id, workflow id).
* **The closed legal-transition table** :data:`_LEGAL_TRANSITIONS` —
  enforced by a ``model_validator(mode="after")`` on
  :class:`TransitionEvent`. Adding an edge is an ADR-0003 amendment, not
  a runtime decoration.
* **The terminal partition constant** :data:`_TERMINAL_LEDGER_KINDS` — a
  cross-story membership test in ``tests/integration/`` asserts this is
  byte-equal to S1-01's :data:`~codegenie.workflows.vuln_sut.TerminalState`
  Literal.

Anti-refactor (story §"Anti-refactor"; CLAUDE.md "composition over
inheritance" + Rule 2):

* No :class:`!BaseLedgerState` ABC. Composition wins (Phase-3
  ``transforms/outcomes.py`` precedent — :class:`RecipeError` is *composed
  into* :class:`RecipeFailed`, never inherited).
* No ``LedgerStateRegistry`` / ``@register_ledger_variant``. The
  seven-variant universe is closed; rule-of-three threshold (a *second*
  ledger sum type) lands in Phase 7 as ``migration_ledger.py``.
* No ``Specification``-pattern transition framework. ``(prior, next) ∈
  frozenset`` is the right predicate granularity.
* No ``transition_log: list`` field on any variant — the chain of
  :class:`TransitionEvent` s lives in the S2-01 checkpoint store and is
  walked via the chain-head pure helper.

Wire shape of :class:`TransitionEvent.triggering_outcome`: ``JsonValue``
(Pydantic's structurally-typed JSON value). Two reasons over a
discriminated union of ``RecipeOutcome | NodeTransition | TrustOutcome``:

1. ``NodeTransition`` carries an ``Advance.state: SubgraphState`` forward
   ref that requires ``model_rebuild()`` at import time — coupling
   ``vuln_ledger.py`` to ``codegenie.plugins.subgraph`` (out of Phase-6
   scope, would close a kernel-cycle).
2. The substrate doesn't need to dispatch on the typed shape — it only
   needs deterministic bytes for the chain-head computation. The
   producer (Phase-6 S3-01 subgraph nodes) serialises via
   ``outcome.model_dump(mode='json')`` before constructing the
   ``TransitionEvent``; the typed shape lives on the producer side, the
   evidence-of-record lives on the ledger side.

This is a Phase-6 S1-02 scope decision recorded in the attempt log.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal, get_args

from pydantic import BaseModel, Field, JsonValue, field_validator, model_validator

from codegenie.transforms.outcomes import HumanReviewReason, RemediationError
from codegenie.types.identifiers import (
    AttemptNumber,
    BlobDigest,
    ChainHead,
    SignalKind,
    TransitionId,
    WorkflowId,
)
from codegenie.workflows._frozen import _FROZEN_FORBID

__all__ = [
    "AwaitingHumanReview",
    "Completed",
    "FailedUnrecoverable",
    "GateFailedRetryable",
    "LedgerStateKind",
    "NeedsPlan",
    "PatchApplied",
    "PlanReady",
    "TransitionEvent",
    "VulnLedgerState",
]


# ---------------------------------------------------------------------------
# Closed kind taxonomy — mirrors the seven variant ``kind`` literals below.
# Membership is asserted byte-equal in tests/unit/workflows/test_vuln_ledger_shape.py.
# ---------------------------------------------------------------------------

LedgerStateKind = Literal[
    "needs_plan",
    "plan_ready",
    "patch_applied",
    "gate_failed_retryable",
    "awaiting_human_review",
    "completed",
    "failed_unrecoverable",
]
"""Closed set of ledger state slugs. Adding an eighth is an ADR-0001 +
ADR-0003 amendment + an edit to S1-01's :data:`TerminalState` if the new
state is terminal."""


_NON_TERMINAL_LEDGER_KINDS: Final[frozenset[LedgerStateKind]] = frozenset(
    {"needs_plan", "plan_ready", "patch_applied", "gate_failed_retryable"}
)
"""Non-terminal partition — the four states with at least one outgoing
legal transition."""

_TERMINAL_LEDGER_KINDS: Final[frozenset[LedgerStateKind]] = frozenset(
    {"awaiting_human_review", "completed", "failed_unrecoverable"}
)
"""Terminal partition — byte-equal to S1-01's :data:`TerminalState` Literal.
Cross-story membership equality is asserted by
``tests/integration/test_phase6_terminal_state_consistency.py`` (AC-6)."""


# ---------------------------------------------------------------------------
# Closed reason literal for the FailedUnrecoverable variant — byte-equal to
# the row keys of phase-arch-design.md §"Failure modes". Adding a sixth row
# is an ADR-0003 amendment.
# ---------------------------------------------------------------------------

FailedUnrecoverableReason = Literal[
    "checkpoint_integrity",
    "subgraph_aborted",
    "manifest_rejected",
    "policy_violation",
    "internal_invariant_violated",
]


_PLAN_SUMMARY_MAX_LEN = 4096
"""Mirrors the Phase-3 :class:`~codegenie.transforms.outcomes.RecipeError`
``_message_length`` cap — keeps the ledger snapshot bytes bounded."""


# ---------------------------------------------------------------------------
# Seven ledger state variants (closed sum type — final-design.md §"State model").
# Each is frozen + extra="forbid"; the _FROZEN_FORBID constant is imported
# (never inlined) so the AST fence at tests/fence/test_workflows_frozen_forbid.py
# pins single-canonical-declaration discipline.
# ---------------------------------------------------------------------------


class NeedsPlan(BaseModel):
    """Initial state — no plan has been proposed yet. No evidence payload."""

    model_config = _FROZEN_FORBID
    kind: Literal["needs_plan"] = "needs_plan"


class PlanReady(BaseModel):
    """A remediation plan has been proposed and is ready for execution."""

    model_config = _FROZEN_FORBID
    kind: Literal["plan_ready"] = "plan_ready"
    plan_summary: str

    @field_validator("plan_summary")
    @classmethod
    def _plan_summary_length(cls, v: str) -> str:
        if len(v) > _PLAN_SUMMARY_MAX_LEN:
            raise ValueError(f"PlanReady.plan_summary: exceeds {_PLAN_SUMMARY_MAX_LEN} chars")
        return v


class PatchApplied(BaseModel):
    """The proposed patch has been applied; gates are pending."""

    model_config = _FROZEN_FORBID
    kind: Literal["patch_applied"] = "patch_applied"
    patch_digest: BlobDigest


class GateFailedRetryable(BaseModel):
    """One or more gates failed but the failure mode admits retry."""

    model_config = _FROZEN_FORBID
    kind: Literal["gate_failed_retryable"] = "gate_failed_retryable"
    failing_signals: tuple[SignalKind, ...]
    attempt_number: AttemptNumber


class AwaitingHumanReview(BaseModel):
    """Terminal: handed off to a human reviewer. ``handoff_path`` is the
    relative path into the per-run artifact directory (``None`` if the
    orchestrator could not allocate before the handoff)."""

    model_config = _FROZEN_FORBID
    kind: Literal["awaiting_human_review"] = "awaiting_human_review"
    review_reason: HumanReviewReason
    handoff_path: str | None = None


class Completed(BaseModel):
    """Terminal: remediation finished. ``report_path`` is the relative path
    into the per-run artifact directory (``None`` when the orchestrator
    failed to allocate the report file before completion)."""

    model_config = _FROZEN_FORBID
    kind: Literal["completed"] = "completed"
    report_path: str | None = None


class FailedUnrecoverable(BaseModel):
    """Terminal: an unrecoverable failure. ``reason`` is the closed-set
    failure-mode key from ``phase-arch-design.md §"Failure modes"``."""

    model_config = _FROZEN_FORBID
    kind: Literal["failed_unrecoverable"] = "failed_unrecoverable"
    reason: FailedUnrecoverableReason
    error: RemediationError | None = None


# ---------------------------------------------------------------------------
# Closed discriminated union (Annotated[..., Field(discriminator="kind")] —
# repo convention, see codegenie/transforms/outcomes.py + indices/freshness.py +
# fallback/plan_outcome.py).
# ---------------------------------------------------------------------------

VulnLedgerState = Annotated[
    NeedsPlan
    | PlanReady
    | PatchApplied
    | GateFailedRetryable
    | AwaitingHumanReview
    | Completed
    | FailedUnrecoverable,
    Field(discriminator="kind"),
]


# ---------------------------------------------------------------------------
# Closed legal-transition table. Derived verbatim from final-design.md
# §"Main workflow" + ADR-0003 §"Consequences". The model_validator on
# TransitionEvent rejects pairs not in this set.
# ---------------------------------------------------------------------------

_LEGAL_TRANSITIONS: Final[frozenset[tuple[LedgerStateKind, LedgerStateKind]]] = frozenset(
    {
        # needs_plan → plan_ready
        ("needs_plan", "plan_ready"),
        # plan_ready → {patch_applied, awaiting_human_review, failed_unrecoverable}
        ("plan_ready", "patch_applied"),
        ("plan_ready", "awaiting_human_review"),
        ("plan_ready", "failed_unrecoverable"),
        # patch_applied → {completed, gate_failed_retryable, awaiting_human_review,
        #                   failed_unrecoverable}
        ("patch_applied", "completed"),
        ("patch_applied", "gate_failed_retryable"),
        ("patch_applied", "awaiting_human_review"),
        ("patch_applied", "failed_unrecoverable"),
        # gate_failed_retryable → {needs_plan, awaiting_human_review, failed_unrecoverable}
        ("gate_failed_retryable", "needs_plan"),
        ("gate_failed_retryable", "awaiting_human_review"),
        ("gate_failed_retryable", "failed_unrecoverable"),
        # awaiting_human_review → {plan_ready, completed, failed_unrecoverable}
        ("awaiting_human_review", "plan_ready"),
        ("awaiting_human_review", "completed"),
        ("awaiting_human_review", "failed_unrecoverable"),
        # completed and failed_unrecoverable are terminal (zero outgoing).
    }
)
"""Closed legal-transition edges — see final-design.md §"Main workflow" +
ADR-0003 §"Consequences". Adding an edge is an ADR-0003 amendment."""


_LEGAL_TRANSITIONS_DIRECTIVE: Final[str] = (
    "TransitionEvent: illegal (prior_state_id, next_state_id) pair. See "
    "ADR-0003 §Consequences for the legal-edge inventory; adding an edge "
    "is an ADR-0003 amendment, not a runtime decoration."
)


# ---------------------------------------------------------------------------
# TransitionEvent — the chained ledger record. Seven fields:
#   * five mandated by final-design.md §"State model"
#   * plus transition_id (per-event ULID, chained for replay determinism)
#   * plus workflow_id (ties the transition to a specific SUT case)
# ---------------------------------------------------------------------------


class TransitionEvent(BaseModel):
    """A single transition record — chained for replay-determinism (ADR-0003).

    ``triggering_outcome`` is a :data:`~pydantic.JsonValue` rather than a
    discriminated union of ``RecipeOutcome | NodeTransition | TrustOutcome``:
    the substrate doesn't need to dispatch on the upstream typed shape —
    only to serialise it deterministically into the chain-head computation.
    The producer (Phase-6 S3-01 subgraph nodes) serialises via
    ``outcome.model_dump(mode='json')`` before constructing this event.
    See module docstring for the rationale (deferred coupling to
    ``codegenie.plugins.subgraph``).
    """

    model_config = _FROZEN_FORBID

    transition_id: TransitionId
    prior_state_id: LedgerStateKind
    next_state_id: LedgerStateKind
    triggering_outcome: JsonValue
    evidence_digest: BlobDigest
    chain_head: ChainHead
    workflow_id: WorkflowId

    @model_validator(mode="after")
    def _enforce_legal_transition(self) -> TransitionEvent:
        pair = (self.prior_state_id, self.next_state_id)
        if pair not in _LEGAL_TRANSITIONS:
            raise ValueError(f"{_LEGAL_TRANSITIONS_DIRECTIVE} Got: {pair!r}.")
        return self


# ---------------------------------------------------------------------------
# Defensive runtime assertion — the seven variant slugs MUST equal the
# LedgerStateKind Literal membership. Catches the case where a future edit
# adds a variant but forgets to widen the alias (or vice versa) before tests
# even run.
# ---------------------------------------------------------------------------

_VARIANT_KINDS: Final[frozenset[str]] = frozenset(
    {
        "needs_plan",
        "plan_ready",
        "patch_applied",
        "gate_failed_retryable",
        "awaiting_human_review",
        "completed",
        "failed_unrecoverable",
    }
)
assert _VARIANT_KINDS == set(get_args(LedgerStateKind)), (
    "vuln_ledger: _VARIANT_KINDS drift from LedgerStateKind — "
    "amend ADR-0001 + ADR-0003 before adding a ledger variant."
)
assert _VARIANT_KINDS == (_NON_TERMINAL_LEDGER_KINDS | _TERMINAL_LEDGER_KINDS), (
    "vuln_ledger: variant partition drift — every kind must be either "
    "non-terminal or terminal, never both."
)
