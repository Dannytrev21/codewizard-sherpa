"""S3-03 — UPSERT pipeline + deterministic feed-digest computation.

Functional core / imperative shell:

- Pure ``_record_to_row(record)`` projects a typed :class:`VulnerabilityRecord`
  into the storage column tuple (no I/O, no global state).
- Impure ``_persist(conn, rows)`` runs ``INSERT OR IGNORE`` against the
  sqlite store and returns ``(inserted, skipped)``.
- ``ingest_records(idx, records)`` drives both, splitting parse errors
  from successful records and capping the error report at
  :data:`_MAX_ERROR_REPORT`.
- ``_update_feed_digest(idx, source, records)`` canonicalizes records by
  ``cve_id ASC`` before concatenation so the digest is deterministic
  across fetch order (load-bearing for Phase-3 ADR-0008's BundleBuilder
  cache key).

ADRs: phase-3 ADR-0008 (`vuln_index.digest()` joins the Bundle cache key —
deterministic across fetch order); ADR-0010 (sum-type discipline at the
error model boundary).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

from codegenie.hashing import identity_hash
from codegenie.vuln_index.index import VulnIndex
from codegenie.vuln_index.models import VulnerabilityRecord
from codegenie.vuln_index.parsers import (
    _MAX_ERROR_REPORT,
    VulnParseError,
    canonical_raw_payload,
)

__all__ = ["IngestStats", "_update_feed_digest", "ingest_records"]


class IngestStats(BaseModel):
    """Bounded summary of one ``ingest_records`` invocation.

    ``errors`` is capped at :data:`_MAX_ERROR_REPORT`; surplus errors are
    counted into ``errors_truncated``. Total error count = ``len(errors)
    + errors_truncated``.
    """

    model_config = ConfigDict(frozen=True)

    inserted: int = 0
    skipped: int = 0
    errors: list[VulnParseError] = []
    errors_truncated: int = 0


def ingest_records(
    idx: VulnIndex,
    records: Iterable[VulnerabilityRecord | VulnParseError],
) -> IngestStats:
    """Drive parse-errors + records through the UPSERT pipeline (AC-D1, AC-D4)."""
    successes: list[VulnerabilityRecord] = []
    errors: list[VulnParseError] = []
    errors_truncated = 0
    for item in records:
        if isinstance(item, VulnParseError):
            if len(errors) < _MAX_ERROR_REPORT:
                errors.append(item)
            else:
                errors_truncated += 1
        elif isinstance(item, VulnerabilityRecord):
            successes.append(item)
        else:  # pragma: no cover — defensive
            raise TypeError(f"ingest_records: unexpected type {type(item).__name__}")
    conn = idx._require_open()  # noqa: SLF001 — intentional test seam
    rows = (_record_to_row_with_blob(r) for r in successes)
    inserted, skipped = _persist(conn, rows)
    return IngestStats(
        inserted=inserted,
        skipped=skipped,
        errors=errors,
        errors_truncated=errors_truncated,
    )


def _persist(
    conn: sqlite3.Connection,
    rows: Iterable[tuple[object, ...]],
) -> tuple[int, int]:
    """Run ``INSERT OR IGNORE`` per row; return ``(inserted, skipped)``.

    sqlite's ``changes()`` reports the rowcount of the most-recent
    statement. ``INSERT OR IGNORE`` returns ``1`` on insert, ``0`` on
    constraint-violation skip — exactly the idempotency signal AC-D4
    requires.
    """
    inserted = 0
    skipped = 0
    for row in rows:
        conn.execute(
            "INSERT OR IGNORE INTO vulnerabilities ("
            "cve_id, ecosystem, package, introduced, fixed, last_affected, "
            "severity, published_at, source, raw_payload"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            row,
        )
        changes = conn.execute("SELECT changes()").fetchone()[0]
        if changes == 1:
            inserted += 1
        else:
            skipped += 1
    return inserted, skipped


def _record_to_row_with_blob(record: VulnerabilityRecord) -> tuple[object, ...]:
    """Internal — :func:`_record_to_row` + the raw-payload BLOB column.

    Tests assert ``_record_to_row`` is pure (no I/O). The persisted BLOB
    is a side-effecty serialization (``model_dump_json``); kept separate so
    the pure helper stays property-testable.
    """
    pure = _record_to_row(record)
    return (*pure, record.model_dump_json().encode("utf-8"))


# AC-D2 — deterministic field separators. ASCII unit-separator (\x1f)
# between fields within a record; record-separator (\x1e) between records.
# Both are reserved control characters that cannot appear in a valid
# JSON-canonicalized payload, eliminating ambiguity.
_FIELD_SEP: Final[str] = "\x1f"
_RECORD_SEP: Final[str] = "\x1e"


def _update_feed_digest(
    idx: VulnIndex,
    source: str,
    records: Sequence[VulnerabilityRecord],
) -> None:
    """Compute and store the per-feed digest for ``source`` (AC-D2 / ADR-0008).

    The records are canonicalized by ``cve_id ASC`` before concat so the
    digest is deterministic across fetch order. ``VulnParseError`` records
    are deliberately NOT included — otherwise a transient parse error
    upstream would thrash the Bundle cache.

    The digest itself is the 64-hex tail of ``identity_hash(...)``
    (BLAKE3/SHA-256 chokepoint — Phase 0 ADR-0001). Empty ``records``
    sequence → empty-string digest (matches the empty-DB sentinel pinned
    by S3-02 AC-H2).
    """
    if not records:
        idx._raw_set_meta(f"feed_digest_{source}", "")  # noqa: SLF001
        return
    canonical = sorted(records, key=lambda r: str(r.cve_id))
    parts: list[str] = []
    for r in canonical:
        # ``model_dump`` gives a deterministic dict; we then canonicalize via
        # the shared :func:`canonical_raw_payload` so dict-key ordering does
        # not leak into the digest.
        payload = canonical_raw_payload(r.model_dump(mode="json"))
        parts.append(f"{r.cve_id}{_FIELD_SEP}{payload.decode('utf-8')}{_RECORD_SEP}")
    prefixed = identity_hash(*parts)
    # ``identity_hash`` returns ``"sha256:<64-hex>"``; the digest column
    # stores the bare hex (matches :meth:`VulnIndex.digest` shape).
    idx._raw_set_meta(f"feed_digest_{source}", prefixed.split(":", 1)[1])  # noqa: SLF001


def _record_to_row(record: VulnerabilityRecord) -> tuple[str, ...]:
    """Pure projection — typed record → storage column tuple (AC-D3).

    Mirrors :meth:`VulnIndex._raw_insert`'s column order (cve_id,
    ecosystem, package, introduced, fixed, last_affected, severity,
    published_at, source). Empty-string sentinel applies to optional
    semver fields (matches the storage round-trip in
    :func:`codegenie.vuln_index.index._row_to_record`).
    """
    return (
        str(record.cve_id),
        record.ecosystem,
        str(record.package),
        str(record.affected_range.introduced),
        str(record.affected_range.fixed) if record.affected_range.fixed is not None else "",
        str(record.affected_range.last_affected)
        if record.affected_range.last_affected is not None
        else "",
        record.severity,
        record.published_at.isoformat(),
        record.source,
    )
