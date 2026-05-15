# Story S6-02 — Coverage ratchet to 90/80 + warm-path + per-probe RSS bench canaries

**Step:** Step 6 — Golden file, coverage ratchet, bench additions, Phase 2 handoff
**Status:** Ready
**Effort:** M
**Depends on:** S5-05, S4-04
**ADRs honored:** ADR-0005 (90/80 floor with 85/75 carve-out for `deployment.py` + `ci.py`)

## Validation notes

Validated: 2026-05-15
Verdict: HARDENED
Findings addressed: 11 total — 4 blocks, 5 hardens, 2 nits

Changes applied:
- AC-1 rewritten — pinned per-module floors to the actually-shipped `[tool.coverage_carve_outs.entries]` table + `scripts/check_coverage_carve_outs.py` enforcement (NOT `[tool.coverage.report]`, which only supports a global `fail_under`). Consistency F1 + Coverage F2.
- AC-2 strengthened — added the harness-not-silently-no-op invariant (re-read JSON + assert keys + `> 0`) mirroring Phase 0's three canaries; added the non-advisory CacheHit gate for at least one probe so a silent cache-never-hits regression is caught even though the wall-clock ratio is advisory. Coverage F4 + Test-Quality F3 + Design-Patterns F5.
- AC-3 strengthened — enumerated all six Layer A probes; pinned start/stop-per-probe to prevent allocation pollution; pinned the single top-level `per_probe_rss` key shape (one `merge_bench_result` call, not six). Coverage F5 + Design-Patterns F4.
- AC-5 strengthened — explicit AC for bumping `bench-collection-guard` from `-ne 3` to `-ne 5` in `.github/workflows/ci.yml` (the gate breaks the moment the two new tests land if not bumped). Coverage F1.
- AC-6 unchanged in intent; reworded for verifiability.
- AC-9 added — negative-space AC: the `[tool.coverage_carve_outs.entries]` table contains exactly two entries (no third carve-out smuggled in to make CI green); the existing S4-04 build test is the runtime proof. Coverage F3.
- AC-10 added — observable extension-by-addition AC: a future bench canary added under `tests/bench/` requires zero edits to `_helpers.py`. Design-Patterns F1 (rule-of-three already passed: cold_start, coordinator_overhead, cache_hit_dispatch are the three precedents).
- TDD plan rewritten — `tests/bench/test_warm_path_latency.py` mirrors Phase 0's `test_cache_hit_dispatch.py` shape (in-process `asyncio.run(gather(...))`, not subprocess) so the warm path can be observed via `GatherResult.executions[...] is CacheHit`; consumes `bench_results_path` + `merge_bench_result` from `tests/bench/_helpers.py` instead of inline atomic-write. Test-Quality F1 + Test-Quality F2 + Design-Patterns F1.
- TDD plan added test for per-probe RSS that explicitly start/stops `tracemalloc` per probe and reads `peak` (not `current`). Test-Quality F5.
- Notes-for-implementer extended with: kernel-consumption framing for `_helpers.py`, the High-level-impl.md vs phase-arch-design.md "≤ 0.25" wording reconciliation (Consistency F2), the deferred extract opportunity for `measure_probe_peak_rss` (Design-Patterns F2 — first occurrence; do NOT extract preemptively per Rule 2), and the `default_registry` introspection pattern that avoids hard-coding probe names (Design-Patterns F3).

Full audit log: docs/phases/01-context-gather-layer-a-node/stories/_validation/S6-02-coverage-ratchet-bench.md

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

