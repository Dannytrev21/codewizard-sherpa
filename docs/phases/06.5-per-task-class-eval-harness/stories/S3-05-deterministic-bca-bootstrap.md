# Story S3-05 — Deterministic BCa bootstrap for `lower_bound_95`

**Step:** Step 3 — Implement the runner: asyncio fan-out, subprocess rubric, aggregator with BCa bootstrap
**Status:** Ready
**Effort:** M
**Depends on:** S3-02 (aggregator scaffolding — fills the `lower_bound_95=0.0` placeholder)
**ADRs honored:** **ADR-0002 (load-bearing — promotion gate keys on `lower_bound_95`)**, ADR-0006 (curation-class held-out floor reinforces small-N caution)

## Context

Per ADR-0002, the promotion gate keys on `BenchRunReport.lower_bound_95`, not `mean_score`. This story implements the BCa bootstrap that computes `lower_bound_95` deterministically: 1000 resamples, seeded by `int(run_id[:8], 16)`, returning the 2.5th percentile of bootstrapped means as a one-sided 95% lower confidence bound.

The bootstrap is the **single probabilistic surface** in an otherwise fully-deterministic harness (arch §Determinism vs probabilism). It is leafed (only the aggregator calls it) and seeded (the seed derives from `run_id`, which is itself content-addressed in S3-01). Identical inputs must produce a byte-identical `lower_bound_95` — that property is what makes the audit chain reproducible across host reboots, CI runners, and Python patch versions.

The BCa (bias-corrected and accelerated) variant matters because `BenchScore.score ∈ [0, 1]` is bounded; symmetric percentile bootstrap produces bounds outside `[0, 1]` near the corners. BCa adds two corrections (`z0` for bias from the boundary, `a` for acceleration via jackknife) that are well-studied at N ≈ 10 — the floor for `min_cases_for_promotion[bronze]`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Determinism vs probabilism` — the bootstrap row; "leafed and seeded — no other component branches on RNG."
  - `../phase-arch-design.md §Components → runner.py` — six-phase pipeline step 4 (aggregate) ends with the bootstrap.
  - `../phase-arch-design.md §Agentic best practices → Confidence handling` — `lower_bound_95` is the sole gate signal; `mean` and `stddev` are reported but not consumed.
  - `../phase-arch-design.md §Testing strategy → Property tests` — the `mean - 2*stddev ≤ lower_bound_95 ≤ mean` sanity property is anchored here.
- **Phase ADRs:**
  - `../ADRs/0002-promotion-gate-keys-on-lower-bound-95.md` — read in full; §Decision pins the seed derivation; §"Revisit trigger" pins the future Wilson switch.
  - `../ADRs/0006-curation-class-split-with-fence-ci-held-out-floor.md` — the held-out floor of 5 reinforces caution at small N.
- **Source design:** `../final-design.md §Departures from all three inputs #2`, `§Open Q #5` (deferred Wilson switch trigger).
- **Standard reference:** Efron, *An Introduction to the Bootstrap* (1993), §14 — BCa (bias-corrected and accelerated). The acceleration constant via jackknife in §14.3 is the implementation pattern.

## Goal

Implement `compute_lower_bound_95(per_case_scores: Sequence[float], *, run_id: str, n_resamples: int = 1000) -> float` that returns a deterministic, seeded BCa-bootstrap 95% one-sided lower bound on the mean of `per_case_scores`, and wire it into S3-02's aggregator.

## Acceptance criteria

- [ ] `src/codegenie/eval/bootstrap.py` exports `compute_lower_bound_95(scores, *, run_id, n_resamples=1000) -> float`.
- [ ] Seed derivation: `seed = int(run_id[:8], 16)` is the **only** source of randomness; the bootstrap uses `numpy.random.default_rng(seed)` (or `random.Random(seed)` if numpy is rejected — pick one explicitly in the implementation and document it).
- [ ] **Byte-identical determinism**: two calls with identical inputs (same `run_id`, same per-case score sequence) produce byte-identical `lower_bound_95` when serialized via `float.hex()`. A test asserts this across 100 reruns.
- [ ] **Cross-Python-version determinism**: byte-identical across Python 3.11 and 3.12 (asserted by a snapshot test that pins the bound to a literal hex for a known input).
- [ ] **Hypothesis property test** (one-tailed lower-bound sanity): for `N ≥ 5` and any sequence in `[0, 1]^N` with `stddev > 0`, the bound satisfies `mean - 2*stddev ≤ lower_bound_95 ≤ mean`. Use `hypothesis.strategies.lists(floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False), min_size=5, max_size=50)`.
- [ ] **Mutation property**: the bound is *non-decreasing* under uniform score shifts: `compute_lower_bound_95([s+δ for s in scores], ...) ≥ compute_lower_bound_95(scores, ...) - 1e-9` for any small `δ > 0` (clamped to `[0,1]`).
- [ ] Degenerate case `stddev == 0` (all scores identical) → `lower_bound_95 == mean` (bypass the bootstrap; no resampling).
- [ ] Edge case `N < 5` → `lower_bound_95 == 0.0` with a `WARNING` log including `n_cases`, `run_id`, and a pointer to ADR-0002.
- [ ] `n_resamples = 1000` per the literature default; expose as a kwarg for property-test speed but the runner always passes 1000.
- [ ] Wire into S3-02's aggregator: replaces the `lower_bound_95=0.0` placeholder; a regression test runs `Runner().execute(...)` and asserts the bound is `> 0.0` on a non-degenerate stub bench.
- [ ] `mypy --strict`, `ruff format --check`, `ruff check` clean.
- [ ] All red tests in §TDD plan exist, were committed at the red marker, and are now green.

