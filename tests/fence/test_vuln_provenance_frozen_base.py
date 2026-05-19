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

**S1-05 carve-out** — the three upstream-syft Pydantic models
(`SyftSbom`, `SyftArtifact`, `SyftLocation`) deliberately do NOT
inherit `_Frozen`: they need ``extra="allow"`` (the inverse posture)
because the upstream syft JSON schema evolves and tightening the model
boundary would break every real-world SBOM the moment Anchore ships a
new field. This is the *single* Phase 7 exception, called out in the
story Notes and mitigated by S4-04's adapter-side AST-walk fence
(adapters read only `_KNOWN_*_FIELDS`). The carve-out lives as the
``_DELIBERATE_EXTRA_ALLOW_RECORDS`` allowlist below; widening it
requires an ADR-0004 amendment.
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

# Phase 7 S1-05 carve-out — the upstream-syft Pydantic models declare
# ``extra="allow"`` (the inverse posture of ``_Frozen``) because the
# upstream Anchore schema evolves and a strict boundary would break
# real-world SBOMs. The carve-out is `(filename, class_name)`-scoped so a
# different module with the same class name still trips the fence.
# Mitigation lives at the consumer boundary: S4-04's AST-walk fence pins
# every adapter to read only the fields in `syft_reader._KNOWN_*_FIELDS`.
_DELIBERATE_EXTRA_ALLOW_RECORDS: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("syft_reader.py", "SyftLocation"),
        ("syft_reader.py", "SyftArtifact"),
        ("syft_reader.py", "SyftSbom"),
    }
)


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
    is the single admitted `BaseModel` subclass.

    The S1-05 ``_DELIBERATE_EXTRA_ALLOW_RECORDS`` allowlist admits the
    three upstream-syft models by `(filename, class_name)` — see the
    module docstring for the rationale."""
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
        # S1-05 deliberate carve-out for the upstream-syft models.
        if (path.name, node.name) in _DELIBERATE_EXTRA_ALLOW_RECORDS:
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
        "amend ADR-0004 and update `_DELIBERATE_EXTRA_ALLOW_RECORDS`."
    )


def test_s1_05_carve_out_actually_carries_extra_allow() -> None:
    """The S1-05 deliberate carve-out is not a free pass — every class in
    ``_DELIBERATE_EXTRA_ALLOW_RECORDS`` must literally declare
    ``extra="allow"`` in its ``model_config``. If a future maintainer
    flips one to ``extra="forbid"``, the carve-out no longer matches its
    documented reason and the class should rejoin the `_Frozen` tree.

    This pins the *intent* of the carve-out, not just the inheritance
    shape (Rule 9).
    """
    by_file: dict[str, set[str]] = {}
    for filename, cls in _DELIBERATE_EXTRA_ALLOW_RECORDS:
        by_file.setdefault(filename, set()).add(cls)

    for filename, expected_classes in by_file.items():
        candidates = [p for p in _collect_py_files(_PRIMITIVE_ROOT) if p.name == filename]
        assert candidates, (
            f"_DELIBERATE_EXTRA_ALLOW_RECORDS names {filename!r} but no such "
            f"file exists under {_PRIMITIVE_ROOT}; the carve-out is stale."
        )
        tree = ast.parse(candidates[0].read_text(encoding="utf-8"))
        seen: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or node.name not in expected_classes:
                continue
            seen.add(node.name)
            # Find `model_config = ConfigDict(extra="allow")` (or any
            # keyword='allow' on a ConfigDict call) inside the class body.
            has_extra_allow = False
            for stmt in node.body:
                if not isinstance(stmt, ast.Assign):
                    continue
                if not any(
                    isinstance(t, ast.Name) and t.id == "model_config" for t in stmt.targets
                ):
                    continue
                if not isinstance(stmt.value, ast.Call):
                    continue
                for kw in stmt.value.keywords:
                    if (
                        kw.arg == "extra"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value == "allow"
                    ):
                        has_extra_allow = True
            assert has_extra_allow, (
                f"{filename}::{node.name} is in _DELIBERATE_EXTRA_ALLOW_RECORDS "
                "but does not declare `model_config = ConfigDict(extra='allow')`. "
                "The carve-out exists *because of* `extra='allow'`; if you removed "
                "it, remove the carve-out entry too (the class should rejoin "
                "`_Frozen`)."
            )
        missing = expected_classes - seen
        assert not missing, (
            f"_DELIBERATE_EXTRA_ALLOW_RECORDS names classes not defined in "
            f"{filename}: {sorted(missing)}. The carve-out is stale."
        )
