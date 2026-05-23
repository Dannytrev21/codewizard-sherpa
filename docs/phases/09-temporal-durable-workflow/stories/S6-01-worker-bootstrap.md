# Story S6-01 — Worker bootstrap + two task-queue pools

**Step:** Step 6 — Worker process model + LangGraph↔Temporal bridge
**Status:** Ready
**Effort:** M
**Depends on:** S5-02 (`VulnRemediationWorkflow`), S5-04 (`MultiPluginParentWorkflow`)
**ADRs honored:** ADR-0007 (exactly two task queues — `vuln-remediation-node-npm` + `system`; expansion by addition), ADR-0013 (no `TemporalPort` abstraction — direct `temporalio.worker.Worker`), ADR-0010 (asymmetric activity granularity — the two pools mirror that asymmetry), production ADR-0043 (extension by addition: new `WorkerKind` enum row, never edits to existing rows)

## Context

Phase 9 has shipped contracts (Step 1), Postgres (Step 2), the event log (Step 3), the activity catalog (Step 4), and the workflows + checkpointer (Step 5). None of it runs yet. This story is the "boots up the host process" seam: `python -m codegenie.durable.workers --kind=...` brings up a `temporalio.worker.Worker` registered for either the workflow pool or one of the two activity task queues. After this story lands, `make dev-up && python -m codegenie.durable.workers --kind=workflow & python -m codegenie.durable.workers --kind=activity --queue=vuln-remediation-node-npm & python -m codegenie.durable.workers --kind=activity --queue=system &` is a real demo at `http://127.0.0.1:8233`.

The two task queues are load-bearing per ADR-0007: `vuln-remediation-node-npm` runs the six repo-shaped activities (`resolve_plugin`, `build_bundle`, `route`, `run_vuln_subgraph`, `sandbox_build_and_test`, `github_open_pr`); `system` runs the three typed-IO activities (`emit_event`, `resolve_blob_ref`, `write_blob_ref`). The asymmetry exists so a compromised `vuln-remediation-*` worker cannot mint `EventLogWriteCapability` for arbitrary event kinds (S6-02 follow-up) and so the cheap `system` pool can scale independently of the heavy sandboxed pool. This story wires the worker plumbing; capability minting comes next in S6-02.

Workers run as **host processes** in dev (per `phase-arch-design.md §C9` reading guide) — `uvloop` event loop + `watchfiles` for sub-second restart on edit. Production is K8s pods (Phase 16). The code path must be identical in both; only the secret-mount path differs (S6-02 covers that).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C8 — Worker process model (codegenie.durable.workers)` — `build_worker(*, kind: WorkerKind, settings: DurableSettings) -> Worker`; the two pools' exact membership; `uvloop` + `watchfiles` dev hot reload; `~800 ms` restart envelope.
  - `../phase-arch-design.md §Physical view (deployment)` L260–330 — host-process workers in dev; containerized stateful pieces only; production shape deferred to Phase 16.
  - `../phase-arch-design.md §Edge cases #1, #2, #15` — SIGKILL of any pool; rolling-deploy version-mismatch (Phase 16 lands Worker Versioning; Phase 9 fails fast).
  - `../phase-arch-design.md §C2 §Failure behavior` — heartbeat-timeout drives Temporal re-dispatch; the new worker resumes from LangGraph checkpoint.
- **Phase ADRs:**
  - `../ADRs/0007-two-task-queue-partitioning-and-expansion-by-addition.md` — Decision: exactly two queues in Phase 9; `WorkerKind` enum + `tests/fence/test_task_queue_naming.py` enforce the `{task-class}-{language}-{package-manager}` shape (or `system`); Phase 7.5 adds `vuln-remediation-python-pip` by addition.
  - `../ADRs/0013-no-temporal-port-abstraction.md` — direct `temporalio.worker.Worker` use; no `TemporalPort` Protocol; honest single-implementation seam.
