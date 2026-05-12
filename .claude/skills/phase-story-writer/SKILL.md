---
name: phase-story-writer
description: Decomposes a codewizard-sherpa phase's architecture, ADRs, and High-level-impl.md into autonomous-AI-agent-executable stories under docs/phases/{phase}/stories/. Runs a planner agent that writes a manifest, then parallel writers (one per impl step) that flesh out each story with context, where-to-look references, goal, acceptance criteria, implementation outline, red-green-refactor TDD plan, files-to-touch, out-of-scope, and implementer notes. Brings sprint-planning rigor (small shippable stories, explicit dependencies) and architect framing (every story traces to arch design + ADRs). Use this skill whenever the user asks to create stories, decompose into stories, break down, sprint-plan, make a backlog, or produce implementation stories for a phase. Trigger on mentions of stories, backlog, sprint, tickets, TDD plan, autonomous implementation, or work decomposition.
---

# Phase Story Writer

Takes the output of `phase-architect` (`phase-arch-design.md` + `ADRs/` + `High-level-impl.md`) and decomposes it into a backlog of autonomous-AI-agent-executable stories under `docs/phases/{phase}/stories/`.

The skill exists because `High-level-impl.md` describes implementation at the **step** level — large coherent chunks of work. To actually drive an AI coding agent (or a human implementer), you need stories sized to **one focused session**: a single deliverable, explicit acceptance criteria, the exact files to touch, references to the architecture sections and ADRs that govern the choice, and a red-green-refactor TDD plan. This skill writes those.

Each story is **self-contained enough to be handed to an autonomous agent** without that agent needing to re-derive context — it tells the agent *what to build, why, where to look, what to test first, and when it is done*.

## When to use

Trigger on any request that asks to:
- Create stories / write stories / generate stories / decompose into stories
- Make a backlog / sprint-plan / make tickets / write the sprint
- Break down / decompose a phase into work units
- Produce a backlog from `High-level-impl.md` / from `phase-arch-design.md`
- Get a phase ready for autonomous implementation

Do **not** trigger on:
- Phases that don't yet have `High-level-impl.md` — that's `phase-architect`'s job; running this skill on a phase without it should stop with a clear error
- Generic sprint planning unrelated to codewizard-sherpa phases
- Writing test code directly (this skill writes *story specs*, including TDD *plans* for an agent to execute — not test implementations themselves)

## Required input

The skill needs **one** thing: the phase number (0–16). If the user didn't give one, ask.

The skill assumes `docs/phases/NN-<slug>/High-level-impl.md`, `phase-arch-design.md`, and `ADRs/` all exist. If any is missing, stop and tell the user to run `phase-architect` first.

## What the skill produces

Inside `docs/phases/NN-<slug>/stories/`:

| File | Purpose |
|---|---|
| `README.md` | The story manifest — index of all stories with status, dependencies, and step grouping (Stage 1 output) |
| `S<N>-<TT>-<slug>.md` | One file per story (Stage 2 output) — e.g., `S1-01-pyproject-toml-scaffold.md` |

Story IDs are `S<step>-<two-digit-story>`: `S1-01`, `S1-02`, …, `S2-01`, `S2-02`, … The leading `S<step>` ties each story back to its `High-level-impl.md` step. The two-digit suffix orders stories *within* a step.

## Workflow — two stages

### Stage 1 — Story planner (1 agent)

Spawn ONE subagent (`general-purpose`). It reads the phase's architecture documents and produces the **stories manifest** at `docs/phases/NN-<slug>/stories/README.md`. The manifest is the contract that Stage 2's parallel writers work against — they don't relitigate the decomposition, they execute it.

The planner reads:
- `docs/phases/NN-<slug>/High-level-impl.md` (primary — the steps to decompose)
- `docs/phases/NN-<slug>/phase-arch-design.md` (architecture context, especially Components + Testing strategy)
- `docs/phases/NN-<slug>/ADRs/` (decisions that constrain how stories are written)
- `docs/phases/NN-<slug>/final-design.md` (background only)
- `docs/roadmap.md` (Phase NN section — exit criteria, broader context)

It writes `stories/README.md` with the full story index + cross-cutting metadata: dependency DAG, definition-of-done, conventions, and per-step story lists.

Prompt and full template: [references/story-planner.md](references/story-planner.md).

### Stage 2 — Story writers (parallel — one per step)

