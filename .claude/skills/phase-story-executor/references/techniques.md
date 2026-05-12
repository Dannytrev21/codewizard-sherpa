# Reasoning techniques — when to use which

This skill leans on several published reasoning techniques. Brief explainers and when each fires.

## ReAct (Reasoning + Acting) — Yao et al. 2022

**Pattern:** Thought → Action → Observation, repeated. Every Action is preceded by a Thought naming the goal and followed by an Observation re-evaluating the result.

**Used in:** Stage 2 (Implementer) as the outer loop. Every code-writing or tool-running step lives inside a ReAct cycle.

**Why it works:** Forces the model to articulate intent before acting and to re-assess after each tool call. Catches drift early — the cost of one extra Thought is tiny compared to the cost of writing the wrong code for 20 minutes.

**Anti-pattern:** Multi-Action steps ("write all 4 files in one tool call") — you lose the ability to reason about each file's signal individually.

**Source:** Yao, S. et al. "ReAct: Synergizing Reasoning and Acting in Language Models." 2022. https://arxiv.org/abs/2210.03629

## Ralph Wiggum — naive verification

**Pattern:** Restate a claim in the simplest, most literal terms (the way Ralph Wiggum, the Simpsons character known for childlike directness, would describe it). Then verify the literal restatement against runtime behavior — not against the code itself.

**Used in:** Stage 3 (Validator) as the primary frame. Also as a mid-stream check every ~5 ReAct cycles in Stage 2 to prevent drift.

**Why it works:** Fights the Implementer's confirmation bias ("I just built this, of course it works"). The naivety is the point — by refusing to take the Implementer's framing on faith, the Validator surfaces hidden assumptions.

**Variant:** "Explain it like I'm five" / rubber-duck debugging share the same shape. Ralph Wiggum emphasizes *literal naivety*, not just simplicity — the goal isn't to be a kind teacher, it's to refuse to fill in any gaps.

**No formal paper.** This is informal craft. The closest formal analog is "naive Bayesian belief updating" or human-in-the-loop adversarial review.

## Reflexion — Shinn et al. 2023

**Pattern:** After a failed attempt, the agent writes a verbal reflection ("what went wrong, what I'd try differently next time") and stores it. The next attempt reads the reflection first.

**Used in:** Between Stage 3 fails and Stage 2 retries (within the 3-attempt cap), and Stage 4 attempt-log writing. The `_attempts/{STORY-ID}.md` journal is the operational implementation of Reflexion.

**Why it works:** Pure ReAct doesn't carry lessons across attempts — each attempt starts fresh. Reflexion does, and that's how the second attempt can avoid repeating the first attempt's mistake.

**Source:** Shinn, N. et al. "Reflexion: Language Agents with Verbal Reinforcement Learning." 2023. https://arxiv.org/abs/2303.11366

## Chain-of-Verification (CoV) — Dhuliawala et al. 2023

**Pattern:** Generate verification questions for your own claim, answer each one independently, check consistency.

**Used in:** Stage 3, supplementary to Ralph Wiggum, for ACs with multiple parts or hidden corners.

**Example:** For an AC "the cache key is content-addressed and deterministic across machines":
1. Generate questions: "what content is hashed?", "what hash function?", "is the hash deterministic across OSes?", "what about line-ending differences?"
2. Answer each independently from the code
3. Check the answers don't contradict each other or the AC

**Why it works:** Surfaces hidden assumptions the Implementer baked in but didn't make explicit.

**Source:** Dhuliawala, S. et al. "Chain-of-Verification Reduces Hallucination in Large Language Models." 2023. https://arxiv.org/abs/2309.11495

## Self-consistency — Wang et al. 2022

**Pattern:** Sample multiple chains of reasoning for the same question; pick the answer that appears most often.

**Used in:** Sparingly. Only when an ambiguous AC has multiple plausible interpretations *and* the user can't be reached for clarification. Sample 3 interpretations, pick the one that aligns with the story's TDD plan and the phase's exit criteria.

**Default behavior:** surface ambiguity to the user (Rule 1 — no silent assumptions). Self-consistency is a fallback when the cost of pausing exceeds the cost of getting it slightly wrong.

**Source:** Wang, X. et al. "Self-Consistency Improves Chain of Thought Reasoning in Language Models." 2022. https://arxiv.org/abs/2203.11171

## When NOT to use a model at all

Per Rule 5 ("use the model only for judgment calls"), deterministic transforms shouldn't go through the LLM:

| Task | Tool, not model |
|---|---|
| Parse JSON / YAML / TOML | language's parser |
| Discover tests | `pytest --collect-only` |
| Find files | `find` / `glob` |
| Check syntax | `python -c "import ast; ast.parse(...)"` / `tsc --noEmit` |
| Lint | `ruff check` |
| Type-check | `mypy` |
| Compute hashes | `hashlib` / `xxhash` / `blake3` |
| Path manipulation | `pathlib` |
| Process exit codes | `$?` / `result.returncode` |

The model is for **judgment** ("is this AC actually met?"), **drafting** ("commit message", "attempt log entry"), **summarization** ("one-paragraph user-facing summary"), and **extraction** ("what files does this story reference?"). Nothing else.

## Picking which technique to use

| Situation | Technique |
|---|---|
| Implementing — building the code | **ReAct** (always) + **red-green-refactor TDD** (always) |
| Implementing — checking yourself mid-stream | **Ralph Wiggum check** every ~5 ReAct cycles |
| Validating — primary frame | **Ralph Wiggum** for every AC |
| Validating — complex AC with multiple parts | **Chain-of-Verification** on top of Ralph Wiggum |
| Between attempts | **Reflexion** via attempt-log carry-forward |
| Ambiguous AC, user unreachable | **Self-consistency** sample-3-and-pick |
| Deterministic transform | **No LLM** — use plain code |

## Notes on technique stacking

These techniques compose. A typical successful story execution looks like:

1. Stage 1 reads with no special technique — just disciplined reading
2. Stage 2 uses **ReAct** outer + **red-green-refactor** inner + **mid-stream Ralph Wiggum** every ~5 cycles
3. Stage 3 uses **Ralph Wiggum** for every AC, plus **CoV** for complex ones, plus the cross-cutting gates
4. Between Stage 3 fail and Stage 2 retry, **Reflexion** carries the lesson forward via the journal
5. Stage 4 uses no special technique — just writes the artifacts

The stack is the point. No single technique is sufficient. Together they catch what each one alone misses.
