# Story S1-07 — `test_kernel_frozen.py` Phase-3 baseline extension

**Step:** Step 1 — Establish Phase-4 type substrate + path-scoped fence amendment
**Status:** Done — GREEN 2026-05-25 (phase-story-executor; re-scoped per validator + executed in a single session — see [`_attempts/S1-07.md`](_attempts/S1-07.md)). 18 fence tests pass (4 new parametrized rows × 2 baselines + 1 docstring assertion); the live phase-3-baseline diff against HEAD is clean (no out-of-allowlist kernel edits since Phase 3 complete).
**Effort:** XS (one-row baseline append + pinned SHA file)
**Depends on:** S1-05 (Phase-4 fence amendment); Phase-3 complete (the SHA being pinned)
**ADRs honored:** ADR-0004 (`PlanOutcome` wraps `RecipeOutcome` — no Phase-3 sum-type widening; the kernel-frozen test is the structural backstop), ADR-0003 (path-scoped fence — kernel-frozen and fence-CI together compose the "no LLM in gather pipeline" invariant), `production/adrs/0031-plugin-architecture.md` (Phase-7 exit criterion — "diff touches only the new plugin directory" — this story lands the test that proves it for Phase 4), ADR-0011 (audit + lint framing — inherited from the shipped Phase-3 fence; no mechanism change)

## Validation re-scope (2026-05-25)

The original story prescribed a brand-new `tests/fence/test_kernel_frozen.py`
built on a BLAKE3 content-snapshot. That file already exists — Phase-3 S1-05
shipped it GREEN on 2026-05-18 as a **git-diff-against-baseline-SHA** fence with
a `_BASELINES: Final[tuple[tuple[str, Path], ...]]` extension seam. Per the
validator's recommended rewrite, Phase-4's contribution is a **one-row append**
to that seam plus a new pinned-SHA sidecar — no new mechanism, no generator
script, no BLAKE3 snapshot, no env-var skip.

### Re-scoped Goal

Extend the existing `tests/fence/test_kernel_frozen.py` so that the
parametrized fence suite also diffs the working tree against the **Phase-3**
kernel state. Concretely:

1. Append `("phase-3", Path("tests/fence/_phase3_baseline.txt"))` to the
   `_BASELINES` `Final` tuple (one-row extension).
2. Create `tests/fence/_phase3_baseline.txt` containing the 40-char SHA of the
   Phase-3-complete commit (`788512f570a0c34e37def129abd262c05de85855` —
   `feat(phase3/S6-04): land ADR-0015 resolver substrate`, the last
   Phase-3 source-code commit before Phase-4 work began).
3. Loop the live "no kernel edits" test over every baseline (not just
   `_BASELINES[0]`) so the Phase-3 row is actively exercised.
4. Update the module docstring + the helpful-error test to name both
   `_phase2_baseline.txt` and `_phase3_baseline.txt`.

The existing `_KERNEL_ALLOWLIST` is **not** widened — Phase-4 adds entirely
new top-level packages (`fallback/`, `rag/`, `workflows/`) that live outside
`_KERNEL_SCOPE_DIRS` and require no allow-list entry. The handful of Phase-4
edits to kernel files (`pyproject.toml`, `_fence.py`, `cli.py`,
`output/sanitizer.py`, `logging.py`, `types/*`) are already on the allow-list
from earlier Phase-4 stories.

### Re-scoped Acceptance criteria

- [ ] **AC-1.** `_BASELINES` contains exactly two rows after this change:
      `("phase-2", _phase2_baseline.txt)` and `("phase-3", _phase3_baseline.txt)`.
- [ ] **AC-2.** `tests/fence/_phase3_baseline.txt` contains exactly one
      40-char lowercase hex SHA — `788512f570a0c34e37def129abd262c05de85855`
      — terminated with a single newline (mirrors `_phase2_baseline.txt`).
- [ ] **AC-3.** The two existing parametrized tests
      (`test_baseline_file_is_a_real_40_char_sha`,
      `test_baseline_resolves_to_ancestor_of_head_and_is_not_head`) cover
      the new row automatically and pass.
