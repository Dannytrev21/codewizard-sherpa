# Story S4-01 — Ship `@audited_node` decorator + node-test scaffolding

**Step:** Step 4 — Implement the ten nodes as thin wrappers over Phase 3/4/5 engines
**Status:** Ready
**Effort:** S
**Depends on:** S1-04
**ADRs honored:** ADR-0002 (`frozen=False` + runtime mutation hook), ADR-0012 (pure-edge discipline; sibling concerns belong in tests, not ACLs)

## Context

Every Phase 6 node body is a sync `(state: VulnLedger) -> VulnLedger` that *must* return `state.model_copy(update={...})` — never mutate in place. S1-04 shipped `make_after_node_hook()`, which diffs `id()` of mutable fields between `before` and `after` and raises `LedgerMutatedInPlace` if `id()` matches but content does not. That hook is useless until it is *wired* — Phase 6 chooses a decorator (`@audited_node`) rather than a custom LangGraph callback because it keeps the seam local to each node module (every `graph/nodes/*.py` re-exports its node through the decorator) and survives LangGraph minor bumps that might break callback shapes.

This story also ships the **shared test scaffolding** every S4-02..S4-09 will use: `tests/graph/test_nodes/conftest.py` with `make_ledger(...)` fixtures (constructs a minimal-but-valid `VulnLedger` for every node's input shape) and `mock_phase{3,4,5}_engine` autouse fixtures (patch the Phase 3/4/5 import boundaries so node tests run without booting sandboxes or hitting LLMs). Without this scaffolding, every later S4-* story would reinvent ledger construction and engine mocking and they'd drift.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Component 5 "Nodes"` (table of inputs/outputs per node); `../phase-arch-design.md §Component 7 "Runtime after-node id()-diff hook"`; `../phase-arch-design.md §Testing strategy — Test pyramid Layer 1`
- **Phase ADRs:** `../ADRs/0002-vuln-ledger-frozen-false-with-runtime-mutation-hook.md` — wraps the model + hook contract; `../ADRs/0012-pure-edge-discipline-tests-over-acl-machinery.md` — explains why this is a decorator+tests, not an ACL framework
- **Source design:** `../final-design.md §Component 7 "Runtime after-node id()-diff hook"`; `../final-design.md §Departures from all three inputs — "Runtime in-place-mutation hook via id() diff"`
- **High-level-impl:** `../High-level-impl.md §Step 4 — Features delivered` — the `@audited_node` bullet

## Goal

Ship `@audited_node` decorator and the shared `tests/graph/test_nodes/conftest.py` so every subsequent S4-02..S4-09 node story has a one-line wrap-and-test path.

## Acceptance criteria

- [ ] `src/codegenie/graph/hooks.py` exports `audited_node(fn: Callable[[VulnLedger], VulnLedger]) -> Callable[[VulnLedger], VulnLedger]` that calls `fn(state)`, runs the `make_after_node_hook()` diff against `(state, returned)`, and returns `returned` unchanged on success.
- [ ] `tests/graph/test_nodes/conftest.py` exposes `make_ledger(**overrides) -> VulnLedger` building a minimal-valid ledger (`schema_version="v0.6.0"`, fake `AdvisoryRef`, empty `prior_attempts`, `chain_head=b"\x00"*32`, etc.) and `mock_phase3`, `mock_phase4`, `mock_phase5` autouse fixtures patching `codegenie.recipes.*`, `codegenie.planner.*`, `codegenie.gates.*` at their import boundaries.
- [ ] The TDD red test `tests/graph/test_audited_node.py::test_audited_node_catches_in_place_mutation` is committed first and fails on a stub; passes once the wrapper invokes the hook.
- [ ] A second test asserts the decorator is **transparent** for well-behaved nodes (returning `state.model_copy(update={...})` does not raise).
- [ ] `mypy --strict src/codegenie/graph/hooks.py tests/graph/test_nodes/conftest.py` clean; no `Any`, no `cast`, no un-justified `# type: ignore`. `ruff format` / `ruff check` clean. `pytest tests/graph/test_audited_node.py` green.

## Implementation outline

1. Read `graph/hooks.py` from S1-04 to see the current shape of `make_after_node_hook()`; confirm it returns `Callable[[VulnLedger, VulnLedger, str], None]`.
2. Add `audited_node(fn)` in `graph/hooks.py`: closes over a process-wide singleton `_HOOK = make_after_node_hook()`, returns a wrapper that captures `before = state`, calls `after = fn(state)`, invokes `_HOOK(before, after, fn.__name__)`, returns `after`.
3. Create `tests/graph/test_nodes/__init__.py` (empty) and `tests/graph/test_nodes/conftest.py` with `make_ledger(**overrides)` builder + `mock_phase3/4/5` autouse fixtures using `unittest.mock.patch` against the import paths each node will use (e.g., `codegenie.recipes.advisory.AdvisoryLoader`, `codegenie.planner.fallback_tier.FallbackTier`, `codegenie.gates.runner.GateRunner`, `codegenie.gates.retry_ledger.RetryLedger`).
4. Document in the conftest's module docstring that tests requiring a *specific* engine response must override the autouse mock (`mocker.patch.object(...)` or `monkeypatch.setattr(...)`).
5. Write the two TDD tests below; commit them as the red step before adding `audited_node`.
6. Implement `audited_node`; both tests turn green.

## TDD plan — red / green / refactor

```python
# tests/graph/test_audited_node.py
import pytest
from codegenie.graph.hooks import audited_node, LedgerMutatedInPlace
from tests.graph.test_nodes.conftest import make_ledger


def test_audited_node_catches_in_place_mutation():
    # Arrange — a buggy "node" that mutates events in place
    @audited_node
    def bad_node(state):
        state.events.append("oops")  # in-place: same id(), different content
        return state

    ledger = make_ledger()

    # Act + Assert
    with pytest.raises(LedgerMutatedInPlace) as exc_info:
        bad_node(ledger)
    assert exc_info.value.field == "events"
    assert exc_info.value.node == "bad_node"


def test_audited_node_transparent_on_model_copy():
    # Arrange — a well-behaved node
    @audited_node
    def good_node(state):
        return state.model_copy(update={"events": state.events + ["clean"]})

    ledger = make_ledger()

    # Act
    returned = good_node(ledger)

    # Assert — returns the new ledger unchanged; no exception
    assert returned is not ledger
    assert returned.events == ["clean"]
    assert ledger.events == []  # original untouched
```

**Red:** Both tests fail because `audited_node` doesn't exist yet (ImportError).
**Green:** Implement `audited_node` in `graph/hooks.py` as a closure over the singleton hook; both tests pass.
**Refactor:** Confirm the wrapper's `functools.wraps(fn)` preserves `__name__` (so the hook's `node` field is meaningful) and that the singleton hook is created lazily on first call (not at module import) to avoid coupling import order to `_MUTABLE_FIELDS`.

