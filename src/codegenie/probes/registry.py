"""Probe registry — explicit-imports collection point (ADR-0007, S2-05, 02-ADR-0003).

The registry is the single place probes are collected. Probes opt in via the
:func:`register_probe` decorator at module import time; there is **no**
``importlib.metadata`` entry-point scan (perf — keeps the CLI cold-start path
clean — and supply-chain hygiene: a third-party package can't slip a probe in
by declaring an entry point).

:class:`Registry` is the data structure; :data:`default_registry` is the
process-wide instance the decorator targets. Tests construct independent
:class:`Registry` instances so they don't pollute each other.

:meth:`Registry.for_task` is the Phase 0/1 dispatch primitive. It filters the
registered probes by ``applies_to_tasks`` and ``applies_to_languages``,
treating ``["*"]`` as "match any" per the contract pinned in
``docs/phases/00-bullet-tracer-foundations/phase-arch-design.md §Component
design — Probe + Registry``. Results are cached via a module-level
``functools.lru_cache`` helper (:func:`_filter`); caching on a bound method
would store ``self`` in the cache and leak the registry, so the cache lives
at module scope and the method delegates to it.

S1-08 (02-ADR-0003): the registry now stores per-entry scheduling annotations
(`heaviness`, `runs_last`) alongside each probe class. These annotations are
*data on the registry entry*, NOT fields on the :class:`Probe` ABC — the
Phase 0 contract freeze is preserved. :meth:`Registry.sorted_for_dispatch`
returns entries ordered ``heavy → medium → light`` then any
``runs_last=True`` entries in the same per-heaviness order at the tail.
``runs_last`` dominates ``heaviness``: a ``runs_last=True heaviness="light"``
probe still runs after a ``runs_last=False heaviness="heavy"`` probe.

``Probe.version`` is a *convention*, not part of the frozen ABC (ADR-0007 +
S2-02 snapshot). Every probe class declares ``version`` as a class attribute;
the registry doesn't enforce this at registration time because (a) S3-01's
``cache_key`` reading ``cls.version`` is what surfaces the gap, and (b)
adding a runtime check here without first amending the ABC would create a
contract-drift trap.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, overload

from codegenie.errors import ProbeError
from codegenie.probes.base import Probe

__all__ = [
    "Heaviness",
    "ProbeRegEntry",
    "Registry",
    "_HEAVINESS_RANK",
    "default_registry",
    "register_probe",
]

Heaviness = Literal["light", "medium", "heavy"]

# Lower rank dispatches first. ``runs_last`` is layered on top of this rank;
# the partition (False, True) is applied before the rank tie-break.
_HEAVINESS_RANK: dict[Heaviness, int] = {"heavy": 0, "medium": 1, "light": 2}


@dataclass(frozen=True)
class ProbeRegEntry:
    """One row in the registry: the probe class plus its scheduling
    annotations.

    ``registration_index`` is the stable-sort tie-breaker — ties within a
    ``(runs_last, heaviness)`` bucket preserve the order the entries were
    registered in. Cache keys and golden files depend on this determinism.

    Field names are chosen to survive a future rule-of-three kernel extract
    (`KernelRegistryEntry[K, V]` — queued by ``src/codegenie/indices/registry.py:26``
    once S1-10 lands the third precedent).
    """

    cls: type[Probe]
    heaviness: Heaviness
    runs_last: bool
    registration_index: int


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


def _sort_entries(entries: tuple[ProbeRegEntry, ...]) -> tuple[ProbeRegEntry, ...]:
    """Sort entries: ``runs_last=False`` first, ``runs_last=True`` last; within
    each partition, ``heavy → medium → light``; ties by ``registration_index``.

    Python's ``sorted`` is stable, so equal sort keys preserve input order.
    The two-pass split + extend rather than a single key on
    ``(runs_last, heaviness_rank, registration_index)`` is functionally
    identical but the explicit split is the load-bearing invariant the story
    documents (AC-3 + AC-13), and matching the prose 1:1 makes the code grep-able.
    """
    non_last = sorted(
        (e for e in entries if not e.runs_last),
        key=lambda e: (_HEAVINESS_RANK[e.heaviness], e.registration_index),
    )
    last = sorted(
        (e for e in entries if e.runs_last),
        key=lambda e: (_HEAVINESS_RANK[e.heaviness], e.registration_index),
    )
    return tuple(non_last + last)


class Registry:
    """Ordered, deduplicated-by-name collection of :class:`Probe` subclasses
    with scheduling annotations (heaviness, runs_last) per entry."""

    def __init__(self) -> None:
        self._entries: list[ProbeRegEntry] = []
        self._counter: int = 0

    def register(
        self,
        cls: type[Probe],
        *,
        heaviness: Heaviness = "light",
        runs_last: bool = False,
    ) -> type[Probe]:
        """Register a probe class with optional scheduling annotations.

        Duplicate ``cls.name`` raises :class:`ProbeError`. Returns the class
        unchanged so this method is usable as a decorator. Duplicate
        detection runs at registration time (i.e., module import) so
        misconfiguration fails loud at startup, never silently at dispatch.
        """
        for existing in self._entries:
            if existing.cls.name == cls.name:
                raise ProbeError(
                    f"duplicate probe name {cls.name!r}: "
                    f"{existing.cls.__module__}.{existing.cls.__qualname__} "
                    f"and {cls.__module__}.{cls.__qualname__}"
                )
        self._entries.append(
            ProbeRegEntry(
                cls=cls,
                heaviness=heaviness,
                runs_last=runs_last,
                registration_index=self._counter,
            )
        )
        self._counter += 1
        return cls

    def decorator(
        self,
        *,
        heaviness: Heaviness = "light",
        runs_last: bool = False,
    ) -> Callable[[type[Probe]], type[Probe]]:
        """Return a class decorator that registers into this registry with the
        given scheduling annotations.

        Used by tests to register into ad-hoc :class:`Registry` instances
        without monkeypatching :data:`default_registry`.
        """

        def _wrap(cls: type[Probe]) -> type[Probe]:
            return self.register(cls, heaviness=heaviness, runs_last=runs_last)

        return _wrap

    def all_probes(self) -> tuple[type[Probe], ...]:
        """Return every registered probe class in registration order.

        Preserved verbatim from Phase 0/1 — many existing tests and the
        ``codegenie.indices.registry`` symmetry note (`indices/registry.py:131`)
        depend on this signature.
        """
        return tuple(e.cls for e in self._entries)

    def for_task(self, task: str, languages: frozenset[str]) -> tuple[type[Probe], ...]:
        """Return probes whose filter attrs admit ``task`` and ``languages``.

        See :func:`_filter` for the filter rules and ``["*"]`` semantics.
        Unchanged Phase 0/1 surface — does NOT apply heaviness/runs_last
        sorting (callers that want the sorted form use
        :meth:`sorted_for_task`).
        """
        return _filter(tuple(e.cls for e in self._entries), task, languages)

    def sorted_for_dispatch(self) -> tuple[ProbeRegEntry, ...]:
        """Return every registered entry in coordinator-dispatch order.

        Order:
        - First: every entry with ``runs_last=False``, ordered
          ``heavy → medium → light``; ties broken by registration order.
        - Last: every entry with ``runs_last=True``, ordered
          ``heavy → medium → light``; ties broken by registration order.

        A ``runs_last=True heaviness="light"`` probe still runs after a
        ``runs_last=False heaviness="heavy"`` probe — ``runs_last`` dominates
        ``heaviness``. (02-ADR-0003 §Decision + §Consequences.)
        """
        return _sort_entries(tuple(self._entries))

    def sorted_for_task(self, task: str, languages: frozenset[str]) -> tuple[ProbeRegEntry, ...]:
        """Filter by ``applies_to_*`` (same rules as :meth:`for_task`) then
        sort by :meth:`sorted_for_dispatch`'s ordering.

        Convenience for callers that need both filter and dispatch order in
        one call. The dispatch-side seam (``cli._seam_registry_for_task``)
        uses :meth:`sorted_for_dispatch` directly today because the seam's
        pre-gather filter input is always ``"*"`` (no language inference
        before the prelude runs).
        """
        cls_set = set(_filter(tuple(e.cls for e in self._entries), task, languages))
        filtered = tuple(e for e in self._entries if e.cls in cls_set)
        return _sort_entries(filtered)


default_registry = Registry()


# Dual-shape decorator: bare ``@register_probe`` (Phase 0/1, no parens) AND
# ``@register_probe(heaviness="heavy", runs_last=True)`` (Phase 2). The cls
# argument is positional-only so the bare form binds it; the kwargs form
# leaves ``cls`` at its sentinel and returns the wrap closure.
@overload
def register_probe(cls: type[Probe], /) -> type[Probe]: ...


@overload
def register_probe(
    *,
    heaviness: Heaviness = "light",
    runs_last: bool = False,
) -> Callable[[type[Probe]], type[Probe]]: ...


def register_probe(
    cls: type[Probe] | None = None,
    *,
    heaviness: Heaviness = "light",
    runs_last: bool = False,
) -> type[Probe] | Callable[[type[Probe]], type[Probe]]:
    """Decorator sugar for :meth:`Registry.register` on :data:`default_registry`.

    Two shapes:
    - ``@register_probe`` (no parens, Phase 0/1) — registers with defaults
      ``heaviness="light"``, ``runs_last=False``.
    - ``@register_probe(heaviness=..., runs_last=...)`` — registers with the
      specified scheduling annotations.

    The bare form passes the class as the first positional argument; the
    factory form leaves ``cls`` ``None`` and returns the wrap closure.
    """
    if cls is not None:
        return default_registry.register(cls)
    return default_registry.decorator(heaviness=heaviness, runs_last=runs_last)
