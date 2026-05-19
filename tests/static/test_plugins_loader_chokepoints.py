"""S2-03 AC-14 — AST source-scan fence on :mod:`codegenie.plugins.loader`.

The loader is the **only** place under ``src/codegenie/plugins/`` that
imports anything for hashing or JSON parsing. Per Phase 0 ADR-0001 and
Phase 1 ADR-0009 those imports MUST route through the chokepoints
(:mod:`codegenie.hashing` and :mod:`codegenie.parsers.safe_json`), never
``hashlib``, ``blake3``, or ``json`` directly.

This fence parses :mod:`codegenie.plugins.loader`'s source with
:func:`ast.parse` and asserts no ``Import`` / ``ImportFrom`` node names
any forbidden module. Mirrors the in-codebase precedent at
``tests/fence/test_transforms_module_purity.py`` (Phase 3 S1-04).

Locality: this lives under ``tests/static/`` rather than ``tests/fence/``
because it is a per-module structural defence — adjacent to a single
source file's import surface — rather than a kernel-wide fence.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import codegenie.plugins.loader as loader_module

_FORBIDDEN_MODULES: Final[frozenset[str]] = frozenset({"hashlib", "blake3", "json"})


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


def test_loader_does_not_import_hashlib_blake3_or_json_directly() -> None:
    """ADR-0001 + Phase 1 ADR-0009 chokepoint discipline.

    ``codegenie.plugins.loader`` must route hashing through
    :mod:`codegenie.hashing` and JSON parsing through
    :mod:`codegenie.parsers.safe_json` — never the underlying primitives.
    """
    loader_path = Path(loader_module.__file__)
    source = loader_path.read_text(encoding="utf-8")
    imports = _imported_module_names(source)
    forbidden = imports & _FORBIDDEN_MODULES
    assert not forbidden, (
        f"codegenie.plugins.loader imports forbidden modules {sorted(forbidden)!r}; "
        f"route through codegenie.hashing or codegenie.parsers.safe_json instead "
        f"(ADR-0001 / Phase 1 ADR-0009)."
    )


def test_loader_imports_the_two_chokepoint_modules() -> None:
    """Positive AST assertion — the loader DOES import the chokepoints.

    Catches the mutant where someone removes the chokepoint call entirely
    (bypassing both the forbidden-import fence and the runtime route).
    """
    loader_path = Path(loader_module.__file__)
    source = loader_path.read_text(encoding="utf-8")
    imports = _imported_module_names(source)
    assert "codegenie.hashing" in imports, (
        "codegenie.plugins.loader must import from codegenie.hashing for tree-digest routing."
    )
    # ``codegenie.parsers.safe_json`` is reached through ``codegenie.plugins.lockfile`` —
    # the loader does not import it directly. Pin the indirection so a maintainer
    # who flattens the design back into the loader still routes through safe_json.
    assert "codegenie.plugins.lockfile" in imports, (
        "codegenie.plugins.loader must compose with codegenie.plugins.lockfile "
        "(which routes its JSON read through codegenie.parsers.safe_json)."
    )
