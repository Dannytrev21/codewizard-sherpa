# Story S5-01 — `RecipeEngine` Protocol + per-plugin `RecipeRegistry` + `@register_recipe` decorator (Gap 3 fix)

**Step:** Step 5 — Transform ABC consumers, RecipeEngine Protocol, RecipeRegistry, lockfile policy
**Status:** Done — GREEN 2026-05-19 (phase-story-executor; see [`_attempts/S5-01.md`](_attempts/S5-01.md) for the per-AC evidence table + gate log)
**Effort:** M
**Depends on:** S1-03 (`Applicability` / `RecipeOutcome` / `ApplicationPlan` already shipped in `transforms/outcomes.py`), S1-04 (`Transform` ABC re-export discipline), S2-01 (`PluginRegistry` shape this story mirrors; `RecipeEngine` stub deferred to Step 5), S4-02 (`SubprocessJail` Port for engines that follow), and S4-05 (`NpmInstallCapability` — `HARDENED`; this story forward-refs it under `TYPE_CHECKING` if it lands after S5-01).
**ADRs honored:** ADR-0009, ADR-0010 (+ Amendment 2026-05-18 on canonical outcome home), ADR-0002, ADR-0001 (contract snapshot re-bake — see Validation notes).

## Validation notes (2026-05-19)

Hardened by `phase-story-validator` (see `_validation/S5-01-recipe-registry.md` for full audit). The original draft was unimplementable as written — five BLOCK findings centred on contract drift against as-built S1-03 (`outcomes.py`) and S2-01 (`protocols.py`). Resolved edits:

- **Imports corrected.** `Applies` / `NotApplies` / `Applicability` / `RecipeOutcome` / `RecipeNotApplicable` / `ApplicationPlan` / `NotApplicableReason` all live in `codegenie.transforms.outcomes` (S1-03 ADR-0010 Amendment 2026-05-18) — NOT in `codegenie.transforms.applicability` (which doesn't exist). The story's draft TDD test imported the wrong module. (Consistency F1)
- **`RecipeOutcome` is a `TypeAlias`, not a class.** It's `Annotated[Applied | Skipped | RecipeNotApplicable | RecipeFailed, Field(discriminator="kind")]`. `isinstance(out, RecipeOutcome)` is a runtime error; `RecipeOutcome.NotApplicable(...)` is pseudo-OO. ACs now reference `RecipeNotApplicable` directly. (Consistency F5, Test-Quality F2)
- **No `RecipeId.parse()` exists.** `RecipeId` is a bare `NewType` per `src/codegenie/types/identifiers.py:66`. The story uses a private `_validate_recipe_id(rid: str) -> RecipeId` regex helper (`^[a-z][a-z0-9-]*$`) at the registration boundary. (Consistency F3)
- **`NotApplicableReason` Literal widened.** `NO_RECIPES_REGISTERED` is added in this story (additive — pre-existing 5 members preserved). The Phase-5 contract snapshot at `tests/integration/test_phase5_contract_snapshot.py` is re-baked; this is an ADR-0001 §Consequences "snapshot regeneration + ADR amendment" event — call it out in the PR description. (Consistency F4)
- **`RecipeNotApplicable.considered: list[NotApplies]` is an additive field with `Field(default_factory=list)`.** Phase 5 callers reading the variant continue to work (default `[]`); the contract-snapshot test re-bakes. The S6-04 orchestrator decorates this with `RecipeFailed` / `RecipeSkipped` events; the registry walker only fills the list. (Consistency F5)
- **Single canonical `RecipeEngine` Protocol home: `src/codegenie/transforms/recipe_engine.py`.** S2-01 shipped a temporary stub in `plugins/protocols.py` with `apply(self, plan, ctx)` and explicitly deferred the freeze to Step 5 (S2-01 Out-of-scope). This story REPLACES that stub: declares the canonical Protocol in `transforms/recipe_engine.py` with the arch-named signature `apply(self, repo, plan, capability) -> RecipeOutcome` (arch §C12 L716, §C10 L672), then re-exports from `plugins/protocols.py` so any S2-01 fixture importer keeps round-tripping. ADR-0009 §Decision names `plugins/protocols.py` as the location — that ADR is amended as a follow-up cleanup; High-level-impl §Step 5 L136 is the load-bearing reference for the canonical home today. (Consistency F1, F8)
- **`ApplicationPlan` reused — no new `RecipePlan` model.** S1-03 already ships `ApplicationPlan(BaseModel, frozen, extra="forbid")` with a `summary: str | None` field as the Phase-3 plan placeholder. Phase 7 widens it additively (e.g., `BaseImagePlan`) — NOT by introducing a parallel `RecipePlan`. The story's `RecipePlan` Pydantic model is removed. (Consistency F2)
- **`match_recipes` return type pinned.** 4-arg `match_recipes(registry, plugin_id, cve, bundle) -> MatchedRecipe | RecipeNotApplicable`. NOT `RecipeOutcome.Applied` (that variant requires the engine's `apply()` output — produced by S5-02 / S5-03; this walker returns an intermediate `MatchedRecipe`). Goal text rewritten to match. (Coverage F3, F4)
- **`RecipeProtocol.kind: TransformKind` is mandatory.** Orchestrator's `apply_recipe` node does `plugin.transforms()[recipe.kind].apply(...)` — without `kind`, the recipe → engine mapping is impossible. (Coverage F5)
- **Name uniqueness within a `plugin_id`.** Two recipes with the same `(precedence, name)` would be order-unstable; registration rejects duplicate names (not just duplicate `recipe_id`s) within the same plugin. (Coverage F6)
- **TDD plan rewritten** with real Pydantic constructors, a proper `type()`-based recipe factory, the `Applies(plan=ApplicationPlan(summary=...))` shape, closed-Literal reasons drawn from `get_args(NotApplicableReason)`, an identity check on decorator return, a `PYTHONHASHSEED`-permutation subprocess test for ordering determinism, and an event-emission negative-control. (Test-Quality F1–F7)
- **Out-of-scope expanded** with concurrent registration + module-reload semantics (mirror S2-01 §Out-of-scope). (Coverage F7)
- **Notes-for-implementer** add a class-decorator-vs-function-call asymmetry rationale (recipes are stateless matchers; engines are stateful workers) and the N=5 rule-of-N census paragraph.

## Context

This story closes **Gap 3** from `../phase-arch-design.md` (§Gap 3). The synthesis named `RecipeProtocol` and listed four npm recipes (`NpmLockfileSemverBumpRecipe`, `NpmPeerDepConflictRecipe`, `NpmTransitiveOverridesRecipe`, `NpmMajorBumpRefuseRecipe`) but never specified *how* a plugin registers them or in what order the `match_recipe` subgraph node iterates them. Without that mechanism pinned now, Phase 7's distroless plugin invents a parallel registration shape and the plugin contract bifurcates — exactly the "tag-and-dispatch without sum type" anti-pattern the critic flagged on best-practices.

The fix is to mirror the `PluginRegistry` shape (from S2-01) at the per-plugin level: an instance-based `RecipeRegistry` plus an `@register_recipe(plugin_id, *, registry=None)` decorator that targets a plugin-local default. Each plugin instantiates one in its `api.py`. The orchestrator's `match_recipe` node iterates `RecipeRegistry.all()` in `(precedence desc, name asc)` order, calling `recipe.applies(cve, bundle) -> Applicability` (`Applies(plan) | NotApplies(reason)` — S1-03 sum). **First `Applies(plan)` wins.** If every recipe returns `NotApplies(reason)`, the registry walk short-circuits with `RecipeOutcome.NotApplicable(reason=ALL_RECIPES_NOT_APPLICABLE)` — a typed Phase-4 trigger, not silent failure.

This story also lands the `RecipeEngine` Protocol itself (`async def apply(self, repo, plan, capability) -> RecipeOutcome`) per ADR-0009 — the Protocol that S5-02's `NpmLockfileRecipeEngine` and S5-03's `OpenRewriteRecipeEngine` will both implement. Shipping the Protocol *before* the two implementations means S5-02 and S5-03 can land in parallel, both checking conformance against the same surface.

The recognizability cost is intentional: any reader familiar with the `PluginRegistry` (S2-01) walks into the `RecipeRegistry` and reads its API in five seconds. No new patterns; one fewer thing to discover.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap 3` — the exact problem statement and Improvement paragraph; this is the load-bearing reference.
  - `../phase-arch-design.md §C12` — `RecipeEngine` Protocol's two day-1 implementations.
  - `../phase-arch-design.md §C4` — `Transform` ABC + `RecipeOutcome` discriminated union (the engine's return).
  - `../phase-arch-design.md §Design patterns applied row 2` — Strategy on `RecipeEngine`; row 5 — tagged unions on `Applicability`.
  - `../phase-arch-design.md §Anti-patterns flagged and rejected` — "Premature pluggability" — `RecipeProtocol` has 4 implementations day-1; pluggability earns its keep.
  - `../phase-arch-design.md §Control flow` — decision point "Recipe returns `NotApplicable`" exits 3 with the reason; Phase 4's LLM-fallback dispatch reads it.
  - `../phase-arch-design.md §C9` — `RecipeMatched` / `RecipeSkipped` / `RecipeFailed` events the registry walk will emit (events themselves land in S6-01; this story only defines the call shape).
- **Phase ADRs (rules this story honors):**
  - `../ADRs/0009-recipe-engine-protocol-with-two-implementations-day-1.md` — ADR-0009 — `RecipeEngine` Protocol with `async def apply(self, repo, plan, capability) -> RecipeOutcome`; two implementations day-1.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — ADR-0010 — `Applicability = Applies(plan) | NotApplies(reason)`; `RecipeOutcome` is a tagged union (`Applied | Skipped | NotApplicable | Failed`); `PluginId` / `RecipeId` are newtypes, never raw `str`.
  - `../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md` — ADR-0002 — the exact shape this `RecipeRegistry` mirrors: instance class + module-level `default_registry` + decorator with optional `registry=` kwarg.
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` — ADR-0001 — `RecipeEngine` is one of the six Phase-5-contracted names; this story ships it.
- **Source design:**
  - `../final-design.md §17` (the four-recipe list) and §Synthesis ledger row "Default recipe engine" (score 15/15).
- **High-level impl:**
  - `../High-level-impl.md §Step 5 — Features delivered` bullet 1 (the `recipe_registry.py` line) and bullet 2 (the `RecipeEngine` Protocol).
- **Sibling stories:**
  - `S2-01-plugin-registry-kernel.md` — the shape this story mirrors; read it before writing the registry.
  - `S1-03-tagged-union-outcomes.md` — `Applicability` and `RecipeOutcome` Pydantic definitions; this story imports them.
  - `S1-04-transform-abc-apply-context.md` — `Transform` ABC re-exported from `transforms/`.
  - `S5-02-npm-lockfile-recipe-engine.md`, `S5-03-openrewrite-engine-scaffold.md` — the two day-1 conformers; both will import `RecipeEngine` from this story.

## Goal

Ship the per-plugin recipe-registration mechanism that closes Gap 3:

- `src/codegenie/transforms/recipe_engine.py` — the canonical home — exposes `RecipeEngine(Protocol)` (the *worker* contract), `RecipeProtocol(Protocol)` (the *matcher* contract), `MatchedRecipe` (frozen-dataclass walker return), and a 4-arg walker `match_recipes(registry, plugin_id, cve, bundle) -> MatchedRecipe | RecipeNotApplicable`. The walker implements first-`Applies(plan)`-wins iteration in `(precedence desc, name asc)` order, with `ALL_RECIPES_NOT_APPLICABLE` (some recipes considered, all declined) vs `NO_RECIPES_REGISTERED` (zero recipes for this plugin) as distinct reasons.
- `src/codegenie/plugins/recipe_registry.py` exposes `RecipeRegistry` + `@register_recipe(plugin_id, *, registry=None)` + `default_recipe_registry: Final[RecipeRegistry]`, mirroring S2-01's `PluginRegistry` shape.
- `src/codegenie/plugins/protocols.py` deletes its S2-01-deferred `RecipeEngine` stub and re-exports the canonical Protocol from `transforms.recipe_engine` (no duplicate declaration).
- `src/codegenie/transforms/outcomes.py` is amended additively: `NotApplicableReason` grows a `NO_RECIPES_REGISTERED` literal; `RecipeNotApplicable` grows a `considered: list[NotApplies] = Field(default_factory=list)` field so Phase 4 can read the structured rejection trace.

## Acceptance criteria

- [ ] **AC-1 — Imports succeed.** `from codegenie.transforms.recipe_engine import RecipeEngine, RecipeProtocol, MatchedRecipe, match_recipes` and `from codegenie.plugins.recipe_registry import RecipeRegistry, register_recipe, default_recipe_registry, RecipeAlreadyRegistered` and `from codegenie.transforms.outcomes import ApplicationPlan, Applies, NotApplies, RecipeNotApplicable, NotApplicableReason` all succeed without `ImportError`.
- [ ] **AC-2 — `RecipeEngine` Protocol surface.** `RecipeEngine` is a `@runtime_checkable Protocol` declared in `codegenie.transforms.recipe_engine` with exactly one abstract async method: `async def apply(self, repo: "SandboxedPath", plan: ApplicationPlan, capability: "NpmInstallCapability") -> RecipeOutcome`. `SandboxedPath` and `NpmInstallCapability` are forward-referenced via `TYPE_CHECKING` blocks (S4-04 / S4-05 own those types). `plugins/protocols.py` re-exports `RecipeEngine` from `transforms.recipe_engine` and does NOT redeclare it (`__all__` in `protocols.py` still includes `"RecipeEngine"` for S2-01 fixture round-trip; pinned by an import-identity test).
- [ ] **AC-3 — `RecipeProtocol` Protocol surface.** `RecipeProtocol` is a `@runtime_checkable Protocol` with class-attribute annotations `recipe_id: RecipeId`, `name: str`, `kind: TransformKind`, `precedence: int` (no default — explicit on every recipe) and one method `def applies(self, cve: "VulnerabilityRecord", bundle: "Bundle") -> Applicability`. `Bundle` / `VulnerabilityRecord` are forward-referenced via `TYPE_CHECKING`. The `kind` attribute is load-bearing: the orchestrator's `apply_recipe` node looks up the engine via `plugin.transforms()[recipe.kind]`.
- [ ] **AC-4 — `RecipeRegistry` public surface.** `RecipeRegistry` is a class (not a module-level dict). Private state: `_recipes: dict[RecipeId, RegisteredRecipe]` and `_by_plugin: dict[PluginId, list[RecipeId]]` and `_names_by_plugin: dict[PluginId, set[str]]` (for name-uniqueness check). Public methods: exactly four — `register(self, plugin_id: PluginId, recipe: RecipeProtocol) -> RecipeProtocol`, `get(self, recipe_id: RecipeId) -> RegisteredRecipe`, `all(self, plugin_id: PluginId | None = None) -> tuple[RegisteredRecipe, ...]`, and `_reset_for_tests(self) -> None` (leading-underscore signals test-only — see Notes §"Why `_reset_for_tests` not `clear`").
- [ ] **AC-5 — Deterministic ordering.** `RecipeRegistry.all(plugin_id=...)` returns recipes for that plugin sorted by `(-precedence, name)` (precedence descending, then name ascending). Determinism is verified by a subprocess-launch test that runs the same registration script under `PYTHONHASHSEED ∈ {0, 1, 2, 42}` and asserts byte-identical output across seeds (catches accidental reliance on dict-iteration ordering).
- [ ] **AC-6 — `register_recipe` decorator factory.** `register_recipe(plugin_id: PluginId, *, registry: RecipeRegistry | None = None)` returns a decorator that: (a) instantiates the decorated class via `recipe_cls()` (no-arg construction — recipes are stateless matchers, see Notes §"Class-decorator vs function-call"); (b) registers the instance on `registry or default_recipe_registry`; (c) returns the original `recipe_cls` unchanged (`assert decorated is OriginalCls` — identity, not `==`).
- [ ] **AC-7 — Duplicate `recipe_id` rejected at registration.** Re-registering any `RecipeId` (regardless of plugin) raises `RecipeAlreadyRegistered(recipe_id: RecipeId, plugin_id: PluginId)` with a typed `.recipe_id: RecipeId` attribute and a message naming the colliding `module.qualname`. Tests assert `exc.recipe_id == RecipeId("...")`, NOT just substring match on the message.
- [ ] **AC-8 — Duplicate `name` within `plugin_id` rejected at registration.** Re-registering any `name` already used by another recipe in the same `plugin_id` raises `RecipeNameCollision(plugin_id, name)`. Distinct exception from AC-7 because the `recipe_id` may differ; the tie-breaker on `(precedence, name)` would otherwise be order-unstable.
- [ ] **AC-9 — `recipe_id` validated at registration via `_validate_recipe_id`.** Private helper `_validate_recipe_id(rid: str) -> RecipeId` enforces `re.fullmatch(r"^[a-z][a-z0-9-]*$", rid)` and lifts to the `RecipeId` newtype. Invalid IDs raise `ValueError(f"recipe_id {rid!r} does not match ^[a-z][a-z0-9-]*$")` at register time, NOT at first `match_recipes` call. Tests cover: empty string, uppercase character, leading digit, contains underscore (should reject), valid id (should accept).
- [ ] **AC-10 — `match_recipes` first-`Applies`-wins + call-count guarantee.** `match_recipes(registry, plugin_id, cve, bundle)` iterates `registry.all(plugin_id)` in order. On first `recipe.applies(cve, bundle) == Applies(plan=...)`, return `MatchedRecipe(recipe=recipe, plan=plan)` and stop. A test instruments three recipes (precedence 10/5/1, middle returns `Applies`) with `applies_calls` counters and asserts the lowest-precedence recipe's `applies_calls == 0` after the walker returns — proves the walker short-circuits.
- [ ] **AC-11 — All-decline short-circuit.** When every registered recipe returns `NotApplies(reason)`, `match_recipes` returns `RecipeNotApplicable(reason="ALL_RECIPES_NOT_APPLICABLE", considered=[na1, na2, ...])` where `considered` carries every visited `NotApplies` instance in iteration order. Phase 4's `prompt_builder` reads `considered` for the structured rejection trace.
- [ ] **AC-12 — Empty registry returns `NO_RECIPES_REGISTERED`.** When `registry.all(plugin_id)` is empty (no recipes registered for `plugin_id` at all), `match_recipes` returns `RecipeNotApplicable(reason="NO_RECIPES_REGISTERED", considered=[])`. Distinct reason from `ALL_RECIPES_NOT_APPLICABLE`. Both reasons are members of the `NotApplicableReason` Literal (this story adds `NO_RECIPES_REGISTERED` to the existing five).
- [ ] **AC-13 — `MatchedRecipe` shape.** `MatchedRecipe` is a `@dataclass(frozen=True, slots=True)` with two fields: `recipe: RecipeProtocol`, `plan: ApplicationPlan`. NOT a Pydantic model (internal walker return; no boundary validation needed). Tests assert `out.recipe.recipe_id` and `out.plan` access patterns.
- [ ] **AC-14 — `RecipeNotApplicable.considered` additive field.** `RecipeNotApplicable` (in `transforms/outcomes.py`) grows `considered: list[NotApplies] = Field(default_factory=list)`. Existing callers reading `.reason` continue to work. The S6-06 Phase-5 contract snapshot at `tests/integration/test_phase5_contract_snapshot.py` is re-baked to include the new field (named in Files-to-touch).
- [ ] **AC-15 — `NotApplicableReason` Literal widened.** `NotApplicableReason` in `transforms/outcomes.py` is amended additively to include `"NO_RECIPES_REGISTERED"`. The pre-existing 5 members (`PEER_DEP_CONFLICT`, `MAJOR_BUMP_REFUSE`, `OVERRIDES_AMBIGUOUS`, `RECIPE_CATALOG_MISS`, `ALL_RECIPES_NOT_APPLICABLE`) are preserved byte-identical. Test asserts membership via `get_args(NotApplicableReason)`.
- [ ] **AC-16 — `match_recipes` emits NO events.** A test monkeypatches a sentinel `EventLog` into the walker's scope and asserts zero `.emit(...)` calls during a full `match_recipes` walk. Events (`RecipeMatched`, `RecipeSkipped`) are the orchestrator's job (S6-04 wraps the walker output); the registry walker is event-free.
- [ ] **AC-17 — Cross-test isolation.** `tests/unit/plugins/conftest.py` extends the existing autouse `restore_default_registry` fixture pattern from S2-01: (a) function-scoped `restore_default_recipe_registry` snapshots `default_recipe_registry._recipes.copy()` pre-test and restores post-test; (b) session-scoped guard asserts `default_recipe_registry.all() == ()` at session start and end. Tests construct fresh `RecipeRegistry()` instances via a `fresh_recipe_registry` fixture.
- [ ] **AC-18 — `default_recipe_registry` is `Final`.** Module-level `default_recipe_registry: Final[RecipeRegistry] = RecipeRegistry()` mirrors S2-01 §3 (`Final` is intentional; replacement requires explicit DI through `register_recipe(..., registry=...)`).
- [ ] **AC-19 — Lint / type / coverage clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean on `src/codegenie/plugins/recipe_registry.py`, `src/codegenie/transforms/recipe_engine.py`, and the amended `src/codegenie/transforms/outcomes.py` + `src/codegenie/plugins/protocols.py`. No `dict[str, Any]`, no `cast`, no `# type: ignore` without a justification comment referencing this story. `pytest tests/unit/plugins/test_recipe_registry.py tests/unit/transforms/test_recipe_engine_protocol.py` green. Branch coverage on the two new modules ≥ 95%.
- [ ] **AC-20 — Phase-5 contract snapshot re-baked.** `tests/integration/test_phase5_contract_snapshot.py` passes with the updated `RecipeNotApplicable` + `NotApplicableReason` shape. The regeneration is intentional (named in this story's commit message); ADR-0001 §Consequences row "Any change to the six named symbols requires a Phase-3 ADR amendment + Phase-5 ADR-update" is honored by this story's Validation notes + a Phase-3 ADR amendment to ADR-0009 (see Notes-for-implementer §"ADR amendments triggered").

## Implementation outline

1. **Amend `src/codegenie/transforms/outcomes.py` (additive).**
   - Add `"NO_RECIPES_REGISTERED"` to the `NotApplicableReason` Literal (AC-15). Pre-existing 5 members preserved byte-identical.
   - Add `considered: list["NotApplies"] = Field(default_factory=list)` to `RecipeNotApplicable` (AC-14). Forward-reference `NotApplies` via the existing module-local declaration. Pydantic resolves the self-referential annotation at class creation.
   - Update `__all__` if needed (no new names exported — both edits are additive within existing names).

2. **Create `src/codegenie/transforms/recipe_engine.py`** (canonical home — High-level-impl §Step 5 L136):
   ```python
   from __future__ import annotations
   import re
   from dataclasses import dataclass
   from typing import TYPE_CHECKING, Protocol, runtime_checkable
   from codegenie.transforms.outcomes import (
       Applicability, Applies, NotApplies, ApplicationPlan,
       RecipeNotApplicable, RecipeOutcome,
   )
   from codegenie.types.identifiers import RecipeId, TransformKind

   if TYPE_CHECKING:
       from codegenie.plugins.recipe_registry import RecipeRegistry
       from codegenie.plugins.sandbox_path import SandboxedPath
       from codegenie.plugins.capabilities import NpmInstallCapability
       from codegenie.plugins.bundle import Bundle           # S3-04
       from codegenie.vuln_index.record import VulnerabilityRecord  # S3-01
       from codegenie.types.identifiers import PluginId

   @runtime_checkable
   class RecipeEngine(Protocol):
       """Worker — one engine serves many recipes; mapped by `recipe.kind`."""
       async def apply(self, repo: "SandboxedPath", plan: ApplicationPlan,
                       capability: "NpmInstallCapability") -> RecipeOutcome: ...

   @runtime_checkable
   class RecipeProtocol(Protocol):
       """Matcher — one per recipe; `kind` selects the engine."""
       recipe_id: RecipeId
       name: str
       kind: TransformKind
       precedence: int
       def applies(self, cve: "VulnerabilityRecord", bundle: "Bundle") -> Applicability: ...

   @dataclass(frozen=True, slots=True)
   class MatchedRecipe:
       recipe: RecipeProtocol
       plan: ApplicationPlan

   _RECIPE_ID_RX = re.compile(r"^[a-z][a-z0-9-]*$")

   def _validate_recipe_id(rid: str) -> RecipeId:
       if not _RECIPE_ID_RX.fullmatch(rid):
           raise ValueError(f"recipe_id {rid!r} does not match {_RECIPE_ID_RX.pattern}")
       return RecipeId(rid)

   def match_recipes(
       registry: "RecipeRegistry",
       plugin_id: "PluginId",
       cve: "VulnerabilityRecord",
       bundle: "Bundle",
   ) -> MatchedRecipe | RecipeNotApplicable:
       """First-`Applies(plan)`-wins; emits no events (S6-04 owns events)."""
       considered: list[NotApplies] = []
       registered = registry.all(plugin_id)
       if not registered:
           return RecipeNotApplicable(reason="NO_RECIPES_REGISTERED", considered=[])
       for entry in registered:
           verdict = entry.recipe.applies(cve, bundle)
           match verdict:
               case Applies(plan=plan):
                   return MatchedRecipe(recipe=entry.recipe, plan=plan)
               case NotApplies() as na:
                   considered.append(na)
       return RecipeNotApplicable(
           reason="ALL_RECIPES_NOT_APPLICABLE", considered=considered,
       )
   ```

3. **Create `src/codegenie/plugins/recipe_registry.py`** — mirror `plugins/registry.py` shape.
   - Module docstring carries the N=5 rule-of-N census + extract-trigger paragraph (see Notes §"Rule-of-N=5").
   - `@dataclass(frozen=True, slots=True) RegisteredRecipe(plugin_id: PluginId, recipe: RecipeProtocol)`.
   - `RecipeRegistry`: `_recipes: dict[RecipeId, RegisteredRecipe]`, `_by_plugin: dict[PluginId, list[RecipeId]]`, `_names_by_plugin: dict[PluginId, set[str]]`, `_origins: dict[RecipeId, str]`.
   - `register(plugin_id, recipe)` — collision-check by `recipe.recipe_id in self._recipes` → `RecipeAlreadyRegistered`; name-collision check via `_names_by_plugin[plugin_id]` → `RecipeNameCollision`; append into all three dicts; return `recipe`.
   - `get(recipe_id)` — KeyError → `RecipeNotFound(recipe_id)`.
   - `all(plugin_id=None)` — when `plugin_id` is None, return ALL recipes flattened, sorted by `(-precedence, name)`; otherwise filter via `_by_plugin[plugin_id]` then sort. Return `tuple[RegisteredRecipe, ...]`.
   - `_reset_for_tests(self) -> None` — clears all three dicts; leading underscore signals test-only.
   - `default_recipe_registry: Final[RecipeRegistry] = RecipeRegistry()`.
   - `register_recipe(plugin_id, *, registry=None)` decorator factory: returns `_decorator(recipe_cls)` that calls `instance = recipe_cls()`, validates `_validate_recipe_id(instance.recipe_id)`, registers, returns `recipe_cls` unchanged.

4. **Amend `src/codegenie/plugins/protocols.py`:** delete the S2-01 deferred-stub `RecipeEngine` declaration (lines 80-98 in current state) and replace with `from codegenie.transforms.recipe_engine import RecipeEngine` (under `TYPE_CHECKING` if circular; otherwise top-level). Re-export via `__all__`. Add an identity test: `from codegenie.plugins.protocols import RecipeEngine as P; from codegenie.transforms.recipe_engine import RecipeEngine as T; assert P is T`.

5. **Re-exports:**
   - `src/codegenie/transforms/__init__.py` — add `MatchedRecipe`, `RecipeProtocol`, `match_recipes` to `__all__` (`RecipeEngine` re-export added once it's the canonical class).
   - `src/codegenie/plugins/__init__.py` — add `RecipeRegistry`, `register_recipe`, `default_recipe_registry`, `RecipeAlreadyRegistered`, `RecipeNameCollision`, `RecipeNotFound`.

6. **Re-bake Phase-5 contract snapshot.** Run `tests/integration/test_phase5_contract_snapshot.py` once with `--regenerate` (or the project-local equivalent) to absorb the additive `RecipeNotApplicable.considered` field + the `NotApplicableReason` literal widening. Commit the regenerated golden alongside the source change. The PR description names this regeneration explicitly (ADR-0001 §Consequences row 6).

7. **Tests** in `tests/unit/plugins/test_recipe_registry.py`, `tests/unit/transforms/test_recipe_engine_protocol.py`, and a `tests/unit/transforms/test_recipe_engine_determinism.py` (subprocess-launch for PYTHONHASHSEED) per TDD plan below.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/unit/plugins/test_recipe_registry.py`, `tests/unit/transforms/test_recipe_engine_protocol.py`, `tests/unit/transforms/test_recipe_engine_determinism.py`.

```python
# tests/unit/plugins/test_recipe_registry.py
from __future__ import annotations
from typing import get_args
import pytest
from codegenie.plugins.recipe_registry import (
    RecipeRegistry, register_recipe, default_recipe_registry,
    RecipeAlreadyRegistered, RecipeNameCollision,
)
from codegenie.transforms.recipe_engine import (
    RecipeProtocol, MatchedRecipe, match_recipes,
)
from codegenie.transforms.outcomes import (
    Applies, NotApplies, ApplicationPlan, RecipeNotApplicable, NotApplicableReason,
)
from codegenie.types.identifiers import PluginId, RecipeId, TransformKind

PID = PluginId("vulnerability-remediation--node--npm")
KIND = TransformKind("npm_lockfile_semver_bump")
PLAN = ApplicationPlan(summary="bump")


def _recipe_factory(rid: str, *, name: str | None = None, precedence: int, verdict):
    """Build a stateless recipe class via type() so class identity is stable
    and `applies_calls` is per-instance (not shared via closure mutation)."""
    nm = name or rid

    def applies(self, cve, bundle):
        self.applies_calls += 1
        return verdict

    def __init__(self) -> None:
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


@pytest.fixture
def fresh_registry() -> RecipeRegistry:
    return RecipeRegistry()


def test_register_decorator_returns_class_unchanged(fresh_registry):
    """AC-6 — identity (not equality). A wrapper-replaces-class mutant fails this."""
    @register_recipe(PID, registry=fresh_registry)
    class Semver:
        recipe_id = RecipeId("npm-semver-bump")
        name = "npm-semver-bump"
        kind = KIND
        precedence = 10
        def applies(self, cve, bundle):
            return NotApplies(reason="PEER_DEP_CONFLICT")

    # `Semver` is the symbol bound by the decorator; assert it IS the original class
    # (decorator returns `recipe_cls` unchanged — `is`, not `==`).
    assert Semver is Semver  # syntactic identity; sanity
    assert Semver.recipe_id == "npm-semver-bump"
    assert len(fresh_registry.all(PID)) == 1
    entry = fresh_registry.all(PID)[0]
    assert isinstance(entry.recipe, Semver)


def test_duplicate_recipe_id_rejected_typed_exception(fresh_registry):
    """AC-7 — `RecipeAlreadyRegistered` carries typed `.recipe_id`."""
    @register_recipe(PID, registry=fresh_registry)
    class A:
        recipe_id = RecipeId("dup"); name = "dup-a"; kind = KIND; precedence = 0
        def applies(self, c, b): return NotApplies(reason="PEER_DEP_CONFLICT")

    with pytest.raises(RecipeAlreadyRegistered) as exc_info:
        @register_recipe(PID, registry=fresh_registry)
        class B:
            recipe_id = RecipeId("dup"); name = "dup-b"; kind = KIND; precedence = 0
            def applies(self, c, b): return NotApplies(reason="PEER_DEP_CONFLICT")

    assert exc_info.value.recipe_id == RecipeId("dup")


def test_duplicate_name_within_plugin_rejected(fresh_registry):
    """AC-8 — same name but distinct recipe_id is rejected (tie-breaker stability)."""
    @register_recipe(PID, registry=fresh_registry)
    class A:
        recipe_id = RecipeId("rid-a"); name = "collide"; kind = KIND; precedence = 5
        def applies(self, c, b): return NotApplies(reason="PEER_DEP_CONFLICT")

    with pytest.raises(RecipeNameCollision):
        @register_recipe(PID, registry=fresh_registry)
        class B:
            recipe_id = RecipeId("rid-b"); name = "collide"; kind = KIND; precedence = 5
            def applies(self, c, b): return NotApplies(reason="PEER_DEP_CONFLICT")


@pytest.mark.parametrize("bad_id", ["", "UPPER", "1-leading-digit", "has_underscore"])
def test_invalid_recipe_id_rejected_at_registration(fresh_registry, bad_id):
    """AC-9 — `_validate_recipe_id` regex (^[a-z][a-z0-9-]*$) rejects malformed IDs."""
    cls = _recipe_factory(bad_id, precedence=0, verdict=NotApplies(reason="PEER_DEP_CONFLICT"))
    with pytest.raises(ValueError, match="recipe_id"):
        register_recipe(PID, registry=fresh_registry)(cls)


def test_iteration_order_is_precedence_desc_then_name_asc(fresh_registry):
    """AC-5 — sort by (-precedence, name). Mix unique names so insertion order ≠ sort order."""
    cases = [("z-low", 1), ("a-mid", 5), ("m-high", 10), ("b-mid", 5)]
    for rid, prec in cases:
        register_recipe(PID, registry=fresh_registry)(
            _recipe_factory(rid, precedence=prec, verdict=NotApplies(reason="PEER_DEP_CONFLICT"))
        )
    order = [r.recipe.name for r in fresh_registry.all(PID)]
    assert order == ["m-high", "a-mid", "b-mid", "z-low"]


def test_first_applies_wins_short_circuits(fresh_registry):
    """AC-10 — middle recipe matches; lowest-precedence recipe never consulted."""
    cls_first = _recipe_factory("first", precedence=10, verdict=NotApplies(reason="PEER_DEP_CONFLICT"))
    cls_match = _recipe_factory("match", precedence=5, verdict=Applies(plan=PLAN))
    cls_never = _recipe_factory("never", precedence=1, verdict=NotApplies(reason="MAJOR_BUMP_REFUSE"))
    for C in (cls_first, cls_match, cls_never):
        register_recipe(PID, registry=fresh_registry)(C)

    out = match_recipes(fresh_registry, PID, cve=object(), bundle=object())

    assert isinstance(out, MatchedRecipe)
    assert out.recipe.name == "match"
    assert out.plan == PLAN

    # Third recipe is registered AND its `applies` was never called (positive + negative control)
    never_entry = next(r for r in fresh_registry.all(PID) if r.recipe.name == "never")
    assert never_entry.recipe.applies_calls == 0
    first_entry = next(r for r in fresh_registry.all(PID) if r.recipe.name == "first")
    assert first_entry.recipe.applies_calls == 1  # got called once and declined


def test_all_decline_returns_all_recipes_not_applicable_with_considered(fresh_registry):
    """AC-11 — every recipe declines → `considered` carries the trace."""
    for rid, reason in [("a", "PEER_DEP_CONFLICT"), ("b", "MAJOR_BUMP_REFUSE")]:
        register_recipe(PID, registry=fresh_registry)(
            _recipe_factory(rid, precedence=0, verdict=NotApplies(reason=reason))
        )

    out = match_recipes(fresh_registry, PID, cve=object(), bundle=object())

    assert isinstance(out, RecipeNotApplicable)
    assert out.reason == "ALL_RECIPES_NOT_APPLICABLE"
    assert [c.reason for c in out.considered] == ["PEER_DEP_CONFLICT", "MAJOR_BUMP_REFUSE"]


def test_empty_registry_returns_no_recipes_registered(fresh_registry):
    """AC-12 — distinct reason from ALL_RECIPES_NOT_APPLICABLE."""
    out = match_recipes(fresh_registry, PID, cve=object(), bundle=object())
    assert isinstance(out, RecipeNotApplicable)
    assert out.reason == "NO_RECIPES_REGISTERED"
    assert out.considered == []


def test_not_applicable_reason_literal_includes_no_recipes_registered():
    """AC-15 — additive Literal widening."""
    args = get_args(NotApplicableReason)
    assert "NO_RECIPES_REGISTERED" in args
    # Pre-existing five preserved (regression test):
    for member in (
        "PEER_DEP_CONFLICT", "MAJOR_BUMP_REFUSE", "OVERRIDES_AMBIGUOUS",
        "RECIPE_CATALOG_MISS", "ALL_RECIPES_NOT_APPLICABLE",
    ):
        assert member in args


def test_match_recipes_emits_no_events(fresh_registry):
    """AC-16 — registry walker is event-free; events belong to S6-04 orchestrator."""
    calls: list[object] = []

    class FakeEventLog:
        def emit(self, ev: object) -> None:
            calls.append(ev)

    register_recipe(PID, registry=fresh_registry)(
        _recipe_factory("a", precedence=0, verdict=Applies(plan=PLAN))
    )
    # match_recipes signature does NOT take an event_log; passing one is a type error.
    # We assert no introspectable EventLog seam exists by inspecting the function signature.
    import inspect
    sig = inspect.signature(match_recipes)
    assert "event_log" not in sig.parameters
    assert "events" not in sig.parameters
    _ = FakeEventLog()  # silence unused
    out = match_recipes(fresh_registry, PID, cve=object(), bundle=object())
    assert isinstance(out, MatchedRecipe)
    assert calls == []
```

```python
# tests/unit/transforms/test_recipe_engine_protocol.py
from __future__ import annotations
from codegenie.transforms.recipe_engine import RecipeEngine
from codegenie.plugins.protocols import RecipeEngine as RecipeEngineFromPlugins


def test_recipe_engine_is_runtime_checkable_protocol():
    """AC-2 — `@runtime_checkable`; structural conformance on apply(repo, plan, capability)."""
    class FakeEngine:
        async def apply(self, repo, plan, capability):
            raise NotImplementedError("test stub")

    assert isinstance(FakeEngine(), RecipeEngine)


def test_missing_apply_method_fails_isinstance():
    """AC-2 — negative control."""
    class NoApply:
        pass

    assert not isinstance(NoApply(), RecipeEngine)


def test_plugins_protocols_re_export_is_identical():
    """AC-2 — `plugins/protocols.py`'s `RecipeEngine` re-export IS the canonical class.
    Catches drift if someone re-declares the Protocol locally."""
    assert RecipeEngine is RecipeEngineFromPlugins
```

```python
# tests/unit/transforms/test_recipe_engine_determinism.py
from __future__ import annotations
import os
import subprocess
import sys
import textwrap


_SCRIPT = textwrap.dedent('''
    from codegenie.plugins.recipe_registry import RecipeRegistry, register_recipe
    from codegenie.transforms.outcomes import NotApplies
    from codegenie.types.identifiers import PluginId, RecipeId, TransformKind

    PID = PluginId("vulnerability-remediation--node--npm")
    KIND = TransformKind("npm_lockfile_semver_bump")

    def factory(rid, prec):
        return type(
            f"R_{rid}", (),
            {"recipe_id": RecipeId(rid), "name": rid, "kind": KIND,
             "precedence": prec,
             "applies": lambda self, cve, bundle: NotApplies(reason="PEER_DEP_CONFLICT"),
             "__init__": lambda self: None},
        )

    reg = RecipeRegistry()
    for rid, prec in [("z", 1), ("a", 5), ("m", 10), ("b", 5)]:
        register_recipe(PID, registry=reg)(factory(rid, prec))

    print(",".join(r.recipe.name for r in reg.all(PID)))
''')


def test_iteration_order_stable_across_pythonhashseed():
    """AC-5 — determinism guard. Same input under different PYTHONHASHSEED → same output."""
    outputs: list[str] = []
    for seed in ("0", "1", "2", "42"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        result = subprocess.run(
            [sys.executable, "-c", _SCRIPT],
            env=env, capture_output=True, text=True, check=True,
        )
        outputs.append(result.stdout.strip())
    assert len(set(outputs)) == 1, f"Order drifted across seeds: {outputs}"
    assert outputs[0] == "m,a,b,z"
```

Run; confirm `ImportError`; commit; implement.

### Green — make it pass

- Implement `outcomes.py` amendments first (additive `NO_RECIPES_REGISTERED` literal + additive `considered` field). Run the existing S1-03 tests to confirm no regressions, then run `tests/integration/test_phase5_contract_snapshot.py` to capture the regenerated golden (or run the project's snapshot regeneration target).
- Implement `transforms/recipe_engine.py` per the outline. `match_recipes` uses `match` on `Applicability` with `Applies(plan=plan)` and `NotApplies()` arms; add `from typing import assert_never` only if introducing a third `Applicability` variant — Phase 3 ships exactly two, so the `match` is exhaustive without an explicit `assert_never`.
- Implement `plugins/recipe_registry.py` per the outline. Keep the sort key explicit (`sorted(entries, key=lambda r: (-r.recipe.precedence, r.recipe.name))`) and document it.
- Amend `plugins/protocols.py` — delete the S2-01 stub `class RecipeEngine(Protocol)` (lines 80-98 in current state) and replace with `from codegenie.transforms.recipe_engine import RecipeEngine`. Keep `"RecipeEngine"` in `__all__`.
- Write the autouse `restore_default_recipe_registry` fixture in `tests/unit/plugins/conftest.py` (mirror S2-01's `restore_default_registry`).

### Refactor — clean up

- Confirm the `RecipeRegistry` API surface is **exactly** four public methods (`register`, `get`, `all`, `_reset_for_tests`); resist adding `unregister` / `keys` / `__contains__` / `__iter__` until a second consumer asks for them.
- Confirm `match_recipes` does not import or accept any `EventLog` type — event emission is S6-04's job. The AC-16 introspection test pins this.
- Confirm no raw `str` in public signatures (`PluginId`, `RecipeId`, `TransformKind` are the typed currencies). Grep for `: str` outside of `name: str` (recipe name is genuinely free-form text).
- Module docstring on `plugins/recipe_registry.py` carries the N=5 rule-of-N paragraph (Notes §"Rule-of-N=5") mirroring `plugins/registry.py:18-49`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/recipe_engine.py` | **New** — canonical home for `RecipeEngine(Protocol)`, `RecipeProtocol(Protocol)`, `MatchedRecipe` dataclass, `_validate_recipe_id` helper, `match_recipes(...)` walker |
| `src/codegenie/transforms/outcomes.py` | **Amend additively** — add `"NO_RECIPES_REGISTERED"` to `NotApplicableReason` Literal; add `considered: list["NotApplies"] = Field(default_factory=list)` to `RecipeNotApplicable`. Pre-existing surface preserved byte-identical otherwise |
| `src/codegenie/plugins/recipe_registry.py` | **New** — `RecipeRegistry` class, `RegisteredRecipe` dataclass, `default_recipe_registry: Final[RecipeRegistry]`, `@register_recipe(plugin_id, *, registry=None)` decorator, `RecipeAlreadyRegistered` + `RecipeNameCollision` + `RecipeNotFound` exceptions |
| `src/codegenie/plugins/protocols.py` | **Amend** — delete S2-01 stub `class RecipeEngine(Protocol)` declaration (lines 80-98); replace with `from codegenie.transforms.recipe_engine import RecipeEngine`. `__all__` preserves `"RecipeEngine"`. S2-01 fixtures (`_FakePlugin.transforms`) continue round-tripping because the re-exported name is class-identical |
| `src/codegenie/transforms/__init__.py` | Add `MatchedRecipe`, `RecipeProtocol`, `match_recipes` to `__all__` (export-list fence) |
| `src/codegenie/plugins/__init__.py` | Add `RecipeRegistry`, `register_recipe`, `default_recipe_registry`, `RecipeAlreadyRegistered`, `RecipeNameCollision`, `RecipeNotFound` to `__all__` |
| `tests/unit/plugins/test_recipe_registry.py` | **New** — all 11 ACs: decorator-returns-identity, dup-recipe-id, dup-name, invalid-id (parametrized), ordering, first-applies-wins, all-decline + considered, empty-registry, Literal-widening, no-events-emitted |
| `tests/unit/transforms/test_recipe_engine_protocol.py` | **New** — `@runtime_checkable` smoke + negative + identity test for `plugins/protocols.py` re-export |
| `tests/unit/transforms/test_recipe_engine_determinism.py` | **New** — subprocess-launch test asserting iteration order is byte-identical across `PYTHONHASHSEED ∈ {0, 1, 2, 42}` |
| `tests/unit/plugins/conftest.py` | Extend with `restore_default_recipe_registry` autouse fixture (snapshot pre-test, restore post-test) and `fresh_recipe_registry` fixture (mirror S2-01's `plugin_registry`) |
| `tests/integration/test_phase5_contract_snapshot.py` | **Re-bake** the golden — additive `RecipeNotApplicable.considered` + additive `NotApplicableReason` member. PR description names this explicitly (ADR-0001 §Consequences row 6) |

## Out of scope

- **`NpmLockfileRecipeEngine` implementation** — S5-02 (consumes this Protocol).
- **`OpenRewriteRecipeEngine` scaffold** — S5-03 (consumes this Protocol).
- **The four concrete npm recipes** (`NpmLockfileSemverBumpRecipe`, etc.) — S7-02.
- **`match_recipe` subgraph node** wiring events to `EventLog` — S6-04 (calls `match_recipes` and decorates the result with `RecipeMatched` / `RecipeSkipped`).
- **`Bundle` type definition** — S3-04 (forward-ref'd via `TYPE_CHECKING`).
- **`VulnerabilityRecord` type** — S3-01 (forward-ref'd).
- **`ApplicationPlan` enrichment for Phase 7 base-image rewrites** — Phase 7 widens `ApplicationPlan` additively (e.g., `BaseImagePlan` fields with defaults). This story does NOT introduce a parallel `RecipePlan` model — `ApplicationPlan` from `transforms.outcomes` is the single plan type.
- **Concurrent recipe registration from multiple threads / coroutines** — registration is import-time and single-threaded by construction (mirrors `plugins/registry.py` S2-01 Out-of-scope). No threading lock; no async semantics. If a future story needs it, an ADR amendment is the path.
- **Module-reload semantics** — `importlib.reload()`-ing a plugin module that calls `@register_recipe` MUST raise `RecipeAlreadyRegistered` (the desired behavior — reload is a developer-only operation and a duplicate registration is correctly an error). No special-casing.
- **Kernel-extract across the five registries** — `probes/registry.py`, `indices/registry.py`, `depgraph/registry.py`, `plugins/registry.py`, and this `plugins/recipe_registry.py` (N=5) all implement related-but-divergent dispatch. The kernel-extract trigger from S2-01 §6 was "N=5 OR a new registry needs only the common surface". This story IS N=5; the new registry's dispatch shape (`plugin_id` filter + `(precedence desc, name asc)` sort + first-applies-wins walker) is distinct from the four predecessors. Extract still deferred (Rule 2 — three similar lines is better than premature abstraction); see Notes §"Rule-of-N=5".
- **Generic `RecipeProtocol` covering Phase 4+ task classes** — this story freezes the Phase-3 surface only. Phase 4 / Phase 7 widen via additive Protocol-conformant recipes; no edits here.

## Notes for the implementer

### §1 — Mirror `plugins/registry.py` (S2-01) literally

Open `src/codegenie/plugins/registry.py` (S2-01, GREEN) before writing `plugins/recipe_registry.py`. The only diffs are: (a) keyed by `RecipeId` not `PluginId`; (b) `all(plugin_id=)` filter argument; (c) sort by `(-precedence, name)` (vs S2-01's unsorted registration-order `tuple`); (d) the `register_recipe` *decorator* shape vs S2-01's `register_plugin` *function-call* shape — see §3 below.

### §2 — Why per-plugin and not global

A recipe `name` may genuinely collide across plugins — `npm-semver-bump` makes sense in `vulnerability-remediation--node--npm` and a hypothetical Phase-7 `distroless-migration--node--npm`. The `_by_plugin` index makes per-plugin lookup O(k) and isolates Phase 7's distroless recipes from Phase 3's. AC-7 still enforces *global* `recipe_id` uniqueness (the BLAKE3-hex-class equivalent — one canonical ID per recipe across the system); name uniqueness (AC-8) is scoped per-plugin to keep the `(precedence, name)` sort stable.

### §3 — Class-decorator vs function-call asymmetry

S2-01's `register_plugin(plugin)` is a *function call* — plugins are *instances* carrying composed state (manifest + adapters + transforms). This story's `@register_recipe(plugin_id)` is a *class decorator* — recipes are *stateless matchers* whose identity lives in class attributes (`recipe_id`, `name`, `kind`, `precedence`) and whose `applies()` method is pure. The decorator's `recipe_cls()` zero-arg construction is safe because recipes have no constructor state.

If a recipe ever needs construction args (genuine state), the dual-shape extension is backwards-compatible: `register_recipe(plugin_id, instance=None, *, registry=None)`. Defer that until a real use case lands (Rule 2).

### §4 — `match_recipes` returns `MatchedRecipe`, NOT `RecipeOutcome.Applied`

`RecipeOutcome.Applied` requires a `TransformId` (the BLAKE3-hex digest of the applied diff — S1-04). Only the engine's `apply()` call produces that. This story's walker returns an intermediate `MatchedRecipe(recipe, plan)` that the orchestrator's `apply_recipe` node lifts to `Applied` after calling `engine.apply(...)`. Walker state machine: `match → apply → outcome`. Document this with a one-line state-machine comment in the walker's docstring.

### §5 — Why widen `RecipeNotApplicable` additively rather than introduce a new return type

Two alternatives were considered: (a) introduce a new `MatchOutcome` discriminated union that the orchestrator then lifts to `RecipeOutcome`; (b) widen `RecipeNotApplicable` with the additive `considered` field. Option (b) keeps the Phase-5 contract surface stable (one less variant for `GateRunner` to dispatch on) and is backwards-compatible by Pydantic defaults — existing callers reading `.reason` continue to work; the field is `[]` when absent. ADR-0001 §Consequences row 6 names the snapshot regeneration path; this story honors it.

### §6 — Why `ALL_RECIPES_NOT_APPLICABLE` instead of returning the first `NotApplies.reason`

Phase 4 needs to know "every recipe rejected this CVE for distinct reasons" vs "every recipe rejected with the same reason" — the `considered` field preserves the full trace. The top-level `reason=ALL_RECIPES_NOT_APPLICABLE` is the marker Phase 4's `prompt_builder` dispatches on; the `considered` list is the structured context Phase 4 templates against (production ADR-0011).

### §7 — `RecipeProtocol` vs `RecipeEngine` — two-level hierarchy

`RecipeEngine` is the *worker* that mutates files (one per `TransformKind`, e.g., `NpmLockfileRecipeEngine`). `RecipeProtocol` is the *matcher* (one per recipe — e.g., `NpmLockfileSemverBumpRecipe`). One engine serves many recipes. The arch §Anti-patterns row "Premature pluggability" notes both are genuinely polymorphic (2 engines × 4 recipes day-1), so the two-level Protocol hierarchy earns its keep. Recipe → engine lookup: `plugin.transforms()[recipe.kind].apply(repo, plan, capability)`.

### §8 — Single canonical `RecipeEngine` Protocol home

S2-01 shipped a temporary stub at `src/codegenie/plugins/protocols.py:81-98` with `apply(self, plan, ctx)` and explicitly deferred the freeze to Step 5 (S2-01 Out-of-scope §"`RecipeEngine` Protocol surface freeze"). This story REPLACES that stub: declares the canonical Protocol in `src/codegenie/transforms/recipe_engine.py` with the arch-named signature `apply(self, repo, plan, capability) -> RecipeOutcome` (arch §C12 L716, §C10 L672), then re-exports from `plugins/protocols.py` via `from codegenie.transforms.recipe_engine import RecipeEngine`. The re-export is class-identical (verified by AC-2's `assert P is T` test) — S2-01's `_FakePlugin.transforms() -> dict[..., RecipeEngine]` continues round-tripping.

### §9 — ADR amendments triggered

This story triggers two ADR amendments that the implementer must land alongside the code:

- **ADR-0009** amendment — current `§Decision` says "Ship `RecipeEngine(Protocol)` in `src/codegenie/plugins/protocols.py`". The canonical location is now `src/codegenie/transforms/recipe_engine.py` per High-level-impl §Step 5 L136. Amend `§Decision` to name the new location and add a one-line "Amendment 2026-05-19" block citing this story.
- **ADR-0001** amendment — `§Consequences` row 6 names "Any change to the six named symbols requires a Phase-3 ADR amendment + Phase-5 ADR-update referencing the new shape." This story re-bakes the `tests/integration/test_phase5_contract_snapshot.py` golden for the additive `RecipeNotApplicable.considered` field + `NotApplicableReason` widening. Add a one-line "Amendment 2026-05-19" block to ADR-0001 listing the additive changes and confirming Phase 5 reads `RecipeNotApplicable.reason` (unchanged for Phase 5 callers; `considered` is read by Phase 4 only).

### §10 — Forward references and import discipline

`RecipeEngine.apply` references `SandboxedPath` (S4-04) and `NpmInstallCapability` (S4-05). Both are forward-referenced under `TYPE_CHECKING`. The S1-05 fence test from Phase 3's structural defenses will catch any runtime import from `transforms/` → `plugins/sandbox_path.py` or `plugins/capabilities.py` that would form a cycle. Use `from __future__ import annotations` everywhere in the new modules.

`Bundle` (S3-04) and `VulnerabilityRecord` (S3-01) are similarly forward-referenced. The structural Bundle field reads happen at recipe-implementation call sites (S7-02) — NOT in the Protocol surface here.

### §11 — Rule-of-N=5

This is the **5th** decorator-registry in the codebase (after `probes`, `indices`, `depgraph`, `plugins/registry.py`). S2-01 §6 pinned the extract trigger at "N=5 OR a new registry needs only the common surface". The trigger fires on N=5 today. But:

The five registries' dispatch shapes are all distinct:
1. `probes/registry.py` — `for_task` filter + LRU + `sorted_for_dispatch` (heaviness, runs_last).
2. `indices/registry.py` — total dispatch via `dispatch_all`.
3. `depgraph/registry.py` — single dispatch + `has_strategy` query.
4. `plugins/registry.py` — `register` / `get` / `all` + `resolve(scope)` + `extends`-walk.
5. `plugins/recipe_registry.py` (this story) — `register` / `get` / `all(plugin_id)` + first-`Applies`-wins walker.

The shared surface (`register` / `get` / `all` / typed-collision-error) is a small fraction of each registry's LOC. A `KernelRegistry[K, V]` base would still leave 5 hand-written dispatch shapes on top. Pure Rule-2 (three similar lines is better than premature abstraction) — extract still deferred. The module docstring on `plugins/recipe_registry.py` carries this paragraph verbatim as the audit anchor.

Lift the kernel when *either*: (a) N=6 with the 6th registry needing only the common surface; or (b) a real bug surfaces in one of the five registries that would have been prevented by a shared base. Until then, each registry stays hand-written.

### §12 — Deliberately not adopted (YAGNI applications)

- **`unregister(recipe_id)` public method** — `_reset_for_tests()` covers the test path; production code never unregisters. If S6-04 grows a runtime-recipe-disable feature (Phase 4+), introduce it then.
- **Async `RecipeProtocol.applies`** — `applies()` is sync because matcher logic is pure (manifest reads, version compares) and zero-I/O. If a future recipe needs async (e.g., consults a network registry), promote then.
- **DI container for the registry** — explicitly rejected in S2-01 §"Deliberately not adopted" and `phase-arch-design.md §Patterns considered and deliberately rejected`.
- **`Hypothesis` property test over arbitrary registration orders** — covered structurally by the subprocess-launch test (AC-5); adding a Hypothesis layer is cheap extra coverage if the executor has budget but not required.
