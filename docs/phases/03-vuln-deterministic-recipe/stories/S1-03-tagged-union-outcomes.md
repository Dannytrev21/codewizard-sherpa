# Story S1-03 — Tagged-union outcome types

**Step:** Step 1 — Scaffold packages, domain primitives, sum types, and structural CI fences
**Status:** HARDENED
**Effort:** M
**Depends on:** S1-01 (newtypes the outcome payloads carry: `TransformId`, `SignalKind`, `PluginId`, `RecipeId`, `WorkflowId`, `BranchName`, `ErrorId`)
**ADRs honored:** ADR-0010 (tagged-union sum types on every state machine; `extra="forbid"`; `match` + `assert_never`), ADR-0001 (Phase-5 wraps `RemediationOutcome` and `RecipeOutcome` — the discriminated-union shape is the contract)

## Validation notes (2026-05-18)

Hardened by `phase-story-validator`. See `_validation/S1-03-tagged-union-outcomes.md` for the full audit. Block-tier closures:
1. `RemediationOutcome.Validated` field set realigned to arch §Data model line 827 — `(branch: BranchName, report_path: str, passed: bool, failing: list[SignalKind])`. Phase 5 GateRunner reads `branch` and `report_path`; the original story dropped them.
2. `RemediationOutcome.Failed` gained `partial_report_path: str | None = None` (arch line 452 / line 830) — the orchestrator writes a partial `remediation-report.yaml` on failure; the path must be carryable on the outcome.
3. Discriminator-string + JSON-shape pinning tests added — round-trip alone is symmetric under `Applied.kind ↔ Failed.kind` swap or `kind` → `tag` rename; both mutations would silently break every Phase-5 consumer.
4. Literal taxonomies enumerated for `SkipReason`, `EscalationReason`, `HumanReviewReason`, `DegradationReason`, `UnavailabilityReason` (story listed names; ACs did not pin the literal members).
5. Repo-uniform conventions pinned: `kind: Literal["..."] = "..."` default-value form; `Annotated[A | B | C, Field(discriminator="kind")]` (not `Discriminator(...)`); module-purity AST scan; `model_construct` source-scan absence; `__all__` exact-set; subprocess-mypy negative meta-test for `assert_never` enforcement.

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

### Structure

- [ ] **AC-1** `src/codegenie/transforms/__init__.py` exists and re-exports the union aliases, every variant class, the reason `Literal` aliases, and the error models per ADR-0001 §Consequences.
- [ ] **AC-2** `src/codegenie/transforms/outcomes.py` defines five discriminated unions. Every variant is a `BaseModel` subclass with `model_config = ConfigDict(frozen=True, extra="forbid")`. Every variant has a `kind: Literal["<name>"] = "<name>"` field (default-value form per the repo convention in `src/codegenie/indices/freshness.py:45`, `src/codegenie/probes/_shared/scanner_outcome.py:117`). Every umbrella alias has the exact shape `Annotated[VariantA | VariantB | ..., Field(discriminator="kind")]` (no `Union[...]` literal; no `Discriminator(...)` callable form — repo precedent: 5 files in `src/codegenie/`).

### Variant shapes (each row is one AC the test plan covers)

- [ ] **AC-3 `RecipeOutcome`** — four variants:
  - `Applied(kind="applied", transform_id: TransformId, plugin_id: PluginId, recipe_id: RecipeId)` — `transform_id` denormalization rationale: `Transform` ABC ships in S1-04; this story cannot import `Transform` (circular). S1-04's `Transform.transform_id` field closes the lookup loop.
  - `Skipped(kind="skipped", reason: SkipReason, plugin_id: PluginId)`.
  - `NotApplicable(kind="not_applicable", reason: NotApplicableReason)`.
  - `Failed(kind="failed", error: RecipeError)`.
