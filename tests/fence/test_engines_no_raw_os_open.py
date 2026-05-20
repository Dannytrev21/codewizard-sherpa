"""AC-3a fence — modules under ``src/codegenie/transforms/engines/`` open
files only through :meth:`SandboxedPath.open`.

A raw ``os.open`` / ``builtins.open`` / ``io.open`` / ``pathlib.Path.open``
bypasses the ``O_NOFOLLOW`` TOCTOU defence (ADR-0011). This AST walk rejects
every such call. The live check and the planted-positive cases both call
:func:`_raw_open_violations` — a regression in the scanner kills both
(mutation resistance).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ENGINES_DIR = Path(__file__).resolve().parents[2] / "src" / "codegenie" / "transforms" / "engines"
_FORBIDDEN_ROOTS = frozenset({"os", "io", "pathlib"})


def _attr_chain(node: ast.expr) -> tuple[str | None, frozenset[str]]:
    """Return ``(root Name id, every attribute name)`` for an attribute /
    call chain — e.g. ``pathlib.Path('x').open`` → ``("pathlib", {"Path",
    "open"})``."""
    attrs: set[str] = set()
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        attrs.add(current.attr)
        current = current.value
    if isinstance(current, ast.Call):
        root, more = _attr_chain(current.func)
        return root, frozenset(attrs | more)
    if isinstance(current, ast.Name):
        return current.id, frozenset(attrs)
    return None, frozenset(attrs)


def _raw_open_violations(source: str, label: str) -> list[str]:
    """Return every raw-open call site in ``source``. ``<var>.open(...)`` —
    the :class:`SandboxedPath` shape — is allowed."""
    out: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open":
            out.append(f"{label}:{node.lineno} bare open()")
        elif isinstance(func, ast.Attribute) and func.attr == "open":
            root, attrs = _attr_chain(func)
            if root in _FORBIDDEN_ROOTS or "Path" in attrs:
                out.append(f"{label}:{node.lineno} {root or '?'}.open()")
    return out


def test_no_raw_open_under_transforms_engines() -> None:
    """AC-3a live check — zero raw opens across every engine module."""
    violations: list[str] = []
    for path in sorted(_ENGINES_DIR.glob("*.py")):
        violations.extend(_raw_open_violations(path.read_text("utf-8"), path.name))
    assert violations == [], f"raw open() under transforms/engines/: {violations}"


@pytest.mark.parametrize(
    "snippet",
    [
        "import os\nfd = os.open('x', 0)\n",
        "data = open('x').read()\n",
        "import io\nio.open('x')\n",
        "import pathlib\npathlib.Path('x').open('rb')\n",
    ],
)
def test_scanner_catches_each_planted_raw_open(snippet: str) -> None:
    """AC-3a planted-positive — the same scanner catches every raw-open form."""
    assert _raw_open_violations(snippet, "planted") != []


def test_scanner_allows_sandboxed_path_open() -> None:
    """AC-3a metamorphic complement — ``<var>.open(...)`` is not a violation."""
    assert _raw_open_violations("path.open('rb')\nresolved.open('wb')\n", "ok") == []
