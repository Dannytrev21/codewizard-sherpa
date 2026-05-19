"""``codegenie.vuln_index`` — content-addressed sqlite vulnerability index.

S3-02 ships the schema + ``VulnIndex`` query surface (``lookup``,
``affecting_range``, ``digest``) + Alembic migration substrate + staleness
predicate. S3-03 layers the NVD/GHSA/OSV ingest CLI on top; S3-04
``BundleBuilder`` reads ``VulnIndex.digest()`` into the Bundle cache key
(Phase-3 ADR-0008).

Module-purity invariant (AC-L2): ``import codegenie.vuln_index`` must NOT
pull ``alembic`` / ``sqlalchemy`` into ``sys.modules``. Alembic is
lazy-imported inside :meth:`VulnIndex._upgrade` only.

ADRs honored: phase-3 ADR-0008 (BundleBuilder cache key), ADR-0005
(``StaleVulnIndex`` spanning event), ADR-0010 (sum-type + newtype
discipline), production ADR-0033 (newtype identifiers), Phase 0 ADR-0001
(BLAKE3/SHA-256 chokepoint via :mod:`codegenie.hashing`), production
ADR-0005 (cold-start budget — no heavyweight import on package load).
"""

from __future__ import annotations

from codegenie.vuln_index.errors import (
    VulnIndexConfigError,
    VulnIndexException,
    VulnIndexLookupError,
)
from codegenie.vuln_index.index import VulnIndex
from codegenie.vuln_index.models import AffectedRange, VulnerabilityRecord

__all__ = [
    "AffectedRange",
    "VulnIndex",
    "VulnIndexConfigError",
    "VulnIndexException",
    "VulnIndexLookupError",
    "VulnerabilityRecord",
]
