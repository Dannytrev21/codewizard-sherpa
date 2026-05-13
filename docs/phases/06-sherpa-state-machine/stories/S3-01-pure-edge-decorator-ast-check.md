# Story S3-01 — Implement `@pure_edge` AST-walking decorator

**Step:** Step 3 — Ship `@pure_edge` decorator + the four conditional-edge predicates + property tests
**Status:** Ready
**Effort:** S
**Depends on:** S1-02 (`VulnLedger` Pydantic model), S1-04 (`ImpureEdge` exception lives in `graph/events.py`)
**ADRs honored:** ADR-0012 (`@pure_edge` discipline — tests over ACL machinery), ADR-0002 (`VulnLedger` integrity), ADR-P6 implicit fence-CI

## Context

Step 3 ships the routing layer. Before any of the four conditional-edge predicates exist, the decorator that polices them needs to land. Per ADR-0012, the discipline rejects two heavier alternatives (docstring `Reads:`/`Writes:` AST validator; per-field `read_acl`/`write_acl`) and ships exactly the smallest static check that catches the *only* structurally-detectable purity violation in an edge predicate: **importing a non-deterministic module**. Anything else (referential transparency, label depending only on a state projection) is verified by behavior tests (S3-03), not by static analysis.

The decorator does three things and only three things:

1. AST-walk the wrapped function's body **at import time** (decorator application time, not first call).
2. Raise `ImpureEdge` if any `Import` or `ImportFrom` node references `random`, `time`, `os`, or `datetime` — with one explicit whitelist: `from datetime import fromisoformat` (or attribute access `datetime.fromisoformat`) is allowed for ISO 8601 parsing of timestamps inside `VulnLedger`.
3. Register the wrapped function in a module-level list `_PURE_EDGES: list[Callable]` so S3-03's Hypothesis property tests can iterate over every decorated predicate.

The decorator does **not** verify "depends only on a state projection" via AST. Per ADR-0012 that path is too brittle (`getattr(state, name)`, chained access, tuple destructure all defeat it). The projection-invariance test in S3-03 is the behavior-level replacement.

## References — where to look

- **Architecture:** `../phase-arch-design.md §Component 4 "@pure_edge predicates"` (lines ~701–746) — the canonical decorator contract; `../phase-arch-design.md §Testing strategy` Layer 0 (the AST gate) and Layer 1 (per-predicate label tests).
- **Phase ADRs:** `../ADRs/0012-pure-edge-discipline-tests-over-acl-machinery.md` — the *why* this is a tiny decorator and not a docstring validator; explicitly closes `critique.md best-practices.2` and `critique.md security.3`.
- **Phase ADRs:** `../ADRs/0002-vuln-ledger-frozen-false-with-runtime-mutation-hook.md` — companion safety net at the node layer.
- **Source design:** `../final-design.md §Component 4 "@pure_edge"` (line ~221) and `§Synthesis ledger row 13` — synthesis-time rationale.
- **High-level plan:** `../High-level-impl.md §Step 3` lines 76–98 — feature list and done criteria.
- **Existing code:** `src/codegenie/graph/edges.py` (stub created in S1-01); `src/codegenie/graph/events.py` (`ImpureEdge` exception class created in S1-04). The decorator lives in `edges.py` because that's the only module any predicate will be defined in.

## Goal

Land `@pure_edge` in `src/codegenie/graph/edges.py` so it AST-rejects forbidden imports at decoration time, whitelists `datetime.fromisoformat`, and registers each decorated predicate for downstream property tests.

## Acceptance criteria

- [ ] `@pure_edge` is defined in `src/codegenie/graph/edges.py`, takes `Callable[[VulnLedger], str]`, returns the same callable unchanged, and runs its AST check synchronously at decoration time.
- [ ] Decorating a function whose body contains `import random`, `import time`, `import os`, `import datetime`, `from random import ...`, `from time import ...`, `from os import ...`, or `from datetime import ...` (other than `fromisoformat`) raises `ImpureEdge` with a message naming the offending module and the line number.
- [ ] Decorating a function whose body contains `from datetime import fromisoformat` (or uses `datetime.fromisoformat` via attribute access on a module-level import that does not appear inside the function body) does **not** raise.
- [ ] Each decorated function is appended to a module-level `_PURE_EDGES: list[Callable[..., str]]` registry that S3-03 will consume; the registry is exposed via `from codegenie.graph.edges import _PURE_EDGES`.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline

1. In `src/codegenie/graph/edges.py` add module-level constants: `_BANNED_MODULES = frozenset({"random", "time", "os", "datetime"})` and `_DATETIME_WHITELIST = frozenset({"fromisoformat"})`.
2. Add a module-level mutable registry `_PURE_EDGES: list[Callable[..., str]] = []`.
3. Define `pure_edge(func: Callable[[VulnLedger], str]) -> Callable[[VulnLedger], str]`:
   - Use `inspect.getsource(func)` + `textwrap.dedent` + `ast.parse` to obtain the function's AST.
   - Walk the body with `ast.walk` looking for `ast.Import` and `ast.ImportFrom` nodes.
   - For `ast.Import`: any `alias.name` whose first dotted segment is in `_BANNED_MODULES` raises `ImpureEdge(module=name, lineno=node.lineno, function=func.__name__)`.
   - For `ast.ImportFrom`: if `node.module` first dotted segment is in `_BANNED_MODULES`, raise unless `node.module == "datetime"` and every `alias.name` is in `_DATETIME_WHITELIST`.
   - Append `func` to `_PURE_EDGES` after the check passes.
   - Return `func` unchanged (the decorator is non-wrapping; no `functools.wraps` needed because no wrapper is produced).
4. Confirm `ImpureEdge` from `src/codegenie/graph/events.py` accepts `module`, `lineno`, `function` kwargs (S1-04 should have shipped it; if not, surface as a blocker, not an inline edit).
5. Add a module docstring noting "Forbidden modules are AST-checked at decoration time; runtime calls to the decorated function are not instrumented — purity at call time is enforced by behavior tests in `tests/graph/test_edges_determinism.py` and `tests/graph/test_edge_label_depends_only_on_projection.py`."

## TDD plan — red / green / refactor

### Red

Test file: `tests/graph/test_pure_edge_rejects_forbidden_imports.py`

```python
"""Story S3-01 — @pure_edge AST-walking decorator.

These tests pin ADR-0012: the decorator catches the only structurally-detectable
purity violation (an import of random|time|os|datetime, with one whitelist).
"""
from __future__ import annotations

import pytest

from codegenie.graph.edges import pure_edge, _PURE_EDGES
from codegenie.graph.events import ImpureEdge
from codegenie.graph.state import VulnLedger  # from S1-02


class TestPureEdgeRejectsForbiddenImports:
    def test_rejects_import_time(self) -> None:
        with pytest.raises(ImpureEdge) as exc:
            @pure_edge
            def bad(state: VulnLedger) -> str:
                import time  # noqa: F401
                return "x"
        assert exc.value.module == "time"
        assert exc.value.function == "bad"

    def test_rejects_import_random(self) -> None:
        with pytest.raises(ImpureEdge):
            @pure_edge
            def bad(state: VulnLedger) -> str:
                import random  # noqa: F401
                return "x"

    def test_rejects_import_os(self) -> None:
        with pytest.raises(ImpureEdge):
            @pure_edge
            def bad(state: VulnLedger) -> str:
                import os  # noqa: F401
                return "x"

    def test_rejects_import_datetime_bare(self) -> None:
        with pytest.raises(ImpureEdge):
            @pure_edge
            def bad(state: VulnLedger) -> str:
                import datetime  # noqa: F401
                return "x"

    def test_rejects_from_time_import(self) -> None:
        with pytest.raises(ImpureEdge):
            @pure_edge
            def bad(state: VulnLedger) -> str:
                from time import sleep  # noqa: F401
                return "x"

    def test_rejects_from_datetime_import_now(self) -> None:
        # datetime.now is the non-whitelisted attack vector that motivated the whitelist
        with pytest.raises(ImpureEdge):
            @pure_edge
            def bad(state: VulnLedger) -> str:
                from datetime import datetime as dt  # noqa: F401
                return "x"


class TestPureEdgeWhitelistsFromisoformat:
    def test_allows_from_datetime_import_fromisoformat(self) -> None:
        @pure_edge
        def good(state: VulnLedger) -> str:
            from datetime import fromisoformat  # noqa: F401
            return "ok"
        assert good in _PURE_EDGES

    def test_allows_module_level_datetime_attribute_access(self) -> None:
        # Module-level `import datetime` outside the function body is the
        # caller's problem (fence-CI gate from S1-01 catches it at file scope);
        # the decorator only walks the function body.
        @pure_edge
        def good(state: VulnLedger) -> str:
            # no import statements inside the body
            return "ok"
        assert good in _PURE_EDGES


class TestPureEdgeRegisters:
    def test_decorated_function_appears_in_registry(self) -> None:
        @pure_edge
        def my_edge(state: VulnLedger) -> str:
            return "x"
        assert my_edge in _PURE_EDGES

    def test_decorator_returns_function_unchanged(self) -> None:
        def raw(state: VulnLedger) -> str:
            return "x"
        wrapped = pure_edge(raw)
        assert wrapped is raw  # identity, not a wrapper
```

