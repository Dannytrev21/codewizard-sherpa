# Story S9-01 — Per-node overhead canary + `baseline.json` bookkeeping

**Step:** Step 9 — Performance canary (G6) + SQLite throughput watchdog (G9) + ADR-P6-006 escalation hook
**Status:** Ready
**Effort:** S
**Depends on:** S5-01
**ADRs honored:** ADR-0001, ADR-0011 (context only — this story does not touch the checkpointer)

## Context
Phase 6 commits to **measured** performance, not asserted performance (`final-design.md §Goals row 6`, `phase-arch-design.md §G6`). This story lands the per-node LangGraph overhead canary: a synthetic 100-no-op-node graph invoked 1,000 times, with p50 and p95 wall-clock per node recorded to `tests/perf/baseline.json` on the *first* CI run after merge and compared against that baseline on every subsequent run. The 25% regression tolerance is intentionally loose (CI runners are noisy); the dial is in the baseline file, not the test code. The baseline-update procedure must be documented so dependency bumps (LangGraph, Pydantic, langgraph-checkpoint-sqlite) become a *deliberate* `git commit tests/perf/baseline.json` step, never a `// flaky-skip`. This story is the small, mechanical foundation that the throughput watchdog (S9-02) and concurrent test (S9-03) build on.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Goals — G6` (lines 24–26) — the canary's contract and tolerance.
  - `../phase-arch-design.md §Performance regression tests` (lines 1208–1212) — names the file and the > 25% rule.
  - `../phase-arch-design.md §Golden files` (line 1185) — `tests/perf/baseline.json` is committed source-of-truth.
  - `../phase-arch-design.md §Open Questions #6` (line 1358) — Renovate/Dependabot bumps must include a baseline-update PR; the implementer documents this in `tests/perf/README.md`.
  - `../phase-arch-design.md §Risk row` ("flaky failures on noisy CI runners") and `High-level-impl.md §Step 9 — Risks specific to this step` — never `// flaky-skip` the gate.
- **Phase ADRs:**
  - `../ADRs/0001-lazy-singleton-build-vuln-loop-factory.md` — `build_vuln_loop()` is the import target; the canary needs a *separate* trivial graph so it doesn't depend on the full vuln topology.
  - `../ADRs/0011-sqlite-throughput-watch-and-postgres-escalation.md` — sister gate; this story does **not** assert throughput, only per-node overhead.
- **High-level-impl:** `../High-level-impl.md §Step 9` (lines 242–266) — features delivered, done criteria, and the explicit Renovate-bump procedure note.
- **Source design:** `../final-design.md §Goals row 6` — committed baseline + 25% tolerance.
- **Existing code:**
  - `src/codegenie/graph/vuln_loop.py` — read `build_vuln_loop()` to understand how `StateGraph` is constructed; the canary builds its own throwaway graph, it does *not* invoke `build_vuln_loop()`.
  - `tests/perf/` — directory may not yet exist; check first.

## Goal
Ship `tests/perf/test_canary_overhead.py` such that on the first CI run after merge it writes p50 and p95 per-node overhead (μs) for a 100-no-op-node graph invoked 1,000 times to `tests/perf/baseline.json`, and on every subsequent run it compares measured p50/p95 against the baseline and fails only on a > 25% regression. Ship `tests/perf/README.md` documenting the baseline-update procedure.

