# Story S7-02 — Four npm recipes + four ADR-0032 npm language search adapters

**Step:** Step 7 — First production plugin, universal HITL fallback plugin, synthetic third plugin
**Status:** Ready
**Effort:** L
**Depends on:** S6-04 (orchestrator + the recipe-engine dispatch path must exist for `RecipeOutcome` to flow), S5-01 (`RecipeRegistry` + `@register_recipe(plugin_id)`), S5-02 (the `NpmLockfileRecipeEngine` production engine — the four recipes wrap its capability), S7-01 (the plugin directory + `plugin.yaml` with `contributes.adapters` import paths must already exist for the adapter modules to drop into)
**ADRs honored:** [ADR-0003](../ADRs/0003-plugin-resolution-and-universal-fallback-semantics.md) (the recipes' `applies(plan) -> Applicability` returns a sum-type variant, never a `bool` — the resolver below `RecipeRegistry` mirrors the kernel's tagged-union discipline), [ADR-0004](../ADRs/0004-plugin-private-capabilities-via-tccm.md) (the four adapters are plugin-local; they implement the *generic* ADR-0032 Protocols but live under `plugins/vulnerability-remediation--node--npm/adapters/` — no kernel edits), [ADR-0009](../ADRs/0009-recipe-engine-protocol-with-two-implementations-day-1.md) (the recipes hand off transformation work to `NpmLockfileRecipeEngine`; `OpenRewriteRecipeEngine` is the scaffold confirming the Protocol takes >1 implementation), [ADR-0010](../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md) (`Applicability` is a Pydantic discriminated union; `applies(...)` returns variants — `Applies(plan)` / `NotApplies(reason)` — never primitive booleans)

## Context

S7-01 landed the plugin's manifest + TCCM + `@register_plugin(...)` call but left `adapters/` and `recipes/` empty. This story populates both. It's the only `L`-sized Step-7 story because volume dominates: **four** recipe classes each with non-trivial `applies(plan) -> Applicability` logic, **four** ADR-0032 adapter implementations wrapping Phase 2's structural probes (`scip`, `import_graph`, `dep_graph`, `test_inventory`), plus plugin-local registration via `@register_recipe(PluginId("vulnerability-remediation--node--npm"))` against the plugin's `RecipeRegistry` from S5-01.

The four recipes are:

| Recipe | When `applies(plan)` returns `Applies(...)` | When it returns `NotApplies(reason)` |
|---|---|---|
| `NpmLockfileSemverBumpRecipe` | A patched version exists in the affected dep's semver range AND no peer-dep constraint is violated | A patched version exists but only by major-bump (delegates to refusal recipe); or no patched version exists at all |
| `NpmPeerDepConflictRecipe` | A patched version exists in range but bumping triggers a peer-dep mismatch detected via `peerDependencies` walking | The patched version is in range and bumping it does NOT trigger a peer conflict (the simple bump recipe should win) |
| `NpmTransitiveOverridesRecipe` | The vulnerable package is reached only via transitive deps; the root `package.json` does NOT directly declare it; an `overrides` block can pin the transitive | The package is a direct dep (use `NpmLockfileSemverBumpRecipe`) |
| `NpmMajorBumpRefuseRecipe` | The only patched version is by a major bump (e.g., 4.x vulnerable, 5.x patched) | A patched version exists within the current major (the simple bump should win) |

The recipes are iterated by the per-plugin `RecipeRegistry` in `(precedence desc, name asc)` order; **first `Applies(plan)`-wins**; all-`NotApplies` short-circuits with `RecipeOutcome.NotApplicable(reason=ALL_RECIPES_NOT_APPLICABLE)` per S5-01. Per-recipe precedence determines order, but the `Applicability` variant determines whether the recipe *can* even attempt the transformation — `Applies(plan)` carries the concrete planning data (target version, peer-dep allowlist, etc.) so the engine doesn't need to re-derive it.

