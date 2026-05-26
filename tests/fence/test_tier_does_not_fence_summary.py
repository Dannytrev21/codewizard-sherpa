"""S6-02 fence — :file:`tier.py` MUST NOT call :meth:`FenceWrapper.fence`.

ADR-04-0011 + S2-04 AC-13: :class:`PromptBuilder` is the **sole** fence-
call site. :class:`FallbackTier` passes the raw ``prior_failure_summary``
``str`` into :meth:`PromptBuilder.build`'s already-shipped
``prior_attempt_summary: str | None`` kwarg; the prompt builder owns
the :meth:`FenceWrapper.fence` call internally.

This AST walk rejects any direct ``self.fence.fence(...)`` /
``fence.fence(...)`` / ``FenceWrapper.fence(...)`` call from within
:mod:`codegenie.fallback.tier`. The audit catches the regression where a
future implementer "helpfully" pre-fences the summary in ``tier.py``,
bypassing :class:`PromptBuilder`'s ownership of the call.
"""

from __future__ import annotations

import ast
from pathlib import Path

_TIER_PY = Path(__file__).parents[2] / "src" / "codegenie" / "fallback" / "tier.py"


def _walk_function_body(tree: ast.Module, name: str) -> list[ast.AST]:
    out: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef) and node.name == name:
            for sub in ast.walk(node):
                out.append(sub)
    return out


def test_tier_module_does_not_call_fence_method() -> None:
    """No ``*.fence(...)`` method call inside ``codegenie.fallback.tier``.

    A call shape like ``foo.fence(...)`` (any receiver, any args) is
    rejected — the only legitimate ``fence``-named call from ``tier.py``
    would be passing through :class:`PromptBuilder`'s internal call,
    which is unreachable from the AST walker because it lives in a
    separate module.
    """
    tree = ast.parse(_TIER_PY.read_text())
    offending: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "fence":
                offending.append((node.lineno, ast.unparse(node)))
    assert not offending, (
        "tier.py must not call *.fence(...) — PromptBuilder owns the fence call "
        f"per S2-04 AC-13. Offending calls: {offending}"
    )


def test_tier_module_does_not_import_fence_segment_or_source_kind() -> None:
    """``tier.py`` MUST NOT import :class:`FencedSegment` or the
    ``SourceKind`` ``Literal`` alias — both are :class:`PromptBuilder`
    internal types. An import would signal a future implementer was
    about to bypass PromptBuilder's ownership.
    """
    tree = ast.parse(_TIER_PY.read_text())
    banned = {"FencedSegment", "SourceKind"}
    leaked: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in banned:
                    leaked.append(f"line {node.lineno}: from ... import {alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[-1] in banned:
                    leaked.append(f"line {node.lineno}: import {alias.name}")
    assert not leaked, (
        "tier.py must not import FencedSegment or SourceKind — those are "
        f"PromptBuilder-private. Leaked imports: {leaked}"
    )
