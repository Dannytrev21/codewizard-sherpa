"""Unit tests for ``codegenie.adapters`` — story 02 S1-03.

Covers all 16 acceptance criteria from
``docs/phases/02-context-gather-layers-b-g/stories/S1-03-adapter-protocols-confidence.md``.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import assert_never

import pytest
from pydantic import TypeAdapter, ValidationError

import codegenie
from codegenie import adapters as adapters_pkg
from codegenie.adapters import (
    AdapterConfidence,
    Degraded,
    DepGraphAdapter,
    ImportGraphAdapter,
    Occurrence,
    ScipAdapter,
    TestId,
    TestInventoryAdapter,
    Trusted,
    Unavailable,
)
from codegenie.adapters import confidence as confidence_mod
from codegenie.adapters import protocols as protocols_mod

# -------- __all__ surface (AC-1) --------

EXPECTED_PUBLIC_SURFACE = {
    "DepGraphAdapter",
    "ImportGraphAdapter",
    "ScipAdapter",
    "TestInventoryAdapter",
    "AdapterConfidence",
    "Trusted",
    "Degraded",
    "Unavailable",
    "Occurrence",
    "TestId",
}


def test_adapters_all_is_exactly_the_public_surface() -> None:
    """AC-1: ``__all__`` is a frozen contract — reorders, typos, and accidental
    surface widening must be caught at unit-test time, not at Phase 3 land time."""
    assert set(adapters_pkg.__all__) == EXPECTED_PUBLIC_SURFACE


# -------- AdapterConfidence variants (AC-3, AC-7, AC-12) --------

CONFIDENCE_INSTANCES: list[AdapterConfidence] = [
    Trusted(),
    Degraded(reason="scip_unavailable"),
    Unavailable(reason="tool_missing"),
]


@pytest.mark.parametrize("instance", CONFIDENCE_INSTANCES)
def test_adapter_confidence_variants_construct_and_roundtrip(
    instance: AdapterConfidence,
) -> None:
    """AC-7: round-trip identity through the discriminated union; nested
    concrete-type preservation guards against a regression that drops
    ``Field(discriminator="kind")`` from the ``Annotated[Union, …]`` wrapper."""
    adapter: TypeAdapter[AdapterConfidence] = TypeAdapter(AdapterConfidence)
    encoded = adapter.dump_json(instance)
    decoded = adapter.validate_json(encoded)
    assert decoded == instance
    assert type(decoded) is type(instance)


def test_discriminator_strings_are_exactly_pinned() -> None:
    """AC-3: discriminator strings are a cross-ADR / cross-phase contract."""
    assert Trusted().kind == "trusted"
    assert Degraded(reason="x").kind == "degraded"
    assert Unavailable(reason="x").kind == "unavailable"


@pytest.mark.parametrize(
    "instance,expected_json",
    [
        (Trusted(), {"kind": "trusted"}),
        (
            Degraded(reason="scip_unavailable"),
            {"kind": "degraded", "reason": "scip_unavailable"},
        ),
        (
            Unavailable(reason="tool_missing"),
            {"kind": "unavailable", "reason": "tool_missing"},
        ),
    ],
)
def test_json_shape_pinned(instance: AdapterConfidence, expected_json: dict[str, str]) -> None:
    """AC-12: catches a symmetric ``kind`` → ``tag`` discriminator-field rename
    that the Python-object round-trip in AC-7 tolerates."""
    adapter: TypeAdapter[AdapterConfidence] = TypeAdapter(AdapterConfidence)
    assert adapter.dump_python(instance) == expected_json


def test_adapter_confidence_rejects_unknown_kind() -> None:
    adapter: TypeAdapter[AdapterConfidence] = TypeAdapter(AdapterConfidence)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "what", "reason": "x"})


def test_degraded_and_unavailable_require_reason() -> None:
    with pytest.raises(ValidationError):
        Degraded.model_validate({"kind": "degraded"})
    with pytest.raises(ValidationError):
        Unavailable.model_validate({"kind": "unavailable"})


# -------- extra="forbid" + frozen (AC-10, AC-11) --------


def test_trusted_rejects_reason_field() -> None:
    """AC-11: ``Trusted`` carries the *absence* of degradation."""
    with pytest.raises(ValidationError):
        Trusted.model_validate({"kind": "trusted", "reason": "x"})


def test_degraded_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        Degraded.model_validate({"kind": "degraded", "reason": "x", "extra": "bad"})


def test_unavailable_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        Unavailable.model_validate({"kind": "unavailable", "reason": "x", "extra": "bad"})


@pytest.mark.parametrize("instance", CONFIDENCE_INSTANCES)
def test_adapter_confidence_instances_are_immutable(
    instance: AdapterConfidence,
) -> None:
    """AC-10: ``frozen=True`` is enforced by runtime mutation attempt."""
    with pytest.raises(ValidationError):
        instance.kind = "what"  # type: ignore[assignment]


# -------- Exhaustive match (AC-14) --------


@pytest.mark.parametrize("instance", CONFIDENCE_INSTANCES)
def test_match_is_exhaustive_over_adapter_confidence(
    instance: AdapterConfidence,
) -> None:
    """AC-14: every consumer of ``AdapterConfidence`` MUST pattern-match every
    variant; rehearses the runtime construction path of every arm."""
    label: str
    match instance:
        case Trusted():
            label = "trusted"
        case Degraded(reason=r):
            label = f"degraded:{r}"
        case Unavailable(reason=r):
            label = f"unavailable:{r}"
        case _:
            assert_never(instance)
    assert label  # non-empty — every arm must yield a value


# -------- Occurrence (AC-13) --------


def test_occurrence_is_frozen_dataclass_with_exact_fields() -> None:
    """AC-13: ``Occurrence`` is the only Phase-2-local concrete value type in
    the adapter surface."""
    assert dataclasses.is_dataclass(Occurrence)
    assert Occurrence.__dataclass_params__.frozen is True  # type: ignore[attr-defined]
    assert {f.name for f in dataclasses.fields(Occurrence)} == {"file", "line", "col"}
    inst = Occurrence(file="a.ts", line=1, col=2)
    with pytest.raises(dataclasses.FrozenInstanceError):
        inst.file = "b.ts"  # type: ignore[misc]


def test_occurrence_uses_slots() -> None:
    """AC-13 (optional slots assertion): mmap-friendly for Phase 3 SCIP."""
    inst = Occurrence(file="a.ts", line=1, col=2)
    assert not hasattr(inst, "__dict__")


# -------- Protocol structural conformance (AC-4, AC-5) --------


class _DepGraphStub:
    def consumers(self, pkg: str) -> list[str]:
        return []

    def producers(self, pkg: str) -> list[str]:
        return []

    def confidence(self) -> AdapterConfidence:
        return Trusted()


class _ImportGraphStub:
    def reverse_lookup(self, module: str) -> list[str]:
        return []

    def confidence(self) -> AdapterConfidence:
        return Trusted()


class _ScipStub:
    def refs(self, symbol: str) -> list[Occurrence]:
        return []

    def confidence(self) -> AdapterConfidence:
        return Trusted()


class _TestInventoryStub:
    def tests_exercising(self, symbol: str) -> list[TestId]:
        return []

    def confidence(self) -> AdapterConfidence:
        return Trusted()


# Incomplete stubs — each removes exactly one declared method.


class _IncompleteDepGraph:
    def consumers(self, pkg: str) -> list[str]:
        return []

    def producers(self, pkg: str) -> list[str]:
        return []

    # confidence() removed


class _IncompleteImportGraph:
    def reverse_lookup(self, module: str) -> list[str]:
        return []

    # confidence() removed


class _IncompleteScip:
    def refs(self, symbol: str) -> list[Occurrence]:
        return []

    # confidence() removed


class _IncompleteTestInventory:
    def tests_exercising(self, symbol: str) -> list[TestId]:
        return []

    # confidence() removed


@pytest.mark.parametrize(
    "stub_cls,proto",
    [
        (_DepGraphStub, DepGraphAdapter),
        (_ImportGraphStub, ImportGraphAdapter),
        (_ScipStub, ScipAdapter),
        (_TestInventoryStub, TestInventoryAdapter),
    ],
)
def test_runtime_checkable_accepts_complete_stub(stub_cls: type, proto: type) -> None:
    """AC-4: @runtime_checkable conformance is structural and attribute-based."""
    assert isinstance(stub_cls(), proto)


@pytest.mark.parametrize(
    "stub_cls,proto",
    [
        (_IncompleteDepGraph, DepGraphAdapter),
        (_IncompleteImportGraph, ImportGraphAdapter),
        (_IncompleteScip, ScipAdapter),
        (_IncompleteTestInventory, TestInventoryAdapter),
    ],
)
def test_runtime_checkable_rejects_incomplete_stub(stub_cls: type, proto: type) -> None:
    """AC-5: PEP 544 §runtime_checkable — ``isinstance`` checks attribute
    *presence*, not signatures. A class missing any declared method must
    return False."""
    assert isinstance(stub_cls(), proto) is False


# -------- Zero-implementation invariant (AC-6) --------

ADAPTER_PROTOCOLS: tuple[type, ...] = (
    DepGraphAdapter,
    ImportGraphAdapter,
    ScipAdapter,
    TestInventoryAdapter,
)
ADAPTER_PROTOCOL_NAMES: frozenset[str] = frozenset(proto.__name__ for proto in ADAPTER_PROTOCOLS)


def test_no_phase2_module_implements_adapter_protocol_dynamic() -> None:
    """AC-6 (dynamic arm). Phase 2 ships Protocols only (02-ADR-0007)."""
    offenders: list[str] = []
    for mod_info in pkgutil.walk_packages(codegenie.__path__, prefix="codegenie."):
        if mod_info.name.startswith("codegenie.adapters"):
            continue
        try:
            mod = importlib.import_module(mod_info.name)
        except Exception:
            continue
        for cls_name, cls in inspect.getmembers(mod, inspect.isclass):
            if cls.__module__ != mod_info.name:
                continue
            # Exceptions can't satisfy any Adapter Protocol (none of the
            # required methods are on BaseException). Skipping them also
            # avoids ``@runtime_checkable``-isinstance's PEP-563 side effect
            # of populating ``__annotations__`` on the inspected class —
            # which would otherwise trip the marker-only invariant in
            # ``tests/unit/test_errors.py::test_subclasses_are_markers_only``.
            if isinstance(cls, type) and issubclass(cls, BaseException):
                continue
            try:
                inst = cls()
            except Exception:
                continue
            if any(isinstance(inst, proto) for proto in ADAPTER_PROTOCOLS):
                offenders.append(f"{mod_info.name}.{cls_name}")
    assert offenders == [], (
        f"02-ADR-0007 prohibits adapter implementations in Phase 2; found (dynamic): {offenders}"
    )


def test_no_phase2_module_inherits_adapter_protocol_statically() -> None:
    """AC-6 (static arm). Closes the gap the dynamic walk leaves open."""
    src_root = Path(codegenie.__file__).parent
    adapters_root = src_root / "adapters"
    offenders: list[str] = []
    for py in src_root.rglob("*.py"):
        if py.is_relative_to(adapters_root):
            continue
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                base_name: str | None = None
                if isinstance(base, ast.Name):
                    base_name = base.id
                elif isinstance(base, ast.Attribute):
                    base_name = base.attr
                if base_name in ADAPTER_PROTOCOL_NAMES:
                    offenders.append(f"{py.relative_to(src_root)}::{node.name}")
    assert offenders == [], (
        f"02-ADR-0007 prohibits adapter implementations in Phase 2; found (static): {offenders}"
    )


# -------- Module purity + forbidden patterns (AC-15, AC-16) --------

FORBIDDEN_IMPORTS: frozenset[str] = frozenset(
    {
        "logging",
        "structlog",
        "subprocess",
        "socket",
        "httpx",
        "requests",
        "anthropic",
        "openai",
        "langgraph",
    }
)
FORBIDDEN_CODEGENIE_PREFIXES: tuple[str, ...] = (
    "codegenie.parsers",
    "codegenie.probes",
    "codegenie.exec",
    "codegenie.coordinator",
    "codegenie.output",
)


@pytest.mark.parametrize(
    "mod_file",
    [
        Path(confidence_mod.__file__),
        Path(protocols_mod.__file__),
    ],
)
def test_adapter_modules_are_pure_typing(mod_file: Path) -> None:
    """AC-15: ``confidence.py`` and ``protocols.py`` are pure typing."""
    tree = ast.parse(mod_file.read_text())
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    for name in imported:
        assert name not in FORBIDDEN_IMPORTS, f"{mod_file.name} imports forbidden module {name!r}"
        for prefix in FORBIDDEN_CODEGENIE_PREFIXES:
            assert not name.startswith(prefix), (
                f"{mod_file.name} imports forbidden {prefix}-tree module {name!r}"
            )


@pytest.mark.parametrize(
    "mod_file",
    [
        Path(confidence_mod.__file__),
        Path(protocols_mod.__file__),
    ],
)
def test_adapter_modules_have_no_model_construct(mod_file: Path) -> None:
    """AC-16: ``model_construct`` bypasses Pydantic validation; banned under
    the typed-sum packages."""
    tree = ast.parse(mod_file.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "model_construct":
            pytest.fail(
                f"{mod_file.name}:{node.lineno}: model_construct is forbidden "
                f"under src/codegenie/adapters/** (02-arch §Anti-patterns row 12)"
            )


# -------- TestId NewType identity (sanity) --------


def test_test_id_is_a_newtype_alias_of_str() -> None:
    """``TestId`` is structurally a ``str`` — a sanity guard so a future
    contributor who tries to promote it to a Pydantic model surfaces here."""
    tid = TestId("test_x")
    assert isinstance(tid, str)
    assert tid == "test_x"
