"""Phase 4 S1-01 — raw primitive annotations stay out of fallback/rag IDs."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Final

DOMAIN_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "budget_token",
        "cassette",
        "chain_head",
        "cve_id",
        "embedding_model",
        "manifest_path",
        "nonce",
        "package",
        "response_id",
        "similarity",
        "solved_example_id",
        "store_digest",
        "tokens_in",
        "tokens_out",
    }
)
RAW_PRIMITIVES: Final[frozenset[str]] = frozenset({"str", "int", "float", "bytes"})
SCAN_ROOTS: Final[tuple[Path, ...]] = (Path("src/codegenie/fallback"), Path("src/codegenie/rag"))


@dataclass(frozen=True)
class RawDomainAnnotation:
    path: Path
    line: int
    name: str
    annotation: str


def _annotation_name(annotation: ast.AST | None) -> str | None:
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return annotation.value
    return None


def _is_domain_name(name: str) -> bool:
    lowered = name.lower()
    return any(keyword in lowered for keyword in DOMAIN_KEYWORDS)


def _violations(path: Path) -> list[RawDomainAnnotation]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[RawDomainAnnotation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            annotation = _annotation_name(node.annotation)
            if annotation in RAW_PRIMITIVES and _is_domain_name(node.target.id):
                found.append(RawDomainAnnotation(path, node.lineno, node.target.id, annotation))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
                annotation = _annotation_name(arg.annotation)
                if annotation in RAW_PRIMITIVES and _is_domain_name(arg.arg):
                    found.append(RawDomainAnnotation(path, arg.lineno, arg.arg, annotation))
            return_annotation = _annotation_name(node.returns)
            if return_annotation in RAW_PRIMITIVES and _is_domain_name(node.name):
                found.append(RawDomainAnnotation(path, node.lineno, node.name, return_annotation))
    return found


def test_phase4_domain_ids_are_not_raw_primitives() -> None:
    paths = [path for root in SCAN_ROOTS if root.exists() for path in root.rglob("*.py")]
    found = [violation for path in paths for violation in _violations(path)]
    assert not found, (
        "Phase-4 domain identifiers must use NewTypes, not raw primitives: "
        + ", ".join(f"{item.path}:{item.line} {item.name}: {item.annotation}" for item in found)
    )
