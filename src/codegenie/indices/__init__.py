"""``codegenie.indices`` — typed answers about index freshness.

For Phase 2 this package contains exactly one module — :mod:`freshness` —
exporting the ``IndexFreshness`` discriminated-union sum type. The S1-02
registry (``codegenie.indices.registry``) layers on top.

See ``docs/phases/02-context-gather-layers-b-g/ADRs/0006-index-freshness-sum-type-location.md``
for the architectural rationale and the cross-ADR contract that pins the
discriminator strings.
"""

from codegenie.indices.freshness import (
    CommitsBehind,
    CoverageGap,
    DigestMismatch,
    Fresh,
    IndexerError,
    IndexFreshness,
    Stale,
    StaleReason,
)
from codegenie.indices.registry import (
    FreshnessCheck,
    FreshnessRegistry,
    FreshnessRegistryError,
    default_freshness_registry,
    register_index_freshness_check,
)

__all__ = [
    "CommitsBehind",
    "CoverageGap",
    "DigestMismatch",
    "Fresh",
    "FreshnessCheck",
    "FreshnessRegistry",
    "FreshnessRegistryError",
    "IndexFreshness",
    "IndexerError",
    "Stale",
    "StaleReason",
    "default_freshness_registry",
    "register_index_freshness_check",
]
