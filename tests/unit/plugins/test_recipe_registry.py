"""Phase-3 S5-01 — :class:`RecipeRegistry` + ``@register_recipe`` + walker.

Mirrors :mod:`tests.unit.plugins.test_registry` (S2-01) but tests the
per-plugin recipe-registration mechanism. The autouse fixtures in
:mod:`tests.unit.plugins.conftest` carry the cross-test isolation guard
for :data:`default_recipe_registry`.
"""

from __future__ import annotations

import inspect
from typing import Any, get_args

import pytest

from codegenie.plugins.recipe_registry import (
    RecipeAlreadyRegistered,
    RecipeNameCollision,
    RecipeNotFound,
    RecipeRegistry,
    default_recipe_registry,
    register_recipe,
)
from codegenie.transforms.outcomes import (
    ApplicationPlan,
    Applies,
    NotApplicableReason,
    NotApplies,
    RecipeNotApplicable,
)
from codegenie.transforms.recipe_engine import (
    MatchedRecipe,
    match_recipes,
)
from codegenie.types.identifiers import PluginId, RecipeId, TransformKind

PID = PluginId("vulnerability-remediation--node--npm")
KIND = TransformKind("npm_lockfile_semver_bump")
PLAN = ApplicationPlan(summary="bump")


def _recipe_factory(
    rid: str,
    *,
    name: str | None = None,
    precedence: int,
    verdict: Applies | NotApplies,
) -> type:
    """Build a stateless recipe class via ``type()``.

    Per-instance ``applies_calls`` counter (NOT closure-shared) — proves the
    walker short-circuits correctly when one of three recipes matches.
    """
    nm = name or rid

    def applies(self: Any, cve: object, bundle: object) -> Applies | NotApplies:
        self.applies_calls += 1
        return verdict

    def __init__(self: Any) -> None:
        self.applies_calls = 0

    return type(
        f"Recipe_{rid.replace('-', '_')}",
        (),
        {
            "recipe_id": RecipeId(rid),
            "name": nm,
            "kind": KIND,
            "precedence": precedence,
            "applies": applies,
            "__init__": __init__,
        },
    )


# --- AC-6 — decorator returns the class unchanged (identity) ----------------


def test_register_decorator_returns_class_unchanged(
    fresh_recipe_registry: RecipeRegistry,
) -> None:
    """AC-6 — identity (not equality). A wrapper-replaces-class mutant fails this."""

    original = _recipe_factory(
        "npm-semver-bump",
        precedence=10,
        verdict=NotApplies(reason="PEER_DEP_CONFLICT"),
    )
    decorated = register_recipe(PID, registry=fresh_recipe_registry)(original)

    assert decorated is original  # identity, not ==
    entries = fresh_recipe_registry.all(PID)
    assert len(entries) == 1
    assert isinstance(entries[0].recipe, original)


# --- AC-7 — duplicate recipe_id rejected with typed exception ---------------


def test_duplicate_recipe_id_rejected_typed_exception(
    fresh_recipe_registry: RecipeRegistry,
) -> None:
    """AC-7 — ``RecipeAlreadyRegistered`` carries typed ``.recipe_id``."""

    register_recipe(PID, registry=fresh_recipe_registry)(
        _recipe_factory(
            "dup", name="dup-a", precedence=0, verdict=NotApplies(reason="PEER_DEP_CONFLICT")
        )
    )

    with pytest.raises(RecipeAlreadyRegistered) as exc_info:
        register_recipe(PID, registry=fresh_recipe_registry)(
            _recipe_factory(
                "dup", name="dup-b", precedence=0, verdict=NotApplies(reason="PEER_DEP_CONFLICT")
            )
        )

    assert exc_info.value.recipe_id == RecipeId("dup")


# --- AC-8 — duplicate name within plugin rejected ---------------------------


def test_duplicate_name_within_plugin_rejected(
    fresh_recipe_registry: RecipeRegistry,
) -> None:
    """AC-8 — same name but distinct recipe_id is rejected.

    The orchestrator's tie-breaker sort is ``(-precedence, name)``; two
    recipes with the same name at the same precedence would be
    order-unstable, so registration rejects it loudly.
    """

    register_recipe(PID, registry=fresh_recipe_registry)(
        _recipe_factory(
            "rid-a", name="collide", precedence=5, verdict=NotApplies(reason="PEER_DEP_CONFLICT")
        )
    )

    with pytest.raises(RecipeNameCollision) as exc_info:
        register_recipe(PID, registry=fresh_recipe_registry)(
            _recipe_factory(
                "rid-b",
                name="collide",
                precedence=5,
                verdict=NotApplies(reason="PEER_DEP_CONFLICT"),
            )
        )

    assert exc_info.value.plugin_id == PID
    assert exc_info.value.name == "collide"


