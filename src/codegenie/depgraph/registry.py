"""``codegenie.depgraph.registry`` — decorator-registry for ecosystem-specific
dependency-graph build strategies.

The Open/Closed seam for **new dependency-graph ecosystems** (pnpm, npm,
yarn-classic, yarn-berry, bun today; Maven/Cargo/Gradle later via Phase 1
ADR-0013 amendment). Each ecosystem's strategy registers via
:func:`register_dep_graph_strategy` (or a private
:class:`DepGraphRegistry`); :class:`codegenie.probes.layer_b.dep_graph.DepGraphProbe`
(B5, S4-05) dispatches by ``PackageManager`` Literal instead of switching
on ecosystem name. Adding a new ecosystem must require **zero edits** to
this module, to the probe, or to ``codegenie.depgraph.__init__``.

Architecture sources:

- ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md`` §"Component design" #11.
- ``docs/phases/02-context-gather-layers-b-g/ADRs/0006-index-freshness-sum-type-location.md``
  §Decisions noted — registry symmetry across
  ``@register_index_freshness_check`` (S1-02), ``@register_probe`` (S1-08),
  and ``@register_dep_graph_strategy`` (this story).
- ``docs/production/adrs/0033-typed-identifiers.md`` — ``PackageManager`` is
  the typed registry key (Phase 1 ADR-0013); the registry's
  ``dict[PackageManager, …]`` annotation carries the nominal-type contract
  under ``mypy --strict``.

Phase-3 hand-off: the canonical first consumer is
``plugins/vulnerability-remediation--node--npm/strategies/dep_graph_pnpm.py``
(per ``docs/phases/02-context-gather-layers-b-g/phase-arch-design.md``
§"Integration with Phase 3").

Rule-of-three observation: this is the 3rd registry of the decorator-registry
family in this codebase (``codegenie.probes.registry`` 1st;
``codegenie.indices.registry`` 2nd; this module 3rd). The three sites'
dispatch shapes diverge non-trivially — ``for_task`` filter + LRU /
``dispatch_all`` total / single-``dispatch`` with ``has_strategy`` query —
so per Rule 2 (simplicity first) + Rule 3 (surgical changes) the
kernel-extract is **NOT prescribed in this story** (mirrors S1-02's
deliberate deferral). The opportunity is recorded for a post-Phase-2
cleanup story to evaluate.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

import structlog

from codegenie.errors import DepGraphRegistryError
from codegenie.probes.base import ProbeContext

# DO NOT redefine PackageManager — Phase 1 ADR-0013 owns the enum; the
# kernel-tier alias surface is :mod:`codegenie.types.identifiers` (S1-05
# re-export). Importing from the types package is the canonical interface
# (production ADR-0033 §3).
from codegenie.types.identifiers import PackageManager

if TYPE_CHECKING:
    import networkx

DepGraphStrategy = Callable[[ProbeContext, list[Mapping[str, Any]]], "networkx.DiGraph"]
"""Function shape every ecosystem strategy must satisfy.

