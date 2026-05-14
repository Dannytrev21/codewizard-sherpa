# Validation report: S5-02 — Project artifacts + contributor docs + Phase 1 handoff

**Validated:** 2026-05-13
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S5-02 is the final story of Phase 0, shipping the handoff state — `.github/` artifacts, `docs/contributing.md`, mkdocs nav update, Phase 0 milestone close + Phase 1 milestone open with 8 issues — that turns the repo from "a CLI that runs" into "a project a Phase 1 contributor can pick up cold." Three parallel critics found 33 findings: 2 blocks (TQ-F3 CODEOWNERS substring match passes a no-owner mutation that silently disables ADR-0002/0007's structural defense; TQ-F7 six ACs were "verified out-of-band" with zero in-repo pinning so the milestone could never be filed and CI could be red on `main` while the PR still passes), 18 hardens (frontmatter parsing, dependabot schema, PR-template checkbox shape, contributing.md four-section content, pyproject.toml ratchet mirror, etc.), and 11 nits. Two NEEDS RESEARCH items (Coverage-F11 CODEOWNERS validator-as-lint-step, Test-Quality-F9 post-merge CI state pinning idiom) both collapsed into the in-repo HANDOFF.md pinning — no Stage 3 research was required.

Edits: rewrote AC-1 through AC-11 (renumbered from 10 ACs to 11, no existing AC numbers removed; AC-7 and AC-8 added) with mutation-resistant verifiability; replaced the four-test TDD plan with eight tests parsing each artifact's intent (frontmatter, schema, owner-token presence, checkbox shape, content markers, single-occurrence nav, ratchet comment, handoff record); updated Green / Refactor / Files-to-touch to match. The goal is unchanged; the implementation surface is now executor-ready and the previously out-of-band invariants are pinned on disk.

## Findings by critic

### Coverage critic

**Severity rollup:** `block: 0 | harden: 9 | nit: 5` (F11 also carries 1 NEEDS RESEARCH sub-question).

- F1 (harden, AC-1): GitHub-UI rendering is unverifiable in CI; URL-200 / screenshot are corroboration not contract. Fix: parse YAML frontmatter (`name`/`about` non-empty).
- F2 (harden, AC-2): dependabot.yml ecosystems aren't pinned by the test; lazy `touch` passes. Fix: `yaml.safe_load` and assert `version`, ecosystems, schedule, PR cap.
- F3 (harden, AC-4): PR template checkbox content under-tested; substring match doesn't verify three actual checkboxes or all six CI job names. Fix: count `^- \[ \] ` lines; assert all six job names + all five contract-frozen paths.
- F4 (harden, AC-5): contributing.md four sections are not individually testable; one-line `TODO` would pass. Fix: assert four H2 headings + coverage-ratchet datapoints + ADR-0007 references.
- F5 (harden, AC-7): Phase 1 milestone is unverifiable from the repo. Fix: pin issue URLs in phase README.
- F6 (harden, AC-8): Phase 0 milestone close has an "or create one" escape hatch; canonical-file ambiguity. Fix: commit to extending the existing phase README.
- F7 (harden, AC-9): "All six CI jobs green on main" has no in-repo verification. Fix: README handoff section pins HEAD SHA + workflow-run URL.
- F8 (harden, new): probe-version-bump convention (Q2) — story claims to resolve in contributing.md but no AC pins it. Fix: explicit AC named in AC-5.
- F9 (harden, new): coverage ratchet schedule should mirror to `pyproject.toml` comment per impl notes; not an AC today. Fix: promote to AC-7.
- F10 (harden, new): `tests/unit/test_project_artifacts.py` itself isn't gated by CODEOWNERS — the regression test for regression defense isn't defended. Fix: add it to AC-3's gated list.
- F11 (nit, AC-3): CODEOWNERS syntax can fail silently if a path glob is malformed. Fix: synthetic PR test or `gh api codeowners/errors`. NEEDS RESEARCH: is the GH API endpoint stable enough for CI?
- F12 (nit, AC-4): PR template should link to ADR-0007 so toggling the contract-frozen box surfaces the resolution policy.
- F13 (nit, AC-6): mkdocs nav position guidance ("after Phases") is in prose but unverified — drop the instruction OR test for it.
- F14 (nit, AC-10): "lint/typecheck/mypy --strict on touched files" — but touched files are mostly Markdown; this AC is redundant with AC-10 (CI green).

### Test-Quality critic

**Severity rollup:** `block: 2 | harden: 5 | nit: 2 | NEEDS RESEARCH: 1`.

- **F1 (harden)** Issue-template tests check only existence; frontmatter intent is unverified. Mutation M5 (a file with just `# TODO`) passes the test but silently fails to render in the GitHub chooser.
- **F2 (harden)** `dependabot.yml` existence-only check ignores schema (AC-2 wholly unverified). Adjacent test `test_ci_workflow.py` already shows the idiomatic YAML-parsing pattern.
- **F3 (BLOCK)** CODEOWNERS substring match passes the no-owner mutation: `src/codegenie/probes/base.py` with no `@user` after it silently disables gating but `path in body` is satisfied. Also a trailing slash on a file path matches the substring but is semantically a directory pattern that won't match. This breaks ADR-0002 and ADR-0007's structural defense while keeping the test green.
- **F4 (harden)** PR-template substring match doesn't constrain checkbox shape; strings inside HTML comments satisfy the test. AC-4 contractually requires actual Markdown task syntax.
- **F5 (harden)** contributing.md content (AC-5 four sections) entirely unverified. Worst single risk: the most-read Phase 1 doc treats body as a blob.
- **F6 (harden)** Coverage-ratchet mirror to `pyproject.toml` is unverified — implementer note promises it but no test enforces.
- **F7 (BLOCK)** Out-of-band ACs (AC-1, AC-3 trailer, AC-7, AC-8, AC-9, AC-10) have zero in-repo pinning. Six ACs admit milestone-not-created / CI-yellow regressions without any failing check. Per CLAUDE.md Rule 12 (Fail loud).
- **F8 (nit)** `mkdocs nav` test tolerates duplicate listings.
- **F9 (NEEDS RESEARCH)** No precedent for asserting external GitHub Actions state from pytest. Resolved: F7's HANDOFF/README pinning is the canonical answer; AC-10 inherits.
- **F10 (positive note)** No mock-of-mock; tests are direct file reads — matches codebase idiom.

### Consistency critic

**Severity rollup:** `block: 0 | harden: 4 | nit: 4`.

- F1 (harden, AC-5): ADR-0006 *Consequences* explicitly says "the 'empty extras are reserved slots' convention has to be documented (Phase 0 `contributing.md`)" — load-bearing commitment routed to S5-02 but missing from ACs.
- F2 (harden, AC-1): impl-outline names the four-step amendment workflow body content but no AC pins it.
- F3 (harden, AC-6/7): milestone + 8 issues + CI green rely entirely on out-of-band verification — no audit evidence on disk.
- F4 (nit, AC-5): manifest says Q2 resolves in contributing.md AND a follow-up issue. AC-5's "Project conventions" bullet list doesn't name probe-version-bump explicitly.
- F5 (harden, AC-4): PR template's contract-frozen checkbox omits `tests/unit/test_pyproject_fence.py` — but AC-3 (CODEOWNERS) gates it per ADR-0002 risk #4. PR template and CODEOWNERS list should match exactly.
- F6 (nit, AC-8): phase README exists; "if absent, create one" hedge invites duplication.
- F7 (nit, Refactor): cross-link between `.github/ISSUE_TEMPLATE/adr-amendment.md` and `templates/adr-amendment.md` (S2-05) is mentioned but not enforced.
- F8 (nit, TDD): test is order-insensitive but Refactor advises positioning.

## Research briefs

None — both NEEDS RESEARCH items (Cov-F11 GH-API CODEOWNERS linter, TQ-F9 post-merge CI state pin) collapsed into the in-repo phase README handoff record (AC-8), which is the consistent solution across all three critics and matches CLAUDE.md Rule 12 (Fail loud).

## Conflict resolutions

- Coverage-F13 (drop nav position guidance) vs. Consistency-F8 (positioning advised in Refactor): Coverage wins on the AC (no positional AC); Consistency's "positioning is editorial" framing kept in the prose. Result: Green-step prose demoted positioning from instruction to suggestion; no AC pins position.
- Coverage-F14 (remove AC-10 as redundant) vs. broader synthesis: tightened rather than removed — renumbered to AC-11 and scoped to "author-side gate, only when `.py` files are touched" so it's not redundant with AC-10's CI assertion.
- Test-Quality-F7 (BLOCK) and Coverage-F5/F6/F7 (harden) and Consistency-F3 (harden) all converged on the same fix: phase README `## Handoff record` with PR URL + HEAD SHA + workflow-run URL + milestone URL + 8 issue URLs. Single AC added (AC-8) addresses all three.

## Edits applied

### Edit 1 — Validation notes block added under header
- Source: editor.md Step 4 protocol
- New block lists every change with the source critic finding ID; preserves a breadcrumb for future readers.

### Edit 2 — AC-1 strengthened (issue templates)
- Source: Coverage F1, Test-Quality F1, Consistency F2 + F7
- Before: "exist and render in the GitHub UI ... screenshot or URL-200 check"
- After: parses YAML frontmatter (`name`/`about` non-empty); `adr-amendment.md` body asserts `ADR-0007`, `localv2.md §4`, `probe_contract.v1.json`, `templates/adr-amendment.md`. GitHub-UI render is corroboration not contract.

### Edit 3 — AC-2 strengthened (dependabot.yml)
- Source: Coverage F2, Test-Quality F2
- After: `yaml.safe_load` + assert `version == 2`, ecosystem set `{pip, github-actions}`, weekly schedule, PR cap 5.

### Edit 4 — AC-3 strengthened (CODEOWNERS) — addresses BLOCK
- Source: Test-Quality F3 (BLOCK), Coverage F10
- After: line-by-line parse; every gated path has ≥ 1 `@owner` token starting with `@`; file paths don't carry trailing slashes; directory pattern does. Added `tests/unit/test_project_artifacts.py` and `.github/CODEOWNERS` to the gated set.

### Edit 5 — AC-4 strengthened (PR template)
- Source: Coverage F3 + F12, Test-Quality F4, Consistency F5
- After: exactly three `^- \[ \] ` anchored-regex checkbox lines; all six CI job names; all five contract-frozen paths (incl. `tests/unit/test_pyproject_fence.py`); `ADR-0007` reference.

### Edit 6 — AC-5 strengthened (contributing.md content)
- Source: Coverage F4 + F8, Test-Quality F5, Consistency F1 + F4
- After: four `^## ` H2 sections; coverage ratchet literals (`85/75`, `87/77`, `90/80`); ADR-0006 four-extras shape (`gather`, `dev`, `service`, `agents` all named) with `[agents]` LLM-SDK rule; ADR-0007 amendment workflow; "Probe version bumps" sub-heading; no residual `TODO(S5-02)`.

### Edit 7 — AC-6 strengthened (mkdocs nav single occurrence)
- Source: Test-Quality F8
- After: `count == 1` enforced; idiomatic `_flatten_nav` walker matching adjacent `test_precommit_and_docs_config.py`.

### Edit 8 — AC-7 added (pyproject.toml ratchet mirror)
- Source: Coverage F9, Test-Quality F6
- New AC: comment within ±5 lines of `--cov-fail-under=85` containing `87/77`, `90/80`, and `contributing.md`.

### Edit 9 — AC-8 added (phase README Handoff record) — addresses BLOCK
- Source: Test-Quality F7 (BLOCK), Coverage F5 + F6 + F7, Consistency F3
- New AC: `## Exit criteria` + `## Handoff record` H2 sections in phase README; pins PR URL, 40-char SHA, workflow-run URL naming both 3.11 and 3.12, milestone URL, exactly 8 issue URLs. The on-disk audit defense for what was previously six out-of-band ACs.

### Edit 10 — AC-9 / AC-10 renumbered + tightened
- Source: Consistency F6
- After: AC-9 (Phase 0 milestone closed; on-disk evidence is AC-8's URLs). AC-10 (six CI jobs green; on-disk evidence is AC-8's workflow-run URL). Hedge dropped — phase README exists.

### Edit 11 — AC-11 (was AC-10) tightened
- Source: Coverage F14
- After: scoped to "if `.py` files touched, ruff/mypy/pytest pass locally" — author discipline gate, distinct from AC-10's CI gate.

### Edit 12 — TDD plan rewritten
- Source: Test-Quality F1–F7
- After: eight tests, each pinning one AC's intent (frontmatter parse, dependabot schema, CODEOWNERS rule-shape, PR-template checkbox count + content, contributing.md sections + content, nav single-occurrence, pyproject ratchet mirror, README handoff regex set). Anchored regex on PR-template checkboxes defeats HTML-comment evasion.

### Edit 13 — Green / Refactor / Files-to-touch synced
- Source: synthesis
- After: Green section names every artifact mapped to its AC; Refactor enforces `templates/adr-amendment.md` cross-link and post-merge-SHA discipline for the Handoff record; Files-to-touch reflects the renamed scope of `contributing.md` (modify the S1-04 stub, not create), the new `pyproject.toml` edit (ratchet comment), and the expanded test scope (8 tests, not 4).

## Verdict rationale

The story's goal and scope were sound; the failure mode was under-specified ACs and a TDD plan that pinned file existence without pinning intent. Both blocks were fixable in place (CODEOWNERS owner-token parsing; phase README handoff pin). No goal-vs-arch contradiction, no Phase Non-goals violation, no ADR contradiction. The story now has 11 ACs each individually verifiable, the TDD plan now has 8 tests with mutation-resistant assertions, and the previously out-of-band invariants (GitHub UI render, milestone closure, CI green on `main`) are pinned on disk via the phase README's `## Handoff record` — which is itself unit-tested.

## Recommended next step

`phase-story-executor` to implement S5-02 against the hardened ACs and TDD plan. The story is ready.
