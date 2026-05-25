"""Phase-4 S1-04 — RAG-side Pydantic v2 contract surface.

Every downstream Phase-4 consumer (``SolvedExampleStore``,
``SolvedExampleRetriever``, ``LlmInvocationGuard``, ``TrustScorer.fold``)
is typed against the frozen-extra-forbid models in this module. They land
*together* in Step 1 because each is a contract surface — the alternative
(landing them lazily per-consumer) produces the "fix-the-shape-and-
everything-breaks" cascade Step 1 exists to prevent.

References:
- ``docs/phases/04-vuln-llm-fallback-rag/phase-arch-design.md §Data model``
- ``docs/phases/04-vuln-llm-fallback-rag/ADRs/0008-two-threshold-calibration-band.md``
  — ``RetrievalOutcome`` three-way union.
- ``docs/phases/04-vuln-llm-fallback-rag/ADRs/0016-chromadb-embedded-yaml-canonical-store.md``
  — ``SolvedExample`` is the persisted YAML record; ``RecordProvenance``
  carries the chain-verify anchor.
- Phase-4 ADR-0015 (typecheck-typescript-signal-and-tsc-allowed-binary)
  — ``TypecheckNodeSignal`` mirrors the Phase-3 ``TrustSignal`` shape.
- ``docs/production/adrs/0033-domain-modeling-discipline.md`` — frozen-
  extra-forbid as the default; primitive obsession on domain IDs blocks review.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Final, Literal, Self

import blake3
import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from codegenie.fallback.plan_proposal import PlanProposal
from codegenie.types.datetime import TzAwareDatetime
from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    CveId,
    EmbeddingVector,
    Language,
    ModelId,
    PackageId,
    PackageManager,
    Similarity,
    SolvedExampleId,
    TaskClassId,
    WorkflowId,
)

# --- Module-level closed-set literals -------------------------------------

FailureModeTag = Literal[
    "build_break",
    "test_fail",
    "typecheck_fail",
    "lockfile_resolution_fail",
    "callsite_signature_drift",
    "policy_block",
]
"""Six remediation-failure tags Phase-4 fixtures cover.

