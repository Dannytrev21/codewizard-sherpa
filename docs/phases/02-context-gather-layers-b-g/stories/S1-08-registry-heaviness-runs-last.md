# Story S1-08 — `@register_probe(heaviness=, runs_last=)` + coordinator sort-order edit

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Ready
**Effort:** M
**Depends on:** S1-05
**ADRs honored:** 02-ADR-0003

## Context

`IndexHealthProbe` (B2) must run *after* every sibling that produces a freshness signal, and `RuntimeTraceProbe` / `ScipIndexProbe` (heavy) should *start first* under the single `Semaphore(min(cpu_count(), 8))` so total wall-clock minimizes. The architect's choice (02-ADR-0003) is *not* to edit the `Probe` ABC (`localv2.md §4` is frozen) but to ride scheduling concerns on the registry decorator: `@register_probe(heaviness="heavy", runs_last=True)`. This story extends the registry and the coordinator's sort logic without touching the ABC.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #1 — IndexHealthProbe` — `runs_last=True` is the load-bearing annotation on B2.
  - `../phase-arch-design.md §"Logical view"` + `§"Process view"` — coordinator reads `heaviness` from the registry; heavy first; `runs_last` reserved for the tail.
  - `../phase-arch-design.md §"Design patterns applied"` row 4 — registry + decorator-data over ABC fields; refuses `cost_tier: Literal[0..3]` on the ABC.
  - `../phase-arch-design.md §"Tradeoffs (consolidated)"` row "Registry annotations instead of ABC fields" — preserves contract freeze.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0003-coordinator-heaviness-sort-annotation.md` — 02-ADR-0003 — the decision and its consequences; `Probe` ABC is **not** edited.
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0007-probe-contract-freeze.md` (Phase 0 ADR-0007) — the Phase 0 contract-freeze snapshot test continues to pass.
- **Source design:**
  - `../final-design.md §13 — Registry annotations instead of ABC fields` — the deliberate scope.
- **Existing code:**
  - `src/codegenie/probes/registry.py` — Phase 0/1 `Registry` class; `register_probe` is currently a bare decorator (no kwargs). Extend in place.
  - `src/codegenie/coordinator/coordinator.py` — Phase 0/1 dispatch path; the sort-order edit lives here.
  - `src/codegenie/probes/base.py` — **NOT touched** (Phase 0 contract freeze).
- **External docs (only if directly relevant):**
  - None.

## Goal

Extend `src/codegenie/probes/registry.py` to accept `@register_probe(heaviness: Literal["light","medium","heavy"]="light", runs_last: bool=False)`, store both kwargs alongside each registered probe class, expose `Registry.sorted_for_dispatch() -> tuple[ProbeRegEntry, ...]` returning heavy → medium → light → `runs_last=True` order; extend `src/codegenie/coordinator/coordinator.py` to read that order under the existing single `Semaphore(min(cpu_count(), 8))`. The `Probe` ABC is **not** edited.

## Acceptance criteria

- [ ] **AC-1.** `register_probe` is now a decorator-factory: `register_probe(*, heaviness: Literal["light","medium","heavy"]="light", runs_last: bool=False) -> Callable[[type[Probe]], type[Probe]]`. The old positional call site `@register_probe` (no parens) still works — backward-compatible with Phase 0/1 probes (defaults `heaviness="light"`, `runs_last=False`). The dual-shape decorator pattern is the canonical approach (handle both `register_probe(cls)` and `register_probe(...)(cls)`).
- [ ] **AC-2.** `Registry.register` accepts `(cls, *, heaviness, runs_last)` and stores a `ProbeRegEntry(cls, heaviness, runs_last)` (frozen dataclass). Existing duplicate-name detection is preserved.
- [ ] **AC-3.** `Registry.sorted_for_dispatch() -> tuple[ProbeRegEntry, ...]` returns:
  - First: every entry with `runs_last=False`, ordered `heavy` → `medium` → `light`, ties broken by registration order (stable).
  - Last: every entry with `runs_last=True`, ordered `heavy` → `medium` → `light`, ties broken by registration order.
  Result: a `runs_last=True` light probe still runs after a `runs_last=False` heavy probe — `runs_last` dominates `heaviness`.
