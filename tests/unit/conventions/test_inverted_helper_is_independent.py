"""AST source-scan — ``_apply_dockerfile_pattern_inverted`` body must not call
``_apply_dockerfile_pattern``.

S2-02 AC-5a / H7: the inverted helper is an independent body, not a wrapper
that flips the Pass/Fail of the non-inverted helper. The Rule of Three is
explicit in the story (~30 LOC each, four helpers, no shared ScannerRunner)
so a future contributor's "just invert the Pass" anti-pattern surfaces here.
"""

from __future__ import annotations

import ast
import pathlib

import codegenie.conventions.catalog as catalog_mod

_CATALOG_SRC = pathlib.Path(catalog_mod.__file__)


def test_inverted_helper_does_not_call_main_helper() -> None:
    tree = ast.parse(_CATALOG_SRC.read_text())
    target: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "_apply_dockerfile_pattern_inverted"
        ):
            target = node
            break
    assert target is not None, (
        "_apply_dockerfile_pattern_inverted is required at module level in catalog.py"
    )
    offenders: list[int] = []
    for sub in ast.walk(target):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name) and func.id == "_apply_dockerfile_pattern":
                offenders.append(sub.lineno)
    assert not offenders, (
        "_apply_dockerfile_pattern_inverted MUST be an independent body, "
        f"not a wrapper over _apply_dockerfile_pattern; sites: {offenders}"
    )
