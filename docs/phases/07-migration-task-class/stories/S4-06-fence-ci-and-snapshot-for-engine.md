# Story S4-06 — Fence-CI synthetic-PR + snapshot regen for `Recipe.engine` extension

**Step:** Step 4 — Land `DockerfileRecipeEngine`, `DockerfileBaseImageSwapTransform`, and the multi-stage refactor recipe
**Status:** Ready
**Effort:** S
**Depends on:** S1-08, S4-02
**ADRs honored:** ADR-P7-001 (six named seams), ADR-P7-006 (`Recipe.engine` Literal extension), ADR-P7-009 (contract-surface snapshot canary)

## Context

This story closes Step 4 by proving that the Phase 7 *enforcement mechanisms* fire correctly on the new code Step 4 just landed. Two mechanisms are exercised:

1. **Fence-CI deny-imports under `recipes/` and `transforms/`** (from S1-08) — a synthetic PR that imports `anthropic` under `src/codegenie/recipes/` is rejected by CI.
2. **Snapshot canary + `snapshot_regen_audit.py`** (from S1-07 + S1-08) — the `Recipe.engine` Literal extension (S1-05) flows through `tools/contract-surface.snapshot.json` and `snapshot_regen_audit` requires the ADR-P7-006 link in the PR body to accept the regen.

If either mechanism is silently broken, every later step's "extension by addition" claim is convention, not enforcement. This story is small but load-bearing: it's the first end-to-end exercise of the two CI gates Step 1 promised.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design ›10. Contract-surface snapshot canary` — what the snapshot covers; how `--update-contract-snapshot` works.
  - `../phase-arch-design.md §Testing strategy ›CI gates` rows 9, 10 — fence-CI, snapshot canary regen audit.
  - `../phase-arch-design.md §Scenarios ›Scenario 4` — the cross-task regression scenario the canary defends.
  - `../phase-arch-design.md §Gap 5` — the snapshot-regen-audit mechanism.
- **Phase ADRs:**
  - `../ADRs/0001-six-named-additive-seams-and-adr-0028-amendment.md` — ADR-P7-001 — the six seams; this story closes Step 4's contribution to that list.
  - `../ADRs/0007-recipe-engine-literal-extended-with-dockerfile.md` — ADR-P7-006 — the Literal extension whose snapshot diff flows through this story.
  - `../ADRs/0009-contract-surface-snapshot-canary.md` — ADR-P7-009 — the canary mechanism this story exercises.
- **Production ADRs:**
  - `../../../production/adrs/0028-task-class-introduction-order.md` — the amended ADR-0028 names ADR-P7-009 as the enforcement mechanism for "extension by addition."
- **Existing code:**
  - `tools/contract-surface.snapshot.json` — landed in S1-07.
  - `tools/snapshot_regen_audit.py` — landed in S1-08.
  - `.github/workflows/fence_ci.yaml` (or equivalent) — landed in S1-08 with the deny-imports extension.
  - `tests/integration/test_contract_surface_snapshot.py` — landed in S1-07.
  - `src/codegenie/recipes/contract.py` — touched in S1-05 to add `"dockerfile"` to the `Recipe.engine` Literal.

## Goal

A synthetic PR that imports `anthropic` under `src/codegenie/recipes/` is *rejected* by fence-CI; and the `Recipe.engine` Literal extension (already in the snapshot from S1-07) is verified to flow through `snapshot_regen_audit.py` with a PR body that mentions ADR-P7-006 — and rejected when the ADR link is missing.

## Acceptance criteria

- [ ] `tests/integration/test_fence_ci_rejects_anthropic_under_recipes.py` exists and runs the fence-CI tool (or its in-process equivalent) against a synthetic file `tests/fixtures/synthetic_pr/anthropic_under_recipes.py` whose top-line is `import anthropic`. The test asserts the fence-CI tool exits non-zero and the error message names `anthropic` and `recipes/`.
- [ ] The synthetic-PR fixture file is *not* under `src/codegenie/recipes/` itself (so it doesn't poison the real codebase); it is under `tests/fixtures/synthetic_pr/` and the test invokes fence-CI on it as if it were at `src/codegenie/recipes/forbidden.py`.
- [ ] `tests/integration/test_fence_ci_rejects_anthropic_under_transforms.py` parallels the above for `src/codegenie/transforms/` — proves the deny-list covers transforms too (S4-03's surface).
- [ ] `tests/integration/test_snapshot_regen_audit_accepts_adr_p7_006_link.py` exists; runs `tools/snapshot_regen_audit.py` against a synthetic PR body containing "Implements ADR-P7-006" + a snapshot-diff that touches the `Recipe.engine` Literal; asserts exit code 0.
- [ ] `tests/integration/test_snapshot_regen_audit_rejects_unlinked_regen.py` exists; runs the audit tool against a PR body with *no* ADR reference but the same snapshot diff; asserts exit code non-zero and the error message names "ADR-".
- [ ] `tests/integration/test_contract_surface_snapshot.py` (from S1-07) is *still* green after Step 4's new files land — proves the engine + transform additions did not drift the snapshot (they shouldn't, because they're additive new files, not edits to snapshotted surfaces).
- [ ] The fence-CI test covers all four scoped directories named in ADR-P7-009 (`probes/`, `transforms/`, `recipes/`, `catalogs/`) — at least one test per directory.
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on the four new test files.

## Implementation outline

1. Read `tools/snapshot_regen_audit.py` (S1-08) and the fence-CI config (S1-08) — understand the public surface each exposes (CLI args, exit codes, error message format).
2. Create `tests/fixtures/synthetic_pr/`:
   - `anthropic_under_recipes.py` — one-line: `import anthropic`.
   - `chromadb_under_transforms.py` — one-line: `import chromadb`.
   - `sentence_transformers_under_probes.py` — one-line: `from sentence_transformers import SentenceTransformer`.
   - `anthropic_under_catalogs.py` — one-line: `import anthropic`.
3. Author `tests/integration/test_fence_ci_rejects_anthropic_under_recipes.py` (and three parallel tests for transforms / probes / catalogs):
   - Invoke fence-CI on the synthetic file, asking it to treat the file as if at `src/codegenie/recipes/forbidden.py`.
   - Assert non-zero exit + error message contains `anthropic` and `recipes/`.
4. Author `tests/integration/test_snapshot_regen_audit_accepts_adr_p7_006_link.py`:
   - Build a synthetic PR body string (`Implements ADR-P7-006 (...)`) and a synthetic snapshot-diff (any non-empty diff under `tools/contract-surface.snapshot.json`).
   - Invoke `tools/snapshot_regen_audit.py` with both; assert exit code 0.
5. Author `tests/integration/test_snapshot_regen_audit_rejects_unlinked_regen.py`:
   - Same diff, PR body without ADR reference.
   - Assert non-zero exit + error mentions ADR.
6. Re-run `tests/integration/test_contract_surface_snapshot.py` from S1-07 to confirm it still passes against the post-Step-4 codebase.
7. Document in each test docstring *why* (per Rule 9): each test encodes the load-bearing enforcement claim.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/test_fence_ci_rejects_anthropic_under_recipes.py`

