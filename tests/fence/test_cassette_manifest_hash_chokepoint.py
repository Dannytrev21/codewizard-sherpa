"""Phase-4 S3-05 AC-20 — `manifest.py` routes BLAKE3 through the chokepoint.

ADR-0001 (Phase 0) names :mod:`codegenie.hashing` as the single import
point for BLAKE3. The cassette manifest stores unprefixed 64-hex digests
in ``cassettes.lock``; the contract is that :func:`compute_cassette_digest`
calls :func:`codegenie.hashing.content_hash` and strips the ``blake3:``
prefix — never imports ``blake3`` itself.

Two checks: a source-text grep (cheap, catches the obvious failure) and
an AST walk (catches a clever import that the grep would miss, e.g.
``importlib.import_module("blake3")``).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_MANIFEST = Path("src/codegenie/fallback/cassette/manifest.py")


def test_manifest_source_does_not_import_blake3_textually() -> None:
    """Text-level guard: no literal `import blake3` or `from blake3 …`."""
    src = _MANIFEST.read_text(encoding="utf-8")
    assert "import blake3" not in src
    assert "from blake3" not in src


def test_manifest_source_calls_content_hash() -> None:
    """The chokepoint helper must appear in the source."""
    src = _MANIFEST.read_text(encoding="utf-8")
    assert "content_hash(" in src


def test_manifest_ast_has_no_blake3_import() -> None:
    """AST guard: defeats `importlib.import_module("blake3")` / aliased imports."""
    tree = ast.parse(_MANIFEST.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "blake3", (
                    f"manifest.py imports blake3 directly: {ast.dump(node)}"
                )
        elif isinstance(node, ast.ImportFrom):
            assert node.module != "blake3", (
                f"manifest.py imports from blake3 directly: {ast.dump(node)}"
            )
        elif isinstance(node, ast.Call):
            # Detect `importlib.import_module("blake3")`.
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "import_module"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                assert node.args[0].value != "blake3", (
                    "manifest.py loads blake3 via importlib — ADR-0001 violation"
                )


@pytest.mark.parametrize(
    "planted",
    [
        "import blake3\n",
        "from blake3 import blake3\n",
        "import importlib\nimportlib.import_module('blake3')\n",
    ],
)
def test_ast_walker_catches_planted_violations(planted: str, tmp_path: Path) -> None:
    """Mutation guard: the AST walker rejects every direct-blake3 shape."""
    src_path = tmp_path / "planted.py"
    src_path.write_text(planted, encoding="utf-8")
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
    caught = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name == "blake3" for a in node.names):
            caught = True
        elif isinstance(node, ast.ImportFrom) and node.module == "blake3":
            caught = True
        elif isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "import_module"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "blake3"
            ):
                caught = True
    assert caught, f"planted violation not caught: {planted!r}"