Kept rag-local rather than promoted to ``codegenie.types.identifiers``: the
codebase's two competing precedents are closed-set Literals like
``PackageManager`` (kernel-tier) vs. domain *reason* taxonomies like
``NotApplicableReason``/``EscalationReason`` (module-local). This is a
remediation-failure vocabulary — closer to the reason-taxonomy precedent.
"""

_FROZEN_FORBID: Final[ConfigDict] = ConfigDict(frozen=True, extra="forbid")
"""Single-source the model config across this module (Rule 11 mirrors the
``plan_proposal.py`` constant); no shared ``FrozenModel`` base — 40+ models
in this codebase repeat ``ConfigDict`` inline by convention."""


# --- RecordProvenance -----------------------------------------------------


class RecordProvenance(BaseModel):
    """Chain-verify input attached to every persisted ``SolvedExample``.

    ``event_chain_head`` is the spanning-log head this record was witnessed
    at; S4-05 reconciles each record against the canonical chain (ADR-0016).
    """

    model_config = _FROZEN_FORBID
    workflow_id: WorkflowId
    event_chain_head: ChainHead
    created_at: TzAwareDatetime
    signing_method: Literal["hmac_sha256_chain", "operator_attestation"]


# --- Query ----------------------------------------------------------------


class Query(BaseModel):
    """Typed-fields retrieval input — no f-string-built prompts (ADR-0001).

    ``digest()`` is the cache key consumed by ``SolvedExampleStore`` /
    ``SolvedExampleRetriever`` (Components 7/9 in the arch). Determinism +
    field-sensitivity are the load-bearing properties (AC-11 mutation guard).
    """

    model_config = _FROZEN_FORBID
    task_class: TaskClassId
    language: Language
    build_system: PackageManager
    cve_id: CveId
    affected_package: PackageId
    failure_mode: FailureModeTag

    def digest(self) -> BlobDigest:
        """BLAKE3-hex over the model's canonical JSON serialisation.

        Pydantic v2 ``model_dump_json`` emits fields in definition order —
        stable across runs for a frozen model — so the dump is deterministic
        without an explicit key sort. Returns 64 lowercase hex chars.
        """
        digest_hex = blake3.blake3(self.model_dump_json().encode("utf-8")).hexdigest()
        return BlobDigest(digest_hex)


# --- SolvedExample --------------------------------------------------------


class SolvedExample(BaseModel):
    """The persisted YAML record S4-04 owns canonically.

    CONTRACT — persisted in ChromaDB; Phase 5 reads ``embedding_model``
    against the embedder's ``model_digest()`` (S5-03 model-mismatch
    exclusion); ``provenance.event_chain_head`` is the chain anchor S4-05
    verifies. ADR-0016 mandates that records carry the embedding *vector*
    alongside the model digest so ``codegenie rag rebuild`` can re-insert
    into chromadb without re-embedding — ``embedding_vector`` is that
    vector (a 384-element tuple of Python floats per the BGE-small
    contract; tuple-shape enforced at the embedder boundary in S4-01).
    """

    model_config = _FROZEN_FORBID
    id: SolvedExampleId
    task_class: TaskClassId
    language: Language
    build_system: PackageManager
    cve_id: CveId
    advisory_digest: BlobDigest
    plan_kind: Literal["dep_bump", "override", "callsite_rewrite"]
    plan_proposal: PlanProposal
    transform_digest: BlobDigest
    trust_outcome_digest: BlobDigest
    provenance: RecordProvenance
    origin: Literal["llm_solved", "operator_curated", "phase11_merge_webhook"]
    embedding_model: ModelId
    embedding_vector: EmbeddingVector
    created_at: TzAwareDatetime

    @classmethod
    def from_yaml(cls, path: Path) -> Self:
        """S4-04 AC-10 — convenience parser used by S4-07's
        ``codegenie rag rebuild`` to rehydrate canonical YAML records.

        Shares the exact ``model_validate(yaml.safe_load(...))`` parse
        core the S4-04 Hypothesis roundtrip property exercises. Errors
        surface as :class:`pydantic.ValidationError` — S4-07 wraps them.
        """
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


# --- RetrievalOutcome -----------------------------------------------------


class RagHit(BaseModel):
    """Confident retrieval: ``score >= high_floor`` (ADR-0008 §Decision).

    Carries a few-shot record fed to the LLM as an exemplar.
    """

    model_config = _FROZEN_FORBID
    kind: Literal["hit"] = "hit"
    few_shot: SolvedExample
    score: Annotated[Similarity, Field(ge=-1.0, le=1.0)]


class RagMiss(BaseModel):
    """Bare retrieval miss — no payload (ADR-0008 §Decision).

    Chain-orphan / model-mismatch observability lives in the emitted
    ``RagRecordChainOrphan`` / ``RagRecordModelMismatch`` events (arch
    edge cases #14, #19), NOT in a ``RagMiss.reason`` field. Adding a
    ``reason`` is an ADR-0008 widening amendment.
    """

    model_config = _FROZEN_FORBID
    kind: Literal["miss"] = "miss"


class RagDegraded(BaseModel):
    """Near-match returned below ``high_floor`` and at-or-above ``degraded_floor``.

    Fed to the LLM with a low-confidence tag (ADR-0008 §Pattern-fit). The
    ``few_shot`` vs ``near_match`` field-name distinction from ``RagHit`` is
    intentional — ADR-0008 §Pattern-fit.
    """

    model_config = _FROZEN_FORBID
    kind: Literal["degraded"] = "degraded"
    near_match: SolvedExample
    score: Annotated[Similarity, Field(ge=-1.0, le=1.0)]


RetrievalOutcome = Annotated[
    RagHit | RagMiss | RagDegraded,
    Field(discriminator="kind"),
]
"""Closed three-way union ADR-0008 §Decision pins.

``Field(discriminator="kind")`` is the implemented repo convention
(``transforms/outcomes.py``); S1-02/S1-03 corrected the same arch-doc
``Discriminator(...)`` drift.
"""


# --- TypecheckNodeSignal --------------------------------------------------


class TypecheckNodeSignal(BaseModel):
    """Phase-3-shaped ``TrustSignal`` for the TypeScript ``tsc`` collector.

    The *collector* (which wraps ``tsc`` and ``@register_signal_kind``s this
    model) is plugin-resident at S6-05; this story ships the model alone.
    Substrate-resident-for-reuse — ADR-0015 anticipates Phase-7 plugins
    reusing the shape.
    """

    model_config = _FROZEN_FORBID
    kind: Literal["typecheck.typescript"] = "typecheck.typescript"
    passed: bool
    details: dict[str, str | int | bool]
    confidence: Literal["high", "medium", "low"]


__all__: Final[tuple[str, ...]] = (
    "FailureModeTag",
    "Query",
    "RagDegraded",
    "RagHit",
    "RagMiss",
    "RecordProvenance",
    "RetrievalOutcome",
    "SolvedExample",
    "TypecheckNodeSignal",
)
