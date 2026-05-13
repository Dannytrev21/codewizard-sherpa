# Story S8-01 — Full Phase 3/4/5/6 unchanged integration suite

**Step:** Step 8 — Pre-flight final regression and snapshot-discipline rehearsal
**Status:** Ready
**Effort:** M
**Depends on:** S7-06
**ADRs honored:** ADR-P7-001, ADR-P7-002, ADR-P7-003, ADR-P7-006, ADR-0009

## Context

This story is the **hard merge gate** for Phase 7 (roadmap exit criterion G4). The whole load-bearing claim of Phase 7 — "extension by addition, behavior preserving" (per the ADR-0028 amendment landed in S1-06) — is only credible if every Phase 3/4/5/6 integration test still passes byte-for-byte with no edits to its source. This story wires those tests into a single re-import shim, registers them on CI's `merge` lane, and proves the regression suite blocks merge when broken.

This is downstream verification work: no new production code, no new probes. The single file it lands is a glue test that imports every Phase 3/4/5/6 integration test verbatim. Failure here means one of the six ADR-gated additive seams (S1-01..06) is not actually behavior-preserving — surface that loudly rather than paper over it.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Testing strategy ›Test pyramid ›Integration tests` — names `tests/integration/test_phase3_4_5_6_unchanged.py` as the G4 hard merge gate.
  - `../phase-arch-design.md §Testing strategy ›CI gates #4` — names this test as a merge-blocking gate.
  - `../phase-arch-design.md §Component 13` — enumerates the seam-by-seam behavior-preservation claims this story verifies.
  - `../phase-arch-design.md §Goals` G2/G3/G4 — the exit criteria this story closes.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0001-six-named-additive-seams-and-adr-0028-amendment.md` — ADR-P7-001 — the "behavior-preserving additive extension" definition this suite enforces.
  - `../ADRs/0002-register-gate-probe-new-registry.md` — ADR-P7-001 — Phase 2 coordinator must see byte-identical `all_probes()`.
  - `../ADRs/0003-objective-signals-widening-and-allowlists.md` — ADR-P7-002 — `ObjectiveSignals` default-`None` widening must keep every Phase 5 consumer green.
  - `../ADRs/0004-fallback-tier-task-type-kwarg.md` — ADR-P7-003 — `FallbackTier.run` with `task_type=None` must produce byte-identical Phase 4 results; `S1-04` already landed `tests/integration/test_phase4_default_task_type_behavior_unchanged.py`.
  - `../ADRs/0007-recipe-engine-literal-extended-with-dockerfile.md` — ADR-P7-006 — additive `"dockerfile"` Literal value must keep every Phase 3 `Recipe` deserialization byte-identical.
  - `../ADRs/0009-contract-surface-snapshot-canary.md` — ADR-0009 — pairs structurally with this regression test; both are permanent merge gates.
- **Production ADRs:**
  - `../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md` — Probe contract preserved.
  - `../../../production/adrs/0028-task-class-introduction-order.md` (amended in S1-06) — defines the "behavior preserving" claim this suite verifies.
- **Existing code:**
  - `tests/integration/test_phase3_*.py`, `tests/integration/test_phase4_*.py`, `tests/integration/test_phase5_*.py`, `tests/integration/test_phase6_*.py` — every Phase 3–6 integration test discovered under these paths is in scope.
  - `tests/integration/test_phase4_default_task_type_behavior_unchanged.py` (from S1-04) — already exercises ADR-P7-003 default branch; this story's suite must include it.
  - `.github/workflows/` — the CI lane definitions where the `merge` lane is registered (extend, don't rewrite).

## Goal

`pytest tests/integration/test_phase3_4_5_6_unchanged.py` re-runs every Phase 3/4/5/6 integration test verbatim with zero source edits to those test files, and the same suite is registered in CI's `merge` lane such that any Phase 3/4/5/6 test failure blocks merge regardless of Phase 7 test status.

## Acceptance criteria

- [ ] `tests/integration/test_phase3_4_5_6_unchanged.py` exists and discovers every `test_phase3_*.py`, `test_phase4_*.py`, `test_phase5_*.py`, `test_phase6_*.py` under `tests/integration/` — no allowlist, no skip-list, no edits to source test files.
- [ ] `pytest tests/integration/test_phase3_4_5_6_unchanged.py` is green on `master` after S7-06 has landed.
- [ ] CI workflow file (`.github/workflows/<merge-lane>.yml` or equivalent) names this test in the `merge` lane such that failure blocks merge regardless of Phase 7-only test results.
- [ ] Naive-failure rehearsal: a deliberate mutation under `src/codegenie/sandbox/signals/models.py` (e.g., flipping a default value on a pre-existing field that has *nothing* to do with the new Phase 7 fields) causes this suite to fail in CI — captured as a screenshot or CI log link in the PR description and then reverted.
- [ ] Suite respects xfail/skip markers from upstream test files verbatim — no new xfail / no new skip introduced by this glue file.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, and `mypy --strict` all pass on the touched files (the suite file itself is a `.py` test; mypy-strict applies if it's imported by anything in `src/`).

## Implementation outline

1. Write the failing red test that asserts the suite file exists and discovers ≥ N tests (N being the live count of Phase 3–6 integration tests at master HEAD).
2. Create `tests/integration/test_phase3_4_5_6_unchanged.py` using one of two equivalent shapes (pick whichever matches repo convention — read `tests/integration/conftest.py` first):
   - **`pytest --pyargs` re-import** via a small `pytest_collect_modifyitems` hook in this file's module that re-collects matching test modules.
   - Or a `pytest.main([...])` subprocess invocation that targets the four glob patterns and asserts exit code 0.
3. Land the CI lane definition: extend the existing CI workflow such that the `merge` lane runs `pytest tests/integration/test_phase3_4_5_6_unchanged.py` and treats any failure as merge-blocking.
4. Run the naive-failure rehearsal: locally edit one byte under `src/codegenie/sandbox/signals/models.py` (or any Phase 3–6 source file unrelated to the six seams), confirm the suite goes red, attach the failing log to the PR description, revert.
5. Refactor: ensure no new fixtures, no new conftest entries, no implicit reordering vs the upstream test files' own runs.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/test_phase3_4_5_6_unchanged.py` (the file *is* the test surface; the red phase is a meta-assertion that the file's collection produces the expected count).

What the test asserts (test name + one-line assertion):

```python
# tests/integration/test_phase3_4_5_6_unchanged.py
"""Glue test that re-runs every Phase 3/4/5/6 integration test verbatim.

Hard merge gate per phase-arch-design.md §Testing strategy ›CI gates #4 (G4).
This file MUST NOT modify upstream test source. Edits = ADR-0001 violation.
"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PHASE_3_TO_6_GLOBS = (
    "tests/integration/test_phase3_*.py",
    "tests/integration/test_phase4_*.py",
    "tests/integration/test_phase5_*.py",
    "tests/integration/test_phase6_*.py",
)

def _discover() -> list[Path]:
    files: list[Path] = []
    for g in PHASE_3_TO_6_GLOBS:
        files.extend(sorted(REPO_ROOT.glob(g)))
    return files

def test_discovery_finds_every_phase3_to_6_integration_test():
    files = _discover()
    # red: expect ≥ N, where N is the count at master HEAD when this story starts.
    # Replace N with the live count after running `ls tests/integration/test_phase{3,4,5,6}_*.py | wc -l`.
    assert len(files) >= N, f"Expected ≥ N Phase 3–6 integration files; found {len(files)}"

def test_phase_3_to_6_integration_suite_runs_unchanged():
    files = _discover()
    assert files, "No Phase 3–6 integration files discovered; glob misconfigured."
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", *[str(f) for f in files]],
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, (
        "A Phase 3/4/5/6 integration test failed. "
        "Phase 7's behavior-preserving additive extension claim (ADR-0028 amendment) "
        "is violated by something this PR ships. Surface and revert; do not weaken this test."
    )
```

Run it: it should fail because either the file doesn't exist (`collection error`) or because `N` hasn't been substituted yet (`AssertionError`). Both are valid red failures. Commit the failing test as a marker.

### Green — make it pass

Substitute `N` with the live count discovered via `find tests/integration -name 'test_phase[3-6]_*.py' | wc -l` at master HEAD. Run `pytest tests/integration/test_phase3_4_5_6_unchanged.py` and confirm green. If any upstream Phase 3/4/5/6 test is red on master, **stop and surface it** — do not weaken this story to skip it.

### Refactor — clean up

After green:
- Add a docstring referencing ADR-0001 and §Testing strategy ›CI gates #4.
- If the repo convention is `pytest -n auto`, pass `-n auto` to the subprocess for parity with the wall-clock canary (S7-01).
- Add the CI lane wiring (separate file, separate diff): the `merge` lane in `.github/workflows/` runs this test as a required check.
- Run the naive-failure rehearsal once locally, attach the CI red log to the PR description, revert.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_phase3_4_5_6_unchanged.py` | New file — the G4 hard merge gate glue test. |
| `.github/workflows/<merge-lane>.yml` (or repo's equivalent CI config) | Add this test to the `merge` lane such that failure blocks merge. |
| `docs/phases/07-migration-task-class/stories/S8-01-phase-3-4-5-6-unchanged-suite.md` | Status update on completion. |

## Out of scope

- **New Phase 3/4/5/6 tests.** This story re-runs existing ones verbatim. New tests belong in their own phase's story (or as Phase 7 additive coverage in earlier S1–S7 stories).
- **Editing or weakening any upstream Phase 3–6 integration test.** If one is flaky, file a follow-up; do not paper it over here.
- **Wall-clock or perf assertions.** S7-01 owns the regression-suite wall-clock canary. This story is correctness only.
- **`@pure_edge` / `python -O` coverage.** Handled by S8-02.
- **Grype-DB concurrent-refresh matrix.** Handled by S8-03.

## Notes for the implementer

- The whole point of this test is that it is **glue, not logic**. If you find yourself reasoning about *why* a Phase 3/4/5/6 test should be green, you're outside scope — the upstream test owns its own correctness; this test only verifies it still passes.
- The repo convention for CI lanes may be GitHub Actions `if:` matrices, Buildkite pipelines, or some other shape. Read `.github/workflows/` (and look for the lane Phase 6 used for its similar merge-gate registration) before extending — surface a conflict per Rule 7 rather than blending.
- Per `phase-arch-design.md §Component 13`, the seam edits in S1-02 (Phase 5 signals widening), S1-03 (allowlists), S1-04 (`FallbackTier.run` kwarg), and S1-05 (`Recipe.engine` Literal) are the *only* Phase 3–6 source bytes that changed. If this suite fails, the failure points directly at which seam broke its behavior-preservation claim.
- Naive-failure rehearsal must be a *real* CI run, not a local-only run. The point is to prove the merge lane actually blocks; a local-only green proves nothing.
- Per CLAUDE.md Rule 12 (Fail loud): if any Phase 3–6 integration test is xfail or skip at master HEAD, do not silently inherit that — surface the count and document the expected pass/skip/xfail breakdown in the story's PR description.
- Do not parallelize with `-n auto` if a Phase 3–6 test relies on serial execution (rare but possible — Phase 5's sandbox tests historically were serial). Read each test file's `pytestmark` before flipping the flag.
- If the count `N` drifts between writing the red test and landing the green, that's fine — the AC says ≥ N, not == N. New tests landing in the same PR cycle should only increase the count.
