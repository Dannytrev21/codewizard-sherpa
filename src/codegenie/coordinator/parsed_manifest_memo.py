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
  — design rationale; key = ``(absolute_path, mtime_ns, size)`` for TOCTOU
  safety in S1-07; key flips to ``(content_hash,)`` in S1-08 once
  ``ctx.input_snapshot`` lands.
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
        self._cache: dict[tuple[str, int, int], MappingProxyType[str, Any]] = {}

    def get(self, path: Path) -> Mapping[str, Any] | None:
        """Return the parsed manifest at ``path`` or ``None`` if non-memoizable.

        Returns ``None`` when (a) ``path.name`` is not in the allowlist
        (case-sensitive) or (b) ``path.stat()`` raises
        :class:`FileNotFoundError`. Any other ``OSError`` (e.g.,
        :class:`PermissionError`) propagates unchanged. The four typed parser
        exceptions raised by :func:`safe_json.load` —
        :class:`codegenie.errors.MalformedJSONError`,
        :class:`codegenie.errors.SizeCapExceeded`,
        :class:`codegenie.errors.DepthCapExceeded`,
        :class:`codegenie.errors.SymlinkRefusedError` — propagate and the
        cache is left untouched.
        """
        if path.name not in self._allowlist:
            return None
        try:
            st = path.stat()
        except FileNotFoundError:
            return None
        # Other OSError subclasses (PermissionError, etc.) propagate.

        # S1-08: key flips to (content_hash,) sourced from ctx.input_snapshot,
        # closing the TOCTOU window between stat() and safe_json.load().
        key = (str(path.resolve()), st.st_mtime_ns, st.st_size)

        hit = self._cache.get(key)
        if hit is not None:
            _logger.info("probe.memo.hit", path=key[0], allowlist_match=path.name)
            return hit

        parsed = safe_json.load(path, max_bytes=_MAX_BYTES)  # may raise; do not cache on failure
        wrapped: MappingProxyType[str, Any] = MappingProxyType(parsed)
        self._cache[key] = wrapped
        _logger.info("probe.memo.miss", path=key[0], allowlist_match=path.name)
        return wrapped
