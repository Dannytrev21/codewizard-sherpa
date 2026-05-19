"""Phase 7 S1-02 AC-14 — `model_construct` bypass fence.

`Pydantic.BaseModel.model_construct(...)` builds a model instance **without
running validators**. A call site under `src/codegenie/primitives/vuln_provenance/`
could silently admit a `DistroPackage(name="", distro="centos", version="")`
and from there poison every downstream consumer.

Phase 7 ADR-0004 §Consequences names this fence verbatim:

> A fence asserts no `model_construct()` call sites under
> `src/codegenie/primitives/vuln_provenance/`.

This module is that fence. AST-walks every `.py` file under the primitive
and asserts no `Call` node whose attribute access ends in `model_construct`
exists.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

_PRIMITIVE_ROOT: Final[Path] = (
    Path(__file__).resolve().parents[2] / "src" / "codegenie" / "primitives" / "vuln_provenance"
)


def _collect_py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _find_model_construct_calls(source: str) -> list[tuple[int, str]]:
    """Return `[(lineno, snippet), ...]` for every `*.model_construct(...)`
    call site in the source. Matches both bound (`DistroPackage.model_construct`)
    and chained (`get_model().model_construct(...)`) shapes."""
    tree = ast.parse(source)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "model_construct":
            hits.append((node.lineno, ast.unparse(func)))
    return hits


@pytest.mark.parametrize(
    "path",
    _collect_py_files(_PRIMITIVE_ROOT),
    ids=lambda p: str(p.relative_to(_PRIMITIVE_ROOT)),
)
def test_no_model_construct_calls_in_primitive(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    hits = _find_model_construct_calls(source)
    assert hits == [], (
        f"{path}: `model_construct(...)` is forbidden under "
        f"`primitives/vuln_provenance/` (Phase 7 ADR-0004 §Consequences — "
        "validation bypass). Call sites: "
        f"{hits}. Use the standard validating constructor instead."
    )
