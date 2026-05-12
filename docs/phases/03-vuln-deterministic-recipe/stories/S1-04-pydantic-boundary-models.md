# Story S1-04 — Pydantic boundary models (`RecipeSelection`, `Recipe`, `ApplyConstraints`, `ValidatorOutput`, `GateOutcome`, `TrustScore`, `RemediationAttempt`, `RemediationReport`)

**Step:** Step 1 — Plant the two ABCs, the four Phase 0/1/2 additive edits, and the foundations every Phase 3 component consumes
**Status:** Ready
**Effort:** M
**Depends on:** S1-02, S1-03
**ADRs honored:** ADR-0001, ADR-0004, ADR-0013

## Context

S1-02 + S1-03 plant the two ABCs but leave the **boundary Pydantic models** that the ABCs reference as forward refs. This story lands all of them in one place so Phase 3's data shape is a closed, frozen, schema-validated surface from day one. The single most consequential model is `RecipeSelection` (ADR-0004): the synthesizer chose a structured triple over the performance-first `Optional[Recipe]` return type, with a closed `Literal` enum of six `reason` values. That enum is the public contract Phase 4 reads to decide whether to fall back to LLM planning; expanding it requires an ADR amendment + code + schema PR in the same change (the Phase 2 `detect.type` discipline).

The other models — `Recipe`, `ApplyConstraints`, `ValidatorOutput`, `GateOutcome`, `TrustScore`, `RemediationAttempt`, `RemediationReport` — are simpler in shape but together define what Phase 3's CLI emits and what every downstream consumer reads. All are frozen Pydantic with `extra="forbid"`. `TransformOutput` (already in S1-02) has no `success` field; `TrustScore` is **strict-AND of binary signals, no LLM** (ADR-0013); `RemediationReport` round-trips on a synthetic happy-path payload as part of this story's acceptance.

## References — where to look

- **Architecture:** `../phase-arch-design.md §"Data model" → Domain models` — the canonical field set for every model in this story.
- **Architecture:** `../phase-arch-design.md §"Data model" → Outputs` — `ValidatorOutput`, `GateOutcome`, `TrustScore` shape.
- **Architecture:** `../phase-arch-design.md §"Component design" #3 (Recipe, RecipeSelector, catalog)` — Recipe field semantics, `ApplyConstraints`, decision-table inputs.
- **Architecture:** `../phase-arch-design.md §"Component design" #12 (TrustScorer)` — strict-AND posture; `TrustScore.binary` is the single load-bearing field.
- **Phase ADRs:** `../ADRs/0004-recipe-selection-structured-triple-not-optional.md` — ADR-0004 — closed-enum `reason` field; the six values are public contract.
- **Phase ADRs:** `../ADRs/0013-confidence-strict-and-of-binary-signals-no-llm.md` — ADR-0013 — `TrustScore` shape; strict-AND of binary signals; no probabilistic blending.
- **Phase ADRs:** `../ADRs/0001-transform-recipe-engine-two-abc-contract.md` — ADR-0001 — `TransformOutput` (already in S1-02) has no `success` field; `RemediationAttempt`/`Report` consume it.
- **Source design:** `../final-design.md §"Synthesis ledger"` rows on `RecipeSelection` triple and `TrustScore` strict-AND.
- **Existing code:** `src/codegenie/transforms/contract.py` (S1-02), `src/codegenie/recipes/contract.py` (S1-03) — these forward-ref `Recipe` and `CveEntry` and `AuditWriter`; this story closes those refs.

## Goal

Land `src/codegenie/recipes/models.py` (`Recipe`, `ApplyConstraints`, `RecipeSelection`) and `src/codegenie/transforms/models.py` (`ValidatorOutput`, `GateOutcome`, `TrustScore`, `RemediationAttempt`, `BranchHandoff`, `RemediationReport`) as frozen Pydantic models with `extra="forbid"`, and trigger `TransformInput.model_rebuild()` + `ApplyContext.model_rebuild()` to resolve the forward refs from S1-02 + S1-03 — proven by a synthetic happy-path `RemediationReport` round-trip test.

## Acceptance criteria

