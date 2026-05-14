"""In-coordinator per-gather parse memo for allowlisted manifests.

The memo eliminates 3x ``package.json`` re-parsing across the four Phase 1
``package.json``-consuming probes (``LanguageDetectionProbe`` extended,
``NodeBuildSystemProbe``, ``NodeManifestProbe``, ``TestInventoryProbe``).
It lives entirely in process memory; it never writes to disk and never
crosses ``OutputSanitizer`` or ``_ProbeOutputValidator`` (Phase 0
ADR-0008 / ADR-0010). Per-gather lifetime: the coordinator constructs one
instance at the top of :func:`codegenie.coordinator.coordinator.gather`
and discards it on return — module-level state is rejected on purpose.

References:

- ``docs/phases/01-context-gather-layer-a-node/phase-arch-design.md``
  §"Component design" #3 — full interface, allowlist, lifetime, immutability
  via :class:`types.MappingProxyType`, failure-doesn't-cache semantics.
- ADR-0002 —
  ``docs/phases/01-context-gather-layer-a-node/ADRs/0002-parsed-manifest-memo-on-probe-context.md``
  — design rationale. S1-07 keyed by ``(absolute_path, mtime_ns, size)``;
  S1-08 lands an **additive** ``content_hash`` parameter — when the
  coordinator's adapter passes a snapshot-derived hash, the cache key is
  ``(content_hash,)`` (Gap-1 closure); when omitted (``content_hash=None``)
  the S1-07 stat-tuple key is used unchanged. Sentinels (``"<oversize>"``,
  ``"<refused>"``) bypass the memo entirely (return ``None``, no cache
  entry).
- ``docs/phases/01-context-gather-layer-a-node/final-design.md`` §"Components" #2
  — the explicit rejection of the msgpack side-channel that motivates the
  in-memory-only design.

Design notes:

- **Kernel/policy split (Open/Closed).** The memo kernel knows nothing about
  *which* paths are memoizable; the allowlist is injected via the ``allowlist``
  keyword-only constructor argument. Phase 2's ``IndexHealthProbe`` reuses
  this kernel by constructing with ``frozenset({"package.json", "scip-index.json"})``
  — zero edits to this module.
- **Failure does not cache.** Any exception raised by :func:`safe_json.load`
  propagates unchanged and the cache stays untouched. The next probe retries
  and observes the same error (or a new value if the file was repaired in
  between). Successful parses cache by value-equal key.
- **No deep freezing.** :class:`MappingProxyType` only wraps the top level;
  nested ``dict``/``list`` values are returned by reference. Probes treat
  the result as ``Mapping[str, Any]``-typed and read-only by convention.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final

import structlog

from codegenie.parsers import safe_json

__all__ = ["ParsedManifestMemo"]

_DEFAULT_ALLOWLIST: Final[frozenset[str]] = frozenset({"package.json"})
# 5 MiB — phase-arch-design.md §"Component design" #3.
_MAX_BYTES: Final[int] = 5_242_880

_logger = structlog.get_logger(__name__)


class ParsedManifestMemo:
    """Per-gather memo for allowlisted JSON manifests.

    Not thread-safe; per-gather coordinator scope assumes serial access on
    the event loop. Phase 14 (concurrent gathers under Temporal Activities)
    constructs a fresh memo per Activity, so wrapping the memo with
    :class:`asyncio.Lock` is unnecessary in that model.
    """

    def __init__(self, *, allowlist: frozenset[str] = _DEFAULT_ALLOWLIST) -> None:
        self._allowlist: frozenset[str] = allowlist
        # The cache is keyed by a tagged tuple shape so the dual S1-07 /
        # S1-08 keys coexist without collisions. S1-07's stat-tuple key is
        # ``(absolute_path, mtime_ns, size)``; S1-08's snapshot-derived key
        # is a single-element ``(content_hash,)`` tuple. The two shapes are
        # never value-equal — distinct length AND distinct member types.
        self._cache: dict[tuple[Any, ...], MappingProxyType[str, Any]] = {}

    def get(
        self,
        path: Path,
        *,
        content_hash: str | None = None,
    ) -> Mapping[str, Any] | None:
        """Return the parsed manifest at ``path`` or ``None`` if non-memoizable.

        Returns ``None`` when (a) ``path.name`` is not in the allowlist
        (case-sensitive), (b) ``content_hash`` is a sentinel
        (``"<oversize>"``, ``"<refused>"`` — any string starting with
        ``"<"``; no cache entry is written), or (c) ``path.stat()`` raises
        :class:`FileNotFoundError` on the stat-tuple key path. Any other
        ``OSError`` (e.g., :class:`PermissionError`) propagates unchanged.
        The four typed parser exceptions raised by :func:`safe_json.load` —
        :class:`codegenie.errors.MalformedJSONError`,
        :class:`codegenie.errors.SizeCapExceeded`,
        :class:`codegenie.errors.DepthCapExceeded`,
        :class:`codegenie.errors.SymlinkRefusedError` — propagate and the
        cache is left untouched.

        S1-08 — when ``content_hash`` is a non-sentinel string, the cache
        key is ``(content_hash,)`` (Gap-1 closure: a file edited mid-gather
        cannot poison the parse of the snapshotted bytes). When omitted,
        the S1-07 ``(absolute_path, mtime_ns, size)`` key is used
        unchanged.
        """
        if path.name not in self._allowlist:
            return None

        # AC-15 — sentinel bypass. Caching a None result under a sentinel
        # key would only serve confusion; the downstream parse would fail
        # anyway. Returns ``None`` and leaves the cache untouched.
        if content_hash is not None and content_hash.startswith("<"):
            return None

        key: tuple[Any, ...]
        log_path: str
        if content_hash is not None:
            key = (content_hash,)
            log_path = str(path)
        else:
            try:
                st = path.stat()
            except FileNotFoundError:
                return None
            # Other OSError subclasses (PermissionError, etc.) propagate.
            log_path = str(path.resolve())
            key = (log_path, st.st_mtime_ns, st.st_size)

        hit = self._cache.get(key)
        if hit is not None:
            _logger.info("probe.memo.hit", path=log_path, allowlist_match=path.name)
            return hit

        parsed = safe_json.load(path, max_bytes=_MAX_BYTES)  # may raise; do not cache on failure
        wrapped: MappingProxyType[str, Any] = MappingProxyType(parsed)
        self._cache[key] = wrapped
        _logger.info("probe.memo.miss", path=log_path, allowlist_match=path.name)
        return wrapped