- [ ] **AC-4.** A new parametrized test
      `test_no_kernel_edits_outside_allowlist[phase-3]` runs the live
      diff against the Phase-3 baseline and passes (no out-of-allowlist
      kernel edits since Phase 3 complete).
- [ ] **AC-5.** A planted-violation test (using the existing
      `_kernel_violations` helper with a fake diff) confirms that a
      hypothetical edit to a Phase-3 kernel file under
      `_KERNEL_SCOPE_DIRS` would be flagged when diffed against the
      Phase-3 baseline.
- [ ] **AC-6.** The module docstring + the helpful-error message name
      both `_phase2_baseline.txt` and `_phase3_baseline.txt`; the existing
      `test_module_docstring_names_adr_0011_framing_and_fetch_depth`
      assertion is extended to cover the Phase-3 baseline filename.

### Re-scoped Files to touch

- `tests/fence/test_kernel_frozen.py` (EDIT — append baseline row;
  generalize the live-diff test; add AC-5 planted-violation test; update
  docstring + helpful-error message).
- `tests/fence/_phase3_baseline.txt` (NEW — single 40-char SHA + newline).

### Re-scoped TDD plan

Red → Green → Refactor:

1. **Red.** Add the new baseline row and create `_phase3_baseline.txt`.
   The existing parametrized tests instantly cover the new row; the live
   diff test still uses `_BASELINES[0]` so it does not yet exercise
   Phase-3. Write the AC-4 generalization + AC-5 planted-violation test
   first — both fail because the live test only iterates over `[0]`.
2. **Green.** Refactor the live test to iterate over all `_BASELINES`
   rows (a parametrized form of the existing function). Run the suite;
   both new tests pass.
3. **Refactor.** Pull the docstring + helpful-error string out so both
   baseline filenames appear in one place; update
   `test_module_docstring_names_adr_0011_framing_and_fetch_depth` to
   assert both names. Re-run the suite.

### Re-scoped Out-of-scope

- BLAKE3 content snapshot mechanism (validator-rejected as duplication-by-addition).
- `scripts/regenerate_kernel_snapshot.py` and `_kernel_snapshot.json`
  (validator-rejected — the existing 40-char SHA file is the canonical
  baseline format).
- `_KERNEL_ALLOWLIST` extension (Phase-4 does not edit kernel files
  outside the already-allowlisted set).
- Subprocess-tree-copy mutation guard (parametrized test suite covers
  the equivalent failure mode for free).

## Context

