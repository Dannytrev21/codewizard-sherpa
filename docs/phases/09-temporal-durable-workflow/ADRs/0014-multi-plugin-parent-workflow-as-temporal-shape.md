# ADR-0014: `MultiPluginParentWorkflow` as a real Temporal parent/child workflow shape

**Status:** Accepted
**Date:** 2026-05-23
**Tags:** sum-type · parent-child-workflow · ADR-0042-rendering
**Related:** [ADR-0007](0007-two-task-queue-partitioning-and-expansion-by-addition.md), [production ADR-0042](../../../production/adrs/0042-multi-plugin-coordination-for-both-workflows.md)

## Context

[Production ADR-0042](../../../production/adrs/0042-multi-plugin-coordination-for-both-workflows.md) names the `Both`-case multi-plugin coordination decision: when a repo's `vuln.provenance` matches multiple plugins (e.g., both `vulnerability-remediation--node--npm` and `vulnerability-remediation--python--pip`), the system must orchestrate multiple per-plugin workflows under a parent coordinator. Phase 8's `SupervisorDecision = … | MultiPluginDispatch` carries the typed shape forward, but Phase 8 itself does not run multiple workflows — it makes the *decision* that multi-plugin dispatch is needed.

None of the three parallel designs ([P], [B], [S]) designed `MultiPluginParentWorkflow` — all three treated multi-plugin as a Phase-10 concern. The critic-roadmap review flagged this as a missed opportunity: Phase 10 will need the parent/child workflow shape *and* the typed `ParentResult` aggregation; if Phase 9 ships only the per-plugin workflow class, Phase 10 must add a new workflow class plus modify Phase-9's bridge — non-additive.

The shape options: (a) defer entirely to Phase 10 (additive cost paid then); (b) ship the typed `MultiPluginDispatch` input model only (no parent workflow class; Phase 10 lands the class additively); (c) ship the full parent/child workflow shape in Phase 9 with `"independent"` coordination semantics, with `"all_or_nothing"` and `"best_effort"` raising `NotImplementedError` until Phase 10 lands them.

## Options considered

- **Defer entirely to Phase 10.** Phase 9 ships only `VulnRemediationWorkflow`; Phase 10 adds `MultiPluginParentWorkflow`. **Pattern:** YAGNI. Phase 10 also pays the bridge update cost.
- **Typed input model only.** Phase 9 ships `MultiPluginDispatch` Pydantic model + `ParentResult` sum type, but no workflow class. **Pattern:** typed-shape-only. Asymmetric — typed shape exists with no consumer; arguably an ADR-0043 violation (decoration without use).
- **Full parent/child workflow class with `coordination_policy = "independent"` only.** Phase 9 ships `MultiPluginParentWorkflow.run(MultiPluginDispatch) -> ParentResult` using `workflow.execute_child_workflow` for `n` `VulnRemediationWorkflow` children in parallel. The `MultiPluginDispatch.coordination_policy: Literal["independent", "all_or_nothing", "best_effort"]` field defaults to `"independent"`; the other two raise `NotImplementedError` at the workflow body (visible in `temporal-ui`, not a silent stub). **Pattern:** real implementation of the cheapest variant; additive growth for the others.

## Decision

