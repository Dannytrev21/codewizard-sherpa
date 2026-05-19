"""S3-05 AC-25 — AST purity fence for :mod:`codegenie.plugins.cache_gc`.

Asserts that the bodies of ``_parse_ttl_seconds``, ``_is_evictable``, and
``_should_run_amortized`` reference no ``os``, ``Path``, ``time``, or
``structlog`` attributes — fencing the functional core (DP2). Mirrors
the S3-04 ``_compose_entry`` purity fence pattern.
"""

from __future__ import annotations

import ast
import pathlib

_TARGET_FUNCS = {"_parse_ttl_seconds", "_is_evictable", "_should_run_amortized"}
_FORBIDDEN_ROOTS = {"os", "Path", "time", "structlog"}


def test_pure_helpers_have_no_io_or_clock_references() -> None:
    src = pathlib.Path("src/codegenie/plugins/cache_gc.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in _TARGET_FUNCS:
            seen.add(node.name)
            for inner in ast.walk(node):
                if isinstance(inner, ast.Attribute):
                    root: ast.expr = inner.value
                    while isinstance(root, ast.Attribute):
                        root = root.value
                    if isinstance(root, ast.Name) and root.id in _FORBIDDEN_ROOTS:
                        raise AssertionError(
                            f"{node.name} references forbidden root '{root.id}'"
                            f" (attribute: {ast.unparse(inner)})"
                        )
                if isinstance(inner, (ast.Import, ast.ImportFrom)):
                    raise AssertionError(
                        f"{node.name} contains a function-scope import"
                        " — pure helpers must declare imports at module top"
                    )
    missing = _TARGET_FUNCS - seen
    assert not missing, f"pure helpers not found in cache_gc.py: {missing}"
