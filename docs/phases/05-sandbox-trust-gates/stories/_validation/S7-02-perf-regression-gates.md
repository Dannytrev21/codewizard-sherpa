# Validation report — Story S7-02 — Performance regression gates (latency + retry-2 budget)

**Story:** [`../S7-02-perf-regression-gates.md`](../S7-02-perf-regression-gates.md)
**Validated:** 2026-05-25
**Validator:** `phase-story-validator` (single-agent inline mode)
**Validator agent run:** automated (`story-validation-corrector` scheduled task)
**Verdict:** **HARDENED**

## Summary

S7-02 owns the two perf gates the phase commits to in §Goal 10 (per-gate p50/p95 latency on `hello-node`) and §Goal 11 (retry-2 wall-clock ≤ 1.6× retry-1). The draft was directionally correct — right budgets, right markers, right "no cache makes this honest" framing — but its TDD plan invoked two **phantom APIs** that S5-02 HARDENED has already locked away (`GateRunner.from_default_catalog(repo=...)` and `runner.run_single_gate(gate_id=...)`), wired sync `def test_*` against `async def run`, pointed at cassette paths that don't match Phase 5's actual cassette layout, and prescribed a `statistics.quantiles(samples, n=20)[18]` p95 over 5 samples (statistically vacuous interpolation, and the default `method='exclusive'` is only marginally defined for tiny N). The flake-rate math is inconsistent ("≤ 1% (≤ 1/50)" — 1/50 is 2 %). The story also rolled its own `Threshold` / assertion shape while ignoring `tests/bench/_bench_kernel.py`, which already ships `Threshold` + `Verdict` (`Ok | CommentOnly | Fail`) and is the third-consumer-onwards extraction site for this exact bench-comparison shape.

Counting: **24 findings — 9 block-tier, 11 harden-tier, 4 nit-tier.** The blocks would have wasted at least one executor attempt on each (phantom APIs raise `AttributeError`; sync-on-async binds a coroutine and assertions vacuously pass; quantiles raise `StatisticsError` or return interpolated garbage; the wrong cassette path makes the retry-2 test unrunnable). The hardens close mutation-resistance gaps (a 0-second stub gate would pass the budget with zero evidence the test fires) and tie loose ends to existing kernels (newtypes, structlog observability, byte-stable JSONL schema). The nits align the Status line, marker registration, gitignore, and `addopts` extension language with existing project conventions.

