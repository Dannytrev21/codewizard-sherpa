"""Phase-4 S4-03 fixture builders for :class:`SolvedExample` / :class:`Query`.

Both ``make_solved_example`` and ``make_query_matching`` hand back the
sensible-defaulted Pydantic models S4-03 tests need (S1-04 ships the
models themselves). The single boundary lift of raw ``str`` → newtyped
identifiers happens here so individual tests stay free of
identifier-construction noise.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from codegenie.fallback.plan_proposal import PlanProposalDepBump
from codegenie.rag.models import (
    FailureModeTag,
    Query,
    RecordProvenance,
    SolvedExample,
)
from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    CveId,
    EmbeddingVector,
    Language,
    ModelId,
    PackageId,
    PackageManager,
    SemverVersion,
    SolvedExampleId,
    TaskClassId,
    WorkflowId,
)

_EMBEDDING_DIM = 384
_ZERO_DIGEST_64 = "0" * 64


def _default_embedding(seed: float = 0.5) -> EmbeddingVector:
    """384-element tuple of ``float``s shaped like S4-01's BGE-small output."""
    return EmbeddingVector(tuple(float(seed) for _ in range(_EMBEDDING_DIM)))


def make_solved_example(
    *,
    id_: str = "ex-001",
    task_class: str = "vuln_remediation",
    language: str = "typescript",
    build_system: PackageManager = "npm",
    cve_id: str = "CVE-2026-1234",
    embedding_vector: EmbeddingVector | None = None,
    origin: Literal["llm_solved", "operator_curated", "phase11_merge_webhook"] = "llm_solved",
    event_chain_head: str = "c" * 64,
) -> SolvedExample:
    """Build a valid :class:`SolvedExample` with sensible defaults.

    ``embedding_vector`` defaults to a 384-element tuple of constant
    floats (see ``_default_embedding``). Callers that need to verify a
    round-trip use the same defaults so the round-trip test isn't
    coupled to the embedder.
    """
    plan = PlanProposalDepBump(
        manifest_path="package.json",
        package=PackageId(f"{cve_id.lower()}@1.0.0"),
        target_version=SemverVersion("1.0.1"),
        rationale="cve-fix",
    )
    return SolvedExample(
        id=SolvedExampleId(id_),
        task_class=TaskClassId(task_class),
        language=Language(language),
        build_system=build_system,
        cve_id=CveId(cve_id),
        advisory_digest=BlobDigest(_ZERO_DIGEST_64),
        plan_kind="dep_bump",
        plan_proposal=plan,
        transform_digest=BlobDigest(_ZERO_DIGEST_64),
        trust_outcome_digest=BlobDigest(_ZERO_DIGEST_64),
        provenance=RecordProvenance(
            workflow_id=WorkflowId("wf-fixture"),
            event_chain_head=ChainHead(event_chain_head),
            created_at=datetime(2026, 5, 25, tzinfo=UTC),
            signing_method="hmac_sha256_chain",
        ),
        origin=origin,
        embedding_model=ModelId("BAAI/bge-small-en-v1.5"),
        embedding_vector=embedding_vector if embedding_vector is not None else _default_embedding(),
        created_at=datetime(2026, 5, 25, tzinfo=UTC),
    )


def make_query_matching(
    example: SolvedExample,
    *,
    failure_mode: FailureModeTag = "build_break",
) -> Query:
    """Build a :class:`Query` whose partition triple matches ``example``.

    Lets the S4-03 round-trip test issue a query whose partition lookup
    lands in the same chromadb collection the seed record was added to,
    without spelling the partition triple twice in the test.
    """
    return Query(
        task_class=example.task_class,
        language=example.language,
        build_system=example.build_system,
        cve_id=example.cve_id,
        affected_package=PackageId(f"{example.cve_id.lower()}@1.0.0"),
        failure_mode=failure_mode,
    )
