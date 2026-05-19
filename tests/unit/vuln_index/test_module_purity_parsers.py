"""S3-03 — AST module-purity fence for ``codegenie.vuln_index/``.

Covers AC-N2 + AC-F1 — no ``requests`` / ``httpx`` / ``urllib3`` / ``subprocess``
imports anywhere in ``src/codegenie/vuln_index/``. The stdlib
``urllib.request`` IS allowed but only inside ``Feed.fetch`` method bodies
(the AST fence forbids module-level imports; the cold-start fence in
``test_cold_start_parsers.py`` enforces the body-only invariant).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

VULN_INDEX_DIR: Final[Path] = (
    Path(__file__).resolve().parents[3] / "src" / "codegenie" / "vuln_index"
)
FORBIDDEN_TOPLEVEL: Final[frozenset[str]] = frozenset(
    {"requests", "httpx", "urllib3", "subprocess"}
)


def _collect_imports(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return names


def test_no_forbidden_http_libs_anywhere_in_vuln_index() -> None:
    """AC-N2 — sweep all ``.py`` files under ``vuln_index/``."""
    for py in VULN_INDEX_DIR.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for imp in _collect_imports(tree):
            top = imp.split(".")[0]
            assert top not in FORBIDDEN_TOPLEVEL, (
                f"AC-N2 violation: forbidden import {imp!r} in {py}"
            )


def _module_level_import_names(tree: ast.AST) -> list[str]:
    """Return names imported at the **module top level only** (not inside func/class)."""
    names: list[str] = []
    for node in tree.body:  # type: ignore[attr-defined]
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return names


def test_urllib_request_not_module_top_level_in_feeds() -> None:
    """AC-N3 — ``urllib.request`` is lazy inside ``Feed.fetch`` only."""
    feeds_dir = VULN_INDEX_DIR / "feeds"
    for py in feeds_dir.glob("*.py"):
        tree = ast.parse(py.read_text())
        names = _module_level_import_names(tree)
        for imp in names:
            assert not imp.startswith("urllib"), (
                f"AC-N3 violation: top-level ``urllib*`` import in {py}: {imp!r} — "
                "must be lazy-imported inside Feed.fetch"
            )


def test_no_subprocess_anywhere_in_vuln_index() -> None:
    """AC-N2 — extends S3-02's parser-discipline fence."""
    for py in VULN_INDEX_DIR.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for imp in _collect_imports(tree):
            assert "subprocess" not in imp, (
                f"AC-N2 violation: subprocess import in {py}: {imp!r}"
            )
