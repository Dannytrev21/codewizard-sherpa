# Story S2-02 — DurableSettings + AsyncConnectionPool factory

**Step:** Step 2 — Provision Postgres + alembic + docker-compose dev surface
**Status:** Ready
**Effort:** S
**Depends on:** S2-01 (the compose ports/services this configures), S1-01 (`TaskQueueName`, `TemporalAddress`, `TemporalNamespace`, `PostgresDsn` Newtypes — references at the annotation level only)
**ADRs honored:** ADR-0011 (one pool per worker, shared with `emit_event` writer), ADR-0012 (Postgres is the workflow-spanning store the pool serves), ADR-0007 (queue names live as typed config — task-queue identity becomes the trust root in S6-02)

## Context

Every Phase-9 runtime piece — alembic, the workflow worker, activity workers, `EventBatchWriter`, `PostgresCheckpointerAdapter`, the projection folders — needs **one** source of truth for cluster addresses, Postgres DSN, pool sizes, and batch parameters. Phase-9 ADR-0012 and ADR-0011 split the event-store and the checkpointer onto the *same* Postgres, sharing one `AsyncConnectionPool` per worker process (line 43 of ADR-0011). This story ships that source of truth.

`phase-arch-design.md §C12` (lines 672–692) is the canonical contract: `DurableSettings` is a Pydantic `BaseSettings` subclass with `env_prefix="CODEGENIE_DURABLE_"`, typed fields for every operationally tunable knob, and fail-fast `ValidationError` at process start on missing required env. The pool factory is the one place that knows how to translate `DurableSettings.postgres_dsn` + `pool_minsize` + `pool_maxsize` into a live `psycopg_pool.AsyncConnectionPool`.

