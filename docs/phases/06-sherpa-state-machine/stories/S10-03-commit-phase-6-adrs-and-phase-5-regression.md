# Story S10-03 — Commit remaining Phase 6 ADRs + Phase 5 regression-suite gate

**Step:** Step 10 — Adversarial hardening + Layer-8 E2E + final polish
**Status:** Ready
**Effort:** M
**Depends on:** S10-02
**ADRs honored:** All Phase 6 ADRs (this is the story that lands the not-yet-committed ones); ADR-0009 (no Phase 0–5 source touched, save the surgical S4-06/S4-10 rename); ADR-0010 (`run_one` promotion is the one and only Phase 5 source touch)

## Context

This is the final-polish story for Phase 6. By the time it runs, the entire test pyramid (Layers 0–8) is green and the LangGraph state machine works end-to-end. What remains is the **documentation and gate plumbing** that turns Phase 6 from a working implementation into a *defended* one: every load-bearing decision lives in an ADR, the `pre-commit` hook prevents regression on touched files, the HITL contract is exported and CI-diffed, and the full Phase 5 regression suite passes on top of Phase 6 changes — which is the canary for Phase 7's "no Phase 0–6 source touched" exit criterion.

The 13 Phase 6 ADRs (0001–0013) are largely committed already (see `docs/phases/06-sherpa-state-machine/ADRs/`). This story verifies that **every** load-bearing decision the High-level-impl §Step 10 enumerates is *actually* in the ADRs directory in Nygard format, lands any that are missing (ADR-P6-008 in particular per Gap 1; the README explicitly says it is "noted but not yet documented"), and wires the cross-cutting CI gates (`pre-commit`, HITL contract diff, Phase 5 regression).

The "Phase 5 regression suite still passes on top of Phase 6 changes" criterion is **the test that proves Phase 7 will be able to start**. If anything in Steps 1–9 silently broke Phase 5 — beyond the documented surgical S4-06/S4-10 rename — Phase 7's "no Phase 0–6 source modified" exit criterion is already at risk. This story runs that suite as a hard CI gate and fails the PR if it regresses.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §CI gates` (lines 1196–1207) — line 1207 names `docs/contracts/hitl-v0.6.0.json` as the CI-diffed export; line 1200 names `pre-commit` running ruff + mypy strict on `src/codegenie/graph/`.
  - `../phase-arch-design.md §Integration with Phase 7` (lines 1226–1241) — "no Phase 0–5 source touched except ADR-0010's rename" is the Phase-7-enabling invariant this story canaries.
  - `../phase-arch-design.md §Tradeoffs accepted` (line 1302) — ADR-0008's deferral; line 1302 is the row this story's ADR commit references.
  - `../phase-arch-design.md §Gap analysis` (lines 1337–1359) — Gap 1 (ADR-P6-008 unresolved roadmap-vs-default), Gap 4 (`continue` after same-sig flake — proposed P6-009 if behavior changes).
- **Phase ADRs:**
  - `../ADRs/README.md §Decisions noted but not yet documented` — explicit list of what this story must land. Most pressing: **ADR-P6-008** (Gap 1) if Phase 6 wants to clear it before Phase 7 starts.
  - `../ADRs/0001-…` through `../ADRs/0013-…` — the existing committed set; this story does **not** rewrite any of them.
- **High-level-impl:**
  - `../High-level-impl.md §Step 10 — Features delivered` (lines 276–286) — names every ADR the step must commit; lines 287–296 enumerate the Done criteria this story closes.
  - `../High-level-impl.md §Implementation-level risks` (lines 314–326) — Risks 1–6 are the bugs this story's gates are designed to catch.
- **Existing artifacts (must read before editing):**
  - `src/codegenie/graph/hitl.py` (S1-03) — source of `HumanRequest.model_json_schema()` + `HumanDecision.model_json_schema()` merged into `docs/contracts/hitl-v0.6.0.json`. Export logic lives in `hitl.py`'s `__main__` per S7-05.
  - `docs/contracts/hitl-v0.6.0.json` (S7-05) — already committed; this story does not regenerate it but adds the diff gate to CI.
  - `tests/test_phase5_regression_suite.py` or whatever Phase 5's regression harness is called — read first to understand the scope; do not duplicate it.
  - `.pre-commit-config.yaml` — extend, do not rewrite.