- [ ] **AC-4.** A synthetic mixed registry test (light+light, medium+medium, heavy+heavy, runs_last=True light, runs_last=True heavy) dispatches in the asserted exact order. Parametrized.
- [ ] **AC-5.** `Registry.for_task(...)` (Phase 0 method) preserves filter semantics; `sorted_for_dispatch` is layered on top — `Registry.sorted_for_task(task, languages) -> tuple[ProbeRegEntry, ...]` combines both.
- [ ] **AC-6.** `src/codegenie/coordinator/coordinator.py` reads `sorted_for_task` (or the equivalent integration point) and dispatches under the **existing** single `Semaphore(min(cpu_count(), 8))`. No per-tier semaphores. No `pytest-xdist`. (02-ADR-0009 + ADR-0003 §Consequences.)
- [ ] **AC-7.** The Phase 0 contract-freeze snapshot test (`tests/unit/test_probe_contract.py`) stays green — `Probe` ABC unchanged (`base.py` not edited in this story).
- [ ] **AC-8.** Phase 0/1 existing probes (`LanguageDetectionProbe`, `NodeBuildSystemProbe`, parsers, etc.) continue to register without per-probe edits; their default `heaviness="light"`, `runs_last=False`.
- [ ] **AC-9.** A unit test asserts dispatch order under a coordinator-like environment: synthetic probes record a timestamp on entry; the order observed matches `sorted_for_dispatch`'s declared order (modulo the semaphore-induced parallelism for ties).
- [ ] **AC-10.** Structured log emission: every dispatch logs `coordinator.dispatch.order` with the list of probe names in order — verified by structlog capture in one test.
- [ ] **AC-11.** The TDD plan's red test exists, was committed, and is green.
- [ ] **AC-12.** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/probes/` + `tests/unit/coordinator/` all pass on the touched files.

## Implementation outline

1. In `src/codegenie/probes/registry.py`:
   - Add `ProbeRegEntry` frozen dataclass: `cls: type[Probe]`, `heaviness: Literal["light","medium","heavy"]`, `runs_last: bool`.
   - Change `Registry._probes` from `list[type[Probe]]` to `list[ProbeRegEntry]`. Maintain `all_probes()` for back-compat returning `tuple[type[Probe], ...]` (Phase 0/1 callers use this).
   - Add `Registry.sorted_for_dispatch()` and `Registry.sorted_for_task()`.
   - Rewrite `register_probe` as a dual-shape decorator: if the first arg is a `type` (Phase 0/1 style), treat as `@register_probe` (no parens); else treat as `@register_probe(...)`.
2. In `src/codegenie/coordinator/coordinator.py`:
   - Replace the Phase 0/1 dispatch iteration with `sorted_for_task` results.
   - Preserve the `Semaphore(min(cpu_count(), 8))` (one semaphore; do not split into per-tier).
   - Emit `coordinator.dispatch.order` log event.
3. Red tests → impl → refactor.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/probes/test_registry_heaviness.py`

