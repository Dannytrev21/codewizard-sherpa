# Story S1-02 — `src/codegenie/transforms/` package skeleton + `Transform` ABC + registry

**Step:** Step 1 — Plant the two ABCs, the four Phase 0/1/2 additive edits, and the foundations every Phase 3 component consumes
**Status:** Ready
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0001, ADR-0002

## Context

The `Transform` ABC is the second load-bearing contract in the system after Phase 1's `Probe` — Phase 4 (LLM fallback), Phase 5 (Trust-Aware gates), Phase 6 (state machine), Phase 7 (Chainguard transforms), and Phase 15 (agent-authored recipes) all compose around it. ADR-0001 freezes the ABC at v0.3.0 with an explicit append-only field policy; ADR-0002 places it in a new top-level package `src/codegenie/transforms/` so the Phase-0 `fence` CI can refuse LLM SDK imports under the entire transforms subtree. This story plants the package, the ABC, and the registry — no concrete transforms, no engines, no coordinator — only the contract surface that every Phase 3 component reads.

The single most important artifact here is the **frozen Pydantic schema snapshot** of `TransformInput` and `TransformOutput`, modeled byte-for-byte on Phase 0's `tests/unit/test_probe_contract.py`. Once green, any future signature drift — by a future implementer or by Claude — fails CI red. This is the same discipline that has kept the `Probe` ABC stable across Phases 1 and 2.

## References — where to look

- **Architecture:** `../phase-arch-design.md §"Component design" #1 (Transform ABC + TransformRegistry)` — public interface, Pydantic at boundary, `requires_recipe_engines` field, registry-via-decorator pattern, snapshot test discipline.
- **Architecture:** `../phase-arch-design.md §"Development view — module tree"` — `transforms/contract.py`, `transforms/registry.py` placement.
- **Architecture:** `../phase-arch-design.md §"Data model" → Inputs/Outputs`  — `TransformInput`, `TransformOutput` field set.
- **Phase ADRs:** `../ADRs/0001-transform-recipe-engine-two-abc-contract.md` — ADR-0001 — two-ABC commitment, append-only field policy, no `success` field on output.
- **Phase ADRs:** `../ADRs/0002-two-new-top-level-packages-transforms-recipes.md` — ADR-0002 — package layout; `transforms/` and `recipes/` as new top-level packages so the Phase-0 fence can scope correctly.
- **Production ADRs:** `../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md` — POC-to-service contract preservation; the Transform ABC is the service-shaped contract Phase 4 reads.
- **Source design:** `../final-design.md §"Goals" §"Contract goals" rows 1–3` — the two-ABC commitment.
- **Source design:** `../final-design.md §"Synthesis ledger" "Conflict-resolution table" row "Top-level Transform ABC"` — the synth departure from all three input lenses.
- **Existing code:** `src/codegenie/probes/contract.py`, `src/codegenie/probes/registry.py`, `tests/unit/test_probe_contract.py` (Phase 0) — the byte-for-byte template this story mirrors.

## Goal

Land `src/codegenie/transforms/{__init__.py, contract.py, registry.py}` so that (a) the `Transform` ABC matches the Probe shape with the addition of `requires_recipe_engines`, (b) `@register_transform` rejects duplicate-name registration, and (c) a frozen Pydantic schema-dump snapshot of `TransformInput` and `TransformOutput` is checked into `tests/unit/transforms/test_contract.py` and fails CI on drift.

## Acceptance criteria

