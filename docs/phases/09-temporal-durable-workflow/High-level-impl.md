# Phase 09 — Durable workflow envelope: Temporal: High-level implementation plan

**Status:** Implementation plan
**Date:** 2026-05-23
**Architecture reference:** [phase-arch-design.md](phase-arch-design.md)
**ADRs:** [ADRs/](ADRs/)
**Source design:** [final-design.md](final-design.md)
**Roadmap reference:** [docs/roadmap.md](../../roadmap.md) §"Phase 9 — Durable workflow envelope: Temporal"

## Executive summary

Build a Temporal durable envelope around the existing Phase-6 SHERPA loop and Phase-8 Supervisor, plus the canonical Postgres event log that future phases (11/13) will fold as projections. The work shape is asymmetric: the Phase-8 Supervisor maps 1:1 to Temporal Activities, while the Phase-6 LangGraph subgraph runs inside *one* fat `run_vuln_subgraph` Activity (preserves `SutDigest` invariance — G5). The 21-variant typed `EventPayload` discriminated union and per-workflow BLAKE3 chain land as the audit substrate. Sequence is contract-first → infra → activities (bottom-up, easiest to test) → workflows → bridge → hardening, because every later layer's tests need the earlier layer's types and the determinism fence has to bite from day one or it never bites.

## Order of operations

Contracts and fences land first because the determinism rules of Temporal workflow code (G4) make retrofit expensive — once a `set(` literal or a `datetime.now()` call ships into a workflow body, every later test layer becomes a forensic exercise. Postgres + alembic land before any activity that writes to it, because the schema is the contract for `emit_event`. Activities land before workflows because workflow tests use Temporal's `WorkflowEnvironment` with mocked activities — the activity *type signatures* are what the workflow sees, so the typed inputs/outputs must exist before the workflow body can be written. The LangGraph↔Temporal bridge (`TemporalVulnRemediationSut`) lands after both, because it requires real workflows and real activities to exercise. Durability and adversarial passes come last because they are negative tests over the full assembly.

Pattern-driven sequencing constraints inherited from the architect:

- **Newtypes + Pydantic event models + smart constructors land in Step 1.** `WorkflowId`, `EventId`, `BlobDigest`, `AttemptId`, `CorrelationId`, `WorkflowSeq`, `ProjectionId`, `TaskQueueName`, `ActivityName`, `PrUrl` must exist before any module references them; the 21-variant `EventPayload` union must exist before `EventLog` or any activity emits one.
- **`@register_activity` / `@register_projection` / `@critical_event` registry kernels land before any module that decorates with them.** Same shape as `@register_probe` from Phase 0 — `__init__.py` is the explicit-import collection point; the decorator populates a dict at first invocation.
- **Adapter ports land before adapters.** `LangGraphCheckpointerPort` Protocol + `Projection` Protocol ship in Step 1; `PostgresCheckpointerAdapter` + the three concrete projections come later.
- **Tagged-union workflow state lands before the workflow that consumes it.** `VulnLedger` is unchanged from Phase 6 (re-export, do not duplicate); `ParentResult = AllMerged | SomeMerged | AllFailed` is new in Step 5.
- **`mypy --strict` + `ruff` + `import-linter` are Step-1 done criteria**, not added later. The `codegenie.durable.workflows-must-be-pure` import-linter contract must exist before the first workflow file does.
- **Smart-constructor seam (`RedactedActivityResult.seal()`, `BlobRef` only-via-`write_blob_ref`) lands with the sanitizer in Step 3**, before any activity that returns a payload references the type.

## Step 1 — Establish domain primitives, typed event contracts, and structural fences

**Goal:** Ship the type contracts, registries, and import-linter rules every later step depends on; make non-determinism a build break before any workflow exists.

