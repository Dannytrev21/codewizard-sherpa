"""``codegenie.depgraph`` — Open/Closed seam for per-ecosystem dep-graph builders.

Public surface (six names, sorted, per S1-10 AC-1):

* :class:`DepGraphProbeOutput` — typed slice shape ``DepGraphProbe`` will return.
* :class:`DepGraphRegistry` — the per-ecosystem strategy registry.
* :class:`DepGraphRegistryError` — duplicate/unknown-ecosystem marker
  (re-exported from :mod:`codegenie.errors`).
* :data:`DepGraphStrategy` — ``Callable[[ProbeContext, list[Mapping]], DiGraph]`` alias.
* :data:`default_dep_graph_registry` — process-wide singleton instance.
* :func:`register_dep_graph_strategy` — decorator-factory targeting the singleton.

Phase 2 ships **zero** registered strategies — the registry is the seam
Phase 3 plugins fill (architect's commitment,
``phase-arch-design.md`` §"Component design" #11).
"""

from __future__ import annotations

from codegenie.depgraph.model import DepGraphProbeOutput
from codegenie.depgraph.registry import (
    DepGraphRegistry,
    DepGraphRegistryError,
    DepGraphStrategy,
    default_dep_graph_registry,
    register_dep_graph_strategy,
)

__all__ = [
    "DepGraphProbeOutput",
    "DepGraphRegistry",
    "DepGraphRegistryError",
    "DepGraphStrategy",
    "default_dep_graph_registry",
    "register_dep_graph_strategy",
]
