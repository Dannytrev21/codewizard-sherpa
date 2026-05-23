# Story S8-01 — G1 kill-worker-resume durability test

**Step:** Step 8 — Durability test pass + adversarial sweep + CI gates
**Status:** Ready
**Effort:** L
**Depends on:** S6-03 (`TemporalVulnRemediationSut` bridge + `SutDigest` invariance), S5-05 (Replayer fixture establishes the "must not flake" discipline)
**ADRs honored:** P9-ADR-0004 (workflow determinism — replay-correctness is what makes kill-resume byte-identical), P9-ADR-0010 (activity granularity — `run_vuln_subgraph` is the [S]-shape that survives kills because its checkpointer state is in Postgres), P9-ADR-0011 (Postgres checkpointer is the resume substrate), P9-ADR-0013 (no Temporal port abstraction — the test uses `WorkflowEnvironment` directly).

## Context

This is the **G1 exit-criterion lynchpin** — the test that proves "Workflows survive process restarts without state loss" (roadmap §Phase 9). If this test does not exist and stay green, Phase 9 has not shipped its load-bearing promise, no matter how clean every other story is. The arch design calls it out by name in two places (§Goals item 1, §Testing strategy §Durability tests line 1011) and the High-level-impl §Step 8 done criteria pin it to **100 consecutive local runs + 10 consecutive PR runs** — the bar that catches flakes the moment they appear, not three weeks later when a contributor marks the test `@pytest.mark.flaky` and the whole phase silently degrades.

