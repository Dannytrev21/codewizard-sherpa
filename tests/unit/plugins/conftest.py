"""Fixtures for ``tests/unit/plugins/`` — ADR-0002 §Consequences row 7
cross-test isolation guard for the Phase 3 :data:`default_registry`.

Two scopes:

- **Function-scoped autouse** :func:`restore_default_registry` — snapshots
  the singleton's contents pre-test and restores them post-test. AC-10
  deliberately writes into the singleton; without this fixture the write
  would leak into every later test.
- **Session-scoped autouse** :func:`_default_registry_session_guard` — the
  load-bearing check ADR-0002 names. Captures ``default_registry.all()`` at
  session start and re-asserts byte-identical equality at session end. Any
  test that escaped the function-scoped restore (e.g., raised mid-cleanup)
  fails the suite loudly.

Mirrors :func:`restore_default_registry` from ``tests/unit/test_registry.py``
(probes precedent, S2-05) — same shape, scoped to the plugin registry.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from codegenie.plugins.recipe_registry import (
    RecipeRegistry,
    default_recipe_registry,
)
from codegenie.plugins.registry import PluginRegistry, default_registry


@pytest.fixture
def plugin_registry() -> PluginRegistry:
    """Return a fresh :class:`PluginRegistry` for one test.

    Tests pass this instance through ``register_plugin(..., registry=...)``
    so the module-level :data:`default_registry` stays untouched. ADR-0002
    §Decision pins this as the canonical isolation pattern.
    """
    return PluginRegistry()


@pytest.fixture(autouse=True)
def restore_default_registry() -> Generator[None, None, None]:
    """Snapshot :data:`default_registry`; restore on teardown.

    AC-10's default-singleton smoke deliberately writes into the global.
    Without this fixture the write leaks into every later test in the same
    pytest session. Mirrors ``tests/unit/test_registry.py:20-40``
    (probes precedent, S2-05).
    """
    snapshot = dict(default_registry._plugins)
    snapshot_origins = dict(default_registry._origins)
    try:
        yield
    finally:
        default_registry._plugins.clear()
        default_registry._plugins.update(snapshot)
        default_registry._origins.clear()
        default_registry._origins.update(snapshot_origins)


@pytest.fixture(scope="session", autouse=True)
def _default_registry_session_guard() -> Generator[None, None, None]:
    """ADR-0002 §Consequences row 7 — ``default_registry.all() == ()`` at
    session end. If any test in this directory escaped its function-scoped
    restore, the suite fails loudly at teardown instead of silently
    polluting downstream sessions."""
    snapshot = default_registry.all()
    yield
    end = default_registry.all()
    assert end == snapshot, (
        f"default_registry mutated across the test session; start={snapshot!r} end={end!r}"
    )


# --- S5-01: per-plugin RecipeRegistry isolation (mirrors PluginRegistry) ---


@pytest.fixture
def fresh_recipe_registry() -> RecipeRegistry:
    """Return a fresh :class:`RecipeRegistry` for one test.

    Tests pass this instance through ``register_recipe(..., registry=...)``
    so the module-level :data:`default_recipe_registry` stays untouched.
    S5-01 mirrors S2-01's :func:`plugin_registry` fixture.
    """
    return RecipeRegistry()


@pytest.fixture(autouse=True)
def restore_default_recipe_registry() -> Generator[None, None, None]:
    """Snapshot :data:`default_recipe_registry`; restore on teardown.

    Mirrors :func:`restore_default_registry`. Any test that writes into the
    default singleton (typically none — fresh ``RecipeRegistry()`` is the
    canonical path) is rolled back here.
    """
    snapshot_recipes = dict(default_recipe_registry._recipes)
    snapshot_by_plugin = {k: list(v) for k, v in default_recipe_registry._by_plugin.items()}
    snapshot_names = {k: set(v) for k, v in default_recipe_registry._names_by_plugin.items()}
    snapshot_origins = dict(default_recipe_registry._origins)
    try:
        yield
    finally:
        default_recipe_registry._recipes.clear()
        default_recipe_registry._recipes.update(snapshot_recipes)
        default_recipe_registry._by_plugin.clear()
        default_recipe_registry._by_plugin.update(snapshot_by_plugin)
        default_recipe_registry._names_by_plugin.clear()
        default_recipe_registry._names_by_plugin.update(snapshot_names)
        default_recipe_registry._origins.clear()
        default_recipe_registry._origins.update(snapshot_origins)


@pytest.fixture(scope="session", autouse=True)
def _default_recipe_registry_session_guard() -> Generator[None, None, None]:
    """ADR-0002 lineage — assert :data:`default_recipe_registry.all() == ()`
    at session start and end. Catches any test that escaped its
    function-scoped restore.
    """
    snapshot = default_recipe_registry.all()
    yield
    end = default_recipe_registry.all()
    assert end == snapshot, (
        f"default_recipe_registry mutated across the test session; start={snapshot!r} end={end!r}"
    )