The four adapters wrap Phase 2's structural probes (Layer D — `import_graph`, Layer F — `scip`, Layer E — `dep_graph`, Layer G — test inventory) into the language-agnostic Protocols from ADR-0032. They are **per-`(language, build)` slice** — npm-specific — and live under `plugins/vulnerability-remediation--node--npm/adapters/`. Each adapter exposes `confidence() -> AdapterConfidence` so the BundleBuilder can detect a stale `IndexHealthProbe` (Phase 2 B2) signal and trigger TCCM-declared fallback per ADR-0008.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C12` (the recipe engines: `NpmLockfileRecipeEngine` production + `OpenRewriteRecipeEngine` scaffold).
  - `../phase-arch-design.md §Component design C7` (BundleBuilder dispatch to adapters; `composed_adapters` is the per-primitive dispatch table).
  - `../phase-arch-design.md §Scenarios A` (recipe loop: registry walked in precedence order; first `Applies(plan)`-wins).
  - `../phase-arch-design.md §Scenarios C` (Stage-6 validate; `RecipeOutcome.Applied(NpmLockfileTransform)` flows into `_validate_stage6`).
  - `../phase-arch-design.md §Decision points` ("Recipe returns `NotApplicable` → exit 3 with `RemediationOutcome.NotApplicable(reason)`. Phase 4 reads `reason` to decide LLM-fallback dispatch" — informs which reasons the four recipes return).
- **Phase ADRs:**
  - `../ADRs/0009-recipe-engine-protocol-with-two-implementations-day-1.md` — `RecipeEngine` Protocol shape; production `NpmLockfileRecipeEngine` is S5-02's surface.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — `Applicability = Applies(plan) | NotApplies(reason)` discriminated union; `applies(plan) -> Applicability` never returns `bool`.
  - `../ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md` — adapters' `confidence()` is the input to the deterministic serial fallback decision; the cache key consumes `dep_graph.digest`, `scip.digest`, `import_graph.digest`.
- **Production ADRs:**
  - `../../../production/adrs/0032-language-search-adapters.md` — **the four adapter Protocols** (`DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter`). Each declares `confidence() -> float` (or `AdapterConfidence` if S1-03 typed it as a sum); the adapter manifest entry points are `module:ClassName`.
  - `../../../production/adrs/0030-graph-aware-context-queries.md` — the primitive interfaces (`scip.refs`, `import_graph.reverse_lookup`, `dep_graph.consumers`, `test_inventory.tests_exercising`) the adapters implement.
- **Phase 2 probe outputs the adapters wrap:**
  - `src/codegenie/probes/layer_e/` — `dep_graph` probe output (per-language consumers data).
  - `src/codegenie/probes/layer_f/` — SCIP index output.
  - `src/codegenie/probes/layer_d/` — `import_graph` probe output.
  - `src/codegenie/probes/layer_g/` — `test_inventory` probe output.
  - **`IndexHealthProbe` (Phase 2 B2)** — the freshness signal each adapter folds into `confidence()`.
