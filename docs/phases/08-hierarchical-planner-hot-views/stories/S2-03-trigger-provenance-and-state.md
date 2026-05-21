# Story S2-03 — Declare the TriggerProvenance sum type and SupervisorState

**Step:** Step 2 — Declare the hot-view data model and the Supervisor/routing sum types
**Status:** Ready
**Effort:** S
**Depends on:** S2-01
**ADRs honored:** ADR-0002

## Context
A workflow entering the Supervisor carries a *provenance*: it is either a single task class, or the ADR-0042 `Both` case where several task classes were implicated by the same trigger. This story lands `TriggerProvenance` as a closed two-variant discriminated union and `SupervisorState` — the frozen per-workflow state the three Supervisor nodes advance by `model_copy(update=...)`. It is foundational, contracts-first work: the `provenance` discriminator drives the single-vs-multi branch in `decide()` (Step 6), and a `BothProvenanceTrigger` with one task class must be impossible to construct — edge case 14 — so the malformed `Both` never reaches `decide()`.

## References — where to look
- **Architecture:**
  - `../phase-arch-design.md §Data model` — the `[contract] trigger provenance` block: `SingleTaskTrigger`, `BothProvenanceTrigger` (`implicated_task_classes: tuple[TaskClassId, ...]` length `>= 2`), `TriggerProvenance = Annotated[..., Field(discriminator="kind")]`.
  - `../phase-arch-design.md §C1 — Supervisor` — the `SupervisorState` frozen-model public-interface block (`workflow_id`, `task_class`, `repo_id`, `provenance`, `resolution`, `bundle`, `decision`, all later fields `| None = None`).
  - `../phase-arch-design.md §Edge cases` — edge case 14: a `Both` trigger naming only one task class fails at construction with a `ValidationError`.
  - `../phase-arch-design.md §Control flow` — D2: `SingleTaskTrigger` → single resolve/build/route; `BothProvenanceTrigger` → resolve per `implicated_task_class`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0002-supervisor-decision-three-variant-sum-type.md` — ADR-0002 — §Consequences: "A `BothProvenanceTrigger` with fewer than two `implicated_task_classes` raises a Pydantic `ValidationError` at trigger construction."
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0038-vulnerability-provenance-attribution.md` — the provenance-attribution lineage behind `BothProvenanceTrigger`.
  - `../../../production/adrs/0042-multi-plugin-coordination-for-both-workflows.md` — the `Both` case.
- **Source design:**
  - `../final-design.md §Departures from all three inputs` — item 1 lineage (the `Both` shape).
- **Existing code (if any):**
  - `src/codegenie/supervisor/state.py` — created by S2-01; this story adds `SingleTaskTrigger`, `BothProvenanceTrigger`, `TriggerProvenance`, `SupervisorState` to the *same* module.
  - `src/codegenie/types/identifiers.py` — `WorkflowId`, `TaskClassId`, `RepoId` (S1-01) newtypes.
  - `src/codegenie/plugins/subgraph.py:65` — the frozen-model `ConfigDict` convention; `SupervisorState` mirrors `SubgraphState`'s `model_copy`-advance discipline.
  - `src/codegenie/plugins/resolver.py` — `PluginResolution` union (`ConcreteResolution | UniversalFallbackResolution`), the type of `SupervisorState.resolution`.
  - `src/codegenie/plugins/bundle.py` — the `Bundle` model, the type of `SupervisorState.bundle`.

## Goal
Declare the `SingleTaskTrigger | BothProvenanceTrigger` `TriggerProvenance` discriminated union (with the `>= 2` validator on `implicated_task_classes`) and the frozen `SupervisorState` model, so the Supervisor graph has a typed per-workflow state and a closed provenance discriminator.

