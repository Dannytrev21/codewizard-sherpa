"""Phase-3 S2-04 AC-13 — module-purity AST scan for ``resolver.py``.

The resolver is the functional core; it must not reach for I/O modules
(``os``, ``pathlib``, ``logging``) or sibling-package coupling. Mirrors
the Phase-3 S1-02 ``scope.py`` AST-scan precedent
(``test_scope_purity.py``) generalised from ADR-0001 chokepoint
hygiene.

Mutation kill-list M16: importing ``pathlib`` (impurity creep) trips
this scan.
"""

from __future__ import annotations

import ast
import inspect

import codegenie.plugins.resolver as resolver_mod

_ALLOWED_TOP_LEVEL: frozenset[str] = frozenset(
    {
        "__future__",
        "dataclasses",
        "typing",
        "pydantic",
        "codegenie.plugins.scope",
        "codegenie.plugins.manifest",
        "codegenie.plugins.protocols",
        "codegenie.plugins.registry",
        "codegenie.plugins.errors",
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
            names.add(node.module or "<relative-import>")
    return names


def test_resolver_module_purity() -> None:
    src = inspect.getsource(resolver_mod)
    imported = _imported_module_names(src)
    extra = imported - _ALLOWED_TOP_LEVEL
    assert not extra, f"codegenie.plugins.resolver imports outside allowlist: {sorted(extra)}"


def test_resolver_max_extends_depth_literal_single_source() -> None:
    """Phase-3 S2-04 AC-17 — the integer literal ``4`` appears at most
    once in ``resolver.py`` (on the ``_MAX_EXTENDS_DEPTH = 4`` line).

    Mutation M18: a future refactor that raises the cap to ``10`` at
    the named constant but leaves an inline ``max_depth=4`` somewhere
    fails this scan. The named constant is the single source of truth
    so an ADR amendment is visible at exactly one site."""
    src = inspect.getsource(resolver_mod)
    tree = ast.parse(src)
    occurrences = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, int) and n.value == 4
    ]
    assert len(occurrences) <= 1, (
        f"integer literal `4` appears {len(occurrences)} times in resolver.py — "
        f"the ``_MAX_EXTENDS_DEPTH`` constant must be the single source of truth "
        f"per AC-17. Found at lines: {[n.lineno for n in occurrences]}"
    )
