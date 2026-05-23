# Phase 09 — Durable workflow envelope: Temporal: Final design

**Status:** Design of record (synthesized from three competing designs + critique).
**Synthesized by:** Graph-of-Thought synthesizer subagent
**Date:** 2026-05-23
**Sources:** `design-performance.md` · `design-security.md` · `design-best-practices.md` · `critique.md`

## Lens summary

Best-practices [B] dominates the **shape** (delegation to the SDK and to upstream `langgraph-checkpoint-postgres`; flat packages; one activity per file; `match` + `assert_never` over a small typed event union; one connection pool); performance [P] dominates the **hot path** (two worker pools, four task queues by workload class, payload-by-reference for any bytes over 8 KiB, batched event-log writer with a *bounded* synchronous-flush vocabulary, `gather_id`-stamped Phase 8 hot views surviving unchanged); security [S] dominates the **trust boundary** (role-scoped Postgres grants, alembic supply-chain discipline, `RedactedActivityPayload.seal()` at the *Activity → workflow-history* seam *only*, AST-fence over workflow code, loopback-only `temporal-ui`). The synthesis **departs from all three** on five things the critic forced into the open: (1) the workflow body **wraps** but does not *contain* the Phase-6 LangGraph subgraph — Phase 6's existing `VulnRemediationSut` runs *inside one fat* `RunVulnSubgraphActivity` (the [S]-shape, single-activity bridge) which preserves the Phase-6 `SutDigest` contract that the per-node 1:1 mapping ([P]/[B]) would have shattered; (2) the Phase-9 event vocabulary is broader than [B]'s five but narrower than [P]'s sprawl — exactly the variants Phase 8's `codegenie.plugins.events` already emits plus the *minimum* superset Phases 10/11/13 need to add by addition; (3) the BLAKE3 prev-hash chain is **per-workflow**, not global — kills the [S] global serial-bottleneck the critic destroyed without giving up tamper-evidence; (4) `MultiPluginDispatch` from Phase 8's `SupervisorDecision` lands as a *real* parent/child Temporal workflow shape (none of the three designed it); (5) the existing Phase-8 hash-chained `codegenie.plugins.events` log becomes the *first writer* into the canonical Postgres event log via a one-way emitter port — the cutover is not parallel, it is **migrated forward on first emit** with a written ADR. The synthesis explicitly rejects: pgcrypto column encryption on `events.payload` (critic showed it is decorative against the projection path), HMAC capability tokens for in-process credential scoping (forgeable by anyone with the worker mount), the `cost_ledger_v1` stub raising `NotImplementedError` (silent-edit-reservation, ADR-0043 violation), and a homegrown `TemporalPort` (no second substrate in sight, premature pluggability).

## Goals (concrete, measurable)

