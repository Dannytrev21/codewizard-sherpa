"""S6-01 AC-CHOKE + AC-NOPATH — ``events.py`` hashing-chokepoint fence.

AST-walks :mod:`codegenie.plugins.events` and fails on:

- any direct ``import blake3`` / ``from blake3 import …`` — every BLAKE3 call
  in the module must route through :mod:`codegenie.hashing` (Phase-0 ADR-0001
  chokepoint discipline; mirrors
  ``tests/unit/plugins/test_cache_no_blake3_import.py``);
- any ``Path``-typed field on an event variant — Phase 9's cross-machine
  projector reads these records, and absolute paths leak host structure
  (CLAUDE.md §"Absolute-path scrubbing"). Event payloads use ``str`` or
  domain newtypes, never :class:`pathlib.Path`.
"""

from __future__ import annotations

import ast
from pathlib import Path

_EVENTS_MODULE = Path("src/codegenie/plugins/events.py")


def _module_imports() -> set[str]:
    tree = ast.parse(_EVENTS_MODULE.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_events_module_does_not_import_blake3() -> None:
    """AC-CHOKE: only ``codegenie.hashing`` may import ``blake3``."""
    offenders = {name for name in _module_imports() if name.split(".")[0] == "blake3"}
    assert not offenders, (
        f"{_EVENTS_MODULE}: ADR-0001 chokepoint — BLAKE3 must route through "
        f"codegenie.hashing.content_hash_bytes; found direct import(s): {offenders}"
    )


def test_events_module_routes_hashing_through_codegenie_hashing() -> None:
    """AC-CHOKE: the module imports the sanctioned chokepoint helper."""
    assert "codegenie.hashing" in _module_imports(), (
        f"{_EVENTS_MODULE}: expected an import of codegenie.hashing — the only "
        f"sanctioned BLAKE3 entry point (ADR-0001)."
    )


def test_no_event_variant_declares_a_path_field() -> None:
    """AC-NOPATH: no event payload field is annotated ``Path``."""
    tree = ast.parse(_EVENTS_MODULE.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        annotation = node.annotation
        names = {
            sub.id if isinstance(sub, ast.Name) else sub.attr
            for sub in ast.walk(annotation)
            if isinstance(sub, (ast.Name, ast.Attribute))
        }
        if "Path" in names:
            offenders.append(f"{node.target.id} (line {node.lineno})")
    assert not offenders, (
        f"{_EVENTS_MODULE}: event payloads must not carry Path fields "
        f"(Phase 9 cross-machine projector); found: {offenders}"
    )
