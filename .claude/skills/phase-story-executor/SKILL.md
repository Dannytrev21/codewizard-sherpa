---
name: phase-story-executor
description: Execute one user story from docs/phases/{phase}/stories/ in the codewizard-sherpa repo using red-green-refactor TDD with ReAct reasoning and a Ralph Wiggum naive-verification pass. Reads the story plus all referenced docs (phase-arch-design.md, ADRs, High-level-impl.md, production/design.md), writes failing tests first, makes them pass with minimum code, refactors, then runs a skeptical validator that checks every acceptance-criterion checkbox has runtime evidence. Loops up to 3 implementer attempts and keeps an append-only attempt log under _attempts/STORY-ID.md so each retry learns from the last. Use this skill whenever the user asks to implement, execute, or run a story — phrases like "do the next story", "implement S1-01", "execute story X", "work on phase 0 story 1", or names a story file path.
---

# phase-story-executor

Execute one user story at a time from `docs/phases/{phase}/stories/`. Reads the story plus every doc it references, implements the code under red-green-refactor TDD with a ReAct outer loop, then runs a Ralph Wiggum naive-verification pass against every acceptance criterion. Logs every attempt so the next try compounds.

This is the **runtime** stage of the four-skill pipeline:

1. `roadmap-phase-designer` — designs the phase
2. `phase-architect` — turns the design into architecture + ADRs + impl plan
3. `phase-story-writer` — turns the impl plan into discrete stories
4. **`phase-story-executor` (this skill)** — turns one story into working code

## When this skill fires

Trigger when the user asks to implement, execute, or run a story. Phrases include:

- "Implement story S1-01" / "execute story X" / "run the next story"
- "Do the next phase 0 story" / "work on phase N story M"
- Any user message that names a path inside `docs/phases/*/stories/`

**Story selection:**

- **Explicit path or ID given** → use it directly. ID-only (e.g., `S1-01`) is resolved against the active phase's `stories/README.md` manifest.
- **"Next story" / unspecified** → open `stories/README.md`, find the lowest-numbered story whose `Status` is not `Done` and whose `Depends on` is satisfied. Print which story was picked and pause for one-line confirmation before Stage 1.

Only one story per invocation. If the user asks for "all stories" or "the rest of the phase", say so and pick the first one — looping at the skill level (rather than within a single invocation) is what gives each story its own attempt log and its own commit.

## Inputs

- A story file (e.g. `docs/phases/00-bullet-tracer-foundations/stories/S1-01-bootstrap-project.md`) — explicit or auto-selected
- The phase directory is inferred from the story path
- Optional: `--retries N` style preference from the user (default 3)

## Outputs

