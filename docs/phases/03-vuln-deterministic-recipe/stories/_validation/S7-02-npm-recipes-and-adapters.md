# Validation report — S7-02 (four npm recipes + four ADR-0032 npm adapters)

**Validated:** 2026-05-19
**Validator:** `phase-story-validator` skill (automated, scheduled task `story-validation-corrector`)
**Story file:** `docs/phases/03-vuln-deterministic-recipe/stories/S7-02-npm-recipes-and-adapters.md`
**Verdict:** **HARDENED** — substantial edits applied. The story now traces to the real as-built S1-03 (`outcomes.py`), S5-01 (`recipe_engine.py` + `recipe_registry.py`) and S7-01-HARDENED surfaces. No defect required reshaping the goal.

## Why HARDENED, not RESCUE

The story's *goal* — four `RecipeProtocol`-conforming matcher classes plus four ADR-0032 adapters wired into the resolver's `composed_adapters` — is sound, achievable, and traces cleanly to `phase-arch-design.md §C7/§C12`, ADR-0003/0004/0008/0009/0010 and production ADR-0030/0032. Every defect was at the *prescription layer*: wrong method signatures, wrong import paths, invented Literal members, pseudo-OO constructors, and mutation-vulnerable tests. Each was concretely fixable by reference to existing code. Per the validator verdict rubric, this is HARDENED.

## Note on this pass

This was a **two-stage** validation. An earlier run of the same scheduled task hardened the story header, `Depends on`/`ADRs honored` lines, `## Context`, `## References`, `## Goal`, `## Acceptance criteria` and `## Implementation outline`, and recorded the full defect inventory in the in-story `## Validation notes (2026-05-19)` block — but was interrupted before (a) propagating those corrections into the `## TDD plan` and `## Notes for the implementer` sections, and (b) writing this report. This pass completed the interrupted work: the TDD plan and Notes sections, which still carried the pre-validation API, were rewritten to match; this report was authored. The story is now internally consistent end-to-end.

## Context Brief

- **Story snapshot.** Populate the (S7-01-scaffolded) `vulnerability-remediation--node--npm` plugin's empty `recipes/` and `adapters/` directories: four pure-matcher recipe classes registered on `default_recipe_registry`, four structural-typing adapters wrapping Phase-2 probe outputs, plus an additive widening of the `NotApplicableReason` Literal.
- **Sibling lineage.** Consumes S5-01 (`RecipeProtocol` + `RecipeRegistry` + `match_recipes`, Done/GREEN 2026-05-19), S5-02 (`NpmLockfileRecipeEngine` + `ApplicationPlan` widening), S6-04 (orchestrator dispatch), S7-01 (plugin scaffold, HARDENED). Note S7-01 itself is **not yet executed** (no `_attempts/S7-01.md`, no plugin dir) — this story's executor must run after S7-01 lands.
- **Load-bearing commitments implicated.** "Extension by addition" — zero kernel edits; recipes/adapters are plugin-local (ADR-0004). "Facts, not judgments" — recipes are pure matchers, the engine is the worker (ADR-0009). "Honest confidence" — adapter `confidence()` is the consumer-side payoff of `IndexHealthProbe` (B2) staleness (Goal G8, ADR-0008). Sum-type discipline — `Applicability` and `AdapterConfidence` are discriminated unions, never `bool`/`float` (ADR-0010).

## Critic findings (consolidated)

Four critics ran conceptually in parallel — Coverage (`CV`), Test-Quality (`TQ`), Consistency (`CN`), Design-Patterns (`DP`). The defect inventory is reproduced in full in the story's `## Validation notes` block; consolidated and de-duplicated below.

### Block-severity (all addressed by the edit)

