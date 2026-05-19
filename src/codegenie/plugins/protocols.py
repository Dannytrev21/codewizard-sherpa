"""Phase 3 plugin contract — frozen :class:`Plugin` Protocol + sibling
:class:`Adapter` / :class:`RecipeEngine` Protocols.

The :class:`Plugin` surface is **exactly four** members
(``manifest``, ``build_subgraph``, ``adapters``, ``transforms``) — the
load-bearing freeze Phase-3 ADR-0004 §Consequences names. The fence
``tests/fence/test_plugin_protocol_frozen.py`` asserts the count: drift
fails CI loudly. Task-class-specific knowledge (CVE feed parsers,
Dockerfile policies) lives on each plugin's TCCM ``provides`` namespace,
NOT on this kernel Protocol — see ADR-0004 §Decision.

:class:`Adapter` and :class:`RecipeEngine` are shipped with the minimum
surface S2-01 needs; their freeze is deferred to S7 / Step 5
(per S2-01 Out-of-scope). The fence test in this story covers ``Plugin``
only.

All three Protocols are :func:`typing.runtime_checkable` — the
``@runtime_checkable`` performance cost is paid at test-fixture time, not
on any production hot path (registration is import-time;
``isinstance`` against these Protocols only fires in tests).

Why **forward references everywhere**: ``codegenie.plugins.protocols`` is
the kernel; importing concrete types (``PluginManifest``,
:class:`codegenie.plugins.scope.PluginScope`, the recipe-time types) at
module-import would couple the kernel to non-kernel packages and trip
the Phase 3 import-linter contracts. ``from __future__ import
annotations`` defers every annotation to a string; ``TYPE_CHECKING``
imports stay invisible at runtime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from codegenie.plugins.registry import PluginRegistry
    from codegenie.types.identifiers import PluginId, PrimitiveName, TransformKind

    # S2-02 ships PluginManifest. Forward-ref stub carries the one field
    # the S2-01 registry's collision check reads (``manifest.name``); S2-02
    # replaces the stub with the full Pydantic model.
    class PluginManifest:  # pragma: no cover - forward-ref stub
        name: PluginId

    # S2-04 ships the resolver and the PluginSubgraph node-graph type.
    class PluginSubgraph:  # pragma: no cover - forward-ref stub
        ...

    # S3-01/S3-02 ship the CveRecord + Bundle types consumed by recipes.
    class CveRecord:  # pragma: no cover - forward-ref stub
        ...

    class Bundle:  # pragma: no cover - forward-ref stub
        ...

    class Applicability:  # pragma: no cover - forward-ref stub
        ...

    # S5 ships the recipe-time types.
    class RecipePlan:  # pragma: no cover - forward-ref stub
        ...

    class ApplyContext:  # pragma: no cover - forward-ref stub
        ...

    class RecipeOutcome:  # pragma: no cover - forward-ref stub
        ...


__all__ = ["Adapter", "Plugin", "RecipeEngine"]


@runtime_checkable
class Adapter(Protocol):
    """Adapter Protocol — minimum surface S2-01 needs.

    Method surface (language search, file write-back, etc.) lands with the
    first concrete adapter in S7 (per Phase-3 ADR-0032). This surface is
    **not** fence-frozen in S2-01 — Out-of-scope of this story.
    """

    primitive: PrimitiveName


@runtime_checkable
class RecipeEngine(Protocol):
    """Recipe-engine Protocol — minimum surface Step 5 consumers need.

    The ``applies`` / ``apply`` signatures ship here so the S5 ``Plugin``
    field-type annotation resolves at story time. The surface is **not**
    fence-frozen in S2-01 — Step 5 owns the freeze.
    """

    kind: TransformKind

    def applies(self, cve: CveRecord, bundle: Bundle) -> Applicability:
        """Cheap predicate: does this engine think it can fix ``cve``
        inside ``bundle``?"""
        ...

    async def apply(self, plan: RecipePlan, ctx: ApplyContext) -> RecipeOutcome:
        """Run the engine; produce a structured outcome."""
        ...


# AC-8 — runtime_checkable; see test_runtime_checkable_protocols_match_fakes.
@runtime_checkable
class Plugin(Protocol):
    """Kernel ``Plugin`` Protocol — exactly four members (ADR-0004).

    The fence test ``tests/fence/test_plugin_protocol_frozen.py`` pins
    this surface; adding a fifth member or removing one fails CI.

    Task-class-specific capabilities (CVE feed parsers, Dockerfile
    policies, etc.) live on each plugin's TCCM ``provides`` namespace —
    NOT on this Protocol. Phase 7 distroless lands with zero edits to
    this file (ADR-0004 §Consequences for Phase 4 / Phase 7).
    """

    manifest: PluginManifest

    def build_subgraph(self, registry: PluginRegistry) -> PluginSubgraph:
        """Return the plugin's per-task-class subgraph.

        Wired into the orchestrator's pipeline at workflow build time.
        Implementations are expected to be cheap (data composition only);
        no I/O, no network, no subprocess.
        """
        ...

    def adapters(self) -> dict[PrimitiveName, Adapter]:
        """Return the plugin's primitive → adapter map.

        Each adapter implements one primitive operation
        (language search, file write-back, etc.) — see S7 for the full
        primitive taxonomy.
        """
        ...

    def transforms(self) -> dict[TransformKind, RecipeEngine]:
        """Return the plugin's transform-kind → recipe-engine map.

        Step 5's recipe registry dispatches by ``TransformKind`` against
        the union of every plugin's returned map.
        """
        ...
