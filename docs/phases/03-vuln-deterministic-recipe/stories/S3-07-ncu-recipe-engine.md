# Story S3-07 — `recipes/engines/ncu.py` — `NcuRecipeEngine` default + availability snapshot

**Step:** Step 3 — Ship the `NcuRecipeEngine` vertical: `tools/npm` + `tools/ncu` wrappers, `LockfileResolver`, `LockfileCanonicalizer`, recipe catalog + selector
**Status:** Ready
**Effort:** M
**Depends on:** S3-02, S3-06
**ADRs honored:** ADR-0003, ADR-0001

## Context

`NcuRecipeEngine` is the production-default engine. It implements the `RecipeEngine` ABC frozen at v0.3.0 by S1-03, drives the `tools/ncu.py` wrapper to bump `package.json`, and returns a `RecipeApplication(diff, files_changed, engine_stdout, engine_stderr, exit_code)`. Its `available()` does `which ncu` + a version-digest check; the result is **snapshotted once at orchestrator entry** per Gap 6 and stored in `RemediationAttempt.engine_availability` — downstream consumers (selector, transform, coordinator) read from the snapshot, never call `available()` again. The adversarial test `tests/adv/test_engine_availability_snapshot.py` pins this invariant by inducing flux mid-run.

The engine itself is **stateless given its `ApplyContext`**: no I/O outside the wrapper call, no subprocess directly.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #2a NcuRecipeEngine` — invocation pattern + sandbox profile + cold-start cost.
  - `../phase-arch-design.md §"Gap analysis" #6` — engine-availability snapshot invariant.
  - `../phase-arch-design.md §"Cross-cutting concerns" engine-availability snapshot invariant` — pin lineage.
- **Phase ADRs:**
  - `../ADRs/0003-recipe-engine-ncu-default-openrewrite-stub-registered.md` — primary contract.
  - `../ADRs/0001-transform-recipe-engine-two-abc-contract.md` — `RecipeEngine` ABC.
- **Source design:**
  - `../final-design.md §Goals #4` — `NcuRecipeEngine` as default.
  - `../final-design.md §Goals #6 — engine-availability snapshot at orchestrator entry`.
- **Existing code:**
  - `src/codegenie/recipes/contract.py` (S1-03) — `RecipeEngine` ABC + `RecipeApplication` Pydantic.
  - `src/codegenie/tools/ncu.py` (S3-02) — wrapper.
  - `src/codegenie/catalogs/tools/__init__.py` (S3-03) — version-digest verification helper for `ncu`.

## Goal

Ship `src/codegenie/recipes/engines/ncu.py` exporting `NcuRecipeEngine(RecipeEngine)` with `available()` (binary present + version digest matches) and `apply(recipe, repo_overlay, ctx)` (calls `tools.ncu.run(...)`, returns `RecipeApplication`). Land the engine-availability snapshot helper that the orchestrator (S5-03) calls at entry and the adversarial test that pins the invariant.

## Acceptance criteria

- [ ] `src/codegenie/recipes/engines/ncu.py` exports `class NcuRecipeEngine(RecipeEngine)` with `name = "ncu"`, `applies_to_engines = ("ncu",)`.
- [ ] `NcuRecipeEngine.available() -> bool` checks (1) `shutil.which("ncu") is not None` and (2) the version on `$PATH` matches the digest in `tools/digests.yaml` via the helper from S3-03.
- [ ] `NcuRecipeEngine.apply(recipe, repo_overlay, ctx) -> RecipeApplication`:
  - Resolves `target` (default `"patch"`) and `filter_packages` from `recipe.params`.
  - Calls `await tools.ncu.run(package_file=repo_overlay/"package.json", target=target, filter_packages=filter_packages, raw_output_path=ctx.engine_stdout_path)`.
  - On success → reads modified `package.json`, computes `diff` (vs the pre-overlay copy), returns `RecipeApplication(diff=diff_bytes, files_changed=[Path("package.json")], engine_stdout_path=ctx.engine_stdout_path, engine_stderr_path=ctx.engine_stderr_path, exit_code=0)`.
  - On non-zero exit → returns `RecipeApplication(diff=b"", files_changed=[], engine_stdout_path=..., engine_stderr_path=..., exit_code=<n>)` — the transform inspects + emits `confidence: low`.
- [ ] `src/codegenie/recipes/engines/availability.py` exports `snapshot_engine_availability() -> dict[str, bool]` — calls `available()` on each registered engine **once**, returns an immutable dict.
- [ ] `RecipeEngine` is registered via `@register_engine`; the registry from S1-03 returns the new engine when iterated.
- [ ] `tests/unit/recipes/engines/test_ncu_engine.py` ≥ 4 tests: happy path (`apply` returns non-empty diff), non-zero exit, missing-binary `available()==False`, version-digest mismatch `available()==False`.
- [ ] `tests/adv/test_engine_availability_snapshot.py` — induce flux (mock `available()` to flip during run); consumers reading from the snapshot continue to see the original value; consumers calling `available()` directly are absent (verified via AST scan or import-check).
- [ ] `ruff check`, `mypy --strict`, `pytest` pass.

## Implementation outline

1. Land `tests/unit/recipes/engines/test_ncu_engine.py` + `tests/adv/test_engine_availability_snapshot.py` first (red).
2. Implement `src/codegenie/recipes/engines/ncu.py`:
   - `available()` — `shutil.which("ncu")` + `_verify_ncu_digest()` (consults `tools/digests.yaml` helper from S3-03).
   - `apply(...)` — pre-snapshot bytes (`pkg_before = (repo_overlay/"package.json").read_bytes()`), call wrapper, post-snapshot bytes (`pkg_after`), compute `diff = unified_diff(pkg_before, pkg_after, ...)`. Return `RecipeApplication`.