## Acceptance criteria
- [ ] `tests/perf/test_canary_overhead.py` exists. It constructs an inline `StateGraph` with 100 no-op nodes wired linearly (`node_0 → node_1 → … → node_99 → END`), each node a `def(state: dict) -> dict: return state`, compiled with no checkpointer (in-memory `MemorySaver` is acceptable; the canary measures LangGraph overhead, *not* persistence).
- [ ] The test invokes the compiled graph 1,000 times, records per-invocation wall-clock via `time.perf_counter_ns()`, and computes per-node overhead as `(total_ns / 100)` for each invocation; from the 1,000-sample list it computes p50 and p95 via `statistics.quantiles` or `numpy.percentile` (project must choose one; document the choice in a module-level constant).
- [ ] On the first run (when `tests/perf/baseline.json` does **not** exist on disk or is missing the `canary_overhead` key), the test writes `{"canary_overhead": {"p50_ns": <int>, "p95_ns": <int>, "recorded_at": "<ISO-8601-UTC>", "node_count": 100, "invocations": 1000, "langgraph_version": "<resolved-version>", "pydantic_version": "<resolved-version>"}}` and **passes** with a printed message: `"baseline recorded: p50=<n>ns p95=<n>ns — commit tests/perf/baseline.json"`.
- [ ] On every subsequent run, the test loads the baseline and asserts `measured_p50 <= baseline_p50 * 1.25` **and** `measured_p95 <= baseline_p95 * 1.25`. A > 25% regression on **either** quantile fails the test.
- [ ] Failure message names the regressing quantile, the baseline value, the measured value, and the percentage delta — *and* prints `"To accept this regression as the new baseline: re-run with CODEGENIE_PERF_BASELINE_REFRESH=1 and commit tests/perf/baseline.json."`.
- [ ] An opt-in `CODEGENIE_PERF_BASELINE_REFRESH=1` environment variable, when set, forces the test to overwrite `tests/perf/baseline.json` with freshly measured values (and pass). The variable's presence is logged to stderr so CI captures it.
- [ ] The test is marked `@pytest.mark.slow` (per `phase-arch-design.md §CI gates row 4`); the merge-queue nightly cron runs it. PR-level CI may *opt in* via `pytest -m slow` but the gate is nightly.
- [ ] A warm-up phase runs **5** untimed invocations before the measured 1,000 to absorb JIT / import-cache cold paths; the warmup count is a module-level constant `WARMUP_INVOCATIONS = 5`.
- [ ] `tests/perf/README.md` exists and documents: (1) what the canary measures and *does not* measure; (2) the exact procedure to bump the baseline after a deliberate dependency upgrade (run with `CODEGENIE_PERF_BASELINE_REFRESH=1`, inspect the diff, commit `tests/perf/baseline.json` as part of the dep-bump PR); (3) the policy that `// flaky-skip` is **prohibited** — noisy runners trigger an investigation, not a skip; (4) the relationship to ADR-P6-006 (separate gate, separate ADR).
- [ ] `tests/perf/__init__.py` and `tests/perf/conftest.py` (if helpers are extracted) exist.
- [ ] `tests/perf/baseline.json` is **not** committed in this PR — it lands as a follow-up commit on the first CI run after merge (matches the "committed on first CI run" wording in arch §Golden files). The story's PR description must call this out so reviewers don't reject the PR for missing the file.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check tests/perf/`, `ruff format --check tests/perf/`, `mypy --strict tests/perf/` clean; `pytest tests/perf/test_canary_overhead.py -m slow` passes locally.

## Implementation outline
1. Read `src/codegenie/graph/vuln_loop.py` for the `StateGraph` construction pattern. The canary uses the same `langgraph.graph.StateGraph` API but a *different* state class — a `TypedDict` with one integer field — to avoid coupling the canary to `VulnLedger` (which would re-introduce Pydantic-validation cost into the measurement and defeat the purpose of measuring *LangGraph* overhead).
2. Create `tests/perf/__init__.py` (empty), `tests/perf/test_canary_overhead.py`.
3. Build the no-op graph in a module-level fixture: 100 nodes named `n_0 … n_99`, each `def(state): return state`. Compile with `MemorySaver()` (or no checkpointer if the API permits — verify which is faster but the *measurement* is what counts, not the absolute number).
4. Wall-clock loop: 5 untimed warm-up invocations, then 1,000 timed invocations via `time.perf_counter_ns()`. Capture per-invocation total, divide by 100, store in a list.
5. Quantile computation: prefer `statistics.quantiles(samples, n=100, method="exclusive")` for p50 (index 49) and p95 (index 94); document the choice in `QUANTILE_METHOD = "exclusive"` at module top so a Python upgrade doesn't silently change the numbers.
6. Baseline file I/O: `BASELINE_PATH = Path("tests/perf/baseline.json")`. Read if exists; if `"canary_overhead"` key missing OR `CODEGENIE_PERF_BASELINE_REFRESH=1`, write and pass.
7. Regression check: tolerance constant `REGRESSION_TOLERANCE = 1.25`; failure message includes `baseline_p50`, `measured_p50`, `delta_pct = (measured - baseline) / baseline * 100`, and the refresh-instruction line.
8. Write `tests/perf/README.md` with the four sections enumerated in the AC.
9. Confirm the test fails cleanly when a `baseline.json` is hand-mutated to a 1 ns value (forcing a synthetic regression) — this is the red test in the TDD plan.
10. Confirm `mypy --strict` is clean — quantile computation typically returns `list[float]`; cast quantile picks to `int` only at write time.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/perf/test_canary_overhead.py` (the canary itself).

