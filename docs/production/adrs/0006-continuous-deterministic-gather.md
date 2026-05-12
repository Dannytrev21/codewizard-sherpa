# ADR-0006: Continuous deterministic gather — event-triggered, always-fresh

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** gather · runtime
**Related:** ADR-0005, ADR-0013

## Context

The gather layer can run in two operational modes: **on-demand** (invoked when a workflow starts; one-shot per workflow) or **continuous** (runs against every watched repo whenever something changes, keeping `RepoContext` warm in the cache).

On-demand is simpler to operate but puts gather on the critical path of every workflow — a 3–6 minute cold gather delays every Stage 2. Continuous gather is more operationally complex but makes Stage 2 a cache-hit (seconds) in steady state.

This decision is enabled by ADR-0005 (no LLM in gather): without that, continuous would be cost-prohibitive at portfolio scale.

## Options considered

- **On-demand only.** Gather fires at Stage 2 of each workflow. Simple ops, slow workflows. Every CVE event waits 3–6 minutes for fresh context.
- **Continuous.** Multiple trigger sources (cron, push webhook, PR opened webhook, CVE feed event, manual CLI) fire incremental gathers. Stage 2 reads warm cache.
- **Hybrid.** Continuous for "watched" repos (those known to need ongoing migration), on-demand for ad-hoc. Operational complexity of both modes.

## Decision

**Continuous gather** with five trigger sources:

- **Cron** — nightly scan across watched repos
- **Repo push webhook** — every push to the default branch (or watched branch)
- **PR opened / synchronized webhook** — fresh gather against the PR HEAD
- **CVE feed event** — new vulnerability published against any package in the SBOM
- **Manual CLI** — `codegenie gather` for local-dev

The Continuous Gather Dispatcher fans in from these sources to the Probe Coordinator. Content-addressed cache (filesystem in POC; object store + Postgres metadata index in service) makes incremental re-runs cheap.

## Tradeoffs

| Gain | Cost |
|---|---|
| `RepoContext` is always fresh when a workflow fires — Stage 2 is seconds, not minutes | Continuous webhook infrastructure must run reliably |
| Continuous CVE-event awareness — agent can react to disclosure as fast as the feed delivers | More compute spend than on-demand (mitigated: most re-runs are cache hits) |
| Cursor-published cache reuse rate >90% in steady state (per `../../context.md`) | Cache invalidation bugs surface as silent staleness — `IndexHealthProbe` is critical |
| Pre-rendered hot views (ADR-0013) become naturally always-fresh | Operational complexity: 4 trigger paths to monitor + cron + manual |

## Consequences

- Three freshness modes (`fresh-on-trigger`, `cached-only`, `force-refresh`) become first-class CLI/API parameters.
- `Probes` declare `declared_inputs` (file globs / external resources). The Coordinator diffs current state against the last gather; unchanged-input probes hit cache, changed-input probes re-run.
- The Discovery Scanner (Stage 0) becomes a *separate* concern from the continuous gather. Discovery adds repos to the watched-list; continuous gather keeps watched-repo context warm.
- Stage 2 in the workflow pipeline becomes "ensure fresh, then read" — almost always a cache hit.
- Cold gather: 3–6 minutes. Warm: 20–40 seconds. Incremental: under 10 seconds.

## Reversibility

**Medium.** Reverting to on-demand-only is operationally simple (turn off webhook listeners, drop the Dispatcher); the cost is reverting to slow Stage 2 cold-starts. The Probe Coordinator and probe contract don't change, so the gather code itself is mode-agnostic.

## Evidence / sources

- `../design.md §3.2` (continuous-gather model with trigger fan-in diagram)
- `../../context.md §"Caching, freshness, and incremental gathers"` (the freshness-mode model and Cursor cache-reuse data)
- `../../context.md §"What runs the gatherer"` (cold/warm/incremental timing figures)
- `../../localv2.md §8` (POC-side caching — same model, filesystem-backed)
