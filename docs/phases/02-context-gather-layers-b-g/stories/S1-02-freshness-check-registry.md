# Story S1-02 — `@register_index_freshness_check` decorator-registry

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Ready
**Effort:** S
**Depends on:** S1-01, S1-05
**ADRs honored:** 02-ADR-0006

## Context

`IndexHealthProbe` (B2) would otherwise grow a `match index_name:` block that every phase has to edit when a new index source appears (Phase 3 SCIP-per-language, Phase 7 distroless target, Phase 14 cross-repo SCIP). The architect's Gap-3 fix closes that Open/Closed failure mode the way the rest of the design closes others: a decorator-registry. Each Phase-2 index source registers a tiny function `(slice, head) -> IndexFreshness`; B2 loops the registry instead of switching on index name. This story plants the registry primitive — zero consumers in this story, but everything else in Steps 4–6 will register through it.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Gap 3" — IndexHealthProbe couples to every sibling probe's slice shape` — the named gap; the prescribed fix is this decorator-registry.
  - `../phase-arch-design.md §"Component design" #1 — IndexHealthProbe` — describes how B2 loops the registry (consumed by S4-01).
  - `../phase-arch-design.md §"Design patterns applied"` row 5 — `@register_dep_graph_strategy` precedent; this registry is the symmetric counterpart for freshness checks.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0006-index-freshness-sum-type-location.md` — 02-ADR-0006 §Decisions noted — the registry location decision (Phase 2 lands it inside `codegenie.indices.registry`; ADR amendment optional only if friction arises).
- **Source design:**
  - `../final-design.md §"Synthesis ledger" — Open Q 1` — first-class registry location resolved here.
- **Existing code:**
  - `src/codegenie/probes/registry.py` — model after this — a class-based `Registry` + module-level `default_registry` + a `register_*` decorator function that targets it. Duplicate-name detection raises a typed error at decoration time (i.e., import time) for fail-loud semantics.
  - `src/codegenie/indices/__init__.py` / `src/codegenie/indices/freshness.py` — S1-01 lands them; the registry imports `IndexFreshness` from here.
- **External docs (only if directly relevant):**
  - None.

## Goal

Implement `src/codegenie/indices/registry.py` exposing `@register_index_freshness_check(index_name: IndexName)` — a decorator-registry that registers `(slice: dict[str, JSONValue], head: str) -> IndexFreshness` functions, rejects duplicate `index_name` at import time, and offers a `dispatch_all(slices, head) -> dict[IndexName, IndexFreshness]` method totalled over every registered name.

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/indices/registry.py` exists and exports `register_index_freshness_check`, `default_freshness_registry`, `FreshnessRegistry`, `FreshnessCheck` (the function-type alias), and a typed `FreshnessRegistryError` (subclass of `codegenie.errors.CodegenieError`) via `__all__`.
- [ ] **AC-2.** `register_index_freshness_check(index_name: IndexName)` is a decorator-factory; the inner decorator registers the function in `default_freshness_registry` and returns the function unchanged so the registration is non-invasive.
- [ ] **AC-3.** Duplicate-name registration raises `FreshnessRegistryError` at decoration time (i.e., module import), with a message containing both the offending `index_name` value and both call sites (`module.qualname` of each function), mirroring `codegenie.probes.registry.Registry.register`.
- [ ] **AC-4.** `FreshnessCheck` signature is exactly `Callable[[dict[str, JSONValue], str], IndexFreshness]` (slice + head; returns a typed freshness value, never raises by contract). `dict[str, JSONValue]` reuses Phase 0's `codegenie.output.sanitizer.JSONValue` recursive type alias (do **not** redefine).
- [ ] **AC-5.** `FreshnessRegistry.dispatch_all(slices: dict[IndexName, dict[str, JSONValue]], head: str) -> dict[IndexName, IndexFreshness]` is total over every registered index name; if a `slices[name]` key is missing, the registered check is still invoked with an empty dict (its responsibility to emit `Stale(IndexerError(message=f"upstream_{name}_unavailable"))`).
- [ ] **AC-6.** Registered functions whose `index_name` is not in `slices.keys()` still appear in the output (the registry is the source of truth for *expected* indices; B2 will treat a missing slice as a degraded upstream — that logic lives in S4-01, not here).
- [ ] **AC-7.** A test exercises a synthetic registration of two checks via the decorator on a fresh `FreshnessRegistry` (not the module-level singleton), then asserts dispatch returns both, dispatching the right slice to each.
- [ ] **AC-8.** The TDD plan's red test exists, was committed, and is green.
- [ ] **AC-9.** Tests live under `tests/unit/indices/test_freshness_registry.py` and use a *local* `FreshnessRegistry()` instance, never `default_freshness_registry`, to avoid cross-test pollution (mirroring `tests/unit/probes/test_registry.py`).
- [ ] **AC-10.** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/indices/test_freshness_registry.py` all pass on the touched files.

## Implementation outline

1. Create `src/codegenie/indices/registry.py` with: a `FreshnessRegistryError` marker subclass of `CodegenieError`; the `FreshnessCheck` type alias; the `FreshnessRegistry` class with `register`, `registered_names`, `dispatch_all`; the module-level `default_freshness_registry = FreshnessRegistry()`; the `register_index_freshness_check(index_name: IndexName)` decorator-factory targeting the default singleton.
2. Add `FreshnessRegistryError` to `src/codegenie/errors.py` as a bare marker subclass (per Phase 0 markers-only convention; same shape as `ProbeError`).
3. Update `src/codegenie/indices/__init__.py` to re-export the registry surface (`register_index_freshness_check`, `default_freshness_registry`, `FreshnessRegistry`, `FreshnessCheck`, `FreshnessRegistryError`).
4. Write the red test against a fresh `FreshnessRegistry()` instance, exercising decoration → dispatch → duplicate-name rejection.
5. Implement; confirm green.
6. Refactor: docstrings, `__all__`, log line emitted on every registration (`structlog` event `indices.freshness_check.registered`), idempotence assertion.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/indices/test_freshness_registry.py`

