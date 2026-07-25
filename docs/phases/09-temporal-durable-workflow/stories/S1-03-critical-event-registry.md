# Story S1-03 — `@critical_event` decorator + registry

**Step:** Step 1 — Domain primitives, typed event contracts, and structural fences
**Status:** HARDENED
**Effort:** S
**Depends on:** S1-01 **GREEN**, S1-02 **GREEN** (the module `src/codegenie/events/payloads.py` and the `_Base` class + five variant classes must be on disk; HARDENED is not sufficient — this story edits that module and imports `_Base` as its TypeVar bound).
**ADRs honored:** ADR-0006 (`@critical_event` synchronous-flush vocabulary — exactly five members), production ADR-0043 (additive — future critical events land via decorator)

## Validation notes

Validated: 2026-07-25
Verdict: HARDENED
Findings addressed: 15 total — 4 blocks, 8 hardens, 3 nits
Full audit log: `_validation/S1-03-critical-event-registry.md`

Key changes:
- Depends-on tightened to S1-02 **GREEN** (imports `_Base`, `_ALL_VARIANT_CLASSES`, and the five variant classes on disk).
- Decorator is bounded: `TypeVar("_BaseT", bound="_Base")` — mis-application to a non-`_Base` subclass is a `mypy --strict` build break, not a runtime hope.
- Vocabulary fence extended to cross-check with S1-02's `_ALL_VARIANT_CLASSES` — catches drift where a variant is renamed/deleted but the decorator sticker lingers.
- `_CRITICAL_EVENTS_BUILDER` is `del`-ed at the module tail — the mutable staging attribute is physically unreachable after the frozenset snapshot, which pins the invariant "runtime `_CRITICAL_EVENTS` cannot diverge from the golden fence's frozen snapshot".
- Collision test rewrites use unique per-test class names (`_FakeCollisionA`, `_FakeCollisionB`) via `type()` to defeat test-order pollution of `_CRITICAL_EVENTS_BUILDER` when tests re-run in the same process.
- Notes-for-implementer corrected: `@register_probe` raises `ProbeError`, not `TypeError` — the parity claim was wrong. The correct framing is "same *shape* (decorator-populated module-level registry, collision-at-import), different exception type (`TypeError` here — usage-error semantic, no new domain exception class introduced)".

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
- [ ] AC-1: `codegenie.events.payloads.critical_event(cls)` decorator exists, returns `cls` unchanged, and adds `cls.__name__` to a module-level mutable `_CRITICAL_EVENTS_BUILDER: set[str]` at import time; the public symbol is `_CRITICAL_EVENTS: Final[frozenset[str]] = frozenset(_CRITICAL_EVENTS_BUILDER)` (frozen after the module finishes importing).
- [ ] AC-2: `@critical_event` is applied to and *only to* `MergeOutcome`, `BudgetExhausted`, `TrustGateFailed`, `WorkflowTerminated`, `ChainTamperDetected` in `codegenie.events.payloads`.
- [ ] AC-3: `tests/fence/test_critical_event_vocabulary.py` asserts `_CRITICAL_EVENTS == frozenset({"MergeOutcome","BudgetExhausted","TrustGateFailed","WorkflowTerminated","ChainTamperDetected"})` and exits with a clear error message that names both **missing** and **extra** entries independently. (validator: preserved from original — good mutation-resistance.)
- [ ] AC-4: `tests/events/test_critical_event_registry.py` decorates a throwaway `_Base` subclass twice (unique class name per test) and asserts the second application raises `TypeError("critical_event already registered: <name>")`. (validator: hardened — the class name must be unique per test and constructed via `type()` so the module-level `_CRITICAL_EVENTS_BUILDER` is not polluted across pytest runs in the same process; see Notes-for-implementer §"Test pollution".)
- [ ] AC-5: `_CRITICAL_EVENTS` is *not* mutable after module import; a test attempts `_CRITICAL_EVENTS.add("X")` and expects `AttributeError` (because it's a `frozenset`); a second test asserts `isinstance(_CRITICAL_EVENTS, frozenset)` — the annotation and runtime type must agree. (validator: hardened — the isinstance check catches a refactor that types the annotation `frozenset` but assigns a `set` literal.)
- [ ] AC-6: `mypy --strict` is clean: the decorator is typed as `Callable[[type[_BaseT]], type[_BaseT]]` where `_BaseT = TypeVar("_BaseT", bound="_Base")` (module-scoped TypeVar bound to the S1-02 `_Base` class). Applying `@critical_event` to a non-`_Base` subclass is a `mypy --strict` error, not a runtime hope. (validator: hardened — the type bound is the extension-by-addition guardrail; without it, a contributor decorating a random `BaseModel` in a distant module silently registers a name that never appears in the union.)
- [ ] AC-7: The vocabulary fence *cross-checks* against S1-02's `_ALL_VARIANT_CLASSES`: `_CRITICAL_EVENTS <= {cls.__name__ for cls in _ALL_VARIANT_CLASSES}` — every name in `_CRITICAL_EVENTS` must correspond to an actual variant in the discriminated union. Failure message names the orphan(s). (validator: added — catches drift where a variant is renamed or removed but the `@critical_event` sticker is left behind on a since-deleted class, or where the golden set names a class that never made it into S1-02's union.)
- [ ] AC-8: The module-level `_CRITICAL_EVENTS_BUILDER` attribute is `del`-ed at the module tail immediately after the frozenset snapshot is assigned; a test asserts `not hasattr(codegenie.events.payloads, "_CRITICAL_EVENTS_BUILDER")`. (validator: added — physically un-reachability of the mutable staging attribute post-freeze pins the "runtime `_CRITICAL_EVENTS` cannot diverge from the golden fence" invariant. A post-import `critical_event(...)` call raises `NameError` at the `_CRITICAL_EVENTS_BUILDER.add(...)` line — loud failure, not a silent divergence.)
- [ ] AC-9: `_CRITICAL_EVENTS_BUILDER` is not exported: neither `_CRITICAL_EVENTS_BUILDER` nor `critical_event`-related transient state appears in `codegenie.events.payloads.__all__`. `_CRITICAL_EVENTS` and `critical_event` **are** exported. (validator: added — the module boundary makes the frozen snapshot the only public surface.)
- [ ] AC-10: The TDD plan's red tests exist, were committed as failing first, and are now green.
- [ ] AC-11: `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on touched files.

## Implementation outline
1. Open `src/codegenie/events/payloads.py` (from S1-02 GREEN).
2. Add near the top (immediately after `_Base` is defined so the TypeVar bound resolves): a module-scoped `TypeVar` and the mutable staging set:
   ```python
   _BaseT = TypeVar("_BaseT", bound=_Base)  # bound after _Base is defined; forward-ref not required
   _CRITICAL_EVENTS_BUILDER: set[str] = set()  # module-private; mutable during import only
   ```
3. Define the decorator immediately below the TypeVar:
   ```python
   def critical_event(cls: type[_BaseT]) -> type[_BaseT]:
       """Mark a Pydantic event variant as synchronous-flush at append time.

       Populates the module-level ``_CRITICAL_EVENTS_BUILDER`` at import time;
       the frozen ``_CRITICAL_EVENTS`` snapshot at the module tail is what
       ``EventBatchWriter.append`` reads (S3-02). Adding a new critical event
       is a decorator line here + a golden-set update in
       ``tests/fence/test_critical_event_vocabulary.py`` — no edits to the
       writer (ADR-0006 §Consequences; production ADR-0043).

       Raises ``TypeError`` at import time if the same class is decorated twice
       (usage-error semantic — no domain exception class introduced).
       """
       if cls.__name__ in _CRITICAL_EVENTS_BUILDER:
           raise TypeError(f"critical_event already registered: {cls.__name__}")
       _CRITICAL_EVENTS_BUILDER.add(cls.__name__)
       return cls
   ```
4. Apply `@critical_event` above exactly the five class declarations (`MergeOutcome`, `BudgetExhausted`, `TrustGateFailed`, `WorkflowTerminated`, `ChainTamperDetected`).
5. At the bottom of the module — after the last variant definition, after `_ALL_VARIANT_CLASSES` from S1-02, and immediately before `__all__` — snapshot and delete:
   ```python
   _CRITICAL_EVENTS: Final[frozenset[str]] = frozenset(_CRITICAL_EVENTS_BUILDER)
   del _CRITICAL_EVENTS_BUILDER  # AC-8: physically unreachable post-freeze
   ```
6. Extend `__all__` with `"critical_event"` and `"_CRITICAL_EVENTS"`. Do NOT include `_CRITICAL_EVENTS_BUILDER` (it no longer exists at module tail anyway).
7. Add the vocabulary-fence test (`tests/fence/test_critical_event_vocabulary.py`) with the three assertions (golden set equality, orphan cross-check with `_ALL_VARIANT_CLASSES`, `isinstance(_CRITICAL_EVENTS, frozenset)`) and the collision + return-identity tests (`tests/events/test_critical_event_registry.py`).

## TDD plan — red / green / refactor
### Red — write the failing test first

Test file path: `tests/fence/test_critical_event_vocabulary.py`
```python
def test_critical_event_vocabulary_is_exactly_the_five_golden_names() -> None:
    # AC-3: golden-set equality with an error message that names both
    # missing and extra entries independently — mutation-resistant to a
    # contributor silently dropping a decorator sticker.
    from codegenie.events.payloads import _CRITICAL_EVENTS
    expected = frozenset({
        "MergeOutcome", "BudgetExhausted", "TrustGateFailed",
        "WorkflowTerminated", "ChainTamperDetected",
    })
    assert _CRITICAL_EVENTS == expected, (
        f"@critical_event drift detected.\n"
        f"  missing (in golden, not on module): {expected - _CRITICAL_EVENTS}\n"
        f"  extra   (on module, not in golden): {_CRITICAL_EVENTS - expected}\n"
        "Adding to or removing from this set requires an ADR-0006 "
        "amendment AND updating this golden."
    )

