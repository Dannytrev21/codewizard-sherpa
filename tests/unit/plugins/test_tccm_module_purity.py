"""Phase-3 S3-01 — AST source-scan for ``codegenie.plugins.tccm`` import
allowlist + helper-extraction discipline.

Pins AC-17 (single ``_NAMESPACE_RE`` call site) and AC-21 (imports subset of
the closed allowlist). Catches a future refactor that fans the namespace
regex across the file, or sneaks a logger / I/O / sibling-module import into
this kernel-tier value module.
"""

from __future__ import annotations

import ast
from pathlib import Path

import codegenie.plugins.tccm as _tccm_mod

# Imports the module is allowed to declare. ``codegenie.errors`` is NOT in
# the allowlist — ``TCCMParseError`` is a frozen Pydantic ``BaseModel``, not a
# ``CodegenieError`` subclass (AC-4 / Validation notes).
_ALLOWED_MODULES = {
    "__future__",
    "re",
    "typing",
    "collections.abc",
    "pydantic",
    "codegenie.types.identifiers",
    "codegenie.result",
}


def _imports_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
    return out


def test_tccm_module_imports_subset_of_allowlist() -> None:
    """AC-21 — no logger, no I/O, no sibling Phase-3 modules."""
    src = Path(_tccm_mod.__file__)
    imports = _imports_in(src)
    extra = imports - _ALLOWED_MODULES
    assert not extra, f"unexpected imports in plugins/tccm.py: {extra}"


def test_namespace_re_fullmatch_appears_only_in_helper() -> None:
    """AC-17 — single helper owns ``_NAMESPACE_RE`` use; new callers must route through it."""
    src_text = Path(_tccm_mod.__file__).read_text(encoding="utf-8")
    n = src_text.count("_NAMESPACE_RE.fullmatch(") + src_text.count("_NAMESPACE_RE.match(")
    assert n == 1, (
        f"Expected exactly one call site for _NAMESPACE_RE; found {n}. "
        "All namespace-key validation must route through _validate_namespace_keys (AC-17)."
    )