## Acceptance criteria
- [ ] `codegenie/supervisor/state.py` declares `SingleTaskTrigger`, `BothProvenanceTrigger`, and `TriggerProvenance = Annotated[SingleTaskTrigger | BothProvenanceTrigger, Field(discriminator="kind")]`.
- [ ] `BothProvenanceTrigger.implicated_task_classes` rejects a tuple of length `< 2` with a Pydantic `ValidationError` (edge case 14).
- [ ] `SupervisorState` is a frozen model with `workflow_id: WorkflowId`, `task_class: TaskClassId`, `repo_id: RepoId`, `provenance: TriggerProvenance`, and `resolution: PluginResolution | None = None`, `bundle: Bundle | None = None`, `decision: SupervisorDecision | None = None`.
- [ ] `SupervisorState.model_copy(update={"resolution": ...})` produces a new frozen instance — in-place mutation of any field raises `ValidationError` (frozen).
- [ ] The new public names are listed in `codegenie/supervisor/__init__.py.__all__`; the running ≤ 24 public-surface count is noted in the attempt log.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest` all pass on the touched files.

## Implementation outline
1. In `codegenie/supervisor/state.py` (created by S2-01), add `SingleTaskTrigger` (just a `kind: Literal["single"]` discriminator) and `BothProvenanceTrigger` (`kind: Literal["both"]`, `implicated_task_classes`).
2. Add the `>= 2` constraint to `implicated_task_classes` — `Annotated[tuple[TaskClassId, ...], Field(min_length=2)]` preferred; a `field_validator` is the fallback.
3. Declare the `TriggerProvenance` `Annotated` discriminated union.
4. Declare `SupervisorState` frozen, with the three required fields and the three `| None = None` accumulator fields. Set `arbitrary_types_allowed=True` if `Bundle` requires it.
5. Export the four new names via `__init__.py.__all__`.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file path: `tests/unit/supervisor/test_trigger_provenance.py`

```python
def test_both_trigger_rejects_single_task_class() -> None:
    # WHY: edge case 14 — a "Both" naming one task class is a degenerate
    # provenance; ADR-0002 mandates it fail at construction so a malformed
    # Both can never reach decide() and produce a one-item MultiPluginDispatch.
    with pytest.raises(ValidationError):
        BothProvenanceTrigger(implicated_task_classes=(TaskClassId("vuln-remediation"),))

def test_trigger_provenance_discriminates_on_kind() -> None:
    # WHY: the provenance discriminator drives the single-vs-multi branch in
    # decide(); it must round-trip by the "kind" tag.
    adapter = TypeAdapter(TriggerProvenance)
    assert isinstance(adapter.validate_python({"kind": "single"}), SingleTaskTrigger)

def test_supervisor_state_advances_by_model_copy() -> None:
    # WHY: SupervisorState is frozen — the three nodes advance it with
    # model_copy(update=...), never in-place mutation (mirrors SubgraphState).
    s0 = SupervisorState(workflow_id=..., task_class=..., repo_id=..., provenance=SingleTaskTrigger())
    s1 = s0.model_copy(update={"resolution": some_resolution})
    assert s0.resolution is None and s1.resolution is some_resolution
    with pytest.raises(ValidationError):
        s0.bundle = some_bundle
```

### Green — make it pass
Declare the two trigger variants, the `>= 2` constraint, the `TriggerProvenance` union, and `SupervisorState`. Smallest shape — no node logic (Step 6), no `decide()` (S6-01).

### Refactor — clean up
Docstrings naming the ADR-0002 lineage and edge case 14. Confirm `SupervisorState` is frozen and the accumulator fields default to `None`. Add a module comment that `SupervisorState` is advanced by `model_copy(update=...)` only (mirrors `plugins/subgraph.py`'s `SubgraphState`). Verify a `match` over `TriggerProvenance` ending in `assert_never` type-checks.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/supervisor/state.py` | Adds `SingleTaskTrigger`, `BothProvenanceTrigger`, `TriggerProvenance`, `SupervisorState`. |
| `src/codegenie/supervisor/__init__.py` | `__all__` gains the four new names. |
| `tests/unit/supervisor/test_trigger_provenance.py` | Red tests: `>= 2` validator, discriminator round-trip, frozen `model_copy`. |

## Out of scope
- The `SupervisorDecision` union and `PluginWorkItem` — S2-01 (imported here as the type of `SupervisorState.decision`).
- The pure `decide()` function that branches on `provenance` — Step 6 (S6-01).
- The Supervisor graph and the three nodes that advance `SupervisorState` — Step 6 (S6-02).
- Any logic that *constructs* a `BothProvenanceTrigger` from a real trigger — Phase 10 is the first real `Both` producer; Phase 8 only ships the shape.

## Notes for the implementer
- The `>= 2` validator on `implicated_task_classes` mirrors S2-01's `work_items` validator exactly — keep the two consistent (same `min_length=2` idiom, same failure mode). ADR-0002 names both.
- `SupervisorState.resolution: PluginResolution | None` — `PluginResolution` is the *reused* `ConcreteResolution | UniversalFallbackResolution` union from `codegenie.plugins.resolver`; do not re-declare it (the architect's §Patterns rejected a second `PluginResolution` as a name collision).
- `SupervisorState` mirrors `SubgraphState` (`plugins/subgraph.py`) — frozen, `model_copy`-advanced. Read that file before writing this one (Rule 8) so the discipline matches.
- `SingleTaskTrigger` carries no data beyond `kind` — that is correct; it is a nullary variant. Do not pad it with speculative fields.
- `extra="forbid"` on every model — an unexpected field on a trigger or on `SupervisorState` must be a loud `ValidationError`.