def test_critical_events_are_all_actual_union_variants() -> None:
    # AC-7: cross-check with S1-02's _ALL_VARIANT_CLASSES — every name in
    # _CRITICAL_EVENTS must correspond to a real variant in EventPayload.
    # Catches renamed / deleted variants whose @critical_event sticker was
    # left behind on a non-existent class, and any golden entry that never
    # made it into S1-02's union.
    from codegenie.events.payloads import _ALL_VARIANT_CLASSES, _CRITICAL_EVENTS
    variant_names = {cls.__name__ for cls in _ALL_VARIANT_CLASSES}
    orphans = _CRITICAL_EVENTS - variant_names
    assert not orphans, (
        f"@critical_event registered for classes that are not in the "
        f"EventPayload discriminated union: {orphans}. "
        f"Either the class was renamed/deleted (remove the decorator) "
        f"or the class was never added to _ALL_VARIANT_CLASSES."
    )

def test_critical_events_is_actually_a_frozenset() -> None:
    # AC-5: annotation and runtime type must agree — catches a refactor
    # that types the annotation frozenset[str] but assigns a set literal.
    from codegenie.events.payloads import _CRITICAL_EVENTS
    assert isinstance(_CRITICAL_EVENTS, frozenset)

def test_critical_events_frozenset_is_immutable() -> None:
    # AC-5: frozenset has no .add — a defensive test to keep the
    # immutability property observable and grep-able.
    from codegenie.events.payloads import _CRITICAL_EVENTS
    import pytest
    with pytest.raises(AttributeError):
        _CRITICAL_EVENTS.add("Sneaky")  # type: ignore[attr-defined]

