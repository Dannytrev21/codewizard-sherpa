"""Phase-4 S6-03 AC-2 — :class:`PostValidationContext` orchestrator-stamped record.

The :meth:`FallbackTier.on_validated` body needs 11 typed fields to
build the :class:`ValidatedPlanOutcome` that S4-06's
``ingest_solved_example`` consumes. Those fields are not all present
on the ``(outcome, trust)`` pair the original story signature passed —
the additive-widening fix (S6-03 §"Changes applied") moves them onto
this orchestrator-stamped context that :meth:`on_validated` receives
keyword-only.

Frozen + ``extra="forbid"``: mirrors the rest of
``codegenie/fallback/`` config. No methods. No ``dict[str, Any]``
escape hatch — every field is typed.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict

from codegenie.fallback.plan_proposal import PlanProposal
from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    CveId,
    Language,
    PackageManager,
    TaskClassId,
    WorkflowId,
)

__all__ = [
    "PostValidationContext",
]


_FROZEN_FORBID: Final[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


class PostValidationContext(BaseModel):
    """Orchestrator-stamped per-validated-run context.

    Phase-3/Phase-5 orchestrator constructs this once per validated
    fallback-tier run (after the Phase-5 ``GateRunner`` reports a
    passing :class:`TrustOutcome`) and hands it to
    :meth:`FallbackTier.on_validated` keyword-only. The FallbackTier
    itself stays stateless (S6-01 invariant); the context is the
    pure-data bridge.

    Eleven typed fields — every one is needed to build the
    :class:`ValidatedPlanOutcome` for S4-06's
    ``ingest_solved_example(*, outcome=...)``. No optionality (every
    field is required); no defaults; ``extra="forbid"`` rejects an
    orchestrator that drifts the field set.
    """

    model_config = _FROZEN_FORBID

    workflow_id: WorkflowId
    chain_head: ChainHead
    advisory_digest: BlobDigest
    cve_id: CveId
    task_class: TaskClassId
    language: Language
    build_system: PackageManager
    transform_digest: BlobDigest
    trust_outcome_digest: BlobDigest
    query_text: str
    plan_proposal: PlanProposal
