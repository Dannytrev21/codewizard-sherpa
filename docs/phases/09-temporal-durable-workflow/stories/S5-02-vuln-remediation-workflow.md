# Story S5-02 — `VulnRemediationWorkflow` — `@workflow.defn` body orchestrating the `VulnLedger` sum-type

**Step:** Step 5 — Postgres checkpointer adapter + workflow definitions
**Status:** Ready
**Effort:** L
**Depends on:** S1-03 (`@critical_event` registry — the 5 critical variants the workflow emits), S4-02 (`emit_event` activity + `write_blob_ref` / `resolve_blob_ref`), S4-01 (`_POLICIES` `RetryPolicy` table), S5-01 (`PostgresCheckpointerAdapter` — consumed *inside* `run_vuln_subgraph` activity, not the workflow body), S1-07 (workflow-determinism fences must already bite)
**ADRs honored:** Phase 9 ADR-0004 (workflow determinism — three layers); Phase 9 ADR-0010 (asymmetric activity granularity — Supervisor is 1:1, SHERPA subgraph is one fat activity); Phase 9 ADR-0006 (`@critical_event` synchronous-flush vocabulary — `MergeOutcome` + `WorkflowTerminated` + `TrustGateFailed`); production ADR-0033 (sum types for domain state — `VulnLedger` exhaustive via `match` + `assert_never`); production ADR-0009 (humans always merge — workflow body has NO `merge_pr` activity dispatch).

## Context

`VulnRemediationWorkflow` is the durable outer envelope around the Phase-6 SHERPA loop. The body is **pure orchestration** over the `VulnLedger` sum-type (Phase 6, intact — re-exported, not duplicated): each variant maps to a `match` arm that dispatches one or more activities via `workflow.execute_activity` under the per-activity `RetryPolicy` from `_POLICIES`. State is tiny — the ledger variant plus four IDs (`WorkflowId`, `RepoId`, `CorrelationId`, `AttemptId`) plus two counters (`retry_count`, `subgraph_resume_count`). Large payloads cross as `BlobRef`s. The workflow body **must be deterministic** (G4) — the three layered fences from S1-07 bite from day one (import-linter forbids `random/time/datetime/uuid/os/socket/httpx/requests/redis/psycopg/asyncpg/subprocess/codegenie.exec/codegenie.transforms/codegenie.probes`; AST walker forbids the literal call shapes; `Replayer` catches transitive non-determinism, landing in S5-05). The workflow **has no retry loops** — G3 is enforced as an S8-05 fence; this story does not add a single `while attempt < max` / `for _ in range(retries)`. Three signals + one query are exposed: `human_review_decision`, `cancel`, and `state()`. The happy path traces 14 history records, 12 events, 1 sync Postgres round-trip (the `MergeOutcome`), 11 batched events.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C1 — Workflow definitions (codegenie.durable.workflows)` — full public interface, internal-structure prescription, forbidden imports, performance envelope (per-workflow Temporal-history ≤ 30 records).
  - `../phase-arch-design.md §VulnLedger sum-type (Contract, Phase-6 intact)` — the 7 variants (`NeedsPlan, PlanReady, PatchApplied, GateFailedRetryable, AwaitingHumanReview, Completed, FailedUnrecoverable`).
  - `../phase-arch-design.md §Control flow — Happy path` + `§Decision points` — the five `match` branches the workflow body owns; especially the routing-vs-subgraph-vs-HITL flow.
  - `../phase-arch-design.md §Agentic best practices — Tool-use safety` — no `merge_pr` dispatch; ADR-0009 rendered as code.
  - `../phase-arch-design.md §Design patterns applied #2 (Tagged union / sum type)` — `match` + `assert_never` discipline.
- **Phase ADRs:**
  - `../ADRs/0004-workflow-determinism-enforcement-three-layers.md` — the forbidden-vocabulary set and the layered fence model.
  - `../ADRs/0010-activity-granularity-asymmetric.md` — Supervisor's three activities + `run_vuln_subgraph` as one fat activity; explains why the workflow body does NOT decompose the LangGraph subgraph itself.
  - `../ADRs/0006-critical-event-synchronous-flush-vocabulary.md` — which events synchronous-flush at append.
