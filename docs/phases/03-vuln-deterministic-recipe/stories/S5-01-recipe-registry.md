# Story S5-01 — `RecipeEngine` Protocol + per-plugin `RecipeRegistry` + `@register_recipe` decorator (Gap 3 fix)

**Step:** Step 5 — Transform ABC consumers, RecipeEngine Protocol, RecipeRegistry, lockfile policy
**Status:** Ready
**Effort:** M
**Depends on:** S1-04, S2-01, S4-02
**ADRs honored:** ADR-0009, ADR-0010, ADR-0002, ADR-0001

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

Ship `src/codegenie/plugins/recipe_registry.py` exposing `RecipeRegistry` + `@register_recipe(plugin_id, *, registry=None)` and `src/codegenie/transforms/recipe_engine.py` exposing the `RecipeEngine(Protocol)` plus a `match_recipes(registry, cve, bundle) -> RecipeOutcome.Applied | RecipeOutcome.NotApplicable` walker that implements the first-`Applies(plan)`-wins iteration and the `ALL_RECIPES_NOT_APPLICABLE` short-circuit.

## Acceptance criteria

- [ ] `from codegenie.transforms.recipe_engine import RecipeEngine, match_recipes` and `from codegenie.plugins.recipe_registry import RecipeRegistry, register_recipe, default_recipe_registry` all succeed.
- [ ] `RecipeEngine` is a `@runtime_checkable Protocol` with exactly one abstract async method `apply(self, repo: SandboxedPath, plan: RecipePlan, capability: NpmInstallCapability) -> RecipeOutcome`; structurally satisfied by S5-02 / S5-03's concrete engines.
- [ ] `RecipeRegistry` is a class (not a module-level dict) — its instance attribute `_recipes: dict[RecipeId, RegisteredRecipe]` is private; the public surface is `register(...)`, `get(recipe_id)`, `all(plugin_id=None)`, `clear()` (test-only).
- [ ] `RecipeRegistry.all(plugin_id=...)` returns recipes for that plugin **sorted by `(precedence desc, name asc)`**; ties on precedence break on name ascending; the order is deterministic across CPython hash-randomization seeds (Hypothesis-tested with `PYTHONHASHSEED` permutation).
- [ ] `register_recipe(plugin_id: PluginId, *, registry: RecipeRegistry | None = None)` is a decorator factory: `@register_recipe(plugin_id, registry=fresh)` returns the recipe class unchanged after registering it on `registry` (or `default_recipe_registry` if omitted) — mirrors `register_plugin` from S2-01.
- [ ] `register_recipe` rejects duplicate `(plugin_id, recipe_id)` pairs with `RecipeAlreadyRegistered(plugin_id, recipe_id)` (exit 4 family per `../phase-arch-design.md §Failure behavior`).
- [ ] `register_recipe` rejects a `RecipeProtocol` instance whose `recipe_id` does not pass `RecipeId.parse(...)` (newtype smart-constructor — ADR-0010); raises `ValueError` at registration time, not at first match.
- [ ] `match_recipes(registry, plugin_id, cve, bundle) -> RecipeOutcome` iterates `registry.all(plugin_id)`; calls each `recipe.applies(cve, bundle)`; on first `Applies(plan)` returns `RecipeOutcome.Applied`-precursor (`MatchedRecipe(recipe, plan)`) and stops — **no further `applies()` calls happen** (verified by call-counting spy).
- [ ] When every recipe returns `NotApplies(reason)`, `match_recipes` returns `RecipeOutcome.NotApplicable(reason=ALL_RECIPES_NOT_APPLICABLE)` carrying the per-recipe reasons in a `considered: list[NotApplies]` field so Phase 4 can read the structured rejection trace.
- [ ] Empty registry (no recipes registered for `plugin_id`) → `RecipeOutcome.NotApplicable(reason=NO_RECIPES_REGISTERED)` (distinct reason from `ALL_RECIPES_NOT_APPLICABLE`; tested explicitly).
- [ ] Per-test isolation: `tests/unit/plugins/test_recipe_registry.py` constructs a fresh `RecipeRegistry()` per test; no test mutates `default_recipe_registry` (enforced by an autouse fixture that asserts `len(default_recipe_registry._recipes) == 0` post-test).
- [ ] `mypy --strict src/codegenie/plugins/recipe_registry.py src/codegenie/transforms/recipe_engine.py` clean; no `dict[str, Any]`, no `cast`, no `# type: ignore` without a justification comment referencing this story.
- [ ] `ruff check`, `ruff format --check`, `pytest tests/unit/plugins/test_recipe_registry.py tests/unit/transforms/test_recipe_engine_protocol.py` all green.
- [ ] Branch coverage on `recipe_registry.py` ≥ 95%; on `recipe_engine.py` ≥ 95%.
- [ ] TDD plan's red tests exist, are committed, and are green.

