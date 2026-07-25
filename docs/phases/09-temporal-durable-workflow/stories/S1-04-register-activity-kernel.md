# Story S1-04 — `@register_activity` registry kernel

**Step:** Step 1 — Domain primitives, typed event contracts, and structural fences
**Status:** HARDENED
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** ADR-0007 (two-task-queue partitioning — the registry stores `task_queue` so workers can filter), production ADR-0043 (additive — every new activity is one decorator + one import line)

## Validation notes (2026-07-25)

Hardened via `/phase-story-validator`. Full report:
[`_validation/S1-04-register-activity-kernel.md`](_validation/S1-04-register-activity-kernel.md).

- **Removed a self-contradiction (Consistency-BLOCK).** The original story's
  Refactor step told the implementer to apply `functools.wraps`, which
  contradicts AC-3's identity assertion (`decorated is fn`). `functools.wraps`
  copies metadata onto a *wrapping* callable; the decorator here is a pure
  recorder that returns `fn` unchanged, so `__name__` and `__doc__` are
  preserved by construction. Refactor bullet rewritten to say
  "**do not use `functools.wraps`**" and to explain why.
- **Reconciled the arch signature discrepancy (Consistency-HARDEN).** Arch
  §C2 line 471 shows the 2-arg `register_activity(*, name, timeout)`
  form; the story uses the 3-arg form including `task_queue: TaskQueueName`.
  ADR-0007 §Consequences + arch line 1072 authorise the 3-arg form; §C2
  is a stale one-line excerpt. Documented inline so the executor doesn't
  hand-wring over the mismatch.
- **Introduced `MappingProxyType`-backed public accessor (Design-Patterns-HARDEN).**
  Kept `_ACTIVITIES` as module-private mutable state; exported a public
  `ACTIVITIES: Mapping[ActivityName, ActivityRegistration]` bound to
  `MappingProxyType(_ACTIVITIES)`. Mirrors Phase-0's `default_registry`
  public-accessor pattern (`src/codegenie/probes/registry.py`), enforces
  immutability at the seam, and eliminates the underscore-prefix-but-public
  smell.
- **Promoted `clean_activity_registry` fixture to an AC (Coverage-HARDEN).**
  Originally a Refactor prose bullet; every Step-4 activity-registration
  test file will pollute `_ACTIVITIES` without it. Now first-class in the
  ACs and Files-to-touch table.
- **Added mutation-resistant TDD tests (Test-Quality-HARDEN).** New tests
  cover: (a) two activities with *different* timeouts + task queues to
  defeat a hard-coded-default implementation; (b) `ActivityRegistration`
  frozen-ness (mutation → `FrozenInstanceError`); (c) `decorated.__name__`
  preserved by identity; (d) same function under two different names is
  permitted (AC-5 gains a test); (e) call site missing `task_queue`
  raises `TypeError` (kwargs-only + no-default is the enforcement).
- **Rewrote the explicit-import fence in AST (Test-Quality-HARDEN).** The
  substring-in-file check false-positives on the module docstring's citation
  of "no `importlib.metadata` scan" (Phase-0 precedent uses that exact
  phrasing). Fence now parses with `ast` and walks for real
  `Import`/`ImportFrom`/`Call(func=Attribute(attr=...))` nodes — docstring-safe
  and more mutation-resistant.
- **Added Open/Closed AC + Notes.** The Open/Closed extension guarantee
  (adding a new activity requires only a new file + one decorator + one
  import — never edits to the kernel or `ActivityRegistration`) is now an
  observable AC. Also documented: `@register_activity` is intentionally
  *single-shape* (kwargs-only), a deliberate divergence from Phase-0's
  dual-shape `@register_probe` because `name` is not defaultable.

