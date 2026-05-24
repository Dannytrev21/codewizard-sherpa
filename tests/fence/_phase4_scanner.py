"""Phase-4 path-scoped fence scanner (ADR-0003).

The single AST-walking kernel consumed by every Phase-4 fence test: the omnibus
``tests/fence/test_pyproject_fence_phase4.py``, the negative
``tests/fence/test_pyproject_fence_phase4_negatives.py`` mutation-guard suite,
AND the three targeted assertions
(``tests/fence/test_only_leaf_imports_anthropic.py``,
``tests/fence/test_rag_no_anthropic.py``,
``tests/fence/test_no_langgraph_in_phase4.py``).

There is exactly one AST-walking implementation under ``tests/fence/`` (S1-05
AC-20). Mutating it kills every Phase-4 fence test simultaneously — no test
re-implements ``ast.walk`` / ``ast.Import`` / ``ast.ImportFrom`` inline.

The diagnostic shape lives in each call site's assertion message — ``ImportViolation``
itself is a minimal ``(file, package)`` value (S1-05 AC-9): only the call site
knows which of the four path-scope rules was violated.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImportViolation:
    """Minimal value object: file path + offending top-level package name.

    No ``reason`` field by design — rule-specific remediation text is the call
    site's job (S1-05 AC-9). The omnibus fence (``test_pyproject_fence_phase4``)
    raises a different message than the targeted ``test_only_leaf_imports_anthropic``
    fence even when both fire on the same violation; coupling the message to the
    scanner would force the scanner to encode rule context it does not own.
    """

    file: str
    package: str


def _top_level_packages(tree: ast.AST) -> set[str]:
    """Return the set of top-level (third-party) package names imported by ``tree``.

    Both ``import X`` and ``from X.* import ...`` forms are collected. Relative
    imports (``node.level > 0`` on ``ast.ImportFrom``) are intra-package and not
    third-party, so the scanner ignores them — that is correct.
    """

    pkgs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                pkgs.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            pkgs.add(node.module.split(".", 1)[0])
    return pkgs


def walk_imports(files: Sequence[Path], *, forbidden: Iterable[str]) -> list[ImportViolation]:
    """Return one :class:`ImportViolation` per ``(file, forbidden-package)`` pair.

    A clean tree produces an empty list. Files that fail to parse (binary
    pollution, ``SyntaxError`` from a deliberate harness fixture, decode errors)
    are skipped silently — the live fence's job is to catch live regressions in
    well-formed Python, not to be a syntax checker.
    """

    forbidden_set = set(forbidden)
    out: list[ImportViolation] = []
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, SyntaxError):
            continue
        for pkg in _top_level_packages(tree):
            if pkg in forbidden_set:
                out.append(ImportViolation(file=str(f), package=pkg))
    return out
