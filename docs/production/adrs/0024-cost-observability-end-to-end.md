# ADR-0024: Cost is observable end-to-end as a first-class commitment

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** cost · observability
**Related:** ADR-0025, ADR-0026, ADR-0027

## Context

An autonomous agentic system running at portfolio scale (hundreds to thousands of migrations per year) can become economically unviable quickly without cost discipline. The dominant variable costs are LLM API spend and sandbox compute; the dominant fixed costs are platform infrastructure (Temporal, Postgres, Redis, vector DB, MCP servers).

Most published agentic systems treat cost as an out-of-band operational concern — measured by the bill at the end of the month, optimized reactively. The empirical pattern is that those systems either become quietly unaffordable or get throttled in ways that mask underlying problems.

This decision is whether cost is a first-class load-bearing commitment in the architecture, with structural enforcement and measurement, or whether it's left as operational hygiene to handle after the fact.

## Options considered

- **Cost is operational, not architectural.** Track total spend; rely on engineering judgment to keep it bounded. Easy to start; predictably bad at scale.
- **Per-component cost monitoring without integration.** Each component (LLM caller, sandbox runner, etc.) reports its own metrics independently. Better than nothing; doesn't roll up per workflow, so attribution is impossible.
- **Cost as a first-class architectural commitment.** Every Activity emits cost to a shared ledger keyed by workflow. The ledger feeds both enforcement and ROI calculation. Cost becomes a state-machine input alongside objective signals.

## Decision

**Cost is a load-bearing architectural commitment (§2.9).** Every Activity in the system implements a cost-emission interface. Costs aggregate to a per-workflow ledger. The ledger feeds three downstream consumers: the per-workflow Budget Enforcer (ADR-0025), the ROI dashboard (ADR-0026), and the Trust-Aware Gate as a state-machine input (§4.6).

## Tradeoffs

| Gain | Cost |
|---|---|
| Cost is attributable per workflow, per stage, per task class | Every Activity must implement the cost-emission interface — instrumentation overhead |
| Budget enforcement is structural — workflows cannot silently overspend | One more cross-cutting concern engineers must internalize |
| ROI is calculable from real data, not modeled estimates | Telemetry storage + dashboard infrastructure to operate |
| Cost-aware gate decisions become possible (cheaper recipe path when budget is near cap) | Cost-emission interface evolution requires coordinated updates across Activities |
| Architectural pressure to keep the system cost-favorable (recipe-first planning, deterministic gather) is reinforced | Some Activities (e.g., probe coordinator) have negligible per-invocation cost but still pay the instrumentation overhead |

## Consequences

- A cost-emission interface (e.g., `emit_cost(workflow_id, stage, source, cost_units)`) is part of the platform substrate, imported by every Activity.
- The cost ledger is keyed by `workflow_id` with secondary keys for stage, source, and time. Storage backend deferred (ADR-0027 covers attribution; storage is part of the telemetry stack — likely the same Postgres or a TSDB).
- §3.3 and §8.10 in `../design.md` make this concrete: instrumentation table, cost view diagram, ROI metrics.
- The "headline cost ratios" (cost per merged PR, cost per CVE eliminated) are computed weekly from the ledger.

## Reversibility

**Low cost to relax** the commitment after the fact (turn off emissions, abandon enforcement). **High cost** to retrofit the commitment onto a system that didn't ship with it from day one — would require touching every Activity. Best to commit early.

## Evidence / sources

- `../design.md §2.9` (commitment)
- `../design.md §3.3` (cost & ROI architectural framing)
- `../design.md §5` (cost controls in the AgentOps chapter)
- `../design.md §8.10` (Cost view diagram)
