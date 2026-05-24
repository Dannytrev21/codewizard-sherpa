"""Forward-defensive: no module under ``src/codegenie/rag/`` may import
``anthropic`` (S1-05 AC-13 / ADR-0003 path-scope discipline).

Vacuously green until S4-xx lands ``src/codegenie/rag/`` — the rag substrate
has no reason to call into the leaf adapter directly.
"""

from __future__ import annotations

import pathlib

import codegenie
from tests.fence._phase4_scanner import walk_imports

_RAG = pathlib.Path(codegenie.__file__).parent / "rag"


def test_rag_does_not_import_anthropic() -> None:
    files = list(_RAG.rglob("*.py")) if _RAG.exists() else []
    offenders = walk_imports(files, forbidden={"anthropic"})
    assert not offenders, (
        f"`src/codegenie/rag/` must not import `anthropic` "
        f"(ADR-0003 path-scope discipline); offenders: {offenders}"
    )
