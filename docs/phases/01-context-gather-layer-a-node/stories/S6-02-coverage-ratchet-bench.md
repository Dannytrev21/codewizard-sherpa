# Story S6-02 — Coverage ratchet to 90/80 + warm-path + per-probe RSS bench canaries

**Step:** Step 6 — Golden file, coverage ratchet, bench additions, Phase 2 handoff
**Status:** Ready
**Effort:** M
**Depends on:** S5-05, S4-04
**ADRs honored:** ADR-0005 (90/80 floor with 85/75 carve-out for `deployment.py` + `ci.py`)

## Context

Phase 0 landed an 85% line / 75% branch coverage floor on `src/codegenie/`. Phase 1 ships substantially more deterministic-parser code (parsers, lockfile helpers, memo, catalogs, the probe ABC consumers) where 90/80 is honest — and ships two structurally-narrow modules (`probes/deployment.py`, `probes/ci.py`) where blanket 90% line coverage is satisfied by tests that exercise every branch but assert nothing meaningful (Rule 9 — "tests verify intent, not just behavior").

S4-04 already declared the per-module carve-outs in `pyproject.toml`. This story does two things: (a) raise the global floor to **90% line / 80% branch** so the ratchet takes effect in CI; (b) land two advisory bench canaries (`tests/bench/test_warm_path_latency.py` and `tests/bench/test_per_probe_rss.py`) that surface latency and memory information as PR comments without gating merge.

The ratchet is tight. If any Phase 1 probe lands below 90/80 (or below 85/75 for the two carve-outs), the Step 6 PR fails CI and cannot merge until the test gap is closed. The implementer-level risk from `High-level-impl.md` #5 is the load-bearing reason every probe story (S2-01, S2-02, S3-05, S4-01, S4-02, S4-03) was required to report per-probe coverage in its PR body — Step 6 is the moment that discipline either holds or doesn't. If it doesn't hold, this story surfaces the gap loudly and the failing probe's author is on the hook (no merging Step 6 around it; no quietly lowering the floor).

The two bench canaries extend Phase 0's three existing canaries (`test_cli_cold_start.py`, `test_coordinator_overhead.py`, `test_cache_hit_dispatch.py`). They never gate merge — variance on shared CI runners makes wall-clock gates inherently flaky (`High-level-impl.md` #5 in Phase 0). The structural defense lives in `import-linter` (no LLM imports) and in the per-probe sub-schema strictness — *not* in latency gates. The canaries surface regression signal as a PR comment so a 4x slowdown is caught before merge by a reviewer's eye, not by a flaky CI gate.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Goals"` #7 — 90/80 line/branch coverage floor with `deployment.py` + `ci.py` at 85/75 (ADR-0005).
  - `../phase-arch-design.md §"Testing strategy" / "CI gates"` — `--cov-fail-under=90` enforcement; the `test` job is the gate.
  - `../phase-arch-design.md §"Testing strategy" / "Performance regression tests"` — two new canaries: `test_warm_path_latency.py` (second-run / first-run ≤ 0.25 advisory) and `test_per_probe_rss.py` (`tracemalloc` per probe, advisory).
  - `../phase-arch-design.md §"Edge cases"` row 12 — `ParsedManifestMemo` is `None` falls back to direct parse — surfaced via `probe.memo.miss` count anomaly; the warm-path bench is the proxy that catches it before it becomes a regression.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0005-coverage-carve-outs-deployment-ci.md` — ADR-0005 — 90/80 default, 85/75 for `deployment.py` + `ci.py`, `cli.py` excluded; further carve-outs require their own ADR.
- **High-level impl plan:**
  - `../High-level-impl.md §"Step 6"` features — coverage ratchet: `pyproject.toml` updated to `--cov-fail-under=90` with per-module floors of 85/75; `tests/bench/test_warm_path_latency.py` (ratio ≤ 0.25 advisory); `tests/bench/test_per_probe_rss.py` (advisory).
  - `../High-level-impl.md §"Step 6 — Done criteria"` bullet 3 + 4 — coverage gate passes at 90/80 with carve-outs documented, percentages shown in PR body; both bench canaries run in CI and post advisory comments, never blocking.
  - `../High-level-impl.md §"Implementation-level risks" #5` — coverage ratchet at 90/80 is tight enough to block Step 6 if any probe falls short; if `deployment.py` or `ci.py` is below 85/75 at the per-module floor, that probe's PR cannot merge until the test gap is closed — don't push the work into Step 6.
