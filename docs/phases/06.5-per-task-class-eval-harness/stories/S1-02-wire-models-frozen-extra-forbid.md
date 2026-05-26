# Story S1-02 — Wire models with frozen + extra=forbid

**Step:** Step 1 — Establish contracts: package scaffold, wire models, registry, Protocol
**Status:** HARDENED
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0001 (isolation-class field origin), ADR-0002 (`lower_bound_95` field), ADR-0003 (tier names are `str`), ADR-0004 (`FailureMode` typed; `severity: Literal["block","warn","info"]`), ADR-0008 (`BenchScore.breakdown` typed-at-the-edge), ADR-0010 (`isolation_class: Literal["subprocess","microvm"]`), Phase 5 ADR-0014 (`frozen=True, extra="forbid"` discipline)

## Validation notes

Validated: 2026-05-26
Verdict: HARDENED
Findings addressed: 14 total — 3 blocks, 8 hardens, 3 nits

Changes applied:
- AC-2 strengthened (structural walk over every `BaseModel` subclass — was: hand-rolled list of 2 of 5 types) — Coverage F-COV-1 / Test-Quality F-TQ-1 / Design-Patterns F-DP-2 (merged)
- AC-3a added (boundary inclusivity on bounded fields) — Test-Quality F-TQ-3
- AC-4 strengthened (severity Literal pinned via `typing.get_args` introspection) — Test-Quality F-TQ-4
- AC-4a added (`FailureMode.detail: str | None = None` default pinned) — Coverage F-COV-3
- AC-5 strengthened (isolation_class — positive `"microvm"` accept + introspection pin) — Test-Quality F-TQ-2
- AC-6a added (BenchRunReport bounded coverage: `passed_count`, `total_cost_usd`, `score_stddev` + boundary inclusivity for `mean_score` / `lower_bound_95`) — Coverage F-COV-2 / Consistency F-CON-1
- AC-7a added (`PromotionVerdict.requires_human_approval` no-default; omission + `=False` both raise) — Coverage F-COV-4 / Design-Patterns F-DP-8
- AC-9 strengthened (`case_digest` negative space enumerated; hypothesis property test) — Test-Quality F-TQ-6
- AC-11 added (`per_case` and `failure_modes` tuple-not-list pinned via annotation introspection) — Coverage F-COV-6 / Design-Patterns F-DP-9
- AC-12 added (BenchCase Literal-typed fields `disposition`/`difficulty`/`source`/`curation_class` exact-set pinning) — Coverage F-COV-5
- AC-13 added (PromotionVerdict tier fields' annotation is `str`, not Literal — via field-annotation introspection) — Test-Quality F-TQ-5
- AC-14 added (`complete=False` JSON round-trip; field not silently elided by a defensive serializer) — Test-Quality F-TQ-7
- TDD plan extended from 8 to ~18 tests (parametrized); promoted `_FROZEN_WIRE_TYPES: Final[frozenset[type[BaseModel]]]` to module-scope catalog (extension-by-addition vehicle for S1-05's substring-ban test) — Design-Patterns F-DP-2
- Out-of-scope expanded with 2 deferrals (`cassette_canary_pin` format validator; JSON Schema artifact) — Coverage F-COV-7 / Consistency F-CON-4
- Notes for implementer expanded with 3 bullets (per-class `model_config` Rule-11 convention rationale + future-kernel-extract trigger; structural-walk test discipline; `complete` bool ↔ `Literal` widening trigger) — Design-Patterns F-DP-1 / F-DP-3 (YAGNI-guarded)
- Refactor step bullet 1 expanded (cite all 6 honored ADRs + Phase 5 ADR-0014 precedent in the module docstring) — Consistency F-CON-2

Full audit log: docs/phases/06.5-per-task-class-eval-harness/stories/_validation/S1-02-wire-models-frozen-extra-forbid.md

## Context

Every component boundary downstream of Step 1 reads or writes one of these five wire types. They are the *contract* — once published, edits become breaking changes for Phase 11 (PR provenance), Phase 13 (cost ledger), and Phase 16 (microVM isolation upgrade). Two field additions over the original synthesis close gaps that would otherwise become silent-correctness failures: `complete: bool = True` on `BenchRunReport` (Gap #4 — promotion gate must reject incomplete partial reports) and `isolation_class: Literal["subprocess","microvm"] = "subprocess"` on `BenchRunReport` (Gap #1 / ADR-0010 — prevents silent population mixing when Phase 16 ships microVM rubric isolation).

This story plants those contracts with the strictest Pydantic v2 discipline (`frozen=True`, `extra="forbid"`) so adding a field is an explicit ADR-amendment-gated change, not an oversight.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Data model` — full field shapes for `FailureMode`, `BenchScore`, `BenchCase`, `BenchRunReport`, `PromotionVerdict`. This is the canonical reference; copy field-for-field.
  - `../phase-arch-design.md §Component design → src/codegenie/eval/models.py` — module-level guidance (~150 LOC, Pydantic v2 throughout, typed-enum-at-the-edge pattern for `BenchScore.breakdown`).
  - `../phase-arch-design.md §Edge cases #10, #12, #15, #21` — semantic contracts the model permits (e.g., `score=0.97` with `passed=False` is allowed; the rubric chooses).
  - `../phase-arch-design.md §Harness engineering — Typed state contracts` — `extra="forbid"` mandatory at every wire type; defense-in-depth re-validation at every consumer.
- **Phase ADRs:**
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md` — `lower_bound_95: float = Field(ge=0.0, le=1.0)` is the only statistic the gate consumes; `mean_score` is human-only.
  - `../ADRs/0003-tier-identifiers-as-str-validated-at-startup.md` — `PromotionVerdict.current_tier` / `target_tier` are `str`, not `Literal[...]`; widening to `"emerald"` is a YAML edit, not a Python edit.
  - `../ADRs/0004-per-task-class-failure-modes-taxonomy.md` — `FailureMode` has `code: str`, `severity: Literal["block","warn","info"]`, `detail: str | None`; `BenchScore.failure_modes: tuple[FailureMode, ...]`; `BenchRunReport.block_severity_failure_modes: tuple[str, ...]` (deduplicated codes).
  - `../ADRs/0008-breakdown-keys-strenum-with-substring-ban.md` — `BenchScore.breakdown: dict[str, float]` at type level; runtime validates against `task_class.breakdown_keys` (the model is permissive; the runner is strict).
  - `../ADRs/0010-isolation-class-annotation-on-bench-run-report.md` — `BenchRunReport.isolation_class: Literal["subprocess", "microvm"] = "subprocess"`; the default preserves Phase 6.5 behavior, and Phase 16's flip is detected mechanically.
- **Production ADRs:** `../../../production/adrs/0008-objective-signal-trust-score.md` — the "facts not judgments" commitment the substring ban (closed by S1-05's `test_bench_score_static.py`) protects.
- **Existing precedent:** `../../05-sandbox-trust-gates/ADRs/0014-objectivesignals-extra-forbid-static-introspection.md` — mirror the `model_config = ConfigDict(frozen=True, extra="forbid")` discipline exactly.

## Goal

Land `src/codegenie/eval/models.py` exporting frozen Pydantic v2 wire types (`FailureMode`, `BenchScore`, `BenchCase`, `BenchRunReport`, `PromotionVerdict`) with every field shape per `../phase-arch-design.md §Data model`, including `complete: bool = True` (Gap #4) and `isolation_class: Literal["subprocess","microvm"] = "subprocess"` (ADR-0010).

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/eval/models.py` exists; `from codegenie.eval.models import FailureMode, BenchScore, BenchCase, BenchRunReport, PromotionVerdict` succeeds.
- [ ] **AC-2.** *Every* `BaseModel` subclass declared in `codegenie.eval.models` has `model_config["frozen"] is True` and `model_config["extra"] == "forbid"`. Verified by a structural walk via `inspect.getmembers(models, inspect.isclass)` filtered to `issubclass(BaseModel) and obj.__module__ == models.__name__` — *not* by a hand-rolled enumeration. The collected set is published as a module-scope `_FROZEN_WIRE_TYPES: Final[frozenset[type[BaseModel]]]` in the test, and its cardinality is asserted to be exactly **5** (FailureMode, BenchScore, BenchCase, BenchRunReport, PromotionVerdict). Mutation raises `pydantic.ValidationError` (`frozen=True`); unknown fields raise (`extra="forbid"`) — both directions verified for every member of the catalog. (validator: hardened from original list-of-two enumeration — Coverage F-COV-1 / Test-Quality F-TQ-1 / Design-Patterns F-DP-2; precedent: `tests/unit/workflows/test_vuln_ledger_shape.py:65`, Phase 5 `test_objective_signals_static.py`)
- [ ] **AC-3.** `BenchScore.score` is `Field(ge=0.0, le=1.0)`; `cost_usd` is `Field(ge=0.0)`; `wall_clock_ms` is `Field(ge=0)`; `breakdown` is `dict[str, float]` (typed-at-the-edge per ADR-0008 — the model does **not** enumerate keys).
- [ ] **AC-3a.** Boundary inclusivity is verified on every bounded BenchScore field: `score=0.0` and `score=1.0` accept; `cost_usd=0.0` accepts; `wall_clock_ms=0` accepts. (Guards against a regression to `gt`/`lt` strict bounds.) (validator: added — Test-Quality F-TQ-3)
- [ ] **AC-4.** `FailureMode.severity: Literal["block", "warn", "info"]` (ADR-0004). Verified two ways: (a) all three values construct successfully; (b) the literal's argument set is pinned via `typing.get_args(FailureMode.model_fields["severity"].annotation) == ("block", "warn", "info")` — exact, three-membered (guards against symmetric widening like `Literal["block","warn","info","trace"]`). (validator: hardened — Test-Quality F-TQ-4)
- [ ] **AC-4a.** `FailureMode.detail: str | None = None` (ADR-0004). The field is optional with a default of `None`; verified by `FailureMode.model_fields["detail"].is_required() is False` and `FailureMode().detail is None` (when constructed with only required fields) AND construction with `detail="something"` works. (validator: added — Coverage F-COV-3)
- [ ] **AC-5.** `BenchRunReport.isolation_class: Literal["subprocess", "microvm"] = "subprocess"` (ADR-0010). Verified three ways: (a) default value is `"subprocess"`; (b) explicit `isolation_class="microvm"` accepts and round-trips; (c) the Literal's argument set is pinned exactly via `typing.get_args(BenchRunReport.model_fields["isolation_class"].annotation) == ("subprocess", "microvm")`. Unknown values (e.g., `"firecracker"`) raise `ValidationError`. (validator: hardened — Test-Quality F-TQ-2)
- [ ] **AC-6.** `BenchRunReport.lower_bound_95: float = Field(ge=0.0, le=1.0)` and `mean_score: float = Field(ge=0.0, le=1.0)` (ADR-0002); `block_severity_failure_modes: tuple[str, ...]` (ADR-0004 — deduplicated codes, not full `FailureMode`s).
- [ ] **AC-6a.** Every bounded BenchRunReport attribute carries its arch-specified `Field(...)` constraint and is regression-tested: `lower_bound_95` rejects `<0` and `>1` and accepts `0.0`/`1.0`; `mean_score` ditto; `score_stddev` rejects `<0` and accepts `0.0`; `passed_count: int = Field(ge=0)` rejects `<0` and accepts `0`; `total_cost_usd: float = Field(ge=0.0)` rejects `<0` and accepts `0.0`. (Guards against an unconstrained-`Field()` regression that would slip ADR-0002's promotion-gate input.) (validator: added — Coverage F-COV-2 / Consistency F-CON-1)
- [ ] **AC-7.** `PromotionVerdict.current_tier: str` and `target_tier: str` (ADR-0003 — *not* `Literal`); `requires_human_approval: Literal[True]` as the structural marker.
- [ ] **AC-7a.** `PromotionVerdict.requires_human_approval` is **required** (no default); construction omitting the field raises `ValidationError`; construction with `requires_human_approval=False` raises `ValidationError`. Verified by `PromotionVerdict.model_fields["requires_human_approval"].is_required() is True` AND both negative constructions in tests. (Structural-marker discipline per ADR-0009 — "humans always promote"; guards against a "tidy-up" PR that adds `= True` default and silently makes the marker invisible.) (validator: added — Coverage F-COV-4 / Design-Patterns F-DP-8)
- [ ] **AC-8.** `BenchCase.commit_sha: str | None`; loader-time check (out of scope here) will enforce `commit_sha is not None` iff `source != "curated"` — this story documents the rule in the model's docstring but does **not** add a Pydantic validator (that lives in the loader, S2-02).
- [ ] **AC-9.** `BenchCase.case_digest: str` matches the regex `r"^blake3:[0-9a-f]{64}$"` enforced by a `field_validator`; malformed input raises `pydantic.ValidationError`. Negative space enumerated in tests: wrong prefix (`sha256:...`); 63 hex chars (length−1); 65 hex chars (length+1); 0 hex chars (`blake3:`); 64 chars but **uppercase** hex (`blake3:` + `"A"*64` — guards against an accidental case-insensitive regex); 64 hex chars but no prefix; trailing whitespace; leading whitespace. Plus a `@hypothesis.given(st.text())` property test: any string not matching the canonical regex must reject (`hypothesis` is already a dev dep — see precedent in `tests/unit/indices/`). (validator: hardened — Test-Quality F-TQ-6)
- [ ] **AC-11.** Immutability-honouring container shapes are pinned via annotation introspection: `BenchRunReport.model_fields["per_case"].annotation` is `tuple[tuple[str, BenchScore], ...]` (origin is `tuple`, not `list`); same for `BenchScore.model_fields["failure_modes"].annotation` (`tuple[FailureMode, ...]`). Verified via `typing.get_origin(...) is tuple` and `typing.get_args(...)` matching the expected shape. (Guards against a refactor to `list[...]` that would defeat `frozen=True` by permitting `report.per_case.append(...)`.) (validator: added — Coverage F-COV-6 / Design-Patterns F-DP-9)
- [ ] **AC-12.** Every BenchCase Literal field's accepted set is pinned exactly via `typing.get_args(BenchCase.model_fields[name].annotation)`:
  - `disposition` → `("positive", "negative", "ambiguous")`
  - `difficulty` → `("easy", "medium", "hard")`
  - `source` → `("curated", "outcome-ledger-derived", "regression-converted")`
  - `curation_class` → `("rag-corpus-derived", "held-out")`
  Plus: one accept and one reject per field at the construction layer (e.g., `disposition="positive"` works; `disposition="undecided"` raises `ValidationError`). (Guards against a lazy-impl that types these as `str`; the taxonomy closure is the model's responsibility per arch §"Component design → models.py".) (validator: added — Coverage F-COV-5)
- [ ] **AC-13.** `PromotionVerdict.current_tier` and `target_tier` field annotations are `str` (not `Literal[...]`), verified via field-annotation introspection: `PromotionVerdict.model_fields["current_tier"].annotation is str` AND same for `target_tier`. (Guards against a regression to `Literal["bronze","silver","gold","platinum",...]` that the value-only test in AC-7 would not detect.) (validator: added — Test-Quality F-TQ-5)
- [ ] **AC-14.** Round-trip discipline: `BenchRunReport(complete=False, ...).model_dump()` contains a `"complete"` key with value `False`; `BenchRunReport.model_validate_json(report.model_dump_json()).complete is False` for both `complete=True` and `complete=False` constructions. (Guards against a defensive `field_serializer` that strips false-y values and silently elides `complete` from the wire — Phase 11/13 readers would see `complete=True` default and treat a partial run as evidence.) (validator: added — Test-Quality F-TQ-7)
- [ ] **AC-15.** The red tests from §TDD plan exist, were committed at the red marker, and are now green.
- [ ] **AC-16.** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/test_eval_models.py` all pass on touched files.

## Implementation outline

1. Write `tests/unit/test_eval_models.py` first (red); confirm `ImportError`.
2. Create `src/codegenie/eval/models.py`:
   - Imports: `from datetime import datetime`, `from pathlib import Path`, `from typing import Literal`, `from pydantic import BaseModel, ConfigDict, Field, field_validator`.
   - Five `BaseModel` subclasses in the order `FailureMode` → `BenchScore` → `BenchCase` → `BenchRunReport` → `PromotionVerdict` (`BenchScore.failure_modes` references `FailureMode`, etc. — define dependencies first).
   - Every class declares `model_config = ConfigDict(frozen=True, extra="forbid")` as the first body line.
   - Field shapes per `../phase-arch-design.md §Data model`; `Field(ge=, le=)` constraints per the AC list above.
   - One `@field_validator("case_digest")` on `BenchCase` enforcing `blake3:<64 hex>`; no other validators (per ADR-0004 the model is permissive; the runner is strict).
3. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/eval/models.py`, `pytest tests/unit/test_eval_models.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_eval_models.py`

```python
# tests/unit/test_eval_models.py
import inspect
import typing
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

import pytest
from hypothesis import given, strategies as st
from pydantic import BaseModel, ValidationError

from codegenie.eval import models  # module-walk; do NOT re-export
from codegenie.eval.models import (
    BenchCase, BenchRunReport, BenchScore, FailureMode, PromotionVerdict,
)


# ---- structural catalog ---------------------------------------------------
# Extension-by-addition vehicle. New BaseModel subclass declared in
# ``codegenie.eval.models`` ⇒ automatically picked up + verified by AC-2.
# Future stories (S1-05's substring-ban test; S3-04's runtime validation;
# S7-01's fence-CI) re-use this catalog instead of hand-rolling a list.
def _collect_frozen_wire_types() -> frozenset[type[BaseModel]]:
    found: set[type[BaseModel]] = set()
    for _name, obj in inspect.getmembers(models, inspect.isclass):
        if not issubclass(obj, BaseModel):
            continue
        if obj.__module__ != models.__name__:
            continue
        found.add(obj)
    return frozenset(found)


_FROZEN_WIRE_TYPES: Final[frozenset[type[BaseModel]]] = _collect_frozen_wire_types()


def _ok_failure_mode() -> FailureMode:
    return FailureMode(code="validator.build_failed", severity="block", detail=None)


def _ok_score() -> BenchScore:
    return BenchScore(
        passed=True, score=0.83,
        breakdown={"cve_dropped": 1.0, "tests_pass": 0.66},
        failure_modes=(),
        cost_usd=0.04, wall_clock_ms=1234,
    )


# === AC-1 ==================================================================
def test_module_exports_the_five_wire_types():
    # AC-1: bare import + explicit names resolve.
    from codegenie.eval.models import (  # noqa: F401  (re-import to assert)
        BenchCase, BenchRunReport, BenchScore, FailureMode, PromotionVerdict,
    )


# === AC-2 (and structural F-COV-1 / F-TQ-1 / F-DP-2 resolution) ============
def test_frozen_wire_types_catalog_has_exactly_five_members():
    # AC-2: cardinality pin. Adding a new wire type silently is rejected;
    # adding one intentionally forces this number to be revisited (and
    # forces ADR amendment per the "wire types are contract" doctrine).
    assert {t.__name__ for t in _FROZEN_WIRE_TYPES} == {
        "FailureMode", "BenchScore", "BenchCase", "BenchRunReport", "PromotionVerdict",
    }
    assert len(_FROZEN_WIRE_TYPES) == 5


@pytest.mark.parametrize("wire_type", sorted(_FROZEN_WIRE_TYPES, key=lambda t: t.__name__))
def test_every_wire_type_in_models_module_is_frozen_and_forbids_extra(
    wire_type: type[BaseModel],
):
    # AC-2: load-bearing — verified structurally for every member of
    # ``_FROZEN_WIRE_TYPES``, not for a hand-rolled subset. A regression
    # dropping ``frozen=True`` or ``extra="forbid"`` from any new (or
    # existing) wire type is caught here.
    assert wire_type.model_config.get("frozen") is True, (
        f"{wire_type.__name__} must have frozen=True (Phase 5 ADR-0014 precedent)"
    )
    assert wire_type.model_config.get("extra") == "forbid", (
        f"{wire_type.__name__} must have extra='forbid'"
    )


# === AC-3 / AC-3a (BenchScore bounded fields + inclusivity) ================
def test_bench_score_score_field_is_bounded_zero_to_one():
    # AC-3: ADR-0002 bound — score ∈ [0, 1].
    with pytest.raises(ValidationError):
        BenchScore(passed=True, score=1.5, breakdown={}, failure_modes=(),
                   cost_usd=0.0, wall_clock_ms=0)
    with pytest.raises(ValidationError):
        BenchScore(passed=True, score=-0.01, breakdown={}, failure_modes=(),
                   cost_usd=0.0, wall_clock_ms=0)


@pytest.mark.parametrize(
    "score,cost_usd,wall_clock_ms",
    [(0.0, 0.0, 0), (1.0, 0.0, 0), (0.5, 0.0, 0)],
)
def test_bench_score_bounded_fields_inclusive_at_boundary(
    score: float, cost_usd: float, wall_clock_ms: int,
):
    # AC-3a: ge / le bounds are INCLUSIVE. A regression to gt / lt would
    # reject score=0.0 (perfect-fail rubric output) and score=1.0
    # (perfect-pass rubric output) — both load-bearing for the gate.
    BenchScore(
        passed=True, score=score, breakdown={}, failure_modes=(),
        cost_usd=cost_usd, wall_clock_ms=wall_clock_ms,
    )


def test_bench_score_breakdown_keys_are_not_enumerated_by_the_model_adr_0008():
    # AC-3: ADR-0008 typed-at-the-edge — the model permits any
    # ``dict[str, float]``; smuggling-key validation is the runner's job
    # (S3-04) and PR-time fence (S1-05), not Pydantic's.
    smuggling = BenchScore(
        passed=True, score=0.5, breakdown={"llm_confidence": 0.9},
        failure_modes=(), cost_usd=0.0, wall_clock_ms=0,
    )
    assert smuggling.breakdown == {"llm_confidence": 0.9}


# === AC-4 / AC-4a (FailureMode severity + detail) ==========================
def test_failure_mode_severity_literal_is_exactly_three_values_adr_0004():
    # AC-4: three-membered Literal pinned both by construction AND by
    # introspection — the introspection guard is the structural defense
    # against symmetric widening (e.g., adding "trace" silently — the
    # construction-only test would still pass).
    for sev in ("block", "warn", "info"):
        assert FailureMode(code="c", severity=sev).severity == sev
    with pytest.raises(ValidationError):
        FailureMode(code="c", severity="fatal")  # type: ignore[arg-type]
    # Introspection pin — ADR-0004 §Consequences.
    args = typing.get_args(FailureMode.model_fields["severity"].annotation)
    assert args == ("block", "warn", "info"), (
        f"FailureMode.severity Literal widened silently: got {args}; "
        "amending ADR-0004 is required to change this set."
    )


def test_failure_mode_detail_is_optional_with_none_default_adr_0004():
    # AC-4a: ADR-0004 specifies ``detail: str | None = None`` — optional.
    assert FailureMode.model_fields["detail"].is_required() is False
    assert FailureMode(code="c", severity="info").detail is None
    assert FailureMode(code="c", severity="info", detail="oops").detail == "oops"


# === AC-5 (BenchRunReport isolation_class — ADR-0010) ======================
def test_bench_run_report_isolation_class_defaults_subprocess_adr_0010():
    # AC-5: default + positive accept on BOTH literal values + introspection
    # pin on the exact two-membered set + negative reject.
    r = _make_report(complete_omitted=True)
    assert r.isolation_class == "subprocess"

    r_microvm = _make_report(complete_omitted=True, isolation_class="microvm")
    assert r_microvm.isolation_class == "microvm"

    with pytest.raises(ValidationError):
        _make_report(complete_omitted=True, isolation_class="firecracker")  # type: ignore[arg-type]

    args = typing.get_args(BenchRunReport.model_fields["isolation_class"].annotation)
    assert args == ("subprocess", "microvm"), (
        f"isolation_class Literal must be exactly two-valued; got {args}. "
        "Widening to a third class requires an ADR amendment of ADR-0010."
    )


# === AC-6 / AC-6a (BenchRunReport bounded fields — ADR-0002) ==============
@pytest.mark.parametrize(
    "field_name,bad_low,bad_high,good_boundary",
    [
        ("lower_bound_95", -0.01, 1.5, [0.0, 1.0]),
        ("mean_score", -0.01, 1.5, [0.0, 1.0]),
        ("score_stddev", -0.01, None, [0.0]),
        ("passed_count", -1, None, [0]),
        ("total_cost_usd", -0.01, None, [0.0]),
    ],
)
def test_bench_run_report_bounded_fields_reject_out_of_range_and_accept_boundary(
    field_name: str, bad_low, bad_high, good_boundary,
):
    # AC-6 / AC-6a: ADR-0002 makes lower_bound_95 the load-bearing promotion
    # input. Every bounded BenchRunReport field is regression-tested for
    # below-bound reject, above-bound reject (when applicable), and inclusive
    # boundary accept. A regression dropping the ``Field(...)`` constraint
    # would silently pass an unbounded value to the promotion gate.
    with pytest.raises(ValidationError):
        _make_report(complete_omitted=True, **{field_name: bad_low})
    if bad_high is not None:
        with pytest.raises(ValidationError):
            _make_report(complete_omitted=True, **{field_name: bad_high})
    for ok_val in good_boundary:
        _make_report(complete_omitted=True, **{field_name: ok_val})


# === AC-7 / AC-7a / AC-13 (PromotionVerdict tier discipline) ==============
def test_promotion_verdict_tier_fields_accept_arbitrary_strings_adr_0003():
    # AC-7: tier names are strings; "emerald" must not require a code edit.
    v = PromotionVerdict(
        task_class="vuln-remediation",
        current_tier="bronze", target_tier="emerald",
        evidence_sufficient=False, reasons=("case count below floor",),
        lower_bound_95=0.62, threshold_at_target=0.75,
        requires_human_approval=True,
    )
    assert v.target_tier == "emerald"


def test_promotion_verdict_tier_field_annotations_are_str_not_literal_adr_0003():
    # AC-13: introspection pin — guards against a regression to
    # ``Literal["bronze","silver","gold","platinum","emerald"]`` that
    # the value-only test above would not detect.
    assert PromotionVerdict.model_fields["current_tier"].annotation is str
    assert PromotionVerdict.model_fields["target_tier"].annotation is str


def test_promotion_verdict_requires_human_approval_has_no_default():
    # AC-7a: structural marker discipline. Omission AND ``=False`` both
    # raise — the gate-is-always-advisory contract per ADR-0009 stays
    # visible in the type system.
    assert PromotionVerdict.model_fields["requires_human_approval"].is_required() is True
    base = dict(
        task_class="t", current_tier="bronze", target_tier="silver",
        evidence_sufficient=False, reasons=(), lower_bound_95=0.0,
        threshold_at_target=0.5,
    )
    with pytest.raises(ValidationError):
        PromotionVerdict(**base)  # type: ignore[arg-type]  # missing requires_human_approval
    with pytest.raises(ValidationError):
        PromotionVerdict(**(base | {"requires_human_approval": False}))  # type: ignore[arg-type]


# === AC-8 (BenchCase commit_sha — docstring documents loader rule) ========
def test_bench_case_commit_sha_is_optional_at_the_model():
    # AC-8: ``commit_sha`` is str | None at the model boundary; the
    # cross-field rule (must be non-None unless source="curated") lives
    # in the loader (S2-02) — NOT in a Pydantic validator here.
    base = _bench_case_kwargs()
    BenchCase(**base)  # commit_sha=None + source="curated" — OK at the model
    BenchCase(**(base | {"commit_sha": "abc1234"}))  # explicit also OK


# === AC-9 (BenchCase case_digest blake3 regex) ============================
@pytest.mark.parametrize(
    "bad_digest",
    [
        "sha256:" + "a" * 64,    # wrong prefix
        "blake3:" + "a" * 63,    # length−1
        "blake3:" + "a" * 65,    # length+1
        "blake3:",               # prefix only, 0 hex
        "blake3:" + "A" * 64,    # uppercase hex — canonicality check
        "a" * 64,                # 64 hex chars, no prefix
        " blake3:" + "a" * 64,   # leading whitespace
        "blake3:" + "a" * 64 + " ",  # trailing whitespace
    ],
)
def test_bench_case_digest_must_match_blake3_64_hex_negative(bad_digest: str):
    # AC-9: enumerated mutation slips. fullmatch + canonical lowercase
    # + canonical length + canonical prefix all enforced.
    base = _bench_case_kwargs()
    with pytest.raises(ValidationError):
        BenchCase(**(base | {"case_digest": bad_digest}))


def test_bench_case_digest_accepts_canonical():
    base = _bench_case_kwargs()
    BenchCase(**base)  # base uses blake3:0*64


@given(st.text(min_size=0, max_size=80))
def test_bench_case_digest_hypothesis_only_canonical_strings_accept(text: str):
    # AC-9 property: any string that does NOT match ``^blake3:[0-9a-f]{64}$``
    # must reject. The regex is small enough that hypothesis spans the
    # negative space in seconds. (Positive space is covered by the
    # canonical-accept test above; we don't bias hypothesis into the
    # tiny canonical band.)
    import re
    base = _bench_case_kwargs()
    if re.fullmatch(r"^blake3:[0-9a-f]{64}$", text):
        BenchCase(**(base | {"case_digest": text}))
    else:
        with pytest.raises(ValidationError):
            BenchCase(**(base | {"case_digest": text}))


# === AC-11 (immutability-honouring container shapes) ======================
def test_per_case_and_failure_modes_use_tuple_not_list():
    # AC-11: ``frozen=True`` doesn't freeze inner mutables — using ``tuple``
    # is what closes that hole. A refactor to ``list[...]`` would allow
    # ``report.per_case.append(...)`` despite ``frozen=True``.
    per_case_anno = BenchRunReport.model_fields["per_case"].annotation
    assert typing.get_origin(per_case_anno) is tuple, (
        f"BenchRunReport.per_case must be a tuple type; got origin "
        f"{typing.get_origin(per_case_anno)!r}"
    )
    failure_modes_anno = BenchScore.model_fields["failure_modes"].annotation
    assert typing.get_origin(failure_modes_anno) is tuple


# === AC-12 (BenchCase Literal-typed fields) ===============================
@pytest.mark.parametrize(
    "field_name,expected_values,accept_one,reject_one",
    [
        ("disposition", ("positive", "negative", "ambiguous"), "positive", "undecided"),
        ("difficulty", ("easy", "medium", "hard"), "medium", "trivial"),
        ("source",
            ("curated", "outcome-ledger-derived", "regression-converted"),
            "curated", "synthetic"),
        ("curation_class", ("rag-corpus-derived", "held-out"), "held-out", "training"),
    ],
)
def test_bench_case_literal_fields_have_exact_value_sets(
    field_name: str, expected_values: tuple[str, ...],
    accept_one: str, reject_one: str,
):
    # AC-12: per-field Literal closure. Lazy-impl using raw ``str`` would
    # pass the construction-layer accept but the introspection pin catches it.
    args = typing.get_args(BenchCase.model_fields[field_name].annotation)
    assert args == expected_values, (
        f"BenchCase.{field_name} Literal must be exactly {expected_values!r}; "
        f"got {args!r}. Widening requires a phase ADR amendment."
    )
    base = _bench_case_kwargs()
    BenchCase(**(base | {field_name: accept_one}))  # accept
    with pytest.raises(ValidationError):
        BenchCase(**(base | {field_name: reject_one}))  # reject


# === AC-4 + Gap-4 (BenchRunReport.complete) ===============================
def test_bench_run_report_complete_defaults_to_true_gap_4():
    # Gap #4: complete defaults True; cost-cap path sets False.
    r = _make_report(complete_omitted=True)
    assert r.complete is True
    r2 = _make_report(complete_omitted=False, complete_value=False)
    assert r2.complete is False


def test_bench_run_report_complete_round_trips_through_json_both_directions():
    # AC-14: explicit ``complete=False`` survives JSON round-trip; the
    # field is not silently elided by a defensive ``field_serializer``.
    r = _make_report(complete_omitted=False, complete_value=False)
    dumped = r.model_dump()
    assert "complete" in dumped and dumped["complete"] is False
    rt = BenchRunReport.model_validate_json(r.model_dump_json())
    assert rt.complete is False
    # Symmetric: True round-trips too.
    r_t = _make_report(complete_omitted=False, complete_value=True)
    assert BenchRunReport.model_validate_json(r_t.model_dump_json()).complete is True


# ---- helpers (test-local; do not export) ---------------------------------
def _make_report(complete_omitted: bool, complete_value: bool = True,
                 isolation_class: str = "subprocess",
                 **overrides) -> BenchRunReport:
    kwargs = dict(
        run_id="abcd1234", task_class="t", harness_version="0.1.0",
        sut_digest="d1", rubric_digest="d2", cassette_corpus_digest="d3",
        started_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
        ended_at=datetime(2026, 5, 12, tzinfo=timezone.utc),
        per_case=(("c1", _ok_score()),),
        mean_score=0.5, score_stddev=0.1, lower_bound_95=0.3,
        passed_count=1, total_cost_usd=0.04,
        block_severity_failure_modes=(),
        prev_hash="0" * 64, chain_head="0" * 64,
        isolation_class=isolation_class,  # type: ignore[arg-type]
    )
    if not complete_omitted:
        kwargs["complete"] = complete_value
    kwargs.update(overrides)  # parametrized field overrides for AC-6a
    return BenchRunReport(**kwargs)  # type: ignore[arg-type]


def _bench_case_kwargs() -> dict:
    now = datetime(2026, 5, 12, tzinfo=timezone.utc)
    return dict(
        case_id="cve-2024-21538", task_class="vuln-remediation",
        disposition="positive", difficulty="medium",
        source="curated", curation_class="held-out",
        commit_sha=None, added_at=now, last_validated_at=now,
        input_path=Path("input"), expected_path=Path("expected"),
        cassette_path=None, cassette_canary_pin="a" * 32,
        case_digest="blake3:" + "0" * 64,
    )
```

Run; confirm `ModuleNotFoundError`. Commit the red marker.

### Green — make it pass

Five Pydantic v2 `BaseModel` subclasses in the documented order, each with `model_config = ConfigDict(frozen=True, extra="forbid")` and the field shapes from `../phase-arch-design.md §Data model`. One `@field_validator("case_digest", mode="after")` on `BenchCase` enforcing `re.fullmatch(r"^blake3:[0-9a-f]{64}$", value)`. No `__init__`s, no methods beyond validators.

### Refactor — clean up

- Module docstring cites `../phase-arch-design.md §Data model` and the **six** ADRs honored: ADR-0002 (`lower_bound_95` as gate input), ADR-0003 (tier slugs are `str`), ADR-0004 (`FailureMode` shape + `severity` Literal closure), ADR-0008 (`breakdown` typed-at-the-edge), ADR-0010 (`isolation_class` for Phase 16 microVM upgrade safety), and **Phase 5 ADR-0014** (the `frozen=True, extra="forbid"` static-introspection discipline this module mirrors — cite `tests/sandbox/test_objective_signals_static.py` as the canonical precedent so a future reader understands where the pattern came from). (validator: hardened from "four phase ADRs" — Consistency F-CON-2)
- Each `BaseModel` carries a one-paragraph class docstring naming the producer and the consumer set (e.g., `BenchScore`: "Producer: rubric subprocess. Consumers: runner, cache, BenchRunReport, PromotionGate.").
- Verify `mypy --strict` is clean with `tuple[FailureMode, ...]` (Pydantic v2 supports `tuple` in field types; if mypy complains, use `tuple[FailureMode, ...]` with no covariance annotations).
- Confirm the field ordering matches the data-model section line-for-line — readers must be able to diff the source against the design doc and see a 1:1 correspondence.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/models.py` | New file — five frozen Pydantic wire types per ADRs |
| `tests/unit/test_eval_models.py` | New file — frozen, extra="forbid", bounded fields, Gap #4 + ADR-0010 defaults |

## Out of scope

- **`TaskClass` dataclass + registry** — handled by S1-03.
- **`Rubric` Protocol** — handled by S1-04.
- **Re-exporting from `codegenie.eval.__init__`** — handled by S1-05.
- **`test_bench_score_static.py` AST-walking substring ban** — handled by S1-05 (this story plants the model; the substring-ban defense lives in the package-init story so it sees every model at import time).
- **Runtime `breakdown` key validation** — handled by S3-04 (runner); ADR-0008 splits "model permits any keys" (this story) from "runner validates against `task_class.breakdown_keys`" (S3-04).
- **`commit_sha` conditional requirement** — handled by S2-02 (loader); ADR-mandated at load time, not at Pydantic time.
- **`cassette_canary_pin` format validator (32-hex check)** — deferred to S2-02 (loader) or S5-07 cassette-seed-shim. This story types it as required `str` and leaves the format check to the cassette adapter, mirroring the model-permissive / runner-strict doctrine. (validator: explicit deferral — Coverage F-COV-7)
- **Publishing eval wire types as a JSON Schema artifact** (parallel to `src/codegenie/schema/repo_context.schema.json`). Phase 6.5 consumers are in-process; cross-process consumers (Phase 11 PR provenance, Phase 13 cost ledger) read the BenchRunReport JSON directly. If a JSON Schema artifact becomes load-bearing, it lands in a Phase 11+ story with an ADR amendment. (validator: explicit deferral — Consistency F-CON-4)

## Notes for the implementer

- `BenchScore.breakdown: dict[str, float]` is *intentionally permissive* (ADR-0008 typed-at-the-edge). Do **not** add a Pydantic validator rejecting `llm_confidence` keys here — that defense lives in two other places: fence-CI (S7-01, PR-time, walks the `BreakdownKey` StrEnum AST) and the runner (S3-04, runtime, validates against `task_class.breakdown_keys`). Re-validating in three places is fine; the model is the *one* place that must stay permissive so a future task class with new keys doesn't need a model edit.
- `PromotionVerdict.requires_human_approval: Literal[True]` is the **structural marker** that `apply()` always raises (S4-04). It is not a runtime flag — it is documentation in the type system that the gate is advisory. Do not give it a default; force every constructor to write `requires_human_approval=True` explicitly. AC-7a pins this no-default discipline structurally so a future "tidy-up" PR cannot make the marker invisible.
- `BenchCase.case_digest` validator is the *only* validator this story adds. ADR-0004 / ADR-0008 both push their structural defenses out to the runner (defense-in-depth), not into Pydantic. Resist the temptation to add validators that "would help" — every one is a future API-break vector. The `case_digest` regex is canonical-only: lowercase hex, exact 64 chars, exact `blake3:` prefix, no whitespace (AC-9 enumerates the negative space + a hypothesis property test spans it).
- The `tuple[FailureMode, ...]` and `tuple[tuple[str, BenchScore], ...]` shapes are deliberate: tuples are immutable, lists are not. Pydantic v2 with `frozen=True` will still permit mutation of inner `list` fields; using `tuple` closes that hole. AC-11 pins the annotation via `typing.get_origin(...) is tuple` — a refactor to `list[...]` is caught structurally.
- `BenchRunReport.block_severity_failure_modes: tuple[str, ...]` (deduplicated *codes*, not `FailureMode`s) per ADR-0004 — the promotion gate reads `== ()` as its precondition; it does not introspect severity at promotion time because the deduplication happens at runner time.
- The `from __future__ import annotations` line is **not** required for Pydantic v2 (it resolves forward references at runtime). If you add it for stylistic consistency with the rest of the package, double-check the `field_validator` decorator still resolves `BenchCase` correctly (it does in Pydantic v2.7+).
- Per `../phase-arch-design.md §Component design — models.py`, target ≤ 150 LOC including docstrings. If you exceed 200, you have probably added behavior — re-read ADR-0004's "model is permissive, runner is strict" line.
- **Structural-walk test discipline (extension by addition).** AC-2 requires `_FROZEN_WIRE_TYPES: Final[frozenset[type[BaseModel]]]` to be collected via `inspect.getmembers(models, inspect.isclass)` — *not* enumerated by hand. This is the same pattern as `tests/unit/workflows/test_vuln_ledger_shape.py:65` (`_ledger_variant_classes`) and the Phase 5 ADR-0014 `test_objective_signals_static.py`. The payoff: a sixth wire type (hypothetical Phase 11 / Phase 16 addition) declared in `models.py` is automatically covered by the frozen+extra=forbid discipline — no test edit. The cardinality assertion (`len(_FROZEN_WIRE_TYPES) == 5`) still forces an ADR-amendment-shaped conversation when the number changes intentionally. Publish the catalog at *test*-module scope (not at production-module scope) — S1-05's substring-ban test will import it.
- **Per-class `model_config` line is the codebase convention (Rule 11).** Resist extracting a `FrozenStrict(BaseModel)` shared base. Precedent: `src/codegenie/indices/freshness.py` (6 classes with the same line), `src/codegenie/probes/layer_g/ripgrep_curated.py`, `plugins/vulnerability-remediation--node--npm/config.py`. Rule of three (third project location with 5+ models repeating the pattern) is approached but not crossed in a way that demands action today; the convention is per-class. Trigger for a future kernel-extract (when a *fifth* such location with 5+ wire models lands): propose a shared base via ADR amendment that names every existing usage as a migration target — extension by editing the convention, not by silent divergence. (validator: design-pattern guard — F-DP-1; Rule 2 YAGNI-guarded.)
- **`complete: bool` is sum-type-ready.** Today's model is binary: complete vs partial. If Phase 16 (or any later phase) adds a third state — `"crashed"`, `"superseded"`, `"externally-cancelled"` — the right move is a `Literal["complete","partial","crashed"]` widening + an ADR amendment. The current bool is the YAGNI-correct call for two states; do not preemptively promote to a Literal. (validator: design-pattern guard — F-DP-3; Rule 2 YAGNI-guarded.)
