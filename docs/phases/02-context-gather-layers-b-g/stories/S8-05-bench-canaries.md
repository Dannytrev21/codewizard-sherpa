# Story S8-05 — Bench canaries: warm-path, B2 budget + 25%-regression gate, SCIP, cold e2e

**Step:** Step 8 — Adversarial corpus + integration end-to-end + seeded-staleness + goldens + CI gates + Phase 3 handoff
**Status:** Ready
**Effort:** M
**Depends on:** S8-02
**ADRs honored:** ADR-0011 (B2 advisory 200 ms budget + 25%-regression gate is load-bearing per Phase 2 Goals #11), ADR-0001 (frozen-snapshot read path is what B2 benches against — must not allocate per-read), ADR-0013 (`SCIPIndexProbe` per-repo binary lifecycle is the SCIP bench's target)

## Context

Phase 2 ships four bench canaries. Three are **advisory** (record-and-trend; not PR-blocking); one is **gating** (PR-blocking on regression). The gating bench is `test_index_health_budget.py` — B2's wall-clock budget is **200 ms p99** across 1000 iterations on a populated peer-output snapshot, with a **25%-regression gate** on PRs touching `src/codegenie/probes/index_health.py` or the coordinator dispatch path. This is the only mandatory bench in Phase 2 (`phase-arch-design.md §"Goals"` #11; `High-level-impl.md §"Step 8"` Done criterion #7).

The other three benches:

- `tests/bench/test_warm_path_phase2.py` — second-run all-cache-hit ratio ≤ 0.05 of first-run wall-clock. Advisory. Catches per-file-cache regressions.
- `tests/bench/test_scip_full_reindex.py` — SCIP full re-index ≤ 30 s p95 on a 1k-file fixture. Advisory. Catches `tools.scip_typescript` argument-explosion regressions.
- `tests/bench/test_phase2_cold_e2e.py` — cold end-to-end gather ≤ 150 s p95 on the integration fixture. Advisory. Catches cumulative regression across the pipeline.

The 25%-regression gate is the trickiest piece. It needs a **baseline file** committed to the repo (median across 1000 iterations on the CI runner), and a **comparator** that reads the baseline and the current bench output and fails if `current_p99 > baseline_p99 * 1.25`. The baseline is refreshed deliberately via a separate PR (analogous to a `--update-goldens` workflow); CI does not auto-bump.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Goals"` #11 — "Wall-clock targets advisory; B2 200 ms budget + 25%-regression gate."
  - `../phase-arch-design.md §"Testing strategy" → "Bench canaries"` — the four-bench inventory.
  - `../phase-arch-design.md §"Component design" #5 IndexHealthProbe` — the per-domain rollup formula B2 evaluates; the budget is on this whole evaluation.
- **Phase ADRs:**
  - `../ADRs/0011-index-health-advisory-budget-and-strict-flag.md` — 200 ms budget rationale; `index_health.budget_exceeded` advisory event; 25%-regression gate is the CI hammer.
  - `../ADRs/0001-peer-outputs-binding.md` — B2 reads a frozen `MappingProxyType` snapshot; the bench must allocate the snapshot once before the timed loop, not per-iteration (otherwise the bench measures snapshot construction, not B2 evaluation).
  - `../ADRs/0013-scip-node-modules-conditional-mount.md` — the SCIP bench fixture has `node_modules` either present or absent depending on what we are exercising; pick one and document.
- **Source design:**
  - `../final-design.md §"Performance budgets"` — the 200 ms B2 budget + p99 across 1000 iterations.
- **Implementation plan:**
  - `../High-level-impl.md §"Step 8"` — bench inventory; B2 25%-regression on PRs touching `index_health.py` or coordinator.
  - `../High-level-impl.md §"Implementation-level risks"` #10 — coverage ratchet at 90/80 (this story does not regress it).
- **Existing code:**
  - `src/codegenie/probes/index_health.py` (S3-01) — the bench's target.
  - `src/codegenie/probes/scip_index.py` (S4-01) — the SCIP bench's target.
  - `src/codegenie/coordinator.py` — the dispatch path the warm-path bench exercises.
  - `tests/bench/` (Phase 1) — the directory pattern; Phase 1 likely shipped no benches, so create.
- **Style reference:** `../../01-context-gather-layer-a-node/stories/S6-02-coverage-ratchet-bench.md` (Phase 1 bench/coverage story — most direct template).

## Goal

Land four bench tests under `tests/bench/` — one PR-gating (B2 budget + 25% regression) and three advisory — plus the baseline file and comparator script so the gating bench is genuinely enforceable on PRs touching B2 or the coordinator.

## Acceptance criteria

- [ ] `tests/bench/test_index_health_budget.py` exists; runs `IndexHealthProbe.run(snapshot, ctx, peer_outputs)` **1000 times** on a populated synthetic peer-output snapshot; records per-iteration wall-clock; asserts (i) **p99 ≤ 200 ms** absolute; (ii) **p99 ≤ baseline_p99 × 1.25** (the 25%-regression gate). The snapshot is constructed once before the timed loop.
- [ ] `tests/bench/baselines/index_health_p99_ms.json` is committed; format: `{"p99_ms": <number>, "captured_on_commit": "<sha>", "captured_at": "<utc>", "ci_runner": "<runner-id>", "snapshot_fixture": "<path>"}`. The file is the bumpable baseline.
- [ ] `scripts/compare_bench_baseline.py` is committed; reads the bench output (pytest-benchmark JSON or a simple JSON written by the bench test) and the baseline; exits 0 if `current_p99 ≤ baseline_p99 × 1.25`, else exits 1 with a clear message naming the regression magnitude. The script runs in the CI `bench_gate` job (wired in S8-06).
- [ ] `tests/bench/test_warm_path_phase2.py` exists; runs gather on `tests/fixtures/node_typescript_with_b_through_g/` twice; asserts `t2 / t1 ≤ 0.05`. **Advisory** — failure prints a warning but does not fail the test (use `pytest.warns` or a structured log + `assert True`, then a separate CI-level threshold check). The advisory threshold is documented inline.
- [ ] `tests/bench/test_scip_full_reindex.py` exists; on a 1k-TS-file fixture (`tests/fixtures/scip_1k_file/`); runs `SCIPIndexProbe.run` cold (no `.codegenie/index/scip-index.scip`); records wall-clock; asserts **p95 ≤ 30 s** across 5 iterations. **Advisory**.
- [ ] `tests/bench/test_phase2_cold_e2e.py` exists; runs gather on `tests/fixtures/node_typescript_with_b_through_g/` cold; records wall-clock; asserts **p95 ≤ 150 s** across 3 iterations. **Advisory**.
- [ ] The bench tests run on **Python 3.11 and 3.12** in CI; the 25%-regression baseline is captured on a known CI runner type and the baseline file records the runner id so cross-runner drift is visible.
- [ ] `tests/bench/README.md` documents (a) which bench is gating vs advisory, (b) how to refresh the baseline (`pytest tests/bench/test_index_health_budget.py --update-baseline` or an equivalent script), (c) which file paths trigger the gating bench on PRs (the path-filter wired in S8-06: `src/codegenie/probes/index_health.py` and `src/codegenie/coordinator.py`).
- [ ] No new top-level dep introduced. If `pytest-benchmark` is not already in Phase 1's dev deps, prefer a hand-rolled timing harness (`time.perf_counter` + `statistics.quantiles`) over adding the dep.

## Implementation outline

1. **Build the synthetic peer-output snapshot for the B2 bench.** The snapshot must populate every domain B2 evaluates (`scip`, `sbom`, `cve`, `semgrep`, `gitleaks`, `runtime_trace`); each peer-output slice has the canonical shape S3-01's sub-schema expects. The snapshot is built once at module-import time (or via a session-scoped fixture) so the timed loop measures B2 evaluation only.
2. **Implement the B2 bench:**
   - 1000 iterations; warm up with 10 untimed iterations to stabilize the JIT/cache.
   - Record per-iteration wall-clock in a list; compute p99 via `statistics.quantiles(data, n=100)[98]`.
   - Read `tests/bench/baselines/index_health_p99_ms.json`; assert `current_p99_ms <= baseline_p99_ms * 1.25`.
   - Also assert `current_p99_ms <= 200` (absolute budget).
   - Write the current bench result to `tests/bench/results/index_health_<utc>.json` for trend tracking (gitignored).
3. **Implement the comparator script:**
   - 30-LOC pure stdlib: read baseline + current; compute ratio; print human-readable message; exit 0/1.
4. **Implement the three advisory benches** with the same timing harness. The warm-path bench uses the integration fixture from S8-02. The SCIP bench needs a 1k-file fixture — either generate at test time (a `tmp_path` factory that produces 1k empty TS files) or commit a `scip_1k_file/` fixture (preferred: 1k small TS files at ~50 KB total compressed via a single-line-each pattern).
5. **`tests/bench/baselines/index_health_p99_ms.json`** — capture the baseline locally by running the bench on a clean CI-like machine (or document that the baseline was captured on the GitHub Actions `ubuntu-22.04` runner); commit the file.
6. **`tests/bench/README.md`** — document the recipe.

## TDD plan — red / green / refactor

### Red — write the failing test first

Start with the B2 budget bench because it is the only gating one.

Path: `tests/bench/test_index_health_budget.py`

```python
"""ADR-0011 | Goal #11: B2 evaluation p99 ≤ 200 ms; PR regression gate at 1.25x baseline."""
import json
import statistics
import time
from pathlib import Path

import pytest

from codegenie.probes.index_health import IndexHealthProbe

BASELINE_PATH = Path("tests/bench/baselines/index_health_p99_ms.json")
SNAPSHOT_FIXTURE = Path("tests/fixtures/index_health_synthetic_snapshot.json")
ITERATIONS = 1000
WARMUP = 10


@pytest.fixture(scope="module")
def populated_snapshot():
    return json.loads(SNAPSHOT_FIXTURE.read_text())


def test_index_health_p99_within_budget_and_baseline(populated_snapshot, build_probe_ctx):
    probe = IndexHealthProbe()
    ctx = build_probe_ctx()

    for _ in range(WARMUP):
        probe.run(snapshot=populated_snapshot, ctx=ctx, peer_outputs=populated_snapshot)

    times_ms = []
    for _ in range(ITERATIONS):
        t0 = time.perf_counter()
        probe.run(snapshot=populated_snapshot, ctx=ctx, peer_outputs=populated_snapshot)
        times_ms.append((time.perf_counter() - t0) * 1000)

    p99 = statistics.quantiles(times_ms, n=100)[98]
    assert p99 <= 200.0, f"absolute budget exceeded: p99={p99:.1f}ms > 200ms"

    baseline = json.loads(BASELINE_PATH.read_text())["p99_ms"]
    assert p99 <= baseline * 1.25, (
        f"25% regression gate: p99={p99:.1f}ms > baseline_p99={baseline:.1f}ms × 1.25"
    )
```

Path: `tests/bench/test_warm_path_phase2.py`

```python
"""Phase 2 warm-path: second-run wall-clock ratio ≤ 0.05 of first-run. Advisory."""
import time
from pathlib import Path

import pytest


def test_warm_path_ratio_advisory(tmp_path, run_gather):
    fixture = Path("tests/fixtures/node_typescript_with_b_through_g").resolve()

    t0 = time.perf_counter()
    first = run_gather(fixture, cache_dir=tmp_path / "cache")
    t1 = time.perf_counter() - t0
    assert first.exit_code == 0

    t0 = time.perf_counter()
    second = run_gather(fixture, cache_dir=tmp_path / "cache")
    t2 = time.perf_counter() - t0
    assert second.exit_code == 0

    ratio = t2 / t1
    if ratio > 0.05:
        pytest.warns(UserWarning, match=f"warm-path ratio {ratio:.3f} exceeds 0.05 advisory")
```

### Green — make it pass

For the B2 bench, the most likely first red is the **absolute** 200 ms budget — if B2's snapshot read does anything expensive per-call (recomputing the BLAKE3 of the snapshot, allocating new dataclasses, calling `git rev-list --count` synchronously per probe iteration instead of caching), p99 will blow past 200 ms. Fix in `IndexHealthProbe`'s implementation: cache the per-snapshot derived values, ensure no subprocess invocation in the read path, ensure the frozen `MappingProxyType` is read directly without copying.

The baseline file's initial value should be captured **after** the absolute-budget assertion passes — running the bench on a clean machine, taking the p99, rounding up to the next sensible value (e.g., if p99 is 87 ms, baseline is 100 ms — leaves slack for normal jitter).

For the advisory benches, green is mostly about the timing harness correctness. The warm-path bench's `ratio > 0.05` check is advisory; using `pytest.warns` makes the failure surface in CI logs without failing the test.

### Refactor — clean up

After green:

- Run the B2 bench **10 times** locally; assert no flake. If the test occasionally exceeds the absolute budget, the iteration count (1000) is too low to stabilize p99 — bump to 2000 or 5000.
- Capture the baseline on a consistent CI runner type; document the runner in the baseline file. If running locally on a faster machine, the baseline may be over-tight for CI — capture on CI explicitly via a one-time PR.
- Verify the bench tests do not regress coverage by running locally with `--cov`.
- Confirm Python 3.11 and 3.12 produce comparable p99 (within 10%); if 3.12 is materially faster or slower, document.
- The `tests/bench/results/` directory should be in `.gitignore` (per-run artifacts).

## Files to touch

| Path | Why |
|---|---|
| `tests/bench/test_index_health_budget.py` | New — gating bench; 200 ms + 25%-regression. |
| `tests/bench/test_warm_path_phase2.py` | New — advisory warm-path ratio. |
| `tests/bench/test_scip_full_reindex.py` | New — advisory SCIP re-index. |
| `tests/bench/test_phase2_cold_e2e.py` | New — advisory cold e2e. |
| `tests/bench/baselines/index_health_p99_ms.json` | New — committed baseline. |
| `tests/bench/README.md` | New — gating-vs-advisory + baseline refresh recipe. |
| `tests/fixtures/index_health_synthetic_snapshot.json` | New — populated peer-output snapshot for the B2 bench. |
| `tests/fixtures/scip_1k_file/` | New — 1k small TS files (committed; ~5 MB on disk). |
| `scripts/compare_bench_baseline.py` | New — pure-stdlib comparator for CI. |
| `.gitignore` | Add `tests/bench/results/`. |

## Out of scope

- **CI workflow wiring of the path-filtered bench gate** — handled by **S8-06** (`bench_gate` job; path filter on `src/codegenie/probes/index_health.py` + `src/codegenie/coordinator.py`).
- **Bench baseline auto-bump** — explicit non-goal. Baselines refresh via a deliberate PR with a one-line message.
- **Coverage ratchet** — held at 90/80 from Phase 1; the per-module floors at 85/75 for the three heavy external-tool probes are declared in `pyproject.toml` and reported by the PR body. This story does not touch coverage.
- **Adding `pytest-benchmark`** — if Phase 1 didn't ship it, do not add. The hand-rolled timing harness is simpler and avoids the dep.
- **Improving B2's algorithm to make the bench faster** — out of scope for this story. If the absolute 200 ms budget fails today, surface as an S3-01 follow-up; fix in S3-01 before merging this story.

## Notes for the implementer

- **The 200 ms budget is the contract; the 25% regression gate is the operational hammer.** Both must pass. The baseline file is what makes the gate enforceable across PRs — without a committed baseline, the gate has no reference point. Do not skip the baseline.
- **Capture the baseline on CI, not locally.** Developer machines vary wildly; CI runner specs are fixed. Run the bench once on the target CI runner, take the p99, commit the baseline. The README documents the recipe for future contributors.
- **The synthetic peer-output snapshot is the bench's most critical fixture.** If it doesn't populate every domain B2 evaluates, the bench measures the wrong path (B2 short-circuits on missing domains). Verify by reading `IndexHealthProbe.run`'s body and confirming every domain is exercised by the fixture.
- **Warmup matters.** The first 10 iterations are untimed because Python's import-time caching, Pydantic schema compilation, and structlog binding-cache warmup add jitter. Do not skip the warmup.
- **`statistics.quantiles(data, n=100)[98]` is the p99.** Index 98 gives the 99th percentile (the n=100 partitioning yields 99 cutpoints; the 99th is at index 98 zero-based). Document inline so a future reader does not flip to `[99]` and silently start measuring max.
- **The path filter for the bench gate is in S8-06.** This story leaves the bench test ready to run; S8-06 wires the CI condition `if: contains(github.event.pull_request.changed_files, 'src/codegenie/probes/index_health.py') || contains(..., 'src/codegenie/coordinator.py')`.
- **The advisory benches are not silent — they emit warnings.** `pytest.warns` (or a structured log via the test's structlog binding) makes the regression visible in CI logs without failing. The team trends them over time; if a 2x regression lands on a "minor" PR, the trend surfaces.
- **The `scip_1k_file/` fixture is ~5 MB on disk.** This is the largest fixture in Phase 2 (after `nestjs/nest`'s pinned lockfile). Generate the 1k files as 1-line stubs (`export const x = 0;`) to keep the bytes-per-file minimal; the count is the bench's input, not the content.
