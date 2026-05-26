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
from pathlib import Path
from typing import assert_never

from codegenie.fallback import anchor_writer
from codegenie.fallback.attempt_anchor import AttemptAnchor
from codegenie.fallback.budget import LlmInvocationGuard
from codegenie.fallback.confidence_gate import ConfidenceGate
from codegenie.fallback.contracts import (
    CveAdvisory,
    RecipeSelection,
    RepoContext,
)
from codegenie.fallback.fence.canary import CanaryGuard
from codegenie.fallback.fence.prompt_builder import PromptBuilder
from codegenie.fallback.fence.wrapper import FenceWrapper
from codegenie.fallback.leaf.port import LeafLlm
from codegenie.fallback.plan_outcome import (
    AppliedFromLlm,
    AppliedFromRecipe,
    PlanOutcome,
    RagOnlyApplicable,
    Refused,
)
from codegenie.fallback.plan_proposal import (
    PlanProposal,
    PlanProposalCallsiteRewrite,
    PlanProposalDepBump,
    PlanProposalOverride,
    PlanProposalRefuse,
)
from codegenie.fallback.post_validation_context import PostValidationContext
from codegenie.fallback.provenance_gate import ProvenanceGate
from codegenie.plugins.events import (
    AttemptAnchorRecorded,
    EventLog,
    HarvestSkipped,
    PlanOutcomeEmitted,
    RagSkippedOnRetry,
    SolvedExampleHarvested,
)
from codegenie.rag._capability_mint import _phase4_local_capability_mint
from codegenie.rag.embedder import Embedder
from codegenie.rag.ingest import ValidatedPlanOutcome, ingest_solved_example
from codegenie.rag.store import SolvedExampleStore
from codegenie.transforms.apply_context import AttemptSummary
from codegenie.transforms.outcomes import TrustOutcome
from codegenie.types.identifiers import (
    AttemptId,
    CveId,
    EventId,
    LeafResponseId,
    ModelId,
)

__all__ = [
    "FallbackTier",
    "HarvestEligibility",
    "harvest_eligibility",
    "select_retry_summary",
    "skip_reason_for",
    "transform_from_plan",
]


# --- Helpers ---------------------------------------------------------------


def _new_event_id() -> EventId:
    return EventId("01HFTR" + uuid.uuid4().hex[:20].upper())


def _new_attempt_id() -> AttemptId:
    """Mint a fresh per-attempt :data:`AttemptId` (UUID4 hex)."""
    return AttemptId(uuid.uuid4().hex)


def _now_utc() -> datetime:
    return datetime.now(UTC)


# --- Transform projection (functional core, ``match`` exhaustiveness) ------


@dataclass(frozen=True, slots=True)
class _TransformProjection:
    """Audit-anchor projection of a :class:`PlanProposal` variant into
    the ``plan_kind`` discriminator the ``TransformBuilt`` event carries.
    """

    plan_kind: str


# --- S6-03 pure helpers ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class HarvestEligibility:
    """Sum-type tag indicating whether a :data:`PlanOutcome` is
    harvestable.

    Only :class:`AppliedFromLlm` is harvestable today — the auto-
    harvester ingests LLM-validated examples so the RAG store grows
    with real fix evidence. ``AppliedFromRecipe`` outcomes already
    have a recipe; ``RagOnlyApplicable`` and ``Refused`` carry no
    proposed plan worth re-using.
    """

    eligible: bool
    """``True`` iff the outcome is :class:`AppliedFromLlm`."""


def harvest_eligibility(outcome: PlanOutcome) -> HarvestEligibility:
    """Pure projection: is ``outcome`` harvestable?

    ``match`` exhaustiveness over the four-variant :data:`PlanOutcome`
    union (S1-03): only :class:`AppliedFromLlm` is eligible. The
    ``case _: assert_never(outcome)`` arm catches a future widening.
    """
    match outcome:
        case AppliedFromLlm():
            return HarvestEligibility(eligible=True)
        case AppliedFromRecipe():
            return HarvestEligibility(eligible=False)
        case RagOnlyApplicable():
            return HarvestEligibility(eligible=False)
        case Refused():
            return HarvestEligibility(eligible=False)
        case _ as unreachable:
            assert_never(unreachable)


