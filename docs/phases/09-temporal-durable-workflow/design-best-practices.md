# Phase 09 — Durable workflow envelope: Temporal: Best-practices design

**Lens:** Best practices — idiomatic, maintainable, conventional, well-tested.
**Designed by:** Best-practices design subagent
**Date:** 2026-05-23

## Lens summary

I optimized for the next engineer reading this code cold: a Temporal workflow that wraps the Phase-6 SHERPA loop should look like a thin, deterministic outer envelope that **delegates everything interesting to typed Activities**, and an event log that looks like one obvious append-only Postgres table read by small projection functions. The Phase-9 surface is composed of three things that are individually boring and well-documented patterns — (1) a Temporal workflow built from Temporal-idiomatic `@workflow.defn` + `@activity.defn` per the SDK's own guidance, (2) a `PostgresSaver` checkpointer from `langgraph-checkpoint-postgres` (the upstream-supported package — we don't write our own checkpointer) wired into the Phase-6 `VulnRemediationSut` builder behind a Port, and (3) a single typed Postgres `events` table with a Pydantic-discriminated-union `Event` model, an append-only writer, and one projection per consumer. The Supervisor graph compiled in Phase 8 is *already* shaped to map node-for-node onto Temporal Activities (Phase 8's `Supervisor` is a three-node LangGraph "deliberately the Phase-9 Temporal-Activity seam") — Phase 9's job is to *wire* that mapping, not to redesign anything upstream. I deprioritized clever performance tricks (Temporal handles retry, backoff, and rate limits; we don't), exotic event-store implementations (Postgres + `INSERT ... RETURNING` + a primary key is the right answer; EventStoreDB and Kafka are wrong for this phase's volume), and any speculative pluggability beyond what ADR-0034 mandates (the `events` table is the event store; we don't build an "event-store-abstraction layer"). Where best practices and exit criteria collide, I surface it (see Risks): determinism rules on workflow code are non-negotiable, and a `ContextVar`-based audit-event sink will leak Temporal's determinism budget if it ever fires inside workflow code.

## Conventions honored

- **No LLM in the gather pipeline →** Temporal's workflow and activity code is 100% deterministic. The `fence` job (`tests/unit/test_pyproject_fence.py`) and `import-linter` already forbid `anthropic|openai|langgraph|langchain|transformers` from `codegenie.*`; Phase 9 adds the same fence to `codegenie.durable.*` and `codegenie.events.*`. The Phase-4 LLM fallback continues to live behind the `LeafLlmPort`, called only from inside one activity (`plan_with_llm_fallback`) — the workflow code never imports it.
- **Facts, not judgments →** events record what happened (`PatchApplied(digest=…, gate_outcome=…)`, `LlmFallbackInvoked(reason=…, tokens=…)`), never conclusions (`MigrationSafe`). Projections (cost ledger, ROI, audit trail) compute their judgments from typed facts; the event log itself is fact-only. This is the natural extension of commitment §2.2 to the event store.
- **Extension by addition →** Phase 9 adds **three** net-new top-level packages — `codegenie.durable` (workflow + activities + checkpointer adapter), `codegenie.events` (typed event models + log + projections), and `codegenie.events.projections` (one module per registered projection) — and edits Phase-6 plugin subgraph code only at compiler/fence-policed wiring lines (the `VulnRemediationSut` builder gains a `checkpointer` parameter; the existing call sites pass the new `PostgresSaver`). Adding a new event variant = one new Pydantic class registered in the `EventPayload` discriminated union; adding a new projection = one new module registered via `@register_projection(name)`. Zero edits to existing event classes or projection modules.
- **Functional core / imperative shell →** the workflow is the imperative shell that schedules activities; every activity has a pure-functional core (`apply_patch_pure(repo_snapshot, plan) -> PatchResult`) plus a thin imperative wrapper that does I/O. The projection consumers are pure functions: `fold_cost_ledger(events: Sequence[Event]) -> CostLedger`. This is the test seam — projections are tested with fixture event streams; no Temporal, no Postgres, no fixtures-on-disk.
- **Typed primitives →** every domain identifier in Phase 9 is a `NewType`: `WorkflowId`, `ActivityId`, `EventId` (UUID4), `EventStreamId`, `ProjectionId`, `CorrelationId`, `MigrationVersion`. No raw `str` flows across module boundaries. Per ADR-0033 §1 — "raw `str` is reserved for genuinely-untyped contexts (log lines, user-facing strings)."
- **Honest confidence →** the `WorkflowResumed` and `ActivityRetried` events carry the retry count and the last failure reason. The audit projection surfaces "this workflow resumed 3 times from `apply_patch`" rather than hiding it; per `CLAUDE.md` Rule 12 ("Fail loud"), silent retries are an antipattern even when Temporal makes them invisible by default.
- **ADR-0033 domain-modeling discipline →** every event is a Pydantic v2 model with `frozen=True, extra="forbid"`; the event union is a discriminated union on `kind: Literal[...]`; every event handler uses `match` + `assert_never` so missing-case bugs are compile errors. The `WorkflowState` (terminal status) is a sum type `Running | AwaitingHuman | Completed | Failed | Cancelled`, never a boolean grid.
- **ADR-0034 event sourcing canonical primitive →** Phase 9 ships exactly the **hybrid** the ADR specifies: Temporal workflow history is the workflow-internal event store (we read it via the SDK's `get_workflow_history` for replay-driven debugging — we do not duplicate it); the Postgres `events` table is the workflow-spanning side-channel. The Phase-8 `codegenie.plugins.events` hash-chained log (the audit-anchor format Phase 6 and Phase 8 already produce) becomes a **projection source** in Phase 9 — its records are migrated to typed events on first read, and new emissions in Phase 9+ go straight to the canonical log. Phase 11 (Learning) and Phase 13 (cost ledger + ROI) ship as projection modules; their independent stores never exist.

## Goals (concrete, measurable)

- **Public API surface (count):** ≤ 18 exported names across the three new packages — `codegenie.durable` (≤7: `VulnWorkflow`, `WorkflowConfig`, `WorkflowState`, `build_worker`, `PostgresCheckpointerAdapter`, `WorkflowError`, `register_activity`), `codegenie.events` (≤7: `Event`, `EventPayload`, `EventLog`, `EventId`, `WorkflowId`, `record_event`, `EventLogError`), `codegenie.events.projections` (≤4: `register_projection`, `Projection`, `replay`, `ProjectionError`). The five concrete event variants Phase 9 ships are re-exported under `codegenie.events.payloads`; that namespace can grow without inflating the four packages' top-level surface.
- **Test coverage target:** ≥ 90% line on the three new packages (above the 85% repo gate); **100% branch** on the `Event` discriminator (`fold` over every variant), the `PostgresCheckpointerAdapter.save / load` round-trip, and the workflow's resume-from-checkpoint branch — the three exit-criteria-bearing surfaces.
- **Cyclomatic complexity ceiling per module:** ≤ 8 per function (`ruff` `C901`); the `match` over `Event` variants in each projection is allowed to approach it and stays table-driven (one short `case` per variant, no nested logic — the variant-handler is a separate function).
- **Net-new top-level packages:** 3 (`codegenie.durable`, `codegenie.events`, `codegenie.events.projections`). The plugin subgraph code in `plugins/vulnerability-remediation--node--npm/subgraph/` is untouched; the `VulnRemediationSut` builder gains one parameter and is otherwise unchanged.
- **Plain-Python vs framework-coupled ratio:** ~75/25. The event models, the event log writer, every projection module, the workflow-state sum type, and the checkpointer adapter contract are plain Python + Pydantic. Temporal coupling is confined to `codegenie.durable.workflows` (the `@workflow.defn` definitions) and `codegenie.durable.activities` (the `@activity.defn` thin wrappers); `langgraph-checkpoint-postgres` coupling is one module (`PostgresCheckpointerAdapter`).

## Architecture

```
                                Temporal local dev server (`temporal server start-dev`)
                                docker-compose adds: temporal-ui, postgres:16-alpine
                                              │
   workflow trigger                           │   (gRPC, port 7233)
   ┌───────────────┐    StartWorkflow         │
   │ codegenie CLI │ ───────────────────────▶ │
   │ /webhook/...  │    (workflow_id=…)        │
   └───────────────┘                          ▼
                              ┌────────────────────────────────────────────────────┐
                              │  Temporal Server (history, task queues, signals)    │
                              │   - workflow history = workflow-internal event store│
                              │   - signals = HITL resume (Phase 6 interrupt path)  │
                              └─────────────────────────┬──────────────────────────┘
                                                        │ poll task queue
                                                        ▼
   ┌──────────────────────────────────────────────────────────────────────────────────┐
   │ codegenie.durable.workers  — separate process; `build_worker()` entrypoint        │
   │                                                                                    │
   │   codegenie.durable.workflows.VulnWorkflow            [NEW — @workflow.defn]       │
   │     - deterministic outer envelope                                                  │
   │     - one workflow per (repo × CVE × task-class)                                    │
   │     - calls activities in the order: resolve → gather → plan → execute → validate   │
   │     - signal handlers: pause_for_human, resume_from_human, cancel                   │
   │     - retry policy lives in @activity.defn options, NOT in workflow code            │
   │                                                                                    │
   │   codegenie.durable.activities         [NEW — @activity.defn one per stage]        │
   │     - resolve_plugin            (wraps codegenie.plugins.resolver) [REUSED]        │
   │     - build_bundle              (wraps codegenie.plugins.BundleBuilder) [REUSED]   │
   │     - plan_with_recipes         (wraps Phase 3 RecipeEngine.apply) [REUSED]        │
   │     - plan_with_rag             (wraps Phase 4 RAG retriever) [REUSED]             │
   │     - plan_with_llm_fallback    (wraps LeafLlmPort) [REUSED]                       │
   │     - apply_patch               (wraps Phase 3 NpmLockfileRecipeEngine) [REUSED]   │
   │     - run_sandbox_gate          (wraps Phase 5 SubprocessJail) [REUSED]            │
   │     - open_pr (Phase 11)        (deferred — not in Phase 9)                        │
   │                                                                                    │
   │   codegenie.durable.checkpointer                       [NEW — adapter]              │
   │     PostgresCheckpointerAdapter implements LangGraphCheckpointerPort                │
   │       internally uses langgraph_checkpoint_postgres.PostgresSaver                   │
   │       — replaces the Phase-6 InMemorySaver / SqliteSaver default                   │
   │     wired into the VulnRemediationSut builder (one new parameter, default behind   │
   │     a feature flag for Phase-6 backward compatibility during rollout)              │
   └──────────────────────────────────────────────────────────────────────────────────┘
                              │                          │
        every activity emits  │                          │ checkpoint writes
        a typed event via the │                          │ (LangGraph state per
        record_event() helper │                          │ semantic boundary)
                              ▼                          ▼
                  ┌─────────────────────────┐  ┌──────────────────────────┐
                  │ codegenie.events.log     │  │ langgraph_checkpoint     │
                  │  EventLog               │  │  schema (PostgresSaver)   │
                  │  - INSERT INTO events    │  │  - upstream-defined; we   │
                  │  - one row per Event     │  │    own migrations via     │
                  │  - JSONB payload (typed) │  │    alembic                │
                  │  - WorkflowId index      │  │                          │
                  └─────────────────────────┘  └──────────────────────────┘
                              ▲                          ▲
                              │ shared connection pool   │
                              ▼                          ▼
                  ┌───────────────────────────────────────────────────────┐
                  │  postgres:16-alpine  (docker-compose; alembic-managed) │
                  │  Schemas:                                              │
                  │    public.events           — Phase 9 (ADR-0034)        │
                  │    public.langgraph_*      — PostgresSaver upstream    │
                  │    public.temporal         — Temporal's own store      │
                  └───────────────────────────────────────────────────────┘
                              ▲
                              │  read-only fold
                              │
                  ┌───────────────────────────────────────────────────────┐
                  │ codegenie.events.projections   [NEW — one mod each]    │
                  │   @register_projection("audit_trail")                  │
                  │   @register_projection("cost_ledger_v1")               │
                  │   @register_projection("retry_histogram")              │
                  │     Phase 11 will register("learning_kg_writeback")    │
                  │     Phase 13 will register("roi_dashboard_v1")         │
                  │                                                        │
                  │   each projection: fold(events: Sequence[Event]) -> M  │
                  │   pure, exhaustive over EventPayload variants          │
                  │   idempotent — running twice produces same M           │
                  └───────────────────────────────────────────────────────┘

  temporal-ui (web): wired up in docker-compose. Workflow history visible per workflow.
  alembic: one migrations directory under src/codegenie/events/alembic/; `make migrate`.
```

The shape: one Temporal workflow class with thin signal handlers, one Activities module that's a one-thin-wrapper-per-stage list, one checkpointer adapter that delegates to upstream `PostgresSaver`, one typed event-log writer, and one projection module per consumer concern. The load-bearing move is **delegation**: Phase 9 doesn't re-implement durability (Temporal does it), doesn't re-implement checkpointing (LangGraph's `PostgresSaver` does it), and doesn't re-implement event storage primitives (Postgres `INSERT` does it). Every novel line of Phase-9 code is either a wiring line, a typed event variant, or a projection fold.

## Components

### `codegenie.durable.workflows.VulnWorkflow` — the Temporal workflow

- **Purpose.** The deterministic outer envelope for one vuln-remediation workflow. One `@workflow.defn`-decorated class with one `@workflow.run` entrypoint plus signal handlers for HITL pause/resume/cancel. The workflow code itself contains no I/O, no clock reads outside Temporal-provided primitives, no random IDs, no network calls — all of those are activities (per ADR-0003 §Consequences).
- **Public interface.**
  ```python
  @workflow.defn(name="VulnRemediationWorkflow")
  class VulnWorkflow:
      @workflow.run
      async def run(self, config: WorkflowConfig) -> WorkflowResult: ...

      @workflow.signal(name="pause_for_human")
      async def pause_for_human(self, evidence: HumanReviewEvidence) -> None: ...

      @workflow.signal(name="resume_from_human")
      async def resume_from_human(self, decision: HumanReviewDecision) -> None: ...

      @workflow.signal(name="cancel")
      async def cancel(self, reason: CancellationReason) -> None: ...

      @workflow.query(name="state")
      def state(self) -> WorkflowState: ...
  ```
  `WorkflowConfig` and `WorkflowResult` are frozen Pydantic models; `WorkflowState` is a tagged-union sum type per ADR-0033 §3 (`Running | AwaitingHuman | Completed | Failed | Cancelled`).
- **Internal design.**
  - **Determinism rule, enforced.** `import-linter` adds a contract forbidding `codegenie.durable.workflows` from importing `random`, `datetime.now`, `time.time`, `uuid.uuid4`, `requests`, `httpx`, `subprocess`, `socket`, or any module under `codegenie.exec` / `codegenie.transforms` / `codegenie.probes`. The same fence forbids the Phase-2 `run_external_cli` helper from being called from workflow code. Activities (the only legitimate I/O surface) live in a sibling package and are imported only via Temporal's `workflow.execute_activity` API — never imported by symbol into the workflow module.
  - **Retry is framework-level.** Per-activity `RetryPolicy` is declared in `codegenie.durable.activities.retry_policies` as a module-level `Final` table keyed by activity name. The workflow code never sees a retry loop. Per the roadmap exit criterion ("application code contains no retry loops"), `forbidden-patterns` adds `while.*retry|for.*range.*retries|except.*continue` regexes scoped to `codegenie.durable.workflows`.
  - **Signal handlers update state, then the run-loop reacts.** Signal handlers do exactly one thing: update the `WorkflowState` sum-type. The main `run` coroutine uses `workflow.wait_condition(lambda: self._state.kind != "running")` for HITL waits — the Temporal-idiomatic shape from the SDK docs. No polling, no busy-wait, no `asyncio.sleep` inside workflow code.
- **Dependencies.** `temporalio` (≥1.5), the activity stubs (passed by signature, not by import), the `WorkflowConfig` / `WorkflowResult` / `WorkflowState` models from `codegenie.events.payloads`.
- **Where it lives.** `src/codegenie/durable/workflows.py` (one file; the workflow class is small and reading it top-to-bottom should be the workflow). The Phase-6 plugin-local subgraph code is *not* moved into this file — the activity wrappers call into it.
- **Tradeoffs.** Workflow-as-code in Python costs the determinism discipline (per ADR-0003 tradeoff row). The fence-and-linter setup pays for itself the first time a contributor reaches for `time.time()` inside a workflow.

### `codegenie.durable.activities` — typed Activities, one per stage

- **Purpose.** Thin, typed wrappers that turn the existing Phase-3/4/5/6 functions into Temporal Activities. Each activity is a *single-purpose, side-effect-bearing, type-annotated coroutine* with declared timeouts and retry policy.
- **Public interface.** Activities are registered via decorator and a small registry the worker reads at startup:
  ```python
  @register_activity(name="apply_patch", timeout=timedelta(minutes=5))
  @activity.defn(name="apply_patch")
  async def apply_patch(input: ApplyPatchInput) -> ApplyPatchResult:
      """Wraps Phase-3 NpmLockfileRecipeEngine.apply; emits PatchApplied event."""
      ...
  ```
  Inputs and outputs are frozen Pydantic models — no `dict[str, Any]` ever crosses an Activity boundary, per ADR-0033 §1 and the anti-pattern call-out in the design-patterns toolkit ("Untyped `dict[str, Any]` interfaces").
- **Internal design.**
  - **Wrapper, not reimplementation.** Each activity is ~15–25 lines: validate input, call the existing Phase-3/4/5 function, emit a typed event via `record_event(...)`, return a typed result. The Phase-3 `NpmLockfileRecipeEngine`, the Phase-4 RAG retriever, the Phase-5 `SubprocessJail`, and the Phase-6 SHERPA loop are **reused without modification**.
  - **Idempotency by activity name + workflow_id + attempt_id.** Every activity that mutates external state (patch application, PR open, KG write) takes an `AttemptId` and is keyed in its underlying store so a Temporal-driven retry produces no duplicate side effects. This is the only correctness rule beyond "delegate to Phase 3/4/5" — it's what makes Temporal's at-least-once execution safe.
  - **Event emission as a discipline.** Every activity emits exactly one terminal event per outcome (`PatchApplied | PatchFailed`, `GatePassed | GateFailed`, `LlmFallbackInvoked`, etc.). The `record_event` helper is the only legitimate way to write to the canonical event log from activity code, and the helper validates that the event's `workflow_id` matches the activity's context — a typed assertion, not a comment.
- **Dependencies.** `temporalio`, the existing Phase-3/4/5/6 modules (imported normally; activities are ordinary Python code), `codegenie.events`.
- **Where it lives.** `src/codegenie/durable/activities/` — one file per activity (`resolve_plugin.py`, `build_bundle.py`, `apply_patch.py`, `run_sandbox_gate.py`, `plan_with_llm_fallback.py`, ...). Flat layout; no per-stage subpackage. Adding an activity is one new file + one import in `__init__.py` — the same shape as the probe registry.
- **Tradeoffs.** A per-file activity layout means ~8 small files for Phase 9. Worth it: every file reads like one obvious thing, and the test file mirrors the activity file 1:1 (`test_apply_patch.py` tests `apply_patch.py`).

### `codegenie.durable.checkpointer.PostgresCheckpointerAdapter` — LangGraph checkpointer adapter

- **Purpose.** Replace the Phase-6 development-mode checkpointer (`InMemorySaver` / `SqliteSaver`) with a production-grade Postgres-backed checkpointer, per ADR-0016 (Postgres is the default).
- **Public interface.**
  ```python
  class LangGraphCheckpointerPort(Protocol):
      def saver(self) -> BaseCheckpointSaver: ...

  class PostgresCheckpointerAdapter:
      def __init__(self, *, dsn: PostgresDsn, pool: AsyncConnectionPool) -> None: ...
      def saver(self) -> PostgresSaver: ...  # the upstream class, untouched
  ```
- **Internal design.**
  - **We don't write a checkpointer.** `langgraph-checkpoint-postgres` is the upstream-supported package (per the LangGraph docs reference list in ADR-0016 §Evidence). The adapter wraps it and exposes the project's `LangGraphCheckpointerPort` Protocol. This is the Adapter pattern in the toolkit sense: "wrap an incompatible interface to make it match the one your client expects."
  - **One connection pool, shared with the event log.** Phase 9 introduces one `psycopg_pool.AsyncConnectionPool` per worker process; the checkpointer and the event log both consume it. This is the boring Python idiom for managing a Postgres connection pool from async code (per `psycopg` 3 docs).
  - **Migration discipline.** The `PostgresSaver` schema is *upstream-owned* — we never edit it. Our alembic migrations live in `src/codegenie/events/alembic/` and own only the `events` table plus its indices. Mixing the two migrations in one directory is forbidden by a comment-fence at the top of `env.py`.
- **Where it lives.** `src/codegenie/durable/checkpointer.py` (one file). The Phase-6 `VulnRemediationSut` builder learns one new parameter:
  ```python
  def build_vuln_sut(
      ...,
      checkpointer: LangGraphCheckpointerPort | None = None,  # NEW; default = InMemorySaver
  ) -> VulnRemediationSut: ...
  ```
  Default remains the Phase-6 behavior for Phase-6 tests; Phase 9's worker passes a `PostgresCheckpointerAdapter`. This is the surgical-change discipline (`CLAUDE.md` Rule 3): one new parameter, default-preserving, no rewrites.
- **Tradeoffs.** Higher write latency than Redis (per ADR-0016 §Options); accepted because the volume estimate doesn't yet show write-throughput problems, and one database to operate beats two. Migration from Postgres → Redis is a "medium cost" reversibility per ADR-0016 — we don't preemptively pay it.

### `codegenie.events.Event` + `codegenie.events.payloads` — typed events

- **Purpose.** The canonical event model. Every workflow-spanning fact is a typed Pydantic event; the event union is closed and exhaustive per ADR-0033 §3.
- **Public interface.**
  ```python
  EventId       = NewType("EventId", str)           # UUID4 hex
  WorkflowId    = NewType("WorkflowId", str)
  CorrelationId = NewType("CorrelationId", str)
  EventStreamId = NewType("EventStreamId", str)     # for Phase 11 stream-per-projection access patterns

  class _EventBase(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      event_id: EventId
      workflow_id: WorkflowId | None       # None = portfolio-level event
      timestamp: datetime                  # UTC; supplied by activity context
      correlation_id: CorrelationId | None

  class WorkflowStarted(_EventBase):
      kind: Literal["workflow_started"] = "workflow_started"
      config_digest: str
      task_class: TaskClass

  class PatchApplied(_EventBase):
      kind: Literal["patch_applied"] = "patch_applied"
      attempt_id: AttemptId
      patch_digest: str
      engine: Literal["npm_lockfile", "openrewrite"]

  class GateOutcome(_EventBase):
      kind: Literal["gate_outcome"] = "gate_outcome"
      gate: GateId
      decision: Literal["pass", "fail"]
      failing_signals: tuple[SignalKind, ...]

  class HumanReviewRequested(_EventBase):
      kind: Literal["human_review_requested"] = "human_review_requested"
      reason: HumanReviewReason
      evidence_digest: str

  class WorkflowCompleted(_EventBase):
      kind: Literal["workflow_completed"] = "workflow_completed"
      outcome: Literal["merged", "closed", "abandoned"]

  EventPayload = Annotated[
      Union[WorkflowStarted, PatchApplied, GateOutcome, HumanReviewRequested, WorkflowCompleted],
      Field(discriminator="kind"),
  ]
  Event = EventPayload   # public type alias; "Event" reads better at call sites
  ```
- **Internal design.**
  - **`frozen=True, extra="forbid"`.** Per ADR-0010 (Pydantic settings + envelope discipline) and the production design-patterns toolkit ("Smart constructor" + "Make illegal states unrepresentable"). An event mis-spelling a field name is a `ValidationError`, not a silent data loss.
  - **Five variants in Phase 9, not 25.** Phase 9 ships the minimum set the exit criteria require — workflow lifecycle, patch application, gate outcome, human review request, workflow completion. Phase 11 adds `MergeOutcome` and the Stage-7 Learning variants; Phase 13 adds `CostIncurred` variants. Each phase adds variants by *extension*, never by editing the existing five. ADR-0034 §Tradeoffs warns against the "put everything in events" temptation — Phase 9 honors it by starting small.
  - **JSONB on disk; Pydantic in memory.** The Postgres `events` table stores `payload JSONB`; `EventLog.append(event)` serializes via `event.model_dump(mode="json")`; `EventLog.read_workflow(workflow_id)` deserializes via `TypeAdapter(EventPayload).validate_python(row["payload"])`. The discriminator field guarantees the right variant; the validator guarantees the shape. Adding a new variant is one new class — no schema migration on the events table (the `kind` discriminator is inside JSONB).
- **Where it lives.** `src/codegenie/events/payloads.py` (the variants) + `src/codegenie/events/_base.py` (the `_EventBase` + the `EventPayload` union). The split keeps the import graph one-level-deep — projection modules import `from codegenie.events.payloads import PatchApplied, GateOutcome` rather than `from codegenie.events import Event` (more specific is better, per the design-patterns toolkit "small modules with deep interfaces" rule).
- **Tradeoffs.** JSONB instead of a relational schema means we can't easily JOIN on event-payload fields; projections that need cross-event analytics fold the stream in Python instead. ADR-0034 §Tradeoffs accepts this explicitly ("Read patterns can be slower for ad-hoc queries that don't match any projection").

### `codegenie.events.log.EventLog` — append-only Postgres event log

- **Purpose.** The one writer to the canonical `events` table; the one reader for projection input. Append-only; the table has no UPDATE or DELETE codepath in the codebase.
- **Public interface.**
  ```python
  class EventLog:
      def __init__(self, *, pool: AsyncConnectionPool) -> None: ...
      async def append(self, event: EventPayload) -> EventId: ...
      async def append_batch(self, events: Sequence[EventPayload]) -> tuple[EventId, ...]: ...
      async def read_workflow(self, workflow_id: WorkflowId) -> AsyncIterator[EventPayload]: ...
      async def read_all_since(self, watermark: datetime) -> AsyncIterator[EventPayload]: ...
  ```
  `record_event(event: EventPayload) -> None` is a module-level helper that resolves the current `EventLog` via a context-injected handle (a thin `ContextVar` set by the Temporal worker bootstrap; per the design-patterns toolkit, the alternative is "capability passed through ten frames as a parameter" — that's what the `ContextVar` exists to avoid).
- **Internal design.**
  - **`INSERT ... RETURNING id`.** Single statement per append. No event store DSL; no abstraction layer. The DDL is in alembic:
    ```sql
    CREATE TABLE events (
      event_id      UUID PRIMARY KEY,
      workflow_id   TEXT,
      kind          TEXT NOT NULL,
      timestamp     TIMESTAMPTZ NOT NULL,
      correlation_id TEXT,
      payload       JSONB NOT NULL
    );
    CREATE INDEX events_workflow_id_idx ON events (workflow_id, timestamp);
    CREATE INDEX events_kind_idx ON events (kind, timestamp);
    ```
  - **No `UPDATE`, no `DELETE`.** A `forbidden-patterns` pre-commit rule (scoped to `codegenie.events.log`) bans the substrings `UPDATE events`, `DELETE FROM events`, and `TRUNCATE events`. ADR-0034 §Decision frames the event log as "append-only by definition" — the project's existing pre-commit firewall is the right enforcement layer.
  - **Determinism boundary.** Workflow code never imports `EventLog` — only activities do (the `record_event` helper resolves to a no-op when called outside an Activity context, and logs a `WARNING`). This is the same boundary ADR-0003 §Consequences draws around side effects.
- **Where it lives.** `src/codegenie/events/log.py` (one file, ~120 lines including type stubs).
- **Tradeoffs.** A single events table for the whole installation means partitioning becomes a real concern at portfolio scale (Phase 10+). ADR-0034 §Tradeoffs acknowledges "Storage cost grows with retention window; eventually need snapshots for long-running workflows (out of scope for v1)." The Phase-9 implementation ships a monolithic table; a future ADR amendment introduces partitioning if and when volume forces it.

### `codegenie.events.projections` — projection registry + replay

- **Purpose.** The contract every consumer of the event stream implements. Each projection is a pure fold; the registry is the standard `@register_*` decorator pattern from the codebase's existing seams.
- **Public interface.**
  ```python
  class Projection(Protocol):
      name: ProjectionId
      def fold(self, events: Sequence[EventPayload]) -> ProjectionState: ...

  _REGISTRY: Final[dict[ProjectionId, Projection]] = {}

  def register_projection(name: ProjectionId) -> Callable[[type[Projection]], type[Projection]]:
      """Decorator. Registers the projection class. Idempotent — re-registration is a TypeError."""
      ...

  async def replay(projection_id: ProjectionId, *, log: EventLog,
                   workflow_id: WorkflowId | None = None) -> ProjectionState: ...
  ```
- **Internal design.**
  - **The two Phase-9 projections.** Phase 9 ships exactly two projection modules and one shim:
    - `codegenie.events.projections.audit_trail` — given a `workflow_id`, returns the chronological event list (the trivial projection — pays its rent by validating the replay machinery).
    - `codegenie.events.projections.retry_histogram` — folds `GateOutcome` events by `gate × failing_signals` to surface the retry-cause histogram ADR-0034 §Projections names.
    - `codegenie.events.projections.cost_ledger_v1` — a Phase-9 *stub* that consumes a `CostIncurred` event variant Phase 13 will add. The stub registers the projection but leaves the fold body as `NotImplementedError("see Phase 13")` — this exists so Phase 13 lands as a single-file addition rather than a cross-cutting wiring change.
  - **One projection per file.** Same shape as activities and probes: adding a projection is one new module + one import in `codegenie.events.projections.__init__`. ADR-0034 §Consequences says "Phase 11 (Learning) and Phase 13 (cost ledger + ROI dashboard) become projections rather than independent stores"; Phase 9's job is to make that single-file addition possible.
  - **Idempotence.** Each projection's `fold` must produce the same `ProjectionState` for the same input event sequence. A property test asserts this on a fixture stream of 200 events shuffled in 50 orderings (the order of events in the *log* is fixed, but the property catches accidental mutable state inside a projection).
- **Where it lives.** `src/codegenie/events/projections/` — `__init__.py` (registry + `replay`), `audit_trail.py`, `retry_histogram.py`, `cost_ledger_v1.py` (stub).
- **Tradeoffs.** A projection that needs cross-projection data (e.g., ROI = `cost_ledger / merge_count`) has to consume the event log directly rather than calling another projection — projection-on-projection composition is explicitly out of scope (it's the path to a feature factory). When Phase 13 needs ROI, it folds the event log once and computes ROI internally; this matches the ADR-0034 §Decision framing of projections as derived materializations.

### `codegenie.durable.bridge` — LangGraph ↔ Temporal adapter

- **Purpose.** The one place that turns the Phase-6 `VulnRemediationSut` (a Protocol with `run_case(...) -> VulnRemediationResult` and `digest() -> SutDigest`) into a sequence of Temporal Activity calls.
- **Public interface.** A single function:
  ```python
  async def run_via_temporal(case: VulnRemediationCase, *,
                             worker_handle: WorkerHandle) -> VulnRemediationResult:
      """Phase-9 alternative to Phase-6's in-process VulnRemediationSut.run_case."""
      ...
  ```
  The Phase-6 `VulnRemediationSut.run_case` continues to work unchanged for Phase-6 tests and the Phase-6 dev mode; Phase 9 introduces this *new* function and a `TemporalVulnRemediationSut` adapter that implements the Phase-6 Protocol by calling `run_via_temporal`. Phase 6.5's harness sees the same Protocol; the durability transition is invisible to it.
- **Internal design.**
  - **One bridge, one direction.** The Supervisor-as-LangGraph (Phase 8) maps node-for-node to Activities. Phase 9 doesn't reuse the LangGraph compilation at runtime — the Activities are called from the Temporal workflow directly, in the same order the Phase-8 graph executed them. The LangGraph compilation is kept for Phase-6 / Phase-8 dev-mode runs; Phase 9 is the production path.
  - **Why not run the LangGraph inside the workflow?** Determinism: LangGraph's compiled graph contains references to closures, dict iteration, and node-name lookups that can re-order between Python versions. Temporal's determinism contract forbids that. The Phase-8 graph was deliberately shaped to be node-for-node mappable for exactly this reason — Phase 8's design-of-record names it "the Phase-9 Temporal-Activity seam."
- **Where it lives.** `src/codegenie/durable/bridge.py` (one small file). The Phase-6 `VulnRemediationSut` Protocol is untouched.
- **Tradeoffs.** Keeping two execution paths (Phase-6 LangGraph dev-mode + Phase-9 Temporal production-mode) doubles the surface to test. Mitigated by the Phase-6 `VulnRemediationSut` Protocol being the contract — both paths produce the same `VulnRemediationResult` and the same `SutDigest`, and Phase 6.5's harness fixture exercises both paths against the same test cases.

### alembic migrations directory + discipline

- `src/codegenie/events/alembic/` — owns the `events` table DDL and any future Phase-9-owned tables. **Does not** own the `PostgresSaver` schema (upstream-managed) or the Temporal schema (Temporal-managed).
- One migration per Pydantic-event-table change (Phase 9 ships exactly one initial migration: `0001_create_events_table.py`).
- `make migrate` runs `alembic upgrade head` against the configured DSN; `make migrate-create` scaffolds a new migration. Both are mechanical, no LLM, no clever inspection.
- `env.py` reads `pyproject.toml` (per the project's existing config-loading idiom) — never a stray `.ini` file.

### docker-compose + local dev surface

`docker-compose.yml` (project root) gains three services:

```yaml
postgres:
  image: postgres:16-alpine
  environment: { POSTGRES_PASSWORD: dev, POSTGRES_DB: codegenie }
  ports: ["5432:5432"]
  volumes: ["pgdata:/var/lib/postgresql/data"]

temporal:
  image: temporalio/auto-setup:1.25
  environment: { DB: postgres12, POSTGRES_SEEDS: postgres, ... }
  depends_on: [postgres]

temporal-ui:
  image: temporalio/ui:2.30
  ports: ["8080:8080"]
  environment: { TEMPORAL_ADDRESS: temporal:7233 }
  depends_on: [temporal]
```

A `make dev-up` target starts the three services and runs the worker (`python -m codegenie.durable.workers`). A `make dev-down` cleans up. Per `CLAUDE.md`'s convention list, the Makefile remains the imperative surface; the new targets follow the existing pattern.

## Data flow

A successful workflow:

1. CLI / webhook calls `temporalio.client.start_workflow("VulnRemediationWorkflow", config, id=workflow_id)`.
2. Temporal schedules the workflow on a worker; `VulnWorkflow.run(config)` begins.
3. Workflow calls `execute_activity("resolve_plugin", ...)`. The activity wraps `codegenie.plugins.resolver.resolve(...)`, emits a `PluginResolved` event (which lives in the existing `codegenie.plugins.events` log in Phase 8, and is *also* mirrored into the canonical `events` table in Phase 9 — the migration ADR records the cutover date).
4. Workflow calls `execute_activity("build_bundle", ...)`. The activity wraps `codegenie.plugins.BundleBuilder.build(...)`, emits a `BundleBuilt` event.
5. Workflow enters the recipe→RAG→LLM ladder (one activity per tier). Each activity emits its outcome event; the LLM-fallback activity emits a `LlmFallbackInvoked` event with token counts (Phase 13 cost projection consumes these).
6. Workflow calls `execute_activity("apply_patch", ...)` → `apply_patch` runs the Phase-3 `NpmLockfileRecipeEngine`, emits `PatchApplied`.
7. Workflow calls `execute_activity("run_sandbox_gate", ...)` → emits `GateOutcome(decision=pass|fail)`.
8. On `pass`: workflow emits `WorkflowCompleted(outcome=...)` and exits. On `fail`: Temporal's per-activity retry policy fires (no application-level retry loop); on retry-budget exhaustion, workflow signals `HumanReviewRequested` and parks on `workflow.wait_condition` until a `resume_from_human` signal arrives. The Phase-6 typed HITL discriminated union (`AwaitingHumanReview` state) carries the resumption contract — Phase 9 preserves that contract via the signal payload type.

Throughout, the LangGraph checkpointer (now `PostgresSaver`) writes per-semantic-boundary state. Worker kill → restart → Temporal replays the workflow from history; the checkpointer rehydrates the in-activity LangGraph state. No state is lost. The `WorkflowResumed` event records the resumption; the `retry_histogram` projection surfaces "this workflow resumed N times from activity X."

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| Worker process killed mid-activity | Temporal heartbeat timeout | Workflow rescheduled on another worker; activity re-runs from input (idempotent by `attempt_id`) |
| Postgres connection failure during event-log write | `psycopg.OperationalError` in `EventLog.append` | Activity's retry policy fires (capped at 3 by default — events are observability, not load-bearing). On budget exhaustion, the activity raises a typed `EventLogUnavailableError` and the workflow surfaces it via `HumanReviewRequested` rather than silently dropping the event. Per `CLAUDE.md` Rule 12 — fail loud. |
| Checkpointer write failure | `psycopg.OperationalError` propagating from `PostgresSaver` | LangGraph re-raises; Temporal retries the activity; recovery is identical to "any activity failure". The activity raises `CheckpointerUnavailableError` (typed; not bare `Exception`) when retries exhausted. |
| Non-determinism bug in workflow code | Temporal replay-validation in `WorkflowEnvironment` | CI runs the workflow under `WorkflowEnvironment.replay_existing_workflow(history)` against recorded fixtures; non-determinism is a test failure, not a production incident. (Per ADR-0034 §Replay — "Replay is also a test primitive.") |
| Signal received before workflow started | Temporal SDK | Temporal queues the signal; workflow's signal handler runs after `run` begins. No application code needed. |
| Event written with wrong `workflow_id` | `record_event` helper's runtime assertion | `EventLogContextMismatch` exception; activity fails loud rather than corrupting the audit trail. |
| `events` table grows unbounded | Operational monitoring (out of scope for code) | Documented in the README under "Operational concerns"; ADR-0034 §Tradeoffs flags partitioning as a future ADR. Phase 9 does not pre-build retention machinery. |
| Two activities of the same name registered | `register_activity` idempotency check | `TypeError` at worker startup. (Same shape as `@register_probe` and `@register_index_freshness_check`.) |

Every failure mode above maps to a typed exception class defined in `codegenie.durable.errors` (`WorkflowError`, `ActivityError`, `CheckpointerUnavailableError`, `EventLogUnavailableError`, `EventLogContextMismatch`, `NonDeterminismDetected`). No bare `Exception` ever escapes a Phase-9 module's public surface.

## Resource & cost profile

- **Postgres footprint.** One database, three logical schemas (Temporal, LangGraph, codewizard-sherpa events). For a Phase-9 dev workload (≤100 workflows/day, ~20 events/workflow), the `events` table grows ~2000 rows/day — under 1 GB/year with JSONB compression. Production sizing is a Phase-13 concern (ROI dashboard will surface it).
- **Temporal footprint.** One server pod + one worker pod is the dev shape (`temporal server start-dev`); ADR-0003 §Consequences names 3+5 as the production starting size. Phase 9 ships the dev shape; production deployment is out of scope.
- **Convention cost.** The "one activity per file" rule costs ~8 small files vs. ~2 larger ones. Worth it for grep-ability and per-file test mirroring.
- **Determinism enforcement cost.** The `import-linter` contract + the `forbidden-patterns` rule add ~30s to CI. Worth it; non-determinism bugs in workflow code are the kind that ship to production and cause silent state loss.
- **What we *save*.** No retry-loop code in the application. ADR-0003 quantifies this as "rebuild ~70% of Temporal, poorly" — the savings are framework-level retry, signal handling, replay, and durability that we'd otherwise write ourselves.

## Test plan

- **Unit tests.** One test file per module; mirror the source layout. Activity-level unit tests mock the wrapped Phase-3/4/5 function and assert (a) the typed event is emitted, (b) the typed input/output round-trips through Pydantic, (c) the activity is idempotent in `attempt_id`. Coverage gate: ≥ 90% line per new package.
- **Property tests** (`hypothesis`). Event payload round-trip: generate a `EventPayload` instance for every variant, assert `TypeAdapter(EventPayload).validate_python(json.loads(json.dumps(event.model_dump(mode='json')))) == event`. Projection idempotence: for each registered projection, generate a list of events, shuffle order N times *within their `timestamp`-equal groupings* (events at different timestamps have a defined order), assert the fold is identical. (Per `CLAUDE.md` Rule 9 — tests verify intent, not just behavior.)
- **Workflow tests** (`temporalio.testing.WorkflowEnvironment`). Run `VulnWorkflow` in-process against mocked activities; assert state transitions match the Phase-6 sum type. The Phase-6 `VulnRemediationSut` Protocol's existing test cases re-run under both Phase-6 in-process mode and Phase-9 Temporal-bridge mode; same outcomes assertion.
- **Integration tests** (`testcontainers-python`). One test that boots Postgres in a container, runs alembic migrations, exercises `EventLog.append` + `EventLog.read_workflow` + `replay("audit_trail", workflow_id=...)`. One test that boots Temporal's local dev server (via `temporalio.testing.WorkflowEnvironment.start_local()`) plus Postgres, runs one full workflow end-to-end, asserts a `WorkflowCompleted` event appears in the `events` table.
- **E2E (minimal).** One test that runs `python -m codegenie.durable.workers` in a subprocess against the docker-compose dev environment, triggers a workflow via the CLI, kills the worker mid-`apply_patch`, restarts the worker, asserts the workflow completes to `WorkflowCompleted`. This is the **durability test** the roadmap calls out. Lives under `tests/e2e/test_temporal_durability.py`, marked `@pytest.mark.e2e` (excluded from `make test` by default; run via `make test-e2e`).
- **Golden files for projection outputs.** `tests/projections/fixtures/sample_workflow_events.json` (a recorded event stream); `tests/projections/test_audit_trail_golden.py` asserts the audit-trail projection produces a byte-identical rendered output; same shape for `retry_histogram`. Golden file updates are PR-reviewable diffs.
- **Replay-determinism invariant.** `tests/workflows/test_replay_determinism.py` records a workflow's history once via `WorkflowEnvironment`, then re-runs the workflow code against the recorded history via `Worker.run_replay_workflows(...)` (the Temporal SDK's replay-testing API). Any non-determinism between Python versions or imports is caught here. (Per ADR-0034 §Replay.)
- **Mutation testing (one-shot, not CI-gated).** A `make mutate` target runs `mutmut` against `codegenie.events.payloads`, `codegenie.events.log`, and `codegenie.durable.activities.apply_patch` — three modules where weak tests would be silently catastrophic. Tracked as a backlog item in the roadmap, not a Phase-9 release gate.

## Design patterns applied

The toolkit's calibrated range is 3–6 explicit pattern decisions per design. Phase 9 has six.

1. **Adapter pattern.** `PostgresCheckpointerAdapter` wraps `langgraph_checkpoint_postgres.PostgresSaver` to expose the project's `LangGraphCheckpointerPort` Protocol. The Adapter pattern is exactly the right shape here ("wrap an incompatible interface to make it match the one your client expects") — we don't fork the upstream class, we don't subclass it, we wrap it. The Phase-6 `VulnRemediationSut` builder consumes the Port, not the concrete class.
2. **Functional core / imperative shell.** Every activity has a pure-functional core (`apply_patch_pure(repo_snapshot, plan) -> PatchResult`) plus a thin imperative wrapper that calls `record_event(...)` and writes to disk. Projections are pure folds over event sequences. The Temporal workflow is the imperative shell that schedules activities. Reason: this is the test seam — projections are tested with fixture event streams; activity cores are tested without Temporal. Per the design-patterns toolkit, "scoring rubrics, BCa bootstrap, decision-classification logic, slice-merging, planning — anywhere 'given inputs, compute outputs deterministically' is the requirement" — projections are exactly this shape.
3. **Tagged union / sum type for state.** `WorkflowState = Running | AwaitingHuman | Completed | Failed | Cancelled`. `EventPayload = WorkflowStarted | PatchApplied | GateOutcome | HumanReviewRequested | WorkflowCompleted` (extensible by addition). `match` + `assert_never` everywhere. Reason: the Phase-6 design-of-record already uses the same discipline (`NeedsPlan | PlanReady | PatchApplied | ...`) — Phase 9 mirrors it. Per ADR-0033 §3 — "Domains to model as sum types: ... `AttemptResult`, `EvalVerdict`, `ProbeOutcome`. Anything that's currently a `str` enum, `bool` flag, or `Optional[X]` that 'really represents' a discriminated choice."
4. **Newtype pattern.** Every domain identifier in Phase 9 (`WorkflowId`, `ActivityId`, `EventId`, `EventStreamId`, `ProjectionId`, `CorrelationId`, `MigrationVersion`) is a `NewType` per ADR-0033 §1. Reason: per the toolkit, "swapping a `RepoId` for a `PRNumber` because both are `str`. Type checker can't help. Newtypes make this a compile-time error." The workflow code threads four IDs simultaneously; this is the kind of code where ID confusion silently corrupts production data.
5. **Registry pattern.** `@register_activity(name)` for activities; `@register_projection(name)` for projections. Both follow the existing `@register_probe` shape from `codegenie.probes.registry` — same mental model, same test shape, same anti-shenanigans rule ("the registry is a dict; the decorator is `def register(name): def wrap(cls): registry[name] = cls; return cls; return wrap`. Stay that simple."). Reason: the project's established Open/Closed seam — same pattern, same enforcement.
6. **Event sourcing for agent runs.** The Postgres `events` table is the canonical append-only side-channel; Temporal workflow history is the workflow-internal store; projections fold both. Reason: ADR-0034 §Decision mandates exactly this hybrid. The toolkit's "Failure mode: event sourcing for state that doesn't need replayability — CRUD is fine if CRUD is what you need" rule was already evaluated by ADR-0034 §Tradeoffs, which observes that 6+ downstream concerns *do* need replayability (cost ledger, ROI, learning, audit, plugin telemetry, trust-gate observability) — so the cohesion case wins.

## Patterns deliberately avoided

- **Strategy pattern for "checkpointer backend."** ADR-0016 explicitly defers Redis-vs-Postgres; Phase 9 picks Postgres and ships exactly one implementation. A `Strategy` interface with a single concrete class is premature pluggability (toolkit anti-pattern). The Port (`LangGraphCheckpointerPort`) exists for the Adapter pattern, not for runtime swapping — one implementation, one production-mode adapter.
- **Command pattern for every workflow action.** The toolkit calls out "Command for trivial in-process function calls. Reserve for things that need audit, retry, or replay." Temporal already provides audit (workflow history), retry (per-activity policies), and replay (the SDK's replay API). Wrapping activities in a homegrown `Command` object is ceremony on top of Temporal's existing primitives.
- **Specification pattern for workflow predicates.** The Phase-6 SHERPA loop's terminal-state predicates (`is_completed`, `is_paused`, ...) are already encoded as sum-type variants. A `Specification` layer is unnecessary; pattern matching does the same job in one less abstraction.
- **Hexagonal architecture as a Phase-9 introduction.** The project's existing seams (`ProbeContext`, `LeafLlmPort`, `SubprocessJail`) are already hexagonal in shape; Phase 9 doesn't formalize a new "hexagonal layer" on top. The Adapter pattern application above is the right granular use of hexagonal thinking; renaming `codegenie.durable` to `codegenie.hex.durable` would be ceremony.
- **Event store abstraction layer.** The toolkit's anti-pattern list includes "Untyped `dict[str, Any]` interfaces"; an event store abstraction would either be that (defeating the discriminated-union discipline) or a generics nightmare (defeating the next-engineer-reads-it-cold goal). We use Postgres directly; the day a non-Postgres event store is required is the day we write a second implementation, never before.

## Risks (top 3–5)

1. **Determinism leak from `ContextVar` event sink.** The `record_event` helper relies on a `ContextVar` populated by the activity bootstrap. If a future change accidentally calls `record_event` from inside workflow code, Temporal's determinism check may not flag it (the helper would no-op cleanly). Mitigation: the `import-linter` contract forbids `codegenie.events.log` from being imported by `codegenie.durable.workflows`; a `tests/fence/test_workflow_determinism.py` AST-walks the workflow file and asserts no `record_event` call. Severity: high (silent failure); likelihood: low (the fence is mechanical).
2. **`PostgresSaver` upstream churn.** `langgraph-checkpoint-postgres` is a relatively young package; an upstream schema change between Phase 9 and Phase 10 would require a migration on Phase-6 in-flight workflows. Mitigation: pin the version in `pyproject.toml`; track upstream release notes in the dependency-update workflow; ADR-0016 §Reversibility already names this as a "medium cost" reversibility concern.
3. **JSONB schema drift across event variants.** Adding a new event variant is non-breaking; renaming or removing a field is breaking. The discipline ADR-0034 §Consequences names ("Schema evolution discipline required") is currently a comment, not enforced code. Mitigation: a `tests/fence/test_event_schema_stability.py` snapshots the JSONSchema for every registered event variant and fails CI on any change that isn't accompanied by a migration note in the test fixture directory. Phase 9 ships this fence.
4. **`events` table partitioning becomes load-bearing at portfolio scale.** Phase 9 ships a monolithic table; once Phase 14 makes gather continuous, write volume grows ~50×. Mitigation: documented as an open question for Phase 14; not pre-built in Phase 9 (YAGNI per the toolkit). The fold-based projection contract is partitioning-friendly when the time comes.
5. **Replay determinism is asserted via tests, not enforced at runtime.** Temporal's own replay validation catches some non-determinism, but Python version drift can introduce subtle ordering changes (set iteration order across CPython versions, for example — though guaranteed since 3.7). Mitigation: the workflow code uses sorted iteration explicitly; the determinism fence forbids `set()` literals and bare `dict.items()` iteration inside workflow code. Per the design-patterns toolkit anti-pattern "Side effects in constructors / module import time" — extended here to "implicit-order iteration in deterministic code."

## Acknowledged blind spots

- **Production Temporal cluster sizing.** ADR-0003 names 3 server pods + 5–10 worker pods; this design doesn't compute the right Phase-9 size for the project's actual workflow volume because Phase 9's volume is dev-shaped (≤100 workflows/day). The performance lens or Phase-10 design should revisit.
- **Multi-tenant event log.** ADR-0034 doesn't name multi-tenancy as a concern; this design assumes one installation = one `events` table. If the production deployment serves multiple orgs from one Temporal cluster, partitioning by `org_id` becomes load-bearing earlier.
- **Cost of LangGraph + Temporal both in the runtime.** ADR-0003 names "operational complexity" as a tradeoff; we now pay it twice (LangGraph for in-process dev mode + Phase-6 tests; Temporal for production). The performance lens may surface this as a fork-the-paths concern — the security lens may surface it as an attack-surface concern.
- **The Phase-8 hash-chained `codegenie.plugins.events` log vs. the new canonical events table.** ADR-0034 §Consequences says "Phases 0–8 use ad-hoc append-only structures where they need them ... no retroactive disruption." Phase 9 begins the migration, but the cutover details (do both logs run in parallel for N days? Does the migration backfill or freeze old data?) are not specified here. Synthesizer should resolve.
- **`MigrationVersion` semantics across Temporal + LangGraph + events.** Three independently-versioned schemas live in the same database. The interaction between Temporal's own schema migrations, LangGraph's `PostgresSaver` migrations, and our `events` migrations isn't specified — one schema's upgrade window could break another. Pre-existing project convention isn't clear; needs a synthesis decision.

## Open questions for the synthesizer

1. **Cutover policy for the existing `codegenie.plugins.events` hash-chained log.** Phase 8 ships a hash-chained append-only log; Phase 9 introduces the canonical Postgres event log. Do both run in parallel for the duration of Phase 9, with Phase 10 freezing the old log? Or does Phase 9 backfill the old log into the new one and decommission it immediately? My design assumes parallel for Phase 9 only — synth should pick a side and update the test plan.
2. **Default checkpointer for `VulnRemediationSut.build()` in Phase 9+.** I kept the Phase-6 default (`InMemorySaver`) for backward compatibility. Should the default flip to `PostgresCheckpointerAdapter` as soon as Phase 9 ships? Performance/security lenses may have opinions; I lean "no — keep the default as InMemory and require explicit opt-in to Postgres for production" because the Phase-6 tests are the canonical reference.
3. **Activity name conventions vs. existing decorator names.** `@register_activity(name="apply_patch")` collides naturally with `@activity.defn(name="apply_patch")`. Should we drop our `@register_activity` and use Temporal's `@activity.defn` registration directly? My design keeps both because the project's `@register_*` pattern is load-bearing convention (`@register_probe`, `@register_dep_graph_strategy`, `@register_index_freshness_check`). Synth should rule on whether the convention earns its rent here or whether the SDK's own registration is sufficient.
4. **Should `record_event` be a callable, a `ContextVar`, or a Pydantic dependency injection?** I chose `ContextVar` per the design-patterns toolkit's "Capability pattern" framing. The performance lens may prefer a direct callable threaded through every activity signature; the security lens may prefer an explicit capability token.
5. **Should the durability test (kill-worker-mid-activity) be `@pytest.mark.e2e` or `@pytest.mark.durability`?** I picked `e2e` because it requires the docker-compose stack. The project already uses `bench`, `adv`, `phase02_adv`. A new `durability` marker may be cleaner. Synth should pick.
6. **Phase 11 / Phase 13 projection stub policy.** I ship a `cost_ledger_v1` stub in Phase 9 to make Phase 13 a single-file addition. Should Phase 9 also ship stubs for `learning_kg_writeback` (Phase 11) and `roi_dashboard_v1` (Phase 13)? My instinct says no — speculative stubs are speculative pluggability. But ADR-0034 §Consequences names these explicitly, so synthesizer may have a different read.
