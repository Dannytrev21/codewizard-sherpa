# Story S8-04 — Gap-1 route-activity overhead canary + G6/G11 perf canaries

**Step:** Step 8 — Durability test pass + adversarial sweep + CI gates
**Status:** Ready
**Effort:** M
**Depends on:** S8-01 (canonical Phase-6 case fixture + worker harness), S8-02 (cluster lifecycle helpers for the throughput run)
**ADRs honored:** P9-ADR-0003 (per-workflow BLAKE3 chain — the relaxation that gives G6 ≥3k events/sec; the throughput canary's correctness predicate), P9-ADR-0010 (activity granularity — the route-activity overhead is the [P]/[B] cost the canary measures), P9-ADR-0007 (two task queues — the throughput canary spreads across 5 activity workers, all on the `vuln-remediation-node-npm` queue). Closes Gap-1 (route-activity overhead canary) noted in the manifest + arch §Gap analysis line 1127.

## Context

Four perf canaries land in this single story (they share infra — one nightly-bench setup, one ratchet-baseline mechanism, four assertions):

1. **`tests/perf/test_phase09_route_activity_overhead.py`** (Gap-1): `execute_activity("route", ...)` p95 ≤ 40 ms over a 100-call fixture portfolio. The 10 ms headroom over Phase-8's 50 ms hot-view budget is the Gap-1 closeout — if the canary fails, escape valve (a) or (b) in arch §Gap analysis line 1127 lands as a follow-up ADR (0016+).
2. **`tests/perf/test_phase09_token_canary.py`** (G11): `total_tokens == 0` on the cassette-replay throughput run. No real LLM call may slip into a deterministic test path; the fence is a hard zero.
3. **`tests/perf/test_phase09_throughput.py`** (G6): ≥ 3,000 events/sec sustained from 5 activity workers writing into the canonical event log across 100 cassette-replay workflows. Postgres pool sizing (S2-02) defaults are validated here; regressions auto-fail.
4. **`tests/perf/test_phase09_cold_replay_latency.py`**: a 200-event history replay completes in ≤ 1.5 s p95 — the cold-replay budget that ensures the Replayer test (S5-05) and the durability tests (S8-01, S8-02) don't slow CI past the per-PR budget as event counts grow.

All four canaries run **under `-m bench`, nightly only** — they don't gate every PR (too expensive, too noisy). They write to `tests/bench/baselines/phase09_*.json`; baselines ratchet downward only (regressions fail; improvements are committed manually as the new baseline). Arch §Testing strategy §CI gates line 1049–1053 + High-level-impl line 231 + manifest §S8-04 are the canonical sources.

The Gap-1 canary is the most architecturally load-bearing: if `route`'s activity-dispatch overhead pushes p95 past Phase-8's 50 ms hot-view budget, the Phase-8/Phase-9 layering is in trouble and a future ADR rewires it (either collapse `resolve_plugin`+`build_bundle`+`route` into one Activity, or import `route` into the workflow body under a determinism fence — see arch §Gap analysis line 1127 for both escape valves). The canary's job is to surface that problem with quantitative evidence.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals item 6` (line 21) — G6 acceptance.
  - `../phase-arch-design.md §Goals item 11` — G11 token canary phrasing.
  - `../phase-arch-design.md §Testing strategy §Performance canaries` (line 1049–1053) — names all four files.
  - `../phase-arch-design.md §Gap analysis §Gap-1` (line 1127) — route-activity overhead, the 40 ms p95 bar, the two escape valves.
- **Phase ADRs:**
  - `../ADRs/0003-per-workflow-blake3-prev-hash-chain.md` — the relaxation that makes G6 reachable.
  - `../ADRs/0010-activity-granularity-asymmetric.md` — names the [P]/[B] route shape whose overhead this canary measures.
- **Stories that feed this:**
  - `S3-07-event-log-throughput-bench.md` — the event-log-only throughput bench; this story extends it to a full-workflow throughput run.
  - `S8-01-kill-worker-resume.md` — shares `_fixtures/canonical_vuln_case.py`.
  - `S2-02-durable-settings.md` — pool sizing defaults (`minsize=2, maxsize=20`) the canary stresses.
- **High-level-impl:** `../High-level-impl.md §Step 8 §Features delivered` line 231; §Implementation-level risks #3 + #4 (the back-pressure / pool-sizing risks this canary surfaces).

## Goal

Ship four perf canaries — Gap-1 route-activity overhead (`p95 ≤ 40 ms`), G11 token canary (`total_tokens == 0`), G6 throughput (`≥ 3k events/sec from 5 workers`), cold-replay latency (`200-event history ≤ 1.5 s p95`) — under `-m bench` nightly, with ratchet baselines under `tests/bench/baselines/`.

## Acceptance criteria

**Route-activity overhead canary — Gap-1 (AC-1)**

- [ ] **AC-1** `tests/perf/test_phase09_route_activity_overhead.py` exists, marked `@pytest.mark.bench`. Fixture: a 100-call sequence of `execute_activity("route", routing_input)` against the real `route` activity (S4-03) backed by the Phase-8 fixture portfolio under cassette replay. Asserts `numpy.percentile(latencies_ms, 95) ≤ 40.0`. Baseline file `tests/bench/baselines/phase09_route_activity_overhead.json` is committed at GREEN time with the observed p50/p95/p99 + the SHA + machine-fingerprint of the run. CI loads the baseline and fails if the new run's p95 > `1.10 × baseline_p95` (the 10% regression ratchet).

**Token canary — G11 (AC-2)**

- [ ] **AC-2** `tests/perf/test_phase09_token_canary.py` runs the same 100-workflow throughput fixture as AC-3 (shared) under cassette replay; collects `total_tokens` from every `LlmInvoked` event in the event log (Phase-6 ships this field); asserts `sum(total_tokens) == 0`. **Exact zero, not ε.** Any non-zero hit means a real LLM call leaked into the deterministic path — surface the offending workflow ID in the failure message for forensic debugging.

**Event-log throughput canary — G6 (AC-3)**

- [ ] **AC-3** `tests/perf/test_phase09_throughput.py` runs 100 cassette-replay `VulnRemediationWorkflow` instances across 5 activity workers on the `vuln-remediation-node-npm` queue, real Postgres, real Temporal `start_local`. Measures total events committed / total elapsed time. Asserts `events_per_sec >= 3000.0`. Records p95 commit latency; asserts ≤ 15 ms (G6's secondary clause). Baseline file `tests/bench/baselines/phase09_throughput.json` carries the same SHA + fingerprint + measured throughput; 10% downward regression fails CI.

**Cold-replay-latency canary (AC-4)**

- [ ] **AC-4** `tests/perf/test_phase09_cold_replay_latency.py` records a workflow history of ≥ 200 events (using S5-05's recorded-history fixture mechanism), then runs `WorkflowReplayer.run_replay_workflows` against it 50 times, measuring per-run wall-clock. Asserts `numpy.percentile(replay_times, 95) ≤ 1.5`. Baseline `tests/bench/baselines/phase09_cold_replay_latency.json`.

**Ratchet-baseline mechanism (AC-5 through AC-7)**

- [ ] **AC-5** Baseline files share a schema:
  ```json
  {
    "metric": "p95_route_activity_overhead_ms",
    "value": 28.3,
    "captured_at_sha": "...",
    "captured_at_iso": "2026-05-...",
    "machine_fingerprint": {"cpu_model": "...", "cores": 8, "ram_gib": 16, "platform": "linux-x86_64"},
    "regression_threshold_ratio": 1.10
  }
  ```
  Schema lives at `tests/bench/baselines/_schema.json` and is validated by every canary at load time. A future "let me bump the baseline 2x to land this PR" attempt requires editing the JSON in a PR — visible at review time, not silent. A `tests/fence/test_bench_baseline_schema.py` validates all four files conform.
- [ ] **AC-6** Machine-fingerprint mismatch: if the runner's `cpu_model`/`cores` differ from `captured_at_machine_fingerprint`, the canary emits a warning + `pytest.skip` (not a fail) — measurements across heterogeneous hardware are noise. CI workflow pins runner type so the fingerprint stays stable. Local runs on a contributor's laptop simply skip with a clear message.
- [ ] **AC-7** Nightly CI workflow `.github/workflows/bench-phase09.yml` runs `pytest -m bench tests/perf/` and uploads the four current measurements as a JSON artifact; failure (any of the four canaries' p95/throughput off-baseline) opens (or updates) a GitHub Issue tagged `perf-regression` with the baseline vs current diff. The issue-opener step is best-effort (skip if `gh` is unavailable in the runner — log only) but the test failure itself is the load-bearing signal.

**Fault-injection scenario for risk #3 (AC-8)**

- [ ] **AC-8** Per the architect's call-out in High-level-impl §Implementation-level risks #3 (EventBatchWriter back-pressure under Postgres latency spikes): AC-3's throughput run **also** runs a paired variant with `pg_sleep(2.0)` injected mid-run via `pg_stat_statements` (or equivalent — a `BEFORE INSERT` trigger on a marker table that pauses every Nth insert). Variant asserts: back-pressure into Temporal kicks in (`emit_event` activity retries land per `RetryPolicy`); no event is double-written (chain-verify on read returns zero `ChainTamperDetected`); throughput-during-spike degrades gracefully (not catastrophically — `events_per_sec >= 500` during the spike).

**Hygiene (AC-9 through AC-11)**

- [ ] **AC-9** All four canaries are under `@pytest.mark.bench` — they do NOT run in `make test`; they run in `make bench` (a new Makefile target if not present: `bench: pytest -m bench`).
- [ ] **AC-10** `ruff check`, `ruff format --check`, `mypy --strict` clean on the test files.
- [ ] **AC-11** Story Status → `Done` after the four canaries produce baselines and the nightly CI workflow has executed at least once successfully. `_attempts/S8-04.md` records the first-night measurements + the chosen machine-fingerprint, plus a note on whether the AC-3 throughput run cleared 3k events/sec at the default `psycopg_pool` sizing (per High-level-impl risk #4, this validates or invalidates S2-02's default).

## Implementation outline

1. Add `tests/bench/__init__.py` + `tests/bench/baselines/__init__.py` if missing. Author `tests/bench/baselines/_schema.json`.
2. Author `tests/bench/_helpers.py` exposing `load_baseline(metric_name) -> Baseline`, `check_machine_fingerprint(baseline) -> None | SkipResult`, `assert_within_ratchet(metric_value, baseline) -> None`.
3. Implement the four `tests/perf/test_phase09_*.py` files, each calling the helpers; each capturing per-run JSON to `tests/bench/baselines/<metric>.json` (write-on-empty, never overwrite — humans bump baselines in PRs).
4. Add `Makefile bench:` target if not present.
5. Add `.github/workflows/bench-phase09.yml` running `pytest -m bench tests/perf/ -v` on a nightly cron; uploads artifact; runs `gh issue` open-or-update step gracefully degrading.
6. Add `tests/fence/test_bench_baseline_schema.py` validating the four baseline files against the schema.
7. Run `make bench` locally; commit baselines; record in `_attempts/S8-04.md`.

## TDD plan — red / green / refactor

**Red:** Write each canary with the threshold asserted but **without** the baseline file committed. The `load_baseline` helper raises `FileNotFoundError` → test errors → red. This is red-by-construction at the first commit; the green step requires landing the baseline alongside the test.

**Green:** Run the canary once on the CI runner type, capture the measured value, commit the baseline JSON with that value. Subsequent runs pass as long as they stay within the 10% ratchet. The Gap-1 canary's first measurement is the load-bearing signal — if p95 > 40 ms on first measurement, the canary stays red and Gap-1's escape valve fires (open a follow-up phase ADR-0016 per arch §Gap analysis line 1127).

**Refactor:** Factor the four canaries' shared scaffolding (`workflow_environment` fixture, `postgres_testcontainer` fixture, the 100-cassette-replay-workflow dispatcher) into `tests/perf/conftest.py`. The four test files reduce to ~30 lines each, mostly the threshold assertion + the metric capture. Avoid extracting a `Canary` base class; the four tests share *fixtures*, not *behavior* — the conftest is the right seam.

## Files to touch

| Path | Why |
|---|---|
| `tests/perf/test_phase09_route_activity_overhead.py` | NEW — Gap-1 canary. |
| `tests/perf/test_phase09_token_canary.py` | NEW — G11. |
| `tests/perf/test_phase09_throughput.py` | NEW — G6 + AC-8 fault-injection variant. |
| `tests/perf/test_phase09_cold_replay_latency.py` | NEW — cold-replay budget. |
| `tests/perf/conftest.py` | NEW or EDIT — shared `workflow_environment` + `postgres_testcontainer` + 100-workflow-dispatcher fixtures. |
| `tests/bench/__init__.py` | NEW (if missing) — package marker. |
| `tests/bench/_helpers.py` | NEW — `load_baseline`, `assert_within_ratchet`, `check_machine_fingerprint`. |
| `tests/bench/baselines/_schema.json` | NEW — baseline JSON schema. |
| `tests/bench/baselines/phase09_route_activity_overhead.json` | NEW — captured at GREEN. |
| `tests/bench/baselines/phase09_throughput.json` | NEW — captured at GREEN. |
| `tests/bench/baselines/phase09_cold_replay_latency.json` | NEW — captured at GREEN. |
| `tests/fence/test_bench_baseline_schema.py` | NEW — validates the baselines against the schema. |
| `Makefile` | EDIT — add `bench:` target if not present. |
| `.github/workflows/bench-phase09.yml` | NEW — nightly cron + ratchet check + artifact upload. |
| `docs/development.md` | EDIT — document `make bench`, how to read baseline failures, the "bump baseline" PR ritual. |

## Out of scope

- **Real-LLM (non-cassette) throughput runs** — Phase 13's cost-ledger story handles that; here the canaries are deterministic.
- **Cross-machine comparability** — AC-6's fingerprint-mismatch skip is the load-bearing scope; building cross-machine normalization (e.g., SPEC scores) is a separate problem.
- **Replacing S3-07's event-log-only bench** — that story still owns its narrower scope; this story adds the *whole-workflow* throughput.
- **Phase-10 portfolio-scale load** — that's Phase-10 territory; here we ship the 100-workflow infrastructure that Phase 10 will extend.
- **Continue-as-new evidence** — open question #1 in the manifest; if AC-3's throughput shows `run_vuln_subgraph` hitting the 20-min cap on any workflow, surface in `_attempts/S8-04.md` as a Phase-10 follow-up.

## Notes for the implementer

- **Baselines are SHA-recorded, not magic numbers.** The first night's run *is* the baseline. AC-5's schema enforces that — never hand-edit a baseline value without committing the SHA+date that captured it. The "bump baseline" PR ritual is a culture pattern; AC-5's schema is the mechanical lock.
- **The 10% ratchet ratio is conservative** for a reason: nightly noise on a CI runner is real (other tenants, kernel scheduler, etc.). 5% ratchet would flake; 10% catches actual regressions while tolerating noise. Surface the chosen ratio in the baseline JSON (not hardcoded) so a future calibration is a JSON edit.
- **Machine-fingerprint matters more than people expect.** A canary green on a c5.4xlarge and red on a c5.2xlarge looks like a regression; AC-6's skip is the correct response. The CI workflow pins the runner type (e.g., `ubuntu-24.04-large` or a self-hosted runner) — a runner change is itself a baseline-rotation event, surfaced in `_attempts/S8-04.md`.
- **Gap-1's escape valves (arch line 1127) only fire if the canary stays red after a real attempt to optimize.** A first-night red doesn't immediately collapse the activity boundary — it opens an investigation. Surface the first measurement honestly; the architect will route to the correct escape valve.
- **AC-8's `pg_sleep`-injection is non-trivial.** The cleanest path is a `BEFORE INSERT` trigger on `events.events` that fires `pg_sleep(2.0)` only when a row in `_test_inject_latency` table is present — installable per-test, removable post-test. Surface the chosen mechanism in `_attempts/S8-04.md`; the goal is "back-pressure works", not "trigger plumbing is perfect".
- **Throughput numbers vary widely by environment.** 3k events/sec is achievable on a developer laptop with `psycopg_pool maxsize=20` and PG 16's defaults; CI runners may be slower. If first-night CI throughput is ≥ 3k events/sec — great, that's the baseline; if it's 2.5k events/sec, the canary stays red until either (a) Postgres pool tuning happens (per High-level-impl risk #4) or (b) the throughput target is renegotiated in a phase-ADR amendment. **Do not silently rebaseline below 3k events/sec** — the roadmap exit criterion is the hard bar.
- **The throughput canary is also the cleanest place to evidence ADR-0003's per-workflow-chain claim.** If you find chains are blocking cross-workflow throughput, the canary surfaces it; the relaxation in ADR-0003 should hold this number above 3k events/sec.