### Green

Smallest shape that passes: implement `pure_edge` exactly per the implementation outline above. ~25 LOC of decorator body plus the registry list and the two frozensets.

### Refactor

- Add precise type hints — `Callable[[VulnLedger], str]` for the predicate, `_PURE_EDGES: list[Callable[..., str]]`.
- Add a module docstring naming ADR-0012 as the source-of-truth.
- Verify `inspect.getsource` works for functions defined inside test classes (it does — the AST is parsed from the source string, not from `func.__code__`). If a future call-site defines a predicate via `exec`/`compile` (no source available), `inspect.getsource` raises `OSError`; document this constraint in the decorator docstring so a future contributor doesn't try.
- Ensure the registry is **not cleared between tests** unintentionally — but in tests we add to it freely; the property-test pass in S3-03 iterates a snapshot. Note this in implementer notes.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/graph/edges.py` | Add `pure_edge` decorator, `_PURE_EDGES` registry, `_BANNED_MODULES`, `_DATETIME_WHITELIST` constants. |
| `tests/graph/test_pure_edge_rejects_forbidden_imports.py` | Red test (becomes green when decorator lands). |

## Out of scope

- The four predicates themselves (`route_after_select_recipe`, `route_after_rag`, `route_after_attempt`, `route_after_human`) — they ship in S3-02.
- Hypothesis property tests for determinism and label-projection invariance — S3-03.
- Verifying "the function reads only declared fields" via AST — explicitly rejected by ADR-0012; do not add this.
- Runtime instrumentation of the wrapped function (no monkey-patching of `time.time`); behavior tests are the runtime-purity check.

## Notes for the implementer

1. The AST check runs at **decoration time** (function-definition time). Tests that decorate inside `with pytest.raises(...)` rely on the decorator raising synchronously — confirm this by reading the test carefully before changing the implementation.
2. `inspect.getsource` requires the function source to be on disk (or in a readable frame); `lambda` predicates or predicates produced by `exec` will fail with `OSError`. Document the constraint and surface a clear error message in `pure_edge` that names this constraint if `getsource` fails.
3. The whitelist is narrow: only `from datetime import fromisoformat`. Any other `from datetime import X` (especially `datetime`, `date`, `time`, `timezone`, `now`) must raise. The test `test_rejects_from_datetime_import_now` pins this.
4. **Do not** clear `_PURE_EDGES` between tests. It is a module-level append-only list. S3-03's property tests iterate a snapshot. Tests that need isolation should test ID-equality of the decorated function in the registry rather than length.
5. The decorator is a no-op at runtime (returns `func` unchanged). This is deliberate — no wrapper means no `functools.wraps`, no perf overhead per call, and `inspect.signature(func)` continues to work for LangGraph's introspection.
6. Fence-CI from S1-01 already forbids `graph/edges.py` from importing `random|time|os|datetime` at the **file level**; this story's decorator catches the case where a contributor imports inside a function body to dodge the fence rule. Both layers are intentional.
