# Phase 09 — Durable workflow envelope: Temporal: Performance-first design

**Lens:** Performance — throughput, latency, token economy, footprint.
**Designed by:** Performance-first design subagent
**Date:** 2026-05-23

## Lens summary

I optimized for **portfolio-scale workflow throughput** and **per-PR token economy** above all. Concretely: keep the Temporal/Postgres substrate from becoming the throughput ceiling that Phase 8's `<50ms p95` hot path implicitly assumed, make the workflow-internal history *cheap to read and cheaper to skip*, drive the Postgres side-channel event log at append rates that scale with workflow concurrency (not gate-transition concurrency), and preserve every cache (Phase 1 content cache, Phase 8 Redis hot views, Phase 4 cassettes) byte-identical across the wrap so a workflow that was warm before Temporal stays warm after Temporal. I explicitly deprioritized: (a) operator ergonomics of `temporal start-dev` (it can be slow to boot — that's a once-per-dev cost, not a per-workflow cost); (b) Postgres operability features that don't move workflows/hour (PITR, fine-grained RLS — defer to Phase 16); (c) cosmetic temporal-ui niceties beyond what proves durability. The bias throughout is **cache > deterministic projection > Activity invocation > LLM call**, and the bias on *where* code runs is **pure-function workflow body > thin Activity > heavy Activity > side-effecting Activity**.

## Goals (concrete, measurable)

- **Workflows/hour target.** Per worker (1 vCPU, 1 GiB): **≥ 60 workflows/hour** of cassette-replay vuln-remediation (warm gather, recipe-route, no human pause). Per pool (5 workers): **≥ 250/hour** sustained, ≥ 400/hour burst for 5 minutes.
- **Time-to-PR p95.** **≤ 8 minutes** wall-clock for a recipe-route workflow on a warm-gather repo (excluding the Stage-5 sandbox build, which dominates and is unchanged); **≤ 18 minutes** p95 for a RAG-route workflow; LLM-route bounded by Phase 4's per-tier caps, not Phase 9.
- **$/PR target.** **No regression** vs. Phase 8: recipe-route `$0.00`, RAG-route `≤ $0.02`, LLM-route `≤ $0.40`. Temporal must not introduce any LLM call. Workflow-history fetches on resume are free (Temporal-internal).
- **Cache hit rate target.** **≥ 95%** on Phase 8 hot views in steady state (no regression from Phase 8); **≥ 90%** Activity-result memoization hit rate on idempotent activities (resolver, BundleBuilder, hot-view read) when the same workflow replays; **100%** for cassette-replay tests.
- **Per-worker memory ceiling.** **≤ 512 MiB RSS** steady-state with 50 in-flight workflows (cooperative async, not threads). Workflow-state heap per workflow **≤ 64 KiB** at every checkpoint (small typed states, no embedded repo bytes).
- **Workflow-history fetch latency target.** Resume after process kill: **≤ 500ms p95** from `temporal worker start` to first Activity dispatched (Temporal history page fetch + replay). Cold-replay of a 200-event history: **≤ 1.5s p95**.
- **Event-log append throughput target.** Postgres side-channel `events` table: **≥ 5,000 appends/sec** sustained from a single worker pool with batched flush; p95 commit latency **≤ 8ms** for a 4 KiB event; projection-lag (events → cost-ledger materialized view) **≤ 200ms p95** under sustained load.

## Architecture

```
                  ┌──────────────────────────────────────────────────────────────────┐
                  │                  TEMPORAL CLUSTER (local: start-dev)              │
                  │   ┌─────────────────┐    ┌────────────────────────────────────┐   │
                  │   │ Frontend / Hist │◄──►│ Workflow History (sharded per WF)  │   │
                  │   └────────┬────────┘    └────────────────────────────────────┘   │
                  │            │                       ▲                              │
                  │            │  task queues          │ replay (cheap, paged)        │
                  └────────────┼───────────────────────┼──────────────────────────────┘
                               │                       │
                ┌──────────────┴──┐         ┌──────────┴──────────────┐
                │ WORKER POOL "wf"│         │  WORKER POOL "activity" │
                │ (workflow-only) │         │  (sticky, language=py)  │
                │ pure code, no IO│         │  IO + LLM + sandbox     │
                │ tiny state, fast│         │  4 task queues by class │
                │ replay          │         │   - probe-quick         │
                │                 │         │   - llm-call            │
                │                 │         │   - sandbox-heavy       │
                │                 │         │   - postgres-write      │
                └────────┬────────┘         └──────────┬──────────────┘
                         │                              │
                         │  invokes Activities          │ reads/writes
                         │  (no shared memory)          │
                         ▼                              ▼
            ┌─────────────────────────────┐   ┌──────────────────────────────┐
            │  LangGraph subgraphs        │   │  POSTGRES 16  (docker-compose)│
            │  Phase 6 SHERPA loop        │   │  ┌─────────────────────────┐  │
            │  Phase 8 Supervisor graph   │   │  │ temporal_visibility     │  │
            │  (each step = Activity)     │   │  ├─────────────────────────┤  │
            │  WORKFLOW BODY is pure;     │   │  │ langgraph_checkpoints   │  │
            │  LangGraph compiled state   │   │  │  (PostgresSaver)        │  │
            │  is the typed Activity arg  │   │  ├─────────────────────────┤  │
            └──────────────┬──────────────┘   │  │ events (side-channel)   │  │
                           │                  │  │  PARTITION BY range(ts) │  │
                           │ append-only      │  │  GIN(workflow_id)       │  │
                           ▼                  │  ├─────────────────────────┤  │
            ┌─────────────────────────────┐   │  │ projections.*           │  │
            │  EventLog (Pydantic envelope│──►│  │  cost_ledger_mv         │  │
            │  per ADR-0033/0034)         │   │  │  trust_gate_history_mv  │  │
            │  batched async writer       │   │  │  plugin_telemetry_mv    │  │
            │  COPY-binary fast-path      │   │  │  (REFRESH CONCURRENTLY) │  │
            └─────────────────────────────┘   │  └─────────────────────────┘  │
                                              └──────────────────────────────┘
                                              ▲
                                              │ unchanged: hot-view writer  ┌─────────┐
                                              └─────────────────────────────┤  REDIS  │
                                                                            │ ph-8 cache│
                                                                            └─────────┘
```