- [ ] `src/codegenie/recipes/models.py` defines `Recipe`, `ApplyConstraints`, `RecipeSelection`. All frozen, `extra="forbid"`.
- [ ] `Recipe` fields: `id: str`, `engine: Literal["ncu","openrewrite"]`, `ecosystem: Literal["npm"]`, `kind: Literal["version_bump"]`, `applies_to: ApplyConstraints`, `params: dict`, `declared_inputs: list[str]`, `digest: str`, `priority: int = 100`.
- [ ] `ApplyConstraints` fields: `ecosystem: Literal["npm"]`, `languages: list[str]`, `package_glob: str | None`, `cve_patterns: list[str] = ["*"]`, `semver_range_predicate: str | None`. (`cve_patterns` is the same field name S1-08 adds to the Skills `ApplyConstraints` — naming consistency is deliberate.)
- [ ] `RecipeSelection` fields: `recipe: Recipe | None`, `reason: Literal["matched","no_engine","range_break","peer_dep_conflict","unsupported_dialect","catalog_miss"]`, `diagnostics: dict`. The `reason` `Literal` enum is closed at exactly six values.
- [ ] When `reason == "matched"`, `recipe` is **non-None**; when `reason != "matched"`, `recipe` is `None`. Enforced by a Pydantic `model_validator` (mode="after"); a model-validation test pins both directions.
- [ ] `src/codegenie/transforms/models.py` defines `ValidatorOutput`, `GateOutcome`, `TrustScore`, `RemediationAttempt`, `BranchHandoff`, `RemediationReport`. All frozen, `extra="forbid"`.
- [ ] `ValidatorOutput` fields per `phase-arch-design.md §"Data model" → Outputs`: `name`, `passed: bool`, `stdout_path: Path`, `stderr_path: Path`, `duration_ms: int`, `confidence: Literal["high","medium","low"]`, `warnings: list[str]`, `errors: list[str]`, `signals: dict`, `requires_network: bool`.
- [ ] `GateOutcome` fields: `green: bool`, `confidence: Literal["high","medium","low"]`, `validators: list[ValidatorOutput]`, `signal_escalate: bool`, `trust_score: TrustScore`.
- [ ] `TrustScore` fields: `binary: bool`, `confidence: Literal["high","medium","low"]`, `detail: dict` (`signal name -> bool`/numeric). Docstring explicitly cites ADR-0013: "strict-AND of binary signals; no LLM-derived confidence."
- [ ] `RemediationAttempt` fields: `run_id`, `repo_root: Path`, `cve_id: str`, `started_at: datetime`, `ended_at: datetime | None`, `transform_output: TransformOutput | None`, `gate_outcome: GateOutcome | None`, `branch_handoff: BranchHandoff | None`, `exit_code: int`.
- [ ] `BranchHandoff` fields: `branch_name: str`, `head_sha: str`, `files_changed: list[Path]`, `diff_path: Path`.
- [ ] `RemediationReport` fields: `attempt: RemediationAttempt`, `audit_path: Path`, `diff_path: Path | None`, `raw_dir: Path`, `confidence_summary: dict`.
- [ ] After defining models, the story calls `TransformInput.model_rebuild()` and `ApplyContext.model_rebuild()` from `recipes/models.py` (or a dedicated `forward_refs.py` module loaded at package import) so the forward refs in S1-02 + S1-03 resolve. Snapshot files from S1-02 + S1-03 are regenerated **once** to include the now-resolved schemas, and the snapshot tests pass.
- [ ] `tests/unit/recipes/test_models.py` covers (a) `RecipeSelection.reason` accepts exactly six values and rejects a seventh, (b) `recipe`-null-iff-`reason`-non-"matched" invariant, (c) `Recipe.priority` defaults to 100, (d) `ApplyConstraints.cve_patterns` defaults to `["*"]`, (e) `extra="forbid"` rejects an unknown field on every model.
- [ ] `tests/unit/transforms/test_models.py` covers (a) `TrustScore.binary` round-trips, (b) `RemediationReport` round-trips on a synthetic happy-path payload (construct → `model_dump()` → `model_validate()` → equal), (c) every model in this story rejects `extra="forbid"`.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on touched files.

## Implementation outline

1. Write `tests/unit/recipes/test_models.py` red — `from codegenie.recipes.models import Recipe, ApplyConstraints, RecipeSelection` ImportErrors.
2. Write `tests/unit/transforms/test_models.py` red — same for transforms/models.
3. Implement `src/codegenie/recipes/models.py`:
   - `ApplyConstraints` (base data class — `Recipe` references it).
   - `Recipe`.
   - `RecipeSelection` with `model_validator(mode="after")` enforcing the recipe-null-iff-reason invariant: when `reason == "matched"`, `recipe is not None`; otherwise `recipe is None`. Validation error raised on mismatch.