- **Production ADRs:**
  - `docs/production/adrs/0009-humans-always-merge.md` — no merge activity ever.
  - `docs/production/adrs/0033-sum-types-for-domain-state.md` — `match` + `assert_never` is mandatory.
- **Implementation plan:**
  - `../High-level-impl.md §Step 5` — features delivered + done criteria.
- **Sibling stories:**
  - `S5-03-freshness-window-resume.md` — *companion* — adds the `freshness_window` check on resume; this story should leave the seam (e.g., a `_check_freshness(decision) -> bool` helper) for S5-03 to extend additively.
  - `S5-05-replay-determinism-replayer.md` — the `Replayer` test fixture this story records the history for.
  - `S5-06-workflow-hitl-tests.md` — happy-path + signal tests against this story's workflow body.
- **Existing code seams:**
  - `src/codegenie/sherpa/vuln/state.py` (Phase 6) — `VulnLedger` sum-type. **Re-export, do not duplicate.**
  - `src/codegenie/durable/activities/retry_policies.py` (S4-01) — `_POLICIES` keyed by `ActivityName`.
  - `src/codegenie/durable/activities/{resolve_plugin,build_bundle,route,run_vuln_subgraph,sandbox_build_and_test,github_open_pr,emit_event}.py` (S4-02..S4-05) — the activities the workflow dispatches.
  - `src/codegenie/durable/workflows/__init__.py` (created in S1-07 with the determinism docstring) — explicit-import collection point.
  - `src/codegenie/events/payloads.py` (S1-02) — type-only imports for `WorkflowStarted, PluginResolved, BundleBuilt, RouteDecided, RecipeApplied, PatchApplied, PrOpened, MergeOutcome, WorkflowTerminated, TrustGatePassed, TrustGateFailed, WorkflowCompleted`.

## Goal

Ship `src/codegenie/durable/workflows/vuln_remediation.py` containing `@workflow.defn(name="VulnRemediationWorkflow") class VulnRemediationWorkflow` with: `run(self, request: VulnRemediationRequest) -> VulnRemediationResult` (pure orchestration over `VulnLedger` variants via `match` + `assert_never`), `human_review_decision` signal, `cancel` signal, and `state() -> VulnLedger` query. Workflow body dispatches activities exclusively via `workflow.execute_activity(...)` with `retry_policy=_POLICIES[ActivityName(...)]`; **no retry loops** in workflow code. The body must pass the S1-07 import-linter contract and AST fence; a `WorkflowEnvironment.start_local()` integration test asserts the `VulnLedger` transitions `NeedsPlan → PlanReady → PatchApplied → AwaitingHumanReview → Completed` on the happy path with mocked activities.

## Acceptance criteria

### A — Package surface + workflow class shape

- [ ] **AC-A1** `src/codegenie/durable/workflows/vuln_remediation.py` exists. Contents: exactly one top-level class `VulnRemediationWorkflow` decorated with `@workflow.defn(name="VulnRemediationWorkflow")`. No module-level mutable globals; no `set()` literals; no `datetime.now()`; no `random.*`; no `time.*`. Module docstring cites Phase-9 ADR-0004 and warns against importing the forbidden vocabulary.
- [ ] **AC-A2** Workflow class exposes (introspected via `temporalio.workflow.{_run, _signals, _queries}` / decorator metadata):
  - `@workflow.run async def run(self, request: VulnRemediationRequest) -> VulnRemediationResult`
  - `@workflow.signal(name="human_review_decision") def human_review_decision(self, decision: HumanReviewDecision) -> None`
  - `@workflow.signal(name="cancel") def cancel(self, reason: CancellationReason) -> None`
  - `@workflow.query(name="state") def state(self) -> VulnLedger`
