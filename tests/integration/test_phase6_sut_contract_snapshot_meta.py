"""Phase 6 S1-01 AC-9 — meta-test for the additive-vs-breaking classifier.

Constructs synthetic snapshots and asserts ``classify_snapshot_diff``
classifies them correctly. Closes the S6-06 "false-positive additive is the
scariest failure mode" gap: a mutant that swaps ``==`` → ``!=`` in the
classifier would silently let breaking changes through; this meta-test dies
loud on that mutation.
"""

from __future__ import annotations

import copy
from typing import Any

from tests.integration.test_phase6_sut_contract_snapshot import classify_snapshot_diff


def _baseline() -> dict[str, Any]:
    return {
        "all": ["SutDigest", "VulnRemediationCase", "VulnRemediationResult", "VulnRemediationSut"],
        "is_runtime_protocol": True,
        "case_schema": {
            "required": ["case_id", "execution_mode"],
            "properties": {
                "case_id": {"type": "string"},
                "execution_mode": {"enum": ["dry_run", "apply", "replay"]},
            },
        },
        "result_schema": {
            "required": ["terminal_state"],
            "properties": {
                "terminal_state": {
                    "enum": ["completed", "awaiting_human_review", "failed_unrecoverable"]
                },
            },
        },
        "protocol": {
            "run_case": {
                "signature": "(self, request: VulnRemediationCase) -> VulnRemediationResult",
                "is_coroutine_function": True,
                "annotations": {
                    "request": "VulnRemediationCase",
                    "return": "VulnRemediationResult",
                },
            },
            "digest": {
                "signature": "(self) -> SutDigest",
                "is_coroutine_function": False,
                "annotations": {"return": "SutDigest"},
            },
        },
    }


def test_meta_noop_is_noop() -> None:
    base = _baseline()
    assert classify_snapshot_diff(base, copy.deepcopy(base)) == "noop"


def test_meta_additive_new_optional_field() -> None:
    """Adding a new optional property (not in `required`) is additive."""
    old = _baseline()
    new = copy.deepcopy(old)
    new["case_schema"]["properties"]["new_optional"] = {"type": "string"}
    assert classify_snapshot_diff(old, new) == "additive"


def test_meta_additive_new_sub_model_in_defs() -> None:
    """Adding a new ``$defs`` entry is additive."""
    old = _baseline()
    new = copy.deepcopy(old)
    new["case_schema"]["$defs"] = {"NewSubModel": {"type": "object", "properties": {}}}
    assert classify_snapshot_diff(old, new) == "additive"


def test_meta_breaking_removed_required_field() -> None:
    old = _baseline()
    new = copy.deepcopy(old)
    new["case_schema"]["properties"].pop("case_id")
    new["case_schema"]["required"].remove("case_id")
    assert classify_snapshot_diff(old, new) == "breaking"


def test_meta_breaking_new_required_unseen_field() -> None:
    """Adding a required field that wasn't in old properties is breaking."""
    old = _baseline()
    new = copy.deepcopy(old)
    new["case_schema"]["properties"]["new_field"] = {"type": "string"}
    new["case_schema"]["required"].append("new_field")
    assert classify_snapshot_diff(old, new) == "breaking"


def test_meta_breaking_literal_narrowed() -> None:
    """Removing a Literal member is breaking."""
    old = _baseline()
    new = copy.deepcopy(old)
    new["case_schema"]["properties"]["execution_mode"]["enum"] = ["dry_run", "apply"]
    assert classify_snapshot_diff(old, new) == "breaking"


def test_meta_breaking_terminal_state_narrowed() -> None:
    old = _baseline()
    new = copy.deepcopy(old)
    new["result_schema"]["properties"]["terminal_state"]["enum"] = [
        "completed",
        "awaiting_human_review",
    ]
    assert classify_snapshot_diff(old, new) == "breaking"


def test_meta_breaking_runtime_checkable_removed() -> None:
    old = _baseline()
    new = copy.deepcopy(old)
    new["is_runtime_protocol"] = False
    assert classify_snapshot_diff(old, new) == "breaking"


def test_meta_breaking_method_removed() -> None:
    old = _baseline()
    new = copy.deepcopy(old)
    new["protocol"].pop("digest")
    assert classify_snapshot_diff(old, new) == "breaking"


def test_meta_breaking_method_signature_changed() -> None:
    old = _baseline()
    new = copy.deepcopy(old)
    new["protocol"]["run_case"]["signature"] = "(self) -> VulnRemediationResult"
    assert classify_snapshot_diff(old, new) == "breaking"


def test_meta_breaking_name_removed_from_all() -> None:
    old = _baseline()
    new = copy.deepcopy(old)
    new["all"].remove("SutDigest")
    assert classify_snapshot_diff(old, new) == "breaking"


def test_meta_additive_name_added_to_all() -> None:
    """Adding a new name to ``__all__`` is additive (the AC-12 sentinel
    catches the *public surface* drift; the snapshot classifier just sees the
    addition itself as additive)."""
    old = _baseline()
    new = copy.deepcopy(old)
    new["all"].append("NewName")
    assert classify_snapshot_diff(old, new) == "additive"