**Features delivered:**
- Newtypes added to `src/codegenie/types/identifiers.py`: `WorkflowId`, `EventId`, `BlobDigest`, `AttemptId`, `CorrelationId`, `WorkflowSeq`, `ProjectionId`, `TaskQueueName`, `ActivityName`, `TaskClassId`, `PrUrl`.
- `src/codegenie/events/payloads.py` — 21-variant Pydantic v2 discriminated union (`frozen=True, extra="forbid"`, `Annotated[Union[...], Field(discriminator="kind")]`); module-level `EventPayloadAdapter: Final[TypeAdapter[EventPayload]]`.
- `@critical_event` decorator (module-level `_CRITICAL_EVENTS: set[str]`); applied to the five variants: `WorkflowTerminated`, `TrustGateFailed`, `MergeOutcome`, `BudgetExhausted`, `ChainTamperDetected`.
- `src/codegenie/types/credentials.py` — `SECRET_TYPES: Final[frozenset[type]]` registry of `GitHubToken | LlmApiKey | MicroVmCredential | PostgresPassword | SshPrivateKey`.
- `Projection` Protocol (`name: ProjectionId`, `fold(events) -> ProjectionState`); `@register_projection` registry kernel.
- `@register_activity` registry kernel under `src/codegenie/durable/activities/__init__.py` (decorator + `_ACTIVITIES: dict[ActivityName, ActivityRegistration]`).
- `LangGraphCheckpointerPort` Protocol under `src/codegenie/durable/checkpointer.py` (port only; no adapter yet).
- `import-linter` contract `codegenie.durable.workflows-must-be-pure` added to `pyproject.toml`: forbid `random`, `time`, `datetime`, `uuid`, `os`, `socket`, `httpx`, `requests`, `redis`, `psycopg`, `asyncpg`, `subprocess`, `codegenie.exec`, `codegenie.transforms`, `codegenie.probes` from `codegenie.durable.workflows.*`.
- AST fence `tests/fence/test_workflow_determinism.py` — walks `src/codegenie/durable/workflows/*.py`, rejects literal `set(`, `random.*`, `time.*`, `datetime.now`, `uuid.uuid4`, `os.environ`.
- Property tests: Hypothesis-generated `EventPayload` instances JSON round-trip via `EventPayloadAdapter`; `@critical_event` registry collision raises `TypeError` at import.

**Done criteria:**
- [ ] `make typecheck` (mypy --strict) green on `codegenie.events`, `codegenie.types`, `codegenie.durable` skeletons.
- [ ] `make lint-imports` green; the new `workflows-must-be-pure` contract is exercised by a deliberate violation fixture (xfail).
- [ ] `pytest tests/fence/test_workflow_determinism.py` green against an empty `codegenie.durable.workflows/` directory (proves the walker runs).
- [ ] `tests/events/test_payload_roundtrip.py` — every of 21 variants JSON-round-trips byte-identically via `EventPayloadAdapter`.
- [ ] `tests/events/test_critical_event_registry.py` — registering the same class twice raises; `_CRITICAL_EVENTS` contains exactly the five names.
- [ ] `tests/property/test_event_payload_hypothesis.py` — 200 generated instances round-trip.
- [ ] Per-submodule cold-start fence still green (no circular imports introduced by the new modules).

**Depends on:** nothing (foundation).

**Effort:** M — wide type surface (21 variants × `frozen=True` boilerplate), but each variant is mechanical. The load-bearing risk is getting the union discriminator right; the round-trip property test is the verification.

**Risks specific to this step:** The 21-variant union is large enough that a missed `Literal["kind_str"] = "kind_str"` discriminator field silently breaks Pydantic's union dispatch — the round-trip property test must run on every variant or this drifts.

## Step 2 — Provision Postgres + alembic + docker-compose dev surface

**Goal:** Stand up the durable infrastructure (Postgres 16 with three schemas, alembic owning `events` only, docker-compose with loopback bindings) and the supply-chain lock so a poisoned migration cannot land.

**Features delivered:**
- `infra/docker-compose.dev.yml` — `postgres:16-alpine`, `temporalio/auto-setup:1.25`, `temporalio/ui:2.30` (bound `127.0.0.1:8233`), `redis:7-alpine`; all ports bound to `127.0.0.1`.
- `scripts/temporal-dev.sh` — rejects `--ip 0.0.0.0` / `*.*.*.*` patterns.
- `src/codegenie/events/alembic/` directory; `env.py` configured for the `events` schema; `versions/0001_create_events_schema.py` — schema, `events.events` table with append-only trigger + row-level grants (`application_role` INSERT/SELECT only; `migrations_role` DDL on `events` schema only, no `CREATE EXTENSION` outside `{pg_stat_statements}`), `events.blob_refs` table, per-workflow `wf_seq` UNIQUE INDEX.
- `tools/alembic-revisions.lock` — SHA-pins every file under `alembic/versions/`.
- `Makefile` targets: `make dev-up`, `make dev-down`, `make migrate`.
- `codegenie.durable.config.DurableSettings` (Pydantic Settings, env-prefix `CODEGENIE_DURABLE_`) wiring Postgres DSN, pool sizes, batch parameters.
- `psycopg_pool.AsyncConnectionPool` factory.

