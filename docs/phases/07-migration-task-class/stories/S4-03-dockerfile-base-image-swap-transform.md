# Story S4-03 — `DockerfileBaseImageSwapTransform`

**Step:** Step 4 — Land `DockerfileRecipeEngine`, `DockerfileBaseImageSwapTransform`, and the multi-stage refactor recipe
**Status:** Ready
**Effort:** M
**Depends on:** S4-01
**ADRs honored:** ADR-P7-001 (six named seams — new files only), ADR-P7-004 (handrolled-only), ADR-P7-006 (`Recipe.engine` Literal extension)

## Context

The transform sits between the graph's `apply_recipe` node and the engine: it does the worktree dance (`git worktree add`, dirty-tree refusal, branch naming), invokes `DockerfileRecipeEngine.apply` (S4-01), runs byte-only canonicalization on the serialized output, calls `git format-patch -1 --stdout`, and tears down. It is the Phase 7 analogue of Phase 3's `NpmPackageUpgradeTransform` and implements the same `Transform` ABC verbatim.

Without this story the engine is unusable from the graph — the `apply_recipe` node calls `Transform.run`, not `RecipeEngine.apply`. The transform is also where the worktree-contamination defense lives (`WorktreeContaminated` on dirty-tree start), which is the load-bearing isolation property for running multiple distroless workflows concurrently against the same repo.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design ›5. DockerfileBaseImageSwapTransform` — interface, internal structure, performance envelope, failure behavior.
  - `../phase-arch-design.md §Testing strategy ›Unit tests` — `test_dockerfile_base_image_swap.py` ≥8 tests.
  - `../phase-arch-design.md §Edge cases` rows 1, 2, 7, 8 — Dockerfile rejected, round-trip failed, registry auth, buildkit cache corruption.
  - `../phase-arch-design.md §Harness engineering` — deterministic git env, subprocess allowlist.
- **Phase ADRs:**
  - `../ADRs/0001-six-named-additive-seams-and-adr-0028-amendment.md` — ADR-P7-001 — transforms are new files, not edits.
  - `../ADRs/0005-openrewrite-rewrite-docker-deferred.md` — ADR-P7-004 — `requires_recipe_engines = ["dockerfile"]` is the only engine the transform demands.
  - `../ADRs/0007-recipe-engine-literal-extended-with-dockerfile.md` — ADR-P7-006.
- **Production ADRs:**
  - `../../../production/adrs/0011-recipe-first-rag-llm-fallback-planning.md` — the transform is *the* recipe-first path for distroless.
- **Existing code:**
  - `src/codegenie/transforms/npm_package_upgrade.py` — Phase 3's transform; mirror its structure (worktree, apply, canonicalize, format-patch, cleanup, return `TransformOutput`).
  - `src/codegenie/recipes/contract.py` — `Transform` ABC + `TransformInput` / `TransformOutput`.
  - `src/codegenie/recipes/engines/dockerfile_engine.py` — the engine landed in S4-01.

## Goal

`DockerfileBaseImageSwapTransform` exists, registers via `@register_transform` with `name="dockerfile_base_image_swap"`, `applies_to_tasks=["distroless_migration"]`, `requires_recipe_engines=["dockerfile"]`; creates a `git worktree` under `.codegenie/migration/<run-id>/worktree/`; refuses dirty trees by raising `WorktreeContaminated`; names the branch `codegenie/distroless/<sha>`; returns a deterministic `TransformOutput` with `patch_bytes` produced by `DockerfileRecipeEngine.apply` + `git format-patch`.

## Acceptance criteria

- [ ] `src/codegenie/transforms/dockerfile_base_image_swap.py` exists with `class DockerfileBaseImageSwapTransform(Transform)` decorated by `@register_transform`.
- [ ] Class attributes: `name = "dockerfile_base_image_swap"`, `applies_to_tasks = ["distroless_migration"]`, `applies_to_languages = ["*"]`, `requires_recipe_engines = ["dockerfile"]`.
- [ ] `applies(input)` returns `True` iff `input.task_type == "distroless_migration"` and a Dockerfile is present in the recipe selection's match context; returns `False` otherwise (no raise).
- [ ] `run(input)` creates a worktree at `.codegenie/migration/<run-id>/worktree/` via `git worktree add` and cleans it up in a `finally` block — verified by a unit test that asserts the directory does not exist after `run` returns (success or failure).
- [ ] Dirty-tree refusal: if the source repo has uncommitted changes when `run` starts, it raises `WorktreeContaminated` with the dirty file list in the message; no worktree is created.
- [ ] Branch naming: the worktree's branch is exactly `codegenie/distroless/<sha>` where `<sha>` is the first 12 chars of `blake3(target_image)` (or equivalent deterministic stable identifier — pick one and document it in the docstring).
- [ ] `run` returns `TransformOutput(exit_code=0, patch_bytes=<bytes>, confidence="high")` on success; on engine failure returns `TransformOutput(exit_code=N, errors=[...], confidence="medium"|"low")` matching the engine's exit-code translation table.
- [ ] No `import random`, no `import time`, no `from datetime import` of `datetime.now`/`time.time` anywhere under `src/codegenie/transforms/dockerfile_base_image_swap.py` (fence-CI deny-imports).
- [ ] The TDD plan's red test exists, was committed, and is green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on the new files.

## Implementation outline

1. Read `src/codegenie/transforms/npm_package_upgrade.py` end-to-end — mirror its structure.
2. Skeleton: class attributes, `applies`, `run`. Wire `@register_transform`.
3. `_assert_clean_tree(repo_path)` helper: `git status --porcelain` returns non-empty → raise `WorktreeContaminated(files=...)`.
4. `_make_worktree(repo_path, run_id, branch_name)` helper: `git worktree add -b <branch> .codegenie/migration/<run-id>/worktree HEAD`. Cleanup via `git worktree remove --force`.
5. Inside the worktree, look up the engine via `get_recipe_engine("dockerfile")` and call `engine.apply(ctx)`; translate the `RecipeApplication` into a `TransformOutput`.
6. Wire the deterministic `git format-patch` call inside the worktree (engine returns `patch_bytes` already; transform passes them through).
7. Add typed errors: `WorktreeContaminated`. Re-export `RoundTripFailure`, `DockerfileRejected` from the engine module — don't redefine.
8. Wire structlog: `transform="dockerfile_base_image_swap"`, `run_id=<id>`, `worktree=<path>`, `branch=<name>`, exit at success/failure with `exit_code` + `errors`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/transforms/test_dockerfile_base_image_swap.py`

