# ADR-0026: ROI KPI model — what we measure and how

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** roi · metrics
**Related:** ADR-0024, ADR-0009

## Context

If cost is observable end-to-end (ADR-0024) but no one defines the headline ratios that turn cost into ROI, the system has telemetry without insight. The metrics that matter need to be decided up front so they can be instrumented from day one.

ROI for an autonomous migration system has multiple plausible framings: cost-saving (vs. manual labor), risk-reduction (CVEs eliminated), throughput (migrations per quarter), quality (post-merge incidents avoided). Different stakeholders care about different framings.

## Options considered

- **Single KPI.** Pick one (e.g., cost per CVE eliminated) and report it. Cleanest narrative, but blind to other dimensions.
- **Long list of metrics.** Report 20+ measurements. Comprehensive, unscannable.
- **Two headline ratios + a small set of supporting metrics.** Lead with the two metrics that matter most to leadership; back them with diagnostic detail.

## Decision

**Two headline ROI ratios, computed weekly:**

- **Cost per successful PR** = (sum of system cost over the period) ÷ (PRs merged over the period)
- **Cost per CVE eliminated** = (sum of system cost over the period) ÷ (severity-weighted CVE reductions over the period)

**Supporting metrics for diagnosis** (also weekly):

| Metric | What it tells us |
|---|---|
| Mean Time to Remediate (MTTR) for new disclosures | Speed of response to new CVEs in watched repos |
| Engineer-hours saved per migration | Labor displaced vs. the manual-baseline estimate |
| Portfolio coverage trajectory | % of eligible repos migrated, by quarter |
| Merge rate | PRs opened ÷ PRs merged — quality of agent proposals |
| Post-merge incident rate | % of merged PRs that caused production incidents |
| Reviewer override rate | % of PRs where humans rejected or substantially modified the plan |
| Knowledge-graph reuse rate | % of LLM invocations that used a solved example as few-shot — measures compounding savings (ADR-0011) |
| Cost breakdown by source | LLM tokens / sandbox / reviewer time / infra — where money is actually going |
| Cap-hit rate | % of workflows that hit 80% warning or 100% halt — calibration signal for ADR-0025 |

## Tradeoffs

| Gain | Cost |
|---|---|
| Two ratios that fit on one slide — leadership can scan in seconds | Two ratios alone hide important nuance (e.g., "PR merged" doesn't mean "no regression") |
| Supporting metrics provide diagnostic depth | Dashboard surface area is non-trivial; needs ownership |
| KPIs are computable from the cost ledger + Stage 7 Learning outputs — no separate pipeline | Severity-weighted CVE reduction requires a weighting scheme (deferred refinement) |
| Knowledge-graph reuse rate makes the compounding-savings story (ADR-0011) measurable | Some metrics (engineer-hours saved) require manual baseline calibration up front |

## Consequences

- Stage 7 Learning writes per-merge cost outcomes to the cost ledger; the dashboard reads from there.
- The ROI dashboard is operated by the platform team; the engineering org receives a weekly digest with the two headline ratios + top-line supporting metrics.
- The severity-weighted CVE reduction formula uses an initial weighting of `Critical=10, High=5, Medium=2, Low=1` — these can be refined per ADR amendment once calibration data exists.
- "Engineer-hours saved" requires a one-time calibration: for each task class, estimate the manual baseline (e.g., distroless migration of a typical Node service: 4–8 engineer-hours). Stored as configuration; revisable.
- The dashboard surfaces both **absolute** numbers (this week's PRs merged, this week's CVEs eliminated) and the **ratios** (cost per PR, cost per CVE).

## Reversibility

**Low cost.** Adding or removing metrics is a dashboard config change. Changing the headline ratios is a leadership-alignment conversation, not a technical migration.

## Evidence / sources

- `../design.md §3.3` (ROI metrics subsection)
- `../design.md §5` (ROI KPI surfacing in AgentOps)
- ADR-0024 (cost observability commitment)
- ADR-0011 (recipe-first planning — the compounding-savings story)
- ADR-0009 (humans always merge — makes "merge rate" a meaningful KPI)
