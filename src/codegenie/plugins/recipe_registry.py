"""Phase-3 S5-01 — per-plugin :class:`RecipeRegistry` + ``@register_recipe``.

Mirrors :mod:`codegenie.plugins.registry`'s shape (S2-01) but keyed by
:data:`RecipeId` with a per-plugin filter and a deterministic
``(-precedence, name)`` sort. The shape divergence from S2-01:

- Recipes are *stateless matchers*; :func:`register_recipe` is a **class
  decorator** that zero-arg constructs (vs S2-01's *function-call* that
  takes a pre-composed instance). See module-level §"Class-decorator vs
  function-call asymmetry" below.
- :meth:`RecipeRegistry.all` filters by ``plugin_id`` and sorts by
  ``(-precedence, name)``; S2-01's :meth:`PluginRegistry.all` preserves
  registration order.
- Name uniqueness is *scoped per-plugin* (recipes with identical names in
  different plugins are allowed); ``recipe_id`` uniqueness is *global*.

**Rule-of-N=5 (kernel-extract trigger).** This is the **5th**
decorator-registry in the codebase (after ``probes/registry.py``,
``indices/registry.py``, ``depgraph/registry.py``,
``plugins/registry.py``). S2-01 §6 pinned the extract trigger at "N=5 OR a
new registry needs only the common surface". The trigger fires today on
N=5, but the five registries' dispatch shapes are all distinct:

1. ``probes/registry.py`` — ``for_task`` filter + LRU + heaviness sort.
2. ``indices/registry.py`` — total dispatch via ``dispatch_all``.
3. ``depgraph/registry.py`` — single dispatch + ``has_strategy`` query.
4. ``plugins/registry.py`` — ``register`` / ``get`` / ``all`` +
   ``resolve(scope)`` + ``extends``-walk.
5. ``plugins/recipe_registry.py`` (this module) — ``register`` / ``get``
   / ``all(plugin_id)`` + first-``Applies``-wins walker.

The shared surface (``register`` / ``get`` / ``all`` /
typed-collision-error) is a small fraction of each registry's LOC. A
``KernelRegistry[K, V]`` base would leave five hand-written dispatch
shapes on top. Pure Rule-2 application — extract still deferred. Lift
the kernel when *either* (a) N=6 with the 6th needing *only* the common
surface; or (b) a real bug surfaces in one of the five that a shared
base would have prevented.

**Class-decorator vs function-call asymmetry.** S2-01's
:func:`register_plugin` is a function call because plugins carry
composed state (manifest + adapters + transforms) that the *plugin
author* constructs. This module's :func:`register_recipe` is a class
decorator because recipes are stateless matchers whose identity is its
class attributes — zero-arg ``recipe_cls()`` construction is safe. If a
future recipe needs genuine constructor state, ``register_recipe(plugin
_id, instance=None)`` is a backwards-compatible widening (deferred per
Rule 2).

ADRs honored: ADR-0002 (kernel-instance + ``default_*`` singleton +
``register_*(..., registry=...)`` DI), ADR-0009 (recipe-engine Protocol
two-implementation discipline), ADR-0010 (newtype identifiers, no raw
``str`` for ``RecipeId`` / ``PluginId``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from codegenie.errors import CodegenieError
from codegenie.transforms.recipe_engine import _validate_recipe_id
from codegenie.types.identifiers import PluginId, RecipeId

if TYPE_CHECKING:
    from codegenie.transforms.recipe_engine import RecipeProtocol


__all__ = [
    "RecipeAlreadyRegistered",
    "RecipeNameCollision",
    "RecipeNotFound",
    "RecipeRegistry",
    "RegisteredRecipe",
    "default_recipe_registry",
    "register_recipe",
]


# --- Typed failure markers -------------------------------------------------


class RecipeAlreadyRegistered(CodegenieError):
    """Raised by :meth:`RecipeRegistry.register` when the recipe-id is
    already registered (globally — uniqueness is across all plugins).

    Carries a typed ``.recipe_id: RecipeId`` so callers can match on a
    structured field rather than parsing the message. The message names
    both colliding ``module.qualname`` strings, mirroring the precedent
    in :class:`codegenie.plugins.errors.PluginAlreadyRegistered`.
    """

    recipe_id: RecipeId

    def __init__(self, recipe_id: RecipeId, existing: str, duplicate: str) -> None:
        self.recipe_id = recipe_id
        self.existing = existing
        self.duplicate = duplicate
        super().__init__(f"duplicate recipe_id {recipe_id!r}: {existing} and {duplicate}")


class RecipeNameCollision(CodegenieError):
    """Raised by :meth:`RecipeRegistry.register` when a recipe ``name`` is
    already used by another recipe in the same ``plugin_id``.

    Distinct from :class:`RecipeAlreadyRegistered` because the
    ``recipe_id`` may differ — the tie-breaker on ``(-precedence, name)``
    would otherwise be order-unstable across registration orders.
    """

    plugin_id: PluginId
    name: str

    def __init__(self, plugin_id: PluginId, name: str) -> None:
        self.plugin_id = plugin_id
        self.name = name
        super().__init__(f"recipe name {name!r} collides within plugin {plugin_id!r}")


class RecipeNotFound(CodegenieError):
    """Raised by :meth:`RecipeRegistry.get` when the requested ``recipe_id``
    is not registered. Carries a typed ``.recipe_id`` attribute.
    """

    recipe_id: RecipeId

    def __init__(self, recipe_id: RecipeId) -> None:
        self.recipe_id = recipe_id
        super().__init__(f"recipe {recipe_id!r} is not registered")


# --- Registered-recipe payload ---------------------------------------------


@dataclass(frozen=True, slots=True)
class RegisteredRecipe:
    """Pairing of ``plugin_id`` and the registered recipe instance.

    Frozen + slots: registry returns are immutable; callers cannot mutate
    a recipe's plugin association after the fact.
    """

    plugin_id: PluginId
    recipe: RecipeProtocol


# --- Registry --------------------------------------------------------------


class RecipeRegistry:
    """Per-plugin recipe collection with deterministic dispatch.

    Public surface is **exactly four** methods (``register`` / ``get`` /
    ``all`` / ``_reset_for_tests``). The underscore on
    ``_reset_for_tests`` signals test-only usage; production code never
    unregisters (a hot-reload feature would land in a future story with
    its own ADR amendment).

    Iteration order from :meth:`all` is sorted by ``(-precedence, name)``
    — NOT registration order. The :func:`match_recipes` walker depends on
    this; the order is verified determinism-stable across
    ``PYTHONHASHSEED`` by the subprocess test.
    """

    def __init__(self) -> None:
        self._recipes: dict[RecipeId, RegisteredRecipe] = {}
        self._by_plugin: dict[PluginId, list[RecipeId]] = {}
        self._names_by_plugin: dict[PluginId, set[str]] = {}
        # Origin strings ("module.qualname") for duplicate-collision messages —
        # mirrors :class:`codegenie.plugins.registry.PluginRegistry`'s _origins.
        self._origins: dict[RecipeId, str] = {}

    def register(self, plugin_id: PluginId, recipe: RecipeProtocol) -> RecipeProtocol:
        """Register ``recipe`` under ``plugin_id``.

        Three checks (in order): regex-validate the ``recipe_id`` (raises
        :class:`ValueError`); global recipe-id uniqueness (raises
        :class:`RecipeAlreadyRegistered`); per-plugin name uniqueness
        (raises :class:`RecipeNameCollision`). Returns the recipe
        unchanged so :func:`register_recipe` mirrors its return.
        """
        validated_rid = _validate_recipe_id(recipe.recipe_id)
        new_origin = f"{type(recipe).__module__}.{type(recipe).__qualname__}"

        if validated_rid in self._recipes:
            existing_origin = self._origins[validated_rid]
            raise RecipeAlreadyRegistered(validated_rid, existing_origin, new_origin)

        names = self._names_by_plugin.setdefault(plugin_id, set())
        if recipe.name in names:
            raise RecipeNameCollision(plugin_id, recipe.name)

        self._recipes[validated_rid] = RegisteredRecipe(plugin_id=plugin_id, recipe=recipe)
        self._by_plugin.setdefault(plugin_id, []).append(validated_rid)
        names.add(recipe.name)
        self._origins[validated_rid] = new_origin
        return recipe

    def get(self, recipe_id: RecipeId) -> RegisteredRecipe:
        """Return the registered :class:`RegisteredRecipe` for ``recipe_id``.

        Raises :class:`RecipeNotFound` (typed ``.recipe_id``) on miss.
        Callers needing the bare recipe object access
        ``.recipe`` on the returned :class:`RegisteredRecipe`.
        """
        try:
            return self._recipes[recipe_id]
        except KeyError:
            raise RecipeNotFound(recipe_id) from None

    def all(self, plugin_id: PluginId | None = None) -> tuple[RegisteredRecipe, ...]:
        """Return registered recipes sorted by ``(-precedence, name)``.

        When ``plugin_id`` is ``None``, returns every registered recipe
        across all plugins; otherwise restricts to a single plugin. The
        sort is the canonical Phase-3 dispatch order — first-Applies-wins
        consults higher-precedence recipes first, breaking ties by name
        for stability.

        Returns a tuple (not a list) — the immutability convention this
        codebase uses across registry surfaces.
        """
        candidates: list[RegisteredRecipe]
        if plugin_id is None:
            candidates = list(self._recipes.values())
        else:
            ids = self._by_plugin.get(plugin_id, [])
            candidates = [self._recipes[rid] for rid in ids]
        return tuple(sorted(candidates, key=lambda r: (-r.recipe.precedence, r.recipe.name)))

    def _reset_for_tests(self) -> None:
        """Clear all internal state. Test-only — leading-underscore signals
        intent; production code never calls this.
        """
        self._recipes.clear()
        self._by_plugin.clear()
        self._names_by_plugin.clear()
        self._origins.clear()


default_recipe_registry: Final[RecipeRegistry] = RecipeRegistry()
"""Process-wide :class:`RecipeRegistry` instance.