```python
# tests/unit/transforms/test_dockerfile_base_image_swap.py
def test_transform_registers_and_applies_dispatches_on_task_type():
    transform = get_transform("dockerfile_base_image_swap")
    assert transform.applies_to_tasks == ["distroless_migration"]
    assert transform.requires_recipe_engines == ["dockerfile"]


def test_run_produces_deterministic_patch(tmp_path_with_git_repo, monkeypatch):
    # arrange: bare-minimum repo with single-stage Dockerfile
    repo = tmp_path_with_git_repo  # fixture creates repo + initial commit
    target = "cgr.dev/chainguard/node:20-distroless@sha256:" + "a" * 64
    input_ = TransformInput(repo_path=repo, target_image=target, task_type="distroless_migration", run_id="r1", ...)

    # act
    transform = DockerfileBaseImageSwapTransform()
    output_a = transform.run(input_)
    output_b = transform.run(input_)  # second run, fresh worktree

    # assert
    assert output_a.exit_code == 0
    assert output_b.exit_code == 0
    assert output_a.patch_bytes == output_b.patch_bytes  # determinism


def test_dirty_tree_raises_worktree_contaminated(tmp_path_with_git_repo):
    # arrange: write an uncommitted file
    (tmp_path_with_git_repo / "DIRTY").write_text("uncommitted\n")
    # act + assert
    with pytest.raises(WorktreeContaminated) as exc:
        DockerfileBaseImageSwapTransform().run(input_for(tmp_path_with_git_repo))
    assert "DIRTY" in str(exc.value)


def test_worktree_cleanup_on_exception(tmp_path_with_git_repo, monkeypatch):
    # arrange: monkeypatch the engine to raise mid-apply
    # act
    with pytest.raises(Exception):
        DockerfileBaseImageSwapTransform().run(input_)
    # assert: no `.codegenie/migration/<run-id>/worktree/` remains
    assert not (tmp_path_with_git_repo / ".codegenie/migration/r1/worktree").exists()
```

Run. They fail because the transform doesn't exist yet (`ImportError`) or the registry doesn't know `"dockerfile_base_image_swap"`. Commit as marker.

