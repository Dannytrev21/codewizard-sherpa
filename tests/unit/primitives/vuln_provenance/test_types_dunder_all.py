"""Phase 7 S1-02 AC-13 — `__all__` sortedness + exactness pinning.

Mirrors the S1-01 convention (`src/codegenie/types/identifiers.py.__all__`
is sorted, exact, asserted). Both the `types.py` module-internal `__all__`
and the `__init__.py` public-surface `__all__` are pinned so downstream
stories (S1-03 et al.) grow the export list additively without re-sorting
or omitting a name.

`_Frozen` is a package-internal base — sibling modules import it directly
via `from codegenie.primitives.vuln_provenance.types import _Frozen`, but
**neither `types.py.__all__` nor `__init__.py.__all__` lists it**
(underscore-prefixed names are not public-surface per the repo
convention). The AC-11 fence still locates `_Frozen` via direct attribute
access, so excluding it from `__all__` does not impair the inheritance
check.
"""

from __future__ import annotations

from typing import Final

import codegenie.primitives.vuln_provenance as primitive_pkg
import codegenie.primitives.vuln_provenance.types as types_mod

_EXPECTED_TYPES_ALL: Final[tuple[str, ...]] = (
    "AdapterConfidence",
    "AppDirect",
    "AppKind",
    "AppTransitive",
    "AppVendored",
    "BaseImage",
    "BaseKind",
    "Both",
    "DistroPackage",
    "Provenance",
    "RuntimeBundled",
    "Unknown",
    "UnknownReason",
)
_EXPECTED_PUBLIC_ALL: Final[tuple[str, ...]] = (
    "AdapterConfidence",
    # S1-04 — vuln-provenance Protocol + error hierarchy.
    "AdapterError",
    "AppDirect",
    "AppKind",
    "AppTransitive",
    "AppVendored",
    "BaseImage",
    "BaseKind",
    "Both",
    "DistroPackage",
    # S2-01 — provenance-adapter registry kernel (enums + decorator).
    "Ecosystem",
    "Layer",
    "Provenance",
    # S1-04.
    "ProvenanceError",
    # S1-04.
    "RegistryError",
    "RuntimeBundled",
    # S1-05 — upstream syft SBOM Pydantic models (deliberate extra="allow").
    "SyftArtifact",
    "SyftLocation",
    "SyftSbom",
    "Unknown",
    "UnknownReason",
    # S1-04 — Protocol port.
    "VulnProvenanceAdapter",
    # S2-01 — decorator (lowercase, sorts after VulnProvenanceAdapter).
    "register_provenance_adapter",
)


def test_types_module_all_is_exact_and_sorted() -> None:
    actual = tuple(types_mod.__all__)
    assert actual == _EXPECTED_TYPES_ALL, (
        f"types.__all__ drifted from the locked tuple {_EXPECTED_TYPES_ALL}; "
        f"got {actual}. Update this test and the locked tuple together."
    )
    assert list(actual) == sorted(actual), (
        f"types.__all__ must be sorted; got {actual}, want {tuple(sorted(actual))}."
    )
    assert not any(name.startswith("_") for name in actual), (
        f"`types.__all__` must omit underscore-prefixed names (package-internal); got {actual}."
    )


def test_public_init_all_is_exact_and_sorted_and_omits_private() -> None:
    actual = tuple(primitive_pkg.__all__)
    assert actual == _EXPECTED_PUBLIC_ALL, (
        f"vuln_provenance.__all__ drifted from the locked tuple "
        f"{_EXPECTED_PUBLIC_ALL}; got {actual}."
    )
    assert list(actual) == sorted(actual)
    # `_Frozen` is package-internal — keep it out of the public surface.
    assert not any(name.startswith("_") for name in actual), (
        f"Public `__init__.py.__all__` must not export private (`_`-prefixed) names; got {actual}."
    )
