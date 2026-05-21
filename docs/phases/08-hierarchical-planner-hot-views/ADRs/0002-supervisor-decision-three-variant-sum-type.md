# ADR-0002: SupervisorDecision is a three-variant sum type including MultiPluginDispatch

**Status:** Accepted
**Date:** 2026-05-21
**Tags:** Tagged union / sum type · make-illegal-states-unrepresentable · multi-plugin coordination
**Related:** ADR-0001, ADR-0008, [production ADR-0042](../../../production/adrs/0042-multi-plugin-coordination-for-both-workflows.md), [production ADR-0031](../../../production/adrs/0031-plugin-architecture.md), [production ADR-0038](../../../production/adrs/0038-vulnerability-provenance-attribution.md)

## Context

The Supervisor's job is to resolve a plugin, build a Context Bundle, route the work, and dispatch into a subgraph. There are three structurally distinct outcomes: a single plugin is dispatched; *no* concrete plugin matches and the work escalates to a human; or the trigger's provenance is `Both` and *several* plugins must run as one coordinated parent workflow.

[production ADR-0042](../../../production/adrs/0042-multi-plugin-coordination-for-both-workflows.md) is `Accepted` and §Consequences states explicitly: "Phase 8 must model parent workflow plus plugin work items." [phase-arch-design.md §Scenario 3](../phase-arch-design.md#scenario-3--adr-0042-multi-plugin-both-workflow) and the roadmap's Phase 10 entry ("the `Both` case escalates as a multi-plugin coordination candidate to Phase 8's Planner") confirm Phase 8 is where the `Both` shape must land. Yet — per [critique.md §Where do all three quietly agree on something questionable](../critique.md#where-do-all-three-quietly-agree-on-something-questionable) — *all three* lens designs modeled the dispatch outcome as a two-variant `Dispatched | EscalatedToHITL` union, omitting the `Accepted` ADR entirely. The synthesis [departs from all three inputs](../final-design.md#departures-from-all-three-inputs) to correct this.

## Options considered

- **Option A — Two-variant union `Dispatched | EscalatedToHITL`; handle `Both` later.** The shape all three lenses shipped. **Pattern:** Tagged union — but an *incomplete* one. It forces Phase 10 (the first `Both` producer) to retrofit parent/child modeling into a shipped, single-plugin-only Supervisor — a non-additive edit, exactly what `production/design.md §2` commitment §5 forbids.
- **Option B — Three-variant union `Dispatched | MultiPluginDispatch | EscalatedToHITL`.** `MultiPluginDispatch(parent_workflow_id, work_items)` carries a tuple of `PluginWorkItem`, one per resolved task class. **Pattern:** Tagged union / make-illegal-states-unrepresentable — `match` + `assert_never` forces every dispatch site to handle the `Both` case.
- **Option C — A boolean `is_multi` flag plus a side `work_items` field on `Dispatched`.** **Pattern:** boolean-flag anti-pattern (toolkit "flag on sight") — a `Dispatched` with `is_multi=True` and a populated `work_items` is an illegal-state-shaped value; nothing stops a `Dispatched` with `is_multi=False` *and* `work_items` set.

## Decision

`SupervisorDecision` is a closed Pydantic discriminated union of **three variants** — `Dispatched | MultiPluginDispatch | EscalatedToHITL` — discriminated on a `kind` `Literal`. `MultiPluginDispatch` carries `parent_workflow_id: WorkflowId` and `work_items: tuple[PluginWorkItem, ...]` (length ≥ 2, one per resolved implicated task class). Every dispatch site handles the union with `match` + `assert_never`. This is the **Tagged union / sum type** pattern applied so the ADR-0042 `Both` case is impossible to silently drop.

## Tradeoffs

| Gain | Cost |
|---|---|
| ADR-0042's "Phase 8 must model parent workflow plus plugin work items" is satisfied structurally, not by a TODO | Phase 8 carries a variant whose deep sequencing logic is not exercised until Phase 10 produces real `Both` candidates |
| `match` + `assert_never` makes a new dispatch consumer that forgets `MultiPluginDispatch` a type error, not a runtime surprise | Three variants are more surface to test than two — every `decide()` test must cover all three |
| Phase 10 becomes an *additive consumer* of `MultiPluginDispatch`, not a non-additive retrofitter of the Supervisor | The `work_items` tuple + `parent_workflow_id` are now a frozen contract Phase 10/Phase 9 build on — widening them later is a contract change |
| "No plugin", "this is `Both`", "single dispatch" are each a distinct, named, frozen value — no illegal combination is constructible | A degenerate `Both` (one task class) must be caught explicitly — handled by a `field_validator(>= 2)` on `BothProvenanceTrigger` (edge case 14) |

## Pattern fit

The toolkit's "Tagged union / sum type for state" entry names exactly this: "state machines, failure-mode taxonomies, promotion verdicts" — model the discriminator as a sum type, never as booleans. The Supervisor's outcome *is* a small state machine with three terminal states. Option C's `is_multi` flag is the toolkit's "booleans for state" failure mode — it "allows illegal combinations." The three-variant union plus `match`/`assert_never` is the pattern's textbook application: the compiler enforces exhaustive handling, so a future dispatch consumer cannot quietly ignore the `Both` case.

## Consequences

- `MultiPluginDispatch` must keep `parent_workflow_id` and `work_items` as the stable extension points; Phase 10's deep cross-PR sequencing (ordering, shared evidence, status rollup) hangs off them additively.
- Every `match` over `SupervisorDecision` ends in `assert_never(decision)` — adding a fourth variant later is a compiler-policed sweep, not a silent gap.
- A `BothProvenanceTrigger` with fewer than two `implicated_task_classes` raises a Pydantic `ValidationError` at trigger construction — a malformed `Both` never reaches `decide()`.
- The contract-snapshot test on `SupervisorDecision` calcifies the three-variant shape; a fourth variant or a field change is a loud reviewable diff.
- Phase 9's Temporal parent/child workflow model maps directly onto `MultiPluginDispatch` — `parent_workflow_id` is the parent-workflow handle.
- `decide()` tests must be exhaustive over the three `SupervisorDecision` variants × the two `TriggerProvenance` variants; a Hypothesis totality property asserts `decide()` is total over all `(provenance, resolution-variant)` pairs.

## Reversibility

**Low.** `SupervisorDecision` is a `[contract]`-tagged cross-phase surface — Phase 9 (Temporal dispatch) and Phase 10 (the first `Both` producer) both consume it. Removing or renaming `MultiPluginDispatch` after Phase 10 ships would break a downstream consumer. *Adding* a fourth variant is cheap (the compiler finds every `match`); *removing* the three-variant commitment is not. The shape is deliberately frozen early — it is earned by the `Accepted` ADR-0042 that names Phase 8.

## Evidence / sources

- ../final-design.md §Departures from all three inputs, item 1 — `MultiPluginDispatch` as a first-class variant
- ../final-design.md §Shared blind spots considered — "Multi-plugin `Both` coordination"
- ../phase-arch-design.md §Data model — `SupervisorDecision` discriminated union
- ../phase-arch-design.md §Scenario 3 — multi-plugin `Both` workflow
- ../critique.md §Cross-design observations — "all three treat multi-plugin `Both`… as out of scope"
- ../../../production/adrs/0042-multi-plugin-coordination-for-both-workflows.md §Consequences
- `design-patterns-toolkit.md` §Tagged union / sum type for state
