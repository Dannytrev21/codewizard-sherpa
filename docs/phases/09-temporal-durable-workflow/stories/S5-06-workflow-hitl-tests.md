# Story S5-06 — Workflow-level happy-path + HITL signal + subgraph-resume tests

**Step:** Step 5 — Postgres checkpointer adapter + workflow definitions
**Status:** Ready
**Effort:** M
**Depends on:** S5-02 (`VulnRemediationWorkflow` body + signals + query), S5-04 (`MultiPluginParentWorkflow` body + `coordination_policy` `match` arms), S4-05 (`run_vuln_subgraph` fat activity — required for the subgraph-resume integration test against a real `PostgresCheckpointerAdapter`), S5-01 (`PostgresCheckpointerAdapter` — consumed by the subgraph-resume integration test)
**ADRs honored:** Phase 9 ADR-0014 (`MultiPluginParentWorkflow` typed-error behavior — `temporal-ui` visibility); Phase 9 ADR-0010 (asymmetric activity granularity — the subgraph-resume test exercises the fat-activity SIGKILL→resume path that justifies the asymmetric choice); Phase 9 ADR-0011 (Postgres checkpointer — the subgraph-resume integration test against a real testcontainers Postgres is the load-bearing cross-process resume evidence); production ADR-0009 (humans always merge — HITL test verifies the signal-driven merge-outcome path; never an auto-merge); production ADR-0033 (sum types — `HumanReviewDecision = Approved | Rejected | Deferred` exhaustive handling).

## Context

S5-02 and S5-04 ship workflow bodies + one happy-path unit test each. This story extends test coverage to the *full surface* the workflows commit to:
- **Happy path (depth)** — every emitted event in the canonical 14-record sequence is observed and ordered correctly.
- **HITL pause + resume** — workflow parks on `wait_condition(human_review_decision)`; signal arrives days later (simulated via `WorkflowEnvironment` time-skipping); workflow resumes; `MergeOutcome` is emitted synchronously (`@critical_event`); workflow exits cleanly. Rejection and `Deferred` paths covered.
- **Parent workflow** — `coordination_policy="all_or_nothing"` and `"best_effort"` raise typed `NotImplementedError`; the failure is visible in `temporal-ui` history (the `WorkflowExecutionFailedEvent` carries the ADR-0014 pointer in its `failure.message`).
- **Subgraph mid-kill resume** — integration test against real Postgres (testcontainers) + real Temporal dev server: kill the activity worker mid-`run_vuln_subgraph`; resume on a fresh worker; assert the LangGraph node-level checkpoint state is byte-identical (cross-process resume — the load-bearing G1 lynchpin per ADR-0011).

