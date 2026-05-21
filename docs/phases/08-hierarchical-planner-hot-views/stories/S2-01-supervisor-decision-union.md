# Story S2-01 — Declare the SupervisorDecision three-variant sum type

**Step:** Step 2 — Declare the hot-view data model and the Supervisor/routing sum types
**Status:** Ready
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** ADR-0002

## Context
The Supervisor's job ends in exactly three structurally distinct outcomes — a single plugin dispatched, several plugins dispatched as one coordinated parent workflow (the ADR-0042 `Both` case), or escalation to a human. This story lands that outcome as a closed Pydantic discriminated union *before any consumer* (`decide()` in Step 6 `match`es over it). It is foundational, contracts-first work: nothing the Supervisor produces can be typed until this union exists, and modelling the `Both` case as a first-class variant now is what keeps Phase 10 an additive consumer rather than a non-additive retrofitter.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Data model` — the `[contract] Supervisor output sum type` block: `PluginWorkItem`, `Dispatched`, `MultiPluginDispatch`, `EscalatedToHITL`, `SupervisorDecision = Annotated[..., Field(discriminator="kind")]`.
  - `../phase-arch-design.md §Logical view` — the `SupervisorDecision <|-- Dispatched / MultiPluginDispatch / EscalatedToHITL` class diagram; field lists per variant.
  - `../phase-arch-design.md §C1 — Supervisor` — `decide()` signature consumes this union; `match` + `assert_never` is the dispatch discipline.
  - `../phase-arch-design.md §Scenario 3` — the multi-plugin `Both` flow that produces `MultiPluginDispatch`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0002-supervisor-decision-three-variant-sum-type.md` — ADR-0002 — three variants, discriminated on `kind`; `MultiPluginDispatch.work_items` length `>= 2`; every `match` ends in `assert_never`.
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0042-multi-plugin-coordination-for-both-workflows.md` — §Consequences: "Phase 8 must model parent workflow plus plugin work items."
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — newtype-for-domain-IDs discipline; no raw `str` for `PluginId` / `WorkflowId`.
- **Source design:**
  - `../final-design.md §Departures from all three inputs` — item 1: `MultiPluginDispatch` as a first-class variant (the three inputs shipped a two-variant union).
- **Existing code (if any):**
  - `src/codegenie/probes/layer_c/_cve_models.py`, `src/codegenie/indices/freshness.py` — existing `Field(discriminator=...)` discriminated-union precedents to mirror exactly.
  - `src/codegenie/plugins/subgraph.py:65` — `SubgraphState` `model_config = ConfigDict(frozen=True, extra="forbid", ...)` — the frozen-model convention.
  - `src/codegenie/types/identifiers.py` — `PluginId`, `WorkflowId`, `RepoId` (added by S1-01) newtypes.
  - `src/codegenie/plugins/bundle.py` — the shipped `Bundle` model (reused, unchanged, as a field type).

## Goal
Declare the frozen `Dispatched | MultiPluginDispatch | EscalatedToHITL` discriminated `SupervisorDecision` union plus `PluginWorkItem` in `codegenie/supervisor/state.py`, so every later Supervisor consumer has a closed, exhaustively-matchable outcome type.