**Done criteria:**
- [ ] `make dev-up` brings docker-compose up in <30 s cold; `make dev-down` tears it down cleanly.
- [ ] `make migrate` runs the alembic upgrade against a fresh Postgres; `events.events` and `events.blob_refs` exist with the append-only trigger active.
- [ ] `tests/fence/test_alembic_revision_lock.py` — SHA of each `versions/*.py` matches `tools/alembic-revisions.lock`; mismatch fails CI.
- [ ] `tests/fence/test_alembic_schema_snapshot.py` — migrate against fresh PG, dump schema, diff against `tests/fence/alembic_schema.sql.snapshot`.
- [ ] `tests/fence/test_alembic_owns_only_events_schema.py` — no migration references `temporal.*` or `langgraph_checkpoints.*`.
- [ ] `tests/fence/test_temporal_ui_loopback.py` — grep `scripts/`, `infra/`, `Makefile` for `0.0.0.0`; zero matches.
- [ ] `tests/adv/test_events_append_only_enforcement.py` — `application_role` UPDATE/DELETE/TRUNCATE raises (testcontainers).
- [ ] `tests/adv/test_alembic_migration_plpython_blocked.py` — a `CREATE FUNCTION ... LANGUAGE plpython3u` migration fails because `migrations_role` is not super.

**Depends on:** Step 1 (the schema column types reflect the Newtype contracts).

**Effort:** M — the alembic supply-chain story (lock + ownership + grants + snapshot diff) is four small fences but they all need to land together to be credible.

**Risks specific to this step:** Engineers will be tempted to add `CREATE EXTENSION pgvector` "while we're here"; the allowlist + non-super `migrations_role` is the only structural defense. The schema-snapshot diff requires a Postgres install in CI — if it flakes, contributors will disable it.

## Step 3 — Canonical event log, BlobRef store, and activity-boundary sanitizer

**Goal:** Ship the typed append-only event log with per-workflow BLAKE3 chain and the smart-constructor seams (`BlobRef` only via `write_blob_ref`, `RedactedActivityResult.seal()`) the activities will use in Step 4.

**Features delivered:**
- `src/codegenie/events/log.py` — `EventLog.append(EventPayload, capability)`, `append_batch`, `read_workflow(workflow_id)`; `EventBatchWriter` with 20 ms / 256-event flush + `@critical_event` synchronous-flush bypass; per-workflow chain-head LRU cache (max 200 in-flight); chain-tail re-read from Postgres on miss; `COPY events.events FROM STDIN BINARY` flush path.
- `src/codegenie/events/blob_refs.py` — `BlobRef` (frozen Pydantic; smart-constructed); `events.blob_refs` content-addressed table; `BLAKE3` digest computation.
- `src/codegenie/durable/sanitizer.py` — `RedactedActivityResult` base class + `seal(model: T) -> RedactedActivityResult`; three-layer sanitization at seal time: (a) Pydantic `extra="forbid"`, (b) typed-credential-class blocklist via `SECRET_TYPES`, (c) value-shape regex backstop (AWS / GitHub PAT / JWT) — match emits `RedactionFired` event.
- `EventLogWriteCapability`, `PrOpenCapability`, `LlmSpendCapability` typed Pydantic records under `src/codegenie/durable/capabilities.py`.

**Done criteria:**
- [ ] `tests/integration/test_event_log_append.py` (testcontainers PG) — 1k events across 10 concurrent workflows; each workflow's chain internally consistent; cross-workflow appends parallel.
- [ ] `tests/integration/test_per_workflow_chain.py` — 100 events across 3 concurrent workflows; tampering one workflow's row leaves the other two chains valid.
- [ ] `tests/integration/test_blob_ref_roundtrip.py` — write 200 KiB blob via `write_blob_ref`; `resolve_blob_ref` returns byte-identical content; duplicate write `ON CONFLICT DO NOTHING`.
- [ ] `tests/unit/test_sanitizer_seal.py` — `seal()` rejects every member of `SECRET_TYPES`; rejects each value-shape regex; emits `RedactionFired` on regex match.
- [ ] `tests/property/test_sanitizer_idempotence.py` — `seal(seal(x)) == seal(x)`.
- [ ] `tests/property/test_secret_shape_hypothesis.py` — Hypothesis-generated AWS / GitHub / JWT secret shapes all rejected.
- [ ] `tests/adv/test_event_chain_tamper_detection.py` — forge a row via `migrations_role`; chain-verify on next read emits `ChainTamperDetected`.
- [ ] `make bench tests/perf/test_phase09_event_log_append.py` — 10k events across 50 concurrent workflows, p95 commit ≤ 15 ms (sync) / ≤ 50 ms (batched). Baseline ratchet recorded.

