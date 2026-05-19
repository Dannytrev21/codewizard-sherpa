"""Fence — :class:`codegenie.plugins.protocols.Plugin` Protocol surface freeze.

Phase 3 ADR-0004 §Consequences names the four-member surface
(``manifest``, ``build_subgraph``, ``adapters``, ``transforms``) and
requires a fence test that asserts the count. Adding a fifth member or
removing one fails this assertion at CI time — keeping the kernel honest
to the "extension by addition" promise (production ADR-0031).

Do **not** rely on ``Plugin.__abstractmethods__`` to enumerate the surface:
:class:`typing.Protocol` (especially when ``@runtime_checkable``) does NOT
populate ``__abstractmethods__`` the way :class:`abc.ABC` does. Some
Python versions leave it empty; others lift only methods (not attributes).
We introspect ``dir(Plugin) - dunders`` + :attr:`__annotations__` instead
— the same idiom the precedent ``codegenie.probes.base`` fence uses.
"""

from __future__ import annotations

import inspect

from codegenie.plugins.protocols import Plugin

_EXPECTED_MEMBERS = frozenset({"manifest", "build_subgraph", "adapters", "transforms"})


def test_plugin_protocol_has_exactly_four_members() -> None:
    """ADR-0004 §Consequences: the ``Plugin`` Protocol's public surface is
    exactly four members. Drift (additions or deletions) fails loudly.

    Method members appear in :func:`dir`; attribute-only members (no
    default value) appear in :attr:`__annotations__`. The union of the
    two is the Protocol's public surface — neither half alone is
    complete on every Python version.
    """
    public_dir = {name for name in dir(Plugin) if not name.startswith("_")}
    annotated = {name for name in Plugin.__annotations__ if not name.startswith("_")}
    members = frozenset(public_dir | annotated)
    assert members == _EXPECTED_MEMBERS, (
        f"Plugin Protocol surface drifted from ADR-0004 freeze: "
        f"got={sorted(members)} expected={sorted(_EXPECTED_MEMBERS)}"
    )


def test_plugin_protocol_manifest_is_annotated_attribute() -> None:
    """ADR-0004 — ``manifest`` is an *attribute*, not a method.
    ``__annotations__`` carries the forward-reference to ``PluginManifest``."""
    assert "manifest" in Plugin.__annotations__


def test_plugin_protocol_three_methods_are_functions() -> None:
    """ADR-0004 — ``build_subgraph``, ``adapters``, ``transforms`` are
    methods. ``inspect.isfunction`` catches an accidental demotion to an
    attribute or a property."""
    assert inspect.isfunction(Plugin.build_subgraph)
    assert inspect.isfunction(Plugin.adapters)
    assert inspect.isfunction(Plugin.transforms)
