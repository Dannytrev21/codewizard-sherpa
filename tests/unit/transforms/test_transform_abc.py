"""Unit tests for ``codegenie.transforms.transform.Transform`` — S1-04 AC-8 suite.

The Transform ABC pattern mirrors ``src/codegenie/probes/base.py``: class-level
type annotations on the abstract class, *not* ``@property @abstractmethod``.
Subclasses declare each attribute as a class variable (or per-instance) and
the ``isinstance(t, Transform)`` check Phase 5 relies on works without any
``runtime_checkable`` overhead.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from codegenie.transforms import (
    SandboxedPath,
    Transform,
    TransformProvenance,
)
from codegenie.types.identifiers import (
    EventId,
    PluginId,
    RecipeId,
    TransformId,
    TransformKind,
)

_ULID_A: str = "01HXX00000000000000000000Z"


def _provenance() -> TransformProvenance:
    return TransformProvenance(
        plugin_id=PluginId("vulnerability-remediation--node--npm"),
        plugin_version="1.0.0",
        recipe_id=RecipeId("npm-lockfile-pin"),
        recipe_version="1.0.0",
        transform_kind=TransformKind("lockfile_pin"),
        applied_at=datetime.now(UTC),
        capability_use_id=EventId(_ULID_A),
    )


# ---------------------------------------------------------------------------
# AC-8a — bare ABC cannot be instantiated
# ---------------------------------------------------------------------------


def test_bare_transform_instantiation_raises_type_error() -> None:
    """``Transform()`` directly raises ``TypeError`` because the ABC must be
    subclassed with at least the four contract attributes defined.

    Pattern precedent: ``src/codegenie/probes/base.py``'s ``Probe(ABC)`` uses
    ``@abstractmethod`` on ``run`` to drive the same instantiation guard.
    ``Transform`` mirrors that — the abstract surface lives in ``run``-style
    contract methods or, in our case, the class itself declared ``ABC``."""
    with pytest.raises(TypeError):
        Transform()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# AC-8b — minimal subclass instantiates and isinstance check works
# ---------------------------------------------------------------------------


def test_subclass_with_all_attributes_instantiates() -> None:
    class FakeTransform(Transform):
        transform_id: TransformId = TransformId("a" * 64)
        diff_bytes: bytes = b""
        files_changed: tuple[SandboxedPath, ...] = ()
        provenance: TransformProvenance = _provenance()

    t = FakeTransform()
    assert isinstance(t, Transform)  # AC-8d
    assert t.transform_id == TransformId("a" * 64)
    assert t.diff_bytes == b""
    assert t.files_changed == ()
    assert t.provenance.plugin_id == PluginId("vulnerability-remediation--node--npm")


# ---------------------------------------------------------------------------
# AC-8c — missing-attribute subclass fails attribute access at runtime
# ---------------------------------------------------------------------------


def test_subclass_missing_attribute_fails_at_attribute_access() -> None:
    """Mirrors the ``Probe(ABC)`` precedent: class-level annotations don't
    enforce attribute presence at instantiation (only ``@abstractmethod``
    does); a malformed subclass that skips ``provenance`` *will* instantiate
    but every ``isinstance``-using consumer raises ``AttributeError`` when it
    reaches for the missing field. That failure mode is what we lock in."""

    class IncompleteTransform(Transform):
        transform_id: TransformId = TransformId("b" * 64)
        diff_bytes: bytes = b""
        files_changed: tuple[SandboxedPath, ...] = ()
        # provenance intentionally omitted.

    t = IncompleteTransform()  # instantiation does NOT raise (precedent: Probe)
    assert isinstance(t, Transform)
    with pytest.raises(AttributeError):
        _ = t.provenance


def test_phase5_isinstance_check_works_through_arbitrary_subclass() -> None:
    """Phase 5's ``GateContext.transform_output: Transform`` is checked via
    ``isinstance``. Pin that this works on the concrete subclass shape that
    S5-02 / S5-03 will mint."""

    class FakeTransform(Transform):
        transform_id: TransformId = TransformId("c" * 64)
        diff_bytes: bytes = b"hello"
        files_changed: tuple[SandboxedPath, ...] = ()
        provenance: TransformProvenance = _provenance()

    t: object = FakeTransform()
    assert isinstance(t, Transform)
