# Story S9-03 — Bench harness + 7-day rolling baseline

**Step:** Step 9 — CI gates, import-linter contracts, performance baselines, bench backfill hook
**Status:** HARDENED (validated 2026-05-20 — see [`_validation/S9-03-bench-harness-baseline.md`](_validation/S9-03-bench-harness-baseline.md))
**Effort:** M
**Depends on:** S9-01 (CI matrix + `make check`). The seven benches additionally require the components they measure — S2-01 + S7-01..S7-05 (`PluginRegistry` + the three loadable plugins), S3-02 (`VulnIndex`), S3-04 (`BundleBuilder`), S5-01 (`RecipeRegistry`), S6-01 (two-stream event log), S6-05 (`codegenie remediate`), S8-01/S8-02 (`express-cve-2024-21501/` fixture). As of 2026-05-20 those upstream stories are `HARDENED`, not `GREEN`; the executor must run the §0 precondition check and mark this story `BLOCKED` rather than stub the benches if any component is absent.
**ADRs honored:** ADR-0008 (`BundleBuilder` deterministic serial fallback + `vuln_index.digest` cache key — `bench_bundle_builder_{warm,cold}` measure the very property that ADR commits to), ADR-0005 (two-stream event log — `bench_event_appender_throughput` measures the spanning-stream write path under load), ADR-0002 (`PluginRegistry` kernel — `bench_plugin_registry_build` measures the kernel construction cost), ADR-0009 (`RecipeEngine` Protocol — `bench_recipe_match` measures the plugin-local `RecipeRegistry` iteration cost)

## Validation notes

Validated: 2026-05-20
Verdict: HARDENED
Findings addressed: 26 total — 6 blocks, 17 hardens, 3 nits

Changes applied:
- **Header** — `Status` → HARDENED; `Depends on` expanded from `S9-01` to the full upstream set, with a §0 precondition-check requirement (Consistency F5; mirrors S9-01/S8-04).
- **BLOCK — bench file naming** — the seven files are renamed `test_bench_*.py` (was `bench_*.py`). `pyproject.toml` does not override `python_files`, so a `bench_*.py` file is never pytest-collected and the `-m bench` collection guard would never see it. The verbatim bench *names* survive as the `record_and_assert` key + arch-doc identifier, decoupled from the file name (Consistency F3).
- **BLOCK — CI baseline persistence** — `actions/cache@v4` with a static key cannot accumulate a rolling window (cache entries are immutable per key). Rewritten to a unique-key-per-run + `restore-keys`-prefix pattern (Consistency F4 / Coverage F4).
- **BLOCK — `_helpers.py` collision** — `_helpers.py` already exists (S8-03 atomic merge writer). Sampling/quantile helpers go in a new `tests/bench/_sampling.py`; the rolling-baseline helper is `tests/bench/_rolling_baseline.py`, renamed from `_baseline.py` to avoid confusion with the existing `baselines/` directory (Consistency F2 / Design F2, F3).
- **BLOCK — signatures** — `record_and_assert` and `compute_rolling_mean` signatures pinned; the `units=` kwarg and `(bench_name, python_version)` filter args were missing / inconsistent between the ACs and the TDD plan (Coverage F1).
- **BLOCK — seed semantics** — "entry count" pinned to the *windowed* count; an all-stale window seeds; the `compute_rolling_mean → None` branch is now AC'd and tested (Coverage F2/F3, Test-Quality F3).
- **§Context / §References** — the stale "three files" `tests/bench/` inventory corrected; the three distinct bench CI surfaces enumerated; the existing `_helpers.py` / `_bench_kernel.py` / `baselines/` infrastructure referenced (Consistency F1, F6).
- **Test hardening** — the regression-diagnostic test now asserts the message names the %, the bench, and the values; a boundary test at exactly 1.25× added; the cross-contamination test made bidirectional; each bench AC gains a semantic assertion that it measures its named component; p-quantile sample counts raised for stability (Test-Quality F1, F2, F4, F5, F6).
- **Design** — `record_and_assert` decomposed into a pure `regression_verdict(...)` + impure shell; the `sample`/`quantile` helper promoted from §Refactor to an AC; the relationship to S8-03's `_bench_kernel.py` documented; the `1.25` threshold named as a `Final` constant (Design F1, F4, F5, F6).

Full audit log: [`_validation/S9-03-bench-harness-baseline.md`](_validation/S9-03-bench-harness-baseline.md)

## Context

Phase 3 commits to seven specific performance budgets (`phase-arch-design.md §Testing strategy / Performance regression budgets`). They are not aspirational; each names a load-bearing component and a budget the component must meet on `ubuntu-24.04` × Python 3.11 / 3.12. The seven:

| Bench | Budget |
|---|---|
| `bench_plugin_registry_build` | < 500 ms for 3 plugins |
| `bench_bundle_builder_warm` | < 5 ms |
| `bench_bundle_builder_cold` | < 300 ms |
| `bench_vuln_index_lookup` | < 10 ms p99 over 100 lookups |
| `bench_recipe_match` | < 60 ms p95 |
| `bench_event_appender_throughput` | > 30,000 events/sec |
| `bench_workflow_e2e_warm` | < 20 s p50, < 35 s p95 |

Absolute thresholds catch the catastrophic regressions but miss the slow creep. The relative-budget assertion is the complementary gate: a benchmark that runs in `0.8 × budget` today and `0.79 × budget` tomorrow does not trip the absolute, but a 30% slowdown still indicates a regression worth investigating. Phase 3 ships the **7-day rolling mean baseline + 25%-regression assertion**: every CI green run appends its measurement to `tests/bench/.baseline.json` keyed by `(bench_name, python_version)`; a new run computes the mean over the last 7 days' worth of entries and fails the bench job if the new measurement exceeds `1.25 × mean`. First-ever run seeds the baseline (no assertion); subsequent runs assert.

