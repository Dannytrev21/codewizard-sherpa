"""Phase 6 S1-01 AC-6 — placeholder fence: Phase 6.5 must not depend on graph internals.

This fence walks a *hypothetical* ``tests/integration/phase65_harness/`` tree
(skipped when absent — Phase 6.5 has not opened yet) and asserts no Python
file under it imports:

* ``plugins.vulnerability_remediation__node__npm.subgraph`` (Phase 6 graph internals)
* ``codegenie.workflows.vuln_ledger`` (Phase 6 ledger internals)
* Any module name beginning with ``_`` (private)

The actual harness fence lands in Phase 6.5's S1; this placeholder lives in
``tests/fence/`` so the executor cannot forget it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HARNESS_DIR = _REPO_ROOT / "tests" / "integration" / "phase65_harness"

_FORBIDDEN_PREFIXES = (
    "plugins.vulnerability_remediation__node__npm.subgraph",
    "codegenie.workflows.vuln_ledger",
)


def _iter_imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                yield node.module


def test_phase65_harness_does_not_touch_phase6_internals() -> None:
    if not _HARNESS_DIR.exists():
        pytest.skip("phase65_harness/ not yet created — placeholder fence")
    for py in _HARNESS_DIR.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for module_name in _iter_imports(tree):
            for prefix in _FORBIDDEN_PREFIXES:
                assert not module_name.startswith(prefix), (
                    f"{py} imports {module_name!r} — Phase 6.5 harness must not "
                    f"depend on Phase 6 graph or ledger internals."
                )
            # Underscore-prefixed module names anywhere in the dotted path are
            # private — same rule, broader catch.
            parts = module_name.split(".")
            for i, part in enumerate(parts):
                if part.startswith("_") and ".".join(parts[: i + 1]).startswith("codegenie."):
                    raise AssertionError(
                        f"{py} imports private module {module_name!r} — "
                        f"Phase 6.5 may only import the four ADR-0001 public names."
                    )
