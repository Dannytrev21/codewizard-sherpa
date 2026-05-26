# Story S7-02 — Performance regression gates (latency + retry-2 budget)

**Step:** Step 7 — Adversarial test suite + performance regression gates
**Status:** Ready (HARDENED 2026-05-25)
**Effort:** M
**Depends on:** S5-02 (`GateRunner`), S5-05 (`breaking-change-cve` fixture + cassette + `_helpers/vcr.py` + `_helpers/hooks.py`), S2-01 (`Attempt.started_at`/`ended_at` on `attempts.jsonl`), S1-04 (`GateContext`), S7-01 (`tests/_helpers/fixtures.py::apply_fixture_patch`)
**ADRs honored:** ADR-0004 (DiD default macOS — budgets are DiD-pinned), ADR-0011 (no verdict cache in Phase 5 — retry-2 budget assumes full re-run)

## Validation notes (2026-05-25)

This story was hardened by the phase-story-validator before execution. The original draft expressed the right goals (the §Goal 10 latency budgets and §Goal 11 retry-2 ratio verbatim) but its TDD plan invoked two phantom APIs S5-02 HARDENED has already locked away, wired sync `def test_*` against `async def run`, pointed at the wrong cassette layout, and prescribed a quantile computation that is statistically vacuous at N=5. The flake-rate math is inconsistent ("≤ 1 % up to 1/50" — 1/50 is 2 %). The story also rolled its own `Threshold` while ignoring `tests/bench/_bench_kernel.py`, which already ships `Threshold` + `Verdict` and is the established extraction site (three existing consumers — past rule-of-three). Full audit at [`_validation/S7-02-perf-regression-gates.md`](_validation/S7-02-perf-regression-gates.md). Summary:

- **`§GateRunner construction` (block).** Per [S5-02 HARDENED AC-CTOR-1](S5-02-gate-runner-retry-loop.md): the only constructor is keyword-only `GateRunner(*, client, gate, ledger, spec_builder, max_attempts=3, replan_hook=None)` — there is no `from_default_catalog(repo=...)` factory. Fix: shared `perf_gate_runner_factory` fixture in `tests/perf/conftest.py` mirroring S5-05's `tests/integration/gates/conftest.py` precedent. AC-CTOR-1.
- **`§GateRunner.run signature` (block).** Per [S5-02 HARDENED AC-RUN-CTX-1](S5-02-gate-runner-retry-loop.md): the only method is `async def run(self, ctx: GateContext) -> GateOutcome` — there is no `run_single_gate(gate_id=...)`. `gate_id` is the `Gate.id` attribute owned by the gate instance; the runner is constructed per-gate. Fix: AC-RUN-CTX-1 — perf test constructs one runner per `gate_id`, threads a real `GateContext`. Adding a thin wrapper around `run` is **out of scope** (S5-02 owns the API).
- **`§async surface` (block).** Per [S5-02 HARDENED AC-ASYNC-1](S5-02-gate-runner-retry-loop.md): `inspect.iscoroutinefunction(GateRunner.run) is True`. Sync `def test_*` binds a coroutine; assertions vacuously succeed. Fix: AC-ASYNC-1 — every perf test is `async def`. Project's `asyncio_mode = "auto"` makes `@pytest.mark.asyncio` redundant.
- **`§cassette layout` (block).** Per [S5-05 HARDENED line 108](S5-05-retry-recovers-integration.md): the actual cassette is the SINGLE FILE `tests/integration/gates/cassettes/stage6_retry_recovers.yaml` (one cassette, two recorded `interactions` in order — NOT two separate cassettes). The draft's `tests/fixtures/vcr/cassette-attempt-{1,2}.yaml` paths do not exist. Fix: AC-CASSETTE-1 + AC-CASSETTE-INTERACT-1.
- **`§fixture ownership` (block).** The `breaking-change-cve` fixture is owned by **Phase 5 / S5-05**, NOT "Phase 4 / S5-05" (Phase 4 has no S5-05). Fix: References row corrected.
- **`§p95 quantile arithmetic` (block).** `statistics.quantiles(samples, n=20)[18]` with N=5 samples is statistically vacuous — exclusive quantiles can raise `StatisticsError` or interpolate garbage between adjacent ventiles when N < 7. Fix: AC-P95-1 — define p95 as `max(samples)` for N=5 via a `_p95_for_small_n` helper with a comment explaining the architectural choice (small N for cost; tight upper bound for safety). Future-proof: when CI runner stabilizes, lift N to ≥ 20 and switch to `quantiles(..., n=20, method='inclusive')[18]`.
- **`§flake-rate arithmetic` (harden).** "≤ 1 % (up to 1/50 tolerated)" is inconsistent — 1/50 = 2 %. Fix: AC-FLAKE-1 takes the strict reading per High-level-impl Step 7 done-criteria #2 — **0 failures over 50 runs** is the gate; tolerated-flake language removed. Editorial amendment for `High-level-impl.md §Step 7` is flagged in Notes for the implementer #5 (out of scope for this story).
- **`§bench-kernel reuse missed` (block — design).** `tests/bench/_bench_kernel.py` already exports `Threshold` + `Verdict` (`Ok | CommentOnly | Fail`) — a tagged-union verdict with a pure `compare_to_baseline(measurements, baseline, thresholds, *, p95_seconds)` decision. Three existing consumers (`bench_portfolio_walltime`, `bench_index_health_overhead`, `bench_portfolio_walltime_hosted_runner`) put `test_gate_latency` at the fourth, well past rule-of-three. Fix: AC-KERNEL-1 + AC-KERNEL-2.
- **`§pyproject addopts extension` (block).** Setting `addopts = "-m 'not perf'"` would **replace** the existing `-m "not bench and not phase_7_preview"` and silently re-enable bench + phase-7 tests in default CI. Fix: AC-ADDOPTS-1 extends to `-m "not bench and not phase_7_preview and not perf"`; AC asserts substring preservation.
- **`§strict-markers compliance` (harden).** Project uses `--strict-markers`; unregistered `perf`/`slow` marks raise at collection. Fix: AC-MARKER-1 — extend `[tool.pytest.ini_options] markers` rows.
- **`§trend-row schema` (harden — design).** The JSONL row was a dict — primitive obsession on `git_sha` (raw `str`), no validation, no `extra='forbid'`. Future consumers will defensively `dict.get(...)`. Fix: AC-SCHEMA-1 / AC-SCHEMA-2 — `LatencySample` and `RetryBudgetSample` Pydantic models (`frozen=True, extra='forbid'`); NewType identifiers (`WorkflowId`, `RunId`, `SignalKind`); `RunnerName: Literal[...]` closed set.
- **`§functional core / imperative shell` (harden — design).** `record_sample(path, row)` mixed pure (row construction) with impure (file append). Fix: AC-PURE-1 — split `to_jsonl_line(model) -> str` (pure) + `append_jsonl_line(path: Path, line: str) -> None` (impure shell). AC-FCIS-1 AST-scan asserts `tests/perf/conftest.py` is the only impure module under `tests/perf/`.
- **`§retry-2 wall source` (harden).** "Wrap GateRunner.run or read from attempts.jsonl" is ambiguous. The arch (Component 5) + S2-01 HARDENED commit `Attempt.started_at`/`ended_at` to the artifact contract. Reading the artifact is the only stable contract. Fix: AC-RETRY-SRC-1 — wall-clock comes from `Attempt.ended_at - Attempt.started_at`, not from `time.monotonic_ns()` outside the runner.
- **`§mutation witnesses` (block).** No AC asserts the perf assertion actually fires. A stub `Gate.evaluate` returning instantly would let `p50 ≤ 90s` pass vacuously forever; a stub `attempts.jsonl` with equal walls would let the 1.6× ratio pass forever. Fix: AC-MUT-LAT-1 + AC-MUT-RETRY-1 — paired witness tests in default CI (not under perf marker) that force the failure mode and assert `AssertionError` is raised.
- **`§warm_pull observability` (harden).** No AC verifies the autouse fixture actually fires. A future refactor could silently disable it; cold-pull cost would inflate p50 by ~5 s and CI would flake. Fix: AC-WARM-1 witness test.
- **`§gate_isolation_class pin` (block).** Per ADR-0004 the budgets are DiD-pinned (`shared_kernel`). A runner switch to Firecracker would invalidate them. Fix: AC-ISO-1 — read `SandboxRun.gate_isolation_class`; `pytest.skip` if not `shared_kernel`.
- **`§ADR-0011 contract` (harden).** The retry-2 ratio is meaningful only because every retry pays full freight. Fix: AC-NOCACHE-1 — assert two distinct `sandbox_run_id` and `sandbox_spec_hash` across attempt 1 / attempt 2 (proves both attempts actually ran sandbox); paired comment cites ADR-0011.
- **`§record_mode none` (block).** Notes prose alone is not a check; a live LLM call in a perf test is a flake source. Fix: AC-OFFLINE-1 mirrors S5-05's AC-OFFLINE-1 — `block_network` fixture or VCR `RecordMode.NONE`; cassette miss raises loud.
- **`§tools/ language convention` (harden).** Repo `tools/` scripts are Python (`tools/fuzz_yarn_lock.py`, `tools/regenerate_probe_schemas.py`). Bash `loop50.sh` violates CLAUDE.md "Match conventions". Fix: AC-LOOP50-LANG-1 — `tools/perf/loop50.py`.
- **`§CI workflow shape` (harden).** Workflow file was unspecified. Phase precedent is [S6-05 HARDENED](S6-05-kvm-smoke-and-weekly-cron.md) `.github/workflows/kvm-smoke.yml` — SHA-pinned `actions/checkout@<sha>` + `astral-sh/setup-uv@<sha>`. Fix: AC-CI-1 mirrors S6-05; re-uses the same self-hosted KVM runner the cron infra already provisions.
- **`§gitignore` (harden).** `.codegenie/perf/` is gitignored per Notes #6 but no AC enforces it. Fix: AC-GITIGNORE-1.
- **`§Status convention` (nit).** Sibling stories carry `Ready (HARDENED YYYY-MM-DD)`. Updated.