**The `tests/bench/` directory as it actually stands (post-Phase-2 S8-03), not the stale "three files" picture.** It holds three `@pytest.mark.bench` *marker* tests — `test_cache_hit_dispatch.py`, `test_cli_cold_start.py`, `test_coordinator_overhead.py` (run via `pytest tests/bench/ -m bench`) — **and also** S8-03's infrastructure: `_helpers.py` (the atomic `bench-results.json` merge writer — `merge_bench_result`, `bench_results_path`; do **not** repurpose this file), `_bench_kernel.py` (a shared bench kernel: pure `compare_to_baseline` + impure `post_comment_if`/`exit_with_verdict`), `baselines/` (committed, metadata-headed baseline JSONs guarded by `test_baseline_has_metadata.py`), three non-marker bench *scripts* run as `python tests/bench/bench_*.py`, and their smoke tests. The `@pytest.mark.bench` marker count is **still exactly 3** — that is what `bench-collection-guard` counts (`pytest --collect-only -m bench … | grep -c '::test_'`), and Phase 3 relaxes that guard from 3 to 10 (3 Phase 2 markers + 7 Phase 3 markers).

**There are three distinct bench CI surfaces today; this story touches only the first.** (a) The `bench-collection-guard` + `bench (advisory)` steps *inside* the `test` job (`.github/workflows/ci.yml` ~lines 128–151) — `-m bench`, `continue-on-error: true`. (b) A separate top-level `bench` job (Job 12, ~lines 480–522) that runs the non-marker scripts. (c) `bench-nightly.yml` — a nightly gating workflow for the hosted-runner script. The seven Phase 3 gating benches attach to surface (a): they are `@pytest.mark.bench` pytest tests in `test_bench_*.py` files, collected by `-m bench`, run by a **new gating step** alongside the existing advisory one. Surfaces (b) and (c) are out of scope (see §Out of scope).

**File name vs bench name.** The seven benchmark *names* are verbatim from `phase-arch-design.md §Testing strategy` (`bench_plugin_registry_build`, …) and are used as the `record_and_assert` key + `.baseline.json` key. The seven *file* names are `test_bench_<name>.py` — the `test_` prefix is mandatory because `pyproject.toml [tool.pytest.ini_options]` does not override `python_files` (default `test_*.py`); a `bench_*.py`-named file is never pytest-collected, so the `-m bench` guard would never count it. The verbatim name lives as a module-level `Final` string constant inside the file; the file itself is `test_bench_*.py`.

**The Phase 3 bench step is gating, not advisory:** `phase-arch-design.md §Testing strategy / Performance regression budgets` names this as a CI gate (`> 25% regression vs. 7-day rolling mean fails`). The Phase 2 `continue-on-error: true` shape does not carry forward to the seven Phase 3 benches; the three Phase 2 marker canaries stay advisory. Variance on shared GitHub runners is the known risk; mitigation is the multi-round sampling + quantile discipline pinned in the Implementation outline and ACs.

S9-01 wired the CI matrix and `make check`. This story lands the seven bench files, the baseline-recording harness (`tests/bench/_rolling_baseline.py` + `tests/bench/_sampling.py`), the relative-regression assertion, and the CI step that gates on the result.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy / Performance regression budgets` — the seven verbatim budgets above; relative-budget rule "> 25% regression vs. 7-day rolling mean fails."
  - `../phase-arch-design.md §Open questions deferred to implementation` ("CI runner concurrency tuning ... record the rolling-7-day baseline at first CI green") — this story owns the answer.
  - `../phase-arch-design.md §Implementation-level risks #1` (`bwrap` availability) — bench tests that depend on the jail (`bench_bundle_builder_cold`, `bench_workflow_e2e_warm`) fail if S9-01's `apt-get install -y bubblewrap` step is missing.
  - `../High-level-impl.md §Step 9 — Bench harness` — itemizes the seven bench files by exact path under `tests/bench/`.
- **Phase ADRs:**
  - `../ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md` — what `bench_bundle_builder_{warm,cold}` measure: warm hits the cache (key includes `vuln_index.digest`); cold misses and rebuilds.
  - `../ADRs/0005-two-stream-event-log-per-adr-0034.md` — the `fcntl.flock`-protected BLAKE3-chained spanning stream is what `bench_event_appender_throughput` measures under contention.
  - `../ADRs/0002-plugin-registry-kernel-instance-with-default-singleton.md` — the kernel `bench_plugin_registry_build` measures: filesystem walk → `importlib.import_module` × N → integrity check.
