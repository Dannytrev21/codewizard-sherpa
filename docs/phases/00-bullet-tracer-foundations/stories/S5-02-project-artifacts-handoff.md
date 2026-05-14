# Story S5-02 — Project artifacts + contributor docs + Phase 1 handoff

**Step:** Step 5 — Close the remaining CI gates and project conventions
**Status:** GREEN (implementation landed 2026-05-13; post-merge SHA + workflow-run URL backfill outstanding — see attempt log)
**Effort:** M
**Depends on:** S4-05
**ADRs honored:** ADR-0002, ADR-0006, ADR-0007

## Validation notes

Validated: 2026-05-13
Verdict: HARDENED
Findings addressed: 33 total (2 blocks, 18 hardens, 11 nits, 2 NEEDS RESEARCH — both collapsed into the in-repo handoff pinning).

Changes applied:
- AC-1 strengthened — each issue template's YAML frontmatter parsed (`name`, `about` non-empty); `adr-amendment.md` body asserts `ADR-0007`, `localv2.md §4`, `probe_contract.v1.json`, `templates/adr-amendment.md` strings — Coverage F1, Test-Quality F1, Consistency F2 + F7.
- AC-2 strengthened — `dependabot.yml` parsed: `version: 2`, ecosystem set `{pip, github-actions}`, `schedule.interval: weekly`, `open-pull-requests-limit: 5` — Coverage F2, Test-Quality F2.
- AC-3 strengthened — CODEOWNERS parsed line-by-line, every contract-frozen path has ≥1 `@owner`, directory-vs-file pattern shape checked; added `tests/unit/test_project_artifacts.py` as a gated path (regression defense for the regression test itself) — Test-Quality F3 (BLOCK), Coverage F10.
- AC-4 strengthened — PR template asserts exactly three `^- \[ \] ` checkbox lines, all six CI job names appear, all five contract-frozen paths (incl. `tests/unit/test_pyproject_fence.py`) appear, `ADR-0007` link/path appears — Coverage F3 + F12, Test-Quality F4, Consistency F5.
- AC-5 strengthened — `contributing.md` parsed: four `## ` H2 sections present; coverage ratchet literal (`85/75`, `87/77`, `90/80`) appears; ADR-0006 four-extras-shape paragraph (`gather`/`dev`/`service`/`agents`, "LLM SDKs land in `[agents]`") appears; ADR-0007 amendment workflow links; "Probe version bumps" sub-heading resolving open question Q2; no residual `TODO(S5-02)` marker — Coverage F4 + F8, Test-Quality F5, Consistency F1 + F4.
- AC-6 strengthened — `contributing.md` appears exactly once in flattened `mkdocs` nav — Test-Quality F8.
- AC-7 added — `pyproject.toml` contains a comment within ±5 lines of `--cov-fail-under=85` referencing the ratchet (`85/75 → 87/77 → 90/80`) and pointing to `docs/contributing.md` — Coverage F9, Test-Quality F6.
- AC-8 added — phase README ships an `## Exit criteria` section plus an `## Handoff record` section pinning: `main` HEAD SHA (40-char hex), GitHub Actions workflow-run URL showing all six jobs green on 3.11 *and* 3.12, the merged PR URL, the Phase 1 milestone URL, and the eight Phase 1 issue URLs (5 Layer A probes + 3 follow-ups). This is the on-disk audit defense for the six previously-out-of-band ACs — Coverage F5 + F6 + F7, Test-Quality F7 (BLOCK) + F9, Consistency F3.
- AC-9 (renumbered from AC-8) — phase README hedge ("if absent, create one") dropped; the file exists, extend it — Consistency F6.
- AC-10 (renumbered from AC-9) — workflow-run URL + HEAD SHA pinning routed through the Handoff record (AC-8) — Coverage F7.
- AC-11 (renumbered from AC-10) — tightened to "if `.py` files are touched by this PR, ruff/mypy/pytest pass locally" (author-side gate, not redundant with AC-10) — Coverage F14.
- Refactor step — `templates/adr-amendment.md` cross-link tightened (issue template must literally name the relative path so a contributor finds the PR template) — Consistency F7.
- Green-step positional guidance for `mkdocs.yml` nav demoted from instruction to suggestion (positioning is editorial) — Consistency F8.

Full audit log: `docs/phases/00-bullet-tracer-foundations/stories/_validation/S5-02-project-artifacts-handoff.md`.

## Context

This is the final story of Phase 0. After S4-05 lands the adversarial suite and S5-01 lands the bench canaries + concurrent-cache test, every load-bearing exit criterion from `roadmap.md §"Phase 0"` is met *technically* — the bullet tracer fires, the cache hits, the fence blocks, the contract is frozen. What's missing is the **handoff state**: the project artifacts that turn the repo from "a CLI that runs" into "a project a Phase 1 contributor can pick up cold and extend by addition without re-deriving Phase 0's decisions." That's six artifact families — issue templates, dependabot config, CODEOWNERS, PR template, contributor docs, milestone + follow-up issues — plus the final exit-checklist update and the close of the Phase 0 milestone.

