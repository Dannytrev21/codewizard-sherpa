# Story S8-04 — Phase-3 handoff issues + `docs/contributing.md` cheat-sheet + Phase 2 README exit-criteria close

**Step:** Step 8 — Confidence section renderer + CI ratchet + advisory benches + Phase-3 handoff
**Status:** Ready
**Effort:** S
**Depends on:** S8-03 (eight CI jobs green on `main`)
**ADRs honored:** 02-ADR-0007 (no Plugin Loader in Phase 2 — Phase 3 ships loader + first plugin + adapters together); 02-ADR-0006 (`IndexFreshness` sum-type location — any drift by Phase 3 requires an ADR amendment to ADR-0006); 02-ADR-0001 (`ALLOWED_BINARIES` — Phase 3 extends with `npm`, `jq` via a fresh ADR or amendment); production ADR-0031 (plugin architecture — Phase 3 owns the loader); production ADR-0032 (language search adapters — Phase 3 owns the four adapter implementations)

## Context

Phase 2 ships kernel-side scaffolding only: adapter `Protocol`s, `TCCMLoader`, `SkillsLoader`, `IndexFreshness`, registration plumbing. The **Plugin Loader itself**, the **universal `(*, *, *)` fallback plugin**, and the **first concrete plugin** (`plugins/vulnerability-remediation--node--npm/`) are deliberately deferred to Phase 3 per ADR-0007 + ADR-0031 §Consequences §1. This is the **handoff** — five GitHub issues filed on the Project board, each with milestones aligned to `roadmap.md §"Phase 3 — Vuln remediation: deterministic recipe path"`, so Phase 3 has a fully-loaded backlog the moment it starts.

The handoff is also the moment to **close the Phase 2 README's exit-criteria checklist** and update `docs/contributing.md` with the "adding a Layer B/C/D/E/G probe" cheat-sheet. The cheat-sheet uses Phase 2's now-shipped probes as canonical examples — `IndexHealthProbe` (B2), `RuntimeTraceProbe` (C4), `SemgrepProbe` (G), `SkillsIndexProbe` (D), `ConventionsProbe` (D), `OwnershipProbe` stub (E) — so a new probe author can copy a real probe and only edit what's task-specific.

The most load-bearing of the five issues is **#4** — *unskip `tests/adv/phase02/test_phase3_handoff_smoke.py`*. That test landed `@pytest.mark.skip(reason="Phase 3 entry-gate review unskips")` in S7-04; unskipping it at the start of Phase 3 forces a re-verification that Phase 2's four adapter `Protocol`s are imported **unchanged**. Any drift (e.g., Phase 3 discovers `consumers(self, pkg: str)` should be `consumers(self, pkg: PackageId, *, transitively: bool = False)`) requires an **explicit ADR amendment** to 02-ADR-0006 or 02-ADR-0007 — not a silent Protocol edit. This is the contract trip-wire phase-arch-design.md §"Gap 1" identified; this issue is what makes Phase 3 honor it.

This is the smallest story in Step 8 in code terms (zero new `src/` code) and the largest in coordination terms (cross-phase contract handoff, GH Project automation, contributor docs).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Integration with Phase 3"` — the table of "what Phase 3 inherits from Phase 2 on day 1, unchanged" + "Implicit guarantees Phase 3 will rely on" + "New artifacts Phase 2 produces that Phase 3 consumes". This is the canonical source for the five handoff issues' content.
  - `../phase-arch-design.md §"Gap analysis"` Gap 1 — Adapter Protocol drift; the `test_phase3_handoff_smoke.py` trip-wire.
  - `../phase-arch-design.md §"Adversarial tests"` — `test_phase3_handoff_smoke.py` row.
