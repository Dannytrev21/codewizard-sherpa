# Story S1-05 — `Projection` Protocol + `@register_projection`

**Step:** Step 1 — Domain primitives, typed event contracts, and structural fences
**Status:** Ready
**Effort:** S
**Depends on:** S1-03 (registry shape mirrored), S1-04 (registry kernel parity established)
**ADRs honored:** production ADR-0043 (additive — every new projection is one module + one import line), production ADR-0034 (canonical event log → projection is the read path)

## Context
Step 7 ships three Phase-9 projections (`audit_trail`, `retry_histogram`, `plugin_telemetry`) as pure folds over the canonical event log; Phase 11 (KG writeback) and Phase 13 (cost ledger) land additively as new projection modules. The shape consumers see is one Protocol (`Projection`) and one registry (`@register_projection`). The arch is explicit: **pure folds, no Postgres needed for unit tests** — the `Projection` Protocol takes a `Sequence[EventPayload]` and returns a `ProjectionState`; no IO. Registry-collision-at-import raises `TypeError` so a Phase-10 contributor naming a new projection `audit_trail` finds out before merge.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C10 — Projections` — `Projection` Protocol shape; `register_projection` collection point; "zero stubs" (ADR-0043) discipline
  - `../phase-arch-design.md §Class diagram §Projection` — the Protocol box
  - `../phase-arch-design.md §Component design — module tree §events/projections/__init__.py (@register_projection)`
- **Phase ADRs:**
  - `../ADRs/0002-phase-8-plugin-events-log-cutover-to-canonical-event-log.md` — Phase-8's `codegenie.plugins.events` is the projection role being absorbed; the cutover commits to "every Phase-8 read site moves to a projection"
- **Production ADRs:**
  - `../../../production/adrs/0034-event-sourcing-canonical-primitive.md` — canonical log + projections is the mandated pattern
  - `../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md` — zero stubs; new projections land as new modules
- **Source design:**
  - `../final-design.md §Synthesis ledger — projection protocol row`
- **Existing code:**
  - `src/codegenie/probes/registry.py` — the collision-raises pattern this story mirrors
  - `src/codegenie/events/payloads.py` (landed by S1-02) — `EventPayload` is the input to `fold`
  - `src/codegenie/types/identifiers.py` — `ProjectionId` (landed by S1-01)

## Goal
Land `src/codegenie/events/projections/__init__.py` with the `Projection` `runtime_checkable` Protocol + `@register_projection` decorator + module-level `_PROJECTIONS: dict[ProjectionId, type[Projection]]`; collision raises `TypeError` at import.

## Acceptance criteria
- [ ] `src/codegenie/events/projections/__init__.py` defines `Projection(Protocol)` with class attribute `name: ProjectionId` and instance method `fold(self, events: Sequence[EventPayload]) -> ProjectionState`.
- [ ] `Projection` is decorated `@runtime_checkable` so `isinstance(x, Projection)` succeeds at runtime for any class declaring the right shape.
- [ ] `ProjectionState` is a `TypeAlias = Mapping[str, Any]` (or a richer typed alias documented in the docstring) — keep narrow; concrete projections in Step 7 may return frozen Pydantic models, all of which structurally satisfy `Mapping[str, Any]` via `.model_dump()`.
- [ ] `register_projection(name: ProjectionId)` is a decorator factory; applying it to a class adds `(name, cls)` to `_PROJECTIONS` and returns the class unchanged.
- [ ] Registering two classes under the same `name` raises `TypeError(f"register_projection name collision: {name}")` at the second decoration.
- [ ] `_PROJECTIONS` is module-level mutable during import; treat it as the public registry (do not freeze — projections register lazily as their modules are explicitly imported).
- [ ] `tests/unit/events/projections/test_register_projection.py` covers: (a) happy-path registration; (b) `runtime_checkable` succeeds for a conforming class and fails for a non-conforming one; (c) collision raises `TypeError`; (d) decorator is identity (class unchanged).
- [ ] `mypy --strict src/codegenie/events/projections/__init__.py` is clean.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on touched files.

## Implementation outline
1. Create `src/codegenie/events/projections/__init__.py`:
   - Module docstring citing ADR-0034 + ADR-0043 + naming `@register_probe` as the precedent.
   - `from typing import Protocol, runtime_checkable, TypeAlias`; `from collections.abc import Mapping, Sequence`.
   - `ProjectionState: TypeAlias = Mapping[str, Any]`.
   - `@runtime_checkable class Projection(Protocol)` with `name: ProjectionId` and `fold(...)`.
   - `_PROJECTIONS: dict[ProjectionId, type[Projection]] = {}`.
   - `register_projection(name: ProjectionId)` decorator factory; raises on collision.
   - `__all__ = ["Projection", "ProjectionState", "register_projection", "_PROJECTIONS"]`.
2. Land the unit tests + the runtime-checkable contract test.
3. `mypy --strict`; iterate until clean.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/events/projections/test_register_projection.py`
```python
from collections.abc import Sequence
import pytest
from codegenie.types.identifiers import ProjectionId

def test_register_projection_populates_registry():
    from codegenie.events.payloads import EventPayload
    from codegenie.events.projections import (
        register_projection, _PROJECTIONS, Projection, ProjectionState,
    )

    @register_projection(ProjectionId("test_alpha_projection"))
    class AlphaProjection:
        name: ProjectionId = ProjectionId("test_alpha_projection")
        def fold(self, events: Sequence[EventPayload]) -> ProjectionState:
            return {"count": len(events)}

    assert ProjectionId("test_alpha_projection") in _PROJECTIONS
    assert _PROJECTIONS[ProjectionId("test_alpha_projection")] is AlphaProjection
    assert isinstance(AlphaProjection(), Projection)  # runtime_checkable

def test_register_projection_collision_raises():
    from codegenie.events.projections import register_projection

    @register_projection(ProjectionId("dup_name"))
    class P1:
        name: ProjectionId = ProjectionId("dup_name")
        def fold(self, events): return {}

    with pytest.raises(TypeError, match=r"collision: dup_name"):
        @register_projection(ProjectionId("dup_name"))
        class P2:
            name: ProjectionId = ProjectionId("dup_name")
            def fold(self, events): return {}

def test_protocol_runtime_check_rejects_nonconforming():
    from codegenie.events.projections import Projection
    class NotAProjection:
        pass
    assert not isinstance(NotAProjection(), Projection)

def test_decorator_is_identity():
    from codegenie.events.projections import register_projection
    class P:
        name: ProjectionId = ProjectionId("identity_p")
        def fold(self, events): return {}
    decorated = register_projection(ProjectionId("identity_p"))(P)
    assert decorated is P
```

