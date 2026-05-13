# Story S1-04 — Add `GraphEvent` + exception hierarchy + after-node `id()`-diff hook

**Step:** Step 1 — Scaffold `graph/` package, ship `VulnLedger` + HITL contracts + structural CI gates
**Status:** Ready
**Effort:** M
**Depends on:** S1-02, S1-03
**ADRs honored:** ADR-0002, ADR-0005, ADR-0007, ADR-0012

## Context
This story closes Step 1's structural contract: the `GraphEvent` cost-ledger seam (Phase 13's input shape), the seven typed exception classes the rest of Phase 6 raises, and — load-bearing — the after-node `id()`-diff hook that makes ADR-0002's "frozen=False + runtime mutation detection" decision real. Without this hook, any node author who writes `state.events.append(e)` silently breaks replay determinism (the canonical Edge case #8). With it, the violation raises `LedgerMutatedInPlace` at the moment of return, with the offending field and node named.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Component 7 — Runtime after-node id()-diff hook` (lines 818–838) — exact `make_after_node_hook` signature, `_MUTABLE_FIELDS` enumeration, hook semantics.
  - `../phase-arch-design.md §Component 9 — events.py` (lines 864–884) — `GraphEvent` shape and `emit_event` constructor.
  - `../phase-arch-design.md §Data model — Internal` (lines 985–994) — full exception-class list with init signatures.
  - `../phase-arch-design.md §Edge cases #8` — the in-place-mutation canary case this hook defends against.
- **Phase ADRs:**
  - `../ADRs/0002-vuln-ledger-frozen-false-with-runtime-mutation-hook.md` — ADR-0002 — this story implements the *hook* side of the decision; S1-02 implemented the *model* side.
  - `../ADRs/0005-static-schema-version-literal-pin.md` — ADR-0005 — `SchemaDrift` and `CheckpointSchemaMismatch` exceptions live here; raisers ship in Step 2.
  - `../ADRs/0007-blake3-chain-extension-and-tamper-evidence.md` — ADR-0007 — `CheckpointTampered`, `AuditChainCorrupted` exceptions live here; raisers ship in Step 2.
  - `../ADRs/0012-pure-edge-discipline-tests-over-acl-machinery.md` — ADR-0012 — `ImpureEdge` exception lives here; raiser ships in S3-01.
- **Source design:**
  - `../final-design.md §Synthesis ledger row 1` — frozen-vs-hook rationale.

## Goal
Land `src/codegenie/graph/events.py` and `src/codegenie/graph/hooks.py` with `GraphEvent`, `emit_event()`, the seven typed exceptions, and `make_after_node_hook()` so every later node module has the runtime safety net and the cost-ledger seam ready to import.

## Acceptance criteria
- [ ] `src/codegenie/graph/events.py` exports `GraphEvent` (frozen, extra=forbid, fields per arch §Component 9) and `emit_event(state, node_name, kind, fields=None, wall_clock_ms=None) -> GraphEvent`.
- [ ] `src/codegenie/graph/hooks.py` exports seven exception classes: `LedgerMutatedInPlace`, `CheckpointTampered`, `CheckpointerInsecure`, `SchemaDrift`, `AuditChainCorrupted`, `CheckpointSchemaMismatch`, `ImpureEdge` — each a `RuntimeError` subclass; `LedgerMutatedInPlace` accepts `field=` and `node=` keyword args.
- [ ] `hooks.py` exports `make_after_node_hook() -> Callable[[VulnLedger, VulnLedger, str], None]` and `_MUTABLE_FIELDS = ("prior_attempts", "events")` (or `frozenset`).
- [ ] Hook raises `LedgerMutatedInPlace(field="events", node="<name>")` when `id(before.events) == id(after.events)` AND `before.events != after.events`.
- [ ] Hook is silent (returns `None`) when nodes correctly use `model_copy(update={"events": state.events + [...]})` — new list object, new `id()`.
- [ ] Hook is silent when nothing mutated (`before == after`, same `id`).
- [ ] The TDD plan's red tests exist, were committed, and are green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/graph/`, and `pytest tests/graph/test_events.py tests/graph/test_hooks.py` all pass.

