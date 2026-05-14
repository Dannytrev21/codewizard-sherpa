# Implementer — Stage 2: ReAct + red-green-refactor TDD

Stage 2 writes the code. Two disciplines, layered:

- **Outer loop (reasoning):** ReAct — Thought → Action → Observation, repeated
- **Inner loop (test discipline):** red-green-refactor TDD per AC

## The outer ReAct loop

ReAct (Yao et al. 2022) is the simplest agentic loop that works for code. Every step is a triple:

```
THOUGHT: {why this step now, in one or two sentences}
ACTION: {single tool call — read a file, write code, run a test, run a linter}
OBSERVATION: {what came back — passing test, error, lint warning, diff applied}
THOUGHT: {what the observation means and what's next}
ACTION: ...
```

Every Thought must end with the **smallest verifiable next step**. Never collapse multiple Actions into one ("write all four files in one tool call") — you lose the ability to reason about each file's signal individually.

Write every Thought-Action-Observation triple into the working journal (`docs/phases/{phase}/stories/_attempts/{STORY-ID}.md`). See [`reflector.md`](reflector.md) for the journal format. The journal is what the next attempt — yours or someone else's — reads first.

## The inner red-green-refactor loop

For each acceptance criterion (or the smallest testable slice of one):

### 1. Red — write the failing test FIRST

- Open the test file the story names in "Files to touch"
- Write a test that captures the AC's *intent*, not just its mechanical behavior (Rule 9 — tests verify intent, not just behavior)
- The assertion should be something that would still hold if you swapped the implementation for any other reasonable one. If the assertion can only be true for the code you happened to write, the test is wrong.
- Run the test. **It MUST fail.** If it passes without any production code change, the test is wrong — strengthen it.
- Capture the exact failure output in the journal

### 2. Green — minimum code to pass

- Write the smallest possible code that makes the test pass
- Run the test. **It MUST pass.**
- Do not optimize. Do not add features the test doesn't exercise. Do not handle edge cases the AC doesn't ask for. (Rule 2 — simplicity first.)
- If the test passes "for the wrong reason" — e.g., the assertion is `assert result is not None` and your code returns `True` regardless of input — that's a Rule 9 violation. Go back to Red.

### 3. Refactor — tidy while green

- Improve naming, eliminate duplication, match conventions extracted in Stage 1.
- **Walk the design-patterns refactor checklist.** Spend ~60 seconds with [`design-patterns.md`](design-patterns.md) §"During Stage 2 refactor" open: raw `str` / `int` / `Any` for something semantic → newtype it; `if/elif` ladder over a closed variant set → tagged union or strategy; new dangerous operation re-implemented inline → route through (or add) a chokepoint module; broad `except Exception` / `except OSError` → narrow; mutable module-level state → `Final` or pass it explicitly; two-level deep inheritance → composition. Reinforce the patterns the codebase already uses (Plugin/Registry, Capability, Pipeline, Markers-only exceptions) rather than re-inventing them. **Do not** manufacture a pattern for a single use site — Rule 2 still wins.
- For each pattern you applied (or deliberately deferred), record one line under "Refactor decisions" in the attempt journal — e.g., "deferred Strategy registry for lockfile parsers; only one parser exists today."
- Behavior must not change. Run the full test suite after each refactor (not just the new test). Any regression = undo and try smaller.

### 4. Move to the next AC

Order: prefer the AC the TDD plan in the story lists first, or the AC with the fewest dependencies on other ACs. Don't write tests for 5 ACs at once — one at a time keeps the signal clean.

## ReAct anti-patterns to avoid

| Anti-pattern | Fix |
|---|---|
| **Action without Thought.** Calling tools to feel productive. | Every Action must be preceded by a one-sentence Thought naming the goal. |
| **Observation without re-evaluation.** Skipping the next Thought. | Every Observation deserves a Thought. If the Observation surprised you, name the surprise. |
| **Multi-step Action.** Writing 4 files in one tool call. | One file or one logical change per Action. You lose signal otherwise. |
| **Drift.** ReAct-ing for 10 cycles without rereading the AC. | Every 5 cycles, re-read the current AC verbatim. See "mid-stream Ralph Wiggum check" below. |

## Mid-stream Ralph Wiggum check

After every 5 ReAct cycles, take a 30-second break: re-read the current AC verbatim, then ask yourself the Ralph Wiggum question — "what would Ralph say this code is supposed to do?" If your latest code doesn't match Ralph's answer, surface the drift now in the journal. Don't wait for Stage 3 to catch it.

This is the mid-stream equivalent of Stage 3's full Ralph Wiggum pass. It's cheap and prevents big rollbacks later.

## When to ask for help vs keep iterating

Keep iterating as long as the **observation signal is changing**. New error messages, different test failures, lint cleaning up — keep going.

Stop and surface to the user if:

- The same test has failed 3 times with the same error and you've tried 3 different fixes — the assumption underneath is wrong
- A library doesn't behave the way you assumed and the docs don't clarify
- The story's TDD plan and the AC contradict each other
- Stage 1 marked an ambiguity that wasn't fully resolved

Write a "stuck" note in the journal, summarize what you tried, and surface. Rule 1 — no silent assumptions.

## Tool-use conventions

- **`Bash`** for running tests, linters, type-checkers — capture exit code and full output
- **`Read`** before `Edit` — never edit a file you haven't read
- **`Write`** only for new files. `Edit` for existing files.
- **Background long runs.** If a test suite takes >30s, run it with `run_in_background` and `Monitor` (or `BashOutput`) so you can keep reasoning.
- **One test run per change.** Don't batch 3 edits then one test — you lose the ability to bisect failures.

## Out-of-scope gravitational pull

When you're deep in code, it's tempting to also fix that obvious typo two lines up, or refactor that adjacent function, or add the missing docstring elsewhere. **Don't.** (Rule 3 — surgical changes.)

If you spot something genuinely worth fixing, log it in the journal under "Follow-ups surfaced this attempt" and keep moving. Stage 4 will surface them to the user as separate suggestions.
