# Story S6-03 — Contributor docs cheat sheet + Phase 2 follow-up issues + Phase 1 README close

**Step:** Step 6 — Golden file, coverage ratchet, bench additions, Phase 2 handoff
**Status:** Ready
**Effort:** S
**Depends on:** S6-01, S6-02
**ADRs honored:** ADR-0002 (memo seam Phase 2 inherits), ADR-0004 (sub-schema strictness convention), ADR-0005 (coverage ratchet handoff), ADR-0006 (catalog versioning Phase 2 may extend), ADR-0007 (warning-ID pattern Phase 2 promotes to enum)

## Context

Phase 1 has shipped the six Layer A probes, the parsers, the memo, the catalogs, the golden file, and the ratcheted coverage gate. What remains is the *handoff layer*: documentation that a new contributor can read to add a Phase 2+ probe, the GitHub Project board issues Phase 2 picks up on day one, and the Phase 1 README exit-criteria checklist marked complete so the phase is genuinely closed.

This is the only Phase 1 story that touches `docs/`. The architecture rule "organizational uniqueness as data, not prompts" (`CLAUDE.md` "Load-bearing architectural commitments") means the contributor cheat sheet doesn't restate the architecture — it points at the architecture. The Phase 1 probes are the canonical examples Phase 2 contributors imitate; the cheat sheet is the *index* into them, not the duplicate.

Five Phase 2 follow-up issues are filed, mapped to the open questions deferred from this phase (`phase-arch-design.md §"Open questions deferred to implementation"`):

