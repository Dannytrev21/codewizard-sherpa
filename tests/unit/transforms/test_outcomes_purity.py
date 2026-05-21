"""Module-purity fences for ``codegenie.transforms.outcomes`` — S1-03 AC-10b / AC-10c."""

from __future__ import annotations

import ast
from pathlib import Path

import codegenie.transforms.outcomes as outcomes_mod

_ALLOWED_IMPORT_ROOTS = {
    "__future__",
    "typing",
    "pydantic",
    "codegenie.types.identifiers",
    "codegenie.types.errors",
    # S6-03 — ``Advance.state: SubgraphState`` needs the name in scope for
    # ``mypy --strict``. The import is ``TYPE_CHECKING``-guarded (zero runtime
    # effect — ``outcomes.py`` stays kernel-pure at runtime); the AST scan
    # below cannot see the guard, so the root is allowlisted explicitly.
    "codegenie.plugins.subgraph",
}


def test_imports_are_kernel_only() -> None:
    """AC-10b — AST source-scan of ``outcomes.py``; allowed import roots
    are exactly the kernel-tier dependencies."""
    source = Path(outcomes_mod.__file__).read_text()
    tree = ast.parse(source)
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in _ALLOWED_IMPORT_ROOTS:
                    bad.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module not in _ALLOWED_IMPORT_ROOTS:
                bad.append(module)
    assert not bad, f"outcomes.py imports outside the kernel-tier allowlist: {bad}"


def test_no_model_construct_in_outcomes() -> None:
    """AC-10c — ``model_construct`` bypasses validation; ban it at the
    source-text level. Mirrors the precedent in
    ``tests/unit/indices/test_freshness.py``."""
    source = Path(outcomes_mod.__file__).read_text()
    assert "model_construct" not in source
