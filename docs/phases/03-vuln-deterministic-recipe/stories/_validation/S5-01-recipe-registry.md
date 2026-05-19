# Validation report — S5-01 — `RecipeEngine` Protocol + per-plugin `RecipeRegistry` + `@register_recipe`

**Validated:** 2026-05-19
**Validator:** phase-story-validator skill (autonomous run via story-validation-corrector scheduled task)
**Verdict:** **HARDENED**
**Story file:** `docs/phases/03-vuln-deterministic-recipe/stories/S5-01-recipe-registry.md`

---

## Context brief

S5-01 closes Phase-3 arch **Gap 3** (`phase-arch-design.md §Gap 3`): the per-plugin recipe-registration mechanism. It is the *first* registry to land alongside the existing `PluginRegistry` (S2-01, GREEN) and the existing `S1-03`-shipped outcomes union (`Applicability`, `RecipeOutcome`, `ApplicationPlan`, `NotApplicableReason` — all canonical in `codegenie.transforms.outcomes`). The story also fixes the `RecipeEngine` Protocol signature: S2-01 shipped a stub at `src/codegenie/plugins/protocols.py:81-98` with `apply(self, plan, ctx)` and intentionally **deferred the freeze to Step 5** (S2-01 Out-of-scope §"`RecipeEngine` Protocol surface freeze"). Step 5 owns that freeze. The arch (line 146 + §C12 + §C10 line 672) names the canonical signature `apply(repo, plan, capability) -> RecipeOutcome` — 3 args, the third a `NpmInstallCapability`.

**Load-bearing context the validator pulled in:**

- `phase-arch-design.md §Gap 3` (L1164-L1168) — the Improvement paragraph this story implements verbatim.
- `phase-arch-design.md §C12` (L714-L717) — two day-1 engine implementations.
- `phase-arch-design.md §C10` (L650-L692) — `NpmInstallCapability` model + `CapabilityBundle` + `mint()` chokepoint (S4-05 ships).
- `phase-arch-design.md §Anti-patterns` row "Premature pluggability" — Protocol earns rent (2 engines + 4 recipes day-1).
- `phase-arch-design.md §Phase 4 / RAG / LLM trigger contract` (L1077) — `NotApplicableReason` taxonomy is Phase 3's contract; Phase 4 widens additively.
- `phase-arch-design.md §Gap 5` and arch C9 — `RecipeMatched`/`RecipeSkipped`/`RecipeFailed` are S6-01 events (NOT this story).
- ADR-0009 — RecipeEngine Protocol with two day-1 implementations; canonical `apply(repo, plan, capability)` signature.
- ADR-0010 — `Applicability = Applies(plan) | NotApplies(reason)` (already shipped in S1-03 `outcomes.py`); newtype every domain identifier; **no smart-constructor exists on `NewType`** — `RecipeId` is a pure `NewType("RecipeId", str)` per `src/codegenie/types/identifiers.py:66`. There is no `RecipeId.parse(...)`.
- ADR-0002 — instance + `default_registry` + decorator-or-function-call helper; the shape this story mirrors.
- ADR-0001 — `RecipeEngine` is one of the six Phase-5-contracted names; `tests/integration/test_phase5_contract_snapshot.py` will fail if the surface drifts.
- ADR-0010 Amendment 2026-05-18 — `Applicability` and `RecipeOutcome` are **already** Pydantic discriminated unions at `codegenie.transforms.outcomes`; `RecipeOutcome` is an `Annotated[A|B|C|D, Field(discriminator="kind")]` alias (NOT a class — `isinstance(out, RecipeOutcome)` is a runtime error). `NotApplicableReason` is a closed `Literal` of 5 members; `NO_RECIPES_REGISTERED` is NOT yet a member.

**As-built state the story doesn't address:**

