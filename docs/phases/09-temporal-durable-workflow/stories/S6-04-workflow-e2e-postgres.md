# Story S6-04 — End-to-end Postgres + Temporal integration test

**Step:** Step 6 — Worker process model + LangGraph↔Temporal bridge
**Status:** Ready
**Effort:** M
**Depends on:** S6-02 (worker bootstrap + capability minting), implicitly S5-02 / S5-04 (workflows), S5-01 (checkpointer adapter), S3-04 (event log)
**ADRs honored:** ADR-0011 (Postgres checkpointer — wired here against a real Postgres), ADR-0007 (two task queues — both pools register against the real cluster), ADR-0015 (loopback only — the dev cluster the test uses is `127.0.0.1`-bound), production ADR-0034 (event-sourcing canonical primitive — event-log contents asserted at terminal state)

## Context

`WorkflowEnvironment.start_local()` from S6-03's G5 test is in-memory and fast, but it does not exercise the real Postgres event-log persistence path, the real Postgres checkpointer, the real `temporal-server`'s persistence layer, or the real dev compose stack. A green G5 test with in-memory Temporal could still ship a workflow that crashes the moment it touches the real Postgres connection pool (wrong DSN format, missing alembic migration, pool exhaustion on the real driver, gRPC framing differences between local and real frontend, etc.).

This story is the **first end-to-end smoke**: real Postgres (via testcontainers OR the `make dev-up` cluster), real Temporal dev server, fake Redis, cassette-replay LLM. A full recipe-route `VulnRemediationWorkflow` runs in ~30 s; the test asserts (a) terminal `VulnLedger` state matches the canonical happy-path, (b) the event log contains the expected 12 events (1 sync + 11 batched per `phase-arch-design.md §Scenario 1`), (c) the BlobRef for the bundle was written and is resolvable, (d) the LangGraph checkpoint was persisted in the `langgraph_checkpoints` schema.

