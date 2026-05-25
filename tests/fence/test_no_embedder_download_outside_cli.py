"""Fence — Phase-4 S4-01 AC-7.

Walk the AST of :mod:`codegenie.rag.embedder` and assert:

1. There is **no module-scope** ``TextEmbedding(...)`` call. A module-
   level call would download weights at import time — exactly the
   silent-bootstrap path ADR-0007 §Decision forbids.

2. Inside ``FastembedEmbedder.__init__``, the lock-verification call
   (``_verify_lock_or_raise(...)``) appears at an earlier statement
   index than the ``TextEmbedding(...)`` call. This is the structural
   guarantee that the runtime path never reaches fastembed unless the
   on-disk weights have already been proven present and matching the
   lock — so fastembed reads from cache and never downloads.

The fence asserts the *ordering*, not the *absence*, of the
``TextEmbedding`` call: ``embedder.py.__init__`` legitimately constructs
``TextEmbedding`` after verification. A fence that demanded absence
would be unsatisfiable (the original story draft's wording bug — caught
by validator finding F4).

The companion CLI body in :mod:`codegenie.rag.cli` IS authorized to
download weights and therefore IS exempt from this fence. This test
only walks the runtime path's AST.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Final

_REPO_ROOT: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]
_EMBEDDER_PATH: Final[pathlib.Path] = _REPO_ROOT / "src" / "codegenie" / "rag" / "embedder.py"


def _module_tree() -> ast.Module:
    return ast.parse(_EMBEDDER_PATH.read_text(encoding="utf-8"))


_SCOPE_BOUNDARY_NODES: tuple[type[ast.AST], ...] = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
)


def _iter_outside_function_scopes(node: ast.AST) -> ast.AST:
    """Yield ``node`` and its descendants, but never descend into the
    body of a function/method/lambda. Class scopes ARE descended into
    so that class-level statements (executed at import time) are
    inspected — only the per-method bodies are skipped.

    This is what lets the fence distinguish a *module-scope* call from
    one nested inside ``FastembedEmbedder.__init__``: the latter only
    fires when ``__init__`` actually runs, the former runs at import.
    """
    yield node
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _SCOPE_BOUNDARY_NODES):
            continue
        yield from _iter_outside_function_scopes(child)


def _statement_calls_text_embedding(node: ast.stmt, *, deep: bool = True) -> bool:
    """True iff this statement contains a Call to a name ending in
    ``TextEmbedding`` (covers both ``TextEmbedding(...)`` and
    ``module.TextEmbedding(...)`` shapes — the latter is how
    ``codegenie.rag.embedder`` reaches the symbol via the dynamic
    ``importlib.import_module`` indirection).

    ``deep`` controls whether descent crosses function/method/lambda
    scopes. The module-scope fence uses ``deep=False`` so a call nested
    inside ``__init__`` is not falsely flagged as a module-scope call.
    """
    walker = ast.walk(node) if deep else _iter_outside_function_scopes(node)
    for sub in walker:
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Name) and func.id == "TextEmbedding":
            return True
        if isinstance(func, ast.Attribute) and func.attr == "TextEmbedding":
            return True
    return False


def _statement_calls_verify_lock_or_raise(node: ast.stmt) -> bool:
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        func = sub.func
        if isinstance(func, ast.Name) and func.id == "_verify_lock_or_raise":
            return True
    return False


def test_no_module_scope_text_embedding_call() -> None:
    """S4-01 AC-7 (structural #1) — a module-scope ``TextEmbedding(...)``
    call would download weights at import time."""
    tree = _module_tree()
    offenders = [
        ast.dump(stmt, include_attributes=False)[:120]
        for stmt in tree.body
        if _statement_calls_text_embedding(stmt, deep=False)
    ]
    assert not offenders, (
        "module-scope `TextEmbedding(...)` call detected in "
        f"{_EMBEDDER_PATH.relative_to(_REPO_ROOT)} — would download "
        "weights at import time, violating ADR-0007 §Decision. "
        f"Offending statements: {offenders}"
    )


def test_text_embedding_call_in_init_is_preceded_by_verify_lock_or_raise() -> None:
    """S4-01 AC-7 (structural #2) — inside
    ``FastembedEmbedder.__init__``, the lock-verification call must
    precede the ``TextEmbedding(...)`` call. Reading the fence the
    other way: an ``__init__`` whose first statement is
    ``TextEmbedding(...)`` would attempt to download (or read stale
    cache) before verifying anything — the refuse-start posture
    collapses."""
    tree = _module_tree()
    class_node: ast.ClassDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "FastembedEmbedder":
            class_node = node
            break
    assert class_node is not None, (
        "FastembedEmbedder class not found in embedder.py — fence assumes "
        "the class is named this; refactor the fence if the class is renamed."
    )

    init_node: ast.FunctionDef | None = None
    for child in class_node.body:
        if isinstance(child, ast.FunctionDef) and child.name == "__init__":
            init_node = child
            break
    assert init_node is not None, "FastembedEmbedder.__init__ not found."

    verify_index: int | None = None
    embed_index: int | None = None
    for idx, stmt in enumerate(init_node.body):
        if verify_index is None and _statement_calls_verify_lock_or_raise(stmt):
            verify_index = idx
        if embed_index is None and _statement_calls_text_embedding(stmt):
            embed_index = idx

    assert verify_index is not None, (
        "FastembedEmbedder.__init__ does not call _verify_lock_or_raise — "
        "the refuse-start posture is lost. AC-7 structural fence FAIL."
    )
    assert embed_index is not None, (
        "FastembedEmbedder.__init__ does not construct TextEmbedding — "
        "this fence cannot enforce ordering when the call is absent. "
        "Likely the refactor moved the construction elsewhere; update "
        "the fence to walk the new home."
    )
    assert verify_index < embed_index, (
        f"AC-7 ordering violation: _verify_lock_or_raise at stmt index "
        f"{verify_index} but TextEmbedding(...) at index {embed_index}. "
        "The lock-verification kernel MUST run before any fastembed "
        "construction (ADR-0007 §Decision)."
    )
