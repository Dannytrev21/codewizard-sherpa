# Story S2-06 — Adversarial: append-only enforcement + plpython3u block

**Step:** Step 2 — Provision Postgres + alembic + docker-compose dev surface
**Status:** Ready
**Effort:** S
**Depends on:** S2-03 (the migration creates the roles + trigger this story attacks), S2-04 (the static fence already rejects plpython3u in checked-in migrations; this story attacks the *runtime* path with an adversarial migration that bypasses static checks)
**ADRs honored:** ADR-0009 (anti-`pgcrypto` rationale extends to anti-`plpython3u`; this story is the runtime-evidence layer the critic-3-on-[S] demanded), ADR-0011 (the role-grant boundary this story stress-tests), ADR-0003 (append-only enforcement is what gives the per-workflow BLAKE3 chain its tamper-evidence property — without it, the chain is decorative)

## Context

The roadmap's G10 (alembic supply-chain integrity) and the per-workflow tamper-detection story (ADR-0003 + S3-04's chain-verify) both rest on a single runtime claim: **the `application_role` cannot mutate `events.events` rows after insertion**. The static fences (S2-04: text grep, S2-05: schema snapshot) catch *check-in-time* attacks; this story catches *runtime* attacks where a contributor either bypasses the static fence (e.g., dynamic SQL constructed in Python and `op.execute`ed) or assumes the role boundary is decorative ("the trigger will protect us anyway").

Phase-9 `phase-arch-design.md §Path to production end state — Test plan` (lines 1057–1063) names two adversarial tests:
- `test_events_append_only_enforcement.py` — `application_role` UPDATE/DELETE/TRUNCATE raises.
- `test_alembic_migration_plpython_blocked.py` — a `CREATE FUNCTION ... LANGUAGE plpython3u` migration **must fail at migration time** because `migrations_role` is non-super. This is the critic-3-on-[S] defeat: the security-first design's `pgcrypto` proposal was attacked on the basis that "every projection holds the key"; the symmetric attack on Phase 9 is "an attacker writes a `plpython3u` function that reads `events.payload`" — preventing this *at migration time* is the structural defense.