- **High-level impl:** `../High-level-impl.md §"Step 7" — `recipes/` and `adapters/` bullets.

## Goal

Land the four recipe classes (registered via `@register_recipe(PluginId("vulnerability-remediation--node--npm"))`), the four ADR-0032 adapter classes (referenced by `plugin.yaml`'s `contributes.adapters` from S7-01), and the wiring so that:
- `default_registry.resolve(...)` returns `ConcreteResolution` whose `composed_adapters` map contains all four (`scip`, `import_graph`, `dep_graph`, `test_inventory`).
- The plugin's `transforms()` method returns a non-empty `{TransformKind: RecipeEngine}` mapping wiring `NpmLockfileRecipeEngine` from S5-02.
- The per-plugin `RecipeRegistry` for `PluginId("vulnerability-remediation--node--npm")` iterates the four recipes in determined order and the orchestrator's `match_recipe` stage returns the right `RecipeOutcome` against fixture inputs covering all four recipes' applicability conditions.

## Acceptance criteria

- [ ] `plugins/vulnerability-remediation--node--npm/recipes/` contains four classes implementing the `RecipeProtocol` (see S5-01): `NpmLockfileSemverBumpRecipe`, `NpmPeerDepConflictRecipe`, `NpmTransitiveOverridesRecipe`, `NpmMajorBumpRefuseRecipe`. Each has an `applies(plan) -> Applicability` method returning `Applies(plan)` or `NotApplies(reason)`; `apply(plan, ctx) -> RecipeOutcome` for the three production recipes returns `Applied(NpmLockfileTransform)` via `NpmLockfileRecipeEngine`, and `NpmMajorBumpRefuseRecipe.apply(...)` returns `RecipeOutcome.NotApplicable(reason=MAJOR_BUMP_REFUSE)` (the refusal IS the applicability outcome — it never produces a transform).
- [ ] Each recipe is registered against the plugin's `RecipeRegistry` via `@register_recipe(PluginId("vulnerability-remediation--node--npm"), precedence=N)` at module-import time; precedence ordering is documented in the recipe class docstring (suggested: `NpmTransitiveOverridesRecipe=300 > NpmPeerDepConflictRecipe=200 > NpmLockfileSemverBumpRecipe=100 > NpmMajorBumpRefuseRecipe=50` — overrides first because they're surgical; refuse last because it's the safety net).
- [ ] `plugins/vulnerability-remediation--node--npm/adapters/` contains four classes implementing the ADR-0032 Protocols:
  - `npm_dep_graph.py: NpmDepGraphAdapter` implementing `DepGraphAdapter` — `consumers(package)` walks the parsed `package-lock.json`'s semver tree to return packages depending on the affected one.
  - `node_import_graph.py: NodeImportGraphAdapter` implementing `ImportGraphAdapter` — `reverse_lookup(module)` walks tree-sitter-typescript output (Phase 2 Layer D) + `tsconfig` path resolution.
  - `node_scip.py: NodeScipAdapter` implementing `ScipAdapter` — `refs(symbol)` reads `scip-typescript`'s indexer output (Phase 2 Layer F).
  - `jest_test_inventory.py: JestTestInventoryAdapter` implementing `TestInventoryAdapter` — `tests_exercising(file_set)` parses jest/vitest configs (Phase 2 Layer G).
- [ ] Each adapter's `confidence()` reads the `IndexHealthProbe` (B2) output and returns `AdapterConfidence.High` when fresh, `AdapterConfidence.Degraded(reason=...)` when the underlying index is stale, `AdapterConfidence.Unavailable(reason=...)` when the underlying probe output is missing (degradation taxonomy per ADR-0008).
- [ ] `plugin.yaml`'s `contributes.adapters` import paths (from S7-01) now resolve at plugin-load time; integration test asserts that `default_registry.resolve(PluginScope.parse("vulnerability-remediation--node--npm").unwrap()).composed_adapters` has exactly four entries keyed by `PrimitiveName(scip)` / `PrimitiveName(import_graph)` / `PrimitiveName(dep_graph)` / `PrimitiveName(test_inventory)`.
- [ ] Unit tests cover each recipe's `applies(...)` against at least four fixture inputs each:
  - For `NpmLockfileSemverBumpRecipe`: returns `Applies(plan)` for an in-range patch fixture; returns `NotApplies(NO_PATCH_IN_RANGE)` for a no-patch fixture; returns `NotApplies(MAJOR_BUMP_ONLY)` for a major-bump-only fixture; returns `NotApplies(PEER_DEP_CONFLICT)` for a peer-dep-conflict fixture.
  - Symmetric coverage for the other three.
- [ ] Integration test `tests/integration/test_npm_recipes_dispatch.py` runs the plugin's `RecipeRegistry.iter(...)` against three fixture plans and asserts the right recipe's `Applies(plan)` wins for each.
- [ ] Adapter unit tests cover the degraded-confidence path: synthesized stale `IndexHealthProbe` output ⇒ adapter `confidence() == AdapterConfidence.Degraded(reason=ScipIndexStale)` (or equivalent per adapter).
- [ ] No LLM SDK import is added under `plugins/vulnerability-remediation--node--npm/` (verified via `make fence` + `make lint-imports`).
- [ ] The red test from §TDD plan exists, was committed at red, and is now green.
- [ ] `ruff format --check`, `ruff check`, `mypy --strict` clean on touched files; existing tests still green (S7-01's scaffold test still passes — adapters/recipes are additive).

## Implementation outline

1. **Recipe Protocol conformance.** Each recipe is a class implementing `RecipeProtocol` (from S5-01). Public surface:
   ```python
   class RecipeProtocol(Protocol):
       recipe_id: RecipeId
       recipe_version: SemverVersion
       def applies(self, plan: RecipePlan) -> Applicability: ...
       def apply(self, plan: RecipePlan, ctx: ApplyContext) -> RecipeOutcome: ...
   ```
   The four recipes are plain classes (not subclasses of an ABC). `@register_recipe(PluginId(...), precedence=N)` at module-import time mutates the plugin-local `RecipeRegistry` (per S5-01 Gap-3 fix).
2. **`NpmLockfileSemverBumpRecipe.applies(...)`** — read the `plan` (which carries: affected package, vulnerable range, patched range, lockfile dependency tree). Returns `Applies(SemverBumpPlan(target_version=...))` IFF (a) `patched_range ∩ current_major != ∅`, AND (b) the `peerDependencies` walk of the patched version against the rest of the lockfile finds no conflict, AND (c) the affected package is a direct dependency (not transitive-only). Otherwise `NotApplies(reason)` with one of `NO_PATCH_IN_RANGE`, `MAJOR_BUMP_ONLY`, `PEER_DEP_CONFLICT`, `TRANSITIVE_ONLY`.
3. **`NpmPeerDepConflictRecipe.applies(...)`** — returns `Applies(...)` IFF the simple bump's `NotApplies` reason was `PEER_DEP_CONFLICT`. The recipe's `apply(...)` walks the peer-dep graph and proposes a coordinated multi-package bump (`SubprocessJail.run(npm install <pkg1>@v1 <pkg2>@v2)`). For Phase 3, this is *conservatively* `NotApplicable(PEER_DEP_CONFLICT_UNRESOLVABLE)` in cases where the multi-package bump itself would conflict — Phase 4's LLM fallback can do the search.
4. **`NpmTransitiveOverridesRecipe.applies(...)`** — returns `Applies(...)` IFF the affected package is transitive-only (not in `package.json` `dependencies`/`devDependencies`/`peerDependencies`) AND a patched version exists in any compatible range. The recipe's `apply(...)` writes an `overrides` block into `package.json` pinning the transitive, then re-runs `npm install --package-lock-only`.
5. **`NpmMajorBumpRefuseRecipe.applies(...)`** — returns `Applies(...)` IFF the only patched version is in a different major from the current one AND no other recipe already returned `Applies`. The recipe's `apply(...)` does NOT produce a transform; it returns `RecipeOutcome.NotApplicable(reason=MAJOR_BUMP_REFUSE)` — the refusal is the typed escalation channel to Phase 4 (per `RemediationOutcome.NotApplicable(reason)` in the architecture's §Decision points).
6. **Adapters.** Each adapter is a class implementing the corresponding ADR-0032 Protocol. Constructor takes the plugin's resolved probe-output paths (read from the `RepoContext` artifact `.codegenie/context/repo-context.yaml`). The methods:
   - `NpmDepGraphAdapter.consumers(package)` — walks the parsed `package-lock.json` semver tree (Phase 2 Layer E output).
   - `NodeImportGraphAdapter.reverse_lookup(module)` — reads Phase 2 Layer D import-graph output filtered to JS/TS.
   - `NodeScipAdapter.refs(symbol)` — reads `scip-typescript` index output from Phase 2 Layer F.
   - `JestTestInventoryAdapter.tests_exercising(file_set)` — reads Phase 2 Layer G test-inventory output filtered to Jest/Vitest.
   - `confidence()` — returns the `AdapterConfidence` sum (`High` / `Degraded(reason)` / `Unavailable(reason)`) folded from `IndexHealthProbe.freshness_for_layer(...)` plus the per-layer output's presence.
7. **Plugin wiring.** Update `api.py`'s `_VulnNodeNpmPlugin.adapters()` to return `{PrimitiveName("dep_graph"): NpmDepGraphAdapter(...), ...}` (four entries). Update `transforms()` to return `{TransformKind("npm_lockfile"): NpmLockfileRecipeEngine(...)}`. The constructor wiring (probe paths, engine config) happens at plugin-load time; per ADR-0002 the registration is lazy at first dispatch.
8. **`PLUGINS.lock` regen.** Because the plugin tree's file set changes, `PLUGINS.lock` row for `vulnerability-remediation--node--npm` must be regenerated. Note the operator workflow in the commit message.

## TDD plan — red / green / refactor

### Red

Test file path: `tests/unit/plugins/test_npm_recipes_applicability.py`

```python
# tests/unit/plugins/test_npm_recipes_applicability.py
import pytest