A *meta*-test that proves the canary fails on a synthetic regression:

```python
# tests/perf/test_canary_overhead_meta.py
import json
from pathlib import Path
import pytest

from tests.perf.test_canary_overhead import (
    BASELINE_PATH,
    REGRESSION_TOLERANCE,
    _check_against_baseline,
)


def test_canary_fails_on_synthetic_50pct_regression(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # arrange: stash a baseline that is 50% faster than what we will "measure"
    fake_baseline = {"canary_overhead": {"p50_ns": 1_000, "p95_ns": 2_000, "node_count": 100, "invocations": 1000}}
    baseline_file = tmp_path / "baseline.json"
    baseline_file.write_text(json.dumps(fake_baseline))
    monkeypatch.setattr("tests.perf.test_canary_overhead.BASELINE_PATH", baseline_file)
    # act: simulate a measurement 50% slower than baseline (1500ns p50)
    with pytest.raises(AssertionError) as exc:
        _check_against_baseline(measured_p50_ns=1500, measured_p95_ns=2500)
    # assert: failure message names p50 and the percentage delta
    assert "p50" in str(exc.value)
    assert "50" in str(exc.value)  # 50% delta
    assert "CODEGENIE_PERF_BASELINE_REFRESH" in str(exc.value)


def test_canary_writes_baseline_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline_file = tmp_path / "baseline.json"
    monkeypatch.setattr("tests.perf.test_canary_overhead.BASELINE_PATH", baseline_file)
    _check_against_baseline(measured_p50_ns=1234, measured_p95_ns=5678)
    data = json.loads(baseline_file.read_text())
    assert data["canary_overhead"]["p50_ns"] == 1234
    assert data["canary_overhead"]["p95_ns"] == 5678
    assert data["canary_overhead"]["node_count"] == 100
    assert data["canary_overhead"]["invocations"] == 1000


def test_canary_passes_within_25pct(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_baseline = {"canary_overhead": {"p50_ns": 1_000, "p95_ns": 2_000, "node_count": 100, "invocations": 1000}}
    baseline_file = tmp_path / "baseline.json"
    baseline_file.write_text(json.dumps(fake_baseline))
    monkeypatch.setattr("tests.perf.test_canary_overhead.BASELINE_PATH", baseline_file)
    # 1.24x is within tolerance; must NOT raise
    _check_against_baseline(measured_p50_ns=1240, measured_p95_ns=2480)
```

### Green — make it pass
Implement `tests/perf/test_canary_overhead.py` with:
- A pure `_check_against_baseline(measured_p50_ns: int, measured_p95_ns: int) -> None` helper that reads `BASELINE_PATH`, writes-on-missing, asserts-on-present, and is the *only* path the test body and the meta-test exercise.
- A `test_per_node_overhead_within_25pct_of_baseline` body that builds the graph, runs warm-up + 1,000 timed invocations, computes p50/p95, and calls `_check_against_baseline(...)`.