S2-03's migration created the roles; S2-04's static fence rejects malicious *text*; S2-05's snapshot catches *structural drift*. This story's tests run the *actual attack* against a real Postgres and verify the system fails closed.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Postgres schema` (lines 832–880) — the `REVOKE UPDATE, DELETE, TRUNCATE` block + the `events_immutable()` trigger + the `migrations_role`-not-super design. AC-1 / AC-2 verify the role boundary; AC-3 verifies the trigger.
  - `../phase-arch-design.md §C11 — Alembic discipline` (line 665) — `migrations_role` has DDL on `events` schema only, no `CREATE EXTENSION` outside `{pg_stat_statements}` allowlist.
  - `../phase-arch-design.md §Path to production end state — Test plan` (lines 1057–1063) — the two adversarial test files this story ships.
  - `../phase-arch-design.md §Edge case 8` (line 990) — "compromised `application_role` INSERTs a poisoned row" — the *post*-INSERT detection is the per-workflow chain (S3-04); the *blast-radius cap* is the role + trigger this story tests.
- **Phase ADRs:**
  - `../ADRs/0009-no-pgcrypto-column-encryption.md` — "anti-decision" framing; the symmetric "anti-`plpython3u`" attack is the runtime mirror.
  - `../ADRs/0003-per-workflow-blake3-prev-hash-chain.md` — the chain is tamper-*evidence*; the role boundary + trigger are tamper-*prevention*. Both layers; this story exercises the prevention.
  - `../ADRs/0011-checkpointer-backend-postgres.md` — the role-ownership boundary CI-asserted.
- **Existing code (precedent to mirror):**
  - `tests/adv/` — Phase 1+ adversarial test conventions (e.g., `tests/unit/probes/layer_b/test_node_reflection_adv.py` if it exists). Mirror the file-naming and `@pytest.mark.adv` / `phase02_adv` style.
  - `pyproject.toml` `[tool.pytest.ini_options] markers` — adversarial markers; this story may add `phase09_adv` (mirror the precedent set by `phase02_adv`).
  - `testcontainers.postgres.PostgresContainer` — same dependency S2-03 added.

## Goal

Ship two adversarial tests under `tests/adv/`:
1. `test_events_append_only_enforcement.py` — connects as `application_role`, INSERTs a row, then attempts UPDATE, DELETE, TRUNCATE; asserts each raises `psycopg.errors.InsufficientPrivilege` *or* the trigger's `RaiseException`. The role boundary is verified first; the trigger is the second layer.
2. `test_alembic_migration_plpython_blocked.py` — constructs a *malicious* alembic migration (in-memory, not committed) that contains `CREATE EXTENSION plpython3u; CREATE FUNCTION ...`, applies it as `migrations_role` against a fresh Postgres, asserts the migration fails with a permission error before any plpython function is created.

Ship a `phase09_adv` pytest marker (or reuse `adv` if the repo's convention is single-marker). Wire both tests into `make test` (not behind a skip-by-default marker for CI; the dev workflow may skip via `-m "not phase09_adv"` ad hoc).

## Acceptance criteria

- [ ] **AC-1 — `application_role` cannot UPDATE.** `tests/adv/test_events_append_only_enforcement.py`:
    - Brings up a `postgres:16-alpine` testcontainer; runs `alembic upgrade head` to land the schema + roles.
    - Connects as superuser; INSERTs one valid `events.events` row (with all required columns satisfied).
    - Connects as `application_role` (`SET ROLE application_role` or new connection with role-scoped credentials).
    - Attempts `UPDATE events.events SET payload = '{"tampered": true}' WHERE event_id = ...`.
    - Asserts the connection raises `psycopg.errors.InsufficientPrivilege` (role boundary) **or** `psycopg.errors.RaiseException` containing the `'events.events is append-only; mutation denied'` text (trigger). Either is acceptable defense; documents which fired in the test's assertion message.
- [ ] **AC-2 — `application_role` cannot DELETE or TRUNCATE.** Same setup as AC-1; attempts `DELETE FROM events.events WHERE event_id = ...` and `TRUNCATE events.events`; asserts both raise per AC-1. (Three sub-tests, parametrized over the mutation verb.)
- [ ] **AC-3 — Superuser CAN bypass via direct trigger disable.** This is the *honest control case* — confirms the test setup actually attacks the boundary. As superuser, INSERT a row; assert the INSERT succeeds (proves we're connected to a working DB). Without this, an AC-1 pass might mean "Postgres rejected everything because the DSN was wrong" — a false-positive trap. The control sits in the same file.
- [ ] **AC-4 — `application_role` CAN INSERT and SELECT.** The role boundary is *exclusionary*, not blanket-deny. As `application_role`: INSERT a row (succeeds); SELECT the row (succeeds with the inserted row visible). Confirms the role grants from S2-03 actually work for the positive case; protects against an over-restrictive future migration that breaks the writer.
- [ ] **AC-5 — `migrations_role` is not super.** `tests/adv/test_alembic_migration_plpython_blocked.py`:
    - Brings up a `postgres:16-alpine` testcontainer; runs `alembic upgrade head`.
    - Connects as `migrations_role` (the role alembic ran as is the one we exercise here — wire via env override or DSN to make this explicit).
    - Queries `SELECT rolsuper FROM pg_roles WHERE rolname = 'migrations_role'`; asserts `False`. (Direct attribute check — independent of the attack.)
- [ ] **AC-6 — `migrations_role` cannot `CREATE EXTENSION plpython3u`.** Same connection as AC-5; runs `CREATE EXTENSION plpython3u;` (or `CREATE EXTENSION pgcrypto;`); asserts `psycopg.errors.InsufficientPrivilege` (or equivalent). The extension must not be created; assert `SELECT * FROM pg_extension WHERE extname = 'plpython3u'` returns zero rows after the attack.
- [ ] **AC-7 — Adversarial migration applied as `migrations_role` fails.** Write a temp migration file (in `tmp_path`) containing `op.execute("CREATE EXTENSION plpython3u; CREATE FUNCTION events.evil() RETURNS TEXT AS $$ return 'pwned' $$ LANGUAGE plpython3u;")`. Configure alembic to read from `tmp_path` (custom script_location); attempt `alembic upgrade head`. Asserts the command exits non-zero; asserts the `events.evil` function does **not** exist (`SELECT * FROM pg_proc WHERE proname = 'evil'` returns zero rows). This is the full attack path the critic-3-on-[S] required defeat for.
- [ ] **AC-8 — Pytest marker registered.** `pyproject.toml`'s `[tool.pytest.ini_options] markers` adds `phase09_adv: Phase 9 adversarial tests (Postgres-backed)` (or reuses `adv` if the project's convention is single). The two test files use the marker. CI's `make check` runs them; contributors can opt out via `pytest -m "not phase09_adv"`.

## Implementation outline

1. **Reuse the testcontainer fixture from S2-03 / S2-05** (if cleanly extractable) or set up an independent container fixture. Session-scope is fine — both tests can share a container if they don't mutate state cross-test (each test inserts its own scoped rows).
2. **Wire role-switching.** Two clean patterns: (a) connect as superuser, then `SET ROLE application_role` for the attack — simpler; (b) create per-role DSNs with passwords set in the migration — closer to production but more setup. Pick (a) for this story; document the choice.
3. **Write `tests/adv/test_events_append_only_enforcement.py`** with sub-tests AC-1..AC-4. Parametrize the mutation verb; each assertion captures *which* defense fired (role or trigger) in the message.
4. **Write `tests/adv/test_alembic_migration_plpython_blocked.py`** with AC-5..AC-7. AC-7's temp migration uses `tmp_path` and a separate alembic config; verify the attack path matches what a real contributor would attempt.
5. **Add the `phase09_adv` marker** to `pyproject.toml` (if `adv` doesn't already exist; if it does, reuse).
6. **Run locally:** `pytest tests/adv/test_events_append_only_enforcement.py tests/adv/test_alembic_migration_plpython_blocked.py -v` and verify each assertion's failure-message text is informative.

## TDD plan — red / green / refactor

**Red.**
- `test_events_append_only_enforcement.py::test_application_role_cannot_update` — written first. Initially fails: testcontainer doesn't have S2-03's migration applied yet (or, if the order is reversed, the role boundary isn't tested against the real schema). Make sure the assertion captures the *exception type and message*, not just "an exception".
- `test_events_append_only_enforcement.py::test_application_role_cannot_delete` — parametrize variant.
- `test_events_append_only_enforcement.py::test_application_role_cannot_truncate` — parametrize variant.
- `test_events_append_only_enforcement.py::test_application_role_can_insert_and_select` — the positive control.
- `test_events_append_only_enforcement.py::test_superuser_can_insert_baseline` — the meta-control.
- `test_alembic_migration_plpython_blocked.py::test_migrations_role_is_not_super` — direct `pg_roles` check.
- `test_alembic_migration_plpython_blocked.py::test_migrations_role_cannot_create_plpython3u_extension` — direct `CREATE EXTENSION` attempt.
- `test_alembic_migration_plpython_blocked.py::test_adversarial_migration_fails` — the full attack-path test.

These tests verify *intent* (Rule 9): a contributor who weakens the role boundary (e.g., grants `application_role` UPDATE in a future migration) breaks the static fence (S2-04 — if the change is in a checked-in migration), the schema-snapshot (S2-05 — the GRANT visibility), and this story's AC-1. Three independent layers.

**Green.**
- The tests assume S2-03 already shipped (it's a dependency). Each test transitions to green by virtue of S2-03's migration doing its job correctly. If a test stays red, **S2-03 has a bug** — fix it there, not by relaxing the assertion. The adversarial tests are the audit; relaxing them defeats the audit.

**Refactor.**
- Extract the container + migrate fixture into `tests/adv/conftest.py` (or `tests/conftest.py` if shared with S2-05). Both adversarial files reuse the same fresh-DB-with-schema fixture.
- Document in each file's module docstring which ADR's claim the file tests (`ADR-0003 tamper-prevention layer`, `ADR-0009 anti-plpython3u corollary`).

## Files to touch

- **New:**
  - `tests/adv/__init__.py` (if not present)
  - `tests/adv/test_events_append_only_enforcement.py`
  - `tests/adv/test_alembic_migration_plpython_blocked.py`
- **Modified:**
  - `pyproject.toml` — add `phase09_adv` marker if `adv` is not the existing convention.
  - `tests/adv/conftest.py` (or `tests/conftest.py`) — add the shared fixture if the precedent calls for it.

## Out of scope

- **Per-workflow chain tamper detection.** S3-04 owns the `ChainTamperDetected` emission on forged-row read. This story tests the *prevention* (role boundary) — the prevention failing is the precondition for tamper to be possible at all; without it, detection is needed even more.
- **Other extensions (`pgcrypto`, `plperlu`, `plsh`).** This story uses `plpython3u` as the canonical example (per `phase-arch-design.md §Path to production`); the broader extension allowlist is enforced by S2-04 (text) + S2-05 (schema). If a future ADR widens the allowlist, this story's tests don't need to be touched.
- **`read_role` boundary.** S2-03 created `read_role` for the Phase-13.5 portal; testing its boundary belongs in a later phase's story (Phase 13.5's portal-auth tests).
- **`migrations_role` having DDL only on `events`, not on `temporal` or `langgraph_checkpoints`.** That negative boundary is implicit (the role was never granted DDL on those schemas); explicitly testing it is overhead this story doesn't carry — S2-04's static fence + S2-05's snapshot scope cover the additive direction.
- **Performance under role-switching.** Connection-per-role overhead is dev-only; production uses separate connection strings. Not measured here.

## Notes for the implementer

- **`SET ROLE application_role` vs separate connection.** Both work. `SET ROLE` reuses the existing superuser connection but adopts the target role's privileges; clean for tests. Separate connections require role passwords (the migration would need to grant logins) and approach the production shape more faithfully. Pick `SET ROLE` for this story; document the choice in the module docstring; if a future story needs the production-shape fidelity, it lands additively.
- **Why three mutations (UPDATE, DELETE, TRUNCATE), not just one.** The append-only trigger fires on `BEFORE UPDATE OR DELETE OR TRUNCATE`; the role REVOKE covers the same three. Two independent layers; the test exercises all three to confirm neither layer has a gap. (Imagine a future PR that drops one of the three from the REVOKE — the trigger still catches it, but the *defense-in-depth* claim is weaker; only by testing all three do we surface the regression.)
- **Why test both layers fire.** ADR-0003 + ADR-0011 + the trigger function are three claims; each test confirms at least one fired. The assertion message names which (`role boundary` vs `trigger`); reviewing the test output tells future engineers which layer was actually exercised. This is the "fail loud" discipline applied to defense-in-depth.
- **The malicious migration in AC-7 is `tmp_path`-scoped.** Do not commit it to `versions/` (S2-04's lock would flag it; S2-05's snapshot would diff). The temp file lives in pytest's `tmp_path`; alembic reads from `tmp_path`-scoped `script_location` via a temp `alembic.ini`. Tests clean up after themselves.
- **`psycopg.errors.InsufficientPrivilege` vs `psycopg.errors.RaiseException`.** The role REVOKE produces `InsufficientPrivilege`; the trigger's `RAISE EXCEPTION` produces `RaiseException`. Either is acceptable defense; the assertion accepts both via `pytest.raises((InsufficientPrivilege, RaiseException))`. Document in the assertion message which fired.
- **Don't catch the exception and re-assert text.** `pytest.raises(...)` is the right shape. Don't write `try: ...; except Exception: pass` — that conceals which exception type fired and breaks the audit.
- **Wall-clock budget.** Each test starts a container; ~10–15 s cold start. Two tests = 20–30 s total. If both share a session-scoped fixture, ~15 s total. Don't make this slower than S2-05; if it does, the contributor experience erodes.
- **`pg_extension` and `pg_proc` introspection.** AC-6 and AC-7 read system catalogs. The queries are simple `SELECT FROM pg_extension WHERE extname = 'plpython3u'` and `SELECT FROM pg_proc WHERE proname = 'evil'`. After a failed migration, both should return zero rows. The check is the proof of failure-mode: not just "command failed" but "the bad thing didn't happen".
- **What S3-04 (chain-tamper detection) reads from you.** Nothing directly. S3-04 forges a row via `migrations_role` (which *can* write to `events.events` for DDL purposes — but in practice, S3-04's test escalates to superuser to plant the forged row, then reads as `application_role` and asserts the chain breaks). Your story closes the *prevention* loop; S3-04 closes the *detection* loop.
- **The critic-3-on-[S] defeat language in the ADRs is not rhetorical.** The plpython3u-attack path was the *concrete attack* the security-critic landed against the security-first design's `pgcrypto`-only defense. AC-7 is the test that closes that case. Without AC-7, the ADR-0009 anti-decision rests on a textual claim; with AC-7, it rests on runtime evidence. Don't skip it; don't loosen it.