from codegenie.plugins.registry import default_registry
from codegenie.types.identifiers import PluginId, PrimitiveName
from codegenie.plugins.scope import PluginScope
from codegenie.transforms.applicability import Applies, NotApplies


@pytest.fixture
def plugin_registry():
    return default_registry


@pytest.fixture
def npm_plugin(plugin_registry):
    return plugin_registry.get(PluginId("vulnerability-remediation--node--npm"))


def test_plugin_exposes_four_adapters(npm_plugin):
    adapters = npm_plugin.adapters()
    assert set(adapters.keys()) == {
        PrimitiveName("scip"),
        PrimitiveName("import_graph"),
        PrimitiveName("dep_graph"),
        PrimitiveName("test_inventory"),
    }


def test_plugin_exposes_npm_lockfile_recipe_engine(npm_plugin):
    transforms = npm_plugin.transforms()
    assert any("npm_lockfile" in str(k) for k in transforms)


@pytest.mark.parametrize("fixture,expected_recipe_id,expected_kind", [
    ("simple-patch-in-range", "npm_lockfile_semver_bump", Applies),
    ("transitive-only-cve", "npm_transitive_overrides", Applies),
    ("major-bump-only", "npm_major_bump_refuse", Applies),
    ("peer-dep-conflict", "npm_peer_dep_conflict", Applies),
    ("no-patch-available", None, NotApplies),    # all-NotApplies short-circuit
])
def test_recipe_registry_dispatches_first_applies_wins(
    plugin_registry, fixture, expected_recipe_id, expected_kind
):
    from tests.fixtures.npm_plans import load_plan
    plan = load_plan(fixture)
    iter_result = plugin_registry.get(
        PluginId("vulnerability-remediation--node--npm")
    ).recipe_registry.iter(plan)
    first_applies = next((r for r in iter_result if isinstance(r.applicability, Applies)), None)
    if expected_kind is Applies:
        assert first_applies is not None
        assert first_applies.recipe.recipe_id == expected_recipe_id
    else:
        assert first_applies is None    # all NotApplies; orchestrator short-circuits


