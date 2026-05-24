"""Phase-4 path-scoped fence (ADR-0003).

This complements (does not replace) the Phase-0 closure-scoped fence at
``tests/unit/test_pyproject_fence.py``. The original ``FORBIDDEN_LLM_SDKS``
*narrows* honestly — anthropic moves to path-scope here, and
sentence-transformers/torch are added (so we don't leave a hole for an
alternative embeddings backend).

Four assertions, one shared AST-walking scanner (``_phase4_scanner.walk_imports``)
consumed by every Phase-4 fence test (S1-05 AC-20). Mutating the scanner kills
every Phase-4 fence test simultaneously.
"""

from __future__ import annotations

import pathlib
from typing import Final

from tests.fence._phase4_scanner import ImportViolation, walk_imports

REPO_ROOT: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[2]

GATHER_PIPELINE_PATHS: Final[frozenset[str]] = frozenset(
    {
        "src/codegenie/probes/",
        "src/codegenie/coordinator/",
        "src/codegenie/cache/",
        "src/codegenie/output/",
        "src/codegenie/schema/",
    }
)
PHASE4_ADMITTED_PACKAGES: Final[frozenset[str]] = frozenset(
    {"anthropic", "chromadb", "fastembed", "onnxruntime"}
)
PHASE4_STILL_FORBIDDEN: Final[frozenset[str]] = frozenset(
    {
        "langgraph",
        "openai",
        "langchain",
        "transformers",
        "sentence_transformers",
        "torch",
    }
)
ONLY_LEAF_ANTHROPIC: Final[pathlib.Path] = (
    REPO_ROOT / "src/codegenie/fallback/leaf/anthropic_adapter.py"
)
RAG_PACKAGE: Final[pathlib.Path] = REPO_ROOT / "src/codegenie/rag"


def _src_files_under(rel_root: str) -> list[pathlib.Path]:
    root = REPO_ROOT / rel_root.rstrip("/")
    if not root.exists():
        return []
    return list(root.rglob("*.py"))


def test_gather_pipeline_has_no_phase4_admitted_or_forbidden_imports() -> None:
    """AC-8 (1) — the gather pipeline closure stays LLM-free."""
    forbidden = PHASE4_ADMITTED_PACKAGES | PHASE4_STILL_FORBIDDEN
    offenders: list[ImportViolation] = []
    for rel in GATHER_PIPELINE_PATHS:
        offenders.extend(walk_imports(_src_files_under(rel), forbidden=forbidden))
    assert not offenders, (
        "Gather-pipeline source imports forbidden package(s); ADR-0003 broken. "
        "PHASE4_ADMITTED_PACKAGES are admitted only under "
        "src/codegenie/fallback/leaf/ or src/codegenie/rag/; "
        "PHASE4_STILL_FORBIDDEN are denied closure-wide. "
        f"Offenders: {offenders}"
    )


def test_closure_wide_phase4_still_forbidden() -> None:
    """AC-8 (2) — no source anywhere imports PHASE4_STILL_FORBIDDEN packages."""
    all_src = _src_files_under("src/")
    offenders = walk_imports(all_src, forbidden=PHASE4_STILL_FORBIDDEN)
    assert not offenders, (
        "Source imports PHASE4_STILL_FORBIDDEN package(s) "
        "(langgraph is Phase 6's job; torch / sentence_transformers are not "
        f"admitted): {offenders}"
    )


def test_anthropic_imported_only_by_leaf_adapter() -> None:
    """AC-8 (3) — anthropic is single-callsite (the leaf adapter)."""
    all_src = _src_files_under("src/")
    leaf_resolved = ONLY_LEAF_ANTHROPIC.resolve()
    offenders = [
        v
        for v in walk_imports(all_src, forbidden={"anthropic"})
        if pathlib.Path(v.file).resolve() != leaf_resolved
    ]
    assert not offenders, (
        f"`anthropic` may be imported only by {ONLY_LEAF_ANTHROPIC} "
        f"(ADR-0003 single-callsite rule); offenders: {offenders}"
    )


def test_chromadb_fastembed_onnxruntime_only_under_rag() -> None:
    """AC-8 (4) — rag-substrate deps may live only under src/codegenie/rag/."""
    all_src = _src_files_under("src/")
    rag_resolved = RAG_PACKAGE.resolve()
    offenders = [
        v
        for v in walk_imports(all_src, forbidden={"chromadb", "fastembed", "onnxruntime"})
        if rag_resolved not in pathlib.Path(v.file).resolve().parents
    ]
    assert not offenders, (
        f"`chromadb`/`fastembed`/`onnxruntime` may be imported only under "
        f"{RAG_PACKAGE} (ADR-0003 rag-scoped admission); offenders: {offenders}"
    )
