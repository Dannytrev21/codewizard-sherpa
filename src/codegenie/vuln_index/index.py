"""``VulnIndex`` — sqlite-backed (name, ecosystem) → ``[VulnerabilityRecord]`` lookup.

The query surface is three methods (``lookup``, ``affecting_range``,
``digest``) plus the staleness predicate (``is_stale`` + ``stale_payload``)
S6-04 wires into the orchestrator's ``StaleVulnIndex`` spanning-event
emission. ``_raw_insert`` / ``_raw_set_meta`` are public-by-convention
seams S3-03's ingest CLI consumes; they are NOT in :data:`__all__`.

Alembic is **lazy-imported inside** :meth:`_upgrade` only — cold-start
fence test (``tests/unit/vuln_index/test_cold_start.py``) enforces.

ADRs honored: phase-3 ADR-0008 (``digest()`` joins the Bundle cache key),
ADR-0005 (``stale_vuln_index`` is a spanning event), ADR-0010 (sum-type /
newtype discipline), Phase 0 ADR-0001 (hashing chokepoint:
:func:`codegenie.hashing.identity_hash`).
"""

from __future__ import annotations

import os
import sqlite3
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Final, Literal

from codegenie.hashing import identity_hash
from codegenie.types.identifiers import BlobDigest, CveId, Ecosystem, PackageName
from codegenie.vuln_index.errors import (
    VulnIndexConfigError,
    VulnIndexException,
    VulnIndexLookupError,
)
from codegenie.vuln_index.models import AffectedRange, VulnerabilityRecord

__all__ = ["VulnIndex"]

_DEFAULT_MAX_AGE_DAYS: Final[int] = 7
_MAX_AGE_ENV_VAR: Final[str] = "CODEGENIE_VULN_INDEX_MAX_AGE_DAYS"
_PRAGMAS: Final[tuple[str, ...]] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
)
_SCHEMA_VERSION: Final[str] = "1"
# AC-F1 — sort order severity DESC, published_at DESC, cve_id ASC.
_SEVERITY_ORDER: Final[Mapping[str, int]] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


def _parse_max_age_seconds(env: Mapping[str, str] | None = None) -> int:
    """Read ``CODEGENIE_VULN_INDEX_MAX_AGE_DAYS`` and return seconds.

    Pure within its declared input — accepts an explicit mapping (for the
    Hypothesis property test) or falls back to ``os.environ``. Raises
    ``VulnIndexException(VulnIndexConfigError(...))`` on any malformed or
    non-positive value. ``"7"``, ``" 7 "`` (post-strip), ``"7\\n"`` accept.
    """
    src: Mapping[str, str] = env if env is not None else os.environ
    raw = src.get(_MAX_AGE_ENV_VAR)
    if raw is None:
        days = _DEFAULT_MAX_AGE_DAYS
    else:
        stripped = raw.strip()
        # ``str.isdigit`` rejects ``"+7"``, ``"-1"``, ``"7.5"``, ``""``,
        # ``"not-an-int"``, ``"007 garbage"`` — exactly the corpus AC-I4
        # pins. Negatives + zero re-raise with the ``non_positive`` reason.
        if not stripped.isdigit():
            try:
                # Numeric-but-non-positive? Re-classify as non_positive.
                n = int(stripped)
            except ValueError:
                raise VulnIndexException(
                    VulnIndexConfigError(reason="invalid_max_age", details={"value": raw})
                ) from None
            if n <= 0:
                raise VulnIndexException(
                    VulnIndexConfigError(reason="non_positive_max_age", details={"value": raw})
                )
            # int() accepted but isdigit() didn't — e.g. ``"+7"``. Reject.
            raise VulnIndexException(
                VulnIndexConfigError(reason="invalid_max_age", details={"value": raw})
            )
        n = int(stripped)
        if n <= 0:
            raise VulnIndexException(
                VulnIndexConfigError(reason="non_positive_max_age", details={"value": raw})
            )
        days = n
    return days * 86400


def _is_stale_pure(*, now: float, mtime: float, max_age_seconds: int) -> bool:
    """Pure staleness predicate — no I/O, no env access.

    ``True`` iff the file is **strictly** older than ``max_age_seconds``
    AND has not skewed into the future. Clock-skew (mtime > now) → ``False``.
    """
    age = now - mtime
    if age <= 0:
        return False
    return age > max_age_seconds


def _upgrade(db: Path) -> None:
    """In-process Alembic upgrade to head — lazy-imported (AC-E1, AC-L2)."""
    # Lazy imports keep alembic + sqlalchemy out of ``import codegenie.vuln_index``'s
    # transitive closure (cold-start fence, AC-L2 / ADR-0005 analog).
    from alembic import command  # noqa: PLC0415 — cold-start budget
    from alembic.config import Config  # noqa: PLC0415

    cfg = Config()
    cfg.set_main_option(
        "script_location",
        str(Path(__file__).parent / "migrations"),
    )
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")