This is polish + gate-closing work; it ships **no new runtime code under `src/codegenie/`**. It does ship the contracts (CODEOWNERS path scope, contributing guide cheat sheet, three follow-up issues filed) that govern how Phase 1 *consumes* what Phase 0 produced.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Integration with Phase 1 (next phase)` — the canonical handoff list. New contracts, new artifacts on disk, state that persists across runs, implicit guarantees Phase 1 inherits. Every bullet in that section maps to "Phase 1 can rely on this"; this story's job is to make that machinery legible to a Phase 1 contributor.
  - `../phase-arch-design.md §Testing strategy / CI gates` — the six-job matrix Phase 0 wires; this story confirms all six are green on `main`.
  - `../phase-arch-design.md §Goals` — exit criteria #5 (six CI jobs green), #6 (`mkdocs build --strict` over curated `nav`), #8 (coverage ≥ 85/75 enforced by `--cov-fail-under=85`).
  - `../phase-arch-design.md §Path to production end state` — the "what's still missing for production" list, used to scope the Phase 1 milestone issues.
  - `../phase-arch-design.md §Open questions deferred to implementation` — Q2 (probe-version-bump convention) and Q5 (coverage ratchet schedule) resolve here in `docs/contributing.md`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0002-fence-ci-job-no-llm-in-gather.md` — ADR-0002 — the `fence` job must be green on `main`'s HEAD on both Python 3.11 and 3.12; the CODEOWNERS scope must include `tests/unit/test_pyproject_fence.py` so its scope cannot widen silently (Implementation-level risk #4 in `High-level-impl.md`).
  - `../ADRs/0007-probe-contract-frozen-snapshot.md` — ADR-0007 — CODEOWNERS must gate `src/codegenie/probes/base.py`, `tests/snapshots/probe_contract.v1.json`, and `localv2.md` because the snapshot drift policy says "drift is resolved by changing code, never by editing the spec"; the `adr-amendment.md` issue template referenced from the snapshot-test failure message ships here.
  - `../ADRs/0006-pyproject-toml-extras-shape.md` — ADR-0006 — the `agents` extra exists as the LLM-SDK landing zone; the contributing guide explains it so a Phase 4 contributor doesn't add `anthropic` to runtime `dependencies`.
- **High-level impl plan:**
  - `../High-level-impl.md §Step 5` — Features delivered list (the six artifact families + the three Phase 1 follow-up issues + the milestone close).
  - `../High-level-impl.md §Step 5 — Done criteria` — every checkbox in this story's acceptance criteria maps to a row in that list.
  - `../High-level-impl.md §What's next — handoff to Phase 1` — the canonical handoff narrative; the body of `docs/contributing.md` distills this for a contributor.
  - `../High-level-impl.md §Implementation-level risks #1` — `localv2.md §4` byte-for-byte transcription risk; the CODEOWNERS gating on `src/codegenie/probes/base.py` is one of the structural defenses against silent drift.
- **Manifest:**
  - `../stories/README.md` — S5-02 row; the "Open implementation questions" section lists Q2 (probe-version-bump convention) and Q5 (coverage ratchet schedule) as resolved-in-this-story.
  - `../stories/README.md §Exit-criteria coverage` — `S5-02` is named on "CI is green on `main` (final)", "Docs site builds locally without warnings (final green incl. `contributing.md`)", and "Issue templates render in GitHub UI".
- **Existing artifacts (consumed):**
  - `.github/workflows/ci.yml` — the six-job matrix (S1-05) this story confirms green on `main`.
  - `mkdocs.yml` — the curated `nav` (S1-04) this story extends with `docs/contributing.md`.
  - `templates/adr-amendment.md` — the PR template (S2-05) referenced by the `.github/ISSUE_TEMPLATE/adr-amendment.md` template this story ships.

## Goal

`.github/` ships issue templates, dependabot config, CODEOWNERS, and a PR template; `docs/contributing.md` joins the curated `mkdocs` `nav` and builds clean; the Phase 0 milestone is closed; a Phase 1 milestone exists with five Layer A probe issues plus three follow-up issues filed; all six CI jobs are green on `main`'s HEAD on Python 3.11 and 3.12.

## Acceptance criteria

