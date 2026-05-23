# Story S5-04 — `MultiPluginParentWorkflow` + `ParentResult` sum-type

**Step:** Step 5 — Postgres checkpointer adapter + workflow definitions
**Status:** Ready
**Effort:** M
**Depends on:** S5-02 (`VulnRemediationWorkflow` — child workflow class spawned via `execute_child_workflow`), S1-03 (`@critical_event` registry — `WorkflowTerminated` for parent fail-loud paths), S1-02 (`EventPayload` union — `MultiPluginDispatched`, `MultiPluginCompleted` variants if added; otherwise re-use `WorkflowStarted` / `WorkflowCompleted` with a discriminator field), S1-07 (workflow-determinism fences applied to *both* workflow files)
**ADRs honored:** Phase 9 ADR-0014 (`MultiPluginParentWorkflow` as real parent/child Temporal shape — `"independent"` coordination only; `"all_or_nothing"` and `"best_effort"` raise typed `NotImplementedError` at the workflow body); production ADR-0042 (multi-plugin coordination for Both-workflows); production ADR-0043 (extension by addition — un-implemented sum-type variants are NOT silent stubs; they fail at *use* time with typed errors visible in `temporal-ui`); Phase 9 ADR-0007 (two task queues — children stay on `vuln-remediation-node-npm`); Phase 9 ADR-0004 (workflow determinism — parent body is pure orchestration).

## Context

Production ADR-0042's `Both`-case names the multi-plugin coordination decision: when a repo's `vuln.provenance` matches multiple plugins (e.g., both `vulnerability-remediation--node--npm` and `vulnerability-remediation--python--pip`), the system orchestrates per-plugin workflows under a parent coordinator. Phase 8's `SupervisorDecision = ... | MultiPluginDispatch` carries the typed shape forward — but Phase 8 does not *run* multiple workflows. Phase 9 ADR-0014 chooses **option (c)**: ship the full parent/child Temporal shape in Phase 9 with `coordination_policy = "independent"` only; the other two variants raise typed `NotImplementedError("see Phase 10")` at the workflow body — fail-loud, visible in `temporal-ui`, additive growth path for Phase 10. The parent workflow takes a `MultiPluginDispatch` Pydantic input and produces a `ParentResult = AllMerged | SomeMerged | AllFailed` sum type. Each child workflow runs the existing `VulnRemediationWorkflow`. The parent body is pure orchestration: spawn N children via `workflow.execute_child_workflow`, await them, aggregate the results into `ParentResult`. The parent does NOT auto-retry failed children — humans decide per ADR-0042. Gap-2's typed precondition (`coordination_policy` field on the input model) carries Phase 10's variant additively.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C1 — Workflow definitions` — `MultiPluginParentWorkflow` public interface.
  - `../phase-arch-design.md §ParentResult sum-type (Contract, new in Phase 9)` — exact dataclass shape of `AllMerged | SomeMerged | AllFailed`.
  - `../phase-arch-design.md §Edge case 17 — MultiPluginParentWorkflow child fails` — `WorkflowFailureError → SomeMerged` aggregation; parent does NOT auto-retry.
  - `../phase-arch-design.md §Gap 2 — MultiPluginParentWorkflow sibling-coordination semantics are under-specified` — the `coordination_policy` field rationale.
  - `../phase-arch-design.md §Integration with Phase 10` — Phase 10's first `Both`-case PR lands `all_or_nothing` / `best_effort` on this story's machinery.
- **Phase ADRs:**
  - `../ADRs/0014-multi-plugin-parent-workflow-as-temporal-shape.md` — full decision (Option C), tradeoffs, "real implementation of the cheapest variant + additive growth" pattern.
  - `../ADRs/0004-workflow-determinism-enforcement-three-layers.md` — parent body must pass the same three fences as `VulnRemediationWorkflow`.
  - `../ADRs/0007-two-task-queue-partitioning-and-expansion-by-addition.md` — children stay on `vuln-remediation-node-npm` (Phase 9 ships one node-npm queue; Phase 10 adds `python-pip` queue additively).
- **Production ADRs:**
  - `docs/production/adrs/0042-multi-plugin-coordination-for-both-workflows.md` — Both-case canonical rationale.
  - `docs/production/adrs/0043-extension-by-addition-means-no-silent-edits.md` — un-implemented variants fail at use time with typed errors (NOT pass / NOT return None / NOT silent stub).
