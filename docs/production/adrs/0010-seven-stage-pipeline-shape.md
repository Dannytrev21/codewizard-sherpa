# ADR-0010: Seven-stage pipeline shape (Discovery → Learning)

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** pipeline · structure
**Related:** ADR-0003, ADR-0006, ADR-0009

## Context

The end-to-end workflow for one repo migration has natural boundaries — discovery is fundamentally different from assessment, planning is fundamentally different from execution, validation is downstream of execution. The choice is how many stages to call out as first-class architectural concerns.

Too few stages: each stage becomes a kitchen sink, internal complexity bloats, debugging is hard.
Too many stages: ceremony overwhelms substance, every workflow has 15 hand-offs.

The shape is also informed by the Konveyor Kai (Red Hat) prior art, which uses a similar multi-stage agentic pipeline for Java framework migrations.

## Options considered

- **Three stages**: Plan, Execute, Validate. Simple but conflates discovery, assessment, deep scan, and handoff into amorphous "Plan."
- **Five stages**: Discovery, Scan, Plan, Execute, Validate. Misses the handoff / learning boundaries that matter for governance and improvement.
- **Seven stages**: Discovery, Assessment, Deep Scan, Planning, Execution, Validation, Handoff, Learning. Matches the Konveyor pattern; each stage has distinct inputs/outputs and ownership boundaries.
- **More than seven**: e.g., split Validation into Build / Test / Security. Useful internally but doesn't deserve top-level visibility.

## Decision

**Seven stages:** Discovery → Assessment → Deep Scan → Planning → Execution → Validation → Handoff → Learning.

(That's eight names; "Stage 7 Learning" is the post-merge step. The pipeline is canonically described as 7 stages with Learning as the closing reflection.)

Each stage has:
- A distinct purpose
- Named inputs and outputs
- A declared answer to "uses LLM or fully deterministic?"
- A declared owner layer (Temporal Activity, Hierarchical Planner, SHERPA subgraph, Trust-Aware gate, deterministic Activity)

## Tradeoffs

| Gain | Cost |
|---|---|
| Each stage is independently testable and debuggable | Pipeline ceremony — 7 stages to traverse for every workflow |
| Clear ownership boundaries — gather doesn't reach into planning, etc. | New engineers must learn 7 stage names and what they do |
| Adding a new task type requires new subgraph at Planning + Execution; other stages reused | Some stages are 95% deterministic (Discovery, Handoff) — feels heavy |
| Stage 7 Learning closes the loop — system improves on every successful merge | Pre-merge stages can run in 10 minutes; post-merge Stage 7 can be days later |
| Matches Konveyor Kai's published structure — prior-art validation | If Kai shifts to a different shape, we don't follow automatically |

## Consequences

- Stages map cleanly to Temporal Activities or child workflows (ADR-0003).
- Stage-to-layer mapping is explicit in `../design.md §4.4`. Every stage has a declared layer owner.
- The Hierarchical Planner sits between Stages 1 and 3 — it routes based on Assessment output into the right Planning subgraph.
- Stage 4 Execution has two operational modes: human-executor (Phase 1) and autonomous-executor (Phase 2+). Both consume the same Stage-3 step files.
- Stage 6 Handoff is the hard human boundary (ADR-0009).
- Stage 7 Learning is post-merge, asynchronous, and not on the workflow's critical path.

## Reversibility

**Medium.** Splitting a stage further or merging two stages is a localized change that affects naming, the personas table, and the architectural views. Re-shaping the pipeline wholesale (e.g., to 4 stages) is expensive because all downstream docs, code organization, and personas reference the 7-stage structure.

## Evidence / sources

- `../design.md §3` (the 7-stage pipeline, one paragraph per stage)
- `../design.md §3.1` (personas grouped by stage)
- `../design.md §4.4` (stage-to-layer ownership table)
- `../../auto-agent-design.md §3` and `§4` — the original 7-stage writeup
- `../../auto-agent-design.md §2.1` — Konveyor Kai prior art
