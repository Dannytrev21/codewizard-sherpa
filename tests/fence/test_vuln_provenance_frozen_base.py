"""Phase 7 S1-02 AC-11 — `_Frozen` inheritance fence for the vuln-provenance
primitive.

AST-walks every `.py` file under `src/codegenie/primitives/vuln_provenance/`
and asserts that every `class X(BaseModel)` (or transitive Pydantic
subclass) inherits from `_Frozen`. Locks the new Phase 7 convention:
**no Phase 7 primitive may bypass `_Frozen` via inline
`ConfigDict(frozen=True, extra="forbid")` shortcuts.**

Phase 3's `transforms/outcomes.py` inline-config style is grandfathered
(predates the `_Frozen` base); the fence scope is `primitives/vuln_provenance/`
only. Story file:
`docs/phases/07-migration-task-class/stories/
S1-02-provenance-enums-and-distro-package.md §AC-11`.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

_PRIMITIVE_ROOT: Final[Path] = (
    Path(__file__).resolve().parents[2] / "src" / "codegenie" / "primitives" / "vuln_provenance"
)

# Bases that count as "Pydantic record" subjects of the fence. `_Frozen`
# itself is the only direct `BaseModel` subclass admitted; any future
# `_Frozen`-derived intermediate (e.g. `_FrozenWithSlots`) lands here too.
_PYDANTIC_BASE_NAMES: Final[frozenset[str]] = frozenset({"BaseModel"})
# Bases admitted as "transitively frozen" — i.e. the class inherits from
# one of these, which themselves inherit from `_Frozen`.
_ADMITTED_FROZEN_BASES: Final[frozenset[str]] = frozenset({"_Frozen"})


def _collect_py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _base_names(bases: list[ast.expr]) -> list[str]:
    """Render each base expression as the dotted-or-bare identifier so the
    fence can match against the admitted-base allowlist."""
    out: list[str] = []
    for base in bases:
        if isinstance(base, ast.Name):
            out.append(base.id)
        elif isinstance(base, ast.Attribute):
            # e.g. `pydantic.BaseModel`
            parts: list[str] = []
            cur: ast.expr = base
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
            out.append(".".join(reversed(parts)))
        else:
            # ast.Subscript (e.g. Generic[T]) or other — skip; the fence is
            # about Pydantic record bases, which are name-or-attribute only.
            continue
    return out


def _is_frozen_base(base_names: list[str]) -> bool:
    """Direct or via-admitted-intermediate `_Frozen` inheritance."""
    return any(name in _ADMITTED_FROZEN_BASES for name in base_names)


def _is_basemodel_definition(class_node: ast.ClassDef) -> bool:
    """`class X(BaseModel)` or `class X(pydantic.BaseModel)` — the body the
    fence applies to (the `_Frozen` declaration itself)."""
    return any(
        name.split(".")[-1] in _PYDANTIC_BASE_NAMES for name in _base_names(class_node.bases)
    )


def _is_frozen_inheritor(class_node: ast.ClassDef) -> bool:
    return _is_frozen_base(_base_names(class_node.bases))


def _violations_in_file(path: Path) -> list[tuple[str, int]]:
    """Return `[(class_name, lineno), ...]` for every Pydantic record under
    `primitives/vuln_provenance/` that bypasses `_Frozen`. `_Frozen` itself
    is the single admitted `BaseModel` subclass."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    violations: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = _base_names(node.bases)
        # `_Frozen` itself — the one admitted BaseModel subclass.
        if node.name == "_Frozen" and _is_basemodel_definition(node):
            continue
        if _is_frozen_inheritor(node):
            continue
        # If the class inherits from BaseModel (directly or via attribute)
        # without `_Frozen` in the MRO declaration, it's a fence violation.
        if any(name.split(".")[-1] in _PYDANTIC_BASE_NAMES for name in bases):
            violations.append((node.name, node.lineno))
    return violations


def test_primitive_root_exists() -> None:
    assert _PRIMITIVE_ROOT.is_dir(), (
        f"Phase 7 ADR-0004 primitive home missing: {_PRIMITIVE_ROOT}. "
        "S1-02 must create it before the fence can scope."
    )


@pytest.mark.parametrize(
    "path",
    _collect_py_files(_PRIMITIVE_ROOT),
    ids=lambda p: str(p.relative_to(_PRIMITIVE_ROOT)),
)
def test_every_pydantic_record_inherits_frozen(path: Path) -> None:
    violations = _violations_in_file(path)
    assert violations == [], (
        f"{path}: classes that subclass `BaseModel` directly bypass `_Frozen` "
        f"(Phase 7 ADR-0004 §Consequences requires inheritance): "
        f"{violations}. Inherit from `_Frozen` instead, or — if intentional — "
        "amend ADR-0004 and update `_ADMITTED_FROZEN_BASES`."
    )