### Green — make it pass

Add `src/codegenie/transforms/dockerfile_base_image_swap.py` with the minimum surface for the four red tests. Use `git worktree add -b` for branch creation. Use `git worktree remove --force` in a `finally`. Subprocess-allowlisted via Phase 5's chokepoint — don't roll your own `subprocess.run`; use the existing `sandbox.host.subprocess` helper if Phase 5 exposes one (check before writing).

### Refactor — clean up

- Extract `_assert_clean_tree`, `_make_worktree`, `_remove_worktree` as private helpers in the module.
- Type hints on `applies` / `run` / helpers; return types pinned.
- Docstrings linking ADR-P7-001 (new-file rule) and ADR-P7-006 (engine routing).
- Branch-name determinism: document the `<sha>` derivation explicitly in the docstring; encode-then-truncate, not truncate-then-encode (test the edge of the choice).
- Confirm cleanup happens in `finally` for every code path: engine success, engine failure, exception inside the engine, `WorktreeContaminated` (no worktree to clean), unrelated `Exception` from the subprocess wrapper.
- Edge cases from `phase-arch-design.md §Edge cases` rows 1, 2, 7, 8 — translate to `TransformOutput.exit_code` values; assert each in the unit test file.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/transforms/dockerfile_base_image_swap.py` | New file — implements the `Transform` ABC. |
| `tests/unit/transforms/test_dockerfile_base_image_swap.py` | New test — anchors TDD red phase; ≥8 tests per `phase-arch-design.md §Testing strategy ›Unit tests`. |
| `tests/unit/transforms/__init__.py` | New empty file — package marker if not present. |
| `tests/conftest.py` (or `tests/unit/transforms/conftest.py`) | Add `tmp_path_with_git_repo` fixture if it doesn't already exist; reuse Phase 3's if it does. |

## Out of scope

- **Engine implementation.** — handled by story S4-01 (this story consumes it).
- **Seed recipes (`swap_base_image_single_stage.yaml`, `multi_stage_distroless_refactor.yaml`).** — handled by stories S4-04 / S4-05.
- **Golden patches.** — handled by stories S4-04 / S4-05.
- **Sandbox build validation (`docker buildx build`).** — handled by Phase 5's `validate_in_sandbox` node; out of scope here.
- **Cross-task chain-no-collision test.** — handled by story S5-07.
- **Replay-after-SIGKILL test.** — handled by story S5-08.

## Notes for the implementer

- `git worktree add -b <branch>` will fail loudly if the branch already exists. Use a deterministic branch name suffix (`<sha>`) so re-runs are idempotent; if the worktree path already exists (prior crash), `git worktree remove --force` it before `add`. Document this rationale in the docstring — the next reader will wonder why the cleanup runs *before* the add.
- The `WorktreeContaminated` exception must include the dirty file list in its `__str__` — that's what the operator sees in the CLI's exit-11 error message (`phase-arch-design.md §Component 12. cli/migrate.py`). Don't swallow the file list.
- `subprocess.run(["git", ...])` must go through Phase 5's allowlisted chokepoint (`src/codegenie/sandbox/host/subprocess.py` or equivalent). Direct `subprocess.run` calls are forbidden by ADR-0003 / ALLOWED_BINARIES; even if it works locally, fence-CI / unit-test snapshots will catch it.
- `.codegenie/migration/<run-id>/worktree/` is created relative to the *source repo*, not the developer's home directory. Use `repo_path / ".codegenie" / "migration" / run_id / "worktree"` — relative paths break under `pytest --basetemp`.
- Per `CLAUDE.md` Rule 12 ("Fail loud"), `WorktreeContaminated` cannot return `False` from `applies` quietly — `applies` is the *dispatch* hook, not the *guard*. The guard is at the top of `run`; if the tree is dirty, `run` raises, the graph sees the exception, the loop routes to `escalate`.
- Phase 6's `id()`-diff hook will fire on any in-place mutation of the `DistrolessLedger` that the transform's caller (the `apply_recipe` node) does. Don't mutate `TransformInput` — treat it as `frozen=True` even if it isn't.
- Read `CLAUDE.md` Rule 11 before authoring: if Phase 3's transform uses class-based registration and you'd prefer a function-decorator pattern, use class-based. Conformance > taste.
