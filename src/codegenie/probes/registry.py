"""Probe registry — explicit-imports collection point (ADR-0007, S2-05).

The registry is the single place probes are collected. Probes opt in via the
:func:`register_probe` decorator at module import time; there is **no**
``importlib.metadata`` entry-point scan (perf — keeps the CLI cold-start path
clean — and supply-chain hygiene: a third-party package can't slip a probe in
by declaring an entry point).

:class:`Registry` is the data structure; :data:`default_registry` is the
process-wide instance the decorator targets. Tests construct independent
:class:`Registry` instances so they don't pollute each other.

:meth:`Registry.for_task` is the coordinator's dispatch primitive. It filters
the registered probes by ``applies_to_tasks`` and ``applies_to_languages``,
treating ``["*"]`` as "match any" per the contract pinned in
``docs/phases/00-bullet-tracer-foundations/phase-arch-design.md §Component
design — Probe + Registry``. Results are cached via a module-level
``functools.lru_cache`` helper (:func:`_filter`); caching on a bound method
would store ``self`` in the cache and leak the registry, so the cache lives
at module scope and the method delegates to it.

``Probe.version`` is a *convention*, not part of the frozen ABC (ADR-0007 +
S2-02 snapshot). Every probe class declares ``version`` as a class attribute;
the registry doesn't enforce this at registration time because (a) S3-01's
``cache_key`` reading ``cls.version`` is what surfaces the gap, and (b)
adding a runtime check here without first amending the ABC would create a
contract-drift trap.
"""

from __future__ import annotations

import functools

from codegenie.errors import ProbeError
from codegenie.probes.base import Probe

__all__ = ["Registry", "default_registry", "register_probe"]


@functools.lru_cache(maxsize=32)
def _filter(
    probes: tuple[type[Probe], ...],
    task: str,
    languages: frozenset[str],
) -> tuple[type[Probe], ...]:
    """Return the subset of ``probes`` matching ``task`` and ``languages``.

    ``["*"]`` in either attribute is "match any". When ``applies_to_languages``
    is a concrete list, a probe matches if the intersection with ``languages``
    is non-empty. Cached on the (probes-tuple, task, languages) tuple — the
    coordinator calls ``for_task`` once per dispatch but unit tests call it
    repeatedly; the cache makes the second call free.
    """
    result: list[type[Probe]] = []
    for cls in probes:
        if "*" not in cls.applies_to_tasks and task not in cls.applies_to_tasks:
            continue
        if "*" not in cls.applies_to_languages:
            if not (set(cls.applies_to_languages) & languages):
                continue
        result.append(cls)
    return tuple(result)


class Registry:
    """Ordered, deduplicated-by-name collection of :class:`Probe` subclasses."""

    def __init__(self) -> None:
        self._probes: list[type[Probe]] = []

    def register(self, cls: type[Probe]) -> type[Probe]:
        """Register a probe class. Duplicate ``cls.name`` raises :class:`ProbeError`.

        Returns the class unchanged so this method is usable as a decorator.
        Duplicate detection runs at decoration time (i.e., module import) so
        misconfiguration fails loud at startup, never silently at dispatch.
        """
        for existing in self._probes:
            if existing.name == cls.name:
                raise ProbeError(
                    f"duplicate probe name {cls.name!r}: "
                    f"{existing.__module__}.{existing.__qualname__} "
                    f"and {cls.__module__}.{cls.__qualname__}"
                )
        self._probes.append(cls)
        return cls

    def all_probes(self) -> tuple[type[Probe], ...]:
        """Return every registered probe class in registration order."""
        return tuple(self._probes)

    def for_task(self, task: str, languages: frozenset[str]) -> tuple[type[Probe], ...]:
        """Return probes whose filter attrs admit ``task`` and ``languages``.

        See :func:`_filter` for the filter rules and ``["*"]`` semantics.
        """
        return _filter(tuple(self._probes), task, languages)


default_registry = Registry()


def register_probe(cls: type[Probe]) -> type[Probe]:
    """Decorator sugar for :meth:`Registry.register` on :data:`default_registry`."""
    return default_registry.register(cls)
