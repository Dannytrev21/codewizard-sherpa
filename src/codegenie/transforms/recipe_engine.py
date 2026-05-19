"""Phase-3 S5-01 — :class:`RecipeEngine` Protocol, :class:`RecipeProtocol`
matcher, :func:`match_recipes` walker, :class:`MatchedRecipe` payload.

This module is the **canonical home** for the Phase-5-contract-surface
``RecipeEngine`` Protocol (ADR-0001). S2-01 shipped a temporary stub in
:mod:`codegenie.plugins.protocols` and deferred the freeze to Step 5; that
stub is now re-exported from this module via ``from codegenie.transforms
.recipe_engine import RecipeEngine`` so any S2-01 fixture continues
round-tripping (the AC-2 identity test pins this).

The walker is **event-free** — events (``RecipeMatched`` /
``RecipeSkipped``) are emitted by the S6-04 orchestrator after the walker
returns. The walker's return is the intermediate :class:`MatchedRecipe`
payload (recipe + plan); the orchestrator's ``apply_recipe`` node lifts it
to :data:`codegenie.transforms.outcomes.RecipeOutcome.Applied` by calling
the matching engine's ``apply()``.

State machine: ``match → apply → outcome`` — this module owns step 1.

**Two-level Protocol hierarchy** (arch §C12, §Design patterns row 2):

- :class:`RecipeEngine` is the **worker** — one per ``TransformKind``
  (``NpmLockfileRecipeEngine``, ``OpenRewriteRecipeEngine``). Shipped in
  S5-02 / S5-03.
- :class:`RecipeProtocol` is the **matcher** — one per recipe
  (``NpmLockfileSemverBumpRecipe``, etc.). Shipped in S7-02.
- Lookup: ``plugin.transforms()[recipe.kind].apply(repo, plan, capability)``.

ADRs honored: ADR-0009 (this Protocol surface), ADR-0010 (sum types +
newtypes), ADR-0001 (Phase-5 contract surface — additive widening of
:class:`RecipeNotApplicable.considered`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol, runtime_checkable

from codegenie.transforms.outcomes import (
    ApplicationPlan,
    Applies,
    NotApplies,
    RecipeNotApplicable,
    RecipeOutcome,
)
from codegenie.types.identifiers import RecipeId, TransformKind

if TYPE_CHECKING:
    from codegenie.plugins.bundle import Bundle
    from codegenie.plugins.capabilities import NpmInstallCapability
    from codegenie.plugins.recipe_registry import RecipeRegistry
    from codegenie.plugins.sandbox_path import SandboxedPath
    from codegenie.types.identifiers import PluginId
    from codegenie.vuln_index.models import VulnerabilityRecord


__all__ = [
    "MatchedRecipe",
    "RecipeEngine",
    "RecipeProtocol",
    "match_recipes",
]


@runtime_checkable
class RecipeEngine(Protocol):
    """Worker contract — produces a :data:`RecipeOutcome` from a plan.

    One engine serves many recipes; the orchestrator picks the engine via
    ``plugin.transforms()[recipe.kind]``. Phase-3 day-1 ships two
    implementations (S5-02 ``NpmLockfileRecipeEngine``,
    S5-03 ``OpenRewriteRecipeEngine``) so the Protocol earns its keep
    (arch §Anti-patterns row "Premature pluggability").

    ``repo`` and ``capability`` are forward-referenced under
    ``TYPE_CHECKING`` — runtime imports would form cycles with
    :mod:`codegenie.plugins.sandbox_path` (S4-04) and
    :mod:`codegenie.plugins.capabilities` (S4-05).
    """

    async def apply(
        self,
        repo: SandboxedPath,
        plan: ApplicationPlan,
        capability: NpmInstallCapability,
    ) -> RecipeOutcome:
        """Run the engine against ``repo`` under ``capability`` and return a
        :data:`RecipeOutcome` (one of ``Applied`` / ``Skipped`` /
        ``RecipeNotApplicable`` / ``RecipeFailed``)."""
        ...


@runtime_checkable
class RecipeProtocol(Protocol):
    """Matcher contract — declares a cheap predicate over (CVE, bundle).

    Stateless: ``recipe_id`` / ``name`` / ``kind`` / ``precedence`` are
    class attributes; ``applies()`` is a pure function. The
    :func:`register_recipe` decorator instantiates with no constructor
    args; future stateful recipes can opt into the
    ``register_recipe(plugin_id, instance=None)`` shape without breaking
    the current API (deferred per Rule 2).

    ``kind`` is load-bearing — the orchestrator's ``apply_recipe`` node
    does ``plugin.transforms()[recipe.kind].apply(...)``. Without it the
    recipe-to-engine mapping is impossible.
    """

    recipe_id: RecipeId
    name: str
    kind: TransformKind
    precedence: int

    def applies(self, cve: VulnerabilityRecord, bundle: Bundle) -> Applies | NotApplies:
        """Cheap predicate. ``Applies(plan=...)`` ⇒ this recipe will run;
        ``NotApplies(reason=...)`` ⇒ skip and try the next recipe."""
        ...


@dataclass(frozen=True, slots=True)
class MatchedRecipe:
    """Walker return payload — intermediate ``match → apply → outcome``.

    Not a Pydantic model (boundary validation isn't required — the walker
    only flows internally, never to disk / wire). Two fields:

    - ``recipe`` — the :class:`RecipeProtocol` instance that matched.
    - ``plan`` — the :class:`ApplicationPlan` the recipe produced.

    The S6-04 orchestrator lifts this to ``Applied`` after invoking
    ``plugin.transforms()[recipe.kind].apply(repo, plan, capability)``.
    """

    recipe: RecipeProtocol
    plan: ApplicationPlan


# Recipe-id smart constructor — regex pinned at ``^[a-z][a-z0-9-]*$``
# (lowercase ASCII identifiers, optional hyphen separator). Matches the
# Phase-3 dotted-snake-case convention's "left half" without the dot
# (recipe ids are flat, not dotted — they live inside a plugin namespace).
_RECIPE_ID_RX: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9-]*$")


def _validate_recipe_id(rid: str) -> RecipeId:
    """Lift ``rid`` to :data:`RecipeId` after enforcing
    ``^[a-z][a-z0-9-]*$``. Raises :class:`ValueError` at register time
    (not at first walker call) so misconfiguration fails loud at import.
    """
    if not _RECIPE_ID_RX.fullmatch(rid):
        raise ValueError(f"recipe_id {rid!r} does not match {_RECIPE_ID_RX.pattern}")
    return RecipeId(rid)


def match_recipes(
    registry: RecipeRegistry,
    plugin_id: PluginId,
    cve: VulnerabilityRecord,
    bundle: Bundle,
) -> MatchedRecipe | RecipeNotApplicable:
    """First-``Applies(plan)``-wins walk over ``registry.all(plugin_id)``.

    Iteration order is ``(-precedence, name)`` — pinned by
    :meth:`RecipeRegistry.all`. The walk short-circuits on the first
    :class:`Applies` verdict; declining recipes are accumulated into
    ``considered`` and returned in the all-decline path so Phase 4's
    prompt builder has a structured rejection trace.

    Three terminal outcomes:

    - :class:`MatchedRecipe` — some recipe matched; orchestrator runs the
      matching engine next.
    - :data:`RecipeNotApplicable` with ``reason="ALL_RECIPES_NOT_APPLICABLE"``
      and ``considered=[...]`` — recipes were considered, all declined.
    - :data:`RecipeNotApplicable` with ``reason="NO_RECIPES_REGISTERED"``
      and ``considered=[]`` — zero recipes registered for this plugin
      (distinct dispatch case from "all-declined").

    This walker emits NO events — event emission is the S6-04
    orchestrator's responsibility. The pinned-signature contract (no
    ``event_log`` parameter) is enforced by AC-16's test.
    """
    registered = registry.all(plugin_id)
    if not registered:
        return RecipeNotApplicable(reason="NO_RECIPES_REGISTERED", considered=[])

    considered: list[NotApplies] = []
    for entry in registered:
        verdict = entry.recipe.applies(cve, bundle)
        match verdict:
            case Applies(plan=plan):
                return MatchedRecipe(recipe=entry.recipe, plan=plan)
            case NotApplies() as na:
                considered.append(na)

    return RecipeNotApplicable(reason="ALL_RECIPES_NOT_APPLICABLE", considered=considered)
