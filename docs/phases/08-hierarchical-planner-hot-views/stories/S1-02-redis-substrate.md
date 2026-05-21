# Story S1-02 — Stand up the Redis 7 substrate and the redis client dependency

**Step:** Step 1 — Land the contract primitives and the runtime substrate
**Status:** Ready
**Effort:** S
**Depends on:** S1-01

## Context
The four Phase-8 hot-view slices are served from Redis; the `< 50 ms p95` exit criterion and its `@pytest.mark.bench` canary need a real `redis:7-alpine` instance from the first hot-view step (Step 5) onward. This story is foundational runtime-substrate work: it provisions the container service and the `redis-py` client dependency so every later hot-view story has a backing store. No behavior is added — this is infrastructure.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Physical view` — the Phase-8 runtime topology: one `redis:7-alpine` container from `docker-compose`, `:6379`, no AOF, no replication (the cache is reconstructable from the next gather).
  - `../phase-arch-design.md §C4 — HotViewStore` — `HotViewStore.__init__` takes an injected `redis: Redis` (the `redis>=5` client); the store is a thin `redis-py` wrapper.
  - `../phase-arch-design.md §Goals §G7` — "`redis:7-alpine` in `docker-compose.yml`; `redis` (client) … added to `pyproject.toml`."
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0005-50ms-p95-exit-criterion-scoped-to-hot-view-read.md` — ADR-0005 — the `< 50 ms` SLO is measured against a real `redis:7-alpine`; the substrate this story stands up is what the Step-7 bench measures.
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0006-gather-pipeline-runtime-closure.md` — `redis` is a Phase-8 runtime dep but **not** part of the gather-pipeline closure; it goes in `[project.dependencies]` only if a non-gather runtime needs it — see Notes.
- **Existing code (if any):**
  - `pyproject.toml §[project.dependencies]` and `§[project.optional-dependencies]` — the dependency declaration sites; note the `service = []` "Phase 9+ slot" comment and the existing dep-comment convention (each dep carries a phase + consumer comment).
  - `tests/unit/test_pyproject_fence.py` — the gather-closure fence; `redis` must not leak into the gather-runtime closure (see S1-04 for the explicit fence test).

## Goal
Provision a `redis:7-alpine` service in `docker-compose.yml` and add the `redis>=5` Python client to `pyproject.toml`, so a `redis-py` ping against `localhost:6379` succeeds and later hot-view stories have a real backing store.

## Acceptance criteria
- [ ] `docker-compose.yml` exists at the repo root with a `redis` service on `redis:7-alpine`, port `6379:6379`, AOF disabled and no replication configured.
- [ ] `redis>=5` is declared as a Phase-8 dependency in `pyproject.toml` with a phase + consumer comment in the existing dep-comment style.
- [ ] `docker compose up -d redis` starts the container and a throwaway `redis-py` `ping()` against `localhost:6379` returns `True`.
- [ ] `import redis` succeeds in the project venv after a `make bootstrap`.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Create `docker-compose.yml` at the repo root with one `redis` service: `image: redis:7-alpine`, `ports: ["6379:6379"]`, `command` (or `--appendonly no`) disabling AOF, no `replicaof`/replication.
2. Add `redis>=5` to `pyproject.toml` dependencies with a comment naming Phase 8 and `codegenie.hotviews.store.HotViewStore` as the consumer (decide `[project.dependencies]` vs a new slot per the Notes / ADR-0006 — confirm the runtime-closure implication and record the choice).
3. Run `make bootstrap` so the lock picks up `redis`; confirm `import redis` works.
4. Write the red test (parse `docker-compose.yml` for the service shape; assert `redis` is in the parsed deps).

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/test_redis_substrate.py`
One red test per behavior. Initially red because `docker-compose.yml` does not exist and `redis` is not a declared dep.

```python
def test_docker_compose_declares_redis_7_alpine() -> None:
    # Intent: the < 50 ms bench (Step 7) needs a real redis:7-alpine; the
    # substrate must be declared, not assumed.
    import tomllib  # noqa: F401  -- use yaml.safe_load for the compose file
    # arrange: read docker-compose.yml at repo root
    # act: parse the `services.redis` block
    # assert: image == "redis:7-alpine", port 6379 mapped, AOF disabled
    ...

def test_redis_client_is_a_declared_dependency() -> None:
    # Intent: redis-py must be installable so HotViewStore can import it.
    # arrange: read pyproject.toml, collect declared dependency names
    # act/assert: a dependency spec starting with "redis" exists with >=5
    ...
```
A real-Redis ping is a separate `@pytest.mark.bench`/integration concern (Step 7) — this story's red test is a static declaration check; the ping is verified manually per the acceptance criteria.

### Green — make it pass
Create the minimal `docker-compose.yml` and add the single `redis>=5` line to `pyproject.toml`. No code.

### Refactor — clean up
Match the dep-comment convention (every dep in `pyproject.toml` carries a phase + consumer comment). Confirm the compose file is minimal — one service, no volumes (the cache is reconstructable, ADR-0005 / `final-design.md`). Confirm `make bootstrap` is reproducible. ADR compliance: AOF off, no replication (Physical view).

## Files to touch
| Path | Why |
|---|---|
| `docker-compose.yml` | New file — the `redis:7-alpine` service (`:6379`, no AOF, no replication). |
| `pyproject.toml` | Add `redis>=5` with a Phase-8 dep comment. |
| `tests/unit/test_redis_substrate.py` | New test file — static checks on the compose service shape and the declared dep. |

## Out of scope
- The `import-linter` LLM-SDK fence group and the `mcp` SDK pin — S1-03.
- The `tests/fence/` Phase-8 wiring allowlist and the gather-closure fence test — S1-04.
- `HotViewStore` itself (the `redis-py` shell) — S5-01.
- Redis relocation to its own host / production topology — Phase 9.

## Notes for the implementer
- `redis` is not an LLM SDK — it does not touch the `FORBIDDEN_LLM_SDKS` fence. But it **must** stay outside the gather-runtime closure that `test_pyproject_fence.py` locks: `codegenie.hotviews` is referenced from the gather tail only through a thin detached-task callback (edge case 16). S1-04 adds the explicit fence test; do not import `redis` from any gather-closure module.
- Decide deliberately where `redis>=5` is declared. The gather pipeline does not import it; if no Phase-8 runtime is in the `[gather]` closure, it can ride `[project.dependencies]` like other non-gather runtime deps (`alembic`, `orjson`) provided the fence stays green. Record the choice and its rationale in the attempt log.
- Pin a floor (`>=5`), not an exact version — `redis-py` 5.x is the stable line; the SDK is mature (unlike `mcp`, S1-03).
- Keep the compose file minimal: no named volume (the hot-view cache is reconstructable from the next gather — ADR-0005), no AOF, no replica.
- The real-Redis ping is verified by hand per the acceptance criteria; the committed test is the static declaration check so CI does not require Docker.
