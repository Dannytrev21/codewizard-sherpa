# Story S8-02 — Temporal-cluster-restart durability test

**Step:** Step 8 — Durability test pass + adversarial sweep + CI gates
**Status:** Ready
**Effort:** M
**Depends on:** S6-03 (`TemporalVulnRemediationSut` bridge + canonical case shape)
**ADRs honored:** P9-ADR-0011 (Postgres checkpointer survives Temporal cluster restart because workflow state is in Temporal's history *plus* LangGraph state in Postgres), P9-ADR-0012 (event-store topology — events in Postgres, workflow history in Temporal — both must survive a restart), P9-ADR-0013 (no Temporal port abstraction — test interacts with `temporalio` SDK directly).

## Context

S8-01 covers worker death (an `asyncio.CancelledError` propagation inside the worker process). S8-02 covers the complementary leg of G1: the **Temporal cluster itself** going down — `temporal server stop && temporal server start` — while in-flight workflows are mid-activity. The roadmap exit criterion ("Workflows survive process restarts without state loss") names both forms; arch §Goals item 1 + §Testing strategy line 1011 enumerate both files explicitly.

The mechanism: a real `temporal server` process (the `temporalio.testing.WorkflowEnvironment.start_local()` variant, or a docker-compose-launched cluster — the test picks the lightest path that exercises the *server* restart, not just the worker), a workflow started against it, then mid-flight `cluster.kill(); cluster.start()` (or equivalent: stop the server, restart, reconnect workers). The workflow's history is in Temporal's persistence (the auto-setup image's SQLite for local; Postgres in CI if we use Postgres-backed Temporal — see Notes). When the cluster comes back, in-flight workflow resumes from history; activity worker re-polls the task queue and picks up. Terminal `VulnLedger` byte-identical to a no-restart reference run.

This test is **complementary** to S8-01, not redundant: S8-01 kills the activity worker (workflow keeps running server-side; resumes on a fresh worker). S8-02 kills the server (workflow's runtime is gone; resumes from history when server returns). Both legs together prove G1; one without the other leaves a gap the architect named.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals item 1` (line 16) — G1 names both files.
  - `../phase-arch-design.md §Testing strategy §Durability tests` (line 1011) — names `test_temporal_cluster_restart.py`.
  - `../phase-arch-design.md §Event store topology` — the dual-source-of-truth (Temporal history + Postgres events) that must reconcile on restart.
- **Phase ADRs:**
  - `../ADRs/0011-checkpointer-backend-postgres.md` — LangGraph state in Postgres survives Temporal restart trivially because it's a separate DB.
  - `../ADRs/0012-event-store-topology-temporal-history-plus-postgres-events.md` — explains why both stores must agree after restart.
- **Stories that feed this:**
  - `S8-01-kill-worker-resume.md` — shares the canonical case fixture (`tests/durability/_fixtures/canonical_vuln_case.py`).
  - `S6-03-temporal-sut-bridge.md` — `SutDigest` byte-identical assertion.
  - `S2-01-docker-compose-dev.md` — the `infra/docker-compose.dev.yml` that this test may reuse for cluster lifecycle (alternative: in-process `WorkflowEnvironment`).
- **High-level-impl:** `../High-level-impl.md §Step 8 §Features delivered` line 229.

## Goal

Ship `tests/durability/test_temporal_cluster_restart.py` that kills the Temporal cluster mid-workflow and restarts it, asserting in-flight workflows resume and terminal `VulnLedger` state is byte-identical to a no-restart reference run.

## Acceptance criteria

**The test (AC-1 through AC-5)**

- [ ] **AC-1** `tests/durability/test_temporal_cluster_restart.py` exists. No `@pytest.mark.e2e`, `@pytest.mark.flaky`, `@pytest.mark.skip`, `@pytest.mark.xfail` on the test function. The meta-test from S8-01 (AC-1) extends to also scan this file — one allow-list, two test paths.
- [ ] **AC-2** Test uses a real Temporal cluster lifecycle — either:
  - **AC-2.a** Option A (preferred for unit-test speed): `WorkflowEnvironment.start_local()` instance, `await env.shutdown()` mid-workflow, then a fresh `WorkflowEnvironment.start_local()` against the **same persistence backend** (file-backed SQLite kept across the shutdown). The test asserts the workflow's `WorkflowId` resumes against the new instance.
  - **AC-2.b** Option B (heavier — gated by an env var `CODEGENIE_DURABLE_E2E_CLUSTER=1` and skipped by default): docker-compose stop/start of the `temporalio/auto-setup` container from S2-01.
  - The story ships AC-2.a unconditionally; AC-2.b lands as an optional path if AC-2.a's `WorkflowEnvironment` restart-with-persistence works in the SDK. If the SDK does not support persisting across `start_local` instances, **flag** in `_attempts/S8-02.md` and route through AC-2.b only.
- [ ] **AC-3** Restart timing: the cluster is killed **after** the workflow has started its first activity (signaled by the first heartbeat event landing in the Postgres event log, identical mechanism to S8-01's K-th-event side-channel) and **before** the workflow completes. A test-only callable in `_fixtures/canonical_vuln_case.py` exposes "wait for first heartbeat", reused.
- [ ] **AC-4** Per-restart assertions (same shape as S8-01 AC-4):
  - **AC-4.a** Workflow completes after restart (no `WorkflowFailureError`).
  - **AC-4.b** Terminal `VulnLedger` byte-identical to the no-restart reference run.
  - **AC-4.c** `TemporalVulnRemediationSut.digest()` byte-identical.
  - **AC-4.d** Event log: exactly one `RunVulnSubgraphStarted` and exactly one `RunVulnSubgraphCompleted` — no double-execution. Crucially: zero `ChainTamperDetected` events from the chain-verify-as-you-read path (S3-04) — proves the per-workflow BLAKE3 chain is intact across restart.
- [ ] **AC-5** Two restart cases parametrized: (i) restart *before* any LangGraph checkpoint write inside `run_vuln_subgraph`; (ii) restart *after* at least one LangGraph checkpoint write. Both must produce identical terminal state — case (ii) proves the checkpointer's resume-from-checkpoint path is exercised across cluster restart.

**Reconciliation discipline (AC-6 through AC-7)**

- [ ] **AC-6** Dual-store reconciliation: after restart-complete, the test asserts `temporal-cli workflow show --workflow-id <wid>` history event count equals the Postgres event-log count for that workflow (modulo Temporal's internal `WorkflowExecutionStarted` and similar lifecycle events — define the equivalence relation in a helper named `assert_history_and_event_log_agree(wid)` in `tests/durability/_fixtures/reconciliation.py`). This is the test that proves ADR-0012's dual-store-with-no-drift commitment under restart.
- [ ] **AC-7** Restart-during-batched-write case: if S3-02's `EventBatchWriter` had events queued when the cluster died, the test asserts those events either (a) all land post-restart or (b) all do not land — never a partial flush. Implementation: forcibly inject `await asyncio.sleep(0.5)` between batcher flush and cluster kill, then count events pre/post. Acceptance: the count is one of `{0, batch_size}`, never in between.

**Hygiene (AC-8 through AC-10)**

- [ ] **AC-8** Test runs in ≤ 60 s per case (two cases = ≤ 120 s total) on CI. If `start_local` cold-start dominates, surface in `_attempts/S8-02.md` and consider gating AC-2.b to nightly.
- [ ] **AC-9** `ruff check`, `ruff format --check`, `mypy --strict` clean on touched files.
- [ ] **AC-10** Story Status → `Done` after AC-4 + AC-6 + AC-7 land green.

## Implementation outline

1. Extend `tests/durability/_fixtures/canonical_vuln_case.py` (from S8-01) with a `wait_for_first_heartbeat(event_log, workflow_id) -> None` helper.
2. Add `tests/durability/_fixtures/reconciliation.py` exposing `assert_history_and_event_log_agree(wid, env, event_log)` — defines the equivalence relation between Temporal history events and Postgres event-log rows.
3. Implement `tests/durability/test_temporal_cluster_restart.py`:
   - `@pytest.mark.parametrize("restart_timing", ["before_checkpoint", "after_checkpoint"])`.
   - Setup: `start_local` env, dispatch workflow, await first heartbeat (or first LangGraph checkpoint write — detected via Postgres `langgraph_checkpoints.*` table row count).
   - Kill: `await env.shutdown()`.
   - Restart: build a fresh `start_local` env against the same persistence (or skip + flag to AC-2.b if persistence doesn't carry).
   - Resume: workflow handle by `WorkflowId`; await completion.
   - Assert AC-4 + AC-6 + AC-7.
4. Update `tests/fence/test_durability_test_not_quarantined.py` (added in S8-01) to also scan `test_temporal_cluster_restart.py`.
5. Run `make check`; record evidence in `_attempts/S8-02.md`.

## TDD plan — red / green / refactor

**Red:** Write the test against `wait_for_first_heartbeat` and `assert_history_and_event_log_agree` — both not yet defined. Test errors at collection → red.

**Green:** Implement the two helpers + the test body. The first restart-resume should "just work" because Temporal's history-based resume is well-trodden. The AC-7 batched-write boundary is where most of the implementation work lives: instrument `EventBatchWriter` (S3-02) with a test-only hook that lets the test pause between flush queue and Postgres commit, kill, restart, and observe that the post-restart Postgres reads agree with the recorded batched-event-set boundary. If S3-02 did not ship that hook, surface in `_attempts/S8-02.md` as a forward-dep break; the test can ship without AC-7 short-term but the story is BLOCKED-PARTIAL until AC-7 lands.

**Refactor:** The reconciliation helper (`assert_history_and_event_log_agree`) is reused by S8-03 (blast-radius reads from both stores) and S8-04 (the throughput canary's correctness oracle). Place it where both can import.

## Files to touch

| Path | Why |
|---|---|
| `tests/durability/test_temporal_cluster_restart.py` | NEW — the test. |
| `tests/durability/_fixtures/canonical_vuln_case.py` | EDIT — add `wait_for_first_heartbeat` helper. |
| `tests/durability/_fixtures/reconciliation.py` | NEW — `assert_history_and_event_log_agree`. |
| `tests/fence/test_durability_test_not_quarantined.py` | EDIT — scan also this new test file (AC-1). |
| `docs/development.md` | EDIT — document the `CODEGENIE_DURABLE_E2E_CLUSTER=1` opt-in (AC-2.b) if it ships. |

## Out of scope

- **Worker-kill resume** — S8-01.
- **Blast-radius adversarial** — S8-03.
- **Perf canaries** — S8-04.
- **Production-shape cluster restart** (3-pod Temporal, mTLS, leader election) — Phase 16; here we only prove single-instance-cluster resume.
- **Postgres restart** — distinct failure mode; arguably a follow-up. The G1 phrasing in the roadmap covers Temporal restart; Postgres restart is implicitly covered by `PostgresCheckpointerAdapter`'s pool reconnect behavior (S5-01 territory). Surface as a possible Phase-16 follow-up if accumulated evidence shows pool reconnect is fragile.

## Notes for the implementer

- **Persistence-across-`start_local` is the open question.** Read `temporalio.testing.WorkflowEnvironment.start_local` signature carefully: it may or may not expose a persistence-dir argument. If it doesn't, AC-2.a is unreachable and you must ship AC-2.b. The story can still GREEN on AC-2.b alone, but flag the route taken in `_attempts/S8-02.md` so future readers know.
- **The dual-store agreement assertion (AC-6) is what makes this test special.** S8-01 proves "workflow resumes". S8-02 proves "the two persistence stores reconcile". A future deploy that introduced a write to Temporal history without a paired event-log row would silently violate ADR-0012; AC-6 catches it.
- **AC-7's batched-write boundary is the failure mode the architect named in §Implementation-level risks #3** (Step 3's `EventBatchWriter` over-cap back-pressure). The test must instrument the batcher; if S3-02 did not ship the test hook, the story is BLOCKED-PARTIAL — do not paper over it.
- **No `time.sleep`-based polling** — use the event-log side-channel or `await wait_condition` against the Temporal SDK. Polling sleeps make this test the slowest one in the suite and the first to be flake-quarantined (which AC-1 forbids).
- **`temporal-cli workflow show` is fine in a test** — it's a subprocess call to an already-installed binary (via the `temporalio/auto-setup` image; in `start_local` mode the SDK exposes equivalent in-process APIs — prefer the in-process API to avoid subprocess fragility).
- **Forensic-on-failure parity with S8-01:** if AC-4 fails, attach both the Temporal history and the Postgres event-log dump. The forensic value of seeing them side-by-side is the difference between fixing the bug in an hour vs a day.
- **The `before_checkpoint` vs `after_checkpoint` distinction (AC-5) is the load-bearing parametrization.** Without `before_checkpoint`, the resume case is trivial (LangGraph never wrote state to Postgres, so the workflow re-starts the activity from scratch and gets the same result by deterministic-cassette construction). Without `after_checkpoint`, the LangGraph resume-from-checkpoint path (S5-01's `PostgresCheckpointerAdapter`) is never exercised end-to-end across a cluster restart. Both cases together prove both paths work; either alone leaves a gap.
- **The dual-store agreement test is more than a sanity check.** ADR-0012 (event-store topology — Temporal history *plus* Postgres events) is the architectural commitment that makes Phase 11's KG writeback and Phase 13's cost-ledger projection cheap to ship. Both downstream phases assume the two stores never drift. AC-6 is where Phase 9 *earns* that assumption — surface the equivalence-relation definition (Temporal history events ↔ Postgres event-log rows) in `_attempts/S8-02.md` so Phase 11's author can read it and trust it.
- **Restart-during-batched-write (AC-7) is risk #3 from High-level-impl made concrete.** The architect named the back-pressure → multiplicative-retry failure mode; AC-7 turns that into a test fixture. If S3-02 did not ship a test-hook into the batcher (most batchers don't), the cleanest path is to add one: a `BatcherTestHook` Protocol with a `before_postgres_commit` callable that defaults to `lambda: None` in production, and the test injects a coroutine that pauses the commit while the cluster gets killed. Surface this as a real S3-02 follow-up if needed.
- **The `WorkflowEnvironment.start_local` SDK semantics evolve.** Read the SDK version pinned in `pyproject.toml` and check its docs; if `start_local` ever changes how it handles persistence across instances, AC-2.a's viability changes. Surface the SDK version + the chosen route in `_attempts/S8-02.md` so a future SDK upgrade doesn't silently degrade this test.
- **Cluster-restart timing matters more than worker-restart timing.** A worker can die and resume in 1–2 s — fast enough that Temporal's task-queue poll picks up before any timeout fires. A cluster, even at `start_local` cold start, takes 3–10 s; if `run_vuln_subgraph`'s `start_to_close_timeout=20m` is the dominant cap, fine — but if any activity has a tight `schedule_to_start_timeout`, the cluster restart can blow past it and the workflow fails with a misleading error. Read `_POLICIES` (S4-01) carefully before testing; if any activity has `schedule_to_start_timeout < 30s`, surface the interaction in `_attempts/S8-02.md` and either bump the timeout or document the constraint.
- **Don't retrofit BLOCKED-PARTIAL into the story without flagging.** If AC-7 cannot ship because S3-02's batcher lacks the test hook, mark the story `BLOCKED-PARTIAL` explicitly, ship AC-1 through AC-6, and open a follow-up story that wires AC-7 once the hook lands. A silent "I'll come back to it" is the exact failure mode the manifest's `BLOCKED-PARTIAL` status was invented to surface.
- **Re-running this test on PR is fine** — unlike S8-01's 10-pass soak (the G1 lynchpin), this is a 2-case `make test` run. Single-pass-per-PR is sufficient; if flakes appear, treat as a real bug, not a flaky test.
