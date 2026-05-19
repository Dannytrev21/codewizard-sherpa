"""Tests for ``codegenie.plugins.registry`` — Phase 3 S2-01 kernel.

Mirrors the shape of ``tests/unit/test_registry.py`` (probes) and
``tests/unit/depgraph/test_registry.py`` (depgraph): identity-tuple
ordering, dual-name collision message, fresh-instance fixture isolation,
``Final`` ``default_registry`` snapshot.

Every test pins one acceptance criterion from
``docs/phases/03-vuln-deterministic-recipe/stories/S2-01-plugin-registry-kernel.md``;
docstrings cite the AC by number.
"""

from __future__ import annotations

import pytest

from codegenie.plugins.errors import (
    PluginAlreadyRegistered,
    PluginNotRegistered,
)
from codegenie.plugins.registry import (
    PluginRegistry,
    default_registry,
    register_plugin,
)
from codegenie.types.identifiers import PluginId
from tests.fixtures.plugins.fake_plugin import make_fake_plugin


def test_collision_raises(plugin_registry: PluginRegistry) -> None:
    """AC-4 — duplicate ``plugin.manifest.name`` raises
    :class:`PluginAlreadyRegistered`. Typed ``.name: PluginId`` payload AND
    both colliding ``module.qualname`` strings appear in the message
    (mirrors ``probes/registry.py:154-158``)."""
    plugin = make_fake_plugin(name="vulnerability-remediation--node--npm")
    register_plugin(plugin, registry=plugin_registry)

    duplicate = make_fake_plugin(name="vulnerability-remediation--node--npm")
    with pytest.raises(PluginAlreadyRegistered) as exc_info:
        register_plugin(duplicate, registry=plugin_registry)

    assert exc_info.value.name == PluginId("vulnerability-remediation--node--npm")
    # Both colliding qualified names appear in the message:
    assert str(exc_info.value).count("_FakePlugin") == 2


def test_all_returns_registration_order(plugin_registry: PluginRegistry) -> None:
    """AC-5 — identity-tuple ordering with names whose alphabetic order
    differs from insertion order. Catches ``return ()``, ``return set(...)``,
    and ``return sorted(...)`` mutants."""
    zeta = make_fake_plugin(name="vulnerability-remediation--node--zeta")
    alpha = make_fake_plugin(name="vulnerability-remediation--node--alpha")
    mu = make_fake_plugin(name="vulnerability-remediation--node--mu")
    register_plugin(zeta, registry=plugin_registry)
    register_plugin(alpha, registry=plugin_registry)
    register_plugin(mu, registry=plugin_registry)

    assert plugin_registry.all() == (zeta, alpha, mu)


def test_all_returns_tuple_not_list(plugin_registry: PluginRegistry) -> None:
    """AC-2 — ``all()`` returns an immutable tuple (not a list)."""
    assert isinstance(plugin_registry.all(), tuple)


def test_register_plugin_returns_plugin_unchanged(
    plugin_registry: PluginRegistry,
) -> None:
    """AC-3 — return identity; catches ``return None`` mutant."""
    plugin = make_fake_plugin(name="vulnerability-remediation--node--npm")
    assert register_plugin(plugin, registry=plugin_registry) is plugin


def test_register_method_returns_plugin_unchanged(
    plugin_registry: PluginRegistry,
) -> None:
    """AC-2 — ``PluginRegistry.register`` returns the plugin unchanged."""
    plugin = make_fake_plugin(name="vulnerability-remediation--node--npm")
    assert plugin_registry.register(plugin) is plugin


def test_register_plugin_default_singleton_path(
    restore_default_registry: None,
) -> None:
    """AC-10 — ``register_plugin(plugin)`` with no ``registry=`` kwarg
    mutates :data:`default_registry`. The autouse
    ``restore_default_registry`` fixture restores state post-test."""
    plugin = make_fake_plugin(name="vulnerability-remediation--node--npm")
    register_plugin(plugin)  # no registry= kwarg

    assert plugin in default_registry.all()


def test_get_returns_registered_plugin(plugin_registry: PluginRegistry) -> None:
    """AC-2 — ``get(name)`` round-trips the registered plugin."""
    plugin = make_fake_plugin(name="vulnerability-remediation--node--npm")
    register_plugin(plugin, registry=plugin_registry)

    assert plugin_registry.get(PluginId("vulnerability-remediation--node--npm")) is plugin


def test_get_unknown_raises_plugin_not_registered_with_typed_name(
    plugin_registry: PluginRegistry,
) -> None:
    """AC-4 — typed ``.name: PluginId`` payload on
    :class:`PluginNotRegistered` (not just stringified message match)."""
    with pytest.raises(PluginNotRegistered) as exc_info:
        plugin_registry.get(PluginId("vulnerability-remediation--node--npm"))

    assert exc_info.value.name == PluginId("vulnerability-remediation--node--npm")
    assert "vulnerability-remediation--node--npm" in str(exc_info.value)


def test_resolve_stub_names_s2_04(plugin_registry: PluginRegistry) -> None:
    """AC-2 — :meth:`PluginRegistry.resolve` is a typed stub.
    The literal substring ``"S2-04"`` MUST appear in the message — S2-04's
    executor will grep on this forward-reference contract."""
    with pytest.raises(NotImplementedError, match="S2-04"):
        plugin_registry.resolve(scope=None)  # type: ignore[arg-type]


def test_runtime_checkable_protocols_match_fakes() -> None:
    """AC-8 — :func:`isinstance` smoke for the ``@runtime_checkable`` decoration.
    Downstream fixtures rely on this; the asymmetry check (``object()``
    fails) catches a trivially-passing ``isinstance(_, Plugin) -> True``
    mutant."""
    from codegenie.plugins.protocols import Plugin

    plugin = make_fake_plugin(name="example--noop--*")
    assert isinstance(plugin, Plugin) is True
    assert isinstance(object(), Plugin) is False


def test_fresh_registries_are_isolated() -> None:
    """AC-6 — both positive AND negative control. Catches the
    ``all() == ()``-always mutant (negative half passes but positive half
    fails) and the ``all() == [last_registered]``-globally mutant (positive
    half passes but negative half fails)."""
    reg_a = PluginRegistry()
    reg_b = PluginRegistry()
    plugin = make_fake_plugin(name="vulnerability-remediation--node--npm")
    register_plugin(plugin, registry=reg_a)

    assert reg_a.all() == (plugin,)  # positive: A has the plugin
    assert reg_b.all() == ()  # negative: fresh B is empty
    assert plugin not in reg_b.all()  # belt and suspenders


def test_register_plugin_into_explicit_registry_does_not_pollute_default(
    plugin_registry: PluginRegistry,
    restore_default_registry: None,
) -> None:
    """AC-6 — ``register_plugin(p, registry=fresh)`` MUST NOT mutate
    :data:`default_registry`. The session-scoped guard also asserts this,
    but this function-scoped pin makes the regression surface immediately."""
    plugin = make_fake_plugin(name="vulnerability-remediation--node--npm")
    register_plugin(plugin, registry=plugin_registry)

    assert plugin not in default_registry.all()
    assert default_registry.all() == ()
