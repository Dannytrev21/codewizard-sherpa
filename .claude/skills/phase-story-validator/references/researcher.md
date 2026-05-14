# Researcher — Stage 3 (Conditional)

Stage 3 fires only when at least one critic finding from Stage 2 is tagged `NEEDS RESEARCH`. The researcher's job is to look up the canonical pattern for the problem the critic flagged — in arXiv, in library docs, or in the codebase's own history — and return a brief that the Synthesizer (Stage 4) can use to propose a fix.

**Skip Stage 3 entirely if no `NEEDS RESEARCH` findings exist.** Research for its own sake is token-burn.

## What this stage reads

For each `NEEDS RESEARCH` finding, in this priority order:

1. **The codebase itself** — has this repo solved something similar before?
   - `Grep` for related concepts (`grep -ri "metamorphic"`, `grep -ri "property-based"`, etc.)
   - Look in `docs/` for design docs or prior ADRs that touched the same domain
   - This is the highest-signal source — same project, same conventions, same constraints

2. **Library / framework docs** — what's the idiomatic pattern in the tool we already use?
   - `WebFetch` the documentation site for the library named in the finding (e.g., `hypothesis`, `pytest-asyncio`, `pact`)
   - Look specifically for the pattern that addresses the critic's concern

3. **arXiv** — what does the research literature say?
   - `WebSearch` for the problem-domain keywords (e.g., "metamorphic testing concurrent systems", "property-based testing LLM outputs site:arxiv.org")
   - Read abstracts; pull the most-cited or most-recent paper that directly addresses the concern
   - Cite arXiv IDs (e.g., 2210.03629) so the Synthesizer can include them in the validation report

4. **Authoritative blog / handbook** — if no academic source, look for industry-standard writeups
   - Hillel Wayne on property testing, Martin Fowler on test doubles, Kent Beck on TDD — these are canonical
   - Cite by URL and author

## When to use each source

| Source | Use when |
|---|---|
| Codebase | The concern is "how does this repo usually handle X" |
| Library docs | The concern is "what's the idiomatic way to use {dependency} for X" |
| arXiv | The concern is "what's the right *methodology* for testing/validating X" — especially when X is non-obvious (concurrency, ML, distributed systems, security properties) |
| Industry handbook | The concern is "what's the canonical pattern" and arXiv would be overkill |

## What to look for, by concern category

### Concurrency / determinism
- arXiv: "deterministic testing concurrent", "linearizability testing"
- Hillel Wayne's writing on TLA+ and property testing
- libraries: `hypothesis` stateful testing, `pytest-asyncio`

### Test oracles when "right answer" is hard
- arXiv: "metamorphic testing" (Chen et al. 1998, foundational)
- Chen, T.Y. et al. "Metamorphic Testing: A Review of Challenges and Opportunities"

### Property-based test design
- Claessen & Hughes 2000 "QuickCheck" (foundational paper)
- `hypothesis` library docs
- Hillel Wayne, "Crafting Test-Resistant Code"

### LLM-output testing
- This is genuinely an open problem — research is recent
- arXiv: "evaluation LLM outputs", "behavior testing language models"
- Note: most reliable approach is "test invariants of the output structure (shape, schema) + spot-check semantic content" rather than asserting on exact strings

### Security / safety properties
- arXiv: "property-based security testing", "differential testing"
- OWASP testing guide for web concerns
- libraries: `bandit`, `semgrep` rules

### Distributed systems / consensus
- arXiv: "Jepsen", "FoundationDB simulation testing"
- Aphyr's blog (Kyle Kingsbury) for canonical pattern writeups

## Researcher output format

For each `NEEDS RESEARCH` finding, produce a short brief:

```markdown
## Research brief — F{N} from {Critic}

### The question
{The critic's finding restated in one sentence as a research question}

### Canonical pattern
{The pattern, in one paragraph. Specific enough that the Synthesizer can write a concrete AC or test using it.}

### Why this pattern
{One sentence on why it addresses the critic's concern}

### How to express in this story's TDD plan
{Concrete sketch of the AC or test entry the Synthesizer should propose}

### Sources
- {arXiv ID or URL} — {one-line context: title + authors + relevance}
- {library doc URL} — {what to read there}
- {codebase precedent path:line} — {what's similar there}

### Confidence
high / medium / low — with one-line reason
```

## Anti-patterns for this stage

- **Researching when the critic already proposed a fix.** If the critic tagged `block` or `harden` with a clear `Proposed fix`, don't research it — the answer is already in the finding.
- **Citing without reading.** If you cite an arXiv paper, you should have read at least the abstract and the relevant section. A bare citation with no synthesis is noise.
- **Bringing in techniques the project hasn't agreed to use.** If the story is in a Python codebase using pytest+hypothesis, don't propose Haskell QuickCheck. Match the codebase's conventions (Rule 11).
- **Researching style questions.** "Should we use `def` or `lambda`?" doesn't need arXiv. Style is captured in CLAUDE.md and existing code; defer to those.
- **Treating "no canonical pattern" as failure.** If you genuinely can't find a canonical pattern for an unusual concern, return that honestly: "no canonical pattern found; two plausible options are A and B." The Synthesizer will then surface the choice to the user. (Rule 12 — fail loud.)

## Token economy

Each research brief should be small — under ~400 tokens. The point is to give the Synthesizer just enough to draft a fix, not to write a literature survey. If a finding genuinely needs a deep dive, surface that to the user with the suggestion to handle it as a separate research task.
