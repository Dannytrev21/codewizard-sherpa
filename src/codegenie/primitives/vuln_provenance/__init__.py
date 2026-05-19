"""Phase 7 `vuln.provenance` primitive — production ADR-0038 contract home.

Phase 7 ADR-0004 fixes this directory as the home for the vulnerability-
provenance primitive. This story (S1-02) ships the three supporting type-
vocabulary members (`AdapterConfidence`, `DistroPackage`, `UnknownReason`)
plus the package-internal `_Frozen` base. Follow-up stories add the
seven-variant `Provenance` union + `AppKind` / `BaseKind` aliases (S1-03),
the `VulnProvenanceAdapter` Protocol + errors (S1-04), and the `SyftSbom`
reader (S1-05).

`__all__` is sorted and exact (locked by
`tests/unit/primitives/vuln_provenance/test_types_dunder_all.py`); S1-03
grows it additively.
"""

from __future__ import annotations

from codegenie.primitives.vuln_provenance.types import (
    AdapterConfidence,
    DistroPackage,
    UnknownReason,
)

__all__ = [
    "AdapterConfidence",
    "DistroPackage",
    "UnknownReason",
]