Key shape choices:
- **Two worker pools** (workflow vs. activity), because Temporal workflow workers replay history and must be CPU-cheap and IO-free; activity workers do the heavy work. Conflating them is the #1 way to wreck workflow scheduling latency.
- **Four task queues on the activity pool** so we can size and rate-limit independently — sandbox builds (slow, IO-bound) cannot starve LLM tokens (slow, rate-limited externally) and neither can starve quick probe activities (fast, cheap, the warm hot-path).
- **Postgres is the one durable store**: Temporal cluster metadata + LangGraph checkpointer + side-channel event log all share one Postgres 16 instance in dev; production splits them by schema and gives Temporal its own physical instance. One database to operate in dev is a *performance* property: shared buffer cache, no cross-DB joins, one set of tunables.
- **Redis hot views are untouched.** Phase 8's `<50ms p95` `HotViewStore.get_all` survives unchanged; Temporal does not move it to Postgres.

## Components

### Workflow definitions — `codegenie.temporal.workflows`

- **Purpose.** One Temporal workflow per per-repo migration. The workflow body is the Phase 6 SHERPA state machine *as code* — each LangGraph node becomes an Activity invocation. Phase 8's Supervisor is a separate, smaller "parent workflow" that owns `MultiPluginDispatch` and signals into child workflows.
- **Interface.**
  ```python
  @workflow.defn(sandboxed=True)
  class VulnRemediationWorkflow:
      @workflow.run
      async def run(self, request: VulnRemediationRequest) -> VulnRemediationResult: ...

      @workflow.signal
      def human_review_decision(self, decision: HumanReviewDecision) -> None: ...

      @workflow.query
      def current_phase(self) -> LedgerState: ...

      @workflow.update
      async def cancel_for_budget_breach(self, reason: str) -> None: ...
  ```
- **Internal design.**
  - **Workflow body is a pure orchestration loop** over the Phase 6 `VulnLedger` sum type. The body calls Activities; it never imports `httpx`, `redis`, `subprocess`, or any LLM SDK (enforced by `import-linter` — extends the existing fence with a `codegenie.temporal.workflows` source set).
  - **State is tiny.** The workflow's local state is the current `VulnLedger` variant + a few `WorkflowId`/`RepoId` newtypes. ContextBundle, raw LLM responses, sandbox logs are never embedded in workflow state — they live in Postgres event payloads or the existing artifact stores, referenced by digest. This is what keeps history small and replay cheap (target: 64 KiB heap at every checkpoint).
  - **Replay determinism is exploited, not endured.** Workflow code uses `workflow.now()`, `workflow.uuid4()`, `workflow.deterministic_random()`. Side-effects go through Activities. Phase 4's cassette-replay determinism property (`tests/property/test_determinism_under_cassette_replay.py`) is *strengthened* in Phase 9 to assert byte-identity across `temporal kill && temporal start && resume`.
  - **No retry loops in workflow code.** Activities have `RetryPolicy` (initial_interval=1s, backoff=2.0, max_attempts=3, non_retryable=`[BudgetExhausted, SchemaValidationError]`). Application-side retry loops are forbidden by an AST-walking fence test (`tests/fence/test_no_workflow_retry_loops.py`).
- **Tradeoffs accepted.** The "Phase 6 graph as workflow body" composition means every LangGraph node is *also* a Temporal Activity boundary — two framework layers. This is paid for with: (1) Phase 8's existing thin three-node Supervisor graph means few hops; (2) the workflow body holds no LangGraph runtime — it just calls `await workflow.execute_activity(run_supervisor_resolve, ...)`. The LangGraph compiled graph lives in the *activity* worker, hydrated from the typed bundle.

### Activity workers — `codegenie.temporal.activities`