def test_duplicate_name_across_plugins_allowed(
    fresh_recipe_registry: RecipeRegistry,
) -> None:
    """AC-8 negative control — name uniqueness is scoped per-plugin.

    ``npm-semver-bump`` makes sense in both
    ``vulnerability-remediation--node--npm`` (Phase 3) and a hypothetical
    ``distroless-migration--node--npm`` (Phase 7).
    """

    other_plugin = PluginId("distroless-migration--node--npm")

    register_recipe(PID, registry=fresh_recipe_registry)(
        _recipe_factory(
            "a-rid",
            name="shared-name",
            precedence=0,
            verdict=NotApplies(reason="PEER_DEP_CONFLICT"),
        )
    )
    register_recipe(other_plugin, registry=fresh_recipe_registry)(
        _recipe_factory(
            "b-rid",
            name="shared-name",
            precedence=0,
            verdict=NotApplies(reason="PEER_DEP_CONFLICT"),
        )
    )

    assert len(fresh_recipe_registry.all(PID)) == 1
    assert len(fresh_recipe_registry.all(other_plugin)) == 1


# --- AC-9 — recipe_id regex validation at registration ----------------------


@pytest.mark.parametrize(
    "bad_id",
    ["", "UPPER", "1-leading-digit", "has_underscore", "-leading-dash"],
)
def test_invalid_recipe_id_rejected_at_registration(
    fresh_recipe_registry: RecipeRegistry, bad_id: str
) -> None:
    """AC-9 — ``_validate_recipe_id`` regex (``^[a-z][a-z0-9-]*$``) rejects
    malformed IDs at register time, not at first ``match_recipes`` call.
    """

    cls = _recipe_factory(
        bad_id,
        name="placeholder",
        precedence=0,
        verdict=NotApplies(reason="PEER_DEP_CONFLICT"),
    )
    with pytest.raises(ValueError, match="recipe_id"):
        register_recipe(PID, registry=fresh_recipe_registry)(cls)


@pytest.mark.parametrize("good_id", ["a", "abc", "a-b", "a1", "npm-semver-bump"])
def test_valid_recipe_id_accepted_at_registration(
    fresh_recipe_registry: RecipeRegistry, good_id: str
) -> None:
    """AC-9 positive control — well-formed IDs pass validation."""

    cls = _recipe_factory(
        good_id,
        name=f"name-for-{good_id}",
        precedence=0,
        verdict=NotApplies(reason="PEER_DEP_CONFLICT"),
    )
    register_recipe(PID, registry=fresh_recipe_registry)(cls)
    assert fresh_recipe_registry.get(RecipeId(good_id)).recipe.recipe_id == RecipeId(good_id)


# --- AC-5 — deterministic (-precedence, name) sort --------------------------


def test_iteration_order_is_precedence_desc_then_name_asc(
    fresh_recipe_registry: RecipeRegistry,
) -> None:
    """AC-5 — sort by ``(-precedence, name)``.

    Insertion order is deliberately scrambled (highest-precedence registered
    second, ties registered out of name-sort order) so insertion-order ≠
    sort-order — proves the registry sorts, not just preserves.
    """

    cases = [("z-low", 1), ("a-mid", 5), ("m-high", 10), ("b-mid", 5)]
    for rid, prec in cases:
        register_recipe(PID, registry=fresh_recipe_registry)(
            _recipe_factory(rid, precedence=prec, verdict=NotApplies(reason="PEER_DEP_CONFLICT"))
        )

    order = [r.recipe.name for r in fresh_recipe_registry.all(PID)]
    assert order == ["m-high", "a-mid", "b-mid", "z-low"]


# --- AC-10 — first-Applies-wins + short-circuit guarantee -------------------


