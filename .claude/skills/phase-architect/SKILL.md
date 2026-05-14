---
name: phase-architect
description: Expands a codewizard-sherpa phase's final-design.md into the architectural artifacts an engineer needs to implement it. Reads docs/phases/{phase}/final-design.md plus docs/production/ (design.md + ADRs) and the broader roadmap, then runs a three-agent workflow producing (1) phase-arch-design.md with 4+1 Mermaid views, testing strategy, harness engineering, edge cases, goals/non-goals, next-phase integration, gap analysis; (2) per-phase ADRs in docs/phases/{phase}/ADRs/ in Nygard format; (3) High-level-impl.md with an ordered step-by-step roadmap. Use this skill whenever the user asks to "architect", "expand", "elaborate", or "flesh out the architecture of" a phase, "extract ADRs from" a phase, "write the implementation plan for" a phase, "produce the 4+1 views" for a phase, or "find gaps and improve" a phase design — as long as that phase already has final-design.md. Trigger even if the user doesn't explicitly mention ADRs, architecture, or 4+1.
---

# Phase Architect

Takes the output of `roadmap-phase-designer` (a `final-design.md` synthesized from three competing lens designs + critique) and expands it into the architectural artifacts an engineer needs to actually implement the phase:

- `phase-arch-design.md` — full architecture spec with 4+1 Mermaid views, testing strategy, harness/agentic best practices, edge cases, goals/non-goals, integration with the next phase, gap analysis.
- `ADRs/0001-*.md, 0002-*.md, ...` — one Nygard-format ADR per significant phase-level decision.
- `High-level-impl.md` — a basic, ordered implementation roadmap with steps and features.

This skill exists because `final-design.md` is intentionally a *design* document — it tells you what the system should look like in the abstract. To start writing code you need: explicit architecture views, a testing strategy, an enumerated list of decisions you can audit, and an ordered work plan. This skill produces those.

## When to use

Trigger on any request that asks to:
- Architect a phase / write the architecture for a phase
- Extract ADRs from a phase's final design
- Produce a 4+1 view for a phase
- Write the implementation plan for a phase
- Elaborate / flesh out a phase that already has `final-design.md`
- Find gaps in a phase's design and improve it
- Take a phase's design "forward toward implementation"

Do **not** trigger on:
- Designing a phase from scratch — that's `roadmap-phase-designer`'s job (which produces the `final-design.md` this skill consumes)
- Editing existing ADRs or the production ADR set in `docs/production/adrs/`
- Adding new phases to `docs/roadmap.md`

## Required input

The skill needs **one** thing: the phase number (0–16). If the user didn't give one, ask.

The skill assumes `docs/phases/NN-<slug>/final-design.md` exists. If it doesn't, stop and tell the user to run `roadmap-phase-designer` first — don't try to fabricate a final design.

## What the skill produces

Inside the phase folder `docs/phases/NN-<slug>/`:

| File / directory | Purpose |
|---|---|
| `phase-arch-design.md` | Full architecture spec (Stage 1 output) |
| `ADRs/0001-<title>.md` …  | One Nygard ADR per significant decision (Stage 2 output) |
| `ADRs/README.md` | Index of the phase's ADRs |
| `High-level-impl.md` | Ordered implementation roadmap with steps + features (Stage 3 output) |

The folder's existing `final-design.md`, `critique.md`, and the three lens designs are **not modified** — they're inputs.

## Workflow — three stages

### Stage 1 — Architect

Spawn ONE subagent (`general-purpose`) — the **Architect**. It produces the architecture spec. This stage must complete before Stages 2 and 3, because both downstream agents read its output.

The Architect reads:
- `docs/phases/NN-<slug>/final-design.md` (primary input)
- `docs/phases/NN-<slug>/critique.md` (what the synthesis was forced to address)
- The three lens designs (`design-performance.md`, `design-security.md`, `design-best-practices.md`) — for context on what was discarded and why
- `docs/roadmap.md` — full file (need the broader arc, especially the *next* phase to plan the integration handoff)
- `docs/production/design.md` — the canonical architecture reference, especially §2 (commitments) and §8 (architectural views)
- All accepted production ADRs in `docs/production/adrs/` that touch this phase's tooling/scope — *all 28 are reasonably small*; the Architect should pull the ones that matter
- Any `final-design.md` from *prior* phases in `docs/phases/` (for continuity)
- `CLAUDE.md`

