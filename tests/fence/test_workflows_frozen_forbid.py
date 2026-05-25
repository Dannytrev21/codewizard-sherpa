"""Phase 6 S1-02 AC-12 — AST fence: every BaseModel in workflows/ uses _FROZEN_FORBID.

Walks every ``.py`` file under ``src/codegenie/workflows/`` and asserts
that every ``class X(BaseModel)`` declaration carries
``model_config = _FROZEN_FORBID`` (literal attribute assignment; no
``ConfigDict(frozen=True, extra="forbid")`` re-declaration — the
canonical constant must be imported, never inlined).

Catches the case where an executor under deadline pressure ships a new
variant without the ``_FROZEN_FORBID`` line and the variant becomes
silently mutable — a Rule-12 fail-loud failure mode.
"""

from __future__ import annotations

import ast
from pathlib import Path

import codegenie.workflows as workflows_pkg


def _basemodel_subclasses(tree: ast.AST) -> list[ast.ClassDef]:
    out: list[ast.ClassDef] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            # base might be ``BaseModel`` (Name) or ``pydantic.BaseModel`` (Attribute).
            if isinstance(base, ast.Name) and base.id == "BaseModel":
                out.append(node)
                break
            if isinstance(base, ast.Attribute) and base.attr == "BaseModel":
                out.append(node)
                break
    return out


def _has_frozen_forbid_assignment(cls: ast.ClassDef) -> bool:
    for stmt in cls.body:
        # ``model_config = _FROZEN_FORBID`` (literal Name on the RHS).
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "model_config"
            and isinstance(stmt.value, ast.Name)
            and stmt.value.id == "_FROZEN_FORBID"
        ):
            return True
    return False


def test_every_basemodel_in_workflows_uses_frozen_forbid_constant() -> None:
    pkg_root = Path(workflows_pkg.__file__).resolve().parent
    failures: list[str] = []
    for py in sorted(pkg_root.glob("*.py")):
        if py.name == "_frozen.py":
            # The canonical declaration site itself doesn't define BaseModel
            # subclasses (it only declares the constant).
            continue
        tree = ast.parse(py.read_text())
        for cls in _basemodel_subclasses(tree):
            if not _has_frozen_forbid_assignment(cls):
                failures.append(
                    f"{py.name}::{cls.name} (line {cls.lineno}) — "
                    "must set 'model_config = _FROZEN_FORBID'"
                )

    assert not failures, (
        "AC-12: workflows BaseModel subclasses must use the canonical "
        "_FROZEN_FORBID constant (imported from codegenie.workflows._frozen). "
        "Inline ConfigDict(...) declarations silently drift; the constant "
        "is the single-source-of-truth. Violations:\n  - " + "\n  - ".join(failures)
    )
