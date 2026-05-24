# Validation report — S7-01 `FallbackTierPlanRecipeEngine` plugin adapter

**Date:** 2026-05-24
**Validator:** `phase-story-validator` (autonomous, scheduled run)
**Story file:** `docs/phases/04-vuln-llm-fallback-rag/stories/S7-01-fallback-tier-plan-recipe-engine.md`
**Verdict:** **HARDENED** — significant edits applied; ready for `phase-story-executor`.

## Context brief (Stage 1)

The story ships `FallbackTierPlanRecipeEngine` as the Phase-3-`RecipeEngine`-shaped adapter the existing plugin's `transforms()['plan']` slot returns. The goal is "zero edits to `src/codegenie/plugins/protocols.py`, `RemediationOrchestrator`, or any Phase-0/1/2/3 kernel file." The adapter wraps `FallbackTier.run` (S6-01) so the orchestrator sees only Phase-3 shapes.

**Authoritative sources read:**
- `src/codegenie/plugins/protocols.py` (`Plugin.transforms() -> dict[TransformKind, RecipeEngine]`)
- `src/codegenie/transforms/recipe_engine.py` (`RecipeEngine.apply(repo: SandboxedPath, plan: ApplicationPlan, capability: NpmInstallCapability) -> RecipeOutcome`)
- `src/codegenie/transforms/outcomes.py` (canonical `RecipeOutcome = Annotated[Applied | Skipped | RecipeNotApplicable | RecipeFailed, ...]` — **four** variants, with structured `RecipeFailed.error: RecipeError`)
- `docs/phases/04-vuln-llm-fallback-rag/ADRs/0003-path-scoped-fence-amendment.md` (path-scoped fence — `src/codegenie/` only)
- `docs/phases/04-vuln-llm-fallback-rag/ADRs/0004-plan-outcome-wraps-recipe-outcome.md` (`PlanOutcome` wraps `RecipeOutcome` — Phase-3 sum type is NOT widened)
- `docs/phases/04-vuln-llm-fallback-rag/phase-arch-design.md` (§Component 14, §Logical view, §Process view, §Design patterns row "FallbackTierPlanRecipeEngine")
- `docs/phases/04-vuln-llm-fallback-rag/High-level-impl.md` (§Step 7)
- `docs/phases/04-vuln-llm-fallback-rag/stories/S6-01-fallback-tier-pipeline.md` (FallbackTier signature + `PlanOutcomeEmitted` ownership)
- `docs/phases/04-vuln-llm-fallback-rag/stories/S1-03-plan-outcome-wraps-recipe-outcome.md` and its `_validation/` report (precedent for `RecipeOutcome` 3-vs-4 variant drift)

## Stage 2 — four critic reports

Four critics ran in parallel (Coverage, Test-Quality, Consistency, Design-Patterns). Aggregate: **8 BLOCK + 13 HARDEN + 3 NIT findings**. All blocks and most hardens applied. Full critic verbatim follows.

### Coverage critic (verdict: 5 block, 5 harden, 1 nit)

Key blocks:
- **CF1 — AC-3 projection table contradicts Phase-3 `RecipeOutcome` shape.** `Applied(transform=t)` does not exist; real shape is `Applied(transform_id, plugin_id, recipe_id)`. `RecipeOutcome.{NotApplicable, Failed}` are mis-named (real: `RecipeNotApplicable`, `RecipeFailed`). `RecipeOutcome` has FOUR variants, not three.
- **CF2 — AC-4 double-emission contradicts S6-01.** S6-01's `FallbackTier.run` owns the terminal `PlanOutcomeEmitted` emit; adapter emitting again would (a) crash the harvester via duplicate events and (b) break S6-01's exact `Counter(kinds)` happy-path AC.
- **CF3 — AC-8 references `plan.recipe_selection.task_class` — field does not exist** on Phase-3 `ApplicationPlan` (which has `summary, package, from_version, to_version, transform_kind` only).

Key hardens:
- **CF4** — "Conforms structurally to RecipeEngine Protocol (mypy --strict accepts assignment without cast)" untested at the runtime/static-check distinction.
- **CF5** — Goal claims "zero edits to RemediationOrchestrator" with no AC enforcing it. Added AC-KERNEL-FROZEN.
- **CF6** — Cassette-replay determinism uncovered. Added AC-DETERMINISM.
- **CF7** — Unexpected-exception behavior unspecified. Added AC-EXCEPTIONS clarifying the closed typed-error list and the no-`except Exception` rule.
- **CF8** — Concurrency contract unspecified. Added AC-REENTRANT.
- **CF9** — AC-11 ("TDD red test exists, committed, green") is content-free. Deleted.
- **CF11** — Plugin-directory `--` separator naming hazard. Added AC-FILE.

