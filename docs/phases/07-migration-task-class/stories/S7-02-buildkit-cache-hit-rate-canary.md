# Story S7-02 — Buildkit cache hit rate canary

**Step:** Step 7 — Performance canaries + fence-CI extension
**Status:** Ready
**Effort:** M
**Depends on:** S7-01
**ADRs honored:** ADR-P7-014 (baseline-relative + `--update-perf-baseline` pattern), ADR-P7-009 (snapshot-canary discipline — runner-class metadata)

## Context

Goal G10 commits Phase 7 to ≥ 85 % pulled-layer + ≥ 60 % derived-layer BuildKit cache hits after the 3-fixture warm-up run. Without this canary, the warm-throughput goals (G6 warm ≥ 24/hr, G7 mixed ≥ 10/hr) silently degrade as later phases poison or bypass the cache. This story reads BuildKit's native cache-hit metadata via `docker buildx build --metadata-file` (or equivalent), aggregates over the warm-up fixture run, and asserts the two rates against the pinned baseline. The canary lives next to the wall-clock canary from S7-01 and reuses its `--update-perf-baseline` flag and runner-class discipline — different metric, same discipline.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals G10` — ≥ 85 % pulled-layer + ≥ 60 % derived-layer after first 3-fixture warm-up run.
  - `../phase-arch-design.md §Testing strategy ›Performance regression tests` bullet 2 — names the canary file (`tests/perf/test_buildkit_cache_hit_rate.py`) and the threshold.
  - `../phase-arch-design.md §Component 9 — Pre-rendered base_catalog.json hot view` — describes the `tests/fixtures/repos/*-distroless/` fixtures (Node Express, static-Go, alpine-to-glibc) that constitute the warm-up portfolio.
  - `../phase-arch-design.md §Edge cases #4` — multi-arch cache key requires `--platform=linux/amd64`; this canary asserts cache keys carry the platform.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0014-regression-suite-wall-clock-canary.md` — ADR-P7-014 — the baseline-file + `--update-perf-baseline` flag + runner-class metadata pattern this story reuses.
  - `../ADRs/0009-contract-surface-snapshot-canary.md` — ADR-P7-009 — runner-class metadata convention.
- **Source design:**
  - `../final-design.md §Goals#10` (and the cache-hit-rate target).
  - `../critique.md §perf.assumption.2` (cache key includes `--platform=linux/amd64` to prevent silent cross-arch reuse).
- **Existing code:**
  - `src/codegenie/tools/buildkit.py` (S2-02) — the wrapper that owns `docker buildx build`; this canary calls it through the existing public surface, never via raw subprocess.
  - `tests/fixtures/repos/express-distroless/`, `static-go-distroless/`, `alpine-to-glibc-distroless/` — the 3-fixture warm-up portfolio.

## Goal

`pytest tests/perf/test_buildkit_cache_hit_rate.py` runs the 3-fixture warm-up sequence (cold-then-warm) on the reference runner and fails when the second-and-after-run pulled-layer hit rate < 85 % or the derived-layer hit rate < 60 %.

## Acceptance criteria

- [ ] `tests/perf/test_buildkit_cache_hit_rate.py` exists with a fixture-portfolio fixture that builds each of `{express-distroless, static-go-distroless, alpine-to-glibc-distroless}` once cold (records baseline), then once warm (records hit rates).
- [ ] Pulled-layer hit rate and derived-layer hit rate are computed from BuildKit metadata (`docker buildx build --metadata-file <path>` plus `imagetools inspect` cache references, or `buildctl --debug=true` output — match whatever `src/codegenie/tools/buildkit.py` already exposes). No screen-scraping of `docker buildx build` stderr; if the wrapper doesn't expose hit counts, extend the wrapper additively (per ADR-P7-001..006 only if the surface is the wrapper; otherwise add a new helper module).
- [ ] Pinned thresholds enforced: pulled-layer hit rate ≥ 85 %; derived-layer hit rate ≥ 60 %. Both checks against `tests/perf/baseline.json` *and* against the absolute G10 floor — whichever is stricter fires.
- [ ] Cache key includes `--platform=linux/amd64` (asserted by inspecting the wrapper's invocation log; closes critic perf.assumption.2 from `phase-arch-design.md §Edge cases #4`).
- [ ] The canary uses S7-01's `--update-perf-baseline` flag for deliberate bumps; an attempted bump that would change `runner_class` is refused without `--allow-runner-class-change` (same discipline as S7-01).
- [ ] The TDD plan's red tests exist, were committed, and are green.
- [ ] `pytest tests/perf/test_buildkit_cache_hit_rate.py` is in CI's merge-gate lane (added alongside S7-01's entry).
- [ ] `ruff check`, `ruff format --check`, and `mypy --strict` clean on touched files.