ADR-0004's load-bearing invariant is "Phase-4 ships with **zero edits** to Phase 0/1/2/3 kernel files." The arch §Goal G3 names it explicitly: "Zero edits to `src/codegenie/{probes,coordinator,cache,output,schema,plugins/protocols.py}/`." The arch §Implementation-level risks #1 is even more specific: `tests/fence/test_kernel_frozen.py` "is a Step-1 deliverable, not a Step-7 one." Landing it now, in Step 1, means every subsequent Step 2–7 PR has its diff scanned against a committed kernel-content snapshot — a sneaky edit to a Phase-3 file slipped in during Steps 2–6 fails the gate immediately, not when the executor verifies at Step 7. This story is the structural fence that makes Phase 7's "extension by addition" exit criterion verifiable by merging.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals — G3` — "Zero edits to Phase 0/1/2/3 kernel files."
  - `../phase-arch-design.md §Testing strategy → CI gates` — `tests/fence/test_kernel_frozen.py` named explicitly.
  - `../phase-arch-design.md §Implementation-level risks §1` — "the test_kernel_frozen.py is a Step-1 deliverable, not a Step-7 one."
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0004-plan-outcome-wraps-recipe-outcome.md` — "`Phase 7's distroless plugin … does not add `case` arms anywhere in Phase 4/5 code"; the structural guarantee this story enforces.
  - `../ADRs/0003-path-scoped-fence-amendment.md` — kernel-frozen complements path-scoping: even if a new module under `src/codegenie/fallback/` lands, the kernel paths stay untouched.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` — "extension by addition; no plugin edits kernel."
  - `../../../production/adrs/0007-probe-contract-preserved-poc-to-service.md` — probe contract stability.
- **Source design:**
  - `../final-design.md §Three load-bearing structural lines` item 3 — "no edits to the kernel."
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - Determine the exact set of "kernel files" the snapshot must cover. From the arch + final-design + the load-bearing commitments:
    - **Directory closures (file lists frozen):** `src/codegenie/probes/`, `src/codegenie/coordinator/`, `src/codegenie/cache/`, `src/codegenie/output/`, `src/codegenie/schema/`.
    - **Specific files (byte-for-byte snapshot):** `src/codegenie/plugins/protocols.py` (the `Plugin` / `RecipeEngine` Protocol), `src/codegenie/transforms/` (the `Transform` ABC), the `RemediationOrchestrator` (find its module via Rule 8 — likely `src/codegenie/orchestrator/` or similar), the canonical `RecipeOutcome` definition (location discovered in S1-03's READ-BEFORE-WRITING).
  - `tests/property/_recipe_outcome_phase3_snapshot.txt` (S1-03) — adjacent fence; this story snapshots more than just variant names.
  - Existing snapshot-style tests in the repo if any (look for `_snapshot.txt` files under `tests/`).

## Goal

Land `tests/fence/test_kernel_frozen.py` + an adjacent `_kernel_snapshot.json` committed alongside, capturing the BLAKE3 digest of every kernel file in scope so any byte-edit during Phases 2–7 fires a high-signal diff-naming diagnostic.

## Acceptance criteria

### Snapshot landed

- [ ] AC-1 — `tests/fence/_kernel_snapshot.json` committed with this exact shape:
  ```json
  {
    "version": "phase-4-step-1",
    "generated_at": "2026-05-18T00:00:00Z",
    "directory_closures": {
      "src/codegenie/probes/": {"file_count": <int>, "tree_digest": "<blake3-hex>"},
      "src/codegenie/coordinator/": {"file_count": <int>, "tree_digest": "<blake3-hex>"},
      "src/codegenie/cache/": {"file_count": <int>, "tree_digest": "<blake3-hex>"},
      "src/codegenie/output/": {"file_count": <int>, "tree_digest": "<blake3-hex>"},
      "src/codegenie/schema/": {"file_count": <int>, "tree_digest": "<blake3-hex>"}
    },
    "files": {
      "src/codegenie/plugins/protocols.py": "<blake3-hex of file bytes>",
      "<RecipeOutcome canonical module>": "<blake3-hex>",
      "<RemediationOrchestrator module>": "<blake3-hex>",
      "<Transform ABC module>": "<blake3-hex>"
    }
  }
  ```
  - `tree_digest` is BLAKE3 over the canonical concatenation `for each file in sorted(rglob("*.py")) under directory: b"\x00" + relpath.encode() + b"\x00" + file_bytes` — order-stable, content-addressed.
  - The file paths in `files` are resolved at story-implementation time per Rule 8 (the implementer reads the source, finds the canonical homes, records them).
- [ ] AC-2 — A generator script `scripts/regenerate_kernel_snapshot.py` ships **as part of this story** that produces `_kernel_snapshot.json` from the current source tree. The script accepts `--write` to commit-update and prints a diff otherwise. The Phase-4 attempt log uses this script to refresh the snapshot if an explicit ADR amendment is needed (no silent updates).

### Test

- [ ] AC-3 — `tests/fence/test_kernel_frozen.py` ships these assertions:
  1. **Directory closure digest match.** For each entry under `directory_closures`, the test recomputes `tree_digest` over the current source and compares against the committed snapshot. Mismatch fails with a diagnostic naming the directory + the closest-changed file (the AST-walk identifies which file's hash drifted).
  2. **File count match.** Per directory, `file_count` matches the committed value. (A new file in `src/codegenie/probes/` fires this assertion separately from `tree_digest`.)
  3. **Specific-file digest match.** For each entry under `files`, the test recomputes BLAKE3 over the file bytes and compares against the committed value.
- [ ] AC-4 — Each failure diagnostic names:
  - The kernel-frozen invariant that was broken.
  - ADR-0004 (`PlanOutcome wraps RecipeOutcome`) **and** the production ADR-0031 (plugin architecture).
  - The remediation path: `"If this edit is intentional, the change is out of scope for Phase 4 and requires an ADR amendment + snapshot refresh via scripts/regenerate_kernel_snapshot.py"`.
- [ ] AC-5 — The test is **opt-in skippable only via env var `CODEGENIE_KERNEL_SNAPSHOT_REGENERATE=1`**. Skipping silently inside the test body is forbidden; the env-var-skipped state prints a loud `pytest.skip("kernel snapshot regeneration mode — review the diff carefully and commit the updated _kernel_snapshot.json")` so CI never accidentally allows the skip.

### Verification — mutation guard

- [ ] AC-6 — `tests/fence/test_kernel_frozen_mutation_guard.py` ships a parametrized test that:
  1. Copies the source tree to a `tmp_path`.
  2. For each kernel file in scope (one parametrized case per file), appends a single-byte modification (e.g., a trailing comment line).
  3. Re-runs the test_kernel_frozen logic against the `tmp_path` + the original snapshot.
  4. Asserts the test fails with a diagnostic naming the modified file.
- [ ] AC-7 — The mutation guard covers **at minimum** one file per directory closure + every specific-file entry — i.e., five directory-edit cases (one per closure) + four file-edit cases (one per files entry).

### Verification — current source is green

- [ ] AC-8 — `tests/fence/test_kernel_frozen.py` exits 0 against the current source tree (the committed snapshot matches the current state at story-completion time).
- [ ] AC-9 — `make check` green. `ruff check`, `ruff format --check`, `mypy --strict` clean on touched files.
- [ ] AC-10 — The TDD plan's red tests exist, are committed, and are green.

## Implementation outline

1. **Discover canonical kernel paths (Rule 8).** Find the exact module locations for:
   - `RecipeOutcome` (S1-03 already discovered this — use the same path).
   - `RemediationOrchestrator` (likely `src/codegenie/orchestrator/` or `src/codegenie/coordinator/` — confirm).
   - `Transform` ABC (likely `src/codegenie/transforms/transform.py` — confirm).
   - `plugins/protocols.py` (`Plugin` and `RecipeEngine` Protocols).
2. **Land `scripts/regenerate_kernel_snapshot.py`** — a small utility that walks the kernel paths, computes BLAKE3, and writes `tests/fence/_kernel_snapshot.json` in the AC-1 shape.
3. **Run the script** to produce the initial `_kernel_snapshot.json`.
4. **Land `tests/fence/test_kernel_frozen.py`** with the three AC-3 assertions and the AC-4 diagnostic shape.
5. **Land `tests/fence/test_kernel_frozen_mutation_guard.py`** with parametrized single-byte-edit cases.
6. **Verify**: `make check` green; the mutation guard tests all fail in the synthetic-edit cases and pass in the no-edit case.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/fence/test_kernel_frozen.py`

