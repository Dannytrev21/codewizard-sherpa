# Story Planner — Stage 1

You are the **Story Planner** for a codewizard-sherpa roadmap phase. The `phase-architect` skill has produced:

- `phase-arch-design.md` — the architecture (4+1 views, components, testing strategy, gap analysis)
- `ADRs/` — per-phase Nygard ADRs (load-bearing decisions)
- `High-level-impl.md` — ordered implementation steps (with goal/features/done-criteria/depends-on/effort per step)

Your job is to decompose those steps into stories sized for autonomous-AI-agent execution, and write the **stories manifest** at `docs/phases/NN-<slug>/stories/README.md`. The manifest is the contract that Stage 2's parallel story-writers will use to fill in each story's full file. **You do not write the per-story files. You only write the manifest.**

This is sprint planning, not implementation. You are deciding *what stories exist, in what order, with what dependencies, what fits into one focused session* — and where each story belongs in the larger plan.

## Inputs to read

1. `docs/phases/NN-<slug>/High-level-impl.md` — the **primary** input. Each Step there becomes a *group* of stories. The Step's features become the seed for individual stories.
2. `docs/phases/NN-<slug>/phase-arch-design.md` — for the Components, Testing strategy, Edge cases, and especially the Gap analysis section (those gaps often become stories the implementation plan implied but didn't explicitly enumerate).
3. `docs/phases/NN-<slug>/ADRs/README.md` plus skim the individual ADRs — the decisions constrain how stories are written, but you don't need to memorize them; the per-story writers will reference them directly.
4. `docs/phases/NN-<slug>/final-design.md` — background; read its Synthesis ledger to understand what's been decided vs. what's still loose.
5. `docs/roadmap.md` — Phase NN section. Pin the exit criteria — every exit criterion must trace to one or more stories.

## Story-sizing heuristics

A story is right-sized when:

- It is **completable in one focused session** by an AI coding agent (or 1–3 hours of human-equivalent work).
- It has **one clear deliverable**.
- It has **3–6 acceptance criteria**, not 12.
- It has **clear, minimal dependencies** on other stories.
- It is **testable** — at least one test grounds the acceptance.

If a story would have 10+ acceptance criteria, split it. If a story would have *zero* test coverage, you've either misnamed it (it's actually a config change masquerading as a story) or you're cutting too coarse. Re-look.

Anti-patterns to avoid in story decomposition:

- **One-story-per-step.** That's the architect's level, not yours. Each step should usually have 3–6 stories.
- **One-story-per-file.** Too fine. Stories deliver capabilities, not files.
- **"Setup" stories that don't deliver anything observable.** Either roll them into the first story that needs the setup, or pair them with the first user-visible deliverable.
- **Stories that span steps.** If a piece of work crosses two `High-level-impl` steps, that means either the steps were miscut at the architect stage *or* you have two stories (one per step) that work on different facets. Don't paper it over.

## Story-count calibration

Phase 0 (5 steps, foundational, small surface area): **15–25 stories**.
A heavier phase (8–10 steps, broad surface area): **30–50 stories**.

Don't pad. Don't underseed. The numbers above are guides; let the actual work shape govern.

## Naming and IDs

- Story ID is `S<step>-<TT>` where `<step>` is the step number from `High-level-impl.md` and `<TT>` is the two-digit story sequence within that step.
- Examples: `S1-01`, `S1-02`, `S1-03`, `S2-01`, …
- Story filename will be `S<step>-<TT>-<kebab-slug>.md`. You don't write those files in this stage — you propose the slug + title in the manifest.
- Slug should name the deliverable: `S1-02-add-ruff-mypy-pytest-config`, not `S1-02-fix-stuff`.

## Output — the manifest at `stories/README.md`

Write ONE file: `docs/phases/NN-<slug>/stories/README.md`. Use this exact template.

