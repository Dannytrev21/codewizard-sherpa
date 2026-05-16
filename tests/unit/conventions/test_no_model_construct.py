"""AST source-scan — ``codegenie.conventions`` may not call ``.model_construct``.

S2-02 AC-14 / H10. ``model_construct`` bypasses Pydantic validation; allowing
it would defeat the typed-discriminator and ``extra='forbid'`` invariants
this story is built on. The pre-commit ``forbidden-patterns`` hook scans the
same paths (defense in depth — the AST scan is alias-resistant).
"""

from __future__ import annotations

import ast
import pathlib

import codegenie.conventions as conventions_pkg

_CONVENTIONS_ROOT = pathlib.Path(conventions_pkg.__file__).parent


def test_no_model_construct_call_or_assignment() -> None:
    offenders: list[tuple[str, int]] = []
    for py_path in _CONVENTIONS_ROOT.rglob("*.py"):
        tree = ast.parse(py_path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "model_construct":
                offenders.append((str(py_path), node.lineno))
    assert not offenders, (
        "codegenie.conventions MUST NOT call model_construct (bypasses validation); "
        f"sites: {offenders}"
    )