## Implementation outline

1. `src/codegenie/transforms/recipe_engine.py`:
   - Define `RecipeEngine(Protocol)` with `@runtime_checkable` and the single async method `apply(self, repo, plan, capability) -> RecipeOutcome`.
   - Define `RecipePlan` Pydantic model (`extra="forbid"`, `frozen=True`) carrying the plan payload (`package: PackageId`, `from_version: SemverVersion`, `to_version: SemverVersion`, `kind: TransformKind`). Phase 7 widens `RecipePlan` additively (e.g., `BaseImagePlan`).
   - Define `RecipeProtocol(Protocol)` with `recipe_id: RecipeId`, `name: str`, `precedence: int = 0`, and `applies(self, cve: VulnerabilityRecord, bundle: Bundle) -> Applicability`.
   - Define `match_recipes(registry, plugin_id, cve, bundle) -> RecipeOutcome` per the algorithm above.
   - Add `NotApplicableReason` literals: `ALL_RECIPES_NOT_APPLICABLE`, `NO_RECIPES_REGISTERED`, plus the existing Phase-3 reasons (`PEER_DEP_CONFLICT`, `MAJOR_BUMP_REFUSE`, `OVERRIDES_AMBIGUOUS`, `RECIPE_CATALOG_MISS`) per `../phase-arch-design.md §Phase 4 / RAG / LLM trigger contract`.
2. `src/codegenie/plugins/recipe_registry.py`:
   - Import `RecipeProtocol` from `transforms.recipe_engine`. Define `@dataclass(frozen=True, slots=True) RegisteredRecipe(plugin_id: PluginId, recipe: RecipeProtocol)`.
   - Implement `RecipeRegistry` class with `_recipes` dict keyed on `RecipeId`, plus a parallel `_by_plugin: dict[PluginId, list[RecipeId]]` for `all(plugin_id=)` lookups.
   - `register(self, plugin_id, recipe)` — dup-check, smart-constructor validation, append.
   - `all(self, plugin_id=None)` — when `plugin_id` is None, return all sorted; otherwise filter then sort by `(precedence desc, name asc)`. Use `sorted(key=lambda r: (-r.recipe.precedence, r.recipe.name))`.
   - `clear(self)` — test-only; documented in the docstring as such.
   - Module-level `default_recipe_registry: RecipeRegistry = RecipeRegistry()`.
   - `register_recipe(plugin_id, *, registry=None)` factory returns `_decorator(recipe_cls)` that instantiates the recipe (via `recipe_cls()`), calls `(registry or default_recipe_registry).register(plugin_id, instance)`, and returns `recipe_cls` unchanged (mirrors `register_plugin` from S2-01).
3. Re-exports:
   - `src/codegenie/transforms/__init__.py` — add `RecipeEngine`, `RecipePlan`, `RecipeProtocol`, `match_recipes` to `__all__` (the export-list fence test from ADR-0001 will require this).
   - `src/codegenie/plugins/__init__.py` — add `RecipeRegistry`, `register_recipe`, `default_recipe_registry`.
4. Tests in `tests/unit/plugins/test_recipe_registry.py` and `tests/unit/transforms/test_recipe_engine_protocol.py` (TDD plan below).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths: `tests/unit/plugins/test_recipe_registry.py`, `tests/unit/transforms/test_recipe_engine_protocol.py`.

