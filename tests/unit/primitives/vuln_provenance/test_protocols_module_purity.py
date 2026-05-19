"""Phase 7 S1-04 AC-8 — module-purity fences on the new ``protocols.py``
and ``errors.py`` modules.

The Protocol is pure type-level — no logging, no filesystem, no I/O. The
error hierarchy is markers-only — only ``codegenie.errors`` admits. Both
fences AST-walk the module and assert the set of top-level imports is a
subset of the allowed list. Drift triggers a hard CI failure.

Mirrors ``tests/unit/primitives/vuln_provenance/test_types_module_purity.py``.
"""

from __future__ import annotations

import ast
import inspect
from typing import Final

import codegenie.primitives.vuln_provenance.errors as errors_mod
import codegenie.primitives.vuln_provenance.protocols as protocols_mod

_ALLOWED_PROTOCOLS_IMPORTS: Final[frozenset[str]] = frozenset(
    {
        "__future__",
        "typing",
        "codegenie.types.identifiers",
        "codegenie.primitives.vuln_provenance.types",
    }
)

_ALLOWED_ERRORS_IMPORTS: Final[frozenset[str]] = frozenset(
    {
        "__future__",
        "codegenie.errors",
    }
)


def _imported_module_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "<relative-import>")
    return names


def test_protocols_module_imports_are_subset_of_allowlist() -> None:
    src = inspect.getsource(protocols_mod)
    imported = _imported_module_names(src)
    extras = imported - _ALLOWED_PROTOCOLS_IMPORTS
    assert not extras, (
        "codegenie.primitives.vuln_provenance.protocols imported modules "
        f"{sorted(extras)} that are not on the AC-8 allowlist "
        f"{sorted(_ALLOWED_PROTOCOLS_IMPORTS)}. Adding a sibling-package "
        "dependency requires an ADR-0004 amendment."
    )


def test_protocols_module_has_no_relative_imports() -> None:
    src = inspect.getsource(protocols_mod)
    imported = _imported_module_names(src)
    assert "<relative-import>" not in imported, (
        "codegenie.primitives.vuln_provenance.protocols uses a relative "
        "import; kernel-tier modules must import via absolute paths."
    )


def test_errors_module_imports_are_subset_of_allowlist() -> None:
    src = inspect.getsource(errors_mod)
    imported = _imported_module_names(src)
    extras = imported - _ALLOWED_ERRORS_IMPORTS
    assert not extras, (
        "codegenie.primitives.vuln_provenance.errors imported modules "
        f"{sorted(extras)} that are not on the AC-8 allowlist "
        f"{sorted(_ALLOWED_ERRORS_IMPORTS)}. The error hierarchy is "
        "markers-only — adding logging / fs / I/O is an ADR-0004 amendment."
    )


def test_errors_module_has_no_relative_imports() -> None:
    src = inspect.getsource(errors_mod)
    imported = _imported_module_names(src)
    assert "<relative-import>" not in imported, (
        "codegenie.primitives.vuln_provenance.errors uses a relative "
        "import; kernel-tier modules must import via absolute paths."
    )
