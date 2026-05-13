# Story S1-05 — Extend `Recipe.engine` `Literal` with `"dockerfile"`

**Step:** Step 1 — Establish the six additive seams, ADRs, and the contract-surface snapshot canary
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-P7-006 (this phase ADR-0007), ADR-P7-008 (this phase ADR-0001), production ADR-0011

## Context

Phase 3 ships `Recipe.engine: Literal["ncu", "openrewrite"]` — a closed `Literal` that Pydantic rejects on unknown deserialized values. The Phase 7 `DockerfileRecipeEngine` (S4-01) must match a `Recipe.engine` value at recipe-load time, so the closed `Literal` is extended by one value: `"dockerfile"`. This is the most surgical of the six seams — a single source-line edit — but it is *the* test of the "closed-`Literal` wall" the critic named as the load-bearing tension in extension-by-addition. A round-trip test fixture proves existing recipes still deserialize identically.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 13 ADR-P7-006` (the exact source-line diff and the closed-`Literal`-wall rationale).
  - `../phase-arch-design.md §Component 4. DockerfileRecipeEngine` — the consumer that will register `name = "dockerfile"` and dispatch on this value (S4-01; not in scope here).
- **Phase ADRs:**
  - `../ADRs/0007-recipe-engine-literal-extended-with-dockerfile.md` — ADR-P7-006 — the decision; rejection of the "open `Literal` to `str`" alternative; closed-`Literal` discipline preserved.
  - `../ADRs/0001-six-named-additive-seams-and-adr-0028-amendment.md` — ADR-P7-008 — additive `Literal` extension is one of the six allowed shapes.
- **Production ADRs:**
  - `../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` — recipe-first dispatch; engine identification by `Recipe.engine` is the dispatcher's join key.
- **Existing code (read before writing):**
  - `src/codegenie/recipes/contract.py` — read `Recipe` and confirm `engine: Literal["ncu", "openrewrite"]` is the exact current shape. Note `RecipeSelection.reason` — it is *also* a closed `Literal` and is **NOT** edited (per ADR-P7-006's "RecipeSelection.reason NOT extended" decision; semantic stretch on `"unsupported_dialect"` is accepted).
  - Phase 3's `RecipeMatcher` (the dispatcher) — read once to confirm it routes on `recipe.engine` and will pick up the new value automatically when Step 4 lands the engine.
  - Any existing recipe-loading test (`tests/unit/recipes/test_contract.py` or similar) — confirm Pydantic raises `ValidationError` on `engine="unknown"` today; this story preserves that behavior for any value not in the extended Literal.

## Goal

`Recipe.engine` accepts `"dockerfile"` as a valid value; existing recipes with `engine: "ncu"` / `engine: "openrewrite"` deserialize byte-identically; an unknown value (`"foobar"`) still raises `ValidationError`.

## Acceptance criteria

- [ ] `src/codegenie/recipes/contract.py` defines `engine: Literal["ncu", "openrewrite", "dockerfile"]` on `Recipe`. Order: `"ncu"`, `"openrewrite"`, `"dockerfile"` — append at the end; do not reorder existing values.
- [ ] `RecipeSelection.reason` is byte-stable — its closed `Literal` value set is unchanged (verify by `sha256` of the file's `RecipeSelection` block against `master`, or by an explicit assertion in the test).
- [ ] `tests/unit/recipes/test_engine_literal_extension.py` is committed and green: (a) `Recipe(engine="dockerfile", <other required fields>)` deserializes without error; (b) `Recipe(engine="ncu", ...)` and `Recipe(engine="openrewrite", ...)` still deserialize byte-identically (round-trip through `model_dump_json` / `model_validate_json` produces the same JSON); (c) `Recipe(engine="totally_unknown", ...)` raises `pydantic.ValidationError`; (d) `RecipeSelection.reason` `Literal` value set is unchanged (compare `typing.get_args` against a hardcoded baseline).
- [ ] A round-trip fixture `tests/fixtures/recipes/engine_dockerfile_minimal.yaml` (or `.json`) — a minimal valid `Recipe` with `engine: "dockerfile"` — deserializes through `Recipe.model_validate` and serializes back via `model_dump_json` to a canonical-JSON byte-stable form.
- [ ] `ruff check`, `ruff format --check`, and `mypy --strict` pass on `src/codegenie/recipes/contract.py` and the new test file.

## Implementation outline

1. Read `src/codegenie/recipes/contract.py` end-to-end. Identify the `Recipe` class, confirm the `engine` field is `Literal["ncu", "openrewrite"]`, and identify which other fields are required (so the test fixture is complete).
2. Snapshot the existing `RecipeSelection.reason` `Literal` value set as a hardcoded test baseline (do not import it dynamically — that would mask the value-set drift this test must catch).
3. Write the failing tests in `tests/unit/recipes/test_engine_literal_extension.py` and add the round-trip fixture `tests/fixtures/recipes/engine_dockerfile_minimal.yaml` (TDD red).
4. Edit `Recipe.engine` to `Literal["ncu", "openrewrite", "dockerfile"]` (one-line edit) (TDD green).
5. Refactor: add a one-line inline comment `# "dockerfile" added in Phase 7 (ADR-P7-006)`; do not edit `RecipeSelection.reason`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/unit/recipes/test_engine_literal_extension.py`

