"""S6-08 fence — ``AttemptAnchorRecorded`` is the terminal event of the
per-attempt tape in :meth:`FallbackTier.run`.

AST walk over ``src/codegenie/fallback/tier.py``: every control-flow branch
that emits ``AttemptAnchorRecorded`` must NOT be followed by another
``event_log.emit_internal(...)`` call inside the same branch. The JSONL
projection's "one line per attempt" promise depends on this: if a post-
anchor event fired in the same attempt frame, replay would have to join
two records.
"""

from __future__ import annotations

import ast
from pathlib import Path

_TIER_PATH = Path(__file__).resolve().parents[2] / "src" / "codegenie" / "fallback" / "tier.py"


def _is_emit_internal_call(node: ast.AST) -> bool:
    """``self.event_log.emit_internal(...)``"""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "emit_internal"
    )


def _emit_event_name(node: ast.Call) -> str | None:
    """Return the BaseModel class name passed to ``emit_internal``, or
    ``None`` if the call shape doesn't match the established pattern."""
    if not node.args:
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name):
        return arg.func.id
    return None


def _flatten_calls_in_order(body: list[ast.stmt]) -> list[ast.Call]:
    """Yield every ``ast.Call`` reachable from ``body`` in source order.

    Walks into nested control flow (if/match/for/with) so a branch that
    emits the anchor then emits another event still trips the fence.
    """
    out: list[ast.Call] = []
    for stmt in body:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Call):
                out.append(sub)
    return out


def test_no_emit_follows_attempt_anchor_in_run_body() -> None:
    """For every ``FallbackTier.run`` control-flow path, an
    ``AttemptAnchorRecorded`` emission must not be followed by another
    ``event_log.emit_internal(...)`` call. We walk the AST in source order
    and verify the property over the linearised call sequence."""
    tree = ast.parse(_TIER_PATH.read_text())
    fallback_tier = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "FallbackTier"
    )
    run_method: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    for node in fallback_tier.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run":
            run_method = node
            break
    assert run_method is not None, "FallbackTier.run not found"

    calls = _flatten_calls_in_order(list(run_method.body))
    anchor_seen = False
    for call in calls:
        if not _is_emit_internal_call(call):
            continue
        event_name = _emit_event_name(call)
        if anchor_seen and event_name is not None and event_name != "AttemptAnchorRecorded":
            raise AssertionError(
                f"emit_internal({event_name}) appears after "
                f"AttemptAnchorRecorded in FallbackTier.run — the anchor "
                f"must be the terminal event of the per-attempt tape."
            )
        if event_name == "AttemptAnchorRecorded":
            anchor_seen = True
