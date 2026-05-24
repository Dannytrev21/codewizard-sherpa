"""Phase-4 S1-04 — happy/sad-path tests for the five RAG-side Pydantic models.

Covers AC-1 through AC-5 / AC-8 / AC-9 / AC-10 / AC-13 / AC-16 / AC-17 for the
``codegenie.rag`` package; the budget-side models (AC-6 / AC-7 / AC-18) live in
``tests/unit/fallback/test_budget_models.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.rag.models import (
    Query,
    RagDegraded,
    RagHit,
    RagMiss,
    RecordProvenance,
    RetrievalOutcome,
    SolvedExample,
    TypecheckNodeSignal,
)

_HEX64 = "a" * 64
_UTC_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_PROV = {
    "workflow_id": "01HXX00000000000000000000Z",
    "event_chain_head": _HEX64,
    "created_at": _UTC_NOW,
    "signing_method": "hmac_sha256_chain",
}
_PLAN_DEPBUMP = {
    "kind": "dep_bump",
    "manifest_path": "package.json",
    "package": "lodash@4.17.21",
    "target_version": "4.17.21",
    "rationale": "x",
}
_SOLVED = {
    "id": _HEX64,
    "task_class": "vuln_remediation",
    "language": "typescript",
    "build_system": "npm",
    "cve_id": "CVE-2026-1234",
    "advisory_digest": _HEX64,
    "plan_kind": "dep_bump",
    "plan_proposal": _PLAN_DEPBUMP,
    "transform_digest": _HEX64,
    "trust_outcome_digest": _HEX64,
    "provenance": _PROV,
    "origin": "llm_solved",
    "embedding_model": "bge-small-en-v1.5",
    "created_at": _UTC_NOW,
}
_QUERY = {
    "task_class": "vuln_remediation",
    "language": "typescript",
    "build_system": "npm",
    "cve_id": "CVE-2026-1234",
    "affected_package": "express@4.18.0",
    "failure_mode": "build_break",
}
_RAG_HIT = {"kind": "hit", "few_shot": _SOLVED, "score": 0.96}
_RAG_MISS = {"kind": "miss"}
_RAG_DEGRADED = {"kind": "degraded", "near_match": _SOLVED, "score": 0.70}
_TYPECHECK = {"passed": True, "details": {"errors": 0}, "confidence": "high"}

# (model_cls, valid_payload, a_field_to_probe_for_frozen) — drives the
# parametrized extra="forbid" / frozen checks over every RAG-side model.
_MODEL_CASES = [
    (SolvedExample, _SOLVED, "cve_id"),
    (Query, _QUERY, "cve_id"),
    (RecordProvenance, _PROV, "signing_method"),
    (RagHit, _RAG_HIT, "score"),
    (RagMiss, _RAG_MISS, "kind"),
    (RagDegraded, _RAG_DEGRADED, "score"),
    (TypecheckNodeSignal, _TYPECHECK, "passed"),
]


_EXPECTED_KEYS = {
    SolvedExample: {
        "id",
        "task_class",
        "language",
        "build_system",
        "cve_id",
        "advisory_digest",
        "plan_kind",
        "plan_proposal",
        "transform_digest",
        "trust_outcome_digest",
        "provenance",
        "origin",
        "embedding_model",
        "created_at",
    },
    Query: {
        "task_class",
        "language",
        "build_system",
        "cve_id",
        "affected_package",
        "failure_mode",
    },
    RecordProvenance: {"workflow_id", "event_chain_head", "created_at", "signing_method"},
    RagHit: {"kind", "few_shot", "score"},
    RagMiss: {"kind"},
    RagDegraded: {"kind", "near_match", "score"},
    TypecheckNodeSignal: {"kind", "passed", "details", "confidence"},
}


def test_solved_example_happy() -> None:
    s = SolvedExample.model_validate(_SOLVED)
    assert s.id == _HEX64
    assert s.created_at == _UTC_NOW


# --- extra="forbid" / frozen / keyset — parametrized over every model (AC-10) ---


@pytest.mark.parametrize("model_cls,payload,_field", _MODEL_CASES)
def test_extra_keys_rejected(model_cls, payload, _field) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationError):
        model_cls.model_validate({**payload, "shell": "rm -rf"})


@pytest.mark.parametrize("model_cls,payload,field", _MODEL_CASES)
def test_frozen_rejects_assignment(model_cls, payload, field) -> None:  # type: ignore[no-untyped-def]
    instance = model_cls.model_validate(payload)
    with pytest.raises(ValidationError):
        setattr(instance, field, getattr(instance, field))


@pytest.mark.parametrize("model_cls,payload,_field", _MODEL_CASES)
def test_keyset_pinned(model_cls, payload, _field) -> None:  # type: ignore[no-untyped-def]
    dumped = model_cls.model_validate(payload).model_dump()
    assert set(dumped) == _EXPECTED_KEYS[model_cls]


# --- tz-aware datetime enforcement (AC-13; BudgetToken.issued_at in fallback file) ---


@pytest.mark.parametrize(
    "model_cls,payload",
    [(SolvedExample, _SOLVED), (RecordProvenance, _PROV)],
)
def test_naive_datetime_rejected(model_cls, payload) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationError):
        model_cls.model_validate({**payload, "created_at": datetime(2026, 1, 1)})


@pytest.mark.parametrize(
    "model_cls,payload",
    [(SolvedExample, _SOLVED), (RecordProvenance, _PROV)],
)
def test_tz_aware_datetime_accepted(model_cls, payload) -> None:  # type: ignore[no-untyped-def]
    instance = model_cls.model_validate({**payload, "created_at": _UTC_NOW})
    assert instance.created_at == _UTC_NOW


# --- Literal-field rejection (AC-16) ---


@pytest.mark.parametrize(
    "model_cls,payload,field,bad",
    [
        (SolvedExample, _SOLVED, "plan_kind", "unknown_kind"),
        (SolvedExample, _SOLVED, "origin", "scraped"),
        (RecordProvenance, _PROV, "signing_method", "pgp_clearsign"),
        (TypecheckNodeSignal, _TYPECHECK, "confidence", "certain"),
        (Query, _QUERY, "failure_mode", "freeform"),
    ],
)
def test_literal_field_rejects_out_of_set(model_cls, payload, field, bad) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationError):
        model_cls.model_validate({**payload, field: bad})


# --- Query.digest() ---


def test_query_digest_is_64_hex_lowercase() -> None:
    d = Query.model_validate(_QUERY).digest()
    assert len(d) == 64
    assert all(c in "0123456789abcdef" for c in d)


def test_query_digest_deterministic() -> None:
    assert Query.model_validate(_QUERY).digest() == Query.model_validate(_QUERY).digest()


@pytest.mark.parametrize(
    "field,value",
    [
        ("task_class", "container_migration"),
        ("language", "javascript"),
        ("build_system", "pnpm"),
        ("cve_id", "CVE-2026-9999"),
        ("affected_package", "lodash@4.17.21"),
        ("failure_mode", "test_fail"),
    ],
)
def test_query_digest_changes_with_each_field(field, value) -> None:  # type: ignore[no-untyped-def]
    base = Query.model_validate(_QUERY)
    perturbed = Query.model_validate({**_QUERY, field: value})
    assert base.digest() != perturbed.digest()


# --- RetrievalOutcome discriminated union ---


def test_rag_hit_happy() -> None:
    rh = RagHit.model_validate(_RAG_HIT)
    assert isinstance(rh.few_shot, SolvedExample)
    assert rh.score == 0.96


def test_rag_degraded_happy() -> None:
    rd = RagDegraded.model_validate(_RAG_DEGRADED)
    assert isinstance(rd.near_match, SolvedExample)


def test_rag_miss_is_bare() -> None:
    rm = RagMiss.model_validate(_RAG_MISS)
    assert rm.kind == "miss"
    assert set(rm.model_dump()) == {"kind"}


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "hit", "score": 0.9},
        {"kind": "degraded", "score": 0.7},
    ],
)
def test_rag_hit_degraded_require_payload(payload) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValidationError):
        TypeAdapter(RetrievalOutcome).validate_python(payload)


def test_retrieval_outcome_routes_by_kind() -> None:
    adapter = TypeAdapter(RetrievalOutcome)
    assert isinstance(adapter.validate_python(_RAG_HIT), RagHit)
    assert isinstance(adapter.validate_python(_RAG_MISS), RagMiss)
    assert isinstance(adapter.validate_python(_RAG_DEGRADED), RagDegraded)


def test_retrieval_outcome_unknown_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(RetrievalOutcome).validate_python({"kind": "exception", "trace": "..."})


# --- score range constraint (AC-17) ---


@pytest.mark.parametrize("score", [1.5, -1.5, 2.0])
def test_rag_hit_score_out_of_range_rejected(score: float) -> None:
    with pytest.raises(ValidationError):
        RagHit.model_validate({**_RAG_HIT, "score": score})


@pytest.mark.parametrize("score", [-1.0, 0.0, 0.85, 1.0])
def test_rag_hit_score_in_band_accepted(score: float) -> None:
    assert RagHit.model_validate({**_RAG_HIT, "score": score}).score == score


# --- TypecheckNodeSignal ---


def test_typecheck_signal_kind_pinned() -> None:
    assert TypecheckNodeSignal.model_validate(_TYPECHECK).kind == "typecheck.typescript"