1. **Real code changes** in the repo: source files, test files, configs, docs — whatever the story's "Files to touch" section names
2. **Per-story attempt log** at `docs/phases/{phase}/stories/_attempts/{STORY-ID}.md` (append-only journal — every attempt is recorded, with what worked / what didn't / lesson for next time)
3. **Cross-story lessons** appended to `docs/phases/{phase}/stories/_attempts/_lessons.md` (short, reusable takeaways)
4. **Story-file status update** — `Status: Done` header block with evidence links (test names, files, commit hash placeholder)
5. **Suggested commit message** printed back to the user — the skill never auto-commits (humans always merge — `docs/production/design.md` load-bearing commitment)

## Workflow

Four stages, sequential. Stage 2 ↔ Stage 3 forms an inner loop with a retry cap.

### Stage 1 — Context Loader

Read everything before writing anything. Produce a one-page **Context Brief** in working memory.

→ See [`references/context-loader.md`](references/context-loader.md) for the read order and the brief template.

**Exit gate:** Context Brief written; "Open ambiguities" section is empty (if not, surface to user before proceeding — Rule 1).

### Stage 2 — Implementer (ReAct + red-green-refactor TDD)

ReAct as the outer loop (Thought → Action → Observation), red-green-refactor as the inner discipline. One AC at a time. Write the failing test first. Smallest code to pass. Refactor while green. Every Thought-Action-Observation triple is journaled.

→ See [`references/implementer.md`](references/implementer.md) for the ReAct discipline and TDD rules.
→ See [`references/techniques.md`](references/techniques.md) for ReAct + Reflexion + CoV background.

**Exit gate:** every AC in the story has at least one test exercising it, all tests pass locally, lint + type-check are clean.

### Stage 3 — Validator (Ralph Wiggum naive verification)

Skeptical fresh-eyes pass. Re-explain each AC in the simplest, most literal terms. Then verify that meaning against runtime behavior — not against the code itself, but against what the code *does when you run it*. Counters the Implementer's confirmation bias.

Also runs cross-cutting gates: full test suite, ruff, mypy, pre-commit if configured.

→ See [`references/validator.md`](references/validator.md) for the Ralph Wiggum frame and report format.

**Decision:**
- All ACs pass + all gates green → proceed to Stage 4
- Any AC or gate fails → return to Stage 2 with the gaps as new Thoughts
- Retry cap: **3 implementer attempts per story**. After 3 RETURN cycles, stop. Write the diagnostic into the attempt log and surface the failure to the user — do not push partial work (Rule 12, fail loud).

### Stage 4 — Reflector

Write the per-story attempt log entry and append any cross-story lessons. Update the story file with `Status: Done` and evidence links. Print the suggested commit message and a one-paragraph summary of what shipped.

→ See [`references/reflector.md`](references/reflector.md) for the log format and the story-status update.

## Definition of Done

A story is complete only when ALL of these hold:

- [ ] Every acceptance-criterion checkbox in the story has an evidence link (file:line, test name, or runtime artifact)
- [ ] All tests added by the story's TDD plan pass
- [ ] The full test suite passes — no new failures, no unexpected skips
- [ ] Lint passes (ruff, or whatever the project's pyproject.toml configures)
- [ ] Type-check passes (mypy strict if configured)
- [ ] Every file listed in "Files to touch" has been touched (created or modified) — or the story file itself is amended to remove a file with a one-line reason
- [ ] Documentation updates from the story's Files-to-touch section are merged
- [ ] Stage 3 Validator signed off all ACs and all gates
- [ ] Attempt log + cross-story lessons written
- [ ] `Status: Done` in story file with evidence block

Anything less = the skill stopped early. Surface the gap explicitly. Do not claim success on something you didn't verify (Rule 12).

## Best practices baked in

- **Match the codebase's conventions** (Rule 11). Read `CLAUDE.md` once at the top of Stage 1 and apply throughout.
- **Surgical changes** (Rule 3). Touch only what the story names. If you spot something else worth fixing, log it as a follow-up — don't silently fold it in.
- **Simplicity first** (Rule 2). Minimum code that satisfies the test. No speculative features.
- **Documentation as you go**. New module → one-paragraph docstring. New CLI command → mkdocs nav entry. New config knob → entry in the relevant `references/` doc.
- **No LLM in deterministic transforms** (Rule 5). Parsing, path manipulation, exit codes, test discovery — use plain code. The model is for judgment, drafting, classification.
- **Fail loud** (Rule 12). Skipped test? Say so. Missing evidence? Say so. Validator partial? Say so.

## Failure modes the skill handles explicitly

| Symptom | Action |
|---|---|
| Story references a file that doesn't exist | Log it. Ask user whether to skip the reference or fail the story. |
| Test infrastructure missing (e.g., pytest not installed) | A prerequisite story didn't run. Stop. Surface to user with the missing dep. |
| Acceptance criterion is too vague to validate | Caught in Stage 1 ideally; if hit mid-implementation, log and surface to user. |
| 3 attempts all failed Stage 3 | Write the full diagnostic into the attempt log and STOP. Do not push partial work. |
| Tests pass but Ralph-Wiggum validator says "this doesn't actually do what was asked" | The test is wrong, not the code (Rule 9). Loop back to Stage 2 TDD red — fix the test first, then re-run green. |
| Story's TDD plan conflicts with the AC | Surface to user. The TDD plan is guidance; the AC is the contract. |
| Phase doesn't have a `stories/` folder yet | The `phase-story-writer` skill hasn't been run. Surface and stop. |

## References

- [`references/context-loader.md`](references/context-loader.md) — what to read, in what order, what to extract
- [`references/implementer.md`](references/implementer.md) — ReAct + red-green-refactor TDD discipline
- [`references/validator.md`](references/validator.md) — Ralph Wiggum naive-verification pass
- [`references/reflector.md`](references/reflector.md) — attempt log + lessons-learned format
- [`references/techniques.md`](references/techniques.md) — ReAct, Reflexion, Ralph Wiggum, Chain-of-Verification, self-consistency: when to use which
