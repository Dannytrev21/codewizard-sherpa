"""Phase 7 S1-04 — `VulnProvenanceAdapter` Protocol shape + `ProvenanceError`
hierarchy pin tests.

Structural fence that keeps S2+ adapter stories from silently growing the
Protocol kernel. The TDD red comes from the missing ``protocols.py`` /
``errors.py`` modules; the green is the four-class hierarchy + the
verbatim two-method Protocol shape from
``docs/phases/07-migration-task-class/phase-arch-design.md §Component design``.

ACs pinned here:

- AC-1 — `attribute` / `confidence` signature shape; annotation completeness.
- AC-2 — Protocol method set is **exactly** ``{"attribute", "confidence"}``
  (no ``cost_band``, no ``applies_when`` — critic Perf-5 + Phase 7 ADR-0007).
- AC-3 — ``@runtime_checkable`` admits a duck-typed conformer and rejects
  **both** the missing-`confidence` AND missing-`attribute` stubs
  (bidirectional structural-contract pin).
- AC-4 / AC-5 — `ProvenanceError` is a `CodegenieError` subclass; both
  `RegistryError` and `AdapterError` are `ProvenanceError` siblings
  (mutually disjoint — not parent/child); ``pytest.raises(ProvenanceError)``
  catches both; a plain `Exception` is not caught by `ProvenanceError`.
- AC-6 — `sbom` annotation is the bare-name forward reference today;
  `# TODO(S1-05)` guards the eventual tightening.
- AC-7 — the four new names re-export off
  ``codegenie.primitives.vuln_provenance``.
- AC-10 — Protocol is structurally a `typing.Protocol`, NOT an `abc.ABC`.
- AC-11 — Each error class is a marker-only body (docstring only — no
  ``__init__``, no class-level attributes, no methods).
"""

from __future__ import annotations

import abc
import ast
import inspect
from pathlib import Path
from typing import Protocol, get_type_hints

import pytest

from codegenie.errors import CodegenieError
from codegenie.primitives.vuln_provenance import (
    AdapterConfidence,
    AdapterError,
    ProvenanceError,
    RegistryError,
    VulnProvenanceAdapter,
)

# --- AC-2 — Protocol method set is exactly {attribute, confidence} ----------

PROTOCOL_FILE = Path("src/codegenie/primitives/vuln_provenance/protocols.py")
ERRORS_FILE = Path("src/codegenie/primitives/vuln_provenance/errors.py")


