"""S4-04 AC-purity-fence — ``codegenie.plugins.sandbox_path`` import allowlist.

AST-walks the module and asserts every imported module name is a subset of
the closed allowlist. Specifically forbids ``codegenie.transforms.*`` imports
so the cycle ADR-0001 / ADR-0013 defend in the opposite direction stays
closed on this side too.
"""

from __future__ import annotations

import ast
import inspect

import codegenie.plugins.sandbox_path as mod

_ALLOWED: frozenset[str] = frozenset(
    {
        "__future__",
        "errno",
        "fcntl",
        "os",
        "pathlib",
        "typing",
        "pydantic",
        "codegenie.result",
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


def test_sandbox_path_module_imports_only_allowed() -> None:
    src = inspect.getsource(mod)
    extra = _imported_module_names(src) - _ALLOWED
    assert not extra, (
        f"codegenie.plugins.sandbox_path imports outside the allowlist: {sorted(extra)}"
    )


def test_sandbox_path_module_does_not_import_transforms() -> None:
    src = inspect.getsource(mod)
    imported = _imported_module_names(src)
    leaks = {name for name in imported if name.startswith("codegenie.transforms")}
    assert not leaks, (
        "codegenie.plugins.sandbox_path must not import from codegenie.transforms.*; "
        f"found: {sorted(leaks)}"
    )