**No `RESCUE`-tier findings.** The goal traces cleanly to phase-arch-design §Goal 10 / §Goal 11; every gap was patchable by pinning against S5-02 / S5-05 HARDENED, the bench-kernel precedent, and CLAUDE.md commitments. **No Stage-3 research needed** — every gap was answerable from the HARDENED sibling reports (S1-04, S2-01, S5-02, S5-05) and the existing `tests/bench/_bench_kernel.py` kernel.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim, hardened):** Land `tests/perf/test_gate_latency.py` and `tests/perf/test_retry_2_budget.py` such that they enforce §Goal 10 (build p50 ≤ 90 s / p95 ≤ 180 s; test p50 ≤ 60 s / p95 ≤ 120 s; trace p50 ≤ 15 s / p95 ≤ 45 s on the `hello-node` fixture) and §Goal 11 (retry-2 wall ≤ 1.6× retry-1 wall against the `breaking-change-cve` fixture S5-05 owns), reuse `tests/bench/_bench_kernel.py`'s `Threshold` + `Verdict` (rule-of-three: bench_portfolio_walltime, bench_index_health_overhead, bench_portfolio_walltime_hosted_runner are already-existing consumers — `test_gate_latency` is the fourth), record per-run trend samples to a session-scoped JSONL with a Pydantic-pinned schema, gate on `[perf]` PR label + weekly cron, and never run in default CI.
- **Non-goals (Out-of-scope, hardened):** Adversarial tests (S7-01); cost emission (S7-03); concurrent-remediate `flock` (S7-04); any cache or memoization (ADR-0011); cross-runner budget normalization (reference runner only); editing `GateRunner` to add a `run_single_gate` helper (the existing keyword-only `run(self, ctx: GateContext)` is the only API); recording new Phase-4 LLM cassettes (this story REPLAYS the cassette S5-05 ships; live re-record is S5-05's runbook).

### Phase 5 exit criteria touched

- **Step 7 done-criteria (`High-level-impl.md §Step 7`):** "Performance tests pass on the reference runner; flake rate ≤ 1 % over 50 runs"; "test_retry_2_budget.py asserts the 1.6× ratio with no cache and full re-run of all six gates."
- **§Goals 10 + 11 (`phase-arch-design.md` lines 25–26):** the two budgets verbatim.
- **§Performance regression tests (`phase-arch-design.md` line 916–919):** both test-file specs.
- **§Component 3 DinD performance envelope (`phase-arch-design.md`):** where the budgets come from.
- **§Step 7 Risk #5 (`High-level-impl.md` line 276):** the warm-pull discipline (cold pull skews variance).

### Load-bearing commitments touched

- **ADR-0011 (no verdict cache in Phase 5):** the retry-2 ratio is meaningful only because every retry pays full freight. The story must encode this assumption AS AN AC, not just as Notes prose, so a future cache cannot silently land without retripping this gate.
- **ADR-0004 (DiD default macOS + `gate_isolation_class`):** the budgets are stated against the DinD reference runner. The perf test should pin `gate_isolation_class == "shared_kernel"` so a runner switch surfaces loudly.
- **CLAUDE.md "Newtype identifiers":** `WorkflowId`, `RunId`, `SignalKind`, `AttemptNumber` are NewTypes; the trend-row Pydantic models must use them rather than raw `str` / `int`.
- **CLAUDE.md "Functional core / imperative shell":** the recorder must split into a pure `to_jsonl_row(...)` helper and an impure `append_to(path, row)` shell.
- **CLAUDE.md "Extension by addition":** four bench consumers now exist (`bench_portfolio_walltime`, `bench_index_health_overhead`, `bench_portfolio_walltime_hosted_runner`, `test_gate_latency`); the kernel at `tests/bench/_bench_kernel.py` is the extraction site — do not reinvent `Threshold`.
- **CLAUDE.md "Match the existing convention":** `tools/` scripts in this repo are Python (`tools/fuzz_yarn_lock.py`, `tools/regenerate_probe_schemas.py`). The draft proposed a bash `tools/perf/loop50.sh`; the convention is `tools/perf/loop50.py`.

### Adjacent / prerequisite stories cited

| Story | Status | What S7-02 reuses |
|---|---|---|
| [S1-02](../S1-02-sandbox-contract-protocol-models.md) | HARDENED | `RunId` NewType (lives in `codegenie.sandbox.contract`) |
| [S1-04](../S1-04-gates-contract-abc-models.md) | HARDENED | `GateContext`, `Attempt.started_at` / `Attempt.ended_at` (per-attempt wall source) |
| [S2-01](../S2-01-retry-ledger-blake3-chain.md) | HARDENED | `attempts.jsonl` row schema with `started_at` / `ended_at` |
| [S5-02](../S5-02-gate-runner-retry-loop.md) | HARDENED | `GateRunner(*, client, gate, ledger, spec_builder, max_attempts=3, replan_hook=None)` — keyword-only; `async def run(self, ctx: GateContext) -> GateOutcome`; `gates.runner.exit` structlog event with `total_duration_ms` |
| [S5-05](../S5-05-retry-recovers-integration.md) | HARDENED | `breaking-change-cve` fixture; `tests/integration/gates/cassettes/stage6_retry_recovers.yaml` cassette; `tests/integration/_helpers/vcr.py` extractor; `tests/integration/_helpers/hooks.py::ReplanHookSpy` |
| [S6-05](../S6-05-kvm-smoke-and-weekly-cron.md) | HARDENED | Weekly-cron CI workflow precedent |

## Critic findings

### Critic A — Coverage (does the AC set guarantee the goal?)

| # | Severity | Finding | Resolution |
|---|---|---|---|
| C-A-1 | block | No AC asserts the perf test actually fires (vacuous-pass). If `GateRunner.run` short-circuits in 0 s on a stub, every budget assertion silently passes. | AC-MUT-LAT-1 / AC-MUT-RETRY-1 — mutation witnesses: a paired unit test that wraps the timed unit so it sleeps `BUDGET + 1` and asserts the assertion fires. |
| C-A-2 | block | No AC pins the cassette `record_mode='none'`; a live LLM call in a perf test is a flake source (Notes #5 alone is not a check). | AC-OFFLINE-1 mirrors S5-05's AC-OFFLINE-1 — `block_network` fixture or VCR `RecordMode.NONE`; cassette miss raises. |
| C-A-3 | block | No AC asserts `gate_isolation_class == "shared_kernel"` on the reference runner. ADR-0004 makes the budgets DinD-specific; a runner switch to Firecracker would invalidate them silently. | AC-ISO-1 — read `SandboxRun.gate_isolation_class` for each sample; skip with `pytest.skip("budget is DiD-specific")` if `microvm`. |
| C-A-4 | harden | No AC ties the test to ADR-0011 (no verdict cache). If a future story lands a cache, retry-2 ratio becomes meaningless. | AC-NOCACHE-1 — runtime assertion that `attempts.jsonl` has two distinct `sandbox_run_id`s and two distinct `sandbox_spec_hash` values across attempt-1 + attempt-2 (proves both attempts actually ran sandbox); paired comment cites ADR-0011. |
| C-A-5 | harden | The retry-2 test has no AC for which gate's retry is being measured. The fixture exercises the `tests` gate (per S5-05 AC-SIG-1). | AC-RETRY-GATE-1 — the test targets the `tests` gate per S5-05 fixture; AC asserts `outcome.failing_signals[0].kind == "tests"` on attempt 1. |
| C-A-6 | harden | `.codegenie/perf/` is gitignored per Notes #6 but no AC enforces it. | AC-GITIGNORE-1 — `.codegenie/perf/` added to `.gitignore` at the repo root (the existing `.codegenie/` parent-level ignore may already cover it; AC asserts grep precedent). |
| C-A-7 | harden | The flake-rate math is inconsistent: "≤ 1 % (up to 1/50 tolerated)" — 1/50 is 2 %. | AC-FLAKE-1 — define flake rate as `failures / runs`; budget ≤ 2 %; mention that 0 failures is target, 1 failure tolerated as variance. Or tighten to "0 failures over 50 runs"; the architect intent (Step 7 Risks #5: ≤ 1 %) is the strict reading — choose strict. |
| C-A-8 | nit | No `Status` HARDENED stamp; sibling stories use `Ready (HARDENED YYYY-MM-DD)`. | Status updated. |

### Critic B — Test Quality (mutation thinking; would the TDD plan catch a wrong impl?)

| # | Severity | Finding | Resolution |
|---|---|---|---|
| C-B-1 | block | `statistics.quantiles(samples, n=20)[18]` with N=5 samples — `method='exclusive'` (the default) interpolates between adjacent samples and the p95 is effectively `max(samples)` with imaginary precision. With N<7, exclusive quantiles can raise `StatisticsError` depending on Python version; with `inclusive` the value is interpolated garbage. | AC-P95-1 — define p95 as `max(samples)` for N=5 with a code comment explaining the architectural choice (small N for cost; tight upper bound for safety); OR lift to N≥20 with an explicit comment. The story now pins **`max(samples)` as p95** for N=5 and a clearly-named `_p95_for_small_n(samples)` helper that documents the choice. (Future-proof: when CI runner stabilizes, lift N and switch to `statistics.quantiles(..., n=20, method='inclusive')[18]`.) |
| C-B-2 | block | No witness test that a real over-budget gate trips the assertion. A vacuous test (gate runs in 0 s) would happily pass forever. | AC-MUT-LAT-1 — `tests/perf/test_gate_latency_witness.py` — uses a stub `Gate.evaluate` that sleeps `budget + 1` and asserts the parametrized test raises `AssertionError`. (Pure unit; not run under perf marker; runs in default CI.) |
| C-B-3 | block | Same mutation gap on retry-2: a stub runner returning hardcoded equal walls passes vacuously. | AC-MUT-RETRY-1 — witness test that forces `retry_2_wall = 2× retry_1_wall` via a fake `attempts.jsonl` and asserts the budget AC fails. |
| C-B-4 | harden | The recorder's append-only golden test (Refactor §2) is described but no AC pins it. | AC-APPEND-1 — pinned as an AC (not just a Refactor step); test inspects file size monotonically grows across two `record` calls. |
| C-B-5 | harden | No property test for the trend-row schema's byte-stability across `record` → `read`. | AC-PROP-1 — Hypothesis property: `parse_jsonl_row(serialize_jsonl_row(row)) == row` over a strategy that emits valid `LatencySample`. |
| C-B-6 | harden | No AC verifies the autouse `warm_pull` fixture actually fires before the first sample. A future fixture refactor could silently disable it; cold-pull cost would inflate p50 by ~5 s and CI would flake. | AC-WARM-1 — `tests/perf/test_warm_pull_fires.py` (witness): a sentinel `caplog`-style spy asserts `warm_pull` invocation count == 1 per session. |
| C-B-7 | harden | `time.monotonic()` precision is fine for ≥ 1 s budgets but `time.monotonic_ns()` is the project precedent (search: `monotonic_ns` in `src/codegenie/` — used for sub-ms timings). For 15 s trace budgets it doesn't matter; pin for consistency. | AC-MONOTONIC-1 — use `time.monotonic_ns()` everywhere; convert to float seconds at the comparison site only. |

### Critic C — Consistency (arch / ADR / commitment)

| # | Severity | Finding | Resolution |
|---|---|---|---|
| C-C-1 | block | `GateRunner.from_default_catalog(repo=repo)` does not exist. Per S5-02 HARDENED AC-CTOR-1: `GateRunner(*, client: SandboxClient, gate: Gate, ledger: RetryLedger, spec_builder: SandboxSpecBuilder, max_attempts: int = 3, replan_hook: ReplanHook | None = None)` — keyword-only; no factory. Draft would `AttributeError` at first run. | AC-CTOR-1 — shared `perf_gate_runner_factory` fixture in `tests/perf/conftest.py` that constructs `GateRunner` with the keyword-only signature mirroring S5-05's `tests/integration/gates/conftest.py` precedent. |
| C-C-2 | block | `runner.run_single_gate(gate_id=gate_id)` does not exist. Per S5-02 HARDENED AC-RUN-CTX-1: the only signature is `async def run(self, ctx: GateContext) -> GateOutcome`. `gate_id` is the `Gate.id` attribute owned by the gate instance — the runner is constructed per-gate. | AC-RUN-CTX-1 — perf test constructs one `GateRunner` per `gate_id` (build / test / trace) wired with the corresponding `Gate` instance; calls `await runner.run(ctx)`. |
| C-C-3 | block | `def test_gate_latency_within_budget(...)` is sync; `GateRunner.run` is `async def` per S5-02 HARDENED AC-ASYNC-1. Sync invocation binds a coroutine; assertions vacuously succeed. | AC-ASYNC-1 — every perf test is `async def`. Project's `asyncio_mode = "auto"` makes `@pytest.mark.asyncio` redundant. |
| C-C-4 | block | `tests/fixtures/vcr/cassette-attempt-1.yaml` and `cassette-attempt-2.yaml` do not exist and are not the Phase 5 cassette layout. Per S5-05 HARDENED line 108: the actual cassette is the SINGLE FILE `tests/integration/gates/cassettes/stage6_retry_recovers.yaml` (one cassette, two recorded `interactions` — the LLM call sequence is read in cassette order). | AC-CASSETTE-1 — perf test uses the cassette at `tests/integration/gates/cassettes/stage6_retry_recovers.yaml`; `@pytest.mark.vcr(...)` decorator matches S5-05 exactly. AC-CASSETTE-INTERACT-1 — asserts cassette has ≥ 2 interactions in order (matches S5-05 AC-FENCE-COUNT-1's expectation). |
| C-C-5 | block | References row "`tests/fixtures/repos/breaking-change-cve/` (from Phase 4 / S5-05)" is wrong. The fixture is owned by **Phase 5 / S5-05** (Phase 4 has no S5-05; its top story is S5-04). | References row corrected to "from Phase 5 / S5-05 — `tests/fixtures/repos/breaking-change-cve/`". |
| C-C-6 | block | `pyproject.toml [tool.pytest.ini_options] addopts = "-m 'not perf'"` would **replace** the existing `-m "not bench and not phase_7_preview"`, breaking the bench + phase-7 exclusions. | AC-ADDOPTS-1 — extend to `-m "not bench and not phase_7_preview and not perf"`; AC asserts the exact substring is preserved. |
| C-C-7 | harden | `perf` and `slow` markers are not registered. Project enforces `--strict-markers`; any unregistered mark raises at collection. | AC-MARKER-1 — `pyproject.toml [tool.pytest.ini_options] markers` extended with `"perf: ...", "slow: ..."` rows. |
| C-C-8 | harden | The CI workflow `.github/workflows/perf.yml` is unspecified: which runner, which uv pin, which gh-action SHAs. Phase precedent (S6-05) ships `.github/workflows/kvm-smoke.yml` with SHA-pinned `actions/checkout@<sha>` + `astral-sh/setup-uv@<sha>`. | AC-CI-1 — workflow file mirrors S6-05's structure: SHA-pinned actions; triggers on `pull_request: {types: [labeled], labels: [perf]}` and `schedule: cron`; runs on the same self-hosted KVM runner S6-05 provisions (re-uses the cron infra). |
| C-C-9 | harden | `tools/perf/loop50.sh` is bash but the repo's `tools/` scripts are Python (`tools/fuzz_yarn_lock.py`, `tools/regenerate_probe_schemas.py`). Mixed-language `tools/` directory is a CLAUDE.md "Match conventions" violation. | AC-LOOP50-LANG-1 — `tools/perf/loop50.py` (Python `argparse`; same shebang `#!/usr/bin/env python3`); shells out to `uv run pytest` with the perf marker. |
| C-C-10 | harden | The retry-2 source-of-truth is left ambiguous ("wrap `GateRunner.run` ... or read from `attempts.jsonl`"). The arch (Component 5) already commits to `attempts.jsonl` carrying `started_at`/`ended_at` per `Attempt` row (S2-01 HARDENED). Reading the artifact is the only stable contract. | AC-RETRY-SRC-1 — retry-2 wall-clock comes from `Attempt.ended_at - Attempt.started_at` on `attempts.jsonl` rows (NOT from `time.monotonic_ns()` outside the runner — that would also count the test harness's setup time). |
| C-C-11 | nit | `tests/fixtures/load.py` was renamed to `tests/_helpers/fixtures.py::apply_fixture_patch` per S7-01 HARDENED AC-LOAD-LOC-1. Draft's `from tests.fixtures.load import load_fixture` is the pre-S7-01 import path. | TDD Red updated to `from tests._helpers.fixtures import apply_fixture_patch`. |

### Critic D — Design Patterns

| # | Severity | Finding | Resolution |
|---|---|---|---|
| C-D-1 | block | `tests/bench/_bench_kernel.py` already ships `Threshold` + `Verdict` (`Ok | CommentOnly | Fail`) — a tagged-union verdict with a pure `compare_to_baseline(measurements, baseline, thresholds, *, p95_seconds)` decision. Three existing consumers (bench_portfolio_walltime, bench_index_health_overhead, bench_portfolio_walltime_hosted_runner). `test_gate_latency` would be the **fourth** consumer — past rule-of-three, well past it. Story rolls its own raw `assert p50 <= ...` instead of constructing a `Threshold(comment_pct=..., fail_p95_s=BUDGETS[gate_id]['p95'])` and matching on the `Verdict`. | AC-KERNEL-1 — perf tests import and reuse `tests.bench._bench_kernel.compare_to_baseline`; the budget table maps to `Threshold` instances; an `Ok` verdict is the pass condition; `Fail` raises `AssertionError` with the kernel's pre-formatted summary. AC-KERNEL-2 — no `assert p50 <= ...` raw expression in either perf test file (AST-scan in `tests/schema/`). |
| C-D-2 | harden | The trend row is described as a `{ts, git_sha, runner_name, gate_id, samples, p50, p95}` dict — primitive obsession on `git_sha` (raw `str`), no validation, no `extra='forbid'`. Future trend-consumer code will defensively `dict.get(...)` rather than know the shape. | AC-SCHEMA-1 — `tests/perf/_models.py` exports `LatencySample` and `RetryBudgetSample` Pydantic models with `frozen=True, extra='forbid'` mirroring `ObjectiveSignals` discipline. Fields type-annotated with NewTypes where available (`WorkflowId`, `RunId`, `SignalKind`); `git_sha` is `str` (no NewType yet) but constrained `Field(pattern=r"^[0-9a-f]{7,40}$")`. AC-SCHEMA-2 — `record_sample(path, model: LatencySample | RetryBudgetSample)` is typed; raw dict passing is a `TypeError`. |
| C-D-3 | harden | `record_sample(path, row)` mixes pure computation (constructing the row) and impure I/O (append to file). | AC-PURE-1 — `tests/perf/_recorder.py` splits into `to_jsonl_line(model) -> str` (pure) and `append_jsonl_line(path: Path, line: str) -> None` (impure shell). Mirrors S6-03 / S7-01 HARDENED `apply_fixture_patch` pattern. |
| C-D-4 | harden | The two perf tests use slightly different paths and conventions. The autouse `warm_pull` fixture is the single "imperative shell" the perf suite has; everything else should be pure. Story doesn't explicitly call out the functional-core / imperative-shell split. | AC-FCIS-1 — `tests/perf/conftest.py` is the only impure module under `tests/perf/`; AST scan asserts no `open(..., "a")` / `Path.write_*` / `subprocess.run` in any `test_*.py` perf file (those calls go through `_recorder.append_jsonl_line` only). |
| C-D-5 | nit | `BUDGETS` table is duplicated in the test body — comments cite the source but no module-level constant. | AC-BUDGETS-CONST-1 — `tests/perf/_budgets.py` exports `LATENCY_BUDGETS: Final[Mapping[str, Threshold]]` and `RETRY_BUDGET_RATIO: Final[float] = 1.6`; one definition site per architectural commitment. |
| C-D-6 | nit | No newtype for `runner_name` (free `str`). The reference runner is one of a closed set ("docker-desktop-mac-m-series", "ci-linux-8core"). Closed set = `Literal` (or `StrEnum`). | AC-RUNNER-1 — `RunnerName: TypeAlias = Literal["docker-desktop-mac-m-series", "ci-linux-8core"]` in `tests/perf/_models.py`; `LatencySample.runner_name: RunnerName`. Future runner-set widening is a one-line `Literal` extension. |

## Stage 3 — Research

**Not invoked.** Every gap was answerable from HARDENED sibling reports + `tests/bench/_bench_kernel.py` + CLAUDE.md commitments. No arXiv / library-docs / external research required.

## Edits applied

The story file at [`../S7-02-perf-regression-gates.md`](../S7-02-perf-regression-gates.md) was edited in place. Summary of edits:

### 1. Status line

- Before: `**Status:** Ready`
- After: `**Status:** Ready (HARDENED 2026-05-25)`

### 2. New `Validation notes (2026-05-25)` block

Appended directly after the header. Cross-links every block-tier finding to the AC that resolves it, plus the `Notes for the implementer` carryforwards.

### 3. References block

- Corrected "(from Phase 4 / S5-05)" → "(from Phase 5 / S5-05)" for `breaking-change-cve`.
- Replaced phantom `tests/fixtures/vcr/cassette-attempt-{1,2}.yaml` with the single real cassette `tests/integration/gates/cassettes/stage6_retry_recovers.yaml` (one cassette, two interactions).
- Added `tests/bench/_bench_kernel.py` (kernel reuse — block C-D-1).
- Added `tests/integration/_helpers/vcr.py` and `tests/integration/_helpers/hooks.py` (S5-05 HARDENED — extractor + spy precedents).
- Added `tests/integration/gates/conftest.py` (S5-05 HARDENED — perf_gate_runner_factory mirrors).
- Added `src/codegenie/sandbox/contract.py` (`RunId` NewType source).
- Added `src/codegenie/gates/contract.py` (`GateContext`, `Attempt` shape source — S1-04 HARDENED).
- Added `tools/fuzz_yarn_lock.py` (Python-tools convention precedent — block C-C-9).
- Added the Phase ADR `0011-no-verdict-cache-in-phase-5.md` already-present row's context (the retry-2 budget depends on it).
- Added the Phase ADR `0004-dind-default-macos-with-gate-isolation-class.md` already-present row's context (the budget is DiD-pinned).

### 4. Acceptance criteria — replaced the 8-AC draft with a sectioned 28-AC hardened set

Headers: **A.** Test layout + markers + addopts (4) | **B.** Runner construction + async surface (3) | **C.** Latency-test correctness (5) | **D.** Retry-2 budget correctness (4) | **E.** Mutation-witness tests (3) | **F.** Trend-row schema + recorder (4) | **G.** Bench-kernel reuse (2) | **H.** Warm-pull discipline (2) | **I.** CI workflow + tooling (3) | **J.** Static guards (2). Every AC carries an `AC-XX-N` ID; every observable claim has a paired test in the rewritten TDD plan.

### 5. Implementation outline — replaced the 8-step prose outline with a numbered 10-step outline

Names: `_budgets.py` (Final-tuple budgets table mapping to `Threshold` instances); `_models.py` (`LatencySample`, `RetryBudgetSample`, `RunnerName`); `_recorder.py` (split pure `to_jsonl_line` + impure `append_jsonl_line`); shared `perf_gate_runner_factory` and `perf_gate_context` fixtures in `tests/perf/conftest.py`; the two perf test files as `async def` with kernel-driven assertions; the two mutation-witness tests; the Python `tools/perf/loop50.py`; the `pyproject.toml` `addopts` + `markers` extension (one combined edit); the `.github/workflows/perf.yml` SHA-pinned workflow.

### 6. TDD plan rewrite

Red examples now: (a) `async def`, (b) keyword-only `GateRunner` construction via the shared factory, (c) `await runner.run(ctx)` with a proper `GateContext`, (d) `compare_to_baseline(...)` returning a `Verdict` whose `Ok` branch is the pass condition, (e) `LatencySample` Pydantic-model instantiation, (f) the witness-test pair. The previous Red example's three structural bugs (sync, phantom APIs, raw `assert`) are gone.

### 7. Files to touch

Extended with the new module split (`_budgets.py`, `_models.py`, `_recorder.py`); the witness tests (`test_gate_latency_witness.py`, `test_retry_2_budget_witness.py`); the Python `loop50.py` replacing the bash variant; the cassette-path reuse row clarified ("READ-ONLY — owned by S5-05; no edits").

### 8. Out of scope

Added: editing `GateRunner` to add `run_single_gate` (S5-02 owns the API; perf story does not widen it); recording new cassettes (S5-05 owns); reinventing `Threshold` or `Verdict` (bench-kernel owns); cross-runner budget normalization (out of scope per arch); cost emission (S7-03 owns).

### 9. Notes for the implementer

Added: (a) the kernel-reuse path and how to map `Threshold.fail_p95_s` to the §Goal 10 p95 numbers; (b) the `Attempt.ended_at - Attempt.started_at` precedent for retry-wall measurement; (c) the warm-pull tradeoff ("imperative shell — only impure module under `tests/perf/`"); (d) the `gate_isolation_class` pin and the `pytest.skip` path for non-DiD runners; (e) the `High-level-impl.md §Step 7 Done criteria #2`'s "≤ 1 %" wording vs. the math (1/50 = 2 %) — the story chooses the strict reading; flag for an editorial fix in High-level-impl.md; (f) the `_p95_for_small_n` helper's design note (max() at N=5, switch to interpolated quantile at N≥20 — future-proof comment).

### 10. Internal-doc drift surfaced (not patched here)

- `High-level-impl.md §Step 7 done-criteria #2` says "flake rate ≤ 1 % over 50 runs" but 1 failure / 50 runs = 2 %. Story chooses the strict reading ("0 failures over 50 runs"); High-level-impl editorial amendment is out of scope for this story but flagged.
- `phase-arch-design.md §Performance regression tests` and §Goal 10 are mutually consistent.

## Verdict

**HARDENED.** The goal is sound and traces to phase exit criteria; the prescribed implementation had reachable API errors, statistical bugs, and missed an established kernel-reuse opportunity. All block-tier issues are now closed by ACs that reference the load-bearing precedents (S5-02, S5-05, S2-01, `_bench_kernel`). The executor's first attempt has a fighting chance.

**Pre-conditions to flag for the executor:**
- S5-02 (`GateRunner`), S5-05 (`breaking-change-cve` fixture + cassette + `_helpers/vcr.py` + `_helpers/hooks.py`), S2-01 (`attempts.jsonl` with `started_at`/`ended_at`), and S1-04 (`GateContext`) must be GREEN before this story can execute.
- If any of the above is still BLOCKED or pre-GREEN at executor time, this story is blocked; do not stub. The executor's attempt log should record the missing precondition and stop.
