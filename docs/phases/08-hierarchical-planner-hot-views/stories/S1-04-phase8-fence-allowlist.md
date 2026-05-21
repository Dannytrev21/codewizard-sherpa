# Story S1-04 — Enumerate the Phase-8 wiring allowlist and gather-closure fence

**Step:** Step 1 — Land the contract primitives and the runtime substrate
**Status:** Ready
**Effort:** S
**Depends on:** S1-01

## Context
Phase 8 adds four new packages, a Redis service line, and two new `pyproject.toml` dependency rows. The codebase's discipline is that structural wiring is enumerated in a `tests/fence/` entry so a silent regression is caught on every PR. This cross-cutting story lands the Phase-8 wiring allowlist and — load-bearing — a fence test confirming the four new packages stay **outside** the gather-runtime closure that `test_pyproject_fence.py` locks (edge case 16: a renderer accidentally imported into the gather closure would break ADR-0006). This is the last Step-1 substrate story; it makes the Phase-8 wiring auditable before any logic lands.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Testing strategy §CI gates` — "A new `tests/fence/` entry enumerating the Phase-8 wiring allowlist: the four new package imports, the `docker-compose.yml` redis service line, the `pyproject.toml` `redis`/`mcp` rows" and "A fence test confirming the four new packages are **outside** the gather-runtime closure `test_pyproject_fence.py` locks."
  - `../phase-arch-design.md §Edge cases §16` — a new package accidentally landing inside the gather-runtime closure; the renderer must be referenced via a thin detached-task callback, not an `import codegenie.hotviews` in the gather closure.
  - `../phase-arch-design.md §Development view` — the four flat packages (`supervisor/`, `planner/`, `hotviews/`, `mcp/`) and the two additive fence-enumerated edits (`RepoId`, the event variants).
  - `../High-level-impl.md §Step 1 §Implementation-level risks §6` — "the Step 1 fence test fails after Step 5 wires the gather-tail callback" — the fence is re-checked then.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0001-supervisor-graph-engine.md` — ADR-0001 — Phase 8 adds exactly two new runtime deps (`redis`, `mcp`); the allowlist enumerates exactly those two rows, not a third (`langgraph` is **not** added).
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0005-no-llm-sdk-in-gather-runtime-closure.md` — the gather-runtime-closure discipline the new fence test extends.
  - `../../../production/adrs/0006-gather-pipeline-runtime-closure.md` — the runtime closure `test_pyproject_fence.py` locks.
- **Existing code (if any):**
  - `tests/fence/` — the structural-defense suite; `test_fence_target_wiring.py` (pins the `make fence` recipe) and `test_per_submodule_cold_start.py` are the closest precedents for a wiring-enumeration fence.
  - `tests/unit/test_pyproject_fence.py` — the gather-runtime-closure fence; `parse_runtime_dep_names_from_toml` / `scan_installed_distribution` are the production functions; the new test asserts the four Phase-8 packages are not in that closure.
  - `src/codegenie/_fence.py` — `FORBIDDEN_LLM_SDKS` and the closure-scanning helpers.

## Goal
Add a `tests/fence/` entry that enumerates the Phase-8 wiring (four package imports, the `docker-compose.yml` redis line, the `pyproject.toml` `redis`/`mcp` rows) and asserts the four new packages stay outside the gather-runtime closure, so any silent wiring regression fails CI.

