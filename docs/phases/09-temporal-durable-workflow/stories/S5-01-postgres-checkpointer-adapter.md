# Story S5-01 — `PostgresCheckpointerAdapter` wrapping `PostgresSaver` + `health()` translation

**Step:** Step 5 — Postgres checkpointer adapter + workflow definitions
**Status:** Ready
**Effort:** M
**Depends on:** S2-03 (Postgres + alembic events schema migrated), S1-06 (`LangGraphCheckpointerPort` Protocol + `CheckpointerHealth` record), S2-02 (`DurableSettings` + `AsyncConnectionPool` factory)
**ADRs honored:** Phase 9 ADR-0011 (Postgres checkpointer; genuine Adapter — translation not forwarder); Phase 9 ADR-0001 (Phase-6 SQLite cutover policy — drain window discipline); resolves production ADR-0016 (checkpointer backend) Deferred → Accepted; Phase 9 ADR-0013 (no Temporal port abstraction — same single-substrate logic applies to checkpointer choice).

## Context

The Phase-6 SHERPA subgraph runs inside the fat `run_vuln_subgraph` Activity (ADR-0010). When the activity worker is SIGKILLed mid-subgraph, the activity must resume on a *fresh* worker at the same LangGraph node. Phase-6's SQLite saver cannot serve this — its checkpoint file lives on one host. ADR-0011 resolves this by adopting `langgraph_checkpoint_postgres.PostgresSaver` via a thin `PostgresCheckpointerAdapter` that wraps it and exposes the `LangGraphCheckpointerPort` Protocol from S1-06. The Adapter earns its name (per critic-3 on [B] in the design pass — single-implementation Adapters that forward methods are anti-pattern) by adding a `health() -> CheckpointerHealth` translation the upstream class does not expose: `pool_in_use`, `pool_idle`, `last_write_age_seconds`. The Adapter does NOT own the `langgraph_checkpoints` Postgres schema — upstream's `PostgresSaver.setup()` does. This story ships the Adapter, the schema bootstrap call, the health-translation logic, and the pool-exhaustion failure behavior.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C4 — Postgres checkpointer adapter (codegenie.durable.checkpointer)` — Adapter interface, `CheckpointerHealth` shape, ownership-boundary discipline, pool sizing envelope (p95 < 10 ms with `min=2, max=2×concurrent-activities`).
  - `../phase-arch-design.md §Design patterns applied #5` — "Adapter (genuine translation, not forwarder)" — the rationale for the `health()` translation method.
  - `../phase-arch-design.md §Tradeoffs (consolidated)` — checkpointer row.
- **Phase ADRs:**
  - `../ADRs/0011-checkpointer-backend-postgres.md` — full decision + consequences. Note: "schema ownership is clean: `langgraph_checkpoints` owned by upstream's `setup()`, not by Phase-9 alembic."
  - `../ADRs/0001-phase-6-sqlite-checkpointer-cutover-policy.md` — drain-window discipline; existing Phase-6 workflows continue on SQLite during cutover.
  - `../ADRs/0013-no-temporal-port-abstraction.md` — single-substrate principle; the Port + Adapter shape exists because of the `health()` translation, not premature pluggability.
- **Production ADRs:**
  - `docs/production/adrs/0016-checkpointer-backend.md` — Deferred entry; this story's evidence promotes it to Accepted.
- **Implementation plan:**
  - `../High-level-impl.md §Step 5 — Postgres checkpointer adapter + workflow definitions` — features delivered + done criteria.
- **Existing code seams:**
  - `src/codegenie/durable/checkpointer.py` (created in S1-06; this story adds the concrete Adapter class beside the Protocol).
  - `src/codegenie/durable/config.py` (created in S2-02; consumes `DurableSettings.postgres_dsn`, `pool_minsize`, `pool_maxsize`).
  - `src/codegenie/types/identifiers.py` (S1-01) — `WorkflowId` Newtype used in checkpoint thread IDs.
- **Upstream:** `langgraph-checkpoint-postgres` README; `psycopg_pool.AsyncConnectionPool` docs (pool-stats surface).

