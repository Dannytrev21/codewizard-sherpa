# ADR-0007: `Recipe.engine` `Literal` extended additively with `"dockerfile"`

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** phase3-contract · recipes · literal-extension · additive-seam
**Related:** [ADR-0001](0001-six-named-additive-seams-and-adr-0028-amendment.md), [ADR-0005](0005-openrewrite-rewrite-docker-deferred.md), [ADR-0009](0009-contract-surface-snapshot-canary.md), [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md)

## Context

Phase 3 shipped `Recipe.engine: Literal["ncu", "openrewrite"]` as a *closed* `Literal` — Pydantic rejects unknown values at deserialization with a typed error. Phase 7's new `DockerfileRecipeEngine` registers under the recipe-engine registry and must match a `Recipe.engine` value (`phase-arch-design.md §Component 4`). The handrolled-only engine choice (ADR-0005 in this phase) means Phase 7 adds exactly one value: `"dockerfile"`.

The closed `Literal` is the canonical "closed-`Literal` wall" the critic named as the load-bearing tension in extension-by-addition (`critique.md §"Where do all three quietly agree on something questionable?"`, §"Which disagreement matters most for this phase?"). Three lens designs took three positions:

- `[P]` silently reused the existing `Literal` and shipped recipes as data — but that doesn't work: the `RecipeMatcher` dispatches on the `engine` field, and unknown engine names would fail Pydantic validation at recipe-load time.
- `[B]` proposed `Recipe.engine: Literal["ncu", "openrewrite", "dockerfile"]` as an additive extension and called it a Phase 3 edit (Open Question #6). The critic landed: this *is* the Phase 3 source edit.
- The synthesizer (`final-design.md §Conflict-resolution row 8`) picked `[B]`'s shape and bundled it under the six-seam discipline (ADR-0001): the closed `Literal` is extended additively, the contract-surface snapshot regenerates in the same PR, and this ADR records the *why*.

Adding a value to a closed `Literal` is a Pydantic-additive change: existing serialized recipes (`engine: "ncu"`, `engine: "openrewrite"`) deserialize identically; existing `RecipeMatcher` callsites are byte-identical when the new value isn't present.

## Options considered

- **Open the `Literal` to `str`.** Behavior-breaking: invalid engine names now fail at runtime (engine-registry lookup) instead of at deserialization. Phase 3's strict typed-contract discipline (`extra="forbid"` + closed `Literal`) is the whole point; opening it for one new engine forecloses every future engine's typed-contract claim.
- **Add `"dockerfile"` to the closed `Literal`.** Behavior-preserving for existing recipes; the contract-surface snapshot diffs at this line; one new ADR (this one) and one Phase 3 source-line edit.
- **Bypass the `Literal` via a custom Pydantic discriminator.** Over-engineered for one new value; obscures the dispatch logic; rejected on `CLAUDE.md` "Simplicity First."

## Decision

Edit `src/codegenie/recipes/contract.py` additively: change `Recipe.engine: Literal["ncu", "openrewrite"]` to `Recipe.engine: Literal["ncu", "openrewrite", "dockerfile"]`. Existing recipes (`ncu`, `openrewrite`) deserialize identically. The contract-surface snapshot (ADR-0009) drifts at this line — regenerated in the same Phase 7 PR alongside this ADR.

## Tradeoffs

| Gain | Cost |
|---|---|
| Recipe `engine` field remains a closed `Literal` — typed-contract discipline preserved; invalid engine names still fail loudly at Pydantic deserialization | The contract-surface snapshot for `Recipe.model_json_schema()` drifts; every later phase that adds a new engine value follows the same pattern (Phase 15 may add `"openrewrite_docker"` if ADR-0005's deferral lands) |
| `RecipeMatcher` dispatches deterministically — `engine == "dockerfile"` routes to `DockerfileRecipeEngine.apply` via the existing `@register_recipe_engine` decorator; no new dispatch logic | The closed-`Literal` wall is *re-painted* every time a new engine arrives — a permanent extension grammar; the discipline holds only via ADR-0001's six-seam constraint |
| `RecipeSelection.reason` is *not* extended (closes critic best-practices.2; see `final-design.md §Conflict row 9`); Phase 7 reuses Phase 3's `"unsupported_dialect"` for image-dialect mismatch, accepting a semantic stretch instead of a second `Literal` edit | The semantic stretch is real — `"unsupported_dialect"` was named for npm dialects; reusing it for Dockerfile dialects relies on the *string* not its origin; future readers may want a domain-specific reason |
| The "additive `Literal` extension" pattern is now part of the six-seam vocabulary (ADR-0001) — Phase 15's recipe-authoring work pattern-matches against this ADR instead of inventing a new shape | Pydantic's `Literal` strictness means schema migrations on persisted recipes (Phase 9 Temporal era) must include the new value; pre-Phase-7 recipes are forward-compatible (no `engine: "dockerfile"` to encounter) |

## Consequences

- `src/codegenie/recipes/contract.py` is on the contract-surface snapshot diff for this Phase 7 PR — regenerated in the same PR with ADR-0009's `pytest --update-contract-snapshot` invocation.
- `tests/unit/recipes/engines/test_dockerfile_engine.py` includes a Pydantic-level test asserting `Recipe(engine="dockerfile", ...)` deserializes successfully and `Recipe(engine="unknown", ...)` raises `ValidationError`.
- `RecipeMatcher` (Phase 3, unchanged) dispatches by `recipe.engine` against the `@register_recipe_engine`-decorated registry; `DockerfileRecipeEngine.name = "dockerfile"` is the join key.
- `RecipeSelection.reason` (closed `Literal` at Phase 3) is *not* edited — image-dialect mismatch reuses `"unsupported_dialect"`. The synthesizer's pick (`final-design.md §Conflict row 9`).
- Phase 15's potential `"openrewrite_docker"` return (per ADR-0005 deferral) follows this exact pattern — new value, new ADR, regenerated snapshot.

## Reversibility

**Medium.** Reverting requires removing `"dockerfile"` from the `Literal` *and* removing the `DockerfileRecipeEngine` registration *and* the three docker catalog recipes. Persisted recipes that reference `engine: "dockerfile"` would fail deserialization. The reversal is bounded but touches Phase 7 user-facing artifacts; not zero-cost.

## Evidence / sources

- `../final-design.md §Conflict-resolution row 8` (Recipe.engine Literal extension)
- `../final-design.md §Conflict-resolution row 9` (RecipeSelection.reason NOT extended)
- `../final-design.md §"Departures #3 ADR-P7-006"` (the seam definition)
- `../phase-arch-design.md §Component 13 ADR-P7-006` (exact diff)
- `../critique.md §best-practices.2` (the `unsupported_image_dialect` closed-Literal violation)
- `../critique.md §"Which disagreement matters most for this phase?"` (the closed-Literal wall)
- [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) — recipe-first → RAG → LLM-fallback
