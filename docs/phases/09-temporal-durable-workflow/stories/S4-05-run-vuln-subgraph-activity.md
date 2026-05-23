# Story S4-05 — `run_vuln_subgraph` fat activity wrapping the Phase-6 LangGraph

**Step:** Step 4 — Activity catalog (one file per activity, typed in and out, registry-collected)
**Status:** Ready
**Effort:** L
**Depends on:** S4-02 (`emit_event`, `write_blob_ref`, `resolve_blob_ref` — the subgraph emits forward into the canonical log via `emit_event`)
**ADRs honored:** ADR-0010 (asymmetric activity granularity — `run_vuln_subgraph` is the **single [S]-shape Activity** that preserves Phase-6's `SutDigest` invariance, G5 lynchpin); ADR-0011 (Postgres checkpointer adapter — LangGraph node-level resume); ADR-0008 (typed-credential blocklist at seal); production ADR-0034 (one-way emitter from subgraph into the canonical log)

## Context

This is the **single fat Activity** of the asymmetric-granularity design. ADR-0010 names the load-bearing reason: the Phase-6 SHERPA subgraph has a `SutDigest` contract pinning its in-process LangGraph checkpoint structure (G5 exit criterion). Decomposing the SHERPA subgraph into one-Activity-per-node would shatter the digest contract — every node would have its own Temporal-history record, the LangGraph state machine would be reconstructed from those records, and the resulting checkpoint shape would not match the in-process baseline. The G5 conformance harness (`tests/conformance/sut/*` from Phase 6.5) would fail across every canonical case.

Instead: **one Activity wrapping the entire LangGraph subgraph**, with node-level resume provided by `PostgresCheckpointerAdapter` (S5-01) instead of Temporal-history records. The Phase-6 LangGraph's `PostgresSaver` checkpoints every node transition; on activity-worker SIGKILL, Temporal re-dispatches the activity and LangGraph resumes from the last node checkpoint — same state, same `SutDigest`. This is **G1's lynchpin** (the kill-worker-resume durability test, S8-01, exercises this exact path).

**Why this is the largest story in Step 4.** Six discipline points compose here:
1. **Idempotence on `AttemptId`.** Re-dispatch must reuse the prior checkpoint, not start a fresh subgraph.
2. **Heartbeat cadence.** Every 5 s, sub the 30 s Temporal heartbeat-timeout, with margin for slow Postgres writes.
3. **`SutDigest` invariance.** The `digest()` Phase-6 builder must produce byte-identical output across `LocalVulnRemediationSut` and `TemporalVulnRemediationSut` (G5; the bridge in S6-03 owns this assertion; this story's discipline is preserving the digest input shape).
4. **One-way event emission.** The subgraph emits `TrustGatePassed`, `RecipeApplied`, `PatchApplied`, etc. into the canonical event log via `emit_event` calls inside the Activity. Phase-8's `codegenie.plugins.events` log runs in parallel for the 30-day-drain window; phase ADR-0002 governs the cutover.
5. **20-minute `start_to_close_timeout`.** From S4-01's `_POLICIES`. If exceeded, the workflow's `match` arm escalates to `AwaitingHumanReview` rather than retrying the whole subgraph. Open question #1 (continue-as-new) is the deferred follow-up.
6. **`SubgraphOutcome` sum type.** Return is one of `SubgraphCompleted | SubgraphPausedHITL | SubgraphFailed`; the workflow's `match` arm (S5-02) decides next steps.

**Scope reminder.** This story ships the Activity wrapper + the typed input/output models + the heartbeat machinery + the idempotence-on-`AttemptId` resume logic. The Phase-6 SHERPA subgraph itself is Phase 6's responsibility — already shipped; this story does NOT modify any Phase-6 code. The bridge that exposes `TemporalVulnRemediationSut` against the Phase-6.5 conformance harness is S6-03. The G5 conformance test (`tests/durability/test_sut_digest_invariance.py`) is also S6-03. This story's contribution to G5 is preserving the input shape and checkpoint structure that make G5 reachable.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Executive summary` — "the **Phase-6 SHERPA subgraph** runs *inside one fat `run_vuln_subgraph` Activity* ([S] shape) because the Phase-6 `SutDigest` contract depends on the in-process LangGraph checkpoint structure."
  - `../phase-arch-design.md §C2 — Activity catalog` lines 482-486 — `run_vuln_subgraph p50 ~4 min / p95 ~8 min`; heartbeat per 5 s.
  - `../phase-arch-design.md §Sequence diagrams Scenario 2 — Failure path` (lines 370-393) — activity-worker SIGKILL mid-`run_vuln_subgraph`; LangGraph PostgresSaver node-level resume; idempotency-on-`attempt_id` means partially-applied patch is reused.
  - `../phase-arch-design.md §Implementation risks specific to this step` — heartbeat cadence sub the 30 s Temporal timeout; idempotence-on-`AttemptId` is the G1 lynchpin.
- **Phase ADRs:**
  - `../ADRs/0010-activity-granularity-asymmetric.md` (full) — the rationale for the single-fat-Activity shape; §Consequences names heartbeat cadence + 20-min timeout.
  - `../ADRs/0011-checkpointer-backend-postgres.md` — `PostgresCheckpointerAdapter` provides node-level resume.
  - `../ADRs/0002-phase-8-plugin-events-log-cutover-to-canonical-event-log.md` — the one-way emitter pattern; this story's `emit_event` calls inside the subgraph honor the cutover.
- **Production ADRs:**
  - `../../../production/adrs/0034-event-sourcing-canonical-primitive.md` — the subgraph's events flow into the canonical log.
  - `../../../production/adrs/0016-checkpointer-backend.md` — Postgres as the default checkpointer; ADR-0011 resolves the deferral.
- **Existing code (the wrapped layer):**
  - Phase-6 SHERPA subgraph (path: `src/codegenie/sherpa/` or similar) — `build_subgraph(...) -> CompiledStateGraph`; this story consumes the existing factory.
  - Phase-6.5 `VulnRemediationSut` Protocol — the contract S6-03's bridge implements.
- **Sibling stories:**
  - `S5-01-postgres-checkpointer-adapter.md` — supplies the `PostgresCheckpointerAdapter` this Activity injects into the LangGraph.
  - `S6-03-temporal-sut-bridge.md` — consumer; asserts `SutDigest` invariance.
  - `S8-01-kill-worker-resume.md` — G1 durability test; kills the activity worker mid-flight and asserts byte-identical terminal `VulnLedger`.

## Goal

Ship `src/codegenie/durable/activities/run_vuln_subgraph.py` — a single `@activity.defn`-decorated function that (a) accepts a typed `RunSubgraphInput` Pydantic model, (b) constructs the Phase-6 LangGraph with `PostgresCheckpointerAdapter` for resume, (c) executes the subgraph with idempotence-on-`AttemptId` (re-dispatch reuses prior LangGraph checkpoint), (d) heartbeats every 5 s during long subgraph runs, (e) emits forward into the canonical event log via `emit_event` calls, (f) returns a `RunSubgraphOutput` carrying a `SubgraphOutcome` sum-type, (g) preserves the input shape and checkpoint structure that make G5's `SutDigest` invariance reachable.

## Acceptance criteria

- [ ] **AC-1 — `RunSubgraphInput` typed model.** Defines `class RunSubgraphInput(BaseModel, frozen=True, extra="forbid")` with fields: `workflow_id: WorkflowId`, `repo_snapshot_ref: BlobRef`, `cve_record_ref: BlobRef`, `plugin_id: PluginId`, `route_decision: RouteDecision` (the result of the prior `route` Activity, including Gap-3 `decided_at` + `freshness_window`), `attempt_id: AttemptId`, `capability: EventLogWriteCapability` (subgraph emits forward via this).
- [ ] **AC-2 — `RunSubgraphOutput` + `SubgraphOutcome` sum type.** Defines `class RunSubgraphOutput(RedactedActivityResult)` with `outcome: SubgraphOutcome`, `patch_ref: BlobRef | None`, `evidence_ref: BlobRef | None`, `subgraph_seq_count: int` (number of LangGraph node transitions), `attempt_id: AttemptId`. `SubgraphOutcome = SubgraphCompleted | SubgraphPausedHITL | SubgraphFailed`, each variant a frozen Pydantic model with `kind: Literal[...]` discriminator. `SubgraphFailed` carries `reason: SubgraphFailureReason` (sum type: `RecipeMissedError | RagMissedError | LlmExhausted | SandboxFailed`) — the workflow body matches on this for Phase-4 tier-descent.
- [ ] **AC-3 — Decorator stack.** `@register_activity(name=ActivityName("run_vuln_subgraph"), task_queue=TaskQueueName("vuln-remediation-node-npm"))` (outer) + `@activity.defn(name="run_vuln_subgraph")` (inner). The name matches `_POLICIES["run_vuln_subgraph"]` (timeout = 20 min, heartbeat_timeout = 30 s).
- [ ] **AC-4 — Idempotence-on-`AttemptId` via checkpoint reuse.** On re-dispatch with the same `attempt_id`, the Activity body MUST: (a) read the prior LangGraph checkpoint from `PostgresCheckpointerAdapter` keyed on `attempt_id`; (b) resume the subgraph from the latest node checkpoint; (c) NOT re-run nodes that already committed. Test: invoke `run_vuln_subgraph`; SIGKILL the LangGraph mid-flight (simulated via `pytest-asyncio` task cancel); re-invoke with identical input; assert the subgraph resumes at the last checkpointed node (asserted via `_FakeSubgraph.resume_count == 1` AND the prior node's emitted events are NOT re-emitted).
- [ ] **AC-5 — Heartbeat cadence (5 s sub 30 s timeout).** During a >15-second subgraph run, the Activity emits ≥3 heartbeats via `temporalio.activity.heartbeat(...)`. Mechanism: an `asyncio.create_task` that loops `await asyncio.sleep(5); activity.heartbeat({"node": current_node, "subgraph_seq": ...})` alongside the LangGraph execution. Test asserts `temporalio.activity.heartbeat` call count ≥3 over a 15 s fake run.
- [ ] **AC-6 — Forward emission into canonical log.** As the subgraph executes, every Phase-6 hash-chained log entry (`TrustGatePassed`, `RecipeApplied`, `PatchApplied`, `TrustGateFailed`, etc.) is mirrored forward via `emit_event(...)` into the canonical event log. Test: run a fake subgraph that yields 3 events; assert 3 rows land in `events.events` via the fake event log fixture; assert each row's `kind` matches the Phase-6 source's `kind` field byte-identically. This is the phase ADR-0002 one-way-emitter mechanism.
- [ ] **AC-7 — `SutDigest`-preservation discipline.** The Activity body MUST NOT mutate `RunSubgraphInput` fields between receipt and subgraph dispatch; the LangGraph initial-state MUST be derived from `input` deterministically. A test asserts that for two distinct invocations with byte-identical `input`, the Phase-6 `digest()` builder consumed by `LocalVulnRemediationSut` and (theoretically) `TemporalVulnRemediationSut` produces byte-identical bytes — using an in-process `digest_for_input(input)` helper this story exposes. (The full G5 cross-SUT assertion is S6-03; this story locks in the input-shape invariant.)
- [ ] **AC-8 — `SubgraphFailed.reason` carries tier-descent triggers (non-retryable).** A test verifies that `SubgraphFailed(reason=RecipeMissedError(...))` is the typed shape returned when the recipe-tier fails; the workflow body matches on this and descends to RAG without retrying the Activity (the `_POLICIES["run_vuln_subgraph"].non_retryable_error_types` from S4-01 includes `RecipeMissedError`). This story ships the **typed return**; S5-02 ships the `match` arm that consumes it.
- [ ] **AC-9 — Workflow-history compactness (G8).** The Activity's return (`RunSubgraphOutput`) MUST cross as <2 MiB at the JSON-serialized boundary. Large artifacts (patch, evidence) cross as `BlobRef` (the `patch_ref` and `evidence_ref` fields). A test asserts `len(out.model_dump_json().encode("utf-8")) < 2_000_000` for the canonical fixture; without this, Temporal-history bloats and G8 regresses silently.
- [ ] **AC-10 — `_EXPECTED_BUT_UNSHIPPED` trim.** Remove `ActivityName("run_vuln_subgraph")` from S4-01's set. Test: `policy_for(ActivityName("run_vuln_subgraph")).start_to_close_timeout == timedelta(minutes=20)`; `.heartbeat_timeout == timedelta(seconds=30)`; `.non_retryable_error_types` includes `"RecipeMissedError"` and `"RagMissedError"`.
- [ ] **AC-11 — Explicit-import collection extension.** One new import line in `__init__.py`; the collection test now asserts nine activity names register (the full Step 4 set).
- [ ] **AC-12 — Lint / type clean.** `ruff check`, `ruff format --check`, `mypy --strict` clean. `make lint-imports` clean. `make typecheck` green.

## Implementation outline

1. **Define `RunSubgraphInput` / `RunSubgraphOutput` / `SubgraphOutcome` / `SubgraphFailureReason`** in `run_vuln_subgraph.py`. The sum types are colocated until a second consumer needs them; lift to `codegenie.events.payloads` only on the second reference.
2. **Heartbeat helper** (`_heartbeat_task`): a small `asyncio.create_task` that loops `await asyncio.sleep(5); activity.heartbeat({"node": tracker.current_node})` until the wrapped LangGraph dispatch returns. Cancel the task in the `finally` clause.
3. **Idempotence check**: pre-dispatch, query `PostgresCheckpointerAdapter` for any checkpoint keyed on `attempt_id`; if present, the LangGraph naturally resumes from it on the next `astream` call. The Activity does NOT manually replay; LangGraph's `PostgresSaver` handles it transparently. The discipline is: pass the same `attempt_id`-derived thread key to LangGraph on every invocation.
4. **LangGraph compilation**: construct the Phase-6 subgraph via the existing `build_subgraph(...)` factory (Phase 6); inject `PostgresCheckpointerAdapter.saver()` as the checkpointer. Do NOT re-construct the subgraph from scratch on each invocation; cache the compiled graph at module-level (mutable hot path; one allocation per worker process).
5. **Event forwarding**: wire a small `_EventForwarder` listener that subscribes to the subgraph's emitted records; for each record, call `emit_event` (the *data layer* helper from S4-02, NOT the Activity — see S4-03 §3 for the rationale).
6. **`SubgraphOutcome` construction**: post-LangGraph-completion, inspect the terminal `VulnLedger` and translate to one of the three outcome variants. The translation is mechanical; the workflow body's `match` arm consumes the typed shape.
7. **`__init__.py`**: add the explicit-import line.
8. **`_EXPECTED_BUT_UNSHIPPED`**: remove the name.

## TDD plan — red / green / refactor

### Red — failing test first

```python
# tests/unit/durable/activities/test_run_vuln_subgraph.py
import asyncio
import pytest
from codegenie.durable.activities.run_vuln_subgraph import (
    run_vuln_subgraph, RunSubgraphInput,
)


async def test_run_vuln_subgraph_resumes_from_checkpoint_on_redispatch(
    fake_postgres_checkpointer, fake_subgraph, fake_event_log, vuln_capability,
):
    """AC-4 — Idempotence-on-AttemptId is the G1 durability lynchpin. The
    reason this is the red test: if re-dispatch starts the subgraph from
    scratch, every kill-worker-resume cycle reprocesses N nodes that already
    committed — the canonical event log doubles, the LangGraph checkpoint
    shape diverges, and SutDigest invariance (G5) fails. Lock in the
    checkpoint-resume invariant from day one."""
    inp = RunSubgraphInput(
        workflow_id=WorkflowId("wf-1"),
        attempt_id=AttemptId("a-1"),
        ...,
    )
    fake_subgraph.set_node_count(5)
    fake_subgraph.kill_at_node(3)  # simulate worker SIGKILL after node 3
    with pytest.raises(asyncio.CancelledError):
        await run_vuln_subgraph(inp)

    # Re-dispatch with same attempt_id — LangGraph should resume from node 3
    fake_subgraph.clear_kill()
    out = await run_vuln_subgraph(inp)
    assert fake_subgraph.nodes_executed_post_resume == [4, 5]  # not [1..5]
    assert fake_event_log.kinds_emitted().count("NodeCompleted") == 5  # not 8
```

Why it fails: `codegenie.durable.activities.run_vuln_subgraph` doesn't exist.

### Green — minimal pass

- Ship the module.
- Activity body: pre-flight checkpoint check (via `PostgresCheckpointerAdapter`); start heartbeat task; dispatch the LangGraph via `astream`; forward events as they emit; on completion, construct typed outcome and seal.

### Required follow-on tests (per AC)

```python
async def test_run_vuln_subgraph_heartbeats_at_5s_cadence(
    fake_subgraph, fake_event_log, vuln_capability, monkeypatch,
):
    """AC-5 — heartbeats sub the 30 s Temporal timeout with 6× margin.
    Without heartbeats, a slow Postgres flush mid-subgraph triggers
    heartbeat-timeout, Temporal re-dispatches mid-flight, and the
    subgraph runs twice from the last checkpoint — the resume itself works
    but the re-dispatch was unnecessary; G1 still passes but throughput
    regresses. The 5 s cadence prevents the spurious re-dispatch."""
    heartbeats = []
    monkeypatch.setattr(
        "temporalio.activity.heartbeat",
        lambda payload: heartbeats.append(payload),
    )
    fake_subgraph.set_run_duration(seconds=15)
    await run_vuln_subgraph(RunSubgraphInput(...))
    assert len(heartbeats) >= 3


async def test_run_vuln_subgraph_forwards_events_into_canonical_log(
    fake_subgraph, fake_event_log, vuln_capability,
):
    """AC-6 — one-way emitter (phase ADR-0002). Every Phase-6 hash-chained
    log entry mirrors forward into events.events. Without this, the
    canonical log is missing the per-node detail that audit projections
    (S7-01) depend on; the audit trail has gaps at exactly the moments
    that matter most (gate decisions, recipe applications)."""
    fake_subgraph.queue_emit("TrustGatePassed", payload={...})
    fake_subgraph.queue_emit("RecipeApplied", payload={...})
    fake_subgraph.queue_emit("PatchApplied", payload={...})
    await run_vuln_subgraph(RunSubgraphInput(...))
    kinds = fake_event_log.kinds_emitted()
    assert "TrustGatePassed" in kinds
    assert "RecipeApplied" in kinds
    assert "PatchApplied" in kinds


async def test_run_vuln_subgraph_returns_typed_failure_reason(
    fake_subgraph, fake_event_log, vuln_capability,
):
    """AC-8 — SubgraphFailed.reason is the typed sum type the workflow's
    match arm consumes for Phase-4 tier-descent. Without typed reasons,
    the workflow body inspects strings (or worse, exception types via
    isinstance) and the OPEN/CLOSED extensibility breaks — adding a fourth
    failure mode requires changes in N places instead of one."""
    fake_subgraph.fail_with(RecipeMissedError("no recipe for CVE-2024-..."))
    out = await run_vuln_subgraph(RunSubgraphInput(...))
    assert isinstance(out.outcome, SubgraphFailed)
    assert isinstance(out.outcome.reason, RecipeMissedError)


def test_run_vuln_subgraph_output_under_2mib():
    """AC-9 — workflow-history compactness; large artifacts cross as BlobRef.
    Without this, a single 2 MiB patch would inflate Temporal-history by
    2 MiB per workflow; G8 regresses; the temporal-ui becomes unusable."""
    out = RunSubgraphOutput(
        outcome=SubgraphCompleted(...),
        patch_ref=BlobRef(...),       # NOT bytes
        evidence_ref=BlobRef(...),     # NOT bytes
        subgraph_seq_count=42,
        attempt_id=AttemptId("a-1"),
    )
    assert len(out.model_dump_json().encode("utf-8")) < 2_000_000


def test_run_vuln_subgraph_input_shape_preserves_digest_input():
    """AC-7 — SutDigest-preservation discipline. The input shape this
    Activity consumes MUST match the input shape Phase-6's
    LocalVulnRemediationSut consumes for digest computation. Without this,
    the cross-SUT assertion in S6-03 (G5) silently diverges and we don't
    find out until conformance runs."""
    inp = RunSubgraphInput(...)
    # Phase-6 builder helper, repurposed here to assert byte-identical:
    from codegenie.sherpa.digest import digest_for_input
    assert digest_for_input(inp) == digest_for_input(RunSubgraphInput.model_validate_json(inp.model_dump_json()))
```

### Refactor

- Module docstring: cites ADR-0010 (the asymmetric-granularity rationale), ADR-0011 (Postgres checkpointer), and phase ADR-0002 (one-way emitter). Names this file as **the G1 durability lynchpin**.
- The `_heartbeat_task` helper carries a docstring naming the 5 s × 30 s margin rationale.
- The `SubgraphFailureReason` sum type's docstring names each variant's downstream consumer in S5-02.
- Module-level `_COMPILED_GRAPH: Final[CompiledStateGraph | None] = None` cached on first invocation; the docstring names the per-worker-process caching invariant.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/durable/activities/run_vuln_subgraph.py` | Activity body, input/output models, `SubgraphOutcome` + `SubgraphFailureReason` sum types, heartbeat machinery, event forwarder. |
| `src/codegenie/durable/activities/__init__.py` | One new explicit-import line. |
| `src/codegenie/durable/activities/retry_policies.py` | Trim `run_vuln_subgraph` from `_EXPECTED_BUT_UNSHIPPED` (this is the LAST one — the set goes to `frozenset()`; AC-6 of S4-01 then fails-loud if the constant survives). |
| `tests/unit/durable/activities/test_run_vuln_subgraph.py` | Red test + per-AC follow-on. |
| `tests/unit/durable/activities/conftest.py` | Add `fake_subgraph`, `fake_postgres_checkpointer` fixtures. |

## Out of scope

- The Phase-6 SHERPA subgraph itself — already shipped; this story wraps, not authors. NO modifications to `src/codegenie/sherpa/*`.
- The `PostgresCheckpointerAdapter` implementation — S5-01.
- The `TemporalVulnRemediationSut` bridge — S6-03.
- The G5 conformance test (`tests/durability/test_sut_digest_invariance.py`) — S6-03.
- The G1 kill-worker-resume durability test (`tests/durability/test_kill_worker_resume.py`) — S8-01.
- Continue-as-new behavior for >20-min subgraph runs — open question #1, deferred to Phase 10.
- Phase-8's `codegenie.plugins.events` log deprecation — Phase 10's first commit deletes it (phase ADR-0002).
- Deciding the workflow's `match` arm responses to each `SubgraphOutcome` variant — S5-02.

## Notes for the implementer

### §1 — The asymmetric-granularity decision is non-negotiable

ADR-0010 carries the load-bearing rationale: Phase-6 `SutDigest` invariance is a G5 exit criterion; decomposing the SHERPA subgraph into per-node Activities would shatter the digest. A reviewer who sees the single-Activity wrapping `~30 LangGraph nodes` may suggest "let's decompose for per-node observability." Surface ADR-0010 and the §Reversibility row: decomposing later is a refactor that necessarily breaks `SutDigest` invariance and requires regenerating every Phase-6.5 conformance fixture. That work is exactly what the asymmetric shape avoids paying.

The Phase-8 Supervisor's three Activities (S4-03) demonstrate the *other* shape — per-node observability — for the case where no digest contract pins the checkpoint structure. The codebase carries both patterns intentionally; engineers must remember which applies where, and the ADR is the audit anchor.

### §2 — `attempt_id` is the only idempotency key that matters here

Two false alternatives:
- Idempotency on `workflow_id` alone: would prevent ANY re-execution of the subgraph for a workflow, breaking the retry semantics the policy table prescribes.
- Idempotency on a content hash of the input: would silently dedupe two distinct attempts that happen to have identical inputs (e.g., a deliberate human-triggered retry after an external system change).

`attempt_id` is unique per logical attempt (the workflow body bumps it on each new retry cycle). It IS the right key. The `PostgresCheckpointerAdapter` keys the LangGraph thread on `attempt_id`-derived state; identical `attempt_id` = identical thread = resume from checkpoint.

### §3 — Heartbeat payload carries observable progress

`activity.heartbeat({"node": current_node, "subgraph_seq": ...})` — not `activity.heartbeat()` with no payload. The payload lands in Temporal-history and is visible in `temporal-ui` (a UI consumer at S6-01's worker bootstrap can render it). Without the payload, `temporal-ui` shows "activity heartbeating" with no detail; with it, operators see node-level progress without leaving the Temporal UI. The discipline applies broadly: heartbeat = observable progress, not just liveness.

### §4 — Compiled graph caching across invocations

LangGraph subgraph compilation is non-trivial (~50–100 ms per `build_subgraph(...)` call). Phase 9's worker is long-running (no per-invocation respawn); cache the compiled graph at module-level:

```python
_COMPILED_GRAPH: CompiledStateGraph | None = None

async def run_vuln_subgraph(input: RunSubgraphInput) -> RunSubgraphOutput:
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is None:
        _COMPILED_GRAPH = build_subgraph(...)
    ...
```

The `global` is unusual in this codebase (functional-core preference) but is the right shape here — per-invocation recompilation would burn 100 ms of activity-worker time on every call and inflate the p50 envelope visibly. The mutation is once-per-worker-process; no concurrency hazard.

### §5 — Forward emission honors phase ADR-0002

Until Phase 10's first commit, Phase-8's `codegenie.plugins.events` log runs alongside the canonical log. This Activity's forwarder writes events to BOTH paths during the drain window. Phase 10 deletes the old path; the forwarder shrinks to one path then. The discipline today is: a contributor MUST NOT silently delete the old-path emission "because we have the new one." The 30-day-drain is a deliberate consumer-cutover window. (Phase 10's first commit removes the old emission AND the parallel-write code.)

### §6 — `SubgraphOutcome` and the workflow's `match` arm

The three variants (`SubgraphCompleted | SubgraphPausedHITL | SubgraphFailed`) map exactly to the three workflow-body branches (`proceed to PR / wait for signal / tier-descend or escalate HITL`). The `SubgraphFailed.reason` sum type carries the tier-descent triggers. The workflow body's `match` arm uses `assert_never` so adding a fourth outcome is a mypy error in every consumer.

If a future contributor proposes a `SubgraphRetrying` variant (e.g., "the subgraph is in mid-retry"), surface the design discipline: the workflow body owns the retry decision via Temporal's `RetryPolicy`; the Activity returns ONE terminal outcome and Temporal handles retry by re-invoking the Activity. A `SubgraphRetrying` variant would conflate the Activity's terminal-state contract with the workflow's retry-cycle observability — the wrong layer.

### §7 — `make typecheck` is the long-pole gate

This is the largest single module in Step 4 by LOC; `mypy --strict` will surface every type annotation drift. Pay attention to:
- `RunSubgraphOutput | None` vs `Optional[RunSubgraphOutput]` (use the former; pre-3.10 syntax doesn't compose with `Field(discriminator=...)`).
- LangGraph's `BaseCheckpointSaver` type (the upstream library; may need a `[tool.mypy.overrides]` row in `pyproject.toml` if upstream stubs are weak — but get this RIGHT before adding the override; the override is the kind of thing that hides the type bug).
- `asyncio.create_task` return type — `Task[None]` if the loop body returns `None`.

### §8 — G1 is the lynchpin

The G1 durability test (S8-01, `tests/durability/test_kill_worker_resume.py`) kills the activity worker at N offsets across this subgraph and asserts the terminal `VulnLedger` is byte-identical across runs. That test passes if and only if AC-4 (idempotence-on-`AttemptId`) and AC-7 (`SutDigest`-preservation) hold. This story's discipline is the substrate that makes G1 pass. If S8-01 starts failing intermittently after this story lands, the first place to look is the AC-4 resume-from-checkpoint logic.
