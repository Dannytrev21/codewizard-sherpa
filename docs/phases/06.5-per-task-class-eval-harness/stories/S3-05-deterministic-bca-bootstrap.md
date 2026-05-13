# Story S3-05 — Deterministic BCa bootstrap for `lower_bound_95`

**Step:** Step 3 — Implement the runner: asyncio fan-out, subprocess rubric, aggregator with BCa bootstrap
**Status:** Ready
**Effort:** M
**Depends on:** S3-02 (aggregator scaffolding)
**ADRs honored:** **ADR-0002 (load-bearing — promotion gate keys on `lower_bound_95`)**

## Context

Per ADR-0002, the promotion gate keys on `BenchRunReport.lower_bound_95`, not `mean_score`. This story implements the BCa bootstrap that computes `lower_bound_95` deterministically: 1000 resamples, seeded by `int(run_id[:8], 16)`, returning the 2.5th percentile of bootstrapped means. The bootstrap is the **single probabilistic surface** in an otherwise fully-deterministic harness — it is leafed and seeded. Identical inputs must produce byte-identical `lower_bound_95`.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Determinism vs probabilism` (the bootstrap row), `§Components → runner.py`
- **Phase ADRs:** `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md` (read whole), `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md` (held-out floor for tier promotion)
- **Source design:** `../final-design.md §Departures from all three inputs #2`, `§Open Q #5`
- **Standard reference:** Efron, *An Introduction to the Bootstrap* (1993), §14 — BCa (bias-corrected and accelerated)

## Goal

Implement `compute_lower_bound_95(per_case_scores: Sequence[float], *, run_id: str, n_resamples: int = 1000) -> float` that returns a deterministic, seeded BCa-bootstrap 95% one-sided lower bound on the mean.

## Acceptance criteria

- [ ] Seed derivation: `seed = int(run_id[:8], 16)` is the only source of randomness; the bootstrap uses `numpy.random.default_rng(seed)` (or `random.Random(seed)` if numpy is not a dependency — pick one explicitly).
- [ ] Two runs with identical inputs (same `run_id`, same per-case score sequence) produce a **byte-identical** `lower_bound_95` when serialized via `float.hex()`. A test asserts this across 100 reruns.
- [ ] Hypothesis property test: for `N ≥ 5` and any sequence in `[0, 1]^N` with `stddev > 0`, the bound satisfies `mean - 2*stddev <= lower_bound_95 <= mean`. Use `hypothesis.strategies.lists(floats(min_value=0.0, max_value=1.0), min_size=5, max_size=50)`.
- [ ] Degenerate case `stddev == 0` (all scores identical) → `lower_bound_95 == mean` (bypass the bootstrap; no resampling needed).
- [ ] Edge case `N < 5` → `lower_bound_95 = 0.0` with a `WARNING` log including `n_cases` and a pointer to ADR-0002 (the gate will refuse promotion at `N < min_cases_for_promotion` anyway).
- [ ] `n_resamples = 1000` per the literature default; expose as a kwarg for property-test speed but the runner always passes 1000.
- [ ] Wire into S3-02's aggregator: `lower_bound_95` is set on the `BenchRunReport` once `per_case` is finalized.
- [ ] `mypy --strict`, ruff clean; the red test `tests/unit/test_bootstrap.py::test_byte_identical_lower_bound_across_reruns` exists and is green.

## Implementation outline

1. New module `src/codegenie/eval/bootstrap.py`:
   ```python
   def compute_lower_bound_95(scores: Sequence[float], *, run_id: str, n_resamples: int = 1000) -> float:
       if len(scores) < 5:
           structlog.warn("bootstrap_n_too_small", n=len(scores), see_adr="ADR-0002")
           return 0.0
       arr = np.asarray(scores, dtype=np.float64)
       if float(arr.std(ddof=1)) == 0.0:
           return float(arr.mean())
       seed = int(run_id[:8], 16)
       rng = np.random.default_rng(seed)
       boot_means = np.empty(n_resamples, dtype=np.float64)
       for i in range(n_resamples):
           sample = rng.choice(arr, size=arr.size, replace=True)
           boot_means[i] = sample.mean()
       # BCa adjustment:
       z0 = _bias_correction(arr, boot_means)
       a = _acceleration(arr)
       alpha_lower = _bca_alpha_lower(z0, a, 0.025)
       return float(np.percentile(boot_means, alpha_lower * 100))
   ```