4. Implement `src/codegenie/transforms/models.py`:
   - `ValidatorOutput`, `TrustScore`, `GateOutcome`, `BranchHandoff`, `RemediationAttempt`, `RemediationReport`. Define in dependency order so forward refs are minimal.
5. Add a top-of-package `forward_refs.py` module under `src/codegenie/transforms/__init__.py` (or directly in `__init__.py`) that imports `Recipe`, `RecipeApplication`, `ApplyContext`, `CveEntry` (S2-01 will provide this — until then, define a placeholder `CveEntry` stub in `transforms/cve/models.py` that this story creates; S2-01 will replace its body) and calls `TransformInput.model_rebuild()` + `ApplyContext.model_rebuild()`.
6. Regenerate the S1-02 + S1-03 snapshot JSON files once (now that forward refs are concrete) and commit. The S1-02 and S1-03 snapshot tests pass against the regenerated snapshots.
7. Run `ruff format`, `ruff check`, `mypy --strict`, `pytest tests/unit/`.

## TDD plan — red / green / refactor

### Red — failing test first

Test file paths: `tests/unit/recipes/test_models.py`, `tests/unit/transforms/test_models.py`.

```python
# tests/unit/recipes/test_models.py
import pytest
from pydantic import ValidationError
from codegenie.recipes.models import Recipe, ApplyConstraints, RecipeSelection

def test_recipe_selection_reason_enum_is_closed_at_six_values():
    # acceptable values: matched, no_engine, range_break,
    #                    peer_dep_conflict, unsupported_dialect, catalog_miss
    # a seventh raises ValidationError — the closed-enum contract Phase 4 reads
    ...

def test_recipe_selection_matched_requires_recipe_non_null():
    # reason="matched" without a recipe is a programmer bug; the model rejects it
    ...

def test_recipe_selection_non_matched_requires_recipe_null():
    # reason="no_engine" with a recipe set is a programmer bug; the model rejects it
    ...

def test_apply_constraints_cve_patterns_defaults_to_star():
    # matches Skills frontmatter default — naming + default deliberately aligned
    assert ApplyConstraints(ecosystem="npm", languages=["js"]).cve_patterns == ["*"]

def test_recipe_rejects_unknown_field():
    # extra="forbid" — Phase 3 contract surface is closed
    with pytest.raises(ValidationError):
        Recipe(id="r", engine="ncu", ecosystem="npm", kind="version_bump", ...,
               unknown_field=42)
```

```python
# tests/unit/transforms/test_models.py
def test_remediation_report_round_trips_on_happy_path_payload():
    # construct → model_dump(mode="json") → model_validate() → deep-equal
    # Pin the closed Phase 3 RemediationReport schema
    ...

def test_trust_score_binary_is_a_required_bool():
    # ADR-0013: TrustScore is strict-AND of binary signals
    ...

def test_validator_output_requires_network_is_required_bool():
    # ADR-0005: gate.signal_escalate routes off this field
    ...

def test_gate_outcome_signal_escalate_is_required_bool():
    # Phase 5 wraps gate logic; reads this field
    ...
```

### Green — make it pass

- Define the models in dependency order. Use `Literal` for enum-like fields. Use `model_config = ConfigDict(extra="forbid", frozen=True)` on every model.
- `RecipeSelection.model_validator(mode="after")`:
  ```
  def _enforce_match_invariant(self) -> Self:
      if self.reason == "matched" and self.recipe is None: raise ValueError(...)
      if self.reason != "matched" and self.recipe is not None: raise ValueError(...)
      return self
  ```
- Wire the `model_rebuild` calls so the S1-02 + S1-03 snapshot tests find concrete schemas. Regenerate the snapshot JSONs in the same commit.

### Refactor — clean up