- **Implementation plan:**
  - `../High-level-impl.md §Step 5 — Features delivered — MultiPluginParentWorkflow` — exact prescription.
- **Sibling stories:**
  - `S5-02-vuln-remediation-workflow.md` — child class spawned by this parent; the parent must not require any S5-02 changes (additive parent only).
  - `S5-06-workflow-hitl-tests.md` — happy-path test for the `"independent"` coordination policy + typed-error test for the other two variants.
  - `S6-01-worker-bootstrap.md` — workflow worker registration includes BOTH workflow classes.
- **Existing code seams:**
  - `src/codegenie/durable/workflows/vuln_remediation.py` (S5-02) — child workflow class (`VulnRemediationWorkflow`).
  - `src/codegenie/durable/workflows/__init__.py` (S1-07) — explicit-import collection point; add `MultiPluginParentWorkflow`.
  - `src/codegenie/types/identifiers.py` (S1-01) — `WorkflowId`, `RepoId`, `CorrelationId` Newtypes used for parent → child correlation.
  - Phase 8: `MultiPluginDispatch` is owned by Phase 8 in `phase-arch-design.md`. **Confirm canonical home** — re-export from `codegenie.plugins.supervisor` if Phase 8 ships it; otherwise define here in `_types.py` with a forward-compat note.

## Goal

Ship `src/codegenie/durable/workflows/multi_plugin_parent.py` containing `@workflow.defn(name="MultiPluginParentWorkflow") class MultiPluginParentWorkflow` with `run(self, dispatch: MultiPluginDispatch) -> ParentResult` that spawns N child `VulnRemediationWorkflow`s via `workflow.execute_child_workflow` for `coordination_policy="independent"` (Phase-9 default), aggregates outcomes into `ParentResult = AllMerged | SomeMerged | AllFailed`, and raises a typed `NotImplementedError("see Phase 10")` at the workflow body's `match` arm for `"all_or_nothing"` and `"best_effort"`. The parent body passes the S1-07 import-linter contract and AST fence. Two unit-level `WorkflowEnvironment` tests cover (1) 2-child happy path producing `AllMerged` and (2) `"all_or_nothing"` raises the typed error visible via `temporal-ui` history.

## Acceptance criteria

### A — Package surface

- [ ] **AC-A1** `src/codegenie/durable/workflows/multi_plugin_parent.py` exists. Contains `@workflow.defn(name="MultiPluginParentWorkflow") class MultiPluginParentWorkflow`. Module docstring cites ADR-0014 + ADR-0042 and warns against `coordination_policy` drift.
- [ ] **AC-A2** `src/codegenie/durable/workflows/multi_plugin_parent/types.py` (or `_types.py` extension) contains:
  - `class MultiPluginDispatch(BaseModel)` with `model_config = ConfigDict(frozen=True, extra="forbid")`. Fields: `dispatch_id: CorrelationId`, `repo_id: RepoId`, `work_items: tuple[PluginWorkItem, ...]` (non-empty), `coordination_policy: Literal["independent", "all_or_nothing", "best_effort"] = "independent"`.
  - `class PluginWorkItem(BaseModel)` (`frozen=True, extra="forbid"`): `plugin_id: PluginId`, `request: VulnRemediationRequest`.
  - `@dataclass(frozen=True, slots=True) class AllMerged: children: tuple[VulnRemediationResult, ...]`
  - `@dataclass(frozen=True, slots=True) class SomeMerged: merged: tuple[VulnRemediationResult, ...]; failed: tuple[VulnRemediationResult, ...]`
  - `@dataclass(frozen=True, slots=True) class AllFailed: failed: tuple[VulnRemediationResult, ...]`
  - `ParentResult = AllMerged | SomeMerged | AllFailed`.
- [ ] **AC-A3** `src/codegenie/durable/workflows/__init__.py` adds `MultiPluginParentWorkflow` to the explicit-import collection alongside `VulnRemediationWorkflow`.
- [ ] **AC-A4** `MultiPluginDispatch` canonical home: if Phase 8 already defines it, re-export from `codegenie.plugins.supervisor`; do NOT duplicate. Verify in attempt log.

### B — Parent body + child dispatch (`coordination_policy="independent"`)

