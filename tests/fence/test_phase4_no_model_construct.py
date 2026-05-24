"""Phase 4 S1-02 — AC-8: ``model_construct()`` bypasses validation; ban it
under ``src/codegenie/fallback/`` and ``src/codegenie/rag/``.

ADR-0001: every ``PlanProposal`` instance must run the smart-constructor
validators. ``Model.model_construct(...)`` skips them — using it inside the
Phase-4 fallback or RAG packages would defeat the closed-union firewall.
"""

from __future__ import annotations

import ast
import pathlib

import codegenie

_ROOT = pathlib.Path(codegenie.__file__).parent


def test_no_model_construct_in_phase4() -> None:
    offenders: list[tuple[str, int]] = []
    for path in (_ROOT / "fallback", _ROOT / "rag"):
        if not path.exists():
            continue
        for py in path.rglob("*.py"):
            tree = ast.parse(py.read_text())
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "model_construct"
                ):
                    offenders.append((str(py), node.lineno))
    assert not offenders, f"model_construct() bypasses validation: {offenders}"
