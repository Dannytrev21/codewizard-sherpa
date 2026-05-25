"""Phase-4 S4-06 — ``ingest_solved_example`` writer + ``ValidatedPlanOutcome``.

The Phase-4 solved-example writer surface. Builds a canonical
:class:`~codegenie.rag.models.SolvedExample` from a validated plan
outcome, embeds the surface query text, and calls
:meth:`SolvedExampleStore.add` once. Returns the assigned
:data:`SolvedExampleId`.

**The writer is silent.** It does NOT inspect ``TrustOutcome.confidence``
and does NOT emit :class:`SolvedExampleHarvested`. The caller-side
confidence gate (``TrustOutcome.passed AND confidence == "high"``) and
event emission are S6-03's responsibility — keeping the writer policy-
free preserves the Specification pattern boundary the final-design pins
(Notes §3, Component 9).

**Module boundary.** The interim Phase-4 capability mint
(:func:`_phase4_local_capability_mint`) lives in the sibling private
module :mod:`codegenie.rag._capability_mint`. This module imports it by
*alias only*; the function is intentionally absent from this module's
namespace (``__all__`` excludes it; ``from codegenie.rag.ingest import
_phase4_local_capability_mint`` fails). The boundary is mechanically
enforced by the ``pyproject.toml`` import-linter contract
``"ADR-0016: phase4 solved-example mint module is scoped"`` plus the
AST fences in ``tests/fence/test_phase4_capability_mint_scope.py``.

**Functional core / imperative shell.** Pure helpers
(:func:`_canonical_identity_bytes`, :func:`_solved_example_id_for`,
:func:`_solved_example_from_outcome`) carry the logic; only
:func:`ingest_solved_example` is impure.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Final

import blake3
from pydantic import BaseModel, ConfigDict

from codegenie.fallback.plan_proposal import PlanProposal
from codegenie.rag import _capability_mint as _capability_mint_module  # noqa: F401
from codegenie.rag.embedder import Embedder
from codegenie.rag.models import RecordProvenance, SolvedExample
from codegenie.rag.store import SolvedExampleStore, SolvedExampleWriteCapability
from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    CveId,
    EmbeddingVector,
    Language,
    LeafResponseId,
    ModelId,
    PackageManager,
    SolvedExampleId,
    TaskClassId,
)

_FROZEN_FORBID: Final[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


# ---------------------------------------------------------------------------
# ValidatedPlanOutcome — projection input for the inline harvester
# ---------------------------------------------------------------------------


class ValidatedPlanOutcome(BaseModel):
    """Frozen, extra-forbid projection of a validated remediation outcome.

    Carries exactly the stable inputs needed to build a
    :class:`~codegenie.rag.models.SolvedExample`. No
    ``dict[str, Any]`` escape hatch, no ``confidence`` field — the
    caller's confidence gate has already passed by the time this lands
    in the writer (Notes §3).
    """

    model_config = _FROZEN_FORBID
    query_text: str
    plan_proposal: PlanProposal
    transform_digest: BlobDigest
    trust_outcome_digest: BlobDigest
    task_class: TaskClassId
    language: Language
    build_system: PackageManager
    cve_id: CveId
    advisory_digest: BlobDigest
    response_id: LeafResponseId
    chain_head: ChainHead


# ---------------------------------------------------------------------------
# Pure helpers — functional core
# ---------------------------------------------------------------------------


def _canonical_identity_bytes(
    *,
    outcome: ValidatedPlanOutcome,
    embedding_model: ModelId,
) -> bytes:
    """Canonical JSON bytes over the five identity fields.

    The set is closed and ordered: ``cve_id``, ``advisory_digest``,
    ``transform_digest``, ``trust_outcome_digest``, ``embedding_model``.
    Sorted keys + tight separators give us the same byte sequence on
    every Python build (S4-05 ``canonical_json_bytes`` pattern). Workflow
    context (``workflow_id``, ``chain_head``, ``created_at``,
    ``query_text``, ``response_id``) is intentionally excluded — the
    same vulnerable code/fix should yield the same record id no matter
    which workflow or replay path produced it (AC-3).
    """
    payload = {
        "cve_id": str(outcome.cve_id),
        "advisory_digest": str(outcome.advisory_digest),
        "transform_digest": str(outcome.transform_digest),
        "trust_outcome_digest": str(outcome.trust_outcome_digest),
        "embedding_model": str(embedding_model),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _solved_example_id_for(
    *,
    outcome: ValidatedPlanOutcome,
    embedding_model: ModelId,
) -> SolvedExampleId:
    """Deterministic :data:`SolvedExampleId` over the five identity fields.

    BLAKE3 hex over :func:`_canonical_identity_bytes`. AC-3 pins the
    field-sensitivity contract: same identity inputs → same id; any
    identity field flipped → different id; workflow-context field
    flipped → unchanged id.
    """
    digest = blake3.blake3(
        _canonical_identity_bytes(outcome=outcome, embedding_model=embedding_model)
    ).hexdigest()
    return SolvedExampleId(digest)


def _solved_example_from_outcome(
    *,
    outcome: ValidatedPlanOutcome,
    embedding_model: ModelId,
    embedding_vector: EmbeddingVector,
    capability: SolvedExampleWriteCapability,
    now: datetime,
) -> SolvedExample:
    """Pure :class:`SolvedExample` builder.

    Routes ``capability.workflow_id`` and ``outcome.chain_head`` into
    the four hardened S1-04 :class:`RecordProvenance` fields. The
    stale-name guard in ``tests/unit/rag/test_ingest.py`` pins absence
    of pre-hardening fields.

    Raises :class:`TypeError` if ``outcome.plan_proposal`` is a refusal —
    refused plans are not harvestable, and the
    :class:`~codegenie.rag.models.SolvedExample.plan_kind` literal
    forbids ``"refuse"`` at the type level. The fail-loud raise (Rule 12)
    is more informative than the inner Pydantic ``ValidationError``.
    """
    plan_kind = outcome.plan_proposal.kind
    if plan_kind == "refuse":
        raise TypeError(
            "refused plans are not harvestable as solved examples (plan_proposal.kind == 'refuse')"
        )
    sid = _solved_example_id_for(outcome=outcome, embedding_model=embedding_model)
    provenance = RecordProvenance(
        workflow_id=capability.workflow_id,
        event_chain_head=outcome.chain_head,
        created_at=now,
        signing_method="hmac_sha256_chain",
    )
    return SolvedExample(
        id=sid,
        task_class=outcome.task_class,
        language=outcome.language,
        build_system=outcome.build_system,
        cve_id=outcome.cve_id,
        advisory_digest=outcome.advisory_digest,
        plan_kind=plan_kind,
        plan_proposal=outcome.plan_proposal,
        transform_digest=outcome.transform_digest,
        trust_outcome_digest=outcome.trust_outcome_digest,
        provenance=provenance,
        origin="llm_solved",
        embedding_model=embedding_model,
        embedding_vector=embedding_vector,
        created_at=now,
    )


# ---------------------------------------------------------------------------
# ingest_solved_example — the impure shell
# ---------------------------------------------------------------------------


async def ingest_solved_example(
    *,
    outcome: ValidatedPlanOutcome,
    store: SolvedExampleStore,
    embedder: Embedder,
    capability: SolvedExampleWriteCapability,
) -> SolvedExampleId:
    """Persist one solved example. Returns the assigned id.

    AC-2 contract:

    1. exactly one :meth:`Embedder.model_digest` call;
    2. exactly one :meth:`Embedder.embed` call over
       ``outcome.query_text``;
    3. exactly one :meth:`SolvedExampleStore.add` call;
    4. UTC-aware ``created_at`` for both the record and its provenance.

    The function never reads ``confidence`` and never touches any
    :class:`~codegenie.plugins.events.EventLog` surface — caller-side
    policy + emission are S6-03's responsibility (Notes §3/§4). The
    ``ModelId(str(embedder.model_digest()))`` line is the boundary
    adapter S1-04 still mandates between
    :data:`~codegenie.types.identifiers.BlobDigest` and
    :data:`~codegenie.types.identifiers.ModelId` (Notes §6).
    """
    embedding_model = ModelId(str(embedder.model_digest()))
    vector = embedder.embed(outcome.query_text)
    now = datetime.now(UTC)
    example = _solved_example_from_outcome(
        outcome=outcome,
        embedding_model=embedding_model,
        embedding_vector=vector,
        capability=capability,
        now=now,
    )
    return await store.add(example, capability)


__all__ = (
    "ValidatedPlanOutcome",
    "_solved_example_id_for",
    "ingest_solved_example",
)
