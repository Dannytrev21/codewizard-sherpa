# Critic C — Consistency

Stage 2C. The Consistency critic's question: **does this story contradict anything the rest of the system has committed to?** Phase architecture, ADRs, production design, CLAUDE.md load-bearing commitments — any of those can be violated by a story that was written hastily or without cross-reference.

## What this critic reads

- The Context Brief (from Stage 1)
- The story file (fresh read)
- `docs/phases/{phase}/phase-arch-design.md` — full
- Every ADR the story names, in `docs/phases/{phase}/ADRs/` AND `docs/production/adrs/` — read Decision + Consequences sections
- `CLAUDE.md` at repo root — the load-bearing commitments section
- `docs/production/design.md` — only the sections the story names
- `docs/phases/{phase}/High-level-impl.md` — to confirm this story's step matches what was planned
- `docs/roadmap.md` — only the phase entry, to confirm task-class scope

## The questions to answer

1. **Does the story's goal match what `High-level-impl.md` planned for this step?**
   - The story should *implement* its planned step, not invent a new one. If it has expanded scope, that's a Consistency issue.
2. **Does any AC contradict a load-bearing commitment in CLAUDE.md?**
   - Examples that would be violations in codewizard-sherpa:
     - An AC that puts an LLM call in the gather pipeline (violates "No LLM anywhere in the gather pipeline")
     - An AC that has a probe write a *judgment* like "safe to migrate" (violates "Facts, not judgments")
     - An AC that requires editing existing probes to add a new language (violates "Extension by addition")
3. **Does any AC contradict a phase-level ADR?**
   - Read each referenced ADR's Decision. If the story's ACs are inconsistent with that decision, the story is wrong, OR the ADR is wrong, OR they're talking about different scopes. Flag it.
4. **Does any AC contradict a production ADR?**
   - Same check, broader scope. The phase's design is supposed to be consistent with production; if an AC drifts, surface it.
5. **Does each AC trace back to *something* (goal, exit criterion, ADR consequence)?**
   - Orphan ACs — ones with no upstream source — are usually either scope creep or leftovers from an earlier draft. Either way, they shouldn't be acted on.
6. **Does the story name files in "Files to touch" that are inconsistent with the arch design's Component design section?**
   - If the arch says "Layer A probes live in `src/codegenie/probes/layer_a/`" and the story creates a probe at `src/codegenie/probes/foo.py`, that's a Consistency violation.
7. **Does the story respect Out-of-scope from the phase-arch-design?**
   - The phase has its own Out-of-scope (Non-goals) section. Stories shouldn't accidentally implement a non-goal.

## Common consistency failures to watch for

- **Scope creep**: story does too much. Often shows up as the goal saying "do X" but the ACs covering X *and* Y. Flag Y.
- **Drift from ADRs**: ADR-0007 says "the probe contract is preserved across POC and service" → the story shouldn't add a probe method that exists only in the POC harness
- **Stale references**: story names an ADR by number that doesn't exist, or an arch section that has been renamed
- **Implicit dependency on un-shipped work**: story requires a config knob that another (later-numbered) story is supposed to add
- **Wrong task class**: story for Phase 3 (vulnerability remediation) implements a Phase 7 (migration) concern. Surface — this should be a separate story in Phase 7.

## Cross-reference traceability check

For every AC, the Consistency critic should be able to say *one of these*:

- "Traces to story goal (which traces to High-level-impl step N, which traces to phase exit criterion X)"
- "Traces to ADR-NNNN consequence Y"
- "Traces to CLAUDE.md commitment Z"
- "Does NOT trace — orphan AC — flag"

If you can't make one of these statements for an AC, it's a finding.

## Finding format

```markdown
## Consistency critic findings — {STORY-ID}

### F1 — AC-5 conflicts with ADR-0005
- **Severity:** block
- **What's wrong:** AC-5 reads "if no LanguageDetection result is found in the cache, the LLM fallback infers the language from filenames". ADR-0005 (No LLM in the gather pipeline) prohibits any LLM call in the gather codepath. The story's AC introduces one.
- **Proposed fix:** Replace with: "if no LanguageDetection result is found, the probe re-runs synchronously; if the probe still produces no result, the field is `null` with `provenance: 'unknown'`". Trace to ADR-0005 in the AC text.
- **Confidence:** high
- **Source:** ADR-0005 Decision + the story's AC-5

### F2 — Files to touch list doesn't match arch design's component layout
- **Severity:** harden
- **What's wrong:** Story lists `src/codegenie/probes/node_build_system.py`. phase-arch-design.md §Component design specifies Layer A probes live in `src/codegenie/probes/layer_a/`.
- **Proposed fix:** Update Files-to-touch to `src/codegenie/probes/layer_a/node_build_system.py`
- **Confidence:** high
- **Source:** phase-arch-design.md §"Component design — file layout"

### F3 — AC-2 doesn't trace anywhere
- **Severity:** harden
- **What's wrong:** AC-2 requires the CLI to emit a colored success banner. Nothing in the goal, no ADR, no CLAUDE.md commitment, no exit criterion mentions UX banners. Looks like leftover scope creep.
- **Proposed fix:** Remove AC-2, OR add a sentence to the story goal explaining why the banner is part of the story (and then we trace).
- **Confidence:** medium
- **Source:** traceability check — no upstream found
```

Severity tags match the other critics: `block`, `harden`, `nit`, `NEEDS RESEARCH`.

`NEEDS RESEARCH` is rare for this critic — consistency is usually answered by reading existing docs, not by external research. But if a story names a domain technique that the critic doesn't recognize (e.g., "use SCIP for cross-repo indexing"), flagging it as `NEEDS RESEARCH` is fine.

## What this critic is NOT for

- Not for finding new ACs the story is missing (that's Coverage)
- Not for assessing test quality (that's Test-Quality)
- Not for stylistic objections — only commitments and constraints with sources
- Not for arguing about which ADR is *correct* — the ADRs are authoritative; if the story is wrong, the story is wrong. (Disagreement with an ADR is a separate ADR-supersession conversation, not a story-validation conversation.)
