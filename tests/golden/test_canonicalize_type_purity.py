"""S7-03 AC-39 — no ``Any`` type slips into ``_canonicalize`` signatures.

Walks ``scripts/regen_golden.py`` with ``ast`` and asserts no function
argument or return is annotated with ``Any``. ``mypy --strict`` then does
real work over the recursive ``JsonValue`` union.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "regen_golden.py"


def _annotation_uses_any(node: ast.expr | None) -> bool:
    if node is None:
        return False
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == "Any":
            return True
    return False


def test_no_any_annotation_in_regen_golden_script() -> None:
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for arg in node.args.args + node.args.kwonlyargs:
                if _annotation_uses_any(arg.annotation):
                    offenders.append(f"{node.name}({arg.arg})")
            if _annotation_uses_any(node.returns):
                offenders.append(f"{node.name} -> Any")
    assert not offenders, (
        "scripts/regen_golden.py contains `Any` type annotations on "
        f"function args or returns: {offenders}. Use the recursive "
        "`JsonValue` TypeAlias so mypy --strict does real work."
    )