- **Phase ADRs:**
  - `../ADRs/0007-no-plugin-loader-in-phase-2.md` — the rationale; Phase 3 ships loader + first plugin + adapters together.
  - `../ADRs/0006-index-freshness-sum-type-location.md` — variant set is stable; Phase 3 extension requires amendment.
  - `../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md` — Phase 3 amendment for `npm`, `jq` is the cleanest precedent.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` §Consequences §1 — first plugin doubles as the proof the loader works.
  - `../../../production/adrs/0032-language-search-adapters.md` — the four adapter Protocols Phase 3 implements.
- **Source design:**
  - `../final-design.md §"What's next — handoff to Phase 3"` (~lines 370–382 of `High-level-impl.md`'s equivalent section) — full prose of the four handoff bullets.
  - `../final-design.md §"Open questions deferred to implementation"` — backlog items this story files.
- **Roadmap:**
  - `../../../roadmap.md §"Phase 3 — Vuln remediation: deterministic recipe path"` — milestone name; issue milestones align to this.
- **Existing code (Phase 2 artifacts the handoff issues reference):**
  - `src/codegenie/adapters/protocols.py` (S1-03) — four Protocols (`DepGraphAdapter`, `ImportGraphAdapter`, `ScipAdapter`, `TestInventoryAdapter`) — Phase 3 implements these.
  - `src/codegenie/indices/freshness.py` (S1-01) — `IndexFreshness` variant set.
  - `src/codegenie/tccm/` (S1-04, S2-03) — `TCCMLoader` Phase 3 invokes against the first plugin's `tccm.yaml`.
  - `src/codegenie/skills/loader.py` (S2-01) — three-tier merge Phase 3's plugin Skills route through.
  - `src/codegenie/exec.py` (S1-07) — `run_external_cli` + `ALLOWED_BINARIES`; Phase 3 amends with `npm`, `jq`.
  - `tests/adv/phase02/test_phase3_handoff_smoke.py` (S7-04) — landed skipped; Phase 3 unskips.
  - `docs/contributing.md` (Phase 0/1) — existing contributor docs to extend.
  - `docs/phases/02-context-gather-layers-b-g/README.md` — exit-criteria checklist to mark complete.

## Goal

Three deliverables:

1. **File five Phase-3 handoff issues** on the GitHub Project board with milestones aligned to `roadmap.md §"Phase 3"`. Use `gh issue create --project <board>` (Phase 0 likely already names the board; reuse, do not invent a new project). Each issue references the relevant Phase 2 artifact and the named ADR(s) governing it.
2. **Update `docs/contributing.md`** with a new section titled "Adding a Layer B/C/D/E/G probe" referencing Phase 2's shipped probes as canonical examples. Verify the doc builds under `mkdocs build --strict` and remains in the curated nav. File the four "Decisions noted but not yet documented" deferred items (Phase 2 README §"Open implementation questions" #2, #4, #5) as backlog issues if they aren't already.
3. **Mark `docs/phases/02-context-gather-layers-b-g/README.md`'s exit-criteria checklist complete.** The README itself does not currently have a checklist section; this story adds one at the bottom of the README mirroring the table from `stories/README.md` §"Exit-criteria coverage" with `[x]` boxes for every Phase 2 exit criterion. Each `[x]` is justified by one or more story IDs.

## Acceptance criteria

- [ ] **AC-1 (issue #1 filed — Plugin Loader + `plugin.yaml` parser).** A GitHub issue titled `[Phase 3] Implement Plugin Loader + plugin.yaml parser` exists on the Project board with milestone `Phase 3 — Vuln remediation: deterministic recipe path`. Body references ADR-0007 (Phase 2 deliberately defers), ADR-0031 (production-level plugin architecture), and names the four adapter Protocols at `src/codegenie/adapters/protocols.py` as the import target. `tests/unit/docs/test_phase3_handoff_issues.py::test_issue_1_exists` queries `gh issue list --json title,milestone,body --search 'Plugin Loader'` (or reads an `issues.json` artifact committed by the issue-creation script) and asserts (a) one matching issue; (b) milestone set; (c) body mentions `ADR-0007` and `ADR-0031`.
- [ ] **AC-2 (issue #2 filed — first plugin + four ADR-0032 adapter implementations).** Issue titled `[Phase 3] Implement plugins/vulnerability-remediation--node--npm/ with four adapter implementations`. Body lists the four implementations expected (`dep_graph_npm.py`, `import_graph_node.py`, `scip_node.py`, `test_inventory_node.py`) per phase-arch-design.md §"Integration with Phase 3" table, references ADR-0032, and names the Phase 2 fixtures (`monorepo-pnpm` + `minimal-ts`) as the first-recipe targets. AC-1's test pattern repeats for this issue.
- [ ] **AC-3 (issue #3 filed — universal `(*, *, *)` fallback plugin / HITL escalation).** Issue titled `[Phase 3] Implement universal (*, *, *) fallback plugin (HITL escalation)`. Body explains the role (when no concrete plugin matches the task-class/language/PM tuple) and references `production/design.md` §"Humans always merge" and ADR-0031.
- [ ] **AC-4 (issue #4 filed — unskip `test_phase3_handoff_smoke.py` + assert Protocols imported unchanged).** Issue titled `[Phase 3] Unskip tests/adv/phase02/test_phase3_handoff_smoke.py at entry-gate review`. Body explicitly states: *"Any Protocol drift requires an explicit ADR amendment to 02-ADR-0006 / 02-ADR-0007. The test's existing skip-reason names this contract."* This is the load-bearing handoff issue — phase-arch-design.md §"Gap 1" trip-wire.
- [ ] **AC-5 (issue #5 filed — extend `ALLOWED_BINARIES` for `npm`, `jq`).** Issue titled `[Phase 3] Extend ALLOWED_BINARIES for npm and jq + amend or add new ADR`. Body references 02-ADR-0001 as the precedent, names `src/codegenie/exec.py` as the file to edit, and explicitly forbids adding "while we're at it" binaries (Implementation risk #2 discipline).
- [ ] **AC-6 (`docs/contributing.md` — "Adding a Layer B/C/D/E/G probe" cheat-sheet present + builds under `mkdocs build --strict`).** `docs/contributing.md` contains a new H2 section titled "Adding a Layer B/C/D/E/G probe" whose body covers the seven steps: (1) pick a Layer letter; (2) subclass `Probe`; (3) decorate with `@register_probe(heaviness=, runs_last=)`; (4) declare `declared_inputs`/`applies_to_tasks`/`applies_to_languages`/`timeout_seconds`; (5) emit a typed `ProbeOutput.schema_slice` via Pydantic (forbid `model_construct`); (6) route external CLIs through `run_external_cli` (B/G) or `run_allowlisted` (C only); (7) register an `IndexFreshness` check via `@register_index_freshness_check` if you produce a cacheable index. Each step names a Phase 2 probe as a canonical example (B2 `IndexHealthProbe`, C4 `RuntimeTraceProbe`, G `SemgrepProbe`, D `ConventionsProbe`). The doc passes `mkdocs build --strict` (no broken links, no orphan files) and appears in `mkdocs.yml`'s nav under the contributor section. `tests/unit/docs/test_contributing_cheatsheet.py` asserts the section exists, lists the seven steps, and contains each canonical-example probe name.
- [ ] **AC-7 (`docs/phases/02-context-gather-layers-b-g/README.md` — exit-criteria checklist appended + every entry `[x]`).** The README's bottom now contains a new H2 section "Phase 2 exit-criteria — closed" with a checklist that mirrors `stories/README.md` §"Exit-criteria coverage". Every checkbox is `[x]`. Each `[x]` line names the story IDs that closed it. `tests/unit/docs/test_phase2_readme_checklist_closed.py` parses the README, asserts (a) the section heading exists; (b) every checkbox is `[x]`, none are `[ ]`; (c) the set of checkbox lines matches the set of exit-criterion rows in `stories/README.md`.
- [ ] **AC-8 (backlog issues filed for "Decisions noted but not yet documented" #2, #4, #5).** Three additional GitHub issues exist on the Project board, milestoned for *post-Phase-3* (`Backlog` milestone or named milestones):
  - "Full-repo `mypy --warn-unreachable` rollout" (per README §"Open implementation questions" #2 — backlog item).
  - "`ExternalDocsProbe` host-allowlist config schema" (per #4 — first arises when a real user opts in; Phase-4-or-later).
  - "`SkillsLoader` per-tier signing (Sigstore-style)" (per #5 — Phase 14 concern).
- [ ] **AC-9 (`adv-phase02` job still load-bearing post-handoff).** The `test_phase3_handoff_smoke.py` file stays skipped at end of Phase 2 (Phase 3's job to unskip). `tests/adv/phase02/test_phase3_handoff_smoke.py` retains its `@pytest.mark.skip(reason="Phase 3 entry-gate review unskips — see [Phase 3] Unskip ... issue #N")` decorator; the issue number is filled in by this story's automation. AC-9 asserts the skip decorator's `reason` string contains the literal issue number (or `#N` placeholder if the issue automation runs after the test snapshot, in which case a follow-up commit on this story updates the reason).
- [ ] **AC-10 (Phase 2 closing-PR sign-off — every Step 8 done-criterion box `[x]`).** `docs/phases/02-context-gather-layers-b-g/High-level-impl.md` §"Step 8 — Done criteria" — every checkbox marked `[x]`. The sign-off PR description lists the eight done-criterion items and links the story IDs that closed each. `tests/unit/docs/test_step8_done_criteria_closed.py` asserts no `[ ]` boxes remain in the Step 8 section.