```python
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from codegenie.errors import FreshnessRegistryError
from codegenie.indices import (
    CommitsBehind,
    Fresh,
    FreshnessRegistry,
    IndexerError,
    Stale,
    register_index_freshness_check,
)
from codegenie.indices.registry import FreshnessCheck  # type alias
from codegenie.types.identifiers import IndexName


def test_register_and_dispatch_round_trip() -> None:
    # arrange: fresh local registry; do NOT touch the module-level default.
    reg = FreshnessRegistry()
    scip = IndexName("scip")
    runtime = IndexName("runtime_trace")

    @reg.register(scip)
    def check_scip(slice_: dict[str, object], head: str) -> "IndexFreshness":
        last = slice_.get("last_indexed_commit")
        if last == head:
            return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=timezone.utc))
        return Stale(reason=CommitsBehind(n=1, last_indexed=str(last or "")))

    @reg.register(runtime)
    def check_runtime(slice_: dict[str, object], head: str) -> "IndexFreshness":
        return Stale(reason=IndexerError(message="upstream_runtime_unavailable"))

    # act
    result = reg.dispatch_all(
        slices={scip: {"last_indexed_commit": "deadbeef"}, runtime: {}},
        head="cafef00d",
    )

    # assert: every registered name appears; dispatched to the right function.
    assert set(result.keys()) == {scip, runtime}
    assert isinstance(result[scip], Stale)
    assert isinstance(result[scip].reason, CommitsBehind)
    assert isinstance(result[runtime].reason, IndexerError)


def test_duplicate_name_rejected_at_registration_time() -> None:
    reg = FreshnessRegistry()
    name = IndexName("scip")

    @reg.register(name)
    def check_a(slice_: dict[str, object], head: str) -> "IndexFreshness":
        return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=timezone.utc))

    with pytest.raises(FreshnessRegistryError) as exc_info:
        @reg.register(name)
        def check_b(slice_: dict[str, object], head: str) -> "IndexFreshness":
            return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=timezone.utc))

    msg = exc_info.value.args[0]
    assert "scip" in msg
    assert "check_a" in msg
    assert "check_b" in msg


def test_decorator_returns_function_unchanged() -> None:
    reg = FreshnessRegistry()

    def f(slice_: dict[str, object], head: str) -> "IndexFreshness":
        return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=timezone.utc))

    returned = reg.register(IndexName("x"))(f)
    assert returned is f  # decorator is non-invasive


def test_module_level_decorator_uses_default_singleton() -> None:
    # The convenience decorator delegates to default_freshness_registry — verified
    # by registering on it and observing the singleton's registered_names.
    from codegenie.indices import default_freshness_registry

    name = IndexName("__test_singleton_marker__")

    @register_index_freshness_check(name)
    def check_marker(slice_: dict[str, object], head: str) -> "IndexFreshness":
        return Fresh(indexed_at=datetime(2026, 5, 14, tzinfo=timezone.utc))

    try:
        assert name in default_freshness_registry.registered_names()
    finally:
        # Be a good citizen — don't pollute downstream tests in the same process.
        default_freshness_registry.unregister_for_tests(name)


def test_dispatch_invokes_check_with_empty_dict_when_slice_missing() -> None:
    reg = FreshnessRegistry()
    name = IndexName("runtime_trace")
    captured: list[dict[str, object]] = []

    @reg.register(name)
    def check(slice_: dict[str, object], head: str) -> "IndexFreshness":
        captured.append(slice_)
        return Stale(reason=IndexerError(message="upstream_runtime_unavailable"))

    out = reg.dispatch_all(slices={}, head="abc123")
    assert name in out
    assert captured == [{}]
    assert isinstance(out[name].reason, IndexerError)
```