- **Purpose.** Where the real work happens: probes, BundleBuilder, hot-view read, planner routing, recipe apply, sandbox run, LLM call, PR open. Each is a single async function with a typed Pydantic input + output.
- **Pool sizing (initial, tuned by load test in S9-XX).**
  - **`probe-quick` queue:** `max_concurrent_activities=64`, no rate limit. Targets: warm BundleBuilder, hot-view read, planner-route — all <100ms. One async worker process; cooperative concurrency.
  - **`llm-call` queue:** `max_concurrent_activities=8`, **token-bucket rate-limited** by `TaskQueueRateLimiter` keyed on `(provider, model)`. Activity body uses Phase 4's cassette adapter or the live Agents SDK port (ADR-0020) behind `LeafLlmPort`.
  - **`sandbox-heavy` queue:** `max_concurrent_activities=4` per worker, capped because each sandbox build is ~2–8 minutes of CPU and disk. Sized so 5 workers = 20 concurrent builds = the practical ceiling for a single laptop or small dev box.
  - **`postgres-write` queue:** `max_concurrent_activities=2`, low because writes batch internally — the bottleneck is Postgres, not the worker. Carries the EventLog flush and any direct projection writes.
- **Activity-result memoization.** Idempotent Activities (`resolve_plugin`, `build_bundle`, `read_hot_views`, `match_recipe`) declare `Idempotent=True` and a `cache_key` derived from typed inputs. The Phase 1 content cache is reused as the backing store — same byte format, same eviction policy. On workflow *replay* Temporal hands back the prior result for free; on workflow *retry* (a new run) the cache hits.
- **Heartbeats on long activities.** `sandbox.build` and `sandbox.run` heartbeat every 5s with `progress: SandboxProgress` (a typed Pydantic event); a 30s heartbeat-timeout triggers Temporal's automatic activity-retry path *without* the workflow having to know.
- **Tradeoffs accepted.** Four task queues = four `Worker` instances per pool process. ~5 MiB RSS per Worker is a real cost; sharing one process keeps it bounded. The alternative (one queue, mixed priority) sounds simpler but lets a single 8-minute sandbox build starve 50 quick probes — a measured-bad outcome in pilot.

### Postgres checkpointer — `codegenie.temporal.checkpointer`

- **Purpose.** Back LangGraph's `interrupt()`-and-resume across hours-to-days human pauses (ADR-0016 — Postgres as default). Land typed checkpoint rows that resume in milliseconds.
- **Connection pool.** **pgbouncer in transaction mode**, 100 client connections × 4 server connections per worker pod. The checkpointer uses `asyncpg` directly (not SQLAlchemy core in the hot path) and prepared-statement caching is on. Pool warm-up at worker boot opens 4 connections eagerly so the first workflow doesn't pay TCP+TLS handshake.
- **Partitioning.** `langgraph_checkpoints` is partitioned by `RANGE(created_at)` monthly. **Old partitions are detached, not dropped**, once the workflow they belong to has terminated — keeps the active partition small (every query is partition-pruned to ≤ 1 month) without losing replay capability for compliance.
- **Serialization format.** Pydantic v2 `model_dump_json()` with `mode="json"` for the state envelope; **`msgspec.msgpack` for the inner payload** (`BundleProvenance`, `VulnLedger` discriminator + payload). Msgpack is 3–4× faster to encode/decode than `json` and 30% smaller on the wire — measured in Phase 8's HotView benchmark; we get the same win here on every checkpoint.
- **Tradeoffs accepted.** Two serialization formats at the same boundary is real cognitive cost; pinned in code by a single `Codec` adapter (ADR-0033-style smart constructor: `Codec.encode(state) -> bytes`). The performance gain (≥ 3× checkpoint write throughput vs. all-JSON) earns it.

### Postgres event log — `codegenie.temporal.eventlog`

- **Purpose.** The side-channel typed event log of ADR-0034. Workflow-spanning events (cost rollups, plugin resolution, KG writes, portfolio-level signals); workflow-internal state lives in Temporal history.
- **Schema (initial, S9-XX migration via alembic).**
  ```sql
  CREATE TABLE events (
      event_id        UUID        PRIMARY KEY,
      event_type      TEXT        NOT NULL,        -- discriminator (ADR-0033 sum-type tag)
      workflow_id     TEXT        NULL,            -- newtype WorkflowId; NULL for portfolio events
      correlation_id  TEXT        NULL,
      ts              TIMESTAMPTZ NOT NULL,        -- partition key
      payload         BYTEA       NOT NULL,        -- msgpack-encoded Pydantic union variant
      payload_schema  SMALLINT    NOT NULL         -- per-event-type schema version
  ) PARTITION BY RANGE (ts);

  CREATE INDEX events_wf_idx     ON events USING btree (workflow_id, ts) WHERE workflow_id IS NOT NULL;
  CREATE INDEX events_type_idx   ON events USING btree (event_type, ts);
  CREATE INDEX events_corr_idx   ON events USING btree (correlation_id) WHERE correlation_id IS NOT NULL;
  ```
  Append-only (enforced by a row-trigger that rejects UPDATE/DELETE outside the retention sweep). Partitions monthly. **No JSONB** in the hot append path — `BYTEA` + msgpack is materially faster (~2× insert throughput in the Phase 4 cassette benchmark profile); JSONB views are materialized only inside projections that need ad-hoc SQL.
