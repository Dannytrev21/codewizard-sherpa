"""Phase 7 S2-02 — `AdapterFactory` Protocol + `DefaultAdapterFactory` tests.

Each test pins one acceptance criterion (see header comments). The factory
inspects a registered adapter class's ``__init__`` and injects ONLY the
closed dependency-injection kwarg vocabulary
``{sbom_reader, logger, image_manifest_cache}`` (Phase 7 ADR-0007 §Decision;
§Tradeoffs row 1 — growing the set is an ADR amendment, never a silent edit).

Fixture adapter classes carry ``attribute`` / ``confidence`` stubs typed
``-> Any`` so they structurally satisfy ``type[VulnProvenanceAdapter]`` at
the factory call site (the ``Any`` return is what makes ``mypy --strict``
admit them — mirrors ``test_registry.py``). They record what their
``__init__`` received into a closure dict rather than exposing attributes,
so the assertions never poke a ``VulnProvenanceAdapter``-typed return.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from codegenie.primitives.vuln_provenance import (
    AdapterFactory,
    DefaultAdapterFactory,
    default_adapter_factory,
)
from codegenie.primitives.vuln_provenance import factory as _factory_mod


def test_default_factory_passes_only_declared_di_kwargs() -> None:
    """AC-10 (RED) + AC-4 — the factory inspects ``cls.__init__`` and passes
    only the DI kwargs the adapter declares. An adapter declaring
    ``sbom_reader`` + ``logger`` gets exactly those two — no more, no less."""
    received: dict[str, object] = {}
    reader = object()
    logger = object()

    class _AdapterDeclaringTwo:
        def __init__(self, *, sbom_reader: object, logger: object) -> None:
            received["sbom_reader"] = sbom_reader
            received["logger"] = logger

        def attribute(self, *a: Any, **kw: Any) -> Any: ...
        def confidence(self) -> Any: ...

    factory = DefaultAdapterFactory(sbom_reader=reader, logger=logger)
    factory(_AdapterDeclaringTwo)

    assert received["sbom_reader"] is reader
    assert received["logger"] is logger
    # No extra kwargs smuggled in (catches a "passes everything" mutant).
    assert set(received) == {"sbom_reader", "logger"}


def test_di_kwargs_is_exact_closed_vocabulary() -> None:
    """AC-2 — ``_DI_KWARGS`` is the exact closed set (exact-set equality
    catches both additions and removals). Growing it is an ADR-0007
    amendment per §Tradeoffs row 1."""
    assert _factory_mod._DI_KWARGS == frozenset({"sbom_reader", "logger", "image_manifest_cache"})


def test_adapter_factory_protocol_surface() -> None:
    """AC-1 — ``AdapterFactory`` Protocol has exactly ``__call__`` and no
    other public attribute; ``__call__`` is a plain function on the body."""
    public = {n for n in dir(AdapterFactory) if not n.startswith("_")}
    assert public == set()
    assert inspect.isfunction(AdapterFactory.__call__)


def test_factory_injects_all_three_closed_vocab_kwargs() -> None:
    """AC-3 — ``DefaultAdapterFactory`` accepts the full closed vocabulary at
    construction; each of the three deps flows through to an adapter that
    declares all three. Verifies the construction surface behaviorally."""
    received: dict[str, object] = {}
    reader = object()
    logger = object()
    cache = object()

    class _AdapterDeclaringAllThree:
        def __init__(
            self,
            *,
            sbom_reader: object,
            logger: object,
            image_manifest_cache: object,
        ) -> None:
            received["sbom_reader"] = sbom_reader
            received["logger"] = logger
            received["image_manifest_cache"] = image_manifest_cache

        def attribute(self, *a: Any, **kw: Any) -> Any: ...
        def confidence(self) -> Any: ...

    factory = DefaultAdapterFactory(sbom_reader=reader, logger=logger, image_manifest_cache=cache)
    factory(_AdapterDeclaringAllThree)

    assert received["sbom_reader"] is reader
    assert received["logger"] is logger
    assert received["image_manifest_cache"] is cache


def test_adapter_with_no_kwargs_constructed_cleanly() -> None:
    """AC-5 — a bare ``__init__(self)`` adapter is constructed with ``cls()``
    and NO kwargs. Catches a "passes everything always" mutant, which would
    raise ``TypeError`` against a no-arg constructor."""
    constructed: list[bool] = []

    class _NoKwargAdapter:
        def __init__(self) -> None:
            constructed.append(True)

        def attribute(self, *a: Any, **kw: Any) -> Any: ...
        def confidence(self) -> Any: ...

    DefaultAdapterFactory()(_NoKwargAdapter)
    assert constructed == [True]


def test_adapter_declaring_unknown_kwarg_is_not_passed_it() -> None:
    """AC-6 — an adapter declaring a parameter outside ``_DI_KWARGS`` is
    NEVER handed that kwarg by the factory; the adapter's own default
    applies. This is the closed-vocabulary discipline's load-bearing case."""
    received: dict[str, object] = {}
    sentinel = object()

    class _AdapterWithUnknown:
        def __init__(self, *, sbom_reader: object, unknown_kwarg: object = "default") -> None:
            received["sbom_reader"] = sbom_reader
            received["unknown_kwarg"] = unknown_kwarg

        def attribute(self, *a: Any, **kw: Any) -> Any: ...
        def confidence(self) -> Any: ...

    DefaultAdapterFactory(sbom_reader=sentinel)(_AdapterWithUnknown)

    assert received["sbom_reader"] is sentinel
    # The adapter's declared default — proof the factory did NOT pass it.
    assert received["unknown_kwarg"] == "default"