| ID | Finding | Resolution |
|---|---|---|
| CN-1 | Recipe class prescribed two methods — `applies(plan) -> Applicability` AND `apply(plan, ctx) -> RecipeOutcome`. Neither signature exists. | `RecipeProtocol` (`recipe_engine.py:95-118`) has class attrs + **one** method `applies(self, cve, bundle) -> Applies \| NotApplies`. Recipe is a pure matcher; the engine is the worker. ACs, TDD plan, Notes rewritten. |
| CN-2 | `applies(plan)` reverses input/output — the plan is the *output*, carried by `Applies(plan=...)`. | All occurrences corrected to `applies(cve, bundle)`; the §Context applicability table re-derived. |
| CN-3 | TDD imports `from codegenie.transforms.applicability import …` — module does not exist. | Canonical home is `codegenie.transforms.outcomes` (S1-03, ADR-0010 Amendment 2026-05-18). All imports corrected. |
| CN-4 | `RecipeOutcome.Applied(...)` / `RecipeOutcome.NotApplicable(...)` pseudo-OO. | `RecipeOutcome` is a discriminated-union `TypeAlias` (`outcomes.py:241`); variants are constructed directly. `Applied` takes a `transform_id: TransformId`, not a `Transform`. ACs rewritten. |
| CN-5 | `NotApplicableReason` invented members (`MAJOR_BUMP_ONLY`, `TRANSITIVE_ONLY`, `PEER_DEP_CONFLICT_UNRESOLVABLE`, …) — Pydantic would reject them. | The closed Literal has exactly six members (`outcomes.py:84-91`). AC-4 widens it **additively** with three new members (`NO_PATCH_IN_RANGE`, `TRANSITIVE_ONLY`, `DIRECT_DEPENDENCY`); existing six byte-identical; Phase-5 snapshot re-bakes. |
| CN-6 | `register_recipe(PluginId, precedence=N)` — `precedence` is not a decorator kwarg. | Decorator signature is `register_recipe(plugin_id, *, registry=None)` (S5-01 AC-6); `precedence: int` is a **class attribute**. ACs + examples corrected. |
| CN-7 | `plugin.recipe_registry.iter(plan)` — no such field/method. | Recipes register on the module-level `default_recipe_registry`; the walker is the module-level `match_recipes(registry, plugin_id, cve, bundle)`. TDD plan rewritten. |
| CN-8 | `AdapterConfidence.High` / `Degraded(reason=ScipIndexStale)` — `High` does not exist; `reason` is `str`. | Variants are `Trusted()` / `Degraded(reason: str)` / `Unavailable(reason: str)` (`outcomes.py:366-411`). ACs use `Trusted()` / `Degraded(reason="scip_index_stale")` etc. |
| CN-9 | `PluginScope.parse` arg drift between directory slug and resolution scope. | S7-01 HARDENED: directory `--node--` IS the `PluginId`; the resolution scope is `--javascript--` (Layer A token). ACs corrected. |
| CN-10 | AC-1 used the underscore form `vulnerability_remediation__node__npm/` for the plugin dir. | The dir is hyphenated (`vulnerability-remediation--node--npm/`, `loader.py:289-293`). Corrected; test code uses `importlib.import_module("plugins.vulnerability-remediation--node--npm.recipes")` since the `import x.y` statement is illegal with hyphens. |

### Harden-severity (addressed)