- **G1 — Durability (the exit criterion).** Workflows survive `SIGKILL` of any worker (workflow worker or activity worker) and `temporal kill && temporal start` of the dev cluster. Verified by `tests/durability/test_kill_worker_resume.py` and `tests/durability/test_temporal_cluster_restart.py`; both must reach byte-identical terminal `VulnLedger` state across N kill offsets. [synth, satisfies roadmap §249]
- **G2 — `temporal-ui` shows live workflow inspection on `127.0.0.1:8233`.** [B]/[S] Bundled via `docker-compose`; wrapper script `scripts/temporal-dev.sh` rejects `--ip 0.0.0.0`. A `tests/fence/test_temporal_ui_loopback.py` greps every checked-in script. [S, satisfies roadmap §249]
- **G3 — Zero application-level retry loops.** [B] `import-linter` + `forbidden-patterns` regex (`while.*retry|for .* range.*retries|except.*: *continue`) over `src/codegenie/durable/workflows/*.py`. All retries flow through Temporal `RetryPolicy` declared in a module-level `Final` table keyed by activity name. [B, satisfies roadmap §249]
- **G4 — Workflow body is deterministic at the import level.** [S]/[B] `import-linter` contract forbids `random`, `time`, `datetime`, `uuid`, `os`, `socket`, `httpx`, `requests`, `redis`, `psycopg`, `asyncpg`, `subprocess`, and any `codegenie.exec` / `codegenie.transforms` / `codegenie.probes` module from importing into `codegenie.durable.workflows`. Allowed: `workflow.now()`, `workflow.uuid4()`, `workflow.logger`, `workflow.execute_activity`, `workflow.execute_child_workflow`, `workflow.wait_condition`. Plus a `Replayer`-based fixture replay in CI. [synth]
- **G5 — `SutDigest` invariance across the wrap.** The Phase-6 `VulnRemediationSut.digest()` produces byte-identical output whether the sut is the Phase-6 `LocalVulnRemediationSut` (in-process LangGraph) or the new Phase-9 `TemporalVulnRemediationSut` (LangGraph inside one Activity). Property test runs the canonical Phase-6 test cases through both suts and `assert digest_a == digest_b`. [synth — departure from all three]
- **G6 — Event-log append throughput.** ≥ **3,000 events/sec** sustained portfolio-wide from 5 activity workers, p95 commit latency ≤ **15 ms** including BLAKE3 chain compute. [P, scaled down from 5k/sec after critic's serial-chain attack — the per-workflow chain is the relaxation]
- **G7 — Audit completeness for the seven critical event types.** `TrustGatePassed`, `TrustGateFailed`, `LlmInvoked`, `RecipeApplied`, `PrOpened`, `MergeOutcome`, `WorkflowTerminated` land in the Postgres event log within **5 s** of the underlying activity completion. Lost-event SLO: **0 silent drops** — drops are detected by the *per-workflow* BLAKE3 chain gap-detection at projection time. [S, scoped to a closed vocabulary the critic forced]
- **G8 — Workflow-history compactness.** Every Activity input/output > **8 KiB** is replaced by a `BlobRef(digest, store)` keyed into a Postgres `BYTEA` blob table; history records hold only the digest. Per-workflow history ≤ **30 events nominally**, ≤ **200 events worst-case** (long retry storm + heartbeats). [P, this is the payload-by-reference discipline best-practices missed]
- **G9 — Per-task-queue credential blast radius.** Compromise of *one* activity worker process cannot: (a) open PRs for a repo outside the active workflow's allowlist; (b) write Postgres events of a `kind` outside its task queue's allowlist; (c) terminate or signal a workflow on a different task queue. Verified by `tests/adv/test_worker_credential_blast_radius.py`. [S, but **two task queues** in Phase 9 — `vuln-remediation-node-npm` and `system` (event-log writer + bridge) — not the N×M sprawl the critic warned about]
- **G10 — Alembic supply-chain integrity.** Every migration in `src/codegenie/events/alembic/versions/` has a SHA pinned in `tools/alembic-revisions.lock`; CI verifies. Migration role has no DML on application tables. Schema snapshot diff in CI. [S, scaled to one alembic directory, not three]
- **G11 — `$/PR` regression: zero.** Phase 9 adds **zero** LLM calls. recipe-route = $0.00; RAG-route = ≤ $0.02; LLM-route = Phase-4-bounded. Token canary asserts `total_tokens == 0` on the cassette-replay durability test. [P]

## Architecture

```
                                  Phase 0 — Untrusted (internet, repo content, LLM output)
                                                            │
                                                            ▼
   ┌──────────────────────────────────────────────────────────────────────────────────────┐
   │                  TEMPORAL CLUSTER (dev: `temporal server start-dev`)                   │
   │                  (prod-shape out of scope: 3 server pods, ADR-0003)                    │
   │   Frontend (mTLS in prod, plain TCP in dev) ─▶ History (sharded per WF)                │
   └────────────────────────┬─────────────────────────────────────────┬─────────────────────┘
                            │ task queues                              │ replay (cheap, paged)
                            ▼                                          ▼
        ┌────────────────────────────────┐         ┌────────────────────────────────────────┐
        │ WORKFLOW WORKER POOL           │         │ ACTIVITY WORKER POOLS (two task queues) │
        │ (workflow-only, no IO)         │         │   queue: vuln-remediation-node-npm       │
        │ codegenie.durable.workflows.*  │         │     creds: GitHub PAT scoped to active   │
        │   VulnRemediationWorkflow      │         │            repo, LLM key (vuln budget),  │
        │   MultiPluginParentWorkflow    │         │            microVM control plane         │
        │                                │         │   queue: system                          │
        │ AST fence + import-linter      │         │     creds: Postgres event-log writer,    │
        │ enforced on import             │         │            checkpointer DB role          │
        └────────────────┬───────────────┘         └────────────────┬───────────────────────┘
                         │ workflow.execute_activity                 │
                         ▼                                          ▼
   ┌───────────────────────────────────────────────────────────────────────────────────────┐
   │ Activity catalog (each = thin Pydantic-typed wrapper over an existing Phase 3-8 fn):   │
   │   resolve_plugin    (wraps codegenie.plugins.resolver.resolve)        [reused]         │
   │   build_bundle      (wraps codegenie.plugins.BundleBuilder.build)     [reused]         │
   │   route             (wraps codegenie.planner.route)                   [reused]         │
   │   run_vuln_subgraph (RUNS Phase-6 LangGraph subgraph INSIDE this ONE activity)  ◀── [synth]
   │   sandbox_build_and_test (heartbeats every 5s, wraps Phase-5 SubprocessJail)            │
   │   github_open_pr    (PrOpenCapability + per-repo TTL token)                              │
   │   emit_event        (the ONLY writer to the events table; on the `system` task queue)   │
   │   resolve_blob_ref  (read-side of payload-by-reference, on `system`)                    │
   │   write_blob_ref    (write-side of payload-by-reference, on `system`)                   │
   └────────────────┬─────────────────────────────────────────────────────┬────────────────┘
                    │ all activity I/O                                    │ heavy compute (sandbox)
                    ▼                                                     ▼
   ┌──────────────────────────────────────────┐         ┌─────────────────────────────────┐
   │  POSTGRES 16 (docker-compose; alembic)    │         │   microVM (ADR-0012)             │
   │  ┌─────────────────────────────────────┐  │         │   Phase-5 boundary; UNCHANGED    │
   │  │ schema: temporal                    │  │         │   no creds, no Temporal reach    │
   │  │   (auto-setup image owns it)        │  │         └─────────────────────────────────┘
   │  ├─────────────────────────────────────┤  │
   │  │ schema: langgraph_checkpoints       │  │         ┌─────────────────────────────────┐
   │  │   (langgraph-checkpoint-postgres    │  │         │   REDIS (Phase 8, unchanged)     │
   │  │    owns it; we pin version)         │  │         │   hot views, gather_id-stamped   │
   │  ├─────────────────────────────────────┤  │         └─────────────────────────────────┘
   │  │ schema: events                      │  │
   │  │   events     (typed, append-only)   │  │
   │  │   blob_refs  (BYTEA, addressed by    │  │
   │  │              BLAKE3 digest)          │  │
   │  │   trigger:   events_immutable        │  │
   │  │              raises on UPDATE/DELETE │  │
   │  │   chain:     per-workflow BLAKE3     │  │
   │  │              prev_hash + seq         │  │
   │  └─────────────────────────────────────┘  │
   │  Roles:                                    │
   │    migrations_role — DDL only              │
   │    application_role — INSERT on events;     │
   │      SELECT on events, blob_refs            │
   │    read_role — SELECT on projections only   │
   │    temporal_role — owns schema temporal     │
   └──────────────────────────────────────────┘
                    ▲
                    │ pure folds
                    │
   ┌──────────────────────────────────────────┐
   │ codegenie.events.projections              │
   │   audit_trail (workflow_id → events)      │
   │   retry_histogram (gate × failing signal) │
   │   plugin_telemetry (per-plugin merge/fall) │
   │   (Phase 11: kg_writeback — additive)      │
   │   (Phase 13: cost_ledger — additive)       │
   └──────────────────────────────────────────┘

  temporal-ui: docker-compose; bind 127.0.0.1:8233 ONLY; wrapper script rejects other binds.
  alembic: src/codegenie/events/alembic/; owns the `events` schema only.
```

## Components

### 1. Workflow definitions — `codegenie.durable.workflows`

- **Provenance.** [B] shape · [P] tiny state · [S] determinism fence · [synth] `MultiPluginParentWorkflow`.
- **Purpose.** Deterministic outer envelope. One `@workflow.defn` per top-level workflow. Phase 9 ships **two**: `VulnRemediationWorkflow` (one-repo-one-CVE, the Phase-6 shape) and `MultiPluginParentWorkflow` (the Phase-8 `MultiPluginDispatch` shape, ADR-0042). The parent uses `workflow.execute_child_workflow` to fan out one `VulnRemediationWorkflow` per `PluginWorkItem` under a shared `parent_workflow_id`.
- **Interface.**
  ```python
  @workflow.defn(name="VulnRemediationWorkflow")
  class VulnRemediationWorkflow:
      @workflow.run
      async def run(self, request: VulnRemediationRequest) -> VulnRemediationResult: ...

      @workflow.signal(name="human_review_decision")
      def human_review_decision(self, decision: HumanReviewDecision) -> None: ...

      @workflow.query(name="state")
      def state(self) -> VulnLedger: ...

      @workflow.signal(name="cancel")
      def cancel(self, reason: CancellationReason) -> None: ...

  @workflow.defn(name="MultiPluginParentWorkflow")
  class MultiPluginParentWorkflow:
      @workflow.run
      async def run(self, dispatch: MultiPluginDispatch) -> ParentResult: ...
  ```
- **Internal design.**
  - Workflow body is a pure orchestration loop over the Phase-6 `VulnLedger` sum type (`NeedsPlan | PlanReady | PatchApplied | GateFailedRetryable | AwaitingHumanReview | Completed | FailedUnrecoverable`). State is tiny: the ledger variant + a `WorkflowId`/`RepoId`/`CorrelationId` triple. Large payloads (`ContextBundle`, raw cassette responses, sandbox logs) cross via `BlobRef` only ([P] payload-by-reference, [G8]).
  - **Determinism fence.** `import-linter` contract `codegenie.durable.workflows-must-be-pure` (declared in `pyproject.toml`) forbids the modules in G4. A second AST fence (`tests/fence/test_workflow_determinism.py`) walks the source and rejects literal calls to `random.*`, `time.*`, `datetime.now`, `uuid.uuid4`, `os.environ`, `socket.*`, `open(`, `set(` literal iteration without `sorted(...)`. The fence list is [S]'s, narrowed to what the critic showed actually bites (LangGraph version drift in iteration order — `set` literal use is the canonical trigger).
  - **No retry loops.** Per-activity `RetryPolicy` lives in `codegenie.durable.activities.retry_policies` as a module-level `Final` table keyed by activity name (e.g., `apply_patch -> RetryPolicy(initial_interval=1s, backoff=2.0, max_attempts=3, non_retryable=[BudgetExhausted, SchemaValidationError, RecipeMissedError, RagMissedError])`). The `non_retryable` list explicitly includes the **tier-descent triggers** ([P] hidden-assumption #3 from critic — `RecipeMissedError` and `RagMissedError` are *not* retryable; they signal Phase-4 `FallbackTier` descent, which the workflow body owns).
  - **`MultiPluginParentWorkflow` semantics.** Receives `MultiPluginDispatch(parent_workflow_id, work_items)`; starts one child workflow per item with `workflow.start_child_workflow(VulnRemediationWorkflow, work_item.request, id=...)`; awaits all children; aggregates `VulnRemediationResult`s into a `ParentResult` (`AllMerged | SomeMerged(merged, failed) | AllFailed`). The Phase-8 `SupervisorDecision.MultiPluginDispatch` variant maps directly. [synth — none of the three designed this; critic-3-roadmap forced it]
- **Where it lives.** `src/codegenie/durable/workflows/vuln_remediation.py`, `src/codegenie/durable/workflows/multi_plugin_parent.py`.
- **Tradeoffs.** Two workflow classes in Phase 9 not one. Earned by ADR-0042 + critic's Phase-8-shape attack on best-practices.

### 2. Activity catalog — `codegenie.durable.activities`

- **Provenance.** [B] one-file-per-activity, registry decorator · [P] task-queue partitioning by workload class · [S] capability tokens at side-effect sites · [synth] `run_vuln_subgraph` is *one fat activity* not many small ones.
- **Purpose.** Thin Pydantic-typed wrappers around shipped Phase 3-8 functions; one wrapper per stage; the seam Temporal sees.
- **Interface (selected).**
  ```python
  @register_activity(name="resolve_plugin", timeout=timedelta(seconds=30))
  @activity.defn(name="resolve_plugin")
  async def resolve_plugin(input: ResolvePluginInput) -> ResolvePluginOutput: ...

  @register_activity(name="run_vuln_subgraph", timeout=timedelta(minutes=20))
  @activity.defn(name="run_vuln_subgraph")
  async def run_vuln_subgraph(input: RunSubgraphInput) -> RunSubgraphOutput:
      """
      The Phase-6 LangGraph SHERPA loop runs to terminal-or-pause INSIDE this one Activity.
      The activity heartbeats per LangGraph node transition (~10–30 heartbeats per run).
      Replay-determinism does not apply to LangGraph internals — they're in the imperative
      shell. Workflow code sees only the typed RunSubgraphOutput.
      """
      ...

  @register_activity(name="emit_event", timeout=timedelta(seconds=5))
  @activity.defn(name="emit_event")
  async def emit_event(input: EmitEventInput) -> EmitEventOutput: ...
  ```
- **Internal design.**
  - **Single bridge activity.** `run_vuln_subgraph` is the *one place* the Phase-6 LangGraph subgraph runs. Inside this activity, `codegenie.plugins.events` continues to append to its hash-chained log (Phase 8 keeps working unchanged); the activity's *terminal* event (`SubgraphCompleted | SubgraphPausedHITL | SubgraphFailed`) is the only thing visible at the Temporal layer. This preserves the Phase-6 `SutDigest` contract (G5) — the digest is computed by the Phase-6 builder over the in-activity LangGraph state, exactly as today. [synth — answers the critic's "disagreement that matters most"]
  - **Heartbeats.** `sandbox_build_and_test` and `run_vuln_subgraph` heartbeat every 5 s with a typed `ActivityProgress` payload. Heartbeat-timeout (30 s) drives Temporal's automatic re-dispatch.
  - **Capability tokens — but real ones.** Privileged side-effects (`github_open_pr`, `emit_event`, `llm_invoke`) take a typed `Capability` injected by the worker at activity start. The capability is **not HMAC-signed** (critic's correct attack: anyone with the worker mount has the key). Instead it is a `frozen=True` Pydantic record minted by the worker from its task-queue identity, threaded explicitly through function signatures (no `ContextVar`), and *only* the activity wrapper's allowlist on its task queue mints it. The security property is *task-queue partitioning*, not cryptographic non-forgeability — the worker's *credentials* are scoped at the K8s/process-mount layer (G9). The Capability type is the *auditable interface*, not the trust root. [synth — departure from [S]'s HMAC story]
  - **Two task queues, not twelve.** `vuln-remediation-node-npm` (the only Phase-7-shape plugin shipped) + `system` (for `emit_event`, `resolve_blob_ref`, `write_blob_ref`). Phase 10/7.5 *add* queues by addition; Phase 9 ships two. [synth — scaling-back of [S]'s N×M sprawl that the critic forced]
  - **Idempotency by `attempt_id`.** Every side-effect-bearing activity takes an `AttemptId` and keys its underlying store on it. Temporal's at-least-once becomes exactly-once at the data layer. [B]
- **Where it lives.** `src/codegenie/durable/activities/{resolve_plugin,build_bundle,route,run_vuln_subgraph,sandbox_build_and_test,github_open_pr,emit_event,resolve_blob_ref,write_blob_ref}.py`. One file per activity; one test file per activity.
- **Tradeoffs.** The single-activity bridge means Temporal's history granularity is coarser than per-node — the trade earns Phase-6 digest invariance.

### 3. LangGraph ↔ Temporal bridge — `codegenie.durable.bridge`

- **Provenance.** [S]/[synth] single-activity wrap · departs from [B]'s per-node and [P]'s "supervisor decide() invoked directly, route() as activity."
- **Purpose.** Adapter that exposes the Phase-6 `VulnRemediationSut` Protocol against the Temporal runtime: a `TemporalVulnRemediationSut` whose `run_case` calls `temporal_client.start_workflow(VulnRemediationWorkflow, ...)` and whose `digest()` delegates to the Phase-6 in-process builder for the case at hand.
- **Interface.**
  ```python
  class TemporalVulnRemediationSut(VulnRemediationSut):
      def __init__(self, *, temporal_client: Client, blob_store: BlobStore) -> None: ...
      async def run_case(self, case: VulnRemediationCase) -> VulnRemediationResult: ...
      def digest(self) -> SutDigest: ...   # delegates to Phase-6 builder; identical bytes
  ```
- **Internal design.**
  - **One bridge, one direction.** The Phase-8 Supervisor's three LangGraph nodes (`resolve`, `build_bundle`, `route`) map 1:1 to Temporal Activities — that part is [P]/[B]. The Phase-6 SHERPA subgraph, however, runs *inside* `run_vuln_subgraph` as one activity — that part is [S]. The Phase-6 graph is not split because Phase 6 ships `SutDigest` semantics that depend on the in-process graph's checkpoint structure; splitting would break Phase 6.5's harness fixtures (G5).
  - **Why this asymmetry.** Phase 8's three Supervisor nodes are deliberately shaped to *be* the Temporal seam (Phase 8 final-design §"three-node LangGraph" calls this out). Phase 6's SHERPA subgraph is *not* — it was designed before Phase 9 and its node-level identity is Phase-6-private. Wrapping the whole thing is the only way to land Phase 9 without a Phase-6 redesign.
- **Where it lives.** `src/codegenie/durable/bridge.py`.
- **Tradeoffs.** Temporal cannot see *which* LangGraph node failed inside `run_vuln_subgraph` — only that the activity failed. The Phase-6 hash-chained `codegenie.plugins.events` log (which *does* see the node-level detail) is mirrored forward into the canonical event log via `emit_event` calls inside the activity body. Auditability is preserved; Temporal-history granularity is coarser. ADR-implied.

### 4. Postgres checkpointer adapter — `codegenie.durable.checkpointer`

- **Provenance.** [B] delegation to upstream, plus the Adapter pattern survives the critic ([B]'s adapter was a "forwarder" — we add genuine translation).
- **Purpose.** Replace the Phase-6 SQLite checkpointer per ADR-0016 default. Behind the project's `LangGraphCheckpointerPort` Protocol.
- **Interface.**
  ```python
  class LangGraphCheckpointerPort(Protocol):
      def saver(self) -> BaseCheckpointSaver: ...
      def health(self) -> CheckpointerHealth: ...    # NEW — what makes this an adapter not a forwarder

  class PostgresCheckpointerAdapter:
      def __init__(self, *, pool: AsyncConnectionPool) -> None: ...
      def saver(self) -> PostgresSaver: ...
      def health(self) -> CheckpointerHealth: ...    # pool stats + last-write age
  ```
- **Internal design.**
  - Wraps `langgraph_checkpoint_postgres.PostgresSaver`; adds a typed `CheckpointerHealth` query the upstream class does not expose — that is the translation the Adapter pattern requires.
  - **One connection pool, shared.** `psycopg_pool.AsyncConnectionPool` per worker process; the checkpointer and `emit_event` share it. **No pgbouncer in Phase 9** — the critic's pgbouncer-vs-prepared-statements attack on [P] showed it costs throughput; defer to Phase 16 if and when connection-count actually saturates.
  - **Three schemas, one DB, written owners.** `temporal` (Temporal's `auto-setup` image owns), `langgraph_checkpoints` (`PostgresSaver` owns; we pin the upstream version in `pyproject.toml`), `events` (Phase-9 alembic owns). A README under `src/codegenie/events/alembic/README.md` declares the ownership; CI asserts no Phase-9 migration touches the other two.
  - **Phase-6 SQLite migration.** In-flight Phase-6 workflows on SQLite drain naturally (existing workflows complete on SQLite; new workflows start on Postgres). A new ADR (`ADR-0001` under Phase 9) records the drain-don't-cutover policy.
- **Where it lives.** `src/codegenie/durable/checkpointer.py`.
- **Tradeoffs.** Two checkpointer implementations in the codebase during the drain window; lifecycle ends when the last Phase-6 SQLite-backed workflow terminates.

### 5. Canonical event log — `codegenie.events`

- **Provenance.** [B] one boring table · [S] role-scoped grants + append-only trigger · [P] batched writer for non-critical events · [synth] **per-workflow** BLAKE3 chain (not global).
- **Purpose.** The single typed append-only side-channel of ADR-0034.
- **Schema (one alembic migration, `0001_create_events_schema.py`).**
  ```sql
  CREATE SCHEMA events;

  CREATE TABLE events.events (
      event_id      UUID        PRIMARY KEY,
      workflow_id   TEXT        NULL,                     -- newtype WorkflowId; NULL = portfolio event
      kind          TEXT        NOT NULL,                 -- ADR-0033 sum-type discriminator
      timestamp     TIMESTAMPTZ NOT NULL,
      correlation_id TEXT       NULL,
      payload       JSONB       NOT NULL,                  -- Pydantic-typed; small; large payloads ride blob_refs
      prev_hash     BYTEA       NULL,                      -- BLAKE3 chain; per (workflow_id) NULL for first row
      row_hash      BYTEA       NOT NULL,
      wf_seq        BIGINT      NOT NULL                   -- per-workflow monotonic
  );
  CREATE INDEX events_wf_idx     ON events.events (workflow_id, wf_seq) WHERE workflow_id IS NOT NULL;
  CREATE INDEX events_kind_idx   ON events.events (kind, timestamp);
  CREATE INDEX events_corr_idx   ON events.events (correlation_id) WHERE correlation_id IS NOT NULL;
  CREATE UNIQUE INDEX events_wf_seq_uniq ON events.events (workflow_id, wf_seq) WHERE workflow_id IS NOT NULL;

  CREATE TABLE events.blob_refs (
      digest        BYTEA       PRIMARY KEY,               -- BLAKE3(content)
      content       BYTEA       NOT NULL,
      created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
  );

  CREATE OR REPLACE FUNCTION events.events_immutable()
  RETURNS TRIGGER AS $$
  BEGIN
      RAISE EXCEPTION 'events.events is append-only; mutation denied';
  END; $$ LANGUAGE plpgsql;

  CREATE TRIGGER events_immutable_trg
      BEFORE UPDATE OR DELETE OR TRUNCATE ON events.events
      FOR EACH STATEMENT EXECUTE FUNCTION events.events_immutable();

  REVOKE UPDATE, DELETE, TRUNCATE ON events.events FROM application_role;
  GRANT  INSERT, SELECT                    ON events.events    TO application_role;
  GRANT  INSERT, SELECT                    ON events.blob_refs TO application_role;
  GRANT  SELECT                            ON events.events    TO read_role;
  ```
- **Per-workflow BLAKE3 chain.** `prev_hash = BLAKE3(prev_row_in_same_workflow.row_hash || canonical_payload)`. **The chain is scoped per `workflow_id`, not global.** This kills the critic's attack on [S]'s global serial-bottleneck — concurrent workflows append in parallel — while preserving tamper-evidence inside each workflow's own audit trail. The chain-verification projection walks each workflow's stream independently. Portfolio-level events (`workflow_id IS NULL`) form their own chain. [synth — direct departure from [S], earned by the critic]
- **No pgcrypto column encryption.** Critic showed it is decorative against the projection path (every projection holds the decryption key); the security gain is illusory. Encryption-at-rest is delegated to the volume layer (LUKS / cloud TDE) — out of scope for Phase 9. [synth — departure from [S]]
- **Append-only enforcement: three layers.** (1) `REVOKE UPDATE/DELETE/TRUNCATE` for `application_role`; (2) `BEFORE` trigger raises; (3) per-workflow BLAKE3 chain. Defeating all three requires DB-superuser AND chain-forgery AND a checked-in trigger-removal migration. [S, intact]
- **Append path — batched, with a *closed* synchronous-flush vocabulary.** Activity-worker holds an `EventBatchWriter` (asyncio.Queue, flush every 20 ms or 256 events via `COPY ... FROM STDIN BINARY` *for JSONB payloads — Postgres handles JSONB in COPY*). Synchronous-flush vocabulary is **fixed** (`@critical_event` decorator on the Pydantic class) and contains exactly: `MergeOutcome`, `BudgetExhausted`, `TrustGateFailed`, `WorkflowTerminated`, `ChainTamperDetected`. **`RouteDecided` is *not* synchronous** — the critic showed [P]'s 5k/sec target collapses if every workflow's `RouteDecided` blocks. `RouteDecided` rides the batch. [synth — applies critic-2's correction to [P]]
- **`EventLog` interface.**
  ```python
  class EventLog:
      def __init__(self, *, pool: AsyncConnectionPool) -> None: ...
      async def append(self, event: EventPayload, *, capability: EventLogWriteCapability) -> EventId: ...
      async def append_batch(self, events: Sequence[EventPayload], *, capability: EventLogWriteCapability) -> tuple[EventId, ...]: ...
      async def read_workflow(self, workflow_id: WorkflowId) -> AsyncIterator[EventPayload]: ...

  def critical_event(cls: type[T]) -> type[T]:
      """Mark an event variant as synchronous-flush at append time."""
      _CRITICAL_EVENTS.add(cls.__name__)
      return cls
  ```
  No `ContextVar`-backed `record_event` helper. The critic showed [B]'s `__all__`-discipline is unsound; every emit site threads `EventLogWriteCapability` explicitly. [synth — departure from [B]]
- **Where it lives.** `src/codegenie/events/payloads.py`, `src/codegenie/events/log.py`, `src/codegenie/events/blob_refs.py`, `src/codegenie/events/alembic/`.

### 6. Typed event vocabulary — `codegenie.events.payloads`

- **Provenance.** [synth] — broader than [B]'s five, narrower than [P]'s sprawl. Sized exactly by the cross-phase needs the critic exposed.
- **The Phase-9 event variants.** Phase 9 ships the minimum *non-additive* superset:
  ```python
  WorkflowStarted          # task_class, config_digest, parent_workflow_id|None
  WorkflowResumed          # resumed_from_event_id, retry_count
  WorkflowCompleted        # outcome: merged|closed|abandoned
  @critical_event
  WorkflowTerminated       # by_operator|by_budget|by_failure, reason
  PluginResolved           # plugin_id, extends_chain, fallback_used  (already in Phase 8 chain)
  BundleBuilt              # bundle_digest, slices: tuple[SliceKind, ...]  (already in Phase 8 chain)
  RouteDecided             # route: recipe|rag|llm, fallback_descent: bool
  RecipeApplied            # recipe_id, patch_digest, attempt_id
  RecipeMissed             # recipe_id, miss_reason
  RagInvoked               # cassette_id|live, hit: bool, tokens: TokenCount
  LlmInvoked               # provider, model, cassette_id|live, tokens, cost_usd
  PatchApplied             # patch_digest, engine: npm_lockfile|openrewrite, attempt_id
  TrustGatePassed          # gate_id, signals: dict[SignalKind, SignalValue]
  @critical_event
  TrustGateFailed          # gate_id, failing_signals, retry_count
  PrOpened                 # pr_url, repo_id
  HumanReviewRequested     # reason, evidence_digest
  HumanReviewDecision      # decision: approved|rejected|deferred
  @critical_event
  MergeOutcome             # pr_url, decision: merged|closed|modified, reviewer
  @critical_event
  BudgetExhausted          # workflow_id, cap_usd, spent_usd
  @critical_event
  ChainTamperDetected      # workflow_id, expected_hash, actual_hash, at_seq
  ```
  21 variants. The "extension by addition" path is clean for Phase 10 (`CandidateRepo`, `AssessmentResult`), Phase 11 (`SolvedExampleWritten`), Phase 13 (`CostIncurred` — though `LlmInvoked.cost_usd` may already be sufficient). [synth — answers critic-3 on [B] and critic-roadmap-1]
- **Discriminated union.** `EventPayload = Annotated[Union[..., ...], Field(discriminator="kind")]`. `frozen=True, extra="forbid"` on every variant. `match` + `assert_never` in every projection. ADR-0033 compliance — enforced by an `mypy --strict` pass.
- **The Phase-8 `codegenie.plugins.events` cutover.** The existing hash-chained log keeps running inside `run_vuln_subgraph` *for one phase*. Its terminal records (`PluginResolved`, `BundleBuilt`, `RouteDecided`) are *also* emitted forward via `emit_event` so projections see them in the canonical log from Phase 9 day-one. Phase 10's first commit deletes the Phase-8 log; a new Phase-9 ADR (`ADR-0002` under Phase 9) records the cutover schedule. **No double-recording confusion** because the canonical log is the *only* source projections consume; the Phase-8 log is a Phase-6/8-private append-only data structure that happens to be a *redundant* writer during Phase 9. [synth — answers critic-roadmap-1 and the [B] open question]

### 7. Payload-by-reference — `codegenie.events.blob_refs`

- **Provenance.** [P] Risk 5 · the [B]/[S] designs missed this entirely; critic flagged.
- **Purpose.** Activity inputs/outputs > 8 KiB do not enter Temporal history directly. They are written to `events.blob_refs` (BYTEA, BLAKE3-digest-keyed) and the activity sees a typed `BlobRef(digest, store_key)` in their place.
- **Interface.**
  ```python
  class BlobRef(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      digest: BlobDigest                          # newtype, BLAKE3 hex
      content_kind: BlobKind                      # ContextBundle | RepoSnapshotDelta | SandboxLog | ...
      byte_len: int

  @register_activity(name="write_blob_ref", timeout=timedelta(seconds=10))
  async def write_blob_ref(input: WriteBlobInput) -> BlobRef: ...

  @register_activity(name="resolve_blob_ref", timeout=timedelta(seconds=10))
  async def resolve_blob_ref(input: BlobRef) -> ResolveBlobOutput: ...
  ```
- **Internal design.** Workflow code never holds bytes; it holds `BlobRef`s. Each activity that needs bytes calls `resolve_blob_ref`; each activity that produces bytes calls `write_blob_ref`. `ContextBundle` (which Phase 8's hot views serialize at ~50–150 KiB) crosses as a `BlobRef` always — earns G8's 200-event history ceiling. [synth]
- **Tradeoffs.** Two extra activities per workflow. Bought back by history compactness; `temporal-ui` becomes legible because no payload exceeds a screenful.

### 8. Activity-boundary sanitization — `codegenie.durable.sanitizer`

- **Provenance.** [S] `RedactedWorkflowPayload.seal()` — but **narrowed**, after the critic showed regex-on-field-names is decorative.
- **Purpose.** Make it a *typed-level* error to return a secret-shaped value from an activity. Defense against the genuine A1 threat ("a naive activity that takes `GitHubToken` as an arg writes the token into history *forever*").
- **Interface.**
  ```python
  class RedactedActivityResult(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid")
      _sanitized: Literal[True] = True   # set only by .seal()

      @classmethod
      def seal(cls, model: T) -> "RedactedActivityResult": ...   # validates + scrubs
  ```
- **Internal design.**
  - **Type-level enforcement.** A fence test (`tests/fence/test_activity_payload_typing.py`) introspects every `@activity.defn`-registered function and asserts the return type is `RedactedActivityResult`-derived. An unsealed return is a type error (`mypy --strict`).
  - **Three-layer sanitization at seal time.** (a) Pydantic `extra="forbid"` rejects unknown fields; (b) **typed credential class blocklist** — any field whose declared type is `GitHubToken | LlmApiKey | MicroVmCredential | PostgresPassword` raises `SealError` (the [S]-design's regex-on-name was the critic's main attack; this *type-driven* check catches the threat properly); (c) value-shape regexes on `str` fields (`AKIA[0-9A-Z]{16}`, `ghp_[A-Za-z0-9]{36}`, JWT shape, `eyJ...`) as a backstop. Layer (b) is the load-bearing one. [synth — addresses critic-2 on [S]]
  - **`RedactionFired` event.** When (c) ever matches, a `RedactionFired(field_path, redaction_kind)` event is emitted — high signal, surfaces *every* contributor's accidental secret leak before it reaches history.
- **Scope.** Applied at the Activity → workflow-history boundary (return values from `@activity.defn` functions). **Not applied** at the workflow-input boundary in Phase 9 — workflow inputs are constructed by the CLI/Temporal-client, which is itself code we own; sealing at the input boundary doubles the cognitive cost without a corresponding threat. [synth — narrows [S]]
- **Where it lives.** `src/codegenie/durable/sanitizer.py`.

### 9. Worker process model — `codegenie.durable.workers`

- **Provenance.** [P] two-pool model (workflow worker + activity worker) · [synth] task queues by **workload class** not by every plugin tuple.
- **Purpose.** Run workflows + activities; the only thing Phase-9 deploys.
- **Internal design.**
  - **Two pools.**
    - **Workflow worker pool** — `Worker(workflows=[VulnRemediationWorkflow, MultiPluginParentWorkflow])`, IO-free, replay-cheap. Steady-state 250 MiB RSS at 50 in-flight workflows; cooperative async.
    - **Activity worker pools by task queue.** Phase 9 ships two queues: `vuln-remediation-node-npm` (the canonical workflow) and `system` (event-log writer + blob refs). Each is its own `Worker(activities=[...])` process. K8s ServiceAccount per pod scopes credentials. [synth — drops [S]'s N×M sprawl; keeps task-queue partitioning as the credential-segmentation primitive]
  - **Workflow-worker hot reload (dev only).** `uvloop` + `watchfiles`; one restart ~800 ms.
  - **`build_worker(...)` entrypoint.** Single function the dev CLI invokes via `python -m codegenie.durable.workers`.
- **Where it lives.** `src/codegenie/durable/workers/__init__.py`.

### 10. Local dev surface — `docker-compose.yml`

- **Provenance.** [B] one compose file with three services · [S] `127.0.0.1`-only ui · [P] worker processes on host, not in containers.
- **Services.**
  - `postgres:16-alpine` (Phase 9 + Phase 8 share it eventually; for Phase 9 it is Phase-9-private).
  - `temporalio/auto-setup:1.25` (Temporal server + its own Postgres tenancy).
  - `temporalio/ui:2.30` bound `127.0.0.1:8233`.
  - `redis:7-alpine` (Phase 8, unchanged).
- **`make dev-up` / `make dev-down`.** Mechanical; no LLM, no clever logic.
- **Tradeoffs.** `temporal auto-setup` and our `events` schema live in the same Postgres instance — three schema owners, written down in the alembic README and CI-asserted no-touch.

### 11. Projections — `codegenie.events.projections`

- **Provenance.** [B] one-file-per-projection registry · [synth] **no stubs**; ADR-0043 cleanliness.
- **Phase-9 projections.** Three real ones, zero stubs.
  - `audit_trail(workflow_id)` — the chronological event list. Pays the rent on the replay machinery.
  - `retry_histogram` — `GateOutcome × failing_signals` rollup. Direct fold over the canonical log.
  - `plugin_telemetry` — `PluginResolved × MergeOutcome` joins for per-plugin merge / fallback rate. Replaces the projection role Phase 8's plugin-events log filled.
- **No `cost_ledger_v1` stub.** The critic was right that a stub raising `NotImplementedError` is a silent-edit-reservation. Phase 13 lands `cost_ledger` *additively* — a new file, new test, new entry in the registry. The Phase-9 events (`LlmInvoked.cost_usd`, `BudgetExhausted`) already carry the data Phase 13 needs to fold. [synth — addresses critic-5 on [B]]
- **Interface.**
  ```python
  class Projection(Protocol):
      name: ProjectionId
      def fold(self, events: Sequence[EventPayload]) -> ProjectionState: ...

  def register_projection(name: ProjectionId) -> Callable[[type[Projection]], type[Projection]]: ...
  ```
  Registry-collision-at-import: a `TypeError` raised at module import (same shape as `@register_probe`). Phase 13's `cost_ledger` is a new name; no collision risk.
- **Each projection is a pure fold.** No Postgres needed for unit tests; fixture event streams drive every test.

### 12. Alembic discipline — `src/codegenie/events/alembic/`

- **Provenance.** [S] supply-chain discipline; [B] one alembic directory.
- **Internal design.**
  - Owns the `events` schema only.
  - `tools/alembic-revisions.lock` SHA-pins every migration file.
  - `migrations_role` has DDL on the `events` schema, no DML on application tables, **no `CREATE EXTENSION`** (allowlist = `{pg_stat_statements}` only — `pgcrypto` is no longer needed since column-encryption is dropped).
  - CI step: run every migration against a fresh Postgres, dump schema, diff against `tests/fence/alembic_schema.sql.snapshot`.
  - **Runtime-side-effect attack** (critic-3 on [S]): a `migrations_role` that cannot read application data cannot exfiltrate. The role's `SELECT` permission is *restricted to the `events` schema's own metadata only*, no `events.events.payload` access. A `CREATE FUNCTION ... LANGUAGE plpython3u` migration that tries to read events fails at runtime — `plpython3u` requires superuser; `migrations_role` is not super.

## Data flow

End-to-end warm-cache recipe-route, single-workflow, no human pause:

```
1. CLI invokes      → temporal_client.start_workflow(VulnRemediationWorkflow, request)
                      [<10 ms]

2. Workflow worker  → workflow body runs; emits WorkflowStarted via emit_event activity
                      (batched, ~1ms enqueue)

3. Workflow worker  → execute_activity("resolve_plugin", input)
                      [Zone 3 → Zone 2; activity worker on vuln-remediation-node-npm queue]
                      → emits PluginResolved (batched)

4. Workflow worker  → execute_activity("build_bundle", resolution)
                      → wraps Phase-8 BundleBuilder.build; result > 8 KiB → write_blob_ref;
                      → returns BlobRef in the activity result.
                      → emits BundleBuilt (batched)

5. Workflow worker  → execute_activity("route", bundle_ref)
                      → wraps Phase-8 planner.route; returns RouteDecision (recipe-route)
                      → emits RouteDecided (batched — NOT synchronous, contra [P])

6. Workflow worker  → execute_activity("run_vuln_subgraph", input_ref)
                      → Phase-6 LangGraph subgraph runs INSIDE this one activity to terminal.
                      → recipe applies; sandbox builds; trust gate runs.
                      → emits TrustGatePassed (batched), RecipeApplied (batched), PatchApplied (batched)
                      → returns SubgraphCompleted(patch_ref, evidence_ref)

7. Workflow worker  → execute_activity("github_open_pr", patch_ref, evidence_ref)
                      → emits PrOpened (batched)
                      → workflow.wait_condition(state is not Running)  ← parks on signal

8. Days later:      → human_review_decision signal arrives
                      → workflow advances to Completed
                      → emits MergeOutcome (SYNCHRONOUS — @critical_event)
                      → workflow exits, emits WorkflowCompleted (batched)

Totals:
  Temporal history records: ~14 (well under 200 worst-case)
  Events to Postgres: ~12 (1 synchronous, 11 batched)
  Postgres roundtrips on hot path: 1 sync (MergeOutcome) + 1 batch (12 events in one COPY)
  Tokens spent: 0 (recipe-route, cassette-replay)
  Wall-clock excluding sandbox: ~3 s
```

`MultiPluginParentWorkflow` differs at step 2 only: it spawns N child `VulnRemediationWorkflow`s via `workflow.execute_child_workflow`, awaits them all, aggregates into `ParentResult`.

## Failure modes & recovery

| Failure | Detected by | Containment | Recovery | Source |
|---|---|---|---|---|
| Activity worker SIGKILL mid-`run_vuln_subgraph` | Temporal heartbeat timeout (30 s) | Activity is idempotent by `attempt_id`; recipe/sandbox steps content-addressed | Temporal re-dispatches to another worker; LangGraph subgraph resumes from Phase-6 `PostgresSaver` checkpoint inside the new activity. | [P]/[B] |
| Workflow worker dies | Temporal sticky-task affinity expires (1 min) | Workflow state is in history + checkpointer | Another worker replays history; resumes at next Activity invocation. **Exit-criterion test.** | [P]/[synth] |
| Postgres unavailable (event-log writer) | `psycopg.OperationalError` in `emit_event` | EventBatchWriter accumulates up to 16 MiB; worker refuses graceful shutdown until drained; over the cap → back-pressure into Temporal | Synchronous-flush events (`MergeOutcome`, `BudgetExhausted`, ...) propagate the error to caller; Temporal retries; non-critical events buffer in memory | [P] |
| Per-workflow chain break (poisoned event row from compromised `application_role`) | Per-workflow BLAKE3 chain verify at projection time emits `ChainTamperDetected` (@critical_event) | Compromised worker can only INSERT, not UPDATE/DELETE — chain forces forge of every later row in *that workflow*, none in others | Halt projections for the affected workflow; forensic review reconstructs; the chain-scope-per-workflow means blast radius is one workflow | [S] narrowed by [synth] |
| Workflow non-determinism after a code change | Temporal `NondeterminismError` on replay; CI `Replayer`-based test catches first | Workflow fails with the error | Workflow reset to pre-change checkpoint; fix and redeploy | [B]/[S] |
| `MultiPluginParentWorkflow` child fails | Temporal child-workflow `WorkflowFailureError` to parent | Parent's `ParentResult` reflects per-child outcome (`SomeMerged | AllFailed`) | Parent decides per ADR-0042 sequencing (Phase 10 will exercise; Phase 9 just models the typed shape) | [synth] |
| Temporal cluster unavailable | `ServiceUnavailableError` | In-flight workflows pause (no state loss — they're on disk) | Workflows resume as cluster returns | [P]/[B] |
| `langgraph-checkpoint-postgres` upstream schema bump | `psycopg.ProgrammingError` on resume | Pinned in `pyproject.toml`; CI-tested upgrades | Manual migration; ADR amendment | [B] Risk 2 |
| Phase-6 SQLite-backed workflow during cutover | Phase-9 worker reads `checkpointer = SqliteSaver` from the workflow's stored config | New workflows start on Postgres; SQLite-backed workflows drain on Phase-6 checkpointer | Drain-don't-cutover policy (Phase-9 ADR-0001) | [synth — addresses critic-roadmap-2] |
| Activity returns unsealed payload (contributor error) | `mypy --strict` + `tests/fence/test_activity_payload_typing.py` | Build break | Re-write activity to seal; or declare exemption (none ship) | [S] |
| Secret-shape regex misses a novel shape | `RedactionFired` does not fire; payload enters history | Typed-credential blocklist (sanitizer layer b) catches by declared type, not by value pattern | Weekly canary scan over recent history for known shapes; regex updated; emit ADR amendment for the new shape | [S] R1, narrowed |

## Resource & cost profile

- **Tokens per run.** Recipe-route $0.00; RAG-route ≤ $0.02; LLM-route Phase-4-bounded. Phase 9 adds **zero** LLM calls.
- **Wall-clock (p50/p95 recipe-route warm, no human pause).** p50 ≈ 4 min, p95 ≈ 8 min — dominated by sandbox build (2–8 min); Temporal overhead < 2%. [P]
- **Memory per worker.** Workflow worker: ~250 MiB at 50 in-flight. Activity worker (vuln queue): ~400 MiB cold; spikes to ~1.5 GiB during sandbox build. System worker: ~150 MiB.
- **Storage growth at 1k workflows/day.** Events: ~12 events × ~1 KiB JSONB × 1 k/day = ~12 MiB/day. Blob refs: ~3 × 50 KiB × 1 k/day = ~150 MiB/day. Workflow history: ~14 events × ~2 KiB × 1 k/day = ~28 MiB/day. Checkpointer: ~32 MiB/day. **Total: ~220 MiB/day**. Annual: ~80 GiB. ADR-0040 retention (365 d for audit-class) is the controlling policy — single Postgres instance is comfortable.
- **Append-throughput ceiling.** Per-workflow chain ⇒ concurrent workflows append in parallel; per-workflow appends are serial by design. At ~12 events/workflow × 200 concurrent workflows × ~1/sec emission per workflow = ~2.4 k/sec effective. Headroom to G6's 3 k/sec.
- **Cost of controls (vs an unfenced baseline).** Sanitizer + capability + per-workflow chain + payload-by-reference adds ~5% wall-clock and ~10% LoC vs. an unfenced "just call activities" design. Bought back by audit-completeness + tamper-evidence + history compactness.

## Test plan

### Unit (fast)
- Activity bodies: vanilla pytest, mock side-effects, assert (a) typed event emitted with right capability, (b) Pydantic round-trip, (c) idempotent in `attempt_id`. One test file per activity.
- Projections: pure fold over fixture event streams; no Postgres. Property test: `fold(events) == fold(events)` (idempotent), `fold(shuffle_within_equal_ts(events)) == fold(events)`.
- Sanitizer: property tests on `seal()` — `seal(seal(x)) == seal(x)`; constructed adversarial inputs over every known secret shape and every typed credential class.
- Event variant round-trip: hypothesis-generated `EventPayload` instances, JSON round-trip via discriminated-union `TypeAdapter`.

### Workflow-level (`WorkflowEnvironment`)
- `VulnRemediationWorkflow` happy path with mocked activities. Asserts state transitions follow `VulnLedger` sum type.
- `MultiPluginParentWorkflow` happy path with 2 children. Asserts `ParentResult.AllMerged` aggregation.
- HITL pause/resume via `human_review_decision` signal. Asserts state machine reaches `Completed` after resume.

### Replay-determinism (CI-gating)
- `tests/workflows/test_replay_determinism.py` — record a workflow history once, then `Worker.run_replay_workflows(...)` against the recorded history; any non-determinism is a build break. Includes a per-Python-minor-version matrix (3.11 + 3.12).
- AST fence `tests/fence/test_workflow_determinism.py` over `src/codegenie/durable/workflows/`.
- `import-linter` contract over the workflow source set.

### Durability (the exit criterion)
- `tests/durability/test_kill_worker_resume.py` — start workflow, advance to mid-`run_vuln_subgraph`, `os.kill(worker_pid, SIGKILL)`, restart worker, assert workflow reaches byte-identical terminal `VulnLedger`. Property: same final state across N kill offsets. **In `make test`, not behind `@pytest.mark.e2e`.** [synth — answers [B] open question 5; this is the exit criterion, it must run on every PR]
- `tests/durability/test_temporal_cluster_restart.py` — kill the dev Temporal cluster mid-workflow, restart, assert resume.
- `tests/durability/test_sut_digest_invariance.py` — for every Phase-6 canonical test case: run via `LocalVulnRemediationSut` (in-process), run via `TemporalVulnRemediationSut`, assert `digest_a == digest_b`. **G5 verification.**

### Integration (`testcontainers`)
- `tests/integration/test_workflow_e2e_postgres.py` — real Postgres, real Temporal dev server, fake Redis, cassette-replay LLM. Full recipe-route workflow end-to-end. ~30 s.
- `tests/integration/test_per_workflow_chain.py` — append 100 events across 3 concurrent workflows, assert each workflow's chain is internally consistent and independent of the others.
- `tests/integration/test_blob_ref_roundtrip.py` — write 200 KiB blob, resolve, verify digest.

### Adversarial (`tests/adv/`)
- `test_events_append_only_enforcement.py` — `application_role` cannot UPDATE/DELETE/TRUNCATE.
- `test_event_chain_tamper_detection.py` — forge a row via `migrations_role` (test setup), assert projection detects the per-workflow chain break.
- `test_secret_leakage_in_history.py` — construct an activity input/return with each known secret shape, assert seal rejects.
- `test_typed_credential_blocklist.py` — construct an activity with a `GitHubToken`-typed return, assert seal raises.
- `test_alembic_revision_lock.py` — every file in `alembic/versions/` has a SHA in `tools/alembic-revisions.lock`.
- `test_alembic_schema_snapshot.py` — run migrations, diff against snapshot.
- `test_temporal_ui_loopback.py` — grep for `0.0.0.0` in scripts; assert none.
- `test_capability_token_scope.py` — `vuln-remediation-node-npm` worker cannot mint `EventLogWriteCapability` for kinds outside its allowlist.
- `test_worker_credential_blast_radius.py` — simulate compromised worker; assert four privileged actions on other-queue workflows fail.

### Perf canaries (`-m bench`, nightly)
- `test_phase09_throughput.py` — 100 cassette-replay workflows on 5 activity workers. Ratchet baseline; CI fails if throughput drops > 10%.
- `test_phase09_event_log_append.py` — 10 k events across 50 concurrent workflows, assert p95 ≤ 15 ms.
- `test_phase09_token_canary.py` — `total_tokens == 0` across the cassette-replay throughput run.

## Design patterns applied

| # | Pattern | Where in Phase 9 | What it buys |
|---|---|---|---|
| 1 | **Functional core / imperative shell** | Workflow body (orchestration, no I/O); projection folds (pure); sanitizer `seal()` (pure). | Replay-safety on the workflow; testability without Postgres on projections; type-level "did you redact?" on sanitizer. |
| 2 | **Tagged union / sum type for state** | `VulnLedger` (Phase 6, intact); `EventPayload` (discriminated union); `SupervisorDecision.MultiPluginDispatch | Dispatched | EscalatedToHITL` (Phase 8, threaded through); `ParentResult = AllMerged | SomeMerged | AllFailed`. `match` + `assert_never` everywhere. | Exhaustive handling at compile time; new variants are additive; illegal states unrepresentable. |
| 3 | **Newtype for domain identifiers** | `WorkflowId`, `EventId`, `BlobDigest`, `AttemptId`, `CorrelationId`, `WorkflowSeq`, `PluginId` (Phase 8). | A `WorkflowId` confused with a `RepoId` is a compile-time error; the workflow threads four IDs simultaneously, exactly the pattern's home turf. |
| 4 | **Smart constructor** | `RedactedActivityResult.seal(model)`; `BlobRef` is created only by `write_blob_ref`; `EventLogWriteCapability` minted only by the worker bootstrap. | Construction path is the validation path; "unsealed return" is a type error. |
| 5 | **Adapter pattern (genuine, not forwarder)** | `PostgresCheckpointerAdapter` (adds `health()` translation over upstream `PostgresSaver`); `TemporalVulnRemediationSut` (adapts Phase-6's `VulnRemediationSut` Protocol to the Temporal substrate). | Single-implementation, but each *translates* — answers the critic's "forwarder" attack on [B]. |
| 6 | **Registry pattern** | `@register_activity`, `@register_projection`, `@critical_event`. Same shape as `@register_probe` from Phase 0. | Adding a new activity / projection / critical event is one file + one decorator + one import. Same mental model across phases. |
| 7 | **Event sourcing for agent runs** | Canonical Postgres event log + per-workflow BLAKE3 chain; Temporal workflow history as the workflow-internal store; projections as the read path. | ADR-0034 mandates the hybrid. Phase 11 / Phase 13 become projections additively. |
| 8 | **Open/Closed via `@critical_event` decorator** | Synchronous-flush vocabulary is a *decorator-defined registry*, not a hardcoded if-chain. | New critical events in future phases are one decorator line; the writer code does not change. Answers [P] open question 2. |
| 9 | **Capability pattern (process-level, not cryptographic)** | `EventLogWriteCapability`, `PrOpenCapability`, `LlmSpendCapability` — typed Pydantic records threaded explicitly. Trust root is the *worker mount*, not the HMAC. | Critic's correct attack on [S] HMAC-tokens accepted: the security primitive is task-queue partitioning + K8s ServiceAccount, not cryptographic non-forgeability. The Capability type is the auditable seam. |

### Patterns considered and deliberately rejected
- **`TemporalPort` / durable-execution abstraction.** No second substrate in sight; ADR-0003 says "Reversibility: high cost" — but a Port with one implementation is premature pluggability (toolkit anti-pattern). Document the reversibility cost in the ADR, do not pre-pay.
- **Per-activity microVM for credential isolation.** Capability tokens + per-task-queue credentials are cheaper and more precise. microVMs are for *untrusted code execution* (Phase 5 gate), not *trusted credential-holding*.
- **Workflow-history encryption via Temporal-cluster-side codec.** Codec key has to live somewhere; centralizing it makes the codec a single point of compromise. Sealing at the type boundary (G8 + sanitizer) keeps secrets *out of history*, which is strictly better than "in history but encrypted."
- **`pgcrypto` column-encryption on `events.payload`.** Critic-5 on [S] is decisive: every projection holds the decryption key, so the encryption is decorative against the only read path. Delegated to volume-layer encryption (TDE/LUKS) — out of Phase-9 scope.
- **`cost_ledger_v1` Phase-13 stub.** ADR-0043 violation; Phase 13 lands additively when it lands.
- **`ContextVar`-backed `record_event`.** Critic showed [B]'s `__all__`-discipline is unsound. Explicit capability-threading is the only safe pattern across the workflow/activity boundary.
- **Specification pattern for `non_retryable` exception classification.** A `tuple[type[Exception], ...]` is small enough that pattern-introducing a Specification adapter would be ceremony.

### Anti-patterns avoided
- Untyped `dict[str, Any]` at activity boundaries (mypy + fence catches it).
- Side effects in module import (registries are dicts populated lazily on first decorator invocation; `__init__.py` only imports modules).
- Boolean flags on workflow state (`is_running: bool, is_paused: bool` is the `VulnLedger` sum type's job).
- Strategy with single implementation (no `CheckpointerStrategy` interface — `LangGraphCheckpointerPort` is an Adapter port for upstream-class wrapping).
- Forwarder Adapter (the `PostgresCheckpointerAdapter` adds genuine `health()` translation).
- Stubs that raise `NotImplementedError` for future phases (Phase 13's `cost_ledger` lands additively).
- Cross-workflow side-channels in workflow history (per-workflow BLAKE3 chain ensures no cross-workflow ordering smuggling).
- Capability passed through 10 frames as a parameter (max 3 frames: worker → activity wrapper → side-effect site).

## Risks (top 5)

1. **`run_vuln_subgraph` activity timeouts on a 20-minute Phase-6 SHERPA run.** The activity timeout is 20 minutes; a slow sandbox build + retry burst could blow it. **Mitigation:** heartbeat every 5 s lets Temporal detect the activity is *alive* even when slow; the activity emits `ActivityProgress` heartbeats so the human-facing `temporal-ui` shows progress. If the 20-min cap is hit, the activity becomes resumable via Temporal's continue-as-new pattern (out of scope to ship in Phase 9 — Phase 10 may need it).
2. **`langgraph-checkpoint-postgres` upstream churn.** Young package; a schema change between Phase 9 and Phase 11 would break in-flight Phase-6/7 workflows. **Mitigation:** pin in `pyproject.toml`; CI tests upgrade by running every shipped fixture workflow on the new pin before merge.
3. **The per-workflow chain leaves portfolio-level events unchained.** Portfolio events (`workflow_id IS NULL`) form their own chain, but cross-workflow tampering between two workflows' chains is undetectable (an attacker who can INSERT into both *can* fake "this happened" for either, just not modify either chain's interior). **Mitigation:** the threat model is "compromised `application_role`"; that role's INSERT-only privilege limits the attack to forward additions, not retroactive rewrites — the critic's "forge a row in the middle" attack is *impossible* without `migrations_role`. Phase 13 may add a periodic cross-workflow snapshot signed by `read_role` if portfolio-level tamper-evidence becomes a real concern.
4. **`SutDigest` invariance hinges on Phase-6 builder behaving identically in-process vs. inside an Activity.** `temporalio`'s asyncio loop is the same loop the Phase-6 builder runs on, but `workflow.now()` is not available inside an Activity (it's a workflow-only primitive). Phase-6's checkpointer does `datetime.now()` directly — which makes its `SutDigest` non-deterministic in the *original* Phase-6 design, and the invariance test G5 must use a frozen-clock fixture. **Mitigation:** the G5 test uses `freezegun` (or `temporalio.testing` time-skipping for the Temporal side); the comparison is at the recorded-evidence-digest level, not raw timestamps.
5. **The Phase-8 `codegenie.plugins.events` → canonical events cutover is a one-shot.** Phase 10's first commit deletes the Phase-8 log; any Phase-8/9 workflow that hasn't drained by then is stranded on a removed log. **Mitigation:** ADR-0002 under Phase 9 records a 30-day drain window; a CI canary asserts no Phase-8-log-only workflow is in flight before the deletion PR can land.

## Synthesis ledger

### Vertex count
- Performance [P]: 38 atomic vertices (architecture: 6; goals: 7; components: 7; data-flow: 4; failure: 7; tests: 7).
- Security [S]: 47 atomic vertices (threat-model: 8 assets + 10 adversaries + 9 surfaces; goals: 10; components: 10; data-flow: 5; failure: 12).
- Best-practices [B]: 31 atomic vertices (conventions: 7; goals: 5; components: 7; data-flow: 8; failure: 8; patterns: 6).
- **Total: 116 input vertices.** Synthesis selected ~52 across the three, modified or replaced ~18, introduced ~12 new synthesis vertices.

### Edges (AGREE / CONFLICT / COMPLEMENT / SUBSUME counts)
- **AGREE: 11** (Postgres = checkpointer + event log substrate; Pydantic-typed events; `frozen=True, extra="forbid"`; `match` + `assert_never`; one `make dev-up`; activity bodies do I/O, workflow body is pure; payload-by-reference is the *right answer for large bytes* — even though [B] missed it; Temporal-history is canonical for workflow-internal; one alembic directory; Phase-9 = local-dev shape; LangGraph stays in the runtime; `langgraph-checkpoint-postgres` is the chosen lib).
- **CONFLICT: 14** (workflow body composition · event-log integrity story · synchronous-flush vocabulary · worker process model · event variant count · checkpointer serialization · temporal-ui exposure · `record_event` mechanism · BLAKE3 chain scope · capability-token signing primitive · pgcrypto encryption · `cost_ledger_v1` stub · two-database vs one · per-task-queue isolation strategy).
- **COMPLEMENT: 8** ([P] payload-by-reference + [S] sanitizer + [B] `frozen=True` are three orthogonal disciplines, all applied; [P] task-queue-by-workload + [S] task-queue-by-task-class are partially-resolved by [synth] task-queue-by-workload-class-with-credential-scoping; [B] registry + [S] capability-tokens compose; [P] batched-writer + [S] per-workflow chain compose).
- **SUBSUME: 4** ([B]'s `forbidden-patterns` regex SQL-string ban is subsumed by [S]'s `REVOKE UPDATE/DELETE` + trigger; [P]'s `EventTypeRegistry` is subsumed by [B]'s discriminated-union + Pydantic `TypeAdapter`; [P]'s `WorkflowHistoryFanout` Activity is subsumed by `emit_event`'s explicit-emission discipline; [S]'s `SearchAttribute` allowlist is subsumed by deferring SearchAttributes to Phase 13.5 operator portal).

### Conflict-resolution table

Scores (0–3 each): Phase exit-fit · Roadmap-fit · Commitments-fit · Critic-fit · Pattern-fit · **Sum**.

| Dimension | [P] picks | [S] picks | [B] picks | Winner | Exit | Road | Commit | Critic | Pattern | Sum |
|---|---|---|---|---|---|---|---|---|---|---|
| Workflow body composition | Workflow body *is* the Phase-6 graph; each node = Activity | Workflow envelope only; whole graph in one Activity | Workflow body + 1:1 LangGraph-node-to-Activity mapping | **[S] (modified)** — whole Phase-6 graph in `run_vuln_subgraph`, Phase-8 Supervisor's 3 nodes mapped 1:1 | 3 | 3 | 3 | 3 | 2 | **14** |
| Event-log integrity | BYTEA + msgpack + no chain | JSONB + pgcrypto + global BLAKE3 chain | JSONB + plain INSERT, no chain | **[synth]** — JSONB + per-workflow BLAKE3 chain, no pgcrypto | 3 | 3 | 3 | 3 | 3 | **15** |
| Synchronous-flush vocabulary | Hardcoded 4 events (incl. `RouteDecided` — critic broke this) | Implicit per-event (chain semantics) | No batching discussion | **[synth]** — `@critical_event` decorator-defined registry of 5 events; `RouteDecided` is *not* critical | 3 | 2 | 3 | 3 | 3 | **14** |
| Worker process model | One pool, 4 task queues by workload class | One process per `task_class×lang×build_system` (12+) | One process for everything | **[P] (narrowed)** — 2 queues in Phase 9 (`vuln-remediation-node-npm` + `system`), expandable by addition | 3 | 3 | 2 | 3 | 2 | **13** |
| Event variant count | ~12 variants incl. fanout-only | Many security-shaped (`RedactionFired`, `EventChainBreak`, ...) | Exactly 5 + stub | **[synth]** — 21 variants covering all phases' critical paths, no stubs | 2 | 3 | 3 | 3 | 3 | **14** |
| Checkpointer serialization | Pydantic JSON envelope + msgpack inner | Two logical DBs + TDE + pgcrypto | Direct delegation to upstream `PostgresSaver` | **[B]** — direct upstream delegation, shared pool | 3 | 3 | 3 | 2 | 3 | **14** |
| Capability-token signing | (not addressed) | HMAC-signed Pydantic records | (not addressed) | **[synth]** — typed Pydantic records, no HMAC; trust root = worker mount + task-queue identity | 2 | 2 | 3 | 3 | 3 | **13** |
| `temporal-ui` exposure | "Default on" in `make dev-up` | Loopback-only forever; wrapper rejects 0.0.0.0 | docker-compose, no auth, dev-only | **[S]** — `127.0.0.1:8233` only, wrapper script enforces; operator portal (Phase 13.5) owns prod | 3 | 3 | 3 | 3 | 2 | **14** |
| `record_event` mechanism | Per-workflow-batch via `EmitEventsBatch` Activity | `EventLogActivity` with capability | `ContextVar` (critic showed unsound) | **[synth]** — explicit `EventLogWriteCapability` through `emit_event` Activity on `system` queue | 3 | 3 | 3 | 3 | 3 | **15** |
| Activity sanitizer | (not addressed) | Regex-on-field-names + value-regex (critic broke regex) | (not addressed) | **[synth]** — typed-credential-class blocklist + value-shape regex backstop | 2 | 2 | 3 | 3 | 3 | **13** |
| BLAKE3 chain scope | (no chain) | Global serial chain across all events | (no chain) | **[synth]** — per-workflow chain; portfolio events form their own | 3 | 3 | 3 | 3 | 3 | **15** |
| `cost_ledger_v1` stub | `cost_ledger_mv` materialized view | Implicit in audit story | Stub raising `NotImplementedError` | **[synth]** — no stub; Phase 13 lands additively | 3 | 3 | 3 | 3 | 3 | **15** |
| Phase-6 SQLite cutover | Open question; defer to synthesizer | (not addressed) | "Keep default = InMemory for back-compat" | **[synth]** — drain-don't-cutover; ADR-0001 Phase-9 | 3 | 3 | 3 | 3 | 2 | **14** |
| `MultiPluginDispatch` shape | "Smaller parent workflow" mentioned in passing | (not addressed) | (not addressed) | **[synth]** — real `MultiPluginParentWorkflow` with child workflows | 3 | 3 | 3 | 3 | 3 | **15** |

Cumulative weight chose [synth] picks 8 times, [S] 2, [P] 1, [B] 1, [S] (modified) 1, [P] (narrowed) 1.

### Shared blind spots considered
1. **No `TemporalPort`.** All three declined to introduce one; critic flagged premature-pluggability risk *and* substrate-swap risk. **Disposition:** synthesis follows [P]/[B]/[S] consensus — no Port. The reversibility cost is documented in the implied ADR-0003 amendment ("substrate swap is a multi-phase rewrite — known cost, acknowledged at Phase-3 acceptance time, not Phase-9-time to revisit").
2. **`langgraph-checkpoint-postgres` upstream stability.** All three assume stability; critic was right that schema bumps will happen. **Disposition:** synthesis pins the version in `pyproject.toml` and ships a migration test that runs every fixture workflow on the new pin before merge. Risk #2 above.
3. **Replay-determinism fences catch literal `time.time()`, not transitive non-determinism through LangGraph version drift.** All three describe AST walkers; none catch LangGraph 0.4→0.5 iteration-order changes. **Disposition:** synthesis adds the `Replayer`-based replay test on every PR (CI-gating); pins LangGraph version; the transitive-drift attack is caught at the *replay* layer, not the *static-analysis* layer.

### Pattern reconciliation

| Pattern | Where it appeared | Synthesis disposition | Rationale |
|---|---|---|---|
| Hexagonal / Ports & Adapters | [P] `LeafLlmPort`, `CheckpointerPort`, `EventLogPort` · [S] Sandbox port preserved · [B] explicit rejection as a Phase-9 introduction | **Kept selectively** — `LangGraphCheckpointerPort` (one upstream adapter target) + the Phase-4 `LeafLlmPort` (intact); no new Phase-9 ports invented. | Single-impl ports are premature; the two we keep wrap genuinely external libraries. |
| Functional core / imperative shell | All three | **Kept fully** — workflow body, projections, `seal()` are pure; activities are the shell. | The discipline is the test seam. |
| Tagged union / sum type | All three | **Kept and extended** — `VulnLedger` (intact); `EventPayload` (21-variant discriminated union); `SupervisorDecision` (Phase 8, threaded); `ParentResult` (new). | ADR-0033 mandates; the new `ParentResult` variant came from `MultiPluginDispatch` modeling. |
| Newtype | All three | **Kept** — adds `BlobDigest`, `WorkflowSeq`, `AttemptId`, `EventLogWriteCapability`. | ADR-0033 mandates. |
| Smart constructor | [S] `RedactedWorkflowPayload.seal()` · [B] `BundleProvenance` (Phase 8) | **Kept and renamed** — `RedactedActivityResult.seal()` (narrower scope than [S]'s); `BlobRef` only minted by `write_blob_ref` activity. | Critic's attack on [S] regex-on-names absorbed; typed-credential blocklist is the load-bearing check. |
| Adapter pattern | [P] `Codec` (msgpack+JSON) · [S] Sandbox port · [B] `PostgresCheckpointerAdapter` (forwarder per critic) | **Reformed** — `PostgresCheckpointerAdapter` adds `health()` translation; `TemporalVulnRemediationSut` translates Phase-6 Protocol to Temporal runtime; `Codec` rejected (two formats at one boundary, CLAUDE Rule 7). | Adapter must translate, not forward. |
| Registry pattern | All three | **Kept** — `@register_activity`, `@register_projection`, `@critical_event`. | Same shape as `@register_probe`. |
| Event sourcing | All three | **Kept and corrected** — per-workflow chain, not global; no encryption; no Phase-13 stubs. | Canonical primitive per ADR-0034; critic forced the per-workflow scope. |
| Capability pattern | [S] HMAC-signed records | **Kept, demoted from cryptographic** — typed Pydantic records threaded explicitly; trust root is the worker mount, not HMAC. | Critic's correct attack on [S]: in-process HMAC is forgeable by anyone with the worker mount. |
| Open/Closed via decorator | [P] open question (chose closed list) · [B] implicit | **Decorator-defined registry chosen** — `@critical_event`. | Adding a critical event in Phase 13 is one line; the writer code does not change. |
| Strategy pattern | [B] explicit rejection for "checkpointer backend" | **Rejected** — single-impl Strategy is premature pluggability. | Toolkit anti-pattern. |
| Specification pattern | None | **Considered, rejected** — `non_retryable` tuple is small enough not to need it. | Premature abstraction. |
| Command pattern | [S] DP5 "Command for privileged activities" | **Rejected** — Temporal's `@activity.defn` *is* the Command; layering ours adds ceremony. | Critic's "wrap Adapter that returns unchanged class" attack also applies to wrapping Temporal's own Command. |

### Departures from all three inputs
1. **Workflow body composition asymmetry.** Phase-6 SHERPA subgraph runs inside *one* `run_vuln_subgraph` activity ([S]-shape) while Phase-8 Supervisor's three nodes map 1:1 to activities ([P]/[B]-shape). Earned by `SutDigest` invariance (G5) and Phase-8's explicit "this is the Temporal-Activity seam" design.
2. **Per-workflow BLAKE3 chain, not global.** Kills [S]'s serial-bottleneck without losing tamper-evidence inside each workflow.
3. **No `pgcrypto` column encryption.** Critic-5 on [S] decisive; encryption decorative against the projection path.
4. **No capability-token HMAC.** Trust root is task-queue partitioning + K8s ServiceAccount, not cryptographic non-forgeability. Critic correct on [S].
5. **`MultiPluginParentWorkflow` as a real second workflow class.** None of the three designed it; ADR-0042 requires it; Phase-8's `MultiPluginDispatch` decision variant is unmoored without a Temporal-side implementation.
6. **21 event variants in Phase 9.** [B]'s 5 is too few (critic broke the projection-additivity story); [P]'s sprawl is too many. The 21 are exactly the set the downstream phases (10/11/13) need to consume *additively*, no re-shaping.
7. **No `cost_ledger_v1` stub.** ADR-0043 cleanliness; Phase 13 lands additively.
8. **Two task queues in Phase 9, not twelve.** Critic-4 on [S] forced the scale-back; the security primitive (task-queue partitioning) is preserved.
9. **Drain-don't-cutover for Phase-6 SQLite.** None of the three named the transition; new ADR records it.
10. **`emit_event` is an Activity on the `system` task queue, capability threaded explicitly — not a `ContextVar`-backed helper, not a fanout listener.** Critic-1 on [B] and [P] both forced this resolution.

## Exit-criteria checklist

- [x] **Workflows survive process restarts without state loss.** Component: `VulnRemediationWorkflow` + `PostgresCheckpointerAdapter` + Temporal workflow history. Verified by `tests/durability/test_kill_worker_resume.py` (runs in `make test`).
- [x] **`temporal-ui` shows live workflow inspection.** Component: docker-compose `temporalio/ui:2.30` bound `127.0.0.1:8233`; `scripts/temporal-dev.sh` wrapper.
- [x] **All retries are framework-level — application code contains no retry loops.** Enforcement: `import-linter` + `forbidden-patterns` regex over `src/codegenie/durable/workflows/*.py`; per-activity `RetryPolicy` table in `codegenie.durable.activities.retry_policies`.

Additional roadmap-anchor criteria:
- [x] **Canonical event log lands operationally.** Component: `codegenie.events` + `events.events` table + per-workflow BLAKE3 chain + three projections (`audit_trail`, `retry_histogram`, `plugin_telemetry`). ADR-0034 satisfied.
- [x] **`SutDigest` invariance preserves Phase-6 harness.** Component: `TemporalVulnRemediationSut` adapter + `run_vuln_subgraph` single-activity bridge. G5.
- [x] **`MultiPluginDispatch` (ADR-0042) modeled as a real Temporal workflow.** Component: `MultiPluginParentWorkflow` + child-workflow dispatch. Phase 10 consumes additively.

## Load-bearing commitments check

Per `docs/production/design.md` §2:

- **§2.1 — No LLM in the gather pipeline.** Workflow code has no LLM imports; activities call the existing `LeafLlmPort` (Phase 4) inside `plan_with_llm_fallback`. The `fence` job extends to `codegenie.durable.workflows` and `codegenie.events` source sets. ✓
- **§2.2 — Facts, not judgments.** Every event variant records what happened (`RecipeApplied(patch_digest=...)`, `LlmInvoked(tokens=...)`), never a conclusion. Projections compute their judgments from typed facts. ✓
- **§2.3 — Honest confidence.** `WorkflowResumed(retry_count)` and `TrustGateFailed(retry_count)` surface retry history; projections don't hide it. `IndexHealthProbe` discipline extended to "every workflow's chain is verified at projection read time" (`ChainTamperDetected` is `@critical_event`). ✓
- **§2.4 — Determinism over probabilism for structural changes.** Workflow body is deterministic by fence (G4); LangGraph subgraph runs in the Activity (imperative shell) where non-determinism is fine. ✓
- **§2.5 — Extension by addition.** Phase 10/11/13 add new event variants (additive); new task queues (additive); new projections (additive). The five `@critical_event` events form a closed registry extended by decorator. No silent edits — `import-linter` + AST fence + alembic schema snapshot catch them. ✓
- **§2.6 — Organizational uniqueness as data, not prompts.** N/A for Phase 9 (no prompts; no skills changes).
- **§2.7 — Progressive disclosure.** `BlobRef` payload-by-reference *is* progressive disclosure at the workflow-history layer; G8 caps history-record size. ✓
- **§2.8 — Humans always merge.** Workflow can `github_open_pr` but **no** `github_merge_pr` activity exists. A fence test (`tests/fence/test_no_merge_activity.py`) asserts no activity name matches `merge_pr|approve_pr|self_merge`. Critic-roadmap-3 on §2.8 addressed. ✓
- **§2.9 — Cost is observable end-to-end.** `LlmInvoked(tokens, cost_usd)` and `BudgetExhausted` events ride the canonical log; Phase 13's cost-ledger projection folds them additively. ✓

## Roadmap coherence check

- **Depends on prior phases.**
  - **Phase 5 (sandbox).** `sandbox_build_and_test` activity wraps the Phase-5 `SubprocessJail`; the microVM boundary is unchanged. Phase-9 adds *no* new pathway from the microVM to Temporal or Postgres (the microVM still has no credentials).
  - **Phase 6 (SHERPA loop).** `run_vuln_subgraph` activity wraps the Phase-6 `VulnRemediationSut` *as-is*; `LocalVulnRemediationSut` continues to work for Phase-6 tests. `SutDigest` invariance is the G5 contract.
  - **Phase 8 (Supervisor + hot views).** `resolve_plugin` + `build_bundle` + `route` activities wrap the Phase-8 three-node graph 1:1 — Phase 8 designed this seam deliberately. Redis hot views are untouched; `gather_id`-stamped reads continue to fail-closed.
  - **Phase 4 (RAG + LLM fallback).** `LeafLlmPort` is intact; only invoked inside the Phase-4 `FallbackTier` ladder, called inside `run_vuln_subgraph`.

- **Establishes for later phases.**
  - **Phase 10 (Discovery + Assessment).** Adds `CandidateRepo` event variant (additively); the new `MultiPluginParentWorkflow` is consumed by Phase-10's `Both`-case `MultiPluginDispatch` decisions. Phase-9 ships the typed shape; Phase 10 ships the deep sequencing.
  - **Phase 11 (Handoff + Learning).** Adds `SolvedExampleWritten` projection; folds Phase-9's `MergeOutcome` + `PatchApplied` + `LlmInvoked` events. Additive — no Phase-9 event variant changes.
  - **Phase 13 (cost ledger + ROI dashboard).** Adds `cost_ledger` projection (folds `LlmInvoked.cost_usd` + `BudgetExhausted` events Phase 9 ships). No stub in Phase 9; pure additive landing.
  - **Phase 13.5 (operator portal).** Reads the canonical event log via `read_role`; needs no Temporal cluster auth (the portal projects off the events, not the workflow-history). Critic-2 hidden-assumption on [S] addressed.
  - **Phase 14 (continuous gather).** Adds webhook-triggered workflow starts; reuses `VulnRemediationWorkflow` with new event variants for `GatherTriggered`. Additive.
  - **Phase 15 (agentic recipe authoring).** Reuses every primitive; adds new task classes via the same `@register_activity` + `@register_event_variant` shape.
  - **Phase 16 (hardening).** Adds prod-shape Temporal cluster (3 server pods), pgbouncer if needed, TDE/LUKS at the volume layer, per-tenant key rotation, mTLS namespace isolation.

- **New ADRs implied (under `docs/phases/09-temporal-durable-workflow/ADRs/`).**
  - **ADR-0001:** Phase-6 SQLite checkpointer drain-don't-cutover policy.
  - **ADR-0002:** Phase-8 `codegenie.plugins.events` log → canonical event log cutover schedule (30-day drain in Phase 10).
  - **ADR-0003:** Per-workflow BLAKE3 chain (not global) — rationale, threat model, scope.
  - **ADR-0004:** Workflow-determinism import-linter + AST-fence vocabulary (the canonical list).
  - **ADR-0005:** Payload-by-reference threshold (8 KiB) + `BlobRef` lifecycle.
  - **ADR-0006:** `@critical_event` synchronous-flush vocabulary — closed registry, decorator-extensible.
  - **ADR-0007:** Two-task-queue partitioning in Phase 9 (`vuln-remediation-node-npm` + `system`); expansion-by-addition policy.
  - **ADR-0008:** `RedactedActivityResult.seal()` typed-credential-class blocklist (the load-bearing security primitive).
  - **ADR-0009:** No `pgcrypto` column encryption; encryption-at-rest delegated to volume layer (deferred to Phase 16).

## Open questions deferred to implementation

1. **Continue-as-new for `run_vuln_subgraph` activities approaching the 20-min cap.** Phase 9 ships a fixed timeout; Phase 10's portfolio shape may force the continue-as-new pattern. Implementation may add it under a story without an ADR amendment.
2. **Whether `@critical_event` events should also write through the EventBatchWriter for *eventual consistency*.** Current design: synchronous-flush bypasses the batcher entirely. If a synchronous flush fails and the workflow retries, two synchronous attempts is wasted work. Implementation may add an "after-write fanout into the batcher for audit" pattern.
3. **Postgres connection-pool sizing under burst.** Per-process `psycopg_pool.AsyncConnectionPool` minsize/maxsize is to be tuned by the throughput canary baseline.
4. **`temporal-ui` link from `make dev-up` output.** Cosmetic but high-value; implementation may print the URL.
5. **Whether `ParentResult.SomeMerged` should auto-emit `HumanReviewRequested` for the unmerged children, or leave it to the parent's reviewer.** ADR-0042 is silent; Phase 10 will exercise the case and decide.
6. **Whether to add a `SearchAttribute` allowlist (closed `Literal` type) in Phase 9 or defer to Phase 13.5.** Critic correctly noted Phase 13.5 needs queryability; Phase 9 ships no `SearchAttribute` registrations. Implementation may add the allowlist primitive without using it.