- **Append path — batched writer.** Each activity worker holds an in-process `EventBatchWriter`:
  - Producer side: every code site (Activity body, workflow signal handler) calls `event_log.append(event)` — non-blocking, drops the typed event into an `asyncio.Queue[EventEnvelope]`. Sub-microsecond.
  - Flusher: a dedicated background `asyncio.Task` drains the queue every **20ms or 256 events, whichever first**, and writes via `COPY ... FROM STDIN BINARY` — the fastest Postgres ingest path. ~5–10× faster than per-event `INSERT`.
  - Failure handling: on Postgres error, the flusher retries with backoff. The batch is held in memory; the worker process refuses graceful shutdown until the queue is drained. Catastrophic loss (kill -9) is bounded by `≤ 20ms × 256 events × workers` worth of trailing events — tens of events portfolio-wide. **Critical events** (`MergeOutcome`, `BudgetExhausted`, `TrustGateFailed`) flush synchronously, bypassing the batcher — paid for in latency to gain durability.
  - **Where the batched writer runs is the trick.** It runs in the activity worker, not the workflow worker. Workflows emit events by enqueueing into a tiny `EmitEvent` Activity that lives on the `postgres-write` queue; that Activity does the batched write. This keeps workflow code I/O-free (replay-safe) without forcing every event to round-trip through Temporal's history.
- **Projection consumers.** Materialized views, `REFRESH MATERIALIZED VIEW CONCURRENTLY` triggered by `pg_notify` on the partition the latest event landed in:
  - `cost_ledger_mv` — `fold(CostIncurred events)` grouped by `(workflow_id, tier, source)`. Cheap upsert; refresh lag target ≤ 200ms p95.
  - `trust_gate_history_mv` — histograms of `TrustGatePassed`/`TrustGateFailed` for the Phase 5 dashboard.
  - `plugin_telemetry_mv` — `PluginResolved` × `MergeOutcome` joins for per-plugin merge rate and fallback rate.
  - Each projection is a **pure fold function** (`fold(events: Iterable[Event]) -> Projection`) testable from a fixture event stream — no Postgres needed for unit tests. Postgres just runs the same fold incrementally via a materialized-view definition that mirrors the Python fold's algebra.
- **Tradeoffs accepted.** BYTEA + msgpack is a small ergonomic cost for ad-hoc DBA queries — paid for with a `events_decoded` SQL view that decodes payload on demand. The decoded view is *slow*; that's fine — the *projections* are the fast read path, and the decoded view exists for forensics.

### Workflow-history → event-log fanout — `codegenie.temporal.history_fanout`

- **Purpose.** Bridge ADR-0034's hybrid model: Temporal owns workflow-internal events natively; the Postgres event log owns workflow-spanning. A small set of *workflow-spanning* events needs to land in *both* places (e.g., `TrustGatePassed` — Temporal already records it as an Activity completion; the event log needs the typed payload for the ROI projection).
- **Internal design.** A "fanout" Activity registered on the `postgres-write` queue. Workflows emit through it explicitly — there is **no Temporal-history-tail listener that auto-projects into Postgres**. Two reasons: (1) Temporal's history API is paged and meant for replay, not high-throughput streaming — building a tail listener risks creating a Postgres-write hot path that depends on Temporal cluster availability; (2) the workflow already knows which events are workflow-spanning (it emits them on purpose). Making fanout explicit keeps the data model honest: every Postgres event was emitted by intention, not derived.
- **Tradeoffs accepted.** A workflow that should emit a workflow-spanning event but doesn't will be missing from the projection. Caught by a static fence test (`tests/fence/test_event_emission_completeness.py`) that walks the LangGraph subgraph code and asserts every node listed in the `WorkflowSpanningEventEmitters` registry actually appends.

### LangGraph ↔ Temporal bridge — `codegenie.temporal.bridge`

- **Purpose.** Phase 6 ships a LangGraph subgraph with `PostgresSaver` (Phase 6 originally said SQLite; Phase 9 swaps to Postgres per ADR-0016 default). Phase 8 ships a three-node Supervisor LangGraph. Phase 9 wraps each LangGraph node as a Temporal Activity *without rewriting the subgraphs*.
- **Internal design.** A single `wrap_node_as_activity(node_fn) -> Callable` adapter — pure functional wrapping, no class hierarchy. The Activity's typed input is the LangGraph state at entry to the node; output is the state after the node ran. The LangGraph compiled graph is constructed once per worker process and held in module scope (~50ms one-time cost amortized over thousands of activities). The Supervisor's `decide()` pure function from Phase 8 is exactly what we want — invoked directly, no Activity needed; only `resolve`, `build_bundle`, and `route` become Activities. Phase 6's nodes follow the same shape.
- **Tradeoffs accepted.** LangGraph and Temporal each have a notion of "node" / "activity" — small conceptual overlap. The bridge keeps it one-line: LangGraph nodes are the unit of *graph composition*, Temporal Activities are the unit of *durable invocation*. They happen to coincide here because Phase 6 designed the graph with semantic boundaries that *also* make sense as failure isolation boundaries.

### Local dev surface — `docker-compose.yml` + `temporal server start-dev`

