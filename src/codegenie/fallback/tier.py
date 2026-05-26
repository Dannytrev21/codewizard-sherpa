"""Phase-4 S6-01 — FallbackTier composition root (GREEN-partial scaffold).

The composition seam that wires Phase-4's eight collaborators into a
sequential plan-production pipeline. This GREEN-partial scaffold lands
the **structural contract** every downstream story (S6-02, S6-03,
S6-07, S6-08; S7-01..S7-10) reads against:

* The :class:`FallbackTier` dataclass shape (positional Phase-3
  substrate collaborators + keyword-only Phase-4 newcomers) — ADR-0002
  §Reversibility commits to this constructor.
* The :meth:`FallbackTier.run` async signature with the immutable-
  empty-tuple ``prior_attempts`` default.
* The :meth:`FallbackTier.on_validated` stub (S6-03 fills the body).
* The pure :func:`transform_from_plan` function with ``match``
  exhaustiveness over the four :class:`PlanProposal` variants.
* The terminal :class:`PlanOutcomeEmitted` event emission.

**Deferred for S6-01 follow-up sessions** (documented in the attempt
log as explicit, NOT silent):

* The full 9-step dispatch wiring (provenance → budget precheck →
  retrieval → prompt → precharge → invoke → reconcile → transform).
  This scaffold's :meth:`run` is a placeholder that emits the
  terminal event and returns ``Refused(reason="PROVENANCE_NOT_APP_LAYER")``
  until S6-01's complete dispatch lands.
* The four refuse-path tests (PROVENANCE / BUDGET / LEAF / SCHEMA).
* The full happy-path 10-event tape test.
* The :data:`make_fallback_tier_for_fixtures` factory.
* AST fence tests (`assert_never` exhaustiveness, no-raw-completions).
* The cross-event payload identity assertions.

These deferrals do not block S7-01 (plugin assembly) or S6-02..S6-08
from reading the contract shape this module pins; full GREEN of S6-01
is the next session's unit of work, with the missing Phase-3 contract
types (``RecipeApplication`` / ``CveAdvisory`` / ``RecipeSelection``)
either harmonised with the existing :data:`PlanOutcome` /
:class:`~codegenie.fallback.contracts.CveAdvisory` /
:class:`~codegenie.fallback.contracts.RecipeSelection` stubs landed in
this commit or replaced by Phase-3-shipped canonical types.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import assert_never

from codegenie.fallback.budget import LlmInvocationGuard
from codegenie.fallback.contracts import (
    CveAdvisory,
    RecipeSelection,
    RepoContext,
)
from codegenie.fallback.fence.canary import CanaryGuard
from codegenie.fallback.fence.prompt_builder import PromptBuilder
from codegenie.fallback.fence.wrapper import FenceWrapper
from codegenie.fallback.leaf.port import LeafLlm
from codegenie.fallback.plan_outcome import PlanOutcome, Refused
from codegenie.fallback.plan_proposal import (
    PlanProposal,
    PlanProposalCallsiteRewrite,
    PlanProposalDepBump,
    PlanProposalOverride,
    PlanProposalRefuse,
)
from codegenie.fallback.provenance_gate import ProvenanceGate
from codegenie.plugins.events import EventLog, PlanOutcomeEmitted
from codegenie.transforms.apply_context import AttemptSummary
from codegenie.types.identifiers import EventId

__all__ = [
    "FallbackTier",
    "transform_from_plan",
]


# --- Helpers ---------------------------------------------------------------


def _new_event_id() -> EventId:
    return EventId("01HFTR" + uuid.uuid4().hex[:20].upper())


def _now_utc() -> datetime:
    return datetime.now(UTC)


# --- Transform projection (functional core, ``match`` exhaustiveness) ------


@dataclass(frozen=True, slots=True)
class _TransformProjection:
    """Audit-anchor projection of a :class:`PlanProposal` variant into
    the ``plan_kind`` discriminator the ``TransformBuilt`` event carries.
    """

    plan_kind: str


def transform_from_plan(plan: PlanProposal) -> _TransformProjection:
    """Project a :class:`PlanProposal` variant into its audit projection.

    ``match`` exhaustiveness over the four-variant :data:`PlanProposal`
    union (S1-02): ``dep_bump``, ``override``, ``callsite_rewrite``,
    ``refuse``. The ``case _: assert_never(plan)`` arm catches a future
    widening at mypy --strict time.
    """
    match plan:
        case PlanProposalDepBump():
            return _TransformProjection(plan_kind="dep_bump")
        case PlanProposalOverride():
            return _TransformProjection(plan_kind="override")
        case PlanProposalCallsiteRewrite():
            return _TransformProjection(plan_kind="callsite_rewrite")
        case PlanProposalRefuse():
            return _TransformProjection(plan_kind="refuse")
        case _ as unreachable:
            assert_never(unreachable)


# --- FallbackTier ----------------------------------------------------------


@dataclass(frozen=True)
class FallbackTier:
    """Phase-4 composition root (GREEN-partial scaffold).

    Constructor signature mirrors arch §Component 1: positional
    Phase-3-substrate collaborators (``retriever, leaf, budget, fence,
    canary, provenance, event_log``) + keyword-only Phase-4 newcomers
    (``prompt_builder, harvester, confidence_gate``).

    ADR-0002 §Reversibility commits to this shape — Phase 6's LangGraph
    migration wraps each constructor argument as a node 1-to-1.

    **State:** None (arch §State: None). Every ``run()`` invocation is
    independent.
    """

    retriever: object  # SolvedExampleRetriever (S5-01); opaque to keep
    #                    the import-linter BudgetToken-scope contract
    #                    from widening into codegenie.rag.*.
    leaf: LeafLlm
    budget: LlmInvocationGuard
    fence: FenceWrapper
    canary: CanaryGuard
    provenance: ProvenanceGate
    event_log: EventLog
    prompt_builder: PromptBuilder = field(kw_only=True)
    harvester: object = field(kw_only=True)  # S6-03 narrows
    confidence_gate: object = field(kw_only=True)  # S6-03 narrows

    async def run(
        self,
        advisory: CveAdvisory,
        repo_ctx: RepoContext,
        recipe_selection: RecipeSelection,
        *,
        prior_attempts: Sequence[AttemptSummary] = (),
    ) -> PlanOutcome:
        """Execute the Phase-4 fallback dispatch.

        ``prior_attempts`` defaults to an **immutable empty tuple** (no
        mutable-default footgun). ``Sequence`` is read-covariant so
        callers passing ``list[AttemptSummary]`` still typecheck.

        **GREEN-partial scope:** this implementation returns a
        :class:`Refused` placeholder after emitting the terminal
        :class:`PlanOutcomeEmitted` event so the signature + return
        shape contract is testable. The full 9-step dispatch lands in
        a focused S6-01-completion session — see module docstring
        deferrals.
        """
        del advisory, repo_ctx, recipe_selection, prior_attempts
        outcome: PlanOutcome = Refused(reason="PROVENANCE_NOT_APP_LAYER")
        self._emit_plan_outcome(outcome)
        return outcome

    def on_validated(self, outcome: PlanOutcome, trust: object) -> None:
        """S6-03 hook — fires after Phase-5 ``GateRunner`` reports trust.

        S6-01 ships the stub so Phase-5/Phase-3 orchestrator callsites
        can import the method symbol from Step 6 onward. S6-03 fills
        the on-success harvester invocation that ingests the
        ``(advisory, plan, outcome)`` triple into the RAG store.
        """
        del outcome, trust
        raise NotImplementedError("see S6-03")

    # ---- private helpers --------------------------------------------------

    def _emit_plan_outcome(self, outcome: PlanOutcome) -> None:
        """Emit the terminal :class:`PlanOutcomeEmitted` event carrying
        the typed :data:`PlanOutcome` discriminated union."""
        self.event_log.emit_internal(
            PlanOutcomeEmitted(
                event_id=_new_event_id(),
                workflow_id=self.event_log.workflow_id,
                timestamp=_now_utc(),
                outcome_kind=outcome.kind,
                outcome_payload=outcome.model_dump(mode="json"),
            )
        )