```python
from __future__ import annotations

import pytest

from codegenie.probes.base import Probe
from codegenie.probes.registry import (
    ProbeRegEntry,
    Registry,
    register_probe,
)


def _make_probe(name_: str) -> type[Probe]:
    class _P(Probe):
        name = name_
        layer = "B"
        tier = "base"
        applies_to_tasks = ["*"]
        applies_to_languages = ["*"]
        requires: list[str] = []
        declared_inputs: list[str] = []
        async def run(self, repo, ctx):  # type: ignore[no-untyped-def]
            raise NotImplementedError
    _P.__name__ = name_
    return _P


def test_sorted_dispatch_order_heavy_then_medium_then_light_then_runs_last() -> None:
    reg = Registry()
    a_light = reg.register(_make_probe("a_light"))
    b_medium = reg.register(_make_probe("b_medium"), heaviness="medium")
    c_heavy = reg.register(_make_probe("c_heavy"), heaviness="heavy")
    d_runs_last_light = reg.register(_make_probe("d_index_health"), runs_last=True)
    e_runs_last_heavy = reg.register(_make_probe("e_runs_last_heavy"), heaviness="heavy", runs_last=True)
    f_light = reg.register(_make_probe("f_light"))

    order = [e.cls.name for e in reg.sorted_for_dispatch()]
    # Non-runs_last first: heavy → medium → light; ties by registration order.
    # Runs_last last: heavy → medium → light.
    assert order == [
        "c_heavy",
        "b_medium",
        "a_light", "f_light",
        "e_runs_last_heavy",
        "d_index_health",
    ]


def test_default_heaviness_is_light_and_runs_last_false() -> None:
    reg = Registry()
    reg.register(_make_probe("x"))
    entries = reg.sorted_for_dispatch()
    assert len(entries) == 1
    assert entries[0].heaviness == "light"
    assert entries[0].runs_last is False


def test_decorator_factory_shape() -> None:
    reg = Registry()

    @reg.decorator(heaviness="heavy", runs_last=True)
    class P1(Probe):
        name = "p1"; layer = "B"; tier = "base"
        applies_to_tasks = ["*"]; applies_to_languages = ["*"]
        requires: list[str] = []; declared_inputs: list[str] = []
        async def run(self, repo, ctx): ...  # type: ignore[no-untyped-def]

    entries = reg.sorted_for_dispatch()
    assert entries[0].cls is P1
    assert entries[0].heaviness == "heavy"
    assert entries[0].runs_last is True


def test_module_level_decorator_backward_compatible_no_parens() -> None:
    """A Phase 0/1 probe decorated with bare @register_probe (no parens) still
    registers with default heaviness="light", runs_last=False."""
    # default_registry is the singleton; use unregister_for_tests hook (add to
    # Registry mirroring S1-02) or use a fresh sub-registry. Pick whichever
    # pattern the Phase 0/1 tests already use; here, assume a fresh registry.
    reg = Registry()
    cls = _make_probe("legacy_phase0_probe")
    # The Phase 0 module-level decorator pattern: @register_probe applied to cls.
    # Simulate by calling the dual-shape decorator with the class positionally.
    returned = register_probe(cls)  # treats first positional arg as the class
    assert returned is cls


def test_iter_order_is_stable_within_tier() -> None:
    """Ties are broken by registration order — load-bearing for cache key
    sensitivity and golden-file stability."""
    reg = Registry()
    for n in ["x1", "x2", "x3"]:
        reg.register(_make_probe(n))
    order = [e.cls.name for e in reg.sorted_for_dispatch()]
    assert order == ["x1", "x2", "x3"]


def test_phase_0_ABC_unchanged() -> None:
    """02-ADR-0003 §Decision — `Probe` ABC is not edited. Spot-check that
    `heaviness` and `runs_last` are NOT attributes on the ABC class."""
    assert not hasattr(Probe, "heaviness")
    assert not hasattr(Probe, "runs_last")
```

Test file path: `tests/unit/coordinator/test_coordinator_sort_order.py`

```python
from __future__ import annotations
# Synthetic registry of light + medium + heavy + runs_last probes; the
# coordinator dispatches in the asserted order under
# Semaphore(min(cpu_count(), 8)). Mirror the integration shape of
# coordinator.gather; mock the cache to force-MISS so every probe runs.
# Capture entry timestamps from each probe's run(); assert ordering survives
# the semaphore.
# [Full test sketch deferred — implementer composes from existing
# tests/unit/coordinator/test_*.py shape.]

def test_runs_last_dispatched_after_every_sibling() -> None:
    # arrange: 5 probes; one is runs_last=True with heaviness="light"; others
    # are mixed heaviness=False runs_last.
    # act: gather()
    # assert: last entry to record its dispatch timestamp is the runs_last
    # probe, even though it's "light".
    ...
```

Run — confirm `ImportError`/`TypeError` on the new decorator-factory signature. Commit.

### Green — make it pass

In `src/codegenie/probes/registry.py`:

```python
from __future__ import annotations
import functools
from dataclasses import dataclass
from typing import Callable, Literal, Union, overload

from codegenie.errors import ProbeError
from codegenie.probes.base import Probe

__all__ = [
    "ProbeRegEntry", "Registry", "default_registry", "register_probe",
]

Heaviness = Literal["light", "medium", "heavy"]
_HEAVINESS_RANK: dict[Heaviness, int] = {"heavy": 0, "medium": 1, "light": 2}


@dataclass(frozen=True)
class ProbeRegEntry:
    cls: type[Probe]
    heaviness: Heaviness
    runs_last: bool
    registration_index: int  # tie-breaker for stable sort


class Registry:
    def __init__(self) -> None:
        self._entries: list[ProbeRegEntry] = []
        self._counter: int = 0

    def register(
        self,
        cls: type[Probe],
        *,
        heaviness: Heaviness = "light",
        runs_last: bool = False,
    ) -> type[Probe]:
        for e in self._entries:
            if e.cls.name == cls.name:
                raise ProbeError(
                    f"duplicate probe name {cls.name!r}: "
                    f"{e.cls.__module__}.{e.cls.__qualname__} and "
                    f"{cls.__module__}.{cls.__qualname__}"
                )
        self._entries.append(ProbeRegEntry(cls, heaviness, runs_last, self._counter))
        self._counter += 1
        return cls

    def decorator(
        self,
        *,
        heaviness: Heaviness = "light",
        runs_last: bool = False,
    ) -> Callable[[type[Probe]], type[Probe]]:
        def _wrap(cls: type[Probe]) -> type[Probe]:
            return self.register(cls, heaviness=heaviness, runs_last=runs_last)
        return _wrap

    def sorted_for_dispatch(self) -> tuple[ProbeRegEntry, ...]:
        non_last = sorted(
            (e for e in self._entries if not e.runs_last),
            key=lambda e: (_HEAVINESS_RANK[e.heaviness], e.registration_index),
        )
        last = sorted(
            (e for e in self._entries if e.runs_last),
            key=lambda e: (_HEAVINESS_RANK[e.heaviness], e.registration_index),
        )
        return tuple(non_last + last)

    def sorted_for_task(self, task: str, languages: frozenset[str]) -> tuple[ProbeRegEntry, ...]:
        # Filter then sort. Preserve Phase 0 _filter semantics.
        ...  # adapt from existing for_task implementation

    def all_probes(self) -> tuple[type[Probe], ...]:
        return tuple(e.cls for e in self._entries)

    def for_task(self, task: str, languages: frozenset[str]) -> tuple[type[Probe], ...]:
        # Phase 0/1 callers — unchanged signature
        return tuple(e.cls for e in self.sorted_for_task(task, languages))


default_registry = Registry()


# Dual-shape decorator: @register_probe (Phase 0/1, no parens) AND
# @register_probe(heaviness="heavy", runs_last=True) (Phase 2).
@overload
def register_probe(cls: type[Probe], /) -> type[Probe]: ...
@overload
def register_probe(*, heaviness: Heaviness = "light", runs_last: bool = False) -> Callable[[type[Probe]], type[Probe]]: ...
def register_probe(
    cls: type[Probe] | None = None,
    *,
    heaviness: Heaviness = "light",
    runs_last: bool = False,
) -> Union[type[Probe], Callable[[type[Probe]], type[Probe]]]:
    if cls is not None:
        # @register_probe  (no parens; Phase 0/1)
        return default_registry.register(cls)
    # @register_probe(heaviness=..., runs_last=...)  (Phase 2)
    return default_registry.decorator(heaviness=heaviness, runs_last=runs_last)
```

In `src/codegenie/coordinator/coordinator.py`:

- Locate the existing dispatch path (gather function).
- Replace the existing `registry.for_task(...)` iteration with `registry.sorted_for_task(...)` (or equivalent) so entries arrive in heaviness/runs-last order. Preserve the single `Semaphore(min(cpu_count(), 8))`.
- Emit `coordinator.dispatch.order` structlog event with the ordered list of probe names.

### Refactor — clean up