```python
# tests/integration/test_fence_ci_rejects_anthropic_under_recipes.py
SYNTHETIC = Path("tests/fixtures/synthetic_pr/anthropic_under_recipes.py")

def test_fence_ci_rejects_anthropic_under_recipes(tmp_path):
    """If this fails, an autonomous PR could import anthropic under recipes/ and
    the deny-imports CI gate (S1-08) silently passes — every later G18 claim
    becomes convention, not enforcement."""
    # arrange: treat the synthetic file as if it were committed under recipes/
    target = tmp_path / "src/codegenie/recipes/forbidden.py"
    target.parent.mkdir(parents=True)
    target.write_bytes(SYNTHETIC.read_bytes())

    # act
    result = subprocess.run(
        ["python", "-m", "tools.fence_ci", "--check", str(tmp_path)],
        capture_output=True, text=True,
    )

    # assert
    assert result.returncode != 0
    assert "anthropic" in result.stderr
    assert "recipes/" in result.stderr
```

Parallel red test for snapshot-regen-audit:

```python
def test_snapshot_regen_audit_rejects_unlinked_regen(tmp_path):
    """If this fails, snapshot regenerations slip through without an ADR link —
    extension-by-addition reverts to convention."""
    # arrange: synthetic PR body with no ADR; a snapshot diff
    body = "Generic refactor that happens to touch the snapshot."
    diff_file = tmp_path / "diff.patch"
    diff_file.write_text("--- a/tools/contract-surface.snapshot.json\n+++ b/tools/contract-surface.snapshot.json\n@@ ...\n")

    # act
    result = subprocess.run(
        ["python", "tools/snapshot_regen_audit.py", "--pr-body", body, "--diff", str(diff_file)],
        capture_output=True, text=True,
    )

    # assert
    assert result.returncode != 0
    assert "ADR" in result.stderr
```

Run. They fail because either the synthetic fixtures don't exist yet or because the tooling under `tools/fence_ci` / `tools/snapshot_regen_audit.py` doesn't expose the CLI shape the test invokes. If the latter, *that's* the bug — surface it back to S1-08 rather than working around it.

