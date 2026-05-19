"""``FeedRegistry`` + ``@register_vuln_feed`` decorator — S3-03 Open/Closed seam.

Mirrors :mod:`codegenie.indices.registry`'s shape (``FreshnessRegistry`` +
``register_index_freshness_check``) and :mod:`codegenie.depgraph.registry`
(``DepGraphRegistry`` + ``register_dep_graph_strategy``). Three peers at
rule-of-three threshold — CLAUDE.md "Open/Closed seams". Adding a Phase 4+
feed = new ``feeds/<source>.py`` module + one explicit-import row in
``vuln_index/__init__.py``.

The registry is the single source of truth for:

- CLI ``--source`` choices (``default_feed_registry.feed_sources()``).
- ``--source all`` iteration order (``sorted`` ASC; determinism for digest).
- Per-feed dispatch through ``get_feed(source)`` — feed classes are
  instantiated lazily on first ``get_feed`` call.

ADRs: phase-3 ADR-0010 (Open/Closed at the file boundary); production
ADR-0033 (newtype identifiers — ``FeedSource`` is a closed-Literal sum type
on the protocol surface).
"""

from __future__ import annotations

from collections.abc import Callable

import structlog

from codegenie.vuln_index.protocol import Feed

__all__ = [
    "FeedRegistry",
    "FeedRegistryError",
    "default_feed_registry",
    "register_vuln_feed",
]


class FeedRegistryError(RuntimeError):
    """Raised on duplicate :func:`register_vuln_feed` decoration.

    Programming error — surfaces at module-import time so a misconfigured
    plugin tree fails loud rather than silently shadowing. Mirrors the
    :class:`codegenie.errors.FreshnessRegistryError` precedent.
    """


_log = structlog.get_logger(__name__)


class FeedRegistry:
    """Ordered, deduplicated-by-source collection of :class:`Feed` classes.

    Tests construct independent :class:`FeedRegistry` instances (or use the
    ``_test_register_feed`` fixture helper in
    :mod:`tests/unit/vuln_index/conftest`) to avoid polluting the
    module-level :data:`default_feed_registry` singleton.
    """

    def __init__(self) -> None:
        self._classes: dict[str, type[Feed]] = {}
        self._instances: dict[str, Feed] = {}
        self._origins: dict[str, str] = {}

    def register(
        self,
        source: str,
    ) -> Callable[[type[Feed]], type[Feed]]:
        """Return a decorator that registers ``cls`` under ``source``.

        The decorator returns ``cls`` unchanged. Duplicate ``source`` raises
        :class:`FeedRegistryError` whose message names both call sites as
        dotted ``module.qualname`` strings.
        """

        def _decorator(cls: type[Feed]) -> type[Feed]:
            origin = f"{cls.__module__}.{cls.__qualname__}"
            if source in self._classes:
                prior = self._origins[source]
                raise FeedRegistryError(f"duplicate feed source {source!r}: {prior} and {origin}")
            self._classes[source] = cls
            self._origins[source] = origin
            _log.debug("vuln_index.feed.registered", source=source, origin=origin)
            return cls

        return _decorator

    def feed_sources(self) -> tuple[str, ...]:
        """Return sorted-ASC tuple of registered feed source names.

        Sort order is **load-bearing** for digest determinism (AC-D2):
        ``refresh --source all`` iterates in this order regardless of
        registration order.
        """
        return tuple(sorted(self._classes))

    def get_feed(self, source: str) -> Feed:
        """Return the registered feed instance for ``source``.

        Lazy instantiation: ``cls()`` is called the first time a given
        source is requested; subsequent calls return the same instance.
        Unregistered ``source`` raises :class:`KeyError`.
        """
        if source not in self._instances:
            self._instances[source] = self._classes[source]()
        return self._instances[source]

    def has_feed(self, source: str) -> bool:
        return source in self._classes

    def _test_unregister(self, source: str) -> None:
        """**Test-only** helper — drop a registration without raising.

        The deliberately-awkward name marks this as test-only. Production
        code paths NEVER unregister.
        """
        self._classes.pop(source, None)
        self._instances.pop(source, None)
        self._origins.pop(source, None)


default_feed_registry = FeedRegistry()


def register_vuln_feed(source: str) -> Callable[[type[Feed]], type[Feed]]:
    """Convenience decorator targeting :data:`default_feed_registry`.

    Equivalent to ``default_feed_registry.register(source)``. Feed modules
    decorate their class with ``@register_vuln_feed("nvd")`` (etc.) at
    import time; ``vuln_index/__init__.py``'s explicit imports drive the
    registration order.
    """
    return default_feed_registry.register(source)
