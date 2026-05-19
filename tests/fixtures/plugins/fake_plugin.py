"""Minimal :class:`codegenie.plugins.protocols.Plugin` stand-in.

Originally landed for S2-01 (`name`-only). Extended for S2-04 with
``extends``, ``precedence``, ``manifest_scope_kwargs``, ``adapters_map``,
and ``transforms_map`` so the resolver tests can compose extends chains,
break precedence ties, fan out multi-scope manifests, and observe
left-to-right adapter / transform merge semantics.

``make_fake_plugin`` is the **single boundary lift** from raw ``str`` to
:class:`PluginId` and from raw ``ManifestScope`` kwargs to the
:class:`ManifestScope` Pydantic model. Tests pass raw strings for
ergonomics; the lift happens here exactly once (Phase-3 ADR-0010 §4 —
smart constructors at the boundary).

The fake's ``manifest`` is the real :class:`PluginManifest` Pydantic
model (S2-02 shipped) — not a frozen-dataclass stub — so consumers can
read every documented field. The ``# type: ignore[return-value]`` on
:func:`make_fake_plugin` is gone now that the manifest shape matches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from codegenie.plugins.manifest import (
    ManifestContributes,
    ManifestScope,
    PluginManifest,
)
from codegenie.types.identifiers import PluginId

if TYPE_CHECKING:
    from codegenie.plugins.protocols import Adapter, Plugin, RecipeEngine
    from codegenie.plugins.registry import PluginRegistry


@dataclass(frozen=True)
class _FakePlugin:
    """Test-time stand-in satisfying the four-member :class:`Plugin` Protocol."""

    manifest: PluginManifest
    _adapters: dict[Any, Any] = field(default_factory=dict)
    _transforms: dict[Any, Any] = field(default_factory=dict)

    def build_subgraph(self, registry: PluginRegistry) -> object:
        raise NotImplementedError("test fake — build_subgraph not implemented")

    def adapters(self) -> dict[Any, Adapter]:
        return dict(self._adapters)

    def transforms(self) -> dict[Any, RecipeEngine]:
        return dict(self._transforms)


def _default_manifest_scope() -> ManifestScope:
    # Default chosen to match the resolver tests' canonical incoming
    # scope ``(vulnerability-remediation, node, npm)`` — tests that omit
    # ``manifest_scope_kwargs`` get an exactly-matching plugin without
    # having to repeat the kwargs.
    return ManifestScope(
        task_class="vulnerability-remediation",
        languages="node",
        build_systems="npm",
    )


def make_fake_plugin(
    *,
    name: str | PluginId,
    extends: tuple[PluginId, ...] = (),
    precedence: int = 50,
    manifest_scope_kwargs: dict[str, str | list[str]] | None = None,
    adapters_map: dict[Any, Any] | None = None,
    transforms_map: dict[Any, Any] | None = None,
) -> Plugin:
    """Return a frozen-dataclass fake satisfying :class:`Plugin`.

    The ``PluginId(name)`` and ``ManifestScope(**kwargs)`` boundary lifts
    happen here and **only here** inside the test suite; production paths
    construct ``PluginId``s via the S2-02 manifest loader.

    Parameters:

    - ``name`` — plugin id. Either a raw ``str`` (lifted to
      :class:`PluginId`) or an already-lifted :class:`PluginId`.
    - ``extends`` — tuple of :class:`PluginId` for the manifest's
      ``extends`` field (S2-04 extends-chain walk).
    - ``precedence`` — manifest precedence; default matches the S2-02
      manifest default of 50.
    - ``manifest_scope_kwargs`` — ``ManifestScope`` constructor kwargs.
      When ``None``, uses ``(vulnerability-remediation, javascript, npm)``.
      Pass ``{"task_class": "*", "languages": "*", "build_systems": "*"}``
      to construct a universal manifest scope (the universal-fallback
      fixture uses this).
    - ``adapters_map`` — return value of ``Plugin.adapters()`` (used by
      the resolver's adapter-merge tests).
    - ``transforms_map`` — return value of ``Plugin.transforms()`` (used
      by the resolver's TCCM ``provides`` merge tests, indirectly).
    """
    # ``PluginId`` is a ``NewType`` (identity-to-``str`` at runtime), so
    # `isinstance(name, PluginId)` would be a type error. Lift unconditionally.
    plugin_id: PluginId = PluginId(str(name))

    scope = (
        ManifestScope(**manifest_scope_kwargs)
        if manifest_scope_kwargs is not None
        else _default_manifest_scope()
    )
    # ``model_construct`` skips the ``parse_plugin_id`` validator so test
    # fakes are free to use short tie-breaking names like ``a-plugin``.
    # The manifest loader's own tests (``test_manifest.py``) exercise the
    # production regex; resolver tests should not be coupled to it.
    manifest = PluginManifest.model_construct(
        name=plugin_id,
        version="0.1.0",
        scope=scope,
        extends=extends,
        precedence=precedence,
        contributes=ManifestContributes(),
    )
    return _FakePlugin(  # type: ignore[return-value]
        manifest=manifest,
        _adapters=dict(adapters_map or {}),
        _transforms=dict(transforms_map or {}),
    )
