# Story S7-02 — Four npm recipes + four ADR-0032 npm language search adapters

**Step:** Step 7 — First production plugin, universal HITL fallback plugin, synthetic third plugin
**Status:** HARDENED (validated 2026-05-19; see `_validation/S7-02-npm-recipes-and-adapters.md`)
**Effort:** L
**Depends on:** S5-01 (`RecipeRegistry` + `@register_recipe(plugin_id)` + `RecipeProtocol` matcher contract — `applies(cve, bundle) -> Applicability`; `match_recipes(registry, plugin_id, cve, bundle)` walker), S5-02 (the `NpmLockfileRecipeEngine` production engine; the additive widening of `ApplicationPlan` with `package`/`from_version`/`to_version`/`transform_kind` fields + `ApplicationPlan.for_npm_semver_bump(...)` smart constructor — the four recipes' `Applies(plan=...)` payloads use these), S6-04 (`RemediationOrchestrator` — the recipe→engine dispatch path is the consumer of `MatchedRecipe.plan` + `engine.apply(repo, plan, capability)` two-stage flow), S7-01 (the plugin directory + `plugin.yaml` with `contributes.adapters` import paths must already exist for the adapter modules to drop into)
**ADRs honored:** [ADR-0003](../ADRs/0003-plugin-resolution-and-universal-fallback-semantics.md) (the recipes' `applies(cve, bundle) -> Applicability` returns a tagged-union variant, never a `bool` — the per-plugin `RecipeRegistry` mirrors the kernel's tagged-union discipline), [ADR-0004](../ADRs/0004-plugin-private-capabilities-via-tccm.md) (the four adapters are plugin-local; they implement the *generic* ADR-0032 Protocols but live under `plugins/vulnerability-remediation--node--npm/adapters/` — no kernel edits), [ADR-0009](../ADRs/0009-recipe-engine-protocol-with-two-implementations-day-1.md) (the recipes are pure matchers; the engine `NpmLockfileRecipeEngine.apply(repo, plan, capability)` does the transformation work — `OpenRewriteRecipeEngine` is the scaffold confirming the Protocol takes >1 implementation), [ADR-0010](../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md) (`Applicability = Applies(plan) | NotApplies(reason)` is a Pydantic discriminated union; `NotApplicableReason` is a closed `Literal` widened additively by this story; `AdapterConfidence = Trusted | Degraded | Unavailable` with `reason: str` per the 2026-05-18 amendment), [ADR-0010 Amendment 2026-05-18](../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md#amendments) (`AdapterConfidence` canonical home + `reason: str` discipline — Phase-2 vocabulary disjoint from Phase-3 orchestrator vocabulary), [ADR-0008](../ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md) (adapters' `confidence()` is the input to the BundleBuilder's deterministic serial fallback decision; degraded confidence triggers TCCM-declared substitution)

## Validation notes (2026-05-19)

Hardened by `phase-story-validator` (see `_validation/S7-02-npm-recipes-and-adapters.md` for the full audit). The original draft contained nine BLOCK-class contract drifts against the as-built S1-03 (`outcomes.py`), S5-01 (`recipe_engine.py` + `recipe_registry.py`), S5-02 (`ApplicationPlan` widening), and S7-01 HARDENED. Resolved edits:

- **Recipe Protocol surface (BLOCK).** The original draft prescribed two methods on each recipe class — `applies(plan) -> Applicability` AND `apply(plan, ctx) -> RecipeOutcome`. Neither signature exists. Per S5-01 hardened, `RecipeProtocol` has class attributes (`recipe_id`, `name`, `kind`, `precedence`) and **exactly one** method: `applies(self, cve: VulnerabilityRecord, bundle: Bundle) -> Applies | NotApplies`. The recipe is a *pure matcher*; the engine (`NpmLockfileRecipeEngine`) is the *worker* with `async apply(self, repo, plan, capability) -> RecipeOutcome`. ACs and TDD plan rewritten throughout to remove the `recipe.apply(...)` shape; the orchestrator's two-stage flow (`match_recipes → MatchedRecipe(recipe, plan) → plugin.transforms()[recipe.kind].apply(repo, plan, capability)`) is documented in the §Context dispatch diagram and the Notes-for-implementer "Recipes are pure matchers" bullet.
- **`applies(plan)` is wrong; it is `applies(cve, bundle)` (BLOCK).** The plan is the *output* (carried by `Applies(plan=ApplicationPlan(...))`); the recipe consumes a CVE record + a context bundle and *produces* the plan. The original draft's table of "When `applies(plan)` returns" reversed input/output; rewritten.
- **`Applicability` import path (BLOCK).** Original TDD draft imports `from codegenie.transforms.applicability import Applies, NotApplies` — the module does not exist. Per S1-03 + ADR-0010 Amendment 2026-05-18, the canonical home is `codegenie.transforms.outcomes`. All TDD imports corrected.
- **`RecipeOutcome` pseudo-OO (BLOCK).** Original draft uses `RecipeOutcome.Applied(NpmLockfileTransform)` and `RecipeOutcome.NotApplicable(reason=MAJOR_BUMP_REFUSE)`. `RecipeOutcome` is a `TypeAlias = Annotated[Applied | Skipped | RecipeNotApplicable | RecipeFailed, Field(discriminator="kind")]` per `outcomes.py:241`; the variants are constructed directly (`Applied(transform_id=..., plugin_id=..., recipe_id=...)`, `RecipeNotApplicable(reason=..., considered=[...])`). Also, `Applied` takes a `transform_id: TransformId`, **not** a `Transform` instance — the transform itself is the second tuple element from `engine.apply()` per S5-02 (`tuple[RecipeOutcome, NpmLockfileTransform | None]`). ACs rewritten.
- **`NotApplicableReason` Literal is closed (BLOCK).** Original draft uses `NO_PATCH_IN_RANGE`, `MAJOR_BUMP_ONLY`, `TRANSITIVE_ONLY`, `PEER_DEP_CONFLICT_UNRESOLVABLE` — **none** are members. The canonical Literal (per `outcomes.py:84-91`) is exactly six: `PEER_DEP_CONFLICT`, `MAJOR_BUMP_REFUSE`, `OVERRIDES_AMBIGUOUS`, `RECIPE_CATALOG_MISS`, `ALL_RECIPES_NOT_APPLICABLE`, `NO_RECIPES_REGISTERED`. Pydantic would reject every invented value at construction.
  **Resolution:** widen the Literal *additively* in this story with three new members: `NO_PATCH_IN_RANGE`, `TRANSITIVE_ONLY`, `DIRECT_DEPENDENCY`. The widening is an ADR-0001 / ADR-0010 amendment trigger; the Phase-5 contract snapshot at `tests/integration/test_phase5_contract_snapshot.py` re-bakes (this story's PR description names the regeneration; mirrors the S5-01 + S5-02 amendment pattern). Existing six members preserved byte-identical.
  Per-recipe reason mapping after widening:
  - `NpmLockfileSemverBumpRecipe.applies → NotApplies(reason)`: `NO_PATCH_IN_RANGE` / `MAJOR_BUMP_REFUSE` / `PEER_DEP_CONFLICT` / `TRANSITIVE_ONLY`.
  - `NpmPeerDepConflictRecipe.applies → NotApplies(reason)`: `NO_PATCH_IN_RANGE` (no patch in range; nothing for the peer-dep variant to coordinate); declines on non-peer-conflict cases by deferring to the simple bump (lower-precedence recipe wins via the walker's first-`Applies` discipline; not a separate reason).
  - `NpmTransitiveOverridesRecipe.applies → NotApplies(reason)`: `DIRECT_DEPENDENCY` (defers to the simple bump) / `OVERRIDES_AMBIGUOUS` (the pinned override would still resolve a vulnerable version) / `NO_PATCH_IN_RANGE`.
  - `NpmMajorBumpRefuseRecipe.applies → NotApplies(reason)`: `MAJOR_BUMP_REFUSE`. **The refuse recipe NEVER returns `Applies(plan)`** — its job is to be the typed escalation signal in `RecipeNotApplicable.considered`; Phase 4 reads `considered[-1].reason == "MAJOR_BUMP_REFUSE"` to dispatch LLM-assisted major-bump migration.
  (Per-recipe applicability table in §Context rewritten accordingly.)
- **`register_recipe(PluginId, precedence=N)` is wrong (BLOCK).** Per S5-01 AC-6, the decorator signature is `register_recipe(plugin_id: PluginId, *, registry: RecipeRegistry | None = None)`. **Precedence is a class attribute** on the recipe class (`precedence: int`), NOT a decorator kwarg. ACs and example code corrected.
- **`plugin.recipe_registry.iter(plan)` does not exist (BLOCK).** Recipes register globally on `default_recipe_registry` keyed by `plugin_id`; the walker is the module-level function `match_recipes(registry, plugin_id, cve, bundle) -> MatchedRecipe | RecipeNotApplicable`. There is no per-plugin `recipe_registry` field. ACs and TDD plan rewritten to call `match_recipes(default_recipe_registry, PluginId("vulnerability-remediation--node--npm"), cve, bundle)`.
- **`AdapterConfidence` variant names (BLOCK).** Original draft uses `AdapterConfidence.High` (does not exist; it is `Trusted()`), `Degraded(reason=ScipIndexStale)` (reason is `str` after the 2026-05-18 amendment — `"scip_index_stale"`, not a class instance), and `Unavailable(reason=...)` typed similarly. Phase-2 emits free-form vocabulary (`"scip_unavailable"`, `"tool_missing"`, `"self_check"`, `"scip_offline"`); Phase-3's orchestrator-domain catalog (`DegradationReason`, `UnavailabilityReason`) is *advisory*, not the field type. ACs and TDD plan corrected to use `Trusted()` / `Degraded(reason="scip_index_stale")` / `Unavailable(reason="scip_binary_missing")`.
- **`PluginScope.parse` arg mismatch (BLOCK).** S7-01 HARDENED settled on directory `--node--` (human readability) and manifest `languages: javascript` (Layer A token). The scope used for resolution is `vulnerability-remediation--javascript--npm`; the directory slug `vulnerability-remediation--node--npm` IS the `PluginId`. ACs corrected: `PluginScope.parse("vulnerability-remediation--javascript--npm").unwrap()` for resolution; `PluginId("vulnerability-remediation--node--npm")` for the registry key.
- **`PrimitiveName(scip)` unquoted (HARDEN).** All four occurrences corrected to `PrimitiveName("scip")` / `PrimitiveName("import_graph")` / etc.
- **TDD plan mutation-resistance hardening (HARDEN).** Original `test_recipe_registry_dispatches_first_applies_wins` would pass with a recipe that returns `Applies(plan=ApplicationPlan())` for every fixture (no field-level discrimination). Tests rewritten to assert (a) the matched recipe's `recipe_id` exactly, (b) the `plan.package` / `plan.from_version` / `plan.to_version` / `plan.transform_kind` field values exactly (post-S5-02 widening), (c) for the all-decline fixtures the `RecipeNotApplicable.considered` list contains the expected per-recipe `NotApplies.reason` sequence in precedence order, and (d) the lowest-precedence recipe's `applies_calls == 0` after a higher-precedence match (positive + negative short-circuit control, mirroring S5-01 AC-10).
- **Adapter degradation cross-check hardening (HARDEN).** Original AC asserted `confidence() == AdapterConfidence.Degraded(reason=ScipIndexStale)` (broken types). Replaced with: each adapter, given a synthesized `IndexHealthProbe.freshness_for_layer(...)` returning a stale verdict, returns `Degraded(reason="<adapter>_index_stale")` where the per-adapter `reason` strings are pinned. Also added a positive control (`Trusted()` when fresh) and a missing-output control (`Unavailable(reason="<adapter>_output_missing")`) per adapter — three states × four adapters = 12 unit cases.
- **Adapter test_inventory primitive name (HARDEN).** Original AC inconsistently uses `test_inventory` (manifest key per ADR-0032) vs `TestInventoryAdapter` (class). Pinned the manifest key as `PrimitiveName("test_inventory")` (per `plugin.yaml` from S7-01) and the class as `JestTestInventoryAdapter`.
- **`PLUGINS.lock` regen path (HARDEN).** Cite S2-03's `compute_plugin_tree_digest` + `LockFile.from_path` (both `Result`-returning) — NOT the old `compute_plugin_tree_sha256` / `read_plugins_lock` shorthand. The pre-commit auto-regen hook (if shipped) MUST be verified by hand; the commit message names whether the helper or hand-computation was used (mirroring S7-01 AC-4 discipline).
- **Engine wiring through `transforms()` (CLARIFY).** The plugin's `transforms()` must return a `dict[TransformKind, RecipeEngine]` keyed by **each recipe's `kind`** so the orchestrator can dispatch `plugin.transforms()[matched_recipe.recipe.kind].apply(repo, plan, capability)`. For Phase 3, all three production recipes use `TransformKind("npm-lockfile-semver-bump")` (or three distinct kinds — the recipes share the engine but each kind triggers a different engine path) — see Notes-for-implementer §"TransformKind discipline" for the chosen mapping.

The story's *goal* (four matchers + four ADR-0032 adapters wired into the resolver's `composed_adapters`) is intact and traces to the phase arch + ADRs cleanly; the contract drift was at the prescription layer, not the design layer.

## Context

S7-01 landed the plugin's manifest + TCCM + `register_plugin(...)` call but left `adapters/` and `recipes/` empty. This story populates both. It's the only `L`-sized Step-7 story because volume dominates: **four** `RecipeProtocol`-conforming matcher classes each with non-trivial `applies(cve, bundle) -> Applicability` logic, **four** ADR-0032 adapter implementations wrapping Phase 2's structural probes (`scip`, `import_graph`, `dep_graph`, `test_inventory`), plus plugin-local registration via `@register_recipe(PluginId("vulnerability-remediation--node--npm"))` against the global `default_recipe_registry` from S5-01.

**Recipes are pure matchers** (per S5-01 `RecipeProtocol`): they consume a `VulnerabilityRecord` + a `Bundle` (the BundleBuilder's output carrying `dep_graph.consumers`, `scip.refs`, `import_graph.reverse_lookup`, `test_inventory.tests_exercising` results) and return `Applies(plan=ApplicationPlan(...))` or `NotApplies(reason)`. The recipe **does not** open files, run subprocesses, or mutate state — that is the engine's job. The orchestrator's two-stage dispatch is:

```
match_recipes(default_recipe_registry, PluginId("vulnerability-remediation--node--npm"), cve, bundle)
  └─ MatchedRecipe(recipe, plan)            # first-Applies-wins; precedence-ordered
        └─ plugin.transforms()[recipe.kind].apply(repo, plan, capability)
              └─ RecipeOutcome (Applied | Skipped | RecipeNotApplicable | RecipeFailed)
```

The four recipes (sorted by precedence descending):

| Recipe | `precedence` | `kind` | `applies(cve, bundle)` returns `Applies(plan=...)` when | …returns `NotApplies(reason)` when |
|---|---|---|---|---|
| `NpmTransitiveOverridesRecipe` | 300 | `npm-lockfile-transitive-overrides` | The affected package is **transitive-only** (absent from `package.json` `dependencies`/`devDependencies`/`peerDependencies`/`optionalDependencies`) AND a patched version exists in any compatible range AND pinning the override resolves to a non-vulnerable version | `DIRECT_DEPENDENCY` (defer to simple bump) / `OVERRIDES_AMBIGUOUS` (pinned override still resolves a vulnerable version somewhere in the tree) / `NO_PATCH_IN_RANGE` (no patch available) |
| `NpmPeerDepConflictRecipe` | 200 | `npm-lockfile-peer-dep-coordinated-bump` | A patched version exists in range AND the `peerDependencies` walk shows the bump would trigger a peer-dep conflict AND a coordinated multi-package bump (within the existing peer-allowlist scope) would resolve it | `NO_PATCH_IN_RANGE` / *(implicit decline)*: when no peer conflict would occur, the recipe returns `NotApplies(reason="DIRECT_DEPENDENCY")` because the simple-bump recipe (precedence 100) is the right path; the walker iterates in precedence order, so a `NotApplies` here lets the next recipe run. Phase 3 conservatively returns `NotApplies` for cases the multi-package bump itself would conflict — Phase 4's LLM fallback owns deep peer-dep search |
| `NpmLockfileSemverBumpRecipe` | 100 | `npm-lockfile-semver-bump` | A patched version exists in the affected dep's current major range (`patched_range ∩ current_major != ∅`) AND no peer-dep conflict AND the package is a direct dep | `NO_PATCH_IN_RANGE` (no in-range patch) / `MAJOR_BUMP_REFUSE` (patched version only in next major) / `PEER_DEP_CONFLICT` (defer to peer recipe; precedence-200 already handled it via first-`Applies`-wins) / `TRANSITIVE_ONLY` (defer to overrides recipe; precedence-300 already handled it) |
| `NpmMajorBumpRefuseRecipe` | 50 | n/a — never produces a transform | **Never** — this recipe ALWAYS returns `NotApplies(reason="MAJOR_BUMP_REFUSE")` when no in-major patch exists; it never returns `Applies`. It is the **typed escalation signal** for Phase 4 (LLM-assisted migration); its presence at precedence 50 (the lowest) ensures `RecipeNotApplicable.considered[-1].reason == "MAJOR_BUMP_REFUSE"` when the prior recipes also declined for the major-bump-only case. | When a patched version exists within the current major (then the recipe returns `NotApplies(reason="NO_PATCH_IN_RANGE")` because its trigger condition didn't fire; the simple-bump recipe at precedence 100 already won) |

The walker (`match_recipes` from S5-01) iterates `default_recipe_registry.all(plugin_id)` in `(precedence desc, name asc)` order; **first `Applies(plan)`-wins**; all-`NotApplies` short-circuits with `RecipeNotApplicable(reason="ALL_RECIPES_NOT_APPLICABLE", considered=[na1, na2, ...])` per S5-01 AC-11. `RecipeNotApplicable.considered` is the structured rejection trace Phase 4's prompt builder reads to decide LLM-fallback dispatch (production ADR-0011). Per-recipe precedence determines walker order; the `Applicability` variant determines whether a recipe *can* match — `Applies(plan)` carries the typed `ApplicationPlan` payload (per S5-02's widening: `package`, `from_version`, `to_version`, `transform_kind`) so the engine doesn't need to re-derive it.

`NotApplicableReason` is widened additively in this story with three new members — `NO_PATCH_IN_RANGE`, `TRANSITIVE_ONLY`, `DIRECT_DEPENDENCY` — mirroring the S5-01 + S5-02 amendment ceremony: Pydantic-Literal-additive, ADR-0001 contract-snapshot re-bake, PR description names the regeneration. Existing six members preserved byte-identical.

The four adapters wrap Phase 2's structural probes (Layer D — `import_graph`, Layer F — `scip`, Layer E — `dep_graph`, Layer G — test inventory) into the language-agnostic Protocols from ADR-0032. They are **per-`(language, build)` slice** — npm-specific — and live under `plugins/vulnerability-remediation--node--npm/adapters/`. Each adapter exposes `confidence() -> AdapterConfidence` where `AdapterConfidence = Annotated[Trusted | Degraded | Unavailable, Field(discriminator="kind")]` (per ADR-0010 Amendment 2026-05-18). `Degraded.reason: str` and `Unavailable.reason: str` (NOT closed Literals — Phase-2 vocabulary is disjoint from Phase-3 orchestrator vocabulary). The BundleBuilder (S3-04) reads `confidence()` and triggers TCCM-declared serial fallback per ADR-0008 when an adapter reports `Degraded` or `Unavailable`; `AdapterDegraded` events flow into `TrustOutcome.confidence` (Goal G8 — honest framing).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C12` (the recipe engines: `NpmLockfileRecipeEngine` production + `OpenRewriteRecipeEngine` scaffold).
  - `../phase-arch-design.md §Component design C7` (BundleBuilder dispatch to adapters; `composed_adapters` is the per-primitive dispatch table).
  - `../phase-arch-design.md §Scenarios A` (recipe loop: registry walked in precedence order; first `Applies(plan)`-wins).
  - `../phase-arch-design.md §Scenarios C` (Stage-6 validate; `Applied(...)` + `NpmLockfileTransform` tuple flows into `_validate_stage6`).
  - `../phase-arch-design.md §Decision points` ("Recipe returns `NotApplicable` → exit 3 with `RemediationNotApplicable(reason)`. Phase 4 reads `reason` to decide LLM-fallback dispatch" — informs which reasons the four recipes return).
- **Phase ADRs:**
  - `../ADRs/0009-recipe-engine-protocol-with-two-implementations-day-1.md` — `RecipeEngine` Protocol shape (`async apply(repo, plan, capability) -> RecipeOutcome`); production `NpmLockfileRecipeEngine` is S5-02's surface.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` (+ Amendment 2026-05-18) — `Applicability = Applies(plan) | NotApplies(reason)` discriminated union; `AdapterConfidence = Trusted | Degraded | Unavailable` (canonical home `codegenie.transforms.outcomes`; `reason: str` by design — Phase-2 vocabulary disjoint from Phase-3 orchestrator vocabulary).
  - `../ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md` — adapters' `confidence()` is the input to the deterministic serial fallback decision; the cache key consumes `dep_graph.digest`, `scip.digest`, `import_graph.digest`.
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` — `NotApplicableReason` widening + `RecipeNotApplicable.considered` schema change triggers a Phase-5 contract-snapshot re-bake (§Consequences row 6).
- **Production ADRs:**
  - `../../../production/adrs/0032-language-search-adapters.md` — **the four adapter Protocols** (`DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter`). The ADR's sketch types `confidence() -> float`; Phase 3 typed it as `AdapterConfidence` per ADR-0010 Amendment 2026-05-18. Adapter manifest entry points are `module:ClassName`.
  - `../../../production/adrs/0030-graph-aware-context-queries.md` — the primitive interfaces (`scip.refs`, `import_graph.reverse_lookup`, `dep_graph.consumers`, `test_inventory.tests_exercising`) the adapters implement.
  - `../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` — the Phase-3-to-Phase-4 escalation contract; Phase 4's `prompt_builder` reads `RecipeNotApplicable.considered`.
- **Source contracts (the executor MUST read these before writing code):**
  - `src/codegenie/transforms/outcomes.py:84-91` — `NotApplicableReason` Literal closed members (six pre-existing; this story adds three).
  - `src/codegenie/transforms/outcomes.py:175-182` — `ApplicationPlan` shape (Phase-3 placeholder; S5-02 widens additively with `package`/`from_version`/`to_version`/`transform_kind` + `for_npm_semver_bump(...)` smart constructor).
  - `src/codegenie/transforms/outcomes.py:190-244` — `Applied`/`Skipped`/`RecipeNotApplicable`/`RecipeFailed` variants + the `RecipeOutcome` TypeAlias.
  - `src/codegenie/transforms/outcomes.py:366-411` — `Trusted`/`Degraded`/`Unavailable` variants + the `AdapterConfidence` TypeAlias (`reason: str`).
  - `src/codegenie/transforms/outcomes.py:419-442` — `Applies(plan: ApplicationPlan)` / `NotApplies(reason: NotApplicableReason)` + the `Applicability` TypeAlias.
  - `src/codegenie/transforms/recipe_engine.py` — `RecipeEngine` Protocol, `RecipeProtocol` matcher Protocol, `MatchedRecipe` dataclass, `match_recipes(...)` walker, `_validate_recipe_id` helper.
  - `src/codegenie/plugins/recipe_registry.py` — `RecipeRegistry`, `RegisteredRecipe`, `default_recipe_registry`, `@register_recipe(plugin_id, *, registry=None)`, `RecipeAlreadyRegistered`, `RecipeNameCollision`.
  - `src/codegenie/plugins/resolver.py:137-163` — `ConcreteResolution(plugin, extends_chain, composed_tccm, composed_adapters: dict[PrimitiveName, Adapter])`; the `composed_adapters` field is built by `_merge_adapters(composed_adapters, current.adapters())` at line 414.
  - `src/codegenie/types/identifiers.py` — `PluginId`, `RecipeId`, `TransformKind`, `PrimitiveName`, `PackageId`, `BlobDigest` newtypes.
- **Phase 2 probe outputs the adapters wrap:**
  - `src/codegenie/probes/layer_e/` — `dep_graph` probe output (per-language consumers data).
  - `src/codegenie/probes/layer_f/` — SCIP index output.
  - `src/codegenie/probes/layer_d/` — `import_graph` probe output.
  - `src/codegenie/probes/layer_g/` — `test_inventory` probe output.
  - **`IndexHealthProbe` (Phase 2 B2)** — the freshness signal each adapter folds into `confidence()`.
- **Sibling stories (executor reads these for as-built contracts):**
  - `S5-01-recipe-registry.md` (Done — GREEN 2026-05-19) — the `RecipeProtocol` + `RecipeRegistry` + `match_recipes` surface this story consumes verbatim.
  - `S5-02-npm-lockfile-recipe-engine.md` — the engine + `ApplicationPlan` widening + smart-constructor convention.
  - `S7-01-vuln-node-npm-plugin-scaffold.md` (HARDENED) — scope token discipline (`PluginId` uses `--node--`; scope uses `--javascript--`).
- **High-level impl:** `../High-level-impl.md §"Step 7"` — `recipes/` and `adapters/` bullets.

## Goal

Land the four `RecipeProtocol`-conforming matcher classes (registered via `@register_recipe(PluginId("vulnerability-remediation--node--npm"))`), the four ADR-0032 adapter classes (referenced by `plugin.yaml`'s `contributes.adapters` from S7-01), and the wiring so that:

- The plugin's `adapters()` method returns a `dict[PrimitiveName, Adapter]` of exactly the four expected entries, and `default_registry.resolve(PluginScope.parse("vulnerability-remediation--javascript--npm").unwrap()).composed_adapters` surfaces them through the resolver's left-to-right merge (`resolver.py:414` `_merge_adapters`).
- The plugin's `transforms()` method returns a `dict[TransformKind, RecipeEngine]` keyed by each production recipe's `kind` (three entries — the refuse recipe has no engine because it never produces a transform), wiring `NpmLockfileRecipeEngine` from S5-02 (the engine is shared across the three production kinds; see Notes-for-implementer §"TransformKind discipline").
- `default_recipe_registry.all(PluginId("vulnerability-remediation--node--npm"))` returns the four recipes in `(precedence desc, name asc)` order (`NpmTransitiveOverridesRecipe`=300, `NpmPeerDepConflictRecipe`=200, `NpmLockfileSemverBumpRecipe`=100, `NpmMajorBumpRefuseRecipe`=50).
- `match_recipes(default_recipe_registry, PluginId("vulnerability-remediation--node--npm"), cve, bundle)` returns the right `MatchedRecipe(recipe, plan)` (or `RecipeNotApplicable(reason, considered=[...])`) against fixture `(VulnerabilityRecord, Bundle)` pairs covering all four recipes' applicability conditions.
- `NotApplicableReason` widens additively with `NO_PATCH_IN_RANGE`, `TRANSITIVE_ONLY`, `DIRECT_DEPENDENCY`; the Phase-5 contract snapshot re-bakes accordingly.

## Acceptance criteria

- [ ] **AC-1 (recipe class surface).** `plugins/vulnerability-remediation--node--npm/recipes/` contains four classes that structurally conform to `RecipeProtocol` (from `codegenie.transforms.recipe_engine`): `NpmLockfileSemverBumpRecipe`, `NpmPeerDepConflictRecipe`, `NpmTransitiveOverridesRecipe`, `NpmMajorBumpRefuseRecipe`. Each class has class-attribute annotations `recipe_id: RecipeId` (regex `^[a-z][a-z0-9-]*$` — validated by `_validate_recipe_id` at registration), `name: str` (unique within the plugin), `kind: TransformKind`, `precedence: int` (explicit, no default) and **exactly one** method `applies(self, cve: VulnerabilityRecord, bundle: Bundle) -> Applies | NotApplies`. A `runtime_checkable` `isinstance(recipe_instance, RecipeProtocol)` test pins structural conformance for each class. The classes do **not** define an `apply(...)` method — that lives on the engine (`NpmLockfileRecipeEngine.apply(repo, plan, capability)` from S5-02).
- [ ] **AC-2 (registration via decorator).** Each recipe class is decorated with `@register_recipe(PluginId("vulnerability-remediation--node--npm"))` (default-registry target — `register_recipe`'s `registry=None` kwarg defaults to `default_recipe_registry`); precedence is the **class attribute** (`precedence: int = 300`, etc.), NOT a decorator kwarg (per S5-01 AC-6). The decorator returns the original class via identity (`assert Decorated is Original`), so subclassing / introspection still works.
- [ ] **AC-3 (precedence ordering pinned).** `default_recipe_registry.all(PluginId("vulnerability-remediation--node--npm"))` returns a 4-tuple of `RegisteredRecipe`s whose `.recipe.name` sequence is exactly `["NpmTransitiveOverridesRecipe", "NpmPeerDepConflictRecipe", "NpmLockfileSemverBumpRecipe", "NpmMajorBumpRefuseRecipe"]`. Determinism is verified by a `PYTHONHASHSEED`-permuted subprocess test (mirrors S5-01 AC-5): same registration order under seeds `{0, 1, 2, 42}` produces byte-identical output.
- [ ] **AC-4 (NotApplicableReason additive widening).** `src/codegenie/transforms/outcomes.py::NotApplicableReason` Literal is widened additively to include `"NO_PATCH_IN_RANGE"`, `"TRANSITIVE_ONLY"`, `"DIRECT_DEPENDENCY"`. The pre-existing six members (`PEER_DEP_CONFLICT`, `MAJOR_BUMP_REFUSE`, `OVERRIDES_AMBIGUOUS`, `RECIPE_CATALOG_MISS`, `ALL_RECIPES_NOT_APPLICABLE`, `NO_RECIPES_REGISTERED`) are preserved byte-identical. Test asserts membership via `get_args(NotApplicableReason)`; nine members total. The Phase-5 contract snapshot at `tests/integration/test_phase5_contract_snapshot.py` re-bakes (this story's PR description names the regeneration — ADR-0001 §Consequences row 6).
- [ ] **AC-5 (recipe `applies(cve, bundle)` — Applies path, field-level pin).** For each production recipe (`NpmTransitiveOverridesRecipe`, `NpmPeerDepConflictRecipe`, `NpmLockfileSemverBumpRecipe`), a fixture `(VulnerabilityRecord, Bundle)` pair that should trigger `Applies` returns `Applies(plan=ApplicationPlan(...))` AND the plan's field values are pinned exactly:
  - `plan.package: PackageId` equals the fixture's affected-package `PackageId`.
  - `plan.from_version: str` equals the fixture's current-installed version (semver-shape per S5-02's regex boundary).
  - `plan.to_version: str` equals the fixture's expected target version.
  - `plan.transform_kind: TransformKind` equals the recipe's class-attribute `kind` (`"npm-lockfile-transitive-overrides"`, `"npm-lockfile-peer-dep-coordinated-bump"`, `"npm-lockfile-semver-bump"` respectively).

  Tests use S5-02's `ApplicationPlan.for_npm_semver_bump(...)` smart constructor (or per-recipe parallels — see Notes-for-implementer §"Smart constructors") to build expected plans, then assert structural equality. Field-level pins catch mutations where the recipe builds a `plan` with a wrong `to_version`.
- [ ] **AC-6 (recipe `applies(cve, bundle)` — NotApplies path, reason taxonomy pinned).** For each of the four recipes, fixture `(VulnerabilityRecord, Bundle)` pairs cover every applicable `NotApplies(reason)` per the §Context table. The full coverage matrix (each row a fixture; each column a recipe; cell = expected `Applicability` variant + reason if `NotApplies`):

  | Fixture | Overrides (prec 300) | PeerDep (prec 200) | SimpleBump (prec 100) | RefuseMajor (prec 50) |
  |---|---|---|---|---|
  | `simple-patch-in-range` | `NotApplies(DIRECT_DEPENDENCY)` | `NotApplies(DIRECT_DEPENDENCY)` | **`Applies(plan)`** | `NotApplies(NO_PATCH_IN_RANGE)` |
  | `transitive-only-cve` | **`Applies(plan)`** | `NotApplies(DIRECT_DEPENDENCY)` | `NotApplies(TRANSITIVE_ONLY)` | `NotApplies(NO_PATCH_IN_RANGE)` |
  | `major-bump-only` | `NotApplies(NO_PATCH_IN_RANGE)` | `NotApplies(NO_PATCH_IN_RANGE)` | `NotApplies(MAJOR_BUMP_REFUSE)` | **`NotApplies(MAJOR_BUMP_REFUSE)`** |
  | `peer-dep-conflict` | `NotApplies(DIRECT_DEPENDENCY)` | **`Applies(plan)`** | `NotApplies(PEER_DEP_CONFLICT)` | `NotApplies(NO_PATCH_IN_RANGE)` |
  | `no-patch-available` | `NotApplies(NO_PATCH_IN_RANGE)` | `NotApplies(NO_PATCH_IN_RANGE)` | `NotApplies(NO_PATCH_IN_RANGE)` | `NotApplies(NO_PATCH_IN_RANGE)` |
  | `transitive-overrides-ambiguous` | `NotApplies(OVERRIDES_AMBIGUOUS)` | `NotApplies(DIRECT_DEPENDENCY)` | `NotApplies(TRANSITIVE_ONLY)` | `NotApplies(NO_PATCH_IN_RANGE)` |

  4 recipes × 6 fixtures = 24 parametric assertions. Each fixture asserts the variant kind (`isinstance(out, Applies)` / `isinstance(out, NotApplies)`) AND, for `NotApplies`, the exact `reason` string (matches one of the closed `NotApplicableReason` Literal members from AC-4).
- [ ] **AC-7 (`NpmMajorBumpRefuseRecipe` never produces a transform).** A negative-control test: for every fixture in the §Context table (including `major-bump-only`), `NpmMajorBumpRefuseRecipe().applies(cve, bundle)` returns `NotApplies(...)` — **never** `Applies(...)`. The recipe has no engine wiring in `plugin.transforms()` (the dict has three entries, not four; see AC-9). Phase 4's `prompt_builder` is the consumer of `MAJOR_BUMP_REFUSE` via `RecipeNotApplicable.considered[-1].reason`.
- [ ] **AC-8 (walker first-`Applies`-wins integration).** `tests/integration/plugins/test_npm_recipes_dispatch.py` calls `match_recipes(default_recipe_registry, PluginId("vulnerability-remediation--node--npm"), cve, bundle)` against the six fixtures from AC-6 and asserts the expected return:
  - `simple-patch-in-range` ⇒ `MatchedRecipe(recipe.recipe_id == RecipeId("npm-lockfile-semver-bump"), plan=ApplicationPlan(package=..., from_version=..., to_version=..., transform_kind=TransformKind("npm-lockfile-semver-bump")))`.
  - `transitive-only-cve` ⇒ `MatchedRecipe(recipe.recipe_id == RecipeId("npm-lockfile-transitive-overrides"), plan=...)`.
  - `peer-dep-conflict` ⇒ `MatchedRecipe(recipe.recipe_id == RecipeId("npm-lockfile-peer-dep-coordinated-bump"), plan=...)`.
  - `major-bump-only` ⇒ `RecipeNotApplicable(reason="ALL_RECIPES_NOT_APPLICABLE", considered=[<4 NotApplies entries in precedence order>])`. The last entry in `considered` has `reason == "MAJOR_BUMP_REFUSE"` (Phase-4 dispatch signal).
  - `no-patch-available` ⇒ `RecipeNotApplicable(reason="ALL_RECIPES_NOT_APPLICABLE", considered=[<4 NotApplies, every reason="NO_PATCH_IN_RANGE">])`.
  - `transitive-overrides-ambiguous` ⇒ `RecipeNotApplicable(reason="ALL_RECIPES_NOT_APPLICABLE", considered=[<4 NotApplies; first reason="OVERRIDES_AMBIGUOUS">])`.

  **Short-circuit control:** for the three `Applies`-fixtures, instrument each lower-precedence recipe with an `applies_calls` counter (mirroring S5-01 AC-10's `_recipe_factory` pattern). After `match_recipes` returns the higher-precedence match, assert lower-precedence recipes' `applies_calls == 0` (proves the walker stopped). For the all-decline fixtures, assert every recipe was consulted exactly once.
- [ ] **AC-9 (plugin `transforms()` mapping).** `_VulnNodeNpmPlugin.transforms()` returns a `dict[TransformKind, RecipeEngine]` with exactly three keys: `TransformKind("npm-lockfile-semver-bump")`, `TransformKind("npm-lockfile-transitive-overrides")`, `TransformKind("npm-lockfile-peer-dep-coordinated-bump")`. Each value `isinstance(..., RecipeEngine)` is true (runtime-checkable Protocol — S5-01 AC-2). All three are instances of `NpmLockfileRecipeEngine` (S5-02); the engine is constructor-shared across `kind`s — the `kind` selects an internal dispatch path inside the engine (see Notes §"TransformKind discipline").
- [ ] **AC-10 (plugin `adapters()` mapping).** `_VulnNodeNpmPlugin.adapters()` returns a `dict[PrimitiveName, Adapter]` with exactly the four entries `PrimitiveName("dep_graph")`, `PrimitiveName("import_graph")`, `PrimitiveName("scip")`, `PrimitiveName("test_inventory")`, whose values are instances of `NpmDepGraphAdapter`, `NodeImportGraphAdapter`, `NodeScipAdapter`, `JestTestInventoryAdapter` respectively.
- [ ] **AC-11 (adapter Protocol conformance).** Each of the four adapter classes structurally conforms to its ADR-0032 Protocol (no `class … (DepGraphAdapter):` inheritance; structural typing only). A `runtime_checkable`-decorated Protocol smoke test per adapter pins conformance.
- [ ] **AC-12 (resolver `composed_adapters` integration).** With a fresh `PluginRegistry` populated by `load_plugins(Path("plugins"), Path("plugins/PLUGINS.lock"), registry=…)`, calling `registry.resolve(PluginScope.parse("vulnerability-remediation--javascript--npm").unwrap())` returns a `ConcreteResolution` whose `composed_adapters` is a `dict[PrimitiveName, Adapter]` with exactly the same four keys as AC-10 (the resolver merges the plugin's `adapters()` return left-to-right; for a plugin with no `extends` parent, `composed_adapters == plugin.adapters()` per `resolver.py:414`).
- [ ] **AC-13 (adapter `confidence()` — Trusted path).** Each adapter, given a synthesized `IndexHealthProbe.freshness_for_layer(...)` returning a fresh verdict AND the underlying Phase-2 probe output present on disk, returns `Trusted()` (the variant has no `reason` field; `isinstance(out, Trusted)` is the assertion). 4 adapters × 1 case = 4 assertions.
- [ ] **AC-14 (adapter `confidence()` — Degraded path).** Each adapter, given a synthesized `IndexHealthProbe.freshness_for_layer(...)` returning a stale verdict AND the underlying Phase-2 probe output present, returns `Degraded(reason="<adapter>_index_stale")` where the pinned reason strings are:
  - `NpmDepGraphAdapter.confidence() == Degraded(reason="dep_graph_index_stale")`
  - `NodeImportGraphAdapter.confidence() == Degraded(reason="import_graph_index_stale")`
  - `NodeScipAdapter.confidence() == Degraded(reason="scip_index_stale")`
  - `JestTestInventoryAdapter.confidence() == Degraded(reason="test_inventory_index_stale")`

  Tests pin `out.reason` exactly (equality, not substring); pinning catches typos and reason drift. The `reason` is `str` per ADR-0010 Amendment 2026-05-18 (NOT a closed Literal).
- [ ] **AC-15 (adapter `confidence()` — Unavailable path).** Each adapter, given the underlying Phase-2 probe output **missing** from disk (regardless of `IndexHealthProbe` freshness), returns `Unavailable(reason="<adapter>_output_missing")`. The four reasons are: `"dep_graph_output_missing"`, `"import_graph_output_missing"`, `"scip_output_missing"`, `"test_inventory_output_missing"`.
- [ ] **AC-16 (adapters are pure-read).** No adapter module imports `codegenie.exec`, `codegenie.transforms.sandbox_jail`, `subprocess`, or any subprocess-spawning module. Adapters are file-readers — they consume probe outputs from `.codegenie/context/raw/*.json` produced upstream by Phase 2 probes. Fence: `tests/fence/test_adapter_modules_are_pure_read.py` AST-walks the four adapter modules for forbidden imports.
- [ ] **AC-17 (`PLUGINS.lock` regen).** `compute_plugin_tree_digest(Path("plugins/vulnerability-remediation--node--npm")).unwrap()` matches `LockFile.from_path(Path("plugins/PLUGINS.lock")).unwrap().root[PluginId("vulnerability-remediation--node--npm")]`. The lockfile was regenerated by this story (the plugin tree gained `recipes/*.py` + `adapters/*.py`); commit message names the regen method (`codegenie plugins lock-update` if the helper exists; else hand-computation via `compute_plugin_tree_digest`).
- [ ] **AC-18 (no LLM SDKs).** `make fence` and `make lint-imports` stay green; no module under `plugins/vulnerability-remediation--node--npm/` imports `anthropic`, `langgraph`, `openai`, `langchain`, or `transformers` (Phase-3 fence contracts from S1-05).
- [ ] **AC-19 (red test landed and now green).** The red tests from §TDD plan exist on a commit annotated "red" and are green on the final commit; `_attempts/S7-02-npm-recipes-and-adapters.md` names the red-commit SHA.
- [ ] **AC-20 (toolchain clean).** `ruff format --check`, `ruff check`, `mypy --strict` clean on touched files. Existing tests (including S5-01's `test_recipe_registry.py`, S5-02's `test_npm_lockfile_engine.py`, S7-01's `test_vuln_node_npm_plugin_scaffold.py`) still green — adapters and recipes are additive. Branch coverage on the eight new modules (4 recipes + 4 adapters) ≥ 90%.

## Implementation outline

1. **Widen `NotApplicableReason` first (AC-4).** Amend `src/codegenie/transforms/outcomes.py:84-91` additively:
   ```python
   NotApplicableReason = Literal[
       "PEER_DEP_CONFLICT",
       "MAJOR_BUMP_REFUSE",
       "OVERRIDES_AMBIGUOUS",
       "RECIPE_CATALOG_MISS",
       "ALL_RECIPES_NOT_APPLICABLE",
       "NO_RECIPES_REGISTERED",
       # S7-02 additive widening (ADR-0001 §Consequences row 6 contract re-bake):
       "NO_PATCH_IN_RANGE",
       "TRANSITIVE_ONLY",
       "DIRECT_DEPENDENCY",
   ]
   ```
   Run `tests/integration/test_phase5_contract_snapshot.py --regenerate` (or the project-local equivalent) to absorb the additive change. Commit the regenerated golden alongside the source change. Existing six members preserved byte-identical.

2. **Recipe Protocol conformance.** Each recipe is a `@dataclass(frozen=True, slots=True)` (or plain class with class attributes — both are RecipeProtocol-conformant) declaring:
   ```python
   from dataclasses import dataclass
   from typing import Final
   from codegenie.transforms.outcomes import Applies, NotApplies, ApplicationPlan
   from codegenie.transforms.recipe_engine import RecipeProtocol  # for runtime_checkable smoke test
   from codegenie.types.identifiers import RecipeId, TransformKind

   class NpmTransitiveOverridesRecipe:
       recipe_id: Final[RecipeId] = RecipeId("npm-lockfile-transitive-overrides")
       name: Final[str] = "NpmTransitiveOverridesRecipe"
       kind: Final[TransformKind] = TransformKind("npm-lockfile-transitive-overrides")
       precedence: Final[int] = 300

       def applies(self, cve: "VulnerabilityRecord", bundle: "Bundle") -> Applies | NotApplies:
           # Pure logic; reads `bundle.dep_graph.consumers(...)`, `bundle.import_graph.reverse_lookup(...)`,
           # `cve.affected_package`, `cve.patched_ranges`; constructs ApplicationPlan via smart constructor.
           ...
   ```
   The four recipes are plain classes (not subclasses of any ABC). `@register_recipe(PluginId(...))` at module-import time inserts an instance into `default_recipe_registry`; the decorator calls `recipe_cls()` (zero-arg construction — recipes are stateless matchers per S5-01 §3) so the dataclass must default-construct cleanly.

3. **`NpmLockfileSemverBumpRecipe.applies(cve, bundle)`** — pure logic over `(cve, bundle)`:
   - Compute `is_direct = cve.affected_package in bundle.package_json.direct_deps` (the `(dependencies + devDependencies + optionalDependencies + peerDependencies)` union).
   - If not direct: return `NotApplies(reason="TRANSITIVE_ONLY")`.
   - Compute `patched_in_major = any(semver.satisfies(p, f"^{current_major}.0.0") for p in cve.patched_ranges)`.
   - If `patched_ranges` empty: return `NotApplies(reason="NO_PATCH_IN_RANGE")`.
   - If `not patched_in_major`: return `NotApplies(reason="MAJOR_BUMP_REFUSE")`.
   - Walk `bundle.dep_graph.consumers(cve.affected_package)` + `bundle.import_graph.reverse_lookup(...)` to detect peer-dep conflicts; if conflict: `NotApplies(reason="PEER_DEP_CONFLICT")`.
   - Otherwise: `Applies(plan=ApplicationPlan.for_npm_semver_bump(package=cve.affected_package, from_version=current_version, to_version=target_version, transform_kind=TransformKind("npm-lockfile-semver-bump")))`.

4. **`NpmPeerDepConflictRecipe.applies(cve, bundle)`** — declines (returns `NotApplies`) unless **all** of: (a) patched version in range, (b) peer-dep conflict detected on bump, (c) a coordinated multi-package bump within the existing peer-allowlist scope resolves the conflict. Per Phase 3 conservative scope: when (a) holds but (b) and (c) both hold, return `Applies(plan=ApplicationPlan.for_npm_peer_dep_coordinated_bump(...))`; otherwise `NotApplies(reason="DIRECT_DEPENDENCY")` (defer to simple-bump via walker precedence — even when the cause is "no peer conflict") or `NotApplies(reason="NO_PATCH_IN_RANGE")` (no patch). Deep peer-dep search across the cross-major space is Phase 4 LLM territory (out of scope).

5. **`NpmTransitiveOverridesRecipe.applies(cve, bundle)`** — returns `Applies(...)` IFF:
   - The affected package is **transitive-only** (not in any direct-deps section).
   - A patched version exists in any compatible semver range.
   - Pinning the override would not produce a conflict elsewhere in the lockfile (resolves to a non-vulnerable version everywhere).

   Else: `NotApplies(reason)` with one of `"DIRECT_DEPENDENCY"` (defer to simple-bump), `"OVERRIDES_AMBIGUOUS"` (the pinned override still resolves a vulnerable version somewhere), `"NO_PATCH_IN_RANGE"`.

6. **`NpmMajorBumpRefuseRecipe.applies(cve, bundle)`** — returns `NotApplies(reason="MAJOR_BUMP_REFUSE")` IFF the only patched version is in a different major from the current one. Otherwise `NotApplies(reason="NO_PATCH_IN_RANGE")` (Phase 4 reads neither — `MAJOR_BUMP_REFUSE` is the only consumed reason; the other branch is the "this recipe doesn't apply" filler). **The recipe never returns `Applies`** — its job is to populate `RecipeNotApplicable.considered[-1]` with the typed escalation signal. The recipe has no engine wiring; `plugin.transforms()` has three keys (the production recipes' kinds), not four.

7. **Adapters.** Each adapter is a `@dataclass(frozen=True)` implementing the corresponding ADR-0032 Protocol via structural conformance (no inheritance). Constructor takes the plugin's resolved probe-output paths (read from `.codegenie/context/raw/*.json` produced by Phase 2 probes; the resolver passes them in at construction time, OR — for Phase 3 — the adapter reads them lazily at first `confidence()` call):
   - `NpmDepGraphAdapter(probe_output_path: Path, index_health: IndexHealthProbeOutput).consumers(package: PackageId) -> list[PackageId]` — walks the parsed `package-lock.json` semver tree (Phase 2 Layer E output).
   - `NodeImportGraphAdapter(...).reverse_lookup(module: str) -> list[FilePath]` — reads Phase 2 Layer D import-graph output filtered to JS/TS.
   - `NodeScipAdapter(...).refs(symbol: SymbolId) -> list[CodeLocation]` — reads `scip-typescript` index output from Phase 2 Layer F.
   - `JestTestInventoryAdapter(...).tests_exercising(file_set: list[FilePath]) -> list[TestName]` — reads Phase 2 Layer G test-inventory output filtered to Jest/Vitest.
   - `confidence() -> AdapterConfidence` (`Trusted` / `Degraded(reason)` / `Unavailable(reason)`) folded from `index_health.freshness_for_layer(...)` plus the per-layer output file's presence. Reason strings pinned per AC-14 / AC-15. **Pure function**: same inputs → same `AdapterConfidence` instance (no side effects, no I/O beyond the cached path).

8. **Plugin wiring.** Update `api.py`'s `_VulnNodeNpmPlugin.adapters()` to return four entries:
   ```python
   def adapters(self) -> dict[PrimitiveName, Adapter]:
       return {
           PrimitiveName("dep_graph"): NpmDepGraphAdapter(...),
           PrimitiveName("import_graph"): NodeImportGraphAdapter(...),
           PrimitiveName("scip"): NodeScipAdapter(...),
           PrimitiveName("test_inventory"): JestTestInventoryAdapter(...),
       }
   ```
   And `transforms()` to return three entries keyed by each production recipe's `kind`:
   ```python
   def transforms(self) -> dict[TransformKind, RecipeEngine]:
       engine = NpmLockfileRecipeEngine(...)  # constructor wiring per S5-02
       return {
           TransformKind("npm-lockfile-semver-bump"): engine,
           TransformKind("npm-lockfile-transitive-overrides"): engine,
           TransformKind("npm-lockfile-peer-dep-coordinated-bump"): engine,
       }
   ```
   The engine is *shared* across the three kinds; the kind selects an internal dispatch path inside the engine. See Notes-for-implementer §"TransformKind discipline" for the rationale.

9. **Recipe registration triggers.** Import the four recipe modules from `recipes/__init__.py` so `@register_recipe(...)` fires at plugin load (per ADR-0002 "registration via side-effecting import"). Per S5-01, the decorator zero-arg-constructs the class; recipes must default-construct cleanly.

10. **`PLUGINS.lock` regen.** Because the plugin tree's file set changes (eight new modules), `PLUGINS.lock` row for `vulnerability-remediation--node--npm` must be regenerated via `compute_plugin_tree_digest(Path("plugins/vulnerability-remediation--node--npm")).unwrap()` and the resulting `BlobDigest` written through `LockFile.from_path(...)` (or the `codegenie plugins lock-update` helper if shipped). Commit message names the regen method.

## TDD plan — red / green / refactor

> **Contract note (validated 2026-05-19).** Recipes are **pure matchers** with **one** method
> `applies(self, cve: VulnerabilityRecord, bundle: Bundle) -> Applies | NotApplies`. They register on the
> module-level `default_recipe_registry` keyed by `PluginId`; the walker is the module-level function
> `match_recipes(registry, plugin_id, cve, bundle) -> MatchedRecipe | RecipeNotApplicable`. There is no
> per-plugin `recipe_registry` field and no `recipe.apply(...)`. All sum types
> (`Applies` / `NotApplies` / `Applicability` / `Trusted` / `Degraded` / `Unavailable` / `AdapterConfidence`)
> import from `codegenie.transforms.outcomes`.

### Red

Test file 1: `tests/unit/plugins/test_npm_recipes_applicability.py` — per-recipe `applies(cve, bundle)` coverage (AC-1, AC-5, AC-6, AC-7).

```python
# tests/unit/plugins/test_npm_recipes_applicability.py
import importlib

import pytest

from codegenie.transforms.outcomes import Applies, NotApplies
from codegenie.transforms.recipe_engine import RecipeProtocol
from tests.fixtures.npm_recipes import load_case  # -> (VulnerabilityRecord, Bundle)

# The plugin dir slug contains hyphens, so `import plugins.x...` syntax is illegal —
# `importlib.import_module` with the literal hyphenated slug is the only path (see Notes
# §"Import path"; matches loader.py:289-293 + S7-01 validation CN/slug-to-module note).
_recipes = importlib.import_module("plugins.vulnerability-remediation--node--npm.recipes")
NpmLockfileSemverBumpRecipe = _recipes.NpmLockfileSemverBumpRecipe
NpmPeerDepConflictRecipe = _recipes.NpmPeerDepConflictRecipe
NpmTransitiveOverridesRecipe = _recipes.NpmTransitiveOverridesRecipe
NpmMajorBumpRefuseRecipe = _recipes.NpmMajorBumpRefuseRecipe

ALL_RECIPES = [
    NpmTransitiveOverridesRecipe,
    NpmPeerDepConflictRecipe,
    NpmLockfileSemverBumpRecipe,
    NpmMajorBumpRefuseRecipe,
]


@pytest.mark.parametrize("recipe_cls", ALL_RECIPES)
def test_recipe_conforms_to_recipe_protocol(recipe_cls):
    # runtime_checkable structural conformance — class attrs + the single `applies` method.
    assert isinstance(recipe_cls(), RecipeProtocol)
    # Negative: recipes do NOT define `apply` — that lives on the engine.
    assert not hasattr(recipe_cls, "apply")


# AC-6 coverage matrix — every (recipe, fixture) cell from the §Acceptance-criteria table.
# cell = ("Applies", None) or ("NotApplies", "<REASON>").
COVERAGE = {
    "simple-patch-in-range": {
        NpmTransitiveOverridesRecipe: ("NotApplies", "DIRECT_DEPENDENCY"),
        NpmPeerDepConflictRecipe: ("NotApplies", "DIRECT_DEPENDENCY"),
        NpmLockfileSemverBumpRecipe: ("Applies", None),
        NpmMajorBumpRefuseRecipe: ("NotApplies", "NO_PATCH_IN_RANGE"),
    },
    "transitive-only-cve": {
        NpmTransitiveOverridesRecipe: ("Applies", None),
        NpmPeerDepConflictRecipe: ("NotApplies", "DIRECT_DEPENDENCY"),
        NpmLockfileSemverBumpRecipe: ("NotApplies", "TRANSITIVE_ONLY"),
        NpmMajorBumpRefuseRecipe: ("NotApplies", "NO_PATCH_IN_RANGE"),
    },
    "major-bump-only": {
        NpmTransitiveOverridesRecipe: ("NotApplies", "NO_PATCH_IN_RANGE"),
        NpmPeerDepConflictRecipe: ("NotApplies", "NO_PATCH_IN_RANGE"),
        NpmLockfileSemverBumpRecipe: ("NotApplies", "MAJOR_BUMP_REFUSE"),
        NpmMajorBumpRefuseRecipe: ("NotApplies", "MAJOR_BUMP_REFUSE"),
    },
    "peer-dep-conflict": {
        NpmTransitiveOverridesRecipe: ("NotApplies", "DIRECT_DEPENDENCY"),
        NpmPeerDepConflictRecipe: ("Applies", None),
        NpmLockfileSemverBumpRecipe: ("NotApplies", "PEER_DEP_CONFLICT"),
        NpmMajorBumpRefuseRecipe: ("NotApplies", "NO_PATCH_IN_RANGE"),
    },
    "no-patch-available": {r: ("NotApplies", "NO_PATCH_IN_RANGE") for r in ALL_RECIPES},
    "transitive-overrides-ambiguous": {
        NpmTransitiveOverridesRecipe: ("NotApplies", "OVERRIDES_AMBIGUOUS"),
        NpmPeerDepConflictRecipe: ("NotApplies", "DIRECT_DEPENDENCY"),
        NpmLockfileSemverBumpRecipe: ("NotApplies", "TRANSITIVE_ONLY"),
        NpmMajorBumpRefuseRecipe: ("NotApplies", "NO_PATCH_IN_RANGE"),
    },
}


@pytest.mark.parametrize("fixture", sorted(COVERAGE))
@pytest.mark.parametrize("recipe_cls", ALL_RECIPES)
def test_recipe_applicability_matrix(fixture, recipe_cls):
    cve, bundle = load_case(fixture)
    out = recipe_cls().applies(cve, bundle)
    variant, reason = COVERAGE[fixture][recipe_cls]
    if variant == "Applies":
        assert isinstance(out, Applies)
        # Field-level pin (AC-5): the plan is fully discriminated, not a bare ApplicationPlan().
        assert out.plan.package == cve.affected_package
        assert out.plan.transform_kind == recipe_cls.kind
        assert out.plan.from_version and out.plan.to_version  # non-empty semver
    else:
        assert isinstance(out, NotApplies)
        assert out.reason == reason  # exact-equality; catches typos + reason drift


def test_major_bump_refuse_never_applies():
    # AC-7 negative control — the refuse recipe is the typed escalation signal, never a transform.
    for fixture in COVERAGE:
        cve, bundle = load_case(fixture)
        out = NpmMajorBumpRefuseRecipe().applies(cve, bundle)
        assert isinstance(out, NotApplies)
```

Test file 2: `tests/unit/plugins/test_npm_adapters_confidence.py` — adapter `confidence()` three-state matrix (AC-13/14/15).

```python
# tests/unit/plugins/test_npm_adapters_confidence.py
import pytest

from codegenie.transforms.outcomes import Trusted, Degraded, Unavailable
from tests.fixtures.npm_recipes import make_index_health  # fresh|stale verdict synth

ADAPTERS = {  # (adapter_cls, stale_reason, missing_reason)
    "NpmDepGraphAdapter": ("dep_graph_index_stale", "dep_graph_output_missing"),
    "NodeImportGraphAdapter": ("import_graph_index_stale", "import_graph_output_missing"),
    "NodeScipAdapter": ("scip_index_stale", "scip_output_missing"),
    "JestTestInventoryAdapter": ("test_inventory_index_stale", "test_inventory_output_missing"),
}


@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_adapter_confidence_trusted_when_fresh(name, tmp_path):
    adapter = _build_adapter(name, tmp_path, output_present=True, index=make_index_health("fresh"))
    assert isinstance(adapter.confidence(), Trusted)


@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_adapter_confidence_degraded_when_b2_stale(name, tmp_path):
    _, stale_reason, _ = ADAPTERS[name]
    adapter = _build_adapter(name, tmp_path, output_present=True, index=make_index_health("stale"))
    out = adapter.confidence()
    assert isinstance(out, Degraded)
    assert out.reason == stale_reason  # exact-equality pin


@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_adapter_confidence_unavailable_when_output_missing(name, tmp_path):
    _, _, missing_reason = ADAPTERS[name]
    adapter = _build_adapter(name, tmp_path, output_present=False, index=make_index_health("fresh"))
    out = adapter.confidence()
    assert isinstance(out, Unavailable)
    assert out.reason == missing_reason
```

Test file 3: `tests/integration/plugins/test_npm_recipes_dispatch.py` — the `match_recipes` walker, first-`Applies`-wins + short-circuit (AC-3, AC-8).

```python
# tests/integration/plugins/test_npm_recipes_dispatch.py
import importlib

import pytest

from codegenie.plugins.recipe_registry import default_recipe_registry
from codegenie.transforms.outcomes import RecipeNotApplicable
from codegenie.transforms.recipe_engine import MatchedRecipe, match_recipes
from codegenie.types.identifiers import PluginId, RecipeId
from tests.fixtures.npm_recipes import load_case

NPM = PluginId("vulnerability-remediation--node--npm")


def test_registry_orders_recipes_by_precedence_desc():
    # AC-3 — importing the plugin's recipes/__init__.py fired @register_recipe x4.
    importlib.import_module("plugins.vulnerability-remediation--node--npm.recipes")  # fires @register_recipe x4
    names = [rr.recipe.name for rr in default_recipe_registry.all(NPM)]
    assert names == [
        "NpmTransitiveOverridesRecipe",
        "NpmPeerDepConflictRecipe",
        "NpmLockfileSemverBumpRecipe",
        "NpmMajorBumpRefuseRecipe",
    ]


@pytest.mark.parametrize("fixture,expected_recipe_id", [
    ("simple-patch-in-range", "npm-lockfile-semver-bump"),
    ("transitive-only-cve", "npm-lockfile-transitive-overrides"),
    ("peer-dep-conflict", "npm-lockfile-peer-dep-coordinated-bump"),
])
def test_match_recipes_first_applies_wins(fixture, expected_recipe_id):
    importlib.import_module("plugins.vulnerability-remediation--node--npm.recipes")  # fires @register_recipe x4
    cve, bundle = load_case(fixture)
    result = match_recipes(default_recipe_registry, NPM, cve, bundle)
    assert isinstance(result, MatchedRecipe)
    assert result.recipe.recipe_id == RecipeId(expected_recipe_id)
    assert result.plan.package == cve.affected_package
    assert result.plan.transform_kind == result.recipe.kind


# considered[] is in walker order (precedence desc): [Overrides, PeerDep, SimpleBump, RefuseMajor].
# Reasons taken from the §Acceptance-criteria AC-6 coverage matrix.
ALL_DECLINE = {
    "major-bump-only": ["NO_PATCH_IN_RANGE", "NO_PATCH_IN_RANGE", "MAJOR_BUMP_REFUSE", "MAJOR_BUMP_REFUSE"],
    "no-patch-available": ["NO_PATCH_IN_RANGE"] * 4,
    "transitive-overrides-ambiguous": ["OVERRIDES_AMBIGUOUS", "DIRECT_DEPENDENCY", "TRANSITIVE_ONLY", "NO_PATCH_IN_RANGE"],
}


@pytest.mark.parametrize("fixture", sorted(ALL_DECLINE))
def test_match_recipes_all_decline_short_circuits(fixture):
    importlib.import_module("plugins.vulnerability-remediation--node--npm.recipes")  # fires @register_recipe x4
    cve, bundle = load_case(fixture)
    result = match_recipes(default_recipe_registry, NPM, cve, bundle)
    assert isinstance(result, RecipeNotApplicable)
    assert result.reason == "ALL_RECIPES_NOT_APPLICABLE"
    # Every recipe consulted exactly once; reason sequence pinned in precedence order.
    assert [na.reason for na in result.considered] == ALL_DECLINE[fixture]
    if fixture == "major-bump-only":
        # AC-8 — last considered entry carries the Phase-4 LLM-fallback dispatch signal.
        assert result.considered[-1].reason == "MAJOR_BUMP_REFUSE"
```

Run all three; confirm `ModuleNotFoundError` on the `recipes`/`adapters` packages and `default_recipe_registry.all(NPM)` returning `()`; commit the red. `_attempts/S7-02-npm-recipes-and-adapters.md` records the red-commit SHA (AC-19).

> **Mutation-resistance (AC-8 short-circuit control).** The walker tests above prove *which* recipe matched
> and *what plan* it produced — but not that the walker *stopped*. Add an `applies_calls` counter to a
> spy-wrapped recipe set (mirror S5-01 AC-10's `_recipe_factory`): after a higher-precedence `Applies`,
> assert every strictly-lower-precedence recipe's `applies_calls == 0`; for the all-decline fixtures assert
> every recipe's `applies_calls == 1`. Without this a recipe returning `Applies(plan=ApplicationPlan(...))`
> unconditionally would still pass the matrix above.

### Green

Implement the four recipes + four adapters; wire the plugin's `adapters()` / `transforms()` accessors and
the `recipes/__init__.py` side-effecting imports that fire `@register_recipe(...)`. Smallest shape: each
recipe's `applies(cve, bundle)` is a single `if`-chain returning `Applies(plan)` or `NotApplies(reason)`;
each adapter's `confidence()` is a single `match` over the `IndexHealthProbe` freshness verdict plus the
output-file presence check. Recipes never open files or spawn subprocesses — that is the engine's surface.

### Refactor

- Confirm `mypy --strict` clean; `_VulnNodeNpmPlugin.adapters()` returns `dict[PrimitiveName, Adapter]`
  where `Adapter` is the union of the four ADR-0032 Protocols. Structural typing only — no inheritance
  from the Protocol classes (AC-11).
- Confirm each recipe is a *pure matcher* — `applies(...)` returns an `Applicability` variant and nothing
  else; there is no `recipe.apply(...)`. The orchestrator dispatches the engine via
  `plugin.transforms()[matched.recipe.kind].apply(repo, plan, capability)` (S6-04 — out of scope here).
- Hoist any duplicated semver-range logic across the recipes into a single private pure helper module
  (`recipes/_semver.py`), keeping each recipe's `applies` body a thin decision chain (functional core).
- Document the precedence rationale in each recipe class docstring; the numeric `precedence` is a class
  attribute, never encoded in the recipe's name.

## Files to touch

| Path | Why |
|---|---|
| `plugins/vulnerability-remediation--node--npm/recipes/__init__.py` | Modified — re-exports the four recipe classes; their import triggers `@register_recipe(...)` |
| `plugins/vulnerability-remediation--node--npm/recipes/lockfile_semver_bump.py` | New — `NpmLockfileSemverBumpRecipe` |
| `plugins/vulnerability-remediation--node--npm/recipes/peer_dep_conflict.py` | New — `NpmPeerDepConflictRecipe` |
| `plugins/vulnerability-remediation--node--npm/recipes/transitive_overrides.py` | New — `NpmTransitiveOverridesRecipe` |
| `plugins/vulnerability-remediation--node--npm/recipes/major_bump_refuse.py` | New — `NpmMajorBumpRefuseRecipe` |
| `plugins/vulnerability-remediation--node--npm/adapters/__init__.py` | Modified — re-exports the four adapter classes |
| `plugins/vulnerability-remediation--node--npm/adapters/npm_dep_graph.py` | New — `NpmDepGraphAdapter` implementing `DepGraphAdapter` |
| `plugins/vulnerability-remediation--node--npm/adapters/node_import_graph.py` | New — `NodeImportGraphAdapter` implementing `ImportGraphAdapter` |
| `plugins/vulnerability-remediation--node--npm/adapters/node_scip.py` | New — `NodeScipAdapter` implementing `ScipAdapter` |
| `plugins/vulnerability-remediation--node--npm/adapters/jest_test_inventory.py` | New — `JestTestInventoryAdapter` implementing `TestInventoryAdapter` |
| `plugins/vulnerability-remediation--node--npm/recipes/_semver.py` | New — shared pure semver-range helper (refactor step; keeps each `applies` body a thin chain) |
| `plugins/vulnerability-remediation--node--npm/api.py` | Modified — `adapters()` returns four entries; `transforms()` returns a `dict[TransformKind, RecipeEngine]` of three `NpmLockfileRecipeEngine` entries; recipe imports trigger registration |
| `src/codegenie/transforms/outcomes.py` | Modified — `NotApplicableReason` Literal widened additively with `NO_PATCH_IN_RANGE`, `TRANSITIVE_ONLY`, `DIRECT_DEPENDENCY` (AC-4) |
| `tests/integration/test_phase5_contract_snapshot.py` (golden) | Modified — re-baked golden absorbs the additive `NotApplicableReason` widening (ADR-0001 §Consequences row 6) |
| `plugins/PLUGINS.lock` | Modified — regenerate the plugin's tree digest (`compute_plugin_tree_digest` → `LockFile`) |
| `tests/fixtures/npm_recipes/` | New — `(VulnerabilityRecord, Bundle)` fixture pairs + `load_case(name)` / `make_index_health(verdict)` helpers in `__init__.py`. Six cases: `simple-patch-in-range`, `transitive-only-cve`, `major-bump-only`, `peer-dep-conflict`, `no-patch-available`, `transitive-overrides-ambiguous` |
| `tests/fence/test_adapter_modules_are_pure_read.py` | New — AST-walk fence: adapter modules import no subprocess-spawning module (AC-16) |
| `tests/unit/plugins/test_npm_recipes_applicability.py` | New — per-recipe `applies(cve, bundle)` 4×6 coverage matrix + `RecipeProtocol` conformance (AC-1, AC-5, AC-6, AC-7) |
| `tests/unit/plugins/test_npm_adapters_confidence.py` | New — `confidence()` three-state matrix (Trusted/Degraded/Unavailable) × four adapters (AC-13/14/15) |
| `tests/integration/plugins/test_npm_recipes_dispatch.py` | New — `match_recipes(...)` first-`Applies`-wins + all-decline short-circuit + precedence ordering (AC-3, AC-8) |

## Out of scope

- **End-to-end Express CVE remediation** — S8-02 lands `tests/integration/test_end_to_end_express_cve.py` and the golden lockfile diff.
- **The synthetic `example--noop--*` plugin + the three-plugin contract bake test** — S7-04.
- **The universal HITL plugin** — S7-03.
- **Phase 4 LLM fallback dispatch** — Phase 4. This story's recipes return `NotApplicable(reason)` for cases Phase 4 will reach; that's the contract boundary.
- **Coordinated multi-package bump search** in `NpmPeerDepConflictRecipe` — the simple peer-dep walk is enough for Phase 3; deep search is Phase 4's LLM-assisted territory.
- **Yarn Berry / pnpm support** — those are separate `(*--node--yarn-berry)` / `(*--node--pnpm)` plugins added by addition in Phase 7+.
- **OpenRewrite recipe engine wiring** — S5-03's scaffold; the npm plugin does not list it under `transforms()` in Phase 3.

## Notes for the implementer

- **`Applicability` is a sum type, NOT a `bool`.** The single most attacked design choice in this codebase per the critic (`Literal["*"]` collapse to `str` at runtime is the same anti-pattern at the scope layer). The recipe's one method is `applies(self, cve: VulnerabilityRecord, bundle: Bundle) -> Applies | NotApplies` — never `-> bool`, never `-> Applicability` keyed off a `plan` argument. The *plan* is the **output** (`Applies(plan=...)`), not the input. Surface any `applies(plan) -> bool` regression loudly.
- **Recipes are pure matchers; the engine is the worker — they are separate objects.** A recipe class has class attributes (`recipe_id`, `name`, `kind`, `precedence`) and exactly one method, `applies`. It has **no `apply(...)` method**. The transformation work lives on `NpmLockfileRecipeEngine.apply(repo, plan, capability)` (S5-02). The S6-04 orchestrator runs the two-stage flow: `match_recipes(...) → MatchedRecipe(recipe, plan) → plugin.transforms()[recipe.kind].apply(repo, plan, capability)`. Do NOT add a method that re-implements lockfile parsing or `npm install` inside a recipe.
- **Registry & walker are module-level, not per-plugin.** Recipes register on the module-level `default_recipe_registry` (`codegenie.plugins.recipe_registry`) keyed by `PluginId` via `@register_recipe(PluginId("vulnerability-remediation--node--npm"))`. There is no `plugin.recipe_registry` field and no `.iter(plan)` method. Dispatch is the module-level function `match_recipes(registry, plugin_id, cve, bundle)`. Precedence is the class attribute `precedence: int` — never a decorator kwarg (S5-01 AC-6).
- **Precedence values are plugin-scoped.** The numeric precedence (300 / 200 / 100 / 50) orders recipes *within* this plugin's `PluginId` bucket; another plugin's recipes have their own precedence space. `match_recipes` walks `registry.all(plugin_id)` in `(precedence desc, name asc)` order; first-`Applies`-wins.
- **Adapter `confidence()` returns a sum type, not a `float`.** Production ADR-0032 §"Adapter Protocols" sketches `confidence() -> float`, but Phase 3 typed it as `AdapterConfidence = Trusted() | Degraded(reason: str) | Unavailable(reason: str)` (canonical home `codegenie.transforms.outcomes`, per ADR-0010 Amendment 2026-05-18). `Trusted` has **no** `reason` field. `Degraded.reason` / `Unavailable.reason` are **`str`**, not closed Literals — Phase-2 vocabulary is disjoint from Phase-3 orchestrator vocabulary; the per-adapter reason strings are pinned in AC-14/AC-15.
- **`tsconfig` path resolution is hard.** Don't try to be exhaustive in Phase 3. `NodeImportGraphAdapter` reads what Phase 2 Layer D already resolved; if Layer D didn't resolve a path, `reverse_lookup(...)` returns an incomplete list and `confidence()` degrades. Honest framing — fail loud, not silent.
- **Import path for the hyphenated plugin slug.** The plugin directory is `plugins/vulnerability-remediation--node--npm/` (literal hyphens — S7-01 HARDENED, `loader.py:289-293`). The `import plugins.x...` statement is illegal syntax with hyphens; test code and the `recipes/__init__.py` side-effecting import must go through `importlib.import_module("plugins.vulnerability-remediation--node--npm.recipes")`. Both `plugins/__init__.py` and the per-plugin `__init__.py` must exist for Python's finder to resolve the dotted name.
- **Fixtures are `(VulnerabilityRecord, Bundle)` pairs, not plans.** A recipe consumes a CVE record + a `Bundle` (BundleBuilder output — `dep_graph.consumers`, `scip.refs`, `import_graph.reverse_lookup`, `test_inventory.tests_exercising`) and *produces* an `ApplicationPlan`. Build fixtures under `tests/fixtures/npm_recipes/` with a `load_case(name) -> tuple[VulnerabilityRecord, Bundle]` helper; keep each small. Use the real `VulnerabilityRecord` (`codegenie.vuln_index.models`) and `Bundle` (`codegenie.plugins.bundle`) types — do not invent a `RecipePlan` shape.
- **Do NOT skip the integrity-mismatch path.** Regenerating `PLUGINS.lock` is part of this story; the CI's `PluginRejected(integrity_mismatch)` test from S2-03 will fail if you forget. Use `compute_plugin_tree_digest(...)` + `LockFile.from_path(...)` (both `Result`-returning — `.unwrap()` them); the commit message names whether a helper or hand-computation was used.
- **`IndexHealthProbe` (B2) is the single most important probe** per CLAUDE.md. The adapters' degradation is the consumer-side payoff — when B2 reports stale, the adapters return `Degraded(reason=...)`; the TCCM-declared serial fallback fires (ADR-0008); `AdapterDegraded` flows into `TrustOutcome.confidence`. This is the load-bearing honest-confidence path (Goal G8); test all three states explicitly.
- **`NpmMajorBumpRefuseRecipe` is the typed escalation signal, not a failure.** It **never** returns `Applies` — it always returns `NotApplies(reason="MAJOR_BUMP_REFUSE")` (when only a cross-major patch exists) or `NotApplies(reason="NO_PATCH_IN_RANGE")` (otherwise). Its purpose is to land at precedence 50 (lowest) so that, for the major-bump-only case, `RecipeNotApplicable.considered[-1].reason == "MAJOR_BUMP_REFUSE"`. Phase 4's prompt builder reads that to dispatch LLM-assisted major-bump migration. It has no engine wiring — `plugin.transforms()` has three keys, not four.
- **`NotApplicableReason` widening is an amendment ceremony.** Widen the closed Literal *additively* (three new members; existing six byte-identical), then re-bake the Phase-5 contract snapshot golden. Name the regeneration in the PR description (ADR-0001 §Consequences row 6) — mirrors the S5-01 + S5-02 amendment pattern.