- [ ] **AC-A3** `VulnRemediationRequest`, `VulnRemediationResult`, `HumanReviewDecision`, `CancellationReason` are Pydantic models (`frozen=True, extra="forbid"`) defined either in `src/codegenie/durable/workflows/_types.py` or imported from a Phase-6 module. Confirm the canonical home; do NOT duplicate.
- [ ] **AC-A4** `src/codegenie/durable/workflows/__init__.py` adds `VulnRemediationWorkflow` to the explicit-import collection (no `importlib.metadata` scan; mirror the Phase-0 `@register_probe` precedent).

### B — `VulnLedger` orchestration discipline

- [ ] **AC-B1** The workflow `run` body uses `match` over the *current* `VulnLedger` variant; each of the 7 variants has its own arm; the final `case _ as never:` arm calls `typing.assert_never(never)`. `mypy --strict` enforces exhaustiveness; a deliberate-variant-drop xfail fixture confirms the fence fires.
- [ ] **AC-B2** Transitions are encoded as **return-of-new-variant** from each arm (functional style — the workflow doesn't mutate the ledger; it reassigns the local). No `self._ledger` mutable attribute; the ledger is a local `ledger: VulnLedger` rebound after each `match` arm. The `state()` query reads `self._ledger_snapshot` (a separate frozen attribute updated whenever the local ledger changes — Temporal queries must be deterministic and side-effect-free).
- [ ] **AC-B3** Each arm uses `workflow.execute_activity` (NOT `start_activity` unless explicit async-without-await semantics are required for parallel sibling activities). Activity name is passed via the `ActivityName(...)` Newtype constant; `retry_policy=_POLICIES[ActivityName("...")]`.
- [ ] **AC-B4** Each arm emits **at least one** `EventPayload` variant via `workflow.execute_activity("emit_event", ...)`. The five `@critical_event` variants (`WorkflowTerminated`, `TrustGateFailed`, `MergeOutcome`, `BudgetExhausted`, `ChainTamperDetected`) emit at the arms that produce them; the other variants are batched. (Test asserts that the happy path emits exactly the 14-record sequence from `phase-arch-design.md §Happy path`.)

### C — Determinism + no-retry-loop discipline

- [ ] **AC-C1** `tests/fence/test_workflow_determinism.py` (S1-07's AST walker) is green over `vuln_remediation.py`. Manual scan: no literal `set(`, `random.*`, `time.*`, `datetime.now`, `uuid.uuid4`, `os.environ`.
- [ ] **AC-C2** `make lint-imports` — the `codegenie.durable.workflows-must-be-pure` contract is green for this file. Forbidden imports: `random | time | datetime | uuid | os | socket | httpx | requests | redis | psycopg | asyncpg | subprocess | codegenie.exec | codegenie.transforms | codegenie.probes | codegenie.events.log`. (The workflow imports `codegenie.events.payloads` for *types only* — that is permitted.)
- [ ] **AC-C3** **No retry loops.** AST/grep over `vuln_remediation.py` shows zero occurrences of `while.*attempt`, `for _ in range(`, `while True:` retry constructs. (S8-05 ships the formal fence; this story passes it preemptively.)
- [ ] **AC-C4** Use of time inside the workflow body uses `workflow.now()` exclusively — never `datetime.now()`. (Note: this story plumbs `workflow.now()` access for S5-03 freshness checks; absence of any `datetime` import in the file is verified.)
- [ ] **AC-C5** Use of sleep inside the workflow body uses `workflow.sleep(timedelta(...))` exclusively — never `asyncio.sleep` or `time.sleep`.

### D — Signal + query semantics

- [ ] **AC-D1** `human_review_decision(decision: HumanReviewDecision)` signal sets `self._review_decision: HumanReviewDecision | None`. The workflow body's `AwaitingHumanReview` arm parks on `await workflow.wait_condition(lambda: self._review_decision is not None)`; on wake, matches the decision (`Approved | Rejected | Deferred`) and transitions accordingly.
- [ ] **AC-D2** `cancel(reason: CancellationReason)` signal sets `self._cancelled: CancellationReason | None`. **Every** `wait_condition` in the body includes `or self._cancelled is not None`; on wake-by-cancel, the workflow emits `WorkflowTerminated(by="operator", reason=...)` synchronously and exits via a `case Completed | FailedUnrecoverable: return` final arm.
- [ ] **AC-D3** `state()` query returns the latest `VulnLedger` snapshot via `self._ledger_snapshot` (frozen attribute, updated immutably). The query is side-effect-free; calling it does NOT progress the workflow. Test calls `state()` mid-pause (after `AwaitingHumanReview` transition) and asserts the returned variant.
- [ ] **AC-D4** `HumanReviewDecision = Approved | Rejected | Deferred` is a sum type (3 variants); `Deferred` keeps the workflow parked (the `wait_condition` returns to waiting). `match` over `HumanReviewDecision` is exhaustive via `assert_never`.

### E — Activity-dispatch contract

- [ ] **AC-E1** Activities are dispatched with `task_queue` selection: `resolve_plugin | build_bundle | route | run_vuln_subgraph | sandbox_build_and_test | github_open_pr` go to `TaskQueueName("vuln-remediation-node-npm")`; `emit_event | write_blob_ref | resolve_blob_ref` go to `TaskQueueName("system")`. (Test asserts the task-queue argument on each dispatch using a `WorkflowEnvironment` activity recorder.)
- [ ] **AC-E2** Workflow dispatches the activities in the documented happy-path order (`emit_event(WorkflowStarted)` → `resolve_plugin` → `emit_event(PluginResolved)` → `build_bundle` → `write_blob_ref` (bundle) → `emit_event(BundleBuilt)` → `route` → `emit_event(RouteDecided)` → `run_vuln_subgraph` → `emit_event(TrustGatePassed, RecipeApplied, PatchApplied)` → `github_open_pr` → `emit_event(PrOpened)` → `wait_condition(human_review_decision)` → `emit_event(MergeOutcome)` → `emit_event(WorkflowCompleted)`).
- [ ] **AC-E3** **No `merge_pr` / `approve_pr` / `self_merge` activity is dispatched** anywhere in the body. (S4-07 ships the fence; this story passes it.) `MergeOutcome` is **observed** (emitted on signal); never **caused**.
- [ ] **AC-E4** Each `workflow.execute_activity` call passes `retry_policy=_POLICIES[ActivityName(name)]` — the workflow body NEVER hardcodes a `RetryPolicy(...)` constructor call. (Test patches `_POLICIES` and verifies the policy reaches `execute_activity` via a spy.)

### F — Happy-path integration test (Temporal `WorkflowEnvironment`)

- [ ] **AC-F1** `tests/workflows/test_vuln_remediation_workflow.py::test_happy_path_ledger_transitions` — uses `WorkflowEnvironment.start_local()` with `temporalio.testing.WorkflowEnvironment` time-skipping. Registers `VulnRemediationWorkflow` against mocked versions of the 9 activities (returning canned `RedactedActivityResult`-derived outputs). Drives the workflow through one happy-path execution; mid-execution sends `human_review_decision(Approved(reviewer_id="alice"))`. Asserts the observed `VulnLedger` transitions captured via `state()` queries at key moments: `NeedsPlan → PlanReady → PatchApplied → AwaitingHumanReview → Completed`. Asserts `WorkflowExecutionCompleted` is the terminal Temporal event.
- [ ] **AC-F2** Same test asserts the 14-record event sequence: collect every `emit_event` call's `EventPayload` kind via the activity mock; assert the ordered list matches the documented happy-path totals exactly.
- [ ] **AC-F3** **Test must NOT be `@pytest.mark.flaky` or `@pytest.mark.skip`.** (Per Implementation risk #1 in `High-level-impl.md`.)

### G — `cancel` signal test

- [ ] **AC-G1** `tests/workflows/test_vuln_remediation_workflow.py::test_cancel_signal_emits_workflow_terminated_and_exits` — start workflow; mid-flight (after `build_bundle`, before `route`) send `cancel(reason=CancellationReason(...))`. Assert: workflow exits with `VulnRemediationResult` carrying a `FailedUnrecoverable` / cancelled-terminal state; final emitted event is `WorkflowTerminated(by="operator", reason=...)`; the event is synchronously flushed (verified via the `@critical_event` registry's marker, not by Postgres in this unit-level test).

### H — Hardcoded-state guards

- [ ] **AC-H1** Mutation-resistance: starting the workflow with a `VulnRemediationRequest` whose `repo_id` is `"repo-A"` and asserting `state() == NeedsPlan(request=<repo-A-request>)` does NOT pass if the workflow has a hardcoded ledger initialization. Paired with a second test using `"repo-B"` — both must distinguish — so a `return NeedsPlan(request=fixed_value)` mutant fails.
- [ ] **AC-H2** Workflow body does NOT contain `self._ledger = <hardcoded variant>` initialization; the initial ledger is `NeedsPlan(request=request)` derived from the input. (Code-grep verifies; also covered by mutation testing in `_attempts/S5-02.md` if a mutmut/cosmic-ray pass is run.)

### I — Replay-determinism preflight

- [ ] **AC-I1** Workflow body passes a single `temporalio.testing.WorkflowReplayer.run_replay_workflow_async` round-trip on a freshly-recorded history (test fixture written by this story; consumed by S5-05's matrix). The fixture lands under `tests/golden/temporal/vuln_remediation_happy_path.json` (recorded once via `make record-replay-fixture`; committed).
- [ ] **AC-I2** Replay error output preserves the full `NondeterminismError` payload (no `except NondeterminismError: pass`-style swallowing).

### J — Gates

- [ ] **AC-J1** `ruff format`, `ruff check`, `mypy --strict src/codegenie/durable/workflows/vuln_remediation.py` clean. `mypy --strict` reports exhaustive `match` (no `assert_never` warnings).
- [ ] **AC-J2** `make lint-imports` — the `workflows-must-be-pure` contract is exercised by *this file* and passes.
- [ ] **AC-J3** `make fence` — no LLM SDK leaks; `pyproject_fence` test stays green.

## Implementation outline

1. **Re-export `VulnLedger` from Phase 6.**
   - In `src/codegenie/durable/workflows/_types.py` add `from codegenie.sherpa.vuln.state import (NeedsPlan, PlanReady, PatchApplied, GateFailedRetryable, AwaitingHumanReview, Completed, FailedUnrecoverable, VulnLedger)`. **Do not redefine.**
2. **Define `VulnRemediationRequest`, `VulnRemediationResult`, `HumanReviewDecision`, `CancellationReason`.**
   - Frozen Pydantic models. `HumanReviewDecision` is a Pydantic discriminated union over `Approved | Rejected | Deferred`.
3. **Write `vuln_remediation.py`.**
   - Decorators: `@workflow.defn(name="VulnRemediationWorkflow")`.
   - `__init__(self)`: `self._review_decision: HumanReviewDecision | None = None`; `self._cancelled: CancellationReason | None = None`; `self._ledger_snapshot: VulnLedger = NeedsPlan(request=...)` (set inside `run`).
   - `run(self, request)` body:
     - Bind `ledger: VulnLedger = NeedsPlan(request=request)`; emit `WorkflowStarted` (batched).
     - Loop: `while True: match ledger: case NeedsPlan(...): ledger = await self._on_needs_plan(ledger); case PlanReady(...): ledger = await self._on_plan_ready(ledger); ... case Completed() | FailedUnrecoverable(): return self._to_result(ledger); case _ as never: assert_never(never)`.
     - **No** retry counters in the loop — `match` arms transition the ledger; Temporal's `RetryPolicy` handles activity-level retries.
     - Each `_on_*` helper is an `async` method that dispatches one or more activities and returns the next variant.
   - `_check_cancel(self) -> None` raises `workflow.CancelledError` if `self._cancelled is not None` after emitting `WorkflowTerminated` synchronously. Called at the top of every `match` arm.
4. **Wire `emit_event` dispatches.**
   - Helper `async def _emit(self, payload: EventPayload) -> None: await workflow.execute_activity("emit_event", EmitEventInput(payload=payload, capability=...), task_queue="system", retry_policy=_POLICIES[ActivityName("emit_event")])`.
   - At synchronous-flush arms, the workflow awaits the activity result (which itself is sync-flushed by the activity); at batched arms, the workflow awaits — Temporal does not differentiate; the sync-flush vs batched is the *activity's* concern.
5. **Wire signals + query.**
   - Signal handlers are non-async; they update flags. Query handler returns `self._ledger_snapshot`.
6. **Wire `_check_freshness` seam for S5-03.**
   - Stub helper `def _check_freshness(self, decision: RouteDecision) -> bool: return True` — S5-03 replaces the body with `workflow.now() - decision.decided_at <= decision.freshness_window`. Story S5-02 leaves the seam as a return-True stub so it's additively extensible; the AC for "freshness check always returns True in S5-02" can be removed when S5-03 lands.
7. **Record a replay-fixture history.**
   - Add a `make record-replay-fixture` target (or a `pytest` marker `@pytest.mark.record-fixture`) that runs the happy path under `WorkflowEnvironment` and dumps the history JSON to `tests/golden/temporal/vuln_remediation_happy_path.json`. Committed once; updated only when the workflow body intentionally changes.

## TDD plan — red / green / refactor

### Red

**Test file: `tests/workflows/test_vuln_remediation_workflow.py`** (Temporal `WorkflowEnvironment` with time-skipping)

```python
import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from codegenie.durable.workflows.vuln_remediation import VulnRemediationWorkflow
from codegenie.durable.workflows._types import (
    VulnRemediationRequest, HumanReviewDecision, Approved, CancellationReason,
)
from codegenie.sherpa.vuln.state import NeedsPlan, AwaitingHumanReview, Completed

@pytest.fixture
async def env():
    async with await WorkflowEnvironment.start_local() as env:
        yield env

@pytest.fixture
def fake_activities():
    # Mocked versions of the 9 activities returning canned RedactedActivityResult-derived outputs.
    # Each records its (name, input, task_queue, retry_policy) call for assertion.
    ...

async def test_happy_path_ledger_transitions(env, fake_activities):
    async with Worker(
        env.client,
        task_queue="vuln-remediation-node-npm",
        workflows=[VulnRemediationWorkflow],
        activities=fake_activities,  # both task queues' activities registered together for the test
    ):
        handle = await env.client.start_workflow(
            VulnRemediationWorkflow.run,
            VulnRemediationRequest(repo_id="repo-A", attempt_id="att-1", ...),
            id="wf-test-1",
            task_queue="vuln-remediation-node-npm",
        )
        # Drive to AwaitingHumanReview, then signal.
        # WorkflowEnvironment time-skipping advances any workflow.sleep.
        async def wait_until_parked():
            for _ in range(50):
                ledger = await handle.query("state")
                if isinstance(ledger, AwaitingHumanReview):
                    return
                await env.sleep(0.1)
            pytest.fail("workflow did not park on AwaitingHumanReview")
        await wait_until_parked()
        await handle.signal("human_review_decision", Approved(reviewer_id="alice"))
        result = await handle.result()
        assert isinstance(await handle.query("state"), Completed)
        # Assert the full transition trace via the activity recorder:
        emitted_kinds = [c.input.payload.kind for c in fake_activities.emit_event_calls]
        assert emitted_kinds == [
            "WorkflowStarted", "PluginResolved", "BundleBuilt", "RouteDecided",
            "TrustGatePassed", "RecipeApplied", "PatchApplied", "PrOpened",
            "MergeOutcome", "WorkflowCompleted",
        ]

async def test_cancel_signal_emits_workflow_terminated_and_exits(env, fake_activities):
    # Start workflow, drive to after build_bundle, then cancel.
    # Assert: final state is FailedUnrecoverable; WorkflowTerminated emitted last.
    ...

async def test_mutation_resistance_initial_state_reflects_request(env, fake_activities):
    # Two workflows, two requests; assert state() distinguishes them.
    # A `return NeedsPlan(request=fixed)` mutant fails this test.
    ...

async def test_state_query_does_not_progress_workflow(env, fake_activities):
    # Call state() three times mid-pause; assert ledger variant unchanged.
    ...

async def test_no_retry_loops_in_workflow_source():
    src = (Path("src/codegenie/durable/workflows/vuln_remediation.py")).read_text()
    for forbidden in ["while attempt", "for _ in range(", "while True"]:
        # `while True:` is allowed *only* in the `match` outer loop; refine grep to per-line ast.
        ...
    # Better: ast.parse + walker that finds While/For nodes and asserts each is the outer match loop OR has a workflow.wait_condition / workflow.sleep, not an attempt counter.
```

**Test file: `tests/fence/test_no_retry_loops_in_workflows.py`** (preflight for S8-05)

```python
import ast
from pathlib import Path

def test_no_retry_loop_constructs_in_workflow_files():
    for py in Path("src/codegenie/durable/workflows").glob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFor) or isinstance(node, ast.For):
                # Allowed: iterating over a tuple of activities or sum-type variants. Forbidden: `range(retries)` counter.
                if isinstance(node.iter, ast.Call) and getattr(node.iter.func, "id", "") == "range":
                    pytest.fail(f"{py}: for ... in range(...) — retry loop construct")
            if isinstance(node, ast.While):
                # Allowed: `while True:` if the body has `match ledger` (the outer state loop) OR `workflow.wait_condition`.
                ...
```

**Test file: `tests/fence/test_workflow_imports_purity.py`** (preflight for S1-07's import-linter)

```python
import ast
from pathlib import Path

FORBIDDEN = {
    "random", "time", "datetime", "uuid", "os", "socket",
    "httpx", "requests", "redis", "psycopg", "asyncpg", "subprocess",
    "codegenie.exec", "codegenie.transforms", "codegenie.probes",
    "codegenie.events.log",
}

def test_vuln_remediation_workflow_imports_pure():
    tree = ast.parse(Path("src/codegenie/durable/workflows/vuln_remediation.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in FORBIDDEN, f"forbidden import: {alias.name}"
        if isinstance(node, ast.ImportFrom):
            assert node.module not in FORBIDDEN, f"forbidden import: {node.module}"
```

### Green

Implement per §Implementation outline. Expected size: ~250 lines for the workflow body, ~80 lines for the `_types.py` Pydantic model definitions. The `_on_*` helper methods are each 10–20 lines (one `execute_activity` + one `_emit`).

### Refactor

- Extract the activity-name + task-queue mapping into a module-level `Final[dict[ActivityName, TaskQueueName]]` so the dispatch helpers read it instead of hardcoding strings.
- Document the `_check_freshness` seam in a module-docstring with a forward reference to S5-03.
- Lift the `_emit` helper into a base mixin if `MultiPluginParentWorkflow` (S5-04) needs the same pattern; otherwise keep inline.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/durable/workflows/vuln_remediation.py` | The workflow class |
| `src/codegenie/durable/workflows/_types.py` | `VulnRemediationRequest`, `VulnRemediationResult`, `HumanReviewDecision`, `CancellationReason` |
| `src/codegenie/durable/workflows/__init__.py` | Explicit-import the workflow class |
| `tests/workflows/test_vuln_remediation_workflow.py` | Happy-path + cancel-signal + state-query tests |
| `tests/fence/test_no_retry_loops_in_workflows.py` | Preflight no-retry-loop fence |
| `tests/fence/test_workflow_imports_purity.py` | Preflight import-vocabulary fence |
| `tests/golden/temporal/vuln_remediation_happy_path.json` | Recorded history fixture for S5-05's Replayer |
| `Makefile` | `record-replay-fixture` target |

## Out of scope

- **`run_vuln_subgraph` Activity implementation.** S4-05 owns the fat-Activity body + LangGraph integration. This workflow story dispatches the activity but mocks it in tests.
- **`MultiPluginParentWorkflow`.** S5-04 owns the parent workflow class. This story does NOT cross-reference or import from it.
- **Freshness-window resume check.** S5-03 implements `_check_freshness` real body + emits `RouteStalenessDescent`. This story leaves the stub seam (returns True) — additive.
- **HITL signal test (parking + signal dispatch).** S5-06 ships the full HITL pause-resume test; this story's happy-path test covers the signal-receive shape but not the days-long park-resume semantics.
- **Replay-determinism matrix.** S5-05 ships the per-Python-minor matrix + fixture refresh discipline. This story only commits the *initial* fixture for the happy path.
- **Per-activity capability minting.** S6-02 owns capability minting at worker bootstrap; this story passes a placeholder capability in tests.
- **Continue-as-new under 20-min subgraph cap.** Open question #1 in `High-level-impl.md` — Phase 10 work.
- **`SubgraphOutcome` sum type handling beyond `Completed`.** The full `case PausedHITL: ... case Failed: ...` arms ship here as stubs (deferring to the LangGraph subgraph's tier-descent ladder); the integration test exercises `Completed` only. `PausedHITL` and `Failed` arms get full coverage in S5-06.

## Notes for the implementer

- **Workflow body is *the* place determinism bites.** Read `phase-arch-design.md §Scenario 3 — Replay-determinism violation` before you write a line. The three layers (import-linter, AST fence, Replayer) are your guardrails — *test against them locally* before committing.
- **`workflow.now()` over `datetime.now()` — non-negotiable.** Replay re-uses recorded times; live calls would diverge. The `_check_freshness` seam (S5-03) uses `workflow.now()`.
- **`workflow.sleep` over `asyncio.sleep`.** Same reason. `WorkflowEnvironment.start_local()` time-skips both, but only `workflow.sleep` survives a real Temporal cluster's replay.
- **`match` + `assert_never` is the contract.** A new `VulnLedger` variant added in a future phase is a build break here — and that's the point. `mypy --strict` catches the missing arm; `assert_never` makes it a runtime error if the fail-fast wasn't seen.
- **No retry loops, period.** Activity-level retry is `_POLICIES[ActivityName(...)]`'s job (S4-01). Workflow-level "retry" semantics ARE the `GateFailedRetryable → ... → AwaitingHumanReview` ledger transitions — they're sum-type-arm walks, NOT counter loops. The S8-05 fence ships post-this-story; this story passes it preemptively.
- **The `state()` query MUST be side-effect-free and deterministic.** Temporal queries can be called many times; they read state only. The `_ledger_snapshot` attribute is *the* read surface — never compute the ledger fresh in `state()`.
- **`cancel` signal semantics — handle at every `await`.** Every `wait_condition` includes `or self._cancelled is not None` in its predicate; every `execute_activity` follows with a `_check_cancel()` call. Otherwise the cancel signal can race against an arm transition.
- **`HumanReviewDecision = Approved | Rejected | Deferred` — `Deferred` is *parked*, not *closed*.** A `Deferred` decision sets `self._review_decision` and the `wait_condition` re-arms — the workflow keeps parking. This is the operator-says-"come back later" path. A future `human_review_decision(Deferred)` is replaced by a subsequent `human_review_decision(Approved | Rejected)`.
- **Activity dispatch is *always* via the `_POLICIES` table.** Inline `RetryPolicy(...)` constructor calls are a violation of S4-01's `Final` table discipline. If a new activity needs a unique policy, add the row in `_POLICIES` and reference it here — not the other way around.
- **The replay-fixture history is a committed artifact.** Recording it once is a `make record-replay-fixture` ceremony; S5-05 consumes it. If you tweak the workflow body (even cosmetically — comment shuffles count) and the fixture goes stale, the Replayer test in CI will fail loudly. *That is the design.* Regenerate the fixture deliberately; don't band-aid.
- **`VulnLedger` re-export, not duplication.** The Phase-6 module is the canonical home. If `_types.py` ends up redefining a variant, you've drifted from the contract — fix the import.
- **Deferred design opportunities** (record in attempt log, don't implement here): (a) splitting the `_on_*` helpers into a class hierarchy — keep procedural for now (the workflow body is the canonical functional core); (b) extracting a `WorkflowEmitter` capability wrapper — premature; (c) caching `_POLICIES` lookups in `__init__` — micro-opt; the dict lookup is sub-microsecond.
