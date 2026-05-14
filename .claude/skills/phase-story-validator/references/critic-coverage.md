# Critic A — Coverage

Stage 2A. The Coverage critic's question is binary: **if every AC in this story passes, is the story's goal guaranteed?** If not, what's missing.

## What this critic reads

- The Context Brief (passed in by Stage 1)
- The story file itself (read it fresh — don't take the Context Brief's restatements on faith)
- `docs/phases/{phase}/phase-arch-design.md` — Goal section, Non-goals section, Exit criteria section
- `docs/phases/{phase}/High-level-impl.md` — find this story's step and read its `done-criteria`
- `references/story-smells.md` — for the catalog of coverage-shaped red flags

## The questions to answer

For each AC:

1. **Is it individually verifiable?**
   - Could a third party with no domain knowledge run a check and get a binary pass/fail?
   - "Handles errors gracefully" — NO (subjective). "Returns `Result.Err` with `kind = TIMEOUT` when the request exceeds 5000ms" — YES.
2. **Does it trace to the goal?**
   - If you removed this AC, would the goal still be satisfiable? If yes, it's at minimum redundant; if it actually contradicts the goal, it's a coverage bug.
3. **Is it the right grain?**
   - Too coarse: "the CLI works correctly" — useless
   - Too fine: a dozen ACs each asserting one line of code — over-specifies and constrains the implementation
   - Right grain: each AC names *one observable behavior* the story must produce

For the AC set as a whole:

4. **Does the union of ACs imply the goal?**
   - Imagine an implementation that satisfies every AC literally and minimally. Does that implementation accomplish the goal? If yes, coverage is sufficient. If no, identify what's missing.
5. **What's missing — by category?**
   - **Happy-path coverage**: the obvious "this is what it does"
   - **Edge cases**: empty input, max-size input, single-element input, boundary values
   - **Error paths**: malformed input, dependency unavailable, timeout, partial failure
   - **Concurrency** (if relevant): two callers at once, mid-operation cancellation
   - **Idempotency / replay** (if relevant): running the operation twice yields the same result, or the second run is a no-op, or the second run errors clearly
   - **Negative space**: things the story should *refuse* to do — often missing entirely
6. **Does the story's "Out of scope" section actually exclude things, or is it empty/vague?**
   - Empty out-of-scope is a smell — every meaningful story has *some* things it intentionally doesn't do.

## How to find missing edge cases

For each AC's verb (returns, computes, fetches, writes, emits, raises, retries), brainstorm the cases:

| Verb | Edge cases to consider |
|---|---|
| **Returns** | empty input → empty output? singleton input? max-size? type errors? |
| **Computes** | identity element? overflow? precision loss? non-commutative inputs? |
| **Fetches** | dependency down? timeout? rate-limited? partial response? cache hit vs miss? |
| **Writes** | target already exists? target read-only? interrupted mid-write? concurrent writer? |
| **Emits** | empty stream? closed sink? backpressure? duplicate events? |
| **Raises** | when *exactly*? what error type? what message? |
| **Retries** | how many times? backoff? what error classes trigger retry? what's the post-retry state? |

If the story's ACs don't address any of these for a verb the goal implies, flag it.

## The "obviously wrong implementation" thought experiment

The most useful question Coverage can ask: **"What's the laziest, most obviously wrong implementation that satisfies every literal AC?"**

Construct it in your head (or in your finding). If that lazy implementation would actually fail the goal but pass every AC, the ACs underspecify.

**Example:**
- Goal: "the CLI gather command produces a `repo-context.yaml` with detected languages"
- AC: "the CLI exits with code 0 and writes `.codegenie/context/repo-context.yaml`"
- Lazy impl: `touch .codegenie/context/repo-context.yaml; exit 0` — passes the AC, fails the goal.
- Missing AC: "the yaml file contains a `detected_languages` key with at least one entry when run in a repository containing source files"

## Finding format

Output a structured list. Use this format so the Synthesizer (Stage 4) can merge easily.

```markdown
## Coverage critic findings — {STORY-ID}

### F1 — AC-3 is unverifiable
- **Severity:** block
- **What's wrong:** AC-3 reads "handles malformed input gracefully" — no observable behavior named
- **Proposed fix:** Replace with "when input file is not valid YAML, the CLI exits with code 2 and prints to stderr `error: {path} is not valid YAML: {parser error}`"
- **Confidence:** high
- **Source:** AC-3 of story

### F2 — Missing empty-input AC
- **Severity:** harden
- **What's wrong:** Goal implies handling any directory; ACs assume a populated directory
- **Proposed fix:** Add AC: "given an empty directory, the CLI exits with code 0 and writes a yaml with `detected_languages: []`"
- **Confidence:** high
- **Source:** lazy-impl thought experiment

### F3 — Concurrency contract unspecified
- **Severity:** NEEDS RESEARCH
- **What's wrong:** Story doesn't say what happens if two `codegenie gather` invocations run concurrently against the same repo
- **Proposed fix:** unknown — depends on whether the cache layer (ADR-NNNN) guarantees per-process isolation
- **Confidence:** low
- **Source:** edge-case brainstorm; defers to researcher
```

Severity:
- **block** — the story should not go to the executor without this fix (broken AC, contradiction with goal)
- **harden** — fixable in place; not a blocker but should be patched
- **nit** — small clarification; defer if Synthesizer is under budget
- **NEEDS RESEARCH** — Coverage doesn't know the right answer; Stage 3 should look it up
