---
name: phase-story-validator
description: Harden one user story in docs/phases/{phase}/stories/ before phase-story-executor implements it. Reads the story + every referenced doc (arch, ADRs, design) and runs four parallel critics — coverage (do ACs cover the goal? edge cases missing?), test-quality (would the TDD plan catch an obviously wrong implementation? thin tests? intent vs behavior?), consistency (story contradicts arch or any ADR?), and design-patterns (does the prescribed implementation miss plugin/strategy/Open-Closed/dependency-inversion/hexagonal opportunities? primitive obsession on domain IDs? anaemic types where sum types would do? pure-impure tangle? hidden state? Open/Closed at the file boundary?). For weaknesses critics can't fix alone, an optional researcher looks up canonical patterns (mutation, property-based, metamorphic, INVEST, design-pattern precedents) and arXiv when non-obvious. Synthesizer edits the story in place — strengthens weak ACs, adds edge cases, rewrites thin tests, surfaces design-pattern opportunities in Notes-for-implementer — and logs everything to _validation/STORY-ID.md. Use whenever the user asks to validate, harden, audit, strengthen, review, or sanity-check a story — 'validate story X', 'harden S2-01', 'is this story ready', 'are the ACs strong enough', 'audit the next story', 'check the implementation patterns'.
---

# phase-story-validator

Harden a user story *before* it goes to the executor. Read the story plus every doc it references, run four parallel critics, optionally pull in research for non-obvious test patterns, then edit the story in place so that its acceptance criteria actually constrain a correct implementation, its TDD plan would catch a wrong one, and its prescribed implementation is easy to extend by addition (not by editing).

This is the **gate** between writing stories and executing them, the fourth stage of the five-skill pipeline:

```
roadmap-phase-designer → phase-architect → phase-story-writer → phase-story-validator → phase-story-executor
   (design phase)        (arch + ADRs)      (write stories)     (harden stories)        (execute stories)
                                                                  ← this skill →
```

## Why this skill exists

`phase-story-executor` is only as good as the story it executes. If an AC is vague ("handles errors gracefully"), the executor's Validator pass can't catch a bad implementation — there's nothing concrete to verify against. If a TDD plan's test is thin ("asserts the function returns a value"), the executor can write trivially wrong code and the test will pass.

The validator catches these failure modes *before* the executor wastes attempts on a story that was never well-specified. It is much cheaper to harden a story than to debug an executor that produced technically-passing-but-actually-wrong code.

## When this skill fires

Trigger when the user asks to validate, harden, audit, strengthen, review, or sanity-check a story. Phrases include:

- "Validate story S1-01" / "harden the next story" / "audit S2-01"
- "Are these ACs strong enough?" / "is this story ready to implement?"
- "Review the TDD plan for story X"
- "Sanity-check the next phase 0 story before we execute"
- Any user message that names a path inside `docs/phases/*/stories/` in a review-shaped context

**Story selection:**

- **Explicit path or ID** → use it directly
- **"Next story" / unspecified** → pick the lowest-numbered story in the active phase whose `Status` is *not* `Done` AND that does *not* already have a corresponding `_validation/{STORY-ID}.md` report. Print which story was picked.

One story per invocation. Looping at the user level keeps each validation isolated and auditable.

## Inputs

- A story file (e.g. `docs/phases/00-bullet-tracer-foundations/stories/S1-01-bootstrap-project.md`)
- Phase directory inferred from the path
- Optional: a `--depth` preference (`quick` skips Stage 3 research, `deep` always runs Stage 3 even when critics didn't request it)

## Outputs

1. **Edited story file** — ACs strengthened in place, TDD plan hardened, edge cases added. A new `Validation notes` block appended after the story header documenting every change and why.
2. **Validation report** at `docs/phases/{phase}/stories/_validation/{STORY-ID}.md` — the full audit log: critic reports, research findings (if any), edits applied with before/after snippets, final verdict.
3. **One of three verdicts** printed back to the user:
   - **STRONG** — story already passes all critics; no edits made; the validation report just records why.
   - **HARDENED** — story had real but fixable weaknesses; edits applied; ready for executor.
   - **RESCUE** — story has structural problems that can't be patched (e.g., the goal contradicts the phase arch, or ACs don't trace to the goal at all). Surface to user with the recommendation to re-run `phase-story-writer` or hand-edit. **No edits made** in this case — the validator does not silently rewrite something this broken.

## Workflow

Four stages. Stages 1 → 2 → 3 → 4 sequential; the four critics in Stage 2 run in parallel.

### Stage 1 — Context Loader

Read the story plus every doc it references. Build a one-page Context Brief, identical in spirit to the one used by `phase-story-executor` but with the validator's focus: what the story *promises*, what the phase's exit criteria *demand*, and what the arch + ADRs *constrain*.