## Context
Step 4 lands nine `@activity.defn`-decorated functions (one per file under `src/codegenie/durable/activities/`). The decorator the workflow body consumes is Temporal's `@activity.defn`; the *parallel* registry this codebase adds (`@register_activity`) tracks `(name, timeout, task_queue)` so workers can spin up the right activity pool per task queue (ADR-0007: `vuln-remediation-node-npm` vs `system`). The shape mirrors `@register_probe` from Phase 0 — explicit-import collection in `__init__.py`, registration-time collision raises `TypeError`. Worker bootstrap (S6-01) reads the registry to assemble each pool.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C2 — Activity catalog` — `register_activity(*, name: ActivityName, timeout: timedelta) -> Callable[[F], F]` shape. **Caveat:** the §C2 one-line excerpt at line 471 shows only 2 args; the authoritative form includes `task_queue: TaskQueueName` per ADR-0007 §Consequences and arch line 1072 ("Integration with Phase 10 — Per-task-class worker pools"). Use the 3-arg form.
  - `../phase-arch-design.md §Component design — module tree` — `codegenie/durable/activities/__init__.py (@register_activity)` lives at the collection point
  - `../phase-arch-design.md §Stable contracts vs internal` (line 294) — `@register_activity` is a **frozen Open/Closed extension point**; adding an activity in a later phase = new file + decorator + import line
  - `../phase-arch-design.md §Design patterns applied #6 — Registry pattern` — "Same shape as `@register_probe` from Phase 0" (with one intentional divergence: `@register_activity` is kwargs-only single-shape because `name` has no viable default)
  - `../phase-arch-design.md §Anti-patterns avoided` (line 970) — "Side effects in module import (registries are dicts populated lazily on first decorator invocation; `__init__.py` only imports modules)"
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
Ship `src/codegenie/durable/activities/__init__.py` with the `@register_activity(*, name, timeout, task_queue)` decorator + the module-level `_ACTIVITIES: dict[ActivityName, ActivityRegistration]` registry (private) and the public `ACTIVITIES: Mapping[ActivityName, ActivityRegistration]` read-view backed by `MappingProxyType(_ACTIVITIES)`; collision raises `TypeError` at import.