```python
# tests/unit/recipes/test_engine_literal_extension.py
import json
import typing
import pytest
from pydantic import ValidationError

from codegenie.recipes.contract import Recipe, RecipeSelection


def _minimal_recipe_kwargs(engine: str) -> dict:
    # Build the minimum required kwargs to construct a Recipe — read contract.py to fill in.
    return {
        "engine": engine,
        "ecosystem": "npm",     # closed Literal["npm"] in Phase 3 — unchanged
        "kind": "version_bump", # closed Literal["version_bump"] in Phase 3 — unchanged
        # … other required fields per the current Recipe definition
    }


def test_recipe_accepts_dockerfile_engine():
    r = Recipe(**_minimal_recipe_kwargs("dockerfile"))
    assert r.engine == "dockerfile"


def test_existing_ncu_recipe_round_trip_byte_identical():
    r = Recipe(**_minimal_recipe_kwargs("ncu"))
    payload = r.model_dump_json()
    restored = Recipe.model_validate_json(payload)
    assert restored == r
    assert restored.model_dump_json() == payload


def test_existing_openrewrite_recipe_round_trip_byte_identical():
    r = Recipe(**_minimal_recipe_kwargs("openrewrite"))
    payload = r.model_dump_json()
    restored = Recipe.model_validate_json(payload)
    assert restored == r
    assert restored.model_dump_json() == payload


def test_unknown_engine_still_rejected_validationerror():
    with pytest.raises(ValidationError):
        Recipe(**_minimal_recipe_kwargs("totally_unknown_engine"))


def test_recipe_engine_literal_value_set_is_exactly_three():
    # The closed-Literal wall: catch accidental drift in either direction.
    engine_field = Recipe.model_fields["engine"]
    values = typing.get_args(engine_field.annotation)
    assert set(values) == {"ncu", "openrewrite", "dockerfile"}


def test_recipe_selection_reason_literal_unchanged():
    # ADR-P7-006: RecipeSelection.reason is NOT extended.
    reason_field = RecipeSelection.model_fields["reason"]
    values = set(typing.get_args(reason_field.annotation))
    # Hardcoded baseline from master — update only if the Phase 3 closed Literal genuinely changes.
    expected = {
        # … list every value the master copy of RecipeSelection.reason has, e.g.:
        # "no_recipe_matched", "unsupported_dialect", "ecosystem_mismatch", …
    }
    assert values == expected, (
        "RecipeSelection.reason closed Literal drifted. ADR-P7-006 says NOT extend; "
        "Phase 7 reuses 'unsupported_dialect' for image-dialect mismatch."
    )
```

Plus a round-trip fixture at `tests/fixtures/recipes/engine_dockerfile_minimal.yaml`:

```yaml
# tests/fixtures/recipes/engine_dockerfile_minimal.yaml — minimal valid Recipe with engine: dockerfile
engine: dockerfile
ecosystem: npm
kind: version_bump
# … other required fields per Recipe — fill from contract.py
```