- **Existing code:**
  - `tests/bench/test_cache_hit_dispatch.py`, `test_cli_cold_start.py`, `test_coordinator_overhead.py` — Phase 2 bench pattern (`@pytest.mark.bench`, `time.perf_counter()` timing, JSON output). Mirror the shape — and note the *semantic* assertion in `test_cache_hit_dispatch.py` (`isinstance(warm_result.executions[...], CacheHit)`): a wall-clock budget alone cannot tell a working component from a no-op, so each Phase 3 bench must likewise assert on the *result* of the operation it times.
  - `tests/bench/_helpers.py` — S8-03's atomic `bench-results.json` merge writer. **Single-purpose; do not add sampling/quantile helpers here.** It does encode the project atomic-write discipline (tmp slot → `fsync` → `os.replace`) worth mirroring for the `.baseline.json` append.
  - `tests/bench/_bench_kernel.py` — S8-03's shared bench kernel. Its `compare_to_baseline` (pure) / `post_comment_if` (impure) split is the local functional-core/imperative-shell exemplar. **Read its docstring**: it compares against *committed, human-curated* baselines — a deliberately different mechanism from this story's *auto-rolling per-runner* baseline. §Notes documents why the two coexist.
  - `tests/bench/baselines/` + `test_baseline_has_metadata.py` — committed baseline JSONs with a mandatory metadata header. This story's `.baseline.json` is a *different* artifact (gitignored, per-runner, no metadata header) — the name proximity is why the helper is `_rolling_baseline.py`, not `_baseline.py`.
  - `.github/workflows/ci.yml § test job — "bench-collection-guard" and "bench (advisory)"` — the existing CI bench steps; this story relaxes the guard to 10 and adds a gating step alongside the advisory one (keep the Phase 2 canaries advisory; gate the seven Phase 3 names).
  - `pyproject.toml § [tool.pytest.ini_options]` — the `bench` marker is already declared (no new marker needed); `python_files` is **not** overridden, so the seven files must be `test_bench_*.py` for pytest to collect them.

## Goal

Land seven bench files under `tests/bench/` measuring the seven Phase 3 components against the verbatim budgets; ship a 7-day rolling baseline harness that records measurements per `(bench, python_version)` to `tests/bench/.baseline.json` and fails the CI bench job on > 25% regression vs. the rolling mean. The bench job is gating, not advisory, for the seven Phase 3 benchmarks (the three Phase 2 canaries remain advisory).

## Acceptance criteria

> **Naming convention (all seven bench files).** The *file* is `tests/bench/test_bench_<name>.py` — the `test_` prefix is mandatory for pytest collection (validator: was `bench_<name>.py`, which pytest never collects with the default `python_files` glob — Consistency F3). The *bench name* passed to `record_and_assert(...)` and used as the `.baseline.json` key is the verbatim `bench_<name>` string from `phase-arch-design.md §Testing strategy`, carried as a module-level `_BENCH_NAME: Final[str]`. File name ≠ bench name.