- [ ] **AC-4 `RemediationOutcome`** — four variants (arch §Data model line 825–830 + §line 452 carry the full field set; the original story dropped `branch`, `report_path`, `partial_report_path`):
  - `Validated(kind="validated", branch: BranchName, report_path: str, passed: bool, failing: list[SignalKind])`. `report_path` is `str` now; S4-01 widens to `SandboxedPath` via `field_validator`. `passed` / `failing` are the flat denormalization of `TrustOutcome.passed` / `TrustOutcome.failing` — S6-02 (`TrustScorer`) widens additively when `TrustOutcome` lands; field-rename is forbidden by ADR-0001 contract-snapshot test.
  - `RequiresHumanReview(kind="requires_human_review", reason: HumanReviewReason, handoff_path: str | None = None)`.
  - `NotApplicable(kind="not_applicable", reason: NotApplicableReason)`.
  - `Failed(kind="failed", error: RemediationError, partial_report_path: str | None = None)`. `partial_report_path` is None when failure occurs before the report path is allocated (arch line 452).
- [ ] **AC-5 `NodeTransition`** (Gap 1 fix per arch §Gap analysis line 1154) — three variants:
  - `Advance(kind="advance", state: dict[str, str | int | bool | float])` — primitive-value-only per ADR-0010 §Consequences (no `Any`, no `list[str]`, no nested dicts). Arch line 1154 typo says `ShortCircuit(outcome: RecipeOutcome)`; story is correct with `RemediationOutcome` (the orchestrator-outer-loop type; arch §Edge cases line 899–904 confirms).
  - `ShortCircuit(kind="short_circuit", outcome: RemediationOutcome)`.
  - `Escalate(kind="escalate", reason: EscalationReason)`.
- [ ] **AC-6 `AdapterConfidence`** — three variants:
  - `Trusted(kind="trusted")`.
  - `Degraded(kind="degraded", reason: DegradationReason)`.
  - `Unavailable(kind="unavailable", reason: UnavailabilityReason)`.
- [ ] **AC-7 `Applicability`** — two variants:
  - `Applies(kind="applies", plan: ApplicationPlan)` where `ApplicationPlan(BaseModel)` has `model_config = ConfigDict(frozen=True, extra="forbid")` and `summary: str | None = None` (S5-01 recipe engines widen additively).
  - `NotApplies(kind="not_applies", reason: NotApplicableReason)`.

### Reason taxonomies (every literal set pinned)

- [ ] **AC-7a `NotApplicableReason`** = `Literal["PEER_DEP_CONFLICT", "MAJOR_BUMP_REFUSE", "OVERRIDES_AMBIGUOUS", "RECIPE_CATALOG_MISS", "ALL_RECIPES_NOT_APPLICABLE"]`. Defined exactly once in `outcomes.py`; imported by both `RecipeOutcome.NotApplicable` and `RemediationOutcome.NotApplicable`. Test asserts identity: a single `is` check across both producers.
- [ ] **AC-7b `SkipReason`** = `Literal["plugin_disabled", "registry_skipped"]` — minimal extensible set; Phase 4+ adds members additively.
- [ ] **AC-7c `EscalationReason`** = `Literal["plugin_extends_cycle", "manifest_rejected", "capability_missing"]`.
- [ ] **AC-7d `HumanReviewReason`** = `Literal["no_concrete_match", "trust_outcome_failed", "policy_violation_unrecoverable"]` (arch line 1075 + §E10 pin `no_concrete_match` for universal-fallback exhaustion).
- [ ] **AC-7e `DegradationReason`** = `Literal["timeout", "partial_results", "rate_limited"]`.
- [ ] **AC-7f `UnavailabilityReason`** = `Literal["binary_missing", "io_error", "unsupported_version"]`.

### Error models

- [ ] **AC-7g** `RecipeError` and `RemediationError` are each frozen `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` and fields `error_id: ErrorId`, `message: str` (max-length 4096 enforced by `field_validator`), and optional `details: dict[str, str | int | bool | float] | None = None`.

### Invariants

- [ ] **AC-7h** `RemediationOutcome.Validated` enforces the trust invariant `passed == (len(failing) == 0)` via `model_validator(mode="after")`. Constructing `Validated(passed=True, failing=[SignalKind("tests")])` raises `ValidationError`. (Make-illegal-states-unrepresentable per ADR-0010 §Pattern fit.)

### Test plan (each row is one AC pinned by a named test)

