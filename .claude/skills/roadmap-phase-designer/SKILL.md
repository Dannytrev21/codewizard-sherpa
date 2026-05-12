---
name: roadmap-phase-designer
description: Designs the implementation plan for a single phase from the codewizard-sherpa roadmap (docs/roadmap.md, Phases 0-16) using a five-agent workflow. Spawns three parallel design subagents (performance-first, security-first, best-practices-first), then a devil's-advocate critic, then a Graph-of-Thought synthesizer that produces the final design. Writes all artifacts into docs/phases/NN-slug/. Use this skill whenever the user asks to design, plan out, flesh out, expand, or drill into a specific codewizard-sherpa roadmap phase by number — e.g., "design Phase 3", "let's flesh out phase 7", "plan out phase 13", "what does phase 5 look like in detail". Use it even when the user doesn't explicitly mention the skill or roadmap.md, as long as the request targets the implementation design of a numbered roadmap phase.
---

# Roadmap Phase Designer

Turns a single phase from `docs/roadmap.md` (Phases 0–16) into a fully designed implementation plan, by running a five-agent design workflow and writing all artifacts to `docs/phases/NN-slug/`.

The skill exists because the roadmap is intentionally epic-level — it says *what ships* per phase, not *how*. Designing the "how" benefits from multiple viewpoints competing rather than a single take, and from explicit critique before synthesis. This skill encodes that pattern.

## When to use

Trigger on any request that asks to *design*, *plan out*, *flesh out*, *expand*, *drill into*, or otherwise produce a detailed implementation design for a numbered roadmap phase. Examples:

- "Design Phase 3"
- "Let's flesh out phase 7"
- "What would phase 11 look like in detail?"
- "Plan out the implementation of phase 13"

Do **not** trigger on:
- Requests to edit or refine `docs/roadmap.md` itself (the roadmap is the input; this skill consumes it)
- Designs that aren't tied to a specific roadmap phase number
- Asking what a phase is *about* (that's just reading roadmap.md)

## Required input

The skill needs **one** thing: the phase number (0–16). If the user didn't give one, ask — don't guess.

## What the skill produces

A new directory at `docs/phases/NN-<slug>/` (slug derived from the phase title) containing:

| File | Purpose |
|---|---|
| `design-performance.md` | Design under the performance-first lens (Round 1) |
| `design-security.md` | Design under the security-first lens (Round 1) |
| `design-best-practices.md` | Design under the best-practices lens (Round 1) |
| `critique.md` | Devil's-advocate critique of all three designs (Round 2) |
| `final-design.md` | Graph-of-Thought synthesis — **the design of record** (Round 3) |
| `README.md` | Index linking to each artifact in reading order |

## Workflow — three rounds

Each round depends on the previous; agents *within* a round run in parallel.

### Round 1 — Three parallel design subagents

Spawn three subagents **in a single message with three Agent tool calls** so they run truly in parallel. Use `subagent_type: general-purpose` (they need write access).

Each agent reads:
- `docs/roadmap.md` (full — every designer needs the broader arc, not just their phase)
- `docs/production/design.md` §2 (load-bearing commitments) for the invariants they must respect
- The ADRs named in their phase's Scope/Tooling sections from `docs/production/adrs/`
- `final-design.md` from any *prior* phases already in `docs/phases/` (preserves coherence across phases)
- For Phase 0/1/2, also `docs/localv2.md` (the local POC contract)

Each agent writes ONE file. The prompts and output templates live in references — load them when you spawn each agent:

- Performance designer → `design-performance.md` — see [references/designer-performance.md](references/designer-performance.md)
- Security designer → `design-security.md` — see [references/designer-security.md](references/designer-security.md)
- Best-practices designer → `design-best-practices.md` — see [references/designer-best-practices.md](references/designer-best-practices.md)

### Round 2 — Devil's-advocate critic

Once all three Round 1 designs are on disk, spawn ONE subagent (`general-purpose`). It reads the roadmap phase + the three designs and writes `critique.md`. The critic attacks each design specifically with concrete weaknesses, hidden assumptions, and missed risks. It does **not** propose alternatives — that's the synthesizer's job.

Prompt and output template: [references/critic.md](references/critic.md).

### Round 3 — Graph-of-Thought synthesizer

Spawn ONE subagent (`general-purpose`). It reads the three designs + the critique + the roadmap phase + the relevant ADRs, performs Graph-of-Thought decomposition (atomic decisions as vertices; agreement/conflict/complement/subsumption as edges), scores against the phase's exit criteria + the broader roadmap + the critique, and writes `final-design.md`.

Prompt, decomposition algorithm, and output template: [references/synthesizer.md](references/synthesizer.md).

### After Round 3 — write the README

Once `final-design.md` exists, write `docs/phases/NN-<slug>/README.md` linking to each artifact in reading order: final-design → critique → the three competing designs. This is a thin orchestrator task — you (the parent Claude) write it directly, no subagent.

## Naming the slug

Derive from the phase title in `roadmap.md`. Drop articles, lowercase-kebab-case the meaningful words, keep under 50 chars total (including the `NN-` prefix). Compress meaningfully if the title is long — don't truncate mid-word.

**Examples (verified against current roadmap.md):**

| Phase title in roadmap | Folder name |
|---|---|
| Phase 0 — Bullet tracer + project foundations | `00-bullet-tracer-foundations` |
| Phase 3 — Vuln remediation: deterministic recipe path | `03-vuln-deterministic-recipe` |
| Phase 7 — Add migration task class (Chainguard distroless) | `07-migration-task-class` |
| Phase 13 — AgentOps: cost ledger + budget enforcement + ROI dashboard | `13-agentops-cost-roi` |
| Phase 15 — Agentic recipe authoring (deterministic → agentic) | `15-agentic-recipe-authoring` |

## Important behaviors

- **Parallelism in Round 1 is load-bearing.** The three designs *must* be independent — they're competing viewpoints, not iterative refinements. Spawn them in a single message with three Agent tool calls. Sequential spawning leaks viewpoint between rounds and defeats the workflow.

- **Don't silently overwrite an existing phase folder.** If `docs/phases/NN-<slug>/` already exists, ask the user whether to overwrite, suffix the new run with `-v2`, or stop. A half-overwritten folder is worse than either decision.

- **`final-design.md` is the design of record.** When other documents link to a phase's design, they link to `final-design.md`, not the per-lens designs. The per-lens designs and the critique are kept for audit, not for execution.

- **The phase scope is fixed by the roadmap.** The three designers are designing *the phase as specified*. They are not redesigning phase boundaries, merging phases, or expanding scope. If a designer believes the phase is wrong, that belongs in the design's "Risks" section — never in changes to phase scope.

- **Pass each subagent a focused prompt, not the whole skill.** When you spawn a subagent, paste the relevant reference file's instructions into the agent's prompt along with the phase number and the resolved phase folder path. Don't expect the subagent to find this skill on its own — it likely can't.

## Tip — running on a previously-designed phase

If the user wants to *re-run* a phase that was designed earlier (e.g., the roadmap moved and they want a fresh take), back up the existing folder (e.g., rename to `NN-<slug>-archived-YYYY-MM-DD`) before running this skill again. The skill is designed to produce a clean folder, not merge into an existing one.