- **Existing code precedents:**
  - `src/codegenie/probes/__init__.py` — explicit-import collection point pattern (no `importlib.metadata` entry-point scan); mirror for `codegenie.durable.workers.__init__`.
  - `src/codegenie/durable/activities/__init__.py` (S1-04) — `@register_activity` registry kernel; `build_worker` reads from this registry to choose which activities a queue's worker registers.
  - `src/codegenie/durable/workflows/vuln_remediation.py` (S5-02) and `multi_plugin_parent.py` (S5-04) — the workflow classes the workflow-kind worker registers.
- **External:**
  - `temporalio.worker.Worker` constructor: `task_queue`, `workflows`, `activities`, `interceptors`, `max_concurrent_activities`.
  - `watchfiles.run_process` for hot reload; `uvloop.install()` before `asyncio.run`.

## Goal

Land `src/codegenie/durable/workers/__init__.py` exposing `build_worker(*, kind: WorkerKind, settings: DurableSettings) -> Worker` and a `python -m codegenie.durable.workers` entrypoint that brings up one of three concrete shapes (`workflow`, `activity --queue=vuln-remediation-node-npm`, `activity --queue=system`) under `uvloop` with `watchfiles` dev hot reload. Graceful shutdown drains in-flight activities + the `EventBatchWriter` before exit; signal handlers (SIGTERM / SIGINT) trigger drain-not-kill. After this story, `make dev-up` + three worker processes register their task queues in `temporal-ui` and a CLI `start_workflow` round-trips through the workflow worker into the activity workers and back.

## Acceptance criteria

### `WorkerKind` enum + registry-driven pool composition

- [ ] **AC-1 — `WorkerKind` is a sum type, not a magic string.** `src/codegenie/durable/workers/_kinds.py` defines `class WorkerKind(StrEnum)` with exactly three members: `WORKFLOW = "workflow"`, `VULN_REMEDIATION_NODE_NPM = "vuln-remediation-node-npm"`, `SYSTEM = "system"`. Adding a Phase-7.5 `VULN_REMEDIATION_PYTHON_PIP = "vuln-remediation-python-pip"` row is one additive line (ADR-0007); the test asserts the current Phase-9 set is exactly these three.
- [ ] **AC-1a — Queue name fence.** `tests/fence/test_task_queue_naming.py` greps every `WorkerKind` value (excluding `workflow`); each must match `^system$|^[a-z]+-remediation-[a-z]+-[a-z]+$` (the `{task-class}-{language}-{package-manager}` shape from ADR-0007 §Tradeoffs row 6) or be exactly `system`. Build break on drift.
- [ ] **AC-2 — Activity-pool membership reads from `@register_activity` registry, NOT a hand-rolled dict.** `_ACTIVITIES_FOR_QUEUE: dict[WorkerKind, frozenset[ActivityName]]` is computed at module load from `codegenie.durable.activities._ACTIVITIES` by reading each registration's `task_queue` field. Hand-keying activity names per queue duplicates the registry and drifts; the test asserts the computed set for `VULN_REMEDIATION_NODE_NPM` is exactly `{resolve_plugin, build_bundle, route, run_vuln_subgraph, sandbox_build_and_test, github_open_pr}` and for `SYSTEM` is exactly `{emit_event, resolve_blob_ref, write_blob_ref}`. Drift in the registry surfaces here as a test failure, not as silent reshuffling.

### `build_worker` factory