```python
# tests/unit/plugins/test_recipe_registry.py
import pytest
from codegenie.plugins.recipe_registry import (
    RecipeRegistry, register_recipe, default_recipe_registry,
    RecipeAlreadyRegistered,
)
from codegenie.transforms.recipe_engine import (
    RecipeProtocol, match_recipes, RecipeOutcome,
)
from codegenie.transforms.applicability import Applies, NotApplies
from codegenie.types.identifiers import PluginId, RecipeId

PID = PluginId("vulnerability-remediation--node--npm")

def _recipe(rid: str, *, precedence: int, verdict):
    class R:
        recipe_id = RecipeId(rid)
        name = rid
        def __init__(self) -> None:
            self.applies_calls = 0
        def applies(self, cve, bundle):
            self.applies_calls += 1
            return verdict
    R.precedence = precedence  # class attr per RecipeProtocol
    return R

@pytest.fixture
def fresh_registry():
    return RecipeRegistry()

def test_register_decorator_returns_class_unchanged(fresh_registry):
    @register_recipe(PID, registry=fresh_registry)
    class Semver:
        recipe_id = RecipeId("npm-semver-bump")
        name = "npm-semver-bump"
        precedence = 10
        def applies(self, cve, bundle): return NotApplies(reason="PEER_DEP_CONFLICT")
    assert Semver.recipe_id == "npm-semver-bump"  # not wrapped
    assert len(fresh_registry.all(PID)) == 1

def test_duplicate_recipe_id_rejected(fresh_registry):
    @register_recipe(PID, registry=fresh_registry)
    class A:
        recipe_id = RecipeId("dup"); name = "dup"; precedence = 0
        def applies(self, c, b): return NotApplies(reason="x")
    with pytest.raises(RecipeAlreadyRegistered):
        @register_recipe(PID, registry=fresh_registry)
        class B:
            recipe_id = RecipeId("dup"); name = "dup"; precedence = 0
            def applies(self, c, b): return NotApplies(reason="x")

def test_iteration_order_is_precedence_desc_then_name_asc(fresh_registry):
    for rid, prec in [("z-low", 1), ("a-mid", 5), ("m-high", 10), ("b-mid", 5)]:
        register_recipe(PID, registry=fresh_registry)(_recipe(rid, precedence=prec, verdict=NotApplies(reason="x")))
    order = [r.recipe.name for r in fresh_registry.all(PID)]
    assert order == ["m-high", "a-mid", "b-mid", "z-low"]

def test_first_applies_wins_short_circuits(fresh_registry):
    plan_obj = object()
    cls_first = _recipe("first", precedence=10, verdict=NotApplies(reason="r1"))
    cls_match = _recipe("match", precedence=5, verdict=Applies(plan=plan_obj))
    cls_never = _recipe("never", precedence=1, verdict=NotApplies(reason="should-not-see"))
    for C in (cls_first, cls_match, cls_never):
        register_recipe(PID, registry=fresh_registry)(C)
    out = match_recipes(fresh_registry, PID, cve=object(), bundle=object())
    assert out.matched.recipe.name == "match"
    # third recipe must NOT have been consulted
    third_instance = next(r.recipe for r in fresh_registry.all(PID) if r.recipe.name == "never")
    assert third_instance.applies_calls == 0

def test_all_not_applies_short_circuits_with_all_recipes_not_applicable(fresh_registry):
    for rid in ("a", "b"):
        register_recipe(PID, registry=fresh_registry)(_recipe(rid, precedence=0, verdict=NotApplies(reason=f"r-{rid}")))
    out = match_recipes(fresh_registry, PID, cve=object(), bundle=object())
    assert isinstance(out, RecipeOutcome) and out.kind == "not_applicable"
    assert out.reason == "ALL_RECIPES_NOT_APPLICABLE"
    assert [c.reason for c in out.considered] == ["r-a", "r-b"]

def test_empty_registry_returns_no_recipes_registered(fresh_registry):
    out = match_recipes(fresh_registry, PID, cve=object(), bundle=object())
    assert out.kind == "not_applicable" and out.reason == "NO_RECIPES_REGISTERED"

def test_default_registry_untouched_by_tests(fresh_registry):
    # autouse fixture in conftest asserts; here we just check the shape
    assert len(default_recipe_registry.all()) == 0
```