## Implementation outline

1. Inspect `src/codegenie/tools/buildkit.py` (landed in S2-02). Identify the public surface for cache-hit reporting. If the wrapper already returns a `BuildResult` Pydantic model with per-layer cache status, use it. If not, extend `BuildResult` additively (`pulled_layer_hits: int`, `pulled_layer_total: int`, `derived_layer_hits: int`, `derived_layer_total: int`) and update the snapshot canary (S1-07) per the snapshot-regen discipline — link ADR-P7-014 in the PR.
2. Write `tests/perf/test_buildkit_cache_hit_rate.py` as one parametrized test over the 3 fixtures, sharing a `module`-scoped fixture that performs the cold-then-warm sequence in one process so the BuildKit local cache is hot.
3. The cold pass populates the cache; the warm pass measures hit rates. Aggregate hit rates across the 3 fixtures (sum hits / sum totals, *not* mean of per-fixture rates — avoids small-denominator skew on the smallest fixture).
4. Compare against `tests/perf/baseline.json` keys `buildkit_pulled_layer_hit_rate`, `buildkit_derived_layer_hit_rate`. Fail with a diff-rendered message naming the worst fixture (per-fixture rates included in the message for actionable feedback, even though the assertion is on the aggregate).
5. Wire into CI merge-gate; document the BuildKit cache directory path (`.codegenie/cache/buildkit/`) that the runner must persist across CI steps (or accept the cold-run cost on every CI invocation — measure once and document the choice).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file: `tests/perf/test_buildkit_cache_hit_rate.py`

```python
# tests/perf/test_buildkit_cache_hit_rate.py
def test_warm_pulled_layer_hit_rate_at_least_85pct(buildkit_warmup):
    # arrange: warmup fixture has run cold-then-warm
    aggregate = buildkit_warmup.aggregate
    # act / assert
    assert aggregate.pulled_layer_hit_rate >= 0.85, (
        f"pulled-layer cache hit rate {aggregate.pulled_layer_hit_rate:.3f} < 0.85; "
        f"per-fixture: {aggregate.per_fixture}"
    )

def test_warm_derived_layer_hit_rate_at_least_60pct(buildkit_warmup):
    aggregate = buildkit_warmup.aggregate
    assert aggregate.derived_layer_hit_rate >= 0.60, (
        f"derived-layer cache hit rate {aggregate.derived_layer_hit_rate:.3f} < 0.60; "
        f"per-fixture: {aggregate.per_fixture}"
    )

def test_warm_run_uses_platform_linux_amd64(buildkit_warmup):
    # arrange: warmup fixture captures the invocation log
    invocations = buildkit_warmup.invocations
    # assert: every warm-pass invocation passed --platform=linux/amd64 (closes critic perf.assumption.2)
    for inv in invocations.warm:
        assert "--platform=linux/amd64" in inv.argv, f"missing --platform in {inv.argv}"
```

The fixture `buildkit_warmup` doesn't exist yet — `pytest` errors out. Commit the failing test.

A unit-level red test on the aggregation logic (so we can iterate without the slow E2E):

```python
# tests/perf/test_buildkit_cache_aggregation.py
def test_aggregate_uses_sum_not_mean():
    # arrange: three fixture results, one tiny denominator that would bias a mean
    per_fixture = [
        FixtureBuildResult(name="big", pulled_hits=85, pulled_total=100, derived_hits=60, derived_total=100),
        FixtureBuildResult(name="big2", pulled_hits=85, pulled_total=100, derived_hits=60, derived_total=100),
        FixtureBuildResult(name="tiny", pulled_hits=0, pulled_total=1, derived_hits=0, derived_total=1),  # 0 % rate
    ]
    # act
    agg = aggregate_hit_rates(per_fixture)
    # assert: sum-of-hits / sum-of-total = 170/201 = 0.8458... not (0.85 + 0.85 + 0)/3 = 0.5667
    assert agg.pulled_layer_hit_rate == pytest.approx(170 / 201)
```

### Green — make it pass

