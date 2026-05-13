# Story S1-02 — Wire models with frozen + extra=forbid

**Step:** Step 1 — Establish contracts: package scaffold, wire models, registry, Protocol
**Status:** Ready
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0001 (isolation-class field origin), ADR-0002 (`lower_bound_95` field), ADR-0003 (tier names are `str`), ADR-0004 (`FailureMode` typed; `severity: Literal["block","warn","info"]`), ADR-0008 (`BenchScore.breakdown` typed-at-the-edge), ADR-0010 (`isolation_class: Literal["subprocess","microvm"]`), Phase 5 ADR-0014 (`frozen=True, extra="forbid"` discipline)

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

- [ ] `src/codegenie/eval/models.py` exists; `from codegenie.eval.models import FailureMode, BenchScore, BenchCase, BenchRunReport, PromotionVerdict` succeeds.
- [ ] Every wire type has `model_config = ConfigDict(frozen=True, extra="forbid")`; mutation raises `pydantic.ValidationError` (`frozen=True`); extra fields raise (`extra="forbid"`).
- [ ] `BenchScore.score` is `Field(ge=0.0, le=1.0)`; `cost_usd` is `Field(ge=0.0)`; `wall_clock_ms` is `Field(ge=0)`; `breakdown` is `dict[str, float]` (typed-at-the-edge per ADR-0008 — the model does **not** enumerate keys).
- [ ] `BenchRunReport.complete: bool = True` (Gap #4): the default is `True`; the runner's cost-cap path constructs `BenchRunReport(..., complete=False)` (S3-06).
- [ ] `BenchRunReport.isolation_class: Literal["subprocess", "microvm"] = "subprocess"` (ADR-0010): default preserves current behavior; the literal is exactly two values, not three.
- [ ] `BenchRunReport.lower_bound_95: float = Field(ge=0.0, le=1.0)` and `mean_score: float = Field(ge=0.0, le=1.0)` (ADR-0002); `block_severity_failure_modes: tuple[str, ...]` (ADR-0004 — deduplicated codes, not full `FailureMode`s).
- [ ] `PromotionVerdict.current_tier: str` and `target_tier: str` (ADR-0003 — *not* `Literal`); `requires_human_approval: Literal[True]` as the structural marker.
- [ ] `BenchCase.commit_sha: str | None`; loader-time check (out of scope here) will enforce `commit_sha is not None` iff `source != "curated"` — this story documents the rule in the model's docstring but does **not** add a Pydantic validator (that lives in the loader, S2-02).
- [ ] `BenchCase.case_digest: str` matches the regex `r"^blake3:[0-9a-f]{64}$"` enforced by a `field_validator`; malformed input raises `pydantic.ValidationError`.
- [ ] The red tests from §TDD plan exist, were committed at the red marker, and are now green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/test_eval_models.py` all pass on touched files.

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
import pytest
from datetime import datetime, timezone
from pathlib import Path
from pydantic import ValidationError

from codegenie.eval.models import (
    BenchCase, BenchRunReport, BenchScore, FailureMode, PromotionVerdict,
)


def _ok_failure_mode() -> FailureMode:
    return FailureMode(code="validator.build_failed", severity="block", detail=None)


def _ok_score() -> BenchScore:
    return BenchScore(
        passed=True, score=0.83,
        breakdown={"cve_dropped": 1.0, "tests_pass": 0.66},
        failure_modes=(),
        cost_usd=0.04, wall_clock_ms=1234,
    )


def test_every_wire_type_is_frozen_and_forbids_extra():
    # frozen=True: mutation raises; extra="forbid": unknown fields raise.
    for ctor, base_kwargs in [
        (FailureMode, {"code": "c", "severity": "info"}),
        (BenchScore, {"passed": True, "score": 0.5, "breakdown": {},
                      "failure_modes": (), "cost_usd": 0.0, "wall_clock_ms": 0}),
    ]:
        instance = ctor(**base_kwargs)
        with pytest.raises(ValidationError):
            instance.code = "x"  # type: ignore[attr-defined]
        with pytest.raises(ValidationError):
            ctor(**base_kwargs, unexpected_field="x")  # type: ignore[call-arg]


def test_bench_score_score_field_is_bounded_zero_to_one():
    # ADR-0002: lower_bound_95 and score are bounded [0, 1].
    with pytest.raises(ValidationError):
        BenchScore(passed=True, score=1.5, breakdown={}, failure_modes=(),
                   cost_usd=0.0, wall_clock_ms=0)
    with pytest.raises(ValidationError):
        BenchScore(passed=True, score=-0.01, breakdown={}, failure_modes=(),
                   cost_usd=0.0, wall_clock_ms=0)


def test_bench_score_breakdown_keys_are_not_enumerated_by_the_model_adr_0008():
    # ADR-0008 typed-at-the-edge: the model permits any dict[str, float];
    # smuggling-key validation is the runner's job, not Pydantic's.
    smuggling = BenchScore(
        passed=True, score=0.5, breakdown={"llm_confidence": 0.9},
        failure_modes=(), cost_usd=0.0, wall_clock_ms=0,
    )
    assert smuggling.breakdown == {"llm_confidence": 0.9}


def test_failure_mode_severity_literal_is_exactly_three_values_adr_0004():
    # ADR-0004: severity is Literal["block", "warn", "info"].
    for sev in ("block", "warn", "info"):
        assert FailureMode(code="c", severity=sev).severity == sev
    with pytest.raises(ValidationError):
        FailureMode(code="c", severity="fatal")  # type: ignore[arg-type]


def test_bench_run_report_complete_defaults_to_true_gap_4():
    # Gap #4: complete defaults True; cost-cap path sets False.
    r = _make_report(complete_omitted=True)
    assert r.complete is True
    r2 = _make_report(complete_omitted=False, complete_value=False)
    assert r2.complete is False


def test_bench_run_report_isolation_class_defaults_subprocess_adr_0010():
    # ADR-0010: the field exists, defaults "subprocess", and the literal is exactly two values.
    r = _make_report(complete_omitted=True)
    assert r.isolation_class == "subprocess"
    with pytest.raises(ValidationError):
        _make_report(complete_omitted=True, isolation_class="firecracker")  # type: ignore[arg-type]


def test_promotion_verdict_tier_fields_are_str_not_literal_adr_0003():
    # ADR-0003: tier names are str; widening to "emerald" must not require a Python edit.
    v = PromotionVerdict(
        task_class="vuln-remediation",
        current_tier="bronze", target_tier="emerald",  # arbitrary string accepted
        evidence_sufficient=False, reasons=("case count below floor",),
        lower_bound_95=0.62, threshold_at_target=0.75, requires_human_approval=True,
    )
    assert v.target_tier == "emerald"


def test_bench_case_digest_must_match_blake3_64_hex():
    base = _bench_case_kwargs()
    BenchCase(**base)  # ok
    with pytest.raises(ValidationError):
        BenchCase(**(base | {"case_digest": "sha256:" + "a" * 64}))
    with pytest.raises(ValidationError):
        BenchCase(**(base | {"case_digest": "blake3:" + "a" * 63}))


# ---- helpers (test-local; do not export) ---------------------------------
def _make_report(complete_omitted: bool, complete_value: bool = True,
                 isolation_class: str = "subprocess") -> BenchRunReport:
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

- Module docstring cites `../phase-arch-design.md §Data model` and the four phase ADRs honored.
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

## Notes for the implementer

- `BenchScore.breakdown: dict[str, float]` is *intentionally permissive* (ADR-0008 typed-at-the-edge). Do **not** add a Pydantic validator rejecting `llm_confidence` keys here — that defense lives in two other places: fence-CI (S7-01, PR-time, walks the `BreakdownKey` StrEnum AST) and the runner (S3-04, runtime, validates against `task_class.breakdown_keys`). Re-validating in three places is fine; the model is the *one* place that must stay permissive so a future task class with new keys doesn't need a model edit.
- `PromotionVerdict.requires_human_approval: Literal[True]` is the **structural marker** that `apply()` always raises (S4-04). It is not a runtime flag — it is documentation in the type system that the gate is advisory. Do not give it a default; force every constructor to write `requires_human_approval=True` explicitly.
- `BenchCase.case_digest` validator is the *only* validator this story adds. ADR-0004 / ADR-0008 both push their structural defenses out to the runner (defense-in-depth), not into Pydantic. Resist the temptation to add validators that "would help" — every one is a future API-break vector.
- The `tuple[FailureMode, ...]` and `tuple[tuple[str, BenchScore], ...]` shapes are deliberate: tuples are immutable, lists are not. Pydantic v2 with `frozen=True` will still permit mutation of inner `list` fields; using `tuple` closes that hole.
- `BenchRunReport.block_severity_failure_modes: tuple[str, ...]` (deduplicated *codes*, not `FailureMode`s) per ADR-0004 — the promotion gate reads `== ()` as its precondition; it does not introspect severity at promotion time because the deduplication happens at runner time.
- The `from __future__ import annotations` line is **not** required for Pydantic v2 (it resolves forward references at runtime). If you add it for stylistic consistency with the rest of the package, double-check the `field_validator` decorator still resolves `BenchCase` correctly (it does in Pydantic v2.7+).
- Per `../phase-arch-design.md §Component design — models.py`, target ≤ 150 LOC including docstrings. If you exceed 200, you have probably added behavior — re-read ADR-0004's "model is permissive, runner is strict" line.