def _protocol_method_names() -> set[str]:
    tree = ast.parse(PROTOCOL_FILE.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "VulnProvenanceAdapter":
            return {
                child.name
                for child in node.body
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
            }
    pytest.fail("VulnProvenanceAdapter class not found in protocols.py")


def test_protocol_method_set_is_exact() -> None:
    assert _protocol_method_names() == {"attribute", "confidence"}, (
        "VulnProvenanceAdapter must not gain cost_band, applies_when, or any "
        "other method (critic Perf-5; Phase 7 ADR-0007)."
    )


# --- AC-3 — @runtime_checkable round-trip (bidirectional rejection) ---------


class _GoodAdapter:
    def attribute(self, cve_id, package_id, image_ref, sbom):  # type: ignore[no-untyped-def]
        ...

    def confidence(self):  # type: ignore[no-untyped-def]
        ...


class _BadAdapterMissingConfidence:
    def attribute(self, cve_id, package_id, image_ref, sbom):  # type: ignore[no-untyped-def]
        ...


class _BadAdapterMissingAttribute:
    def confidence(self):  # type: ignore[no-untyped-def]
        ...


def test_runtime_checkable_admits_good_adapter() -> None:
    assert isinstance(_GoodAdapter(), VulnProvenanceAdapter)


def test_runtime_checkable_rejects_missing_confidence() -> None:
    assert not isinstance(_BadAdapterMissingConfidence(), VulnProvenanceAdapter)


def test_runtime_checkable_rejects_missing_attribute() -> None:
    """AC-3 bidirectional pin — drop ``attribute`` instead of ``confidence``
    and isinstance must still return False. A method-renamer mutation that
    drops one but keeps the other is caught by either negative test."""
    assert not isinstance(_BadAdapterMissingAttribute(), VulnProvenanceAdapter)


# --- AC-4 / AC-5 — Error hierarchy (siblings, not chain) --------------------


def test_error_hierarchy_is_subclass_of_codegenie_error() -> None:
    assert issubclass(ProvenanceError, CodegenieError)
    assert issubclass(RegistryError, ProvenanceError)
    assert issubclass(AdapterError, ProvenanceError)


def test_provenance_error_catches_subclasses() -> None:
    with pytest.raises(ProvenanceError):
        raise RegistryError("dup")
    with pytest.raises(ProvenanceError):
        raise AdapterError("kaboom")
    # And the narrow-catch idiom S2-04 may use for adapter-only failures.
    with pytest.raises(AdapterError):
        raise AdapterError("kaboom")


def test_adapter_and_registry_errors_are_siblings_not_chain() -> None:
    """AC-4 sub-clause — typed-error sum-type discipline. Refactoring one
    into a subclass of the other would silently change S2-04's catch-arm
    semantics (one of them would suddenly satisfy ``except SiblingError``)."""
    assert AdapterError is not RegistryError
    assert not issubclass(AdapterError, RegistryError)
    assert not issubclass(RegistryError, AdapterError)


def test_provenance_error_does_not_catch_plain_exception() -> None:
    """AC-5 — ``ProvenanceError`` is not just ``Exception``. Assert via
    ``excinfo.value`` identity rather than catch-then-re-raise (the
    catch-then-re-raise idiom passes vacuously when both arms behave the
    same — Rule 9)."""
    with pytest.raises(Exception) as excinfo:  # noqa: PT011, BLE001 — pinning identity, not type.
        raise Exception("plain")
    assert not isinstance(excinfo.value, ProvenanceError)


# --- AC-1 — method signature shape + annotation completeness ----------------


def test_attribute_signature() -> None:
    sig = inspect.signature(VulnProvenanceAdapter.attribute)
    params = list(sig.parameters.keys())
    assert params == ["self", "cve_id", "package_id", "image_ref", "sbom"]


def test_confidence_signature() -> None:
    sig = inspect.signature(VulnProvenanceAdapter.confidence)
    params = list(sig.parameters.keys())
    assert params == ["self"]


def test_confidence_returns_adapter_confidence() -> None:
    hints = get_type_hints(VulnProvenanceAdapter.confidence)
    assert hints.get("return") is AdapterConfidence


def test_attribute_is_fully_annotated() -> None:
    """AC-1 sub-clause — every parameter (self excepted) AND the return
    type carries an annotation. A stripped-annotation implementation
    (``def attribute(self, cve_id, package_id, image_ref, sbom):``) would
    pass the signature-name test but defeat the Protocol's purpose."""
    raw = inspect.get_annotations(VulnProvenanceAdapter.attribute, eval_str=False)
    assert set(raw.keys()) == {"cve_id", "package_id", "image_ref", "sbom", "return"}
    # No annotation is allowed to be empty / None / missing.
    assert all(v is not None and str(v).strip() != "" for v in raw.values())


def test_confidence_is_fully_annotated() -> None:
    raw = inspect.get_annotations(VulnProvenanceAdapter.confidence, eval_str=False)
    assert set(raw.keys()) == {"return"}


# --- AC-6 — `SyftSbom` forward reference today; resolves after S1-05 --------


def test_attribute_sbom_param_is_forward_reference_today() -> None:
    """The story spec keeps ``sbom`` as a bare-name forward reference until
    S1-05 lands the `SyftSbom` Pydantic model.

    Today, with ``from __future__ import annotations`` and the
    ``TYPE_CHECKING``-guarded placeholder in ``protocols.py``, the raw
    annotation is the unevaluated string ``"SyftSbom"``. Once S1-05 ships,
    ``get_type_hints(...)`` will resolve it.

    The ``TODO(S1-05)`` marker below is the planned-tightening guard — when
    S1-05 lands, flip this to assert the resolved class.
    """
    raw = inspect.get_annotations(VulnProvenanceAdapter.attribute, eval_str=False)
    # TODO(S1-05): once SyftSbom is importable, switch to
    #   ``get_type_hints(VulnProvenanceAdapter.attribute)["sbom"] is SyftSbom``.
    assert raw["sbom"] == "SyftSbom", (
        "sbom annotation must remain the bare-name forward reference 'SyftSbom' "
        "until S1-05 lands the model. Drift is a Phase 7 ADR-0004 amendment."
    )


# --- AC-10 — Protocol-not-ABC structural pin --------------------------------


def test_protocol_is_a_typing_protocol_not_abc() -> None:
    """Phase 7 ADR-0007 — adapters implement the contract by shape; the
    kernel never inherits ABC. If a refactor turns the Protocol into an
    ABC subclass, every adapter would need ``class X(VulnProvenanceAdapter)``
    inheritance, which the arch explicitly rejects."""
    assert Protocol in VulnProvenanceAdapter.__mro__
    assert abc.ABC not in VulnProvenanceAdapter.__mro__


# --- AC-11 — errors-as-markers convention (no __init__, no attrs, no methods)


def _error_class_body_kinds(name: str) -> list[str]:
    """Return the AST node-kind labels of every top-level body element of
    the class ``name`` in ``errors.py``. The marker-only convention permits
    only a single docstring (``Expr(Constant(str))``).
    """
    tree = ast.parse(ERRORS_FILE.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            kinds: list[str] = []
            for child in node.body:
                if (
                    isinstance(child, ast.Expr)
                    and isinstance(child.value, ast.Constant)
                    and isinstance(child.value.value, str)
                ):
                    kinds.append("docstring")
                else:
                    kinds.append(type(child).__name__)
            return kinds
    pytest.fail(f"Class {name!r} not found in errors.py")


@pytest.mark.parametrize("klass_name", ["ProvenanceError", "RegistryError", "AdapterError"])
def test_error_class_is_markers_only(klass_name: str) -> None:
    """AC-11 — mirrors ``src/codegenie/errors.py`` "Subclasses carry no
    ``__init__``, no ``__str__``, no class attributes — they are markers
    only." A single docstring body is the only admitted shape."""
    body_kinds = _error_class_body_kinds(klass_name)
    assert body_kinds == ["docstring"], (
        f"{klass_name} must be markers-only (docstring body only); got "
        f"{body_kinds}. Adding __init__ / __str__ / attributes is a Phase 7 "
        "ADR-0004 amendment."
    )
