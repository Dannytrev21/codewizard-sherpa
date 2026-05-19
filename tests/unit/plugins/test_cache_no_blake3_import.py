"""S3-05 AC-13 — ADR-0001 chokepoint fence.

Neither :mod:`codegenie.plugins.cache` nor :mod:`codegenie.plugins.cache_gc`
may ``import blake3`` directly — all BLAKE3 must route through
:mod:`codegenie.hashing` (Phase-0 ADR-0001).
"""

from __future__ import annotations

import ast
import pathlib


def _imports(path: str) -> set[str]:
    tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_neither_cache_module_imports_blake3_directly() -> None:
    for path in (
        "src/codegenie/plugins/cache.py",
        "src/codegenie/plugins/cache_gc.py",
    ):
        names = _imports(path)
        offenders = {n for n in names if n.startswith("blake3")}
        assert not offenders, (
            f"{path}: ADR-0001 chokepoint — only codegenie.hashing imports blake3; "
            f"found: {offenders}"
        )