After this story, Phase 9 has its first piece of "the whole thing runs" evidence — the proof that the Phase 9 substrate is real, not a stack of unit-test mocks. S8-01 (G1 kill-worker-resume) and S8-02 (cluster restart) build on this fixture pattern.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Scenario 1 — Happy path: recipe-route vuln remediation, warm cache, no human pause yet` L334–368 — the exact sequence diagram + event count + wall-clock budget this test verifies. "≈14 Temporal-history records; 12 events emitted (1 sync + 11 batched); 0 tokens; 0 LLM calls; wall-clock ~3 s minus sandbox build."
  - `../phase-arch-design.md §Physical view (deployment)` L260–330 — the dev compose stack the test consumes.
  - `../phase-arch-design.md §Testing strategy §Integration (testcontainers)` L1010 — "`test_workflow_e2e_postgres.py` — real Postgres, real Temporal dev server, fake Redis, cassette-replay LLM. Full recipe-route workflow end-to-end (~30 s)."
  - `../phase-arch-design.md §C10 §Performance envelope` — "wall-clock ~3 s minus sandbox."
- **Phase ADRs:**
  - `../ADRs/0011-checkpointer-backend-postgres.md` — the real checkpointer wired here.
  - `../ADRs/0007-two-task-queue-partitioning-and-expansion-by-addition.md` — two-queue dispatch happens against the real cluster.
  - `../ADRs/0015-temporal-ui-loopback-only.md` — the dev cluster's `127.0.0.1` binding the test connects to.
- **Existing code:**
  - `src/codegenie/durable/bridge.py` (S6-03) — `TemporalVulnRemediationSut` from the bridge story (but this test bypasses the bridge to assert event-log + checkpointer side-effects directly).
  - `infra/docker-compose.dev.yml` (S2-01) — the compose file the test fixture brings up.
  - `src/codegenie/events/log.py` (S3-04) — `EventLog.read_workflow(workflow_id)` for the assertion phase.
  - `src/codegenie/events/blob_refs.py` (S3-05) — `BlobStore.resolve` for the BlobRef assertion.
- **External:**
  - `testcontainers-python` for Postgres + (optional) Temporal containers; alternative is shelling out to the existing `make dev-up`.
  - `pytest-cassette` or `vcrpy` for the cassette-replay LLM (the Phase-6 cassettes are reused).

## Goal

Land `tests/integration/test_workflow_e2e_postgres.py` that brings up a real Postgres + real Temporal dev server (via testcontainers OR the `make dev-up` stack), starts a `VulnRemediationWorkflow` happy-path case, awaits its terminal state, and asserts (a) `VulnLedger == Completed`, (b) event-log contents match the 12-event canonical sequence from `phase-arch-design.md §Scenario 1`, (c) the BlobRef for the bundle is byte-identical to the bundle bytes, (d) the LangGraph checkpointer recorded the expected node sequence, (e) `total_tokens == 0` (G11 cassette canary). Total wall-clock ≤30 s. This is the first piece of "real substrate" evidence in Phase 9.

## Acceptance criteria

### Fixture topology

- [ ] **AC-1 — Test uses real Postgres + real Temporal dev server + fake Redis + cassette-replay LLM.** Concretely: `pytest` fixture `e2e_stack` yields a `dataclass E2EStack(postgres_dsn: str, temporal_address: str, redis_client: FakeRedis, llm_cassette_path: Path)`. The fixture brings up the stack via testcontainers (or detects a running `make dev-up` cluster via `127.0.0.1:7233` reachability and reuses it; preference is testcontainers for hermetic CI).
- [ ] **AC-1a — Postgres comes up with the Phase-9 alembic migrations applied.** The fixture runs `alembic upgrade head` against the test database before yielding. Assert `events.events` and `events.blob_refs` tables exist; assert the `langgraph_checkpoints` schema is created by `PostgresCheckpointerAdapter.saver().setup()` (lazy schema bootstrap).
- [ ] **AC-1b — Temporal dev server is `temporalio.testing.WorkflowEnvironment.start_time_skipping()` against the testcontainer Temporal OR the `make dev-up` Temporal.** For CI hermetic: testcontainers `temporalio/auto-setup:1.25` image. For local dev: detect-and-reuse a running cluster (skip-or-warn if unavailable).
- [ ] **AC-1c — Fake Redis is `fakeredis.FakeAsyncRedis`.** The Phase-8 hot view (`PluginResolutionView`) is preloaded with the canonical case's plugin row before the workflow runs; this is the "warm cache" path of `Scenario 1`.
- [ ] **AC-1d — Cassette-replay LLM means `total_tokens == 0`.** The Phase-6 cassette fixture for the canonical case is reused; assert in AC-6 below.

### Workers come up against the real substrate

- [ ] **AC-2 — One workflow worker + two activity workers run against the real cluster.** The test brings up:
  - One `build_worker(kind=WORKFLOW, settings=test_settings, client=client, mint=<empty mint>)` task.
  - One `build_worker(kind=VULN_REMEDIATION_NODE_NPM, settings=test_settings, client=client, mint=<vuln mint>)` task.
  - One `build_worker(kind=SYSTEM, settings=test_settings, client=client, mint=<system mint>)` task.
  - All three run concurrently via `asyncio.gather` for the test duration; gracefully shut down at teardown.
- [ ] **AC-2a — Workers register against the real Temporal cluster's namespace.** Per `phase-arch-design.md §Edge case #4`: Temporal cluster unreachable ⇒ test skips with `pytest.skip("Temporal cluster unreachable")`, NOT a test failure (the test is gated on cluster availability). For testcontainers path, the container's readiness is a precondition.
- [ ] **AC-2b — Capability mint loads from dev fixture, not K8s mount.** `test_settings.mount_path = None` per S6-02 AC-3a; the dev fixture path produces the same `CapabilityMint` as the K8s path would.

### Workflow execution

