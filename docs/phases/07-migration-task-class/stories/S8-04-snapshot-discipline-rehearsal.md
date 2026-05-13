# Story S8-04 — Snapshot-discipline rehearsals A + B + final PR checklist

**Step:** Step 8 — Pre-flight final regression and snapshot-discipline rehearsal
**Status:** Ready
**Effort:** S
**Depends on:** S8-03
**ADRs honored:** ADR-P7-001, ADR-0009

## Context

The single load-bearing claim of Phase 7 — proven mechanically rather than by convention — is that the contract-surface snapshot canary (S1-07) plus the `snapshot_regen_audit.py` gate (S1-08) catch every drift outside the six ADR-gated additive seams. S1-07 and S1-08 unit-tested the *mechanism*. This story rehearses the *workflow* end-to-end against the real CI lane via two rehearsal PRs:

- **Rehearsal A** — a no-op edit to a Phase 0–6 source file that is *not* one of the six seams. Expected outcome: `tests/integration/test_contract_surface_snapshot.py` (if the edit touches the contract surface) **or** `snapshot_regen_audit.py` (if the snapshot is also regenerated without an ADR) fires and the PR is blocked.
- **Rehearsal B** — a legitimate additive snapshot regeneration with a matching ADR linked in the same PR. Expected outcome: both the canary and the audit accept the PR.

These are **real PRs against the real CI lane**, not unit tests of `snapshot_regen_audit.py`. The point is to validate that the discipline survives a real-world operator workflow, not just an isolated test harness. The final acceptance is that Phase 7's own merge PR description links every ADR-P7-001..007 and the ADR-0028 amendment — the audit trail any reviewer (or any future phase 8 author) needs to verify the discipline propagates.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component 10` — the snapshot canary's failure-mode behavior and the "Phase 7 PR is the first PR that intentionally regenerates the snapshot" claim that this story rehearses.
  - `../phase-arch-design.md §Gap 5` — the canonical motivation for `snapshot_regen_audit.py` as the mechanical enforcement of the ADR-or-revert discipline.
  - `../phase-arch-design.md §Scenarios ›Scenario 4: Cross-task regression — the contract-surface snapshot fires on an inadvertent Phase 6 edit (test path)` — the exact failure trajectory Rehearsal A simulates.
  - `../phase-arch-design.md §Path to production end state` — the ADR-0028 amendment that this story's final-PR checklist must link.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0001-six-named-additive-seams-and-adr-0028-amendment.md` — ADR-P7-001 — the six-seam discipline this story rehearses.
  - `../ADRs/0009-contract-surface-snapshot-canary.md` — ADR-0009 — the snapshot canary mechanism; rehearsal B exercises its `--update-contract-snapshot` workflow.
  - `../ADRs/0002-..-0008-..*.md` — ADR-P7-001..007 — the per-phase ADRs the final PR description must link.
- **Production ADRs:**
  - `../../../production/adrs/0028-task-class-introduction-order.md` (amended in S1-06) — the production amendment the final PR description must link.
- **Existing code:**
  - `tools/contract-surface.snapshot.json` (from S1-07) — the artifact rehearsal B intentionally regenerates.
  - `tools/snapshot_regen_audit.py` (from S1-08) — the audit tool both rehearsals exercise.
  - `tests/integration/test_contract_surface_snapshot.py` (from S1-07) — the test rehearsal A trips and rehearsal B updates.
  - `.github/workflows/` — where the `snapshot_regen_audit` job runs.
- **External docs:**
  - None — the workflow is fully internal to this repo.

## Goal

Two rehearsal PRs land — Rehearsal A is rejected by CI as expected, Rehearsal B is accepted — and Phase 7's final merge PR description links every ADR-P7-001..007 ADR file plus the ADR-0028 amendment.

## Acceptance criteria

