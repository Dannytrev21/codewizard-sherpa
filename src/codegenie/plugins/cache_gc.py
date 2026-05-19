"""S3-05 — Bundle cache garbage collector (Gap 4 fix).

This module IS the Gap 4 fix from
``docs/phases/03-vuln-deterministic-recipe/phase-arch-design.md
§Gap analysis``: the synthesis named "GC after 7 days mtime" but no
component owned the mechanism. :class:`BundleCacheGc` is that
component, with two trigger surfaces:

- :meth:`BundleCacheGc.run` — unconditional walk + evict. The
  ``codegenie cache prune`` operator CLI dispatches here.
- :meth:`BundleCacheGc.run_amortized` — 24-hour-amortised walk.
  Consults ``<cache_dir>/.gc-stamp`` under an ``fcntl.flock`` and
  short-circuits when the previous run is < 24h old. The
  orchestrator (S6-04) dispatches here at workflow init.

Both paths emit **exactly one** :class:`CacheGcCompletedEvent` per
``run()`` invocation (the no-op branch of ``run_amortized`` emits
zero events). The event carries ``trigger ∈ {"amortized",
"operator_cli"}`` so Phase 9 spanning-stream queries can distinguish
background GC from operator-driven prune.

Design discipline:

- **Functional core / imperative shell.** :func:`_parse_ttl_seconds`,
  :func:`_is_evictable`, :func:`_should_run_amortized` are pure (no
  ``os``, ``time``, ``Path`` references). The AST fence at
  ``tests/unit/plugins/test_cache_gc_purity.py`` holds the line.
- **Strict ``>`` TTL boundary** (matches arch §Gap-4 prose ``mtime
  > 7 days``). An entry whose age equals the TTL is kept; one second
  older is evicted.
- **Fail-loud env validation.** A malformed
  ``CODEGENIE_BUNDLE_CACHE_TTL_DAYS`` value raises
  :class:`BundleCacheRaise` with ``reason="invalid_ttl_env"`` (Rule
  12 — silent default-fallback hides operator typos).
- **Constructor does no I/O.** Env reads happen in :meth:`run` so a
  malformed env value does not fail at construction (DP1 — S3-02
  ``_parse_max_age_seconds`` precedent).
"""

from __future__ import annotations

import fcntl
import os
import re
import secrets
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, field_serializer

from codegenie.plugins.cache import BundleCacheErrorModel, BundleCacheRaise
from codegenie.transforms._forward import SandboxedPath

__all__ = sorted(
    [
        "BundleCacheGc",
        "CacheGcCompletedEvent",
        "CacheGcResult",
    ]
)


# --- Constants --------------------------------------------------------------

_DEFAULT_TTL_DAYS: Final[int] = 7
_BUNDLES_DIRNAME: Final[str] = "bundles"
_GC_STAMP_FILENAME: Final[str] = ".gc-stamp"
_GC_STAMP_LOCK_FILENAME: Final[str] = ".gc-stamp.lock"
_AMORTIZATION_SECONDS: Final[int] = 86_400
_HEX_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}\.json$")
_TTL_ENV_VAR: Final[str] = "CODEGENIE_BUNDLE_CACHE_TTL_DAYS"
_DECIMAL_INT_RE: Final[re.Pattern[str]] = re.compile(r"^[1-9][0-9]*$")
_FILE_MODE: Final[int] = 0o600
_DIR_MODE: Final[int] = 0o700


# --- Pure helpers (functional core; AST-fenced) -----------------------------


def _parse_ttl_seconds(env: Mapping[str, str]) -> int:
    """Return the configured TTL in seconds from the env mapping.

    Reads :data:`_TTL_ENV_VAR` (default ``"7"``), strips ASCII
    whitespace, and accepts only positive decimal integers. Anything
    else — empty, ``"0"``, ``"-1"``, ``"7.5"``, ``"+7"``, ``"1e2"``,
    ``"0x7"``, non-digits — raises :class:`BundleCacheRaise` with
    ``reason="invalid_ttl_env"``. Multiplies the parsed days by
    ``86400``.

    Pure — no env, no filesystem, no clock. The caller passes
    ``os.environ`` (or a test mapping) at the impure-shell boundary.
    """
    raw = env.get(_TTL_ENV_VAR, "7")
    stripped = raw.strip()
    if not _DECIMAL_INT_RE.fullmatch(stripped):
        raise BundleCacheRaise(
            BundleCacheErrorModel(
                reason="invalid_ttl_env",
                details={"value": raw},
            )
        )
    return int(stripped) * 86_400


