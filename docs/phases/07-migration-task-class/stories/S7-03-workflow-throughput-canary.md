# Story S7-03 — Workflow throughput canary cold + warm + mixed

**Step:** Step 7 — Performance canaries + fence-CI extension
**Status:** Ready
**Effort:** M
**Depends on:** S7-02
**ADRs honored:** ADR-P7-014 (baseline-relative + `--update-perf-baseline` pattern, runner-class metadata)

## Context

Goals G6 and G7 commit Phase 7 to three throughput numbers: ≥ 6/hr cold distroless, ≥ 24/hr warm distroless, and ≥ 10/hr warm mixed-portfolio (vuln + distroless interleaved). These numbers were chosen "honest under Linux DinD" per `final-design.md §Goals#1` and `critique.md perf.2`; without a canary they erode silently as Phase 8/9 add coordination overhead. This story is the *core* perf canary in Step 7 — it also captures the time-to-PR p95 measurement that feeds G8 reporting. S7-05 (mixed-portfolio E2E) consumes the warm-mixed measurement infrastructure that this story lands.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals G6 / G7 / G8` — cold ≥ 6/hr, warm distroless ≥ 24/hr, warm mixed ≥ 10/hr; time-to-PR p95 envelope (recipe hot ≤ 240 s, RAG ≤ 420 s, LLM ≤ 600 s).
  - `../phase-arch-design.md §Testing strategy ›Performance regression tests` bullet 3 — names the canary file (`tests/perf/test_workflow_throughput.py`) and counts (6 cold + 24 warm + ≥ 10/hr mixed).
  - `../phase-arch-design.md §Process view — runtime concurrency and durability` — the wall-clock model (per-workflow durability via `AuditedSqliteSaver` fsync, single-writer audit-chain lock).
  - `../phase-arch-design.md §Physical view — deployment topology` — Linux DinD reference runner specifics.
  - `../phase-arch-design.md §Edge cases #16` — `cgr.dev` cold pull blind spot; relevant to honest cold-throughput measurement.
- **Phase ADRs:**
  - `../ADRs/0014-regression-suite-wall-clock-canary.md` — ADR-P7-014 — flag + baseline-file + runner-class discipline (same as S7-01 / S7-02).
- **Source design:**
  - `../final-design.md §Goals#1` — throughput targets.
  - `../critique.md §perf.2` — why the numbers are honest only under Linux DinD on the reference runner.
- **Existing code:**
  - `src/codegenie/cli/migrate.py` (S5-05) — the operator entry point this canary drives.
  - `src/codegenie/cli/loop.py` (Phase 6, unchanged) — the vuln entry point needed for the mixed-portfolio leg.
  - `tests/fixtures/repos/express-distroless/`, `static-go-distroless/`, `alpine-to-glibc-distroless/` — the 3-fixture distroless portfolio.
  - Phase 3/4/5/6 vuln fixtures — at least one is needed for the mixed-portfolio leg.

## Goal

`pytest tests/perf/test_workflow_throughput.py` executes 6 cold distroless workflows + 24 warm distroless workflows + a mixed-portfolio sequence on the reference Linux DinD runner and fails when cold throughput < 6/hr, warm-distroless < 24/hr, or warm-mixed < 10/hr.

## Acceptance criteria

- [ ] `tests/perf/test_workflow_throughput.py` exists with three sub-tests (cold, warm-distroless, warm-mixed) driving real `codegenie migrate` invocations (and `codegenie loop` for the mixed leg) through the public CLI, never via internal Python imports.
- [ ] Cold throughput sub-test: starts on a freshly-purged BuildKit cache (`.codegenie/cache/buildkit/` emptied + `cgr.dev` image refs un-pulled), runs 6 distinct distroless workflows in sequence, asserts ≥ 6/hr (i.e. total wall-clock ≤ 3600 s).
- [ ] Warm-distroless sub-test: warm cache prerequisite (cold pass already done in the same module), runs 24 distroless workflows, asserts ≥ 24/hr.
- [ ] Warm-mixed sub-test: 10 interleaved (vuln, distroless, vuln, distroless, …) workflows over the warm cache, asserts ≥ 10/hr.
- [ ] Per-workflow time-to-PR p95 measured and reported (informational; does *not* gate this story — G8 caps are stored under `tests/perf/baseline.json` keys for later observation): `time_to_pr_p95_recipe_hot_s`, `time_to_pr_p95_rag_s` (if cassette available), `time_to_pr_p95_llm_s` (if cassette available). For now, only recipe-hot is enforced.
- [ ] Baseline keys added to `tests/perf/baseline.json`: `workflow_cold_per_hr`, `workflow_warm_distroless_per_hr`, `workflow_warm_mixed_per_hr`, `time_to_pr_p95_recipe_hot_s`. Bumps go through `--update-perf-baseline` (from S7-01) with `--allow-runner-class-change` discipline preserved.
- [ ] Reference runner pinned in test docstring + `baseline.json`'s `runner_class`. The canary skips with a loud, structured `SKIP_REASON="runner_class_mismatch:<actual>"` when run off the reference runner (so the test is never silently green on a laptop).
- [ ] The TDD plan's red tests exist, were committed, and are green.
- [ ] `pytest tests/perf/test_workflow_throughput.py` is in CI's merge-gate lane.
- [ ] `ruff check`, `ruff format --check`, and `mypy --strict` clean on touched files.

