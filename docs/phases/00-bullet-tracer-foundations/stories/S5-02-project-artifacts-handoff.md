# Story S5-02 — Project artifacts + contributor docs + Phase 1 handoff

**Step:** Step 5 — Close the remaining CI gates and project conventions
**Status:** Ready
**Effort:** M
**Depends on:** S4-05
**ADRs honored:** ADR-0002, ADR-0006, ADR-0007

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

- [ ] `.github/ISSUE_TEMPLATE/new-probe.md`, `.github/ISSUE_TEMPLATE/new-skill.md`, `.github/ISSUE_TEMPLATE/adr-amendment.md` exist and render in the GitHub UI when "New Issue" is clicked (verified by opening the GitHub repo's `/issues/new/choose` URL; screenshot or URL-200 check captured in the PR description).
- [ ] `.github/dependabot.yml` ships with weekly `pip` (against `pyproject.toml`) and weekly `github-actions` ecosystems; the schedule cadence is `weekly`; the open-PR cap is reasonable (`open-pull-requests-limit: 5` per ecosystem).
- [ ] `.github/CODEOWNERS` gates the following paths to a designated reviewer set (the user's GitHub handle for Phase 0; expand the team later): `src/codegenie/probes/base.py`, `tests/snapshots/probe_contract.v1.json`, `tests/unit/test_pyproject_fence.py`, `localv2.md`, `docs/production/adrs/`, and `.github/CODEOWNERS` itself. A synthetic test PR touching `src/codegenie/probes/base.py` shows the designated reviewer auto-requested in the "Reviewers" pane.
- [ ] `.github/PULL_REQUEST_TEMPLATE.md` exists and includes (a) a checkbox "Touches a contract-frozen file (`src/codegenie/probes/base.py`, `tests/snapshots/probe_contract.v1.json`, `localv2.md`, or `docs/production/adrs/`)? If yes, link the ADR amendment PR.", (b) a checkbox "All six CI jobs green on this PR (`lint`, `typecheck`, `test`, `security`, `docs`, `fence`)", (c) a checkbox "ADRs honored explicitly named in the description".
- [ ] `docs/contributing.md` exists and covers four sections: **Bootstrap** (`make bootstrap` + the `uv`/no-`uv` paths from S1-03), **Running the harness locally** (`codegenie gather ./`, reading the YAML and audit record), **Adding a probe — cheat sheet** (the seven-step recipe: subclass `Probe`, declare `declared_inputs`, declare `applies_to_tasks`/`applies_to_languages`, bump `version`, register via `probes/__init__.py` import line, add per-probe sub-schema under `src/codegenie/schema/probes/`, write the unit test + the registry test + the cache-hit test), **Project conventions** (the coverage ratchet schedule `85/75 → 87/77 in Phase 1 → 90/80 in Phase 2 → frozen until Phase 5`, the chokepoint policy from `phase-arch-design.md §Component design` for hashing/exec/sanitizer/registry, and the ADR-amendment workflow from ADR-0007).
- [ ] `mkdocs.yml`'s curated `nav` includes `docs/contributing.md`; `make docs` (which runs `mkdocs build --strict`) passes without warnings.
- [ ] A Phase 1 milestone exists in the GitHub project board with at least eight issues: five for the remaining Layer A probes (`NodeBuildSystem`, `NodeManifest`, `CI`, `Deployment`, `TestInventory` per `localv2.md §12 Week 1`), plus three follow-up issues — (a) `mkdocs nav cleanup` for the currently-excluded docs (`local.md`, `auto-agent-design.md`, `gemini-auto-agent-design.md`, `context.md`, `localv2.md`), (b) `probe-version-bump convention` documented in the contributing guide and enforced in PR review (open question #2 in `phase-arch-design.md`), (c) `aiofiles documentation bug — remove from roadmap.md §Phase 0` (per `final-design.md §L3 row 15`).
- [ ] The Phase 0 milestone is closed; its checklist in `docs/phases/00-bullet-tracer-foundations/README.md` (or the phase README equivalent — confirm which file is the canonical Phase 0 status page; if absent, this story creates a minimal `README.md` in the phase folder with the exit-criteria checklist marked complete).
- [ ] All six CI jobs (`lint`, `typecheck`, `test`, `security`, `docs`, `fence`) are green on the `main` branch's HEAD commit on **both** Python 3.11 and Python 3.12 on `ubuntu-24.04`. Verified by reading the latest workflow run on `main` after this story's PR merges.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` (no `src/` changes expected — but the lint/format pass over the new markdown is a no-op gate), and `pytest` all pass on the touched files. The `docs` job (`mkdocs build --strict`) passes after `docs/contributing.md` is added to the curated `nav`.

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

### Red — write the failing test first

Test file path: `tests/unit/test_project_artifacts.py`

```python
# tests/unit/test_project_artifacts.py
"""
Phase 0 handoff artifacts must exist on disk and be wired into the docs nav.

The GitHub-UI-side rendering and milestone state are verified out-of-band
(they cannot be asserted from pytest); this test pins the file-system
invariants only — the artifacts a Phase 1 contributor will look for cold.
"""
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "relpath",
    [
        ".github/ISSUE_TEMPLATE/new-probe.md",
        ".github/ISSUE_TEMPLATE/new-skill.md",
        ".github/ISSUE_TEMPLATE/adr-amendment.md",
        ".github/dependabot.yml",
        ".github/CODEOWNERS",
        ".github/PULL_REQUEST_TEMPLATE.md",
        "docs/contributing.md",
    ],
)
def test_phase_0_handoff_artifact_exists(relpath: str) -> None:
    assert (REPO_ROOT / relpath).is_file(), f"missing handoff artifact: {relpath}"


def test_codeowners_gates_contract_frozen_paths() -> None:
    body = (REPO_ROOT / ".github/CODEOWNERS").read_text(encoding="utf-8")
    # Every contract-frozen path must appear in CODEOWNERS so a touch
    # forces the designated reviewer (ADR-0002, ADR-0007).
    for path in (
        "src/codegenie/probes/base.py",
        "tests/snapshots/probe_contract.v1.json",
        "tests/unit/test_pyproject_fence.py",
        "localv2.md",
        "docs/production/adrs/",
    ):
        assert path in body, f"CODEOWNERS missing gate for: {path}"


def test_contributing_md_is_in_mkdocs_nav() -> None:
    cfg = yaml.safe_load((REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8"))
    nav = cfg.get("nav") or []
    # Flatten the nav tree and assert contributing.md appears.
    flat: list[str] = []
    def walk(node: object) -> None:
        if isinstance(node, str):
            flat.append(node)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
    walk(nav)
    assert any(p.endswith("contributing.md") for p in flat), \
        f"docs/contributing.md not in mkdocs nav; got: {flat}"


def test_pr_template_names_contract_frozen_paths() -> None:
    body = (REPO_ROOT / ".github/PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")
    # The PR template names the contract-frozen file set so a contributor
    # cannot silently bypass the ADR-amendment workflow (ADR-0007).
    assert "src/codegenie/probes/base.py" in body
    assert "tests/snapshots/probe_contract.v1.json" in body
    assert "ADR amendment" in body
```

The test fails initially because none of the seven files exist yet and `mkdocs.yml`'s `nav` does not yet include `contributing.md`. Run it, confirm failure on every parametrized row and on each of the three structural assertions, commit the failing test as a marker.

### Green — make it pass

Create each of the seven artifacts. The implementation is mechanical:

- **Issue templates** — three small Markdown files with GitHub frontmatter. The `adr-amendment.md` template links to ADR-0007's resolution policy and asks for the link to the `localv2.md` diff and the link to the regenerated `probe_contract.v1.json` blob.
- **`dependabot.yml`** — two ecosystems, weekly schedule, conservative PR cap.
- **`CODEOWNERS`** — path globs to a single reviewer (the user's GitHub handle); document the team-expansion plan in a top-of-file comment.
- **`PULL_REQUEST_TEMPLATE.md`** — three checkboxes that name the contract-frozen path set and the six CI jobs explicitly so the contract cannot drift via vague "honor the rules" wording.
- **`docs/contributing.md`** — four sections per the acceptance criteria. Link out to `phase-arch-design.md`, the ADR folder, and `localv2.md §4`. The "Adding a probe" cheat sheet is the load-bearing section for Phase 1 onboarding.
- **`mkdocs.yml`** — add a `Contributing` entry under the curated `nav`. Position it after the `Phases` section.

Resist scope expansion: this story is *not* the place to clean up the excluded design docs (`mkdocs nav cleanup` is one of the three Phase 1 follow-up issues this story files), and it is *not* the place to author new ADRs (those belong with the runtime changes that motivate them).

### Refactor — clean up

- Cross-link `docs/contributing.md` from the phase README's onboarding section so a contributor landing in the phase folder finds the guide.
- Confirm the `adr-amendment.md` issue template references the same `templates/adr-amendment.md` PR template that S2-05 landed; the two work together (issue template captures *why*; PR template captures *what changed*).
- Re-run `make docs` after the `nav` edit; confirm zero warnings.
- Verify CODEOWNERS path globs match GitHub's behavior — trailing slashes, glob semantics, etc. Use the `gh` CLI's CODEOWNERS validator or the GitHub UI's "Settings → Code and automation → Code review limits" preview before merging.

## Files to touch

| Path | Why |
|---|---|
| `.github/ISSUE_TEMPLATE/new-probe.md` | New file — onboarding template for Phase 1's Layer A probe issues. |
| `.github/ISSUE_TEMPLATE/new-skill.md` | New file — anticipates Phase 4's Skills catalog; ships now so the template exists when the first Skill issue is filed. |
| `.github/ISSUE_TEMPLATE/adr-amendment.md` | New file — the workflow ADR-0007 references in the snapshot-test failure message. |
| `.github/dependabot.yml` | New file — weekly `pip` + `github-actions` updates. |
| `.github/CODEOWNERS` | New file — gates the contract-frozen path set. |
| `.github/PULL_REQUEST_TEMPLATE.md` | New file — names the contract-frozen paths + the six CI jobs explicitly. |
| `docs/contributing.md` | New file — bootstrap, run the harness, adding a probe, project conventions (incl. the coverage ratchet schedule). |
| `mkdocs.yml` | Modify — add `Contributing: contributing.md` (or the appropriate nested key) under the curated `nav`. |
| `tests/unit/test_project_artifacts.py` | New file — pins the file-system invariants of the seven artifact files + the `mkdocs nav` wiring. |
| `docs/phases/00-bullet-tracer-foundations/README.md` (if absent) | New file or modify — final exit-criteria checklist with every Phase 0 criterion marked complete. |

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