```python
# tests/unit/transforms/test_recipe_engine_protocol.py
from typing import runtime_checkable
import pytest
from codegenie.transforms.recipe_engine import RecipeEngine, RecipeOutcome

def test_recipe_engine_is_runtime_checkable_protocol():
    # structural conformance — anything with async apply(repo, plan, capability) qualifies
    class FakeEngine:
        async def apply(self, repo, plan, capability):
            return RecipeOutcome(kind="not_applicable", reason="x")
    assert isinstance(FakeEngine(), RecipeEngine)

def test_missing_apply_method_fails_isinstance():
    class NoApply: pass
    assert not isinstance(NoApply(), RecipeEngine)
```

Run; confirm `ImportError`; commit; implement.

### Green — make it pass

- Implement `RecipeRegistry` minimally per the outline; keep the sort key explicit (`(-r.recipe.precedence, r.recipe.name)`) and document it in the docstring.
- `match_recipes` is a small loop with one `match` on `Applicability`; use `assert_never` on a synthetic exhaustiveness check (`from typing import assert_never` at the loop's else branch — Pyright/mypy enforce). Collect `NotApplies` into `considered` even though only `ALL_RECIPES_NOT_APPLICABLE` exposes them today (Phase 4 will read them).
- `RegisteredRecipe` is a frozen dataclass so registry entries are hashable / immutable.
- For `default_recipe_registry`, write the autouse fixture in `tests/unit/plugins/conftest.py` (or extend the existing one from S2-01) that calls `default_recipe_registry.clear()` between tests and asserts empty post-test.

### Refactor — clean up

- Confirm the `RecipeRegistry` API surface is **exactly** the four methods listed; resist adding `unregister` / `keys` / `__contains__` / `__iter__` until a second consumer asks for them (YAGNI; mirrors S2-01's restraint).
- Confirm `match_recipes` does not emit any events here — event emission is S6-01's job (`RecipeMatched` / `RecipeSkipped` / `RecipeFailed` land on the EventLog at the orchestrator's `match_recipe` node, not in the registry walk itself). Document this in the function's docstring so the reader knows where to look.
- Re-read ADR-0010: every domain identifier (`PluginId`, `RecipeId`) must come from `codegenie.types.identifiers`; no raw `str` in the public signatures. Grep the file for `: str` and replace with newtypes.
- Add a `mypy --strict` smoke import test at module top to guarantee no forward-ref breaks: `if TYPE_CHECKING: from codegenie.plugins.bundle import Bundle` — Bundle is S3-04's deliverable; `RecipeProtocol.applies(cve, bundle)` uses a `TYPE_CHECKING`-guarded forward ref to avoid a cycle.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/recipe_engine.py` | New — `RecipeEngine` Protocol, `RecipeProtocol` Protocol, `RecipePlan`, `match_recipes` walker, `NotApplicableReason` literals |
| `src/codegenie/plugins/recipe_registry.py` | New — `RecipeRegistry` class + `@register_recipe` decorator + `default_recipe_registry` |
| `src/codegenie/transforms/__init__.py` | Add `RecipeEngine`, `RecipeProtocol`, `RecipePlan`, `match_recipes` to `__all__` (ADR-0001 export-list fence) |
| `src/codegenie/plugins/__init__.py` | Add `RecipeRegistry`, `register_recipe`, `default_recipe_registry`, `RecipeAlreadyRegistered` |
| `tests/unit/plugins/test_recipe_registry.py` | New — duplicate, ordering, first-`Applies`-wins, all-`NotApplies` short-circuit, empty-registry distinct reason, isolation |
| `tests/unit/transforms/test_recipe_engine_protocol.py` | New — Protocol structural conformance + missing-method negative |
| `tests/unit/plugins/conftest.py` | Extend autouse `default_*_registry` reset fixture to include `default_recipe_registry` |

## Out of scope

- **`NpmLockfileRecipeEngine` implementation** — S5-02 (consumes this Protocol).
- **`OpenRewriteRecipeEngine` scaffold** — S5-03 (consumes this Protocol).
- **The four concrete npm recipes** (`NpmLockfileSemverBumpRecipe`, etc.) — S7-02.
- **`match_recipe` subgraph node** wiring events to `EventLog` — S6-04 (calls `match_recipes` and decorates the result with `RecipeMatched` / `RecipeSkipped`).
- **`Bundle` type definition** — S3-04 (forward-ref'd via `TYPE_CHECKING`).
- **`VulnerabilityRecord` type** — S3-01 (forward-ref'd).
- **`RecipePlan` enrichment for Phase 7 base-image rewrites** — Phase 7 widens additively.

## Notes for the implementer

- **Mirror S2-01 literally.** Open `src/codegenie/plugins/registry.py` (S2-01) and read it before writing this file; the only diffs are: (a) keyed by `RecipeId` not `PluginId`; (b) `all(plugin_id=)` filter argument; (c) sort by `(precedence desc, name asc)` not `(specificity desc, precedence desc, name asc)` (no `PluginScope` here). The decorator factory shape (`(plugin_id, *, registry=None) -> _decorator -> cls`) is byte-identical in spirit.
- **Why per-plugin and not global?** A `RecipeId` may genuinely collide across plugins (`npm-semver-bump` makes sense in `vulnerability-remediation--node--npm` and again in `distroless-migration--node--npm` if Phase 7 ever ships one). Scoping by `plugin_id` makes collisions impossible-by-construction; the `_by_plugin` parallel dict makes the filter O(k) where k = recipes for that plugin.
- **`match_recipes` does NOT emit `RecipeOutcome.Applied`.** Returning `Applied` requires the `Transform` payload, which only the `RecipeEngine.apply` call produces. This story's walker returns an intermediate `MatchedRecipe(recipe, plan)` wrapper or a `RecipeOutcome.NotApplicable` — the orchestrator's `apply_recipe` node calls `engine.apply(...)` and lifts to `RecipeOutcome.Applied`. Document this in the walker's docstring with a one-line state-machine diagram (`match → apply → outcome`).
- **Why `ALL_RECIPES_NOT_APPLICABLE` instead of returning the first `NotApplies.reason`?** Phase 4 needs to know "every recipe rejected this CVE for distinct reasons" vs. "every recipe rejected with the same reason" — the `considered: list[NotApplies]` field preserves the full trace. The top-level `reason=ALL_RECIPES_NOT_APPLICABLE` is the marker that Phase 4's `prompt_builder` dispatches on; the `considered` list is the structured context Phase 4 templates against.
- **Hypothesis test for ordering determinism**: parametrize over `PYTHONHASHSEED ∈ [0, 1, 2, 42]` (set in subprocess via `subprocess.run([sys.executable, "-c", "..."], env={"PYTHONHASHSEED": ...})`) — the sorted output must be byte-identical across seeds. This catches accidental reliance on dict-insertion-order at the registry level.
- **`RecipeProtocol` vs. `RecipeEngine` — keep them separate.** `RecipeEngine` is the *worker* that mutates files (one per `TransformKind`, e.g., `NpmLockfileRecipeEngine`). `RecipeProtocol` is the *matcher* (one per recipe, e.g., `NpmLockfileSemverBumpRecipe`). One engine serves many recipes. The arch design's §Anti-patterns row "Premature pluggability" notes both are genuinely polymorphic — 2 engines and 4 recipes day-1 — so the two-level Protocol hierarchy earns its keep.
- **Do not import `Bundle` or `VulnerabilityRecord` at module top.** Use `TYPE_CHECKING` guards. The fence test from S1-05 will catch any runtime imports from `transforms/` → `plugins/bundle.py` that would create a cycle.