def test_npm_dep_graph_adapter_degrades_confidence_when_b2_stale(tmp_path):
    from codegenie.plugins.adapter_confidence import Degraded
    # Synthesize a stale IndexHealthProbe output; instantiate the adapter; expect Degraded.
    ...
```

Run; confirm `KeyError` on adapter lookup and `AttributeError` on `recipe_registry`; commit the red.

### Green

Implement the four recipes + four adapters; wire the plugin's `adapters()` / `transforms()` / `recipe_registry` accessors. Smallest shape: each recipe's `applies(...)` is a single `if` chain returning `Applies(plan)` or `NotApplies(reason)`; each adapter's `confidence()` is a single `match` on the `IndexHealthProbe` freshness signal.

### Refactor

- Lift the `NotApplies` reason enums into a single `NotApplicableReason` `StrEnum` (or extend S1-03's tagged union) so the orchestrator's `match` over `RecipeOutcome.NotApplicable(reason)` stays exhaustive.
- Confirm `mypy --strict` clean; the plugin's `_VulnNodeNpmPlugin.adapters()` return type is `dict[PrimitiveName, Adapter]` where `Adapter` is the union of the four ADR-0032 Protocols. Use `Protocol` structural typing — no inheritance.
- Confirm the recipes' `apply(...)` methods route through `NpmLockfileRecipeEngine` (S5-02), not re-implementing the lockfile rewrite. The recipe is the *what*; the engine is the *how*.
- Document precedence rationale in each recipe class docstring; do not bake precedence into the recipe's name.

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
| `plugins/vulnerability-remediation--node--npm/api.py` | Modified — `adapters()` returns four entries; `transforms()` returns `NpmLockfileRecipeEngine`; recipe imports trigger registration |
| `plugins/PLUGINS.lock` | Modified — regenerate the plugin's tree sha256 |
| `tests/fixtures/npm_plans/` | New — fixture plans (`simple-patch-in-range.json`, `transitive-only-cve.json`, `major-bump-only.json`, `peer-dep-conflict.json`, `no-patch-available.json`) |
| `tests/unit/plugins/test_npm_recipes_applicability.py` | New — parametric `applies(...)` coverage + adapter wiring asserts |
| `tests/unit/plugins/test_npm_adapters_confidence.py` | New — degraded-confidence path for each adapter |
| `tests/integration/test_npm_recipes_dispatch.py` | New — `RecipeRegistry.iter(...)` first-Applies-wins integration |

## Out of scope

- **End-to-end Express CVE remediation** — S8-02 lands `tests/integration/test_end_to_end_express_cve.py` and the golden lockfile diff.
- **The synthetic `example--noop--*` plugin + the three-plugin contract bake test** — S7-04.
- **The universal HITL plugin** — S7-03.
- **Phase 4 LLM fallback dispatch** — Phase 4. This story's recipes return `NotApplicable(reason)` for cases Phase 4 will reach; that's the contract boundary.
- **Coordinated multi-package bump search** in `NpmPeerDepConflictRecipe` — the simple peer-dep walk is enough for Phase 3; deep search is Phase 4's LLM-assisted territory.
- **Yarn Berry / pnpm support** — those are separate `(*--node--yarn-berry)` / `(*--node--pnpm)` plugins added by addition in Phase 7+.
- **OpenRewrite recipe engine wiring** — S5-03's scaffold; the npm plugin does not list it under `transforms()` in Phase 3.

## Notes for the implementer

- **`Applicability` is a sum type, NOT a `bool`.** The single most attacked design choice in this codebase per the critic (`Literal["*"]` collapse to `str` at runtime is the same anti-pattern at the scope layer). `applies(plan) -> bool` is a refactor regression — surface it loudly if you find it anywhere.
- **The recipes wrap the engine; the engine does the work.** `NpmLockfileSemverBumpRecipe.apply(...)` is ~10 lines: validate the `Applies(plan)` payload, hand off to `NpmLockfileRecipeEngine.apply(plan, ctx)`, return its `RecipeOutcome`. Do NOT re-implement lockfile parsing or `npm install` invocation inside the recipe — that's the engine's surface (S5-02).
- **Precedence values are recipe-local, not global.** The numeric precedence (300 / 200 / 100 / 50) is what the per-plugin `RecipeRegistry` sorts by; another plugin's recipes have their own precedence space. Do NOT global-sort; the architecture's first-`Applies(plan)`-wins is per-`RecipeRegistry`.
- **Adapter `confidence()` returns a sum type, not a `float`.** Production ADR-0032 §"Adapter Protocols" sketches `confidence() -> float`, but Phase 3 typed it as `AdapterConfidence = High | Degraded(reason) | Unavailable(reason)` per ADR-0008 (sum type for state). Use the sum type variant; the BundleBuilder's degradation logic matches on it. If S1-03 didn't ship `AdapterConfidence`, that's a real gap — surface it.
- **`tsconfig` path resolution is hard.** Don't try to be exhaustive in Phase 3. The `NodeImportGraphAdapter` reads what Phase 2 Layer D already resolved; if Layer D didn't resolve a path, `reverse_lookup(...)` returns an incomplete list and `confidence()` degrades. Honest framing — fail loud, not silent.
- **Fixture plans are JSON; load via `tests/fixtures/npm_plans/__init__.py:load_plan(name)`.** Keep them small (10-30 lines each) — they're inputs to `applies(...)`, not full repo snapshots. A `RecipePlan` is the typed input shape; if S5-01 named it differently, mirror that.
- **Do NOT skip the integrity-mismatch path.** Regenerating `PLUGINS.lock` is part of this story; the CI's `PluginRejected(integrity_mismatch)` test from S2-03 will fail if you forget. The pre-commit hook from S2-03's risk-mitigation should auto-regen, but verify by hand if it's not wired yet.
- **`IndexHealthProbe` (B2) is the single most important probe** per CLAUDE.md. The adapters' degradation is the consumer-side payoff — when B2 reports stale, three of the four adapters degrade; the TCCM-declared fallback fires; `AdapterDegraded` is emitted; `TrustOutcome.confidence` becomes `"degraded"`. This is the load-bearing honest-confidence path (Goal G8); test it explicitly.
- **`NpmMajorBumpRefuseRecipe` is the safety net, not a failure.** Its `Applies(plan)` returning IS the deterministic-recipe-path's correct answer when no in-major patch exists. Phase 4 reads `NotApplicableReason.MAJOR_BUMP_REFUSE` and decides whether an LLM-assisted major-bump migration is in scope. The refusal is the typed escalation, not an error.
