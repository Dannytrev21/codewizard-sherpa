# codewizard-sherpa

**An autonomous agentic system that opens pull requests to modify code across an organization's repositories at portfolio scale.**

Deterministic where it can be. Probabilistic only where it must. Humans always merge.

<div class="grid cards" markdown>

-   :material-rocket-launch: **Get started**

    ---

    Clone the repo, run `make bootstrap`, gather your first `RepoContext` in five minutes.

    [→ Get started](get-started.md)

-   :material-sitemap: **Architecture**

    ---

    The Temporal-orchestrated, layered-hybrid design — read top-down or drill into ADRs and phase designs.

    [→ Architecture overview](architecture.md)

-   :material-map: **Roadmap**

    ---

    17 phases from local bullet tracer to multi-tenant production. Phases 0–2 are shipping; phases 3–7 are designed.

    [→ Roadmap](roadmap.md)

</div>

## What is this?

Most refactoring and vulnerability-remediation work in an organization is **mechanical**: upgrade this package, replace this base image, rewrite these call sites for an API change. The mechanical work is also where human engineers waste the most time — too repetitive to enjoy, too risky to delegate to a script that doesn't understand context.

codewizard-sherpa is built to **do the mechanical work itself, end-to-end, across many repos at once**, and stop at the point a human reviewer would actually add value: the pull-request review. It scans repos, gathers structured context, plans changes recipe-first and LLM-last, applies them in microVM sandboxes, validates them against objective signals, and opens PRs with full evidence bundles. **It never merges.**

The system is designed around the empirical finding that AI agents are "safer builders, risky maintainers" — they break things during refactors at higher rates than during net-new code. So **structural changes go through recipes (OpenRewrite, AST manipulation), and the LLM is reserved for judgment calls only**.

## Headline shape

The production system is a **Temporal-durable workflow envelope** wrapping a three-layer orchestrator:

1. **Hierarchical Planner** (LangGraph Supervisor) — reads intent, dispatches to a subgraph
2. **SHERPA-style State Machine** (the worker subgraph) — Pydantic state ledger; nodes never call nodes
3. **Trust-Aware Verification** (conditional edges) — microVM sandbox + objective signals decide every transition

LLMs appear only at the **leaves**, called via the Agents SDK for narrow judgment calls. Everything else — routing, gating, control flow, cost accounting — is deterministic.

[→ Read the architecture overview](architecture.md){ .md-button }

## Status

**As of 2026-05:**

| What | Status |
|---|---|
| Phase 0 — Bullet tracer foundations | ✅ Shipped |
| Phase 1 — Layer A (Node) context gathering | 🚧 In progress |
| Phase 2 — Layers B–G context gathering | 🚧 In progress |
| Phases 3–7 — Designed; implementation pending plugin-architecture redesign | 📐 Designs complete |
| Phases 8–16 — Roadmap stubs awaiting design | 📋 Planned |

The implementation focus today is the **local CLI POC** (`codegenie gather`). The probe contract it implements is the same one the production service will use ([ADR-0007](production/adrs/0007-probe-contract-preserved-poc-to-service.md)) — drift here would propagate everywhere.

[→ Full roadmap](roadmap.md){ .md-button }

## The architectural commitments

Every subsystem in codewizard-sherpa honors nine load-bearing constraints. The two most important:

!!! quote "Commitment §1 — No LLM in the gather pipeline"
    Probes are deterministic; same inputs always produce same outputs. This is what makes the `RepoContext` artifact reproducible, cacheable, and auditable. Enforced in CI by `import-linter` ([ADR-0005](production/adrs/0005-no-llm-in-gather-pipeline.md)).

!!! quote "Commitment §8 — Humans always merge"
    Autonomy ends at PR creation. This is the consistent finding from every published autonomous-migration study. The system can spend hours of LLM time and days of sandbox compute building a PR; merging is always a human decision ([ADR-0009](production/adrs/0009-humans-always-merge.md)).

[→ All nine commitments + their ADRs](architecture.md#load-bearing-architectural-commitments)

## How to read further

This site is structured for progressive disclosure:

| If you have… | Read |
|---|---|
| 5 minutes | This page |
| 30 minutes | This page + [Architecture overview](architecture.md) |
| 2 hours | Add the [Production design](production/design.md) |
| A weekend | Add the [ADR index](production/adrs/README.md) (36 numbered decisions) and one or two phase [final-designs](roadmap.md) |
| Want to contribute | [Contributing guide](contributing.md) |
