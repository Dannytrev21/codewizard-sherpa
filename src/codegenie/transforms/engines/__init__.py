"""Phase-3 recipe-engine implementations — concrete :class:`~codegenie
.transforms.recipe_engine.RecipeEngine` workers.

ADR-0009 ships the ``RecipeEngine`` Protocol with two day-1 implementations
so the Protocol earns its keep: :mod:`codegenie.transforms.engines.npm_lockfile`
(S5-02) and the OpenRewrite scaffold (S5-03). This package is the home for
those workers; it deliberately re-exports nothing — each engine module is
imported directly by the orchestrator that wires it.
"""

from __future__ import annotations
