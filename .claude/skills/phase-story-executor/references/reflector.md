# Reflector — Stage 4: Attempt Log + Lessons Learned

Stage 4 runs after the Validator (Stage 3) green-lights every AC and gate. Three artifacts to produce:

1. **Per-story attempt log** — append a final SUCCESS entry to `docs/phases/{phase}/stories/_attempts/{STORY-ID}.md`
2. **Cross-story lessons** — append (sparingly) to `docs/phases/{phase}/stories/_attempts/_lessons.md`
3. **Story-file status update** — add the `Status: Done` header block to the story file with evidence links

Then print a suggested commit message + a one-paragraph summary to the user.

## Per-story attempt log format

Append-only. Earlier attempts stay at the top; each new attempt goes at the bottom. The journal is what the *next* story in the phase reads in Stage 1.

```markdown
# Attempt log: {STORY-ID} — {short title from the story header}

## Attempt 1 — {YYYY-MM-DD HH:MM} — FAILED
**Approach:** {1-2 sentence summary of the approach}

**ReAct cycles:** {count}

**What worked:**
- {bullet — what you'd carry forward}

**What didn't:**
- {bullet — specific symptom: error message, failed AC, validator gap}

**Root cause:** {your best diagnosis when this attempt ended}

**Lesson for next attempt:** {one-sentence carry-forward}

**Validator report (if Stage 3 ran):** {paste the Stage 3 report block here, or "did not reach Stage 3"}

---

## Attempt 2 — {YYYY-MM-DD HH:MM} — FAILED
...

---

## Attempt N — {YYYY-MM-DD HH:MM} — SUCCESS

**Approach:** {what worked in the end}

**ReAct cycles:** {count}

**Validator report:** {paste the final passing Stage 3 report inline}

**Final files touched:**
- `{path}` — {created | modified} — {one-line summary}

**Tests added:**
- `{test path}::{name}` — verifies AC-{N}

**Documentation updated:**
- `{path}` — {what changed}

**Deviations from the story spec (if any):**
- {anything that ended up different from what the story said, with reason} — surfaced for human review

**Follow-ups surfaced this attempt:**
- {out-of-scope items observed but deliberately not touched}
```

## Cross-story lessons file (`_lessons.md`)

Append rarely. One entry should only be added if it's likely to apply to *other* stories. One-shot quirks belong in the per-story log only.

```markdown
# Lessons learned — Phase {N} — {phase name}

## Conventions discovered (not in CLAUDE.md)
- {lesson} — first hit: {STORY-ID}

## Common pitfalls
- {pitfall — symptom — fix} — first hit: {STORY-ID}

## Tooling notes
- {tool gotcha — workaround} — first hit: {STORY-ID}

## Testing patterns that worked
- {pattern} — first hit: {STORY-ID}
```

Keep `_lessons.md` under ~100 lines. If it grows past that, summarize the older half into a single "summary" section and archive the originals to `_lessons-archive.md`.

## Story-file status update

At the top of the story file, immediately under the existing header block, prepend a `Status` block. **Do not delete or modify the rest of the story** — it remains the contract.

```markdown
**Status:** Done
**Completed:** {YYYY-MM-DD}
**Attempts:** {N}
**Evidence:**
- Files: {comma-separated list of files created/modified}
- Tests: {comma-separated list of test names that prove the ACs}
- Commit: (pending human merge)
```

Then **check every acceptance-criterion checkbox** in the story file. Use `Edit` to change `- [ ]` to `- [x]` for each AC.

**Do not check a box for an AC that didn't actually get done.** If any AC didn't get done, the story isn't done — Stage 3 wouldn't have green-lit it. If you reach Stage 4 with an unchecked AC, something went wrong in Stage 3; stop and surface.

## Suggested commit message

The skill never auto-commits — humans always merge (`docs/production/design.md` load-bearing commitment). Print a suggested commit message for the user:

```
{phase-tag}({story-id}): {one-line summary}

Implements story {STORY-ID}: {goal sentence from Context Brief}.

ACs satisfied:
- AC-1: {short restatement}
- AC-2: {short restatement}
- AC-3: {short restatement}

Files touched: {count}
Tests added: {count}
Attempts: {N}

🤖 Generated with phase-story-executor skill
```

`{phase-tag}` is a short tag like `phase0`, `phase3`, etc. extracted from the phase folder name.

## Final summary to the user

After writing the artifacts, print a short summary in the chat:

> **Story {STORY-ID} complete.**
>
> - Acceptance criteria: {N}/{N} verified
> - Files touched: {list}
> - Tests added: {count} ({list})
> - Attempts taken: {N}
> - Attempt log: `{path}`
> - Suggested commit message above
>
> **Follow-ups surfaced (not folded in):**
> - {item with location}
> - {item with location}
>
> Ready for review. The skill does not auto-commit — `git diff` to inspect, then commit manually.

## What NOT to do in Stage 4

- Do not run any new tests that weren't part of Stage 3's gates (Stage 3 is the source of truth for verification)
- Do not refactor "while you're at it" (Rule 3 — surgical changes)
- Do not auto-commit (humans always merge)
- Do not delete or rewrite earlier attempts in the log — append only (Reflexion requires the full history)
- Do not check ACs that weren't verified in Stage 3 (Rule 12 — fail loud)