- [ ] **AC-8a** `tests/unit/transforms/test_outcomes.py::test_construct_and_round_trip` is **parametrized** over a fixture list containing every one of the 17 variants. For each instance: construct OK; `TypeAdapter(<umbrella>).dump_json(inst)` round-trips back to `==` and `type(decoded) is type(inst)`; nested-discriminator preservation when applicable (e.g., `ShortCircuit(outcome=Validated(...))` round-trip preserves `Validated` concrete type).
- [ ] **AC-8b** `test_outcomes.py::test_extra_field_rejected` — parametrized over every variant; `<Variant>.model_validate({"kind": "...", "<extra>": "x", ...})` raises `ValidationError`.
- [ ] **AC-8c** `test_outcomes.py::test_frozen_after_construction` — parametrized over every variant; mutation raises `ValidationError`.
- [ ] **AC-8d** `test_outcomes.py::test_discriminator_strings_are_exactly_pinned` — enumerates all 19 variant discriminator strings (4 + 4 + 3 + 3 + 2 + 3 reason-Literal "validated"/"requires_human_review"/"not_applicable"/"failed"; duplicates collapsed). Mirrors `tests/unit/indices/test_freshness.py:55`. Rationale: a symmetric `Applied.kind ↔ Failed.kind` swap is round-trip-stable but breaks every Phase-5 consumer.
- [ ] **AC-8e** `test_outcomes.py::test_json_shape_pinned` — for each variant, asserts `inst.model_dump(mode="json")["kind"]` equals the expected literal and asserts the full `model_dump(mode="json")` key-set equality (catches `kind` → `tag` rename). Mirrors `test_freshness.py:70`.
- [ ] **AC-8f** `test_outcomes.py::test_top_level_unknown_kind_rejected` — parametrized over the five umbrella unions; `TypeAdapter(U).validate_python({"kind": "bogus_kind"})` raises `ValidationError`.
- [ ] **AC-8g** `test_outcomes.py::test_not_applicable_reason_is_single_source_of_truth` — `from codegenie.transforms.outcomes import NotApplicableReason as A`; same alias is the type of `RecipeOutcome.NotApplicable.model_fields["reason"].annotation` AND `RemediationOutcome.NotApplicable.model_fields["reason"].annotation`. Identity check (`is`).
- [ ] **AC-8h** `test_outcomes.py::test_validated_passed_failing_invariant` — `Validated(passed=True, failing=[])` OK; `Validated(passed=False, failing=[])` raises; `Validated(passed=True, failing=[SignalKind("tests")])` raises; `Validated(passed=False, failing=[SignalKind("tests")])` OK.
- [ ] **AC-8i** `test_outcomes.py::test_advance_state_primitives_only` — `Advance(state={"k": 1})` OK; `Advance(state={"k": "v"})` OK; `Advance(state={"k": True})` OK; `Advance(state={"k": [1, 2]})` raises; `Advance(state={"k": {"nested": 1}})` raises.
- [ ] **AC-9** `tests/unit/transforms/test_exhaustiveness.py` defines **five named test functions** — `test_exhaustiveness_recipe_outcome`, `test_exhaustiveness_remediation_outcome`, `test_exhaustiveness_node_transition`, `test_exhaustiveness_adapter_confidence`, `test_exhaustiveness_applicability` — each exercises every variant of its union via `match` + `assert_never(unexpected)` and collects a `seen: set[str]` to assert full coverage at runtime. Mirrors `test_freshness.py:111-130`.
- [ ] **AC-9a** `tests/unit/transforms/test_outcomes_mypy_negative.py` ships a subprocess-mypy meta-test: writes a temp module that `match`-es over `RecipeOutcome` with one variant arm intentionally missing and an `assert_never(unexpected)` line, subprocess-invokes `mypy --strict <tmp>`, asserts non-zero exit and that the expected error substring (`Argument 1 to "assert_never"`) appears. This is the type-time enforcement that makes the type-system catch Phase 4's silent `Union` widening.

### Module-purity / Open-Closed fences