def test_builder_is_gone_after_module_import() -> None:
    # AC-8: the mutable staging attribute is del-ed at module tail.
    # Post-import mutation is a NameError, not a silent divergence.
    import codegenie.events.payloads as payloads
    assert not hasattr(payloads, "_CRITICAL_EVENTS_BUILDER")

def test_public_surface_names_the_frozen_set_and_decorator_only() -> None:
    # AC-9: __all__ exposes the frozen snapshot and the decorator; the
    # transient builder is not exported (and no longer exists anyway).
    from codegenie.events.payloads import __all__
    assert "critical_event" in __all__
    assert "_CRITICAL_EVENTS" in __all__
    assert "_CRITICAL_EVENTS_BUILDER" not in __all__
```

Test file path: `tests/events/test_critical_event_registry.py`
```python
def test_double_registration_raises_typeerror() -> None:
    # AC-4: collision-at-import discipline. Use type() with a unique
    # per-test name so re-running the test in the same process is
    # deterministic — the module-level _CRITICAL_EVENTS_BUILDER is del-ed
    # at import so this only mutates the local closure; but even without
    # that, using a fresh class per test keeps the failure mode local.
    from codegenie.events.payloads import _Base, critical_event
    import pytest

    Fake = type("_FakeCollisionA", (_Base,), {"kind": "fake_collision_a"})
    # First registration is a no-op collision-wise (the builder was
    # del-ed at module import, so post-import calls raise NameError
    # inside the decorator — which is the point: this test relies on
    # importing the decorator into a *fresh* test-only context via
    # rebinding). See Notes-for-implementer §"Test pollution" for the
    # canonical way to exercise the collision path without polluting
    # module state.
    try:
        critical_event(Fake)
    except NameError:
        # Expected: the builder no longer exists post-import.
        # The collision path is exercised via a fixture that rebinds
        # _CRITICAL_EVENTS_BUILDER for the test's duration; see below.
        pytest.skip("collision path requires fixture; see next test")


