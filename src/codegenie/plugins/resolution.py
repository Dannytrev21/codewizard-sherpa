"""S2-04 :class:`PluginResolution` re-export shim.

The real definition (and the
:class:`ConcreteResolution | UniversalFallbackResolution` discriminated
union it aliases) lives in :mod:`codegenie.plugins.resolver`. This
module preserves the S2-01 import path
(``from codegenie.plugins.resolution import PluginResolution``) so
older callers keep importing the alias from the same place; new
consumers should import directly from :mod:`codegenie.plugins.resolver`.
"""

from __future__ import annotations

from codegenie.plugins.resolver import (
    ConcreteResolution as ConcreteResolution,
)
from codegenie.plugins.resolver import (
    PluginResolution as PluginResolution,
)
from codegenie.plugins.resolver import (
    UniversalFallbackResolution as UniversalFallbackResolution,
)

__all__ = [
    "ConcreteResolution",
    "PluginResolution",
    "UniversalFallbackResolution",
]