- [ ] **AC-3 — `build_worker(*, kind: WorkerKind, settings: DurableSettings) -> Worker` factory signature.** Pure factory; **does not start the worker** (the caller calls `await worker.run()`). For `kind=WORKFLOW`: returns `Worker(client=..., task_queue="workflow", workflows=[VulnRemediationWorkflow, MultiPluginParentWorkflow], activities=[], interceptors=[...])`. For `kind=VULN_REMEDIATION_NODE_NPM` or `SYSTEM`: returns `Worker(client=..., task_queue=kind.value, workflows=[], activities=[<resolved from registry>], interceptors=[...])`. `workflows=[]` on activity workers is load-bearing — workflow worker pool is separate (C8 §Internal structure).
- [ ] **AC-3a — `max_concurrent_activities=10` default on activity workers, `1` is invalid.** Per `phase-arch-design.md §C8`. The setting comes from `DurableSettings`. Test asserts `1` raises (workflows would starve) and the default is `10`.
- [ ] **AC-3b — Workflow worker has zero activities registered.** The IO-free property is structural: the workflow worker process must never have access to an activity body. AST/registry check: `build_worker(kind=WORKFLOW, ...).config()["activities"]` is empty. (`Worker.config()` is the SDK's introspection hook.)
- [ ] **AC-3c — No two workers register overlapping activities.** Computed fact: `_ACTIVITIES_FOR_QUEUE[VULN_REMEDIATION_NODE_NPM].isdisjoint(_ACTIVITIES_FOR_QUEUE[SYSTEM])`. ADR-0007's blast-radius rationale collapses if `emit_event` ends up on both pools.

### Entrypoint module + argparse

- [ ] **AC-4 — `python -m codegenie.durable.workers` is the runnable entrypoint.** `src/codegenie/durable/workers/__main__.py` exists and is callable. CLI shape: `python -m codegenie.durable.workers --kind={workflow|activity} [--queue={vuln-remediation-node-npm|system}]`. `--queue` is required iff `--kind=activity`. The test invokes the entrypoint via `subprocess.run([sys.executable, "-m", "codegenie.durable.workers", "--help"])` and asserts the help text mentions all three concrete shapes.
- [ ] **AC-4a — Invalid `--queue` value is a hard exit.** `python -m codegenie.durable.workers --kind=activity --queue=does-not-exist` exits non-zero with a typed error message naming the valid set. Test: subprocess fixture; assert exit code != 0 and the unknown-queue is named in stderr.
- [ ] **AC-4b — `--kind=workflow` rejects `--queue`.** Workflow worker has a fixed task queue identifier (`workflow`); accepting `--queue=foo` would let a contributor accidentally point the workflow worker at an activity queue. Test asserts exit non-zero on `--kind=workflow --queue=system`.

### Event loop + dev hot reload

- [ ] **AC-5 — `uvloop` installed before `asyncio.run`.** The `__main__.py` calls `uvloop.install()` before `asyncio.run(_main())` (per `phase-arch-design.md §C8 §Dependencies`). Test: monkeypatch `uvloop.install` and assert it's called before `asyncio.run`. (uvloop unavailable on Windows is out of scope per `phase-arch-design.md §Non-goals`; document but don't gate.)
- [ ] **AC-6 — Dev hot reload via `watchfiles` is opt-in via `--reload` flag, NOT the default.** Production deploys must never run `watchfiles`. Test: subprocess fixture; assert that without `--reload` the process does not import `watchfiles` (introspect via `sys.modules`-like fixture). When `--reload` is set, `watchfiles.run_process(...)` wraps `_main`. Restart envelope is `<1 s` (per `High-level-impl.md §Step 6 §Done criteria` and ADR-0007 §C8 §Internal structure ~800 ms).
- [ ] **AC-6a — Hot reload integration test.** `tests/integration/test_worker_hot_reload.py` (marked `slow`, not `bench`): start a worker with `--reload`; touch a file under `src/codegenie/durable/activities/`; assert the worker process PID changes within 2 s (`watchfiles.run_process` spawns a child). Gracefully kill the parent at test teardown.

### Graceful shutdown + signal handling

