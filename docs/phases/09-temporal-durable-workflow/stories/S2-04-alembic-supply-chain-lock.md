# Story S2-04 — Alembic supply-chain lock + ownership fences

**Step:** Step 2 — Provision Postgres + alembic + docker-compose dev surface
**Status:** Ready
**Effort:** S
**Depends on:** S2-03 (the migration file that the lock SHA-pins must exist first)
**ADRs honored:** ADR-0011 (alembic owns the `events` schema only; `langgraph_checkpoints` and `temporal` are out of bounds), ADR-0009 (no `pgcrypto`, no `plpython3u` — extension allowlist is `{pg_stat_statements}` only — the static fence here complements the runtime fence in S2-06)

## Context

A poisoned alembic migration is one of the highest-impact supply-chain attacks on Phase 9: a single PR adding `op.execute("CREATE EXTENSION pgcrypto; ...")` or `op.execute("GRANT ALL ON events.events TO PUBLIC; ...")` would silently relax the trust boundary every Step-3+ story rests on. The roadmap's G10 exit criterion encodes this as **alembic supply-chain integrity** — `tools/alembic-revisions.lock` SHA-pins every file under `versions/`, and CI fails if any pinned file's hash drifts without a corresponding lock update.

This story complements the runtime fence in S2-06 (which spins up a real Postgres and tries the attack) with a **static-text fence**: every migration file under `src/codegenie/events/alembic/versions/` must (a) hash-match the lock, (b) not reference `temporal.*` or `langgraph_checkpoints.*` schemas, (c) not contain a `CREATE EXTENSION` for anything outside the `{pg_stat_statements}` allowlist. The fence catches *additions* (a new migration without a lock entry) and *mutations* (an existing migration whose SHA drifts). The two layers (static + runtime) are non-overlapping per the same defense-in-depth pattern ADR-0004 uses for workflow determinism.

The lock file is a precedent for Phase 10+: every new migration brings its own lock-line in the same PR; CI's mismatch error message names the file and the expected vs actual SHAs. Reviewers see the lock change as a *signal* — if the SHA in the lock changes but no migration file changed in the diff, something is wrong.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C11 — Alembic discipline` (lines 658–670) — the verbatim contract: `tools/alembic-revisions.lock` SHA-pins, CI fence file, `migrations_role` no-`CREATE EXTENSION`-outside-allowlist, schema-snapshot diff.
  - `../phase-arch-design.md §Goals G10` (line 25) — "Alembic supply-chain integrity" — exit criterion this story satisfies.
  - `../phase-arch-design.md §Path to production end state — Test plan` (lines 1040–1043) — `test_alembic_revision_lock.py` and `test_alembic_owns_only_events_schema.py` named explicitly.
- **Phase ADRs:**
  - `../ADRs/0011-checkpointer-backend-postgres.md` §Consequences row 2 — `langgraph_checkpoints` is upstream-owned; alembic does *not* migrate it; fence enforces.
  - `../ADRs/0009-no-pgcrypto-column-encryption.md` — `pgcrypto` is forbidden. The extension allowlist is `{pg_stat_statements}`.
  - `../ADRs/0012-event-store-topology-temporal-history-plus-postgres-events.md` — the `temporal` schema is owned by `temporalio/auto-setup`; alembic does *not* touch it.
- **Existing code (precedent to mirror):**
  - `tests/fence/` — Phase-2's `forbidden-patterns` pre-commit hook and `tests/fence/test_pyproject_fence.py` are the *shape* this story mirrors: a static grep/hash fence whose failure message tells the contributor exactly what to fix.
  - `tools/` directory — convention is one `.lock` file per supply-chain dimension. If `tools/grammars.lock` precedent exists from Phase 0, follow the format.
  - `tests/fence/test_temporal_ui_loopback.py` (S2-01) — same shape: walk a directory, regex-check, fail with `path:line`.

## Goal

Ship `tools/alembic-revisions.lock` SHA-pinning every file under `src/codegenie/events/alembic/versions/`; ship `tests/fence/test_alembic_revision_lock.py` (hash mismatch fails CI with diff guidance) and `tests/fence/test_alembic_owns_only_events_schema.py` (any migration referencing `temporal.*`, `langgraph_checkpoints.*`, or `CREATE EXTENSION` outside the `{pg_stat_statements}` allowlist fails CI). The two fences run in `make test` and are wired into CI's existing test job — no new CI steps.

## Acceptance criteria

