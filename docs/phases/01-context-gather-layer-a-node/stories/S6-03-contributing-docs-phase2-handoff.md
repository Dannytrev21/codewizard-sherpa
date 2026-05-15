# Story S6-03 — Contributor docs cheat sheet + Phase 2 follow-up issues + Phase 1 README close

**Step:** Step 6 — Golden file, coverage ratchet, bench additions, Phase 2 handoff
**Status:** Ready
**Effort:** S → M (validator-bumped — README handoff record + ratchet reconciliation + mandatory tests)
**Depends on:** S6-01, S6-02
**ADRs honored:** ADR-0002 (memo seam Phase 2 inherits), ADR-0004 (sub-schema strictness convention), ADR-0005 (coverage ratchet handoff), ADR-0006 (catalog versioning Phase 2 may extend), ADR-0007 (warning-ID pattern Phase 2 promotes to enum)

## Validation notes

Validated: 2026-05-15
Verdict: HARDENED
Findings addressed: 35 total — 4 blocks, 16 hardens, 15 nits

Changes applied:
- AC-1 rewritten — `docs/contributing.md` already has `## Adding a probe` H2 from Phase 0 (line 69, `LanguageDetectionProbe` worked example). The story now extends in place via a new H3 (`### Phase 1+ probes (cheat sheet)`); does NOT duplicate the H2; references the existing `## Probe version bumps` H3 for `version` semantics rather than re-explaining; ends with a one-paragraph "Extending this cheat sheet" Open/Closed convention. Coverage F2 + Consistency F2 + Coverage F9 + Design Patterns F6.
- AC-2 strengthened — pinned grep oracle: every probe filename + class name appears as a relative markdown link (not bare backticked text); class-name-only references are forbidden so file rename trips `mkdocs build --strict`. Coverage F4 + Test-Quality F4 + Design Patterns F4.
- AC-3 rewritten — Mode A primary: five Phase 2 issue bodies are drafted as files under `docs/phases/01-context-gather-layer-a-node/_phase2_issues/{1..5}.md` so the autonomous executor stays inside the file-edit envelope (CLAUDE.md "Humans always merge" applied broadly). Mode B optional: if `gh` is authenticated, also `gh issue create` and capture URLs into the README handoff record. Each draft contains a `Extension surface:` paragraph naming new files / allowed edits per CLAUDE.md "Extension by addition." Set equality enforced by `diff` against the canonical title list. Consistency F6 + Design Patterns F2 + Coverage F5 + Test-Quality F1.
- AC-4 strengthened — issue body link-back enforced by greppable substring oracle against the draft files (verifiable from the file-edit envelope). Test-Quality F2 + Consistency F9.
- AC-5 rewritten — adopts Phase 0 S5-02's AC-8 shape verbatim: `## Exit criteria` H2 (10 goals from `phase-arch-design.md §"Goals"` rendered as `[x]` checkboxes with citation token `S\d+-\d{2}`) + `## Handoff record` H2 (PR URL, 40-char SHA, workflow-run URL naming both 3.11 and 3.12, milestone URL, ≥5 issue URLs). The Phase 1 README has NO existing checklist — this story authors it. Pre-authored goal→story citation table inlined to Implementation outline §6 so the executor ticks rather than re-derives. Coverage F1 + Consistency F1 + Design Patterns F1 + Consistency F7 + Coverage F10.
- AC-6 reworded — drops the dead "if absent, add" branch (`mkdocs.yml:47` already nav-includes contributing.md). Consistency F8.
- AC-7 unchanged — `make check` regression gate.
- AC-8 added — `docs/contributing.md` ratchet schedule table (lines 131–135) reconciled to actually-shipped values: Phase 0 = 85/75, Phase 1 = 90/80 with 85/75 carve-outs (ADR-0005), Phase 2 = 92/82 (proposed; tracked as Phase 2 issue #5). Closes the doc/CI contradiction. Coverage F3 + Consistency F3.
- AC-9 added — `tests/docs/test_phase1_readme_closed.py` MANDATORY (not optional). Promoted from "Out of scope per Rule 2" to a 5-line pytest defending the only AC for which mutation-resistance is trivially achievable. Asserts: (a) zero `- [ ]` markers in the README; (b) every `- [x]` in `## Exit criteria` ends with a `S\d+-\d{2}` citation token. Test-Quality F3 + Design Patterns F1.
- AC-10 added — negative-space scope guard: `git diff --name-only origin/main..HEAD -- src/` returns zero lines. The story's repeated "Do not touch `src/`" warning made runnable. Coverage F7 + Test-Quality F5.
- AC-11 added — Step 6 PR body contractual content: five Phase 2 draft-file paths (and URLs if Mode B was run); the per-module coverage table from S6-02; byte-identical `sha256` lines from S6-01; checkbox list mirroring the README `## Exit criteria`. Notes-for-implementer's narrative requirement is now an AC. Coverage F6.
- TDD plan rewritten — `tests/docs/test_phase1_readme_closed.py` and `tests/docs/test_contributing_cheat_sheet.py` are mandatory red→green tests; per-issue draft-file shape is greppable; set-equality via `diff /tmp/expected.txt /tmp/actual.txt` is the issue-count verifier; `git diff` scope guard is one-shell-line.
- Out-of-scope updated — REMOVED the Rule-2 dismissal of `test_phase1_readme_closed.py` (it's now mandatory per AC-9). ADDED explicit deviation policy for >5 / <5 Phase 2 issues per CLAUDE.md "Fail loud" (Design Patterns F3). ADDED note that the parameterized `tests/docs/test_phase_readme_closed.py` (across all phases) is Phase 2's rule-of-three trigger, not Phase 1's (Design Patterns F7).
- Notes-for-implementer extended with: precedent pointer to Phase 0 S5-02 AC-8 shape; prefix-discipline suggestion for Phase 2 issue titles (`[probe]`/`[schema]`/`[infra]`/`[ratchet]`) per Design Patterns F5; future-extraction note for `probe-patterns.yaml` queryable manifest as a Phase 4+ rule-of-three trigger (Design Patterns F8); deep-anchor link-rot acknowledgment per Coverage F8 + Consistency F10.
- Files-to-touch extended — five draft issue files under `_phase2_issues/`; the two new `tests/docs/` test files; the new READme `## Exit criteria` + `## Handoff record` sections; the contributing.md ratchet table reconciliation.

Full audit log: [`_validation/S6-03-contributing-docs-phase2-handoff.md`](_validation/S6-03-contributing-docs-phase2-handoff.md)

## Context

Phase 1 has shipped the six Layer A probes, the parsers, the memo, the catalogs, the golden file, and the ratcheted coverage gate. What remains is the *handoff layer*: documentation that a new contributor can read to add a Phase 2+ probe, the GitHub Project board issues Phase 2 picks up on day one, and the Phase 1 README exit-criteria checklist marked complete so the phase is genuinely closed.

This is the only Phase 1 story that touches `docs/`. The architecture rule "organizational uniqueness as data, not prompts" (`CLAUDE.md` "Load-bearing architectural commitments") means the contributor cheat sheet doesn't restate the architecture — it points at the architecture. The Phase 1 probes are the canonical examples Phase 2 contributors imitate; the cheat sheet is the *index* into them, not the duplicate.

Five Phase 2 follow-up issues are drafted (Mode A: as files in this PR) and optionally filed (Mode B: via `gh issue create` if the implementer is authenticated). Each traces to a specific source-of-truth doc section — note these are NOT all "open questions"; two trace to ADR consequences and the contributing.md ratchet table:

1. **Implement `IndexHealthProbe (B2)`** — the load-bearing Phase 2 probe, the silent-staleness aggregator. Origin: `phase-arch-design.md §"Non-goals"` #1 ("Phase 2 owns it") + `phase-arch-design.md §"Path to production end state"` first bullet ("the silent-staleness aggregator"); roadmap §"Phase 2".
2. **Promote `WarningId` to a typed enum** — Origin: `phase-arch-design.md §"Open questions deferred to implementation"` #7 + ADR-0007 §"Reversibility" (forward direction = enum promotion).
3. **Decide per-probe sub-schema release-versioning policy** — Origin: `phase-arch-design.md §"Open questions"` #2.
4. **Extend the memo allowlist** beyond `{"package.json"}` for Layer B/C/D index manifests — Origin: ADR-0002 §"Consequences" "allowlist extends additively" + `phase-arch-design.md §"Integration with Phase 2"` line discussing memo-allowlist additive growth.
5. **Coverage ratchet to 92/82** in Phase 2 (proposal — title reframed as "Decide Phase 2 coverage target — proposed 92/82") — Origin: `docs/contributing.md` ratchet schedule (after this story reconciles it per AC-8). NOT prescriptive on Phase 2; flagged as a proposal subject to Phase 2's final-design.

Issues are drafted as files first (Mode A — auditable in this PR) and optionally filed via `gh issue create` (Mode B) with `phase-2` label and the `Phase 2` milestone aligned to `roadmap.md §"Phase 2"`. They are not Phase 1 work — they are the explicit, documented surface Phase 2 starts from. Each draft includes an `Extension surface:` paragraph naming the new file(s) added and existing file(s) edited (default: none, per CLAUDE.md "Extension by addition") so the autonomous executor in Phase 2 doesn't re-derive the seam.

The Phase 1 README has **no existing exit-criteria checklist** — `grep -c '\[ \]' docs/phases/01-context-gather-layer-a-node/README.md` returns 0. This story therefore *authors* the checklist (mirroring the Phase 0 S5-02 AC-8 shape: `## Exit criteria` + `## Handoff record` H2s) and ticks it. Marking it complete is the closing step; reviewers see "Phase 1 closed" without having to re-derive the closure from CI status. The `## Handoff record` is the rule-of-three frozen-audit-ledger pattern (Phase 0 → Phase 1 → Phase 2's S6-X handoff at three).

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
  - `docs/contributing.md` — already has `## Adding a probe` H2 (line 69, Phase 0 / S4-01) referencing `LanguageDetectionProbe`; already has `## Probe version bumps` H3 (line 105–122); already has the (now-stale) ratchet table (lines 131–135). This story EXTENDS in place; does not duplicate the H2.
  - `docs/phases/01-context-gather-layer-a-node/README.md` — currently has no exit-criteria checklist (verified: zero `- [ ]` markers). This story AUTHORS the checklist + handoff record per Phase 0 S5-02 AC-8 precedent.
  - `mkdocs.yml:47` — already nav-includes `contributing.md`; AC-6 verifies it stays.
- **Precedent to mirror (load-bearing):**
  - `../../00-bullet-tracer-foundations/README.md §"Exit criteria" + §"Handoff record"` — the worked example for the README structure this story authors.
  - `../../00-bullet-tracer-foundations/stories/S5-02-project-artifacts-handoff.md` AC-8 — the canonical AC shape this story's AC-5 mirrors.
  - `../../00-bullet-tracer-foundations/stories/_validation/S5-02-project-artifacts-handoff.md` — adjacent validation precedent for the same closure shape.
  - `../../01-context-gather-layer-a-node/stories/_validation/S6-02-coverage-ratchet-bench.md` — adjacent Phase 1 validation precedent (also Step 6).

## Goal

Update `docs/contributing.md` with an "adding a probe" cheat sheet section pointing at Phase 1 probes as canonical examples, file the five Phase 2 follow-up issues on the GitHub Project board aligned to `roadmap.md §"Phase 2"`, and mark the Phase 1 README's exit-criteria checklist complete so the phase is closed.

## Acceptance criteria

- [ ] **AC-1 — Cheat sheet extends the existing `## Adding a probe` H2 in place.** `docs/contributing.md` already has `## Adding a probe` (line 69, Phase 0 / S4-01 worked example for `LanguageDetectionProbe`). This story does NOT add a second H2 with the same name and does NOT replace the existing 7-step `LanguageDetectionProbe` recipe. Instead it appends a new `### Phase 1+ probes (cheat sheet)` H3 inside the existing H2 covering: (a) where to register (additive import in `src/codegenie/probes/__init__.py`); (b) the probe ABC contract (`name`, `layer`, `tier`, `applies_to_languages`, `applies_to_tasks`, `requires`, `timeout_seconds`, `declared_inputs`, `declared_raw_artifact_budget_mb`, `version` — for `version` semantics, **link to the existing `## Probe version bumps` H3 by relative anchor; do NOT re-explain**); (c) the sub-schema convention (`additionalProperties: false` at root; envelope `$ref` composition); (d) the memo seam (`ctx.parsed_manifest` if reading an allowlisted manifest); (e) the warning-ID pattern (`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`); (f) the coverage discipline (per-module floor declared, intent-verifying tests). The H3 ends with a one-paragraph **"Extending this cheat sheet"** subsection saying: new probe-design patterns add a new H4 inside this H3 (no per-phase forks; no separate file); the new H4 cites the canonical example probe by relative link path; pattern contradictions require an ADR amendment, not silent edits. After the edit, `grep -c '^## Adding a probe$' docs/contributing.md` returns exactly 1 (set equality, no duplicate H2).

- [ ] **AC-2 — Cheat sheet references named Phase 1 probes by relative markdown link AND uses link-form for class-name references.** Every one of the five Phase 1 probes appears as a relative markdown link in the cheat sheet H3, by file path:
  - `[NodeBuildSystemProbe](../src/codegenie/probes/node_build_system.py)` — allowlisted-binary pattern (a)
  - `[NodeManifestProbe](../src/codegenie/probes/node_manifest.py)` — catalog cross-reference + raw-artifact budget override
  - `[DeploymentProbe](../src/codegenie/probes/deployment.py)` — zip-slip path containment + multi-env list
  - `[CIProbe](../src/codegenie/probes/ci.py)` — multi-provider + secrets-as-strings
  - `[TestInventoryProbe](../src/codegenie/probes/test_inventory.py)` — lcov scanner
  Class-name references in cheat-sheet prose are EITHER backtick-fenced AND wrapped in a markdown link to the defining file, OR omitted in favor of the link form above. Free-text backticked class names (e.g., a bare `` `NodeBuildSystemProbe` `` in prose) are not allowed, so file rename trips `mkdocs build --strict`. Verified by `tests/docs/test_contributing_cheat_sheet.py` greps for each of the five `src/codegenie/probes/...py` substrings inside the file.

- [ ] **AC-3 — Five Phase 2 follow-up issues drafted as files (Mode A); optionally filed via `gh` (Mode B).** **Mode A (mandatory, file-edit envelope):** five files land at `docs/phases/01-context-gather-layer-a-node/_phase2_issues/{1..5}-{slug}.md`, one per issue. Each file is structured as: (i) H1 with the canonical issue title (verbatim from the list below); (ii) 4–8 sentence body — first sentence problem statement, second sentence cites the originating doc by relative path + section, third sentence names the load-bearing surface this issue unblocks; (iii) a literal line `Extension surface: <new file(s) to land — default no edits to existing files; if any existing edit is required, name the ADR that authorizes it>`; (iv) `Labels: phase-2, <type>` where `<type>` is `probe`, `schema`, `infra`, or `ratchet`; (v) `Milestone: Phase 2`. The five canonical titles (used for both Mode A filenames and Mode B titles):
  1. ``Implement `IndexHealthProbe (B2)` — Phase 2 load-bearing probe``
  2. ``Promote `WarningId` to typed enum (open question #7)``
  3. ``Decide per-probe sub-schema release-versioning policy (open question #2)``
  4. ``Extend `ParsedManifestMemo` allowlist beyond `package.json` ``
  5. ``Decide Phase 2 coverage target — proposed 92/82``
  **Mode B (optional, requires authenticated `gh` with `repo` scope and milestone-edit permissions):** if the implementer has credentials, also `gh issue create` each draft (titles verbatim, bodies pasted from the draft files, labels and milestone applied) and capture the five resulting URLs into the README `## Handoff record` (AC-5) and the Step 6 PR body (AC-11). If `gh` is not authenticated, the PR body cites the five draft files + names a maintainer to file them at merge time. Set equality enforced by:
  ```sh
  ls docs/phases/01-context-gather-layer-a-node/_phase2_issues/[1-9]-*.md | wc -l   # must == 5
  ```
  If Mode B was run, additionally:
  ```sh
  gh issue list --milestone "Phase 2" --label phase-2 --json title --jq '.[].title' | sort > /tmp/actual.txt
  # /tmp/expected.txt = the five canonical titles, sorted
  diff /tmp/expected.txt /tmp/actual.txt   # must be empty
  ```

- [ ] **AC-4 — Each Phase 2 issue draft body links back to its originating doc section (greppable substring oracle).** For each of the five `_phase2_issues/*.md` files, the body contains a substring matching the regex `docs/phases/01-context-gather-layer-a-node/(phase-arch-design|High-level-impl|ADRs/[0-9]{4}-[a-z0-9-]+)\.md` OR a backticked relative-path reference of equivalent shape. Verified by `tests/docs/test_contributing_cheat_sheet.py::test_phase2_issue_drafts_cite_origin`. The five expected origins:
  1. `IndexHealthProbe` → `phase-arch-design.md §"Non-goals"` #1 + `phase-arch-design.md §"Path to production end state"`
  2. `WarningId enum` → `phase-arch-design.md §"Open questions"` #7 + `ADRs/0007-warnings-id-pattern.md` §Reversibility
  3. Sub-schema versioning policy → `phase-arch-design.md §"Open questions"` #2
  4. Memo allowlist extension → `ADRs/0002-parsed-manifest-memo-on-probe-context.md` §Consequences + `phase-arch-design.md §"Integration with Phase 2"`
  5. Phase 2 coverage target → `docs/contributing.md` ratchet schedule (post-AC-8 reconciliation)

- [ ] **AC-5 — Phase 1 README pins the auditable handoff record (mirrors Phase 0 S5-02 AC-8 verbatim).** `docs/phases/01-context-gather-layer-a-node/README.md` (file already exists from `roadmap-phase-designer`; **extend it** — do NOT replace the existing `## Reading order`, `## Status update (2026-05-13)`, or `## Provenance` sections) gains two new H2 sections appended at the end:
  - `## Exit criteria` — the ten goals from `phase-arch-design.md §"Goals"` (#1–#10) rendered as a Markdown checkbox list, each line `- [x] **G{n} — <short title>.**` followed by either a repo-relative path to a verifying test, the closing story ID, OR a GitHub Actions workflow-run URL. Citation token `S\d+-\d{2}` MUST appear on every ticked line OR the line ends with a workflow-run URL (regex `actions/runs/\d+`). Pre-authored mapping of the ten goals to closing stories is provided in Implementation outline §6.
  - `## Handoff record` — pins, in this order: (i) merged PR URL for the Step 6 closing PR (regex `https://github\.com/.+/pull/\d+`); (ii) `main` HEAD SHA at handoff (40-char hex `[0-9a-f]{40}`); (iii) at least one GitHub Actions workflow-run URL on that SHA showing all six jobs green on Python 3.11 AND 3.12 (regex `https://github\.com/.+/actions/runs/\d+`; the description names both `python-3.11` and `python-3.12` matrix entries); (iv) the Phase 2 milestone URL if it exists (regex `https://github\.com/.+/milestone/\d+`); (v) at least five Phase 2 issue URLs from AC-3 Mode B (regex `https://github\.com/.+/issues/\d+`) — if Mode B was not run, the five draft-file paths from Mode A are listed instead with a note "to be filed by maintainer at merge."

  Verification: `tests/docs/test_phase1_readme_closed.py` (AC-9) parses the README, finds both sections, and runs the regexes.

- [ ] **AC-6 — `mkdocs build --strict` passes; `docs/contributing.md` remains in the curated `nav`.** `mkdocs.yml:47` already nav-includes `contributing.md` (no add required); the AC verifies the entry is preserved and the build is clean.

- [ ] **AC-7 — No regressions.** `ruff check`, `ruff format --check`, `mypy --strict`, and the full `pytest` suite still pass on `main` after the docs land.

- [ ] **AC-8 — `docs/contributing.md` ratchet schedule reconciled with shipped CI.** The "Coverage ratchet" table in `docs/contributing.md` (currently lines 131–135) is updated to reflect actually-shipped values:
  | Phase    | Line | Branch | Notes |
  |----------|-----:|-------:|-------|
  | Phase 0  |  85  |   75   | `--cov-fail-under=85` global. |
  | Phase 1  |  90  |   80   | Bumped by S6-02. Per-module carve-outs at 85/75 for `probes/deployment.py` + `probes/ci.py` per [ADR-0005](../docs/phases/01-context-gather-layer-a-node/ADRs/0005-coverage-carve-outs-deployment-ci.md). |
  | Phase 2  |  92  |   82   | **Proposed.** Tracked as Phase 2 follow-up issue (see `_phase2_issues/5-*.md`); subject to Phase 2 final-design. |

  The pre-existing prose around the table is updated to drop the "do not raise the gate ahead of the schedule" sentence's outdated example. Verified by `tests/docs/test_contributing_cheat_sheet.py::test_ratchet_table_matches_shipped_values` which greps for the three `90/80`, `85/75`, `92/82` substrings in their expected rows.

- [ ] **AC-9 — `tests/docs/test_phase1_readme_closed.py` lands as a mandatory test.** Two assertions:
  1. `test_phase1_exit_criteria_all_ticked` — parses the Phase 1 README; finds zero `- [ ]` lines anywhere in the file.
  2. `test_phase1_exit_criteria_each_box_has_story_citation` — for every `- [x]` line inside the `## Exit criteria` H2 region, asserts the line contains a citation token matching `S\d+-\d{2}` OR ends with a workflow-run URL substring (`actions/runs/`).
  Test failures cite the offending line(s). The test runs in the standard `pytest` job and contributes to the coverage gate's denominator (5 lines in `tests/docs/`, not in `src/codegenie/`).

- [ ] **AC-10 — Negative-space scope guard: no `src/` files modified.** `git diff --name-only origin/main..HEAD -- src/` returns zero lines in the Step 6 PR. The story's repeated "Do not touch `src/`" warning is now machine-checkable. If a `src/` edit is genuinely required (e.g., a probe docstring referenced by the cheat sheet is wrong), it ships in a separate PR with its own ADR-or-justification.

- [ ] **AC-11 — Step 6 PR body contains the closing artifact contents.** The Step 6 PR description includes, in this order:
  1. The five Phase 2 follow-up draft-file paths (`_phase2_issues/{1..5}-*.md`) AND, if Mode B was run, the five matching `gh` issue URLs.
  2. The per-module coverage table from S6-02 (line/branch percentages for every Phase 1 probe + the global gate result).
  3. The byte-identical `sha256` lines from S6-01's regen-script verification (two consecutive `scripts/regen_golden.py` runs producing identical YAML).
  4. A checkbox list mirroring the Phase 1 README's `## Exit criteria` section, all ticked. Reviewers should be able to close Phase 1 without leaving the PR.

## Implementation outline

1. **Audit `docs/contributing.md` for the existing `## Adding a probe` H2 (line 69).** It already exists from Phase 0 / S4-01 with a 7-step `LanguageDetectionProbe` recipe + a `## Probe version bumps` H3 (line 105–122) + the (stale) ratchet table (lines 131–135). Do NOT replace any of these; **append** a new `### Phase 1+ probes (cheat sheet)` H3 inside the existing `## Adding a probe` H2, plus reconcile the ratchet table per AC-8 in the same edit. After the edit, `grep -c '^## Adding a probe$'` returns 1.

2. **Write the `### Phase 1+ probes (cheat sheet)` H3.** Six subsections (a–f from AC-1), each ≤ 15 lines. Use markdown links of the form `[ClassName](../src/codegenie/probes/foo.py)` for every Phase 1 probe + class-name reference (per AC-2 — no bare backticked class names). Do not duplicate the ABC contract definition — link to `[the probe contract](../docs/localv2.md#4-the-probe-contract)` (verify the anchor resolves) and `[Component design](../docs/phases/01-context-gather-layer-a-node/phase-arch-design.md#component-design)`. For `version` semantics, link to the existing `## Probe version bumps` H3 by relative anchor (`#probe-version-bumps`); do not re-explain. End with a one-paragraph "Extending this cheat sheet" subsection per AC-1.

3. **Reconcile the `Coverage ratchet` table (AC-8).** Replace the existing 3-row table at lines 131–135 with the AC-8 table (Phase 0 = 85/75; Phase 1 = 90/80 with carve-outs; Phase 2 = 92/82 proposed). Drop any prose that contradicts the new values; one new sentence below the table cites ADR-0005 for the carve-outs and the `_phase2_issues/5-*.md` draft for the Phase 2 proposal.

4. **Confirm `mkdocs.yml`** still lists `contributing.md` under `nav` (it does — line 47; this is a no-op verification). Run `mkdocs build --strict` locally; fix any link warnings (likely the first cycle catches a typo in a probe path or an anchor).

5. **Draft the five Phase 2 issue files (Mode A — mandatory).** Create `docs/phases/01-context-gather-layer-a-node/_phase2_issues/` and land the five files per AC-3:
   - `1-implement-index-health-probe.md`
   - `2-promote-warningid-to-typed-enum.md`
   - `3-decide-subschema-versioning-policy.md`
   - `4-extend-memo-allowlist.md`
   - `5-decide-phase2-coverage-target.md`
   Each file: H1 = canonical title verbatim from AC-3; body 4–8 sentences with origin citation per AC-4; literal `Extension surface:` line per AC-3; `Labels: phase-2, <type>`; `Milestone: Phase 2`. Drafts are auditable in the PR diff before any side effect runs.

6. **Author the Phase 1 README `## Exit criteria` + `## Handoff record` sections (AC-5).** Append both H2s to `docs/phases/01-context-gather-layer-a-node/README.md`, after the existing `## Provenance` section. Goal→closing-story mapping (use this verbatim — these are the citations to put on each ticked box):

   | Goal (from `phase-arch-design.md §"Goals"`) | Closing artifact / citation token |
   |---|---|
   | G1 — Useful `repo-context.yaml` on a real Node.js repo | `tests/integration/probes/test_layer_a_end_to_end.py` — S5-05 |
   | G2 — Cache hits on second run (all six Layer A probes) | `tests/integration/probes/test_cache_hit_on_real_repo.py` — S5-05 |
   | G3 — Schema validation at envelope + per-probe sub-schema | `tests/unit/test_sub_schemas.py` — S1-10 + S5-05 |
   | G4 — Probe contract conformance (snapshot test green) | `tests/unit/test_probe_contract.py` — S1-06 (ADR-0002 amendment) |
   | G5 — Adversarial robustness (≥ 20 hostile inputs, zero RCE/OOM) | `tests/adv/` — S5-01 + S5-02 + S5-03 |
   | G6 — Hard caps in every parser (5 MB / 50 MB / depth 64) | `src/codegenie/parsers/` — S1-02 + S1-03 + S1-04 |
   | G7 — Coverage ratchet 90/80 with 85/75 carve-outs | `pyproject.toml --cov-fail-under=90` — S6-02 (carve-outs declared S4-04) |
   | G8 — Tokens per run = 0 (`fence` job continues to assert) | Phase 0 `fence` workflow — cross-cutting (Phase 0 §G7) |
   | G9 — Wall-clock targets (advisory) | `tests/bench/test_warm_path_latency.py` — S6-02 |
   | G10 — Extension by addition holds (exactly three Phase 0 in-place edits) | cross-cutting — S1-01..S1-10 (each ADR-gated edit; verified by ADR-0001 + ADR-0002 amendment scope sentinel) |

   Each line in the README rendered as `- [x] **G{n} — <short title>.** <citation per the table above>`. Then author the `## Handoff record` per AC-5: PR URL, SHA, workflow-run URL (3.11 + 3.12), Phase 2 milestone URL (or `TBD — milestone not yet created` if absent), and the five Phase 2 issue URLs from AC-3 Mode B (or the five `_phase2_issues/*.md` paths from Mode A if Mode B was not run).

7. **Land the mandatory tests (AC-9 + AC-2 grep oracle).** Create `tests/docs/__init__.py` (empty if needed) + `tests/docs/test_phase1_readme_closed.py` (per AC-9) + `tests/docs/test_contributing_cheat_sheet.py` (per AC-2 + AC-4 + AC-8). Run them; they should all pass against the README + contributing.md edits authored above. Test red phase: temporarily comment out one ticked checkbox in the README; confirm `test_phase1_exit_criteria_all_ticked` fails. Restore.

8. **(Optional) File the five issues via `gh` (Mode B).** If `gh auth status` succeeds with `repo` scope: `gh api repos/:owner/:repo/milestones --jq '.[].title'` to confirm `Phase 2` exists (if not, file a one-line PR creating it before this story merges). Then for each `_phase2_issues/*.md` file: `gh issue create --title "<H1>" --body-file <file> --label phase-2,<type> --milestone "Phase 2"`. Capture the five resulting URLs and paste them into the README `## Handoff record` (replacing the draft-file paths) and the Step 6 PR body.

9. **Final pass.** `make check` (lint + typecheck + test — including the new `tests/docs/`). `mkdocs build --strict`. Run `git diff --name-only origin/main..HEAD -- src/ | wc -l` and confirm the result is `0` (AC-10). Update the Step 6 PR body per AC-11.

## TDD plan — red / green / refactor

This is primarily a documentation + issues-board story, but it now has two mandatory test files (AC-9 + AC-2) and several runnable verifiers. Per Rule 9, every AC has at least one machine-checkable assertion or grep oracle.

### Red — write the failing tests first

1. **`tests/docs/test_phase1_readme_closed.py` — fails before the README is authored.** Parse the README; assert no `- [ ]` markers exist anywhere AND every `- [x]` inside `## Exit criteria` ends with a `S\d+-\d{2}` token or an `actions/runs/` URL substring. Pre-edit, the test fails because there is no `## Exit criteria` section at all.

   ```python
   # tests/docs/test_phase1_readme_closed.py
   from pathlib import Path
   import re

   README = Path("docs/phases/01-context-gather-layer-a-node/README.md")
   STORY_CITATION = re.compile(r"\bS\d+-\d{2}\b")
   WORKFLOW_RUN = re.compile(r"actions/runs/")
   EXIT_CRITERIA_SECTION = re.compile(
       r"^## Exit criteria\b(.*?)(?=^## |\Z)", flags=re.MULTILINE | re.DOTALL
   )

   def test_phase1_exit_criteria_all_ticked() -> None:
       text = README.read_text()
       unchecked = re.findall(r"^\s*-\s*\[\s\]\s+.*$", text, flags=re.MULTILINE)
       assert not unchecked, f"Phase 1 closure: {len(unchecked)} unchecked boxes:\n" + "\n".join(unchecked)

   def test_phase1_exit_criteria_each_box_has_story_citation() -> None:
       text = README.read_text()
       section = EXIT_CRITERIA_SECTION.search(text)
       assert section, "README missing `## Exit criteria` section"
       ticked = re.findall(r"^\s*-\s*\[x\]\s+.+$", section.group(1), flags=re.MULTILINE)
       assert ticked, "Exit criteria section has no ticked boxes"
       for line in ticked:
           assert STORY_CITATION.search(line) or WORKFLOW_RUN.search(line), (
               f"ticked box missing story citation or workflow-run URL: {line}"
           )
   ```

2. **`tests/docs/test_contributing_cheat_sheet.py` — fails before the H3 + ratchet table land.** Three assertions:
   - `test_cheat_sheet_references_all_phase1_probes` — greps for each of the five `src/codegenie/probes/<name>.py` substrings; fails if any is missing.
   - `test_cheat_sheet_covers_all_six_subsections` — case-insensitive grep for the six subsection markers (`register`, `ABC`, `additionalProperties`, `parsed_manifest`, `WarningId`, `coverage`); fails if any is absent.
   - `test_ratchet_table_matches_shipped_values` — greps for the three `90/80`, `85/75`, `92/82` substrings; fails if the stale `87/77` line is still present.
   - `test_phase2_issue_drafts_cite_origin` — for each `_phase2_issues/[1-9]-*.md` file, grep for the AC-4 origin regex; fails if any is missing.
   - `test_no_duplicate_adding_a_probe_h2` — `grep -c '^## Adding a probe$'` returns exactly 1.

   ```python
   # tests/docs/test_contributing_cheat_sheet.py
   from pathlib import Path
   import re

   CONTRIB = Path("docs/contributing.md")
   ISSUE_DIR = Path("docs/phases/01-context-gather-layer-a-node/_phase2_issues")
   REQUIRED_PROBE_REFS = [
       "src/codegenie/probes/node_build_system.py",
       "src/codegenie/probes/node_manifest.py",
       "src/codegenie/probes/deployment.py",
       "src/codegenie/probes/ci.py",
       "src/codegenie/probes/test_inventory.py",
   ]
   REQUIRED_SUBSECTION_TOKENS = [
       "register", "ABC", "additionalProperties",
       "parsed_manifest", "WarningId", "coverage",
   ]
   ORIGIN_RE = re.compile(
       r"docs/phases/01-context-gather-layer-a-node/(phase-arch-design|High-level-impl|ADRs/[0-9]{4}-[a-z0-9-]+)\.md"
   )

   def test_no_duplicate_adding_a_probe_h2() -> None:
       text = CONTRIB.read_text()
       assert text.count("\n## Adding a probe\n") + (1 if text.startswith("## Adding a probe\n") else 0) == 1

   def test_cheat_sheet_references_all_phase1_probes() -> None:
       text = CONTRIB.read_text()
       missing = [p for p in REQUIRED_PROBE_REFS if p not in text]
       assert not missing, f"cheat sheet missing probe refs: {missing}"

   def test_cheat_sheet_covers_all_six_subsections() -> None:
       text = CONTRIB.read_text().lower()
       missing = [t for t in REQUIRED_SUBSECTION_TOKENS if t.lower() not in text]
       assert not missing, f"cheat sheet missing subsection markers: {missing}"

   def test_ratchet_table_matches_shipped_values() -> None:
       text = CONTRIB.read_text()
       for required in ("90", "85/75", "92"):
           assert required in text, f"ratchet table missing required value: {required}"
       assert "87/77" not in text, "stale Phase 1 = 87/77 row still present"

   def test_phase2_issue_drafts_cite_origin() -> None:
       drafts = sorted(ISSUE_DIR.glob("[1-9]-*.md"))
       assert len(drafts) == 5, f"expected exactly 5 Phase 2 issue drafts, found {len(drafts)}"
       for draft in drafts:
           body = draft.read_text()
           assert ORIGIN_RE.search(body), f"draft {draft.name} missing origin citation"
           assert "Extension surface:" in body, f"draft {draft.name} missing Extension surface line"
   ```

3. **One-shell verifiers (run by the executor; output pasted into PR body):**

   ```sh
   # AC-3 Mode A set equality
   ls docs/phases/01-context-gather-layer-a-node/_phase2_issues/[1-9]-*.md | wc -l   # must == 5

   # AC-3 Mode B set equality (only if gh was run)
   gh issue list --milestone "Phase 2" --label phase-2 --json title --jq '.[].title' | sort > /tmp/actual.txt
   cat <<'EOF' | sort > /tmp/expected.txt
   Implement `IndexHealthProbe (B2)` — Phase 2 load-bearing probe
   Promote `WarningId` to typed enum (open question #7)
   Decide per-probe sub-schema release-versioning policy (open question #2)
   Extend `ParsedManifestMemo` allowlist beyond `package.json`
   Decide Phase 2 coverage target — proposed 92/82
   EOF
   diff /tmp/expected.txt /tmp/actual.txt   # must be empty

   # AC-10 scope guard
   git diff --name-only origin/main..HEAD -- src/ | wc -l   # must == 0

   # AC-6 docs
   mkdocs build --strict   # must succeed
   ```

### Green — make it pass

1. Author the contributing.md cheat-sheet H3 + reconcile the ratchet table. Run `tests/docs/test_contributing_cheat_sheet.py`; iterate until all five assertions pass.
2. Draft the five `_phase2_issues/*.md` files. Run `test_phase2_issue_drafts_cite_origin`; iterate.
3. Author the README `## Exit criteria` + `## Handoff record` sections per the goal→story mapping in Implementation outline §6. Run `tests/docs/test_phase1_readme_closed.py`; iterate.
4. Run `mkdocs build --strict`; fix any link warnings.
5. (Optional) If `gh` is authenticated, file the five issues; capture URLs into the README handoff record + PR body.
6. `make check` to confirm no regression.
7. Run the one-shell verifiers; paste outputs into the PR body per AC-11.

### Refactor — clean up

- The cheat sheet H3 may grow over time as Phase 2/3 probes add patterns. Phase 1 ships the minimum viable H3; do not preemptively expand for hypothetical future patterns (Rule 2). Use the "Extending this cheat sheet" subsection to encode the convention; let Phase 2's executor add their H4 when they need it.
- If the goal→story mapping in §6 turns out to be wrong for a particular goal (e.g., G3 actually closes at S5-04 not S5-05), update the mapping in this story's Implementation outline FIRST, then the README — keep the two in sync.
- Confirm the contributing.md examples format consistently: backtick-fenced AND linked for class names; relative markdown links for cross-references; no absolute URLs to GitHub (they break on fork).
- After Mode B has been run, refactor the README handoff record to replace draft-file paths with the actual issue URLs (do this in the same Step 6 PR, not a follow-up).

## Files to touch

| Path | Why |
|---|---|
| `docs/contributing.md` | Modify — append `### Phase 1+ probes (cheat sheet)` H3 inside the existing `## Adding a probe` H2 (do NOT duplicate the H2); reconcile the `Coverage ratchet` table (lines 131–135) per AC-8. |
| `docs/phases/01-context-gather-layer-a-node/README.md` | Modify — append `## Exit criteria` H2 (10 ticked boxes per pre-authored goal→story mapping) + `## Handoff record` H2 (PR URL, SHA, workflow-run URL, milestone URL, ≥5 issue URLs). Preserve existing `## Reading order`, `## Status update`, and `## Provenance` sections. |
| `docs/phases/01-context-gather-layer-a-node/_phase2_issues/1-implement-index-health-probe.md` | Create — Mode A draft for Phase 2 issue #1 (IndexHealthProbe). |
| `docs/phases/01-context-gather-layer-a-node/_phase2_issues/2-promote-warningid-to-typed-enum.md` | Create — Mode A draft for Phase 2 issue #2 (WarningId enum). |
| `docs/phases/01-context-gather-layer-a-node/_phase2_issues/3-decide-subschema-versioning-policy.md` | Create — Mode A draft for Phase 2 issue #3 (sub-schema versioning). |
| `docs/phases/01-context-gather-layer-a-node/_phase2_issues/4-extend-memo-allowlist.md` | Create — Mode A draft for Phase 2 issue #4 (memo allowlist). |
| `docs/phases/01-context-gather-layer-a-node/_phase2_issues/5-decide-phase2-coverage-target.md` | Create — Mode A draft for Phase 2 issue #5 (coverage target proposal). |
| `tests/docs/__init__.py` | Create if absent — empty package init so `tests/docs/` is discoverable by pytest. |
| `tests/docs/test_phase1_readme_closed.py` | Create — AC-9 mandatory test asserting README closure invariant. |
| `tests/docs/test_contributing_cheat_sheet.py` | Create — AC-2 + AC-4 + AC-8 grep oracle tests for the cheat sheet, the ratchet table, and the Phase 2 issue drafts. |
| `mkdocs.yml` | No change (verification only — `contributing.md` already nav-included at line 47). |
| GitHub Project board / Issues | Mode B optional — five Phase 2 follow-up issues created from the Mode A drafts if `gh` is authenticated; not a file in the repo, but a deliverable for the closing PR. |

## Out of scope

- **Designing `IndexHealthProbe`.** That's Phase 2 work. The Mode A draft (`_phase2_issues/1-implement-index-health-probe.md`) names the load-bearing surface (silent staleness; `confidence` + `warnings` aggregation) and the extension surface (new file; no edits to existing probes) and stops. Do not start drafting the probe here.
- **Promoting `WarningId` to an enum.** Filed as a Phase 2 follow-up draft; not implemented here. The pattern constraint is the Phase 1 minimum defense (ADR-0007).
- **Extending the memo allowlist.** The allowlist stays at `{"package.json"}` for Phase 1. Phase 2 extends additively per ADR-0002's documented growth path.
- **Coverage ratchet to 92/82.** Phase 2 work. Phase 1 lands 90/80 with carve-outs (S6-02); the further bump is drafted as a *proposal* in `_phase2_issues/5-*.md`, not a prescription for Phase 2.
- **Phase 2's golden portfolio.** S6-01 ships one golden; the Phase 2 expansion is Phase 2's responsibility. Do not preemptively seed Phase 2 fixtures.
- **A typed-warning-IDs enum migration tool.** Phase 2 work. If the enum promotion lands, a migration of existing string warnings is necessary — that's part of the Phase 2 issue body, not Phase 1.
- **Parameterized `tests/docs/test_phase_readme_closed.py` across all phases.** That's Phase 2's rule-of-three trigger: Phase 0 + Phase 1 = two phases with the closure invariant; Phase 2's S6-X-handoff is the third instance. Phase 2's executor extracts the parameterized test then. This story ships the per-phase `test_phase1_readme_closed.py` only (AC-9).
- **`probe-patterns.yaml` queryable manifest.** First-occurrence cheat sheet ships as markdown prose (Rule 2 — three similar lines is better than premature abstraction). The future-extraction trigger is a Phase 4+ Skill or Planner consumer needing programmatic pattern lookup; until then, the markdown is the source of truth.
- **A `scripts/check_doc_anchors.py` deep-anchor validator.** `mkdocs build --strict` validates file-level relative links but is permissive on intra-doc anchors. Surface as a manual-eyeball reviewer step (Notes-for-implementer); do not add a new script absent a recurring failure pattern (Rule 2).
- **A standing CI gate enforcing exactly five Phase 2 issues exist on the milestone.** Phase 2 PRs naturally add more issues; a strict count gate would fight that workflow. The `diff` set-equality verifier is a one-shot at story execution time, not a standing gate.

### Deviation policy for the five Phase 2 issues (per CLAUDE.md "Fail loud")

If during execution the implementer discovers a sixth open question genuinely worth filing (e.g., a real ambiguity surfaces while authoring the cheat sheet), file it as a sixth `_phase2_issues/6-*.md` draft AND note in the PR body: "Discovered a sixth follow-up during execution: [path]. AC-3 list extended from five to six." If one of the five is already resolved by an unrelated PR, do NOT file it; instead note in the PR body: "Issue X (\<title\>) is already resolved by [PR link]; AC-3 list reduced from five to four." The README handoff record reflects whichever count actually shipped. Do not silently trim or pad to match the literal "five" in this story — surface the deviation explicitly.

## Notes for the implementer

- **The cheat sheet's job is to be an *index*, not a *textbook*.** A new contributor should be able to skim it in 5 minutes and know where to look for each pattern. If a subsection exceeds 15 lines, you're explaining instead of pointing.
- **Cite Phase 1 probes by relative path AND wrap in markdown link.** Bare backticked class names in prose drift silently when files are renamed. Use `` [`NodeBuildSystemProbe`](../src/codegenie/probes/node_build_system.py) `` so a rename trips `mkdocs build --strict`. AC-2 enforces this.
- **The Phase 1 README has NO existing exit-criteria checklist.** Phase 0's README is the worked example to copy (the `## Exit criteria` + `## Handoff record` H2s shipped by Phase 0 S5-02 AC-8). Read [`../../00-bullet-tracer-foundations/README.md`](../../00-bullet-tracer-foundations/README.md) and [`../../00-bullet-tracer-foundations/stories/S5-02-project-artifacts-handoff.md`](../../00-bullet-tracer-foundations/stories/S5-02-project-artifacts-handoff.md) before authoring. The structure is non-negotiable: the rule-of-three pattern (Phase 0 → Phase 1 → Phase 2) needs Phase 1 to inherit the shape verbatim so Phase 2 inherits a stable contract.
- **Mode A is mandatory; Mode B is optional.** The autonomous executor stays inside the file-edit envelope by default (drafting the five `_phase2_issues/*.md` files is fully auditable in the PR diff). Filing the issues via `gh` is irreversible and is gated on `gh auth status` + sufficient scope. If `gh` is not authenticated, the PR body cites the five drafts + names a maintainer to file at merge time. CLAUDE.md "Humans always merge" applied broadly to "autonomy ends at PR creation."
- **Each Phase 2 issue draft names its `Extension surface:`.** This is what makes the issue actionable for an autonomous executor in Phase 2 — they don't re-derive whether they may edit existing code. CLAUDE.md "Extension by addition" applied to issue templates. The default surface is "no edits to existing files"; any exception names the ADR that authorizes it.
- **Issue title prefix discipline (suggestion, not enforced).** Consider tagging each issue title with `[probe]`, `[schema]`, `[infra]`, or `[ratchet]` for Phase 2+ grep-ability and label composability. This is a soft convention; if the Phase 2 author prefers labels-only, drop. The point is: pick one and document it in the README handoff record so Phase 3 inherits.
- **Milestone alignment.** Before Mode B issue creation, run `gh api repos/:owner/:repo/milestones --jq '.[].title'` to confirm `Phase 2` exists. If absent, file a one-line PR creating the milestone before this story merges; do not invent ad-hoc labels.
- **`mkdocs build --strict`** is in CI already (Phase 0 S1-04). Running it locally catches link rot before CI does; do it. **Caveat:** strict mode validates file-level relative links but is permissive on intra-doc anchors (`docs/foo.md#some-section`). Manually eyeball any deep-anchor references in the cheat sheet content; prefer file-level links over deep anchors when possible.
- **If a Phase 2 issue overlaps an existing GitHub issue**, link rather than duplicate. The five named issues are specific enough to be new; if one exists already (e.g., someone filed "IndexHealthProbe" months ago during design), tag and reference rather than re-file. Note the deviation in the PR body per the Out-of-scope deviation policy.
- **The Step 6 PR body is the closing artifact for Phase 1.** AC-11 makes the contents contractual: (a) the five `_phase2_issues/*.md` paths + (Mode B) URLs; (b) the per-module coverage table from S6-02; (c) the byte-identical `sha256` lines from S6-01's regen verification; (d) a checkbox list mirroring the README `## Exit criteria`, all ticked. Reviewers should be able to close Phase 1 without leaving the PR.
- **Do not touch `src/`.** AC-10 makes this machine-checkable. If you find yourself editing a probe to "fix" a documentation example, stop — the probe is the canonical example, and the doc points at *it*, not the other way around. If a `src/` edit is genuinely necessary, ship it in a separate PR with its own justification.
- **Phase 7 inherits `native_modules.yaml`.** The cheat sheet's catalog cross-reference subsection (if you include it under (a) or as a sub-bullet of (b)) can mention this in one line; do not write a Phase 7 design preview.
- **Future-extraction note for Phase 2's executor.** A `tests/docs/test_phase_readme_closed.py` parameterized over `docs/phases/*/README.md` is the rule-of-three target — Phase 0 + Phase 1 = two; Phase 2's S6-X handoff is the third instance. Per Rule 2, do NOT extract here. The Phase 2 executor will see the pattern and lift it. If they want it pre-filed as a Phase 2 issue, leave a note in `_phase2_issues/6-*.md` (deviation per the policy above).
- **Future-extraction note for Phase 4+ tooling.** If a Phase 4+ Skill or Planner agent needs programmatic access to the probe-patterns catalog, the rule-of-three trigger is to migrate the cheat sheet from markdown prose to a `docs/contributing/probe-patterns.yaml` manifest rendered by an mkdocs plugin. Phase 1 is the first occurrence; do NOT promote here.
