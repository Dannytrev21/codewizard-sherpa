# ADR-0007: Bench-invocation tagging on `SandboxCostEntry` via env-var contract — amends Phase 5 ADR-0010

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** cost-ledger · phase-5-amendment · phase-13-handoff · cross-phase-boundary
**Related:** [ADR-0001](0001-rubric-execution-isolation-via-subprocess.md), [Phase 5 ADR-0010](../../05-sandbox-trust-gates/ADRs/0010-cost-sandbox-run-ledger-schema.md), [Phase 5 ADR-0016](../../05-sandbox-trust-gates/ADRs/0016-per-task-class-eval-harness-as-trust-evidence.md), [production ADR-0024](../../../production/adrs/0024-cost-observability-end-to-end.md)

## Context

Phase 5 ships `SandboxCostEntry` ([Phase 5 ADR-0010](../../05-sandbox-trust-gates/ADRs/0010-cost-sandbox-run-ledger-schema.md)): one ledger entry per `GateRunner` attempt at `.codegenie/cost/sandbox.jsonl`, consumed by Phase 13's ROI dashboard ([production ADR-0024](../../../production/adrs/0024-cost-observability-end-to-end.md)). When the eval harness runs nightly, every bench case invokes the SUT, which invokes Phase 5's sandbox, which writes a `SandboxCostEntry`. From Phase 13's perspective, those bench-driven entries look identical to production workflow-driven entries — the `workflow_id` field carries whatever the SUT thinks it is, and there is no marker distinguishing "real PR work" from "evaluation work."