## Implementation outline

1. Add `tests/perf/_throughput.py` with pure helpers: `purge_buildkit_cache(cache_root: Path) -> None`, `purge_cgr_dev_image_refs(refs: list[str]) -> None`, `run_one_distroless_workflow(fixture: Path, ...) -> WorkflowResult`, `run_one_vuln_workflow(fixture: Path, ...) -> WorkflowResult`. Each `run_one_*` shells out to the CLI binary (`subprocess.run` against `codegenie migrate ...` / `codegenie loop ...`), captures wall-clock + exit code + structured JSON output.
2. Build a module-scoped fixture `warm_cache_state` that performs the cold pass (which is itself a subset of the cold-throughput test data — re-use the same runs, don't double-pay).
3. Write the three sub-tests. Each computes per-hour rate as `len(workflows) / (sum_wall_clock_s / 3600)`.
4. Capture per-workflow durations into the run report. Compute p95 over the distroless-only warm runs for `time_to_pr_p95_recipe_hot_s`.
5. Wire the runner-class skip: read `CODEGENIE_RUNNER_CLASS`; if it doesn't match `baseline.json["runner_class"]`, `pytest.skip(SKIP_REASON, allow_module_level=True)` — but emit a `warnings.warn` so the skip is *loud* in CI logs.
6. Add the canary to CI's merge-gate lane. Document in the test docstring that running this canary requires ~12–15 minutes wall-clock — flag it as the budget consumer of Step 7.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/perf/test_workflow_throughput.py`

```python
# tests/perf/test_workflow_throughput.py
def test_cold_throughput_at_least_6_per_hour(throughput_run):
    cold = throughput_run.cold
    assert cold.per_hour >= 6.0, (
        f"cold throughput {cold.per_hour:.2f}/hr < 6.0/hr; "
        f"6 workflows in {cold.wall_clock_s:.1f}s; "
        f"slowest: {cold.slowest_workflow}"
    )

def test_warm_distroless_throughput_at_least_24_per_hour(throughput_run):
    warm = throughput_run.warm_distroless
    assert warm.per_hour >= 24.0, (
        f"warm-distroless throughput {warm.per_hour:.2f}/hr < 24.0/hr; "
        f"per-workflow durations: {warm.durations_s}"
    )

def test_warm_mixed_throughput_at_least_10_per_hour(throughput_run):
    mixed = throughput_run.warm_mixed
    assert mixed.per_hour >= 10.0, (
        f"warm-mixed throughput {mixed.per_hour:.2f}/hr < 10.0/hr"
    )
```

The fixture `throughput_run` is undefined — pytest errors. Commit.

A unit-level red test for the rate-computation helper:

```python
# tests/perf/test_throughput_helpers.py
def test_per_hour_uses_inclusive_wall_clock_not_per_workflow_mean():
    # arrange: 6 workflows, each 600 s wall-clock, run sequentially → 3600 s total → 6/hr
    durations_s = [600.0] * 6
    # act
    rate = per_hour_rate(durations_s)
    # assert
    assert rate == pytest.approx(6.0)

def test_per_hour_handles_zero_workflows_loudly():
    with pytest.raises(EmptyThroughputRun):
        per_hour_rate([])
```

### Green — make it pass

- Add `tests/perf/_throughput.py` with `per_hour_rate`, `EmptyThroughputRun`, `WorkflowResult`, `ThroughputLeg`, `ThroughputRun`. Pydantic-frozen result models.
- Add the `throughput_run` fixture (module-scoped) that performs cold → warm → mixed in one process so cache state is honest.
- Drive workflows via `subprocess.run` against the CLI entry points — no internal Python imports of `build_distroless_loop` / `build_vuln_loop` (per the architecture's "operator surface is the CLI"; per Goal G1).

### Refactor — clean up

- Type hints + frozen Pydantic models for `ThroughputLeg` and `ThroughputRun`.
- Docstrings on the three sub-tests explaining the exact ordering (cold → warm-distroless → warm-mixed; cache state is cumulative).
- Edge case from `phase-arch-design.md §Edge cases #16`: cold pull from `cgr.dev` is included in the cold-throughput measurement (it is *the* cold cost). Do not pre-warm `cgr.dev` images before the cold pass — that would dishonest the cold number.
- Edge case from `§Edge cases #5` (strace budget exhaust) — if a workflow times out, the canary records the timeout in the leg's `failures` field and the throughput test fails loudly with `WorkflowFailureDuringThroughput` (not a silent throughput pass on 5 successes + 1 failure).
- Per ADR-P7-014, the runner-class skip is loud (warns) — do not silently turn it into an expected-skip.
- Per Global Rule 12: a workflow that exits non-zero is a hard failure of the throughput canary, not a "skip and continue" — the canary's job is to catch silent slowdowns, not to mask correctness regressions as perf.

## Files to touch

| Path | Why |
|---|---|
| `tests/perf/test_workflow_throughput.py` | New file — the canary (G6 / G7). |
| `tests/perf/test_throughput_helpers.py` | New file — unit tests for rate helpers. |
| `tests/perf/_throughput.py` | New file — pure-function helpers + Pydantic models. |
| `tests/perf/conftest.py` | Add `throughput_run` module-scoped fixture. |
| `tests/perf/baseline.json` | Add `workflow_cold_per_hr`, `workflow_warm_distroless_per_hr`, `workflow_warm_mixed_per_hr`, `time_to_pr_p95_recipe_hot_s` keys. |
| `.github/workflows/ci.yml` | Add canary to merge-gate lane. |

## Out of scope

- **`tests/e2e/test_mixed_portfolio_warm.py`** — the E2E mixed-portfolio test (also G7) is owned by S7-05; this canary's mixed leg is the *throughput* measurement only.
- **Time-to-PR p95 RAG / LLM enforcement.** The recipe-hot p95 is captured here; RAG and LLM caps (G8) are observed-only until S7-05 lands the cassette-driven mixed run.
- **Per-worker memory.** Owned by S7-06 (measurement integrated into *this* throughput test in S7-06; not in scope to introduce here).
- **Strace budget distribution.** Owned by S7-04.
- **Dockerfile-engine p95.** Owned by S7-04.

## Notes for the implementer

- **The fixture cache state is cumulative.** Cold pass populates the BuildKit cache and `cgr.dev` image refs; warm-distroless reads them; warm-mixed continues. Don't accidentally purge between legs — that's a different (and dishonest) measurement.
- **`subprocess.run` against the installed CLI, not the in-tree module.** Per `phase-arch-design.md §Architectural context` G1, the contract is the operator CLI. If the CLI is invoked via `python -m codegenie.cli.migrate ...` rather than a `codegenie` entry-point script, fine — but use the entry-point form if it's wired up in `pyproject.toml`.
- **Cold pass *is* the BuildKit + `cgr.dev` cold cost.** Do not pre-warm. The whole point of the cold-throughput number is to honest-budget the new-runner case (`§Edge cases #16`).
- **The runner-class skip is loud.** If you run this on a laptop, the canary skips and `pytest` emits a `UserWarning` line — that is *the desired UX*. Do not "fix" the warning by suppressing it; it's the signal that the canary is runner-locked.
- **A workflow exit non-zero is a hard fail.** Per Global Rule 12 — a throughput canary that silently passes 5/6 cold workflows because one crashed is worse than no canary.
- **`time_to_pr_p95_recipe_hot_s` is the p95 over the *warm-distroless* leg only.** The cold leg includes `cgr.dev` pull cost; the mixed leg includes vuln workflows. Recipe-hot p95 has one canonical definition; do not contaminate it.
- **~12–15 min wall-clock budget for this canary.** Document in the test docstring; CI runner needs to be sized to accept the cost. If the cost exceeds 15 min in practice, raise as a follow-up to bump `phase-arch-design.md §Goals G12` rather than silently sharding the canary.
- **Per Global Rule 8 (Read before you write):** verify the CLI exit-code contract from `src/codegenie/cli/migrate.py` (S5-05) before parsing — `0` is success, `11`/`12`/`13` are escalate/paused/tampered. A `12` (paused-at-human) during a throughput canary is *not* success; treat as failure.
- **`--platform=linux/amd64` is mandatory on every BuildKit invocation** (closes critic perf.assumption.2). The throughput canary doesn't need to re-assert this — S7-02 already does — but if your subprocess invocations override it for any reason, you have a different bug.