```python
"""ADR-0004 / production ADR-0031 / arch §Goal G3 — Phase 4 ships zero edits to
the Phase 0/1/2/3 kernel. Fails loud if any file in `_kernel_snapshot.json`
drifts from its committed digest.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest
from blake3 import blake3  # already a project dep

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = pathlib.Path(__file__).parent / "_kernel_snapshot.json"

_REGENERATE_ENV = "CODEGENIE_KERNEL_SNAPSHOT_REGENERATE"
_REMEDIATION = (
    "If this edit is intentional, the change is out of scope for Phase 4 and "
    "requires an ADR amendment + snapshot refresh via "
    "scripts/regenerate_kernel_snapshot.py. See ADR-0004 (this phase) + "
    "production ADR-0031 (plugin architecture)."
)


def _load_snapshot() -> dict:
    return json.loads(SNAPSHOT_PATH.read_text())


def _tree_digest(root: pathlib.Path) -> tuple[int, str]:
    files = sorted(root.rglob("*.py"))
    h = blake3()
    for f in files:
        rel = f.relative_to(REPO_ROOT).as_posix().encode()
        h.update(b"\x00" + rel + b"\x00" + f.read_bytes())
    return len(files), h.hexdigest()


def _file_digest(path: pathlib.Path) -> str:
    return blake3(path.read_bytes()).hexdigest()


@pytest.fixture(autouse=True)
def _refuse_silent_skip() -> None:
    if os.environ.get(_REGENERATE_ENV) == "1":
        pytest.skip(
            "kernel snapshot regeneration mode — review the diff carefully and "
            "commit the updated _kernel_snapshot.json"
        )


def test_directory_closures_unchanged() -> None:
    snap = _load_snapshot()
    drifts: list[str] = []
    for rel, expected in snap["directory_closures"].items():
        root = REPO_ROOT / rel.rstrip("/")
        file_count, tree_digest = _tree_digest(root)
        if file_count != expected["file_count"]:
            drifts.append(
                f"{rel} file_count changed: expected {expected['file_count']}, "
                f"got {file_count}"
            )
        if tree_digest != expected["tree_digest"]:
            drifts.append(
                f"{rel} tree_digest changed: expected "
                f"{expected['tree_digest'][:12]}..., got {tree_digest[:12]}..."
            )
    assert not drifts, (
        f"Phase 0/1/2/3 kernel drifted from Phase-4 snapshot.\n"
        f"{chr(10).join(drifts)}\n{_REMEDIATION}"
    )


def test_specific_files_unchanged() -> None:
    snap = _load_snapshot()
    drifts: list[str] = []
    for rel, expected_digest in snap["files"].items():
        path = REPO_ROOT / rel
        if not path.exists():
            drifts.append(f"{rel} was DELETED — kernel removal is out of scope for Phase 4")
            continue
        actual = _file_digest(path)
        if actual != expected_digest:
            drifts.append(
                f"{rel} content changed: expected {expected_digest[:12]}..., "
                f"got {actual[:12]}..."
            )
    assert not drifts, (
        f"Phase 0/1/2/3 kernel file drifted from Phase-4 snapshot.\n"
        f"{chr(10).join(drifts)}\n{_REMEDIATION}"
    )
```