### Test-Quality critic (verdict: 4 block, 6 harden, 2 nit)

Key blocks:
- **TF1 — `RecipeOutcome.Applied` does not exist as an attribute.** `RecipeOutcome` is an `Annotated[Union, ...]` alias; `.Applied` raises `AttributeError`. Same mistake for `.NotApplicable`/`.Failed`. Real fix: import variants directly (`from codegenie.transforms.outcomes import Applied, RecipeNotApplicable, RecipeFailed`).
- **TF2 — `RecipeNotApplicable.reason` Literal violation** as documented for CF1.
- **TF3 — Test 4 reads `out.reason`** but `RecipeFailed` carries `error: RecipeError(error_id, message)`. The test would `AttributeError` before reaching its assertion.
- **TF4 — `_with_tier` test seam invented by tests, not in ACs.** Removed entirely; constructor injection only.

Key hardens:
- **TF5** — Tautological structural-conformance test. Replaced with subprocess-mypy fixture pair (mirrors S1-03 AC-9).
- **TF6** — Discriminator-mapping totality test missing. Added (mirrors S1-03 AC-11).
- **TF7** — Event-emission assertion permissive (`[evt] = …`). Replaced with count-delta assertion now that emission is the tier's responsibility.
- **TF8** — Mutation-resistance hole. Rewrote tests with parametrize across every variant + exact-field equality.
- **TF9** — AST import-fence missed `from . import x` (when `node.module=None`) and `level > 0` relative imports. Walker rewritten to handle every shape.
- **TF10** — Property-based opportunity (projection is a pure closed mapping). Surfaced; added totality + purity AST tests in lieu of full Hypothesis run (Rule 2 — full Hypothesis property test would be premature for a 5-arm match).
- **TF11** — Metamorphic idempotence. Added via `test_apply_is_deterministic_under_cassette_replay`.

### Consistency critic (verdict: 5 block, 3 harden, 1 nit)

Reproduces (and reinforces) CF1/CF2/CF3 from Coverage; adds:
- **F4 — `RecipeFailed.error` is structured, not `reason: str`.** Story used `RecipeOutcome.Failed(reason=...)`; real shape is `RecipeFailed(error=RecipeError(error_id, message, details))`. Applied.
- **F7 — `'plan'` raw string vs `TransformKind` newtype.** `Plugin.transforms() -> dict[TransformKind, RecipeEngine]`. Applied — AC-TRANSFORMS-KEY uses `TransformKind("plan")`.
- **F9 — Path-scoped fence relationship.** ADR-0003 covers `src/codegenie/` only; the adapter lives under `plugins/`. AST-import test is the **primary** control, not defense-in-depth. Clarified in AC-FENCE-IMPORT and Notes.
- **F10 — Adapter dep list (10 args) replicates `FallbackTier.__init__`.** Recommended option (A): inject pre-built tier. Applied.

### Design-Patterns critic (verdict: 2 block, 4 harden, 2 nit)

- **DF1 (block) — Adapter constructs `FallbackTier` inline (Dependency Inversion violation).** Resolved by composition-root move: 10-arg constructor → 2-arg `__init__(*, tier)`. Plugin's `transforms()` factory owns substrate assembly.
- **DF2 (block) — `PlanOutcome` emission ownership split.** Resolved per Consistency F5 — adapter emits no events; tier owns `PlanOutcomeEmitted`.
- **DF3 (harden) — Functional core / imperative shell.** Promoted `_project_recipe_application_to_recipe_outcome` from Refactor to AC-PROJECTION + Tier 2 AST purity test.
- **DF4 (block) — AC-8 dead-code defense.** Deleted per CLAUDE.md "trust internal code and framework guarantees".
- **DF5 (harden) — Implementation outline §4 dispatched over wrong shape** (`PlanProposal` vs `ApplicationPlan`/`RecipeApplication`). Rewrote outline.
- **DF6 (harden) — Raw `'plan'` string** → `TransformKind("plan")` per Consistency F7.
- **DF7 (nit) — Rule-of-three watch.** Resisted shared `engine_helpers` extraction. Noted in implementer notes per Rule 2.
- **DF8 (nit) — `harvester` + `confidence_gate` in adapter constructor.** Resolved by composition-root move (DF1).

## Stage 3 — Researcher

**Skipped.** No critic finding was tagged `NEEDS RESEARCH`. Every issue had a canonical fix derivable from in-repo precedent (S1-03 validation report; sibling `NpmLockfileRecipeEngine` / `OpenRewriteRecipeEngine`; established subprocess-mypy idiom).

## Stage 4 — Synthesis + edits

