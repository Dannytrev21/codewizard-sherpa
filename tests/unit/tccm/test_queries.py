"""Unit tests for ``codegenie.tccm.queries`` — story 02 S1-04.

Covers AC-3, AC-6, AC-12 (discriminator-string pin), AC-13 (JSON-shape pin),
AC-14 (immutability), AC-15 (per-variant foreign-payload rejection), AC-16
(exhaustive ``match`` + ``assert_never``).
"""

from __future__ import annotations

from typing import assert_never

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.tccm import (
    ConsumersOf,
    DerivedQuery,
    ProducersOf,
    RefsTo,
    ReverseLookup,
)

# `TestsExercising` is aliased on import — pytest collects any class whose name
# starts with "Test" and warns when the class declares an ``__init__`` (Pydantic
# BaseModel does). The alias keeps the public domain name stable while keeping
# pytest's collector quiet (L5 cross-story lesson; S1-03 precedent).
from codegenie.tccm import TestsExercising as ExerciseTestsQuery


# AC-6 — round-trip identity per variant.
@pytest.mark.parametrize(
    "q",
    [
        ConsumersOf(pkg="@org/p"),
        ProducersOf(pkg="@org/p"),
        ReverseLookup(module="src/x.ts"),
        RefsTo(symbol="Foo.bar"),
        ExerciseTestsQuery(symbol="Foo.bar"),
    ],
    ids=["consumers_of", "producers_of", "reverse_lookup", "refs_to", "tests_exercising"],
)
def test_derived_query_roundtrip(q: DerivedQuery) -> None:
    adapter: TypeAdapter[DerivedQuery] = TypeAdapter(DerivedQuery)
    decoded = adapter.validate_json(adapter.dump_json(q))
    assert decoded == q
    assert type(decoded) is type(q)


# AC-12 — discriminator-string literal pin (defaults + frozenset equality).
def test_compute_discriminator_strings_are_exactly_pinned() -> None:
    expected = {
        ConsumersOf: "consumers_of",
        ProducersOf: "producers_of",
        ReverseLookup: "reverse_lookup",
        RefsTo: "refs_to",
        ExerciseTestsQuery: "tests_exercising",
    }
    for cls, lit in expected.items():
        default = cls.model_fields["compute"].default
        assert default == lit, f"{cls.__name__}.compute default = {default!r}, expected {lit!r}"


def test_compute_discriminator_strings_form_exact_set() -> None:
    defaults = {
        cls.model_fields["compute"].default
        for cls in (
            ConsumersOf,
            ProducersOf,
            ReverseLookup,
            RefsTo,
            ExerciseTestsQuery,
        )
    }
    assert defaults == {
        "consumers_of",
        "producers_of",
        "reverse_lookup",
        "refs_to",
        "tests_exercising",
    }


# AC-13 — JSON-shape pin (closes the compute → tag symmetric-rename mutation).
@pytest.mark.parametrize(
    "variant, expected",
    [
        (ConsumersOf(pkg="x"), {"compute": "consumers_of", "pkg": "x"}),
        (ProducersOf(pkg="x"), {"compute": "producers_of", "pkg": "x"}),
        (ReverseLookup(module="x"), {"compute": "reverse_lookup", "module": "x"}),
        (RefsTo(symbol="x"), {"compute": "refs_to", "symbol": "x"}),
        (
            ExerciseTestsQuery(symbol="x"),
            {"compute": "tests_exercising", "symbol": "x"},
        ),
    ],
)
def test_derived_query_json_shape_pinned(variant: DerivedQuery, expected: dict[str, str]) -> None:
    assert variant.model_dump() == expected


# AC-14 — runtime immutability (every variant raises on field assignment).
@pytest.mark.parametrize(
    "instance, field",
    [
        (ConsumersOf(pkg="x"), "pkg"),
        (ProducersOf(pkg="x"), "pkg"),
        (ReverseLookup(module="x"), "module"),
        (RefsTo(symbol="x"), "symbol"),
        (ExerciseTestsQuery(symbol="x"), "symbol"),
    ],
    ids=["consumers_of", "producers_of", "reverse_lookup", "refs_to", "tests_exercising"],
)
def test_derived_query_variants_are_immutable(instance: DerivedQuery, field: str) -> None:
    with pytest.raises(ValidationError):
        setattr(instance, field, "new")


# AC-15 — per-variant ``extra="forbid"`` rejects foreign payload fields.
def test_consumers_of_rejects_module_field() -> None:
    with pytest.raises(ValidationError):
        ConsumersOf(pkg="x", module="y")  # type: ignore[call-arg]


def test_producers_of_rejects_symbol_field() -> None:
    with pytest.raises(ValidationError):
        ProducersOf(pkg="x", symbol="y")  # type: ignore[call-arg]


def test_reverse_lookup_rejects_pkg_field() -> None:
    with pytest.raises(ValidationError):
        ReverseLookup(module="x", pkg="y")  # type: ignore[call-arg]


def test_refs_to_rejects_pkg_field() -> None:
    with pytest.raises(ValidationError):
        RefsTo(symbol="x", pkg="y")  # type: ignore[call-arg]


def test_tests_exercising_rejects_module_field() -> None:
    with pytest.raises(ValidationError):
        ExerciseTestsQuery(symbol="x", module="y")  # type: ignore[call-arg]


# AC-16 — exhaustive match + assert_never over DerivedQuery.
def _describe(q: DerivedQuery) -> str:
    match q:
        case ConsumersOf(pkg=p):
            return f"consumers:{p}"
        case ProducersOf(pkg=p):
            return f"producers:{p}"
        case ReverseLookup(module=m):
            return f"reverse:{m}"
        case RefsTo(symbol=s):
            return f"refs:{s}"
        case ExerciseTestsQuery(symbol=s):
            return f"tests:{s}"
        case _:
            assert_never(q)


def test_match_is_exhaustive_over_derived_query() -> None:
    descriptions = [
        _describe(ConsumersOf(pkg="x")),
        _describe(ProducersOf(pkg="x")),
        _describe(ReverseLookup(module="x")),
        _describe(RefsTo(symbol="x")),
        _describe(ExerciseTestsQuery(symbol="x")),
    ]
    assert descriptions == [
        "consumers:x",
        "producers:x",
        "reverse:x",
        "refs:x",
        "tests:x",
    ]
