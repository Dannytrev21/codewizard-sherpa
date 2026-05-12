# Context Loader — Stage 1

The goal of Stage 1 is to build a one-page **Context Brief** that the Implementer (Stage 2) refers back to throughout coding. **Do not write any production code in Stage 1.** Reading-only.

## Read order

Read in this order and stop reading anything else once you have what you need. Token economy matters — the next stages need budget too.

1. **The story file** itself (`docs/phases/{phase}/stories/{STORY-ID}.md`)
   - Read every section: Header, Context, References, Goal, Acceptance criteria, Implementation outline, TDD plan, Files to touch, Out of scope, Notes for implementer
   - Note the References section carefully — it is the authoritative list of what else to read

2. **Project root conventions**
   - `CLAUDE.md` at repo root — load-bearing commitments, conventions, what NOT to do
   - `~/.claude/CLAUDE.md` if accessible — the 12 global rules

3. **Phase design docs** (only the ones the story references)
   - `docs/phases/{phase}/phase-arch-design.md` — read the sections the story names (Component design, Data model, Control flow, Testing strategy are usually relevant)
   - `docs/phases/{phase}/High-level-impl.md` — find this story's step entry
   - `docs/phases/{phase}/final-design.md` — only the synthesis ledger entries the story names
   - `docs/phases/{phase}/ADRs/*.md` — read every ADR the story names by number

4. **Production design references** (only the sections the story names)
   - `docs/production/design.md` — section by section, never the whole file
   - `docs/production/adrs/NNNN-*.md` — each one the story names

5. **Prior attempts on THIS story** (critical for Reflexion-style learning)
   - `docs/phases/{phase}/stories/_attempts/{STORY-ID}.md` — if it exists, read in full
   - `docs/phases/{phase}/stories/_attempts/_lessons.md` — cumulative cross-story lessons

6. **Adjacent code** (only if it already exists)
   - Each file in the story's "Files to touch" — read fully if it exists
   - The package's `__init__.py` one level up
   - One existing test file in the same directory — to learn the test style

## Context Brief template

After reading, write a Context Brief into working memory (do not save it to disk — it lives in the conversation). Use this exact template:

```markdown
## Context Brief: {STORY-ID}

### Goal (one sentence, your own words)
{What this story produces and why it matters}

### Acceptance criteria (verbatim, with AC numbers)
- [ ] AC-1: ...
- [ ] AC-2: ...
- [ ] AC-3: ...

### Files to touch
- {path} — {create | modify | delete} — {one-line reason}
- {path} — {create | modify | delete} — {one-line reason}

### Conventions to follow (extracted from CLAUDE.md and adjacent code)
- Naming: snake_case for {x}, PascalCase for {y}
- Tests: pytest with {observed pattern}
- Error handling: {observed pattern}
- Async: {observed pattern}

### Constraints from ADRs and arch design
- ADR-{NNNN}: {one-sentence decision that constrains this story}
- ADR-{NNNN}: ...
- Arch decision: {if the phase-arch-design.md takes a stance the story has to obey}

### Lessons from prior attempts (if any)
- Attempt {N}: {what failed and why}
- Carry forward: {what to do differently this time}

### Open ambiguities
- {anything in the story that's unclear or contradicted by another doc}
```

## The hard gate at the end of Stage 1

If "Open ambiguities" has any entries, **stop and surface them to the user** before entering Stage 2. Do not invent answers (Rule 1 — no silent assumptions). State each ambiguity, your best-guess interpretation, and ask for one-line confirmation.

If "Open ambiguities" is empty, proceed to Stage 2.

## What NOT to read

- The entire `docs/production/design.md` — read only the sections the story explicitly names
- Random source files outside the story's "Files to touch" list — unless they are direct callers/callees of those files
- Other phases' stories — unless the current story explicitly references one
- The production ADR index of decisions the story doesn't reference

If you find yourself reading more than ~5 files in detail, stop and reassess. Either the story is too broad (surface to user) or you're chasing a tangent.

## Reading hygiene

- Use `Read` with `offset` and `limit` for large files. Don't pull the whole thing if you only need one section.
- Note which sections you skipped, so the Implementer can come back if needed.
- For ADRs, extract the **Decision** and **Consequences** sections; usually you can skip Context/Options/Tradeoffs unless you're choosing between approaches.

Aim to keep Stage 1 well under your per-task token budget — the bulk of tokens belong to Stage 2 (implementation) and Stage 3 (validation), where they earn more.
