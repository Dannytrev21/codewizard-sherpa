# Validation report — S8-04 (Phase-3 handoff issues + `docs/contributing.md` addendum + Phase 2 README sign-off)

**Story:** [S8-04-phase3-handoff-and-docs.md](../S8-04-phase3-handoff-and-docs.md)
**Date:** 2026-05-18
**Validator:** phase-story-validator (skill v1.x)
**Verdict:** **HARDENED**

## Summary

The story's *intent* — Phase 2 close-out (project-board issues for Phase 3 work, contributor cheat-sheet, exit-criteria sign-off) — is sound and traces to `phase-arch-design.md §"Integration with Phase 3"` + `final-design.md §"What's next"` + ADR-0007. The *prescriptions*, however, contradicted master in nine places and prescribed mechanisms that would silently duplicate existing artifacts. The two-pass critic run produced sixteen findings (eight `block`, six `harden`, two `nit`). Sixteen edits applied. Verdict: **HARDENED**.

The most consequential reframing: this story is no longer "file 5 issues that re-prescribe Phase 3 work" — Phase 3 has 47 designed stories already — it is "file 5 project-board issues that *link to* the canonical Phase 3 story files." The handoff issues are a project-board *mirror* of the stories, not a parallel work surface that would drift.

## Context Brief

**What the story promises (Goal, draft):**
1. File 5 Phase-3 handoff issues + 3 backlog issues via `gh issue create`.
2. Add a new H2 "Adding a Layer B/C/D/E/G probe" to `docs/contributing.md`.
3. Add an exit-criteria checklist to the phase README.
4. Update `test_phase3_handoff_smoke.py`'s skip-reason with the filed issue number.
5. Mark every Step 8 done-criterion `[x]`.

**What the phase's exit criteria demand:**
- Phase 3 handoff issues filed; reference TCCM exercises every Protocol method via mock (`stories/README.md §Exit-criteria coverage`).
- `test_phase3_handoff_smoke.py` (skipped) closes Gap 1 (Adapter Protocol drift); Phase 3 unskips at entry-gate review.

**What the arch + ADRs constrain:**
- ADR-0007: no Plugin Loader in Phase 2; Phase 3 ships it together with first plugin + adapters.
- ADR-0008: no new Phase-2 events; this story trivially honors (zero new structlog events).
- ADR-0006: `IndexFreshness` sum type stable; Phase 3 extension requires amendment.

## Source-of-truth verifications (grep against master)

| Reference in draft | Master surface | Verdict |
|---|---|---|
| "five Phase-3 handoff issues for Phase 3 work" | Phase 3 has 47 designed stories already (`docs/phases/03-vuln-deterministic-recipe/stories/`) including S2-01..S2-04 (loader), S7-01..S7-02 (npm plugin + adapters), S7-03 (universal fallback). | **REDUNDANT WITHOUT LINKAGE** — issues must mirror, not re-prescribe |
| `docs/contributing.md` "currently lacks an 'Adding a Layer B/C/D/E/G probe' section" | `docs/contributing.md:69` — `## Adding a probe` H2 already exists (Phase 0; 7-step recipe with `LanguageDetectionProbe`). | **EXISTING ARTIFACT** — parallel H2 would create two sources of truth |
| `src/codegenie/exec.py` | Path is `src/codegenie/exec/__init__.py` (package, not module). Verified: `ls src/codegenie/exec/__init__.py` exists; `ls src/codegenie/exec.py` errors. | **WRONG PATH** |
| `tests/adv/phase02/test_phase3_handoff_smoke.py` function `test_phase3_handoff_smoke` | Actual function name: `test_phase3_adapter_handoff_smoke` (file is `test_phase3_handoff_smoke.py`). | **WRONG FUNCTION NAME** |
| Existing skip-reason just cites ADR-0007 placeholder; need to add issue number | Existing reason: `"enabled when Phase 3 plugin lands — see docs/phases/02-context-gather-layers-b-g/ADRs/0007-no-plugin-loader-in-phase-2.md and docs/phases/02-context-gather-layers-b-g/High-level-impl.md §Step 7 Phase-3-handoff bullet"` — already substantive + ADR-anchored. | **EXISTING REASON IS DURABLE** — issue # would be less stable |
| Exit-criteria checklist not present anywhere | `stories/README.md §"Exit-criteria coverage"` (line 235) has the complete mapping table for every Phase 2 exit criterion. Phase README (`docs/phases/02-context-gather-layers-b-g/README.md`) does NOT have one. | **DUPLICATION RISK** — adding a second table to phase README drifts |
| "Open implementation questions #2, #4, #5" three items needing backlog | `stories/README.md §"Open implementation questions"` has 8 items; #2, #4, #5 are currently open; #1, #3, #6, #7, #8 are resolved by shipped stories (S1-02, S4-02/S7-02, S3-01, S7-04, S1-11). | **OK** — selection rationale needed inline |
| `ALLOWED_BINARIES` needs `npm`, `jq` extension | `src/codegenie/exec/__init__.py:96-110` — current set is `{git, node, semgrep, syft, grype, gitleaks, scip-typescript, ast-grep, ripgrep, tree-sitter, docker, strace}`. No `npm`, no `jq`. | **OK — AC-5 valid** |
| GH Project board "Phase 0 likely already names" | Not verified; the closing-PR operator must confirm. | **UNVERIFIED PRECONDITION** — script must handle no-board gracefully |
| `phase-arch-design.md §"Integration with Phase 3"` | Verified at line 957 — canonical table of inheritance + implicit guarantees + new artifacts. | **OK — canonical source** |

