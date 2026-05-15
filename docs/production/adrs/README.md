# Architecture Decision Records (ADRs) — Production Design

Each file in this directory captures one architectural decision: the context that motivated it, the alternatives considered, what we decided, what tradeoffs we accepted, what becomes harder later, and how reversible the choice is.

The format is **lightweight Nygard-style** (per Michael Nygard's [original 2011 essay](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)) with extensions for tradeoffs and reversibility. Every ADR has:

| Section | What it captures |
|---|---|
| **Status** | Proposed · Accepted · Deferred · Superseded |
| **Context** | The situation, forces, and constraints that triggered the decision |
| **Options considered** | The alternatives evaluated, briefly |
| **Decision** | What we chose, stated unambiguously |
| **Tradeoffs** | What we gain and what we give up — both columns |
| **Consequences** | What becomes easier, what becomes harder, what's now constrained downstream |
| **Reversibility** | How costly it is to undo this decision later, and what would need to change |
| **Evidence / sources** | The references this decision is grounded in |

## Conventions

- **Filenames** are `NNNN-kebab-case-title.md` with zero-padded four-digit numbers. Numbers are assigned at write-time and never reused, even if an ADR is superseded.
- **Numbers are sequential and immutable.** A superseded ADR keeps its number; the new ADR gets the next number and links back.
- **Status transitions are append-only.** When you supersede an ADR, edit both the old and new ADRs to cross-link, but don't delete history.
- **Each ADR is self-contained.** A reader should be able to understand the decision from the ADR alone, without reading the main `design.md`.

---

## Index — Accepted decisions

| # | Title | Tags |
|---|---|---|
| [0001](0001-layered-hybrid-orchestration.md) | Layered Hybrid orchestration — three layers, not one framework | orchestration · architecture |
| [0002](0002-langgraph-as-runtime-sherpa-as-discipline.md) | LangGraph as runtime, SHERPA as discipline — composition over alternatives | orchestration · runtime |
| [0003](0003-temporal-as-workflow-substrate.md) | Temporal as the durable workflow substrate | platform · durability |
| [0004](0004-python-as-harness-language.md) | Python as the harness language across POC and service | language · ecosystem |
| [0005](0005-no-llm-in-gather-pipeline.md) | No LLM in the gather pipeline — determinism end-to-end | gather · determinism |
| [0006](0006-continuous-deterministic-gather.md) | Continuous deterministic gather — event-triggered, always-fresh | gather · runtime |
| [0007](0007-probe-contract-preserved-poc-to-service.md) | Probe contract preserved unchanged from POC to service | contract · stability |
| [0008](0008-objective-signal-trust-score.md) | Trust score uses objective signals only — no LLM self-confidence | trust · safety |
| [0009](0009-humans-always-merge.md) | Humans always merge — no autonomous merge to production | safety · governance |
| [0010](0010-seven-stage-pipeline-shape.md) | Seven-stage pipeline shape (Discovery → Learning) | pipeline · structure |
| [0011](0011-recipe-first-rag-llm-fallback-planning.md) | Recipe-first → RAG → LLM-fallback planning order | planning · cost |
| [0012](0012-microvm-sandbox-for-trust-gates.md) | microVM sandbox isolation for trust gates | trust · sandbox |
| [0013](0013-pre-rendered-redis-hot-views.md) | Pre-rendered Redis hot views for agent context | latency · ergonomics |
| [0014](0014-three-retry-default-per-gate.md) | Three-retry default per gate transition | policy · escalation |
| [0024](0024-cost-observability-end-to-end.md) | Cost is observable end-to-end as a first-class commitment | cost · observability |
| [0025](0025-per-workflow-cost-cap.md) | Per-workflow cost cap as a hard guard | cost · safety |
| [0026](0026-roi-kpi-model.md) | ROI KPI model — what we measure and how | roi · metrics |
| [0027](0027-cost-attribution-model.md) | Cost attribution model — mapping costs to workflows, repos, and task classes | cost · attribution |
| [0028](0028-task-class-introduction-order.md) | Task class introduction order — vulnerability remediation before migration | task-class · sequencing |
| [0029](0029-task-class-context-manifests.md) | Task-Class Context Manifests — context selection as data | context · task-class · skills |
| [0030](0030-graph-aware-context-queries.md) | Graph-aware context queries — dep graph + tree-sitter + SCIP power TCCMs | context · graph-analysis · scip |
| [0031](0031-plugin-architecture.md) | Plugin architecture — granular (task × language × build-tool) units of work | architecture · plugins · extension-by-addition |
| [0032](0032-language-search-adapters.md) | Language search adapters — bridging generic queries to language-specific indexers | adapters · code-search · scip · plugins |
| [0033](0033-domain-modeling-discipline.md) | Domain modeling discipline — newtype + smart constructor + sum type + illegal-states-unrepresentable | typing · correctness · discipline |
| [0034](0034-event-sourcing-canonical-primitive.md) | Event sourcing as canonical primitive for agent runs | event-sourcing · audit · replay · observability |
| [0035](0035-operator-portal-architecture.md) | Operator portal — read-only-first, event-log-projected, GitHub-OAuth, with visibility/authority separated | ui · observability · audit · ops · phase-13.5 |
| [0036](0036-plugin-task-enablement-dual-source-policy.md) | Plugin/task enablement — dual-source policy (operator Postgres + repo `codegenie.yaml`), OR resolution, fail-closed, stage-aware | policy · kill-switch · config-as-code · audit · phase-13.5 |

## Index — Deferred decisions

These are committed to the architecture as questions; the decision itself awaits evidence. Each ADR documents the default behavior until the decision is made and what evidence would resolve it.

| # | Title | Tags |
|---|---|---|
| [0015](0015-trust-score-threshold-calibration.md) | Trust-score threshold calibration | trust · calibration |
| [0016](0016-checkpointer-backend.md) | Checkpointer backend (Postgres vs Redis) | platform · storage |
| [0017](0017-knowledge-graph-backend.md) | Knowledge-graph backend (Qdrant / pgvector / Neo4j) | platform · storage |
| [0018](0018-supervisor-pure-routing-vs-llm.md) | Hierarchical Planner: pure routing vs LLM-driven | orchestration · cost |
| [0019](0019-sandbox-stack.md) | Sandbox stack (Firecracker / gVisor / nested QEMU) | platform · sandbox |
| [0020](0020-leaf-agents-sdk.md) | Leaf Agents SDK choice (Anthropic / OpenAI / both) | llm · vendor |
| [0021](0021-policy-engine-build-vs-adopt.md) | Policy engine: build vs adopt RuleZ | platform · safety |
| [0022](0022-per-subgraph-topology.md) | Per-subgraph topology — when to extract shared structure | orchestration · refactor |
| [0023](0023-mcp-server-topology.md) | MCP server topology (single global vs per-stage) | platform · authorization |

---

## How to add a new ADR

1. Pick the next sequential number (look at the highest existing).
2. Choose a short kebab-case title that names the decision (not the conclusion).
3. Create `NNNN-title.md` using the template below.
4. Add an entry to the index above (Accepted or Deferred).
5. Reference the ADR from the relevant section of `../design.md`.
6. If this ADR supersedes a previous one, edit both to cross-link and mark the old one `Superseded by ADR-NNNN`.

### Template

```markdown
# ADR-NNNN: <Decision title>

**Status:** Proposed | Accepted | Deferred | Superseded by ADR-XXXX
**Date:** YYYY-MM-DD
**Tags:** tag · tag · tag
**Related:** ADR-NNNN, ADR-NNNN

## Context

What situation triggered this decision? What are the forces in play? Cite specific sections of design.md or other docs where this decision surfaces.

## Options considered

- **Option A** — one-paragraph summary
- **Option B** — one-paragraph summary
- **Option C** — one-paragraph summary

## Decision

What we chose, stated unambiguously in one or two sentences.

## Tradeoffs

| Gain | Cost |
|---|---|
| ... | ... |

## Consequences

- What becomes easier downstream.
- What becomes harder or constrained.
- What new invariants must be preserved.

## Reversibility

How costly is undoing this decision later? What would need to change in the rest of the system? Low / Medium / High with justification.

## Evidence / sources

- Citations to design.md sections, other ADRs, research docs, published papers, or external references.
```
