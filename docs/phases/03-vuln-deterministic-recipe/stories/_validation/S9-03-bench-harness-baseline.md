# Validation report: S9-03 — Bench harness + 7-day rolling baseline

**Validated:** 2026-05-20
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S9-03 lands seven performance benchmarks for Phase 3's load-bearing components plus
a 7-day rolling-mean baseline harness that fails the CI bench step on a > 25 %
regression. The story's *goal* is sound and traces cleanly to `High-level-impl.md
§Step 9` and `phase-arch-design.md §Testing strategy / Performance regression
budgets`. The story's *premises*, however, had drifted from shipped reality and its
central mechanism had two genuine implementation defects.

Four parallel critics (Coverage, Test-Quality, Consistency, Design-Patterns) raised
**26 findings — 6 block, 17 harden, 3 nit**. The dominant theme: the story was
written against a `tests/bench/` directory that no longer exists. Phase 2's S8-03
landed a whole bench infrastructure (`_helpers.py`, `_bench_kernel.py`, `baselines/`,
non-marker bench scripts) that S9-03 was unaware of — so its file-naming plan, its
"refactor into `_helpers.py`" step, and its CI-surface picture were all wrong. Two
further block findings were mechanism defects: `bench_*.py`-named files are never
pytest-collected (so the `-m bench` collection guard would never see them), and the
recommended static-key `actions/cache@v4` shape cannot accumulate a rolling window
(cache entries are immutable per key, so the baseline would freeze after run 1 and
the regression assertion would be permanently dead).

Every block has a clean in-place fix — none required rewriting the goal — so the
verdict is **HARDENED**. All 26 findings were addressed in the story file. No
Stage-3 research was required.

## Findings by critic

### Coverage critic

1. **`block`** — Ambiguous function signatures. AC-8 defined `record_and_assert`
   without the `units=` kwarg the TDD plan calls it with; `compute_rolling_mean`'s
   Implementation-outline signature `(entries, *, days=7)` lacked the
   `bench_name`/`python_version` filter args the TDD plan passes. An executor must
   guess. Fix: pin both signatures.
2. **`block`** — "entry count < 1" undefined as windowed-vs-total. AC-8 never said
   whether the seed-vs-assert count is the windowed (last-7-days) count or the
   total. The "all entries exist but all > 7 days stale" case (windowed 0, total
   > 0) was uncovered. Fix: pin to the windowed count; add the all-stale edge case.
3. **`harden`** — `compute_rolling_mean`'s `None` return path is not covered by any
   AC, and AC-8 never said how `record_and_assert` consumes `None` (must seed, not
   divide). Fix: AC + test for the `None` branch.
4. **`block`** — AC-12 conflated two persistence mechanisms ("uploads `.baseline.json`
   as a **workflow artifact**" then recommends `actions/cache@v4`) with incompatible
   accumulation semantics. The rolling-7-day window is impossible unless the file
   survives and *grows* across runs. Fix: rewrite AC-12 to the `actions/cache@v4`
   accumulating-key pattern; drop "as a workflow artifact".
5. **`harden`** — No AC for `bwrap`-absent skip behavior on `bench_bundle_builder_cold`
   + `bench_workflow_e2e_warm` (both need the jail; absent on macOS local dev). Fix:
   add a skip-guard AC reusing S9-01's `_bwrap_required(platform)` helper.
6. **`harden`** — `bench_workflow_e2e_warm`'s warmup was under-specified ("committed
   under `tests/fixtures/npm-cache/` *or* constructed in the test fixture" — two
   materially different impls). Fix: pin to a session-scoped `conftest.py` fixture
   that constructs (not commits) the npm cache.
7. **`harden`** — AC-9 ("both gates must pass") had an ordering escape hatch: a seed
   run skips the relative assertion, and nothing said a seed run still *records*. A
   wrong impl could record only on assert-pass, starving the window. Fix: pin
   "`record_and_assert` always appends before deciding whether to assert".
8. **`harden`** — Goal says "fails the CI bench job on > 25 % regression" but no AC
   verified the end-to-end gating chain (a raised `AssertionError` → non-zero job
   exit via `continue-on-error: false`). Fix: strengthen the `test_ci_workflow.py`
   AC to assert the gating-step shape.
9. **`nit`** — `.baseline.json` schema vs `units` consistency — folds into finding 1.

Goal-trace check: all ACs trace to the goal; the most dangerous escape hatch was
finding 4 (an executor could satisfy AC-12 literally and ship a baseline that resets
every run — every AC green, the rolling window silently dead).

### Test-Quality critic

1. **`harden`** — `test_record_and_assert_fails_on_25_percent_regression` used
   `pytest.raises(AssertionError, match="regression")`. AC-8 promises "a diagnostic
   naming the regression %", but the test only checks the literal word "regression".
   `AssertionError("regression detected")` with zero numbers passes. Rule 9
   behavior-not-intent. Fix: assert the message names the bench, the measurement,
   the rolling mean, and the %.
2. **`harden`** — No boundary test at exactly `1.25 × mean`. Tests used 1.24× and
   1.26×; an off-by-one `<` vs `<=` mutation survives both. Fix: add a test at
   exactly 125.0 vs mean 100.0 (must pass — `<=`).
3. **`block`** — `compute_rolling_mean -> float | None` but the `None` branch is
   never tested. Mutation `return 0.0` for an empty window survives — and that
   corrupts `record_and_assert` (`measurement <= 1.25 * 0.0` fails every run). Fix:
   two tests for the `None` path (all-stale window; unknown bench).
4. **`harden`** — `test_python_versions_do_not_cross_contaminate` was asymmetric: it
   proved 3.11 seeds but never proved a 3.11 write leaves the 3.12 entry untouched.
   An impl that ignores `python_version` could still pass. Fix: assert both
   directions and `len(data) == 2`.
5. **`harden`** — No test/AC proves a bench file actually *measures its named
   component*. A bench timing `pass` runs in ~0 ms, passes `< 500 ms`, and stays a
   silent dead canary forever. The Phase 2 `test_cache_hit_dispatch.py` defends
   against exactly this with a semantic `isinstance(..., CacheHit)` assertion. Fix:
   add a semantic result-assertion to each of the seven bench ACs.
6. **`harden`** — p-quantile budgets lacked sampling discipline as an AC (it was
   only in §Notes), and N = 20 is too small for a stable p95 (canonical guidance —
   pytest-benchmark / JMH — is ≥ 50 rounds). Fix: promote the median/quantile choice
   to ACs; raise `bench_recipe_match` to ≥ 50 samples.

### Consistency critic

1. **`harden`** — Stale `tests/bench/` inventory. The story claimed three files; the
   directory actually holds S8-03's `_helpers.py`, `_bench_kernel.py`, `baselines/`,
   three non-marker bench scripts, and three smoke tests. The `@pytest.mark.bench`
   *marker* count IS still 3 (verified by `grep -rl`) — so the guard-logic premise
   holds, but the inventory claim is false and feeds findings 2 and 3.
2. **`block`** — `_helpers.py` collision. The §Refactor said "lift quantile helpers
   into `tests/bench/_helpers.py`" — but `_helpers.py` already exists (S8-03) as the
   atomic `bench-results.json` merge writer. Fix: new module `tests/bench/_sampling.py`.
3. **`block`** — `bench_*.py` prefix is not pytest-collected. `pyproject.toml` does
   not override `python_files` (default `test_*.py`); the guard runs
   `pytest --collect-only -m bench ... | grep -c '::test_'`. A `bench_*.py`-named
   file is invisible to pytest, so bumping the guard to 10 makes it permanently RED.
   Story Note ("the `bench_` prefix … so the collection guard counts them
   correctly") is exactly backwards. Fix: name the files `test_bench_*.py`; keep the
   verbatim bench *name* as a string constant.
4. **`block`** — `actions/cache@v4` static key freezes the baseline. `actions/cache`
   only saves on a cache *miss*; a static `…-v1` key means run 1 saves and every
   later run hits-and-never-resaves → `.baseline.json` frozen at one entry → the
   7-day window never accumulates → the regression assertion is dead code. Directly
   contradicts the story's own Goal. Fix: unique-per-run key + `restore-keys` prefix.
5. **`harden`** — `Depends on: S9-01` only, but the seven benches exercise
   `PluginRegistry` + 3 plugins, `BundleBuilder`, `VulnIndex`, `RecipeRegistry`, the
   spanning event log, and `codegenie remediate` + the `express-cve` fixture — almost
   all `HARDENED`-not-`GREEN`. S9-01/S8-04 handled the same understatement by
   expanding `Depends on` and adding a precondition-check step. Fix: same.
6. **`harden`** — CI-surface undercount. The story saw one bench surface; there are
   three (`-m bench` step in the `test` job; the separate top-level `bench` job;
   `bench-nightly.yml`). Fix: enumerate all three, scope this story to the first,
   declare the other two out of scope.

### Design-Patterns critic

1. **`block` → resolved as documented coexistence** — S8-03's `_bench_kernel.py`
   docstring explicitly says "Adding a fourth bench in Phase 3+ requires zero edits
   to the kernel" — a seam built *for this story* that S9-03 was unaware of. The two
   mechanisms are, however, genuinely different (committed-curated baseline vs
   auto-rolling per-runner baseline), so a separate module is justified — but the
   story must acknowledge `_bench_kernel.py`, justify the split, and avoid
   collisions. Fix: §Notes paragraph + §References entry.
2. **`harden`** — Quantile helpers wrongly placed in `_helpers.py` (single-purpose
   atomic merge writer). Fix: `tests/bench/_sampling.py`.
3. **`harden`** — Naming smell: a new `_baseline.py` adjacent to the existing
   `baselines/` directory. Fix: rename to `_rolling_baseline.py`.
4. **`harden`** — Functional-core / imperative-shell split not enforced.
   `record_and_assert` tangled the pure regression decision with file I/O. Fix:
   decompose into a pure `regression_verdict(...)` (filesystem-free, independently
   testable) + an impure shell — mirroring `_bench_kernel.py`'s `compare_to_baseline`
   / `post_comment_if` split.
5. **`harden`** — `sample_p95` crosses rule-of-three (seven consumers). Promote from
   §Refactor (routinely dropped under time pressure) to an AC.
6. **`nit`** — Magic `1.25` → a `Final` constant (`_REGRESSION_THRESHOLD`) with a
   comment citing the arch doc. Bench names as raw `str` — leave as-is; a `NewType`
   wrapper would be over-engineering per Rule 2 (names are pinned verbatim and
   structurally guarded by the collection count).
7. **`nit`** — `record_and_assert` should mirror `_helpers.merge_bench_result`'s
   atomic tmp-replace write technique (not share code — shapes differ).

## Research briefs

None. No finding was tagged `NEEDS RESEARCH`. The one research-adjacent note
(Test-Quality F6 — minimum sample count for a stable p95) was answered inline from
well-known benchmarking guidance (pytest-benchmark / JMH ≥ 50 rounds) and folded
into the harden directly.

## Conflict resolutions

No critic-vs-critic conflicts. All findings were mutually compatible:

- Design-Patterns F1 proposed an *observable* outcome (the story documents the
  relationship to `_bench_kernel.py`) rather than a pattern-name mandate — accepted
  as a §Notes paragraph, consistent with editor rule 4.
- Design-Patterns F5 (promote `sample`/`quantile` helper to an AC) clears the
  rule-of-three threshold cleanly (seven consumers from day one) — no conflict with
  Rule 2 / editor rule 5; promoted to an AC phrased as an observable ("the seven
  bench files do not inline a sample loop").
- Design-Patterns F6 explicitly *declined* a `NewType` wrapper for bench names on
  Rule 2 grounds — the validator concurred; only the `Final` constant was adopted.

## Edits applied

### Edit 1 — Header: Status → HARDENED, Depends on expanded
- Source: Consistency F5
- `Status: Ready` → `HARDENED (validated 2026-05-20 …)`. `Depends on: S9-01` →
  S9-01 + the full upstream component set (S2-01, S3-02, S3-04, S5-01, S6-01, S6-05,
  S7-01..S7-05, S8-01/S8-02) with an executor "pause and mark BLOCKED" instruction.

### Edit 2 — `## Validation notes` block inserted after the header
- Records the 26 findings and the change summary.