## Critic reports

### Coverage critic

- [block][AC-1..AC-5,AC-8] Issue idempotency on re-run; script creates 8 duplicates on second invocation. Fix: dedupe-by-title + `gh issue edit` for body changes.
- [block][AC-1..AC-5] Milestone pre-existence not verified; script will fail if missing. Fix: pre-flight `gh api ... /milestones` + create if missing.
- [block][AC-1] Redundancy with shipped Phase 3 stories S2-01..S2-04 (loader); issue should link, not re-prescribe.
- [block][AC-2/3] Redundancy with S7-01/S7-02 (npm plugin) and S7-03 (fallback).
- [block][AC-6] Redundancy with existing `## Adding a probe` H2 in `docs/contributing.md`.
- [block][AC-7] Redundancy with existing `stories/README.md §Exit-criteria coverage` table.
- [block][Files-to-touch] Wrong file path: `src/codegenie/exec.py` → `src/codegenie/exec/__init__.py`.
- [harden][AC-9] Vague verifiability — `#N` placeholder lets AC pass with unfilled issue number.
- [harden][AC-9] Existing skip-reason already names ADR-0007 + High-level-impl.md §Step 7; more durable than GH issue number.
- [harden][AC-8] Cherry-picks 3 of 8 open questions without justification.
- [harden][AC-1..AC-5] No-board edge case not in ACs.
- [harden][TDD step 5] `mkdocs build --strict` subprocess in unit test — slow + side-effectful + duplicates `make docs` CI.
- [harden][AC-10] Cross-story coupling — gates on S8-01..S8-03 completion.
- [harden][AC-2] Fork PR / external contributor auth handling not covered.
- [nit][Goal §2] "the four" vs lists three — off-by-one.
- [nit][References] `final-design.md ~lines 370–382` — citation drift.
- [nit][AC-6] Verify `run_external_cli (B/G) vs run_allowlisted (C)` matches actual code.

### Test-Quality / Consistency / Design-Patterns critic (combined)

- [CO][block][AC-1..AC-5] Redundancy with shipped Phase 3 stories (S2-01..S2-04, S7-01, S7-03).
- [CO][block][AC-8] No-board precondition unverified.
- [CO][harden][Context line 11, AC-2] Probe-count reconciliation (four Protocols vs six probes vs four canonical examples).
- [CO][harden][References line 42] `src/codegenie/exec.py` doesn't exist.
- [CO][harden][AC-6] Existing `## Adding a probe` H2 collision.
- [CO][harden][AC-7 + Goal §3] Exit-criteria duplication.
- [CO][nit][AC-8] Cherry-picked subset.
- [CO][harden][AC-9] Test function name mismatch + skip-reason already substantive.
- [TQ][block][AC-1] Mutation-weak body assertion — empty body containing literal "ADR-0007" passes.
- [TQ][block][RED step 5] `mkdocs build --strict` subprocess slow + side-effectful.
- [TQ][harden][AC-7] Tautological table comparison if both render from same source.
- [DP][harden][GREEN §1] 8 inline dict payloads → `IssueSpec` Pydantic frozen + `Final` tuple registry.
- [DP][harden][Same] Pure data spec / impure `gh` shell split; functional core / imperative shell.
- [DP][nit][AC-5] Structural `frozenset` enforcement is the real guard.