Phase 9 ships `MultiPluginParentWorkflow` as a real `@workflow.defn`-decorated parent workflow that uses `workflow.execute_child_workflow` to fan out one `VulnRemediationWorkflow` per `PluginWorkItem`. Phase 9 implements `coordination_policy = "independent"` only; the other two variants raise `NotImplementedError` at the workflow body (fail-loud, surfaced in `temporal-ui`). The `ParentResult` sum type (`AllMerged | SomeMerged | AllFailed`) carries the aggregation. **Pattern: real implementation of the cheapest variant; additive growth.**

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 10's `Both`-case workflow lands on existing machinery — Phase 10 PR is `coordination_policy="all_or_nothing"` implementation, not a new workflow class | Two workflow classes in Phase 9 (`VulnRemediationWorkflow` + `MultiPluginParentWorkflow`), not one |
| `ParentResult` sum type forces exhaustive handling of multi-child outcomes at compile time | `SomeMerged` semantics question (auto-emit `HumanReviewRequested` for unmerged children?) is open ([phase-arch-design.md §Open questions #5](../phase-arch-design.md#open-questions-deferred-to-implementation)); the typed shape carries the variant ahead of the decision |
| The `NotImplementedError` at the workflow body is fail-loud — visible to the operator in `temporal-ui` — *not* a silent stub | A `NotImplementedError` raises questions: is this an ADR-0043 violation? The synthesis answer is no — it is a typed precondition on a workflow input, fails at *use* time with a typed error visible in `temporal-ui`, not a "future capability reservation" |
| Phase-8's `MultiPluginDispatch` decision variant has a real consumer from Phase 9 day-one | Test surface widens — both workflow classes need their own happy-path tests, replay-determinism fixtures, and durability tests |
| `ADR-0042`'s commitment is rendered as code, not just docs | Phase 10's first PR must implement at least one of `all_or_nothing` / `best_effort` to use any real `Both`-case workflow |

## Pattern fit

Real implementation of the cheapest variant + additive growth is the codebase pattern for "the typed shape is needed now; the full behavior is needed later". The toolkit's `design-patterns-toolkit.md §Variant-driven evolution` argues that sum types with un-implemented variants are *not* the same as silent stubs — the un-implemented variant fails at use time with a typed error pointing at the missing implementation, which is loud, audited, and easy to extend additively. ADR-0043's "no silent edits" rule prohibits silent stubs (`pass`, `return None`, `NotImplementedError` in a function that's *called* by existing code paths); the parent-workflow `NotImplementedError` is in a code path that is only entered when a future contributor passes `coordination_policy=…` for which there is no implementation — fail-loud by design.

## Consequences

- `codegenie.durable.workflows.multi_plugin_parent.MultiPluginParentWorkflow` is the new workflow class.
- `MultiPluginDispatch` Pydantic input model carries `coordination_policy: Literal["independent", "all_or_nothing", "best_effort"]` with default `"independent"`.
- `ParentResult = AllMerged | SomeMerged | AllFailed` sum type lives in `codegenie.durable.workflows.multi_plugin_parent.types`.
- `workflow.execute_child_workflow` is the dispatch mechanism; children share a `parent_workflow_id` correlation key.
- The two unimplemented coordination policies are *not* registered as registry entries — they raise `NotImplementedError("see Phase 10")` at the workflow body's `match` arm. `temporal-ui` shows the failure; operators see the typed error.
- `tests/workflows/test_multi_plugin_parent_workflow.py` tests `"independent"` happy paths (2 children, all merged → `AllMerged`; 2 children, 1 failed → `SomeMerged`); `"all_or_nothing"` raises; `"best_effort"` raises.
- Phase 10's first PR for either policy implementation is an additive change to the `match` arm + new tests; no edit to existing tests.
- The `SomeMerged.unmerged_children → auto-emit HumanReviewRequested?` open question lives in [phase-arch-design.md §Open questions #5](../phase-arch-design.md#open-questions-deferred-to-implementation); Phase 10 decides.

## Reversibility

**Medium.** Removing the parent-workflow class would mean reverting Phase 10's `Both`-case integration — non-trivial. Keeping the class but collapsing the sum type to a single variant is easy but loses the typed evolution path.

## Evidence / sources

- [`../phase-arch-design.md §C1 — Workflow definitions`](../phase-arch-design.md#c1--workflow-definitions-codegeniedurableworkflows)
- [`../phase-arch-design.md §Gap 2 — MultiPluginParentWorkflow sibling-coordination semantics`](../phase-arch-design.md#gap-2-multipluginparentworkflow-sibling-coordination-semantics-are-under-specified)
- [`../phase-arch-design.md §Integration with Phase 10 — MultiPluginParentWorkflow`](../phase-arch-design.md#integration-with-phase-10-stage-0-discovery--stage-1-assessment)
- [`../final-design.md §Departures from all three inputs #5`](../final-design.md)
- [`../final-design.md §Exit-criteria checklist — MultiPluginDispatch (ADR-0042) modeled as a real Temporal workflow`](../final-design.md)
- [production ADR-0042](../../../production/adrs/0042-multi-plugin-coordination-for-both-workflows.md)
- [production ADR-0043](../../../production/adrs/0043-extension-by-addition-means-no-silent-edits.md) — the "no silent edits" rule this decision conforms to