## Implementation outline

1. New module `src/codegenie/eval/bootstrap.py`:
   ```python
   def compute_lower_bound_95(
       scores: Sequence[float], *, run_id: str, n_resamples: int = 1000
   ) -> float:
       if len(scores) < 5:
           structlog.get_logger().warning(
               "bootstrap_n_too_small", n=len(scores), run_id=run_id, see_adr="ADR-0002",
           )
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
       z0 = _bias_correction(arr, boot_means)
       a = _acceleration(arr)
       alpha_lower = _bca_alpha_lower(z0, a, 0.025)
       return float(np.percentile(boot_means, alpha_lower * 100))
   ```
2. `_bias_correction(arr, boot_means)`: `z0 = norm.ppf(mean(boot_means < arr.mean()))` (use `scipy.stats.norm.ppf` if scipy is available; else Acklam's algorithm via a stdlib implementation).
3. `_acceleration(arr)`: jackknife-based acceleration constant per Efron §14.3:
   ```python
   jackknife_means = np.array([arr[np.arange(len(arr)) != i].mean() for i in range(len(arr))])
   diffs = jackknife_means.mean() - jackknife_means
   return (diffs**3).sum() / (6.0 * (diffs**2).sum() ** 1.5)
   ```
4. `_bca_alpha_lower(z0, a, alpha)`: `norm.cdf(z0 + (z0 + norm.ppf(alpha)) / (1 - a*(z0 + norm.ppf(alpha))))`.
5. Call from S3-02's aggregator: after sorting `per_case` by `case_id`, compute `lower_bound_95 = compute_lower_bound_95([s.score for _, s in per_case], run_id=plan.run_id)` and set on the report.

## TDD plan — red / green / refactor

### Red — write failing tests first

`tests/unit/test_bootstrap.py`:

```python
import numpy as np
import pytest
from hypothesis import given, strategies as st, settings
from codegenie.eval.bootstrap import compute_lower_bound_95


def test_byte_identical_lower_bound_across_reruns():
    """Determinism is load-bearing: cassette reruns must produce the same chain."""
    scores = [0.6, 0.7, 0.8, 0.9, 0.55, 0.65, 0.75, 0.85, 0.5, 0.95]
    run_id = "abc1234500000000"
    runs = {compute_lower_bound_95(scores, run_id=run_id).hex() for _ in range(100)}
    assert len(runs) == 1, runs


def test_snapshot_bound_for_known_input():
    """Cross-Python-version stability: a pinned bound for a pinned input."""
    scores = [0.5, 0.6, 0.7, 0.8, 0.9, 0.55, 0.65, 0.75, 0.85, 0.95]
    bound = compute_lower_bound_95(scores, run_id="deadbeef00000000")
    # Pinned value — regenerated by scripts/regen_bootstrap_snapshot.py if intentional.
    assert bound.hex() == "0x1.5cc4..."  # PLACEHOLDER: real value filled in at green step


def test_degenerate_stddev_zero_returns_mean():
    scores = [0.7] * 10
    assert compute_lower_bound_95(scores, run_id="0" * 16) == 0.7


def test_small_n_returns_zero_and_warns(caplog):
    scores = [0.5, 0.6, 0.7, 0.8]  # N=4
    bound = compute_lower_bound_95(scores, run_id="0" * 16)
    assert bound == 0.0
    assert any("bootstrap_n_too_small" in r.message for r in caplog.records)


@given(scores=st.lists(
    st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    min_size=5, max_size=50,
))
@settings(max_examples=200, deadline=None)
def test_bca_bound_within_mean_minus_two_stddev_window(scores):
    """One-tailed 95% lower-bound sanity property (ADR-0002)."""
    arr = np.asarray(scores)
    if arr.std(ddof=1) == 0.0:
        return
    lb = compute_lower_bound_95(list(scores), run_id="deadbeef00000000")
    assert arr.mean() - 2 * arr.std(ddof=1) <= lb <= arr.mean() + 1e-9


@given(scores=st.lists(
    st.floats(min_value=0.0, max_value=0.9, allow_nan=False),
    min_size=5, max_size=20,
))
@settings(max_examples=50, deadline=None)
def test_uniform_score_shift_is_non_decreasing(scores):
    """If every score goes up by δ, the bound cannot go down."""
    bound_a = compute_lower_bound_95(scores, run_id="cafebabe00000000")
    shifted = [s + 0.05 for s in scores]
    bound_b = compute_lower_bound_95(shifted, run_id="cafebabe00000000")
    assert bound_b >= bound_a - 1e-9


@pytest.mark.asyncio
async def test_bound_lands_on_report(stub_bench):
    """Regression: aggregator wires the real bound (not the 0.0 placeholder)."""
    from codegenie.eval.runner import Runner
    plan = make_plan_with_varied_scores(stub_bench)
    report = await Runner().execute(plan, system_under_test=stub_sut, rubric_runner=stub_rubric)
    assert 0.0 < report.lower_bound_95 < report.mean_score
```

Run all seven; confirm failures. Commit as the red marker (note: the snapshot hex is filled in at the green step, not invented at red).

### Green — make them pass

Implement `compute_lower_bound_95` with the simplest correct BCa: bias correction + jackknife acceleration. Vectorize the resample loop with `rng.choice(arr, size=arr.size, replace=True)` if numpy is available. Wire into the aggregator's report build.

### Refactor — clean up

- Pull `_bias_correction`, `_acceleration`, `_bca_alpha_lower` into private helpers with their own unit tests verified against a published worked example from Efron §14.3.
- Add a `pytest -m slow` marker on the 100-rerun byte-identical test so it can be skipped locally; CI runs it.
- Module docstring states the seed-derivation rule and cites ADR-0002 verbatim: "changing it would invalidate the audit chain's reproducibility claim."
- Cross-reference comment in `runner.py` aggregator: `# lower_bound_95 is the ONLY gate signal (ADR-0002); mean and stddev are reported for human review only.`
- `scripts/regen_bootstrap_snapshot.py` — operator tool that recomputes the snapshot hex when the BCa implementation is intentionally changed (rare; gated by an ADR amendment).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/bootstrap.py` | New module — BCa implementation + helpers |
| `src/codegenie/eval/runner.py` | Wire the call into the aggregator; remove the placeholder |
| `tests/unit/test_bootstrap.py` | Determinism + snapshot + two Hypothesis properties + degenerate + small-N + aggregator regression |
| `pyproject.toml` | If numpy/scipy are not yet deps, add them (or implement `norm.ppf` locally with Acklam's algorithm) |
| `scripts/regen_bootstrap_snapshot.py` | Operator tool for snapshot regeneration |

## Out of scope

- Switching to Wilson interval (ADR-0002's revisit trigger — future ADR amendment if `score ∈ {0.0, 1.0}` rate > 80%).
- Two-sided confidence intervals (only the lower bound matters for the gate).
- Cross-task-class bootstrap stitching (Phase 16).
- Per-breakdown-key sub-bootstraps (would surface in Phase 13 dashboards; not needed for the gate).

## Notes for the implementer

- **The seed derivation rule is structural state.** ADR-0002 calls it out by name: "changing it would invalidate the audit chain's reproducibility claim." If you find a reason to change it, escalate via an ADR amendment, not a code change.
- BCa over the percentile method is the right choice because `BenchScore.score ∈ [0, 1]` is asymmetric near the boundaries; the bias correction matters at `N ≈ 10`.
- The Hypothesis bound `mean - 2*stddev <= lower_bound_95 <= mean` is a *sanity* property, not the canonical BCa property. It catches gross implementation bugs (e.g., returning the upper bound by accident, or returning `mean + stddev`). It does not certify BCa correctness — that's what the Efron §14.3 worked example is for in the unit test of `_bias_correction` and `_acceleration`.
- The monotone-shift property is the second guardrail: if every score increases, the lower bound cannot decrease. A bug that, e.g., swapped sign on `z0` would fail this within ~10 Hypothesis examples.
- The numpy dependency is small and the BCa math is materially harder to write correctly without it. If the project rejects numpy, implement `_acceleration` with stdlib `statistics` + a hand-rolled `norm.ppf` (Acklam's algorithm); leave a TODO and a citation. Either choice must be byte-identical across Python versions — pin the choice in a code comment.
- The degenerate `stddev == 0` path is required — without it, the jackknife denominator is zero and the bootstrap explodes (NaN).
- The `N < 5` floor is conservative: BCa is known to be unreliable below ~5 samples. The promotion gate's `min_cases_for_promotion[bronze] = 10` makes the practical gate stricter than this safeguard; the warning exists for Phase 6 (the seed migration corpus at N=3) and for malformed runs that emit < 5 cases.
- **Snapshot test is intentional**: it pins the BCa output for known inputs across Python minor versions and numpy versions. If the snapshot fails on a numpy upgrade, that's a signal — not silent drift. The regen script makes the snapshot legible.
- Vectorize the resample loop if numpy: `rng.choice(arr, size=(n_resamples, arr.size), replace=True).mean(axis=1)` is one statement and ~50× faster than the per-iteration loop. Keep the slow loop in the docstring as the readable spec.