### Refactor — clean up
Pull the graph construction into a `_build_canary_graph() -> CompiledStateGraph` fixture; pull the timing loop into `_measure_overhead_ns(graph, *, invocations: int = 1000, warmup: int = 5) -> tuple[int, int]` returning `(p50, p95)`. Both are module-private. Keep the meta-test pure (no real measurement, only `_check_against_baseline` exercised), so it runs in milliseconds and is *not* `@pytest.mark.slow`.

## Files to touch
| Path | Why |
|---|---|
| `tests/perf/__init__.py` | New package marker. |
| `tests/perf/test_canary_overhead.py` | The canary itself. |
| `tests/perf/test_canary_overhead_meta.py` | Meta-tests for `_check_against_baseline` (red test source). |
| `tests/perf/README.md` | Baseline-update procedure, flaky-skip prohibition, ADR-P6-006 relationship. |
| (optional) `tests/perf/conftest.py` | If `_build_canary_graph` is reused by S9-02/S9-03 helpers. Leave out unless needed. |

## Out of scope
- **Checkpoint throughput** — S9-02 (`test_checkpoint_throughput.py`, 100 writes/s gate, ADR-P6-006 ADR text).
- **Concurrent-workflow throughput** — S9-03 (Gap 3 addendum).
- **Cold-start compile perf** — already shipped in S5-03 (`test_compile_cold_start.py`).
- **CI workflow file edits** — adding `@pytest.mark.slow` to the merge-queue cron is a CI-config concern owned by Step 10's polish work. This story confirms the marker is present but does not edit `.github/workflows/`.
- **Editing `tests/perf/baseline.json`** — the file is created on the first post-merge CI run; the PR does **not** commit it.

## Notes for the implementer
- The canary measures **LangGraph dispatch overhead**, not application work. Use a `TypedDict` state with one integer field — not `VulnLedger` — to keep Pydantic validation out of the hot loop. If you accidentally use `VulnLedger`, the measurement becomes "Pydantic round-trip cost," the baseline drifts up an order of magnitude, and the 25% regression rule loses meaning.
- Warm-up matters more than people expect. The first invocation pays cold-import costs (LangGraph builds internal dispatch tables on first compile). The 5 warm-up invocations are the floor; raise to 10 if your local runs show first-iteration jitter > 2× steady-state.
- Pin `QUANTILE_METHOD = "exclusive"` (the default for `statistics.quantiles`) and document why: switching to `"inclusive"` would shift p95 by one sample position and look like a 1–2% baseline drift on a Python upgrade. Catch this at design time.
- The `CODEGENIE_PERF_BASELINE_REFRESH=1` escape hatch must be loud — log to stderr on every invocation when set. Silent baseline bumps are how the gate erodes.
- The 25% tolerance is intentionally loose. Resist the urge to tighten it to 10% "for hygiene"; CI-runner noise will flap the gate and the team will start hating it. The strategy is *loose tolerance + deliberate baseline bumps*, not *tight tolerance + skip on flake*. See `High-level-impl.md §Step 9 Risks` and CLAUDE.md global rule §12.
- The baseline file shape (`{"canary_overhead": {...}}`) leaves room for S9-02 and S9-03 to add sibling keys (`"checkpoint_throughput": {...}`, `"concurrent_throughput": {...}`) under the same file. Do not rename the top-level shape later — coordinate via this story's schema.
- If `tests/perf/baseline.json` already contains a `canary_overhead` key when this PR lands (e.g., a developer ran the test locally and committed it by accident), treat that as a *bug* and remove it — the baseline is committed on the first **CI** run, not the first local run, so the recorded numbers reflect CI hardware. The PR description must instruct reviewers to check.
- If LangGraph's API for compiling without any checkpointer changes (`MemorySaver` vs `None`), document which one you used and why. The canary should not silently start measuring `MemorySaver`'s in-memory dict cost if a real `None` option exists.
- ADR-P6-006 is **not** referenced by this story's failure path. This canary failing on regression does *not* trigger Postgres pull-forward — it triggers a baseline-bump conversation. ADR-P6-006 is exclusively the throughput watchdog's escalation hook (S9-02). Be explicit in the failure message so operators don't conflate the two gates.
