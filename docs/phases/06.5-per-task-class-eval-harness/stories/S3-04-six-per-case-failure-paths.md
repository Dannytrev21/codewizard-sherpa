# Story S3-04 — Six typed per-case failure paths

**Step:** Step 3 — Implement the runner: asyncio fan-out, subprocess rubric, aggregator with BCa bootstrap
**Status:** Ready
**Effort:** M
**Depends on:** S3-03 (subprocess rubric invocation)
**ADRs honored:** ADR-0004 (`failure_modes.yaml` taxonomy + block-severity), ADR-0008 (BreakdownKey runtime validation + substring ban), ADR-0001 (subprocess failure surface is typed FailureMode)

## Context

S3-02 set up the worker; S3-03 wired the subprocess and handled three subprocess-level failure modes (`rubric.timeout`, `rubric.malformed_output`, and "non-zero exit ⇒ rubric.malformed_output"). This story closes the loop with the **six typed per-case failure paths** the architecture commits to. Each one maps to a `FailureMode(severity="block")` recorded on the per-case `BenchScore`; **the run does NOT abort** on any of them. The aggregator continues; the promotion gate later surfaces them in `block_severity_failure_modes`.

The six paths (arch §Components → runner.py §Failure behavior, arch §Edge cases #3–#5, #12, #14):

1. `sut.exception` — SUT raises any exception other than asyncio cancel/keyboard-interrupt.
2. `sut.timeout` — SUT exceeds `timeout_per_case_seconds`.
3. `rubric.malformed_output` — non-zero exit OR `pydantic.ValidationError` on stdout (S3-03 already maps).
4. `rubric.timeout` — subprocess exceeds `case.rubric_wall_clock_seconds` (S3-03 already maps).
5. `rubric.unknown_breakdown_key` — `BenchScore.breakdown` contains a key not in `task_class.breakdown_keys` (ADR-0008 runtime validation).
6. `rubric.unknown_failure_mode` — a rubric-emitted `FailureMode.code` is not in `task_class.failure_mode_taxonomy` (ADR-0004 runtime resolution).

Paths 1, 2, 5, 6 are this story's work. Paths 3, 4 are wired by S3-03 but this story extends the test surface to include them in the integrated run.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Control flow → Decision points #3, #4` — SUT exception/timeout and rubric subprocess failures both yield typed `FailureMode`s; case completes; run continues.
  - `../phase-arch-design.md §Edge cases #3 (rubric crash), #4 (rubric timeout), #5 (malformed JSON), #12 (banned breakdown key), #14 (SUT exception)`.
  - `../phase-arch-design.md §Agentic best practices → Error escalation` — the full bucket-to-code mapping.
  - `../phase-arch-design.md §Components → models.py` — `BenchScore.breakdown` runtime validation against `task_class.breakdown_keys` is the "typed-enum-at-the-edge" pattern.
- **Phase ADRs:**
  - `../ADRs/0004-per-task-class-failure-modes-taxonomy.md` — `failure_modes.yaml` taxonomy + `severity ∈ {block, warn, info}`; rubric-emitted codes resolved against this map; unknown codes → `rubric.unknown_failure_mode` block-severity.
  - `../ADRs/0008-breakdown-keys-strenum-with-substring-ban.md` — runtime validation of `BenchScore.breakdown` dict keys against `task_class.breakdown_keys: frozenset[str]`; unknown keys → `rubric.unknown_breakdown_key` block-severity.
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md` §Consequences — the four rubric-side codes typed.
- **Source design:** `../final-design.md §Edge cases — `BenchScore.breakdown` key smuggling defense`.

## Goal

Extend the runner's worker pipeline so all six per-case failure paths produce a `BenchScore(passed=False, failure_modes=(FailureMode(code="<typed-code>", severity="block", detail=...),))` and **never abort the run**. Define `block_severity_failure_modes` as the deduplicated, sorted tuple of block-severity codes across the run.

## Acceptance criteria

- [ ] `sut.exception` path: when `system_under_test(case)` raises `Exception` (subclasses of `BaseException` other than `KeyboardInterrupt`/`SystemExit`/`asyncio.CancelledError`), the worker produces `BenchScore(passed=False, score=0.0, breakdown={}, failure_modes=(FailureMode(code="sut.exception", severity="block", detail=f"{type(e).__name__}: {str(e)[:200]}"),), cost_usd=0.0, wall_clock_ms=<measured>)`.
- [ ] `sut.timeout` path: when `asyncio.wait_for(system_under_test(case), timeout=plan.timeout_per_case_seconds)` raises `asyncio.TimeoutError`, the worker produces `BenchScore(..., failure_modes=(FailureMode(code="sut.timeout", severity="block"),))`. **Critical**: `asyncio.wait_for`, not `signal.SIGALRM` — Phase 6's SUT is `async` (final-design §Components → runner.py "asyncio.wait_for, not SIGALRM").
- [ ] `rubric.unknown_breakdown_key`: after the rubric subprocess returns a parseable `BenchScore`, the runner validates `set(score.breakdown).issubset(task_class.breakdown_keys)`; on a violation, **the offending case** is recorded as `BenchScore(passed=False, ..., failure_modes=(FailureMode(code="rubric.unknown_breakdown_key", severity="block", detail=<offending key as string>),))` — the rubric's original score is discarded.
- [ ] `rubric.unknown_failure_mode`: after parsing, the runner iterates `score.failure_modes` and resolves each `fm.code` against `task_class.failure_mode_taxonomy`. Codes not in the taxonomy are replaced with `FailureMode(code="rubric.unknown_failure_mode", severity="block", detail=<original_code>)`. Known codes get their *severity* re-resolved from the taxonomy (the rubric's emitted severity is the *suggestion*; the taxonomy is the *source of truth* per ADR-0004 §"Facts, not judgments").
- [ ] `KeyboardInterrupt`, `SystemExit`, and `asyncio.CancelledError` are **never** mapped to `FailureMode` — they propagate. A test asserts this for each of the three.
- [ ] **Run continues on every failure path**: a 3-case bench where case-A's SUT throws, case-B's SUT times out, case-C's rubric emits a banned breakdown key produces a `BenchRunReport` with three `per_case` entries; `len(per_case) == 3`; `complete=True`.
- [ ] `block_severity_failure_modes` on the aggregate report is the deduplicated, sorted tuple of all `fm.code` where `fm.severity == "block"` across all `per_case` entries.
- [ ] `mypy --strict`, `ruff format --check`, `ruff check` clean.
- [ ] All red tests in §TDD plan exist, were committed at the red marker, and are now green.

## Implementation outline

1. Extract a `_run_case(plan, case, system_under_test, rubric_runner) -> BenchScore` function from S3-02's worker body (if not already done in S3-02's refactor).
2. Around the SUT call:
   ```python
   try:
       harness_output = await asyncio.wait_for(
           system_under_test(case), timeout=plan.timeout_per_case_seconds,
       )
   except asyncio.TimeoutError:
       return _sut_timeout_score(case, start_ns)
   except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
       raise
   except Exception as e:
       return _sut_exception_score(case, e, start_ns)
   ```
3. After the rubric subprocess returns a parseable `BenchScore` from S3-03:
   - Validate `set(score.breakdown).issubset(plan.task_class.breakdown_keys)`. On miss: pick `next(iter(unknown))` for the detail; return `_unknown_breakdown_score(...)`.
   - Resolve `failure_modes`:
     ```python
     resolved: list[FailureMode] = []
     taxonomy = plan.task_class.failure_mode_taxonomy
     for fm in score.failure_modes:
         if fm.code in taxonomy:
             resolved.append(FailureMode(code=fm.code, severity=taxonomy[fm.code], detail=fm.detail))
         else:
             resolved.append(FailureMode(code="rubric.unknown_failure_mode", severity="block", detail=fm.code))
     ```
   - Return `score.model_copy(update={"failure_modes": tuple(resolved)})`.
4. Update the aggregator (S3-02) to compute `block_severity_failure_modes`:
   ```python
   block_codes = tuple(sorted({fm.code for _, s in per_case for fm in s.failure_modes if fm.severity == "block"}))
   ```

## TDD plan — red / green / refactor

### Red — write failing tests first

Test file: `tests/unit/test_runner_failure_paths.py`

```python
import asyncio
import pytest
from codegenie.eval.models import BenchScore, FailureMode
from codegenie.eval.runner import Runner
from tests.helpers.bench import make_stub_plan
from tests.helpers.suts import (
    RaisingSUT, SleepingSUT, DeterministicSUT, multi_sut,
)
from tests.helpers.rubrics import (
    in_process_stub_rubric,
    banned_breakdown_key_rubric,
    unknown_failure_mode_rubric,
    mixed_severity_rubric,
)


@pytest.mark.asyncio
async def test_sut_exception_maps_to_sut_exception_failure_mode():
    plan = make_stub_plan(case_ids=["a"])
    sut = RaisingSUT(error=RuntimeError("nope, broken"))
    report = await Runner().execute(plan, system_under_test=sut, rubric_runner=in_process_stub_rubric)
    s = report.per_case[0][1]
    assert s.passed is False
    assert s.failure_modes[0].code == "sut.exception"
    assert s.failure_modes[0].severity == "block"
    assert "RuntimeError" in (s.failure_modes[0].detail or "")
    assert "nope, broken" in (s.failure_modes[0].detail or "")


@pytest.mark.asyncio
async def test_sut_timeout_maps_to_sut_timeout_failure_mode():
    plan = make_stub_plan(case_ids=["a"], timeout_per_case_seconds=0.1)
    sut = SleepingSUT(seconds=5.0)
    report = await Runner().execute(plan, system_under_test=sut, rubric_runner=in_process_stub_rubric)
    s = report.per_case[0][1]
    assert s.failure_modes[0].code == "sut.timeout"
    assert s.failure_modes[0].severity == "block"


@pytest.mark.asyncio
async def test_keyboard_interrupt_propagates():
    plan = make_stub_plan(case_ids=["a"])
    async def boom(case): raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        await Runner().execute(plan, system_under_test=boom, rubric_runner=in_process_stub_rubric)


@pytest.mark.asyncio
async def test_system_exit_propagates():
    plan = make_stub_plan(case_ids=["a"])
    async def bye(case): raise SystemExit(2)
    with pytest.raises(SystemExit):
        await Runner().execute(plan, system_under_test=bye, rubric_runner=in_process_stub_rubric)


@pytest.mark.asyncio
async def test_cancellederror_propagates():
    plan = make_stub_plan(case_ids=["a"])
    async def cancel(case): raise asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await Runner().execute(plan, system_under_test=cancel, rubric_runner=in_process_stub_rubric)


@pytest.mark.asyncio
async def test_unknown_breakdown_key_maps_to_block_failure():
    """ADR-0008 runtime validation: rubric emits 'llm_confidence' → block."""
    plan = make_stub_plan(case_ids=["a"], breakdown_keys=frozenset({"correctness"}))
    sut = DeterministicSUT.passing()
    report = await Runner().execute(
        plan, system_under_test=sut, rubric_runner=banned_breakdown_key_rubric("llm_confidence"),
    )
    s = report.per_case[0][1]
    assert s.passed is False
    assert s.failure_modes[0].code == "rubric.unknown_breakdown_key"
    assert s.failure_modes[0].severity == "block"
    assert s.failure_modes[0].detail == "llm_confidence"


@pytest.mark.asyncio
async def test_unknown_failure_mode_code_replaced():
    """ADR-0004 runtime resolution: rubric-emitted code not in taxonomy → unknown_failure_mode."""
    plan = make_stub_plan(case_ids=["a"], failure_mode_taxonomy={"validator.build_failed": "block"})
    sut = DeterministicSUT.passing()
    report = await Runner().execute(
        plan, system_under_test=sut,
        rubric_runner=unknown_failure_mode_rubric(emitted_code="some.typoed.code"),
    )
    s = report.per_case[0][1]
    assert s.failure_modes[0].code == "rubric.unknown_failure_mode"
    assert s.failure_modes[0].severity == "block"
    assert s.failure_modes[0].detail == "some.typoed.code"


@pytest.mark.asyncio
async def test_known_failure_mode_severity_resolved_from_taxonomy():
    """Rubric's emitted severity is suggestion; taxonomy is source of truth."""
    plan = make_stub_plan(case_ids=["a"], failure_mode_taxonomy={"recipe.unused_field": "warn"})
    rubric = unknown_failure_mode_rubric(emitted_code="recipe.unused_field", emitted_severity="block")
    sut = DeterministicSUT.passing()
    report = await Runner().execute(plan, system_under_test=sut, rubric_runner=rubric)
    s = report.per_case[0][1]
    assert s.failure_modes[0].code == "recipe.unused_field"
    assert s.failure_modes[0].severity == "warn"  # taxonomy wins


@pytest.mark.asyncio
async def test_run_does_not_abort_on_any_failure_path():
    """3 cases, 3 different failure modes — all three land in the report."""
    plan = make_stub_plan(
        case_ids=["a", "b", "c"],
        breakdown_keys=frozenset({"correctness"}),
        failure_mode_taxonomy={"validator.build_failed": "block"},
        timeout_per_case_seconds=0.1,
    )
    def sut_for(case_id):
        if case_id == "a":
            return RaisingSUT(error=ValueError("boom"))
        if case_id == "b":
            return SleepingSUT(seconds=5.0)
        return DeterministicSUT.passing()
    report = await Runner().execute(
        plan,
        system_under_test=multi_sut(sut_for),
        rubric_runner=banned_breakdown_key_rubric("llm_confidence"),
    )
    codes = {fm.code for _, s in report.per_case for fm in s.failure_modes}
    assert "sut.exception" in codes
    assert "sut.timeout" in codes
    assert "rubric.unknown_breakdown_key" in codes
    assert len(report.per_case) == 3
    assert report.complete is True


@pytest.mark.asyncio
async def test_block_severity_failure_modes_is_dedup_sorted_block_only():
    plan = make_stub_plan(case_ids=["a", "b"], failure_mode_taxonomy={
        "validator.build_failed": "block",
        "recipe.unused_field": "warn",
    })
    report = await Runner().execute(
        plan,
        system_under_test=DeterministicSUT.passing(),
        rubric_runner=mixed_severity_rubric({
            "a": [("validator.build_failed", "block")],
            "b": [("recipe.unused_field", "warn")],
        }),
    )
    assert report.block_severity_failure_modes == ("validator.build_failed",)
```

Run all ten; confirm failures. Commit as the red marker.

### Green — make them pass

Wrap the SUT call in `try/except` with the cancel-exception passthrough. Add the breakdown-key validation and failure-mode taxonomy resolution after `BenchScore.model_validate_json`. Update the aggregator to compute `block_severity_failure_modes` from the deduplicated, sorted block-severity set.

### Refactor — clean up

- Pull each failure-mode mapping into a named helper (`_sut_exception_score`, `_sut_timeout_score`, `_unknown_breakdown_score`, `_resolve_failure_modes`) — readable and testable in isolation.
- Add a module-level table comment listing the six codes and their architectural origins (ADR refs).
- Structured logs: `log.warning("case_failed", code=fm.code, severity=fm.severity, detail=fm.detail)` on every block-severity emission.
- Verify the helpers are pure (no `await`, no I/O); they take inputs and return a `BenchScore`. Pure helpers + a thin async glue function is the clean refactor target.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/runner.py` | Add the six failure-path mappings and aggregator's `block_severity_failure_modes` computation |
| `tests/unit/test_runner_failure_paths.py` | New: ten tests covering all six paths + propagation guarantees + aggregator dedup |
| `tests/helpers/suts.py` | Add `RaisingSUT`, `SleepingSUT`, `DeterministicSUT`, `multi_sut` |
| `tests/helpers/rubrics.py` | Add `banned_breakdown_key_rubric`, `unknown_failure_mode_rubric`, `mixed_severity_rubric` (all in-process — subprocess versions live in S3-07) |

## Out of scope

- `rubric.timeout` and `rubric.malformed_output` *plumbing* — S3-03 owns these; this story extends the test surface for the integrated run but does not change the subprocess module.
- Adversarial subprocess fixtures (`tests/fixtures/bench/adversarial-task-class/`) — S3-07.
- Cost-cap path (`run_id = "partial:..."`) — S3-06.
- BCa bootstrap on `lower_bound_95` — S3-05.
- Promotion gate's consumption of `block_severity_failure_modes` — S4-04.

## Notes for the implementer

- **`asyncio.wait_for`, not `signal.SIGALRM`.** Called out in `final-design.md §Components → runner.py` as a critic-flagged correctness issue (SIGALRM doesn't compose with asyncio). The temptation to "just use a signal handler" is wrong; the test for `sut.timeout` will catch it because `signal.SIGALRM` won't fire inside the event loop.
- **`asyncio.CancelledError` passthrough is critical.** S3-06's cost-cap path uses `asyncio.Task.cancel()` to abort outstanding workers; mapping `CancelledError` to a `FailureMode` would silently turn cost-cap into "all cases failed" instead of "run aborted." The explicit `CancelledError` propagation test is the structural guard.
- **Taxonomy severity overrides rubric severity.** Non-obvious. ADR-0004 §"Facts, not judgments" — the rubric is allowed to *report* what happened; the taxonomy decides what *severity* that event is. A rubric that emits `severity="warn"` for a code the taxonomy classifies as `"block"` must produce a `"block"`-severity `FailureMode`. The test for this is load-bearing.
- **`task_class.breakdown_keys` is `frozenset[str]`** (per arch §Data model). The runtime check is `set(score.breakdown).issubset(task_class.breakdown_keys)`. Pick `next(iter(unknown))` for the detail — if multiple keys are unknown, this surfaces one; the rubric author fixes one and re-runs to discover the next. The `detail` field is single-string by ADR-0004.
- **Defense in depth**: ADR-0008 says the fence-CI substring ban (`tests/unit/test_eval_fence.py`) catches banned keys at PR time; this runtime check is the second layer. Both must be live; one is not enough.
- **Don't conflate "warn-severity" with "passed=False"**. A case can have `passed=True` AND `failure_modes=(FailureMode(code="recipe.unused_field", severity="warn"),)`. `block_severity_failure_modes` filters on severity; the rubric's `passed` field is independent. ADR-0004 §Tradeoffs explicitly allows this asymmetry.
- **The test fixture rubrics are in-process** (S3-04 reuses S3-02's in-process injection seam). Subprocess versions of the adversarial rubrics live in S3-07's bench fixture portfolio.
