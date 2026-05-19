"""Phase 7 S1-02 AC-9 — module purity fence on the new primitive's `types.py`.

AST-walks `codegenie.primitives.vuln_provenance.types` and asserts the set
of top-level imported modules is **exactly** `{__future__, typing, enum,
pydantic}` — not a subset. Drift in either direction (a missing import
that should be there, or a new sibling-package dependency) is a CI failure.

Mirrors the Phase 3 S1-01 / Phase 2 S1-04 / S1-05 module-purity precedent
(see `tests/unit/types/test_module_purity.py`).

The fence keeps the seed of the discriminated union free of sibling-package
imports so S1-03 (which adds the seven variants) and downstream adapter
plugins can compose `Provenance` without dragging logging / fs / probe
dependencies into the type vocabulary.
"""

from __future__ import annotations

import ast
import inspect
from typing import Final

import codegenie.primitives.vuln_provenance.types as types_mod

_ALLOWED_TOP_LEVEL_IMPORTS: Final[frozenset[str]] = frozenset(
    {
        "__future__",
        "typing",
        "enum",
        "pathlib",
        "pydantic",
        # S1-03 — the seven variants' field types reference the kernel-tier
        # newtypes (`ImageDigest`, `LayerDigest`, `RuntimeId`,
        # `DockerStageName`, `PackageId`). The single sibling-package
        # dependency admitted by ADR-0004; widening this set further is an
        # ADR-0004 amendment.
        "codegenie.types.identifiers",
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
            # `node.module` is None on relative-from imports — surface as a
            # non-allowed sentinel so the fence catches them.
            names.add(node.module or "<relative-import>")
    return names


def test_types_module_imports_are_exactly_the_allowed_set() -> None:
    src = inspect.getsource(types_mod)
    imported = _imported_module_names(src)
    assert imported == _ALLOWED_TOP_LEVEL_IMPORTS, (
        "codegenie.primitives.vuln_provenance.types imports drifted from the "
        f"exact allowlist {sorted(_ALLOWED_TOP_LEVEL_IMPORTS)}; got "
        f"{sorted(imported)}. Extras must be admitted by an ADR-0004 amendment; "
        "missing imports indicate the module lost its type-vocabulary seed."
    )


def test_types_module_has_no_relative_imports() -> None:
    """Belt-and-braces: catch a sneaky `from . import x` that bypasses the
    name-only check above."""
    src = inspect.getsource(types_mod)
    imported = _imported_module_names(src)
    assert "<relative-import>" not in imported, (
        "codegenie.primitives.vuln_provenance.types uses a relative import; "
        "kernel-tier modules must import via absolute paths."
    )
