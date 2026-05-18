# Story S7-08 — Final `kernel-frozen` verification

**Step:** Step 7 — Ship plugin wiring: FallbackTierPlanRecipeEngine + harvest + E2E exit criteria
**Status:** Ready
**Effort:** S
**Depends on:** S7-01 (plugin adapter landed — the last code change Step 7 makes); S1-07 (`test_kernel_frozen.py` shipped in Step 1 with the path allow-list).
**ADRs honored:** ADR-0003 (path-scoped fence amendment), ADR-0004 (`PlanOutcome` doesn't widen `RecipeOutcome`), production-ADR-0031 (extension by addition into plugin), Phase-7 precondition (diff touches only the new plugin directory)

## Context

`test_kernel_frozen.py` landed in S1-07 as a guard: it asserts **zero edits** to Phase-0/1/2/3 kernel files for the duration of Phase 4. The test runs in CI on every push, but its load-bearing moment is the *merging of Step 7* — if any story between S1 and S7 sneakily edited `src/codegenie/{probes,coordinator,cache,output,schema,plugins/protocols.py}/`, `RemediationOrchestrator`, the `Plugin` Protocol, the `RecipeEngine` Protocol, or the `Transform` ABC, this story catches it.

This is **not** a re-implementation story — it's the explicit re-verification gate. The deliverable is (a) running the test on the post-Step-7 codebase, (b) walking the diff range from `git merge-base master HEAD` to confirm the change-set lives only inside the allow-listed paths, (c) updating the test's "phase 7 precondition" docstring with the as-merged confirmation, and (d) (optional) tightening the allow-list if any path can be safely narrowed post-Phase-4.

The Phase-7 precondition is the *next phase*'s exit-criterion contract: Phase 7 (distroless plugin) must be able to merge with zero edits outside its own new plugin directory. That contract is preserved only if Phase 4 itself preserved its analog. This story is the empirical proof.

Three failure modes to surface explicitly:
1. **Phase-3 file silently edited** — most likely `src/codegenie/plugins/protocols.py` (a `RecipeEngine` ABC method added "to make the adapter simpler"). ADR-0004's `tests/property/test_plan_outcome_no_recipe_outcome_widening.py` catches the variant widening, but a method addition is a separate failure mode.
2. **Phase-0 fence-CI silently widened** — `tests/unit/test_pyproject_fence.py`'s `FORBIDDEN_LLM_SDKS` set was modified in a way the path-scoped Phase-4 fence (S1-05) was supposed to compensate for, but a future commit weakened either side.
3. **`Transform` ABC edited** — a contributor adds `apply_with_capability(...)` or similar; this story's check is the last line of defense.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals — G3` — "Zero edits to Phase 3 kernel. No edits to `src/codegenie/{probes,coordinator,cache,output,schema}/`, no edits to `RemediationOrchestrator`, no edits to `Plugin` Protocol, no edits to `RecipeEngine` Protocol, no edits to `Transform` ABC, no widening of `RecipeOutcome`. Enforced by `tests/fence/test_kernel_frozen.py` + `tests/property/test_plan_outcome_no_recipe_outcome_widening.py`."
  - `../phase-arch-design.md §Edge cases` and §"Phase 7 precondition" framing throughout.
- **Phase ADRs:**
  - `../ADRs/0003-path-scoped-fence-amendment.md` — the broader fence story; this story is the runtime witness.
  - `../ADRs/0004-plan-outcome-wraps-recipe-outcome.md` — "Phase 7's 'diff touches only the new plugin directory' exit criterion holds." This story closes that loop for Phase 4.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` — extension by addition; the Phase-7 precondition is rooted here.
- **High-level impl:**
  - `../High-level-impl.md §Step 7 §Done criteria` — "`tests/fence/test_kernel_frozen.py` green: zero edits to Phase 0/1/2/3 kernel files; zero edits to `RemediationOrchestrator`, `Plugin` Protocol, `RecipeEngine` Protocol, `Transform` ABC."
- **Existing code:**
  - `tests/fence/test_kernel_frozen.py` (S1-07) — read its allow-list carefully; the test format is the contract.
  - `tests/property/test_plan_outcome_no_recipe_outcome_widening.py` (S1-03) — the companion AST-walk property test; must remain green.
  - `tests/fence/test_pyproject_fence_phase4.py` (S1-05) — the path-scoped fence; must remain green.
  - `tests/unit/test_pyproject_fence.py` (Phase 0) — the closure-scoped fence; must remain green and **unmodified**.

## Goal

Run `tests/fence/test_kernel_frozen.py` (and its two companion tests) at Step-7 completion against the merged Step-7 codebase, walk the actual diff from `git merge-base master HEAD..HEAD` to confirm the change-set's path footprint matches the allow-list, and update the test's docstring with the as-merged Phase-7-precondition affirmation. Optionally tighten the allow-list if any path can be safely narrowed.

## Acceptance criteria

- [ ] `tests/fence/test_kernel_frozen.py` runs and returns green on the post-Step-7 codebase. Run `pytest tests/fence/test_kernel_frozen.py -v` and paste the result into the story's attempt log.
- [ ] `tests/property/test_plan_outcome_no_recipe_outcome_widening.py` runs and returns green — the Phase-3 `RecipeOutcome` AST has not drifted.
- [ ] `tests/fence/test_pyproject_fence_phase4.py` runs and returns green — the path-scoped fence still holds.
- [ ] `tests/unit/test_pyproject_fence.py` (Phase 0) runs green; `git diff master -- tests/unit/test_pyproject_fence.py` returns **empty** (file unmodified across Phase 4).
- [ ] `git diff --name-only $(git merge-base master HEAD)..HEAD` is inspected; every changed path lives in **at least one** of these allow-list buckets, with no exceptions:
  - `src/codegenie/fallback/**` (new)
  - `src/codegenie/rag/**` (new)
  - `plugins/vulnerability-remediation--node--npm/**` (existing plugin; surgical additions only)
  - `tests/**` (test suite; all phases write here)
  - `docs/phases/04-vuln-llm-fallback-rag/**` (this phase's docs)
  - `pyproject.toml` (dep additions; gated by the path-scoped fence)
  - `Makefile` (e.g., `make refresh-cassettes` target from S3-06)
  - `.codeowners` / `CODEOWNERS` (cassette steward entry from S3-06)
  - `docs/operations/{secrets,cassettes,embeddings}.md` (S7-10)
- [ ] Any path *outside* the allow-list raises a structured failure: the story fails-loud (Global Rule 12) with a diagnostic naming the file, the commit that introduced the change, and the ADR amendment the change would need. **Do not** silently extend the allow-list — that defeats the purpose of this story.
- [ ] `tests/fence/test_kernel_frozen.py`'s module docstring is updated with a one-line as-merged confirmation at the bottom: e.g., `# Verified at Phase-4 Step-7 completion on 2026-MM-DD: diff range <sha>..<sha> touched <N> files, all inside allow-list.`
- [ ] If the allow-list can be tightened (e.g., Step 4's RAG store didn't actually need to write anywhere new and a sub-path can be narrowed), the tightening is proposed but **not** applied in this story — record it as a follow-up TODO in the test's docstring with a Phase-5 cross-link.
- [ ] No edits to `RemediationOrchestrator` (`src/codegenie/orchestrator/orchestrator.py`), `Plugin` Protocol, `RecipeEngine` Protocol, `Transform` ABC. Verified by:
  - `git diff master -- src/codegenie/plugins/protocols.py` returns empty.
  - `git diff master -- src/codegenie/orchestrator/` returns empty.
  - `git diff master -- src/codegenie/transforms/` returns empty (the ABC; not the plugin-side transforms).
- [ ] `make check` clean.
- [ ] Story-attempt log records the diff-walk output (path list + bucket assignment).

## Implementation outline

1. Pull latest master; rebase the Step-7 branch onto master if needed.
2. Run `pytest tests/fence/test_kernel_frozen.py tests/property/test_plan_outcome_no_recipe_outcome_widening.py tests/fence/test_pyproject_fence_phase4.py tests/unit/test_pyproject_fence.py -v`. All four must be green. If any is red, **stop** — surface immediately per Global Rule 12; do not proceed.
3. Run `git diff --name-only $(git merge-base master HEAD)..HEAD | sort > /tmp/phase4-diff-paths.txt`. Inspect the file.
4. Walk each path; assign it to one of the allow-list buckets. If any path doesn't fit, locate the introducing commit (`git log --oneline -- <path>`), inspect, and decide:
   - If the change is safe and additive (no kernel edit), document the path in the test's docstring and add the bucket if missing.
   - If the change is a kernel edit, **revert it** and replace with an additive shape; do not extend the allow-list to cover it.
5. Run `git diff master -- src/codegenie/plugins/protocols.py src/codegenie/orchestrator/ src/codegenie/transforms/` and confirm each returns empty. If not empty, revert per Step 4.
6. Update `tests/fence/test_kernel_frozen.py` module docstring with the as-merged confirmation line.
7. If any sub-path can be tightened, document the proposal as a TODO inside the docstring (Phase-5 follow-up).
8. Run the full `make check` to confirm no test was broken by the verification.

## TDD plan — red / green / refactor

### Red — write the failing test first

This story is the verification gate, not a code-change story. The "failing test" form is a script that walks the diff and asserts allow-list membership. Land it as `tests/fence/test_phase4_diff_within_allow_list.py`:

```python
# tests/fence/test_phase4_diff_within_allow_list.py
"""Phase-4 final verification: every Phase-4 diff path is inside the kernel-frozen allow-list.

Runs against the merged Phase-4 branch; intended as the Step-7 completion gate.
"""
from __future__ import annotations
import subprocess
from pathlib import Path
import pytest


# Allow-list buckets from the story's acceptance criteria.
ALLOWED_PREFIXES = (
    "src/codegenie/fallback/",
    "src/codegenie/rag/",
    "plugins/vulnerability-remediation--node--npm/",
    "tests/",
    "docs/phases/04-vuln-llm-fallback-rag/",
)

ALLOWED_EXACT = frozenset({
    "pyproject.toml",
    "uv.lock",
    "Makefile",
    "CODEOWNERS",
    ".codeowners",
    "docs/operations/secrets.md",
    "docs/operations/cassettes.md",
    "docs/operations/embeddings.md",
})


def _phase4_diff_paths() -> list[str]:
    base = subprocess.check_output(
        ["git", "merge-base", "master", "HEAD"], text=True,
    ).strip()
    out = subprocess.check_output(
        ["git", "diff", "--name-only", f"{base}..HEAD"], text=True,
    )
    return [p for p in out.splitlines() if p]


def test_every_diff_path_inside_allow_list():
    paths = _phase4_diff_paths()
    assert paths, "no diff from master; nothing to verify"
    violations = []
    for p in paths:
        if any(p.startswith(prefix) for prefix in ALLOWED_PREFIXES):
            continue
        if p in ALLOWED_EXACT:
            continue
        violations.append(p)
    assert not violations, (
        "Phase-4 final verification: paths outside the kernel-frozen allow-list:\n  - "
        + "\n  - ".join(violations)
        + "\nEach path must either fit a bucket or be reverted (do not silently widen)."
    )


def test_phase_3_kernel_files_unmodified():
    base = subprocess.check_output(
        ["git", "merge-base", "master", "HEAD"], text=True,
    ).strip()
    forbidden = [
        "src/codegenie/plugins/protocols.py",
        "src/codegenie/orchestrator/orchestrator.py",
        "src/codegenie/transforms/",
        "tests/unit/test_pyproject_fence.py",
    ]
    for f in forbidden:
        diff = subprocess.check_output(
            ["git", "diff", "--", f"{base}..HEAD", "--", f], text=True,
        )
        assert diff == "", f"forbidden modification to kernel-frozen path: {f}\n{diff}"


def test_companion_property_test_still_green():
    """The PlanOutcome AST-walk property is its own test; this asserts it exists, runs, and passes."""
    result = subprocess.run(
        ["pytest", "-q", "tests/property/test_plan_outcome_no_recipe_outcome_widening.py"],
        check=False,
    )
    assert result.returncode == 0
```

Run: `pytest tests/fence/test_phase4_diff_within_allow_list.py -v` — fails if any path is outside the allow-list, succeeds otherwise.

### Green — make it pass

If the diff-walk shows any path outside the allow-list, revert the offending commit (do not silently widen the allow-list). If the test passes, the verification is complete.

### Refactor — clean up

- Move the `ALLOWED_PREFIXES` / `ALLOWED_EXACT` constants into `tests/fence/_kernel_allow_list.py` if other fence tests (Phase 7 will write one too) want to consume the same list.
- Update `tests/fence/test_kernel_frozen.py`'s module docstring with the as-merged line.
- Re-run `make check` to confirm.

## Files to touch

| Path | Why |
|---|---|
| `tests/fence/test_phase4_diff_within_allow_list.py` | New diff-walk gate (the verification artifact). |
| `tests/fence/test_kernel_frozen.py` | Docstring update only (as-merged confirmation line). |
| `tests/fence/_kernel_allow_list.py` (optional) | Shared allow-list constants if Phase 7 wants to reuse. |

## Out of scope

- Phase 7's own kernel-frozen verification — that ships in Phase 7 (mirror pattern).
- Tightening the allow-list (proposed as TODO, not applied in this story).
- Adversarial corpus (S7-09).
- Phase-5 contract snapshot refresh (S7-10).

## Notes for the implementer

- This story is **the merge gate** — it must run as the last verification in Step 7 before the branch is merged. Running it early (before S7-01 lands) catches nothing.
- The temptation to silently widen the allow-list is real and is the single most common way this guard fails. Follow Global Rule 12: surface the violation explicitly; do not paper over it.
- If a violation surfaces, the resolution is *not* "amend the allow-list with an ADR." It is "revert the offending commit and replace with an additive shape." The Phase-7 precondition is a contract with Phase 7's implementer (a future agent or human); they're relying on Phase 4 not having papered over its own kernel edits.
- The `test_phase_3_kernel_files_unmodified` test is the explicit guard for the four most-likely-to-be-edited paths (`protocols.py`, orchestrator, transforms, Phase-0 fence). If any of these legitimately needs a change in Phase 4, that's an ADR-amendment-level event — surface per Global Rule 7 before the change lands, not after.
- The Phase-0 fence file (`tests/unit/test_pyproject_fence.py`) is in the "unmodified" guard because S1-05 should have *added* the Phase-4 path-scoped fence as a new file (`tests/fence/test_pyproject_fence_phase4.py`), not edited the Phase-0 set. If S1-05 did edit Phase-0's set, that's a deviation from ADR-0003 — surface immediately.
- Optional tightening proposals belong in the docstring TODO, not in this story's code. Phase-5 will pick them up if they're actionable.
- The diff-walk runs against `git merge-base master HEAD`; if the branch was rebased recently, the merge-base might differ from what reviewers expect — print both the base SHA and the HEAD SHA in the test's failure message so the reviewer can reproduce locally.
