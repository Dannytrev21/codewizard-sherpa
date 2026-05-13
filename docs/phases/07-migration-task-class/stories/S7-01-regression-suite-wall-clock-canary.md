# Story S7-01 — Regression-suite wall-clock canary + baseline

**Step:** Step 7 — Performance canaries + fence-CI extension
**Status:** Ready
**Effort:** M
**Depends on:** S6-09
**ADRs honored:** ADR-P7-014 (regression-suite wall-clock canary, never retired)

## Context

This story lands the *suite-level* performance canary that pairs with the contract-surface snapshot (ADR-P7-009). The contract canary catches API drift; this one catches the *other* failure mode of extension-by-addition — cumulative wall-clock regression as Phase 8/9/13/14/15 each add tests. Without this, a 30 % slowdown sneaks in three phases at a time and the suite eventually becomes unrunnable in CI. Goal G12 makes the canary permanent: p50 ≤ 4 min, p95 ≤ 7 min, fail at >10 % regression on either percentile against the checked-in baseline. This is the first story of Step 7 — every later perf canary in the step (S7-02..S7-06) builds on the baseline-file + `--update-perf-baseline` flag pattern landed here.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 11 — Regression-suite wall-clock canary` — the reference public interface (`test_regression_suite_wall_clock` shape, baseline-relative thresholds, `--update-perf-baseline` flag, slowest-10-tests reporting on failure).
  - `../phase-arch-design.md §Goals G12` — permanence + the 10 % threshold + 4 min / 7 min absolute caps.
  - `../phase-arch-design.md §Testing strategy ›Performance regression tests` — narrow-scope siblings (`test_buildkit_cache_hit_rate.py`, `test_workflow_throughput.py`, `test_dockerfile_engine_p95.py`, `test_strace_budget_distribution.py`) — make sure none of them are accidentally folded into this canary.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0014-regression-suite-wall-clock-canary.md` — ADR-P7-014 — the decision, tradeoffs, and consequences; ship the test, ship `tests/perf/baseline.json`, runner-class metadata on the baseline file, deliberate-bump-only via flag.
  - `../ADRs/0009-contract-surface-snapshot-canary.md` — ADR-P7-009 — the *sister* canary; this story copies the `--update-...` flag pattern and the "deliberate-not-casual" regen discipline from there.
- **Source design:**
  - `../final-design.md §Goals#10` — wall-clock target as a Goal.
  - `../final-design.md §Component 9` — perf canary, never retired.
  - `../critique.md §best-practices.5` — the gap this story closes (the time-budget half of extension-by-addition).
- **Existing code (none yet):**
  - The test must be importable; no `src/` change is required. Reuse `pytest-xdist` (Phase 0 dev-dep).

## Goal

`pytest tests/perf/test_regression_suite_wall_clock.py` runs the full vuln + distroless regression suite under `pytest -n auto`, compares p50 / p95 wall-clock against the checked-in `tests/perf/baseline.json`, and fails when either percentile regresses by >10 % or breaches the absolute 4 min / 7 min caps.

## Acceptance criteria

- [ ] `tests/perf/test_regression_suite_wall_clock.py` exists with one test that runs the full regression suite under `pytest -n auto` and times it (per-test wall-clock collected via `pytest --durations=0 --json-report` or equivalent JSON sink).
- [ ] `tests/perf/baseline.json` exists at repo root path `tests/perf/baseline.json` with keys `p50_s`, `p95_s`, `recorded_at`, `runner_class` (e.g. `"linux-dind-reference-x86_64"`), `pytest_xdist_workers`, `commit_sha`. The values are populated from a real measured run on the reference Linux DinD runner — not hand-typed estimates.
- [ ] Failure cases verified in test: (a) p50 > `baseline.p50_s * 1.10` → fail; (b) p95 > `baseline.p95_s * 1.10` → fail; (c) p50 > 240 s → fail; (d) p95 > 420 s → fail. Each branch is exercised by an injected-baseline fixture test.
- [ ] On failure, the assertion message includes the slowest 10 tests (test nodeid + per-test wall-clock seconds) so the PR author has actionable feedback.
- [ ] A custom pytest flag `--update-perf-baseline` is registered (in `tests/perf/conftest.py`) that, when present, regenerates `tests/perf/baseline.json` from the just-measured run instead of comparing — and refuses to write if the diff would change `runner_class` without an explicit `--allow-runner-class-change` flag (silent runner-class change is the single worst bump mode).
- [ ] The TDD plan's red tests exist, were committed, and are green.
- [ ] `pytest tests/perf/test_regression_suite_wall_clock.py` is in CI's merge-gate lane (`.github/workflows/ci.yml` or equivalent) — referenced in `phase-arch-design.md §Testing strategy ›CI gates #6`.
- [ ] `ruff check`, `ruff format --check`, and `mypy --strict` clean on `tests/perf/test_regression_suite_wall_clock.py` and `tests/perf/conftest.py`.