- Module docstring on `registry.py`: name 02-ADR-0003 (decorator-data, not ABC fields) and the runs_last invariant (`IndexHealthProbe` is the canonical user).
- The legacy `@register_probe` (no parens) backward-compat must be tested. Phase 0/1 probes are not edited.
- `Probe` ABC remains unchanged (`base.py` is not in this story's "Files to touch").
- Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/probes/registry.py src/codegenie/coordinator/coordinator.py tests/unit/probes/test_registry_heaviness.py tests/unit/coordinator/test_coordinator_sort_order.py`, `pytest tests/unit/probes/ tests/unit/coordinator/ -v`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/registry.py` | Add `ProbeRegEntry`, `sorted_for_dispatch`, `sorted_for_task`, dual-shape `register_probe` decorator. |
| `src/codegenie/coordinator/coordinator.py` | Dispatch reads `sorted_for_task` order; preserve single `Semaphore`; emit `coordinator.dispatch.order` log. |
| `tests/unit/probes/test_registry_heaviness.py` | Heaviness/runs_last ordering, decorator factory, backward-compat, ABC-unchanged. |
| `tests/unit/coordinator/test_coordinator_sort_order.py` | Coordinator honors registry order under single semaphore. |

## Out of scope

- **`Probe` ABC edits** — explicitly forbidden by 02-ADR-0003 §Decision. Editing `src/codegenie/probes/base.py` here makes the Phase 0 contract-freeze snapshot test fail and breaks 02-ADR-0003's commitment.
- **Per-tier semaphores** — explicitly rejected by 02-ADR-0009 (`pytest-xdist` veto preserved) and architect's `cpu_count()=2` analysis (`../phase-arch-design.md §"Gap 2"`). Single `Semaphore(min(cpu_count(), 8))` only.
- **`pytest-xdist` reversal** — 02-ADR-0009.
- **`ProbeContext.image_digest_resolver`** — handled by S1-09 (the next story); this story does not edit `base.py`.
- **`IndexHealthProbe` itself** — S4-01; this story only ensures the registry has the `runs_last` annotation slot it will use.
- **Probe scheduling with `requires:` topological ordering** — Phase 0/1 already implements `requires`; this story does not change that. `runs_last` is a *layer* over `requires`; topo sort first, then within-batch heaviness sort.

## Notes for the implementer

- **Dual-shape decorator is the canonical idiom.** The `cls=None` + overload pattern is in Python textbooks; ensure mypy is happy by using `@overload` properly. Test backward-compat explicitly — Phase 0/1 probes use `@register_probe` with no parens and must continue to work.
- **`Probe` ABC is not edited.** The Phase 0 contract-freeze snapshot test (`tests/unit/test_probe_contract.py`) is the structural defense. If that test fails after this story, the change is wrong — back out and route via the registry annotation instead.
- **Stable sort is load-bearing.** Cache keys and golden files depend on deterministic dispatch order; ties between probes of the same heaviness/runs_last MUST be broken by registration order (the `registration_index` field). `sorted()` in Python is stable; using the rank-tuple key preserves the registration-index tie-break.
- **`runs_last` dominates `heaviness`.** A `runs_last=True heaviness="light"` probe still runs after a `runs_last=False heaviness="heavy"` probe. The architect's intent is: `runs_last` means *truly last*, not "last within its heaviness tier."
- **Coordinator integration is surgical.** The existing `coordinator.gather` already iterates registered probes; the change is *which iteration order it reads*. Do not rewrite the dispatch loop, the semaphore, or the cache lookup. The synthesis explicitly says "~15 LOC sort-order edit to Phase 0 coordinator" (`../phase-arch-design.md §"Tradeoffs (consolidated)"` row 2).
- **`requires:` interactions.** Phase 0's coordinator runs `requires` as topological ordering (each probe waits for its dependencies' slices). `runs_last=True` is *separate* — it's an entire-batch postponement, not a dependency. If `IndexHealthProbe` has `requires=[]` (the architect's spec — B2 reads sibling slices "via the coordinator-provided slice map, not via topological ordering") then `runs_last=True` is what enforces the after-everyone-else ordering. Verify: this story's tests use `requires=[]` and rely on `runs_last` alone for ordering — the integration with topo-sort `requires` is tested in S4-01.
- **Default heaviness "light" is the right default.** Most Phase 0/1 probes are I/O-light marker probes; the architect's heaviness assignment table reserves "heavy" for `SCIPIndexProbe` and `RuntimeTraceProbe` only.
- **`coordinator.dispatch.order` log field.** This is the audit-anchor diagnostic for "why did probes run in that order?" — verifiable by a Phase 0 audit-anchor reviewer without re-running.
