"""``Feed(Protocol)`` — hexagonal port for one CVE feed source (S3-03).

Each concrete feed (``NvdFeed``, ``GhsaFeed``, ``OsvFeed``) under
:mod:`codegenie.vuln_index.feeds` implements this Protocol and registers
itself with :func:`codegenie.vuln_index.registry.register_vuln_feed`. The
CLI iterates ``default_feed_registry.feed_sources()`` (sorted) and
dispatches through ``registry.get_feed(source)`` — Phase 4+ adds a feed by
landing a new ``feeds/<source>.py`` module + one explicit-import row in
``vuln_index/__init__.py``. Zero edits to ``cli.py``, ``parsers.py``, or
``ingest.py``.

ADRs honored: Phase-3 ADR-0010 (Open/Closed seam at the file boundary —
mirrors :mod:`codegenie.indices.registry` and :mod:`codegenie.depgraph.registry`
precedents).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import ClassVar, Literal, Protocol, runtime_checkable

from codegenie.result import Result
from codegenie.vuln_index.models import VulnerabilityRecord
from codegenie.vuln_index.parsers import VulnParseError

__all__ = ["Feed", "FeedSource"]

# Closed Literal of registered feed sources. Phase 4+ widens by ADR
# amendment ONLY (not silently). Mirrors S3-02's ``Ecosystem`` discipline.
FeedSource = Literal["nvd", "ghsa", "osv"]


@runtime_checkable
class Feed(Protocol):
    """One CVE-feed source — fetch raw record bytes + parse one record at a time.

    Implementations are stateless: ``fetch()`` returns an iterator of opaque
    record-shaped byte chunks, ``parse_one(raw)`` projects one chunk into a
    typed :class:`VulnerabilityRecord` (or a typed :class:`VulnParseError`).
    The ingest layer drives both via ``(feed.parse_one(b) for b in feed.fetch())``.
    """

    source: ClassVar[str]
    """One of :data:`FeedSource` — but typed as ``str`` here so the test
    helper can register additional cassette-only feeds (e.g., ``"_test"``)
    without amending the Literal mid-test."""

    def parse_one(self, raw: bytes) -> Result[VulnerabilityRecord, VulnParseError]:
        """Project one raw record-shaped chunk into a typed record or error."""
        ...

    def fetch(
        self,
        *,
        since: datetime | None = None,
        timeout_s: float = 30.0,
    ) -> Iterator[bytes]:
        """Yield raw record-shaped chunks from the upstream feed."""
        ...
