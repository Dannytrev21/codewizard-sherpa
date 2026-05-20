"""S5-01b — :class:`TransformRegistry` unit tests.

Covers the registry surface (register / get / ``__contains__`` / ``__len__``),
the typed error markers, per-workflow-instance independence (no ``default_*``
singleton), and the module's import-set discipline. See
``docs/phases/03-vuln-deterministic-recipe/stories/S5-01b-transform-registry.md``
and ADR-0014.
"""

from __future__ import annotations

import ast
import inspect

import pytest

import codegenie.transforms as transforms_pkg
import codegenie.transforms.transform_registry as tr_mod
from codegenie.errors import CodegenieError
from codegenie.transforms.transform import Transform, TransformProvenance
from codegenie.transforms.transform_registry import (
    TransformAlreadyRegistered,
    TransformNotFound,
    TransformRegistry,
)
from codegenie.types.identifiers import (
    EventId,
    PluginId,
    RecipeId,
    TransformId,
    TransformKind,
)

# --- Test fixtures: a minimal concrete Transform ----------------------------


def _provenance() -> TransformProvenance:
    return TransformProvenance(
        plugin_id=PluginId("vulnerability-remediation--node--npm"),
        plugin_version="0.1.0",
        recipe_id=RecipeId("npm-semver-bump"),
        recipe_version="0.1.0",
        transform_kind=TransformKind("npm-lockfile-semver-bump"),
        capability_use_id=EventId("01HX0000000000000000000000"),
    )


class _FakeTransform(Transform):
    """Minimal concrete Transform — the registry never inspects anything
    beyond ``transform_id``, so diff/files are left trivial."""

    def __init__(self, transform_id: str) -> None:
        self.transform_id = TransformId(transform_id)
        self.diff_bytes = b""
        self.files_changed = ()
        self.provenance = _provenance()


_TID_A = "a" * 64
_TID_B = "b" * 64


# --- Surface ----------------------------------------------------------------


def test_all_is_exact_set() -> None:
    assert set(tr_mod.__all__) == {
        "TransformAlreadyRegistered",
        "TransformNotFound",
        "TransformRegistry",
    }


def test_not_reexported_from_transforms_package() -> None:
    # AC-Surface-2 — internal mechanism, not a Phase-5 contract symbol.
    assert "TransformRegistry" not in transforms_pkg.__all__


def test_no_module_level_singleton() -> None:
    # AC-Surface-3 — per-workflow injection; no default_* singleton.
    assert not any(isinstance(v, TransformRegistry) for v in vars(tr_mod).values())


def test_instances_are_independent() -> None:
    r1, r2 = TransformRegistry(), TransformRegistry()
    r1.register(_FakeTransform(_TID_A))
    assert len(r1) == 1
    assert len(r2) == 0


# --- register ---------------------------------------------------------------


def test_register_returns_same_object() -> None:
    reg = TransformRegistry()
    t = _FakeTransform(_TID_A)
    assert reg.register(t) is t


def test_register_then_contains_and_len() -> None:
    reg = TransformRegistry()
    t = _FakeTransform(_TID_A)
    reg.register(t)
    assert t.transform_id in reg
    assert len(reg) == 1


def test_register_two_distinct_ids() -> None:
    reg = TransformRegistry()
    a, b = _FakeTransform(_TID_A), _FakeTransform(_TID_B)
    reg.register(a)
    reg.register(b)
    assert len(reg) == 2
    assert reg.get(a.transform_id) is a
    assert reg.get(b.transform_id) is b


def test_register_duplicate_id_raises_and_first_wins() -> None:
    reg = TransformRegistry()
    first = _FakeTransform(_TID_A)
    second = _FakeTransform(_TID_A)  # same id, different object
    reg.register(first)
    with pytest.raises(TransformAlreadyRegistered) as exc_info:
        reg.register(second)
    assert exc_info.value.transform_id == TransformId(_TID_A)
    # First registration is unaffected.
    assert reg.get(TransformId(_TID_A)) is first
    assert len(reg) == 1


# --- get --------------------------------------------------------------------


def test_get_returns_exact_object() -> None:
    reg = TransformRegistry()
    t = _FakeTransform(_TID_A)
    reg.register(t)
    assert reg.get(t.transform_id) is t


def test_get_miss_raises_transform_not_found() -> None:
    reg = TransformRegistry()
    with pytest.raises(TransformNotFound) as exc_info:
        reg.get(TransformId(_TID_A))
    assert exc_info.value.transform_id == TransformId(_TID_A)


def test_contains_false_for_unregistered() -> None:
    reg = TransformRegistry()
    assert TransformId(_TID_A) not in reg
    assert "not-even-a-transform-id" not in reg  # never raises


# --- Typed error markers ----------------------------------------------------


def test_errors_subclass_codegenie_error() -> None:
    already = TransformAlreadyRegistered(TransformId(_TID_A), "mod.A", "mod.B")
    missing = TransformNotFound(TransformId(_TID_B))
    assert isinstance(already, CodegenieError)
    assert isinstance(missing, CodegenieError)
    assert already.transform_id == TransformId(_TID_A)
    assert missing.transform_id == TransformId(_TID_B)
    # Duplicate message names both colliding origins.
    assert "mod.A" in str(already) and "mod.B" in str(already)


# --- Discipline -------------------------------------------------------------


def test_import_set_is_within_allowlist() -> None:
    # AC-Disc-1 — no codegenie.plugins.* reach-through, no LLM SDK.
    allowed = {
        "__future__",
        "typing",
        "codegenie.errors",
        "codegenie.transforms.transform",
        "codegenie.types.identifiers",
    }
    tree = ast.parse(inspect.getsource(tr_mod))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "<relative>")
    assert imported <= allowed, f"unexpected imports: {sorted(imported - allowed)}"
