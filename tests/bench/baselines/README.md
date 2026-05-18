# Bench baselines — refresh ritual (S8-03)

Baselines for the three Phase-2 bench scripts live in this directory:

* `portfolio_walltime.json` — per-fixture cold + warm p50 walltime for the dev-laptop bench (`tests/bench/bench_portfolio_walltime.py`). Advisory; comment-only on ≥ 50 % regression.
* `portfolio_walltime_hosted_runner.json` — per-fixture cold + warm p50 walltime for the nightly hosted-runner bench (`tests/bench/bench_portfolio_walltime_hosted_runner.py`). **Gating**: ≥ 100 % regression OR p95 > 360 s fails the build.

The `bench_index_health_overhead.py` script has no committed baseline — its threshold is a static fraction (≥ 10 % of cold-gather walltime → comment).

## File shape

Every baseline JSON carries a metadata header AND a `measurements` map:

```json
{
  "refreshed_at": "<ISO-8601 UTC timestamp>",
  "refreshed_by": "<GitHub username>",
  "reason": "<one-line justification>",
  "measurements": {
    "<fixture-name>/<metric>": <seconds>,
    ...
  }
}
```

The three metadata keys are asserted by `tests/bench/test_baseline_has_metadata.py`. The `measurements` map is loaded by `tests/bench/_bench_kernel.load_baseline()`.

## When to refresh

Refresh ONLY when a deliberate change makes a regression intentional (new probe, new fixture, new strategy). Process:

1. **Run the bench locally** with the change applied. Capture the measurement output (the bench scripts print a JSON block to stdout).
2. **Open a separate PR** titled `bench(baselines): refresh <bench-name> — <one-line reason>`. The PR touches only this directory.
3. **Update the metadata header** in the same commit:
   * `refreshed_at` — ISO-8601 UTC timestamp of the measurement run.
   * `refreshed_by` — your GitHub login.
   * `reason` — one line; what code change made the regression intentional. Link the PR that introduced the change.
4. **Reviewer approval is required.** A baseline-refresh PR with no `reason` linking back to an intentional change is a code smell — reviewers should question whether the regression is real or noise.

`git log tests/bench/baselines/` is the audit trail.

## When NOT to refresh

* Variance from a shared CI runner (the bench scripts already take the p50 of N runs to dampen this).
* A one-off failing nightly — re-run via `workflow_dispatch` first.
* "It's been a while since we touched this" — baselines age in place; freshness is not a signal here.

If you find yourself refreshing baselines repeatedly to silence regressions, that is the prompt to escape-valve: commit per-fixture `.codegenie/cache/` blobs (see `final-design.md §"Open Q 6"`). Editing the baseline JSON to hide a real regression is a deception, not a fix.