The ``manifests`` parameter is ``list[Mapping[str, Any]]`` — Phase 1's
``parsed_manifest`` returns ``Mapping[str, Any] | None`` per
:mod:`codegenie.probes.base` ADR-0002. A future story that promotes
manifests to a Pydantic model rebinds this alias **by ADR amendment**,
never by silent widening (AC-3).
"""

_log = structlog.get_logger(__name__)


__all__ = [
    "DepGraphRegistry",
    "DepGraphRegistryError",
    "DepGraphStrategy",
    "default_dep_graph_registry",
    "register_dep_graph_strategy",
]


class DepGraphRegistry:
    """Per-ecosystem :data:`DepGraphStrategy` collection with duplicate-loud semantics.

    Mirrors the shape of :class:`codegenie.indices.registry.FreshnessRegistry`
    and :class:`codegenie.probes.registry.Registry`: duplicate ecosystem
    registration raises :class:`DepGraphRegistryError` at decoration time
    (i.e., module import) so misconfiguration fails loud at startup, never
    silently at dispatch. Tests construct independent ``DepGraphRegistry``
    instances so they do not pollute each other; the module-level
    :data:`default_dep_graph_registry` is the process-wide instance the
    convenience decorator targets.

    Dispatch contract (AC-4 / AC-11): the registry passes ``ctx`` and
    ``manifests`` positionally and verbatim to the registered strategy, and
    returns the strategy's exact graph object (identity, not a copy or
    wrapper). Defensive serialisation/copy belongs to the writer chokepoint
    (``nx.node_link_data`` at S4-05), not here.
    """

    def __init__(self) -> None:
        self._strategies: dict[PackageManager, DepGraphStrategy] = {}
        # Origin strings ("module.qualname") kept alongside so duplicate
        # errors can name BOTH call sites without re-introspecting the
        # prior function (a caller could have mutated it). Mirrors
        # :mod:`codegenie.indices.registry`.
        self._origins: dict[PackageManager, str] = {}

    def register(self, ecosystem: PackageManager) -> Callable[[DepGraphStrategy], DepGraphStrategy]:
        """Return a decorator that registers ``fn`` under ``ecosystem``.

        The decorator returns ``fn`` unchanged so registration is
        non-invasive (``reg.register(eco)(fn) is fn`` — AC-10). Duplicate
        ``ecosystem`` raises :class:`DepGraphRegistryError` whose message
        names both call sites as dotted ``module.qualname`` strings so an
        operator grepping a multi-file plugin tree can locate both
        registrations from the message alone (AC-2).
        """

        def _decorator(fn: DepGraphStrategy) -> DepGraphStrategy:
            origin = f"{fn.__module__}.{fn.__qualname__}"
            if ecosystem in self._strategies:
                prior = self._origins[ecosystem]
                raise DepGraphRegistryError(
                    f"duplicate ecosystem {ecosystem!r}: {prior} and {origin}"
                )
            self._strategies[ecosystem] = fn
            self._origins[ecosystem] = origin
            _log.debug(
                "depgraph.strategy.registered",
                ecosystem=str(ecosystem),
                origin=origin,
            )
            return fn  # AC-10 — return identity, non-invasive.

        return _decorator

    def has_strategy(self, ecosystem: PackageManager) -> bool:
        """Non-raising membership query (AC-5).

        Used by :class:`DepGraphProbe` (S4-05) to decide whether to dispatch
        or emit a low-confidence slice directly. Total over the
        :data:`PackageManager` Literal — never raises for an unregistered
        Literal value.
        """
        return ecosystem in self._strategies

    def dispatch(
        self,
        ecosystem: PackageManager,
        ctx: ProbeContext,
        manifests: list[Mapping[str, Any]],
    ) -> networkx.DiGraph:
        """Invoke the registered strategy for ``ecosystem``.

        Returns the strategy's exact :class:`networkx.DiGraph` (AC-4, AC-11)
        — no defensive copy, no wrapper. Unknown ecosystem raises
        :class:`DepGraphRegistryError` whose ``args[0]`` begins with the
        literal prefix ``no_strategy_for_ecosystem: `` followed by
        ``repr(ecosystem)``. The prefix is the structural token S4-05's
        probe matches when translating to
        ``DepGraphProbeOutput(confidence="low", reason="no_strategy_for_ecosystem")``.
        """
        try:
            fn = self._strategies[ecosystem]
        except KeyError:
            raise DepGraphRegistryError(f"no_strategy_for_ecosystem: {ecosystem!r}") from None
        # Positional, verbatim — argument-swap or copy-on-pass is a mutation
        # pinned by AC-11.
        return fn(ctx, manifests)

    def registered_ecosystems(self) -> frozenset[PackageManager]:
        """Return the set of registered ecosystems (AC-12).

        Unordered, immutable, non-mutating. Empty on a fresh registry.
        Symmetric with :meth:`FreshnessRegistry.registered_names` and
        :meth:`Registry.all_probes`'s enumeration roles.
        """
        return frozenset(self._strategies)

    def unregister_for_tests(self, ecosystem: PackageManager) -> None:
        """**Test-only** convenience for cleaning the module-level singleton.

        The deliberately-awkward name *is* the policy (mirrors S1-02 /
        :mod:`codegenie.indices.registry`). Production code paths do not
        unregister. Tests that touch :data:`default_dep_graph_registry`
        MUST clean up in a ``finally:`` block to avoid polluting downstream
        tests in the same process (the zero-strategies-in-Phase-2 invariant
        relies on the singleton being empty between tests).
        """
        self._strategies.pop(ecosystem, None)
        self._origins.pop(ecosystem, None)


default_dep_graph_registry = DepGraphRegistry()


def register_dep_graph_strategy(
    ecosystem: PackageManager,
) -> Callable[[DepGraphStrategy], DepGraphStrategy]:
    """Convenience decorator targeting :data:`default_dep_graph_registry`.

    Equivalent to ``default_dep_graph_registry.register(ecosystem)``; the
    indirection exists so ecosystem-strategy modules (Phase 3 plugins) can
    spell the registration without importing the singleton by name.
    """
    return default_dep_graph_registry.register(ecosystem)