### Green — make it pass
Module with `Protocol` + decorator factory + module-level dict. Collision check before insert; `TypeError` with the offending `ProjectionId`.

### Refactor — clean up
- `Projection` Protocol carries a `name: ProjectionId` *class* attribute (not `name: str`) — `runtime_checkable` checks attribute presence, not its declared type, but the docstring should call this out so Step 7 concrete projections declare it as `ClassVar[ProjectionId]` cleanly.
- Tests share `_PROJECTIONS` — provide a `clean_projection_registry` fixture (snapshot + restore) so Step 7 tests don't cross-pollute.
- Decorator docstring cites ADR-0034 + the Phase-7 expectation "zero stubs raising `NotImplementedError`".

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/events/projections/__init__.py` | `Projection` Protocol + `register_projection` + `_PROJECTIONS` |
| `tests/unit/events/__init__.py`, `tests/unit/events/projections/__init__.py` | Markers |
| `tests/unit/events/projections/test_register_projection.py` | Happy path + collision + runtime-check + identity |
| `tests/conftest.py` *(or local conftest)* | `clean_projection_registry` fixture |

## Out of scope
- **Concrete projections** (`audit_trail`, `retry_histogram`, `plugin_telemetry`) — Step 7 (S7-01, S7-02, S7-03).
- **Phase-8 `codegenie.plugins.events` cutover** — Phase 10's first commit (per ADR-0002).
- **Projection lag-alarm thresholds** — Phase 13.5 portal surfaces.
- **`fold` invocation infrastructure** — projections are pure functions in Phase 9; how/when they run is Step 7 + later phases.
- **A `last_processed_seq` cursor / streaming-fold variant** — Phase 13+ if needed; this story ships the simplest `Sequence` input.

## Notes for the implementer
- The Protocol's `name: ProjectionId` class attribute is the *identity* of the projection — duplicated names are the silent-bug surface this story's collision check is built to catch.
- `runtime_checkable` is the right shape because concrete projections in Step 7 (and Phase 11/13) are independent classes that should not need to `import Projection` — structural subtyping is the discipline. Verify with the `isinstance(AlphaProjection(), Projection)` assertion.
- Step 7's `audit_trail` projection will *also* emit `ChainTamperDetected` on a chain gap — meaning `fold` can have side effects on the canonical event log. The `Projection` Protocol's pure-function signature does **not** forbid this in Phase 9; document the convention in the docstring but do not encode it in the type.
- Do not introduce a `Projection` ABC instead of a Protocol — the codebase's structural-subtyping discipline (`@runtime_checkable Protocol`) is the canonical seam; ABCs invite ceremony.
- `ProjectionState: TypeAlias = Mapping[str, Any]` is the conservative typed alias; Step 7 will return concrete Pydantic models that `model_dump()` into the `Mapping`-shape; consumers (tests) can `isinstance(state, dict)`-check the dump.
- `_PROJECTIONS` is per-process module-level state; the `clean_projection_registry` fixture is the discipline that keeps Step 7 tests hermetic.