def skip_reason_for(
    trust: TrustOutcome,
) -> str:
    """Project a failing :class:`TrustOutcome` into the
    :class:`HarvestSkipped.reason` closed-set Literal.

    Called only when :meth:`ConfidenceGate.passes(trust)` returned
    ``False`` — at least one clause failed:

    * ``trust.passed is False`` → ``"trust_failed"`` (clause 1 failed)
    * ``trust.confidence != "high"`` → ``"low_confidence"`` (clause 2)

    If both clauses fail, ``"trust_failed"`` takes precedence (the
    more fundamental failure).
    """
    if not trust.passed:
        return "trust_failed"
    return "low_confidence"


def _validated_outcome_from(
    *,
    outcome: AppliedFromLlm,
    context: PostValidationContext,
) -> ValidatedPlanOutcome:
    """Pure projection (``AppliedFromLlm``, ``PostValidationContext``) →
    :class:`ValidatedPlanOutcome`.

    AC-9 type guard: only ``AppliedFromLlm`` is accepted. Callers
    prove they passed the eligibility filter before invoking; a
    caller passing a different :data:`PlanOutcome` variant is a
    mypy --strict error.
    """
    return ValidatedPlanOutcome(
        query_text=context.query_text,
        plan_proposal=context.plan_proposal,
        transform_digest=context.transform_digest,
        trust_outcome_digest=context.trust_outcome_digest,
        task_class=context.task_class,
        language=context.language,
        build_system=context.build_system,
        cve_id=context.cve_id,
        advisory_digest=context.advisory_digest,
        response_id=LeafResponseId(str(outcome.response_id)),
        chain_head=context.chain_head,
    )


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


# --- S6-02 retry-bypass functional core -----------------------------------