Run — confirm `ImportError: cannot import name 'FreshnessRegistry' from 'codegenie.indices'`. Commit.

### Green — make it pass

```python
# src/codegenie/indices/registry.py
from __future__ import annotations
from collections.abc import Callable
from typing import TYPE_CHECKING

import structlog

from codegenie.errors import FreshnessRegistryError
from codegenie.types.identifiers import IndexName

if TYPE_CHECKING:
    from codegenie.indices.freshness import IndexFreshness

JSONValue = object  # use codegenie.output.sanitizer.JSONValue if already public; otherwise the
                    # registry contract carries no narrower shape than "Pydantic-serializable".
FreshnessCheck = Callable[[dict[str, "JSONValue"], str], "IndexFreshness"]

_log = structlog.get_logger(__name__)


class FreshnessRegistry:
    def __init__(self) -> None:
        self._checks: dict[IndexName, FreshnessCheck] = {}
        self._origins: dict[IndexName, str] = {}  # for fail-loud duplicate messages

    def register(self, index_name: IndexName) -> Callable[[FreshnessCheck], FreshnessCheck]:
        def _decorator(fn: FreshnessCheck) -> FreshnessCheck:
            if index_name in self._checks:
                prior = self._origins[index_name]
                raise FreshnessRegistryError(
                    f"duplicate index_name {index_name!r}: "
                    f"{prior} and {fn.__module__}.{fn.__qualname__}"
                )
            self._checks[index_name] = fn
            self._origins[index_name] = f"{fn.__module__}.{fn.__qualname__}"
            _log.debug("indices.freshness_check.registered", index_name=index_name)
            return fn
        return _decorator

    def registered_names(self) -> frozenset[IndexName]:
        return frozenset(self._checks)

    def dispatch_all(
        self,
        slices: dict[IndexName, dict[str, "JSONValue"]],
        head: str,
    ) -> dict[IndexName, "IndexFreshness"]:
        return {
            name: check(slices.get(name, {}), head)
            for name, check in self._checks.items()
        }

    def unregister_for_tests(self, index_name: IndexName) -> None:
        """Test-only convenience to keep the singleton clean across tests."""
        self._checks.pop(index_name, None)
        self._origins.pop(index_name, None)


default_freshness_registry = FreshnessRegistry()


def register_index_freshness_check(
    index_name: IndexName,
) -> Callable[[FreshnessCheck], FreshnessCheck]:
    """Decorator targeting :data:`default_freshness_registry`."""
    return default_freshness_registry.register(index_name)


__all__ = [
    "FreshnessCheck",
    "FreshnessRegistry",
    "default_freshness_registry",
    "register_index_freshness_check",
]
```

