# Story S3-04 — Six typed per-case failure paths

**Step:** Step 3 — Implement the runner: asyncio fan-out, subprocess rubric, aggregator with BCa bootstrap
**Status:** Ready (HARDENED 2026-05-27)
**Effort:** M
**Depends on:** S3-03 (subprocess rubric invocation HARDENED — `SubprocessRubricRunner.run` returns `BenchScore` on rubric-side failure, never raises); S3-02 (asyncio fan-out HARDENED — `_run_case` extracted; queue is `tuple[str, BenchScore] | _Sentinel`; aggregator `_aggregate` already owns `block_severity_failure_modes`; `Runner.execute(plan, *, system_under_test, rubric_runner, cache_dir, timeout_per_case_seconds, ...)` is the canonical signature; `make_stub_plan(tmp_path, *, case_ids=...)` is the helper shape)
**ADRs honored:** ADR-0001 (subprocess failure surface is typed `FailureMode`), ADR-0004 (`failure_modes.yaml` taxonomy + severity resolution), ADR-0008 (BreakdownKey runtime validation + substring ban)
**ADR amendments required as preconditions:**
1. **ADR-0004 §Consequences seed taxonomy** — replace `sut.cancelled` with `sut.timeout`. `asyncio.CancelledError` is reserved for S3-06's cost-cap path and must NOT be mapped to a `FailureMode`; the SUT-exceeds-timeout case is its own structurally distinct code. The story implements `sut.timeout`; the executor MUST land the ADR amendment in the same PR (Rule 7 — surface conflicts, don't average).
2. **ADR-0004 §Consequences** — add explicit bullet: "Rubric-emitted severity on a *known* code is overridden by the taxonomy's severity. The rubric reports the event; the taxonomy classifies it. The rubric's emitted severity is discarded, not merged." Currently implicit in "Facts, not judgments" but not spelled out.
3. **ADR-0008 §Consequences** — add explicit bullet: "When `rubric.unknown_breakdown_key` fires, the rubric's original `BenchScore.score`, `breakdown`, and `passed` are **discarded** (replaced with `score=0.0`, `breakdown={}`, `passed=False`). `cost_usd` and `wall_clock_ms` are **preserved** (the rubric did the work; Phase 13's cost dashboard must reflect it)."

## Validation notes

Hardened 2026-05-27 by the `phase-story-validator` skill. 36 critic findings (10 blocks, 21 hardens, 5 nits) applied; full audit at `_validation/S3-04-six-per-case-failure-paths.md`. Headlines:

- **F-CON-1/2/3/4/11 (blocks).** Five concrete drifts against HARDENED S3-02 fixed: `plan.timeout_per_case_seconds` → `timeout_per_case_seconds` (execute() kwarg, never RunPlan); `make_stub_plan(case_ids=...)` → `make_stub_plan(tmp_path, *, case_ids=...)` with additive `breakdown_keys=` / `failure_mode_taxonomy=` widening; worker enqueues `(case_id, score)` tuples (not bare BenchScore); aggregator `block_severity_failure_modes` computation is owned by HARDENED S3-02 (removed re-prescription; AC reframed as integration assertion); rubric helpers are classes implementing `RubricRunner` Protocol (not bare async callables).
- **F-CON-1 + ADR-0004 amendment.** Story uses `sut.timeout` (correct) but ADR-0004 seed taxonomy says `sut.cancelled`. Surfaced as an ADR-amendment precondition; executor must ship the amendment in the same PR.
- **C-08 (block).** Catch narrowed to `Exception` (NOT `BaseException`). Custom `BaseException` subclasses propagate — pinned by a red test.
- **C-09 (block).** SUT returning non-`Mapping` output mapped to `sut.exception` with `detail='harness_output_not_mapping: <type>'`. The rubric subprocess sees garbage JSON otherwise.
- **C-10 / F-TQ-8 (block).** Multi-banned-key non-determinism closed: `min(unknown_keys)` (NOT `next(iter(set))`) for the deterministic detail. Pinned by a red test with 3 unknown keys.
- **C-11 / F-DP-3 (block).** Reserved-namespace smuggling defense added. Rubrics may NOT emit codes prefixed `sut.` or `rubric.`; if they do, the resolver replaces with `rubric.unknown_failure_mode(detail=f'reserved_code:{original}')` regardless of taxonomy registration. A buggy rubric can no longer fabricate runner-only events.
- **C-12 (harden).** Runner-emitted codes (the six) bypass `task_class.failure_mode_taxonomy` resolution — severity hardcoded `"block"` by the runner. ACs pin the asymmetry.
- **C-15 / C-16 / F-TQ-16 (harden).** Universal 200-char `detail` truncation across ALL six paths (not just `sut.exception`). Pinned by a 10kB-message red test.
- **C-17 / F-CON-5 (harden).** `wall_clock_ms = (time.monotonic_ns() - start_ns) // 1_000_000` measurement convention pinned to match S3-03 AC-16.
- **C-18 / C-19 (harden).** Failure-path BenchScores ARE cached (S3-02's `cache.put` policy applies uniformly); `OSError` log-and-continue inherits S3-02 AC-10a. Pinned by red tests on `sut.timeout` re-run identity.
- **C-20 (harden).** Structural fence test: AST-walk `runner.py` asserts `signal.SIGALRM` is not referenced. SIGALRM-in-asyncio is the load-bearing wrong-implementation; behavior tests alone don't catch it.
- **C-23 (harden).** `asyncio.CancelledError` raised from the rubric subprocess (S3-06 cost-cap path) must propagate, NOT be mapped to `rubric.malformed_output`. Pinned by red test.
- **F-DP-1 (harden).** Registry promotion (the F-DP-2 thread from S3-03's validation report) is **explicitly deferred** in Out-of-scope. The 6 mappings have 3 distinct constructor shapes; abstraction would unify call sites that don't share a useful signature (Rule 2). Closes the thread by saying so, rather than silent skip.
- **F-DP-2 (harden).** `_resolve_failure_modes(modes: tuple[FailureMode, ...], taxonomy: Mapping[str, Severity]) -> tuple[FailureMode, ...]` extracted as a **pure** module-level helper with its own AC (AC-12) and its own unit-test file with a Hypothesis property. The taxonomy-overrides-rubric-severity logic is the most mutation-vulnerable code in this story; isolating it shortens the catch loop.
- **F-DP-5 (nit→adopted).** Smart constructor `_failure_score(code, *, detail=None, severity="block", wall_clock_ms, cost_usd=0.0)` collapses the 4 helpers' shared `BenchScore` literal-construction into 1 (rule-of-three at the literal level — 4 sites).
- **F-TQ-1/2/3/4/5/6/7 (blocks).** Test-quality holes patched: `wall_clock_ms`+`cost_usd` pinned on `sut.exception`; elapsed-time enforcement on `sut.timeout` (`< 1s` when cap is `0.1s`); `rubric.call_count == 0` on propagation tests; mixed known+unknown codes test added; warn→block upgrade symmetry test added; per-case-id pairing (not flattened-set) pinned; dedup + sort pinned in `block_severity_failure_modes` (with overlap from S3-02 noted).
- **F-TQ-13 (harden).** S3-02 AC-15 universal report-shape repetition discipline (`isinstance(report.per_case, tuple)`, `report.isolation_class == "subprocess"`) propagated to every S3-04 test.

## Context

S3-02 (HARDENED) shipped the runner skeleton: `Runner.execute` fans out per-case workers under a bounded semaphore, each worker runs as `_run_case`, scores land on `asyncio.Queue[tuple[str, BenchScore] | _Sentinel]`, and a single `_aggregate` task computes `BenchRunReport` — already including `block_severity_failure_modes` as a deduplicated, sorted tuple of block-severity codes. S3-03 (HARDENED) shipped `SubprocessRubricRunner` which substitutes for S3-02's in-process stub rubric and produces `FailureMode(code="rubric.timeout" | "rubric.malformed_output", severity="block")` BenchScores **without raising** for those two paths.

S3-04 closes the loop by extending `_run_case`'s body to wrap the existing `await asyncio.wait_for(system_under_test(case), timeout=timeout_per_case_seconds)` and the existing `await rubric_runner.run(...)` call sites with typed-exception → typed-FailureMode mapping, and by validating the rubric's returned `BenchScore` against the task class's `breakdown_keys` and `failure_mode_taxonomy`. **The aggregator is unchanged.** **`_run_case` is not re-extracted.**

The six paths (arch §Components → runner.py §Failure behavior, arch §Edge cases #3–#5, #12, #14):

| # | Code | Trigger | Owner |
|---|---|---|---|
| 1 | `sut.exception` | SUT raises `Exception` subclass other than `KeyboardInterrupt`/`SystemExit`/`asyncio.CancelledError`/SUT-yield returns non-`Mapping` | S3-04 |
| 2 | `sut.timeout` | `asyncio.wait_for(system_under_test(case), timeout=timeout_per_case_seconds)` raises `asyncio.TimeoutError` | S3-04 |
| 3 | `rubric.malformed_output` | non-zero exit OR `pydantic.ValidationError` on stdout | S3-03 (S3-04 extends test surface only) |
| 4 | `rubric.timeout` | subprocess exceeds `wall_clock_cap_seconds` | S3-03 (S3-04 extends test surface only) |
| 5 | `rubric.unknown_breakdown_key` | `BenchScore.breakdown` contains a key not in `task_class.breakdown_keys` (ADR-0008) | S3-04 |
| 6 | `rubric.unknown_failure_mode` | rubric-emitted `FailureMode.code` is not in `task_class.failure_mode_taxonomy` OR is in the runner-reserved namespace (`sut.*`, `rubric.*`) (ADR-0004 + reserved-namespace defense) | S3-04 |

Severity for all six is hardcoded `"block"` by the runner — they are runner-emitted and bypass the per-task-class taxonomy resolution. The taxonomy governs **rubric-emitted** codes only.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Control flow → Decision points #3, #4` — SUT exception/timeout and rubric subprocess failures both yield typed `FailureMode`s; case completes; run continues.
  - `../phase-arch-design.md §Edge cases #3 (rubric crash), #4 (rubric timeout), #5 (malformed JSON), #12 (banned breakdown key), #14 (SUT exception), #21 (passed=True + warn failure_modes)`.
  - `../phase-arch-design.md §Agentic best practices → Error escalation` — the full bucket-to-code mapping.
  - `../phase-arch-design.md §Components → models.py` — `BenchScore.breakdown` runtime validation against `task_class.breakdown_keys` is the "typed-enum-at-the-edge" pattern.
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md` §Consequences row 3 — the four rubric-side typed codes.
  - `../ADRs/0004-per-task-class-failure-modes-taxonomy.md` — severity resolution (rubric-emitted codes only); the executor MUST amend §Consequences to (a) replace `sut.cancelled` with `sut.timeout` in the seed taxonomy, (b) spell out the "taxonomy severity overrides rubric severity" semantic.
  - `../ADRs/0008-breakdown-keys-strenum-with-substring-ban.md` — runtime validation of `BenchScore.breakdown` dict keys; the executor MUST amend §Consequences to spell out the score-discard semantic.
- **Sibling stories (HARDENED — the contracts THIS story consumes):**
  - `S3-02-asyncio-fan-out-and-aggregator.md` — `Runner.execute(plan, *, system_under_test, rubric_runner, cache_dir, timeout_per_case_seconds, ...)`; queue type `tuple[str, BenchScore] | _Sentinel`; `_run_case` extracted; `_aggregate` owns `block_severity_failure_modes`; `make_stub_plan(tmp_path, *, case_ids=...)`; `InProcessStubRubric` class implements `RubricRunner` Protocol; AC-12 covers `KeyboardInterrupt` + `asyncio.CancelledError` propagation; AC-15 universal report-shape assertions.
  - `S3-03-subprocess-rubric-invocation.md` — `SubprocessRubricRunner.run(self, rubric_path, case, harness_output, *, wall_clock_cap_seconds) -> BenchScore`; returns BenchScore on rubric-side failure, never raises; `wall_clock_ms = (time.monotonic_ns() - start_ns) // 1_000_000` measurement convention (AC-16).
  - `S1-02-wire-models-frozen-extra-forbid.md` — `BenchScore`, `BenchRunReport`, `FailureMode` shapes (frozen, `extra="forbid"`).
  - `S1-03-taskclass-dataclass-and-registry.md` — `TaskClass.breakdown_keys: frozenset[str]`, `TaskClass.failure_mode_taxonomy: Mapping[str, Literal["block","warn","info"]]`.
- **Source design:** `../final-design.md §Components → runner.py` ("`asyncio.wait_for`, not SIGALRM"); §"Block-severity definition"; §"`BenchScore.breakdown` key smuggling defense".

## Goal

Extend the HARDENED-S3-02 `_run_case` body to map four runner-visible failure conditions and two rubric-output validation failures into typed `FailureMode(severity="block")` BenchScores, **never aborting the run**. The aggregator is unchanged: S3-02's `_aggregate` already deduplicates and sorts `block_severity_failure_modes` from any block-severity FailureMode on any `per_case` entry. This story's job is to (a) populate those FailureModes, (b) extract a pure `_resolve_failure_modes(modes, taxonomy)` helper for the taxonomy-resolution logic, (c) install the reserved-namespace smuggling defense, and (d) keep `asyncio.CancelledError` + `KeyboardInterrupt` + `SystemExit` propagating.

## Acceptance criteria

### Exception discipline + propagation

- [ ] **AC-1.** `sut.exception` path: when `system_under_test(case)` raises `Exception` (NOT `BaseException`), the worker enqueues `(case.case_id, _failure_score(code="sut.exception", detail=f"{type(e).__name__}: {str(e)[:200]}", wall_clock_ms=<measured>))`. **The catch is `except Exception as e:`, not `except BaseException as e:`** — pathological user `BaseException` subclasses propagate. Red test: a `class Custom(BaseException): pass` raised from the SUT escapes `Runner.execute(...)` unmapped.

- [ ] **AC-2.** `sut.timeout` path: when `asyncio.wait_for(system_under_test(case), timeout=timeout_per_case_seconds)` raises `asyncio.TimeoutError`, the worker enqueues `(case.case_id, _failure_score(code="sut.timeout", detail=None, wall_clock_ms=<measured>))`. **Critical**: `asyncio.wait_for`, NOT `signal.SIGALRM` (final-design.md §Components → runner.py — SIGALRM-in-asyncio is the load-bearing wrong-implementation). The `timeout_per_case_seconds` value is the same `Runner.execute(...)` kwarg threaded through `_run_case` — NOT a `RunPlan` field, NOT a `BenchCase` field.

- [ ] **AC-2a.** **Structural no-SIGALRM fence.** `tests/fence/test_runner_no_sigalrm.py` AST-walks `src/codegenie/eval/runner.py`; asserts no `import signal` and no `signal.SIGALRM` reference appears. A SIGALRM-based timeout would *also* eventually produce `sut.timeout`, just non-deterministically — behavior tests alone don't catch it.

- [ ] **AC-3.** Non-`Mapping` SUT output: if `system_under_test(case)` returns a non-`Mapping` value (e.g., `None`, `str`, `int`), `_run_case` raises `TypeError(f"harness_output must be Mapping; got {type(out).__name__}")` BEFORE calling `rubric_runner.run`. The `TypeError` is caught by the `except Exception` branch (AC-1) → emitted as `sut.exception` with `detail=f"TypeError: harness_output must be Mapping; got {type(out).__name__}"`. The rubric subprocess never sees garbage JSON.

- [ ] **AC-4.** **Propagation (S3-02 AC-12 widening).** `KeyboardInterrupt`, `SystemExit`, AND `asyncio.CancelledError` raised from either the SUT or the rubric subprocess **never map to a `FailureMode`** — they propagate out of `Runner.execute(...)`. Three separate red tests cover the SUT side; one red test covers the rubric subprocess side. For each, assert (a) the exception propagates with `pytest.raises(...)`, (b) `rubric.call_count == 0` for the SUT-side tests (the case did not reach the rubric), (c) no leaked tasks (`asyncio.all_tasks() - {asyncio.current_task()}` is empty after propagation). `SystemExit` is an additive widening of S3-02 AC-12 (which covered only `KeyboardInterrupt`+`CancelledError`).

- [ ] **AC-4a.** **External cancel (S3-06 cost-cap path).** A red test creates a `Runner.execute(...)` task, then calls `task.cancel()` from outside. Assert `asyncio.CancelledError` propagates AND no `FailureMode` was synthesized for any case mid-run AND no leaked tasks. This is the actual S3-06 cost-cap path semantics; AC-4's "SUT raises CancelledError" is a separate scenario.

### Rubric output validation (after rubric returns)

- [ ] **AC-5.** `rubric.unknown_breakdown_key`: after `rubric_runner.run(...)` returns a parseable `BenchScore`, the runner validates `unknown_keys = set(score.breakdown) - task_class.breakdown_keys`. On a non-empty `unknown_keys`, the offending case BenchScore is replaced with `_failure_score(code="rubric.unknown_breakdown_key", detail=min(unknown_keys), wall_clock_ms=<measured>, cost_usd=score.cost_usd)`. **Use `min(unknown_keys)` — NOT `next(iter(unknown_keys))`** — set iteration order is non-deterministic; `min` is stable. The rubric's original `passed`, `score`, `breakdown` are **discarded**; `cost_usd` is **preserved** (the rubric did the work). Pinned by red test with 3 unknown keys asserting `detail == "apple"` (lexicographically smallest of `{"zebra", "apple", "mango"}`).

- [ ] **AC-6.** `rubric.unknown_failure_mode`: after parsing, the runner replaces the `BenchScore` with `score.model_copy(update={"failure_modes": _resolve_failure_modes(score.failure_modes, task_class.failure_mode_taxonomy)})`. The resolver (AC-12) re-resolves severity, replaces unknown codes, and rejects reserved-namespace codes.

### Reserved-namespace smuggling defense (F-DP-3 / C-11)

- [ ] **AC-7.** **Rubrics may NOT emit codes in the runner-reserved namespace.** A module-level `_RESERVED_RUNNER_CODES: Final[frozenset[str]] = frozenset({"sut.exception", "sut.timeout", "rubric.malformed_output", "rubric.timeout", "rubric.unknown_breakdown_key", "rubric.unknown_failure_mode"})` declares the set. `_resolve_failure_modes` replaces any rubric-emitted `fm.code in _RESERVED_RUNNER_CODES` with `FailureMode(code="rubric.unknown_failure_mode", severity="block", detail=f"reserved_code:{fm.code}")` — **regardless of whether the code is registered in the taxonomy**. A buggy or adversarial rubric can no longer fabricate runner-only events. Red test: `_resolve_failure_modes((FailureMode(code="sut.exception", severity="warn", detail="fake"),), {"sut.exception": "block"})` returns `(FailureMode(code="rubric.unknown_failure_mode", severity="block", detail="reserved_code:sut.exception"),)` — note the taxonomy registration does NOT save the smuggled code.

### Runner-emitted codes bypass taxonomy (C-12)

- [ ] **AC-8.** The six runner-emitted codes (`sut.exception`, `sut.timeout`, `rubric.malformed_output`, `rubric.timeout`, `rubric.unknown_breakdown_key`, `rubric.unknown_failure_mode`) carry hardcoded `severity="block"` from the runner and bypass `task_class.failure_mode_taxonomy` resolution. A task class whose `failure_modes.yaml` omits one of these codes does NOT cause the runner to emit a different severity. Red test: a task class with `failure_mode_taxonomy={}` (empty); SUT raises `RuntimeError`; emitted FailureMode is `(code="sut.exception", severity="block", ...)`.

### Run continues + per-case pairing (C-13, C-14, F-TQ-6)

- [ ] **AC-9.** **Run continues on every failure path.** A 3-case bench (`case_ids=["a", "b", "c"]`) where case-A's SUT raises `ValueError("boom")`, case-B's SUT sleeps past `timeout_per_case_seconds=0.1`, and case-C's rubric emits a banned breakdown key (`{"llm_confidence": 0.9}` while `breakdown_keys=frozenset({"correctness"})`) produces a `BenchRunReport` with `len(report.per_case) == 3` and `report.complete is True`. Per-case-id pairing pinned: `{cid: s.failure_modes[0].code for cid, s in report.per_case} == {"a": "sut.exception", "b": "sut.timeout", "c": "rubric.unknown_breakdown_key"}` (NOT a flattened set — a wrong impl that transposes case_ids on failure assignment would pass a set-based assertion).

- [ ] **AC-9a.** **`passed=False` + empty `failure_modes` policy.** If the rubric returns `BenchScore(passed=False, failure_modes=(), ...)`, the runner does NOT inject a failure mode. The score flows through unchanged. Red test pins. Arch Edge case #21 — rubric-author choice; gate is allowed to see "failed but undiagnosed."

- [ ] **AC-9b.** **`passed=True` + `warn`/`info` failure modes policy.** When `score.passed is True` and `score.failure_modes == (FailureMode(code="recipe.unused_field", severity="warn"),)`, the case survives `passed=True`; the warn code does NOT appear in `report.block_severity_failure_modes`; `report.passed_count` includes this case. Red test pins (independent of AC-11 — observation, not aggregation).

### Aggregator integration (NOT re-prescription — F-CON-4)

- [ ] **AC-10.** S3-02's aggregator (`_aggregate`) is unchanged. The story does NOT touch `_aggregate`. **Integration assertion**: in AC-9's 3-case bench, `report.block_severity_failure_modes == ("rubric.unknown_breakdown_key", "sut.exception", "sut.timeout")` (deduplicated, lexicographically sorted by S3-02's existing computation). `report.passed_count == 0` (no failure path emits `passed=True`).

- [ ] **AC-11.** **Dedup + sort coverage** (extends S3-02's coverage; specific to the 6 new failure codes). A 4-case bench where two cases emit `sut.exception` and two cases emit different rubric-warn-codes asserts `report.block_severity_failure_modes == ("sut.exception",)` — single dedup'd entry, no warn codes leaking, no duplicates.

### Pure resolver helper (F-DP-2)

- [ ] **AC-12.** `_resolve_failure_modes(failure_modes: tuple[FailureMode, ...], taxonomy: Mapping[str, Severity]) -> tuple[FailureMode, ...]` exists as a **pure** module-level function in `src/codegenie/eval/runner.py` (or a sibling `_failure_modes.py` if extracted further). No `await`, no I/O, no closure over `plan`. Behavior:
  - For each input `fm` in order:
    - If `fm.code in _RESERVED_RUNNER_CODES`: replace with `FailureMode(code="rubric.unknown_failure_mode", severity="block", detail=f"reserved_code:{fm.code}")` (AC-7).
    - Else if `fm.code in taxonomy`: emit `FailureMode(code=fm.code, severity=taxonomy[fm.code], detail=fm.detail)` (taxonomy severity wins; rubric severity discarded).
    - Else: emit `FailureMode(code="rubric.unknown_failure_mode", severity="block", detail=fm.code)`.
  - Order is preserved (the output tuple has `len(input)` entries in the same positions).
  - Tests:
    - **At least 6 unit tests** in `tests/unit/test_resolve_failure_modes.py` covering: empty input → empty output; preserved known code with severity rewrite (block→warn); upgrade (warn→block); upgrade (warn→info); unknown code → `rubric.unknown_failure_mode`; reserved-namespace code → rejected with `reserved_code:` prefix.
    - **Hypothesis property test** (in same file): draw `taxonomy: dict[str, Literal["block","warn","info"]]` (3-10 entries with non-reserved codes) and `incoming: list[FailureMode]` (0-5, codes drawn 50/50 from taxonomy keys vs random non-reserved strings); assert `len(resolved) == len(incoming)`, every input code in taxonomy is preserved at the same index with `severity = taxonomy[code]`, every input code NOT in taxonomy resolves to `("rubric.unknown_failure_mode", "block", detail=original_code)` at the same index.
    - **Mixed known+unknown test**: rubric emits `(("validator.build_failed", "warn"), ("typoed.code", "block"), ("recipe.unused_field", "warn"))`; taxonomy `{"validator.build_failed": "block", "recipe.unused_field": "warn"}`. Assert resolved is `(("validator.build_failed", "block"), ("rubric.unknown_failure_mode", "block", "typoed.code"), ("recipe.unused_field", "warn"))` — ordering preserved, per-code resolution independent (a wrong impl that replaces ALL when ANY is unknown fails this).

### Detail truncation (C-16 / F-TQ-16) + measurement (C-17 / F-CON-5)

- [ ] **AC-13.** Every `FailureMode.detail` emitted by the runner is truncated to `<= 200` characters via the smart constructor (`_failure_score(detail=...)` slices). Red test: SUT raises `RuntimeError("x" * 1000)` → `len(emitted_fm.detail) <= 200`. Same for `rubric.unknown_breakdown_key` with a 1kB key name.

- [ ] **AC-14.** Every failure-path BenchScore has `wall_clock_ms = (time.monotonic_ns() - start_ns) // 1_000_000` measured from `_run_case` entry to score emission — same convention as S3-03 AC-16. Red test: SUT `await asyncio.sleep(0.05)` then raises → emitted BenchScore has `wall_clock_ms >= 50`. A wrong impl returning `wall_clock_ms=0` fails.

### Cache discipline on failure-path scores (C-18 / C-19)

- [ ] **AC-15.** Failure-path BenchScores ARE cached via S3-02's existing `cache.put(plan.cache_keys[case.case_id], score, cache_dir)` call site in `_run_case`. The story does NOT add a new cache path; it relies on the existing one. Red test: a SUT that raises on every call + a cache hit on second invocation → SUT `call_count == 1`, second `report.per_case[0][1] is cached_score` (identity); the `sut.exception` is not re-synthesized.

- [ ] **AC-16.** `cache.put` `OSError` on failure-path scores inherits S3-02 AC-10a: log at `WARNING` (`runner.cache_put_failed`), score still enters the queue. Red test parallels S3-02's `test_cache_put_oserror_logs_and_continues` but with a `sut.timeout` score.

### Universal report-shape repetition (S3-02 AC-15 discipline / F-TQ-13)

- [ ] **AC-17.** Every S3-04 test that produces a `BenchRunReport` asserts `isinstance(report.per_case, tuple)` AND `report.isolation_class == "subprocess"`. A wrong impl that returns `list` or conditionalizes `isolation_class` is caught by repetition.

### Tooling

- [ ] **AC-18.** `mypy --strict`, `ruff format --check`, `ruff check` clean on touched files. All red tests listed in §TDD plan exist, were committed at the red marker, and are now green.

## Implementation outline

S3-02 (HARDENED) already extracted `_run_case` (see S3-02 §Implementation outline step 5). This story **widens** that body — it does NOT re-extract.

1. **Define module-level constants and helpers in `src/codegenie/eval/runner.py`:**

   ```python
   from typing import Final, Literal, Mapping

   Severity = Literal["block", "warn", "info"]

   _RESERVED_RUNNER_CODES: Final[frozenset[str]] = frozenset({
       "sut.exception",
       "sut.timeout",
       "rubric.malformed_output",
       "rubric.timeout",
       "rubric.unknown_breakdown_key",
       "rubric.unknown_failure_mode",
   })

   _DETAIL_MAX_LEN: Final[int] = 200

   def _failure_score(
       code: str,
       *,
       detail: str | None = None,
       severity: Severity = "block",
       wall_clock_ms: int,
       cost_usd: float = 0.0,
   ) -> BenchScore:
       """Smart constructor — collapses the 4 failure-helper literal-construction sites."""
       truncated = detail if detail is None else detail[:_DETAIL_MAX_LEN]
       return BenchScore(
           passed=False, score=0.0, breakdown={},
           failure_modes=(FailureMode(code=code, severity=severity, detail=truncated),),
           cost_usd=cost_usd, wall_clock_ms=wall_clock_ms,
       )

   def _resolve_failure_modes(
       failure_modes: tuple[FailureMode, ...],
       taxonomy: Mapping[str, Severity],
   ) -> tuple[FailureMode, ...]:
       """Pure. Re-resolve severity from taxonomy; reject reserved-namespace; replace unknown codes."""
       out: list[FailureMode] = []
       for fm in failure_modes:
           if fm.code in _RESERVED_RUNNER_CODES:
               out.append(FailureMode(
                   code="rubric.unknown_failure_mode",
                   severity="block",
                   detail=f"reserved_code:{fm.code}"[:_DETAIL_MAX_LEN],
               ))
           elif fm.code in taxonomy:
               out.append(FailureMode(code=fm.code, severity=taxonomy[fm.code], detail=fm.detail))
           else:
               out.append(FailureMode(
                   code="rubric.unknown_failure_mode",
                   severity="block",
                   detail=fm.code[:_DETAIL_MAX_LEN],
               ))
       return tuple(out)
   ```

2. **Widen `_run_case`** (do NOT re-extract — S3-02 already owns it). Replace the existing `await asyncio.wait_for(...)` + `await rubric_runner.run(...)` blocks with:

   ```python
   import time

   async def _run_case(
       case: BenchCase, plan: RunPlan, sem: asyncio.Semaphore,
       queue: "asyncio.Queue[tuple[str, BenchScore] | _Sentinel]",
       *,
       system_under_test: Callable[..., Awaitable[Mapping[str, Any]]],
       rubric_runner: RubricRunner,
       cache_dir: Path,
       timeout_per_case_seconds: float,
   ) -> None:
       async with sem:
           log = structlog.get_logger().bind(case_id=case.case_id, run_id=plan.run_id)
           start_ns = time.monotonic_ns()
           # cache probe unchanged from S3-02
           cached = cache.get(plan.cache_keys[case.case_id], cache_dir)
           if cached is not None:
               await queue.put((case.case_id, cached))
               return

           # AC-1 / AC-2 / AC-3 / AC-4 — SUT call with typed failure mapping
           try:
               harness_output = await asyncio.wait_for(
                   system_under_test(case), timeout=timeout_per_case_seconds,
               )
           except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
               raise
           except asyncio.TimeoutError:
               score = _failure_score(
                   code="sut.timeout", detail=None,
                   wall_clock_ms=_elapsed_ms(start_ns),
               )
               _put_in_cache(plan, case, score, cache_dir, log)
               await queue.put((case.case_id, score))
               return
           except Exception as e:
               score = _failure_score(
                   code="sut.exception",
                   detail=f"{type(e).__name__}: {str(e)[:200]}",
                   wall_clock_ms=_elapsed_ms(start_ns),
               )
               _put_in_cache(plan, case, score, cache_dir, log)
               await queue.put((case.case_id, score))
               return

           # AC-3 — non-Mapping SUT output → TypeError → maps via the except Exception above
           if not isinstance(harness_output, Mapping):
               raise TypeError(
                   f"harness_output must be Mapping; got {type(harness_output).__name__}",
               )
           # ^^ this propagates back up to the try; restructure: validate BEFORE the try, OR
           # raise the TypeError inside the try block. Use the latter (simpler control flow):
           # move the isinstance check INSIDE the try, between the wait_for and the rubric call.

           # rubric call — S3-03 promises this NEVER raises for rubric.timeout/malformed_output
           # (returns BenchScore with typed FailureMode instead). CancelledError MUST propagate.
           try:
               raw_score = await rubric_runner.run(
                   plan.task_class.bench_path / "rubric.py",
                   case, harness_output,
                   wall_clock_cap_seconds=timeout_per_case_seconds,
               )
           except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
               raise   # AC-4 — S3-06 cost-cap path must work

           # AC-5 — breakdown-key validation
           unknown_keys = set(raw_score.breakdown) - plan.task_class.breakdown_keys
           if unknown_keys:
               score = _failure_score(
                   code="rubric.unknown_breakdown_key",
                   detail=min(unknown_keys),                # AC-5: deterministic, NOT next(iter())
                   wall_clock_ms=_elapsed_ms(start_ns),
                   cost_usd=raw_score.cost_usd,             # AC-5: preserve
               )
           else:
               # AC-6 — failure-mode resolution (pure helper)
               resolved = _resolve_failure_modes(
                   raw_score.failure_modes, plan.task_class.failure_mode_taxonomy,
               )
               score = raw_score.model_copy(update={"failure_modes": resolved})

           _put_in_cache(plan, case, score, cache_dir, log)
           await queue.put((case.case_id, score))


   def _elapsed_ms(start_ns: int) -> int:
       return (time.monotonic_ns() - start_ns) // 1_000_000


   def _put_in_cache(plan, case, score, cache_dir, log) -> None:
       """AC-15 + AC-16 — cache failure-path scores; OSError log-and-continue."""
       try:
           cache.put(plan.cache_keys[case.case_id], score, cache_dir)
       except OSError as exc:
           log.warning("runner.cache_put_failed", error=str(exc))
   ```

   (Restructure: move the `isinstance(harness_output, Mapping)` check INSIDE the `try` block between `wait_for` and the rubric call, so the `TypeError` is caught by the `except Exception` branch and emitted as `sut.exception` per AC-3. The outline above shows the conceptual structure; the final code keeps a single `try` around `wait_for(...) + isinstance check + rubric call` — but `CancelledError`/`KeyboardInterrupt`/`SystemExit` from the rubric call MUST still propagate via a nested `try`. Two structurally distinct `try` blocks is cleaner than one wide `try` with a multi-branch `except` chain.)

3. **Aggregator is UNCHANGED.** S3-02's `_aggregate` already computes `block_severity_failure_modes` from `per_case`'s FailureModes. The story does not touch it.

4. **Helper widening** (test-side):
   - `tests/helpers/bench.py`: widen `make_stub_plan(tmp_path, *, case_ids=..., breakdown_keys=None, failure_mode_taxonomy=None)` — additive kwargs that thread into `stub_task_class_fixture` → `TaskClass`. Existing call sites unaffected.
   - `tests/helpers/suts.py`: add `RaisingSUT(error: Exception)`, `SleepingSUT(seconds: float)`, `DeterministicSUT.passing()`, `MultiSUT(sut_for: Callable[[str], AsyncCallable])` — all as classes with `call_count`. Honor S3-02's `JitteredStubSUT` shape.
   - `tests/helpers/rubrics.py`: add `BannedBreakdownKeyRubric(banned_key: str)`, `EmittedFailureModeRubric(emitted_codes: list[tuple[str, Severity]])`, `MixedSeverityRubric(per_case: Mapping[str, list[tuple[str, Severity]]])` — all as classes implementing `RubricRunner` Protocol (`async def run(self, rubric_path, case, harness_output, *, wall_clock_cap_seconds) -> BenchScore`).
   - `tests/fence/test_runner_no_sigalrm.py` (new): AST-walk; assert `signal.SIGALRM` not referenced.

## TDD plan — red / green / refactor

### Red — write failing tests first

Helpers must land in red before tests reference them.

**Test files:**
- `tests/unit/test_runner_failure_paths.py` — the 6 paths + propagation + integration assertions (~15 tests).
- `tests/unit/test_resolve_failure_modes.py` — pure helper unit tests + Hypothesis property (~9 tests).
- `tests/fence/test_runner_no_sigalrm.py` — structural fence (1 test).

Representative tests below (full enumeration in §Files-to-touch comments — total 17 mutation-resistant tests + 1 Hypothesis property + 2 metamorphic relations):

```python
# tests/unit/test_runner_failure_paths.py

import asyncio
import time
from collections import Counter
from pathlib import Path

import pytest

from codegenie.eval.models import BenchScore, FailureMode
from codegenie.eval.runner import Runner
from tests.helpers.bench import make_stub_plan
from tests.helpers.suts import (
    RaisingSUT, SleepingSUT, DeterministicSUT, MultiSUT,
)
from tests.helpers.rubrics import (
    InProcessStubRubric, BannedBreakdownKeyRubric,
    EmittedFailureModeRubric, MixedSeverityRubric,
)


def _default_kwargs(tmp_path: Path, *, timeout: float = 30.0) -> dict:
    return dict(
        rubric_runner=InProcessStubRubric(),
        cache_dir=tmp_path / "cache",
        timeout_per_case_seconds=timeout,
    )


def _assert_report_shape(report) -> None:
    assert isinstance(report.per_case, tuple)              # AC-17
    assert report.isolation_class == "subprocess"          # AC-17


# ---------- AC-1 — sut.exception ------------------------------------------
@pytest.mark.asyncio
async def test_sut_exception_maps_with_measured_wall_clock_and_zero_cost(tmp_path):
    plan = make_stub_plan(tmp_path, case_ids=["a"])
    async def boomer(case):
        await asyncio.sleep(0.05)
        raise RuntimeError("nope, broken")
    report = await Runner().execute(plan, system_under_test=boomer, **_default_kwargs(tmp_path))
    _assert_report_shape(report)
    s = report.per_case[0][1]
    assert s.passed is False
    assert s.score == 0.0
    assert s.breakdown == {}
    assert s.cost_usd == 0.0                                # AC-1
    assert s.wall_clock_ms >= 50                            # AC-14 — measured, not 0
    assert len(s.failure_modes) == 1
    assert s.failure_modes[0].code == "sut.exception"
    assert s.failure_modes[0].severity == "block"
    assert "RuntimeError: nope, broken" in s.failure_modes[0].detail


# ---------- AC-1 — BaseException subclasses propagate ---------------------
@pytest.mark.asyncio
async def test_custom_baseexception_subclass_propagates_unmapped(tmp_path):
    class CustomBaseExc(BaseException): pass
    plan = make_stub_plan(tmp_path, case_ids=["a"])
    async def custom(case): raise CustomBaseExc("escape!")
    with pytest.raises(CustomBaseExc, match="escape!"):
        await Runner().execute(plan, system_under_test=custom, **_default_kwargs(tmp_path))


# ---------- AC-2 — sut.timeout enforces the cap, not the SUT's natural exit
@pytest.mark.asyncio
async def test_sut_timeout_aborts_at_cap_not_natural_completion(tmp_path):
    plan = make_stub_plan(tmp_path, case_ids=["a"])
    sut = SleepingSUT(seconds=5.0)
    t0 = time.monotonic()
    report = await Runner().execute(
        plan, system_under_test=sut, **_default_kwargs(tmp_path, timeout=0.1),
    )
    elapsed = time.monotonic() - t0
    assert elapsed < 1.0                                    # AC-2: cap enforced
    s = report.per_case[0][1]
    assert s.failure_modes[0].code == "sut.timeout"
    assert s.failure_modes[0].severity == "block"
    assert s.wall_clock_ms < 1000 and s.wall_clock_ms >= 100  # measured ms


# ---------- AC-3 — non-Mapping SUT output --------------------------------
@pytest.mark.asyncio
async def test_non_mapping_sut_output_maps_to_sut_exception(tmp_path):
    plan = make_stub_plan(tmp_path, case_ids=["a"])
    async def returns_none(case): return None
    rubric = InProcessStubRubric()
    report = await Runner().execute(
        plan, system_under_test=returns_none,
        rubric_runner=rubric, cache_dir=tmp_path / "cache",
        timeout_per_case_seconds=5.0,
    )
    s = report.per_case[0][1]
    assert s.failure_modes[0].code == "sut.exception"
    assert "TypeError" in s.failure_modes[0].detail
    assert "harness_output must be Mapping" in s.failure_modes[0].detail
    assert rubric.call_count == 0                           # AC-4 indirect: rubric never reached


# ---------- AC-4 — propagation with rubric.call_count == 0 ---------------
@pytest.mark.asyncio
@pytest.mark.parametrize("exc_cls", [KeyboardInterrupt, SystemExit, asyncio.CancelledError])
async def test_propagation_does_not_invoke_rubric(tmp_path, exc_cls):
    plan = make_stub_plan(tmp_path, case_ids=["a"])
    rubric = InProcessStubRubric()
    async def boom(case): raise exc_cls()
    with pytest.raises(exc_cls):
        await Runner().execute(
            plan, system_under_test=boom,
            rubric_runner=rubric, cache_dir=tmp_path / "cache",
            timeout_per_case_seconds=5.0,
        )
    assert rubric.call_count == 0


# ---------- AC-4 (rubric side) — CancelledError from rubric propagates ---
@pytest.mark.asyncio
async def test_cancellederror_from_rubric_propagates_unmapped(tmp_path):
    class CancellingRubric:
        async def run(self, rubric_path, case, harness_output, *, wall_clock_cap_seconds):
            raise asyncio.CancelledError()
    plan = make_stub_plan(tmp_path, case_ids=["a"])
    with pytest.raises(asyncio.CancelledError):
        await Runner().execute(
            plan, system_under_test=DeterministicSUT.passing(),
            rubric_runner=CancellingRubric(),
            cache_dir=tmp_path / "cache", timeout_per_case_seconds=5.0,
        )


# ---------- AC-4a — external cancel (S3-06 cost-cap path) ----------------
@pytest.mark.asyncio
async def test_external_cancel_propagates_no_synthesized_failure_mode(tmp_path):
    plan = make_stub_plan(tmp_path, case_ids=["a", "b", "c"])
    sut = SleepingSUT(seconds=10.0)
    task = asyncio.create_task(
        Runner().execute(plan, system_under_test=sut, **_default_kwargs(tmp_path, timeout=30.0)),
    )
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # No FailureMode survived; no leaked tasks
    assert all(t.done() for t in asyncio.all_tasks() - {asyncio.current_task()})


# ---------- AC-5 — multiple banned keys, deterministic detail ------------
@pytest.mark.asyncio
async def test_multiple_unknown_breakdown_keys_picks_lexicographically_smallest(tmp_path):
    plan = make_stub_plan(
        tmp_path, case_ids=["a"],
        breakdown_keys=frozenset({"correctness"}),
    )
    rubric = BannedBreakdownKeyRubric(  # emits {"zebra": 0.5, "apple": 0.5, "mango": 0.5}
        banned_keys={"zebra", "apple", "mango"},
    )
    report = await Runner().execute(
        plan, system_under_test=DeterministicSUT.passing(),
        rubric_runner=rubric, cache_dir=tmp_path / "cache",
        timeout_per_case_seconds=5.0,
    )
    s = report.per_case[0][1]
    assert s.failure_modes[0].code == "rubric.unknown_breakdown_key"
    assert s.failure_modes[0].detail == "apple"             # AC-5 — min(), not next(iter())
    assert s.passed is False
    assert s.score == 0.0
    assert s.breakdown == {}                                # AC-5 — discarded


# ---------- AC-9 / AC-10 / AC-11 — run continues + integration --------
@pytest.mark.asyncio
async def test_three_case_three_failure_modes_run_continues(tmp_path):
    plan = make_stub_plan(
        tmp_path, case_ids=["a", "b", "c"],
        breakdown_keys=frozenset({"correctness"}),
    )
    sut_for = {
        "a": RaisingSUT(error=ValueError("boom")),
        "b": SleepingSUT(seconds=5.0),
        "c": DeterministicSUT.passing(),
    }
    rubric = BannedBreakdownKeyRubric(banned_keys={"llm_confidence"})
    report = await Runner().execute(
        plan, system_under_test=MultiSUT(lambda cid: sut_for[cid]),
        rubric_runner=rubric, cache_dir=tmp_path / "cache",
        timeout_per_case_seconds=0.1,
    )
    _assert_report_shape(report)
    assert len(report.per_case) == 3
    assert report.complete is True
    code_by_cid = {cid: s.failure_modes[0].code for cid, s in report.per_case}
    assert code_by_cid == {
        "a": "sut.exception",
        "b": "sut.timeout",
        "c": "rubric.unknown_breakdown_key",
    }
    # AC-10 integration assertion — S3-02's aggregator computed this
    assert report.block_severity_failure_modes == (
        "rubric.unknown_breakdown_key", "sut.exception", "sut.timeout",
    )
    assert report.passed_count == 0


# ---------- AC-9b — passed=True + warn survives ---------------------------
@pytest.mark.asyncio
async def test_passed_true_with_warn_failure_mode_preserved(tmp_path):
    plan = make_stub_plan(
        tmp_path, case_ids=["a"],
        failure_mode_taxonomy={"recipe.unused_field": "warn"},
    )
    rubric = EmittedFailureModeRubric(
        emitted=[("recipe.unused_field", "warn")], passed=True, score=0.95,
    )
    report = await Runner().execute(
        plan, system_under_test=DeterministicSUT.passing(),
        rubric_runner=rubric, cache_dir=tmp_path / "cache",
        timeout_per_case_seconds=5.0,
    )
    s = report.per_case[0][1]
    assert s.passed is True
    assert s.failure_modes[0].code == "recipe.unused_field"
    assert s.failure_modes[0].severity == "warn"
    assert "recipe.unused_field" not in report.block_severity_failure_modes
    assert report.passed_count == 1


# ---------- AC-13 — detail truncation -------------------------------------
@pytest.mark.asyncio
async def test_sut_exception_detail_truncated_to_200_chars(tmp_path):
    plan = make_stub_plan(tmp_path, case_ids=["a"])
    async def big(case): raise RuntimeError("x" * 10000)
    report = await Runner().execute(plan, system_under_test=big, **_default_kwargs(tmp_path))
    s = report.per_case[0][1]
    assert len(s.failure_modes[0].detail) <= 200


# ---------- AC-15 — failure-path cache identity ---------------------------
@pytest.mark.asyncio
async def test_sut_exception_cached_second_run_returns_cached_score(tmp_path):
    plan = make_stub_plan(tmp_path, case_ids=["a"])
    call_count = {"n": 0}
    async def boomer(case):
        call_count["n"] += 1
        raise RuntimeError("flaky")
    # First run synthesizes + caches
    r1 = await Runner().execute(plan, system_under_test=boomer, **_default_kwargs(tmp_path))
    # Second run — same cache_dir, same plan → cache hit, SUT not invoked again
    r2 = await Runner().execute(plan, system_under_test=boomer, **_default_kwargs(tmp_path))
    assert call_count["n"] == 1
    assert r1.per_case[0][1].failure_modes[0].code == r2.per_case[0][1].failure_modes[0].code
```

```python
# tests/unit/test_resolve_failure_modes.py

import pytest
from hypothesis import given, strategies as st, settings

from codegenie.eval.models import FailureMode
from codegenie.eval.runner import _resolve_failure_modes


def test_empty_input_empty_output():
    assert _resolve_failure_modes((), {}) == ()


def test_known_code_severity_overridden_block_to_warn():
    fm = FailureMode(code="recipe.unused_field", severity="block", detail="x")
    out = _resolve_failure_modes((fm,), {"recipe.unused_field": "warn"})
    assert out[0].code == "recipe.unused_field"
    assert out[0].severity == "warn"
    assert out[0].detail == "x"


def test_known_code_severity_upgrade_warn_to_block():
    fm = FailureMode(code="validator.build_failed", severity="warn", detail=None)
    out = _resolve_failure_modes((fm,), {"validator.build_failed": "block"})
    assert out[0].severity == "block"


def test_known_code_severity_info():
    fm = FailureMode(code="recipe.optimized_path", severity="block", detail=None)
    out = _resolve_failure_modes((fm,), {"recipe.optimized_path": "info"})
    assert out[0].severity == "info"


def test_unknown_code_replaced_with_rubric_unknown_failure_mode():
    fm = FailureMode(code="some.typoed.code", severity="block", detail="oops")
    out = _resolve_failure_modes((fm,), {"known.code": "block"})
    assert out[0].code == "rubric.unknown_failure_mode"
    assert out[0].severity == "block"
    assert out[0].detail == "some.typoed.code"


def test_reserved_namespace_code_rejected_even_if_in_taxonomy():
    """The smuggling defense — a buggy rubric can't fabricate sut.exception."""
    fm = FailureMode(code="sut.exception", severity="warn", detail="fake")
    out = _resolve_failure_modes((fm,), {"sut.exception": "block"})
    assert out[0].code == "rubric.unknown_failure_mode"
    assert out[0].severity == "block"
    assert out[0].detail == "reserved_code:sut.exception"


def test_mixed_known_and_unknown_resolved_independently_preserving_order():
    """A wrong impl that replaces ALL when ANY is unknown fails this."""
    modes = (
        FailureMode(code="validator.build_failed", severity="warn", detail="m1"),
        FailureMode(code="typoed.code", severity="block", detail="m2"),
        FailureMode(code="recipe.unused_field", severity="warn", detail="m3"),
    )
    taxonomy = {"validator.build_failed": "block", "recipe.unused_field": "warn"}
    out = _resolve_failure_modes(modes, taxonomy)
    assert out[0] == FailureMode(code="validator.build_failed", severity="block", detail="m1")
    assert out[1] == FailureMode(code="rubric.unknown_failure_mode", severity="block", detail="typoed.code")
    assert out[2] == FailureMode(code="recipe.unused_field", severity="warn", detail="m3")


# ---------- Hypothesis resolver-purity property --------------------------
_RESERVED = {"sut.exception", "sut.timeout", "rubric.malformed_output",
             "rubric.timeout", "rubric.unknown_breakdown_key",
             "rubric.unknown_failure_mode"}
_severity = st.sampled_from(["block", "warn", "info"])
_non_reserved_code = st.text(
    alphabet=st.characters(whitelist_categories=("Ll",)), min_size=4, max_size=30,
).map(lambda s: f"family.{s}").filter(lambda c: c not in _RESERVED)


@given(
    taxonomy_pairs=st.lists(
        st.tuples(_non_reserved_code, _severity), min_size=2, max_size=8, unique_by=lambda p: p[0],
    ),
    incoming_codes=st.lists(_non_reserved_code, min_size=0, max_size=5),
)
@settings(max_examples=30, deadline=None)
def test_resolver_property_preserves_order_and_resolves_independently(taxonomy_pairs, incoming_codes):
    taxonomy = dict(taxonomy_pairs)
    incoming = tuple(
        FailureMode(code=c, severity="warn", detail=f"d:{c}") for c in incoming_codes
    )
    out = _resolve_failure_modes(incoming, taxonomy)
    assert len(out) == len(incoming)
    for i, fm_in in enumerate(incoming):
        fm_out = out[i]
        if fm_in.code in taxonomy:
            assert fm_out.code == fm_in.code
            assert fm_out.severity == taxonomy[fm_in.code]
            assert fm_out.detail == fm_in.detail
        else:
            assert fm_out.code == "rubric.unknown_failure_mode"
            assert fm_out.severity == "block"
            assert fm_out.detail == fm_in.code


# ---------- Taxonomy-shuffle metamorphic relation -----------------------
@given(
    taxonomy_pairs=st.lists(
        st.tuples(_non_reserved_code, _severity), min_size=3, max_size=8, unique_by=lambda p: p[0],
    ),
)
@settings(max_examples=15, deadline=None)
def test_resolver_invariant_under_taxonomy_dict_permutation(taxonomy_pairs):
    """Dict iteration order is insertion-ordered; resolver must not depend on it."""
    incoming = tuple(
        FailureMode(code=c, severity="warn", detail=None) for c, _ in taxonomy_pairs
    )
    out_a = _resolve_failure_modes(incoming, dict(taxonomy_pairs))
    out_b = _resolve_failure_modes(incoming, dict(reversed(taxonomy_pairs)))
    assert out_a == out_b
```

```python
# tests/fence/test_runner_no_sigalrm.py
import ast
from pathlib import Path


def test_runner_does_not_use_signal_sigalrm():
    """SIGALRM-in-asyncio is the load-bearing wrong-implementation for sut.timeout."""
    source = Path("src/codegenie/eval/runner.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "signal" for alias in node.names), \
                "runner.py must not import signal (use asyncio.wait_for for SUT timeout)"
        if isinstance(node, ast.ImportFrom):
            assert node.module != "signal", "runner.py must not import from signal"
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "signal" and node.attr == "SIGALRM":
                raise AssertionError("signal.SIGALRM forbidden in runner.py")
```

Run all 17 + 9 + 1 tests; confirm failures. Commit as the red marker.

### Green — make them pass

Land the smart constructor `_failure_score`, the pure `_resolve_failure_modes`, `_RESERVED_RUNNER_CODES`, the widened `_run_case` body, and the helper-class additions. The aggregator is unchanged.

### Refactor — clean up

- Verify `_failure_score` and `_resolve_failure_modes` are pure (no `await`, no I/O, no global state). The pure-impure split is the load-bearing testability win.
- Audit that `_run_case` has exactly two `try` blocks (one around `wait_for` + isinstance check, one around `rubric_runner.run`) — adding a third invites the "anaemic exception chain" anti-pattern.
- Add a module-level comment table listing the six runner-emitted codes and their architectural origins (ADR refs).
- Structured logs: `log.warning("case_failed", code=fm.code, severity=fm.severity, detail=fm.detail)` on every block-severity emission.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/runner.py` | Add `_RESERVED_RUNNER_CODES`, `_DETAIL_MAX_LEN`, `_failure_score`, `_resolve_failure_modes`, `_elapsed_ms`, `_put_in_cache` helpers; widen `_run_case` body per AC-1…AC-7 |
| `tests/unit/test_runner_failure_paths.py` | New: 17 mutation-resistant tests covering all six paths + propagation + integration |
| `tests/unit/test_resolve_failure_modes.py` | New: 9 pure-helper unit tests + Hypothesis resolver-purity property + taxonomy-shuffle metamorphic relation |
| `tests/fence/test_runner_no_sigalrm.py` | New: structural AST fence — `signal.SIGALRM` not referenced in `runner.py` |
| `tests/helpers/suts.py` | Add `RaisingSUT`, `SleepingSUT`, `DeterministicSUT`, `MultiSUT` (all classes with `call_count`) |
| `tests/helpers/rubrics.py` | Add `BannedBreakdownKeyRubric`, `EmittedFailureModeRubric`, `MixedSeverityRubric` (all classes implementing `RubricRunner` Protocol with `async def run(self, rubric_path, case, harness_output, *, wall_clock_cap_seconds)`) |
| `tests/helpers/bench.py` | Widen `make_stub_plan(tmp_path, *, case_ids=..., breakdown_keys=None, failure_mode_taxonomy=None)` — additive kwargs threaded through `stub_task_class_fixture` → `TaskClass`; existing call sites unaffected |
| `docs/phases/06.5-per-task-class-eval-harness/ADRs/0004-per-task-class-failure-modes-taxonomy.md` | Amendment (precondition): replace `sut.cancelled` with `sut.timeout` in §Consequences seed taxonomy; add explicit bullet that taxonomy severity overrides rubric-emitted severity on known codes |
| `docs/phases/06.5-per-task-class-eval-harness/ADRs/0008-breakdown-keys-strenum-with-substring-ban.md` | Amendment (precondition): add explicit bullet that `rubric.unknown_breakdown_key` discards `score`/`breakdown`/`passed`, preserves `cost_usd`/`wall_clock_ms` |

## Out of scope

- `rubric.timeout` and `rubric.malformed_output` *plumbing* — S3-03 owns these; this story extends the test surface for the integrated run but does not change the subprocess module.
- Adversarial subprocess fixtures (`tests/fixtures/bench/adversarial-task-class/`) — S3-07.
- Cost-cap path (`run_id = "partial:..."`) — S3-06.
- BCa bootstrap on `lower_bound_95` — S3-05.
- Promotion gate's consumption of `block_severity_failure_modes` — S4-04.
- **Aggregator changes.** S3-02's `_aggregate` already computes `block_severity_failure_modes` correctly. This story does NOT touch `_aggregate` — it only feeds it.
- **Registry promotion `@register_failure_score_factory(code, factory)`** — explicitly deferred (closes S3-03's F-DP-2 thread). The 6 mappings have 3 distinct constructor shapes (from-exception, from-breakdown-key, from-rubric-emitted-code); a registry would unify call sites that don't share a useful signature (Rule 2 — three similar lines is better than premature abstraction). Re-evaluate at Phase 7 if `baseimage.*` runner-emitted codes appear with a shape that *does* share `from-exception` constructor logic.
- **Phase-4 `CanaryMismatch` integration test** — generic `sut.exception` mapping covers it; a Phase-4-specific test (verifying the `from codegenie.cassettes.canary import CanaryMismatch` import path works through the runner) lives with the Phase 4 cassette story, not S3-04.
- **`FailureMode.code` tightening to `StrEnum`** — S1-02's HARDENED contract is `code: str`. Phase 7 may revisit (see Notes-for-implementer).

## Notes for the implementer

- **ADR amendments are preconditions, not story bodies.** Land the two ADR-0004 amendments (replace `sut.cancelled` with `sut.timeout` in §Consequences seed taxonomy + spell out the taxonomy-overrides-rubric-severity semantic) and the ADR-0008 amendment (spell out the score-discard semantic on `rubric.unknown_breakdown_key`) in the SAME PR as this story. Mention the amendments in the PR description.

- **The reserved-namespace defense (`_RESERVED_RUNNER_CODES`) is load-bearing.** A buggy or adversarial rubric can today fabricate `sut.exception` events that the resolver would accept (the vuln-remediation seed taxonomy includes `sut.exception` per ADR-0004 §Consequences). The reserved-namespace check runs BEFORE the taxonomy lookup; taxonomy registration of these codes is irrelevant to whether the rubric can emit them. This is the structural guard that backs "Facts, not judgments" at the trust boundary.

- **Pure-impure split (`_resolve_failure_modes`).** The taxonomy-severity-override logic is the single most mutation-vulnerable piece of code in this story. Extracting it as a pure module-level function lets `tests/unit/test_resolve_failure_modes.py` exercise it directly without going through `Runner.execute(...)` — shorter feedback loop, deeper mutation coverage. **Do not inline the resolver back into `_run_case` during refactor.**

- **Smart constructor `_failure_score` is the rule-of-three at the literal level (4 sites), NOT at the semantic level (6 paths).** The 4 paths (`sut.exception`, `sut.timeout`, `rubric.unknown_breakdown_key`, `rubric.unknown_failure_mode`) all build the same literal `BenchScore(passed=False, score=0.0, breakdown={}, failure_modes=(FailureMode(...),), cost_usd=<varies>, wall_clock_ms=<measured>)` — so collapsing into one constructor pays its rent. The semantic mappings (what triggers each, how detail is constructed) are different shapes — that's why a registry over the 6 paths does NOT pay its rent (see Out-of-scope).

- **`asyncio.wait_for`, not `signal.SIGALRM`.** Called out in `final-design.md §Components → runner.py` as a critic-flagged correctness issue (SIGALRM doesn't compose with asyncio). The structural fence test (`tests/fence/test_runner_no_sigalrm.py`) catches this at PR time even if the behavior test happens to pass.

- **`asyncio.CancelledError` passthrough is critical.** S3-06's cost-cap path uses `asyncio.Task.cancel()` to abort outstanding workers. Mapping `CancelledError` to a `FailureMode` (from either the SUT or the rubric subprocess) would silently turn cost-cap into "all cases failed" instead of "run aborted." The explicit `CancelledError` propagation tests at both layers are the structural guard.

- **Taxonomy severity overrides rubric severity on KNOWN codes.** Non-obvious. ADR-0004 §"Facts, not judgments" — the rubric is allowed to *report* what happened; the taxonomy decides what *severity* that event is. A rubric that emits `severity="warn"` for a code the taxonomy classifies as `"block"` must produce a `"block"`-severity `FailureMode`. The test for this asymmetry (warn→block upgrade AND block→warn downgrade AND info round-trip) is load-bearing.

- **Multiple banned breakdown keys: `min(unknown_keys)`, NOT `next(iter(unknown_keys))`.** Set iteration order is non-deterministic; the audit chain demands byte-identical reports across runs (S3-02 AC-9a). `min()` is stable. The Hypothesis property + the 3-key red test pin this.

- **`task_class.breakdown_keys` is `frozenset[str]`** (per arch §Data model). The runtime check is `set(score.breakdown) - task_class.breakdown_keys` — set difference is unordered (hence `min()` requirement above). Defense in depth: ADR-0008's fence-CI substring ban catches LLM-confidence smuggling at PR time; this runtime check is the second layer.

- **Runner-emitted codes (the six) bypass taxonomy resolution.** They are constructed by the runner with hardcoded `severity="block"`. Even if a task class's `failure_modes.yaml` omits one of them, the runner emits `block` regardless. This is by design — runner-emitted codes are "system events," not "rubric judgments." A future fence test could assert every task class's `failure_modes.yaml` registers all six (so the gate's `description` lookup works); out of scope for S3-04.

- **`cost_usd` is preserved on `rubric.unknown_breakdown_key`.** The rubric did the work — Phase 13's cost dashboard must reflect it. `score`/`breakdown`/`passed` are discarded (the rubric output is repudiated for quality), but the cost is a fact of what happened.

- **Detail truncation (200 chars) defends against detail-blowup in audit records.** Exception messages from common libraries (e.g., `psycopg`, `aiohttp`) contain large object reprs, full SQL queries, full HTTP response bodies. Without truncation, a single failure can balloon the audit chain. The smart constructor `_failure_score` enforces; `_resolve_failure_modes` enforces for reserved-namespace replacement details.

- **Determinism caveat for exception messages.** Two independent runs of a SUT that raises `RuntimeError(f'oops at {id(self)}')` would produce non-deterministic `detail` strings (memory addresses), breaking S3-02 AC-9a's byte-identity property. The story does NOT install detail normalization — exception messages with non-deterministic content are a SUT-author responsibility. If a future need surfaces (e.g., a Phase-4 cassette author writes a non-deterministic SUT), revisit via an ADR amendment for a detail normalization pass.

- **`type(e).__name__` (not `__qualname__`).** Style-consistent with the existing convention in the story; for nested-class exceptions across libraries, two `SomeError` classes from different modules would be indistinguishable in the audit chain. If that becomes a Phase 13 audit-debugging pain point, escalate to `type(e).__qualname__` + `type(e).__module__` via an additive change to `_failure_score`.

- **`FailureMode.code: str` is anaemic — Phase 7 may revisit.** S1-02's HARDENED contract is `code: str`. A future tightening to `NewType("RuntimeFailureCode", str)` with a smart constructor enforcing the `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` regex (matches Phase 1 ADR-0007's warning-ID convention) would close the "any string is a code" hole, but adds friction for marginal value at the rule-of-three threshold. Defer.

- **The test fixture rubrics are in-process** (S3-04 reuses S3-02's in-process injection seam — `InProcessStubRubric` is the prior art). Subprocess versions of the adversarial rubrics live in S3-07's bench fixture portfolio. The new helpers (`BannedBreakdownKeyRubric`, `EmittedFailureModeRubric`, `MixedSeverityRubric`) MUST be classes (not bare callables) implementing the `RubricRunner` Protocol — `isinstance(x, RubricRunner)` must succeed (S3-02 AC-3).