### Researcher report

**Skipped** — no findings tagged `NEEDS RESEARCH`. All hardenings were codebase-grounded (existing sections, existing skip-reasons, existing tables) or convention-rooted (pure/impure split, dedupe-by-title idempotency, BLAKE3 freeze for "no-edit" assertions). No external pattern lookup required.

## Conflict resolution

Priority order: **Consistency > Coverage > Test-Quality > Design-Patterns.**

- **Coverage** wanted to file 5 fresh GH issues. **Consistency** found Phase 3 already has 47 designed stories covering the same work. **Consistency wins** — issues mirror, do not re-prescribe.
- **Coverage** wanted a new H2 in `docs/contributing.md`. **Consistency** found an existing `## Adding a probe` H2. **Consistency wins** — new content is an H3 subsection under the existing H2 (Rule 7 — surface conflict, don't blend).
- **Coverage** wanted a second exit-criteria table in phase README. **Consistency** found the canonical table in `stories/README.md`. **Consistency wins** — phase README POINTS at the canonical table + provides a small G1–G10 sign-off (no duplication).
- **Coverage** wanted AC-9 to update the skip-reason with the filed issue number. **Consistency** found the existing skip-reason is more durable (ADR-anchored, file-path-anchored). **Consistency wins** — AC-9 enforces a BLAKE3 freeze on the file; Phase 3's entry-gate review owns any future edit.
- **Coverage** wanted AC-10 to gate on every Step 8 box (across S8-01..S8-04). **Test-Quality** flagged this as cross-story coupling. **Test-Quality wins partially** — AC-10 split into 10a (this story's boxes, hard assertion) + 10b (other stories' boxes, soft warning).
- **Design-Patterns** proposed `IssueSpec` Pydantic registry + `MilestoneName` newtype. **Rule 2** considered: 8 heterogeneous payloads cross the rule-of-three threshold and the dict-shuffling-drift risk is real. **Adopted.** Pure spec / impure shell split.
- **Test-Quality** flagged `mkdocs build --strict` subprocess in unit test. **Design-Patterns** + **Consistency** agreed (duplicates `make docs` CI). Resolved: unit test greps section presence only; AC-6c manual ritual captures `make docs` exit-0 in `_attempts/S8-04.md`.

## Edits applied to story (before → after)

| Section | Before | After |
|---|---|---|
| Title | "Phase-3 handoff issues + `docs/contributing.md` cheat-sheet + Phase 2 README exit-criteria close" | "Phase-3 handoff issues (project-board mirrors of existing Phase 3 stories) + `docs/contributing.md` Layer B–G addendum + Phase 2 README exit-criteria pointer" — explicit reframing |
| Status | `Ready` | `HARDENED` |
| ADRs honored | 5 ADRs | added ADR-0008 (no new events — trivially honored) |
| Validation notes | absent | 16-item block documenting every change and why |
| Context | "five GitHub issues filed on the Project board" | reframed as project-board mirrors of existing Phase 3 stories; explicit acknowledgment of the 47-story Phase 3 backlog |
| Goal §1 | "File five Phase-3 handoff issues" | "File eight GitHub issues … each handoff issue is a project-board mirror that *links* to the canonical Phase 3 story file(s)" |
| Goal §2 | "new H2 section titled 'Adding a Layer B/C/D/E/G probe'" | "Extend `docs/contributing.md`'s existing `## Adding a probe` section … with a new SUBSECTION `### Adding a Layer B/C/D/E/G probe (Phase 2 additions)`" |
| Goal §3 | "mirror the table from stories/README.md … with `[x]` boxes" | "POINTS at the canonical table … + top-level `[x]` checklist over the high-level Phase 2 goals (G1–G10)" — no duplication |
| AC-1 | "body mentions `ADR-0007` and `ADR-0031`" | structured-payload assertion: all-of `{ADR-0007, ADR-0031, src/codegenie/adapters/protocols.py, four story-file links}`, body `>= 200` chars, three H3 sections |
| AC-1b/c/d (new) | absent | idempotency on re-run; no-board graceful degradation + loud warning; milestone pre-flight (create if missing) |
| AC-2/3 | re-prescribed plugin scope | links to S7-01/S7-02 (npm plugin) and S7-03 (fallback); structured-payload pattern repeats |
| AC-4 | "ADR amendment requirement" generic | five literal phrase assertions including the correct file path AND the correct function name (`test_phase3_adapter_handoff_smoke`) |
| AC-5 | `src/codegenie/exec.py` (wrong) | `src/codegenie/exec/__init__.py` (correct); acknowledges the `frozenset` structural guard |
| AC-6 | new H2 prescription | H3 subsection UNDER existing H2; assertion that existing H2's first 50 lines are byte-identical |
| AC-6b | absent | `mkdocs.yml` nav parse (no subprocess); AC-6c manual `make docs` ritual captured in attempt log |
| AC-7 | "mirror the table" | "POINTS at canonical table" + exactly 10 `[x]` checkboxes (G1–G10) — assert checkbox count == 10 (NOT a full table duplication) |
| AC-8 | three backlog items, no justification | three backlog items WITH inline justification for why #1/#3/#6/#7/#8 are excluded (resolved by shipped stories) |
| AC-9 | "update skip-reason with issue #" | BLAKE3 freeze on `test_phase3_handoff_smoke.py` — DO NOT edit; Phase 3 owns the update |
| AC-10 (split) | "every Step 8 box `[x]`" | AC-10a (three boxes owned by S8-04, hard); AC-10b (other boxes, soft `pytest.warns`) — decouples from S8-01..S8-03 |
| AC-11 (new) | absent | mypy/ruff/fence green; zero new src/ imports |
| Out of scope | 6 items | added: no parallel H2 in contributing.md; no table duplication; no skip-reason edit; no `mkdocs` subprocess from unit test; no GH Project board creation |
| Files to touch — New | 9 files | 12 files: split `scripts/_phase3_handoff_issues.py` (pure registry) + `scripts/file_phase3_handoff_issues.py` (impure shell); separate test files per AC |
| Files to touch — Untouched | 3 items | added: `tests/adv/phase02/test_phase3_handoff_smoke.py` (AC-9 BLAKE3 freeze); `stories/README.md`; `mkdocs.yml`; `src/codegenie/exec/__init__.py` |
| TDD plan | 8 RED tests | 13 RED tests + 9 GREEN steps (one labelled OPERATOR-RUN) + refactor + manual ritual capture |
| Notes for implementer | 8 bullets | 14 bullets covering: issues mirror stories; pure/impure split; idempotency; no-board graceful; open-questions selection rationale; Rule 2 vs `IssueSpec` registry justification |

## Final verdict

**HARDENED.** The Goal is sound (Phase 2 close-out, zero production code) but the original prescriptions would have created several parallel artifacts that drift from the canonical sources — duplicate plugin-loader spec next to S2-01..S2-04, duplicate "Adding a probe" recipe next to the existing one, duplicate exit-criteria table next to `stories/README.md`, brittle "issue # in skip-reason" coupling. The rewritten story is implementable by the executor: the GH issues are project-board mirrors linking to story files (`IssueSpec` typed registry), the cheat-sheet is an H3 subsection under the existing H2, the phase README's exit-criteria section is a pointer not a duplicate, the test file stays unedited (BLAKE3 frozen), and the script is idempotent on re-run with graceful no-board degradation.

A future contributor reading the rewritten story alongside master will find: (a) eight GitHub issues filed (5 handoff + 3 backlog) linking to canonical Phase 3 story files; (b) `docs/contributing.md`'s existing 7-step "Adding a probe" recipe untouched, with a new Phase-2-specific H3 subsection below it; (c) phase README's exit-criteria sign-off pointing at the canonical mapping table (10 G1–G10 checkboxes, not a duplicate of the ~22-row coverage table); (d) `test_phase3_handoff_smoke.py` BLAKE3-frozen — Phase 3 owns any edit; (e) `scripts/_phase3_handoff_issues.py` pure data registry of typed `IssueSpec` + `scripts/file_phase3_handoff_issues.py` impure idempotent shell; (f) zero production-code changes; (g) Phase 0 fence green trivially.
