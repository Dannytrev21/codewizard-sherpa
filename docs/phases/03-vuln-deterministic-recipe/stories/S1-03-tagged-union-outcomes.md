# Story S1-03 — Tagged-union outcome types

**Step:** Step 1 — Scaffold packages, domain primitives, sum types, and structural CI fences
**Status:** Ready
**Effort:** M
**Depends on:** S1-01 (newtypes the outcome payloads carry: `TransformId`, `SignalKind`, `PluginId`, `RecipeId`, `WorkflowId`)
**ADRs honored:** ADR-0010 (tagged-union sum types on every state machine; `extra="forbid"`; `match` + `assert_never`), ADR-0001 (Phase-5 wraps `RemediationOutcome` and `RecipeOutcome` — the discriminated-union shape is the contract)

## Context

Production ADR-0033 rejects booleans-for-state and `(passed: bool, error: str | None)`-style returns; ADR-0010 carries the rule into Phase 3 with concrete unions for every outcome the orchestrator, recipe engine, adapter, and subgraph node can produce. The critic flagged this as the load-bearing missing piece in `critique.md §Best-practices design §Open Q #5` — `RecipeProtocol.applies(...) -> bool` cannot carry the `plan` the engine needs nor the `reason` the orchestrator needs. This story ships the five Pydantic discriminated unions every later Phase-3 module dispatches on: `RecipeOutcome`, `RemediationOutcome`, `NodeTransition`, `AdapterConfidence`, `Applicability` — each via `Field(discriminator="kind")` so mypy + Pydantic both enforce exhaustiveness and `extra="forbid"` rejects accidental field drift.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C4` — `RecipeOutcome` variants (`Applied | Skipped | NotApplicable | Failed`); `Applied.transform: Transform` is the Phase-5 wrap target.
  - `../phase-arch-design.md §Component design C8` — `AdapterConfidence` (`Trusted | Degraded(reason) | Unavailable(reason)`); `BundleBuilder` reads this to trigger deterministic serial fallback.
  - `../phase-arch-design.md §Scenarios §Scenario C` — `RemediationOutcome.Validated(passed=False)` is terminal in Phase 3 (Phase 5 wraps with retry).
  - `../phase-arch-design.md §Gap analysis Gap 1` — `NodeTransition` (`Advance | ShortCircuit | Escalate`) is the SubgraphNode return contract; S6-03 consumes this story's union.
- **Phase ADRs:**
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — Decision §3 enumerates exactly the unions this story lands; Consequences §`extra="forbid"` + `frozen=True` on every Pydantic model is mandatory.
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` — `RecipeOutcome.NotApplicable(reason)` and `RemediationOutcome.*` shapes are the Phase-5 wrap surface; renames break the contract snapshot test (S6-06).
- **Existing code:**
  - `src/codegenie/output/sanitizer.py` and `src/codegenie/probes/base.py` — Phase 0/2 precedent for `model_config = ConfigDict(frozen=True, extra="forbid")` + `Field(discriminator=...)`.
  - `src/codegenie/probes/layer_d/` — recent `match` + `assert_never` examples for closed unions; mirror the convention.

## Goal

Land `src/codegenie/transforms/outcomes.py` with five Pydantic discriminated unions (`RecipeOutcome`, `RemediationOutcome`, `NodeTransition`, `AdapterConfidence`, `Applicability`), each `frozen=True` + `extra="forbid"`, with a `Discriminator("kind")` and one exhaustiveness test per union using `match` + `assert_never`.

## Acceptance criteria