- [ ] **AC-10a** `__all__` in `src/codegenie/transforms/outcomes.py` is an exact-set equality: variant classes (17) + umbrella aliases (5) + reason `Literal` aliases (6) + error models (2) + `ApplicationPlan` (1) = 31 names. `set(outcomes.__all__) == EXPECTED_NAMES`. Mirrors S1-01's exact-set discipline.
- [ ] **AC-10b** `tests/unit/transforms/test_outcomes_purity.py::test_imports_are_kernel_only` — AST source-scan of `outcomes.py`; allowed import set is exactly `{__future__, typing, pydantic, codegenie.types.identifiers, codegenie.types.errors}`. Anything else fails.
- [ ] **AC-10c** `test_outcomes_purity.py::test_no_model_construct_in_outcomes` — `"model_construct" not in Path(outcomes.__file__).read_text()`. Mirrors `tests/unit/indices/test_freshness.py:174`.

### Bar ACs

- [ ] **AC-11** `mypy --strict src/codegenie/transforms/` clean.
- [ ] **AC-12** `ruff check`, `ruff format --check` clean on touched files.
- [ ] **AC-13** TDD plan's red test (`test_construct_and_round_trip` parametrized fixture) exists, was committed in a failing state, is now green.

## Implementation outline

1. Create `src/codegenie/transforms/__init__.py` (one-line docstring naming the contract surface ADR-0001 freezes; re-exports per AC-10a).
2. Create `src/codegenie/transforms/outcomes.py`. Use the repo-idiomatic `Annotated[VariantA | VariantB | ..., Field(discriminator="kind")]` form (5 existing files use it; do NOT use the callable `Discriminator(...)` form). Every variant declares `kind: Literal["..."] = "..."` (default value), `model_config = ConfigDict(frozen=True, extra="forbid")`.
3. Define inner `Literal` reason taxonomies as module-level type aliases (members pinned by AC-7a..AC-7f): `NotApplicableReason`, `SkipReason`, `EscalationReason`, `HumanReviewReason`, `DegradationReason`, `UnavailabilityReason`. Keep them small + named so Phase 4 can extend additively.
4. `RecipeError`, `RemediationError` are small Pydantic models per AC-7g (`error_id: ErrorId`, `message: str` capped at 4096 chars via `field_validator`, optional `details: dict[str, str | int | bool | float] | None`).
5. `ApplicationPlan` Pydantic placeholder per AC-7 (`summary: str | None = None`).
6. `Validated` carries a `model_validator(mode="after")` enforcing the `passed == (len(failing) == 0)` invariant (AC-7h).
7. Pin `__all__` to the exact 31-name set per AC-10a.
8. Add `tests/unit/transforms/__init__.py` + `test_outcomes.py` (parametrized fixtures over all 17 variants) + `test_exhaustiveness.py` (5 named tests) + `test_outcomes_purity.py` (module-purity AST scan + `model_construct` absence) + `test_outcomes_mypy_negative.py` (subprocess-mypy fence per AC-9a).
9. Run `mypy --strict src/codegenie/transforms/` + `pytest tests/unit/transforms/ -v`.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/unit/transforms/test_outcomes.py`

```python
from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.transforms.outcomes import (
    # Umbrella unions
    RecipeOutcome, RemediationOutcome, NodeTransition,
    AdapterConfidence, Applicability,
    # RecipeOutcome variants
    Applied, Skipped, NotApplicable as RecipeNotApplicable, Failed as RecipeFailed,
    # RemediationOutcome variants
    Validated, RequiresHumanReview,
    NotApplicable as RemediationNotApplicable, Failed as RemediationFailed,
    # NodeTransition variants
    Advance, ShortCircuit, Escalate,
    # AdapterConfidence variants
    Trusted, Degraded, Unavailable,
    # Applicability variants
    Applies, NotApplies,
    # Reason literals + payload types
    NotApplicableReason, SkipReason, EscalationReason,
    HumanReviewReason, DegradationReason, UnavailabilityReason,
    ApplicationPlan, RecipeError, RemediationError,
)
from codegenie.types.identifiers import (
    TransformId, PluginId, RecipeId, BranchName, SignalKind, ErrorId,
)

