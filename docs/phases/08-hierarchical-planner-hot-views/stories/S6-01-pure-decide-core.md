# Story S6-01 — Implement the pure decide() core

**Step:** Step 6 — Assemble the Supervisor graph and the pure decide() core
**Status:** Ready
**Effort:** M
**Depends on:** S2-03
**ADRs honored:** ADR-0001, ADR-0002

## Context
The Supervisor's job ends in exactly one of three structurally distinct outcomes — a single plugin is dispatched, several plugins must run as one coordinated parent workflow, or no concrete plugin matched and the work escalates to a human. This story implements the **pure functional core** that maps `(provenance, resolutions, bundles, routes)` to a `SupervisorDecision` with zero I/O — the heart that the three-node graph (S6-02) wires around. It is foundational: every later Supervisor story dispatches on the value `decide()` returns.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §C1 — Supervisor` — the `decide()` signature; "pure core that maps `(provenance, resolution(s), bundle(s), route(s))` to a `SupervisorDecision` with no I/O".
  - `../phase-arch-design.md §Control flow` — decision points D1 (`PluginResolution` variant) and D2 (`TriggerProvenance` variant).
  - `../phase-arch-design.md §Data model` — the `[contract]` `SupervisorDecision`, `PluginWorkItem`, `TriggerProvenance` definitions.
  - `../phase-arch-design.md §Testing strategy` — "decide() exhaustively over the three SupervisorDecision variants and the two TriggerProvenance variants … zero mocks"; the totality property test.
  - `../phase-arch-design.md §Scenario 3` / `§Scenario 4` — the `Both` and universal-fallback flows `decide()` terminates.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0002-supervisor-decision-three-variant-sum-type.md` — ADR-0002 — `match` + `assert_never` over the three-variant union; one `PluginWorkItem` per resolved task class.
  - `../ADRs/0001-supervisor-graph-engine.md` — ADR-0001 — `decide()` stays a pure core regardless of the graph engine; it is the Phase-9-stable seam.
- **Existing code (if any):**
  - `src/codegenie/supervisor/state.py` — the `SupervisorDecision` union, `Dispatched`, `MultiPluginDispatch`, `EscalatedToHITL`, `PluginWorkItem` declared by S2-01/S2-03; import them, do not redeclare.
  - `src/codegenie/plugins/resolver.py` — the shipped `ConcreteResolution` / `UniversalFallbackResolution` (`PluginResolution`) union `decide()` matches over.
  - `src/codegenie/plugins/resolver.py` precedent `tests/unit/plugins/test_resolver_property.py` — the Hypothesis totality-property style to mirror.

## Goal
A pure `decide()` function exists in `codegenie/supervisor/decide.py` that totally maps `(provenance, resolutions, bundles, routes, parent_workflow_id)` to a `Dispatched | MultiPluginDispatch | EscalatedToHITL` via `match` + `assert_never`, with no imports of any I/O module.

## Acceptance criteria
- [ ] `from codegenie.supervisor.decide import decide` succeeds; the signature matches `§C1` exactly (keyword-only args: `provenance`, `resolutions`, `bundles`, `routes`, `parent_workflow_id`).
- [ ] A single `ConcreteResolution` + `SingleTaskTrigger` yields a `Dispatched`; a `UniversalFallbackResolution` yields an `EscalatedToHITL`; a `BothProvenanceTrigger` with N resolved `ConcreteResolution`s yields a `MultiPluginDispatch` with N `PluginWorkItem`s.
- [ ] Every `match` over `SupervisorDecision` inputs and over the `PluginResolution` variant ends in `assert_never(...)` — adding a fourth variant later is a `mypy` error.
- [ ] A Hypothesis property test confirms `decide()` is total: it returns a `SupervisorDecision` (never raises, never returns `None`) over all `(provenance-variant, resolution-variant)` pairs.
- [ ] A functional-core purity AST test asserts `decide.py` imports no I/O module (mirrors `tests/unit/plugins/test_resolver_purity.py`).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Create `src/codegenie/supervisor/decide.py`. Import `SupervisorDecision`, `Dispatched`, `MultiPluginDispatch`, `EscalatedToHITL`, `PluginWorkItem` from `supervisor/state.py`; `TriggerProvenance`/`SingleTaskTrigger`/`BothProvenanceTrigger` from the same module; `ConcreteResolution`/`UniversalFallbackResolution` from `plugins/resolver.py`.
2. Write `decide(*, provenance, resolutions, bundles, routes, parent_workflow_id) -> SupervisorDecision`. `match` first on whether any resolution is a `UniversalFallbackResolution` → `EscalatedToHITL(reason, evidence)`. Then `match` on `provenance`: `SingleTaskTrigger` → `Dispatched`; `BothProvenanceTrigger` → `MultiPluginDispatch` zipping `resolutions`/`bundles`/`routes` into `PluginWorkItem`s.
3. Close every `match` with `assert_never` so an unhandled variant is a compile error.
4. Add the module-level `_WARNING_IDS` if `decide()` logs (it should not — pure core; logging belongs to the nodes); keep it I/O-free.
5. Wire `decide` into `supervisor/__init__.py` `__all__` only if it is part of the bounded public surface — otherwise keep it package-internal (the graph in S6-02 is the public entry).

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/supervisor/test_decide.py`
One red test per behavior. First red test — single-dispatch happy path:
```python
def test_decide_single_concrete_resolution_yields_dispatched() -> None:
    # arrange: a SingleTaskTrigger + one ConcreteResolution fixture + one Bundle + one RouteDecision
    # act: result = decide(provenance=single, resolutions=(concrete,), bundles=(bundle,),
    #                       routes=(route,), parent_workflow_id=wf_id)
    # assert: isinstance(result, Dispatched) and result.bundle is bundle and result.route is route
    ...
```
Then a red test per remaining behavior: `test_decide_universal_fallback_yields_escalated_to_hitl`, `test_decide_both_provenance_yields_multi_plugin_dispatch` (assert `len(result.work_items) == N`), and the totality property:
```python
@given(provenance=trigger_provenance_st(), resolution_variant=resolution_variant_st())
def test_decide_is_total_over_provenance_and_resolution(provenance, resolution_variant) -> None:
    # act/assert: decide(...) returns a SupervisorDecision instance for every pair — never raises, never None
    ...
```
### Green — make it pass
Implement `decide()` as the minimal `match` cascade described in the outline. No helper classes — a single pure function. Resolution-variant detection is a plain `isinstance`/`match`; the `Both` branch is a `zip` over the three input tuples into `PluginWorkItem`s.
### Refactor — clean up
Add a module docstring and a precise return-type annotation. Confirm `assert_never` import is from `typing`. Confirm no `import` of `redis`, `pathlib`, `codegenie.plugins.events`, or any shell module — `decide()` takes already-computed inputs only (edge cases 1, 3 from `§Edge cases` are exercised through the inputs, not by `decide()` doing work). Keep cyclomatic complexity ≤ 8.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/supervisor/decide.py` | New — the pure `decide()` core. |
| `tests/unit/supervisor/test_decide.py` | New — exhaustive variant tests + the totality property test. |
| `tests/unit/supervisor/test_decide_purity.py` | New — the functional-core purity AST test. |
| `src/codegenie/supervisor/__init__.py` | Possibly — only if `decide` joins the bounded public surface. |

## Out of scope
- The three graph nodes and `run_supervisor` — S6-02.
- Actually resolving the `Both` task classes / building per-resolution Bundles — S6-03 feeds `decide()` the tuples; `decide()` only maps them.
- The subgraph handoff of the `Dispatched` payload — S6-04.
- The static append-before-transition AST test — S6-05.

## Notes for the implementer
- `decide()` is pure by contract — if you find yourself importing `EventLog` or `redis`, you have pulled node responsibility into the core. The nodes emit events; `decide()` only computes.
- The `BothProvenanceTrigger` `>= 2` validator already lives on the model (S2-03) — `decide()` does not re-check it; a degenerate `Both` never reaches here (edge case 14).
- `assert_never` is non-negotiable per ADR-0002 — it is what makes a future fourth `SupervisorDecision` variant a loud `mypy` failure rather than a silent drop.
- The totality property test is the ADR-0002-mandated guard; mirror the existing `tests/unit/plugins/test_resolver_property.py` Hypothesis strategy style rather than inventing a new one.
- Keep `decide()` out of `__all__` unless the bounded ≤24-name surface budget genuinely needs it exported — the graph (S6-02) is the public entry point.