Internal-doc drift surfaced (not patched here): `High-level-impl.md §Step 7 done-criteria #2` says "flake rate ≤ 1 % over 50 runs" but 1/50 = 2 %. Story chooses the strict reading ("0 failures over 50 runs"); High-level-impl editorial amendment is flagged for the architect.

## Context

Phase 5 commits to two latency invariants: per-gate p50/p95 budgets against the `hello-node` fixture (§Goal 10) and a retry-2 wall-clock ≤ 1.6× retry-1 wall-clock (§Goal 11). This story lands the two pytest files that enforce them, the trend-row recorder that emits append-only JSONL with a Pydantic-pinned schema, the warm-pull autouse fixture that keeps cold image pulls from polluting the measurements, and the CI workflow that gates on the `[perf]` label + weekly cron. The tests are marked `slow` and `perf` and do not gate every PR (Step 7 §Risks). They reuse `tests/bench/_bench_kernel.py`'s `Threshold` + `Verdict` tagged-union (rule-of-three: `test_gate_latency` is the fourth consumer) and read per-attempt wall-clock from `attempts.jsonl` (the stable Phase 5 contract per S2-01 HARDENED), never from a synthesized timer around the runner.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Performance regression tests` (lines 916–919) — both test specs in 2 bullets.
- **Architecture:** `../phase-arch-design.md §Component 3 DinD performance envelope` — where the p50 ≤ 90 s / p95 ≤ 180 s budgets come from.
- **Architecture:** `../phase-arch-design.md §Goals` — Goals 10 and 11 verbatim (lines 25–26).
- **Phase ADRs:**
  - [`../ADRs/0011-no-verdict-cache-in-phase-5.md`](../ADRs/0011-no-verdict-cache-in-phase-5.md) — the "no cache" stance the retry-2 budget assumes.
  - [`../ADRs/0004-dind-default-macos-with-gate-isolation-class.md`](../ADRs/0004-dind-default-macos-with-gate-isolation-class.md) — backend choice the budgets are pinned against (`gate_isolation_class == "shared_kernel"`).