# 17-variant concrete fixture list. Used by every parametrized test below.
ALL_VARIANTS = [
    Applied(transform_id=TransformId("a" * 64),
            plugin_id=PluginId("vuln--node--npm"),
            recipe_id=RecipeId("R1")),
    Skipped(reason="plugin_disabled", plugin_id=PluginId("vuln--node--npm")),
    RecipeNotApplicable(reason="PEER_DEP_CONFLICT"),
    RecipeFailed(error=RecipeError(error_id=ErrorId("e.1"), message="boom")),
    Validated(branch=BranchName("fix/cve-1"),
              report_path="/jail/report.yaml",
              passed=True, failing=[]),
    RequiresHumanReview(reason="no_concrete_match"),
    RemediationNotApplicable(reason="RECIPE_CATALOG_MISS"),
    RemediationFailed(error=RemediationError(error_id=ErrorId("r.1"), message="b")),
    Advance(state={"k": 1}),
    ShortCircuit(outcome=RemediationNotApplicable(reason="PEER_DEP_CONFLICT")),
    Escalate(reason="capability_missing"),
    Trusted(),
    Degraded(reason="timeout"),
    Unavailable(reason="binary_missing"),
    Applies(plan=ApplicationPlan(summary="bump express")),
    NotApplies(reason="MAJOR_BUMP_REFUSE"),
]

# Map each variant to its parent umbrella union for round-trip testing.
UNION_FOR = {
    Applied: RecipeOutcome, Skipped: RecipeOutcome,
    RecipeNotApplicable: RecipeOutcome, RecipeFailed: RecipeOutcome,
    Validated: RemediationOutcome, RequiresHumanReview: RemediationOutcome,
    RemediationNotApplicable: RemediationOutcome,
    RemediationFailed: RemediationOutcome,
    Advance: NodeTransition, ShortCircuit: NodeTransition, Escalate: NodeTransition,
    Trusted: AdapterConfidence, Degraded: AdapterConfidence,
    Unavailable: AdapterConfidence,
    Applies: Applicability, NotApplies: Applicability,
}


@pytest.mark.parametrize("inst", ALL_VARIANTS)
def test_construct_and_round_trip(inst):
    """AC-8a — every variant round-trips through its umbrella union."""
    union = UNION_FOR[type(inst)]
    adapter = TypeAdapter(union)
    decoded = adapter.validate_json(adapter.dump_json(inst))
    assert decoded == inst
    assert type(decoded) is type(inst)


@pytest.mark.parametrize("inst", ALL_VARIANTS)
def test_extra_field_rejected(inst):
    """AC-8b — every variant rejects extra fields."""
    payload = {**inst.model_dump(), "_oops": "x"}
    with pytest.raises(ValidationError):
        type(inst).model_validate(payload)


@pytest.mark.parametrize("inst", ALL_VARIANTS)
def test_frozen_after_construction(inst):
    """AC-8c — every variant is frozen."""
    with pytest.raises(ValidationError):
        # try mutating the discriminator
        inst.kind = "bogus"  # type: ignore[misc]


def test_discriminator_strings_are_exactly_pinned():
    """AC-8d — a symmetric kind-swap would pass round-trip; pin the strings."""
    expected: dict[type, str] = {
        Applied: "applied", Skipped: "skipped",
        RecipeNotApplicable: "not_applicable", RecipeFailed: "failed",
        Validated: "validated", RequiresHumanReview: "requires_human_review",
        RemediationNotApplicable: "not_applicable",
        RemediationFailed: "failed",
        Advance: "advance", ShortCircuit: "short_circuit", Escalate: "escalate",
        Trusted: "trusted", Degraded: "degraded", Unavailable: "unavailable",
        Applies: "applies", NotApplies: "not_applies",
    }
    for inst in ALL_VARIANTS:
        assert inst.kind == expected[type(inst)]


@pytest.mark.parametrize("inst", ALL_VARIANTS)
def test_json_shape_pinned(inst):
    """AC-8e — `kind` → `tag` rename would pass round-trip; pin the JSON shape."""
    dump = inst.model_dump(mode="json")
    assert "kind" in dump
    assert dump["kind"] == inst.kind


