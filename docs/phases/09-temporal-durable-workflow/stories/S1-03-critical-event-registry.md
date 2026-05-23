# Story S1-03 — `@critical_event` decorator + registry

**Step:** Step 1 — Domain primitives, typed event contracts, and structural fences
**Status:** Ready
**Effort:** S
**Depends on:** S1-01, S1-02
**ADRs honored:** ADR-0006 (`@critical_event` synchronous-flush vocabulary — exactly five members), production ADR-0043 (additive — future critical events land via decorator)

## Context
The `EventBatchWriter` (Step 3, S3-02) flushes on a 20 ms / 256-event boundary to hit the ≥3k events/sec G6 target. Five variants whose loss would compromise audit, safety, or cost claims (`MergeOutcome`, `BudgetExhausted`, `TrustGateFailed`, `WorkflowTerminated`, `ChainTamperDetected`) must take the synchronous-flush path. ADR-0006 records this as a decorator-populated registry — same shape as `@register_probe` from Phase 0 — so future phases extend the set additively without editing the writer. The vocabulary is the contract; a golden-set fence (asserts the set is *exactly* those five names) forces a code-review conversation any time the set changes.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C5 — Canonical event log` — `critical_event(cls) -> cls` shape; `EventBatchWriter.append` checks `type(event).__name__ in _CRITICAL_EVENTS`
  - `../phase-arch-design.md §Design patterns applied #8 — Open/Closed via decorator` — registry pattern parity with `@register_probe`
  - `../phase-arch-design.md §Concurrency, blocking, durable checkpoints` — names the five sync-flush variants explicitly
- **Phase ADRs:**
  - `../ADRs/0006-critical-event-synchronous-flush-vocabulary.md` — Consequences §`tests/fence/test_critical_event_vocabulary.py` asserts the set is exactly `{"MergeOutcome","BudgetExhausted","TrustGateFailed","WorkflowTerminated","ChainTamperDetected"}`
- **Production ADRs:**
  - `../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md` — future critical events are additive decorator lines, never edits to the writer
- **Source design:**
  - `../final-design.md §Synthesis ledger — synchronous-flush vocabulary row`
- **Existing code:**
  - `src/codegenie/probes/registry.py` — precedent for the decorator-populated module-level registry shape (idempotent at import; collision raises at registration)
  - `src/codegenie/events/payloads.py` (landed by S1-02) — the five variants the decorator will be applied to

## Goal
Land the `@critical_event` decorator + the module-level `_CRITICAL_EVENTS: Final[frozenset[str]]` registry inside `codegenie.events.payloads`, apply it to exactly the five named variants, and ship a vocabulary-fence test that pins the set to the golden five.

