"""Phase 3 S1-02 AC-21 — module-purity AST scan for ``scope.py``.

The plugin-scope kernel imports only the closed allowlist. No fs, no logger,
no sibling-package coupling. Mirrors the Phase-2 S1-04 ``codegenie.result``
and Phase-2 S1-01 ``codegenie.indices.freshness`` precedents.
"""

from __future__ import annotations

import ast
import inspect

import codegenie.plugins.scope as scope_mod

_ALLOWED_TOP_LEVEL: frozenset[str] = frozenset(
    {
        "__future__",
        "dataclasses",
        "re",
        "typing",
        "codegenie.result",
        "codegenie.types.errors",
    }
)


def _imported_module_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "<relative-import>")
    return names


def test_scope_module_purity() -> None:
    src = inspect.getsource(scope_mod)
    imported = _imported_module_names(src)
    extra = imported - _ALLOWED_TOP_LEVEL
    assert not extra, f"codegenie.plugins.scope imports outside allowlist: {sorted(extra)}"
