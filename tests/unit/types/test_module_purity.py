"""Phase 3 S1-01 AC-16 — module purity guard for ``errors.py`` and ``parsers.py``.

AST-walk the new kernel-tier modules and assert the import set is a strict
subset of the allowlist. Mirrors the Phase-2 S1-05 / S1-04 module-purity
precedent that protects ``codegenie.result`` and ``codegenie.types.*`` from
accidentally pulling in fs/logger/sibling-package dependencies.
"""

from __future__ import annotations

import ast
import inspect

import codegenie.types.errors as errors_mod
import codegenie.types.parsers as parsers_mod

_ERRORS_ALLOWED: frozenset[str] = frozenset({"__future__", "typing", "pydantic"})

_PARSERS_ALLOWED: frozenset[str] = frozenset(
    {
        "__future__",
        "typing",
        "collections.abc",
        "re",
        "unicodedata",
        "codegenie.result",
        "codegenie.types.errors",
        "codegenie.types.identifiers",
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
            # node.module may be None for relative-from imports — we forbid those
            # in kernel-tier modules; surface as a non-allowed sentinel.
            names.add(node.module or "<relative-import>")
    return names


def test_errors_module_imports_only_allowed() -> None:
    src = inspect.getsource(errors_mod)
    imported = _imported_module_names(src)
    extra = imported - _ERRORS_ALLOWED
    assert not extra, f"codegenie.types.errors imports outside the allowlist: {sorted(extra)}"


def test_parsers_module_imports_only_allowed() -> None:
    src = inspect.getsource(parsers_mod)
    imported = _imported_module_names(src)
    extra = imported - _PARSERS_ALLOWED
    assert not extra, f"codegenie.types.parsers imports outside the allowlist: {sorted(extra)}"
