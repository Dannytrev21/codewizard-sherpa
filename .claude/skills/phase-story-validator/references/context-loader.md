# Context Loader — Stage 1

Stage 1 builds the **Context Brief** that the three critics (Stage 2) all reference. Read disciplined and write tight — the critics will each ingest different slices of this brief plus their own focused reads.

## Read order

1. **The story file** itself (`docs/phases/{phase}/stories/{STORY-ID}.md`)
   - Every section. Pay special attention to the Goal, Acceptance criteria, TDD plan, Files to touch, and the References block.

2. **Project commitments**
   - `CLAUDE.md` — the load-bearing commitments section (e.g., "No LLM anywhere in the gather pipeline", "Facts, not judgments", "Extension by addition"). Any AC that contradicts these is a Consistency failure.
   - `~/.claude/CLAUDE.md` if accessible — the 12 global rules. Rule 9 ("Tests verify intent, not just behavior") is the polestar for Stage 2B.

3. **Phase-level context** (only what the story references)
   - `docs/phases/{phase}/phase-arch-design.md` — the Goal, Non-goals, Component design, Testing strategy sections are usually relevant
   - `docs/phases/{phase}/final-design.md` — the synthesis ledger entry the story implements
   - `docs/phases/{phase}/High-level-impl.md` — find this story's step
   - `docs/phases/{phase}/ADRs/*.md` — every ADR the story names

4. **Production-level context** (only the sections the story names)
   - `docs/production/design.md` — never the whole file
   - `docs/production/adrs/*.md` — each referenced ADR

5. **Prior validation, if any**
   - `docs/phases/{phase}/stories/_validation/{STORY-ID}.md` — if it exists, the story has been validated before. Read in full to understand what was changed last time.

6. **Adjacent test code** (the Test-Quality critic will need this in Stage 2B; pre-fetch the path)
   - One existing test file in the directory the story's TDD plan will write to (if that directory has any tests yet)
   - The project's test config (`pyproject.toml`'s `[tool.pytest.ini_options]` or `pytest.ini`)

7. **Adjacent production code + sibling-story validation history** (the Design-Patterns critic will need this in Stage 2D; pre-fetch the paths)
   - The nearest sibling module in the directory the story writes to — patterns are inferred from neighbours, not invented (Rule 11)
   - Any existing shared kernel the story is supposed to consume (`parsers/_io.py`, `parsers/_depth.py`, `coordinator/budgeting.py`, etc. — read the Implementation outline for hints)
   - Prior `_validation/{STORY-ID}.md` reports for sibling stories in the same family (e.g., if validating S1-04, read `_validation/S1-02-…md` and `_validation/S1-03-…md` for the established plugin/strategy framing)

## What to extract — Context Brief template

After reading, write a Context Brief into working memory using this template:

```markdown
## Context Brief: {STORY-ID}

### Story snapshot
- **Goal** (verbatim from story): {one sentence}
- **Non-goals** (from story Out-of-scope section, if any): ...

### Acceptance criteria as written (verbatim, numbered)
- AC-1: ...
- AC-2: ...
- AC-3: ...

### TDD plan as written (one bullet per test)
- Test 1: {description} — verifies AC-{N}
- Test 2: {description} — verifies AC-{N}

### Files to touch (story-declared)
- {path} — {create | modify | delete}

### Proposed module shape (from Implementation outline)
- **Public surface:** {function signatures the story prescribes}
- **Pure helpers:** {state-machine / parser / walker functions the story names; mark "pure bytes-to-bytes" or "side-effecting"}
- **Side effects:** {fd open, structlog emit, fs write — for the imperative-shell / functional-core diagnostic}
- **Existing kernel consumed:** {paths in repo the story imports from — for the Open/Closed and Dependency-Inversion checks}
- **Existing files edited:** {non-create entries in Files-to-touch — for the surgical-edit / OCP diagnostic}

### Sibling-family lineage (Design-Patterns critic)
- **This story is the {1st | 2nd | 3rd | Nth} concrete consumer of {family-name}** (e.g., 3rd parser after `safe_json`, `safe_yaml`)
- **Prior validation framings carried forward:** {e.g., S1-03 hardening established `parsers/_io.py` + `parsers/_depth.py` + `parser_kind` discriminator strategy}
- **Rule-of-three threshold:** {NOT YET REACHED | REACHED — kernel extract is now mandatory | ALREADY EXTRACTED — story should consume}

### Goal-to-AC trace (does each AC trace back to the goal?)
- AC-1 → goal: YES (covers behavior X)
- AC-2 → goal: WEAK (covers a niche of the goal, may need strengthening)
- AC-3 → goal: NO (doesn't trace — flag for Consistency critic)

### Phase / arch constraints
- ADR-{NNNN}: {one-sentence constraint relevant to this story}
- Arch decision: {if phase-arch-design.md takes a stance the story must obey}
- CLAUDE.md commitment: {if any is implicated, e.g. "No LLM in gather pipeline"}

### Phase exit criteria the story must contribute to
- {bullet from phase-arch-design.md or High-level-impl.md's exit criteria}

### Prior validation history (if any)
- Last validated: {date}
- Last verdict: STRONG / HARDENED / RESCUE
- Changes carried forward: {summary}

### Open ambiguities
- {anything in the story that's unclear or contradicted by another doc}
```

The Context Brief is shared (as a pre-filled context block) with all three critics in Stage 2. Each critic also reads its own focused set of files — see the respective critic reference.

## The hard gate at the end of Stage 1

If "Open ambiguities" has entries, **stop and surface them to the user** before spawning critics. The critics will produce noisy findings if asked to critique a story whose own meaning is in dispute. Surface, get one-line clarification, then proceed.

If "Open ambiguities" is empty, proceed to Stage 2.

## Reading hygiene

- Use `Read` with `offset`/`limit` for big files; don't pull whole production/design.md
- For ADRs, extract Decision + Consequences sections; skip Options / Tradeoffs unless evaluating a tradeoff
- Note in the Context Brief what you intentionally skipped — the critics may want to come back
- Token budget for Stage 1: aim under ~1500 tokens of Context Brief. The brief is overhead; the value is in Stage 2's parallel critiques.
