"""Phase 3 plugin kernel — instance-based :class:`PluginRegistry` with a
module-level :data:`default_registry` singleton + :func:`register_plugin`
helper.

This is the closed-for-modification kernel ADR-0002 names. Production
code uses the :data:`default_registry`; tests pass fresh
:class:`PluginRegistry` instances via ``register_plugin(p, registry=r)``
to avoid cross-test pollution (ADR-0002 §Decision).

``register_plugin`` is a **function call**, NOT a class decorator.
Plugins are *instances* that carry composed state (manifest, adapters,
recipe engines); the class-decorator shape used by the three sibling
registries (``register_probe``, ``register_index_freshness_check``,
``register_dep_graph_strategy``) would force module-import-time
zero-arg construction, breaking the manifest-carrying contract. ADR-0002
§Decision pins the asymmetry as intentional.

**Rule-of-three observation — now four registries.** This is the **4th**
decorator-registry in the codebase:

1. :mod:`codegenie.probes.registry` (Phase 0 + 02-ADR-0003 amendments) —
   ``for_task`` filter + LRU + ``sorted_for_dispatch``.
2. :mod:`codegenie.indices.registry` (Phase 2 S1-02) — total dispatch via
   ``dispatch_all``.
3. :mod:`codegenie.depgraph.registry` (Phase 2 S1-10) — single dispatch +
   ``has_strategy`` query.
4. :mod:`codegenie.plugins.registry` (this module, Phase 3 S2-01) —
   ``register`` / ``get`` / ``all`` + ``resolve(scope)`` + (in S2-04)
   ``extends``-walk.

Both ``indices/registry.py:26-31`` and ``depgraph/registry.py:30-38``
explicitly document the rule-of-three threshold and **defer** the
kernel-extract because dispatch shapes diverge. The deferral still holds
at N=4 — ``resolve()``'s specificity / precedence / extends-walk logic
dominates this kernel's LOC; the shared surface (``register`` / ``get`` /
``all`` / typed-collision-error) is a small fraction. Pure Rule-2
application (simplicity first).

**Extract trigger** (lift a shared ``KernelRegistry[K, V]`` base):

- N=5, OR
- a new registry needs *only* the common surface
  (``register`` / ``get`` / ``all`` / typed-collision-error) without
  additional dispatch machinery — then the kernel-extract pays for
  itself in one new site.

Until either trigger fires, each registry stays as a hand-written class
matched to its own dispatch shape. This story file is the audit anchor;
the next registry's author can grep the four precedents and decide.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from codegenie.plugins.errors import (
    PluginAlreadyRegistered,
    PluginNotRegistered,
)
from codegenie.plugins.protocols import Plugin
from codegenie.plugins.resolution import PluginResolution
from codegenie.types.identifiers import PluginId

if TYPE_CHECKING:
    from codegenie.plugins.scope import PluginScope


__all__ = [
    "PluginRegistry",
    "default_registry",
    "register_plugin",
]


class PluginRegistry:
    """Ordered, deduplicated-by-name collection of :class:`Plugin`
    instances.

    Mirrors the shape of :class:`codegenie.probes.registry.Registry`:
    duplicate names raise :class:`PluginAlreadyRegistered` at
    :meth:`register` time so misconfiguration fails loud at import,
    never silently at dispatch. Tests construct independent
    :class:`PluginRegistry` instances so they do not pollute each other;
    the module-level :data:`default_registry` is the process-wide
    instance the convenience helper :func:`register_plugin` targets when
    its ``registry`` kwarg is omitted.

    Iteration order is **registration order** (CPython ≥ 3.7 dict
    insertion-order semantics). The Phase 3 audit log and the resolver's
    deterministic sort depend on this; do not sort, ``frozenset()``, or
    otherwise re-permute the registered names inside this class.
    """

    def __init__(self) -> None:
        self._plugins: dict[PluginId, Plugin] = {}
        # Origin strings ("module.qualname") are kept alongside so
        # duplicate errors can name BOTH call sites without re-introspecting
        # the prior plugin (which a caller could have mutated).
        # Mirrors ``indices/registry.py``'s ``_origins`` design.
        self._origins: dict[PluginId, str] = {}

    def register(self, plugin: Plugin) -> Plugin:
        """Register ``plugin`` under its ``manifest.name``.

        Returns the plugin unchanged so the helper :func:`register_plugin`
        can mirror its return. Duplicate ``manifest.name`` raises
        :class:`PluginAlreadyRegistered` whose message names both
        colliding ``module.qualname`` strings — the precedent
        ``probes/registry.py:154-158`` shape.

        Validation is deliberately kept to one line: collision-check then
        append. Pydantic manifest validation (S2-02), integrity checks
        (S2-03), and resolver totality (S2-04) live downstream. The
        kernel does **only** registration (ADR-0002 §Decision).
        """
        name: PluginId = plugin.manifest.name
        new_origin = f"{type(plugin).__module__}.{type(plugin).__qualname__}"
        if name in self._plugins:
            existing_origin = self._origins[name]
            raise PluginAlreadyRegistered(name, existing_origin, new_origin)
        self._plugins[name] = plugin
        self._origins[name] = new_origin
        return plugin

    def get(self, name: PluginId) -> Plugin:
        """Return the registered plugin for ``name``.

        Raises :class:`PluginNotRegistered` (carrying a typed
        ``.name: PluginId`` payload) when ``name`` is not registered.
        Callers that need a default should use :meth:`resolve` once
        S2-04 ships — the kernel deliberately does **not** ship a
        ``get_or_default`` here.
        """
        try:
            return self._plugins[name]
        except KeyError:
            raise PluginNotRegistered(name) from None

    def all(self) -> tuple[Plugin, ...]:
        """Return every registered plugin in registration order, as an
        immutable tuple.

        Returning a tuple (not a list) is the immutability convention this
        codebase uses across its registry surfaces
        (``probes/registry.py:189``,
        ``depgraph/registry.py``'s ``registered_ecosystems``). Callers
        get an iterable they cannot accidentally mutate.

        Phase 3 audit-chain hashing and the resolver's deterministic
        sort depend on byte-stable insertion order; the underlying
        ``dict`` ordering is the contract.
        """
        return tuple(self._plugins.values())

    def resolve(self, scope: PluginScope) -> PluginResolution:
        """**Stub — S2-04 ships the resolver.**

        The specificity / precedence / ``extends``-walk / universal-fallback
        algorithm lives in S2-04 (Phase-3 ADR-0003). The S2-04 executor
        greps for the literal substring ``"S2-04"`` in this stub's
        message — do not remove it from the raise site.
        """
        raise NotImplementedError(
            "resolve() lands in S2-04; the universal-fallback algorithm is not yet implemented"
        )


default_registry: Final[PluginRegistry] = PluginRegistry()
"""Process-wide :class:`PluginRegistry` instance.

Production plugin modules register into this singleton via
:func:`register_plugin`. Tests pass fresh :class:`PluginRegistry`
instances through the ``registry=`` kwarg to avoid pollution
(ADR-0002 §Consequences row 7 — the session-scoped fixture in
``tests/unit/plugins/conftest.py`` asserts ``default_registry.all()``
remains byte-identical across the test session).

``Final`` is intentional and tighter than the sibling
``probes/registry.py:238``: replacement requires explicit DI through
``register_plugin(..., registry=...)``. ADR-0002 §Consequences row 2
names this posture.
"""


def register_plugin(
    plugin: Plugin,
    *,
    registry: PluginRegistry | None = None,
) -> Plugin:
    """Register ``plugin`` into ``registry`` (or :data:`default_registry`
    when ``registry`` is ``None``); return the unchanged plugin.

    Convenience for plugin ``api.py`` modules — the canonical usage is
    ``PLUGIN = register_plugin(MyPlugin())``. NOT a class decorator: see
    the module docstring's "function call, not a decorator" paragraph for
    the rationale (ADR-0002 §Decision).
    """
    return (registry or default_registry).register(plugin)