- [ ] `src/codegenie/transforms/__init__.py` exists (empty package marker for the new `codegenie.transforms.*` namespace).
- [ ] `src/codegenie/transforms/outcomes.py` defines five discriminated unions; each variant is a `BaseModel` subclass with `model_config = ConfigDict(frozen=True, extra="forbid")` and a `kind: Literal["<name>"]` field. The umbrella alias uses `Annotated[Union[...], Field(discriminator="kind")]`.
- [ ] `RecipeOutcome` variants: `Applied(kind="applied", transform_id: TransformId, plugin_id: PluginId, recipe_id: RecipeId)`; `Skipped(kind="skipped", reason: SkipReason, plugin_id: PluginId)`; `NotApplicable(kind="not_applicable", reason: NotApplicableReason)`; `Failed(kind="failed", error: RecipeError)`. `NotApplicableReason` is a `Literal["PEER_DEP_CONFLICT","MAJOR_BUMP_REFUSE","OVERRIDES_AMBIGUOUS","RECIPE_CATALOG_MISS","ALL_RECIPES_NOT_APPLICABLE"]`.
- [ ] `RemediationOutcome` variants: `Validated(kind="validated", transform_id, trust_outcome_passed: bool, failing: list[SignalKind])`; `RequiresHumanReview(kind="requires_human_review", reason: HumanReviewReason)`; `NotApplicable(kind="not_applicable", reason: NotApplicableReason)`; `Failed(kind="failed", error: RemediationError)`.
- [ ] `NodeTransition` variants (Gap 1): `Advance(kind="advance", state: dict[str, str | int | bool | float])`; `ShortCircuit(kind="short_circuit", outcome: RemediationOutcome)`; `Escalate(kind="escalate", reason: EscalationReason)`. Note `state` is primitives-only per ADR-0010 (no `Any`).
- [ ] `AdapterConfidence` variants: `Trusted(kind="trusted")`; `Degraded(kind="degraded", reason: DegradationReason)`; `Unavailable(kind="unavailable", reason: UnavailabilityReason)`.
- [ ] `Applicability` variants: `Applies(kind="applies", plan: ApplicationPlan)` where `ApplicationPlan` is a frozen `BaseModel` placeholder (Phase 3 fills concrete fields when recipes land); `NotApplies(kind="not_applies", reason: NotApplicableReason)`.
- [ ] `tests/unit/transforms/test_outcomes.py` covers: construct each variant; reject extra field (`extra="forbid"`); reject mutation (`frozen=True`); JSON round-trip via `model_validate_json(o.model_dump_json())` lands the same `kind`.
- [ ] `tests/unit/transforms/test_exhaustiveness.py` exists with one `match` + `assert_never` test per union that explicitly exercises every variant and would fail at mypy time if a new variant were added without a corresponding `case`.
- [ ] `mypy --strict src/codegenie/transforms/` clean.
- [ ] `ruff check`, `ruff format --check` clean.
- [ ] TDD plan's red test exists, committed, green.

## Implementation outline