### Edit 3 — §Context rewritten
- Source: Consistency F1, F3, F6
- Corrected the `tests/bench/` inventory; enumerated the three CI bench surfaces;
  added the file-name-vs-bench-name distinction with the pytest-collection reason.

### Edit 4 — §References "Existing code" expanded
- Source: Consistency F1/F2, Design F1
- Added `_helpers.py`, `_bench_kernel.py`, `baselines/` + `test_baseline_has_metadata.py`
  entries; called out the semantic-assertion pattern in `test_cache_hit_dispatch.py`.

### Edit 5 — §Acceptance criteria rewritten
- Source: all four critics
- Added a naming-convention preamble; added a §0 precondition-check AC; added the
  semantic result-assertion to each of the seven bench ACs; added the `bwrap`
  skip-guard to two; pinned the `_rolling_baseline.py` / `_sampling.py` signatures;
  pinned `record_and_assert` behavior (always-append, windowed-count seed,
  diagnostic contents); rewrote the CI-persistence AC to the accumulating-key
  pattern; added the cache-key + gating-chain assertions to the `test_ci_workflow.py`
  AC; raised `bench_recipe_match` to ≥ 50 samples.

### Edit 6 — §Implementation outline rewritten
- Source: Coverage F1/F6, Consistency F4, Design F2/F3/F4
- `_rolling_baseline.py` (pure core + impure shell, `_REGRESSION_THRESHOLD` constant,
  atomic append); new `_sampling.py`; `test_bench_*.py` file names; the
  `conftest.py` warm-up fixture; the unique-key `actions/cache` pattern; CI
  integration scoped to surface (a).

