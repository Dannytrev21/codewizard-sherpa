"""Unit tests for ``codegenie.tccm.model`` — story 02 S1-04.

Covers AC-1 (``__all__`` exact-set), AC-2 (TCCM fields), AC-7 (TCCM round-trip),
AC-15 (TCCM extra="forbid"), AC-17 (no ``model_construct`` AST scan),
AC-18 (module purity AST scan), AC-19 (``__all__`` test),
AC-24 (empty / duplicate collection decisions), AC-25
(``TCCMLoadError`` markers-only structural test).
"""

from __future__ import annotations

import ast
import pathlib

import pytest
from pydantic import ValidationError

import codegenie.result as result_mod
import codegenie.tccm as tccm_pkg
import codegenie.tccm.loader as loader_mod
import codegenie.tccm.model as model_mod
import codegenie.tccm.queries as queries_mod
from codegenie.adapters import Trusted
from codegenie.errors import CodegenieError, TCCMLoadError
from codegenie.tccm import (
    TCCM,
    ConsumersOf,
    DerivedQuery,
    ProducersOf,
    RefsTo,
    ReverseLookup,
    TCCMLoader,
)

# Alias on import — `TestsExercising` collides with pytest's `Test*` collector.
from codegenie.tccm import TestsExercising as ExerciseTestsQuery
from codegenie.tccm.queries import DerivedQuery as DerivedQueryAlias  # noqa: F401
from codegenie.types.identifiers import ProbeId, SkillId, TaskClassId


# AC-1 / AC-19 — ``codegenie.tccm.__all__`` exact public surface.
def test_tccm_all_is_exactly_the_public_surface() -> None:
    assert set(tccm_pkg.__all__) == {
        "ConsumersOf",
        "DerivedQuery",
        "ProducersOf",
        "RefsTo",
        "ReverseLookup",
        "TCCM",
        "TCCMLoadError",
        "TCCMLoader",
        "TestsExercising",
    }
    for name in tccm_pkg.__all__:
        assert name in tccm_pkg.__dict__, f"{name} in __all__ but missing from module"


# AC-2 — TCCM field set is the documented five.
def test_tccm_model_fields_are_the_documented_five() -> None:
    assert set(TCCM.model_fields) == {
        "schema_version",
        "task_class",
        "required_probes",
        "required_skills",
        "derived_queries",
        "confidence_floor",
    }


# AC-7 — well-formed TCCM round-trips identity.
def test_tccm_roundtrip_identity() -> None:
    original = TCCM(
        schema_version="1",
        task_class=TaskClassId("ihc"),
        required_probes=[ProbeId("index_health")],
        required_skills=[SkillId("scip.maintenance")],
        derived_queries=[
            ConsumersOf(pkg="@org/p"),
            ProducersOf(pkg="@org/p"),
            ReverseLookup(module="src/x.ts"),
            RefsTo(symbol="Foo.bar"),
            ExerciseTestsQuery(symbol="Foo.bar"),
        ],
        confidence_floor=Trusted(),
    )
    decoded = TCCM.model_validate(original.model_dump())
    assert decoded == original
    # Concrete-class preservation across the five DerivedQuery variants.
    assert [type(q) for q in decoded.derived_queries] == [
        ConsumersOf,
        ProducersOf,
        ReverseLookup,
        RefsTo,
        ExerciseTestsQuery,
    ]


# AC-15 — TCCM rejects extra fields (closes "drop extra=forbid on TCCM" mutation).
def test_tccm_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        TCCM.model_validate(
            {
                "schema_version": "1",
                "task_class": "x",
                "required_probes": [],
                "required_skills": [],
                "derived_queries": [],
                "confidence_floor": {"kind": "trusted"},
                "notes": "bonus",
            }
        )


# AC-14 — TCCM instance is frozen.
def test_tccm_is_immutable() -> None:
    t = TCCM(
        schema_version="1",
        task_class=TaskClassId("x"),
        required_probes=[],
        required_skills=[],
        derived_queries=[],
        confidence_floor=Trusted(),
    )
    with pytest.raises(ValidationError):
        t.schema_version = "2"  # type: ignore[misc]


# AC-17 — ``model_construct`` source-scan ban across S1-04's modules.
def test_tccm_modules_have_no_model_construct() -> None:
    modules = [result_mod, model_mod, queries_mod, loader_mod]
    for mod in modules:
        tree = ast.parse(pathlib.Path(mod.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "model_construct":
                pytest.fail(f"{mod.__name__} uses model_construct (forbidden by AC-17)")


# AC-18 — module purity for queries.py + model.py (no I/O imports).
def test_tccm_pure_modules_have_no_io_imports() -> None:
    allowed_prefixes = (
        "__future__",
        "typing",
        "pydantic",
        "codegenie.adapters",
        "codegenie.tccm.queries",
        "codegenie.types",
    )
    for mod in (model_mod, queries_mod):
        tree = ast.parse(pathlib.Path(mod.__file__).read_text())
        for node in ast.walk(tree):
            target = None
            if isinstance(node, ast.Import):
                target = node.names[0].name
            elif isinstance(node, ast.ImportFrom):
                target = node.module
            if target is None:
                continue
            assert any(target == p or target.startswith(p + ".") for p in allowed_prefixes), (
                f"{mod.__name__} imports {target!r} — forbidden in pure modules"
            )


# AC-24 — empty / duplicate collection decisions.
def test_tccm_accepts_empty_derived_queries() -> None:
    t = TCCM(
        schema_version="1",
        task_class=TaskClassId("x"),
        required_probes=[],
        required_skills=[],
        derived_queries=[],
        confidence_floor=Trusted(),
    )
    assert t.derived_queries == []


def test_tccm_accepts_empty_required_probes_and_skills() -> None:
    t = TCCM(
        schema_version="1",
        task_class=TaskClassId("x"),
        required_probes=[],
        required_skills=[],
        derived_queries=[ConsumersOf(pkg="p")],
        confidence_floor=Trusted(),
    )
    assert t.required_probes == []
    assert t.required_skills == []


def test_tccm_accepts_duplicate_required_probes() -> None:
    t = TCCM(
        schema_version="1",
        task_class=TaskClassId("x"),
        required_probes=[ProbeId("a"), ProbeId("a")],
        required_skills=[],
        derived_queries=[],
        confidence_floor=Trusted(),
    )
    assert t.required_probes == [ProbeId("a"), ProbeId("a")]


# AC-25 — TCCMLoadError is a bare marker.
def test_tccm_load_error_is_bare_marker() -> None:
    assert TCCMLoadError.__init__ is Exception.__init__
    assert issubclass(TCCMLoadError, CodegenieError)


# Sanity guard — keep DerivedQueryAlias usage live so flake doesn't strip the
# import (it documents that ``DerivedQuery`` is the only alias the surface uses).
def test_derived_query_alias_is_the_package_export() -> None:
    assert DerivedQuery is DerivedQueryAlias


# TCCMLoader has no __init__ (pure-data-at-construction discipline).
def test_tccm_loader_has_no_custom_init() -> None:
    assert TCCMLoader.__init__ is object.__init__