- **Implementation plan:** `../High-level-impl.md §Step 7` — exact budgets + done criteria (note: arithmetic error in done-criteria #2 noted in Validation notes; this story takes the strict reading).
- **Existing code — kernels to reuse (rule-of-three already crossed):**
  - [`tests/bench/_bench_kernel.py`](../../../../tests/bench/_bench_kernel.py) — `Threshold`, `Verdict` (`Ok | CommentOnly | Fail`), `compare_to_baseline(measurements, baseline, thresholds, *, p95_seconds)`. **The perf tests construct `Threshold` instances and match on the returned `Verdict`; no raw `assert p50 <=` expressions.**
  - [`src/codegenie/types/identifiers.py`](../../../../src/codegenie/types/identifiers.py) — `WorkflowId`, `SignalKind`, `AttemptNumber` NewTypes.
  - [`src/codegenie/sandbox/contract.py`](../../../../src/codegenie/sandbox/contract.py) — `RunId` NewType (S1-02 owns).
  - [`src/codegenie/gates/contract.py`](../../../../src/codegenie/gates/contract.py) — `GateContext`, `Attempt` Pydantic shape with `started_at`/`ended_at` (S1-04 owns).
  - [`src/codegenie/gates/runner.py`](../../../../src/codegenie/gates/runner.py) — `GateRunner` (S5-02 owns; **keyword-only constructor; `async def run(self, ctx: GateContext) -> GateOutcome` is the only method**).
- **Existing code — Phase 5 precedents to mirror:**
  - [`tests/fixtures/repos/hello-node/`](../../../../tests/fixtures/repos/hello-node/) — perf measurement baseline.
  - `tests/fixtures/repos/breaking-change-cve/` — from Phase 5 / [S5-05](S5-05-retry-recovers-integration.md) — retry-2 fixture (recipe attempt 1 fails on `tests`; LLM-fallback attempt 2 passes).
  - `tests/integration/gates/cassettes/stage6_retry_recovers.yaml` — from Phase 5 / [S5-05](S5-05-retry-recovers-integration.md) — single cassette with two LLM interactions in order. **READ-ONLY for this story.**
  - `tests/integration/_helpers/vcr.py` — from Phase 5 / [S5-05](S5-05-retry-recovers-integration.md) — `extract_phase4_interactions(cassette_path)` helper.
  - `tests/integration/_helpers/hooks.py` — from Phase 5 / [S5-05](S5-05-retry-recovers-integration.md) — `ReplanHookSpy` Decorator (not load-bearing for this story but available if needed).
  - `tests/integration/gates/conftest.py` — from Phase 5 / S5-05 — `gate_runner_factory` precedent the perf conftest mirrors.
  - `tests/_helpers/fixtures.py::apply_fixture_patch` — from Phase 5 / [S7-01 HARDENED](S7-01-adversarial-fixtures-and-tests.md) — fixture loader.
- **Existing code — convention precedents:**
  - [`tools/fuzz_yarn_lock.py`](../../../../tools/fuzz_yarn_lock.py), [`tools/regenerate_probe_schemas.py`](../../../../tools/regenerate_probe_schemas.py) — `tools/` scripts are Python; `loop50` must be too.
  - [`.github/workflows/kvm-smoke.yml`](../../../../.github/workflows/kvm-smoke.yml) (when S6-05 lands) — SHA-pinned actions; `pull_request: {types: [labeled]}` + `schedule: cron`; self-hosted runner.

## Goal

Land `tests/perf/test_gate_latency.py` and `tests/perf/test_retry_2_budget.py` such that they (a) enforce the §Goal 10 / §Goal 11 budgets on the DiD reference runner; (b) reuse `tests/bench/_bench_kernel.py`'s `Threshold` + `Verdict`; (c) record per-run trend samples to a session-scoped JSONL with Pydantic-pinned schemas (`LatencySample`, `RetryBudgetSample`); (d) read per-attempt wall-clock from `Attempt.started_at`/`ended_at` on `attempts.jsonl` rather than wrapping the runner; (e) replay the S5-05 cassette under `RecordMode.NONE` (no live LLM call); (f) gate on `[perf]` PR label + weekly cron; (g) ship two mutation-witness tests that prove the assertions actually fire under a forced over-budget condition.

## Acceptance criteria

### A. Test layout + markers + addopts

- [ ] **AC-LAYOUT-1** — Files exist at `tests/perf/conftest.py`, `tests/perf/_budgets.py`, `tests/perf/_models.py`, `tests/perf/_recorder.py`, `tests/perf/test_gate_latency.py`, `tests/perf/test_retry_2_budget.py`, `tests/perf/test_gate_latency_witness.py`, `tests/perf/test_retry_2_budget_witness.py`, `tests/perf/test__recorder_append_only.py`. No `tests/perf/__init__.py` (pytest discovery via `conftest.py` only — mirrors the S7-01 AC-COLLECT-NO-INIT-1 precedent).
- [ ] **AC-MARKER-1** — `pyproject.toml [tool.pytest.ini_options] markers` extended with `"perf: performance regression tests — gated on [perf] PR label + weekly cron (S7-02)"` and `"slow: tests that intentionally take > 10 s — composed with `perf` for the perf suite"`. Asserted in `tests/schema/test_pyproject_markers_registered.py`.
- [ ] **AC-ADDOPTS-1** — `pyproject.toml [tool.pytest.ini_options] addopts` extended from `-m "not bench and not phase_7_preview"` to `-m "not bench and not phase_7_preview and not perf"` — **extended, not replaced**. Existing `bench` and `phase_7_preview` exclusions remain. Asserted in `tests/schema/test_pyproject_addopts_perf_excluded.py` via substring match.
- [ ] **AC-MARKERED-1** — Both perf tests carry `@pytest.mark.perf` AND `@pytest.mark.slow`. Asserted via AST scan in `tests/schema/test_perf_files_double_marked.py`.

### B. Runner construction + async surface

- [ ] **AC-CTOR-1** — `tests/perf/conftest.py` exposes a `perf_gate_runner_factory` fixture that returns a callable `(gate: Gate, *, ledger: RetryLedger, ctx: GateContext) -> GateRunner`. The factory constructs `GateRunner` via the keyword-only signature locked by [S5-02 HARDENED AC-CTOR-1](S5-02-gate-runner-retry-loop.md): `GateRunner(*, client=client, gate=gate, ledger=ledger, spec_builder=spec_builder, max_attempts=3, replan_hook=None)`. No phantom `from_default_catalog` or `run_single_gate` call appears anywhere under `tests/perf/`. Asserted by `tests/schema/test_perf_no_phantom_api.py` — AST scan for `GateRunner.from_default_catalog` / `run_single_gate` / `runner.run(gate_id=` literal nodes.
- [ ] **AC-RUN-CTX-1** — `test_gate_latency.py` constructs one `GateRunner` per `gate_id` (`build`, `test`, `trace`) and one matching `GateContext` per call; the timed call is `await runner.run(ctx)`. The `ctx` is a real `GateContext` per [S1-04 HARDENED](S1-04-gates-contract-abc-models.md), not a `MagicMock`.
- [ ] **AC-ASYNC-1** — Every test under `tests/perf/` invoking `GateRunner.run` is `async def`. The repo's `asyncio_mode = "auto"` makes `@pytest.mark.asyncio` redundant; no perf test carries the marker. Asserted in `tests/schema/test_perf_async_invocation.py`.

### C. Latency-test correctness (`test_gate_latency.py`)

- [ ] **AC-LAT-1** — Test parametrizes `gate_id ∈ {"build", "test", "trace"}`; runs each gate 5 times against the `hello-node` fixture loaded via `apply_fixture_patch` from `tests._helpers.fixtures`; collects 5 wall-clock samples in seconds from `time.monotonic_ns()`.
- [ ] **AC-P95-1** — p50 is `statistics.median(samples)`; p95 at N=5 is `_p95_for_small_n(samples) := max(samples)` exposed from `tests/perf/_budgets.py` with a code-comment design note ("max() at N=5; lift to ≥ 20 samples + `statistics.quantiles(..., n=20, method='inclusive')[18]` when CI runner stabilizes — small-N quantile interpolation is statistically meaningless"). Test imports `_p95_for_small_n` rather than inlining the choice. Asserted: `tests/perf/test__p95_for_small_n.py` golden — for `samples=[1.0, 2.0, 3.0, 4.0, 5.0]`, returns `5.0`.
- [ ] **AC-BUDGET-1** — `tests/perf/_budgets.py` exports `LATENCY_BUDGETS: Final[Mapping[str, Threshold]]` mapping each `gate_id` to a `Threshold(comment_pct=20.0, fail_pct=100.0, fail_p95_s=<arch p95>)` constructed from the §Goal 10 numbers. `RETRY_BUDGET_RATIO: Final[float] = 1.6` exported from the same module. One definition site per architectural commitment; importers do not redefine.
- [ ] **AC-KERNEL-1** — Latency test invokes `tests.bench._bench_kernel.compare_to_baseline(measurements={gate_id: p50}, baseline={gate_id: BUDGETS[gate_id].p50}, thresholds=LATENCY_BUDGETS[gate_id], p95_seconds=p95)`. Pass = returned `Verdict` is `Ok`; otherwise the test raises `AssertionError` with the kernel's pre-formatted `summary`.
- [ ] **AC-KERNEL-2** — No raw `assert p50 <=` or `assert p95 <=` expression appears in either perf test file. Asserted by AST scan in `tests/schema/test_perf_no_raw_budget_assert.py` — `ast.Assert` with a `Compare` test comparing to `Threshold.fail_p95_s` field is the only permitted shape.
- [ ] **AC-ISO-1** — Latency test asserts `gate_isolation_class == "shared_kernel"` per ADR-0004 for each `SandboxRun` consumed. If non-`shared_kernel`, the test `pytest.skip("§Goal 10 budgets are DiD-pinned; non-shared_kernel runner detected")` rather than fail (a Firecracker runner is a legitimate environment but a different budget surface).

### D. Retry-2 budget correctness (`test_retry_2_budget.py`)

- [ ] **AC-CASSETTE-1** — Test is decorated `@pytest.mark.vcr("../integration/gates/cassettes/stage6_retry_recovers.yaml")` (or equivalent — the single cassette S5-05 ships, not two separate ones). Cassette path is `Path(__file__).parent.parent / "integration/gates/cassettes/stage6_retry_recovers.yaml"`; AC asserts the path resolves.
- [ ] **AC-CASSETTE-INTERACT-1** — Test pre-asserts (before timing starts) that the cassette has ≥ 2 interactions in order via `extract_phase4_interactions(cassette_path)` (S5-05's helper) — proves the fixture is the retry-2 cassette and not a degenerate single-interaction file.
- [ ] **AC-OFFLINE-1** — Test consumes `pytest-recording`'s `block_network` fixture (or VCR `RecordMode.NONE`) — any network escape during replay raises (`vcr.errors.CannotOverwriteExistingCassetteException`). Mirrors S5-05 AC-OFFLINE-1.
- [ ] **AC-RETRY-SRC-1** — Per-attempt wall-clock comes from `Attempt.ended_at - Attempt.started_at` parsed from the `attempts.jsonl` artifact (S2-01 HARDENED), NOT from `time.monotonic_ns()` wrapped around the runner (which would conflate test-harness setup time with sandbox wall time). The test reads `attempts.jsonl`, extracts the two `Attempt` rows in chain order, computes `retry_1_wall = (a1.ended_at - a1.started_at).total_seconds()` and `retry_2_wall = (a2.ended_at - a2.started_at).total_seconds()`.
- [ ] **AC-RETRY-GATE-1** — The test targets the `tests` gate (the failing gate in the S5-05 fixture per [S5-05 AC-SIG-1](S5-05-retry-recovers-integration.md)). Pre-assert: `attempt_1.outcome.failing_signals[0].kind == "tests"` AND `attempt_2.outcome.state == "passed"`. If either fails, the perf assertion does not run (the fixture has regressed and the architect is paged).
- [ ] **AC-RATIO-1** — Final assertion: `retry_2_wall / retry_1_wall <= RETRY_BUDGET_RATIO` (= 1.6 from `_budgets.py`). On failure, the `AssertionError` message includes both walls and the ratio with one-decimal precision.
- [ ] **AC-NOCACHE-1** — Per ADR-0011, the budget assumes no cache. Test asserts `attempts[0].sandbox_run_id != attempts[1].sandbox_run_id` AND `attempts[0].outcome.sandbox_spec_hash != attempts[1].outcome.sandbox_spec_hash` (proves both attempts ran full sandbox; a cache-hit would return identical IDs). Paired code comment cites ADR-0011.

### E. Mutation-witness tests (default CI, NOT under perf marker)

- [ ] **AC-MUT-LAT-1** — `tests/perf/test_gate_latency_witness.py` proves the latency assertion fires: a stub `Gate` whose `evaluate` sleeps `LATENCY_BUDGETS["build"].fail_p95_s + 1` seconds is wired through the kernel; the witness asserts `compare_to_baseline(...)` returns a `Fail` verdict. Runs in default CI in < 200 s (the sleep is the only cost). NOT marked `perf`.
- [ ] **AC-MUT-RETRY-1** — `tests/perf/test_retry_2_budget_witness.py` proves the retry-2 assertion fires: a synthesized `attempts.jsonl` with `retry_1_wall=10.0` / `retry_2_wall=20.0` (ratio 2.0 > 1.6) is constructed in `tmp_path`; the parser + ratio assertion raises `AssertionError`. NOT marked `perf`.
- [ ] **AC-WARM-1** — `tests/perf/test_warm_pull_fires.py` proves the autouse warm-pull fixture runs: a sentinel counter (module-level) incremented by `warm_pull` is asserted `== 1` at session teardown via a `pytest_sessionfinish` hook in `conftest.py`. NOT marked `perf` (runs in default CI).

### F. Trend-row schema + recorder

- [ ] **AC-SCHEMA-1** — `tests/perf/_models.py` exports two Pydantic models with `model_config = ConfigDict(frozen=True, extra="forbid")`:
  - `LatencySample(ts: datetime, git_sha: str (Field(pattern=r"^[0-9a-f]{7,40}$")), runner_name: RunnerName, gate_id: Literal["build", "test", "trace"], samples: tuple[float, ...] (min/max length 5), p50: float, p95: float)`.
  - `RetryBudgetSample(ts: datetime, git_sha: str, runner_name: RunnerName, retry_1_wall: float, retry_2_wall: float, ratio: float)`.
  - `RunnerName: TypeAlias = Literal["docker-desktop-mac-m-series", "ci-linux-8core"]` — closed set; widening is a one-line edit.
- [ ] **AC-SCHEMA-2** — `record_sample(path: Path, model: LatencySample | RetryBudgetSample) -> None` is typed at the boundary; passing a raw `dict` is a `TypeError` at mypy time. Asserted via the existing `tests/static/test_mypy_strict_passes.py`.
- [ ] **AC-PURE-1** — `tests/perf/_recorder.py` splits into `to_jsonl_line(model: BaseModel) -> str` (pure: `model.model_dump_json() + "\n"`) and `append_jsonl_line(path: Path, line: str) -> None` (impure shell). Mirrors S6-03 / S7-01 HARDENED `apply_fixture_patch` pattern.
- [ ] **AC-APPEND-1** — `tests/perf/test__recorder_append_only.py` writes two rows, then a third, asserts file size monotonically grows AND the file contains exactly three lines in order. No truncation, no clobber.

### G. Bench-kernel reuse + functional core / imperative shell

- [ ] **AC-FCIS-1** — Only `tests/perf/conftest.py` performs I/O (the autouse warm-pull `docker pull` invocation) under `tests/perf/`. AST scan in `tests/schema/test_perf_fcis_split.py` asserts no `open(..., "a"|"w")`, `Path.write_*`, or `subprocess.run` appears in any `test_*.py` under `tests/perf/` (those calls route through `_recorder.append_jsonl_line` only).
- [ ] **AC-PROP-1** — Hypothesis property test in `tests/perf/test__models_roundtrip.py`: for a strategy emitting valid `LatencySample` instances, `LatencySample.model_validate_json(to_jsonl_line(sample).rstrip("\n")) == sample`.

### H. Warm-pull discipline

- [ ] **AC-PULL-1** — `tests/perf/conftest.py` exposes an autouse session-scoped `warm_pull` fixture that issues `subprocess.run(["docker", "pull", <pinned-digest>])` once before any timed code; the digest is read from `tools/digests.yaml` per ADR-0013. AC-PULL-1 verifies subprocess call count == 1 via a `caplog`-style spy.
- [ ] **AC-PULL-2** — If `docker pull` fails (e.g., the host has no docker), the fixture `pytest.skip`s the entire perf module with a structured reason (`"warm_pull unavailable: docker not installed"`). NOT a silent pass; NOT a hard fail outside CI.

### I. CI workflow + tooling

- [ ] **AC-CI-1** — `.github/workflows/perf.yml` exists, SHA-pinned for `actions/checkout` and `astral-sh/setup-uv` (use the same SHAs as `.github/workflows/kvm-smoke.yml` when S6-05 lands; if S6-05 not yet GREEN, executor records the dependency and stops). Triggers: `pull_request: {types: [labeled]}` filtered to `if: contains(github.event.pull_request.labels.*.name, 'perf')` AND `schedule: [{cron: '<weekly cron same as S6-05>'}]`. Runs on the same self-hosted KVM runner S6-05 provisions (reuses existing cron infra per High-level-impl §Step 7 Risks).
- [ ] **AC-LOOP50-LANG-1** — `tools/perf/loop50.py` (Python, NOT bash) — shebang `#!/usr/bin/env python3`; `argparse` CLI exposing `--iters 50` (default 50), `--marker perf`; shells out via `subprocess.run(["uv", "run", "pytest", "-m", marker, ...])`; tallies failures; exits non-zero if `failures > 0` (strict per High-level-impl Step 7 done-criteria #2 — see Validation notes flake-rate item).
- [ ] **AC-FLAKE-1** — `tools/perf/loop50.py` enforces **0 failures over 50 runs** as the gate (strict reading). Documented runtime ≈ 2 hours; intended to be run locally before opening a `[perf]`-labeled PR.
- [ ] **AC-GITIGNORE-1** — Repo `.gitignore` contains `.codegenie/perf/` (or a parent-glob covering it). Per-runner trend data is never committed. Asserted by `tests/schema/test_gitignore_includes_codegenie_perf.py`.

### J. Static guards + final discipline

- [ ] **AC-MONOTONIC-1** — All wall-clock measurements in `tests/perf/` use `time.monotonic_ns()` (NOT `time.time()`). AST scan in `tests/schema/test_perf_monotonic_ns.py` asserts no `time.time()` call appears under `tests/perf/`. (Reason: `monotonic_ns` is project precedent for sub-ms timing; `time.time()` is sensitive to NTP/DST jumps.)
- [ ] **AC-LINT-1** — `ruff check tests/perf/`, `mypy --strict tests/perf/`, and `pytest tests/perf/ --no-cov -m perf` all pass on the reference DiD runner. (`--no-cov` per project-wide ad-hoc-run convention — narrow subsets miss the 85 % global cov gate.)
- [ ] **AC-TDD-1** — TDD plan's red tests exist, were committed before green, and are now green. Attempt log records the red → green diff sha.

## Implementation outline

1. **Pyproject extension (single combined edit).** In `pyproject.toml`: extend `addopts` to `-m "not bench and not phase_7_preview and not perf"`; add `"perf": ...` and `"slow": ...` rows under `markers`. Run `pytest --collect-only` to confirm `--strict-markers` accepts both. (AC-ADDOPTS-1, AC-MARKER-1.)
2. **Trend-row schema (`tests/perf/_models.py`).** `LatencySample`, `RetryBudgetSample`, `RunnerName: TypeAlias = Literal[...]`. `frozen=True, extra='forbid'`. Import `RunId`, `WorkflowId` from their existing modules — do NOT redefine. (AC-SCHEMA-1, AC-SCHEMA-2.)
3. **Recorder split (`tests/perf/_recorder.py`).** Pure `to_jsonl_line(model: BaseModel) -> str` + impure `append_jsonl_line(path: Path, line: str) -> None`. Open with `mode='a'`, encoding='utf-8', `newline=''`. (AC-PURE-1, AC-APPEND-1.)
4. **Budgets table (`tests/perf/_budgets.py`).** `LATENCY_BUDGETS: Final[Mapping[str, Threshold]]` mapping `"build"|"test"|"trace"` to `Threshold(comment_pct=20.0, fail_pct=100.0, fail_p95_s=<arch p95>)`. `RETRY_BUDGET_RATIO: Final[float] = 1.6`. `_p95_for_small_n(samples) -> float` with the design-note comment. (AC-BUDGET-1, AC-P95-1.)
5. **Conftest (`tests/perf/conftest.py`).** Autouse session-scoped `warm_pull` fixture; `perf_gate_runner_factory` fixture that returns a callable constructing `GateRunner` with the keyword-only signature; sentinel counter for `test_warm_pull_fires`. ONLY impure module under `tests/perf/`. (AC-CTOR-1, AC-WARM-1, AC-PULL-1/2, AC-FCIS-1.)
6. **Latency test (`tests/perf/test_gate_latency.py`).** `async def`; parametrize over three gates; load `hello-node` via `apply_fixture_patch`; loop 5 × `await runner.run(ctx)` with `time.monotonic_ns()` braces; compute p50 = median, p95 = `_p95_for_small_n(samples)`; invoke `compare_to_baseline(...)`; assert `isinstance(verdict, Ok)`; record a `LatencySample` via `append_jsonl_line(to_jsonl_line(sample))`; pin `gate_isolation_class == "shared_kernel"` per AC-ISO-1. (AC-LAT-1, AC-ISO-1, AC-KERNEL-1/2, AC-RUN-CTX-1, AC-ASYNC-1, AC-MONOTONIC-1.)
7. **Retry-2 test (`tests/perf/test_retry_2_budget.py`).** `async def`; `@pytest.mark.vcr("../integration/gates/cassettes/stage6_retry_recovers.yaml")`; `block_network`; pre-assert ≥ 2 interactions; `await runner.run(ctx)` against `breaking-change-cve`; parse `attempts.jsonl`; assert `failing_signals[0].kind == "tests"` and `attempt_2.state == "passed"`; assert `sandbox_run_id` and `sandbox_spec_hash` differ across the two attempts (ADR-0011); compute the ratio from `Attempt.ended_at - Attempt.started_at`; assert `<= RETRY_BUDGET_RATIO`. (AC-CASSETTE-1/INTERACT-1, AC-OFFLINE-1, AC-RETRY-SRC-1, AC-RETRY-GATE-1, AC-RATIO-1, AC-NOCACHE-1.)
8. **Mutation-witness tests.** `tests/perf/test_gate_latency_witness.py` — kernel returns `Fail` when measurement > `fail_p95_s`. `tests/perf/test_retry_2_budget_witness.py` — synthesized `attempts.jsonl` with ratio 2.0 raises. `tests/perf/test_warm_pull_fires.py` — sentinel counter == 1. Both default-CI, NOT marked `perf`. (AC-MUT-LAT-1, AC-MUT-RETRY-1, AC-WARM-1.)
9. **Loop50 harness (`tools/perf/loop50.py`).** Python `argparse`; `subprocess.run(["uv", "run", "pytest", "-m", "perf", "--no-cov"])` in a loop; tally failures; exit non-zero on any failure. (AC-LOOP50-LANG-1, AC-FLAKE-1.)
10. **CI workflow (`.github/workflows/perf.yml`).** SHA-pinned actions; `pull_request: {types: [labeled]}` filtered by label name; `schedule: cron` weekly matching S6-05's; self-hosted runner reuse. (AC-CI-1.)

## TDD plan — red / green / refactor

### Red

Test file path: `tests/perf/test_gate_latency.py`

```python
"""§Goal 10 — per-gate p50/p95 latency budgets on hello-node (DiD reference runner).

Why this matters: the budgets are the operator-facing promise. A regression here
means a remediation that fits the cost cap today silently misses it after a deploy.
The test fails loud the moment a change introduces a >2× regression on any gate.

ADR-0011 (no verdict cache in Phase 5) and ADR-0004 (DiD default macOS) are the
load-bearing context. Cache landing would make these numbers unmeaningful;
runner switch would invalidate them.
"""

from __future__ import annotations

import statistics
import time
from typing import TYPE_CHECKING

import pytest

from tests._helpers.fixtures import apply_fixture_patch
from tests.bench._bench_kernel import Ok, compare_to_baseline
from tests.perf._budgets import LATENCY_BUDGETS, _p95_for_small_n
from tests.perf._models import LatencySample, RunnerName
from tests.perf._recorder import append_jsonl_line, to_jsonl_line

if TYPE_CHECKING:
    from collections.abc import Callable

    from codegenie.gates.contract import Gate, GateContext
    from codegenie.gates.runner import GateRunner


_TREND_PATH = ".codegenie/perf/latency.jsonl"
_SAMPLES_PER_GATE: int = 5  # Source: §Goal 10. Lift to ≥ 20 + statistics.quantiles when CI runner stabilizes (AC-P95-1).


@pytest.mark.perf
@pytest.mark.slow
@pytest.mark.parametrize("gate_id", ["build", "test", "trace"])
async def test_gate_latency_within_budget(
    tmp_path,
    gate_id: str,
    perf_gate_runner_factory: Callable[..., GateRunner],
    build_gate: Gate,  # fixture: returns the Gate instance for the given gate_id
    perf_gate_context: GateContext,
    perf_runner_name: RunnerName,
    perf_git_sha: str,
) -> None:
    repo = apply_fixture_patch("hello-node", into=tmp_path)
    samples_ns: list[int] = []
    runner = perf_gate_runner_factory(gate=build_gate, ctx=perf_gate_context)
    iso_seen: set[str] = set()

    for _ in range(_SAMPLES_PER_GATE):
        start = time.monotonic_ns()
        outcome = await runner.run(perf_gate_context)
        samples_ns.append(time.monotonic_ns() - start)
        # AC-ISO-1: skip loud if the runner is not DiD shared_kernel.
        iso_seen.add(outcome.signals.gate_isolation_class)

    if iso_seen != {"shared_kernel"}:
        pytest.skip(f"§Goal 10 budgets are DiD-pinned; saw isolation classes {iso_seen}")

    samples = [n / 1e9 for n in samples_ns]
    p50 = statistics.median(samples)
    p95 = _p95_for_small_n(samples)

    threshold = LATENCY_BUDGETS[gate_id]
    verdict = compare_to_baseline(
        measurements={gate_id: p50},
        baseline={gate_id: threshold.fail_p95_s / 2.0},  # comment-only threshold is "regression vs half-of-p95"
        thresholds=threshold,
        p95_seconds=p95,
    )

    sample = LatencySample(
        ts=datetime.now(UTC),
        git_sha=perf_git_sha,
        runner_name=perf_runner_name,
        gate_id=gate_id,  # type: ignore[arg-type]  # mypy narrows via Literal
        samples=tuple(samples),
        p50=p50,
        p95=p95,
    )
    append_jsonl_line(Path(_TREND_PATH), to_jsonl_line(sample))

    assert isinstance(verdict, Ok), verdict.summary if not isinstance(verdict, Ok) else ""
```

### Green

1. Land `tests/perf/_budgets.py`, `_models.py`, `_recorder.py` (Implementation outline §2–4).
2. Land `tests/perf/conftest.py` with the warm-pull autouse fixture + `perf_gate_runner_factory` + the three small fixtures the test reads (`build_gate`, `perf_gate_context`, `perf_runner_name`, `perf_git_sha`).
3. Run the latency test on the reference runner; confirm it passes.
4. Land `test_retry_2_budget.py` reading from `attempts.jsonl` per AC-RETRY-SRC-1.
5. Land the three mutation-witness tests; confirm they pass under default CI (NOT under perf marker).
6. Land `tools/perf/loop50.py` and `.github/workflows/perf.yml`.

### Refactor

- Confirm no raw `assert p50 <=` or `assert p95 <=` survives — AC-KERNEL-2 AST scan is the gate.
- Confirm the trend-row JSONL is byte-stable: run the property test in AC-PROP-1.
- Confirm `tests/perf/conftest.py` is the only impure module under `tests/perf/` (AC-FCIS-1).
- Skip the perf suite on default PR CI via the `addopts` extension (AC-ADDOPTS-1).

## Files to touch

| Path | Why |
|---|---|
| `tests/perf/conftest.py` | Warm-pull autouse fixture + `perf_gate_runner_factory` + sentinel counter (ONLY impure module under `tests/perf/`) |
| `tests/perf/_budgets.py` | `LATENCY_BUDGETS: Final[Mapping[str, Threshold]]`, `RETRY_BUDGET_RATIO`, `_p95_for_small_n` |
| `tests/perf/_models.py` | `LatencySample`, `RetryBudgetSample`, `RunnerName: TypeAlias = Literal[...]` |
| `tests/perf/_recorder.py` | Pure `to_jsonl_line` + impure `append_jsonl_line` (functional-core / imperative-shell split) |
| `tests/perf/test_gate_latency.py` | §Goal 10 budgets enforced via bench kernel |
| `tests/perf/test_retry_2_budget.py` | §Goal 11 ratio enforced; reads `attempts.jsonl`; ADR-0011 pin |
| `tests/perf/test_gate_latency_witness.py` | Mutation witness — proves AC-LAT-1 assertion actually fires (default CI; NOT marked `perf`) |
| `tests/perf/test_retry_2_budget_witness.py` | Mutation witness — proves AC-RATIO-1 actually fires (default CI; NOT marked `perf`) |
| `tests/perf/test_warm_pull_fires.py` | Witness — proves autouse warm-pull fixture invoked exactly once |
| `tests/perf/test__recorder_append_only.py` | Append-only contract |
| `tests/perf/test__models_roundtrip.py` | Hypothesis property — JSONL round-trip stability |
| `tests/perf/test__p95_for_small_n.py` | Golden — `[1..5] → 5.0` (proves max() not interpolation) |
| `tests/schema/test_pyproject_markers_registered.py` | AC-MARKER-1 |
| `tests/schema/test_pyproject_addopts_perf_excluded.py` | AC-ADDOPTS-1 (substring preservation) |
| `tests/schema/test_perf_files_double_marked.py` | AC-MARKERED-1 |
| `tests/schema/test_perf_no_phantom_api.py` | AC-CTOR-1 (no `from_default_catalog` / `run_single_gate` literals) |
| `tests/schema/test_perf_async_invocation.py` | AC-ASYNC-1 |
| `tests/schema/test_perf_no_raw_budget_assert.py` | AC-KERNEL-2 |
| `tests/schema/test_perf_fcis_split.py` | AC-FCIS-1 |
| `tests/schema/test_perf_monotonic_ns.py` | AC-MONOTONIC-1 |
| `tests/schema/test_gitignore_includes_codegenie_perf.py` | AC-GITIGNORE-1 |
| `tools/perf/loop50.py` | Python flake-rate harness (replaces the proposed bash variant) |
| `.github/workflows/perf.yml` | `[perf]` label + weekly cron CI (SHA-pinned actions per S6-05 precedent) |
| `pyproject.toml` | `addopts` extension + `perf` / `slow` markers (single combined edit) |
| `.gitignore` | `.codegenie/perf/` (if parent-glob doesn't already cover) |

## Out of scope

- Adversarial tests (S7-01 owns).
- Cost emission (S7-03 owns).
- Concurrent-remediate `flock` (S7-04 owns).
- Adding any cache or memoization to make budgets easier — ADR-0011 forbids it in Phase 5.
- Cross-runner budget normalization. Budgets are stated against the DiD reference runner; CI runners that differ must run the perf suite on a self-hosted job that matches the reference.
- Editing `GateRunner` to add a `run_single_gate(gate_id=...)` helper. S5-02 owns the API; the keyword-only `run(self, ctx: GateContext)` is the only method. Constructing one runner per gate is the right pattern.
- Recording new Phase 4 LLM cassettes. This story REPLAYS the cassette S5-05 ships; live re-record is S5-05's runbook.
- Reinventing `Threshold` or `Verdict`. `tests/bench/_bench_kernel.py` is the canonical kernel — this story is its fourth consumer.
- Editing `High-level-impl.md §Step 7 done-criteria #2` flake-rate arithmetic (1/50 → 1 % vs 2 %). Story takes the strict reading (0 failures over 50 runs); editorial amendment is flagged for the architect.

## Notes for the implementer

1. **`time.monotonic_ns()`, NOT `time.time()` or `time.monotonic()`.** A wall-clock jump (NTP slew, DST) can produce negative deltas that silently pass the assertion. `monotonic_ns` is project precedent for sub-ms timing; AC-MONOTONIC-1 enforces it via AST scan.
2. **Five samples is the floor, not the target.** At N=5, p95 = max(samples) is the honest statistic; `statistics.quantiles(..., n=20)` interpolation produces a confidence-free number. When the CI runner stabilizes (Phase 9+ Temporal-pinned, lower variance), lift N to ≥ 20 and switch to `quantiles(..., n=20, method='inclusive')[18]` in `_p95_for_small_n`. The helper's name is intentionally honest about the choice.
3. **Warm pull is essential.** Without it, the first `build` gate eats the image-pull cost (~5 s) and skews p50 above budget. Pull once per session, before any timed code runs. `tests/perf/conftest.py` is the ONLY impure module under `tests/perf/` — AC-FCIS-1 keeps it that way.
4. **`Attempt.ended_at - Attempt.started_at` is the only retry-2 wall source.** Wrapping `await runner.run(ctx)` with `monotonic_ns()` would conflate test-harness setup time (cassette load, ctx construction) with sandbox wall time and skew the ratio. The arch's §Component 5 commits per-attempt timing to `attempts.jsonl` (S2-01 HARDENED owns the row schema with `started_at`/`ended_at`); read the artifact, not a synthesized timer.
5. **High-level-impl §Step 7 done-criteria #2 has an arithmetic error.** "≤ 1 % (≤ 1/50 failures)" — 1/50 is 2 %. This story takes the strict reading ("0 failures over 50 runs") via AC-FLAKE-1. Flag an editorial amendment for the architect; do NOT silently propagate the wrong reading.
6. **`.codegenie/perf/` is per-runner, gitignored.** Trend data shape is contractual (Pydantic) so CI cron upload-to-artifact-storage in Phase 14 ops can consume it byte-stably. Do not commit the JSONL.
7. **Bench-kernel reuse is the load-bearing design choice.** `tests/bench/_bench_kernel.py` already owns `Threshold` + `Verdict` and three consumers — this story is the fourth (well past rule-of-three). Constructing a fresh `Threshold(comment_pct=20, fail_pct=100, fail_p95_s=<arch p95>)` per gate and matching on the returned `Verdict` is the entire assertion shape. Raw `assert p50 <= 90.0` would not just bypass the kernel — it would re-introduce the primitive-obsession the kernel exists to abolish (Threshold is the budget vocabulary). AC-KERNEL-2 is the AST-scan guard.
8. **`gate_isolation_class == "shared_kernel"` per ADR-0004.** The budgets are DiD-specific. A Firecracker runner would have different latency surface (microVM cold-start, kernel boot, rootfs mount) and these numbers would be wrong by ≥ 2×. AC-ISO-1 skips loud rather than fails — Firecracker is a legitimate environment that deserves its own future budget (Phase 13 cost dashboard owns the cross-class measurement).
9. **The `perf_gate_runner_factory` fixture mirrors S5-05's `gate_runner_factory`.** If S5-05 names it `gate_runner_factory` and exports it from `tests/integration/gates/conftest.py`, perf's fixture should import and rewrap (DRY) rather than reimplement. If S5-05's factory needs widening (e.g., the perf story needs no `ReplanHook`), surface as a hardening of S5-05's fixture, NOT a fork.
10. **`block_network` in `test_retry_2_budget.py` is non-optional.** A live LLM call in a perf test is a Phase 4 budget burn AND a flake source — the cassette captures the deterministic input. Mirror S5-05's AC-OFFLINE-1 exactly.
11. **Pre-condition discipline for executor.** S5-02, S5-05, S2-01, S1-04, and S7-01 must all be GREEN before this story can execute. If any precondition is still BLOCKED or pre-GREEN at executor time, this story is blocked; do not stub. The executor's `_attempts/S7-02-perf-regression-gates.md` log should record the missing precondition and stop.
