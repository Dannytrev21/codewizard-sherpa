# Story S7-06 — Per-worker memory measurement + fence-CI synthetic PR

**Step:** Step 7 — Performance canaries + fence-CI extension
**Status:** Ready
**Effort:** S
**Depends on:** S7-05
**ADRs honored:** ADR-P7-014 (perf-baseline pattern, runner-class metadata), ADR-P7-009 (fence-CI lives in the same enforcement family as the snapshot canary)

## Context

Two final perf-and-discipline canaries for Step 7. (1) Goal G11 commits to per-worker steady-state memory ≤ 2.4 GB — this story instruments the throughput test from S7-03 to record per-worker RSS during warm distroless runs and asserts the cap. (2) Goal G18 requires zero LLM tokens inside the Phase 7 package boundary; fence-CI from Phase 0 was extended in S1-08 to deny `anthropic|chromadb|sentence-transformers` imports under `probes/`, `transforms/`, `recipes/`, `catalogs/`. This story lands the *synthetic PR* test that proves the deny works — a deliberately broken PR (imports `anthropic` under `recipes/`) is rejected by CI. The discipline mirrors the contract-surface snapshot's rehearsal A from S8-04 — both are mechanical proof that the gate works, not promise that the gate exists.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals G11` — per-worker steady-state ≤ 2.4 GB.
  - `../phase-arch-design.md §Goals G18` — zero LLM tokens inside Phase 7's package boundary; fence-CI deny-imports.
  - `../phase-arch-design.md §Process view — runtime concurrency and durability` — one worker = one workflow at a time in Phase 7 (no fan-out); steady-state RSS is dominated by `dockerfile-parse` AST + Pydantic models + BuildKit metadata.
  - `../phase-arch-design.md §Testing strategy ›Performance regression tests` bullet 4 — memory measurement *integrated into the throughput test* (do not introduce a separate workflow run).
  - `../phase-arch-design.md §Testing strategy ›CI gates #9` — fence-CI is `fence_ci.yaml`.
- **Phase ADRs:**
  - `../ADRs/0014-regression-suite-wall-clock-canary.md` — ADR-P7-014 — baseline-file pattern, runner-class metadata.
  - `../ADRs/0009-contract-surface-snapshot-canary.md` — ADR-P7-009 — the discipline-rehearsal pattern this story's fence-CI synthetic PR mirrors.
- **Source design:**
  - `../final-design.md §Goals#16` — fence-CI extension and the rationale (no LLM tokens inside Phase 7).
- **Existing code:**
  - `tests/perf/test_workflow_throughput.py` (S7-03) — extend this with per-worker RSS sampling; do not introduce a parallel workflow runner.
  - Phase 0's `fence_ci.yaml` (or equivalent fence-CI mechanism — read Phase 0's convention) — owns the deny-import list.
  - S1-08's `tools/snapshot_regen_audit.py` — pattern for "synthetic-PR proves the gate works" — this story copies the *test* pattern, not the *script* pattern.

## Goal

`pytest tests/perf/test_workflow_throughput.py` records per-worker steady-state RSS and asserts ≤ 2.4 GB; `pytest tests/perf/test_fence_ci_denies_anthropic_under_recipes.py` synthesizes a broken PR (imports `anthropic` under `src/codegenie/recipes/`) and asserts fence-CI rejects it.

## Acceptance criteria

