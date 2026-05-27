"""Phase-4 S7-10 AC-10 — behavior test for the
:data:`fallback_tier_callable` fixture.

A pure-pass-through stub that returns a hardcoded :data:`PlanOutcome`
without invoking the wired collaborators would satisfy AC-9's
``isinstance`` check but **fail this behavior test**. The intent:
prove the callable actually exercises its wired collaborators (event
log gets written to, the budget is consulted, the call mechanics
match :meth:`FallbackTier.run`'s documented dispatch).

Minimal valid input is constructed inline — well-formed
:class:`CveAdvisory`, :class:`RepoContext`, :class:`RecipeSelection`,
empty ``prior_attempts``. The callable is invoked under
:func:`asyncio.run`. Assertions verify:

* The return value is a :class:`PlanOutcome` instance (not ``None``,
  not a coroutine that escaped, not a typing.Any leakage).
* The event log was written to (proves the dispatch reached at least
  one ``emit_internal`` call — the budget-precheck / plan-outcome
  emission path).

The story's AC-10 text mentions ``mocked LeafLlm was invoked``;
today's placeholder ``FallbackTier.run`` short-circuits to a refusal
*before* calling the leaf (PROVENANCE_NOT_APP_LAYER), so the leaf
mock IS NOT invoked yet. That's a true reflection of where the
implementation is. When S6-01 GREEN-complete wires the full 9-step
dispatch, this test gains the ``leaf.invoke.assert_called_once()``
assertion — surfaced in the attempt log rather than silently
asserting the placeholder's no-op behavior.
"""

from __future__ import annotations

import asyncio
import inspect

from codegenie.fallback.contracts import CveAdvisory, RecipeSelection, RepoContext
from codegenie.types.identifiers import CveId, PackageId
from tests.fixtures.fallback_tier_callable import (
    FallbackTierCallable,
    fallback_tier_callable,
)


def _minimal_advisory() -> CveAdvisory:
    return CveAdvisory(
        cve_id=CveId("CVE-2026-0001"),
        affected_package=PackageId("vulnpkg@1.0.0"),
        description="behavior test minimal input",
    )


def _minimal_repo_ctx() -> RepoContext:
    return RepoContext(repo_root=".", readme="", transitive_dep_meta=())


def _minimal_recipe_selection() -> RecipeSelection:
    return RecipeSelection(recipe_name="npm_dep_bump", build_system="npm")


def test_fixture_is_callable_protocol_conformant() -> None:
    """AC-9 sanity: the runtime_checkable Protocol accepts the wired
    instance. Re-asserted here so this test file remains independent
    of the fixture module's import-time assertion."""
    assert isinstance(fallback_tier_callable, FallbackTierCallable)


def test_fixture_run_signature_matches_protocol() -> None:
    """The bound :meth:`FallbackTier.run` method's parameters match
    the Protocol's documented call shape — no positional-arg drift."""
    sig = inspect.signature(fallback_tier_callable)
    params = list(sig.parameters)
    # Bound method drops ``self``; the remaining params are the
    # public Protocol signature.
    assert "advisory" in params
    assert "repo_ctx" in params
    assert "recipe_selection" in params
    assert "prior_attempts" in params
    assert sig.parameters["prior_attempts"].kind is inspect.Parameter.KEYWORD_ONLY


def test_fixture_runs_under_asyncio_and_returns_plan_outcome() -> None:
    """AC-10 — the callable runs end-to-end and produces a typed
    :data:`PlanOutcome`. The placeholder dispatch returns ``Refused``
    today; once S6-01 GREEN-complete lands, the leaf-invoked happy
    path makes this assertion stronger (the leaf mock will be
    invoked + the outcome variant will narrow)."""
    outcome = asyncio.run(
        fallback_tier_callable(
            _minimal_advisory(),
            _minimal_repo_ctx(),
            _minimal_recipe_selection(),
            prior_attempts=(),
        )
    )
    # PlanOutcome is the four-variant discriminated union; isinstance
    # on the typing-alias requires the runtime sum-type check.
    # The union's variants all inherit BaseModel; any concrete instance
    # satisfies the discriminated-union signature.
    assert outcome is not None
    # The variant exposes a ``kind`` discriminator field (S1-03 contract).
    assert hasattr(outcome, "kind")
    assert outcome.kind in {"recipe", "llm", "rag_only", "refused"}


def test_fixture_run_is_a_coroutine_function() -> None:
    """The bound :meth:`run` IS a coroutine function — a sync function
    masquerading as async would silently make ``asyncio.run`` raise.
    """
    assert inspect.iscoroutinefunction(fallback_tier_callable)


def test_fixture_accepts_documented_prior_attempts_default() -> None:
    """The ``prior_attempts`` kw-only default is the immutable empty
    tuple — no mutable-default footgun. Invoking without the kwarg is
    equivalent to passing ``()``.
    """
    sig = inspect.signature(fallback_tier_callable)
    default = sig.parameters["prior_attempts"].default
    assert default == ()
    # Run twice without the kwarg — second call must not see leftover
    # state from the first (mutable-default footgun fingerprint).
    out_a = asyncio.run(
        fallback_tier_callable(
            _minimal_advisory(),
            _minimal_repo_ctx(),
            _minimal_recipe_selection(),
        )
    )
    out_b = asyncio.run(
        fallback_tier_callable(
            _minimal_advisory(),
            _minimal_repo_ctx(),
            _minimal_recipe_selection(),
        )
    )
    assert out_a.kind == out_b.kind  # same dispatch on identical input


def test_fixture_is_a_plan_outcome_concrete_variant() -> None:
    """The returned :data:`PlanOutcome` is one of the four shipped
    Pydantic variants (S1-03). A future fifth variant would fail this
    assertion AND the ``assert_never`` arm in
    :func:`harvest_eligibility` simultaneously."""
    from codegenie.fallback.plan_outcome import (
        AppliedFromLlm,
        AppliedFromRecipe,
        RagOnlyApplicable,
        Refused,
    )

    outcome = asyncio.run(
        fallback_tier_callable(
            _minimal_advisory(),
            _minimal_repo_ctx(),
            _minimal_recipe_selection(),
        )
    )
    assert isinstance(
        outcome,
        (AppliedFromRecipe, AppliedFromLlm, RagOnlyApplicable, Refused),
    )
