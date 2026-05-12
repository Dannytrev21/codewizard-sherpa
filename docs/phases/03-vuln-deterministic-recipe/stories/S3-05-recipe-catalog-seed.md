# Story S3-05 — `recipes/catalog/npm/<recipe-id>.yaml` first recipe seed + models

**Step:** Step 3 — Ship the `NcuRecipeEngine` vertical: `tools/npm` + `tools/ncu` wrappers, `LockfileResolver`, `LockfileCanonicalizer`, recipe catalog + selector
**Status:** Ready
**Effort:** S
**Depends on:** S3-04
**ADRs honored:** ADR-0001, ADR-0002, ADR-0004

## Context

Phase 3 ships the contract for recipes (Pydantic `Recipe` model) plus at minimum **one** working recipe, so the selector + engine vertical proves end-to-end on a real fixture in S7-02. The first recipe is `npm-upgrade-patched-v1` — a `(ecosystem=npm, engine=ncu, kind=version_bump)` recipe that the `NcuRecipeEngine` drives to bump dependencies to the patched version. Future recipes (`npm-upgrade-minor-v1`, OpenRewrite stub recipe in S6-01, Phase 7 docker recipe, Phase 15 author-loop recipes) extend this catalog without editing existing files.

This story lands the Pydantic `Recipe` model + `ApplyConstraints` per the arch's component design + the YAML for the first recipe + the manifest entry in `recipes/digests.yaml` + a round-trip unit test.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #3 (Recipe, RecipeSelector, catalog)` — `Recipe` Pydantic shape; `ApplyConstraints`.
  - `../phase-arch-design.md §"Components" #2a NcuRecipeEngine` — the engine that drives this recipe.
- **Phase ADRs:**
  - `../ADRs/0001-transform-recipe-engine-two-abc-contract.md` — `RecipeEngine` ABC.
  - `../ADRs/0002-two-new-top-level-packages-transforms-recipes.md` — `recipes/catalog/<ecosystem>/` directory shape.
  - `../ADRs/0004-recipe-selection-structured-triple-not-optional.md` — selector contract that consumes this recipe.
- **Source design:**
  - `../final-design.md §"Components" #3` — recipe-as-data discipline.
- **Existing code:**
  - `src/codegenie/recipes/registry.py` (from S3-04) — loader that hashes + validates this YAML.
  - `src/codegenie/recipes/digests.yaml` (from S3-04) — manifest the new YAML must register in.
  - `src/codegenie/recipes/contract.py` (from S1-03) — `RecipeEngine` interface that consumes the recipe.

## Goal

Ship `src/codegenie/recipes/models.py` (`Recipe` + `ApplyConstraints` Pydantic) and `src/codegenie/recipes/catalog/npm/npm-upgrade-patched-v1.yaml` (the first recipe). Register its digest in `recipes/digests.yaml`. Round-trip-test that `RecipeRegistry.load(...)` returns the parsed recipe.

## Acceptance criteria

- [ ] `src/codegenie/recipes/models.py` exports `ApplyConstraints` and `Recipe` matching the arch design:
  - `ApplyConstraints` → `{ecosystem: Literal["npm"], languages: list[str], package_glob: str | None, cve_patterns: list[str] = ["*"], semver_range_predicate: str | None}`.
  - `Recipe` → `{id: str, engine: Literal["ncu","openrewrite"], ecosystem: Literal["npm"], kind: Literal["version_bump"], applies_to: ApplyConstraints, params: dict, declared_inputs: list[str], digest: str, priority: int = 100}`.
  - All models `model_config = ConfigDict(extra="forbid", frozen=True)`.
- [ ] `src/codegenie/recipes/catalog/npm/npm-upgrade-patched-v1.yaml` exists with:
  - `id: npm-upgrade-patched-v1`
  - `engine: ncu`
  - `ecosystem: npm`
  - `kind: version_bump`
  - `applies_to: {ecosystem: npm, languages: ["javascript","typescript"], package_glob: null, cve_patterns: ["*"], semver_range_predicate: "supports_patched_version"}`
  - `params: {target: "patch"}`
  - `declared_inputs: ["package.json", "package-lock.json"]`
  - `digest: <sha256 of canonicalized YAML>`
  - `priority: 100`