1. Create `src/codegenie/transforms/__init__.py` (one-line docstring naming the contract surface ADR-0001 freezes).
2. Create `src/codegenie/transforms/outcomes.py`. Use Pydantic v2 `Discriminator("kind")` per the v2 docs; pattern is `Annotated[Union[A, B, C], Discriminator("kind")]` re-exported as the union alias.
3. Define inner `Literal` reason taxonomies as module-level type aliases: `NotApplicableReason`, `SkipReason`, `EscalationReason`, `HumanReviewReason`, `DegradationReason`, `UnavailabilityReason`. Keep them small + named so Phase 4 can extend additively (`NotApplicableReason` grows new literals; existing consumers' `match` arms still cover the Phase-3 reasons).
4. `RecipeError`, `RemediationError` are themselves small Pydantic models (`error_id: ErrorId`, `message: str`, optional `details: dict[str, str | int | bool | float]`).
5. Add `tests/unit/transforms/__init__.py` + `test_outcomes.py` + `test_exhaustiveness.py`.
6. Run `mypy --strict src/codegenie/transforms/` + `pytest tests/unit/transforms/ -v`.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/unit/transforms/test_outcomes.py`

```python
import pytest
from pydantic import ValidationError

from codegenie.transforms.outcomes import (
    RecipeOutcome, Applied, NotApplicable, Failed,
    RemediationOutcome, Validated,
    AdapterConfidence, Trusted, Degraded,
    Applicability, Applies, NotApplies,
    NodeTransition, Advance, ShortCircuit, Escalate,
)
from codegenie.types.identifiers import TransformId, PluginId, RecipeId


def test_applied_constructs_and_is_frozen():
    a = Applied(
        kind="applied",
        transform_id=TransformId("a" * 64),
        plugin_id=PluginId("vulnerability-remediation--node--npm"),
        recipe_id=RecipeId("NpmLockfileSemverBumpRecipe"),
    )
    with pytest.raises(ValidationError):
        a.transform_id = TransformId("b" * 64)  # frozen


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        NotApplicable(kind="not_applicable", reason="PEER_DEP_CONFLICT", oops="x")  # type: ignore[call-arg]


def test_discriminator_round_trip():
    a: RecipeOutcome = Applied(
        kind="applied",
        transform_id=TransformId("a" * 64),
        plugin_id=PluginId("vuln--node--npm"),
        recipe_id=RecipeId("R"),
    )
    raw = a.model_dump_json()
    # Validator must pick the right variant from `kind`.
    from pydantic import TypeAdapter
    parsed = TypeAdapter(RecipeOutcome).validate_json(raw)
    assert parsed.kind == "applied"


def test_not_applicable_reason_taxonomy():
    NotApplicable(kind="not_applicable", reason="PEER_DEP_CONFLICT")
    NotApplicable(kind="not_applicable", reason="MAJOR_BUMP_REFUSE")
    with pytest.raises(ValidationError):
        NotApplicable(kind="not_applicable", reason="UNKNOWN_REASON")  # not in Literal


# tests/unit/transforms/test_exhaustiveness.py:

from typing import assert_never

def describe(o: RecipeOutcome) -> str:
    match o:
        case Applied(): return "applied"
        case NotApplicable(): return "not_applicable"
        case Failed(): return "failed"
        case Skipped(): return "skipped"
        case _: assert_never(o)

def test_exhaustiveness_covers_all_variants():
    # If a new RecipeOutcome variant is added without updating `describe`,
    # mypy --strict fails at the assert_never line.
    assert describe(Applied(...)) == "applied"
    # ... etc per variant
```

State why it fails: `ModuleNotFoundError: codegenie.transforms.outcomes` — module doesn't exist.

### Green — minimal pass
- Add `src/codegenie/transforms/__init__.py`.
- Add `src/codegenie/transforms/outcomes.py` with the five unions, their variants, and the discriminator-tagged aliases. Use Pydantic v2 idioms (`ConfigDict`, `model_dump_json`, `TypeAdapter`).

### Refactor
- Re-export the variants + unions from `src/codegenie/transforms/__init__.py` per ADR-0001 §Consequences (Phase 5 imports `from codegenie.transforms import RemediationOutcome`).
- Add docstrings to each variant naming the producer (e.g., `"""Applied — produced by NpmLockfileRecipeEngine on a successful lockfile re-resolve."""`).
- Cover edge cases from §Edge cases: E4 (`PEER_DEP_CONFLICT`), E6 (`MAJOR_BUMP_REFUSE`), E10 (universal-fallback not silent: `HumanReviewReason.NoConcreteMatch`); each appears as a `Literal` member.
- Confirm `assert_never` exhaustiveness fires by writing a deliberately-broken version in a `# type: ignore` block + a mypy check (or a comment naming the line that would fail). The exhaustiveness *test* is for runtime semantics; the *type-time* exhaustiveness is enforced by mypy reading `assert_never`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/__init__.py` | NEW — package marker; re-export the unions (ADR-0001). |
| `src/codegenie/transforms/outcomes.py` | NEW — five discriminated unions + reason `Literal`s + error models. |
| `tests/unit/transforms/__init__.py` | NEW — test package marker. |
| `tests/unit/transforms/test_outcomes.py` | NEW — construct + freeze + extra-rejection + discriminator round-trip. |
| `tests/unit/transforms/test_exhaustiveness.py` | NEW — `match` + `assert_never` per union (S1-05 fence test will assert this file exists and has ≥ 5 such tests). |

## Out of scope

- **`Transform` ABC + `ApplyContext` + `AttemptSummary`** — handled by S1-04. This story ships only the *outcome* unions; the data they carry (`Transform`) is S1-04's surface.
- **`TrustOutcome` + `TrustSignal`** — handled by S6-02 (TrustScorer) under the `transforms/` namespace; not part of Step 1.
- **`JailedSubprocessResult` discriminated union** — handled by S4-01 (`src/codegenie/transforms/sandbox_jail.py`).
- **`PluginResolution = ConcreteResolution | UniversalFallbackResolution`** — handled by S2-04; lives in `src/codegenie/plugins/resolution.py`.
- **`WorkflowInternalEvent` / `WorkflowSpanningEvent`** — handled by S6-01.

## Notes for the implementer

- **Pydantic v2's `Discriminator("kind")` vs. plain `Field(discriminator="kind")`** — both work; the repo's existing convention (check `src/codegenie/output/sanitizer.py` and `src/codegenie/probes/layer_b/`) uses one or the other. Match what's there; surface if neither has a precedent and pick the v2-idiomatic `Annotated[Union[...], Discriminator("kind")]`.
- **`extra="forbid"` is non-negotiable** — ADR-0010 §Consequences and S1-05's `test_no_any_in_plugin_surface.py` will fail otherwise. No `model_config = ConfigDict()` left default.
- **`frozen=True` makes models hashable** — needed for using `RecipeOutcome` as dict keys in some tests; also gives the "no mutation after construction" guarantee callers depend on.
- **`NotApplicableReason` is shared between `RecipeOutcome.NotApplicable` and `RemediationOutcome.NotApplicable`** — define it once, import it in both. Phase 4 will add `LLM_FALLBACK_REQUIRED` etc. additively; the `Literal` grows.
- **`assert_never` from `typing`** (Python 3.11+) — covered by the repo's CI matrix. Always pair with `match` on closed unions; the lint that would catch a missing `case` is mypy seeing the `assert_never` and verifying every variant has an arm.
- **`NodeTransition.Advance.state: dict[str, str | int | bool | float]`** is deliberately primitives-only — ADR-0010 §Consequences forbids `dict[str, Any]` under `transforms/`. If a node genuinely needs richer state, the right move is a new typed payload model, not a dict-of-Any.
- **`ApplicationPlan` is a placeholder Pydantic model** in Phase 3 (one optional `summary: str` field is enough); S5-01's recipe engines flesh out the real fields. Surface this in a code comment so the implementer of S5-01 knows to extend, not redefine.