- [ ] **AC-3 — Workflow happy path completes in ≤30 s wall-clock.** Start `VulnRemediationWorkflow.run(canonical_request)` via `client.execute_workflow`; await result; assert duration ≤30 s. The `Scenario 1` budget is ~3 s + sandbox; 30 s gives 10× headroom for CI variance. Test is NOT marked `@pytest.mark.bench`; it gates on `make check` (this is THE end-to-end smoke).
- [ ] **AC-3a — Terminal `VulnLedger == Completed`.** Per `Scenario 1`: workflow transitions `NeedsPlan → PlanReady → PatchApplied → AwaitingHumanReview → Completed`. The test dispatches the `human_review_decision(Approved)` signal after the workflow parks on `wait_condition`; asserts the terminal ledger state is `Completed`.
- [ ] **AC-3b — `human_review_decision` signal is dispatched at the parked state.** The test polls `client.get_workflow_handle(workflow_id).query(VulnRemediationWorkflow.state)` until the ledger is `AwaitingHumanReview`; then signals; then awaits result. Bound poll loop by 10 s with a typed `WorkflowDidNotParkError` on timeout.

### Event-log assertions

- [ ] **AC-4 — Event log contains exactly the 12-event canonical sequence.** Read via `EventLog.read_workflow(workflow_id)` (S3-04 surface); assert the returned sequence's `kind` values are exactly (in order):
  ```
  WorkflowStarted, PluginResolved, BundleBuilt, RouteDecided,
  TrustGatePassed, RecipeApplied, PatchApplied, PrOpened,
  SubgraphPausedHITL, MergeOutcome, WorkflowCompleted
  ```
  (11 events emitted by activities + 1 `SubgraphPausedHITL` from the workflow body waiting on signal = 12 total per `Scenario 1` count.) `MergeOutcome` is the `@critical_event` (synchronous flush per S3-03); all others are batched.
- [ ] **AC-4a — Per-workflow BLAKE3 chain verifies on read.** `EventLog.read_workflow` chain-verifies inline (S3-04); the test asserts no `ChainTamperDetected` is emitted during the read pass (defense-in-depth: a malformed event-log writer would surface here).
- [ ] **AC-4b — Per-workflow chain head matches the last event's `row_hash`.** Direct Postgres query: `SELECT row_hash FROM events.events WHERE workflow_id = $1 ORDER BY wf_seq DESC LIMIT 1`; assert byte-equal to the in-memory chain-head cache (per ADR-0003).
- [ ] **AC-4c — `MergeOutcome` was synchronously flushed.** Query Postgres `events.events` immediately after the workflow body emits `MergeOutcome` (use a workflow query handler that returns the current chain-head before exiting); assert the row is present (NOT still in the `EventBatchWriter` buffer). This is the S3-03 critical-event sync-flush bypass verified end-to-end.

### BlobRef assertions

- [ ] **AC-5 — Bundle BlobRef is resolvable, byte-identical to the bundle bytes.** Read the `BundleBuilt` event's `bundle_ref: BlobRef` field; call `BlobStore.resolve(bundle_ref)` against the real Postgres; assert `len(resolved_bytes) == bundle_ref.byte_len` and `BLAKE3(resolved_bytes).hex() == bundle_ref.digest`.
- [ ] **AC-5a — Bundle bytes contain the canonical case's expected hot-view fields.** Golden-file diff: the resolved bundle JSON matches `tests/golden/e2e/canonical_bundle.json` byte-identically. Drift surfaces here.

### Checkpointer assertions

- [ ] **AC-6 — LangGraph checkpointer recorded ≥2 checkpoints in `langgraph_checkpoints` schema.** Per `Scenario 2` / `phase-arch-design.md §C2`: `run_vuln_subgraph` checkpoints after "match_recipe" and "apply_patch" nodes. Direct Postgres query: `SELECT COUNT(*) FROM langgraph_checkpoints.checkpoints WHERE thread_id LIKE $1` (thread_id is the LangGraph-side workflow handle); assert ≥2.
- [ ] **AC-6a — Zero LLM tokens (G11 canary).** Cassette-replay means the LLM never actually hits a network; `assert total_tokens == 0` via the cassette's recording-miss-counter. If the workflow accidentally lights up an LLM call outside the cassette, the recording miss surfaces here (and would have also surfaced in S6-03's G5).
- [ ] **AC-6b — Two-queue dispatch evidence.** Direct Postgres / Temporal query: `client.list_task_queues(...)` filtered to the test workflow's run shows both `vuln-remediation-node-npm` and `system` received tasks (a workflow that ran with only one queue active would silently complete with mocked-out events).