- Add `tests/perf/_buildkit_cache.py` with `FixtureBuildResult`, `AggregateResult`, `aggregate_hit_rates()` pure helpers.
- Add the `buildkit_warmup` module-scoped fixture in `tests/perf/conftest.py` that drives `BuildkitWrapper` over the 3-fixture portfolio (cold pass then warm pass) and captures invocation log + per-fixture metadata.
- If `BuildkitWrapper.BuildResult` is missing the cache-hit fields, extend it additively in the same PR, regen `tools/contract-surface.snapshot.json`, link ADR-P7-014 (the cache-hit canary's owning ADR) — `snapshot_regen_audit.py` from S1-08 will enforce.

### Refactor — clean up

- Type hints + `Pydantic`-immutable models for `FixtureBuildResult` and `AggregateResult` (`model_config = ConfigDict(frozen=True)`).
- Docstring on `aggregate_hit_rates` explicitly documenting the sum-vs-mean choice and the rationale ("tiny-fixture bias on mean produces dishonest aggregates").
- Edge case from `phase-arch-design.md §Edge cases #4` — assert `--platform=linux/amd64` on every warm-pass invocation; in `_buildkit_cache.py` add a tiny helper `assert_platform_pinned(invocations)` and call it from a sibling test.
- Edge case from `§Edge cases #16` (cgr.dev cold pull on fresh CI runner) — the cold pass must complete before the warm pass times anything; the fixture's cold pass is *not* the measurement, it is setup.
- Honor ADR-P7-014 "Consequences": this canary is *narrower scope* than the wall-clock canary; do not fold it in.

## Files to touch

| Path | Why |
|---|---|
| `tests/perf/test_buildkit_cache_hit_rate.py` | New file — the canary (G10). |
| `tests/perf/test_buildkit_cache_aggregation.py` | New file — unit tests for aggregation logic. |
| `tests/perf/_buildkit_cache.py` | New file — pure-function helpers + Pydantic result models. |
| `tests/perf/conftest.py` | Add `buildkit_warmup` module-scoped fixture. |
| `tests/perf/baseline.json` | Add `buildkit_pulled_layer_hit_rate`, `buildkit_derived_layer_hit_rate` keys (measured on reference runner). |
| `src/codegenie/tools/buildkit.py` | Possible additive extension of `BuildResult` if cache-hit fields are missing (regen snapshot in same PR). |
| `tools/contract-surface.snapshot.json` | Regen if `BuildResult` is extended; link ADR-P7-014 in PR body. |
| `.github/workflows/ci.yml` | Add canary to merge-gate lane (next to S7-01). |

## Out of scope

- **Cold throughput / time-to-PR.** Owned by S7-03.
- **`dockerfile-parse` round-trip p95.** Owned by S7-04.
- **Per-worker memory measurement.** Owned by S7-06.
- **Cross-host distributed-cache poisoning adversarial.** Phase 9 Temporal idempotency closes that case (per `phase-arch-design.md §Adversarial tests ›Deferred`).
- **`--cache-to` shared registry cache.** Phase 7 uses BuildKit local cache only (`.codegenie/cache/buildkit/`); registry-cache export is a Phase 8 question.

## Notes for the implementer

- **Sum-of-hits / sum-of-total — not mean of rates.** Mean over per-fixture rates is biased when fixtures have wildly different layer counts (one tiny `static-go` image vs a large Node image). The TDD plan's unit test pins this; do not "simplify" to a mean.
- **The cold pass is setup, not measurement.** Do not assert hit-rate on the cold pass; on a fresh runner the cold pass has *zero* hits by construction. The fixture must clearly separate cold (populate) from warm (measure).
- **`--platform=linux/amd64` is not optional.** Critic perf.assumption.2 specifically called out that omitting `--platform` allows silent cross-arch cache reuse — a correctness, not perf, bug. The canary asserts it as a side-quest.
- **Honor Global Rule 8 (Read before you write).** `src/codegenie/tools/buildkit.py` may already expose cache-hit metadata via a Pydantic model. Read the file first; if so, do *not* add a parallel parser. If not, the additive extension to `BuildResult` is the right move — but it touches the snapshot canary, so the PR must link ADR-P7-014 per `tools/snapshot_regen_audit.py` (S1-08).
- **Honor Global Rule 12 (Fail loud).** If the cache-hit metadata path is missing (`docker buildx --metadata-file` not present on the runner), raise `BuildkitMetadataUnavailable` and explicitly fail the canary — never silently fall through with a 0 % hit rate assumed.
- **The 3 fixtures are the *warm-up portfolio*, not the *test portfolio*.** Adding a 4th fixture changes the aggregate — bump the baseline via `--update-perf-baseline` in the same PR that adds the fixture, link the relevant ADR. Per ADR-P7-014, every bump is reviewable.
- **Don't measure on a developer laptop and commit.** The baseline is runner-class-locked; the `runner_class` field must be `linux-dind-reference-x86_64` (or whatever Phase 0 names the canonical CI runner — re-use exactly that string, do not invent a new one).
