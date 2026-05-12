# ADR-0003: Temporal as the durable workflow substrate

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** platform · durability
**Related:** ADR-0001, ADR-0016

## Context

Per-repo workflows in this system span hours to days. A typical workflow proceeds through 7 stages, includes one or more multi-minute sandbox builds, and pauses for human review at Stage 6 — that pause can last days. The orchestrator must survive process restarts, retry transient failures (LLM 429s, CI flakes, registry timeouts), and resume exactly where it left off without losing state.

Most general-purpose orchestrators were designed for batch processing (hours of compute, then done) or stream processing (continuous low-latency flows). Neither fits "single workflow that takes a week of real time, mostly sleeping."

## Options considered

- **Temporal.** Durable execution: workflow code is deterministic, side-effects go to Activities, state rehydrates on worker restart. Signals are first-class. Workflow-as-code in Python or TypeScript. Production precedent: OpenAI Codex, Replit coding agent.
- **Airflow.** Batch-oriented. Sensor pattern can fake long pauses but is brittle. Not designed for multi-day suspensions.
- **AWS Step Functions.** AWS-locked. State machine via JSON DSL. Less ergonomic for code-authoring. Acceptable if everything else is AWS-native.
- **Prefect.** Closer in shape to Temporal. Smaller ecosystem, weaker durability semantics.
- **Dagster.** Asset/data-pipeline-shaped. Strong for ELT. Awkward for "branching workflow with human signals."
- **Argo Workflows.** Kubernetes-native YAML DAGs. Too rigid for stateful LLM-loop code.
- **Home-rolled.** Build state persistence, retry, signals, and replay from scratch. Best estimate: rebuild ~70% of Temporal, poorly.

## Decision

Adopt **Temporal** as the outer workflow substrate. Every per-repo migration is a Temporal workflow. Probes, gate evaluations, sandbox runs, and LLM calls are Temporal Activities. LangGraph subgraphs execute as Activity payloads.

## Tradeoffs

| Gain | Cost |
|---|---|
| Durable execution across process restarts | Operational complexity (Temporal cluster + workers to run) |
| Multi-day pauses via signals are first-class | New engineers must learn Temporal's workflow/activity model |
| Retry policies + backoff for free on LLM transient failures | Workflow code must be deterministic (no random IDs, no clock reads outside Activities) |
| Workflow-as-code in Python — no proprietary DSL | Self-hosted Temporal has real ops cost; Temporal Cloud has subscription cost |
| Production precedent at scale (OpenAI Codex, Replit) | One more piece of infrastructure to monitor |

## Consequences

- The codebase organizes Temporal workflows in `platform/temporal/`. Activity definitions live alongside the layer they wrap (gather Activities under `codegenie/`, gate Activities under `trust/`, etc.).
- Determinism rule for workflow code: any non-deterministic call (LLM, clock, random, network) must go through an Activity.
- Operations: Temporal cluster + Postgres state store + worker pods. Reasonable starting size is 3 server pods, 5–10 worker pods, autoscaling on queue depth.
- Cost ceilings (ADR-0014's retry caps, workflow-level token budgets) are enforced via workflow-level checks; Temporal does not provide these natively.

## Reversibility

**Medium.** Temporal workflow code is portable to other durable-execution engines (Prefect, custom) in principle, but the durability contract is the load-bearing property — losing it would require rebuilding signal handling, replay, and retry logic. Activities are easier to port than workflows.

## Evidence / sources

- `../design.md §4.1` (outer envelope description)
- `../design.md §4.4` (stage-to-layer mapping — Stage 0 and Stage 6 are Temporal-owned)
- `../../auto-agent-design.md §6` — Temporal rationale and alternatives table
- Temporal AI documentation — Codex and Replit case studies
- Operational precedent: Replit's migration blog post
