# ADR-0013: Dockerfile transforms use pure-Python `dockerfile-parse`, not OpenRewrite

**Status:** Accepted
**Date:** 2026-05-19
**Tags:** strategy · jvm-tax · convention-split · determinism
**Related:** [0012](0012-dockerfile-policy-gate-strict-and-no-override.md), [0014](0014-multi-stage-refactor-recipe-synchronous.md), [0015](0015-allowed-binaries-amendment-dive-buildx.md), [Phase 3 ADR-0009](../../03-vuln-deterministic-recipe/ADRs/0009-recipe-engine-protocol-with-two-implementations-day-1.md)

## Context

Phase 3 shipped `RecipeEngine` Protocol with two implementations: `NpmLockfileRecipeEngine` (production, ships diffs) and `OpenRewriteRecipeEngine` (scaffold for future language-level transforms). [Phase 3 ADR-0009](../../03-vuln-deterministic-recipe/ADRs/0009-recipe-engine-protocol-with-two-implementations-day-1.md) establishes OpenRewrite as the engine for future structural transforms.

Phase 7's recipes are different: pure Dockerfile edits — base-image swap, multi-stage refactor. The three lens designs all converged on **`dockerfile-parse` (pure-Python AST manipulation)** instead of OpenRewrite's JVM-hosted recipe engine. The reasoning is concrete:

- **JVM cold-start tax.** OpenRewrite is JVM-hosted. Each per-workflow startup is ~2 s. Phase 7's per-workflow wall-clock budget is tight; adding 2 s for a single-stage Dockerfile swap (which `dockerfile-parse` does in ≤ 80 ms) is asymmetric cost.
- **OpenRewrite Dockerfile support is immature.** Its language-level Java/Kotlin/etc. recipes are the load-bearing case; Dockerfile recipes are an open community project.
- **Determinism.** Pure-Python `dockerfile-parse` AST manipulation is deterministic and reviewable; OpenRewrite recipes for Dockerfile would require building a Recipe class and managing the OpenRewrite resource model.

The critic raised a real concern (Perf-3 hidden assumption): "Phase 3's `OpenRewriteRecipeEngine` stub is the established recipe engine; Phase 7 picks a *different* engine for a *different* file type, which Phase 8/12/15 will inherit as 'two engines is fine.' The convention-drift cost is borne by every later phase. Performance-first acknowledges no precedent obligation here." `final-design.md §Components §9` records the engine-split rationale explicitly: `dockerfile-parse` for Dockerfile recipes, OpenRewrite stays the engine for Phase 8+ language-level transforms. The split is named, not silent.

## Options considered

- **Option A — `dockerfile-parse` (pure-Python AST manipulation).** All three lens designs converged on this. **Pattern:** Strategy — engine selected per file type. Picks the right tool for the file type; pays the convention-split cost.
- **Option B — OpenRewrite Dockerfile recipes.** Reuses Phase 3's `OpenRewriteRecipeEngine` engine. **Pattern:** Strategy — one engine for all transforms. Honors the established precedent; pays the JVM cold-start tax (~2 s); inherits OpenRewrite's immature Dockerfile recipe support.
- **Option C — Regex-based Dockerfile rewriting.** **Pattern:** Pattern-matching. Lossy on multi-stage; brittle on heredocs and ARG-driven FROM; no AST.

## Decision