## Acceptance criteria
- [ ] `codegenie.events.payloads.critical_event(cls)` decorator exists, returns `cls` unchanged, and adds `cls.__name__` to a module-level mutable `_CRITICAL_EVENTS_BUILDER: set[str]` at import time; the public symbol is `_CRITICAL_EVENTS: Final[frozenset[str]] = frozenset(_CRITICAL_EVENTS_BUILDER)` (frozen after the module finishes importing).
- [ ] `@critical_event` is applied to and *only to* `MergeOutcome`, `BudgetExhausted`, `TrustGateFailed`, `WorkflowTerminated`, `ChainTamperDetected` in `codegenie.events.payloads`.
- [ ] `tests/fence/test_critical_event_vocabulary.py` asserts `_CRITICAL_EVENTS == frozenset({"MergeOutcome","BudgetExhausted","TrustGateFailed","WorkflowTerminated","ChainTamperDetected"})` and exits with a clear error message if any name is missing or extra.
- [ ] `tests/events/test_critical_event_registry.py` decorates a throwaway `BaseModel` subclass twice and asserts the second application raises `TypeError("critical_event already registered: <name>")` (collision-at-import discipline; mirrors `@register_probe`).
- [ ] `_CRITICAL_EVENTS` is *not* mutable after module import; a test attempts `_CRITICAL_EVENTS.add("X")` and expects `AttributeError` (because it's a `frozenset`).
- [ ] `mypy --strict` is clean: the decorator is typed as `Callable[[type[T]], type[T]]`.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on touched files.

## Implementation outline
1. Open `src/codegenie/events/payloads.py` (from S1-02).
2. Add near the top: `_CRITICAL_EVENTS_BUILDER: set[str] = set()` (module-private; mutable during import only).
3. Define the decorator:
   ```python
   def critical_event(cls: type[_BaseT]) -> type[_BaseT]:
       if cls.__name__ in _CRITICAL_EVENTS_BUILDER:
           raise TypeError(f"critical_event already registered: {cls.__name__}")
       _CRITICAL_EVENTS_BUILDER.add(cls.__name__)
       return cls
   ```
4. Apply `@critical_event` above exactly the five class declarations.
5. At the bottom of the module: `_CRITICAL_EVENTS: Final[frozenset[str]] = frozenset(_CRITICAL_EVENTS_BUILDER)`.
6. Add the vocabulary-fence test and the collision test.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/fence/test_critical_event_vocabulary.py`
```python
def test_critical_event_vocabulary_is_exactly_the_five_golden_names():
    from codegenie.events.payloads import _CRITICAL_EVENTS
    expected = frozenset({
        "MergeOutcome", "BudgetExhausted", "TrustGateFailed",
        "WorkflowTerminated", "ChainTamperDetected",
    })
    assert _CRITICAL_EVENTS == expected, (
        f"@critical_event drift detected.\n"
        f"  missing: {expected - _CRITICAL_EVENTS}\n"
        f"  extra:   {_CRITICAL_EVENTS - expected}\n"
        "Adding to this set requires an ADR amendment (see ADR-0006)."
    )

def test_critical_events_frozenset_is_immutable():
    from codegenie.events.payloads import _CRITICAL_EVENTS
    import pytest
    with pytest.raises(AttributeError):
        _CRITICAL_EVENTS.add("Sneaky")  # type: ignore[attr-defined]
```

Test file path: `tests/events/test_critical_event_registry.py`
```python
def test_double_registration_raises_typeerror():
    from pydantic import BaseModel, ConfigDict
    from codegenie.events.payloads import critical_event
    import pytest

    class _Fake(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")

    critical_event(_Fake)
    with pytest.raises(TypeError, match=r"already registered: _Fake"):
        critical_event(_Fake)

def test_decorator_returns_class_unchanged():
    from pydantic import BaseModel, ConfigDict
    from codegenie.events.payloads import critical_event

    class _AlsoFake(BaseModel):
        model_config = ConfigDict(frozen=True, extra="forbid")

    decorated = critical_event(_AlsoFake)
    assert decorated is _AlsoFake
```

### Green — make it pass
Add the builder set, the decorator function, the `@critical_event` lines above the five variant classes, and the `Final[frozenset]` snapshot at module tail.

### Refactor — clean up
- Decorator docstring cites ADR-0006 and notes "new critical events require updating both this decoration AND the golden set in `tests/fence/test_critical_event_vocabulary.py`".
- The decorator is `Callable[[type[T]], type[T]]` — generic so `mypy` preserves the class type post-decoration.
- The collision-raise message points at the exact `cls.__name__`; do not swallow it.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/events/payloads.py` | Add decorator + `_CRITICAL_EVENTS` snapshot; decorate five variants |
| `tests/fence/__init__.py` | Marker (if absent) |
| `tests/fence/test_critical_event_vocabulary.py` | Golden-set fence |
| `tests/events/test_critical_event_registry.py` | Collision raises; decorator is identity |

## Out of scope
- **`EventBatchWriter` consumption of `_CRITICAL_EVENTS`** — Step 3 (S3-02, S3-03); the writer checks `type(event).__name__ in _CRITICAL_EVENTS` at append time.
- **Synchronous-flush semantics** — Step 3 (S3-03).
- **Adding new `@critical_event` variants in Phase 10+** — additive per ADR-0043, but out of scope here.

## Notes for the implementer
- The two-stage build (`_CRITICAL_EVENTS_BUILDER: set[str]` mutated during import, `_CRITICAL_EVENTS: Final[frozenset[str]]` exported) is the pattern that makes the registry write-only at import time and immutable after — same shape as `Final` constants elsewhere in `codegenie.types.identifiers`.
- The vocabulary fence is the *whole point* of ADR-0006 — if the test passes after a contributor silently drops `@critical_event` from `MergeOutcome`, the safety claim is gone. Make sure the test's failure message tells the next contributor what's missing AND what's extra.
- The decorator's collision-raise (`TypeError`) is the parity with `@register_probe`. Use `TypeError`, not `ValueError`, so the failure surface matches the rest of the codebase.
- Do **not** add a `@critical_event` to any variant other than the five named — adding a sixth requires an ADR-0006 amendment, not a story.
- `_CRITICAL_EVENTS_BUILDER` is a mutable module attribute during import; conventionally a single-underscore prefix signals "internal". Do not expose it via `__all__`.
- The `_CRITICAL_EVENTS: Final[frozenset[str]]` symbol is what Step 3's batcher will import; treat it as the stable public symbol (in the same module but consumed elsewhere).
