# ADR-0003: Ship two recipe engines — `NcuRecipeEngine` (default) and `OpenRewriteEngineStub` (registered, opt-in, JVM-gated)

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** recipe-engine · openrewrite · ncu · synthesizer-departure · phase-15-anchor · roadmap-fit
**Related:** ADR-0001, ADR-0004, ADR-0013, [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md), [production design.md §2.4](../../../production/design.md)

## Context

The roadmap Phase 3 line names OpenRewrite first ("OpenRewrite recipes for npm dependency updates (or `npm-check-updates` as a simpler first cut...)") (`docs/roadmap.md §"Phase 3"`). The three competing designs went three different directions: performance-first reframed recipes as `stdlib JSON mutation` for throughput, ditching the engine abstraction entirely; best-practices shipped only `ncu` and deferred OpenRewrite behind an ABC with one implementation; security-first kept OpenRewrite but with an unspecified "signed-manifest ceremony" and a `tools/maven-mirror/` of undocumented custody.

The critic dismantled all three (`critique.md §"Cross-design observations" §"Which disagreement matters most for this phase?"`): performance-first leaves Phase 4 no failure surface and Phase 15 no recipe ecosystem (`§"Attacks on performance-first" #1`); best-practices ships without OpenRewrite at all, leaving Phase 15's authoring target constrained to "agent writes new YAML that parameterizes `ncu`" — a much shallower deliverable (`§"Attacks on best-practices" #1`); security-first's OpenRewrite ceremony has unspecified key custody, no upgrade story, and the operational tax may not survive a real install on a developer laptop (`§"Attacks on security-first" #3`).

The synthesis treats this as the most consequential phase-3 choice (`final-design.md §"Lens summary"`, `§"Synthesis ledger"` row "Recipe engine default"). It is also the one decision that determines whether Phase 4, Phase 7, and Phase 15 inherit a recipe ecosystem or a recipe stub.

## Options considered

- **`ncu` only [B].** Ship one engine. Roadmap says OpenRewrite first. Phase 15 authoring is constrained to ncu parameterizations.
- **OpenRewrite only with full Maven mirror + signed-manifest ceremony [S].** Honors roadmap. Adds unspecified ceremony custody, a built+pinned Maven mirror, and a key-rotation upgrade path Phase 3 is too small to own.
- **Stdlib JSON mutation, no engine ABC [P].** Cheapest. Defeats `production/design.md §2.4` (recipes-as-data). Phase 15 has no engine ecosystem.
- **Two engines: `ncu` default + `OpenRewriteEngineStub` registered (one recipe, no Maven mirror, opt-in) [synth].** Honors the roadmap's named OpenRewrite seat. Bounds operational burden (one pinned jar, one recipe, opt-in via `--engine=openrewrite`). Proves the contract extends. Phase 15 has a recipe-engine ecosystem to author into.

## Decision

**Phase 3 ships two `RecipeEngine` implementations in v0.3.0:**

1. **`NcuRecipeEngine` — default for all `(ecosystem=npm, kind=version_bump)` recipes.** Calls `ncu --packageFile package.json --upgrade --target patch --filter <pkg>`; defers lockfile generation to the `LockfileResolver`. On-PATH check at startup (ADR-0013); pinned digest in `tools/digests.yaml`.
2. **`OpenRewriteEngineStub` — registered, opt-in via `--engine=openrewrite`.** Requires `java` on PATH and a pinned `tools/openrewrite/<digest>.jar`. Ships **one** smoke-tested recipe (candidate: `org.openrewrite.npm.UpgradeDependencyVersion`-shaped — implementer may roll a minimal internal recipe under the same engine contract if the npm OpenRewrite ecosystem is too thin). If `java` or the jar is missing, the engine registers as **unavailable**; the selector emits `RecipeSelection(reason="no_engine")` (ADR-0004) rather than failing the run. **No Maven runtime resolution.** The stub is a single-recipe JVM invocation against the pinned jar.

**The `OpenRewriteEngineStub` is a contract anchor, not a feature.** Coverage is intentionally narrow in v0.3.0 (one recipe). The point is the contract, not the catalog. Phase 4 and Phase 7 expand it; Phase 15 authors against it.

**No Maven mirror.** `tools/maven-mirror/` is NOT introduced in Phase 3. The signed-manifest ceremony from `design-security.md` is explicitly rejected. Any phase that needs full OpenRewrite Maven resolution must surface a new ADR (likely Phase 7 or later).

## Tradeoffs