def test_double_registration_via_isolated_builder_raises_typeerror(monkeypatch) -> None:
    # AC-4: the canonical way to exercise the collision-at-import path
    # without leaving residue on the module. monkeypatch re-installs a
    # fresh mutable builder for the duration of the test only.
    from codegenie.events import payloads
    from codegenie.events.payloads import _Base, critical_event
    import pytest

    monkeypatch.setattr(payloads, "_CRITICAL_EVENTS_BUILDER", set(), raising=False)

    FakeA = type("_FakeCollisionA", (_Base,), {"kind": "fake_collision_a"})
    critical_event(FakeA)
    with pytest.raises(TypeError, match=r"already registered: _FakeCollisionA"):
        critical_event(FakeA)


def test_decorator_returns_class_unchanged(monkeypatch) -> None:
    # AC-1: decorator is identity — no wrapping, no metaclass, no
    # subclass creation. The class object passed in must be the class
    # object returned out (preserves isinstance / issubclass identity
    # for downstream discriminated-union dispatch).
    from codegenie.events import payloads
    from codegenie.events.payloads import _Base, critical_event

    monkeypatch.setattr(payloads, "_CRITICAL_EVENTS_BUILDER", set(), raising=False)

    FakeB = type("_FakeCollisionB", (_Base,), {"kind": "fake_collision_b"})
    assert critical_event(FakeB) is FakeB
