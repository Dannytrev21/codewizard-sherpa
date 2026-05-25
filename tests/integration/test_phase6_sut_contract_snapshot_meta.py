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
        # S1-02 AC-15 extension — ledger-shaped fields.
        "ledger_state_schema": {
            "$defs": {
                "NeedsPlan": {"properties": {"kind": {"enum": ["needs_plan"]}}},
                "PlanReady": {"properties": {"kind": {"enum": ["plan_ready"]}}},
            },
        },
        "transition_event_schema": {
            "required": ["transition_id", "prior_state_id", "next_state_id"],
            "properties": {
                "transition_id": {"type": "string"},
                "prior_state_id": {"type": "string"},
                "next_state_id": {"type": "string"},
            },
        },
        "legal_transitions": [
            "needs_plan->plan_ready",
            "plan_ready->patch_applied",
            "patch_applied->completed",
        ],
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
        # S2-01 AC-15 — checkpoint substrate contract.
        "checkpoint_store_protocol": {
            "append": {
                "signature": "(self, event: TransitionEvent) -> ChainHead",
                "is_coroutine_function": False,
            },
            "read_all_for_workflow": {
                "signature": ("(self, workflow_id: WorkflowId) -> Iterator[TransitionEvent]"),
                "is_coroutine_function": False,
            },
            "tail_chain_head": {
                "signature": "(self, workflow_id: WorkflowId) -> ChainHead",
                "is_coroutine_function": False,
            },
            "lock": {
                "signature": ("(self, workflow_id: WorkflowId) -> AbstractContextManager[None]"),
                "is_coroutine_function": False,
            },
            "close": {
                "signature": "(self) -> None",
                "is_coroutine_function": False,
            },
        },
        "checkpoint_store_is_runtime_protocol": True,
        "semantic_boundary_kinds": sorted(
            [
                "plan_ready",
                "patch_applied",
                "gate_failed_retryable",
                "awaiting_human_review",
                "completed",
                "failed_unrecoverable",
            ]
        ),
        "max_event_bytes": 65_536,
        "checkpoint_sqlite_schema": (
            "CREATE TABLE IF NOT EXISTS checkpoint_chain (...);\n"
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_chain_next_head ON ...;\n"
        ),
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


# ---------------------------------------------------------------------------
# AC-15 S1-02 — ledger-shaped deltas exercise the classifier on the new fields.
# ---------------------------------------------------------------------------


def test_meta_additive_new_transition_edge() -> None:
    """Adding a new edge to ``legal_transitions`` is additive — the closed-
    set transition table widens by addition, never silently."""
    old = _baseline()
    new = copy.deepcopy(old)
    new["legal_transitions"].append("plan_ready->failed_unrecoverable")
    assert classify_snapshot_diff(old, new) == "additive"


def test_meta_breaking_removed_legal_transition_edge() -> None:
    """Removing an edge from ``legal_transitions`` is breaking — silently
    narrows the legal-edge inventory and would soft-lock the resumable
    ``awaiting_human_review → plan_ready`` path the harness depends on."""
    old = _baseline()
    new = copy.deepcopy(old)
    new["legal_transitions"].remove("needs_plan->plan_ready")
    assert classify_snapshot_diff(old, new) == "breaking"


def test_meta_breaking_removed_ledger_variant_via_defs() -> None:
    """Removing a variant from the ledger schema's ``$defs`` is breaking —
    a removed variant silently mis-routes round-tripping payloads."""
    old = _baseline()
    new = copy.deepcopy(old)
    new["ledger_state_schema"]["$defs"].pop("NeedsPlan")
    # The diff currently flows through the `$defs`-walk inside
    # ``_schema_diff_is_breaking``; if no $defs walker is present, this
    # exercises the broader `properties`-removal rule as well.
    # Either way the rejection must classify as breaking.
    assert classify_snapshot_diff(old, new) == "breaking"


def test_meta_breaking_transition_event_required_field_removed() -> None:
    old = _baseline()
    new = copy.deepcopy(old)
    new["transition_event_schema"]["properties"].pop("chain_head", None)
    new["transition_event_schema"]["properties"].pop("prior_state_id")
    new["transition_event_schema"]["required"].remove("prior_state_id")
    assert classify_snapshot_diff(old, new) == "breaking"


# ---------------------------------------------------------------------------
# Phase 6 S2-01 AC-15 — synthetic checkpoint-substrate deltas. Two cases:
# one additive (new optional adapter method with `Protocol` ``...`` body)
# and one breaking (removed semantic boundary kind).
# ---------------------------------------------------------------------------


def test_meta_additive_new_checkpoint_protocol_method() -> None:
    """Adding a method to the CheckpointStore Protocol is additive.

    Phase-9 may add an optional ``read_since_sequence()`` for forward
    seekers; the additive classification means the existing adapters
    keep working until the method is non-optional.
    """
    old = _baseline()
    new = copy.deepcopy(old)
    new["checkpoint_store_protocol"]["read_since_sequence"] = {
        "signature": "(self, workflow_id: WorkflowId, sequence: int) -> Iterator[TransitionEvent]",
        "is_coroutine_function": False,
    }
    assert classify_snapshot_diff(old, new) == "additive"


def test_meta_breaking_removed_semantic_boundary_kind() -> None:
    """Removing a kind from ``_SEMANTIC_BOUNDARY_KINDS`` is breaking.

    Mutation-resistance: dropping ``failed_unrecoverable`` would let a
    workflow crash with no terminal checkpoint; the classifier must
    return ``breaking`` so the executor cannot rubber-stamp it.
    """
    old = _baseline()
    new = copy.deepcopy(old)
    new["semantic_boundary_kinds"] = [
        k for k in old["semantic_boundary_kinds"] if k != "failed_unrecoverable"
    ]
    assert classify_snapshot_diff(old, new) == "breaking"


def test_meta_breaking_narrowed_max_event_bytes() -> None:
    """Narrowing the per-event byte cap downward is breaking."""
    old = _baseline()
    new = copy.deepcopy(old)
    new["max_event_bytes"] = 1024
    assert classify_snapshot_diff(old, new) == "breaking"


def test_meta_additive_widened_max_event_bytes() -> None:
    """Raising the per-event byte cap is additive."""
    old = _baseline()
    new = copy.deepcopy(old)
    new["max_event_bytes"] = 131_072
    assert classify_snapshot_diff(old, new) == "additive"


def test_meta_breaking_checkpoint_runtime_checkable_removed() -> None:
    old = _baseline()
    new = copy.deepcopy(old)
    new["checkpoint_store_is_runtime_protocol"] = False
    assert classify_snapshot_diff(old, new) == "breaking"


def test_meta_breaking_checkpoint_method_signature_changed() -> None:
    old = _baseline()
    new = copy.deepcopy(old)
    new["checkpoint_store_protocol"]["append"]["signature"] = "(self, event: dict) -> ChainHead"
    assert classify_snapshot_diff(old, new) == "breaking"