### Graceful teardown + isolation

- [ ] **AC-7 — Teardown drains workers + flushes the EventBatchWriter.** Per S6-01 AC-7c: graceful shutdown drains. The teardown fixture sends SIGTERM-equivalent (cancels the worker tasks); asserts no events are stranded in the batcher (`SELECT COUNT(*) FROM events.events WHERE workflow_id = $1` matches the in-memory queue-drain count).
- [ ] **AC-7a — Test isolation: each test gets a fresh database.** The testcontainers fixture creates a database-per-test (or schema-per-test for speed); no leakage across runs. (For the `make dev-up`-reuse path: the test uses a randomized `workflow_id` prefix and asserts only on rows matching that prefix.)
- [ ] **AC-7b — Test is hermetic: zero network calls outside the test stack.** AST-walk + cassette mode: the test should NOT reach github.com, NOT reach api.anthropic.com, NOT reach hub.docker.com (the testcontainer image pull is a setup-time concern, not test-time). Verified by `pytest-block-network` or equivalent.

### Performance envelope + flake budget

- [ ] **AC-8 — Test wall-clock ≤30 s p95 across 10 consecutive runs.** Per `High-level-impl.md §Step 6 §Done criteria`: "full recipe-route workflow completes in ~30 s." The test's fixture setup + workflow execution + assertion phase must stay under 30 s p95. A `tests/perf/test_phase09_e2e_wallclock.py` (`@pytest.mark.bench`) ratchets the baseline.
- [ ] **AC-8a — Test MUST NOT be `@pytest.mark.flaky`.** Mirrors S5-05 risk #1 closure. If the test flakes, the root cause (timing, container startup, LLM cassette miss) gets fixed; flake-shielding silently relaxes the smoke.

### Gates

- [ ] **AC-9** — `mypy --strict tests/integration/test_workflow_e2e_postgres.py` clean.
- [ ] **AC-10** — `ruff check` + `ruff format --check` clean.
- [ ] **AC-11** — Test is wired into `make check` (NOT `make bench`; runs on every PR).
- [ ] **AC-12** — TDD plan's red test (fixture missing, workers don't compile against real cluster) committed before green.

## Implementation outline

1. **`tests/integration/conftest.py` (EXTEND)**: add `e2e_stack` fixture — testcontainers Postgres + Temporal; runs `alembic upgrade head`; yields `E2EStack` dataclass; teardown stops containers.
2. **`tests/integration/_workers.py` (NEW)**: helper to spawn the three worker tasks via `asyncio.gather` against an `E2EStack`; yields when all three are registered with the cluster (poll `list_task_queues`); teardown cancels gracefully.
3. **`tests/integration/test_workflow_e2e_postgres.py` (NEW)**: the test itself. Uses `e2e_stack` + worker helper; starts workflow; polls for `AwaitingHumanReview`; signals; awaits result; runs assertion suite (AC-4 through AC-6b).
4. **`tests/golden/e2e/canonical_bundle.json` (NEW)**: golden bundle bytes for AC-5a.
5. **`tests/perf/test_phase09_e2e_wallclock.py` (NEW, `@pytest.mark.bench`)**: 10-run ratchet for AC-8.
6. **`tests/bench/baselines/phase09_e2e_wallclock.json` (NEW)**: initial baseline.
7. **CI wiring**: ensure the test runs under `make check` (S8-06 closeout will widen `make check`; this story just makes sure the test is picked up by `pytest` defaults, not behind a marker excluded by `addopts`).

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/integration/test_workflow_e2e_postgres.py`

```python
import pytest
from temporalio.client import Client

from codegenie.durable.workflows.vuln_remediation import VulnRemediationWorkflow
from codegenie.durable.workflows.types import HumanReviewDecision, WorkflowRequest
from codegenie.events.log import EventLog