3. Implement `src/codegenie/recipes/engines/availability.py` — iterates registered engines once, caches in-process.
4. Register the engine via the S1-03 decorator (`@register_engine`).
5. Wire the snapshot consumer in the test harness so the adversarial test can prove the invariant (no engine consumer calls `.available()` mid-run).

## TDD plan — red / green / refactor

### Red
Path: `tests/adv/test_engine_availability_snapshot.py`
```python
from unittest.mock import patch

import pytest

from codegenie.recipes.engines.availability import snapshot_engine_availability
from codegenie.recipes.engines.ncu import NcuRecipeEngine


def test_snapshot_immune_to_mid_run_flux():
    # Initial state: ncu present
    with patch.object(NcuRecipeEngine, "available", return_value=True):
        snap = snapshot_engine_availability()
    assert snap["ncu"] is True

    # Now flip ncu's availability mid-run
    with patch.object(NcuRecipeEngine, "available", return_value=False):
        # Selector / transform / coordinator must read from `snap`, not re-call .available()
        assert snap["ncu"] is True, (
            "snapshot must not change after capture; consumers must read from the snapshot"
        )
```

Path: `tests/unit/recipes/engines/test_ncu_engine.py`
```python
import pytest
from pathlib import Path
from unittest.mock import patch

from codegenie.recipes.engines.ncu import NcuRecipeEngine
from codegenie.recipes.contract import RecipeApplication


@pytest.mark.asyncio
async def test_apply_happy_path_returns_non_empty_diff(tmp_path, recipe_first, apply_ctx):
    (tmp_path/"package.json").write_text('{"name":"x","dependencies":{"express":"4.17.0"}}')
    with patch("codegenie.recipes.engines.ncu.ncu.run") as run:
        # Wrapper returns a NcuResult that mutated package.json
        async def fake_run(*a, **kw):
            (tmp_path/"package.json").write_text('{"name":"x","dependencies":{"express":"4.17.1"}}')
            class R: exit_code = 0; upgrades = {"express": "4.17.1"}
            return R()
        run.side_effect = fake_run
        eng = NcuRecipeEngine()
        result = await eng.apply(recipe_first, tmp_path, apply_ctx)
    assert result.exit_code == 0
    assert b"4.17.1" in result.diff
    assert Path("package.json") in result.files_changed


def test_available_false_when_binary_missing():
    with patch("shutil.which", return_value=None):
        assert NcuRecipeEngine().available() is False


def test_available_false_when_digest_mismatches():
    with patch("shutil.which", return_value="/usr/local/bin/ncu"), \
         patch("codegenie.recipes.engines.ncu._verify_ncu_digest", return_value=False):
        assert NcuRecipeEngine().available() is False
```

### Green
Smallest impl: stateless class implementing the two ABC methods; snapshot helper is a one-shot dict comprehension over registered engines.

### Refactor
- Once S5-03 lands and the coordinator consumes the snapshot, ensure no consumer imports `NcuRecipeEngine` directly to call `.available()`. A small static check in `scripts/check_no_direct_available_calls.py` is appropriate (defer to S7-07 if not needed sooner).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/recipes/engines/__init__.py` | New — package marker |
| `src/codegenie/recipes/engines/ncu.py` | New — `NcuRecipeEngine` |
| `src/codegenie/recipes/engines/availability.py` | New — `snapshot_engine_availability()` |
| `tests/unit/recipes/engines/test_ncu_engine.py` | New — ≥ 4 tests |
| `tests/adv/test_engine_availability_snapshot.py` | New — invariant pin |

## Out of scope

- **`OpenRewriteEngineStub`** — handled by S6-01.
- **The transform that drives this engine** — handled by S5-01.
- **Snapshot consumption by the coordinator** — handled by S5-03 (this story exposes the helper).
- **`tools/ncu.py` wrapper itself** — landed in S3-02.

## Notes for the implementer
- The engine is **stateless given `ApplyContext`** — no module-level mutable state, no in-memory caching across `apply()` calls. Caching is the resolver's job (S3-08).
- The diff computation is a plain `difflib.unified_diff` over the pre/post `package.json` bytes; do **not** invoke `git diff` here (that's the transform's job over the worktree).
- `available()` must be **cheap and idempotent** — a `shutil.which` + a small hash check. Don't call `ncu --version` (that's a subprocess; the digest verification from S3-03 reads the on-disk binary's hash instead, which is faster and matches the pin-manifest contract).
- The engine-availability snapshot is captured **once at orchestrator entry** — re-calling `.available()` during a run is forbidden. The adversarial test pins this; if a future contributor adds a `.available()` re-call mid-run, the test breaks.
- The `available()`-returning-False path **never raises** — the selector consumes the snapshot via `engine_availability` and emits `RecipeSelection(reason="no_engine")` instead. No exception leaks past the engine.
- Per Rule 12 (Fail loud): when `available() == False` due to a digest mismatch, the engine logs a `structlog` event with both observed and expected digests so the operator can update `tools/digests.yaml` in a reviewed PR.
- The `applies_to_engines` field is `("ncu",)` — a single-element tuple. The reason it's a sequence (not a scalar) is to give Phase-7's potential `dockerfile_rewrite` engine room to claim multiple recipe-engine names without an ABC bump.
