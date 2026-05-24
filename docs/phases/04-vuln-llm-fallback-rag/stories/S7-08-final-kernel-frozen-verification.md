# Story S7-08 — Final `kernel-frozen` verification

**Step:** Step 7 — Ship plugin wiring: FallbackTierPlanRecipeEngine + harvest + E2E exit criteria
**Status:** HARDENED (2026-05-24 — phase-story-validator) — **BLOCKED-PARTIAL on S1-07** (Phase-3 baseline row never landed; AC-1 runs against phase-2 baseline only until S1-07 is re-authored — see [`_validation/S7-08-final-kernel-frozen-verification.md`](_validation/S7-08-final-kernel-frozen-verification.md))
**Effort:** S
**Depends on:** S7-01 (plugin adapter landed — the last code change Step 7 makes); S1-03 (`tests/property/test_plan_outcome_no_recipe_outcome_widening.py` ships — see AC-2); S1-05 (`tests/fence/test_pyproject_fence_phase4.py` ships — see AC-3); **S1-07 RESCUE** (`tests/fence/test_kernel_frozen.py` Phase-3 baseline row — see `_validation/S1-07-test-kernel-frozen.md`; the executor must either wait for S1-07 re-author, or document AC-1's deferred phase-3 coverage in the attempt log).
**ADRs honored:** ADR-0003 (path-scoped fence amendment), ADR-0004 (`PlanOutcome` doesn't widen `RecipeOutcome`), production-ADR-0031 (extension by addition into plugin), Phase-7 precondition (diff touches only the new plugin directory)

## Validation notes

Validated: 2026-05-24 — phase-story-validator
Verdict: **HARDENED**. Twelve edits applied; goal is correct (Phase-4 Step-7
merge gate enforcing kernel-frozen contract), body had block-class drifts
against shipped code. Full audit at
[`_validation/S7-08-final-kernel-frozen-verification.md`](_validation/S7-08-final-kernel-frozen-verification.md).

**Block-class fixes (already applied below):**
- F1 — `src/codegenie/orchestrator/` does **not exist** in the shipped tree.
  Vacuous-pass guard removed; replaced with explicit-file pins on
  `src/codegenie/plugins/protocols.py`, `src/codegenie/plugins/registry.py`,
  `src/codegenie/transforms/recipe_engine.py`, `src/codegenie/transforms/transform.py`.
- F2 — `git diff master -- src/codegenie/transforms/` would always be
  non-empty (the directory holds Phase-3 plugin-side `engines/`, `policy/`,
  `sandbox/`, etc.). Replaced with file-specific pin on the ABC
  `transforms/transform.py` (and `recipe_engine.py` for the protocol).
- F3 — `Depends on:` was undercounted. Added S1-03 + S1-05 + surfaced S1-07
  RESCUE as `BLOCKED-PARTIAL`.
- F4 — `git diff -- {base}..HEAD -- {f}` is invalid (double `--`). Fixed in
  TDD plan.
- F5 — AC bucket list and TDD `ALLOWED_EXACT` disagreed. Reconciled: added
  `uv.lock`, `.importlinter`, `.github/workflows/ci.yml` to both.

**Harden-class fixes (already applied below):**
- F6 — `test_phase_3_kernel_files_unmodified` forbidden-paths list expanded
  to cover all 8 Goal-G3 surfaces (5 dirs + 3 contract files), not just 4.
- F7 — Dropped `test_companion_property_test_still_green` (recursive pytest
  spawn — fragile and redundant).
- F8 — Added vacuous-allow-list invariant guard (`ALLOWED_PREFIXES` entries
  must be non-empty and not `/`).
- F9 — Extracted pure `_classify` helper; added planted-violation table
  tests so the fence is exercised on a clean branch (Rule 9).
- F10 — Empty-diff-on-master case now `pytest.skip`s instead of failing.
- F11 — Docstring-update demoted from AC to Notes (manual hygiene step).
- F12 — Functional-core / imperative-shell split for `_classify` (pure) vs
  `_phase4_diff_paths` (subprocess).
- F14 — Failure message now includes bucket-classification hint + ADR
  amendment escape-hatch wording (mirrors Phase-3 fence convention, Rule 11).

**Demoted (Rule 2 wins):**
- F13 — Optional `_kernel_allow_list.py` extraction deferred; rule-of-three
  not yet met (Phase 7 will be the second consumer if it materializes).

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
  - `tests/fence/test_kernel_frozen.py` (shipped GREEN by **Phase-3 S1-05**, not Phase-4 S1-07 — see RESCUE report below) — read its `_BASELINES`/`_KERNEL_ALLOWLIST` shape carefully; the test format is the contract. The Phase-3 baseline row is **not yet landed** (S1-07 is RESCUE).
  - `tests/property/test_plan_outcome_no_recipe_outcome_widening.py` (S1-03, HARDENED) — the companion AST-walk property test; must remain green.
  - `tests/fence/test_pyproject_fence_phase4.py` (S1-05, HARDENED) — the path-scoped fence; must remain green.
  - `tests/unit/test_pyproject_fence.py` (Phase 0) — the closure-scoped fence; must remain green and **unmodified**.
- **Sibling stories (consumed):**
  - `S1-03-plan-outcome-wraps-recipe-outcome.md` — AC-2 depends on its property test.
  - `S1-05-path-scoped-fence-amendment.md` — AC-3 depends on its path-scoped fence; the `_validation/S1-05-…md` F8 finding requires `.github/workflows/ci.yml` wiring (now in the allow-list).
  - `S1-07-test-kernel-frozen.md` — **RESCUE**; see `_validation/S1-07-test-kernel-frozen.md`. The Phase-3 baseline row this story implicitly relies on for AC-1's phase-3 coverage was never landed.
- **Shipped kernel contract files** (the exact paths the four-class guard pins):
  - `src/codegenie/plugins/protocols.py:69` — `class Plugin(Protocol)`
  - `src/codegenie/plugins/registry.py:76` — `class PluginRegistry`
  - `src/codegenie/transforms/recipe_engine.py:67` — `class RecipeEngine(Protocol)`
  - `src/codegenie/transforms/transform.py:64` — `class Transform(ABC)`
  - `src/codegenie/transforms/transform_registry.py:95` — `class TransformRegistry`
  - `src/codegenie/{probes,coordinator,cache,output,schema}/` — Phase-0/1/2 kernel directories (Goal G3)

## Goal

Run `tests/fence/test_kernel_frozen.py` (and its two companion tests) at Step-7 completion against the merged Step-7 codebase, walk the actual diff from `git merge-base master HEAD..HEAD` to confirm the change-set's path footprint matches the allow-list, and update the test's docstring with the as-merged Phase-7-precondition affirmation. Optionally tighten the allow-list if any path can be safely narrowed.

## Acceptance criteria

- [ ] **AC-1** `tests/fence/test_kernel_frozen.py` (shipped by Phase-3 S1-05) runs and returns green on the post-Step-7 codebase. Run `pytest tests/fence/test_kernel_frozen.py -v` and paste the result into the story's attempt log. **Coverage note:** if S1-07 has not yet landed the `phase-3` baseline row, AC-1 covers only the phase-2 baseline; record this as a known deferred coverage in the attempt log and route per the S1-07 rescue plan.
- [ ] **AC-2** `tests/property/test_plan_outcome_no_recipe_outcome_widening.py` (S1-03) runs and returns green — the Phase-3 `RecipeOutcome` AST has not drifted. (Depends on S1-03 being GREEN.)
- [ ] **AC-3** `tests/fence/test_pyproject_fence_phase4.py` (S1-05) runs and returns green — the path-scoped fence still holds. (Depends on S1-05 being GREEN.)
- [ ] **AC-4** `tests/unit/test_pyproject_fence.py` (Phase 0) runs green; `git diff "$(git merge-base master HEAD)..HEAD" -- tests/unit/test_pyproject_fence.py` returns **empty** (file unmodified across Phase 4 — narrows-not-edits per ADR-0003 §Decision + arch §Gap 5).
- [ ] **AC-5** A new gate `tests/fence/test_phase4_diff_within_allow_list.py` ships; it walks `git diff --name-only "$(git merge-base master HEAD)..HEAD"` and asserts every changed path lives in **at least one** of these allow-list buckets — the **same** set is enumerated both in this AC and in the test file's `ALLOWED_PREFIXES` / `ALLOWED_EXACT` constants:
  - **Prefixes** (`startswith`):
    - `src/codegenie/fallback/` (new)
    - `src/codegenie/rag/` (new)
    - `plugins/vulnerability-remediation--node--npm/` (existing plugin; surgical additions only)
    - `tests/` (test suite; all phases write here)
    - `docs/phases/04-vuln-llm-fallback-rag/` (this phase's docs)
  - **Exact filenames:**
    - `pyproject.toml` (dep additions; gated by the path-scoped fence per ADR-0003)
    - `uv.lock` (lockfile companion to `pyproject.toml`)
    - `.importlinter` (path-scoped contracts per ADR-0003 §Decision)
    - `Makefile` (e.g., `make refresh-cassettes` target from S3-06)
    - `CODEOWNERS` / `.codeowners` (cassette steward entry from S3-06)
    - `.github/workflows/ci.yml` (path-scoped fence CI wiring per S1-05 F8)
    - `docs/operations/secrets.md` / `cassettes.md` / `embeddings.md` (S7-10)
- [ ] **AC-6** Any path *outside* the allow-list raises a structured failure: the test fails-loud (Global Rule 12) with a diagnostic that contains (a) the violator list, (b) the literal phrase "either fit a bucket via ADR-0003 amendment or revert the change", and (c) the path to the bucket-classification map artifact (`/tmp/phase4-diff-paths.txt`). **Do not** silently extend the allow-list — that defeats the purpose of this story.
- [ ] **AC-7 (no-op skip on master)** When `HEAD == master` (or `git merge-base master HEAD == HEAD`), the diff is empty and the test `pytest.skip`s with a structured reason (`"running on master/empty-diff branch; nothing to gate"`). It does NOT pass vacuously and it does NOT error: skip means "trivially-correct no-op", failure is reserved for genuinely-pathological cases (detached HEAD, no merge-base resolvable).
- [ ] **AC-8 (vacuous-allow-list invariant)** A unit test `test_allowed_prefixes_are_non_empty_and_rooted` asserts every `ALLOWED_PREFIXES` entry is non-empty, does not equal `/`, and ends with `/`. A sibling test asserts `ALLOWED_EXACT` entries are all non-empty and contain no path separator at column 0. (Guards against a contributor "cleaning up" the constants into a vacuously-passing state.)
- [ ] **AC-9 (planted-violation table tests)** A pure helper `_classify(path: str, prefixes: Sequence[str], exact: frozenset[str]) -> bool` is extracted from the live diff-walk and table-tested with planted inputs:
  - Flagged as **outside**: `src/codegenie/probes/_dummy.py`, `src/codegenie/coordinator/_dummy.py`, `src/codegenie/cache/_dummy.py`, `src/codegenie/output/_dummy.py`, `src/codegenie/schema/repo_context.schema.json`, `src/codegenie/plugins/protocols.py` (kernel contract file).
  - Flagged as **inside**: `src/codegenie/fallback/leaf/anthropic_adapter.py`, `src/codegenie/rag/store.py`, `tests/unit/fallback/test_x.py`, `pyproject.toml`, `docs/phases/04-vuln-llm-fallback-rag/foo.md`.
  This is the mutation-resistance guard: a refactor that silently breaks the classifier (early `return True`) is caught even on a clean branch (Rule 9).
- [ ] **AC-10 (Phase-3 kernel contract files unmodified)** A test `test_phase_3_kernel_files_unmodified` iterates a `Final[tuple[Path, ...]]` of all eight Goal-G3-named surfaces and asserts `git diff "$(git merge-base master HEAD)..HEAD" -- <path>` returns empty for each:
  - **Directories** (any change inside is flagged): `src/codegenie/probes/`, `src/codegenie/coordinator/`, `src/codegenie/cache/`, `src/codegenie/output/`, `src/codegenie/schema/`.
  - **Specific contract files** (one file per protocol/ABC):
    - `src/codegenie/plugins/protocols.py` (`Plugin` Protocol)
    - `src/codegenie/transforms/recipe_engine.py` (`RecipeEngine` Protocol)
    - `src/codegenie/transforms/transform.py` (`Transform` ABC)
- [ ] **AC-11** `make check` clean.
- [ ] **AC-12** Story-attempt log records the full diff-walk output (path list with bucket assignment for every path, not just violators) so a reviewer can audit the empirical evidence without re-running the gate.

### Demoted to Notes for the implementer (was an AC; not test-verifiable as a one-off docstring line)

- `tests/fence/test_kernel_frozen.py`'s module docstring update with a one-line as-merged confirmation (e.g., `# Verified at Phase-4 Step-7 completion on 2026-MM-DD: diff range <sha>..<sha> touched <N> files, all inside allow-list.`) — see Notes for the implementer.
- Allow-list tightening proposals — see Notes for the implementer.

## Implementation outline

0. **Precondition check (S1-07 routing).** Confirm whether S1-07 has been re-authored and is GREEN. If yes, `tests/fence/test_kernel_frozen.py` includes the `phase-3` baseline row and AC-1 has full Phase-3 coverage. If no, proceed but flag `AC-1` in the attempt log as `deferred-phase-3-coverage` and ensure the S1-07 re-author is on the Phase-5 / Phase-7 follow-up backlog. **Do not** silently treat the deferred coverage as "covered."
1. Pull latest master; rebase the Step-7 branch onto master if needed.
2. Run `pytest tests/fence/test_kernel_frozen.py tests/property/test_plan_outcome_no_recipe_outcome_widening.py tests/fence/test_pyproject_fence_phase4.py tests/unit/test_pyproject_fence.py -v`. All four must be green. If any is red, **stop** — surface immediately per Global Rule 12; do not proceed.
3. Run `git diff --name-only "$(git merge-base master HEAD)..HEAD" | sort > /tmp/phase4-diff-paths.txt`. Inspect the file.
4. Walk each path through the pure `_classify` helper; record the bucket assignment for every path (not just violators) in the attempt log per AC-12. If any path doesn't fit, locate the introducing commit (`git log --oneline -- <path>`), inspect, and decide:
   - If the change is safe and additive (no kernel edit) AND fits an existing bucket once the bucket is broadened by ADR-0003 amendment, route via ADR amendment (not in this story).
   - If the change is a kernel edit, **revert it** and replace with an additive shape; do not extend the allow-list to cover it.
5. Run `git diff "$(git merge-base master HEAD)..HEAD" -- src/codegenie/plugins/protocols.py src/codegenie/transforms/transform.py src/codegenie/transforms/recipe_engine.py` and confirm each returns empty. If any is non-empty, revert per Step 4. (Note: `src/codegenie/orchestrator/` does **not** exist in the shipped tree; the contract files live at the explicit paths above.)
6. Update `tests/fence/test_kernel_frozen.py` module docstring with the as-merged confirmation line (manual hygiene step — see Notes; not test-verified).
7. If any sub-path can be tightened, document the proposal as a TODO inside the new `tests/fence/test_phase4_diff_within_allow_list.py` docstring (Phase-5 follow-up). Do **not** apply tightening in this story.
8. Run the full `make check` to confirm no test was broken by the verification.

## TDD plan — red / green / refactor

### Red — write the failing tests first

This story is the verification gate, not a code-change story. The "failing
tests" come in two shapes: (a) unit-table tests for the **pure** classifier
(planted-violation coverage; runs on every CI build, not just at merge time);
(b) integration tests that walk the actual diff (runs at Step-7 completion).
Land all of them as `tests/fence/test_phase4_diff_within_allow_list.py`:

```python
# tests/fence/test_phase4_diff_within_allow_list.py
"""Phase-4 final verification: every Phase-4 diff path is inside the kernel-frozen allow-list.

This module ships two complementary guards:

1. **Pure classifier unit tests** (always run): planted-violation table
   tests over ``_classify(path, prefixes, exact)`` ensure the classifier
   would catch a kernel edit even on a clean branch (Rule 9 — tests verify
   intent). Vacuous-allow-list invariant tests guard against a contributor
   setting ``ALLOWED_PREFIXES = ("",)`` and silently disabling the fence.

2. **Live diff-walk gate** (runs at Step-7 completion): walks
   ``git diff --name-only $(git merge-base master HEAD)..HEAD`` and asserts
   every path is inside the allow-list. Skips on master / empty-diff so CI
   on master itself does not spuriously fail.

The classifier is the *functional core*; the diff-walk is the *imperative
shell* (CLAUDE.md). The split exists so the classifier is unit-testable
without subprocess mocking.
"""
from __future__ import annotations

import subprocess
from collections.abc import Sequence
from typing import Final

import pytest


# ---------------------------------------------------------------------------
# Allow-list constants — Final so the type system enforces immutability.
# Adding a bucket is a one-row append (Open/Closed at the file boundary).
# ---------------------------------------------------------------------------

ALLOWED_PREFIXES: Final[tuple[str, ...]] = (
    "src/codegenie/fallback/",
    "src/codegenie/rag/",
    "plugins/vulnerability-remediation--node--npm/",
    "tests/",
    "docs/phases/04-vuln-llm-fallback-rag/",
)

ALLOWED_EXACT: Final[frozenset[str]] = frozenset({
    "pyproject.toml",
    "uv.lock",
    ".importlinter",
    "Makefile",
    "CODEOWNERS",
    ".codeowners",
    ".github/workflows/ci.yml",
    "docs/operations/secrets.md",
    "docs/operations/cassettes.md",
    "docs/operations/embeddings.md",
})

# The eight Goal-G3 untouchable surfaces. Five directories (any change inside
# is flagged); three explicit contract files (one per protocol/ABC).
PHASE3_FORBIDDEN_DIRS: Final[tuple[str, ...]] = (
    "src/codegenie/probes/",
    "src/codegenie/coordinator/",
    "src/codegenie/cache/",
    "src/codegenie/output/",
    "src/codegenie/schema/",
)
PHASE3_FORBIDDEN_FILES: Final[tuple[str, ...]] = (
    "src/codegenie/plugins/protocols.py",     # Plugin Protocol
    "src/codegenie/transforms/recipe_engine.py",  # RecipeEngine Protocol
    "src/codegenie/transforms/transform.py",  # Transform ABC
)


# ---------------------------------------------------------------------------
# Pure functional core
# ---------------------------------------------------------------------------


def _classify(
    path: str,
    prefixes: Sequence[str] = ALLOWED_PREFIXES,
    exact: frozenset[str] = ALLOWED_EXACT,
) -> bool:
    """Return True iff ``path`` is inside the allow-list (prefix or exact match).

    Pure: no I/O, no subprocess. Unit-testable directly with planted inputs.
    """
    if path in exact:
        return True
    return any(path.startswith(p) for p in prefixes)


# ---------------------------------------------------------------------------
# Imperative shell — subprocess wrappers
# ---------------------------------------------------------------------------


def _merge_base() -> str:
    return subprocess.check_output(
        ["git", "merge-base", "master", "HEAD"], text=True,
    ).strip()


def _phase4_diff_paths(base: str) -> list[str]:
    out = subprocess.check_output(
        ["git", "diff", "--name-only", f"{base}..HEAD"], text=True,
    )
    return [p for p in out.splitlines() if p]


def _head_sha() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True,
    ).strip()


# ---------------------------------------------------------------------------
# AC-8 — vacuous-allow-list invariant guard
# ---------------------------------------------------------------------------


def test_allowed_prefixes_are_non_empty_and_rooted() -> None:
    """Guard against ``ALLOWED_PREFIXES = ("",)`` silently disabling the fence."""
    for p in ALLOWED_PREFIXES:
        assert p, f"empty prefix in ALLOWED_PREFIXES would match every path"
        assert p != "/", "ALLOWED_PREFIXES entry '/' would match every absolute-shaped path"
        assert p.endswith("/"), (
            f"prefix {p!r} must end with '/' so 'src/codegenie/fallback' "
            f"does not accidentally match 'src/codegenie/fallback_other/'"
        )


def test_allowed_exact_entries_are_non_empty_files() -> None:
    for e in ALLOWED_EXACT:
        assert e, "empty entry in ALLOWED_EXACT"
        assert not e.startswith("/"), f"ALLOWED_EXACT entry must be repo-relative: {e!r}"
        assert "\n" not in e, f"ALLOWED_EXACT entry contains newline: {e!r}"


# ---------------------------------------------------------------------------
# AC-9 — planted-violation table tests (mutation-resistance)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,expected_inside",
    [
        # Planted violators — must be flagged as OUTSIDE the allow-list.
        ("src/codegenie/probes/_dummy.py", False),
        ("src/codegenie/coordinator/_dummy.py", False),
        ("src/codegenie/cache/_dummy.py", False),
        ("src/codegenie/output/_dummy.py", False),
        ("src/codegenie/schema/repo_context.schema.json", False),
        ("src/codegenie/plugins/protocols.py", False),  # Plugin Protocol — kernel contract
        ("src/codegenie/transforms/transform.py", False),  # Transform ABC
        ("src/codegenie/transforms/recipe_engine.py", False),  # RecipeEngine Protocol
        # Planted non-violators — must be flagged as INSIDE.
        ("src/codegenie/fallback/leaf/anthropic_adapter.py", True),
        ("src/codegenie/rag/store.py", True),
        ("tests/unit/fallback/test_x.py", True),
        ("pyproject.toml", True),
        ("uv.lock", True),
        (".importlinter", True),
        (".github/workflows/ci.yml", True),
        ("docs/phases/04-vuln-llm-fallback-rag/foo.md", True),
    ],
)
def test_classify_planted_violations(path: str, expected_inside: bool) -> None:
    """Rule 9 — every test must encode WHY the behavior matters.

    These planted inputs would fail if a contributor refactored ``_classify``
    into a vacuous ``return True`` or ``return False``. The fence is exercised
    on every CI build, not only on the once-per-phase Step-7 merge.
    """
    assert _classify(path) is expected_inside


# ---------------------------------------------------------------------------
# AC-5 / AC-6 / AC-7 — live diff-walk gate
# ---------------------------------------------------------------------------


def test_every_diff_path_inside_allow_list() -> None:
    base = _merge_base()
    if base == _head_sha():
        pytest.skip("running on master / empty-diff branch; nothing to gate")
    paths = _phase4_diff_paths(base)
    if not paths:
        pytest.skip("empty diff vs merge-base; nothing to gate")

    classification = {p: _classify(p) for p in paths}
    violations = [p for p, ok in classification.items() if not ok]

    assert not violations, (
        "Phase-4 final verification: paths outside the kernel-frozen allow-list:\n  - "
        + "\n  - ".join(violations)
        + "\n\nEither fit a bucket via ADR-0003 amendment or revert the change "
          "— do not silently widen ALLOWED_PREFIXES / ALLOWED_EXACT.\n"
        + f"Full bucket-classification map: write classification = {classification!r} "
          f"to /tmp/phase4-diff-paths.txt and inspect."
    )


# ---------------------------------------------------------------------------
# AC-10 — Phase-3 kernel contract surfaces unmodified
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("forbidden", PHASE3_FORBIDDEN_DIRS + PHASE3_FORBIDDEN_FILES)
def test_phase_3_kernel_surface_unmodified(forbidden: str) -> None:
    """Goal G3 — five kernel directories + three contract files must be untouched.

    Each path is asserted independently so a failure pinpoints the exact
    violated surface (Rule 12 — fail loud with diagnostic value).
    """
    base = _merge_base()
    if base == _head_sha():
        pytest.skip("running on master / empty-diff branch; nothing to gate")
    diff = subprocess.check_output(
        ["git", "diff", f"{base}..HEAD", "--", forbidden], text=True,
    )
    assert diff == "", (
        f"forbidden modification to kernel-frozen surface: {forbidden!r}\n"
        f"This path is locked by Goal G3 (arch §G3). Either revert the edit "
        f"or amend the kernel-frozen contract via an ADR (ADR-0003 / ADR-0004 "
        f"/ production-ADR-0031).\n\n{diff}"
    )
```

Run: `pytest tests/fence/test_phase4_diff_within_allow_list.py -v` — the
unit-table tests (`_classify`, vacuous-allow-list, planted violations) run
on every CI build; the live diff-walk + `test_phase_3_kernel_surface_unmodified`
fire at Step-7 merge time (skipping on master).

### Green — make it pass

If the diff-walk shows any path outside the allow-list (or any of the eight
Goal-G3 surfaces show drift), **revert the offending commit** — do not
silently widen the allow-list. If all tests pass, the verification is
complete.

### Refactor — clean up

- Run `pytest tests/fence/test_phase4_diff_within_allow_list.py -v` and
  paste the full output (every test, not just the live gate) into the
  attempt log per AC-12.
- Manually update `tests/fence/test_kernel_frozen.py`'s module docstring
  with the as-merged confirmation line (see Notes — this is hygiene, not
  test-verified).
- Re-run `make check` to confirm nothing else broke.
- **Do not** extract `ALLOWED_PREFIXES` / `ALLOWED_EXACT` to a shared module
  in this story — there is no second consumer yet (Phase 7 mirror would be
  the third use; until then Rule 2 / rule-of-three apply).

## Files to touch

| Path | Why |
|---|---|
| `tests/fence/test_phase4_diff_within_allow_list.py` | NEW — pure classifier + planted-violation table tests + live diff-walk gate + per-surface G3 unmodified checks. |
| `tests/fence/test_kernel_frozen.py` | Docstring-only update (as-merged confirmation line — manual hygiene step, not test-verified). |

> Deferred (rule-of-three): `tests/fence/_kernel_allow_list.py` extraction.
> Phase 7 would be the second consumer at most; wait for a third. Rule 2
> (Simplicity First) wins over speculative reuse.

## Out of scope

- Phase 7's own kernel-frozen verification — that ships in Phase 7 (mirror pattern).
- Tightening the allow-list (proposed as TODO, not applied in this story).
- Adversarial corpus (S7-09).
- Phase-5 contract snapshot refresh (S7-10).

## Notes for the implementer

- This story is **the merge gate** — it must run as the last verification in Step 7 before the branch is merged. Running it early (before S7-01 lands) catches nothing of structural interest. The unit-table tests (vacuous-allow-list, planted-violation classifier) DO run on every CI build from the moment the file lands, so the *classifier itself* gets continuous mutation-resistance coverage even before the merge.
- **S1-07 routing.** S1-07 is RESCUE (Phase-3 baseline row in `test_kernel_frozen.py` never landed). Two acceptable executor paths: (a) wait for S1-07 re-author + GREEN before running this story — AC-1 then has full Phase-3 coverage; (b) run this story now with the deferred-phase-3-coverage flag in the attempt log and route S1-07 re-author to a follow-up. Do not silently pretend AC-1 covers Phase 3 if S1-07 hasn't landed (Rule 12 — fail loud).
- **Where the contract files actually live** (verified against the shipped tree as of 2026-05-24):
  - `Plugin` Protocol → `src/codegenie/plugins/protocols.py:69`
  - `RecipeEngine` Protocol → `src/codegenie/transforms/recipe_engine.py:67`
  - `Transform` ABC → `src/codegenie/transforms/transform.py:64`
  - There is **no** `src/codegenie/orchestrator/` package in the shipped tree. `RemediationOrchestrator` is named in arch docs but Phase-3 orchestration is implemented across `plugins/registry.py`, `plugins/loader.py`, `transforms/transform_registry.py`, and per-plugin subgraph modules. Earlier drafts of this story pinned a non-existent `orchestrator/orchestrator.py` path; that pin would have passed vacuously. The corrected AC-10 pins the three real contract files explicitly.
- The temptation to silently widen the allow-list is real and is the single most common way this guard fails. Follow Global Rule 12: surface the violation explicitly; do not paper over it.
- If a violation surfaces, the default resolution is *not* "amend the allow-list with an ADR." It is "revert the offending commit and replace with an additive shape." The Phase-7 precondition is a contract with Phase 7's implementer (a future agent or human); they're relying on Phase 4 not having papered over its own kernel edits. The ADR-amendment route is the escape hatch for genuinely-cross-cutting changes — not the default.
- The Phase-0 fence file (`tests/unit/test_pyproject_fence.py`) is in the "unmodified" guard because S1-05 should have *added* the Phase-4 path-scoped fence as a new file (`tests/fence/test_pyproject_fence_phase4.py`), not edited the Phase-0 set. If S1-05 did edit Phase-0's set, that's a deviation from ADR-0003 — surface immediately.
- **`tests/fence/test_kernel_frozen.py` docstring update (manual hygiene step, demoted from AC).** Append a single line at the bottom of the module docstring along the lines of `# Verified at Phase-4 Step-7 completion on 2026-MM-DD: diff range <base>..<HEAD> touched <N> files, all inside allow-list.` This is paper trail, not test-verified — Rule 2 says don't build a regex test for a one-off docstring line.
- **Tightening proposals (demoted from AC).** If any allow-list bucket can be narrowed (e.g., Step-4's RAG store didn't actually need to write somewhere the bucket allows), record the proposal as a `# TODO(phase-5):` comment inside `tests/fence/test_phase4_diff_within_allow_list.py`. Do not apply tightening in this story — Phase 5 will pick up actionable proposals.
- The diff-walk runs against `git merge-base master HEAD`; if the branch was rebased recently, the merge-base might differ from what reviewers expect — the failure message includes both the base SHA and the HEAD SHA so the reviewer can reproduce locally.
- **Phase-7 mirror pattern (deferred extraction).** Phase 7 will ship its own diff-walk gate with the same shape (different prefixes/exact set, identical classifier). If a third sibling (e.g., Phase 11) appears with the same need, extract `ALLOWED_PREFIXES` / `ALLOWED_EXACT` / `_classify` to `tests/fence/_diff_allow_list.py` at *that* time (rule of three) and refactor the existing two consumers as the same commit. Do not preemptively extract — Rule 2 / Rule 11.
