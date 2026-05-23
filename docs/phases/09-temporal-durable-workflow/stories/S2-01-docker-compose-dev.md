# Story S2-01 — docker-compose.dev.yml + loopback-only ports

**Step:** Step 2 — Provision Postgres + alembic + docker-compose dev surface
**Status:** Ready
**Effort:** S
**Depends on:** S1-01 (DurableSettings references the `TaskQueueName` / `TemporalAddress` Newtypes only at the type-annotation level; the compose file itself is config-only — the dependency is on having a place to land env-var docs, not on runtime imports)
**ADRs honored:** ADR-0015 (`temporal-ui` loopback-only), ADR-0007 (two task queues — referenced only by container topology), ADR-0012 (event-store topology — Postgres is one of three services)

## Context

Phase 9's local dev surface is **one command** (`make dev-up`) and **four containers** (`postgres:16-alpine`, `temporalio/auto-setup:1.25`, `temporalio/ui:2.30`, `redis:7-alpine`). The load-bearing constraint is `temporal-ui`'s bind address: ADR-0015 freezes it to `127.0.0.1:8233`, and the G2 exit criterion encodes that as a fence test (`tests/fence/test_temporal_ui_loopback.py`) that greps `scripts/`, `infra/`, `Makefile` for any literal `0.0.0.0` (zero matches allowed).

This story ships the compose file, the `scripts/temporal-dev.sh` driver, the `Makefile` `dev-up`/`dev-down` targets, and the loopback fence test. It does **not** ship `DurableSettings` (S2-02), the alembic migration (S2-03), or any application code. The containers are *the runtime substrate* — every later Step-2 story executes inside, or migrates against, this compose.

ADR-0015 is the secure-default + structural-enforcement pattern: the default bind is the safe one, deviation requires a code change that the fence catches. Phase-2's `forbidden-patterns` pre-commit hook is the precedent — same shape, different domain.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C9 — Local dev surface` (lines 611–635) — the compose-file excerpt, `scripts/temporal-dev.sh` rejection rule, `make dev-up` / `make dev-down` / `make migrate` targets.
  - `../phase-arch-design.md §Physical view` (around line 300) — "dev box (docker-compose + host processes)"; workers run as **host processes**, not in containers; the compose only carries the stateful pieces.
  - `../phase-arch-design.md §Goals G2` (line 17) — the exit criterion phrasing the fence test must verify.
  - `../phase-arch-design.md §Component map` (line 291) — `infra/docker-compose.dev.yml` + `scripts/temporal-dev.sh` + `tools/alembic-revisions.lock` shown together; this story lands the first two.
- **Phase ADRs:**
  - `../ADRs/0015-temporal-ui-loopback-only.md` — the decision, tradeoffs, the fence-allowlist comment convention (`# fence-allowlist: <reason>`), the SSH-tunnel pattern for remote sharing.
  - `../ADRs/0007-two-task-queue-partitioning-and-expansion-by-addition.md` — only one container exposes Temporal (`temporal:7233`); the queues are *application-level*, not container-level.
- **Existing code (precedent to mirror):**
  - Repo `Makefile` — existing target style for `make bootstrap`, `make check`; new targets use the same `.PHONY` discipline and `@echo` introduction lines.
  - Repo `scripts/` — any existing bash script for arg-parse precedent (use `set -euo pipefail`, `getopts` or explicit `case` on `$1`).
  - `tests/fence/` — existing fence-test idioms; the new test mirrors the grep-walks-the-repo shape used by phase-2 `forbidden-patterns`.

## Goal

Ship `infra/docker-compose.dev.yml`, `scripts/temporal-dev.sh`, `Makefile` `dev-up`/`dev-down` targets, and `tests/fence/test_temporal_ui_loopback.py` so that `make dev-up` brings the four containers up with every port bound to `127.0.0.1`, `scripts/temporal-dev.sh --ip 0.0.0.0` exits non-zero before doing anything, and a fresh-clone CI greps zero `0.0.0.0` literals across `scripts/`, `infra/`, `Makefile`.

## Acceptance criteria

