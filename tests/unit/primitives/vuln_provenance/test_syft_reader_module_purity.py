"""Phase 7 S1-05 AC-8 — module purity fence on ``syft_reader.py``.

AST-walks ``codegenie.primitives.vuln_provenance.syft_reader`` and asserts
the set of top-level imported modules is a *subset* of the allowlist —
``{__future__, typing, pydantic}``. The reader is types-only: no I/O, no
logging, no sibling-package imports.

Mirrors `test_types_module_purity.py` (S1-02) and
`test_protocols_module_purity.py` (S1-04). The difference: this story
admits a *subset* check rather than equality, because Pydantic models
need at minimum ``BaseModel`` + ``ConfigDict``, but a future maintenance
change may legitimately drop ``__future__`` or ``typing`` if no
annotations need them. Drift into a *new* sibling-package import is what
the fence is designed to catch.
"""

from __future__ import annotations

import ast
import inspect
from typing import Final

import codegenie.primitives.vuln_provenance.syft_reader as syft_reader_mod

_ALLOWED_TOP_LEVEL_IMPORTS: Final[frozenset[str]] = frozenset(
    {
        "__future__",
        "typing",
        "pydantic",
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


def test_syft_reader_imports_are_subset_of_allowlist() -> None:
    src = inspect.getsource(syft_reader_mod)
    imported = _imported_module_names(src)
    extras = imported - _ALLOWED_TOP_LEVEL_IMPORTS
    assert not extras, (
        "codegenie.primitives.vuln_provenance.syft_reader introduced an "
        f"import outside the allowlist {sorted(_ALLOWED_TOP_LEVEL_IMPORTS)}: "
        f"{sorted(extras)}. Widening this set is an ADR-0004 amendment — the "
        "reader is intentionally types-only (no I/O, no logging, no siblings)."
    )


def test_syft_reader_has_no_relative_imports() -> None:
    src = inspect.getsource(syft_reader_mod)
    imported = _imported_module_names(src)
    assert "<relative-import>" not in imported, (
        "codegenie.primitives.vuln_provenance.syft_reader uses a relative "
        "import; kernel-tier modules must import via absolute paths."
    )


# --- AC-8.5 — no `model_construct()` call sites ------------------------------


def test_syft_reader_has_no_model_construct_call_sites() -> None:
    """ADR-0004 §Consequences fence — `model_construct()` is Pydantic's
    smart-constructor *bypass*: it skips validation entirely and stuffs
    an unvalidated dict into the model. Allowing it inside the primitive
    tree would let an adapter feed unsanitized data to downstream
    consumers under the cover of a typed object.

    `syft_reader.py` is the deserialization surface — the file most
    likely to attract a "performance shortcut" of the form
    ``SyftSbom.model_construct(**raw_dict)``. AST-walk every `Call`
    node and assert the attribute is not ``model_construct``.

    This pins *intent* (Rule 9): an impl that smuggled validation in
    `model_construct()` would silently break adapter trust in
    ``layerID`` / ``name`` / ``version`` field types.
    """
    src = inspect.getsource(syft_reader_mod)
    tree = ast.parse(src)
    bad: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "model_construct":
                bad.append(node.lineno)
    assert not bad, (
        "syft_reader.py uses Pydantic `model_construct()` "
        f"(lines: {bad}). That call bypasses validation — the whole point of "
        "the deliberate `extra='allow'` posture is that *known fields are "
        "still validated*. Use `model_validate()` instead, or amend ADR-0004."
    )
