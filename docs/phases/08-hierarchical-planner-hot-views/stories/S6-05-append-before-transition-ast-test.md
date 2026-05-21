# Story S6-05 — Add the static append-before-transition AST test

**Step:** Step 6 — Assemble the Supervisor graph and the pure decide() core
**Status:** Ready
**Effort:** S
**Depends on:** S6-03
**ADRs honored:** ADR-0001

## Context
Exit criterion 1 of Phase 8 is "the chosen path is logged on every workflow". S5-06 wired `PlannerNode.route` to append the `RouteDecided` event *before* returning the `RouteDecision`, making the append a precondition of the routing transition. But "before" is a property of the code's *shape* — a future edit could add a routing return path that skips the append, and a behavioral test would only catch the cases it happens to exercise. This story adds a **static AST test** that proves, by construction, that no routing code path in `route_node`/`PlannerNode.route` reaches a routing transition without the `RouteDecided` append. It is the polishing guard that turns exit criterion 1 from "tested" into "structurally impossible to violate".

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C7 — Routing/resolution event emission` — "A static test asserts no routing edge is reachable on a code path that skips the append".
  - `../phase-arch-design.md §Goals` — G1: "A static AST test asserts no routing code path reaches a transition without the append. (Exit criterion 1.)".
  - `../phase-arch-design.md §Testing strategy` — §CI gates: "The `RouteDecided`-append static test — no routing edge reachable on a code path that skips the append"; §Adversarial tests — the functional-core purity fence as the AST-scan precedent.
  - `../phase-arch-design.md §Control flow` — step 4: `route` "emits `RouteDecided` via `EventLog.emit_internal` *before* returning".
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0001-supervisor-graph-engine.md` — ADR-0001 — the three-node discipline is enforced by tests, not a graph type; this AST test is part of that enforcement.
- **Existing code (if any):**
  - `src/codegenie/planner/routing.py` — `PlannerNode.route` (S5-05/S5-06) — the function whose AST this test scans.
  - `src/codegenie/supervisor/graph.py` — `route_node` (S6-02/S6-03) — the node that calls `route`.
  - `tests/unit/plugins/test_resolver_purity.py` — the precedent AST-source-scan test to mirror in structure (`ast.parse`, walk, assert).

## Goal
A static AST test fails if any `return` of a `RouteDecision` inside `PlannerNode.route` is reachable without a preceding `emit_internal(RouteDecided(...))` call on the same code path.

## Acceptance criteria
- [ ] A test file scans `codegenie/planner/routing.py` (and, if `route_node` itself constructs a `RouteDecision`, `codegenie/supervisor/graph.py`) with `ast.parse` — no `import`, no execution of the module under test.
- [ ] The test asserts every code path in `PlannerNode.route` that returns / yields a `RouteDecision` is dominated by a `RouteDecided`-append call (an `emit_internal` call whose argument constructs `RouteDecided`).
- [ ] The test fails on a deliberately-mutated copy of `route` where the append is deleted or moved after the `return` — verified by a fixture or an inline mutation check, so the test is proven to have teeth (it is not vacuously green).
- [ ] The test is named and placed so `make check` runs it — it is a CI gate, not an opt-in marker.
- [ ] The TDD plan's red test exists, was committed, and is green against the real (correct) `route` implementation.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Create `tests/unit/planner/test_route_append_before_transition.py`. Read `routing.py` source and `ast.parse` it (no import) — mirror `tests/unit/plugins/test_resolver_purity.py`'s scan structure.
2. Locate the `route` function node; collect all `ast.Return` (and `ast.Expr`/`ast.Yield` if applicable) nodes that produce a `RouteDecision`, and all call sites of `emit_internal` whose argument is a `RouteDecided(...)` construction.
3. Assert dominance: every `RouteDecision`-return is preceded — on every path that reaches it — by a `RouteDecided` append. The simplest sound check given the fixed-pipeline shape: assert the append statement appears *lexically before* every `return RouteDecision` and is not nested in a branch that a return can bypass. Document the soundness assumption in the test docstring.
4. Add a teeth-proving check: a small fixture (a mutated source string with the append removed) the same scan logic flags — assert the scan would fail it.
5. Keep the test pure-AST and fast (sub-millisecond) so it runs on every PR.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/planner/test_route_append_before_transition.py`
First red test — the real implementation passes the structural check:
```python
def test_route_appends_route_decided_before_every_transition() -> None:
    # arrange: ast.parse the source of codegenie/planner/routing.py; find the `route` FunctionDef
    # act: returns = collect_route_decision_returns(route_def)
    #      appends = collect_route_decided_appends(route_def)
    # assert: every return is dominated by an append (no RouteDecision return on a path that skips the append)
    ...
```
Second red test — the scan has teeth (would catch a regression):
```python
def test_scan_flags_a_route_with_the_append_removed() -> None:
    # arrange: a source string of `route` with the emit_internal(RouteDecided(...)) line deleted
    # act: parse it, run the same dominance check
    # assert: the check reports a violation  (pytest.raises / returns False)
    ...
```
### Green — make it pass
This story is test-only — the "green" is that the real `route` (S5-06) already satisfies the structural property. If the real `route` *fails* the scan, that is a real S5-06 defect — surface it loudly, do not weaken the scan to pass. Implement the AST-walk helpers (`collect_route_decision_returns`, `collect_route_decided_appends`, the dominance check) in the test file.
### Refactor — clean up
Docstring the soundness assumption — what code shapes the scan covers and what it deliberately does not (e.g. it assumes `route` is a fixed-pipeline function, not a dynamic-dispatch jungle, per ADR-0011). Type-hint the AST helpers. Keep the scan logic in the test file (not `src/`) unless a sibling test reuses it.

## Files to touch
| Path | Why |
|---|---|
| `tests/unit/planner/test_route_append_before_transition.py` | New — the static AST append-before-transition test + the teeth-proving check. |

## Out of scope
- The *behavioral* decision-log completeness test (N workflows → N `RouteDecided` events) — S7-05.
- The `phase08_e2e` routing test asserting `RouteDecided` is in the live stream — S7-02.
- `RouteDescended` emission wiring — S7-05.
- Any change to `route` itself — S5-06 owns the implementation; this story only proves its shape. If the scan finds a real defect, route it back to S5-06, do not fix it here silently.

## Notes for the implementer
- This is a *static* test — it must `ast.parse` the source, never `import` and run `routing.py`. Mirror `tests/unit/plugins/test_resolver_purity.py` exactly.
- The test must have teeth — the second red test (the mutated-source check) is the AC that proves the scan is not vacuously green. A static test that passes a deliberately-broken input is worthless (Rule 9).
- ADR-0011 fixes `route` to a fixed three-step pipeline — lean on that: the scan does not need to handle arbitrary control flow, only the fixed-pipeline shape. State that assumption in the docstring so a future engineer who makes `route` dynamic knows the scan needs revisiting.
- If the real `route` does not pass the scan, that is exit-criterion-1 broken — surface it as a blocking finding against S5-06, do not loosen the assertion.
- The fixed-tuple iteration in `route` (one `return` per first-hit, one fallthrough `LLM` return) is the precise structure to enumerate — every one of those returns must be dominated by the single append.
