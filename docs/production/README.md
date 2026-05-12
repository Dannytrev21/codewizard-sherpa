# Production design — codewizard-sherpa

Everything relevant to the production-target architecture of codewizard-sherpa lives in this folder. Self-contained: a new engineer can hand this folder to themselves and understand the system without reading other design docs.

## What's in here

| File | Purpose |
|---|---|
| [`design.md`](design.md) | The canonical production architecture reference. Read this first. Covers the 7-stage pipeline, the Layered Hybrid orchestrator (Temporal + LangGraph + SHERPA + Trust-Aware gates), agent personas, continuous-gather model, POC-to-service mapping, deferred decisions, and 4+1 architectural views (Logical / Process / Development / Physical / Scenarios) plus supplementary views (Persona / Component / Subgraph state machine / Gate decision flow). |
| [`adrs/`](adrs/) | One Architecture Decision Record per major design choice. Each ADR captures *why* a decision was made, what alternatives were considered, what tradeoffs were accepted, and how reversible the choice is. Start at [`adrs/README.md`](adrs/README.md) for the index. |

## Reading order

1. [`design.md`](design.md) — the architecture
2. [`adrs/README.md`](adrs/README.md) — the decisions index
3. Specific ADRs as cross-referenced from `design.md`

## How to extend

- **Adding a new architectural decision.** Write a new ADR in `adrs/`, numbered sequentially. Add an entry to [`adrs/README.md`](adrs/README.md). Reference the ADR from the relevant section of `design.md`. Do not bury new rationale inside the design doc — keep `design.md` focused on the *what*, push the *why* to ADRs.
- **Reversing or refining an existing decision.** Create a new ADR with status `Supersedes ADR-NNNN`. Update the superseded ADR's status to `Superseded by ADR-MMMM` but keep the file — historical context matters.
- **Resolving a deferred decision.** When evidence arrives (e.g., post-launch metrics, spike results), update the deferred ADR's status to `Accepted`, fill in the chosen option, and record the evidence that resolved it. Add a "Resolution date" line.

## Background research (not in this folder)

The original research and supporting docs live in `docs/` (one level up):

- `docs/localv2.md` — the local POC spec for the gather layer
- `docs/context.md` — the original gather-layer service design
- `docs/auto-agent-design.md` — the original 7-stage pipeline writeup
- `docs/gemini-auto-agent-design.md` — Gemini-authored research with empirical findings and AgentOps reference
- `docs/local.md` — superseded by `localv2.md`

These are kept as background. `design.md` synthesizes them and cites them as evidence; do not edit them.

## Template for future system designs

This folder shape is the template for every future system design in this project. When you design the next system (e.g., the planning service, the autonomous executor, the policy engine), create `docs/<system-name>/` with the same structure:

```
docs/<system-name>/
├── README.md     # this same template, adapted
├── design.md     # architecture + 4+1 views
└── adrs/
    ├── README.md
    └── 0001-*.md ...
```

Consistency across system designs makes the documentation surface scannable as the project grows.