Expected red failure mode: `pydantic.ValidationError: 1 validation error for Recipe / engine / Input should be 'ncu' or 'openrewrite' [type=literal_error, input_value='dockerfile']` on the first test.

### Green — make it pass

In `src/codegenie/recipes/contract.py`:

```python
class Recipe(BaseModel):
    # ... unchanged fields ...
    engine: Literal["ncu", "openrewrite", "dockerfile"]   # "dockerfile" added Phase 7 — ADR-P7-006
    ecosystem: Literal["npm"]            # unchanged
    kind: Literal["version_bump"]        # unchanged
    # ... unchanged fields ...
```

One-character-set edit. Do not touch `RecipeSelection.reason` or any other closed `Literal` in this file.

### Refactor — clean up

- Inline comment `# "dockerfile" added in Phase 7 — ADR-P7-006` immediately after the new value.
- Confirm `mypy --strict` is clean on the file (the new value should not trigger any narrowing-related errors in callers that pattern-match on engine).
- Re-run the broader Phase 3 unit-test suite (`pytest tests/unit/recipes/`) to confirm zero regressions.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/recipes/contract.py` | One-line edit: extend `Recipe.engine` `Literal` with `"dockerfile"` (ADR-P7-006). |
| `tests/unit/recipes/test_engine_literal_extension.py` | New test — TDD red anchor; round-trip + value-set drift detector. |
| `tests/fixtures/recipes/engine_dockerfile_minimal.yaml` | Minimal valid `Recipe` fixture with `engine: dockerfile` for round-trip. |

## Out of scope

- **`DockerfileRecipeEngine` (`src/codegenie/recipes/engines/dockerfile_engine.py`)** — S4-01 (Step 4 lands the engine that *consumes* this Literal value).
- **`DockerfileBaseImageSwapTransform`** — S4-03.
- **Recipe catalog entries `swap_base_image_single_stage.yaml`, `multi_stage_distroless_refactor.yaml`** — S4-04 and S4-05.
- **`RecipeSelection.reason` extension** — explicitly *out* per ADR-P7-006. Phase 7 reuses `"unsupported_dialect"` for image-dialect mismatch; do not propose a `"unsupported_image_dialect"` value.
- **Contract-surface snapshot regen capturing the new value set** — S1-07.

## Notes for the implementer

- Order in the `Literal` matters for the contract-surface snapshot's canonical-JSON serialization (S1-07). The arch doc specifies `Literal["ncu", "openrewrite", "dockerfile"]` — **append** at the end; do not reorder existing values. If you sort the literal alphabetically ("dockerfile" first), the snapshot diff in S1-07 widens unnecessarily.
- The `test_recipe_selection_reason_literal_unchanged` test is *not* a check that ADR-P7-006 was implemented — it is a check that ADR-P7-006's *non-decision* (don't extend `RecipeSelection.reason`) was honored. If you find yourself wanting to add `"unsupported_image_dialect"` to fix a "semantic stretch," **stop and re-read ADR-P7-006's Decision** — the semantic stretch is *accepted*; the seam count stays at six.
- The "unknown engine rejected" test is the load-bearing check that this remains a *closed* `Literal`. If a future story tries to relax it to `str`, this test fails and surfaces the regression. Do not weaken its assertion.
- The round-trip fixture must be minimal — only the required fields, no optional bloat. If `Recipe` requires a deeply-nested sub-model, build the smallest valid sub-model possible. Bloat in the fixture creates noise in the snapshot diff.
- This story's edit is one source line. If you find yourself touching more than `contract.py` plus one test file plus one fixture, you've drifted out of scope.
- Per CLAUDE.md "Surgical Changes": the only edit to `contract.py` is the engine `Literal` widening. Do not "fix" adjacent comments, formatting, or imports — that creates a snapshot diff in S1-07 that has nothing to do with ADR-P7-006 and confuses reviewers.
- The integration with `RecipeMatcher` is automatic: Phase 3's matcher dispatches on `recipe.engine` via the `@register_recipe_engine` registry. When S4-01 registers `DockerfileRecipeEngine` with `name = "dockerfile"`, the matcher picks it up without any further edit. This story does not touch the matcher.
