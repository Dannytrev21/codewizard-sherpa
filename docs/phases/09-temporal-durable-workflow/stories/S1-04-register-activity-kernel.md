# Story S1-04 — `@register_activity` registry kernel

**Step:** Step 1 — Domain primitives, typed event contracts, and structural fences
**Status:** Ready
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** ADR-0007 (two-task-queue partitioning — the registry stores `task_queue` so workers can filter), production ADR-0043 (additive — every new activity is one decorator + one import line)

## Context
Step 4 lands nine `@activity.defn`-decorated functions (one per file under `src/codegenie/durable/activities/`). The decorator the workflow body consumes is Temporal's `@activity.defn`; the *parallel* registry this codebase adds (`@register_activity`) tracks `(name, timeout, task_queue)` so workers can spin up the right activity pool per task queue (ADR-0007: `vuln-remediation-node-npm` vs `system`). The shape mirrors `@register_probe` from Phase 0 — explicit-import collection in `__init__.py`, registration-time collision raises `TypeError`. Worker bootstrap (S6-01) reads the registry to assemble each pool.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C2 — Activity catalog` — `register_activity(*, name: ActivityName, timeout: timedelta) -> Callable[[F], F]` shape
  - `../phase-arch-design.md §Component design — module tree` — `codegenie/durable/activities/__init__.py (@register_activity)` lives at the collection point
  - `../phase-arch-design.md §Design patterns applied #6 — Registry pattern` — "Same shape as `@register_probe` from Phase 0"
- **Phase ADRs:**
  - `../ADRs/0007-two-task-queue-partitioning-and-expansion-by-addition.md` — `task_queue: TaskQueueName` is a first-class registration field; new queues expand the registry without editing the kernel
- **Production ADRs:**
  - `../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md` — new activities land as new modules + one decorator + one import line in `__init__.py`
- **Source design:**
  - `../final-design.md §Synthesis ledger` — registry pattern row
- **Existing code:**
  - `src/codegenie/probes/registry.py` — the canonical Phase-0 registry shape this story mirrors (header docstring §"explicit-imports collection point"); read the `register_probe` decorator, the `Registry` data structure, and the module-level `default_registry` pattern
  - `src/codegenie/probes/__init__.py` — explicit-import collection point precedent
  - `src/codegenie/types/identifiers.py` — `ActivityName` (landed in S1-01); `TaskQueueName` (landed in S1-01)

## Goal
Ship `src/codegenie/durable/activities/__init__.py` with the `@register_activity(*, name, timeout, task_queue)` decorator + the module-level `_ACTIVITIES: dict[ActivityName, ActivityRegistration]` registry; collision raises `TypeError` at import.

## Acceptance criteria
- [ ] `src/codegenie/durable/__init__.py` exists (marker module + docstring).
- [ ] `src/codegenie/durable/activities/__init__.py` exports `register_activity` and `_ACTIVITIES`, plus an `ActivityRegistration` frozen dataclass carrying `name: ActivityName`, `timeout: timedelta`, `task_queue: TaskQueueName`, and `fn: Callable[..., Awaitable[Any]]`.
- [ ] `register_activity(*, name: ActivityName, timeout: timedelta, task_queue: TaskQueueName) -> Callable[[F], F]` is keyword-only and returns the decorated function unchanged.
- [ ] Registering two different functions with the same `name` raises `TypeError(f"register_activity name collision: {name}")` at the second decoration.
- [ ] Registering the same function under two different names is permitted (independent registrations).
- [ ] `tests/unit/durable/activities/test_register_activity.py` covers: (a) happy-path registration populates `_ACTIVITIES`; (b) collision raises; (c) decorated function is identity (same callable, same `__name__`); (d) `ActivityRegistration` carries the threaded `timeout` and `task_queue`.
- [ ] `tests/fence/test_durable_activities_init_explicit_imports.py` asserts `src/codegenie/durable/activities/__init__.py` contains *no* `importlib.metadata`/entry-point scan logic and *no* `pkgutil.walk_packages` (cold-start hygiene; mirrors Phase 0 ADR-0007 — explicit imports only).
- [ ] `mypy --strict src/codegenie/durable/` is clean.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on touched files.

## Implementation outline
1. Create `src/codegenie/durable/__init__.py` (one-line docstring citing the phase + the determinism fence).
2. Create `src/codegenie/durable/activities/__init__.py`:
   - Module docstring citing ADR-0007 + ADR-0043 + naming `@register_probe` as the precedent.
   - `@dataclass(frozen=True, slots=True)` `ActivityRegistration`.
   - Module-level `_ACTIVITIES: dict[ActivityName, ActivityRegistration] = {}`.
   - `register_activity(*, name, timeout, task_queue)` decorator; inner closure validates non-collision, stores the registration, returns the original function.
   - `__all__ = ["register_activity", "ActivityRegistration", "_ACTIVITIES"]`.
3. Land the unit tests + the explicit-import fence.
4. `mypy --strict`; iterate until clean.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/durable/activities/test_register_activity.py`
```python
from datetime import timedelta
import pytest
from codegenie.types.identifiers import ActivityName, TaskQueueName