## Files to touch

| Path | Action |
|---|---|
| `src/codegenie/graph/hooks.py` | Add `audited_node(fn)` decorator |
| `tests/graph/test_nodes/__init__.py` | New (empty) |
| `tests/graph/test_nodes/conftest.py` | New — `make_ledger` + `mock_phase3/4/5` fixtures |
| `tests/graph/test_audited_node.py` | New — the two TDD tests above |

## Out of scope

- Any actual node implementation (S4-02..S4-09 land those).
- Cross-process mutation detection (the hook is in-process; durability + tamper-detection is the checkpointer's job, S2-01..S2-03).
- AST-based static mutation analysis (rejected by ADR-0012; we use the runtime hook instead).
- `audited_node` doing *anything* beyond the id()-diff hook — no logging, no tracing, no event emission. Nodes emit events themselves.

## Notes for the implementer

- The hook must be invoked **after** the node returns but **before** the returned ledger is handed back to LangGraph. Otherwise an in-place mutation would propagate one node further and the failure would be misattributed.
- `make_ledger()` must respect `extra="forbid"` — every required field must be supplied with a valid default. If `VulnLedger` later gains a non-Optional field, `make_ledger()` is the one place to update.
- Patch Phase 3/4/5 engines at their **import paths** (the module where each node will `from X import Y`), not at their origin module. This is the standard mock-where-it's-used rule and prevents test-leakage across nodes.
- Per `../phase-arch-design.md §Component 7`, `_MUTABLE_FIELDS = ["prior_attempts", "events"]` — the hook only covers top-level mutable fields by design; deep-nested mutations of frozen sub-models (e.g., `AttemptSummary`) cannot occur because those models are `frozen=True`.
- Keep the decorator < 15 LOC. The whole point is "thin wrapper over the existing hook"; do not introduce a class or a registry.