def _is_evictable(now: float, mtime: float, ttl_seconds: int) -> bool:
    """Return ``True`` iff ``mtime`` is **strictly** older than ``now - ttl_seconds``.

    Strict ``>`` matches arch §Gap-4 prose ``mtime > 7 days``: an entry
    whose age equals the TTL is **kept**. Pure.
    """
    return (now - mtime) > ttl_seconds


def _should_run_amortized(now: float, last_stamp: float, interval_seconds: int) -> bool:
    """Return ``True`` iff the amortised GC should run.

    True when ``(now - last_stamp) >= interval_seconds`` OR
    ``last_stamp > now`` (clock-skew resilience: a future-dated stamp
    is treated as stale and re-written). Pure.
    """
    if last_stamp > now:
        return True
    return (now - last_stamp) >= interval_seconds


# --- Result + event models --------------------------------------------------


class CacheGcResult(BaseModel):
    """Typed result of one :meth:`BundleCacheGc.run` invocation."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    entries_evicted: int
    bytes_reclaimed: int
    cache_dir: SandboxedPath
    ttl_days: int
    duration_ms: int
    wall_clock_iso: str

    @field_serializer("cache_dir")
    def _serialise_cache_dir(self, value: SandboxedPath) -> str:
        return str(value.absolute)


class CacheGcCompletedEvent(BaseModel):
    """Spanning-stream event emitted exactly once per :meth:`BundleCacheGc.run`.

    ``event_type`` is the discriminator on the
    :data:`codegenie.events.WorkflowSpanningEvent.event_type` Literal
    union (arch §C9; line ~872 amended additively by this story per
    AC-23).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_type: Literal["cache_gc_completed"] = "cache_gc_completed"
    cache_dir: str
    entries_evicted: int
    bytes_reclaimed: int
    ttl_days: int
    duration_ms: int
    wall_clock_iso: str
    trigger: Literal["amortized", "operator_cli"]

    @classmethod
    def from_result(
        cls,
        result: CacheGcResult,
        *,
        trigger: Literal["amortized", "operator_cli"],
    ) -> CacheGcCompletedEvent:
        """Project a :class:`CacheGcResult` to a :class:`CacheGcCompletedEvent`.

        Stringifies ``cache_dir`` (JSON-friendly); copies the rest
        verbatim. A drift canary test asserts every
        :class:`CacheGcResult` field other than ``cache_dir`` is
        present in this event.
        """
        return cls(
            cache_dir=str(result.cache_dir),
            entries_evicted=result.entries_evicted,
            bytes_reclaimed=result.bytes_reclaimed,
            ttl_days=result.ttl_days,
            duration_ms=result.duration_ms,
            wall_clock_iso=result.wall_clock_iso,
            trigger=trigger,
        )


# --- BundleCacheGc ----------------------------------------------------------