@pytest.mark.asyncio
async def test_recipe_route_happy_path_e2e(e2e_stack, three_workers, canonical_request):
    client = await Client.connect(e2e_stack.temporal_address)
    handle = await client.start_workflow(
        VulnRemediationWorkflow.run,
        canonical_request,
        id=f"e2e-{canonical_request.case_id}-{e2e_stack.run_id_hex}",
        task_queue="workflow",
    )
    # Poll for AwaitingHumanReview
    await _poll_until_state(handle, "AwaitingHumanReview", timeout_s=10)
    # Approve
    await handle.signal(VulnRemediationWorkflow.human_review_decision, HumanReviewDecision.approved())
    result = await handle.result()

    # AC-3a: terminal ledger
    assert result.ledger.kind == "Completed"

    # AC-4: event-log canonical sequence
    log = EventLog(pool=e2e_stack.postgres_pool)
    events = [e async for e in log.read_workflow(handle.id)]
    assert [e.kind for e in events] == [
        "WorkflowStarted", "PluginResolved", "BundleBuilt", "RouteDecided",
        "TrustGatePassed", "RecipeApplied", "PatchApplied", "PrOpened",
        "SubgraphPausedHITL", "MergeOutcome", "WorkflowCompleted",
    ]
    # (additional AC-4a, AC-4b, AC-4c, AC-5, AC-5a, AC-6, AC-6a, AC-6b assertions follow)
```

Why it fails: fixtures `e2e_stack`, `three_workers`, `canonical_request` don't exist; the helper module doesn't exist.

### Green — minimal pass
- Land `e2e_stack` fixture in `tests/integration/conftest.py`.
- Land `three_workers` helper.
- Make AC-3a pass first (terminal ledger only).
- Then layer in AC-4 (event sequence), AC-5 (BlobRef), AC-6 (checkpointer).

### Refactor
- Pull the assertion bundle into `tests/integration/_e2e_assertions.py` so subsequent stories (S8-01 kill-worker-resume, S8-02 cluster restart) can reuse the assertion helpers.
- Add structured-log capture (`caplog` fixture) and assert specific log lines (`workflow.started`, `workflow.parked`, `workflow.completed`) — observability becomes part of the contract.
- Pin the testcontainers image SHAs to the same set as `infra/docker-compose.dev.yml` (S2-01) so CI and dev see the same Postgres/Temporal versions.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/conftest.py` | EXTEND — `e2e_stack` fixture: testcontainers Postgres + Temporal; alembic upgrade; teardown. |
| `tests/integration/_workers.py` | NEW — spawn the three worker tasks; await registration; graceful teardown helper. |
| `tests/integration/_e2e_assertions.py` | NEW — reusable assertion bundle (event sequence, chain-head, BlobRef, checkpointer); S8-01/S8-02 will reuse. |
| `tests/integration/test_workflow_e2e_postgres.py` | NEW — the test itself. |
| `tests/golden/e2e/canonical_bundle.json` | NEW — golden bundle bytes for AC-5a. |
| `tests/perf/test_phase09_e2e_wallclock.py` | NEW (`@pytest.mark.bench`) — 10-run ratchet for AC-8. |
| `tests/bench/baselines/phase09_e2e_wallclock.json` | NEW — initial baseline (sampled at story-implementation time). |

## Out of scope

- **G1 kill-worker-resume durability test** — S8-01. This story is the smoke; S8-01 is the durability proof.
- **Cluster-restart durability** — S8-02. Same reuse pattern.
- **G9 worker-credential blast-radius adversarial** — S8-03. Reuses the worker helpers from here; expands to four privileged actions.
- **G6 throughput canary (≥3k events/sec)** — S8-04. Different test (perf, not smoke).
- **`MultiPluginParentWorkflow` end-to-end** — partially in S5-06 (workflow-env happy path); a real-substrate parent-+-2-children test is a follow-up if needed.
- **Production-grade test isolation (per-test cluster)** — overkill for Phase 9; per-test database is sufficient.