- [ ] **AC-B1** Parent `run` body opens with `match dispatch.coordination_policy:`. Three arms: `case "independent":` (real impl), `case "all_or_nothing":` (raises `NotImplementedError("see Phase 10")`), `case "best_effort":` (raises `NotImplementedError("see Phase 10")`). Final `case _ as never: assert_never(never)` enforces exhaustiveness.
- [ ] **AC-B2** The `"independent"` arm:
  - Spawns N child workflows via `workflow.execute_child_workflow(VulnRemediationWorkflow.run, work_item.request, id=f"{dispatch.dispatch_id}-child-{i}", task_queue=TaskQueueName("vuln-remediation-node-npm"), parent_close_policy=ParentClosePolicy.TERMINATE)`.
  - Children share `parent_workflow_id = workflow.info().workflow_id` correlation key (auto-set by Temporal; verify via child's `workflow.info().parent`).
  - Awaits all N child handles concurrently via `asyncio.gather(*handles, return_exceptions=True)` — capturing `WorkflowFailureError` per child without crashing the parent.
- [ ] **AC-B3** Aggregation into `ParentResult`:
  - All N children return success → `AllMerged(children=tuple(results))`.
  - All N children fail (`WorkflowFailureError`) → `AllFailed(failed=tuple(error_payload_per_child))`.
  - Mixed → `SomeMerged(merged=tuple(...), failed=tuple(...))`.
  - **No auto-retry of failed children** — humans decide per ADR-0042. (AC verified by counting `execute_child_workflow` calls per `dispatch_id` = exactly N, never N+1.)
- [ ] **AC-B4** Empty `work_items` rejected at Pydantic-validation time (`min_length=1` on the tuple) — the parent body never sees an empty dispatch. Test asserts `MultiPluginDispatch(work_items=())` raises `ValidationError`.

### C — `NotImplementedError` for unimplemented coordination policies (ADR-0014 + ADR-0043)

- [ ] **AC-C1** `"all_or_nothing"` arm: `raise NotImplementedError("MultiPluginParentWorkflow coordination_policy='all_or_nothing' lands in Phase 10; see docs/phases/09-temporal-durable-workflow/ADRs/0014-multi-plugin-parent-workflow-as-temporal-shape.md")`. The exception message is the typed pointer to ADR-0014 + Phase 10.
- [ ] **AC-C2** `"best_effort"` arm: identical shape, message references Phase 10.
- [ ] **AC-C3** Test: `WorkflowEnvironment` start with `coordination_policy="all_or_nothing"`; assert workflow fails with `WorkflowFailureError` whose `cause` includes `NotImplementedError`; assert the workflow's Temporal-history (via `await handle.fetch_history()` or equivalent) carries the ADR-0014 pointer in the failure message (visible in `temporal-ui`).
- [ ] **AC-C4** These are **not silent stubs** (ADR-0043). The arms are reached *only* when a future contributor passes the new policy; they fail at use time, loud and typed. Verify via attempt-log note: "the `NotImplementedError`s in `multi_plugin_parent.py` conform to ADR-0043's no-silent-edits rule because they are typed preconditions on a workflow input, fail at use time with a pointer to the implementation work."

### D — Determinism + import discipline

- [ ] **AC-D1** `tests/fence/test_workflow_determinism.py` (S1-07's AST walker) is green over `multi_plugin_parent.py`. No `set(`, `random.*`, `time.*`, `datetime.now`, `uuid.uuid4`, `os.environ`.
- [ ] **AC-D2** `make lint-imports` — the `workflows-must-be-pure` contract is green: `multi_plugin_parent.py` imports only `temporalio.workflow`, `pydantic`, `codegenie.events.payloads` (type-only), `codegenie.types.identifiers`, and the `VulnRemediationWorkflow` *class* (`from codegenie.durable.workflows.vuln_remediation import VulnRemediationWorkflow`).
- [ ] **AC-D3** No retry loops; child failures are aggregated into `ParentResult.SomeMerged` / `AllFailed` — never re-dispatched.

### E — Parent → child correlation + identifiers

- [ ] **AC-E1** Each child workflow's ID derives deterministically from the parent: `f"{dispatch.dispatch_id}-child-{i}"` where `i` is the work-item index in `work_items` (ordered). Test asserts the IDs are stable across two invocations with the same `MultiPluginDispatch`.
- [ ] **AC-E2** Each child workflow's `parent_workflow_id` (via `workflow.info().parent.workflow_id` inside the child) matches the parent's `workflow_id`. (Temporal auto-wires this; we verify the wiring is reachable.)
- [ ] **AC-E3** Each child workflow receives its own `task_queue` — Phase 9 ships all children on `vuln-remediation-node-npm`. Phase 10 may parameterize per-plugin (Gap-2 forward-compat); this story uses the constant.

### F — Happy-path integration test (`coordination_policy="independent"`)

- [ ] **AC-F1** `tests/workflows/test_multi_plugin_parent_workflow.py::test_two_children_happy_path_all_merged` — uses `WorkflowEnvironment.start_local()`. Registers BOTH `VulnRemediationWorkflow` and `MultiPluginParentWorkflow` against mocked child activities (both children take the happy path → `Completed(decision="merged")`). Dispatches `MultiPluginDispatch` with 2 `PluginWorkItem`s. Asserts:
  - Parent terminates with `ParentResult = AllMerged(children=(...,...))`.
  - Both children's IDs match `f"{dispatch_id}-child-0"` and `f"{dispatch_id}-child-1"`.
  - `state()` query on each child (if registered) returns `Completed`.

### G — Typed-error test (`coordination_policy="all_or_nothing"`)

- [ ] **AC-G1** `tests/workflows/test_multi_plugin_parent_workflow.py::test_all_or_nothing_raises_not_implemented` — dispatches `MultiPluginDispatch(coordination_policy="all_or_nothing", work_items=(...,))`. Asserts:
  - Parent fails with `WorkflowFailureError`.
  - The error chain includes `NotImplementedError`.
  - The error message contains `"Phase 10"` and `"ADR-0014"` (the pointer is real).
  - **No child workflow is spawned** (verified via Temporal history — children would appear as `ChildWorkflowExecutionStarted` events; absent for unimplemented policies).

### H — Mixed-outcome test (some succeed, some fail)

- [ ] **AC-H1** `tests/workflows/test_multi_plugin_parent_workflow.py::test_some_merged_aggregation` — dispatch 3 children; mock 2 to succeed (`Completed(decision="merged")`) and 1 to fail (raise `WorkflowFailureError` from the child via a mocked activity that raises non-retryable). Assert `ParentResult = SomeMerged(merged=tuple(2 items), failed=tuple(1 item))`. Assert the parent does NOT retry the failed child (`execute_child_workflow` called 3 times total, not 4).

### I — Replay-determinism preflight

- [ ] **AC-I1** `tests/workflows/test_multi_plugin_parent_replay.py` — record a 2-child happy-path history under the fixture `tests/golden/temporal/multi_plugin_parent_happy_path.json`; `WorkflowReplayer.run_replay_workflow_async` succeeds on this fixture (no `NondeterminismError`). Per-Python-minor matrix (3.11 + 3.12).
- [ ] **AC-I2** Replay test is NOT `@pytest.mark.flaky` (per Implementation risk #1).

### J — Gates

- [ ] **AC-J1** `ruff format`, `ruff check`, `mypy --strict src/codegenie/durable/workflows/multi_plugin_parent.py` clean. `match` over `coordination_policy` is exhaustive via `assert_never`; `match` over child outcomes is exhaustive.
- [ ] **AC-J2** `make lint-imports` — the `workflows-must-be-pure` contract is exercised by this file and passes.

## Implementation outline

1. **Define types in `_types.py` (extending S5-02's).**
   - Re-export `MultiPluginDispatch`, `PluginWorkItem` from Phase 8 if it owns them; otherwise define here with `frozen=True, extra="forbid"`.
   - Define `AllMerged`, `SomeMerged`, `AllFailed` as `@dataclass(frozen=True, slots=True)` per the canonical `phase-arch-design.md §ParentResult` shape.
   - `ParentResult = AllMerged | SomeMerged | AllFailed`.
2. **Write `multi_plugin_parent.py`.**
   - `@workflow.defn(name="MultiPluginParentWorkflow") class MultiPluginParentWorkflow:`
   - `@workflow.run async def run(self, dispatch: MultiPluginDispatch) -> ParentResult:`
     - `match dispatch.coordination_policy:`
       - `case "independent": return await self._run_independent(dispatch)`
       - `case "all_or_nothing": raise NotImplementedError("MultiPluginParentWorkflow coordination_policy='all_or_nothing' lands in Phase 10; see docs/phases/09-temporal-durable-workflow/ADRs/0014-multi-plugin-parent-workflow-as-temporal-shape.md")`
       - `case "best_effort": raise NotImplementedError("MultiPluginParentWorkflow coordination_policy='best_effort' lands in Phase 10; see docs/phases/09-temporal-durable-workflow/ADRs/0014-multi-plugin-parent-workflow-as-temporal-shape.md")`
       - `case _ as never: assert_never(never)`
   - `async def _run_independent(self, dispatch) -> ParentResult:`
     - Build child IDs: `child_ids = tuple(f"{dispatch.dispatch_id}-child-{i}" for i in range(len(dispatch.work_items)))`.
     - Spawn: `handles = await asyncio.gather(*(workflow.execute_child_workflow(VulnRemediationWorkflow.run, wi.request, id=cid, task_queue=TaskQueueName("vuln-remediation-node-npm"), parent_close_policy=ParentClosePolicy.TERMINATE) for wi, cid in zip(dispatch.work_items, child_ids)), return_exceptions=True)`.
     - Partition: `merged = tuple(h for h in handles if not isinstance(h, BaseException))`; `failed = tuple(self._failure_to_result(h) for h in handles if isinstance(h, BaseException))`.
     - Aggregate: `if not failed: return AllMerged(children=merged); if not merged: return AllFailed(failed=failed); return SomeMerged(merged=merged, failed=failed)`.
3. **No new activities, no new task queues.**
   - Children use the existing `vuln-remediation-node-npm` queue from S6-01.
4. **Record the replay fixture.**
   - `make record-parent-replay-fixture` target; outputs `tests/golden/temporal/multi_plugin_parent_happy_path.json`.

## TDD plan — red / green / refactor

### Red

**Test file: `tests/workflows/test_multi_plugin_parent_workflow.py`**

```python
import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from codegenie.durable.workflows.multi_plugin_parent import MultiPluginParentWorkflow
from codegenie.durable.workflows.vuln_remediation import VulnRemediationWorkflow
from codegenie.durable.workflows._types import (
    MultiPluginDispatch, PluginWorkItem, AllMerged, SomeMerged, AllFailed,
    VulnRemediationRequest,
)

@pytest.fixture
async def env():
    async with await WorkflowEnvironment.start_local() as env:
        yield env

async def test_two_children_happy_path_all_merged(env, fake_activities_all_success):
    async with Worker(env.client, task_queue="vuln-remediation-node-npm",
                      workflows=[MultiPluginParentWorkflow, VulnRemediationWorkflow],
                      activities=fake_activities_all_success):
        dispatch = MultiPluginDispatch(
            dispatch_id="DSP-001", repo_id="repo-A",
            work_items=(
                PluginWorkItem(plugin_id="vulnerability-remediation--node--npm",
                               request=VulnRemediationRequest(repo_id="repo-A", attempt_id="att-0", ...)),
                PluginWorkItem(plugin_id="vulnerability-remediation--node--npm",
                               request=VulnRemediationRequest(repo_id="repo-A", attempt_id="att-1", ...)),
            ),
            coordination_policy="independent",
        )
        handle = await env.client.start_workflow(
            MultiPluginParentWorkflow.run, dispatch,
            id="parent-001", task_queue="vuln-remediation-node-npm",
        )
        result = await handle.result()
        assert isinstance(result, AllMerged)
        assert len(result.children) == 2

async def test_all_or_nothing_raises_not_implemented(env, fake_activities_all_success):
    async with Worker(env.client, task_queue="vuln-remediation-node-npm",
                      workflows=[MultiPluginParentWorkflow, VulnRemediationWorkflow],
                      activities=fake_activities_all_success):
        dispatch = MultiPluginDispatch(
            dispatch_id="DSP-002", repo_id="repo-A",
            work_items=(PluginWorkItem(plugin_id="x", request=VulnRemediationRequest(...)),),
            coordination_policy="all_or_nothing",
        )
        handle = await env.client.start_workflow(
            MultiPluginParentWorkflow.run, dispatch,
            id="parent-002", task_queue="vuln-remediation-node-npm",
        )
        with pytest.raises(Exception) as exc:
            await handle.result()
        # The WorkflowFailureError wraps the NotImplementedError; assert the chain.
        message = str(exc.value)
        assert "Phase 10" in message
        assert "ADR-0014" in message
        # No child workflow spawned:
        history = [e async for e in handle.fetch_history_events()]
        assert not any("ChildWorkflowExecutionStarted" in str(e) for e in history)

async def test_best_effort_raises_not_implemented(env, fake_activities_all_success):
    # symmetric to all_or_nothing test
    ...

async def test_some_merged_aggregation(env, fake_activities_2_success_1_fail):
    async with Worker(env.client, task_queue="vuln-remediation-node-npm",
                      workflows=[MultiPluginParentWorkflow, VulnRemediationWorkflow],
                      activities=fake_activities_2_success_1_fail):
        dispatch = MultiPluginDispatch(
            dispatch_id="DSP-003", repo_id="repo-A",
            work_items=tuple(PluginWorkItem(plugin_id="x", request=VulnRemediationRequest(repo_id="repo-A", attempt_id=f"att-{i}", ...)) for i in range(3)),
            coordination_policy="independent",
        )
        handle = await env.client.start_workflow(MultiPluginParentWorkflow.run, dispatch, id="parent-003", task_queue="vuln-remediation-node-npm")
        result = await handle.result()
        assert isinstance(result, SomeMerged)
        assert len(result.merged) == 2
        assert len(result.failed) == 1
        # No retry of failed child:
        history = [e async for e in handle.fetch_history_events()]
        starts = sum(1 for e in history if "ChildWorkflowExecutionStarted" in str(e))
        assert starts == 3  # exactly 3, not 4

async def test_all_failed_aggregation(env, fake_activities_all_fail):
    # All N children fail → AllFailed
    ...

async def test_child_ids_are_deterministic():
    # Same dispatch produces the same child IDs across invocations
    ...

async def test_empty_work_items_rejected_at_pydantic():
    with pytest.raises(Exception):  # ValidationError
        MultiPluginDispatch(dispatch_id="DSP-x", repo_id="repo-A", work_items=(),
                            coordination_policy="independent")
```

**Test file: `tests/workflows/test_multi_plugin_parent_replay.py`**

```python
async def test_parent_happy_path_history_replays_clean():
    from temporalio.testing import WorkflowReplayer
    import json
    history = json.loads(Path("tests/golden/temporal/multi_plugin_parent_happy_path.json").read_text())
    replayer = WorkflowReplayer(workflows=[MultiPluginParentWorkflow, VulnRemediationWorkflow])
    await replayer.replay_workflow(history)  # MUST NOT raise
```

### Green

Implement per §Implementation outline. Expected size: ~120 lines for the workflow body, ~60 lines for the `_types.py` additions. The `_run_independent` helper is the largest single function (~50 lines).

### Refactor

- Extract `_failure_to_result(exception) -> VulnRemediationResult` — pure helper that converts a `WorkflowFailureError` into a typed failure result. Testable in isolation.
- If the typed-error pattern repeats in `VulnRemediationWorkflow` (e.g., for Phase-10 routing variants), extract a `_phase_10_not_implemented(policy_name, adr_pointer)` helper. Don't extract preemptively.
- Document the parent's no-retry stance in the class docstring; cite ADR-0042.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/durable/workflows/multi_plugin_parent.py` | The parent workflow class |
| `src/codegenie/durable/workflows/_types.py` | Add `MultiPluginDispatch`, `PluginWorkItem`, `ParentResult` sum type (re-export if Phase 8 owns the input shape) |
| `src/codegenie/durable/workflows/__init__.py` | Explicit-import the parent workflow |
| `tests/workflows/test_multi_plugin_parent_workflow.py` | Happy-path + typed-error + mixed-outcome tests |
| `tests/workflows/test_multi_plugin_parent_replay.py` | Replay-determinism test |
| `tests/golden/temporal/multi_plugin_parent_happy_path.json` | Recorded history fixture |
| `Makefile` | `record-parent-replay-fixture` target |

## Out of scope

- **`"all_or_nothing"` and `"best_effort"` implementations.** Phase 10's first PR. The typed `NotImplementedError`s are the precondition.
- **Per-plugin task-queue routing.** Phase 9 ships one node-npm queue. Phase 10 / Phase 7.5 adds `python-pip` queue + routes children to the right queue based on `PluginWorkItem.plugin_id`.
- **`SomeMerged.unmerged_children → auto-emit HumanReviewRequested?`** Open question #5 in `phase-arch-design.md`; Phase 10 decides. This story's `SomeMerged` is a typed aggregate; consumers decide policy.
- **Parent-level cancel propagation to children.** `parent_close_policy=ParentClosePolicy.TERMINATE` is set (default for Phase 9); a future operator-cancel-signal-cascades story is Phase 10/13.
- **Parent retry of failed children.** ADR-0042: humans decide; no auto-retry.
- **Multiple parents per repo.** A second `MultiPluginDispatch` for the same repo runs concurrently — that's a Phase-10 concurrency-control question (e.g., per-repo workflow ID idempotence).
- **`ParentResult` projection.** A Phase-10 projection could fold `AllMerged | SomeMerged | AllFailed` rollups; not Phase-9 scope.

## Notes for the implementer

- **The typed `NotImplementedError`s are *the* design feature, not a TODO.** They make ADR-0014's "real implementation of the cheapest variant + additive growth" concrete: a future Phase-10 contributor passes `"all_or_nothing"`, sees the typed error pointing at ADR-0014, and lands the implementation in the same `match` arm. NO `pass`, NO `return None`, NO silent stub. ADR-0043 forbids those; this conforms.
- **Empty `work_items` is rejected at Pydantic, not at the workflow body.** `min_length=1` on the tuple field. The parent body never sees an empty dispatch — saves a defensive `match` arm.
- **`asyncio.gather(*, return_exceptions=True)` is the key.** Without `return_exceptions=True`, the first child failure crashes the parent — but ADR-0042 requires aggregation. The flag turns child failures into typed values the parent can partition.
- **`parent_close_policy=ParentClosePolicy.TERMINATE`.** If the parent is cancelled, children are also cancelled. The alternative (`ABANDON`) leaves orphan children running — bad operational hygiene. Document this in the parent's docstring.
- **Children share a `parent_workflow_id` correlation key automatically.** Temporal wires this. The cross-workflow correlation in `audit_trail` projection (S7-01) folds child events under the parent via `workflow.info().parent.workflow_id`.
- **The mixed-outcome aggregation order matters.** `merged` and `failed` tuples should preserve the **input order** of `work_items` — auditors expect "child-0 succeeded, child-1 failed, child-2 succeeded" to read in dispatch order. The aggregation logic must NOT reorder.
- **No retry of failed children — by design.** ADR-0042: humans decide. The parent does NOT call `execute_child_workflow` more than N times. If a Phase-10 contributor wants `"best_effort"` to retry failed children, that's an *additive* implementation in the corresponding `match` arm — NOT a relaxation of this story's `"independent"` contract.
- **`MultiPluginDispatch` canonical home.** If Phase 8's `codegenie.plugins.supervisor` already exports it (per ADR-0014 §Context: "Phase 8's `SupervisorDecision = ... | MultiPluginDispatch` carries the typed shape forward"), re-export from there. **Do not duplicate.** Verify the import path in the attempt log.
- **The parent body MUST be deterministic.** Same fences as `VulnRemediationWorkflow`. The `asyncio.gather` is deterministic because the child handles are returned in input order; child workflow IDs are deterministic per AC-E1; replay re-uses the recorded child results.
- **Replay test on the per-Python-minor matrix.** Multi-child parents are more vulnerable to dict-ordering / async-scheduling drift than single-line workflows; the matrix is the early-warning system.
- **The `NotImplementedError` message format is part of the contract.** Phase 10 will grep for this message in their migration story; keep `"Phase 10"` and `"ADR-0014"` as literal substrings.
- **Deferred design opportunities** (record in attempt log): (a) extracting a `ParentResult.from_outcomes(outcomes)` smart constructor — keep procedural for clarity in Phase 9; (b) parameterizing the child task queue per plugin — Phase 10 work; (c) introducing a `CancellableChildPolicy` enum — Phase 13 ergonomics; (d) folding `ParentResult` aggregation into a projection — Phase 10 evidence first.
