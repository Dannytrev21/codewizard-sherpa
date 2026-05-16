"""``codegenie.indices.registry`` — decorator-registry for index freshness checks.

The Open/Closed seam for **new index sources**: each Phase-2 (and Phase-3+)
index source registers a tiny ``(slice, head) -> IndexFreshness`` function
via :func:`register_index_freshness_check`;
``codegenie.probes.layer_b.index_health.IndexHealthProbe`` (B2, S4-01) loops
the registry instead of switching on index name. Adding a new index source
must require **zero edits** to this module,
``codegenie.probes.layer_b.index_health``, or ``codegenie.indices.__init__``.

Architecture sources:

- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md §"Gap 3"``
  — names the coupling this registry breaks.
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0006-index-freshness-sum-type-location.md``
  (02-ADR-0006) — pins the variant set and discriminator strings of the
  ``IndexFreshness`` value type.

Location deviation from 02-ADR-0006: the ADR's §Consequences bullet says the
decorator-registry lives "in ``freshness.py``", but this module lands it in
``registry.py`` to keep ``freshness.py`` pure data and avoid a circular
import once the registry imports ``IndexFreshness``. The deviation is
intentional and bounded by the ADR's "ADR amendment optional only if
friction arises" allowance.

Rule-of-three observation: this is the 2nd registry of the decorator-registry
family in this phase (``codegenie.probes.registry`` is the 1st precedent;
``codegenie.depgraph.registry`` at S1-10 will be the 3rd). The kernel-extract
opportunity (a shared ``KernelRegistry[K, V]`` base + per-registry typed
errors) crosses the rule-of-three threshold when S1-10 lands; this story
intentionally does **not** pre-extract (Rule 2 — simplicity first).

The :data:`FreshnessCheck` alias is intentionally lenient — Phase 0's
``codegenie.output.sanitizer`` does not export a ``JSONValue`` recursive
type alias today (the writer chokepoint takes ``dict[str, Any]``). The
structural fallback is ``dict[str, object]`` — "Pydantic-serializable JSON
payload". If a later story promotes ``JSONValue`` to a public alias, this
module will rebind the inner type **by import**, never by redefinition; the
contract surface (signature shape) does not change.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import structlog

from codegenie.errors import FreshnessRegistryError

if TYPE_CHECKING:
    from codegenie.indices.freshness import IndexFreshness

    # ``IndexName`` is a ``NewType("IndexName", str)`` — identity-to-``str`` at
    # runtime, so we never need the symbol at runtime in this module. Pulling
    # it in eagerly would trip the import cycle that crystallizes once
    # ``codegenie.probes.__init__`` transitively triggers a Phase 2 layer-B
    # probe whose own imports come back through this very module:
    #     types.identifiers → probes.node_build_system → probes/__init__
    #     → probes.layer_b.index_health → indices.registry (mid-load) → BOOM
    # Type-checking-only import keeps the cycle broken without losing
    # nominal typing (mypy still treats ``IndexName`` as distinct from
    # ``str`` under ``--strict``).
    from codegenie.types.identifiers import IndexName

# JSONValue forward-reference is intentionally lenient. See module docstring.
FreshnessCheck = Callable[[dict[str, object], str], "IndexFreshness"]

_log = structlog.get_logger(__name__)


__all__ = [
    "FreshnessCheck",
    "FreshnessRegistry",
    "FreshnessRegistryError",
    "default_freshness_registry",
    "register_index_freshness_check",
]


class FreshnessRegistry:
    """Ordered, deduplicated-by-name collection of :data:`FreshnessCheck` functions.

    Mirrors the shape of :class:`codegenie.probes.registry.Registry`: duplicate
    names raise :class:`FreshnessRegistryError` at decoration time (i.e., module
    import) so misconfiguration fails loud at startup, never silently at
    dispatch. Tests construct independent :class:`FreshnessRegistry` instances
    so they do not pollute each other; the module-level
    :data:`default_freshness_registry` is the process-wide instance the
    convenience decorator targets.

    The registry is **the source of truth for *expected* indices**: every
    registered check appears in :meth:`dispatch_all` output even when the
    coordinator did not provide a matching slice (the check is invoked with
    an empty dict and is responsible for emitting an
    ``IndexFreshness.Stale(IndexerError(...))``; the upstream-degraded
    decision lives in S4-01's ``IndexHealthProbe``, not here).
    """

    def __init__(self) -> None:
        self._checks: dict[IndexName, FreshnessCheck] = {}
        # Origin strings ("module.qualname") are kept alongside so duplicate
        # errors can name BOTH call sites without re-introspecting the prior
        # function (which a caller could have mutated).
        self._origins: dict[IndexName, str] = {}

    def register(
        self,
        index_name: IndexName,
    ) -> Callable[[FreshnessCheck], FreshnessCheck]:
        """Return a decorator that registers ``fn`` under ``index_name``.

        The decorator returns ``fn`` unchanged so registration is non-invasive
        (``reg.register(name)(fn) is fn``). Duplicate ``index_name`` raises
        :class:`FreshnessRegistryError` whose message names both call sites
        as dotted ``module.qualname`` strings so an operator grepping a
        multi-file plugin tree can locate both registrations from the
        message alone.
        """

        def _decorator(fn: FreshnessCheck) -> FreshnessCheck:
            origin = f"{fn.__module__}.{fn.__qualname__}"
            if index_name in self._checks:
                prior = self._origins[index_name]
                raise FreshnessRegistryError(
                    f"duplicate index_name {index_name!r}: {prior} and {origin}"
                )
            self._checks[index_name] = fn
            self._origins[index_name] = origin
            _log.debug(
                "indices.freshness_check.registered",
                index_name=index_name,
                origin=origin,
            )
            return fn

        return _decorator

    def registered_names(self) -> frozenset[IndexName]:
        """Return the set of registered index names (unordered).

        Symmetric with :meth:`codegenie.probes.registry.Registry.all_probes`'s
        public-surface role: callers use this to enumerate the registry without
        reaching through ``_checks``. Iteration order is **not** guaranteed
        here — :meth:`dispatch_all`'s output ordering carries the audit-chain
        contract.
        """
        return frozenset(self._checks)

    def dispatch_all(
        self,
        slices: dict[IndexName, dict[str, object]],
        head: str,
    ) -> dict[IndexName, IndexFreshness]:
        """Invoke every registered check; return ``{name: freshness, ...}``.

        Total over the registry (every registered name appears in the result).
        For each registered name, the check is called with
        ``slices.get(name, {})`` and the unchanged ``head`` value — no
        coercion, no slicing. ``head`` is passed positionally; the slice/head
        argument-swap is a plausible silent mutation pinned by AC-12.

        Iteration order is **registration order** (``dict`` insertion-order
        semantics, Python ≥ 3.7). Audit-chain hashing (Phase 0 ADR / S3-06)
        depends on byte-stable outputs; do not sort, ``frozenset()``, or
        otherwise re-permute the registered names inside this method.

        Exceptions raised by a check propagate unchanged — by contract a
        well-behaved check returns a typed freshness value (constructing a
        ``Stale(IndexerError(...))`` for its own internal failures); an
        exception escaping a check is a bug, and the coordinator at S4-01
        is the right place to catch (Phase 0 coordinator-isolation precedent).
        """
        return {name: check(slices.get(name, {}), head) for name, check in self._checks.items()}

    def dispatch_one(
        self,
        name: IndexName,
        slices: dict[IndexName, dict[str, object]],
        head: str,
    ) -> IndexFreshness:
        """Invoke a single registered check by name; return its freshness.

        Used by ``IndexHealthProbe`` (S4-01, AC-8) as the per-name fallback
        when :meth:`dispatch_all` raises — the call site wraps each
        invocation in its own ``try`` so one misbehaving check cannot poison
        the whole map. Exceptions from the underlying check still propagate
        unchanged (the **caller** is responsible for wrapping); this method
        is mechanically the same single-name lookup ``dispatch_all`` performs
        per-iteration, exposed as a public surface so the failure-isolation
        site at S4-01 does not need to reach into ``_checks`` directly.

        Added in S4-01 (additive). No existing callers of
        :meth:`dispatch_all` are affected.
        """
        return self._checks[name](slices.get(name, {}), head)

    def unregister_for_tests(self, index_name: IndexName) -> None:
        """**Test-only** convenience for cleaning the module-level singleton.

        The deliberately-awkward name *is* the policy — production code paths
        do not unregister. Two tests in
        ``tests/unit/indices/test_freshness_registry.py`` call this in a
        ``finally:`` block to avoid polluting downstream tests in the same
        process when verifying the module-level singleton's wiring.
        """
        self._checks.pop(index_name, None)
        self._origins.pop(index_name, None)


default_freshness_registry = FreshnessRegistry()


def register_index_freshness_check(
    index_name: IndexName,
) -> Callable[[FreshnessCheck], FreshnessCheck]:
    """Convenience decorator targeting :data:`default_freshness_registry`.

    Equivalent to ``default_freshness_registry.register(index_name)``; the
    indirection exists so probe modules can spell the registration without
    importing the singleton by name.
    """
    return default_freshness_registry.register(index_name)