def test_default_adapter_factory_module_singleton_works_for_no_kwarg_adapters() -> None:
    """AC-7 — the module-level ``default_adapter_factory`` (all-``None`` DI)
    constructs a dependency-free adapter without error."""
    constructed: list[bool] = []

    class _NoKwargAdapter:
        def __init__(self) -> None:
            constructed.append(True)

        def attribute(self, *a: Any, **kw: Any) -> Any: ...
        def confidence(self) -> Any: ...

    default_adapter_factory(_NoKwargAdapter)
    assert constructed == [True]


def test_default_adapter_factory_singleton_passes_none_to_required_dep() -> None:
    """AC-7 — the all-``None`` singleton passes ``None`` for declared DI
    kwargs; an adapter that requires a real dependency surfaces a clear
    error. Production code MUST inject a factory with non-``None`` deps."""

    class _RequiresSbomReader:
        def __init__(self, *, sbom_reader: Any) -> None:
            if sbom_reader is None:
                raise TypeError("sbom_reader is required and must not be None")
            self._sbom_reader = sbom_reader

        def attribute(self, *a: Any, **kw: Any) -> Any: ...
        def confidence(self) -> Any: ...

    with pytest.raises(TypeError, match="sbom_reader is required"):
        default_adapter_factory(_RequiresSbomReader)


def test_runtime_checkable_protocol_smoke() -> None:
    """AC-8 — ``AdapterFactory`` is ``@runtime_checkable``; S2-04's
    ``adapter_factory: AdapterFactory | None`` parameter relies on the
    ``isinstance`` guard for fixture substitution."""
    assert isinstance(DefaultAdapterFactory(), AdapterFactory) is True
    assert isinstance(object(), AdapterFactory) is False


def test_substitute_factory_satisfies_protocol_via_duck_typing() -> None:
    """AC-9 — a deterministic test factory satisfies ``AdapterFactory`` by
    shape alone. This is the contract S2-04's ``adapter_factory`` parameter
    relies on for test isolation."""

    class _FixtureFactory:
        def __call__(self, cls: type[Any], /) -> Any:
            return cls()

    assert isinstance(_FixtureFactory(), AdapterFactory) is True