Plugin ``api.py`` modules register into this singleton via
``@register_recipe(plugin_id)``. Tests pass fresh :class:`RecipeRegistry`
instances through ``register_recipe(..., registry=...)`` (the
``fresh_recipe_registry`` fixture in ``tests/unit/plugins/conftest.py``).

``Final`` mirrors :data:`codegenie.plugins.registry.default_registry` —
replacement requires explicit DI through the ``registry=`` kwarg.
"""


def register_recipe(
    plugin_id: PluginId,
    *,
    registry: RecipeRegistry | None = None,
) -> Callable[[type], type]:
    """Decorator factory: zero-arg-construct the decorated class, register
    the instance under ``plugin_id``, and return the **original class**
    unchanged.

    Canonical usage::

        @register_recipe(PluginId("vulnerability-remediation--node--npm"))
        class NpmSemverBumpRecipe:
            recipe_id = RecipeId("npm-semver-bump")
            name = "npm-semver-bump"
            kind = TransformKind("npm_lockfile_semver_bump")
            precedence = 10
            def applies(self, cve, bundle): ...

    Returns the class via identity (``decorated is original``) so consumer
    code (subclassing, ``isinstance`` checks, ``__name__`` introspection)
    behaves exactly as if the decorator weren't there.
    """
    target = registry if registry is not None else default_recipe_registry

    def _decorator(recipe_cls: type) -> type:
        instance = recipe_cls()
        target.register(plugin_id, instance)
        return recipe_cls

    return _decorator
