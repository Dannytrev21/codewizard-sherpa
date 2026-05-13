# ADR-0005: OpenRewrite `rewrite-docker` deferred to Phase 15 — handrolled `dockerfile-parse` engine only

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** recipes · openrewrite · deferred · simplicity-first
**Related:** [ADR-0001](0001-six-named-additive-seams-and-adr-0028-amendment.md), [ADR-0007](0007-recipe-engine-literal-extended-with-dockerfile.md), [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md)

## Context

Phase 3 shipped `OpenRewriteEngineStub` as a deliberate stub — opt-in via `--engine=openrewrite`, registered-but-unavailable when `java` is missing, one smoke-tested recipe. Phase 7's headline deliverable per the roadmap is "Dockerfile base-image swap **and** multi-stage build refactor" — two recipes the OpenRewrite ecosystem advertises via `rewrite-docker`.

The best-practices design proposed `rewrite-docker` as the primary engine with a handrolled fallback (`critique.md §best-practices.4`). The critic landed: best-practices' own Risk #3 admits "`rewrite-docker` covers base-image swaps well and multistage refactors poorly." So the headline harder-recipe always falls through to the handrolled path; the OpenRewrite seat is structurally decorative. None of the three lens designs demonstrated a working `rewrite-docker` invocation on a Chainguard fixture (`critique.md §"Where do all three quietly agree on something questionable?" #3`).

Phase 15 (agentic recipe authoring) is the right home for the re-evaluation: it grows the recipe catalog from solved examples and will need to decide whether OpenRewrite returns as a Java-style first-class engine, an authoring-target intermediate, or a permanent deferral.

## Options considered

- **Ship OpenRewrite `rewrite-docker` as primary engine.** Best-practices' pick. Multi-stage recipe always falls through to handrolled fallback; the primary engine is decorative.
- **Ship a stub like Phase 3's `OpenRewriteEngineStub`.** Registered-but-`available()=False`. Maintains parity with Phase 3's pattern; consumes catalog/test surface with no actual coverage.
- **Drop OpenRewrite from Phase 7 entirely.** Ship handrolled only; Phase 15 re-evaluates. The synthesizer's pick — closes critic best-practices.4 cleanly.

## Decision

Phase 7 ships **one** Dockerfile recipe engine: `DockerfileRecipeEngine` over `dockerfile-parse` (handrolled). No OpenRewrite-shaped engine, no stub, no `rewrite-docker` catalog entries. Phase 15 owns the re-evaluation: if and when `rewrite-docker` proves out on a real multi-stage corpus, it returns as a Phase 15 ADR + a new `RecipeEngine` registration.

## Tradeoffs

| Gain | Cost |
|---|---|
| One engine to test, one engine to fingerprint, one engine to round-trip-verify — the test pyramid is small and full-coverage | Phase 15's recipe authoring inherits the unanswered question "should OpenRewrite return for Docker?" — a deferred design surface |
| Multi-stage refactor ships on the engine that can actually do it (handrolled `dockerfile-parse` AST mutation) — the harder recipe is not decorative | The recipe ecosystem story is now Java-asymmetric: Phase 15 may want OpenRewrite for parity but won't have a Phase 7 baseline to compare against |
| `Recipe.engine` `Literal` extension (ADR-0007 in this phase) adds *one* value (`"dockerfile"`), not two; the contract-surface snapshot diff is smaller | If `rewrite-docker` improves upstream before Phase 15, Phase 7's handrolled engine becomes the "legacy" path users compare against |
| Aligns with `CLAUDE.md` "Simplicity First": one engine that does the job vs two engines where one falls through 50% of the time | Reviewers familiar with Phase 3's stub pattern may expect parity; the choice to *not* ship a stub is documented here so the next reviewer doesn't add one |

## Consequences

- `src/codegenie/recipes/engines/dockerfile_engine.py` is the only new Dockerfile-shaped engine in Phase 7.
- `src/codegenie/recipes/catalog/docker/` contains three handrolled YAML recipes (`distroless_node_swap.yaml`, `distroless_node_multistage.yaml`, `distroless_static_go.yaml`); none reference OpenRewrite.
- `Recipe.engine: Literal["ncu", "openrewrite", "dockerfile"]` adds one value — `"dockerfile"` — and not `"rewrite-docker"` (ADR-0007 in this phase).
- Phase 15 (agentic recipe authoring) owns the re-evaluation; this ADR is the documented hand-off.
- The handrolled engine ships the round-trip safety property (`parse(serialize(parse(x))) == parse(x)`) and the adversarial Dockerfile corpus (≥ 30 fixtures, G13) — Phase 15 gets a test bed to compare any future OpenRewrite-shaped engine against.

## Reversibility

**High.** Re-adding `rewrite-docker` is a new file (`recipes/engines/openrewrite_docker_engine.py`), a new `Recipe.engine` `Literal` value (additive — same pattern as ADR-0007), and a new ADR. The handrolled engine continues to work either way. The cost of reversal is only the Phase 15 design work this ADR was meant to defer.

## Evidence / sources

- `../final-design.md §Conflict-resolution row 18` (OpenRewrite `rewrite-docker` shipped)
- `../final-design.md §"Departures #3 ADR-P7-004"` (pure deferral)
- `../phase-arch-design.md §Component 4` (DockerfileRecipeEngine — no OpenRewrite path)
- `../phase-arch-design.md §Component 13 ADR-P7-004` (pure deferral)
- `../critique.md §best-practices.4` (the OpenRewrite primary-engine attack)
- `../critique.md §"Where do all three quietly agree on something questionable?" #3` (no working migration verified)
- [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) — recipe-first ordering