Why this story exists separately from S2-01 (compose) and S2-03 (alembic): the compose is config-the-runtime; alembic is config-the-schema; *this* story is config-the-application-typed. They sit in three different files and have three different audiences (Docker, Postgres, Python). Splitting keeps each diff small enough to review.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C12 — Configuration` (lines 672–692) — the canonical `DurableSettings` shape, env-prefix, fail-fast discipline.
  - `../phase-arch-design.md §C8 — Worker process model` (lines 600–609) — workers construct `DurableSettings` once at process start; per-process pool; per-K8s-pod ServiceAccount.
  - `../phase-arch-design.md §C11 — Alembic discipline` (lines 658–670) — alembic also constructs a pool against the same DSN; this story is the type contract alembic's `env.py` reads.
  - `../phase-arch-design.md §Edge case 3` (line 985) — Postgres unavailable → `psycopg.OperationalError`; the pool's behavior under failure feeds the back-pressure story.
- **Phase ADRs:**
  - `../ADRs/0011-checkpointer-backend-postgres.md` — "One `psycopg_pool.AsyncConnectionPool` per worker — shared with `emit_event` writer"; `minsize=2, maxsize=20`; `PoolTimeoutError` under burst.
  - `../ADRs/0012-event-store-topology-temporal-history-plus-postgres-events.md` — same pool serves `events.events` and `langgraph_checkpoints`.
  - `../ADRs/0007-two-task-queue-partitioning-and-expansion-by-addition.md` — `vuln-remediation-node-npm` and `system` queue names typed via `TaskQueueName`.
- **Existing code (precedent to mirror):**
  - `src/codegenie/types/identifiers.py` — `TemporalAddress`, `TemporalNamespace`, `PostgresDsn` Newtypes (added in S1-01); import them.
  - Any existing `pydantic_settings.BaseSettings` use in the repo (search `BaseSettings` in `src/codegenie/`); mirror the `model_config` style. If none exists, this is the precedent; document the pattern in the module docstring.
  - `pyproject.toml` `[tool.mypy]` settings — `strict = true` is global; the new module must pass.
- **Upstream:**
  - `psycopg_pool.AsyncConnectionPool` docs — `min_size`, `max_size`, `timeout`, `open=False` (do not open at construction; `await pool.open()` explicitly so worker bootstrap controls timing).

## Goal

Ship `src/codegenie/durable/config.py` exporting `DurableSettings` (Pydantic `BaseSettings`, env-prefix `CODEGENIE_DURABLE_`, typed and immutable after construction) and `make_pool(settings: DurableSettings) -> AsyncConnectionPool` factory; add `make dev-up` and `make dev-down` already exist (S2-01) — ensure `DurableSettings` defaults align with the compose's exposed ports so a contributor running `make dev-up && python -c "from codegenie.durable.config import DurableSettings; DurableSettings(postgres_dsn='postgresql://postgres@127.0.0.1:5432/postgres')"` succeeds.

## Acceptance criteria

- [ ] **AC-1 — `DurableSettings` shape matches §C12.** `src/codegenie/durable/config.py` exports `DurableSettings(BaseSettings)` with `model_config = SettingsConfigDict(env_prefix="CODEGENIE_DURABLE_", frozen=True)` and exactly these fields:
    - `temporal_address: TemporalAddress = TemporalAddress("127.0.0.1:7233")`
    - `temporal_namespace: TemporalNamespace = TemporalNamespace("default")`
    - `postgres_dsn: PostgresDsn` (required — no default)
    - `pool_minsize: PositiveInt = 2`
    - `pool_maxsize: PositiveInt = 20`
    - `event_batch_size: PositiveInt = 256`
    - `event_batch_flush_interval_ms: PositiveInt = 20`
    - `activity_worker_max_concurrent_activities: PositiveInt = 10`
  No other public fields. Adding one without amending §C12 + this AC must fail a fence (AC-7).
- [ ] **AC-2 — Frozen post-construction.** `settings = DurableSettings(postgres_dsn=...)`; `settings.pool_minsize = 100` raises `pydantic.ValidationError` or `dataclasses.FrozenInstanceError`-class error (Pydantic v2's `frozen=True` produces `ValidationError`). Test asserts the raise; `mypy --strict` reading the module agrees (the field assignment is flagged).
- [ ] **AC-3 — Fail-fast on missing required env.** With no `CODEGENIE_DURABLE_POSTGRES_DSN` env var set and no `postgres_dsn` argument, `DurableSettings()` raises `pydantic.ValidationError` *at construction*, not at first use. Error message names `postgres_dsn` literally. No environment-default fallback; no silent localhost guess.
- [ ] **AC-4 — `pool_minsize <= pool_maxsize` validator.** A `@model_validator(mode="after")` rejects `pool_minsize > pool_maxsize` with a typed message naming both values. Test asserts the raise with `pool_minsize=10, pool_maxsize=5`.
- [ ] **AC-5 — `make_pool` factory exists and uses the settings.** `src/codegenie/durable/config.py` exports `async def make_pool(settings: DurableSettings) -> AsyncConnectionPool` (or a sync `make_pool(settings) -> AsyncConnectionPool` that returns the unopened pool). The function passes `min_size=settings.pool_minsize`, `max_size=settings.pool_maxsize`, `conninfo=settings.postgres_dsn`, `open=False`. The caller is responsible for `await pool.open()` and `await pool.close()`. Test asserts the pool object's `min_size` / `max_size` attributes (or the keyword args, via a mock) match the settings.
- [ ] **AC-6 — Env-var override round-trip.** With `CODEGENIE_DURABLE_POOL_MAXSIZE=42` and `CODEGENIE_DURABLE_POSTGRES_DSN=postgresql://...` set, `DurableSettings().pool_maxsize == 42`. Tested via `monkeypatch.setenv`. Confirms the env-prefix wiring works for *each* knob (parametrize across all fields).
- [ ] **AC-7 — Field-set fence.** `tests/fence/test_durable_settings_fields.py` introspects `DurableSettings.model_fields` and asserts the set of field names equals the frozen set declared in the test. Adding a field without updating this fence breaks CI. (This is the "no silent field additions" enforcement — same shape as Phase-1's `_WARNING_IDS` discipline.)
- [ ] **AC-8 — `mypy --strict` clean and import-linter clean.** The new module passes `make typecheck`. `import-linter` confirms `codegenie.durable.config` does not import from `codegenie.durable.workflows`, `codegenie.durable.activities`, or `codegenie.events` (config is foundational; it imports from `codegenie.types` only).

## Implementation outline

1. Write a failing field-set fence (`tests/fence/test_durable_settings_fields.py`) declaring the exact eight field names from AC-1.
2. Create `src/codegenie/durable/__init__.py` (empty namespace module) and `src/codegenie/durable/config.py` per AC-1; use `pydantic_settings.BaseSettings` (already in `pyproject.toml`'s deps tree via langgraph; if not, add `pydantic-settings>=2`).
3. Add the `@model_validator(mode="after")` for AC-4.
4. Write `make_pool` per AC-5; do **not** open the pool — the caller controls lifecycle.
5. Write unit tests for AC-2..AC-6; use `monkeypatch.setenv` and `monkeypatch.delenv` to control env.
6. Run `make lint`, `make typecheck`, `make lint-imports`, `make test -k durable_settings`.

## TDD plan — red / green / refactor

**Red.**
- `tests/unit/durable/test_config.py::test_field_set_matches_frozen_contract` — import `DurableSettings`, assert `set(DurableSettings.model_fields.keys()) == frozenset({...eight names...})`. Fails: module doesn't exist.
- `tests/unit/durable/test_config.py::test_missing_postgres_dsn_raises_at_construction` — `monkeypatch.delenv("CODEGENIE_DURABLE_POSTGRES_DSN", raising=False); with pytest.raises(ValidationError, match="postgres_dsn"): DurableSettings()`. Fails: not implemented.
- `tests/unit/durable/test_config.py::test_pool_minsize_exceeds_maxsize_rejected` — `with pytest.raises(ValidationError, match="pool_minsize"): DurableSettings(postgres_dsn=..., pool_minsize=10, pool_maxsize=5)`.
- `tests/unit/durable/test_config.py::test_frozen_after_construction` — `s = DurableSettings(postgres_dsn=...); with pytest.raises(ValidationError): s.pool_minsize = 100`.
- `tests/unit/durable/test_config.py::test_env_override_pool_maxsize` — `monkeypatch.setenv("CODEGENIE_DURABLE_POOL_MAXSIZE", "42"); assert DurableSettings(postgres_dsn=...).pool_maxsize == 42`.
- `tests/unit/durable/test_config.py::test_make_pool_passes_sizes` — mock `psycopg_pool.AsyncConnectionPool`, call `make_pool(settings)`, assert the constructor was called with `min_size=settings.pool_minsize, max_size=settings.pool_maxsize, conninfo=settings.postgres_dsn, open=False`.

These tests verify *intent* per global Rule 9: each one fails when an obviously-wrong implementation is substituted (e.g., a `make_pool` that hardcodes sizes would still satisfy "returns a pool" but fail the parametric size assertion).

**Green.**
- Implement `DurableSettings` and `make_pool` minimally — no extra fields, no extra validators beyond AC-4.

**Refactor.**
- Move the field-set frozenset literal to a module-level `Final` so the fence test imports it instead of duplicating the list. Then verify the test still fails when a single field is removed from the literal (mutation-test the fence).
- Add a module docstring naming the env-prefix convention and citing ADR-0011 / ADR-0012 / §C12 so future readers reach the decision in one hop.

## Files to touch

- **New:**
  - `src/codegenie/durable/__init__.py` (empty namespace; one-line module docstring naming the phase)
  - `src/codegenie/durable/config.py`
  - `tests/unit/durable/__init__.py`
  - `tests/unit/durable/test_config.py`
  - `tests/fence/test_durable_settings_fields.py`
- **Modified:**
  - `pyproject.toml` — add `pydantic-settings>=2` (if not already transitively present); add `psycopg-pool>=3.2` and `psycopg[binary]>=3.2` (if not present). Update `tool.import-linter.contracts` so `codegenie.durable.config` is a "foundational" layer (no application-layer imports).

## Out of scope

- **Opening the pool.** S5-01 (`PostgresCheckpointerAdapter`) and S3-02 (`EventBatchWriter`) own pool lifecycle. This story exposes the factory; the callers run `await pool.open()` / `await pool.close()`.
- **Wiring `DurableSettings` into the alembic `env.py`.** S2-03 reads `postgres_dsn` from `DurableSettings` (or from `os.environ` directly — S2-03 chooses). This story does not import alembic.
- **Connecting workers to Temporal.** `temporal_address` and `temporal_namespace` are typed and defaulted here; S6-01 wires them into `temporalio.client.Client`. No `temporalio` import in this story.
- **K8s ServiceAccount-mount capability minting.** S6-02 reads `/var/run/secrets/codegenie/queue-identity`. `DurableSettings` does not carry capability state.
- **`CheckpointerHealth`.** A separate Pydantic model in S5-01; not added here even though it lives in the same package eventually (`codegenie.durable`).

## Notes for the implementer

- **Why one pool, not two (one for events, one for checkpoints).** ADR-0011 lines 42–43: same pool. The `EventBatchWriter`'s burst writes and the `PostgresCheckpointerAdapter`'s steady-state checkpoint writes share the connection budget; sizing the pool against the *sum* of demands is the operational truth, not two pools each undersized. The factory returns one pool; callers pass it where it's needed.
- **`open=False`.** `psycopg_pool` defaults to opening at construction; that violates "no IO in constructors" (anti-pattern row in `§Anti-patterns avoided` line 977). The caller controls the open in an `async with` or explicit lifecycle handler. The test in AC-5 can verify the kwarg.
- **`frozen=True` on the Settings.** Pydantic v2's `BaseSettings` supports `model_config = SettingsConfigDict(frozen=True)`. After-construction mutation raises `ValidationError`. This is the immutability story — `DurableSettings` is constructed once at process start and never mutated.
- **`PositiveInt` vs `int`.** Pydantic's `PositiveInt` is `Annotated[int, Gt(0)]`; using it shifts "pool size can't be zero" from a `model_validator` to a field-level constraint, which produces a cleaner error message. Same for the batch fields.
- **Don't validate the DSN's reachability at construction.** `PostgresDsn` Newtype checks string shape; *reachability* is a runtime concern surfaced as `psycopg.OperationalError` on first connect. Config validation is shape-only — fail-fast on missing values, not on unreachable databases (which would break offline dev).
- **Test isolation under `monkeypatch.setenv`.** Pydantic Settings reads env *at construction*; `monkeypatch.setenv` followed by `DurableSettings()` in the same test works. Don't cache a `DurableSettings()` at module load in test fixtures.
- **`make dev-up` integration.** This story's tests don't need Docker — they all use env injection. The integration with the compose's actual ports happens implicitly: a contributor who runs `make dev-up` and points `CODEGENIE_DURABLE_POSTGRES_DSN=postgresql://postgres@127.0.0.1:5432/postgres` at it gets a working pool. That smoke is exercised in S2-03 (alembic) and S5-01 (checkpointer integration).
- **Future fields.** When Phase 10 adds new tunables (e.g., portfolio-scan concurrency), they land in this same file — additive only — and the field-set fence (AC-7) is the discussion-forcing function. ADR-amend `§C12`, update the frozenset, land the field.
