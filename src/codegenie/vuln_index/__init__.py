"""``codegenie.vuln_index`` — content-addressed sqlite vulnerability index.

S3-02 ships the schema + ``VulnIndex`` query surface (``lookup``,
``affecting_range``, ``digest``) + Alembic migration substrate + staleness
predicate. S3-03 layers the NVD/GHSA/OSV ingest CLI on top via a
``@register_vuln_feed`` registry kernel; S3-04 ``BundleBuilder`` reads
``VulnIndex.digest()`` into the Bundle cache key (Phase-3 ADR-0008).

Module-purity invariant: ``import codegenie.vuln_index`` must NOT pull
``alembic`` / ``sqlalchemy`` / ``urllib.request`` into ``sys.modules``.
Alembic is lazy-imported inside :meth:`VulnIndex._upgrade` and the CLI's
``_apply_migrations`` helper; ``urllib.request`` is lazy-imported inside
each ``Feed.fetch`` method body. Tests
(``tests/unit/vuln_index/test_cold_start*.py``) enforce.

Explicit imports drive feed registration (AC-R4 — mirrors
``probes/__init__.py``'s explicit-import discipline; no
``importlib.metadata`` entry-point scan). Adding a Phase 4+ feed:

1. land a new ``feeds/<source>.py`` module decorated with
   ``@register_vuln_feed("<source>")``;
2. add one new ``from .feeds import <source> as _<source>`` line below.

ADRs honored: phase-3 ADR-0008 (BundleBuilder cache key), ADR-0005
(``StaleVulnIndex`` spanning event), ADR-0010 (sum-type + newtype
discipline + Open/Closed seam), production ADR-0033 (newtype identifiers),
Phase 0 ADR-0001 (BLAKE3/SHA-256 chokepoint via :mod:`codegenie.hashing`),
production ADR-0005 (cold-start budget).
"""

from __future__ import annotations

from codegenie.vuln_index.errors import (
    VulnIndexConfigError,
    VulnIndexException,
    VulnIndexLookupError,
)

# Explicit-import wiring — each row fires one ``@register_vuln_feed(...)``
# decoration at import time. Order is irrelevant (registry sorts on
# iteration), but the row count is load-bearing: AC-R4 asserts that
# omitting one row drops the corresponding source.
from codegenie.vuln_index.feeds import ghsa as _ghsa  # noqa: F401
from codegenie.vuln_index.feeds import nvd as _nvd  # noqa: F401
from codegenie.vuln_index.feeds import osv as _osv  # noqa: F401
from codegenie.vuln_index.index import VulnIndex
from codegenie.vuln_index.ingest import IngestStats, ingest_records
from codegenie.vuln_index.models import AffectedRange, VulnerabilityRecord
from codegenie.vuln_index.parsers import VulnParseError, VulnParseException
from codegenie.vuln_index.protocol import Feed, FeedSource
from codegenie.vuln_index.registry import (
    FeedRegistry,
    FeedRegistryError,
    default_feed_registry,
    register_vuln_feed,
)

__all__ = [
    "AffectedRange",
    "Feed",
    "FeedRegistry",
    "FeedRegistryError",
    "FeedSource",
    "IngestStats",
    "VulnIndex",
    "VulnIndexConfigError",
    "VulnIndexException",
    "VulnIndexLookupError",
    "VulnParseError",
    "VulnParseException",
    "VulnerabilityRecord",
    "default_feed_registry",
    "ingest_records",
    "register_vuln_feed",
]
