"""AST source-scan — no direct ``blake3`` / ``hashlib`` import inside
``codegenie.skills``.

AC-25 of S2-01: ADR-0001 mandates a single hashing chokepoint
(``codegenie.hashing``). The skills loader streams body bytes through the
new chokepoint extension ``content_hash_fd``; a future contributor who
imports ``blake3`` or ``hashlib`` here breaks the Open/Closed boundary the
ADR pins.
"""

from __future__ import annotations

import ast
import pathlib

import codegenie.skills as skills_pkg

_SKILLS_ROOT = pathlib.Path(skills_pkg.__file__).parent

_BANNED_MODULES = {"blake3", "hashlib"}


def test_no_skills_module_imports_blake3_or_hashlib_directly() -> None:
    offenders: list[tuple[str, int, str]] = []
    for py_path in _SKILLS_ROOT.rglob("*.py"):
        tree = ast.parse(py_path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in _BANNED_MODULES or any(
                        alias.name.startswith(f"{m}.") for m in _BANNED_MODULES
                    ):
                        offenders.append((str(py_path), node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.module in _BANNED_MODULES or (
                    node.module is not None
                    and any(node.module.startswith(f"{m}.") for m in _BANNED_MODULES)
                ):
                    offenders.append((str(py_path), node.lineno, node.module or "?"))
    assert not offenders, (
        "codegenie.skills MUST route every hash through codegenie.hashing; "
        f"direct blake3/hashlib import sites: {offenders}"
    )


def test_hashing_all_grew_by_exactly_one_for_content_hash_fd() -> None:
    """AC-25: the chokepoint module grew by exactly one entry for S2-01's
    ``content_hash_fd``. Phase 3 S2-03 adds a second additive entry —
    ``tree_digest_of_files`` — which is itself pinned by
    :func:`test_hashing_all_includes_tree_digest_for_s2_03`.
    """
    import codegenie.hashing as h

    # Six exports = the original five + the S2-01 addition.
    assert "content_hash_fd" in h.__all__
    assert len(h.__all__) == 7, (
        f"hashing.__all__ must have exactly 7 entries (5 original + content_hash_fd"
        f" + tree_digest_of_files), got {len(h.__all__)}: {h.__all__}"
    )


def test_hashing_all_includes_tree_digest_for_s2_03() -> None:
    """Phase 3 S2-03 (ADR-0001 additive extension): the chokepoint exports
    a tree-digest helper for the plugin loader's integrity check."""
    import codegenie.hashing as h

    assert "tree_digest_of_files" in h.__all__