**Depends on:** Step 1 (types), Step 2 (Postgres + schema).

**Effort:** L — the BLAKE3 chain semantics (per-workflow, not global) + the COPY-binary fast path are the load-bearing performance work; the sanitizer's three-layer order is load-bearing for security.

**Risks specific to this step:** The chain-head LRU cache is the perf shortcut that makes per-workflow chaining feasible at 3k events/sec; a bug here either tanks throughput or causes a missed chain link. The synchronous-flush bypass for `@critical_event` is easy to write wrong (e.g., "synchronous *and* batched" — double-write); the bench tests must cover both.

## Step 4 — Activity catalog (one file per activity, typed in and out, registry-collected)

**Goal:** Ship the nine activities that the workflow body will dispatch, each thin enough that its test file is the only meaningful entry point.

**Features delivered:**
- `src/codegenie/durable/activities/retry_policies.py` — module-level `Final` table `_POLICIES: dict[ActivityName, RetryPolicy]` keyed by activity name; `non_retryable` lists include the tier-descent triggers (`RecipeMissedError`, `RagMissedError`).
- One file per activity under `src/codegenie/durable/activities/`:
  - `resolve_plugin.py`, `build_bundle.py`, `route.py` — wrap Phase-8 Supervisor's three nodes.
  - `run_vuln_subgraph.py` — fat activity wrapping the Phase-6 LangGraph subgraph; heartbeats every 5 s; idempotent on `AttemptId`; resumes from `PostgresCheckpointerAdapter` checkpoint on re-dispatch.
  - `sandbox_build_and_test.py` — wraps Phase-5 `SubprocessJail`; idempotent on `(patch_digest, build_inputs_digest)`.
  - `github_open_pr.py` — wraps Phase-11-preview PR opener; idempotent on `(repo, attempt_id)`; threaded `PrOpenCapability`.
  - `emit_event.py` — calls `EventLog.append_batch`; threaded `EventLogWriteCapability`.
  - `resolve_blob_ref.py`, `write_blob_ref.py`.
- Every activity's input + output is `BaseModel`-derived (`frozen=True, extra="forbid"`); every output is `RedactedActivityResult`-derived.
- `tests/fence/test_activity_payload_typing.py` — introspects every `@activity.defn`-decorated function; asserts inputs are `BaseModel` and outputs are `RedactedActivityResult`-derived; the *return type annotation* (`get_type_hints`) is the check, not runtime shape.
- `tests/fence/test_no_merge_activity.py` — greps `@activity.defn(name=...)` for `merge_pr|approve_pr|self_merge` (zero matches; ADR-0009 fence).

**Done criteria:**
- [ ] Each activity has a corresponding `tests/unit/durable/activities/test_{activity}.py` covering (a) typed-event emit with right capability, (b) Pydantic round-trip, (c) idempotence on `AttemptId`.
- [ ] `tests/fence/test_activity_payload_typing.py` green.
- [ ] `tests/fence/test_no_merge_activity.py` green.
- [ ] `tests/adv/test_typed_credential_blocklist.py` — an activity declared with a `GitHubToken`-typed return field is rejected by `seal()` at first invocation.
- [ ] `tests/adv/test_secret_leakage_in_history.py` — every known secret shape in an activity return is rejected; `RedactionFired` lands in the event log.
- [ ] `make lint-imports` — no activity imports from `codegenie.durable.workflows.*` (one-way dependency).
- [ ] `make typecheck` green; every activity registered via `@register_activity`.

**Depends on:** Step 1 (types + registries), Step 3 (sanitizer + event log + capabilities). Does *not* depend on Step 5 — activities are testable in isolation against mocked inputs.

**Effort:** L — nine activities × (file + test file + retry-policy row); mechanically large but each unit is small. The `run_vuln_subgraph` Activity is the only deep one (it wraps the entire Phase-6 LangGraph).

**Risks specific to this step:** `run_vuln_subgraph`'s idempotence-on-`AttemptId` is the G1 exit-criterion lynchpin; the heartbeat cadence (5 s) must be sub-Temporal's heartbeat-timeout (30 s) by a margin that survives a slow Postgres write — get this wrong and replays fail flakily.

## Step 5 — Postgres checkpointer adapter + workflow definitions

**Goal:** Ship the `PostgresCheckpointerAdapter` (replaces Phase-6 SQLite) and the two workflow classes (`VulnRemediationWorkflow`, `MultiPluginParentWorkflow`) — pure orchestration over `VulnLedger`/`ParentResult` sum-types, dispatching the Step-4 activities.