def test_register_activity_populates_registry():
    from codegenie.durable.activities import register_activity, _ACTIVITIES

    @register_activity(
        name=ActivityName("test_alpha"),
        timeout=timedelta(seconds=5),
        task_queue=TaskQueueName("system"),
    )
    async def alpha(x: int) -> int:
        return x

    assert ActivityName("test_alpha") in _ACTIVITIES
    reg = _ACTIVITIES[ActivityName("test_alpha")]
    assert reg.timeout == timedelta(seconds=5)
    assert reg.task_queue == TaskQueueName("system")
    assert reg.fn is alpha

def test_register_activity_collision_raises_type_error():
    from codegenie.durable.activities import register_activity

    @register_activity(
        name=ActivityName("collide_me"),
        timeout=timedelta(seconds=1),
        task_queue=TaskQueueName("system"),
    )
    async def first() -> None: ...

    with pytest.raises(TypeError, match=r"collision: collide_me"):
        @register_activity(
            name=ActivityName("collide_me"),
            timeout=timedelta(seconds=1),
            task_queue=TaskQueueName("system"),
        )
        async def second() -> None: ...

def test_register_activity_is_identity():
    from codegenie.durable.activities import register_activity

    async def fn() -> None: ...
    decorated = register_activity(
        name=ActivityName("identity_check"),
        timeout=timedelta(seconds=1),
        task_queue=TaskQueueName("system"),
    )(fn)
    assert decorated is fn
```

Test file path: `tests/fence/test_durable_activities_init_explicit_imports.py`
```python
def test_no_dynamic_discovery_in_activities_init():
    from pathlib import Path
    src = Path("src/codegenie/durable/activities/__init__.py").read_text()
    forbidden = ("importlib.metadata", "entry_points", "pkgutil.walk_packages",
                 "iter_modules")
    for token in forbidden:
        assert token not in src, (
            f"{token} found in activities/__init__.py — explicit-imports only "
            "(mirrors Phase 0 ADR-0007 + supply-chain hygiene)."
        )
```

### Green — make it pass
Module + decorator + frozen dataclass + module-level dict. Collision check before insert; `TypeError` with the offending name.

### Refactor — clean up
- Use `functools.wraps` so the decorator preserves `__name__`, `__doc__`, etc. — necessary for Temporal's `@activity.defn` to see the original function name when stacked on top in Step 4.
- The decorator's signature uses keyword-only arguments (the leading `*,`) — surface in docstring as "all arguments must be named at the call site" to match the arch contract.
- The registry is per-process; tests that pollute `_ACTIVITIES` must clean up — provide a `pytest` fixture `clean_activity_registry` that snapshots `_ACTIVITIES` and restores in teardown. (Failure mode: subsequent Step-4 tests see stale registrations.)

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/durable/__init__.py` | New marker package |
| `src/codegenie/durable/activities/__init__.py` | Decorator + registry + `ActivityRegistration` |
| `tests/unit/durable/__init__.py`, `tests/unit/durable/activities/__init__.py` | Markers |
| `tests/unit/durable/activities/test_register_activity.py` | Happy-path + collision + identity |
| `tests/fence/test_durable_activities_init_explicit_imports.py` | No dynamic discovery |
| `tests/conftest.py` *(or local conftest)* | `clean_activity_registry` fixture (snapshot/restore) |

## Out of scope
- **Concrete activity bodies** (`emit_event`, `run_vuln_subgraph`, etc.) — Step 4.
- **`@activity.defn` stacking on top of `@register_activity`** — Step 4's per-activity story decides the order (the precedent in arch §C2 puts `@register_activity` outside `@activity.defn`).
- **`RetryPolicy` table** — Step 4 (S4-01) lands `_POLICIES: dict[ActivityName, RetryPolicy]` separately; this story does not include the retry-policy registry.
- **Worker bootstrap consumption** — Step 6 (S6-01) reads `_ACTIVITIES` to assemble per-queue worker pools.
- **`TaskQueueName` validation** (e.g., closed-set Literal of `"system" | "vuln-remediation-node-npm"`) — leave open; ADR-0007 explicitly expands by addition.

## Notes for the implementer
- The Phase-0 `@register_probe` precedent (`src/codegenie/probes/registry.py`) carries a `Registry` *class* alongside the module-level `default_registry`; this story is smaller — a module-level `_ACTIVITIES` dict is enough. Do **not** introduce a `Registry` class unless Step 4 surfaces a real need (test isolation; pluggable scheduling annotations). Match the smaller pattern.
- `register_activity` is a *parallel* decorator to Temporal's `@activity.defn`. Step 4 will stack them; the order matters because Temporal's decorator does runtime registration with its own SDK. Don't pre-stack in this story — just ship the kernel.
- Tests share the module-level `_ACTIVITIES` — the `clean_activity_registry` fixture is the discipline that keeps Step 4 tests from cross-polluting.
- `functools.wraps` preserves `__name__`; Temporal uses `fn.__name__` as the default activity name when none is passed to `@activity.defn` — getting this wrong is a debugging nightmare in Step 6.
- The explicit-import fence (`test_durable_activities_init_explicit_imports.py`) is the **only** structural defense against a third-party package slipping an activity in via entry-points; treat it as load-bearing.
- The `task_queue` argument is what enables ADR-0007 partitioning; do not default it (force the caller to be explicit about which pool consumes the activity).
