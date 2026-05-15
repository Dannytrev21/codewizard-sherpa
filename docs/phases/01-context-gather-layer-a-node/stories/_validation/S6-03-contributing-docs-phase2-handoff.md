# Validation report — S6-03 (Contributor docs cheat sheet + Phase 2 follow-up issues + Phase 1 README close)

**Date:** 2026-05-15
**Verdict:** HARDENED
**Skill:** phase-story-validator
**Story file:** [`../S6-03-contributing-docs-phase2-handoff.md`](../S6-03-contributing-docs-phase2-handoff.md)

---

## Stage 1 — Context Brief

### Goal restated
Update `docs/contributing.md` with an "adding a probe" cheat sheet section pointing at Phase 1 probes as canonical examples; file the five Phase 2 follow-up issues on the GitHub Project board aligned to `roadmap.md §"Phase 2"`; mark the Phase 1 README's exit-criteria checklist complete so the phase is closed.

### What the phase arch + ADRs constrain
- ADR-0002 (memo seam Phase 2 inherits — allowlist additive growth path)
- ADR-0004 (per-probe sub-schema `additionalProperties: false` at root)
- ADR-0005 (coverage carve-outs require their own ADR amendment)
- ADR-0006 (catalog versioning Phase 7 may extend)
- ADR-0007 (warning-ID pattern; Phase 2 promotes to enum per open question #7)
- `phase-arch-design.md §"Goals"` (10 numbered goals — the canonical exit-criteria source)
- `phase-arch-design.md §"Open questions deferred to implementation"` items 2, 7, 8 — three of the five filed Phase 2 issues
- CLAUDE.md "Extension by addition" — issues must name new files / extension surfaces, never edits to existing components
- CLAUDE.md "Organizational uniqueness as data, not prompts" — applies recursively to the cheat sheet itself

### On-disk facts that contradicted the story
1. **`docs/phases/01-context-gather-layer-a-node/README.md` has zero `[ ]` markers** — there is no exit-criteria checklist to "tick complete." Phase 0's README has the precedent shape (`## Exit criteria` + `## Handoff record` H2s) per S5-02 AC-8.
2. **`docs/contributing.md` already has `## Adding a probe` H2** at line 69 (Phase 0 / S4-01 worked-example for `LanguageDetectionProbe`). A second H2 with the same name would be invalid Markdown.
3. **`docs/contributing.md` lines 131–135 ratchet schedule is stale** (publishes Phase 1 = 87/77, Phase 2 = 90/80) while S6-02 actually shipped Phase 1 = 90/80 with carve-outs and this story files an issue for Phase 2 = 92/82.
4. **`mkdocs.yml:47`** already nav-includes `contributing.md` — AC-6's "if absent, add" branch is dead code in the implementation outline.
5. **`gh` issue creation** is an irreversible side-effect outside the executor's normal file-edit envelope; CLAUDE.md "Humans always merge" applies broadly to "autonomy ends at PR creation."

---

## Stage 2 — Critic findings

Four critics ran in parallel: Coverage, Test Quality, Consistency, Design Patterns. No `NEEDS RESEARCH` tags surfaced; Stage 3 skipped.

### Coverage critic (10 findings)

- **F1 [block]** — README has no exit-criteria checklist; AC-5 presupposes one. Implementer outcome non-deterministic.
- **F2 [block]** — `docs/contributing.md` already has `## Adding a probe` H2. AC-1 doesn't address extend vs. duplicate vs. replace.
- **F3 [harden]** — Stale ratchet schedule in `contributing.md` not reconciled.
- **F4 [harden]** — Milestone-existence escape clause unverifiable as written.
- **F5 [harden]** — Negative-space gap: nothing prevents 4 or 6 issues passing AC-3.
- **F6 [harden]** — No AC requires the Step 6 PR body to actually contain the five issue URLs / coverage table / sha256 lines.
- **F7 [harden]** — "No `src/` files modified" stated in prose; not encoded as AC.
- **F8 [harden]** — `mkdocs build --strict` doesn't validate intra-doc anchor targets.
- **F9 [harden]** — Cheat sheet doesn't reference the existing "Probe version bumps" H3, risking duplication.
- **F10 [nit]** — Citation format on ticked checkboxes unbounded.

### Test Quality critic (7 findings)

- **F1 [harden]** — No positive count / set-equality assertion for the five Phase 2 issues.
- **F2 [harden]** — No verifier that issue bodies actually link back to originating doc.
- **F3 [block]** — `tests/docs/test_phase1_readme_closed.py` should be MANDATORY, not optional. Rule 2 (simplicity) does not override Rule 9 (tests verify intent); a 5-line pytest is the trivial defense the story walks away from. The "reviewer eyeballs the README" position is the same anti-pattern S6-02's validation hardened against.
- **F4 [harden]** — AC-1 / AC-2 enumerate subsections + probe references but no grep oracle asserts presence.
- **F5 [nit]** — `git diff --name-only` scope guard not encoded.
- **F6 [nit]** — Anchor link rot (mkdocs gap) acceptable residual.
- **F7 [nit]** — Issue-count CI gate not justified; one-shot diff in PR body is the right level.

### Consistency critic (10 findings)

- **F1 [block]** — Same as Coverage F1: README has no checklist; story narrative is empirically false.
- **F2 [block]** — Same as Coverage F2: existing H2 not addressed.
- **F3 [block]** — Same as Coverage F3: ratchet schedule contradicts shipped CI gate.
- **F4 [harden]** — Issue #5 ("Coverage ratchet 92/82") presumes a Phase 2 design decision that hasn't been made.
- **F5 [harden]** — Story Context claims all five issues trace to `phase-arch-design.md §"Open questions"`; only three actually do (#2, #7, #8). The other two trace to ADR-0002 §Consequences and `contributing.md`'s ratchet table.
- **F6 [harden]** — Issue creation is an irreversible side-effect; should be drafts-as-files (Mode A) with optional `gh issue create` (Mode B) per "Humans always merge."
- **F7 [harden]** — AC-5 demands one closing-story citation per goal; several goals close at multiple stories or at infrastructure that landed in Phase 0. Pre-author the mapping.
- **F8 [nit]** — Implementation outline §3 has a dead "if absent, add" branch (mkdocs.yml already includes contributing.md).
- **F9 [nit]** — AC-4 link-back is unverifiable from the file-edit envelope until F6 is applied.
- **F10 [nit]** — `mkdocs build --strict` is permissive on links to non-nav-listed files (Phase 0 known limitation); surface as a manual-eyeball note.

### Design Patterns critic (8 findings)

- **F1 [block]** — README handoff record is the third instance of the "frozen audit ledger" pattern (Phase 0 + Phase 1). Adopt S5-02's AC-8 shape verbatim rather than re-inventing.
- **F2 [harden]** — Phase 2 issue bodies should name their **Extension surface** (which new file lands; which existing file is allowed-to-edit, default "none") so the autonomous executor in Phase 2 doesn't re-derive whether they may edit existing code. CLAUDE.md "Extension by addition" applied to issue templates.
- **F3 [harden]** — Hard-coded "five issues" needs a deviation policy (>5 / <5) per "Fail loud."
- **F4 [harden]** — Class-name references in cheat-sheet prose drift silently — `mkdocs --strict` catches link rot but not unlinked backticked identifier rot.
- **F5 [nit]** — Issue title prefix discipline (`[probe]`, `[schema]`, `[infra]`, `[ratchet]`) for Phase 2+ grep-ability.
- **F6 [harden]** — Cheat sheet needs its own "Extending this cheat sheet" convention (Open/Closed at the documentation boundary).
- **F7 [nit]** — `test_phase_readme_closed.py` parameterization is the rule-of-three target for Phase 2. Do not extract here; surface in Notes.
- **F8 [nit]** — YAML manifest (`probe-patterns.yaml`) for queryable pattern catalog is a future Phase 4+ trigger (Rule 2 — first occurrence; do NOT promote).

---

## Stage 4 — Synthesis + edits

### Conflict resolution

- **Test Quality F3 (mandate the test) vs. Story's Rule-2 framing (defer it).** Resolution: Rule 9 (tests verify intent) overrides Rule 2 (simplicity) when the test is trivial and the alternative is "reviewer eyeballs." Three other critics (Coverage F1, Consistency F1, Design F1) independently flagged the README closure as block-tier. Promote `tests/docs/test_phase1_readme_closed.py` to mandatory; remove the Rule-2 dismissal from Out-of-scope.
- **Coverage F8 (anchor validation) vs. Consistency F10 (mkdocs strict gap is acceptable Phase 0 residual).** Consistency wins per priority — surface as Notes-for-implementer guidance to prefer file-level relative links over deep anchors; do NOT add a new doc-anchor verifier (Rule 2).
- **Consistency F6 (drafts-as-files) vs. Story's gh-create flow.** Consistency wins — adopt Mode A as the executor primary path; Mode B (`gh issue create`) as optional follow-on for an authenticated implementer. The drafts-as-files path is what the validator can audit.
- **Design F1 vs. Story's "tick the boxes" framing.** Design wins — adopt S5-02's AC-8 shape verbatim (`## Exit criteria` + `## Handoff record` H2s) so the rule-of-three pattern (Phase 0 + Phase 1) is genuinely established for Phase 2 to inherit.

### Edits applied to the story

1. **Validation notes block** appended after the story header documenting the verdict, findings, and changes.
2. **Context paragraph** (§Context lines 15–22) rewritten to give explicit per-issue source-of-truth trace (Coverage F5, Consistency F5).
3. **Acceptance criteria entirely rewritten:**
   - **AC-1** — extends the existing `## Adding a probe` H2 with a `### Phase 1+ probes (cheat sheet)` H3 covering (a)–(f); references existing "Probe version bumps" H3 for `version` semantics rather than duplicating; ends with "Extending this cheat sheet" subsection (F2 Coverage + F2 Consistency + F9 Coverage + F6 Design).
   - **AC-2** — pinned grep-oracle assertion: each of the five Phase 1 probe filenames must appear as a relative markdown link; class names cited in prose are backtick-fenced AND linked to file (F4 Coverage + F4 Test-Quality + F4 Design).
   - **AC-3** — mandates Mode A (five draft files under `docs/phases/01-context-gather-layer-a-node/_phase2_issues/{1..5}.md`) with `Extension surface:` paragraph in each; Mode B (optional `gh issue create`) for authenticated implementer; set-equality assertion via `diff` against the canonical title list (F1 Test-Quality + F2 Design + F6 Consistency + F5 Coverage).
   - **AC-4** — issue body link-back as greppable substring assertion against the draft files (F2 Test-Quality + F9 Consistency).
   - **AC-5** — rewritten to mirror S5-02 AC-8 verbatim, adapted: `## Exit criteria` (10 goals from `phase-arch-design.md §"Goals"` with citation format pinned) + `## Handoff record` (PR URL, SHA, workflow-run URL, milestone URL, ≥5 issue URLs); pre-authored goal→story citation table inlined to the Implementation outline (F1 Coverage + F1 Consistency + F1 Design + F7 Consistency + F10 Coverage).
   - **AC-6** — unchanged in intent; reworded to drop the dead "if absent, add" branch (F8 Consistency).
   - **AC-7** — unchanged: `make check` regression gate.
   - **AC-8 (NEW)** — `docs/contributing.md` ratchet schedule reconciled to actually-shipped values (Phase 0=85/75, Phase 1=90/80 with carve-outs, Phase 2=92/82 proposed) (F3 Coverage + F3 Consistency).
   - **AC-9 (NEW)** — `tests/docs/test_phase1_readme_closed.py` lands as a mandatory test asserting (a) no `- [ ]` remains in the README, (b) every `- [x]` in the Exit criteria section ends with a `S\d+-\d{2}` story-citation token (F3 Test-Quality + F3 Design).
   - **AC-10 (NEW)** — Step 6 PR body negative-space AC: `git diff --name-only origin/main..HEAD -- src/` returns zero lines (F7 Coverage + F5 Test-Quality).
   - **AC-11 (NEW)** — Step 6 PR body contains: five Phase 2 draft-file paths (and URLs if Mode B was run), the per-module coverage table from S6-02, the byte-identical sha256 lines from S6-01, and a checkbox list mirroring the README Exit criteria (F6 Coverage).
4. **Implementation outline** rewritten to walk through: extend (not duplicate) the contributing.md H2; reconcile the ratchet table; pre-author the goal→story citation table; draft the five issue files first (Mode A); ship the mandatory test; if `gh` authenticated, file the issues (Mode B) and capture URLs into the README handoff record + PR body; tick the README boxes; final `make check` + `mkdocs build --strict`.
5. **TDD plan** strengthened — `tests/docs/test_phase1_readme_closed.py` promoted from optional to mandatory; greppable-content tests added for the cheat-sheet content (`tests/docs/test_contributing_cheat_sheet.py`); diff-based set-equality verifier added for the issue-title list.
6. **Out-of-scope** — Rule-2 dismissal of `test_phase1_readme_closed.py` REMOVED; explicit deviation-policy bullet ADDED (>5 / <5 issues handling); explicit Phase-2 anchor-validator extraction note ADDED.
7. **Notes-for-implementer** extended with: precedent pointer to Phase 0 S5-02's AC-8 shape; prefix-discipline suggestion for Phase 2 issue titles; future-extraction note for parameterized phase-README closure test (rule-of-three at Phase 2); future-extraction note for `probe-patterns.yaml` queryable manifest (rule-of-three at Phase 4+); deep-anchor link rot acknowledgment.
8. **Files-to-touch** updated to include: five draft issue files; the new `tests/docs/test_phase1_readme_closed.py`; the new `tests/docs/test_contributing_cheat_sheet.py`.

### Findings NOT applied (explicit reasoning)

- **Coverage F8 (deep anchor validator script).** Surfaced in Notes; not made into an AC. Phase 0 already accepts mkdocs's nav-link-only validation as the residual; adding `scripts/check_doc_anchors.py` would be Rule 2 violation absent a recurring failure pattern.
- **Test Quality F7 (CI count gate for Phase 2 issues).** F1 Test-Quality's one-shot diff verifier in the PR body is the right level. A standing CI gate would fight Phase 2's natural workflow (Phase 2 PRs add more issues).
- **Design F8 (`probe-patterns.yaml` queryable manifest).** First occurrence; deferred per Rule 2. Surfaced in Notes for the rule-of-three trigger at Phase 4+.

---

## Verdict: HARDENED

Three critics independently flagged the same block-tier failure (README has no checklist to tick); a fourth critic added a fourth block (mandate the test). All four blockers are fixable without re-design — they are all AC rewrites + adoption of an existing pattern (S5-02 AC-8 shape) + promotion of an already-named optional test. Story is now executor-ready: every AC is binary pass/fail-checkable on disk, the issues are drafted-as-files (auditable file-edit envelope), and the README closure is the genuine third instance of the "frozen audit ledger" rule-of-three. Send to phase-story-executor.
