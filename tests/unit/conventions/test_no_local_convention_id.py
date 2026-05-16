"""AST source-scan — ``ConventionId`` lives only in ``codegenie.types.identifiers``.

S2-02 AC-1a / B2: prevent primitive-obsession drift where a sibling module
re-defines ``ConventionId = NewType(...)``. The canonical home is the
identifier roster — every consumer imports from there.
"""

from __future__ import annotations

import ast
import pathlib

import codegenie.conventions as conventions_pkg

_CONVENTIONS_ROOT = pathlib.Path(conventions_pkg.__file__).parent


def test_no_local_convention_id_newtype() -> None:
    offenders: list[tuple[str, int]] = []
    for py_path in _CONVENTIONS_ROOT.rglob("*.py"):
        tree = ast.parse(py_path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_newtype = (
                (isinstance(func, ast.Name) and func.id == "NewType")
                or (isinstance(func, ast.Attribute) and func.attr == "NewType")
            )
            if not is_newtype:
                continue
            if (
                node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "ConventionId"
            ):
                offenders.append((str(py_path), node.lineno))
    assert not offenders, (
        "ConventionId MUST live in codegenie.types.identifiers; "
        f"local NewType call sites: {offenders}"
    )


def test_convention_id_resolves_from_identifiers_module() -> None:
    from codegenie.types.identifiers import ConventionId

    assert ConventionId.__module__ == "codegenie.types.identifiers"
