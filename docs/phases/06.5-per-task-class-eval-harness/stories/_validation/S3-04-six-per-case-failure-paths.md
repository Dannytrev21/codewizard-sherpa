# Validation report — S3-04 — Six typed per-case failure paths

**Validator run:** 2026-05-27 (scheduled task `story-validation-corrector`)
**Story file:** `../S3-04-six-per-case-failure-paths.md`
**Verdict:** **HARDENED** — 36 findings (10 block, 21 harden, 5 nit) applied; story rewritten in place. Five concrete contract drifts against HARDENED S3-02 fixed; reserved-namespace smuggling defense added; pure-resolver extraction promoted from refactor note to AC; multi-banned-key non-determinism closed; ADR-0004 amendment surfaced as a precondition.
**Skip Stage 3:** no findings tagged `NEEDS RESEARCH` (everything resolvable against canonical phase docs + HARDENED siblings).

## Context Brief (Stage 1)

S3-04 is the typed-failure-mapping layer of the runner. It widens the worker `_run_case` (extracted GREEN-ready by HARDENED S3-02 per F-DP-6) to translate four runner-visible failure conditions into the typed `FailureMode` sum-type ADR-0004 commits to, and to translate two rubric-output validation failures (ADR-0008 banned-breakdown-key + ADR-0004 unknown-failure-code) into typed failures **without aborting the run**. The aggregator (`_aggregate`) is owned by HARDENED S3-02 and already computes `block_severity_failure_modes` — this story must NOT re-prescribe that computation, only feed it.

Load-bearing constraints:

- **HARDENED S3-02 contracts** (the upstream story this builds on):
  - `Runner.execute(plan, *, system_under_test, rubric_runner, cache_dir, timeout_per_case_seconds, concurrency=None, on_score=None) -> BenchRunReport` — `timeout_per_case_seconds` and `cache_dir` are **`execute()` kwargs, NOT `RunPlan` fields** (S3-01 + S3-02 HARDENED).
  - Queue type: `asyncio.Queue[tuple[str, BenchScore] | _Sentinel]` — failure-path scores are enqueued as `(case_id, score)`, not bare `BenchScore`.
  - `_run_case(case, plan, sem, queue, *, system_under_test, rubric_runner, cache_dir, timeout_per_case_seconds) -> None` is already extracted; this story extends its body, does NOT re-extract.
  - `_aggregate` already computes `block_severity_failure_modes = tuple(sorted({fm.code for _cid, s in per_case for fm in s.failure_modes if fm.severity == "block"}))`.
  - Test helper `make_stub_plan(tmp_path, *, case_ids=...)` — `tmp_path` is positional.
  - Rubric helpers are **classes implementing the `RubricRunner` Protocol**, NOT bare async callables (S3-02 AC-3).
- **HARDENED S3-03 contracts**:
  - `SubprocessRubricRunner.run(self, rubric_path, case, harness_output, *, wall_clock_cap_seconds) -> BenchScore` — returns `BenchScore` (with typed FailureMode) on `rubric.timeout` / `rubric.malformed_output`; **never raises** for those two paths.
  - `wall_clock_ms = (time.monotonic_ns() - start_ns) // 1_000_000` is the measurement convention (S3-03 AC-16).
