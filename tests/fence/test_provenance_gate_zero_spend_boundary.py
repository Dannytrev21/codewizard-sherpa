"""Phase-4 S2-01 AC-8 — zero-token / zero-budget boundary fence.

``ProvenanceGate.classify`` is the **first** decision point on the Phase-4
fallback path; it must not even import a spend surface, let alone exercise
one. This fence walks ``src/codegenie/fallback/provenance_gate.py``'s AST
to prove no LLM/RAG/budget module is reachable from this primitive.

The integration-level event-absence proof lives in the S6-01 / S7-06
end-to-end tests; this story owns the primitive-level structural fence.

Sources of truth:
- ``docs/phases/04-vuln-llm-fallback-rag/stories/S2-01-provenance-gate-tier-zero.md`` AC-8.
- ``docs/phases/04-vuln-llm-fallback-rag/ADRs/0012-provenance-gate-explicit-tier-zero.md``.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Final

from codegenie.fallback.provenance_gate import ProvenanceGate

_MODULE_PATH: Final[Path] = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "codegenie"
    / "fallback"
    / "provenance_gate.py"
)

# Every name on this list is a "spend surface" the gate must not be able to
# reach by import. The bare top-level package name (``anthropic``, ``rag``)
# and any dotted submodule (``codegenie.fallback.budget``,
# ``codegenie.rag.store``) are both rejected by the prefix match below.
_FORBIDDEN_IMPORT_ROOTS: Final[frozenset[str]] = frozenset(
    {
        # Phase-4 in-tree spend surfaces.
        "codegenie.fallback.budget",
        "codegenie.fallback.leaf",
        "codegenie.fallback.prompt",
        "codegenie.fallback.cassette",
        "codegenie.rag",
        # Cross-cut Phase-4 LLM / embedding closure.
        "anthropic",
        "openai",
        "langchain",
        "langgraph",
        "transformers",
        "torch",
        "sentence_transformers",
        "chromadb",
        "fastembed",
        "onnxruntime",
    }
)


def _is_forbidden(module_name: str) -> bool:
    """Return ``True`` when ``module_name`` matches a forbidden root or a
    descendant of one."""
    return any(
        module_name == root or module_name.startswith(root + ".")
        for root in _FORBIDDEN_IMPORT_ROOTS
    )


def test_provenance_gate_imports_no_spend_surface() -> None:
    """AC-8: the gate module imports zero LLM/RAG/budget symbols."""
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))

    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            if _is_forbidden(node.module):
                offenders.append(f"from {node.module} import …")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden(alias.name):
                    offenders.append(f"import {alias.name}")

    assert offenders == [], (
        "ProvenanceGate must not import any spend surface — "
        f"found: {offenders}. The gate is the tier-0 short-circuit and "
        "lives before any LLM tokens are spent (Phase-4 ADR-0012)."
    )


def test_provenance_gate_classify_signature_has_no_budget_token() -> None:
    """AC-8: ``ProvenanceGate.classify`` has no ``BudgetToken`` parameter.

    Even with the import fence in place, an instance-state ``BudgetToken``
    could sneak a spend surface in. This pins the public method signature
    to the four typed provenance inputs only.
    """
    sig = inspect.signature(ProvenanceGate.classify)
    parameter_names = {name for name in sig.parameters if name != "self"}
    assert parameter_names == {"cve_id", "package_id", "image_ref", "sbom"}
    assert "token" not in sig.parameters
    assert "budget" not in sig.parameters
    assert "guard" not in sig.parameters


def test_provenance_gate_dataclass_has_no_spend_fields() -> None:
    """AC-8 + N3: the gate's instance state is exactly classifier + event_log."""
    from dataclasses import fields

    field_names = {f.name for f in fields(ProvenanceGate)}
    assert field_names == {"classifier", "event_log"}