| Gain | Cost |
|---|---|
| Roadmap's OpenRewrite seat is honored — Phase 3 is not the phase that drops it | OpenRewrite coverage is one recipe in v0.3.0 — feature parity with ncu is years away and may never close |
| Phase 15's agent-authored recipes have an OpenRewrite-shaped target — a richer ecosystem to author into than ncu parameterizations | OpenRewrite recipe authoring tooling for npm is genuinely thin; the implementer may need to roll a minimal internal recipe shape |
| Phase 7's distroless recipes can extend the engine ABC additively (Dockerfile-shaped OpenRewrite or a Docker-specific engine) — same registry pattern | Two engines doubles the engine-availability test matrix; `OpenRewriteEngineStub` CI runs are JVM-gated and skipped on developer laptops without `java` |
| `NcuRecipeEngine` is the throughput default — npm bump remediation never pays JVM cold-start cost in the common case | The default-vs-opt-in split means the test suite must cover both paths; integration test `test_remediate_openrewrite_stub_e2e.py` skips when java unavailable |
| Engine `available()` is captured once at orchestrator entry (`phase-arch-design.md §"Gap analysis" §"Gap 6"`); the transform reads the snapshot, not by re-calling | Phase 9 (Temporal) inherits the snapshot through the Activity payload; cross-Activity environment flux is not modeled in Phase 3 |
| No Maven mirror, no signed-manifest ceremony — `localv2.md` "single Python project, no services" invariant holds | The first phase that needs full OpenRewrite Maven resolution pays the ceremony cost in one phase, not amortized across Phase 3–7 |
| `recipes-as-data` (`production/design.md §2.4`) preserved end-to-end: recipes are YAML; engine selection is data; engine implementation is code | `Recipe.engine` field is a Pydantic literal — adding a third engine kind requires updating the literal and the registry simultaneously |

## Consequences

- `src/codegenie/recipes/engine.py` defines the ABC, `NcuRecipeEngine`, and `OpenRewriteEngineStub`.
- `tools/digests.yaml` extends with `npm`, `ncu`, and the OpenRewrite jar digest (ADR-0014).
- `tools/openrewrite/<digest>.jar` is committed (or fetched-and-verified at install time per Phase 2 ADR-0004 precedent).
- `ALLOWED_BINARIES` (Phase 2 ADR-0005) extends with `npm`, `ncu`, and `java` — `java` flagged as opt-in (ADR-0014).
- `recipes/catalog/npm/*.yaml` recipes declare their `engine` field; the selector filters by engine availability (ADR-0004).
- Integration test `tests/integration/test_remediate_openrewrite_stub_e2e.py` runs only in CI matrix entries with `java` available; otherwise skips with reason.
- The CLI's `--engine={ncu,openrewrite}` flag is the explicit opt-in for the stub.
- Phase 15's recipe-authoring loop targets both engines; agent-authored OpenRewrite recipes update `recipes/digests.yaml` (ADR-0011) and any required jar pins.
- The `phase-arch-design.md §"Gap analysis" §"Gap 6"` engine-availability snapshot is captured at `RemediationAttempt.engine_availability` and read by the transform.

## Reversibility

**Medium.** Removing `OpenRewriteEngineStub` later (if Phase 15 finds the contract is fine to author against without an OpenRewrite anchor) is mechanically additive — drop the implementation, remove the jar pin, update the CLI flag. Adding a third engine (e.g., a Docker-specific engine for Phase 7) is purely additive — same `@register_engine` pattern. The decision *to ship two engines now* is the load-bearing piece; reversing it (dropping one or both) requires a Phase 3 ADR amendment and downstream consumer review. Adding the full Maven mirror later is a Phase-7-or-later ADR; doing it in Phase 3 retroactively would require new ceremony and is high-cost.

## Evidence / sources

- `../final-design.md §"Lens summary"` — the synth's "departure from all three" rationale
- `../final-design.md §"Goals" §"Contract goals"` row 4 — two-engine commitment
- `../final-design.md §"Components" #2 "RecipeEngine ABC with two impls"`
- `../final-design.md §"Synthesis ledger" §"Conflict-resolution table"` row "Recipe engine default" (sum=12)
- `../final-design.md §"Departures from all three inputs"` #1
- `../phase-arch-design.md §"Component design" #2 "RecipeEngine ABC + two implementations"`
- `../phase-arch-design.md §"Gap analysis" §"Gap 6 — Engine availability check happens twice"`
- `../critique.md §"Cross-design observations" §"Which disagreement matters most for this phase?"`
- `../critique.md §"Attacks on best-practices" #1`, `§"Attacks on security-first" #3`, `§"Attacks on performance-first" #1`
- `docs/roadmap.md §"Phase 3"` — "OpenRewrite recipes for npm dependency updates (or `npm-check-updates` as a simpler first cut)"
- [production ADR-0011](../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md) — recipe-first planning