2. `_bias_correction(arr, boot_means)`: `z0 = norm.ppf(mean(boot_means < arr.mean()))`.
3. `_acceleration(arr)`: jackknife-based acceleration constant per Efron §14.3.
4. Call from S3-02's aggregator: after sorting `per_case` by `case_id`, compute `lower_bound_95 = compute_lower_bound_95([s.score for s in per_case], run_id=plan.run_id)` and set on the report.

## TDD plan — red / green / refactor

### Red

`tests/unit/test_bootstrap.py`:

```python
def test_byte_identical_lower_bound_across_reruns():
    scores = [0.6, 0.7, 0.8, 0.9, 0.55, 0.65, 0.75, 0.85, 0.5, 0.95]
    run_id = "abc12345" + "0" * 8
    runs = {compute_lower_bound_95(scores, run_id=run_id).hex() for _ in range(100)}
    assert len(runs) == 1, runs

@given(scores=st.lists(st.floats(min_value=0.0, max_value=1.0,
                                  allow_nan=False, allow_infinity=False),
                      min_size=5, max_size=50))
def test_bca_bound_within_mean_minus_two_stddev_window(scores):
    arr = np.asarray(scores)
    if arr.std(ddof=1) == 0.0:
        return  # degenerate handled separately
    lb = compute_lower_bound_95(list(scores), run_id="deadbeef" + "0" * 8)
    assert arr.mean() - 2 * arr.std(ddof=1) <= lb <= arr.mean() + 1e-9
```

### Green

Implement `compute_lower_bound_95` with the simplest correct BCa: bias correction + jackknife acceleration. Vectorize the resample loop with `rng.choice` if numpy is available.

### Refactor

Pull `_bias_correction`, `_acceleration`, `_bca_alpha_lower` into private helpers with their own unit tests (verified against a published worked example from Efron §14.3); add a `pytest -m slow` marker on the 100-rerun byte-identical test so it can be skipped locally; add a docstring stating the seed-derivation rule and citing ADR-0002 verbatim ("changing the seed-derivation rule invalidates the audit chain's reproducibility claim").

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/bootstrap.py` | New module — BCa implementation |
| `src/codegenie/eval/runner.py` | Wire the call into the aggregator |
| `tests/unit/test_bootstrap.py` | Determinism + Hypothesis property + degenerate cases |
| `pyproject.toml` | If numpy is not yet a dep, add it (and `scipy` for `norm.ppf`, or implement `norm.ppf` locally) |

## Out of scope

- Switching to Wilson interval (the ADR-0002 revisit trigger — future ADR amendment if `score ∈ {0.0, 1.0}` rate > 80%).
- Two-sided confidence intervals (only the lower bound matters for the gate).
- Cross-task-class bootstrap stitching (Phase 16).

## Notes for the implementer

- **The seed derivation rule is structural state.** ADR-0002 calls it out by name: "changing it would invalidate the audit chain's reproducibility claim." If you find a reason to change it, escalate via an ADR amendment, not a code change.
- BCa over the percentile method is the right choice because `BenchScore.score ∈ [0, 1]` is asymmetric near the boundaries; the bias correction matters at `N ≈ 10`.
- The Hypothesis bound `mean - 2*stddev <= lower_bound_95 <= mean` is a *sanity* property, not the canonical BCa property. It catches gross implementation bugs (e.g., returning the upper bound by accident, or returning `mean + stddev`). It does not certify BCa correctness — that's what the Efron §14.3 worked example is for in the unit test.
- The numpy dependency is small and the BCa math is materially harder to write correctly without it. If the project rejects numpy, implement `_acceleration` with stdlib `statistics` + a hand-rolled `norm.ppf` (e.g., Acklam's algorithm); leave a TODO and a citation.
- The degenerate `stddev == 0` path is required — without it, the jackknife denominator is zero and the bootstrap explodes.
- The `N < 5` floor is conservative: BCa is known to be unreliable below ~5 samples. The promotion gate's `min_cases_for_promotion` floor (10 for bronze) makes the practical gate stricter than this safeguard.