- Docstring on each model explicitly cites the ADR that locks its field set (`ADR-0001` on `RemediationAttempt`, `ADR-0004` on `RecipeSelection`, `ADR-0013` on `TrustScore`).
- `__all__` on both `models.py` files lists exactly the public names.
- `mypy --strict` clean — `Literal` types preserved through serialization round-trip.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/recipes/models.py` | `Recipe`, `ApplyConstraints`, `RecipeSelection` |
| `src/codegenie/transforms/models.py` | `ValidatorOutput`, `TrustScore`, `GateOutcome`, `BranchHandoff`, `RemediationAttempt`, `RemediationReport` |
| `src/codegenie/transforms/__init__.py` | Wire `model_rebuild()` calls; update `__all__` |
| `src/codegenie/recipes/__init__.py` | Re-export `Recipe`, `RecipeSelection`, `ApplyConstraints` |
| `src/codegenie/transforms/cve/__init__.py` | Stub `CveEntry` so forward refs resolve (S2-01 replaces the body) |
| `src/codegenie/transforms/cve/models.py` | Stub `CveEntry`/`AffectedRange`/`Provenance`/`Severity`/`Reference` (S2-01 replaces) |
| `tests/unit/recipes/test_models.py` | Closed-enum + invariant tests |
| `tests/unit/transforms/test_models.py` | Round-trip + invariant tests |
| `tests/unit/transforms/snapshots/transform_contract_v0_3_0.json` | Regenerate with resolved forward refs |
| `tests/unit/recipes/snapshots/recipe_engine_contract_v0_3_0.json` | Regenerate with resolved forward refs |

## Out of scope

- **CVE model field set + provenance discipline + parsers** — S2-01 / S2-02–S2-04 (this story only stubs `CveEntry` so the forward refs resolve).
- **Recipe catalog YAML + selector** — Step 3.
- **Validator implementations** — Step 4 (this story is the typed shape they emit; the functions live in `transforms/validation/`).
- **`TrustScorer` logic** — Step 5; this story is just the typed result shape.
- **`PatchBranchWriter` implementation** — Step 5; this story is just `BranchHandoff` shape.
- **`AuditWriter` type** — Phase 2 already exports this; consumed by reference in S1-03's `ApplyContext`. No change to Phase 2 code.

## Notes for the implementer

- **The `RecipeSelection.reason` enum is the public contract Phase 4 reads.** ADR-0004's six values are not exhaustive in some abstract sense — they were chosen with Phase 4's "where do we fall back to LLM planning" decision tree in mind. Adding a seventh requires (a) an ADR amendment to ADR-0004, (b) a code change in `recipes/selector.py` to emit it, (c) a Phase 4 ADR documenting how it routes. Same change, same PR. Resist single-word "while we're here" additions.
- **The recipe-null-iff-reason invariant is enforced by a model validator, not a separate check.** Without it, programmers will construct `RecipeSelection(recipe=None, reason="matched", diagnostics={})` and ship a "selected nothing but reported success" bug. The validator catches this at construction.
- **`ApplyConstraints.cve_patterns` is the same field name as `SkillApplies.cve_patterns` added in S1-08.** Both default to `["*"]`. The match logic that consumes them (S3-09 selector) is parallel: a recipe matches `cve_id` if `any(fnmatch(cve_id, p) for p in cve_patterns)`. Naming and default semantics are deliberately aligned so the selector code is uniform.
- **`TrustScore.detail: dict`** is intentionally typed as `dict`, not `dict[str, bool | float | str]`. The detail dict is opaque to the typed boundary — its keys are signal names that vary per gate; Phase 5 will tighten it if a unifying schema emerges. Document this in the docstring.
- **Snapshot regeneration.** This story is the **only** time the S1-02 + S1-03 snapshots are regenerated as a planned activity. Once concrete forward refs resolve, the schemas are locked. Any future change to `Recipe`, `RecipeApplication`, etc. requires an ADR amendment and a new versioned snapshot file alongside (or replacing) the v0.3.0 file.
- **`RemediationReport` round-trip test.** This is the single most useful test in the story — it pins the entire Phase 3 output schema. A synthetic happy-path payload is small (one transform output, one gate outcome with one validator, one branch handoff); construct it inline in the test and exercise both `model_dump(mode="json")` (for the YAML emitter in Step 5) and `model_validate()` (for any reader).
- The `CveEntry` stub created here is replaced in S2-01. The stub's docstring must say "STUB — replaced by S2-01; do not import outside S2 code paths" so a future reader sees the seam clearly.
- Do not import `pydantic.v1`. Use pydantic v2.