- **Purpose.** `make dev-up` brings up Temporal + Postgres + Redis + temporal-ui in one command; matches CI.
- **Internal design.**
  - `temporal server start-dev --db-filename .codegenie/temporal-dev.db --ui-port 8233` for the cluster (SQLite-backed dev cluster — Temporal's own choice for fast boot; production uses Postgres-backed Temporal).
  - `docker-compose.yml` services: `postgres-16` (one volume per host, port 5432), `redis-7-alpine` (Phase 8, unchanged), `pgbouncer` (transaction-mode pool).
  - **Worker processes run on the host, not in a container, in dev.** Two reasons: (1) hot-reload via `uvicorn --reload`-style watchers is brittle through container layers; (2) sandbox builds already shell out to host docker — nesting is worse than co-locating. Production uses container-per-worker.
  - **Workflow-worker hot reload is real:** `uvloop` + `watchfiles` + Temporal worker's `restart_workflows_on_code_change=False` (off in dev so a worker restart doesn't reset in-flight test workflows). One restart = ~800ms; acceptable.
- **Tradeoffs accepted.** SQLite-backed `start-dev` Temporal cluster cannot test full HA; that's fine — Phase 16 owns HA. The dev surface tests durability (kill -9 worker, restart, assert resume) which is the exit criterion.

## Data flow

One representative warm run — vulnerability-remediation, recipe-route, no human pause:

```
1. CLI fires      → temporal_client.start_workflow("VulnRemediationWorkflow", request)
                    [<10ms; Temporal frontend round-trip]

2. WF worker picks task →
   workflow.execute_activity("supervisor.resolve", request)
                    [activity worker, ~3ms, memoized in Phase 1 cache]
                    →  emits PluginResolved to event log batch [<1µs, queued]

3. workflow.execute_activity("supervisor.build_bundle", resolution)
                    [activity worker, ~50ms cold / ~2ms memoized; calls shipped BundleBuilder]
                    →  emits BundleBuilt to event log batch

4. workflow.execute_activity("planner.route", bundle)
                    [activity worker, ~5ms; one Redis pipelined read for hot views]
                    →  emits RouteDecided to event log batch (SYNCHRONOUS flush — exit-criterion event)

5. workflow.execute_activity("sherpa.plan", bundle, route)            [activity worker]
   workflow.execute_activity("sherpa.apply_recipe", plan)              [activity worker, ~200ms]
   workflow.execute_activity("sandbox.build_and_test", patch)
                    [sandbox-heavy queue; heartbeats every 5s; 2–8 min]
                    →  TrustGatePassed (fanout: Temporal history + event log batch)

6. workflow.execute_activity("github.open_pr", patch, evidence)        [activity worker, ~600ms]
                    →  MergeOutcome appended SYNCHRONOUSLY (durable critical event)
                    →  workflow waits on signal "human_review_decision" (days; Temporal sleeps)

[caches hit at every memoizable step; LLM never invoked on this run; $0.00]
[event log: 8 events emitted; 7 batched, 2 synchronous flushes; total Postgres latency: ~12ms]
[workflow history: ~14 events; replay-cost on resume: <50ms]
[redis hot views: untouched; Phase 8 cache hit ratio holds]
```

Parallelism markers:
- The `event_log.append` calls are **non-blocking** for the workflow — the batched writer flushes in the background.
- Multiple concurrent workflows share the **same** worker pool; cooperative async lets 50 in-flight workflows run on a 1-vCPU worker because all but `sandbox.build_and_test` are I/O-bound.
- The `sandbox-heavy` queue is the only serializing point; rate-limited deliberately so a portfolio sweep doesn't thrash one machine.

Serialization points to be honest about:
- Every Activity invocation serializes args + return through msgpack. Per-call cost ≤ 0.5ms for typical payloads.
- Every event-log batched flush is one Postgres `COPY` — the natural batching means we serialize *less* per-event than per-call activities.
- Temporal workflow history serialization is Temporal-internal; tuned by their team, not ours.

## Failure modes & recovery