The mutation guard:

```python
# tests/fence/test_kernel_frozen_mutation_guard.py
"""Mutation guard for test_kernel_frozen.py — appending a byte to any kernel
file must fire the diagnostic. Tests the test."""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SNAPSHOT = REPO_ROOT / "tests/fence/_kernel_snapshot.json"


def _snapshot_paths() -> tuple[list[str], list[str]]:
    snap = json.loads(SNAPSHOT.read_text())
    return list(snap["directory_closures"].keys()), list(snap["files"].keys())


DIRS, FILES = _snapshot_paths()


@pytest.mark.parametrize("dir_rel", DIRS)
def test_appending_to_any_file_in_directory_closure_fires(tmp_path, dir_rel):
    # Copy the kernel + snapshot to tmp; perturb one .py file; assert the test fails.
    work = tmp_path / "work"
    shutil.copytree(REPO_ROOT / "src", work / "src")
    shutil.copytree(REPO_ROOT / "tests/fence", work / "tests/fence")

    target_dir = work / dir_rel.rstrip("/")
    py_files = sorted(target_dir.rglob("*.py"))
    assert py_files, f"No .py files under {dir_rel} to perturb"
    perturb_target = py_files[0]
    perturb_target.write_bytes(perturb_target.read_bytes() + b"\n# perturbed\n")

    # Run the kernel-frozen test against the perturbed tree.
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-x", "-q",
         str(work / "tests/fence/test_kernel_frozen.py::test_directory_closures_unchanged")],
        capture_output=True, text=True, cwd=work,
        env={"PYTHONPATH": str(work / "src"), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode != 0, (
        f"Mutation guard did not fire on {dir_rel}: stdout={result.stdout}"
    )


@pytest.mark.parametrize("file_rel", FILES)
def test_appending_to_specific_file_fires(tmp_path, file_rel):
    work = tmp_path / "work"
    shutil.copytree(REPO_ROOT / "src", work / "src")
    shutil.copytree(REPO_ROOT / "tests/fence", work / "tests/fence")

    target = work / file_rel
    target.write_bytes(target.read_bytes() + b"\n# perturbed\n")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-x", "-q",
         str(work / "tests/fence/test_kernel_frozen.py::test_specific_files_unchanged")],
        capture_output=True, text=True, cwd=work,
        env={"PYTHONPATH": str(work / "src"), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode != 0, (
        f"Mutation guard did not fire on {file_rel}: stdout={result.stdout}"
    )
```