## Out of scope

- Implementing any Phase 3 code. Plugin Loader, first plugin, adapters, `npm`/`jq` allowlist edits are **all Phase 3**. This story files issues only.
- Unskipping `test_phase3_handoff_smoke.py`. That action belongs to Phase 3's entry-gate review (covered by issue #4).
- Editing the four adapter `Protocol`s at `src/codegenie/adapters/protocols.py`. Any drift is an ADR amendment, not silent code change (Implementation risk #8).
- Adding a "Phase 2 retrospective" document. Useful, but not required by the roadmap; if the team wants one, a separate ticket.
- Migrating `docs/contributing.md` to a new doc system. Stay in `mkdocs` (the Phase 0 baseline).
- Editing `roadmap.md` to mark Phase 2 done. The roadmap update is its own commit on the closing PR; mechanical, not part of this story's tests.

## Files to touch

**New:**

- `tests/unit/docs/__init__.py` — empty.
- `tests/unit/docs/test_phase3_handoff_issues.py` — AC-1 through AC-5 (and AC-8 backlog issues). Reads from a generated `tests/unit/docs/_fixtures/issues.json` (committed; produced by the issue-creation script's `--dry-run` mode) — this avoids GH API calls in unit tests while still asserting the issue payload shape.
- `tests/unit/docs/test_contributing_cheatsheet.py` — AC-6.
- `tests/unit/docs/test_phase2_readme_checklist_closed.py` — AC-7.
- `tests/unit/docs/test_step8_done_criteria_closed.py` — AC-10.
- `scripts/file_phase3_handoff_issues.py` — a small helper that, given a `--project <board-name>` arg, files the eight issues (5 handoff + 3 backlog) via `gh issue create`. Has a `--dry-run` flag that emits the JSON payload to `tests/unit/docs/_fixtures/issues.json` for the unit tests above. **One source of truth** for the issue contents.
- `tests/unit/docs/_fixtures/issues.json` — committed output of the dry-run; the unit tests read this rather than hitting GH live.

**Modified:**

- `docs/contributing.md` — append H2 "Adding a Layer B/C/D/E/G probe" section per AC-6.
- `mkdocs.yml` — ensure the contributing section appears in nav (likely already does; verify, don't restructure).
- `docs/phases/02-context-gather-layers-b-g/README.md` — append H2 "Phase 2 exit-criteria — closed" checklist per AC-7.
- `docs/phases/02-context-gather-layers-b-g/High-level-impl.md` — mark every Step 8 done-criterion box `[x]` per AC-10. (Other steps' done-criteria are closed by their own stories; this story closes Step 8 only.)
- `tests/adv/phase02/test_phase3_handoff_smoke.py` — update the `@pytest.mark.skip` reason string to include the filed issue number (one-line edit; AC-9).

**Untouched (DO NOT EDIT):**

- `src/codegenie/adapters/protocols.py` (Implementation risk #8 — Protocol shape is Phase 3's discovery; any drift is ADR amendment).
- Any Phase 2 production `src/` code under `src/codegenie/`.
- `roadmap.md` §"Phase 3" itself (this story files issues against the milestone; the roadmap text is unchanged).

## TDD plan — red / green / refactor

**RED (failing tests committed first):**

1. `test_phase3_handoff_issues.py::test_five_handoff_issues_exist` — reads `tests/unit/docs/_fixtures/issues.json`, asserts five issues with titles matching the AC-1..AC-5 patterns, each with milestone `Phase 3 — Vuln remediation: deterministic recipe path`. Fails red — fixture does not yet exist.
2. `test_phase3_handoff_issues.py::test_issue_4_names_protocol_drift_amendment` — asserts issue #4's body contains the literal phrase `ADR amendment to 02-ADR-0006`. Fails red.
3. `test_phase3_handoff_issues.py::test_three_backlog_issues_exist` — asserts the three backlog issues per AC-8. Fails red.
4. `test_contributing_cheatsheet.py::test_section_exists_with_seven_steps` — parses `docs/contributing.md`, asserts the "Adding a Layer B/C/D/E/G probe" H2 exists with seven enumerated steps; each step contains a canonical Phase 2 probe name. Fails red.
5. `test_contributing_cheatsheet.py::test_mkdocs_build_strict` — invokes `mkdocs build --strict` as a subprocess and asserts exit 0. Fails red until the new section's links resolve.
6. `test_phase2_readme_checklist_closed.py::test_no_unchecked_boxes` — parses `docs/phases/02-context-gather-layers-b-g/README.md`, asserts the "Phase 2 exit-criteria — closed" section exists and every box is `[x]`. Fails red.
7. `test_phase2_readme_checklist_closed.py::test_checklist_matches_stories_readme_table` — asserts the set of checklist lines is a superset/equal of the set of rows in `stories/README.md §"Exit-criteria coverage"`. Fails red.
8. `test_step8_done_criteria_closed.py::test_no_unchecked_boxes_in_step8` — asserts the Step 8 done-criteria section has zero `[ ]` boxes. Fails red.

**GREEN (minimum code to pass):**

1. Write `scripts/file_phase3_handoff_issues.py` with the issue payloads (titles + bodies + milestone + labels) hard-coded inline. Provide `--dry-run` that writes `tests/unit/docs/_fixtures/issues.json` without touching GH.
2. Run the dry-run, commit the generated `issues.json`. The unit tests now pass.
3. Append the "Adding a Layer B/C/D/E/G probe" section to `docs/contributing.md` with the seven enumerated steps, citing Phase 2 probes as canonical examples.
4. Verify `mkdocs build --strict` is clean; fix any broken links.
5. Append the "Phase 2 exit-criteria — closed" section to the Phase 2 README, copying each row from `stories/README.md §"Exit-criteria coverage"` as a `[x]` line with the story IDs.
6. Mark every Step 8 done-criterion box `[x]` in `High-level-impl.md`.
7. Run the file-issue script live (`--no-dry-run`, against the actual Project board) and capture issue numbers; update the `@pytest.mark.skip` reason in `test_phase3_handoff_smoke.py` to reference the filed issue number.

**REFACTOR:**

- If the issue body content duplicates phrasing from `phase-arch-design.md §"Integration with Phase 3"`, link to that section rather than inline-copying — but keep enough body text that a reader landing on the issue from GH Notifications has context without clicking through.
- Double-check no PII / no internal hostnames leaked into issue bodies (Rule 12).
- Validate the JSON fixture round-trips via `json.loads(Path(...).read_text())` and the test fixture stays parseable.
- `ruff format` on the script; `mypy --strict scripts/file_phase3_handoff_issues.py` clean.

## Notes for the implementer

- **Issue #4 is the load-bearing one.** The other four issues are operational handoff; #4 is the *contract trip-wire* — without it, Phase 3 can silently drift the four Protocols and Phase 2's typing guarantee evaporates. Treat the wording of issue #4 with care: name the ADR amendment requirement explicitly. The Step 8 PR review must verify this issue's body before merge.
- **Use one script, one fixture.** `scripts/file_phase3_handoff_issues.py --dry-run` is the canonical source for the issue bodies; the unit tests read the dry-run output. Do not maintain two copies (script + fixture editor) of the issue text — fixture drift is a maintenance bug.
- **`mkdocs build --strict` checks broken links.** If you cite `02-ADR-0006` in the cheat-sheet, use a working relative link to `docs/phases/02-context-gather-layers-b-g/ADRs/0006-...`. Broken-link errors will fail AC-6's `test_mkdocs_build_strict`.
- **`docs/contributing.md` already exists from earlier phases.** Append, do not rewrite. Match existing heading depth + style (likely `##` for top-level sections; check the file's existing conventions per Rule 11).
- **GH Project board reuse.** Phase 0/1 likely already names a `codewizard-sherpa` Project board; the issue-file script should accept it as a CLI arg (`--project codewizard-sherpa`) rather than hard-coding. If no board exists, this story does NOT create one — file the issues to the repo without a project association and surface the gap (Rule 12).
- **Issue labels.** Apply `phase:3`, `handoff:from-phase-2`, plus one of `loader`/`plugin`/`fallback`/`smoke`/`allowlist` for the five primary issues. Backlog issues get `backlog` + the relevant area label (`mypy`, `external-docs`, `skills`).
- **The closing PR for Phase 2.** This story is one of the last to land. The closing PR likely contains S8-04 + the trailing parts of S8-03 (baseline JSON refresh, etc.). Coordinate the PR commit-message with the team's convention (Phase 1 used `feat(phase1/SX-XX)` prefixes per recent git log).
- **Don't unskip `test_phase3_handoff_smoke.py`.** The unskip is Phase 3's first commit on that test — the action **is** the entry-gate review. If a reviewer asks "why don't we just unskip it now?", the answer is ADR-0007 / Implementation risk #8: Phase 2 has zero implementations of the Protocols; unskipping in Phase 2 verifies nothing because there's no concrete adapter to verify against. The test only earns its keep when Phase 3's first plugin lands.
- **Mark `roadmap.md §"Phase 2"` complete in a separate commit on the closing PR**, not in this story. Mechanical, no test coverage.
- **Phase 0 fence stays green:** zero new `src/` imports introduced. Trivially.
