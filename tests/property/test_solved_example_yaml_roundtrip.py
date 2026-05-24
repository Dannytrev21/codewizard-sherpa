"""Phase-4 S1-04 — concrete JSON round-trip for ``SolvedExample`` (AC-12).

The full ``from_yaml(to_yaml(x)) == x`` Hypothesis property lands in S4-04
(which owns the canonical YAML serialiser + the ``PlanProposal`` generator).
This story proves the Pydantic shape is serialisable: ``model_validate_json
(model_dump_json(x)) == x`` for a representative valid record.
"""

from __future__ import annotations

from datetime import UTC, datetime

from codegenie.rag.models import SolvedExample

_HEX64 = "a" * 64
_SOLVED = {
    "id": _HEX64,
    "task_class": "vuln_remediation",
    "language": "typescript",
    "build_system": "npm",
    "cve_id": "CVE-2026-1234",
    "advisory_digest": _HEX64,
    "plan_kind": "dep_bump",
    "plan_proposal": {
        "kind": "dep_bump",
        "manifest_path": "package.json",
        "package": "lodash@4.17.21",
        "target_version": "4.17.21",
        "rationale": "x",
    },
    "transform_digest": _HEX64,
    "trust_outcome_digest": _HEX64,
    "provenance": {
        "workflow_id": "01HXX00000000000000000000Z",
        "event_chain_head": _HEX64,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "signing_method": "hmac_sha256_chain",
    },
    "origin": "llm_solved",
    "embedding_model": "bge-small-en-v1.5",
    "created_at": datetime(2026, 1, 1, tzinfo=UTC),
}


def test_solved_example_json_roundtrip() -> None:
    original = SolvedExample.model_validate(_SOLVED)
    restored = SolvedExample.model_validate_json(original.model_dump_json())
    assert restored == original
