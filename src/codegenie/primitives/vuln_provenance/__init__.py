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
"""

from __future__ import annotations

from codegenie.primitives.vuln_provenance.errors import (
    AdapterError,
    ProvenanceError,
    RegistryError,
)
from codegenie.primitives.vuln_provenance.protocols import VulnProvenanceAdapter
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
    "AppDirect",
    "AppKind",
    "AppTransitive",
    "AppVendored",
    "BaseImage",
    "BaseKind",
    "Both",
    "DistroPackage",
    "Provenance",
    "ProvenanceError",
    "RegistryError",
    "RuntimeBundled",
    "Unknown",
    "UnknownReason",
    "VulnProvenanceAdapter",
]
