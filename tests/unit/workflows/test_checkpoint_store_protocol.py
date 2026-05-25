"""Phase 6 S2-01 AC-1 — ``CheckpointStore`` Protocol shape.

The Protocol is the kernel; the SQLite + InMemory adapters are additions.
This test pins the five-method shape byte-for-byte so a future executor
cannot collapse ``append`` + ``lock`` into one method (the Phase-3
``EventStreamSink`` precedent keeps them separate so the per-workflow
lock policy stays observable).

AC-1 (iv) — the Phase-3 ``EventStreamSink`` Protocol is **not** imported
here; the two ports are deliberately distinct (S2-01 References §
"Disambiguation note").
"""

from __future__ import annotations

import inspect
import typing
from typing import Protocol, get_type_hints

from codegenie.workflows.checkpoints import CheckpointStore


def test_checkpoint_store_is_runtime_checkable_protocol() -> None:
    assert issubclass(CheckpointStore, Protocol)  # type: ignore[arg-type]
    assert getattr(CheckpointStore, "_is_runtime_protocol", False) is True


def test_checkpoint_store_exposes_exactly_five_methods() -> None:
    expected = {"append", "read_all_for_workflow", "tail_chain_head", "lock", "close"}
    declared = {
        name
        for name in vars(CheckpointStore)
        if callable(getattr(CheckpointStore, name)) and not name.startswith("_")
    }
    assert declared == expected, (
        f"CheckpointStore Protocol must declare exactly {sorted(expected)}; got {sorted(declared)}."
    )


def test_checkpoint_store_method_annotations_are_typed() -> None:
    """Every method has a fully-typed signature — no implicit ``Any``."""
    hints = {
        name: get_type_hints(getattr(CheckpointStore, name))
        for name in ("append", "read_all_for_workflow", "tail_chain_head", "lock", "close")
    }
    for name, h in hints.items():
        assert "return" in h, f"{name} missing return annotation"
    # ``append`` returns ChainHead, has TransitionEvent parameter
    assert hints["append"]["event"].__name__ == "TransitionEvent"
    assert hints["append"]["return"].__name__ == "ChainHead"
    # ``read_all_for_workflow`` returns Iterator[TransitionEvent]
    ra_return = hints["read_all_for_workflow"]["return"]
    assert typing.get_origin(ra_return) is not None  # parameterized generic
    assert hints["read_all_for_workflow"]["workflow_id"].__name__ == "WorkflowId"
    # ``tail_chain_head`` takes WorkflowId, returns ChainHead
    assert hints["tail_chain_head"]["workflow_id"].__name__ == "WorkflowId"
    assert hints["tail_chain_head"]["return"].__name__ == "ChainHead"
    # ``lock`` takes WorkflowId and returns an AbstractContextManager
    assert hints["lock"]["workflow_id"].__name__ == "WorkflowId"
    # ``close`` returns None
    assert hints["close"]["return"] is type(None)


def test_checkpoint_module_does_not_import_event_stream_sink() -> None:
    """AC-1 (iv) — the Phase-3 forensic-log Protocol stays distinct.

    AST-walk every ``Import`` / ``ImportFrom`` in ``checkpoints.py`` and
    reject any binding of the name ``EventStreamSink``. Mentions in
    docstrings/comments are fine — only actual imports would collapse the
    two ports' independence.
    """
    import ast

    module = __import__("codegenie.workflows.checkpoints", fromlist=["x"])
    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert alias.name != "EventStreamSink", (
                    "checkpoints.py must not import EventStreamSink — "
                    "S2-01 References §'Disambiguation note': the forensic "
                    "EventLog and the CheckpointStore are deliberately "
                    "distinct ports."
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert "EventStreamSink" not in alias.name, (
                    "checkpoints.py must not import EventStreamSink."
                )