@pytest.mark.parametrize(
    "union", [RecipeOutcome, RemediationOutcome,
              NodeTransition, AdapterConfidence, Applicability],
)
def test_top_level_unknown_kind_rejected(union):
    """AC-8f — bogus discriminator value rejected per umbrella."""
    with pytest.raises(ValidationError):
        TypeAdapter(union).validate_python({"kind": "bogus_kind"})


def test_not_applicable_reason_is_single_source_of_truth():
    """AC-8g — the Literal type is the same object across both producers."""
    recipe_anno = RecipeNotApplicable.model_fields["reason"].annotation
    rem_anno = RemediationNotApplicable.model_fields["reason"].annotation
    assert recipe_anno is rem_anno
    assert recipe_anno is NotApplicableReason


def test_validated_passed_failing_invariant():
    """AC-8h — passed == (failing == [])."""
    Validated(branch=BranchName("b"), report_path="/p", passed=True, failing=[])
    Validated(branch=BranchName("b"), report_path="/p",
              passed=False, failing=[SignalKind("tests")])
    with pytest.raises(ValidationError):
        Validated(branch=BranchName("b"), report_path="/p",
                  passed=True, failing=[SignalKind("tests")])
    with pytest.raises(ValidationError):
        Validated(branch=BranchName("b"), report_path="/p",
                  passed=False, failing=[])


@pytest.mark.parametrize("bad", [
    {"k": [1, 2]}, {"k": {"nested": 1}}, {"k": None},
])
def test_advance_state_primitives_only_rejects(bad):
    """AC-8i — `state` accepts only str | int | bool | float values."""
    with pytest.raises(ValidationError):
        Advance(state=bad)


@pytest.mark.parametrize("ok", [
    {"k": "v"}, {"k": 1}, {"k": True}, {"k": 1.5}, {},
])
def test_advance_state_primitives_only_accepts(ok):
    """AC-8i — primitive values + empty dict accepted."""
    Advance(state=ok)
```

Test file path: `tests/unit/transforms/test_exhaustiveness.py` — five named tests; pattern mirrors `tests/unit/indices/test_freshness.py:111`:

```python
from typing import assert_never
# ... imports omitted ...

def test_exhaustiveness_recipe_outcome():
    seen: set[str] = set()
    for o in (Applied(...), Skipped(...), RecipeNotApplicable(...), RecipeFailed(...)):
        match o:
            case Applied():               seen.add("applied")
            case Skipped():               seen.add("skipped")
            case RecipeNotApplicable():   seen.add("not_applicable")
            case RecipeFailed():          seen.add("failed")
            case _ as unexpected:         assert_never(unexpected)
    assert seen == {"applied", "skipped", "not_applicable", "failed"}

# ... four more for RemediationOutcome, NodeTransition, AdapterConfidence, Applicability ...
```

Test file path: `tests/unit/transforms/test_outcomes_mypy_negative.py` — subprocess-mypy fence (AC-9a):

```python
import subprocess, sys, textwrap
from pathlib import Path

FIXTURE = textwrap.dedent('''
    from typing import assert_never
    from codegenie.transforms.outcomes import (
        RecipeOutcome, Applied, Skipped, NotApplicable,
    )
    # Intentionally missing the `Failed` arm:
    def describe(o: RecipeOutcome) -> str:
        match o:
            case Applied():            return "a"
            case Skipped():            return "s"
            case NotApplicable():      return "n"
            case _ as unexpected:      assert_never(unexpected)  # mypy must complain
        return ""
''')