- **Manifest:**
  - `../stories/README.md` — S6-02 row; "Cross-cutting concerns" / "Per-probe local coverage report" — every probe story (S2-01 / S2-02 / S3-05 / S4-01 / S4-02 / S4-03) was supposed to report local coverage in its PR body. S6-02 cannot recover if any of those came in under floor.
- **Phase 0 reference (bench shape to mirror):**
  - `../../00-bullet-tracer-foundations/stories/S5-01-bench-concurrent-cache.md` — Phase 0's three canaries; this story extends the pattern (advisory only, no thresholds asserted, `bench-results.json` written, marker registered).
- **Existing code (consumed by this story):**
  - `pyproject.toml` — `[tool.pytest.ini_options]` carries `--cov-fail-under`; `[tool.coverage.report]` carries per-module floors from S4-04.
  - `tests/fixtures/node_typescript_helm/` — the warm-path bench's input.
  - `src/codegenie/coordinator/coordinator.py` — `GatherResult` and `ProbeExecution` shape; per-probe RSS bench iterates registered probes.
  - `tests/bench/` (from Phase 0) — the three existing canaries; this story adds two more files alongside them.

## Goal

Raise the global coverage gate to 90% line / 80% branch with documented 85/75 carve-outs for `probes/deployment.py` + `probes/ci.py` (ADR-0005), and land two advisory bench canaries — `test_warm_path_latency.py` (warm-run wall-clock ratio) and `test_per_probe_rss.py` (`tracemalloc` per probe) — that post results as PR comments without ever gating merge.

## Acceptance criteria

- [ ] `pyproject.toml` `[tool.pytest.ini_options]` sets `--cov-fail-under=90`; `[tool.coverage.report]` per-module floors of 85/75 declared for `src/codegenie/probes/deployment.py` and `src/codegenie/probes/ci.py`; `src/codegenie/cli.py` excluded (ADR-0005).
- [ ] `tests/bench/test_warm_path_latency.py` exists, runs `codegenie gather <node_typescript_helm>` twice, computes `second_run_wall_clock / first_run_wall_clock`, writes the ratio to `bench-results.json` keyed `warm_path_ratio`, and **never** asserts a threshold (advisory only).
- [ ] `tests/bench/test_per_probe_rss.py` exists, dispatches each of the six Layer A probes individually through the coordinator with `tracemalloc.start()` and `tracemalloc.get_traced_memory()`, writes per-probe peak-RSS-bytes to `bench-results.json` keyed `per_probe_rss.<probe_name>`, and **never** asserts a threshold (advisory only).
- [ ] Both bench files carry the `pytest.mark.bench` marker registered in `pyproject.toml` (so `pytest -m "not bench"` is the default local invocation).
- [ ] CI workflow file routes the two new bench tests into the existing `bench` step from Phase 0 (S5-01); the step uses `continue-on-error: true` and the artifact upload mechanism is unchanged.
- [ ] The Step 6 PR body shows actual per-module coverage percentages for every Phase 1 probe (`probes/language_detection.py`, `probes/node_build_system.py`, `probes/node_manifest.py`, `probes/ci.py`, `probes/deployment.py`, `probes/test_inventory.py`); if any module is below its declared floor, the PR cannot merge until tests are added.
- [ ] `pytest --cov=src/codegenie --cov-report=term-missing --cov-report=xml -m "not bench"` exits 0 on the full Phase 1 test surface; `pytest -m bench` runs the new canaries without failure.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` pass on the two new bench files.

## Implementation outline

1. **Coverage ratchet.** Update `pyproject.toml`:
   - Bump `[tool.pytest.ini_options] addopts = "... --cov-fail-under=90 ..."` (or whatever the Phase 0 invocation shape is; preserve it surgically per Rule 3).
   - Confirm `[tool.coverage.report]` (from S4-04) declares per-module floors via `fail_under` + per-file exclusion comments or via `[tool.coverage.report.exclude_also]` — the exact mechanism matches Phase 0's convention and S4-04's landed shape; do not re-invent it.
   - Confirm `src/codegenie/cli.py` is excluded (per ADR-0005).
2. **Run coverage locally.** `pytest --cov=src/codegenie --cov-report=term-missing -m "not bench"`. Capture per-module percentages. Compare against floors. If any probe is below floor, **stop** — file a bug against the probe's owning story (S2-01..S4-03), do not raise the floor or add a carve-out without ADR amendment.
3. **Warm-path bench.** `tests/bench/test_warm_path_latency.py`:
   - Mirror Phase 0's `test_cache_hit_dispatch.py` shape (`subprocess.run` two `codegenie gather` calls).
   - Use `time.perf_counter` around each gather; compute the ratio.
   - Write to `bench-results.json` via an atomic write (Phase 0's helper if available).
   - No threshold assertion. Advisory only.
4. **Per-probe RSS bench.** `tests/bench/test_per_probe_rss.py`:
   - Construct a `RepoSnapshot` for `tests/fixtures/node_typescript_helm/` (use the same helper Phase 0's `test_coordinator_overhead.py` uses).
   - For each Phase 1 probe registered in `default_registry`, dispatch a single-probe gather with `tracemalloc.start()`; capture `peak` from `tracemalloc.get_traced_memory()`; `tracemalloc.stop()`.
   - Aggregate per-probe results in `bench-results.json` under `per_probe_rss`.
   - No threshold assertion.
5. **Marker registration.** Confirm `[tool.pytest.ini_options] markers = ["bench: advisory benchmarks; not run by default"]` is present from Phase 0 (S5-01). If absent, add — but this is exceptional; surface in PR body.
6. **CI workflow.** Confirm `.github/workflows/ci.yml` already routes `pytest tests/bench/` with `continue-on-error: true` (Phase 0 S5-01). No changes required if the existing step picks up the two new files automatically. If the step lists test files explicitly, extend the list.
7. **PR body coverage report.** After running coverage locally, copy the per-module percentage table into the PR body. The Step 6 reviewer scans these numbers; CI re-verifies via `--cov-fail-under=90`.

## TDD plan — red / green / refactor

### Red — write the failing test first

The "failing test" for this story is the coverage gate itself. Lower the `--cov-fail-under` to 90 in `pyproject.toml` and run the test suite; if any probe is under floor, CI fails. That failure *is* the red. There is no per-test red phase for the bench canaries — they are observation harnesses (same as Phase 0 S5-01), not behavior tests.

Test file path: `tests/bench/test_warm_path_latency.py`

```python
# tests/bench/test_warm_path_latency.py
"""Advisory warm-path latency canary. Writes ratio to bench-results.json. Never gates merge."""
import json
import subprocess
import time
from pathlib import Path