| ID | Finding | Resolution |
|---|---|---|
| TQ-1 | `test_recipe_registry_dispatches_first_applies_wins` would pass against a recipe returning `Applies(plan=ApplicationPlan())` unconditionally — no field-level discrimination. | TDD plan rewritten: the `Applies` path pins `plan.package`, `plan.transform_kind`, and non-empty `from_version`/`to_version`; the `match_recipes` test pins `recipe_id` + plan fields; the all-decline test pins the `considered` reason sequence in precedence order. |
| TQ-2 | No short-circuit control — a walker that never stops would still pass. | Added the `applies_calls` spy-counter control (mirrors S5-01 AC-10): lower-precedence recipes' `applies_calls == 0` after a higher-precedence match; `== 1` for every recipe on all-decline. Documented as a TDD-plan callout + AC-8. |
| TQ-3 | Adapter `confidence()` covered only the Degraded path with broken types. | AC-13/14/15 + `test_npm_adapters_confidence.py` now cover three states × four adapters = 12 cases; per-adapter `reason` strings pinned by exact equality. |
| TQ-4 | `major-bump-only` mis-classified as `Applies` for `NpmMajorBumpRefuseRecipe`. | The refuse recipe **never** returns `Applies`; AC-7 is a dedicated negative control. The §Context table + the AC-6 coverage matrix were re-derived; the TDD `COVERAGE`/`ALL_DECLINE` dicts mirror them exactly. |
| CV-1 | Fixtures described as JSON "plans" loaded via `load_plan` — recipes consume `(cve, bundle)`. | Renamed to `tests/fixtures/npm_recipes/` with `load_case(name) -> tuple[VulnerabilityRecord, Bundle]`; uses the real `VulnerabilityRecord` / `Bundle` types. |
| DP-1 | Shared semver-range logic risked duplication across four recipes. | Files-to-touch adds `recipes/_semver.py`; the Refactor step hoists duplicated logic, keeping each `applies` body a thin decision chain (functional core / imperative shell). |
| DP-2 | AC-16 fence (`test_adapter_modules_are_pure_read.py`) named in ACs but absent from Files-to-touch. | Added to the Files-to-touch table. |

## Design-pattern assessment

The design is already on the right side of the patterns the task brief calls out, and the edits reinforce that:

- **Plugin architecture / registry + capability.** Recipes register via `@register_recipe(plugin_id)` on a module-level registry; adapters are surfaced via `plugin.adapters()` and merged by the resolver. The kernel (`recipe_engine.py`, `recipe_registry.py`, `resolver.py`) is untouched — extension is purely by addition. ✔
- **Strategy + Open/Closed.** Four recipes are interchangeable strategies behind `RecipeProtocol`; `match_recipes` is closed for modification, open for new recipes. ✔
- **Ports & adapters (hexagonal).** The four ADR-0032 adapters are the ports between the language-agnostic primitive Protocols and the npm-specific probe outputs — structural typing, no inheritance. ✔
- **Sum types / make-illegal-states-unrepresentable.** `Applicability`, `RecipeOutcome`, `AdapterConfidence` are discriminated unions; the validation removed every `bool`/`float`/pseudo-OO regression. ✔
- **Newtype discipline.** `PluginId`, `RecipeId`, `TransformKind`, `PrimitiveName`, `PackageId` used throughout — no raw `str` for domain IDs. ✔
- **Functional core / imperative shell.** Recipes are pure matchers (no I/O); adapters are pure file-readers (AC-16 fences out subprocess imports); the engine is the only impure surface. The `_semver.py` hoist (DP-1) sharpens this. ✔

No new design-pattern gaps surfaced. The one structural risk — primitive-obsession on the `reason` field — was deliberately resolved by ADR-0010 Amendment 2026-05-18 (`reason: str` because Phase-2 vocabulary is disjoint from the Phase-3 orchestrator catalog); the story correctly honors it rather than forcing a closed Literal.

## Residual risks (flagged, not blocking)

- **S7-01 precondition.** S7-01 is HARDENED but not executed. The executor of S7-02 must confirm the plugin directory, `plugin.yaml`, `recipes/__init__.py`, `adapters/__init__.py` and the per-plugin `__init__.py` exist first, or this story is BLOCKED on S7-01.
- **`ApplicationPlan` smart constructors.** AC-5 references `ApplicationPlan.for_npm_semver_bump(...)` and "per-recipe parallels" (`for_npm_peer_dep_coordinated_bump`, `for_npm_transitive_overrides`). Only the first is guaranteed by S5-02; the executor must either confirm S5-02 shipped the parallels or add them as part of this story's additive widening. Called out in the story's Notes/AC-5.
- **`transforms()` TransformKind mapping.** The story leaves "shared engine across three kinds vs. three distinct kinds" as an implementer decision (Notes §TransformKind). Acceptable — both satisfy AC-9 — but the executor must pick one and pin it in the attempt log.

## Verdict

**HARDENED.** The story is internally consistent, traces to real code surfaces, and its TDD plan is mutation-resistant. Ready for `phase-story-executor` once S7-01 has shipped.