| Failure | Detected by | Recovery |
|---|---|---|
| Activity worker dies mid-recipe-apply | Temporal activity heartbeat timeout (30s) | Temporal re-dispatches to another worker on the same task queue; activity body is idempotent (Phase 6 recipe-apply is content-addressed); no double-apply because the recipe step's effect is captured in a content-hashed patch artifact, not the file system directly. |
| Workflow worker dies | Temporal sticky-task affinity expires (1 min) | Another workflow worker picks up; replays history from the last checkpoint; resumes at the next Activity invocation. Target: < 500ms p95 from worker boot to first Activity dispatched. Tested by `tests/durability/test_kill_worker_resume.py` (exit criterion). |
| Postgres unavailable | `asyncpg.PostgresConnectionError` in the EventLog flusher or checkpointer | EventLog batches accumulate in worker memory up to a 16 MiB cap; over the cap, the worker refuses new activities (back-pressure into Temporal). Workflow worker pauses on next checkpoint write. **Critical events** (MergeOutcome, BudgetExhausted) propagate the error to the activity caller — the workflow retries the activity (Temporal-native). No data loss. |
| pgbouncer pool exhaustion | `PoolTimeout` from asyncpg | Activity raises a retryable error; Temporal backs off. Alert fires (Phase 13 hookpoint) before the pool sustains saturation. Worker concurrency caps are sized below pool depth so this is exceptional. |
| Redis unreachable on hot-view read | Phase 8's existing fall-through to cold storage | Unchanged from Phase 8 — Temporal does not own this path. |
| Workflow non-determinism after a code change | Temporal `NondeterminismError` on replay | Workflow is failed with that error; a `WorkflowReset` operation rewinds to the pre-change checkpoint. Property test in CI runs the cassette-replay determinism check against every PR. |
| Temporal cluster unavailable | `temporalio.exceptions.ServiceUnavailableError` | New workflow starts fail fast; in-flight workflows pause without state loss (they're on disk). Recovery is "wait for Temporal" — workflows resume as the cluster returns. Tested in `tests/resilience/test_temporal_outage.py`. |
| Event log retention sweep deleting in-flight workflow | A retention-sweep race | Sweep is **partition-detach, not row-delete**; retention is enforced by `ts` partition boundaries plus a foreign-key-shaped check that the partition's workflows are all terminal. The sweep cannot touch active partitions; in-flight workflows are safe by construction. |

## Resource & cost profile

- **Tokens per run.** Phase 9 adds **zero** LLM calls; per-run token cost equals Phase 8's: recipe-route $0.00, RAG-route ~$0.015, LLM-route up to Phase 4's per-tier cap.
- **Wall-clock per run (p50/p95, recipe-route, warm gather, no human pause).** p50 = 4 min, p95 = 8 min. The 2–8 min sandbox-build dominates; Temporal overhead is < 2% of wall-clock. RAG-route adds ~3 min for the embedding fetch + retrieval (Phase 4-bounded). LLM-route is Phase 4-bounded, not Phase 9-bounded.
- **Memory per worker.** Workflow worker steady-state: 250 MiB RSS at 50 concurrent workflows (5 MiB per workflow, mostly LangGraph compiled-graph caches shared across all). Activity worker: 400 MiB RSS at 64 concurrent quick-activities, dominated by Pydantic model schema caches and asyncpg buffer pool. Sandbox worker spikes to 1.5 GiB during a build — sized accordingly.
- **Storage growth rate.** Workflow history: ~30 KiB per typical workflow × 1,000 workflows/day = 30 MiB/day. Event log: ~12 events × 4 KiB × 1,000/day = 48 MiB/day. LangGraph checkpoints: ~8 KiB × 4 checkpoints × 1,000/day = 32 MiB/day. **Total: ~110 MiB/day at 1k workflows/day**. Monthly partitions stay under 4 GiB each — well within Postgres B-tree comfort.
- **Hot vs cold cost ratio.** A warm-cache replay of an already-completed workflow's history (for debugging) is ~200× cheaper than the original run (no Activities executed, just history fetched + folded). Cassette-replay tests cost ~5× a single recipe-route workflow's wall-clock — fast enough to be a per-PR check, not a nightly job.

## Test plan

- **Unit tests.**
  - Workflow body: `temporalio.testing.WorkflowEnvironment` with `Time-skipping` enabled. Asserts the workflow follows the right state-machine path; mocks every Activity. Sub-second per test.
  - Activity body: vanilla pytest. Each Activity is a typed async function with no Temporal dependency; testable in isolation.
  - Projections: `fold(events) == expected_projection` on fixture event streams. **No Postgres needed for these tests** — the fold is pure. This is the ADR-0034 "projections independently testable from fixture event streams" property.
  - EventBatchWriter: property tests over `(produce_rate, flush_interval, crash_at_random_offset) → no_event_loss_modulo_in_flight_batch`.
- **Integration tests.**
  - `tests/integration/test_workflow_e2e_postgres.py` — real Postgres, real Temporal dev server, fake Redis (Phase 8 already has this fake), cassette-replay LLM. Runs the recipe-route happy path end-to-end. < 30s.
  - `tests/integration/test_checkpointer_roundtrip.py` — write checkpoint, read back, assert byte-identity through msgpack codec.
- **Durability tests.**
  - `tests/durability/test_kill_worker_resume.py` — start workflow, advance to mid-Activity, `os.kill(worker_pid, SIGKILL)`, restart worker, assert workflow reaches the same terminal state. Property: same final ledger state across N kill points.
  - `tests/durability/test_temporal_cluster_restart.py` — kill the dev Temporal cluster mid-workflow, restart, assert workflow resumes from history.
- **Resilience tier (Phase 5 introduced; extended here).**
  - `tests/resilience/test_postgres_outage.py` — block Postgres for 30s, assert events queue up, no data loss after restoration.
  - `tests/resilience/test_pgbouncer_exhaustion.py` — pin pool to N=2, fire N+1 concurrent activities, assert back-pressure rather than hang.
- **Determinism property.** `tests/property/test_determinism_under_cassette_replay.py` — extended from Phase 4 / Phase 6: for any `(repo_snapshot, cassette_id, embedding_model_digest, kill_offset)`, the workflow reaches byte-identical terminal state across runs with and without a mid-Activity kill.
- **Perf regression canary** (`tests/bench/test_phase09_canary.py`, `-m bench`, nightly).
  - **Throughput canary.** 100 cassette-replay workflows on a fixed-size local Temporal + Postgres + 5 activity workers. Measures workflows/hour. Ratchets up (regression-only) into a frozen baseline JSON; CI fails if throughput drops > 10% vs. baseline. Targets: ≥ 250 workflows/hour (matches the goal above).
  - **Latency canary.** p50/p95 of `read_hot_views` Activity (Phase 8 budget pass-through), `EventBatchWriter` flush, and worker resume after kill. All three have frozen baselines.
  - **Memory canary.** Worker RSS at 50 in-flight workflows; baselined; ratchet-only.
  - **Token canary.** Total LLM token spend over the 100-workflow run is **asserted == 0** (cassette-replay only) — guards against accidentally introducing an LLM call in a workflow code path.
- **Fence tests (added in Phase 9).**
  - `tests/fence/test_no_workflow_retry_loops.py` — AST-walks `codegenie/temporal/workflows/` and forbids `while`, `for ... in range(...)` with retry semantics, `try/except + continue` loops.
  - `tests/fence/test_workflow_imports_are_pure.py` — `codegenie.temporal.workflows` may not import `httpx`, `redis`, `subprocess`, `anthropic`, `openai`, `psycopg`, `asyncpg` (the existing fence vocabulary extended with workflow-pure semantics).
  - `tests/fence/test_event_emission_completeness.py` — every LangGraph node listed in the `WorkflowSpanningEventEmitters` registry has at least one `event_log.append(...)` call inside its Activity body.

## Design patterns applied

| Pattern | Where | Why it fits | Pattern not applied / deliberately skipped |
|---|---|---|---|
| **Hexagonal / Ports & Adapters** | `CheckpointerPort`, `EventLogPort`, `LeafLlmPort` (unchanged from Phase 4) | The workflow body and projections depend on Protocols, not on `asyncpg` / `psycopg`; lets us swap Postgres → Redis for the checkpointer (ADR-0016 reversibility) without touching workflow code. Activities are the adapters. | Did **not** introduce a `TemporalPort` — Temporal SDK is the only durable-execution engine we plan to use, and abstracting it would add ceremony without a second implementation in sight. |
| **Event sourcing for agent runs** | `EventLog` + projections (cost ledger, plugin telemetry, trust gate history) | ADR-0034 mandates it. Replay-driven debugging, projections independently testable from fixture event streams, new observability features become projections — these are the compounding wins the ADR lists, and Phase 9 is where they land operationally. | Did **not** apply event sourcing to *workflow-internal* state — Temporal already is event-sourced (workflow history), and re-doing it in Postgres would be the Two Sources Of Truth anti-pattern ADR-0034 explicitly rejects (Option B). |
| **Sum type / Tagged union** | `EventPayload` (the discriminated union of every event variant), `VulnLedger` (Phase 6, unchanged), `WorkerPoolKind`, `TaskQueueId` | ADR-0033 discipline. Exhaustive matching in projections is what makes "add a new event variant" non-breaking and "rename a field" loud-breaking — exactly the property we want for schema evolution. | Did **not** model "Activity result" as a sum type — Temporal already gives `ActivityResult[T] = Ok | RetryableError | NonRetryableError | Timeout`; building our own would be re-implementing the framework. |
| **Functional core / Imperative shell** | Projection folds (pure); workflow body (orchestration but I/O-free); EventBatchWriter producer side (pure enqueue) | The workflow body must be deterministic (replay safety) — that's literally the imperative-shell discipline with extra teeth. Projections being pure is what makes them testable against fixture streams without Postgres. | Did **not** apply to Activity bodies — they exist precisely to do I/O; making them pure would defeat their purpose. The discipline is *about* the workflow body. |
| **Registry pattern** | `EventTypeRegistry` (event_type → Pydantic variant class), `TaskQueueRegistry` (queue name → worker config), `ProjectionRegistry` | Adding a new event type or projection is one new file + one registration line; no central dispatch table grows. Matches the Phase 0 `@register_probe` shape and the Phase 8 `@register_task_class` shape. | Did **not** use a registry for *workflows themselves* — Temporal's own `@workflow.defn` is already a registry by another name; layering ours on top is ceremony. |
| **Adapter pattern** | `LangGraphNode → TemporalActivity` wrapper (`wrap_node_as_activity`), `Codec` (Pydantic ↔ msgpack ↔ JSON) | Wraps two foreign libraries (LangGraph, Temporal SDK) at one functional seam each. No class hierarchy — just `Callable[[State], Coroutine]` adapters. | Did **not** wrap Pydantic models behind another adapter — they're already the project's wire-type pattern (ADR-0010). |

## Risks (top 3–5)

1. **Workflow history bloat from chatty event emission.** A workflow that calls `event_log.append` 100+ times — easy to accidentally do inside a loop — will grow workflow history rapidly even though the events themselves are in Postgres. The `EmitEvent` Activity is one history record per call. Mitigation: the EventBatchWriter producer side is non-blocking *and* per-workflow-batched (events from one workflow buffer to a per-workflow queue inside the activity, then flush as one `EmitEventsBatch` Activity invocation = one history record). Measured ceiling: ≤ 20 history records per workflow for emission. Fence test enforces this.
2. **pgbouncer transaction-mode incompatibility with prepared statements.** Transaction-mode pooling and `asyncpg`'s prepared-statement cache fight each other in known ways. Mitigation: pin asyncpg's `statement_cache_size=0` on the pgbouncer-fronted connections and rely on Postgres's own plan cache. ~3% latency cost vs. session-mode pooling, paid for in connection-count headroom. If this turns out to be too costly, fallback is session-mode pooling at lower connection count.
3. **Activity-result memoization invalidation drift.** The Phase 1 content cache uses content-addressed keys derived from `declared_inputs`. If Phase 9 derives an Activity cache_key from inputs but a non-deterministic field sneaks in (e.g., `datetime.now()`), the cache will appear to hit while serving stale data — silent. Mitigation: same fence we use for the gather cache — only allow `cache_key` to come from a `CacheKey.derive(typed_inputs)` smart constructor that *only* hashes Pydantic-model fields (no `Any`); plus a property test that asserts repeated cache key derivation is byte-identical.
4. **Postgres becomes the throughput ceiling under burst.** A portfolio sweep of 500 simultaneous workflows × 12 events each × 5 sec spread = 1,200 events/sec. Within target, but a coincident bench run or projection refresh could push it. Mitigation: the `COPY`-batched writer leaves ~5× headroom (target 5k/sec, expected peak 1.2k/sec); projection refreshes are `CONCURRENTLY` (non-blocking); partition pruning keeps every index hot in shared buffers. If still insufficient: shard `events` by `workflow_id` hash — already trivially possible given the schema. Documented as a Phase 13 trigger.
5. **Replay slowness for very long workflows.** A workflow paused on `human_review_decision` for 14 days might have 200+ history events by then. Resume replay should still hit the ≤ 1.5s target, but a worst-case workflow (many retries, large input payloads embedded in history) could blow it. Mitigation: payload-by-reference discipline — every Activity input/output larger than 8 KiB is stored as a Postgres `BYTEA` row keyed by digest and the history holds only the digest. Already the pattern for `ContextBundle` and `RepoContext`; extended to all payloads via the `Codec` adapter.

## Acknowledged blind spots

- **HA Temporal cluster behavior.** The dev surface uses `temporal start-dev` (SQLite-backed). Throughput numbers above assume a comparably-sized prod Temporal cluster; cluster-side bottlenecks (history shard contention, matching service throughput) are unmeasured here. Phase 16 owns this.
- **Cross-DC replication of the event log.** No design for it. The schema is partition-friendly and logical-replication-friendly, but verifying that under load is out of scope.
- **Observability cost.** Temporal's own metric export, the projection-refresh pg_notify storms, and the synchronous critical-event flushes all cost something. Not measured at portfolio scale here; Phase 13 owns the cost-ledger projection and will report.
- **What happens when the Pydantic schema for an event variant changes mid-workflow.** ADR-0033's "additive only" rule covers the wire-format side, but a workflow that started under v1 and resumes under v2 sees the new field as `None`. Functionally fine; might confuse projections that aggregate across versions. Phase 11 (Stage 7 Learning) is the first heavy projection consumer; the discipline gets tested then.
- **CPU profile under cassette-replay batch.** A 100-workflow burst on a 5-worker laptop is approximate from prior Phase-4 cassette runs, not measured at the Phase 9 shape. The throughput canary will tell us the real number; the target is a target.

## Open questions for the synthesizer

1. **Should `RetryPolicy` be configured per-Activity or per-TaskQueue?** Per-Activity gives finer control (LLM 429s want longer backoff than transient Postgres errors); per-TaskQueue is simpler ops. The performance-first answer is per-Activity at the cost of declaration ceremony. Defer to synthesizer's read of best-practices lens.
2. **Synchronous-flush event vocabulary — fixed or extensible?** I made `MergeOutcome`, `BudgetExhausted`, `TrustGateFailed` synchronous-flush by hardcoded list. Extensible via a `@critical_event` decorator on the Pydantic class would be more open/closed, but adds discovery cost. The security lens will likely want more events on the critical list; I want as few as possible for throughput.
3. **`EmitEvent` Activity granularity — per-event vs. per-workflow-batch.** I chose per-workflow-batch (one Activity invocation = N events) to bound workflow-history records. The best-practices lens may push for per-event for "each event is auditable in Temporal history independently." The two are not the same property; pick one.
4. **Phase 6 checkpointer migration plan.** Phase 6 shipped with SQLite; ADR-0016 names Postgres. Does Phase 9 *also* migrate in-flight Phase-6 workflows from SQLite → Postgres, or only new workflows? Migration is doable (drain SQLite as workflows complete; new workflows start on Postgres). Latency for the cutover, not throughput, drives the answer.
5. **Whether `pg_notify` is fast enough at our event-log append rate.** A 5k/sec append rate produces 5k notifications/sec; Postgres handles it, but every projection subscriber has to keep up. Alternative: poll a sequence counter every 100ms. The notification mechanism affects projection-lag latency, not append throughput, so it's a synthesizer-tier call.
6. **Whether to ship `temporal-ui` as part of `make dev-up` or only as an opt-in.** UI bundles add ~150 MiB to the docker pulls; not throughput-relevant but real for fresh-checkout developer wall-clock-to-first-workflow. I'd default it on; security lens may differ.