- [ ] **§0 precondition check (do this first).** Before writing any bench, verify the components under measurement are on disk and importable: `PluginRegistry` + the three plugin directories, `BundleBuilder`, `VulnIndex`, `RecipeRegistry`, the spanning event log (`codegenie.plugins.events`), `codegenie remediate`. If any is absent (upstream story still `HARDENED`, not `GREEN`), **stop**: mark this story `BLOCKED` with an `_attempts/` entry naming the missing component — do not stub or `xfail` the bench. (validator: added — Consistency F5; mirrors S9-01/S8-04.)
- [ ] `tests/bench/test_bench_plugin_registry_build.py` (NEW) constructs a fresh `PluginRegistry` and loads three plugins (vuln-node-npm + universal + `example--noop--*`). Asserts wall-clock < 500 ms (median of ≥ 5 samples) **and** asserts the registry holds 3 resolvable plugins (`len(registry.plugins) == 3`) so an empty/no-op build cannot pass the budget. Marker `@pytest.mark.bench`. (validator: added the semantic assertion — Test-Quality F5.)
- [ ] `tests/bench/test_bench_bundle_builder_warm.py` (NEW) pre-populates `.codegenie/cache/bundles/` (cache hit), then measures `BundleBuilder.build(...)`. Asserts < 5 ms (median of ≥ 5) **and** asserts the returned bundle was a cache hit (the warm path was actually taken, not a silent rebuild). (validator: added the semantic assertion — Test-Quality F5.)
- [ ] `tests/bench/test_bench_bundle_builder_cold.py` (NEW) clears the cache, runs `BundleBuilder.build(...)`. Asserts < 300 ms (median of ≥ 5) **and** asserts the build produced a non-empty bundle. Skips with a structured reason when `bwrap`/`bubblewrap` is not on `PATH` (reuse S9-01's `_bwrap_required(platform)` helper); on CI — where S9-01 installs `bubblewrap` — a skip is itself a failure, so assert the env so a silently-skipped CI bench is loud. (validator: added semantic assertion + `bwrap` skip-guard — Test-Quality F5, Coverage F5.)
- [ ] `tests/bench/test_bench_vuln_index_lookup.py` (NEW) runs 100 `VulnIndex.lookup(...)` calls; asserts p99 < 10 ms **and** asserts every lookup returned a non-`None` result (the index is populated, the lookups are real). (validator: added the semantic assertion — Test-Quality F5.)
- [ ] `tests/bench/test_bench_recipe_match.py` (NEW) iterates a plugin's `RecipeRegistry` against a synthetic `Plan`; asserts p95 < 60 ms over ≥ 50 samples **and** asserts the match returned the expected recipe id (the iteration actually matched, not a no-op miss). (validator: sample count 20 → 50 for a stable p95; added semantic assertion — Test-Quality F5, F6.)
- [ ] `tests/bench/test_bench_event_appender_throughput.py` (NEW) emits ≥ 100k events in a tight loop to the **spanning** stream (single-process; `fcntl.flock` round-trip per emit per ADR-0005); asserts throughput > 30,000 events/sec **and** asserts the resulting BLAKE3 chain has ≥ 100k links (the events were actually appended, the chain extended). (validator: added the semantic assertion — Test-Quality F5.)
- [ ] `tests/bench/test_bench_workflow_e2e_warm.py` (NEW) runs `codegenie remediate` against the `express-cve-2024-21501/` fixture with caches pre-warmed; asserts p50 < 20 s and p95 < 35 s over ≥ 5 samples **and** asserts the workflow reached a `validated` `RemediationOutcome` (a workflow that errored fast would otherwise pass the budget). Skips with a structured reason when `bwrap` is absent; a CI skip is a failure (as `test_bench_bundle_builder_cold.py`). Warm-up: a session-scoped `conftest.py` fixture primes the bundle cache via one `BundleBuilder.build(...)` and constructs an npm offline cache by running `npm install --prefer-offline` into a `tmp_path`-rooted directory **before** the timed region — the npm cache is constructed per session, **not** committed to the repo. (validator: pinned the warm-up mechanism, removed the "committed-or-constructed" ambiguity, added the semantic assertion + `bwrap` skip-guard — Coverage F6, F5, Test-Quality F5.)
- [ ] `tests/bench/_sampling.py` (NEW) — shared sampling helper so the seven bench files do not each inline a sample loop: `sample(operation: Callable[[], object], n: int) -> list[float]` (wall-clock deltas via `time.perf_counter()`, one untimed warm-up call before the loop) and `quantile(samples: list[float], q: float) -> float` (thin wrapper over `statistics.quantiles`). p-quantile benches assert against the quantile; single-shot benches (`bench_plugin_registry_build`, `bench_bundle_builder_{warm,cold}`, `bench_event_appender_throughput`) take ≥ 5 samples and assert against the **median** (not min — hides regressions; not max — trips on noise). (validator: promoted from §Refactor to an AC — the helper crosses rule-of-three at seven consumers, Design F5; placed in a new module, not the single-purpose `_helpers.py`, Design F2.)
- [ ] `tests/bench/_rolling_baseline.py` (NEW) — rolling-baseline helper. **Pure core:** `regression_verdict(measurement: float, rolling_mean: float, *, threshold: float = _REGRESSION_THRESHOLD) -> RegressionVerdict` — a filesystem-free decision returning a tagged result (`WithinBudget | Regression`, the `Regression` variant carrying `measurement`, `rolling_mean`, and the computed `regression_pct` so the diagnostic can name them); `compute_rolling_mean(entries: list[dict], bench_name: str, python_version: tuple[int, int], *, days: int = 7) -> float | None` — filters `entries` to those matching `(bench_name, python_version)` **and** recorded within the last `days`, returns their mean, or `None` when that windowed set is empty. **Impure shell:** `load_baseline(path) -> list[dict]` (empty list if missing); `record_and_assert(bench_name: str, measurement: float, *, units: str, python_version: tuple[int, int] = sys.version_info[:2], baseline_path: Path = ...) -> None`. (validator: signatures pinned — `units` was used in the TDD plan but missing from the AC signature; `compute_rolling_mean` was missing its `bench_name`/`python_version` filter args; decomposed into pure `regression_verdict` + impure shell — Coverage F1, Design F4.)
- [ ] `record_and_assert(...)` behavior, pinned: (1) it **always** appends the new `{bench_name, python_version, measurement_value, units, recorded_at_iso_utc}` entry to `.baseline.json` — seeding and asserting both persist the measurement; (2) it computes the rolling mean via `compute_rolling_mean(...)`; (3) if that mean is `None` — i.e. the **windowed** entry set (entries matching `(bench_name, python_version)` within 7 days) is empty, *including* the case where only stale >7-day entries exist — this is a **seed run**: append only, no assertion; (4) otherwise it calls `regression_verdict(...)` and on a `Regression` raises `AssertionError` whose message names the bench, the measurement, the rolling mean, and the regression %. (validator: "entry count < 1" pinned to the *windowed* count; all-stale-window seeds; always-append pinned; diagnostic contents pinned — Coverage F2, F7, Test-Quality F1.)
- [ ] `tests/bench/.baseline.json` (NEW, gitignored) is created on first CI green; subsequent runs append. Schema documented in the `tests/bench/_rolling_baseline.py` docstring (entries: `{bench_name, python_version, measurement_value, units, recorded_at_iso_utc}`). It is a *different artifact* from the committed `baselines/*.json` — gitignored, per-runner, and carries **no** metadata header; the docstring states this so a future contributor does not apply `test_baseline_has_metadata.py`'s header contract to it. (validator: clarified the relationship to `baselines/` — Design F1, F3.)
- [ ] Each of the seven bench files calls `record_and_assert(_BENCH_NAME, ...)` after asserting its absolute budget and its semantic assertion — all gates must pass. The bench *name* argument is the verbatim `bench_<name>` string (the module-level `Final` constant), never the file name. (validator: name-vs-file pinned — Consistency F3.)
- [ ] `.github/workflows/ci.yml § test job — bench-collection-guard` is updated from `-ne 3` to `-ne 10` (3 Phase 2 markers + 7 Phase 3 markers). The seven Phase 3 bench tests are wired into a **new gating step** (`continue-on-error: false`) that runs only the seven `test_bench_*.py` files by explicit path; the Phase 2 three-marker `bench (advisory)` step keeps `continue-on-error: true`. (validator: clarified marker-count vs file-name; gating step runs the seven by explicit path — Consistency F3, F6.)
- [ ] CI persists `tests/bench/.baseline.json` across runs via `actions/cache@v4` with an **accumulating** key shape: primary `key: bench-baseline-${{ runner.os }}-${{ matrix.python }}-${{ github.run_id }}` (unique per run — always a cache miss, so the post-job save **always** writes the updated file) plus `restore-keys: bench-baseline-${{ runner.os }}-${{ matrix.python }}-` (restores the most-recent prior baseline at job start). A *static* key (e.g. `…-v1`) must **not** be used: `actions/cache` never overwrites an existing key, so a static key would freeze `.baseline.json` at the first run's single entry, the 7-day window would never accumulate, and the regression assertion would be permanently dead. `runner.os` + `matrix.python` in the key keep 3.11 and 3.12 baselines from cross-contaminating. (validator: BLOCK — the originally-recommended static-key `actions/cache` shape cannot implement a rolling baseline — Consistency F4, Coverage F4.)
- [ ] `tests/unit/test_ci_workflow.py` (existing) asserts: the bench-collection-guard count is `10`; the new gating bench step exists with `continue-on-error: false` and names the seven Phase 3 `test_bench_*.py` files; the Phase 2 `bench (advisory)` step still has `continue-on-error: true`; the `actions/cache@v4` step uses a `${{ github.run_id }}`-suffixed (non-static) key with a `restore-keys` prefix. (validator: added the gating-chain + cache-key assertions — Coverage F8, Consistency F4.)
- [ ] `mypy --strict` clean on `tests/bench/_rolling_baseline.py` + `tests/bench/_sampling.py` + the seven bench files; `ruff check`, `ruff format --check` clean on all touched files. (validator: named the modules explicitly.)
- [ ] TDD plan's red tests exist, committed, fail for the stated reason, then green.

## Implementation outline

1. **`tests/bench/_rolling_baseline.py`.** Pure-Python, no third-party deps. **Pure core:** `regression_verdict(measurement, rolling_mean, *, threshold=_REGRESSION_THRESHOLD) -> RegressionVerdict`, where `RegressionVerdict` is a tagged union (`WithinBudget | Regression(measurement, rolling_mean, regression_pct)` — a frozen-dataclass pair or a `Literal`-discriminated pair); filesystem-free, so unit-testable without `tmp_path`. `compute_rolling_mean(entries, bench_name, python_version, *, days=7) -> float | None` — filter by `(bench_name, python_version)` and `datetime.fromisoformat(...) >= now - timedelta(days=days)`, return the mean or `None` if that windowed set is empty. **Impure shell:** `load_baseline(path) -> list[dict]`; `record_and_assert(...)` composes load → append → `compute_rolling_mean` → (`None` ⇒ seed, return) / `regression_verdict` → raise on `Regression`. `_REGRESSION_THRESHOLD: Final[float] = 1.25` is a module-level constant with a comment citing `phase-arch-design.md §Testing strategy` (not configurable — see §Notes). The `.baseline.json` append uses the atomic tmp-replace technique from `_helpers.py` (write a unique `.tmp` slot → `fsync` → `os.replace`) so a runner killed mid-append cannot leave a half-written file. Keep it tight (~110 LoC).
2. **`tests/bench/_sampling.py`.** `sample(operation, n) -> list[float]` (one untimed warm-up call, then `n` `time.perf_counter()` deltas) and `quantile(samples, q) -> float`. Both pure. The seven bench files import from here — no inlined sample loops.
3. **Seven bench files** named `tests/bench/test_bench_<name>.py`. Mirror the Phase 2 `test_cache_hit_dispatch.py` shape: one `@pytest.mark.bench` test per file; a module-level `_BENCH_NAME: Final[str] = "bench_<name>"`; collect samples via `_sampling.sample(...)`; assert the absolute budget against the median (single-shot) or the quantile (p-budget); assert the *semantic* result of the timed operation (see each AC); then `record_and_assert(_BENCH_NAME, ...)`. Sample counts: ≥ 50 for the p95 bench, 100 for `bench_vuln_index_lookup` (p99), ≥ 5 for `bench_workflow_e2e_warm`, ≥ 5 (median) for the single-shot benches.
4. **`bench_workflow_e2e_warm`'s warm-up.** A session-scoped `conftest.py` fixture primes the bundle cache via one `BundleBuilder.build(...)` and constructs an npm offline cache by running `npm install --prefer-offline` into a `tmp_path`-rooted directory — both **outside** the timed region. The npm cache is constructed per session, never committed (committed `node_modules`-shaped fixtures rot). Without warm-up the 20 s p50 budget is unmeetable; `bench_bundle_builder_cold` separately owns the cold path.
5. **Baseline file lifecycle.** `tests/bench/.baseline.json` in `.gitignore` (per-runner state, *not* a committed `baselines/*.json`). CI persists it with `actions/cache@v4`: primary `key` suffixed `${{ github.run_id }}` (unique → the post-job save always writes), `restore-keys: bench-baseline-${{ runner.os }}-${{ matrix.python }}-` (restores the latest prior). A static key is wrong — `actions/cache` will not overwrite an existing key, so the window would never grow. `runner.os` + `matrix.python` segregate 3.11 / 3.12.
6. **CI integration.** In `.github/workflows/ci.yml`: keep the Phase 2 `bench (advisory)` step (`-m bench`, three markers, `continue-on-error: true`); bump `bench-collection-guard` from `-ne 3` to `-ne 10`; add a new `bench (gating)` step running the seven `test_bench_*.py` files by explicit path with `continue-on-error: false`; add the `actions/cache@v4` restore/save around them. Do **not** touch the separate top-level `bench` job or `bench-nightly.yml` (out of scope). Verify the matrix entries inherited from S9-01 are in effect.
7. **Variance mitigation.** Each bench warms by running the operation once outside the timing region (eliminates first-import / first-syscall cost). p-quantile benches take ≥ 50 (p95) / 100 (p99) samples and assert the quantile; single-shot benches take ≥ 5 and assert the **median** — never the single best (min hides regressions) or worst (max trips on noise) run.

## TDD plan — red / green / refactor

### Red — write the failing tests first
Helper modules: `tests/bench/_rolling_baseline.py`, `tests/bench/_sampling.py`. Unit-test file: `tests/bench/test_baseline_unit.py`.

```python
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.bench._rolling_baseline import (
    Regression,
    WithinBudget,
    compute_rolling_mean,
    record_and_assert,
    regression_verdict,
)


def _entry(bench: str, val: float, days_ago: float, py: tuple[int, int] = (3, 11)) -> dict:
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return {
        "bench_name": bench,
        "python_version": list(py),
        "measurement_value": val,
        "units": "ms",
        "recorded_at_iso_utc": ts.isoformat(),
    }


# --- compute_rolling_mean -------------------------------------------------

def test_rolling_mean_excludes_entries_older_than_7_days() -> None:
    entries = [_entry("b", 100.0, 1), _entry("b", 200.0, 3), _entry("b", 999.0, 10)]
    mean = compute_rolling_mean(entries, "b", (3, 11), days=7)
    assert mean == pytest.approx(150.0)  # 999 excluded; (100+200)/2


def test_rolling_mean_returns_none_when_window_all_stale() -> None:
    """Why: an all->7-day-old window must yield None so record_and_assert
    takes the SEED branch. An impl that returns 0.0 instead would make every
    measurement fail `<= 1.25 * 0` — it must be caught here."""
    entries = [_entry("b", 999.0, 30), _entry("b", 999.0, 100)]
    assert compute_rolling_mean(entries, "b", (3, 11), days=7) is None


def test_rolling_mean_returns_none_for_unknown_bench() -> None:
    assert compute_rolling_mean([_entry("a", 100.0, 1)], "b", (3, 11), days=7) is None


def test_rolling_mean_keys_on_python_version() -> None:
    """Why: a 3.12 measurement must not enter 3.11's mean — different
    interpreters have systematically different cost. An impl that ignores
    python_version would average 50 and 100 to 75 and fail this."""
    entries = [_entry("b", 50.0, 1, py=(3, 12)), _entry("b", 100.0, 1, py=(3, 11))]
    assert compute_rolling_mean(entries, "b", (3, 11), days=7) == pytest.approx(100.0)


# --- regression_verdict (pure — no filesystem) ---------------------------

def test_regression_verdict_within_budget_at_exactly_threshold() -> None:
    """Why: AC spec is `measurement <= 1.25 * mean` — exactly 1.25x is
    WITHIN budget. Pins the inclusive boundary so a `<` mutation is caught."""
    assert isinstance(regression_verdict(125.0, 100.0), WithinBudget)


def test_regression_verdict_flags_just_over_threshold() -> None:
    v = regression_verdict(126.0, 100.0)
    assert isinstance(v, Regression)
    assert v.regression_pct == pytest.approx(26.0)  # 126/100 - 1 -> 26%


# --- record_and_assert (impure shell) ------------------------------------

def test_record_and_assert_seeds_on_empty_baseline(tmp_path: Path) -> None:
    """Why: first-ever CI green must seed without failing — no baseline to
    compare against (phase-arch-design.md §Open questions)."""
    bp = tmp_path / "baseline.json"
    bp.write_text("[]")
    record_and_assert("b", 100.0, units="ms", baseline_path=bp)  # must not raise
    assert len(json.loads(bp.read_text())) == 1


def test_record_and_assert_seeds_when_all_history_is_stale(tmp_path: Path) -> None:
    """Why: a baseline holding only >7-day-old entries has an empty WINDOW —
    it must seed, not assert against a None mean. And it must still append."""
    bp = tmp_path / "baseline.json"
    bp.write_text(json.dumps([_entry("b", 100.0, 30), _entry("b", 100.0, 99)]))
    record_and_assert("b", 9999.0, units="ms", baseline_path=bp)  # must not raise
    assert len(json.loads(bp.read_text())) == 3  # always appends


def test_record_and_assert_fails_on_25_percent_regression(tmp_path: Path) -> None:
    """Why: the cardinal Phase 3 regression rule. The diagnostic must be
    operator-actionable — it names the bench, the measurement, the mean,
    and the regression % (a bare "regression" string is not enough)."""
    bp = tmp_path / "baseline.json"
    bp.write_text(json.dumps([_entry("b", 100.0, 1) for _ in range(3)]))
    with pytest.raises(AssertionError) as exc:
        record_and_assert("b", 126.0, units="ms", baseline_path=bp)
    msg = str(exc.value)
    assert "b" in msg                                  # bench name
    assert "126" in msg                                # measurement
    assert "100" in msg                                # rolling mean
    assert "26" in msg                                 # regression %


def test_record_and_assert_accepts_at_exactly_threshold(tmp_path: Path) -> None:
    """Why: `<= 1.25 * mean` — exactly 125.0 vs mean 100.0 must PASS. Brackets
    the boundary together with the 126.0 test so a `<`/`<=` mutation is caught."""
    bp = tmp_path / "baseline.json"
    bp.write_text(json.dumps([_entry("b", 100.0, 1) for _ in range(3)]))
    record_and_assert("b", 125.0, units="ms", baseline_path=bp)  # must not raise


def test_record_and_assert_accepts_within_25_percent(tmp_path: Path) -> None:
    bp = tmp_path / "baseline.json"
    bp.write_text(json.dumps([_entry("b", 100.0, 1) for _ in range(3)]))
    record_and_assert("b", 124.0, units="ms", baseline_path=bp)  # must not raise


def test_python_versions_do_not_cross_contaminate(tmp_path: Path) -> None:
    """Why: 3.12 measurements must not poison 3.11's baseline, and a 3.11
    write must not touch the 3.12 entry — asserts BOTH directions, so an
    impl that ignores python_version entirely is caught."""
    bp = tmp_path / "baseline.json"
    bp.write_text(json.dumps([_entry("b", 50.0, 1, py=(3, 12))]))
    # 3.11 sees an empty window -> seeds; no regression assertion.
    record_and_assert("b", 1000.0, units="ms", baseline_path=bp, python_version=(3, 11))
    data = json.loads(bp.read_text())
    by_py = {tuple(e["python_version"]): e["measurement_value"] for e in data}
    assert by_py[(3, 12)] == 50.0      # 3.12 entry untouched
    assert by_py[(3, 11)] == 1000.0    # 3.11 seeded independently
    assert len(data) == 2              # no merge across interpreters
```

State why it fails: `tests/bench/_rolling_baseline.py` and `tests/bench/_sampling.py` do not exist; the seven `test_bench_*.py` files do not exist; the bench-collection-guard count is 3.

### Green — minimal pass
- Write `tests/bench/_rolling_baseline.py` and `tests/bench/_sampling.py` to satisfy the unit tests.
- Write the seven `tests/bench/test_bench_*.py` files. Each declares `_BENCH_NAME: Final[str] = "bench_<name>"` and calls `record_and_assert(_BENCH_NAME, ...)` after its absolute + semantic assertions. Do **not** derive the name from `__name__` — the file is `test_bench_*` and the name is `bench_*`; they differ by design.
- Update `.github/workflows/ci.yml`: collection-guard `-ne 3` → `-ne 10`; add the gating bench step; add the `actions/cache@v4` restore/save with the run-id-suffixed key + `restore-keys` prefix.
- Update `tests/unit/test_ci_workflow.py` for the new collection-guard count, the gating-step shape, and the cache-key shape.

### Refactor
- The sample/quantile helper is `tests/bench/_sampling.py` — an AC, not a refactor afterthought (it has seven consumers from day one). Do **not** add it to `_helpers.py` (that file is S8-03's atomic merge writer — single purpose).
- Add a `make bench` Makefile target running `pytest tests/bench/ -m bench --no-cov` for local pre-flight (optional convenience — `bwrap`-dependent benches skip locally on macOS).
- Document the baseline-cache key + invalidation policy in the `_rolling_baseline.py` docstring (a `restore-keys`-prefix change = baseline reset; runners that find no prior cache see "seed" behavior, which is correct).
- Edge case: variance on shared CI runners (the documented Phase 2 risk). Mitigation: multi-sample + quantile/median, never single-run min/max. If a bench is chronically flaky on `ubuntu-24.04`, surface it (do not weaken the assertion) and pick retry-tactic vs budget-amend via an ADR amendment.

## Files to touch

| Path | Why |
|---|---|
| `tests/bench/_rolling_baseline.py` | NEW — rolling-baseline helper: pure `regression_verdict` + `compute_rolling_mean`; impure `load_baseline` + `record_and_assert`. |
| `tests/bench/_sampling.py` | NEW — shared `sample(...)` + `quantile(...)` helpers (seven consumers; do NOT use the existing single-purpose `_helpers.py`). |
| `tests/bench/test_baseline_unit.py` | NEW — unit tests for the rolling-baseline helper. |
| `tests/bench/conftest.py` | NEW (or extend) — session-scoped warm-up fixture for `test_bench_workflow_e2e_warm.py` (bundle-cache prime + constructed npm offline cache). |
| `tests/bench/test_bench_plugin_registry_build.py` | NEW — kernel build < 500 ms; asserts 3 plugins resolved. |
| `tests/bench/test_bench_bundle_builder_warm.py` | NEW — cache-hit < 5 ms; asserts the warm path was taken. |
| `tests/bench/test_bench_bundle_builder_cold.py` | NEW — cache-miss < 300 ms; `bwrap`-skip-guarded. |
| `tests/bench/test_bench_vuln_index_lookup.py` | NEW — p99 < 10 ms over 100 lookups; asserts non-None results. |
| `tests/bench/test_bench_recipe_match.py` | NEW — p95 < 60 ms over ≥ 50 samples; asserts the expected recipe matched. |
| `tests/bench/test_bench_event_appender_throughput.py` | NEW — > 30k events/sec to the spanning stream; asserts the BLAKE3 chain extended. |
| `tests/bench/test_bench_workflow_e2e_warm.py` | NEW — e2e p50 < 20 s, p95 < 35 s; `bwrap`-skip-guarded; asserts a `validated` outcome. |
| `.gitignore` | Add `tests/bench/.baseline.json` (per-runner state). |
| `.github/workflows/ci.yml` | Bump collection-guard `-ne 3` → `-ne 10`; add the gating bench step; add `actions/cache@v4` with a run-id-suffixed key + `restore-keys` prefix. Do NOT touch the top-level `bench` job or `bench-nightly.yml`. |
| `tests/unit/test_ci_workflow.py` | Update collection-guard assertion; assert the gating-step shape and the non-static cache-key shape. |
| `Makefile` (optional) | Add a `bench` convenience target. |

## Out of scope

- **`BenchReplayable` event payload + Phase 6.5 backfill** — owned by S9-04.
- **`docs/operations/phase03-runbook.md`** — owned by S9-04.
- **Macroscopic optimization** — if a bench fails its absolute budget, this story does NOT include a perf investigation; surface the regression and open a follow-up. The baseline assertion catches creep; budget violations are a separate diagnostic loop.
- **Microbenchmark for `TrustScorer.score`** — the seven listed budgets are exhaustive for Phase 3. `TrustScorer.score` is dominated by `npm install` + `npm test` wall-clock (already covered by `bench_workflow_e2e_warm`).
- **Comparing Phase 3 perf to Phase 2** — Phase 2's three bench canaries remain advisory and are separately scoped.
- **The separate top-level `bench` job + `bench-nightly.yml`** — Phase 2's S8-03 bench *scripts* (`bench_portfolio_walltime.py` etc., run as `python tests/bench/...`) and their nightly gating workflow are a distinct CI surface. This story neither edits nor extends them; the seven Phase 3 benches attach only to the `-m bench` surface inside the `test` job.
- **Postgres-backed baseline persistence** — Phase 9 may move the rolling baseline into the production-side event store; Phase 3 ships the JSON-file shape.

## Notes for the implementer

- **Benchmark name vs file name.** The seven benchmark *names* are verbatim from `phase-arch-design.md §Testing strategy` (`bench_plugin_registry_build`, …) — they are the `record_and_assert` key and the `.baseline.json` key; drift breaks baseline matching. Carry each as a module-level `_BENCH_NAME: Final[str]`. The *file* name is `test_bench_<name>.py` — the `test_` prefix is **mandatory** so pytest collects the file (`pyproject.toml` does not override `python_files`; the default glob is `test_*.py`). A `bench_*.py`-named file is invisible to `pytest --collect-only -m bench`, so the collection guard would never count it. (validator: corrected — the original note claimed the `bench_` prefix made the guard count them, which is exactly backwards.)
- **Two baseline mechanisms now coexist in `tests/bench/` — deliberately.** S8-03's `_bench_kernel.py` compares against *committed, human-curated* baselines (`baselines/*.json`, metadata header, refresh-by-PR ritual, `compare_to_baseline`). This story's `_rolling_baseline.py` is an *auto-rolling, per-runner, gitignored* baseline (7-day window, no human in the loop). They are not duplicates — one is curated, one is automatic — and must not be merged. Do not route the Phase 3 rolling benches through `_bench_kernel.compare_to_baseline`, and do not give `.baseline.json` the metadata header `test_baseline_has_metadata.py` enforces on `baselines/*.json`. The `_rolling_baseline.py` docstring must state this relationship so the next maintainer can tell the two systems apart. (validator: Design F1.)
- **Functional core / imperative shell.** `regression_verdict` and `compute_rolling_mean` are pure (no filesystem; the time window is derived from an injected-or-`now` timestamp) — they are unit-tested without `tmp_path`. Only `load_baseline` and `record_and_assert` touch disk. This mirrors `_bench_kernel.py`'s `compare_to_baseline` (pure) / `post_comment_if` (impure) split — the project-wide convention. (validator: Design F4.)
- **Atomic `.baseline.json` append.** `record_and_assert`'s append must use the tmp-slot → `fsync` → `os.replace` technique `_helpers.merge_bench_result` already encodes — a plain `write_text` risks a half-written `.baseline.json` if a runner is killed mid-append. The shapes differ (list-append vs key-overlay) so do not share code with `_helpers.py`; mirror the technique only. (validator: Design F7.)
- **`pytest-benchmark` is tempting but not required.** The Phase 2 bench files use `time.perf_counter()` directly; mirror that for consistency. `pytest-benchmark`'s rich output is nice-to-have, not load-bearing for the 25%-regression assertion.
- **`_REGRESSION_THRESHOLD` is a named constant, not configurable.** The 25% threshold is `_REGRESSION_THRESHOLD: Final[float] = 1.25` in `_rolling_baseline.py`, with a comment citing `phase-arch-design.md §Testing strategy`. Operators who want to widen it amend that architecture section — they do not tweak a constant or pass a parameter. No env var, no config surface: the named constant documents intent, that is the whole fix. (validator: was "hard-coded in `record_and_assert`" — named the constant; Design F6.)
- **Baseline persistence — the cache key must be unique per run.** `actions/cache@v4` only writes a cache entry on a *miss*; an existing key is never overwritten. So the primary `key` must be unique per run (`…-${{ github.run_id }}`) — that guarantees a miss and therefore a post-job save — paired with `restore-keys: bench-baseline-${{ runner.os }}-${{ matrix.python }}-` to restore the latest prior baseline. A static key (`…-v1`) would freeze `.baseline.json` after run 1 and the rolling window would never grow — the 25%-regression assertion would be permanently dead. Operators running locally pass `baseline_path` to the helper to point at a separate file. (validator: BLOCK — the original static-key recommendation cannot accumulate a rolling baseline; Consistency F4 / Coverage F4.)
- **`bench_event_appender_throughput` measures the spanning stream specifically.** The per-workflow `internal` stream does NOT use `fcntl.flock` (per-workflow file; no cross-process contention) and would benchmark differently. The 30k events/sec budget applies to the spanning stream — that is what S6-01's BLAKE3 chain + `fcntl.flock` round-trip has to sustain.
- **`bench_workflow_e2e_warm` budget includes `npm install` + `npm test`.** Those wall-clocks dominate; if the budget feels tight, verify the warmup (pre-warmed bundle cache + `--prefer-offline` npm) is in effect. Without warmup the budget is wildly unmeetable; with warmup it's the floor + a few hundred ms of orchestrator overhead.
- **Variance is the enemy.** Multi-sample + quantile is the right answer for the four benches with p-quantile budgets. For single-shot benches (`bench_plugin_registry_build`, `bench_bundle_builder_{warm,cold}`, `bench_event_appender_throughput`), take 5+ samples and assert against the median (not the minimum, not the maximum) — minimum hides regressions, maximum trips on noise.
- **The collection-guard bump 3 → 10 is the single brittle integration point with S9-01.** If S9-01 already bumped it (or restructured), reconcile against `test_ci_workflow.py` and document which story owns the count.