- **Production reference:**
  - `docs/production/adrs/` — Nygard format reference; match the existing project-level ADR style exactly.

## Goal

Every Phase 6 ADR listed in High-level-impl §Step 10 is committed in Nygard format under `docs/phases/06-sherpa-state-machine/ADRs/`; the `pre-commit` hook runs `ruff` + `mypy --strict` on changed files under `src/codegenie/graph/`; the HITL contract diff gate runs in CI; and the full Phase 5 regression suite passes when run on top of the Phase 6 changes.

## Acceptance criteria

- [ ] **ADR audit.** A `tools/check_phase6_adrs.py` script (or a small `pytest` test under `tests/docs/`) enumerates every ADR ID High-level-impl §Step 10 names (ADR-P6-001 through ADR-P6-007, plus ADR-P6-008 if Gap 1 is resolved here) and asserts each has a corresponding file under `docs/phases/06-sherpa-state-machine/ADRs/` matching `NNNN-*.md`. Currently committed: 0001–0013 (the local numbering). The audit maps `ADR-P6-NNN` → the local-numbered file (the README index is the source of truth for that mapping).
- [ ] **ADR-P6-008 (Gap 1).** Either: (a) commit a new `docs/phases/06-sherpa-state-machine/ADRs/0014-roadmap-twice-in-a-row-vs-default-max-attempts.md` in Nygard format that records the chosen resolution (amend roadmap, or change default to 2); OR (b) explicitly defer it with a one-paragraph addendum to `ADRs/README.md` stating the deferral and the phase that owns the resolution. The story must not silently leave Gap 1 floating into Phase 7.
- [ ] **ADR-P6-009 (Gap 4).** If S7-04 chose option (a) clear `prior_attempts` or (b) `hitl_continue` marker, commit a new ADR documenting the choice; if S7-04 stuck with option (c) document-and-warn, no new ADR — the existing CLI-warning behavior is the recorded decision.
- [ ] **Every ADR is Nygard format.** Each new ADR has the canonical sections: Status, Context, Decision, Alternatives Considered, Consequences (or Tradeoffs Accepted / Tradeoffs Refused), Reversibility, Related ADRs. Match the existing `0001-…` through `0013-…` shape verbatim. Verified by a small `pytest` that grep-checks the section headers.
- [ ] **`pre-commit` hook.** `.pre-commit-config.yaml` has an additive entry that runs `ruff check`, `ruff format --check`, and `mypy --strict` against any file under `src/codegenie/graph/` that is staged for commit. The hook is *file-scoped*; it does not run on the whole repo (cost mitigation per Phase 9 risk #5). Verify by staging a no-op edit to `src/codegenie/graph/state.py`, running `pre-commit run --files src/codegenie/graph/state.py`, and asserting the three tools all run.
- [ ] **HITL contract diff gate.** A CI step runs `python -m codegenie.graph.hitl --export > /tmp/hitl.regen.json` and `diff docs/contracts/hitl-v0.6.0.json /tmp/hitl.regen.json` — non-zero diff fails CI. (S7-05 lands the export; this story lands the CI-side diff invocation if S7-05 stopped at the export script.)
- [ ] **Phase 5 regression suite green.** The full pre-Phase-6 Phase 5 test suite (`tests/gates/`, `tests/phase5/`, or whatever Phase 5's pytest scope is — confirm by reading Phase 5's `README` / `final-design.md`) runs and passes with the Phase 6 code merged. Concretely: `pytest tests/gates/ tests/phase5/ -v` (or the project-level equivalent) returns exit 0. Add this as a named CI job so a Phase 6 regression on Phase 5 is loud.
- [ ] **Phase 5 source canary.** A small in-repo check (test or `Makefile` target) compares the Phase 5 source tree to its `git merge-base` against the Phase 6 branch and asserts the diff is empty **except for** `src/codegenie/gates/runner.py`'s `run_one` rename (ADR-0010). Any other diff is a Phase 7 exit-criterion violation and fails CI.
- [ ] **High-level-impl §Step 10 Done criteria.** All eight checkboxes (lines 288–295) are demonstrably green at PR time. The story's PR description must cite each one inline.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and the full Phase 6 + Phase 5 pytest scope all pass.

## Implementation outline

1. **Inventory the existing ADRs.** Run `ls docs/phases/06-sherpa-state-machine/ADRs/` and cross-reference against High-level-impl §Step 10 lines 276–286. The local numbering 0001–0013 maps to the `ADR-P6-NNN` names via the README index. Build a small table in the PR description.
2. **Resolve Gap 1 (ADR-P6-008).** Read `final-design.md §Gap analysis Gap 1` and `phase-arch-design.md §Gap analysis Gap 1` to confirm the choice space. Pick one:
   - Amend `docs/roadmap.md`'s Phase 6 exit criterion to say "fail consecutively at the same gate" (matches `max_attempts=3` default).
   - OR change ADR-0014's default `max_attempts` from 3 to 2 (and update tests / the Phase 5 contract — likely too invasive for Phase 6).
   - OR defer to Phase 7 with a one-paragraph addendum to `ADRs/README.md`.
   - Commit the resolution as `0014-roadmap-twice-in-a-row-vs-default-max-attempts.md` (or defer-paragraph) **before** writing any other code in this story; the resolution affects the ADR audit test below.
3. **Resolve Gap 4 (ADR-P6-009).** Read S7-04's story output. If the option-(c) document-and-warn behavior shipped, no new ADR is needed beyond a one-paragraph note in `ADRs/README.md §Decisions noted but not yet documented` marking it resolved. If options (a) or (b) shipped, commit `0015-hitl-continue-after-same-sig-flake.md` in Nygard format documenting the choice.
4. **Author the ADR audit test.** `tests/docs/test_phase6_adrs_complete.py`:
   - Parses `docs/phases/06-sherpa-state-machine/ADRs/README.md` for the index table.
   - Asserts every row maps to an existing file.
   - Asserts every file has the Nygard section headers.
   - Asserts every ADR named in `High-level-impl.md §Step 10` is represented (even if via the local numbering).
5. **Extend `.pre-commit-config.yaml`.** Add a `repo: local` hook with three `hooks:` entries (ruff check, ruff format --check, mypy --strict) each with `files: ^src/codegenie/graph/` so they only run on changed files in that path. Test the hook locally with `pre-commit run --files src/codegenie/graph/state.py`.
6. **HITL contract diff gate.**
   - Confirm S7-05 shipped `python -m codegenie.graph.hitl --export` writing to stdout.
   - Add a CI step to the per-PR workflow that runs the export, diffs against `docs/contracts/hitl-v0.6.0.json`, fails on non-empty diff. Provide a clear error message: `"Run python -m codegenie.graph.hitl --export > docs/contracts/hitl-v0.6.0.json and commit the result."`.
7. **Phase 5 regression CI job.**
   - Read Phase 5's `final-design.md` / `phase-arch-design.md` to confirm the test scope (`tests/gates/`, `tests/phase5/`, etc.).
   - Add a CI job (separate from the Phase 6 job) that runs that scope. Job name: `phase-5-regression-on-phase-6`.
   - Job fails the PR on non-zero exit.
8. **Phase 5 source canary.**
   - Add `tests/test_phase5_source_untouched.py` (or a `Makefile` target) that:
     - Computes `git diff --name-only $(git merge-base origin/main HEAD) -- src/codegenie/gates/ src/codegenie/planner/`.
     - Asserts the only changed file is `src/codegenie/gates/runner.py`.
     - Asserts the diff for `runner.py` is exclusively a rename of `_run_one_attempt` → `run_one` (regex-check the diff text, narrow scope).
   - This is a defensive test; if it ever flags more changes, surface to the implementer.
9. **PR description checklist.** Mirror the eight Done-criteria checkboxes from High-level-impl §Step 10 (lines 288–295) in the PR description with cite-links to evidence (test names, CI job names, ADR file paths).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/docs/test_phase6_adrs_complete.py`

```python
"""Phase 6 ADR completeness gate.

The High-level implementation plan (Step 10) names every ADR Phase 6 must
commit before merge. This test parses the manifest and the ADR README index,
and asserts every named ADR exists as a Nygard-format markdown file.

Failure mode this test catches: an ADR is referenced from the design docs
but never written, leaving a load-bearing decision undocumented. That kind
of drift compounds across phases — Phase 7's planner reads Phase 6 ADRs
to know what NOT to touch; a missing ADR is a silent license to violate.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ADR_DIR = Path(__file__).parents[2] / "docs" / "phases" / "06-sherpa-state-machine" / "ADRs"
HIGH_LEVEL_IMPL = Path(__file__).parents[2] / "docs" / "phases" / "06-sherpa-state-machine" / "High-level-impl.md"

NYGARD_REQUIRED_SECTIONS = ["Status", "Context", "Decision", "Consequences"]


def _adr_ids_named_in_high_level_impl() -> set[str]:
    text = HIGH_LEVEL_IMPL.read_text()
    return set(re.findall(r"ADR-P6-\d{3}", text))


def _committed_local_numbers() -> set[str]:
    return {p.name.split("-", 1)[0] for p in ADR_DIR.glob("[0-9]*.md")}


def test_every_p6_adr_named_in_step_10_is_committed() -> None:
    # Map ADR-P6-NNN to local 4-digit numbers via the README index.
    readme = (ADR_DIR / "README.md").read_text()
    named = _adr_ids_named_in_high_level_impl()
    # The README must mention each named ADR (either as a row in the index
    # or in the "Decisions noted but not yet documented" deferral list).
    missing = [adr_id for adr_id in named if adr_id not in readme]
    assert missing == [], f"ADRs named in High-level-impl but not in README: {missing}"


@pytest.mark.parametrize("adr_path", sorted(ADR_DIR.glob("[0-9]*.md")))
def test_each_adr_uses_nygard_format(adr_path: Path) -> None:
    text = adr_path.read_text()
    missing = [s for s in NYGARD_REQUIRED_SECTIONS if f"## {s}" not in text and f"# {s}" not in text]
    assert missing == [], f"{adr_path.name} missing Nygard sections: {missing}"
```

Test file path: `tests/test_phase5_source_untouched.py`

```python
"""Phase 7 exit-criterion canary: no Phase 0–5 source touched except ADR-0010.

Catches the subtle case where a Phase 6 story silently edited a Phase 5
file (e.g., to make a parity test pass). The only permitted Phase 5 edit
is GateRunner._run_one_attempt -> run_one (ADR-0010).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


PHASE5_SCOPE = ["src/codegenie/gates/", "src/codegenie/planner/"]
PERMITTED = {"src/codegenie/gates/runner.py"}


@pytest.mark.skipif(
    not Path(".git").is_dir(),
    reason="git history required for this canary",
)
def test_phase5_source_diff_against_merge_base() -> None:
    base = subprocess.check_output(
        ["git", "merge-base", "origin/main", "HEAD"], text=True
    ).strip()
    out = subprocess.check_output(
        ["git", "diff", "--name-only", base, "--"] + PHASE5_SCOPE, text=True
    )
    changed = {line.strip() for line in out.splitlines() if line.strip()}
    unexpected = changed - PERMITTED
    assert unexpected == set(), (
        f"Phase 5 source changed outside the ADR-0010 surgical rename: {unexpected}"
    )
```

### Green — make it pass

1. **ADR audit test fails first** because (most likely) ADR-P6-008 is named in High-level-impl but absent from the README. Resolve Gap 1 (commit `0014-…` or add a deferral paragraph), then the audit passes.
2. **Phase 5 source canary fails** only if a story upstream broke ADR-0009. If it does, **stop** — the violation is real and Phase 7 cannot proceed. Surface to the implementer; do not paper over.
3. **`pre-commit` hook landing**: run `pre-commit run --all-files` locally; expect failures only on previously-unfixed style/type issues in `src/codegenie/graph/`. Fix those (or surface as separate stories if non-trivial); do not weaken the hook.
4. **HITL contract diff gate**: if the diff is non-empty on first run, run `python -m codegenie.graph.hitl --export > docs/contracts/hitl-v0.6.0.json` and commit. This is the deliberate-update path arch §CI gates line 1207 describes.
5. **Phase 5 regression CI**: most likely passes outright; if it fails, the failure is a real regression — read the failing test, find the offending Phase 6 commit, fix at the source.

### Refactor — clean up

- Move repeated path computations (`Path(__file__).parents[2]` × 2) into a single `_repo_root()` helper in `tests/docs/conftest.py`.
- Document the ADR audit's regex (`ADR-P6-\d{3}`) in a comment — a future contributor renaming the ADR scheme should hit a loud test failure, not a silent skip.
- Confirm the new CI jobs are named distinctly (`phase-6-tests`, `phase-5-regression-on-phase-6`, `hitl-contract-diff`, `phase5-source-canary`) so a red CI status points to the right job.
- If `0014-…` was committed, update `ADRs/README.md`'s index table with the new row.

## Files to touch

| Path | Why |
|---|---|
| `docs/phases/06-sherpa-state-machine/ADRs/0014-roadmap-twice-in-a-row-vs-default-max-attempts.md` | New if Gap 1 resolved here. |
| `docs/phases/06-sherpa-state-machine/ADRs/0015-hitl-continue-after-same-sig-flake.md` | New if S7-04 chose (a) or (b); skip if (c). |
| `docs/phases/06-sherpa-state-machine/ADRs/README.md` | Update index table for any new ADR; mark resolved Gap 1 / Gap 4 entries. |
| `tests/docs/__init__.py` | New — package marker. |
| `tests/docs/test_phase6_adrs_complete.py` | New — ADR audit. |
| `tests/test_phase5_source_untouched.py` | New — Phase 5 source canary. |
| `.pre-commit-config.yaml` | Extend with file-scoped ruff + mypy hooks for `src/codegenie/graph/`. |
| `.github/workflows/<per-pr>.yml` (or equivalent) | Add `hitl-contract-diff`, `phase-5-regression-on-phase-6`, `phase5-source-canary` jobs. |

## Out of scope

- **Rewriting any existing ADR** — ADRs 0001–0013 are committed and immutable per the README's "Numbers are immutable" convention.
- **Phase 11 HITL signing layer** — ADR-0008 explicitly defers; this story does not anticipate it.
- **Phase 9 Postgres swap** — ADR-0011's threshold; this story does not measure it.
- **Phase 7 implementation** — the canary tests prove Phase 7 *can* start cleanly; Phase 7's own stories build the distroless loop.
- **The Layer-8 E2E test** — already landed in S10-02.
- **Adversarial tests** — already landed in S10-01.

## Notes for the implementer

- **Gap 1 (ADR-P6-008) deserves real thought**, not a rubber-stamp deferral. Read `phase-arch-design.md §Gap analysis Gap 1` end-to-end before picking the resolution. The cheapest fix is amending `docs/roadmap.md` to say "fail consecutively at the same gate" — it matches the production default and changes no code. If you choose to defer, the deferral paragraph must name the phase that owns the resolution (most likely Phase 11 since that phase touches HITL semantics anyway).
- **The Phase 5 source canary is the most load-bearing gate in this story.** If it fires, Phase 7's first sentence ("no Phase 0–6 source touched") is already wrong. Do not weaken the canary; if it flags a legitimate need (e.g., a typo fix in a Phase 5 docstring), surface the violation, get a one-line amendment to ADR-0009, and re-run. Silence is worse than friction here.
- **Do not delete or edit ADR-0001 through ADR-0013** even if you spot a typo. Their numbers are immutable. Open a follow-up story to amend with a "Superseded by" link if a real change is needed.
- The `pre-commit` hook scope is **file-glob**, not branch-wide. The hook should run only on changed files under `src/codegenie/graph/` — running mypy strict on the whole repo on every commit is too slow. Use `files: ^src/codegenie/graph/` in `.pre-commit-config.yaml` and verify by staging a no-op edit elsewhere and confirming the hook does not run.
- The HITL contract diff gate must give an *actionable* error message: `"Run python -m codegenie.graph.hitl --export > docs/contracts/hitl-v0.6.0.json and commit the result."` — operators landing on this gate for the first time need to know exactly what to do.
- If High-level-impl §Step 10 line 277 ("ADR-P6-001 — promote `_run_one_attempt` to public `run_one`") doesn't match what S4-10 actually committed (e.g., S4-10 needed a wider refactor per Risk #1 of High-level-impl), reconcile the doc — either S4-10's ADR is correct and High-level-impl §Step 10 is stale, or vice versa. The ADR file on disk is the source of truth.
- The full Phase 5 regression suite passing on top of Phase 6 changes is the **green light for Phase 7 to start**. Make this story's PR a clean signal — well-named jobs, clear PR description, no `[wip]` markers — because Phase 7's first story will read this one to confirm the floor.
