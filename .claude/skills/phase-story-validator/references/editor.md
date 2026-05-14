# Synthesizer + Editor — Stage 4

Stage 4 merges the three critic reports + any research briefs and edits the story file in place. Also writes the full validation report. Picks the verdict.

## Inputs to this stage

- Four critic reports (Coverage, Test-Quality, Consistency, Design-Patterns)
- Optional set of research briefs (Stage 3 output) — one per `NEEDS RESEARCH` finding
- The original story file (read fresh — don't trust your memory of it)
- The Context Brief from Stage 1

## Synthesis algorithm

### Step 1 — Collect findings

Aggregate every finding from the four critics into a single list. Each finding has:
- Source critic (Coverage / Test-Quality / Consistency / Design-Patterns)
- Severity (block / harden / nit / NEEDS RESEARCH)
- Proposed fix (or, if `NEEDS RESEARCH`, the matching research brief's fix sketch)

Then count by severity:

| Severity | Count | Implication |
|---|---|---|
| block, total | ≥1 → consider RESCUE candidate; ≥3 → likely RESCUE | These are hard blockers. If they can't be fixed in place, the story is too broken. |
| harden, total | Any → HARDENED candidate | These are the bread-and-butter edits. |
| nit, total | Any → fix if cheap; defer if not | Don't burn time on these. |

### Step 2 — Resolve conflicts between critics

If two findings propose contradictory fixes, apply this priority:

1. **Consistency wins over Coverage, Test-Quality, and Design-Patterns.** If Coverage wants an AC that Consistency says contradicts an ADR, the ADR wins. Same for any Design-Patterns proposal that would violate a load-bearing arch decision (e.g., introducing a registry pattern when an ADR explicitly rejected one). Drop or modify the lower-priority finding.
2. **Coverage wins over Test-Quality on AC content.** If Test-Quality wants to test something Coverage says is out of scope, drop the test.
3. **Test-Quality wins over Coverage on AC phrasing.** If Coverage proposes an AC but Test-Quality says "that wording is too weak to test against", reword the AC using Test-Quality's language.
4. **Coverage / Test-Quality / Consistency win over Design-Patterns on AC content.** Pattern proposals NEVER add new ACs that don't trace to the goal. If Design-Patterns proposes "introduce a `Parser` ABC", that's an *implementation* opinion — its place is in `Notes for the implementer`, not in a new AC. The Design-Patterns critic may, however, propose an *observable* AC like "adding a new parser must require zero edits to `parsers/_io.py`" — that's a behaviour, not a pattern name, and is acceptable.
5. **Rule 2 (Simplicity First) wins over Design-Patterns** when a finding asks for scaffolding ahead of the rule-of-three threshold. If only one or two concrete consumers of a would-be abstraction exist, demote the finding from `harden` to `nit` and surface as a `Notes for the implementer` paragraph, NOT as an AC. Only mandate the kernel/extract when the third concrete consumer arrives (the validator should look at the prior `_validation/` reports for the family to count occurrences).
6. **Design-Patterns wins over silence on extension-by-addition violations.** If Coverage / Test-Quality / Consistency are clean but the implementation outline bakes in an Open/Closed violation (kernel must be edited to add the next sibling), the Design-Patterns critic's `harden` finding stands and the story is HARDENED, not STRONG.

Record every conflict + resolution in the validation report. The synthesis priority chain is: `Consistency > Coverage > Test-Quality > Design-Patterns`.

### Step 3 — Pick the verdict

- **STRONG** — zero findings of any severity. No edits. Validation report says why.
- **HARDENED** — at least one `harden`/`nit` finding, OR `block` findings that have clear in-place fixes (after research, if any). Edits applied; story ready for executor.
- **RESCUE** — `block` findings whose fixes require rewriting the story's *goal*, not just its ACs. E.g.:
  - Story's goal contradicts the phase arch
  - ACs don't trace to the goal at all (the entire AC set is orphan)
  - Story implements a non-goal of the phase
  - More than ~3 `block` findings even after research

In RESCUE: do NOT edit the story. Write a validation report explaining why, recommending re-running `phase-story-writer` for this step OR hand-editing the story's goal.

### Step 4 — Apply the edits (HARDENED only)

Edit the story file in place using `Edit`. Specific operations:

#### Strengthening a weak AC
Replace the existing AC text with the stronger version proposed by Coverage or Test-Quality. Keep the AC numbering stable — don't renumber existing ACs (downstream references would break). If a new AC is being added, append it with the next available number.

Before:
```
- [ ] AC-3: handles errors gracefully
```

After:
```
- [ ] AC-3: when input file is not valid YAML, the CLI exits with code 2 and prints to stderr `error: {path} is not valid YAML: {parser error}` (validator: hardened from original "handles errors gracefully")
```

The trailing parenthetical is intentional — it preserves a breadcrumb so a future reader can see what changed.

#### Adding a missing AC
Append at the end of the AC list. New AC gets the next number:

```
- [ ] AC-7: given an empty directory, the CLI exits with code 0 and writes `.codegenie/context/repo-context.yaml` with `detected_languages: []` (validator: added — empty-input edge case)
```

#### Rewriting a thin test in the TDD plan
Locate the test entry in the TDD plan section. Replace its content:

Before:
```
- Test 1 (test_language_detection_finds_typescript): create a .ts file, assert detected_languages contains 'typescript'
```

After:
```
- Test 1 (test_language_detection_finds_typescript_across_extensions): given a directory with `app.ts`, `component.tsx`, and `script.mts`, assert `detected_languages` contains 'typescript' AND the evidence field cites all three file extensions. (validator: hardened — original test could be satisfied by a detector that only matched `.ts`)
```

#### Adding a property-based or metamorphic test
Append to the TDD plan with explicit framework:

```
- Test 5 (test_cache_key_is_deterministic, property-based via hypothesis): generate arbitrary nested dicts of file metadata using `st.dictionaries(...)`; assert `hash(metadata) == hash(metadata)` (idempotence) AND `hash(metadata_a) != hash(metadata_b)` when `metadata_a != metadata_b` (no collisions across distinct inputs). (validator: added — cache-key determinism is a property suitable for generative testing)
```

#### Surfacing a design-pattern opportunity (Notes for the implementer)
Design-pattern findings usually land here, NOT as a new AC. Append to (or extend the existing) `Notes for the implementer` section:

```markdown
- **Plugin / strategy framing.** This is the third concrete parser after `safe_json` (S1-02) and `safe_yaml` (S1-03). The kernel established by S1-03's hardening — `parsers/_io.py` (O_NOFOLLOW + size cap + structlog event) and `parsers/_depth.py` (post-parse walker) — should be consumed here. The parser-specific shape (the comment stripper) is the only new logic. New parsers added by **new file + new `parser_kind` literal**; no edits to existing parsers (Open/Closed; "Extension by addition" — CLAUDE.md). No `ParserRegistry`, no factory, no `Parser` ABC — the `parser_kind` discriminator on the structlog event is the strategy's identity.
```

When the design finding crosses the rule-of-three threshold and the kernel/extract is now mandatory, ALSO add an *observable* AC stating the behaviour (not the pattern name):

```
- [ ] AC-N — Adding a new parser sibling under `src/codegenie/parsers/*.py` requires zero edits to `parsers/_io.py` and `parsers/_depth.py`. (validator: added — extension-by-addition AC; pattern: plugin / strategy)
```

The AC asserts the behaviour; the parenthetical names the pattern for reviewers. Avoid ACs that read "use the Strategy pattern" — pattern names aren't testable.

#### Append a "Validation notes" block

Under the story's header block (the one with `Status`, `Estimate`, etc.), insert a new block titled `Validation notes`:

```markdown
## Validation notes

Validated: {YYYY-MM-DD}
Verdict: HARDENED
Findings addressed: {N total — {block} blocks, {harden} hardens, {nit} nits}

Changes applied:
- AC-3 strengthened (was: "handles errors gracefully") — Coverage finding F1
- AC-7 added (empty-input edge case) — Coverage finding F2
- Test 1 hardened (covers .tsx and .mts) — Test-Quality finding F1
- Test 5 added (property-based cache-key test) — Test-Quality finding F2 + research brief
- File path fixed: probes/node_build_system.py → probes/layer_a/node_build_system.py — Consistency finding F2

Full audit log: docs/phases/{phase}/stories/_validation/{STORY-ID}.md
```

### Step 5 — Write the validation report

Always write the report, regardless of verdict. Location: `docs/phases/{phase}/stories/_validation/{STORY-ID}.md`. Create the `_validation/` directory if it doesn't exist.

Report template:

```markdown
# Validation report: {STORY-ID} — {short title}

**Validated:** {YYYY-MM-DD HH:MM}
**Verdict:** STRONG | HARDENED | RESCUE
**Validator version:** phase-story-validator v1

## Summary

{One paragraph: what the story is, what we found, what we did about it. Plain English.}

## Findings by critic

### Coverage critic
{paste the Coverage findings block verbatim}

### Test-Quality critic
{paste the Test-Quality findings block verbatim}

### Consistency critic
{paste the Consistency findings block verbatim}

### Design-Patterns critic
{paste the Design-Patterns findings block verbatim}

## Research briefs (if any)
{paste each research brief}

## Conflict resolutions
{any cases where critics disagreed and how the resolution was picked}

## Edits applied (HARDENED only — empty for STRONG; "no edits — see verdict" for RESCUE)

### Edit 1 — AC-3 strengthened
- Source: Coverage F1
- Before: `handles errors gracefully`
- After: `when input file is not valid YAML, the CLI exits with code 2 and prints to stderr ...`
- Rationale: original AC was unverifiable; replaced with observable contract

### Edit 2 — ...

## Verdict rationale

{Why STRONG / HARDENED / RESCUE — one paragraph}

## Recommended next step

- STRONG / HARDENED → `phase-story-executor` to implement
- RESCUE → re-run `phase-story-writer` for this step, OR hand-edit the goal and resubmit
```

### Step 6 — Print the user-facing summary

Short, scannable:

> **Story {STORY-ID} — verdict: HARDENED**
>
> Found {N} findings ({n_block} blockers, {n_harden} hardens, {n_nit} nits).
> Applied {M} edits to the story file.
> Research consulted: {none | brief titles}.
>
> Story is ready for `phase-story-executor`. Audit log at `_validation/{STORY-ID}.md`.

Or for RESCUE:

> **Story {STORY-ID} — verdict: RESCUE**
>
> Found {N} structural issues that can't be patched in place:
> - {bullet}
> - {bullet}
>
> Recommend re-running `phase-story-writer` for this step, OR hand-editing the goal.
> Detailed analysis at `_validation/{STORY-ID}.md`.

## What Stage 4 must NOT do

- Do not commit. Humans always merge (`docs/production/design.md` load-bearing commitment).
- Do not rewrite the story's goal or scope. Those are `phase-story-writer`'s responsibility. If the goal is wrong, that's a RESCUE.
- Do not delete or renumber existing ACs (downstream references would break — the executor's attempt log may reference AC numbers).
- Do not add ACs that don't trace to the existing goal (scope creep).
- Do not silently fold in adjacent improvements to other stories (Rule 3 — surgical changes).
- Do not edit anything outside the one story file and the `_validation/{STORY-ID}.md` file.
