"""Phase 7 S2-01 — `_REGISTRY` + `@register_provenance_adapter` decorator tests.

Each test pins one acceptance criterion from the story (see header comments).
The autouse ``provenance_registry_reset`` fixture in ``conftest.py`` ensures
``_REGISTRY`` is empty at the start of every test.

ADRs honored:
- Phase 7 ADR-0007 — registry stores classes, not instances; duplicate key
  raises ``RegistryError`` at decoration time; no ``isinstance(cls(), ...)``
  runtime guard.
- Phase 7 ADR-0006 — registry is a plain dict; dispatch ordering is NOT a
  registry concern.
"""

from __future__ import annotations

from typing import Any

import pytest

from codegenie.primitives.vuln_provenance import (
    Ecosystem,
    Layer,
    register_provenance_adapter,
)
from codegenie.primitives.vuln_provenance import registry as _registry_mod
from codegenie.primitives.vuln_provenance.errors import RegistryError


def test_duplicate_registration_raises_registry_error() -> None:
    """AC-6 (RED) — duplicate `(Layer, Ecosystem)` raises `RegistryError` at
    decoration time. Both colliding ``module.qualname`` strings appear in the
    message; the typed ``.key`` payload equals the colliding pair.

    Plugin loader (S8-03) reads ``exc.key`` to print a structured diagnostic;
    operators grep the message for ``module.qualname`` to locate both sites.
    """

    @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)
    class _FirstNpmAdapter:
        def attribute(self, *a: Any, **kw: Any) -> Any: ...
        def confidence(self) -> Any: ...

    with pytest.raises(RegistryError) as exc_info:

        @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)
        class _DuplicateNpmAdapter:
            def attribute(self, *a: Any, **kw: Any) -> Any: ...
            def confidence(self) -> Any: ...

    assert exc_info.value.key == (Layer.APP, Ecosystem.NPM)
    msg = str(exc_info.value)
    assert "_FirstNpmAdapter" in msg
    assert "_DuplicateNpmAdapter" in msg


def test_layer_enum_declaration_order() -> None:
    """AC-1 — `Layer` has exactly three members in
    ``APP → BASE_IMAGE → RUNTIME`` order. Declaration order is load-bearing
    because S2-03's ``_ADAPTER_DISPATCH_ORDER`` iterates in this order."""
    assert tuple(Layer) == (Layer.APP, Layer.BASE_IMAGE, Layer.RUNTIME)
    assert Layer.APP.value == "app"
    assert Layer.BASE_IMAGE.value == "base_image"
    assert Layer.RUNTIME.value == "runtime"


def test_ecosystem_enum_declaration_order() -> None:
    """AC-2 — `Ecosystem` has exactly six members in declaration order.
    S2-03 iterates intra-layer adapters in this order. Adding a value is an
    ADR amendment, not a silent change."""
    assert tuple(Ecosystem) == (
        Ecosystem.NPM,
        Ecosystem.YARN_BERRY,
        Ecosystem.PNPM,
        Ecosystem.APK,
        Ecosystem.DPKG,
        Ecosystem.RPM,
    )
    assert Ecosystem.NPM.value == "npm"
    assert Ecosystem.YARN_BERRY.value == "yarn-berry"
    assert Ecosystem.PNPM.value == "pnpm"
    assert Ecosystem.APK.value == "apk"
    assert Ecosystem.DPKG.value == "dpkg"
    assert Ecosystem.RPM.value == "rpm"


def test_registry_is_empty_at_test_start() -> None:
    """AC-3 + AC-9 — ``_REGISTRY`` starts empty thanks to the autouse fixture."""
    assert _registry_mod._REGISTRY == {}


def test_registry_stores_the_class_not_an_instance() -> None:
    """AC-4 — BP-3 regression check. The registry value IS the class itself
    (identity), not an instance produced by calling ``cls()`` at decoration
    time. S2-02's ``AdapterFactory`` owns instance construction."""

    @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)
    class _Adapter:
        def attribute(self, *a: Any, **kw: Any) -> Any: ...
        def confidence(self) -> Any: ...

    assert _registry_mod._REGISTRY[(Layer.APP, Ecosystem.NPM)] is _Adapter


def test_decorator_returns_class_unchanged() -> None:
    """AC-5 — identity return. Catches ``return None`` / ``return wrapper``
    mutants where the decorator silently swaps the user's class."""

    class _Adapter:
        def attribute(self, *a: Any, **kw: Any) -> Any: ...
        def confidence(self) -> Any: ...

    decorated = register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.APK)(
        _Adapter
    )
    assert decorated is _Adapter