## Implementation outline
1. Land `events.py` first: a `GraphEvent` frozen `BaseModel` + a tiny `emit_event` factory that captures `datetime.now(timezone.utc)` only when `at` is not supplied. Keep `emit_event` deterministic when given an explicit `at` — useful for tests.
2. Land `hooks.py`: define seven exception classes; `LedgerMutatedInPlace.__init__` accepts `*, field: str, node: str` and stores both on the instance plus formats a useful `__str__`.
3. Implement `make_after_node_hook()` as a closure returning a callable; iterate `_MUTABLE_FIELDS`; for each field compare `id()` and content via `!=`.
4. Author red tests covering: (a) in-place `events.append` is caught; (b) `model_copy(update={"events": ...})` passes; (c) no mutation passes; (d) `prior_attempts` mutation is also caught; (e) each exception is instantiable with documented kwargs and stringifies usefully.
5. `VulnLedger.model_rebuild()` may be needed in `__init__.py` once `events.py` lands so the forward reference to `GraphEvent` in `VulnLedger.events` resolves — surface this dependency loudly if `model_rebuild` is required.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/graph/test_hooks.py`

```python
def test_after_node_hook_catches_in_place_append_to_events() -> None:
    # arrange: a baseline ledger; the "after" is the SAME object mutated in place
    before = _make_minimal_ledger()
    after = before  # same id()
    after.events.append(GraphEvent(  # noqa: PERF  -- deliberately wrong on purpose
        node_name="ingest_cve", kind="enter",
        at=datetime(2026, 5, 12, tzinfo=timezone.utc),
    ))
    hook = make_after_node_hook()
    # act + assert: hook raises with field name and node name in the message
    with pytest.raises(LedgerMutatedInPlace) as exc:
        hook(before, after, node_name="ingest_cve")
    assert exc.value.field == "events"
    assert exc.value.node == "ingest_cve"
    assert "events" in str(exc.value)
    assert "ingest_cve" in str(exc.value)


def test_after_node_hook_silent_on_model_copy_update() -> None:
    # arrange: idiomatic node return — new list object
    before = _make_minimal_ledger()
    new_event = GraphEvent(
        node_name="ingest_cve", kind="enter",
        at=datetime(2026, 5, 12, tzinfo=timezone.utc),
    )
    after = before.model_copy(update={"events": before.events + [new_event]})
    # assert: different id() AND different content -> hook is silent
    assert id(before.events) != id(after.events)
    hook = make_after_node_hook()
    hook(before, after, node_name="ingest_cve")  # must not raise


def test_after_node_hook_silent_when_nothing_mutated() -> None:
    # arrange: same object, no mutation
    before = _make_minimal_ledger()
    hook = make_after_node_hook()
    # act + assert: same id, same content -> silent
    hook(before, before, node_name="ingest_cve")


def test_after_node_hook_catches_in_place_append_to_prior_attempts() -> None:
    # arrange: pin _MUTABLE_FIELDS coverage — prior_attempts is also watched
    before = _make_minimal_ledger()
    after = before
    after.prior_attempts.append(_make_attempt_summary())
    hook = make_after_node_hook()
    with pytest.raises(LedgerMutatedInPlace) as exc:
        hook(before, after, node_name="record_attempt")
    assert exc.value.field == "prior_attempts"


def test_exception_hierarchy_all_runtime_errors_and_instantiable() -> None:
    # arrange + act: each exception class must instantiate with its documented kwargs
    # assert: subclass check + str() is informative
    assert issubclass(LedgerMutatedInPlace, RuntimeError)
    assert issubclass(CheckpointTampered, RuntimeError)
    assert issubclass(CheckpointerInsecure, RuntimeError)
    assert issubclass(SchemaDrift, RuntimeError)
    assert issubclass(AuditChainCorrupted, RuntimeError)
    assert issubclass(CheckpointSchemaMismatch, RuntimeError)
    assert issubclass(ImpureEdge, RuntimeError)
    # LedgerMutatedInPlace requires kwargs
    e = LedgerMutatedInPlace(field="events", node="ingest_cve")
    assert "events" in str(e) and "ingest_cve" in str(e)
```

Test file path: `tests/graph/test_events.py`

```python
def test_graph_event_is_frozen_and_extra_forbid() -> None:
    # arrange: a valid GraphEvent
    e = GraphEvent(node_name="ingest_cve", kind="enter",
                   at=datetime(2026, 5, 12, tzinfo=timezone.utc))
    # act + assert: cannot mutate
    with pytest.raises(ValidationError):
        e.node_name = "select_recipe"  # type: ignore[misc]
    # extra field rejected
    with pytest.raises(ValidationError):
        GraphEvent.model_validate({
            "node_name": "x", "kind": "enter",
            "at": "2026-05-12T00:00:00Z", "rogue": True,
        })


def test_emit_event_with_explicit_at_is_deterministic() -> None:
    # arrange + act: emit_event with explicit at produces a stable GraphEvent
    fixed = datetime(2026, 5, 12, 12, 0, 0, tzinfo=timezone.utc)
    e1 = emit_event(_make_minimal_ledger(), "ingest_cve", "enter",
                    fields={"k": "v"}, wall_clock_ms=10)  # default at=now
    # cannot assert wall_clock; assert structural fields
    assert e1.node_name == "ingest_cve"
    assert e1.kind == "enter"
    assert e1.fields == {"k": "v"}
    assert e1.wall_clock_ms == 10