- [ ] **AC-1 — Compose file exists and is loopback-bound.** `infra/docker-compose.dev.yml` ships exactly four services: `postgres` (image `postgres:16-alpine`), `temporal` (image `temporalio/auto-setup:1.25`), `temporal-ui` (image `temporalio/ui:2.30`), `redis` (image `redis:7-alpine`). Every `ports:` entry has the form `"127.0.0.1:<port>:<port>"`. No `0.0.0.0`, no host-network mode, no bare `<port>:<port>` (which Docker interprets as `0.0.0.0`). Tags pinned (no `:latest`).
- [ ] **AC-2 — Volumes named and persistent.** Postgres uses a named volume `codegenie-pg-data` mapped to `/var/lib/postgresql/data`; Redis uses `codegenie-redis-data`. `make dev-down && make dev-up` preserves Postgres data; `make dev-down -v` (or a separate `make dev-reset` target) tears volumes too. The story file documents which one wipes data.
- [ ] **AC-3 — `scripts/temporal-dev.sh` rejects non-loopback binds.** The script accepts `--ip <addr>`; any value matching `0.0.0.0`, `*`, or a `*.*.*.*` wildcard pattern exits with non-zero status and a message naming the rejected value before invoking any docker command. `127.0.0.1` and `localhost` are accepted. The script uses `set -euo pipefail`. Exit code is non-zero before any side effect.
- [ ] **AC-4 — `Makefile` targets exist.** `make dev-up` runs `docker compose -f infra/docker-compose.dev.yml up -d`; `make dev-down` runs `docker compose -f infra/docker-compose.dev.yml down`; both are `.PHONY`. `make dev-up` prints the `temporal-ui` URL (`http://127.0.0.1:8233`) at completion so the engineer can click it.
- [ ] **AC-5 — Loopback fence test exists and is green on a clean clone.** `tests/fence/test_temporal_ui_loopback.py` walks `infra/`, `scripts/`, `Makefile` and counts every line matching the regex `\b0\.0\.0\.0\b`. Any line not annotated with an inline `# fence-allowlist: <reason>` comment fails the test. Test runs in `make test`; reports the offending file:line in the failure message. Annotated lines must still appear in a checked-in `tests/fence/loopback_allowlist.md` registry with the justification.
- [ ] **AC-6 — Compose validates.** `docker compose -f infra/docker-compose.dev.yml config -q` exits zero (this is the CI smoke that catches YAML typos without spinning containers). A unit-style test invokes it (`subprocess.run(["docker", "compose", "-f", ...], check=True)`), skipping cleanly with `pytest.skip("docker not available")` when the binary is absent so contributors without Docker can still run `make test`.
- [ ] **AC-7 — Port collision yields a typed failure.** When 5432/6379/7233/8233 is already bound on the host, `make dev-up` fails with the docker-compose error pass-through; `docs/development.md` (touched in S8-06) is referenced in Notes as the env-override doc. This story documents the env-var override convention (`POSTGRES_PORT=5433 make dev-up`) but does *not* land the docs (S8-06 owns).
- [ ] **AC-8 — `temporal-ui` reachability proven loopback-only by health probe.** An integration smoke test (skipped without Docker) brings the compose up, polls `http://127.0.0.1:8233/` until ready, asserts `200`-class response, then asserts a connection attempt to `<lan-ip>:8233` (computed from `socket.gethostname()` or a documented fallback) raises `ConnectionRefusedError` / times out. Tears compose down on success and on failure (try/finally).

## Implementation outline