## Implementation outline

1. Pick the per-test wall-clock collection mechanism. Use `pytest-json-report` (already a Phase 0 dev-dep if available; otherwise add it under `[project.optional-dependencies].dev`) so the in-test runner can parse `tests/.report.json` for per-test durations without re-implementing pytest's plugin protocol. Document the dep in `pyproject.toml`.
2. Write `tests/perf/conftest.py` registering `--update-perf-baseline` and `--allow-runner-class-change` flags, plus the helper `runner_class()` (reads `CODEGENIE_RUNNER_CLASS` env var; defaults to `"unknown"` and the test then refuses to update without the override).
3. Write `tests/perf/test_regression_suite_wall_clock.py` with one test that: subprocess-runs `pytest -n auto --json-report --json-report-file=tests/.report.json tests/ --ignore=tests/perf` (avoid recursion), parses the JSON for per-test durations, derives p50/p95 over the *full set*, compares against `baseline.json`, and asserts.
4. Make the assertion message build a "slowest 10 tests" table from the same JSON — sort by duration desc, take 10, render as `nodeid  duration_s`.
5. Generate `tests/perf/baseline.json` on the reference runner via `pytest tests/perf/test_regression_suite_wall_clock.py --update-perf-baseline` and commit the resulting file.
6. Wire the test into the merge-gate CI lane; add a `pytest --collect-only` smoke test in CI to ensure the perf test is discoverable from a clean checkout.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file paths:
- `tests/perf/test_regression_suite_wall_clock.py` — the canary itself (red because the file doesn't exist).
- `tests/perf/test_baseline_compare_logic.py` — unit tests for the comparison helper (red because the helper doesn't exist).

What the unit-test file asserts (anchor for the logic, fast feedback):

```python
# tests/perf/test_baseline_compare_logic.py
def test_p50_regression_over_10pct_fails():
    # arrange: synthetic baseline + measurement
    baseline = {"p50_s": 100.0, "p95_s": 200.0, "runner_class": "linux-dind-reference-x86_64"}
    measurement = {"p50_s": 111.0, "p95_s": 200.0}
    # act
    verdict = compare_to_baseline(measurement, baseline, absolute_caps=(240.0, 420.0))
    # assert
    assert verdict.passed is False
    assert "p50 regressed by >10%" in verdict.reason
    assert "111.0" in verdict.reason and "100.0" in verdict.reason

def test_absolute_cap_p95_over_420s_fails_even_if_below_baseline_pct():
    baseline = {"p50_s": 300.0, "p95_s": 500.0, "runner_class": "linux-dind-reference-x86_64"}  # broken baseline
    measurement = {"p50_s": 300.0, "p95_s": 421.0}
    verdict = compare_to_baseline(measurement, baseline, absolute_caps=(240.0, 420.0))
    assert verdict.passed is False
    assert "absolute cap" in verdict.reason

def test_slowest_10_rendered_on_failure():
    durations = [("t_a", 50.0), ("t_b", 5.0), ("t_c", 30.0)] + [(f"t_{i}", float(i)) for i in range(20)]
    table = render_slowest_10(durations)
    assert table.splitlines()[0].startswith("t_a")  # sorted desc
    assert len(table.splitlines()) == 10
```

And one canary smoke test that proves the file is wired:

```python
# tests/perf/test_regression_suite_wall_clock.py
def test_canary_module_imports_and_exposes_test():
    # arrange/act: import the module
    from tests.perf import test_regression_suite_wall_clock as m
    # assert: the canary test is present
    assert callable(getattr(m, "test_regression_suite_wall_clock"))
```

The unit tests must fail because `compare_to_baseline` and `render_slowest_10` don't exist yet. Run, confirm `ImportError` / `AttributeError`, then commit the failing tests as a marker.

### Green — make it pass

The smallest implementation:
- Add `tests/perf/_baseline.py` with `compare_to_baseline()` returning a `Verdict(passed: bool, reason: str)` `NamedTuple` and `render_slowest_10(durations)` returning a string. Pure functions, no I/O.
- Add `tests/perf/test_regression_suite_wall_clock.py::test_regression_suite_wall_clock` that subprocess-invokes pytest with `--json-report`, parses durations, calls `compare_to_baseline`, asserts, and includes `render_slowest_10(durations)` in the assertion message.
- Add `tests/perf/conftest.py` with the `--update-perf-baseline` and `--allow-runner-class-change` options.

Do not implement runner-class detection beyond reading `CODEGENIE_RUNNER_CLASS`. Do not implement CI-side baseline-regeneration automation in this story — bump-via-flag is enough.

### Refactor — clean up

After green:
- Type hints on every public function (`Verdict`, `compare_to_baseline`, `render_slowest_10`, the option-registration hook).
- Docstrings on `compare_to_baseline` explicitly stating the four failure branches.
- Edge cases from `phase-arch-design.md §Edge cases` row 16 (cold-pull on fresh runner) — note in the baseline.json metadata that the first warm-up run is excluded from the recorded baseline; the test's subprocess invocation does *not* run a warm-up phase (the suite itself is the workload).
- Per `phase-arch-design.md §Harness engineering`, the test must not introduce `random` or `time.time()` ordering into the suite-under-test — use `time.monotonic()` only inside the canary's own measurement; never inside test code.
- Compliance with ADR-P7-014 "Consequences": confirm `tests/perf/baseline.json` is committed via the same PR as the canary code; CI fails on missing baseline.

## Files to touch

| Path | Why |
|---|---|
| `tests/perf/test_regression_suite_wall_clock.py` | New file — the canary test (G12). |
| `tests/perf/_baseline.py` | New file — pure-function comparison + rendering helpers (extracted for unit-testability). |
| `tests/perf/test_baseline_compare_logic.py` | New file — unit tests for the helpers. |
| `tests/perf/conftest.py` | New file — `--update-perf-baseline` + `--allow-runner-class-change` option registration. |
| `tests/perf/baseline.json` | New file — checked-in baseline; populated from one measured run on the reference Linux DinD runner. |
| `pyproject.toml` | Add `pytest-json-report` under `[project.optional-dependencies].dev` if not already present. |
| `.github/workflows/ci.yml` (or equivalent) | Add the canary to the merge-gate lane (per `phase-arch-design.md §Testing strategy ›CI gates #6`). |

## Out of scope

- **Buildkit cache hit rate canary** — handled by story S7-02.
- **Workflow throughput canary (cold + warm + mixed)** — handled by story S7-03.
- **Dockerfile-engine p95 and strace budget distribution** — handled by story S7-04.
- **Mixed-portfolio warm E2E** — handled by story S7-05.
- **Per-worker memory + fence-CI synthetic PR** — handled by story S7-06.
- **Per-test perf budgets.** Rejected by ADR-P7-014 ("Burdensome to author; brittle on legitimate test additions"). Do not introduce them here even as an opt-in.
- **Automated baseline-regen on green CI.** Explicitly out per ADR-P7-014 "Consequences" — bumps must be deliberate human gestures, reviewable in PR diff.

## Notes for the implementer

- **Runner-class metadata is load-bearing.** Local-laptop measurements are not comparable to CI; the `runner_class` field in `baseline.json` is the contract. If the env var `CODEGENIE_RUNNER_CLASS` is unset, the test refuses to *update* the baseline (it still compares — local devs can run the canary, they just can't bump it). This is the single most common silent-regression mode for perf canaries; do not paper over it.
- **Don't recurse.** The canary's subprocess invocation runs `pytest -n auto tests/ --ignore=tests/perf` — if you forget the ignore, the canary calls itself and the suite either hangs or measures the wrong thing.
- **`pytest-json-report` is currently the lowest-friction collector; if Phase 0 prefers a different mechanism (e.g. a tiny in-tree pytest plugin), match Phase 0's convention rather than introducing a new tool — per Global Rule 11 (Match the codebase's conventions). Read Phase 0's `pyproject.toml` dev-deps before adding `pytest-json-report`.
- **The 10 % threshold is intentionally wide enough** to absorb legitimate test additions in Phase 8/9 — do not narrow it locally. If a future phase needs a tighter budget, that's an amendment to ADR-P7-014.
- **CI runner image must be stable** across the lifetime of the baseline. If Phase 8 changes the runner image (e.g. bumps the Ubuntu base), the baseline must be regenerated in the same PR with `--allow-runner-class-change` — flag this explicitly in `operator-notes.md` if/when it ships per S8-04.
- **`pytest --update-perf-baseline` writes the JSON unconditionally** when the flag is present; do not gate it on "tests passed" (you want to be able to regenerate a baseline even if the comparison would otherwise fail, that's the whole point of the flag).
- **Per Global Rule 12 (Fail loud):** when the JSON report path is missing or empty, raise an explicit `PerfBaselineMissingDurations` error — do not silently fall back to per-test wall-clock estimated from `pytest --durations=10` output or any other secondary source.