The implementation risk the architect named explicitly (§Implementation-level risks #1) is that this test gets `@pytest.mark.flaky`-quarantined the first time it fails on an unrelated PR. That quarantine *is* the failure mode. AC-1 below forbids `@pytest.mark.flaky` and `@pytest.mark.e2e` on this test; AC-7 wires the consecutive-run bar into the executor's validation gate.

The test mechanism: spin up `WorkflowEnvironment.start_local()` with a real Postgres testcontainer + real `PostgresCheckpointerAdapter`, start `VulnRemediationWorkflow` for a Phase-6 canonical case, wait for `run_vuln_subgraph` activity to begin (signaled by the first heartbeat), then simulate a worker kill by cancelling the activity worker's asyncio task (`asyncio.CancelledError` propagation) at N programmed offsets, restart the worker on the same task queue, and assert that (a) the workflow completes, (b) the terminal `VulnLedger` state is byte-identical to a single-process run, (c) the `SutDigest` (from S6-03) is byte-identical across both runs. The activity's `AttemptId` idempotence (Step 4) + LangGraph checkpointer resume (Step 5) are what make the post-kill resume read the same state as the pre-kill in-flight state — this test is the integration test that proves all those pieces compose.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals item 1` (line 16) — G1 acceptance phrasing.
  - `../phase-arch-design.md §Testing strategy §Durability tests` (line 1011) — names this test explicitly and pins it out of `@pytest.mark.e2e`.
  - `../phase-arch-design.md §Implementation-level risks #1` (line 1145 area) — flake-quarantine failure mode.
  - `../phase-arch-design.md §Activity catalog §run_vuln_subgraph` — heartbeat cadence (5 s) sub Temporal's 30 s heartbeat-timeout; idempotence-on-`AttemptId`.
- **Phase ADRs:** `../ADRs/0010-activity-granularity-asymmetric.md` (S-shape rationale), `../ADRs/0011-checkpointer-backend-postgres.md` (resume substrate), `../ADRs/0004-workflow-determinism-enforcement-three-layers.md` (Replayer-as-Step-5 + this test compose to give byte-identical resume).
- **Stories that feed this:**
  - `S4-05-run-vuln-subgraph-activity.md` — the fat activity this test kills; the `AttemptId` idempotence assertion lives there.
  - `S5-01-postgres-checkpointer-adapter.md` — the resume substrate.
  - `S5-05-replay-determinism-replayer.md` — the "must not be `@pytest.mark.flaky`" discipline this story extends.
  - `S6-03-temporal-sut-bridge.md` — `TemporalVulnRemediationSut.digest()` is the byte-identical-state assertion target.
- **High-level-impl:** `../High-level-impl.md §Step 8 §Features delivered` line 228; §Done criteria line 237.

## Goal

Ship `tests/durability/test_kill_worker_resume.py` that kills the activity worker at N programmed offsets across `run_vuln_subgraph`, restarts it on the same task queue, and asserts byte-identical terminal `VulnLedger` state + byte-identical `SutDigest` — without `@pytest.mark.e2e` or `@pytest.mark.flaky`, passing 100 consecutive local runs + 10 consecutive PR runs.

## Acceptance criteria

**The G1 test itself (AC-1 through AC-4)**

- [ ] **AC-1** `tests/durability/test_kill_worker_resume.py` exists. The test function carries **no** `@pytest.mark.e2e`, **no** `@pytest.mark.flaky`, **no** `@pytest.mark.skip`, **no** `@pytest.mark.xfail`. Verified by a meta-test (`tests/fence/test_durability_test_not_quarantined.py`) that parses the file AST and asserts the absence of those markers — a future "we'll just mark it flaky for now" PR fails CI.
- [ ] **AC-2** Test uses `temporalio.testing.WorkflowEnvironment.start_local()` with a real Postgres testcontainer wired to `PostgresCheckpointerAdapter` (S5-01). No `WorkflowEnvironment.start_time_skipping()` (time-skipping silently changes the activity-kill semantics).
- [ ] **AC-3** Test parametrizes over **N kill offsets** where N ≥ 3: at least one kill before the first checkpoint write, one between checkpoints, one after the last checkpoint but before activity return. Offsets are detected via a deterministic side-channel (e.g., a counter in a test-only `EventLogWriteCapability` wrapper that fires on the K-th event). Each parametrized case asserts terminal state independently — no shared mutable fixture state across cases.
- [ ] **AC-4** For each kill offset, the test asserts:
  - **AC-4.a** Workflow completes (no `WorkflowFailureError`).
  - **AC-4.b** Terminal `VulnLedger` variant is `Completed` (or the deterministic terminal for the chosen Phase-6 canonical case) — byte-identical to the no-kill reference run (compared via `pickle.dumps(ledger)` SHA-256, or per-field comparison if pickle is undesirable per the codebase's no-`pickle.loads` rule — prefer the per-field route).
  - **AC-4.c** `TemporalVulnRemediationSut.digest()` (S6-03) is byte-identical to the no-kill reference run. This is G5 piggybacking on G1.
  - **AC-4.d** The event log records exactly one `RunVulnSubgraphStarted` and exactly one `RunVulnSubgraphCompleted` (idempotence-on-`AttemptId` worked — no double-execution).

**Mechanics — the kill (AC-5 through AC-6)**

- [ ] **AC-5** The worker kill is implemented as `worker_task.cancel()` followed by `await asyncio.wait_for(worker_task, timeout=5.0)` swallowing `asyncio.CancelledError`. Not `os.kill(pid, SIGTERM)` (subprocess-level kills are out of scope for unit-test infra and add noise; cluster-restart is S8-02's job). The test docstring names this scoping: "this test kills the worker task; `S8-02` kills the Temporal cluster."
- [ ] **AC-6** Restart: a fresh `Worker(task_queue=..., activities=[...], workflows=[...])` is constructed on the same task queue + same Postgres-backed checkpointer; `run()` awaited until the workflow completes. The same `WorkflowId` is preserved (Temporal resumes by `WorkflowId`).

**Determinism discipline (AC-7 through AC-8)**

- [ ] **AC-7** Consecutive-run bar: a CI workflow `.github/workflows/durability-soak.yml` runs `pytest tests/durability/test_kill_worker_resume.py` 10 times in a loop on every PR; one failure across the 10 fails the job. Locally, `scripts/soak-kill-worker-resume.sh N=100` runs the test 100 times and is documented in `docs/development.md`. Evidence (commit SHA + run logs) recorded in `_attempts/S8-01.md` at GREEN.
- [ ] **AC-8** Forensic-on-failure: the test captures `NondeterminismError.full_message` (Temporal SDK exposes this) and the recorded-vs-replayed history diff as a `pytest`-attached artifact when assertion fails, so the first time it goes red the contributor sees the diff, not a generic `AssertionError`.

**Hygiene (AC-9 through AC-12)**

- [ ] **AC-9** Test directory layout: `tests/durability/__init__.py` exists; `tests/durability/conftest.py` provides the `postgres_testcontainer` + `workflow_environment` fixtures (session-scoped where safe, function-scoped where state isolation matters).
- [ ] **AC-10** Reference run (no kill) is itself a fixture function reused by S8-02 + S8-04 — avoid copying the "happy path" setup three times. Surface this as `tests/durability/_fixtures/canonical_vuln_case.py`.
- [ ] **AC-11** `ruff check`, `ruff format --check`, `mypy --strict` clean on touched files. No `# type: ignore` introduced.
- [ ] **AC-12** Story status updated to `Done` after AC-7's evidence lands. Attempt log notes how long a single run takes on CI (target ≤ 30 s) so the 10-run soak fits the PR budget.

## Implementation outline

1. Add `tests/durability/__init__.py` + `tests/durability/conftest.py` with `postgres_testcontainer` fixture (testcontainers-python; PG 16) and `workflow_environment` fixture (`WorkflowEnvironment.start_local()`).
2. Add `tests/durability/_fixtures/canonical_vuln_case.py` exposing a function `build_canonical_case() -> VulnRemediationRequest` reusing a Phase-6 canonical case (cassette-replay, deterministic).
3. Implement `tests/durability/test_kill_worker_resume.py`:
   - `pytest_generate_tests` (or `@pytest.mark.parametrize("kill_offset", [...])`) over N ≥ 3 kill offsets.
   - Fixture `reference_terminal_state` (session-scoped) runs the no-kill case once and caches `(ledger_bytes, sut_digest, event_kinds)`.
   - Per-case: start the worker, dispatch the workflow, await the K-th event via the side-channel counter, `worker_task.cancel()`, await cancellation, build a fresh worker, await workflow completion, assert AC-4.a–d.
4. Add `tests/fence/test_durability_test_not_quarantined.py` — AST-walk asserting no quarantine markers on the test function (AC-1).
5. Add `scripts/soak-kill-worker-resume.sh` (N=100 by default) and document in `docs/development.md`.
6. Add `.github/workflows/durability-soak.yml` running the 10-pass loop on PRs.
7. Run `make check` end-to-end; run the local soak; record SHAs in `_attempts/S8-01.md`.

## TDD plan — red / green / refactor

**Red:** Write the test against the not-yet-wired test-only `EventLogWriteCapability` counter wrapper. Without the counter, the kill-offset detection fails → test errors. Equivalent red: the `_fixtures/canonical_vuln_case.py` import fails because the file does not exist. Both are red-by-construction at first commit.

**Green:** Implement the counter wrapper + canonical-case fixture + the cancel-restart dance. Each parametrized case goes green when (a) `WorkflowEnvironment` resumes the workflow on a fresh worker and (b) the LangGraph checkpointer's resume reads the same state — which it must, because S5-01 + S4-05 already shipped that property. If any case stays red, the regression is in S4-05's `AttemptId` idempotence or S5-01's checkpointer adapter — escalate, do not patch the test.

**Refactor:** Lift the per-case setup into helpers. Add the meta-test (AC-1) AFTER the test is green so a future flake-quarantine attempt fails CI. Record forensic-capture wiring (AC-8) by attaching the Temporal history JSON via `pytest`'s `record_property` or a `request.node.add_report_section` hook.

## Files to touch

| Path | Why |
|---|---|
| `tests/durability/__init__.py` | NEW — test package marker. |
| `tests/durability/conftest.py` | NEW — `postgres_testcontainer` + `workflow_environment` fixtures. |
| `tests/durability/_fixtures/__init__.py` | NEW — fixture package marker. |
| `tests/durability/_fixtures/canonical_vuln_case.py` | NEW — shared canonical Phase-6 case builder (reused by S8-02, S8-04). |
| `tests/durability/test_kill_worker_resume.py` | NEW — the G1 test. |
| `tests/fence/test_durability_test_not_quarantined.py` | NEW — meta-test forbidding `@pytest.mark.flaky` / `@pytest.mark.e2e` / `@pytest.mark.skip` / `@pytest.mark.xfail` on the G1 test (AC-1). |
| `scripts/soak-kill-worker-resume.sh` | NEW — 100-run local soak. |
| `.github/workflows/durability-soak.yml` | NEW — 10-run PR soak. |
| `docs/development.md` | EDIT — document the soak scripts + how to read the forensic artifact on failure. |

## Out of scope

- **Cluster-restart kill** — S8-02 handles `temporal kill && temporal start` separately.
- **Compromised-worker blast radius** — S8-03.
- **Perf canaries** — S8-04.
- **Subprocess-level `SIGTERM` kills** — out of scope per AC-5 docstring scoping; the activity-worker `asyncio.CancelledError` path is what the durability promise rests on.
- **Continue-as-new on 20-min cap** — open question #1 in the manifest; Phase 10.

## Notes for the implementer

- **The 10-PR-runs CI loop is the load-bearing flake catcher.** A test that's green 99% of the time goes red on the 100th run; the loop turns "tolerable flake" into "build break before merge". Resist the urge to make the loop conditional / nightly — it must run on every PR that touches `src/codegenie/durable/` or `tests/durability/`. Single-CI-run-per-PR shipped a flake into `master`; multi-run-per-PR catches it.
- **No `@pytest.mark.flaky`.** The architect named this in §Implementation-level risks #1 + §Implementation risk in S5-05's manifest entry. If a contributor's PR adds the marker, AC-1's meta-test fails CI; reviewers see the violation, not the test history.
- **Forensic-on-failure (AC-8) earns its keep the first time.** Without it, the first red test in six months gets re-run, comes back green, and a real determinism bug ships. With it, the contributor sees `NondeterminismError: history mismatch at event 17: recorded RunVulnSubgraphStarted with run_id=X, replayed with run_id=Y` and the offending diff is obvious.
- **Reuse the canonical case in S8-02 + S8-04.** Three identical case-builders rot independently; one shared builder rots in one place.
- **Per-case state isolation matters.** If `kill_offset=10` leaves Postgres rows behind that `kill_offset=20` reads, you have a test that's "sometimes" green. Either truncate the testcontainer between cases (slow) or use a unique `WorkflowId` per case (fast). Prefer the latter; `WorkflowId = f"durability-{kill_offset}-{uuid4()}"` (the `uuid4` is *test*-side, not workflow-side, so it does not break determinism).
- **Don't piggyback `SutDigest` invariance assertion onto AC-4.c if S6-03 hasn't shipped the bridge.** This story's dep on S6-03 is real; if S6-03 is partial, surface the gap in `_attempts/S8-01.md` and gate AC-4.c on the bridge landing.
- **The 30 s per-run budget is real.** A 60 s run × 10 = 10 min PR overhead, which contributors will quietly route around. Profile the single-run cost; if it exceeds 30 s, the cassette-replay case is too large — shrink it. S5-05's Replayer test should already be using a sub-30 s case.
- **Determinism interlock with S5-05.** S5-05's Replayer test catches *transitive* non-determinism (LangGraph version drift, dict-iteration changes). S8-01 catches *behavioral* non-determinism (worker dies → resumes → produces different state). The two are non-overlapping: a workflow that passes the Replayer but fails kill-resume has a non-deterministic *activity* (probably `run_vuln_subgraph`'s LangGraph node hits an unseeded RNG or unsorted dict); a workflow that passes kill-resume but fails the Replayer has a non-deterministic *workflow body* (probably an unfenced `time.now()` or `set()` literal). When red, attribute the failure to the right layer before patching either test.
- **The K-th-event side-channel must be deterministic.** If the kill offset depends on wall-clock timing (`asyncio.sleep(0.3); kill`), the test flakes by construction. The side-channel is the event-log row count for the workflow under test — read the row count from Postgres, compare against the target offset, kill when matched. This is a tiny per-iteration query, fine for the test budget.
- **`AttemptId` plumbing is what makes idempotence work, and you should verify it on red.** If AC-4.d ever fails (more than one `RunVulnSubgraphCompleted`), the bug is almost certainly an `AttemptId` that isn't stable across the kill — Temporal's at-least-once delivery rebuilt the input with a fresh `AttemptId` instead of reusing the original. S4-05 ships the stable-`AttemptId` derivation; verify on failure before chasing ghosts elsewhere.