1. Create `infra/` directory; write `docker-compose.dev.yml` per AC-1/AC-2. Lock image digests in a comment next to each `image:` line (digests pinned in S2-04's lock; this story carries the human-readable tag pin).
2. Create `scripts/temporal-dev.sh` per AC-3 — pure bash, no Python; argparse via `case` on flags; `set -euo pipefail`.
3. Add `dev-up` / `dev-down` (and optionally `dev-reset`) targets to the top-level `Makefile`. Update the `Makefile`'s top-of-file comment listing targets.
4. Write `tests/fence/test_temporal_ui_loopback.py`:
   - Iterates `infra/`, `scripts/`, top-level `Makefile`.
   - Uses `re.compile(r"\b0\.0\.0\.0\b")`.
   - Per-line check; if the matched line lacks `# fence-allowlist:`, fail with `path:line: <line content>`.
   - Cross-checks the allowlist registry (`tests/fence/loopback_allowlist.md`) so an `# fence-allowlist:` comment without a registry entry also fails (prevents quiet-skip drift).
5. Write `tests/fence/loopback_allowlist.md` with the header and an empty bullet list (no current allowlisted lines; the file is the seam that future PRs touch).
6. Write `tests/fence/test_compose_validates.py` and the smoke test from AC-8 (both gated on `shutil.which("docker")`).
7. Run `make dev-up` locally; confirm `127.0.0.1:8233` loads `temporal-ui`; confirm a connection to the LAN IP is refused; confirm `make dev-down` cleans up.

## TDD plan — red / green / refactor

**Red.**
- Write `tests/fence/test_temporal_ui_loopback.py` first against an *empty* `infra/` + `scripts/` tree; the test must pass with zero files (proves the walker doesn't false-positive on absence). Then plant a fixture string `0.0.0.0` in a tempfile inside the walked roots — the test must fail with the fixture path in the message. Remove the fixture.
- Write `tests/fence/test_temporal_dev_sh_rejects_wildcard.py` invoking `scripts/temporal-dev.sh --ip 0.0.0.0` via `subprocess.run` and asserting `returncode != 0` and `"0.0.0.0"` appears in stderr. Before the script exists, the test should fail because the file is not executable / not found.
- Write `tests/fence/test_compose_validates.py` calling `docker compose ... config -q` against the missing file — the test must fail with the missing-file path in the error.
- Write the AC-8 reachability smoke as a `@pytest.mark.integration` test; in red phase it fails because the compose isn't there.

**Green.**
- Land `infra/docker-compose.dev.yml`, `scripts/temporal-dev.sh`, the `Makefile` targets, the allowlist registry — make each red test pass one at a time. Resist the urge to write all four at once; surfacing each red→green transition is the discipline.

**Refactor.**
- Extract the `0.0.0.0` regex + walker into a tiny helper inside the test file (no new module — fence tests live as flat scripts in this codebase). DRY only if the same walker shape recurs in S2-04/S2-05 (which it will — but DRY *then*, not preemptively).
- Confirm the `# fence-allowlist:` registry-cross-check has zero entries (no allowlisted lines today); the absence is itself evidence.

## Files to touch

- **New:**
  - `infra/docker-compose.dev.yml`
  - `scripts/temporal-dev.sh` (executable, `chmod +x`)
  - `tests/fence/test_temporal_ui_loopback.py`
  - `tests/fence/test_temporal_dev_sh_rejects_wildcard.py`
  - `tests/fence/test_compose_validates.py`
  - `tests/fence/test_temporal_ui_loopback_smoke.py` (integration-marked; AC-8)
  - `tests/fence/loopback_allowlist.md`
- **Modified:**
  - `Makefile` — add `.PHONY: dev-up dev-down` plus the targets; update the top-of-file target list.

## Out of scope

- **`DurableSettings`.** Lands in S2-02 — this story does not import `pydantic-settings` and does not parse env vars at the application layer.
- **Alembic schema migrations.** S2-03 lands `events.events`, the append-only trigger, role grants. This story's containers come up with a stock `postgres:16-alpine` (no roles, no schemas).
- **`migrations_role` / `application_role`.** Created by S2-03's initial migration (or a `docker-entrypoint-initdb.d/` seed script S2-03 owns). This story does not pre-create them.
- **SHA-pinning image digests.** Tags (`postgres:16-alpine`, `temporalio/auto-setup:1.25`) are pinned by this story; digest pinning (`@sha256:...`) is S2-04's supply-chain lock concern.
- **`docs/development.md` content.** S8-06 ships the doc page. This story only writes references to it in Notes.
- **Worker `make` targets.** `python -m codegenie.durable.workers` lands in S6-01.

## Notes for the implementer

- **The fence-allowlist registry is a seam, not a hatch.** Resist landing the first allowlist entry in this story — every line we add now becomes a precedent. If a future PR needs a non-loopback bind for a legitimate reason (e.g., the `docs preview` server, a contributor's dev tunnel), the allowlist + ADR-0015 acknowledgement is the discussion-forcing function. Stage it for the actual case, not a hypothetical.
- **`docker compose` (v2, space) vs `docker-compose` (v1, hyphen).** Phase 9 targets v2; the `Makefile` calls `docker compose`, not `docker-compose`. CI's Docker is v2. If a contributor is on v1, `make dev-up` fails with a Docker-side error pointing at the missing subcommand — that's acceptable; ADR-0015's "Docker is already required" reasoning extends to v2.
- **`temporalio/auto-setup` opens 7233 (Temporal frontend).** The compose binds `127.0.0.1:7233:7233` even though the workflow workers connect from the same host. Engineers running workers in a *container* and the frontend on the host need the loopback note in `docs/development.md` (S8-06). Phase 9 workers run as *host processes* (`§Physical view` line 330) so loopback works for the default path.
- **Why `tags` not `@sha256:` digests here.** Tag pinning gives a contributor on a fresh clone a fast pull; digest pinning gives CI build-break determinism. S2-04 layers the digest lock on top — same pattern as `pyproject.toml` SHA-pin in `pre-commit-config.yaml` over an unpinned tag.
- **The `# fence-allowlist:` comment is a *line* comment, not a block.** The walker reads line-by-line; multi-line strings in `.yml` that contain `0.0.0.0` (e.g., a long-form config block) need the comment on every offending line. If this becomes onerous (e.g., one container needs a true `0.0.0.0` for legitimate reasons — Temporal's own server config does this internally), prefer adding a *parser* concession (skip lines inside `command:` blocks) over relaxing the rule.
- **Don't extend the compose to include the application workers.** They run as host processes; baking them in defeats the hot-reload story (`uvloop` + `watchfiles` — S6-01). The compose is *stateful pieces only*.
- **The AC-8 reachability test is the only place the compose actually boots in this story.** It must be marked `@pytest.mark.integration` (or equivalent) and gated on `shutil.which("docker")`; otherwise a contributor without Docker (e.g., on macOS without Docker Desktop) cannot run `make test`. The fence tests in AC-5/AC-6 are pure-text walks and run unconditionally — that's the bulk of the safety net.
- **Future-Phase tunnel-sharing.** ADR-0015 explicitly documents the SSH-tunnel pattern for sharing the UI with a teammate; do *not* land a `--share` flag or any other affordance that relaxes the bind. The discussion forcing function is the value.
