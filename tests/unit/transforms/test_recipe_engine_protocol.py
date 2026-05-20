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


# ---------------------------------------------------------------------------
# S5-03 amendment — the scaffolded ``OpenRewriteRecipeEngine`` (the second
# day-1 engine) also structurally satisfies the Protocol. This pair is the
# rent-payment receipt for ADR-0009's "two implementations from day one"
# commitment — without a second conformant engine the Protocol would be the
# "Strategy with one strategy" anti-pattern. Runs every PR (pure structural
# typing — no JVM needed); deliberately NOT marked ``phase_7_preview``.
# ---------------------------------------------------------------------------


def test_openrewrite_engine_satisfies_protocol() -> None:
    """S5-03 AC-Conf-1 — ``OpenRewriteRecipeEngine`` satisfies the
    ``@runtime_checkable`` ``RecipeEngine`` Protocol."""
    from codegenie.transforms.engines.openrewrite import OpenRewriteRecipeEngine
    from codegenie.transforms.sandbox_jail import JailedSubprocessResult, JailedSubprocessSpec
    from codegenie.transforms.transform_registry import TransformRegistry

    class _FakeJail:
        async def run(self, spec: JailedSubprocessSpec) -> JailedSubprocessResult:
            raise NotImplementedError("test stub")

    engine = OpenRewriteRecipeEngine(jail=_FakeJail(), transform_registry=TransformRegistry())
    assert isinstance(engine, RecipeEngine)


def test_openrewrite_engine_apply_return_annotation() -> None:
    """S5-03 AC-Conf-1 + AC-Contract-1 — ``apply`` returns a bare
    ``RecipeOutcome`` (ADR-0014); both day-1 engines share the annotation
    verbatim. The harden-pass 2-tuple rewrite is withdrawn per the
    Re-execution note."""
    import inspect

    from codegenie.transforms.engines.npm_lockfile import NpmLockfileRecipeEngine
    from codegenie.transforms.engines.openrewrite import OpenRewriteRecipeEngine

    or_ann = inspect.signature(OpenRewriteRecipeEngine.apply).return_annotation
    npm_ann = inspect.signature(NpmLockfileRecipeEngine.apply).return_annotation
    assert str(or_ann) == "RecipeOutcome"
    assert str(or_ann) == str(npm_ann)
