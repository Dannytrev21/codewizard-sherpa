"""Phase-4 S4-04 — Hypothesis YAML round-trip property (AC-6).

Property: ``SolvedExample.model_validate(yaml.safe_load(_canonical_yaml_dump(x))) == x``
for every valid ``SolvedExample`` ``x``. This is the load-bearing schema
discipline that makes ``codegenie rag rebuild`` (S4-07) deterministic.

Discipline:

- **Explicit per-field strategy.** ``st.builds(SolvedExample, ...)`` with
  inference would fail on the newtype / ``EmbeddingVector`` / nested
  ``RecordProvenance`` / ``datetime`` fields, or generate degenerate
  values that prove nothing. Every field has a bound strategy.
- **Non-degeneracy assertion inline** — ``len(x.embedding_vector) == 384``.
- **Routes through ``_canonical_yaml_dump``**, the same serialisation
  surface ``add()`` uses; the property therefore guards the real code
  path, not a hand-inlined ``safe_dump``.
- **Key-order-independent.** ``safe_load`` parses into a dict regardless
  of key order — the property does NOT guard ``sort_keys=True``. The
  sorted-key discipline is pinned by AC-1's full-ordering assertion in
  ``tests/unit/rag/test_store_yaml_canonical.py``.
- ``@settings(max_examples=50, deadline=None, database=None)`` —
  ``deadline=None`` because YAML serialisation under coverage is slow;
  ``database=None`` keeps CI hermetic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast

import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from codegenie.rag.models import RecordProvenance, SolvedExample
from codegenie.rag.store import _canonical_yaml_dump
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

# Bounded sub-strategies — tight enough that each example is a valid
# ``SolvedExample`` AND distinct enough to exercise the YAML serialiser.

_HEX_CHARS = "0123456789abcdef"
_PACKAGE_MANAGERS: tuple[PackageManager, ...] = ("bun", "pnpm", "yarn-classic", "yarn-berry", "npm")


def _hex_str(n: int) -> st.SearchStrategy[str]:
    return st.text(min_size=n, max_size=n, alphabet=_HEX_CHARS)


_id_strategy = _hex_str(8).map(SolvedExampleId)
_blob_digest = _hex_str(64).map(BlobDigest)
_chain_head = _hex_str(64).map(ChainHead)
_cve_id = st.integers(min_value=1000, max_value=99999).map(lambda n: CveId(f"CVE-2026-{n}"))
_workflow_id = st.text(
    min_size=8,
    max_size=24,
    alphabet="ABCDEFGHJKMNPQRSTVWXYZ0123456789",
).map(WorkflowId)
_lang = st.sampled_from(("typescript", "javascript", "python", "java", "go")).map(Language)
_pm = st.sampled_from(_PACKAGE_MANAGERS)
_task_class = st.sampled_from(("vuln_remediation", "distroless_migration")).map(TaskClassId)
_model_id = st.sampled_from(("BAAI/bge-small-en-v1.5", "bge-small-en-v1.5")).map(ModelId)
_origin = st.sampled_from(("llm_solved", "operator_curated", "phase11_merge_webhook"))
_signing = st.sampled_from(("hmac_sha256_chain", "operator_attestation"))
_created_at = st.datetimes(
    min_value=datetime(2024, 1, 1),
    max_value=datetime(2028, 1, 1),
).map(lambda dt: dt.replace(tzinfo=UTC))

_embedding_vector = st.lists(
    st.floats(min_value=-1.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    min_size=384,
    max_size=384,
).map(lambda xs: EmbeddingVector(tuple(xs)))

_semver = st.tuples(
    st.integers(min_value=0, max_value=99),
    st.integers(min_value=0, max_value=99),
    st.integers(min_value=0, max_value=99),
).map(lambda t: SemverVersion(f"{t[0]}.{t[1]}.{t[2]}"))


def _build_plan_proposal(cve_id: str, semver: str) -> dict[str, object]:
    return {
        "kind": "dep_bump",
        "manifest_path": "package.json",
        "package": PackageId(f"{cve_id.lower()}@1.0.0"),
        "target_version": semver,
        "rationale": "cve-fix",
    }


@st.composite
def solved_examples(draw: st.DrawFn) -> SolvedExample:
    """Build a valid ``SolvedExample`` with all fields drawn explicitly."""
    cve = draw(_cve_id)
    semver = draw(_semver)
    return SolvedExample(
        id=draw(_id_strategy),
        task_class=draw(_task_class),
        language=draw(_lang),
        build_system=draw(_pm),
        cve_id=cve,
        advisory_digest=draw(_blob_digest),
        plan_kind="dep_bump",
        plan_proposal=_build_plan_proposal(cve, semver),  # type: ignore[arg-type]
        transform_digest=draw(_blob_digest),
        trust_outcome_digest=draw(_blob_digest),
        provenance=RecordProvenance(
            workflow_id=draw(_workflow_id),
            event_chain_head=draw(_chain_head),
            created_at=draw(_created_at),
            signing_method=cast(
                "Literal['hmac_sha256_chain', 'operator_attestation']",
                draw(_signing),
            ),
        ),
        origin=cast(
            "Literal['llm_solved', 'operator_curated', 'phase11_merge_webhook']",
            draw(_origin),
        ),
        embedding_model=draw(_model_id),
        embedding_vector=draw(_embedding_vector),
        created_at=draw(_created_at),
    )


@given(example=solved_examples())
@settings(max_examples=50, deadline=None, database=None)
def test_solved_example_yaml_roundtrip_is_exact(example: SolvedExample) -> None:
    """``SolvedExample.model_validate(yaml.safe_load(_canonical_yaml_dump(x)))
    == x`` — the load-bearing schema discipline."""
    assert len(example.embedding_vector) == 384  # non-degeneracy guard
    raw = _canonical_yaml_dump(example)
    restored = SolvedExample.model_validate(yaml.safe_load(raw))
    assert restored == example