def _atomic_write_text(target: Path, content: str) -> None:
    """Write ``content`` to ``target`` via tmp + fsync + ``os.replace``.

    Mirrors :func:`codegenie.cache.store._atomic_write_bytes`. The
    third atomic-write call site lands here (after Phase-0 and the
    Bundle blob write in :mod:`codegenie.plugins.cache`); the
    rule-of-three for extraction to ``codegenie._fs_atomic`` is met
    in spirit but story §Notes DP-G defers it ("inline ~5 lines"
    keeps this PR surgical).
    """
    tmp = target.with_suffix(target.suffix + f".{os.getpid()}.{secrets.token_hex(4)}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _FILE_MODE)
    try:
        os.write(fd, content.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, target)


def _now_iso() -> str:
    """Return ``time.time()``'s UTC wall-clock as RFC3339 with millisecond precision."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class BundleCacheGc:
    """Bundle-cache garbage collector — pure helpers + impure shell.

    The constructor does **no I/O and no env read** (DP1). Env reads
    happen in :meth:`run`; a malformed env value raises
    :class:`BundleCacheRaise` then, not at construction.
    """

    def __init__(
        self,
        cache_dir: SandboxedPath,
        *,
        ttl_seconds: int | None = None,
        event_emitter: Callable[[CacheGcCompletedEvent], None] | None = None,
    ) -> None:
        self.cache_dir: SandboxedPath = cache_dir
        self._ttl_seconds_override: int | None = ttl_seconds
        self._event_emitter: Callable[[CacheGcCompletedEvent], None] | None = event_emitter

    def _resolved_ttl_seconds(self) -> int:
        if self._ttl_seconds_override is not None:
            return self._ttl_seconds_override
        return _parse_ttl_seconds(os.environ)

    def run(self) -> CacheGcResult:
        """Walk ``<cache_dir>/bundles/``, evict stale entries, emit one event.

        Returns a :class:`CacheGcResult` with bookkeeping fields
        (``entries_evicted``, ``bytes_reclaimed``, ``duration_ms``,
        ``wall_clock_iso``). If ``event_emitter`` was provided to the
        constructor, calls it **exactly once** with a
        :class:`CacheGcCompletedEvent` whose ``trigger="amortized"``
        (the CLI rewrites the trigger to ``"operator_cli"`` on top of
        this result via :meth:`CacheGcCompletedEvent.from_result`).
        """
        start_ns = time.monotonic_ns()
        wall_clock_iso = _now_iso()
        ttl_seconds = self._resolved_ttl_seconds()
        ttl_days = ttl_seconds // 86_400

        entries_evicted = 0
        bytes_reclaimed = 0
        bundles = self.cache_dir / _BUNDLES_DIRNAME
        now = time.time()
        if bundles.is_dir():
            for child in bundles.iterdir():
                if child.is_symlink():
                    continue
                if not child.is_file():
                    continue
                if not _HEX_NAME_RE.fullmatch(child.name):
                    continue
                try:
                    stat = child.stat()
                except FileNotFoundError:
                    continue
                if not _is_evictable(now, stat.st_mtime, ttl_seconds):
                    continue
                size = stat.st_size
                try:
                    child.unlink()
                except FileNotFoundError:
                    continue
                entries_evicted += 1
                bytes_reclaimed += size

        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        result = CacheGcResult(
            entries_evicted=entries_evicted,
            bytes_reclaimed=bytes_reclaimed,
            cache_dir=self.cache_dir,
            ttl_days=ttl_days,
            duration_ms=duration_ms,
            wall_clock_iso=wall_clock_iso,
        )
        if self._event_emitter is not None:
            self._event_emitter(CacheGcCompletedEvent.from_result(result, trigger="amortized"))
        return result

    def run_amortized(self) -> CacheGcResult | None:
        """Run :meth:`run` iff > 24h has elapsed since the last stamp.

        Acquires ``fcntl.flock(LOCK_EX)`` on
        ``<cache_dir>/.gc-stamp.lock`` for the entire read-stamp /
        decide / run / write-stamp critical section. Returns ``None``
        if the previous run is within 24 hours; otherwise calls
        :meth:`run`, atomically updates ``.gc-stamp`` with
        ``time.time()`` and returns the result.

        A future-dated stamp is treated as stale (clock-skew
        resilience). A corrupt stamp raises :class:`BundleCacheRaise`
        with ``reason="corrupt_gc_stamp"`` (Rule 12).
        """
        self.cache_dir.absolute.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.cache_dir, _DIR_MODE)
        except (FileNotFoundError, PermissionError):
            pass
        lock_path = self.cache_dir / _GC_STAMP_LOCK_FILENAME
        stamp_path = self.cache_dir / _GC_STAMP_FILENAME

        lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, _FILE_MODE)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            last_stamp = self._read_stamp(stamp_path)
            now = time.time()
            if not _should_run_amortized(now, last_stamp, _AMORTIZATION_SECONDS):
                return None
            result = self.run()
            _atomic_write_text(stamp_path, repr(time.time()))
            return result
        finally:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)

    @staticmethod
    def _read_stamp(stamp_path: Path) -> float:
        """Return the float seconds in ``.gc-stamp``, or ``0.0`` if absent.

        A non-parseable body raises :class:`BundleCacheRaise` with
        ``reason="corrupt_gc_stamp"``.
        """
        try:
            content = stamp_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return 0.0
        try:
            return float(content)
        except ValueError as exc:
            raise BundleCacheRaise(
                BundleCacheErrorModel(
                    reason="corrupt_gc_stamp",
                    details={"content": content[:32]},
                )
            ) from exc
