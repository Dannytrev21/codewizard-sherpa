"""Phase 7 S2-03 + S2-04 — `_ADAPTER_DISPATCH_ORDER` `Final` tuple, the
`Ecosystem`-sorted intra-layer iteration helper `iter_adapters_for_layer_set`,
and the `assemble_provenance(...)` composition free function.

`assemble_provenance` (S2-04) is the header function of the `vuln.provenance`
primitive: it walks `_ADAPTER_DISPATCH_ORDER`, dispatches each registered
adapter through the `AdapterFactory`, keeps the first non-`Unknown` result per
layer, and composes `(app_result, base_result)` into one `Provenance` via a
`match`/`assert_never` block (Phase 7 ADR-0006 §Decision). Adapter
`ProvenanceError`s fold to `Unknown` (ADR-0007); every other exception
propagates (global Rule 12 — fail loud). Production consumers go through this
function — never the raw `_REGISTRY`.

Phase 7 ADR-0006 §Decision lands the answer to the order-policy question
production ADR-0038 deferred: dispatch order is **explicit data**, declared as
a module-level `Final` tuple — not the implicit `dict.items()` iteration the
best-practices lens proposed (critic BP-1: `dict.items()` smuggles plugin-import
order, which depends on filesystem ordering, as the dispatch policy).

`_ADAPTER_DISPATCH_ORDER` is the operator-facing dispatch policy: an operator
predicts routing by reading one tuple of three rows. Within each layer-set,
`iter_adapters_for_layer_set` iterates the registry in
`Ecosystem`-enum-declaration order (ADR-0006 §Consequences row 3 — Gap 4
polyglot tiebreaker), so **registration order is not load-bearing**. S2-05's
Hypothesis property test (50 registration-order permutations → byte-identical
result) locks the discipline end-to-end; this module is where it lives.

`iter_adapters_for_layer_set` yields adapter **classes**, not instances
(Phase 7 ADR-0007 §Decision — `_REGISTRY` stores classes; construction is
dispatch-time and DI-aware via S2-02's `AdapterFactory`). S2-04's
`assemble_provenance` consumes both `_ADAPTER_DISPATCH_ORDER` and this helper.

Extension protocol (ADR-0006 §Consequences): adding a `Layer` row to
`_ADAPTER_DISPATCH_ORDER` is an ADR-worthy event. Adding an `Ecosystem` to an
existing layer is free — registry-only — and the intra-layer sort re-derives
automatically from `Ecosystem`'s declaration order (S2-01 AC-2 pins it).

This is a **Final-tuple marker catalog** — the sibling pattern to Phase 1's
`_GENERATOR_HEADER_MARKERS`, `_REFLECTION_QUERIES`, and `_LOCKFILE_PRECEDENCE`:
typed data declares policy, code reads it (Strategy via data; ADR-0006
§Pattern fit).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Final, assert_never, cast

from codegenie.primitives.vuln_provenance.errors import ProvenanceError
from codegenie.primitives.vuln_provenance.factory import default_adapter_factory
from codegenie.primitives.vuln_provenance.registry import _REGISTRY, Ecosystem, Layer
from codegenie.primitives.vuln_provenance.types import (
    AppDirect,
    AppTransitive,
    AppVendored,
    BaseImage,
    Both,
    RuntimeBundled,
    Unknown,
)

if TYPE_CHECKING:
    from codegenie.primitives.vuln_provenance.factory import AdapterFactory
    from codegenie.primitives.vuln_provenance.protocols import VulnProvenanceAdapter
    from codegenie.primitives.vuln_provenance.syft_reader import SyftSbom
    from codegenie.primitives.vuln_provenance.types import AppKind, BaseKind, Provenance
    from codegenie.types.identifiers import (
        CveId,
        ImageRef,
        PackageId,
        ProvenanceAdapterId,
    )


__all__ = ["assemble_provenance", "iter_adapters_for_layer_set"]


_ADAPTER_DISPATCH_ORDER: Final[tuple[tuple[Layer, ...], ...]] = (
    (Layer.APP,),  # app-layer adapters first
    (Layer.BASE_IMAGE,),  # then base-image adapters
    (Layer.RUNTIME,),  # then runtime-bundled adapters (reserved — no Phase 7 adapter)
)
"""The operator-facing dispatch policy (Phase 7 ADR-0006 §Decision).

A `Final` tuple of layer-sets walked in declaration order. The
`(Layer.RUNTIME,)` row is a reserved slot — Phase 7 ships no runtime adapter,
but the row is part of the shape so the first runtime adapter (JRE-bundled,
future phase) registers without a code change here. Changing this tuple
requires an ADR amendment (ADR-0006 §Consequences)."""


_ECOSYSTEM_SORT_KEY: Final[Mapping[Ecosystem, int]] = {eco: i for i, eco in enumerate(Ecosystem)}
"""`Ecosystem` → declaration-order index, built once at import time.

