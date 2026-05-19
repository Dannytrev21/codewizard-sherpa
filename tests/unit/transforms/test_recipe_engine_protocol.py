"""Phase-3 S5-01 — :class:`RecipeEngine` Protocol surface tests.

Pins the ``@runtime_checkable`` Protocol behaviour and the re-export
identity between :mod:`codegenie.transforms.recipe_engine` (canonical
home, S5-01) and :mod:`codegenie.plugins.protocols` (S2-01 deferred-stub
location).
"""

from __future__ import annotations

from codegenie.plugins.protocols import RecipeEngine as RecipeEngineFromPlugins
from codegenie.transforms.recipe_engine import RecipeEngine


def test_recipe_engine_is_runtime_checkable_protocol() -> None:
    """AC-2 — ``@runtime_checkable``; structural conformance on
    ``apply(self, repo, plan, capability)``.
    """

    class FakeEngine:
        async def apply(self, repo: object, plan: object, capability: object) -> object:
            raise NotImplementedError("test stub")

    assert isinstance(FakeEngine(), RecipeEngine)


def test_missing_apply_method_fails_isinstance() -> None:
    """AC-2 negative control — no ``apply`` ⇒ not a ``RecipeEngine``."""

    class NoApply:
        pass

    assert not isinstance(NoApply(), RecipeEngine)


def test_plugins_protocols_re_export_is_identical() -> None:
    """AC-2 — ``plugins/protocols.py`` re-export IS the canonical class.

    Catches drift if someone re-declares the Protocol locally instead of
    re-exporting; ``is`` (not ``==``) is the load-bearing identity check.
    """
    assert RecipeEngine is RecipeEngineFromPlugins