- [ ] **AC-7 — SIGTERM triggers graceful shutdown, NOT immediate exit.** A signal handler installed in `_main` sets a `shutting_down: asyncio.Event`; `worker.run()` is wrapped in a task that on event-set calls `worker.shutdown()` (Temporal SDK's graceful drain), waits for in-flight activities to complete (bounded by `DurableSettings.shutdown_grace_seconds`, default 30 s), then exits 0. Test: pytest fixture `monkeypatch`-installs a fake signal handler; sends `signal.SIGTERM`; asserts `worker.shutdown()` is awaited before process exit.
- [ ] **AC-7a — SIGINT (Ctrl-C) is identical to SIGTERM.** Both trigger drain. Dev contributors hit Ctrl-C; production K8s sends SIGTERM. The handler is the same. Parametrized test over `(signal.SIGTERM, signal.SIGINT)`.
- [ ] **AC-7b — Second SIGTERM during drain is a force-exit.** If the operator sends SIGTERM twice (the K8s pre-stop -> SIGTERM -> wait -> SIGKILL sequence), the second signal logs `worker.shutdown.forced` and `sys.exit(130)`. Prevents a hung worker holding the workflow worker pool open. Test: dispatch SIGTERM twice; assert second handler call exits non-zero.
- [ ] **AC-7c — Graceful shutdown drains `EventBatchWriter` before exiting.** Per `phase-arch-design.md §Edge cases #3`: "worker refuses graceful shutdown until drained." For activity workers on the `system` queue, the shutdown sequence awaits `EventBatchWriter.flush()` to completion *before* exiting. Test: queue 50 events; trigger shutdown; assert all 50 are flushed to Postgres (testcontainers fixture) before the process exits.

### Rolling-deploy version negotiation (no-go, fail-fast)

- [ ] **AC-8 — Worker build-id stamping for forensic replay.** Each worker registers `Worker(..., build_id=settings.build_id)` where `build_id` is `DurableSettings.build_id` (defaults to `os.environ.get("CODEGENIE_BUILD_ID", "dev")`). Test: assert the value reaches the `Worker` constructor. This is the read-only side of Phase 16's Worker Versioning — Phase 9 stamps but does NOT consume.
- [ ] **AC-8a — Different-build workers on the same workflow surface `NondeterminismError` fast (no silent retry-storm).** Per `phase-arch-design.md §Edge cases #15`: "Workflow fails fast; rollback restores compatible version." Phase 9 does NOT implement compatibility-set logic (that's Phase 16); but `tests/integration/test_rolling_deploy_version_mismatch.py` (marked `slow`) records a workflow history on build A, then runs `Replayer.run_replay_workflows` on build B with an intentionally-divergent fixture; asserts `WorkflowNondeterminismError` is raised (preserves full payload for forensic diff per S5-05). This is the negative-evidence test that the *current* answer to multi-version replay is "fail fast", with the upgrade path called out in S5-05's risk-#1 closure.

### Wiring + observable demo

- [ ] **AC-9 — `temporal-ui` round-trip.** Integration test `tests/integration/test_workers_register_task_queues.py` (marked `slow`): `make dev-up` fixture brings up the Temporal cluster; start all three worker processes via the entrypoint module; poll the Temporal `ListTaskQueues` gRPC endpoint via `Client.list_task_queues()`; assert the result includes exactly `{workflow, vuln-remediation-node-npm, system}` (and exactly the activity-name allowlist for each queue). The `High-level-impl.md §Step 6 §Done criteria` line "`temporal-ui` at `http://127.0.0.1:8233` shows the registered task queues" is operationalized by this gRPC introspection (not by scraping the UI).

### Gates

- [ ] **AC-10** — `mypy --strict src/codegenie/durable/workers/` clean.
- [ ] **AC-11** — `ruff check src/codegenie/durable/workers/ tests/unit/durable/workers/` and `ruff format --check` clean.
- [ ] **AC-12** — `make lint-imports` clean (extends the `codegenie.durable.workflows-must-be-pure` contract: `workers/__init__.py` may import workflows + activities, but workflows still may not import workers).
- [ ] **AC-13** — TDD plan's red test (no module exists) is committed before the green pass.

## Implementation outline

1. **`src/codegenie/durable/workers/_kinds.py` (NEW)**: `class WorkerKind(StrEnum)`; three members; module-level `_TASK_CLASS_QUEUE_PATTERN: re.Pattern` for the AC-1a fence.
2. **`src/codegenie/durable/workers/__init__.py` (NEW)**: `build_worker(*, kind, settings) -> Worker`; computes `_ACTIVITIES_FOR_QUEUE` at module load from the `@register_activity` registry (lazy-importable via `codegenie.durable.activities.list_activities_for_queue(kind)`); chooses `workflows=` / `activities=` per kind; passes `interceptors=[<replay-determinism-guard from S1-07>]`, `max_concurrent_activities=settings.max_concurrent_activities`, `build_id=settings.build_id`.
3. **`src/codegenie/durable/workers/__main__.py` (NEW)**: argparse with `--kind` + `--queue` + `--reload` + `--build-id`; install `uvloop`; on `--reload`, wrap `_main` in `watchfiles.run_process`; otherwise call `asyncio.run(_main(...))`. Install SIGTERM + SIGINT handlers that set an `asyncio.Event`; `_main` awaits `worker.run()` racing against the event; on event-set, calls `worker.shutdown()` and `EventBatchWriter.flush()` under `asyncio.wait_for(..., shutdown_grace_seconds)`.
4. **`src/codegenie/durable/config.py` (EXTEND from S2-02)**: add `max_concurrent_activities: int = Field(default=10, ge=2)`, `shutdown_grace_seconds: float = 30.0`, `build_id: str = "dev"`.
5. **Tests**: unit tests for `build_worker` (kind→pool mapping; activity-disjoint; `max_concurrent_activities=1` rejected); subprocess fixtures for `__main__.py` argparse paths (AC-4a, AC-4b); fence test for `_TASK_CLASS_QUEUE_PATTERN` (AC-1a); `monkeypatch` tests for signal handlers (AC-7, AC-7a, AC-7b); integration tests for hot reload (AC-6a), graceful drain (AC-7c), task-queue registration (AC-9), and version-mismatch fast-fail (AC-8a).
6. **Documentation**: `docs/development.md §Workers` section names the three concrete commands; the `make dev-up` page links into it.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/unit/durable/workers/test_build_worker.py`

The first failing test imports `build_worker` and asserts the workflow-kind worker has zero activities + both workflows registered:

```python
from codegenie.durable.config import DurableSettings
from codegenie.durable.workers import WorkerKind, build_worker
from codegenie.durable.workflows.vuln_remediation import VulnRemediationWorkflow
from codegenie.durable.workflows.multi_plugin_parent import MultiPluginParentWorkflow

def test_workflow_kind_worker_has_no_activities(settings_fixture, fake_client):
    w = build_worker(kind=WorkerKind.WORKFLOW, settings=settings_fixture, client=fake_client)
    config = w.config()
    assert config["activities"] == []
    assert set(config["workflows"]) == {VulnRemediationWorkflow, MultiPluginParentWorkflow}
    assert config["task_queue"] == "workflow"

def test_activity_pools_are_disjoint(settings_fixture, fake_client):
    vuln = build_worker(kind=WorkerKind.VULN_REMEDIATION_NODE_NPM, settings=settings_fixture, client=fake_client)
    system = build_worker(kind=WorkerKind.SYSTEM, settings=settings_fixture, client=fake_client)
    vuln_acts = {a.__temporal_activity__.name for a in vuln.config()["activities"]}
    sys_acts = {a.__temporal_activity__.name for a in system.config()["activities"]}
    assert vuln_acts.isdisjoint(sys_acts)
    assert vuln_acts == {"resolve_plugin", "build_bundle", "route", "run_vuln_subgraph", "sandbox_build_and_test", "github_open_pr"}
    assert sys_acts == {"emit_event", "resolve_blob_ref", "write_blob_ref"}
```

Why it fails: `ModuleNotFoundError: codegenie.durable.workers` — the package doesn't exist yet. The signal-handler tests fail next because `__main__.py` doesn't exist.

### Green — minimal pass
- Add `WorkerKind` enum.
- Add `build_worker` factory; compute `_ACTIVITIES_FOR_QUEUE` from the registry.
- Add `__main__.py` with argparse + uvloop + signal handlers + optional watchfiles wrap.
- Extend `DurableSettings` with the three new fields.

### Refactor
- Pull the registry-→-pool computation into `codegenie.durable.activities.list_activities_for_queue(kind: WorkerKind) -> frozenset[ActivityName]` so workers depend on the activity-registry's public surface, not its private dict (one-way dependency direction preserved per S4-08).
- Pull signal-handler installation into a tiny `_signal_handlers.py` module with a single `install_drain_handlers(event: asyncio.Event) -> None` function — keeps `__main__.py` readable and the handler logic unit-testable without subprocess fixtures.
- Add structured logs at every signal transition (`worker.shutdown.requested`, `worker.shutdown.draining`, `worker.shutdown.complete`, `worker.shutdown.forced`); these are the operator's only window into Phase-9 worker state until Phase 16's metrics land.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/durable/workers/__init__.py` | NEW — `build_worker` factory; computes activity pool from `@register_activity` registry; one-way dependency direction. |
| `src/codegenie/durable/workers/_kinds.py` | NEW — `WorkerKind(StrEnum)`; three members; the queue-name fence pattern lives here. |
| `src/codegenie/durable/workers/_signal_handlers.py` | NEW — `install_drain_handlers(event)`; testable in isolation; second-signal force-exit logic. |
| `src/codegenie/durable/workers/__main__.py` | NEW — argparse entrypoint; uvloop install; watchfiles wrap on `--reload`; signal-handler install; `worker.run` task. |
| `src/codegenie/durable/activities/__init__.py` | EXTEND — add `list_activities_for_queue(kind: WorkerKind) -> frozenset[ActivityName]` public function. |
| `src/codegenie/durable/config.py` | EXTEND — `max_concurrent_activities`, `shutdown_grace_seconds`, `build_id`. |
| `tests/unit/durable/workers/test_build_worker.py` | NEW — kind→pool mapping; activity-disjoint; `max_concurrent_activities=1` rejected; workflow worker IO-free property. |
| `tests/unit/durable/workers/test_signal_handlers.py` | NEW — SIGTERM/SIGINT trigger drain; second-signal force-exit. |
| `tests/unit/durable/workers/test_entrypoint_argparse.py` | NEW — subprocess fixtures for `--help`, invalid `--queue`, `--kind=workflow --queue=foo` rejection. |
| `tests/fence/test_task_queue_naming.py` | NEW — every `WorkerKind` value matches the ADR-0007 shape. |
| `tests/integration/test_worker_hot_reload.py` | NEW (marked `slow`) — `--reload` flag triggers child-PID change on file edit; <2 s. |
| `tests/integration/test_workers_register_task_queues.py` | NEW (marked `slow`) — `Client.list_task_queues()` includes the three queues; activity-name allowlist per queue. |
| `tests/integration/test_graceful_drain_flushes_events.py` | NEW (marked `slow`) — queue events; SIGTERM; assert flushed before exit. |
| `tests/integration/test_rolling_deploy_version_mismatch.py` | NEW (marked `slow`) — Replayer fails fast on intentional divergence; preserves full forensic payload. |
| `docs/development.md` | EXTEND — `Workers` section: three commands; `--reload` flag; graceful-shutdown contract. |

## Out of scope

- **Capability minting from K8s ServiceAccount mount** — S6-02. This story brings the workers up; S6-02 adds the per-queue Capability allowlist.
- **`TemporalVulnRemediationSut` bridge** — S6-03. This story makes activities runnable; S6-03 wires the Phase-6.5 harness through Temporal.
- **End-to-end Postgres + Temporal integration test** — S6-04. Story S6-04 exercises a full recipe-route workflow ~30 s; this story stops at "workers register and accept shutdown".
- **Worker Versioning compatibility-set logic** — Phase 16. Phase 9 stamps `build_id` but does not consume it for compatibility decisions.
- **Production deployment shape (K8s manifests, autoscaling, mTLS)** — Phase 16. Dev host-process shape only.
- **`temporal-ui` URL emitted from `make dev-up`** — cosmetic ergonomics; documented open question #4 in the manifest; may land without a story bump.

## Notes for the implementer

- **`WorkerKind` is a `StrEnum`, NOT a `Literal` union of strings.** Phase-7.5's `vuln-remediation-python-pip` lands as one additive `WorkerKind` member; `Literal` unions force every `match` site to grow. `StrEnum` keeps the value-vs-enum-symbol distinction clean (`kind.value` is the wire format Temporal sees).
- **The activity pool is computed from the registry, not hand-keyed.** If you find yourself writing `if kind == VULN_REMEDIATION_NODE_NPM: return [resolve_plugin, build_bundle, ...]` you're duplicating the `@register_activity(name=..., task_queue=...)` registration and the two will drift. Read from `codegenie.durable.activities._ACTIVITIES` (or its public `list_activities_for_queue` accessor) so adding a new activity to a queue is one `@register_activity` decoration, not two edits.
- **`workflows=[]` on activity workers is load-bearing.** Per `phase-arch-design.md §C8 §Internal structure`, the workflow worker pool is IO-free *and separate*. An activity worker that also registered workflows would pick up workflow tasks under its activity capability mint, breaking ADR-0007's blast-radius rationale. The unit test (AC-3b) catches this structurally.
- **`max_concurrent_activities` defaults to `10`** per `phase-arch-design.md §C8 §Performance envelope` ("Activity-worker concurrency capped at `max_concurrent_activities=10` per pod (default; tuned by canary)"). The `ge=2` Pydantic validator prevents `1` (workflow worker would starve waiting for an activity slot; deadlock). Per `phase-arch-design.md §Open questions §3`, Phase 8's G6 throughput canary may amend the default; that's a settings change, not a story bump.
- **`watchfiles` is dev-only — `--reload` is opt-in.** If `watchfiles` ever ends up importable in a production K8s pod's runtime closure, you've shipped a memory hog and a file-descriptor leak. The `--reload` flag gate must be enforced by import guard, not convention. AC-6's subprocess fixture asserts `watchfiles` is not in `sys.modules` without `--reload`.
- **Graceful shutdown drains `EventBatchWriter` BEFORE the worker exits.** Per `phase-arch-design.md §Edge cases #3`: "worker refuses graceful shutdown until drained." If you skip this, a SIGTERM during a high-throughput burst silently drops events on the floor — the worst Phase-9 failure mode short of chain tamper. The drain is bounded by `shutdown_grace_seconds=30 s`; over the cap, structured-log the surviving event count and exit non-zero (a hung pod is worse than a known-loss pod with an operator-visible exit code).
- **Second SIGTERM is force-exit (`sys.exit(130)`).** K8s pre-stop is SIGTERM → grace period → SIGKILL. If your handler captures both SIGTERMs and tries to drain twice, the worker hangs and K8s SIGKILLs you anyway — but with no exit-code signal to the operator. Make the second SIGTERM a deliberate force-exit so the operator sees `130` (the standard SIGINT exit code) and knows the drain was abandoned.
- **`build_id` is read-stamped, not consumed.** Phase 9's answer to multi-version replay is "fail fast"; Phase 16 lands Worker Versioning's compatibility sets. Stamping `build_id` now lets Phase 16's compat-set rollout be additive (no field renames). The Replayer fast-fail test (AC-8a) is the negative-evidence test that Phase 9's posture is honest.
- **uvloop is unavailable on Windows.** `phase-arch-design.md §Non-goals` rules out Windows-host dev; the import is guarded behind `sys.platform != "win32"`, with a structured warning that drops back to the stdlib loop on Windows. Don't add a Windows-fallback test path.
- **Don't introduce a `TemporalPort` Protocol.** Per ADR-0013: single Temporal substrate in sight ⇒ premature pluggability. `temporalio.worker.Worker` is the concrete class; treat it as the seam directly. If a future Phase wants an alternative substrate, that's an ADR amendment, not a Phase-9 abstraction.
- **The hot-reload restart envelope is `<1 s` per `High-level-impl.md §Step 6 §Done criteria` and `~800 ms` per `phase-arch-design.md §C8`.** If `watchfiles.run_process` consistently takes >1.5 s on the canary machine, the cause is likely `Worker.__init__`'s registration sweep over a slow `@register_activity` decorator list; profile and surface as a follow-up, not as a story-bump.
