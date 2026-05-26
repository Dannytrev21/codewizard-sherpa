"""Phase-4 S6-03 AC-2 — :class:`PostValidationContext` shape pinning."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from codegenie.fallback.plan_proposal import PlanProposalDepBump
from codegenie.fallback.post_validation_context import PostValidationContext
from codegenie.types.identifiers import (
    BlobDigest,
    ChainHead,
    CveId,
    Language,
    PackageId,
    SemverVersion,
    TaskClassId,
    WorkflowId,
)


def _ctx_kwargs() -> dict[str, object]:
    plan = PlanProposalDepBump(
        manifest_path="package.json",
        package=PackageId("a@1.0.0"),
        target_version=SemverVersion("1.0.1"),
        rationale="patch",
    )
    return {
        "workflow_id": WorkflowId("wf-001"),
        "chain_head": ChainHead("a" * 64),
        "advisory_digest": BlobDigest("0" * 64),
        "cve_id": CveId("CVE-2026-1234"),
        "task_class": TaskClassId("vuln_remediation"),
        "language": Language("typescript"),
        "build_system": "npm",
        "transform_digest": BlobDigest("1" * 64),
        "trust_outcome_digest": BlobDigest("2" * 64),
        "query_text": "fix the CVE",
        "plan_proposal": plan,
    }


def test_ac2_post_validation_context_constructs_with_eleven_fields() -> None:
    """All 11 typed fields populate; the model accepts the canonical kwargs."""
    ctx = PostValidationContext(**_ctx_kwargs())  # type: ignore[arg-type]
    assert ctx.workflow_id == "wf-001"
    assert ctx.cve_id == "CVE-2026-1234"


def test_ac2_post_validation_context_is_frozen() -> None:
    """Mutation post-construction raises (frozen=True)."""
    ctx = PostValidationContext(**_ctx_kwargs())  # type: ignore[arg-type]
    with pytest.raises(Exception):  # noqa: B017 — pydantic frozen error
        ctx.workflow_id = WorkflowId("wf-002")  # type: ignore[misc]


def test_ac2_post_validation_context_rejects_extra_fields() -> None:
    """extra='forbid' catches an orchestrator that drifts the field set."""
    kwargs = _ctx_kwargs()
    kwargs["unexpected"] = "field"
    with pytest.raises(ValidationError, match="unexpected"):
        PostValidationContext(**kwargs)  # type: ignore[arg-type]


def test_ac2_post_validation_context_all_eleven_fields_required() -> None:
    """No defaults — dropping any field raises ValidationError."""
    full = _ctx_kwargs()
    for field_name in list(full.keys()):
        kwargs = {k: v for k, v in full.items() if k != field_name}
        with pytest.raises(ValidationError):
            PostValidationContext(**kwargs)  # type: ignore[arg-type]