def test_assert_never_catches_missing_arm(tmp_path: Path):
    f = tmp_path / "negative.py"
    f.write_text(FIXTURE)
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(f)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "assert_never" in result.stdout
```

State why the red tests fail: `ModuleNotFoundError: codegenie.transforms.outcomes` — module doesn't exist.

### Green — minimal pass
- Add `src/codegenie/transforms/__init__.py` with re-exports per AC-10a.
- Add `src/codegenie/transforms/outcomes.py` with the five unions, all 17 variants, the six reason `Literal` aliases, the `ApplicationPlan` / `RecipeError` / `RemediationError` models, and the `Validated` `model_validator(mode="after")`. Use `Annotated[A | B | C, Field(discriminator="kind")]` for every umbrella; `kind: Literal["..."] = "..."` default-value form on every variant; `model_config = ConfigDict(frozen=True, extra="forbid")` everywhere.

### Refactor
- Add module docstring naming ADR-0001 / ADR-0010 + listing the five Phase-5-wrap-target unions.
- Add docstrings to each variant naming the producer (e.g., `"""Applied — produced by NpmLockfileRecipeEngine on a successful lockfile re-resolve."""`).
- Verify `__all__` is sorted; verify the AST source-scan and `model_construct` purity guards pass.
- Verify the subprocess-mypy fixture flags the deliberately-missing arm.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/__init__.py` | NEW — package marker; re-export the 31-name surface (ADR-0001). |
| `src/codegenie/transforms/outcomes.py` | NEW — five discriminated unions + six reason `Literal`s + error models + `ApplicationPlan`. |
| `tests/unit/transforms/__init__.py` | NEW — test package marker. |
| `tests/unit/transforms/test_outcomes.py` | NEW — parametrized construct + frozen + extra-reject + JSON round-trip + discriminator-string pin + JSON-shape pin + top-level-rejection + invariants. |
| `tests/unit/transforms/test_exhaustiveness.py` | NEW — five named `match` + `assert_never` tests, one per union (S1-05 fence test will assert this file exists and has ≥ 5 such tests). |
| `tests/unit/transforms/test_outcomes_purity.py` | NEW — module-purity AST scan; `model_construct` absence (AC-10b / AC-10c). |
| `tests/unit/transforms/test_outcomes_mypy_negative.py` | NEW — subprocess-mypy fence proving `assert_never` catches a missing `case` arm (AC-9a). |

## Out of scope

- **`Transform` ABC + `ApplyContext` + `AttemptSummary`** — handled by S1-04. This story ships only the *outcome* unions; the data they carry (`Transform`) is S1-04's surface.
- **`TrustOutcome` + `TrustSignal`** — handled by S6-02 (TrustScorer) under the `transforms/` namespace; not part of Step 1.
- **`JailedSubprocessResult` discriminated union** — handled by S4-01 (`src/codegenie/transforms/sandbox_jail.py`).
- **`PluginResolution = ConcreteResolution | UniversalFallbackResolution`** — handled by S2-04; lives in `src/codegenie/plugins/resolution.py`.
- **`WorkflowInternalEvent` / `WorkflowSpanningEvent`** — handled by S6-01.

## Notes for the implementer