class VulnIndex:
    """Sqlite-backed vulnerability index — three query methods + staleness."""

    def __init__(self, path: Path) -> None:
        self._path: Path = path
        self._closed: bool = False
        self._conn: sqlite3.Connection | None = None
        if path.exists():
            self._conn = sqlite3.connect(str(path), isolation_level=None)
            for pragma in _PRAGMAS:
                self._conn.execute(pragma)

    # ----- context-manager + lifecycle -------------------------------------

    def __enter__(self) -> VulnIndex:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Idempotent close — releases the sqlite fd."""
        if self._closed:
            return
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        self._closed = True

    def __repr__(self) -> str:
        return f"VulnIndex(path={self._path!r}, closed={self._closed})"

    # ----- internal helpers -------------------------------------------------

    def _require_open(self) -> sqlite3.Connection:
        if self._closed or self._conn is None:
            raise VulnIndexException(VulnIndexLookupError(reason="closed"))
        return self._conn

    # ----- query surface ----------------------------------------------------

    def lookup(self, name: PackageName, ecosystem: Ecosystem) -> list[VulnerabilityRecord]:
        """Return all records matching ``(ecosystem, name)``, deterministically sorted."""
        conn = self._require_open()
        rows = conn.execute(
            "SELECT cve_id, ecosystem, package, introduced, fixed, last_affected, "
            "severity, published_at, source FROM vulnerabilities "
            "WHERE ecosystem = ? AND package = ?",
            (ecosystem, str(name)),
        ).fetchall()
        records = [_row_to_record(r) for r in rows]
        records.sort(key=_sort_key)
        return records

    def find_by_cve(self, cve: CveId) -> list[VulnerabilityRecord]:
        """Return all records matching ``cve``, deterministically sorted.

        ADR-0015 needs CVE-keyed lookup before the orchestrator intersects
        records with the target repo dependency set. Missing CVE returns an
        empty list, matching :meth:`lookup`'s no-match convention.
        """
        conn = self._require_open()
        rows = conn.execute(
            "SELECT cve_id, ecosystem, package, introduced, fixed, last_affected, "
            "severity, published_at, source FROM vulnerabilities "
            "WHERE cve_id = ?",
            (str(cve),),
        ).fetchall()
        records = [_row_to_record(r) for r in rows]
        records.sort(key=_sort_key)
        return records

    def affecting_range(self, cve: CveId) -> AffectedRange:
        """Return the first matching row's AffectedRange (deterministic order)."""
        conn = self._require_open()
        row = conn.execute(
            "SELECT introduced, fixed, last_affected FROM vulnerabilities "
            "WHERE cve_id = ? "
            "ORDER BY package ASC, ecosystem ASC, introduced ASC LIMIT 1",
            (str(cve),),
        ).fetchone()
        if row is None:
            raise VulnIndexException(
                VulnIndexLookupError(
                    reason="cve_not_found",
                    details={"cve_id": str(cve)},
                )
            )
        # Coalesce empty-string sentinel → None at the read boundary
        # (mirrors :func:`_row_to_record`; same reason). The values originated
        # from rows that already passed the SemverVersion field-validator on
        # insert; the runtime ``mode="before"`` validator re-coerces strings
        # so the typed annotation stays honest.
        fixed_out = row[1] if row[1] not in (None, "") else None
        last_affected_out = row[2] if row[2] not in (None, "") else None
        return AffectedRange.model_validate(
            {
                "introduced": row[0],
                "fixed": fixed_out,
                "last_affected": last_affected_out,
            }
        )

    def digest(self) -> BlobDigest:
        """Return ``BlobDigest`` (64-hex, no prefix) summarizing the meta inputs."""
        conn = self._require_open()
        meta_values = {
            "schema_version": _SCHEMA_VERSION,
            "feed_digest_nvd": "",
            "feed_digest_ghsa": "",
            "feed_digest_osv": "",
        }
        rows = conn.execute("SELECT key, value FROM meta").fetchall()
        for key, value in rows:
            if key in meta_values:
                meta_values[key] = value
        prefixed = identity_hash(
            meta_values["schema_version"],
            meta_values["feed_digest_nvd"],
            meta_values["feed_digest_ghsa"],
            meta_values["feed_digest_osv"],
        )
        # identity_hash returns "sha256:<64-hex>"; BlobDigest grammar is
        # ^[0-9a-f]{64}$ (no prefix). Strip the algorithm tag.
        return BlobDigest(prefixed.split(":", 1)[1])

    # ----- staleness --------------------------------------------------------

    def is_stale(self, *, now: float | None = None) -> bool:
        """Return ``True`` iff the on-disk file's mtime is older than the threshold.

        Reads the env var per call so operators flipping the threshold
        mid-run take effect immediately (12-factor dynamic config).
        Non-existent path → ``False`` (an empty index is "fresh" by
        convention).
        """
        max_age_seconds = _parse_max_age_seconds()
        if not self._path.exists():
            return False
        wall = now if now is not None else time.time()
        try:
            mtime = self._path.stat().st_mtime
        except FileNotFoundError:
            # TOCTOU between exists() + stat() — treat as fresh.
            return False
        return _is_stale_pure(now=wall, mtime=mtime, max_age_seconds=max_age_seconds)

    def stale_payload(self) -> dict[str, str | int | bool | float | list[str]]:
        """Return the dict payload S6-04 attaches to ``stale_vuln_index`` events."""
        max_age_seconds = _parse_max_age_seconds()
        threshold_days = max_age_seconds // 86400
        wall = time.time()
        try:
            mtime = self._path.stat().st_mtime
        except FileNotFoundError:
            mtime = wall
        age_days = max((wall - mtime) / 86400.0, 0.0)
        mtime_iso = datetime.fromtimestamp(mtime, tz=UTC).isoformat()
        return {
            "path": str(self._path),
            "mtime_iso": mtime_iso,
            "age_days": age_days,
            "threshold_days": int(threshold_days),
        }

    # ----- test seams (NOT in __all__; S3-03 ingest CLI consumes) -----------

    def _raw_insert(self, record: VulnerabilityRecord) -> None:
        """Insert one record idempotently (``INSERT OR IGNORE``) — AC-D4.

        ``fixed`` / ``last_affected`` are coalesced ``None → ""`` at the
        storage boundary so the unique constraint participates correctly
        (sqlite treats NULL as distinct from NULL by default, which would
        defeat ``INSERT OR IGNORE``). The empty string is round-tripped
        back to ``None`` in :func:`_row_to_record`.
        """
        if not isinstance(record, VulnerabilityRecord):
            raise TypeError(f"_raw_insert expects VulnerabilityRecord, got {type(record).__name__}")
        conn = self._require_open()
        conn.execute(
            "INSERT OR IGNORE INTO vulnerabilities ("
            "cve_id, ecosystem, package, introduced, fixed, last_affected, "
            "severity, published_at, source, raw_payload"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(record.cve_id),
                record.ecosystem,
                str(record.package),
                record.affected_range.introduced,
                record.affected_range.fixed if record.affected_range.fixed is not None else "",
                record.affected_range.last_affected
                if record.affected_range.last_affected is not None
                else "",
                record.severity,
                record.published_at.isoformat(),
                record.source,
                record.model_dump_json().encode("utf-8"),
            ),
        )

    def _raw_set_meta(self, key: str, value: str) -> None:
        """Upsert a meta row (S3-03 ingest CLI seam)."""
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError("_raw_set_meta expects (str, str) arguments")
        conn = self._require_open()
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def _row_to_record(row: tuple[object, ...]) -> VulnerabilityRecord:
    """Reconstitute a ``VulnerabilityRecord`` from a sqlite row.

    Trusted-input boundary — values originated from a record that already
    passed Pydantic validation on insert. ``datetime.fromisoformat`` rebuilds
    the tz-aware timestamp (AC-B4).
    """
    cve_id, ecosystem, package, introduced, fixed, last_affected, severity, published_at, source = (
        row
    )
    # Empty-string sentinel (set by _raw_insert) round-trips back to None.
    fixed_out = str(fixed) if fixed not in (None, "") else None
    last_affected_out = str(last_affected) if last_affected not in (None, "") else None
    return VulnerabilityRecord(
        cve_id=CveId(str(cve_id)),
        ecosystem=_narrow_ecosystem(str(ecosystem)),
        package=PackageName(str(package)),
        affected_range=AffectedRange.model_validate(
            {
                "introduced": str(introduced),
                "fixed": fixed_out,
                "last_affected": last_affected_out,
            }
        ),
        severity=_narrow_severity(str(severity)),
        published_at=datetime.fromisoformat(str(published_at)),
        source=_narrow_source(str(source)),
    )