### Edit 7 — §TDD plan Red section rewritten
- Source: Test-Quality F1–F6, Coverage F1/F2/F3
- Import path → `_rolling_baseline`; added pure `regression_verdict` tests including
  the exact-1.25× boundary; added two `None`-branch tests; added the all-stale-window
  seed test; rewrote the regression-diagnostic test to assert message contents;
  made the cross-contamination test bidirectional.

### Edit 8 — §Green / §Refactor updated
- Source: Consistency F2/F3, Design F2/F5
- Green: `test_bench_*` files, `_BENCH_NAME` constant, the cache-key wiring.
  Refactor: the `_sampling.py` placement note (not `_helpers.py`).

### Edit 9 — §Files to touch table rewritten
- Source: Consistency F2/F3, Design F3
- All seven bench files → `test_bench_*.py`; `_baseline.py` → `_rolling_baseline.py`;
  added `_sampling.py` and `conftest.py` rows.

### Edit 10 — §Out of scope: bench-surfaces bullet added
- Source: Consistency F6
- The top-level `bench` job + `bench-nightly.yml` declared explicitly out of scope.

### Edit 11 — §Notes for the implementer updated
- Source: Consistency F3, Design F1/F4/F6/F7, Coverage F4
- Rewrote the backwards file-prefix note; added the two-baseline-mechanisms note,
  the functional-core/imperative-shell note, and the atomic-append note; rewrote the
  threshold note to name the `Final` constant; rewrote the baseline-persistence note
  to the unique-key requirement.