- **`Field(discriminator="kind")`, NOT `Discriminator("kind")`.** The repo has 5 existing Pydantic discriminated unions and every one of them uses `Annotated[A | B | C, Field(discriminator="kind")]` (see `src/codegenie/indices/freshness.py:110`, `src/codegenie/probes/_shared/scanner_outcome.py:130`, `src/codegenie/probes/layer_c/scenario_result.py:105`, `src/codegenie/probes/layer_c/_cve_models.py:70`). `Discriminator("kind")` is the *callable-discriminator* API for cases where the discriminator is computed; ours is tag-string. Match the convention (CLAUDE.md Rule 11).
- **`kind: Literal["..."] = "..."` default-value form.** Repo convention (`freshness.py:45`, `scanner_outcome.py:117`). Construction stays terse — `Applied(transform_id=..., plugin_id=..., recipe_id=...)` instead of `Applied(kind="applied", ...)`.
- **`extra="forbid"` is non-negotiable** — ADR-0010 §Consequences; the Step 1 fence test `test_no_any_in_plugin_surface.py` (lands in S1-05) will fail otherwise.
- **Build-order rationale for `Applied.transform_id: TransformId` (vs arch line 534's `Applied.transform: Transform`).** `Transform` ABC ships in S1-04 — this story cannot import it (circular: `outcomes.py` would import `transform.py` which imports `RecipeOutcome` from `outcomes.py`). S1-04's `Transform.transform_id` field is the lookup key; consumers do `transforms_by_id[outcome.transform_id]`. S1-04 closes the loop. Do not add a `Transform` field to `Applied` retroactively — that would be a contract rename and break ADR-0001's snapshot test.
- **`branch: BranchName` + `report_path: str` placeholder typing on `Validated`.** `SandboxedPath` (arch line 827) ships in S4-01. Until then, `report_path: str` is the contract. S4-01 widens via a Pydantic `field_validator` that converts `str` → `SandboxedPath` at construction time (additive — string callers still work). Do not pre-import `SandboxedPath` in S1-03; that's a circular dependency in the other direction.
- **`Validated.passed` + `Validated.failing` are the flat denormalization of arch's `TrustOutcome.passed` + `TrustOutcome.failing`.** S6-02 (`TrustScorer`) ships `TrustOutcome` under `transforms/trust_scorer.py`; it does **not** rename `Validated.passed` / `Validated.failing` — the additive widening adds `signals: list[TrustSignal]` and `confidence: Literal["high","degraded"]` ALONGSIDE the existing flat fields. ADR-0001 contract-snapshot enforces this. (If S6-02 wants a nested `TrustOutcome`, the right move is a *new* `Validated2` variant with a deprecation path, not a rename — but the cheapest correct shape is additive fields.)
- **Arch line 1154 typo on `NodeTransition.ShortCircuit`.** Arch Gap-1 example shows `ShortCircuit(outcome: RecipeOutcome)`. Story (correctly) ships `ShortCircuit(outcome: RemediationOutcome)` — orchestrator-outer-loop short-circuits at the *workflow* level, not the *recipe* level. Arch §Edge cases line 899–904 confirms (`RemediationOutcome.Failed/NotApplicable` are the outer-loop short-circuit returns). Document this drift in a code comment so the next phase-arch update reflects it.
- **`Skipped` semantics.** `RecipeOutcome.Skipped` is for plugin opt-out — a plugin's pre-`applies()` hook declines to even evaluate (vs `NotApplicable` which is `applies()` returning `NotApplies`). Phase 3's NpmLockfileRecipe never emits `Skipped` in normal flow; the variant is reserved for Phase 4+ additive plugins. `SkipReason = Literal["plugin_disabled", "registry_skipped"]` is the minimal set.
- **`NotApplicableReason` shared identity (AC-7a / AC-8g).** Define the `Literal` ONCE at module level; `RecipeOutcome.NotApplicable.reason: NotApplicableReason` and `RemediationOutcome.NotApplicable.reason: NotApplicableReason` both reference the same alias. Phase 4 adds members additively (e.g., `LLM_FALLBACK_REQUIRED`). The single-source-of-truth identity test (`A is B`) catches accidental duplication.
- **`assert_never` is *type-time* enforcement.** Runtime tests assert "every variant has a case arm right now"; the *real* protection against silent `Union` widening is `mypy --strict` reading `assert_never(unexpected)` and verifying every variant has been narrowed-out by the time the default arm is reached. That's why AC-9a ships a subprocess-mypy fixture — without it, a future contributor who adds `LLMFallback` to `RecipeOutcome` without updating `describe()` would silently pass CI.
- **`NodeTransition.Advance.state` primitives-only** — ADR-0010 §Consequences forbids `dict[str, Any]` under `transforms/`. Pydantic with `dict[str, str | int | bool | float]` enforces this at validation time (rejects nested dicts, lists, `None` values). If a node genuinely needs richer state, the right move is a new typed payload model, not relaxing `Advance.state`.
- **`ApplicationPlan` is a placeholder** in Phase 3 — `summary: str | None = None`. S5-01's `NpmLockfileRecipeEngine` widens via additive fields. Add a code comment on the class naming S5-01 as the widener so the implementer there knows to extend, not redefine.
- **Closest precedent to mirror.** `src/codegenie/indices/freshness.py` (Phase 2 S1-01) — same Pydantic discriminated union shape, same `kind: Literal[...] = "..."` form, same `Annotated[A | B, Field(discriminator="kind")]` umbrella. Tests in `tests/unit/indices/test_freshness.py` are the test-shape template: parametrized round-trip identity, discriminator-string pin, JSON-shape pin, top-level-rejection, nested-discriminator preservation, `match` + `assert_never` exhaustiveness, `__all__` pin, `model_construct` purity scan.