**Features delivered:**
- `src/codegenie/durable/checkpointer.py` — `PostgresCheckpointerAdapter` implementing `LangGraphCheckpointerPort`; wraps `langgraph_checkpoint_postgres.PostgresSaver`; adds `health() -> CheckpointerHealth` translation (`pool_in_use`, `pool_idle`, `last_write_age_seconds` — not exposed by upstream).
- `src/codegenie/durable/workflows/vuln_remediation.py` — `@workflow.defn(name="VulnRemediationWorkflow")`; `run(request)`, `human_review_decision` signal, `cancel` signal, `state()` query; `match` over `VulnLedger` variants; per-activity `RetryPolicy` from `_POLICIES`; **no** retry loops in workflow code.
- `src/codegenie/durable/workflows/multi_plugin_parent.py` — `@workflow.defn(name="MultiPluginParentWorkflow")`; `run(MultiPluginDispatch)` spawns N child `VulnRemediationWorkflow`s via `execute_child_workflow`; aggregates `ParentResult = AllMerged | SomeMerged | AllFailed`; honors `MultiPluginDispatch.coordination_policy: Literal["independent", "all_or_nothing", "best_effort"]` (Phase 9 implements `"independent"` only; other variants raise typed `NotImplementedError("see Phase 10")` at the workflow body — per Gap-2 / phase ADR-0011).
- `RouteDecision` and `PluginResolved` payloads carry `freshness_window: timedelta` + `decided_at`; workflow body checks staleness on resume and tier-descends if expired (emits `RouteStalenessDescent` event variant — per Gap-3 / phase ADR-0012).
- `src/codegenie/durable/workflows/__init__.py` — explicit imports; module-level docstring naming the determinism fence.

**Done criteria:**
- [ ] `tests/workflows/test_vuln_remediation_workflow.py` (Temporal `WorkflowEnvironment`) — happy path with mocked activities asserts `VulnLedger` transitions `NeedsPlan → PlanReady → PatchApplied → AwaitingHumanReview → Completed`.
- [ ] `tests/workflows/test_multi_plugin_parent_workflow.py` — 2-child happy path produces `ParentResult.AllMerged`; `coordination_policy="all_or_nothing"` raises typed error visible in `temporal-ui`.
- [ ] `tests/workflows/test_hitl_pause_resume.py` — `wait_condition(human_review_decision)` parks the workflow; signal dispatch resumes it.
- [ ] `tests/workflows/test_replay_determinism.py` — `temporalio.testing.WorkflowReplayer.run_replay_workflows(histories=[fixture])` succeeds; per-Python-minor matrix (3.11 + 3.12).
- [ ] `tests/integration/test_checkpointer_health.py` — `PostgresCheckpointerAdapter.health()` reports pool stats; pool exhaustion yields `psycopg.PoolTimeoutError`.
- [ ] `tests/integration/test_subgraph_resume_determinism.py` — kill activity mid-LangGraph; resume reads same checkpoint state.
- [ ] `make lint-imports` — `codegenie.durable.workflows-must-be-pure` contract green.
- [ ] `tests/fence/test_workflow_determinism.py` — AST walker green over the new workflow files (no `set(` / `random` / `time` / etc.).
- [ ] `make typecheck` — `match` arms exhaustive over `VulnLedger`; `assert_never` at the bottom of every `match`.

**Depends on:** Step 4 (activities + retry policies), Step 3 (event log — workflow emits `WorkflowStarted` via `execute_activity("emit_event", ...)`).

**Effort:** L — the workflow code is small but the determinism fences bite hard; the `WorkflowEnvironment` test setup + replay-test fixture-history recording are non-trivial scaffolding.

**Risks specific to this step:** Replay-determinism is a tar pit. The AST fence catches direct calls; `import-linter` catches direct imports; only the `Replayer` test catches transitive non-determinism through `langgraph` version drift (the canonical trigger). If the Replayer test flakes once on a transient Postgres pool issue, it will get marked `@pytest.mark.flaky` — the architect explicitly called this out. The G1 durability test must run in `make test`, not behind `@pytest.mark.e2e`.

## Step 6 — Worker process model + LangGraph↔Temporal bridge

**Goal:** Make the workflows runnable (workers, hot reload, capability minting from K8s ServiceAccount mount) and expose the Temporal-backed Phase-6.5 SUT so `SutDigest` invariance is testable.