- [ ] **AC-1 — `tools/alembic-revisions.lock` exists and pins every version file.** The file lists every `src/codegenie/events/alembic/versions/*.py` (excluding `__init__.py`) with its BLAKE3 (or SHA-256, matching the precedent set by `tools/grammars.lock` if it exists) hash. Format is YAML or simple `path = hash` lines — pick whatever the codebase's existing `.lock` files use; mirror exactly. The lock includes `0001_create_events_schema.py` (S2-03's output).
- [ ] **AC-2 — Hash-mismatch fence fails informatively.** `tests/fence/test_alembic_revision_lock.py` reads `tools/alembic-revisions.lock`, recomputes the hash of every listed file, and asserts the computed hash equals the locked hash. On mismatch the failure message includes: (a) the file path, (b) the locked hash, (c) the computed hash, (d) a one-line remediation hint (`Run \`tools/regen-alembic-lock.sh\` after reviewing the diff` or equivalent). A fixture-mutation test (locally toggling a byte in a temp copy of `0001_create_events_schema.py`) confirms the fence fires.
- [ ] **AC-3 — Lock catches *additions*, not just mutations.** A `versions/0002_*.py` file present on disk but absent from the lock fails the fence with `unpinned migration file: <path>`. A lock entry pointing to a file that no longer exists also fails with `stale lock entry: <path>`. (Both halves of the bijection are checked.)
- [ ] **AC-4 — Ownership fence rejects out-of-bounds schema references.** `tests/fence/test_alembic_owns_only_events_schema.py` walks every file under `src/codegenie/events/alembic/versions/`, greps for the literals `temporal.` and `langgraph_checkpoints.` (case-insensitive), and fails on any match with `path:line: out-of-bounds schema reference: <line>`. The trigger function `events.events_immutable()` and table references like `events.events` are explicitly allowed.
- [ ] **AC-5 — Extension allowlist enforced.** Same fence file (AC-4) greps for `CREATE EXTENSION` (case-insensitive); any match whose extension name is not exactly `pg_stat_statements` fails with `disallowed extension: <name>`. The S2-03 migration has zero `CREATE EXTENSION` lines today, so the test currently asserts zero matches.
- [ ] **AC-6 — Allowlist registry document.** `tools/alembic-allowlist.md` (or inline in the lock file) declares the two allowlists: schema references = `{events.*}` only; extensions = `{pg_stat_statements}` only. Future relaxations require an ADR amendment and a registry update in the same PR — the fence test reads the registry rather than hardcoding the allowlist, so the discussion-forcing function lives in one file.
- [ ] **AC-7 — Lock-regen helper exists.** `tools/regen-alembic-lock.sh` (or `tools/regen-alembic-lock.py`) reads every `versions/*.py`, computes hashes, writes `tools/alembic-revisions.lock`. The script is what a contributor runs after intentionally landing a new migration. The script is *not* run by CI (that would defeat the lock); CI runs the *check*, contributors run the *regen*. The script's header documents this asymmetry.
- [ ] **AC-8 — Both fences green on fresh clone after `make test`.** No setup beyond `make bootstrap`; no Postgres needed; no Docker needed. Pure-text walks. Fast (< 100 ms total).

## Implementation outline

1. **Pick the hash algorithm.** If `tools/` has any prior `.lock` (e.g., `tools/grammars.lock`), mirror its algorithm. Otherwise, default to SHA-256 (universally available in `hashlib`; no extra dependency). Document the choice in the lock file's header comment.
2. **Pick the lock format.** Simple `path  hash` one-per-line is the lowest-ceremony shape; YAML is the alternative. Mirror precedent; if no precedent, choose simple text. The lock file is human-reviewable.
3. **Write `tools/regen-alembic-lock.sh`** (or `.py`) — straightforward `for f in versions/*.py; do sha256sum "$f"; done > tools/alembic-revisions.lock`.
4. **Generate the initial lock** by running the regen script against S2-03's output. Commit the resulting lock file.
5. **Write `tests/fence/test_alembic_revision_lock.py`** per AC-2 and AC-3: parse the lock, walk the versions directory, assert the bijection.
6. **Write `tests/fence/test_alembic_owns_only_events_schema.py`** per AC-4 and AC-5: per-file line-by-line grep with the two regexes; one consolidated failure summary if multiple violations.
7. **Write `tools/alembic-allowlist.md`** declaring the two allowlists; the fence reads from this file (or from a constant pulled from it).

## TDD plan — red / green / refactor

**Red.**
- `tests/fence/test_alembic_revision_lock.py::test_lock_matches_disk` — fails because `tools/alembic-revisions.lock` doesn't exist yet. Then exists with wrong hash → mismatch failure message includes expected and actual.
- `tests/fence/test_alembic_revision_lock.py::test_unpinned_file_rejected` — fixture creates `versions/9999_test.py` (or uses `tmp_path` clone of the directory); test asserts the fence reports the file as unpinned.
- `tests/fence/test_alembic_revision_lock.py::test_stale_lock_entry_rejected` — lock points at a file that doesn't exist; test asserts the fence reports the stale entry.
- `tests/fence/test_alembic_owns_only_events_schema.py::test_temporal_reference_rejected` — fixture: write a `versions/9999_evil.py` containing `op.execute("ALTER TABLE temporal.workflows ...")`; test asserts the fence catches the `temporal.` literal.
- `tests/fence/test_alembic_owns_only_events_schema.py::test_langgraph_checkpoints_reference_rejected` — same shape, `langgraph_checkpoints.` literal.
- `tests/fence/test_alembic_owns_only_events_schema.py::test_pgcrypto_extension_rejected` — fixture: `op.execute("CREATE EXTENSION pgcrypto;")`; fence catches.
- `tests/fence/test_alembic_owns_only_events_schema.py::test_pg_stat_statements_extension_allowed` — fixture: `op.execute("CREATE EXTENSION pg_stat_statements;")`; fence passes.