- [ ] `tests/perf/test_workflow_throughput.py` (from S7-03) is extended to sample per-worker RSS at ≥ 1 Hz during the warm-distroless leg and record the steady-state value as `max(samples[skip_first_n:])` where `skip_first_n=10` (skip warm-up tail of the cold pass that bleeds into the warm leg's first second).
- [ ] A new sub-test in `test_workflow_throughput.py` asserts steady-state RSS ≤ 2.4 GB (2_400 MB / 2.4 * 1024 * 1024 * 1024 bytes — be explicit and consistent about units).
- [ ] Steady-state RSS baseline key added to `tests/perf/baseline.json`: `per_worker_steady_state_rss_mb`. Bumps via `--update-perf-baseline` (S7-01).
- [ ] RSS sampler is platform-aware: Linux reads `/proc/<pid>/statm` (resident pages × page size); macOS falls back to `psutil.Process(pid).memory_info().rss` if psutil is available, else `ps -o rss=` parsing. Each path documented in the helper module.
- [ ] `tests/perf/test_fence_ci_denies_anthropic_under_recipes.py` exists and runs the fence-CI script against a synthetic source tree (under `tmp_path`) that contains a single file `src/codegenie/recipes/_synthetic_broken.py` with `import anthropic`. The test asserts fence-CI exits non-zero and the stderr/stdout names the offending file path and the denied import.
- [ ] A *companion* positive test in the same file asserts fence-CI exits 0 on a synthetic tree that does *not* import `anthropic|chromadb|sentence-transformers` under the denied scopes — i.e. the gate is not failing-open by accident.
- [ ] Synthetic-PR test exercises *all three* denied imports (`anthropic`, `chromadb`, `sentence-transformers`) under at least one denied scope each (`recipes/`, `probes/`, `transforms/`, `catalogs/`). Parametrize over the cross-product to keep the test honest.
- [ ] The TDD plan's red tests exist, were committed, and are green.
- [ ] Both canaries in CI's merge-gate lane.
- [ ] `ruff check`, `ruff format --check`, and `mypy --strict` clean on touched files.

## Implementation outline

1. Add `tests/perf/_rss.py` with `sample_rss_mb(pid: int) -> float` and a `RssSampler` context manager that spawns a tiny background thread to sample at 1 Hz, captures samples to a list, and exposes `steady_state_mb(skip_first_n: int) -> float` on exit.
2. Modify `tests/perf/conftest.py`'s `throughput_run` fixture (from S7-03) to wrap the warm-distroless leg in a `RssSampler`. Capture the samples and the steady-state value into the leg's result.
3. Add `test_per_worker_steady_state_rss_under_2400mb` to `tests/perf/test_workflow_throughput.py` (next to the existing throughput sub-tests).
4. Add `tests/perf/test_fence_ci_denies_anthropic_under_recipes.py`. The test synthesizes a temp source tree, writes the offending file, then invokes the fence-CI script as a subprocess and asserts on the exit code + stderr. Parametrize over (import, scope-directory) pairs.
5. Wire both into CI merge-gate lane.

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/perf/test_workflow_throughput.py (extended)
def test_per_worker_steady_state_rss_under_2400mb(throughput_run):
    steady = throughput_run.warm_distroless.steady_state_rss_mb
    assert steady <= 2400.0, (
        f"per-worker steady-state RSS {steady:.1f} MB > 2400 MB; "
        f"peak: {throughput_run.warm_distroless.peak_rss_mb:.1f} MB"
    )
```

```python
# tests/perf/test_fence_ci_denies_anthropic_under_recipes.py
import pytest

DENIED_IMPORTS = ["anthropic", "chromadb", "sentence_transformers"]
DENIED_SCOPES = ["recipes", "probes", "transforms", "catalogs"]

@pytest.mark.parametrize("denied_import", DENIED_IMPORTS)
@pytest.mark.parametrize("denied_scope", DENIED_SCOPES)
def test_fence_ci_rejects_denied_import_under_scope(
    tmp_path, denied_import, denied_scope, run_fence_ci
):
    # arrange: synthesize a broken source tree
    scope_dir = tmp_path / "src" / "codegenie" / denied_scope
    scope_dir.mkdir(parents=True)
    broken_file = scope_dir / "_synthetic_broken.py"
    broken_file.write_text(f"import {denied_import}\n")
    # act
    result = run_fence_ci(tmp_path)
    # assert
    assert result.exit_code != 0, f"fence-CI silently accepted {denied_import} under {denied_scope}"
    assert denied_import in result.stderr or denied_import in result.stdout
    assert str(broken_file.relative_to(tmp_path)) in (result.stderr + result.stdout)

def test_fence_ci_accepts_clean_tree(tmp_path, run_fence_ci):
    # arrange: a clean tree with no denied imports
    (tmp_path / "src" / "codegenie" / "recipes").mkdir(parents=True)
    (tmp_path / "src" / "codegenie" / "recipes" / "_clean.py").write_text(
        "from pathlib import Path\n"
    )
    # act
    result = run_fence_ci(tmp_path)
    # assert
    assert result.exit_code == 0, f"fence-CI false-positive on clean tree: {result.stderr}"
```

And a unit-level red test on the RSS helper so we can iterate fast:

```python
# tests/perf/test_rss_helpers.py
def test_steady_state_skips_first_n_samples():
    samples = [3000.0, 2900.0, 2800.0, 2500.0, 2400.0, 2400.0, 2400.0, 2400.0, 2400.0, 2400.0, 2400.0, 2400.0]
    # ^ first 5 are warm-up tail (high RSS as cache populates); steady-state is 2400
    sampler = _RssSampleSet(samples_mb=samples)
    assert sampler.steady_state_mb(skip_first_n=5) == 2400.0

def test_steady_state_loudly_fails_on_empty_samples():
    with pytest.raises(EmptyRssSamples):
        _RssSampleSet(samples_mb=[]).steady_state_mb(skip_first_n=5)
```

Each red test fails — sampler doesn't exist, fence-CI fixture doesn't exist. Commit.

### Green — make it pass

- Add `tests/perf/_rss.py` with platform-aware `sample_rss_mb()`, `RssSampler` context manager, `_RssSampleSet` frozen Pydantic, `EmptyRssSamples` exception.
- Extend the `throughput_run` fixture (in `tests/perf/conftest.py`) to wrap the warm-distroless subprocess invocation in `RssSampler(pid=child.pid)`.
- Add `tests/perf/conftest.py`'s `run_fence_ci` fixture — a thin wrapper that locates the Phase 0 fence-CI script (via `tools/fence_ci.py` or whatever Phase 0 named) and invokes it via `subprocess.run` against the synthetic tree.
- Add the four test functions.

### Refactor — clean up

- Type hints + frozen Pydantic for sample-set models.
- Docstring on `RssSampler` explicitly documenting the 1 Hz sample rate and the platform-dispatch table (Linux: `/proc/<pid>/statm`; macOS: `psutil.Process.memory_info().rss` or `ps -o rss=`).
- Edge case: `subprocess.run` on macOS spawns a child whose RSS may be reported in KiB by `ps` but bytes by `psutil` — normalize to MB inside the sampler; don't push unit-conversion into the assertion.
- Per Global Rule 12 (Fail loud): empty sample list raises `EmptyRssSamples` — never coerce to 0 (silent pass).
- Per ADR-P7-014's "Consequences" — `tests/perf/baseline.json#per_worker_steady_state_rss_mb` is reviewable; bump deliberately via the flag.
- The fence-CI synthetic-PR test is *the* discipline-rehearsal for G18 — pair this story's PR description with a one-paragraph note that the synthetic PR demonstrably fired locally before merge.

## Files to touch

| Path | Why |
|---|---|
| `tests/perf/test_workflow_throughput.py` | Extended with `test_per_worker_steady_state_rss_under_2400mb`. |
| `tests/perf/test_fence_ci_denies_anthropic_under_recipes.py` | New file — fence-CI synthetic-PR canary (G18). |
| `tests/perf/test_rss_helpers.py` | New file — unit tests for sample-set helpers. |
| `tests/perf/_rss.py` | New file — `RssSampler`, `sample_rss_mb`, `_RssSampleSet`. |
| `tests/perf/conftest.py` | Extend `throughput_run` fixture; add `run_fence_ci` fixture. |
| `tests/perf/baseline.json` | Add `per_worker_steady_state_rss_mb` key. |
| `.github/workflows/ci.yml` | Add fence-CI synthetic-PR test to merge-gate lane (the RSS check rides on the existing throughput test entry). |

## Out of scope

- **Mixed-portfolio memory measurement.** S7-05's E2E does *not* measure per-worker RSS; G11's cap is on the steady-state of the warm-distroless workflow (the canonical Phase 7 unit-of-work). If a future phase needs per-task-class memory differentiation, that's an amendment to G11.
- **`fence_ci.yaml` config edits.** The actual deny list was extended in S1-08. This story only verifies the gate; do not re-edit the deny list here.
- **Cross-language import detection.** Fence-CI is Python-import-based; `node_modules/` is not in scope (Phase 7 ships no Node code).
- **OpenTelemetry memory tracing.** Phase 13 owns observability; not in Phase 7.
- **Other denied imports beyond the three named.** `anthropic|chromadb|sentence-transformers` is the canonical list per G18; if more arrive, they go in a new ADR + a new test parametrization.

## Notes for the implementer

- **Memory measurement integrates into the existing throughput test — do not introduce a parallel workflow runner.** Doubling the wall-clock cost of Step 7 for a single RSS number violates the cumulative perf-canary budget that ADR-P7-014's "Tradeoffs" called out.
- **The 1 Hz sample rate is conservative.** Steady-state captures will be stable; a higher rate (10 Hz) increases noise and wastes CPU. Document the choice in `RssSampler`'s docstring.
- **`skip_first_n=10` is "skip the first 10 seconds of the warm leg".** The first seconds of warm-distroless include the residual RSS from the cold pre-pass + import warm-up; the steady-state is what matters for G11. Document and pin.
- **Per `phase-arch-design.md §Process view`, Phase 7 is single-worker.** "Per-worker steady-state" means "the steady-state of the one worker we have". If a future phase introduces fan-out, the canary's `skip_first_n` and the metric semantics will need revisiting.
- **Platform-aware RSS reading is fragile.** On macOS, `psutil` may not be installed in CI by default — add it under `[project.optional-dependencies].dev` if missing, and the helper must raise a loud `RssSamplerUnavailable("psutil required on macOS — install via `pip install -e '.[dev]'`")` rather than silently falling back to a `ps` parse that may differ across `ps` versions.
- **Fence-CI invocation must use the same script Phase 0 ships.** Per Global Rule 11 (Match the codebase's conventions). If Phase 0 named the script `tools/fence_ci.py`, the `run_fence_ci` fixture invokes that exact path; do not stub a parallel checker.
- **The synthetic-PR test does *not* commit anything to git** — it operates entirely in `tmp_path`. Fence-CI must support being pointed at an arbitrary tree (most fence-CI scripts do); if it strictly only walks `$CWD`, use `cwd=tmp_path` on the subprocess invocation.
- **Per Global Rule 9 (Tests verify intent, not just behavior):** the parametrized fence-CI test name encodes *why* — "fence_ci_rejects_denied_import_under_scope" — and the assertion message names both the import and the file, so a failure tells the reviewer exactly which gate broke. Do not collapse the parametrization into a single test.
- **Per Global Rule 12 (Fail loud):** if fence-CI is missing (e.g. Phase 0's script was renamed), `run_fence_ci` raises `FenceCiScriptMissing` rather than silently passing — the *worst* failure mode is a green CI that doesn't actually enforce G18.
- **The companion positive test (`test_fence_ci_accepts_clean_tree`) is not optional.** Without it, the negative tests could be silently failing-open if fence-CI is broken and rejects everything; the positive test bounds the gate's behavior on both ends.