## Goal

Ship `PostgresCheckpointerAdapter` in `src/codegenie/durable/checkpointer.py` that implements `LangGraphCheckpointerPort`, wraps `langgraph_checkpoint_postgres.PostgresSaver`, and exposes a `health() -> CheckpointerHealth(pool_in_use, pool_idle, last_write_age_seconds)` translation the upstream Saver does not provide. The Adapter calls `PostgresSaver.setup()` exactly once at first use to bootstrap the `langgraph_checkpoints` schema (upstream-owned; Phase-9 alembic does not migrate it). Pool exhaustion surfaces as `psycopg.PoolTimeoutError` after the configured `pool_timeout` (default 5 s) and is left for the caller's `RetryPolicy` to handle.

## Acceptance criteria

### A — Package surface + Protocol conformance

- [ ] **AC-A1** `src/codegenie/durable/checkpointer.py` contains `class PostgresCheckpointerAdapter` alongside the `LangGraphCheckpointerPort` Protocol from S1-06. `__all__` (or the module's explicit re-export set in `src/codegenie/durable/__init__.py`) includes `PostgresCheckpointerAdapter` and `CheckpointerHealth` but does NOT include `PostgresSaver` (upstream type stays internal).
- [ ] **AC-A2** `isinstance(adapter, LangGraphCheckpointerPort)` is `True` — the Adapter is a structural Protocol implementer. A `tests/fence/test_checkpointer_port_conformance.py` test asserts `PostgresCheckpointerAdapter` satisfies the Protocol via `typing.get_type_hints` introspection on the two methods (`saver`, `health`).
- [ ] **AC-A3** Constructor signature is exactly `def __init__(self, *, pool: AsyncConnectionPool) -> None`. The pool is dependency-injected — the Adapter never creates its own pool. (Matches `phase-arch-design.md §C4 dependencies`.)

### B — `saver()` delegation + `setup()` bootstrap

- [ ] **AC-B1** `adapter.saver()` returns a `langgraph_checkpoint_postgres.PostgresSaver` instance bound to the injected pool. Calling `saver()` twice returns the *same* instance (the Adapter caches the upstream Saver — re-creating it on each call would re-run `setup()` thrash).
- [ ] **AC-B2** On first `saver()` invocation, the Adapter calls `await PostgresSaver.setup(pool)` (or the upstream-equivalent bootstrap entrypoint per the pinned version) exactly once and the `langgraph_checkpoints` schema becomes queryable. Second `saver()` call does NOT re-run `setup()` (idempotency check via call-count assertion on a spy).
- [ ] **AC-B3** Schema-ownership fence: `tests/fence/test_alembic_owns_only_events_schema.py` (S2-04) remains green — *no* Phase-9 alembic migration references `langgraph_checkpoints.*`. AC verified by re-running the fence after S5-01 lands.
- [ ] **AC-B4** Upstream version pin: `pyproject.toml` carries `langgraph-checkpoint-postgres == <pinned-version>` (pin recorded in story `_attempts/` log; bumps are intentional). Test asserts the importable version matches the pin.

### C — `health()` translation (load-bearing — earns the Adapter pattern name)

- [ ] **AC-C1** `adapter.health()` returns a `CheckpointerHealth` Pydantic model (`frozen=True, extra="forbid"`, defined in S1-06) with exactly these fields: `pool_in_use: int`, `pool_idle: int`, `last_write_age_seconds: float`. No extra fields; no upstream type leakage.
- [ ] **AC-C2** `pool_in_use` and `pool_idle` are derived from `AsyncConnectionPool` stats (typically `pool.get_stats()`'s `requests_num`/`pool_size` / `pool_available` fields per `psycopg_pool` docs; pick the pair that gives "currently-checked-out" vs "currently-idle-in-pool"). Test seeds a pool with `min=2,max=4`, checks out 2 connections, asserts `pool_in_use == 2` and `pool_idle in {0, 1, 2}` (depending on `min`).
- [ ] **AC-C3** `last_write_age_seconds` is the wall-clock seconds since the adapter's most recent successful checkpoint write. Initial value (before any write) is `float("inf")` — a sentinel that operator dashboards can format distinctly. After a checkpoint write, the value drops to ≤ 1.0 within the same test tick.
- [ ] **AC-C4** `health()` is non-blocking and side-effect-free apart from reading internal counters; concurrent `health()` calls from N coroutines do not deadlock and do not check out a Postgres connection (test asserts `pool_in_use` is unchanged before/after a `health()` call when no real workload is in flight).

### D — Pool exhaustion + failure behavior

- [ ] **AC-D1** Integration test (testcontainers Postgres) with `pool_minsize=1, pool_maxsize=1, pool_timeout=0.5`: hold the single connection in a long-running query; concurrent checkpoint write raises `psycopg.PoolTimeoutError` within ~0.5 s. The Adapter does NOT swallow the error or wrap it in a custom exception — it propagates verbatim so Temporal's `RetryPolicy` sees the upstream type (ADR-0011 §Consequences).
- [ ] **AC-D2** After `PoolTimeoutError`, `adapter.health()` still works (no broken state): `pool_in_use == 1, pool_idle == 0`. The error is transient; subsequent successful writes update `last_write_age_seconds`.
- [ ] **AC-D3** Upstream checkpoint-schema bump (simulated by monkeypatching `PostgresSaver.SCHEMA_VERSION` or similar pinned-version sentinel) is caught by `tests/fence/test_langgraph_checkpoint_postgres_pin.py`: importing the upstream module asserts its `__version__` matches the `pyproject.toml` pin; mismatch fails CI (per ADR-0011 §Consequences "CI's pinned-version test catches schema bumps before merge").

### E — Concurrency + correctness

- [ ] **AC-E1** Integration test: 20 concurrent `WorkflowId`s each write 10 checkpoints via the Adapter against a shared pool (`min=2,max=20`); all 200 checkpoints commit; `health().pool_idle + health().pool_in_use == 20` (total pool size invariant); no `PoolTimeoutError`.
- [ ] **AC-E2** Resume test: write a checkpoint for `WorkflowId("WF-A")` at LangGraph node N; create a fresh `PostgresCheckpointerAdapter` instance against the same DSN; load the checkpoint for `WF-A`; assert byte-identical state. This is the cross-process resume contract — the load-bearing semantic that makes ADR-0011's "activity worker SIGKILL → resume on any worker" claim real.
- [ ] **AC-E3** No connection leak: 1024 sequential `with PostgresCheckpointerAdapter(...) as adapter: adapter.saver().put(...)` cycles do not raise `OSError: Too many open files`. (Context-manager support is via the pool, not the Adapter — assert pool lifecycle is correct.)

### F — Cold-start + module purity

- [ ] **AC-F1** `import codegenie.durable.checkpointer` does NOT load `langgraph_checkpoint_postgres` or `psycopg` into `sys.modules`. Both are lazy-imported inside `__init__` / `saver()` / `health()` as needed. Cold-start fence test under `tests/fence/test_checkpointer_cold_start.py` snapshots `sys.modules` before/after the import and asserts the absence.
- [ ] **AC-F2** No `import codegenie.durable.workflows` anywhere in `src/codegenie/durable/checkpointer.py` (one-way dependency — checkpointer is consumed by activities, not workflows).

### G — Gates

- [ ] **AC-G1** `ruff format`, `ruff check`, `mypy --strict src/codegenie/durable/checkpointer.py` clean.
- [ ] **AC-G2** `make lint-imports` green; the `codegenie.durable.workflows-must-be-pure` import-linter contract (S1-07) still rejects `from codegenie.durable.checkpointer import ...` inside `src/codegenie/durable/workflows/*.py` (workflows do not see the checkpointer directly — only via the activity boundary).
- [ ] **AC-G3** Per-submodule cold-start fence stays green (`tests/fence/test_per_submodule_cold_start.py` from existing infra).

## Implementation outline

1. **Edit `src/codegenie/durable/checkpointer.py` (created in S1-06).**
   - Keep the existing `LangGraphCheckpointerPort` Protocol + `CheckpointerHealth` Pydantic model from S1-06 untouched.
   - Add `class PostgresCheckpointerAdapter:` with `__init__(self, *, pool: AsyncConnectionPool) -> None` storing `self._pool = pool`, `self._saver: PostgresSaver | None = None`, `self._setup_done: bool = False`, `self._last_write_ts: float = float("-inf")`.
   - `def saver(self) -> PostgresSaver:` (lazy-imports `from langgraph_checkpoint_postgres import PostgresSaver` inside the function; lazy-imports `psycopg_pool` only via the injected pool's type, no top-level import). On first call: instantiate `PostgresSaver(pool=self._pool)`; await `setup` (if upstream's API is async, wrap in `asyncio.run_coroutine_threadsafe` or expose an `async setup()` method on the Adapter — *prefer the async path*; AC-B2 verifies once-only).
   - `def health(self) -> CheckpointerHealth:` reads `self._pool.get_stats()` (or whatever the pinned `psycopg_pool` exposes); computes `time.monotonic() - self._last_write_ts` (use `monotonic` to avoid wall-clock skew); returns `CheckpointerHealth(pool_in_use=..., pool_idle=..., last_write_age_seconds=...)`.
   - Wrap the upstream Saver's `put` / `aput` to update `self._last_write_ts = time.monotonic()` on success. Concrete shape: subclass `PostgresSaver` *only if necessary*; preferred shape is a thin wrapper class that delegates and notes the write time — keep the Adapter genuine (translation) not a deep subclass.
2. **Hook `setup()` into the bootstrap path.**
   - Make `setup()` idempotent via the `self._setup_done` flag (set after first call). A second `saver()` call is `if self._setup_done: return self._saver` then `self._setup_done = True; await PostgresSaver.setup(self._pool); return self._saver`.
3. **Add `pyproject.toml` entry.**
   - `langgraph-checkpoint-postgres == <pin>` (record the pin in `_attempts/S5-01.md`).
   - Add to the `dev` extra or a new `durable` extra per `DurableSettings`/`AsyncConnectionPool` infra precedent.
4. **Add the version-pin fence.**
   - `tests/fence/test_langgraph_checkpoint_postgres_pin.py` imports the upstream `__version__`; asserts it matches the `pyproject.toml` pin (parse via `importlib.metadata.version` and a small `toml`/`tomllib` read).
5. **Add the cold-start fence.**
   - `tests/fence/test_checkpointer_cold_start.py` — same shape as the Phase-3 vuln-index cold-start test; assert no `langgraph_checkpoint_postgres` or `psycopg` in `sys.modules` after `import codegenie.durable.checkpointer`.
6. **Add the Protocol-conformance fence.**
   - `tests/fence/test_checkpointer_port_conformance.py` — assert `isinstance(PostgresCheckpointerAdapter(pool=...), LangGraphCheckpointerPort)` using a stub pool; assert the two methods' signatures via `inspect.signature`.

## TDD plan — red / green / refactor

### Red

**Test file: `tests/unit/durable/test_checkpointer_adapter.py`** (unit-level — uses a stub `AsyncConnectionPool` to exercise the Adapter without Postgres)

- `test_saver_returns_same_instance_on_repeat_call` — assert identity equality.
- `test_setup_called_exactly_once` — patch `PostgresSaver.setup` with a spy; call `saver()` 3 times; assert call count `== 1`.
- `test_health_initial_state` — fresh Adapter; `health().last_write_age_seconds == float("inf")`; `pool_in_use == 0`; `pool_idle == stub_pool.idle_count`.
- `test_health_after_write_updates_age` — fake a `put` call; assert `health().last_write_age_seconds < 1.0`.
- `test_health_is_non_blocking` — spawn 10 concurrent `health()` coroutines; assert all return in < 100 ms; assert `pool_in_use` is unchanged.
- `test_adapter_satisfies_port_protocol` — `assert isinstance(adapter, LangGraphCheckpointerPort)`.
- `test_no_postgres_saver_in_sys_modules_at_import` — drop cached modules; `import codegenie.durable.checkpointer`; assert `langgraph_checkpoint_postgres` not in `sys.modules`.

**Test file: `tests/integration/durable/test_checkpointer_postgres.py`** (testcontainers Postgres; marked `@pytest.mark.integration`)

- `test_setup_creates_langgraph_checkpoints_schema` — fresh PG; instantiate Adapter; call `saver()`; assert `langgraph_checkpoints` schema exists.
- `test_alembic_does_not_own_langgraph_checkpoints` — run `make migrate` (Phase-9 alembic); assert `langgraph_checkpoints` schema is *not* present (only `events` schema is). Adapter's `saver()` call is what creates it.
- `test_pool_exhaustion_yields_psycopg_pool_timeout_error` — `pool_minsize=1, pool_maxsize=1, pool_timeout=0.5`; hold conn via `pg_sleep(2.0)`; concurrent checkpoint write raises `psycopg.PoolTimeoutError` within 1.0 s wall-clock.
- `test_20_concurrent_workflows_200_checkpoints_no_pool_timeout` — concurrency invariant test.
- `test_cross_process_resume_state_byte_identical` — process A writes checkpoint for `WF-A`; process B (fresh Adapter, same DSN) loads `WF-A` checkpoint; bytes equal.
- `test_no_fd_leak_1024_open_close` — regression test.

**Test file: `tests/fence/test_langgraph_checkpoint_postgres_pin.py`**

```python
from importlib.metadata import version
import tomllib
from pathlib import Path

def test_langgraph_checkpoint_postgres_version_matches_pin():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    deps = pyproject["project"]["dependencies"]
    pin_line = next(d for d in deps if d.startswith("langgraph-checkpoint-postgres"))
    pinned_version = pin_line.split("==")[1].strip()
    assert version("langgraph-checkpoint-postgres") == pinned_version
```

**Test file: `tests/fence/test_checkpointer_port_conformance.py`**

```python
from codegenie.durable.checkpointer import LangGraphCheckpointerPort, PostgresCheckpointerAdapter
import inspect

def test_adapter_implements_protocol(stub_pool):
    adapter = PostgresCheckpointerAdapter(pool=stub_pool)
    assert isinstance(adapter, LangGraphCheckpointerPort)  # structural check

def test_health_method_signature():
    sig = inspect.signature(PostgresCheckpointerAdapter.health)
    assert sig.return_annotation.__name__ == "CheckpointerHealth"
```

### Green

Implement per §Implementation outline. Expected size: ~120 lines (most is delegation + the `_last_write_ts` book-keeping). The upstream `PostgresSaver` does the heavy lifting.

### Refactor

- Extract the pool-stats translation into `_pool_health_snapshot(pool) -> tuple[int, int]` — pure helper; testable without Postgres.
- Consider exposing `async setup()` on the Adapter as an explicit no-op shortcut for callers who want to bootstrap eagerly at worker startup (S6-01 may use this).
- Add a `__repr__` showing `(pool_size, setup_done, last_write_age)` for operator debug.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/durable/checkpointer.py` | Add `PostgresCheckpointerAdapter` (Protocol + `CheckpointerHealth` already from S1-06) |
| `pyproject.toml` | Add `langgraph-checkpoint-postgres == <pin>` runtime dep |
| `tests/unit/durable/test_checkpointer_adapter.py` | Unit-level Adapter tests with stub pool |
| `tests/integration/durable/test_checkpointer_postgres.py` | Postgres-backed integration tests (testcontainers) |
| `tests/fence/test_checkpointer_port_conformance.py` | Protocol-conformance fence |
| `tests/fence/test_checkpointer_cold_start.py` | Cold-start fence |
| `tests/fence/test_langgraph_checkpoint_postgres_pin.py` | Upstream version-pin fence |

## Out of scope

- **Multi-region Postgres / replica routing.** Phase 16 deployment hardening will land it; Phase 9 ships single-primary.
- **Checkpoint TTL / GC.** Upstream `PostgresSaver` does not GC; Phase 10/13 may add a projection-driven sweeper. Don't ship GC logic here.
- **`SqliteSaver` removal.** Per ADR-0001, the Phase-6 SQLite saver continues to drain existing workflows during the cutover window. This story does *not* delete `codegenie.sherpa.vuln.checkpointer` (Phase 6).
- **`health()` as an HTTP endpoint.** Operator dashboards are Phase 13 (projections + observability); Phase 9 exposes the typed record only.
- **Checkpoint encryption at rest.** ADR-0009 (no pgcrypto column encryption) — out of scope; rely on Postgres-level disk encryption + Capability discipline.
- **Pool sizing autotune.** S2-02 ships static `minsize=2, maxsize=20`; the canary baseline in S8-04 drives any future re-tuning.

## Notes for the implementer

- **The Adapter pattern claim is load-bearing for ADR-0011.** Critic-3 on the [B] design attacked single-implementation Adapters as forwarders ("`PostgresCheckpointerAdapter.saver()` is `return self._inner.saver()` — what does the Adapter buy?"). The answer is `health()` — a translation method that does NOT exist on upstream's `PostgresSaver` but is essential for operator dashboards. If a future refactor temptation is "just expose `PostgresSaver` directly and skip the Adapter," reject it — the Protocol seam + `health()` is the contract.
- **`setup()` idempotency is essential.** Upstream's `setup()` is `CREATE SCHEMA IF NOT EXISTS` (idempotent), but calling it on every `saver()` request would round-trip Postgres needlessly. The `self._setup_done` flag is the cache.
- **`last_write_age_seconds = float("inf")` initial value is intentional.** Operator dashboards format `inf` as "never written"; a `0.0` initial value would be misleading. The `last_write_age_seconds` is wall-clock since the *Adapter's* lifetime, not since the database row was inserted (which is what a projection would show).
- **`time.monotonic()`, not `time.time()`.** Wall-clock can jump backwards on NTP sync; `monotonic()` is strictly increasing. The `health()` value is for operator humans; sub-second precision is fine.
- **Do NOT subclass `PostgresSaver` deeply.** The temptation is to override `put` / `aput` and inject the timestamp update. Preferred shape: a thin wrapper class instance with `__getattr__` delegating unknowns; explicit overrides for the methods that need timestamp tracking. Keeps the Adapter surface obviously small.
- **Connection-pool sharing with `EventBatchWriter`.** Per ADR-0011 §Consequences: "The Adapter takes one `psycopg_pool.AsyncConnectionPool`; the same pool is shared with `EventBatchWriter` for `emit_event`." This story doesn't wire that integration (S3-02 owns the batch writer); just note that the pool is dependency-injected so the worker bootstrap (S6-01) can share one pool across both.
- **Lazy import of `langgraph_checkpoint_postgres` is load-bearing for cold-start.** Production ADR-0005's "no LLM SDK in `--help` closure" applies by analogy — `--help` should not pay for the upstream import. The `import langgraph_checkpoint_postgres` lives inside `saver()`, not at module top.
- **Version pin discipline.** Upstream `langgraph-checkpoint-postgres` has had checkpoint-format bumps in the past (per the upstream changelog); the version-pin fence (AC-D3) is the early-warning system. If a bump lands, the fence fires; the dev intentionally updates the pin AND regenerates any cross-process resume test fixtures (AC-E2).
- **Production ADR-0016 promotion.** When this story ships GREEN, the executor's attempt log entry should reference the docs/production/adrs/0016-checkpointer-backend.md evidence row update (the production ADR's "evidence" subsection gets a Phase-9 row). The promotion itself is a one-line edit; mention it in `_attempts/S5-01.md`.
- **Deferred design opportunities** (record in attempt log, don't implement here): (a) `RedisCheckpointerAdapter` against a hypothetical Redis-backed Saver — defer to Phase 16 if needed; (b) `health()` returning a richer `CheckpointerHealth` shape with histograms — Phase 13 observability is the natural home; (c) read-replica routing for `aget` calls — Phase 16.