def select_retry_summary(
    prior_attempts: Sequence[AttemptSummary],
) -> AttemptSummary:
    """Pure selector — return the most recent :class:`AttemptSummary`.

    The retry-bypass branch (ADR-04-0011) passes the last attempt's
    ``prior_failure_summary`` into :meth:`PromptBuilder.build` in place
    of the RAG few-shot. This helper makes the selection rule explicit
    and unit-testable in isolation (mirrors S6-01's
    :func:`transform_from_plan` functional-core split).

    The ``len > 0`` assertion is **defense-in-depth** — the
    ``bool(prior_attempts)`` guard in :meth:`FallbackTier.run` already
    prevents the empty case. A future refactor that flips the predicate
    would silently :class:`IndexError` without this assert; instead it
    surfaces with a clear "unreachable" message.
    """
    assert len(prior_attempts) > 0, (  # noqa: S101 — defense-in-depth invariant
        "unreachable: select_retry_summary called with no prior attempts; "
        "the bool(prior_attempts) guard in FallbackTier.run must precede this call"
    )
    return prior_attempts[-1]


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
    harvester: object = field(kw_only=True)  # Phase-4-local placeholder
    confidence_gate: ConfidenceGate = field(kw_only=True)
    store: SolvedExampleStore = field(kw_only=True)  # S6-03 — for harvest
    embedder: Embedder = field(kw_only=True)  # S6-03 — for harvest
    # S6-08 — JSONL anchor output root + per-attempt anchor parking lot.
    # ``frozen=True`` freezes attribute *rebinding*; the dict itself remains
    # mutable so :meth:`run` can stash a pending anchor for ``on_validated``
    # to recover on the success path.
    anchor_output_dir: Path = field(
        default_factory=lambda: Path(".codegenie/fallback/anchors"),
        kw_only=True,
    )
    _pending_anchors: dict[AttemptId, AttemptAnchor] = field(
        default_factory=dict, kw_only=True, repr=False, compare=False
    )

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

        **S6-08 wiring:** ``AttemptAnchorRecorded`` is the *new* terminal
        event of the per-attempt tape (emitted after
        :class:`PlanOutcomeEmitted`); refusal-path anchors additionally
        write the JSONL projection inline via
        :func:`anchor_writer.write`. Success-path anchors are parked in
        :attr:`_pending_anchors` for :meth:`on_validated` to attach
        trust + write deferredly (AC-WRITER-3).
        """
        del repo_ctx, recipe_selection
        attempt_id = _new_attempt_id()
        # S6-02 retry-bypass branch (ADR-04-0011): when prior_attempts is
        # non-empty, RAG retrieval is skipped entirely; the last attempt's
        # ``prior_failure_summary`` substitutes for the RAG few-shot in the
        # prompt. ``bool(prior_attempts)`` is the load-bearing predicate —
        # both ``()`` and ``[]`` are falsy (initial-plan path); any non-
        # empty Sequence is truthy (retry-bypass path).
        if prior_attempts:
            self._emit_rag_skipped_on_retry(prior_attempts)
        outcome: PlanOutcome = Refused(reason="PROVENANCE_NOT_APP_LAYER")
        self._emit_plan_outcome(outcome)
        anchor = self._build_refusal_anchor(
            attempt_id=attempt_id,
            cve_id=advisory.cve_id,
            reason="PROVENANCE_NOT_APP_LAYER",
            attempt_index=len(prior_attempts),
        )
        self._emit_attempt_anchor(anchor)
        anchor_writer.write(anchor, output_dir=self.anchor_output_dir)
        return outcome

    async def on_validated(
        self,
        outcome: PlanOutcome,
        trust: TrustOutcome,
        *,
        context: PostValidationContext,
    ) -> None:
        """S6-03 — inline auto-harvest dispatch.

        Six-step body (ADR-04-0009 §Decision; the original 7-step list
        in the story includes the AC-8 idempotence pre-check, deferred
        until ``SolvedExampleStore.contains()`` lands on the Protocol):

        1. ``eligibility = harvest_eligibility(outcome)`` — only
           :class:`AppliedFromLlm` is eligible. Otherwise emit
           ``HarvestSkipped(reason="outcome_not_harvestable")``.
        2. ``self.confidence_gate.passes(trust)`` — if False, emit
           ``HarvestSkipped(reason=skip_reason_for(trust))``.
        3. Mint capability via ``_phase4_local_capability_mint``.
        4. Project ``ValidatedPlanOutcome`` via
           :func:`_validated_outcome_from`.
        5. ``await ingest_solved_example(...)`` — keyword-only writer.
        6. Emit ``SolvedExampleHarvested`` with the actual returned id.
        """
        eligibility = harvest_eligibility(outcome)
        if not eligibility.eligible:
            self._emit_harvest_skipped(reason="outcome_not_harvestable", outcome_kind=outcome.kind)
            return
        if not self.confidence_gate.passes(trust):
            self._emit_harvest_skipped(
                reason=skip_reason_for(trust),
                outcome_kind=outcome.kind,
            )
            return
        # Type-narrow: eligibility guard guarantees outcome is AppliedFromLlm.
        assert isinstance(outcome, AppliedFromLlm)  # noqa: S101
        validated = _validated_outcome_from(outcome=outcome, context=context)
        capability = _phase4_local_capability_mint(
            workflow_id=context.workflow_id,
            chain_head=context.chain_head,
        )
        actual_sid = await ingest_solved_example(
            outcome=validated,
            store=self.store,
            embedder=self.embedder,
            capability=capability,
        )
        self.event_log.emit_internal(
            SolvedExampleHarvested(
                event_id=_new_event_id(),
                workflow_id=self.event_log.workflow_id,
                timestamp=_now_utc(),
                solved_example_id=actual_sid,
                embedding_model=ModelId(str(self.embedder.model_digest())),
                event_chain_head=context.chain_head,
            )
        )

    # ---- private helpers --------------------------------------------------

    def _emit_rag_skipped_on_retry(
        self,
        prior_attempts: Sequence[AttemptSummary],
    ) -> None:
        """Emit :class:`RagSkippedOnRetry` for the retry-bypass branch.

        Payload reflects the **last** attempt (``[-1]``) plus the total
        count. ``select_retry_summary`` enforces the "last attempt is the
        signal" invariant; emitting from ``[0]`` instead would be a
        regression invisible to N=1 cases.
        """
        latest = select_retry_summary(prior_attempts)
        self.event_log.emit_internal(
            RagSkippedOnRetry(
                event_id=_new_event_id(),
                workflow_id=self.event_log.workflow_id,
                timestamp=_now_utc(),
                attempt_count=len(prior_attempts),
                last_attempt_number=latest.attempt,
                last_failing_signals=latest.failing_signals,
            )
        )

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

    def finalize_success_anchor(
        self,
        attempt_id: AttemptId,
        trust: TrustOutcome,
    ) -> None:
        """S6-08 deferred-attach hook (AC-WRITER-3 / AC-PHASE5-1).

        Recovers the pending anchor stashed at :meth:`run` entry, attaches
        the post-validation :class:`TrustOutcome`, and writes the JSONL
        projection. Called by:

        * Phase 5's ``GateRunner`` success-path validator block once that
          file (``src/codegenie/gates/runner.py``) lands (AC-PHASE5-1),
          **OR**
        * The eventual S6-01 GREEN-complete ``on_validated`` body — once
          the success path stores anchors in ``_pending_anchors``.

        Both call sites are purely additive over today's Phase-5 / S6-01
        partial-builds. ``finalize_success_anchor`` is a no-op when the
        anchor was never parked (defensive — refusal-path anchors are
        written inline in :meth:`run` and never reach here).
        """
        anchor = self._pending_anchors.pop(attempt_id, None)
        if anchor is None:
            return
        attached = anchor.attach_trust_outcome(trust)
        anchor_writer.write(attached, output_dir=self.anchor_output_dir)

    def _build_refusal_anchor(
        self,
        *,
        attempt_id: AttemptId,
        cve_id: CveId,
        reason: str,
        attempt_index: int,
    ) -> AttemptAnchor:
        """Construct a refusal-path :class:`AttemptAnchor` — the five LLM-
        derived fields stay ``None`` (early-refusal paths short-circuit
        before any prompt is built; AC-SCHEMA-1)."""
        return AttemptAnchor(
            attempt_id=attempt_id,
            workflow_id=self.event_log.workflow_id,
            cve_id=cve_id,
            timestamp_utc=_now_utc(),
            attempt_index=attempt_index,
            plan_proposal_kind="refuse",
            validator_outcome="Refused",
            refusal_reason=reason,  # type: ignore[arg-type]
        )

    def _emit_attempt_anchor(self, anchor: AttemptAnchor) -> None:
        """Emit the terminal :class:`AttemptAnchorRecorded` event
        (eleventh event of S6-01's per-step tape; ADR-04-0017)."""
        self.event_log.emit_internal(
            AttemptAnchorRecorded(
                event_id=_new_event_id(),
                workflow_id=self.event_log.workflow_id,
                timestamp=_now_utc(),
                attempt_id=anchor.attempt_id,
                anchor=anchor.model_dump(mode="json"),
            )
        )

    def _emit_harvest_skipped(
        self,
        *,
        reason: str,
        outcome_kind: str,
    ) -> None:
        """Emit a :class:`HarvestSkipped` event with the closed-set
        ``reason`` and the gate's ``plan_outcome_kind`` discriminator."""
        self.event_log.emit_internal(
            HarvestSkipped(
                event_id=_new_event_id(),
                workflow_id=self.event_log.workflow_id,
                timestamp=_now_utc(),
                reason=reason,  # type: ignore[arg-type]
                plan_outcome_kind=outcome_kind,  # type: ignore[arg-type]
            )
        )