It writes ONE file: `docs/phases/NN-<slug>/phase-arch-design.md`.

Prompt and full output template: [references/architect.md](references/architect.md).

### Stages 2 & 3 — ADR extractor + Implementation planner (parallel)

After the Architect finishes, spawn TWO subagents **in a single message with two Agent tool calls** so they run in parallel:

**Stage 2 — ADR extractor.** Reads `phase-arch-design.md`, `final-design.md` (especially its Synthesis ledger), `critique.md`, and the relevant production ADRs (for format and tone). Writes one Nygard-format ADR per significant phase-level decision into `docs/phases/NN-<slug>/ADRs/0001-*.md`, `0002-*.md`, …, plus `ADRs/README.md` as the index.

Aim for 5–15 ADRs per phase. Consolidate related decisions into single ADRs. Don't ADR-ify the trivial.

Prompt and full output template: [references/adr-extractor.md](references/adr-extractor.md).

**Stage 3 — Implementation planner.** Reads `phase-arch-design.md` and `final-design.md`. Writes `High-level-impl.md` — an ordered roadmap of implementation steps with features per step and done-criteria.

Prompt and full output template: [references/impl-planner.md](references/impl-planner.md).

## Naming the slug

Slugs are inherited from the existing phase folder under `docs/phases/`. Do **not** invent a new slug — the folder already exists with the name that `roadmap-phase-designer` chose.

## Important behaviors

- **Stage 1 must complete before Stages 2 and 3.** The Architect's output is an input for both downstream agents. Don't shortcut by running all three in parallel.

- **Stages 2 and 3 must run in parallel.** A single message with two Agent tool calls. They're independent — sequential spawning just wastes wall-clock time.

- **Don't silently overwrite.** If `phase-arch-design.md` or `ADRs/` already exists, ask the user whether to overwrite, archive (rename existing to `*-archived-YYYY-MM-DD`), or stop.

- **Don't fabricate decisions.** The ADR extractor's source of truth is `final-design.md` + `phase-arch-design.md`. If a decision isn't documented in those, it doesn't get an ADR. If the agent thinks a decision *should* exist but isn't documented, that's a gap — flag it back to the user, don't invent it.

- **Pass each subagent a focused prompt.** Subagents likely can't find this skill on their own. When you spawn each, paste the reference file's prompt content directly along with the phase number, the resolved phase folder path, and the current date.

- **Architect quality is load-bearing.** This is the single most important output of the skill — Stages 2 and 3 are derivative. If the Architect produces a thin or wrong document, the ADRs and impl plan inherit those problems. Don't rush Stage 1.

## Architecture framings the Architect should use

The 4+1 view set is canonical. Beyond that, the Architect should also bring:

- **C4-style decomposition** at the component level if the phase is component-heavy (containers → components → code).
- **Sequence diagrams** for every non-trivial control flow, not just one.
- **Failure-mode-first thinking.** "What does this look like when it breaks?" should be answered for every component.
- **Idempotence, replay, and determinism** as first-class properties — this is an agentic system; non-deterministic control flow is a smell.
- **Test pyramid plus property tests and golden files** where applicable. Don't punt the testing strategy to implementation.
- **Goals AND non-goals.** Non-goals prevent scope creep.
- **Design-pattern toolkit awareness.** All three agents in this skill consult `references/design-patterns-toolkit.md` (the same catalog used by `roadmap-phase-designer`). The Architect explicitly names the patterns it commits to in a "Design patterns applied" section; the ADR extractor tags each ADR with its pattern and produces *anti-decision* ADRs ("why we did NOT introduce Strategy here") for restraint; the impl planner uses pattern commitments to drive sequencing (Newtypes + Smart constructors land Step 1; Plugin/Registry kernels precede their plugins; type-strict from day 1). Honoring the toolkit's anti-patterns list (pattern soup, premature pluggability, stringly-typed identifiers, boolean-flag soup, untyped `dict[str, Any]`) is non-negotiable — those become Gap-analysis entries when found, not silent acceptance.

## Tip — running on a phase after the architecture changes

If you regenerate `final-design.md` (e.g., the roadmap shifted), back up the existing `phase-arch-design.md`, `ADRs/`, and `High-level-impl.md` (e.g., rename to `*-archived-YYYY-MM-DD`) before re-running this skill. The skill is designed to produce clean outputs, not merge into existing ones.