- [ ] **Rehearsal A** is opened as a real PR (against `master` or against the Phase 7 integration branch — match repo convention). It contains exactly one no-op edit to a Phase 0–6 source file that is *not* in the six-seam allowlist (e.g., a comment tweak to `src/codegenie/probes/coordinator.py` — Phase 2's coordinator, byte-frozen per ADR-P7-001).
- [ ] Rehearsal A's CI run is **red**: either the contract-surface snapshot test fails because the edit shifted a tracked surface, or — if the edit doesn't touch a tracked surface — `snapshot_regen_audit.py` fails because the edit *does* touch Phase 0–6 source without an accompanying ADR (or the configured fence-CI fires on a non-allowed edit). The PR description records which gate fired and is linked from this story's PR.
- [ ] **Rehearsal B** is opened as a real PR with three artifacts in the same commit: (a) a new minimal Pydantic field on some Phase 7-owned model that flows through `compute_snapshot()`, (b) the regenerated `tools/contract-surface.snapshot.json` (from `pytest --update-contract-snapshot`), (c) a one-line ADR amendment to one of the Phase 7 ADRs (or a new throwaway `docs/phases/07-migration-task-class/ADRs/9999-rehearsal-b.md` that the team agrees to revert after the rehearsal).
- [ ] Rehearsal B's CI run is **green**: the snapshot test passes against the regenerated snapshot, `snapshot_regen_audit.py` finds the ADR-NNNN reference in the PR body and matches it to the ADR file modified in the same PR.
- [ ] Both rehearsal PRs are linked from this story's PR description (URLs to the rejected and accepted CI runs).
- [ ] Phase 7's **final merge PR description** explicitly links every ADR-P7-001..007 file path under `docs/phases/07-migration-task-class/ADRs/` and the production ADR-0028 amendment file path. A checklist in the PR description confirms each link.
- [ ] Rehearsal B is reverted (or, if it landed on an integration branch only, deleted) before Phase 7's final merge — so the noise commit does not pollute master.
- [ ] The TDD plan's "red rehearsal" exists as a real PR with a failing CI link captured; this counts as the story's red marker.

## Implementation outline

1. Identify the rehearsal target files. Read `phase-arch-design.md §Component 13` to confirm exactly which Phase 0–6 files are *not* in the six-seam allowlist — these are the safe targets for Rehearsal A. Choose one that's unambiguously outside the allowlist (e.g., `src/codegenie/probes/coordinator.py` or a Phase 6 graph node).
2. Pre-write the two rehearsal commit messages following the repo's PR template (so the audit tool's body-regex scrape behaves as it would for a real PR).
3. **Rehearsal A:** open a branch from current Phase 7 integration HEAD, make one no-op edit (comment or whitespace if the contract surface is byte-stable to whitespace; otherwise a single-character edit to a docstring of a tracked Pydantic field — the snapshot canary tracks `model_json_schema()` which includes descriptions). Push, open PR, wait for CI, screenshot or link the red result.
4. **Rehearsal B:** open a second branch from current HEAD. Add a minimal new optional Pydantic field to `MigrationReport` (or another Phase 7-owned model). Run `pytest --update-contract-snapshot tests/integration/test_contract_surface_snapshot.py` and stage the snapshot diff. Add a one-line entry to one of the Phase 7 ADRs' Consequences section noting the field. Commit and push as one commit. Confirm CI green.
5. Capture both CI run URLs.
6. Update Phase 7's final-merge PR description with the checklist of all ADR-P7-001..007 links and the ADR-0028 amendment link.
7. Revert Rehearsal B (and Rehearsal A's no-op edit if not already discarded) before final merge.

## TDD plan — red / green / refactor

This story doesn't ship runtime code; the TDD shape is "rehearsal as red, accepted-rehearsal as green."

### Red — write the failing test first

The red phase **is** Rehearsal A. Open a PR that intentionally violates the snapshot-discipline contract; confirm CI fails for the right reason; capture the CI URL.

Equivalent in pseudo-code (this is the rehearsal narrative, not source code to commit):

```text
# rehearsal-a/branch
$ git checkout -b rehearsal-a-no-op-phase2-edit
$ # edit `src/codegenie/probes/coordinator.py` — change a docstring word
$ git commit -am "rehearsal A: no-op edit to Phase 2 coordinator (expected to fail)"
$ gh pr create --title "[REHEARSAL A] no-op edit; expect rejection" --body "Tests S8-04 discipline."
# CI runs:
#   - test_contract_surface_snapshot.py: pass (docstrings on internal functions
#     don't flow through model_json_schema)
#   - snapshot_regen_audit.py: not triggered (snapshot not changed)
#   - BUT: the body lacks any ADR-NNNN reference AND the PR touches a frozen
#     Phase 2 file outside the six-seam allowlist. If the audit tool's scope
#     covers Phase 0–6 edits (not just snapshot edits), it fails here.
#   - If the audit only covers snapshot edits, then Rehearsal A must trip
#     the test_contract_surface_snapshot.py canary by editing a *tracked* surface
#     (e.g., a Pydantic field description). Adjust the edit until red CI is real.
# Expected end state: CI red, PR un-mergeable, URL captured.
```

The valid red outcomes are:
1. `test_contract_surface_snapshot.py` fails on the diff.
2. `snapshot_regen_audit.py` fails for lack of ADR-NNNN in body when the PR touches the snapshot.
3. Fence-CI fails on a forbidden edit pattern.

Any of the three counts as red. If *none* fire, then the discipline has a hole and the rehearsal has just discovered it — surface it as a Phase 7 blocker rather than papering over.

### Green — make it pass

The green phase **is** Rehearsal B. Open a PR that does the right things in lockstep — new optional field, snapshot regen, ADR amendment — and confirm CI accepts it.

Pseudo-narrative:

```text
# rehearsal-b/branch
$ git checkout -b rehearsal-b-legit-additive-regen
$ # 1. Add `notes: str | None = None` to MigrationReport in src/codegenie/graph/state_distroless.py
$ # 2. Regenerate the snapshot:
$ pytest --update-contract-snapshot tests/integration/test_contract_surface_snapshot.py
$ # 3. Add a Consequences-section line to docs/phases/07-migration-task-class/ADRs/0011-*.md
$ #    referencing ADR-P7-008 (or whatever the next free ADR ID is) for the rehearsal.
$ git commit -am "rehearsal B: additive MigrationReport.notes; ADR-P7-008 linked"
$ gh pr create --title "[REHEARSAL B] legit additive regen; expect acceptance" \
$   --body "Tests S8-04 discipline. ADR-P7-008 linked in this PR's diff."
# Expected: CI green; snapshot_regen_audit.py finds ADR-P7-008 in body AND in the diff.
```

### Refactor — clean up

After both rehearsals capture their CI URLs:
- Revert Rehearsal B (the new field, the ADR amendment, the snapshot regen) so master is not polluted.
- Update this story's PR description (and Phase 7's final-merge PR description) with the rehearsal CI URLs.
- Confirm the final-merge PR description checklist references each ADR-P7-001..007 file path under `docs/phases/07-migration-task-class/ADRs/` and the production ADR-0028 amendment file path.
- If the team practice is to keep rehearsal branches as documentation, label them `rehearsal/` and don't merge — just keep the CI runs alive.