## Acceptance criteria
- [ ] `src/codegenie/durable/__init__.py` exists (marker module + docstring).
- [ ] `src/codegenie/durable/activities/__init__.py` exports `register_activity`, `ActivityRegistration`, and the public read-view `ACTIVITIES: Mapping[ActivityName, ActivityRegistration]`. The mutable module-private `_ACTIVITIES: dict[ActivityName, ActivityRegistration]` is **not** in `__all__` (kept for internal mutation by the decorator and for the `clean_activity_registry` fixture only).
- [ ] `ACTIVITIES` is `types.MappingProxyType(_ACTIVITIES)` — attempting `ACTIVITIES["x"] = ...` raises `TypeError` (immutable view). This is the seam consumers (S6-01 worker bootstrap) read.
- [ ] `ActivityRegistration` is `@dataclass(frozen=True, slots=True)` and carries `name: ActivityName`, `timeout: timedelta`, `task_queue: TaskQueueName`, `fn: Callable[..., Awaitable[Any]]`. Attempting to mutate any field on an instance raises `dataclasses.FrozenInstanceError`.
- [ ] `register_activity(*, name: ActivityName, timeout: timedelta, task_queue: TaskQueueName) -> Callable[[F], F]` is **keyword-only** (leading `*,`) with **no defaults** — omitting `task_queue` (or `name` or `timeout`) at the call site raises `TypeError` from the Python argument-binding layer. The kernel is deliberately single-shape (no bare-decorator form), a considered divergence from Phase-0's dual-shape `@register_probe`.
- [ ] The decorator returns the input callable **unchanged**: `register_activity(...)(fn) is fn` (object identity). No wrapping is performed; `functools.wraps` is deliberately *not* used (see Notes and TDD plan). `__name__` and `__doc__` are preserved by identity — verified: `register_activity(...)(fn).__name__ == fn.__name__`.
- [ ] Registering two different functions with the same `name` raises `TypeError(f"register_activity name collision: {name}")` at the second decoration. Registering the same `name` a third+ time also still raises (invariant is stable across repeat attempts).
- [ ] Registering the *same* function under two different names is permitted — both rows appear in `_ACTIVITIES` (independent registrations).
- [ ] A `clean_activity_registry` pytest fixture lands at `tests/conftest.py` (or `tests/unit/durable/activities/conftest.py`) that snapshots `_ACTIVITIES` in setup and restores it in teardown. Every test in `tests/unit/durable/activities/test_register_activity.py` uses the fixture; a regression test asserts the fixture actually restores (registration inside the test disappears after teardown).
- [ ] `tests/unit/durable/activities/test_register_activity.py` covers, at minimum: (a) happy-path registration populates `_ACTIVITIES` and `ACTIVITIES`; (b) name collision on second decoration raises `TypeError` with the offending name in the message; (c) decorated callable is identity (same object) AND `__name__` is preserved; (d) two registrations with *different* `timeout` and *different* `task_queue` values each carry their own correct row values (defeats a hard-coded-default implementation); (e) same function under two different names is permitted (independent rows); (f) `ActivityRegistration` mutation raises `FrozenInstanceError`; (g) `ACTIVITIES` is an immutable view (assignment raises `TypeError`); (h) call site missing `task_queue` raises `TypeError` at binding time.
- [ ] `tests/fence/test_durable_activities_init_explicit_imports.py` **parses `src/codegenie/durable/activities/__init__.py` with `ast`** and asserts that (i) there are no `Import` or `ImportFrom` nodes referencing `importlib.metadata` or `pkgutil`, and (ii) there are no `Call` nodes whose function attribute is `walk_packages`, `iter_modules`, or `entry_points`. Docstring text is ignored by construction (AST parses docstrings as string literals, not imports). Rationale: explicit-imports-only + cold-start hygiene + supply-chain hygiene, mirroring Phase-0 ADR-0007.
- [ ] **Open/Closed extension invariant.** Adding a new activity module in a later story must not require editing `src/codegenie/durable/activities/__init__.py`'s decorator definition or the `ActivityRegistration` dataclass. Observable at Step-4-story review: any new activity lands as (a) a new file, (b) one `@register_activity(...)` decoration, (c) one new `import` line in `activities/__init__.py`. Codified here as a Notes-for-implementer paragraph the executor's Validator pass will grep for.
- [ ] `mypy --strict src/codegenie/durable/` is clean.
- [ ] The TDD plan's red tests exist, were committed as `FAIL`s, and are green after the Green step.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on touched files.

