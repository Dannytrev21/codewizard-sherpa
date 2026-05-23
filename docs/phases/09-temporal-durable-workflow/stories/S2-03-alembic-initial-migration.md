# Story S2-03 — Alembic initial migration: events schema, append-only trigger, role grants

**Step:** Step 2 — Provision Postgres + alembic + docker-compose dev surface
**Status:** Ready
**Effort:** M
**Depends on:** S2-02 (`DurableSettings.postgres_dsn` is what alembic's `env.py` reads), S2-01 (alembic runs against the compose-provided Postgres)
**ADRs honored:** ADR-0003 (per-workflow BLAKE3 chain — schema carries `prev_hash`/`row_hash`/`wf_seq`), ADR-0009 (no `pgcrypto` — `events.payload` is plain JSONB), ADR-0011 (alembic owns `events` schema only; `langgraph_checkpoints` belongs to upstream), ADR-0012 (`events.events` is the workflow-spanning store), ADR-0006 (`@critical_event` synchronous-flush is what the schema must serve under low latency)

## Context

This story is the **schema contract** every Step-3+ story depends on. `EventBatchWriter` (S3-02) writes `events.events` rows via `COPY ... FROM STDIN BINARY`; the per-workflow BLAKE3 chain (S3-01) reads `prev_hash`/`row_hash`/`wf_seq` columns this migration creates; the `audit_trail` projection (S7-01) folds rows from this table; the `application_role` grants (this story) are the trust boundary `tests/adv/test_events_append_only_enforcement.py` (S2-06) attacks; the `migrations_role` non-super-with-no-plpython3u grants are the trust boundary `tests/adv/test_alembic_migration_plpython_blocked.py` (S2-06) attacks.

The canonical SQL is `phase-arch-design.md §Postgres schema` (lines 832–880): one `events` schema, `events.events` table with append-only trigger + per-workflow `wf_seq` UNIQUE INDEX, `events.blob_refs` content-addressed table, and three role grants (`application_role` INSERT+SELECT, `read_role` SELECT-only, `migrations_role` DDL on `events` only). `ADR-0011 §Consequences` line 42 is emphatic: alembic does *not* migrate `langgraph_checkpoints` (upstream's `setup()` owns) or `temporal` (`auto-setup` image owns). The schema-ownership fence (S2-04) catches violations.

The migration is **additive only**. ADR-0011's reversibility note + ADR-0034's event-sourcing primitive mean schema changes to `events.events` past this point are expand-then-contract; Phase 9 ships exactly one alembic revision. Phase 10+ schemas land additively (new tables, new indexes — not column drops, not type changes).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Postgres schema` (lines 832–880) — the verbatim SQL: `CREATE SCHEMA events`; the columns of `events.events`; the three indexes (`events_wf_seq_idx`, `events_kind_idx`, `events_corr_idx`); the UNIQUE INDEX `events_wf_seq_uniq`; `events.blob_refs` shape; the `events.events_immutable()` trigger function + trigger; the `REVOKE`/`GRANT` block.
  - `../phase-arch-design.md §C11 — Alembic discipline` (lines 658–670) — ownership boundary, `tools/alembic-revisions.lock` SHA-pin (S2-04), `migrations_role` non-super + `pg_stat_statements`-only extension allowlist, schema-snapshot diff (S2-05).
  - `../phase-arch-design.md §Edge case 9` (line 991) — transactional DDL; expand-then-contract for multi-step (deferred).
  - `../phase-arch-design.md §Edge case 13` (line 995) — `WorkflowId` collision surfaces as `UniqueViolation` on `events_wf_seq_uniq` — this story creates the index that makes the test possible.
- **Phase ADRs:**
  - `../ADRs/0003-per-workflow-blake3-prev-hash-chain.md` — column semantics: `prev_hash BYTEA NULL` first row per workflow; `row_hash BYTEA NOT NULL`; `wf_seq` UNIQUE within `workflow_id`; portfolio rows (`workflow_id IS NULL`) are unchained.
  - `../ADRs/0009-no-pgcrypto-column-encryption.md` — `events.payload` is *plain* JSONB; this migration must not enable `pgcrypto`; allowlisted extension is `pg_stat_statements` only.
  - `../ADRs/0011-checkpointer-backend-postgres.md` §Consequences row 2 — `langgraph_checkpoints` schema is *upstream-owned*; no alembic migration touches it.
  - `../ADRs/0012-event-store-topology-temporal-history-plus-postgres-events.md` — `events.events` lives in Postgres schema `events`, owned by Phase-9 alembic.
- **Existing code (precedent to mirror):**
  - No existing alembic in this repo — this story is the precedent. Mirror canonical alembic layout: `alembic.ini`, `env.py`, `versions/0001_*.py`.
  - `src/codegenie/durable/config.py` (S2-02) — `DurableSettings.postgres_dsn` is what `env.py` reads.
- **Upstream:**
  - `alembic` docs — `env.py` async DSN config; `op.execute(...)` for raw SQL; `version_table_schema='events'` to land the `alembic_version` table inside the owned schema.

## Goal

Land `src/codegenie/events/alembic/{alembic.ini, env.py, README.md, versions/0001_create_events_schema.py}` so `alembic upgrade head` against a fresh Postgres creates the `events` schema, `events.events` and `events.blob_refs` tables, the append-only trigger, the three indexes + UNIQUE INDEX, the `application_role`/`read_role`/`migrations_role` roles with the exact grants from `§Postgres schema`, and the `alembic_version` row in `events.alembic_version`. Ship `make migrate` target; ship one integration test that runs the migration against a testcontainer Postgres and asserts every schema object exists.

## Acceptance criteria

- [ ] **AC-1 — Alembic scaffold exists.** `src/codegenie/events/alembic/alembic.ini`, `src/codegenie/events/alembic/env.py`, `src/codegenie/events/alembic/README.md`, `src/codegenie/events/alembic/versions/0001_create_events_schema.py` all present. The `README.md` declares ownership (`events` schema only; cite ADR-0011) and lists the role grants. `alembic.ini` `script_location` points at `src/codegenie/events/alembic`; `version_table_schema = events`.
- [ ] **AC-2 — `env.py` reads from `DurableSettings`.** `env.py`'s `run_migrations_online()` constructs `DurableSettings()` (or reads `os.environ["CODEGENIE_DURABLE_POSTGRES_DSN"]` directly with a documented fallback) and passes the DSN to alembic; no hardcoded DSN; no `sqlalchemy.url` literal in `alembic.ini` beyond a `driver_name`-only stanza. `mypy --strict` clean.
- [ ] **AC-3 — `0001_create_events_schema.py` matches §Postgres schema byte-for-byte semantically.** The migration creates, in order:
    1. `events` schema (`CREATE SCHEMA events`)
    2. Three roles: `application_role`, `read_role`, `migrations_role` (idempotent `DO $$ ... CREATE ROLE IF NOT EXISTS ... $$` blocks or pre-flight checks — the migration must be re-runnable against a fresh DB and against one where roles already exist)
    3. `events.events` table with the eight columns from line 838–848 (`event_id UUID PRIMARY KEY`, `workflow_id TEXT NULL`, `kind TEXT NOT NULL`, `timestamp TIMESTAMPTZ NOT NULL`, `correlation_id TEXT NULL`, `payload JSONB NOT NULL`, `prev_hash BYTEA NULL`, `row_hash BYTEA NOT NULL`, `wf_seq BIGINT NULL`)
    4. Three indexes: `events_wf_seq_idx`, `events_kind_idx`, `events_corr_idx` (partial indexes where the schema specifies `WHERE workflow_id IS NOT NULL` / `WHERE correlation_id IS NOT NULL`)
    5. UNIQUE INDEX `events_wf_seq_uniq ON (workflow_id, wf_seq) WHERE workflow_id IS NOT NULL`
    6. `events.blob_refs` table with five columns (lines 858–864): `digest BYTEA PRIMARY KEY`, `content BYTEA NOT NULL`, `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`, `content_kind TEXT NOT NULL`, `byte_len BIGINT NOT NULL`
    7. `events.events_immutable()` trigger function (`RAISE EXCEPTION 'events.events is append-only; mutation denied'`) and `events_immutable_trg` BEFORE UPDATE OR DELETE OR TRUNCATE trigger
    8. Grants: `REVOKE UPDATE, DELETE, TRUNCATE ON events.events FROM application_role`; `GRANT INSERT, SELECT ON events.events TO application_role`; `GRANT INSERT, SELECT ON events.blob_refs TO application_role`; `GRANT SELECT ON events.events TO read_role`; `GRANT USAGE ON SCHEMA events TO application_role, read_role, migrations_role`
    9. `migrations_role` is **not** super; `migrations_role` gets DDL on `events` schema only via `GRANT CREATE ON SCHEMA events`; explicitly NOT `SUPERUSER`, NOT `CREATEDB`, NOT `CREATE EXTENSION` privilege except for `pg_stat_statements` (which Postgres permits only to non-super if pre-allowed via `shared_preload_libraries`; the migration documents this in a comment).
- [ ] **AC-4 — Migration is reversible.** `downgrade()` drops everything `upgrade()` created, in reverse order. The migration is *not* a "no downgrade" stub; per ADR-0011 reversibility note (Medium), a downgrade path exists. Running `upgrade → downgrade → upgrade` against the same DB succeeds and lands the same schema state.
- [ ] **AC-5 — Integration test asserts schema exists after migrate.** `tests/integration/test_alembic_initial_migration.py` (uses `testcontainers` Postgres):
    - Spins up `postgres:16-alpine`.
    - Runs `alembic upgrade head` via `subprocess.run` *or* `alembic.command.upgrade(...)`.
    - Asserts via `information_schema` queries: schema `events` exists; tables `events.events` and `events.blob_refs` exist with the expected columns; indexes `events_wf_seq_idx`, `events_kind_idx`, `events_corr_idx`, `events_wf_seq_uniq` exist; trigger `events_immutable_trg` exists; roles `application_role`, `read_role`, `migrations_role` exist; `events.alembic_version` carries revision `0001`.
    - Asserts the trigger fires: a superuser INSERT followed by an UPDATE attempt raises a `RAISES EXCEPTION` with the immutability message.
    - Asserts `application_role` grants by connecting as that role (`SET ROLE application_role`) and confirming INSERT succeeds, UPDATE/DELETE/TRUNCATE raise.
- [ ] **AC-6 — `make migrate` target exists and runs.** `Makefile` adds `.PHONY: migrate` and `migrate:` runs `cd src/codegenie/events/alembic && alembic upgrade head` (or equivalent with `-c`). Works against the compose-provided Postgres (S2-01) when `CODEGENIE_DURABLE_POSTGRES_DSN` points at it.
- [ ] **AC-7 — Migration runs in < 10 seconds against empty Postgres.** Per §C11 line 669 — full migration history runs in < 10 s. The integration test (AC-5) measures wall-clock of the upgrade step and asserts the bound. (This is the human ergonomics floor for `make migrate`; missing it means the CI loop drags.)
- [ ] **AC-8 — No `CREATE EXTENSION` outside the allowlist.** The migration grep-asserts (in the integration test or a static-file fence) that the only `CREATE EXTENSION` line, if any, references `pg_stat_statements`. No `pgcrypto`, no `pgvector`, no `plpython3u`. The schema-snapshot diff (S2-05) catches drift.

## Implementation outline

1. **Scaffold alembic.** `cd src/codegenie/events && alembic init alembic` (or write the files by hand to control layout). Configure `alembic.ini` to use `script_location = src/codegenie/events/alembic` (relative to repo root) and `version_table_schema = events`.
2. **Wire `env.py` to `DurableSettings`.** Import `from codegenie.durable.config import DurableSettings`. In `run_migrations_online()`, construct settings and use `settings.postgres_dsn`. Branch online vs offline modes per alembic standard scaffolding.
3. **Write `versions/0001_create_events_schema.py`.** Use `op.execute(text("..."))` for the DDL blocks; raw SQL is fine here because the schema is the canonical artifact (don't over-abstract with `op.create_table` if it loses precision on the partial indexes or trigger). Set `revision = "0001"`, `down_revision = None`, `branch_labels = None`, `depends_on = None`.
4. **Write `downgrade()`.** Reverse order: drop trigger, drop function, drop indexes, drop tables (`events.events`, `events.blob_refs`), drop roles (`DROP ROLE IF EXISTS`), drop schema (`DROP SCHEMA events CASCADE`). Idempotent.
5. **Write `make migrate` target** in `Makefile` (top-level). The target reads `CODEGENIE_DURABLE_POSTGRES_DSN`; if unset, it points at the compose default (`postgresql://postgres:postgres@127.0.0.1:5432/postgres`) and emits a warning.
6. **Write the integration test.** Use `testcontainers.postgres.PostgresContainer("postgres:16-alpine")`; pass its `get_connection_url()` into the alembic invocation via env override.
7. **Write `README.md`** declaring ownership, citing ADR-0011 and ADR-0012, naming each role and its grants.

## TDD plan — red / green / refactor

**Red.**
- `tests/integration/test_alembic_initial_migration.py::test_schema_after_upgrade` — start container, run upgrade, query `information_schema.schemata` for `events`. Fails: migration file doesn't exist.
- `tests/integration/test_alembic_initial_migration.py::test_events_table_columns` — query `information_schema.columns` for `events.events`; assert the 9 columns with the right types. Fails.
- `tests/integration/test_alembic_initial_migration.py::test_append_only_trigger_blocks_update` — superuser INSERTs a row, then UPDATE raises a `psycopg.errors.RaiseException` whose `pgerror` includes `"append-only"`.
- `tests/integration/test_alembic_initial_migration.py::test_application_role_can_insert_cannot_update` — `SET ROLE application_role`; INSERT succeeds; UPDATE / DELETE / TRUNCATE each raise `psycopg.errors.InsufficientPrivilege`. **This is the load-bearing trust assertion** — without it, the append-only story is decorative.
- `tests/integration/test_alembic_initial_migration.py::test_unique_index_blocks_duplicate_wf_seq` — INSERT two rows with the same `(workflow_id, wf_seq)`; the second raises `psycopg.errors.UniqueViolation`. Confirms edge case 13.
- `tests/integration/test_alembic_initial_migration.py::test_blob_refs_dedupes_on_digest_pk` — INSERT two rows with the same `digest`; second raises `UniqueViolation` (or, more idiomatic for S3-05, the writer uses `ON CONFLICT DO NOTHING` — but the PK shape is what makes that possible; assert the PK).
- `tests/integration/test_alembic_initial_migration.py::test_downgrade_reverses` — upgrade, downgrade, query `information_schema.schemata` for `events` → not present.
- `tests/integration/test_alembic_initial_migration.py::test_upgrade_runs_under_10s` — `start = time.monotonic(); run upgrade; assert time.monotonic() - start < 10.0`.

These tests verify the schema **as the consumer perceives it** (the writer trying to write; the reader trying to query) — per global Rule 9, they would fail under an obviously-wrong implementation (e.g., a migration that creates the table without the trigger would pass the column test but fail the append-only test).

**Green.**
- Write the migration; run the tests one at a time; resist the urge to write all the DDL before any test passes. Each `op.execute(text("CREATE ..."))` block satisfies one or two tests.

**Refactor.**
- Pull the DDL into a single multi-statement string within `upgrade()` if the granularity becomes noise — but keep `op.execute` per logical block for review clarity.
- Move the `information_schema` query helpers into a tiny test-only module if the integration test grows past ~200 lines; otherwise keep them inline.
- Document in the migration file's docstring which AC each block satisfies, so a future reader correlates the schema to the contract.

## Files to touch

- **New:**
  - `src/codegenie/events/__init__.py` (empty namespace; one-line docstring naming the event-log home)
  - `src/codegenie/events/alembic/__init__.py` (empty; alembic doesn't require it but Python tooling does)
  - `src/codegenie/events/alembic/alembic.ini`
  - `src/codegenie/events/alembic/env.py`
  - `src/codegenie/events/alembic/script.py.mako` (alembic's standard template)
  - `src/codegenie/events/alembic/versions/__init__.py` (empty)
  - `src/codegenie/events/alembic/versions/0001_create_events_schema.py`
  - `src/codegenie/events/alembic/README.md`
  - `tests/integration/test_alembic_initial_migration.py`
- **Modified:**
  - `Makefile` — add `.PHONY: migrate` and the `migrate:` target.
  - `pyproject.toml` — add `alembic>=1.13` and `testcontainers[postgres]>=4` (the latter under `dev` extras only).

## Out of scope

- **`tools/alembic-revisions.lock` SHA-pin.** S2-04 owns. This story creates the file the lock will pin.
- **Schema-snapshot diff (`tests/fence/test_alembic_schema_snapshot.py`).** S2-05 owns. This story produces the schema the snapshot will baseline.
- **`migrations_role` plpython3u block adversarial.** S2-06 owns. This story creates the role; S2-06 attacks it.
- **`application_role` UPDATE/DELETE adversarial.** S2-06 owns the adversarial extras; this story's AC-5 has the *positive* trust test (role can do what it should) — adversarial tests go further.
- **`langgraph_checkpoints` schema.** Upstream's `PostgresSaver.setup()` (S5-01) creates it. This story explicitly does *not* touch it.
- **`temporal` schema.** `temporalio/auto-setup` image creates it. This story explicitly does *not* touch it.
- **Phase 10 schema additions.** Future migrations are additive; this story does not pre-bake any column "for Phase 10".

## Notes for the implementer

- **`CREATE ROLE IF NOT EXISTS` does not exist in Postgres.** Use the `DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='application_role') THEN CREATE ROLE application_role; END IF; END $$;` idiom. The integration test must work against a fresh container (roles don't exist) and against a re-run (roles already exist).
- **Why partial indexes on `wf_seq_idx` and `corr_idx`.** Portfolio rows have `workflow_id IS NULL` and `correlation_id IS NULL`; partial indexes skip them. The UNIQUE INDEX `events_wf_seq_uniq` *must* be partial because two portfolio rows can both have `(NULL, NULL)` which is allowed (Postgres treats NULLs as distinct in UNIQUE; the partial-index `WHERE workflow_id IS NOT NULL` makes the intent explicit and ergonomic).
- **`BYTEA` vs `TEXT` for hashes.** ADR-0003 and §Postgres schema use `BYTEA`; the BLAKE3 hash is raw bytes, not hex. The `EventBatchWriter` (S3-02) passes raw `bytes`; the `audit_trail` projection (S7-01) reads raw `bytes`. Do *not* introduce a `TEXT`-encoded hex column — that's the wrong default and S3-01 will need to undo it.
- **`payload JSONB`, not `JSON`.** JSONB gives Postgres-side indexability if Phase 10/13's projections need it; JSON keeps surface compatibility. JSONB is correct here per the §Postgres schema; do *not* downgrade.
- **`event_id UUID PRIMARY KEY` is application-generated**, not `gen_random_uuid()` default. S3-01's writer mints the UUID before the COPY; the table has no DEFAULT. Don't add `DEFAULT gen_random_uuid()` (which would need `pgcrypto` — ADR-0009 violation).
- **`alembic_version` schema placement.** Default alembic puts `alembic_version` in `public`; this story configures `version_table_schema = events` so the row lives inside the owned schema. Test asserts this.
- **`make migrate` running against the compose Postgres.** First time you run it after `make dev-up`, the migration creates everything. Subsequent runs (no new versions) are no-ops. The `migrate` target prints the resulting head revision.
- **Why no `op.create_table` ORM-style.** The raw SQL is the canonical artifact (the §Postgres schema block is the source of truth); abstracting it via SQLAlchemy types loses precision (partial indexes, triggers, role grants don't translate cleanly). Stay close to the SQL.
- **What S2-04 (the lock) needs from you.** A committed migration file. After your file lands, S2-04 generates the SHA into `tools/alembic-revisions.lock`. Do **not** modify the file after S2-04 lands; the lock catches drift.
- **What S2-05 (the snapshot diff) needs from you.** A schema that the snapshot test can `pg_dump --schema-only --no-owner` and check in. Your file produces; S2-05 baselines.
- **Why transactional DDL matters.** Postgres runs DDL inside a transaction by default. If any block in `upgrade()` fails, the whole migration rolls back — no half-created schema. Don't add explicit transaction control (no `BEGIN`/`COMMIT` in your `op.execute` strings); alembic owns the transaction.
- **The `psycopg.errors.InsufficientPrivilege` check in AC-5** is the load-bearing security assertion of Phase 9. Without it, ADR-0009's "secrets stay out of the payload" defense and ADR-0003's "tamper blast radius is one workflow" defense both rest on a role boundary that was never tested. Don't skip it; don't loosen it.
