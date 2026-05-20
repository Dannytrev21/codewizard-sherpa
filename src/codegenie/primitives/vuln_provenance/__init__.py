"""Phase 7 `vuln.provenance` primitive — production ADR-0038 contract home.

Phase 7 ADR-0004 fixes this directory as the home for the vulnerability-
provenance primitive. S1-02 shipped the three supporting type-vocabulary
members (`AdapterConfidence`, `DistroPackage`, `UnknownReason`) plus the
package-internal `_Frozen` base. S1-03 grows the surface with the
seven-variant `Provenance` discriminated union, the `AppKind` / `BaseKind`
nested-union aliases, and the final `Provenance` alias. Follow-up stories
add the `VulnProvenanceAdapter` Protocol + errors (S1-04) and the
`SyftSbom` reader (S1-05).

`__all__` is sorted and exact (locked by
`tests/unit/primitives/vuln_provenance/test_types_dunder_all.py`); future
stories grow it additively in ASCII order.

S1-04 grows the surface by four names — `VulnProvenanceAdapter` (the
Protocol port; `errors.py` companions `ProvenanceError`, `RegistryError`,
`AdapterError`).

S1-05 grows the surface by three names — the upstream-syft Pydantic
models `SyftSbom`, `SyftArtifact`, `SyftLocation` (carrying the
deliberate `extra="allow"` posture; consumer-side fence lives in S4-04).

S2-01 grows the surface by three names — the `Layer` and `Ecosystem` enums
plus the `@register_provenance_adapter` decorator. The `_REGISTRY` dict
itself stays module-private (see `registry.py`); consumers go through
`assemble_provenance` (S2-04), not the raw dict.

S2-02 grows the surface by three names — the `AdapterFactory` Protocol,
the `DefaultAdapterFactory` implementation, and the all-`None`
`default_adapter_factory` singleton. The closed DI-kwarg vocabulary
`_DI_KWARGS` stays module-private (see `factory.py`).

S2-03 grows the surface by one name — `iter_adapters_for_layer_set`, the
`Ecosystem`-sorted intra-layer adapter-iteration helper. The dispatch-order
tuple `_ADAPTER_DISPATCH_ORDER` stays module-private (see `assembly.py`);
S2-04's `assemble_provenance` reaches it via the module path.

S2-04 grows the surface by two names — `assemble_provenance`, the composition
free function that walks `_ADAPTER_DISPATCH_ORDER` and folds adapter results
into one `Provenance`, and `provenance`, a re-export alias of the same
callable that TCCM `derived_queries:` (S8-02) resolves `compute:
vuln.provenance` to.
"""

from __future__ import annotations

from codegenie.primitives.vuln_provenance.assembly import (
    assemble_provenance,
    iter_adapters_for_layer_set,
)
from codegenie.primitives.vuln_provenance.assembly import (
    assemble_provenance as provenance,
)
from codegenie.primitives.vuln_provenance.errors import (
    AdapterError,
    ProvenanceError,
    RegistryError,
)
from codegenie.primitives.vuln_provenance.factory import (
    AdapterFactory,
    DefaultAdapterFactory,
    default_adapter_factory,
)
from codegenie.primitives.vuln_provenance.protocols import VulnProvenanceAdapter
from codegenie.primitives.vuln_provenance.registry import (
    Ecosystem,
    Layer,
    register_provenance_adapter,
)
from codegenie.primitives.vuln_provenance.syft_reader import (
    SyftArtifact,
    SyftLocation,
    SyftSbom,
)
from codegenie.primitives.vuln_provenance.types import (
    AdapterConfidence,
    AppDirect,
    AppKind,
    AppTransitive,
    AppVendored,
    BaseImage,
    BaseKind,
    Both,
    DistroPackage,
    Provenance,
    RuntimeBundled,
    Unknown,
    UnknownReason,
)

__all__ = [
    "AdapterConfidence",
    "AdapterError",
    "AdapterFactory",
    "AppDirect",
    "AppKind",
    "AppTransitive",
    "AppVendored",
    "BaseImage",
    "BaseKind",
    "Both",
    "DefaultAdapterFactory",
    "DistroPackage",
    "Ecosystem",
    "Layer",
    "Provenance",
    "ProvenanceError",
    "RegistryError",
    "RuntimeBundled",
    "SyftArtifact",
    "SyftLocation",
    "SyftSbom",
    "Unknown",
    "UnknownReason",
    "VulnProvenanceAdapter",
    "assemble_provenance",
    "default_adapter_factory",
    "iter_adapters_for_layer_set",
    "provenance",
    "register_provenance_adapter",
]
