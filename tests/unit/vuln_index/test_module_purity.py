"""S3-02 — AST-walk fences for ``codegenie.vuln_index/`` discipline.

Covers AC-L1 (no raw ``blake3``, ``PackageName``/``Ecosystem`` live in
``identifiers.py`` only) and AC-L3 (no ``subprocess`` import — Alembic
invocation is in-process).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

VULN_INDEX_DIR: Final[Path] = (
    Path(__file__).resolve().parents[3] / "src" / "codegenie" / "vuln_index"
)
INDEX_FILE: Final[Path] = VULN_INDEX_DIR / "index.py"


def _collect_imports(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return names


def test_no_raw_blake3_in_index() -> None:
    """AC-L1 — ADR-0001 chokepoint discipline."""
    tree = ast.parse(INDEX_FILE.read_text())
    for name in _collect_imports(tree):
        assert not name.startswith("blake3"), (
            f"ADR-0001 violation: raw blake3 import in {INDEX_FILE}: {name!r}"
        )


def test_no_raw_blake3_anywhere_in_vuln_index() -> None:
    """AC-L1 — sweep ALL files in vuln_index/."""
    for py in VULN_INDEX_DIR.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for name in _collect_imports(tree):
            assert not name.startswith("blake3"), (
                f"ADR-0001 violation: raw blake3 import in {py}: {name!r}"
            )


def test_no_subprocess_in_vuln_index() -> None:
    """AC-L3 — Alembic is in-process; no subprocess shell-out."""
    for py in VULN_INDEX_DIR.rglob("*.py"):
        # Skip the migrations env.py if alembic ever pulls it via cwd — we
        # don't ship a subprocess invocation, but make the rule explicit.
        tree = ast.parse(py.read_text())
        for name in _collect_imports(tree):
            assert "subprocess" not in name, f"AC-L3 violation: subprocess import in {py}: {name!r}"


def test_package_name_and_ecosystem_live_in_identifiers_module() -> None:
    """AC-L1 — PackageName + Ecosystem are kernel-tier in identifiers.py."""
    from codegenie.types import identifiers as ids

    assert "PackageName" in ids.__all__
    assert "Ecosystem" in ids.__all__
    # And they MUST NOT be re-defined inside vuln_index/.
    for py in VULN_INDEX_DIR.rglob("*.py"):
        src = py.read_text()
        assert 'NewType("PackageName"' not in src, (
            f"AC-L1 violation — PackageName redefined in {py}"
        )
        # Ecosystem literal definition shape — guarded against drift.
        assert "Ecosystem = Literal[" not in src, f"AC-L1 violation — Ecosystem redefined in {py}"