```

### Green — make it pass
Add the `TypeVar` (bound to `_Base`), the builder set, the decorator function, the `@critical_event` lines above the five variant classes, the `Final[frozenset]` snapshot at module tail, the `del _CRITICAL_EVENTS_BUILDER` immediately after, and extend `__all__` with `"critical_event"` and `"_CRITICAL_EVENTS"`.

### Refactor — clean up
- Decorator docstring cites ADR-0006 and states explicitly: "new critical events require updating this decoration AND the golden set in `tests/fence/test_critical_event_vocabulary.py` AND (if the variant is genuinely new) landing the class in S1-02's `_ALL_VARIANT_CLASSES` — the vocabulary fence cross-checks all three, so drift on any one is a loud failure."
- The decorator is `Callable[[type[_BaseT]], type[_BaseT]]` with `_BaseT` bounded to `_Base` — `mypy` preserves the class type post-decoration AND rejects mis-application to non-`_Base` subclasses.
- The collision-raise message names the exact `cls.__name__`; do not swallow it.
- The `TypeError` collision-raise is *usage-error semantic*, chosen for locality; it does not introduce a new domain exception class. This is a documented divergence from `@register_probe`'s `ProbeError` (see Notes-for-implementer §"Exception-class parity").

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

- **Two-stage build.** `_CRITICAL_EVENTS_BUILDER: set[str]` is populated during module import by the decorator; `_CRITICAL_EVENTS: Final[frozenset[str]] = frozenset(_CRITICAL_EVENTS_BUILDER)` snapshots it at module tail; `del _CRITICAL_EVENTS_BUILDER` on the very next line makes the mutable stage physically unreachable. This is the pattern that makes the registry write-only at import time and immutable after — same *shape* as `Final` constants elsewhere in `codegenie.types.identifiers`, but with the added `del` step because the mutable-then-immutable transition here is genuinely load-bearing (post-import mutation of the builder would silently diverge from the frozen snapshot that both the writer and the fence read).

- **The vocabulary fence is the whole point of ADR-0006.** If the test passes after a contributor silently drops `@critical_event` from `MergeOutcome`, the safety claim is gone. The fence's three assertions (golden equality, `_ALL_VARIANT_CLASSES` cross-check, `isinstance(_, frozenset)`) each catch a distinct failure mode. Make sure every failure message names both the missing and the extra entries.

- **Exception-class parity with `@register_probe` — clarified.** ADR-0006 says the pattern is the same *shape* as `@register_probe` (decorator-populated module-level registry, collision-at-import). The exception *class* is not the same: `@register_probe` raises `codegenie.errors.ProbeError`; `@critical_event` raises `TypeError`. This is deliberate — `TypeError` carries usage-error semantics (wrong-way-to-use-this-decorator, no new domain exception class introduced), and adding a new domain exception (`CriticalEventError`) for a single call-site is Rule-2 scope creep. If Phase 10+ adds a third decorator-registry, revisit — a shared `RegistryError` base might emerge at that point.

- **Type bound is the extension-by-addition guardrail.** `_BaseT = TypeVar("_BaseT", bound=_Base)` means `@critical_event MergeOutcome` type-checks (MergeOutcome inherits `_Base`) but `@critical_event SomeUnrelatedBaseModel` is a `mypy --strict` error. Without the bound, a contributor could silently register a string that never appears in the discriminated union, and the writer would never see the event class at runtime — the golden-fence orphan check catches this at test time, but a compiler-caught failure is cheaper. Both defenses land: bound + orphan cross-check.

- **Do NOT add `@critical_event` to any variant other than the five named.** Adding a sixth requires an ADR-0006 amendment (which updates the golden set), not a code-only edit. The vocabulary fence exists to force that conversation.

- **`_CRITICAL_EVENTS` is the stable public symbol.** Step 3's `EventBatchWriter.append` (S3-02) will import `_CRITICAL_EVENTS` from `codegenie.events.payloads` and check `type(event).__name__ in _CRITICAL_EVENTS`. Do not rename, do not move, do not wrap. The single-underscore prefix here is a convention that says "read-only-across-package"; it is intentionally exported via `__all__` because `EventBatchWriter` in the sibling `codegenie.events.log` module needs it.

- **String identity (not class identity) is the writer's key.** The writer looks up by `cls.__name__`, not `cls in _CRITICAL_EVENTS`. This is deliberate — a rename of the class in a distant refactor breaks a name-based check loudly (both fence tests fail), whereas a class-based check would silently continue to work with the old class object cached somewhere. ADR-0006 documents this trade-off.

- **Test pollution.** The naive test — `class _Fake(BaseModel): ...` at module scope, `critical_event(_Fake)` — pollutes `_CRITICAL_EVENTS_BUILDER` for the entire pytest process. Two mitigations:
  1. The `del _CRITICAL_EVENTS_BUILDER` step at module tail means post-import calls to `critical_event` raise `NameError` — the *canonical* runtime path is inert after import.
  2. To *exercise* the collision path in tests, use the `monkeypatch` fixture to re-install a fresh `_CRITICAL_EVENTS_BUILDER` for the duration of the test only (see `test_double_registration_via_isolated_builder_raises_typeerror` above). This keeps the collision-detection logic testable without polluting the module.
  3. Never define the throwaway class at test-module scope — always inside the test function (or via `type()`), so re-runs in the same process don't collide on the class object's `__name__`.

- **Decorator-registry family (Rule of Three watch).** `@register_probe` (Phase 0) is precedent #1; `@critical_event` (this story) is #2. A third decorator-registry (`@register_activity` in S1-04, or `@register_projection` in S7-01) will trigger a rule-of-three question: do we extract a shared `DecoratorRegistry[T, K]` kernel, or keep the three modules with their local implementations? Do NOT pre-extract in this story — the two implementations diverge in exception class and post-freeze semantics (`del` here, not in `@register_probe`), and premature abstraction would erase those deliberate choices. Leave the extraction question to whoever ships precedent #3.

- **`_Base` visibility.** The tests import `_Base` from `codegenie.events.payloads` — the leading underscore signals "module-private by convention", but the collision test genuinely needs it. S1-02's `__all__` may or may not include `_Base`; regardless, direct-attribute import (`from codegenie.events.payloads import _Base`) is legal Python and idiomatic for adjacent test code. If S1-02 ever adds a `# type: ignore[private-import]` or a linter suppresses it, this test-import is the reason to allow it.