Add the marker exception:

```python
# in src/codegenie/errors.py — append (markers only, per Phase 0/1 convention)
class FreshnessRegistryError(CodegenieError):
    """Raised by indices.registry on duplicate @register_index_freshness_check
    decoration; hard fail at import time (load-bearing fail-loud surface)."""
```

Update `__all__` of `codegenie.errors`. Re-export from `codegenie/indices/__init__.py`:

```python
from codegenie.indices.registry import (
    FreshnessCheck, FreshnessRegistry,
    default_freshness_registry, register_index_freshness_check,
)
```

### Refactor — clean up

- Type hints already strict. Add module docstring referencing 02-ADR-0006 §Decisions noted #1 and the architect's Gap-3 fix.
- The `FreshnessCheck` alias is exposed at package level so probes can spell it without dipping into the submodule.
- Docstring `unregister_for_tests` clearly: this is **test-only** and the name carries the intent (do not invent a "deregister" public API).
- Confirm the structlog `indices.freshness_check.registered` event has at least one log-emission assertion test (covered by the "Cross-cutting concerns" §Structured logging from the manifest).
- Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/indices/ tests/unit/indices/test_freshness_registry.py`, `pytest tests/unit/indices/test_freshness_registry.py -v`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/indices/registry.py` | New module; decorator-registry primitive. |
| `src/codegenie/indices/__init__.py` | Extend re-exports with the registry surface. |
| `src/codegenie/errors.py` | Append `FreshnessRegistryError` marker; extend `__all__`. |
| `tests/unit/indices/test_freshness_registry.py` | Red-then-green coverage of register / dispatch / duplicate / module decorator. |

## Out of scope

- **`IndexHealthProbe` looping the registry** — handled by S4-01.
- **Phase-2 index source registrations** (SCIP, runtime trace, semgrep, gitleaks, conventions) — those land in their own probe stories (S5-05, S6-08) once the probes exist.
- **`mypy --warn-unreachable` per-module override on `codegenie.indices/**`** — handled by S1-11.
- **Phase 3+ ecosystem-specific index sources** — registered later via the same decorator from inside the Phase 3 plugin; no edit to this file is required.

## Notes for the implementer

- **Singleton vs. local registry discipline.** Tests MUST use a local `FreshnessRegistry()` instance. The `test_module_level_decorator_uses_default_singleton` test is the one exception — guard it with `unregister_for_tests` in a `finally`, exactly as shown.
- **Duplicate-name failure is import-time, not dispatch-time.** Mirror `codegenie.probes.registry.Registry.register`'s fail-loud-at-decoration discipline. A registry that fails silently is worse than no registry.
- **`FreshnessCheck` does not raise.** By contract, a check function takes a slice + head and returns a typed freshness value. If construction fails internally, it returns `Stale(IndexerError(message="..."))`. The registry does not catch exceptions; an exception from a check is a bug and must propagate (see Phase 0's coordinator isolation — it's the right place to catch).
- **The `slices` parameter to `dispatch_all` is *the coordinator-provided slice map* — already-sanitized.** The registry contract has no opinion on `dict[str, JSONValue]`'s typing depth; Phase 0's `JSONValue` is the right reuse. Do **not** invent a narrower `IndexSlice` Pydantic model here — that is a Step-4 IndexHealthProbe-internal concern.
- **Why not Pydantic for the function type?** A `Callable[[dict, str], IndexFreshness]` is the simplest correct typing surface; Pydantic models with `__call__` are pattern-soup (final-design Anti-patterns §"Pattern soup" precedent). The registry stays a plain dict + decorator.
- **`unregister_for_tests` is intentionally awkward.** The name is the policy; do not promote it to a normal `unregister` public method.
