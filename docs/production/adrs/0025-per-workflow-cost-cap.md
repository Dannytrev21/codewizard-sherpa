# ADR-0025: Per-workflow cost cap as a hard guard

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** cost · safety
**Related:** ADR-0024, ADR-0014

## Context

Even with cost-favorable architecture (deterministic gather, recipe-first planning, knowledge-graph reuse), individual workflows can spiral. A worker that hits a hard problem may retry, fall through to LLM-from-scratch, retry again, escalate to error-triage, retry the new plan — token spend can grow non-linearly even with the 3-retry cap (ADR-0014) on individual nodes.

The retry cap bounds spend per node. Per-workflow caps bound spend across all nodes of one workflow. Both are needed.

## Options considered

- **No per-workflow cap.** Trust the per-node retry cap. Acceptable if workflows are short; risky if they have many nodes.
- **Soft cap (warning at 100%, no enforcement).** Operators see overruns but can't stop them automatically. Better than nothing.
- **Hard cap with override.** 80% triggers a soft warning to operators; 100% triggers a hard halt unless an explicit `--allow-overrun` annotation was set at workflow start.
- **Hard cap without override.** No escape valve. Simpler; brittle on rare-but-legitimate cases.

## Decision

**Hard per-workflow cost cap with explicit override:**

- Each workflow declares a token + compute budget at start. Defaults differ by task class (vulnerability patches get a higher cap; convenience migrations get a lower cap).
- Temporal workflow state tracks cumulative spend deterministically across all Activities.
- At **80% of cap**: soft warning emitted to operators; workflow continues.
- At **100% of cap**: Supervisor short-circuits via `interrupt()`, logs the budget overrun, escalates to human review.
- The `--allow-overrun` annotation can be set on the workflow start signal for known-expensive cases (e.g., a multi-repo monorepo migration). Use is logged for audit.

## Tradeoffs

| Gain | Cost |
|---|---|
| Hard upper bound on per-workflow cost — no silent runaway | Cap calibration is initially guesswork; needs tuning |
| Operators see warning at 80% — can intervene before the cap hits | False positives (legitimate work that hits the cap) escalate to humans, adding review load |
| Per-task-class defaults capture "vulnerability patches are worth more than convenience migrations" intuition | Cap-by-task-class adds configuration surface area |
| Override exists for rare-but-real expensive cases — escape valve prevents brittle behavior | Override usage must be policed; could become the lazy escape for poor estimates |

## Consequences

- The Budget Enforcer is implemented as Temporal middleware that wraps Activity execution. After each Activity completes, it reads the ledger and either advances or short-circuits.
- The Supervisor is the agent of the short-circuit — it issues `interrupt()` with a state annotation explaining the budget cause.
- Cap values are deferred decisions per task class — initial defaults are conservative; ADR amendment paths cover retuning after production data.
- The 80% warning triggers an automated message to a `#codewizard-budget-warnings` channel; the 100% halt opens an audit ticket.
- This cap is independent of the per-node retry cap (ADR-0014); both can fire.

## Reversibility

**Low cost.** Cap thresholds and defaults are configuration. The Budget Enforcer middleware can be disabled (in test environments) without code changes. The enforcement *behavior* (halt on overrun) is the load-bearing piece; the *threshold* is not.

## Evidence / sources

- `../design.md §3.3` (Per-workflow budget enforcement subsection)
- `../design.md §5` (Cost controls — Per-workflow budget cap)
- ADR-0024 (cost observability commitment)
- ADR-0014 (per-node retry cap — complementary)