**Conflict-resolution priority** (Consistency > Coverage > Test-Quality > Design-Patterns) applied:
- **Emission ownership** (Consistency F5 vs Design F2): Consistency wins — adapter emits nothing; tier owns the emit. Design F2's "return `(RecipeApplication, PlanOutcome)` from tier" alternative is preserved as an open question in Notes (would need S6-01 amendment — out of scope here).
- **`PlanOutcome` event payload reconstruction** (Design F2): handled implicitly by the no-emit decision; the tier already has the rich payload.
- **Rule-of-three for shared `engine_helpers`** (Design F7): Rule 2 (Simplicity First) wins — three engines but different source types → no extraction. Noted in implementer notes.

**Edits applied (in story file):**

1. **`Status:` line** — `Ready` → `HARDENED (2026-05-24 — phase-story-validator)`.
2. **New `Validation notes` block** under header — single-source summary of every load-bearing change.
3. **Context paragraph rewritten** to fix the "emits PlanOutcome alongside" misclaim; add Composition-Root framing; cite the four-variant `RecipeOutcome` shape; explain the projection-into-`CVE_NOT_IN_DEPENDENCY_SET` decision.
4. **Goal rewritten** — names the four-variant `RecipeOutcome` correctly; says "the adapter emits no events"; says "does not widen `NotApplicableReason`"; uses `TransformKind("plan")`.
5. **Acceptance criteria fully rewritten** (10 named ACs, every one verifiable):
   - AC-FILE (plugin-directory import-resolution)
   - AC-PROTOCOL-CONFORMANCE (runtime isinstance + subprocess mypy)
   - AC-CTOR (constructor injection, keyword-only `tier`, no seams)
   - AC-PROJECTION (pure free function + explicit closed mapping table)
   - AC-EXCEPTIONS (closed typed-error list, no `except Exception`)
   - AC-NO-EMIT (adapter emits zero events)
   - AC-KERNEL-FROZEN (zero edits + `git diff --name-only` assertion)
   - AC-TRANSFORMS-KEY (`TransformKind("plan")` newtype, literal at one site)
   - AC-PROJECTION-TOTALITY (discriminator-mapping totality + subprocess-mypy `assert_never`)
   - AC-FENCE-IMPORT (full-shape AST walker; primary control, not defense-in-depth)
   - AC-DETERMINISM (cassette-replay byte equality)
   - AC-REENTRANT (`asyncio.gather` two independent stub tiers)
   - AC-FAIL-LOUD-CONSTRUCTION (missing `tier` kwarg → `TypeError`)
   - AC-CHECK (`make check` green on 3.11 + 3.12)
6. **Implementation outline rewritten** — adds plugin-import-shim resolution as step 2; corrects the dispatch shape from `PlanProposal` to `RecipeApplication`; ships a complete code skeleton for projector + adapter.
7. **TDD plan fully rewritten** — six test files (projection, purity, totality, assert_never, imports, conformance); no `_with_tier` seam; parametrized across every variant; subprocess-mypy fixtures.
8. **Files to touch table expanded** (6 new entries for the additional test modules).
9. **Notes for implementer rewritten** — Adapter pattern framing; Composition-Root; no private seams; functional-core / imperative-shell; emission ownership; closed `NotApplicableReason`; path-scoped-fence relationship; closed exception contract; budget non-threading; zero kernel edits; subprocess-mypy `assert_never`; plugin directory `--` hazard; Rule-of-three watch.

## Open follow-ups (not patched here)

- **ADR-0004 + `phase-arch-design.md` still describe `RecipeOutcome = Applied | Skipped | Failed`.** The S1-03 validation report already recommended doc correction; this report adds a second voice. Suggest a small doc-amendment PR (out of this story's scope).
- **`Plugin.transforms() -> dict[str, RecipeEngine]` Protocol shape** (raw `str` keys, not `TransformKind`) is itself a primitive-obsession smell on the Phase-3 kernel. Surface to phase-architect for a possible additive widening at the Plugin Protocol surface.
- **Plugin-loader resolution mechanism for `--`-separated directory names** is currently implicit. Worth a brief Phase-3 implementation-doc note so future plugins inherit a consistent resolution path.
- **AC-PROJECTION assumes S6-01 will finalize `RecipeApplication.Applied.transform`** as the field name. If S6-01's hardening renames it (e.g., to `transform_id` or `transform_obj`), the projector's `case TierApplied(transform=t)` line is the only update site.

## Verdict

**HARDENED.** Every BLOCK finding fixed; every HARDEN finding either applied or explicitly deferred to noted follow-ups. The story now has the verifiability + mutation-resistance + extension-by-addition shape that `phase-story-executor` needs to ship safely.