## Acceptance criteria
- [ ] `codegenie/supervisor/state.py` declares `PluginWorkItem`, `Dispatched`, `MultiPluginDispatch`, `EscalatedToHITL`, and `SupervisorDecision = Annotated[Dispatched | MultiPluginDispatch | EscalatedToHITL, Field(discriminator="kind")]`.
- [ ] Each variant is a frozen Pydantic model (`model_config = ConfigDict(frozen=True, extra="forbid")`, `arbitrary_types_allowed=True` only where a `Bundle` field requires it) carrying a `kind: Literal[...]` discriminator with a default.
- [ ] `MultiPluginDispatch.work_items` rejects a tuple of length `< 2` with a Pydantic `ValidationError` (a `field_validator` or `min_length` constraint enforcing `>= 2`).
- [ ] A `match` statement over `SupervisorDecision` ending in `assert_never` type-checks under `mypy --strict` (a small `match`-and-`assert_never` test or doctest proves exhaustiveness compiles).
- [ ] The four new names are listed in `codegenie/supervisor/__init__.py.__all__` and the running public-surface count (≤ 24 across the four new packages) is noted in the attempt log.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. Create the `codegenie/supervisor/` package directory with `__init__.py` and `state.py`.
2. In `state.py`, declare `PluginWorkItem(plugin: PluginId, bundle: Bundle, route: RouteDecision)` frozen. Import `RouteDecision` from `codegenie.planner.model` — if S2-04 has not landed yet, gate the import behind `TYPE_CHECKING` or sequence after S2-04; the manifest DAG places S2-04 after S2-01, so use a forward reference (`route: "RouteDecision"`) and a `TYPE_CHECKING` import to avoid a hard dependency.
3. Declare the three variants with `kind` `Literal` discriminators and the field lists from §Data model.
4. Add the `>= 2` constraint to `MultiPluginDispatch.work_items` (prefer `Annotated[tuple[PluginWorkItem, ...], Field(min_length=2)]`; a `field_validator` is acceptable if `min_length` does not apply cleanly to a homogeneous tuple).
5. Declare the `SupervisorDecision` `Annotated` discriminated union.
6. Export the four names via `__init__.py.__all__`.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/supervisor/test_supervisor_decision.py`

One red test per behavior:

```python
def test_multi_plugin_dispatch_rejects_single_work_item() -> None:
    # WHY: a degenerate "Both" (one plugin) is an illegal state — ADR-0002
    # mandates >= 2 work_items so a one-item MultiPluginDispatch can never be built.
    with pytest.raises(ValidationError):
        MultiPluginDispatch(parent_workflow_id=..., work_items=(one_work_item,))

def test_supervisor_decision_discriminates_on_kind() -> None:
    # WHY: the union must round-trip by the "kind" tag so no dispatch site
    # can silently mis-parse a variant.
    adapter = TypeAdapter(SupervisorDecision)
    assert isinstance(adapter.validate_python({"kind": "escalated_to_hitl", ...}), EscalatedToHITL)

def test_dispatched_is_frozen() -> None:
    # WHY: a SupervisorDecision is an immutable record — mutation after decide()
    # would desync the audit log from the dispatched payload.
    d = Dispatched(plugin=..., version="0.1.0", bundle=..., route=...)
    with pytest.raises(ValidationError):
        d.version = "9.9.9"
```

### Green — make it pass
Declare the four models with `frozen=True, extra="forbid"`, the `kind` `Literal` discriminators, the `min_length=2` constraint on `work_items`, and the `Annotated[..., Field(discriminator="kind")]` union alias. Smallest shape that satisfies the red asserts — no `decide()` logic (Step 6), no graph wiring (Step 6).

### Refactor — clean up
Docstrings on each public model naming the `[contract]` status and the ADR-0002 lineage. Confirm `arbitrary_types_allowed` is set only where `Bundle` (a non-Pydantic-friendly field) demands it. Add a module-level comment that every `match` over `SupervisorDecision` must end in `assert_never` (ADR-0002 §Consequences). Verify `mypy --strict` accepts an exhaustive `match` and would flag a missing variant.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/supervisor/__init__.py` | New package; `__all__` exports the four new names. |
| `src/codegenie/supervisor/state.py` | Declares `PluginWorkItem`, `Dispatched`, `MultiPluginDispatch`, `EscalatedToHITL`, `SupervisorDecision`. |
| `tests/unit/supervisor/test_supervisor_decision.py` | Red tests: `>= 2` validator, discriminator round-trip, frozen. |

## Out of scope
- `SupervisorState` and the `TriggerProvenance` union — S2-03.
- `RouteDecision` / `PlanningRoute` — S2-04 (imported here as a forward reference only).
- The pure `decide()` function and any `match` logic — Step 6 (S6-01).
- The contract-snapshot test that calcifies the JSON shape — Step 6 / Step 7 hardening; this story only needs the round-trip test.

## Notes for the implementer
- ADR-0002 explicitly rejects the `is_multi` boolean-flag shape (Option C). Do **not** add any boolean to `Dispatched` — the three outcomes are variants, never flags.
- `min_length=2` on a `tuple[PluginWorkItem, ...]` must produce a `ValidationError`, not silently truncate — test the failure path, not just the happy path (Rule 9).
- `PluginWorkItem.route` is a forward reference to `RouteDecision` (S2-04). Use `from __future__ import annotations` + a `TYPE_CHECKING` import; do not create a circular import by importing `codegenie.planner` at module scope from `codegenie.supervisor`.
- The bounded public surface is ≤ 24 names across all four new packages — record this story's contribution (4 names) in the attempt log so the running total stays visible.
- `extra="forbid"` is mandatory — an unexpected field on a decision variant must be a loud `ValidationError`, not a silently-absorbed key.