def _narrow_ecosystem(s: str) -> Ecosystem:
    if s not in {"npm", "pypi", "maven", "rubygems", "gomod"}:
        raise ValueError(f"unknown ecosystem in stored row: {s!r}")
    return s  # type: ignore[return-value]


def _narrow_severity(s: str) -> Literal["low", "medium", "high", "critical"]:
    if s not in {"low", "medium", "high", "critical"}:
        raise ValueError(f"unknown severity in stored row: {s!r}")
    return s  # type: ignore[return-value]


def _narrow_source(s: str) -> Literal["nvd", "ghsa", "osv"]:
    if s not in {"nvd", "ghsa", "osv"}:
        raise ValueError(f"unknown source in stored row: {s!r}")
    return s  # type: ignore[return-value]


def _sort_key(r: VulnerabilityRecord) -> tuple[int, float, str]:
    """AC-F1 / AC-F4 — severity DESC, published_at DESC, cve_id ASC."""
    # ``published_at DESC`` via negation of the timestamp; cve_id ASC stays
    # natural. ``_SEVERITY_ORDER`` maps critical=0 (highest) → low=3, so the
    # natural ascending order on the int IS severity DESC.
    return (_SEVERITY_ORDER[r.severity], -r.published_at.timestamp(), str(r.cve_id))