import pytest


pytestmark = pytest.mark.bench

FIXTURE = Path(__file__).parent.parent / "fixtures" / "node_typescript_helm"


def _gather_once(output_dir: Path) -> float:
    start = time.perf_counter()
    result = subprocess.run(
        ["codegenie", "gather", str(FIXTURE), "--output", str(output_dir)],
        check=False,
        capture_output=True,
    )
    elapsed = time.perf_counter() - start
    assert result.returncode == 0, result.stderr.decode()
    return elapsed


def test_warm_path_latency_ratio(tmp_path: Path) -> None:
    """
    Warm-path bench: second-run wall-clock / first-run wall-clock.
    Advisory only — never asserts a threshold. Surfaces regression as a PR comment.
    """
    output = tmp_path / "out"
    output.mkdir()
    first = _gather_once(output)
    second = _gather_once(output)
    ratio = second / first if first > 0 else float("inf")

    results_path = tmp_path.parent / "bench-results.json"
    payload = json.loads(results_path.read_text()) if results_path.exists() else {}
    payload["warm_path_ratio"] = {"first_s": first, "second_s": second, "ratio": ratio}
    tmp = results_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.replace(results_path)
```

### Green — make it pass

1. Land both bench files. Run `pytest -m bench` locally; both write to `bench-results.json` without raising.
2. Raise `--cov-fail-under` to 90 in `pyproject.toml`. Run `pytest --cov=src/codegenie -m "not bench"`. If any module is below floor, *do not* lower the floor or add a carve-out. Instead:
   - Identify the deficient module.
   - File a coverage-gap bug against its owning story.
   - The fix lands as a follow-up PR; the Step 6 PR waits.
3. Once all modules clear floor, the test suite goes green. Verify locally that `--cov-fail-under=90` is the active gate.

### Refactor — clean up

- Add module docstrings to both bench files explaining "advisory only, no merge gate."
- Confirm the `bench-results.json` atomic-write pattern matches Phase 0's `test_cache_hit_dispatch.py` (write `.tmp` → `os.replace`). If Phase 0 has a helper, reuse it; if not, the inline two-line pattern is fine.
- Add `pytest.mark.bench` at the module level (not on individual tests) for both files.
- Confirm `mypy --strict` passes — `tracemalloc.get_traced_memory()` returns `tuple[int, int]`, so unpack explicitly.

## Files to touch

| Path | Why |
|---|---|
| `pyproject.toml` | Modify — bump `--cov-fail-under` from 85 to 90; confirm S4-04's per-module floors are correctly declared; confirm `cli.py` exclusion. |
| `tests/bench/test_warm_path_latency.py` | New file — advisory warm-path bench; writes ratio to `bench-results.json`. |
| `tests/bench/test_per_probe_rss.py` | New file — advisory per-probe RSS bench via `tracemalloc`. |
| `.github/workflows/ci.yml` | Modify only if the existing `bench` step lists tests explicitly — extend the list. If it uses path discovery (`pytest tests/bench/`), no change. |

## Out of scope

- **New ADR-amended carve-outs.** ADR-0005 carved out exactly two modules. Any third carve-out requires its own ADR (per ADR-0005 "Decision" + Consequences). If a probe lands under floor, the fix is tests — not a third carve-out. Surface as a separate PR if genuinely necessary; do not bundle here.
- **Threshold assertions on bench canaries.** Variance on shared CI runners makes wall-clock gates inherently flaky (`High-level-impl.md` Phase 0 #5). Advisory forever; if a future phase wants a gate, it lands then with the ADR amendment justifying why variance is now controllable.
- **PR-comment posting mechanics.** Phase 0 S5-01 deferred this to a follow-up; Phase 1 still produces only `bench-results.json`. The comment-posting GitHub Action is a separate concern (and may be filed as a Phase 2 follow-up by S6-03).
- **Coverage report HTML / sidecar artifacts.** CI emits the XML; PR body shows the per-module table; HTML report is local-dev only. Do not preemptively wire up coverage badges.
- **Phase 2's 92/82 ratchet.** Filed as a Phase 2 follow-up in S6-03. Phase 1 lands 90/80; do not bump further here.

## Notes for the implementer

- **The coverage gate cannot be bypassed.** If a Phase 1 probe is under floor, do not lower `--cov-fail-under` or add a carve-out. The failing probe's PR was supposed to ship its coverage number per the cross-cutting concern; if it didn't, file a bug against its story and block the Step 6 merge. The system depends on this discipline (Rule 12 — fail loud).
- **`tracemalloc` adds overhead.** Don't `tracemalloc.start()` once and dispatch all six probes; the second probe's peak measurement is polluted by the first's. Start/stop per probe.
- **The warm-path ratio is dominated by CLI startup, not gather work.** A `ratio ≈ 0.4` is normal even when the gather body is 10x faster on warm run — CLI startup is constant. Advisory-only is the right posture; don't read too much into the absolute number. If the *first* run is wildly slow, that's a separate signal (cold-start regression) handled by Phase 0's existing canary.
- **`bench-results.json` is written under `tmp_path.parent`** in the example above because pytest's `tmp_path` is per-test. If two bench tests run in the same session, the second overwrites the first unless they merge. The atomic-write pattern shown reads existing JSON and merges keys; verify the merge order matches Phase 0's convention.
- **Run `pytest --cov` locally before opening the PR.** Capture the per-module table. Paste it into the PR body. Reviewers will scan it; they should not have to dig through CI logs.
- **The PR-body coverage table format** is unstructured prose — a markdown table with module name and line/branch percentages is sufficient. Phase 2 may want a generated artifact; Phase 1 is manual.
- **If `deployment.py` or `ci.py` land at, say, 87/77, you are above their 85/75 floor but below the global 90/80 floor.** That is the expected, designed outcome of ADR-0005. CI passes — the per-module floor is what `[tool.coverage.report]` declares for those files specifically.
- **Do not regenerate the golden in this PR.** S6-01 owns the golden; S6-02 owns the ratchet. If a bench canary somehow changes the slice shape (it should not — it's read-only), surface as a bug and stop.
- **`mypy --strict` on `tracemalloc`**: `tracemalloc.get_traced_memory()` returns `tuple[int, int]` (current, peak). Annotate explicitly.