The regenerator script:

```python
# scripts/regenerate_kernel_snapshot.py
"""Regenerate tests/fence/_kernel_snapshot.json. Use ONLY with an ADR amendment.

CLI:
  python scripts/regenerate_kernel_snapshot.py        # dry-run (prints diff)
  python scripts/regenerate_kernel_snapshot.py --write  # commit
"""
from __future__ import annotations

import argparse
import json
import pathlib
from datetime import UTC, datetime

from blake3 import blake3

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SNAPSHOT = REPO_ROOT / "tests/fence/_kernel_snapshot.json"

DIRECTORY_CLOSURES = [
    "src/codegenie/probes/",
    "src/codegenie/coordinator/",
    "src/codegenie/cache/",
    "src/codegenie/output/",
    "src/codegenie/schema/",
]
# Discovered at story-implementation time per Rule 8.
SPECIFIC_FILES = [
    "src/codegenie/plugins/protocols.py",
    # "<RecipeOutcome canonical module>",
    # "<RemediationOrchestrator module>",
    # "<Transform ABC module>",
]


def _tree_digest(root: pathlib.Path) -> tuple[int, str]:
    files = sorted(root.rglob("*.py"))
    h = blake3()
    for f in files:
        rel = f.relative_to(REPO_ROOT).as_posix().encode()
        h.update(b"\x00" + rel + b"\x00" + f.read_bytes())
    return len(files), h.hexdigest()


def _build() -> dict:
    dc = {}
    for rel in DIRECTORY_CLOSURES:
        n, d = _tree_digest(REPO_ROOT / rel.rstrip("/"))
        dc[rel] = {"file_count": n, "tree_digest": d}
    files = {}
    for rel in SPECIFIC_FILES:
        files[rel] = blake3((REPO_ROOT / rel).read_bytes()).hexdigest()
    return {
        "version": "phase-4-step-1",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "directory_closures": dc,
        "files": files,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--write", action="store_true")
    args = p.parse_args()
    fresh = _build()
    if args.write:
        SNAPSHOT.write_text(json.dumps(fresh, indent=2, sort_keys=True) + "\n")
        print(f"wrote {SNAPSHOT}")
    else:
        existing = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else {}
        if existing == fresh:
            print("snapshot is up to date")
        else:
            print("DIFF detected — re-run with --write to commit. Be sure an ADR amendment is in flight.")


if __name__ == "__main__":
    main()
```

State why it fails: the snapshot file doesn't exist; the regenerator hasn't been run.

### Green — make it pass

1. Discover the canonical kernel paths via Rule 8 reading; fill `SPECIFIC_FILES` in the regenerator.
2. Run `python scripts/regenerate_kernel_snapshot.py --write` to commit the initial snapshot.
3. Verify `test_kernel_frozen.py` exits 0.
4. Run the mutation-guard tests; verify all parametrized cases fail in the synthetic-edit cases.

### Refactor — clean up

- Module docstring naming ADR-0004 + production ADR-0031 explicitly.
- The diagnostic message format is the load-bearing fail-loud control (Rule 12). Keep it under ~6 lines so it shows up cleanly in CI logs.
- Edge cases enumerated in arch §Edge cases that touch this code: none directly; this story is the structural backstop for every other edge case that touches kernel paths.
- Confirm `_kernel_snapshot.json` ends with a newline and is sorted-keys formatted (deterministic across regenerations).

## Files to touch

| Path | Why |
|---|---|
| `tests/fence/_kernel_snapshot.json` | NEW — committed snapshot of kernel file digests. |
| `tests/fence/test_kernel_frozen.py` | NEW — three AC-3 assertions + AC-5 env-var skip + AC-4 diagnostic. |
| `tests/fence/test_kernel_frozen_mutation_guard.py` | NEW — parametrized synthetic-edit cases (mutation guard for the live test). |
| `scripts/regenerate_kernel_snapshot.py` | NEW — generator utility; CLI for `--write` vs. dry-run. |