## Notes for the implementer

- **testcontainers preferred over `make dev-up`-reuse for CI hermeticity.** Local dev contributors can opt into reusing their running cluster via `CODEGENIE_E2E_REUSE_DEVUP=1` env, but the default + CI path is testcontainers. A reused cluster carries cross-test contamination; the fixture's per-test DB mitigates but doesn't eliminate it.
- **`alembic upgrade head` in the fixture is load-bearing.** If you skip it, the test fails with "table events.events does not exist" — but the failure mode is opaque (looks like an event-log bug, is actually a migration-not-applied bug). Run it explicitly and assert the migration version matches `tools/alembic-revisions.lock`'s head before yielding.
- **`langgraph_checkpoints` schema is created lazily by `PostgresSaver.setup()`.** Don't pre-create it in the alembic migration (S2-03 explicitly owns ONLY `events`); the first `PostgresCheckpointerAdapter.saver()` call bootstraps the schema. Fixture asserts the schema exists *after* worker startup, not before.
- **Poll-for-parked-state is bounded.** AC-3b: 10 s timeout. If the workflow doesn't park within 10 s, the test fails fast with a typed `WorkflowDidNotParkError(workflow_id, last_known_state)` — not "deadline exceeded." Per global Rule 12: fail loud.
- **The 12-event sequence assertion (AC-4) is a STRICT-ORDER list comparison, not a set.** Per `Scenario 1`: order matters (`WorkflowStarted` MUST precede `PluginResolved`, `MergeOutcome` MUST come after `SubgraphPausedHITL` because the signal triggers it). If the assertion becomes flaky on order, the cause is concurrent batched-write reordering — diagnose, don't loosen to a set check.
- **`MergeOutcome` sync-flush verification (AC-4c)** is the end-to-end evidence that S3-03's critical-event bypass actually works. A workflow that emits `MergeOutcome` and exits before the batcher flushes would lose the event; the sync-flush bypass guarantees it's on disk. The test queries Postgres directly via a workflow-query handler before `WorkflowCompleted` lands.
- **`total_tokens == 0` (AC-6a) catches cassette misses.** If a contributor adds an LLM call inside the workflow body without recording a cassette, the test's recording-miss counter increments and the assertion fires. This is the same canary S6-03 uses; doubling it here is intentional.
- **Two-queue dispatch evidence (AC-6b)** prevents a sneaky regression: a workflow that runs every activity on a single (default) queue completes correctly but breaks the G9 blast-radius rationale. `client.list_task_queues(...)` is the structural check.
- **Teardown drain (AC-7) is NOT optional.** A teardown that hard-cancels workers leaves events in the batcher and corrupts the next test's database state. The teardown awaits `worker.shutdown()` + `EventBatchWriter.flush()` bounded by 5 s; over the cap, log loud and continue (better an audible loss than a silent one).
- **Wall-clock budget is 30 s p95 (AC-8), NOT mean.** Mean is dominated by the median fast cases; p95 captures the slow-CI variance. The ratchet baseline file tracks p95 so regressions surface at the slow tail, not the median.
- **Test is in `make check`, NOT `make bench`.** This is the smoke; gating on PR is the point. If the test becomes too slow to run on PR (>30 s p95 violated), the answer is "diagnose the slowness", not "move to nightly bench". Per the global rule on goal-driven execution: the goal is "Phase 9 substrate proven on every PR"; moving to nightly bench is silently abandoning the goal.
- **Reuse `_e2e_assertions.py` helpers in S8-01 and S8-02.** Don't copy-paste assertion bundles across durability tests; the helpers are the contract. If S8-01 finds a missing assertion, add it here too — both tests must verify the same set.
- **The `e2e_stack` fixture's image SHAs MUST match `infra/docker-compose.dev.yml`** (S2-01 ships `postgres:16-alpine`, `temporalio/auto-setup:1.25`). Drift between fixture and dev means a contributor sees green CI and broken `make dev-up`, or vice versa. Pin once, surface drift loudly.