After Stage 1, spawn N subagents **in one message with N Agent tool calls** — one per step in `High-level-impl.md` — so they run in parallel. Each agent fleshes out the stories for ONE step.

Each writer reads:
- `docs/phases/NN-<slug>/stories/README.md` (the manifest — assigns it stories by step)
- `docs/phases/NN-<slug>/phase-arch-design.md` (full)
- `docs/phases/NN-<slug>/ADRs/` (full — these are the constraints stories must honor)
- `docs/phases/NN-<slug>/High-level-impl.md` (its assigned step's section)

Each writer writes ONE file per story assigned to its step. Files are named `S<N>-<TT>-<slug>.md`. The writer for Step 1 produces `S1-01-*.md`, `S1-02-*.md`, … and so on.

Prompt and full template: [references/story-writer.md](references/story-writer.md).

## Story structure (every story file)

Each story file MUST follow the same structure so an agent picking up any story knows where to find what:

1. Header (ID, title, status, effort, dependencies)
2. **Context** — why this story exists, traced to arch design
3. **References — where to look** — concrete pointers to arch sections + ADRs + external docs
4. **Goal** — one sentence
5. **Acceptance criteria** — verifiable checkboxes
6. **Implementation outline** — ordered steps
7. **TDD plan — red / green / refactor** — write the failing test first, smallest impl to green, refactor
8. **Files to touch** — table of paths + reason
9. **Out of scope** — deferred items + where they go
10. **Notes for the implementer** — watch-outs, edge cases, patterns to honor

The exact template lives in [references/story-writer.md](references/story-writer.md). All stories use it — consistency means an autonomous agent learns the shape once.

## Important behaviors

- **Stage 1 must complete before Stage 2.** The manifest is the contract; writers depend on it.
- **Stage 2 writers run in parallel.** A single message with N Agent tool calls. Sequential spawning just wastes wall-clock with no quality gain (each writer's step is independent of the others).
- **Don't silently overwrite an existing `stories/` directory.** If it already exists, ask the user — overwrite, archive (rename to `stories-archived-YYYY-MM-DD`), or stop.
- **Story sizing is load-bearing.** Each story should be completable in **one focused session** by an AI coding agent. Rule of thumb: 1–3 hours of human-equivalent work; one clear deliverable; 3–6 acceptance-criteria checkboxes. If you find yourself writing a story with 12 acceptance criteria, split it.
- **Pass each subagent a focused prompt.** Inline the reference file content directly in the Agent prompt along with the phase number, resolved phase folder path, the step assigned to that writer (for Stage 2), and the current date.
- **Stories trace back, always.** Every story's "References — where to look" section must point to at least one arch-design section and at least one ADR. Stories that don't trace back are floating tasks; floating tasks rot.

## Sprint-planning rigor we bring

- **Definition of done** is the same across all stories — captured once in `stories/README.md` and inherited.
- **Dependencies are explicit and minimal.** A story should depend on the smallest possible set of upstream stories; transitive dependencies are not listed.
- **No story spans steps.** If a piece of work feels like it crosses two `High-level-impl` steps, that's a sign the steps were miscut at the architect stage, or that two stories should exist (one per step). Don't paper over it.
- **Shippable in isolation when feasible.** Each story should produce *some* observable change in the system — even if it's just a new module that passes its own test. Stories that "set up" without delivering anything observable are usually two stories merged.
- **Right-size for autonomy.** The story is written for an AI agent that has read no other prior context in this session. Self-containment is the test: if the agent needs to ask "why am I doing this," the story failed.

## Architect framing we bring

- **Every story is anchored in `phase-arch-design.md`.** "Where to look" points at specific sections, not the whole document.
- **ADR compliance is part of acceptance.** If ADR-0007 says the probe contract is byte-for-byte frozen, the story that touches the probe contract has an acceptance criterion that the snapshot test passes.
- **The 4+1 views are the map.** If a story implements a component named in the Logical view, link to it. If it crosses the boundary of a Process-view sequence, link to the sequence diagram.
- **Gaps from the arch's "Gap analysis" become first-class stories**, not afterthoughts. If the architect surfaced a gap, the story manifest has a story for it.

## Tip — re-running on a phase

If you regenerate `High-level-impl.md` or the ADRs (because the phase architecture shifted), back up `stories/` first (rename to `stories-archived-YYYY-MM-DD`), then re-run. The skill produces a clean directory, not a merge.