## Files to touch

| Path | Why |
|---|---|
| `docs/phases/07-migration-task-class/stories/S8-04-snapshot-discipline-rehearsal.md` | This story's PR description + Status update — links to Rehearsal A red CI URL and Rehearsal B green CI URL. |
| Phase 7's final-merge PR description (not a file in the repo) | Checklist of ADR-P7-001..007 + ADR-0028 amendment links. |
| (transient on rehearsal branches; reverted before merge) `src/codegenie/probes/coordinator.py` | Rehearsal A no-op edit; revert. |
| (transient on rehearsal branches; reverted before merge) `src/codegenie/graph/state_distroless.py`, `tools/contract-surface.snapshot.json`, one Phase 7 ADR file | Rehearsal B legitimate additive change + snapshot regen + ADR amendment; revert before final merge. |

## Out of scope

- **Editing or extending `snapshot_regen_audit.py`.** S1-08 owns the tool. If a rehearsal discovers a gap in the tool's logic, file a Phase 7.1 follow-up — do not patch the tool in this story.
- **Editing the contract-surface canary test.** S1-07 owns `tests/integration/test_contract_surface_snapshot.py`. If a rehearsal shows the canary missing a tracked surface, file a follow-up.
- **Adding new ADRs.** ADR-P7-001..007 are landed by S1-06. This story consumes them; it does not author new ones (other than the throwaway in Rehearsal B, which is reverted).
- **Operator notes documentation.** `phase-arch-design.md §High-level-impl Step 8` mentions `docs/phases/07-migration-task-class/operator-notes.md` as *optional* — defer to Phase 11 if the repo convention is no operator docs at this phase.
- **Bumping `gate.shell_trace.budget_s`.** Operator-facing tunable; documented but not touched here.

## Notes for the implementer

- The rehearsals are the *whole story*. Do not collapse them into unit tests of `snapshot_regen_audit.py` — those already exist (S1-08). The point is to validate the workflow end-to-end against the real CI, not the tool in isolation.
- Per CLAUDE.md Rule 12 (Fail loud): if Rehearsal A passes CI green, the discipline has a hole. Stop, surface it loudly, and either tighten the audit tool's scope (S1-08 follow-up) or pick a different rehearsal target until the failure is real and for the right reason.
- The audit tool scans for `ADR-(P\d+-\d+|0\d+)` in the PR body. Rehearsal B's body must contain a real match such as `ADR-P7-008` (or whichever ID you chose), and that ADR file must be in the PR's file diff — both conditions, not just one.
- The "no-op edit" in Rehearsal A is subtle: a literal whitespace change may not trigger the snapshot test (which canonicalizes), and may not trigger the audit (which only runs on snapshot diffs). You may need to deliberately touch a *tracked* surface (e.g., a docstring on a Pydantic field, which flows through `model_json_schema()`). Iterate locally until the red is real and for the right reason; document the chosen target in the rehearsal PR body.
- The throwaway ADR for Rehearsal B (`9999-rehearsal-b.md`) should be obviously labeled in its title so reviewers know it's not a real decision. Better: amend an *existing* ADR's Consequences section with a one-line "Rehearsal B link" entry, then revert that line in the cleanup commit — less filesystem churn.
- Per `phase-arch-design.md §Path to production end state`, the ADR-0028 amendment is the *production-side* of the Phase 7 discipline. The final-merge PR description must link both the per-phase ADR files (under `docs/phases/07-migration-task-class/ADRs/`) and the production amendment (under `docs/production/adrs/0028-*.md`). Two namespaces, both required.
- If `gh pr create` is not the repo's PR-opening workflow (e.g., the team uses Buildkite + a forge other than GitHub), adapt — but keep the round-trip: open PR → wait for CI → capture URL. Local-only verification does not satisfy this story's acceptance criteria.
- Revert order matters: clean up Rehearsal B (which has more pieces) before Rehearsal A, so the final merge diff is exactly the intended Phase 7 surface and nothing else.
