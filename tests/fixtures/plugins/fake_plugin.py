"""Minimal :class:`codegenie.plugins.protocols.Plugin` stand-in for S2-01 tests.

S2-02 ships the full ``PluginManifest`` Pydantic model. Until then, the
fixture uses a frozen-dataclass ``_FakeManifest`` carrying just the ``name:
PluginId`` field the registry's collision check reads. The
``# type: ignore[return-value]`` on :func:`make_fake_plugin` is the
deliberate "Pydantic model not yet" wrinkle the story names — it comes off
once S2-02 lands and the fake satisfies the full manifest shape.

The :func:`make_fake_plugin` helper is the **single boundary lift** from raw
``str`` to :class:`PluginId`. Tests pass raw strings for ergonomics; the
``PluginId(name)`` wrap happens here exactly once (Phase-3 ADR-0010 §4 —
smart constructors at the boundary).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codegenie.types.identifiers import PluginId

if TYPE_CHECKING:
    from codegenie.plugins.protocols import Adapter, Plugin, RecipeEngine
    from codegenie.plugins.registry import PluginRegistry


@dataclass(frozen=True)
class _FakeManifest:
    """Test-time stand-in for the S2-02 ``PluginManifest`` Pydantic model.

    Carries only the ``name`` field the registry collision check reads.
    """

    name: PluginId


@dataclass(frozen=True)
class _FakePlugin:
    """Test-time stand-in satisfying the four-member :class:`Plugin` Protocol."""

    manifest: _FakeManifest

    def build_subgraph(self, registry: PluginRegistry) -> object:
        raise NotImplementedError("test fake — build_subgraph not implemented")

    def adapters(self) -> dict[object, Adapter]:
        return {}

    def transforms(self) -> dict[object, RecipeEngine]:
        return {}


def make_fake_plugin(*, name: str) -> Plugin:
    """Return a frozen-dataclass fake satisfying :class:`Plugin`.

    The ``PluginId(name)`` boundary lift happens here and **only here**
    inside the test suite; production paths construct ``PluginId``s via the
    S2-02 manifest loader.
    """
    return _FakePlugin(manifest=_FakeManifest(name=PluginId(name)))  # type: ignore[return-value]