1. **Implement `IndexHealthProbe (B2)`** — the load-bearing Phase 2 probe, the silent-staleness aggregator.
2. **Promote `WarningId` to a typed enum** (open question #7).
3. **Decide per-probe sub-schema release-versioning policy** (open question #2).
4. **Extend the memo allowlist** beyond `{"package.json"}` for Layer B/C/D index manifests.
5. **Coverage ratchet to 92/82** in Phase 2.

Each issue is filed against the GitHub Project board with the `phase-2` milestone aligned to `roadmap.md §"Phase 2"`. They are not Phase 1 work — they are the explicit, documented surface Phase 2 starts from.

The Phase 1 README's exit-criteria checklist is the visible signal that Phase 1 is done. Marking it complete is the closing step; reviewers see "Phase 1 closed" without having to re-derive the closure from CI status.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Integration with Phase 2 (next phase)"` — new contracts Phase 2 consumes (memo, parsers, sub-schemas, warning-ID pattern, coverage carve-out convention); new artifacts on disk Phase 2 reads; state that persists; implicit guarantees.
  - `../phase-arch-design.md §"Open questions deferred to implementation"` items 2, 4, 7, 8 — the surface filed as Phase 2 issues.
  - `../phase-arch-design.md §"Path to production end state"` — what's still missing (IndexHealthProbe; Layers B–G; recipe + LLM-fallback; continuous gather) — informs the issue narratives.
- **Phase ADRs (rules this story must honor and reference in handoff docs):**
  - `../ADRs/0002-parsed-manifest-memo-on-probe-context.md` — the memo seam Phase 2 reuses; the cheat sheet's "reading manifests" section points here.
  - `../ADRs/0004-per-probe-subschema-additional-properties-false.md` — every Phase 2 probe sub-schema follows this convention; cheat sheet references.
  - `../ADRs/0005-coverage-carve-outs-deployment-ci.md` — further carve-outs require their own ADR; the cheat sheet documents this clearly so Phase 2 contributors don't quietly add a third.
  - `../ADRs/0006-native-module-catalog-versioning.md` — catalog version drives cache invalidation; Phase 7's input.
  - `../ADRs/0007-warnings-id-pattern.md` — warning IDs match the pattern; Phase 2 issue #2 promotes to enum.
- **High-level impl plan:**
  - `../High-level-impl.md §"Step 6"` features — `docs/contributing.md` updated with the "adding a probe" cheat sheet section; `docs/phases/01-context-gather-layer-a-node/README.md` updated with final exit-criteria checklist marked complete; Phase 2 issues filed on the GitHub Project board.
  - `../High-level-impl.md §"What's next — handoff to Phase 2"` — the prose Phase 2's author reads on day one; informs the cheat sheet's framing.
- **Manifest:**
  - `../stories/README.md` — S6-03 row; the Step 6 entry's `applies_to` listing the five Phase 2 follow-up issues.
- **Roadmap and existing docs (consumed/extended by this story):**
  - `../../../roadmap.md §"Phase 2"` — milestone alignment for the issues.
  - `docs/contributing.md` (if it exists from Phase 0; otherwise create) — the "adding a probe" cheat sheet lands here.
  - `docs/phases/01-context-gather-layer-a-node/README.md` — exit-criteria checklist mark-complete.
  - `mkdocs.yml` — confirm `contributing.md` is in the curated `nav` and the build passes `mkdocs build --strict`.

## Goal

Update `docs/contributing.md` with an "adding a probe" cheat sheet section pointing at Phase 1 probes as canonical examples, file the five Phase 2 follow-up issues on the GitHub Project board aligned to `roadmap.md §"Phase 2"`, and mark the Phase 1 README's exit-criteria checklist complete so the phase is closed.

## Acceptance criteria

- [ ] `docs/contributing.md` has an "Adding a probe" section (one H2) covering: (a) where to register (additive import in `src/codegenie/probes/__init__.py`); (b) the probe ABC contract (`name`, `layer`, `tier`, `applies_to_languages`, `applies_to_tasks`, `requires`, `timeout_seconds`, `declared_inputs`, `declared_raw_artifact_budget_mb`, `version`); (c) the sub-schema convention (`additionalProperties: false` at root; envelope `$ref` composition); (d) the memo seam (`ctx.parsed_manifest` if reading an allowlisted manifest); (e) the warning-ID pattern (`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`); (f) the coverage discipline (per-module floor declared, intent-verifying tests).
- [ ] The cheat sheet references **specific Phase 1 probes as canonical examples** for each pattern — at minimum `node_build_system.py` (allowlisted binary), `node_manifest.py` (catalog cross-reference + raw-artifact budget override), `deployment.py` (zip-slip path containment + multi-env list), `ci.py` (multi-provider + secrets-as-strings), `test_inventory.py` (lcov scanner) — by relative link path.
- [ ] Five Phase 2 follow-up issues are filed on the GitHub Project board, each labeled `phase-2` and milestoned to `roadmap.md §"Phase 2"`:
  - "Implement `IndexHealthProbe (B2)` — Phase 2 load-bearing probe"
  - "Promote `WarningId` to typed enum (open question #7)"
  - "Decide per-probe sub-schema release-versioning policy (open question #2)"
  - "Extend `ParsedManifestMemo` allowlist beyond `package.json`"
  - "Coverage ratchet 92/82 in Phase 2"
- [ ] Each Phase 2 issue body links back to the originating doc section (`phase-arch-design.md §"Open questions..."` or `phase-arch-design.md §"Integration with Phase 2"`) so the Phase 2 author has the originating context one click away.
- [ ] `docs/phases/01-context-gather-layer-a-node/README.md` has its exit-criteria checklist (the one from `phase-arch-design.md §"Goals"`) marked complete — every checkbox ticked with a citation to the closing story (S5-05, S6-01, S6-02, or this story).
- [ ] `mkdocs build --strict` passes; `docs/contributing.md` remains in the curated `nav`.
- [ ] No regressions: `ruff check`, `ruff format --check`, `mypy --strict`, and the full `pytest` suite still pass on `main` after the docs land.

## Implementation outline

1. **Audit `docs/contributing.md`.** Verify it exists (Phase 0 likely seeded it). If not, create with the standard contributor preamble (development setup, `make check`, PR conventions) — keep brief, reference Phase 0's existing docs surgically (Rule 3).
2. **Write the "Adding a probe" section.** Six subsections (a–f from acceptance criteria), each ≤ 15 lines. Use markdown links to point at specific Phase 1 probe files; do not duplicate the ABC contract definition — point at `localv2.md §4` and `phase-arch-design.md §"Component design"`.
3. **Confirm `mkdocs.yml`** lists `contributing.md` under `nav`. If absent, add. Run `mkdocs build --strict` locally; fix any link warnings.
4. **File the five Phase 2 issues.** Use `gh issue create` for each:
   - Title verbatim from acceptance criteria.
   - Body: 4–8 sentences. First sentence is the problem statement (the deferred open question). Second sentence cites the originating doc by relative path + section. Third names the load-bearing surface this issue unblocks. Remaining sentences are scope hints (not a design — leave that to the Phase 2 author).
   - Labels: `phase-2`, `enhancement` (or `tech-debt` for the ratchet/enum promotion).
   - Milestone: the Phase 2 milestone if it exists; otherwise file a request to create it and note in the PR body.
5. **Capture the issue URLs.** Paste them into the Step 6 PR body so reviewers can confirm they exist without leaving the PR.
6. **Mark the Phase 1 README exit-criteria checklist complete.** Each checkbox gets a closing citation to the story that completed it (e.g., `- [x] Cache hits on second run (all six Layer A probes) — S5-05`). The list should look like a closed ledger, not an open question.
7. **Final pass.** `make check` (lint + typecheck + test). `mkdocs build --strict`. Confirm nothing in `src/` was touched (this is a docs-and-issues story; touching `src/` would be a scope violation).

## TDD plan — red / green / refactor

### Red — write the failing test first

This is a documentation + issues-board story. There is no per-test red phase in the executable-code sense. The "red" equivalents are:

1. `mkdocs build --strict` fails initially if `contributing.md`'s new section has broken relative links (point at a Phase 1 probe path that doesn't exist).
2. `gh issue list --milestone "Phase 2" --label phase-2` returns fewer than five issues before this story runs.
3. The Phase 1 README's exit-criteria checklist has unchecked boxes for golden, coverage ratchet, and Phase 2 handoff.

Each is a verifiable "red" the reviewer can confirm. There is no `tests/` file for this story.

If the implementer wants a CI-enforceable assertion for the README exit-criteria checklist, an optional `tests/docs/test_phase1_readme_closed.py` parses the README, asserts every `- [ ]` is `- [x]`, and fails if any box is unchecked. This is **optional** (Rule 2 — simplicity first) — the README is human-eyeballed at PR review.

### Green — make it pass

1. Write the "Adding a probe" section. Run `mkdocs build --strict`. Fix any link warnings (likely the first cycle catches a typo in a probe path).
2. File the five issues via `gh issue create`. Capture URLs. Paste into PR body.
3. Tick the README exit-criteria boxes; cite the closing story for each.
4. `make check` to confirm no regression.

### Refactor — clean up

- The "Adding a probe" section may grow over time as Phase 2/3 probes add patterns. Phase 1 ships the minimum viable cheat sheet; do not preemptively expand for hypothetical future patterns (Rule 2).
- If Phase 0's `docs/contributing.md` was sparse, this story is a fine moment to add the "PR conventions" subsection if it's missing — but only if missing. Surgical changes (Rule 3).
- Confirm the contributing.md examples format consistently: backtick-fenced code blocks for probe filenames; relative markdown links for cross-references; no absolute URLs to GitHub (they break on fork).

## Files to touch

| Path | Why |
|---|---|
| `docs/contributing.md` | Modify — add "Adding a probe" section with Phase 1 probes as canonical examples. |
| `docs/phases/01-context-gather-layer-a-node/README.md` | Modify — tick exit-criteria checklist; cite closing stories. |
| `mkdocs.yml` | Modify (only if missing) — confirm `contributing.md` is in `nav`; verify `mkdocs build --strict` passes. |
| GitHub Project board / Issues | Create — five Phase 2 follow-up issues; not a file in the repo, but a deliverable of this story. |

## Out of scope

- **Designing `IndexHealthProbe`.** That's Phase 2 work. The issue body names the load-bearing surface (silent staleness; `confidence` + `warnings` aggregation) and stops. Do not start drafting the probe here.
- **Promoting `WarningId` to an enum.** Filed as a Phase 2 follow-up; not implemented here. The pattern constraint is the Phase 1 minimum defense (ADR-0007).
- **Extending the memo allowlist.** The allowlist stays at `{"package.json"}` for Phase 1. Phase 2 extends additively per ADR-0002's documented growth path.
- **Coverage ratchet to 92/82.** Phase 2 work. Phase 1 lands 90/80 (S6-02); the further bump is filed as an issue.
- **Phase 2's golden portfolio.** S6-01 ships one golden; the Phase 2 expansion is Phase 2's responsibility. Do not preemptively seed Phase 2 fixtures.
- **A typed-warning-IDs enum migration tool.** Phase 2 work. If the enum promotion lands, a migration of existing string warnings is necessary — that's part of the Phase 2 issue, not Phase 1.
- **A `tests/docs/test_phase1_readme_closed.py` CI gate** asserting all checkboxes are ticked. Optional per the TDD plan; reviewers eyeball the README at PR review. Adding the test is a Rule 2 violation unless the team's experience suggests checkboxes get missed at scale (not yet evidence-based).

## Notes for the implementer

- **The cheat sheet's job is to be an *index*, not a *textbook*.** A new contributor should be able to skim it in 5 minutes and know where to look for each pattern. If a section exceeds 15 lines, you're explaining instead of pointing.
- **Cite Phase 1 probes by relative path** (e.g., `src/codegenie/probes/node_manifest.py`). Use markdown link form so `mkdocs` validates the path at build time.
- **The five Phase 2 issues are *not* designed here.** Each body is 4–8 sentences naming the problem and citing the originating doc section. The Phase 2 author does the design when they pick up the issue.
- **Milestone alignment.** If the GitHub Project board does not yet have a Phase 2 milestone, file a request in the same PR (or via `gh` if you have permissions). Do not invent ad-hoc labels.
- **The Phase 1 README's exit-criteria checklist** likely already exists from the Phase 1 design stage. This story marks it complete; it does not re-author it. Surgical (Rule 3).
- **`mkdocs build --strict`** is in CI already (Phase 0 S1-04). Running it locally catches link rot before CI does; do it.
- **If a Phase 2 issue overlaps an existing GitHub issue**, link rather than duplicate. The five named issues are specific enough to be new; if one exists already (e.g., someone filed "IndexHealthProbe" months ago during design), tag and reference rather than re-file.
- **The Step 6 PR body is the closing artifact for Phase 1.** It should contain: (a) the per-module coverage table from S6-02; (b) the byte-identical `sha256` lines from S6-01's regen verification; (c) the five Phase 2 issue URLs from this story; (d) a checkbox list mirroring the Phase 1 README's exit criteria, all ticked. Reviewers should be able to close Phase 1 without leaving the PR.
- **Do not touch `src/`.** This is a docs + issues story. If you find yourself editing a probe to "fix" a documentation example, stop — the probe is the canonical example, and the doc points at *it*, not the other way around.
- **Phase 7 inherits `native_modules.yaml`.** The cheat sheet's "catalog extensions" subsection (under "Adding a probe" → catalog cross-reference, if you choose to include it) can mention this in one line; do not write a Phase 7 design preview.