**Features delivered:**
- `src/codegenie/durable/workers/__init__.py` — `build_worker(kind: WorkerKind, settings: DurableSettings) -> Worker`; `python -m codegenie.durable.workers` entrypoint; `uvloop` + `watchfiles` dev hot reload.
- Two activity worker pools wired:
  - `vuln-remediation-node-npm`: `[resolve_plugin, build_bundle, route, run_vuln_subgraph, sandbox_build_and_test, github_open_pr]`.
  - `system`: `[emit_event, resolve_blob_ref, write_blob_ref]`.
- Capability minting at worker startup: reads `/var/run/secrets/codegenie/queue-identity` (K8s ServiceAccount mount) — local dev reads from a `.env`-loaded file; constructs the `Capability` types the worker is allowed to mint.
- `src/codegenie/durable/bridge.py` — `TemporalVulnRemediationSut(VulnRemediationSut)`; `run_case` writes case inputs to `BlobStore`, starts workflow, awaits result, reads terminal `BlobRef`s; `digest()` delegates to Phase-6 builder under `freezegun`.

**Done criteria:**
- [ ] `make dev-up && python -m codegenie.durable.workers --kind=workflow &` + `--kind=activity --queue=vuln-remediation-node-npm` + `--kind=activity --queue=system` brings workers up; `temporal-ui` at `http://127.0.0.1:8233` shows the registered task queues.
- [ ] `tests/durability/test_sut_digest_invariance.py` (G5) — every Phase-6 canonical case digests byte-identically under `LocalVulnRemediationSut` and `TemporalVulnRemediationSut`.
- [ ] `tests/integration/test_workflow_e2e_postgres.py` — real Postgres + real Temporal dev server + fake Redis + cassette LLM; full recipe-route workflow completes in ~30 s.
- [ ] `tests/adv/test_capability_token_scope.py` — `vuln-remediation-node-npm` worker cannot mint `EventLogWriteCapability` for kinds outside its allowlist.
- [ ] Hot reload demonstrated: edit an activity file; worker restarts in <1 s.

**Depends on:** Step 5 (workflows + checkpointer), Step 4 (activities).

**Effort:** M — worker scaffolding is mostly Temporal SDK plumbing; the bridge is small (delegates to `temporal_client.start_workflow`); capability minting is one file.

**Risks specific to this step:** Worker hot reload via `watchfiles` is dev-only ergonomics — easy to ship a path that works in dev but blows up under K8s (where `/var/run/secrets/...` is the only legal mount). The capability-minting code must work identically in both; the test fixture should mock the mount path explicitly.

## Step 7 — Projections (real, not stubs)

**Goal:** Ship the three Phase-9 projections — `audit_trail`, `retry_histogram`, `plugin_telemetry` — pure folds over the canonical event log, registered via `@register_projection`. **Zero stubs raising `NotImplementedError`** (ADR-0043).