Adopt **Option A** with the engine-split rationale explicitly recorded. Phase 7's two Dockerfile recipes (`DockerfileBaseImageSwapTransform`, `DockerfileMultiStageRefactorTransform`) use pure-Python `dockerfile-parse` AST manipulation. They extend Phase 3's `Transform` ABC. They do **not** plug into the `OpenRewriteRecipeEngine` scaffold. The engine split is named: `dockerfile-parse` for Dockerfile-format recipes; OpenRewrite remains the engine for Phase 8+ language-level transforms (Java/Kotlin/etc. recipes). `dockerfile-parse` is the one net-new runtime Python dependency Phase 7 introduces; it is added under the fence allowlist ([0009](0009-phase-7-byte-edit-allowlist-fence.md) row #9).

## Tradeoffs

| Gain | Cost |
|---|---|
| No JVM cold-start tax — per-workflow wall-clock budget holds (swap recipe ≤ 80 ms; multi-stage ≤ 350 ms) | Two engines in the codebase: `dockerfile-parse` for Dockerfile, OpenRewrite for Java/Kotlin. Convention split is named in this ADR; future engineers don't argue "which engine?" |
| Pure-Python AST manipulation is reviewable; the diffs are byte-deterministic; property-test idempotence | `dockerfile-parse` is a third-party dep with its own bug surface (heredocs, ARG-driven FROM — see `phase-arch-design.md §Edge cases #13`). Mitigated: unparseable Dockerfile → `TransformOutcome(kind="not_applicable", reason="dockerfile_parse_failed")`, HITL |
| One new Python dep (`dockerfile-parse`); the fence allowlist authorizes the `pyproject.toml` edit explicitly | A future case where a Dockerfile recipe interacts with Java/Kotlin recipe (cross-language workflow) would need both engines wired up; that's a Phase 8+ design problem |
| Determinism guarantees mirror Phase 3's recipe discipline: same inputs → same diff, byte-equal across runs | OpenRewrite's broader Dockerfile recipe community is bypassed; if/when their Dockerfile recipes mature, switching engines is a separate ADR |
| Aligns with [production §2.4 Determinism over probabilism for structural changes](../../../production/design.md) — the AST is pure data, transforms are functions, no LLM | Some operators may expect "the recipe engine is OpenRewrite" by Phase 3 ADR-0009 precedent; this ADR is the explicit divergence |

## Pattern fit

Implements **Strategy via configuration** (toolkit §Behavioral — engine selection per file-type domain): `RecipeEngine` Protocol per file type, not per workflow. Also instantiates **Right tool, named tradeoff** (toolkit §Architecture / boundaries — convention splits are documented, not silent). [Phase 3 ADR-0009](../../03-vuln-deterministic-recipe/ADRs/0009-recipe-engine-protocol-with-two-implementations-day-1.md)'s "two implementations on day one" precedent is honored: Phase 7's engine adds a third row to the same conceptual matrix.

## Consequences

- `plugins/distroless-migration--node--npm/recipes/dockerfile_base_image_swap.py` and `.../dockerfile_multi_stage.py` use `dockerfile-parse` directly; neither plugs into `OpenRewriteRecipeEngine`.
- `pyproject.toml` gains `dockerfile-parse` as the **one** net-new runtime Python dep (fence allowlist row #9). Pinned version in `uv.lock`.
- Both recipes extend Phase 3's `Transform` ABC; they use `ApplyContext`, `TransformOutcome` per Phase 3 ADR-0001.
- Unparseable Dockerfile cases (heredocs, ARG-driven FROM, etc.) → `TransformOutcome(kind="not_applicable", reason="dockerfile_parse_failed")` per `phase-arch-design.md §Edge cases #13`. Routes to universal HITL.
- Property tests assert idempotence (applying the same diff twice is a no-op).
- The engine-split convention is named in this ADR's prose, in `final-design.md §Components §9`, and in the plugin's recipes/`README.md` (or equivalent). Future phases discovering a Dockerfile recipe need can use `dockerfile-parse` directly without re-litigating the engine choice.
- OpenRewrite's `OpenRewriteRecipeEngine` stub from Phase 3 remains in place untouched — Phase 8+ language-level transforms still target it.
- A future Phase 8+ ADR may revisit the split if OpenRewrite's Dockerfile recipes mature; the cost would be a recipe-by-recipe migration, not a wholesale engine change.

## Reversibility

**Medium.** Migrating Phase 7's two recipes from `dockerfile-parse` to OpenRewrite would be a per-recipe rewrite plus accepting the JVM cold-start cost — recipe-by-recipe, no kernel impact. The convention split is conceptual; reversing it (consolidating on OpenRewrite for all file types) is a multi-phase coordination plus per-recipe migration. The `dockerfile-parse` dep itself is removable when the last consumer migrates.

## Evidence / sources

- `../final-design.md §Components §9` (`DockerfileBaseImageSwapTransform` — engine choice + ADR-0005 placeholder for the split rationale), §10 (`DockerfileMultiStageRefactorTransform`), §Goals ("Dockerfile recipes ship as deterministic `Transform` subclasses […] pure-Python AST manipulation via `dockerfile-parse`")
- `../phase-arch-design.md §Component design §11` (`DockerfileBaseImageSwapTransform` + `DockerfileMultiStageRefactorTransform`), §Tradeoffs (consolidated) row "`dockerfile-parse` recipe engine"
- `../critique.md §Attacks on the performance-first design "Hidden assumptions §3"` (OpenRewrite immaturity vs convention drift)
- [Phase 3 ADR-0009 — RecipeEngine Protocol with two implementations day 1](../../03-vuln-deterministic-recipe/ADRs/0009-recipe-engine-protocol-with-two-implementations-day-1.md)
- [production §2.4 — Determinism over probabilism for structural changes](../../../production/design.md)
