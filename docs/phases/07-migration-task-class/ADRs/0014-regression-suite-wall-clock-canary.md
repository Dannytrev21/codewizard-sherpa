# ADR-0014: Regression-suite wall-clock canary — permanent perf gate, never retired

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** ci · performance · permanent-canary · enforcement
**Related:** [ADR-0009](0009-contract-surface-snapshot-canary.md), [ADR-0001](0001-six-named-additive-seams-and-adr-0028-amendment.md)

## Context

Extension-by-addition has two failure modes worth catching mechanically: (1) accidental contract drift (caught by the contract-surface snapshot, ADR-0009), and (2) accidental performance regression — a new phase whose tests don't *break* existing logic but make the regression suite materially slower. Slow tests get skipped, sharded, or marked flaky; the cumulative effect across many phases is that "the suite passes" becomes a meaningless invariant (`critique.md §best-practices.5`: the second half — "extension-by-addition is one invariant; not silently slowing the regression suite is another").

The synthesizer's response (`final-design.md §Goals#10`, `§Component 9`; `phase-arch-design.md §Component 11`): a permanent CI test that records `pytest --xdist -n auto` p50 / p95 wall-clock across the full vuln + distroless regression suite, compared against a checked-in `tests/perf/baseline.json`. >10% regression in either p50 or p95 fails the build with the slowest 10 tests highlighted.

The canary survives forever — Phase 8, 9, 15, every later phase pays if they slip the budget. Goal targets: p50 ≤ 4 min, p95 ≤ 7 min (Goal G12).

## Options considered

- **No perf canary; trust reviewer attention.** Phase-by-phase slowdowns accumulate silently; suite eventually becomes unrunnable in CI.
- **Per-test perf budgets.** Burdensome to author; brittle on legitimate test additions.
- **Suite-level wall-clock canary with baseline.json (synthesizer's pick).** One canary catches cumulative drift; baseline regeneration via `pytest --update-perf-baseline` flag (deliberate, not casual).
- **Suite-level wall-clock canary without baseline (absolute thresholds only).** Brittle on CI infrastructure changes; baseline-relative is more honest.

## Decision

Ship `tests/perf/test_regression_suite_wall_clock.py` as a permanent CI test. It runs the full regression suite under `pytest -n auto` with LFS-pack-restored caches, records p50 + p95 wall-clock, compares against `tests/perf/baseline.json`. Fails if `p50 > baseline.p50 * 1.10 OR p95 > baseline.p95 * 1.10 OR p95 > 7 min OR p50 > 4 min`. Baseline is regenerated via `pytest --update-perf-baseline` — deliberate. The test reports the slowest 10 tests in its failure output for the PR author.

## Tradeoffs

| Gain | Cost |
|---|---|
| Permanent enforcement of suite wall-clock — Phase 8/9/13/14/15 cannot silently introduce a 30% slowdown over the lifetime of the project | One additional CI step per PR (~suite wall-clock); on a 7-minute suite, that's 7 minutes per CI run — non-trivial but bounded |
| The >10% threshold is wide enough to absorb test additions; tight enough to fire on accumulated drift across phases | Calibration question: 10% may be too tight on small suites or too loose on large ones; revisit if the suite size doubles |
| The "slowest 10 tests" output gives the PR author actionable feedback — they see exactly which test slowed down | Authors may game the canary by parallelizing badly-written tests instead of fixing them; the `-n auto` scheduler should normalize most cases |
| `tests/perf/baseline.json` is a checked-in artifact — every change to it is reviewable in PR diff | Baseline regeneration discipline ("regenerate only when slowdown is justified") is convention-enforced; can erode if reviewers don't scrutinize |
| Pairs with ADR-0009's contract-surface canary — one catches API/schema drift, the other catches performance drift; together they cover the two named failure modes of extension-by-addition | Two permanent canaries together adds operational overhead; both are budgeted (3 s for snapshot, 7 min for perf) |

## Consequences

- `tests/perf/test_regression_suite_wall_clock.py` is on the CI gate list; failure blocks merge.
- `tests/perf/baseline.json` lives at the repo root; bumped via `pytest --update-perf-baseline`; bumps are reviewable.
- The Phase 7 PR ships the initial `baseline.json` after the first measured run on the canonical CI environment.
- Phase 8/9/13/14/15 each pay one baseline regeneration if their feature adds enough tests to legitimately move the wall-clock — paired with a perf justification in PR description.
- The test infrastructure assumes `pytest-xdist -n auto` + LFS-pack-restored caches; documented in CI configuration.
- `tests/perf/test_buildkit_cache_hit_rate.py` (G10), `tests/perf/test_workflow_throughput.py` (G6/G7), `tests/perf/test_dockerfile_engine_p95.py` (G14), `tests/perf/test_strace_budget_distribution.py` (Risk #3) — separate canaries with narrower scopes; this ADR covers the *suite-level* one only.

## Reversibility

**Low.** Removing the canary undoes the only mechanical enforcement of suite wall-clock. The discipline reverts to "the reviewer checks how long CI took" — which empirically doesn't survive multiple phases. The asymmetry is deliberate; this ADR exists to be permanent.

## Evidence / sources

- `../final-design.md §Goals#10` (regression-suite wall-clock target)
- `../final-design.md §Component 9` (perf canary, never retired)
- `../phase-arch-design.md §Component 11` (full design)
- `../phase-arch-design.md §Goals G12` (regression-suite wall-clock canary)
- `../critique.md §best-practices.5` (the missing time-budget enforcement)