- `src/codegenie/plugins/protocols.py:81-98` already declares a `RecipeEngine` Protocol with `apply(self, plan, ctx)` (2 args). S5-01 must replace this signature in-place (per S2-01 Out-of-scope §"freeze deferred to Step 5") and the `make_fake_plugin` fixture's `_FakePlugin.transforms() -> dict[..., RecipeEngine]` consumer must keep round-tripping.
- `src/codegenie/transforms/outcomes.py` already defines `ApplicationPlan`, `Applies`, `NotApplies`, `Applicability`, `RecipeOutcome`, `RecipeNotApplicable`, `NotApplicableReason`. Story's separate `RecipePlan` Pydantic model and "Add `NotApplicableReason` literals" instructions duplicate these. The S1-03 contract snapshot is frozen — every variant rename or addition is a Phase-3 ADR amendment.
- `NpmInstallCapability` is *not yet shipped*: S4-05 is `HARDENED` but not `GREEN`. The story does not list S4-05 in `Depends on:`.
- `tests/fence/` exists (S2-01 populated it). The story's mypy-strict claim is fine but the contract snapshot test `tests/integration/test_phase5_contract_snapshot.py` (ADR-0001 §Consequences) must keep passing — adding `considered: list[NotApplies]` to `RecipeNotApplicable` would re-baseline that snapshot. The story does not acknowledge this.

**Original story strengths:**