### Green — make it pass

- Add the synthetic-fixture files under `tests/fixtures/synthetic_pr/` (each one line, no other content).
- Author the four fence-CI tests (one per scoped directory). Re-use a common helper to keep them small.
- Author the two snapshot-regen-audit tests.
- Confirm `tests/integration/test_contract_surface_snapshot.py` is still green.

### Refactor — clean up

- Extract a `_run_fence_ci(repo_root: Path)` helper into a `conftest.py` if duplication is meaningful across the four fence-CI tests.
- Each test's docstring states the WHY: what breaks if the test passes when it shouldn't.
- Confirm the synthetic fixtures are *only* under `tests/fixtures/synthetic_pr/`, never imported by real code — fence-CI must not be confused by self-tests.
- Add a one-line note in `tests/fixtures/synthetic_pr/README.md` documenting that these files are *intentional fixture violations* and should never be moved into the main src tree.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/synthetic_pr/anthropic_under_recipes.py` | New — one-line synthetic violation. |
| `tests/fixtures/synthetic_pr/chromadb_under_transforms.py` | New — one-line synthetic violation. |
| `tests/fixtures/synthetic_pr/sentence_transformers_under_probes.py` | New — one-line synthetic violation. |
| `tests/fixtures/synthetic_pr/anthropic_under_catalogs.py` | New — one-line synthetic violation. |
| `tests/fixtures/synthetic_pr/README.md` | Short note that these files are intentional. |
| `tests/integration/test_fence_ci_rejects_anthropic_under_recipes.py` | New — anchors TDD red phase. |
| `tests/integration/test_fence_ci_rejects_chromadb_under_transforms.py` | New — parallel test. |
| `tests/integration/test_fence_ci_rejects_sentence_transformers_under_probes.py` | New — parallel test. |
| `tests/integration/test_fence_ci_rejects_anthropic_under_catalogs.py` | New — parallel test. |
| `tests/integration/test_snapshot_regen_audit_accepts_adr_p7_006_link.py` | New — happy path for ADR-linked regen. |
| `tests/integration/test_snapshot_regen_audit_rejects_unlinked_regen.py` | New — rejection path. |

## Out of scope

- **The fence-CI tool itself.** — landed in S1-08; this story consumes it.
- **The `snapshot_regen_audit.py` tool itself.** — landed in S1-08; this story consumes it.
- **Re-running the synthetic fence-CI rejection on real GitHub Actions.** — handled by story S7-06 (real CI-level synthetic-PR rejection).
- **`Recipe.engine` Literal extension itself.** — landed in S1-05; this story verifies the *snapshot flow*, not the Literal change.
- **The contract-surface snapshot's content.** — landed in S1-07; this story re-asserts post-Step-4 stability but does not edit the snapshot.
- **Generic CI-flake handling.** — out of scope.

## Notes for the implementer

- The fence-CI tool's exact CLI shape (`python -m tools.fence_ci --check <path>` vs another invocation) depends on what S1-08 shipped. *Read S1-08's deliverables first* (per Rule 8). If the CLI is different, conform to it; if it's missing a documented behavior, surface back to S1-08 — do not invent it here.
- The synthetic fixture files must be `.py` files (so fence-CI's AST/import scanner sees them) but they should *not* be importable as part of the real package (so they don't accidentally load `anthropic` at test-collect time). Easiest path: keep them under `tests/fixtures/synthetic_pr/` which is not on the package `__init__`.
- Per Rule 12, each test must *actually fail* if the underlying mechanism is broken. If the fence-CI tool quietly does nothing when given a bad path, the test passes vacuously — assert on stdout/stderr content too, not just exit code.
- Per Rule 9, each test's docstring must state the WHY. The pattern: "If this passes when it shouldn't, X happens." Make X concrete (e.g., "an autonomous PR ships `import anthropic` under `recipes/` and zero-LLM-tokens-in-Phase-7-boundary becomes a documented lie").
- The `Recipe.engine` Literal extension's snapshot diff already exists in `tools/contract-surface.snapshot.json` from S1-07. *Don't regenerate it here.* This story exercises the audit-and-link flow, not the regen flow.
- This story closes Step 4. After it's green, Step 4's deliverable is end-to-end: engine + property tests + transform + two recipes + golden patches + determinism + fence-CI enforcement + snapshot-link enforcement. The next step (Step 5) builds the graph + CLI on top.
- The PR description for this story should link ADR-P7-006 (whose snapshot diff this story verifies flows through correctly) — that's also the live test of the discipline this story enforces.
