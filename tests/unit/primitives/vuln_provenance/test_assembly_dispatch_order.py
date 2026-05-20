"""Phase 7 S2-03 — `_ADAPTER_DISPATCH_ORDER` tuple + `iter_adapters_for_layer_set`.

Pins the dispatch policy (Phase 7 ADR-0006): dispatch order is explicit
`Final`-tuple data, and intra-layer iteration is `Ecosystem`-enum-declaration
sorted — NOT `dict.items()` registration order (BP-1 closure).

The load-bearing test is
`test_intra_layer_iteration_is_ecosystem_sorted_not_registration_sorted`:
it registers adapters in reversed declaration order and asserts the helper
re-sorts them. S2-05's Hypothesis property test locks this end-to-end across
50 permutations; this module locks it at the helper level.
"""

from __future__ import annotations

from codegenie.primitives.vuln_provenance import assembly as _assembly_mod
from codegenie.primitives.vuln_provenance.assembly import iter_adapters_for_layer_set
from codegenie.primitives.vuln_provenance.registry import Ecosystem, Layer


def test_intra_layer_iteration_is_ecosystem_sorted_not_registration_sorted() -> None:
    """ADR-0006 §Consequences: 'Within-layer iteration is sorted(adapters_for_layer,
    key=lambda a: a.ecosystem) — explicit, by Ecosystem enum value.'
    BP-1 closure: registration order is NOT load-bearing."""

    class _DpkgAdapter: ...

    class _ApkAdapter: ...

    # Register DPKG (index 4 in Ecosystem) BEFORE APK (index 3 in Ecosystem)
    # — registration order is reversed from declaration order.
    registry = {
        (Layer.BASE_IMAGE, Ecosystem.DPKG): _DpkgAdapter,
        (Layer.BASE_IMAGE, Ecosystem.APK): _ApkAdapter,
    }

    yielded = list(iter_adapters_for_layer_set((Layer.BASE_IMAGE,), registry))
    yielded_eco = [key[1] for key, _ in yielded]

    # APK comes first because Ecosystem.APK is declared before Ecosystem.DPKG.
    assert yielded_eco == [Ecosystem.APK, Ecosystem.DPKG]


def test_dispatch_order_tuple_shape_and_declaration_order() -> None:
    """AC-1 + AC-2 — exact tuple equality + tuple-not-list shape."""
    assert _assembly_mod._ADAPTER_DISPATCH_ORDER == (
        (Layer.APP,),
        (Layer.BASE_IMAGE,),
        (Layer.RUNTIME,),
    )
    assert isinstance(_assembly_mod._ADAPTER_DISPATCH_ORDER, tuple)
    for layer_set in _assembly_mod._ADAPTER_DISPATCH_ORDER:
        assert isinstance(layer_set, tuple)


def test_iter_filters_by_layer() -> None:
    """AC-3 — yields only matching-layer entries (catches 'yields everything' mutant)."""

    class _Npm: ...

    class _Apk: ...

    class _Dpkg: ...

    registry = {
        (Layer.APP, Ecosystem.NPM): _Npm,
        (Layer.BASE_IMAGE, Ecosystem.APK): _Apk,
        (Layer.BASE_IMAGE, Ecosystem.DPKG): _Dpkg,
    }
    app_only = list(iter_adapters_for_layer_set((Layer.APP,), registry))
    assert [key[0] for key, _ in app_only] == [Layer.APP]
    assert [cls for _, cls in app_only] == [_Npm]

    base_only = list(iter_adapters_for_layer_set((Layer.BASE_IMAGE,), registry))
    assert {key[1] for key, _ in base_only} == {Ecosystem.APK, Ecosystem.DPKG}


def test_empty_runtime_layer_yields_nothing() -> None:
    """AC-5 — RUNTIME reserved slot smoke; Phase 7 ships no runtime adapter."""

    class _Npm: ...

    registry = {(Layer.APP, Ecosystem.NPM): _Npm}
    yielded = list(iter_adapters_for_layer_set((Layer.RUNTIME,), registry))
    assert yielded == []


def test_multi_layer_layer_set_preserves_layer_set_tuple_order() -> None:
    """AC-6 — future-proof multi-element layer-set; outer order is the layer_set tuple."""

    class _Npm: ...

    class _Apk: ...

    class _Dpkg: ...

    registry = {
        (Layer.APP, Ecosystem.NPM): _Npm,
        (Layer.BASE_IMAGE, Ecosystem.APK): _Apk,
        (Layer.BASE_IMAGE, Ecosystem.DPKG): _Dpkg,
    }
    yielded = list(iter_adapters_for_layer_set((Layer.APP, Layer.BASE_IMAGE), registry))
    keys = [key for key, _ in yielded]
    assert keys == [
        (Layer.APP, Ecosystem.NPM),
        (Layer.BASE_IMAGE, Ecosystem.APK),
        (Layer.BASE_IMAGE, Ecosystem.DPKG),
    ]


def test_iter_returns_classes_not_instances() -> None:
    """ADR-0007 cross-check: the helper yields type[VulnProvenanceAdapter], not instances."""

    class _Npm: ...

    registry = {(Layer.APP, Ecosystem.NPM): _Npm}
    yielded = list(iter_adapters_for_layer_set((Layer.APP,), registry))
    _, cls = yielded[0]
    assert cls is _Npm  # identity — it's the CLASS
    assert isinstance(cls, type)  # confirm class-not-instance


def test_iter_adapters_for_layer_set_is_reexported_from_package() -> None:
    """AC — `iter_adapters_for_layer_set` is re-exported from the package init
    so S2-04 can import it from `codegenie.primitives.vuln_provenance`."""
    import codegenie.primitives.vuln_provenance as pkg

    assert pkg.iter_adapters_for_layer_set is iter_adapters_for_layer_set
    assert "iter_adapters_for_layer_set" in pkg.__all__
