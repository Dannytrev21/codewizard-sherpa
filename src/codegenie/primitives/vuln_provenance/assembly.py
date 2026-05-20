"""Phase 7 S2-03 — `_ADAPTER_DISPATCH_ORDER` `Final` tuple + the
`Ecosystem`-sorted intra-layer iteration helper `iter_adapters_for_layer_set`.

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
from typing import TYPE_CHECKING, Final

from codegenie.primitives.vuln_provenance.registry import Ecosystem, Layer

if TYPE_CHECKING:
    from codegenie.primitives.vuln_provenance.protocols import VulnProvenanceAdapter
    from codegenie.types.identifiers import ProvenanceAdapterId


__all__ = ["iter_adapters_for_layer_set"]


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