## Acceptance criteria
- [ ] A new `tests/fence/test_phase8_wiring_allowlist.py` enumerates the Phase-8 wiring: the four package names (`codegenie.supervisor`, `codegenie.planner`, `codegenie.hotviews`, `codegenie.mcp`), the `docker-compose.yml` `redis` service line, and the `pyproject.toml` `redis` and `mcp` dependency rows.
- [ ] A test asserts the `pyproject.toml` `redis` and `mcp` rows are present (the allowlist is the expected set; a missing row fails).
- [ ] A test asserts the four Phase-8 packages are **not** in the gather-runtime closure `test_pyproject_fence.py` locks — neither in `[project].dependencies`'s gather closure nor imported by any gather-pipeline module.
- [ ] `make fence` runs the new test (the `Makefile` `fence:` recipe already globs `tests/fence/` — confirm the new file is picked up).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Create `tests/fence/test_phase8_wiring_allowlist.py` with module-level `Final` tuples enumerating: the four Phase-8 package names, the expected `pyproject.toml` dependency rows (`redis`, `mcp`), and the `docker-compose.yml` redis-service marker.
2. Write a test parsing `pyproject.toml` (via `tomllib`) that asserts the `redis` and `mcp` dependency rows are present in the enumerated allowlist.
3. Write a test parsing `docker-compose.yml` that asserts the `redis` service line is present.
4. Write the gather-closure test: reuse `codegenie._fence` helpers / `test_pyproject_fence.py`'s parsing to confirm none of the four Phase-8 packages are reachable from the gather-runtime closure.
5. Confirm `make fence` picks up the new file (the recipe globs `tests/fence/` per `test_fence_target_wiring.py`).

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/fence/test_phase8_wiring_allowlist.py`
One red test per behavior. The deps-row tests are red until S1-02/S1-03 land the rows; the gather-closure test is green-by-construction now and stays green after Step 5 wires the gather-tail callback (that is the point — edge case 16).

```python
_PHASE8_PACKAGES: Final[tuple[str, ...]] = (
    "codegenie.supervisor", "codegenie.planner",
    "codegenie.hotviews", "codegenie.mcp",
)

def test_phase8_dependency_rows_present() -> None:
    # Intent: redis + mcp are the exactly-two new deps (ADR-0001 — not a third).
    # arrange: tomllib-parse pyproject.toml, collect dependency names
    # act/assert: {"redis", "mcp"} is a subset of the declared deps
    ...

def test_docker_compose_redis_line_enumerated() -> None:
    # Intent: the redis service line is part of the audited Phase-8 wiring.
    # assert: docker-compose.yml has a `redis` service on redis:7-alpine
    ...

def test_phase8_packages_outside_gather_runtime_closure() -> None:
    # Intent: edge case 16 — a renderer imported into the gather closure
    # would break ADR-0006; the renderer is reached via a detached callback.
    # arrange: derive the gather-runtime closure via test_pyproject_fence's
    #          parsing (codegenie._fence helpers)
    # act/assert: no Phase-8 package name appears in the gather closure
    ...
```

### Green — make it pass
The deps-row tests go green once S1-02/S1-03 are in. The gather-closure test goes green by construction (no Phase-8 package is in the closure yet). No `src/` code is added by this story.

### Refactor — clean up
Use module-level `Final` tuples for the enumerated allowlist (the codebase's "data-driven, iterated not branched" convention — mirrors `_REQUIRED_PATHS_IN_FENCE_RECIPE` in `test_fence_target_wiring.py`). Add a module docstring explaining the fence's purpose and that it is re-checked after Step 5 wires the gather-tail callback. ADR compliance: the allowlist enumerates exactly two new dep rows — assert there is no third (no `langgraph`).

## Files to touch
| Path | Why |
|---|---|
| `tests/fence/test_phase8_wiring_allowlist.py` | New fence file — enumerates the Phase-8 wiring; asserts the four packages stay outside the gather closure. |

## Out of scope
- Declaring the `redis`/`mcp` deps and the `docker-compose.yml` service — S1-02 and S1-03 (this story enumerates and fences them; it does not create them).
- The LLM-SDK `import-linter` contract — S1-03.
- The gather-tail render callback that this fence re-validates — S5-07.

## Notes for the implementer
- This story's deps-row tests depend on S1-02 and S1-03 having landed their rows — sequence it after both, or write the tests red and let them go green as the sibling stories merge. Record the dependency in the attempt log.
- The gather-closure test is the load-bearing one: it must still pass after S5-07 wires the gather-tail render callback. If it fails then, the renderer was imported into the gather closure instead of being reached through a detached-task callback (edge case 16) — that is a real regression, not a test to relax.
- Reuse `codegenie._fence`'s closure-scanning helpers rather than re-deriving the gather closure — `test_pyproject_fence.py` invokes the same production code path; coupling to it keeps one source of truth.
- Enumerate exactly two new dependency rows. ADR-0001 caps Phase 8 at `redis` + `mcp`; a test asserting "no `langgraph`" makes the dep-count discipline a CI gate.
- `make fence` already globs `tests/fence/` (`test_fence_target_wiring.py` pins the recipe) — a new file in that directory is picked up automatically; confirm, don't re-wire the `Makefile`.
- Keep the allowlist as module-level `Final` tuples iterated by the tests — never branch on package names; this matches the codebase's data-driven-registry convention.
