# Story S5-03 — Freshness-window resume check + `RouteStalenessDescent` event emission

**Step:** Step 5 — Postgres checkpointer adapter + workflow definitions
**Status:** Ready
**Effort:** S
**Depends on:** S5-02 (`VulnRemediationWorkflow` body + the `_check_freshness` seam), S1-03 (`@critical_event` registry — `RouteStalenessDescent` does NOT join the 5 critical members; it's a non-critical batched event), S1-02 (`EventPayload` union — `RouteStalenessDescent` variant must be present from day one per Gap-3)
**ADRs honored:** Phase 9 ADR-0004 (workflow determinism — `workflow.now()` is the only legal clock inside the workflow body); Phase 9 ADR-0010 (asymmetric activity granularity — tier-descent re-dispatches the `resolve_plugin` / `route` activities, not the fat subgraph); future Phase 9 ADR-0018 (records the default `freshness_window=7 days` — lands additively in Step 8 with canary evidence).

## Context

`phase-arch-design.md §Gap 3` flags a subtle replay correctness problem: when a workflow resumes weeks later and consults a recorded `RouteDecision` or `PluginResolved` payload, Temporal replays the *recorded* value — Phase-8 fail-closed freshness semantics never fire because no fresh hot-view read is made. The recorded `gather_id` may reference a GC'd Phase-8 hot view; the recorded plugin may have been removed from the catalog between the original execution and resume. The fix (per ADR-0018-pending) is to carry a `freshness_window: timedelta` + `decided_at: datetime` on `RouteDecision` and `PluginResolved` payloads (S1-02 lands the variant fields; S4-03 lands the activity output shape); when the workflow body resumes and consults a recorded decision, the `match` arm checks `workflow.now() - decision.decided_at <= decision.freshness_window`; if stale, tier-descend to a fresh `resolve_plugin` / `route` cycle (which Temporal records as a *new* activity result on resume — replay-safe). The descent emits a `RouteStalenessDescent` event (batched; not `@critical_event`). This story replaces S5-02's `_check_freshness` stub (currently returns `True`) with the real implementation, wires the tier-descent transition, and adds the descent emission.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Gap 3 — Resume-after-long-pause freshness story is silent` — full gap rationale + improvement spec.
  - `../phase-arch-design.md §Edge case 14 — Workflow resumes after months-long pause; recorded RouteDecision references GC'd gather_id` — the failure mode being closed.
  - `../phase-arch-design.md §VulnLedger sum-type` — note that tier-descent does NOT add a new ledger variant; it re-enters `PlanReady → PatchApplied` via fresh activity dispatch (additive count via `subgraph_resume_count`).
- **Phase ADRs:**
  - `../ADRs/0004-workflow-determinism-enforcement-three-layers.md` — `workflow.now()` over `datetime.now()`; this check uses `workflow.now()` exclusively.
  - **Pending:** `../ADRs/0018-freshness-window-default-7-days.md` — will land in Step 8 with canary evidence; this story emits the event variant that ADR will reference.
- **Implementation plan:**
  - `../High-level-impl.md §Step 5 — Features delivered — RouteDecision and PluginResolved payloads carry `freshness_window`` — exact prescription.
- **Sibling stories:**
  - `S5-02-vuln-remediation-workflow.md` — owns the `_check_freshness` stub seam this story replaces.
  - `S1-02-event-payload-union.md` — `RouteStalenessDescent` variant must already exist (per Gap-3 prescription) before this story emits it.
  - `S4-03-phase8-supervisor-activities.md` — `route` and `resolve_plugin` activity outputs already carry `freshness_window` + `decided_at` (story note in the parent manifest).
- **Existing code seams:**
  - `src/codegenie/durable/workflows/vuln_remediation.py` (S5-02) — `_check_freshness(decision) -> bool` stub to replace.
  - `src/codegenie/events/payloads.py` (S1-02) — `RouteStalenessDescent` variant.
  - `src/codegenie/durable/config.py` (S2-02) — `DurableSettings.default_freshness_window: timedelta` (Pydantic Settings field; pass into the activity at dispatch time, not into the workflow body).

## Goal

Replace `VulnRemediationWorkflow._check_freshness(decision) -> bool` stub with a real implementation that returns `True` iff `workflow.now() - decision.decided_at <= decision.freshness_window`. When the check returns `False` on a `RouteDecision` or `PluginResolved` consulted during resume, the workflow body tier-descends by re-dispatching the `resolve_plugin` / `route` activity and emits a `RouteStalenessDescent(workflow_id, original_decision_id, original_decided_at, current_workflow_now, freshness_window)` event. The default `freshness_window` value (`timedelta(days=7)`) flows from `DurableSettings` into the activity output at dispatch time — the workflow body does not read settings.

## Acceptance criteria

### A — `_check_freshness` real implementation

- [ ] **AC-A1** `VulnRemediationWorkflow._check_freshness(decision: RouteDecision | PluginResolved) -> bool` returns `True` iff `(workflow.now() - decision.decided_at) <= decision.freshness_window`. The expression uses `workflow.now()` exclusively — no `datetime.now()` in the workflow file (S1-07's AST fence stays green).
- [ ] **AC-A2** Boundary semantics: equality is fresh (NOT stale). `workflow.now() - decision.decided_at == decision.freshness_window` returns `True`. (Matches the freshness-window-as-allowed-budget interpretation, mirrors S3-02's strict-`>` boundary discipline.)
- [ ] **AC-A3** The helper handles both `RouteDecision` and `PluginResolved` shapes via duck-typing on the two fields (`decided_at`, `freshness_window`) — no isinstance check needed if both payloads share a `FreshnessAware` Protocol or both carry the same two field names. If the implementer prefers an explicit `match`, both variants are exhaustive.

### B — Tier-descent transition

- [ ] **AC-B1** The workflow body's `PlanReady` arm (which consults the recorded `PluginResolved`) and the post-`route` arm (which consults `RouteDecision`) check `self._check_freshness(decision)` *before* proceeding. On `False`, the arm re-dispatches `resolve_plugin` / `route` (respectively) — a fresh activity invocation that Temporal records as a new history event (replay-safe).
- [ ] **AC-B2** Tier-descent does NOT introduce a `while`/`for` retry loop. The descent is structured as a *single* re-dispatch within the arm; the new activity result replaces the stale decision; the arm proceeds. If the *new* decision is also stale (a pathological edge case where the activity returned with `decided_at = workflow.now()` but the freshness window is `timedelta(0)`), the workflow body emits `RouteStalenessDescent` once more and transitions to `FailedUnrecoverable(reason="freshness_loop")` — fail-loud, never silent.
- [ ] **AC-B3** `self.subgraph_resume_count` counter (initialized to 0 in `__init__`) increments on each tier-descent. This is *not* a retry-loop counter; it's a metric exposed via `state()` introspection. Bounded by AC-B2's fail-loud semantics.

### C — `RouteStalenessDescent` emission

- [ ] **AC-C1** On tier-descent (i.e., when `_check_freshness` returns `False`), the workflow emits a `RouteStalenessDescent` event via `await self._emit(RouteStalenessDescent(...))` *before* re-dispatching the activity. The event is **batched** — not `@critical_event` (per S1-03; the descent is observable but not durability-critical).
- [ ] **AC-C2** `RouteStalenessDescent` payload fields (from S1-02): `workflow_id: WorkflowId`, `original_decision_kind: Literal["RouteDecision", "PluginResolved"]`, `original_decided_at: datetime`, `workflow_now: datetime`, `freshness_window: timedelta`. (Names match the S1-02 variant exactly; if S1-02 differs, fix S1-02 — coordinated update.)
- [ ] **AC-C3** Test asserts the emission ordering: `RouteStalenessDescent` is emitted *before* the fresh `resolve_plugin` / `route` dispatch — auditors reading the event log see the descent reason before the new decision.

### D — Replay safety + determinism

- [ ] **AC-D1** A `WorkflowEnvironment` test records a workflow history with a stale recorded `RouteDecision` (`decided_at = workflow.now() - timedelta(days=10)`, `freshness_window = timedelta(days=7)`); replays the history under `WorkflowReplayer.run_replay_workflow_async`; the replay succeeds (no `NondeterminismError`) — the tier-descent path is replay-safe because `workflow.now()` is the same on replay (Temporal records it).
- [ ] **AC-D2** `workflow.now()` is the only clock used. No `datetime.now()`, no `time.time()`, no `time.monotonic()` in `vuln_remediation.py`. (S1-07's AST fence catches any drift; this story passes it.)
- [ ] **AC-D3** The descent's emitted `workflow_now` field is *the same value* as `workflow.now()` at decision time — captured once at the top of the arm, not re-read after `_emit` (the event payload's `workflow_now` must be a workflow-history-recorded value to survive replay).

### E — Happy-path (not-stale) test

- [ ] **AC-E1** `tests/workflows/test_freshness_window_check.py::test_fresh_decision_no_descent` — start workflow; `route` activity returns `RouteDecision(decided_at=workflow.now(), freshness_window=timedelta(days=7))`; workflow proceeds to `run_vuln_subgraph` without re-dispatching `route` or emitting `RouteStalenessDescent`. Assert: event log does NOT contain `RouteStalenessDescent`.

### F — Stale-resume tier-descent test

- [ ] **AC-F1** `tests/workflows/test_freshness_window_check.py::test_stale_resume_emits_descent_and_re_dispatches` — start workflow; mock `route` to return `RouteDecision(decided_at = workflow.now() - timedelta(days=10), freshness_window=timedelta(days=7))`; assert:
  - `RouteStalenessDescent` is emitted exactly once.
  - `route` activity is dispatched twice (original + fresh).
  - The fresh `RouteDecision` (with `decided_at = workflow.now()`) is consulted; workflow proceeds.
  - `state()` query reports `subgraph_resume_count == 1`.
- [ ] **AC-F2** Mutation-resistance: a `_check_freshness` mutant that returns `True` regardless of age fails AC-F1; a mutant that returns `False` regardless fails AC-E1. The paired tests pin the predicate's *direction*.

### G — Pathological-loop fail-loud test

- [ ] **AC-G1** `tests/workflows/test_freshness_window_check.py::test_freshness_loop_fails_unrecoverable` — `route` activity is mocked to always return a stale `RouteDecision` (`freshness_window = timedelta(0)`). Assert: workflow terminates with `VulnLedger.FailedUnrecoverable(reason="freshness_loop")` after exactly 2 `RouteStalenessDescent` emissions (one for the original stale check, one for the still-stale fresh check); workflow does NOT loop indefinitely.

### H — Gates

- [ ] **AC-H1** `ruff format`, `ruff check`, `mypy --strict src/codegenie/durable/workflows/vuln_remediation.py` clean. `match` over `HumanReviewDecision` + ledger remains exhaustive.
- [ ] **AC-H2** `tests/fence/test_workflow_determinism.py` (S1-07) stays green over the edited file.
- [ ] **AC-H3** `make lint-imports` — the `workflows-must-be-pure` contract stays green.

## Implementation outline

1. **Replace `_check_freshness` body in `src/codegenie/durable/workflows/vuln_remediation.py`.**
   - From `def _check_freshness(self, decision) -> bool: return True` (S5-02 stub) to `def _check_freshness(self, decision: RouteDecision | PluginResolved) -> bool: return (workflow.now() - decision.decided_at) <= decision.freshness_window`.
   - Strictly `<=` per AC-A2.
2. **Edit the `PlanReady` and post-`route` arms to consult `_check_freshness`.**
   - Capture `now = workflow.now()` once at arm top.
   - Compute `is_fresh = self._check_freshness(decision)`.
   - If `is_fresh`: proceed to next activity dispatch (existing S5-02 logic).
   - Else: emit `RouteStalenessDescent(workflow_id=self._workflow_id, original_decision_kind=..., original_decided_at=decision.decided_at, workflow_now=now, freshness_window=decision.freshness_window)`; re-dispatch the activity (`resolve_plugin` or `route`); set `decision = fresh_decision`; check `_check_freshness(decision)` once more; if still stale, transition to `FailedUnrecoverable(reason="freshness_loop")`.
   - Increment `self.subgraph_resume_count` on the descent.
3. **Add the `subgraph_resume_count` initialization to `__init__` and expose it in `state()`.**
   - If `state()` returns `VulnLedger` only (per S5-02 AC-A2), add a `subgraph_resume_count` as a separate query `@workflow.query(name="resume_count") def resume_count(self) -> int: return self._subgraph_resume_count` — or include it in the `state()` payload via a wrapper Pydantic model `WorkflowStateSnapshot(ledger: VulnLedger, resume_count: int)`. Pick the wrapper approach for additive-friendliness; S5-02's `state() -> VulnLedger` query becomes `state() -> WorkflowStateSnapshot` (additive shape change; coordinate with S5-02's executor if not yet shipped).
4. **No edits to `_POLICIES`, no new activities, no new task queues.**
   - The fresh dispatch reuses existing `resolve_plugin` / `route` activities with the same `RetryPolicy` row.

## TDD plan — red / green / refactor

### Red

**Test file: `tests/workflows/test_freshness_window_check.py`** (Temporal `WorkflowEnvironment` time-skipping)

```python
import pytest
from datetime import timedelta
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker
from codegenie.durable.workflows.vuln_remediation import VulnRemediationWorkflow
from codegenie.durable.workflows._types import VulnRemediationRequest
from codegenie.events.payloads import RouteStalenessDescent, RouteDecision
from codegenie.sherpa.vuln.state import FailedUnrecoverable

@pytest.fixture
async def env():
    async with await WorkflowEnvironment.start_local() as env:
        yield env

async def test_fresh_decision_no_descent(env, fake_activities_fresh):
    # fake_activities_fresh returns RouteDecision(decided_at=workflow.now(), freshness_window=7d)
    async with Worker(env.client, task_queue="vuln-remediation-node-npm",
                      workflows=[VulnRemediationWorkflow], activities=fake_activities_fresh):
        handle = await env.client.start_workflow(
            VulnRemediationWorkflow.run,
            VulnRemediationRequest(repo_id="repo-A", attempt_id="att-1", ...),
            id="wf-fresh", task_queue="vuln-remediation-node-npm",
        )
        await handle.result()
        kinds = [c.input.payload.kind for c in fake_activities_fresh.emit_event_calls]
        assert "RouteStalenessDescent" not in kinds
        assert fake_activities_fresh.route_call_count == 1  # not re-dispatched

async def test_stale_resume_emits_descent_and_re_dispatches(env, fake_activities_stale_then_fresh):
    async with Worker(env.client, task_queue="vuln-remediation-node-npm",
                      workflows=[VulnRemediationWorkflow], activities=fake_activities_stale_then_fresh):
        handle = await env.client.start_workflow(
            VulnRemediationWorkflow.run,
            VulnRemediationRequest(repo_id="repo-A", attempt_id="att-1", ...),
            id="wf-stale", task_queue="vuln-remediation-node-npm",
        )
        await handle.result()
        # First call: returns stale RouteDecision. Second call: returns fresh.
        descent_emits = [c for c in fake_activities_stale_then_fresh.emit_event_calls
                         if c.input.payload.kind == "RouteStalenessDescent"]
        assert len(descent_emits) == 1
        descent = descent_emits[0].input.payload
        assert descent.original_decision_kind == "RouteDecision"
        assert descent.freshness_window == timedelta(days=7)
        assert fake_activities_stale_then_fresh.route_call_count == 2
        snapshot = await handle.query("state")
        assert snapshot.resume_count == 1  # one descent counted

async def test_freshness_loop_fails_unrecoverable(env, fake_activities_always_stale):
    # freshness_window=timedelta(0) on every return; both checks fail.
    async with Worker(env.client, task_queue="vuln-remediation-node-npm",
                      workflows=[VulnRemediationWorkflow], activities=fake_activities_always_stale):
        handle = await env.client.start_workflow(
            VulnRemediationWorkflow.run,
            VulnRemediationRequest(repo_id="repo-A", attempt_id="att-1", ...),
            id="wf-loop", task_queue="vuln-remediation-node-npm",
        )
        result = await handle.result()  # workflow completes; ledger is terminal failure
        snapshot = await handle.query("state")
        assert isinstance(snapshot.ledger, FailedUnrecoverable)
        assert snapshot.ledger.reason == "freshness_loop"
        descent_count = sum(1 for c in fake_activities_always_stale.emit_event_calls
                            if c.input.payload.kind == "RouteStalenessDescent")
        assert descent_count == 2  # exactly two; not infinite

async def test_boundary_equality_is_fresh():
    # Unit test the pure helper directly (extracted from _check_freshness).
    from codegenie.durable.workflows.vuln_remediation import _is_fresh
    from datetime import datetime, timezone
    t0 = datetime(2026, 5, 23, tzinfo=timezone.utc)
    assert _is_fresh(now=t0 + timedelta(days=7), decided_at=t0, freshness_window=timedelta(days=7)) is True
    assert _is_fresh(now=t0 + timedelta(days=7, seconds=1), decided_at=t0, freshness_window=timedelta(days=7)) is False
```

**Test file: `tests/workflows/test_freshness_replay_safety.py`** (replay-determinism specific)

```python
async def test_stale_resume_history_replays_clean(env, recorded_stale_history_fixture):
    """Recorded history with a stale RouteDecision replays without NondeterminismError."""
    from temporalio.testing import WorkflowReplayer
    replayer = WorkflowReplayer(workflows=[VulnRemediationWorkflow])
    await replayer.replay_workflow(recorded_stale_history_fixture)  # MUST NOT raise
```

### Green

Implement per §Implementation outline. Expected size: ~25 lines added to `vuln_remediation.py` (one helper rewrite, two arm edits, one extra query). Lift the pure `_is_fresh(now, decided_at, freshness_window) -> bool` out for direct unit testability.

### Refactor

- If the pattern repeats for additional decision payloads (Phase 10's portfolio-scan decisions, say), extract a `FreshnessAware` `Protocol` with `decided_at: datetime` and `freshness_window: timedelta` attributes; `_check_freshness` consumes the Protocol. Keep this story's implementation minimal — Phase 10 can refactor up.
- Document the boundary semantics (`<=` is fresh) in the helper's docstring; cite this AC.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/durable/workflows/vuln_remediation.py` | Replace `_check_freshness` stub; edit two arms; add `subgraph_resume_count`; add `state()` snapshot wrapper |
| `src/codegenie/durable/workflows/_types.py` | Add `WorkflowStateSnapshot` Pydantic wrapper (if pursuing the wrapper-state approach) |
| `tests/workflows/test_freshness_window_check.py` | Happy-path + stale-resume + loop tests |
| `tests/workflows/test_freshness_replay_safety.py` | Replay-determinism specific test |
| `tests/golden/temporal/vuln_remediation_stale_resume.json` | Recorded history with stale `RouteDecision` (fixture for replay test) |

## Out of scope

- **`DurableSettings.default_freshness_window` default.** S2-02 ships the Settings field; future ADR-0018 (Step 8) records the 7-day default. This story consumes whatever S4-03's activity output declares.
- **`PluginResolved` freshness check.** This story implements the `RouteDecision` arm; the `PluginResolved` arm is structurally identical and the implementer should add it in the same edit — but the *primary* test target is `RouteDecision`. `PluginResolved` follows by parameterization.
- **`gather_id` GC integration.** Phase 8's hot-view GC discipline is upstream; this story does NOT verify the `gather_id` is actually gone — only that the recorded decision is older than the window.
- **Operator-overridable freshness window via signal.** Future ADR-0018 may add a `set_freshness_window` signal; not in this story's scope.
- **Per-decision-type freshness window.** Some future phase might want shorter windows for `RouteDecision` than `PluginResolved`; both share the field today and use the same default.
- **`RouteStalenessDescent` projection.** S7-03 (`plugin_telemetry`) can fold these counts into a stale-decision histogram; not in Phase-9 scope here.

## Notes for the implementer

- **`workflow.now()` is the only legal clock.** Replay correctness depends on it. Test AC-D1 specifically exercises the replay path — if it flakes, the helper is wrong, not the test.
- **Boundary equality is fresh.** Engineers tend to write `<` when they mean `<=`; the boundary tests pin direction. Stale = `(now - decided_at) > freshness_window` strictly.
- **Tier-descent is *not* a retry loop.** A retry loop has a counter and a max; this is a *one-shot* re-dispatch within the arm, with a fail-loud fallback if the fresh decision is also stale. The S8-05 fence is grep-based; the `while` constructs in the workflow body remain only the outer `match` loop.
- **`RouteStalenessDescent` is batched, not synchronous.** Per S1-03, only 5 variants `@critical_event`; the descent is observable but not in the critical set. Don't accidentally decorate it.
- **`workflow_now` captured ONCE at arm top.** If you re-call `workflow.now()` between the staleness check and the event emission, the values differ. Bind once: `now = workflow.now()` → use `now` everywhere in the arm.
- **`subgraph_resume_count` is a metric, not a retry counter.** It increments on each descent for *observability* — operator dashboards can spike-detect. AC-G1's `2`-then-fail bound is the structural limit; the counter is *not* the limit.
- **`state()` signature additive change.** S5-02 declares `state() -> VulnLedger`. This story adds the resume count. The wrapper-shape (`WorkflowStateSnapshot(ledger, resume_count)`) is the additive-friendly evolution; a second `@workflow.query` is *also* fine if the wrapper is overkill. Pick one and document.
- **Pure helper `_is_fresh`.** Extract for unit-test directness. The workflow's `_check_freshness` method calls it but adds nothing — pure wrapping. This earns the "functional core / imperative shell" pattern.
- **`RouteStalenessDescent` variant must exist in S1-02.** Per Gap-3, S1-02 lands it on day one of the 21-variant union. If S1-02's executor hasn't shipped that variant yet, this story is BLOCKED — coordinate via the validator. (Don't add a workaround; the variant is part of the 21.)
- **The pathological-loop fail-loud is the *contract*.** Two stale-in-a-row → terminate. Without it, a misconfigured `freshness_window=timedelta(0)` would spin forever. The bound is structural, not config-driven.
- **Deferred design opportunities** (record in attempt log): (a) per-decision-type freshness windows — Phase 10 evidence; (b) operator-override signal — Phase 13 ergonomics; (c) `FreshnessAware` Protocol extraction — premature without a third consumer.