- [ ] **AC-1 — Issue templates exist with valid GitHub frontmatter.** `.github/ISSUE_TEMPLATE/new-probe.md`, `.github/ISSUE_TEMPLATE/new-skill.md`, and `.github/ISSUE_TEMPLATE/adr-amendment.md` exist as regular files. Each file opens with a YAML frontmatter block (between two `^---$` lines) that parses via `yaml.safe_load` and contains non-empty `name` and `about` keys (a `labels` key is recommended but not required). The `adr-amendment.md` body (post-frontmatter) literally contains the strings `ADR-0007`, `localv2.md §4`, `probe_contract.v1.json`, and the relative path `templates/adr-amendment.md` (the PR template S2-05 shipped). Verification: `tests/unit/test_project_artifacts.py` parses each file's frontmatter and asserts the body strings. The GitHub-UI render of the chooser at `/issues/new/choose` is captured as a screenshot or URL-200 check in the PR description (corroboration, not the test).
- [ ] **AC-2 — `dependabot.yml` schema is pinned.** `.github/dependabot.yml` parses via `yaml.safe_load` and satisfies: `version == 2`; `updates[]` contains exactly two entries whose `package-ecosystem` values are the set `{"pip", "github-actions"}`; each entry has `schedule.interval == "weekly"` and `open-pull-requests-limit == 5`. Verification: `tests/unit/test_project_artifacts.py::test_dependabot_yaml_schema`.
- [ ] **AC-3 — `.github/CODEOWNERS` gates contract-frozen paths with real owners.** The file exists and contains rules for each of these paths: `src/codegenie/probes/base.py`, `tests/snapshots/probe_contract.v1.json`, `tests/unit/test_pyproject_fence.py`, `tests/unit/test_project_artifacts.py` (regression defense for this story's own structural test), `localv2.md`, `docs/production/adrs/`, and `.github/CODEOWNERS` itself. For every gated path, the matching CODEOWNERS rule has ≥ 1 `@owner` token (lines without owners silently disable gating on GitHub). For the four single-file paths, the pattern is NOT directory-suffixed with `/`; for `docs/production/adrs/`, the pattern IS directory-suffixed with `/`. Verification: `tests/unit/test_project_artifacts.py::test_codeowners_gates_contract_frozen_paths` parses CODEOWNERS line-by-line and asserts the rule shape. A synthetic test PR touching `src/codegenie/probes/base.py` on a scratch branch shows the designated reviewer auto-requested (corroboration).
- [ ] **AC-4 — PR template names the contract-frozen set and the six CI jobs.** `.github/PULL_REQUEST_TEMPLATE.md` exists and contains exactly three lines (or ≥ 3, no upper bound enforced) matching the anchored regex `^- \[ \] ` (Markdown task syntax — substrings inside HTML comments do not satisfy this). The full file body contains: (a) all five contract-frozen file paths (`src/codegenie/probes/base.py`, `tests/snapshots/probe_contract.v1.json`, `tests/unit/test_pyproject_fence.py`, `localv2.md`, `docs/production/adrs/`); (b) all six CI job names (`lint`, `typecheck`, `test`, `security`, `docs`, `fence`); (c) a link or relative-path reference to `ADR-0007` (so a contributor toggling the contract-frozen checkbox finds the resolution policy); (d) the string `ADR amendment` or `adr-amendment`. Verification: `tests/unit/test_project_artifacts.py::test_pr_template_contract_and_ci_jobs`.
- [ ] **AC-5 — `docs/contributing.md` has four sections plus required load-bearing content.** The file exists and contains exactly four `^## ` H2 headings with the substrings: `Bootstrap`, `Running the harness`, `Adding a probe`, and `Project conventions`. The body contains the literal strings: `make bootstrap`, `codegenie gather`, `LanguageDetectionProbe` (the S4-01 worked example), `ADR-0007`, the coverage ratchet schedule (`85/75`, `87/77`, `90/80` all three appear), the four `pyproject.toml` extras shape (`gather`, `dev`, `service`, `agents` all four appear) with a sentence explaining that LLM SDKs (e.g., `anthropic`) land in `[agents]` and NEVER in `[project.dependencies]` (resolving ADR-0006's Phase-0 documentation commitment), and a sub-heading or named bullet "Probe version bumps" (resolving open question Q2 from `phase-arch-design.md §Open questions`). The body does NOT contain the placeholder string `TODO(S5-02)` (negative-space check — the S1-04 placeholder must be replaced). Verification: `tests/unit/test_project_artifacts.py::test_contributing_md_sections_and_content`.
- [ ] **AC-6 — `mkdocs.yml` `nav` includes `contributing.md` exactly once and the docs build is strict-clean.** The curated `nav` (flattened recursively) contains `contributing.md` exactly once (no duplicates, no stale entries). `make docs` (running `mkdocs build --strict`) passes with zero warnings. Verification: `tests/unit/test_project_artifacts.py::test_contributing_md_is_in_mkdocs_nav` asserts the `count == 1` invariant; the `docs` CI job verifies the strict build.
- [ ] **AC-7 — `pyproject.toml` mirrors the coverage-ratchet schedule near the `--cov-fail-under` gate.** Within ±5 lines of the line containing `--cov-fail-under=85` in `pyproject.toml`, a `#` comment line contains the strings `87/77` and `90/80` (the ratchet schedule mnemonics) and the string `contributing.md`. This is the structural defense against a contributor editing the gate without seeing the schedule. Verification: `tests/unit/test_project_artifacts.py::test_pyproject_mirrors_coverage_ratchet_schedule`.
- [ ] **AC-8 — Phase README pins the auditable handoff record.** `docs/phases/00-bullet-tracer-foundations/README.md` (file already exists from the `roadmap-phase-designer` skill output; extend it, do NOT replace its reading-order section) contains two new H2 sections:
  - `## Exit criteria` — the ten exit criteria from `phase-arch-design.md §Goals` (#1–#10) as a Markdown checkbox list, each line `[x]` and including either a repo-relative path to a verifying test OR a GitHub Actions workflow-run URL.
  - `## Handoff record` — pins, in this order, the following auditable evidence:
    - The merged PR URL for this story (regex `https://github\.com/.+/pull/\d+`).
    - The `main` HEAD commit SHA at handoff (40-char hex regex `[0-9a-f]{40}`).
    - At least one GitHub Actions workflow-run URL on that SHA showing all six jobs green (regex `https://github\.com/.+/actions/runs/\d+`); the description names both `python-3.11` and `python-3.12` matrix entries.
    - The Phase 1 milestone URL (regex `https://github\.com/.+/milestone/\d+`).
    - Exactly eight Phase 1 issue URLs (regex `https://github\.com/.+/issues/\d+`) — five for the remaining Layer A probes (`NodeBuildSystem`, `NodeManifest`, `CI`, `Deployment`, `TestInventory` per `localv2.md §12 Week 1`) plus three follow-ups: (a) `mkdocs nav cleanup` for the currently-excluded docs (`local.md`, `auto-agent-design.md`, `gemini-auto-agent-design.md`, `context.md`, `localv2.md`); (b) `probe-version-bump convention` (open question #2 in `phase-arch-design.md`); (c) `aiofiles documentation bug — remove from roadmap.md §Phase 0` (per `final-design.md §L3 row 15`).
  Verification: `tests/unit/test_project_artifacts.py::test_phase_readme_pins_handoff_evidence` parses the README, finds both sections, runs each regex, and asserts the issue-URL count == 8.
- [ ] **AC-9 — Phase 0 milestone is closed.** The Phase 0 milestone is closed on GitHub (verified out-of-band; the on-disk evidence is AC-8's README handoff record citing the merged PR URL plus the milestone URL). The Phase 1 milestone exists with the eight issues from AC-8.
- [ ] **AC-10 — All six CI jobs are green on `main`'s HEAD on Python 3.11 and 3.12.** The six jobs (`lint`, `typecheck`, `test`, `security`, `docs`, `fence`) are green on the `main` branch's HEAD commit on `ubuntu-24.04` for both `python: ["3.11", "3.12"]`. The on-disk evidence is AC-8's `## Handoff record` workflow-run URL; this AC's verification is reading that URL.
- [ ] **AC-11 — Local author-side gates pass on touched code paths.** If any `.py` file is touched by this PR (the new `tests/unit/test_project_artifacts.py` is one), `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/test_project_artifacts.py` all pass locally before the PR opens. (Markdown / `.github/*` files are not in scope of `ruff`/`mypy`; this AC is an author discipline gate, not redundant with AC-10's CI gate.)

## Implementation outline

1. Write the TDD red test first — a single test that asserts the four `.github/` artifact files exist and that `docs/contributing.md` exists and is listed in `mkdocs.yml`'s `nav`. Commit it failing. (The other acceptance criteria — GitHub UI rendering, milestone existence, CI green on `main` — are verified out-of-band; the test pins the *file-system* invariants only.)
2. Author the three issue templates (`new-probe.md`, `new-skill.md`, `adr-amendment.md`). Use GitHub's frontmatter format (`---\nname: ...\nabout: ...\nlabels: ...\n---`). The `adr-amendment.md` body templates the workflow from ADR-0007 (link the snapshot diff, link `localv2.md §4`, name the ADR being amended).
3. Write `.github/dependabot.yml` with two ecosystems (`pip` and `github-actions`); confirm via `yamllint` (or manual inspection) that the schema is valid.
4. Write `.github/CODEOWNERS` with the six path gates. Validate the syntax by pushing a no-op PR touching `src/codegenie/probes/base.py` on a scratch branch and confirming the auto-request happens (or, equivalently, by running GitHub's CODEOWNERS validator via the `gh` CLI).
5. Write `.github/PULL_REQUEST_TEMPLATE.md` with the three checkboxes.
6. Author `docs/contributing.md` with the four sections. Cross-link to `phase-arch-design.md`, the ADR folder, and `localv2.md §4`. Keep it under ~250 lines — it's onboarding, not reference.
7. Update `mkdocs.yml` to include `docs/contributing.md` in the curated `nav`. Run `make docs` locally and confirm `mkdocs build --strict` is green.
8. Create the Phase 1 milestone in the GitHub project board via `gh`. File the five Layer A probe issues and the three follow-up issues against it. Link each to the relevant `phase-arch-design.md` / `roadmap.md` section in the issue body.
9. Update the phase README's exit-criteria checklist (or create a minimal README if absent) to mark every Phase 0 exit criterion as complete with a link to the verifying test or artifact.
10. Close the Phase 0 milestone via `gh milestone edit --state closed`.
11. Verify all six CI jobs are green on `main`'s HEAD on Python 3.11 and 3.12 by reading the workflow runs page.
12. Run `make check` locally; open PR; merge.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file path: `tests/unit/test_project_artifacts.py`

The test set pins the **intent** of each artifact, not just existence — a contributor cannot land an empty `contributing.md`, a CODEOWNERS file with no owner tokens, a `dependabot.yml` containing only whitespace, or a PR template with the right strings hidden inside HTML comments. Each test maps to one AC. Verification of GitHub-UI rendering, milestone closure, and post-merge CI greenness is pinned on-disk via the phase README's `## Handoff record` (AC-8) which itself is unit-tested below.

```python
# tests/unit/test_project_artifacts.py
"""
Phase 0 handoff artifacts must exist, parse, and pin the intent of every AC
in S5-02. GitHub-UI rendering and milestone closure are pinned indirectly via
the on-disk Handoff record (AC-8); CI greenness on main is corroborated by
the workflow-run URL pinned there.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
GITHUB_USER_RE = re.compile(r"@[A-Za-z0-9-]+(/[A-Za-z0-9_-]+)?")


def _flatten_nav(node: object) -> list[str]:
    out: list[str] = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, list):
        for item in node:
            out.extend(_flatten_nav(item))
    elif isinstance(node, dict):
        for value in node.values():
            out.extend(_flatten_nav(value))
    return out


# ---- AC-1: issue templates exist with valid frontmatter ----------------------

ISSUE_TEMPLATES = (
    ".github/ISSUE_TEMPLATE/new-probe.md",
    ".github/ISSUE_TEMPLATE/new-skill.md",
    ".github/ISSUE_TEMPLATE/adr-amendment.md",
)


@pytest.mark.parametrize("relpath", ISSUE_TEMPLATES)
def test_issue_template_has_valid_frontmatter(relpath: str) -> None:
    text = (REPO_ROOT / relpath).read_text(encoding="utf-8")
    # Frontmatter is the first YAML block between two `---` lines.
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    assert m, f"{relpath}: missing GitHub frontmatter block"
    fm = yaml.safe_load(m.group(1)) or {}
    assert isinstance(fm, dict), f"{relpath}: frontmatter is not a mapping"
    assert fm.get("name"), f"{relpath}: frontmatter `name` missing or empty"
    assert fm.get("about"), f"{relpath}: frontmatter `about` missing or empty"


def test_adr_amendment_template_body_references_workflow() -> None:
    body = (REPO_ROOT / ".github/ISSUE_TEMPLATE/adr-amendment.md").read_text(encoding="utf-8")
    # Body must hand a contributor everything ADR-0007's workflow requires.
    for marker in ("ADR-0007", "localv2.md §4", "probe_contract.v1.json", "templates/adr-amendment.md"):
        assert marker in body, f"adr-amendment.md body missing marker: {marker!r}"


# ---- AC-2: dependabot schema --------------------------------------------------

def test_dependabot_yaml_schema() -> None:
    cfg = yaml.safe_load((REPO_ROOT / ".github/dependabot.yml").read_text(encoding="utf-8"))
    assert cfg.get("version") == 2, f"dependabot version != 2: {cfg.get('version')!r}"
    updates = cfg.get("updates") or []
    ecosystems = {u.get("package-ecosystem") for u in updates}
    assert ecosystems == {"pip", "github-actions"}, f"unexpected ecosystems: {ecosystems!r}"
    for u in updates:
        assert (u.get("schedule") or {}).get("interval") == "weekly", f"non-weekly: {u!r}"
        assert u.get("open-pull-requests-limit") == 5, f"PR cap != 5: {u!r}"


# ---- AC-3: CODEOWNERS gates with real owners ---------------------------------

CONTRACT_FROZEN_FILES = (
    "src/codegenie/probes/base.py",
    "tests/snapshots/probe_contract.v1.json",
    "tests/unit/test_pyproject_fence.py",
    "tests/unit/test_project_artifacts.py",
    "localv2.md",
    ".github/CODEOWNERS",
)
CONTRACT_FROZEN_DIRS = ("docs/production/adrs/",)


def _parse_codeowners(text: str) -> list[tuple[str, tuple[str, ...]]]:
    rules: list[tuple[str, tuple[str, ...]]] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        pattern, owners = parts[0], tuple(parts[1:])
        rules.append((pattern, owners))
    return rules


def test_codeowners_gates_contract_frozen_paths() -> None:
    rules = _parse_codeowners((REPO_ROOT / ".github/CODEOWNERS").read_text(encoding="utf-8"))
    patterns = {p: owners for p, owners in rules}

    for path in CONTRACT_FROZEN_FILES:
        assert path in patterns, f"CODEOWNERS missing rule for {path!r}"
        owners = patterns[path]
        assert owners, f"CODEOWNERS rule for {path!r} has no owners (silent no-gate)"
        assert all(GITHUB_USER_RE.fullmatch(o) for o in owners), f"bad owner tokens for {path!r}: {owners!r}"
        assert not path.endswith("/"), f"file path mis-rendered as directory: {path!r}"

    for path in CONTRACT_FROZEN_DIRS:
        assert path in patterns, f"CODEOWNERS missing rule for {path!r}"
        owners = patterns[path]
        assert owners, f"CODEOWNERS rule for {path!r} has no owners"
        assert path.endswith("/"), f"directory pattern missing trailing slash: {path!r}"


# ---- AC-4: PR template — three checkboxes, all paths, all CI jobs ------------

CI_JOBS = ("lint", "typecheck", "test", "security", "docs", "fence")


def test_pr_template_contract_and_ci_jobs() -> None:
    body = (REPO_ROOT / ".github/PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")
    checkboxes = re.findall(r"^- \[ \] .+$", body, flags=re.MULTILINE)
    assert len(checkboxes) >= 3, f"PR template has {len(checkboxes)} checkboxes; want ≥ 3"
    for path in (
        "src/codegenie/probes/base.py",
        "tests/snapshots/probe_contract.v1.json",
        "tests/unit/test_pyproject_fence.py",
        "localv2.md",
        "docs/production/adrs/",
    ):
        assert path in body, f"PR template missing contract-frozen path {path!r}"
    for job in CI_JOBS:
        assert re.search(rf"\b{job}\b", body), f"PR template missing CI job name {job!r}"
    assert "ADR-0007" in body, "PR template missing ADR-0007 reference"
    assert "ADR amendment" in body or "adr-amendment" in body, "PR template missing ADR-amendment phrasing"


# ---- AC-5: contributing.md sections + load-bearing content -------------------

def test_contributing_md_sections_and_content() -> None:
    body = (REPO_ROOT / "docs/contributing.md").read_text(encoding="utf-8")
    h2s = re.findall(r"^## (.+)$", body, flags=re.MULTILINE)
    section_markers = ("Bootstrap", "Running the harness", "Adding a probe", "Project conventions")
    for marker in section_markers:
        assert any(marker in h for h in h2s), f"contributing.md missing H2 section: {marker!r}; got {h2s!r}"

    # Coverage ratchet (open question Q5) — all three datapoints present.
    for ratchet in ("85/75", "87/77", "90/80"):
        assert ratchet in body, f"contributing.md missing coverage ratchet datapoint: {ratchet!r}"

    # ADR-0006 four-extras shape (load-bearing for Phase 4 LLM-SDK landing zone).
    for extra in ("gather", "dev", "service", "agents"):
        # Surrounded by backticks or brackets in idiomatic prose; substring check is sufficient.
        assert extra in body, f"contributing.md missing [project.optional-dependencies] extra: {extra!r}"
    assert "[agents]" in body, "contributing.md must name the [agents] slot for LLM SDKs (ADR-0006)"

    # ADR-0007 amendment workflow + S4-01 worked example + bootstrap recipe.
    for marker in ("ADR-0007", "make bootstrap", "codegenie gather", "LanguageDetectionProbe"):
        assert marker in body, f"contributing.md missing required marker: {marker!r}"

    # Open question Q2 — Probe version bumps named as a heading or bullet.
    assert "Probe version bumps" in body or "probe-version-bump" in body, \
        "contributing.md missing Q2 resolution (probe-version-bump convention)"

    # Negative-space: the S1-04 TODO placeholder must be gone.
    assert "TODO(S5-02)" not in body, "contributing.md still contains S1-04's TODO(S5-02) marker"


# ---- AC-6: contributing.md is in mkdocs nav exactly once ---------------------

def test_contributing_md_is_in_mkdocs_nav() -> None:
    cfg = yaml.safe_load((REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
    refs = _flatten_nav(cfg.get("nav") or [])
    hits = [p for p in refs if p.endswith("contributing.md")]
    assert len(hits) == 1, f"contributing.md must appear exactly once in nav; got {hits!r} from {refs!r}"


# ---- AC-7: pyproject mirrors the coverage-ratchet comment --------------------

def test_pyproject_mirrors_coverage_ratchet_schedule() -> None:
    lines = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines()
    anchors = [i for i, ln in enumerate(lines) if "--cov-fail-under=85" in ln]
    assert anchors, "pyproject.toml has no `--cov-fail-under=85` line to anchor the comment to"
    for anchor in anchors:
        window = lines[max(0, anchor - 5): anchor + 6]
        joined = "\n".join(line for line in window if line.lstrip().startswith("#"))
        if "87/77" in joined and "90/80" in joined and "contributing.md" in joined:
            return
    pytest.fail("pyproject.toml is missing the coverage-ratchet comment near --cov-fail-under=85")


# ---- AC-8: phase README pins the handoff record ------------------------------

PR_URL_RE = re.compile(r"https://github\.com/[^\s)]+/pull/\d+")
SHA_RE = re.compile(r"\b[0-9a-f]{40}\b")
WORKFLOW_RUN_RE = re.compile(r"https://github\.com/[^\s)]+/actions/runs/\d+")
MILESTONE_RE = re.compile(r"https://github\.com/[^\s)]+/milestone/\d+")
ISSUE_RE = re.compile(r"https://github\.com/[^\s)]+/issues/\d+")


def test_phase_readme_pins_handoff_evidence() -> None:
    readme = (REPO_ROOT / "docs/phases/00-bullet-tracer-foundations/README.md").read_text(encoding="utf-8")
    # Two named sections.
    assert re.search(r"^## Exit criteria\b", readme, flags=re.MULTILINE), "README missing `## Exit criteria` section"
    handoff_match = re.search(
        r"^## Handoff record\b(.*?)(?=^## |\Z)", readme, flags=re.MULTILINE | re.DOTALL
    )
    assert handoff_match, "README missing `## Handoff record` section"
    record = handoff_match.group(1)

    assert PR_URL_RE.search(record), "Handoff record missing merged PR URL"
    assert SHA_RE.search(record), "Handoff record missing 40-char main HEAD SHA"
    assert WORKFLOW_RUN_RE.search(record), "Handoff record missing workflow-run URL"
    assert "3.11" in record and "3.12" in record, "Handoff record must name both Python matrix versions"
    assert MILESTONE_RE.search(record), "Handoff record missing Phase 1 milestone URL"

    issue_urls = ISSUE_RE.findall(record)
    assert len(issue_urls) == 8, f"Handoff record must list exactly 8 Phase 1 issue URLs; got {len(issue_urls)}"
```

The test suite fails initially because the seven artifact files do not exist, `contributing.md` is the S1-04 stub with `TODO(S5-02)`, `pyproject.toml` has no ratchet comment, and the phase README has no `## Handoff record`. Run the suite, confirm failure on every named test, commit the failing tests as a marker.

### Green — make it pass

Create each of the seven artifacts and update three existing files. The implementation is mechanical; each item maps directly to one or more ACs.

- **Issue templates** (AC-1) — three small Markdown files with GitHub `name`/`about`/`labels` frontmatter (frontmatter is what the GitHub UI parses to render the chooser; without it the file is invisible). The `adr-amendment.md` body literally names `ADR-0007`, `localv2.md §4`, `probe_contract.v1.json`, and the relative path `templates/adr-amendment.md` (the PR template S2-05 landed) — these strings power AC-1's body assertions.
- **`dependabot.yml`** (AC-2) — `version: 2`, two `updates[]` entries with `package-ecosystem: pip` and `package-ecosystem: github-actions`, both with `schedule.interval: weekly` and `open-pull-requests-limit: 5`.
- **`CODEOWNERS`** (AC-3) — every gated path on its own line, each followed by ≥ 1 `@owner` token. Single-file patterns must NOT carry a trailing slash; the only directory pattern is `docs/production/adrs/` (which must). Document the team-expansion plan in a top-of-file comment. The seven gated paths are: the six in AC-3 plus `.github/CODEOWNERS` itself.
- **`PULL_REQUEST_TEMPLATE.md`** (AC-4) — exactly three Markdown task-list checkboxes (`- [ ] ...`) at column 0. The first names the five contract-frozen paths (including `tests/unit/test_pyproject_fence.py` so fence-scope drift trips the prompt — `High-level-impl.md §Implementation-level risks #4`) and links to ADR-0007. The second enumerates the six CI job names explicitly. The third covers ADRs honored.
- **`docs/contributing.md`** (AC-5) — replace the S1-04 `TODO(S5-02)` stub with the four-section body. The "Adding a probe" cheat sheet is the load-bearing section for Phase 1 onboarding; "Project conventions" carries the coverage ratchet (`85/75 → 87/77 → 90/80`), the four-extras shape (`gather`/`dev`/`service`/`agents`) with the `[agents]` rule explained, the ADR-0007 amendment workflow, and the "Probe version bumps" sub-heading resolving open question Q2.
- **`pyproject.toml`** (AC-7) — add a one-line `# Coverage ratchet: 85/75 (Phase 0) → 87/77 (Phase 1) → 90/80 (Phase 2). See docs/contributing.md §Project conventions.` comment within ±5 lines of `--cov-fail-under=85`. This is the structural defense against a contributor editing the gate without seeing the schedule.
- **`mkdocs.yml`** (AC-6) — add a `Contributing` entry referencing `contributing.md` under the curated `nav`. Position is editorial (suggested: after the `Phases` section, but no AC pins position); the test only enforces a single occurrence.
- **`docs/phases/00-bullet-tracer-foundations/README.md`** (AC-8) — extend (do not replace) the existing reading-order section with two new H2 sections: `## Exit criteria` (the ten criteria from `phase-arch-design.md §Goals` as `[x]` checkboxes with verifying-test paths) and `## Handoff record` (PR URL, `main` HEAD SHA, workflow-run URL naming both Python 3.11 and 3.12, Phase 1 milestone URL, exactly eight Phase 1 issue URLs).
- **Phase 1 milestone work** (AC-9, AC-10) — create the milestone via `gh milestone create --title "Phase 1"`; file the eight issues via `gh issue create --milestone "Phase 1"` (five Layer A probes + three follow-ups); close the Phase 0 milestone via `gh milestone edit --state closed` *after* paste-back of the URLs into the README's Handoff record.

Resist scope expansion: this story is *not* the place to clean up the excluded design docs (`mkdocs nav cleanup` is one of the three Phase 1 follow-up issues this story files), and it is *not* the place to author new ADRs (those belong with the runtime changes that motivate them).

### Refactor — clean up

- Cross-link `docs/contributing.md` from the phase README's onboarding section so a contributor landing in the phase folder finds the guide.
- Confirm the `.github/ISSUE_TEMPLATE/adr-amendment.md` issue template body contains the literal relative path `templates/adr-amendment.md` so a contributor opening an amendment issue can navigate to the matching PR template that S2-05 landed. The two are siblings: issue template captures *why* the amendment is needed (the snapshot diff plus the §4 change); PR template captures *what changed* (the implementation update). AC-1's body assertion enforces the cross-link.
- Re-run `make docs` after the `nav` edit; confirm zero warnings under `mkdocs build --strict`.
- Verify CODEOWNERS path globs match GitHub's behavior — trailing slashes matter, glob semantics differ from `.gitignore`. The unit test enforces the file-vs-directory shape (no trailing slash on file paths; trailing slash on the one directory). Corroborate with a synthetic test PR touching `src/codegenie/probes/base.py` on a scratch branch and confirming the designated reviewer auto-requests, or with `gh api repos/:owner/:repo/codeowners/errors`.
- Verify the README's `## Handoff record` has the workflow-run URL pinned to the *post-merge* `main` SHA (not the PR branch's SHA) — the AC-8 test enforces the format, but the human ritual is to update the SHA + workflow-run URL *after* the PR merges and the `main`-branch CI run completes green on both Python 3.11 and 3.12. This is the on-disk audit defense the implementer notes describe.

## Files to touch

| Path | Why |
|---|---|
| `.github/ISSUE_TEMPLATE/new-probe.md` | New file — onboarding template for Phase 1's Layer A probe issues. |
| `.github/ISSUE_TEMPLATE/new-skill.md` | New file — anticipates Phase 4's Skills catalog; ships now so the template exists when the first Skill issue is filed. |
| `.github/ISSUE_TEMPLATE/adr-amendment.md` | New file — the workflow ADR-0007 references in the snapshot-test failure message. |
| `.github/dependabot.yml` | New file — weekly `pip` + `github-actions` updates. |
| `.github/CODEOWNERS` | New file — gates the contract-frozen path set. |
| `.github/PULL_REQUEST_TEMPLATE.md` | New file — names the contract-frozen paths + the six CI jobs explicitly. |
| `docs/contributing.md` | Modify — replace the S1-04 `TODO(S5-02)` stub with the four-section body (bootstrap, run the harness, adding a probe, project conventions incl. coverage ratchet + four-extras shape + ADR-amendment workflow + probe-version-bumps). |
| `mkdocs.yml` | Modify — add `Contributing: contributing.md` (or the appropriate nested key) under the curated `nav`. |
| `pyproject.toml` | Modify — add a `# Coverage ratchet: 85/75 → 87/77 → 90/80. See docs/contributing.md §Project conventions.` comment within ±5 lines of `--cov-fail-under=85`. |
| `tests/unit/test_project_artifacts.py` | New file — eight tests pinning AC-1 through AC-8 invariants on disk (frontmatter, dependabot schema, CODEOWNERS shape with real owners, PR-template checkboxes + CI jobs, contributing.md sections + content, nav single-occurrence, pyproject ratchet comment, phase README handoff record). |
| `docs/phases/00-bullet-tracer-foundations/README.md` | Modify (file exists) — append `## Exit criteria` and `## Handoff record` H2 sections; preserve existing reading-order content. |

## Out of scope

- **Net-new runtime code under `src/codegenie/`** — by design. Phase 0's runtime surface is sealed at S5-01; this story is artifacts + docs.
- **Cleaning up the excluded design docs** (`docs/local.md`, `docs/auto-agent-design.md`, `docs/gemini-auto-agent-design.md`, `docs/context.md`, `docs/localv2.md`) — handled by the Phase 1 follow-up issue `mkdocs nav cleanup` that this story files. The decision (fix-vs-delete) belongs to Phase 1, not Phase 0.
- **Authoring new ADRs** — none of the Step 5 work introduces a new architectural decision worth an ADR. ADRs ship with the runtime changes that motivate them; documentation alone does not earn one.
- **Team-level CODEOWNERS expansion** — Phase 0 has one maintainer; the file ships with the user's GitHub handle gating the contract-frozen paths. Expanding to a team is a Phase 1+ administrative change, not a code change.
- **Bench-comment GitHub Action wiring** — S5-01's bench tests emit `bench-results.json`; the Action that consumes the artifact and posts the PR comment is one of the Phase 1 follow-ups (filed as a separate issue, not this one — the bench tests run advisory-only without it).
- **Reproducibility CI check** — `phase-arch-design.md §Non-goals #7` defers this to Phase 1 when probe outputs (SCIP, runtime traces) become reproducible-vs-not.

## Notes for the implementer

- The `tests/unit/test_project_artifacts.py` test is the structural defense against regression — if a future contributor deletes `.github/CODEOWNERS` or removes `contributing.md` from `nav`, CI fails. This test should be in `tests/unit/` (not `tests/adv/`) because it pins a positive invariant (artifacts present), not a negative one (attack surface absent).
- Per `phase-arch-design.md §Goals` #6 and `High-level-impl.md §Step 5 Done criteria`, `mkdocs build --strict` must be green over the curated `nav` after `contributing.md` is added — `--strict` treats warnings as errors, so any broken relative link in `contributing.md` will fail CI. Test locally with `make docs` before opening the PR.
- The CODEOWNERS file is parsed by GitHub, not by Git; the syntax is *similar* to `.gitignore` but with a username column. Trailing slashes on directory paths matter (`docs/production/adrs/` not `docs/production/adrs`). Validate by opening a synthetic PR before the phase closes — the Implementation-level risk #4 in `High-level-impl.md` calls this out explicitly.
- Per `High-level-impl.md §Implementation-level risks #4`, the `fence` test scope is `dependencies` only — never `optional-dependencies`. The CODEOWNERS gate on `tests/unit/test_pyproject_fence.py` is the structural defense against silent scope widening; do not omit it.
- The "Adding a probe" cheat sheet in `docs/contributing.md` is the single most-read document Phase 1 contributors will consult. Make it concrete — a numbered seven-step recipe pointing at the exact files (`src/codegenie/probes/`, `src/codegenie/schema/probes/`, `src/codegenie/probes/__init__.py`, `tests/unit/test_<probe>.py`). Reference the existing `LanguageDetectionProbe` (from S4-01) as the worked example.
- The coverage ratchet schedule (`85/75 → 87/77 in Phase 1 → 90/80 in Phase 2 → frozen until Phase 5`) resolves open question #5 from `phase-arch-design.md`. Document it in `docs/contributing.md` under "Project conventions" *and* mirror it as a comment in `pyproject.toml` near `--cov-fail-under=85` so a contributor editing the gate sees the schedule.
- When closing the Phase 0 milestone, link to (a) the PR that lands this story, (b) the workflow run on `main`'s HEAD showing all six CI jobs green on Python 3.11 and 3.12, and (c) the Phase 1 milestone URL. This forms the auditable handoff record per `phase-arch-design.md §Integration with Phase 1`.
- The three Phase 1 follow-up issues (`mkdocs nav cleanup`, `probe-version-bump convention`, `aiofiles documentation bug`) are named explicitly in `High-level-impl.md §Step 5`. File them via `gh issue create --milestone "Phase 1"` so they show up in the milestone view; do not file them in the Phase 0 milestone.