- [ ] `src/codegenie/transforms/__init__.py` exports `Transform`, `TransformInput`, `TransformOutput`, `register_transform`, `all_transforms`.
- [ ] `src/codegenie/transforms/contract.py` defines `class Transform(ABC)` with class-level attributes `name: str`, `declared_inputs: Sequence[str]`, `applies_to_tasks: Sequence[str]`, `applies_to_languages: Sequence[str]`, `requires_recipe_engines: Sequence[str]`; abstract methods `applies(view, advisory, recipe) -> bool` and `run(input: TransformInput) -> TransformOutput`.
- [ ] `TransformInput` is a `pydantic.BaseModel` with `model_config = ConfigDict(extra="forbid", frozen=True)` and exactly the fields listed in `phase-arch-design.md §"Data model" → Inputs` (`repo_root: Path`, `worktree_root: Path`, `branch_name: str`, `advisory: CveEntry`, `recipe: Recipe`, `repo_context_path: Path`, `run_id: str`). `advisory` and `recipe` are typed against forward refs resolved in S1-04 (use `from __future__ import annotations` + `TYPE_CHECKING`).
- [ ] `TransformOutput` is a `BaseModel` with `extra="forbid"` and exactly the fields listed in `phase-arch-design.md §"Data model" → Outputs` (`name: str`, `diff_path: Path | None`, `branch_name: str | None`, `files_changed: list[Path]`, `confidence: Literal["high","medium","low"]`, `warnings: list[str]`, `errors: list[str]`, `skipped: bool`). **There is no `success` field.**
- [ ] `src/codegenie/transforms/registry.py` exposes `@register_transform` and `all_transforms() -> Sequence[type[Transform]]`. Duplicate-name registration raises `RuntimeError` at decoration time (per Phase 0's `@register_probe` precedent).
- [ ] `tests/unit/transforms/test_contract.py` contains a snapshot test asserting `TransformInput.model_json_schema()` and `TransformOutput.model_json_schema()` match a checked-in canonical JSON file under `tests/unit/transforms/snapshots/transform_contract_v0_3_0.json` (formatted, sorted keys); any drift fails CI red.
- [ ] `tests/unit/transforms/test_contract.py` includes a structural assertion that `TransformOutput` does **not** define a `success` field (the docstring's "facts not judgments" rule is encoded as a test).
- [ ] `tests/unit/transforms/test_registry.py` covers (a) happy registration via decorator, (b) duplicate-name rejection, (c) `all_transforms()` returns a `tuple` (immutable snapshot), (d) registration order is preserved per insertion.
- [ ] No `subprocess.run`/`subprocess.Popen`/`os.system` imports under `src/codegenie/transforms/` (the fence test in S1-09 will assert this; this story keeps the package clean from the start).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/transforms/ tests/unit/transforms/` pass.

## Implementation outline

1. Read `src/codegenie/probes/contract.py` and `src/codegenie/probes/registry.py` end-to-end — Rule 8. The Transform ABC mirrors them byte-for-byte except for the `requires_recipe_engines` field on the class and the Pydantic-frozen `TransformInput`/`TransformOutput`.
2. Write `tests/unit/transforms/test_contract.py` red — snapshot path under `tests/unit/transforms/snapshots/transform_contract_v0_3_0.json` does not exist yet; the test asserts schema-dump equals file contents. Initially the assertion fails because both the schema and the file are absent.
3. Write `tests/unit/transforms/test_registry.py` red — `from codegenie.transforms import register_transform, all_transforms` ImportErrors.
4. Create the package: `src/codegenie/transforms/__init__.py`, `contract.py`, `registry.py`. Mirror the Phase-0 module docstrings ("Phase 3 — Transform ABC and registry (ADR-0001, ADR-0002). DO NOT EDIT FIELD SET WITHOUT AN ADR AMENDMENT.").
5. Run the contract test once; capture the produced schema-dump JSON; write it to the snapshot file; re-run; it now passes. This is the same "generate snapshot once, freeze" workflow Phase 0 used for `Probe`.
6. Implement `registry.py` with `_TRANSFORMS: dict[str, type[Transform]] = {}` and the decorator. Duplicate-name rejection raises `RuntimeError(f"duplicate transform name: {cls.name}")` — the message matches the Phase 0 wording exactly.
7. Wire `tests/unit/transforms/__init__.py` (empty file) so pytest discovers the package; same for `tests/unit/transforms/snapshots/__init__.py`.
8. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest tests/unit/transforms/`.

## TDD plan — red / green / refactor

### Red — failing test first

Test file paths: `tests/unit/transforms/test_contract.py`, `tests/unit/transforms/test_registry.py`.

```python
# tests/unit/transforms/test_contract.py
import json
from pathlib import Path
from codegenie.transforms.contract import TransformInput, TransformOutput, Transform

SNAPSHOT = Path(__file__).parent / "snapshots" / "transform_contract_v0_3_0.json"

def test_transform_input_output_schema_matches_v0_3_0_snapshot():
    # arrange: load canonical snapshot
    # act: dump current schemas
    # assert: equal — drift fails CI red
    ...

def test_transform_output_has_no_success_field():
    # ADR-0001: "facts not judgments — validators emit `passed`, transforms emit `confidence`"
    assert "success" not in TransformOutput.model_fields

def test_transform_abc_has_requires_recipe_engines():
    # The single declarative addition over the Probe shape
    assert "requires_recipe_engines" in Transform.__annotations__
```

```python
# tests/unit/transforms/test_registry.py
import pytest
from codegenie.transforms.registry import register_transform, all_transforms
from codegenie.transforms.contract import Transform

def test_register_transform_happy_path():
    # arrange: declare a minimal Transform subclass with a unique name
    # act: decorate
    # assert: all_transforms() includes it; tuple type
    ...

def test_duplicate_name_registration_raises_runtime_error():
    # Same posture as Phase 0 @register_probe: loud at decoration time
    ...

def test_all_transforms_returns_immutable_tuple():
    # Callers must not mutate the registry mid-run
    ...
```

Run — every test imports a not-yet-existent module; commit red.

### Green — make it pass

- Create the three files under `src/codegenie/transforms/`. ABC mirrors Phase 0 Probe verbatim, with the additional class attribute `requires_recipe_engines: Sequence[str]`.
- `TransformInput`/`TransformOutput` are frozen Pydantic with the exact field set from `phase-arch-design.md §"Data model"`. Forward refs (`"CveEntry"`, `"Recipe"`) resolved lazily — S1-04 imports the concrete types and `model_rebuild()`-es.
- Decorator + registry: copy Phase 0's `probes/registry.py` verbatim; rename to transform-shaped identifiers.
- Generate the snapshot once (`python -c "from codegenie.transforms.contract import TransformInput, TransformOutput; import json, pathlib; pathlib.Path('tests/unit/transforms/snapshots/transform_contract_v0_3_0.json').write_text(json.dumps({'input': TransformInput.model_json_schema(), 'output': TransformOutput.model_json_schema()}, indent=2, sort_keys=True))"`); commit it.

### Refactor — clean up

- Move docstrings into `contract.py` (Transform docstring lists all five class attributes with their semantics, references ADR-0001 by ID).
- Confirm `mypy --strict` is clean. `Sequence[str]` over `list[str]` on class-level metadata so subclasses can pass tuples (matches Phase 0 Probe).
- `__all__` on `__init__.py` lists exactly the public names; no internal helpers leak.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/__init__.py` | Public package surface |
| `src/codegenie/transforms/contract.py` | `Transform` ABC + `TransformInput` + `TransformOutput` |
| `src/codegenie/transforms/registry.py` | `@register_transform` + `all_transforms()` |
| `tests/unit/transforms/__init__.py` | pytest package marker |
| `tests/unit/transforms/test_contract.py` | Snapshot + structural tests |
| `tests/unit/transforms/test_registry.py` | Decorator behavior |
| `tests/unit/transforms/snapshots/transform_contract_v0_3_0.json` | Frozen schema dump |

## Out of scope

- **`RecipeEngine` ABC + registry** — S1-03.
- **Concrete `RecipeSelection`, `ApplyContext`, `RecipeApplication`, `ValidatorOutput`, `GateOutcome`, `TrustScore`, `RemediationReport` Pydantic models** — S1-04.
- **Concrete `NpmPackageUpgradeTransform`** — Step 5.
- **Coordinator (`transforms/coordinator.py`)** — Step 5.
- **`RepoContextView` type** — referenced in `Transform.applies()` but the concrete type lives in Step 3 (`transforms/context.py`); this story uses a forward ref + `TYPE_CHECKING` guard.
- **Fence test asserting no LLM imports under `transforms/`** — S1-09.

## Notes for the implementer

- **Snapshot generation is one-shot, not iterative.** Generate the canonical JSON once after the Pydantic models are stable, commit it, and never regenerate without an ADR amendment to ADR-0001. The whole point of the snapshot is to detect unintentional drift.
- Phase 0's `@register_probe` raises `RuntimeError` (not a typed `CodegenieError`) for duplicate-name. Match that — Rule 11 — even though it deviates from the typed-exception discipline elsewhere. The reason: registration happens at module import, before the error hierarchy is loaded in some import orders; `RuntimeError` is safe across all of them.
- The class-level `name` attribute is a plain string, not a `Literal`. Subclasses set it. The registry uses `cls.name` lookups; subclasses that forget set the inherited `name: str` to its empty default and the registry rejects empty strings explicitly (mirroring Phase 0 Probe).
- `requires_recipe_engines: Sequence[str]` accepts `["ncu"]`, `["ncu", "openrewrite"]`, or `[]` (transforms that drive no engine — none in v0.3.0 but the field exists for Phase 7's Dockerfile transform). Default is **not** provided at the ABC; subclasses must declare it explicitly so missing it is a `mypy` error, not a silent `[]`.
- The forward refs to `CveEntry` and `Recipe` are resolved in S1-04 via `TransformInput.model_rebuild()` called from S1-04's models module. Until S1-04 lands, the snapshot test substitutes simple `dict` schemas where the forward refs appear — document this in the snapshot file's top-level `$comment` so a future reader understands why the schema is partially abstract.
- Resist adding a `description` field, a `version` field, or a `tags` field to `Transform`. The minimum surface that survives all four downstream phases is locked by ADR-0001; expansions require an ADR amendment and a coordinated PR.
- Do **not** import `pydantic.v1` — Phase 0 uses pydantic v2; conform.