- [ ] `src/codegenie/recipes/digests.yaml` adds the matching `npm-upgrade-patched-v1: {sha256: "<...>"}` entry.
- [ ] `tests/unit/recipes/test_first_recipe_roundtrip.py` — `RecipeRegistry.load(...)` returns a `Recipe` whose fields exactly equal the YAML.
- [ ] `tests/unit/recipes/test_recipe_extra_field_rejected.py` — adding `foo: bar` to a recipe-shaped dict raises `pydantic.ValidationError` (anchors `additionalProperties: false` discipline).
- [ ] `ruff check`, `mypy --strict`, `pytest` pass.

## Implementation outline

1. Land `tests/unit/recipes/test_first_recipe_roundtrip.py` first (red — the model module doesn't exist yet).
2. Implement `src/codegenie/recipes/models.py`:
   ```text
   ApplyConstraints(BaseModel): ecosystem, languages, package_glob, cve_patterns, semver_range_predicate
   Recipe(BaseModel): id, engine, ecosystem, kind, applies_to, params, declared_inputs, digest, priority
   ```
   Both with `extra="forbid"` and `frozen=True`.
3. Author `src/codegenie/recipes/catalog/npm/npm-upgrade-patched-v1.yaml` with the field values above.
4. Run `python -m codegenie.recipes.registry --recompute-digests` (utility from S3-04) to produce the SHA-256, paste it into both `digests` (recipe `digest` field) and `recipes/digests.yaml`.
5. Add the extra-field-rejection unit test.
6. Run the full unit suite.

## TDD plan — red / green / refactor

### Red
Path: `tests/unit/recipes/test_first_recipe_roundtrip.py`
```python
from pathlib import Path

from codegenie.recipes.registry import RecipeRegistry


def test_first_recipe_loads_and_roundtrips():
    catalog = Path("src/codegenie/recipes/catalog")
    manifest = Path("src/codegenie/recipes/digests.yaml")
    loaded = RecipeRegistry.load(catalog_root=catalog, manifest_path=manifest)
    r = loaded["npm-upgrade-patched-v1"]
    assert r.engine == "ncu"
    assert r.ecosystem == "npm"
    assert r.kind == "version_bump"
    assert r.applies_to.languages == ["javascript", "typescript"]
    assert r.params == {"target": "patch"}
    assert r.priority == 100
```

### Green
Land the Pydantic models, the YAML, and the manifest entry. The first run will compute the YAML's canonical digest; commit both digest fields (in the YAML body and in `recipes/digests.yaml`) at the same SHA.

### Refactor
- After S3-06 lands and uses `Recipe.applies_to.semver_range_predicate`, the predicate-string DSL may want its own type alias; defer.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/recipes/models.py` | New — `Recipe` + `ApplyConstraints` Pydantic |
| `src/codegenie/recipes/catalog/npm/npm-upgrade-patched-v1.yaml` | New — first recipe |
| `src/codegenie/recipes/digests.yaml` | Add manifest entry |
| `tests/unit/recipes/test_first_recipe_roundtrip.py` | New |
| `tests/unit/recipes/test_recipe_extra_field_rejected.py` | New |

## Out of scope

- **Selector** — handled by S3-06.
- **Engine that drives this recipe** — handled by S3-07.
- **Decision-table YAML (`selector.yaml`)** — handled by S3-06.
- **OpenRewrite-shaped recipe** — handled by S6-01 (different catalog dir).

## Notes for the implementer
- The `digest` field inside the YAML body and the `sha256` entry in `recipes/digests.yaml` must match. The canonicalization function from S3-04 is the source of truth; if there's any drift, the loader refuses.
- `semver_range_predicate` is a string DSL evaluated by the selector in S3-06; for this first recipe use the placeholder `"supports_patched_version"` — S3-06 will define the predicate's evaluation contract.
- `priority: 100` is the default; lower numbers win in the future when multiple recipes match a given advisory (S3-06 enforces ties → error).
- Pydantic `frozen=True` is load-bearing — the registry returns immutable values; consumers must not mutate.
- The single shipped recipe is the minimum viable surface to land Step 3; S4-S5 do not need more recipes to land. Phase 4 onwards adds them.
- Do **not** add a YAML schema file (`recipe.schema.json`) — the Pydantic model **is** the schema, and `RecipeRegistry.load` is the validator. The arch deliberately rejects a second source of truth.