- [ ] **AC-1 (coverage ratchet — pinned to S4-04's actually-shipped mechanism).** `pyproject.toml` `[tool.pytest.ini_options].addopts` is updated from `--cov-fail-under=85` to `--cov-fail-under=90`; the existing `[tool.coverage_carve_outs.entries]` rows for `src/codegenie/probes/deployment.py` and `src/codegenie/probes/ci.py` at line=85 / branch=75 (S4-04, ADR-0005) are preserved unchanged; `[tool.coverage.report].omit` continues to exclude `src/codegenie/cli.py`; `scripts/check_coverage_carve_outs.py` continues to be invoked in the CI `test` job's "Per-module coverage carve-outs (ADR-0005)" step against `coverage.json`. (validator: hardened — original AC-1 named `[tool.coverage.report]` per-module floors, but coverage.py only supports a global `fail_under`; per-module enforcement actually lives in `[tool.coverage_carve_outs.entries]` + the script reading `coverage.json`. See ADR-0005 §Consequences for the historical wording vs. what shipped.)
- [ ] **AC-2 (warm-path bench — in-process, harness-not-noop, non-advisory cache-hit gate).** `tests/bench/test_warm_path_latency.py` exists and:
  - Mirrors Phase 0's `tests/bench/test_cache_hit_dispatch.py` shape: copies `tests/fixtures/node_typescript_helm/` into `tmp_path`, builds a `RepoSnapshot`, and dispatches via `asyncio.run(gather(snap, task, probes, cfg, cache, sanitizer))` twice in the same Python process (NOT via `subprocess.run(["codegenie", ...])` — the in-process path is what allows the warm-run executions dict to be inspected).
  - Times each call with `time.perf_counter()`; computes `ratio = warm_s / cold_s`.
  - Calls `merge_bench_result(bench_results_path(tmp_path), "warm_path_ratio", {"cold_s": ..., "warm_s": ..., "ratio": ...})` from `tests/bench/_helpers.py` (does NOT reinvent the atomic-write).
  - **Never asserts a threshold on the ratio** (advisory; ratio surfaces in the PR comment only — ADR per `phase-arch-design.md §Edge cases row 12`).
  - **Non-advisory gate:** asserts that on the warm run, at least one Layer A probe execution is `isinstance(execution, CacheHit)` (mirroring `test_cache_hit_dispatch.py:69`'s ADR-0009 gate). A silent cache-never-hits regression would otherwise produce a small ratio that looks healthy.
  - **Harness-not-silently-no-op:** after writing, re-reads `bench-results.json` and asserts `parsed["warm_path_ratio"]["cold_s"] > 0` and `parsed["warm_path_ratio"]["warm_s"] > 0` (mirrors the same invariant in all three Phase 0 canaries).
  (validator: hardened — original AC ran subprocess + reinvented the atomic-write inline + had no harness-not-noop and no cache-hit assertion.)
- [ ] **AC-3 (per-probe RSS bench — exhaustive, non-polluting, single namespaced key).** `tests/bench/test_per_probe_rss.py` exists and:
  - Dispatches **each of the six Layer A probes** (`language_detection`, `node_build_system`, `node_manifest`, `ci`, `deployment`, `test_inventory`) **individually** through `gather(...)` with the production `OutputSanitizer` + `CacheStore(tmp_path / "cache")`. The set is enumerated by reading `default_registry.for_task(...)` and filtering on `probe.layer == "A"` (NOT a hard-coded list — the test should still work when Phase 2 adds Layer B/C/D probes).
  - For each probe, calls `tracemalloc.start()` **before** the dispatch and `tracemalloc.stop()` **after** (start/stop per probe; the second probe's peak must NOT be polluted by the first's allocations). Reads `_current, peak = tracemalloc.get_traced_memory()` and stores `peak`.
  - Writes results via a **single** `merge_bench_result(out, "per_probe_rss", {probe_name: peak_bytes, ...})` call producing one top-level `per_probe_rss` key whose value is a dict mapping all six probe names to ints (NOT six separate top-level keys).
  - **Never asserts a threshold on `peak`** (advisory).
  - **Harness-not-silently-no-op:** asserts `set(parsed["per_probe_rss"].keys()) == {six probe names}` (or equivalent assertion that all six probes were measured, no probe was silently skipped) and `all(v > 0 for v in parsed["per_probe_rss"].values())`.
  (validator: hardened — original AC did not enumerate the six probes, did not pin start/stop-per-probe, did not pin the JSON key shape — `per_probe_rss.<probe_name>` is ambiguous between "nested dict" and "six dotted top-level keys".)
- [ ] **AC-4 (marker registration).** Both bench files carry the `pytest.mark.bench` marker — already registered in `pyproject.toml` `[tool.pytest.ini_options].markers` from S5-01. Default local invocation (`pytest`) skips both via `addopts = "... -m 'not bench' ..."`; `pytest -m bench tests/bench/` runs all five canaries.
- [ ] **AC-5 (CI bench-collection-guard bumped 3 → 5).** `.github/workflows/ci.yml`'s `bench-collection-guard` step (currently asserts `collected -ne 3` to fail) is updated to assert `collected -ne 5`; its echo message and the failure stderr message are bumped accordingly. The `bench (advisory)` step itself (`continue-on-error: true`, `pytest tests/bench/ -m bench`) needs no change — it already discovers files via the marker. The `Upload bench-results.json` artifact step is unchanged. (validator: added — original story said "no changes required if the existing step picks up the two new files automatically" but did NOT mention the gating `bench-collection-guard` count, which would silently fail the moment the two new tests land. This is a CI-breaking gap.)
- [ ] **AC-6 (PR body shows per-module coverage).** The Step 6 PR body contains a markdown table with one row per Phase 1 probe (`probes/language_detection.py`, `probes/node_build_system.py`, `probes/node_manifest.py`, `probes/ci.py`, `probes/deployment.py`, `probes/test_inventory.py`) and columns `line %` / `branch %` / `floor (line/branch)` / `pass`; if any module is below its declared floor, the PR cannot merge until tests are added (the `Per-module coverage carve-outs (ADR-0005)` CI step is the runtime proof — but a human-readable table in the PR body is the reviewer's signal).
- [ ] **AC-7 (test suites green).** `pytest -m "not bench"` exits 0 on the full Phase 1 test surface with the new `--cov-fail-under=90` global gate active and the per-module 85/75 carve-outs honored; `pytest tests/bench/ -m bench` runs all five canaries (3 from Phase 0 + 2 new) without raising and writes `bench-results.json` with all five top-level keys present.
- [ ] **AC-8 (lint/format/type clean).** `ruff check tests/bench/test_warm_path_latency.py tests/bench/test_per_probe_rss.py`, `ruff format --check tests/bench/test_warm_path_latency.py tests/bench/test_per_probe_rss.py`, and `mypy --strict tests/bench/test_warm_path_latency.py tests/bench/test_per_probe_rss.py` all pass — `tracemalloc.get_traced_memory()` is annotated as `tuple[int, int]` and unpacked explicitly.
- [ ] **AC-9 (negative-space — no third carve-out smuggled in).** `[tool.coverage_carve_outs.entries]` in `pyproject.toml` contains **exactly two entries** after this PR (deployment.py + ci.py), unchanged from S4-04. `tests/unit/build/test_coverage_carve_outs.py::test_carve_out_table_has_exactly_two_entries` (S4-04) continues to pass. (validator: added — Coverage F3. Without this AC, the laziest passing implementation is "if a probe is under floor, add a third carve-out at 80/70 and ship". The story's narrative says "do not lower or carve out — file a bug against the probe's owning story" but that intent must be encoded as an observable contract, not just narrative.)
- [ ] **AC-10 (extension-by-addition for bench harness).** Adding a sixth bench canary under `tests/bench/test_<name>.py` requires zero edits to `tests/bench/_helpers.py`; the new test consumes `bench_results_path()` + `merge_bench_result()` and registers a new top-level key. The only edit elsewhere in the repo is bumping `bench-collection-guard`'s `-ne N` count by 1 and (one-time) declaring the new `bench` marker — already declared. (validator: added — Design-Patterns F1, observable Open/Closed contract for the bench harness; `_helpers.py` is the kernel, the canaries are leaves; rule-of-three was passed by Phase 0's three canaries — this story consumes, does not reinvent. Pattern: Plugin / Kernel + Registry, "Extension by addition" — CLAUDE.md.)

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

### Red — write the failing tests first

Two failing-test surfaces:

1. **The coverage gate itself.** Bumping `--cov-fail-under` from 85 to 90 in `pyproject.toml` and running `pytest -m "not bench"` locally either passes (every Phase 1 probe is at-or-above floor; the gate becomes active going forward) OR fails on the first probe under floor. A failure *is* the red — STOP and file a coverage-gap bug against the offending probe's owning story (S2-01..S4-03). Do NOT lower the floor or add a third carve-out (AC-9 is the negative-space contract).

2. **The bench-collection-guard gate.** `.github/workflows/ci.yml`'s `bench-collection-guard` step asserts `collected -ne 3`. Adding two new bench files makes `collected == 5`, which fails the guard immediately on PR push. That failure *is* the second red — bump the count to `5` in the same PR (AC-5).

Bench canaries themselves are observation harnesses (Phase 0 S5-01 precedent), not behavior tests, so they have no per-test red phase — they're written green-from-birth and read by reviewers via the artifact. The non-advisory assertions inside them (`isinstance(execution, CacheHit)` for AC-2; the harness-not-noop re-read assertions in both) are the gates that catch silent-no-op failure modes.

### Green — make it pass

Test file path: `tests/bench/test_warm_path_latency.py`

```python
"""Advisory warm-path latency canary (S6-02).

Mirrors `tests/bench/test_cache_hit_dispatch.py` (Phase 0 S5-01) intentionally
— in-process gather is what allows the warm-run executions dict to be
inspected for `CacheHit`. A subprocess shape would lose that signal and a
silent cache-never-hits regression would produce a healthy-looking ratio.

The wall-clock ratio (warm / cold) is advisory and written to
``bench-results.json["warm_path_ratio"]``. The non-advisory invariant is
the CacheHit assertion mirrored from S5-01 (ADR-0009).
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from pathlib import Path

import pytest

# Side-effect imports — trigger @register_probe for every Layer A probe.
import codegenie.probes.ci  # noqa: F401
import codegenie.probes.deployment  # noqa: F401
import codegenie.probes.language_detection  # noqa: F401
import codegenie.probes.node_build_system  # noqa: F401
import codegenie.probes.node_manifest  # noqa: F401
import codegenie.probes.test_inventory  # noqa: F401
from codegenie.cache.store import CacheStore
from codegenie.config.defaults import Config
from codegenie.coordinator.coordinator import CacheHit, gather
from codegenie.coordinator.snapshot import build_snapshot
from codegenie.output.sanitizer import OutputSanitizer
from codegenie.probes.base import Task
from codegenie.probes.registry import default_registry
from tests.bench._helpers import bench_results_path, merge_bench_result

_FIXTURE_SRC = Path(__file__).parent.parent / "fixtures" / "node_typescript_helm"


@pytest.mark.bench
def test_warm_path_latency_ratio(tmp_path: Path) -> None:
    fixture = tmp_path / "node_typescript_helm"
    shutil.copytree(_FIXTURE_SRC, fixture)

    cfg = Config()
    sanitizer = OutputSanitizer()
    cache = CacheStore(
        cache_dir=fixture / ".codegenie" / "cache",
        ttl_hours=cfg.cache_ttl_hours,
    )
    probe_classes = default_registry.for_task("__bullet_tracer__", frozenset({"node"}))
    snap = build_snapshot(fixture, cfg)
    task = Task(type="__bullet_tracer__", options={})

    # Cold run.
    probes_cold = [cls() for cls in probe_classes]
    t0 = time.perf_counter()
    asyncio.run(gather(snap, task, probes_cold, cfg, cache, sanitizer))
    cold_s = time.perf_counter() - t0

    # Warm run.
    probes_warm = [cls() for cls in probe_classes]
    t0 = time.perf_counter()
    warm_result = asyncio.run(gather(snap, task, probes_warm, cfg, cache, sanitizer))
    warm_s = time.perf_counter() - t0

    # Non-advisory gate (mirrors test_cache_hit_dispatch.py:69 / ADR-0009).
    cache_hits = [
        name for name, execution in warm_result.executions.items()
        if isinstance(execution, CacheHit)
    ]
    assert cache_hits, (
        "expected at least one Layer A probe to be a CacheHit on warm run; "
        f"executions={warm_result.executions}"
    )

    ratio = (warm_s / cold_s) if cold_s > 0 else 0.0
    out = bench_results_path(tmp_path)
    merge_bench_result(
        out,
        "warm_path_ratio",
        {"cold_s": cold_s, "warm_s": warm_s, "ratio": ratio},
    )

    # Harness-not-silently-no-op assertion (mirrors all three Phase 0 canaries).
    parsed = json.loads(out.read_text(encoding="utf-8"))
    assert "warm_path_ratio" in parsed, parsed
    assert parsed["warm_path_ratio"]["cold_s"] > 0
    assert parsed["warm_path_ratio"]["warm_s"] > 0
```

Test file path: `tests/bench/test_per_probe_rss.py`

```python
"""Advisory per-probe RSS canary (S6-02).

For each Layer A probe registered on ``default_registry``, dispatches a
single-probe gather inside ``tracemalloc.start() ... stop()`` and records
the peak. start/stop is per-probe so the second probe's measurement is
not polluted by the first's allocations (Notes-for-implementer §
``tracemalloc`` adds overhead).

The set of Layer A probes is derived from ``default_registry`` filtered on
``probe.layer == "A"`` so Phase 2's Layer B/C/D probes do not silently
appear in this canary's namespace and so no probe is silently skipped if
the registry shape changes.

Advisory: no threshold assertion on `peak`. The single non-advisory
invariant is harness-not-silently-no-op (all six probes recorded, all > 0).
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tracemalloc
from pathlib import Path

import pytest

import codegenie.probes.ci  # noqa: F401
import codegenie.probes.deployment  # noqa: F401
import codegenie.probes.language_detection  # noqa: F401
import codegenie.probes.node_build_system  # noqa: F401
import codegenie.probes.node_manifest  # noqa: F401
import codegenie.probes.test_inventory  # noqa: F401
from codegenie.cache.store import CacheStore
from codegenie.config.defaults import Config
from codegenie.coordinator.coordinator import gather
from codegenie.coordinator.snapshot import build_snapshot
from codegenie.output.sanitizer import OutputSanitizer
from codegenie.probes.base import Task
from codegenie.probes.registry import default_registry
from tests.bench._helpers import bench_results_path, merge_bench_result

_FIXTURE_SRC = Path(__file__).parent.parent / "fixtures" / "node_typescript_helm"
_EXPECTED_LAYER_A_PROBES = {
    "language_detection",
    "node_build_system",
    "node_manifest",
    "ci",
    "deployment",
    "test_inventory",
}


@pytest.mark.bench
def test_per_probe_peak_rss(tmp_path: Path) -> None:
    fixture = tmp_path / "node_typescript_helm"
    shutil.copytree(_FIXTURE_SRC, fixture)

    cfg = Config()
    sanitizer = OutputSanitizer()
    snap = build_snapshot(fixture, cfg)
    task = Task(type="__bullet_tracer__", options={})

    layer_a_classes = [
        cls
        for cls in default_registry.for_task("__bullet_tracer__", frozenset({"node"}))
        if getattr(cls, "layer", None) == "A"
    ]

    per_probe_peak: dict[str, int] = {}
    for cls in layer_a_classes:
        cache = CacheStore(
            cache_dir=fixture / ".codegenie" / "cache" / cls.name,
            ttl_hours=cfg.cache_ttl_hours,
        )
        probe = cls()
        tracemalloc.start()
        try:
            asyncio.run(gather(snap, task, [probe], cfg, cache, sanitizer))
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        per_probe_peak[cls.name] = peak

    out = bench_results_path(tmp_path)
    merge_bench_result(out, "per_probe_rss", per_probe_peak)

    parsed = json.loads(out.read_text(encoding="utf-8"))
    assert "per_probe_rss" in parsed, parsed
    assert set(parsed["per_probe_rss"].keys()) == _EXPECTED_LAYER_A_PROBES, (
        f"expected exactly the six Layer A probes; got {set(parsed['per_probe_rss'].keys())}"
    )
    assert all(v > 0 for v in parsed["per_probe_rss"].values()), parsed["per_probe_rss"]
```

Then:

1. Land both bench files. Run `pytest tests/bench/ -m bench` locally; both write to `bench-results.json` without raising; the harness-not-noop assertions are the executor's runtime evidence for AC-2 / AC-3.
2. Bump `--cov-fail-under` to 90 in `pyproject.toml`. Run `pytest -m "not bench"`. If any module is below floor, **STOP** — file a coverage-gap bug against the probe's owning story. AC-9 is the negative-space contract: do NOT add a third carve-out.
3. Bump `bench-collection-guard` in `.github/workflows/ci.yml` from `-ne 3` to `-ne 5` and update the echo + stderr messages. Without this, the `test` CI job fails the moment the two new bench files land.
4. Once all modules clear floor and the guard is bumped, push the PR with the per-module coverage table in the body (AC-6).

### Refactor — clean up

- Module docstrings on both bench files explicitly say "advisory only, no merge gate" and reference the ADR per `phase-arch-design.md §Edge cases row 12`.
- Confirm both files consume `bench_results_path` + `merge_bench_result` from `tests/bench/_helpers.py` (no inline atomic-write — the kernel already handles `$GITHUB_WORKSPACE` resolution + per-writer tmp + `fsync` + `os.replace`). Reinventing this is the design-pattern smell flagged in validation.
- `pytest.mark.bench` is applied at the test-function level via `@pytest.mark.bench` decorator (consistent with Phase 0; no module-level `pytestmark`).
- `mypy --strict` passes — `tracemalloc.get_traced_memory()` returns `tuple[int, int]`; the unpack `_current, peak = ...` is explicit.
- The `default_registry.for_task(...) | filter(layer == "A")` introspection avoids hard-coding probe names in the test source; the `_EXPECTED_LAYER_A_PROBES` constant is the negative-space oracle that catches silent registry skew.

## Files to touch

| Path | Why |
|---|---|
| `pyproject.toml` | Modify — bump `--cov-fail-under=85` → `--cov-fail-under=90` in `[tool.pytest.ini_options].addopts` ONLY. Do NOT touch `[tool.coverage_carve_outs.entries]` (S4-04, ADR-0005 — preserved unchanged); do NOT add `[tool.coverage.report].exclude_also` (the per-module floors are NOT enforced via `[tool.coverage.report]`); do NOT touch `[tool.coverage.report].omit` (`cli.py` exclusion preserved). |
| `tests/bench/test_warm_path_latency.py` | New file — advisory warm-path bench; in-process `gather()` ×2; non-advisory CacheHit assertion + harness-not-noop re-read; consumes `_helpers.merge_bench_result()`. |
| `tests/bench/test_per_probe_rss.py` | New file — advisory per-probe RSS bench via `tracemalloc`; one dispatch per probe with start/stop-per-probe; single `per_probe_rss` top-level key; consumes `_helpers.merge_bench_result()`. |
| `.github/workflows/ci.yml` | Modify — bump `bench-collection-guard`'s `-ne 3` → `-ne 5` and update the two surrounding messages (`expected exactly 3 bench tests` → `expected exactly 5 bench tests (S5-01 + S6-02)`; `bench tests collected: ${collected}` echo unchanged in semantics). The `bench (advisory)` step itself uses path discovery (`pytest tests/bench/ -m bench`) and needs no edit. The `Upload bench-results.json` step needs no edit. |

## Out of scope

- **New ADR-amended carve-outs.** ADR-0005 carved out exactly two modules. Any third carve-out requires its own ADR (per ADR-0005 "Decision" + Consequences). If a probe lands under floor, the fix is tests — not a third carve-out. Surface as a separate PR if genuinely necessary; do not bundle here.
- **Threshold assertions on bench canaries.** Variance on shared CI runners makes wall-clock gates inherently flaky (`High-level-impl.md` Phase 0 #5). Advisory forever; if a future phase wants a gate, it lands then with the ADR amendment justifying why variance is now controllable.
- **PR-comment posting mechanics.** Phase 0 S5-01 deferred this to a follow-up; Phase 1 still produces only `bench-results.json`. The comment-posting GitHub Action is a separate concern (and may be filed as a Phase 2 follow-up by S6-03).
- **Coverage report HTML / sidecar artifacts.** CI emits the XML; PR body shows the per-module table; HTML report is local-dev only. Do not preemptively wire up coverage badges.
- **Phase 2's 92/82 ratchet.** Filed as a Phase 2 follow-up in S6-03. Phase 1 lands 90/80; do not bump further here.

## Notes for the implementer

- **Consume the existing bench kernel — do NOT reinvent it.** `tests/bench/_helpers.py` (S5-01) ships `bench_results_path()` (resolves `$GITHUB_WORKSPACE` for CI artifact upload, falls back to `tmp_path` locally) and `merge_bench_result()` (per-writer tmp + `fsync` + `os.replace`; safe under parallel writers). All three Phase 0 canaries consume it; this is the third precedent and the rule-of-three is decisively passed. Pattern: Plugin / Kernel + Registry; the kernel is `_helpers`, the canaries are leaves. Inline atomic-write (the pattern in the original draft of this story) drops `$GITHUB_WORKSPACE` handling so the artifact upload silently fails in CI, drops `fsync`, and races a same-name `.tmp` under future `pytest-xdist` — three regressions for the price of one. AC-10 is the observable Open/Closed contract.
- **In-process gather, not subprocess.** Phase 0's `test_cache_hit_dispatch.py` deliberately uses `asyncio.run(gather(...))` so the `GatherResult.executions` dict can be inspected for `CacheHit`. A subprocess-based warm-path bench loses that signal: a regression that silently disables caching produces a clean ratio. Mirror the in-process shape (AC-2). Per-probe RSS via `tracemalloc` already requires in-process — but the *style* should match across both new files.
- **`tracemalloc` adds overhead.** Don't `tracemalloc.start()` once and dispatch all six probes; the second probe's peak measurement is polluted by the first's. Start/stop per probe — AC-3 pins this and the Green example shows the shape.
- **`get_traced_memory()` returns `(current, peak)`.** Unpack explicitly: `_current, peak = tracemalloc.get_traced_memory()`. `current` is ~0 after gather completes (memory freed); `peak` is the load-bearing field. mypy --strict catches this if you omit the annotation.
- **Probe enumeration via `default_registry`, not hard-coded literals.** AC-3's enumeration of "the six Layer A probes" is a *negative-space oracle* (catches silent registry skew). The test source itself iterates `default_registry.for_task(...)` filtered on `probe.layer == "A"` — when Phase 2 lands Layer B/C/D probes they do not silently pollute `per_probe_rss`. Pattern: Open/Closed at the test boundary.
- **First-occurrence note (do NOT extract preemptively, Rule 2):** if Phase 2's Layer B/C/D probes add a per-layer RSS canary, the loop body of `test_per_probe_rss.py` is a candidate to extract as `measure_probe_peak_rss(probe, snap, cfg, cache, sanitizer) -> int` in `_helpers.py`. This is the FIRST occurrence — three similar lines is better than premature abstraction. Defer extraction; surface the opportunity in the Phase 2 story that introduces the second user.
- **Coverage gate enforcement is a *script*, not coverage.py's `fail_under`.** S4-04 shipped `[tool.coverage_carve_outs.entries]` as a TOML table that `scripts/check_coverage_carve_outs.py` reads alongside `coverage.json` (emitted by `pytest --cov-report=json`). The CI `test` job invokes the script as a separate step. coverage.py's `[tool.coverage.report].fail_under` is global only — the per-module 85/75 carve-outs MUST live in the carve-outs table, not in `[tool.coverage.report]`. ADR-0005 §Consequences originally named `[tool.coverage.report]`; what shipped (S4-04) is the script-driven mechanism. Honor what shipped.
- **The `--cov-fail-under=90` change is a one-line edit.** Bump in `[tool.pytest.ini_options].addopts`. The pyproject.toml comment block above the addopts line already explicitly names this story (S6-02) as the moment the global ratchet happens — the architecture anticipated this edit.
- **The coverage gate cannot be bypassed.** If a Phase 1 probe is under floor, do not lower `--cov-fail-under` or add a third carve-out (AC-9 enforces). The failing probe's PR was supposed to ship its coverage number per the cross-cutting concern; if it didn't, file a bug against its story and block the Step 6 merge (Rule 12 — fail loud).
- **`bench-collection-guard` is the second silent CI failure waiting to bite.** It currently asserts `collected -ne 3`. Bump to `-ne 5` in the same PR or the moment the two new bench files land they trip the guard with a confusing error message. Files-to-touch lists this explicitly.
- **The warm-path ratio is dominated by gather work, not CLI startup, in the in-process shape.** Phase 0's `test_cache_hit_dispatch.py` shape removes the CLI startup cost from the measurement. A ratio < 0.5 is the expected ballpark; a ratio > 0.8 suggests the cache isn't hitting — but the non-advisory `CacheHit` assertion is the real gate, not the ratio.
- **The "≤ 0.25" wording in `High-level-impl.md §Step 6`.** That number is the *expectation*, not the assertion. `phase-arch-design.md §Edge cases row 12` and Phase 0's S5-01 precedent both rule that wall-clock thresholds on shared CI runners are inherently flaky. The bench is advisory forever; the 0.25 number lives in the PR comment as expectation-context, not in the code. Out-of-scope is explicit.
- **PR-body coverage table.** Markdown table with columns `module | line % | branch % | floor (line/branch) | pass`. Run `pytest --cov-report=term-missing -m "not bench"` locally; copy the per-module rows. AC-6 is human-readable; the runtime-enforcement gate is the carve-outs script in CI.
- **If `deployment.py` or `ci.py` lands at, say, 87/77, you are above their 85/75 floor but below the global 90/80 floor.** That is the expected, designed outcome of ADR-0005 — `scripts/check_coverage_carve_outs.py` honors the per-module entry, so CI passes.
- **Do not regenerate the golden in this PR.** S6-01 owns the golden; S6-02 owns the ratchet. If a bench canary somehow changes the slice shape (it should not — bench tests are read-only against the gather pipeline), surface as a bug and stop.
