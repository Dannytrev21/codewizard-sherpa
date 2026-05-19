"""Fixture for the canonical ``universal--*--*`` fallback plugin.

S2-04 introduces the universal-fallback resolution semantics
(production ADR-0031 §No-match fallback; Phase-3 ADR-0003 §Decision
step 3). The real fallback plugin (with its handoff-writing subgraph)
lands in S7-03; until then, tests need a registrable stand-in.

``make_universal_fallback`` returns a minimal :class:`Plugin` whose
``manifest.name == UNIVERSAL_FALLBACK_ID``, whose ``manifest.scope``
is ``(*, *, *)``, whose precedence is ``0`` (lowest — strictly below
the S2-02 default of 50 so a tied-on-everything-else concrete plugin
always beats the fallback at sort time), and whose ``extends`` is
empty.

**Why ``model_construct`` instead of the regular constructor.** The
S2-02 :class:`PluginManifest` ``name`` validator routes raw strings
through :func:`codegenie.types.parsers.parse_plugin_id`, whose regex
``^[a-z][a-z0-9-]{0,63}--[a-z]...--[a-z]...$`` rejects ``*``. The
universal fallback literal is the load-bearing convention but does
not satisfy the concrete-plugin id regex; ``model_construct``
bypasses validators so the fixture honours the literal without
amending the parser (S7-03 — and a future ADR amendment — owns the
real loader's universal-id allowance).

The literal string ``"universal--*--*"`` lives in **exactly two**
places in the codebase: :data:`codegenie.plugins.resolver.UNIVERSAL_FALLBACK_ID`
and this fixture. The AST source-scan test
``tests/static/test_universal_fallback_id_single_source.py``
enforces this. To reference the literal elsewhere, import the
constant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from codegenie.plugins.manifest import (
    ManifestContributes,
    ManifestRequirements,
    ManifestScope,
    PluginManifest,
)
from codegenie.plugins.resolver import UNIVERSAL_FALLBACK_ID

if TYPE_CHECKING:
    from codegenie.plugins.protocols import Adapter, Plugin, RecipeEngine
    from codegenie.plugins.registry import PluginRegistry

__all__ = ["make_universal_fallback"]


@dataclass(frozen=True)
class _UniversalFallbackPlugin:
    """Test-time stand-in for the S7-03 real fallback plugin."""

    manifest: PluginManifest
    _adapters: dict[Any, Any] = field(default_factory=dict)
    _transforms: dict[Any, Any] = field(default_factory=dict)

    def build_subgraph(self, registry: PluginRegistry) -> object:
        raise NotImplementedError("universal-fallback fixture — build_subgraph lands with S7-03")

    def adapters(self) -> dict[Any, Adapter]:
        return dict(self._adapters)

    def transforms(self) -> dict[Any, RecipeEngine]:
        return dict(self._transforms)


def make_universal_fallback() -> Plugin:
    """Return a minimal universal-fallback :class:`Plugin` stand-in.

    Reused by S7-03's real HITL fallback plugin (which extends this
    shape with a non-stub ``build_subgraph``). Until then, every
    resolver test that needs a registered fallback registers this
    fixture.
    """
    manifest = PluginManifest.model_construct(
        name=UNIVERSAL_FALLBACK_ID,
        version="0.0.0",
        scope=ManifestScope(task_class="*", languages="*", build_systems="*"),
        extends=(),
        precedence=0,
        contributes=ManifestContributes(),
        requirements=ManifestRequirements(),
    )
    return _UniversalFallbackPlugin(manifest=manifest)  # type: ignore[return-value]