- Correctly cites Gap 3, ADR-0009, ADR-0002, ADR-0010, ADR-0001 across References.
- Mirrors `PluginRegistry` (S2-01) shape with intent — `default_recipe_registry`, autouse-fixture isolation, dual-shape decorator.
- Out-of-scopes the four concrete npm recipes (S7-02), the two engine implementations (S5-02 / S5-03), and the orchestrator wiring (S6-04) cleanly.
- TDD plan includes the load-bearing "first-`Applies`-wins short-circuits" test with a call-counting spy.
- Distinguishes `ALL_RECIPES_NOT_APPLICABLE` from `NO_RECIPES_REGISTERED` as a Phase-4 dispatch concern (this is good design — but the Literal isn't widened).
- Names the `RecipeProtocol` vs `RecipeEngine` split correctly (matcher vs worker; 4 recipes × 2 engines).

**Original story weaknesses (resolved here):**

The story has substantial contract drift against as-built code. **Multiple BLOCK findings** before this validation pass — without these fixes the story is literally unimplementable (imports fail, Pydantic constructors reject, classes don't exist).

---

## Stage 2 — Four critic reports

### Coverage critic — 8 findings

| ID  | Severity | Title                                                                          | Resolution                                                                                                                                       |
| --- | -------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| F1  | block    | `from codegenie.transforms.applicability import` wrong path; real path is `transforms.outcomes` | Applied — AC-1 imports rewritten to `codegenie.transforms.outcomes`. Story's TDD code corrected.                                                |
| F2  | block    | `RecipeOutcome.NotApplicable` is pseudo-OO; actual class is `RecipeNotApplicable` from `outcomes.py` | Applied — ACs use `RecipeNotApplicable` explicitly; `RecipeOutcome` is documented as the `Annotated` umbrella alias (not a class).                |
| F3  | block    | `match_recipes` return type self-contradicts (Goal says 3-arg + 2-variant return; AC-7 says 4-arg + intermediate `MatchedRecipe`) | Applied — Goal rewritten to 4-arg `match_recipes(registry, plugin_id, cve, bundle)`; return type pinned as `MatchedRecipe \| RecipeNotApplicable` (no premature `RecipeOutcome.Applied` — engine produces that). |
| F4  | harden   | `MatchedRecipe(recipe, plan)` wrapper not pinned (mentioned only in Notes)     | Applied — new AC pins `MatchedRecipe` as a frozen dataclass with typed `recipe: RecipeProtocol`, `plan: ApplicationPlan` fields.                  |
| F5  | harden   | `RecipeProtocol` missing `kind: TransformKind` — orchestrator can't map recipe → engine without it | Applied — AC for `RecipeProtocol` now requires `kind: TransformKind` class attribute; ties to `plugin.transforms()[recipe.kind]` lookup.        |
| F6  | harden   | Tie-breaker undefined when two recipes share `(precedence, name)`              | Applied — AC mandates `name` uniqueness within a `plugin_id` (enforced at registration via `_by_plugin_names` set); tie-on-(precedence,name) is type-impossible. |
| F7  | nit      | Out-of-scope omits concurrent registration / module-reload semantics           | Applied — Out-of-scope expanded mirroring S2-01.                                                                                                  |
| F8  | nit      | `Bundle` / `VulnerabilityRecord` forward refs not paired with `from __future__ import annotations` requirement | Applied — Implementation outline pins `from __future__ import annotations` + `TYPE_CHECKING` blocks; cycle defence cited.                          |

### Test-Quality critic — 8 findings

| ID  | Severity | Title                                                                                | Resolution                                                                                                                                                  |
| --- | -------- | ------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F1  | block    | `Applies(plan=plan_obj)` with `plan_obj = object()` — Pydantic rejects (requires `ApplicationPlan`) | Applied — all TDD test bodies rewritten to use `Applies(plan=ApplicationPlan(summary="..."))`.                                                                |
| F2  | block    | `RecipeOutcome(kind=..., reason=...)` — `RecipeOutcome` is a `TypeAlias`, not a class | Applied — TDD test rewritten to construct `RecipeNotApplicable(reason=...)` directly; `assert isinstance(out, RecipeOutcome)` REMOVED (was a runtime error). |
| F3  | block    | `NotApplies(reason="r1")` — Pydantic rejects (reason is closed `Literal`); also `reason="x"`, `"PEER_DEP_CONFLICT"` mixed | Applied — every test reason drawn from `get_args(NotApplicableReason)`; `NO_RECIPES_REGISTERED` added to the Literal as part of this story.                  |
| F4  | block    | `_recipe()` helper mutates class attr after class body (`R.precedence = precedence`) — fragile, shares state across instances of same kind | Applied — helper rewritten as a real class factory with `precedence` and `verdict` as class attributes set in `type()` call; `applies_calls` lives on instances. |
| F5  | harden   | Decorator-returns-class-unchanged assertion (`Semver.recipe_id == "npm-semver-bump"`) doesn't catch wrapper-replaces-class mutant | Applied — AC mandates `assert <returned> is Semver` identity check (catches `return type("Wrapped", ...)` mutant).                                          |
| F6  | harden   | Default-registry pollution check is half-control only (`len == 0`)                  | Applied — autouse fixture in `tests/unit/plugins/conftest.py` extended to BOTH snapshot pre-test AND restore post-test, mirroring S2-01 `restore_default_registry`. |
| F7  | harden   | Hypothesis test for ordering determinism mentioned in AC but no concrete test body  | Applied — concrete subprocess-launch test added to TDD plan (PYTHONHASHSEED ∈ {0,1,2,42}; assert byte-identical `all()` output).                            |
| F8  | nit      | First-`Applies`-wins call-count check could regress to "second never registered" if order broken | Applied — test asserts third recipe IS in `registry.all(PID)` (registration succeeded) AND its `applies_calls == 0` (walker stopped early).                |

### Consistency critic — 12 findings

| ID  | Severity | Title                                                                                            | Resolution                                                                                                                                                                                                |
| --- | -------- | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F1  | block    | `RecipeEngine` Protocol declared in TWO places — `plugins/protocols.py:81-98` (S2-01 stub) and story's new `transforms/recipe_engine.py` | Applied — story pins the canonical home as `codegenie.transforms.recipe_engine` per High-level-impl §Step 5 (L136). `plugins/protocols.py` is amended in-place to **delete its `RecipeEngine` declaration** and re-export from `transforms.recipe_engine` (replaces the S2-01 deferred stub). Files-to-touch updated. |
| F2  | block    | Story's `RecipePlan` Pydantic model duplicates the already-shipped `ApplicationPlan` (S1-03 outcomes.py) | Applied — story reuses `ApplicationPlan` from `codegenie.transforms.outcomes`. Notes explain Phase 7 widens `ApplicationPlan` additively (not introduce a new `RecipePlan`).                                |
| F3  | block    | `RecipeId.parse(...)` smart constructor does not exist (`RecipeId` is bare `NewType`)             | Applied — AC rewritten to validate `recipe_id` via a private `_validate_recipe_id(rid: str) -> RecipeId` helper that asserts `re.fullmatch(r"^[a-z][a-z0-9-]*$", rid)`. No invented `.parse()` on a `NewType`. Notes-for-implementer adds: "If S1-01 ever lands a real `RecipeId.parse()` smart constructor (ADR amendment), migrate to it; until then this helper is the boundary lift." |
| F4  | block    | `NotApplicableReason` Literal does NOT include `NO_RECIPES_REGISTERED`                            | Applied — story explicitly lists "amend `outcomes.NotApplicableReason` to include `NO_RECIPES_REGISTERED`" as an in-scope task. Files-to-touch includes `src/codegenie/transforms/outcomes.py`. Notes flag this as a Phase-5 contract surface drift — re-baseline `tests/integration/test_phase5_contract_snapshot.py` golden (ADR-0001 §Consequences "snapshot regeneration + ADR amendment"). A Phase-3 ADR amendment is required and named in Notes. |
| F5  | block    | `considered: list[NotApplies]` field doesn't exist on `RecipeNotApplicable` (S1-03 frozen shape)  | Applied — story rewritten to make this an **additive field with `default_factory=list`** on `RecipeNotApplicable`, re-baseline the contract-snapshot, AND introduce an ADR amendment line in Notes citing ADR-0001 §Consequences. Additive Pydantic field (with default) does NOT break Phase 5 callers — they read `considered` as `[]` when absent. The snapshot regeneration is an explicit Files-to-touch entry. |
| F6  | block    | Goal text (`match_recipes(registry, cve, bundle)`) contradicts AC-7 (`match_recipes(registry, plugin_id, cve, bundle)`) | Applied — Goal rewritten to 4-arg shape (per-plugin scoping is the load-bearing design choice; arch §Gap 3 Improvement makes this explicit).                                                                |
| F7  | block    | `NpmInstallCapability` not yet shipped; S4-05 (HARDENED) is not in `Depends on:`                  | Applied — `Depends on:` expanded to include S4-05; `NpmInstallCapability` is forward-ref'd under `TYPE_CHECKING` until S4-05 lands. Notes spell out: if S4-05 lands first, the import comes off the TYPE_CHECKING block; if S5-01 lands first, the TYPE_CHECKING guard avoids the runtime import error. |
| F8  | harden   | ADR-0009 §Decision says "Ship `RecipeEngine(Protocol)` in `src/codegenie/plugins/protocols.py`" — conflicts with story's `transforms/recipe_engine.py` location | Applied — Notes-for-implementer cites the divergence and pins the canonical location as `codegenie.transforms.recipe_engine` per High-level-impl Step 5 (the more recent and load-bearing reference); ADR-0009 to be amended as a follow-up cleanup (named in Notes). The re-export in `plugins/protocols.py` preserves backward compatibility for any S2-01 consumer. |
| F9  | harden   | `RecipeProtocol(Protocol)` declared in story but NOT in arch §Component design / High-level-impl  | Applied — Notes-for-implementer cites the arch line ("How does match_recipe find the four recipes?") and pins `RecipeProtocol` as new in this story, with `@runtime_checkable` and frozen surface attributes (`recipe_id`, `name`, `kind`, `precedence`, `applies`).                          |
| F10 | harden   | `match_recipes` should not emit events here (events are S6-01) — already correctly out-of-scoped, but the test doesn't assert event-free | Applied — TDD plan adds a test asserting `match_recipes` does NOT touch the `EventLog` (introspect via monkeypatched no-op `EventLog` — no calls expected).                                                |
| F11 | harden   | `RecipeProtocol.applies(cve, bundle)` — `bundle` type forward-ref needs the `Bundle` placeholder to ship now (S3-04 owns it) | Applied — Implementation outline §1 confirms `bundle: "Bundle"` under `TYPE_CHECKING`; `Bundle` is a Pydantic model that S3-04 ships. Notes pin the contract: structural Bundle field reads happen at recipe call sites, not in the Protocol surface. |
| F12 | nit      | "`tests/integration/test_phase5_contract_snapshot.py` will fail under additive `considered` field" — not addressed | Applied — Files-to-touch adds the snapshot regeneration line and Notes pin: "additive `considered: list[NotApplies] = Field(default_factory=list)` is backwards-compatible by Pydantic semantics; existing callers consuming `RecipeNotApplicable.reason` continue to work; the snapshot test re-bakes with the new field." |

### Design-Patterns critic — 6 findings

| ID  | Severity | Title                                                                                          | Resolution                                                                                                                                                                                                                              |
| --- | -------- | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| F1  | harden   | `default_recipe_registry: RecipeRegistry = RecipeRegistry()` — not `Final[...]` like S2-01     | Applied — AC mandates `default_recipe_registry: Final[RecipeRegistry] = RecipeRegistry()`. Mirror S2-01 §3 rationale.                                                                                                                    |
| F2  | harden   | Class-decorator shape forces `recipe_cls()` instantiation — precludes recipes carrying state at construction | Documented — Notes-for-implementer §"Class-decorator vs function-call" pins the asymmetry with rationale: recipes are *stateless matchers* with class-attribute identity (`recipe_id`, `name`, `kind`, `precedence`); engines (S5-02 / S5-03) carry state and are wired via `plugin.transforms()`. The split is intentional. Mirrors `@register_probe` (class-decorator, stateless) and contrasts with `register_plugin(instance)` (instance, stateful). If a recipe ever needs construction args, the function-call dual-shape is a backwards-compatible extension. |
| F3  | nit      | Rule-of-N=5 observation — this is the 5th decorator-registry in the codebase                   | Applied — module docstring on `plugins/recipe_registry.py` adds the N=5 census + extract-trigger paragraph (mirror `plugins/registry.py:39-49` shape). The kernel-extract is **still deferred** because this registry's dispatch shape (precedence-name sort + plugin_id filter + first-applies-wins walker) is distinct from the 4 predecessors. The deferral discipline is the design pattern. |
| F4  | harden   | `RegisteredRecipe` should be `@dataclass(frozen=True, slots=True)` (story has it; preserve)     | No-op — story already specifies. Validation report confirms the choice.                                                                                                                                                                  |
| F5  | harden   | `clear()` on `RecipeRegistry` — S2-01 deliberately did NOT add `unregister_for_tests` to `PluginRegistry`; story diverges | Applied — `clear()` retained but renamed to `_reset_for_tests()` (leading underscore signals test-only) + docstring cites "S2-01 §"Cross-test isolation mechanism"; this kernel ships the helper because the autouse fixture targets the default explicitly." Notes-for-implementer pin the rationale: the alternative is a fixture that snapshots-and-restores `_recipes` directly (no public surface), which is the S2-01 path. Either is acceptable; the story picks `_reset_for_tests()` to keep test setup readable. |
| F6  | nit      | `MatchedRecipe` should be a frozen dataclass, not a Pydantic model — fast hot-path             | Applied — AC pins `MatchedRecipe` as `@dataclass(frozen=True, slots=True)`; not Pydantic (no extra-forbid validation needed for an internal walker return).                                                                              |

---

## Stage 3 — Conditional research

**Skipped.** No `NEEDS RESEARCH` tags. All canonical patterns (Registry, Strategy, Sum type, Smart constructor, Dependency inversion) are already cited and well-trodden in this codebase (`plugins/registry.py`, `transforms/outcomes.py`, `probes/registry.py`).

---

## Stage 4 — Synthesizer

Applied 33 of 34 findings (one was already-correct; verified). Five **BLOCK** findings centred on contract drift against as-built S1-03 / S2-01:

1. `Applicability` and `RecipeOutcome` import path (`outcomes`, not `applicability`).
2. `RecipeOutcome` is a `TypeAlias`, not a class with `.NotApplicable` accessors.
3. `RecipeId.parse()` smart constructor doesn't exist — use a private `_validate_recipe_id` regex helper.
4. `NotApplicableReason` Literal needs `NO_RECIPES_REGISTERED` added (Phase-5 contract snapshot re-bake; ADR amendment).
5. `RecipeEngine` Protocol shipped in `plugins/protocols.py` (S2-01 stub) must be replaced — single canonical declaration in `transforms/recipe_engine.py`, re-exported from `plugins/protocols.py`.

The story is now ready for the executor.

**Verdict:** **HARDENED.**

---

## Edits applied (summary)

- Goal rewritten to 4-arg `match_recipes(registry, plugin_id, cve, bundle)` returning `MatchedRecipe | RecipeNotApplicable`.
- ACs rewritten: numbered, individually verifiable, mutation-resistant. Imports corrected to `codegenie.transforms.outcomes`. `RecipeNotApplicable` accessed directly (no pseudo-OO `.NotApplicable`). `RecipeProtocol` requires `kind: TransformKind`. `MatchedRecipe` pinned as frozen dataclass. `_validate_recipe_id` helper specified. `NotApplicableReason` widened by additive Literal. `RecipeNotApplicable` widened by additive `considered: list[NotApplies] = []` field with snapshot regeneration named.
- TDD plan rewritten: real Pydantic constructors (`Applies(plan=ApplicationPlan(...))`, `NotApplies(reason="PEER_DEP_CONFLICT")`); `_recipe()` helper rewritten via `type()` factory; `isinstance(out, RecipeOutcome)` removed (was a runtime error); identity check on decorator return.
- Implementation outline updated to consume `ApplicationPlan` (no new `RecipePlan`), forward-ref `NpmInstallCapability` under `TYPE_CHECKING`, replace the S2-01-stub `RecipeEngine` declaration in `plugins/protocols.py` with a re-export.
- Files-to-touch expanded with `src/codegenie/transforms/outcomes.py` (additive Literal + additive field) and `tests/integration/test_phase5_contract_snapshot.py` (snapshot rebake) and `src/codegenie/plugins/protocols.py` (delete the duplicate `RecipeEngine` declaration; re-export from `transforms.recipe_engine`).
- Out-of-scope expanded with concurrent registration + module-reload semantics (mirror S2-01).
- Depends on widened to S4-05 (`NpmInstallCapability`).
- Notes-for-implementer expanded: divergence from ADR-0009 §Decision location pinned (`transforms/recipe_engine.py` is the canonical home per High-level-impl Step 5 L136); rule-of-N=5 paragraph added; class-decorator vs function-call asymmetry rationalized; `_validate_recipe_id` boundary lift documented.
- New `Validation notes` block prepended to the story header.

---

## Notes for future validations

This story's BLOCK findings were almost all *consistency-vs-as-built-code* — the original draft referenced symbols and import paths that S1-03 and S2-01 explicitly relocated (S1-03 consolidated all outcome unions into `outcomes.py`; S2-01 shipped the `RecipeEngine` stub in `protocols.py` and deferred its freeze to Step 5). The validator caught this because it grepped the actual `src/` tree, not just the docs. Future Phase 3 story validators should always check `src/codegenie/transforms/__init__.py` and `src/codegenie/plugins/protocols.py` against the story's import paths before approving — those two files are the Phase-3 canonical home and a drift signal.