def test_first_applies_wins_short_circuits(
    fresh_recipe_registry: RecipeRegistry,
) -> None:
    """AC-10 — middle recipe matches; lowest-precedence recipe never consulted.

    ``applies_calls == 0`` on the never-walked recipe is the load-bearing
    short-circuit witness.
    """

    cls_first = _recipe_factory(
        "first", precedence=10, verdict=NotApplies(reason="PEER_DEP_CONFLICT")
    )
    cls_match = _recipe_factory("match", precedence=5, verdict=Applies(plan=PLAN))
    cls_never = _recipe_factory(
        "never", precedence=1, verdict=NotApplies(reason="MAJOR_BUMP_REFUSE")
    )
    for C in (cls_first, cls_match, cls_never):
        register_recipe(PID, registry=fresh_recipe_registry)(C)

    out = match_recipes(fresh_recipe_registry, PID, cve=object(), bundle=object())

    assert isinstance(out, MatchedRecipe)
    assert out.recipe.name == "match"
    assert out.plan == PLAN

    entries_by_name = {r.recipe.name: r for r in fresh_recipe_registry.all(PID)}
    # First (precedence 10) was called once and declined.
    assert entries_by_name["first"].recipe.applies_calls == 1
    # Match (precedence 5) was called once and matched.
    assert entries_by_name["match"].recipe.applies_calls == 1
    # Never (precedence 1) was NEVER consulted — short-circuit witness.
    assert entries_by_name["never"].recipe.applies_calls == 0


# --- AC-11 — all-decline returns considered trace ---------------------------


def test_all_decline_returns_all_recipes_not_applicable_with_considered(
    fresh_recipe_registry: RecipeRegistry,
) -> None:
    """AC-11 — every recipe declines → ``considered`` carries the trace.

    Phase-4's ``prompt_builder`` reads ``considered`` for a structured
    rejection trace; the top-level ``reason=ALL_RECIPES_NOT_APPLICABLE``
    is the dispatch marker.
    """

    for rid, reason in (("a", "PEER_DEP_CONFLICT"), ("b", "MAJOR_BUMP_REFUSE")):
        register_recipe(PID, registry=fresh_recipe_registry)(
            _recipe_factory(rid, precedence=0, verdict=NotApplies(reason=reason))
        )

    out = match_recipes(fresh_recipe_registry, PID, cve=object(), bundle=object())

    assert isinstance(out, RecipeNotApplicable)
    assert out.reason == "ALL_RECIPES_NOT_APPLICABLE"
    assert [c.reason for c in out.considered] == ["PEER_DEP_CONFLICT", "MAJOR_BUMP_REFUSE"]


# --- AC-12 — empty registry returns NO_RECIPES_REGISTERED -------------------


def test_empty_registry_returns_no_recipes_registered(
    fresh_recipe_registry: RecipeRegistry,
) -> None:
    """AC-12 — distinct reason from ``ALL_RECIPES_NOT_APPLICABLE``.

    The two cases are semantically distinct: "we considered N recipes and
    they all declined" vs "no recipes were ever registered for this
    plugin". Phase 4 may dispatch differently on each.
    """

    out = match_recipes(fresh_recipe_registry, PID, cve=object(), bundle=object())
    assert isinstance(out, RecipeNotApplicable)
    assert out.reason == "NO_RECIPES_REGISTERED"
    assert out.considered == []


# --- AC-15 — NotApplicableReason Literal includes NO_RECIPES_REGISTERED ----


def test_not_applicable_reason_literal_includes_no_recipes_registered() -> None:
    """AC-15 — additive Literal widening; pre-existing five preserved."""
    args = get_args(NotApplicableReason)
    assert "NO_RECIPES_REGISTERED" in args
    for member in (
        "PEER_DEP_CONFLICT",
        "MAJOR_BUMP_REFUSE",
        "OVERRIDES_AMBIGUOUS",
        "RECIPE_CATALOG_MISS",
        "ALL_RECIPES_NOT_APPLICABLE",
    ):
        assert member in args


# --- AC-16 — walker is event-free -------------------------------------------


def test_match_recipes_emits_no_events(
    fresh_recipe_registry: RecipeRegistry,
) -> None:
    """AC-16 — registry walker is event-free; events belong to the S6-04
    orchestrator. The walker's signature MUST NOT take an event log.
    """

    register_recipe(PID, registry=fresh_recipe_registry)(
        _recipe_factory("a", precedence=0, verdict=Applies(plan=PLAN))
    )
    sig = inspect.signature(match_recipes)
    assert "event_log" not in sig.parameters
    assert "events" not in sig.parameters


# --- AC-13 — MatchedRecipe shape --------------------------------------------