## Out of scope

- **Adding new files under `src/codegenie/fallback/` or `src/codegenie/rag/`** — handled by later Step 1 stories (S1-02, S1-03, S1-04 land code there). Those paths are NOT in the kernel snapshot — they're Phase-4-new.
- **Snapshotting plugin directories** — `plugins/vulnerability-remediation--node--npm/` already has Phase-4 work (S6-04 `tsc` allowlist, S7-01 plugin adapter); not in the snapshot.
- **Re-running snapshot regeneration on each merge** — manual ADR-amendment trigger only.
- **`tests/fence/test_phase4_no_raw_str_for_domain_ids.py`** — S1-01 (AST source-scan; different fence).
- **Path-scoped fence test** — S1-05.
- **import-linter contracts** — S1-06.

## Notes for the implementer

- **Discover the specific-file paths via Rule 8 BEFORE running the regenerator.** The four file paths in `SPECIFIC_FILES` must be the canonical homes:
  - `src/codegenie/plugins/protocols.py` — `Plugin` + `RecipeEngine` Protocol.
  - `RecipeOutcome` — discovered in S1-03 (e.g., `src/codegenie/plugins/protocols.py` or `src/codegenie/transforms/recipe_outcome.py`). If `RecipeOutcome` lives in `protocols.py` already, the path is the same and the digest covers both — that's fine.
  - `RemediationOrchestrator` — search for its class definition (`grep -r "class RemediationOrchestrator"`).
  - `Transform` ABC — search for `class Transform` or `class Transform(ABC)`.
- **The directory closures are file-list-and-content snapshots.** Adding a new `.py` file to `src/codegenie/probes/` fires AC-3 (1) (file_count mismatch) and AC-3 (1) (tree_digest mismatch) — both diagnostics flag it. This is intentional: Phase 4 does NOT add probes.
- **The `_REGENERATE_ENV` skip is for the regenerator script run only.** Never set this in CI. The local workflow is: (a) write an ADR amendment justifying the kernel edit; (b) run `scripts/regenerate_kernel_snapshot.py --write`; (c) commit the new snapshot in the same PR as the ADR amendment; (d) reviewer sees the snapshot diff alongside the ADR. AC-5's "review the diff carefully" message is the user-facing hint.
- **The mutation guard tests run `pytest` in a subprocess against a copied tree.** This is deliberately slow (one subprocess per case) but it's the only way to verify the fail-loud contract; the test runs in CI per `make check` but is gated by the `bench` marker if a perf-aware contributor wants to skip locally (consider `@pytest.mark.adv` or similar — surface per repo convention).
- **BLAKE3 is already a project dep** (per Phase-2 ADR-0006); no new dep introduction needed.
- **`scripts/` may not exist yet** — create the directory + `__init__.py` if absent. The repo convention is to keep CLI scripts in `scripts/` (verify by reading the `Makefile` and any existing `scripts/` references).
- **Fail-loud diagnostic structure (Rule 12).** A kernel-frozen failure must read like: "Phase 0/1/2/3 kernel drifted from Phase-4 snapshot. `src/codegenie/probes/foo.py` tree_digest changed: expected aabbccdd..., got eeff1122.... If this edit is intentional, the change is out of scope for Phase 4 and requires an ADR amendment + snapshot refresh." The next reader sees the file, the digest delta, the ADR, and the remediation in one frame.
- **This test runs in every Phase-4 PR including Steps 2–7.** A sneaky edit in any of those steps (e.g., a Phase-3 file silently touched during S6-05's `@register_signal_kind` introduction) fires here, not at S7-08's final verification. That's the whole point of landing it Step 1 (arch §Implementation-level risks #1).
- **The arch's "Implementation-level risks #1" framing is load-bearing.** Quote it verbatim in the module docstring: "this test is a Step-1 deliverable, not a Step-7 one." The next reader sees the strategic placement and understands why.