- **ADR-0001** §Consequences row 3 enumerates the four rubric-side typed codes: `rubric.malformed_output`, `rubric.timeout` (S3-03 owns), `rubric.unknown_breakdown_key`, `rubric.unknown_failure_mode` (S3-04 owns). Plus runner-emitted `sut.exception` and the SUT-timeout case.
- **ADR-0004** §Consequences seed taxonomy lists `sut.cancelled` (block) but **NOT `sut.timeout`** — this is a real ADR-vs-story conflict (see F-CON-1 below). The story chooses `sut.timeout` (correct: `asyncio.CancelledError` is reserved for S3-06's cost-cap and must NOT be conflated with `asyncio.TimeoutError`). An ADR-0004 amendment is a precondition for executor.
- **ADR-0004** silently endorses "rubric severity is suggestion, taxonomy is source of truth" via "Facts, not judgments" but does NOT spell it out in §Decision/§Consequences. F-CON-7 surfaces this as an ADR-0004 amendment opportunity (the story's AC enforces the semantic regardless).
- **ADR-0008** §Consequences pin `rubric.unknown_breakdown_key, severity="block", detail=<key>` but is silent on whether the rubric's original score is discarded. The story commits to discard (defensible: one bad key → can't trust the breakdown → can't trust the score) — F-CON-9 recommends ADR-0008 amendment.
- **CLAUDE.md**: Rule 7 (surface conflicts, don't average); Rule 9 (tests verify intent); Rule 12 (fail loud); "Facts, not judgments"; "Extension by addition — no silent edits".

## Stage 2 — Critic findings

Four critics ran in parallel.

### Coverage (C-01 … C-28) — 28 findings

Blocks: C-01 `plan.timeout_per_case_seconds` drift; C-02 `case.rubric_wall_clock_seconds` drift; C-03 `make_stub_plan(case_ids=...)` missing `tmp_path`; C-04 `make_stub_plan` lacks `breakdown_keys`/`failure_mode_taxonomy` widening; C-05 `_run_case` re-extraction conflict; C-06 queue-type drift (worker enqueues bare `BenchScore` instead of `(case_id, score)`); C-07 AC-7 duplicates S3-02 aggregator; C-08 `BaseException` subclasses other than the three; C-09 SUT returns `None`/non-Mapping; C-10 multi-banned-key non-determinism (`next(iter(set))`); C-11 reserved-namespace smuggling (rubric emits `code="sut.exception"`).

Hardens: C-12 runner-emitted codes vs taxonomy resolution; C-13 `passed=False, failure_modes=()` policy; C-14 `passed=True` + warn/info path; C-15 exception-detail determinism (memory addresses); C-16 universal `detail` 200-char truncation; C-17 `wall_clock_ms` measurement on failure paths; C-18 cache-puts on failure scores; C-19 `cache.put OSError` policy reuse; C-20 `signal.SIGALRM` structural negative test; C-21 promotion-gate consumer integration assertion; C-22 Goal-vs-AC traceability rewrite; C-23 `CancelledError` from rubric subprocess; C-24 Phase-4 `CanaryMismatch` integration test (deferred — see Out-of-scope); C-25 `cost_usd` preservation on discarded scores; C-28 rubric severity discarded, not merged.

Nits: C-26 `type.__qualname__` vs `__name__` (kept `__name__` for now; flagged as Phase-7 follow-up); C-27 `_default_kwargs` helper hoist.

### Test-Quality (F-TQ-1 … F-TQ-18) — 18 findings

Blocks: F-TQ-1 `wall_clock_ms`/`cost_usd` unasserted on `sut.exception`; F-TQ-2 elapsed-time enforcement on `sut.timeout`; F-TQ-3 `rubric.call_count==0` on propagation tests; F-TQ-4 mixed known+unknown codes test missing; F-TQ-5 warn→block upgrade symmetry; F-TQ-6 `codes = set(...)` flattens — per-case-id pairing untested; F-TQ-7 dedup + sort untested in `block_severity_failure_modes`; F-TQ-9 `make_stub_plan` signature drift (= C-03/C-04).

Hardens: F-TQ-8 multi-banned-key determinism; F-TQ-10 `multi_sut` shape undefined; F-TQ-11 rubric helpers must be Protocol classes; F-TQ-12 misleading helper name; F-TQ-13 universal report-shape assertions (S3-02 AC-15 mandate); F-TQ-14 cancel-from-outside (S3-06 path) test; F-TQ-15 original-score-discarded assertion; F-TQ-16 detail 200-char truncation test.

Nits: F-TQ-17 inline comment for muddled multi-rubric test; F-TQ-18 `started_at <= ended_at` per-case.

Hypothesis property recommendations (all merged into story):
1. **Resolver purity property**: arbitrary taxonomy + arbitrary `FailureMode` list — preserved 1:1 with severity re-keyed when in taxonomy; replaced with `rubric.unknown_failure_mode` when not; order preserved.
2. **Metamorphic "extra failure mode doesn't change passing distribution"**: substituting one case's SUT with a raising one preserves the other cases' BenchScores bytewise.
3. **Taxonomy-shuffle metamorphic**: permuting taxonomy dict insertion order produces byte-identical reports.

### Consistency (F-CON-1 … F-CON-11) — 11 findings

Blocks: F-CON-1 `sut.timeout` vs ADR-0004's `sut.cancelled` (story wins on code design — `asyncio.CancelledError` is reserved for S3-06; ADR-0004 amendment in same PR); F-CON-2 `plan.timeout_per_case_seconds` drift; F-CON-3 `make_stub_plan` drift; F-CON-4 aggregator duplication; F-CON-11 rubric helpers must be Protocol classes.

Hardens: F-CON-5 wall-clock convention pinned to `time.monotonic_ns()`; F-CON-7 taxonomy-overrides-rubric-severity not in ADR-0004 (recommend amendment); F-CON-8 `SystemExit` is additive widening of S3-02 AC-12 (annotate); F-CON-9 score-discarded-on-unknown-breakdown-key not in ADR-0008 (recommend amendment).

Nits: F-CON-6 (no change); F-CON-10 (S3-02 AC-15 repetition discipline).

### Design-Patterns (F-DP-1 … F-DP-6) — 6 findings

Hardens: F-DP-1 explicitly defer S3-03's F-DP-2 registry-promotion thread (the 6 mappings have 3 distinct constructor shapes — Rule 2 says hold off; close the thread by saying so); F-DP-2 promote `_resolve_failure_modes` to a pure module-level function with its own AC and unit tests; F-DP-3 reserved-namespace smuggling defense (= C-11).

Nits: F-DP-4 `FailureMode.code: str` anaemia (Phase-7 follow-up); F-DP-5 smart-constructor `_failure_score(...)` (collapses 4 helpers' literal construction into 1 — this is the rule-of-three at literal level); F-DP-6 try/except branch is additive-by-file Open/Closed (head-off note).

## Stage 3 — Researcher

Skipped — every finding resolves against canonical phase docs + HARDENED S3-02/S3-03 contracts. The `NEEDS RESEARCH` tags in the Coverage report (cache policy per-code, `__qualname__` convention, `CanaryMismatch` import path) all have conservative defaults that don't require external lookup: failure-path scores ARE cached (S3-02's _run_case.cache.put policy applies uniformly); `type(e).__name__` is consistent with the existing story style; CanaryMismatch is deferred to Phase-4 integration via Out-of-scope.

## Stage 4 — Synthesizer

**Conflict resolution (Consistency > Coverage > Test-Quality > Design-Patterns):**

| Conflict | Resolution | Wins because |
|---|---|---|
| Story's `plan.timeout_per_case_seconds` vs S3-02's `execute()` kwarg | Use kwarg | HARDENED S3-02 contract is source of truth; Rule 7 (surface conflicts) |
| Story's `make_stub_plan(case_ids=...)` vs HARDENED `make_stub_plan(tmp_path, *, case_ids=...)` | Match HARDENED helper; widen additively for `breakdown_keys`/`failure_mode_taxonomy` | HARDENED upstream wins |
| Story prescribes aggregator's `block_severity_failure_modes` computation; S3-02 already owns it | Delete duplication; story becomes integration assertion | F-CON-4: source-of-truth wins (Consistency); double-implementation risks drift |
| ADR-0004 lists `sut.cancelled` (block); story uses `sut.timeout` | Story wins on code design — `asyncio.CancelledError` is S3-06-reserved and must not be conflated with `asyncio.TimeoutError`; ADR-0004 amendment is a same-PR precondition | Surface conflict (Rule 7), don't average; the SUT-timeout-vs-cancel distinction is structural |
| Coverage wants registry promotion (rule-of-three at 6 mappings); Design-Patterns says defer | Defer with explicit reason in Out-of-scope | Rule 2 + Rule 7: 6 mappings have 3 distinct constructor shapes; abstraction would unify call sites that don't share a useful signature; close the F-DP-2 thread by saying so |

**Edits applied to the story** (full delta-list in the story's new `## Validation notes` block at the top):

1. **Header** — `Status: Ready` → `Status: Ready (HARDENED 2026-05-27)`; `Depends on` widened to S3-02 HARDENED; `ADRs honored` clarified.
2. **`## Validation notes` block** appended after the title.
3. **Goal** — rewritten to (a) bind to the existing S3-02 aggregator (no re-prescription), (b) clarify the runner-emitted vs rubric-emitted code split, (c) name the reserved-namespace defense, (d) cite the ADR-0004 amendment precondition.
4. **Acceptance criteria** — renumbered AC-1…AC-18. 9 new ACs (`BaseException` discipline; non-Mapping SUT output; deterministic multi-banned-key detail; reserved-namespace smuggling defense; runner-emitted codes bypass taxonomy; `passed=False` + empty `failure_modes` policy; `passed=True` + warn/info policy; universal 200-char detail truncation; `wall_clock_ms` measurement convention; structural no-SIGALRM fence; pure `_resolve_failure_modes` helper; rubric-emitted severity discarded not merged).
5. **Implementation outline** — rewritten to extend (not re-extract) S3-02's `_run_case`; smart-constructor `_failure_score(code, *, detail=None, severity="block", wall_clock_ms, cost_usd=0.0)`; pure `_resolve_failure_modes(modes, taxonomy)` module-level helper; reserved-namespace constant `_RESERVED_RUNNER_CODES: Final[frozenset[str]]`; `time.monotonic_ns()` measurement; `min(unknown)` for deterministic detail. Removed §4 aggregator re-prescription.
6. **TDD plan** — rewritten with 17 mutation-resistant tests, 1 Hypothesis resolver-purity property, 2 metamorphic tests (extra-failure-mode invariance, taxonomy-shuffle invariance), pure-resolver unit tests in their own file.
7. **Files to touch** — added `tests/unit/test_resolve_failure_modes.py` (pure-resolver unit + Hypothesis); widened `tests/helpers/bench.py` (extend `make_stub_plan` additively); widened `tests/helpers/suts.py` (Protocol-class shapes); widened `tests/helpers/rubrics.py` (Protocol-class shapes); added `tests/fence/test_runner_no_sigalrm.py`.
8. **Out of scope** — explicit registry-promotion deferral (closes S3-03's F-DP-2 thread); CanaryMismatch Phase-4 integration test (S5-xx story); ADR-0004 + ADR-0008 amendments are explicit preconditions, not story-bodies.
9. **Notes for the implementer** — substantially rewritten: ADR amendment list; reserved-namespace defense rationale; pure-impure split; smart-constructor reason; deferred registry; detail-truncation defense; exception-detail determinism caveat; cost_usd preservation rationale.

## Verdict

**HARDENED.** The story is now compatible with HARDENED S3-02 + S3-03, conformant with the spirit of ADR-0001 + ADR-0004 + ADR-0008 (with two amendment preconditions surfaced explicitly), and would catch wrong implementations via 17 mutation-resistant tests + 1 Hypothesis property + 2 metamorphic relations. The pure-resolver extraction (F-DP-2) makes the load-bearing taxonomy-override-rubric-severity logic mutation-vulnerable at a unit-test boundary. The reserved-namespace defense (C-11 / F-DP-3) closes a real smuggling vector that arguably justifies the whole "Facts, not judgments" stance.

Ready for `phase-story-executor`.