**Features delivered:**
- `src/codegenie/events/projections/audit_trail.py` — chronological event list per workflow; chain-verifies on every fold; emits `ChainTamperDetected` on gap.
- `src/codegenie/events/projections/retry_histogram.py` — `GateOutcome × failing_signals` rollup; folds over `TrustGatePassed` + `TrustGateFailed`.
- `src/codegenie/events/projections/plugin_telemetry.py` — `PluginResolved × MergeOutcome` join for per-plugin merge / fallback rates; replaces the projection role Phase-8 `codegenie.plugins.events` filled.
- `src/codegenie/events/projections/__init__.py` — `@register_projection` collection; collision raises `TypeError` at import.
- One-way emitter from `run_vuln_subgraph` into the canonical log (Phase-8 `codegenie.plugins.events` keeps running for the 30-day-drain window; deletion is Phase-10's first commit per phase ADR-0002).

**Done criteria:**
- [ ] Each projection has a test file under `tests/events/projections/` folding fixture event streams; **no Postgres needed for unit tests**.
- [ ] `tests/property/test_projection_idempotence.py` — `fold(events) == fold(events)`.
- [ ] `tests/property/test_projection_timestamp_invariance.py` — `fold(shuffle_within_equal_ts(events)) == fold(events)`.
- [ ] `tests/integration/test_audit_trail_chain_verify.py` — chain gap triggers `ChainTamperDetected`; halts further folding for that workflow.
- [ ] Golden event-stream fixtures per workflow type land under `tests/golden/events/`.
- [ ] `tests/integration/test_phase08_log_fanout.py` — the `run_vuln_subgraph` one-way emitter writes `PluginResolved` / `BundleBuilt` / `RouteDecided` into the canonical log byte-identically to the Phase-8 log's records.

**Depends on:** Step 3 (event log), Step 4 (`run_vuln_subgraph` activity).

**Effort:** M — three pure folds + their goldens; the load-bearing piece is the chain-verify semantics on `audit_trail`.

**Risks specific to this step:** The Phase-8 log fanout invites silent double-recording or silent miss; the canonical log is the *only* source projections consume, but engineers may forget that and accidentally read Phase-8 records into a new projection. Add a fence that no projection imports `codegenie.plugins.events`.

## Step 8 — Durability test pass + adversarial sweep + CI gates

**Goal:** Prove G1, G6, G9, G11 with adversarial tests; wire every fence and durability test into `make check` so regressions surface at PR time.

**Features delivered:**
- `tests/durability/test_kill_worker_resume.py` (G1) — N kill offsets across `run_vuln_subgraph`; assert byte-identical terminal `VulnLedger` state. **Runs in `make test`, not `@pytest.mark.e2e`.**
- `tests/durability/test_temporal_cluster_restart.py` — `temporal kill && temporal start`; in-flight workflows resume.
- `tests/adv/test_worker_credential_blast_radius.py` (G9) — compromised worker cannot: (a) open PRs outside its allowlist; (b) write events of a kind outside its task queue's allowlist; (c) signal/terminate a workflow on a different task queue.
- Perf canaries under `-m bench`, nightly: `test_phase09_throughput.py` (≥3k events/sec); `test_phase09_event_log_append.py` (p95 ≤ 15 ms); `test_phase09_token_canary.py` (G11: `total_tokens == 0` on cassette-replay); `test_phase09_cold_replay_latency.py` (200-event history ≤ 1.5 s p95); `tests/perf/test_phase09_route_activity_overhead.py` (Gap-1 canary: `execute_activity("route", ...)` p95 ≤ 40 ms).
- CI workflow updates: `make check` includes every new fence; `make bench` runs nightly with ratchet-baseline files under `tests/bench/baselines/`.
- Documentation site updates: `docs/development.md` covers `make dev-up`, port overrides, troubleshooting; ADRs published.

**Done criteria:**
- [ ] `make check` green end-to-end on a clean clone after `make dev-up`.
- [ ] G1: `test_kill_worker_resume.py` passes 100 consecutive runs locally; CI 10 consecutive PR runs (catches flakes).
- [ ] G6: nightly bench shows ≥3k events/sec sustained from 5 activity workers; baseline ratchet file checked in.
- [ ] G9: blast-radius adversarial test green for all four privileged actions.
- [ ] G11: `total_tokens == 0` on the cassette-replay throughput run.
- [ ] Roadmap exit-criteria phrasing verified: "Workflows survive process restarts without state loss" (G1); "temporal-ui shows live workflow inspection" (G2 + Step 2/6 evidence); "All retries are framework-level — application code contains no retry loops" (G3 — `import-linter` over `src/codegenie/durable/workflows/*.py` rejects `while ... retry` / `for ... in range(retries)` patterns; this fence is added in this step).
- [ ] mkdocs build strict green; Phase-9 page published.

**Depends on:** Steps 1–7.

**Effort:** M — the durability tests themselves are small (kill the worker; resume; assert digest); the load-bearing work is making them not flake.

**Risks specific to this step:** Once the durability tests are green and CI is happy, the temptation is to call the phase done. The Gap-1 route-activity canary, the Gap-2 `coordination_policy` Phase-10 handoff field, and the Gap-3 freshness-window resume semantics all need explicit closeout-story checks; missing any of these silently strands Phase 10.

## Exit-criteria mapping (table)

Phase 9 roadmap exit criteria → steps that ship the evidence:

| Roadmap exit criterion | Steps that ship evidence | Verification path |
|---|---|---|
| Workflows survive process restarts without state loss | Step 5 (workflow + checkpointer), Step 6 (workers + bridge), Step 8 (G1 durability tests) | `tests/durability/test_kill_worker_resume.py` + `test_temporal_cluster_restart.py` byte-identical terminal `VulnLedger`; runs in `make test`. |
| `temporal-ui` shows live workflow inspection | Step 2 (docker-compose + loopback enforcement), Step 6 (workers register), Step 8 (CI greps loopback) | `make dev-up`; browse `http://127.0.0.1:8233`; `tests/fence/test_temporal_ui_loopback.py` green. |
| All retries are framework-level — application code contains no retry loops | Step 4 (`retry_policies._POLICIES` module-level `Final` table), Step 5 (workflow body has no retry loops), Step 8 (CI fence over `codegenie.durable.workflows/*`) | `import-linter` + `forbidden-patterns` regex over `src/codegenie/durable/workflows/*.py`; code-search assertion in CI rejecting `while ... attempt < max` / `for _ in range(retries)` constructs. |

## Implementation-level risks

1. **Replay-determinism flake quarantine.** The `Replayer`-based test (Step 5) catches transitive non-determinism that the AST fence and `import-linter` cannot — but it is also the most expensive layer and the easiest to mark flaky. **Signal:** the first time the test fails on a PR that did not touch `codegenie.durable.workflows/`, the contributor will assume "infra flake" and re-run. **Response:** the test must produce a deterministic error pointing at the offending diff (Temporal SDK does this — preserve the full `NondeterminismError` payload in the test output); CI must record the recorded-vs-replayed history diff as an artifact.

2. **Alembic migration creates an N-1/N worker incompatibility window during deploy.** Step 2's append-only events table cannot be altered backwards; Step 8's CI gate "migrate against fresh PG" catches *forward* incompatibilities but not *rolling-deploy* incompatibilities where worker N-1 (old code) and worker N (new code) are simultaneously alive. **Signal:** an integration test passes locally but a staging deploy shows new-code workers writing rows old-code workers can't read. **Response:** every migration in this phase is *additive only* (Step 2 ships one migration; this is the discipline). Schema-changing migrations land in Phase 10+ with an expand-then-contract template.

3. **EventBatchWriter back-pressure interaction with Temporal activity retries.** Step 3's batcher accumulates up to 16 MiB on Postgres unavailability; over the cap → back-pressure into Temporal (activity retries per `RetryPolicy`). **Signal:** under sustained Postgres latency spikes, activity retries pile up; `emit_event` retries multiplicatively because each retry re-enqueues. **Response:** the bench tests in Step 8 must include a fault-injection scenario (Postgres `pg_sleep(2.0)` injected via `pg_stat_statements`); if back-pressure misbehaves, the bench fails before merge.

4. **Postgres connection-pool sizing wrong under burst.** Step 2's default `minsize=2, maxsize=20` per process is a guess; Step 8's G6 throughput canary surfaces wrong values as a regression. **Signal:** p95 commit latency degrades non-linearly past ~30 in-flight workflows. **Response:** the canary baseline ratchets the pool sizing as evidence accumulates; phase ADR-0003 records the final defaults.

5. **`run_vuln_subgraph` exceeds 20-minute timeout on a pathological case.** Step 4 ships a fixed `start_to_close_timeout=timedelta(minutes=20)`; the workflow body's `match` arm escalates to `AwaitingHumanReview` on timeout. **Signal:** any Phase-10 portfolio scan with a 4-min p50 / 8-min p95 envelope from a worst-case case crosses the cap. **Response:** open question #1 — continue-as-new lands in Phase 10 without an ADR amendment.

## What's next — handoff to Phase 10

Phase 10 (Stage 0 Discovery + Stage 1 Assessment) consumes the Phase-9 substrate:

- **Canonical Postgres event log + `Projection` Protocol** = Stage 1 Assessment's `vuln.provenance` routing ([ADR-0038](../../production/adrs/0038-vulnerability-provenance-attribution.md)) lands as a new projection on top of `LlmInvoked` + `RouteDecided` + new Phase-10 variants. No Phase-9 event re-shapes.
- **Durable Temporal envelope** = Phase 10's nightly portfolio scan is a Temporal Schedule (same `temporalio` SDK); no new workflow infrastructure.
- **`@register_event` / `@register_activity` discipline** = Stage 0/1 events (`RepoDiscovered`, `AssessmentScored`, `CandidateRepo`) just register new variants in the discriminated union; activities register via the existing decorator. Mechanical add.
- **Postgres baseline + alembic discipline** = Phase 10 schema additions are additive migrations (new variants live in the JSONB `payload` column — no schema migration at all for most additions).
- **`MultiPluginParentWorkflow` already shipped** = Phase 10's `Both`-case (`vuln.provenance ∈ {both}`) exercises existing machinery; the `coordination_policy="all_or_nothing"` / `"best_effort"` variants land additively (Gap-2's typed precondition).
- **Per-task-queue worker pool model** = Phase 7.5 / Phase 10 add new queues (`vuln-remediation-python-pip`, `assessment-*-*`) via `@register_activity(task_queue=...)`. No edit to existing activities.
- **Phase-8 `codegenie.plugins.events` cutover** = Phase 10's first commit deletes the old log after the 30-day-drain window per phase ADR-0002; the cutover canary asserts no in-flight workflow is on the old log before deletion.