→ See [`references/context-loader.md`](references/context-loader.md).

**Exit gate:** Context Brief written, ambiguities surfaced (if any) before proceeding.

### Stage 2 — Four parallel critics

Spawn four independent subagents in a single message. Each one reads only what its lens needs (token economy). Each produces a structured finding list.

| Critic | Lens | Reads |
|---|---|---|
| **Coverage** | Do the ACs collectively guarantee the goal? What edge cases are missing? Are any ACs vague or unverifiable? | story + arch design's goal section + phase exit criteria |
| **Test Quality** | Would the TDD plan's tests catch an obviously wrong implementation (mutation thinking)? Are any tests thin, tautological, or verifying-behavior-not-intent (Rule 9)? Are there hidden invariants suitable for property-based or metamorphic tests? | story + an adjacent test file from the codebase + the test-quality techniques file |
| **Consistency** | Does the story contradict the phase arch, any ADR, the production design, or a CLAUDE.md load-bearing commitment? Does each AC trace back to the goal? | story + arch design + referenced ADRs + CLAUDE.md + production design sections the story names |
| **Design Patterns** | Will the implementation this story prescribes be easy to maintain and extend by addition? Does it miss plugin / strategy / Open-Closed / DIP / hexagonal opportunities? Does it lock in anti-patterns (primitive obsession, anaemic types, hidden state, pure-impure tangle, untyped `dict` shuffling, deep inheritance)? Or does it push abstraction past Rule 2's "three similar lines is better than premature abstraction" threshold? | story (Implementation outline + Files to touch + Notes for implementer) + the nearest sibling module in the codebase + prior `_validation/` reports for the family + CLAUDE.md load-bearing commitments ("Extension by addition", etc.) |

→ See [`references/critic-coverage.md`](references/critic-coverage.md), [`references/critic-test-quality.md`](references/critic-test-quality.md), [`references/critic-consistency.md`](references/critic-consistency.md), [`references/critic-design-patterns.md`](references/critic-design-patterns.md).
→ See [`references/story-smells.md`](references/story-smells.md) — catalog of red-flag patterns every critic should scan for.
→ See [`references/techniques.md`](references/techniques.md) — mutation testing, property-based, metamorphic, INVEST, specification-by-example, design-quality vocabulary.

**Exit gate:** four critic reports landed; each finding tagged with severity (`block` / `harden` / `nit`) and a proposed fix or `NEEDS RESEARCH`.

### Stage 3 — Conditional Researcher

Fires only when at least one critic finding is tagged `NEEDS RESEARCH`. For each such finding, the researcher subagent looks up the canonical pattern via:

- WebSearch / WebFetch on arXiv for problem-domain-specific test methodology (e.g., "metamorphic testing concurrent systems", "property-based testing LLM outputs")
- Library docs (hypothesis, pytest-bdd, fastcheck, etc.) for idiomatic patterns
- Codebase Grep for prior precedents — has *this* repo solved something similar before?

Returns: a short brief with "recommended pattern, why, how to express in this story's TDD plan, sources." Cite arXiv IDs or doc URLs.

→ See [`references/researcher.md`](references/researcher.md).

**Skip Stage 3 entirely if no findings are tagged `NEEDS RESEARCH`** — research without a question is token-burn.

### Stage 4 — Synthesizer + Editor

Merge the four critic reports plus any research briefs. Resolve conflicts using the priority `Consistency > Coverage > Test-Quality > Design-Patterns` (source-of-truth dominates pattern advice — e.g., if Coverage says "add an empty-input AC" and Consistency says "the goal explicitly excludes empty inputs", Consistency wins; if Design-Patterns says "introduce a registry pattern" and Rule 2 / Consistency says "three similar lines is better than premature abstraction", the YAGNI position wins and the design opportunity is recorded in `Notes for the implementer` only).

Then *edit the story file in place*:

- Tighten vague ACs into verifiable assertions
- Add missing-edge-case ACs
- Rewrite thin tests in the TDD plan
- Add property-based or metamorphic test entries where applicable
- Surface design-pattern opportunities as `Notes for the implementer` paragraphs (don't add pattern names as ACs — ACs must be observable; pattern advice is contextual). When the design finding crosses the rule-of-three threshold (the third concrete consumer of a family), elevate the kernel/extract opportunity to an AC phrased as an *observable* constraint (e.g., "adding a new parser must require zero edits to `parsers/_io.py`") rather than as a pattern-name mandate.
- Append a `Validation notes` block under the story header recording every change

Write the full validation report to `_validation/{STORY-ID}.md`.

→ See [`references/editor.md`](references/editor.md).

**Exit gate:** verdict chosen (STRONG / HARDENED / RESCUE), report written, story file edited (HARDENED only), summary printed.

## What "good" looks like

A story is **STRONG** when:

- Every AC is *individually verifiable* (a third party could run a check and get a binary pass/fail)
- The AC set *collectively* guarantees the story's goal (no escape hatches)
- Every AC has at least one test in the TDD plan that would *fail* if a wrong implementation were swapped in (mutation-resistance)
- No AC is a tautology, a "no exception thrown" check, or a vague qualitative statement
- The TDD plan distinguishes intent-verifying tests from regression tests
- The story doesn't contradict the phase arch, any ADR, or CLAUDE.md
- Critical edge cases for the problem domain are listed (empty input, concurrency, error paths, large input, malformed input — whichever apply)
- The prescribed implementation consumes existing kernels / abstractions where they exist; introduces new ones only at the rule-of-three threshold; and leaves an explicit extension-by-addition path for the next sibling story (no "edit the kernel" cliffs for unsupported parser kinds / task classes / probe shapes)
- Domain identifiers (probe IDs, warning IDs, parser kinds, run IDs, paths-relative-to-repo-root) are typed (newtype / `Literal` / `StrEnum`) when they cross ≥ 2 module boundaries; pure logic is separable from I/O (functional core / imperative shell) when the goal admits it; data shapes don't permit illegal combinations a defensive reader has to check (tagged union > anaemic dict)

The validator's job is to move the story to this bar.

## Anti-goals (what this skill does NOT do)

- Does not implement the story (that's `phase-story-executor`)
- Does not rewrite the story's goal or scope (the original `phase-story-writer` output is authoritative on intent — if the goal is wrong, that's a `phase-story-writer` re-run)
- Does not add new ACs that weren't implied by the goal — only adds ACs that *enforce* the existing goal more strictly
- Does not commit (humans always merge — `docs/production/design.md` load-bearing commitment)
- Does not silently fold in adjacent improvements outside the story's scope (Rule 3 — surgical changes)

## Failure modes the skill handles explicitly

| Symptom | Action |
|---|---|
| Story has no ACs at all, or ACs don't trace to the goal at all | Verdict: RESCUE. No edits. Surface to user with re-run-the-writer suggestion. |
| All three critics return clean | Verdict: STRONG. Validation report explains *why* it's strong (so future stories can learn). |
| Two critics conflict (e.g., Coverage wants AC-7, Consistency says ADR-12 forbids it) | Consistency wins (source of truth is the arch/ADR). Edit the story to reflect that. Note the conflict resolution in the report. |
| `NEEDS RESEARCH` finding, but Stage 3 can't find a canonical pattern | Researcher returns "no canonical pattern found; here are two plausible options." Synthesizer surfaces the choice to the user inline, does NOT auto-pick. |
| Story already has a `_validation/{STORY-ID}.md` report | The story has already been validated. Confirm with user whether to re-validate. |
| Story file references docs that don't exist | Critic-Consistency flags it. Synthesizer surfaces. Does not auto-fix references that depend on missing files. |

## Composition with the rest of the pipeline

| Skill | Reads | Writes |
|---|---|---|
| `phase-story-writer` | arch design, ADRs, impl plan | `stories/{ID}.md` (first draft) |
| **`phase-story-validator`** (this skill) | `stories/{ID}.md` + every ref it names | edited `stories/{ID}.md`, `_validation/{ID}.md` |
| `phase-story-executor` | hardened `stories/{ID}.md` | code, `_attempts/{ID}.md`, `_lessons.md` |

The validator's output IS the executor's input. A story that has been through the validator is ready to be executed. A story that hasn't been validated *can* still be executed, but the executor will be at the mercy of whatever the writer produced.

## References

- [`references/context-loader.md`](references/context-loader.md) — what to read and how to build the Context Brief
- [`references/critic-coverage.md`](references/critic-coverage.md) — Stage 2A: AC coverage critic
- [`references/critic-test-quality.md`](references/critic-test-quality.md) — Stage 2B: TDD-plan test-quality critic
- [`references/critic-consistency.md`](references/critic-consistency.md) — Stage 2C: arch / ADR / commitment consistency critic
- [`references/critic-design-patterns.md`](references/critic-design-patterns.md) — Stage 2D: implementation-shape / design-pattern critic
- [`references/researcher.md`](references/researcher.md) — Stage 3 (conditional): arXiv + library-docs + codebase research
- [`references/editor.md`](references/editor.md) — Stage 4: synthesizer, edit-in-place rules, validation report format
- [`references/story-smells.md`](references/story-smells.md) — red-flag catalog every critic scans for
- [`references/techniques.md`](references/techniques.md) — mutation thinking, property-based, metamorphic, INVEST, specification-by-example, design-quality vocabulary
