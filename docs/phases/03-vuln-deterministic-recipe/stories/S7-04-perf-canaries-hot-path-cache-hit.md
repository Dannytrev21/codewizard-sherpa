# Story S7-04 — Perf canaries: hot-path latency + lockfile cache hit rate + memory peak

**Step:** Step 7 — Harden — ≥ 30 adversarial fixtures, determinism canary, perf canaries, Phase-2 regression hard-gate, Phase-4 handoff verification, CI gates
**Status:** Ready
**Effort:** M
**Depends on:** S7-01 (fixture portfolio + mirror — every canary runs against these), S5-05 (full CLI vertical), S3-08 (`LockfileResolver` cache surface — the hit-rate canary asserts ≥ 70% across the portfolio)
**ADRs honored:** ADR-0011 (canonicalization + pinned `npm` minor digest — the latency canary depends on these being deterministic), ADR-0012 (pinned mirror — perf is offline, no network jitter), ADR-0014 (`ALLOWED_BINARIES` is the only exec surface — perf measurements include wrapper overhead)

## Context

Phase 3 commits to three concrete latency / efficiency goals (`final-design.md §"Cost & latency goals"` #7, #8 + `phase-arch-design.md §"Goals"` #7, #8):

- **Hot-path p95 ≤ 30 s** (excluding test suite execution) on the canary fixture, caches warm.
- **Lockfile cache hit rate ≥ 70%** across the fixture portfolio on a second pass (warm cache).
- **Peak RSS ≤ 1.5 GB** during a single remediate run (memory regression canary, advisory).

This story lands three integration tests under `tests/integration/`:

1. **`test_hot_path_latency.py`** — runs `codegenie remediate` against the `express` canary fixture with **caches warm** (pre-populated via a setup run); asserts p95 over 5 sampled runs ≤ 30 s **excluding** the test-suite execution time (the express fixture ships with a one-test suite finishing in < 1 s, so subtracting the test-suite duration is straightforward). **Gated**: CI red-fails on regression.
2. **`test_lockfile_cache_hit_rate.py`** — runs `codegenie remediate` twice across all six fixtures from S7-01; second pass should hit the lockfile resolver cache for ≥ 70% of fixtures (i.e., ≥ 5 of 6 emit `cache.replay` audit events on the second pass). **Gated**: CI red-fails on regression.
3. **Memory regression canary** — co-located in `test_hot_path_latency.py` (or its own file), uses `resource.getrusage(RUSAGE_CHILDREN)` to record peak RSS during the hot-path run; **advisory**: warns at > 1.5 GB, does **not** fail CI (advisory-not-gating per the step's exit criteria).

These canaries are **not** the determinism canary (S7-03). They measure speed + efficiency, not byte-identity. They are subject to noise (CI runner variance, network state — though the mirror is local) so the budget margins are deliberately generous: the 30 s p95 is set against a real-world expectation of ~10–15 s on the canary, with 30 s leaving headroom for noisy runners.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Goals"` #7 (hot-path p95 ≤ 30 s) and #8 (lockfile cache hit rate ≥ 70%).
  - `../phase-arch-design.md §"Testing strategy" §"Performance canary"` — the canonical list this story implements.
  - `../phase-arch-design.md §"Resource & cost profile"` — informs the memory peak budget.
  - `../phase-arch-design.md §"Risks (top 5)"` — Risk #5 (cache-hit-rate underperforms); this canary is the gate.
- **Phase ADRs:**
  - `../ADRs/0011-lockfile-canonicalization-and-npm-digest-pin-for-deterministic-diffs.md` — the canonicalization + pinned npm are why the cache is hittable across re-runs.
  - `../ADRs/0012-test-fixture-bundle-plus-resolution-plus-pinned-mirror.md` — the mirror is what makes the perf canary deterministic-enough to assert percentiles.
- **Production ADRs:** `../../../production/adrs/` — no direct dependency.
- **Source design:**
  - `../final-design.md §"Cost & latency goals"` #7, #8 — the numeric targets.
  - `../final-design.md §"Test plan" §"Performance canary"` — the named test files.
  - `../final-design.md §"Resource & cost profile"` — memory peak budget context.
- **Existing code:**
  - `src/codegenie/recipes/lockfile_resolver.py` (S3-08) — emits `cache.replay` on hits; the hit-rate canary counts these.
  - `src/codegenie/transforms/coordinator.py` (S5-03) — the path being timed.
  - `src/codegenie/audit_writer.py` — the source of truth for cache-hit accounting.
- **Style reference:**
  - `../../02-context-gather-layers-b-g/stories/` — Phase 2's bench-canary story (if present) is the shape; otherwise this story is the first perf canary in the repo and sets the pattern.

## Goal

Land `tests/integration/test_hot_path_latency.py` + `tests/integration/test_lockfile_cache_hit_rate.py` (the latter is CI-gated; the former is CI-gated on p95 and advisory on memory peak) so Phase 3's latency + efficiency commitments are enforced at merge time.

## Acceptance criteria

- [ ] `tests/integration/test_hot_path_latency.py` exists and is green on `main`. It runs `codegenie remediate` against the `express` bundle from S7-01 **5 times** with **warm caches** (a setup phase pre-runs once to populate `.codegenie/cache/`), records per-run wall-clock excluding the test-suite execution time (subtract `tests.executed.duration_ms` from the run total), computes the p95 over the 5 samples, and asserts **p95 ≤ 30 s** (gating).
- [ ] The same test records peak RSS via `resource.getrusage(RUSAGE_CHILDREN)` and emits a structured warning on > 1.5 GB but **does not fail** the test. The peak is recorded in the test output for trend monitoring.
- [ ] `tests/integration/test_lockfile_cache_hit_rate.py` exists and is green on `main`. It runs `codegenie remediate` against **each of the six fixtures** from S7-01 **twice in sequence** (first pass cold, second pass warm), counts the number of fixtures whose second pass emits a `cache.replay` audit event, and asserts the ratio ≥ **70%** (i.e., ≥ 5 of 6 fixtures hit the cache on second pass). **Gating**.
- [ ] The hot-path test uses `subprocess.run` to invoke the CLI (not the orchestrator function directly), so the measurement includes interpreter startup + click parsing + CLI plumbing.
- [ ] Both tests register `pytest.mark.perf_canary` and the marker is registered in `pyproject.toml`. S7-07 wires a CI job that selects them.
- [ ] The hot-path test's p95 assertion surfaces the **per-run wall-clock breakdown** on red-fail (`run_0: 12.3 s, run_1: 13.1 s, ..., p95 = 14.8 s, budget = 30 s`) — diagnostic, not just an `AssertionError`.
- [ ] The cache-hit-rate test's red-fail surfaces **which fixtures missed the cache** on second pass + the audit events that determined the classification — diagnostic, not just a ratio.
- [ ] The memory peak measurement is recorded for **every** perf-canary run (not just on red), so trend monitoring works without flaky failures.
- [ ] The two tests together complete in **≤ 300 s** on the CI runner (5 hot-path runs at ≤ 30 s each + the 6-fixture × 2-pass = 12 runs; 12 × 15 s typical = 180 s). The step's exit criterion documents the wall-clock budget.
- [ ] The hot-path test's express fixture ships with a **one-test suite finishing in < 1 s** so the subtraction (total wall − test-suite wall) is clean and the 30 s budget is meaningful. The test asserts `tests.executed.duration_ms < 1000` as a precondition; if the fixture's test suite grows, the precondition red-fails loudly and the budget is re-examined explicitly via a PR + ADR amendment.
- [ ] Neither canary touches the live `npmjs.org` registry; both run against the pinned mirror from S7-01 (verified by audit-log inspection — no `socket` calls outside the mirror's `file://` URL).

## Implementation outline

1. **Build the runner helper (or reuse S7-03's `run_remediate_into`).** If S7-03 has shipped `run_remediate_into(tmp_path, bundle, cve)`, reuse it directly — both stories share the canary-invocation pattern. Otherwise, factor it under `tests/integration/conftest.py` as a session-scoped fixture.
2. **Warm-cache setup phase for the hot-path test.** Before the 5 timed runs, perform one untimed setup run that populates `.codegenie/cache/` (lockfile cache + recipe cache). Then run 5 timed runs sharing that cache directory. The cache is shared across the 5 runs (this is the warm-cache scenario; the determinism canary in S7-03 is the cold scenario).
3. **Per-run wall-clock measurement.** Time each run via `time.perf_counter()` around the `subprocess.run` call. Subtract the test-suite execution time recorded in the run's `tests.executed` audit event. Compute the p95 over the 5 samples using `statistics.quantiles` or a simple sort + index.
4. **Memory peak measurement.** Wrap each run with a `resource.getrusage(RUSAGE_CHILDREN)` snapshot before and after; record `ru_maxrss` delta. On Linux, `ru_maxrss` is in KB; on macOS, it's in bytes — handle both and document. Warn if peak > 1.5 GB; do not fail.
5. **Cache-hit-rate test loop.** For each of the six fixtures:
   - First pass: cold cache, run remediate, capture the audit slice.
   - Second pass: same cache dir, run remediate, capture the audit slice.
   - Count: did the second pass emit a `cache.replay` event from the `LockfileResolver` (S3-08)?
   Tally hits / 6; assert ratio ≥ 0.70.
6. **Diagnostic output on red-fail.** Wrap the p95 assertion in `assert_p95_or_diagnose(samples, budget)` that, on mismatch, prints the per-run breakdown + the p95 + the budget. Wrap the cache-hit ratio assertion in `assert_hit_rate_or_diagnose(per_fixture_hits, budget)` that prints the per-fixture classification (hit / miss) + the audit events that determined it.
7. **Register `pytest.mark.perf_canary`** in `pyproject.toml`'s `[tool.pytest.ini_options]` `markers` list. S7-07 references it for the CI job `perf_canary`.
8. **Document the budget rationale inline.** A docstring at the top of each test file pins the budget number + cites the goal it implements + names the consequence of a red-fail (regression in the warm path or the cache surface).

## TDD plan — red / green / refactor

### Red — write the failing test first

Path: `tests/integration/test_hot_path_latency.py`

```python
"""ADR-0011 + Goals #7 | Invariant: warm-cache hot-path p95 ≤ 30 s (excluding test-suite execution) on the express canary fixture.

A regression here means one of:
- Cache miss on a path expected to be warm (S3-08 regression).
- Wrapper overhead increased (S3-01 regression).
- `ncu` or `npm install` took longer (registry mirror integrity regression — check S7-01).
- Orchestrator added a new sync step (S5-03 regression).
"""

@pytest.mark.perf_canary
def test_hot_path_p95_under_30s_warm_cache(tmp_path, bundle_fixture, npm_mirror_url, run_remediate_into) -> None: ...

@pytest.mark.perf_canary
def test_express_test_suite_under_1s_precondition(tmp_path, bundle_fixture, npm_mirror_url, run_remediate_into) -> None:
    """Express canary's test suite must stay < 1 s so the 30 s p95 budget is meaningful after subtracting test-suite time."""

@pytest.mark.perf_canary
def test_peak_rss_warning_advisory_not_gating(tmp_path, bundle_fixture, npm_mirror_url, run_remediate_into, caplog) -> None:
    """Peak RSS > 1.5 GB logs a warning but does NOT fail the test."""
```

Path: `tests/integration/test_lockfile_cache_hit_rate.py`

```python
"""ADR-0011 + Goals #8 | Invariant: second pass across the fixture portfolio hits the lockfile resolver cache for ≥ 70% of fixtures.

A regression here means one of:
- Cache-key composition changed silently (S3-08 — cache key is `(blake3(package.json), blake3(package-lock.json), npm_minor_digest, registry_mirror_digest, recipe_digest)`).
- Canonicalizer regression (lockfile bytes differ on second pass → cache miss).
- Recipe digest churned between runs (S3-04 — `recipes/digests.yaml` was edited but the recipe content wasn't).
"""

@pytest.mark.perf_canary
def test_portfolio_second_pass_cache_hit_rate_at_least_70_percent(tmp_path, bundle_fixture, npm_mirror_url, run_remediate_into) -> None: ...

@pytest.mark.perf_canary
def test_cache_hit_rate_diagnostic_surfaces_missing_fixtures_on_red(tmp_path, bundle_fixture, npm_mirror_url, run_remediate_into) -> None:
    """If the ratio is < 70%, the failure message lists which fixtures missed and the audit events that determined it."""
```

The diagnostic-on-red tests follow the same shape as S7-03's: they monkeypatch the production code to introduce a deliberate regression and assert the failure message contains the right diagnostic line. Without these, a future PR that drops the diagnostic is invisible.

### Green — make each one pass

Green requires the production code (S3-08 lockfile cache, S3-09 canonicalizer, S5-03 orchestrator) to actually meet the budgets. If the hot-path canary red-fails on first run with p95 = 45 s, **do not** raise the budget; root-cause to one of the four regression axes listed in the docstring and fix the production code. Common first failures:

- The express fixture's test suite is > 1 s — fix the precondition test first (shrink the test suite by trimming non-essential cases from the bundled `package.json` test script).
- The setup-run cache wasn't actually populated — verify by inspecting `tmp_path/.codegenie/cache/` after the setup run; expect ≥ 1 file.
- The lockfile cache miss on second pass because the cache key includes a churning component (e.g., a timestamp leaked in) — debug by logging the cache key composition.

For the cache-hit-rate test, green is reached when ≥ 5 of 6 fixtures hit on second pass. The `peer-dep-conflict` fixture intentionally errors out on first pass (no diff produced), so its second pass also errors out (and the cache is never written); it counts as a miss. This means **5 of 6 = 83%** is the realistic ceiling and **4 of 6 = 67%** is below budget. If the ratio comes in at 67%, find the second missing fixture and fix the cache-key composition.

### Refactor — clean up

After green:

- **Confirm budget headroom.** If p95 is consistently ~12 s against a 30 s budget, that's healthy headroom. If it's ~28 s, surface as a perf-debt follow-up; the budget shouldn't be load-bearing on its own margin.
- **Confirm the cache-hit-rate diagnostic actually triggers on red.** Monkeypatch the cache-key composition to include a random nonce; assert the test red-fails *and* the failure message lists the per-fixture classification.
- **Trend-monitor the memory peak.** Record the typical peak in the PR body (e.g., "express canary peak RSS = 380 MB; budget = 1500 MB"); this number should rise predictably with feature work, not silently spike.
- **Open the PR with the full perf summary.** Format: per-test wall-clock p95, per-test peak RSS, cache-hit-rate ratio. This makes the merge a 30-second review for someone trusting the green check marks.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_hot_path_latency.py` | Hot-path p95 + memory peak canary. |
| `tests/integration/test_lockfile_cache_hit_rate.py` | Cache-hit-rate canary. |
| `tests/integration/conftest.py` (extend if S7-03 hasn't already) | `run_remediate_into` fixture (reused from S7-03). |
| `pyproject.toml` (extend) | Register `perf_canary` pytest marker. |
| `tests/fixtures/repos_bundles/express.metadata.yaml` (extend if needed) | Capture the express fixture's test-suite duration upper bound (`max_test_suite_ms: 1000`) so the precondition test reads it from metadata. |

## Out of scope

- **The determinism canary.** S7-03 — separate concern (byte-identity, not latency).
- **The adversarial corpus wall-clock budget.** S7-02 — separate budget (< 90 s p95 for the adv suite).
- **Phase 2 regression hard-gate.** S7-05 — runs the Phase-2 integration suite; not a perf concern.
- **Phase-4 handoff contract test.** S7-06.
- **CI workflow wiring.** S7-07 wires the `perf_canary` job.
- **Performance optimization.** If a budget red-fails, the fix is in the originating production code (S3-08 / S5-03 / etc.), surfaced as a separate PR. This story enforces the budget; it does not optimize.
- **Cold-cache latency budgets.** Phase 3 commits to *warm-cache* p95. Cold-cache latency is bounded by `npm install` runtime, which is upstream of the orchestrator and not in scope to bound.
- **Memory peak gating.** Per the step exit criteria, memory peak is **advisory** in Phase 3. Phase 5's microVM swap will pin it tighter.

## Notes for the implementer

- **Warm-cache vs cold-cache is the load-bearing distinction.** The hot-path budget is *warm*. Without the setup run that populates `.codegenie/cache/`, the canary measures cold latency and red-fails for the wrong reason. Confirm the setup run actually populates the cache by inspecting `tmp_path/.codegenie/cache/` after step 2 of the implementation outline.
- **Subtract test-suite time, not total wall-clock.** ADR-0011 + Goals #7 specifically excludes test-suite execution from the 30 s budget. The audit event `tests.executed` carries the duration; subtract it from the total. If a future fixture has a 10 s test suite, the budget is still 30 s on the non-test path; the subtraction makes this robust.
- **Use `subprocess.run` for the CLI invocation.** Direct-function invocation inherits the test process's state (cache primed, interpreter warm) and silently underestimates real-world latency. The canary must measure CLI subprocess wall-clock to be meaningful.
- **The 5-sample p95 is a noisy estimator on a small N.** Treat it as a smoke detector, not a precision instrument. If you find yourself debating 28 s vs 32 s, the real signal is in the per-run breakdown — look for an outlier run rather than the percentile.
- **`peer-dep-conflict` fixture is the canonical cache miss.** It errors out before reaching the resolver cache write, so its second pass also misses. This is by design; the 70% budget is set against 5/6 = 83% realistic ceiling. If a future PR changes the resolver to cache the *error* (so the second pass hits), the budget should rise — surface as a separate PR + ADR amendment.
- **Memory peak is platform-dependent.** `ru_maxrss` is KB on Linux, bytes on macOS. The test must handle both; document the unit in the warning message so operators reading CI logs know which scale they're seeing. On Windows the field doesn't exist; skip the memory check on Windows runners.
- **Diagnostic-on-red is what prevents canary degradation.** Without the per-run breakdown on the hot-path test and the per-fixture classification on the cache-hit-rate test, a future PR that drops the diagnostic is invisible until the canary actually red-fails — and by then the diagnostic is gone. Pin the diagnostic shape with its own tests (see the red section).
- **The memory peak is advisory, not gating, in Phase 3.** Phase 5's microVM swap will pin it tighter. Don't promote the advisory to a gate without an ADR amendment.
- **The perf canaries are subject to CI runner variance.** A 2× headroom (30 s budget against ~12–15 s typical) is intentional. If the CI runner changes (new hardware), re-baseline before raising or lowering the budget.