These tests are *workflow-level*, not the build-time fences from S5-05 (replay-determinism) or the runtime G1 durability test from S8-01. They sit between: more than unit, less than full kill-worker-resume. Together with S5-05, they form the green-light suite for declaring the workflow bodies "shipped."

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Control flow — Happy path (recipe-route, warm cache, no human pause)` — the 14-record sequence (`WorkflowStarted, PluginResolved, BundleBuilt, RouteDecided, TrustGatePassed, RecipeApplied, PatchApplied, PrOpened, MergeOutcome (sync), WorkflowCompleted` plus the 4 prep events).
  - `../phase-arch-design.md §Decision points` — the five `match` branches the HITL test exercises (decision #4: `human_review_decision` signal).
  - `../phase-arch-design.md §Edge case 11 — Human-review-signal arrives after weeks` — the days-long park-resume semantics being validated.
  - `../phase-arch-design.md §Edge case 17 — MultiPluginParentWorkflow child fails` — `WorkflowFailureError → SomeMerged`; this story tests the `NotImplementedError` path of unimplemented coordination policies.
  - `../phase-arch-design.md §Goals G1 — Durability` + `§Risks specific to this step (run_vuln_subgraph)` — heartbeat-survives-slow-Postgres correctness; subgraph resume from same checkpoint.
- **Phase ADRs:**
  - `../ADRs/0014-multi-plugin-parent-workflow-as-temporal-shape.md §Consequences` — typed `NotImplementedError` in the workflow body's `match` arm; visible in `temporal-ui`.
  - `../ADRs/0011-checkpointer-backend-postgres.md §Consequences` — pool exhaustion, cross-process resume contract.
  - `../ADRs/0010-activity-granularity-asymmetric.md` — why the subgraph-mid-kill resume test is specifically the `run_vuln_subgraph` activity, not workflow-level retry.
- **Production ADRs:**
  - `docs/production/adrs/0009-humans-always-merge.md` — HITL `Approved` triggers `MergeOutcome`; never auto.
  - `docs/production/adrs/0042-multi-plugin-coordination-for-both-workflows.md` — the typed-error semantics for unimplemented policies.
- **Implementation plan:**
  - `../High-level-impl.md §Step 5 — Done criteria` — covers `tests/workflows/test_vuln_remediation_workflow.py`, `test_multi_plugin_parent_workflow.py`, `test_hitl_pause_resume.py`, `test_subgraph_resume_determinism.py`.
- **Sibling stories:**
  - `S5-02-vuln-remediation-workflow.md` — owns the happy-path test stub; this story extends it.
  - `S5-04-multi-plugin-parent-workflow.md` — owns the 2-child happy-path test stub; this story extends with the typed-error visibility test.
  - `S4-05-run-vuln-subgraph-activity.md` — the fat-activity body the subgraph-resume test kills mid-flight.
  - `S5-05-replay-determinism-replayer.md` — uses the same HITL fixture this story records.
  - `S8-01-kill-worker-resume.md` — the *runtime* version of the subgraph-resume test under N kill offsets; this story tests the single-kill case as the ramp-up.
- **Existing code seams:**
  - `src/codegenie/durable/workflows/vuln_remediation.py` (S5-02), `multi_plugin_parent.py` (S5-04).
  - `src/codegenie/durable/activities/run_vuln_subgraph.py` (S4-05) — body to kill mid-flight.
  - `src/codegenie/durable/checkpointer.py` (S5-01) — `PostgresCheckpointerAdapter` consumed by the subgraph-resume test.

## Goal

Ship four test files that collectively validate (1) the full happy-path emission trace, (2) the HITL `Approved | Rejected | Deferred` signal-driven branches, (3) `MultiPluginParentWorkflow` unimplemented-coordination-policy typed-error visibility in `temporal-ui` history, (4) `run_vuln_subgraph` mid-flight activity-kill resume against real Postgres reads identical LangGraph checkpoint state. Tests use `WorkflowEnvironment.start_local()` with time-skipping for (1)-(3); test (4) uses `testcontainers Postgres + temporal dev server`. None of these tests are `@pytest.mark.flaky`. The subgraph-resume test is *not* the G1 kill-worker-resume test (S8-01 ships that with N kill offsets); this is the single-offset ramp-up that demonstrates the path works at all.

## Acceptance criteria

### A — Test file inventory

- [ ] **AC-A1** `tests/workflows/test_vuln_remediation_workflow.py` — extends S5-02's happy-path test. New test functions: `test_full_event_emission_trace_in_order`, `test_state_query_during_each_phase`, `test_workflow_completes_with_completed_decision_merged`.
- [ ] **AC-A2** `tests/workflows/test_hitl_pause_resume.py` — new file. Tests: `test_workflow_parks_on_await_human_review`, `test_approved_signal_resumes_and_emits_merge_outcome`, `test_rejected_signal_resumes_and_emits_workflow_terminated`, `test_deferred_signal_keeps_workflow_parked`, `test_signal_after_long_wait_via_time_skip` (simulates days-long park).
- [ ] **AC-A3** `tests/workflows/test_multi_plugin_parent_workflow.py` — extends S5-04's test stubs. New tests: `test_all_or_nothing_failure_visible_in_temporal_history`, `test_best_effort_failure_visible_in_temporal_history`, `test_typed_error_message_contains_adr_pointer`.
- [ ] **AC-A4** `tests/integration/test_subgraph_resume_determinism.py` — new file. Test: `test_kill_activity_mid_subgraph_then_resume_reads_identical_checkpoint`. Marked `@pytest.mark.integration`; requires `testcontainers Postgres + temporalio dev server`.

### B — Full happy-path emission trace

- [ ] **AC-B1** `test_full_event_emission_trace_in_order` — drives the workflow through the happy path with mocked activities; collects every `emit_event` call's `EventPayload.kind`; asserts the ordered list matches:
  ```
  ["WorkflowStarted", "PluginResolved", "BundleBuilt", "RouteDecided",
   "TrustGatePassed", "RecipeApplied", "PatchApplied", "PrOpened",
   "MergeOutcome", "WorkflowCompleted"]
  ```
  Length is 10 (the 14-record total in `phase-arch-design.md` counts 4 prep events the activities emit internally — those are accounted for by the activity mocks). Strict order assertion; out-of-order = build break.
- [ ] **AC-B2** Synchronous-flush invariant: `MergeOutcome` and `WorkflowTerminated` (when present) are emitted with the synchronous-flush bypass active — verified by inspecting the activity mock's `EmitEventInput.capability.flush_mode` or equivalent flag the activity sets based on the payload kind's `@critical_event` membership.

### C — `state()` query during each phase

- [ ] **AC-C1** `test_state_query_during_each_phase` — drives the workflow stepwise; after each activity completes (via barrier in the activity mock), queries `state()`; asserts the returned `VulnLedger` variant matches the expected per-phase variant:
  - After `WorkflowStarted` emit: `NeedsPlan`
  - After `resolve_plugin + build_bundle + route + run_vuln_subgraph`: `PatchApplied`
  - After `github_open_pr`: `AwaitingHumanReview`
  - After `human_review_decision(Approved)`: `Completed(decision="merged")`
- [ ] **AC-C2** `state()` query is **idempotent** during pause — calling it 5 times during `AwaitingHumanReview` returns the same `VulnLedger.AwaitingHumanReview` instance value 5 times (Pydantic frozen equality); no side effects observable in the event log.

### D — HITL `Approved` path

- [ ] **AC-D1** `test_workflow_parks_on_await_human_review` — drive workflow to `AwaitingHumanReview`; *do NOT* send signal; assert via `WorkflowEnvironment.sleep(timedelta(hours=24))` time-skip that the workflow does NOT progress; `state()` still returns `AwaitingHumanReview`.
- [ ] **AC-D2** `test_approved_signal_resumes_and_emits_merge_outcome` — park workflow; send `human_review_decision(Approved(reviewer_id="alice", reviewed_at=workflow.now()))`; assert workflow exits with `state() == Completed(decision="merged")`; final emitted event is `MergeOutcome(outcome="merged", reviewer="alice")`; `MergeOutcome` is the **synchronous-flush** variant (verify via the activity mock's flush-mode flag).

### E — HITL `Rejected` path

- [ ] **AC-E1** `test_rejected_signal_resumes_and_emits_workflow_terminated` — park workflow; send `human_review_decision(Rejected(reviewer_id="bob", reason="security-review-failed"))`; assert workflow exits with `state() == Completed(decision="closed")` (or `FailedUnrecoverable`, depending on S5-02's chosen mapping — verify against S5-02's actual implementation); final emitted event is `WorkflowTerminated(by="reviewer", reason="rejected")` (synchronous-flush — `@critical_event`).

### F — HITL `Deferred` path

- [ ] **AC-F1** `test_deferred_signal_keeps_workflow_parked` — park workflow; send `human_review_decision(Deferred(reviewer_id="carol", revisit_at=workflow.now() + timedelta(days=3)))`; assert via time-skip that the workflow does NOT exit; `state()` still returns `AwaitingHumanReview`; the `_review_decision` attribute is reset to None (so the wait_condition re-arms — verify via direct state check OR a subsequent `Approved` signal that *does* exit the workflow).
- [ ] **AC-F2** After `Deferred`, a subsequent `Approved` signal *does* resume — establishes that `Deferred` is a re-park, not a terminal state.

### G — Days-long park via time-skip

- [ ] **AC-G1** `test_signal_after_long_wait_via_time_skip` — park workflow; advance virtual clock by 30 days via `env.sleep(timedelta(days=30))`; send `Approved`; assert workflow exits cleanly. Wall-clock test duration ≤ 5 s (time-skip is virtual).
- [ ] **AC-G2** Asserts the workflow's `wait_condition(human_review_decision)` does NOT time out (workflow has no internal timeout on the wait — operator-driven only). If S5-02 added a configurable timeout, this AC accommodates by using a 100-day skip > the timeout and asserting the appropriate terminal state instead.

### H — `MultiPluginParentWorkflow` typed-error visibility

- [ ] **AC-H1** `test_all_or_nothing_failure_visible_in_temporal_history` — dispatch `MultiPluginDispatch(coordination_policy="all_or_nothing", ...)`; await the workflow handle; on failure, fetch the full event history via `await handle.fetch_history()`; assert at least one `WorkflowExecutionFailedEvent` (or equivalent type) is present; assert its `failure.message` contains `"Phase 10"` AND `"ADR-0014"` AND `"all_or_nothing"`.
- [ ] **AC-H2** `test_best_effort_failure_visible_in_temporal_history` — symmetric; assert message contains `"best_effort"`.
- [ ] **AC-H3** `test_typed_error_message_contains_adr_pointer` — both unimplemented policies' error messages include the literal substring `docs/phases/09-temporal-durable-workflow/ADRs/0014-multi-plugin-parent-workflow-as-temporal-shape.md` — Phase 10 contributors grep for this.

### I — Subgraph mid-kill resume against real Postgres (integration)

- [ ] **AC-I1** `test_kill_activity_mid_subgraph_then_resume_reads_identical_checkpoint` — `@pytest.mark.integration`. Setup:
  1. Start testcontainers Postgres; run `make migrate` (Phase-9 alembic for `events` schema).
  2. Instantiate `PostgresCheckpointerAdapter` against the shared pool.
  3. Start a `temporalio` dev server (in-process).
  4. Register `VulnRemediationWorkflow` + `run_vuln_subgraph` (real, not mocked) + minimal mocks for the other activities.
  5. Start the workflow with a fixture `VulnRemediationRequest` that drives `run_vuln_subgraph` through ≥ 2 LangGraph nodes (the heartbeat lifecycle exercises).
  6. After the first heartbeat (verified via a barrier), forcibly cancel the activity worker (`worker.shutdown()` or process kill).
  7. Start a fresh activity worker; await the workflow result.
- [ ] **AC-I2** Assert: the resumed activity reads the *same* LangGraph checkpoint state as the pre-kill activity wrote — captured by inspecting the `langgraph_checkpoints` table directly via psycopg; byte-equal `state` blob across the two reads.
- [ ] **AC-I3** Assert: the workflow's final `VulnLedger` is `Completed(decision="merged")` (or the test-fixture's expected terminal); the kill+resume is invisible to the workflow body (workflow sees one `run_vuln_subgraph` activity completion event).
- [ ] **AC-I4** Test wall-clock ≤ 60 s under typical CI conditions; if longer, the test must be marked `@pytest.mark.slow` (but NOT `@pytest.mark.flaky`).

### J — Anti-flake discipline

- [ ] **AC-J1** None of the four test files is decorated with `@pytest.mark.flaky`. Grep fence (extension of S5-05's AC-G1) covers `tests/workflows/test_vuln_remediation_workflow.py`, `test_hitl_pause_resume.py`, `test_multi_plugin_parent_workflow.py`, and `tests/integration/test_subgraph_resume_determinism.py`.
- [ ] **AC-J2** No `time.sleep(N)` calls inside test bodies — `WorkflowEnvironment.sleep(...)` time-skipping only. Avoids wall-clock flake.
- [ ] **AC-J3** Activity mocks use deterministic barriers (`asyncio.Event` / `asyncio.Barrier`) rather than `time.sleep` to coordinate test phases.

### K — Gates

- [ ] **AC-K1** `ruff format`, `ruff check` clean. `mypy --strict` over the test files passes (test files have `frozen=True` mocks; type-check via `pytest_collection_modifyitems` if needed).
- [ ] **AC-K2** `make test` includes these tests by default (NOT behind `-m bench` or `-m e2e`). The integration test (`test_subgraph_resume_determinism.py`) is `-m integration`; integration tests run in the CI matrix (per existing CI config; mirror the pattern Phase-3 sets).

## Implementation outline

1. **Extend `tests/workflows/test_vuln_remediation_workflow.py`.**
   - Add the three new test functions (AC-A1).
   - Reuse the existing `env` and activity-mock fixtures from S5-02.
   - The "trace" test collects emit calls; asserts order strictly.
2. **Create `tests/workflows/test_hitl_pause_resume.py`.**
   - Five tests covering the four signal paths + the long-wait variant.
   - Use `WorkflowEnvironment.sleep(timedelta(days=N))` for virtual time-skip.
   - Activity mocks: `run_vuln_subgraph` returns a successful `SubgraphOutcome.Completed`; `github_open_pr` returns a `PrOpened` synthetic PR URL; `emit_event` collects calls.
3. **Extend `tests/workflows/test_multi_plugin_parent_workflow.py`.**
   - Add the three typed-error-visibility tests (AC-A3).
   - Use `await handle.fetch_history()` (or the SDK's current API for retrieving the workflow's event history); search for `WorkflowExecutionFailedEvent`; inspect its `failure.message`.
4. **Create `tests/integration/test_subgraph_resume_determinism.py`.**
   - Marked `@pytest.mark.integration`.
   - Fixture chain:
     - `pg_container` — testcontainers Postgres.
     - `alembic_upgrade(pg_container)` — runs `make migrate`-equivalent against the container.
     - `pg_pool(pg_container)` — `psycopg_pool.AsyncConnectionPool` against the container's DSN.
     - `checkpointer_adapter(pg_pool)` — `PostgresCheckpointerAdapter(pool=pg_pool)`.
     - `temporal_dev_server()` — `WorkflowEnvironment.start_local()` (or `start_time_skipping=False` if real-time semantics matter).
   - Test body:
     - Start workflow via the client; in parallel, monitor heartbeats via a side-channel (e.g., the activity emits a heartbeat marker into a shared `asyncio.Queue` via the test harness).
     - On first heartbeat, `worker.shutdown()` (cancels in-flight activity).
     - Read `langgraph_checkpoints.checkpoints` directly via psycopg; capture the `state` BYTEA.
     - Start a fresh worker; wait for workflow completion.
     - Read `langgraph_checkpoints.checkpoints` again at the same `thread_id` + `checkpoint_id`; assert byte-equal state.
     - Assert workflow's terminal `VulnLedger`.
5. **Extend the anti-flake-marker fence (from S5-05's `test_no_flake_marker_on_replay.py`).**
   - Generalize to walk all files matching `tests/workflows/*.py` and `tests/integration/test_subgraph_resume_*.py`; assert absence of `@pytest.mark.flaky` / `@pytest.mark.skip` / `pytest.skip(`.

## TDD plan — red / green / refactor

### Red

**Test file: `tests/workflows/test_hitl_pause_resume.py`** (representative — others follow the same shape)

```python
import pytest
from datetime import timedelta
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from codegenie.durable.workflows.vuln_remediation import VulnRemediationWorkflow
from codegenie.durable.workflows._types import (
    VulnRemediationRequest, HumanReviewDecision, Approved, Rejected, Deferred,
)
from codegenie.sherpa.vuln.state import AwaitingHumanReview, Completed

@pytest.fixture
async def env():
    async with await WorkflowEnvironment.start_local() as env:
        yield env

async def test_workflow_parks_on_await_human_review(env, fake_activities_to_pr_open):
    async with Worker(env.client, task_queue="vuln-remediation-node-npm",
                      workflows=[VulnRemediationWorkflow], activities=fake_activities_to_pr_open):
        handle = await env.client.start_workflow(
            VulnRemediationWorkflow.run,
            VulnRemediationRequest(repo_id="repo-A", attempt_id="att-1", ...),
            id="wf-park", task_queue="vuln-remediation-node-npm",
        )
        # Wait until parked.
        for _ in range(50):
            ledger = await handle.query("state")
            if isinstance(getattr(ledger, "ledger", ledger), AwaitingHumanReview):
                break
            await env.sleep(0.1)
        # Time-skip 24 hours; assert still parked.
        await env.sleep(timedelta(hours=24))
        ledger = await handle.query("state")
        assert isinstance(getattr(ledger, "ledger", ledger), AwaitingHumanReview)

async def test_approved_signal_resumes_and_emits_merge_outcome(env, fake_activities_to_pr_open):
    async with Worker(env.client, task_queue="vuln-remediation-node-npm",
                      workflows=[VulnRemediationWorkflow], activities=fake_activities_to_pr_open):
        handle = await env.client.start_workflow(
            VulnRemediationWorkflow.run,
            VulnRemediationRequest(repo_id="repo-A", attempt_id="att-2", ...),
            id="wf-approved", task_queue="vuln-remediation-node-npm",
        )
        await _wait_until_parked(handle, env)
        await handle.signal("human_review_decision", Approved(reviewer_id="alice", reviewed_at=...))
        result = await handle.result()
        final_state = await handle.query("state")
        assert isinstance(getattr(final_state, "ledger", final_state), Completed)
        # Final emitted event is MergeOutcome with synchronous-flush capability.
        last_emit = fake_activities_to_pr_open.emit_event_calls[-1]
        assert last_emit.input.payload.kind in {"MergeOutcome", "WorkflowCompleted"}
        # Find the MergeOutcome emit (penultimate, or final depending on ordering)
        merge_emits = [c for c in fake_activities_to_pr_open.emit_event_calls
                       if c.input.payload.kind == "MergeOutcome"]
        assert len(merge_emits) == 1
        # @critical_event variants are sync-flushed:
        assert merge_emits[0].input.capability.flush_mode == "synchronous" \
            or merge_emits[0].input.flush_synchronously is True  # match S3-03's actual flag

async def test_rejected_signal_resumes_and_emits_workflow_terminated(env, fake_activities_to_pr_open):
    ...

async def test_deferred_signal_keeps_workflow_parked(env, fake_activities_to_pr_open):
    # Park; signal Deferred; time-skip 1 day; assert still parked; signal Approved; assert exits.
    ...

async def test_signal_after_long_wait_via_time_skip(env, fake_activities_to_pr_open):
    # Park; env.sleep(timedelta(days=30)); signal Approved; assert exit.
    ...

async def _wait_until_parked(handle, env, max_iters=50):
    for _ in range(max_iters):
        ledger = await handle.query("state")
        if isinstance(getattr(ledger, "ledger", ledger), AwaitingHumanReview):
            return
        await env.sleep(0.1)
    pytest.fail("workflow did not park on AwaitingHumanReview")
```

**Test file: `tests/workflows/test_multi_plugin_parent_workflow.py`** (extending S5-04's stubs)

```python
async def test_all_or_nothing_failure_visible_in_temporal_history(env, fake_activities_all_success):
    async with Worker(env.client, task_queue="vuln-remediation-node-npm",
                      workflows=[MultiPluginParentWorkflow, VulnRemediationWorkflow],
                      activities=fake_activities_all_success):
        dispatch = MultiPluginDispatch(
            dispatch_id="DSP-FAIL-001", repo_id="repo-A",
            work_items=(PluginWorkItem(plugin_id="x", request=VulnRemediationRequest(...)),),
            coordination_policy="all_or_nothing",
        )
        handle = await env.client.start_workflow(
            MultiPluginParentWorkflow.run, dispatch, id="parent-fail-001",
            task_queue="vuln-remediation-node-npm",
        )
        with pytest.raises(Exception):
            await handle.result()
        history_events = [e async for e in handle.fetch_history_events()]
        failed_events = [e for e in history_events if "WorkflowExecutionFailed" in str(e.event_type)]
        assert failed_events, "expected WorkflowExecutionFailedEvent in history"
        message = failed_events[0].workflow_execution_failed_event_attributes.failure.message
        assert "Phase 10" in message
        assert "ADR-0014" in message
        assert "all_or_nothing" in message
        assert "0014-multi-plugin-parent-workflow-as-temporal-shape.md" in message
```

**Test file: `tests/integration/test_subgraph_resume_determinism.py`** (integration; testcontainers + temporal dev server)

```python
import pytest
from datetime import timedelta
import psycopg
from testcontainers.postgres import PostgresContainer
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from codegenie.durable.workflows.vuln_remediation import VulnRemediationWorkflow
from codegenie.durable.checkpointer import PostgresCheckpointerAdapter
from codegenie.durable.activities.run_vuln_subgraph import run_vuln_subgraph
# ... other activity imports

@pytest.fixture(scope="module")
def pg_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg

@pytest.fixture
async def pg_pool(pg_container):
    # alembic upgrade + AsyncConnectionPool factory; identical to S2-02 + S2-03 setup
    ...

@pytest.fixture
async def checkpointer_adapter(pg_pool):
    return PostgresCheckpointerAdapter(pool=pg_pool)

@pytest.mark.integration
async def test_kill_activity_mid_subgraph_then_resume_reads_identical_checkpoint(
    pg_container, pg_pool, checkpointer_adapter, ...
):
    async with await WorkflowEnvironment.start_local() as env:
        # Start first worker; register run_vuln_subgraph (real) + mocked others.
        heartbeat_q = asyncio.Queue()
        first_worker = Worker(
            env.client, task_queue="vuln-remediation-node-npm",
            workflows=[VulnRemediationWorkflow],
            activities=[
                run_vuln_subgraph_with_heartbeat_emit(heartbeat_q, checkpointer_adapter),
                ... mocked others ...
            ],
        )
        first_worker_task = asyncio.create_task(first_worker.run())
        handle = await env.client.start_workflow(
            VulnRemediationWorkflow.run,
            VulnRemediationRequest(repo_id="repo-A", attempt_id="att-kill", ...),
            id="wf-resume-test", task_queue="vuln-remediation-node-npm",
        )
        # Wait for first heartbeat from the subgraph activity.
        await heartbeat_q.get()
        # Capture the checkpoint state.
        async with pg_pool.connection() as conn:
            rows = await conn.execute(
                "SELECT thread_id, checkpoint_id, state FROM langgraph_checkpoints.checkpoints WHERE thread_id LIKE %s ORDER BY ts DESC LIMIT 1",
                (f"wf-resume-test%",)
            )
            row_before = (await rows.fetchone())
        # Forcibly shut down the first worker.
        first_worker.shutdown()
        await first_worker_task
        # Start a fresh worker.
        second_worker = Worker(
            env.client, task_queue="vuln-remediation-node-npm",
            workflows=[VulnRemediationWorkflow],
            activities=[run_vuln_subgraph_with_heartbeat_emit(heartbeat_q, checkpointer_adapter), ...],
        )
        async with second_worker:
            result = await handle.result()
        # Read checkpoint again.
        async with pg_pool.connection() as conn:
            rows = await conn.execute(
                "SELECT thread_id, checkpoint_id, state FROM langgraph_checkpoints.checkpoints WHERE thread_id LIKE %s ORDER BY ts DESC LIMIT 1",
                (f"wf-resume-test%",)
            )
            row_after = (await rows.fetchone())
        # Byte-equal state: at the kill-offset checkpoint, the resumed activity reads back the same state.
        assert row_before[2] == row_after[2], "LangGraph checkpoint state diverged after resume"
        final_state = await handle.query("state")
        assert isinstance(getattr(final_state, "ledger", final_state), Completed)
```

**Test file: anti-flake fence extension** (`tests/fence/test_no_flake_marker_on_workflow_tests.py`)

```python
from pathlib import Path

TARGETS = [
    Path("tests/workflows/test_vuln_remediation_workflow.py"),
    Path("tests/workflows/test_hitl_pause_resume.py"),
    Path("tests/workflows/test_multi_plugin_parent_workflow.py"),
    Path("tests/integration/test_subgraph_resume_determinism.py"),
]

def test_no_flake_marker_on_workflow_tests():
    for path in TARGETS:
        src = path.read_text()
        for forbidden in ["@pytest.mark.flaky", "pytestmark = pytest.mark.flaky"]:
            assert forbidden not in src, f"Forbidden flake marker in {path}"
```

### Green

Implement the four test files per outline. Expected sizes: HITL test ~180 lines (5 tests × ~30 lines), multi-plugin extension ~80 lines (3 tests × ~25 lines), subgraph-resume integration ~150 lines (fixture chain is heavy), happy-path extensions ~80 lines.

### Refactor

- Extract the `_wait_until_parked(handle, env)` helper into `tests/workflows/conftest.py` — reused by HITL and S5-02.
- Extract the activity-mock-with-heartbeat-emit fixture into `tests/integration/conftest.py` if multiple tests need it.
- Document the `MergeOutcome` synchronous-flush invariant in a top-of-file comment with citation to ADR-0006.

## Files to touch

| Path | Why |
|---|---|
| `tests/workflows/test_vuln_remediation_workflow.py` | Extend with trace + per-phase state + completed-decision tests |
| `tests/workflows/test_hitl_pause_resume.py` | New: HITL signal-path tests (Approved, Rejected, Deferred, long-wait) |
| `tests/workflows/test_multi_plugin_parent_workflow.py` | Extend with typed-error visibility tests |
| `tests/integration/test_subgraph_resume_determinism.py` | New: subgraph mid-kill resume against testcontainers Postgres + Temporal dev server |
| `tests/workflows/conftest.py` | Shared `_wait_until_parked` helper + activity-mock fixtures |
| `tests/integration/conftest.py` | Shared testcontainers Postgres + temporal dev server fixtures |
| `tests/fence/test_no_flake_marker_on_workflow_tests.py` | Extended anti-flake-marker fence |
| `Makefile` | Ensure `make test` covers these; CI matrix wires `-m integration` |

## Out of scope

- **G1 N-kill-offset durability sweep.** S8-01 ships `tests/durability/test_kill_worker_resume.py` with N offsets across `run_vuln_subgraph`. This story is the *single*-kill ramp-up that proves the path is wired.
- **Temporal-cluster restart durability.** S8-02 ships `tests/durability/test_temporal_cluster_restart.py`. Out of scope here.
- **Worker credential blast-radius.** S8-03. Out of scope.
- **End-to-end with cassette LLM.** S6-04 (`test_workflow_e2e_postgres.py`) ships the cassette-driven full-stack test. This story uses mocked activities, not cassettes.
- **HITL signal during `run_vuln_subgraph`.** Per S5-02's contract, HITL park happens *after* `github_open_pr` lands; the subgraph's own HITL-pause (Phase-6 internal) is handled inside the activity. Not surfaced at the workflow body here.
- **`cancel` signal mid-subgraph.** S5-02 covers the happy-path cancel; mid-subgraph cancel propagation into the LangGraph state is a Phase-10 / Phase-6.5-conformance concern.
- **Replay-determinism per-Python-minor matrix.** S5-05 owns. This story's tests run on the host's Python minor only.

## Notes for the implementer

- **`WorkflowEnvironment.start_local()` time-skipping is virtual.** A 30-day skip costs ~ms wall-clock. The HITL long-wait test (AC-G1) MUST use this, never `time.sleep`.
- **`@pytest.mark.flaky` is forbidden across all four files.** Per Implementation risk #1 from `High-level-impl.md`. If a test is flaky in practice, it's a real signal — the activity mock's barriers are racy or the workflow body has a determinism issue. Fix the cause, not the symptom.
- **Activity mocks use deterministic barriers.** `asyncio.Event` for "wait until this phase completes" — not `time.sleep(N)`. The `WorkflowEnvironment` doesn't time-skip `time.sleep` (only `workflow.sleep`); a `time.sleep(60)` in a test will hang for 60 wall-clock seconds and probably flake.
- **`MergeOutcome` synchronous-flush verification.** The `@critical_event` decorator (S1-03) marks 5 variants; the activity (S4-02 `emit_event`) bypasses the batcher for marked variants and synchronously flushes. The test asserts this via the activity mock's recorded `flush_mode` flag. If S3-03's actual flag name differs (e.g., `is_critical_event`), adapt — the *behavior* is what we're checking.
- **`temporal-ui` visibility test (AC-H1) inspects the workflow history programmatically.** `handle.fetch_history_events()` (or current SDK equivalent) yields the same events the UI would render. The assertion is against the `failure.message` string — that's what an operator sees in the UI.
- **Subgraph-resume test is a load-bearing piece of evidence for ADR-0011.** It's the first place where cross-process resume against real Postgres is exercised end-to-end. S5-01's AC-E2 covers the cross-Adapter resume; this test covers the cross-worker resume (which is what G1 ultimately requires). If the test passes, ADR-0011 is *materially* validated.
- **`worker.shutdown()` is the canonical "kill" in tests.** Process-level SIGKILL is for S8-01; here, the shutdown call cancels the in-flight activity coroutine, which is structurally equivalent for the cross-process-resume semantics.
- **The heartbeat barrier is the test's clock.** Without it, the test races between "kill the worker" and "the activity has actually started writing checkpoints." Add an `activity.heartbeat(...)` call in `run_vuln_subgraph`'s body that, under test conditions, publishes the heartbeat to a side-channel queue. The test consumes from the queue to know when to kill.
- **Real Temporal dev server is fine for the integration test.** `WorkflowEnvironment.start_local()` spins one in-process. Don't use the docker-compose Temporal — testcontainers + in-process is faster and hermetic.
- **`tests/_replay_artifacts/` does NOT participate here.** That directory is S5-05's. This story's tests fail loudly via pytest's default machinery.
- **Test wall-clock budget.** Per AC-I4 + AC-K2: full Step-5 test suite (all four files) should run in < 3 minutes. The integration test is the long pole.
- **Deferred design opportunities** (record in attempt log): (a) Hypothesis-fuzzing of HITL signal sequences — Phase 13 observability; (b) parameterizing the activity-kill offset for a parameterized matrix — S8-01's job; (c) a `temporalio.workflow.Inspector` plugin for richer history assertions — Phase 16 ergonomics.