## Verdict rationale

HARDENED. The story carried six block findings — by the editor's count heuristic
(> 3 blocks) a RESCUE candidate — but the dispositive RESCUE test is "do the fixes
require rewriting the *goal*?" They do not. Two blocks (Consistency F1/F2, the stale
inventory + `_helpers.py` collision) are drift-from-shipped-reality reconciliations.
Three (Consistency F3/F4, Coverage F1/F2) are mechanism contradictions with clean,
fully-specified in-place fixes. One (Test-Quality F3) is a missing test. The goal —
seven benches measuring the seven verbatim Phase 3 budgets + a 7-day rolling-mean
baseline + a gating CI step — is coherent and traces directly to `High-level-impl.md
§Step 9` and `phase-arch-design.md §Testing strategy`. Sibling S9-01 carried seven
blocks and was likewise HARDENED on the same reasoning. All 26 findings were closed
in place.

## Recommended next step

`phase-story-executor` — **but only once the upstream components are GREEN.** The
seven benches measure `PluginRegistry` + the three plugins (S7-01..S7-05),
`BundleBuilder` (S3-04), `VulnIndex` (S3-02), `RecipeRegistry` (S5-01), the spanning
event log (S6-01), and `codegenie remediate` (S6-05) against the `express-cve`
fixture (S8-01/S8-02). As of 2026-05-20 those stories are `HARDENED`, not `GREEN`.
The story's new §0 precondition-check AC instructs the executor to verify each
component is on disk and to mark S9-03 `BLOCKED` (with an `_attempts/` entry) rather
than stub or `xfail` the benches if any is absent. This is a phase-sequencing gate,
not a story-quality defect — S9-03 is itself ready to execute the moment its
dependencies land.