## Implementation outline
1. Create `src/codegenie/durable/__init__.py` (one-line docstring citing the phase + the determinism fence).
2. Create `src/codegenie/durable/activities/__init__.py`:
   - Module docstring citing ADR-0007 + ADR-0043 + naming `@register_probe` as the precedent. The docstring MAY mention "no `importlib.metadata` / entry-point scan" verbatim; the AST-based fence will not false-positive on the string.
   - `@dataclass(frozen=True, slots=True)` `ActivityRegistration` with fields `name: ActivityName`, `timeout: timedelta`, `task_queue: TaskQueueName`, `fn: Callable[..., Awaitable[Any]]`. Annotate the `Any` with a one-line comment citing arch §C2 (heterogeneous activity IO — a `TypeVar` here would not buy anything).
   - Module-private `_ACTIVITIES: dict[ActivityName, ActivityRegistration] = {}`.
   - Module-public `ACTIVITIES: Mapping[ActivityName, ActivityRegistration] = types.MappingProxyType(_ACTIVITIES)`.
   - `register_activity(*, name, timeout, task_queue)` decorator: inner closure validates non-collision against `_ACTIVITIES` (raises `TypeError(f"register_activity name collision: {name}")` on duplicate), stores an `ActivityRegistration` in `_ACTIVITIES[name]`, and returns the original `fn` **unchanged** (no `functools.wraps` — see Notes and TDD plan below).
   - `__all__ = ["register_activity", "ActivityRegistration", "ACTIVITIES"]` (private `_ACTIVITIES` is intentionally omitted from the public surface; the fixture reaches for it by name from inside the package's test tree, which is legitimate).
3. Land the `clean_activity_registry` pytest fixture (see Files to touch — one conftest, one line per test).
4. Land the unit tests + the AST-based explicit-import fence.
5. `mypy --strict`; iterate until clean.

## TDD plan — red / green / refactor
### Red — write the failing tests first

Fixture — lands **before** the unit tests (they depend on it):
Test file path: `tests/unit/durable/activities/conftest.py`
```python
import pytest

@pytest.fixture
def clean_activity_registry():
    """Snapshot _ACTIVITIES pre-test; restore in teardown so tests are hermetic.

    Reaches for the module-private _ACTIVITIES by name; legitimate because the
    fixture ships alongside the module's own tests (same package).
    """
    from codegenie.durable.activities import _ACTIVITIES
    snapshot = dict(_ACTIVITIES)
    try:
        yield
    finally:
        _ACTIVITIES.clear()
        _ACTIVITIES.update(snapshot)
```

Test file path: `tests/unit/durable/activities/test_register_activity.py`
```python
import dataclasses
from datetime import timedelta
from types import MappingProxyType

import pytest
from codegenie.types.identifiers import ActivityName, TaskQueueName


def test_register_activity_populates_registry(clean_activity_registry):
    from codegenie.durable.activities import ACTIVITIES, _ACTIVITIES, register_activity

    @register_activity(
        name=ActivityName("test_alpha"),
        timeout=timedelta(seconds=5),
        task_queue=TaskQueueName("system"),
    )
    async def alpha(x: int) -> int:
        return x

    key = ActivityName("test_alpha")
    assert key in _ACTIVITIES
    assert key in ACTIVITIES  # public read-view sees the same row
    reg = _ACTIVITIES[key]
    assert reg.name == key
    assert reg.timeout == timedelta(seconds=5)
    assert reg.task_queue == TaskQueueName("system")
    assert reg.fn is alpha


def test_registered_rows_carry_distinct_timeouts_and_queues(clean_activity_registry):
    """Defeats a hard-coded-default implementation: both rows must carry
    the values threaded at their own call sites."""
    from codegenie.durable.activities import _ACTIVITIES, register_activity

    @register_activity(
        name=ActivityName("a_short"),
        timeout=timedelta(seconds=2),
        task_queue=TaskQueueName("system"),
    )
    async def short() -> None: ...

    @register_activity(
        name=ActivityName("a_long"),
        timeout=timedelta(minutes=20),
        task_queue=TaskQueueName("vuln-remediation-node-npm"),
    )
    async def long_() -> None: ...

    assert _ACTIVITIES[ActivityName("a_short")].timeout == timedelta(seconds=2)
    assert _ACTIVITIES[ActivityName("a_long")].timeout == timedelta(minutes=20)
    assert _ACTIVITIES[ActivityName("a_short")].task_queue == TaskQueueName("system")
    assert _ACTIVITIES[ActivityName("a_long")].task_queue == TaskQueueName("vuln-remediation-node-npm")


def test_register_activity_collision_raises_type_error(clean_activity_registry):
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

    # Invariant stability: third attempt still raises.
    with pytest.raises(TypeError, match=r"collision: collide_me"):
        @register_activity(
            name=ActivityName("collide_me"),
            timeout=timedelta(seconds=1),
            task_queue=TaskQueueName("system"),
        )
        async def third() -> None: ...


def test_same_function_two_names_is_permitted(clean_activity_registry):
    """AC-5: registering the same function under two different names is legal —
    each is an independent row."""
    from codegenie.durable.activities import _ACTIVITIES, register_activity

    async def fn() -> None: ...

    register_activity(
        name=ActivityName("name_alpha"),
        timeout=timedelta(seconds=1),
        task_queue=TaskQueueName("system"),
    )(fn)
    register_activity(
        name=ActivityName("name_beta"),
        timeout=timedelta(seconds=1),
        task_queue=TaskQueueName("system"),
    )(fn)

    assert _ACTIVITIES[ActivityName("name_alpha")].fn is fn
    assert _ACTIVITIES[ActivityName("name_beta")].fn is fn


def test_register_activity_is_identity_and_preserves_dunder_name(clean_activity_registry):
    from codegenie.durable.activities import register_activity

    async def fn() -> None:
        """docstring intact"""

    decorated = register_activity(
        name=ActivityName("identity_check"),
        timeout=timedelta(seconds=1),
        task_queue=TaskQueueName("system"),
    )(fn)
    assert decorated is fn                          # object identity
    assert decorated.__name__ == "fn"               # preserved by identity, not functools.wraps
    assert decorated.__doc__ == "docstring intact"  # ditto


def test_activity_registration_is_frozen():
    from codegenie.durable.activities import ActivityRegistration

    async def fn() -> None: ...
    reg = ActivityRegistration(
        name=ActivityName("frozen_check"),
        timeout=timedelta(seconds=1),
        task_queue=TaskQueueName("system"),
        fn=fn,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        reg.timeout = timedelta(seconds=99)  # type: ignore[misc]


def test_public_activities_view_is_immutable(clean_activity_registry):
    from codegenie.durable.activities import ACTIVITIES

    assert isinstance(ACTIVITIES, MappingProxyType)
    with pytest.raises(TypeError):
        ACTIVITIES[ActivityName("nope")] = None  # type: ignore[index]


def test_missing_task_queue_at_call_site_raises_type_error():
    """The kwargs-only, no-default signature enforces explicitness at binding time."""
    from codegenie.durable.activities import register_activity

    with pytest.raises(TypeError):
        register_activity(  # type: ignore[call-arg]
            name=ActivityName("missing_queue"),
            timeout=timedelta(seconds=1),
        )


def test_fixture_actually_restores(clean_activity_registry):
    """Meta-test: after this test's registration, the fixture teardown must
    restore _ACTIVITIES to the pre-test snapshot. Verified by re-running the
    same registration in a sibling test would succeed (see the collision
    test above using the same name is safe because of this fixture)."""
    from codegenie.durable.activities import _ACTIVITIES, register_activity

    baseline = len(_ACTIVITIES)

    @register_activity(
        name=ActivityName("ephemeral_row"),
        timeout=timedelta(seconds=1),
        task_queue=TaskQueueName("system"),
    )
    async def _e() -> None: ...

    assert len(_ACTIVITIES) == baseline + 1
    # Teardown restores; verified transitively by no other test hitting
    # "collision: ephemeral_row" when re-run in a loop.
```

Test file path: `tests/fence/test_durable_activities_init_explicit_imports.py`
```python
"""AST-based fence: activities/__init__.py must not perform dynamic discovery.

Substring-in-file matching would false-positive on the module's own docstring
citation of "no importlib.metadata / entry-point scan"; parsing with `ast`
ignores docstring string literals by construction.
"""
import ast
from pathlib import Path


_FORBIDDEN_IMPORT_ROOTS = frozenset({"importlib.metadata", "pkgutil"})
_FORBIDDEN_CALL_ATTRS = frozenset({"walk_packages", "iter_modules", "entry_points"})


def _walked(tree: ast.AST) -> list[ast.AST]:
    return list(ast.walk(tree))


def test_no_dynamic_discovery_in_activities_init():
    src = Path("src/codegenie/durable/activities/__init__.py").read_text()
    tree = ast.parse(src)

    for node in _walked(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in _FORBIDDEN_IMPORT_ROOTS, (
                    f"forbidden `import {alias.name}` in activities/__init__.py — "
                    "explicit-imports only (Phase-0 ADR-0007 + supply-chain hygiene)"
                )
                # `import importlib.metadata` shows as alias.name == "importlib.metadata"
                # `import importlib` alone is fine (stdlib import is common)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module not in _FORBIDDEN_IMPORT_ROOTS, (
                f"forbidden `from {module} import …` in activities/__init__.py — "
                "explicit-imports only (Phase-0 ADR-0007 + supply-chain hygiene)"
            )
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                assert func.attr not in _FORBIDDEN_CALL_ATTRS, (
                    f"forbidden call `<...>.{func.attr}(...)` in activities/__init__.py — "
                    "no dynamic-discovery calls; explicit imports only"
                )
            elif isinstance(func, ast.Name):
                assert func.id not in _FORBIDDEN_CALL_ATTRS, (
                    f"forbidden call `{func.id}(...)` in activities/__init__.py"
                )
```

### Green — make it pass
Module + decorator + frozen dataclass + private module-level dict + `MappingProxyType`-backed public view. Collision check before insert; `TypeError` with the offending name in the message.

### Refactor — clean up
- **Do NOT use `functools.wraps`.** The decorator returns `fn` unchanged (identity), so `__name__` and `__doc__` are preserved *by construction*. Wrapping via `functools.wraps` would break AC-3's identity assertion (`decorated is fn`). In Step 4, Temporal's `@activity.defn` will stack on top of `@register_activity`; because we return the same callable, `activity.defn` sees the original `fn.__name__` naturally.
- The decorator's signature uses keyword-only arguments (the leading `*,`) with **no defaults** — surface in docstring as "all arguments must be named at the call site *and* none are defaultable" so downstream code doesn't accidentally rely on an implicit `task_queue`.
- Confirm `ACTIVITIES` is truly a read-only view — `MappingProxyType` guarantees this at the type-system level and the fence test guarantees it at the source level.
- The registry is per-process; the `clean_activity_registry` fixture is now a first-class AC, not an afterthought — Step 4's activity-registration tests will depend on it.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/durable/__init__.py` | New marker package |
| `src/codegenie/durable/activities/__init__.py` | Decorator + `_ACTIVITIES` (private) + `ACTIVITIES` (`MappingProxyType` public view) + `ActivityRegistration` |
| `tests/unit/durable/__init__.py`, `tests/unit/durable/activities/__init__.py` | Markers |
| `tests/unit/durable/activities/conftest.py` | `clean_activity_registry` fixture (snapshot/restore around each test) |
| `tests/unit/durable/activities/test_register_activity.py` | Happy-path + distinct-timeouts/queues + collision + repeated-collision stability + same-fn-two-names + identity + `__name__` preservation + frozen `ActivityRegistration` + `MappingProxyType` immutability + missing-`task_queue` binding error + fixture meta-test |
| `tests/fence/test_durable_activities_init_explicit_imports.py` | AST-based fence: no `importlib.metadata`/`pkgutil` imports, no `walk_packages`/`iter_modules`/`entry_points` calls |

## Out of scope
- **Concrete activity bodies** (`emit_event`, `run_vuln_subgraph`, etc.) — Step 4.
- **`@activity.defn` stacking on top of `@register_activity`** — Step 4's per-activity story decides the order (the precedent in arch §C2 puts `@register_activity` outside `@activity.defn`).
- **`RetryPolicy` table** — Step 4 (S4-01) lands `_POLICIES: dict[ActivityName, RetryPolicy]` separately; this story does not include the retry-policy registry.
- **Worker bootstrap consumption** — Step 6 (S6-01) reads `_ACTIVITIES` to assemble per-queue worker pools.
- **`TaskQueueName` validation** (e.g., closed-set Literal of `"system" | "vuln-remediation-node-npm"`) — leave open; ADR-0007 explicitly expands by addition.

## Notes for the implementer
- The Phase-0 `@register_probe` precedent (`src/codegenie/probes/registry.py`) carries a `Registry` *class* alongside the module-level `default_registry`; this story is smaller — a module-level `_ACTIVITIES` dict + `MappingProxyType(_ACTIVITIES)` public view is enough. Do **not** introduce a `Registry` class unless Step 4 surfaces a real need (test isolation; pluggable scheduling annotations). Rule 2 — simplicity first; rule-of-three not met.
- **`@register_activity` is deliberately single-shape (kwargs-only, no bare-decorator form).** This is a considered divergence from Phase-0's dual-shape `@register_probe`: `@register_probe` supports a bare form because `Probe.name` is defined on the class and defaults are viable; here, `name` is required at the call site and has no viable default, so a bare form would be a runtime bug factory. Do not "fix" this to dual-shape — it is intentional.
- `register_activity` is a *parallel* decorator to Temporal's `@activity.defn`. Step 4 will stack them; the order matters because Temporal's decorator does runtime registration with its own SDK. Don't pre-stack in this story — just ship the kernel.
- Tests share the module-level `_ACTIVITIES` — the `clean_activity_registry` fixture is the discipline that keeps Step 4 tests from cross-polluting. Land the fixture in this story; every Step-4 test file will `import` it.
- **Do NOT use `functools.wraps`.** The decorator is a pure recorder that returns `fn` unchanged (identity), which preserves `__name__` and `__doc__` by construction. `functools.wraps` implies wrapping *another* callable and copying metadata onto it — that would break AC-3 (`decorated is fn`). Temporal's `@activity.defn` in Step 4 sees the original `fn.__name__` naturally because we return the same object.
- **`_ACTIVITIES` private, `ACTIVITIES` public.** Consumers (S6-01 worker bootstrap) read from `ACTIVITIES` (the `MappingProxyType` view) — this prevents accidental mutation of the registry from outside the decorator. The mutable `_ACTIVITIES` is reached for only by the decorator itself and by the `clean_activity_registry` fixture (which lives in the same package's test tree).
- The AST-based explicit-import fence (`test_durable_activities_init_explicit_imports.py`) is the **only** structural defense against a third-party package slipping an activity in via entry-points; treat it as load-bearing. AST-based (not substring) matters — the module's own docstring will cite ADR-0007's "no `importlib.metadata` scan" phrasing verbatim, and a substring fence would false-positive on that.
- The `task_queue` argument is what enables ADR-0007 partitioning; do not default it (force the caller to be explicit about which pool consumes the activity). The `*,` prefix + no defaults on all three parameters means a call site missing any argument is a `TypeError` from Python's argument-binding layer — the kernel doesn't need its own validation branch.
- **Open/Closed extension guarantee.** Adding a new activity in a later story must land as: (a) a new file under `src/codegenie/durable/activities/`, (b) one `@register_activity(...)` decoration, (c) one new `import` line in `activities/__init__.py`. Editing the decorator definition or the `ActivityRegistration` dataclass is *not* required. This is the same "loud compiler-policed additive edit" pattern that production ADR-0043 §1 sanctions (import-line additions are loud, bounded, reviewable).
- **`Any` in `fn: Callable[..., Awaitable[Any]]`.** The heterogeneous registry across nine activities with different arg/return shapes makes a `TypeVar` here useless (each activity has its *own* IO type). Annotate the `Any` with a one-line comment citing arch §C2 so a future reviewer doesn't try to "fix" it.
- **Arch §C2 vs ADR-0007 signature.** Arch §C2 line 471's one-line excerpt shows only 2 args (`name`, `timeout`); the authoritative 3-arg form (adds `task_queue`) is per ADR-0007 §Consequences + arch line 1072 ("Integration with Phase 10 — Per-task-class worker pools"). Use the 3-arg form; the arch excerpt is a stale short-form.
