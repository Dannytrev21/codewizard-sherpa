"""AC-Surface-4 fence — no module-level mutable non-``Final`` state under
``src/codegenie/transforms/engines/``.

A recipe engine is constructor-injected with every collaborator (ADR-0014);
a mutable module global (a bare ``list`` / ``dict`` / ``set``) is shared
hidden state across workflow runs. This AST walk rejects any module-level
binding to a mutable literal that is not annotated ``Final``. The live check
and the planted cases share :func:`_module_state_violations`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ENGINES_DIR = Path(__file__).resolve().parents[2] / "src" / "codegenie" / "transforms" / "engines"
_MUTABLE_CONSTRUCTORS = frozenset({"list", "dict", "set", "bytearray"})


def _is_final(annotation: ast.expr | None) -> bool:
    if isinstance(annotation, ast.Name):
        return annotation.id == "Final"
    if isinstance(annotation, ast.Attribute):
        return annotation.attr == "Final"
    if isinstance(annotation, ast.Subscript):
        return _is_final(annotation.value)
    return False


def _is_mutable_value(value: ast.expr) -> bool:
    if isinstance(value, ast.List | ast.Dict | ast.Set | ast.ListComp | ast.DictComp | ast.SetComp):
        return True
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in _MUTABLE_CONSTRUCTORS
    )


def _is_dunder(name: str | None) -> bool:
    return name is not None and name.startswith("__") and name.endswith("__")


def _module_state_violations(source: str, label: str) -> list[str]:
    """Return every module-level mutable non-``Final`` binding. ``__all__`` and
    other dunders are exempt (every module declares ``__all__`` as a list)."""
    out: list[str] = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            if _is_dunder(name) or node.value is None:
                continue
            if _is_mutable_value(node.value) and not _is_final(node.annotation):
                out.append(f"{label}: {name}")
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if not isinstance(target, ast.Name) or _is_dunder(target.id):
                    continue
                if _is_mutable_value(node.value):
                    out.append(f"{label}: {target.id}")
    return out


def test_no_module_level_mutable_state_under_engines() -> None:
    """AC-Surface-4 live check — engine modules carry no mutable globals."""
    violations: list[str] = []
    for path in sorted(_ENGINES_DIR.glob("*.py")):
        violations.extend(_module_state_violations(path.read_text("utf-8"), path.name))
    assert violations == [], f"module-level mutable state under transforms/engines/: {violations}"


@pytest.mark.parametrize(
    "snippet",
    [
        "MUTABLE = []\n",
        "REGISTRY = {}\n",
        "SEEN: set = set()\n",
        "CACHE = dict()\n",
    ],
)
def test_scanner_catches_planted_mutable_state(snippet: str) -> None:
    """AC-Surface-4 planted-positive — mutable non-``Final`` globals are caught."""
    assert _module_state_violations(snippet, "planted") != []


def test_scanner_allows_final_and_dunders() -> None:
    """AC-Surface-4 complement — ``Final`` constants and ``__all__`` are exempt."""
    ok = "from typing import Final\n__all__ = ['x']\nC: Final[dict[str, int]] = {}\nT = (1, 2)\n"
    assert _module_state_violations(ok, "ok") == []