`iter_adapters_for_layer_set` looks up here (O(1)) instead of calling
`tuple(Ecosystem).index(...)` (O(n)) per item. Binding the sort to
`enumerate(Ecosystem)` keeps `Ecosystem`'s declaration order the single
source of truth (S2-01 AC-2 pins it)."""


def iter_adapters_for_layer_set(
    layer_set: tuple[Layer, ...],
    registry: Mapping[ProvenanceAdapterId, type[VulnProvenanceAdapter]],
) -> Iterator[tuple[ProvenanceAdapterId, type[VulnProvenanceAdapter]]]:
    """Yield `(key, adapter_class)` pairs for `layer_set`, in dispatch order.

    Outer order is the `layer_set` tuple. Within each layer, entries are
    sorted by `Ecosystem` enum **declaration** order — NOT `dict.items()`
    registration order (ADR-0006 §Consequences row 3; BP-1 closure). The
    helper yields adapter **classes** (ADR-0007); construction happens later
    via S2-02's `AdapterFactory`.

    `registry` is typed `Mapping` so callers pass either the real `_REGISTRY`
    or a plain-`dict` test fixture. The `key` is yielded alongside the class
    so S2-04's `assemble_provenance` can pin the `Layer` + `Ecosystem` pair
    in its audit log.
    """
    for layer in layer_set:
        matching = [(key, cls) for key, cls in registry.items() if key[0] == layer]
        # Ecosystem-enum-declaration order, NOT dict.items() order
        # (ADR-0006 §Consequences row 3; BP-1 closure).
        matching.sort(key=lambda kv: _ECOSYSTEM_SORT_KEY[kv[0][1]])
        yield from matching


def assemble_provenance(
    cve_id: CveId,
    package_id: PackageId,
    image_ref: ImageRef | None,
    sbom: SyftSbom,
    *,
    registry: Mapping[ProvenanceAdapterId, type[VulnProvenanceAdapter]] | None = None,
    adapter_factory: AdapterFactory | None = None,
) -> Provenance:
    """Compose registered adapter results into one `Provenance` — the answer
    to production ADR-0038's deferred "where is this CVE coming from?".

    Walks `_ADAPTER_DISPATCH_ORDER` (Phase 7 ADR-0006): for each layer-set,
    iterates adapters in `Ecosystem`-declaration order via
    `iter_adapters_for_layer_set`, constructs each through the `AdapterFactory`
    (ADR-0007), and keeps the first non-`Unknown` result per layer. The
    `match (app_result, base_result)` block composes the four cases:

    - `(None, None)` → `Unknown` — `adapter_error` if any adapter raised a
      `ProvenanceError`, else `no_adapter_resolved`.
    - `(app, None)` → the app-layer result, unchanged.
    - `(None, base)` → the base-layer result, unchanged.
    - `(app, base)` → `Both(app_record=app, base_record=base)` — evidence for
      Step 11's `RequiresMultiPluginCoordination`, never a coordinator call
      (ADR-0001).

    `ProvenanceError` from an adapter is caught and folded away (ADR-0007);
    every other exception propagates (global Rule 12 — fail loud). `registry`
    and `adapter_factory` default to the module `_REGISTRY` and the all-`None`
    `default_adapter_factory`; both kwargs exist for test isolation.
    """
    reg = _REGISTRY if registry is None else registry
    factory = default_adapter_factory if adapter_factory is None else adapter_factory

    app_result: Provenance | None = None
    base_result: Provenance | None = None
    adapter_error_seen = False

    for layer_set in _ADAPTER_DISPATCH_ORDER:
        for _key, cls in iter_adapters_for_layer_set(layer_set, reg):
            try:
                result = factory(cls).attribute(cve_id, package_id, image_ref, sbom)
            except ProvenanceError:
                # ADR-0007: adapter errors fold to Unknown, never crash the
                # assembly. The flag poisons the (None, None) reason below.
                adapter_error_seen = True
                continue
            if isinstance(result, Unknown):
                continue  # keep walking — a later adapter may resolve.
            # First non-Unknown wins. The (Layer, *) registration is the
            # contract that an APP adapter yields AppKind / a BASE_IMAGE
            # adapter yields BaseKind; a misbehaving adapter is caught by the
            # Both(...) Pydantic validation in the match block.
            if layer_set == (Layer.APP,):
                app_result = result
            elif layer_set == (Layer.BASE_IMAGE,):
                base_result = result
            break

    match (app_result, base_result):
        case (None, None):
            return Unknown(reason="adapter_error" if adapter_error_seen else "no_adapter_resolved")
        case (AppDirect() | AppTransitive() | AppVendored() as app, None):
            return app
        case (None, BaseImage() | RuntimeBundled() as base):
            return base
        case (app, base):
            # The irrefutable capture arm makes `case _` statically Never so
            # `assert_never` typechecks. Reached only when the class-pattern
            # arms above did not — i.e. both layers resolved. The casts honour
            # the (Layer, *) registration contract; a misbehaving adapter that
            # smuggled a wrong-layer variant is rejected by Both(...)'s
            # discriminated-union validation (fail loud — Rule 12).
            return Both(
                app_record=cast("AppKind", app),
                base_record=cast("BaseKind", base),
            )
        case _:  # pragma: no cover — static-exhaustive (assert_never proves it).
            assert_never((app_result, base_result))