```

### Green — make it pass
- `events.py`: `GraphEvent(BaseModel)` with `model_config = ConfigDict(extra="forbid", frozen=True)` and the fields per arch §Component 9. `emit_event` is a free function that constructs a `GraphEvent` with `at=datetime.now(timezone.utc)` if not supplied.
- `hooks.py`: seven exception classes (`LedgerMutatedInPlace` with custom `__init__(*, field, node)` storing both and producing `f"{node}: in-place mutation of {field}"`); `_MUTABLE_FIELDS` tuple; `make_after_node_hook` closure.

### Refactor — clean up
- Module docstring on `events.py`: "Cost-ledger seam — Phase 13 consumes this stream."
- Module docstring on `hooks.py`: "Runtime safety net for ADR-0002; structural enforcement for ADR-0007 and ADR-0012."
- The `kind: Literal["enter", "exit", "decision", "interrupt", "resume"]` Literal set is exhaustive per arch §Component 9 — match it exactly.
- Consider extracting `_MUTABLE_FIELDS` as `Final[tuple[str, ...]]` to satisfy mypy strict.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/graph/events.py` | `GraphEvent` + `emit_event`. |
| `src/codegenie/graph/hooks.py` | Seven exception classes + `_MUTABLE_FIELDS` + `make_after_node_hook`. |
| `src/codegenie/graph/__init__.py` | Add `VulnLedger.model_rebuild()` (if needed) once forward refs resolve. |
| `tests/graph/test_events.py` | Red tests for `GraphEvent` shape + `emit_event` semantics. |
| `tests/graph/test_hooks.py` | Red tests for hook behavior + exception hierarchy. |
| `tests/graph/conftest.py` | (new or extend) `_make_minimal_ledger()` and `_make_attempt_summary()` helpers — used by S4-* later too. |

## Out of scope
- **`@audited_node` decorator** that wires the hook around every node return — that's S4-01.
- **`@pure_edge` decorator** which raises `ImpureEdge` — that's S3-01.
- **Raisers** of `CheckpointTampered`, `CheckpointerInsecure`, `SchemaDrift`, `AuditChainCorrupted`, `CheckpointSchemaMismatch` — Step 2 (checkpointer).
- **Static test** asserting every node module is `@audited_node`-wrapped — S4-01.
- **Nested-id walks** for mutable sub-collections of `AttemptSummary` (e.g., `failing_signals`) — ADR-0002 records this as a known coverage gap; add it when Step 4 surfaces the need, not preemptively.

## Notes for the implementer
- **`_MUTABLE_FIELDS` is the union of fields the hook iterates.** Arch §Component 7 lists `["prior_attempts", "events"]` as the v0.6.0 set. ADR-0002's "Consequences" block explicitly flags that nested mutable sub-collections (`AttemptSummary.failing_signals`) are **not** caught — do not silently extend the enumeration; surface the gap as a story comment if Step 4 needs it.
- **Hook closure vs class.** Arch §Component 7 shows a closure (`def make_after_node_hook() -> Callable...`). Stay with the closure form — it satisfies `mypy --strict` cleanly with `Callable[[VulnLedger, VulnLedger, str], None]` and matches the arch pseudocode.
- **`id()` semantics.** `id(before_field) == id(after_field)` is the cheap check; `before_field != after_field` is the content check. The order matters — if the ids differ, we are immediately silent (a new list object was constructed, regardless of content). If ids match but content differs, we have an in-place mutation. CPython's GC can theoretically recycle ids, but only after the object is collected; in this context `before` is held by the caller so its list cannot be GC'd before the hook runs.
- **Forward-reference fallout in `VulnLedger`**: `VulnLedger.events: list[GraphEvent]` was a forward reference in S1-02. Land `events.py` first, then call `VulnLedger.model_rebuild()` in `graph/__init__.py` (or use `update_forward_refs()` for older Pydantic). Surface this if it bites — symptom is `PydanticUserError: class not fully defined`.
- **`GraphEvent.kind` Literal set is closed.** Adding a new kind is a contract change. The five existing values cover entry, exit, decision points, the HITL pause, and HITL resume.
- **CLAUDE.md Rule 12 (Fail loud).** `LedgerMutatedInPlace` must name *both* the field and the node in its `__str__`; the test pins this so a future "tidy up the error message" PR can't silently weaken debug surface.
- **Imports.** `hooks.py` imports `VulnLedger` — this is the only file in Step 1 that imports the model for non-typing purposes; everywhere else uses `if TYPE_CHECKING:` to dodge cycles. `events.py` does **not** import `VulnLedger` (it takes the state by parameter and never inspects it).