The critic identified the load-bearing consequence (critic roadmap-level #6): Phase 13's ROI math (`$ spent on autonomous PR work / $ value delivered`) would silently double-count bench costs as production costs. Nightly bench runs at the `≥ 10 cases × 2 task classes × cost/case` scale would inflate the denominator daily, while delivering zero PR value — Phase 13's KPIs read systematically wrong. The harness can't fix this in its own ledger because Phase 13's reader consumes `SandboxCostEntry`, not a parallel stream — a separate harness ledger would require Phase 13 to learn two formats.

The constraint is "additive only" — Phase 5 is shipped, Phase 13 is not designed, and any field added now must default to a value Phase 13 can ignore safely. `SandboxCostEntry` has `model_config = ConfigDict(extra="forbid", frozen=True)` ([Phase 5 ADR-0014](../../05-sandbox-trust-gates/ADRs/0014-objectivesignals-extra-forbid-static-introspection.md)) — extending the model is an ADR-anchored amendment, not a runtime extension. The amendment shape that satisfies "additive only" is one optional boolean field with `default=False`, plus an env-var read in `CostEmitter` that flips the flag when set.

## Options considered

- **Silent / no tagging** (all three input designs). Bench-driven entries land in `.codegenie/cost/sandbox.jsonl` indistinguishable from production. Phase 13 silently inflates costs. Rejected — violates [CLAUDE.md §"Fail loud"](../../../CLAUDE.md) for cost observability.
- **Separate ledger** (`.codegenie/cost/bench.jsonl`). Phase 13 reads two streams. Adds load-bearing coupling for Phase 13 to be aware of a phase that did not exist when [Phase 5 ADR-0010](../../05-sandbox-trust-gates/ADRs/0010-cost-sandbox-run-ledger-schema.md) was written. Reader complexity grows linearly with future "tagged ledger" use cases.
- **Workflow-ID prefix convention** (`workflow_id = "bench:..."`). Hacky; couples ledger consumers to a string-prefix protocol. Easy to mis-parse; no `extra="forbid"` enforcement.
- **Env-var contract + additive `bench_invocation: bool = False` field on `SandboxCostEntry`** (synthesized). The eval runner sets `CODEGENIE_BENCH_INVOCATION_TAG = f"bench:{run_started_iso}:{task_class}:{case_id}"` before each `SUT(case)` call and clears it after. Phase 5's `CostEmitter` reads the env var; when present, sets `SandboxCostEntry.workflow_id` to the tag and `bench_invocation=True`. Phase 13 filters `WHERE bench_invocation IS NOT TRUE`. Cleanly additive, fail-loud (default `False` is unambiguous), reader-trivial.

## Decision

Phase 5's `SandboxCostEntry` gains an additive field `bench_invocation: bool = False`. Phase 5's `CostEmitter` is amended to read `os.environ.get("CODEGENIE_BENCH_INVOCATION_TAG")`; when present, it sets `SandboxCostEntry.workflow_id` to the tag value and `bench_invocation=True`. `src/codegenie/eval/cost_tag.py` exposes a `tag_invocation(task_class, case_id, run_started_iso)` context manager that sets and clears the env var around each `SUT(case)` call. The Phase 5 ADR-0010 amendment ships as part of Phase 6.5 work; Phase 13 (when designed) filters `WHERE bench_invocation IS NOT TRUE` for ROI math.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 13's ROI math is filterable from day one — no retroactive cost-reclassification ever needed | Phase 5 ADR-0010 ships an amendment (additive); cross-phase boundary requires Phase 5 CODEOWNERS review of the schema diff |
| The contract is data: one optional field, default `False`; Phase 13's reader treats absent or `False` identically | `extra="forbid"` means every `SandboxCostEntry` consumer must update its schema *before* Phase 6.5 ships any bench-tagged entries; the order of operations matters |
| Env-var injection is process-local and clears cleanly — `tag_invocation(...)` is a context manager with deterministic teardown | Forgetting `__exit__` (or an unhandled exception inside the with-block) would leak the tag to the next sandbox invocation; the context manager is the load-bearing discipline |
| `workflow_id = f"bench:{run_started_iso}:{task_class}:{case_id}"` produces a queryable, human-readable identifier per case — operators can join bench cost back to specific cases | The string-prefix convention duplicates structural information already in `bench_invocation: True`; readers must understand both signals carry the same meaning |
| Graceful degradation: if Phase 5 hasn't landed the additive field yet (in-flight implementation), the env var is silently ignored — `SandboxCostEntry` just doesn't include the field | "Silently ignored" is a fail-open posture for the duration of the amendment-landing gap; `tests/unit/test_cost_ledger_tagging.py` is the structural check once Phase 5 ships |
| Symmetric to [ADR-0005](0005-cassette-canary-seed-parameterization.md)'s Phase 4 amendment pattern — the same shape, different phase boundary | Two cross-phase additive amendments shipping in Phase 6.5 (Phase 4 canary seed, Phase 5 cost tagging) compound review surface |

## Consequences

- **Phase 5 ADR-0010 is amended** (additive): `SandboxCostEntry` gains `bench_invocation: bool = False`. The amendment is drafted as part of Phase 6.5 work and merged via the same cross-phase discipline as [ADR-0005](0005-cassette-canary-seed-parameterization.md)'s Phase 4 amendment.
- Phase 5's `CostEmitter` (`src/codegenie/sandbox/cost.py`) gains the env-var read: when `CODEGENIE_BENCH_INVOCATION_TAG` is set, `workflow_id` becomes the tag value and `bench_invocation=True`.
- `src/codegenie/eval/cost_tag.py` exposes:
  ```python
  def tag_invocation(task_class: str, case_id: str, run_started_iso: str) -> ContextManager[None]: ...
  ```
- The eval runner wraps every `system_under_test(case)` call in `with tag_invocation(...):`.
- Phase 13's ROI consumer (`production ADR-0024` consumer) filters `WHERE bench_invocation IS NOT TRUE` for production-ROI math; reads `WHERE bench_invocation IS TRUE` for "cost of nightly eval" line item.
- `BenchRunReport.total_cost_usd` continues to aggregate `BenchScore.cost_usd` for the harness's own reporting; the cost ledger is the *cross-phase* contract, the report is the harness's *self-report*. The two should agree but live on different substrates.
- `tests/unit/test_cost_ledger_tagging.py`: when `CODEGENIE_BENCH_INVOCATION_TAG` is set, an emitted `SandboxCostEntry` carries `bench_invocation == True` and `workflow_id == tag`. Without the env var, both fields revert to default.
- `tests/adv/test_cost_ledger_pollution.py`: a bench-tagged entry is filterable; a production-tagged entry is not. Mirrors the discipline of [Phase 5 ADR-0014](../../05-sandbox-trust-gates/ADRs/0014-objectivesignals-extra-forbid-static-introspection.md)'s adversarial enforcement.
- Phase 6.5's `phase-arch-design.md §Edge cases #15` ties Phase 13's correct consumption of this field as part of the cross-phase invariant; Phase 13 owns the consumer filter — the producer side (this ADR) makes the filter possible.
- The env-var name `CODEGENIE_BENCH_INVOCATION_TAG` is namespaced for cross-phase clarity; adding new tags (e.g., `CODEGENIE_DEV_INVOCATION_TAG` for operator exploratory runs) follows the same shape via additive ADR amendment.

## Reversibility

**Medium.** Reverting Phase 5's `bench_invocation` field is a Pydantic edit — but every bench-driven `SandboxCostEntry` already written under the new shape would lose the filter, and Phase 13's ROI math would retroactively double-count history. The amendment is one-way *additive*; downgrade requires either filling in synthetic `bench_invocation=False` for legitimate past production entries (which lies) or accepting historical inaccuracy. Forward evolution (adding `dev_invocation`, `regression_test_invocation`) is the realistic direction. The env-var contract is mechanically reversible (delete the read, delete the wrapper) at any time before Phase 13 ships its filter — once Phase 13 ships, removal breaks Phase 13's ROI dashboard.

## Evidence / sources

- [final-design.md §Bench-run cost-ledger tagging](../final-design.md#bench-run-cost-ledger-tagging)
- [final-design.md §Synthesis ledger row "Cost-ledger pollution"](../final-design.md#conflict-resolution-table)
- [final-design.md §Departures from all three inputs #4](../final-design.md#departures-from-all-three-inputs)
- [final-design.md §Risks #5](../final-design.md#risks-top-5)
- [phase-arch-design.md §Component design — `cost_tag.py`](../phase-arch-design.md#srccodegenieevalcost_tagpy)
- [phase-arch-design.md §Edge cases #15](../phase-arch-design.md#edge-cases)
- [phase-arch-design.md §Testing strategy — Adversarial tests](../phase-arch-design.md#adversarial-tests)
- [critique.md §Roadmap-level critiques #1](../critique.md#roadmap-level-critiques) (Phase 7's "no edits to existing code" invariant — this ADR amends Phase 5, not Phase 7's purview)
- [Phase 5 ADR-0010](../../05-sandbox-trust-gates/ADRs/0010-cost-sandbox-run-ledger-schema.md) — the schema this ADR amends
- [production ADR-0024](../../../production/adrs/0024-cost-observability-end-to-end.md) — the cost-observability commitment this filter preserves