def test_no_instance_construction_at_decoration_time() -> None:
    """AC-7 — BP-3 canary. A class whose ``__init__`` raises must still
    register successfully. If a future PR introduces ``_REGISTRY[key] = cls()``
    this test fails loud — every Phase 8+ adapter relies on lazy construction."""

    @register_provenance_adapter(layer=Layer.RUNTIME, ecosystem=Ecosystem.RPM)
    class _AdapterWithExplodingInit:
        def __init__(self) -> None:
            raise RuntimeError("decorator must not construct instances")

        def attribute(self, *a: Any, **kw: Any) -> Any: ...
        def confidence(self) -> Any: ...

    assert _registry_mod._REGISTRY[(Layer.RUNTIME, Ecosystem.RPM)] is _AdapterWithExplodingInit


def test_no_isinstance_runtime_contract_guard() -> None:
    """AC-8 — per ADR-0007 §Tradeoffs row 4, the decorator does NOT check the
    adapter's method signatures at decoration time (``Protocol.__runtime_checkable__``
    only verifies method NAMES, which would give false safety). ``mypy --strict``
    is the CI gate. A wrong-signature class registers successfully."""

    @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.YARN_BERRY)
    class _WrongSignatureAdapter:
        def attribute(self) -> None: ...  # wrong arity, on purpose
        def confidence(self, extra: int) -> None: ...  # wrong arity, on purpose

    assert _registry_mod._REGISTRY[(Layer.APP, Ecosystem.YARN_BERRY)] is _WrongSignatureAdapter


def test_distinct_keys_coexist() -> None:
    """AC-3 + AC-4 — two adapters with different ``(layer, ecosystem)`` keys
    coexist; the registry stores both."""

    @register_provenance_adapter(layer=Layer.APP, ecosystem=Ecosystem.NPM)
    class _A:
        def attribute(self, *a: Any, **kw: Any) -> Any: ...
        def confidence(self) -> Any: ...

    @register_provenance_adapter(layer=Layer.BASE_IMAGE, ecosystem=Ecosystem.APK)
    class _B:
        def attribute(self, *a: Any, **kw: Any) -> Any: ...
        def confidence(self) -> Any: ...

    assert _registry_mod._REGISTRY[(Layer.APP, Ecosystem.NPM)] is _A
    assert _registry_mod._REGISTRY[(Layer.BASE_IMAGE, Ecosystem.APK)] is _B
    assert len(_registry_mod._REGISTRY) == 2


def test_isolation_fixture_clears_between_tests() -> None:
    """AC-9 (paired with ``test_registry_stores_the_class_not_an_instance``).

    Even though the prior test in this file registered an adapter, this test
    sees an empty registry — the autouse ``provenance_registry_reset`` fixture
    snapshots/clears/restores ``_REGISTRY`` per test. Tests in this file are
    collected in source order; this test runs AFTER the registration tests
    above, so a real isolation bug would surface here as a non-empty dict."""
    assert _registry_mod._REGISTRY == {}


def test_public_surface_reexports_layer_ecosystem_decorator() -> None:
    """AC-10 — package ``__init__`` re-exports ``Layer``, ``Ecosystem``, and
    ``register_provenance_adapter``. ``_REGISTRY`` itself stays module-private."""
    from codegenie.primitives import vuln_provenance as _vp

    assert _vp.Layer is Layer
    assert _vp.Ecosystem is Ecosystem
    assert _vp.register_provenance_adapter is register_provenance_adapter
    assert "_REGISTRY" not in _vp.__all__


def test_registry_error_duplicate_classmethod_payload() -> None:
    """AC-6 (payload contract) — ``RegistryError.duplicate(...)`` produces an
    exception with ``.key`` set to the colliding ``ProvenanceAdapterId`` and a
    message containing both ``existing_qualname`` and ``duplicate_qualname``."""
    err = RegistryError.duplicate(
        key=(Layer.APP, Ecosystem.NPM),
        existing_qualname="pkg.mod.First",
        duplicate_qualname="pkg.mod.Second",
    )
    assert isinstance(err, RegistryError)
    assert err.key == (Layer.APP, Ecosystem.NPM)
    msg = str(err)
    assert "pkg.mod.First" in msg
    assert "pkg.mod.Second" in msg