def test_matched_recipe_is_frozen_slots_dataclass(
    fresh_recipe_registry: RecipeRegistry,
) -> None:
    """AC-13 — ``MatchedRecipe`` is ``@dataclass(frozen=True, slots=True)``
    with exactly two fields."""

    register_recipe(PID, registry=fresh_recipe_registry)(
        _recipe_factory("only", precedence=0, verdict=Applies(plan=PLAN))
    )
    out = match_recipes(fresh_recipe_registry, PID, cve=object(), bundle=object())
    assert isinstance(out, MatchedRecipe)
    assert out.plan is PLAN
    # frozen — mutation raises:
    with pytest.raises((AttributeError, Exception)):
        out.plan = ApplicationPlan(summary="other")  # type: ignore[misc]


# --- AC-14 — RecipeNotApplicable.considered additive field ------------------


def test_recipe_not_applicable_has_considered_field_default_empty() -> None:
    """AC-14 — ``considered`` is additive with ``Field(default_factory=list)``.

    Existing callers that don't pass ``considered`` continue to work — the
    default is ``[]``; each instance gets its own list (default_factory,
    not a shared default).
    """
    out_a = RecipeNotApplicable(reason="ALL_RECIPES_NOT_APPLICABLE")
    out_b = RecipeNotApplicable(reason="ALL_RECIPES_NOT_APPLICABLE")
    assert out_a.considered == []
    assert out_b.considered == []
    assert out_a.considered is not out_b.considered  # default_factory, not default


def test_recipe_not_applicable_with_considered_list() -> None:
    """AC-14 — passing ``considered`` preserves the list in iteration order."""
    nas = [NotApplies(reason="PEER_DEP_CONFLICT"), NotApplies(reason="MAJOR_BUMP_REFUSE")]
    out = RecipeNotApplicable(reason="ALL_RECIPES_NOT_APPLICABLE", considered=nas)
    assert [c.reason for c in out.considered] == ["PEER_DEP_CONFLICT", "MAJOR_BUMP_REFUSE"]


# --- AC-4 — RecipeRegistry public surface (exactly four methods) ------------


def test_recipe_registry_public_surface_is_four_methods() -> None:
    """AC-4 — exactly four public methods on RecipeRegistry: register, get,
    all, _reset_for_tests. Resist API creep.
    """
    public_methods = {
        name
        for name in dir(RecipeRegistry)
        if callable(getattr(RecipeRegistry, name)) and not name.startswith("__")
    }
    # _reset_for_tests has leading underscore (test-only signal); public surface
    # is register / get / all. All four exist.
    assert {"register", "get", "all", "_reset_for_tests"} <= public_methods
    # No surprise extras like unregister/keys/__contains__/__iter__ surfaces.
    for forbidden in ("unregister", "keys", "values", "items", "clear", "pop"):
        assert forbidden not in public_methods


# --- AC-18 — default_recipe_registry is Final --------------------------------


def test_default_recipe_registry_is_recipe_registry_instance() -> None:
    """AC-18 — ``default_recipe_registry: Final[RecipeRegistry] = RecipeRegistry()``.
    Replacement requires explicit DI through ``register_recipe(..., registry=...)``.
    """
    assert isinstance(default_recipe_registry, RecipeRegistry)


# --- AC-7 negative — RecipeNotFound on get() miss ---------------------------


def test_get_unknown_recipe_id_raises_recipe_not_found(
    fresh_recipe_registry: RecipeRegistry,
) -> None:
    """``RecipeRegistry.get`` on a missing id raises ``RecipeNotFound``
    carrying a typed ``.recipe_id`` attribute."""
    with pytest.raises(RecipeNotFound) as exc_info:
        fresh_recipe_registry.get(RecipeId("missing"))
    assert exc_info.value.recipe_id == RecipeId("missing")


# --- AC-4 — all() with no filter returns flattened-sorted -------------------


def test_all_without_plugin_filter_returns_every_recipe(
    fresh_recipe_registry: RecipeRegistry,
) -> None:
    """``registry.all()`` (no filter) returns every recipe across plugins,
    sorted by ``(-precedence, name)``."""
    other = PluginId("distroless-migration--node--npm")
    register_recipe(PID, registry=fresh_recipe_registry)(
        _recipe_factory("a", precedence=1, verdict=NotApplies(reason="PEER_DEP_CONFLICT"))
    )
    register_recipe(other, registry=fresh_recipe_registry)(
        _recipe_factory("b", precedence=10, verdict=NotApplies(reason="PEER_DEP_CONFLICT"))
    )
    register_recipe(PID, registry=fresh_recipe_registry)(
        _recipe_factory("c", precedence=5, verdict=NotApplies(reason="PEER_DEP_CONFLICT"))
    )
    order = [r.recipe.name for r in fresh_recipe_registry.all()]
    assert order == ["b", "c", "a"]