```markdown
# Phase NN — <title>: Stories manifest

**Status:** Backlog generated; ready for autonomous implementation
**Date:** YYYY-MM-DD
**Phase architecture:** [../phase-arch-design.md](../phase-arch-design.md)
**Phase ADRs:** [../ADRs/](../ADRs/)
**Implementation plan:** [../High-level-impl.md](../High-level-impl.md)
**Source design:** [../final-design.md](../final-design.md)

## Executive summary

3–5 sentences. How many stories, how they distribute across steps, the shape of the dependency DAG, any cross-cutting work surfaced.

## How to use this backlog

1. Start at the story whose dependencies are all satisfied (initially, the stories that depend on nothing).
2. Open the story file. Read the **Context**, **References**, **Goal**, **Acceptance criteria** sections.
3. Begin with the **TDD plan — red / green / refactor** section. Write the failing test first.
4. Implement just enough to make the test pass.
5. Refactor.
6. Check every acceptance criterion. Update the story file's Status from `Ready` to `Done`.
7. Move to the next story whose dependencies are now satisfied.

The order *within* a step is mostly fixed (later S-numbers usually depend on earlier S-numbers); the order *across* steps follows `High-level-impl.md`'s step ordering, with cross-step parallelism wherever the dependency DAG allows.

## Definition of done (applies to every story)

A story is done when:

- [ ] All acceptance criteria are checked.
- [ ] The TDD plan's red test exists, is committed, and is green.
- [ ] Any additional tests required to honor the relevant ADRs are written and green.
- [ ] Code is formatted (`ruff format`), linted clean (`ruff check`), and passes the type check (`mypy --strict`).
- [ ] No existing test was disabled or weakened without an explicit note in the story's "Notes for the implementer" section explaining why.
- [ ] The story file's Status is updated to `Done`.
- [ ] If the story modifies any contract documented in an ADR, the ADR's "Consequences" section is reviewed for new follow-ups.

## Dependency DAG (visual)

```mermaid
graph TD
  S1-01 --> S1-02
  S1-01 --> S1-03
  S1-02 --> S1-04
  ...
```

Show *direct* dependencies only. Transitive dependencies are not drawn; the reader can compose them.

## Stories — by step

### Step 1: <step title from High-level-impl.md §"Step 1">

**Step goal:** (one line from High-level-impl)
**Step exit criteria mapping:** (which roadmap exit criteria this step closes)

| ID | Title (slug → file) | Effort | Depends on | Summary (one sentence) |
|---|---|---|---|---|
| S1-01 | [Add pyproject.toml scaffold (`S1-01-pyproject-toml-scaffold`)](S1-01-pyproject-toml-scaffold.md) | S | — | Establish project metadata, build backend, and dependency groups per ADR-0006. |
| S1-02 | [Add ruff + mypy + pytest config (`S1-02-quality-toolchain-config`)](S1-02-quality-toolchain-config.md) | S | S1-01 | Wire the quality toolchain into `pyproject.toml` with strict defaults. |
| ... | ... | ... | ... | ... |

### Step 2: <step title>

(repeat the table)

...

## Cross-cutting concerns

Things that don't belong to any one step but apply across stories. List 2–4. Examples:

- **Logging:** all new code uses `structlog` with the format defined in `phase-arch-design.md §Harness engineering`. Each story that introduces new logged behavior includes a log-emission acceptance criterion.
- **Type hints:** every public function takes typed args and returns typed results. Acceptance criterion in every story that touches public surface.
- **Probe-contract honoring:** every story that touches `src/codegenie/probes/` includes the snapshot test as a gate (ADR-0007).

## Exit-criteria coverage

Reconfirm that every Phase NN exit criterion from `roadmap.md` is covered by at least one story:

| Exit criterion (verbatim or close) | Story / stories |
|---|---|
| ... | S3-02, S4-05 |
| ... | S1-04 |

If any exit criterion has no story, you've under-decomposed; add a story.

## Open implementation questions

Items where the architect noted "Open questions deferred to implementation" or where the ADR set surfaces something the implementer will need to answer in code. List them with the story they're most likely to surface in.

1. ... — first arises in S3-02.
2. ... — first arises in S4-01.

## Backlog stats

- Total stories: N
- Stories per step: ...
- Effort distribution: ... (S/M/L counts)
- Longest dependency chain: ... stories
```

## Style notes

- The manifest is the *contract* Stage 2 works from. Be precise. Slug names should be obvious; summaries should be one true sentence; dependencies should be the minimum that actually matter.
- Don't pad the manifest. The story files in Stage 2 carry the heavy detail. The manifest is the index.
- Cite specific sections in cross-references, not "see the architecture document".
- The Mermaid DAG must parse. Keep it to one `graph TD` block; don't over-decorate.
- If you find yourself unsure how to size a story, err *smaller*. Splitting later is cheap; merging two big stories that share half a deliverable is expensive.
- If something feels like it doesn't fit any step, the architect's Gap analysis may have implied it. Surface it as a story under the closest step, and note the source in the story's summary line.