These tests verify intent per global Rule 9: a contributor swapping the regex for one that misses `temporal.` would still pass a "fence test runs" check but fail the *fixture-driven* assertion. Negative tests with planted fixtures are the discipline.

**Green.**
- Land the lock file, the two fence test files, the regen script. Each red test transitions to green one at a time.

**Refactor.**
- Pull the line-walker / regex-match helper into a shared module if both fence files duplicate the loop. Resist over-abstraction — two fences may be cleaner as two flat scripts.
- Make the failure message format consistent across both fences (`path:line: <description>: <line content>`). The grep convention helps reviewers.

## Files to touch

- **New:**
  - `tools/alembic-revisions.lock`
  - `tools/regen-alembic-lock.sh` (executable, `chmod +x`) — or `tools/regen-alembic-lock.py`
  - `tools/alembic-allowlist.md`
  - `tests/fence/test_alembic_revision_lock.py`
  - `tests/fence/test_alembic_owns_only_events_schema.py`
- **Modified:** None. (The fence tests stand alone; no `Makefile` change beyond what S2-03 already added.)

## Out of scope

- **Schema-snapshot diff.** S2-05 owns. That is a *runtime* fence (migrate against a fresh Postgres, dump schema, diff) and complements this story's *static* fences.
- **Runtime adversarial enforcement.** S2-06 owns. That story tries the attack (`CREATE EXTENSION plpython3u` actually fails at migration time because `migrations_role` is non-super) — the runtime layer of defense-in-depth.
- **`pre-commit-config.yaml` hook.** Phase 9 does not add a pre-commit hook for this; the test-time fence in `make test` is sufficient (and identical to how Phase-2's `forbidden-patterns` ships — hook *and* test, both layers). If a contributor regularly hits the fence at PR time, a future story can add the pre-commit hook additively. Not now.
- **Phase 10's migration lock entries.** Phase 10 adds its own migrations and lock lines additively in its own stories.

## Notes for the implementer

- **Why the regen script doesn't run in CI.** If CI regenerated the lock, the lock would always pass — defeating its purpose. The lock is a *human-acknowledged seal*; the contributor regenerates it intentionally after reviewing the new migration. CI's job is to *verify*, not to *regenerate*. The script's header documents this.
- **Why two fence files, not one.** The hash-pin and the schema-ownership/extension allowlist are *orthogonal* concerns: hash-pinning catches "the file was tampered with after review"; ownership catches "the file's content steps outside the agreed-on boundaries". Keeping them separate makes the failure messages distinct and a contributor's mental model clean.
- **Allowlist relaxation is an ADR amendment, not a config tweak.** If a future story legitimately needs `pgcrypto` (e.g., Phase 16 production deployment evolves), the change requires (a) amending ADR-0009 or writing a new ADR overruling it, (b) updating `tools/alembic-allowlist.md` in the same PR, (c) the fence reads from the updated allowlist. The fence is the discussion-forcing function — don't bypass.
- **Case-insensitivity matters.** Postgres SQL is case-insensitive (unless quoted); a contributor might write `Temporal.workflows` or `LANGGRAPH_CHECKPOINTS.snapshots`. The fence regex is case-insensitive (`re.IGNORECASE`). Test the variants.
- **False-positive risk.** If a migration's comment block contains the literal `temporal.` (e.g., describing what the migration *avoids*), the fence triggers. Treat that as a feature: rephrase comments to use the word `Temporal` (capital T, no dot) or quote-strip. The fence is intentionally noisy on the right side of "be careful around these schema names".
- **Hash algorithm: SHA-256 vs BLAKE3.** ADR-0003 uses BLAKE3 for chain hashing inside Postgres (perf-sensitive); the lock is not perf-sensitive (per-PR check, < 100 ms). SHA-256 (stdlib `hashlib`) is the lower-ceremony choice if no precedent. If `tools/grammars.lock` uses BLAKE3, mirror it.
- **What S2-05 reads from you.** Nothing directly — S2-05 dumps `pg_dump` output and diffs it. Your fences are *static*; theirs is *runtime*. Both are required for the supply-chain story.
- **What S2-06 reads from you.** S2-06 exercises a real Postgres with a `migrations_role` non-super role and tries `CREATE FUNCTION ... LANGUAGE plpython3u`. Postgres itself refuses. Your fence prevents the migration from even *trying* — defense-in-depth.
- **Token count of the lock.** ~10 lines today (one migration). A Phase-10 PR adding three migrations adds three lines. The lock will never be more than ~50 lines through Phase 16; no need for elaborate parsing.
- **Don't `mock.patch` the SHA in the test.** If a test ever monkey-patches the lock contents in-memory, the fence verifies nothing real. The tests work against tempfiles (fixtures with known contents) — never against the actual lock file with mocked hashes.
