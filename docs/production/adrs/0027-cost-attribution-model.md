# ADR-0027: Cost attribution model — mapping costs to workflows, repos, and task classes

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** cost · attribution
**Related:** ADR-0024, ADR-0025, ADR-0026

## Context

Cost observability (ADR-0024) is only useful if costs can be attributed to specific workflows, repos, and task classes. The attribution model determines which questions are answerable from the cost ledger:

- "How much did this migration cost?"
- "Which repos are most expensive to migrate?"
- "What task class has the worst cost-per-PR ratio?"
- "Did the knowledge-graph reuse reduce per-migration cost over time?"

Attribution gets thorny when stages share resources. The Probe Coordinator runs continuously across all watched repos (ADR-0006); how is its cost attributed? A microVM warmed for one workflow may be reused for another; how is the warm-up amortized? Shared infrastructure (Temporal cluster, MCP servers) has fixed cost that has to be allocated.

## Options considered

- **Workflow-local attribution only.** Each workflow pays for what it directly causes. Shared / continuous work (gather, infra) is unattributed overhead. Simple; underestimates true cost per workflow.
- **Full marginal attribution.** Continuous gather costs are amortized across the workflows that consume them in a window; shared infra is allocated proportionally. Most accurate; complex.
- **Tiered: direct + amortized + overhead.** Direct costs (LLM calls, sandbox runs uniquely for one workflow) attributed exactly. Continuous costs (gather, pre-rendering) amortized across consuming workflows. Fixed overhead (Temporal cluster, MCP infra) tracked at portfolio level, not per workflow.

## Decision

**Tiered attribution model:**

1. **Direct costs** — attributed exactly to the workflow that triggered them:
   - LLM API calls (tokens × per-token cost by model)
   - Sandbox microVM runs (microVM-seconds × rate)
   - Workflow-specific MCP reads beyond the pre-rendered hot views
   - Reviewer time on the workflow's PR (Stage 6)

2. **Continuous costs** — amortized across consuming workflows:
   - Continuous gather (ADR-0006) cost is attributed per-gather, then divided across the workflows that read that gather's `RepoContext` within its freshness window
   - Pre-rendered Redis hot views are similarly amortized
   - Knowledge graph indexing cost (write side) is amortized across reads in a window

3. **Portfolio overhead** — tracked at the platform level, not per workflow:
   - Temporal cluster running cost
   - Postgres / Redis / vector DB baseline cost
   - MCP server pod baseline cost (compute, not query work)
   - Observability stack

Portfolio overhead is reported separately on the dashboard as a fixed-cost line item. The two headline ratios (ADR-0026) use direct + amortized; overhead is shown alongside but not divided into them.

## Tradeoffs

| Gain | Cost |
|---|---|
| Per-workflow cost reflects true marginal cost — comparing workflows is fair | Amortization windows need definition (default: rolling 24h for continuous gather; revisable) |
| Portfolio overhead is visible as fixed cost — leadership can see the "table stakes" line | Some costs (e.g., a probe that fired for one workflow but cached for 50) are messy to attribute |
| Knowledge-graph compounding savings (ADR-0011) show up as decreasing amortized cost per workflow over time | Cross-workflow attribution math means a single workflow's reported cost can change retroactively as its gather is reused |
| Three tiers map cleanly to the cost ledger schema | Edge cases (e.g., a sandbox warmed for workflow A reused by workflow B before cooling) need decision rules |

## Consequences

- The cost ledger schema has three classes of entries: `direct`, `amortized`, `overhead`.
- Amortized entries are written initially with a "pending" attribution; finalized once the amortization window closes.
- The dashboard surfaces all three: per-workflow direct + amortized for the "cost per merged PR" ratio; overhead as a separate fixed-cost line.
- Compounding savings via the knowledge graph (ADR-0011) become measurable: as more solved examples accumulate, per-workflow amortized RAG retrieval cost goes up (more storage) but per-workflow LLM cost goes down (more few-shot hits). Net per-workflow cost should trend down over time — this is a key ROI signal.
- Per-repo cost rolls up from per-workflow cost: same workflow-id keys, grouped by repo.
- Per-task-class cost rolls up similarly: useful for tuning per-task-class caps (ADR-0025).

## Reversibility

**Medium.** Adjusting the amortization rules (e.g., changing the gather amortization window) is config; the cost ledger's reported numbers shift accordingly. Adding a new tier (e.g., "shared between specific workflow pairs") is a schema change with backfill implications.

## Evidence / sources

- `../design.md §3.3` (Cost telemetry instrumentation table — aggregation keys per source)
- `../design.md §8.10` (Cost view — ledger as central aggregation)
- ADR-0024 (cost observability commitment)
- ADR-0026 (KPI model — depends on attribution being well-defined)
